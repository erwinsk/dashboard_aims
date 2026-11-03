"""Tema, preset, aksen, stylesheet, dan palette aplikasi."""

from PyQt5.QtGui import QColor, QPalette


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
