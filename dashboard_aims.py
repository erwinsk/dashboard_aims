"""Titik masuk aplikasi Dashboard AiMS.

Seluruh logika ada di paket `aims_dashboard/`. File ini sengaja tetap
bernama dashboard_aims.py supaya perintah build (PyInstaller / workflow
GitHub Actions) tidak perlu diubah.
"""
from aims_dashboard.app import main

if __name__ == "__main__":
    main()
