import sys
import os
import json
import time
import csv
import html
import math
import warnings
from collections import deque

import numpy as np
from scipy.optimize import curve_fit
from scipy.optimize import OptimizeWarning

import serial
import serial.tools.list_ports

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFormLayout, QLineEdit, QPushButton, QTextEdit, QLabel, QComboBox,
    QGroupBox, QTabWidget, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QSpinBox, QDoubleSpinBox, QCheckBox,
    QDialog, QDialogButtonBox, QProgressBar, QInputDialog, QFrame,
    QScrollArea, QColorDialog, QSplitter, QSizePolicy
)
from PyQt5.QtCore import pyqtSignal, QThread, QTimer, Qt, QPointF
from PyQt5.QtGui import QPalette, QColor, QFont, QPainter, QPolygonF

# ---------------------------------------------------------------------------
# DUKUNGAN LAYAR HIGH-DPI / RETINA (2K, 4K 3840x2160, dst.)
# ---------------------------------------------------------------------------
# Atribut Qt.AA_* di bawah ini WAJIB di-set SEBELUM instance QApplication
# dibuat, jadi ditaruh di level modul (dieksekusi saat import, sebelum
# main() memanggil QApplication(sys.argv)). Ini membuat Qt otomatis
# membaca faktor skala DPI dari sistem operasi (mis. 100%/150%/200%/250%
# di Windows, atau scale factor di Linux/macOS) dan menyesuaikan ukuran
# font, widget, spacing, serta stylesheet berbasis px secara konsisten,
# tanpa perlu mengubah satupun angka ukuran di kode.
#
# Variabel environment QT_ENABLE_HIGHDPI_SCALING / QT_SCALE_FACTOR
# dihormati oleh Qt bila pengguna ingin override manual (mis. paksa 200%
# di monitor 4K yang tidak diset scaling oleh OS-nya):
#   QT_SCALE_FACTOR=2 python logger_dashboard.py
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

if hasattr(Qt, "AA_EnableHighDpiScaling"):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
if hasattr(Qt, "AA_UseHighDpiPixmaps"):
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
# Kebijakan pembulatan faktor skala pecahan (mis. 150%, 175%) -- "PassThrough"
# memakai faktor skala persis sesuai laporan OS (tidak dibulatkan ke integer
# terdekat), supaya layout tetap presisi di monitor dengan scaling non-bulat.
if hasattr(QApplication, "setHighDpiScaleFactorRoundingPolicy") and hasattr(
    Qt, "HighDpiScaleFactorRoundingPolicy"
):
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

# pyqtgraph di-import setelah QApplication dibuat pada main().
pg = None

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "device_config.json")

MAX_POINTS = 300
BUZZER_PATTERN_COUNT = 10
GRAPH_COLORS = [
    "#e74c3c", "#3498db", "#2ecc71", "#f39c12",
    "#9b59b6", "#1abc9c", "#e67e22", "#34495e",
]

# Path payload TELEMETRY yang PASTI ada & numerik sesuai skema firmware
# saat ini (lihat payload_manager.build_telemetry()). Dipakai supaya
# dropdown payload di dialog Threshold tidak kosong sebelum device pernah
# mengirim data sama sekali -- sebelumnya daftar itu 100% bergantung pada
# self.latest_payload (data live), jadi kosong/"hilang" total kalau dialog
# dibuka sebelum device terhubung atau sebelum siklus telemetri pertama
# masuk. Sensor tambahan yang dikirim firmware di masa depan tetap
# otomatis ikut lewat self.latest_payload begitu ada payload live masuk.
KNOWN_NUMERIC_PAYLOAD_KEYS = {"sensors.t", "sensors.h", "sensors.batt", "wifi.rssi"}

# Sebelum payload_manager.py di-restrukturisasi, field sensor threshold
# disimpan FLAT ("t"/"h"/"batt"). Sekarang semuanya nested di bawah
# "sensors" ("sensors.t", dst). Threshold lama yang tersimpan di
# device_config.json dari sebelum migrasi itu masih menyimpan path lama --
# dipetakan otomatis di sini (sama seperti threshold_manager.py di
# firmware) supaya threshold lama "sembuh" begitu dibuka/disimpan lagi,
# tanpa operator perlu edit ulang satu-satu.
LEGACY_PAYLOAD_ALIASES = {"t": "sensors.t", "h": "sensors.h", "batt": "sensors.batt"}

DEFAULT_CONFIG = {
    "version": 1,
    "device": {
        "name": "ESP32 Sensor Logger",
        "baudrate": 115200,
        "mode": "always_on",
        "deep_sleep_sec": 60,
    },
    "dashboard": {
        "widgets": [
            {"key": "sensors.t", "label": "Suhu", "unit": "°C", "decimals": 1, "show_graph": True},
            {"key": "sensors.h", "label": "Kelembaban", "unit": "%", "decimals": 1, "show_graph": True},
        ]
    },
    "thresholds": [],
    "sensor_labels": {},
    "calibration": {},
    # Titik mentah (nilai mentah -> nilai acuan) yang dipakai untuk fitting
    # di Calibration Wizard, per payload key. Disimpan di PC (untuk
    # convenience: mengedit/re-fit tanpa ketik ulang) DAN dikirim ke device
    # lewat SET_CALIBRATION supaya ikut persisten di flash -- device
    # TIDAK memakainya untuk apa pun (tidak ada scipy/fitting di firmware,
    # lihat komentar di evaluate_calibration_model()), cuma menyimpan &
    # mengembalikannya apa adanya lewat GET_CONFIG. Ini murni jaring
    # pengaman supaya titik kalibrasi tidak hilang total kalau device
    # dipindah ke PC lain yang belum pernah menyimpan cache-nya.
    "calibration_points": {},
    "device_identity": {"pn": "", "sn": "", "firmware_version": ""},
    # Cache kalibrasi PER SERIAL NUMBER (SN) device fisik -- karena satu PC
    # ini bisa dipakai bergantian untuk banyak unit device yang beda
    # karakteristik sensornya. "calibration"/"calibration_points" di atas
    # selalu berisi profil device yang SEDANG aktif (device yang terakhir
    # terhubung dan teridentifikasi); begitu SN device yang connect
    # berbeda dari SN aktif sebelumnya, app otomatis switch: snapshot
    # profil lama disimpan ke sini dulu, baru profil SN baru dimuat ke
    # "calibration"/"calibration_points" di atas -- kalau PC ini belum
    # pernah mengenal SN itu, keduanya ditarik dari device sendiri lewat
    # GET_CONFIG (lihat _handle_identity), termasuk titik mentahnya karena
    # sekarang device juga menyimpannya.
    # Format: {sn: {"pn":..., "firmware_version":..., "calibration":{...},
    #                "calibration_points":{...}}}
    "device_profiles": {},
    "buzzer": {
        "patterns": 10
    },
    "logging": {
        "data_enabled": True,
        "data_interval_sec": 60,
        "data_retention_days": 7,
        "system_enabled": True,
        "system_retention_days": 30,
    },
    # Timer refresh e-paper (SSD1680), disinkron dua arah dengan device
    # lewat SET_DISPLAY_CONFIG / GET_CONFIG. update_interval_sec = jeda
    # antar partial refresh (nilai default sensor/waktu/wifi di layar),
    # full_refresh_interval_min = jeda antar full-refresh (bersihkan
    # ghosting panel).
    "display": {
        "update_interval_sec": 60,
        "full_refresh_interval_min": 30,
    },
    # Kirim data ke gerbang HTTP udaraku (POST). Menggantikan jalur "server"
    # (JWT-signed, iot.kemenperin.go.id) yang lama -- lihat udaraku_sync.py di
    # firmware. "key" = Bearer key alat (BUKAN private key untuk signing --
    # kontraknya beda dari jalur lama). "kode_alat" boleh berbeda dari SN
    # device, diisi manual. "kanal" = daftar payload key yang dikirim (mis.
    # ["t","h"]); dibiarkan kosong berarti SEMUA kanal dikirim (begitu cara
    # firmware menafsirkan "kanal" kosong/falsy -- lihat udaraku_sync.py).
    # "queue_interval_sec"/"queue_enabled" = perilaku backlog CSV, sama
    # semangatnya dengan jalur server lama tapi mekanismenya ada di
    # udaraku_sync (firmware), bukan di sini.
    "udaraku": {
        "enabled": False,
        "url": "",
        "key": "",
        "kode_alat": "",
        "interval_sec": 60,
        "timeout_sec": 15,
        "kanal": [],
        "queue_enabled": True,
        "queue_interval_sec": 5,
        "fail_buzzer_enabled": True,
        "fail_buzzer_pattern": 3,
        "success_buzzer_enabled": True,
        "success_buzzer_pattern": 1,
    },
    # Preferensi tampilan aplikasi (BUKAN pengaturan alat) -- disimpan
    # terpisah supaya jelas ini murni preferensi PC/GUI, tidak pernah
    # dikirim ke firmware. "accent" merujuk ke key di ACCENT_PRESETS.
    "ui": {
        "accent": "blue",
        "theme": "light_blue",
        "font_family": "Segoe UI",
        "font_size": 13,
        "custom_colors": {},
    },
}


# ---------------------------------------------------------------------------
# SISTEM TEMA KOMPREHENSIF
# ---------------------------------------------------------------------------
# Theme lama berbasis "accent" tetap dibaca untuk kompatibilitas config lama.
# Pengaturan baru disimpan di ui.theme, tetapi tidak mengubah konfigurasi ESP32.

DEFAULT_THEME = {
    "label": "Light Blue",
    "window_bg": "#e6e6e6",
    "surface_bg": "#ffffff",
    "surface_alt": "#f4f4f4",
    "panel_bg": "#fafafa",
    "topbar_bg": "#f4f4f4",
    "border": "#b7b7b7",
    "border_light": "#d6d6d6",
    "text": "#1a1a1a",
    "muted_text": "#6e6e6e",
    "input_bg": "#ffffff",
    "input_text": "#1a1a1a",
    "button_bg": "#ffffff",
    "button_text": "#1a1a1a",
    "button_hover": "#ececec",
    "button_pressed": "#dcdcdc",
    "accent": "#2f6fb0",
    "accent_hover": "#275c94",
    "accent_pressed": "#1f4a78",
    "success": "#2e8b57",
    "success_hover": "#257046",
    "danger": "#c0392b",
    "danger_hover": "#a5301f",
    "warning": "#a9720a",
    "warning_hover": "#8c5e08",
    "disabled_bg": "#f1f1f1",
    "disabled_text": "#a5a5a5",
    "terminal_bg": "#1c1e22",
    "terminal_text": "#d8dade",
    "terminal_border": "#2a2d33",
    "terminal_timestamp": "#8c939b",
    "plot_bg": "#ffffff",
    "plot_grid": "#9ca3af",
    "selection_bg": "#2f6fb0",
    "selection_text": "#ffffff",
    "font_family": "Segoe UI",
    "font_size": 13,
}

def _theme_variant(label, base=DEFAULT_THEME, **overrides):
    theme = dict(base)
    theme.update(overrides)
    theme["label"] = label
    return theme

# Semua preset dibangun dari DEFAULT_THEME secara berurutan. Tidak ada preset
# yang merujuk dirinya sendiri, sehingga tidak mungkin terjadi NameError/recursive
# dict construction seperti pada versi sebelumnya.
THEME_PRESETS = {}

THEME_PRESETS["light_blue"] = _theme_variant("Light Blue")
THEME_PRESETS["light_teal"] = _theme_variant(
    "Light Teal", accent="#1f7a6c", accent_hover="#19624f", accent_pressed="#134a3d",
    plot_grid="#8ca6a0", selection_bg="#1f7a6c"
)
THEME_PRESETS["warm_light"] = _theme_variant(
    "Warm Light", window_bg="#ece8e1", surface_bg="#fffdf8", surface_alt="#f5f0e8",
    panel_bg="#fcfaf5", topbar_bg="#f4eee4", border="#b9b0a4", border_light="#ddd4c8",
    text="#2a2724", muted_text="#716960", input_bg="#fffdf8", input_text="#2a2724",
    button_bg="#fffdf8", button_text="#2a2724", button_hover="#efe8dd", button_pressed="#e5ddcf",
    accent="#a9720a", accent_hover="#8c5e08", accent_pressed="#704a06",
    warning="#9a6a0a", warning_hover="#7b5407", plot_bg="#fffdf8", plot_grid="#b0a79d",
    selection_bg="#a9720a"
)
THEME_PRESETS["light_purple"] = _theme_variant(
    "Light Purple", window_bg="#ece8f4", surface_alt="#f3eff8", panel_bg="#fbf9fd",
    topbar_bg="#f2edf8", border="#b7aac4", border_light="#ddd5e4", text="#29242f",
    muted_text="#746b7c", button_hover="#eee7f3", button_pressed="#e3d9ea",
    accent="#7652a8", accent_hover="#63418f", accent_pressed="#503476", plot_grid="#aaa0b6",
    selection_bg="#7652a8"
)
THEME_PRESETS["light_green"] = _theme_variant(
    "Light Green", window_bg="#e8efe9", surface_alt="#f0f5f1", panel_bg="#f9fcfa",
    topbar_bg="#edf4ef", border="#a9b8ad", border_light="#d4ddd6", text="#243028",
    muted_text="#69766d", button_hover="#e7f0e9", button_pressed="#dce8df",
    accent="#2f7d4a", accent_hover="#286a3e", accent_pressed="#205632", plot_grid="#9fad9f",
    selection_bg="#2f7d4a"
)
THEME_PRESETS["nordic_light"] = _theme_variant(
    "Nordic Light", window_bg="#e8edf2", surface_bg="#fdfefe", surface_alt="#eef3f7",
    panel_bg="#f8fafc", topbar_bg="#edf2f6", border="#aab5bf", border_light="#d6dde3",
    text="#27313a", muted_text="#667581", button_hover="#e8eef3", button_pressed="#dde5eb",
    accent="#4f6f8f", accent_hover="#405d79", accent_pressed="#334b61", plot_bg="#fdfefe",
    plot_grid="#aab6c1", selection_bg="#4f6f8f"
)
THEME_PRESETS["sand_light"] = _theme_variant(
    "Sand Light", window_bg="#e9e3d8", surface_bg="#fffdf7", surface_alt="#f3ede2",
    panel_bg="#fbf7ef", topbar_bg="#efe7da", border="#b8aa96", border_light="#d8cdbd",
    text="#2b2926", muted_text="#756c61", button_bg="#fffdf8", button_text="#2b2926",
    button_hover="#eee5d7", button_pressed="#e1d6c5", input_bg="#fffdf8", input_text="#2b2926",
    accent="#8b6b3f", accent_hover="#72552f", accent_pressed="#5b4324", plot_bg="#fffdf8",
    plot_grid="#b9ae9e", selection_bg="#8b6b3f"
)
THEME_PRESETS["dark_slate"] = _theme_variant(
    "Dark Slate", window_bg="#1d2127", surface_bg="#252a31", surface_alt="#2c323a",
    panel_bg="#293039", topbar_bg="#232831", border="#47515d", border_light="#39424d",
    text="#e7eaf0", muted_text="#a8b0bc", input_bg="#1f242b", input_text="#e7eaf0",
    button_bg="#303741", button_text="#e7eaf0", button_hover="#3a444f", button_pressed="#454f5b",
    accent="#4c9be8", accent_hover="#3986cf", accent_pressed="#2e6da8",
    success="#3fa76d", success_hover="#328b59", danger="#dc5a4e", danger_hover="#b8473d",
    warning="#d2a23a", warning_hover="#b48522", disabled_bg="#30343a", disabled_text="#727b87",
    terminal_bg="#111418", terminal_text="#d9dee7", terminal_border="#333a44",
    terminal_timestamp="#7f8995", plot_bg="#20252b", plot_grid="#68717c",
    selection_bg="#4c9be8"
)
THEME_PRESETS["dark_blue"] = _theme_variant(
    "Dark Blue", THEME_PRESETS["dark_slate"], window_bg="#17202b", surface_bg="#1f2b38",
    surface_alt="#263646", panel_bg="#223140", topbar_bg="#1c2834", border="#41576b",
    border_light="#334858", text="#e7eef5", muted_text="#a4b5c5", input_bg="#18242f",
    input_text="#e7eef5", button_bg="#2a3a4a", button_text="#e7eef5", button_hover="#35495c",
    button_pressed="#40596d", accent="#3f8edb", accent_hover="#3277ba", accent_pressed="#285f96",
    terminal_bg="#0f1821", plot_bg="#1b2732", plot_grid="#617487", selection_bg="#3f8edb"
)
THEME_PRESETS["midnight_blue"] = _theme_variant(
    "Midnight Blue", THEME_PRESETS["dark_slate"], window_bg="#101722", surface_bg="#182231",
    surface_alt="#202d3f", panel_bg="#1c2939", topbar_bg="#141e2c", border="#40516a",
    border_light="#314157", text="#e9f0f8", muted_text="#a7b6c8", input_bg="#121c29",
    input_text="#e9f0f8", button_bg="#223145", button_text="#e9f0f8", button_hover="#2c3d54",
    button_pressed="#364b66", accent="#5aa9ff", accent_hover="#428fe2", accent_pressed="#2e73bc",
    terminal_bg="#0a0f16", plot_bg="#111b28", plot_grid="#52657f", selection_bg="#5aa9ff"
)
THEME_PRESETS["dark_purple"] = _theme_variant(
    "Dark Purple", THEME_PRESETS["dark_slate"], window_bg="#241f2b", surface_bg="#30283a",
    surface_alt="#382f45", panel_bg="#332b40", topbar_bg="#2b2435", border="#5b4d68",
    border_light="#493d56", text="#f0ebf4", muted_text="#b8aebe", input_bg="#261f2f",
    input_text="#f0ebf4", button_bg="#3c3248", button_text="#f0ebf4", button_hover="#4a3e58",
    button_pressed="#574866", accent="#9a6bd2", accent_hover="#8256b9", accent_pressed="#69439a",
    terminal_bg="#17121c", plot_bg="#2b2533", plot_grid="#786a86", selection_bg="#9a6bd2"
)
THEME_PRESETS["dark_green"] = _theme_variant(
    "Dark Green", THEME_PRESETS["dark_slate"], window_bg="#1d2822", surface_bg="#26352c",
    surface_alt="#2d3f34", panel_bg="#2a392f", topbar_bg="#222f27", border="#496052",
    border_light="#3a4e41", text="#e6efe9", muted_text="#aabaae", input_bg="#1b2720",
    input_text="#e6efe9", button_bg="#33453a", button_text="#e6efe9", button_hover="#3d5243",
    button_pressed="#48604e", accent="#4eaa72", accent_hover="#3f8f5e", accent_pressed="#337448",
    terminal_bg="#101812", plot_bg="#202d25", plot_grid="#65766b", selection_bg="#4eaa72"
)
THEME_PRESETS["oled_dark"] = _theme_variant(
    "OLED Dark", THEME_PRESETS["dark_slate"], window_bg="#050505", surface_bg="#0b0b0b",
    surface_alt="#111111", panel_bg="#0d0d0d", topbar_bg="#080808", border="#2a2a2a",
    border_light="#1c1c1c", text="#f2f2f2", muted_text="#999999", input_bg="#080808",
    input_text="#f2f2f2", button_bg="#141414", button_text="#f2f2f2", button_hover="#202020",
    button_pressed="#2a2a2a", accent="#38a6ff", accent_hover="#2588d8", accent_pressed="#1c6cae",
    terminal_bg="#000000", plot_bg="#050505", plot_grid="#444444", selection_bg="#38a6ff"
)


DEFAULT_THEME_KEY = "light_blue"

# Legacy accent presets tetap dipertahankan supaya file device_config.json lama
# dan panggilan internal lama tidak rusak.
ACCENT_PRESETS = {
    "blue": {"label": "Biru", "base": "#2f6fb0", "hover": "#275c94", "pressed": "#1f4a78"},
    "teal": {"label": "Teal", "base": "#1f7a6c", "hover": "#19624f", "pressed": "#134a3d"},
    "amber": {"label": "Amber", "base": "#a9720a", "hover": "#8c5e08", "pressed": "#704a06"},
    "graphite": {"label": "Graphite", "base": "#3a3a3a", "hover": "#2c2c2c", "pressed": "#1e1e1e"},
}
DEFAULT_ACCENT = "blue"
LEGACY_ACCENT_TO_THEME = {
    "blue": "light_blue",
    "teal": "light_teal",
    "amber": "warm_light",
    "graphite": "dark_slate",
}

_STYLESHEET_TEMPLATE = """
QWidget {{
    font-family: \"{font_family}\", \"Segoe UI\", \"Cantarell\", \"Noto Sans\", sans-serif;
    font-size: {font_size}px;
    color: {text};
    background-color: {window_bg};
}}
QFrame#topBar {{ background-color: {topbar_bg}; border-bottom: 1px solid {border}; }}
QLabel#appTitle {{ font-size: 15px; font-weight: 700; color: {text}; background: transparent; }}
QLabel#appSubtitle {{ font-size: 11px; color: {muted_text}; background: transparent; }}
QTabBar::tab {{ color: {text}; background: {surface_alt}; padding: 7px 12px; border: 1px solid transparent; }}
QTabBar::tab:selected {{ background: {surface_bg}; border-bottom: 3px solid {accent}; }}
QTabBar::tab:hover {{ background: {button_hover}; }}
QGroupBox {{ color: {text}; background: {panel_bg}; border: 1px solid {border_light}; border-radius: 5px; margin-top: 10px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {text}; background: {panel_bg}; }}
QPushButton {{ background: {button_bg}; color: {button_text}; border: 1px solid {border}; border-radius: 4px; padding: 6px 12px; font-weight: 600; }}
QPushButton:hover {{ background: {button_hover}; border-color: {accent}; }}
QPushButton:pressed {{ background: {button_pressed}; }}
QPushButton:disabled {{ background: {disabled_bg}; border-color: {border_light}; color: {disabled_text}; }}
QPushButton#btnPrimary {{ background: {accent}; border-color: {accent}; color: #ffffff; }}
QPushButton#btnPrimary:hover {{ background: {accent_hover}; border-color: {accent_hover}; }}
QPushButton#btnPrimary:pressed {{ background: {accent_pressed}; border-color: {accent_pressed}; }}
QPushButton#btnDanger {{ background: {danger}; border-color: {danger}; color: #ffffff; }}
QPushButton#btnDanger:hover {{ background: {danger_hover}; border-color: {danger_hover}; }}
QPushButton#btnSuccess {{ background: {success}; border-color: {success}; color: #ffffff; }}
QPushButton#btnSuccess:hover {{ background: {success_hover}; border-color: {success_hover}; }}
QPushButton#btnPrimary:disabled, QPushButton#btnDanger:disabled, QPushButton#btnSuccess:disabled {{ background: {disabled_bg}; border-color: {border_light}; color: {disabled_text}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {input_bg}; color: {input_text}; border: 1px solid {border}; border-radius: 4px; padding: 6px 8px; selection-background-color: {selection_bg}; selection-color: {selection_text}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {accent}; }}
/* PERBAIKAN: dulu ada styling custom "QComboBox::drop-down" +
   "QComboBox QAbstractItemView" di sini supaya warna popup ikut tema.
   Kombinasi keduanya (tanpa QComboBox::down-arrow / ::item eksplisit)
   kena bug Qt/Fusion yang cukup dikenal: popup-nya tetap berfungsi
   (bisa di-scroll/dipilih lewat keyboard) tapi baris-barisnya dirender
   dengan tinggi ~0px, jadi item TIDAK PERNAH kelihatan sama sekali --
   persis gejala "dropdown payload hilang, padahal bisa discroll" yang
   dilaporkan. Dihapus supaya popup QComboBox kembali dirender native
   oleh Qt (cocok dengan referensi UI yang terbukti jalan normal). */
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 20px; border-left: 1px solid {border}; border-bottom: 1px solid {border_light}; border-top-right-radius: 4px; background: {button_bg}; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 20px; border-left: 1px solid {border}; border-bottom-right-radius: 4px; background: {button_bg}; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background: {button_hover}; }}
/* Arrow digambar oleh subclass ThemedSpinBox/ThemedDoubleSpinBox. */
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ width: 0px; height: 0px; image: none; }}
QCheckBox, QRadioButton {{ color: {text}; background: transparent; }}
QTableWidget, QListWidget, QTreeWidget {{ background: {surface_bg}; alternate-background-color: {surface_alt}; color: {text}; border: 1px solid {border_light}; gridline-color: {border_light}; selection-background-color: {selection_bg}; selection-color: {selection_text}; }}
QHeaderView::section {{ background: {surface_alt}; color: {text}; border: 1px solid {border_light}; padding: 5px; }}
QScrollArea {{ background: {window_bg}; border: none; }}
QLabel#statusCard {{ background: {surface_bg}; color: {text}; border: 1px solid {border_light}; border-radius: 4px; padding: 8px 12px; font-weight: 600; }}
QLabel#statusBadgeConnected {{ background: {success}; color: #ffffff; border-radius: 3px; padding: 3px 12px; font-weight: 700; }}
QLabel#statusBadgeDisconnected {{ background: {disabled_text}; color: #ffffff; border-radius: 3px; padding: 3px 12px; font-weight: 700; }}
QLabel#statusBadgeError {{ background: {danger}; color: #ffffff; border-radius: 3px; padding: 3px 12px; font-weight: 700; }}
QTextEdit#terminal {{ background: {terminal_bg}; color: {terminal_text}; border: 1px solid {terminal_border}; font-family: \"Consolas\", \"Courier New\", monospace; padding: 8px; }}
QToolTip {{ background: {surface_bg}; color: {text}; border: 1px solid {border}; }}
QProgressBar {{ background: {surface_alt}; color: {text}; border: 1px solid {border}; border-radius: 4px; text-align: center; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}
"""

def normalize_theme(theme):
    out = dict(DEFAULT_THEME)
    if isinstance(theme, dict):
        out.update({k: v for k, v in theme.items() if k in out})
    try:
        out["font_size"] = max(9, min(24, int(out.get("font_size", 13))))
    except (TypeError, ValueError):
        out["font_size"] = 13
    out["font_family"] = str(out.get("font_family") or DEFAULT_THEME["font_family"])
    return out

def theme_from_config(ui_cfg):
    ui_cfg = ui_cfg if isinstance(ui_cfg, dict) else {}
    key = str(ui_cfg.get("theme", "")).strip()
    if key == "custom":
        theme = normalize_theme(THEME_PRESETS[DEFAULT_THEME_KEY])
    else:
        if key not in THEME_PRESETS:
            legacy = str(ui_cfg.get("accent", DEFAULT_ACCENT)).strip()
            key = LEGACY_ACCENT_TO_THEME.get(legacy, DEFAULT_THEME_KEY)
        theme = normalize_theme(THEME_PRESETS.get(key, THEME_PRESETS[DEFAULT_THEME_KEY]))
    custom = ui_cfg.get("custom_colors")
    if isinstance(custom, dict):
        for k, v in custom.items():
            if k in theme and isinstance(v, str):
                theme[k] = v
        theme["label"] = "Custom"
    if "font_family" in ui_cfg:
        theme["font_family"] = str(ui_cfg.get("font_family") or theme["font_family"])
    if "font_size" in ui_cfg:
        try:
            theme["font_size"] = max(9, min(24, int(ui_cfg["font_size"])))
        except (TypeError, ValueError):
            pass
    return key, normalize_theme(theme)

