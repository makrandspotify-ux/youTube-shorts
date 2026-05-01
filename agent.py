import vertexai
from vertexai.generative_models import GenerativeModel
from google.cloud import texttospeech, speech
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
from moviepy.video.fx.all import crop
import os
import re
import random
import platform
from uploader import upload_to_youtube 

# --- MAC SPECIFIC FIX ---
if platform.system() == "Darwin":
    if os.path.exists("/opt/homebrew/bin/magick"):
        from moviepy.config import change_settings
        change_settings({"IMAGEMAGICK_BINARY": "/opt/homebrew/bin/magick"})
    FONT_PATH = "/System/Library/Fonts/Helvetica.ttc"
else:
    FONT_PATH = "DejaVu-Sans-Bold"  # ✅ GitHub Actions (Ubuntu) font

# Sample rates
TTS_SAMPLE_RATE = 24000  # ✅ Google Neural2 native output rate
STT_SAMPLE_RATE = 44100  # ✅ MoviePy always rewrites WAV at this rate

# --- 1. INITIALIZE ---
PROJECT_ID = "shorts-auto-agent" 
LOCATION = "us-central1"
vertexai.init(project=PROJECT_ID, location=LOCATION)
model = GenerativeModel("gemini-2.5-flash")

# --- 2. GENERATE SCRIPT & VOICE ---
print("Asking Gemini to choose an amazing topic...")
topic_prompt = """
Pick ONE insanely clickable YouTube Shorts topic for today.

Constraints:
- Must be a real-world topic (e.g., bizarre historical facts, crazy science, deep ocean mysteries, space anomalies, true crime, or wildlife).
- STRICTLY NO AI, tech, or futuristic meta-topics. Give me something real, grounded, and fascinating.
- 6 to 12 words.
- Not politics, not explicit, not medical advice.
- Output ONLY the topic line. No quotes, no bullets, no extra text.
""".strip()

trending_topic = model.generate_content(topic_prompt).text.strip()
trending_topic = re.sub(r'[\r\n]+', ' ', trending_topic).strip()
trending_topic = re.sub(r'^[\'"\-\s]+|[\'"\-\s]+$', '', trending_topic).strip()
print(f"Chosen topic: {trending_topic}")

prompt = (
    "Write a punchy YouTube Short script about: "
    f"{trending_topic}. "
    "No visual/audio cues, just spoken text. "
    "Start with an aggressive stop-scrolling hook. "
    "STRICT LENGTH: The script MUST be exactly between 140 and 155 words. This is critical to hit the 55-second audio mark."
)

print("Asking Gemini to write the script...")
script_response = model.generate_content(prompt).text
cleaned_script = re.sub(r'\*+', '', script_response)
cleaned_script = re.sub(r'[\(\[].*?[\)\]]', '', cleaned_script).strip()

print("Generating voiceover...")
tts_client = texttospeech.TextToSpeechClient()
fixed_ssml = cleaned_script.replace("AI", '<say-as interpret-as="characters">AI</say-as>')
synthesis_input = texttospeech.SynthesisInput(ssml=f"<speak>{fixed_ssml}</speak>")
voice = texttospeech.VoiceSelectionParams(language_code="en-US", name="en-US-Neural2-J")
audio_config = texttospeech.AudioConfig(
    audio_encoding=texttospeech.AudioEncoding.LINEAR16,
    speaking_rate=1.2,
    sample_rate_hertz=TTS_SAMPLE_RATE  # ✅ Explicit native rate
)

tts_response = tts_client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
with open("voiceover.wav", "wb") as out:
    out.write(tts_response.audio_content)

# --- 3. TRIM AUDIO (must happen before STT) ---
print("Trimming audio...")
audio_clip = AudioFileClip("voiceover.wav")
safe_duration = min(58.0, audio_clip.duration)
audio_clip = audio_clip.subclip(0, safe_duration)
audio_clip.write_audiofile("voiceover.wav", ffmpeg_params=["-ac", "1"])  # ✅ Trim + force mono
print(f"Audio trimmed to {safe_duration:.1f}s")

# --- 4. GET WORD-LEVEL TIMESTAMPS ---
print("Syncing captions...")
stt_client = speech.SpeechClient()

with open("voiceover.wav", "rb") as audio_file:
    content = audio_file.read()

audio_recognition = speech.RecognitionAudio(content=content)
stt_config = speech.RecognitionConfig(
    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
    sample_rate_hertz=STT_SAMPLE_RATE,  # ✅ Matches MoviePy resampled rate
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

# --- 5. PREPARE BACKGROUND VIDEO & CALCULATE DYNAMIC WIDTH ---
print("Calculating dynamic text bounds...")
full_video = VideoFileClip("background_loop.mp4")
audio_clip = AudioFileClip("voiceover.wav")  # Reload trimmed version

MIN_SKIP = 26
start_time = random.uniform(MIN_SKIP, max(MIN_SKIP, full_video.duration - safe_duration))
video_bg = full_video.subclip(start_time, start_time + safe_duration)

# Calculate exactly how wide the video will be AFTER the 9:16 crop
w, h = video_bg.size
target_width = int(h * (9 / 16))
final_video_width = target_width if w > target_width else w

# Magic Fix: The text box will now dynamically be exactly 85% of the screen width
dynamic_text_width = int(final_video_width * 0.85)

# Crop the video
if w != target_width:
    video_bg = crop(video_bg, x_center=w/2, y_center=h/2, width=target_width, height=h)

# --- 6. CREATE DYNAMIC WRAPPING CAPTIONS ---
word_clips = []
chunk_size = 3 

for i in range(0, len(all_words), chunk_size):
    chunk = all_words[i:i + chunk_size]
    phrase = " ".join([w['word'] for w in chunk])
    start_t = chunk[0]['start']
    end_t = chunk[-1]['end']

    if start_t >= safe_duration or (end_t - start_t) <= 0:
        continue

    caption_clip = TextClip(
        phrase, 
        fontsize=60, 
        color='yellow', 
        font=FONT_PATH,
        stroke_color='black',  
        stroke_width=2,
        method='caption',
        size=(dynamic_text_width, None)
    ).set_start(start_t).set_duration(end_t - start_t).set_position(('center', 'center'))

    word_clips.append(caption_clip)

# --- 7. COMPILE & EXPORT ---
print("Rendering final video...")
final_video = CompositeVideoClip([video_bg] + word_clips)
final_video = final_video.set_audio(audio_clip)

final_video.write_videofile("final_viral_short.mp4", fps=24, codec="libx264", audio_codec="aac")
print("\nSUCCESS! Video rendered in perfect Shorts format.")

# --- 8. AUTO-UPLOAD TO YOUTUBE ---
print("\nAsking Gemini to write the YouTube description and hashtags...")

metadata_prompt = f"""
Write a highly engaging, punchy YouTube Shorts description for a video about: '{trending_topic}'.
- Keep it under 3 sentences.
- Add an engaging question for the viewers to answer in the comments.
- Include 4-5 highly relevant viral hashtags at the bottom (always include #shorts).
- Output plain text only, no markdown formatting (like asterisks).
"""

generated_desc = model.generate_content(metadata_prompt).text.strip()

print("\n--- Generated Metadata ---")
print(generated_desc)
print("--------------------------\n")

print("Initializing YouTube Upload...")
video_title = f"{trending_topic} 🤯 #shorts"
upload_to_youtube("final_viral_short.mp4", video_title, generated_desc)
