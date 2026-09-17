# gui/code_editor.py — ЧАСТЬ 1 (Обновленная с RGB/HEX палитрой)
import re
from PySide6.QtWidgets import QTextEdit, QWidget, QCompleter, QColorDialog
from PySide6.QtGui import QFont, QPainter, QColor, QPaintEvent, QTextCursor
from PySide6.QtCore import QSize, Qt, QRect, QStringListModel

class LineNumberArea(QWidget):
    """Боковая панель для отрисовки номеров строк."""
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event: QPaintEvent):
        self.code_editor.line_number_area_paint_event(event)


class CodeEditor(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.line_number_area = LineNumberArea(self)
        self.init_completer()
        
        self.document().blockCountChanged.connect(self.update_line_number_area_width)
        self.verticalScrollBar().valueChanged.connect(self.line_number_area.update)
        self.textChanged.connect(self.line_number_area.update)
        
        self.update_line_number_area_width()
        
        # Разрешаем отслеживание мыши для тултипов
        self.setMouseTracking(True)

    def init_ui(self):
        font = QFont("Consolas", 12)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.setPlaceholderText("# Напиши свой Python код здесь...\n# Например: print('Keelah se\'lai!')")

        # Встроенная база знаний для тултипов (оставляем старую)
        self.tooltip_dict = {
            "print": "<b>print(...)</b><br>Выводит текст на экран.",
            "input": "<b>input(...)</b><br>Запрашивает ввод текста с клавиатуры.",
            "range": "<b>range(от, до)</b><br>Создает последовательность чисел.",
            "append": "<b>.append(...)</b><br>Добавляет элемент в конец списка.",
            "len": "<b>len(...)</b><br>Возвращает длину строки или списка.",
            "import": "<b>import модуль</b><br>Подключает внешние библиотеки."
        }

    def mouseDoubleClickEvent(self, event):
        """Перехватываем двойной клик для поиска и редактирования цветов в коде."""
        cursor = self.textCursor()
        
        # 1. Проверяем HEX-формат (например, #FF6A00)
        # Выделяем строку, где стоит курсор, чтобы найти в ней регулярное выражение
        cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        line_text = cursor.selectedText()
        line_start = cursor.selectionStart()
        
        # Регулярка для HEX цветов
        hex_match = re.search(r"#[0-9a-fA-F]{6}\b", line_text)
        if hex_match:
            start_pos = line_start + hex_match.start()
            end_pos = line_start + hex_match.end()
            
            # Если клик попал именно на этот HEX код
            current_pos = self.cursorForPosition(event.position().toPoint()).position()
            if start_pos <= current_pos <= end_pos:
                hex_color = hex_match.group()
                self.open_color_picker_and_replace(hex_color, "hex", start_pos, end_pos)
                return

        # 2. Проверяем RGB-формат (например, (255, 106, 0) или)
        rgb_match = re.search(r"[\(\[\s]*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})[\)\]\s]*", line_text)
        if rgb_match:
            start_pos = line_start + rgb_match.start()
            end_pos = line_start + rgb_match.end()
            
            current_pos = self.cursorForPosition(event.position().toPoint()).position()
            if start_pos <= current_pos <= end_pos:
                r, g, b = map(int, rgb_match.groups())
                if all(0 <= val <= 255 for val in (r, g, b)):
                    self.open_color_picker_and_replace(QColor(r, g, b), "rgb", start_pos, end_pos)
                    return

        # Если дважды кликнули не по цвету — выполняем стандартное выделение слова в Qt
        super().mouseDoubleClickEvent(event)

    def open_color_picker_and_replace(self, initial_color, color_type, start, end):
        """Открывает диалог палитры и заменяет старый текст новым цветом."""
        q_color = QColor(initial_color) if color_type == "hex" else initial_color
        
        # Открываем системное окно палитры
        new_color = QColorDialog.getColor(q_color, self, "Выберите цвет для Омни-инструмента")
        
        if new_color.isValid():
            # Формируем новую строку в зависимости от старого формата
            if color_type == "hex":
                new_text = new_color.name().upper() # Вернет формат #RRGGBB
            else:
                new_text = f"({new_color.red()}, {new_color.green()}, {new_color.blue()})"
                
            # Перемещаем курсор к границам старого текста и заменяем его
            tc = self.textCursor()
            tc.setPosition(start)
            tc.setPosition(end, QTextCursor.MoveMode.KeepAnor)
            tc.insertText(new_text)
# gui/code_editor.py — ЧАСТЬ 2 (Обновленная с RGB/HEX палитрой)

    # --- ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ АВТОДОПОЛНЕНИЯ (COMPLETER) ---

    def init_completer(self):
        words = ["print", "input", "append", "range", "length", "split", "join", "import", "from", "return", "def", "class", "if", "elif", "else", "while", "for", "in", "try", "except", "True", "False", "None"]
        self.completer = QCompleter(self)
        self.completer.setModel(QStringListModel(words, self.completer))
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.activated.connect(self.insert_completion)

    def insert_completion(self, completion):
        tc = self.textCursor()
        extra = len(completion) - len(self.completer.completionPrefix())
        tc.movePosition(QTextCursor.MoveOperation.Left)
        tc.movePosition(QTextCursor.MoveOperation.EndOfWord)
        tc.insertText(completion[-extra:])
        self.setTextCursor(tc)

    def text_under_cursor(self):
        tc = self.textCursor()
        tc.select(QTextCursor.SelectionType.WordUnderCursor)
        return tc.selectedText()

    def keyPressEvent(self, event):
        if self.completer and self.completer.popup().isVisible():
            if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab, Qt.Key.Key_Escape):
                event.ignore()
                return
        super().keyPressEvent(event)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier or not event.text():
            return
        completion_prefix = self.text_under_cursor()
        if len(completion_prefix) < 2:
            self.completer.popup().hide()
            return
        if completion_prefix != self.completer.completionPrefix():
            self.completer.setCompletionPrefix(completion_prefix)
            self.completer.popup().setCurrentIndex(self.completer.completionModel().index(0, 0))
        cr = self.cursorRect()
        cr.setWidth(self.completer.popup().sizeHint().width())
        self.completer.complete(cr)

    # --- МАСШТАБ И ДВИЖЕНИЕ МЫШИ (TOOLTIPS) ---

    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            current_font = self.font()
            current_size = current_font.pointSize()
            new_size = current_size + 1 if event.angleDelta().y() > 0 else current_size - 1
            if 6 <= new_size <= 48:
                current_font.setPointSize(new_size)
                self.setFont(current_font)
                self.update_line_number_area_width()
                self.line_number_area.update()
            event.accept()
        else:
            super().wheelEvent(event)

    def mouseMoveEvent(self, event):
        """Отслеживает движение мыши для показа всплывающих подсказок (Tooltips)."""
        from PySide6.QtWidgets import QToolTip
        pos = event.position().toPoint()
        cursor = self.cursorForPosition(pos)
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        word = cursor.selectedText().strip()
        
        if word in self.tooltip_dict:
            global_pos = self.mapToGlobal(pos)
            QToolTip.showText(global_pos, self.tooltip_dict[word], self)
        else:
            QToolTip.hideText()
            
        super().mouseMoveEvent(event)

    # --- МАТЕМАТИКА И ОТРИСОВКА НОМЕРОВ СТРОК ---

    def line_number_area_width(self) -> int:
        digits = 1
        max_lines = max(1, self.document().blockCount())
        while max_lines >= 10:
            max_lines /= 10
            digits += 1
        return 15 + self.fontMetrics().horizontalAdvance('9') * digits

    def update_line_number_area_width(self):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def paintEvent(self, event: QPaintEvent):
        """Динамическая отрисовка линий границ классов и методов (Scope Guides)."""
        painter = QPainter(self.viewport())
        bg_color = self.palette().color(self.backgroundRole())
        if bg_color.lightness() > 128:
            painter.setPen(QColor(100, 100, 100, 45))  # Серый для светлой темы
        else:
            painter.setPen(QColor(122, 107, 155, 60))  # Фиолетовый для темных тем
        
        space_width = self.fontMetrics().horizontalAdvance(' ')
        tab_stop_width = space_width * 4
        
        if tab_stop_width > 0:
            block = self.document().begin()
            line_height = self.fontMetrics().height()
            while block.isValid():
                if block.isVisible():
                    text = block.text()
                    if text.strip():
                        leading_spaces = len(text) - len(text.lstrip())
                        indent_level = leading_spaces // 4
                        block_geometry = self.document().documentLayout().blockBoundingRect(block)
                        block_top = block_geometry.top() - self.verticalScrollBar().value()
                        
                        if block_top + line_height > 0 and block_top < self.viewport().height():
                            for level in range(1, indent_level + 1):
                                x_pos = (level * tab_stop_width) + 2
                                painter.drawLine(int(x_pos), int(block_top), int(x_pos), int(block_top + line_height))
                block = block.next()
        painter.end()
        super().paintEvent(event)

    def line_number_area_paint_event(self, event: QPaintEvent):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(20, 20, 30, 20))
        visible_rect = event.rect()
        block = self.document().begin()
        block_number = 1
        while block.isValid():
            block_geometry = self.document().documentLayout().blockBoundingRect(block)
            block_top = block_geometry.top() - self.verticalScrollBar().value()
            block_bottom = block_top + block_geometry.height()
            if block_top <= visible_rect.bottom() and block_bottom >= visible_rect.top():
                painter.setPen(QColor("#7A6B9B"))
                if block == self.document().findBlock(self.textCursor().position()):
                    painter.setPen(QColor("#FF9F1C"))
                painter.drawText(0, int(block_top), self.line_number_area.width() - 5, self.fontMetrics().height(), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(block_number))
            block = block.next()
            block_number += 1