def build_stylesheet(theme):
    theme = normalize_theme(theme)
    return _STYLESHEET_TEMPLATE.format(**theme)

def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in cfg})
            if isinstance(data.get("dashboard"), dict):
                cfg["dashboard"].update(data["dashboard"])
            if isinstance(data.get("device"), dict):
                cfg["device"].update(data["device"])
            if isinstance(data.get("buzzer"), dict):
                cfg["buzzer"].update(data["buzzer"])
            if isinstance(data.get("logging"), dict):
                cfg["logging"].update(data["logging"])
            if isinstance(data.get("udaraku"), dict):
                cfg["udaraku"].update(data["udaraku"])
            if isinstance(data.get("ui"), dict):
                cfg["ui"].update(data["ui"])
                if isinstance(data["ui"].get("custom_colors"), dict):
                    cfg["ui"]["custom_colors"] = dict(data["ui"]["custom_colors"])
            if "thresholds" in data:
                cfg["thresholds"] = data["thresholds"]
        return cfg
    except Exception:
        return json.loads(json.dumps(DEFAULT_CONFIG))

def save_config(config):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)

def format_file_size(num_bytes):
    """Format ukuran file dalam B/KB/MB yang mudah dibaca (dipakai di tabel
    SD Card & dialog progress download)."""
    try:
        num_bytes = float(num_bytes)
    except (TypeError, ValueError):
        return "--"
    if num_bytes < 1024:
        return f"{int(num_bytes)} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"

class SerialWorker(QThread):
    data_received = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, port, baudrate=115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = True

    def run(self):
        buffer = ""
        try:
            # PENTING: DTR/RTS di-set ke False SEBELUM open(), bukan sesudah.
            # pyserial menerapkan level DTR/RTS PADA SAAT open() dipanggil --
            # serial.Serial(port, baud, ...) (constructor lama) otomatis
            # meng-open() dengan DTR/RTS default (biasanya HIGH/asserted),
            # dan setDTR(False)/setRTS(False) yang dipanggil SETELAHNYA cuma
            # menutup pintu setelah kuda lepas: pulsa reset ke rangkaian
            # auto-reset board (DTR->EN, RTS->GPIO0) sudah keburu terjadi
            # dengan level HIGH itu. Kalau pulsa EN itu kebetulan berbarengan
            # GPIO0 masih ter-sample LOW, ESP32 masuk ROM bootloader (download
            # mode) alih-alih boot MicroPython -- device jadi diam total
            # (tidak pernah kirim "INFO"/TELEMETRY apa pun), persis gejala
            # "stuck di menghubungkan ke serial" yang cuma bisa diperbaiki
            # dengan reset FISIK (bukan software) karena bootloader ROM tidak
            # merespons command JSON apa pun. Ini race condition (bukan bug
            # deterministik) -- makin rawan kalau baru saja disconnect dari
            # sesi Thonny sebelumnya.
            #
            # Fix: buat objek Serial KOSONG dulu, set port/baudrate/DTR/RTS,
            # baru panggil open() -- supaya level DTR/RTS yang diterapkan
            # SAAT port benar-benar dibuka sudah False sejak awal, tidak ada
            # window HIGH sama sekali.
            self.ser = serial.Serial()
            self.ser.port = self.port
            self.ser.baudrate = self.baudrate
            self.ser.timeout = 0.1
            self.ser.dtr = False
            self.ser.rts = False
            self.ser.open()
            time.sleep(0.5)
            self.ser.reset_input_buffer()
            while self.running:
                if self.ser.in_waiting:
                    buffer += self.ser.read(self.ser.in_waiting).decode("utf-8", errors="ignore")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if line:
                            self.data_received.emit(line)
                time.sleep(0.01)
        except Exception as exc:
            self.error_signal.emit(str(exc))
        finally:
            try:
                if self.ser and self.ser.is_open:
                    self.ser.close()
            except Exception:
                pass

    def write_data(self, data):
        if self.ser and self.ser.is_open:
            try:
                self.ser.write((data + "\n").encode("utf-8"))
                return True
            except Exception as exc:
                self.error_signal.emit(f"Gagal kirim data serial: {exc}")
        return False

    def stop(self):
        self.running = False
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass
        self.wait()


class _ThemedSpinMixin:
    """Mixin untuk menggambar panah spinner secara deterministik.

    QSS Qt menghilangkan arrow native ketika subcontrol arrow di-custom.
    Versi sebelumnya melakukan custom QSS tetapi tidak menyediakan image
    arrow, sehingga area +/− terlihat kosong. Mixin ini menggambar segitiga
    langsung pada area tombol setelah renderer Qt selesai menggambar widget.
    """
    def _paint_spin_arrows(self):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        enabled = self.isEnabled()
        color = self.palette().text().color()
        if not enabled:
            color.setAlpha(100)
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)

        w = 20
        x0 = max(0, self.width() - w)
        half = self.height() // 2
        cx = x0 + w // 2
        tri_w = 8
        tri_h = 5

        painter.drawPolygon(QPolygonF([
            QPointF(cx, half - 6),
            QPointF(cx - tri_w / 2, half - 6 + tri_h),
            QPointF(cx + tri_w / 2, half - 6 + tri_h),
        ]))
        painter.drawPolygon(QPolygonF([
            QPointF(cx, half + 6),
            QPointF(cx - tri_w / 2, half + 6 - tri_h),
            QPointF(cx + tri_w / 2, half + 6 - tri_h),
        ]))
        painter.end()

class ThemedSpinBox(QSpinBox, _ThemedSpinMixin):
    def paintEvent(self, event):
        super().paintEvent(event)
        self._paint_spin_arrows()

class ThemedDoubleSpinBox(QDoubleSpinBox, _ThemedSpinMixin):
    def paintEvent(self, event):
        super().paintEvent(event)
        self._paint_spin_arrows()


class SensorConfigDialog(QDialog):
    def __init__(self, parent=None, config=None, payload_keys=None):
        super().__init__(parent)
        config = config or {}
        payload_keys = payload_keys or []
        self.setWindowTitle("Konfigurasi Widget (Value Card)")
        self.resize(380, 250)

        form = QFormLayout(self)

        self.cb_key = QComboBox()
        self.cb_key.setEditable(True)
        self.cb_key.addItems(payload_keys)
        self.cb_key.setCurrentText(str(config.get("key", "")))

        self.txt_label = QLineEdit(str(config.get("label", "")))
        self.txt_unit = QLineEdit(str(config.get("unit", "")))

        self.sp_dec = ThemedSpinBox()
        self.sp_dec.setRange(0, 6)
        self.sp_dec.setValue(int(config.get("decimals", 1)))

        self.chk_graph = QCheckBox("Tampilkan pada grafik & rekam CSV")
        self.chk_graph.setChecked(bool(config.get("show_graph", True)))

        form.addRow("Payload key:", self.cb_key)
        form.addRow("Label (Judul):", self.txt_label)
        form.addRow("Satuan (Unit):", self.txt_unit)
        form.addRow("Jumlah Desimal:", self.sp_dec)
        form.addRow("", self.chk_graph)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def get_config(self):
        key = self.cb_key.currentText().strip()
        return {
            "key": key,
            "label": self.txt_label.text().strip() or key,
            "unit": self.txt_unit.text().strip(),
            "decimals": self.sp_dec.value(),
            "show_graph": self.chk_graph.isChecked(),
        }


