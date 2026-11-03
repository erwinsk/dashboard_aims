"""Jendela utama LoggerDashboard -- merakit semua mixin."""

import html
import time

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget

from aims_dashboard.config import (
    LEGACY_PAYLOAD_ALIASES, load_config, save_config,
)
from aims_dashboard.mixins.connection import ConnectionMixin
from aims_dashboard.mixins.device_config import DeviceConfigMixin
from aims_dashboard.mixins.file_transfer import FileTransferMixin
from aims_dashboard.mixins.layout_helpers import LayoutHelpersMixin
from aims_dashboard.mixins.protocol import ProtocolMixin
from aims_dashboard.mixins.tab_calibration import CalibrationTabMixin
from aims_dashboard.mixins.tab_control import ControlTabMixin
from aims_dashboard.mixins.tab_custom import CustomTabMixin
from aims_dashboard.mixins.tab_dashboard import DashboardTabMixin
from aims_dashboard.mixins.tab_network import NetworkTabMixin
from aims_dashboard.mixins.tab_sdcard import SdCardTabMixin
from aims_dashboard.mixins.tab_terminal import TerminalTabMixin
from aims_dashboard.mixins.tab_udaraku import UdarakuTabMixin
from aims_dashboard.mixins.telemetry import TelemetryMixin
from aims_dashboard.mixins.theme_mixin import ThemeMixin
from aims_dashboard.screen import (
    _available_screen_geometry, compute_adaptive_window_geometry,
)


