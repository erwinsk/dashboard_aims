"""Perhitungan ukuran/posisi jendela adaptif sesuai layar."""

from PyQt5.QtWidgets import QApplication


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
