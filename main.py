# main.py
import sys
import os
from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow

def main():
    # Исправление для Windows: заставляем ОС группировать окна приложения правильно
    # и корректно применять кастомные стили к панели задач
    if sys.platform == "win32":
        import ctypes
        myappid = "rookiecorp.rookieide.omnitool.1.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    # Создаем экземпляр приложения Qt
    app = QApplication(sys.argv)
    
    # Меняем рабочую директорию на папку со скриптом, 
    # чтобы относительные пути к файлам стилей QSS всегда работали железно
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Запускаем наше собранное Главное Окно
    window = MainWindow()
    window.show()
    
    # Запуск бесконечного цикла обработки событий приложения
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
