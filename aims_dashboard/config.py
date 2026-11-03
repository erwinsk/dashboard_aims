"""Konstanta aplikasi, DEFAULT_CONFIG, serta load/save device_config.json."""

import json
import os


# Folder induk paket = folder tempat dashboard_aims.py berada (sama seperti
# sebelum kode dipecah), supaya device_config.json tetap di lokasi yang sama.
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


CONFIG_PATH = os.path.join(APP_DIR, "device_config.json")


MAX_POINTS = 300


BUZZER_PATTERN_COUNT = 10


GRAPH_COLORS = [
    "#e74c3c", "#3498db", "#2ecc71", "#f39c12",
    "#9b59b6", "#1abc9c", "#e67e22", "#34495e",
]


# Path payload TELEMETRY yang PASTI ada & numerik sesuai skema firmware
# saat ini (lihat payload_manager.build_telemetry()). Dipakai supaya
# dropdown payload di dialog Threshold tidak kosong sebelum device pernah
# mengirim data sama sekali -- sebelumnya daftar itu 100% bergantung pada
# self.latest_payload (data live), jadi kosong/"hilang" total kalau dialog
# dibuka sebelum device terhubung atau sebelum siklus telemetri pertama
# masuk. Sensor tambahan yang dikirim firmware di masa depan tetap
# otomatis ikut lewat self.latest_payload begitu ada payload live masuk.
KNOWN_NUMERIC_PAYLOAD_KEYS = {"sensors.t", "sensors.h", "sensors.batt", "wifi.rssi"}


# Sebelum payload_manager.py di-restrukturisasi, field sensor threshold
# disimpan FLAT ("t"/"h"/"batt"). Sekarang semuanya nested di bawah
# "sensors" ("sensors.t", dst). Threshold lama yang tersimpan di
# device_config.json dari sebelum migrasi itu masih menyimpan path lama --
# dipetakan otomatis di sini (sama seperti threshold_manager.py di
# firmware) supaya threshold lama "sembuh" begitu dibuka/disimpan lagi,
# tanpa operator perlu edit ulang satu-satu.
LEGACY_PAYLOAD_ALIASES = {"t": "sensors.t", "h": "sensors.h", "batt": "sensors.batt"}


