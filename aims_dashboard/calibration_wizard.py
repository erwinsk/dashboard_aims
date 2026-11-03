"""Dialog wizard kalibrasi (GUI)."""

import html

import numpy as np

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from aims_dashboard.calibration_math import (
    _format_calibration_number, CALIBRATION_MODEL_LABELS,
    CALIBRATION_MODEL_PARAM_COUNTS, evaluate_calibration_model,
    fit_calibration_candidates,
)
from aims_dashboard.config import GRAPH_COLORS
from aims_dashboard.pgproxy import pg
from aims_dashboard.screen import _available_screen_geometry


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
