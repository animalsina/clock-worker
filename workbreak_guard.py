#!/usr/bin/env python3
"""
WorkBreak Guard - promemoria pausa per Ubuntu/Wayland.

Funzioni principali:
- Gestisce mattina e pomeriggio come sessioni separate.
- All'inizio di ogni sessione azzera il timer e chiede conferma prima di partire.
- Esclude sabato/domenica e, se attivo, festivi italiani.
- Alla fine del tempo di lavoro permette un ultimatum predefinito, di 5 o 10 minuti.
- Mostra i countdown soltanto accanto all'icona nella barra di sistema.
- Registra progetto, attività corrente, lavoro effettivo e pause effettive.
- Permette di cambiare attività, riprendere quelle di oggi/ieri e consultare 24 mesi di storico.
- Supporta Ctrl+Alt+Q come scorciatoia globale per cambiare attività.
- Permette di aggiungere, modificare ed eliminare manualmente attività e durate giornaliere, incluso il tempo precedente non classificato.
- Genera un riepilogo Markdown del giorno selezionato, pronto da copiare.
- Mostra un riepilogo dettagliato al termine della giornata, con straordinari giornalieri e mensili.
- Continua a conteggiare il lavoro fino alla conferma effettiva di inizio pausa.
- Calcola obiettivo giornaliero, pausa accreditata, massimale settimanale ed EXTRA.
- Mantiene un saldo ore tra giornate, con recupero post chiusura o rinvio al giorno successivo.
- Tronca le pause pomeridiane all'orario effettivo di chiusura.
- Chiude mensilmente il saldo positivo nel primo giorno della settimana configurato dopo il giorno base.
- Permette di lavorare su festività/ferie/giorni esclusi classificando quelle ore come EXTRA.
- Può azzerare il ciclo e ripartire subito dal tempo completo configurato.
- Ripristina fase, tempo residuo, progetto e attività dopo la chiusura nella stessa fascia.
- Gestisce il lavoro oltre la fine fascia con conferma, promemoria periodici e recupero della pausa mattutina.
- Calcola festività nazionali, patroni di Este/Firenze e ferie o ricorrenze personalizzate.
- Impostazioni GTK salvate in ~/.config/workbreak-guard/settings.json.
- Statistiche salvate in ~/.config/workbreak-guard/activity-log.json.
- AppIndicator/Ayatana tray se disponibile, con etichetta tempo compatta se supportata.
- Finestra controllo fallback se la tray non è disponibile.
"""

from __future__ import annotations

import datetime as dt
import atexit
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk, Pango  # type: ignore

# AppIndicator è opzionale. Su Ubuntu/GNOME spesso serve l'estensione AppIndicator.
Indicator = None
IndicatorCategory = None
IndicatorStatus = None
try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as Indicator  # type: ignore

    IndicatorCategory = Indicator.IndicatorCategory
    IndicatorStatus = Indicator.IndicatorStatus
except Exception:
    try:
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3 as Indicator  # type: ignore

        IndicatorCategory = Indicator.IndicatorCategory
        IndicatorStatus = Indicator.IndicatorStatus
    except Exception:
        Indicator = None

APP_ID = "workbreak-guard"
APP_NAME = "WorkBreak Guard"
CONFIG_DIR = Path.home() / ".config" / APP_ID
CONFIG_FILE = CONFIG_DIR / "settings.json"
ACTIVITY_LOG_FILE = CONFIG_DIR / "activity-log.json"
RUNTIME_STATE_FILE = CONFIG_DIR / "runtime-state.json"
PID_FILE = CONFIG_DIR / "app.pid"
AUTOSTART_DIR = Path.home() / ".config" / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / f"{APP_ID}.desktop"
SESSION_END_INACTIVITY_SECONDS = 20 * 60


@dataclass
class Settings:
    enabled: bool = True
    work_minutes: int = 60
    break_minutes: int = 5
    daily_target_hours: int = 8
    warning_seconds: int = 60
    overtime_reminder_minutes: int = 10
    extra_closure_day: int = 1
    extra_closure_weekday: int = 0  # lun=0
    active_days: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])  # lun=0
    morning_start: str = "09:00"
    morning_end: str = "13:00"
    afternoon_start: str = "14:00"
    afternoon_end: str = "18:00"
    skip_italian_holidays: bool = True
    local_holidays: list[str] = field(default_factory=lambda: ["este", "firenze"])
    custom_holidays: list[str] = field(default_factory=list)  # compatibilità: YYYY-MM-DD
    custom_days_off: list[dict] = field(default_factory=list)
    audio_enabled: bool = True
    beep_volume: float = 0.10  # ampiezza wav, volutamente bassa
    beep_count: int = 5
    beep_interval_seconds: int = 20
    show_clock_last_minutes: int = 5
    clock_enabled: bool = True
    indicator_label_enabled: bool = True
    markdown_include_task_times: bool = False
    clock_opacity_low: float = 0.22
    clock_opacity_high: float = 0.72
    launch_minimized: bool = True

    @classmethod
    def load(cls) -> "Settings":
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if not CONFIG_FILE.exists():
            s = cls()
            s.save()
            return s
        try:
            raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            base = cls()
            for key, value in raw.items():
                if hasattr(base, key):
                    setattr(base, key, value)
            base.sanitize()
            return base
        except Exception:
            backup = CONFIG_FILE.with_suffix(".broken.json")
            try:
                CONFIG_FILE.rename(backup)
            except Exception:
                pass
            s = cls()
            s.save()
            return s

    def sanitize(self) -> None:
        self.work_minutes = clamp_int(self.work_minutes, 5, 240)
        self.break_minutes = clamp_int(self.break_minutes, 1, 60)
        self.daily_target_hours = clamp_int(self.daily_target_hours, 1, 24)
        self.warning_seconds = clamp_int(self.warning_seconds, 5, 600)
        self.overtime_reminder_minutes = clamp_int(self.overtime_reminder_minutes, 1, 120)
        self.extra_closure_day = clamp_int(self.extra_closure_day, 1, 28)
        self.extra_closure_weekday = clamp_int(self.extra_closure_weekday, 0, 6)
        self.show_clock_last_minutes = clamp_int(self.show_clock_last_minutes, 0, 60)
        self.beep_count = clamp_int(self.beep_count, 0, 20)
        self.beep_interval_seconds = clamp_int(self.beep_interval_seconds, 5, 300)
        self.beep_volume = max(0.0, min(float(self.beep_volume), 0.30))
        self.active_days = [int(x) for x in self.active_days if int(x) in range(7)] or [0, 1, 2, 3, 4]
        self.morning_start = normalize_time(self.morning_start, "09:00")
        self.morning_end = normalize_time(self.morning_end, "13:00")
        self.afternoon_start = normalize_time(self.afternoon_start, "14:00")
        self.afternoon_end = normalize_time(self.afternoon_end, "18:00")
        local_holidays = self.local_holidays if isinstance(self.local_holidays, list) else []
        self.local_holidays = [
            key for key in local_holidays if str(key) in LOCAL_HOLIDAY_DEFINITIONS
        ]
        self.local_holidays = sorted(set(str(key) for key in self.local_holidays))

        cleaned = []
        legacy_holidays = self.custom_holidays if isinstance(self.custom_holidays, list) else []
        for item in legacy_holidays:
            try:
                dt.date.fromisoformat(str(item).strip())
                cleaned.append(str(item).strip())
            except Exception:
                pass
        self.custom_holidays = sorted(set(cleaned))

        normalized_days_off: list[dict] = []
        seen_days_off: set[tuple[str, str, str, bool, str]] = set()
        custom_days_off = self.custom_days_off if isinstance(self.custom_days_off, list) else []
        for item in custom_days_off:
            normalized = normalize_day_off_entry(item)
            if normalized is None:
                continue
            key = (
                normalized["start"],
                normalized["end"],
                normalized["label"].casefold(),
                bool(normalized["recurring"]),
                normalized["kind"],
            )
            if key in seen_days_off:
                continue
            seen_days_off.add(key)
            normalized_days_off.append(normalized)

        # Migra senza perdita il vecchio elenco di date singole.
        existing_exact_dates = {
            entry["start"]
            for entry in normalized_days_off
            if not entry["recurring"] and entry["start"] == entry["end"]
        }
        for date_text in self.custom_holidays:
            if date_text in existing_exact_dates:
                continue
            normalized_days_off.append(
                {
                    "start": date_text,
                    "end": date_text,
                    "label": "Festività personalizzata",
                    "recurring": False,
                    "kind": "holiday",
                }
            )
        self.custom_days_off = sorted(
            normalized_days_off,
            key=lambda item: (item["start"], item["end"], item["label"].casefold()),
        )
        # Il vecchio campo viene svuotato dopo la migrazione, così una data eliminata
        # dalla nuova interfaccia non viene ricreata al salvataggio successivo.
        self.custom_holidays = []

    def save(self) -> None:
        self.sanitize()
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")


def clamp_int(value: int, low: int, high: int) -> int:
    try:
        ivalue = int(value)
    except Exception:
        ivalue = low
    return max(low, min(ivalue, high))


def normalize_time(value: str, fallback: str) -> str:
    try:
        h, m = str(value).strip().split(":", 1)
        hh = max(0, min(int(h), 23))
        mm = max(0, min(int(m), 59))
        return f"{hh:02d}:{mm:02d}"
    except Exception:
        return fallback


def parse_hhmm(value: str) -> dt.time:
    h, m = normalize_time(value, "00:00").split(":")
    return dt.time(int(h), int(m))


def easter_date(year: int) -> dt.date:
    """Algoritmo Meeus/Jones/Butcher per Pasqua gregoriana."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    mm = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * mm + 114) // 31
    day = ((h + l - 7 * mm + 114) % 31) + 1
    return dt.date(year, month, day)


LOCAL_HOLIDAY_DEFINITIONS = {
    "este": {
        "label": "Santa Tecla, patrona di Este",
        "month": 9,
        "day": 23,
    },
    "firenze": {
        "label": "San Giovanni Battista, patrono di Firenze",
        "month": 6,
        "day": 24,
    },
}


def italian_holiday_names(year: int) -> dict[dt.date, str]:
    holidays = {
        dt.date(year, 1, 1): "Capodanno",
        dt.date(year, 1, 6): "Epifania",
        dt.date(year, 4, 25): "Festa della Liberazione",
        dt.date(year, 5, 1): "Festa del Lavoro",
        dt.date(year, 6, 2): "Festa della Repubblica",
        dt.date(year, 8, 15): "Ferragosto",
        dt.date(year, 11, 1): "Ognissanti",
        dt.date(year, 12, 8): "Immacolata Concezione",
        dt.date(year, 12, 25): "Natale",
        dt.date(year, 12, 26): "Santo Stefano",
        easter_date(year) + dt.timedelta(days=1): "Lunedì dell’Angelo",
    }
    # Legge 8 ottobre 2025, n. 151, in vigore dal 1° gennaio 2026.
    if year >= 2026:
        holidays[dt.date(year, 10, 4)] = "San Francesco d’Assisi"
    return holidays


def italian_holidays(year: int) -> set[dt.date]:
    return set(italian_holiday_names(year))


def local_holiday_names(year: int, enabled: list[str]) -> dict[dt.date, str]:
    holidays: dict[dt.date, str] = {}
    for key in enabled:
        definition = LOCAL_HOLIDAY_DEFINITIONS.get(str(key))
        if not definition:
            continue
        holidays[dt.date(year, int(definition["month"]), int(definition["day"]))] = str(
            definition["label"]
        )
    return holidays


def normalize_day_off_entry(item: object) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    try:
        start = dt.date.fromisoformat(str(item.get("start", "")).strip())
        end = dt.date.fromisoformat(str(item.get("end", item.get("start", ""))).strip())
    except Exception:
        return None
    if end < start:
        start, end = end, start
    if (end - start).days > 366:
        end = start + dt.timedelta(days=366)
    kind = str(item.get("kind", "vacation")).strip().lower()
    if kind not in {"vacation", "holiday", "workday"}:
        kind = "vacation"
    label = str(item.get("label", "")).strip()
    if not label:
        default_labels = {
            "vacation": "Ferie",
            "holiday": "Festività personalizzata",
            "workday": "Giornata lavorativa straordinaria",
        }
        label = default_labels[kind]
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "label": label,
        "recurring": bool(item.get("recurring", False)),
        "kind": kind,
    }


def _safe_date(year: int, month: int, day: int) -> dt.date:
    while day > 28:
        try:
            return dt.date(year, month, day)
        except ValueError:
            day -= 1
    return dt.date(year, month, day)


def custom_day_off_matches(day: dt.date, entry: dict) -> bool:
    normalized = normalize_day_off_entry(entry)
    if normalized is None:
        return False
    start = dt.date.fromisoformat(normalized["start"])
    end = dt.date.fromisoformat(normalized["end"])
    if not normalized["recurring"]:
        return start <= day <= end

    start_this_year = _safe_date(day.year, start.month, start.day)
    end_this_year = _safe_date(day.year, end.month, end.day)
    if (end.month, end.day) >= (start.month, start.day):
        return start_this_year <= day <= end_this_year

    # Intervallo ricorrente che attraversa Capodanno.
    end_next_year = _safe_date(day.year + 1, end.month, end.day)
    start_previous_year = _safe_date(day.year - 1, start.month, start.day)
    end_current_year = _safe_date(day.year, end.month, end.day)
    return start_this_year <= day <= end_next_year or start_previous_year <= day <= end_current_year


def custom_day_off_label(day: dt.date, entries: list[dict]) -> Optional[str]:
    for entry in entries:
        normalized = normalize_day_off_entry(entry)
        if normalized is None or normalized["kind"] == "workday":
            continue
        if custom_day_off_matches(day, normalized):
            label = str(normalized.get("label", "")).strip()
            return label or "Giornata esclusa"
    return None


def custom_workday_label(day: dt.date, entries: list[dict]) -> Optional[str]:
    """Restituisce l'eventuale autorizzazione a lavorare in una giornata esclusa."""
    for entry in entries:
        normalized = normalize_day_off_entry(entry)
        if normalized is None or normalized["kind"] != "workday":
            continue
        if custom_day_off_matches(day, normalized):
            label = str(normalized.get("label", "")).strip()
            return label or "Giornata lavorativa straordinaria"
    return None


def format_mmss(seconds: int) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def format_signed_hours_minutes(seconds: int, always_sign: bool = True) -> str:
    seconds = int(seconds)
    sign = "+" if seconds >= 0 else "−"
    total_minutes = int(math.ceil(abs(seconds) / 60.0)) if seconds else 0
    hours, minutes = divmod(total_minutes, 60)
    prefix = sign if always_sign or seconds < 0 else ""
    return f"{prefix}{hours:02d}:{minutes:02d}"


def format_compact_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds >= 3600:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h{minutes:02d}"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"


ITALIAN_MONTH_NAMES = (
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
)

ITALIAN_MONTH_ABBREVIATIONS = (
    "gen",
    "feb",
    "mar",
    "apr",
    "mag",
    "giu",
    "lug",
    "ago",
    "set",
    "ott",
    "nov",
    "dic",
)


def format_italian_markdown_date(day: dt.date) -> str:
    return f"{day.day:02d} {ITALIAN_MONTH_ABBREVIATIONS[day.month - 1]} {day.year}"


def installed_command() -> str:
    local_bin = Path.home() / ".local" / "bin" / APP_ID
    if local_bin.exists():
        return str(local_bin)
    return str(Path(__file__).resolve())


def autostart_desktop_text() -> str:
    cmd = installed_command()
    return f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
