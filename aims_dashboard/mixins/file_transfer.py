"""Penerimaan file dari device (START/CHUNK/END) + checksum."""

from PyQt5.QtWidgets import QFileDialog, QMessageBox

from aims_dashboard.config import format_file_size


class FileTransferMixin:
    """Penerimaan file dari device (START/CHUNK/END) + checksum."""

    def _handle_file_start(self, data):
        """
        Awal transfer file ber-chunk (balasan atas GET_FILE).

        PERBAIKAN: sebelumnya dialog "Simpan File" langsung dibuka di sini
        dan file ditulis ke disk per-chunk begitu diterima. Masalahnya,
        dialog simpan itu MODAL -- selama menunggu user memilih lokasi,
        chunk yang keburu datang dari ESP32 dibuang begitu saja (state
        penyimpanannya belum ada). Untuk file kecil, seluruh transfer bisa
        selesai SEBELUM user sempat klik "Save", sehingga hasil akhirnya
        0 bytes walau ACK-nya "ok". Sekarang isi file ditampung dulu di
        memori sampai FILE_END, baru dialog simpan dibuka dan file ditulis
        sekali jalan -- tidak ada lagi celah kehilangan chunk.
        """
        cid = data.get("id")
        self._touch_pending_command(cid)

        filename = str(data.get("filename", "downloaded_file.txt"))
        size = data.get("size", 0)

        self.file_downloads[cid] = {
            "filename": filename,
            "size": size,
            "chunks": [],
            "received_bytes": 0,
            # PERBAIKAN: lacak potongan yang gagal checksum ("cks") supaya
            # file yang korup di jalur serial tidak diam-diam disimpan
            # seolah-olah utuh (lihat catatan perbaikan di firmware,
            # FILE_CHUNK_SIZE, soal akar masalahnya).
            "bad_seqs": [],
            "cks_sum": 0,
        }
        self.lbl_ack.setText(f"Download\n{filename} 0%")

        size_text = format_file_size(size) if size else "?"
        self.lbl_sd_progress.setText(f"Mengunduh '{filename}' (0 B / {size_text})...")
        self.progress_sd_download.setRange(0, 100 if size else 0)
        self.progress_sd_download.setValue(0)

    @staticmethod
    def _checksum16(text):
        """Checksum 16-bit sederhana (sum-of-bytes mod 65536), harus sama
        persis dengan _checksum16() di firmware (main.py) supaya tiap chunk
        bisa diverifikasi begitu diterima."""
        total = 0
        for b in text.encode("utf-8", errors="ignore"):
            total = (total + b) & 0xFFFF
        return total

    def _handle_file_chunk(self, data):
        """Tampung satu potongan isi file di memori (belum ditulis ke disk),
        dan verifikasi checksum-nya kalau firmware menyertakannya."""
        cid = data.get("id")
        self._touch_pending_command(cid)

        state = self.file_downloads.get(cid)
        if not state:
            return

        chunk = str(data.get("data", ""))
        seq = data.get("seq")
        state["chunks"].append(chunk)
        state["received_bytes"] += len(chunk.encode("utf-8", errors="ignore"))

        # PERBAIKAN: verifikasi checksum tiap chunk begitu diterima. Kalau
        # firmware tidak menyertakan "cks" (mis. firmware lama), lewati
        # validasi ini secara diam-diam (backward compatible).
        expected_cks = data.get("cks")
        if expected_cks is not None:
            actual_cks = self._checksum16(chunk)
            state["cks_sum"] = (state.get("cks_sum", 0) + actual_cks) & 0xFFFF
            if actual_cks != expected_cks:
                state["bad_seqs"].append(seq)
                self.log_terminal(
                    "ERR",
                    f"Chunk #{seq} file '{state['filename']}' gagal verifikasi checksum "
                    f"(kemungkinan korup di jalur serial).",
                    "#c0392b"
                )

        size = state.get("size") or 0
        received = state["received_bytes"]
        size_text = format_file_size(size) if size else "?"
        received_text = format_file_size(received)

        if size:
            pct = min(100, int(received * 100 / size))
            self.lbl_ack.setText(f"Download\n{state['filename']} {pct}%")
            self.progress_sd_download.setValue(pct)
        else:
            self.lbl_ack.setText(f"Download\n{state['filename']} {received}B")

        warn = f" -- {len(state['bad_seqs'])} chunk korup!" if state["bad_seqs"] else ""
        self.lbl_sd_progress.setText(
            f"Mengunduh '{state['filename']}' ({received_text} / {size_text}){warn}"
        )

    def _handle_file_end(self, data):
        """Transfer selesai (atau gagal di tengah jalan): baru sekarang minta
        lokasi simpan dan tulis seluruh isi file yang sudah ditampung."""
        cid = data.get("id")
        self._touch_pending_command(cid)

        state = self.file_downloads.pop(cid, None)
        if not state:
            return

        filename = state["filename"]
        received_text = format_file_size(state["received_bytes"])

        if data.get("aborted"):
            self.log_terminal("ERR", f"Download '{filename}' terhenti di tengah jalan (firmware error).", "#c0392b")
            self.lbl_sd_progress.setText(f"Download '{filename}' gagal (terhenti di tengah jalan).")
            self.progress_sd_download.setValue(0)
            return

        # PERBAIKAN: verifikasi keutuhan file SEBELUM ditawarkan untuk
        # disimpan. Kalau ada chunk yang gagal checksum, atau checksum total
        # yang dihitung PC tidak cocok dengan "cks_sum" yang dilaporkan
        # firmware, peringatkan pengguna dengan jelas -- daripada diam-diam
        # menyimpan file yang isinya rusak (ini akar masalah di log lama).
        bad_seqs = state.get("bad_seqs", [])
        expected_total_cks = data.get("cks_sum")
        total_mismatch = (
            expected_total_cks is not None and state.get("cks_sum", 0) != expected_total_cks
        )
        is_corrupted = bool(bad_seqs) or total_mismatch

        content = "".join(state["chunks"])

        if is_corrupted:
            detail = f"{len(bad_seqs)} chunk gagal checksum" if bad_seqs else "checksum total tidak cocok"
            self.log_terminal(
                "ERR",
                f"File '{filename}' terindikasi KORUP saat transfer serial ({detail}). "
                f"Disarankan mengulang download.",
                "#c0392b"
            )
            self.lbl_sd_progress.setText(f"'{filename}' terindikasi korup ({detail}). Coba download ulang.")
            self.progress_sd_download.setValue(0)
            proceed = QMessageBox.warning(
                self, "File Kemungkinan Korup",
                f"'{filename}' terdeteksi korup saat transfer lewat serial ({detail}).\n\n"
                "Ini biasanya karena gangguan transien di jalur serial, bukan file aslinya "
                "yang rusak di SD Card. Disarankan klik Download lagi.\n\n"
                "Simpan hasil yang ada sekarang (mungkin ada data hilang/salah)?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if proceed != QMessageBox.Yes:
                self.log_terminal("INFO", f"Download '{filename}' yang korup dibuang (tidak disimpan).", "#7f8c8d")
                return
        else:
            self.lbl_sd_progress.setText(f"'{filename}' selesai diunduh ({received_text}).")
            self.progress_sd_download.setValue(100)

        save_path, _ = QFileDialog.getSaveFileName(
            self, f"Simpan '{filename}' ({received_text})", filename, "All Files (*)"
        )
        if not save_path:
            self.log_terminal("INFO", f"Download '{filename}' dibatalkan (tidak disimpan).", "#7f8c8d")
            return

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(content)
            self.log_terminal(
                "INFO",
                f"File '{filename}' berhasil disimpan ke {save_path} ({received_text})",
                "#16a085"
            )
            QMessageBox.information(
                self, "Download Selesai",
                f"File berhasil disimpan:\n{save_path}\n\nUkuran: {received_text}"
            )
        except Exception as exc:
            self.log_terminal("ERR", f"Gagal menyimpan file '{filename}': {exc}", "#c0392b")
            QMessageBox.critical(self, "Error", f"Gagal menyimpan file:\n{exc}")
