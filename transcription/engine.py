"""
Transcription Engine
Supports: OpenAI Whisper, ElevenLabs Scribe v2, NVIDIA Parakeet, Real-time (Faster-Whisper)
"""

import os
import time
import tempfile
import importlib.util
from typing import Callable, Optional, List
from audio.processor import split_audio_into_chunks, get_audio_duration, cleanup_temp_files

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

MODELS = {
    "whisper": {
        "label": "OpenAI Whisper",
        "description": "Industry-standard STT by OpenAI. Reliable, multilingual.",
        "requires_api_key": True,
        "api_key_label": "OpenAI API Key",
        "supports_long_audio": True,
        "icon": "🤖",
    },
    "elevenlabs_scribe_v2": {
        "label": "ElevenLabs Scribe v2",
        "description": "High-accuracy transcription with speaker diarization.",
        "requires_api_key": True,
        "api_key_label": "ElevenLabs API Key",
        "supports_long_audio": True,
        "icon": "🎙️",
    },
    "parakeet": {
        "label": "NVIDIA Parakeet (Local)",
        "description": "NVIDIA's open-source ASR model. Runs locally, no API key needed.",
        "requires_api_key": False,
        "api_key_label": None,
        "supports_long_audio": True,
        "icon": "🦜",
    },
    "realtime": {
        "label": "Real-time (Faster-Whisper)",
        "description": "Local faster-whisper for near real-time transcription.",
        "requires_api_key": False,
        "api_key_label": None,
        "supports_long_audio": True,
        "icon": "⚡",
    },
}

SUMMARY_MODEL = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4o-mini")
DEFAULT_SUMMARY_PROMPT = """# Role
You are an expert Information Architect and Transcription Analyst. Your goal is to transform raw transcripts into high-utility, structured summaries.

# Task
Analyze the provided transcript and follow this three-step execution plan:

## Step 1: Classification & Framework Selection
First, identify the nature of the transcript (e.g., Business Meeting, Qualitative Interview, Academic Lecture, Podcast, Legal Deposition, or Workshop). Based on this classification, select the most appropriate summary framework.

## Step 2: Analysis
Review the text for key themes, speaker intent, significant decisions, and recurring patterns.

## Step 3: Structured Output
Generate the summary using the selected framework. Regardless of the type, your output MUST include:
1. **Metadata:** (Type of transcript, estimated duration, and list of speakers).
2. **The "North Star" Summary:** A 2-sentence executive summary of the core purpose.
3. **Structured Breakdown:** Use headings specific to the transcript type:
   - *For Meetings:* Decisions Made, Action Items (with owners), and Blockers.
   - *For Interviews:* Key Insights, Direct Quotes, and Participant Sentiment.
   - *For Lectures/Podcasts:* Main Thesis, Key Concepts, and Further Reading/Action.
4. **The "A-Ha" Moment:** One non-obvious insight or important subtext found in the transcript.

# Context (Transcript Data)
[PASTE YOUR TRANSCRIPT HERE]
"""


# ---------------------------------------------------------------------------
# Model readiness checks
# ---------------------------------------------------------------------------


class TranscriptionUserError(RuntimeError):
    """Expected user-facing transcription errors (auth/quota/provider restrictions)."""

