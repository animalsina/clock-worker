#!/usr/bin/env bash
set -euo pipefail
SHORTCUT_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/workbreak-guard-change-activity/"
SHORTCUT_SCHEMA="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
SHORTCUTS_SCHEMA="org.gnome.settings-daemon.plugins.media-keys"

remove_change_activity_shortcut() {
  command -v gsettings >/dev/null 2>&1 || return 0

  local current updated
  current="$(gsettings get "$SHORTCUTS_SCHEMA" custom-keybindings 2>/dev/null || printf '@as []')"
  updated="$(python3 - "$current" "$SHORTCUT_PATH" <<'PY_INNER'
import ast
import sys

raw = sys.argv[1].strip()
path = sys.argv[2]
if raw.startswith("@as "):
    raw = raw[4:].strip()
try:
    values = ast.literal_eval(raw)
except Exception:
    values = []
if not isinstance(values, list):
    values = []
print(repr([str(item) for item in values if str(item) != path]))
PY_INNER
)"

  gsettings set "$SHORTCUTS_SCHEMA" custom-keybindings "$updated" >/dev/null 2>&1 || true
  gsettings reset-recursively "$SHORTCUT_SCHEMA:$SHORTCUT_PATH" >/dev/null 2>&1 || true
}

remove_change_activity_shortcut
rm -f "$HOME/.local/bin/workbreak-guard"
rm -f "$HOME/.local/share/applications/workbreak-guard.desktop"
rm -f "$HOME/.config/autostart/workbreak-guard.desktop"
rm -rf "$HOME/.local/share/workbreak-guard"
echo "Rimosso WorkBreak Guard. Le impostazioni restano in ~/.config/workbreak-guard; rimuovile manualmente se vuoi cancellarle."
