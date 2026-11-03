"""Tab SD Card: konfigurasi logger + browse/download/delete file."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from aims_dashboard.config import format_file_size
from aims_dashboard.widgets import ThemedSpinBox


class SdCardTabMixin:
    """Tab SD Card: konfigurasi logger + browse/download/delete file."""

    def setup_tab_sdcard(self):
        """Tab SD Card dipecah jadi 2 panel BERDAMPINGAN (kiri-kanan) lewat
        QSplitter horizontal (_new_splitter_tab_layout, orientation=
        Qt.Horizontal): KIRI = Konfigurasi Logger, KANAN = Browse SD Card.
        Dengan susunan ini tabel file di kanan mendapat SELURUH tinggi tab
        (sebelumnya, susunan atas-bawah membuatnya berbagi tinggi dengan
        panel konfigurasi, sehingga di layar 1366x768 cuma muat beberapa
        baris dan sisanya tidak kelihatan). Garis pembatas kiri-kanan tetap
        bisa DITARIK MANUAL oleh user kapan saja."""
        splitter = self._new_splitter_tab_layout(self.tab_sdcard, Qt.Horizontal)

        self.lbl_sd_detail = QLabel("Status SD Card: --")
        self.lbl_sd_detail.setObjectName("statusCard")
        # Panel kiri sekarang lebih sempit dari lebar tab penuh -- teks
        # status yang panjang harus membungkus baris, bukan memaksa panel
        # melebar.
        self.lbl_sd_detail.setWordWrap(True)

        # --- Panel KIRI: Konfigurasi Logger (Data & System) -------------
        pane_config = self._add_splitter_pane(splitter, stretch=2)
        pane_config.addWidget(self.lbl_sd_detail)

        # Konfigurasi Data Logger & System Logger (disimpan ke flash ESP32
        # lewat command SET_LOGGING_CONFIG, terpisah dari config WiFi/mode/
        # threshold supaya tidak saling menimpa).
        grp_logging = QGroupBox("Konfigurasi Logger (Data & System)")
        v_log = QVBoxLayout(grp_logging)

        form_data = QFormLayout()
        self.chk_data_enabled = QCheckBox("Aktif")
        self.chk_data_enabled.setChecked(True)
        self.sp_data_interval = ThemedSpinBox()
        self.sp_data_interval.setRange(1, 86400)
        self.sp_data_interval.setValue(60)
        self.sp_data_interval.setSuffix(" detik")
        self.sp_data_retention = ThemedSpinBox()
        self.sp_data_retention.setRange(1, 365)
        self.sp_data_retention.setValue(7)
        self.sp_data_retention.setSuffix(" hari")
        form_data.addRow("Data Logger:", self.chk_data_enabled)
        form_data.addRow("Interval:", self.sp_data_interval)
        form_data.addRow("Retention:", self.sp_data_retention)
        v_log.addLayout(form_data)

        form_sys = QFormLayout()
        self.chk_system_enabled = QCheckBox("Aktif")
        self.chk_system_enabled.setChecked(True)
        self.sp_system_retention = ThemedSpinBox()
        self.sp_system_retention.setRange(1, 365)
        self.sp_system_retention.setValue(30)
        self.sp_system_retention.setSuffix(" hari")
        form_sys.addRow("System Logger:", self.chk_system_enabled)
        form_sys.addRow("Retention:", self.sp_system_retention)
        v_log.addLayout(form_sys)

        # Tombol disusun VERTIKAL (bukan berjajar horizontal seperti
        # sebelumnya): panel kiri sekarang sempit, dua tombol berjajar
        # dengan teks panjang akan memaksa lebar minimum panel membengkak
        # dan menyempitkan panel browse di kanan.
        btn_get_logging = QPushButton("Muat Konfigurasi Logger dari Device")
        btn_get_logging.clicked.connect(
            lambda: self.send_json_command({"cmd": "GET_CONFIG"}, ui_button=btn_get_logging)
        )
        btn_sync_logging = QPushButton("Sync Configuration")
        btn_sync_logging.setObjectName("btnPrimary")
        btn_sync_logging.clicked.connect(
            lambda: self.sync_logging_config(ui_button=btn_sync_logging)
        )
        v_log.addWidget(btn_get_logging)
        v_log.addWidget(btn_sync_logging)

        pane_config.addWidget(grp_logging)
        pane_config.addStretch()

        # --- Panel KANAN: Browse SD Card (navigasi + tabel file + progress) ---
        pane_browse = self._add_splitter_pane(splitter, stretch=3)

        # Navigasi folder: breadcrumb menunjukkan path saat ini + tombol
        # untuk naik ke folder induk. Path disimpan di self.sd_current_path
        # dan dikirim ke firmware sebagai parameter "path" di LIST_LOGS
        # (implementasi firmware-nya menyusul di sesi berikutnya).
        h_nav = QHBoxLayout()
        self.btn_sd_up = QPushButton("⬆ Kembali")
        self.btn_sd_up.setEnabled(False)
        self.btn_sd_up.clicked.connect(self.go_sd_parent)
        self.lbl_sd_breadcrumb = QLabel("📁 /")
        self.lbl_sd_breadcrumb.setObjectName("statusCard")
        h_nav.addWidget(self.btn_sd_up)
        h_nav.addWidget(self.lbl_sd_breadcrumb, stretch=1)
        pane_browse.addLayout(h_nav)

        h = QHBoxLayout()
        btn = QPushButton("Refresh Daftar File Log")
        btn.setObjectName("btnPrimary")
        btn.clicked.connect(lambda: self.refresh_sd_listing(ui_button=btn))
        h.addWidget(btn)
        h.addStretch()
        pane_browse.addLayout(h)

        self.table_files = self._make_expanding_table(min_height=180)
        self.table_files.setColumnCount(3)
        self.table_files.setHorizontalHeaderLabels(["Nama File", "Ukuran", "Aksi"])
        self.table_files.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_files.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table_files.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table_files.setColumnWidth(1, 90)
        self.table_files.setColumnWidth(2, 190)
        self.table_files.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_files.setSelectionBehavior(QTableWidget.SelectRows)
        # Double-click pada baris folder langsung masuk ke folder itu,
        # sama seperti klik tombol "Buka" di kolom Aksi.
        self.table_files.cellDoubleClicked.connect(self._on_sd_row_double_clicked)
        pane_browse.addWidget(self.table_files, stretch=1)

        # Progress download: sebelumnya progress cuma muncul sebagai teks kecil
        # di kartu ACK umum di atas. Sekarang ditambahkan progress bar +
        # label khusus di tab SD Card ini, supaya ukuran file & progress
        # transfer terlihat jelas tanpa harus melihat tab lain.
        grp_progress = QGroupBox("Progress Download")
        vp = QVBoxLayout(grp_progress)
        self.lbl_sd_progress = QLabel("Belum ada download berjalan.")
        self.progress_sd_download = QProgressBar()
        self.progress_sd_download.setRange(0, 100)
        self.progress_sd_download.setValue(0)
        self.progress_sd_download.setTextVisible(True)
        vp.addWidget(self.lbl_sd_progress)
        vp.addWidget(self.progress_sd_download)
        pane_browse.addWidget(grp_progress)

        # Lebar awal panel: "Browse SD Card" (kanan) dapat porsi lebih besar
        # daripada "Konfigurasi Logger" (kiri) -- tabel file butuh lebar
        # untuk kolom Nama File + Ukuran + Aksi. Ini hanya PROPORSI awal
        # (Qt menskalakannya ke lebar tab sebenarnya); user tetap bebas
        # menarik ulang garis pembatasnya kapan saja lewat handle splitter.
        splitter.setSizes([380, 620])

    def _populate_file_table(self, files):
        self.table_files.setRowCount(0)
        for entry in files:
            # PERBAIKAN: firmware sekarang mengirim tiap entri sebagai dict
            # {"name":..., "size":..., "dir":...} supaya ukuran file bisa
            # ditampilkan. Tetap dukung format lama (string nama saja) kalau
            # firmware belum di-update, supaya GUI tidak error.
            if isinstance(entry, dict):
                filename = str(entry.get("name", ""))
                size = entry.get("size")
                is_dir = bool(entry.get("dir"))
            else:
                filename = str(entry)
                size = None
                is_dir = False

            if not filename:
                continue

            row = self.table_files.rowCount()
            self.table_files.insertRow(row)
            self.table_files.setItem(row, 0, QTableWidgetItem(filename))

            size_text = "Folder" if is_dir else (format_file_size(size) if size is not None else "--")
            item_size = QTableWidgetItem(size_text)
            item_size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table_files.setItem(row, 1, item_size)

            action_widget = QWidget()
            h = QHBoxLayout(action_widget)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(4)

            if is_dir:
                # Folder: tombol "Buka" untuk masuk ke dalamnya (sama seperti
                # double-click baris), tidak ada Download/Delete untuk folder
                # sistem seperti "System Volume Information" supaya aman.
                bo = self._make_compact_table_button("Buka")
                bo.clicked.connect(lambda _, f=filename: self.open_sd_folder(f))
                h.addWidget(bo)
            else:
                bd = self._make_compact_table_button("Download")
                bd.clicked.connect(
                    lambda _, f=filename, b=bd: self.send_json_command({
                        "cmd": "GET_FILE", "filename": self._sd_join(self.sd_current_path, f)
                    }, ui_button=b)
                )
                bx = self._make_compact_table_button("Delete")
                bx.clicked.connect(lambda _, f=filename: self.delete_log_file(f))
                h.addWidget(bd)
                h.addWidget(bx)
            self.table_files.setCellWidget(row, 2, action_widget)
            self.table_files.setRowHeight(row, 28)

    def _sd_join(self, path, name):
        """Gabungkan path folder saat ini dengan nama file/folder, hasil path
        relatif tanpa leading slash (mis. "logs_csv/2026-07-27-data.csv")."""
        path = (path or "").strip("/")
        name = (name or "").strip("/")
        if not path:
            return name
        if not name:
            return path
        return f"{path}/{name}"

    def _sd_parent(self, path):
        """Hitung path folder induk. Root ("") tetap root."""
        path = (path or "").strip("/")
        if "/" not in path:
            return ""
        return path.rsplit("/", 1)[0]

    def _update_sd_breadcrumb(self):
        display = self.sd_current_path.strip("/")
        self.lbl_sd_breadcrumb.setText(f"📁 /{display}" if display else "📁 /")
        self.btn_sd_up.setEnabled(bool(display))

    def refresh_sd_listing(self, ui_button=None):
        """Minta daftar isi folder SD Card saat ini (self.sd_current_path) ke firmware."""
        self._update_sd_breadcrumb()
        self.send_json_command(
            {"cmd": "LIST_LOGS", "path": self.sd_current_path}, ui_button=ui_button
        )

    def open_sd_folder(self, folder_name):
        """Masuk ke subfolder (dipanggil dari tombol 'Buka' atau double-click baris folder)."""
        self.sd_current_path = self._sd_join(self.sd_current_path, folder_name)
        self.refresh_sd_listing()

    def go_sd_parent(self):
        """Naik ke folder induk."""
        self.sd_current_path = self._sd_parent(self.sd_current_path)
        self.refresh_sd_listing()

    def _on_sd_row_double_clicked(self, row, _column):
        item = self.table_files.item(row, 1)
        if item is not None and item.text() == "Folder":
            name_item = self.table_files.item(row, 0)
            if name_item is not None:
                self.open_sd_folder(name_item.text())

    def delete_log_file(self, filename):
        if QMessageBox.question(
            self, "Konfirmasi Hapus",
            f"Yakin ingin menghapus file '{filename}' dari SD Card?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            self.send_json_command({
                "cmd": "DELETE_FILE",
                "filename": self._sd_join(self.sd_current_path, filename),
            })