def _module_exists(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def _build_elevenlabs_error_message(response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, dict):
        detail_status = (detail.get("status") or "").strip()
        detail_message = (detail.get("message") or "").strip()

        if detail_status == "detected_unusual_activity":
            return (
                "ElevenLabs blocked this request due to unusual activity on Free Tier. "
                "Disable VPN/proxy, use a paid ElevenLabs plan, or switch to another model."
            )

        if response.status_code == 401 or detail_status == "invalid_api_key":
            return "ElevenLabs authentication failed. Verify your API key and account access."

        if detail_message:
            return f"ElevenLabs error: {detail_message}"
        if detail_status:
            return f"ElevenLabs error: {detail_status}"

    if isinstance(detail, str) and detail.strip():
        return f"ElevenLabs error: {detail.strip()}"

    if response.status_code == 401:
        return "ElevenLabs authentication failed (401). Verify your API key and account access."

    return f"ElevenLabs API error {response.status_code}: {response.text[:300]}"


def check_model_requirements(model: str, api_key: str = None) -> tuple[bool, Optional[str]]:
    """Validate runtime requirements for a selected model."""
    if model == "whisper" and not api_key:
        return False, "OpenAI API key is required for Whisper."
    if model == "elevenlabs_scribe_v2" and not api_key:
        return False, "ElevenLabs API key is required for Scribe v2."

    if model == "parakeet":
        if not _module_exists("nemo.collections.asr"):
            return False, "NeMo toolkit not installed. Run: pip install nemo_toolkit['asr']"

    if model == "realtime":
        if not _module_exists("faster_whisper"):
            return False, "faster-whisper not installed. Run: pip install faster-whisper"

    return True, None


# ---------------------------------------------------------------------------
# Individual model transcription functions
# ---------------------------------------------------------------------------

def transcribe_with_whisper(audio_path: str, api_key: str, language: str = None) -> dict:
    """Transcribe using OpenAI's Whisper API."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package not installed. Run: pip install openai")

    client = OpenAI(api_key=api_key)

    with open(audio_path, "rb") as f:
        kwargs = {"model": "whisper-1", "file": f, "response_format": "verbose_json"}
        if language:
            kwargs["language"] = language
        response = client.audio.transcriptions.create(**kwargs)

    return {
        "text": response.text,
        "language": getattr(response, "language", "unknown"),
        "segments": getattr(response, "segments", []),
    }


def transcribe_with_elevenlabs(audio_path: str, api_key: str, language: str = None) -> dict:
    """Transcribe using ElevenLabs Scribe v2."""
    try:
        import requests
    except ImportError:
        raise ImportError("requests package not installed.")

    url = "https://api.elevenlabs.io/v1/speech-to-text"
    headers = {"xi-api-key": api_key}

    with open(audio_path, "rb") as f:
        files = {"file": (os.path.basename(audio_path), f, "audio/wav")}
        data = {"model_id": "scribe_v2"}
        if language:
            data["language_code"] = language

        response = requests.post(url, headers=headers, files=files, data=data)

    if response.status_code != 200:
        raise TranscriptionUserError(_build_elevenlabs_error_message(response))

    result = response.json()
    speakers = {}
    text_parts = []

    for word in result.get("words", []):
        if word.get("type") == "word":
            speaker = word.get("speaker_id", "")
            if speaker and speaker not in speakers:
                speakers[speaker] = f"Speaker {len(speakers) + 1}"
            text_parts.append(word.get("text", ""))

    return {
        "text": result.get("text", " ".join(text_parts)),
        "language": result.get("language_code", "unknown"),
        "words": result.get("words", []),
        "speakers": speakers,
    }


def transcribe_with_parakeet(audio_path: str) -> dict:
    """Transcribe using NVIDIA Parakeet (nemo toolkit)."""
    try:
        import nemo.collections.asr as nemo_asr
    except ImportError:
        raise ImportError(
            "NeMo toolkit not installed. Run:\n"
            "pip install nemo_toolkit['asr']"
        )

    model = nemo_asr.models.ASRModel.from_pretrained("nvidia/parakeet-tdt-1.1b")
    transcripts = model.transcribe([audio_path])
    text = transcripts[0] if transcripts else ""

    return {"text": text, "language": "en"}


def transcribe_with_faster_whisper(audio_path: str, model_size: str = "base") -> dict:
    """Transcribe using faster-whisper (local, real-time capable)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ImportError(
            "faster-whisper not installed. Run: pip install faster-whisper"
        )

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio_path, beam_size=5)

    text_parts = []
    segment_list = []
    for seg in segments:
        text_parts.append(seg.text.strip())
        segment_list.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip()
        })

    return {
        "text": " ".join(text_parts),
        "language": info.language,
        "segments": segment_list,
        "language_probability": info.language_probability,
    }


