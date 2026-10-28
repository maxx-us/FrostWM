#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.local/share/frostwm" "$HOME/.local/bin" "$HOME/.config/frostwm" "$HOME/.config/systemd/user" "$HOME/.config/waybar/scripts"
install -m 755 "$ROOT/frostwm.py" "$HOME/.local/share/frostwm/frostwm.py"
install -m 644 "$ROOT/config.example.json" "$HOME/.local/share/frostwm/config.example.json"
if [[ ! -e "$HOME/.config/frostwm/config.json" ]]; then
  install -m 644 "$ROOT/config.example.json" "$HOME/.config/frostwm/config.json"
fi
install -m 755 "$ROOT/bin/frostwm" "$HOME/.local/bin/frostwm"
install -m 644 "$ROOT/systemd/frostwm.service" "$HOME/.config/systemd/user/frostwm.service"
install -m 755 "$ROOT/waybar/frostwm" "$HOME/.config/waybar/scripts/frostwm"
if [[ -d "$ROOT/gnome-extension" ]]; then
  GNOME_EXT="$HOME/.local/share/gnome-shell/extensions/frostwm@maxx-us.github.io"
  mkdir -p "$GNOME_EXT"
  install -m 644 "$ROOT/gnome-extension/extension.js" "$GNOME_EXT/extension.js"
  install -m 644 "$ROOT/gnome-extension/metadata.json" "$GNOME_EXT/metadata.json"
  echo "Installed GNOME Shell extension files (enable with: gnome-extensions enable frostwm@maxx-us.github.io)."
fi
systemctl --user daemon-reload
echo "Installed FrostWM 0.9."
echo "Ensure ~/.local/bin is on PATH; in zsh add: export PATH=\"\$HOME/.local/bin:\$PATH\""
echo "Start it with: frostwm start"
echo "Optional autostart: frostwm enable"
