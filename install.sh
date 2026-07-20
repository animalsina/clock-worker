#!/usr/bin/env bash
set -euo pipefail

APP_ID="workbreak-guard"
APP_NAME="WorkBreak Guard"
INSTALL_DIR="$HOME/.local/share/$APP_ID"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
AUTOSTART_DIR="$HOME/.config/autostart"
ENABLE_AUTOSTART="1"
START_AFTER_INSTALL="1"
PID_FILE="$HOME/.config/$APP_ID/app.pid"
START_LOG="$HOME/.config/$APP_ID/startup.log"
SYSTEM_PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
SYSTEM_PYTHON="/usr/bin/python3"
SHORTCUT_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/workbreak-guard-change-activity/"
SHORTCUT_SCHEMA="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
SHORTCUTS_SCHEMA="org.gnome.settings-daemon.plugins.media-keys"

for arg in "$@"; do
  case "$arg" in
    --no-autostart) ENABLE_AUTOSTART="0" ;;
    --autostart) ENABLE_AUTOSTART="1" ;;
    --no-start) START_AFTER_INSTALL="0" ;;
    *) echo "Argomento non riconosciuto: $arg" >&2; exit 2 ;;
  esac
done

# Ripristina subito il runtime di sistema. Lo script può essere stato aperto da
# un terminale integrato in un'app Snap e aver ereditato librerie di core20.
export PATH="$SYSTEM_PATH"
export XDG_DATA_DIRS="/usr/local/share:/usr/share:/var/lib/snapd/desktop"
unset LD_LIBRARY_PATH LD_PRELOAD LD_AUDIT PYTHONHOME PYTHONPATH
unset GTK_PATH GIO_MODULE_DIR GIO_EXTRA_MODULES GI_TYPELIB_PATH GSETTINGS_SCHEMA_DIR
unset LIBGL_DRIVERS_PATH LIBVA_DRIVERS_PATH VK_ICD_FILENAMES
unset SNAP SNAP_ARCH SNAP_COMMON SNAP_CONTEXT SNAP_COOKIE SNAP_DATA
unset SNAP_INSTANCE_KEY SNAP_INSTANCE_NAME SNAP_LIBRARY_PATH SNAP_NAME SNAP_REAL_HOME
unset SNAP_REEXEC SNAP_REVISION SNAP_USER_COMMON SNAP_USER_DATA SNAP_VERSION

if [[ ! -x "$SYSTEM_PYTHON" ]]; then
  SYSTEM_PYTHON="$(PATH="$SYSTEM_PATH" command -v python3 2>/dev/null || true)"
