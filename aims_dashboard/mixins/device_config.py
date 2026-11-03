"""Konfigurasi perangkat: deep sleep, reset, push config, logging, display."""

import html

from PyQt5.QtWidgets import QMessageBox


class DeviceConfigMixin:
    """Konfigurasi perangkat: deep sleep, reset, push config, logging, display."""

    def save_deep_sleep_setting(self, value):
        self.config.setdefault("device", {})["deep_sleep_sec"] = int(value)
        self.persist_config()

    def set_always_on_mode(self):
        self.config.setdefault("device", {})["mode"] = "always_on"
        self.persist_config()
        self.send_json_command({
            "cmd": "SET_MODE",
            "mode": "always_on",
        })

    def set_deep_sleep_mode(self):
        seconds = int(self.sp_deep_sleep.value())
        self.config.setdefault("device", {})["mode"] = "deep_sleep"
        self.config.setdefault("device", {})["deep_sleep_sec"] = seconds
        self.persist_config()
        self.send_json_command({
            "cmd": "SET_MODE",
            "mode": "deep_sleep",
            "deep_sleep_sec": seconds,
        })

    def reset_device_action(self):
        reply = QMessageBox.question(
            self, "Konfirmasi Reset",
            "Perangkat akan restart (machine.reset()).\n"
            "Koneksi serial akan terputus sesaat dan tersambung ulang setelah boot.\n\n"
            "Lanjutkan?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.send_json_command({"cmd": "RESET"})

    def _handle_device_config(self, data):
        """Menampilkan config yang dibalas firmware atas GET_CONFIG.

        Bentuk payload yang diharapkan:
        {"type": "CONFIG", "wifi_ssid": "...", "mode": "...", "thresholds": [...]}
        """
        ssid = data.get("wifi_ssid", "(belum ada SSID tersimpan)")
        mode = data.get("mode", "--")
        thresholds = data.get("thresholds", [])
        normalized = []
        if isinstance(thresholds, list):
            for th in thresholds:
                norm = self._normalize_threshold_record(th)
                if norm:
                    normalized.append(norm)
        n_thresh = len(normalized)

        if normalized:
            self.config["thresholds"] = normalized
            self.refresh_threshold_table()

        if "wifi_ssid" in data:
            self.config.setdefault("device", {})["wifi_ssid"] = str(ssid)
        if "mode" in data:
            self.config.setdefault("device", {})["mode"] = str(mode)

        # Sinkronkan interval deep sleep dari GET_CONFIG ke config lokal
        # dan spinbox GUI. Firmware menggunakan key resmi "deep_sleep_sec".
        # blockSignals mencegah perubahan dari device memicu handler
        # perubahan nilai GUI secara tidak sengaja.
        if "deep_sleep_sec" in data:
            try:
                deep_sleep_sec = int(data["deep_sleep_sec"])
                self.config.setdefault("device", {})["deep_sleep_sec"] = deep_sleep_sec
                if hasattr(self, "sp_deep_sleep"):
                    self.sp_deep_sleep.blockSignals(True)
                    self.sp_deep_sleep.setValue(deep_sleep_sec)
                    self.sp_deep_sleep.blockSignals(False)
            except (TypeError, ValueError):
                pass

        logging_cfg = data.get("logging")
        if isinstance(logging_cfg, dict):
            self.config["logging"] = logging_cfg
            self.chk_data_enabled.setChecked(bool(logging_cfg.get("data_enabled", True)))
            self.sp_data_interval.setValue(int(logging_cfg.get("data_interval_sec", 60)))
            self.sp_data_retention.setValue(int(logging_cfg.get("data_retention_days", 7)))
            self.chk_system_enabled.setChecked(bool(logging_cfg.get("system_enabled", True)))
            self.sp_system_retention.setValue(int(logging_cfg.get("system_retention_days", 30)))

        sensor_labels = data.get("sensor_labels")
        if isinstance(sensor_labels, dict):
            self.config["sensor_labels"] = dict(sensor_labels)
            self._update_payload_registry_table()

        calibration = data.get("calibration")
        if isinstance(calibration, dict):
            self.config["calibration"] = dict(calibration)
            self._update_calibration_table()

        # Titik mentah kalibrasi (raw->ref) -- device cuma menitipkannya
        # (tidak pernah memprosesnya), jadi kalau ada di respons GET_CONFIG
        # berarti pernah dikirim dari suatu PC lewat SET_CALIBRATION. Ini
        # jaring pengaman utama saat device dipindah ke PC yang belum
        # punya cache lokal SN ini (lihat _handle_identity).
        calibration_points = data.get("calibration_points")
        if isinstance(calibration_points, dict):
            self.config["calibration_points"] = dict(calibration_points)
        if isinstance(calibration, dict) or isinstance(calibration_points, dict):
            if self._active_device_sn:
                self._snapshot_calibration_into_profile(self._active_device_sn)
            self.persist_config()

        udaraku_cfg = data.get("udaraku")
        if isinstance(udaraku_cfg, dict):
            self.config["udaraku"] = udaraku_cfg
            self._load_udaraku_controls_from_config()

        display_cfg = data.get("display")
        if isinstance(display_cfg, dict):
            self.config["display"] = display_cfg
            if hasattr(self, "sp_display_interval"):
                self.sp_display_interval.blockSignals(True)
                self.sp_display_interval.setValue(int(display_cfg.get("update_interval_sec", 60)))
                self.sp_display_interval.blockSignals(False)
            if hasattr(self, "sp_display_full_refresh"):
                self.sp_display_full_refresh.blockSignals(True)
                self.sp_display_full_refresh.setValue(int(display_cfg.get("full_refresh_interval_min", 30)))
                self.sp_display_full_refresh.blockSignals(False)
        self.lbl_device_config.setText(
            f"Tersimpan di flash device — SSID auto-reconnect: <b>{html.escape(str(ssid))}</b> | "
            f"Mode default: <b>{html.escape(str(mode))}</b> | "
            f"Threshold tersimpan: <b>{n_thresh}</b>"
        )
        self.log_terminal("INFO", "Config device berhasil dimuat dari flash.", "#16a085")

    def push_device_config(self, ui_button=None):
        """Kirim config gabungan (WiFi + mode + threshold) untuk disimpan
        firmware ke flash -- dipakai untuk auto-reconnect & threshold
        persisten setelah reboot. Field WiFi diambil dari input SSID/password
        di tab ini kalau diisi; kalau kosong, firmware diharapkan tetap
        mempertahankan SSID yang sudah tersimpan sebelumnya (tidak menimpa
        dengan string kosong) -- ini perlu dipastikan lagi di implementasi
        firmware sesi berikutnya.
        """
        ssid = self.txt_ssid.text().strip()
        pwd = self.txt_pass.text()
        normalized_thresholds = []
        for th in self.thresholds:
            norm = self._normalize_threshold_record(th)
            if norm:
                normalized_thresholds.append(norm)

        config_payload = {
            "mode": self.config.get("device", {}).get("mode", "always_on"),
            "thresholds": normalized_thresholds,
        }
        if ssid:
            config_payload["wifi_ssid"] = ssid
            config_payload["wifi_password"] = pwd
        self.send_json_command(
            {"cmd": "SET_CONFIG", "config": config_payload}, ui_button=ui_button
        )

    def _load_logging_controls_from_config(self):
        """Isi kontrol Tab 3 dari config PC yang tersimpan lokal (sebelum
        pernah GET_CONFIG dari device)."""
        logging_cfg = self.config.get("logging", {})
        self.chk_data_enabled.setChecked(bool(logging_cfg.get("data_enabled", True)))
        self.sp_data_interval.setValue(int(logging_cfg.get("data_interval_sec", 60)))
        self.sp_data_retention.setValue(int(logging_cfg.get("data_retention_days", 7)))
        self.chk_system_enabled.setChecked(bool(logging_cfg.get("system_enabled", True)))
        self.sp_system_retention.setValue(int(logging_cfg.get("system_retention_days", 30)))

    def sync_logging_config(self, ui_button=None):
        """Kirim konfigurasi Data Logger & System Logger (Tab 3) ke ESP32
        untuk disimpan ke flash lewat command SET_LOGGING_CONFIG."""
        logging_payload = {
            "data_enabled": self.chk_data_enabled.isChecked(),
            "data_interval_sec": self.sp_data_interval.value(),
            "data_retention_days": self.sp_data_retention.value(),
            "system_enabled": self.chk_system_enabled.isChecked(),
            "system_retention_days": self.sp_system_retention.value(),
        }
        self.config["logging"] = logging_payload
        self.persist_config()
        self.send_json_command(
            {"cmd": "SET_LOGGING_CONFIG", "logging": logging_payload}, ui_button=ui_button
        )

    def sync_display_config(self, ui_button=None):
        """Kirim timer refresh e-paper (partial update interval & full
        refresh interval) ke ESP32 untuk disimpan ke flash lewat command
        SET_DISPLAY_CONFIG, dan diterapkan live tanpa perlu reboot."""
        display_payload = {
            "update_interval_sec": self.sp_display_interval.value(),
            "full_refresh_interval_min": self.sp_display_full_refresh.value(),
        }
        self.config["display"] = display_payload
        self.persist_config()
        self.send_json_command(
            {"cmd": "SET_DISPLAY_CONFIG", "display": display_payload}, ui_button=ui_button
        )
