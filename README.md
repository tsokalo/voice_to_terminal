# Voice To Terminal

`voice_to_terminal.py` listens continuously, detects speech, transcribes it with `faster-whisper`, and types the recognized text into the currently focused window.

## Features

- Starts listening immediately
- Detects speech automatically instead of recording fixed-length clips
- Keeps listening while previous speech is being transcribed
- Types into the active window using:
  - `ydotool` on Wayland
  - `xdotool` on X11
- Spoken `Enter` becomes a real Return key press

## Requirements

- Ubuntu or similar Linux system
- Python 3.10+
- Microphone access
- One of:
  - Wayland with `ydotool` and `/dev/uinput` access
  - X11 with `xdotool`

## Setup

Run:

```bash
cd ~/workspace/voice_to_terminal
./setup.sh
```

The setup script:

- creates `.venv`
- installs Python dependencies
- installs system packages with `apt`
- configures `/dev/uinput` access for Wayland input injection

If `setup.sh` adds your user to the `input` group, log out and log back in before testing on Wayland.

## Run

```bash
cd ~/workspace/voice_to_terminal
./run.sh
```

`run.sh` activates the local virtual environment and starts `voice_to_terminal.py`.

## Usage

- Focus the terminal or app where text should be typed
- Start speaking
- Pause briefly to end the utterance
- Say `Enter` when you want a real line break / Return key

Example spoken input:

```text
git status Enter
```

## Configuration

The main tuning values are at the top of [voice_to_terminal.py](/home/ievgenii/workspace/voice_to_terminal/voice_to_terminal.py):

- `MODEL_NAME`
- `VOICE_THRESHOLD`
- `SILENCE_DURATION_SEC`
- `PRE_SPEECH_BUFFER_SEC`
- `MAX_RECORDING_SEC`

Notes:

- `tiny` is faster and less accurate
- `base` is slower and usually more accurate
- `tiny.en` can be a good choice for English-only speech

## Troubleshooting

If typing works poorly on Wayland:

```bash
id
ls -l /dev/uinput
ydotool type test
```

Expected:

- `id` includes `input`
- `/dev/uinput` is group `input`
- `ydotool type test` types into the active window

If transcription fails on first run, the model may need to be downloaded first or `MODEL_NAME` may need to point to a local model directory.
