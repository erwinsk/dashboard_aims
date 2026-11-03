"""Kirim perintah, terima data, dispatch, ACK, heartbeat, pending command."""

import html
import json
import time
from collections import deque

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox

from aims_dashboard.config import MAX_POINTS


class ProtocolMixin:
    """Kirim perintah, terima data, dispatch, ACK, heartbeat, pending command."""

    def send_command(self, cmd, expect_ack=False, timeout=5.0, ui_button=None):
        if not self.worker:
            QMessageBox.warning(self, "Peringatan", "Perangkat belum terhubung secara serial.")
            if ui_button:
                ui_button.setEnabled(True)
                ui_button.setText(ui_button.property("original_text"))
            return None

        command_id = None
        if expect_ack:
            self.command_seq += 1
            command_id = self.command_seq
            self.pending_commands[command_id] = {
                "cmd": cmd,
                "sent": time.time(),
                "timeout": timeout,
                "ui_button": ui_button,
                "action": "RAW"
            }

        if self.worker.write_data(cmd):
            self.log_terminal("OUT", cmd, "#8e44ad") # Purple
            return command_id
        return None

    def send_json_command(self, payload, expect_ack=True, ui_button=None):
        # Cek koneksi lebih dulu, SEBELUM tombol diubah ke status "Loading...".
        # Kalau tidak, saat device belum terhubung, tombol akan macet disabled
        # selama masa timeout ACK (beberapa detik) padahal sudah jelas gagal
        # sejak awal (send_command_without_new_id tidak menerima ui_button
        # sehingga tidak bisa mengembalikan status tombol dengan segera).
        if not self.worker:
            QMessageBox.warning(self, "Peringatan", "Perangkat belum terhubung secara serial.")
            return None

        payload = dict(payload)

        # Loading Feedback for UI Button
        if ui_button:
            ui_button.setProperty("original_text", ui_button.text())
            ui_button.setEnabled(False)
            ui_button.setText("Loading...")
            
        if expect_ack:
            self.command_seq += 1
            payload["id"] = self.command_seq
            cid = payload["id"]
            cmd_text = json.dumps(payload, separators=(",", ":"))
            # GET_FILE sekarang dikirim ber-chunk (bisa berupa banyak pesan
            # serial berturut-turut untuk file besar), jadi butuh timeout ACK
            # yang jauh lebih longgar daripada perintah biasa. Timeout ini
            # tetap "di-reset" tiap kali chunk baru masuk lewat
            # _touch_pending_command(), jadi 90 detik ini cuma jaring
            # pengaman kalau transfer benar-benar macet total.
            action_timeout = 90.0 if payload.get("cmd") == "GET_FILE" else 6.0
            self.pending_commands[cid] = {
                "cmd": cmd_text,
                "sent": time.time(),
                "timeout": action_timeout,
                "ui_button": ui_button,
                "action": payload.get("cmd", "UNKNOWN")
            }
            return self.send_command_without_new_id(cmd_text)
        return self.send_command(json.dumps(payload, separators=(",", ":")), False, ui_button=ui_button)

    def send_command_without_new_id(self, cmd):
        if not self.worker:
            QMessageBox.warning(self, "Peringatan", "Perangkat belum terhubung secara serial.")
            return None
        if self.worker.write_data(cmd):
            self.log_terminal("OUT", cmd, "#8e44ad") # Purple
            return True
        return False

    def send_custom_command(self):
        cmd = self.txt_cmd.text().strip()
        if cmd:
            self.send_command(cmd, expect_ack=False)
            self.txt_cmd.clear()

    def handle_incoming_data(self, raw_data):
        """Slot yang dipanggil worker.data_received.emit() dari thread lain
        (queued connection lintas thread). PERBAIKAN (crash nyata yang
        pernah teramati -- lihat catatan di handle_ack()): seluruh isi
        method ini dibungkus try/except supaya SATU baris data yang
        memicu error tak terduga di mana pun (bug lain, race kondisi
        widget yang sudah dihapus, dll.) tidak lagi menjatuhkan SELURUH
        proses (sebelumnya: RuntimeError tak tertangani di sini bisa
        membuat aplikasi core-dump -- dashboard jadi "diam total" tanpa
        pesan apa pun terlihat kalau dijalankan bukan dari terminal).
        Error tak terduga sekarang dicatat ke Terminal Log, koneksi serial
        TIDAK diputus, siklus data berikutnya tetap diproses normal."""
        try:
            self._dispatch_incoming_data(raw_data)
        except Exception as exc:
            self.log_terminal(
                "ERR", f"Galat tak terduga saat memproses data masuk: {exc!r}", "#c0392b"
            )

    def _dispatch_incoming_data(self, raw_data):
        self.log_terminal("IN", raw_data, "#34495e") # Dark Blue/Gray
        self._update_heartbeat()

        # PERBAIKAN: minta identitas (SN) device otomatis begitu ada tanda
        # device benar-benar hidup & mengirim data (baris pertama masuk) --
        # bukan langsung saat tombol Connect diklik, karena port baru
        # dibuka belum tentu device-nya sudah selesai boot/reset. SN inilah
        # yang dipakai untuk memilih profil kalibrasi mana yang aktif
        # (lihat _handle_identity), jadi harus otomatis, tidak menunggu
        # operator klik "Ambil Identitas dari Device" secara manual.
        if self.worker is not None and not self._identity_requested_this_session:
            self._identity_requested_this_session = True
            self.send_json_command({"cmd": "GET_IDENTITY"})

        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            # PERBAIKAN: baris yang gagal di-parse dulu dibuang diam-diam,
            # jadi kalau ada korupsi data di jalur serial (mis. akibat
            # brownout LDO saat WiFi scan), pengguna tidak tahu apa-apa
            # selain "hasilnya tidak muncul". Sekarang tetap dicatat sebagai
            # error di terminal supaya kelihatan jelas ada baris yang rusak.
            self.log_terminal(
                "ERR",
                f"Baris tidak bisa di-parse (kemungkinan korup di jalur serial): {raw_data[:200]}",
                "#c0392b"
            )
            return

        if not isinstance(data, dict):
            return

        self._register_payloads(data)

        if data.get("type") == "ACK" or "ack" in data:
            self.handle_ack(data)

        if data.get("type") in ("HB", "TELEMETRY", "DATA", "STATUS") or any(
            cfg.get("key") in data for cfg in self.sensor_config if isinstance(cfg, dict)
        ) or "wifi" in data:
            self._handle_telemetry(data)

        if data.get("type") == "SCAN_START":
            self._handle_scan_start(data)
        elif data.get("type") == "SCAN_ITEM":
            self._handle_scan_item(data)
        elif data.get("type") == "SCAN_END":
            self._handle_scan_end(data)

        if isinstance(data.get("files"), list):
            self._populate_file_table(data["files"])

        if data.get("type") == "FILE_START":
            self._handle_file_start(data)
        elif data.get("type") == "FILE_CHUNK":
            self._handle_file_chunk(data)
        elif data.get("type") == "FILE_END":
            self._handle_file_end(data)

        if data.get("type") == "CONFIG":
            self._handle_device_config(data)

        if data.get("type") == "UDARAKU_STATUS":
            self._handle_udaraku_status(data)

        if data.get("type") == "IDENTITY":
            self._handle_identity(data)

    def _register_payloads(self, data):
        ignored = {
            "type", "ack", "status", "cmd", "id", "message",
            "files", "error"
        }
        now = time.time()

        def _register_one(k, v):
            self.payload_registry[k] = {
                "type": type(v).__name__,
                "last": v,
                "updated": now,
            }
            self.latest_payload[k] = v
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                self.history.setdefault(k, deque(maxlen=MAX_POINTS))
                self.history[k].append((now - self.start_time, v))

        for key, value in data.items():
            if key in ignored:
                continue
            _register_one(key, value)
            # PERBAIKAN: payload nested (mis. "wifi": {"ssid":..,"rssi":..})
            # sebelumnya cuma terdaftar sebagai satu key "wifi" (tipe dict),
            # jadi kalau widget dashboard diarahkan ke field di dalamnya
            # (mis. mengetik "rssi" di Payload Designer), nilainya TIDAK
            # PERNAH match karena "rssi" bukan key top-level -- ini penyebab
            # widget baru yang tidak mau menampilkan nilai. Sekarang field
            # di dalam dict satu level diratakan juga sebagai "wifi.rssi",
            # "wifi.ssid", dst, supaya bisa dipilih & benar-benar ke-update.
            if isinstance(value, dict):
                for subkey, subval in value.items():
                    _register_one(f"{key}.{subkey}", subval)

        # PERBAIKAN: dulu dipanggil refresh_payload_registry_ui() di sini,
        # yang JUGA merombak total tabel Widget Dashboard (Dashboard
        # Designer) setiap payload masuk (~1x/detik) -- akibatnya baris yang
        # sedang dipilih di situ selalu ke-reset sebelum sempat diklik
        # Edit/Hapus. Sekarang cukup refresh tabel Payload Registry saja;
        # tabel Widget Dashboard hanya dirombak saat konfigurasinya memang
        # berubah (tambah/edit/hapus/pindah widget).
        self._update_payload_registry_table()
        self._update_calibration_table()

    def handle_ack(self, data):
        status = str(data.get("status", "ok")).lower()
        cmd = data.get("cmd", data.get("ack", "UNKNOWN"))
        cid = data.get("id")

        if cid is not None and cid in self.pending_commands:
            info = self.pending_commands.pop(cid)
            btn = info.get("ui_button")
            action = info.get("action")

            # Restore Button State
            # PERBAIKAN (crash nyata di lapangan, lihat catatan diskusi
            # migrasi udaraku): ACK bisa datang SETELAH tombol yang
            # memicunya sudah dihapus Qt (paling sering saat aplikasi
            # sedang ditutup -- worker.stop() dipanggil di closeEvent,
            # tapi sinyal data_received yang SUDAH terlanjur di-queue lintas
            # thread sebelum stop() tetap diproses event loop setelah
            # sebagian widget mulai dihancurkan). Referensi Python ke
            # tombol itu (`btn`) tetap "truthy" walau objek C++-nya sudah
            # mati, jadi `if btn:` saja TIDAK cukup -- baru ketahuan saat
            # method dipanggil (RuntimeError: wrapped C/C++ object ...
            # has been deleted), yang tadinya bikin seluruh proses crash
            # (core dumped) dan membuat dashboard terlihat "diam total".
            if btn:
                try:
                    btn.setEnabled(True)
                    btn.setText(btn.property("original_text"))
                except RuntimeError:
                    pass

            # Popups for Wi-Fi commands
            if action in ("WIFI_CONNECT", "WIFI_OFF"):
                if status == "ok":
                    QMessageBox.information(self, "Berhasil", f"Perintah {action} berhasil dijalankan ESP32.")
                else:
                    msg = data.get("message", "Terjadi kesalahan jaringan.")
                    QMessageBox.warning(self, "Gagal", f"Perangkat gagal memproses perintah {action}:\n{msg}")

            # Threshold / config ACK: samakan field yang dibaca GUI dengan
            # field yang dipakai firmware (threshold, thresholds, thresholds_count).
            if action in ("SET_THRESHOLD", "SET_THRESHOLDS", "SET_CONFIG", "GET_CONFIG") and status == "ok":
                ack_thresholds = data.get("thresholds")
                if isinstance(ack_thresholds, list):
                    normalized = []
                    for th in ack_thresholds:
                        norm = self._normalize_threshold_record(th)
                        if norm:
                            normalized.append(norm)
                    if normalized:
                        self.config["thresholds"] = normalized
                        self.refresh_threshold_table()

                ack_threshold = data.get("threshold")
                if isinstance(ack_threshold, dict):
                    norm = self._normalize_threshold_record(ack_threshold)
                    if norm:
                        replaced = False
                        for i, th in enumerate(self.thresholds):
                            if th.get("id") == norm.get("id"):
                                self.thresholds[i] = norm
                                replaced = True
                                break
                        if not replaced and action == "SET_THRESHOLD":
                            self.thresholds.append(norm)
                        self.persist_config()
                        self.refresh_threshold_table()

                if isinstance(data.get("thresholds_count"), int):
                    self.lbl_device_config.setText(
                        f"Tersimpan di flash device — SSID auto-reconnect: <b>{html.escape(str(self.config.get('device', {}).get('wifi_ssid', '(belum ada SSID tersimpan)')))}</b> | "
                        f"Mode default: <b>{html.escape(str(self.config.get('device', {}).get('mode', '--')))}</b> | "
                        f"Threshold tersimpan: <b>{data['thresholds_count']}</b>"
                    )

            # Setelah file berhasil dihapus, refresh otomatis daftar file
            # supaya tabel langsung update tanpa perlu klik Refresh manual.
            # Memakai refresh_sd_listing() (bukan LIST_LOGS polos) supaya
            # path folder yang sedang dibuka tetap sama, bukan balik ke root.
            if action == "DELETE_FILE":
                if status == "ok":
                    self.refresh_sd_listing()
                else:
                    msg = data.get("message", "Terjadi kesalahan.")
                    QMessageBox.warning(self, "Gagal Menghapus", f"Perangkat gagal menghapus file:\n{msg}")

            if action == "GET_FILE" and status != "ok":
                msg = data.get("message", "Terjadi kesalahan.")
                QMessageBox.warning(self, "Gagal Download", f"Perangkat gagal mengirim file:\n{msg}")

        self.lbl_ack.setText(f"ACK\n{cmd}: {status}")
        self.lbl_ack.setStyleSheet(
            "background-color:#d2f8d2;border:1px solid #2ecc71;"
            "border-radius:6px;padding:8px 14px;font-weight:600;"
        )
        QTimer.singleShot(800, lambda: self.lbl_ack.setStyleSheet(""))

        message = data.get("message", "")
        self.log_terminal("ACK", f"cmd={cmd} id={cid} status={status} {message}", "#27ae60")

    def _update_heartbeat(self):
        self.hb_count += 1
        self.last_hb_time = time.strftime("%H:%M:%S")
        self.lbl_heartbeat.setText(f"Heartbeat\n#{self.hb_count} ({self.last_hb_time})")
        self.lbl_heartbeat.setStyleSheet(
            "background-color:#b9f6ca;border:1px solid #2ecc71;"
            "border-radius:6px;padding:8px 14px;font-weight:600;"
        )
        QTimer.singleShot(200, self._reset_heartbeat_style)

    def _reset_heartbeat_style(self):
        if hasattr(self, "lbl_heartbeat"):
            self.lbl_heartbeat.setStyleSheet("")

    def _touch_pending_command(self, cid):
        """
        Reset jam timeout ACK untuk command id tertentu. Dipanggil setiap kali
        ada progress (FILE_START/FILE_CHUNK/FILE_END) untuk download yang
        sedang berjalan, supaya check_pending_commands() tidak menganggapnya
        timeout selama data masih terus mengalir dari ESP32 -- ini yang
        memperbaiki kasus file besar sebelumnya "gagal/timeout" padahal
        firmware sebenarnya masih mengirim.
        """
        if cid is not None and cid in self.pending_commands:
            self.pending_commands[cid]["sent"] = time.time()

    def check_pending_commands(self):
        now = time.time()
        expired = []
        for cid, info in list(self.pending_commands.items()):
            if now - info["sent"] > info["timeout"]:
                expired.append(cid)

        for cid in expired:
            info = self.pending_commands.pop(cid, None)
            if info:
                btn = info.get("ui_button")
                if btn:
                    # Sama seperti di handle_ack() -- lihat catatan di sana.
                    try:
                        btn.setEnabled(True)
                        btn.setText(btn.property("original_text"))
                    except RuntimeError:
                        pass

                self.lbl_ack.setText(f"ACK\nTimeout #{cid}")
                self.log_terminal("ERR", f"ACK TIMEOUT #{cid} untuk {info['action']}", "#c0392b") # Red