class ThresholdDialog(QDialog):
    def __init__(self, parent=None, payload_keys=None, threshold=None):
        super().__init__(parent)
        threshold = threshold or {}
        payload_keys = payload_keys or []
        self.setWindowTitle("Konfigurasi Threshold")
        self.resize(420, 300)

        form = QFormLayout(self)

        self.cb_payload = QComboBox()
        self.cb_payload.setEditable(True)
        self.cb_payload.addItems(payload_keys)
        self.cb_payload.setCurrentText(str(threshold.get("payload", "")))

        self.cb_operator = QComboBox()
        self.cb_operator.addItems([">", ">=", "<", "<=", "==", "!="])
        self.cb_operator.setCurrentText(str(threshold.get("operator", ">")))

        self.sp_value = ThemedDoubleSpinBox()
        self.sp_value.setRange(-1e12, 1e12)
        self.sp_value.setDecimals(6)
        self.sp_value.setValue(float(threshold.get("value", 0)))

        self.cb_buzzer = QComboBox()
        for i in range(1, BUZZER_PATTERN_COUNT + 1):
            self.cb_buzzer.addItem(f"Pattern {i}", i)
        self.cb_buzzer.setCurrentIndex(
            max(0, min(BUZZER_PATTERN_COUNT - 1, int(threshold.get("buzzer", 1)) - 1))
        )

        self.sp_interval = ThemedSpinBox()
        self.sp_interval.setRange(1, 1440)
        self.sp_interval.setSuffix(" menit")
        interval_sec = threshold.get("interval_sec", 300)
        try:
            interval_sec = int(interval_sec)
        except (TypeError, ValueError):
            interval_sec = 300
        self.sp_interval.setValue(max(1, min(1440, (interval_sec + 59) // 60)))

        self.chk_enabled = QCheckBox("Threshold aktif")
        self.chk_enabled.setChecked(bool(threshold.get("enabled", True)))

        form.addRow("Payload:", self.cb_payload)
        form.addRow("Operator:", self.cb_operator)
        form.addRow("Nilai:", self.sp_value)
        form.addRow("Buzzer:", self.cb_buzzer)
        form.addRow("Interval:", self.sp_interval)
        form.addRow("", self.chk_enabled)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def get_threshold(self):
        return {
            "payload": self.cb_payload.currentText().strip(),
            "operator": self.cb_operator.currentText(),
            "value": self.sp_value.value(),
            "buzzer": int(self.cb_buzzer.currentData()),
            "interval_sec": int(self.sp_interval.value()) * 60,
            "enabled": self.chk_enabled.isChecked(),
        }


# ---------------------------------------------------------------------------
# Model kalibrasi non-linear -- fitting multi-titik + pemilihan R^2 terbaik.
#
# evaluate_calibration_model() SENGAJA diduplikasi dari payload_manager.py
# (bukan di-import) karena dashboard ini berjalan di PC dan firmware
# (payload_manager.py) berjalan terpisah di device -- keduanya tidak selalu
# berbagi filesystem yang sama. Kalau modul ini diubah, payload_manager.py
# harus disinkronkan manual (dan sebaliknya) supaya nilai preview di GUI
# sama persis dengan yang benar-benar dihitung firmware.
#
# Fitting di bawah pakai numpy/scipy (dependency tambahan -- butuh
# `pip install numpy scipy`):
#   - linear/poly2/poly3 -> numpy.polyfit (least-squares via SVD, jauh
#     lebih stabil numerik utk data yang nyaris collinear / ill-conditioned
#     dibanding normal-equations manual).
#   - exponential/logarithmic/power -> scipy.optimize.curve_fit, yaitu
#     nonlinear least-squares (Levenberg-Marquardt) di ruang y ASLI.
#     Ini SENGAJA bukan pendekatan "linearisasi" (regresi pada ln(x)/ln(y))
#     -- linearisasi meminimalkan error di ruang log, bukan di satuan
#     sensor yang sebenarnya, jadi hasilnya bias, khususnya kalau titik
#     kalibrasi tersebar tidak merata. curve_fit tetap dikasih initial
#     guess dari linearisasi (via _linearized_guess_*) supaya konvergen
#     lebih stabil & cepat, tapi hasil akhirnya di-refine di ruang asli.
#
# Firmware (payload_manager.py) TIDAK ikut pakai numpy/scipy -- device
# hanya perlu evaluate_calibration_model() (murni math dasar), bukan
# fitting, dan target embedded pada umumnya tidak punya scipy sama sekali.
# ---------------------------------------------------------------------------

CALIBRATION_MODEL_PARAM_COUNTS = {
    "linear": 2,        # [a, b]       -> y = a*x + b
    "poly2": 3,         # [a, b, c]    -> y = a*x^2 + b*x + c
    "poly3": 4,         # [a, b, c, d] -> y = a*x^3 + b*x^2 + c*x + d
    "exponential": 2,   # [a, b]       -> y = a * e^(b*x)
    "logarithmic": 2,   # [a, b]       -> y = a*ln(x) + b   (butuh x > 0)
    "power": 2,         # [a, b]       -> y = a * x^b       (butuh x > 0)
}

CALIBRATION_MODEL_LABELS = {
    "linear": "Linear (y = ax + b)",
    "poly2": "Polinomial derajat 2 (y = ax\u00b2 + bx + c)",
    "poly3": "Polinomial derajat 3 (y = ax\u00b3 + bx\u00b2 + cx + d)",
    "exponential": "Eksponensial (y = a\u00b7e^(bx))",
    "logarithmic": "Logaritmik (y = a\u00b7ln(x) + b)",
    "power": "Pangkat (y = a\u00b7x^b)",
}


def evaluate_calibration_model(model, params, value):
    """Hitung nilai terkalibrasi untuk satu model+params pada satu nilai
    mentah. Mengembalikan None kalau model/params tidak valid atau di luar
    domain (mis. logarithmic/power untuk value <= 0). Harus tetap identik
    secara perilaku dengan payload_manager.evaluate_calibration_model() --
    fungsi ini SENGAJA masih pure math (bukan numpy) walau modul ini sudah
    boleh pakai numpy/scipy, supaya evaluasi satu-nilai tetap murah dan
    tidak menyeret overhead array numpy untuk kasus sesederhana ini."""
    try:
        if model == "linear":
            a, b = params
            return a * value + b
        if model == "poly2":
            a, b, c = params
            return a * value * value + b * value + c
        if model == "poly3":
            a, b, c, d = params
            return a * value ** 3 + b * value ** 2 + c * value + d
        if model == "exponential":
            a, b = params
            return a * math.exp(b * value)
        if model == "logarithmic":
            a, b = params
            if value <= 0:
                return None
            return a * math.log(value) + b
        if model == "power":
            a, b = params
            if value <= 0:
                return None
            return a * (value ** b)
    except (TypeError, ValueError, OverflowError, ZeroDivisionError):
        return None
    return None


def _safe_polyfit(xs, ys, degree):
    """np.polyfit dibungkus try/except + RankWarning di-silent-kan --
    kembalikan None (bukan raise) kalau sistemnya singular/ill-conditioned
    (mis. titik x kurang bervariasi untuk derajat yang diminta). Warning
    disupres generik (bukan import np.RankWarning langsung) karena lokasi
    kelas itu pindah antar versi numpy (np.RankWarning di numpy<2,
    np.exceptions.RankWarning di numpy>=2)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            coeffs = np.polyfit(xs, ys, degree)
        if np.any(np.isnan(coeffs)) or np.any(np.isinf(coeffs)):
            return None
        return coeffs
    except (np.linalg.LinAlgError, ValueError):
        return None


def _linearized_guess_exponential(xs, ys):
    """Initial guess untuk curve_fit(exponential) lewat linearisasi
    ln(y) = ln(a) + b*x. Cuma dipakai sebagai titik awal iterasi
    Levenberg-Marquardt, BUKAN hasil akhir -- hasil akhir tetap di-fit di
    ruang y asli lewat curve_fit."""
    fit = _safe_polyfit(xs, np.log(ys), 1)
    if fit is None:
        return [1.0, 0.01]
    slope, intercept = fit
    return [math.exp(intercept), slope]


def _linearized_guess_logarithmic(xs, ys):
    fit = _safe_polyfit(np.log(xs), ys, 1)
    if fit is None:
        return [1.0, 0.0]
    a, b = fit
    return [a, b]


def _linearized_guess_power(xs, ys):
    fit = _safe_polyfit(np.log(xs), np.log(ys), 1)
    if fit is None:
        return [1.0, 1.0]
    slope, intercept = fit
    return [math.exp(intercept), slope]


def _r_squared(ys_actual, ys_pred):
    ys_actual = np.asarray(ys_actual, dtype=float)
    ys_pred = np.asarray(ys_pred, dtype=float)
    ss_tot = float(np.sum((ys_actual - ys_actual.mean()) ** 2))
    ss_res = float(np.sum((ys_actual - ys_pred) ** 2))
    if ss_tot < 1e-12:
        return 1.0 if ss_res < 1e-12 else 0.0
    return 1.0 - ss_res / ss_tot


def fit_calibration_candidates(points):
    """Coba fit beberapa model kalibrasi (linear/poly2/poly3/exponential/
    logarithmic/power) dari titik-titik (raw, ref) yang diberikan, hitung
    R^2 masing-masing di ruang y ASLI, lalu kembalikan list dict
    {"model","params","r2"} terurut dari R^2 terbaik ke terburuk. Model
    yang butuh titik lebih banyak dari yang tersedia, domainnya tidak valid
    (mis. logarithmic/power butuh semua raw > 0), atau gagal konvergen,
    otomatis dilewati -- bukan error, cuma tidak masuk hasil."""
    points = [(float(x), float(y)) for x, y in points]
    xs = np.array([p[0] for p in points], dtype=float)
    ys = np.array([p[1] for p in points], dtype=float)
    n = len(points)
    n_distinct_x = len(set(xs.tolist()))
    results = []

    def try_add(model, params):
        if params is None:
            return
        preds = [evaluate_calibration_model(model, params, x) for x in xs]
        if any(p is None for p in preds):
            return
        r2 = _r_squared(ys, preds)
        results.append({"model": model, "params": [float(p) for p in params], "r2": r2})

    # Linear / poly2 / poly3 -- least-squares polinomial via numpy.polyfit.
    if n >= 2 and n_distinct_x >= 2:
        try_add("linear", _safe_polyfit(xs, ys, 1))
    if n >= 3 and n_distinct_x >= 3:
        try_add("poly2", _safe_polyfit(xs, ys, 2))
    if n >= 4 and n_distinct_x >= 4:
        try_add("poly3", _safe_polyfit(xs, ys, 3))

    # Exponential y = a*e^(bx) -- nonlinear fit, butuh semua ref (y) > 0
    # supaya initial guess dari linearisasi ln(y) valid.
    if n >= 2 and n_distinct_x >= 2 and np.all(ys > 0):
        p0 = _linearized_guess_exponential(xs, ys)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", OptimizeWarning)
                popt, _ = curve_fit(
                    lambda x, a, b: a * np.exp(b * x), xs, ys, p0=p0, maxfev=10000
                )
            try_add("exponential", popt)
        except (RuntimeError, ValueError):
            pass

    # Logarithmic y = a*ln(x) + b -- butuh semua raw (x) > 0.
    if n >= 2 and n_distinct_x >= 2 and np.all(xs > 0):
        p0 = _linearized_guess_logarithmic(xs, ys)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", OptimizeWarning)
                popt, _ = curve_fit(
                    lambda x, a, b: a * np.log(x) + b, xs, ys, p0=p0, maxfev=10000
                )
            try_add("logarithmic", popt)
        except (RuntimeError, ValueError):
            pass

    # Power y = a*x^b -- butuh semua raw (x) > 0 DAN semua ref (y) > 0.
    if n >= 2 and n_distinct_x >= 2 and np.all(xs > 0) and np.all(ys > 0):
        p0 = _linearized_guess_power(xs, ys)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", OptimizeWarning)
                popt, _ = curve_fit(
                    lambda x, a, b: a * np.power(x, b), xs, ys, p0=p0, maxfev=10000
                )
            try_add("power", popt)
        except (RuntimeError, ValueError):
            pass

    results.sort(key=lambda r: r["r2"], reverse=True)
    return results


def _format_calibration_number(value):
    """Format angka param/preview biar rapi di UI -- integer tanpa desimal
    berlebih, float dibulatkan wajar tanpa notasi ilmiah untuk rentang
    kalibrasi sensor yang umum."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.6g}"


class CalibrationWizardDialog(QDialog):
    """Dialog kalibrasi untuk satu payload key. Kalibrasi TIDAK HARUS
    linear lagi -- model yang didukung: linear, poly2, poly3, exponential,
    logarithmic, power (lihat CALIBRATION_MODEL_PARAM_COUNTS).

    Alur pemakaian:
    1) Isi beberapa titik referensi (nilai mentah sensor vs nilai acuan
       alat ukur standar) di tabel "Titik Kalibrasi" -- minimal 2 titik,
       makin banyak titik makin banyak model yang bisa dicoba & makin
       akurat fitting-nya.
    2) Klik "Hitung Otomatis" -- semua model yang datanya cukup (jumlah
       titik & domain valid, mis. logarithmic/power butuh nilai mentah
       semua > 0) di-fit sekaligus, lalu diurutkan dari R^2 terbaik ke
       terburuk di tabel "Hasil Fitting".
    3) Pilih salah satu baris hasil (default: yang R^2-nya tertinggi sudah
       otomatis diterapkan) lalu klik "Gunakan Model Terpilih", ATAU edit
       manual model & params di bagian "Model Kalibrasi Aktif" kalau mau
       menimpa hasil fitting.
    4) Save -- ini yang tersimpan ke self.config['calibration'][key] dan
       (lewat sync_calibration_to_device) dikirim ke firmware."""

    def __init__(self, parent=None, key="", label="", current_cal=None,
                 current_points=None, last_raw=None):
        super().__init__(parent)
        current_cal = current_cal or {}
        self._initial_points = list(current_points) if current_points else []
        self._last_raw = last_raw
        self.setWindowTitle(f"Calibration Wizard -- {label or key}")
        # Dialog boleh di-resize bebas (default QDialog) -- tinggi awal
        # dibatasi supaya tidak melebihi tinggi layar kecil (mis. laptop
        # 1360x768 setelah dikurangi taskbar & title bar), dan isinya
        # dibungkus QScrollArea di bawah supaya kalau tetap kurang, user
        # tinggal scroll alih-alih konten terpotong/dialog tak muat layar.
        # Dialog dilebarkan (dibanding versi 1-kolom lama) supaya layout
        # 2-kolom di bawah (data kiri, grafik kanan) sama-sama lega --
        # tinggi tetap dibatasi ke tinggi layar seperti sebelumnya.
        avail = _available_screen_geometry()
        max_h = avail.height() - 80 if avail is not None else 640
        max_w = avail.width() - 80 if avail is not None else 980
        self.resize(min(980, max(720, max_w)), min(640, max(360, max_h)))
        self.setMinimumSize(720, 360)

        outer = QVBoxLayout(self)

        info_text = f"Payload key: <b>{html.escape(str(key))}</b>"
        if last_raw is not None:
            info_text += f" | Nilai mentah terakhir: <b>{last_raw}</b>"
        lbl_info = QLabel(info_text)
        lbl_info.setWordWrap(True)
        outer.addWidget(lbl_info)

        # Layout 2 kolom: KIRI = semua data/kontrol (titik kalibrasi, tabel
        # hasil fitting, model aktif) dibungkus QScrollArea supaya tetap
        # aman di layar kecil; KANAN = grafik kalibrasi, dibuat lega/besar
        # karena tidak perlu berbagi ruang vertikal dengan tabel-tabel lagi.
        # QSplitter dipakai (bukan QHBoxLayout tetap) supaya user bebas
        # menggeser proporsi kiri/kanan sesuai kebutuhan.
        splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(splitter, stretch=1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_inner = QWidget()
        scroll_layout = QVBoxLayout(scroll_inner)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(14)
        scroll.setWidget(scroll_inner)
        splitter.addWidget(scroll)

        # --- Panel kanan: grafik kalibrasi ---
        panel_graph = QWidget()
        vgraph = QVBoxLayout(panel_graph)
        vgraph.setContentsMargins(0, 0, 0, 0)
        grp_graph = QGroupBox("Grafik Kalibrasi")
        vg = QVBoxLayout(grp_graph)
        self._last_fit_points = []
        self._last_fit_results = []
        lbl_graph = QLabel("Titik & kurva tiap model hasil fitting -- klik baris di tabel Hasil Fitting untuk menyorot kurva.")
        lbl_graph.setWordWrap(True)
        vg.addWidget(lbl_graph)
        self.plot_calibration = pg.PlotWidget()
        self.plot_calibration.setMinimumWidth(320)
        self.plot_calibration.showGrid(x=True, y=True, alpha=0.25)
        self.plot_calibration.setLabel("left", "Nilai Acuan")
        self.plot_calibration.setLabel("bottom", "Nilai Mentah")
        self.plot_calibration.addLegend()
        vg.addWidget(self.plot_calibration, stretch=1)
        vgraph.addWidget(grp_graph, stretch=1)
        splitter.addWidget(panel_graph)

        # Proporsi awal kiri:kanan -- kanan sedikit lebih lebar karena
        # grafik butuh ruang horizontal utk terlihat lega, kiri cukup utk
        # tabel tanpa perlu scroll horizontal.
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([440, 500])

        # --- Titik kalibrasi multi-titik ---
        grp_points = QGroupBox("Titik Kalibrasi (Nilai Mentah -> Nilai Acuan)")
        vp = QVBoxLayout(grp_points)
        self.table_points = QTableWidget()
        self.table_points.setColumnCount(2)
        self.table_points.setHorizontalHeaderLabels(["Nilai Mentah", "Nilai Acuan"])
        self.table_points.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_points.setMinimumHeight(120)
        vp.addWidget(self.table_points)
        if self._initial_points:
            # Pre-populate dari titik yang sudah tersimpan sebelumnya (dari
            # cache PC atau hasil tarik ulang dari device) -- supaya tidak
            # perlu ketik ulang tiap buka wizard.
            for raw, ref in self._initial_points:
                self._add_point_row(raw, ref)
        else:
            for _ in range(2):
                self._add_point_row()

        hp = QHBoxLayout()
        btn_add_point = QPushButton("+ Titik")
        btn_add_point.clicked.connect(lambda: self._add_point_row())
        hp.addWidget(btn_add_point)
        btn_remove_point = QPushButton("- Titik Terpilih")
        btn_remove_point.clicked.connect(self._remove_selected_point_row)
        hp.addWidget(btn_remove_point)
        hp.addStretch()
        vp.addLayout(hp)

        btn_fit = QPushButton("Hitung Otomatis -- Coba Semua Model, Pilih R\u00b2 Terbaik")
        btn_fit.setObjectName("btnPrimary")
        btn_fit.clicked.connect(self._run_fitting)
        vp.addWidget(btn_fit)
        scroll_layout.addWidget(grp_points)

        # --- Hasil fitting ---
        grp_results = QGroupBox("Hasil Fitting (urut R\u00b2 terbaik -> terburuk)")
        vr = QVBoxLayout(grp_results)
        self.table_results = QTableWidget()
        self.table_results.setColumnCount(3)
        self.table_results.setHorizontalHeaderLabels(["Model", "Params", "R\u00b2"])
        self.table_results.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_results.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_results.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_results.setMinimumHeight(100)
        self.table_results.itemDoubleClicked.connect(lambda _item: self._apply_selected_result())
        self.table_results.itemSelectionChanged.connect(self._plot_fitting_results)
        vr.addWidget(self.table_results)
        btn_apply_result = QPushButton("Gunakan Model Terpilih dari Hasil Fitting")
        btn_apply_result.clicked.connect(self._apply_selected_result)
        vr.addWidget(btn_apply_result)
        scroll_layout.addWidget(grp_results)

        # --- Model aktif (hasil fitting diterapkan ke sini, atau isi manual) ---
        grp_active = QGroupBox("Model Kalibrasi Aktif (bisa ditimpa manual)")
        form_active = QFormLayout(grp_active)
        self.cb_model = QComboBox()
        for model_key, model_label in CALIBRATION_MODEL_LABELS.items():
            self.cb_model.addItem(model_label, model_key)
        self.cb_model.currentIndexChanged.connect(self._update_preview)
        form_active.addRow("Model:", self.cb_model)

        self.ed_params = QLineEdit()
        self.ed_params.setPlaceholderText("params dipisah koma, mis. 1.02, -0.3")
        self.ed_params.textChanged.connect(self._update_preview)
        form_active.addRow("Params:", self.ed_params)

        self.lbl_r2 = QLabel("--")
        form_active.addRow("R\u00b2 (dari fitting):", self.lbl_r2)

        self.lbl_preview = QLabel("--")
        form_active.addRow("Preview (nilai mentah terakhir):", self.lbl_preview)
        scroll_layout.addWidget(grp_active)

        # Pre-populate dari kalibrasi yang sudah tersimpan (format baru
        # model+params, ATAU format lama scale/offset -> dianggap linear).
        self._active_r2 = None
        model = current_cal.get("model")
        if model not in CALIBRATION_MODEL_PARAM_COUNTS:
            model = "linear"
            params = [float(current_cal.get("scale", 1.0)), float(current_cal.get("offset", 0.0))]
        else:
            params = current_cal.get("params", [])
        if "r2" in current_cal:
            try:
                self._active_r2 = float(current_cal["r2"])
            except (TypeError, ValueError):
                self._active_r2 = None
        self._set_active_model(model, params, self._active_r2)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save_clicked)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # -- titik kalibrasi -----------------------------------------------
    def _add_point_row(self, raw=None, ref=None):
        row = self.table_points.rowCount()
        self.table_points.insertRow(row)
        self.table_points.setItem(row, 0, QTableWidgetItem("" if raw is None else _format_calibration_number(raw)))
        self.table_points.setItem(row, 1, QTableWidgetItem("" if ref is None else _format_calibration_number(ref)))

    def _remove_selected_point_row(self):
        row = self.table_points.currentRow()
        if row >= 0:
            self.table_points.removeRow(row)

    def _collect_points(self):
        """Baca semua baris yang KEDUA kolomnya terisi angka valid. Baris
        kosong/parsial diabaikan diam-diam supaya user bebas menyisakan
        baris kosong di tabel tanpa perlu menghapusnya."""
        points = []
        for row in range(self.table_points.rowCount()):
            raw_item = self.table_points.item(row, 0)
            ref_item = self.table_points.item(row, 1)
            if raw_item is None or ref_item is None:
                continue
            raw_text = raw_item.text().strip()
            ref_text = ref_item.text().strip()
            if not raw_text or not ref_text:
                continue
            try:
                points.append((float(raw_text), float(ref_text)))
            except ValueError:
                continue
        return points

    # -- fitting ----------------------------------------------------------
    def _run_fitting(self):
        points = self._collect_points()
        if len(points) < 2:
            QMessageBox.warning(
                self, "Peringatan",
                "Minimal butuh 2 titik kalibrasi (nilai mentah & nilai acuan) "
                "yang terisi lengkap untuk menghitung fitting."
            )
            return

        results = fit_calibration_candidates(points)
        self.table_results.setRowCount(0)
        if not results:
            self._last_fit_points = []
            self._last_fit_results = []
            self._plot_fitting_results()
            QMessageBox.warning(
                self, "Peringatan",
                "Tidak ada model yang cocok dihitung dari titik-titik ini "
                "(mis. semua nilai mentah harus sama-sama unik, dan "
                "logarithmic/power butuh nilai mentah semuanya > 0)."
            )
            return

        for res in results:
            row = self.table_results.rowCount()
            self.table_results.insertRow(row)
            self.table_results.setItem(row, 0, QTableWidgetItem(CALIBRATION_MODEL_LABELS.get(res["model"], res["model"])))
            params_text = ", ".join(_format_calibration_number(p) for p in res["params"])
            self.table_results.setItem(row, 1, QTableWidgetItem(params_text))
            self.table_results.setItem(row, 2, QTableWidgetItem(f"{res['r2']:.5f}"))
            # simpan model key & params mentah di item pertama biar bisa
            # dibaca lagi tanpa parsing ulang teks label.
            self.table_results.item(row, 0).setData(Qt.UserRole, res)

        # Simpan hasil mentah supaya grafik bisa digambar ulang (mis. saat
        # baris yang disorot berganti) tanpa perlu fitting ulang tiap kali.
        self._last_fit_points = points
        self._last_fit_results = results

        self.table_results.selectRow(0)
        self._apply_selected_result()

    def _plot_fitting_results(self):
        """Gambar ulang grafik kalibrasi: titik input (scatter) + kurva tiap
        kandidat model dari fitting terakhir, sehingga hasilnya bisa
        dibandingkan secara visual SEBELUM memilih model mana yang dipakai
        dari tabel Hasil Fitting. Model yang sedang disorot di tabel
        digambar lebih tebal supaya gampang dibedakan dari yang lain."""
        self.plot_calibration.clear()

        points = self._last_fit_points
        results = self._last_fit_results
        if not points or not results:
            return

        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        scatter = pg.ScatterPlotItem(
            x=xs, y=ys, size=10,
            brush=pg.mkBrush("#2c3e50"), pen=pg.mkPen("#ffffff", width=1),
            name="Titik Kalibrasi"
        )
        self.plot_calibration.addItem(scatter)

        # Rentang sumbu-x untuk kurva: sedikit lebih lebar dari titik data
        # supaya terlihat jelas menembus seluruh sebaran titik, bukan cuma
        # nyambung titik-ke-titik.
        x_min, x_max = min(xs), max(xs)
        span = (x_max - x_min) or max(abs(x_max), 1.0)
        x_lo = x_min - span * 0.15
        x_hi = x_max + span * 0.15
        xs_dense = np.linspace(x_lo, x_hi, 200)

        row = self.table_results.currentRow()
        selected_model = None
        if row >= 0:
            item = self.table_results.item(row, 0)
            res = item.data(Qt.UserRole) if item else None
            if res:
                selected_model = res["model"]

        for idx, res in enumerate(results):
            model = res["model"]
            params = res["params"]
            xs_valid, ys_valid = [], []
            for xv in xs_dense:
                # Model logarithmic/power tidak terdefinisi utk x <= 0 --
                # evaluate_calibration_model mengembalikan None, titik itu
                # dilewati saja supaya kurva tidak putus/error.
                yv = evaluate_calibration_model(model, params, float(xv))
                if yv is not None:
                    xs_valid.append(xv)
                    ys_valid.append(yv)
            if not xs_valid:
                continue
            color = GRAPH_COLORS[idx % len(GRAPH_COLORS)]
            is_selected = (model == selected_model)
            pen = pg.mkPen(color, width=3 if is_selected else 1.5)
            label = CALIBRATION_MODEL_LABELS.get(model, model)
            self.plot_calibration.plot(
                xs_valid, ys_valid, pen=pen,
                name=f"{label} (R\u00b2={res['r2']:.4f})"
            )

    def _apply_selected_result(self):
        row = self.table_results.currentRow()
        if row < 0:
            return
        item = self.table_results.item(row, 0)
        if item is None:
            return
        res = item.data(Qt.UserRole)
        if not res:
            return
        self._set_active_model(res["model"], res["params"], res["r2"])

    # -- model aktif --------------------------------------------------
    def _set_active_model(self, model, params, r2=None):
        idx = self.cb_model.findData(model)
        if idx >= 0:
            self.cb_model.setCurrentIndex(idx)
        self.ed_params.setText(", ".join(_format_calibration_number(p) for p in params))
        self._active_r2 = r2
        self.lbl_r2.setText(f"{r2:.5f}" if isinstance(r2, (int, float)) else "--")
        self._update_preview()

    def _parse_active_params(self):
        text = self.ed_params.text().strip()
        if not text:
            return []
        out = []
        for chunk in text.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                out.append(float(chunk))
            except ValueError:
                return None
        return out

    def _update_preview(self):
        model = self.cb_model.currentData()
        params = self._parse_active_params()
        expected = CALIBRATION_MODEL_PARAM_COUNTS.get(model)
        if params is None or expected is None or len(params) != expected:
            self.lbl_preview.setText("(params belum valid)")
            return
        if self._last_raw is None:
            self.lbl_preview.setText("(tidak ada nilai mentah terakhir)")
            return
        result = evaluate_calibration_model(model, params, float(self._last_raw))
        self.lbl_preview.setText("(di luar domain model ini)" if result is None else _format_calibration_number(result))

    def _on_save_clicked(self):
        model = self.cb_model.currentData()
        params = self._parse_active_params()
        expected = CALIBRATION_MODEL_PARAM_COUNTS.get(model)
        if params is None or expected is None or len(params) != expected:
            QMessageBox.warning(
                self, "Peringatan",
                f"Params untuk model \"{CALIBRATION_MODEL_LABELS.get(model, model)}\" harus "
                f"{expected if expected is not None else '?'} angka dipisah koma."
            )
            return
        self.accept()

    def get_calibration(self):
        model = self.cb_model.currentData()
        params = self._parse_active_params() or []
        out = {"model": model, "params": params}
        if isinstance(self._active_r2, (int, float)):
            out["r2"] = self._active_r2
        return out

    def get_calibration_points(self):
        """Titik mentah (raw->ref) yang sedang terisi di tabel "Titik
        Kalibrasi" saat dialog ditutup -- dipakai pemanggil (edit_calibration)
        untuk disimpan ke cache PC & dititipkan ke device lewat
        SET_CALIBRATION, supaya tidak hilang."""
        return self._collect_points()


class ThemeDialog(QDialog):
    """Pengaturan tampilan global aplikasi.

    Preset mengubah palet seluruh GUI; pengguna juga dapat memilih font dan
    beberapa warna utama secara manual tanpa menyentuh konfigurasi device.
    """
    COLOR_FIELDS = [
        ("accent", "Aksen"),
        ("window_bg", "Latar Aplikasi"),
        ("panel_bg", "Panel / Kartu"),
        ("text", "Teks Utama"),
        ("muted_text", "Teks Sekunder"),
        ("input_bg", "Input / Field"),
        ("terminal_bg", "Terminal Latar"),
        ("terminal_text", "Terminal Teks"),
    ]

    def __init__(self, parent=None, current_theme_key=DEFAULT_THEME_KEY, current_ui=None):
        super().__init__(parent)
        current_ui = current_ui if isinstance(current_ui, dict) else {}
        self.setWindowTitle("Pengaturan Tampilan (Tema)")
        self.resize(760, 620)
        self.selected_theme = current_theme_key if (current_theme_key in THEME_PRESETS or current_theme_key == "custom") else DEFAULT_THEME_KEY
        base_theme_key = self.selected_theme if self.selected_theme in THEME_PRESETS else DEFAULT_THEME_KEY
        self.colors = dict(normalize_theme(THEME_PRESETS[base_theme_key]))
        if isinstance(current_ui.get("custom_colors"), dict):
            for k, v in current_ui["custom_colors"].items():
                if k in self.colors and isinstance(v, str):
                    self.colors[k] = v
        self.font_family = str(current_ui.get("font_family") or self.colors.get("font_family", "Segoe UI"))
        try:
            self.font_size = max(9, min(24, int(current_ui.get("font_size", self.colors.get("font_size", 13)))))
        except (TypeError, ValueError):
            self.font_size = 13

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        title = QLabel("Pengaturan Tampilan")
        title.setStyleSheet("font-weight: 700; font-size: 15px;")
        outer.addWidget(title)
        desc = QLabel("Preset mengubah warna aplikasi secara menyeluruh: latar, panel, input, tombol, terminal, tabel, seleksi, dan grafik.")
        desc.setWordWrap(True)
        outer.addWidget(desc)

        body = QHBoxLayout()
        body.setSpacing(12)

        preset_box = QGroupBox("Tema Preset")
        preset_layout = QVBoxLayout(preset_box)
        self.preset_buttons = {}
        for key, theme in THEME_PRESETS.items():
            b = QPushButton(theme["label"])
            b.setMinimumHeight(34)
            b.setCheckable(True)
            b.setChecked(key == self.selected_theme)
            b.clicked.connect(lambda checked, k=key: self._pick_theme(k))
            self.preset_buttons[key] = b
            preset_layout.addWidget(b)
        preset_layout.addStretch()
        body.addWidget(preset_box, 1)

        settings_box = QGroupBox("Kustomisasi")
        form = QFormLayout(settings_box)
        self.color_buttons = {}
        for key, label in self.COLOR_FIELDS:
            b = QPushButton()
            b.setMinimumWidth(170)
            b.clicked.connect(lambda checked=False, k=key: self._pick_color(k))
            self.color_buttons[key] = b
            form.addRow(label + ":", b)

        self.cb_font = QComboBox()
        self.cb_font.setEditable(True)
        fonts = [
            "Segoe UI", "Noto Sans", "Cantarell", "DejaVu Sans", "Liberation Sans",
            "Arial", "Tahoma", "Ubuntu", "Roboto",
        ]
        self.cb_font.addItems(fonts)
        self.cb_font.setCurrentText(self.font_family)
        form.addRow("Font Family:", self.cb_font)

        self.sp_font = ThemedSpinBox()
        self.sp_font.setRange(9, 24)
        self.sp_font.setValue(self.font_size)
        self.sp_font.setSuffix(" pt")
        form.addRow("Ukuran Font:", self.sp_font)
        body.addWidget(settings_box, 2)

        outer.addLayout(body)
        self.lbl_preview = QLabel("Preview: Primary Button · Success · Danger · Input")
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setMinimumHeight(44)
        outer.addWidget(self.lbl_preview)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._refresh_colors()

    def _pick_theme(self, key):
        if key not in THEME_PRESETS:
            return
        self.selected_theme = key
        self.colors = dict(normalize_theme(THEME_PRESETS[key]))
        self._refresh_colors()
        for k, b in self.preset_buttons.items():
            b.setChecked(k == key)

    def _pick_color(self, key):
        current = QColor(str(self.colors.get(key, "#ffffff")))
        chosen = QColorDialog.getColor(current, self, f"Pilih warna — {key}")
        if chosen.isValid():
            self.colors[key] = chosen.name()
            self.selected_theme = "custom"
            for b in self.preset_buttons.values():
                b.setChecked(False)
            self._refresh_colors()

    def _refresh_colors(self):
        for key, button in self.color_buttons.items():
            color = str(self.colors.get(key, "#ffffff"))
            button.setText(color)
            button.setStyleSheet(
                f"QPushButton {{ background: {color}; color: {'#000000' if QColor(color).lightness() > 160 else '#ffffff'}; "
                "border: 1px solid #777; border-radius: 4px; padding: 5px 10px; }"
            )
        self.lbl_preview.setStyleSheet(
            f"QLabel {{ background: {self.colors.get('panel_bg', '#ffffff')}; color: {self.colors.get('text', '#1a1a1a')}; "
            f"border: 1px solid {self.colors.get('border', '#b7b7b7')}; border-radius: 4px; padding: 8px; }}"
        )

    def get_settings(self):
        font_family = self.cb_font.currentText().strip() or "Segoe UI"
        return {
            "theme": self.selected_theme if self.selected_theme in THEME_PRESETS else "custom",
            "font_family": font_family,
            "font_size": self.sp_font.value(),
            "custom_colors": {k: self.colors[k] for k, _ in self.COLOR_FIELDS},
        }


# ---------------------------------------------------------------------------
# Ukuran jendela adaptif terhadap resolusi layar
# ---------------------------------------------------------------------------
# Desain window awalnya di-hardcode 1250x850 px logis. Itu sudah otomatis
# ikut di-scale oleh Qt di layar HiDPI (lihat AA_EnableHighDpiScaling di
# atas), TAPI di layar besar yang scaling OS-nya diset 100% (umum di
# beberapa setup Linux/monitor 4K "raw"), 1250x850 akan tampak sangat kecil
# di tengah layar 3840x2160. Fungsi ini menghitung ukuran awal jendela
# proporsional terhadap luas layar yang tersedia (bukan fixed), sekaligus
# tetap menghormati batas minimum yang wajar untuk layar kecil (laptop
# 1366x768 dst.).
REFERENCE_SCREEN_W = 1920
REFERENCE_SCREEN_H = 1080
BASE_WINDOW_W = 1250
BASE_WINDOW_H = 850
BASE_MIN_W = 1000
BASE_MIN_H = 700


def _available_screen_geometry():
    """Ambil area layar yang tersedia (di luar taskbar dsb). Screen tempat
    kursor mouse berada dipakai bila tersedia (multi-monitor), fallback ke
    primary screen."""
    app = QApplication.instance()
    if app is None:
        return None
    screen = None
    try:
        from PyQt5.QtGui import QCursor
        screen = app.screenAt(QCursor.pos())
    except Exception:
        screen = None
    if screen is None:
        screen = app.primaryScreen()
    return screen.availableGeometry() if screen else None


def compute_adaptive_window_geometry():
    """Hitung (width, height, min_width, min_height) jendela utama, mengikuti
    resolusi layar aktif -- mendukung dari layar kecil (1366x768) sampai
    2K/4K (2560x1440, 3840x2160) dan seterusnya."""
    avail = _available_screen_geometry()
    if avail is None or avail.width() <= 0 or avail.height() <= 0:
        return BASE_WINDOW_W, BASE_WINDOW_H, BASE_MIN_W, BASE_MIN_H

    scale = min(avail.width() / REFERENCE_SCREEN_W, avail.height() / REFERENCE_SCREEN_H)
    # Batasi skala supaya di layar sangat kecil jendela tak jadi terlalu
    # sempit, dan di layar sangat besar (mis. 4K/5K) jendela tak jadi
    # janggal memenuhi hampir seluruh layar.
    scale = max(0.72, min(scale, 2.4))

    width = int(BASE_WINDOW_W * scale)
    height = int(BASE_WINDOW_H * scale)

    # Jangan sampai melebihi area layar yang tersedia (sisakan margin kecil).
    width = min(width, avail.width() - 40)
    height = min(height, avail.height() - 60)

    min_width = min(BASE_MIN_W, avail.width() - 40)
    min_height = min(BASE_MIN_H, avail.height() - 60)

    width = max(width, min_width)
    height = max(height, min_height)

    return width, height, min_width, min_height


class LoggerDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.setWindowTitle("Sistem Kontrol & Telemetri Logger ESP32 (UI V2)")

        win_w, win_h, min_w, min_h = compute_adaptive_window_geometry()
        self.setMinimumSize(min_w, min_h)
        self.resize(win_w, win_h)
        self._center_on_screen()

        # Terapkan tema tampilan yang tersimpan. Preferensi ini hanya untuk GUI PC.
        self._apply_theme(persist=False)

        self.worker = None
        # SN device yang profil kalibrasinya sedang aktif di
        # self.config["calibration"]/["calibration_points"], dan flag
        # supaya GET_IDENTITY otomatis cuma dikirim SEKALI per sesi koneksi
        # (dipicu begitu ada baris data pertama masuk -- lihat
        # handle_incoming_data -- bukan langsung saat klik Connect, supaya
        # tidak terkirim saat device masih boot/reset). Diisi dari
        # device_identity yang tersimpan di config.json sesi sebelumnya
        # dulu (asumsi awal: "calibration" aktif saat ini masih milik SN
        # itu) -- akan otomatis dikoreksi begitu GET_IDENTITY sesi baru
        # menjawab dengan SN yang beda.
        self._active_device_sn = str(
            self.config.get("device_identity", {}).get("sn") or ""
        ).strip() or None
        self._identity_requested_this_session = False
        self.is_recording = False
        self.csv_file = None
        self.csv_fh = None
        self.csv_writer = None
        self.csv_widget_keys = []
        self.csv_widget_labels = []
        self.csv_timestamp_header = "Timestamp PC"
        self.csv_interval_sec = 1.0
        self._last_csv_write_ts = 0.0

        self.hb_count = 0
        self.last_hb_time = None
        self.start_time = time.time()

        # State navigasi folder SD Card. "" berarti root (mount point SD).
        # Path relatif ini yang dikirim ke firmware lewat parameter "path"
        # di LIST_LOGS, dan digabung dengan nama file saat GET_FILE/DELETE_FILE
        # supaya file di dalam subfolder tetap bisa diakses.
        self.sd_current_path = ""

        self.payload_registry = {}
        self.latest_payload = {}
        self.history = {}
        self.pending_commands = {}
        self.command_seq = 0

        # Menyimpan progress download file yang sedang berjalan (protokol
        # ber-chunk: FILE_START -> beberapa FILE_CHUNK -> FILE_END), key-nya
        # adalah command id supaya tidak tertukar kalau ada beberapa
        # permintaan GET_FILE yang id-nya berbeda.
        self.file_downloads = {}

        # Menampung item hasil scan WiFi yang datang satu-per-satu
        # (SCAN_START -> beberapa SCAN_ITEM -> SCAN_END), key-nya command id.
        self.wifi_scans = {}

        self.sensor_labels = {}
        self.sensor_curves = {}
        self.sensor_x = {}
        self.sensor_y = {}

        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self._setup_top_bar()

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 12, 14, 14)
        body_layout.addWidget(self.tabs)
        self.main_layout.addWidget(body)

        self.tab_dashboard = QWidget()
        self.tab_network = QWidget()
        self.tab_sdcard = QWidget()
        self.tab_control = QWidget()
        self.tab_terminal = QWidget()
        self.tab_custom = QWidget()
        self.tab_udaraku = QWidget()
        self.tab_calibration = QWidget()

        self.tabs.addTab(self.tab_dashboard, "📊  Dashboard && Grafik")
        self.tabs.addTab(self.tab_network, "📶  Network && RTC")
        self.tabs.addTab(self.tab_sdcard, "💾  SD Card")
        self.tabs.addTab(self.tab_control, "🎚️  Kontrol && Threshold")
        self.tabs.addTab(self.tab_terminal, "🖥️  Terminal Log")
        self.tabs.addTab(self.tab_custom, "🎨  Dashboard Designer")
        self.tabs.addTab(self.tab_udaraku, "☁️  Kirim ke Udaraku")
        self.tabs.addTab(self.tab_calibration, "🛠️  Kalibrasi && Identitas")

        self.setup_tab_dashboard()
        self.setup_tab_network()
        self.setup_tab_sdcard()
        self.setup_tab_control()
        self.setup_tab_terminal()
        self.setup_tab_custom()
        self.setup_tab_udaraku()
        self.setup_tab_calibration()

        # _rebuild_sensor_cards() dipanggil sebelum _load_udaraku_controls_
        # from_config() dengan sengaja: yang pertama membangun checkbox
        # kanal dari sensor_config (lihat _refresh_udaraku_kanal_checkboxes,
        # dipanggil dari dalamnya), yang kedua baru menandai kanal mana yang
        # tercentang sesuai config tersimpan. Urutan terbalik akan membuat
        # tanda centang yang sudah dimuat langsung hilang lagi.
        self._rebuild_sensor_cards()
        self._rebuild_sensor_curves()
        self.refresh_payload_registry_ui()
        self.refresh_threshold_table()
        self._load_logging_controls_from_config()
        self._load_udaraku_controls_from_config()
        self._update_calibration_table()
        self._load_identity_display_from_config()
        self._update_active_profile_label()

        # Terapkan ulang setelah seluruh widget dibuat agar elemen seperti
        # pyqtgraph dan custom spinbox juga menerima warna/font tema yang aktif.
        self._apply_theme(persist=False)

        self.timer_pc_time = QTimer()
        self.timer_pc_time.timeout.connect(self.update_pc_clock)
        self.timer_pc_time.start(1000)

        self.timer_pending = QTimer()
        self.timer_pending.timeout.connect(self.check_pending_commands)
        self.timer_pending.start(250)

    @property
    def sensor_config(self):
        return self.config.setdefault("dashboard", {}).setdefault("widgets", [])

    @property
    def thresholds(self):
        return self.config.setdefault("thresholds", [])

    def persist_config(self):
        save_config(self.config)

    def _normalize_threshold_record(self, threshold):
        """
        Samakan nama field threshold end-to-end:
        id, payload, operator, value, buzzer, interval_sec, enabled.
        """
        if not isinstance(threshold, dict):
            return {}
        out = dict(threshold)
        payload = str(out.get("payload", "")).strip()
        if not payload:
            return {}
        payload = LEGACY_PAYLOAD_ALIASES.get(payload, payload)
        out["payload"] = payload
        out["operator"] = str(out.get("operator", ">"))
        try:
            out["value"] = float(out.get("value", 0))
        except (TypeError, ValueError):
            out["value"] = 0.0
        try:
            out["buzzer"] = int(out.get("buzzer", 1))
        except (TypeError, ValueError):
            out["buzzer"] = 1
        try:
            out["interval_sec"] = int(out.get("interval_sec", 300))
        except (TypeError, ValueError):
            out["interval_sec"] = 300
        if out["interval_sec"] < 1:
            out["interval_sec"] = 1
        out["enabled"] = bool(out.get("enabled", True))
        if "id" in out:
            try:
                out["id"] = int(out["id"])
            except (TypeError, ValueError):
                pass
        return out

    def log_terminal(self, tag, message, color="#2c3e50"):
        """Fungsi pembantu untuk menulis log ke terminal secara rapi.

        PERBAIKAN BUG: `message` (dan `tag`) sebelumnya disisipkan MENTAH ke
        string HTML. Kalau isinya mengandung karakter '<', '>', atau '&'
        (mis. payload threshold berisi operator "<" atau "<="), Qt membaca
        karakter itu sebagai awal tag HTML, bukan teks biasa -- sisa baris
        jadi "hilang" dari tampilan meski data asli yang terkirim ke serial
        tetap utuh. Sekarang di-escape lewat html.escape() dulu supaya '<',
        '>', '&' selalu tampil apa adanya sebagai teks.
        """
        timestamp = time.strftime("%H:%M:%S")
        safe_tag = html.escape(str(tag))
        safe_message = html.escape(str(message))
        line = (
            f'<span style="color:#7f8c8d; font-size:11px;">[{timestamp}]</span> '
            f'<strong style="color:{color}; font-size:11px">[{safe_tag}]</strong> '
            f'<span style="font-size:11px">{safe_message}</span>'
        )
        self.txt_log.append(line)

    def _setup_top_bar(self):
        """Bar permanen di atas tab (bukan di dalam tab manapun) -- judul
        aplikasi + kontrol koneksi serial (port, connect, badge status).
        Sebelumnya kontrol ini terkubur di dalam groupbox tab 1 saja,
        sehingga operator harus pindah ke tab Dashboard dulu untuk sekadar
        connect/disconnect. Widget (`cb_ports`, `btn_connect`,
        `lbl_conn_status`) TETAP dibuat dengan nama atribut yang sama --
        semua logic yang mereferensikannya di tempat lain tidak berubah."""
        bar = QFrame()
        bar.setObjectName("topBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(20, 12, 20, 12)
        h.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        lbl_title = QLabel("AiMS Kontrol")
        lbl_title.setObjectName("appTitle")
        lbl_subtitle = QLabel("Logger Sensor SHT31 — ESP32-S3")
        lbl_subtitle.setObjectName("appSubtitle")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_subtitle)
        h.addLayout(title_box)

        h.addSpacing(28)
        h.addWidget(QLabel("Port:"))

        self.cb_ports = QComboBox()
        self.cb_ports.setMinimumWidth(170)
        h.addWidget(self.cb_ports)

        btn_ref = QPushButton("⟳")
        btn_ref.setToolTip("Refresh daftar port serial")
        # Tidak ada lagi override lebar khusus -- dengan padding QPushButton
        # yang sekarang seragam (6px 16px) di semua tombol, tombol ikon ini
        # otomatis proporsional dengan tombol "Connect" di sebelahnya, tanpa
        # risiko ikon kepotong seperti versi fixed-width sebelumnya.
        btn_ref.clicked.connect(self.refresh_ports)
        h.addWidget(btn_ref)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setObjectName("btnPrimary")
        self.btn_connect.clicked.connect(self.toggle_connection)
        h.addWidget(self.btn_connect)

        h.addStretch()

        # Tombol Pengaturan Tampilan -- sengaja ditaruh di top bar (bukan
        # di salah satu tab pengaturan alat), karena ini murni preferensi
        # GUI/PC, tidak berhubungan dengan konfigurasi device.
        btn_theme = QPushButton("🎨")
        btn_theme.setToolTip("Pengaturan Tampilan (tema warna aplikasi)")
        btn_theme.clicked.connect(self.open_theme_dialog)
        h.addWidget(btn_theme)

        self.lbl_conn_status = QLabel("Disconnected")
        self.lbl_conn_status.setObjectName("statusBadgeDisconnected")
        self.lbl_conn_status.setAlignment(Qt.AlignCenter)
        h.addWidget(self.lbl_conn_status)

        self.main_layout.addWidget(bar)
        self.refresh_ports()

    def _new_tab_layout(self, tab_widget):
        """Layout dasar tiap tab: dibungkus QScrollArea supaya kalau jendela
        di-resize kecil (atau tab isinya padat, mis. "Kirim ke Server"),
        konten SCROLL alih-alih terpotong atau numpuk vertikal. Margin &
        spacing sengaja sedang (bukan besar) sesuai masukan -- cukup
        untuk "napas" tanpa terasa boros ruang. Nama widget yang dipasang
        lewat layout ini tidak berubah sama sekali, jadi semua logic tetap
        utuh."""
        outer = QVBoxLayout(tab_widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(14)

        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return layout

    def _new_splitter_tab_layout(self, tab_widget):
        """Alternatif _new_tab_layout() untuk tab yang isinya beberapa
        panel "berat" (tabel besar dsb) yang saling berebut ruang vertikal
        di layar kecil (mis. laptop 1360x768). Bedanya dengan
        _new_tab_layout(): konten TIDAK dibungkus QScrollArea, melainkan
        QSplitter(Qt.Vertical) yang memenuhi seluruh tinggi tab -- jadi
        setiap panel benar-benar dapat jatah ruang vertikal (bukan cuma
        sizeHint alami), DAN user bisa menarik manual garis pembatas antar
        panel (splitter handle) untuk memperbesar salah satu panel (mis.
        tabel daftar file SD Card) dengan mengecilkan panel lain.

        Return QSplitter kosong -- panggil self._add_splitter_pane() untuk
        menambah tiap panel (kembaliannya QVBoxLayout, dipakai persis
        seperti layout dari _new_tab_layout())."""
        outer = QVBoxLayout(tab_widget)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        splitter = QSplitter(Qt.Vertical)
        # False supaya panel tidak bisa "ditarik sampai hilang total" ke
        # tinggi 0 -- selalu ada minimumSizeHint layout di dalamnya yang
        # dihormati, jadi user tetap bisa menarik balik.
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        outer.addWidget(splitter, stretch=1)
        return splitter

    def _add_splitter_pane(self, splitter, stretch=1):
        """Tambah satu panel baru ke splitter dari _new_splitter_tab_layout().
        `stretch` menentukan proporsi ruang awal panel ini relatif ke
        panel lain (dipakai lewat setStretchFactor setelah semua panel
        ditambahkan oleh pemanggil) -- besaran pastinya tetap bisa ditarik
        manual oleh user lewat splitter handle kapan saja setelah itu."""
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        splitter.addWidget(pane)
        splitter.setStretchFactor(splitter.count() - 1, stretch)
        return layout

    def _make_expanding_table(self, min_height=160):
        """QTableWidget dengan size policy Expanding (bukan default
        Preferred) supaya benar-benar memakai ruang tambahan yang
        dialokasikan panel splitter/layout di sekitarnya, plus tinggi
        minimum yang wajar supaya tetap menampilkan beberapa baris di
        layar kecil (1360x768 dst.) tanpa perlu di-scroll dulu."""
        table = QTableWidget()
        table.setMinimumHeight(min_height)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return table

    def setup_tab_dashboard(self):
        layout = self._new_tab_layout(self.tab_dashboard)

        self.group_status = QGroupBox("Status & Payload Real-time")
        self.grid_status = QGridLayout(self.group_status)
        layout.addWidget(self.group_status)

        self.group_plot = QGroupBox("Grafik Sensor Real-Time")
        vplot = QVBoxLayout(self.group_plot)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground(self.config.get("ui", {}).get("theme", "light_blue") in THEME_PRESETS and THEME_PRESETS[self.config.get("ui", {}).get("theme", "light_blue")]["plot_bg"] or DEFAULT_THEME["plot_bg"])
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setLabel("left", "Nilai Parameter")
        self.plot_widget.setLabel("bottom", "Waktu (detik sejak mulai)")
        vplot.addWidget(self.plot_widget)
        layout.addWidget(self.group_plot, stretch=1)

        hrec = QHBoxLayout()
        hrec.addWidget(QLabel("Interval Simpan (detik):"))
        self.sp_csv_interval = ThemedDoubleSpinBox()
        self.sp_csv_interval.setRange(0.1, 3600.0)
        self.sp_csv_interval.setSingleStep(0.5)
        self.sp_csv_interval.setValue(1.0)
        self.sp_csv_interval.setToolTip(
            "Jarak waktu minimum antar baris yang ditulis ke CSV. "
            "Telemetri tetap masuk tiap detik dari firmware, tapi baris CSV "
            "baru ditulis kalau sudah melewati interval ini."
        )
        hrec.addWidget(self.sp_csv_interval)
        self.btn_record = QPushButton("Start Record CSV")
        self.btn_record.setObjectName("btnSuccess")
        self.btn_record.clicked.connect(self.toggle_record_csv)
        hrec.addStretch()
        hrec.addWidget(self.btn_record)
        layout.addLayout(hrec)

    def _make_card(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("statusCard")
        lbl.setAlignment(Qt.AlignCenter)
        return lbl

    def _rebuild_sensor_cards(self):
        while self.grid_status.count():
            item = self.grid_status.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.sensor_labels.clear()
        cards = []

        for cfg in self.sensor_config:
            key = cfg.get("key")
            if not key:
                continue
            label = cfg.get("label", key)
            unit = cfg.get("unit", "")
            text = f"{label}\n-- {unit}".strip()
            card = self._make_card(text)
            self.sensor_labels[key] = card
            cards.append(card)

        self.lbl_mode = self._make_card("Mode Daya\n--")
        self.lbl_wifi = self._make_card("WiFi\n--")
        self.lbl_ip = self._make_card("Alamat IP\n--")
        self.lbl_sd_stat = self._make_card("SD Card\n--")
        self.lbl_heartbeat = self._make_card("Heartbeat\n#0")
        self.lbl_ack = self._make_card("ACK\n--")

        cards.extend([
            self.lbl_mode, self.lbl_wifi, self.lbl_ip,
            self.lbl_sd_stat, self.lbl_heartbeat, self.lbl_ack
        ])

        for i, card in enumerate(cards):
            self.grid_status.addWidget(card, i // 4, i % 4)

        # Checkbox kanal udaraku mengikuti sensor_config -- dibangun ulang
        # di sini supaya menambah/menghapus/mengedit widget dashboard di tab
        # Dashboard Designer otomatis tercermin di daftar kanal yang bisa
        # dipilih, tanpa daftar statis terpisah yang gampang basi.
        self._refresh_udaraku_kanal_checkboxes()

    def _rebuild_sensor_curves(self):
        self.sensor_curves.clear()
        self.sensor_x.clear()
        self.sensor_y.clear()

        self.plot_widget.clear()
        self.plot_widget.addLegend()

        for idx, cfg in enumerate(self.sensor_config):
            key = cfg.get("key")
            if not key or not cfg.get("show_graph", True):
                continue
            self.sensor_x[key] = deque(maxlen=MAX_POINTS)
            self.sensor_y[key] = deque(maxlen=MAX_POINTS)
            pen = pg.mkPen(GRAPH_COLORS[idx % len(GRAPH_COLORS)], width=2)
            curve = self.plot_widget.plot(
                pen=pen,
                name=f"{cfg.get('label', key)} ({cfg.get('unit', '')})"
            )
            self.sensor_curves[key] = curve

    def setup_tab_network(self):
        layout = self._new_tab_layout(self.tab_network)

        grp_wifi = QGroupBox("Manajemen Wi-Fi")
        v = QVBoxLayout(grp_wifi)

        h = QHBoxLayout()
        btn_scan = QPushButton("Scan Wi-Fi")
        btn_scan.setObjectName("btnPrimary")
        btn_scan.clicked.connect(
            lambda: self.send_json_command({"cmd": "WIFI_SCAN"}, ui_button=btn_scan)
        )

        self.btn_disconnect = QPushButton("Disconnect Wi-Fi")
        self.btn_disconnect.setObjectName("btnDanger")
        self.btn_disconnect.clicked.connect(self.disconnect_wifi_action)

        h.addWidget(btn_scan)
        h.addWidget(self.btn_disconnect)
        h.addStretch()
        v.addLayout(h)

        h = QHBoxLayout()
        self.txt_ssid = QLineEdit()
        self.txt_ssid.setPlaceholderText("SSID Wi-Fi")

        self.txt_pass = QLineEdit()
        self.txt_pass.setPlaceholderText("Password")
        self.txt_pass.setEchoMode(QLineEdit.Password)

        self.btn_connect_wifi = QPushButton("Connect Wi-Fi")
        self.btn_connect_wifi.setObjectName("btnPrimary")
        self.btn_connect_wifi.clicked.connect(self.connect_wifi_action)

        h.addWidget(self.txt_ssid)
        h.addWidget(self.txt_pass)
        h.addWidget(self.btn_connect_wifi)
        v.addLayout(h)

        self.table_wifi_scan = QTableWidget()
        self.table_wifi_scan.setColumnCount(3)
        self.table_wifi_scan.setHorizontalHeaderLabels(["SSID", "RSSI", "Aksi"])
        self.table_wifi_scan.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_wifi_scan.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_wifi_scan.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_wifi_scan.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_wifi_scan.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_wifi_scan.setMinimumHeight(160)
        
        v.addWidget(QLabel("Hasil Scan Wi-Fi"))
        v.addWidget(self.table_wifi_scan)

        layout.addWidget(grp_wifi)

        grp_time = QGroupBox("Sinkronisasi Waktu & RTC")
        v = QVBoxLayout(grp_time)
        self.lbl_time_pc = QLabel("Waktu PC: --")
        self.lbl_time_rtc = QLabel("Waktu RTC Perangkat: --")
        v.addWidget(self.lbl_time_pc)
        v.addWidget(self.lbl_time_rtc)

        h = QHBoxLayout()
        b1 = QPushButton("Sinkron RTC dengan Jam PC (Unix TS)")
        b1.clicked.connect(self.sync_rtc_pc_action)
        h.addWidget(b1)
        h.addStretch()
        v.addLayout(h)

        layout.addWidget(grp_time)

        # Config Device tersimpan di flash ESP32. Sesuai keputusan desain:
        # satu file config gabungan di firmware (WiFi SSID terakhir + mode +
        # daftar threshold), dipakai untuk auto-reconnect WiFi saat boot
        # tanpa perlu GUI terhubung. GET_CONFIG / SET_CONFIG sudah
        # diimplementasikan penuh di firmware (lihat main.py) -- panel ini
        # bukan lagi scaffolding.
        grp_config = QGroupBox("Konfigurasi Tersimpan di Device (Flash) — Auto-Reconnect")
        v_cfg = QVBoxLayout(grp_config)

        self.lbl_device_config = QLabel(
            "Belum diambil dari device. Klik 'Muat Config dari Device' untuk cek "
            "apa yang tersimpan di flash ESP32 (dipakai untuk auto-reconnect saat boot)."
        )
        self.lbl_device_config.setObjectName("statusCard")
        self.lbl_device_config.setWordWrap(True)
        v_cfg.addWidget(self.lbl_device_config)

        h_cfg = QHBoxLayout()
        btn_get_cfg = QPushButton("Muat Config dari Device")
        btn_get_cfg.clicked.connect(
            lambda: self.send_json_command({"cmd": "GET_CONFIG"}, ui_button=btn_get_cfg)
        )
        btn_set_cfg = QPushButton("Simpan Config ke Device (Flash)")
        btn_set_cfg.setObjectName("btnPrimary")
        btn_set_cfg.clicked.connect(
            lambda: self.push_device_config(ui_button=btn_set_cfg)
        )
        h_cfg.addWidget(btn_get_cfg)
        h_cfg.addWidget(btn_set_cfg)
        h_cfg.addStretch()
        v_cfg.addLayout(h_cfg)

        layout.addWidget(grp_config)
        layout.addStretch()

    def setup_tab_sdcard(self):
        """Tab SD Card dipecah jadi 2 panel lewat QSplitter vertikal
        (_new_splitter_tab_layout) supaya di layar kecil (1360x768 dst.)
        panel "Browse SD Card" -- yang paling sering perlu dilihat banyak
        baris sekaligus -- bisa DITARIK MANUAL oleh user lebih besar
        dengan mengecilkan panel Konfigurasi Logger di atasnya, alih-alih
        cuma menampilkan beberapa baris lalu terpotong/perlu scroll
        halaman penuh."""
        splitter = self._new_splitter_tab_layout(self.tab_sdcard)

        self.lbl_sd_detail = QLabel("Status SD Card: --")
        self.lbl_sd_detail.setObjectName("statusCard")

        # --- Panel 1: Konfigurasi Logger (Data & System) ---------------
        pane_config = self._add_splitter_pane(splitter, stretch=0)
        pane_config.addWidget(self.lbl_sd_detail)

        # Konfigurasi Data Logger & System Logger (disimpan ke flash ESP32
        # lewat command SET_LOGGING_CONFIG, terpisah dari config WiFi/mode/
        # threshold supaya tidak saling menimpa).
        grp_logging = QGroupBox("Konfigurasi Logger (Data & System)")
        v_log = QVBoxLayout(grp_logging)

        form_data = QFormLayout()
        self.chk_data_enabled = QCheckBox("Aktif")
        self.chk_data_enabled.setChecked(True)
        self.sp_data_interval = ThemedSpinBox()
        self.sp_data_interval.setRange(1, 86400)
        self.sp_data_interval.setValue(60)
        self.sp_data_interval.setSuffix(" detik")
        self.sp_data_retention = ThemedSpinBox()
        self.sp_data_retention.setRange(1, 365)
        self.sp_data_retention.setValue(7)
        self.sp_data_retention.setSuffix(" hari")
        form_data.addRow("Data Logger:", self.chk_data_enabled)
        form_data.addRow("Interval:", self.sp_data_interval)
        form_data.addRow("Retention:", self.sp_data_retention)
        v_log.addLayout(form_data)

        form_sys = QFormLayout()
        self.chk_system_enabled = QCheckBox("Aktif")
        self.chk_system_enabled.setChecked(True)
        self.sp_system_retention = ThemedSpinBox()
        self.sp_system_retention.setRange(1, 365)
        self.sp_system_retention.setValue(30)
        self.sp_system_retention.setSuffix(" hari")
        form_sys.addRow("System Logger:", self.chk_system_enabled)
        form_sys.addRow("Retention:", self.sp_system_retention)
        v_log.addLayout(form_sys)

        h_log = QHBoxLayout()
        btn_get_logging = QPushButton("Muat Konfigurasi Logger dari Device")
        btn_get_logging.clicked.connect(
            lambda: self.send_json_command({"cmd": "GET_CONFIG"}, ui_button=btn_get_logging)
        )
        btn_sync_logging = QPushButton("Sync Configuration")
        btn_sync_logging.setObjectName("btnPrimary")
        btn_sync_logging.clicked.connect(
            lambda: self.sync_logging_config(ui_button=btn_sync_logging)
        )
        h_log.addWidget(btn_get_logging)
        h_log.addWidget(btn_sync_logging)
        h_log.addStretch()
        v_log.addLayout(h_log)

        pane_config.addWidget(grp_logging)
        pane_config.addStretch()

        # --- Panel 2: Browse SD Card (navigasi + tabel file + progress) ---
        pane_browse = self._add_splitter_pane(splitter, stretch=1)

        # Navigasi folder: breadcrumb menunjukkan path saat ini + tombol
        # untuk naik ke folder induk. Path disimpan di self.sd_current_path
        # dan dikirim ke firmware sebagai parameter "path" di LIST_LOGS
        # (implementasi firmware-nya menyusul di sesi berikutnya).
        h_nav = QHBoxLayout()
        self.btn_sd_up = QPushButton("⬆ Kembali")
        self.btn_sd_up.setEnabled(False)
        self.btn_sd_up.clicked.connect(self.go_sd_parent)
        self.lbl_sd_breadcrumb = QLabel("📁 /")
        self.lbl_sd_breadcrumb.setObjectName("statusCard")
        h_nav.addWidget(self.btn_sd_up)
        h_nav.addWidget(self.lbl_sd_breadcrumb, stretch=1)
        pane_browse.addLayout(h_nav)

        h = QHBoxLayout()
        btn = QPushButton("Refresh Daftar File Log")
        btn.setObjectName("btnPrimary")
        btn.clicked.connect(lambda: self.refresh_sd_listing(ui_button=btn))
        h.addWidget(btn)
        h.addStretch()
        pane_browse.addLayout(h)

        self.table_files = self._make_expanding_table(min_height=180)
        self.table_files.setColumnCount(3)
        self.table_files.setHorizontalHeaderLabels(["Nama File", "Ukuran", "Aksi"])
        self.table_files.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_files.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table_files.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table_files.setColumnWidth(1, 90)
        self.table_files.setColumnWidth(2, 190)
        self.table_files.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_files.setSelectionBehavior(QTableWidget.SelectRows)
        # Double-click pada baris folder langsung masuk ke folder itu,
        # sama seperti klik tombol "Buka" di kolom Aksi.
        self.table_files.cellDoubleClicked.connect(self._on_sd_row_double_clicked)
        pane_browse.addWidget(self.table_files, stretch=1)

        # Progress download: sebelumnya progress cuma muncul sebagai teks kecil
        # di kartu ACK umum di atas. Sekarang ditambahkan progress bar +
        # label khusus di tab SD Card ini, supaya ukuran file & progress
        # transfer terlihat jelas tanpa harus melihat tab lain.
        grp_progress = QGroupBox("Progress Download")
        vp = QVBoxLayout(grp_progress)
        self.lbl_sd_progress = QLabel("Belum ada download berjalan.")
        self.progress_sd_download = QProgressBar()
        self.progress_sd_download.setRange(0, 100)
        self.progress_sd_download.setValue(0)
        self.progress_sd_download.setTextVisible(True)
        vp.addWidget(self.lbl_sd_progress)
        vp.addWidget(self.progress_sd_download)
        pane_browse.addWidget(grp_progress)

        # Ukuran awal panel: kasih "Browse SD Card" porsi lebih besar
        # daripada "Konfigurasi Logger" sejak awal dibuka -- user tetap
        # bebas menarik ulang garis pembatasnya kapan saja lewat handle
        # splitter di antara kedua panel ini.
        splitter.setSizes([260, 520])

    def setup_tab_control(self):
        layout = self._new_tab_layout(self.tab_control)

        grp_thresh = QGroupBox("Daftar Threshold yang Diterapkan ke Perangkat")
        v = QVBoxLayout(grp_thresh)

        self.table_threshold = self._make_expanding_table(min_height=150)
        self.table_threshold.setColumnCount(8)
        self.table_threshold.setHorizontalHeaderLabels([
            "ID", "Payload", "Operator", "Nilai", "Buzzer", "Interval", "Enabled", "Aksi"
        ])
        self.table_threshold.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_threshold.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_threshold.setEditTriggers(QTableWidget.NoEditTriggers)
        v.addWidget(self.table_threshold, stretch=1)

        h = QHBoxLayout()
        self.btn_add_threshold = QPushButton("Tambah Threshold")
        self.btn_add_threshold.setObjectName("btnPrimary")
        self.btn_add_threshold.clicked.connect(self.add_threshold)

        self.btn_edit_threshold = QPushButton("Edit")
        self.btn_edit_threshold.clicked.connect(self.edit_threshold)

        self.btn_delete_threshold = QPushButton("Delete")
        self.btn_delete_threshold.setObjectName("btnDanger")
        self.btn_delete_threshold.clicked.connect(self.delete_threshold)

        self.btn_sync_threshold = QPushButton("Kirim Semua Threshold ke ESP32")
        self.btn_sync_threshold.setObjectName("btnSuccess")
        self.btn_sync_threshold.clicked.connect(self.sync_all_thresholds)

        for b in [self.btn_add_threshold, self.btn_edit_threshold, self.btn_delete_threshold, self.btn_sync_threshold]:
            h.addWidget(b)
        h.addStretch()
        v.addLayout(h)
        layout.addWidget(grp_thresh, stretch=1)

        grp_buzzer = QGroupBox("Uji Coba Buzzer ESP32")
        vb = QHBoxLayout(grp_buzzer)
        self.cb_buzzer_test = QComboBox()
        for i in range(1, BUZZER_PATTERN_COUNT + 1):
            self.cb_buzzer_test.addItem(f"Pattern {i}", i)
        btn_test = QPushButton("Test Buzzer")
        btn_test.setObjectName("btnPrimary")
        btn_test.clicked.connect(self.test_buzzer)
        vb.addWidget(QLabel("Pilih suara:"))
        vb.addWidget(self.cb_buzzer_test)
        vb.addWidget(btn_test)
        vb.addStretch()
        layout.addWidget(grp_buzzer)

        grp_sys = QGroupBox("Manajemen Sistem & Daya")
        v = QVBoxLayout(grp_sys)
        self.lbl_current_mode = self._make_card("Mode Saat Ini: --")
        v.addWidget(self.lbl_current_mode)

        h = QHBoxLayout()
        b1 = QPushButton("Set Always On")
        b1.clicked.connect(self.set_always_on_mode)

        b2 = QPushButton("Set Deep Sleep")
        b2.clicked.connect(self.set_deep_sleep_mode)

        h.addWidget(b1)
        h.addWidget(b2)
        h.addStretch()
        v.addLayout(h)

        hsleep = QHBoxLayout()
        hsleep.addWidget(QLabel("Durasi Deep Sleep:"))

        self.sp_deep_sleep = ThemedSpinBox()
        self.sp_deep_sleep.setRange(1, 86400)
        self.sp_deep_sleep.setSuffix(" detik")
        self.sp_deep_sleep.setValue(
            int(self.config.get("device", {}).get("deep_sleep_sec", 60))
        )
        self.sp_deep_sleep.valueChanged.connect(self.save_deep_sleep_setting)

        hsleep.addWidget(self.sp_deep_sleep)
        hsleep.addStretch()
        v.addLayout(hsleep)

        breset = QPushButton("System Soft-Reset / Reboot")
        breset.setObjectName("btnDanger")
        breset.clicked.connect(self.reset_device_action)
        v.addWidget(breset)
        layout.addWidget(grp_sys)

        # Timer refresh e-paper (SSD1680) -- terpisah dari interval
        # logging SD supaya operator bisa mengatur seberapa sering layar
        # digambar ulang (partial) dan seberapa sering full-refresh
        # dipaksa (bersihkan ghosting) tanpa memengaruhi konfigurasi lain.
        # Font panel tetap font6x8 (tidak lagi bisa dipilih dari GUI).
        grp_display = QGroupBox("Timer Refresh E-Paper Display")
        v_disp = QVBoxLayout(grp_display)

        form_disp = QFormLayout()
        self.sp_display_interval = ThemedSpinBox()
        self.sp_display_interval.setRange(5, 3600)
        self.sp_display_interval.setSuffix(" detik")
        self.sp_display_interval.setValue(
            int(self.config.get("display", {}).get("update_interval_sec", 60))
        )
        self.sp_display_full_refresh = ThemedSpinBox()
        self.sp_display_full_refresh.setRange(1, 1440)
        self.sp_display_full_refresh.setSuffix(" menit")
        self.sp_display_full_refresh.setValue(
            int(self.config.get("display", {}).get("full_refresh_interval_min", 30))
        )
        form_disp.addRow("Update Layar (Partial):", self.sp_display_interval)
        form_disp.addRow("Full Refresh (Anti-Ghosting):", self.sp_display_full_refresh)
        v_disp.addLayout(form_disp)

        h_disp = QHBoxLayout()
        btn_get_display = QPushButton("Muat Konfigurasi Display dari Device")
        btn_get_display.clicked.connect(
            lambda: self.send_json_command({"cmd": "GET_CONFIG"}, ui_button=btn_get_display)
        )
        btn_sync_display = QPushButton("Sync Configuration")
        btn_sync_display.setObjectName("btnPrimary")
        btn_sync_display.clicked.connect(
            lambda: self.sync_display_config(ui_button=btn_sync_display)
        )
        h_disp.addWidget(btn_get_display)
        h_disp.addWidget(btn_sync_display)
        h_disp.addStretch()
        v_disp.addLayout(h_disp)

        layout.addWidget(grp_display)

    def setup_tab_terminal(self):
        layout = self._new_tab_layout(self.tab_terminal)

        self.txt_log = QTextEdit()
        self.txt_log.setObjectName("terminal")
        self.txt_log.setReadOnly(True)
        # Setup Maximum blocks (lines)
        self.txt_log.document().setMaximumBlockCount(150)
        
        layout.addWidget(self.txt_log)

        h = QHBoxLayout()
        self.txt_cmd = QLineEdit()
        self.txt_cmd.setPlaceholderText("Ketik perintah custom...")
        self.txt_cmd.returnPressed.connect(self.send_custom_command)
        
        btn = QPushButton("Kirim")
        btn.setObjectName("btnPrimary")
        btn.clicked.connect(self.send_custom_command)

        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self.txt_log.clear)

        h.addWidget(self.txt_cmd)
        h.addWidget(btn)
        h.addWidget(btn_clear)
        layout.addLayout(h)

    def setup_tab_custom(self):
        """Dua tabel besar (Widget Dashboard & Payload Registry) ditumpuk
        di tab ini -- kandidat paling gampang "berebut" ruang vertikal di
        layar kecil. Sama seperti tab SD Card, dipecah lewat
        _new_splitter_tab_layout supaya user bisa menarik manual proporsi
        ruang antara dua tabel ini sesuai kebutuhan saat itu."""
        splitter = self._new_splitter_tab_layout(self.tab_custom)

        # --- Panel 1: Widget Dashboard (Value Card) ---------------------
        pane_widgets = self._add_splitter_pane(splitter, stretch=1)
        grp_widgets = QGroupBox("Widget Dashboard (Value Card)")
        vw = QVBoxLayout(grp_widgets)

        self.table_widgets = self._make_expanding_table(min_height=140)
        # Simplified columns
        self.table_widgets.setColumnCount(6)
        self.table_widgets.setHorizontalHeaderLabels([
            "No", "Payload Key", "Label", "Unit", "Desimal", "Graph & CSV"
        ])
        self.table_widgets.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_widgets.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widgets.setEditTriggers(QTableWidget.NoEditTriggers)
        vw.addWidget(self.table_widgets, stretch=1)

        hw = QHBoxLayout()
        b_add = QPushButton("Tambah Widget")
        b_add.setObjectName("btnPrimary")
        b_add.clicked.connect(self.add_dashboard_widget)

        b_edit = QPushButton("Edit Widget")
        b_edit.clicked.connect(self.edit_dashboard_widget)

        b_delete = QPushButton("Hapus Widget")
        b_delete.setObjectName("btnDanger")
        b_delete.clicked.connect(self.delete_dashboard_widget)

        b_up = QPushButton("Naik")
        b_up.clicked.connect(lambda: self.move_widget(-1))

        b_down = QPushButton("Turun")
        b_down.clicked.connect(lambda: self.move_widget(1))

        b_save = QPushButton("Simpan Konfigurasi")
        b_save.setObjectName("btnSuccess")
        b_save.clicked.connect(self.save_dashboard_config)

        for b in [b_add, b_edit, b_delete, b_up, b_down, b_save]:
            hw.addWidget(b)
        hw.addStretch()
        vw.addLayout(hw)
        pane_widgets.addWidget(grp_widgets, stretch=1)

        # --- Panel 2: Payload Registry -----------------------------------
        pane_payload = self._add_splitter_pane(splitter, stretch=1)
        grp_payload = QGroupBox("Payload Registry — key yang terdeteksi dari JSON")
        vp = QVBoxLayout(grp_payload)

        self.table_payload = self._make_expanding_table(min_height=140)
        self.table_payload.setColumnCount(5)
        self.table_payload.setHorizontalHeaderLabels([
            "Payload Key", "Tipe", "Nilai Terakhir", "Dipakai Dashboard", "Label CSV (SD)"
        ])
        self.table_payload.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_payload.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_payload.setEditTriggers(QTableWidget.NoEditTriggers)
        vp.addWidget(self.table_payload, stretch=1)

        hp = QHBoxLayout()
        b_refresh = QPushButton("Refresh Registry")
        b_refresh.clicked.connect(self.refresh_payload_registry_ui)
        hp.addWidget(b_refresh)

        b_edit_label = QPushButton("Edit Label CSV")
        b_edit_label.clicked.connect(self.edit_sensor_label)
        hp.addWidget(b_edit_label)

        b_sync_labels = QPushButton("Kirim Label ke Device")
        b_sync_labels.setObjectName("btnSuccess")
        b_sync_labels.clicked.connect(self.sync_sensor_labels)
        hp.addWidget(b_sync_labels)

        hp.addStretch()
        vp.addLayout(hp)
        pane_payload.addWidget(grp_payload, stretch=1)

        self.lbl_dashboard_info = QLabel()
        self.lbl_dashboard_info.setWordWrap(True)
        pane_payload.addWidget(self.lbl_dashboard_info)

        # Bagi rata dua panel sejak awal dibuka -- user tetap bebas
        # menarik ulang garis pembatasnya lewat handle splitter.
        splitter.setSizes([390, 390])

    def setup_tab_udaraku(self):
        """Tab 7 -- konfigurasi pengiriman data ke gerbang HTTP udaraku
        (POST) yang dilakukan LANGSUNG oleh ESP32 (bukan lewat GUI/PC).
        GUI di sini murni alat untuk mengatur & mengirim konfigurasi ke
        device lewat command SET_UDARAKU_CONFIG, disimpan firmware ke
        flash. Menggantikan tab "Kirim ke Server" (JWT, iot.kemenperin.
        go.id) yang sudah dihapus total dari firmware -- lihat
        udaraku_sync.py untuk kontrak protokolnya (Bearer key, bukan
        JWT signing).
        """
        layout = self._new_tab_layout(self.tab_udaraku)

        grp_conn = QGroupBox("Koneksi Udaraku")
        form_conn = QFormLayout(grp_conn)

        self.chk_udaraku_enabled = QCheckBox("Aktifkan pengiriman data ke udaraku")
        form_conn.addRow(self.chk_udaraku_enabled)

        self.txt_udaraku_url = QLineEdit()
        self.txt_udaraku_url.setPlaceholderText(
            "https://udaraku.kemenperin.go.id:8005/v1/ingest/kanal"
        )
        form_conn.addRow("URL Endpoint:", self.txt_udaraku_url)

        h_key = QHBoxLayout()
        self.txt_udaraku_key = QLineEdit()
        # Bearer key alat -- BEDA kontrak dari private key JWT jalur server
        # lama. Dikirim apa adanya sebagai header "Authorization: Bearer
        # <key>" oleh udaraku_sync.py, tidak dipakai untuk signing apa pun.
        self.txt_udaraku_key.setPlaceholderText("Bearer key alat (aqk_live_...)")
        self.txt_udaraku_key.setEchoMode(QLineEdit.Password)
        h_key.addWidget(self.txt_udaraku_key)
        self.chk_show_udaraku_key = QCheckBox("Tampilkan")
        self.chk_show_udaraku_key.toggled.connect(
            lambda checked: self.txt_udaraku_key.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        h_key.addWidget(self.chk_show_udaraku_key)
        form_conn.addRow("Bearer Key:", h_key)

        self.txt_udaraku_kode_alat = QLineEdit()
        self.txt_udaraku_kode_alat.setPlaceholderText("mis. TRHC001")
        # Sengaja input manual, BUKAN auto-terisi dari SN device (GET_IDENTITY)
        # -- kode_alat boleh berbeda dari SN fisik alat.
        form_conn.addRow("Kode Alat:", self.txt_udaraku_kode_alat)

        layout.addWidget(grp_conn)

        grp_kanal = QGroupBox("Kanal yang Dikirim")
        v_kanal = QVBoxLayout(grp_kanal)
        lbl_kanal_hint = QLabel(
            "Centang payload key yang dikirim ke udaraku. Daftar ini mengikuti "
            "widget sensor yang terdaftar di tab \"Dashboard Designer\" -- "
            "tambah/hapus widget di sana untuk mengubah pilihan di sini. "
            "Kalau TIDAK ADA yang dicentang, firmware mengirim SEMUA kanal "
            "(begitu udaraku_sync.py menafsirkan daftar kanal kosong)."
        )
        lbl_kanal_hint.setWordWrap(True)
        v_kanal.addWidget(lbl_kanal_hint)

        self._kanal_checkbox_container = QWidget()
        self._kanal_checkbox_layout = QVBoxLayout(self._kanal_checkbox_container)
        self._kanal_checkbox_layout.setContentsMargins(0, 0, 0, 0)
        self._chk_udaraku_kanal = {}
        v_kanal.addWidget(self._kanal_checkbox_container)

        layout.addWidget(grp_kanal)

        grp_timing = QGroupBox("Interval Pengiriman")
        form_timing = QFormLayout(grp_timing)

        self.sp_udaraku_interval = ThemedSpinBox()
        self.sp_udaraku_interval.setRange(5, 86400)
        self.sp_udaraku_interval.setSuffix(" detik")
        self.sp_udaraku_interval.setValue(60)
        form_timing.addRow("Interval Realtime:", self.sp_udaraku_interval)

        self.chk_udaraku_queue_enabled = QCheckBox(
            "Aktifkan pengiriman antrian (backlog CSV)"
        )
        self.chk_udaraku_queue_enabled.setChecked(True)
        form_timing.addRow(self.chk_udaraku_queue_enabled)

        self.sp_udaraku_queue_interval = ThemedSpinBox()
        self.sp_udaraku_queue_interval.setRange(1, 3600)
        self.sp_udaraku_queue_interval.setSuffix(" detik")
        self.sp_udaraku_queue_interval.setValue(5)
        form_timing.addRow("Interval Antrian:", self.sp_udaraku_queue_interval)

        self.sp_udaraku_timeout = ThemedSpinBox()
        self.sp_udaraku_timeout.setRange(1, 120)
        self.sp_udaraku_timeout.setSuffix(" detik")
        self.sp_udaraku_timeout.setValue(15)
        form_timing.addRow("Timeout Koneksi:", self.sp_udaraku_timeout)

        layout.addWidget(grp_timing)

        grp_notif = QGroupBox("Notifikasi Buzzer Pengiriman")
        v_notif = QVBoxLayout(grp_notif)

        lbl_fail_header = QLabel("<b>Saat Gagal</b>")
        v_notif.addWidget(lbl_fail_header)

        form_fail = QFormLayout()
        self.chk_udaraku_fail_buzzer_enabled = QCheckBox(
            "Bunyikan buzzer setiap kali satu kiriman ke udaraku gagal"
        )
        self.chk_udaraku_fail_buzzer_enabled.setChecked(True)
        form_fail.addRow(self.chk_udaraku_fail_buzzer_enabled)

        self.sp_udaraku_fail_buzzer_pattern = ThemedSpinBox()
        self.sp_udaraku_fail_buzzer_pattern.setRange(1, 10)
        self.sp_udaraku_fail_buzzer_pattern.setValue(3)
        form_fail.addRow("Pola Buzzer (jumlah bunyi):", self.sp_udaraku_fail_buzzer_pattern)
        v_notif.addLayout(form_fail)

        lbl_success_header = QLabel("<b>Saat Sukses</b>")
        v_notif.addWidget(lbl_success_header)

        form_success = QFormLayout()
        self.chk_udaraku_success_buzzer_enabled = QCheckBox(
            "Bunyikan buzzer setiap kali kirim realtime sukses"
        )
        self.chk_udaraku_success_buzzer_enabled.setChecked(True)
        form_success.addRow(self.chk_udaraku_success_buzzer_enabled)

        self.sp_udaraku_success_buzzer_pattern = ThemedSpinBox()
        self.sp_udaraku_success_buzzer_pattern.setRange(1, 10)
        self.sp_udaraku_success_buzzer_pattern.setValue(1)
        form_success.addRow(
            "Pola Buzzer (jumlah bunyi):", self.sp_udaraku_success_buzzer_pattern
        )
        v_notif.addLayout(form_success)

        layout.addWidget(grp_notif)

        h_btn = QHBoxLayout()
        btn_get_udaraku = QPushButton("Muat Konfigurasi Udaraku dari Device")
        btn_get_udaraku.clicked.connect(
            lambda: self.send_json_command({"cmd": "GET_CONFIG"}, ui_button=btn_get_udaraku)
        )
        btn_sync_udaraku = QPushButton("Sync Configuration")
        btn_sync_udaraku.setObjectName("btnPrimary")
        btn_sync_udaraku.clicked.connect(
            lambda: self.sync_udaraku_config(ui_button=btn_sync_udaraku)
        )
        h_btn.addWidget(btn_get_udaraku)
        h_btn.addWidget(btn_sync_udaraku)
        h_btn.addStretch()
        layout.addLayout(h_btn)

        grp_status = QGroupBox("Status Pengiriman ke Udaraku")
        v_status = QVBoxLayout(grp_status)

        h_badge = QHBoxLayout()
        self.lbl_udaraku_status = QLabel("Belum ada aktivitas")
        self.lbl_udaraku_status.setObjectName("statusBadgeDisconnected")
        self.lbl_udaraku_status.setAlignment(Qt.AlignCenter)
        h_badge.addWidget(self.lbl_udaraku_status)
        h_badge.addStretch()
        v_status.addLayout(h_badge)

        form_status = QFormLayout()
        self.lbl_udaraku_last_send = QLabel("--")
        self.lbl_udaraku_response = QLabel("--")
        self.lbl_udaraku_response.setTextFormat(Qt.PlainText)
        self.lbl_udaraku_queue = QLabel("--")
        form_status.addRow("Terakhir kirim:", self.lbl_udaraku_last_send)
        form_status.addRow("Respons udaraku:", self.lbl_udaraku_response)
        form_status.addRow("Sisa antrian:", self.lbl_udaraku_queue)
        v_status.addLayout(form_status)

        layout.addWidget(grp_status)
        layout.addStretch()

    def _refresh_udaraku_kanal_checkboxes(self):
        """Bangun ulang checkbox kanal udaraku dari daftar widget dashboard
        (self.sensor_config) -- dipanggil dari _rebuild_sensor_cards()
        supaya daftar kanal yang bisa dipilih selalu mengikuti sensor yang
        terdaftar di tab Dashboard Designer, tanpa daftar statis terpisah
        yang gampang basi (lihat diskusi: opsi 9).

        PERBAIKAN (ditemukan lewat pengujian hardware -- lihat log
        UDARAKU_STATUS "tidak ada kanal bernilai" di setiap kirim): key di
        self.sensor_config memakai format path bertitik ala threshold,
        mis. "sensors.t" (lihat default widget & KNOWN_NUMERIC_PAYLOAD_KEYS
        di atas), BUKAN kode kanal mentah yang dipakai firmware di
        telemetry["sensors"]/cfg["kanal"] ("t", "h", "batt" -- lihat
        payload_manager.build_telemetry()). Sebelum perbaikan ini, kanal
        yang dikirim ke firmware berupa "sensors.t"/"sensors.h", yang tidak
        pernah cocok dengan kode asli "t"/"h" di firmware -- akibatnya
        SEMUA kanal selalu terfilter habis, persis gejala yang dilaporkan.
        Perbaikannya: hanya widget dengan prefix "sensors." yang dijadikan
        opsi kanal (widget lain, mis. "wifi.rssi", BUKAN bagian dari
        payload sensors yang dikirim ke udaraku -- dilewati), dan
        checkbox di-key oleh kode MENTAH setelah prefix dibuang, supaya
        `kanal` yang dikirim ke SET_UDARAKU_CONFIG cocok dengan yang
        difilter firmware."""
        if not hasattr(self, "_kanal_checkbox_layout"):
            return  # tab udaraku belum dibuat (dipanggil sebelum setup_tab_udaraku)

        # Pertahankan pilihan yang sedang tercentang di GUI sebelum widget
        # lama dihapus, supaya menambah/menghapus satu sensor tidak ikut
        # menghapus pilihan kanal yang sudah dicentang untuk sensor lain.
        # Kalau checkbox belum pernah dibangun sama sekali (panggilan
        # pertama saat init), pakai config tersimpan sebagai sumber awal.
        if self._chk_udaraku_kanal:
            previously_checked = {
                key for key, chk in self._chk_udaraku_kanal.items() if chk.isChecked()
            }
        else:
            previously_checked = set(
                self.config.get("udaraku", {}).get("kanal") or []
            )

        while self._kanal_checkbox_layout.count():
            item = self._kanal_checkbox_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._chk_udaraku_kanal = {}
        dilewati_bukan_sensor = []
        for cfg in self.sensor_config:
            payload_key = cfg.get("key", "")
            if not payload_key.startswith("sensors."):
                # Bukan bagian dari telemetry["sensors"] (mis. "wifi.rssi")
                # -- udaraku hanya mengirim kanal dari "sensors", jadi
                # widget ini tidak relevan sebagai opsi kanal.
                if payload_key:
                    dilewati_bukan_sensor.append(payload_key)
                continue
            kode = payload_key[len("sensors."):]
            if not kode or kode in self._chk_udaraku_kanal:
                continue
            label = cfg.get("label", kode)
            chk = QCheckBox(f"{label} ({kode})")
            chk.setChecked(kode in previously_checked)
            self._kanal_checkbox_layout.addWidget(chk)
            self._chk_udaraku_kanal[kode] = chk

        if not self._chk_udaraku_kanal:
            pesan = "Belum ada widget sensor (\"sensors.*\") terdaftar di tab Dashboard Designer."
            if dilewati_bukan_sensor:
                pesan += f" ({len(dilewati_bukan_sensor)} widget lain dilewati karena bukan kanal sensor.)"
            self._kanal_checkbox_layout.addWidget(QLabel(pesan))

    def setup_tab_calibration(self):
        """Tab 8 -- Kalibrasi Sensor (model bisa linear ATAU non-linear --
        poly2/poly3/exponential/logarithmic/power, lihat
        CalibrationWizardDialog) dan tampilan Identitas Perangkat
        (read-only, dari GET_IDENTITY). Kalibrasi (model+params) DAN titik
        mentahnya disimpan lokal dulu di self.config['calibration'] /
        ['calibration_points'], baru dikirim ke device lewat command
        SET_CALIBRATION supaya sama-sama persisten di flash (firmware
        menerapkan model+params ke t/h/batt di setiap payload; titik
        mentah cuma dititipkan, tidak diproses -- lihat DEFAULT_CONFIG).
        Profil disimpan per-SN device fisik supaya app bisa dipakai
        bergantian untuk banyak unit tanpa tertukar (lihat
        _handle_identity / device_profiles)."""
        layout = self._new_tab_layout(self.tab_calibration)

        grp_cal = QGroupBox("Kalibrasi Sensor (linear atau non-linear -- lihat Calibration Wizard)")
        vc = QVBoxLayout(grp_cal)

        self.lbl_active_profile = QLabel("Profil kalibrasi aktif: --")
        self.lbl_active_profile.setWordWrap(True)
        vc.addWidget(self.lbl_active_profile)

        self.table_calibration = self._make_expanding_table(min_height=150)
        self.table_calibration.setColumnCount(7)
        self.table_calibration.setHorizontalHeaderLabels([
            "Payload Key", "Label", "Model", "Params", "R\u00b2", "Nilai Mentah Terakhir", "Preview Terkalibrasi"
        ])
        self.table_calibration.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_calibration.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_calibration.setEditTriggers(QTableWidget.NoEditTriggers)
        vc.addWidget(self.table_calibration, stretch=1)

        hc = QHBoxLayout()
        btn_refresh_cal = QPushButton("Refresh Tabel")
        btn_refresh_cal.clicked.connect(self._update_calibration_table)
        hc.addWidget(btn_refresh_cal)

        btn_edit_cal = QPushButton("Calibration Wizard...")
        btn_edit_cal.setObjectName("btnPrimary")
        btn_edit_cal.clicked.connect(self.edit_calibration)
        hc.addWidget(btn_edit_cal)

        btn_reset_cal = QPushButton("Reset ke Default (tanpa kalibrasi)")
        btn_reset_cal.setObjectName("btnDanger")
        btn_reset_cal.clicked.connect(self.reset_calibration)
        hc.addWidget(btn_reset_cal)
        hc.addStretch()
        vc.addLayout(hc)

        hc2 = QHBoxLayout()
        btn_load_cal = QPushButton("Muat Kalibrasi dari Device")
        btn_load_cal.clicked.connect(
            lambda: self.send_json_command({"cmd": "GET_CONFIG"}, ui_button=btn_load_cal)
        )
        btn_sync_cal = QPushButton("Kirim Kalibrasi ke Device")
        btn_sync_cal.setObjectName("btnSuccess")
        btn_sync_cal.clicked.connect(self.sync_calibration_to_device)
        hc2.addWidget(btn_load_cal)
        hc2.addWidget(btn_sync_cal)
        hc2.addStretch()
        vc.addLayout(hc2)
        layout.addWidget(grp_cal, stretch=1)

        grp_identity = QGroupBox("Identitas Perangkat (Read-only -- dari device_identity.json firmware)")
        form_identity = QFormLayout(grp_identity)

        self.lbl_identity_pn = QLabel("--")
        self.lbl_identity_sn = QLabel("--")
        self.lbl_identity_fw = QLabel("--")
        form_identity.addRow("Part Number (PN):", self.lbl_identity_pn)
        form_identity.addRow("Serial Number (SN):", self.lbl_identity_sn)
        form_identity.addRow("Firmware Version:", self.lbl_identity_fw)

        btn_get_identity = QPushButton("Ambil Identitas dari Device")
        btn_get_identity.clicked.connect(
            lambda: self.send_json_command({"cmd": "GET_IDENTITY"}, ui_button=btn_get_identity)
        )
        form_identity.addRow(btn_get_identity)

        layout.addWidget(grp_identity)
        layout.addStretch()

    def _update_calibration_table(self):
        """Refresh tabel kalibrasi. Mengikuti pola yang sama seperti tabel
        Payload Registry -- simpan & pulihkan key yang sedang dipilih supaya
        seleksi baris tidak ter-reset kalau dipanggil tiap telemetri masuk."""
        current_row = self.table_calibration.currentRow()
        selected_key = None
        if current_row >= 0:
            item = self.table_calibration.item(current_row, 0)
            if item is not None:
                selected_key = item.text()

        calibration = self.config.get("calibration", {})
        candidate_keys = {
            self._sensor_base_key(k) for k in self.get_payload_keys(numeric_only=True)
            if k.startswith("sensors.")
        }
        candidate_keys.update(calibration.keys())

        self.table_calibration.setRowCount(0)
        restore_row = -1
        for key in sorted(candidate_keys):
            row = self.table_calibration.rowCount()
            self.table_calibration.insertRow(row)

            label = self.config.get("sensor_labels", {}).get(key, key)
            cal = calibration.get(key, {})
            model = cal.get("model")
            if model not in CALIBRATION_MODEL_PARAM_COUNTS:
                # Belum pernah dikalibrasi, atau format lama tanpa "model"
                # -- anggap identity linear untuk ditampilkan.
                model = "linear"
                params = [float(cal.get("scale", 1.0)), float(cal.get("offset", 0.0))]
            else:
                params = cal.get("params", [])
            r2 = cal.get("r2")
            raw = self.latest_payload.get(f"sensors.{key}")

            self.table_calibration.setItem(row, 0, QTableWidgetItem(key))
            self.table_calibration.setItem(row, 1, QTableWidgetItem(str(label)))
            self.table_calibration.setItem(row, 2, QTableWidgetItem(CALIBRATION_MODEL_LABELS.get(model, model)))
            self.table_calibration.setItem(row, 3, QTableWidgetItem(
                ", ".join(_format_calibration_number(p) for p in params)
            ))
            self.table_calibration.setItem(row, 4, QTableWidgetItem(
                f"{r2:.5f}" if isinstance(r2, (int, float)) else "--"
            ))

            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                self.table_calibration.setItem(row, 5, QTableWidgetItem(str(raw)))
                preview = evaluate_calibration_model(model, params, raw)
                preview_text = "(di luar domain)" if preview is None else str(round(preview, 2))
                self.table_calibration.setItem(row, 6, QTableWidgetItem(preview_text))
            else:
                self.table_calibration.setItem(row, 5, QTableWidgetItem("--"))
                self.table_calibration.setItem(row, 6, QTableWidgetItem("--"))

            if key == selected_key:
                restore_row = row

        if restore_row >= 0:
            self.table_calibration.selectRow(restore_row)

    def edit_calibration(self):
        row = self.table_calibration.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Info", "Pilih dulu salah satu baris payload key di tabel."
            )
            return
        key_item = self.table_calibration.item(row, 0)
        if key_item is None:
            return
        key = key_item.text()
        label = self.config.get("sensor_labels", {}).get(key, key)
        current_cal = self.config.get("calibration", {}).get(key, {})
        current_points = self.config.get("calibration_points", {}).get(key, [])
        last_raw = self.latest_payload.get(key)

        dialog = CalibrationWizardDialog(
            self, key=key, label=label, current_cal=current_cal,
            current_points=current_points, last_raw=last_raw
        )
        if dialog.exec_() == QDialog.Accepted:
            self.config.setdefault("calibration", {})[key] = dialog.get_calibration()
            # Titik mentah (raw->ref) yang dipakai fitting ikut disimpan --
            # PC saja, lihat catatan di DEFAULT_CONFIG["calibration_points"].
            points = dialog.get_calibration_points()
            if points:
                self.config.setdefault("calibration_points", {})[key] = points
            else:
                self.config.setdefault("calibration_points", {}).pop(key, None)
            if self._active_device_sn:
                self._snapshot_calibration_into_profile(self._active_device_sn)
            self.persist_config()
            self._update_calibration_table()

    def reset_calibration(self):
        row = self.table_calibration.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Info", "Pilih dulu salah satu baris payload key di tabel."
            )
            return
        key_item = self.table_calibration.item(row, 0)
        if key_item is None:
            return
        key = key_item.text()
        self.config.get("calibration", {}).pop(key, None)
        self.config.get("calibration_points", {}).pop(key, None)
        if self._active_device_sn:
            self._snapshot_calibration_into_profile(self._active_device_sn)
        self.persist_config()
        self._update_calibration_table()

    def sync_calibration_to_device(self):
        """Kirim seluruh kalibrasi (model+params) DAN titik mentahnya yang
        tersimpan lokal ke device (flash) lewat command SET_CALIBRATION.
        Device tidak memproses "calibration_points" sama sekali (tidak ada
        fitting di firmware) -- field itu cuma dititipkan supaya ikut
        persisten di flash & bisa ditarik balik lewat GET_CONFIG kalau
        suatu saat device ini dipindah ke PC lain yang belum punya cache-
        nya. Kalau belum pernah dikalibrasi sama sekali, tetap boleh
        dikirim kosong -- firmware akan tetap memperlakukan semua key
        sebagai identity (tidak ada efek)."""
        calibration = self.config.get("calibration", {})
        calibration_points = self.config.get("calibration_points", {})
        self.send_json_command({
            "cmd": "SET_CALIBRATION",
            "calibration": calibration,
            "calibration_points": calibration_points,
        })

    def _load_identity_display_from_config(self):
        identity = self.config.get("device_identity", {})
        self.lbl_identity_pn.setText(str(identity.get("pn") or "--"))
        self.lbl_identity_sn.setText(str(identity.get("sn") or "--"))
        self.lbl_identity_fw.setText(str(identity.get("firmware_version") or "--"))

    def _snapshot_calibration_into_profile(self, sn):
        """Simpan self.config['calibration']/['calibration_points'] yang
        SEDANG aktif ke cache device_profiles[sn], supaya tidak hilang saat
        nanti app switch ke profil SN lain. Dipanggil setiap identitas
        device (baru/lama) diterima, dan sebelum switch profil aktif."""
        sn = str(sn or "").strip()
        if not sn:
            return
        profile = self.config.setdefault("device_profiles", {}).setdefault(sn, {})
        profile["calibration"] = dict(self.config.get("calibration", {}))
        profile["calibration_points"] = dict(self.config.get("calibration_points", {}))
        ident = self.config.get("device_identity", {})
        if ident.get("pn"):
            profile["pn"] = ident["pn"]
        if ident.get("firmware_version"):
            profile["firmware_version"] = ident["firmware_version"]

    def _update_active_profile_label(self):
        if not hasattr(self, "lbl_active_profile"):
            return
        sn = self._active_device_sn
        n_known = len(self.config.get("device_profiles", {}))
        if sn:
            self.lbl_active_profile.setText(
                f"Profil kalibrasi aktif: SN <b>{html.escape(sn)}</b> "
                f"({n_known} device dikenal di PC ini)"
            )
        else:
            self.lbl_active_profile.setText(
                f"Profil kalibrasi aktif: belum ada device teridentifikasi "
                f"({n_known} device dikenal di PC ini)"
            )

    def _handle_identity(self, data):
        """Menampilkan identitas perangkat yang dibalas firmware atas
        GET_IDENTITY. Read-only di sisi GUI (tidak ada SET_IDENTITY),
        sesuai keputusan: provisioning SN/PN dilakukan manual di flash.

        SN yang didapat di sini JUGA dipakai sebagai kunci untuk memilih
        profil kalibrasi mana yang aktif (self.config['calibration'] /
        ['calibration_points']) -- lihat device_profiles di DEFAULT_CONFIG.
        Kalau SN berbeda dari sebelumnya (device fisik lain baru saja
        connect): profil lama di-snapshot dulu, lalu profil SN baru
        dimuat kalau PC ini pernah mengenalnya; kalau belum pernah (mis.
        device ini biasa dikalibrasi dari PC lain), kalibrasi lokal
        dikosongkan dulu (supaya TIDAK ketimpa kalibrasi device lain) dan
        app otomatis menarik persamaan yang sudah tersimpan di flash
        device sendiri lewat GET_CONFIG sebagai fallback -- device tetap
        satu-satunya yang wajib "tahu" hasil akhir, PC cuma cache."""
        new_sn = str(data.get("sn") or "").strip()
        old_sn = self._active_device_sn

        if new_sn and new_sn != old_sn:
            if old_sn:
                self._snapshot_calibration_into_profile(old_sn)

            profile = self.config.get("device_profiles", {}).get(new_sn)
            if profile:
                self.config["calibration"] = dict(profile.get("calibration", {}))
                self.config["calibration_points"] = dict(profile.get("calibration_points", {}))
                self.log_terminal(
                    "INFO",
                    f"Profil kalibrasi SN {new_sn} dimuat dari cache lokal PC ini.",
                    "#16a085"
                )
            else:
                self.config["calibration"] = {}
                self.config["calibration_points"] = {}
                self.log_terminal(
                    "INFO",
                    f"SN {new_sn} belum dikenal PC ini -- menarik kalibrasi "
                    f"tersimpan langsung dari device (GET_CONFIG)...",
                    "#2980b9"
                )
                self.send_json_command({"cmd": "GET_CONFIG"})

            self._active_device_sn = new_sn
            self._update_calibration_table()

        identity = {
            "pn": data.get("pn", ""),
            "sn": data.get("sn", ""),
            "firmware_version": data.get("firmware_version", ""),
        }
        self.config["device_identity"] = identity
        if new_sn:
            self._snapshot_calibration_into_profile(new_sn)
        self.persist_config()
        self._load_identity_display_from_config()
        self._update_active_profile_label()
        self.log_terminal("INFO", "Identitas device berhasil dimuat.", "#16a085")

    def _load_udaraku_controls_from_config(self):
        """Isi kontrol Tab 7 dari config PC yang tersimpan lokal (sebelum
        pernah GET_CONFIG dari device). Checkbox kanal harus sudah dibangun
        oleh _refresh_udaraku_kanal_checkboxes() (dipanggil dari
        _rebuild_sensor_cards() sebelum method ini di __init__) supaya
        tanda centang di bawah ini punya widget untuk diisi."""
        udaraku_cfg = self.config.get("udaraku", {})
        self.chk_udaraku_enabled.setChecked(bool(udaraku_cfg.get("enabled", False)))
        self.txt_udaraku_url.setText(str(udaraku_cfg.get("url", "")))
        self.txt_udaraku_key.setText(str(udaraku_cfg.get("key", "")))
        self.txt_udaraku_kode_alat.setText(str(udaraku_cfg.get("kode_alat", "")))
        self.sp_udaraku_interval.setValue(int(udaraku_cfg.get("interval_sec", 60)))
        self.chk_udaraku_queue_enabled.setChecked(bool(udaraku_cfg.get("queue_enabled", True)))
        self.sp_udaraku_queue_interval.setValue(int(udaraku_cfg.get("queue_interval_sec", 5)))
        self.sp_udaraku_timeout.setValue(int(udaraku_cfg.get("timeout_sec", 15)))
        self.chk_udaraku_fail_buzzer_enabled.setChecked(
            bool(udaraku_cfg.get("fail_buzzer_enabled", True))
        )
        self.sp_udaraku_fail_buzzer_pattern.setValue(
            int(udaraku_cfg.get("fail_buzzer_pattern", 3))
        )
        self.chk_udaraku_success_buzzer_enabled.setChecked(
            bool(udaraku_cfg.get("success_buzzer_enabled", True))
        )
        self.sp_udaraku_success_buzzer_pattern.setValue(
            int(udaraku_cfg.get("success_buzzer_pattern", 1))
        )
        kanal_tersimpan = set(udaraku_cfg.get("kanal") or [])
        for key, chk in self._chk_udaraku_kanal.items():
            chk.setChecked(key in kanal_tersimpan)

    def sync_udaraku_config(self, ui_button=None):
        """Kirim konfigurasi udaraku (Tab 7) ke ESP32 untuk disimpan ke
        flash lewat command SET_UDARAKU_CONFIG."""
        kanal = [key for key, chk in self._chk_udaraku_kanal.items() if chk.isChecked()]
        udaraku_payload = {
            "enabled": self.chk_udaraku_enabled.isChecked(),
            "url": self.txt_udaraku_url.text().strip().rstrip("/"),
            "key": self.txt_udaraku_key.text(),
            "kode_alat": self.txt_udaraku_kode_alat.text().strip(),
            "interval_sec": self.sp_udaraku_interval.value(),
            "queue_enabled": self.chk_udaraku_queue_enabled.isChecked(),
            "queue_interval_sec": self.sp_udaraku_queue_interval.value(),
            "timeout_sec": self.sp_udaraku_timeout.value(),
            "kanal": kanal,
            "fail_buzzer_enabled": self.chk_udaraku_fail_buzzer_enabled.isChecked(),
            "fail_buzzer_pattern": self.sp_udaraku_fail_buzzer_pattern.value(),
            "success_buzzer_enabled": self.chk_udaraku_success_buzzer_enabled.isChecked(),
            "success_buzzer_pattern": self.sp_udaraku_success_buzzer_pattern.value(),
        }
        if udaraku_payload["enabled"] and not udaraku_payload["url"]:
            QMessageBox.warning(
                self, "Peringatan",
                "URL Endpoint tidak boleh kosong kalau pengiriman ke udaraku diaktifkan."
            )
            return
        if udaraku_payload["enabled"] and not udaraku_payload["key"]:
            QMessageBox.warning(
                self, "Peringatan",
                "Bearer Key tidak boleh kosong kalau pengiriman ke udaraku diaktifkan."
            )
            return
        self.config["udaraku"] = udaraku_payload
        self.persist_config()
        self.send_json_command(
            {"cmd": "SET_UDARAKU_CONFIG", "udaraku": udaraku_payload}, ui_button=ui_button
        )

    def _handle_udaraku_status(self, data):
        """Menampilkan status pengiriman ke udaraku real-time. Dikirim
        firmware setiap kali selesai satu upaya POST (realtime maupun
        antrian), TIDAK menunggu diminta GUI. Bentuk payload yang
        diharapkan (disepakati untuk implementasi firmware selanjutnya --
        menggantikan pesan string polos yang dibuang diam-diam oleh
        dashboard versi sebelumnya, lihat catatan migrasi):

        {"type": "UDARAKU_STATUS", "mode": "realtime"|"queue",
         "success": true/false, "http_status": 200, "message": "...",
         "timestamp": "2026-07-29 10:00:00", "queue_pending": 3}
        """
        success = bool(data.get("success"))
        mode = str(data.get("mode", "--"))
        mode_label = "Realtime" if mode == "realtime" else "Antrian" if mode == "queue" else mode

        if not success:
            fail_reason = data.get("message") or data.get("http_status") or "tidak diketahui"
            self.log_terminal(
                "WARNING", f"Kirim ke udaraku gagal ({mode_label}): {fail_reason}", "#e67e22"
            )
        if data.get("recovered"):
            self.log_terminal(
                "INFO", "Koneksi ke udaraku PULIH setelah sempat gagal.", "#16a085"
            )

        if success:
            self.lbl_udaraku_status.setObjectName("statusBadgeConnected")
            self.lbl_udaraku_status.setText(f"Sukses ({mode_label})")
        else:
            self.lbl_udaraku_status.setObjectName("statusBadgeError")
            self.lbl_udaraku_status.setText(f"Gagal ({mode_label})")
        self.lbl_udaraku_status.style().unpolish(self.lbl_udaraku_status)
        self.lbl_udaraku_status.style().polish(self.lbl_udaraku_status)

        ts = data.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S"))
        self.lbl_udaraku_last_send.setText(str(ts))

        http_status = data.get("http_status")
        message = data.get("message", "")
        if message:
            pesan_text = str(message)
        else:
            pesan_text = "Terverifikasi, tanpa pesan tambahan" if success else "Tidak ada pesan dari udaraku"
        resp = f"HTTP {http_status} -- {pesan_text}" if http_status is not None else pesan_text
        # textFormat sudah di-set PlainText saat widget dibuat -- jangan
        # dibungkus html.escape() (lihat catatan yang sama di versi lama
        # untuk jalur server: itu untuk konteks rich text, bukan QLabel ini).
        self.lbl_udaraku_response.setText(resp)

        if "queue_pending" in data:
            self.lbl_udaraku_queue.setText(str(data.get("queue_pending")))

    # ---------------- Serial ----------------
    def refresh_ports(self):
        self.cb_ports.clear()
        for port in serial.tools.list_ports.comports():
            self.cb_ports.addItem(port.device)

    def toggle_connection(self):
        if self.worker is None:
            port = self.cb_ports.currentText()
            if not port:
                QMessageBox.warning(self, "Peringatan", "Pilih Port Serial terlebih dahulu.")
                return

            baud = int(self.config.get("device", {}).get("baudrate", 115200))
            self._identity_requested_this_session = False
            self.worker = SerialWorker(port, baud)
            self.worker.data_received.connect(self.handle_incoming_data)
            self.worker.error_signal.connect(self.handle_serial_error)
            self.worker.start()

            self.btn_connect.setText("Disconnect")
            self._set_button_role(self.btn_connect, "btnDanger")
            self.lbl_conn_status.setText("Connected")
            self.lbl_conn_status.setObjectName("statusBadgeConnected")
            self.lbl_conn_status.style().unpolish(self.lbl_conn_status)
            self.lbl_conn_status.style().polish(self.lbl_conn_status)
            
            self.log_terminal("INFO", f"Mencoba terhubung ke {port} dengan baudrate {baud}", "#2980b9")
        else:
            self.disconnect_serial()

    def disconnect_serial(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        self._identity_requested_this_session = False
        self.btn_connect.setText("Connect")
        self._set_button_role(self.btn_connect, "btnPrimary")
        self.lbl_conn_status.setText("Disconnected")
        self.lbl_conn_status.setObjectName("statusBadgeDisconnected")
        self.lbl_conn_status.style().unpolish(self.lbl_conn_status)
        self.lbl_conn_status.style().polish(self.lbl_conn_status)
        self.log_terminal("INFO", "Port serial diputuskan.", "#7f8c8d")

    def _set_button_role(self, button, object_name):
        button.setObjectName(object_name)
        button.style().unpolish(button)
        button.style().polish(button)

    def _apply_theme(self, persist=True, settings=None):
        """Terapkan tema global ke stylesheet, palette, font, dan grafik."""
        ui = self.config.setdefault("ui", {})
        if settings is not None:
            ui.update(settings)

        if settings and settings.get("theme") == "custom":
            key = "custom"
            base = dict(normalize_theme(THEME_PRESETS[DEFAULT_THEME_KEY]))
            for k, v in (settings.get("custom_colors") or {}).items():
                if k in base and isinstance(v, str):
                    base[k] = v
            base["font_family"] = str(settings.get("font_family") or base["font_family"])
            base["font_size"] = int(settings.get("font_size", base["font_size"]))
            theme = normalize_theme(base)
        else:
            key, theme = theme_from_config(ui)
            if settings and settings.get("theme") in THEME_PRESETS:
                key = settings["theme"]
                theme = normalize_theme(THEME_PRESETS[key])
                theme["font_family"] = str(settings.get("font_family") or theme["font_family"])
                theme["font_size"] = int(settings.get("font_size", theme["font_size"]))
                if isinstance(settings.get("custom_colors"), dict):
                    for k, v in settings["custom_colors"].items():
                        if k in theme and isinstance(v, str):
                            theme[k] = v
                theme = normalize_theme(theme)

        app = QApplication.instance()
        app.setStyleSheet(build_stylesheet(theme))
        app.setFont(QFont(theme["font_family"], int(theme["font_size"])))
        app.setPalette(_build_theme_palette(theme))

        if hasattr(self, "plot_widget"):
            self.plot_widget.setBackground(theme["plot_bg"])
            axis_color = QColor(theme["text"])
            for axis_name in ("left", "bottom", "right", "top"):
                try:
                    axis = self.plot_widget.getAxis(axis_name)
                    axis.setPen(axis_color)
                    axis.setTextPen(axis_color)
                except Exception:
                    pass
            try:
                self.plot_widget.showGrid(x=True, y=True, alpha=0.20)
            except Exception:
                pass

        ui["theme"] = key
        ui["font_family"] = theme["font_family"]
        ui["font_size"] = int(theme["font_size"])
        if key == "custom":
            ui["custom_colors"] = {k: theme[k] for k, _ in ThemeDialog.COLOR_FIELDS}
        elif not isinstance(ui.get("custom_colors"), dict):
            ui["custom_colors"] = {}

        # Tetap sinkronkan legacy accent untuk config lama.
        reverse = {v: k for k, v in LEGACY_ACCENT_TO_THEME.items()}
        if key in reverse:
            ui["accent"] = reverse[key]
        else:
            ui["accent"] = "blue"

        if persist:
            self.persist_config()

    def _apply_accent(self, accent_key, persist=True):
        """Kompatibilitas terhadap pemanggil lama: accent lama dipetakan ke tema baru."""
        key = LEGACY_ACCENT_TO_THEME.get(accent_key, DEFAULT_THEME_KEY)
        self._apply_theme(
            persist=persist,
            settings={
                "theme": key,
                "font_family": self.config.get("ui", {}).get("font_family", DEFAULT_THEME["font_family"]),
                "font_size": self.config.get("ui", {}).get("font_size", DEFAULT_THEME["font_size"]),
                "custom_colors": {},
            },
        )

    def open_theme_dialog(self):
        ui = self.config.get("ui", {})
        current_key, _ = theme_from_config(ui)
        dialog = ThemeDialog(self, current_theme_key=current_key, current_ui=ui)
        if dialog.exec_() == QDialog.Accepted:
            settings = dialog.get_settings()
            self._apply_theme(persist=True, settings=settings)

    def send_command(self, cmd, expect_ack=False, timeout=5.0, ui_button=None):
        if not self.worker:
            QMessageBox.warning(self, "Peringatan", "Perangkat belum terhubung secara serial.")
            if ui_button:
                ui_button.setEnabled(True)
                ui_button.setText(ui_button.property("original_text"))
            return None

        command_id = None
        if expect_ack:
            self.command_seq += 1
            command_id = self.command_seq
            self.pending_commands[command_id] = {
                "cmd": cmd,
                "sent": time.time(),
                "timeout": timeout,
                "ui_button": ui_button,
                "action": "RAW"
            }

        if self.worker.write_data(cmd):
            self.log_terminal("OUT", cmd, "#8e44ad") # Purple
            return command_id
        return None

    def send_json_command(self, payload, expect_ack=True, ui_button=None):
        # Cek koneksi lebih dulu, SEBELUM tombol diubah ke status "Loading...".
        # Kalau tidak, saat device belum terhubung, tombol akan macet disabled
        # selama masa timeout ACK (beberapa detik) padahal sudah jelas gagal
        # sejak awal (send_command_without_new_id tidak menerima ui_button
        # sehingga tidak bisa mengembalikan status tombol dengan segera).
        if not self.worker:
            QMessageBox.warning(self, "Peringatan", "Perangkat belum terhubung secara serial.")
            return None

        payload = dict(payload)

        # Loading Feedback for UI Button
        if ui_button:
            ui_button.setProperty("original_text", ui_button.text())
            ui_button.setEnabled(False)
            ui_button.setText("Loading...")
            
        if expect_ack:
            self.command_seq += 1
            payload["id"] = self.command_seq
            cid = payload["id"]
            cmd_text = json.dumps(payload, separators=(",", ":"))
            # GET_FILE sekarang dikirim ber-chunk (bisa berupa banyak pesan
            # serial berturut-turut untuk file besar), jadi butuh timeout ACK
            # yang jauh lebih longgar daripada perintah biasa. Timeout ini
            # tetap "di-reset" tiap kali chunk baru masuk lewat
            # _touch_pending_command(), jadi 90 detik ini cuma jaring
            # pengaman kalau transfer benar-benar macet total.
            action_timeout = 90.0 if payload.get("cmd") == "GET_FILE" else 6.0
            self.pending_commands[cid] = {
                "cmd": cmd_text,
                "sent": time.time(),
                "timeout": action_timeout,
                "ui_button": ui_button,
                "action": payload.get("cmd", "UNKNOWN")
            }
            return self.send_command_without_new_id(cmd_text)
        return self.send_command(json.dumps(payload, separators=(",", ":")), False, ui_button=ui_button)

    def send_command_without_new_id(self, cmd):
        if not self.worker:
            QMessageBox.warning(self, "Peringatan", "Perangkat belum terhubung secara serial.")
            return None
        if self.worker.write_data(cmd):
            self.log_terminal("OUT", cmd, "#8e44ad") # Purple
            return True
        return False

    def send_custom_command(self):
        cmd = self.txt_cmd.text().strip()
        if cmd:
            self.send_command(cmd, expect_ack=False)
            self.txt_cmd.clear()

    # ---------------- Incoming ----------------
    def handle_incoming_data(self, raw_data):
        """Slot yang dipanggil worker.data_received.emit() dari thread lain
        (queued connection lintas thread). PERBAIKAN (crash nyata yang
        pernah teramati -- lihat catatan di handle_ack()): seluruh isi
        method ini dibungkus try/except supaya SATU baris data yang
        memicu error tak terduga di mana pun (bug lain, race kondisi
        widget yang sudah dihapus, dll.) tidak lagi menjatuhkan SELURUH
        proses (sebelumnya: RuntimeError tak tertangani di sini bisa
        membuat aplikasi core-dump -- dashboard jadi "diam total" tanpa
        pesan apa pun terlihat kalau dijalankan bukan dari terminal).
        Error tak terduga sekarang dicatat ke Terminal Log, koneksi serial
        TIDAK diputus, siklus data berikutnya tetap diproses normal."""
        try:
            self._dispatch_incoming_data(raw_data)
        except Exception as exc:
            self.log_terminal(
                "ERR", f"Galat tak terduga saat memproses data masuk: {exc!r}", "#c0392b"
            )

    def _dispatch_incoming_data(self, raw_data):
        self.log_terminal("IN", raw_data, "#34495e") # Dark Blue/Gray
        self._update_heartbeat()

        # PERBAIKAN: minta identitas (SN) device otomatis begitu ada tanda
        # device benar-benar hidup & mengirim data (baris pertama masuk) --
        # bukan langsung saat tombol Connect diklik, karena port baru
        # dibuka belum tentu device-nya sudah selesai boot/reset. SN inilah
        # yang dipakai untuk memilih profil kalibrasi mana yang aktif
        # (lihat _handle_identity), jadi harus otomatis, tidak menunggu
        # operator klik "Ambil Identitas dari Device" secara manual.
        if self.worker is not None and not self._identity_requested_this_session:
            self._identity_requested_this_session = True
            self.send_json_command({"cmd": "GET_IDENTITY"})

        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            # PERBAIKAN: baris yang gagal di-parse dulu dibuang diam-diam,
            # jadi kalau ada korupsi data di jalur serial (mis. akibat
            # brownout LDO saat WiFi scan), pengguna tidak tahu apa-apa
            # selain "hasilnya tidak muncul". Sekarang tetap dicatat sebagai
            # error di terminal supaya kelihatan jelas ada baris yang rusak.
            self.log_terminal(
                "ERR",
                f"Baris tidak bisa di-parse (kemungkinan korup di jalur serial): {raw_data[:200]}",
                "#c0392b"
            )
            return

        if not isinstance(data, dict):
            return

        self._register_payloads(data)

        if data.get("type") == "ACK" or "ack" in data:
            self.handle_ack(data)

        if data.get("type") in ("HB", "TELEMETRY", "DATA", "STATUS") or any(
            cfg.get("key") in data for cfg in self.sensor_config if isinstance(cfg, dict)
        ) or "wifi" in data:
            self._handle_telemetry(data)

        if data.get("type") == "SCAN_START":
            self._handle_scan_start(data)
        elif data.get("type") == "SCAN_ITEM":
            self._handle_scan_item(data)
        elif data.get("type") == "SCAN_END":
            self._handle_scan_end(data)

        if isinstance(data.get("files"), list):
            self._populate_file_table(data["files"])

        if data.get("type") == "FILE_START":
            self._handle_file_start(data)
        elif data.get("type") == "FILE_CHUNK":
            self._handle_file_chunk(data)
        elif data.get("type") == "FILE_END":
            self._handle_file_end(data)

        if data.get("type") == "CONFIG":
            self._handle_device_config(data)

        if data.get("type") == "UDARAKU_STATUS":
            self._handle_udaraku_status(data)

        if data.get("type") == "IDENTITY":
            self._handle_identity(data)

    def _register_payloads(self, data):
        ignored = {
            "type", "ack", "status", "cmd", "id", "message",
            "files", "error"
        }
        now = time.time()

        def _register_one(k, v):
            self.payload_registry[k] = {
                "type": type(v).__name__,
                "last": v,
                "updated": now,
            }
            self.latest_payload[k] = v
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                self.history.setdefault(k, deque(maxlen=MAX_POINTS))
                self.history[k].append((now - self.start_time, v))

        for key, value in data.items():
            if key in ignored:
                continue
            _register_one(key, value)
            # PERBAIKAN: payload nested (mis. "wifi": {"ssid":..,"rssi":..})
            # sebelumnya cuma terdaftar sebagai satu key "wifi" (tipe dict),
            # jadi kalau widget dashboard diarahkan ke field di dalamnya
            # (mis. mengetik "rssi" di Payload Designer), nilainya TIDAK
            # PERNAH match karena "rssi" bukan key top-level -- ini penyebab
            # widget baru yang tidak mau menampilkan nilai. Sekarang field
            # di dalam dict satu level diratakan juga sebagai "wifi.rssi",
            # "wifi.ssid", dst, supaya bisa dipilih & benar-benar ke-update.
            if isinstance(value, dict):
                for subkey, subval in value.items():
                    _register_one(f"{key}.{subkey}", subval)

        # PERBAIKAN: dulu dipanggil refresh_payload_registry_ui() di sini,
        # yang JUGA merombak total tabel Widget Dashboard (Dashboard
        # Designer) setiap payload masuk (~1x/detik) -- akibatnya baris yang
        # sedang dipilih di situ selalu ke-reset sebelum sempat diklik
        # Edit/Hapus. Sekarang cukup refresh tabel Payload Registry saja;
        # tabel Widget Dashboard hanya dirombak saat konfigurasinya memang
        # berubah (tambah/edit/hapus/pindah widget).
        self._update_payload_registry_table()
        self._update_calibration_table()

    def handle_ack(self, data):
        status = str(data.get("status", "ok")).lower()
        cmd = data.get("cmd", data.get("ack", "UNKNOWN"))
        cid = data.get("id")

        if cid is not None and cid in self.pending_commands:
            info = self.pending_commands.pop(cid)
            btn = info.get("ui_button")
            action = info.get("action")

            # Restore Button State
            # PERBAIKAN (crash nyata di lapangan, lihat catatan diskusi
            # migrasi udaraku): ACK bisa datang SETELAH tombol yang
            # memicunya sudah dihapus Qt (paling sering saat aplikasi
            # sedang ditutup -- worker.stop() dipanggil di closeEvent,
            # tapi sinyal data_received yang SUDAH terlanjur di-queue lintas
            # thread sebelum stop() tetap diproses event loop setelah
            # sebagian widget mulai dihancurkan). Referensi Python ke
            # tombol itu (`btn`) tetap "truthy" walau objek C++-nya sudah
            # mati, jadi `if btn:` saja TIDAK cukup -- baru ketahuan saat
            # method dipanggil (RuntimeError: wrapped C/C++ object ...
            # has been deleted), yang tadinya bikin seluruh proses crash
            # (core dumped) dan membuat dashboard terlihat "diam total".
            if btn:
                try:
                    btn.setEnabled(True)
                    btn.setText(btn.property("original_text"))
                except RuntimeError:
                    pass

            # Popups for Wi-Fi commands
            if action in ("WIFI_CONNECT", "WIFI_OFF"):
                if status == "ok":
                    QMessageBox.information(self, "Berhasil", f"Perintah {action} berhasil dijalankan ESP32.")
                else:
                    msg = data.get("message", "Terjadi kesalahan jaringan.")
                    QMessageBox.warning(self, "Gagal", f"Perangkat gagal memproses perintah {action}:\n{msg}")

            # Threshold / config ACK: samakan field yang dibaca GUI dengan
            # field yang dipakai firmware (threshold, thresholds, thresholds_count).
            if action in ("SET_THRESHOLD", "SET_THRESHOLDS", "SET_CONFIG", "GET_CONFIG") and status == "ok":
                ack_thresholds = data.get("thresholds")
                if isinstance(ack_thresholds, list):
                    normalized = []
                    for th in ack_thresholds:
                        norm = self._normalize_threshold_record(th)
                        if norm:
                            normalized.append(norm)
                    if normalized:
                        self.config["thresholds"] = normalized
                        self.refresh_threshold_table()

                ack_threshold = data.get("threshold")
                if isinstance(ack_threshold, dict):
                    norm = self._normalize_threshold_record(ack_threshold)
                    if norm:
                        replaced = False
                        for i, th in enumerate(self.thresholds):
                            if th.get("id") == norm.get("id"):
                                self.thresholds[i] = norm
                                replaced = True
                                break
                        if not replaced and action == "SET_THRESHOLD":
                            self.thresholds.append(norm)
                        self.persist_config()
                        self.refresh_threshold_table()

                if isinstance(data.get("thresholds_count"), int):
                    self.lbl_device_config.setText(
                        f"Tersimpan di flash device — SSID auto-reconnect: <b>{html.escape(str(self.config.get('device', {}).get('wifi_ssid', '(belum ada SSID tersimpan)')))}</b> | "
                        f"Mode default: <b>{html.escape(str(self.config.get('device', {}).get('mode', '--')))}</b> | "
                        f"Threshold tersimpan: <b>{data['thresholds_count']}</b>"
                    )

            # Setelah file berhasil dihapus, refresh otomatis daftar file
            # supaya tabel langsung update tanpa perlu klik Refresh manual.
            # Memakai refresh_sd_listing() (bukan LIST_LOGS polos) supaya
            # path folder yang sedang dibuka tetap sama, bukan balik ke root.
            if action == "DELETE_FILE":
                if status == "ok":
                    self.refresh_sd_listing()
                else:
                    msg = data.get("message", "Terjadi kesalahan.")
                    QMessageBox.warning(self, "Gagal Menghapus", f"Perangkat gagal menghapus file:\n{msg}")

            if action == "GET_FILE" and status != "ok":
                msg = data.get("message", "Terjadi kesalahan.")
                QMessageBox.warning(self, "Gagal Download", f"Perangkat gagal mengirim file:\n{msg}")

        self.lbl_ack.setText(f"ACK\n{cmd}: {status}")
        self.lbl_ack.setStyleSheet(
            "background-color:#d2f8d2;border:1px solid #2ecc71;"
            "border-radius:6px;padding:8px 14px;font-weight:600;"
        )
        QTimer.singleShot(800, lambda: self.lbl_ack.setStyleSheet(""))

        message = data.get("message", "")
        self.log_terminal("ACK", f"cmd={cmd} id={cid} status={status} {message}", "#27ae60")

    def _update_heartbeat(self):
        self.hb_count += 1
        self.last_hb_time = time.strftime("%H:%M:%S")
        self.lbl_heartbeat.setText(f"Heartbeat\n#{self.hb_count} ({self.last_hb_time})")
        self.lbl_heartbeat.setStyleSheet(
            "background-color:#b9f6ca;border:1px solid #2ecc71;"
            "border-radius:6px;padding:8px 14px;font-weight:600;"
        )
        QTimer.singleShot(200, self._reset_heartbeat_style)

    def _reset_heartbeat_style(self):
        if hasattr(self, "lbl_heartbeat"):
            self.lbl_heartbeat.setStyleSheet("")

    @staticmethod
    def _resolve_payload_value(data, key):
        """
        Ambil nilai payload untuk `key`, mendukung dot-notation untuk field
        di dalam dict nested (mis. "wifi.rssi" -> data["wifi"]["rssi"]).
        Mengembalikan (value, found).
        """
        if key in data:
            return data[key], True
        if "." in key:
            cur = data
            for part in key.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return None, False
            return cur, True
        return None, False

    def _handle_telemetry(self, data):
        now = time.time() - self.start_time

        for cfg in self.sensor_config:
            if not isinstance(cfg, dict):
                continue
            key = cfg.get("key")
            if not key:
                continue
            value, found = self._resolve_payload_value(data, key)
            if not found:
                continue
            if key in self.sensor_labels:
                decimals = int(cfg.get("decimals", 1))
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    text = f"{value:.{decimals}f}"
                else:
                    text = str(value)
                unit = cfg.get("unit", "")
                self.sensor_labels[key].setText(
                    f"{cfg.get('label', key)}\n{text} {unit}".strip()
                )

            if (
                key in self.sensor_curves
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                self.sensor_x[key].append(now)
                self.sensor_y[key].append(value)
                self.sensor_curves[key].setData(
                    list(self.sensor_x[key]), list(self.sensor_y[key])
                )

        mode = data.get("mode")
        if mode is not None:
            display = {
                "always_on": "Always On",
                "deep_sleep": "Deep Sleep"
            }.get(str(mode), str(mode))
            self.lbl_mode.setText(f"Mode Daya\n{display}")
            self.lbl_current_mode.setText(f"Mode Saat Ini: {display}")
            self.config.setdefault("device", {})["mode"] = str(mode)

        if "sleep_sec" in data:
            try:
                sleep_sec = int(data["sleep_sec"])
                self.config.setdefault("device", {})["deep_sleep_sec"] = sleep_sec
                if hasattr(self, "sp_deep_sleep"):
                    self.sp_deep_sleep.blockSignals(True)
                    self.sp_deep_sleep.setValue(sleep_sec)
                    self.sp_deep_sleep.blockSignals(False)
            except (TypeError, ValueError):
                pass

        # Nested Wi-Fi payload support
        wifi_data = data.get("wifi")
        if isinstance(wifi_data, dict):
            wifi_conn = bool(wifi_data.get("connected", False))
            rssi = wifi_data.get("rssi")
            ssid = wifi_data.get("ssid", "")
            ip = wifi_data.get("ip", "")
            
            text = "Terhubung" if wifi_conn else "Terputus"
            if wifi_conn and ssid: text += f"\nSSID: {ssid}"
            if wifi_conn and rssi is not None: text += f"\nRSSI: {rssi} dBm"
            self.lbl_wifi.setText(f"WiFi\n{text}")

            # PERBAIKAN: sebelumnya "if ip:" -- kalau device disconnect,
            # firmware mengirim ip="" (falsy), jadi baris ini dilewati dan
            # label Alamat IP tetap menampilkan IP lama selamanya. Sekarang
            # selalu di-set sesuai status koneksi: ada IP kalau terhubung,
            # "--" kalau tidak.
            self.lbl_ip.setText(f"Alamat IP\n{ip if (wifi_conn and ip) else '--'}")
        # Flat fallback
        elif "w" in data:
            wifi = bool(data["w"])
            rssi = data.get("rssi")
            text = "Terhubung" if wifi else "Terputus"
            if wifi and rssi is not None:
                text += f"\n{rssi} dBm"
            self.lbl_wifi.setText(f"WiFi\n{text}")

        if "ip" in data and not isinstance(wifi_data, dict):
            self.lbl_ip.setText(f"Alamat IP\n{data['ip']}")

        if "sd_init" in data:
            ok = bool(data["sd_init"])
            self.lbl_sd_stat.setText(f"SD Card\n{'OK' if ok else 'ERROR'}")
            self.lbl_sd_detail.setText(
                f"Status SD Card: {'Terdeteksi & Normal' if ok else 'Gagal/Tidak Ada'}"
            )

        if "rtc_time" in data:
            self.lbl_time_rtc.setText(f"Waktu RTC Perangkat: {data['rtc_time']}")

        self.update_dashboard_info()

        if self.is_recording and self.csv_writer:
            self.write_dynamic_csv(data)

    # ---------------- Dynamic CSV ----------------
    def _get_graph_csv_widgets(self):
        widgets = []
        for cfg in self.sensor_config:
            if not isinstance(cfg, dict):
                continue
            key = str(cfg.get("key", "")).strip()
            if not key or not cfg.get("show_graph", True):
                continue
            widgets.append(cfg)
        return widgets

    def toggle_record_csv(self):
        if not self.is_recording:
            filepath, _ = QFileDialog.getSaveFileName(
                self, "Simpan File CSV", "", "CSV Files (*.csv)"
            )
            if not filepath:
                return

            try:
                self.csv_file = filepath
                self.csv_fh = open(filepath, "w", newline="", encoding="utf-8-sig")

                graph_widgets = self._get_graph_csv_widgets()
                self.csv_widget_keys = [cfg["key"] for cfg in graph_widgets]
                self.csv_widget_labels = [str(cfg.get("label", cfg["key"])) for cfg in graph_widgets]

                self.csv_writer = csv.writer(
                    self.csv_fh, delimiter=";", lineterminator="\n"
                )

                headers = [self.csv_timestamp_header, *self.csv_widget_labels]
                self.csv_writer.writerow(headers)
                self.csv_fh.flush()

                self.csv_interval_sec = self.sp_csv_interval.value()
                self._last_csv_write_ts = 0.0  # baris pertama langsung ditulis

                self.is_recording = True
                self.btn_record.setText("Stop Record CSV")
                self._set_button_role(self.btn_record, "btnDanger")

                widget_text = ", ".join(self.csv_widget_labels) if self.csv_widget_labels else "(tidak ada)"
                self.log_terminal(
                    "INFO",
                    f"Recording started: {filepath} ({widget_text}) | interval {self.csv_interval_sec}s",
                    "#16a085"
                )

            except Exception as exc:
                self._close_csv_file()
                QMessageBox.critical(self, "Error", f"Gagal membuka CSV: {exc}")

        else:
            self.is_recording = False
            self._close_csv_file()
            self.btn_record.setText("Start Record CSV")
            self._set_button_role(self.btn_record, "btnSuccess")
            QMessageBox.information(self, "Info", "Perekaman CSV dihentikan.")
            self.log_terminal("INFO", "Recording stopped.", "#16a085")

    def write_dynamic_csv(self, data):
        if not self.csv_writer or not self.csv_fh:
            return
        # PERBAIKAN: dulu setiap telemetri masuk (~1x/detik) langsung ditulis
        # sebagai baris baru, tanpa opsi mengatur jaraknya. Sekarang baris
        # baru hanya ditulis kalau sudah melewati csv_interval_sec sejak
        # baris terakhir -- telemetri lain di antaranya tetap dipakai untuk
        # update kartu/grafik seperti biasa, cuma tidak ikut direkam ke CSV.
        now = time.monotonic()
        if now - self._last_csv_write_ts < self.csv_interval_sec:
            return
        self._last_csv_write_ts = now
        try:
            timestamp_pc = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            row = [timestamp_pc]
            for key in self.csv_widget_keys:
                value, found = self._resolve_payload_value(data, key)
                row.append(value if found else "")
            self.csv_writer.writerow(row)
            self.csv_fh.flush()
        except Exception as exc:
            self.log_terminal("ERR", f"CSV Error: {exc}", "#c0392b") # Red

    def _close_csv_file(self):
        if self.csv_fh:
            try:
                self.csv_fh.close()
            except Exception:
                pass
        self.csv_fh = None
        self.csv_writer = None
        self.csv_widget_keys = []
        self.csv_widget_labels = []

    # ---------------- Threshold / Buzzer ----------------
    @staticmethod
    def _sensor_base_key(key):
        """Payload TELEMETRY sekarang nesting semua sensor di bawah
        "sensors": {...} (mis. path GUI "sensors.t"), TAPI firmware
        (payload_manager.py) tetap memakai key MENTAH tanpa prefix untuk
        kalibrasi (SET_CALIBRATION) dan label CSV (SET_SENSOR_LABELS) --
        keduanya diterapkan pada isi dict "sensors", bukan pada path
        top-level yang sudah di-nesting. Helper ini memetakan
        "sensors.t" -> "t"; key lain (mis. "wifi.rssi") dikembalikan
        apa adanya karena tidak relevan untuk kalibrasi/label CSV."""
        if key.startswith("sensors."):
            return key.split(".", 1)[1]
        return key

    def get_payload_keys(self, numeric_only=False):
        keys = set(self.payload_registry.keys())
        keys.update(
            cfg.get("key") for cfg in self.sensor_config
            if isinstance(cfg, dict) and cfg.get("key")
        )
        if numeric_only:
            # KNOWN_NUMERIC_PAYLOAD_KEYS masuk tanpa syarat (statis, sesuai
            # skema firmware saat ini) -- key lain (mis. widget custom yang
            # ditambah user) tetap difilter lewat data live supaya key
            # non-numerik tidak nyasar ke dropdown Threshold.
            keys.update(KNOWN_NUMERIC_PAYLOAD_KEYS)
            keys = {
                k for k in keys
                if k in KNOWN_NUMERIC_PAYLOAD_KEYS
                or (
                    k in self.latest_payload
                    and isinstance(self.latest_payload[k], (int, float))
                    and not isinstance(self.latest_payload[k], bool)
                )
            }
        return sorted(keys)

    def next_threshold_id(self):
        return max([int(t.get("id", 0)) for t in self.thresholds] + [0]) + 1

    def refresh_threshold_table(self):
        self.table_threshold.setRowCount(0)
        migrated = False

        for threshold in self.thresholds:
            normalized = self._normalize_threshold_record(threshold)
            if not normalized:
                continue

            row = self.table_threshold.rowCount()
            self.table_threshold.insertRow(row)

            if normalized != threshold:
                migrated = True

            values = [
                normalized.get("id", ""),
                normalized.get("payload", ""),
                normalized.get("operator", ">"),
                normalized.get("value", ""),
                normalized.get("buzzer", 1),
                f"{max(1, (int(normalized.get('interval_sec', 300)) + 59) // 60)} menit",
                "Yes" if normalized.get("enabled", True) else "No",
            ]
            for col, value in enumerate(values):
                self.table_threshold.setItem(
                    row, col, QTableWidgetItem(str(value))
                )

            btn = QPushButton("Kirim")
            btn.clicked.connect(
                lambda _, tid=normalized.get("id"): self.send_threshold_by_id(tid)
            )
            self.table_threshold.setCellWidget(row, 7, btn)

        if migrated:
            self.thresholds[:] = [
                self._normalize_threshold_record(th)
                for th in self.thresholds
                if self._normalize_threshold_record(th)
            ]
            self.persist_config()

    def add_threshold(self):
        dialog = ThresholdDialog(
            self, payload_keys=self.get_payload_keys(numeric_only=True)
        )
        if dialog.exec_() == QDialog.Accepted:
            threshold = self._normalize_threshold_record(dialog.get_threshold())
            if not threshold:
                QMessageBox.warning(self, "Peringatan", "Payload threshold tidak boleh kosong.")
                return
            threshold["id"] = self.next_threshold_id()
            self.thresholds.append(threshold)
            self.persist_config()
            self.refresh_threshold_table()

    def edit_threshold(self):
        row = self.table_threshold.currentRow()
        if row < 0 or row >= len(self.thresholds):
            QMessageBox.warning(self, "Peringatan", "Pilih threshold terlebih dahulu.")
            return

        threshold = self.thresholds[row]
        dialog = ThresholdDialog(
            self,
            payload_keys=self.get_payload_keys(numeric_only=True),
            threshold=threshold,
        )
        if dialog.exec_() == QDialog.Accepted:
            updated = self._normalize_threshold_record(dialog.get_threshold())
            if not updated:
                QMessageBox.warning(self, "Peringatan", "Payload threshold tidak boleh kosong.")
                return
            updated["id"] = threshold.get("id", self.next_threshold_id())
            self.thresholds[row] = updated
            self.persist_config()
            self.refresh_threshold_table()

    def delete_threshold(self):
        row = self.table_threshold.currentRow()
        if row < 0:
            return
        if QMessageBox.question(
            self, "Konfirmasi", "Hapus threshold yang dipilih?"
        ) == QMessageBox.Yes:
            self.thresholds.pop(row)
            self.persist_config()
            self.refresh_threshold_table()

    def send_threshold_by_id(self, threshold_id):
        threshold = next((t for t in self.thresholds if t.get("id") == threshold_id), None)
        if threshold:
            self.send_json_command({
                "cmd": "SET_THRESHOLD",
                "threshold": self._normalize_threshold_record(threshold),
            })

    def sync_all_thresholds(self):
        self.send_json_command({
            "cmd": "SET_THRESHOLDS",
            "thresholds": [
                self._normalize_threshold_record(th)
                for th in self.thresholds
                if self._normalize_threshold_record(th)
            ],
        })

    def test_buzzer(self):
        pattern = int(self.cb_buzzer_test.currentData())
        self.send_json_command({
            "cmd": "BUZZER_TEST",
            "pattern": pattern,
        })

    # ---------------- Dashboard Designer ----------------
    def refresh_widgets_ui(self):
        self.table_widgets.setRowCount(0)

        for idx, cfg in enumerate(self.sensor_config, start=1):
            if not isinstance(cfg, dict):
                continue
            key = str(cfg.get("key", "")).strip()
            if not key:
                continue

            row = self.table_widgets.rowCount()
            self.table_widgets.insertRow(row)

            values = [
                idx,
                key,
                cfg.get("label", key),
                cfg.get("unit", ""),
                cfg.get("decimals", "1"),
                "Yes" if cfg.get("show_graph", True) else "No",
            ]

            for col, value in enumerate(values):
                self.table_widgets.setItem(
                    row, col, QTableWidgetItem(str(value))
                )

        self.table_widgets.resizeRowsToContents()

    def refresh_payload_registry_ui(self):
        """
        Refresh LENGKAP: daftar Widget Dashboard + tabel Payload Registry.
        Dipakai setelah operasi tambah/edit/hapus/pindah widget -- BUKAN
        dipanggil tiap payload masuk (lihat _update_payload_registry_table),
        supaya seleksi baris di tabel Widget Dashboard tidak ter-reset tiap
        detik oleh telemetri yang masuk.
        """
        self.refresh_widgets_ui()
        self._update_payload_registry_table()

    def _update_payload_registry_table(self):
        """
        PERBAIKAN: sebelumnya dipanggil lewat refresh_payload_registry_ui()
        yang JUGA merombak total table_widgets (Dashboard Designer) tiap
        payload masuk (~1x/detik) -- akibatnya baris yang sedang dipilih di
        situ selalu ter-reset, sehingga tombol Edit/Hapus terasa "tidak bisa
        dipilih". Method ini HANYA mengurus tabel Payload Registry
        (nilai real-time), aman dipanggil sesering apa pun.

        PERBAIKAN 2: setRowCount(0) + rebuild penuh di bawah ini JUGA
        menghapus seleksi baris tiap kali dipanggil (sama seperti masalah
        yang sudah diperbaiki di atas untuk table_widgets) -- akibatnya
        tombol "Edit Label CSV" tidak sempat diklik karena baris terpilih
        selalu ter-reset tiap ~1 detik oleh telemetri berikutnya. Fix:
        simpan KEY yang sedang dipilih (bukan nomor baris, karena urutan
        alfabetis bisa berubah kalau ada key baru muncul), lalu cari &
        pilih ulang baris dengan key yang sama setelah rebuild.
        """
        current_row = self.table_payload.currentRow()
        selected_key = None
        if current_row >= 0:
            item = self.table_payload.item(current_row, 0)
            if item is not None:
                selected_key = item.text()

        self.table_payload.setRowCount(0)
        restore_row = -1
        for key in sorted(self.payload_registry):
            info = self.payload_registry[key]
            row = self.table_payload.rowCount()
            self.table_payload.insertRow(row)
            self.table_payload.setItem(row, 0, QTableWidgetItem(key))
            self.table_payload.setItem(row, 1, QTableWidgetItem(info["type"]))
            self.table_payload.setItem(row, 2, QTableWidgetItem(str(info["last"])))

            used = any(
                isinstance(cfg, dict) and cfg.get("key") == key
                for cfg in self.sensor_config
            )
            self.table_payload.setItem(
                row, 3, QTableWidgetItem("Yes" if used else "No")
            )

            label = self.config.get("sensor_labels", {}).get(self._sensor_base_key(key), key)
            self.table_payload.setItem(row, 4, QTableWidgetItem(str(label)))

            if key == selected_key:
                restore_row = row

        if restore_row >= 0:
            self.table_payload.selectRow(restore_row)

        self.update_dashboard_info()

    def edit_sensor_label(self):
        """Edit label CSV (nama kolom header SD Card) untuk key payload yang
        dipilih di tabel Payload Registry -- lepas dari apakah key itu
        dipakai sebagai Widget Dashboard atau tidak. Disimpan lokal dulu
        (self.config['sensor_labels']); baru dikirim ke device lewat
        tombol 'Kirim Label ke Device' (command SET_SENSOR_LABELS)."""
        row = self.table_payload.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Info", "Pilih dulu salah satu baris payload key di tabel."
            )
            return
        key_item = self.table_payload.item(row, 0)
        if key_item is None:
            return
        key = key_item.text()
        csv_key = self._sensor_base_key(key)

        current_label = self.config.get("sensor_labels", {}).get(csv_key, csv_key)
        new_label, ok = QInputDialog.getText(
            self, "Edit Label CSV",
            f"Label kolom CSV untuk payload key \"{key}\":",
            text=current_label
        )
        if not ok:
            return
        new_label = new_label.strip()
        if not new_label:
            QMessageBox.warning(self, "Peringatan", "Label tidak boleh kosong.")
            return

        self.config.setdefault("sensor_labels", {})[csv_key] = new_label
        self.persist_config()
        self._update_payload_registry_table()

    def sync_sensor_labels(self):
        """Kirim semua label CSV yang tersimpan lokal ke device (flash)
        lewat command SET_SENSOR_LABELS. Kalau belum pernah diedit sama
        sekali, tetap boleh dikirim kosong -- firmware akan tetap pakai
        default bawaannya sendiri."""
        labels = self.config.get("sensor_labels", {})
        self.send_json_command({"cmd": "SET_SENSOR_LABELS", "labels": labels})

    def add_dashboard_widget(self):
        dialog = SensorConfigDialog(
            self, payload_keys=self.get_payload_keys(numeric_only=False)
        )
        if dialog.exec_() == QDialog.Accepted:
            config = dialog.get_config()
            if not config["key"]:
                return
            if any(c.get("key") == config["key"] for c in self.sensor_config):
                QMessageBox.warning(
                    self, "Peringatan",
                    "Payload key tersebut sudah digunakan oleh widget lain."
                )
                return
            self.sensor_config.append(config)
            self.persist_config()
            self._rebuild_sensor_cards()
            self._rebuild_sensor_curves()
            self.refresh_payload_registry_ui()
            self.table_widgets.selectRow(len(self.sensor_config) - 1)

    def edit_dashboard_widget(self):
        row = self.table_widgets.currentRow()
        if row < 0 or row >= len(self.sensor_config):
            QMessageBox.warning(self, "Peringatan", "Pilih widget pada daftar Widget Dashboard.")
            return

        old = self.sensor_config[row]
        dialog = SensorConfigDialog(
            self,
            config=old,
            payload_keys=self.get_payload_keys(numeric_only=False)
        )
        if dialog.exec_() == QDialog.Accepted:
            new_cfg = dialog.get_config()
            if not new_cfg["key"]:
                return
            for i, cfg in enumerate(self.sensor_config):
                if i != row and cfg.get("key") == new_cfg["key"]:
                    QMessageBox.warning(
                        self, "Peringatan",
                        "Payload key tersebut sudah digunakan oleh widget lain."
                    )
                    return
            self.sensor_config[row] = new_cfg
            self.persist_config()
            self._rebuild_sensor_cards()
            self._rebuild_sensor_curves()
            self.refresh_payload_registry_ui()
            self.table_widgets.selectRow(row)

    def delete_dashboard_widget(self):
        row = self.table_widgets.currentRow()
        if row < 0 or row >= len(self.sensor_config):
            return
        key = self.sensor_config[row].get("key", "")
        if QMessageBox.question(
            self, "Konfirmasi",
            f"Hapus widget '{key}' dari dashboard?"
        ) == QMessageBox.Yes:
            self.sensor_config.pop(row)
            self.persist_config()
            self._rebuild_sensor_cards()
            self._rebuild_sensor_curves()
            self.refresh_payload_registry_ui()

    def move_widget(self, direction):
        row = self.table_widgets.currentRow()
        target = row + direction
        if row < 0 or target < 0 or target >= len(self.sensor_config):
            return
        self.sensor_config[row], self.sensor_config[target] = (
            self.sensor_config[target], self.sensor_config[row]
        )
        self.persist_config()
        self._rebuild_sensor_cards()
        self._rebuild_sensor_curves()
        self.refresh_payload_registry_ui()
        self.table_widgets.selectRow(target)

    def save_dashboard_config(self):
        self.persist_config()
        QMessageBox.information(
            self, "Info",
            f"Konfigurasi perangkat berhasil disimpan:\n{CONFIG_PATH}"
        )

    def update_dashboard_info(self):
        self.lbl_dashboard_info.setText(
            f"Widget aktif: {len(self.sensor_config)} | "
            f"Payload terdeteksi: {len(self.payload_registry)} | "
            f"Threshold: {len(self.thresholds)} | "
            f"Buzzer Pattern: 1–{BUZZER_PATTERN_COUNT} | "
            f"Config: {os.path.basename(CONFIG_PATH)} | "
            f"Deep Sleep: {self.config.get('device', {}).get('deep_sleep_sec', 60)} detik"
        )

    # ---------------- RC1 Wi-Fi / Power ----------------
    def _handle_scan_start(self, data):
        """Awal hasil scan WiFi ber-tahap (SCAN_START -> beberapa SCAN_ITEM -> SCAN_END)."""
        cid = data.get("id")
        self._touch_pending_command(cid)
        self.wifi_scans[cid] = {"items": [], "expected": data.get("count", 0)}
        self.table_wifi_scan.setRowCount(0)

    def _handle_scan_item(self, data):
        """Satu SSID hasil scan. Dikirim satu-per-satu supaya kalau ada satu
        pesan yang korup di jalur serial, cuma SSID itu yang hilang -- bukan
        seluruh hasil scan seperti pada protokol lama (satu array besar)."""
        cid = data.get("id")
        self._touch_pending_command(cid)

        ssid = str(data.get("ssid", "")).strip()
        if not ssid:
            return

        state = self.wifi_scans.setdefault(cid, {"items": [], "expected": 0})
        state["items"].append({"ssid": ssid, "rssi": data.get("rssi", "")})

    def _handle_scan_end(self, data):
        """Akhir hasil scan: render semua item yang berhasil diterima ke tabel,
        dan beri tahu pengguna secara eksplisit kalau ada yang hilang di jalan
        (dibanding count asli dari firmware) supaya tidak dikira tabel kosong
        tanpa sebab."""
        cid = data.get("id")
        self._touch_pending_command(cid)

        state = self.wifi_scans.pop(cid, None)
        items = state["items"] if state else []
        self._populate_wifi_scan_table(items)

        expected = data.get("count")
        if expected is not None and len(items) < expected:
            self.log_terminal(
                "ERR",
                f"Hasil scan WiFi tidak lengkap: {len(items)}/{expected} jaringan diterima "
                "(sebagian pesan kemungkinan korup di jalur serial).",
                "#c0392b"
            )

    def _populate_wifi_scan_table(self, networks):
        self.table_wifi_scan.setRowCount(0)
        if not isinstance(networks, list):
            return

        for network in networks:
            if not isinstance(network, dict):
                continue
            ssid = str(network.get("ssid", "")).strip()
            if not ssid:
                continue
            rssi = network.get("rssi", "")

            row = self.table_wifi_scan.rowCount()
            self.table_wifi_scan.insertRow(row)

            self.table_wifi_scan.setItem(row, 0, QTableWidgetItem(ssid))
            self.table_wifi_scan.setItem(row, 1, QTableWidgetItem(str(rssi)))

            btn_use = QPushButton("Gunakan")
            btn_use.clicked.connect(
                lambda _, value=ssid: self.txt_ssid.setText(value)
            )
            self.table_wifi_scan.setCellWidget(row, 2, btn_use)

    def save_deep_sleep_setting(self, value):
        self.config.setdefault("device", {})["deep_sleep_sec"] = int(value)
        self.persist_config()

    def set_always_on_mode(self):
        self.config.setdefault("device", {})["mode"] = "always_on"
        self.persist_config()
        self.send_json_command({
            "cmd": "SET_MODE",
            "mode": "always_on",
        })

    def set_deep_sleep_mode(self):
        seconds = int(self.sp_deep_sleep.value())
        self.config.setdefault("device", {})["mode"] = "deep_sleep"
        self.config.setdefault("device", {})["deep_sleep_sec"] = seconds
        self.persist_config()
        self.send_json_command({
            "cmd": "SET_MODE",
            "mode": "deep_sleep",
            "deep_sleep_sec": seconds,
        })

    def reset_device_action(self):
        reply = QMessageBox.question(
            self, "Konfirmasi Reset",
            "Perangkat akan restart (machine.reset()).\n"
            "Koneksi serial akan terputus sesaat dan tersambung ulang setelah boot.\n\n"
            "Lanjutkan?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.send_json_command({"cmd": "RESET"})

    # ---------------- Misc ----------------
    def connect_wifi_action(self):
        ssid = self.txt_ssid.text().strip()
        pwd = self.txt_pass.text()
        if not ssid:
            QMessageBox.warning(self, "Peringatan", "SSID tidak boleh kosong.")
            return
        self.send_json_command({
            "cmd": "WIFI_CONNECT",
            "ssid": ssid,
            "password": pwd,
        }, ui_button=self.btn_connect_wifi)

    def disconnect_wifi_action(self):
        self.send_json_command({"cmd": "WIFI_OFF"}, ui_button=self.btn_disconnect)

    def sync_rtc_pc_action(self):
        self.send_json_command({
            "cmd": "SET_RTC",
            "timestamp": int(time.time()),
        })

    def _handle_device_config(self, data):
        """Menampilkan config yang dibalas firmware atas GET_CONFIG.

        Bentuk payload yang diharapkan:
        {"type": "CONFIG", "wifi_ssid": "...", "mode": "...", "thresholds": [...]}
        """
        ssid = data.get("wifi_ssid", "(belum ada SSID tersimpan)")
        mode = data.get("mode", "--")
        thresholds = data.get("thresholds", [])
        normalized = []
        if isinstance(thresholds, list):
            for th in thresholds:
                norm = self._normalize_threshold_record(th)
                if norm:
                    normalized.append(norm)
        n_thresh = len(normalized)

        if normalized:
            self.config["thresholds"] = normalized
            self.refresh_threshold_table()

        if "wifi_ssid" in data:
            self.config.setdefault("device", {})["wifi_ssid"] = str(ssid)
        if "mode" in data:
            self.config.setdefault("device", {})["mode"] = str(mode)

        # Sinkronkan interval deep sleep dari GET_CONFIG ke config lokal
        # dan spinbox GUI. Firmware menggunakan key resmi "deep_sleep_sec".
        # blockSignals mencegah perubahan dari device memicu handler
        # perubahan nilai GUI secara tidak sengaja.
        if "deep_sleep_sec" in data:
            try:
                deep_sleep_sec = int(data["deep_sleep_sec"])
                self.config.setdefault("device", {})["deep_sleep_sec"] = deep_sleep_sec
                if hasattr(self, "sp_deep_sleep"):
                    self.sp_deep_sleep.blockSignals(True)
                    self.sp_deep_sleep.setValue(deep_sleep_sec)
                    self.sp_deep_sleep.blockSignals(False)
            except (TypeError, ValueError):
                pass

        logging_cfg = data.get("logging")
        if isinstance(logging_cfg, dict):
            self.config["logging"] = logging_cfg
            self.chk_data_enabled.setChecked(bool(logging_cfg.get("data_enabled", True)))
            self.sp_data_interval.setValue(int(logging_cfg.get("data_interval_sec", 60)))
            self.sp_data_retention.setValue(int(logging_cfg.get("data_retention_days", 7)))
            self.chk_system_enabled.setChecked(bool(logging_cfg.get("system_enabled", True)))
            self.sp_system_retention.setValue(int(logging_cfg.get("system_retention_days", 30)))

        sensor_labels = data.get("sensor_labels")
        if isinstance(sensor_labels, dict):
            self.config["sensor_labels"] = dict(sensor_labels)
            self._update_payload_registry_table()

        calibration = data.get("calibration")
        if isinstance(calibration, dict):
            self.config["calibration"] = dict(calibration)
            self._update_calibration_table()

        # Titik mentah kalibrasi (raw->ref) -- device cuma menitipkannya
        # (tidak pernah memprosesnya), jadi kalau ada di respons GET_CONFIG
        # berarti pernah dikirim dari suatu PC lewat SET_CALIBRATION. Ini
        # jaring pengaman utama saat device dipindah ke PC yang belum
        # punya cache lokal SN ini (lihat _handle_identity).
        calibration_points = data.get("calibration_points")
        if isinstance(calibration_points, dict):
            self.config["calibration_points"] = dict(calibration_points)
        if isinstance(calibration, dict) or isinstance(calibration_points, dict):
            if self._active_device_sn:
                self._snapshot_calibration_into_profile(self._active_device_sn)
            self.persist_config()

        udaraku_cfg = data.get("udaraku")
        if isinstance(udaraku_cfg, dict):
            self.config["udaraku"] = udaraku_cfg
            self._load_udaraku_controls_from_config()

        display_cfg = data.get("display")
        if isinstance(display_cfg, dict):
            self.config["display"] = display_cfg
            if hasattr(self, "sp_display_interval"):
                self.sp_display_interval.blockSignals(True)
                self.sp_display_interval.setValue(int(display_cfg.get("update_interval_sec", 60)))
                self.sp_display_interval.blockSignals(False)
            if hasattr(self, "sp_display_full_refresh"):
                self.sp_display_full_refresh.blockSignals(True)
                self.sp_display_full_refresh.setValue(int(display_cfg.get("full_refresh_interval_min", 30)))
                self.sp_display_full_refresh.blockSignals(False)
        self.lbl_device_config.setText(
            f"Tersimpan di flash device — SSID auto-reconnect: <b>{html.escape(str(ssid))}</b> | "
            f"Mode default: <b>{html.escape(str(mode))}</b> | "
            f"Threshold tersimpan: <b>{n_thresh}</b>"
        )
        self.log_terminal("INFO", "Config device berhasil dimuat dari flash.", "#16a085")

    def push_device_config(self, ui_button=None):
        """Kirim config gabungan (WiFi + mode + threshold) untuk disimpan
        firmware ke flash -- dipakai untuk auto-reconnect & threshold
        persisten setelah reboot. Field WiFi diambil dari input SSID/password
        di tab ini kalau diisi; kalau kosong, firmware diharapkan tetap
        mempertahankan SSID yang sudah tersimpan sebelumnya (tidak menimpa
        dengan string kosong) -- ini perlu dipastikan lagi di implementasi
        firmware sesi berikutnya.
        """
        ssid = self.txt_ssid.text().strip()
        pwd = self.txt_pass.text()
        normalized_thresholds = []
        for th in self.thresholds:
            norm = self._normalize_threshold_record(th)
            if norm:
                normalized_thresholds.append(norm)

        config_payload = {
            "mode": self.config.get("device", {}).get("mode", "always_on"),
            "thresholds": normalized_thresholds,
        }
        if ssid:
            config_payload["wifi_ssid"] = ssid
            config_payload["wifi_password"] = pwd
        self.send_json_command(
            {"cmd": "SET_CONFIG", "config": config_payload}, ui_button=ui_button
        )

    def _load_logging_controls_from_config(self):
        """Isi kontrol Tab 3 dari config PC yang tersimpan lokal (sebelum
        pernah GET_CONFIG dari device)."""
        logging_cfg = self.config.get("logging", {})
        self.chk_data_enabled.setChecked(bool(logging_cfg.get("data_enabled", True)))
        self.sp_data_interval.setValue(int(logging_cfg.get("data_interval_sec", 60)))
        self.sp_data_retention.setValue(int(logging_cfg.get("data_retention_days", 7)))
        self.chk_system_enabled.setChecked(bool(logging_cfg.get("system_enabled", True)))
        self.sp_system_retention.setValue(int(logging_cfg.get("system_retention_days", 30)))

    def sync_logging_config(self, ui_button=None):
        """Kirim konfigurasi Data Logger & System Logger (Tab 3) ke ESP32
        untuk disimpan ke flash lewat command SET_LOGGING_CONFIG."""
        logging_payload = {
            "data_enabled": self.chk_data_enabled.isChecked(),
            "data_interval_sec": self.sp_data_interval.value(),
            "data_retention_days": self.sp_data_retention.value(),
            "system_enabled": self.chk_system_enabled.isChecked(),
            "system_retention_days": self.sp_system_retention.value(),
        }
        self.config["logging"] = logging_payload
        self.persist_config()
        self.send_json_command(
            {"cmd": "SET_LOGGING_CONFIG", "logging": logging_payload}, ui_button=ui_button
        )

    def sync_display_config(self, ui_button=None):
        """Kirim timer refresh e-paper (partial update interval & full
        refresh interval) ke ESP32 untuk disimpan ke flash lewat command
        SET_DISPLAY_CONFIG, dan diterapkan live tanpa perlu reboot."""
        display_payload = {
            "update_interval_sec": self.sp_display_interval.value(),
            "full_refresh_interval_min": self.sp_display_full_refresh.value(),
        }
        self.config["display"] = display_payload
        self.persist_config()
        self.send_json_command(
            {"cmd": "SET_DISPLAY_CONFIG", "display": display_payload}, ui_button=ui_button
        )

    def _populate_file_table(self, files):
        self.table_files.setRowCount(0)
        for entry in files:
            # PERBAIKAN: firmware sekarang mengirim tiap entri sebagai dict
            # {"name":..., "size":..., "dir":...} supaya ukuran file bisa
            # ditampilkan. Tetap dukung format lama (string nama saja) kalau
            # firmware belum di-update, supaya GUI tidak error.
            if isinstance(entry, dict):
                filename = str(entry.get("name", ""))
                size = entry.get("size")
                is_dir = bool(entry.get("dir"))
            else:
                filename = str(entry)
                size = None
                is_dir = False

            if not filename:
                continue

            row = self.table_files.rowCount()
            self.table_files.insertRow(row)
            self.table_files.setItem(row, 0, QTableWidgetItem(filename))

            size_text = "Folder" if is_dir else (format_file_size(size) if size is not None else "--")
            item_size = QTableWidgetItem(size_text)
            item_size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table_files.setItem(row, 1, item_size)

            action_widget = QWidget()
            h = QHBoxLayout(action_widget)
            h.setContentsMargins(0, 0, 0, 0)

            if is_dir:
                # Folder: tombol "Buka" untuk masuk ke dalamnya (sama seperti
                # double-click baris), tidak ada Download/Delete untuk folder
                # sistem seperti "System Volume Information" supaya aman.
                bo = QPushButton("Buka")
                bo.clicked.connect(lambda _, f=filename: self.open_sd_folder(f))
                h.addWidget(bo)
            else:
                bd = QPushButton("Download")
                bd.clicked.connect(
                    lambda _, f=filename, b=bd: self.send_json_command({
                        "cmd": "GET_FILE", "filename": self._sd_join(self.sd_current_path, f)
                    }, ui_button=b)
                )
                bx = QPushButton("Delete")
                bx.clicked.connect(lambda _, f=filename: self.delete_log_file(f))
                h.addWidget(bd)
                h.addWidget(bx)
            self.table_files.setCellWidget(row, 2, action_widget)

    def _sd_join(self, path, name):
        """Gabungkan path folder saat ini dengan nama file/folder, hasil path
        relatif tanpa leading slash (mis. "logs_csv/2026-07-27-data.csv")."""
        path = (path or "").strip("/")
        name = (name or "").strip("/")
        if not path:
            return name
        if not name:
            return path
        return f"{path}/{name}"

    def _sd_parent(self, path):
        """Hitung path folder induk. Root ("") tetap root."""
        path = (path or "").strip("/")
        if "/" not in path:
            return ""
        return path.rsplit("/", 1)[0]

    def _update_sd_breadcrumb(self):
        display = self.sd_current_path.strip("/")
        self.lbl_sd_breadcrumb.setText(f"📁 /{display}" if display else "📁 /")
        self.btn_sd_up.setEnabled(bool(display))

    def refresh_sd_listing(self, ui_button=None):
        """Minta daftar isi folder SD Card saat ini (self.sd_current_path) ke firmware."""
        self._update_sd_breadcrumb()
        self.send_json_command(
            {"cmd": "LIST_LOGS", "path": self.sd_current_path}, ui_button=ui_button
        )

    def open_sd_folder(self, folder_name):
        """Masuk ke subfolder (dipanggil dari tombol 'Buka' atau double-click baris folder)."""
        self.sd_current_path = self._sd_join(self.sd_current_path, folder_name)
        self.refresh_sd_listing()

    def go_sd_parent(self):
        """Naik ke folder induk."""
        self.sd_current_path = self._sd_parent(self.sd_current_path)
        self.refresh_sd_listing()

    def _on_sd_row_double_clicked(self, row, _column):
        item = self.table_files.item(row, 1)
        if item is not None and item.text() == "Folder":
            name_item = self.table_files.item(row, 0)
            if name_item is not None:
                self.open_sd_folder(name_item.text())

    def _touch_pending_command(self, cid):
        """
        Reset jam timeout ACK untuk command id tertentu. Dipanggil setiap kali
        ada progress (FILE_START/FILE_CHUNK/FILE_END) untuk download yang
        sedang berjalan, supaya check_pending_commands() tidak menganggapnya
        timeout selama data masih terus mengalir dari ESP32 -- ini yang
        memperbaiki kasus file besar sebelumnya "gagal/timeout" padahal
        firmware sebenarnya masih mengirim.
        """
        if cid is not None and cid in self.pending_commands:
            self.pending_commands[cid]["sent"] = time.time()

    def _handle_file_start(self, data):
        """
        Awal transfer file ber-chunk (balasan atas GET_FILE).

        PERBAIKAN: sebelumnya dialog "Simpan File" langsung dibuka di sini
        dan file ditulis ke disk per-chunk begitu diterima. Masalahnya,
        dialog simpan itu MODAL -- selama menunggu user memilih lokasi,
        chunk yang keburu datang dari ESP32 dibuang begitu saja (state
        penyimpanannya belum ada). Untuk file kecil, seluruh transfer bisa
        selesai SEBELUM user sempat klik "Save", sehingga hasil akhirnya
        0 bytes walau ACK-nya "ok". Sekarang isi file ditampung dulu di
        memori sampai FILE_END, baru dialog simpan dibuka dan file ditulis
        sekali jalan -- tidak ada lagi celah kehilangan chunk.
        """
        cid = data.get("id")
        self._touch_pending_command(cid)

        filename = str(data.get("filename", "downloaded_file.txt"))
        size = data.get("size", 0)

        self.file_downloads[cid] = {
            "filename": filename,
            "size": size,
            "chunks": [],
            "received_bytes": 0,
            # PERBAIKAN: lacak potongan yang gagal checksum ("cks") supaya
            # file yang korup di jalur serial tidak diam-diam disimpan
            # seolah-olah utuh (lihat catatan perbaikan di firmware,
            # FILE_CHUNK_SIZE, soal akar masalahnya).
            "bad_seqs": [],
            "cks_sum": 0,
        }
        self.lbl_ack.setText(f"Download\n{filename} 0%")

        size_text = format_file_size(size) if size else "?"
        self.lbl_sd_progress.setText(f"Mengunduh '{filename}' (0 B / {size_text})...")
        self.progress_sd_download.setRange(0, 100 if size else 0)
        self.progress_sd_download.setValue(0)

    @staticmethod
    def _checksum16(text):
        """Checksum 16-bit sederhana (sum-of-bytes mod 65536), harus sama
        persis dengan _checksum16() di firmware (main.py) supaya tiap chunk
        bisa diverifikasi begitu diterima."""
        total = 0
        for b in text.encode("utf-8", errors="ignore"):
            total = (total + b) & 0xFFFF
        return total

    def _handle_file_chunk(self, data):
        """Tampung satu potongan isi file di memori (belum ditulis ke disk),
        dan verifikasi checksum-nya kalau firmware menyertakannya."""
        cid = data.get("id")
        self._touch_pending_command(cid)

        state = self.file_downloads.get(cid)
        if not state:
            return

        chunk = str(data.get("data", ""))
        seq = data.get("seq")
        state["chunks"].append(chunk)
        state["received_bytes"] += len(chunk.encode("utf-8", errors="ignore"))

        # PERBAIKAN: verifikasi checksum tiap chunk begitu diterima. Kalau
        # firmware tidak menyertakan "cks" (mis. firmware lama), lewati
        # validasi ini secara diam-diam (backward compatible).
        expected_cks = data.get("cks")
        if expected_cks is not None:
            actual_cks = self._checksum16(chunk)
            state["cks_sum"] = (state.get("cks_sum", 0) + actual_cks) & 0xFFFF
            if actual_cks != expected_cks:
                state["bad_seqs"].append(seq)
                self.log_terminal(
                    "ERR",
                    f"Chunk #{seq} file '{state['filename']}' gagal verifikasi checksum "
                    f"(kemungkinan korup di jalur serial).",
                    "#c0392b"
                )

        size = state.get("size") or 0
        received = state["received_bytes"]
        size_text = format_file_size(size) if size else "?"
        received_text = format_file_size(received)

        if size:
            pct = min(100, int(received * 100 / size))
            self.lbl_ack.setText(f"Download\n{state['filename']} {pct}%")
            self.progress_sd_download.setValue(pct)
        else:
            self.lbl_ack.setText(f"Download\n{state['filename']} {received}B")

        warn = f" -- {len(state['bad_seqs'])} chunk korup!" if state["bad_seqs"] else ""
        self.lbl_sd_progress.setText(
            f"Mengunduh '{state['filename']}' ({received_text} / {size_text}){warn}"
        )

    def _handle_file_end(self, data):
        """Transfer selesai (atau gagal di tengah jalan): baru sekarang minta
        lokasi simpan dan tulis seluruh isi file yang sudah ditampung."""
        cid = data.get("id")
        self._touch_pending_command(cid)

        state = self.file_downloads.pop(cid, None)
        if not state:
            return

        filename = state["filename"]
        received_text = format_file_size(state["received_bytes"])

        if data.get("aborted"):
            self.log_terminal("ERR", f"Download '{filename}' terhenti di tengah jalan (firmware error).", "#c0392b")
            self.lbl_sd_progress.setText(f"Download '{filename}' gagal (terhenti di tengah jalan).")
            self.progress_sd_download.setValue(0)
            return

        # PERBAIKAN: verifikasi keutuhan file SEBELUM ditawarkan untuk
        # disimpan. Kalau ada chunk yang gagal checksum, atau checksum total
        # yang dihitung PC tidak cocok dengan "cks_sum" yang dilaporkan
        # firmware, peringatkan pengguna dengan jelas -- daripada diam-diam
        # menyimpan file yang isinya rusak (ini akar masalah di log lama).
        bad_seqs = state.get("bad_seqs", [])
        expected_total_cks = data.get("cks_sum")
        total_mismatch = (
            expected_total_cks is not None and state.get("cks_sum", 0) != expected_total_cks
        )
        is_corrupted = bool(bad_seqs) or total_mismatch

        content = "".join(state["chunks"])

        if is_corrupted:
            detail = f"{len(bad_seqs)} chunk gagal checksum" if bad_seqs else "checksum total tidak cocok"
            self.log_terminal(
                "ERR",
                f"File '{filename}' terindikasi KORUP saat transfer serial ({detail}). "
                f"Disarankan mengulang download.",
                "#c0392b"
            )
            self.lbl_sd_progress.setText(f"'{filename}' terindikasi korup ({detail}). Coba download ulang.")
            self.progress_sd_download.setValue(0)
            proceed = QMessageBox.warning(
                self, "File Kemungkinan Korup",
                f"'{filename}' terdeteksi korup saat transfer lewat serial ({detail}).\n\n"
                "Ini biasanya karena gangguan transien di jalur serial, bukan file aslinya "
                "yang rusak di SD Card. Disarankan klik Download lagi.\n\n"
                "Simpan hasil yang ada sekarang (mungkin ada data hilang/salah)?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if proceed != QMessageBox.Yes:
                self.log_terminal("INFO", f"Download '{filename}' yang korup dibuang (tidak disimpan).", "#7f8c8d")
                return
        else:
            self.lbl_sd_progress.setText(f"'{filename}' selesai diunduh ({received_text}).")
            self.progress_sd_download.setValue(100)

        save_path, _ = QFileDialog.getSaveFileName(
            self, f"Simpan '{filename}' ({received_text})", filename, "All Files (*)"
        )
        if not save_path:
            self.log_terminal("INFO", f"Download '{filename}' dibatalkan (tidak disimpan).", "#7f8c8d")
            return

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(content)
            self.log_terminal(
                "INFO",
                f"File '{filename}' berhasil disimpan ke {save_path} ({received_text})",
                "#16a085"
            )
            QMessageBox.information(
                self, "Download Selesai",
                f"File berhasil disimpan:\n{save_path}\n\nUkuran: {received_text}"
            )
        except Exception as exc:
            self.log_terminal("ERR", f"Gagal menyimpan file '{filename}': {exc}", "#c0392b")
            QMessageBox.critical(self, "Error", f"Gagal menyimpan file:\n{exc}")

    def delete_log_file(self, filename):
        if QMessageBox.question(
            self, "Konfirmasi Hapus",
            f"Yakin ingin menghapus file '{filename}' dari SD Card?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            self.send_json_command({
                "cmd": "DELETE_FILE",
                "filename": self._sd_join(self.sd_current_path, filename),
            })

    def check_pending_commands(self):
        now = time.time()
        expired = []
        for cid, info in list(self.pending_commands.items()):
            if now - info["sent"] > info["timeout"]:
                expired.append(cid)

        for cid in expired:
            info = self.pending_commands.pop(cid, None)
            if info:
                btn = info.get("ui_button")
                if btn:
                    # Sama seperti di handle_ack() -- lihat catatan di sana.
                    try:
                        btn.setEnabled(True)
                        btn.setText(btn.property("original_text"))
                    except RuntimeError:
                        pass

                self.lbl_ack.setText(f"ACK\nTimeout #{cid}")
                self.log_terminal("ERR", f"ACK TIMEOUT #{cid} untuk {info['action']}", "#c0392b") # Red

    def handle_serial_error(self, err_msg):
        self.log_terminal("ERR", f"SERIAL ERROR: {err_msg}", "#c0392b")
        self.disconnect_serial()

    def update_pc_clock(self):
        self.lbl_time_pc.setText(
            f"Waktu PC: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}"
        )

    def closeEvent(self, event):
        self._close_csv_file()
        self.persist_config()
        if self.worker:
            self.worker.stop()
            self.worker = None
        event.accept()

    def _center_on_screen(self):
        """Posisikan jendela di tengah layar aktif -- berguna khususnya di
        monitor besar (2K/4K) supaya window tidak "nyangkut" di pojok
        kiri-atas layar, dan tetap benar di layar kecil/multi-monitor."""
        avail = _available_screen_geometry()
        if avail is None:
            return
        frame = self.frameGeometry()
        x = avail.x() + max(0, (avail.width() - frame.width()) // 2)
        y = avail.y() + max(0, (avail.height() - frame.height()) // 2)
        self.move(x, y)

def _build_theme_palette(theme=None):
    """Bangun QPalette dasar yang konsisten dengan tema global."""
    theme = normalize_theme(theme or DEFAULT_THEME)
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(theme["window_bg"]))
    palette.setColor(QPalette.WindowText, QColor(theme["text"]))
    palette.setColor(QPalette.Base, QColor(theme["input_bg"]))
    palette.setColor(QPalette.AlternateBase, QColor(theme["surface_alt"]))
    palette.setColor(QPalette.ToolTipBase, QColor(theme["surface_bg"]))
    palette.setColor(QPalette.ToolTipText, QColor(theme["text"]))
    palette.setColor(QPalette.Text, QColor(theme["input_text"]))
    palette.setColor(QPalette.Button, QColor(theme["button_bg"]))
    palette.setColor(QPalette.ButtonText, QColor(theme["button_text"]))
    palette.setColor(QPalette.Highlight, QColor(theme["selection_bg"]))
    palette.setColor(QPalette.HighlightedText, QColor(theme["selection_text"]))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(theme["disabled_text"]))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(theme["disabled_text"]))
    return palette


def main():
    global pg
    app = QApplication(sys.argv)
    # PERBAIKAN: pindah dari stylesheet custom penuh ke native Fusion style
    # + palet, mengikuti contoh referensi pengguna. Ini akar penyebab 3
    # keluhan sebelumnya: QGroupBox custom margin/padding bentrok dengan
    # render native (judul numpuk isi, terutama tab padat seperti "Kirim
    # ke Server"), tombol refresh ke-clip karena padding QPushButton global
    # menimpa lebar fixed-nya, dan resize jadi kaku karena banyak metrik
    # di-hardcode lewat stylesheet alih-alih dihitung native oleh Qt.
    app.setStyle("Fusion")
    app.setPalette(_build_theme_palette(DEFAULT_THEME))
    app.setStyleSheet(build_stylesheet(DEFAULT_THEME))

    import pyqtgraph
    pg = pyqtgraph
    # Antialiasing membuat garis grafik tetap halus/tajam saat di-scale
    # ke faktor DPI tinggi (2K/4K), bukan hanya berjalan di resolusi native.
    pg.setConfigOptions(antialias=True)

    window = LoggerDashboard()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
