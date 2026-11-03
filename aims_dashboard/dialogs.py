"""Dialog sederhana: konfigurasi sensor, threshold, dan tema."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout,
)

from aims_dashboard.config import BUZZER_PATTERN_COUNT
from aims_dashboard.theme import (
    DEFAULT_THEME_KEY, normalize_theme, THEME_PRESETS,
)
from aims_dashboard.widgets import ThemedDoubleSpinBox, ThemedSpinBox


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
