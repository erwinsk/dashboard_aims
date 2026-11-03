"""Tab Udaraku: kirim ke server, kanal, status."""

import time

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from aims_dashboard.widgets import ThemedSpinBox


class UdarakuTabMixin:
    """Tab Udaraku: kirim ke server, kanal, status."""

    def setup_tab_udaraku(self):
        """Tab 7 -- konfigurasi pengiriman data ke gerbang HTTP udaraku
        (POST) yang dilakukan LANGSUNG oleh ESP32 (bukan lewat GUI/PC).
        GUI di sini murni alat untuk mengatur & mengirim konfigurasi ke
        device lewat command SET_UDARAKU_CONFIG, disimpan firmware ke
        flash. Menggantikan tab "Kirim ke Server" (JWT, iot.kemenperin.
        go.id) yang sudah dihapus total dari firmware -- lihat
        udaraku_sync.py untuk kontrak protokolnya (Bearer key, bukan
        JWT signing).
        """
        layout = self._new_tab_layout(self.tab_udaraku)

        grp_conn = QGroupBox("Koneksi Udaraku")
        form_conn = QFormLayout(grp_conn)

        self.chk_udaraku_enabled = QCheckBox("Aktifkan pengiriman data ke udaraku")
        form_conn.addRow(self.chk_udaraku_enabled)

        self.txt_udaraku_url = QLineEdit()
        self.txt_udaraku_url.setPlaceholderText(
            "https://udaraku.kemenperin.go.id:8005/v1/ingest/kanal"
        )
        form_conn.addRow("URL Endpoint:", self.txt_udaraku_url)

        h_key = QHBoxLayout()
        self.txt_udaraku_key = QLineEdit()
        # Bearer key alat -- BEDA kontrak dari private key JWT jalur server
        # lama. Dikirim apa adanya sebagai header "Authorization: Bearer
        # <key>" oleh udaraku_sync.py, tidak dipakai untuk signing apa pun.
        self.txt_udaraku_key.setPlaceholderText("Bearer key alat (aqk_live_...)")
        self.txt_udaraku_key.setEchoMode(QLineEdit.Password)
        h_key.addWidget(self.txt_udaraku_key)
        self.chk_show_udaraku_key = QCheckBox("Tampilkan")
        self.chk_show_udaraku_key.toggled.connect(
            lambda checked: self.txt_udaraku_key.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        h_key.addWidget(self.chk_show_udaraku_key)
        form_conn.addRow("Bearer Key:", h_key)

        self.txt_udaraku_kode_alat = QLineEdit()
        self.txt_udaraku_kode_alat.setPlaceholderText("mis. TRHC001")
        # Sengaja input manual, BUKAN auto-terisi dari SN device (GET_IDENTITY)
        # -- kode_alat boleh berbeda dari SN fisik alat.
        form_conn.addRow("Kode Alat:", self.txt_udaraku_kode_alat)

        layout.addWidget(grp_conn)

        grp_kanal = QGroupBox("Kanal yang Dikirim")
        v_kanal = QVBoxLayout(grp_kanal)
        lbl_kanal_hint = QLabel(
            "Centang payload key yang dikirim ke udaraku. Daftar ini mengikuti "
            "widget sensor yang terdaftar di tab \"Dashboard Designer\" -- "
            "tambah/hapus widget di sana untuk mengubah pilihan di sini. "
            "Kalau TIDAK ADA yang dicentang, firmware mengirim SEMUA kanal "
            "(begitu udaraku_sync.py menafsirkan daftar kanal kosong)."
        )
        lbl_kanal_hint.setWordWrap(True)
        v_kanal.addWidget(lbl_kanal_hint)

        self._kanal_checkbox_container = QWidget()
        self._kanal_checkbox_layout = QVBoxLayout(self._kanal_checkbox_container)
        self._kanal_checkbox_layout.setContentsMargins(0, 0, 0, 0)
        self._chk_udaraku_kanal = {}
        v_kanal.addWidget(self._kanal_checkbox_container)

        layout.addWidget(grp_kanal)

        grp_timing = QGroupBox("Interval Pengiriman")
        form_timing = QFormLayout(grp_timing)

        self.sp_udaraku_interval = ThemedSpinBox()
        self.sp_udaraku_interval.setRange(5, 86400)
        self.sp_udaraku_interval.setSuffix(" detik")
        self.sp_udaraku_interval.setValue(60)
        form_timing.addRow("Interval Realtime:", self.sp_udaraku_interval)

        self.chk_udaraku_queue_enabled = QCheckBox(
            "Aktifkan pengiriman antrian (backlog CSV)"
        )
        self.chk_udaraku_queue_enabled.setChecked(True)
        form_timing.addRow(self.chk_udaraku_queue_enabled)

        self.sp_udaraku_queue_interval = ThemedSpinBox()
        self.sp_udaraku_queue_interval.setRange(1, 3600)
        self.sp_udaraku_queue_interval.setSuffix(" detik")
        self.sp_udaraku_queue_interval.setValue(5)
        form_timing.addRow("Interval Antrian:", self.sp_udaraku_queue_interval)

        self.sp_udaraku_timeout = ThemedSpinBox()
        self.sp_udaraku_timeout.setRange(1, 120)
        self.sp_udaraku_timeout.setSuffix(" detik")
        self.sp_udaraku_timeout.setValue(15)
        form_timing.addRow("Timeout Koneksi:", self.sp_udaraku_timeout)

        layout.addWidget(grp_timing)

        grp_notif = QGroupBox("Notifikasi Buzzer Pengiriman")
        v_notif = QVBoxLayout(grp_notif)

        lbl_fail_header = QLabel("<b>Saat Gagal</b>")
        v_notif.addWidget(lbl_fail_header)

        form_fail = QFormLayout()
        self.chk_udaraku_fail_buzzer_enabled = QCheckBox(
            "Bunyikan buzzer setiap kali satu kiriman ke udaraku gagal"
        )
        self.chk_udaraku_fail_buzzer_enabled.setChecked(True)
        form_fail.addRow(self.chk_udaraku_fail_buzzer_enabled)

        self.sp_udaraku_fail_buzzer_pattern = ThemedSpinBox()
        self.sp_udaraku_fail_buzzer_pattern.setRange(1, 10)
        self.sp_udaraku_fail_buzzer_pattern.setValue(3)
        form_fail.addRow("Pola Buzzer (jumlah bunyi):", self.sp_udaraku_fail_buzzer_pattern)
        v_notif.addLayout(form_fail)

        lbl_success_header = QLabel("<b>Saat Sukses</b>")
        v_notif.addWidget(lbl_success_header)

        form_success = QFormLayout()
        self.chk_udaraku_success_buzzer_enabled = QCheckBox(
            "Bunyikan buzzer setiap kali kirim realtime sukses"
        )
        self.chk_udaraku_success_buzzer_enabled.setChecked(True)
        form_success.addRow(self.chk_udaraku_success_buzzer_enabled)

        self.sp_udaraku_success_buzzer_pattern = ThemedSpinBox()
        self.sp_udaraku_success_buzzer_pattern.setRange(1, 10)
        self.sp_udaraku_success_buzzer_pattern.setValue(1)
        form_success.addRow(
            "Pola Buzzer (jumlah bunyi):", self.sp_udaraku_success_buzzer_pattern
        )
        v_notif.addLayout(form_success)

        layout.addWidget(grp_notif)

        h_btn = QHBoxLayout()
        btn_get_udaraku = QPushButton("Muat Konfigurasi Udaraku dari Device")
        btn_get_udaraku.clicked.connect(
            lambda: self.send_json_command({"cmd": "GET_CONFIG"}, ui_button=btn_get_udaraku)
        )
        btn_sync_udaraku = QPushButton("Sync Configuration")
        btn_sync_udaraku.setObjectName("btnPrimary")
        btn_sync_udaraku.clicked.connect(
            lambda: self.sync_udaraku_config(ui_button=btn_sync_udaraku)
        )
        h_btn.addWidget(btn_get_udaraku)
        h_btn.addWidget(btn_sync_udaraku)
        h_btn.addStretch()
        layout.addLayout(h_btn)

        grp_status = QGroupBox("Status Pengiriman ke Udaraku")
        v_status = QVBoxLayout(grp_status)

        h_badge = QHBoxLayout()
        self.lbl_udaraku_status = QLabel("Belum ada aktivitas")
        self.lbl_udaraku_status.setObjectName("statusBadgeDisconnected")
        self.lbl_udaraku_status.setAlignment(Qt.AlignCenter)
        h_badge.addWidget(self.lbl_udaraku_status)
        h_badge.addStretch()
        v_status.addLayout(h_badge)

        form_status = QFormLayout()
        self.lbl_udaraku_last_send = QLabel("--")
        self.lbl_udaraku_response = QLabel("--")
        self.lbl_udaraku_response.setTextFormat(Qt.PlainText)
        self.lbl_udaraku_queue = QLabel("--")
        form_status.addRow("Terakhir kirim:", self.lbl_udaraku_last_send)
        form_status.addRow("Respons udaraku:", self.lbl_udaraku_response)
        form_status.addRow("Sisa antrian:", self.lbl_udaraku_queue)
        v_status.addLayout(form_status)

        layout.addWidget(grp_status)
        layout.addStretch()

    def _refresh_udaraku_kanal_checkboxes(self):
        """Bangun ulang checkbox kanal udaraku dari daftar widget dashboard
        (self.sensor_config) -- dipanggil dari _rebuild_sensor_cards()
        supaya daftar kanal yang bisa dipilih selalu mengikuti sensor yang
        terdaftar di tab Dashboard Designer, tanpa daftar statis terpisah
        yang gampang basi (lihat diskusi: opsi 9).

        PERBAIKAN (ditemukan lewat pengujian hardware -- lihat log
        UDARAKU_STATUS "tidak ada kanal bernilai" di setiap kirim): key di
        self.sensor_config memakai format path bertitik ala threshold,
        mis. "sensors.t" (lihat default widget & KNOWN_NUMERIC_PAYLOAD_KEYS
        di atas), BUKAN kode kanal mentah yang dipakai firmware di
        telemetry["sensors"]/cfg["kanal"] ("t", "h", "batt" -- lihat
        payload_manager.build_telemetry()). Sebelum perbaikan ini, kanal
        yang dikirim ke firmware berupa "sensors.t"/"sensors.h", yang tidak
        pernah cocok dengan kode asli "t"/"h" di firmware -- akibatnya
        SEMUA kanal selalu terfilter habis, persis gejala yang dilaporkan.
        Perbaikannya: hanya widget dengan prefix "sensors." yang dijadikan
        opsi kanal (widget lain, mis. "wifi.rssi", BUKAN bagian dari
        payload sensors yang dikirim ke udaraku -- dilewati), dan
        checkbox di-key oleh kode MENTAH setelah prefix dibuang, supaya
        `kanal` yang dikirim ke SET_UDARAKU_CONFIG cocok dengan yang
        difilter firmware."""
        if not hasattr(self, "_kanal_checkbox_layout"):
            return  # tab udaraku belum dibuat (dipanggil sebelum setup_tab_udaraku)

        # Pertahankan pilihan yang sedang tercentang di GUI sebelum widget
        # lama dihapus, supaya menambah/menghapus satu sensor tidak ikut
        # menghapus pilihan kanal yang sudah dicentang untuk sensor lain.
        # Kalau checkbox belum pernah dibangun sama sekali (panggilan
        # pertama saat init), pakai config tersimpan sebagai sumber awal.
        if self._chk_udaraku_kanal:
            previously_checked = {
                key for key, chk in self._chk_udaraku_kanal.items() if chk.isChecked()
            }
        else:
            previously_checked = set(
                self.config.get("udaraku", {}).get("kanal") or []
            )

        while self._kanal_checkbox_layout.count():
            item = self._kanal_checkbox_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._chk_udaraku_kanal = {}
        dilewati_bukan_sensor = []
        for cfg in self.sensor_config:
            payload_key = cfg.get("key", "")
            if not payload_key.startswith("sensors."):
                # Bukan bagian dari telemetry["sensors"] (mis. "wifi.rssi")
                # -- udaraku hanya mengirim kanal dari "sensors", jadi
                # widget ini tidak relevan sebagai opsi kanal.
                if payload_key:
                    dilewati_bukan_sensor.append(payload_key)
                continue
            kode = payload_key[len("sensors."):]
            if not kode or kode in self._chk_udaraku_kanal:
                continue
            label = cfg.get("label", kode)
            chk = QCheckBox(f"{label} ({kode})")
            chk.setChecked(kode in previously_checked)
            self._kanal_checkbox_layout.addWidget(chk)
            self._chk_udaraku_kanal[kode] = chk

        if not self._chk_udaraku_kanal:
            pesan = "Belum ada widget sensor (\"sensors.*\") terdaftar di tab Dashboard Designer."
            if dilewati_bukan_sensor:
                pesan += f" ({len(dilewati_bukan_sensor)} widget lain dilewati karena bukan kanal sensor.)"
            self._kanal_checkbox_layout.addWidget(QLabel(pesan))

    def _load_udaraku_controls_from_config(self):
        """Isi kontrol Tab 7 dari config PC yang tersimpan lokal (sebelum
        pernah GET_CONFIG dari device). Checkbox kanal harus sudah dibangun
        oleh _refresh_udaraku_kanal_checkboxes() (dipanggil dari
        _rebuild_sensor_cards() sebelum method ini di __init__) supaya
        tanda centang di bawah ini punya widget untuk diisi."""
        udaraku_cfg = self.config.get("udaraku", {})
        self.chk_udaraku_enabled.setChecked(bool(udaraku_cfg.get("enabled", False)))
        self.txt_udaraku_url.setText(str(udaraku_cfg.get("url", "")))
        self.txt_udaraku_key.setText(str(udaraku_cfg.get("key", "")))
        self.txt_udaraku_kode_alat.setText(str(udaraku_cfg.get("kode_alat", "")))
        self.sp_udaraku_interval.setValue(int(udaraku_cfg.get("interval_sec", 60)))
        self.chk_udaraku_queue_enabled.setChecked(bool(udaraku_cfg.get("queue_enabled", True)))
        self.sp_udaraku_queue_interval.setValue(int(udaraku_cfg.get("queue_interval_sec", 5)))
        self.sp_udaraku_timeout.setValue(int(udaraku_cfg.get("timeout_sec", 15)))
        self.chk_udaraku_fail_buzzer_enabled.setChecked(
            bool(udaraku_cfg.get("fail_buzzer_enabled", True))
        )
        self.sp_udaraku_fail_buzzer_pattern.setValue(
            int(udaraku_cfg.get("fail_buzzer_pattern", 3))
        )
        self.chk_udaraku_success_buzzer_enabled.setChecked(
            bool(udaraku_cfg.get("success_buzzer_enabled", True))
        )
        self.sp_udaraku_success_buzzer_pattern.setValue(
            int(udaraku_cfg.get("success_buzzer_pattern", 1))
        )
        kanal_tersimpan = set(udaraku_cfg.get("kanal") or [])
        for key, chk in self._chk_udaraku_kanal.items():
            chk.setChecked(key in kanal_tersimpan)

    def sync_udaraku_config(self, ui_button=None):
        """Kirim konfigurasi udaraku (Tab 7) ke ESP32 untuk disimpan ke
        flash lewat command SET_UDARAKU_CONFIG."""
        kanal = [key for key, chk in self._chk_udaraku_kanal.items() if chk.isChecked()]
        udaraku_payload = {
            "enabled": self.chk_udaraku_enabled.isChecked(),
            "url": self.txt_udaraku_url.text().strip().rstrip("/"),
            "key": self.txt_udaraku_key.text(),
            "kode_alat": self.txt_udaraku_kode_alat.text().strip(),
            "interval_sec": self.sp_udaraku_interval.value(),
            "queue_enabled": self.chk_udaraku_queue_enabled.isChecked(),
            "queue_interval_sec": self.sp_udaraku_queue_interval.value(),
            "timeout_sec": self.sp_udaraku_timeout.value(),
            "kanal": kanal,
            "fail_buzzer_enabled": self.chk_udaraku_fail_buzzer_enabled.isChecked(),
            "fail_buzzer_pattern": self.sp_udaraku_fail_buzzer_pattern.value(),
            "success_buzzer_enabled": self.chk_udaraku_success_buzzer_enabled.isChecked(),
            "success_buzzer_pattern": self.sp_udaraku_success_buzzer_pattern.value(),
        }
        if udaraku_payload["enabled"] and not udaraku_payload["url"]:
            QMessageBox.warning(
                self, "Peringatan",
                "URL Endpoint tidak boleh kosong kalau pengiriman ke udaraku diaktifkan."
            )
            return
        if udaraku_payload["enabled"] and not udaraku_payload["key"]:
            QMessageBox.warning(
                self, "Peringatan",
                "Bearer Key tidak boleh kosong kalau pengiriman ke udaraku diaktifkan."
            )
            return
        self.config["udaraku"] = udaraku_payload
        self.persist_config()
        self.send_json_command(
            {"cmd": "SET_UDARAKU_CONFIG", "udaraku": udaraku_payload}, ui_button=ui_button
        )

    def _handle_udaraku_status(self, data):
        """Menampilkan status pengiriman ke udaraku real-time. Dikirim
        firmware setiap kali selesai satu upaya POST (realtime maupun
        antrian), TIDAK menunggu diminta GUI. Bentuk payload yang
        diharapkan (disepakati untuk implementasi firmware selanjutnya --
        menggantikan pesan string polos yang dibuang diam-diam oleh
        dashboard versi sebelumnya, lihat catatan migrasi):

        {"type": "UDARAKU_STATUS", "mode": "realtime"|"queue",
         "success": true/false, "http_status": 200, "message": "...",
         "timestamp": "2026-07-29 10:00:00", "queue_pending": 3}
        """
        success = bool(data.get("success"))
        mode = str(data.get("mode", "--"))
        mode_label = "Realtime" if mode == "realtime" else "Antrian" if mode == "queue" else mode

        if not success:
            fail_reason = data.get("message") or data.get("http_status") or "tidak diketahui"
            self.log_terminal(
                "WARNING", f"Kirim ke udaraku gagal ({mode_label}): {fail_reason}", "#e67e22"
            )
        if data.get("recovered"):
            self.log_terminal(
                "INFO", "Koneksi ke udaraku PULIH setelah sempat gagal.", "#16a085"
            )

        if success:
            self.lbl_udaraku_status.setObjectName("statusBadgeConnected")
            self.lbl_udaraku_status.setText(f"Sukses ({mode_label})")
        else:
            self.lbl_udaraku_status.setObjectName("statusBadgeError")
            self.lbl_udaraku_status.setText(f"Gagal ({mode_label})")
        self.lbl_udaraku_status.style().unpolish(self.lbl_udaraku_status)
        self.lbl_udaraku_status.style().polish(self.lbl_udaraku_status)

        ts = data.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S"))
        self.lbl_udaraku_last_send.setText(str(ts))

        http_status = data.get("http_status")
        message = data.get("message", "")
        if message:
            pesan_text = str(message)
        else:
            pesan_text = "Terverifikasi, tanpa pesan tambahan" if success else "Tidak ada pesan dari udaraku"
        resp = f"HTTP {http_status} -- {pesan_text}" if http_status is not None else pesan_text
        # textFormat sudah di-set PlainText saat widget dibuat -- jangan
        # dibungkus html.escape() (lihat catatan yang sama di versi lama
        # untuk jalur server: itu untuk konteks rich text, bukan QLabel ini).
        self.lbl_udaraku_response.setText(resp)

        if "queue_pending" in data:
            self.lbl_udaraku_queue.setText(str(data.get("queue_pending")))
