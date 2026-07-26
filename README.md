# YouTube Shorts Auto-Agent

A fully automated, zero-touch YouTube Shorts channel. Every day at 19:00 UTC a GitHub Action wakes up, invents a topic, writes a script, records a voiceover, edits a captioned 9:16 video, and publishes it to YouTube — no human in the loop.

## How it works

`agent.py` runs the whole pipeline end-to-end:

1. **Topic** — Gemini 2.5 Flash (via Vertex AI) picks one scroll-stopping topic (real-world only: nature, history, ocean, space, crime, ancient civilizations…).
2. **Script** — Gemini writes a 140–155 word script following a strict viral arc: Hook → Pull → Escalation → Reframe → Exit line.
3. **Voiceover** — Google Cloud Text-to-Speech (`en-US-Neural2-J`, 1.2× speed) renders the script; audio is trimmed to a max of 58 s and forced to mono.
4. **Caption timing** — Google Cloud Speech-to-Text transcribes the voiceover with word-level timestamps.
5. **Video edit** — MoviePy picks a random `bg_part*.mp4` background chunk, grabs a random 58 s window, center-crops it to 9:16, and burns in yellow 3-word caption chunks synced to the voice.
6. **Publish** — Gemini writes the title, description and hashtags, then `uploader.py` uploads the finished `final_viral_short.mp4` to YouTube (public) via the YouTube Data API.

## Repo layout

| File | Purpose |
|---|---|
| `agent.py` | The entire generation + edit pipeline |
| `uploader.py` | YouTube Data API upload (OAuth, `token.pickle`) |
| `split_video.py` | One-time helper: splits a long `background_loop.mp4` into 90 s `bg_part*.mp4` chunks that stay under GitHub's 100 MB file limit |
| `bg_part1..12.mp4` | Pre-split background footage the agent samples from |
| `.github/workflows/main.yml` | Daily scheduled runner (19:00 UTC + manual dispatch) |

## Setup

### Google Cloud
1. Create a project (the code uses `shorts-auto-agent`, region `us-central1`) and enable **Vertex AI**, **Cloud Text-to-Speech**, and **Cloud Speech-to-Text**.
2. Create a service account with access to those APIs and download its JSON key.

### YouTube OAuth (one-time, locally)
1. In Google Cloud Console create an **OAuth client (Desktop)** for the YouTube Data API v3 and save it as `client_secrets.json`.
2. Run the agent once locally — `uploader.py` opens a browser login and saves `token.pickle` for all future headless runs.

### GitHub Actions secrets
| Secret | Contents |
|---|---|
| `GOOGLE_CREDENTIALS_JSON` | The service-account JSON key (raw) |
| `CLIENT_SECRETS_JSON` | The OAuth client JSON (raw) |
| `TOKEN_PICKLE_BASE64` | `base64 < token.pickle` |

The workflow reconstructs all three files at runtime, installs ffmpeg + ImageMagick (with the text-policy fix), and runs `python agent.py`.

## Run locally

```bash
pip install -r requirements.txt
export GOOGLE_APPLICATION_CREDENTIALS=google_credentials.json
python agent.py
```

macOS is supported out of the box (Homebrew ImageMagick + Helvetica); Linux uses DejaVu Sans Bold.

## Swapping the background footage

Drop any long landscape video in as `background_loop.mp4`, run `python split_video.py`, commit the generated `bg_part*.mp4` chunks, and delete the original. Chunks shorter than 60 s are skipped so the agent always has room to cut a 58 s clip.

## Notes

- Videos are capped at 58 s to stay safely inside the Shorts limit.
- Uploads are `public` by default — change `privacyStatus` in `uploader.py` to `private` while testing.
- Topics deliberately exclude AI, tech, politics, medicine and religion.
