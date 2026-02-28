import os
import subprocess
import tempfile
import math
from pathlib import Path
from typing import List, Tuple

SUPPORTED_EXTENSIONS = {
    ".opus", ".ogg", ".wav", ".mp3", ".m4a", ".aac",
    ".flac", ".wma", ".webm", ".mp4", ".avi", ".mkv",
    ".amr", ".3gp", ".caf", ".aiff", ".aif"
}

CHUNK_DURATION_SECONDS = 10 * 60  # 10 minutes per chunk for long files


def check_ffmpeg() -> bool:
    """Check if FFmpeg is installed."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_audio_duration(filepath: str) -> float:
    """Get duration of audio file in seconds using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", filepath],
            capture_output=True, text=True, check=True
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def get_audio_info(filepath: str) -> dict:
    """Get detailed audio info using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration,size,bit_rate:stream=codec_name,sample_rate,channels",
             "-of", "json", filepath],
            capture_output=True, text=True, check=True
        )
        import json
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [{}])
        return {
            "duration": float(fmt.get("duration", 0)),
            "size_mb": round(int(fmt.get("size", 0)) / (1024 * 1024), 2),
            "bit_rate": int(fmt.get("bit_rate", 0)),
            "codec": streams[0].get("codec_name", "unknown"),
            "sample_rate": streams[0].get("sample_rate", "unknown"),
            "channels": streams[0].get("channels", 1),
        }
    except Exception as e:
        return {"duration": 0, "size_mb": 0, "error": str(e)}


def convert_to_wav(input_path: str, output_dir: str = None) -> str:
    """Convert any supported audio format to WAV (16kHz, mono) for transcription."""
    input_path = str(input_path)
    stem = Path(input_path).stem
    if output_dir is None:
        output_dir = tempfile.gettempdir()

    output_path = os.path.join(output_dir, f"{stem}_converted.wav")

    cmd = [
        "ffmpeg", "-y",           # overwrite if exists
        "-i", input_path,         # input file
        "-ar", "16000",           # 16kHz sample rate (optimal for speech models)
        "-ac", "1",               # mono channel
        "-c:a", "pcm_s16le",      # PCM 16-bit signed little-endian
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg conversion failed:\n{result.stderr}")

    return output_path


def split_audio_into_chunks(filepath: str, chunk_duration: int = CHUNK_DURATION_SECONDS,
                             output_dir: str = None) -> List[str]:
    """Split a long audio file into chunks for processing."""
    if output_dir is None:
        output_dir = tempfile.mkdtemp()

    duration = get_audio_duration(filepath)
    if duration <= chunk_duration:
        return [filepath]  # No splitting needed

    stem = Path(filepath).stem
    num_chunks = math.ceil(duration / chunk_duration)
    chunk_paths = []

    for i in range(num_chunks):
        start = i * chunk_duration
        chunk_path = os.path.join(output_dir, f"{stem}_chunk_{i:03d}.wav")

        cmd = [
            "ffmpeg", "-y",
            "-i", filepath,
            "-ss", str(start),
            "-t", str(chunk_duration),
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            chunk_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg chunk {i} failed:\n{result.stderr}")

        chunk_paths.append(chunk_path)

    return chunk_paths


def process_uploaded_file(uploaded_file, output_dir: str = None) -> Tuple[str, dict]:
    """
    Save uploaded Streamlit file, convert to WAV, and return path + audio info.
    Returns: (converted_wav_path, audio_info_dict)
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp()

    # Save the raw uploaded file
    ext = Path(uploaded_file.name).suffix.lower()
    raw_path = os.path.join(output_dir, f"raw_input{ext}")
    with open(raw_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    # Get info before conversion
    info = get_audio_info(raw_path)

    # Convert to WAV
    wav_path = convert_to_wav(raw_path, output_dir)

    return wav_path, info


def cleanup_temp_files(*paths):
    """Remove temporary files safely."""
    for path in paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
