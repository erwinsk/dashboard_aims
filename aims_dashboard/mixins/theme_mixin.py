"""Penerapan tema & aksen ke seluruh aplikasi."""

from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import QApplication, QDialog

from aims_dashboard.dialogs import ThemeDialog
from aims_dashboard.theme import (
    _build_theme_palette, build_stylesheet, DEFAULT_THEME, DEFAULT_THEME_KEY,
    LEGACY_ACCENT_TO_THEME, normalize_theme, theme_from_config, THEME_PRESETS,
)


class ThemeMixin:
    """Penerapan tema & aksen ke seluruh aplikasi."""

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
