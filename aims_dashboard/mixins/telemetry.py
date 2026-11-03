"""Pengolahan telemetri & perekaman CSV dinamis."""

import csv
import time

from PyQt5.QtWidgets import QFileDialog, QMessageBox

from aims_dashboard.config import KNOWN_NUMERIC_PAYLOAD_KEYS


class TelemetryMixin:
    """Pengolahan telemetri & perekaman CSV dinamis."""

    @staticmethod
    def _resolve_payload_value(data, key):
        """
        Ambil nilai payload untuk `key`, mendukung dot-notation untuk field
        di dalam dict nested (mis. "wifi.rssi" -> data["wifi"]["rssi"]).
        Mengembalikan (value, found).
        """
        if key in data:
            return data[key], True
        if "." in key:
            cur = data
            for part in key.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return None, False
            return cur, True
        return None, False

    def _handle_telemetry(self, data):
        now = time.time() - self.start_time

        for cfg in self.sensor_config:
            if not isinstance(cfg, dict):
                continue
            key = cfg.get("key")
            if not key:
                continue
            value, found = self._resolve_payload_value(data, key)
            if not found:
                continue
            if key in self.sensor_labels:
                decimals = int(cfg.get("decimals", 1))
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    text = f"{value:.{decimals}f}"
                else:
                    text = str(value)
                unit = cfg.get("unit", "")
                self.sensor_labels[key].setText(
                    f"{cfg.get('label', key)}\n{text} {unit}".strip()
                )

            if (
                key in self.sensor_curves
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                self.sensor_x[key].append(now)
                self.sensor_y[key].append(value)
                self.sensor_curves[key].setData(
                    list(self.sensor_x[key]), list(self.sensor_y[key])
                )

        mode = data.get("mode")
        if mode is not None:
            display = {
                "always_on": "Always On",
                "deep_sleep": "Deep Sleep"
            }.get(str(mode), str(mode))
            self.lbl_mode.setText(f"Mode Daya\n{display}")
            self.lbl_current_mode.setText(f"Mode Saat Ini: {display}")
            self.config.setdefault("device", {})["mode"] = str(mode)

        if "sleep_sec" in data:
            try:
                sleep_sec = int(data["sleep_sec"])
                self.config.setdefault("device", {})["deep_sleep_sec"] = sleep_sec
                if hasattr(self, "sp_deep_sleep"):
                    self.sp_deep_sleep.blockSignals(True)
                    self.sp_deep_sleep.setValue(sleep_sec)
                    self.sp_deep_sleep.blockSignals(False)
            except (TypeError, ValueError):
                pass

        # Nested Wi-Fi payload support
        wifi_data = data.get("wifi")
        if isinstance(wifi_data, dict):
            wifi_conn = bool(wifi_data.get("connected", False))
            rssi = wifi_data.get("rssi")
            ssid = wifi_data.get("ssid", "")
            ip = wifi_data.get("ip", "")
            
            text = "Terhubung" if wifi_conn else "Terputus"
            if wifi_conn and ssid: text += f"\nSSID: {ssid}"
            if wifi_conn and rssi is not None: text += f"\nRSSI: {rssi} dBm"
            self.lbl_wifi.setText(f"WiFi\n{text}")

            # PERBAIKAN: sebelumnya "if ip:" -- kalau device disconnect,
            # firmware mengirim ip="" (falsy), jadi baris ini dilewati dan
            # label Alamat IP tetap menampilkan IP lama selamanya. Sekarang
            # selalu di-set sesuai status koneksi: ada IP kalau terhubung,
            # "--" kalau tidak.
            self.lbl_ip.setText(f"Alamat IP\n{ip if (wifi_conn and ip) else '--'}")
        # Flat fallback
        elif "w" in data:
            wifi = bool(data["w"])
            rssi = data.get("rssi")
            text = "Terhubung" if wifi else "Terputus"
            if wifi and rssi is not None:
                text += f"\n{rssi} dBm"
            self.lbl_wifi.setText(f"WiFi\n{text}")

        if "ip" in data and not isinstance(wifi_data, dict):
            self.lbl_ip.setText(f"Alamat IP\n{data['ip']}")

        if "sd_init" in data:
            ok = bool(data["sd_init"])
            self.lbl_sd_stat.setText(f"SD Card\n{'OK' if ok else 'ERROR'}")
            self.lbl_sd_detail.setText(
                f"Status SD Card: {'Terdeteksi & Normal' if ok else 'Gagal/Tidak Ada'}"
            )

        if "rtc_time" in data:
            self.lbl_time_rtc.setText(f"Waktu RTC Perangkat: {data['rtc_time']}")

        self.update_dashboard_info()

        if self.is_recording and self.csv_writer:
            self.write_dynamic_csv(data)

    def _get_graph_csv_widgets(self):
        widgets = []
        for cfg in self.sensor_config:
            if not isinstance(cfg, dict):
                continue
            key = str(cfg.get("key", "")).strip()
            if not key or not cfg.get("show_graph", True):
                continue
            widgets.append(cfg)
        return widgets

    def toggle_record_csv(self):
        if not self.is_recording:
            filepath, _ = QFileDialog.getSaveFileName(
                self, "Simpan File CSV", "", "CSV Files (*.csv)"
            )
            if not filepath:
                return

            try:
                self.csv_file = filepath
                self.csv_fh = open(filepath, "w", newline="", encoding="utf-8-sig")

                graph_widgets = self._get_graph_csv_widgets()
                self.csv_widget_keys = [cfg["key"] for cfg in graph_widgets]
                self.csv_widget_labels = [str(cfg.get("label", cfg["key"])) for cfg in graph_widgets]

                self.csv_writer = csv.writer(
                    self.csv_fh, delimiter=";", lineterminator="\n"
                )

                headers = [self.csv_timestamp_header, *self.csv_widget_labels]
                self.csv_writer.writerow(headers)
                self.csv_fh.flush()

                self.csv_interval_sec = self.sp_csv_interval.value()
                self._last_csv_write_ts = 0.0  # baris pertama langsung ditulis

                self.is_recording = True
                self.btn_record.setText("Stop Record CSV")
                self._set_button_role(self.btn_record, "btnDanger")

                widget_text = ", ".join(self.csv_widget_labels) if self.csv_widget_labels else "(tidak ada)"
                self.log_terminal(
                    "INFO",
                    f"Recording started: {filepath} ({widget_text}) | interval {self.csv_interval_sec}s",
                    "#16a085"
                )

            except Exception as exc:
                self._close_csv_file()
                QMessageBox.critical(self, "Error", f"Gagal membuka CSV: {exc}")

        else:
            self.is_recording = False
            self._close_csv_file()
            self.btn_record.setText("Start Record CSV")
            self._set_button_role(self.btn_record, "btnSuccess")
            QMessageBox.information(self, "Info", "Perekaman CSV dihentikan.")
            self.log_terminal("INFO", "Recording stopped.", "#16a085")

    def write_dynamic_csv(self, data):
        if not self.csv_writer or not self.csv_fh:
            return
        # PERBAIKAN: dulu setiap telemetri masuk (~1x/detik) langsung ditulis
        # sebagai baris baru, tanpa opsi mengatur jaraknya. Sekarang baris
        # baru hanya ditulis kalau sudah melewati csv_interval_sec sejak
        # baris terakhir -- telemetri lain di antaranya tetap dipakai untuk
        # update kartu/grafik seperti biasa, cuma tidak ikut direkam ke CSV.
        now = time.monotonic()
        if now - self._last_csv_write_ts < self.csv_interval_sec:
            return
        self._last_csv_write_ts = now
        try:
            timestamp_pc = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            row = [timestamp_pc]
            for key in self.csv_widget_keys:
                value, found = self._resolve_payload_value(data, key)
                row.append(value if found else "")
            self.csv_writer.writerow(row)
            self.csv_fh.flush()
        except Exception as exc:
            self.log_terminal("ERR", f"CSV Error: {exc}", "#c0392b") # Red

    def _close_csv_file(self):
        if self.csv_fh:
            try:
                self.csv_fh.close()
            except Exception:
                pass
        self.csv_fh = None
        self.csv_writer = None
        self.csv_widget_keys = []
        self.csv_widget_labels = []

    @staticmethod
    def _sensor_base_key(key):
        """Payload TELEMETRY sekarang nesting semua sensor di bawah
        "sensors": {...} (mis. path GUI "sensors.t"), TAPI firmware
        (payload_manager.py) tetap memakai key MENTAH tanpa prefix untuk
        kalibrasi (SET_CALIBRATION) dan label CSV (SET_SENSOR_LABELS) --
        keduanya diterapkan pada isi dict "sensors", bukan pada path
        top-level yang sudah di-nesting. Helper ini memetakan
        "sensors.t" -> "t"; key lain (mis. "wifi.rssi") dikembalikan
        apa adanya karena tidak relevan untuk kalibrasi/label CSV."""
        if key.startswith("sensors."):
            return key.split(".", 1)[1]
        return key

    def get_payload_keys(self, numeric_only=False):
        keys = set(self.payload_registry.keys())
        keys.update(
            cfg.get("key") for cfg in self.sensor_config
            if isinstance(cfg, dict) and cfg.get("key")
        )
        if numeric_only:
            # KNOWN_NUMERIC_PAYLOAD_KEYS masuk tanpa syarat (statis, sesuai
            # skema firmware saat ini) -- key lain (mis. widget custom yang
            # ditambah user) tetap difilter lewat data live supaya key
            # non-numerik tidak nyasar ke dropdown Threshold.
            keys.update(KNOWN_NUMERIC_PAYLOAD_KEYS)
            keys = {
                k for k in keys
                if k in KNOWN_NUMERIC_PAYLOAD_KEYS
                or (
                    k in self.latest_payload
                    and isinstance(self.latest_payload[k], (int, float))
                    and not isinstance(self.latest_payload[k], bool)
                )
            }
        return sorted(keys)
