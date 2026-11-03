"""Tab Kalibrasi: tabel, profil, sinkron ke device, identitas."""

import html

from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from aims_dashboard.calibration_math import (
    _format_calibration_number, CALIBRATION_MODEL_LABELS,
    CALIBRATION_MODEL_PARAM_COUNTS, evaluate_calibration_model,
)
from aims_dashboard.calibration_wizard import CalibrationWizardDialog


class CalibrationTabMixin:
    """Tab Kalibrasi: tabel, profil, sinkron ke device, identitas."""

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
