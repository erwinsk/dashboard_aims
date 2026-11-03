"""Koneksi serial: daftar port, connect/disconnect, error."""

import serial
import serial.tools.list_ports

from PyQt5.QtWidgets import QMessageBox

from aims_dashboard.serial_worker import SerialWorker


class ConnectionMixin:
    """Koneksi serial: daftar port, connect/disconnect, error."""

    def refresh_ports(self):
        self.cb_ports.clear()
        for port in serial.tools.list_ports.comports():
            self.cb_ports.addItem(port.device)

    def toggle_connection(self):
        if self.worker is None:
            port = self.cb_ports.currentText()
            if not port:
                QMessageBox.warning(self, "Peringatan", "Pilih Port Serial terlebih dahulu.")
                return

            baud = int(self.config.get("device", {}).get("baudrate", 115200))
            self._identity_requested_this_session = False
            self.worker = SerialWorker(port, baud)
            self.worker.data_received.connect(self.handle_incoming_data)
            self.worker.error_signal.connect(self.handle_serial_error)
            self.worker.start()

            self.btn_connect.setText("Disconnect")
            self._set_button_role(self.btn_connect, "btnDanger")
            self.lbl_conn_status.setText("Connected")
            self.lbl_conn_status.setObjectName("statusBadgeConnected")
            self.lbl_conn_status.style().unpolish(self.lbl_conn_status)
            self.lbl_conn_status.style().polish(self.lbl_conn_status)
            
            self.log_terminal("INFO", f"Mencoba terhubung ke {port} dengan baudrate {baud}", "#2980b9")
        else:
            self.disconnect_serial()

    def disconnect_serial(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        self._identity_requested_this_session = False
        self.btn_connect.setText("Connect")
        self._set_button_role(self.btn_connect, "btnPrimary")
        self.lbl_conn_status.setText("Disconnected")
        self.lbl_conn_status.setObjectName("statusBadgeDisconnected")
        self.lbl_conn_status.style().unpolish(self.lbl_conn_status)
        self.lbl_conn_status.style().polish(self.lbl_conn_status)
        self.log_terminal("INFO", "Port serial diputuskan.", "#7f8c8d")

    def _set_button_role(self, button, object_name):
        button.setObjectName(object_name)
        button.style().unpolish(button)
        button.style().polish(button)

    def handle_serial_error(self, err_msg):
        self.log_terminal("ERR", f"SERIAL ERROR: {err_msg}", "#c0392b")
        self.disconnect_serial()
