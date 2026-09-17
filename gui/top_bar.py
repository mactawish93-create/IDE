# gui/top_bar.py
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QComboBox, QLineEdit, QLabel
from PySide6.QtCore import Signal, Qt

class TopBar(QWidget):
    # Сигналы для работы с файлами и запуска
    new_project_clicked = Signal()
    open_file_clicked = Signal()
    save_file_clicked = Signal()
    run_clicked = Signal()
    stop_clicked = Signal()
    theme_changed = Signal(str)
    
    # Сигналы для кастомного управления окном Windows
    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()
    
    # Сигнал для поиска
    search_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        # Фиксируем высоту панели заголовка
        self.setFixedHeight(35)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(6)

        # --- ЛЕВАЯ ЧАСТЬ: Название ПО и текстовые кнопки управления файлами ---
        self.title_label = QLabel("EDI - Cerberus Edition", self)
        self.title_label.setStyleSheet("font-weight: bold; margin-right: 5px;")
        layout.addWidget(self.title_label)

        # Текстовые кнопки вместо пустых иконок-квадратов
        self.btn_new = QPushButton("Новый", self)
        self.btn_new.setFixedHeight(24)
        
        self.btn_open = QPushButton("Открыть", self)
        self.btn_open.setFixedHeight(24)
        
        self.btn_save = QPushButton("Сохранить", self)
        self.btn_save.setFixedHeight(24)
                
        self.btn_run = QPushButton("RUN 🚀", self)
        self.btn_run.setFixedHeight(24)
        self.btn_run.setObjectName("run_button")

        self.btn_stop = QPushButton("СТОП", self)
        self.btn_stop.setFixedHeight(24)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setObjectName("stop_button")

        self.settings_btn = QPushButton("Настройки", self)
        self.settings_btn.setFixedHeight(24)

        layout.addWidget(self.btn_new)
        layout.addWidget(self.btn_open)
        layout.addWidget(self.btn_save)
        layout.addWidget(self.btn_run)
        layout.addWidget(self.btn_stop)
        layout.addWidget(self.settings_btn)

        # Плавный сдвиг к центру
        layout.addStretch()

        # --- ЦЕНТРАЛЬНАЯ ЧАСТЬ: Поиск по коду (VS Code Style) ---
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("🔍 Поиск по коду (Enter)...")
        self.search_input.setFixedWidth(240)
        self.search_input.setFixedHeight(24)
        self.search_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.search_input)

        # Плавный сдвиг к правому краю
        layout.addStretch()

        # --- ПРАВАЯ ЧАСТЬ: Выбор темы и Стандартные кнопки окон Windows ---
        self.theme_combo = QComboBox(self)
        self.theme_combo.setFixedHeight(24)
        self.theme_combo.setFixedWidth(130)
        self.theme_combo.addItem("Тёмный", "hacker")
        self.theme_combo.addItem("Цербер", "quarian")
        self.theme_combo.addItem("Светлый", "light")
        layout.addWidget(self.theme_combo)

        # Кнопки управления окном (Стилизация под нативную Windows)
        self.btn_min = QPushButton("—", self)
        self.btn_min.setFixedSize(46, 32)
        self.btn_min.setObjectName("window_min_button")
        
        self.btn_max = QPushButton("🗖", self)
        self.btn_max.setFixedSize(46, 32)
        self.btn_max.setObjectName("window_max_button")
        
        self.btn_close = QPushButton("✕", self)
        self.btn_close.setFixedSize(46, 32)
        self.btn_close.setObjectName("window_close_button")


        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(self.btn_close)

        # --- СВЯЗЫВАНИЕ СОБЫТИЙ ---
        self.btn_new.clicked.connect(self.new_project_clicked.emit)
        self.btn_open.clicked.connect(self.open_file_clicked.emit)
        self.btn_save.clicked.connect(self.save_file_clicked.emit)
        self.btn_stop.clicked.connect(self.stop_clicked.emit)
        self.btn_run.clicked.connect(self.run_clicked.emit)
        
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        self.search_input.returnPressed.connect(self.on_search_submitted)
        
        self.btn_min.clicked.connect(self.minimize_requested.emit)
        self.btn_max.clicked.connect(self.maximize_requested.emit)
        self.btn_close.clicked.connect(self.close_requested.emit)

    def on_theme_changed(self, index):
        self.theme_changed.emit(self.theme_combo.itemData(index))

    def on_search_submitted(self):
        self.search_requested.emit(self.search_input.text())
