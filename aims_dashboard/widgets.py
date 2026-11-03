"""Widget kustom yang mengikuti tema (SpinBox)."""

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QPainter, QPolygonF
from PyQt5.QtWidgets import QDoubleSpinBox, QSpinBox


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