def _extract_openai_text(response) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text.strip()

    choices = getattr(response, "choices", None)
    if choices:
        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        content = getattr(message, "content", "") if message else ""
        if isinstance(content, str) and content.strip():
            return content.strip()

    output_items = getattr(response, "output", None)
    if output_items:
        parts = []
        for item in output_items:
            content_items = getattr(item, "content", None) or []
            for content_item in content_items:
                text_value = getattr(content_item, "text", None)
                if text_value:
                    parts.append(text_value)
        if parts:
            return "\n".join(parts).strip()

    return ""


def summarize_transcript_with_openai(
    transcript: str,
    api_key: str,
    prompt_template: str = DEFAULT_SUMMARY_PROMPT,
    model: str = SUMMARY_MODEL,
) -> dict:
    if not api_key:
        raise TranscriptionUserError("OpenAI API key is required to generate a summary.")
    if not transcript or not transcript.strip():
        raise TranscriptionUserError("Transcript is empty. Nothing to summarize.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("openai package not installed. Run: pip install openai") from exc

    client = OpenAI(api_key=api_key)
    prompt = prompt_template.replace("[PASTE YOUR TRANSCRIPT HERE]", transcript.strip())

    response = None
    if hasattr(client, "responses"):
        try:
            response = client.responses.create(
                model=model,
                reasoning={"effort": "low"},
                input=prompt,
            )
        except Exception:
            response = client.responses.create(
                model=model,
                input=prompt,
            )
    else:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                reasoning_effort="low",
            )
        except Exception:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )

    summary_text = _extract_openai_text(response)
    if not summary_text:
        raise RuntimeError("OpenAI returned an empty summary.")

    return {
        "summary": summary_text,
        "model_used": model,
    }


# ---------------------------------------------------------------------------
# Main transcription orchestrator
# ---------------------------------------------------------------------------

def transcribe(
    audio_path: str,
    model: str,
    api_key: str = None,
    language: str = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> dict:
    """
    Main entry point. Handles chunking for long audio, then dispatches
    to the appropriate model function.

    Returns dict with: text, language, duration, word_count, model_used, chunks
    """
    if progress_callback:
        progress_callback(5, "Analyzing audio file...")

    is_ready, readiness_error = check_model_requirements(model, api_key=api_key)
    if not is_ready:
        raise RuntimeError(readiness_error)

    duration = get_audio_duration(audio_path)
    temp_dir = tempfile.mkdtemp()
    chunks = split_audio_into_chunks(audio_path, output_dir=temp_dir)
    is_chunked = len(chunks) > 1

    all_texts = []
    total_chunks = len(chunks)
    detected_language = language or "unknown"

    try:
        for i, chunk_path in enumerate(chunks):
            chunk_label = f"chunk {i + 1}/{total_chunks}" if is_chunked else "audio"
            if progress_callback:
                pct = 10 + int((i / total_chunks) * 80)
                progress_callback(pct, f"Transcribing {chunk_label}...")

            try:
                if model == "whisper":
                    result = transcribe_with_whisper(chunk_path, api_key, language)
                elif model == "elevenlabs_scribe_v2":
                    result = transcribe_with_elevenlabs(chunk_path, api_key, language)
                elif model == "parakeet":
                    result = transcribe_with_parakeet(chunk_path)
                elif model == "realtime":
                    result = transcribe_with_faster_whisper(chunk_path)
                else:
                    raise ValueError(f"Unknown model: {model}")
            except Exception as e:
                if isinstance(e, TranscriptionUserError):
                    raise TranscriptionUserError(f"Transcription failed for {chunk_label}: {e}") from e
                raise RuntimeError(f"Transcription failed for {chunk_label}: {e}") from e

            all_texts.append(result.get("text", ""))
            detected_language = result.get("language", detected_language)
    finally:
        if is_chunked:
            for c in chunks:
                cleanup_temp_files(c)

    if progress_callback:
        progress_callback(95, "Finalizing transcript...")

    full_text = "\n\n".join(filter(None, all_texts))
    word_count = len(full_text.split())

    if progress_callback:
        progress_callback(100, "Done!")

    return {
        "text": full_text,
        "language": detected_language,
        "duration": duration,
        "word_count": word_count,
        "model_used": model,
        "chunks_processed": total_chunks,
    }
