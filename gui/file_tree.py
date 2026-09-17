# Стало (перенесли QFileSystemModel в QtWidgets):
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeView, QLabel, QMenu, QMessageBox, QInputDialog, QFileSystemModel
from PySide6.QtGui import QCursor
from PySide6.QtCore import QDir, Signal, Qt


class FileTree(QWidget):
    # Сигнал, сообщающий главному окну, что нужно открыть файл
    file_double_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self.title_label = QLabel("📂 Файлы проекта", self)
        layout.addWidget(self.title_label)

        self.model = QFileSystemModel()
        self.model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)
        self.model.setRootPath(QDir.currentPath())

        self.tree = QTreeView(self)
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(QDir.currentPath()))

        self.tree.setColumnHidden(1, True)
        self.tree.setColumnHidden(2, True)
        self.tree.setColumnHidden(3, True)
        self.tree.header().hide()

        layout.addWidget(self.tree)

        # Включаем поддержку контекстного меню по правому клику
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        
        # Двойной клик для открытия файла
        self.tree.doubleClicked.connect(self.on_file_double_clicked)

    def on_file_double_clicked(self, index):
        if not self.model.isDir(index):
            file_path = self.model.filePath(index)
            self.file_double_clicked.emit(file_path)

    def set_root_folder(self, folder_path):
        self.model.setRootPath(folder_path)
        self.tree.setRootIndex(self.model.index(folder_path))

    def show_context_menu(self, position):
        """Создает и показывает меню по правому клику мыши."""
        index = self.tree.indexAt(position)
        
        # Определяем путь к папке, в которой будем создавать файлы
        if index.isValid():
            target_path = self.model.filePath(index)
            if not self.model.isDir(index):
                target_path = os.path.dirname(target_path)
        else:
            target_path = self.model.rootPath()

        menu = QMenu(self)
        
        action_new_file = menu.addAction("📄 Создать файл (.py)")
        action_new_dir = menu.addAction("📁 Создать папку")
        
        # Если кликнули по конкретному файлу/папке, добавляем опцию удаления
        action_delete = None
        if index.isValid():
            menu.addSeparator()
            action_delete = menu.addAction("🗑 Удалить")

        # Показываем меню там, где находится курсор
        selected_action = menu.exec(QCursor.pos())

        # Обработка выбора пользователя
        if selected_action == action_new_file:
            self.create_new_file(target_path)
        elif selected_action == action_new_dir:
            self.create_new_directory(target_path)
        elif action_delete and selected_action == action_delete:
            self.delete_item(index)

    def create_new_file(self, folder_path):
        """Создает новый файл Python."""
        filename, ok = QInputDialog.getText(self, "Новый файл", "Введите имя файла (без .py):")
        if ok and filename.strip():
            if not filename.endswith(".py"):
                filename += ".py"
            
            full_path = os.path.join(folder_path, filename)
            try:
                if not os.path.exists(full_path):
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write("# Новый скрипт Python\n")
                else:
                    QMessageBox.warning(self, "Ошибка", "Файл с таким именем уже существует!")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось создать файл: {str(e)}")

    def create_new_directory(self, folder_path):
        """Создает новую папку."""
        dirname, ok = QInputDialog.getText(self, "Новая папка", "Введите имя папки:")
        if ok and dirname.strip():
            full_path = os.path.join(folder_path, dirname)
            try:
                if not os.path.exists(full_path):
                    os.makedirs(full_path)
                else:
                    QMessageBox.warning(self, "Ошибка", "Папка с таким именем уже существует!")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось создать папку: {str(e)}")

    def delete_item(self, index):
        """Удаляет файл или папку после подтверждения."""
        path = self.model.filePath(index)
        name = self.model.fileName(index)
        
        reply = QMessageBox.question(
            self, 
            "Подтверждение удаления", 
            f"Вы уверены, что хотите удалить '{name}'?\nЭто действие нельзя отменить.",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                if self.model.isDir(index):
                    os.rmdir(path)  # Удалит только пустую папку для безопасности новичка
                else:
                    os.remove(path)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить элемент: {str(e)}")
