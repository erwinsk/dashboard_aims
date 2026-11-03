"""Tab Network: Wi-Fi scan/connect, sinkron RTC."""

import time

from PyQt5.QtWidgets import (
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)


class NetworkTabMixin:
    """Tab Network: Wi-Fi scan/connect, sinkron RTC."""

    def setup_tab_network(self):
        layout = self._new_tab_layout(self.tab_network)

        grp_wifi = QGroupBox("Manajemen Wi-Fi")
        v = QVBoxLayout(grp_wifi)

        h = QHBoxLayout()
        btn_scan = QPushButton("Scan Wi-Fi")
        btn_scan.setObjectName("btnPrimary")
        btn_scan.clicked.connect(
            lambda: self.send_json_command({"cmd": "WIFI_SCAN"}, ui_button=btn_scan)
        )

        self.btn_disconnect = QPushButton("Disconnect Wi-Fi")
        self.btn_disconnect.setObjectName("btnDanger")
        self.btn_disconnect.clicked.connect(self.disconnect_wifi_action)

        h.addWidget(btn_scan)
        h.addWidget(self.btn_disconnect)
        h.addStretch()
        v.addLayout(h)

        h = QHBoxLayout()
        self.txt_ssid = QLineEdit()
        self.txt_ssid.setPlaceholderText("SSID Wi-Fi")

        self.txt_pass = QLineEdit()
        self.txt_pass.setPlaceholderText("Password")
        self.txt_pass.setEchoMode(QLineEdit.Password)

        self.btn_connect_wifi = QPushButton("Connect Wi-Fi")
        self.btn_connect_wifi.setObjectName("btnPrimary")
        self.btn_connect_wifi.clicked.connect(self.connect_wifi_action)

        h.addWidget(self.txt_ssid)
        h.addWidget(self.txt_pass)
        h.addWidget(self.btn_connect_wifi)
        v.addLayout(h)

        self.table_wifi_scan = QTableWidget()
        self.table_wifi_scan.setColumnCount(3)
        self.table_wifi_scan.setHorizontalHeaderLabels(["SSID", "RSSI", "Aksi"])
        self.table_wifi_scan.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_wifi_scan.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_wifi_scan.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_wifi_scan.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_wifi_scan.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_wifi_scan.setMinimumHeight(160)
        
        v.addWidget(QLabel("Hasil Scan Wi-Fi"))
        v.addWidget(self.table_wifi_scan)

        layout.addWidget(grp_wifi)

        grp_time = QGroupBox("Sinkronisasi Waktu & RTC")
        v = QVBoxLayout(grp_time)
        self.lbl_time_pc = QLabel("Waktu PC: --")
        self.lbl_time_rtc = QLabel("Waktu RTC Perangkat: --")
        v.addWidget(self.lbl_time_pc)
        v.addWidget(self.lbl_time_rtc)

        h = QHBoxLayout()
        b1 = QPushButton("Sinkron RTC dengan Jam PC (Unix TS)")
        b1.clicked.connect(self.sync_rtc_pc_action)
        h.addWidget(b1)
        h.addStretch()
        v.addLayout(h)

        layout.addWidget(grp_time)

        # Config Device tersimpan di flash ESP32. Sesuai keputusan desain:
        # satu file config gabungan di firmware (WiFi SSID terakhir + mode +
        # daftar threshold), dipakai untuk auto-reconnect WiFi saat boot
        # tanpa perlu GUI terhubung. GET_CONFIG / SET_CONFIG sudah
        # diimplementasikan penuh di firmware (lihat main.py) -- panel ini
        # bukan lagi scaffolding.
        grp_config = QGroupBox("Konfigurasi Tersimpan di Device (Flash) — Auto-Reconnect")
        v_cfg = QVBoxLayout(grp_config)

        self.lbl_device_config = QLabel(
            "Belum diambil dari device. Klik 'Muat Config dari Device' untuk cek "
            "apa yang tersimpan di flash ESP32 (dipakai untuk auto-reconnect saat boot)."
        )
        self.lbl_device_config.setObjectName("statusCard")
        self.lbl_device_config.setWordWrap(True)
        v_cfg.addWidget(self.lbl_device_config)

        h_cfg = QHBoxLayout()
        btn_get_cfg = QPushButton("Muat Config dari Device")
        btn_get_cfg.clicked.connect(
            lambda: self.send_json_command({"cmd": "GET_CONFIG"}, ui_button=btn_get_cfg)
        )
        btn_set_cfg = QPushButton("Simpan Config ke Device (Flash)")
        btn_set_cfg.setObjectName("btnPrimary")
        btn_set_cfg.clicked.connect(
            lambda: self.push_device_config(ui_button=btn_set_cfg)
        )
        h_cfg.addWidget(btn_get_cfg)
        h_cfg.addWidget(btn_set_cfg)
        h_cfg.addStretch()
        v_cfg.addLayout(h_cfg)

        layout.addWidget(grp_config)
        layout.addStretch()

    def _handle_scan_start(self, data):
        """Awal hasil scan WiFi ber-tahap (SCAN_START -> beberapa SCAN_ITEM -> SCAN_END)."""
        cid = data.get("id")
        self._touch_pending_command(cid)
        self.wifi_scans[cid] = {"items": [], "expected": data.get("count", 0)}
        self.table_wifi_scan.setRowCount(0)

    def _handle_scan_item(self, data):
        """Satu SSID hasil scan. Dikirim satu-per-satu supaya kalau ada satu
        pesan yang korup di jalur serial, cuma SSID itu yang hilang -- bukan
        seluruh hasil scan seperti pada protokol lama (satu array besar)."""
        cid = data.get("id")
        self._touch_pending_command(cid)

        ssid = str(data.get("ssid", "")).strip()
        if not ssid:
            return

        state = self.wifi_scans.setdefault(cid, {"items": [], "expected": 0})
        state["items"].append({"ssid": ssid, "rssi": data.get("rssi", "")})

    def _handle_scan_end(self, data):
        """Akhir hasil scan: render semua item yang berhasil diterima ke tabel,
        dan beri tahu pengguna secara eksplisit kalau ada yang hilang di jalan
        (dibanding count asli dari firmware) supaya tidak dikira tabel kosong
        tanpa sebab."""
        cid = data.get("id")
        self._touch_pending_command(cid)

        state = self.wifi_scans.pop(cid, None)
        items = state["items"] if state else []
        self._populate_wifi_scan_table(items)

        expected = data.get("count")
        if expected is not None and len(items) < expected:
            self.log_terminal(
                "ERR",
                f"Hasil scan WiFi tidak lengkap: {len(items)}/{expected} jaringan diterima "
                "(sebagian pesan kemungkinan korup di jalur serial).",
                "#c0392b"
            )

    def _populate_wifi_scan_table(self, networks):
        self.table_wifi_scan.setRowCount(0)
        if not isinstance(networks, list):
            return

        for network in networks:
            if not isinstance(network, dict):
                continue
            ssid = str(network.get("ssid", "")).strip()
            if not ssid:
                continue
            rssi = network.get("rssi", "")

            row = self.table_wifi_scan.rowCount()
            self.table_wifi_scan.insertRow(row)

            self.table_wifi_scan.setItem(row, 0, QTableWidgetItem(ssid))
            self.table_wifi_scan.setItem(row, 1, QTableWidgetItem(str(rssi)))

            btn_use = QPushButton("Gunakan")
            btn_use.clicked.connect(
                lambda _, value=ssid: self.txt_ssid.setText(value)
            )
            self.table_wifi_scan.setCellWidget(row, 2, btn_use)

    def connect_wifi_action(self):
        ssid = self.txt_ssid.text().strip()
        pwd = self.txt_pass.text()
        if not ssid:
            QMessageBox.warning(self, "Peringatan", "SSID tidak boleh kosong.")
            return
        self.send_json_command({
            "cmd": "WIFI_CONNECT",
            "ssid": ssid,
            "password": pwd,
        }, ui_button=self.btn_connect_wifi)

    def disconnect_wifi_action(self):
        self.send_json_command({"cmd": "WIFI_OFF"}, ui_button=self.btn_disconnect)

    def sync_rtc_pc_action(self):
        self.send_json_command({
            "cmd": "SET_RTC",
            "timestamp": int(time.time()),
        })
