# 🎙️ MLabs Transcription

> A powerful, full-featured audio transcription application built with Streamlit.
> Supports multiple AI models, any audio format, and hours-long recordings.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-red)
![FFmpeg](https://img.shields.io/badge/FFmpeg-required-orange)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Features

| Feature | Details |
|---|---|
| 🔐 **User Accounts** | Register, log in, manage your profile |
| 📁 **Projects** | Organize transcriptions into separate projects |
| 🤖 **Multiple AI Models** | Whisper, ElevenLabs Scribe v2, NVIDIA Parakeet, Faster-Whisper |
| 🔊 **Any Audio Format** | MP3, WAV, OPUS (WhatsApp), M4A, FLAC, WebM, OGG, AMR, and more via FFmpeg |
| ⏱️ **Long Audio Support** | Automatically chunks 1–5 hour recordings into 10-min segments |
| 🔑 **Your API Keys** | Use your own keys per project or globally |
| 📤 **Rich Export** | TXT, JSON, Markdown, DOCX, SRT, VTT, CSV |
| 🌐 **Multilingual** | Auto-detect or specify language |

---

## 🚀 Quick Start

### 1. Prerequisites

**Install FFmpeg** (required for audio conversion):

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html and add to PATH
```

### 2. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/transcription-by-mlabs.git
cd transcription-by-mlabs

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate      # Linux/Mac
# venv\Scripts\activate       # Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Run

```bash
python -m streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## 🤖 Supported Transcription Models

### 1. 🤖 OpenAI Whisper (`whisper`)
- **API Key required:** Yes (OpenAI)
- **Pricing:** ~$0.006/minute
- **Best for:** Accurate multilingual transcription, well-tested
- Get your key at: https://platform.openai.com/api-keys

### 2. 🎙️ ElevenLabs Scribe v2 (`elevenlabs_scribe_v2`)
- **API Key required:** Yes (ElevenLabs)
- **Pricing:** See ElevenLabs pricing
- **Best for:** Speaker diarization, high accuracy
- Get your key at: https://elevenlabs.io

### 3. 🦜 NVIDIA Parakeet (`parakeet`)
- **API Key required:** No — runs fully locally
- **Requirements:** `pip install nemo_toolkit['asr']` (large download)
- **Best for:** Privacy-sensitive content, offline use

### 4. ⚡ Faster-Whisper (`realtime`)
- **API Key required:** No — runs locally
- **Requirements:** `pip install faster-whisper`
- **Best for:** Fast local transcription, low latency

---

## 📂 Project Structure

```
transcription-by-mlabs/
├── app.py                    # Main Streamlit entry point / Dashboard
├── requirements.txt
├── .streamlit/
│   └── config.toml           # Dark theme config
│
├── pages/
│   ├── projects.py           # Project management
│   ├── transcribe.py         # Upload & transcribe audio
│   ├── history.py            # View & export transcriptions
│   └── settings.py           # API keys & account settings
│
├── database/
│   └── db.py                 # SQLite ORM (users, projects, transcriptions)
│
├── audio/
│   └── processor.py          # FFmpeg audio conversion & chunking
│
├── transcription/
│   └── engine.py             # Model dispatcher (Whisper, ElevenLabs, etc.)
│
├── exports/
│   └── exporter.py           # TXT, JSON, DOCX, SRT, VTT, CSV exporters
│
└── utils/
    ├── auth_ui.py            # Login/register Streamlit components
    └── components.py         # Shared UI helpers
```

---

## 🔊 Audio Format Support

MLabs uses **FFmpeg** to handle virtually any audio format:

| Format | Extension | Source |
|--------|-----------|--------|
| OPUS | `.opus` | WhatsApp, Telegram voice messages |
| MP3 | `.mp3` | Standard compressed audio |
| WAV | `.wav` | Uncompressed audio |
| M4A | `.m4a` | Apple/iPhone recordings |
| AAC | `.aac` | Compressed audio |
| FLAC | `.flac` | Lossless audio |
| OGG | `.ogg` | Open source format |
| WebM | `.webm` | Browser recordings |
| AMR | `.amr` | Old mobile recordings |
| MP4 | `.mp4` | Video (audio extracted) |

All audio is converted to **16kHz mono WAV** before transcription — the optimal format for speech recognition models.

---

## ⏱️ Long Audio Handling

Files longer than **10 minutes** are automatically split into chunks:

1. FFmpeg splits audio into 10-minute segments
2. Each chunk is transcribed independently
3. Results are joined with paragraph breaks
4. Temporary chunk files are cleaned up

This approach handles recordings of **1–5+ hours** reliably.

---

## 📤 Export Formats

From the History page, each transcription can be exported as:

- **TXT** — Plain text transcript
- **JSON** — Full metadata + transcript
- **Markdown** — Formatted with metadata header
- **DOCX** — Word document with metadata table
- **CSV** — Bulk export of multiple transcriptions

---

## ☁️ Deploy to Streamlit Cloud

1. Push to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repo → set main file: `app.py`
4. Add **secrets** in Streamlit Cloud settings if needed
5. Deploy!

> ⚠️ Note: FFmpeg must be available on the server. On Streamlit Cloud, add a `packages.txt`:
> ```
> ffmpeg
> ```

### Auth and Email Secrets

To enable Google sign-in plus Gmail-based invitation/reset emails, add these secrets in Streamlit Cloud:

```toml
APP_BASE_URL = "https://your-app.streamlit.app"
GMAIL_USER = "your-account@gmail.com"
GMAIL_APP_PASSWORD = "your-gmail-app-password"

[auth]
redirect_uri = "https://your-app.streamlit.app/oauth2callback"
cookie_secret = "replace-with-a-long-random-secret"

[auth.google]
client_id = "your-google-oauth-client-id"
client_secret = "your-google-oauth-client-secret"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

For local development, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in the real values.
Use a Gmail App Password (not your normal Gmail login password).
Google sign-in is restricted to `@gmail.com` accounts in this app.
If an app password or OAuth secret is ever shared, rotate it immediately.

---

## 🔒 Security Notes

- Passwords are hashed with SHA-256 before storage
- Google sign-in is validated against Gmail-only OIDC claims before a local session is created
- API keys are stored locally in SQLite (never sent to third parties except the chosen transcription API)
- For production, consider using environment variables or Streamlit secrets for sensitive config

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

## 🙋 By M Labs

Built with ❤️ using [Streamlit](https://streamlit.io), [FFmpeg](https://ffmpeg.org), and the best AI transcription APIs available.
