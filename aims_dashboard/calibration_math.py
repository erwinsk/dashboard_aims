"""Model & fitting kalibrasi (numpy/scipy) -- tanpa GUI."""

import math
import warnings

import numpy as np
from scipy.optimize import OptimizeWarning
from scipy.optimize import curve_fit


# ---------------------------------------------------------------------------
# Model kalibrasi non-linear -- fitting multi-titik + pemilihan R^2 terbaik.
#
# evaluate_calibration_model() SENGAJA diduplikasi dari payload_manager.py
# (bukan di-import) karena dashboard ini berjalan di PC dan firmware
# (payload_manager.py) berjalan terpisah di device -- keduanya tidak selalu
# berbagi filesystem yang sama. Kalau modul ini diubah, payload_manager.py
# harus disinkronkan manual (dan sebaliknya) supaya nilai preview di GUI
# sama persis dengan yang benar-benar dihitung firmware.
#
# Fitting di bawah pakai numpy/scipy (dependency tambahan -- butuh
# `pip install numpy scipy`):
#   - linear/poly2/poly3 -> numpy.polyfit (least-squares via SVD, jauh
#     lebih stabil numerik utk data yang nyaris collinear / ill-conditioned
#     dibanding normal-equations manual).
#   - exponential/logarithmic/power -> scipy.optimize.curve_fit, yaitu
#     nonlinear least-squares (Levenberg-Marquardt) di ruang y ASLI.
#     Ini SENGAJA bukan pendekatan "linearisasi" (regresi pada ln(x)/ln(y))
#     -- linearisasi meminimalkan error di ruang log, bukan di satuan
#     sensor yang sebenarnya, jadi hasilnya bias, khususnya kalau titik
#     kalibrasi tersebar tidak merata. curve_fit tetap dikasih initial
#     guess dari linearisasi (via _linearized_guess_*) supaya konvergen
#     lebih stabil & cepat, tapi hasil akhirnya di-refine di ruang asli.
#
# Firmware (payload_manager.py) TIDAK ikut pakai numpy/scipy -- device
# hanya perlu evaluate_calibration_model() (murni math dasar), bukan
# fitting, dan target embedded pada umumnya tidak punya scipy sama sekali.
# ---------------------------------------------------------------------------

CALIBRATION_MODEL_PARAM_COUNTS = {
    "linear": 2,        # [a, b]       -> y = a*x + b
    "poly2": 3,         # [a, b, c]    -> y = a*x^2 + b*x + c
    "poly3": 4,         # [a, b, c, d] -> y = a*x^3 + b*x^2 + c*x + d
    "exponential": 2,   # [a, b]       -> y = a * e^(b*x)
    "logarithmic": 2,   # [a, b]       -> y = a*ln(x) + b   (butuh x > 0)
    "power": 2,         # [a, b]       -> y = a * x^b       (butuh x > 0)
}


CALIBRATION_MODEL_LABELS = {
    "linear": "Linear (y = ax + b)",
    "poly2": "Polinomial derajat 2 (y = ax\u00b2 + bx + c)",
    "poly3": "Polinomial derajat 3 (y = ax\u00b3 + bx\u00b2 + cx + d)",
    "exponential": "Eksponensial (y = a\u00b7e^(bx))",
    "logarithmic": "Logaritmik (y = a\u00b7ln(x) + b)",
    "power": "Pangkat (y = a\u00b7x^b)",
}


def evaluate_calibration_model(model, params, value):
    """Hitung nilai terkalibrasi untuk satu model+params pada satu nilai
    mentah. Mengembalikan None kalau model/params tidak valid atau di luar
    domain (mis. logarithmic/power untuk value <= 0). Harus tetap identik
    secara perilaku dengan payload_manager.evaluate_calibration_model() --
    fungsi ini SENGAJA masih pure math (bukan numpy) walau modul ini sudah
    boleh pakai numpy/scipy, supaya evaluasi satu-nilai tetap murah dan
    tidak menyeret overhead array numpy untuk kasus sesederhana ini."""
    try:
        if model == "linear":
            a, b = params
            return a * value + b
        if model == "poly2":
            a, b, c = params
            return a * value * value + b * value + c
        if model == "poly3":
            a, b, c, d = params
            return a * value ** 3 + b * value ** 2 + c * value + d
        if model == "exponential":
            a, b = params
            return a * math.exp(b * value)
        if model == "logarithmic":
            a, b = params
            if value <= 0:
                return None
            return a * math.log(value) + b
        if model == "power":
            a, b = params
            if value <= 0:
                return None
            return a * (value ** b)
    except (TypeError, ValueError, OverflowError, ZeroDivisionError):
        return None
    return None


