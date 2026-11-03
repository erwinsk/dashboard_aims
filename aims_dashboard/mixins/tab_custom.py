"""Tab Custom (Dashboard Designer berbasis splitter)."""

from PyQt5.QtWidgets import (
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QVBoxLayout,
)


class CustomTabMixin:
    """Tab Custom (Dashboard Designer berbasis splitter)."""

    def setup_tab_custom(self):
        """Dua tabel besar (Widget Dashboard & Payload Registry) ditumpuk
        di tab ini -- kandidat paling gampang "berebut" ruang vertikal di
        layar kecil. Sama seperti tab SD Card, dipecah lewat
        _new_splitter_tab_layout supaya user bisa menarik manual proporsi
        ruang antara dua tabel ini sesuai kebutuhan saat itu."""
        splitter = self._new_splitter_tab_layout(self.tab_custom)

        # --- Panel 1: Widget Dashboard (Value Card) ---------------------
        pane_widgets = self._add_splitter_pane(splitter, stretch=1)
        grp_widgets = QGroupBox("Widget Dashboard (Value Card)")
        vw = QVBoxLayout(grp_widgets)

        self.table_widgets = self._make_expanding_table(min_height=140)
        # Simplified columns
        self.table_widgets.setColumnCount(6)
        self.table_widgets.setHorizontalHeaderLabels([
            "No", "Payload Key", "Label", "Unit", "Desimal", "Graph & CSV"
        ])
        self.table_widgets.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_widgets.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widgets.setEditTriggers(QTableWidget.NoEditTriggers)
        vw.addWidget(self.table_widgets, stretch=1)

        hw = QHBoxLayout()
        b_add = QPushButton("Tambah Widget")
        b_add.setObjectName("btnPrimary")
        b_add.clicked.connect(self.add_dashboard_widget)

        b_edit = QPushButton("Edit Widget")
        b_edit.clicked.connect(self.edit_dashboard_widget)

        b_delete = QPushButton("Hapus Widget")
        b_delete.setObjectName("btnDanger")
        b_delete.clicked.connect(self.delete_dashboard_widget)

        b_up = QPushButton("Naik")
        b_up.clicked.connect(lambda: self.move_widget(-1))

        b_down = QPushButton("Turun")
        b_down.clicked.connect(lambda: self.move_widget(1))

        b_save = QPushButton("Simpan Konfigurasi")
        b_save.setObjectName("btnSuccess")
        b_save.clicked.connect(self.save_dashboard_config)

        for b in [b_add, b_edit, b_delete, b_up, b_down, b_save]:
            hw.addWidget(b)
        hw.addStretch()
        vw.addLayout(hw)
        pane_widgets.addWidget(grp_widgets, stretch=1)

        # --- Panel 2: Payload Registry -----------------------------------
        pane_payload = self._add_splitter_pane(splitter, stretch=1)
        grp_payload = QGroupBox("Payload Registry — key yang terdeteksi dari JSON")
        vp = QVBoxLayout(grp_payload)

        self.table_payload = self._make_expanding_table(min_height=140)
        self.table_payload.setColumnCount(5)
        self.table_payload.setHorizontalHeaderLabels([
            "Payload Key", "Tipe", "Nilai Terakhir", "Dipakai Dashboard", "Label CSV (SD)"
        ])
        self.table_payload.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_payload.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_payload.setEditTriggers(QTableWidget.NoEditTriggers)
        vp.addWidget(self.table_payload, stretch=1)

        hp = QHBoxLayout()
        b_refresh = QPushButton("Refresh Registry")
        b_refresh.clicked.connect(self.refresh_payload_registry_ui)
        hp.addWidget(b_refresh)

        b_edit_label = QPushButton("Edit Label CSV")
        b_edit_label.clicked.connect(self.edit_sensor_label)
        hp.addWidget(b_edit_label)

        b_sync_labels = QPushButton("Kirim Label ke Device")
        b_sync_labels.setObjectName("btnSuccess")
        b_sync_labels.clicked.connect(self.sync_sensor_labels)
        hp.addWidget(b_sync_labels)

        hp.addStretch()
        vp.addLayout(hp)
        pane_payload.addWidget(grp_payload, stretch=1)

        self.lbl_dashboard_info = QLabel()
        self.lbl_dashboard_info.setWordWrap(True)
        pane_payload.addWidget(self.lbl_dashboard_info)

        # Bagi rata dua panel sejak awal dibuka -- user tetap bebas
        # menarik ulang garis pembatasnya lewat handle splitter.
        splitter.setSizes([390, 390])
