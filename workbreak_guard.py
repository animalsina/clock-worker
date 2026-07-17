#!/usr/bin/env python3
# Copyright (c) 2026 Giuseppe Mazzullo <info@animalsina.work>
# Licensed under the PolyForm Noncommercial License 1.0.0. See LICENSE.
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
- Permette di iniziare manualmente prima della fascia, sospendere e riprendere la giornata, oppure terminarla in anticipo.
- Supporta pause manuali a durata definita o senza scadenza, registrate ma non accreditate nell’obiettivo giornaliero.
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
REGULAR_PAUSE_WORK_BLOCK_SECONDS = 2 * 60 * 60

TIMER_END_SOUND_OPTIONS = {
    "none": "Nessun suono",
    "soft": "Beep morbido",
    "double": "Doppio beep",
    "chime": "Campanello",
}


@dataclass
class Settings:
    enabled: bool = True
    work_minutes: int = 60
    break_minutes: int = 5
    regular_pause_credit_minutes: int = 10
    daily_pause_extra_credit_minutes: int = 20
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
    timer_end_sound: str = "soft"
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
        self.regular_pause_credit_minutes = clamp_int(
            self.regular_pause_credit_minutes, 0, 60
        )
        self.daily_pause_extra_credit_minutes = clamp_int(
            self.daily_pause_extra_credit_minutes, 0, 240
        )
        self.daily_target_hours = clamp_int(self.daily_target_hours, 1, 24)
        self.warning_seconds = clamp_int(self.warning_seconds, 5, 600)
        self.overtime_reminder_minutes = clamp_int(self.overtime_reminder_minutes, 1, 120)
        self.extra_closure_day = clamp_int(self.extra_closure_day, 1, 28)
        self.extra_closure_weekday = clamp_int(self.extra_closure_weekday, 0, 6)
        self.show_clock_last_minutes = clamp_int(self.show_clock_last_minutes, 0, 60)
        self.timer_end_sound = str(self.timer_end_sound or "soft")
        if self.timer_end_sound not in TIMER_END_SOUND_OPTIONS:
            self.timer_end_sound = "soft"
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


def format_hhmmss(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_negative_countdown(seconds: int) -> str:
    """Formatta un tempo trascorso come countdown negativo, es. -05:30."""
    return f"-{format_mmss(seconds)}"


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
    .wb-summary-card {
        background: alpha(@theme_fg_color, 0.055);
        border: 1px solid alpha(@theme_fg_color, 0.12);
        border-radius: 12px;
        padding: 12px;
    }
    .wb-summary-value { font-size: 22px; font-weight: 800; }
    .wb-summary-caption { font-size: 12px; opacity: 0.72; }
    .wb-chart-title { font-size: 18px; font-weight: 800; }
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
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)

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
        button.set_can_focus(False)
        button.set_sensitive(False)
        button.connect("clicked", self._clicked)
        outer.pack_start(button, False, False, 0)
        GLib.timeout_add(800, self._enable_button_safely, button)

        self.show_all()
        place_on_active_monitor_top_right(self, 520, 220)

    @staticmethod
    def _enable_button_safely(button: Gtk.Button) -> bool:
        try:
            button.set_sensitive(True)
        except Exception:
            pass
        return False

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



def active_monitor_geometry():
    """Restituisce la geometria del monitor in cui si trova il puntatore."""
    try:
        display = Gdk.Display.get_default()
        if not display:
            return None
        monitor = None
        seat = display.get_default_seat()
        pointer = seat.get_pointer() if seat else None
        if pointer:
            _screen, x, y = pointer.get_position()
            if hasattr(display, "get_monitor_at_point"):
                monitor = display.get_monitor_at_point(x, y)
        monitor = monitor or display.get_primary_monitor() or display.get_monitor(0)
        return monitor.get_geometry() if monitor else None
    except Exception:
        return None


def place_on_active_monitor(window: Gtk.Window, width: int, height: int) -> None:
    """Centra la finestra sul monitor in cui si trova il puntatore."""
    try:
        geo = active_monitor_geometry()
        if not geo:
            return
        window.resize(width, height)
        window.move(geo.x + max(0, (geo.width - width) // 2), geo.y + max(0, (geo.height - height) // 2))
    except Exception:
        # Su Wayland il compositor può ignorare il posizionamento esplicito.
        pass


def place_on_active_monitor_top_right(
    window: Gtk.Window, width: int, height: int, margin: int = 24
) -> None:
    """Posiziona un avviso in alto a destra senza coprire il centro del lavoro."""
    try:
        geo = active_monitor_geometry()
        if not geo:
            return
        window.resize(width, height)
        window.move(
            geo.x + max(0, geo.width - width - margin),
            geo.y + max(0, margin),
        )
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
        if len(choices) >= 5:
            self.window_width = 1040
        elif len(choices) >= 4:
            self.window_width = 820
        else:
            self.window_width = 620
        self.set_default_size(self.window_width, 250)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)

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
            button.set_can_focus(False)
            button.set_sensitive(False)
            button.connect("clicked", self._clicked, callback)
            row.pack_start(button, True, True, 0)
            GLib.timeout_add(800, self._enable_button_safely, button)

        self.show_all()
        place_on_active_monitor_top_right(self, self.window_width, 250)

    @staticmethod
    def _enable_button_safely(button: Gtk.Button) -> bool:
        try:
            button.set_sensitive(True)
        except Exception:
            pass
        return False

    def _clicked(self, _button: Gtk.Button, callback: Callable[[], None]) -> None:
        self.destroy()
        callback()

    def _on_key(self, _widget, event) -> bool:
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space) and self.choices:
            self.destroy()
            self.choices[0][1]()
            return True
        return False


