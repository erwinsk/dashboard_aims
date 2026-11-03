"""Helper pembuat layout tab/splitter/tombol tabel dan top bar."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QTableWidget, QVBoxLayout, QWidget,
)


class LayoutHelpersMixin:
    """Helper pembuat layout tab/splitter/tombol tabel dan top bar."""

    def _setup_top_bar(self):
        """Bar permanen di atas tab (bukan di dalam tab manapun) -- judul
        aplikasi + kontrol koneksi serial (port, connect, badge status).
        Sebelumnya kontrol ini terkubur di dalam groupbox tab 1 saja,
        sehingga operator harus pindah ke tab Dashboard dulu untuk sekadar
        connect/disconnect. Widget (`cb_ports`, `btn_connect`,
        `lbl_conn_status`) TETAP dibuat dengan nama atribut yang sama --
        semua logic yang mereferensikannya di tempat lain tidak berubah."""
        bar = QFrame()
        bar.setObjectName("topBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(20, 12, 20, 12)
        h.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        lbl_title = QLabel("AiMS Kontrol")
        lbl_title.setObjectName("appTitle")
        lbl_subtitle = QLabel("Logger Sensor SHT31 — ESP32-S3")
        lbl_subtitle.setObjectName("appSubtitle")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_subtitle)
        h.addLayout(title_box)

        h.addSpacing(28)
        h.addWidget(QLabel("Port:"))

        self.cb_ports = QComboBox()
        self.cb_ports.setMinimumWidth(170)
        h.addWidget(self.cb_ports)

        btn_ref = QPushButton("⟳")
        btn_ref.setToolTip("Refresh daftar port serial")
        # Tidak ada lagi override lebar khusus -- dengan padding QPushButton
        # yang sekarang seragam (6px 16px) di semua tombol, tombol ikon ini
        # otomatis proporsional dengan tombol "Connect" di sebelahnya, tanpa
        # risiko ikon kepotong seperti versi fixed-width sebelumnya.
        btn_ref.clicked.connect(self.refresh_ports)
        h.addWidget(btn_ref)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setObjectName("btnPrimary")
        self.btn_connect.clicked.connect(self.toggle_connection)
        h.addWidget(self.btn_connect)

        h.addStretch()

        # Tombol Pengaturan Tampilan -- sengaja ditaruh di top bar (bukan
        # di salah satu tab pengaturan alat), karena ini murni preferensi
        # GUI/PC, tidak berhubungan dengan konfigurasi device.
        btn_theme = QPushButton("🎨")
        btn_theme.setToolTip("Pengaturan Tampilan (tema warna aplikasi)")
        btn_theme.clicked.connect(self.open_theme_dialog)
        h.addWidget(btn_theme)

        self.lbl_conn_status = QLabel("Disconnected")
        self.lbl_conn_status.setObjectName("statusBadgeDisconnected")
        self.lbl_conn_status.setAlignment(Qt.AlignCenter)
        h.addWidget(self.lbl_conn_status)

        self.main_layout.addWidget(bar)
        self.refresh_ports()

    def _new_tab_layout(self, tab_widget):
        """Layout dasar tiap tab: dibungkus QScrollArea supaya kalau jendela
        di-resize kecil (atau tab isinya padat, mis. "Kirim ke Server"),
        konten SCROLL alih-alih terpotong atau numpuk vertikal. Margin &
        spacing sengaja sedang (bukan besar) sesuai masukan -- cukup
        untuk "napas" tanpa terasa boros ruang. Nama widget yang dipasang
        lewat layout ini tidak berubah sama sekali, jadi semua logic tetap
        utuh."""
        outer = QVBoxLayout(tab_widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(14)

        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return layout

    def _new_splitter_tab_layout(self, tab_widget, orientation=Qt.Vertical):
        """Alternatif _new_tab_layout() untuk tab yang isinya beberapa
        panel "berat" (tabel besar dsb) yang saling berebut ruang di layar
        kecil (mis. laptop 1360x768). Bedanya dengan _new_tab_layout():
        konten TIDAK dibungkus QScrollArea, melainkan QSplitter yang
        memenuhi seluruh area tab -- jadi setiap panel benar-benar dapat
        jatah ruang (bukan cuma sizeHint alami), DAN user bisa menarik
        manual garis pembatas antar panel (splitter handle) untuk
        memperbesar salah satu panel dengan mengecilkan panel lain.

        `orientation`: Qt.Vertical (default, panel bertumpuk atas-bawah --
        dipakai tab Dashboard Designer) atau Qt.Horizontal (panel
        berdampingan kiri-kanan -- dipakai tab SD Card, supaya tabel file
        mendapat SELURUH tinggi tab alih-alih berbagi tinggi dengan panel
        konfigurasi di atasnya).

        Return QSplitter kosong -- panggil self._add_splitter_pane() untuk
        menambah tiap panel (kembaliannya QVBoxLayout, dipakai persis
        seperti layout dari _new_tab_layout())."""
        outer = QVBoxLayout(tab_widget)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        splitter = QSplitter(orientation)
        # False supaya panel tidak bisa "ditarik sampai hilang total" ke
        # ukuran 0 -- selalu ada minimumSizeHint layout di dalamnya yang
        # dihormati, jadi user tetap bisa menarik balik.
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        outer.addWidget(splitter, stretch=1)
        return splitter

    def _add_splitter_pane(self, splitter, stretch=1):
        """Tambah satu panel baru ke splitter dari _new_splitter_tab_layout().
        `stretch` menentukan proporsi ruang awal panel ini relatif ke
        panel lain (dipakai lewat setStretchFactor setelah semua panel
        ditambahkan oleh pemanggil) -- besaran pastinya tetap bisa ditarik
        manual oleh user lewat splitter handle kapan saja setelah itu."""
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        splitter.addWidget(pane)
        splitter.setStretchFactor(splitter.count() - 1, stretch)
        return layout

    def _make_compact_table_button(self, text):
        """Tombol kecil khusus untuk ditaruh DI DALAM sel tabel (lewat
        setCellWidget) -- lihat _populate_file_table() dan tombol "Kirim"
        di table_threshold. Tombol QPushButton biasa di app ini memakai
        padding tema global (6px 12px, ~34px tinggi -- nyaman untuk layar
        normal/sentuh), tapi kalau dipakai DI DALAM baris tabel, tinggi itu
        ikut menentukan tinggi SATU BARIS tabel. Di layar kecil (1366x768)
        dengan panel splitter yang sudah sempit (lihat
        _new_splitter_tab_layout), ini membuat cuma 3-4 baris yang
        kelihatan sebelum perlu scroll -- baris sisanya jadi tidak
        kelihatan (laporan nyata: baris file di SD Card tidak kelihatan/
        tidak bisa didownload). Tombol di sini sengaja dibuat lebih
        pendek & padding lebih tipis, HANYA untuk konteks dalam tabel --
        warna/border tetap ikut tema (diwariskan dari stylesheet global,
        cuma padding & tinggi yang dioverride di sini), dan tombol normal
        di tempat lain SAMA SEKALI TIDAK ikut berubah."""
        btn = QPushButton(text)
        btn.setFixedHeight(24)
        btn.setStyleSheet("QPushButton { padding: 2px 8px; }")
        return btn

    def _make_expanding_table(self, min_height=160):
        """QTableWidget dengan size policy Expanding (bukan default
        Preferred) supaya benar-benar memakai ruang tambahan yang
        dialokasikan panel splitter/layout di sekitarnya, plus tinggi
        minimum yang wajar supaya tetap menampilkan beberapa baris di
        layar kecil (1360x768 dst.) tanpa perlu di-scroll dulu."""
        table = QTableWidget()
        table.setMinimumHeight(min_height)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return table

    def _make_card(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("statusCard")
        lbl.setAlignment(Qt.AlignCenter)
        return lbl
