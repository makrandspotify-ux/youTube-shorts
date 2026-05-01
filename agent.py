import os
import re
import random
import platform
import vertexai
from vertexai.generative_models import GenerativeModel
from google.cloud import texttospeech, speech
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
from moviepy.video.fx.all import crop
from uploader import upload_to_youtube

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
PROJECT_ID      = "shorts-auto-agent"
LOCATION        = "us-central1"
GEMINI_MODEL    = "gemini-2.5-flash"
TTS_VOICE       = "en-US-Neural2-J"
TTS_SPEED       = 1.2
SAMPLE_RATE     = 44100
MAX_DURATION    = 58.0
CAPTION_CHUNKS  = 3
CAPTION_FONT_SZ = 60
BACKGROUND_VID  = "background_loop.mp4"
VOICEOVER_FILE  = "voiceover.wav"
OUTPUT_FILE     = "final_short.mp4"

if platform.system() == "Darwin":
    if os.path.exists("/opt/homebrew/bin/magick"):
        from moviepy.config import change_settings
        change_settings({"IMAGEMAGICK_BINARY": "/opt/homebrew/bin/magick"})
    FONT_PATH = "/System/Library/Fonts/Helvetica.ttc"
else:
    FONT_PATH = "DejaVu-Sans-Bold"

# ─────────────────────────────────────────────
# INITIALIZE
# ─────────────────────────────────────────────
vertexai.init(project=PROJECT_ID, location=LOCATION)
model      = GenerativeModel(GEMINI_MODEL)
tts_client = texttospeech.TextToSpeechClient()
stt_client = speech.SpeechClient()

# ─────────────────────────────────────────────
# STEP 1 — GENERATE TOPIC & SCRIPT
# ─────────────────────────────────────────────
print("Generating topic...")
topic_prompt = (
    "Pick ONE insanely clickable YouTube Shorts topic for today "
    "(History, Science, Mysteries, or Wildlife). "
    "6 to 12 words. Output ONLY the topic line."
)
trending_topic = model.generate_content(topic_prompt).text.strip()
print(f"Topic: {trending_topic}")

script_prompt = (
    f"Write a punchy YouTube Shorts script about: {trending_topic}. "
    "Start with an aggressive hook. No stage directions or annotations. "
    "Length: 140-155 words."
)
raw_script    = model.generate_content(script_prompt).text
clean_script  = re.sub(r'[\(\[].*?[\)\]]', '', raw_script).strip()
print(f"Script ready ({len(clean_script.split())} words)")

# ─────────────────────────────────────────────
# STEP 2 — GENERATE VOICEOVER
# ─────────────────────────────────────────────
print("Generating voiceover...")
tts_response = tts_client.synthesize_speech(
    input=texttospeech.SynthesisInput(text=clean_script),
    voice=texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name=TTS_VOICE
    ),
    audio_config=texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        speaking_rate=TTS_SPEED,
        sample_rate_hertz=SAMPLE_RATE
    )
)
with open(VOICEOVER_FILE, "wb") as f:
    f.write(tts_response.audio_content)
print("Voiceover saved.")

# ─────────────────────────────────────────────
# STEP 3 — TRIM AUDIO & FORCE MONO (before STT)
# ─────────────────────────────────────────────
print("Trimming audio...")
audio_clip    = AudioFileClip(VOICEOVER_FILE)
safe_duration = min(MAX_DURATION, audio_clip.duration)
audio_clip    = audio_clip.subclip(0, safe_duration)
audio_clip.write_audiofile(
    VOICEOVER_FILE,
    ffmpeg_params=["-ac", "1"]  # Force mono for STT compatibility
)
print(f"Audio trimmed to {safe_duration:.1f}s")

# ─────────────────────────────────────────────
# STEP 4 — TRANSCRIBE WITH WORD TIMESTAMPS
# ─────────────────────────────────────────────
print("Transcribing audio...")
with open(VOICEOVER_FILE, "rb") as f:
    audio_bytes = f.read()

stt_result = stt_client.long_running_recognize(
    config=speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=SAMPLE_RATE,  # Match TTS output rate
        language_code="en-US",
        enable_word_time_offsets=True,
        enable_automatic_punctuation=True,
    ),
    audio=speech.RecognitionAudio(content=audio_bytes)
).result(timeout=90)

all_words = [
    {
        'word':  w.word.upper(),
        'start': w.start_time.total_seconds(),
        'end':   w.end_time.total_seconds()
    }
    for result in stt_result.results
    for w in result.alternatives[0].words
]
print(f"Transcribed {len(all_words)} words.")

# ─────────────────────────────────────────────
# STEP 5 — VIDEO PROCESSING
# ─────────────────────────────────────────────
print("Processing video...")
full_video  = VideoFileClip(BACKGROUND_VID)
audio_clip  = AudioFileClip(VOICEOVER_FILE)

# Pick a random start point in the background
start_time  = random.uniform(0, max(0, full_video.duration - safe_duration))
video_bg    = full_video.subclip(start_time, start_time + safe_duration)

# Crop to 9:16 portrait
w, h         = video_bg.size
target_width = int(h * (9 / 16))
video_bg     = crop(video_bg, x_center=w/2, y_center=h/2, width=target_width, height=h)
text_width   = int(target_width * 0.85)

# ─────────────────────────────────────────────
# STEP 6 — CAPTION GENERATION
# ─────────────────────────────────────────────
print("Generating captions...")
word_clips = []

for i in range(0, len(all_words), CAPTION_CHUNKS):
    chunk   = all_words[i:i + CAPTION_CHUNKS]
    phrase  = " ".join(w['word'] for w in chunk)
    start_t = chunk[0]['start']
    end_t   = chunk[-1]['end']
    dur     = min(end_t - start_t, safe_duration - start_t)

    if start_t >= safe_duration or dur <= 0:
        continue

    word_clips.append(
        TextClip(
            phrase,
            fontsize=CAPTION_FONT_SZ,
            color='yellow',
            font=FONT_PATH,
            stroke_color='black',
            stroke_width=2,
            method='caption',
            size=(text_width, None)
        )
        .set_start(start_t)
        .set_duration(dur)
        .set_position(('center', 'center'))
    )

print(f"Generated {len(word_clips)} caption clips.")

# ─────────────────────────────────────────────
# STEP 7 — EXPORT
# ─────────────────────────────────────────────
print("Exporting final video...")
CompositeVideoClip([video_bg] + word_clips) \
    .set_audio(audio_clip) \
    .write_videofile(
        OUTPUT_FILE,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        threads=4,          # Faster encoding
        preset="fast",      # Balance speed vs file size
        logger=None         # Suppress verbose ffmpeg output
    )
print(f"Exported: {OUTPUT_FILE}")

# ─────────────────────────────────────────────
# STEP 8 — GENERATE METADATA & UPLOAD
# ─────────────────────────────────────────────
print("Generating metadata...")
metadata_prompt = (
    f"Write a punchy 2-sentence YouTube description and 4 relevant hashtags "
    f"for a Shorts video about: {trending_topic}. "
    "Format: description first, then hashtags on a new line."
)
metadata = model.generate_content(metadata_prompt).text.strip()

print("Uploading to YouTube...")
upload_to_youtube(OUTPUT_FILE, f"{trending_topic} #shorts", metadata)
print("Done! ✅")