fi
if [[ -z "$SYSTEM_PYTHON" || ! -x "$SYSTEM_PYTHON" || "$SYSTEM_PYTHON" == /snap/* ]]; then
  echo "Python di sistema non disponibile. Installa il pacchetto python3 di Ubuntu." >&2
  exit 1
fi

# Esegue un comando di sistema senza le variabili esportate da Snap, IDE,
# AppImage o ambienti Python incorporati. Queste variabili possono far caricare
# a /usr/bin/python3 la glibc di /snap/core20 e causare errori GLIBC_PRIVATE.
run_system_command() {
  env \
    -u LD_LIBRARY_PATH \
    -u LD_PRELOAD \
    -u LD_AUDIT \
    -u PYTHONHOME \
    -u PYTHONPATH \
    -u GTK_PATH \
    -u GIO_MODULE_DIR \
    -u GIO_EXTRA_MODULES \
    -u GI_TYPELIB_PATH \
    -u GSETTINGS_SCHEMA_DIR \
    -u LIBGL_DRIVERS_PATH \
    -u LIBVA_DRIVERS_PATH \
    -u VK_ICD_FILENAMES \
    -u SNAP \
    -u SNAP_ARCH \
    -u SNAP_COMMON \
    -u SNAP_CONTEXT \
    -u SNAP_COOKIE \
    -u SNAP_DATA \
    -u SNAP_INSTANCE_KEY \
    -u SNAP_INSTANCE_NAME \
    -u SNAP_LIBRARY_PATH \
    -u SNAP_NAME \
    -u SNAP_REAL_HOME \
    -u SNAP_REEXEC \
    -u SNAP_REVISION \
    -u SNAP_USER_COMMON \
    -u SNAP_USER_DATA \
    -u SNAP_VERSION \
    PATH="$SYSTEM_PATH" \
    XDG_DATA_DIRS="/usr/local/share:/usr/share:/var/lib/snapd/desktop" \
    "$@"
}

# Individua l'istanza tramite PID file e, come fallback, tramite riga comando.
# Il vecchio controllo sul solo percorso installato non riconosceva sempre le
# istanze avviate da launcher, terminale o da una versione precedente.
RUNNING_PIDS=()
declare -A SEEN_PIDS=()

add_running_pid() {
  local pid="${1:-}" cmdline="" process_name=""
  [[ "$pid" =~ ^[0-9]+$ ]] || return 0
  [[ "$pid" != "$$" ]] || return 0
  kill -0 "$pid" 2>/dev/null || return 0
  if [[ -r "/proc/$pid/comm" ]]; then
    process_name="$(cat "/proc/$pid/comm" 2>/dev/null || true)"
    [[ "$process_name" == python* ]] || return 0
  fi
  if [[ -r "/proc/$pid/cmdline" ]]; then
    cmdline="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
    [[ "$cmdline" == *"workbreak_guard.py"* ]] || return 0
  fi
  [[ -n "${SEEN_PIDS[$pid]:-}" ]] && return 0
  SEEN_PIDS[$pid]="1"
  RUNNING_PIDS+=("$pid")
}

if [[ -r "$PID_FILE" ]]; then
  add_running_pid "$(cat "$PID_FILE" 2>/dev/null || true)"
fi
if command -v pgrep >/dev/null 2>&1; then
  while IFS= read -r pid; do
    add_running_pid "$pid"
  done < <(pgrep -f 'workbreak_guard\.py' 2>/dev/null || true)
fi

if (( ${#RUNNING_PIDS[@]} > 0 )); then
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
set -e

# Usa sempre Python e librerie di Ubuntu. Un terminale aperto da un'app Snap
# può ereditare /snap/core20 nelle variabili di caricamento e rompere la glibc.
export PATH="$SYSTEM_PATH"
export XDG_DATA_DIRS="/usr/local/share:/usr/share:/var/lib/snapd/desktop"
unset LD_LIBRARY_PATH LD_PRELOAD LD_AUDIT PYTHONHOME PYTHONPATH
unset GTK_PATH GIO_MODULE_DIR GIO_EXTRA_MODULES GI_TYPELIB_PATH GSETTINGS_SCHEMA_DIR
unset LIBGL_DRIVERS_PATH LIBVA_DRIVERS_PATH VK_ICD_FILENAMES
unset SNAP SNAP_ARCH SNAP_COMMON SNAP_CONTEXT SNAP_COOKIE SNAP_DATA
unset SNAP_INSTANCE_KEY SNAP_INSTANCE_NAME SNAP_LIBRARY_PATH SNAP_NAME SNAP_REAL_HOME
unset SNAP_REEXEC SNAP_REVISION SNAP_USER_COMMON SNAP_USER_DATA SNAP_VERSION
exec "$SYSTEM_PYTHON" -I "$INSTALL_DIR/workbreak_guard.py" "\$@"
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

repair_legacy_desktop_launchers() {
  local desktop_dir="" candidate="" detected=""
  local -a desktop_dirs=("$HOME/Desktop" "$HOME/Scrivania")

  if [[ -x /usr/bin/xdg-user-dir ]]; then
    detected="$(run_system_command /usr/bin/xdg-user-dir DESKTOP 2>/dev/null || true)"
    [[ -n "$detected" ]] && desktop_dirs+=("$detected")
  fi

  declare -A seen_desktop_dirs=()
  for desktop_dir in "${desktop_dirs[@]}"; do
    [[ -n "$desktop_dir" && -d "$desktop_dir" ]] || continue
    [[ -n "${seen_desktop_dirs[$desktop_dir]:-}" ]] && continue
    seen_desktop_dirs[$desktop_dir]="1"

    while IFS= read -r -d '' candidate; do
      # Le vecchie scorciatoie cercavano workbreak_guard.py accanto al file
      # .desktop e mostravano "La cartella Desktop non contiene i file...".
      # Ora qualsiasi launcher WorkBreak Guard già presente punta sempre
      # all'installazione stabile in ~/.local/bin.
      if /usr/bin/grep -Eqi \
        '(^Name=.*WorkBreak Guard|workbreak[-_ ]guard|workbreak_guard\.py)' \
        "$candidate" 2>/dev/null; then
        cp "$APP_DIR/$APP_ID.desktop" "$candidate"
        chmod +x "$candidate"
        if [[ -x /usr/bin/gio ]]; then
          run_system_command /usr/bin/gio set \
            "$candidate" metadata::trusted true >/dev/null 2>&1 || true
        fi
        echo "Scorciatoia Desktop aggiornata: $candidate"
      fi
    done < <(find "$desktop_dir" -maxdepth 1 -type f -name '*.desktop' -print0 2>/dev/null)
  done
}

repair_legacy_desktop_launchers

register_change_activity_shortcut() {
  if ! command -v gsettings >/dev/null 2>&1; then
    echo "Scorciatoia globale non registrata: gsettings non disponibile." >&2
    return 0
  fi

  local current updated
  current="$(gsettings get "$SHORTCUTS_SCHEMA" custom-keybindings 2>/dev/null || printf '@as []')"
  updated="$("$SYSTEM_PYTHON" -I - "$current" "$SHORTCUT_PATH" <<'PY_INNER'
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
  echo "Dipendenze principali consigliate su Ubuntu:"
  echo "  sudo apt-get install -y python3-gi gir1.2-gtk-3.0 pulseaudio-utils pipewire-bin dbus gir1.2-ayatanaappindicator3-0.1 gnome-shell-extension-appindicator"
  echo "Integrazione Google Drive opzionale tramite GNOME:"
  echo "  sudo apt-get install -y gnome-online-accounts gvfs-backends libglib2.0-bin"
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

if [[ "$START_AFTER_INSTALL" == "1" ]]; then
  mkdir -p "$(dirname "$START_LOG")"
  rm -f "$PID_FILE"
  {
    printf '=== Avvio installazione %s ===\n' "$(date --iso-8601=seconds 2>/dev/null || date)"
    printf 'Python: %s\n' "$SYSTEM_PYTHON"
  } >"$START_LOG"
  echo "Avvio la versione appena installata…"
  if [[ -x /usr/bin/setsid ]]; then
    nohup /usr/bin/setsid "$BIN_DIR/$APP_ID" --autostart </dev/null >>"$START_LOG" 2>&1 &
  else
    nohup "$BIN_DIR/$APP_ID" --autostart </dev/null >>"$START_LOG" 2>&1 &
  fi

  started="0"
  for _ in {1..80}; do
    if [[ -r "$PID_FILE" ]]; then
      new_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
      if [[ "$new_pid" =~ ^[0-9]+$ ]] && kill -0 "$new_pid" 2>/dev/null; then
        started="1"
        break
      fi
    fi
    sleep 0.1
  done
  if [[ "$started" == "1" ]]; then
    echo "Programma riaperto correttamente (PID $new_pid)."
  else
    echo "Installazione completata, ma l'avvio automatico non è riuscito." >&2
    echo "Log: $START_LOG" >&2
    tail -n 20 "$START_LOG" 2>/dev/null || true
    echo "Avvio manuale: $BIN_DIR/$APP_ID" >&2
  fi
else
  echo "Avvio finale disattivato con --no-start."
fi
