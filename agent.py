import os
import re
import random
import wave
import platform
import vertexai
from vertexai.generative_models import GenerativeModel
from google.cloud import texttospeech, speech

# --- MOVIEPY V2 CLOUD IMPORTS ---
from moviepy.video.VideoClip import TextClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.fx.all import crop

from uploader import upload_to_youtube 

# --- OS SPECIFIC SETUP ---
if platform.system() == "Darwin":
    if os.path.exists("/opt/homebrew/bin/magick"):
        from moviepy.config import change_settings
        change_settings({"IMAGEMAGICK_BINARY": "/opt/homebrew/bin/magick"})
    FONT_PATH = "/System/Library/Fonts/Helvetica.ttc"
else:
    FONT_PATH = "DejaVu-Sans-Bold"  # GitHub Actions (Ubuntu)

TTS_SAMPLE_RATE = 24000  # Google Neural2 native output rate

# --- 1. INITIALIZE ---
PROJECT_ID = "shorts-auto-agent" 
LOCATION = "us-central1"
vertexai.init(project=PROJECT_ID, location=LOCATION)
model = GenerativeModel("gemini-2.5-flash")

# --- 2. GENERATE SCRIPT & VOICE ---
print("Asking Gemini to choose an amazing topic...")
topic_prompt = """
You are a viral YouTube Shorts strategist. Your job is to pick ONE topic for a short-form video that will make someone stop mid-scroll.

A great topic has at least 2 of these:
- A shocking contrast ("the deadliest X that looks completely harmless")
- A counterintuitive fact ("why X actually does the opposite of what you think")
- A hidden or suppressed truth ("the thing they don't teach you about X")
- A visceral visual hook (something the viewer can picture immediately)
- A scale that breaks intuition (impossibly big, small, fast, old, strange)

Hard rules:
- Real world ONLY: nature, history, ocean, space, animals, human body, geography, crime, psychology, ancient civilizations, disasters
- NO AI, tech, politics, medicine, or religion
- The topic must imply a story — not just a subject
- 8 to 14 words
- Write it like a half-finished thought that DEMANDS to be completed
- Output ONLY the topic. No punctuation at the end. No quotes. No labels.

Bad example: Deep ocean creatures
Good example: The fish that dissolves itself alive before transforming into something else
""".strip()

trending_topic = model.generate_content(topic_prompt).text.strip()
trending_topic = re.sub(r'[\r\n]+', ' ', trending_topic).strip()
trending_topic = re.sub(r'^[\'"\-\s]+|[\'"\-\s]+$', '', trending_topic).strip()
print(f"Chosen topic: {trending_topic}")

