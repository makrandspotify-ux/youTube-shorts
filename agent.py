import os
import re
import random
import platform
import vertexai
from vertexai.generative_models import GenerativeModel
from google.cloud import texttospeech, speech
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
from moviepy.video.fx.all import crop  # ✅ Only one crop import, correct v1 style
from uploader import upload_to_youtube 

# --- 1. OS-SPECIFIC SETUP ---
if platform.system() == "Darwin":
    if os.path.exists("/opt/homebrew/bin/magick"):
        from moviepy.config import change_settings
        change_settings({"IMAGEMAGICK_BINARY": "/opt/homebrew/bin/magick"})
    FONT_PATH = "/System/Library/Fonts/Helvetica.ttc"
else:
    FONT_PATH = "DejaVu-Sans-Bold"

# --- 2. INITIALIZE GOOGLE CLOUD ---
PROJECT_ID = "shorts-auto-agent"
LOCATION = "us-central1"
vertexai.init(project=PROJECT_ID, location=LOCATION)
model = GenerativeModel("gemini-2.0-flash-001")  # ✅ Fixed: correct Vertex AI model name

# --- 3. GENERATE SCRIPT & VOICE ---
print("Choosing a topic...")
topic_prompt = """
Pick ONE insanely clickable YouTube Shorts topic for today (History, Science, Mysteries, or Wildlife).
6 to 12 words. Output ONLY the topic line.
""".strip()

trending_topic = model.generate_content(topic_prompt).text.strip()
print(f"Topic: {trending_topic}")

script_prompt = (
    f"Write a punchy YouTube Short script about: {trending_topic}. "
    "Start with an aggressive hook. Length: 140-155 words."
)

script_response = model.generate_content(script_prompt).text
cleaned_script = re.sub(r'[\(\[].*?[\)\]]', '', script_response).strip()

print("Generating voiceover...")
tts_client = texttospeech.TextToSpeechClient()
synthesis_input = texttospeech.SynthesisInput(text=cleaned_script)
voice = texttospeech.VoiceSelectionParams(language_code="en-US", name="en-US-Neural2-J")
audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.LINEAR16, speaking_rate=1.2)

tts_response = tts_client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
with open("voiceover.wav", "wb") as out:
    out.write(tts_response.audio_content)

# --- 4. GET WORD-LEVEL TIMESTAMPS ---
stt_client = speech.SpeechClient()
with open("voiceover.wav", "rb") as audio_file:
    content = audio_file.read()

audio_recognition = speech.RecognitionAudio(content=content)
stt_config = speech.RecognitionConfig(
    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
    language_code="en-US",
    enable_word_time_offsets=True,
)

operation = stt_client.long_running_recognize(config=stt_config, audio=audio_recognition)
stt_result = operation.result(timeout=90)

all_words = []
for result in stt_result.results:
    for word_info in result.alternatives[0].words:
        all_words.append({
            'word': word_info.word.upper(),
            'start': word_info.start_time.total_seconds(),
            'end': word_info.end_time.total_seconds()
        })

# --- 5. VIDEO PROCESSING ---
print("Editing video...")
full_video = VideoFileClip("background_loop.mp4")
audio_clip = AudioFileClip("voiceover.wav")

safe_duration = min(58.0, audio_clip.duration)
audio_clip = audio_clip.subclip(0, safe_duration)

start_time = random.uniform(0, max(0, full_video.duration - safe_duration))
video_bg = full_video.subclip(start_time, start_time + safe_duration)

# Dynamic 9:16 Crop & Width Calculation
w, h = video_bg.size
target_width = int(h * (9 / 16))
video_bg = crop(video_bg, x_center=w/2, y_center=h/2, width=target_width, height=h)  # ✅ Fixed: v1 style
text_width = int(target_width * 0.85)

# --- 6. CAPTION GENERATION ---
word_clips = []
chunk_size = 3

for i in range(0, len(all_words), chunk_size):
    chunk = all_words[i:i + chunk_size]
    phrase = " ".join([w['word'] for w in chunk])
    start_t = chunk[0]['start']
    end_t = chunk[-1]['end']

    if start_t < safe_duration:
        caption_clip = TextClip(
            phrase,
            fontsize=60,
            color='yellow',
            font=FONT_PATH,
            stroke_color='black',
            stroke_width=2,
            method='caption',
            size=(text_width, None)
        ).set_start(start_t).set_duration(min(end_t - start_t, safe_duration - start_t)).set_position(('center', 'center'))
        word_clips.append(caption_clip)

# --- 7. EXPORT & UPLOAD ---
final_video = CompositeVideoClip([video_bg] + word_clips).set_audio(audio_clip)
final_video.write_videofile("final_short.mp4", fps=24, codec="libx264", audio_codec="aac")

metadata_prompt = f"Write a 2-sentence YouTube description and 4 hashtags for a video about {trending_topic}."
metadata = model.generate_content(metadata_prompt).text.strip()

upload_to_youtube("final_short.mp4", f"{trending_topic} #shorts", metadata)
