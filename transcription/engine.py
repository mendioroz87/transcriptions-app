"""
Transcription Engine
Supports: OpenAI Whisper, ElevenLabs Scribe v2, NVIDIA Parakeet, Real-time (Faster-Whisper)
"""

import os
import time
import tempfile
import importlib.util
import re
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

SUMMARY_MODEL = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-5-nano")

SUMMARY_ROLE_INSTRUCTIONS = (
    "You are an expert Information Architect and Transcription Analyst. "
    "Your goal is to transform raw transcripts into high-utility, structured, and easy-to-read summaries."
)

SUMMARY_TASK_INSTRUCTIONS = """Analyze the provided transcript and generate a comprehensive, well-structured summary. Review the text for key themes, main topics discussed, and significant points.

Your output MUST include:
1. **Metadata:** A brief overview of the transcript (e.g., general topic, identifiable speakers).
2. **Executive Summary:** A concise 2-3 sentence overview of the core purpose and main takeaways.
3. **Key Points & Highlights:** A bulleted breakdown of the most important information, decisions, or insights discussed.
4. **Conclusion / Next Steps:** Any final thoughts, conclusions, or action items mentioned in the transcript."""

SUMMARY_OUTPUT_CONSTRAINTS = """- The output language MUST be exactly: {transcript_language}
- Make the summary accurate and concrete, avoiding fluff or generic statements."""

SUMMARY_METADATA_CONTEXT_TEMPLATE = "Language from transcription metadata: {transcript_language}"

SUMMARY_SYSTEM_PROMPT_TEMPLATE = """{role_instructions}

Output format rules:
- Return valid Markdown only.
- The response language MUST be exactly: {transcript_language}
- Start directly with the first section header, with no preface or follow-up comments."""

SUMMARY_USER_PROMPT_TEMPLATE = """Generate the final structured summary using these instructions:

<summary_instructions>
{summary_instructions}
</summary_instructions>

<transcript_metadata>
{metadata_context}
</transcript_metadata>

<transcription>
{transcription_text}
</transcription>"""

SUMMARY_SECTION_START_MARKERS = (
    "metadatos",
    "metadata",
    "resumen ejecutivo",
    "north star summary",
    'the "north star" summary',
    "executive summary",
)

DEFAULT_SUMMARY_PROMPT = """# Role
{role_instructions}

# Task
{task_instructions}

# Output Constraints
{output_constraints}

# Context (Transcript Metadata)
{metadata_context}

# Context (Transcript Data)
{transcription_text}
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

def transcribe_with_whisper(audio_path: str, api_key: str, language: str = None, prompt: str = None) -> dict:
    """Transcribe using OpenAI's Whisper API."""
    try:
        from openai import OpenAI, OpenAIError
    except ImportError:
        raise ImportError("openai package not installed. Run: pip install openai")

    client = OpenAI(api_key=api_key)

    try:
        with open(audio_path, "rb") as f:
            kwargs = {
                "model": "whisper-1", 
                "file": f, 
                "response_format": "verbose_json",
                "timestamp_granularities": ["segment", "word"]
            }
            if language:
                kwargs["language"] = language
            
            if prompt:
                # Whisper prompts are limited to ~224 tokens. Using the last ~1000 chars is a safe estimate.
                kwargs["prompt"] = prompt[-1000:]

            response = client.audio.transcriptions.create(**kwargs)

        return {
            "text": response.text,
            "language": getattr(response, "language", "unknown"),
            "segments": getattr(response, "segments", []),
            "words": getattr(response, "words", []),
        }
    except OpenAIError as e:
        raise TranscriptionUserError(f"OpenAI API Error: {str(e)}")


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