DEFAULT_CONFIG = {
    "version": 1,
    "device": {
        "name": "ESP32 Sensor Logger",
        "baudrate": 115200,
        "mode": "always_on",
        "deep_sleep_sec": 60,
    },
    "dashboard": {
        "widgets": [
            {"key": "sensors.t", "label": "Suhu", "unit": "°C", "decimals": 1, "show_graph": True},
            {"key": "sensors.h", "label": "Kelembaban", "unit": "%", "decimals": 1, "show_graph": True},
        ]
    },
    "thresholds": [],
    "sensor_labels": {},
    "calibration": {},
    # Titik mentah (nilai mentah -> nilai acuan) yang dipakai untuk fitting
    # di Calibration Wizard, per payload key. Disimpan di PC (untuk
    # convenience: mengedit/re-fit tanpa ketik ulang) DAN dikirim ke device
    # lewat SET_CALIBRATION supaya ikut persisten di flash -- device
    # TIDAK memakainya untuk apa pun (tidak ada scipy/fitting di firmware,
    # lihat komentar di evaluate_calibration_model()), cuma menyimpan &
    # mengembalikannya apa adanya lewat GET_CONFIG. Ini murni jaring
    # pengaman supaya titik kalibrasi tidak hilang total kalau device
    # dipindah ke PC lain yang belum pernah menyimpan cache-nya.
    "calibration_points": {},
    "device_identity": {"pn": "", "sn": "", "firmware_version": ""},
    # Cache kalibrasi PER SERIAL NUMBER (SN) device fisik -- karena satu PC
    # ini bisa dipakai bergantian untuk banyak unit device yang beda
    # karakteristik sensornya. "calibration"/"calibration_points" di atas
    # selalu berisi profil device yang SEDANG aktif (device yang terakhir
    # terhubung dan teridentifikasi); begitu SN device yang connect
    # berbeda dari SN aktif sebelumnya, app otomatis switch: snapshot
    # profil lama disimpan ke sini dulu, baru profil SN baru dimuat ke
    # "calibration"/"calibration_points" di atas -- kalau PC ini belum
    # pernah mengenal SN itu, keduanya ditarik dari device sendiri lewat
    # GET_CONFIG (lihat _handle_identity), termasuk titik mentahnya karena
    # sekarang device juga menyimpannya.
    # Format: {sn: {"pn":..., "firmware_version":..., "calibration":{...},
    #                "calibration_points":{...}}}
    "device_profiles": {},
    "buzzer": {
        "patterns": 10
    },
    "logging": {
        "data_enabled": True,
        "data_interval_sec": 60,
        "data_retention_days": 7,
        "system_enabled": True,
        "system_retention_days": 30,
    },
    # Timer refresh e-paper (SSD1680), disinkron dua arah dengan device
    # lewat SET_DISPLAY_CONFIG / GET_CONFIG. update_interval_sec = jeda
    # antar partial refresh (nilai default sensor/waktu/wifi di layar),
    # full_refresh_interval_min = jeda antar full-refresh (bersihkan
    # ghosting panel).
    "display": {
        "update_interval_sec": 60,
        "full_refresh_interval_min": 30,
    },
    # Kirim data ke gerbang HTTP udaraku (POST). Menggantikan jalur "server"
    # (JWT-signed, iot.kemenperin.go.id) yang lama -- lihat udaraku_sync.py di
    # firmware. "key" = Bearer key alat (BUKAN private key untuk signing --
    # kontraknya beda dari jalur lama). "kode_alat" boleh berbeda dari SN
    # device, diisi manual. "kanal" = daftar payload key yang dikirim (mis.
    # ["t","h"]); dibiarkan kosong berarti SEMUA kanal dikirim (begitu cara
    # firmware menafsirkan "kanal" kosong/falsy -- lihat udaraku_sync.py).
    # "queue_interval_sec"/"queue_enabled" = perilaku backlog CSV, sama
    # semangatnya dengan jalur server lama tapi mekanismenya ada di
    # udaraku_sync (firmware), bukan di sini.
    "udaraku": {
        "enabled": False,
        "url": "",
        "key": "",
        "kode_alat": "",
        "interval_sec": 60,
        "timeout_sec": 15,
        "kanal": [],
        "queue_enabled": True,
        "queue_interval_sec": 5,
        "fail_buzzer_enabled": True,
        "fail_buzzer_pattern": 3,
        "success_buzzer_enabled": True,
        "success_buzzer_pattern": 1,
    },
    # Preferensi tampilan aplikasi (BUKAN pengaturan alat) -- disimpan
    # terpisah supaya jelas ini murni preferensi PC/GUI, tidak pernah
    # dikirim ke firmware. "accent" merujuk ke key di ACCENT_PRESETS.
    "ui": {
        "accent": "blue",
        "theme": "light_blue",
        "font_family": "Segoe UI",
        "font_size": 13,
        "custom_colors": {},
    },
}


def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in cfg})
            if isinstance(data.get("dashboard"), dict):
                cfg["dashboard"].update(data["dashboard"])
            if isinstance(data.get("device"), dict):
                cfg["device"].update(data["device"])
            if isinstance(data.get("buzzer"), dict):
                cfg["buzzer"].update(data["buzzer"])
            if isinstance(data.get("logging"), dict):
                cfg["logging"].update(data["logging"])
            if isinstance(data.get("udaraku"), dict):
                cfg["udaraku"].update(data["udaraku"])
            if isinstance(data.get("ui"), dict):
                cfg["ui"].update(data["ui"])
                if isinstance(data["ui"].get("custom_colors"), dict):
                    cfg["ui"]["custom_colors"] = dict(data["ui"]["custom_colors"])
            if "thresholds" in data:
                cfg["thresholds"] = data["thresholds"]
        return cfg
    except Exception:
        return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(config):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_PATH)


def format_file_size(num_bytes):
    """Format ukuran file dalam B/KB/MB yang mudah dibaca (dipakai di tabel
    SD Card & dialog progress download)."""
    try:
        num_bytes = float(num_bytes)
    except (TypeError, ValueError):
        return "--"
    if num_bytes < 1024:
        return f"{int(num_bytes)} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.2f} MB"
