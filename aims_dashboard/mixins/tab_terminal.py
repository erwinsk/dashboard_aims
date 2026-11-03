"""Tab Terminal."""

from PyQt5.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QTextEdit


class TerminalTabMixin:
    """Tab Terminal."""

    def setup_tab_terminal(self):
        layout = self._new_tab_layout(self.tab_terminal)

        self.txt_log = QTextEdit()
        self.txt_log.setObjectName("terminal")
        self.txt_log.setReadOnly(True)
        # Setup Maximum blocks (lines)
        self.txt_log.document().setMaximumBlockCount(150)
        
        layout.addWidget(self.txt_log)

        h = QHBoxLayout()
        self.txt_cmd = QLineEdit()
        self.txt_cmd.setPlaceholderText("Ketik perintah custom...")
        self.txt_cmd.returnPressed.connect(self.send_custom_command)
        
        btn = QPushButton("Kirim")
        btn.setObjectName("btnPrimary")
        btn.clicked.connect(self.send_custom_command)

        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self.txt_log.clear)

        h.addWidget(self.txt_cmd)
        h.addWidget(btn)
        h.addWidget(btn_clear)
        layout.addLayout(h)