def _strip_summary_code_fence(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned.startswith("```"):
        return cleaned

    lines = cleaned.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return cleaned


def _normalize_summary_heading(line: str) -> str:
    normalized = (line or "").strip().lower()
    normalized = re.sub(r"^[#>\-\*\s`_]+", "", normalized)
    normalized = re.sub(r"[*`_:\-]+$", "", normalized)
    normalized = normalized.strip()
    return normalized


def _trim_reasoning_preface(summary_text: str) -> str:
    lines = (summary_text or "").splitlines()
    if not lines:
        return ""

    start_index = None
    for idx, line in enumerate(lines):
        normalized = _normalize_summary_heading(line)
        if any(normalized.startswith(marker) for marker in SUMMARY_SECTION_START_MARKERS):
            start_index = idx
            break

    if start_index is not None and start_index > 0:
        return "\n".join(lines[start_index:]).strip()
    return "\n".join(lines).strip()


def _trim_trailing_follow_up(summary_text: str) -> str:
    lines = (summary_text or "").splitlines()

    def is_follow_up_line(value: str) -> bool:
        normalized = value.strip().lower()
        if not normalized:
            return False
        if normalized in {"---", "***", "___"}:
            return True
        if "?" in normalized or normalized.startswith("¿"):
            return True
        follow_up_starts = (
            "would you like",
            "do you want",
            "let me know",
            "if you want",
            "si quieres",
            "si deseas",
            "puedo ayudarte",
            "avísame",
            "hay alguna instrucción adicional",
            "alguna instrucción adicional",
        )
        return normalized.startswith(follow_up_starts)

    while lines and not lines[-1].strip():
        lines.pop()

    while lines and is_follow_up_line(lines[-1]):
        lines.pop()
        while lines and not lines[-1].strip():
            lines.pop()

    return "\n".join(lines).strip()


def _sanitize_summary_output(summary_text: str) -> str:
    cleaned = _strip_summary_code_fence(summary_text)
    cleaned = _trim_reasoning_preface(cleaned)
    cleaned = _trim_trailing_follow_up(cleaned)
    return cleaned.strip()


class _SafePromptVarMap(dict):
    """Leave unknown template variables untouched instead of raising KeyError."""

    def __missing__(self, key):
        return "{" + key + "}"


def _sanitize_transcription_text(transcription_text: str) -> str:
    sanitized = (transcription_text or "").strip().replace('"""', "'''")
    sanitized = sanitized.replace("<transcription>", "").replace("</transcription>", "")
    return sanitized.replace("<transcripcion>", "").replace("</transcripcion>", "")


def _build_summary_prompt_payload(
    summary_instructions_template: str,
    *,
    transcript_language: str,
    transcription_text: str,
    role_instructions: str = SUMMARY_ROLE_INSTRUCTIONS,
    task_instructions: str = SUMMARY_TASK_INSTRUCTIONS,
    output_constraints_template: str = SUMMARY_OUTPUT_CONSTRAINTS,
    metadata_context_template: str = SUMMARY_METADATA_CONTEXT_TEMPLATE,
    system_prompt_template: str = SUMMARY_SYSTEM_PROMPT_TEMPLATE,
    user_prompt_template: str = SUMMARY_USER_PROMPT_TEMPLATE,
) -> dict:
    language_value = (transcript_language or "unknown").strip() or "unknown"
    base_variables = _SafePromptVarMap(
        {
            "transcript_language": language_value,
            "role_instructions": role_instructions,
            "task_instructions": task_instructions,
            "output_constraints": output_constraints_template.format(
                transcript_language=language_value
            ),
            "metadata_context": metadata_context_template.format(
                transcript_language=language_value
            ),
            "transcription_text": _sanitize_transcription_text(transcription_text),
        }
    )

    template = summary_instructions_template or DEFAULT_SUMMARY_PROMPT
    summary_instructions = template.format_map(base_variables)
    summary_instructions = summary_instructions.replace(
        "[TRANSCRIPT_LANGUAGE]", base_variables["transcript_language"]
    )
    summary_instructions = summary_instructions.replace(
        "[PASTE YOUR TRANSCRIPT HERE]", base_variables["transcription_text"]
    )

    prompt_variables = _SafePromptVarMap(
        {
            **base_variables,
            "summary_instructions": summary_instructions,
        }
    )
    system_prompt = system_prompt_template.format_map(prompt_variables)
    user_prompt = user_prompt_template.format_map(prompt_variables)
    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "transcript_language": language_value,
        "transcription_text": prompt_variables["transcription_text"],
    }


def summarize_transcript_with_openai(
    transcript: str,
    api_key: str,
    transcript_language: str = "unknown",
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
    prompt_payload = _build_summary_prompt_payload(
        prompt_template,
        transcript_language=transcript_language,
        transcription_text=transcript,
    )
    
    system_prompt = prompt_payload["system_prompt"]
    user_prompt = prompt_payload["user_prompt"]

    # For reasoning models (o1, o3-mini, gpt-5-nano), OpenAI recommends using the 'developer' 
    # role instead of 'system'. They also do not support the 'temperature' parameter.
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "developer", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            reasoning_effort="low",
        )
    except Exception as e:
        # Fallback if the model doesn't support 'developer' role or 'reasoning_effort'
        # and requires standard chat completion parameters
        if "developer" in str(e).lower() or "reasoning_effort" in str(e).lower():
            response = client.chat.completions.create(
                model=model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        else:
            raise e

    summary_text = _sanitize_summary_output(_extract_openai_text(response))
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
    accumulated_context = ""

    try:
        for i, chunk_path in enumerate(chunks):
            chunk_label = f"chunk {i + 1}/{total_chunks}" if is_chunked else "audio"
            if progress_callback:
                pct = 10 + int((i / total_chunks) * 80)
                progress_callback(pct, f"Transcribing {chunk_label}...")

            try:
                if model == "whisper":
                    result = transcribe_with_whisper(
                        chunk_path, 
                        api_key, 
                        language, 
                        prompt=accumulated_context
                    )
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

            chunk_text = result.get("text", "")
            all_texts.append(chunk_text)
            detected_language = result.get("language", detected_language)
            
            if chunk_text:
                accumulated_context += " " + chunk_text

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