class ManualPauseWindow(Gtk.Window):
    def __init__(self, app: "WorkBreakApp"):
        super().__init__(title="Pausa manuale")
        self.app = app
        self.set_default_size(620, 330)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        outer.set_border_width(24)
        outer.get_style_context().add_class("wb-card")
        self.add(outer)

        title = Gtk.Label(label="Quanto deve durare la pausa?")
        title.get_style_context().add_class("wb-title")
        title.set_line_wrap(True)
        title.set_justify(Gtk.Justification.CENTER)
        outer.pack_start(title, False, False, 0)

        message = Gtk.Label(
            label=(
                "La pausa manuale viene registrata come pausa effettiva, ma non viene "
                "conteggiata nelle ore di lavoro giornaliere. Puoi scegliere una durata "
                "oppure lasciarla senza scadenza e riprendere quando vuoi."
            )
        )
        message.get_style_context().add_class("wb-body")
        message.set_line_wrap(True)
        message.set_justify(Gtk.Justification.CENTER)
        outer.pack_start(message, False, False, 0)

        quick = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        quick.set_homogeneous(True)
        outer.pack_start(quick, False, False, 0)
        for minutes in (5, 10, 15, 30, 60):
            button = Gtk.Button(label=f"{minutes} min")
            button.connect("clicked", lambda _button, value=minutes: self._start(value))
            quick.pack_start(button, True, True, 0)

        custom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        outer.pack_start(custom, False, False, 0)
        custom.pack_start(Gtk.Label(label="Durata personalizzata:"), False, False, 0)
        self.minutes = Gtk.SpinButton.new_with_range(1, 720, 1)
        self.minutes.set_value(20)
        custom.pack_start(self.minutes, False, False, 0)
        custom.pack_start(Gtk.Label(label="minuti"), False, False, 0)
        start_custom = Gtk.Button(label="Avvia pausa")
        start_custom.connect("clicked", lambda *_: self._start(int(self.minutes.get_value())))
        custom.pack_end(start_custom, False, False, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        actions.set_homogeneous(True)
        outer.pack_start(actions, False, False, 0)
        indefinite = Gtk.Button(label="Pausa senza scadenza")
        indefinite.connect("clicked", lambda *_: self._start(None))
        actions.pack_start(indefinite, True, True, 0)
        cancel = Gtk.Button(label="Annulla")
        cancel.connect("clicked", lambda *_: self._cancel())
        actions.pack_start(cancel, True, True, 0)

        self.connect("delete-event", self._on_delete)
        self.show_all()
        place_on_active_monitor(self, 620, 330)
        self.present()

    def _start(self, minutes: Optional[int]) -> None:
        self.app.manual_pause_window = None
        self.destroy()
        self.app.start_manual_break(minutes)

    def _cancel(self) -> None:
        self.app.manual_pause_window = None
        self.destroy()

    def _on_delete(self, *_args) -> bool:
        self.app.manual_pause_window = None
        return False


class RegularPauseWindow(Gtk.Window):
    """Scelta della durata per la pausa ciclica accreditabile nell’obiettivo."""

    def __init__(self, app: "WorkBreakApp"):
        super().__init__(title="Durata della pausa")
        self.app = app
        self.set_default_size(650, 330)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        outer.set_border_width(24)
        outer.get_style_context().add_class("wb-card")
        self.add(outer)

        title = Gtk.Label(label="Quanto deve durare la pausa?")
        title.get_style_context().add_class("wb-title")
        title.set_line_wrap(True)
        title.set_justify(Gtk.Justification.CENTER)
        outer.pack_start(title, False, False, 0)

        day = app.current_session_date or dt.date.today()
        available = app.regular_pause_credit_available_seconds(day)
        credit_minutes = max(0, int(app.settings.regular_pause_credit_minutes))
        extra_minutes = max(0, int(app.settings.daily_pause_extra_credit_minutes))
        if credit_minutes > 0:
            credit_explanation = (
                f"Ogni pausa può abbuonare fino a {credit_minutes} minuti. "
                f"La giornata matura {credit_minutes} minuti ogni 2 ore lavorate "
                f"più {extra_minutes} minuti di tolleranza giornaliera: soltanto "
                "la parte oltre il tetto complessivo sarà da recuperare."
            )
        else:
            credit_explanation = (
                "Nelle impostazioni la pausa abbuonata per singola pausa è disattivata: "
                "tutta la durata scelta resterà una pausa reale da recuperare."
            )
        message = Gtk.Label(
            label=(
                "La pausa parte nel momento in cui scegli una durata. "
                f"{credit_explanation}\n"
                f"Quota ancora disponibile oggi: {app._format_effective_minutes(available)}."
            )
        )
        message.get_style_context().add_class("wb-body")
        message.set_line_wrap(True)
        message.set_justify(Gtk.Justification.CENTER)
        outer.pack_start(message, False, False, 0)

        quick = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        quick.set_homogeneous(True)
        outer.pack_start(quick, False, False, 0)
        for minutes in (5, 10, 15):
            button = Gtk.Button(label=f"{minutes} minuti")
            button.connect("clicked", lambda _button, value=minutes: self._start(value))
            quick.pack_start(button, True, True, 0)

        custom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        outer.pack_start(custom, False, False, 0)
        custom.pack_start(Gtk.Label(label="Durata personalizzata:"), False, False, 0)
        self.minutes = Gtk.SpinButton.new_with_range(1, 720, 1)
        self.minutes.set_value(max(1, int(app.settings.break_minutes)))
        custom.pack_start(self.minutes, False, False, 0)
        custom.pack_start(Gtk.Label(label="minuti"), False, False, 0)
        start_custom = Gtk.Button(label="Avvia pausa personalizzata")
        start_custom.connect("clicked", lambda *_: self._start(int(self.minutes.get_value())))
        custom.pack_end(start_custom, False, False, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        actions.set_homogeneous(True)
        outer.pack_start(actions, False, False, 0)
        skip = Gtk.Button(label="Salta pausa e continua il lavoro")
        skip.connect("clicked", lambda *_: self._skip())
        actions.pack_start(skip, True, True, 0)
        cancel = Gtk.Button(label="Annulla")
        cancel.connect("clicked", lambda *_: self._cancel())
        actions.pack_start(cancel, True, True, 0)

        self.connect("delete-event", self._on_delete)
        self.show_all()
        place_on_active_monitor(self, 650, 330)
        self.present()

    def _start(self, minutes: int) -> None:
        self.app.regular_pause_window = None
        self.destroy()
        self.app._begin_regular_break(minutes)

    def _cancel(self) -> None:
        self.app.regular_pause_window = None
        self.destroy()
        self.app._cancel_regular_pause_choice()

    def _skip(self) -> None:
        self.app.regular_pause_window = None
        self.destroy()
        self.app._skip_regular_break()

    def _on_delete(self, *_args) -> bool:
        self.app.regular_pause_window = None
        GLib.idle_add(self.app._cancel_regular_pause_choice)
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
        info_lines: Optional[list[str]] = None,
    ):
        super().__init__(title=title)
        self.current_activity = current_activity.strip()
        self.current_project = current_project.strip()
        self.recent_activities = recent_activities
        self.on_activity = on_activity
        self.on_later = on_later
        self.activity_question = activity_question
        self.set_default_size(700, 610 if info_lines else 500)
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

        self.info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.info_box.set_margin_top(2)
        self.info_box.set_margin_bottom(4)
        outer.pack_start(self.info_box, False, False, 0)
        self.update_info_lines(info_lines or [])

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
        place_on_active_monitor(self, 700, 610 if info_lines else 500)
        self.present()
        self.entry.grab_focus()

    def update_info_lines(self, lines: list[str]) -> None:
        """Aggiorna il riquadro informativo senza ricreare la finestra."""
        for child in self.info_box.get_children():
            self.info_box.remove(child)
        if not lines:
            self.info_box.set_no_show_all(True)
            self.info_box.hide()
            return

        self.info_box.set_no_show_all(False)
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.info_box.pack_start(separator, False, False, 2)
        for index, text in enumerate(lines):
            label = Gtk.Label(label=text)
            label.set_xalign(0)
            label.set_line_wrap(True)
            label.set_selectable(True)
            if index >= max(0, len(lines) - 2):
                label.get_style_context().add_class("wb-body")
            self.info_box.pack_start(label, False, False, 0)
        self.info_box.show_all()

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


class TransferTimeDialog(Gtk.Dialog):
    def __init__(
        self,
        parent: Gtk.Window,
        source: dict,
        targets: list[dict],
    ):
        super().__init__(
            title="Trasferisci tempo in un altro task",
            transient_for=parent,
            flags=Gtk.DialogFlags.MODAL,
        )
        self.targets = targets
        self.source_seconds = max(0, int(source.get("seconds", 0)))
        self.add_button("Annulla", Gtk.ResponseType.CANCEL)
        transfer_button = self.add_button("Trasferisci", Gtk.ResponseType.OK)
        transfer_button.get_style_context().add_class("suggested-action")
        self.set_default_response(Gtk.ResponseType.OK)
        self.set_default_size(620, 320)
        self.set_resizable(False)

        content = self.get_content_area()
        content.set_spacing(12)
        content.set_border_width(16)

        grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        content.pack_start(grid, True, True, 0)

        source_project = str(source.get("project", "")).strip()
        source_activity = str(source.get("activity", "")).strip()
        source_text = (
            f"{source_project} — {source_activity}"
            if source_project
            else source_activity
        )
        source_label = Gtk.Label(label="Task di origine")
        source_label.set_xalign(0)
        grid.attach(source_label, 0, 0, 1, 1)
        source_value = Gtk.Label(label=source_text)
        source_value.set_xalign(0)
        source_value.set_line_wrap(True)
        grid.attach(source_value, 1, 0, 3, 1)

        target_label = Gtk.Label(label="Task di destinazione")
        target_label.set_xalign(0)
        grid.attach(target_label, 0, 1, 1, 1)
        self.target_combo = Gtk.ComboBoxText()
        for index, target in enumerate(targets):
            project = str(target.get("project", "")).strip()
            activity = str(target.get("activity", "")).strip()
            label = f"{project} — {activity}" if project else activity
            self.target_combo.append(str(index), label)
        if targets:
            self.target_combo.set_active(0)
        grid.attach(self.target_combo, 1, 1, 3, 1)

        duration_label = Gtk.Label(label="Tempo da trasferire")
        duration_label.set_xalign(0)
        grid.attach(duration_label, 0, 2, 1, 1)

        hours, remainder = divmod(self.source_seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        self.hours_spin = Gtk.SpinButton.new_with_range(0, max(9999, hours), 1)
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

        available = Gtk.Label(
            label=f"Tempo disponibile nel task: {format_hhmmss(self.source_seconds)}"
        )
        available.set_xalign(0)
        grid.attach(available, 1, 3, 3, 1)

        note = Gtk.Label(
            label=(
                "Il trasferimento modifica soltanto la distribuzione del tempo tra i task: "
                "il totale di lavoro, il saldo e gli straordinari della giornata non cambiano."
            )
        )
        note.set_xalign(0)
        note.set_line_wrap(True)
        grid.attach(note, 0, 4, 4, 1)

        self.show_all()

    def values(self) -> Optional[tuple[dict, int]]:
        target_id = self.target_combo.get_active_id()
        if target_id is None:
            return None
        try:
            target = self.targets[int(target_id)]
        except (ValueError, IndexError):
            return None
        seconds = (
            int(self.hours_spin.get_value_as_int()) * 3600
            + int(self.minutes_spin.get_value_as_int()) * 60
            + int(self.seconds_spin.get_value_as_int())
        )
        return target, seconds


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


class DayChartView(Gtk.ScrolledWindow):
    """Dashboard grafica del riepilogo giornaliero, senza dipendenze esterne."""

    def __init__(self, app: "WorkBreakApp", day: dt.date):
        super().__init__()
        self.app = app
        self.day = day
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        viewport = Gtk.Viewport()
        viewport.set_shadow_type(Gtk.ShadowType.NONE)
        self.add(viewport)

        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.content.set_border_width(16)
        viewport.add(self.content)
        self.refresh()

    def _clear(self) -> None:
        for child in self.content.get_children():
            child.destroy()

    @staticmethod
    def _duration(app: "WorkBreakApp", seconds: int) -> str:
        return app._format_effective_minutes(max(0, int(seconds)))

    @staticmethod
    def _signed_duration(seconds: int) -> str:
        return format_signed_hours_minutes(int(seconds))

    def _section_title(self, text: str, subtitle: str = "") -> None:
        title = Gtk.Label(label=text)
        title.set_xalign(0)
        title.get_style_context().add_class("wb-chart-title")
        self.content.pack_start(title, False, False, 0)
        if subtitle:
            detail = Gtk.Label(label=subtitle)
            detail.set_xalign(0)
            detail.set_line_wrap(True)
            detail.get_style_context().add_class("wb-summary-caption")
            self.content.pack_start(detail, False, False, 0)

    @staticmethod
    def _metric_card(caption: str, value: str, detail: str = "") -> Gtk.Widget:
        card = Gtk.EventBox()
        card.get_style_context().add_class("wb-summary-card")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        box.set_border_width(10)
        card.add(box)

        value_label = Gtk.Label(label=value)
        value_label.set_xalign(0)
        value_label.set_selectable(True)
        value_label.get_style_context().add_class("wb-summary-value")
        box.pack_start(value_label, False, False, 0)

        caption_label = Gtk.Label(label=caption)
        caption_label.set_xalign(0)
        caption_label.set_line_wrap(True)
        box.pack_start(caption_label, False, False, 0)

        if detail:
            detail_label = Gtk.Label(label=detail)
            detail_label.set_xalign(0)
            detail_label.set_line_wrap(True)
            detail_label.get_style_context().add_class("wb-summary-caption")
            box.pack_start(detail_label, False, False, 0)
        return card

    @staticmethod
    def _bar_row(label: str, value: str, fraction: float, subtitle: str = "") -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.pack_start(header, False, False, 0)

        name = Gtk.Label(label=label)
        name.set_xalign(0)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.set_tooltip_text(label)
        header.pack_start(name, True, True, 0)

        duration = Gtk.Label(label=value)
        duration.set_xalign(1)
        duration.set_selectable(True)
        header.pack_end(duration, False, False, 0)

        progress = Gtk.ProgressBar()
        progress.set_fraction(max(0.0, min(1.0, float(fraction))))
        progress.set_hexpand(True)
        row.pack_start(progress, False, False, 0)

        if subtitle:
            detail = Gtk.Label(label=subtitle)
            detail.set_xalign(0)
            detail.set_ellipsize(Pango.EllipsizeMode.END)
            detail.set_tooltip_text(subtitle)
            detail.get_style_context().add_class("wb-summary-caption")
            row.pack_start(detail, False, False, 0)
        return row

    def refresh(self) -> None:
        self._clear()
        day = self.day
        stats = self.app.activity_log.get("days", {}).get(
            day.isoformat(),
            {
                "work_seconds": 0,
                "break_seconds": 0,
                "credited_break_seconds": 0,
                "regular_break_eligible_seconds": 0,
                "overtime_seconds": 0,
                "activity_totals": [],
            },
        )

        work_seconds = max(0, int(stats.get("work_seconds", 0)))
        break_seconds = max(0, int(stats.get("break_seconds", 0)))
        credited_break_seconds = max(
            0, int(self.app.credited_break_for_day_seconds(day, stats))
        )
        recoverable_break_seconds = max(0, break_seconds - credited_break_seconds)
        counted_seconds = max(0, int(self.app.daily_counted_seconds(day)))
        target_seconds = max(0, int(self.app._daily_target_seconds_for(day)))
        remaining_seconds = max(0, int(self.app.daily_remaining_seconds(day)))
        overtime_seconds = max(0, int(stats.get("overtime_seconds", 0)))
        total_extra_seconds = max(0, int(self.app.total_extra_for_day_seconds(day)))
        balance_before_seconds = int(self.app.time_balance_before_day_seconds(day))
        if bool(stats.get("day_closed", False)):
            balance_after_seconds = int(self.app.active_time_balance_seconds(day))
        else:
            balance_after_seconds = int(self.app.projected_time_balance_for_day_seconds(day))

        date_title = Gtk.Label(label=format_italian_markdown_date(day))
        date_title.set_xalign(0)
        date_title.modify_font(Pango.FontDescription("Sans Bold 22"))
        self.content.pack_start(date_title, False, False, 0)

        goal_card = Gtk.EventBox()
        goal_card.get_style_context().add_class("wb-summary-card")
        goal_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        goal_box.set_border_width(12)
        goal_card.add(goal_box)
        self.content.pack_start(goal_card, False, False, 0)

        goal_title = Gtk.Label(label="Avanzamento della giornata")
        goal_title.set_xalign(0)
        goal_title.get_style_context().add_class("wb-chart-title")
        goal_box.pack_start(goal_title, False, False, 0)

        goal_bar = Gtk.ProgressBar()
        goal_bar.set_show_text(True)
        if self.app.day_has_regular_target(day) and target_seconds > 0:
            goal_bar.set_fraction(min(1.0, counted_seconds / target_seconds))
            if remaining_seconds > 0:
                goal_bar.set_text(
                    f"{self._duration(self.app, counted_seconds)} su "
                    f"{self._duration(self.app, target_seconds)} · "
                    f"mancano {self._duration(self.app, remaining_seconds)}"
                )
            else:
                surplus = max(0, counted_seconds - target_seconds)
                suffix = (
                    f" · +{self._duration(self.app, surplus)}"
                    if surplus > 0
                    else " · obiettivo raggiunto"
                )
                goal_bar.set_text(
                    f"{self._duration(self.app, counted_seconds)} su "
                    f"{self._duration(self.app, target_seconds)}{suffix}"
                )
        elif self.app._is_special_workday(day, stats):
            goal_bar.set_fraction(1.0 if work_seconds > 0 else 0.0)
            goal_bar.set_text(
                f"Giornata EXTRA · {self._duration(self.app, work_seconds)} lavorate"
            )
        else:
            goal_bar.set_fraction(0.0)
            goal_bar.set_text("Nessun obiettivo ordinario previsto")
        goal_box.pack_start(goal_bar, False, False, 0)

        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(12)
        grid.set_column_homogeneous(True)
        cards = [
            ("Lavoro effettivo", self._duration(self.app, work_seconds), "Tempo attribuito alle attività"),
            ("Pause totali", self._duration(self.app, break_seconds), "Tutto il tempo trascorso in pausa"),
            ("Pausa abbuonata", self._duration(self.app, credited_break_seconds), "Quota conteggiata nell’obiettivo"),
            ("Pausa da recuperare", self._duration(self.app, recoverable_break_seconds), "Parte non conteggiata come lavoro"),
            ("Straordinario oltre fascia", self._duration(self.app, overtime_seconds), "Lavoro confermato dopo l’orario"),
            ("EXTRA totale del giorno", self._duration(self.app, total_extra_seconds), "Festivi, ferie o limite settimanale"),
            ("Saldo iniziale", self._signed_duration(balance_before_seconds), "Credito o debito prima della giornata"),
            ("Saldo dopo la giornata", self._signed_duration(balance_after_seconds), "Valore aggiornato con i dati correnti"),
        ]
        for index, (caption, value, detail) in enumerate(cards):
            grid.attach(self._metric_card(caption, value, detail), index % 2, index // 2, 1, 1)
        self.content.pack_start(grid, False, False, 0)

        self._section_title(
            "Composizione del tempo",
            "Le barre confrontano lavoro, pausa abbuonata e pausa da recuperare.",
        )
        composition = [
            ("Lavoro effettivo", work_seconds),
            ("Pausa abbuonata", credited_break_seconds),
            ("Pausa da recuperare", recoverable_break_seconds),
        ]
        composition_max = max([value for _label, value in composition] + [1])
        composition_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for label, seconds in composition:
            composition_box.pack_start(
                self._bar_row(
                    label,
                    self._duration(self.app, seconds),
                    seconds / composition_max,
                ),
                False,
                False,
                0,
            )
        self.content.pack_start(composition_box, False, False, 0)

        rows = self.app._activity_totals_for(day, include_unclassified=True)
        rows = sorted(
            rows,
            key=lambda item: int(item.get("work_seconds", 0)),
            reverse=True,
        )
        self._section_title(
            "Tempo per attività",
            "Le attività sono ordinate dalla più lunga alla più breve.",
        )
        if not rows:
            empty = Gtk.Label(label="Nessuna attività registrata per questa giornata.")
            empty.set_xalign(0)
            self.content.pack_start(empty, False, False, 0)
        else:
            activities_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            max_activity_seconds = max(
                [max(0, int(item.get("work_seconds", 0))) for item in rows] + [1]
            )
            for item in rows:
                seconds = max(0, int(item.get("work_seconds", 0)))
                activity = str(item.get("text", "")).strip() or "Tempo non classificato"
                project = str(item.get("project", "")).strip() or "Senza progetto"
                activities_box.pack_start(
                    self._bar_row(
                        activity,
                        self._duration(self.app, seconds),
                        seconds / max_activity_seconds,
                        project,
                    ),
                    False,
                    False,
                    0,
                )
            self.content.pack_start(activities_box, False, False, 0)

        self.content.show_all()


class DaySummaryWindow(Gtk.Window):
    """Riepilogo giornaliero con grafico, testo leggibile e Markdown."""

    def __init__(
        self,
        app: "WorkBreakApp",
        day: dt.date,
        parent: Optional[Gtk.Window] = None,
    ):
        super().__init__(title="Riepilogo giornaliero")
        self.app = app
        self.day = day
        if parent is not None:
            self.set_transient_for(parent)
            self.set_modal(True)
            self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        else:
            self.set_modal(False)
            self.set_position(Gtk.WindowPosition.CENTER)
        self.set_default_size(860, 680)
        self.set_border_width(14)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(outer)

        title = Gtk.Label(label=f"Riepilogo · {format_italian_markdown_date(day)}")
        title.set_xalign(0)
        title.modify_font(Pango.FontDescription("Sans Bold 17"))
        outer.pack_start(title, False, False, 0)

        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        outer.pack_start(self.notebook, True, True, 0)

        self.chart_view = DayChartView(app, day)
        self.notebook.append_page(self.chart_view, Gtk.Label(label="Grafico"))

        plain_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.plain_text_view = Gtk.TextView()
        self.plain_text_view.set_editable(False)
        self.plain_text_view.set_cursor_visible(False)
        self.plain_text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.plain_text_view.get_buffer().set_text(app.build_day_plain_text(day))
        plain_text_scroll = Gtk.ScrolledWindow()
        plain_text_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        plain_text_scroll.add(self.plain_text_view)
        plain_text_box.pack_start(plain_text_scroll, True, True, 0)
        self.notebook.append_page(plain_text_box, Gtk.Label(label="Solo testo"))

        markdown_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.markdown_view = Gtk.TextView()
        self.markdown_view.set_editable(True)
        self.markdown_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.markdown_view.set_monospace(True)
        self.markdown_view.get_buffer().set_text(app.build_day_markdown(day))
        markdown_scroll = Gtk.ScrolledWindow()
        markdown_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        markdown_scroll.add(self.markdown_view)
        markdown_box.pack_start(markdown_scroll, True, True, 0)
        self.notebook.append_page(markdown_box, Gtk.Label(label="Markdown"))

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer.pack_start(footer, False, False, 0)

        copy_text_button = Gtk.Button(label="Copia testo")
        copy_text_button.connect(
            "clicked",
            lambda button: self._copy_view_text(
                self.plain_text_view,
                button,
                "Copia testo",
            ),
        )
        footer.pack_start(copy_text_button, False, False, 0)

        copy_markdown_button = Gtk.Button(label="Copia Markdown")
        copy_markdown_button.connect(
            "clicked",
            lambda button: self._copy_view_text(
                self.markdown_view,
                button,
                "Copia Markdown",
            ),
        )
        footer.pack_start(copy_markdown_button, False, False, 0)

        refresh_button = Gtk.Button(label="Aggiorna riepilogo")
        refresh_button.connect("clicked", lambda *_: self._refresh_summary())
        footer.pack_start(refresh_button, False, False, 0)

        close_button = Gtk.Button(label="Chiudi")
        close_button.connect("clicked", lambda *_: self.destroy())
        footer.pack_end(close_button, False, False, 0)

        self.show_all()
        width, height = 860, 680
        geometry = active_monitor_geometry()
        if geometry is not None:
            width = max(620, min(width, geometry.width - 64))
            height = max(460, min(height, geometry.height - 96))
        self.resize(width, height)
        place_on_active_monitor(self, width, height)
        self.present()

    def _refresh_summary(self) -> None:
        self.chart_view.refresh()
        self.plain_text_view.get_buffer().set_text(
            self.app.build_day_plain_text(self.day)
        )
        self.markdown_view.get_buffer().set_text(
            self.app.build_day_markdown(self.day)
        )

    @staticmethod
    def _copy_view_text(
        text_view: Gtk.TextView,
        button: Gtk.Button,
        original_label: str,
    ) -> None:
        buffer = text_view.get_buffer()
        start, end = buffer.get_bounds()
        current_text = buffer.get_text(start, end, True)
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(current_text, -1)
        clipboard.store()
        button.set_label("Copiato")
        GLib.timeout_add_seconds(
            2,
            lambda: DaySummaryWindow._restore_copy_label(button, original_label),
        )

    @staticmethod
    def _restore_copy_label(button: Gtk.Button, original_label: str) -> bool:
        if button.get_parent() is not None:
            button.set_label(original_label)
        return False


class ActivitySummaryWindow(Gtk.Window):
    def __init__(self, app: "WorkBreakApp", selected_day: Optional[dt.date] = None):
        super().__init__(title="Attività e tempi")
        self.app = app
        self.selected_day = selected_day or dt.date.today()
        self._changing_day = False
        self.markdown_window: Optional[Gtk.Window] = None
        self.set_default_size(1180, 600)
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

        transfer_button = Gtk.Button(label="Trasferisci tempo in un altro task")
        transfer_button.connect("clicked", lambda *_: self._transfer_selected())
        transfer_button.set_tooltip_text(
            "Sposta tutto o parte del tempo del task selezionato verso un altro task della stessa giornata"
        )
        actions.pack_start(transfer_button, False, False, 0)

        delete_button = Gtk.Button(label="Elimina selezionata")
        delete_button.connect("clicked", lambda *_: self._delete_selected())
        actions.pack_start(delete_button, False, False, 0)

        markdown_button = Gtk.Button(label="Mostra riepilogo")
        markdown_button.connect("clicked", lambda *_: self._show_summary())
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
        place_on_active_monitor(self, 1180, 600)
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

    def _transfer_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            self._message("Nessuna selezione", "Seleziona prima il task da cui trasferire il tempo.")
            return
        if row["unclassified"]:
            self._message(
                "Tempo non classificato",
                "Prima assegna il tempo non classificato a un task, poi potrai trasferirlo.",
                Gtk.MessageType.WARNING,
            )
            return
        if row["seconds"] <= 0:
            self._message("Nessun tempo disponibile", "Il task selezionato non contiene tempo da trasferire.")
            return

        targets = []
        for item in self.app._activity_totals_for(self.selected_day):
            activity = str(item.get("text", "")).strip()
            project = str(item.get("project", "")).strip()
            if not activity or self.app._same_activity(item, row["activity"], row["project"]):
                continue
            targets.append(
                {
                    "activity": activity,
                    "project": project,
                    "seconds": max(0, int(item.get("work_seconds", 0))),
                }
            )

        if not targets:
            self._message(
                "Nessun task di destinazione",
                "Nella giornata deve esistere almeno un altro task a cui trasferire il tempo.",
                Gtk.MessageType.WARNING,
            )
            return

        dialog = TransferTimeDialog(self, row, targets)
        response = dialog.run()
        values = dialog.values() if response == Gtk.ResponseType.OK else None
        dialog.destroy()
        if values is None:
            return
        target, seconds = values
        if seconds <= 0:
            self._message(
                "Durata non valida",
                "Indica almeno un secondo da trasferire.",
                Gtk.MessageType.WARNING,
            )
            return
        if seconds > row["seconds"]:
            self._message(
                "Tempo insufficiente",
                "Non puoi trasferire più tempo di quello presente nel task di origine.",
                Gtk.MessageType.WARNING,
            )
            return

        changed = self.app.transfer_activity_time(
            self.selected_day,
            row["activity"],
            row["project"],
            str(target.get("activity", "")),
            str(target.get("project", "")),
            seconds,
        )
        if not changed:
            self._message(
                "Trasferimento non riuscito",
                "I task sono cambiati nel frattempo. Aggiorna la finestra e riprova.",
                Gtk.MessageType.WARNING,
            )
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

    def _show_summary(self) -> None:
        if self.markdown_window and self.markdown_window.get_visible():
            self.markdown_window.destroy()
        self.markdown_window = DaySummaryWindow(self.app, self.selected_day, self)

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
        credited_pause_seconds = self.app.credited_break_for_day_seconds(self.selected_day, stats)
        credited_pause = self.app._format_effective_minutes(credited_pause_seconds)
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

    def update(
        self,
        seconds_left: int,
        overrun_seconds: int = 0,
        started_late: bool = False,
    ) -> None:
        seconds_left = max(0, int(seconds_left))
        overrun_seconds = max(0, int(overrun_seconds))
        if overrun_seconds > 0:
            self.timer.set_text(format_negative_countdown(overrun_seconds))
            self.hint.set_text(
                "La pausa prevista è terminata e stai sforando da "
                f"{format_mmss(overrun_seconds)}. Premi il pulsante quando riprendi a lavorare."
            )
        elif seconds_left <= 0:
            self.timer.set_text("00:00")
            self.hint.set_text(
                "La pausa prevista è terminata. Se non riprendi ora, il timer inizierà a contare in negativo."
            )
        else:
            self.timer.set_text(format_mmss(seconds_left))
            if started_late:
                self.hint.set_text(
                    "Hai iniziato la pausa dopo la fine della mattina: il rientro è stato spostato "
                    "per garantirti l’intera pausa prevista. Puoi interromperla quando vuoi."
                )
            else:
                self.hint.set_text(
                    "Il countdown termina all’orario previsto di rientro. Se continui la pausa, "
                    "proseguirà in negativo finché non confermi di aver ripreso."
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
        self.persisted_settings = Settings.load()
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
                "giorno saranno conteggiate separatamente come EXTRA. Le modifiche al calendario "
                "saranno applicate al prossimo avvio, senza interrompere il timer corrente."
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
        persisted = Settings.load()
        persisted.custom_days_off = entries
        persisted.save()
        self.persisted_settings = persisted
        if self.app.settings_window and self.app.settings_window.get_visible():
            try:
                self.app.settings_window.edit_settings = persisted
                self.app.settings_window.holidays_count.set_text(
                    f"{len(persisted.custom_days_off)} date o intervalli personalizzati"
                )
                self.app.settings_window.save_status.set_text(
                    "Calendario salvato. Sarà applicato al prossimo avvio senza "
                    "interrompere il timer corrente."
                )
            except Exception:
                pass
        self.refresh()

    def _add_entry(self) -> None:
        values = self._open_editor("Aggiungi data o giornata lavorativa extra")
        if values is None:
            return
        entries = list(self.persisted_settings.custom_days_off)
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
        entries = list(self.persisted_settings.custom_days_off)
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
            for item in self.persisted_settings.custom_days_off
            if normalize_day_off_entry(item) != normalized_selected
        ]
        self._save_entries(entries)

    def refresh(self) -> None:
        self.store.clear()
        for entry in self.persisted_settings.custom_days_off:
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
    RESTART_FIELDS = (
        "work_minutes",
        "break_minutes",
        "regular_pause_credit_minutes",
        "daily_pause_extra_credit_minutes",
        "daily_target_hours",
        "warning_seconds",
        "overtime_reminder_minutes",
        "extra_closure_day",
        "extra_closure_weekday",
        "active_days",
        "morning_start",
        "morning_end",
        "afternoon_start",
        "afternoon_end",
        "skip_italian_holidays",
        "local_holidays",
        "custom_days_off",
    )

    IMMEDIATE_FIELDS = (
        "audio_enabled",
        "timer_end_sound",
        "beep_volume",
        "beep_count",
        "beep_interval_seconds",
        "markdown_include_task_times",
    )

    def __init__(self, app: "WorkBreakApp"):
        super().__init__(title="Impostazioni WorkBreak Guard")
        self.app = app
        # Mostra sempre i valori già salvati su disco. Durante l'esecuzione le
        # impostazioni strutturali possono essere diverse da quelle attive,
        # perché vengono applicate soltanto al prossimo avvio.
        self.edit_settings = Settings.load()
        screen = Gdk.Screen.get_default()
        available_width = screen.get_width() - 100 if screen else 720
        available_height = screen.get_height() - 100 if screen else 760
        self.set_default_size(
            max(560, min(760, available_width)),
            max(420, min(820, available_height)),
        )
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(18)
        self.set_keep_above(False)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(outer)

        title = Gtk.Label(label="Impostazioni pause")
        title.set_xalign(0)
        title.modify_font(Pango.FontDescription("Sans Bold 18"))
        outer.pack_start(title, False, False, 0)

        apply_notice = Gtk.Label(
            label=(
                "Le voci contrassegnate con ↻ vengono salvate senza interrompere il lavoro "
                "e saranno applicate al prossimo avvio del programma."
            )
        )
        apply_notice.set_xalign(0)
        apply_notice.set_line_wrap(True)
        outer.pack_start(apply_notice, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.IN)
        outer.pack_start(scrolled, True, True, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        content.set_border_width(10)
        scrolled.add_with_viewport(content)

        actions_frame = Gtk.Frame(label="Azioni programma")
        actions_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        actions_grid.set_column_homogeneous(True)
        actions_grid.set_border_width(10)
        actions_frame.add(actions_grid)
        content.pack_start(actions_frame, False, False, 0)

        reset_now = Gtk.Button(label="Resetta e comincia adesso")
        reset_now.connect("clicked", lambda *_: app.reset_and_start_now())
        actions_grid.attach(reset_now, 0, 0, 1, 1)

        activities = Gtk.Button(label="Attività e tempi")
        activities.connect("clicked", lambda *_: app.show_activity_summary())
        actions_grid.attach(activities, 1, 0, 1, 1)

        day_offs = Gtk.Button(label="Ferie, festività e giornate EXTRA")
        day_offs.connect("clicked", lambda *_: app.show_day_off_manager())
        actions_grid.attach(day_offs, 0, 1, 1, 1)

        show_control = Gtk.Button(label="Mostra controllo")
        show_control.connect("clicked", lambda *_: app.show_control())
        actions_grid.attach(show_control, 1, 1, 1, 1)

        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        grid.set_column_homogeneous(False)
        content.pack_start(grid, False, False, 0)

        self.enabled = Gtk.CheckButton(
            label="Promemoria attivo (usa il pulsante in basso per disattivarlo o riattivarlo)"
        )
        self.enabled.set_active(app.settings.enabled)
        self.enabled.set_sensitive(False)
        grid.attach(self.enabled, 0, 0, 2, 1)

        self.audio = Gtk.CheckButton(label="Audio attivo, con volume lieve")
        self.audio.set_active(self.edit_settings.audio_enabled)
        grid.attach(self.audio, 0, 1, 2, 1)

        self.skip_holidays = Gtk.CheckButton(label="↻ Non contare le festività nazionali italiane")
        self.skip_holidays.set_active(self.edit_settings.skip_italian_holidays)
        grid.attach(self.skip_holidays, 0, 2, 2, 1)

        self.este_holiday = Gtk.CheckButton(label="↻ Includi Santa Tecla, patrona di Este — 23 settembre")
        self.este_holiday.set_active("este" in self.edit_settings.local_holidays)
        grid.attach(self.este_holiday, 0, 3, 2, 1)

        self.florence_holiday = Gtk.CheckButton(
            label="↻ Includi San Giovanni Battista, patrono di Firenze — 24 giugno"
        )
        self.florence_holiday.set_active("firenze" in self.edit_settings.local_holidays)
        grid.attach(self.florence_holiday, 0, 4, 2, 1)

        self.autostart_enabled = Gtk.CheckButton(label="Avvia automaticamente all'accesso")
        self.autostart_enabled.set_active(is_autostart_enabled())
        grid.attach(self.autostart_enabled, 0, 5, 2, 1)

        self.work_minutes = self._spin(self.edit_settings.work_minutes, 5, 240)
        self.break_minutes = self._spin(self.edit_settings.break_minutes, 1, 60)
        self.regular_pause_credit_minutes = self._spin(
            self.edit_settings.regular_pause_credit_minutes, 0, 60
        )
        self.daily_pause_extra_credit_minutes = self._spin(
            self.edit_settings.daily_pause_extra_credit_minutes, 0, 240
        )
        self.daily_target_hours = self._spin(self.edit_settings.daily_target_hours, 1, 24)
        self.warning_seconds = self._spin(self.edit_settings.warning_seconds, 5, 600)
        self.overtime_reminder_minutes = self._spin(self.edit_settings.overtime_reminder_minutes, 1, 120)
        self.extra_closure_day = self._spin(self.edit_settings.extra_closure_day, 1, 28)
        self.extra_closure_weekday = Gtk.ComboBoxText()
        for index, weekday_name in enumerate(
            ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
        ):
            self.extra_closure_weekday.append(str(index), weekday_name)
        self.extra_closure_weekday.set_active_id(str(self.edit_settings.extra_closure_weekday))
        self.timer_end_sound = Gtk.ComboBoxText()
        for sound_id, sound_label in TIMER_END_SOUND_OPTIONS.items():
            self.timer_end_sound.append(sound_id, sound_label)
        self.timer_end_sound.set_active_id(self.edit_settings.timer_end_sound)
        timer_sound_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        timer_sound_box.pack_start(self.timer_end_sound, True, True, 0)
        preview_sound = Gtk.Button(label="Prova")
        preview_sound.connect("clicked", self._preview_timer_sound)
        timer_sound_box.pack_start(preview_sound, False, False, 0)
        self.timer_sound_box = timer_sound_box
        self.beep_count = self._spin(self.edit_settings.beep_count, 0, 20)
        self.beep_interval = self._spin(self.edit_settings.beep_interval_seconds, 5, 300)
        self.volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 30, 1)
        self.volume.set_value(int(self.edit_settings.beep_volume * 100))
        self.volume.set_digits(0)

        row = 6
        row = self._labeled(grid, row, "↻ Minuti lavoro", self.work_minutes)
        row = self._labeled(grid, row, "↻ Minuti pausa", self.break_minutes)
        row = self._labeled(
            grid,
            row,
            "↻ Quota pausa regolare ogni 2 ore, minuti",
            self.regular_pause_credit_minutes,
        )
        row = self._labeled(
            grid,
            row,
            "↻ Abbuono extra giornaliero pause, minuti",
            self.daily_pause_extra_credit_minutes,
        )
        row = self._labeled(grid, row, "↻ Tempo massimo per giornata, ore", self.daily_target_hours)
        row = self._labeled(grid, row, "↻ Tempo predefinito prima di 'Fermati subito', secondi", self.warning_seconds)
        row = self._labeled(
            grid,
            row,
            "↻ Promemoria lavoro oltre orario, minuti",
            self.overtime_reminder_minutes,
        )
        row = self._labeled(
            grid,
            row,
            "↻ Chiusura mensile EXTRA: giorno base del mese",
            self.extra_closure_day,
        )
        row = self._labeled(
            grid,
            row,
            "↻ Primo giorno uguale o successivo per la chiusura",
            self.extra_closure_weekday,
        )
        row = self._labeled(
            grid, row, "Suono alla scadenza dei timer", self.timer_sound_box
        )
        row = self._labeled(grid, row, "Numero beep in pausa", self.beep_count)
        row = self._labeled(grid, row, "Distanza beep, secondi", self.beep_interval)
        row = self._labeled(grid, row, "Volume beep 0-30%", self.volume)

        self.morning_start = Gtk.Entry(text=self.edit_settings.morning_start)
        self.morning_end = Gtk.Entry(text=self.edit_settings.morning_end)
        self.afternoon_start = Gtk.Entry(text=self.edit_settings.afternoon_start)
        self.afternoon_end = Gtk.Entry(text=self.edit_settings.afternoon_end)
        row = self._labeled(grid, row, "↻ Mattina inizio HH:MM", self.morning_start)
        row = self._labeled(grid, row, "↻ Mattina fine HH:MM", self.morning_end)
        row = self._labeled(grid, row, "↻ Pomeriggio inizio HH:MM", self.afternoon_start)
        row = self._labeled(grid, row, "↻ Pomeriggio fine HH:MM", self.afternoon_end)

        days_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.days = []
        for idx, name in enumerate(["L", "M", "M", "G", "V", "S", "D"]):
            chk = Gtk.CheckButton(label=name)
            chk.set_active(idx in self.edit_settings.active_days)
            self.days.append(chk)
            days_box.pack_start(chk, False, False, 0)
        row = self._labeled(grid, row, "↻ Giorni attivi", days_box)

        holidays_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.holidays_count = Gtk.Label(
            label=f"{len(self.edit_settings.custom_days_off)} date o intervalli personalizzati"
        )
        self.holidays_count.set_xalign(0)
        holidays_box.pack_start(self.holidays_count, True, True, 0)
        row = self._labeled(grid, row, "↻ Calendario e giornate EXTRA", holidays_box)

        self.markdown_include_task_times = Gtk.CheckButton(
            label="Mostra il tempo impiegato per ogni task nel Markdown"
        )
        self.markdown_include_task_times.set_active(self.edit_settings.markdown_include_task_times)
        grid.attach(self.markdown_include_task_times, 0, row, 2, 1)
        row += 1

        self.save_status = Gtk.Label(label="")
        self.save_status.set_xalign(0)
        self.save_status.set_line_wrap(True)
        outer.pack_start(self.save_status, False, False, 0)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        outer.pack_start(controls, False, False, 0)

        save = Gtk.Button(label="Salva")
        save.connect("clicked", self._save)
        controls.pack_start(save, False, False, 0)

        pause = Gtk.Button(label="Disattiva/Riattiva promemoria")
        pause.connect("clicked", lambda *_: app.toggle_enabled())
        controls.pack_start(pause, False, False, 0)

        start_break = Gtk.Button(label="Metti in pausa")
        start_break.connect("clicked", lambda *_: app.request_manual_pause())
        controls.pack_start(start_break, False, False, 0)

        close = Gtk.Button(label="Chiudi")
        close.connect("clicked", lambda *_: self.destroy())
        controls.pack_end(close, False, False, 0)

        self.show_all()

    def _preview_timer_sound(self, *_args) -> None:
        sound_id = self.timer_end_sound.get_active_id() or "soft"
        self.app._play_sound(sound_id)

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
        # Costruisce una copia destinata al file di configurazione senza
        # modificare la configurazione strutturale usata dal timer corrente.
        current = self.app.settings
        pending = Settings(**asdict(Settings.load()))
        pending.enabled = current.enabled
        pending.audio_enabled = self.audio.get_active()
        pending.skip_italian_holidays = self.skip_holidays.get_active()
        pending.local_holidays = []
        if self.este_holiday.get_active():
            pending.local_holidays.append("este")
        if self.florence_holiday.get_active():
            pending.local_holidays.append("firenze")
        pending.work_minutes = int(self.work_minutes.get_value())
        pending.break_minutes = int(self.break_minutes.get_value())
        pending.regular_pause_credit_minutes = int(
            self.regular_pause_credit_minutes.get_value()
        )
        pending.daily_pause_extra_credit_minutes = int(
            self.daily_pause_extra_credit_minutes.get_value()
        )
        pending.daily_target_hours = int(self.daily_target_hours.get_value())
        pending.warning_seconds = int(self.warning_seconds.get_value())
        pending.overtime_reminder_minutes = int(
            self.overtime_reminder_minutes.get_value()
        )
        pending.extra_closure_day = int(self.extra_closure_day.get_value())
        pending.markdown_include_task_times = (
            self.markdown_include_task_times.get_active()
        )
        try:
            pending.extra_closure_weekday = int(
                self.extra_closure_weekday.get_active_id() or 0
            )
        except Exception:
            pending.extra_closure_weekday = 0
        pending.timer_end_sound = self.timer_end_sound.get_active_id() or "soft"
        pending.beep_count = int(self.beep_count.get_value())
        pending.beep_interval_seconds = int(self.beep_interval.get_value())
        pending.beep_volume = float(self.volume.get_value()) / 100.0
        pending.morning_start = self.morning_start.get_text()
        pending.morning_end = self.morning_end.get_text()
        pending.afternoon_start = self.afternoon_start.get_text()
        pending.afternoon_end = self.afternoon_end.get_text()
        pending.active_days = [
            idx for idx, chk in enumerate(self.days) if chk.get_active()
        ]
        pending.save()

        restart_required = any(
            getattr(current, field_name) != getattr(pending, field_name)
            for field_name in self.RESTART_FIELDS
        )

        # Solo le preferenze realmente innocue vengono applicate subito.
        # Non richiamare reload_schedule(), toggle_enabled() o metodi di reset:
        # salvare non deve mai alterare fase, residuo o attività corrente.
        for field_name in self.IMMEDIATE_FIELDS:
            setattr(current, field_name, getattr(pending, field_name))

        set_autostart_enabled(self.autostart_enabled.get_active())
        self.enabled.set_active(current.enabled)
        self.app.update_indicator_menu()
        self.app._update_ui()

        if restart_required:
            self.save_status.set_text(
                "Salvato. Le modifiche contrassegnate con ↻ saranno applicate "
                "al prossimo avvio; il timer corrente continua senza interruzioni."
            )
        else:
            self.save_status.set_text(
                "Salvato. Le preferenze immediate sono state aggiornate senza "
                "interrompere il timer."
            )


class ControlWindow(Gtk.Window):
    def __init__(self, app: "WorkBreakApp"):
        super().__init__(title=APP_NAME)
        self.app = app
        self.set_default_size(560, 260)
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

        manual_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.pack_start(manual_actions, False, False, 0)
        self.start_now_btn = Gtk.Button(label="Inizia a lavorare adesso")
        self.start_now_btn.connect("clicked", lambda *_: app.request_start_work_now())
        manual_actions.pack_start(self.start_now_btn, True, True, 0)
        self.manual_pause_btn = Gtk.Button(label="Pausa manuale…")
        self.manual_pause_btn.connect("clicked", lambda *_: app.request_manual_pause())
        manual_actions.pack_start(self.manual_pause_btn, True, True, 0)
        self.finish_day_btn = Gtk.Button(label="Termina giornata")
        self.finish_day_btn.connect("clicked", lambda *_: app.request_finish_day_early())
        manual_actions.pack_start(self.finish_day_btn, True, True, 0)
        self.show_all()

    def _on_delete(self, *_args) -> bool:
        self.hide()
        return True

    def update(self, text: str, enabled: bool) -> None:
        self.status.set_text(text)
        self.toggle_btn.set_label("Disattiva Promemoria" if enabled else "Riattiva promemoria")
        if self.app.in_midday_recovery:
            self.start_now_btn.set_label("Interrompi pausa e inizia")
        elif self.app.day_suspended:
            self.start_now_btn.set_label("Riprendi la giornata")
        else:
            self.start_now_btn.set_label("Inizia a lavorare adesso")
        self.start_now_btn.set_sensitive(
            enabled
            and (
                self.app.day_suspended
                or self.app.in_midday_recovery
                or self.app.current_session is None
                or self.app.waiting_session_start
                or self.app.manual_break
                or self.app.in_break
                or self.app.waiting_return
            )
        )
        self.manual_pause_btn.set_label(
            "Riprendi il lavoro"
            if self.app.manual_break or self.app.in_break or self.app.waiting_return
            else "Pausa manuale…"
        )
        self.manual_pause_btn.set_sensitive(
            enabled and self.app.current_session is not None and not self.app.day_suspended
        )
        self.finish_day_btn.set_sensitive(
            enabled
            and self.app.current_session is not None
            and not self.app.day_suspended
            and not self.app.waiting_session_start
            and not self.app.waiting_daily_close_choice
            and not self.app.in_midday_recovery
        )


class WorkBreakApp:
    def __init__(self):
        self.settings = Settings.load()
        self.work_remaining = self.settings.work_minutes * 60
        self.grace_remaining = 0
        self.break_remaining = 0
        self.break_elapsed = 0
        self.regular_break_credit_remaining = 0
        self.break_credit_eligible_seconds = 0
        self.break_planned_seconds = 0
        self.break_credited_seconds = 0
        self.return_overrun_seconds = 0
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
        self.midday_recovery_overrun_seconds = 0
        self.midday_recovery_started_late = False
        self.afternoon_started_early = False
        self.waiting_daily_close_choice = False
        self.compensating_daily_balance = False
        self.compensation_remaining = 0
        self.compensation_day: Optional[dt.date] = None
        self.break_truncated_by_day_end = False
        self.manual_break = False
        self.manual_break_indefinite = False
        self.manual_schedule_override = False
        self.manual_open_ended_work = False
        self.day_suspended = False
        # Quando i promemoria vengono riattivati con “Continua”, il ciclo deve
        # conservare esattamente il residuo congelato senza essere ricappato
        # automaticamente all'orario di fine fascia.
        self.resume_preserves_cycle = False
        self.pending_manual_session: Optional[str] = None
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
        self.day_markdown_window: Optional[DaySummaryWindow] = None
        self.day_off_window: Optional[DayOffManagerWindow] = None
        self.session_end_window: Optional[ChoiceAlertWindow] = None
        self.midday_recovery_window: Optional[MiddayRecoveryWindow] = None
        self.daily_close_window: Optional[ChoiceAlertWindow] = None
        self.compensation_window: Optional[DailyCompensationWindow] = None
        self.manual_pause_window: Optional[ManualPauseWindow] = None
        self.regular_pause_window: Optional[RegularPauseWindow] = None
        self.reminder_reactivation_window: Optional[ChoiceAlertWindow] = None
        self.regular_pause_origin = "stop"
        # Mantenuti per compatibilità interna, ma i countdown non usano più popup.
        self.break_window: Optional[BreakCountdown] = None
        self.clock = ClockOverlay()
        self.clock.hide()
        self.settings_window: Optional[SettingsWindow] = None
        self.control_window: Optional[ControlWindow] = None
        self.indicator = None
        self.indicator_status_item: Optional[Gtk.MenuItem] = None
        self.indicator_toggle_item: Optional[Gtk.MenuItem] = None
        self.sound_files: dict[str, Path] = {}
        self.beep_file = self._build_sound_file("soft")

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
        menu.append(Gtk.SeparatorMenuItem())

        self.indicator_toggle_item = Gtk.MenuItem(
            label="Disattiva Promemoria" if self.settings.enabled else "Riattiva promemoria"
        )
        self.indicator_toggle_item.connect("activate", lambda *_: self.toggle_enabled())
        menu.append(self.indicator_toggle_item)

        activity_item = Gtk.MenuItem(
            label="Cosa stai facendo adesso? (CTRL + ALT + Q)"
        )
        activity_item.connect("activate", lambda *_: self.request_activity_prompt())
        menu.append(activity_item)

        if (
            self.day_suspended
            or self.current_session is None
            or self.waiting_session_start
            or self.in_midday_recovery
        ):
            if self.in_midday_recovery:
                start_label = "Interrompi la pausa e inizia adesso"
            elif self.day_suspended:
                start_label = "Riprendi la giornata adesso"
            else:
                start_label = "Inizia a lavorare adesso"
            start_or_resume = Gtk.MenuItem(label=start_label)
            start_or_resume.connect("activate", lambda *_: self.request_start_work_now())
            menu.append(start_or_resume)

        if self.manual_break or self.in_break or self.waiting_return:
            pause_item = Gtk.MenuItem(label="Riprendi il lavoro adesso")
            pause_item.connect("activate", lambda *_: self.resume_work_now())
        else:
            pause_item = Gtk.MenuItem(label="Metti in pausa")
            pause_item.connect("activate", lambda *_: self.request_manual_pause())
        menu.append(pause_item)

        if (
            self.current_session is not None
            and not self.day_suspended
            and not self.waiting_session_start
            and not self.waiting_daily_close_choice
            and not self.in_midday_recovery
        ):
            finish_day = Gtk.MenuItem(label="Termina la giornata adesso")
            finish_day.connect("activate", lambda *_: self.request_finish_day_early())
            menu.append(finish_day)

        if self.compensating_daily_balance:
            finish_now = Gtk.MenuItem(label="Concludi definitivamente adesso")
            finish_now.connect("activate", lambda *_: self.finish_daily_compensation_now())
            menu.append(finish_now)

        menu.append(Gtk.SeparatorMenuItem())

        markdown_item = Gtk.MenuItem(label="Mostra riepilogo")
        markdown_item.connect("activate", lambda *_: self.show_day_markdown())
        menu.append(markdown_item)

        menu.append(Gtk.SeparatorMenuItem())

        settings = Gtk.MenuItem(label="Impostazioni")
        settings.connect("activate", lambda *_: self.show_settings())
        menu.append(settings)

        menu.append(Gtk.SeparatorMenuItem())

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
        if self.day_markdown_window and self.day_markdown_window.get_visible():
            self.day_markdown_window.destroy()
        parent: Optional[Gtk.Window] = None
        if self.summary_window and self.summary_window.get_visible():
            parent = self.summary_window
        elif self.control_window and self.control_window.get_visible():
            parent = self.control_window
        elif self.settings_window and self.settings_window.get_visible():
            parent = self.settings_window
        self.day_markdown_window = DaySummaryWindow(self, selected_day, parent)

    def toggle_enabled(self) -> None:
        if self.settings.enabled:
            self._pause_reminders()
        else:
            self._request_reminder_reactivation()

    def _hide_runtime_windows_for_reminder_pause(self) -> None:
        """Chiude gli avvisi operativi senza alterare la macchina a stati."""
        for attr in (
            "warning_window",
            "grace_choice_window",
            "stop_window",
            "return_window",
            "session_window",
            "activity_window",
            "break_window",
            "session_end_window",
            "midday_recovery_window",
            "daily_close_window",
            "compensation_window",
            "manual_pause_window",
            "regular_pause_window",
        ):
            window = getattr(self, attr, None)
            try:
                if window:
                    window.destroy()
            except Exception:
                pass
            setattr(self, attr, None)
        self.clock.hide()

    def _persist_runtime_enabled(self) -> None:
        """Salva solo lo stato attivo senza sovrascrivere opzioni in attesa di riavvio."""
        persisted = Settings.load()
        persisted.enabled = self.settings.enabled
        persisted.save()

    def _pause_reminders(self) -> None:
        """Congela il timer corrente senza azzerare fase, residui o attività."""
        if not self.settings.enabled:
            return
        self._save_activity_log()
        # Salva prima lo stato mentre è ancora attivo, poi persiste anche il flag
        # di pausa. Il payload resta valido anche con settings.enabled=False.
        self._save_runtime_state(force=True)
        self.settings.enabled = False
        self._persist_runtime_enabled()
        self._hide_runtime_windows_for_reminder_pause()
        self._save_runtime_state(force=True)
        self.update_indicator_menu()
        self._update_ui()

    def _request_reminder_reactivation(self) -> None:
        if self.settings.enabled:
            return
        if self.reminder_reactivation_window and self.reminder_reactivation_window.get_visible():
            self.reminder_reactivation_window.present()
            return

        if self.current_session is not None and self.current_session_date == dt.date.today():
            frozen = self.compact_frozen_timer_text()
            message = (
                f"Il promemoria è fermo su {frozen}. Vuoi riprendere esattamente "
                "dal punto interrotto oppure avviare un nuovo conteggio completo?"
            )
        else:
            message = (
                "Non c’è un ciclo odierno da riprendere. Puoi comunque riattivare "
                "il promemoria oppure ricominciare il conteggio nella fascia corrente."
            )

        self.reminder_reactivation_window = ChoiceAlertWindow(
            "Riattiva promemoria",
            message,
            [
                ("Continua da dove interrotto", self._continue_frozen_reminders),
                ("Ricomincia il conteggio", self._restart_reminder_count),
                ("Annulla", self._cancel_reminder_reactivation),
            ],
        )

    def _cancel_reminder_reactivation(self) -> None:
        self.reminder_reactivation_window = None

    def compact_frozen_timer_text(self) -> str:
        if self.in_break:
            return "pausa senza scadenza" if self.manual_break_indefinite else f"pausa {format_mmss(self.break_remaining)}"
        if self.waiting_return:
            return f"rientro {format_negative_countdown(self.return_overrun_seconds)}"
        if self.in_grace:
            return f"ultimatum {format_mmss(self.grace_remaining)}"
        if self.in_midday_recovery:
            value = (
                format_negative_countdown(self.midday_recovery_overrun_seconds)
                if self.midday_recovery_overrun_seconds > 0
                else format_mmss(self.midday_recovery_remaining)
            )
            return f"recupero mattutino {value}"
        if self.in_overtime:
            return f"lavoro oltre orario +{format_mmss(self.overtime_seconds)}"
        if self.compensating_daily_balance:
            return f"compensazione {format_mmss(self.compensation_remaining)}"
        return f"timer lavoro {format_mmss(self.work_remaining)}"

    def _enable_reminders_base(self) -> dt.datetime:
        self.reminder_reactivation_window = None
        self.settings.enabled = True
        self._persist_runtime_enabled()
        return dt.datetime.now()

    def _continue_frozen_reminders(self) -> None:
        """Riprende esattamente fase e residui congelati nello stesso giorno."""
        now = self._enable_reminders_base()
        if self.current_session is None or self.current_session_date != now.date():
            # Uno stato di un giorno precedente non può essere attribuito alla
            # giornata nuova: in quel caso si applica il normale avvio odierno.
            self._clear_runtime_state()
            self._reset_runtime_state()
            self.current_session = None
            self.current_session_date = None
            self._sync_session(now, force=True)
        else:
            self.resume_preserves_cycle = True
            self._save_runtime_state(force=True)
            self.update_indicator_menu()
            self._update_ui()
            GLib.idle_add(self._restore_pending_runtime_window)

    def _restart_reminder_count(self) -> None:
        """Azzera la fase congelata e avvia un nuovo ciclo di lavoro."""
        now = self._enable_reminders_base()
        previous_session = self.current_session
        previous_date = self.current_session_date
        previous_manual_override = self.manual_schedule_override
        previous_activity = self.current_activity
        previous_project = self.current_project

        scheduled_session = self.session_for(now)
        session = scheduled_session
        if session is None and previous_date == now.date() and previous_session in {"morning", "afternoon"}:
            # La scelta esplicita di ricominciare consente di ripartire anche se
            # nel frattempo si è usciti dalla fascia in cui il timer era fermo.
            session = previous_session

        self._clear_runtime_state()
        self._reset_runtime_state()
        self.current_activity = previous_activity
        self.current_project = previous_project
        self.current_session = session
        self.current_session_date = now.date() if session else None

        if session is None:
            self._sync_session(now, force=True)
            self.update_indicator_menu()
            self._update_ui()
            return

        self.manual_schedule_override = previous_manual_override or scheduled_session != session
        self.manual_open_ended_work = now >= self._session_boundary(session, now.date(), end=True)
        self.afternoon_started_early = (
            session == "afternoon"
            and now < self._session_boundary("afternoon", now.date(), end=False)
        )
        self.resume_preserves_cycle = False
        self.work_remaining = self._work_cycle_seconds_for_now(now, session)
        self.waiting_session_start = not bool(self.current_activity)
        self._mark_day_reopened(now.date())
        if self.current_activity:
            self._record_activity(self.current_activity, self.current_project)
        else:
            self._show_session_start_prompt(session)
        self._save_runtime_state(force=True)
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
        self._mark_day_reopened(now.date())
        self.work_remaining = self._work_cycle_seconds_for_now(now, session)
        if self.current_activity:
            self.waiting_session_start = False
            self._record_activity(self.current_activity, self.current_project)
        else:
            self.waiting_session_start = True
            self._show_session_start_prompt(session)
        self._save_runtime_state(force=True)
        self.update_indicator_menu()
        self._update_ui()

    def _manual_session_for_now(self, now: dt.datetime) -> str:
        morning_end = self._session_boundary("morning", now.date(), end=True)
        return "morning" if now < morning_end else "afternoon"

    def _mark_day_reopened(self, day: dt.date) -> None:
        stats = self._stats_for(day)
        self._ensure_target_snapshot(day, stats)
        stats["day_closed"] = False
        stats["close_choice"] = "Giornata riaperta manualmente"
        stats["balance_delta_seconds"] = None
        stats["summary_shown"] = False
        self._save_activity_log()

    def request_start_work_now(self) -> None:
        if not self.settings.enabled:
            AlertWindow(
                "Promemoria disattivato",
                "Riattiva prima il promemoria per iniziare a lavorare.",
                "OK",
            )
            return
        if self.in_midday_recovery:
            self.start_afternoon_from_recovery()
            return
        if self.manual_break or self.in_break or self.waiting_return:
            self.resume_work_now()
            return
        if self.waiting_session_start and self.current_session is not None:
            self._show_session_start_prompt()
            return
        if self.current_session is not None and not self.day_suspended:
            AlertWindow(
                "Giornata già in corso",
                "Il conteggio del lavoro è già attivo. Puoi cambiare attività, avviare una pausa manuale oppure terminare la giornata.",
                "OK",
            )
            return
        if self.activity_window and self.activity_window.get_visible():
            self.activity_window.present()
            return
        now = dt.datetime.now()
        self.pending_manual_session = self._manual_session_for_now(now)
        title = "Riprendiamo la giornata?" if self.day_suspended else "Inizia a lavorare adesso"
        question = (
            "Cosa stai facendo oggi?"
            if not self.day_suspended and self.pending_manual_session == "morning"
            else "Cosa stai facendo adesso?"
        )
        self.activity_window = ActivityPromptWindow(
            title,
            self.current_activity,
            self.current_project,
            self._recent_activity_options(),
            self._project_suggestions(),
            self._begin_manual_work,
            self._dismiss_activity_prompt,
            activity_question=question,
        )

    def _begin_manual_work(self, activity: str, project: str) -> None:
        now = dt.datetime.now()
        session = self.pending_manual_session or self._manual_session_for_now(now)
        self.activity_window = None
        self._reset_runtime_state()
        self.current_session = session
        self.current_session_date = now.date()
        self.manual_schedule_override = True
        self.afternoon_started_early = (
            session == "afternoon"
            and now < self._session_boundary("afternoon", now.date(), end=False)
        )
        self.manual_open_ended_work = now >= self._session_boundary(session, now.date(), end=True)
        self.work_remaining = self._work_cycle_seconds_for_now(now, session)
        self.waiting_session_start = False
        self._mark_day_reopened(now.date())
        self._record_activity(activity, project)
        self._save_runtime_state(force=True)
        self.update_indicator_menu()
        self._update_ui()

    def request_manual_pause(self) -> None:
        if self.day_suspended:
            AlertWindow(
                "Giornata terminata",
                "Riprendi prima la giornata, poi potrai avviare una pausa manuale.",
                "OK",
            )
            return
        if self.current_session is None or self.waiting_session_start:
            AlertWindow(
                "Lavoro non avviato",
                "Inizia prima a lavorare con ‘Inizia a lavorare adesso’.",
                "OK",
            )
            return
        if self.waiting_daily_close_choice or self.compensating_daily_balance or self.in_midday_recovery:
            AlertWindow(
                "Azione non disponibile",
                "Concludi prima la fase corrente, poi potrai avviare una pausa manuale.",
                "OK",
            )
            return
        if self.waiting_session_end:
            self._show_session_end_prompt()
            return
        if self.manual_break or self.in_break or self.waiting_return:
            self.resume_work_now()
            return
        if self.manual_pause_window and self.manual_pause_window.get_visible():
            self.manual_pause_window.present()
            return
        self.manual_pause_window = ManualPauseWindow(self)

    def start_manual_break(self, minutes: Optional[int]) -> None:
        if self.current_session is None or self.day_suspended:
            return
        for attr in ("grace_choice_window", "stop_window", "warning_window"):
            window = getattr(self, attr, None)
            try:
                if window:
                    window.destroy()
            except Exception:
                pass
            setattr(self, attr, None)
        self.waiting_grace_choice = False
        self.waiting_break_start = False
        self.in_grace = False
        self.in_overtime = False
        self.waiting_session_end = False
        self.in_break = True
        self.waiting_return = False
        self.manual_break = True
        self.manual_break_indefinite = minutes is None
        self.break_remaining = 0 if minutes is None else max(1, int(minutes)) * 60
        self.break_elapsed = 0
        self.regular_break_credit_remaining = 0
        self.break_credit_eligible_seconds = 0
        self.break_planned_seconds = self.break_remaining
        self.break_credited_seconds = 0
        self.return_overrun_seconds = 0
        self.break_truncated_by_day_end = False
        self._play_beep_once()
        self._save_runtime_state(force=True)
        self.update_indicator_menu()
        self._update_ui()

    def resume_work_now(self) -> None:
        if self.day_suspended:
            self.request_start_work_now()
            return
        if not (self.manual_break or self.in_break or self.waiting_return):
            self.request_start_work_now()
            return
        self.in_break = False
        if not self.waiting_return:
            self.return_overrun_seconds = 0
        self.waiting_return = True
        self.break_remaining = 0
        self._save_runtime_state(force=True)
        self._show_return_activity_prompt()
        self.update_indicator_menu()
        self._update_ui()

    def request_finish_day_early(self) -> None:
        if self.compensating_daily_balance:
            self.finish_daily_compensation_now()
            return
        if self.waiting_daily_close_choice:
            self._show_daily_close_choice()
            return
        if self.in_midday_recovery:
            AlertWindow(
                "Pausa mattutina in corso",
                "Interrompi o completa prima il recupero della pausa mattutina.",
                "OK",
            )
            return
        if self.current_session is None or self.day_suspended or self.waiting_session_start:
            AlertWindow(
                "Giornata non attiva",
                "Non c’è una giornata di lavoro già avviata da terminare.",
                "OK",
            )
            return
        day = self.current_session_date or dt.date.today()
        remaining = self.balance_remaining_for_day_seconds(day)
        if self._day_participates_in_balance(day):
            balance_text = (
                f"Al momento mancano {format_signed_hours_minutes(remaining)}. "
                if remaining > 0
                else "L’obiettivo e il saldo corrente risultano coperti. "
            )
        else:
            balance_text = "Il tempo registrato resterà classificato secondo il tipo di giornata. "
        ChoiceAlertWindow(
            "Terminare la giornata adesso?",
            balance_text
            + "La giornata verrà fermata immediatamente. Potrai comunque riaprirla più tardi con ‘Riprendi la giornata adesso’.",
            [
                ("Termina la giornata", self._finish_day_early),
                ("Annulla", lambda: None),
            ],
        )

    def _finish_day_early(self) -> None:
        if self.current_session is None:
            return
        day = self.current_session_date or dt.date.today()
        if self.waiting_session_end:
            pending = max(0, int(self.end_prompt_unaccounted_seconds))
            if pending:
                self._record_work_seconds(day, pending, overtime=True)
                self.overtime_seconds += pending
        for attr in (
            "grace_choice_window",
            "stop_window",
            "return_window",
            "session_window",
            "session_end_window",
            "manual_pause_window",
            "regular_pause_window",
        ):
            window = getattr(self, attr, None)
            try:
                if window:
                    window.destroy()
            except Exception:
                pass
            setattr(self, attr, None)
        self.waiting_session_start = False
        self.waiting_grace_choice = False
        self.waiting_break_start = False
        self.in_grace = False
        self.in_break = False
        self.waiting_return = False
        self.waiting_session_end = False
        self.in_overtime = False
        self.manual_break = False
        self.manual_break_indefinite = False
        self.break_remaining = 0
        self.break_elapsed = 0
        self.regular_break_credit_remaining = 0
        self.break_credit_eligible_seconds = 0
        self.break_planned_seconds = 0
        self.break_credited_seconds = 0
        self.return_overrun_seconds = 0
        self.end_prompt_wait_seconds = 0
        self.end_prompt_unaccounted_seconds = 0
        self.overtime_reminder_remaining = 0
        self.day_suspended = True
        self.manual_schedule_override = True
        self.manual_open_ended_work = False
        self._finalize_balance_day(day, "Terminata anticipatamente; giornata riapribile")
        self._save_runtime_state(force=True)
        self.show_daily_summary(day, mark_shown=True)
        self.update_indicator_menu()
        self._update_ui()

    def _manual_work_is_overtime(self, now: dt.datetime) -> bool:
        if self.current_session is None:
            return False
        return now >= self._session_boundary(self.current_session, now.date(), end=True)

    def _record_active_work_second(self, now: dt.datetime) -> None:
        self._record_work_second(
            now.date(),
            overtime=self.manual_open_ended_work or self._manual_work_is_overtime(now),
        )

    def _reset_runtime_state(self) -> None:
        self.work_remaining = self.settings.work_minutes * 60
        self.grace_remaining = 0
        self.break_remaining = 0
        self.break_elapsed = 0
        self.regular_break_credit_remaining = 0
        self.break_credit_eligible_seconds = 0
        self.break_planned_seconds = 0
        self.break_credited_seconds = 0
        self.return_overrun_seconds = 0
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
        self.midday_recovery_overrun_seconds = 0
        self.midday_recovery_started_late = False
        self.afternoon_started_early = False
        self.waiting_daily_close_choice = False
        self.compensating_daily_balance = False
        self.compensation_remaining = 0
        self.compensation_day = None
        self.break_truncated_by_day_end = False
        self.manual_break = False
        self.manual_break_indefinite = False
        self.manual_schedule_override = False
        self.manual_open_ended_work = False
        self.day_suspended = False
        self.resume_preserves_cycle = False
        self.pending_manual_session = None
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
            self.manual_pause_window,
            self.regular_pause_window,
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
        self.manual_pause_window = None
        self.regular_pause_window = None
        self.regular_pause_origin = "stop"
        self.clock.hide()

    def _runtime_phase(self) -> str:
        if self.day_suspended:
            return "day_suspended"
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
        if self.current_session is None or self.current_session_date is None:
            return None
        return {
            "schema_version": 8,
            "reminders_paused": not self.settings.enabled,
            "saved_at": dt.datetime.now().isoformat(timespec="seconds"),
            "session": self.current_session,
            "session_date": self.current_session_date.isoformat(),
            "phase": self._runtime_phase(),
            "work_remaining": max(0, int(self.work_remaining)),
            "grace_remaining": max(0, int(self.grace_remaining)),
            "break_remaining": max(0, int(self.break_remaining)),
            "break_elapsed": max(0, int(self.break_elapsed)),
            "regular_break_credit_remaining": max(0, int(self.regular_break_credit_remaining)),
            "break_credit_eligible_seconds": max(0, int(self.break_credit_eligible_seconds)),
            "break_planned_seconds": max(0, int(self.break_planned_seconds)),
            "break_credited_seconds": max(0, int(self.break_credited_seconds)),
            "return_overrun_seconds": max(0, int(self.return_overrun_seconds)),
            "overtime_seconds": max(0, int(self.overtime_seconds)),
            "overtime_reminder_remaining": max(0, int(self.overtime_reminder_remaining)),
            "end_prompt_wait_seconds": max(0, int(self.end_prompt_wait_seconds)),
            "end_prompt_unaccounted_seconds": max(0, int(self.end_prompt_unaccounted_seconds)),
            "end_prompt_is_reminder": bool(self.end_prompt_is_reminder),
            "midday_recovery_remaining": max(0, int(self.midday_recovery_remaining)),
            "midday_recovery_total": max(0, int(self.midday_recovery_total)),
            "midday_recovery_overrun_seconds": max(
                0, int(self.midday_recovery_overrun_seconds)
            ),
            "midday_recovery_started_late": bool(self.midday_recovery_started_late),
            "afternoon_started_early": bool(self.afternoon_started_early),
            "compensation_remaining": max(0, int(self.compensation_remaining)),
            "compensation_day": self.compensation_day.isoformat() if self.compensation_day else "",
            "break_truncated_by_day_end": bool(self.break_truncated_by_day_end),
            "manual_break": bool(self.manual_break),
            "manual_break_indefinite": bool(self.manual_break_indefinite),
            "manual_schedule_override": bool(self.manual_schedule_override),
            "manual_open_ended_work": bool(self.manual_open_ended_work),
            "day_suspended": bool(self.day_suspended),
            "resume_preserves_cycle": bool(self.resume_preserves_cycle),
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
        if not RUNTIME_STATE_FILE.exists():
            return False
        try:
            raw = json.loads(RUNTIME_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            self._clear_runtime_state()
            return False
        if not isinstance(raw, dict) or int(raw.get("schema_version", 0)) not in (1, 2, 3, 4, 5, 6, 7, 8):
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
            "day_suspended",
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
            "day_suspended",
        }
        scheduled_session = self.session_for(now)
        restored_early_afternoon = bool(raw.get("afternoon_started_early", False))
        restored_manual_override = bool(raw.get("manual_schedule_override", False))
        restored_manual_break = bool(raw.get("manual_break", False))
        restored_preserved_cycle = bool(raw.get("resume_preserves_cycle", False))
        if (
            self.settings.enabled
            and not special_phase
            and not restored_early_afternoon
            and not restored_manual_override
            and not restored_manual_break
            and not restored_preserved_cycle
            and scheduled_session != saved_session
        ):
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
        self.regular_break_credit_remaining = self._safe_runtime_seconds(
            raw.get("regular_break_credit_remaining", 0),
            self.regular_pause_credit_per_break_seconds(),
        )
        self.break_credit_eligible_seconds = self._safe_runtime_seconds(
            raw.get("break_credit_eligible_seconds", raw.get("break_credited_seconds", 0)),
            self.regular_pause_credit_per_break_seconds(),
        )
        self.break_planned_seconds = self._safe_runtime_seconds(
            raw.get("break_planned_seconds", self.break_elapsed + self.break_remaining),
            7 * 86400,
        )
        self.break_credited_seconds = self._safe_runtime_seconds(
            raw.get("break_credited_seconds", 0),
            7 * 86400,
        )
        self.return_overrun_seconds = self._safe_runtime_seconds(
            raw.get("return_overrun_seconds", 0),
            7 * 86400,
        )
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
        self.midday_recovery_overrun_seconds = self._safe_runtime_seconds(
            raw.get("midday_recovery_overrun_seconds", 0), 7 * 86400
        )
        self.midday_recovery_started_late = bool(
            raw.get("midday_recovery_started_late", False)
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
        self.manual_break = bool(raw.get("manual_break", False))
        self.manual_break_indefinite = bool(raw.get("manual_break_indefinite", False))
        if "break_credited_seconds" not in raw:
            self.break_credited_seconds = (
                0
                if self.manual_break
                else min(
                    self.break_elapsed,
                    self.regular_pause_credit_per_break_seconds(),
                )
            )
        if (
            (
                "regular_break_credit_remaining" not in raw
                or "break_credit_eligible_seconds" not in raw
            )
            and phase in {"break", "waiting_return"}
            and not self.manual_break
        ):
            # Compatibilità con uno stato salvato dalla versione precedente:
            # ricostruisce soltanto la quota residua della pausa già iniziata.
            per_break_remaining = max(
                0, self.regular_pause_credit_per_break_seconds() - self.break_elapsed
            )
            self.break_credit_eligible_seconds = min(
                self.break_elapsed, self.regular_pause_credit_per_break_seconds()
            )
            self.regular_break_credit_remaining = per_break_remaining
        self.manual_schedule_override = restored_manual_override
        self.manual_open_ended_work = bool(raw.get("manual_open_ended_work", False))
        self.day_suspended = bool(raw.get("day_suspended", phase == "day_suspended"))
        self.resume_preserves_cycle = restored_preserved_cycle

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
        self._cap_work_cycle_to_session_end(now)
        self._save_runtime_state(force=True)
        return True

    def _restore_pending_runtime_window(self) -> bool:
        if not self.settings.enabled:
            return False
        if self.day_suspended:
            self.update_indicator_menu()
        elif self.compensating_daily_balance:
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

        if not self.settings.enabled:
            # Timer e fasi restano completamente congelati finché l'utente non
            # sceglie come riattivare il promemoria.
            self.clock.hide()
            self._save_runtime_state()
            self._update_ui()
            return True

        self._sync_session(now)
        self._cap_work_cycle_to_session_end(now)

        if self.current_session is None:
            self.clock.hide()
            self._update_ui()
            return True

        if self.day_suspended:
            self.clock.hide()
            self._save_runtime_state()
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
            # Finché non viene confermato il rientro, ogni secondo resta pausa effettiva.
            self._record_break_second(now.date())
            if self.midday_recovery_remaining > 0:
                self.midday_recovery_remaining = max(0, self.midday_recovery_remaining - 1)
            else:
                self.midday_recovery_overrun_seconds += 1
            if self.midday_recovery_window:
                self.midday_recovery_window.update(
                    self.midday_recovery_remaining,
                    self.midday_recovery_overrun_seconds,
                    self.midday_recovery_started_late,
                )
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
            self._record_active_work_second(now)
            self.clock.hide()
            self._save_runtime_state()
            self._update_ui()
            return True

        if self.waiting_return:
            # La pausa effettiva termina solo quando l'utente conferma il rientro.
            # Per una pausa ciclica il ritardo resta abbuonabile fino al tetto
            # della singola pausa (es. 5 minuti previsti + altri 5 concessi).
            credit_this_second = (
                not self.manual_break and self.regular_break_credit_remaining > 0
            )
            credited_now = self._record_break_second(
                now.date(), credited=credit_this_second
            )
            if credit_this_second:
                self.regular_break_credit_remaining = max(
                    0, self.regular_break_credit_remaining - 1
                )
                self.break_credit_eligible_seconds += 1
                self.break_credited_seconds += credited_now
            self.break_elapsed += 1
            self.return_overrun_seconds += 1
            self._update_return_prompt_timing()
            self._save_runtime_state()
            self._update_ui()
            return True

        if self.in_break:
            if not self.manual_break_indefinite:
                self.break_remaining = max(0, self.break_remaining - 1)
            self.break_elapsed += 1
            # Le pause manuali non sono accreditate. Per le pause cicliche
            # il massimo per singola pausa e per blocco di 2 ore è configurabile.
            credit_this_second = (
                not self.manual_break and self.regular_break_credit_remaining > 0
            )
            credited_now = self._record_break_second(
                now.date(), credited=credit_this_second
            )
            if credit_this_second:
                self.regular_break_credit_remaining = max(
                    0, self.regular_break_credit_remaining - 1
                )
                self.break_credit_eligible_seconds += 1
                self.break_credited_seconds += credited_now
            self._maybe_beep()
            if not self.manual_break_indefinite and self.break_remaining <= 0:
                self._finish_break()
            self._save_runtime_state()
            self._update_ui()
            return True

        if self.in_grace:
            self.grace_remaining = max(0, self.grace_remaining - 1)
            self._record_active_work_second(now)
            if self.grace_remaining <= 0:
                self._show_stop_alert()
            self._save_runtime_state()
            self._update_ui()
            return True

        self.work_remaining = max(0, self.work_remaining - 1)
        self._record_active_work_second(now)
        if self.work_remaining <= 0:
            self.resume_preserves_cycle = False
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

    def _work_cycle_seconds_for_now(
        self, now: Optional[dt.datetime] = None, session: Optional[str] = None
    ) -> int:
        """Limita il ciclo al tempo reale rimasto prima della fine fascia.

        Se, per esempio, il ciclo configurato è 60 minuti ma mancano soltanto
        22 minuti a ``Mattina fine``, il countdown deve partire da 22 minuti.
        Fuori dall'orario di fine (lavoro manuale aperto) resta invece valido
        l'intero ciclo configurato.
        """
        current = now or dt.datetime.now()
        selected = session or self.current_session
        configured = max(1, int(self.settings.work_minutes)) * 60
        if selected not in {"morning", "afternoon"}:
            return configured

        boundary = self._session_boundary(selected, current.date(), end=True)
        seconds_to_end = int(math.ceil((boundary - current).total_seconds()))
        if seconds_to_end <= 0:
            return configured
        return max(1, min(configured, seconds_to_end))

    def _cap_work_cycle_to_session_end(self, now: Optional[dt.datetime] = None) -> None:
        """Applica il limite anche agli stati ripristinati da versioni precedenti."""
        current = now or dt.datetime.now()
        if (
            self.current_session not in {"morning", "afternoon"}
            or self.current_session_date != current.date()
            or self.manual_open_ended_work
            or self.in_overtime
            or self.waiting_session_end
            or self.compensating_daily_balance
            or self.resume_preserves_cycle
            or not self.settings.enabled
        ):
            return
        maximum = self._work_cycle_seconds_for_now(current, self.current_session)
        if self.work_remaining > maximum:
            self.work_remaining = maximum

    def _sync_session(self, now: dt.datetime, force: bool = False) -> None:
        if not self.settings.enabled:
            # Disattivare i promemoria congela la macchina a stati: non deve
            # cancellare né azzerare il timer corrente.
            return

        if self.current_session is not None and self.current_session_date == now.date():
            if self.day_suspended or self.manual_break or self.manual_open_ended_work:
                return
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

            if self.manual_schedule_override and now < session_end:
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
            summary_day = old_session_date or now.date()
            summary_stats = self.activity_log.get("days", {}).get(summary_day.isoformat(), {})
            if not bool(summary_stats.get("summary_shown", False)):
                self.show_daily_summary(summary_day, mark_shown=True)

        if new_session is not None:
            self.work_remaining = self._work_cycle_seconds_for_now(now, new_session)
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

        self._play_timer_end_sound()
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
            creditable = min(residual, max(0, int(self.regular_break_credit_remaining)))
            if creditable > 0:
                credited_now = self._record_break_seconds(day, creditable, credited=True)
                self.break_credit_eligible_seconds += creditable
                self.break_credited_seconds += credited_now
            if residual > creditable:
                self._record_break_seconds(day, residual - creditable, credited=False)
            self.regular_break_credit_remaining = 0
        self.in_break = False
        self.waiting_return = False
        self.break_planned_seconds = 0
        self.break_credited_seconds = 0
        self.return_overrun_seconds = 0
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
        self.break_remaining = 0
        self.break_elapsed = 0
        self.regular_break_credit_remaining = 0
        self.break_credit_eligible_seconds = 0
        self.break_planned_seconds = 0
        self.break_credited_seconds = 0
        self.return_overrun_seconds = 0
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
        now = dt.datetime.now()
        morning_end = self._session_boundary("morning", day, end=True)
        afternoon_start = self._session_boundary("afternoon", day, end=False)
        scheduled_pause_seconds = max(
            0, int(math.ceil((afternoon_start - morning_end).total_seconds()))
        )
        elapsed = max(0, int(elapsed_break_seconds))
        # Nei timeout automatici una parte della pausa è già trascorsa prima di aprire la finestra.
        actual_pause_start = now - dt.timedelta(seconds=elapsed)
        started_late = actual_pause_start > morning_end
        if started_late:
            expected_return = actual_pause_start + dt.timedelta(
                seconds=scheduled_pause_seconds
            )
        else:
            expected_return = afternoon_start

        remaining = max(0, int(math.ceil((expected_return - now).total_seconds())))
        overrun = max(0, int(math.floor((now - expected_return).total_seconds())))
        if elapsed:
            self._record_break_seconds(day, elapsed)

        self._reset_runtime_state()
        self.current_session = "morning"
        self.current_session_date = day
        self.in_midday_recovery = True
        self.midday_recovery_total = remaining
        self.midday_recovery_remaining = remaining
        self.midday_recovery_overrun_seconds = overrun
        self.midday_recovery_started_late = started_late
        self._show_midday_recovery_window()
        self._save_runtime_state(force=True)
        self.update_indicator_menu()
        self._update_ui()

    def _show_midday_recovery_window(self) -> None:
        if self.midday_recovery_window and self.midday_recovery_window.get_visible():
            self.midday_recovery_window.update(
                self.midday_recovery_remaining,
                self.midday_recovery_overrun_seconds,
                self.midday_recovery_started_late,
            )
            self.midday_recovery_window.present()
            return
        self.midday_recovery_window = MiddayRecoveryWindow(self)
        self.midday_recovery_window.update(
            self.midday_recovery_remaining,
            self.midday_recovery_overrun_seconds,
            self.midday_recovery_started_late,
        )

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
        self.midday_recovery_overrun_seconds = 0
        self.midday_recovery_started_late = False
        self.current_session = "afternoon"
        self.current_session_date = now.date()
        self.afternoon_started_early = now < self._session_boundary("afternoon", now.date(), end=False)
        self.work_remaining = self._work_cycle_seconds_for_now(now, "afternoon")
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
        self.manual_schedule_override = False
        self.manual_open_ended_work = False
        self.day_suspended = False
        self.work_remaining = self._work_cycle_seconds_for_now(
            dt.datetime.now(), self.current_session
        )
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
            self._play_timer_end_sound()
        default_seconds = self.settings.warning_seconds
        default_label = f"Predefinito: {format_mmss(default_seconds)}"
        self.grace_choice_window = ChoiceAlertWindow(
            "Quanto tempo ti serve per concludere?",
            "Scegli l'ultimatum. Dopo la scelta il conto alla rovescia resta soltanto vicino all'icona nella barra di sistema.",
            [
                (default_label, lambda: self._start_grace(default_seconds)),
                ("5 minuti", lambda: self._start_grace(5 * 60)),
                ("10 minuti", lambda: self._start_grace(10 * 60)),
                ("Inizia subito la pausa…", self._start_break_immediately),
                ("Salta pausa e continua il lavoro", self._skip_regular_break),
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

    def _start_break_immediately(self) -> None:
        """Salta l’ultimatum e chiede subito la durata della pausa ciclica."""
        self.grace_choice_window = None
        self.in_grace = False
        self.grace_remaining = 0
        # Manteniamo waiting_grace_choice finché la durata non viene confermata:
        # il lavoro continua quindi a essere conteggiato durante la scelta.
        self._request_regular_pause_duration("grace")

    def _show_stop_alert(self, immediate: bool = False, restoring: bool = False) -> None:
        self.in_grace = False
        self.waiting_grace_choice = False
        self.waiting_break_start = True
        self.grace_remaining = 0
        self.clock.hide()
        if not restoring:
            self._play_timer_end_sound()
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
        self.stop_window = ChoiceAlertWindow(
            "Fermati subito!",
            f"{prefix}\nIl lavoro continua finché non scegli la durata e avvii realmente la pausa.",
            [
                ("Scegli durata pausa", lambda: self._request_regular_pause_duration("stop")),
                ("Salta pausa e continua il lavoro", self._skip_regular_break),
            ],
        )
        self._save_runtime_state(force=True)

    def _request_regular_pause_duration(self, origin: str) -> None:
        if self.regular_pause_window and self.regular_pause_window.get_visible():
            self.regular_pause_window.present()
            return
        self.regular_pause_origin = origin if origin in {"grace", "stop"} else "stop"
        self.stop_window = None
        self.regular_pause_window = RegularPauseWindow(self)
        self._save_runtime_state(force=True)

    def _cancel_regular_pause_choice(self) -> bool:
        origin = self.regular_pause_origin
        self.regular_pause_origin = "stop"
        if origin == "grace":
            self.waiting_grace_choice = True
            self.waiting_break_start = False
            self._show_grace_choice(restoring=True)
        else:
            self.waiting_grace_choice = False
            self.waiting_break_start = True
            self._show_stop_alert(restoring=True)
        self._save_runtime_state(force=True)
        self._update_ui()
        return False

    def _skip_regular_break(self) -> None:
        """Ignora la pausa ciclica e avvia subito un nuovo blocco di lavoro."""
        for attr in ("grace_choice_window", "stop_window", "regular_pause_window"):
            window = getattr(self, attr, None)
            try:
                if window:
                    window.destroy()
            except Exception:
                pass
            setattr(self, attr, None)

        self.waiting_grace_choice = False
        self.waiting_break_start = False
        self.in_grace = False
        self.grace_remaining = 0
        self.regular_pause_origin = "stop"
        self.resume_preserves_cycle = False
        self.work_remaining = self._work_cycle_seconds_for_now(
            dt.datetime.now(), self.current_session
        )
        self.clock.hide()
        self._save_runtime_state(force=True)
        self._update_ui()

    def start_break(self) -> None:
        """Compatibilità: apre la scelta della durata della pausa ciclica."""
        origin = "grace" if self.waiting_grace_choice else "stop"
        self._request_regular_pause_duration(origin)

    def _begin_regular_break(self, minutes: int) -> None:
        # La pausa parte solo dopo la scelta esplicita della durata.
        self.waiting_grace_choice = False
        self.waiting_break_start = False
        self.in_grace = False
        self.grace_remaining = 0
        self.grace_choice_window = None
        self.regular_pause_window = None
        self.regular_pause_origin = "stop"
        self.in_break = True
        self.manual_break = False
        self.manual_break_indefinite = False
        configured_break = max(1, int(minutes)) * 60
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
        self.break_planned_seconds = self.break_remaining
        self.break_credited_seconds = 0
        self.break_credit_eligible_seconds = 0
        self.return_overrun_seconds = 0
        # Il tetto della singola pausa resta disponibile anche dopo la durata
        # scelta: per esempio una pausa prevista da 5 minuti può abbuonare altri
        # 5 minuti di ritardo, fino al massimo configurato di 10 minuti.
        self.regular_break_credit_remaining = self.regular_pause_credit_per_break_seconds()
        try:
            if self.stop_window:
                self.stop_window.destroy()
        except Exception:
            pass
        self.stop_window = None
        # Nessuna finestra countdown: il tempo resta sempre accanto all’icona.
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
            self.regular_break_credit_remaining = 0
            self._prepare_end_of_day(self.current_session_date or dt.date.today(), explicit=True)
            return
        self.in_break = False
        self.waiting_return = True
        self.break_remaining = 0
        # La quota residua della singola pausa resta disponibile durante il
        # messaggio di rientro, così un piccolo ritardo può essere abbuonato.
        self.return_overrun_seconds = 0
        self._play_timer_end_sound()
        self._save_runtime_state(force=True)
        self._show_return_activity_prompt()

    def _return_break_info_lines(self) -> list[str]:
        elapsed = max(0, int(self.break_elapsed))
        planned = max(0, int(self.break_planned_seconds))
        credited = max(0, min(int(self.break_credited_seconds), elapsed))
        overrun = max(0, int(self.return_overrun_seconds))
        non_credited = max(0, elapsed - credited)

        planned_text = "senza scadenza" if self.manual_break_indefinite else format_mmss(planned)
        lines = [f"Pausa prevista: {planned_text} · effettiva finora: {format_mmss(elapsed)}"]
        if self.manual_break:
            lines.extend(
                [
                    f"Pausa terminata da: {format_negative_countdown(overrun)}",
                    "Pausa manuale: nessun minuto è abbuonato nell’obiettivo giornaliero.",
                    f"Tempo da recuperare per questa pausa: {format_negative_countdown(non_credited)}",
                ]
            )
        else:
            lines.extend(
                [
                    f"Quota abbuonata utilizzata: {format_mmss(credited)}",
                    f"Pausa terminata da: {format_negative_countdown(overrun)}",
                    (
                        f"Sforamento oltre i {format_mmss(credited)} abbuonati: "
                        f"{format_negative_countdown(non_credited)}"
                    ),
                ]
            )
        return lines

    def _update_return_prompt_timing(self) -> None:
        if isinstance(self.return_window, ActivityPromptWindow):
            self.return_window.update_info_lines(self._return_break_info_lines())

    def _show_return_activity_prompt(self) -> None:
        if self.return_window and self.return_window.get_visible():
            self._update_return_prompt_timing()
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
            info_lines=self._return_break_info_lines(),
        )

    def _defer_return(self) -> None:
        self.return_window = None
        self.waiting_return = True
        self._save_runtime_state(force=True)
        self._update_ui()

    def returned_from_break(self, activity: str, project: str) -> None:
        was_manual_break = self.manual_break
        now = dt.datetime.now()
        self.waiting_return = False
        self.in_break = False
        self.manual_break = False
        self.manual_break_indefinite = False
        if was_manual_break:
            self.current_session = self._manual_session_for_now(now)
            self.current_session_date = now.date()
            self.manual_schedule_override = True
            self.afternoon_started_early = (
                self.current_session == "afternoon"
                and now < self._session_boundary("afternoon", now.date(), end=False)
            )
            self.manual_open_ended_work = now >= self._session_boundary(
                self.current_session, now.date(), end=True
            )
            self._mark_day_reopened(now.date())
        self.work_remaining = self._work_cycle_seconds_for_now(now, self.current_session)
        self.break_elapsed = 0
        self.regular_break_credit_remaining = 0
        self.break_credit_eligible_seconds = 0
        self.break_planned_seconds = 0
        self.break_credited_seconds = 0
        self.return_overrun_seconds = 0
        try:
            if self.return_window:
                self.return_window.destroy()
        except Exception:
            pass
        self.return_window = None
        self._record_activity(activity, project)
        self._save_runtime_state(force=True)
        self.update_indicator_menu()
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

    def _build_sound_file(self, sound_key: str) -> Path:
        sound_key = sound_key if sound_key in TIMER_END_SOUND_OPTIONS else "soft"
        cache_key = f"{sound_key}-{int(self.settings.beep_volume * 100)}"
        cached = self.sound_files.get(cache_key) if hasattr(self, "sound_files") else None
        if cached and cached.exists():
            return cached

        path = Path(tempfile.gettempdir()) / f"{APP_ID}-{cache_key}.wav"
        rate = 44100
        amplitude = max(0.01, min(self.settings.beep_volume, 0.30))

        if sound_key == "double":
            segments = [(760.0, 0.15), (0.0, 0.10), (900.0, 0.18)]
        elif sound_key == "chime":
            segments = [(660.0, 0.20), (880.0, 0.24), (1100.0, 0.30)]
        else:
            segments = [(740.0, 0.18)]

        frames = bytearray()
        for frequency, duration in segments:
            samples = max(1, int(rate * duration))
            for i in range(samples):
                if frequency <= 0:
                    value = 0
                else:
                    fade_in = min(1.0, i / max(1, int(rate * 0.020)))
                    fade_out = min(1.0, (samples - i) / max(1, int(rate * 0.045)))
                    env = max(0.0, min(fade_in, fade_out))
                    if sound_key == "chime":
                        tone = (
                            math.sin(2 * math.pi * frequency * i / rate)
                            + 0.35 * math.sin(2 * math.pi * frequency * 2 * i / rate)
                        ) / 1.35
                    else:
                        tone = math.sin(2 * math.pi * frequency * i / rate)
                    value = int(32767 * amplitude * env * tone)
                frames.extend(value.to_bytes(2, byteorder="little", signed=True))

        with wave.open(str(path), "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(bytes(frames))
        if hasattr(self, "sound_files"):
            self.sound_files[cache_key] = path
        return path

    def _play_sound(self, sound_key: str) -> None:
        if not self.settings.audio_enabled or sound_key == "none":
            return
        sound_file = self._build_sound_file(sound_key)
        player = shutil.which("paplay") or shutil.which("aplay")
        if player:
            try:
                subprocess.Popen(
                    [player, str(sound_file)],
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

    def _play_timer_end_sound(self) -> None:
        self._play_sound(self.settings.timer_end_sound)

    def _build_beep_file(self) -> Path:
        # Alias mantenuto per compatibilità interna con versioni precedenti.
        return self._build_sound_file("soft")

    def _play_beep_once(self) -> None:
        # I beep periodici della pausa restano volutamente morbidi.
        self.beep_file = self._build_sound_file("soft")
        self._play_sound("soft")

    def _load_activity_log(self) -> dict:
        raw: dict = {
            "schema_version": 6,
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

        try:
            previous_schema = int(raw.get("schema_version", 0) or 0)
        except Exception:
            previous_schema = 0
        raw["schema_version"] = 6
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
            if "regular_break_eligible_seconds" not in stats:
                legacy_credited = max(0, int(stats.get("credited_break_seconds", 0)))
                legacy_eligible = legacy_credited
                # Le versioni precedenti non conservavano i secondi regolari eccedenti.
                # Solo per la giornata corrente ancora aperta recuperiamo, in modo
                # prudente, fino all'abbuono extra giornaliero configurato.
                try:
                    legacy_day = dt.date.fromisoformat(day_key)
                except Exception:
                    legacy_day = None
                if (
                    previous_schema < 6
                    and legacy_day == dt.date.today()
                    and not bool(stats.get("day_closed", False))
                ):
                    unclassified_break = max(
                        0, int(stats.get("break_seconds", 0)) - legacy_credited
                    )
                    legacy_eligible += min(
                        unclassified_break,
                        max(0, int(self.settings.daily_pause_extra_credit_minutes)) * 60,
                    )
                stats["regular_break_eligible_seconds"] = legacy_eligible
            stats.setdefault("overtime_seconds", 0)
            stats.setdefault("special_workday", False)
            stats.setdefault("special_workday_label", "")
            stats.setdefault("activities", [])
            stats.setdefault("activity_totals", [])
            stats.setdefault("time_transfers", [])
            stats.setdefault("summary_shown", False)
            stats.setdefault("day_closed", False)
            stats.setdefault("close_choice", "")
            stats.setdefault("balance_delta_seconds", None)
            if not isinstance(stats["activities"], list):
                stats["activities"] = []
            if not isinstance(stats["activity_totals"], list):
                stats["activity_totals"] = []
            if not isinstance(stats["time_transfers"], list):
                stats["time_transfers"] = []
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
            classified_work = sum(
                max(0, int(item.get("work_seconds", 0)))
                for item in stats.get("activity_totals", [])
                if isinstance(item, dict)
            )
            stats["work_seconds"] = max(
                max(0, int(stats.get("work_seconds", 0))),
                max(0, int(stats.get("overtime_seconds", 0))),
                classified_work,
            )
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
                "time_transfers": [],
                "summary_shown": False,
                "day_closed": False,
                "close_choice": "",
                "balance_delta_seconds": None,
            },
        )
        stats.setdefault("work_seconds", 0)
        stats.setdefault("break_seconds", 0)
        stats.setdefault("credited_break_seconds", 0)
        stats.setdefault(
            "regular_break_eligible_seconds",
            max(0, int(stats.get("credited_break_seconds", 0))),
        )
        stats.setdefault("overtime_seconds", 0)
        stats.setdefault("special_workday", False)
        stats.setdefault("special_workday_label", "")
        stats.setdefault("activities", [])
        stats.setdefault("activity_totals", [])
        stats.setdefault("time_transfers", [])
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

    def regular_pause_credit_per_break_seconds(self) -> int:
        """Massimo configurato che una singola pausa ciclica può abbuonare."""
        return max(0, int(self.settings.regular_pause_credit_minutes)) * 60

    def regular_pause_base_credit_limit_seconds(
        self, day: dt.date, stats: Optional[dict] = None
    ) -> int:
        """Quota ordinaria maturata: valore configurato per ogni blocco iniziato di 2 ore."""
        stats = stats or self.activity_log.get("days", {}).get(day.isoformat(), {})
        work = max(0, int(stats.get("work_seconds", 0)))
        credit_per_block = self.regular_pause_credit_per_break_seconds()
        if work <= 0 or credit_per_block <= 0:
            return 0
        blocks = max(
            1,
            (work + REGULAR_PAUSE_WORK_BLOCK_SECONDS - 1)
            // REGULAR_PAUSE_WORK_BLOCK_SECONDS,
        )
        return blocks * credit_per_block

    def regular_pause_credit_limit_seconds(
        self, day: dt.date, stats: Optional[dict] = None
    ) -> int:
        """Tetto giornaliero: quota ordinaria maturata + abbuono extra giornaliero."""
        stats = stats or self.activity_log.get("days", {}).get(day.isoformat(), {})
        work = max(0, int(stats.get("work_seconds", 0)))
        if work <= 0:
            return 0
        base = self.regular_pause_base_credit_limit_seconds(day, stats)
        extra = max(0, int(self.settings.daily_pause_extra_credit_minutes)) * 60
        return base + extra

    def credited_break_for_day_seconds(
        self, day: dt.date, stats: Optional[dict] = None
    ) -> int:
        stats = stats or self.activity_log.get("days", {}).get(day.isoformat(), {})
        stored = max(0, int(stats.get("credited_break_seconds", 0)))
        eligible = max(
            stored,
            max(0, int(stats.get("regular_break_eligible_seconds", stored))),
        )
        credited = min(eligible, self.regular_pause_credit_limit_seconds(day, stats))
        if isinstance(stats, dict):
            stats["regular_break_eligible_seconds"] = eligible
            stats["credited_break_seconds"] = credited
        return credited

    def regular_pause_credit_available_seconds(self, day: dt.date) -> int:
        stats = self.activity_log.get("days", {}).get(day.isoformat(), {})
        return max(
            0,
            self.regular_pause_credit_limit_seconds(day, stats)
            - self.credited_break_for_day_seconds(day, stats),
        )

    def _recalculate_pause_credits(self) -> None:
        changed = False
        for day_key, stats in self.activity_log.get("days", {}).items():
            if not isinstance(stats, dict):
                continue
            try:
                day = dt.date.fromisoformat(day_key)
            except Exception:
                continue
            before = max(0, int(stats.get("credited_break_seconds", 0)))
            after = self.credited_break_for_day_seconds(day, stats)
            if before != after:
                changed = True
            self._refresh_closed_balance_delta(day)
        if changed:
            self._save_activity_log()

    def daily_counted_seconds(self, day: dt.date) -> int:
        """Tempo utile per l'obiettivo: lavoro + sola pausa terminata entro il countdown."""
        stats = self.activity_log.get("days", {}).get(day.isoformat(), {})
        work = max(0, int(stats.get("work_seconds", 0)))
        credited_break = self.credited_break_for_day_seconds(day, stats)
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
                total += self.credited_break_for_day_seconds(cursor, stats)
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
        # Aumentando il lavoro possono maturare nuovi blocchi di pausa: eventuali
        # secondi regolari già idonei vengono abbuonati retroattivamente fino al
        # nuovo tetto giornaliero.
        stats["credited_break_seconds"] = self.credited_break_for_day_seconds(day, stats)
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

    def _record_break_second(self, day: dt.date, credited: bool = False) -> int:
        return self._record_break_seconds(day, 1, credited=credited)

    def _record_break_seconds(
        self, day: dt.date, seconds: int, credited: bool = False
    ) -> int:
        """Registra la pausa e restituisce quanti secondi sono diventati utili all'obiettivo.

        ``credited`` indica che i secondi appartengono a una pausa ciclica ancora
        entro il tetto della singola pausa. Vengono conservati come idonei anche
        se il tetto giornaliero è momentaneamente esaurito: lavorando ancora, la
        quota ordinaria può maturare e accreditarli successivamente.
        """
        seconds = max(0, int(seconds))
        if seconds <= 0:
            return 0
        stats = self._stats_for(day)
        self._ensure_target_snapshot(day, stats)
        before_credit = self.credited_break_for_day_seconds(day, stats)
        stats["break_seconds"] = int(stats.get("break_seconds", 0)) + seconds
        if credited:
            stats["regular_break_eligible_seconds"] = max(
                0, int(stats.get("regular_break_eligible_seconds", 0))
            ) + seconds
        after_credit = self.credited_break_for_day_seconds(day, stats)
        stats["credited_break_seconds"] = after_credit
        stats["summary_shown"] = False
        self._refresh_closed_balance_delta(day)
        if seconds == 1:
            self._touch_stats()
        else:
            self._save_activity_log()
        if self.summary_window and self.summary_window.get_visible() and self.stats_save_counter % 5 == 0:
            self.summary_window.refresh()
        return max(0, after_credit - before_credit)

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

    def transfer_activity_time(
        self,
        day: dt.date,
        source_activity: str,
        source_project: str,
        target_activity: str,
        target_project: str,
        seconds: int,
    ) -> bool:
        source_activity = source_activity.strip()
        source_project = source_project.strip()
        target_activity = target_activity.strip()
        target_project = target_project.strip()
        seconds = max(0, int(seconds))
        if (
            not source_activity
            or not target_activity
            or seconds <= 0
            or (
                source_activity.casefold() == target_activity.casefold()
                and source_project.casefold() == target_project.casefold()
            )
        ):
            return False

        stats = self._stats_for(day)
        totals = stats.setdefault("activity_totals", [])
        source_index = next(
            (
                index
                for index, item in enumerate(totals)
                if isinstance(item, dict)
                and self._same_activity(item, source_activity, source_project)
            ),
            None,
        )
        target = next(
            (
                item
                for item in totals
                if isinstance(item, dict)
                and self._same_activity(item, target_activity, target_project)
            ),
            None,
        )
        if source_index is None or target is None:
            return False

        source = totals[source_index]
        available = max(0, int(source.get("work_seconds", 0)))
        if seconds > available:
            return False

        event_time = self._manual_event_time(day)
        source["work_seconds"] = available - seconds
        target["work_seconds"] = max(0, int(target.get("work_seconds", 0))) + seconds
        target["last_used"] = event_time
        if int(source.get("work_seconds", 0)) <= 0:
            totals.pop(source_index)

        stats.setdefault("time_transfers", []).append(
            {
                "time": event_time,
                "seconds": seconds,
                "source": {
                    "text": source_activity,
                    "project": source_project,
                },
                "target": {
                    "text": target_activity,
                    "project": target_project,
                },
            }
        )
        stats["time_transfers"] = stats["time_transfers"][-500:]
        stats["summary_shown"] = False
        self._remember_project(target_project)
        self._save_activity_log()
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

    def build_day_plain_text(self, day: dt.date) -> str:
        """Genera un riepilogo leggibile senza sintassi Markdown."""
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
        lines = [
            "RIEPILOGO GIORNALIERO",
            format_italian_markdown_date(day),
            "",
            "ATTIVITÀ SVOLTE",
        ]

        if rows:
            grouped: dict[str, list[dict]] = {}
            for item in rows:
                project = str(item.get("project", "")).strip() or "Senza progetto"
                grouped.setdefault(project, []).append(item)
            for project, items in grouped.items():
                lines.append(project)
                for item in items:
                    activity = (
                        str(item.get("text", "")).strip()
                        or "Tempo non classificato"
                    )
                    duration = self._format_effective_minutes(
                        int(item.get("work_seconds", 0))
                    )
                    lines.append(f"  • {activity}: {duration}")
                lines.append("")
            if lines[-1] == "":
                lines.pop()
        else:
            lines.append("Nessuna attività registrata.")

        work_seconds = max(0, int(stats.get("work_seconds", 0)))
        break_seconds = max(0, int(stats.get("break_seconds", 0)))
        credited_break_seconds = max(
            0, int(self.credited_break_for_day_seconds(day, stats))
        )
        recoverable_break_seconds = max(
            0, break_seconds - credited_break_seconds
        )
        counted_seconds = max(0, int(self.daily_counted_seconds(day)))
        target_seconds = max(0, int(self._daily_target_seconds_for(day)))
        remaining_seconds = max(0, int(self.daily_remaining_seconds(day)))
        balance_before_seconds = int(self.time_balance_before_day_seconds(day))
        if bool(stats.get("day_closed", False)):
            balance_after_seconds = int(self.active_time_balance_seconds(day))
        else:
            balance_after_seconds = int(
                self.projected_time_balance_for_day_seconds(day)
            )

        lines.extend(
            [
                "",
                "TEMPI DELLA GIORNATA",
                f"Lavoro effettivo: {self._format_effective_minutes(work_seconds)}",
                f"Pause totali: {self._format_effective_minutes(break_seconds)}",
                (
                    "Pausa conteggiata nell’obiettivo: "
                    f"{self._format_effective_minutes(credited_break_seconds)}"
                ),
                (
                    "Pausa da recuperare: "
                    f"{self._format_effective_minutes(recoverable_break_seconds)}"
                ),
            ]
        )

        if self._is_special_workday(day, stats):
            lines.extend(
                [
                    "",
                    "GIORNATA EXTRA",
                    f"Motivo: {self._special_workday_label(day, stats)}",
                    (
                        "EXTRA festivo/ferie: "
                        f"{self._format_effective_minutes(self.special_day_extra_seconds(day))}"
                    ),
                ]
            )
        elif self.day_has_regular_target(day):
            lines.extend(
                [
                    "",
                    "OBIETTIVO E SALDO",
                    (
                        "Avanzamento: "
                        f"{self._format_effective_minutes(counted_seconds)} su "
                        f"{self._format_effective_minutes(target_seconds)}"
                    ),
                    (
                        "Tempo ancora da fare: "
                        f"{self._format_effective_minutes(remaining_seconds)}"
                    ),
                    (
                        "Saldo iniziale: "
                        f"{format_signed_hours_minutes(balance_before_seconds)}"
                    ),
                    (
                        "Saldo dopo la giornata: "
                        f"{format_signed_hours_minutes(balance_after_seconds)}"
                    ),
                    (
                        "Scelta di chiusura: "
                        f"{str(stats.get('close_choice', '')).strip() or 'non ancora effettuata'}"
                    ),
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    "OBIETTIVO E SALDO",
                    "Obiettivo giornaliero: non previsto",
                ]
            )

        current_month_label = f"{ITALIAN_MONTH_NAMES[day.month - 1]} {day.year}"
        previous_year, previous_month = self.previous_month(day.year, day.month)
        previous_month_label = (
            f"{ITALIAN_MONTH_NAMES[previous_month - 1]} {previous_year}"
        )
        closure_date = self._extra_closure_date(day.year, day.month)
        lines.extend(
            [
                "",
                "STRAORDINARI ED EXTRA",
                (
                    "Straordinario oltre fascia del giorno: "
                    f"{self._format_effective_minutes(int(stats.get('overtime_seconds', 0)))}"
                ),
                (
                    "Settimana ordinaria: "
                    f"{self._format_effective_minutes(self.regular_week_counted_seconds(day))} su "
                    f"{self._format_effective_minutes(self._weekly_target_seconds_for(day))}"
                ),
                (
                    "EXTRA oltre limite settimanale: "
                    f"{self._format_effective_minutes(self.weekly_extra_seconds(day))}"
                ),
                (
                    "EXTRA settimanale attribuito al giorno: "
                    f"{self._format_effective_minutes(self.weekly_extra_for_day_seconds(day))}"
                ),
                (
                    "EXTRA totale del giorno: "
                    f"{self._format_effective_minutes(self.total_extra_for_day_seconds(day))}"
                ),
                (
                    f"EXTRA {current_month_label}: "
                    f"{self._format_effective_minutes(self.month_extra_seconds(day.year, day.month))}"
                ),
                (
                    "Di cui EXTRA festivi/ferie: "
                    f"{self._format_effective_minutes(self.month_special_extra_seconds(day.year, day.month))}"
                ),
                (
                    f"Straordinario oltre fascia {current_month_label}: "
                    f"{self._format_effective_minutes(self.month_overtime_seconds(day.year, day.month))}"
                ),
                (
                    f"EXTRA riportato da {previous_month_label}: "
                    f"{self._format_effective_minutes(self.month_extra_seconds(previous_year, previous_month))}"
                ),
                (
                    f"Straordinario riportato da {previous_month_label}: "
                    f"{self._format_effective_minutes(self.month_overtime_seconds(previous_year, previous_month))}"
                ),
                (
                    "Saldo ore attivo: "
                    f"{format_signed_hours_minutes(self.active_time_balance_seconds())}"
                ),
                (
                    "EXTRA da saldo chiuso nel mese: "
                    f"{self._format_effective_minutes(self.closed_balance_extra_seconds(day.year, day.month))}"
                ),
                f"Data di chiusura saldo del mese: {closure_date.strftime('%d/%m/%Y')}",
            ]
        )
        return "\n".join(lines)

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
        credited_pause = self._format_effective_minutes(
            self.credited_break_for_day_seconds(day, stats)
        )
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
            if day == now.date() and self.current_session is not None and not self.day_suspended:
                continue
            day_is_finished = day < now.date() or now.time() >= afternoon_end
            if has_time and day_is_finished:
                self.show_daily_summary(day, mark_shown=True)
                break
        return False

    def compact_indicator_label(self) -> str:
        # Il tempo resta sempre accanto all'icona quando il pannello lo supporta.
        if not self.settings.enabled:
            return "OFF"
        elif self.day_suspended:
            base = "FINE"
        elif self.current_session is None:
            base = "Zz"
        elif self.compensating_daily_balance:
            base = f"↥ {format_mmss(self.compensation_remaining)}"
        elif self.waiting_daily_close_choice:
            base = "Saldo?"
        elif self.in_midday_recovery:
            recovery_time = (
                format_negative_countdown(self.midday_recovery_overrun_seconds)
                if self.midday_recovery_overrun_seconds > 0
                else format_mmss(self.midday_recovery_remaining)
            )
            base = f"↻ {recovery_time}"
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
            base = f"Rientro {format_negative_countdown(self.return_overrun_seconds)}"
        elif self.in_break and self.manual_break_indefinite:
            base = "☕ ∞"
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
            return "Promemoria disattivato — timer congelato"
        if self.day_suspended:
            remaining = self.balance_remaining_for_day_seconds(
                self.current_session_date or dt.date.today()
            )
            if remaining > 0:
                return (
                    "Giornata terminata anticipatamente — deficit corrente "
                    f"{format_signed_hours_minutes(remaining)}. Puoi riprenderla più tardi."
                )
            return "Giornata terminata anticipatamente — puoi riprenderla più tardi"
        if self.current_session is None:
            reason = self.day_off_reason(dt.date.today())
            if reason:
                return f"Giornata esclusa: {reason}"
            return "Fuori fascia: timer fermo — puoi iniziare manualmente"
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
            if self.midday_recovery_overrun_seconds > 0:
                return (
                    "Pausa mattutina oltre il rientro da "
                    f"{format_mmss(self.midday_recovery_overrun_seconds)}: conferma il rientro"
                )
            if self.midday_recovery_remaining <= 0:
                return "Pausa mattutina terminata: il prossimo secondo sarà conteggiato in negativo"
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
            non_credited = max(
                0,
                int(self.break_elapsed) - int(self.break_credited_seconds),
            )
            if self.manual_break:
                return (
                    "Pausa manuale conclusa da "
                    f"{format_negative_countdown(self.return_overrun_seconds)} — "
                    "tempo non abbuonato "
                    f"{format_negative_countdown(non_credited)}. Conferma quando riprendi il lavoro."
                )
            return (
                "Pausa terminata da "
                f"{format_negative_countdown(self.return_overrun_seconds)} — "
                f"oltre i {format_mmss(self.break_credited_seconds)} abbuonati: "
                f"{format_negative_countdown(non_credited)}. "
                "Il ritardo non viene conteggiato come lavoro."
            )
        if self.in_break and self.manual_break_indefinite:
            return "Pausa manuale senza scadenza: riprendi quando vuoi"
        if self.in_break and self.manual_break:
            return f"Pausa manuale: {format_mmss(self.break_remaining)}"
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
                "Disattiva Promemoria" if self.settings.enabled else "Riattiva promemoria"
            )
        if self.control_window:
            self.control_window.update(text, self.settings.enabled)
        if self.settings_window and self.settings_window.get_visible():
            try:
                self.settings_window.enabled.set_active(self.settings.enabled)
            except Exception:
                pass

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
