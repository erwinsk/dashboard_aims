"""Thread pembaca/penulis port serial (UART ke ESP32)."""

import time

import serial

from PyQt5.QtCore import pyqtSignal, QThread


class SerialWorker(QThread):
    data_received = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, port, baudrate=115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.running = True

    def run(self):
        buffer = ""
        try:
            # PENTING: DTR/RTS di-set ke False SEBELUM open(), bukan sesudah.
            # pyserial menerapkan level DTR/RTS PADA SAAT open() dipanggil --
            # serial.Serial(port, baud, ...) (constructor lama) otomatis
            # meng-open() dengan DTR/RTS default (biasanya HIGH/asserted),
            # dan setDTR(False)/setRTS(False) yang dipanggil SETELAHNYA cuma
            # menutup pintu setelah kuda lepas: pulsa reset ke rangkaian
            # auto-reset board (DTR->EN, RTS->GPIO0) sudah keburu terjadi
            # dengan level HIGH itu. Kalau pulsa EN itu kebetulan berbarengan
            # GPIO0 masih ter-sample LOW, ESP32 masuk ROM bootloader (download
            # mode) alih-alih boot MicroPython -- device jadi diam total
            # (tidak pernah kirim "INFO"/TELEMETRY apa pun), persis gejala
            # "stuck di menghubungkan ke serial" yang cuma bisa diperbaiki
            # dengan reset FISIK (bukan software) karena bootloader ROM tidak
            # merespons command JSON apa pun. Ini race condition (bukan bug
            # deterministik) -- makin rawan kalau baru saja disconnect dari
            # sesi Thonny sebelumnya.
            #
            # Fix: buat objek Serial KOSONG dulu, set port/baudrate/DTR/RTS,
            # baru panggil open() -- supaya level DTR/RTS yang diterapkan
            # SAAT port benar-benar dibuka sudah False sejak awal, tidak ada
            # window HIGH sama sekali.
            self.ser = serial.Serial()
            self.ser.port = self.port
            self.ser.baudrate = self.baudrate
            self.ser.timeout = 0.1
            self.ser.dtr = False
            self.ser.rts = False
            self.ser.open()
            time.sleep(0.5)
            self.ser.reset_input_buffer()
            while self.running:
                if self.ser.in_waiting:
                    buffer += self.ser.read(self.ser.in_waiting).decode("utf-8", errors="ignore")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if line:
                            self.data_received.emit(line)
                time.sleep(0.01)
        except Exception as exc:
            self.error_signal.emit(str(exc))
        finally:
            try:
                if self.ser and self.ser.is_open:
                    self.ser.close()
            except Exception:
                pass

    def write_data(self, data):
        if self.ser and self.ser.is_open:
            try:
                self.ser.write((data + "\n").encode("utf-8"))
                return True
            except Exception as exc:
                self.error_signal.emit(f"Gagal kirim data serial: {exc}")
        return False

    def stop(self):
        self.running = False
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass
        self.wait()
