#!/usr/bin/env python3
import collections
import os
import queue
import re
import shutil
import sys
import subprocess
import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHANNELS = 1
MODEL_NAME = "tiny.en"   # or a local CTranslate2 model directory path
TRANSCRIBE_LANGUAGE = "en"
COMPUTE_TYPE = "int8"    # good for CPU
AUTO_ENTER = False       # set True if you want it to press Enter after typing
LOCAL_FILES_ONLY = False # set True to prevent downloads and require a local model
TYPE_BACKEND = "auto"    # "auto", "xdotool", or "ydotool"
BLOCK_DURATION_SEC = 0.1
PRE_SPEECH_BUFFER_SEC = 0.4
SILENCE_DURATION_SEC = 0.8
MAX_RECORDING_SEC = 20
VOICE_THRESHOLD = 700
MIN_SPEECH_BLOCKS = 2
QUEUE_POLL_TIMEOUT_SEC = 0.1
BEAM_SIZE = 1
BEST_OF = 1
WORD_TIMESTAMPS = False
CONDITION_ON_PREVIOUS_TEXT = False
ENTER_PATTERN = re.compile(r"\s*\benter\b\s*", re.IGNORECASE)

def audio_level(block) -> int:
    return int(np.abs(block).mean())

def queue_audio_segment(captured_blocks, utterance_q: queue.Queue):
    if not captured_blocks:
        return

    audio = np.concatenate(captured_blocks, axis=0)
    if audio.size == 0:
        return

    utterance_q.put(audio)

def listen_loop(sample_rate: int, utterance_q: queue.Queue):
    blocksize = int(sample_rate * BLOCK_DURATION_SEC)
    pre_speech_blocks = max(1, int(PRE_SPEECH_BUFFER_SEC / BLOCK_DURATION_SEC))
    silence_limit_blocks = max(1, int(SILENCE_DURATION_SEC / BLOCK_DURATION_SEC))
    max_blocks = max(1, int(MAX_RECORDING_SEC / BLOCK_DURATION_SEC))

    audio_q = queue.Queue()
    pre_buffer = collections.deque(maxlen=pre_speech_blocks)
    captured_blocks = []
    speech_blocks = 0
    silence_blocks = 0
    started = False

    def callback(indata, frames, time_info, status):
        if status:
            print(f"Audio status: {status}", file=sys.stderr)
        audio_q.put(indata.copy())

    print("Listening...")
    with sd.InputStream(
        samplerate=sample_rate,
        channels=CHANNELS,
        dtype="int16",
        blocksize=blocksize,
        callback=callback,
    ):
        while True:
            block = audio_q.get()
            level = audio_level(block)

            if not started:
                pre_buffer.append(block)
                if level >= VOICE_THRESHOLD:
                    speech_blocks += 1
                    if speech_blocks >= MIN_SPEECH_BLOCKS:
                        started = True
                        captured_blocks.extend(pre_buffer)
                        print("Speech detected.")
                else:
                    speech_blocks = 0
                continue

            captured_blocks.append(block)

            if level >= VOICE_THRESHOLD:
                silence_blocks = 0
            else:
                silence_blocks += 1

            if silence_blocks >= silence_limit_blocks or len(captured_blocks) >= max_blocks:
                queue_audio_segment(captured_blocks, utterance_q)
                pre_buffer.clear()
                captured_blocks = []
                speech_blocks = 0
                silence_blocks = 0
                started = False

def load_model():
    print("Loading model...")
    from faster_whisper import WhisperModel

    try:
        return WhisperModel(
            MODEL_NAME,
            compute_type=COMPUTE_TYPE,
            local_files_only=LOCAL_FILES_ONLY,
        )
    except Exception as exc:
        if exc.__class__.__name__ == "LocalEntryNotFoundError":
            raise RuntimeError(
                "Whisper model not found locally and download failed. "
                "If this is the first run, connect to the internet so "
                f"faster-whisper can download '{MODEL_NAME}', or set MODEL_NAME "
                "to a local CTranslate2 model directory and enable "
                "LOCAL_FILES_ONLY."
            ) from exc
        raise