prompt = (
    "You are a top-tier YouTube Shorts scriptwriter. Your scripts don't just inform — they hijack attention and make skipping feel physically impossible.\n\n"
    f"TOPIC: {trending_topic}\n\n"
    "---\n\n"
    "STRUCTURAL BLUEPRINT (follow this arc exactly):\n\n"
    "[HOOK — Lines 1-2]\n"
    "Open with a statement so strange, wrong-sounding, or visceral that stopping is involuntary.\n"
    "NOT a question. NOT 'Did you know.' A declarative gut-punch.\n"
    "Example pattern: 'A [creature/person/place] [did something that violates expectations] — and science still can't explain why.'\n\n"
    "[PULL — Lines 3-5]\n"
    "Instantly reward them for stopping. Give one concrete, specific detail that proves this is real and worth 55 seconds.\n"
    "Kill all vagueness here. Numbers, names, places — make it tactile.\n\n"
    "[ESCALATION — Lines 6-12]\n"
    "This is the engine. Each sentence must make the next one feel inevitable.\n"
    "Use these transitions sparingly but deliberately:\n"
    "- 'But that's not even the strange part.'\n"
    "- 'Here's where it breaks down.'\n"
    "- 'Nobody talks about what happened next.'\n"
    "Never summarize. Always reveal.\n\n"
    "[REFRAME — Lines 13-15]\n"
    "Flip the viewer's understanding of everything they just heard.\n"
    "One fact that recontextualizes the whole story. This is your 'oh shit' moment.\n\n"
    "[EXIT LINE — Line 16]\n"
    "Do NOT end with 'so next time you...' or 'isn't that crazy?'\n"
    "End with either:\n"
    "  A) A lingering unresolved fact that haunts them ('And nobody has ever found it since.')\n"
    "  B) A direct challenge that triggers comments ('Most people get this completely wrong.')\n\n"
    "---\n\n"
    "WRITING RULES:\n\n"
    "- Sentence length: Vary it. Short. Then longer for rhythm. Then short again. Never 3 long sentences in a row.\n"
    "- Every sentence must earn its place. If it doesn't escalate, reveal, or hook — cut it.\n"
    "- No metaphors. No 'imagine if.' Ground everything in what actually happened.\n"
    "- No filler openers: Never start with 'So,' 'Well,' 'Today,' 'In this video,' or 'Have you ever.'\n"
    "- Write for the voice — read it aloud in your head. It must feel spoken, not written.\n"
    "- Zero stage directions, labels, or formatting. Raw spoken text only.\n\n"
    "STRICT LENGTH: 140-155 words exactly. Count before outputting.\n\n"
    "OUTPUT: The script only. Nothing else."
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
    sample_rate_hertz=TTS_SAMPLE_RATE  # Neural2 native rate
)

tts_response = tts_client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)

# ✅ RAW AUDIO FIX: Save initial file separately to prevent FFmpeg corruption
with open("voiceover_raw.wav", "wb") as out:
    out.write(tts_response.audio_content)

# --- 3. TRIM AUDIO (must happen before STT) ---
print("Trimming audio...")
raw_audio_clip = AudioFileClip("voiceover_raw.wav")
safe_duration = min(58.0, raw_audio_clip.duration)

# Process from the raw file and save to the final file
trimmed_clip = raw_audio_clip.subclip(0, safe_duration)
trimmed_clip.write_audiofile("voiceover.wav", ffmpeg_params=["-ac", "1"])  # Trim + force mono

# Clean up memory locks
raw_audio_clip.close()
trimmed_clip.close()
print(f"Audio trimmed to {safe_duration:.1f}s")

# --- 4. GET WORD-LEVEL TIMESTAMPS ---
print("Syncing captions...")

# Read actual sample rate from file — never guess
with wave.open("voiceover.wav", "rb") as wav_file:
    actual_sample_rate = wav_file.getframerate()
print(f"Detected sample rate: {actual_sample_rate} Hz")

stt_client = speech.SpeechClient()
with open("voiceover.wav", "rb") as audio_file:
    content = audio_file.read()

audio_recognition = speech.RecognitionAudio(content=content)
stt_config = speech.RecognitionConfig(
    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
    sample_rate_hertz=actual_sample_rate,  # Always correct, never guessed
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

print(f"Transcribed {len(all_words)} words.")

# --- 5. PREPARE BACKGROUND VIDEO & CALCULATE DYNAMIC WIDTH ---
print("Calculating dynamic text bounds...")
full_video = VideoFileClip("background_loop.mp4")
audio_clip = AudioFileClip("voiceover.wav")  # Load trimmed clean version

MIN_SKIP = 26
start_time = random.uniform(MIN_SKIP, max(MIN_SKIP, full_video.duration - safe_duration))
video_bg = full_video.subclip(start_time, start_time + safe_duration)

# Calculate exactly how wide the video will be AFTER the 9:16 crop
w, h = video_bg.size
target_width = int(h * (9 / 16))
final_video_width = target_width if w > target_width else w
dynamic_text_width = int(final_video_width * 0.85)

# Crop to 9:16
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
    duration = end_t - start_t

    if start_t >= safe_duration or duration <= 0:
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
    ).set_start(start_t).set_duration(duration).set_position(('center', 'center'))

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
