"""Tab Dashboard + Dashboard Designer (widget, label sensor, payload registry)."""

import os
from collections import deque

from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
    QMessageBox, QPushButton, QTableWidgetItem, QVBoxLayout,
)

from aims_dashboard.config import (
    BUZZER_PATTERN_COUNT, CONFIG_PATH, GRAPH_COLORS, MAX_POINTS,
)
from aims_dashboard.dialogs import SensorConfigDialog
from aims_dashboard.pgproxy import pg
from aims_dashboard.theme import DEFAULT_THEME, THEME_PRESETS
from aims_dashboard.widgets import ThemedDoubleSpinBox


class DashboardTabMixin:
    """Tab Dashboard + Dashboard Designer (widget, label sensor, payload registry)."""

    def setup_tab_dashboard(self):
        layout = self._new_tab_layout(self.tab_dashboard)

        self.group_status = QGroupBox("Status & Payload Real-time")
        self.grid_status = QGridLayout(self.group_status)
        layout.addWidget(self.group_status)

        self.group_plot = QGroupBox("Grafik Sensor Real-Time")
        vplot = QVBoxLayout(self.group_plot)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground(self.config.get("ui", {}).get("theme", "light_blue") in THEME_PRESETS and THEME_PRESETS[self.config.get("ui", {}).get("theme", "light_blue")]["plot_bg"] or DEFAULT_THEME["plot_bg"])
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setLabel("left", "Nilai Parameter")
        self.plot_widget.setLabel("bottom", "Waktu (detik sejak mulai)")
        vplot.addWidget(self.plot_widget)
        layout.addWidget(self.group_plot, stretch=1)

        hrec = QHBoxLayout()
        hrec.addWidget(QLabel("Interval Simpan (detik):"))
        self.sp_csv_interval = ThemedDoubleSpinBox()
        self.sp_csv_interval.setRange(0.1, 3600.0)
        self.sp_csv_interval.setSingleStep(0.5)
        self.sp_csv_interval.setValue(1.0)
        self.sp_csv_interval.setToolTip(
            "Jarak waktu minimum antar baris yang ditulis ke CSV. "
            "Telemetri tetap masuk tiap detik dari firmware, tapi baris CSV "
            "baru ditulis kalau sudah melewati interval ini."
        )
        hrec.addWidget(self.sp_csv_interval)
        self.btn_record = QPushButton("Start Record CSV")
        self.btn_record.setObjectName("btnSuccess")
        self.btn_record.clicked.connect(self.toggle_record_csv)
        hrec.addStretch()
        hrec.addWidget(self.btn_record)
        layout.addLayout(hrec)

    def _rebuild_sensor_cards(self):
        while self.grid_status.count():
            item = self.grid_status.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.sensor_labels.clear()
        cards = []

        for cfg in self.sensor_config:
            key = cfg.get("key")
            if not key:
                continue
            label = cfg.get("label", key)
            unit = cfg.get("unit", "")
            text = f"{label}\n-- {unit}".strip()
            card = self._make_card(text)
            self.sensor_labels[key] = card
            cards.append(card)

        self.lbl_mode = self._make_card("Mode Daya\n--")
        self.lbl_wifi = self._make_card("WiFi\n--")
        self.lbl_ip = self._make_card("Alamat IP\n--")
        self.lbl_sd_stat = self._make_card("SD Card\n--")
        self.lbl_heartbeat = self._make_card("Heartbeat\n#0")
        self.lbl_ack = self._make_card("ACK\n--")

        cards.extend([
            self.lbl_mode, self.lbl_wifi, self.lbl_ip,
            self.lbl_sd_stat, self.lbl_heartbeat, self.lbl_ack
        ])

        for i, card in enumerate(cards):
            self.grid_status.addWidget(card, i // 4, i % 4)

        # Checkbox kanal udaraku mengikuti sensor_config -- dibangun ulang
        # di sini supaya menambah/menghapus/mengedit widget dashboard di tab
        # Dashboard Designer otomatis tercermin di daftar kanal yang bisa
        # dipilih, tanpa daftar statis terpisah yang gampang basi.
        self._refresh_udaraku_kanal_checkboxes()

    def _rebuild_sensor_curves(self):
        self.sensor_curves.clear()
        self.sensor_x.clear()
        self.sensor_y.clear()

        self.plot_widget.clear()
        self.plot_widget.addLegend()

        for idx, cfg in enumerate(self.sensor_config):
            key = cfg.get("key")
            if not key or not cfg.get("show_graph", True):
                continue
            self.sensor_x[key] = deque(maxlen=MAX_POINTS)
            self.sensor_y[key] = deque(maxlen=MAX_POINTS)
            pen = pg.mkPen(GRAPH_COLORS[idx % len(GRAPH_COLORS)], width=2)
            curve = self.plot_widget.plot(
                pen=pen,
                name=f"{cfg.get('label', key)} ({cfg.get('unit', '')})"
            )
            self.sensor_curves[key] = curve

    def refresh_widgets_ui(self):
        self.table_widgets.setRowCount(0)

        for idx, cfg in enumerate(self.sensor_config, start=1):
            if not isinstance(cfg, dict):
                continue
            key = str(cfg.get("key", "")).strip()
            if not key:
                continue

            row = self.table_widgets.rowCount()
            self.table_widgets.insertRow(row)

            values = [
                idx,
                key,
                cfg.get("label", key),
                cfg.get("unit", ""),
                cfg.get("decimals", "1"),
                "Yes" if cfg.get("show_graph", True) else "No",
            ]

            for col, value in enumerate(values):
                self.table_widgets.setItem(
                    row, col, QTableWidgetItem(str(value))
                )

        self.table_widgets.resizeRowsToContents()

    def refresh_payload_registry_ui(self):
        """
        Refresh LENGKAP: daftar Widget Dashboard + tabel Payload Registry.
        Dipakai setelah operasi tambah/edit/hapus/pindah widget -- BUKAN
        dipanggil tiap payload masuk (lihat _update_payload_registry_table),
        supaya seleksi baris di tabel Widget Dashboard tidak ter-reset tiap
        detik oleh telemetri yang masuk.
        """
        self.refresh_widgets_ui()
        self._update_payload_registry_table()

    def _update_payload_registry_table(self):
        """
        PERBAIKAN: sebelumnya dipanggil lewat refresh_payload_registry_ui()
        yang JUGA merombak total table_widgets (Dashboard Designer) tiap
        payload masuk (~1x/detik) -- akibatnya baris yang sedang dipilih di
        situ selalu ter-reset, sehingga tombol Edit/Hapus terasa "tidak bisa
        dipilih". Method ini HANYA mengurus tabel Payload Registry
        (nilai real-time), aman dipanggil sesering apa pun.

        PERBAIKAN 2: setRowCount(0) + rebuild penuh di bawah ini JUGA
        menghapus seleksi baris tiap kali dipanggil (sama seperti masalah
        yang sudah diperbaiki di atas untuk table_widgets) -- akibatnya
        tombol "Edit Label CSV" tidak sempat diklik karena baris terpilih
        selalu ter-reset tiap ~1 detik oleh telemetri berikutnya. Fix:
        simpan KEY yang sedang dipilih (bukan nomor baris, karena urutan
        alfabetis bisa berubah kalau ada key baru muncul), lalu cari &
        pilih ulang baris dengan key yang sama setelah rebuild.
        """
        current_row = self.table_payload.currentRow()
        selected_key = None
        if current_row >= 0:
            item = self.table_payload.item(current_row, 0)
            if item is not None:
                selected_key = item.text()

        self.table_payload.setRowCount(0)
        restore_row = -1
        for key in sorted(self.payload_registry):
            info = self.payload_registry[key]
            row = self.table_payload.rowCount()
            self.table_payload.insertRow(row)
            self.table_payload.setItem(row, 0, QTableWidgetItem(key))
            self.table_payload.setItem(row, 1, QTableWidgetItem(info["type"]))
            self.table_payload.setItem(row, 2, QTableWidgetItem(str(info["last"])))

            used = any(
                isinstance(cfg, dict) and cfg.get("key") == key
                for cfg in self.sensor_config
            )
            self.table_payload.setItem(
                row, 3, QTableWidgetItem("Yes" if used else "No")
            )

            label = self.config.get("sensor_labels", {}).get(self._sensor_base_key(key), key)
            self.table_payload.setItem(row, 4, QTableWidgetItem(str(label)))

            if key == selected_key:
                restore_row = row

        if restore_row >= 0:
            self.table_payload.selectRow(restore_row)

        self.update_dashboard_info()

    def edit_sensor_label(self):
        """Edit label CSV (nama kolom header SD Card) untuk key payload yang
        dipilih di tabel Payload Registry -- lepas dari apakah key itu
        dipakai sebagai Widget Dashboard atau tidak. Disimpan lokal dulu
        (self.config['sensor_labels']); baru dikirim ke device lewat
        tombol 'Kirim Label ke Device' (command SET_SENSOR_LABELS)."""
        row = self.table_payload.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Info", "Pilih dulu salah satu baris payload key di tabel."
            )
            return
        key_item = self.table_payload.item(row, 0)
        if key_item is None:
            return
        key = key_item.text()
        csv_key = self._sensor_base_key(key)

        current_label = self.config.get("sensor_labels", {}).get(csv_key, csv_key)
        new_label, ok = QInputDialog.getText(
            self, "Edit Label CSV",
            f"Label kolom CSV untuk payload key \"{key}\":",
            text=current_label
        )
        if not ok:
            return
        new_label = new_label.strip()
        if not new_label:
            QMessageBox.warning(self, "Peringatan", "Label tidak boleh kosong.")
            return

        self.config.setdefault("sensor_labels", {})[csv_key] = new_label
        self.persist_config()
        self._update_payload_registry_table()

    def sync_sensor_labels(self):
        """Kirim semua label CSV yang tersimpan lokal ke device (flash)
        lewat command SET_SENSOR_LABELS. Kalau belum pernah diedit sama
        sekali, tetap boleh dikirim kosong -- firmware akan tetap pakai
        default bawaannya sendiri."""
        labels = self.config.get("sensor_labels", {})
        self.send_json_command({"cmd": "SET_SENSOR_LABELS", "labels": labels})

    def add_dashboard_widget(self):
        dialog = SensorConfigDialog(
            self, payload_keys=self.get_payload_keys(numeric_only=False)
        )
        if dialog.exec_() == QDialog.Accepted:
            config = dialog.get_config()
            if not config["key"]:
                return
            if any(c.get("key") == config["key"] for c in self.sensor_config):
                QMessageBox.warning(
                    self, "Peringatan",
                    "Payload key tersebut sudah digunakan oleh widget lain."
                )
                return
            self.sensor_config.append(config)
            self.persist_config()
            self._rebuild_sensor_cards()
            self._rebuild_sensor_curves()
            self.refresh_payload_registry_ui()
            self.table_widgets.selectRow(len(self.sensor_config) - 1)

    def edit_dashboard_widget(self):
        row = self.table_widgets.currentRow()
        if row < 0 or row >= len(self.sensor_config):
            QMessageBox.warning(self, "Peringatan", "Pilih widget pada daftar Widget Dashboard.")
            return

        old = self.sensor_config[row]
        dialog = SensorConfigDialog(
            self,
            config=old,
            payload_keys=self.get_payload_keys(numeric_only=False)
        )
        if dialog.exec_() == QDialog.Accepted:
            new_cfg = dialog.get_config()
            if not new_cfg["key"]:
                return
            for i, cfg in enumerate(self.sensor_config):
                if i != row and cfg.get("key") == new_cfg["key"]:
                    QMessageBox.warning(
                        self, "Peringatan",
                        "Payload key tersebut sudah digunakan oleh widget lain."
                    )
                    return
            self.sensor_config[row] = new_cfg
            self.persist_config()
            self._rebuild_sensor_cards()
            self._rebuild_sensor_curves()
            self.refresh_payload_registry_ui()
            self.table_widgets.selectRow(row)

    def delete_dashboard_widget(self):
        row = self.table_widgets.currentRow()
        if row < 0 or row >= len(self.sensor_config):
            return
        key = self.sensor_config[row].get("key", "")
        if QMessageBox.question(
            self, "Konfirmasi",
            f"Hapus widget '{key}' dari dashboard?"
        ) == QMessageBox.Yes:
            self.sensor_config.pop(row)
            self.persist_config()
            self._rebuild_sensor_cards()
            self._rebuild_sensor_curves()
            self.refresh_payload_registry_ui()

    def move_widget(self, direction):
        row = self.table_widgets.currentRow()
        target = row + direction
        if row < 0 or target < 0 or target >= len(self.sensor_config):
            return
        self.sensor_config[row], self.sensor_config[target] = (
            self.sensor_config[target], self.sensor_config[row]
        )
        self.persist_config()
        self._rebuild_sensor_cards()
        self._rebuild_sensor_curves()
        self.refresh_payload_registry_ui()
        self.table_widgets.selectRow(target)

    def save_dashboard_config(self):
        self.persist_config()
        QMessageBox.information(
            self, "Info",
            f"Konfigurasi perangkat berhasil disimpan:\n{CONFIG_PATH}"
        )

    def update_dashboard_info(self):
        self.lbl_dashboard_info.setText(
            f"Widget aktif: {len(self.sensor_config)} | "
            f"Payload terdeteksi: {len(self.payload_registry)} | "
            f"Threshold: {len(self.thresholds)} | "
            f"Buzzer Pattern: 1–{BUZZER_PATTERN_COUNT} | "
            f"Config: {os.path.basename(CONFIG_PATH)} | "
            f"Deep Sleep: {self.config.get('device', {}).get('deep_sleep_sec', 60)} detik"
        )
