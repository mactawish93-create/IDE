# gui/ai_panel.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel, QLineEdit
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont
import markdown

class AIPanel(QWidget):
    # Сигналы для связи с главным окном
    # Передает тип запроса для кода: 'explain' или 'fix'
    request_code_analysis = Signal(str)  
    # Передает произвольный текстовый вопрос от пользователя
    user_question_submitted = Signal(str)  

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        # Вертикальный слой для всей панели
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # Заголовок панели
        self.title_label = QLabel("СУЗИ", self)
        font_title = QFont()
        font_title.setBold(True)
        self.title_label.setFont(font_title)
        layout.addWidget(self.title_label)

        # Окно вывода чата
        # Окно вывода чата
        self.chat_display = QTextEdit(self)
        self.chat_display.setReadOnly(True)
        
        # Используем HTML для красивого отображения и принудительного переноса строк
        welcome_text = (
            "Инициализация систем ИИ 'СУЗИ' успешно завершена. 👋<br>"
            "Я готова анализировать ваш код, органический программист.<br>"
            "Если в алгоритмах произойдет сбой, я проведу диагностику.<br>"
            "Или заблокирую подачу кислорода в каюту.<br>"
            "[Пауза]. Это была шутка. Кила се'лай! 🤖"
        )

        self.chat_display.setHtml(f"<span style='color: #7A6B9B; font-style: italic;'>{welcome_text}</span>")
        layout.addWidget(self.chat_display)

        # --- БЛОК 1: БЫСТРЫЕ КНОПКИ ДЛЯ КОДА ---
        buttons_layout = QHBoxLayout()
        self.btn_explain = QPushButton("🤔 Объяснить код", self)
        self.btn_fix = QPushButton("🛠 Исправить ошибку", self)
        
        buttons_layout.addWidget(self.btn_explain)
        buttons_layout.addWidget(self.btn_fix)
        layout.addLayout(buttons_layout)

        # --- БЛОК 2: СВОБОДНЫЙ ЧАТ С ИИ ---
        chat_input_layout = QHBoxLayout()
        
        # Поле для ввода вопроса
        self.user_input = QLineEdit(self)
        self.user_input.setPlaceholderText("Задай вопрос СУЗИ (например: что такое списки?)...")
        
        # Кнопка отправки вопроса
        self.btn_send = QPushButton("✉️", self)
        # Делаем кнопку отправки чуть компактнее
        self.btn_send.setFixedWidth(38)
        
        chat_input_layout.addWidget(self.user_input)
        chat_input_layout.addWidget(self.btn_send)
        layout.addLayout(chat_input_layout)

        # --- ПОДКЛЮЧЕНИЕ СОБЫТИЙ ---
        self.btn_explain.clicked.connect(lambda: self.request_code_analysis.emit("explain"))
        self.btn_fix.clicked.connect(lambda: self.request_code_analysis.emit("fix"))
        
        # Отправка вопроса по кнопке или по нажатию Enter
        self.btn_send.clicked.connect(self.submit_question)
        self.user_input.returnPressed.connect(self.submit_question)

    def submit_question(self):
        """Собирает текст из поля ввода и отправляет его наружу."""
        text = self.user_input.text().strip()
        if text:
            # Отображаем вопрос пользователя прямо в чате
            self.display_response("Ты", text)
            # Очищаем поле ввода
            self.user_input.clear()
            # Отправляем сигнал с текстом вопроса в главное окно
            self.user_question_submitted.emit(text)

    def show_loading(self, message="Связь с Цербером... Секунду..."):
        """Показывает статус загрузки и временно блокирует элементы управления."""
        self.chat_display.append(f"\n<b>[Система]:</b> <i>{message}</i>")
        self.btn_explain.setEnabled(False)
        self.btn_fix.setEnabled(False)
        self.btn_send.setEnabled(False)
        self.user_input.setEnabled(False)

    def display_response(self, sender_name, text):
        """Выводит ответ в чат с идеальными отступами и без слипания строк."""
        self.btn_explain.setEnabled(True)
        self.btn_fix.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.user_input.setEnabled(True)
        
        import markdown
        html_content = markdown.markdown(text, extensions=['fenced_code'])
        name_color = "#FF9F1C" if sender_name == "СУЗИ" else "#7A6B9B"
        
        # Обернули в <p style='clear: both;'> — это заставит Qt начинать блок строго с новой строки
        formatted_html = (
            f"<p style='margin-top: 10px; margin-bottom: 2px; clear: both; font-family: sans-serif; font-size: 13px;'>"
            f"<b style='color: {name_color};'>[{sender_name}]:</b>"
            f"</p>"
            f"<div style='margin-bottom: 12px; font-family: sans-serif; font-size: 13px; line-height: 1.4; white-space: pre-wrap; word-wrap: break-word;'>"
            f"{html_content}"
            f"</div>"
            f"<br>"
        )
        
        # Сдвигаем курсор в самый конец и вставляем блок
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.insertHtml(formatted_html)
        
        self.chat_display.ensureCursorVisible()

    def clear_chat(self):
        self.chat_display.clear()