class LoggerDashboard(
    LayoutHelpersMixin,
    ThemeMixin,
    ConnectionMixin,
    ProtocolMixin,
    TelemetryMixin,
    DashboardTabMixin,
    NetworkTabMixin,
    ControlTabMixin,
    DeviceConfigMixin,
    SdCardTabMixin,
    FileTransferMixin,
    TerminalTabMixin,
    CustomTabMixin,
    UdarakuTabMixin,
    CalibrationTabMixin,
    QMainWindow,
):
    """Jendela utama aplikasi. Perilaku dipisah ke mixin per tab/fungsi
    (lihat paket aims_dashboard.mixins); di sini hanya state inti."""

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.setWindowTitle("Sistem Kontrol & Telemetri Logger ESP32 (UI V2)")

        win_w, win_h, min_w, min_h = compute_adaptive_window_geometry()
        self.setMinimumSize(min_w, min_h)
        self.resize(win_w, win_h)
        self._center_on_screen()

        # Terapkan tema tampilan yang tersimpan. Preferensi ini hanya untuk GUI PC.
        self._apply_theme(persist=False)

        self.worker = None
        # SN device yang profil kalibrasinya sedang aktif di
        # self.config["calibration"]/["calibration_points"], dan flag
        # supaya GET_IDENTITY otomatis cuma dikirim SEKALI per sesi koneksi
        # (dipicu begitu ada baris data pertama masuk -- lihat
        # handle_incoming_data -- bukan langsung saat klik Connect, supaya
        # tidak terkirim saat device masih boot/reset). Diisi dari
        # device_identity yang tersimpan di config.json sesi sebelumnya
        # dulu (asumsi awal: "calibration" aktif saat ini masih milik SN
        # itu) -- akan otomatis dikoreksi begitu GET_IDENTITY sesi baru
        # menjawab dengan SN yang beda.
        self._active_device_sn = str(
            self.config.get("device_identity", {}).get("sn") or ""
        ).strip() or None
        self._identity_requested_this_session = False
        self.is_recording = False
        self.csv_file = None
        self.csv_fh = None
        self.csv_writer = None
        self.csv_widget_keys = []
        self.csv_widget_labels = []
        self.csv_timestamp_header = "Timestamp PC"
        self.csv_interval_sec = 1.0
        self._last_csv_write_ts = 0.0

        self.hb_count = 0
        self.last_hb_time = None
        self.start_time = time.time()

        # State navigasi folder SD Card. "" berarti root (mount point SD).
        # Path relatif ini yang dikirim ke firmware lewat parameter "path"
        # di LIST_LOGS, dan digabung dengan nama file saat GET_FILE/DELETE_FILE
        # supaya file di dalam subfolder tetap bisa diakses.
        self.sd_current_path = ""

        self.payload_registry = {}
        self.latest_payload = {}
        self.history = {}
        self.pending_commands = {}
        self.command_seq = 0

        # Menyimpan progress download file yang sedang berjalan (protokol
        # ber-chunk: FILE_START -> beberapa FILE_CHUNK -> FILE_END), key-nya
        # adalah command id supaya tidak tertukar kalau ada beberapa
        # permintaan GET_FILE yang id-nya berbeda.
        self.file_downloads = {}

        # Menampung item hasil scan WiFi yang datang satu-per-satu
        # (SCAN_START -> beberapa SCAN_ITEM -> SCAN_END), key-nya command id.
        self.wifi_scans = {}

        self.sensor_labels = {}
        self.sensor_curves = {}
        self.sensor_x = {}
        self.sensor_y = {}

        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self._setup_top_bar()

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 12, 14, 14)
        body_layout.addWidget(self.tabs)
        self.main_layout.addWidget(body)

        self.tab_dashboard = QWidget()
        self.tab_network = QWidget()
        self.tab_sdcard = QWidget()
        self.tab_control = QWidget()
        self.tab_terminal = QWidget()
        self.tab_custom = QWidget()
        self.tab_udaraku = QWidget()
        self.tab_calibration = QWidget()

        self.tabs.addTab(self.tab_dashboard, "📊  Dashboard && Grafik")
        self.tabs.addTab(self.tab_network, "📶  Network && RTC")
        self.tabs.addTab(self.tab_sdcard, "💾  SD Card")
        self.tabs.addTab(self.tab_control, "🎚️  Kontrol && Threshold")
        self.tabs.addTab(self.tab_terminal, "🖥️  Terminal Log")
        self.tabs.addTab(self.tab_custom, "🎨  Dashboard Designer")
        self.tabs.addTab(self.tab_udaraku, "☁️  Kirim ke Udaraku")
        self.tabs.addTab(self.tab_calibration, "🛠️  Kalibrasi && Identitas")

        self.setup_tab_dashboard()
        self.setup_tab_network()
        self.setup_tab_sdcard()
        self.setup_tab_control()
        self.setup_tab_terminal()
        self.setup_tab_custom()
        self.setup_tab_udaraku()
        self.setup_tab_calibration()

        # _rebuild_sensor_cards() dipanggil sebelum _load_udaraku_controls_
        # from_config() dengan sengaja: yang pertama membangun checkbox
        # kanal dari sensor_config (lihat _refresh_udaraku_kanal_checkboxes,
        # dipanggil dari dalamnya), yang kedua baru menandai kanal mana yang
        # tercentang sesuai config tersimpan. Urutan terbalik akan membuat
        # tanda centang yang sudah dimuat langsung hilang lagi.
        self._rebuild_sensor_cards()
        self._rebuild_sensor_curves()
        self.refresh_payload_registry_ui()
        self.refresh_threshold_table()
        self._load_logging_controls_from_config()
        self._load_udaraku_controls_from_config()
        self._update_calibration_table()
        self._load_identity_display_from_config()
        self._update_active_profile_label()

        # Terapkan ulang setelah seluruh widget dibuat agar elemen seperti
        # pyqtgraph dan custom spinbox juga menerima warna/font tema yang aktif.
        self._apply_theme(persist=False)

        self.timer_pc_time = QTimer()
        self.timer_pc_time.timeout.connect(self.update_pc_clock)
        self.timer_pc_time.start(1000)

        self.timer_pending = QTimer()
        self.timer_pending.timeout.connect(self.check_pending_commands)
        self.timer_pending.start(250)

    @property
    def sensor_config(self):
        return self.config.setdefault("dashboard", {}).setdefault("widgets", [])

    @property
    def thresholds(self):
        return self.config.setdefault("thresholds", [])

    def persist_config(self):
        save_config(self.config)

    def _normalize_threshold_record(self, threshold):
        """
        Samakan nama field threshold end-to-end:
        id, payload, operator, value, buzzer, interval_sec, enabled.
        """
        if not isinstance(threshold, dict):
            return {}
        out = dict(threshold)
        payload = str(out.get("payload", "")).strip()
        if not payload:
            return {}
        payload = LEGACY_PAYLOAD_ALIASES.get(payload, payload)
        out["payload"] = payload
        out["operator"] = str(out.get("operator", ">"))
        try:
            out["value"] = float(out.get("value", 0))
        except (TypeError, ValueError):
            out["value"] = 0.0
        try:
            out["buzzer"] = int(out.get("buzzer", 1))
        except (TypeError, ValueError):
            out["buzzer"] = 1
        try:
            out["interval_sec"] = int(out.get("interval_sec", 300))
        except (TypeError, ValueError):
            out["interval_sec"] = 300
        if out["interval_sec"] < 1:
            out["interval_sec"] = 1
        out["enabled"] = bool(out.get("enabled", True))
        if "id" in out:
            try:
                out["id"] = int(out["id"])
            except (TypeError, ValueError):
                pass
        return out

    def log_terminal(self, tag, message, color="#2c3e50"):
        """Fungsi pembantu untuk menulis log ke terminal secara rapi.

        PERBAIKAN BUG: `message` (dan `tag`) sebelumnya disisipkan MENTAH ke
        string HTML. Kalau isinya mengandung karakter '<', '>', atau '&'
        (mis. payload threshold berisi operator "<" atau "<="), Qt membaca
        karakter itu sebagai awal tag HTML, bukan teks biasa -- sisa baris
        jadi "hilang" dari tampilan meski data asli yang terkirim ke serial
        tetap utuh. Sekarang di-escape lewat html.escape() dulu supaya '<',
        '>', '&' selalu tampil apa adanya sebagai teks.
        """
        timestamp = time.strftime("%H:%M:%S")
        safe_tag = html.escape(str(tag))
        safe_message = html.escape(str(message))
        line = (
            f'<span style="color:#7f8c8d; font-size:11px;">[{timestamp}]</span> '
            f'<strong style="color:{color}; font-size:11px">[{safe_tag}]</strong> '
            f'<span style="font-size:11px">{safe_message}</span>'
        )
        self.txt_log.append(line)

    def update_pc_clock(self):
        self.lbl_time_pc.setText(
            f"Waktu PC: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}"
        )

    def closeEvent(self, event):
        self._close_csv_file()
        self.persist_config()
        if self.worker:
            self.worker.stop()
            self.worker = None
        event.accept()

    def _center_on_screen(self):
        """Posisikan jendela di tengah layar aktif -- berguna khususnya di
        monitor besar (2K/4K) supaya window tidak "nyangkut" di pojok
        kiri-atas layar, dan tetap benar di layar kecil/multi-monitor."""
        avail = _available_screen_geometry()
        if avail is None:
            return
        frame = self.frameGeometry()
        x = avail.x() + max(0, (avail.width() - frame.width()) // 2)
        y = avail.y() + max(0, (avail.height() - frame.height()) // 2)
        self.move(x, y)