Comment=Promemoria pause configurabile per Ubuntu/Wayland
Exec={cmd} --autostart
Icon=alarm-symbolic
Terminal=false
Categories=Utility;GTK;
StartupNotify=false
X-GNOME-Autostart-enabled=true
Hidden=false
"""


def set_autostart_enabled(enabled: bool) -> None:
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    if enabled:
        AUTOSTART_FILE.write_text(autostart_desktop_text(), encoding="utf-8")
    else:
        if AUTOSTART_FILE.exists():
            AUTOSTART_FILE.unlink()


def is_autostart_enabled() -> bool:
    return AUTOSTART_FILE.exists()


def rgba(css: str) -> None:
    provider = Gtk.CssProvider()
    provider.load_from_data(css.encode("utf-8"))
    screen = Gdk.Screen.get_default()
    if screen:
        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


rgba(
    """
    .wb-card {
        background: rgba(18, 18, 22, 0.94);
        color: #ffffff;
        border-radius: 22px;
        padding: 24px;
        box-shadow: 0 18px 70px rgba(0,0,0,0.50);
    }
    .wb-title { font-size: 28px; font-weight: 800; }
    .wb-body { font-size: 18px; }
    .wb-clock {
        background: rgba(18, 18, 22, 0.40);
        color: #ffffff;
        border-radius: 13px;
        padding: 7px 12px;
        font-size: 14px;
        font-weight: 700;
    }
    .wb-countdown { font-size: 64px; font-weight: 900; }
    .wb-danger { color: #ff8a80; }
    .wb-ok { color: #b9f6ca; }
    """
)


class AlertWindow(Gtk.Window):
    def __init__(self, title: str, message: str, button_text: str = "OK", on_click: Optional[Callable] = None):
        super().__init__(title=title)
        self.on_click = on_click
        self.set_default_size(520, 220)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.connect("key-press-event", self._on_key)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        outer.set_border_width(24)
        outer.get_style_context().add_class("wb-card")
        self.add(outer)

        title_label = Gtk.Label(label=title)
        title_label.get_style_context().add_class("wb-title")
        title_label.set_line_wrap(True)
        title_label.set_justify(Gtk.Justification.CENTER)
        outer.pack_start(title_label, False, False, 0)

        msg_label = Gtk.Label(label=message)
        msg_label.get_style_context().add_class("wb-body")
        msg_label.set_line_wrap(True)
        msg_label.set_justify(Gtk.Justification.CENTER)
        outer.pack_start(msg_label, True, True, 0)

        button = Gtk.Button(label=button_text)
        button.set_size_request(220, 48)
        button.connect("clicked", self._clicked)
        outer.pack_start(button, False, False, 0)

        self.show_all()
        place_on_active_monitor(self, 520, 220)
        self.present()

    def _clicked(self, *_args) -> None:
        if self.on_click:
            self.on_click()
        self.destroy()

    def _on_key(self, _widget, event) -> bool:
        # Invio/Spazio equivalgono al pulsante principale.
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self._clicked()
            return True
        return False



def place_on_active_monitor(window: Gtk.Window, width: int, height: int) -> None:
    """Centra la finestra sul monitor in cui si trova il puntatore."""
    try:
        display = Gdk.Display.get_default()
        if not display:
            return
        monitor = None
        seat = display.get_default_seat()
        pointer = seat.get_pointer() if seat else None
        if pointer:
            _screen, x, y = pointer.get_position()
            if hasattr(display, "get_monitor_at_point"):
                monitor = display.get_monitor_at_point(x, y)
        monitor = monitor or display.get_primary_monitor() or display.get_monitor(0)
        if not monitor:
            return
        geo = monitor.get_geometry()
        window.resize(width, height)
        window.move(geo.x + max(0, (geo.width - width) // 2), geo.y + max(0, (geo.height - height) // 2))
    except Exception:
        # Su Wayland il compositor può ignorare il posizionamento esplicito.
        pass


class ChoiceAlertWindow(Gtk.Window):
    def __init__(
        self,
        title: str,
        message: str,
        choices: list[tuple[str, Callable[[], None]]],
    ):
        super().__init__(title=title)
        self.choices = choices
        self.set_default_size(620, 250)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.connect("key-press-event", self._on_key)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        outer.set_border_width(24)
        outer.get_style_context().add_class("wb-card")
        self.add(outer)

        title_label = Gtk.Label(label=title)
        title_label.get_style_context().add_class("wb-title")
        title_label.set_line_wrap(True)
        title_label.set_justify(Gtk.Justification.CENTER)
        outer.pack_start(title_label, False, False, 0)

        msg_label = Gtk.Label(label=message)
        msg_label.get_style_context().add_class("wb-body")
        msg_label.set_line_wrap(True)
        msg_label.set_justify(Gtk.Justification.CENTER)
        outer.pack_start(msg_label, True, True, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.set_homogeneous(True)
        outer.pack_start(row, False, False, 0)
        for label, callback in choices:
            button = Gtk.Button(label=label)
            button.set_size_request(170, 48)
            button.connect("clicked", self._clicked, callback)
            row.pack_start(button, True, True, 0)

        self.show_all()
        place_on_active_monitor(self, 620, 250)
        self.present()

    def _clicked(self, _button: Gtk.Button, callback: Callable[[], None]) -> None:
        self.destroy()
        callback()

    def _on_key(self, _widget, event) -> bool:
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space) and self.choices:
            self.destroy()
            self.choices[0][1]()
            return True
        return False


class ActivityPromptWindow(Gtk.Window):
    def __init__(
        self,
        title: str,
        current_activity: str,
        current_project: str,
        recent_activities: list[dict],
        project_suggestions: list[str],
        on_activity: Callable[[str, str], None],
        on_later: Optional[Callable[[], None]] = None,
        activity_question: str = "Cosa stai facendo adesso?",
    ):
        super().__init__(title=title)
        self.current_activity = current_activity.strip()
        self.current_project = current_project.strip()
        self.recent_activities = recent_activities
        self.on_activity = on_activity
        self.on_later = on_later
        self.activity_question = activity_question
        self.set_default_size(700, 500)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_border_width(24)
        outer.get_style_context().add_class("wb-card")
        self.add(outer)

        title_label = Gtk.Label(label=title)
        title_label.get_style_context().add_class("wb-title")
        title_label.set_line_wrap(True)
        title_label.set_justify(Gtk.Justification.CENTER)
        outer.pack_start(title_label, False, False, 0)

        if self.current_activity:
            current_label = self._display_activity(self.current_project, self.current_activity)
            if len(current_label) > 75:
                current_label = current_label[:72] + "…"
            continue_button = Gtk.Button(label=f"Continuo: {current_label}")
            continue_button.set_size_request(-1, 46)
            continue_button.connect(
                "clicked",
                lambda *_: self._finish(self.current_activity, self.current_project),
            )
            outer.pack_start(continue_button, False, False, 0)

        if self.recent_activities:
            recent_label = Gtk.Label(label="Riprendi un’attività di oggi o di ieri")
            recent_label.set_xalign(0)
            outer.pack_start(recent_label, False, False, 0)

            recent_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            outer.pack_start(recent_row, False, False, 0)
            self.recent_combo = Gtk.ComboBoxText()
            for item in self.recent_activities:
                self.recent_combo.append_text(str(item.get("label", "")))
            self.recent_combo.set_active(0)
            recent_row.pack_start(self.recent_combo, True, True, 0)

            resume_button = Gtk.Button(label="Riprendi")
            resume_button.connect("clicked", lambda *_: self._resume_recent())
            recent_row.pack_start(resume_button, False, False, 0)
        else:
            self.recent_combo = None

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        outer.pack_start(separator, False, False, 4)

        new_label = Gtk.Label(label="Oppure crea una nuova attività")
        new_label.set_xalign(0)
        new_label.get_style_context().add_class("wb-body")
        outer.pack_start(new_label, False, False, 0)

        project_label = Gtk.Label(label="Progetto")
        project_label.set_xalign(0)
        outer.pack_start(project_label, False, False, 0)

        self.project_combo = Gtk.ComboBoxText.new_with_entry()
        for project in project_suggestions:
            self.project_combo.append_text(project)
        project_entry = self.project_combo.get_child()
        if isinstance(project_entry, Gtk.Entry):
            project_entry.set_placeholder_text("Scrivi o cerca un progetto già usato")
            project_entry.set_text(self.current_project)
            completion_model = Gtk.ListStore(str)
            for project in project_suggestions:
                completion_model.append([project])
            completion = Gtk.EntryCompletion()
            completion.set_model(completion_model)
            completion.set_text_column(0)
            completion.set_inline_completion(True)
            completion.set_popup_completion(True)
            completion.set_match_func(self._project_match)
            project_entry.set_completion(completion)
        outer.pack_start(self.project_combo, False, False, 0)

        activity_label = Gtk.Label(label=self.activity_question)
        activity_label.set_xalign(0)
        outer.pack_start(activity_label, False, False, 0)

        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Descrivi brevemente l’attività")
        self.entry.set_activates_default(True)
        outer.pack_start(self.entry, False, False, 0)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        outer.pack_start(buttons, False, False, 0)

        start_button = Gtk.Button(label="Inizia o passa a questa attività")
        start_button.set_can_default(True)
        start_button.connect("clicked", lambda *_: self._submit_entry())
        buttons.pack_start(start_button, True, True, 0)
        start_button.grab_default()

        if on_later:
            later_button = Gtk.Button(label="Non ancora")
            later_button.connect("clicked", lambda *_: self._later())
            buttons.pack_start(later_button, False, False, 0)

        self.show_all()
        place_on_active_monitor(self, 700, 500)
        self.present()
        self.entry.grab_focus()

    @staticmethod
    def _display_activity(project: str, activity: str) -> str:
        return f"{project} — {activity}" if project else activity

    @staticmethod
    def _project_match(_completion: Gtk.EntryCompletion, key: str, tree_iter: Gtk.TreeIter, data=None) -> bool:
        model = _completion.get_model()
        value = str(model[tree_iter][0]) if model is not None else ""
        return key.casefold() in value.casefold()

    def _project_text(self) -> str:
        child = self.project_combo.get_child()
        if isinstance(child, Gtk.Entry):
            return child.get_text().strip()
        return ""

    def _resume_recent(self) -> None:
        if self.recent_combo is None:
            return
        index = self.recent_combo.get_active()
        if index < 0 or index >= len(self.recent_activities):
            return
        item = self.recent_activities[index]
        self._finish(str(item.get("text", "")), str(item.get("project", "")))

    def _submit_entry(self) -> None:
        activity = self.entry.get_text().strip()
        if not activity:
            self.entry.set_placeholder_text("Indica l’attività oppure riprendine una")
            self.entry.grab_focus()
            return
        self._finish(activity, self._project_text())

    def _finish(self, activity: str, project: str) -> None:
        self.destroy()
        self.on_activity(activity.strip(), project.strip())

    def _later(self) -> None:
        self.destroy()
        if self.on_later:
            self.on_later()


class ActivityEntryDialog(Gtk.Dialog):
    def __init__(
        self,
        parent: Gtk.Window,
        title: str,
        project_suggestions: list[str],
        project: str = "",
        activity: str = "",
        seconds: int = 0,
    ):
        super().__init__(title=title, transient_for=parent, flags=Gtk.DialogFlags.MODAL)
        self.add_button("Annulla", Gtk.ResponseType.CANCEL)
        save_button = self.add_button("Salva", Gtk.ResponseType.OK)
        save_button.get_style_context().add_class("suggested-action")
        self.set_default_response(Gtk.ResponseType.OK)
        self.set_default_size(560, 280)
        self.set_resizable(False)

        content = self.get_content_area()
        content.set_spacing(12)
        content.set_border_width(16)

        grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        content.pack_start(grid, True, True, 0)

        project_label = Gtk.Label(label="Progetto")
        project_label.set_xalign(0)
        grid.attach(project_label, 0, 0, 1, 1)

        self.project_combo = Gtk.ComboBoxText.new_with_entry()
        for suggestion in project_suggestions:
            self.project_combo.append_text(suggestion)
        project_entry = self.project_combo.get_child()
        if isinstance(project_entry, Gtk.Entry):
            project_entry.set_text(project)
            project_entry.set_placeholder_text("Scrivi o cerca un progetto")
            completion_model = Gtk.ListStore(str)
            for suggestion in project_suggestions:
                completion_model.append([suggestion])
            completion = Gtk.EntryCompletion()
            completion.set_model(completion_model)
            completion.set_text_column(0)
            completion.set_inline_completion(True)
            completion.set_popup_completion(True)
            completion.set_match_func(ActivityPromptWindow._project_match)
            project_entry.set_completion(completion)
        grid.attach(self.project_combo, 1, 0, 3, 1)

        activity_label = Gtk.Label(label="Attività")
        activity_label.set_xalign(0)
        grid.attach(activity_label, 0, 1, 1, 1)

        self.activity_entry = Gtk.Entry()
        self.activity_entry.set_text(activity)
        self.activity_entry.set_placeholder_text("Descrivi l’attività")
        self.activity_entry.set_activates_default(True)
        grid.attach(self.activity_entry, 1, 1, 3, 1)

        duration_label = Gtk.Label(label="Tempo impiegato")
        duration_label.set_xalign(0)
        grid.attach(duration_label, 0, 2, 1, 1)

        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)

        self.hours_spin = Gtk.SpinButton.new_with_range(0, 9999, 1)
        self.hours_spin.set_value(hours)
        self.minutes_spin = Gtk.SpinButton.new_with_range(0, 59, 1)
        self.minutes_spin.set_value(minutes)
        self.seconds_spin = Gtk.SpinButton.new_with_range(0, 59, 1)
        self.seconds_spin.set_value(secs)

        duration_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        duration_box.pack_start(self.hours_spin, False, False, 0)
        duration_box.pack_start(Gtk.Label(label="ore"), False, False, 0)
        duration_box.pack_start(self.minutes_spin, False, False, 0)
        duration_box.pack_start(Gtk.Label(label="min"), False, False, 0)
        duration_box.pack_start(self.seconds_spin, False, False, 0)
        duration_box.pack_start(Gtk.Label(label="sec"), False, False, 0)
        grid.attach(duration_box, 1, 2, 3, 1)

        note = Gtk.Label(
            label="La durata modifica automaticamente il totale di lavoro della giornata."
        )
        note.set_xalign(0)
        note.set_line_wrap(True)
        grid.attach(note, 0, 3, 4, 1)

        self.show_all()
        self.activity_entry.grab_focus()

    def values(self) -> tuple[str, str, int]:
        project_entry = self.project_combo.get_child()
        project = project_entry.get_text().strip() if isinstance(project_entry, Gtk.Entry) else ""
        activity = self.activity_entry.get_text().strip()
        seconds = (
            int(self.hours_spin.get_value_as_int()) * 3600
            + int(self.minutes_spin.get_value_as_int()) * 60
            + int(self.seconds_spin.get_value_as_int())
        )
        return activity, project, seconds


class MarkdownPreviewWindow(Gtk.Window):
    def __init__(self, parent: Optional[Gtk.Window], markdown_text: str):
        super().__init__(title="Riepilogo Markdown")
        self.markdown_text = markdown_text
        if parent is not None:
            self.set_transient_for(parent)
            self.set_modal(True)
            self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        else:
            self.set_modal(False)
            self.set_position(Gtk.WindowPosition.CENTER)
        self.set_default_size(720, 560)
        self.set_border_width(16)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(outer)

        title = Gtk.Label(label="Riepilogo pronto in Markdown")
        title.set_xalign(0)
        title.modify_font(Pango.FontDescription("Sans Bold 16"))
        outer.pack_start(title, False, False, 0)

        self.text_view = Gtk.TextView()
        self.text_view.set_editable(True)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.set_monospace(True)
        self.text_view.get_buffer().set_text(markdown_text)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.text_view)
        outer.pack_start(scroll, True, True, 0)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer.pack_start(footer, False, False, 0)

        copy_button = Gtk.Button(label="Copia negli appunti")
        copy_button.connect("clicked", self._copy_markdown)
        footer.pack_start(copy_button, False, False, 0)

        close_button = Gtk.Button(label="Chiudi")
        close_button.connect("clicked", lambda *_: self.destroy())
        footer.pack_end(close_button, False, False, 0)

        self.show_all()
        place_on_active_monitor(self, 720, 560)
        self.present()

    def _copy_markdown(self, button: Gtk.Button) -> None:
        buffer = self.text_view.get_buffer()
        start, end = buffer.get_bounds()
        current_text = buffer.get_text(start, end, True)
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(current_text, -1)
        clipboard.store()
        button.set_label("Copiato")
        GLib.timeout_add_seconds(2, lambda: self._restore_copy_label(button))

    @staticmethod
    def _restore_copy_label(button: Gtk.Button) -> bool:
        if button.get_parent() is not None:
            button.set_label("Copia negli appunti")
        return False


class ActivitySummaryWindow(Gtk.Window):
    def __init__(self, app: "WorkBreakApp", selected_day: Optional[dt.date] = None):
        super().__init__(title="Attività e tempi")
        self.app = app
        self.selected_day = selected_day or dt.date.today()
        self._changing_day = False
        self.markdown_window: Optional[MarkdownPreviewWindow] = None
        self.set_default_size(940, 580)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(16)
        self.connect("destroy", self._on_destroy)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(outer)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer.pack_start(header, False, False, 0)
        previous_button = Gtk.Button(label="‹ Giorno precedente")
        previous_button.connect("clicked", lambda *_: self._move_day(-1))
        header.pack_start(previous_button, False, False, 0)

        self.date_label = Gtk.Label()
        self.date_label.modify_font(Pango.FontDescription("Sans Bold 16"))
        header.pack_start(self.date_label, True, True, 0)

        self.day_combo = Gtk.ComboBoxText()
        self.day_combo.set_tooltip_text("Vai rapidamente a un giorno già registrato")
        self.day_combo.connect("changed", self._day_selected)
        header.pack_start(self.day_combo, False, False, 0)

        today_button = Gtk.Button(label="Oggi")
        today_button.connect("clicked", lambda *_: self._set_day(dt.date.today()))
        header.pack_start(today_button, False, False, 0)

        next_button = Gtk.Button(label="Giorno successivo ›")
        next_button.connect("clicked", lambda *_: self._move_day(1))
        header.pack_start(next_button, False, False, 0)

        self.totals_label = Gtk.Label()
        self.totals_label.set_xalign(0)
        self.totals_label.set_line_wrap(True)
        self.totals_label.set_selectable(True)
        outer.pack_start(self.totals_label, False, False, 0)

        # project, activity, formatted duration, seconds, editable, unclassified
        self.store = Gtk.ListStore(str, str, str, int, bool, bool)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.connect("row-activated", lambda *_: self._edit_selected())
        for title, column_index in (("Progetto", 0), ("Attività", 1), ("Tempo impiegato", 2)):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=column_index)
            column.set_resizable(True)
            column.set_expand(column_index == 1)
            self.tree.append_column(column)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.tree)
        outer.pack_start(scroll, True, True, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer.pack_start(actions, False, False, 0)

        add_button = Gtk.Button(label="Aggiungi voce")
        add_button.connect("clicked", lambda *_: self._add_entry())
        actions.pack_start(add_button, False, False, 0)

        edit_button = Gtk.Button(label="Modifica selezionata")
        edit_button.connect("clicked", lambda *_: self._edit_selected())
        actions.pack_start(edit_button, False, False, 0)

        delete_button = Gtk.Button(label="Elimina selezionata")
        delete_button.connect("clicked", lambda *_: self._delete_selected())
        actions.pack_start(delete_button, False, False, 0)

        markdown_button = Gtk.Button(label="Mostra Markdown")
        markdown_button.connect("clicked", lambda *_: self._show_markdown())
        actions.pack_end(markdown_button, False, False, 0)

        overtime_button = Gtk.Button(label="Straordinari ed EXTRA del mese")
        overtime_button.connect("clicked", lambda *_: self._show_month_overtime())
        actions.pack_end(overtime_button, False, False, 0)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer.pack_start(footer, False, False, 0)
        hint = Gtk.Label(label="Doppio clic su una riga per modificarla. I dati restano disponibili per 24 mesi.")
        hint.set_xalign(0)
        footer.pack_start(hint, True, True, 0)
        close = Gtk.Button(label="Chiudi")
        close.connect("clicked", lambda *_: self.destroy())
        footer.pack_end(close, False, False, 0)

        self.refresh()
        self.show_all()
        place_on_active_monitor(self, 940, 580)
        self.present()

    def _on_destroy(self, *_args) -> None:
        if self.markdown_window and self.markdown_window.get_visible():
            self.markdown_window.destroy()
        if self.app.summary_window is self:
            self.app.summary_window = None

    def _move_day(self, delta: int) -> None:
        self._set_day(self.selected_day + dt.timedelta(days=delta))

    def _set_day(self, day: dt.date) -> None:
        if day > dt.date.today():
            day = dt.date.today()
        self.selected_day = day
        self.refresh()

    def _day_selected(self, combo: Gtk.ComboBoxText) -> None:
        if self._changing_day:
            return
        day_id = combo.get_active_id()
        if not day_id:
            return
        try:
            self.selected_day = dt.date.fromisoformat(day_id)
        except Exception:
            return
        self.refresh()

    def _reload_day_combo(self) -> None:
        self._changing_day = True
        self.day_combo.remove_all()
        stored_days = set(self.app.activity_log.get("days", {}).keys())
        stored_days.add(dt.date.today().isoformat())
        stored_days.add(self.selected_day.isoformat())
        for day_key in sorted(stored_days, reverse=True):
            try:
                day = dt.date.fromisoformat(day_key)
            except Exception:
                continue
            self.day_combo.append(day_key, day.strftime("%d/%m/%Y"))
        self.day_combo.set_active_id(self.selected_day.isoformat())
        self._changing_day = False

    def _selected_row(self) -> Optional[dict]:
        model, tree_iter = self.tree.get_selection().get_selected()
        if tree_iter is None:
            return None
        project = str(model[tree_iter][0])
        return {
            "project": "" if project == "—" else project,
            "activity": str(model[tree_iter][1]),
            "seconds": int(model[tree_iter][3]),
            "editable": bool(model[tree_iter][4]),
            "unclassified": bool(model[tree_iter][5]),
        }

    def _message(self, title: str, message: str, message_type=Gtk.MessageType.INFO) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=message_type,
            buttons=Gtk.ButtonsType.OK,
            text=title,
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def _open_editor(
        self,
        title: str,
        project: str = "",
        activity: str = "",
        seconds: int = 0,
        allow_empty_activity: bool = False,
    ) -> Optional[tuple[str, str, int]]:
        dialog = ActivityEntryDialog(
            self,
            title,
            self.app._project_suggestions(),
            project=project,
            activity=activity,
            seconds=seconds,
        )
        response = dialog.run()
        values = dialog.values() if response == Gtk.ResponseType.OK else None
        dialog.destroy()
        if values is None:
            return None
        new_activity, new_project, new_seconds = values
        if not new_activity and not allow_empty_activity:
            self._message("Attività mancante", "Inserisci un nome per l’attività.", Gtk.MessageType.WARNING)
            return None
        return new_activity, new_project, new_seconds

    def _add_entry(self) -> None:
        values = self._open_editor("Aggiungi attività")
        if values is None:
            return
        activity, project, seconds = values
        self.app.add_manual_activity(self.selected_day, activity, project, seconds)
        self.refresh()

    def _edit_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            self._message("Nessuna selezione", "Seleziona prima una riga da modificare.")
            return
        if not row["editable"]:
            self._message("Voce non modificabile", "Questa riga non può essere modificata.")
            return

        if row["unclassified"]:
            values = self._open_editor(
                "Modifica o classifica il tempo precedente",
                project="",
                activity="",
                seconds=row["seconds"],
                allow_empty_activity=True,
            )
            if values is None:
                return
            activity, project, seconds = values
            changed = self.app.update_unclassified_time(
                self.selected_day,
                activity,
                project,
                seconds,
            )
        else:
            values = self._open_editor(
                "Modifica attività",
                project=row["project"],
                activity=row["activity"],
                seconds=row["seconds"],
            )
            if values is None:
                return
            activity, project, seconds = values
            changed = self.app.edit_manual_activity(
                self.selected_day,
                row["activity"],
                row["project"],
                activity,
                project,
                seconds,
            )

        if not changed:
            self._message("Voce non trovata", "La voce è cambiata nel frattempo. Aggiorna la finestra e riprova.")
        self.refresh()

    def _delete_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            self._message("Nessuna selezione", "Seleziona prima una riga da eliminare.")
            return
        if not row["editable"]:
            self._message("Voce non eliminabile", "Questa riga non può essere eliminata.")
            return
        confirm = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=(
                "Eliminare il tempo precedente non classificato?"
                if row["unclassified"]
                else "Eliminare questa voce?"
            ),
        )
        confirm.format_secondary_text(
            "Il tempo verrà sottratto dal totale di lavoro della giornata e il saldo ore sarà ricalcolato."
        )
        confirm.add_button("Annulla", Gtk.ResponseType.CANCEL)
        confirm.add_button("Elimina", Gtk.ResponseType.OK)
        response = confirm.run()
        confirm.destroy()
        if response != Gtk.ResponseType.OK:
            return
        if row["unclassified"]:
            self.app.delete_unclassified_time(self.selected_day)
        else:
            self.app.delete_manual_activity(
                self.selected_day,
                row["activity"],
                row["project"],
            )
        self.refresh()

    def _show_markdown(self) -> None:
        markdown_text = self.app.build_day_markdown(self.selected_day)
        if self.markdown_window and self.markdown_window.get_visible():
            self.markdown_window.destroy()
        self.markdown_window = MarkdownPreviewWindow(self, markdown_text)

    def _show_month_overtime(self) -> None:
        markdown_text = self.app.build_month_overtime_markdown(
            self.selected_day.year,
            self.selected_day.month,
        )
        if self.markdown_window and self.markdown_window.get_visible():
            self.markdown_window.destroy()
        self.markdown_window = MarkdownPreviewWindow(self, markdown_text)

    def refresh(self) -> None:
        self._reload_day_combo()
        stats = self.app.activity_log.get("days", {}).get(
            self.selected_day.isoformat(),
            {
                "work_seconds": 0,
                "break_seconds": 0,
                "credited_break_seconds": 0,
                "overtime_seconds": 0,
                "activity_totals": [],
            },
        )
        self.date_label.set_text(self.selected_day.strftime("%A %d/%m/%Y").capitalize())
        work = self.app._format_effective_minutes(stats.get("work_seconds", 0))
        pause = self.app._format_effective_minutes(stats.get("break_seconds", 0))
        credited_pause = self.app._format_effective_minutes(stats.get("credited_break_seconds", 0))
        counted = self.app._format_effective_minutes(self.app.daily_counted_seconds(self.selected_day))
        target = self.app._format_effective_minutes(self.app._daily_target_seconds_for(self.selected_day))
        remaining = self.app._format_effective_minutes(self.app.daily_remaining_seconds(self.selected_day))
        balance_before_seconds = self.app.time_balance_before_day_seconds(self.selected_day)
        if bool(stats.get("day_closed", False)):
            balance_after_seconds = self.app.active_time_balance_seconds(self.selected_day)
        else:
            balance_after_seconds = self.app.projected_time_balance_for_day_seconds(self.selected_day)
        balance_before = format_signed_hours_minutes(balance_before_seconds)
        balance_after = format_signed_hours_minutes(balance_after_seconds)
        day_overtime = self.app._format_effective_minutes(stats.get("overtime_seconds", 0))
        special_extra_seconds = self.app.special_day_extra_seconds(self.selected_day)
        weekly_day_extra_seconds = self.app.weekly_extra_for_day_seconds(self.selected_day)
        total_day_extra_seconds = special_extra_seconds + weekly_day_extra_seconds
        special_extra = self.app._format_effective_minutes(special_extra_seconds)
        weekly_day_extra = self.app._format_effective_minutes(weekly_day_extra_seconds)
        total_day_extra = self.app._format_effective_minutes(total_day_extra_seconds)
        week_counted = self.app._format_effective_minutes(
            self.app.regular_week_counted_seconds(self.selected_day)
        )
        week_target = self.app._format_effective_minutes(
            self.app._weekly_target_seconds_for(self.selected_day)
        )
        week_extra = self.app._format_effective_minutes(
            self.app.weekly_extra_seconds(self.selected_day)
        )
        month_overtime = self.app._format_effective_minutes(
            self.app.month_overtime_seconds(self.selected_day.year, self.selected_day.month)
        )
        month_extra = self.app._format_effective_minutes(
            self.app.month_extra_seconds(self.selected_day.year, self.selected_day.month)
        )
        month_special_extra = self.app._format_effective_minutes(
            self.app.month_special_extra_seconds(self.selected_day.year, self.selected_day.month)
        )
        month_closed_balance_extra = self.app._format_effective_minutes(
            self.app.closed_balance_extra_seconds(self.selected_day.year, self.selected_day.month)
        )
        closure_date = self.app._extra_closure_date(self.selected_day.year, self.selected_day.month)
        previous_year, previous_month = self.app.previous_month(
            self.selected_day.year, self.selected_day.month
        )
        previous_overtime = self.app._format_effective_minutes(
            self.app.month_overtime_seconds(previous_year, previous_month)
        )
        previous_extra = self.app._format_effective_minutes(
            self.app.month_extra_seconds(previous_year, previous_month)
        )
        current_month_label = (
            f"{ITALIAN_MONTH_NAMES[self.selected_day.month - 1]} {self.selected_day.year}"
        )
        previous_month_label = f"{ITALIAN_MONTH_NAMES[previous_month - 1]} {previous_year}"
        if self.app._is_special_workday(self.selected_day, stats):
            objective_line = (
                f"Giornata EXTRA: {self.app._special_workday_label(self.selected_day, stats)}    •    "
                f"EXTRA festivo/ferie: {special_extra}"
            )
        elif self.app.day_has_regular_target(self.selected_day):
            objective_line = (
                f"Tempo utile per l’obiettivo: {counted} / {target}    •    Mancano: {remaining}    •    "
                f"Pausa conteggiata nelle ore: {credited_pause}\n"
                f"Saldo iniziale: {balance_before}    •    Saldo dopo la giornata: {balance_after}    •    "
                f"Scelta di chiusura: {str(stats.get('close_choice', '')).strip() or 'non ancora effettuata'}"
            )
        else:
            objective_line = "Nessun obiettivo ordinario previsto per questa giornata"

        self.totals_label.set_text(
            f"Lavoro effettivo: {work}    •    Pause effettive: {pause}    •    "
            f"Straordinario oltre fascia: {day_overtime}\n"
            f"{objective_line}\n"
            f"Settimana ordinaria: {week_counted} / {week_target}    •    "
            f"EXTRA oltre limite settimanale: {week_extra}    •    EXTRA attribuito al giorno: {weekly_day_extra}\n"
            f"EXTRA totale del giorno: {total_day_extra}    •    EXTRA {current_month_label}: {month_extra}    •    "
            f"di cui festivi/ferie: {month_special_extra}\n"
            f"Straordinario oltre fascia {current_month_label}: {month_overtime}    •    "
            f"EXTRA del mese precedente ({previous_month_label}): {previous_extra}    •    "
            f"Straordinario oltre fascia precedente: {previous_overtime}\n"
            f"Saldo ore attivo: {format_signed_hours_minutes(self.app.active_time_balance_seconds())}    •    "
            f"EXTRA da saldo chiuso nel mese: {month_closed_balance_extra}    •    "
            f"Prossima/prevista chiusura: {closure_date.strftime('%d/%m/%Y')}"
        )
        self.store.clear()
        rows = self.app._activity_totals_for(self.selected_day, include_unclassified=True)
        for item in rows:
            seconds = int(item.get("work_seconds", 0))
            unclassified = bool(item.get("unclassified", False))
            editable = bool(str(item.get("text", "")).strip()) or unclassified
            self.store.append(
                [
                    str(item.get("project", "")) or "—",
                    str(item.get("text", "")) or "Tempo non classificato",
                    self.app._format_effective_minutes(seconds),
                    seconds,
                    editable,
                    unclassified,
                ]
            )
        self.tree.set_tooltip_text("Seleziona o fai doppio clic per modificare progetto, attività e durata")


class ClockOverlay(Gtk.Window):
    def __init__(self):
        super().__init__(title="Work timer")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.set_app_paintable(True)
        self.opacity_toggle = False

        self.label = Gtk.Label(label="")
        self.label.get_style_context().add_class("wb-clock")
        self.add(self.label)
        self.hide()

    def update(self, text: str, low: float, high: float) -> None:
        self.label.set_text(text)
        self.opacity_toggle = not self.opacity_toggle
        self.set_opacity(high if self.opacity_toggle else low)
        if not self.get_visible():
            self.show_all()
        self._move_top_right()

    def _move_top_right(self) -> None:
        # Wayland può limitare il posizionamento assoluto: in quel caso il compositor decide.
        display = Gdk.Display.get_default()
        if not display:
            return
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        if not monitor:
            return
        geo = monitor.get_geometry()
        self.resize(150, 34)
        self.move(geo.x + geo.width - 170, geo.y + 18)


class BreakCountdown(Gtk.Window):
    def __init__(self, app: "WorkBreakApp"):
        super().__init__(title="Pausa in corso")
        self.app = app
        self.set_default_size(460, 260)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_border_width(28)
        box.get_style_context().add_class("wb-card")
        self.add(box)

        title = Gtk.Label(label="Pausa attiva")
        title.get_style_context().add_class("wb-title")
        box.pack_start(title, False, False, 0)

        self.timer = Gtk.Label(label="05:00")
        self.timer.get_style_context().add_class("wb-countdown")
        box.pack_start(self.timer, True, True, 0)

        hint = Gtk.Label(label="Alzati, guarda lontano, respira e muoviti un po'.")
        hint.get_style_context().add_class("wb-body")
        hint.set_line_wrap(True)
        hint.set_justify(Gtk.Justification.CENTER)
        box.pack_start(hint, False, False, 0)

        self.show_all()
        self.present()

    def update(self, seconds_left: int) -> None:
        self.timer.set_text(format_mmss(seconds_left))


class MiddayRecoveryWindow(Gtk.Window):
    def __init__(self, app: "WorkBreakApp"):
        super().__init__(title="Recupero pausa mattutina")
        self.app = app
        self.set_default_size(560, 320)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_border_width(28)
        box.get_style_context().add_class("wb-card")
        self.add(box)

        title = Gtk.Label(label="Recupero della pausa mattutina")
        title.get_style_context().add_class("wb-title")
        title.set_line_wrap(True)
        title.set_justify(Gtk.Justification.CENTER)
        box.pack_start(title, False, False, 0)

        self.timer = Gtk.Label(label="00:00")
        self.timer.get_style_context().add_class("wb-countdown")
        box.pack_start(self.timer, True, True, 0)

        self.hint = Gtk.Label(
            label="Il lavoro oltre l’orario mattutino sposta in avanti il rientro. "
            "Puoi interrompere il recupero e ricominciare quando vuoi."
        )
        self.hint.get_style_context().add_class("wb-body")
        self.hint.set_line_wrap(True)
        self.hint.set_justify(Gtk.Justification.CENTER)
        box.pack_start(self.hint, False, False, 0)

        button = Gtk.Button(label="Interrompi e ricomincia a lavorare")
        button.set_size_request(320, 52)
        button.connect("clicked", lambda *_: app.start_afternoon_from_recovery())
        box.pack_start(button, False, False, 0)

        self.show_all()
        place_on_active_monitor(self, 560, 320)
        self.present()

    def update(self, seconds_left: int) -> None:
        self.timer.set_text(format_mmss(seconds_left))
        if seconds_left <= 0:
            self.hint.set_text(
                "La pausa prevista è stata recuperata. Premi il pulsante per indicare che hai ripreso a lavorare."
            )


class DailyCompensationWindow(Gtk.Window):
    def __init__(self, app: "WorkBreakApp"):
        super().__init__(title="Compensazione ore")
        self.app = app
        self.set_default_size(580, 330)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_border_width(28)
        box.get_style_context().add_class("wb-card")
        self.add(box)

        title = Gtk.Label(label="Compensazione post chiusura")
        title.get_style_context().add_class("wb-title")
        title.set_line_wrap(True)
        title.set_justify(Gtk.Justification.CENTER)
        box.pack_start(title, False, False, 0)

        self.timer = Gtk.Label(label="00:00")
        self.timer.get_style_context().add_class("wb-countdown")
        box.pack_start(self.timer, True, True, 0)

        self.hint = Gtk.Label(
            label="Il lavoro continua a essere attribuito all’attività corrente finché il saldo mancante non arriva a zero."
        )
        self.hint.get_style_context().add_class("wb-body")
        self.hint.set_line_wrap(True)
        self.hint.set_justify(Gtk.Justification.CENTER)
        box.pack_start(self.hint, False, False, 0)

        button = Gtk.Button(label="Concludi definitivamente adesso")
        button.set_tooltip_text("Chiude subito la giornata e riporta soltanto il tempo ancora mancante")
        button.set_size_request(330, 52)
        button.connect("clicked", lambda *_: app.finish_daily_compensation_now())
        box.pack_start(button, False, False, 0)

        self.show_all()
        place_on_active_monitor(self, 580, 330)
        self.present()

    def update(self, seconds_left: int) -> None:
        self.timer.set_text(format_signed_hours_minutes(max(0, seconds_left)))
        if seconds_left <= 0:
            self.hint.set_text("Saldo ore compensato. La giornata viene chiusa automaticamente.")



class DayOffEntryDialog(Gtk.Dialog):
    def __init__(self, parent: Gtk.Window, title: str, entry: Optional[dict] = None):
        super().__init__(
            title=title,
            transient_for=parent,
            flags=Gtk.DialogFlags.MODAL,
        )
        self.add_button("Annulla", Gtk.ResponseType.CANCEL)
        self.add_button("Salva", Gtk.ResponseType.OK)
        self.set_default_size(700, 520)
        self.set_border_width(12)

        normalized = normalize_day_off_entry(entry or {})
        today = dt.date.today()
        start_day = dt.date.fromisoformat(normalized["start"]) if normalized else today
        end_day = dt.date.fromisoformat(normalized["end"]) if normalized else today

        content = self.get_content_area()
        content.set_spacing(10)

        form = Gtk.Grid(column_spacing=12, row_spacing=10)
        content.pack_start(form, False, False, 0)

        kind_label = Gtk.Label(label="Tipo")
        kind_label.set_xalign(0)
        form.attach(kind_label, 0, 0, 1, 1)
        self.kind = Gtk.ComboBoxText()
        self.kind.append("vacation", "Ferie / assenza")
        self.kind.append("holiday", "Festività personalizzata")
        self.kind.append("workday", "Giornata lavorativa straordinaria")
        self.kind.set_active_id(normalized["kind"] if normalized else "vacation")
        form.attach(self.kind, 1, 0, 1, 1)

        description_label = Gtk.Label(label="Descrizione")
        description_label.set_xalign(0)
        form.attach(description_label, 0, 1, 1, 1)
        self.description = Gtk.Entry()
        self.description.set_placeholder_text("Esempio: Ferie estive")
        self.description.set_text(normalized["label"] if normalized else "")
        form.attach(self.description, 1, 1, 1, 1)

        self.recurring = Gtk.CheckButton(
            label="Ripeti ogni anno nelle stesse date"
        )
        self.recurring.set_active(bool(normalized and normalized["recurring"]))
        form.attach(self.recurring, 0, 2, 2, 1)

        calendars = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        content.pack_start(calendars, True, True, 0)

        self.start_calendar = Gtk.Calendar()
        self.end_calendar = Gtk.Calendar()
        self._select_calendar_day(self.start_calendar, start_day)
        self._select_calendar_day(self.end_calendar, end_day)

        start_frame = Gtk.Frame(label="Dal giorno")
        start_frame.set_border_width(6)
        start_frame.add(self.start_calendar)
        calendars.pack_start(start_frame, True, True, 0)

        end_frame = Gtk.Frame(label="Al giorno (anche uguale)")
        end_frame.set_border_width(6)
        end_frame.add(self.end_calendar)
        calendars.pack_start(end_frame, True, True, 0)

        note = Gtk.Label(
            label=(
                "Per un solo giorno seleziona la stessa data in entrambi i calendari. "
                "Le ferie non ricorrenti restano legate all’anno scelto; le festività e le "
                "giornate lavorative straordinarie ricorrenti vengono riconosciute automaticamente "
                "anche negli anni successivi."
            )
        )
        note.set_xalign(0)
        note.set_line_wrap(True)
        content.pack_start(note, False, False, 0)
        self.show_all()

    @staticmethod
    def _select_calendar_day(calendar: Gtk.Calendar, day: dt.date) -> None:
        calendar.select_month(day.month - 1, day.year)
        calendar.select_day(day.day)

    @staticmethod
    def _calendar_day(calendar: Gtk.Calendar) -> dt.date:
        year, month_zero_based, day = calendar.get_date()
        return dt.date(int(year), int(month_zero_based) + 1, int(day))

    def values(self) -> Optional[dict]:
        start = self._calendar_day(self.start_calendar)
        end = self._calendar_day(self.end_calendar)
        if end < start:
            start, end = end, start
        if (end - start).days > 366:
            return None
        kind = self.kind.get_active_id() or "vacation"
        label = self.description.get_text().strip()
        if not label:
            default_labels = {
                "vacation": "Ferie",
                "holiday": "Festività personalizzata",
                "workday": "Giornata lavorativa straordinaria",
            }
            label = default_labels.get(kind, "Ferie")
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "label": label,
            "recurring": self.recurring.get_active(),
            "kind": kind,
        }


class DayOffManagerWindow(Gtk.Window):
    def __init__(self, app: "WorkBreakApp"):
        super().__init__(title="Ferie, festività e giornate extra")
        self.app = app
        self.set_default_size(820, 520)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(16)
        self.connect("destroy", self._on_destroy)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(outer)

        title = Gtk.Label(label="Ferie, festività e giornate lavorative extra")
        title.set_xalign(0)
        title.modify_font(Pango.FontDescription("Sans Bold 18"))
        outer.pack_start(title, False, False, 0)

        info = Gtk.Label(
            label=(
                "Aggiungi singoli giorni o intervalli. Puoi anche autorizzare una giornata "
                "festiva, di ferie o normalmente non lavorativa: tutte le ore svolte in quel "
                "giorno saranno conteggiate separatamente come EXTRA."
            )
        )
        info.set_xalign(0)
        info.set_line_wrap(True)
        outer.pack_start(info, False, False, 0)

        # periodo, descrizione, tipo, ricorrenza, start, end, recurring, kind
        self.store = Gtk.ListStore(str, str, str, str, str, str, bool, str)
        self.tree = Gtk.TreeView(model=self.store)
        self.tree.connect("row-activated", lambda *_: self._edit_selected())
        for title_text, index in (
            ("Periodo", 0),
            ("Descrizione", 1),
            ("Tipo", 2),
            ("Ricorrenza", 3),
        ):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title_text, renderer, text=index)
            column.set_resizable(True)
            column.set_expand(index == 1)
            self.tree.append_column(column)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.tree)
        outer.pack_start(scroll, True, True, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer.pack_start(actions, False, False, 0)

        add_button = Gtk.Button(label="Aggiungi data o giornata extra")
        add_button.connect("clicked", lambda *_: self._add_entry())
        actions.pack_start(add_button, False, False, 0)

        edit_button = Gtk.Button(label="Modifica selezionata")
        edit_button.connect("clicked", lambda *_: self._edit_selected())
        actions.pack_start(edit_button, False, False, 0)

        delete_button = Gtk.Button(label="Elimina selezionata")
        delete_button.connect("clicked", lambda *_: self._delete_selected())
        actions.pack_start(delete_button, False, False, 0)

        close_button = Gtk.Button(label="Chiudi")
        close_button.connect("clicked", lambda *_: self.destroy())
        actions.pack_end(close_button, False, False, 0)

        self.refresh()
        self.show_all()
        place_on_active_monitor(self, 820, 520)
        self.present()

    def _on_destroy(self, *_args) -> None:
        if self.app.day_off_window is self:
            self.app.day_off_window = None

    def _selected(self) -> Optional[dict]:
        model, tree_iter = self.tree.get_selection().get_selected()
        if tree_iter is None:
            return None
        return {
            "start": str(model[tree_iter][4]),
            "end": str(model[tree_iter][5]),
            "recurring": bool(model[tree_iter][6]),
            "kind": str(model[tree_iter][7]),
            "label": str(model[tree_iter][1]),
        }

    def _message(self, title: str, message: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text=title,
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def _open_editor(self, title: str, entry: Optional[dict] = None) -> Optional[dict]:
        dialog = DayOffEntryDialog(self, title, entry)
        response = dialog.run()
        values = dialog.values() if response == Gtk.ResponseType.OK else None
        dialog.destroy()
        if response == Gtk.ResponseType.OK and values is None:
            self._message("Intervallo troppo lungo", "L’intervallo massimo consentito è di 366 giorni.")
        return values

    def _save_entries(self, entries: list[dict]) -> None:
        self.app.settings.custom_days_off = entries
        self.app.settings.save()
        self.app.calendar_settings_changed()
        self.refresh()

    def _add_entry(self) -> None:
        values = self._open_editor("Aggiungi data o giornata lavorativa extra")
        if values is None:
            return
        entries = list(self.app.settings.custom_days_off)
        entries.append(values)
        self._save_entries(entries)

    def _edit_selected(self) -> None:
        selected = self._selected()
        if selected is None:
            self._message("Nessuna selezione", "Seleziona prima una voce da modificare.")
            return
        values = self._open_editor("Modifica data o giornata lavorativa extra", selected)
        if values is None:
            return
        entries = list(self.app.settings.custom_days_off)
        for index, item in enumerate(entries):
            if normalize_day_off_entry(item) == normalize_day_off_entry(selected):
                entries[index] = values
                self._save_entries(entries)
                return
        self._message("Voce non trovata", "La voce è cambiata nel frattempo. Aggiorna e riprova.")

    def _delete_selected(self) -> None:
        selected = self._selected()
        if selected is None:
            self._message("Nessuna selezione", "Seleziona prima una voce da eliminare.")
            return
        confirm = Gtk.MessageDialog(
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text="Eliminare questa data?",
        )
        if selected.get("kind") == "workday":
            confirm.format_secondary_text(
                "La data tornerà a essere esclusa se è festiva, di ferie o normalmente non lavorativa."
            )
        else:
            confirm.format_secondary_text(
                "La giornata tornerà a essere considerata lavorativa, se prevista dall’orario."
            )
        confirm.add_button("Annulla", Gtk.ResponseType.CANCEL)
        confirm.add_button("Elimina", Gtk.ResponseType.OK)
        response = confirm.run()
        confirm.destroy()
        if response != Gtk.ResponseType.OK:
            return
        normalized_selected = normalize_day_off_entry(selected)
        entries = [
            item
            for item in self.app.settings.custom_days_off
            if normalize_day_off_entry(item) != normalized_selected
        ]
        self._save_entries(entries)

    def refresh(self) -> None:
        self.store.clear()
        for entry in self.app.settings.custom_days_off:
            normalized = normalize_day_off_entry(entry)
            if normalized is None:
                continue
            start = dt.date.fromisoformat(normalized["start"])
            end = dt.date.fromisoformat(normalized["end"])
            if normalized["recurring"]:
                if start == end:
                    period = start.strftime("%d/%m")
                else:
                    period = f"{start.strftime('%d/%m')} – {end.strftime('%d/%m')}"
            elif start == end:
                period = start.strftime("%d/%m/%Y")
            else:
                period = f"{start.strftime('%d/%m/%Y')} – {end.strftime('%d/%m/%Y')}"
            kind_labels = {
                "vacation": "Ferie / assenza",
                "holiday": "Festività",
                "workday": "Lavorativa EXTRA",
            }
            kind_label = kind_labels.get(normalized["kind"], "Ferie / assenza")
            recurrence_label = "Ogni anno" if normalized["recurring"] else "Solo una volta"
            self.store.append(
                [
                    period,
                    normalized["label"],
                    kind_label,
                    recurrence_label,
                    normalized["start"],
                    normalized["end"],
                    normalized["recurring"],
                    normalized["kind"],
                ]
            )


class SettingsWindow(Gtk.Window):
    def __init__(self, app: "WorkBreakApp"):
        super().__init__(title="Impostazioni WorkBreak Guard")
        self.app = app
        self.set_default_size(680, 860)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(18)
        self.set_keep_above(False)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(outer)

        title = Gtk.Label(label="Impostazioni pause")
        title.set_xalign(0)
        title.modify_font(Pango.FontDescription("Sans Bold 18"))
        outer.pack_start(title, False, False, 0)

        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        grid.set_column_homogeneous(False)
        outer.pack_start(grid, True, True, 0)

        self.enabled = Gtk.CheckButton(label="Promemoria attivo")
        self.enabled.set_active(app.settings.enabled)
        grid.attach(self.enabled, 0, 0, 2, 1)

        self.audio = Gtk.CheckButton(label="Audio attivo, con volume lieve")
        self.audio.set_active(app.settings.audio_enabled)
        grid.attach(self.audio, 0, 1, 2, 1)

        self.skip_holidays = Gtk.CheckButton(label="Non contare le festività nazionali italiane")
        self.skip_holidays.set_active(app.settings.skip_italian_holidays)
        grid.attach(self.skip_holidays, 0, 2, 2, 1)

        self.este_holiday = Gtk.CheckButton(label="Includi Santa Tecla, patrona di Este — 23 settembre")
        self.este_holiday.set_active("este" in app.settings.local_holidays)
        grid.attach(self.este_holiday, 0, 3, 2, 1)

        self.florence_holiday = Gtk.CheckButton(
            label="Includi San Giovanni Battista, patrono di Firenze — 24 giugno"
        )
        self.florence_holiday.set_active("firenze" in app.settings.local_holidays)
        grid.attach(self.florence_holiday, 0, 4, 2, 1)

        self.autostart_enabled = Gtk.CheckButton(label="Avvia automaticamente all'accesso")
        self.autostart_enabled.set_active(is_autostart_enabled())
        grid.attach(self.autostart_enabled, 0, 5, 2, 1)

        self.work_minutes = self._spin(app.settings.work_minutes, 5, 240)
        self.break_minutes = self._spin(app.settings.break_minutes, 1, 60)
        self.daily_target_hours = self._spin(app.settings.daily_target_hours, 1, 24)
        self.warning_seconds = self._spin(app.settings.warning_seconds, 5, 600)
        self.overtime_reminder_minutes = self._spin(app.settings.overtime_reminder_minutes, 1, 120)
        self.extra_closure_day = self._spin(app.settings.extra_closure_day, 1, 28)
        self.extra_closure_weekday = Gtk.ComboBoxText()
        for index, weekday_name in enumerate(
            ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
        ):
            self.extra_closure_weekday.append(str(index), weekday_name)
        self.extra_closure_weekday.set_active_id(str(app.settings.extra_closure_weekday))
        self.beep_count = self._spin(app.settings.beep_count, 0, 20)
        self.beep_interval = self._spin(app.settings.beep_interval_seconds, 5, 300)
        self.volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 30, 1)
        self.volume.set_value(int(app.settings.beep_volume * 100))
        self.volume.set_digits(0)

        row = 6
        row = self._labeled(grid, row, "Minuti lavoro", self.work_minutes)
        row = self._labeled(grid, row, "Minuti pausa", self.break_minutes)
        row = self._labeled(grid, row, "Tempo massimo per giornata, ore", self.daily_target_hours)
        row = self._labeled(grid, row, "Tempo predefinito prima di 'Fermati subito', secondi", self.warning_seconds)
        row = self._labeled(
            grid,
            row,
            "Promemoria lavoro oltre orario, minuti",
            self.overtime_reminder_minutes,
        )
        row = self._labeled(
            grid,
            row,
            "Chiusura mensile EXTRA: giorno base del mese",
            self.extra_closure_day,
        )
        row = self._labeled(
            grid,
            row,
            "Primo giorno uguale o successivo per la chiusura",
            self.extra_closure_weekday,
        )
        row = self._labeled(grid, row, "Numero beep in pausa", self.beep_count)
        row = self._labeled(grid, row, "Distanza beep, secondi", self.beep_interval)
        row = self._labeled(grid, row, "Volume beep 0-30%", self.volume)

        self.morning_start = Gtk.Entry(text=app.settings.morning_start)
        self.morning_end = Gtk.Entry(text=app.settings.morning_end)
        self.afternoon_start = Gtk.Entry(text=app.settings.afternoon_start)
        self.afternoon_end = Gtk.Entry(text=app.settings.afternoon_end)
        row = self._labeled(grid, row, "Mattina inizio HH:MM", self.morning_start)
        row = self._labeled(grid, row, "Mattina fine HH:MM", self.morning_end)
        row = self._labeled(grid, row, "Pomeriggio inizio HH:MM", self.afternoon_start)
        row = self._labeled(grid, row, "Pomeriggio fine HH:MM", self.afternoon_end)

        days_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.days = []
        for idx, name in enumerate(["L", "M", "M", "G", "V", "S", "D"]):
            chk = Gtk.CheckButton(label=name)
            chk.set_active(idx in app.settings.active_days)
            self.days.append(chk)
            days_box.pack_start(chk, False, False, 0)
        row = self._labeled(grid, row, "Giorni attivi", days_box)

        holidays_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.holidays_count = Gtk.Label(
            label=f"{len(app.settings.custom_days_off)} date o intervalli personalizzati"
        )
        self.holidays_count.set_xalign(0)
        holidays_box.pack_start(self.holidays_count, True, True, 0)
        holidays_button = Gtk.Button(label="Gestisci ferie, festività e giornate EXTRA…")
        holidays_button.connect("clicked", lambda *_: app.show_day_off_manager())
        holidays_box.pack_end(holidays_button, False, False, 0)
        row = self._labeled(grid, row, "Calendario e giornate EXTRA", holidays_box)

        self.markdown_include_task_times = Gtk.CheckButton(
            label="Mostra il tempo impiegato per ogni task nel Markdown"
        )
        self.markdown_include_task_times.set_active(app.settings.markdown_include_task_times)
        grid.attach(self.markdown_include_task_times, 0, row, 2, 1)
        row += 1

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        outer.pack_start(controls, False, False, 0)

        save = Gtk.Button(label="Salva")
        save.connect("clicked", self._save)
        controls.pack_start(save, False, False, 0)

        pause = Gtk.Button(label="Pausa/Riattiva ora")
        pause.connect("clicked", lambda *_: app.toggle_enabled())
        controls.pack_start(pause, False, False, 0)

        start_break = Gtk.Button(label="Avvia pausa adesso")
        start_break.connect("clicked", lambda *_: app.force_break_now())
        controls.pack_start(start_break, False, False, 0)

        close = Gtk.Button(label="Chiudi")
        close.connect("clicked", lambda *_: self.destroy())
        controls.pack_end(close, False, False, 0)

        self.show_all()

    def _spin(self, value: int, low: int, high: int) -> Gtk.SpinButton:
        adj = Gtk.Adjustment(value=value, lower=low, upper=high, step_increment=1, page_increment=5)
        spin = Gtk.SpinButton(adjustment=adj, climb_rate=1, digits=0)
        return spin

    def _labeled(self, grid: Gtk.Grid, row: int, text: str, widget: Gtk.Widget) -> int:
        label = Gtk.Label(label=text)
        label.set_xalign(0)
        grid.attach(label, 0, row, 1, 1)
        grid.attach(widget, 1, row, 1, 1)
        return row + 1

    def _save(self, *_args) -> None:
        s = self.app.settings
        s.enabled = self.enabled.get_active()
        s.audio_enabled = self.audio.get_active()
        s.skip_italian_holidays = self.skip_holidays.get_active()
        s.local_holidays = []
        if self.este_holiday.get_active():
            s.local_holidays.append("este")
        if self.florence_holiday.get_active():
            s.local_holidays.append("firenze")
        s.work_minutes = int(self.work_minutes.get_value())
        s.break_minutes = int(self.break_minutes.get_value())
        s.daily_target_hours = int(self.daily_target_hours.get_value())
        s.warning_seconds = int(self.warning_seconds.get_value())
        s.overtime_reminder_minutes = int(self.overtime_reminder_minutes.get_value())
        s.extra_closure_day = int(self.extra_closure_day.get_value())
        s.markdown_include_task_times = self.markdown_include_task_times.get_active()
        try:
            s.extra_closure_weekday = int(self.extra_closure_weekday.get_active_id() or 0)
        except Exception:
            s.extra_closure_weekday = 0
        s.beep_count = int(self.beep_count.get_value())
        s.beep_interval_seconds = int(self.beep_interval.get_value())
        s.beep_volume = float(self.volume.get_value()) / 100.0
        s.morning_start = self.morning_start.get_text()
        s.morning_end = self.morning_end.get_text()
        s.afternoon_start = self.afternoon_start.get_text()
        s.afternoon_end = self.afternoon_end.get_text()
        s.active_days = [idx for idx, chk in enumerate(self.days) if chk.get_active()]
        s.save()
        set_autostart_enabled(self.autostart_enabled.get_active())
        self.app.reload_schedule()
        self.app.update_indicator_menu()
        self.app._update_ui()
        AlertWindow("Salvato", "Le impostazioni sono state aggiornate.", "OK")


class ControlWindow(Gtk.Window):
    def __init__(self, app: "WorkBreakApp"):
        super().__init__(title=APP_NAME)
        self.app = app
        self.set_default_size(430, 190)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(14)
        self.connect("delete-event", self._on_delete)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(box)
        self.status = Gtk.Label(label="")
        self.status.set_xalign(0)
        box.pack_start(self.status, True, True, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.pack_start(row, False, False, 0)
        self.toggle_btn = Gtk.Button(label="Pausa")
        self.toggle_btn.connect("clicked", lambda *_: app.toggle_enabled())
        row.pack_start(self.toggle_btn, True, True, 0)
        settings = Gtk.Button(label="Impostazioni")
        settings.connect("clicked", lambda *_: app.show_settings())
        row.pack_start(settings, True, True, 0)
        quit_btn = Gtk.Button(label="Esci")
        quit_btn.connect("clicked", lambda *_: app.quit())
        row.pack_start(quit_btn, True, True, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.pack_start(actions, False, False, 0)
        activities = Gtk.Button(label="Attività e tempi")
        activities.connect("clicked", lambda *_: app.show_activity_summary())
        actions.pack_start(activities, True, True, 0)
        reset_now = Gtk.Button(label="Resetta e comincia adesso")
        reset_now.connect("clicked", lambda *_: app.reset_and_start_now())
        actions.pack_start(reset_now, True, True, 0)
        self.show_all()

    def _on_delete(self, *_args) -> bool:
        self.hide()
        return True

    def update(self, text: str, enabled: bool) -> None:
        self.status.set_text(text)
        self.toggle_btn.set_label("Pausa" if enabled else "Riattiva")


class WorkBreakApp:
    def __init__(self):
        self.settings = Settings.load()
        self.work_remaining = self.settings.work_minutes * 60
        self.grace_remaining = 0
        self.break_remaining = 0
        self.break_elapsed = 0
        self.waiting_session_start = False
        self.waiting_grace_choice = False
        self.waiting_break_start = False
        self.in_grace = False
        self.in_break = False
        self.waiting_return = False
        self.waiting_session_end = False
        self.in_overtime = False
        self.overtime_seconds = 0
        self.overtime_reminder_remaining = 0
        self.end_prompt_wait_seconds = 0
        self.end_prompt_unaccounted_seconds = 0
        self.end_prompt_is_reminder = False
        self.in_midday_recovery = False
        self.midday_recovery_remaining = 0
        self.midday_recovery_total = 0
        self.afternoon_started_early = False
        self.waiting_daily_close_choice = False
        self.compensating_daily_balance = False
        self.compensation_remaining = 0
        self.compensation_day: Optional[dt.date] = None
        self.break_truncated_by_day_end = False
        self.current_session: Optional[str] = None
        self.current_session_date: Optional[dt.date] = None
        self.current_activity = ""
        self.current_project = ""
        self.stats_save_counter = 0
        self.runtime_save_counter = 0
        self.activity_log = self._load_activity_log()
        self._finalize_unclosed_past_days()
        self._ensure_due_balance_settlements()

        self.warning_window: Optional[Gtk.Window] = None
        self.grace_choice_window: Optional[ChoiceAlertWindow] = None
        self.stop_window: Optional[Gtk.Window] = None
        self.return_window: Optional[Gtk.Window] = None
        self.session_window: Optional[ActivityPromptWindow] = None
        self.activity_window: Optional[ActivityPromptWindow] = None
        self.summary_window: Optional[ActivitySummaryWindow] = None
        self.day_markdown_window: Optional[MarkdownPreviewWindow] = None
        self.day_off_window: Optional[DayOffManagerWindow] = None
        self.session_end_window: Optional[ChoiceAlertWindow] = None
        self.midday_recovery_window: Optional[MiddayRecoveryWindow] = None
        self.daily_close_window: Optional[ChoiceAlertWindow] = None
        self.compensation_window: Optional[DailyCompensationWindow] = None
        # Mantenuti per compatibilità interna, ma i countdown non usano più popup.
        self.break_window: Optional[BreakCountdown] = None
        self.clock = ClockOverlay()
        self.clock.hide()
        self.settings_window: Optional[SettingsWindow] = None
        self.control_window: Optional[ControlWindow] = None
        self.indicator = None
        self.indicator_status_item: Optional[Gtk.MenuItem] = None
        self.indicator_toggle_item: Optional[Gtk.MenuItem] = None
        self.beep_file = self._build_beep_file()

        self._setup_indicator_or_control()
        self._restore_latest_activity()
        now = dt.datetime.now()
        if self._restore_runtime_state(now):
            self.update_indicator_menu()
            self._update_ui()
            GLib.idle_add(self._restore_pending_runtime_window)
        else:
            self._sync_session(now, force=True)
        GLib.timeout_add_seconds(1, self.tick)
        GLib.idle_add(self._show_pending_summary_if_needed)
        signal.signal(signal.SIGINT, lambda *_: self.quit())
        signal.signal(signal.SIGTERM, lambda *_: self.quit())
        if hasattr(signal, "SIGUSR1"):
            signal.signal(signal.SIGUSR1, self._handle_change_activity_signal)
        self._write_pid_file()
        atexit.register(self._save_runtime_state, True)
        atexit.register(self._remove_pid_file)

    def _write_pid_file(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
        except Exception:
            pass

    def _remove_pid_file(self) -> None:
        try:
            if PID_FILE.exists() and PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
                PID_FILE.unlink()
        except Exception:
            pass

    def _handle_change_activity_signal(self, *_args) -> None:
        # I signal Python possono arrivare fuori dal ciclo GTK: rimandiamo l'apertura
        # della finestra al main loop per evitare accessi concorrenti alla UI.
        GLib.idle_add(self.request_activity_prompt)

    def _setup_indicator_or_control(self) -> None:
        if Indicator is not None:
            try:
                self.indicator = Indicator.Indicator.new(
                    APP_ID,
                    "alarm-symbolic",
                    IndicatorCategory.APPLICATION_STATUS,
                )
                self.indicator.set_status(IndicatorStatus.ACTIVE)
                self.update_indicator_menu()
                self._update_indicator_label()
                return
            except Exception:
                self.indicator = None
        self.control_window = ControlWindow(self)
        if self.settings.launch_minimized:
            self.control_window.hide()

    def update_indicator_menu(self) -> None:
        if self.indicator is None:
            return
        menu = Gtk.Menu()
        self.indicator_status_item = Gtk.MenuItem(label=self.status_text())
        self.indicator_status_item.set_sensitive(False)
        menu.append(self.indicator_status_item)

        self.indicator_toggle_item = Gtk.MenuItem(
            label="Pausa promemoria" if self.settings.enabled else "Riattiva promemoria"
        )
        self.indicator_toggle_item.connect("activate", lambda *_: self.toggle_enabled())
        menu.append(self.indicator_toggle_item)

        activity_item = Gtk.MenuItem(label="Cosa stai facendo adesso?")
        activity_item.connect("activate", lambda *_: self.request_activity_prompt())
        menu.append(activity_item)

        reset_now = Gtk.MenuItem(label="Resetta e comincia adesso")
        reset_now.connect("activate", lambda *_: self.reset_and_start_now())
        menu.append(reset_now)

        start_break = Gtk.MenuItem(label="Avvia pausa adesso")
        start_break.connect("activate", lambda *_: self.force_break_now())
        menu.append(start_break)

        if self.compensating_daily_balance:
            finish_now = Gtk.MenuItem(label="Concludi definitivamente adesso")
            finish_now.connect("activate", lambda *_: self.finish_daily_compensation_now())
            menu.append(finish_now)

        summary = Gtk.MenuItem(label="Attività e tempi")
        summary.connect("activate", lambda *_: self.show_activity_summary())
        menu.append(summary)

        markdown_item = Gtk.MenuItem(label="Mostra Markdown")
        markdown_item.connect("activate", lambda *_: self.show_day_markdown())
        menu.append(markdown_item)

        day_offs = Gtk.MenuItem(label="Ferie, festività e giornate EXTRA")
        day_offs.connect("activate", lambda *_: self.show_day_off_manager())
        menu.append(day_offs)

        settings = Gtk.MenuItem(label="Impostazioni")
        settings.connect("activate", lambda *_: self.show_settings())
        menu.append(settings)

        autostart_item = Gtk.MenuItem(
            label="Disabilita avvio automatico" if is_autostart_enabled() else "Abilita avvio automatico"
        )
        autostart_item.connect("activate", lambda *_: self.toggle_autostart())
        menu.append(autostart_item)

        show_window = Gtk.MenuItem(label="Mostra controllo")
        show_window.connect("activate", lambda *_: self.show_control())
        menu.append(show_window)

        quit_item = Gtk.MenuItem(label="Esci")
        quit_item.connect("activate", lambda *_: self.quit())
        menu.append(quit_item)

        menu.show_all()
        self.indicator.set_menu(menu)

    def show_control(self) -> None:
        if self.control_window is None:
            self.control_window = ControlWindow(self)
        self.control_window.show_all()
        self.control_window.present()

    def show_settings(self) -> None:
        if self.settings_window and self.settings_window.get_visible():
            self.settings_window.present()
            return
        self.settings_window = SettingsWindow(self)

    def show_day_off_manager(self) -> None:
        if self.day_off_window and self.day_off_window.get_visible():
            self.day_off_window.present()
            return
        self.day_off_window = DayOffManagerWindow(self)

    def calendar_settings_changed(self) -> None:
        now = dt.datetime.now()
        if self.day_off_reason(now.date()):
            self._save_activity_log()
            self._clear_runtime_state()
            self._reset_runtime_state()
            self.current_session = None
            self.current_session_date = None
        else:
            self._sync_session(now)
        self.update_indicator_menu()
        self._update_ui()
        if self.settings_window and self.settings_window.get_visible():
            try:
                self.settings_window.este_holiday.set_active("este" in self.settings.local_holidays)
                self.settings_window.florence_holiday.set_active("firenze" in self.settings.local_holidays)
                self.settings_window.holidays_count.set_text(
                    f"{len(self.settings.custom_days_off)} date o intervalli personalizzati"
                )
            except Exception:
                pass

    def workday_override_reason(self, day: dt.date) -> Optional[str]:
        return custom_workday_label(day, self.settings.custom_days_off)

    def _base_nonworking_reason(self, day: dt.date) -> Optional[str]:
        """Motivo per cui il giorno è normalmente non lavorativo, indipendentemente dall'override."""
        if day.weekday() not in self.settings.active_days:
            return "Giorno della settimana non lavorativo"
        national = italian_holiday_names(day.year).get(day)
        if national:
            return national
        local = local_holiday_names(day.year, self.settings.local_holidays).get(day)
        if local:
            return local
        custom = custom_day_off_label(day, self.settings.custom_days_off)
        if custom:
            return custom
        return None

    def special_workday_reason(self, day: dt.date) -> Optional[str]:
        """Descrive una giornata lavorata che, per calendario, è festiva/ferie/non lavorativa."""
        base_reason = self._base_nonworking_reason(day)
        if not base_reason:
            return None
        override = self.workday_override_reason(day)
        if override:
            return f"{override} — {base_reason}"
        # Le festività nazionali possono essere abilitate come giornate normali dalle impostazioni,
        # ma le ore svolte restano comunque EXTRA festivo.
        if italian_holiday_names(day.year).get(day) and not self.settings.skip_italian_holidays:
            return base_reason
        return None

    def day_off_reason(self, day: dt.date) -> Optional[str]:
        if self.workday_override_reason(day):
            return None
        if day.weekday() not in self.settings.active_days:
            return "Giorno della settimana non lavorativo"
        if self.settings.skip_italian_holidays:
            national = italian_holiday_names(day.year).get(day)
            if national:
                return national
        local = local_holiday_names(day.year, self.settings.local_holidays).get(day)
        if local:
            return local
        custom = custom_day_off_label(day, self.settings.custom_days_off)
        if custom:
            return custom
        if day.isoformat() in self.settings.custom_holidays:
            return "Festività personalizzata"
        return None

    def show_activity_summary(self, day: Optional[dt.date] = None, mark_shown: bool = False) -> None:
        selected_day = day or dt.date.today()
        if mark_shown:
            stats = self._stats_for(selected_day)
            stats["summary_shown"] = True
            self._save_activity_log()
        if self.summary_window and self.summary_window.get_visible():
            self.summary_window._set_day(selected_day)
            self.summary_window.present()
            return
        self.summary_window = ActivitySummaryWindow(self, selected_day)

    def show_day_markdown(self, day: Optional[dt.date] = None) -> None:
        selected_day = day or dt.date.today()
        markdown_text = self.build_day_markdown(selected_day)
        if self.day_markdown_window and self.day_markdown_window.get_visible():
            self.day_markdown_window.destroy()
        parent: Optional[Gtk.Window] = None
        if self.summary_window and self.summary_window.get_visible():
            parent = self.summary_window
        elif self.control_window and self.control_window.get_visible():
            parent = self.control_window
        elif self.settings_window and self.settings_window.get_visible():
            parent = self.settings_window
        self.day_markdown_window = MarkdownPreviewWindow(parent, markdown_text)

    def toggle_enabled(self) -> None:
        self.settings.enabled = not self.settings.enabled
        self.settings.save()
        if not self.settings.enabled:
            self._save_activity_log()
            self.current_session = None
            self.current_session_date = None
            self._reset_runtime_state()
            self._clear_runtime_state()
        else:
            self.current_session = None
            self.current_session_date = None
            self._sync_session(dt.datetime.now(), force=True)
        self.update_indicator_menu()
        self._update_ui()

    def toggle_autostart(self) -> None:
        set_autostart_enabled(not is_autostart_enabled())
        self.update_indicator_menu()
        self._update_ui()

    def reload_schedule(self) -> None:
        """Rilegge le fasce appena salvate e richiede una nuova conferma."""
        self._ensure_target_snapshot(dt.date.today(), overwrite=True)
        self._save_activity_log()
        self._clear_runtime_state()
        self.current_session = None
        self.current_session_date = None
        self._reset_runtime_state()
        self._sync_session(dt.datetime.now(), force=True)

    def reset_cycle(self, reason: str = "reset") -> None:
        self._clear_runtime_state()
        self.current_session = None
        self.current_session_date = None
        self._reset_runtime_state()
        if self.settings.enabled and self.session_for(dt.datetime.now()):
            self._sync_session(dt.datetime.now(), force=True)

    def reset_and_start_now(self) -> None:
        now = dt.datetime.now()
        session = self.session_for(now) if self.settings.enabled else None
        if (
            session is None
            and self.settings.enabled
            and self.current_session == "afternoon"
            and self.afternoon_started_early
            and self.current_session_date == now.date()
        ):
            session = "afternoon"
        if not self.settings.enabled:
            AlertWindow(
                "Promemoria disattivato",
                "Riattiva prima il promemoria, poi usa ‘Resetta e comincia adesso’.",
                "OK",
            )
            return
        if session is None:
            AlertWindow(
                "Fuori fascia",
                "Il timer può ripartire subito soltanto durante una fascia di lavoro configurata.",
                "OK",
            )
            return

        self._reset_runtime_state()
        self.current_session = session
        self.current_session_date = now.date()
        self.work_remaining = self.settings.work_minutes * 60
        if self.current_activity:
            self.waiting_session_start = False
            self._record_activity(self.current_activity, self.current_project)
        else:
            self.waiting_session_start = True
            self._show_session_start_prompt(session)
        self._save_runtime_state(force=True)
        self.update_indicator_menu()
        self._update_ui()

    def _reset_runtime_state(self) -> None:
        self.work_remaining = self.settings.work_minutes * 60
        self.grace_remaining = 0
        self.break_remaining = 0
        self.break_elapsed = 0
        self.waiting_session_start = False
        self.waiting_grace_choice = False
        self.waiting_break_start = False
        self.in_grace = False
        self.in_break = False
        self.waiting_return = False
        self.waiting_session_end = False
        self.in_overtime = False
        self.overtime_seconds = 0
        self.overtime_reminder_remaining = 0
        self.end_prompt_wait_seconds = 0
        self.end_prompt_unaccounted_seconds = 0
        self.end_prompt_is_reminder = False
        self.in_midday_recovery = False
        self.midday_recovery_remaining = 0
        self.midday_recovery_total = 0
        self.afternoon_started_early = False
        self.waiting_daily_close_choice = False
        self.compensating_daily_balance = False
        self.compensation_remaining = 0
        self.compensation_day = None
        self.break_truncated_by_day_end = False
        for window in [
            self.warning_window,
            self.grace_choice_window,
            self.stop_window,
            self.return_window,
            self.session_window,
            self.activity_window,
            self.break_window,
            self.session_end_window,
            self.midday_recovery_window,
            self.daily_close_window,
            self.compensation_window,
        ]:
            try:
                if window:
                    window.destroy()
            except Exception:
                pass
        self.warning_window = None
        self.grace_choice_window = None
        self.stop_window = None
        self.return_window = None
        self.session_window = None
        self.activity_window = None
        self.break_window = None
        self.session_end_window = None
        self.midday_recovery_window = None
        self.daily_close_window = None
        self.compensation_window = None
        self.clock.hide()

    def _runtime_phase(self) -> str:
        if self.compensating_daily_balance:
            return "daily_compensation"
        if self.waiting_daily_close_choice:
            return "waiting_daily_close_choice"
        if self.in_midday_recovery:
            return "midday_recovery"
        if self.waiting_session_end:
            return "waiting_session_end"
        if self.in_overtime:
            return "overtime"
        if self.waiting_session_start:
            return "waiting_session_start"
        if self.waiting_grace_choice:
            return "waiting_grace_choice"
        if self.waiting_break_start:
            return "waiting_break_start"
        if self.waiting_return:
            return "waiting_return"
        if self.in_break:
            return "break"
        if self.in_grace:
            return "grace"
        return "work"

    def _runtime_state_payload(self) -> Optional[dict]:
        if not self.settings.enabled or self.current_session is None or self.current_session_date is None:
            return None
        return {
            "schema_version": 3,
            "saved_at": dt.datetime.now().isoformat(timespec="seconds"),
            "session": self.current_session,
            "session_date": self.current_session_date.isoformat(),
            "phase": self._runtime_phase(),
            "work_remaining": max(0, int(self.work_remaining)),
            "grace_remaining": max(0, int(self.grace_remaining)),
            "break_remaining": max(0, int(self.break_remaining)),
            "break_elapsed": max(0, int(self.break_elapsed)),
            "overtime_seconds": max(0, int(self.overtime_seconds)),
            "overtime_reminder_remaining": max(0, int(self.overtime_reminder_remaining)),
            "end_prompt_wait_seconds": max(0, int(self.end_prompt_wait_seconds)),
            "end_prompt_unaccounted_seconds": max(0, int(self.end_prompt_unaccounted_seconds)),
            "end_prompt_is_reminder": bool(self.end_prompt_is_reminder),
            "midday_recovery_remaining": max(0, int(self.midday_recovery_remaining)),
            "midday_recovery_total": max(0, int(self.midday_recovery_total)),
            "afternoon_started_early": bool(self.afternoon_started_early),
            "compensation_remaining": max(0, int(self.compensation_remaining)),
            "compensation_day": self.compensation_day.isoformat() if self.compensation_day else "",
            "break_truncated_by_day_end": bool(self.break_truncated_by_day_end),
            "activity": self.current_activity,
            "project": self.current_project,
        }

    def _clear_runtime_state(self) -> None:
        self.runtime_save_counter = 0
        try:
            if RUNTIME_STATE_FILE.exists():
                RUNTIME_STATE_FILE.unlink()
        except Exception:
            pass

    def _save_runtime_state(self, force: bool = False) -> None:
        if not force:
            self.runtime_save_counter += 1
            if self.runtime_save_counter < 5:
                return
        self.runtime_save_counter = 0
        payload = self._runtime_state_payload()
        if payload is None:
            self._clear_runtime_state()
            return
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = RUNTIME_STATE_FILE.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(RUNTIME_STATE_FILE)
        except Exception:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass

    @staticmethod
    def _safe_runtime_seconds(value: object, maximum: int = 86400) -> int:
        try:
            parsed = int(value)
        except Exception:
            return 0
        return max(0, min(parsed, maximum))

    def _restore_runtime_state(self, now: dt.datetime) -> bool:
        if not self.settings.enabled or not RUNTIME_STATE_FILE.exists():
            return False
        try:
            raw = json.loads(RUNTIME_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            self._clear_runtime_state()
            return False
        if not isinstance(raw, dict) or int(raw.get("schema_version", 0)) not in (1, 2, 3):
            self._clear_runtime_state()
            return False

        phase = str(raw.get("phase", "work"))
        valid_phases = {
            "work",
            "waiting_session_start",
            "waiting_grace_choice",
            "waiting_break_start",
            "grace",
            "break",
            "waiting_return",
            "waiting_session_end",
            "overtime",
            "midday_recovery",
            "waiting_daily_close_choice",
            "daily_compensation",
        }
        if phase not in valid_phases:
            self._clear_runtime_state()
            return False

        saved_session = str(raw.get("session", ""))
        saved_date = str(raw.get("session_date", ""))
        if saved_session not in {"morning", "afternoon"} or saved_date != now.date().isoformat():
            self._clear_runtime_state()
            return False

        special_phase = phase in {
            "waiting_session_end",
            "overtime",
            "midday_recovery",
            "waiting_daily_close_choice",
            "daily_compensation",
        }
        scheduled_session = self.session_for(now)
        restored_early_afternoon = bool(raw.get("afternoon_started_early", False))
        if not special_phase and not restored_early_afternoon and scheduled_session != saved_session:
            # Fuori dalla stessa fascia si applica il normale nuovo avvio.
            self._clear_runtime_state()
            return False

        self.current_session = saved_session
        self.current_session_date = now.date()
        self.current_activity = str(raw.get("activity", self.current_activity)).strip()
        self.current_project = str(raw.get("project", self.current_project)).strip()
        self.work_remaining = self._safe_runtime_seconds(
            raw.get("work_remaining", self.settings.work_minutes * 60),
            max(86400, self.settings.work_minutes * 60),
        )
        self.grace_remaining = self._safe_runtime_seconds(raw.get("grace_remaining", 0))
        self.break_remaining = self._safe_runtime_seconds(raw.get("break_remaining", 0))
        self.break_elapsed = self._safe_runtime_seconds(raw.get("break_elapsed", 0), 7 * 86400)
        self.overtime_seconds = self._safe_runtime_seconds(raw.get("overtime_seconds", 0), 7 * 86400)
        self.overtime_reminder_remaining = self._safe_runtime_seconds(
            raw.get("overtime_reminder_remaining", self.settings.overtime_reminder_minutes * 60),
            86400,
        )
        self.end_prompt_wait_seconds = self._safe_runtime_seconds(
            raw.get("end_prompt_wait_seconds", 0), SESSION_END_INACTIVITY_SECONDS
        )
        self.end_prompt_unaccounted_seconds = self._safe_runtime_seconds(
            raw.get("end_prompt_unaccounted_seconds", 0), SESSION_END_INACTIVITY_SECONDS
        )
        self.end_prompt_is_reminder = bool(raw.get("end_prompt_is_reminder", False))
        self.midday_recovery_remaining = self._safe_runtime_seconds(
            raw.get("midday_recovery_remaining", 0), 7 * 86400
        )
        self.midday_recovery_total = self._safe_runtime_seconds(
            raw.get("midday_recovery_total", 0), 7 * 86400
        )
        self.afternoon_started_early = restored_early_afternoon
        self.compensation_remaining = self._safe_runtime_seconds(
            raw.get("compensation_remaining", 0), 14 * 86400
        )
        try:
            compensation_day_text = str(raw.get("compensation_day", ""))
            self.compensation_day = dt.date.fromisoformat(compensation_day_text) if compensation_day_text else None
        except Exception:
            self.compensation_day = now.date()
        self.break_truncated_by_day_end = bool(raw.get("break_truncated_by_day_end", False))

        self.waiting_session_start = phase == "waiting_session_start"
        self.waiting_grace_choice = phase == "waiting_grace_choice"
        self.waiting_break_start = phase == "waiting_break_start"
        self.in_grace = phase == "grace"
        self.in_break = phase == "break"
        self.waiting_return = phase == "waiting_return"
        self.waiting_session_end = phase == "waiting_session_end"
        self.in_overtime = phase == "overtime"
        self.in_midday_recovery = phase == "midday_recovery"
        self.waiting_daily_close_choice = phase == "waiting_daily_close_choice"
        self.compensating_daily_balance = phase == "daily_compensation"
        self._save_runtime_state(force=True)
        return True

    def _restore_pending_runtime_window(self) -> bool:
        if self.compensating_daily_balance:
            self._show_daily_compensation_window()
        elif self.waiting_daily_close_choice:
            self._show_daily_close_choice()
        elif self.in_midday_recovery:
            self._show_midday_recovery_window()
        elif self.waiting_session_end:
            self._show_session_end_prompt(restoring=True)
        elif self.waiting_session_start:
            self._show_session_start_prompt()
        elif self.waiting_grace_choice:
            self._show_grace_choice(restoring=True)
        elif self.waiting_break_start:
            self._show_stop_alert(restoring=True)
        elif self.waiting_return:
            self._show_return_activity_prompt()
        return False

    def force_break_now(self) -> None:
        if self.waiting_daily_close_choice or self.compensating_daily_balance:
            return
        if self.waiting_session_end or self.in_overtime:
            self._finish_session_end(explicit=True)
            return
        if (
            self.in_midday_recovery
            or self.in_break
            or self.waiting_return
            or self.waiting_break_start
            or not self.current_session
            or self.waiting_session_start
        ):
            return
        self.waiting_grace_choice = False
        self._show_stop_alert(immediate=True)

    def tick(self) -> bool:
        now = dt.datetime.now()
        self._ensure_due_balance_settlements(now.date())
        self._sync_session(now)

        if not self.settings.enabled or self.current_session is None:
            self.clock.hide()
            self._update_ui()
            return True

        if self.waiting_daily_close_choice:
            self.clock.hide()
            self._save_runtime_state()
            self._update_ui()
            return True

        if self.compensating_daily_balance:
            day = self.compensation_day or self.current_session_date or now.date()
            self._record_work_second(day, overtime=True)
            self.overtime_seconds += 1
            self.compensation_remaining = self.balance_remaining_for_day_seconds(day)
            if self.compensation_window:
                self.compensation_window.update(self.compensation_remaining)
            if self.compensation_remaining <= 0:
                self._complete_daily_compensation()
                return True
            self._save_runtime_state()
            self._update_ui()
            return True

        if self.in_midday_recovery:
            if self.midday_recovery_remaining > 0:
                self.midday_recovery_remaining = max(0, self.midday_recovery_remaining - 1)
                self._record_break_second(now.date())
            if self.midday_recovery_window:
                self.midday_recovery_window.update(self.midday_recovery_remaining)
            self._save_runtime_state()
            self._update_ui()
            return True

        if self.waiting_session_end:
            self.end_prompt_wait_seconds += 1
            self.end_prompt_unaccounted_seconds += 1
            if self.end_prompt_wait_seconds >= SESSION_END_INACTIVITY_SECONDS:
                self._finish_session_end(explicit=False)
            self._save_runtime_state()
            self._update_ui()
            return True

        if self.in_overtime:
            self.overtime_seconds += 1
            self.overtime_reminder_remaining = max(0, self.overtime_reminder_remaining - 1)
            self._record_work_second(now.date(), overtime=True)
            if self.overtime_reminder_remaining <= 0:
                self._begin_session_end_confirmation(now, reminder=True)
            self._save_runtime_state()
            self._update_ui()
            return True

        if self.waiting_session_start:
            self.clock.hide()
            self._save_runtime_state()
            self._update_ui()
            return True

        if self.waiting_break_start or self.waiting_grace_choice:
            # Finché l'utente non conferma di essersi realmente fermato, il tempo
            # continua a essere lavoro effettivo attribuito all'attività corrente.
            self._record_work_second(now.date())
            self.clock.hide()
            self._save_runtime_state()
            self._update_ui()
            return True

        if self.waiting_return:
            # La pausa effettiva termina solo quando l'utente conferma il rientro.
            self._record_break_second(now.date())
            self._save_runtime_state()
            self._update_ui()
            return True

        if self.in_break:
            self.break_remaining = max(0, self.break_remaining - 1)
            self.break_elapsed += 1
            # Solo la pausa entro il countdown configurato concorre all'obiettivo
            # giornaliero. L'eventuale ritardo successivo resta pausa effettiva,
            # ma non viene considerato come tempo utile per completare le ore.
            self._record_break_second(now.date(), credited=True)
            self._maybe_beep()
            if self.break_remaining <= 0:
                self._finish_break()
            self._save_runtime_state()
            self._update_ui()
            return True

        if self.in_grace:
            self.grace_remaining = max(0, self.grace_remaining - 1)
            self._record_work_second(now.date())
            if self.grace_remaining <= 0:
                self._show_stop_alert()
            self._save_runtime_state()
            self._update_ui()
            return True

        self.work_remaining = max(0, self.work_remaining - 1)
        self._record_work_second(now.date())
        if self.work_remaining <= 0:
            self._show_grace_choice()

        self._save_runtime_state()
        self._update_ui()
        return True

    def session_for(self, now: dt.datetime) -> Optional[str]:
        s = self.settings
        today = now.date()
        override = self.workday_override_reason(today)
        if not override and now.weekday() not in s.active_days:
            return None
        if not override and self.day_off_reason(today):
            return None
        t = now.time()
        morning_start = parse_hhmm(s.morning_start)
        morning_end = parse_hhmm(s.morning_end)
        afternoon_start = parse_hhmm(s.afternoon_start)
        afternoon_end = parse_hhmm(s.afternoon_end)
        if morning_start < morning_end and morning_start <= t < morning_end:
            return "morning"
        if afternoon_start < afternoon_end and afternoon_start <= t < afternoon_end:
            return "afternoon"
        return None

    def is_active_time(self, now: dt.datetime) -> bool:
        return self.session_for(now) is not None

    def _session_boundary(self, session: str, day: dt.date, end: bool = False) -> dt.datetime:
        if session == "morning":
            value = self.settings.morning_end if end else self.settings.morning_start
        else:
            value = self.settings.afternoon_end if end else self.settings.afternoon_start
        return dt.datetime.combine(day, parse_hhmm(value))

    def _midday_break_seconds(self, day: dt.date) -> int:
        morning_end = self._session_boundary("morning", day, end=True)
        afternoon_start = self._session_boundary("afternoon", day, end=False)
        return max(0, int((afternoon_start - morning_end).total_seconds()))

    def _sync_session(self, now: dt.datetime, force: bool = False) -> None:
        if not self.settings.enabled:
            if self.current_session is not None:
                self._clear_runtime_state()
                self._reset_runtime_state()
                self.current_session = None
                self.current_session_date = None
            return

        if self.current_session is not None and self.current_session_date == now.date():
            if self.in_midday_recovery or self.waiting_session_end or self.in_overtime:
                return
            if self.waiting_daily_close_choice or self.compensating_daily_balance:
                return

            session_end = self._session_boundary(self.current_session, now.date(), end=True)
            if now >= session_end:
                if self.current_session == "afternoon" and (self.in_break or self.waiting_return):
                    self._finish_afternoon_while_paused(now.date())
                    return
                self._begin_session_end_confirmation(now)
                return

            if self.current_session == "afternoon" and self.afternoon_started_early:
                return

            if not force and self.session_for(now) == self.current_session:
                return

        new_session = self.session_for(now)
        if (
            not force
            and new_session == self.current_session
            and (new_session is None or self.current_session_date == now.date())
        ):
            return

        old_session = self.current_session
        old_session_date = self.current_session_date
        if old_session is not None:
            self._save_activity_log()
        self._clear_runtime_state()
        self._reset_runtime_state()
        self.current_session = new_session
        self.current_session_date = now.date() if new_session is not None else None

        if old_session == "afternoon" and new_session != "afternoon":
            self.show_daily_summary(old_session_date or now.date(), mark_shown=True)

        if new_session is not None:
            self.work_remaining = self.settings.work_minutes * 60
            self.waiting_session_start = True
            self._show_session_start_prompt(new_session)
            self._save_runtime_state(force=True)
        self.update_indicator_menu()
        self._update_ui()

    def _begin_session_end_confirmation(self, now: dt.datetime, reminder: bool = False) -> None:
        if self.current_session is None or self.current_session_date != now.date():
            return
        if self.waiting_session_end:
            self._show_session_end_prompt()
            return

        if reminder:
            elapsed = 0
        else:
            scheduled_end = self._session_boundary(self.current_session, now.date(), end=True)
            elapsed = max(0, int((now - scheduled_end).total_seconds()))

        self.in_grace = False
        self.waiting_grace_choice = False
        self.waiting_break_start = False
        self.in_break = False
        self.waiting_return = False
        self.waiting_session_start = False
        self.in_overtime = False
        self.waiting_session_end = True
        self.end_prompt_is_reminder = reminder
        self.end_prompt_wait_seconds = elapsed
        self.end_prompt_unaccounted_seconds = elapsed
        self.overtime_reminder_remaining = 0
        self.clock.hide()

        for attr in ("grace_choice_window", "stop_window", "return_window", "session_window", "break_window"):
            window = getattr(self, attr, None)
            try:
                if window:
                    window.destroy()
            except Exception:
                pass
            setattr(self, attr, None)

        if self.end_prompt_wait_seconds >= SESSION_END_INACTIVITY_SECONDS:
            self._finish_session_end(explicit=False)
            return

        self._play_beep_once()
        self._show_session_end_prompt()
        self._save_runtime_state(force=True)
        self._update_ui()

    def _show_session_end_prompt(self, restoring: bool = False) -> None:
        if self.current_session is None:
            return
        if self.session_end_window and self.session_end_window.get_visible():
            self.session_end_window.present()
            return

        morning = self.current_session == "morning"
        period = "mattutino" if morning else "pomeridiano"
        stop_label = "Sono andato in pausa" if morning else "Ho terminato"
        reminder_minutes = self.settings.overtime_reminder_minutes
        if self.end_prompt_is_reminder:
            title = "Stai ancora lavorando?"
            message = (
                f"Sono passati altri {reminder_minutes} minuti oltre l’orario {period}. "
                "Conferma se stai continuando oppure indica che hai terminato. "
                "Senza risposta entro 20 minuti considero come ultimo orario valido questo avviso."
            )
        else:
            title = f"Orario {period} terminato"
            message = (
                f"Stai ancora lavorando? Se continui, te lo ricorderò ogni {reminder_minutes} minuti. "
                "Senza risposta entro 20 minuti considero terminato il lavoro all’orario previsto."
            )
        self.session_end_window = ChoiceAlertWindow(
            title,
            message,
            [
                ("Sto continuando", self._continue_overtime),
                (stop_label, lambda: self._finish_session_end(explicit=True)),
            ],
        )
        if restoring:
            self.session_end_window.present()

    def _continue_overtime(self) -> None:
        pending = max(0, int(self.end_prompt_unaccounted_seconds))
        if pending:
            self._record_work_seconds(self.current_session_date or dt.date.today(), pending, overtime=True)
            self.overtime_seconds += pending
        self.session_end_window = None
        self.waiting_session_end = False
        self.in_overtime = True
        self.end_prompt_wait_seconds = 0
        self.end_prompt_unaccounted_seconds = 0
        self.end_prompt_is_reminder = False
        self.overtime_reminder_remaining = self.settings.overtime_reminder_minutes * 60
        self._save_runtime_state(force=True)
        self._update_ui()

    def _finish_session_end(self, explicit: bool) -> None:
        if self.current_session is None:
            return
        session = self.current_session
        session_day = self.current_session_date or dt.date.today()
        break_elapsed_before_countdown = 0

        if self.waiting_session_end:
            if explicit:
                pending = max(0, int(self.end_prompt_unaccounted_seconds))
                if pending:
                    self._record_work_seconds(session_day, pending, overtime=True)
                    self.overtime_seconds += pending
            else:
                # Nessuna risposta: l’ultimo momento confermato diventa l’inizio reale della pausa.
                break_elapsed_before_countdown = max(0, int(self.end_prompt_wait_seconds))

        try:
            if self.session_end_window:
                self.session_end_window.destroy()
        except Exception:
            pass
        self.session_end_window = None
        self.waiting_session_end = False
        self.in_overtime = False
        self.end_prompt_wait_seconds = 0
        self.end_prompt_unaccounted_seconds = 0
        self.end_prompt_is_reminder = False
        self.overtime_reminder_remaining = 0
        self._save_activity_log()

        if session == "morning":
            self._start_midday_recovery(session_day, break_elapsed_before_countdown)
            return

        self._prepare_end_of_day(session_day, explicit=explicit)

    def _finish_afternoon_while_paused(self, day: dt.date) -> None:
        if self.current_session != "afternoon":
            return
        if self.in_break and self.break_remaining > 0:
            residual = max(0, int(self.break_remaining))
            self.break_remaining = 0
            self.break_elapsed += residual
            self._record_break_seconds(day, residual, credited=True)
        self.in_break = False
        self.waiting_return = False
        self.break_truncated_by_day_end = False
        for attr in ("return_window", "break_window"):
            window = getattr(self, attr, None)
            try:
                if window:
                    window.destroy()
            except Exception:
                pass
            setattr(self, attr, None)
        self._prepare_end_of_day(day, explicit=True)

    def _prepare_end_of_day(self, day: dt.date, explicit: bool) -> None:
        self.waiting_session_end = False
        self.in_overtime = False
        self.in_grace = False
        self.waiting_grace_choice = False
        self.waiting_break_start = False
        self.in_break = False
        self.waiting_return = False
        self.end_prompt_wait_seconds = 0
        self.end_prompt_unaccounted_seconds = 0
        self.overtime_reminder_remaining = 0
        self.break_truncated_by_day_end = False
        self.compensation_day = day
        self.clock.hide()

        for attr in (
            "session_end_window",
            "grace_choice_window",
            "stop_window",
            "return_window",
            "break_window",
        ):
            window = getattr(self, attr, None)
            try:
                if window:
                    window.destroy()
            except Exception:
                pass
            setattr(self, attr, None)

        remaining = self.balance_remaining_for_day_seconds(day)
        if remaining > 0 and explicit and self._day_participates_in_balance(day):
            self.waiting_daily_close_choice = True
            self.compensation_remaining = remaining
            self._show_daily_close_choice()
            self._save_runtime_state(force=True)
            self._update_ui()
            return

        choice = "Posticipato automaticamente" if remaining > 0 else "Giornata completata"
        self._close_day_after_balance(day, choice)

    def _show_daily_close_choice(self) -> None:
        day = self.compensation_day or self.current_session_date or dt.date.today()
        remaining = self.balance_remaining_for_day_seconds(day)
        self.compensation_remaining = remaining
        if remaining <= 0:
            self._close_day_after_balance(day, "Giornata completata")
            return
        if self.daily_close_window and self.daily_close_window.get_visible():
            self.daily_close_window.present()
            return
        missing = format_signed_hours_minutes(remaining)
        self.daily_close_window = ChoiceAlertWindow(
            f"Mancano {missing}",
            "Vuoi compensare il saldo mancante continuando a lavorare dopo la chiusura, "
            "oppure posticiparlo al prossimo giorno lavorativo? Il surplus già accumulato è stato sottratto automaticamente.",
            [
                (f"Compensa {missing} post chiusura", self._start_daily_compensation),
                ("Posticipa al prossimo giorno", self._defer_daily_balance),
            ],
        )

    def _start_daily_compensation(self) -> None:
        day = self.compensation_day or self.current_session_date or dt.date.today()
        self.daily_close_window = None
        self.waiting_daily_close_choice = False
        self.compensating_daily_balance = True
        self.compensation_day = day
        self.compensation_remaining = self.balance_remaining_for_day_seconds(day)
        self.current_session = "afternoon"
        self.current_session_date = day
        self._show_daily_compensation_window()
        self.update_indicator_menu()
        self._save_runtime_state(force=True)
        self._update_ui()

    def _show_daily_compensation_window(self) -> None:
        if self.compensation_window and self.compensation_window.get_visible():
            self.compensation_window.update(self.compensation_remaining)
            self.compensation_window.present()
            return
        self.compensation_window = DailyCompensationWindow(self)
        self.compensation_window.update(self.compensation_remaining)

    def _defer_daily_balance(self) -> None:
        day = self.compensation_day or self.current_session_date or dt.date.today()
        self.daily_close_window = None
        self.waiting_daily_close_choice = False
        self._close_day_after_balance(day, "Posticipato al prossimo giorno lavorativo")

    def finish_daily_compensation_now(self) -> None:
        if not self.compensating_daily_balance:
            return
        day = self.compensation_day or self.current_session_date or dt.date.today()
        self.compensating_daily_balance = False
        try:
            if self.compensation_window:
                self.compensation_window.destroy()
        except Exception:
            pass
        self.compensation_window = None
        self._close_day_after_balance(day, "Concluso manualmente; residuo posticipato")

    def stop_daily_compensation_and_defer(self) -> None:
        # Alias mantenuto per compatibilità con eventuali richiami di versioni precedenti.
        self.finish_daily_compensation_now()

    def _complete_daily_compensation(self) -> None:
        if not self.compensating_daily_balance:
            return
        day = self.compensation_day or self.current_session_date or dt.date.today()
        self.compensating_daily_balance = False
        try:
            if self.compensation_window:
                self.compensation_window.destroy()
        except Exception:
            pass
        self.compensation_window = None
        self._close_day_after_balance(day, "Compensato post chiusura", completed_alert=True)

    def _close_day_after_balance(self, day: dt.date, choice: str, completed_alert: bool = False) -> None:
        self._finalize_balance_day(day, choice)
        self._clear_runtime_state()
        self._reset_runtime_state()
        self.current_session = None
        self.current_session_date = None
        self.show_daily_summary(day, mark_shown=True)
        self.update_indicator_menu()
        self._update_ui()
        if completed_alert:
            AlertWindow(
                "Saldo ore compensato",
                "Il tempo mancante è stato recuperato e la giornata è stata chiusa.",
                "OK",
            )

    def _start_midday_recovery(self, day: dt.date, elapsed_break_seconds: int = 0) -> None:
        total = self._midday_break_seconds(day)
        elapsed = max(0, int(elapsed_break_seconds))
        if elapsed:
            self._record_break_seconds(day, elapsed)

        self._reset_runtime_state()
        self.current_session = "morning"
        self.current_session_date = day
        self.in_midday_recovery = True
        self.midday_recovery_total = total
        self.midday_recovery_remaining = max(0, total - elapsed)
        self._show_midday_recovery_window()
        self._save_runtime_state(force=True)
        self.update_indicator_menu()
        self._update_ui()

    def _show_midday_recovery_window(self) -> None:
        if self.midday_recovery_window and self.midday_recovery_window.get_visible():
            self.midday_recovery_window.update(self.midday_recovery_remaining)
            self.midday_recovery_window.present()
            return
        self.midday_recovery_window = MiddayRecoveryWindow(self)
        self.midday_recovery_window.update(self.midday_recovery_remaining)

    def start_afternoon_from_recovery(self) -> None:
        if not self.in_midday_recovery:
            return
        now = dt.datetime.now()
        try:
            if self.midday_recovery_window:
                self.midday_recovery_window.destroy()
        except Exception:
            pass
        self.midday_recovery_window = None
        self.in_midday_recovery = False
        self.midday_recovery_remaining = 0
        self.midday_recovery_total = 0
        self.current_session = "afternoon"
        self.current_session_date = now.date()
        self.afternoon_started_early = now < self._session_boundary("afternoon", now.date(), end=False)
        self.work_remaining = self.settings.work_minutes * 60
        self.waiting_session_start = False
        if self.current_activity:
            self._record_activity(self.current_activity, self.current_project)
        self._save_runtime_state(force=True)
        self.update_indicator_menu()
        self._update_ui()

    def _session_name(self, session: Optional[str] = None) -> str:
        selected = session or self.current_session
        return "mattina" if selected == "morning" else "pomeriggio"

    def _show_session_start_prompt(self, session: Optional[str] = None) -> None:
        selected = session or self.current_session
        if selected is None:
            return
        if self.session_window and self.session_window.get_visible():
            self.session_window.present()
            return
        self.waiting_session_start = True
        self.session_window = ActivityPromptWindow(
            f"Possiamo iniziare la {self._session_name(selected)}?",
            self.current_activity,
            self.current_project,
            self._recent_activity_options(),
            self._project_suggestions(),
            self._begin_session,
            self._defer_session_start,
            activity_question=(
                "Cosa stai facendo oggi?"
                if selected == "morning"
                else "Cosa stai facendo adesso?"
            ),
        )

    def _defer_session_start(self) -> None:
        self.session_window = None
        self.waiting_session_start = True
        self._save_runtime_state(force=True)
        self._update_ui()

    def _begin_session(self, activity: str, project: str) -> None:
        self.session_window = None
        self.waiting_session_start = False
        self.work_remaining = self.settings.work_minutes * 60
        self._record_activity(activity, project)
        self._save_runtime_state(force=True)
        self._update_ui()

    def request_activity_prompt(self) -> None:
        if self.waiting_daily_close_choice:
            self._show_daily_close_choice()
            return
        if self.in_midday_recovery:
            AlertWindow(
                "Pausa mattutina in corso",
                "Interrompi prima il recupero della pausa per indicare una nuova attività.",
                "OK",
            )
            return
        if self.waiting_session_end:
            self._show_session_end_prompt()
            return
        if self.waiting_session_start:
            self._show_session_start_prompt()
            return
        if self.waiting_return:
            self._show_return_activity_prompt()
            return
        if self.current_session is None:
            AlertWindow(
                "Fuori fascia",
                "Il promemoria attività sarà disponibile quando inizierà la prossima fascia di lavoro.",
                "OK",
            )
            return
        if self.activity_window and self.activity_window.get_visible():
            self.activity_window.present()
            return
        self.activity_window = ActivityPromptWindow(
            "Cosa stai facendo adesso?",
            self.current_activity,
            self.current_project,
            self._recent_activity_options(),
            self._project_suggestions(),
            self._update_current_activity,
            self._dismiss_activity_prompt,
        )

    def _dismiss_activity_prompt(self) -> None:
        self.activity_window = None

    def _update_current_activity(self, activity: str, project: str) -> None:
        self.activity_window = None
        self._record_activity(activity, project)
        self._update_ui()

    def _show_grace_choice(self, restoring: bool = False) -> None:
        if not restoring and (self.waiting_grace_choice or self.in_grace):
            return
        self.waiting_grace_choice = True
        self.work_remaining = 0
        if not restoring:
            self._play_beep_once()
        default_seconds = self.settings.warning_seconds
        default_label = f"Predefinito: {format_mmss(default_seconds)}"
        self.grace_choice_window = ChoiceAlertWindow(
            "Quanto tempo ti serve per concludere?",
            "Scegli l'ultimatum. Dopo la scelta il conto alla rovescia resta soltanto vicino all'icona nella barra di sistema.",
            [
                (default_label, lambda: self._start_grace(default_seconds)),
                ("5 minuti", lambda: self._start_grace(5 * 60)),
                ("10 minuti", lambda: self._start_grace(10 * 60)),
            ],
        )
        self._save_runtime_state(force=True)

    def _start_grace(self, seconds: int) -> None:
        self.grace_choice_window = None
        self.waiting_grace_choice = False
        self.in_grace = True
        self.grace_remaining = max(1, int(seconds))
        self.clock.hide()
        self._save_runtime_state(force=True)
        self._update_ui()

    def _show_stop_alert(self, immediate: bool = False, restoring: bool = False) -> None:
        self.in_grace = False
        self.waiting_grace_choice = False
        self.waiting_break_start = True
        self.grace_remaining = 0
        self.clock.hide()
        if not restoring:
            self._play_beep_once()
        try:
            if self.warning_window:
                self.warning_window.destroy()
            if self.grace_choice_window:
                self.grace_choice_window.destroy()
        except Exception:
            pass
        self.warning_window = None
        self.grace_choice_window = None
        if self.stop_window:
            try:
                self.stop_window.destroy()
            except Exception:
                pass
        prefix = "Pausa avviata manualmente." if immediate else "Il tempo scelto è terminato."
        self.stop_window = AlertWindow(
            "Fermati subito!",
            f"{prefix}\nAlzati ora: quando premi il pulsante parte il tempo di pausa, visibile nella barra di sistema.",
            "Ho iniziato la pausa",
            self.start_break,
        )
        self._save_runtime_state(force=True)

    def start_break(self) -> None:
        self.waiting_break_start = False
        self.in_break = True
        configured_break = self.settings.break_minutes * 60
        self.break_truncated_by_day_end = False
        if self.current_session == "afternoon" and self.current_session_date == dt.date.today():
            seconds_to_close = max(
                0,
                int(
                    math.ceil(
                        (
                            self._session_boundary("afternoon", dt.date.today(), end=True)
                            - dt.datetime.now()
                        ).total_seconds()
                    )
                ),
            )
            if seconds_to_close < configured_break:
                self.break_truncated_by_day_end = True
                self.break_remaining = seconds_to_close
            else:
                self.break_remaining = configured_break
        else:
            self.break_remaining = configured_break
        self.break_elapsed = 0
        try:
            if self.stop_window:
                self.stop_window.destroy()
        except Exception:
            pass
        self.stop_window = None
        # Nessuna finestra countdown: il tempo resta sempre accanto all'icona.
        self.break_window = None
        self._play_beep_once()
        if self.break_remaining <= 0 and self.current_session == "afternoon":
            self.in_break = False
            self._prepare_end_of_day(self.current_session_date or dt.date.today(), explicit=True)
            return
        self._save_runtime_state(force=True)
        self._update_ui()

    def _finish_break(self) -> None:
        if self.break_truncated_by_day_end and self.current_session == "afternoon":
            self.in_break = False
            self.break_remaining = 0
            self._prepare_end_of_day(self.current_session_date or dt.date.today(), explicit=True)
            return
        self.in_break = False
        self.waiting_return = True
        self.break_remaining = 0
        self._play_beep_once()
        self._save_runtime_state(force=True)
        self._show_return_activity_prompt()

    def _show_return_activity_prompt(self) -> None:
        if self.return_window and self.return_window.get_visible():
            self.return_window.present()
            return
        self.return_window = ActivityPromptWindow(
            "Pausa finita — cosa stai facendo?",
            self.current_activity,
            self.current_project,
            self._recent_activity_options(),
            self._project_suggestions(),
            self.returned_from_break,
            self._defer_return,
        )

    def _defer_return(self) -> None:
        self.return_window = None
        self.waiting_return = True
        self._save_runtime_state(force=True)
        self._update_ui()

    def returned_from_break(self, activity: str, project: str) -> None:
        self.waiting_return = False
        self.work_remaining = self.settings.work_minutes * 60
        self.break_elapsed = 0
        try:
            if self.return_window:
                self.return_window.destroy()
        except Exception:
            pass
        self.return_window = None
        self._record_activity(activity, project)
        self._save_runtime_state(force=True)
        self._update_ui()

    def _maybe_beep(self) -> None:
        s = self.settings
        if not s.audio_enabled or s.beep_count <= 0:
            return
        if self.break_elapsed <= 0:
            return
        if self.break_elapsed % s.beep_interval_seconds == 0:
            beep_index = self.break_elapsed // s.beep_interval_seconds
            if beep_index < s.beep_count:
                self._play_beep_once()

    def _build_beep_file(self) -> Path:
        path = Path(tempfile.gettempdir()) / f"{APP_ID}-soft-beep.wav"
        rate = 44100
        duration = 0.18
        freq = 740.0
        amplitude = max(0.01, min(self.settings.beep_volume, 0.30))
        samples = int(rate * duration)
        with wave.open(str(path), "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            frames = bytearray()
            for i in range(samples):
                env = min(i / (rate * 0.025), 1.0, (samples - i) / (rate * 0.040))
                val = int(32767 * amplitude * env * math.sin(2 * math.pi * freq * i / rate))
                frames.extend(val.to_bytes(2, byteorder="little", signed=True))
            wav.writeframes(bytes(frames))
        return path

    def _play_beep_once(self) -> None:
        if not self.settings.audio_enabled:
            return
        self.beep_file = self._build_beep_file()
        player = shutil.which("paplay") or shutil.which("aplay")
        if player:
            try:
                subprocess.Popen(
                    [player, str(self.beep_file)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return
            except Exception:
                pass
        try:
            Gdk.beep()
        except Exception:
            pass

    def _load_activity_log(self) -> dict:
        raw: dict = {
            "schema_version": 5,
            "days": {},
            "projects": {},
            "balance_enabled_from": dt.date.today().isoformat(),
            "balance_settlements": {},
        }
        try:
            loaded = json.loads(ACTIVITY_LOG_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("days", {}), dict):
                raw = loaded
        except Exception:
            pass

        raw["schema_version"] = 5
        raw.setdefault("days", {})
        if not isinstance(raw.get("balance_settlements"), dict):
            raw["balance_settlements"] = {}
        try:
            dt.date.fromisoformat(str(raw.get("balance_enabled_from", "")))
        except Exception:
            raw["balance_enabled_from"] = dt.date.today().isoformat()
        projects = raw.get("projects", {})
        if isinstance(projects, list):
            projects = {
                str(name).strip().casefold(): {"name": str(name).strip(), "last_used": ""}
                for name in projects
                if str(name).strip()
            }
        if not isinstance(projects, dict):
            projects = {}
        raw["projects"] = projects

        for day_key, stats in list(raw["days"].items()):
            if not isinstance(stats, dict):
                raw["days"].pop(day_key, None)
                continue
            stats.setdefault("work_seconds", 0)
            stats.setdefault("break_seconds", 0)
            stats.setdefault("credited_break_seconds", 0)
            stats.setdefault("overtime_seconds", 0)
            stats.setdefault("special_workday", False)
            stats.setdefault("special_workday_label", "")
            stats.setdefault("activities", [])
            stats.setdefault("activity_totals", [])
            stats.setdefault("summary_shown", False)
            stats.setdefault("day_closed", False)
            stats.setdefault("close_choice", "")
            stats.setdefault("balance_delta_seconds", None)
            if not isinstance(stats["activities"], list):
                stats["activities"] = []
            if not isinstance(stats["activity_totals"], list):
                stats["activity_totals"] = []
            for entry in stats["activities"]:
                if isinstance(entry, dict):
                    entry.setdefault("project", "")
                    project = str(entry.get("project", "")).strip()
                    if project:
                        key = project.casefold()
                        current = projects.get(key, {}) if isinstance(projects.get(key), dict) else {}
                        projects[key] = {
                            "name": project,
                            "last_used": max(str(current.get("last_used", "")), str(entry.get("time", ""))),
                        }
            for item in stats["activity_totals"]:
                if isinstance(item, dict):
                    item.setdefault("project", "")
                    item.setdefault("text", "")
                    item.setdefault("work_seconds", 0)
                    item.setdefault("last_used", "")
                    project = str(item.get("project", "")).strip()
                    if project:
                        key = project.casefold()
                        current = projects.get(key, {}) if isinstance(projects.get(key), dict) else {}
                        projects[key] = {
                            "name": project,
                            "last_used": max(str(current.get("last_used", "")), str(item.get("last_used", ""))),
                        }
        return raw

    def _save_activity_log(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        days = self.activity_log.setdefault("days", {})
        # Conserva due anni di attività e progetti: memoria utile per molti mesi senza crescita illimitata.
        for key in sorted(days)[:-730]:
            days.pop(key, None)
        for stats in days.values():
            if isinstance(stats, dict) and isinstance(stats.get("activities"), list):
                stats["activities"] = stats["activities"][-500:]
        tmp = ACTIVITY_LOG_FILE.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self.activity_log, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(ACTIVITY_LOG_FILE)
            self.stats_save_counter = 0
        except Exception:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass

    def _stats_for(self, day: dt.date) -> dict:
        days = self.activity_log.setdefault("days", {})
        stats = days.setdefault(
            day.isoformat(),
            {
                "work_seconds": 0,
                "break_seconds": 0,
                "credited_break_seconds": 0,
                "overtime_seconds": 0,
                "special_workday": False,
                "special_workday_label": "",
                "activities": [],
                "activity_totals": [],
                "summary_shown": False,
                "day_closed": False,
                "close_choice": "",
                "balance_delta_seconds": None,
            },
        )
        stats.setdefault("work_seconds", 0)
        stats.setdefault("break_seconds", 0)
        stats.setdefault("credited_break_seconds", 0)
        stats.setdefault("overtime_seconds", 0)
        stats.setdefault("special_workday", False)
        stats.setdefault("special_workday_label", "")
        stats.setdefault("activities", [])
        stats.setdefault("activity_totals", [])
        stats.setdefault("summary_shown", False)
        stats.setdefault("day_closed", False)
        stats.setdefault("close_choice", "")
        stats.setdefault("balance_delta_seconds", None)
        special_reason = self.special_workday_reason(day)
        if special_reason:
            stats["special_workday"] = True
            stats["special_workday_label"] = special_reason
        return stats

    def _ensure_target_snapshot(self, day: dt.date, stats: Optional[dict] = None, overwrite: bool = False) -> dict:
        stats = stats or self._stats_for(day)
        daily_target = self.settings.daily_target_hours * 3600
        weekly_target = daily_target * len(self.settings.active_days)
        if overwrite or "daily_target_seconds" not in stats:
            stats["daily_target_seconds"] = daily_target
        if overwrite or "weekly_target_seconds" not in stats:
            stats["weekly_target_seconds"] = weekly_target
        if overwrite or "active_days_snapshot" not in stats:
            stats["active_days_snapshot"] = list(self.settings.active_days)
        return stats

    def _daily_target_seconds_for(self, day: dt.date) -> int:
        stats = self.activity_log.get("days", {}).get(day.isoformat(), {})
        try:
            value = int(stats.get("daily_target_seconds", self.settings.daily_target_hours * 3600))
        except Exception:
            value = self.settings.daily_target_hours * 3600
        return max(0, value)

    def _weekly_target_seconds_for(self, day: dt.date) -> int:
        stats = self.activity_log.get("days", {}).get(day.isoformat(), {})
        default = self.settings.daily_target_hours * 3600 * len(self.settings.active_days)
        try:
            value = int(stats.get("weekly_target_seconds", default))
        except Exception:
            value = default
        return max(0, value)

    def _is_special_workday(self, day: dt.date, stats: Optional[dict] = None) -> bool:
        stats = stats or self.activity_log.get("days", {}).get(day.isoformat(), {})
        if bool(stats.get("special_workday", False)):
            return True
        return bool(self._base_nonworking_reason(day)) and int(stats.get("work_seconds", 0)) > 0

    def _special_workday_label(self, day: dt.date, stats: Optional[dict] = None) -> str:
        stats = stats or self.activity_log.get("days", {}).get(day.isoformat(), {})
        stored = str(stats.get("special_workday_label", "")).strip()
        if stored:
            return stored
        return self._base_nonworking_reason(day) or "Giornata non lavorativa"

    def daily_counted_seconds(self, day: dt.date) -> int:
        """Tempo utile per l'obiettivo: lavoro + sola pausa terminata entro il countdown."""
        stats = self.activity_log.get("days", {}).get(day.isoformat(), {})
        work = max(0, int(stats.get("work_seconds", 0)))
        credited_break = max(0, int(stats.get("credited_break_seconds", 0)))
        return work + credited_break

    def _balance_activation_day(self) -> dt.date:
        try:
            return dt.date.fromisoformat(str(self.activity_log.get("balance_enabled_from", "")))
        except Exception:
            today = dt.date.today()
            self.activity_log["balance_enabled_from"] = today.isoformat()
            return today

    def _day_participates_in_balance(self, day: dt.date) -> bool:
        return day >= self._balance_activation_day() and self.day_has_regular_target(day)

    def _daily_balance_delta_now(self, day: dt.date) -> int:
        if not self._day_participates_in_balance(day):
            return 0
        return self.daily_counted_seconds(day) - self._daily_target_seconds_for(day)

    def _stored_balance_delta(self, day: dt.date) -> int:
        stats = self.activity_log.get("days", {}).get(day.isoformat(), {})
        if not bool(stats.get("day_closed", False)):
            return 0
        try:
            value = stats.get("balance_delta_seconds")
            if value is None:
                return self._daily_balance_delta_now(day)
            return int(value)
        except Exception:
            return self._daily_balance_delta_now(day)

    def _extra_closure_date(self, year: int, month: int) -> dt.date:
        base = dt.date(year, month, self.settings.extra_closure_day)
        offset = (self.settings.extra_closure_weekday - base.weekday()) % 7
        return base + dt.timedelta(days=offset)

    @staticmethod
    def _iter_months(start: dt.date, end: dt.date):
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            yield year, month
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1

    def _settled_balance_seconds_through(self, day: dt.date) -> int:
        total = 0
        settlements = self.activity_log.get("balance_settlements", {})
        if not isinstance(settlements, dict):
            return 0
        for settlement in settlements.values():
            if not isinstance(settlement, dict):
                continue
            try:
                closure_day = dt.date.fromisoformat(str(settlement.get("closure_date", "")))
            except Exception:
                continue
            if closure_day <= day:
                total += max(0, int(settlement.get("closed_extra_seconds", 0)))
        return total

    def active_time_balance_seconds(self, through_day: Optional[dt.date] = None) -> int:
        through = through_day or dt.date.today()
        total = 0
        for day_key in self.activity_log.get("days", {}):
            try:
                day = dt.date.fromisoformat(day_key)
            except Exception:
                continue
            if day > through:
                continue
            total += self._stored_balance_delta(day)
        return total - self._settled_balance_seconds_through(through)

    def time_balance_before_day_seconds(self, day: dt.date) -> int:
        total = 0
        for day_key in self.activity_log.get("days", {}):
            try:
                stored_day = dt.date.fromisoformat(day_key)
            except Exception:
                continue
            if stored_day < day:
                total += self._stored_balance_delta(stored_day)
        # Una chiusura programmata per l'inizio di questa giornata deve essere
        # già applicata al saldo disponibile prima di iniziare a lavorare.
        return total - self._settled_balance_seconds_through(day)

    def projected_time_balance_for_day_seconds(self, day: dt.date) -> int:
        return self.time_balance_before_day_seconds(day) + self._daily_balance_delta_now(day)

    def balance_remaining_for_day_seconds(self, day: dt.date) -> int:
        if not self._day_participates_in_balance(day):
            return 0
        return max(0, -self.projected_time_balance_for_day_seconds(day))

    def closed_balance_extra_seconds(self, year: int, month: int) -> int:
        settlement = self.activity_log.get("balance_settlements", {}).get(f"{year:04d}-{month:02d}", {})
        if not isinstance(settlement, dict):
            return 0
        return max(0, int(settlement.get("closed_extra_seconds", 0)))

    def _ensure_due_balance_settlements(self, today: Optional[dt.date] = None) -> None:
        today = today or dt.date.today()
        activation = self._balance_activation_day()
        settlements = self.activity_log.setdefault("balance_settlements", {})
        changed = False
        for year, month in self._iter_months(activation, today):
            period_key = f"{year:04d}-{month:02d}"
            if period_key in settlements:
                continue
            closure_day = self._extra_closure_date(year, month)
            if closure_day > today:
                continue
            balance_before_closure = self.active_time_balance_seconds(
                closure_day - dt.timedelta(days=1)
            )
            settlements[period_key] = {
                "closure_date": closure_day.isoformat(),
                "closed_extra_seconds": max(0, balance_before_closure),
                "weekday": self.settings.extra_closure_weekday,
                "base_day": self.settings.extra_closure_day,
            }
            changed = True
        if changed:
            self._save_activity_log()

    def _finalize_balance_day(self, day: dt.date, choice: str) -> None:
        stats = self._stats_for(day)
        self._ensure_target_snapshot(day, stats)
        stats["day_closed"] = True
        stats["close_choice"] = choice
        stats["balance_delta_seconds"] = self._daily_balance_delta_now(day)
        stats["summary_shown"] = False
        self._save_activity_log()
        self._ensure_due_balance_settlements(day)

    def _refresh_closed_balance_delta(self, day: dt.date) -> None:
        stats = self.activity_log.get("days", {}).get(day.isoformat(), {})
        if not isinstance(stats, dict) or not bool(stats.get("day_closed", False)):
            return
        stats["balance_delta_seconds"] = self._daily_balance_delta_now(day)

    def _finalize_unclosed_past_days(self, today: Optional[dt.date] = None) -> None:
        today = today or dt.date.today()
        changed = False
        for day_key, stats in self.activity_log.get("days", {}).items():
            if not isinstance(stats, dict):
                continue
            try:
                day = dt.date.fromisoformat(day_key)
            except Exception:
                continue
            if day >= today or not self._day_participates_in_balance(day):
                continue
            has_data = int(stats.get("work_seconds", 0)) + int(stats.get("break_seconds", 0)) > 0
            if has_data and not bool(stats.get("day_closed", False)):
                self._ensure_target_snapshot(day, stats)
                stats["day_closed"] = True
                stats["close_choice"] = "Chiusura automatica al riavvio"
                stats["balance_delta_seconds"] = self._daily_balance_delta_now(day)
                changed = True
        if changed:
            self._save_activity_log()

    def day_has_regular_target(self, day: dt.date) -> bool:
        return day.weekday() in self.settings.active_days and self._base_nonworking_reason(day) is None

    def daily_remaining_seconds(self, day: dt.date) -> int:
        if not self.day_has_regular_target(day):
            return 0
        if self._day_participates_in_balance(day):
            return self.balance_remaining_for_day_seconds(day)
        return max(0, self._daily_target_seconds_for(day) - self.daily_counted_seconds(day))

    @staticmethod
    def _week_start(day: dt.date) -> dt.date:
        return day - dt.timedelta(days=day.weekday())

    def regular_week_counted_seconds(self, day: dt.date, through_day: Optional[dt.date] = None) -> int:
        start = self._week_start(day)
        end = start + dt.timedelta(days=6)
        if through_day is not None:
            end = min(end, through_day)
        total = 0
        cursor = start
        while cursor <= end:
            stats = self.activity_log.get("days", {}).get(cursor.isoformat(), {})
            if not self._is_special_workday(cursor, stats):
                total += max(0, int(stats.get("work_seconds", 0)))
                total += max(0, int(stats.get("credited_break_seconds", 0)))
            cursor += dt.timedelta(days=1)
        return total

    def weekly_extra_seconds(self, day: dt.date) -> int:
        total = self.regular_week_counted_seconds(day)
        return max(0, total - self._weekly_target_seconds_for(day))

    def weekly_extra_for_day_seconds(self, day: dt.date) -> int:
        start = self._week_start(day)
        if day <= start:
            before = 0
        else:
            before = self.regular_week_counted_seconds(day, day - dt.timedelta(days=1))
        through = self.regular_week_counted_seconds(day, day)
        target = self._weekly_target_seconds_for(day)
        return max(0, through - target) - max(0, before - target)

    def special_day_extra_seconds(self, day: dt.date) -> int:
        stats = self.activity_log.get("days", {}).get(day.isoformat(), {})
        if not self._is_special_workday(day, stats):
            return 0
        return max(0, int(stats.get("work_seconds", 0)))

    def total_extra_for_day_seconds(self, day: dt.date) -> int:
        return self.special_day_extra_seconds(day) + self.weekly_extra_for_day_seconds(day)

    def month_extra_seconds(self, year: int, month: int) -> int:
        total = 0
        for day_key in self.activity_log.get("days", {}):
            try:
                day = dt.date.fromisoformat(day_key)
            except Exception:
                continue
            if day.year == year and day.month == month:
                total += self.total_extra_for_day_seconds(day)
        return total

    def month_special_extra_seconds(self, year: int, month: int) -> int:
        total = 0
        for day_key in self.activity_log.get("days", {}):
            try:
                day = dt.date.fromisoformat(day_key)
            except Exception:
                continue
            if day.year == year and day.month == month:
                total += self.special_day_extra_seconds(day)
        return total

    def month_weekly_extra_seconds(self, year: int, month: int) -> int:
        total = 0
        for day_key in self.activity_log.get("days", {}):
            try:
                day = dt.date.fromisoformat(day_key)
            except Exception:
                continue
            if day.year == year and day.month == month:
                total += self.weekly_extra_for_day_seconds(day)
        return total

    def daily_progress_text(self, day: dt.date) -> str:
        stats = self.activity_log.get("days", {}).get(day.isoformat(), {})
        if self._is_special_workday(day, stats):
            extra = self.special_day_extra_seconds(day)
            return (
                f"Giornata EXTRA ({self._special_workday_label(day, stats)}): "
                f"{self._format_effective_minutes(extra)}"
            )
        if not self.day_has_regular_target(day):
            return ""
        counted = self.daily_counted_seconds(day)
        target = self._daily_target_seconds_for(day)
        remaining = max(0, target - counted)
        balance_before = self.time_balance_before_day_seconds(day)
        balance_after = self.projected_time_balance_for_day_seconds(day)
        balance_remaining = self.balance_remaining_for_day_seconds(day)
        if balance_remaining > 0:
            return (
                f"Obiettivo giornaliero: {self._format_effective_minutes(counted)} di "
                f"{self._format_effective_minutes(target)} — saldo iniziale "
                f"{format_signed_hours_minutes(balance_before)} — mancano "
                f"{format_signed_hours_minutes(balance_remaining)}"
            )
        if balance_after > 0:
            return (
                "Obiettivo giornaliero completato — saldo disponibile "
                f"{format_signed_hours_minutes(balance_after)}"
            )
        return "Obiettivo giornaliero completato"

    @staticmethod
    def _same_activity(item: dict, activity: str, project: str) -> bool:
        return (
            str(item.get("text", "")).strip().casefold() == activity.strip().casefold()
            and str(item.get("project", "")).strip().casefold() == project.strip().casefold()
        )

    def _activity_total_entry(self, stats: dict, activity: str, project: str, create: bool = True) -> Optional[dict]:
        activity = activity.strip()
        project = project.strip()
        totals = stats.setdefault("activity_totals", [])
        for item in totals:
            if isinstance(item, dict) and self._same_activity(item, activity, project):
                return item
        if not create or not activity:
            return None
        item = {
            "text": activity,
            "project": project,
            "work_seconds": 0,
            "last_used": dt.datetime.now().isoformat(timespec="seconds"),
        }
        totals.append(item)
        return item

    def _touch_stats(self) -> None:
        self.stats_save_counter += 1
        if self.stats_save_counter >= 30:
            self._save_activity_log()

    def _record_work_second(self, day: dt.date, overtime: bool = False) -> None:
        self._record_work_seconds(day, 1, overtime=overtime)

    def _record_work_seconds(self, day: dt.date, seconds: int, overtime: bool = False) -> None:
        seconds = max(0, int(seconds))
        if seconds <= 0:
            return
        stats = self._stats_for(day)
        self._ensure_target_snapshot(day, stats)
        stats["work_seconds"] = int(stats.get("work_seconds", 0)) + seconds
        if overtime:
            stats["overtime_seconds"] = int(stats.get("overtime_seconds", 0)) + seconds
        stats["summary_shown"] = False
        if self.current_activity:
            item = self._activity_total_entry(stats, self.current_activity, self.current_project)
            if item is not None:
                item["work_seconds"] = int(item.get("work_seconds", 0)) + seconds
                item["last_used"] = dt.datetime.now().isoformat(timespec="seconds")
        self._refresh_closed_balance_delta(day)
        if seconds == 1:
            self._touch_stats()
        else:
            self._save_activity_log()
        if self.summary_window and self.summary_window.get_visible() and self.stats_save_counter % 5 == 0:
            self.summary_window.refresh()

    def _record_break_second(self, day: dt.date, credited: bool = False) -> None:
        self._record_break_seconds(day, 1, credited=credited)

    def _record_break_seconds(self, day: dt.date, seconds: int, credited: bool = False) -> None:
        seconds = max(0, int(seconds))
        if seconds <= 0:
            return
        stats = self._stats_for(day)
        self._ensure_target_snapshot(day, stats)
        stats["break_seconds"] = int(stats.get("break_seconds", 0)) + seconds
        if credited:
            stats["credited_break_seconds"] = int(stats.get("credited_break_seconds", 0)) + seconds
        stats["summary_shown"] = False
        self._refresh_closed_balance_delta(day)
        if seconds == 1:
            self._touch_stats()
        else:
            self._save_activity_log()
        if self.summary_window and self.summary_window.get_visible() and self.stats_save_counter % 5 == 0:
            self.summary_window.refresh()

    def _remember_project(self, project: str) -> None:
        project = project.strip()
        if not project:
            return
        projects = self.activity_log.setdefault("projects", {})
        projects[project.casefold()] = {
            "name": project,
            "last_used": dt.datetime.now().isoformat(timespec="seconds"),
        }

    def _record_activity(self, activity: str, project: str = "") -> None:
        activity = activity.strip()
        project = project.strip()
        if not activity:
            return
        self.current_activity = activity
        self.current_project = project
        self._remember_project(project)
        stats = self._stats_for(dt.date.today())
        activities = stats.setdefault("activities", [])
        stats["summary_shown"] = False
        now_text = dt.datetime.now().isoformat(timespec="seconds")
        entry = {"time": now_text, "text": activity, "project": project}
        if (
            not activities
            or str(activities[-1].get("text", "")).strip().casefold() != activity.casefold()
            or str(activities[-1].get("project", "")).strip().casefold() != project.casefold()
        ):
            activities.append(entry)
        total = self._activity_total_entry(stats, activity, project)
        if total is not None:
            total["last_used"] = now_text
        self._save_activity_log()
        self._save_runtime_state(force=True)
        if self.summary_window and self.summary_window.get_visible():
            self.summary_window.refresh()

    @staticmethod
    def _manual_event_time(day: dt.date) -> str:
        now = dt.datetime.now()
        if day == now.date():
            return now.isoformat(timespec="seconds")
        return dt.datetime.combine(day, dt.time(12, 0)).isoformat(timespec="seconds")

    def add_manual_activity(self, day: dt.date, activity: str, project: str, seconds: int) -> None:
        activity = activity.strip()
        project = project.strip()
        seconds = max(0, int(seconds))
        if not activity:
            return
        stats = self._stats_for(day)
        self._ensure_target_snapshot(day, stats)
        item = self._activity_total_entry(stats, activity, project)
        if item is None:
            return
        item["work_seconds"] = max(0, int(item.get("work_seconds", 0))) + seconds
        event_time = self._manual_event_time(day)
        item["last_used"] = event_time
        stats["work_seconds"] = max(0, int(stats.get("work_seconds", 0))) + seconds
        stats["summary_shown"] = False
        self._refresh_closed_balance_delta(day)
        stats.setdefault("activities", []).append(
            {
                "time": event_time,
                "text": activity,
                "project": project,
                "manual": True,
            }
        )
        self._remember_project(project)
        self._save_activity_log()

    @staticmethod
    def _allocated_activity_seconds(stats: dict) -> int:
        total = 0
        for item in stats.get("activity_totals", []):
            if isinstance(item, dict):
                total += max(0, int(item.get("work_seconds", 0)))
        return total

    def unclassified_time_seconds(self, day: dt.date) -> int:
        stats = self.activity_log.get("days", {}).get(day.isoformat(), {})
        if not isinstance(stats, dict):
            return 0
        total_work = max(0, int(stats.get("work_seconds", 0)))
        return max(0, total_work - self._allocated_activity_seconds(stats))

    def update_unclassified_time(
        self,
        day: dt.date,
        activity: str,
        project: str,
        seconds: int,
    ) -> bool:
        activity = activity.strip()
        project = project.strip()
        seconds = max(0, int(seconds))
        stats = self._stats_for(day)
        self._ensure_target_snapshot(day, stats)
        old_unclassified = self.unclassified_time_seconds(day)
        if old_unclassified <= 0:
            return False

        allocated_before = self._allocated_activity_seconds(stats)
        event_time = self._manual_event_time(day)
        if activity and seconds > 0:
            item = self._activity_total_entry(stats, activity, project)
            if item is None:
                return False
            item["work_seconds"] = max(0, int(item.get("work_seconds", 0))) + seconds
            item["last_used"] = event_time
            stats.setdefault("activities", []).append(
                {
                    "time": event_time,
                    "text": activity,
                    "project": project,
                    "manual": True,
                    "classified_from_previous": True,
                }
            )
            self._remember_project(project)
            stats["work_seconds"] = allocated_before + seconds
        else:
            # Attività vuota: modifica soltanto la quantità ancora non classificata.
            stats["work_seconds"] = allocated_before + seconds

        stats["overtime_seconds"] = min(
            max(0, int(stats.get("overtime_seconds", 0))),
            max(0, int(stats.get("work_seconds", 0))),
        )
        stats["summary_shown"] = False
        self._refresh_closed_balance_delta(day)
        self._save_activity_log()
        return True

    def delete_unclassified_time(self, day: dt.date) -> bool:
        stats = self._stats_for(day)
        self._ensure_target_snapshot(day, stats)
        unclassified = self.unclassified_time_seconds(day)
        if unclassified <= 0:
            return False
        stats["work_seconds"] = self._allocated_activity_seconds(stats)
        stats["overtime_seconds"] = min(
            max(0, int(stats.get("overtime_seconds", 0))),
            max(0, int(stats.get("work_seconds", 0))),
        )
        stats["summary_shown"] = False
        self._refresh_closed_balance_delta(day)
        self._save_activity_log()
        return True

    def edit_manual_activity(
        self,
        day: dt.date,
        old_activity: str,
        old_project: str,
        new_activity: str,
        new_project: str,
        new_seconds: int,
    ) -> bool:
        old_activity = old_activity.strip()
        old_project = old_project.strip()
        new_activity = new_activity.strip()
        new_project = new_project.strip()
        new_seconds = max(0, int(new_seconds))
        if not new_activity:
            return False
        stats = self._stats_for(day)
        self._ensure_target_snapshot(day, stats)
        totals = stats.setdefault("activity_totals", [])
        source_index = next(
            (
                index
                for index, item in enumerate(totals)
                if isinstance(item, dict) and self._same_activity(item, old_activity, old_project)
            ),
            None,
        )
        if source_index is None:
            return False

        source = totals[source_index]
        old_seconds = max(0, int(source.get("work_seconds", 0)))
        event_time = self._manual_event_time(day)
        same_key = (
            old_activity.casefold() == new_activity.casefold()
            and old_project.casefold() == new_project.casefold()
        )

        if same_key:
            source["text"] = new_activity
            source["project"] = new_project
            source["work_seconds"] = new_seconds
            source["last_used"] = event_time
        else:
            target = next(
                (
                    item
                    for index, item in enumerate(totals)
                    if index != source_index
                    and isinstance(item, dict)
                    and self._same_activity(item, new_activity, new_project)
                ),
                None,
            )
            if target is not None:
                target["work_seconds"] = max(0, int(target.get("work_seconds", 0))) + new_seconds
                target["last_used"] = event_time
                totals.pop(source_index)
            else:
                source["text"] = new_activity
                source["project"] = new_project
                source["work_seconds"] = new_seconds
                source["last_used"] = event_time

        for event in stats.get("activities", []):
            if isinstance(event, dict) and self._same_activity(event, old_activity, old_project):
                event["text"] = new_activity
                event["project"] = new_project

        stats["work_seconds"] = max(
            0,
            int(stats.get("work_seconds", 0)) + new_seconds - old_seconds,
        )
        stats["summary_shown"] = False
        self._refresh_closed_balance_delta(day)
        self._remember_project(new_project)
        self._save_activity_log()
        if day == dt.date.today() and self._same_activity(
            {"text": self.current_activity, "project": self.current_project},
            old_activity,
            old_project,
        ):
            self.current_activity = new_activity
            self.current_project = new_project
            self._save_runtime_state(force=True)
        return True

    def delete_manual_activity(self, day: dt.date, activity: str, project: str) -> bool:
        activity = activity.strip()
        project = project.strip()
        stats = self._stats_for(day)
        self._ensure_target_snapshot(day, stats)
        totals = stats.setdefault("activity_totals", [])
        source_index = next(
            (
                index
                for index, item in enumerate(totals)
                if isinstance(item, dict) and self._same_activity(item, activity, project)
            ),
            None,
        )
        if source_index is None:
            return False
        removed = totals.pop(source_index)
        removed_seconds = max(0, int(removed.get("work_seconds", 0)))
        stats["work_seconds"] = max(0, int(stats.get("work_seconds", 0)) - removed_seconds)
        stats["activities"] = [
            event
            for event in stats.get("activities", [])
            if not (isinstance(event, dict) and self._same_activity(event, activity, project))
        ]
        stats["summary_shown"] = False
        self._refresh_closed_balance_delta(day)
        self._save_activity_log()
        if day == dt.date.today() and self._same_activity(
            {"text": self.current_activity, "project": self.current_project},
            activity,
            project,
        ):
            self.current_activity = ""
            self.current_project = ""
            self._save_runtime_state(force=True)
        return True

    @staticmethod
    def previous_month(year: int, month: int) -> tuple[int, int]:
        if month <= 1:
            return year - 1, 12
        return year, month - 1

    def month_overtime_seconds(self, year: int, month: int) -> int:
        total = 0
        for day_key, stats in self.activity_log.get("days", {}).items():
            if not isinstance(stats, dict):
                continue
            try:
                day = dt.date.fromisoformat(day_key)
            except Exception:
                continue
            if day.year == year and day.month == month:
                total += max(0, int(stats.get("overtime_seconds", 0)))
        return total

    @staticmethod
    def _markdown_escape(value: str) -> str:
        escaped = str(value).replace("\\", "\\\\")
        for char in ("*", "_", "[", "]", "`"):
            escaped = escaped.replace(char, f"\\{char}")
        return escaped

    def build_day_markdown(self, day: dt.date) -> str:
        stats = self.activity_log.get("days", {}).get(
            day.isoformat(),
            {
                "work_seconds": 0,
                "break_seconds": 0,
                "credited_break_seconds": 0,
                "overtime_seconds": 0,
                "activity_totals": [],
            },
        )
        rows = self._activity_totals_for(day, include_unclassified=True)
        lines = [f"# {format_italian_markdown_date(day)}", ""]
        if rows:
            grouped: dict[str, list[dict]] = {}
            for item in rows:
                project = str(item.get("project", "")).strip() or "Senza progetto"
                grouped.setdefault(project, []).append(item)
            for project, items in grouped.items():
                lines.append(f"- **{self._markdown_escape(project)}**")
                for item in items:
                    activity = str(item.get("text", "")).strip() or "Tempo non classificato"
                    if self.settings.markdown_include_task_times:
                        duration = self._format_effective_minutes(int(item.get("work_seconds", 0)))
                        lines.append(
                            f"  - {self._markdown_escape(activity)} — "
                            f"{self._markdown_escape(duration)}"
                        )
                    else:
                        lines.append(f"  - {self._markdown_escape(activity)}")
        else:
            lines.append("- Nessuna attività registrata.")

        work = self._format_effective_minutes(int(stats.get("work_seconds", 0)))
        pause = self._format_effective_minutes(int(stats.get("break_seconds", 0)))
        credited_pause = self._format_effective_minutes(int(stats.get("credited_break_seconds", 0)))
        counted = self._format_effective_minutes(self.daily_counted_seconds(day))
        target = self._format_effective_minutes(self._daily_target_seconds_for(day))
        remaining = self._format_effective_minutes(self.daily_remaining_seconds(day))
        balance_before_seconds = self.time_balance_before_day_seconds(day)
        if bool(stats.get("day_closed", False)):
            balance_after_seconds = self.active_time_balance_seconds(day)
        else:
            balance_after_seconds = self.projected_time_balance_for_day_seconds(day)
        balance_before = format_signed_hours_minutes(balance_before_seconds)
        balance_after = format_signed_hours_minutes(balance_after_seconds)
        day_overtime = self._format_effective_minutes(int(stats.get("overtime_seconds", 0)))
        special_extra = self._format_effective_minutes(self.special_day_extra_seconds(day))
        weekly_day_extra = self._format_effective_minutes(self.weekly_extra_for_day_seconds(day))
        total_day_extra = self._format_effective_minutes(self.total_extra_for_day_seconds(day))
        week_counted = self._format_effective_minutes(self.regular_week_counted_seconds(day))
        week_target = self._format_effective_minutes(self._weekly_target_seconds_for(day))
        week_extra = self._format_effective_minutes(self.weekly_extra_seconds(day))
        month_overtime = self._format_effective_minutes(
            self.month_overtime_seconds(day.year, day.month)
        )
        month_extra = self._format_effective_minutes(self.month_extra_seconds(day.year, day.month))
        month_special_extra = self._format_effective_minutes(
            self.month_special_extra_seconds(day.year, day.month)
        )
        month_closed_balance_extra = self._format_effective_minutes(
            self.closed_balance_extra_seconds(day.year, day.month)
        )
        closure_date = self._extra_closure_date(day.year, day.month)
        previous_year, previous_month = self.previous_month(day.year, day.month)
        previous_overtime = self._format_effective_minutes(
            self.month_overtime_seconds(previous_year, previous_month)
        )
        previous_extra = self._format_effective_minutes(
            self.month_extra_seconds(previous_year, previous_month)
        )
        current_month_label = f"{ITALIAN_MONTH_NAMES[day.month - 1]} {day.year}"
        previous_month_label = f"{ITALIAN_MONTH_NAMES[previous_month - 1]} {previous_year}"
        lines.extend(["", f"- **Totale lavoro:** {self._markdown_escape(work)}"])
        lines.append(f"- **Totale pause:** {self._markdown_escape(pause)}")
        lines.append(
            f"- **Pausa conteggiata nell’obiettivo giornaliero:** {self._markdown_escape(credited_pause)}"
        )
        if self._is_special_workday(day, stats):
            lines.append(
                f"- **Giornata lavorativa EXTRA:** "
                f"{self._markdown_escape(self._special_workday_label(day, stats))}"
            )
            lines.append(f"- **EXTRA festivo/ferie:** {self._markdown_escape(special_extra)}")
        elif self.day_has_regular_target(day):
            lines.append(
                f"- **Obiettivo giornaliero:** {self._markdown_escape(counted)} / "
                f"{self._markdown_escape(target)}"
            )
            lines.append(f"- **Tempo mancante:** {self._markdown_escape(remaining)}")
            lines.append(f"- **Saldo iniziale:** {self._markdown_escape(balance_before)}")
            lines.append(f"- **Saldo dopo la giornata:** {self._markdown_escape(balance_after)}")
            lines.append(
                f"- **Scelta di chiusura:** "
                f"{self._markdown_escape(str(stats.get('close_choice', '')).strip() or 'non ancora effettuata')}"
            )
        else:
            lines.append("- **Obiettivo giornaliero:** non previsto")
        lines.extend(
            [
                f"- **Straordinario oltre fascia del giorno:** {self._markdown_escape(day_overtime)}",
                f"- **Settimana ordinaria:** {self._markdown_escape(week_counted)} / "
                f"{self._markdown_escape(week_target)}",
                f"- **EXTRA oltre limite settimanale:** {self._markdown_escape(week_extra)}",
                f"- **EXTRA settimanale attribuito al giorno:** {self._markdown_escape(weekly_day_extra)}",
                f"- **EXTRA totale del giorno:** {self._markdown_escape(total_day_extra)}",
                f"- **EXTRA {self._markdown_escape(current_month_label)}:** "
                f"{self._markdown_escape(month_extra)}",
                f"- **Di cui EXTRA festivi/ferie:** {self._markdown_escape(month_special_extra)}",
                f"- **Straordinario oltre fascia {self._markdown_escape(current_month_label)}:** "
                f"{self._markdown_escape(month_overtime)}",
                f"- **EXTRA riportato dal mese precedente ({self._markdown_escape(previous_month_label)}):** "
                f"{self._markdown_escape(previous_extra)}",
                f"- **Straordinario oltre fascia del mese precedente "
                f"({self._markdown_escape(previous_month_label)}):** "
                f"{self._markdown_escape(previous_overtime)}",
                f"- **Saldo ore attivo:** "
                f"{self._markdown_escape(format_signed_hours_minutes(self.active_time_balance_seconds()))}",
                f"- **EXTRA da saldo chiuso nel mese:** "
                f"{self._markdown_escape(month_closed_balance_extra)}",
                f"- **Data di chiusura saldo del mese:** "
                f"{self._markdown_escape(closure_date.strftime('%d/%m/%Y'))}",
            ]
        )
        return "\n".join(lines)

    def build_month_overtime_markdown(self, year: int, month: int) -> str:
        month_label = f"{ITALIAN_MONTH_NAMES[month - 1]} {year}"
        lines = [f"# Straordinari ed EXTRA {month_label}", ""]
        closed_balance_extra = self.closed_balance_extra_seconds(year, month)
        closure_date = self._extra_closure_date(year, month)
        overtime_total = 0
        extra_total = 0
        special_total = 0
        weekly_total = 0
        rows: list[tuple[dt.date, int, int, int]] = []
        for day_key, stats in self.activity_log.get("days", {}).items():
            if not isinstance(stats, dict):
                continue
            try:
                day = dt.date.fromisoformat(day_key)
            except Exception:
                continue
            if day.year != year or day.month != month:
                continue
            overtime = max(0, int(stats.get("overtime_seconds", 0)))
            special_extra = self.special_day_extra_seconds(day)
            weekly_extra = self.weekly_extra_for_day_seconds(day)
            total_extra = special_extra + weekly_extra
            if overtime <= 0 and total_extra <= 0:
                continue
            rows.append((day, overtime, special_extra, weekly_extra))
            overtime_total += overtime
            special_total += special_extra
            weekly_total += weekly_extra
            extra_total += total_extra
        rows.sort(key=lambda item: item[0])
        if rows:
            for day, overtime, special_extra, weekly_extra in rows:
                details = []
                if overtime:
                    details.append(
                        f"oltre fascia {self._format_effective_minutes(overtime)}"
                    )
                if weekly_extra:
                    details.append(
                        f"EXTRA settimanale {self._format_effective_minutes(weekly_extra)}"
                    )
                if special_extra:
                    label = self._special_workday_label(day)
                    details.append(
                        f"EXTRA festivo/ferie {self._format_effective_minutes(special_extra)} "
                        f"({label})"
                    )
                lines.append(
                    f"- **{format_italian_markdown_date(day)}:** "
                    f"{self._markdown_escape(' · '.join(details))}"
                )
        else:
            lines.append("- Nessuno straordinario o EXTRA registrato nel mese.")

        previous_year, previous_month = self.previous_month(year, month)
        previous_label = f"{ITALIAN_MONTH_NAMES[previous_month - 1]} {previous_year}"
        previous_overtime = self.month_overtime_seconds(previous_year, previous_month)
        previous_extra = self.month_extra_seconds(previous_year, previous_month)
        lines.extend(
            [
                "",
                f"- **Totale straordinario oltre fascia {self._markdown_escape(month_label)}:** "
                f"{self._markdown_escape(self._format_effective_minutes(overtime_total))}",
                f"- **Totale EXTRA {self._markdown_escape(month_label)}:** "
                f"{self._markdown_escape(self._format_effective_minutes(extra_total))}",
                f"- **Di cui EXTRA oltre limite settimanale:** "
                f"{self._markdown_escape(self._format_effective_minutes(weekly_total))}",
                f"- **Di cui EXTRA festivi/ferie:** "
                f"{self._markdown_escape(self._format_effective_minutes(special_total))}",
                f"- **EXTRA riportato dal mese precedente ({self._markdown_escape(previous_label)}):** "
                f"{self._markdown_escape(self._format_effective_minutes(previous_extra))}",
                f"- **Straordinario oltre fascia del mese precedente "
                f"({self._markdown_escape(previous_label)}):** "
                f"{self._markdown_escape(self._format_effective_minutes(previous_overtime))}",
                f"- **EXTRA da saldo ore chiuso nel mese:** "
                f"{self._markdown_escape(self._format_effective_minutes(closed_balance_extra))}",
                f"- **Data prevista/effettiva di chiusura saldo:** "
                f"{self._markdown_escape(closure_date.strftime('%d/%m/%Y'))}",
                f"- **Saldo ore attivo attuale:** "
                f"{self._markdown_escape(format_signed_hours_minutes(self.active_time_balance_seconds()))}",
            ]
        )
        return "\n".join(lines)

    def _restore_latest_activity(self) -> None:
        days = self.activity_log.get("days", {})
        today = dt.date.today()
        # Per riprendere rapidamente vengono proposte soltanto oggi e ieri.
        for day in (today, today - dt.timedelta(days=1)):
            activities = days.get(day.isoformat(), {}).get("activities", [])
            if activities:
                latest = activities[-1]
                text = str(latest.get("text", "")).strip()
                if text:
                    self.current_activity = text
                    self.current_project = str(latest.get("project", "")).strip()
                    return

    def _project_suggestions(self) -> list[str]:
        projects = self.activity_log.setdefault("projects", {})
        values = []
        for data in projects.values():
            if not isinstance(data, dict):
                continue
            name = str(data.get("name", "")).strip()
            if name:
                values.append((str(data.get("last_used", "")), name))
        values.sort(key=lambda item: (item[0], item[1].casefold()), reverse=True)
        return [name for _last_used, name in values]

    def _activity_totals_for(self, day: dt.date, include_unclassified: bool = False) -> list[dict]:
        stats = self.activity_log.get("days", {}).get(day.isoformat())
        if not isinstance(stats, dict):
            return []
        rows = []
        allocated = 0
        for item in stats.get("activity_totals", []):
            if not isinstance(item, dict):
                continue
            seconds = max(0, int(item.get("work_seconds", 0)))
            allocated += seconds
            rows.append(
                {
                    "text": str(item.get("text", "")).strip(),
                    "project": str(item.get("project", "")).strip(),
                    "work_seconds": seconds,
                    "last_used": str(item.get("last_used", "")),
                }
            )
        total_work = max(0, int(stats.get("work_seconds", 0)))
        if include_unclassified and total_work > allocated:
            rows.append(
                {
                    "text": "Tempo precedente non classificato",
                    "project": "",
                    "work_seconds": total_work - allocated,
                    "last_used": "",
                    "unclassified": True,
                }
            )
        rows.sort(key=lambda item: (int(item.get("work_seconds", 0)), str(item.get("last_used", ""))), reverse=True)
        return rows

    def _recent_activity_options(self) -> list[dict]:
        today = dt.date.today()
        seen: set[tuple[str, str]] = set()
        options: list[dict] = []
        for day, day_name in ((today, "oggi"), (today - dt.timedelta(days=1), "ieri")):
            stats = self.activity_log.get("days", {}).get(day.isoformat(), {})
            totals = self._activity_totals_for(day)
            totals_by_key = {
                (str(item.get("project", "")).casefold(), str(item.get("text", "")).casefold()): item
                for item in totals
            }
            activities = stats.get("activities", []) if isinstance(stats, dict) else []
            ordered: list[dict] = []
            for event in reversed(activities):
                if not isinstance(event, dict):
                    continue
                text = str(event.get("text", "")).strip()
                project = str(event.get("project", "")).strip()
                if not text:
                    continue
                total = totals_by_key.get((project.casefold(), text.casefold()), {})
                ordered.append(
                    {
                        "text": text,
                        "project": project,
                        "work_seconds": int(total.get("work_seconds", 0)),
                        "last_used": str(event.get("time", "")),
                    }
                )
            ordered.extend(totals)
            for item in ordered:
                text = str(item.get("text", "")).strip()
                project = str(item.get("project", "")).strip()
                key = (project.casefold(), text.casefold())
                if not text or key in seen:
                    continue
                seen.add(key)
                display = f"{project} — {text}" if project else text
                duration = self._format_effective_minutes(int(item.get("work_seconds", 0)))
                options.append(
                    {
                        "text": text,
                        "project": project,
                        "label": f"{display} · {duration} · {day_name}",
                        "last_used": str(item.get("last_used", "")),
                    }
                )
        return options

    @staticmethod
    def _format_effective_minutes(seconds: int) -> str:
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours} h {minutes:02d} min" if secs == 0 else f"{hours} h {minutes:02d} min {secs:02d} sec"
        if secs == 0:
            return f"{minutes} min"
        return f"{minutes} min {secs:02d} sec"

    def show_daily_summary(self, day: Optional[dt.date] = None, mark_shown: bool = False) -> None:
        self.show_activity_summary(day, mark_shown)

    def _show_pending_summary_if_needed(self) -> bool:
        now = dt.datetime.now()
        afternoon_end = parse_hhmm(self.settings.afternoon_end)
        for day_key in sorted(self.activity_log.get("days", {}), reverse=True):
            try:
                day = dt.date.fromisoformat(day_key)
            except Exception:
                continue
            if day > now.date():
                continue
            stats = self.activity_log.get("days", {}).get(day_key, {})
            if stats.get("summary_shown"):
                continue
            has_time = int(stats.get("work_seconds", 0)) + int(stats.get("break_seconds", 0)) > 0
            day_is_finished = day < now.date() or now.time() >= afternoon_end
            if has_time and day_is_finished:
                self.show_daily_summary(day, mark_shown=True)
                break
        return False

    def compact_indicator_label(self) -> str:
        # Il tempo resta sempre accanto all'icona quando il pannello lo supporta.
        if not self.settings.enabled:
            return "OFF"
        elif self.current_session is None:
            base = "Zz"
        elif self.compensating_daily_balance:
            base = f"↥ {format_mmss(self.compensation_remaining)}"
        elif self.waiting_daily_close_choice:
            base = "Saldo?"
        elif self.in_midday_recovery:
            base = f"↻ {format_mmss(self.midday_recovery_remaining)}"
        elif self.waiting_session_end:
            base = "Fine?"
        elif self.in_overtime:
            base = f"+ {format_mmss(self.overtime_seconds)}"
        elif self.waiting_session_start:
            base = "START"
        elif self.waiting_grace_choice:
            base = "Scegli"
        elif self.waiting_break_start:
            base = "STOP"
        elif self.waiting_return:
            base = "Rientro"
        elif self.in_break:
            base = f"☕ {format_mmss(self.break_remaining)}"
        elif self.in_grace:
            base = f"! {format_mmss(self.grace_remaining)}"
        else:
            base = format_compact_time(self.work_remaining)

        today = dt.date.today()
        stats = self.activity_log.get("days", {}).get(today.isoformat(), {})
        if self._is_special_workday(today, stats):
            special = self.special_day_extra_seconds(today)
            if special > 0:
                return f"{base} · EXTRA {format_compact_time(special)}"
            return base
        if self.day_has_regular_target(today):
            remaining = self.daily_remaining_seconds(today)
            if remaining > 0:
                return f"{base} · {format_compact_time(remaining)} da fare"
            balance = self.projected_time_balance_for_day_seconds(today)
            if balance > 0:
                return f"{base} · saldo {format_signed_hours_minutes(balance)}"
            return f"{base} · giornata ✓"
        return base

    def _update_indicator_label(self) -> None:
        if self.indicator is None:
            return
        label = self.compact_indicator_label()
        try:
            if hasattr(self.indicator, "set_label"):
                self.indicator.set_label(label, "88m88 · 88h88 da fare")
        except Exception:
            pass

    def status_text(self) -> str:
        if not self.settings.enabled:
            return "Promemoria in pausa"
        if self.current_session is None:
            reason = self.day_off_reason(dt.date.today())
            if reason:
                return f"Giornata esclusa: {reason}"
            return "Fuori fascia: timer fermo"
        if self.compensating_daily_balance:
            return (
                "Compensazione post chiusura: mancano "
                f"{format_signed_hours_minutes(self.compensation_remaining)}"
            )
        if self.waiting_daily_close_choice:
            return (
                "Fine giornata: scegli se compensare o posticipare "
                f"{format_signed_hours_minutes(self.compensation_remaining)}"
            )
        if self.in_midday_recovery:
            if self.midday_recovery_remaining <= 0:
                return "Pausa mattutina recuperata: conferma il rientro"
            return f"Recupero pausa mattutina: {format_mmss(self.midday_recovery_remaining)}"
        if self.waiting_session_end:
            remaining = max(0, SESSION_END_INACTIVITY_SECONDS - self.end_prompt_wait_seconds)
            return f"Fine {self._session_name()}: attendendo conferma ({format_mmss(remaining)})"
        if self.in_overtime:
            return (
                f"Lavoro oltre orario: +{format_mmss(self.overtime_seconds)} — "
                f"prossimo promemoria tra {format_mmss(self.overtime_reminder_remaining)}"
            )
        if self.waiting_session_start:
            return f"In attesa di iniziare il {self._session_name()}"
        if self.waiting_grace_choice:
            return "Scegli quanto tempo usare per concludere: il lavoro continua a essere conteggiato"
        if self.waiting_break_start:
            return "In attesa della pausa: il lavoro continua a essere conteggiato"
        if self.waiting_return:
            return "Pausa terminata: il ritardo non viene conteggiato come lavoro"
        if self.in_break:
            return f"Pausa: {format_mmss(self.break_remaining)}"
        if self.in_grace:
            return f"Fermati tra: {format_mmss(self.grace_remaining)}"
        activity = ""
        if self.current_activity:
            current = f"{self.current_project} — {self.current_activity}" if self.current_project else self.current_activity
            activity = f" — {current}"
        return f"Prossima pausa: {format_mmss(self.work_remaining)}{activity}"

    def _update_ui(self) -> None:
        text = self.status_text()
        progress = self.daily_progress_text(dt.date.today())
        if progress:
            text = f"{text}\n{progress}"
        self._update_indicator_label()
        if self.indicator_status_item:
            self.indicator_status_item.set_label(text)
        if self.indicator_toggle_item:
            self.indicator_toggle_item.set_label(
                "Pausa promemoria" if self.settings.enabled else "Riattiva promemoria"
            )
        if self.control_window:
            self.control_window.update(text, self.settings.enabled)

    def quit(self) -> None:
        self._save_activity_log()
        self._save_runtime_state(force=True)
        self._remove_pid_file()
        Gtk.main_quit()

    def run(self) -> None:
        Gtk.main()

def request_change_activity_from_running_instance() -> bool:
    if not hasattr(signal, "SIGUSR1"):
        return False
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        if pid <= 1 or pid == os.getpid():
            return False
        os.kill(pid, 0)
        proc_cmdline = Path(f"/proc/{pid}/cmdline")
        if proc_cmdline.exists():
            command = proc_cmdline.read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
            if APP_ID not in command and "workbreak_guard.py" not in command:
                raise ProcessLookupError(f"Il PID {pid} non appartiene a {APP_ID}")
        os.kill(pid, signal.SIGUSR1)
        return True
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError, OSError):
        try:
            PID_FILE.unlink()
        except Exception:
            pass
        return False


def main() -> int:
    if "--enable-autostart" in sys.argv:
        set_autostart_enabled(True)
        print(f"Autostart abilitato: {AUTOSTART_FILE}")
        return 0
    if "--disable-autostart" in sys.argv:
        set_autostart_enabled(False)
        print("Autostart disabilitato")
        return 0
    if "--status-autostart" in sys.argv:
        print("enabled" if is_autostart_enabled() else "disabled")
        return 0
    change_activity_requested = "--change-activity" in sys.argv
    if change_activity_requested and request_change_activity_from_running_instance():
        return 0
    # --autostart è solo un marcatore per distinguere l'avvio di sessione nei log/launcher.
    app = WorkBreakApp()
    if change_activity_requested:
        GLib.idle_add(app.request_activity_prompt)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
