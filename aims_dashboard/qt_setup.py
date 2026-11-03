"""Pengaturan High-DPI Qt. WAJIB di-import SEBELUM QApplication dibuat."""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication


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
