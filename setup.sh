#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
UINPUT_RULE_PATH="/etc/udev/rules.d/99-uinput.rules"
UINPUT_RULE='KERNEL=="uinput", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"'

echo "Installing system packages..."
sudo apt-get update
sudo apt-get install -y \
  ffmpeg \
  libportaudio2 \
  portaudio19-dev \
  python3-venv \
  xdotool \
  ydotool

echo "Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"

echo "Installing Python packages..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install \
  faster-whisper \
  numpy \
  sounddevice

if ! getent group input >/dev/null; then
  echo "Creating input group..."
  sudo groupadd input
fi

echo "Adding $USER to input group..."
sudo usermod -aG input "$USER"

echo "Installing uinput udev rule..."
printf '%s\n' "$UINPUT_RULE" | sudo tee "$UINPUT_RULE_PATH" >/dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger --name-match=uinput || true

if [[ -e /dev/uinput ]]; then
  echo "Fixing /dev/uinput ownership..."
  sudo chgrp input /dev/uinput || true
  sudo chmod 660 /dev/uinput || true
fi

echo
echo "Setup complete."
echo
echo "If you are using Wayland, log out and log back in so the 'input' group is active."
echo "Then run:"
echo "  cd \"$PROJECT_DIR\""
echo "  .venv/bin/python voice_to_terminal.py"
