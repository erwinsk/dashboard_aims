"""Fungsi main(): membuat QApplication, tema, dan jendela utama."""

import sys

from PyQt5.QtWidgets import QApplication

from aims_dashboard.main_window import LoggerDashboard
from aims_dashboard.pgproxy import pg
from aims_dashboard.theme import (
    _build_theme_palette, build_stylesheet, DEFAULT_THEME,
)

from aims_dashboard import qt_setup  # noqa: F401  (efek samping: set atribut High-DPI)


def main():
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

    # Antialiasing membuat garis grafik tetap halus/tajam saat di-scale
    # ke faktor DPI tinggi (2K/4K), bukan hanya berjalan di resolusi native.
    pg.setConfigOptions(antialias=True)

    window = LoggerDashboard()
    window.show()
    sys.exit(app.exec_())
