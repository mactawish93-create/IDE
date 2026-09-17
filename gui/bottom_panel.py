# gui/bottom_panel.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QTextEdit
from PySide6.QtGui import QFont, QColor

class BottomPanel(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        # Настраиваем вкладки снизу (сделаем их аккуратными)
        self.setTabPosition(QTabWidget.TabPosition.North)
        
        # --- ВКЛАДКА 1: КОНСОЛЬ ВЫВОДА ---
        self.console_output = QTextEdit(self)
        self.console_output.setReadOnly(True)  # Только для чтения, чтобы юзер случайно не стер вывод
        
        # Устанавливаем моноширинный шрифт для вывода, как в реальном терминале
        console_font = QFont("Consolas", 11)
        self.console_output.setFont(console_font)
        self.console_output.setPlaceholderText("🚀 Результат выполнения программы появится здесь после нажатия 'ЗАПУСТИТЬ КОД'...")
        
        # --- ВКЛАДКА 2: ЛОГ ОШИБОК ---
        self.error_log = QTextEdit(self)
        self.error_log.setReadOnly(True)
        self.error_log.setFont(console_font)
        self.error_log.setPlaceholderText("✅ Ошибок не обнаружено. Твой код чист, как обшивка Нормандии!")

        # Добавляем вкладки в панель
        self.addTab(self.console_output, "🖥 Консоль вывода")
        self.addTab(self.error_log, "⚠️ Лог ошибок")

    def append_output(self, text: str):
        """Добавляет обычный текст в консоль вывода."""
        self.console_output.moveCursor(self.console_output.textCursor().MoveOperation.End)
        self.console_output.insertPlainText(text)
        self.console_output.ensureCursorVisible()
        # При выводе текста автоматически переключаем на вкладку консоли
        self.setCurrentIndex(0)

    def append_error(self, text: str):
        """Добавляет текст ошибки в лог ошибок."""
        self.error_log.moveCursor(self.error_log.textCursor().MoveOperation.End)
        # Подсветим ошибку темно-красным цветом для наглядности (через HTML)
        formatted_error = f"<span style='color:#FF5555;'>{text}</span>"
        self.error_log.insertHtml(formatted_error)
        self.error_log.ensureCursorVisible()
        # При появлении ошибки автоматически переключаем фокус на вкладку ошибок, чтобы привлечь внимание
        self.setCurrentIndex(1)

    def clear_all(self):
        """Полная очистка обеих панелей перед новым запуском кода."""
        self.console_output.clear()
        self.error_log.clear()
