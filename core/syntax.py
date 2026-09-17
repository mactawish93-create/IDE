# core/syntax.py
import re
from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont

class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []

    def apply_theme(self, theme_name):
        """Динамически настраивает цвета под выбранную тему."""
        self.highlighting_rules.clear()

        # Цветовые палитры для тем
        if theme_name == "quarian":
            color_keyword = "#FF6A00"    # Неоново-оранжевый Цербер
            color_string = "#00E5FF"     # Яркий квантовый голубой
            color_comment = "#666670"    # Приглушенный стальной серый
            color_function = "#E1E1E6"   # Жемчужно-белый
            color_number = "#FF3333"     # Тревожный красный
        elif theme_name == "hacker":     # Теперь это стиль VS Code
            color_keyword = "#569CD6"    # Синий VS Code
            color_string = "#CE9178"     # Терракотовый
            color_comment = "#6A9955"    # Зеленый комментарий
            color_function = "#DCDCAA"   # Желтые функции
            color_number = "#B5CEA8"     # Светло-зеленые числа
        else:                            # Light тема
            color_keyword = "#0000FF"    # Синий классический
            color_string = "#A31515"     # Темно-красный
            color_comment = "#008000"    # Зеленый
            color_function = "#745310"   # Коричневый
            color_number = "#098658"     # Мягкий зеленый

        # Ключевые слова Python
        keywords = [
            "False", "None", "True", "and", "as", "assert", "async", "await",
            "break", "class", "continue", "def", "del", "elif", "else", "except",
            "finally", "for", "from", "global", "if", "import", "in", "is",
            "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
            "while", "with", "yield", "print"
        ]

        # 1. Формат для Ключевых слов
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor(color_keyword))
        keyword_format.setFontWeight(QFont.Weight.Bold)
        for word in keywords:
            pattern = QRegularExpression(rf"\b{word}\b")
            self.highlighting_rules.append((pattern, keyword_format))

        # 2. Формат для Строк (в одинарных или двойных кавычках)
        string_format = QTextCharFormat()
        string_format.setForeground(QColor(color_string))
        self.highlighting_rules.append((QRegularExpression(r"\"[^\"]*\""), string_format))
        self.highlighting_rules.append((QRegularExpression(r"\'[^\']*\'"), string_format))

        # 3. Формат для Чисел
        number_format = QTextCharFormat()
        number_format.setForeground(QColor(color_number))
        self.highlighting_rules.append((QRegularExpression(r"\b[0-9]+\b"), number_format))

        # 4. Формат для Комментариев (от знака # до конца строки)
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor(color_comment))
        comment_format.setFontItalic(True)
        self.highlighting_rules.append((QRegularExpression(r"#[^\n]*"), comment_format))

        # Принудительно вызываем перерисовку всего документа
        self.rehighlight()

    def highlightBlock(self, text):
        """Автоматически вызывается Qt для каждой строки текста."""
        for pattern, format in self.highlighting_rules:
            expression = QRegularExpression(pattern)
            match_iterator = expression.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)
