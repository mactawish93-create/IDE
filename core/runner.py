# core/runner.py
import os
import sys
import tempfile
from PySide6.QtCore import QObject, QProcess, Signal

class CodeRunner(QObject):
    # Сигналы для передачи данных в нижнюю панель интерфейса
    output_ready = Signal(str)  # Передает обычный вывод (print)
    error_ready = Signal(str)   # Передает системную ошибку (Traceback)
    finished = Signal(int)      # Передает код завершения программы (0 - успех, другое - ошибка)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.temp_file_path = None

    def run_code(self, code_text: str):
        """Создает временный файл с кодом и запускает его через QProcess."""
        # Если какой-то код уже выполняется, не запускаем новый процесс
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            return

        # 1. Сохраняем код во временный файл прямо в текущей рабочей папке проекта
        try:
            # Префикс точки делает файл скрытым на Unix системах, а suffix .py нужен для интерпретатора
            # dir=os.getcwd() — заставляет создать файл в текущей папке проекта!
            with tempfile.NamedTemporaryFile(suffix=".py", dir=os.getcwd(), delete=False, mode="w", encoding="utf-8") as temp_file:
                temp_file.write(code_text)
                self.temp_file_path = temp_file.name
        except Exception as e:
            self.error_ready.emit(f"Критическая ошибка создания файла в папке проекта: {str(e)}\n")
            return

        # 2. Настраиваем процесс QProcess
        self.process = QProcess(self)
        
        # Перенаправляем потоки вывода так, чтобы Qt мог их читать по отдельности
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)

        # Подключаем встроенные события процесса к нашим сигналам
        self.process.readyReadStandardOutput.connect(self.on_stdout_ready)
        self.process.readyReadStandardError.connect(self.on_stderr_ready)
        self.process.finished.connect(self.on_process_finished)

        # 3. Стартуем! Используем тот же интерпретатор Python, в котором запущен редактор
        python_executable = sys.executable
        self.process.start(python_executable, [self.temp_file_path])

    def on_stdout_ready(self):
        """Вызывается, когда запущенный скрипт что-то напечатал через print()."""
        data = self.process.readAllStandardOutput().data()
        # Декодируем из utf-8 (в Windows может быть cp1251, fallback защитит от падения)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode(sys.getdefaultencoding(), errors="replace")
        self.output_ready.emit(text)

    def on_stderr_ready(self):
        """Вызывается, когда запущенный скрипт выдал системную ошибку (Traceback)."""
        data = self.process.readAllStandardError().data()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode(sys.getdefaultencoding(), errors="replace")
        self.error_ready.emit(text)

    def on_process_finished(self, exit_code):
        """Вызывается, когда программа завершила работу."""
        self.finished.emit(exit_code)
        
        # Удаляем временный файл за собой, чтобы не засорять систему
        if self.temp_file_path and os.path.exists(self.temp_file_path):
            try:
                os.remove(self.temp_file_path)
            except OSError:
                pass
            self.temp_file_path = None

    def stop_process(self):
        """Принудительно останавливает код (нужно, если пользователь написал вечный цикл)."""
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            self.process.kill()
            self.output_ready.emit("\n🛑 Выполнение программы принудительно остановлено.\n")