def detect_typing_backend() -> str:
    backend = TYPE_BACKEND.lower()
    if backend == "auto":
        session_type = (os.environ.get("XDG_SESSION_TYPE") or "").lower()
        if session_type == "wayland" and shutil.which("ydotool") is not None:
            return "ydotool"
        if shutil.which("xdotool") is not None:
            return "xdotool"
        if shutil.which("ydotool") is not None:
            return "ydotool"
        raise RuntimeError("Neither xdotool nor ydotool is available.")

    if backend == "xdotool":
        if shutil.which("xdotool") is None:
            raise RuntimeError("TYPE_BACKEND is set to xdotool, but xdotool is not installed.")
        return "xdotool"

    if backend == "ydotool":
        if shutil.which("ydotool") is None:
            raise RuntimeError("TYPE_BACKEND is set to ydotool, but ydotool is not installed.")
        return "ydotool"

    raise RuntimeError(f"Unsupported TYPE_BACKEND: {TYPE_BACKEND}")

def run_tool(command: list[str]):
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        if command[0] == "ydotool" and (
            "failed to open uinput device" in details or
            "backend unavailable" in details
        ):
            raise RuntimeError(
                "ydotool is installed but cannot access /dev/uinput. "
                "Fix /dev/uinput permissions for your user, or use an X11 session."
            ) from exc
        raise RuntimeError(details or f"{command[0]} failed with exit code {exc.returncode}.") from exc

def press_enter(backend: str):
    if backend == "xdotool":
        run_tool(["xdotool", "key", "Return"])
        return

    run_tool(["ydotool", "key", "28:1", "28:0"])

def type_text(text: str, backend: str):
    text = text.strip()
    if not text:
        print("No text recognized.")
        return

    print(f"Recognized: {text}")
    parts = ENTER_PATTERN.split(text)
    enter_count = max(0, len(parts) - 1)

    for index, part in enumerate(parts):
        chunk = part.strip()
        if chunk:
            if backend == "xdotool":
                run_tool(["xdotool", "type", "--delay", "1", chunk])
            else:
                run_tool(["ydotool", "type", chunk])

        if index < enter_count:
            press_enter(backend)

    if AUTO_ENTER:
        press_enter(backend)

def transcribe_audio(model, audio) -> str:
    audio_float32 = audio.astype(np.float32).reshape(-1) / 32768.0
    segments, info = model.transcribe(
        audio_float32,
        language=TRANSCRIBE_LANGUAGE,
        beam_size=BEAM_SIZE,
        best_of=BEST_OF,
        word_timestamps=WORD_TIMESTAMPS,
        condition_on_previous_text=CONDITION_ON_PREVIOUS_TEXT,
        vad_filter=False,
    )
    return " ".join(segment.text for segment in segments).strip()

def transcription_worker(utterance_q: queue.Queue, backend: str, stop_event: threading.Event):
    model = load_model()

    while not stop_event.is_set() or not utterance_q.empty():
        try:
            audio = utterance_q.get(timeout=QUEUE_POLL_TIMEOUT_SEC)
        except queue.Empty:
            continue

        try:
            text = transcribe_audio(model, audio)
            type_text(text, backend)
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
        finally:
            utterance_q.task_done()

def main():
    backend = detect_typing_backend()
    utterance_q = queue.Queue()
    stop_event = threading.Event()
    worker = threading.Thread(
        target=transcription_worker,
        args=(utterance_q, backend, stop_event),
        daemon=True,
    )
    worker.start()

    try:
        listen_loop(SAMPLE_RATE, utterance_q)
    except KeyboardInterrupt:
        print("\nExiting.")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
    finally:
        stop_event.set()
        worker.join()
        sys.exit(0)

if __name__ == "__main__":
    main()
