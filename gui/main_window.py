# gui/main_window.py — ЧАСТЬ 1
import os
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QSplitter, QFileDialog, QInputDialog, QMessageBox
from PySide6.QtCore import Qt, QPoint, QThread, Signal

from gui.top_bar import TopBar
from gui.file_tree import FileTree
from gui.code_editor import CodeEditor
from gui.ai_panel import AIPanel
from gui.bottom_panel import BottomPanel
from core.syntax import PythonHighlighter
from core.runner import CodeRunner
from ai.assistant import ChiktikkaAssistant

class AIWorker(QThread):
    """Фоновый поток для того, чтобы запросы к ИИ не вешали интерфейс окна."""
    response_ready = Signal(str, str)  # Передает (Имя отправителя, Текст ответа)

    def __init__(self, assistant, prompt_type, code, context):
        super().__init__()
        self.assistant = assistant
        self.prompt_type = prompt_type
        self.code = code
        self.context = context

    def run(self):
        try:
            # Запускаем сетевой запрос к Hugging Face
            reply = self.assistant.generate_response(self.prompt_type, self.code, self.context)
            if not reply:
                reply = "СУЗИ не смогла сформировать ответ. Базы данных Цербера временно недоступны."
            self.response_ready.emit("СУЗИ", reply)
        except Exception as e:
            # Если что-то пошло не так, поток вернет описание ошибки вместо бесконечного зависания
            self.response_ready.emit("Система", f"Критический сбой потока ИИ: {str(e)}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EDI - Cerberus Edition")
        self.resize(1100, 750)
        
        # Переводим окно в безрамочный режим (VS Code Style)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        
        # Переменные для перетаскивания безрамочного окна мышью
        self.drag_position = QPoint()
        self.is_dragging = False

        self.current_project_dir = os.getcwd()
        self.current_file_path = None
        
        # Инициализируем мозги ИИ
        self.assistant = ChiktikkaAssistant()
        
        self.init_ui()
        self.apply_theme("hacker")

    def init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Создаем наш кастомный Top Bar
        self.top_bar = TopBar(self)
        main_layout.addWidget(self.top_bar)

        # --- СВЯЗЫВАЕМ ПЕРЕТАСКИВАНИЕ ОКНА ЗА TOP BAR ---
        self.top_bar.mousePressEvent = self.on_top_bar_pressed
        self.top_bar.mouseMoveEvent = self.on_top_bar_moved
        self.top_bar.mouseReleaseEvent = self.on_top_bar_released

        # Сетка разделителей
        vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        horizontal_splitter = QSplitter(Qt.Orientation.Horizontal)

        self.file_tree = FileTree(self)
        self.code_editor = CodeEditor(self)
        self.highlighter = PythonHighlighter(self.code_editor.document())
        self.ai_panel = AIPanel(self)

        horizontal_splitter.addWidget(self.file_tree)
        horizontal_splitter.addWidget(self.code_editor)
        horizontal_splitter.addWidget(self.ai_panel)
        horizontal_splitter.setSizes([120, 780, 200])

        self.bottom_panel = BottomPanel(self)
        vertical_splitter.addWidget(horizontal_splitter)
        vertical_splitter.addWidget(self.bottom_panel)
        vertical_splitter.setSizes([650, 100])

        main_layout.addWidget(vertical_splitter)

        self.runner = CodeRunner(self)

        # --- ПОДКЛЮЧЕНИЕ СИГНАЛОВ И КНОПОК ---
        self.top_bar.theme_changed.connect(self.apply_theme)
        self.top_bar.run_clicked.connect(self.start_code_execution)
        self.top_bar.stop_clicked.connect(self.runner.stop_process)
        
        # Сигналы кнопок управления окном
        self.top_bar.minimize_requested.connect(self.showMinimized)
        self.top_bar.maximize_requested.connect(self.toggle_maximize)
        self.top_bar.close_requested.connect(self.close)
        
        # Сигнал поиска по коду
        self.top_bar.search_requested.connect(self.search_in_code)

        # Сигналы ИИ-панели Чиктики
        self.ai_panel.request_code_analysis.connect(self.handle_ai_analysis_request)
        self.ai_panel.user_question_submitted.connect(self.handle_ai_chat_question)

        # Файловые кнопки
        self.top_bar.new_project_clicked.connect(self.create_new_file_topbar)
        self.top_bar.open_file_clicked.connect(self.open_project_folder)
        self.top_bar.save_file_clicked.connect(self.save_current_file)
        
        self.file_tree.file_double_clicked.connect(self.open_file_in_editor)
        self.runner.output_ready.connect(self.bottom_panel.append_output)
        self.runner.error_ready.connect(self.bottom_panel.append_error)
        self.runner.finished.connect(self.on_code_execution_finished)

    def on_top_bar_pressed(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.is_dragging = True
            event.accept()

    def on_top_bar_moved(self, event):
        if self.is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def on_top_bar_released(self, event):
        self.is_dragging = False

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
# gui/main_window.py — ЧАСТЬ 2

    # --- ЛОГИКА ПОИСКА ПО КОДУ ---
    
    def search_in_code(self, search_text: str):
        if not search_text:
            return
        found = self.code_editor.find(search_text)
        if not found:
            self.code_editor.moveCursor(self.code_editor.textCursor().MoveOperation.Start)
            found = self.code_editor.find(search_text)
            
        if found:
            self.code_editor.setFocus()
        else:
            self.bottom_panel.append_output(f"\n🔍 [Поиск]: Строка '{search_text}' не найдена.")

    # --- ЛОГИКА РАБОТЫ С ИИ ЧИКТИКИ ---

    def handle_ai_analysis_request(self, request_type: str):
        """Вызывается по кнопкам 'Объяснить код' или 'Исправить ошибку'."""
        code = self.code_editor.toPlainText()
        error_context = ""
        
        if request_type == "fix":
            error_context = self.bottom_panel.error_log.toPlainText()
            if not error_context.strip() or "Ошибок не обнаружено" in error_context:
                self.ai_panel.display_response("СУЗИ", "Диагностика чиста, Джеф! Лог ошибок пуст. Кила се'лай!")
                return
        
        self.ai_panel.show_loading("СУЗИ сканирует систему через Омни-инструмент...")
        
        # Запускаем фоновый поток, который мы добавили в начало файла!
        self.ai_thread = AIWorker(self.assistant, request_type, code, error_context)
        self.ai_thread.response_ready.connect(self.ai_panel.display_response)
        self.ai_thread.start()

    def handle_ai_chat_question(self, question_text: str):
        """Вызывается, когда пользователь вбивает текстовый вопрос в чат вручную."""
        code = self.code_editor.toPlainText()
        self.ai_panel.show_loading("СУЗИ сверяется с базами данных Цербера...")
        
        self.ai_thread = AIWorker(self.assistant, "chat", code, question_text)
        self.ai_thread.response_ready.connect(self.ai_panel.display_response)
        self.ai_thread.start()

    # --- ОСТАЛЬНАЯ ЛОГИКА СИСТЕМЫ ---

    def apply_theme(self, theme_name: str):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        qss_path = os.path.join(current_dir, "styles", f"{theme_name}.qss")
        if os.path.exists(qss_path):
            try:
                with open(qss_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
                self.highlighter.apply_theme(theme_name)
            except Exception as e:
                print(f"Ошибка загрузки темы: {e}")

    def open_project_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выбрать папку проекта", self.current_project_dir)
        if folder:
            self.current_project_dir = folder
            self.file_tree.set_root_folder(folder)
            os.chdir(folder)
            self.ai_panel.display_response("Система", f"Проект переключен на папку: <code>{os.path.basename(folder)}</code>")

    def create_new_file_topbar(self):
        filename, ok = QInputDialog.getText(self, "Новый файл", "Введите имя файла (без .py):")
        if ok and filename.strip():
            if not filename.endswith(".py"):
                filename += ".py"
            full_path = os.path.join(self.current_project_dir, filename)
            try:
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write("# Код вашего нового модуля\n")
                self.open_file_in_editor(full_path)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось создать файл: {str(e)}")

    def open_file_in_editor(self, file_path: str):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                self.code_editor.setPlainText(f.read())
            self.current_file_path = file_path
            self.ai_panel.display_response("СУЗИ", f"Файл <code>{os.path.basename(file_path)}</code> загружен.")
        except Exception as e:
            self.bottom_panel.append_error(f"Не удалось открыть файл: {str(e)}\n")

    def save_current_file(self):
        if self.current_file_path:
            try:
                with open(self.current_file_path, "w", encoding="utf-8") as f:
                    f.write(self.code_editor.toPlainText())
                self.ai_panel.display_response("Система", "Изменения успешно сохранены.")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл: {str(e)}")
        else:
            file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить файл", self.current_project_dir, "Python Files (*.py)")
            if file_path:
                self.current_file_path = file_path
                self.save_current_file()

    def start_code_execution(self):
        if self.current_file_path:
            with open(self.current_file_path, "w", encoding="utf-8") as f:
                f.write(self.code_editor.toPlainText())
        
        code_text = self.code_editor.toPlainText()
        self.bottom_panel.clear_all()
        self.ai_panel.display_response("Система", "Запуск диагностики систем...")
        
        self.top_bar.btn_run.setEnabled(False)
        self.top_bar.btn_stop.setEnabled(True)
        
        os.chdir(self.current_project_dir)
        self.runner.run_code(code_text)

    def on_code_execution_finished(self, exit_code: int):
        self.top_bar.btn_run.setEnabled(True)
        self.top_bar.btn_stop.setEnabled(False)
        
        if exit_code == 0:
            self.ai_panel.display_response("СУЗИ", "Программа отработала успешно! Кила се'лай!")
        else:
            if "Выполнение программы принудительно остановлено" in self.bottom_panel.console_output.toPlainText():
                self.ai_panel.display_response("СУЗИ", "Процесс успешно прерван по твоей команде.")
            else:
                self.ai_panel.display_response(
                    "СУЗИ", 
                    "Обнаружена ошибка! В коде завёлся боштед. Нажми кнопку <b>'Исправить ошибку'</b> для глубокого сканирования!"
                )
