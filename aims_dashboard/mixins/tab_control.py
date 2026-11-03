"""Tab Control: threshold & buzzer."""

from PyQt5.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from aims_dashboard.config import BUZZER_PATTERN_COUNT
from aims_dashboard.dialogs import ThresholdDialog
from aims_dashboard.widgets import ThemedSpinBox


class ControlTabMixin:
    """Tab Control: threshold & buzzer."""

    def setup_tab_control(self):
        layout = self._new_tab_layout(self.tab_control)

        grp_thresh = QGroupBox("Daftar Threshold yang Diterapkan ke Perangkat")
        v = QVBoxLayout(grp_thresh)

        self.table_threshold = self._make_expanding_table(min_height=150)
        self.table_threshold.setColumnCount(8)
        self.table_threshold.setHorizontalHeaderLabels([
            "ID", "Payload", "Operator", "Nilai", "Buzzer", "Interval", "Enabled", "Aksi"
        ])
        self.table_threshold.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_threshold.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_threshold.setEditTriggers(QTableWidget.NoEditTriggers)
        v.addWidget(self.table_threshold, stretch=1)

        h = QHBoxLayout()
        self.btn_add_threshold = QPushButton("Tambah Threshold")
        self.btn_add_threshold.setObjectName("btnPrimary")
        self.btn_add_threshold.clicked.connect(self.add_threshold)

        self.btn_edit_threshold = QPushButton("Edit")
        self.btn_edit_threshold.clicked.connect(self.edit_threshold)

        self.btn_delete_threshold = QPushButton("Delete")
        self.btn_delete_threshold.setObjectName("btnDanger")
        self.btn_delete_threshold.clicked.connect(self.delete_threshold)

        self.btn_sync_threshold = QPushButton("Kirim Semua Threshold ke ESP32")
        self.btn_sync_threshold.setObjectName("btnSuccess")
        self.btn_sync_threshold.clicked.connect(self.sync_all_thresholds)

        for b in [self.btn_add_threshold, self.btn_edit_threshold, self.btn_delete_threshold, self.btn_sync_threshold]:
            h.addWidget(b)
        h.addStretch()
        v.addLayout(h)
        layout.addWidget(grp_thresh, stretch=1)

        grp_buzzer = QGroupBox("Uji Coba Buzzer ESP32")
        vb = QHBoxLayout(grp_buzzer)
        self.cb_buzzer_test = QComboBox()
        for i in range(1, BUZZER_PATTERN_COUNT + 1):
            self.cb_buzzer_test.addItem(f"Pattern {i}", i)
        btn_test = QPushButton("Test Buzzer")
        btn_test.setObjectName("btnPrimary")
        btn_test.clicked.connect(self.test_buzzer)
        vb.addWidget(QLabel("Pilih suara:"))
        vb.addWidget(self.cb_buzzer_test)
        vb.addWidget(btn_test)
        vb.addStretch()
        layout.addWidget(grp_buzzer)

        grp_sys = QGroupBox("Manajemen Sistem & Daya")
        v = QVBoxLayout(grp_sys)
        self.lbl_current_mode = self._make_card("Mode Saat Ini: --")
        v.addWidget(self.lbl_current_mode)

        h = QHBoxLayout()
        b1 = QPushButton("Set Always On")
        b1.clicked.connect(self.set_always_on_mode)

        b2 = QPushButton("Set Deep Sleep")
        b2.clicked.connect(self.set_deep_sleep_mode)

        h.addWidget(b1)
        h.addWidget(b2)
        h.addStretch()
        v.addLayout(h)

        hsleep = QHBoxLayout()
        hsleep.addWidget(QLabel("Durasi Deep Sleep:"))

        self.sp_deep_sleep = ThemedSpinBox()
        self.sp_deep_sleep.setRange(1, 86400)
        self.sp_deep_sleep.setSuffix(" detik")
        self.sp_deep_sleep.setValue(
            int(self.config.get("device", {}).get("deep_sleep_sec", 60))
        )
        self.sp_deep_sleep.valueChanged.connect(self.save_deep_sleep_setting)

        hsleep.addWidget(self.sp_deep_sleep)
        hsleep.addStretch()
        v.addLayout(hsleep)

        breset = QPushButton("System Soft-Reset / Reboot")
        breset.setObjectName("btnDanger")
        breset.clicked.connect(self.reset_device_action)
        v.addWidget(breset)
        layout.addWidget(grp_sys)

        # Timer refresh e-paper (SSD1680) -- terpisah dari interval
        # logging SD supaya operator bisa mengatur seberapa sering layar
        # digambar ulang (partial) dan seberapa sering full-refresh
        # dipaksa (bersihkan ghosting) tanpa memengaruhi konfigurasi lain.
        # Font panel tetap font6x8 (tidak lagi bisa dipilih dari GUI).
        grp_display = QGroupBox("Timer Refresh E-Paper Display")
        v_disp = QVBoxLayout(grp_display)

        form_disp = QFormLayout()
        self.sp_display_interval = ThemedSpinBox()
        self.sp_display_interval.setRange(5, 3600)
        self.sp_display_interval.setSuffix(" detik")
        self.sp_display_interval.setValue(
            int(self.config.get("display", {}).get("update_interval_sec", 60))
        )
        self.sp_display_full_refresh = ThemedSpinBox()
        self.sp_display_full_refresh.setRange(1, 1440)
        self.sp_display_full_refresh.setSuffix(" menit")
        self.sp_display_full_refresh.setValue(
            int(self.config.get("display", {}).get("full_refresh_interval_min", 30))
        )
        form_disp.addRow("Update Layar (Partial):", self.sp_display_interval)
        form_disp.addRow("Full Refresh (Anti-Ghosting):", self.sp_display_full_refresh)
        v_disp.addLayout(form_disp)

        h_disp = QHBoxLayout()
        btn_get_display = QPushButton("Muat Konfigurasi Display dari Device")
        btn_get_display.clicked.connect(
            lambda: self.send_json_command({"cmd": "GET_CONFIG"}, ui_button=btn_get_display)
        )
        btn_sync_display = QPushButton("Sync Configuration")
        btn_sync_display.setObjectName("btnPrimary")
        btn_sync_display.clicked.connect(
            lambda: self.sync_display_config(ui_button=btn_sync_display)
        )
        h_disp.addWidget(btn_get_display)
        h_disp.addWidget(btn_sync_display)
        h_disp.addStretch()
        v_disp.addLayout(h_disp)

        layout.addWidget(grp_display)

    def next_threshold_id(self):
        return max([int(t.get("id", 0)) for t in self.thresholds] + [0]) + 1

    def refresh_threshold_table(self):
        self.table_threshold.setRowCount(0)
        migrated = False

        for threshold in self.thresholds:
            normalized = self._normalize_threshold_record(threshold)
            if not normalized:
                continue

            row = self.table_threshold.rowCount()
            self.table_threshold.insertRow(row)

            if normalized != threshold:
                migrated = True

            values = [
                normalized.get("id", ""),
                normalized.get("payload", ""),
                normalized.get("operator", ">"),
                normalized.get("value", ""),
                normalized.get("buzzer", 1),
                f"{max(1, (int(normalized.get('interval_sec', 300)) + 59) // 60)} menit",
                "Yes" if normalized.get("enabled", True) else "No",
            ]
            for col, value in enumerate(values):
                self.table_threshold.setItem(
                    row, col, QTableWidgetItem(str(value))
                )

            btn = self._make_compact_table_button("Kirim")
            btn.clicked.connect(
                lambda _, tid=normalized.get("id"): self.send_threshold_by_id(tid)
            )
            self.table_threshold.setCellWidget(row, 7, btn)
            self.table_threshold.setRowHeight(row, 28)

        if migrated:
            self.thresholds[:] = [
                self._normalize_threshold_record(th)
                for th in self.thresholds
                if self._normalize_threshold_record(th)
            ]
            self.persist_config()

    def add_threshold(self):
        dialog = ThresholdDialog(
            self, payload_keys=self.get_payload_keys(numeric_only=True)
        )
        if dialog.exec_() == QDialog.Accepted:
            threshold = self._normalize_threshold_record(dialog.get_threshold())
            if not threshold:
                QMessageBox.warning(self, "Peringatan", "Payload threshold tidak boleh kosong.")
                return
            threshold["id"] = self.next_threshold_id()
            self.thresholds.append(threshold)
            self.persist_config()
            self.refresh_threshold_table()

    def edit_threshold(self):
        row = self.table_threshold.currentRow()
        if row < 0 or row >= len(self.thresholds):
            QMessageBox.warning(self, "Peringatan", "Pilih threshold terlebih dahulu.")
            return

        threshold = self.thresholds[row]
        dialog = ThresholdDialog(
            self,
            payload_keys=self.get_payload_keys(numeric_only=True),
            threshold=threshold,
        )
        if dialog.exec_() == QDialog.Accepted:
            updated = self._normalize_threshold_record(dialog.get_threshold())
            if not updated:
                QMessageBox.warning(self, "Peringatan", "Payload threshold tidak boleh kosong.")
                return
            updated["id"] = threshold.get("id", self.next_threshold_id())
            self.thresholds[row] = updated
            self.persist_config()
            self.refresh_threshold_table()

    def delete_threshold(self):
        row = self.table_threshold.currentRow()
        if row < 0:
            return
        if QMessageBox.question(
            self, "Konfirmasi", "Hapus threshold yang dipilih?"
        ) == QMessageBox.Yes:
            self.thresholds.pop(row)
            self.persist_config()
            self.refresh_threshold_table()

    def send_threshold_by_id(self, threshold_id):
        threshold = next((t for t in self.thresholds if t.get("id") == threshold_id), None)
        if threshold:
            self.send_json_command({
                "cmd": "SET_THRESHOLD",
                "threshold": self._normalize_threshold_record(threshold),
            })

    def sync_all_thresholds(self):
        self.send_json_command({
            "cmd": "SET_THRESHOLDS",
            "thresholds": [
                self._normalize_threshold_record(th)
                for th in self.thresholds
                if self._normalize_threshold_record(th)
            ],
        })

    def test_buzzer(self):
        pattern = int(self.cb_buzzer_test.currentData())
        self.send_json_command({
            "cmd": "BUZZER_TEST",
            "pattern": pattern,
        })
