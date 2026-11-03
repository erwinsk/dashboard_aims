"""Proxy malas (lazy) untuk pyqtgraph.

Aslinya pyqtgraph di-import di dalam main() SETELAH QApplication dibuat
(variabel global `pg`). Supaya perilaku itu tetap sama setelah kode dipecah
ke banyak modul, semua modul cukup `from aims_dashboard.pgproxy import pg`:
pyqtgraph baru benar-benar di-import saat atribut pertamanya diakses
(pertama kali: pg.setConfigOptions(...) di main(), sesudah QApplication ada).
"""


class _LazyPyQtGraph:
    _mod = None

    def __getattr__(self, name):
        if _LazyPyQtGraph._mod is None:
            import pyqtgraph  # noqa: PLC0415 -- sengaja malas
            _LazyPyQtGraph._mod = pyqtgraph
        return getattr(_LazyPyQtGraph._mod, name)


pg = _LazyPyQtGraph()
