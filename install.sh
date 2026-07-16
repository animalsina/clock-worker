#!/usr/bin/env bash
set -euo pipefail

APP_ID="workbreak-guard"
APP_NAME="WorkBreak Guard"
INSTALL_DIR="$HOME/.local/share/$APP_ID"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
AUTOSTART_DIR="$HOME/.config/autostart"
ENABLE_AUTOSTART="1"
SHORTCUT_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/workbreak-guard-change-activity/"
SHORTCUT_SCHEMA="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
SHORTCUTS_SCHEMA="org.gnome.settings-daemon.plugins.media-keys"

for arg in "$@"; do
  case "$arg" in
    --no-autostart) ENABLE_AUTOSTART="0" ;;
    --autostart) ENABLE_AUTOSTART="1" ;;
    *) echo "Argomento non riconosciuto: $arg" >&2; exit 2 ;;
  esac
done

# Ricorda se la versione installata era già in esecuzione. L'installer deve
# sostituirla, ma non deve avviare l'app autonomamente quando prima era chiusa.
WAS_RUNNING="0"
RUNNING_PIDS=()
if command -v pgrep >/dev/null 2>&1; then
  while IFS= read -r pid; do
    [[ -n "$pid" ]] && RUNNING_PIDS+=("$pid")
  done < <(pgrep -f "$INSTALL_DIR/workbreak_guard.py" 2>/dev/null || true)
fi

if (( ${#RUNNING_PIDS[@]} > 0 )); then
  WAS_RUNNING="1"
  echo "Chiudo la versione precedente di $APP_NAME…"
  kill "${RUNNING_PIDS[@]}" 2>/dev/null || true
  for _ in {1..50}; do
    still_running="0"
    for pid in "${RUNNING_PIDS[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then
        still_running="1"
        break
      fi
    done
    [[ "$still_running" == "0" ]] && break
    sleep 0.1
  done
  for pid in "${RUNNING_PIDS[@]}"; do
    kill -9 "$pid" 2>/dev/null || true
  done
fi

mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$APP_DIR" "$AUTOSTART_DIR"
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$SOURCE_DIR/workbreak_guard.py" "$INSTALL_DIR/workbreak_guard.py"
chmod +x "$INSTALL_DIR/workbreak_guard.py"
for legal_file in LICENSE AUTHORS.md NOTICE; do
  if [[ -f "$SOURCE_DIR/$legal_file" ]]; then
    cp "$SOURCE_DIR/$legal_file" "$INSTALL_DIR/$legal_file"
  fi
done

cat > "$BIN_DIR/$APP_ID" <<EOF_INNER
#!/usr/bin/env bash
exec python3 "$INSTALL_DIR/workbreak_guard.py" "\$@"
EOF_INNER
chmod +x "$BIN_DIR/$APP_ID"

cat > "$APP_DIR/$APP_ID.desktop" <<EOF_INNER
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Promemoria pause configurabile per Ubuntu/Wayland
Exec=$BIN_DIR/$APP_ID
Icon=alarm-symbolic
Terminal=false
Categories=Utility;GTK;
StartupNotify=false
EOF_INNER

register_change_activity_shortcut() {
  if ! command -v gsettings >/dev/null 2>&1; then
    echo "Scorciatoia globale non registrata: gsettings non disponibile." >&2
    return 0
  fi

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
values = [str(item) for item in values]
if path not in values:
    values.append(path)
print(repr(values))
PY_INNER
)"

  gsettings set "$SHORTCUTS_SCHEMA" custom-keybindings "$updated" || return 0
  gsettings set "$SHORTCUT_SCHEMA:$SHORTCUT_PATH" name "WorkBreak Guard — Cambia attività" || return 0
  gsettings set "$SHORTCUT_SCHEMA:$SHORTCUT_PATH" command "$BIN_DIR/$APP_ID --change-activity" || return 0
  gsettings set "$SHORTCUT_SCHEMA:$SHORTCUT_PATH" binding '<Control><Alt>q' || return 0
  echo "Scorciatoia globale registrata: Ctrl+Alt+Q — Cosa stai facendo adesso?"
}

register_change_activity_shortcut

if [[ "$ENABLE_AUTOSTART" == "1" ]]; then
  cat > "$AUTOSTART_DIR/$APP_ID.desktop" <<EOF_INNER
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Promemoria pause configurabile per Ubuntu/Wayland
Exec=$BIN_DIR/$APP_ID --autostart
Icon=alarm-symbolic
Terminal=false
Categories=Utility;GTK;
StartupNotify=false
X-GNOME-Autostart-enabled=true
Hidden=false
EOF_INNER
else
  rm -f "$AUTOSTART_DIR/$APP_ID.desktop"
fi

if command -v apt-get >/dev/null 2>&1; then
  echo "Dipendenze consigliate su Ubuntu:"
  echo "  sudo apt-get install -y python3-gi gir1.2-gtk-3.0 pulseaudio-utils gir1.2-ayatanaappindicator3-0.1 gnome-shell-extension-appindicator"
fi

echo "Installato: $APP_NAME"
echo "Avvio manuale: $APP_ID"
if [[ "$ENABLE_AUTOSTART" == "1" ]]; then
  echo "Autostart abilitato: $AUTOSTART_DIR/$APP_ID.desktop"
else
  echo "Autostart disabilitato. Puoi abilitarlo con: $APP_ID --enable-autostart"
fi
echo "Comandi autostart: $APP_ID --enable-autostart | --disable-autostart | --status-autostart"
echo "Cambio attività: Ctrl+Alt+Q oppure $APP_ID --change-activity"
echo "Impostazioni: ~/.config/$APP_ID/settings.json o finestra Impostazioni dell'app"

if [[ "$WAS_RUNNING" == "1" ]]; then
  echo "Avvio la nuova versione perché l'istanza precedente era attiva…"
  nohup "$BIN_DIR/$APP_ID" --autostart >/dev/null 2>&1 &
else
  echo "Nessuna istanza era attiva: il programma resta chiuso."
fi