def _safe_polyfit(xs, ys, degree):
    """np.polyfit dibungkus try/except + RankWarning di-silent-kan --
    kembalikan None (bukan raise) kalau sistemnya singular/ill-conditioned
    (mis. titik x kurang bervariasi untuk derajat yang diminta). Warning
    disupres generik (bukan import np.RankWarning langsung) karena lokasi
    kelas itu pindah antar versi numpy (np.RankWarning di numpy<2,
    np.exceptions.RankWarning di numpy>=2)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            coeffs = np.polyfit(xs, ys, degree)
        if np.any(np.isnan(coeffs)) or np.any(np.isinf(coeffs)):
            return None
        return coeffs
    except (np.linalg.LinAlgError, ValueError):
        return None


def _linearized_guess_exponential(xs, ys):
    """Initial guess untuk curve_fit(exponential) lewat linearisasi
    ln(y) = ln(a) + b*x. Cuma dipakai sebagai titik awal iterasi
    Levenberg-Marquardt, BUKAN hasil akhir -- hasil akhir tetap di-fit di
    ruang y asli lewat curve_fit."""
    fit = _safe_polyfit(xs, np.log(ys), 1)
    if fit is None:
        return [1.0, 0.01]
    slope, intercept = fit
    return [math.exp(intercept), slope]


def _linearized_guess_logarithmic(xs, ys):
    fit = _safe_polyfit(np.log(xs), ys, 1)
    if fit is None:
        return [1.0, 0.0]
    a, b = fit
    return [a, b]


def _linearized_guess_power(xs, ys):
    fit = _safe_polyfit(np.log(xs), np.log(ys), 1)
    if fit is None:
        return [1.0, 1.0]
    slope, intercept = fit
    return [math.exp(intercept), slope]


def _r_squared(ys_actual, ys_pred):
    ys_actual = np.asarray(ys_actual, dtype=float)
    ys_pred = np.asarray(ys_pred, dtype=float)
    ss_tot = float(np.sum((ys_actual - ys_actual.mean()) ** 2))
    ss_res = float(np.sum((ys_actual - ys_pred) ** 2))
    if ss_tot < 1e-12:
        return 1.0 if ss_res < 1e-12 else 0.0
    return 1.0 - ss_res / ss_tot


def fit_calibration_candidates(points):
    """Coba fit beberapa model kalibrasi (linear/poly2/poly3/exponential/
    logarithmic/power) dari titik-titik (raw, ref) yang diberikan, hitung
    R^2 masing-masing di ruang y ASLI, lalu kembalikan list dict
    {"model","params","r2"} terurut dari R^2 terbaik ke terburuk. Model
    yang butuh titik lebih banyak dari yang tersedia, domainnya tidak valid
    (mis. logarithmic/power butuh semua raw > 0), atau gagal konvergen,
    otomatis dilewati -- bukan error, cuma tidak masuk hasil."""
    points = [(float(x), float(y)) for x, y in points]
    xs = np.array([p[0] for p in points], dtype=float)
    ys = np.array([p[1] for p in points], dtype=float)
    n = len(points)
    n_distinct_x = len(set(xs.tolist()))
    results = []

    def try_add(model, params):
        if params is None:
            return
        preds = [evaluate_calibration_model(model, params, x) for x in xs]
        if any(p is None for p in preds):
            return
        r2 = _r_squared(ys, preds)
        results.append({"model": model, "params": [float(p) for p in params], "r2": r2})

    # Linear / poly2 / poly3 -- least-squares polinomial via numpy.polyfit.
    if n >= 2 and n_distinct_x >= 2:
        try_add("linear", _safe_polyfit(xs, ys, 1))
    if n >= 3 and n_distinct_x >= 3:
        try_add("poly2", _safe_polyfit(xs, ys, 2))
    if n >= 4 and n_distinct_x >= 4:
        try_add("poly3", _safe_polyfit(xs, ys, 3))

    # Exponential y = a*e^(bx) -- nonlinear fit, butuh semua ref (y) > 0
    # supaya initial guess dari linearisasi ln(y) valid.
    if n >= 2 and n_distinct_x >= 2 and np.all(ys > 0):
        p0 = _linearized_guess_exponential(xs, ys)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", OptimizeWarning)
                popt, _ = curve_fit(
                    lambda x, a, b: a * np.exp(b * x), xs, ys, p0=p0, maxfev=10000
                )
            try_add("exponential", popt)
        except (RuntimeError, ValueError):
            pass

    # Logarithmic y = a*ln(x) + b -- butuh semua raw (x) > 0.
    if n >= 2 and n_distinct_x >= 2 and np.all(xs > 0):
        p0 = _linearized_guess_logarithmic(xs, ys)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", OptimizeWarning)
                popt, _ = curve_fit(
                    lambda x, a, b: a * np.log(x) + b, xs, ys, p0=p0, maxfev=10000
                )
            try_add("logarithmic", popt)
        except (RuntimeError, ValueError):
            pass

    # Power y = a*x^b -- butuh semua raw (x) > 0 DAN semua ref (y) > 0.
    if n >= 2 and n_distinct_x >= 2 and np.all(xs > 0) and np.all(ys > 0):
        p0 = _linearized_guess_power(xs, ys)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", OptimizeWarning)
                popt, _ = curve_fit(
                    lambda x, a, b: a * np.power(x, b), xs, ys, p0=p0, maxfev=10000
                )
            try_add("power", popt)
        except (RuntimeError, ValueError):
            pass

    results.sort(key=lambda r: r["r2"], reverse=True)
    return results


def _format_calibration_number(value):
    """Format angka param/preview biar rapi di UI -- integer tanpa desimal
    berlebih, float dibulatkan wajar tanpa notasi ilmiah untuk rentang
    kalibrasi sensor yang umum."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.6g}"
