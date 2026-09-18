
###**🔴 Ключевая защита — «сухой запуск»:** сначала применитель собирает **новую версию файла целиком в памяти**, компилирует её (для `.py`), и только если всё ок — пишет на диск. Если хоть один якорь не найден или дублируется — **вся операция атомарно отменяется**, файлы не тронуты. Никаких «полу-применённых» правок.

###**Совместимость:** старые форматы `### Файл: x.py` и `### Файл: x.py [APPEND]` работают как раньше. Ничего не сломано.

###---

### 📄 Полный код файла

### Файл: core/patch_applier.py

# core/patch_applier.py
"""«Нейро-интеграция»: разбирает ответ СУЗИ и раскладывает правки по файлам.
По принципу распределительного щита Нормандии: одна большая посылка →
много маленьких пакетов, каждый — в свой отсек.

🛰 РЕЖИМЫ ЗАПИСИ (указываются маркером в заголовке файла или строкой «### РЕЖИМ:»):

  [REPLACE] (по умолчанию) — файл перезаписывается целиком;
  [APPEND]                 — блок кода дописывается в КОНЕЦ файла;
  [REPLACE_BLOCK]          — заменить ОТ якоря НАЧАЛО ДО якоря КОНЕЦ (включительно);
  [REPLACE_BETWEEN]        — заменить ТОЛЬКО МЕЖДУ якорями (якоря остаются);
  [INSERT_AFTER]           — вставить блок ПОСЛЕ строки-якоря;
  [INSERT_BEFORE]          — вставить блок ПЕРЕД строкой-якорем;
  [DELETE_BLOCK]           — удалить якоря и всё содержимое между ними;
  [DELETE_BETWEEN]         — удалить только содержимое между якорями;
  [REPLACE_LINES]          — заменить по номерам строк (### СТРОКИ: N-M).

Пример «хирургического» ответа СУЗИ:

    ### Файл: core/patch_applier.py
    ### РЕЖИМ: replace_between
    ### НАЧАЛО: def apply_patches(
    ### КОНЕЦ: return {
    ```python
        # … тут только новая начинка без обвязки
    ```

⚠️🛡 ЗАЩИТА АТОМАРНОСТИ: перед записью применитель собирает НОВУЮ версию
каждого файла ЦЕЛИКОМ в памяти, для .py проверяет её через compile().
Если где-то якорь не найден/дублируется или в коде синтаксический сбой —
вся операция ОТМЕНЯЕТСЯ, файлы на диске остаются нетронутыми.
"""

import os
import re
from dataclasses import dataclass
from typing import List, Optional

# --- Режимы записи ---
MODE_REPLACE         = "replace"
MODE_APPEND          = "append"
MODE_REPLACE_BLOCK   = "replace_block"
MODE_REPLACE_BETWEEN = "replace_between"
MODE_INSERT_AFTER    = "insert_after"
MODE_INSERT_BEFORE   = "insert_before"
MODE_DELETE_BLOCK    = "delete_block"
MODE_DELETE_BETWEEN  = "delete_between"
MODE_REPLACE_LINES   = "replace_lines"

# Псевдонимы (что можно писать в [XXX] или в «### РЕЖИМ: ...»)
_MODE_ALIASES = {
    "replace":         MODE_REPLACE,
    "full":            MODE_REPLACE,
    "rewrite":         MODE_REPLACE,
    "append":          MODE_APPEND,
    "add":             MODE_APPEND,
    "replace_block":   MODE_REPLACE_BLOCK,
    "block":           MODE_REPLACE_BLOCK,
    "replace_between": MODE_REPLACE_BETWEEN,
    "between":         MODE_REPLACE_BETWEEN,
    "insert_after":    MODE_INSERT_AFTER,
    "after":           MODE_INSERT_AFTER,
    "insert_before":   MODE_INSERT_BEFORE,
    "before":          MODE_INSERT_BEFORE,
    "delete_block":    MODE_DELETE_BLOCK,
    "delete":          MODE_DELETE_BLOCK,
    "delete_between":  MODE_DELETE_BETWEEN,
    "replace_lines":   MODE_REPLACE_LINES,
    "lines":           MODE_REPLACE_LINES,
}

# Человеческие ярлыки для GUI-диалога
MODE_LABELS = {
    MODE_REPLACE:         "полная замена",
    MODE_APPEND:          "дописать в конец",
    MODE_REPLACE_BLOCK:   "замена блока (с якорями)",
    MODE_REPLACE_BETWEEN: "замена между якорями",
    MODE_INSERT_AFTER:    "вставка ПОСЛЕ якоря",
    MODE_INSERT_BEFORE:   "вставка ПЕРЕД якорем",
    MODE_DELETE_BLOCK:    "удаление блока",
    MODE_DELETE_BETWEEN:  "удаление между якорями",
    MODE_REPLACE_LINES:   "замена по строкам",
}

@dataclass
class Patch:
    """Одна правка: файл, код, режим и метаданные для предупреждений."""
    path: str
    rel_path: str
    code: str
    language: str = ""
    exists: bool = False
    mode: str = MODE_REPLACE
    old_lines: int = 0
    new_lines: int = 0
    old_bytes: int = 0
    # Якоря (для блочных режимов)
    start_anchor: Optional[str] = None
    end_anchor: Optional[str] = None
    # Номера строк (для MODE_REPLACE_LINES, 1-based, включительно)
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    # Результат применения (заполняется apply_patches)
    status: str = "pending"        # pending / applied / failed
    message: str = ""

# =========================================================================
# РАЗБОР ОТВЕТА СУЗИ
# =========================================================================

# Строка-маркер файла: «### Файл: x.py» / «📄 x.py» / «**Файл:** x.py» и т.п.
_FILE_LINE_RE = re.compile(
    r'(?:'
    r'^#{1,4}\s*📄'
    r'|^📄'
    r'|^#{1,4}\s*[Фф]айл'
    r'|\*\*\s*[Фф]айл\s*\d*\s*[:—–-]?\s*\*\*'
    r'|[Фф]айл\s*\d+\s*[:—–-]'
    r')'
)

# Путь с узнаваемым расширением
_PATH_EXTRACT_RE = re.compile(
    r'[`"\']?'
    r'([A-Za-z0-9А-Яа-я_\-./\\]+\.'
    r'(?:py|txt|json|qss|css|md|bat|cfg|ini|yaml|yml|html|js|ts|sql))'
    r'[`"\']?',
    re.UNICODE,
)

# Старый маркер режима в квадратных скобках: [APPEND] / [REPLACE_BLOCK] / [BEFORE] ...
_BRACKET_MODE_RE = re.compile(r'\[([A-Za-z_]+)\]')

# Мета-строки применителя
_META_MODE_RE   = re.compile(r'^\s*#{1,4}\s*[Рр]ежим\s*[:=]\s*([A-Za-z_]+)', re.IGNORECASE)
_META_START_RE  = re.compile(r'^\s*#{1,4}\s*(?:[Нн]ачало|[Ss]tart|ОТ)\s*[:=]\s*(.+?)\s*$')
_META_END_RE    = re.compile(r'^\s*#{1,4}\s*(?:[Кк]онец|[Ee]nd|ДО)\s*[:=]\s*(.+?)\s*$')
_META_LINES_RE  = re.compile(r'^\s*#{1,4}\s*(?:[Сс]трок[аи]|[Ll]ines?)\s*[:=]\s*(\d+)\s*[-–—]\s*(\d+)')
_META_LINE1_RE  = re.compile(r'^\s*#{1,4}\s*(?:[Сс]трока|[Ll]ine)\s*[:=]\s*(\d+)')

def _clean_path(raw: str) -> str:
    return raw.strip().strip('`\'"').strip().rstrip('.,;:)')

def _count_lines(text: str) -> int:
    if not text:
        return 0
    return text.count('\n') + 1

def _read_file_safe(path: str) -> Optional[str]:
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception:
        return None

def _make_patch(rel_path: str, project_root: str, code_text: str,
                lang: str, mode: str, start_anchor: Optional[str],
                end_anchor: Optional[str],
                start_line: Optional[int], end_line: Optional[int]) -> Optional[Patch]:
    """Собирает объект Patch, проверяя, что путь находится внутри проекта."""
    raw_path = rel_path.replace('\\', os.sep).replace('/', os.sep)
    if os.path.isabs(raw_path):
        abs_path = os.path.normpath(raw_path)
    else:
        abs_path = os.path.normpath(os.path.join(project_root, raw_path))

    # Защита: не вылезаем за пределы проекта
    try:
        rel_check = os.path.relpath(abs_path, project_root)
        if rel_check.startswith('..'):
            return None
    except ValueError:
        return None

    exists = os.path.exists(abs_path)
    old_lines = 0
    old_bytes = 0
    if exists:
        old_content = _read_file_safe(abs_path)
        if old_content is not None:
            old_lines = _count_lines(old_content)
            old_bytes = len(old_content.encode('utf-8', errors='ignore'))

    return Patch(
        path=abs_path,
        rel_path=rel_path,
        code=code_text,
        language=lang,
        exists=exists,
        mode=mode,
        old_lines=old_lines,
        new_lines=_count_lines(code_text),
        old_bytes=old_bytes,
        start_anchor=start_anchor,
        end_anchor=end_anchor,
        start_line=start_line,
        end_line=end_line,
    )

def extract_patches(response_text: str, project_root: str) -> List[Patch]:
    """Из ответа СУЗИ достаём список правок (файл + код + режим + якоря)."""
    if not response_text:
        return []

    project_root = os.path.abspath(project_root)
    patches: List[Patch] = []
    lines = response_text.split('\n')

    # Текущий «разбираемый» заголовок
    current: Optional[dict] = None

    i = 0
    while i < len(lines):
        line = lines[i]

        # --- 1. Маркер строки файла ---
        if _FILE_LINE_RE.search(line):
            m = _PATH_EXTRACT_RE.search(line)
            if m:
                current = {
                    "rel_path": _clean_path(m.group(1)),
                    "mode": MODE_REPLACE,
                    "start": None,
                    "end": None,
                    "start_line": None,
                    "end_line": None,
                }
                # [APPEND] / [REPLACE_BLOCK] / [BEFORE] и т.п. прямо в заголовке
                for bm in _BRACKET_MODE_RE.finditer(line):
                    key = bm.group(1).lower()
                    if key in _MODE_ALIASES:
                        current["mode"] = _MODE_ALIASES[key]
            i += 1
            continue

        # --- 2. Мета-строки режима/якорей (только если есть текущий файл) ---
        if current is not None:
            s = line.strip()

            m = _META_MODE_RE.match(s)
            if m:
                key = m.group(1).lower()
                if key in _MODE_ALIASES:
                    current["mode"] = _MODE_ALIASES[key]
                i += 1
                continue

            m = _META_START_RE.match(s)
            if m:
                current["start"] = m.group(1).strip()
                i += 1
                continue

            m = _META_END_RE.match(s)
            if m:
                current["end"] = m.group(1).strip()
                i += 1
                continue

            m = _META_LINES_RE.match(s)
            if m:
                current["start_line"] = int(m.group(1))
                current["end_line"] = int(m.group(2))
                if current["mode"] == MODE_REPLACE:
                    current["mode"] = MODE_REPLACE_LINES
                i += 1
                continue

            m = _META_LINE1_RE.match(s)
            if m:
                n = int(m.group(1))
                current["start_line"] = n
                current["end_line"] = n
                if current["mode"] == MODE_REPLACE:
                    current["mode"] = MODE_REPLACE_LINES
                i += 1
                continue

        # --- 3. Фенс с кодом ---
        stripped = line.strip()
        if stripped.startswith('```'):
            lang = stripped[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            i += 1  # закрывающий фенс

            if current:
                # Для режимов-удалений код может быть пустым — это нормально
                has_code = bool(code_lines) or current["mode"] in (
                    MODE_DELETE_BLOCK, MODE_DELETE_BETWEEN)

                if has_code:
                    code_text = '\n'.join(code_lines)
                    p = _make_patch(
                        rel_path=current["rel_path"],
                        project_root=project_root,
                        code_text=code_text,
                        lang=lang,
                        mode=current["mode"],
                        start_anchor=current["start"],
                        end_anchor=current["end"],
                        start_line=current["start_line"],
                        end_line=current["end_line"],
                    )
                    if p is not None:
                        patches.append(p)

            current = None
            continue

        i += 1

    return patches

# =========================================================================
# СБОРКА НОВОЙ ВЕРСИИ ФАЙЛА (in-memory)
# =========================================================================

def _find_anchor_line(lines: List[str], anchor: str) -> int:
    """Индекс строки (0-based), где встречается anchor. Требует УНИКАЛЬНОСТИ."""
    if not anchor:
        raise ValueError("не задан якорь")
    idxs = [i for i, ln in enumerate(lines) if anchor in ln]
    if not idxs:
        raise ValueError(f"якорь не найден: {anchor!r}")
    if len(idxs) > 1:
        raise ValueError(
            f"якорь встречается {len(idxs)} раз(а), нужно уточнить: {anchor!r}")
    return idxs[0]

def _compose_new_content(patch: Patch) -> str:
    """Собирает НОВОЕ содержимое файла в памяти. Не пишет на диск.
    Бросает ValueError с понятным сообщением, если что-то не сходится."""
    mode = patch.mode

    # Прочитаем существующий файл (если он есть)
    old = _read_file_safe(patch.path) if os.path.exists(patch.path) else None

    # Простые режимы
    if mode == MODE_REPLACE:
        return patch.code

    if mode == MODE_APPEND:
        if old is None:
            return patch.code
        if old.endswith("\n\n"):
            sep = ""
        elif old.endswith("\n"):
            sep = "\n"
        else:
            sep = "\n\n"
        return old + sep + patch.code

    # Дальше — режимы, которым нужен существующий файл
    if old is None:
        # Файла нет — трактуем как создание с нуля. Но якоря осмысленны только
        # если файл есть — иначе негде их искать.
        if mode in (MODE_REPLACE_LINES,):
            raise ValueError("файл не существует — замена по строкам невозможна")
        if mode in (MODE_INSERT_AFTER, MODE_INSERT_BEFORE):
            raise ValueError(f"файл не существует — якорь негде искать ({mode})")
        if mode in (MODE_REPLACE_BLOCK, MODE_REPLACE_BETWEEN,
                    MODE_DELETE_BLOCK, MODE_DELETE_BETWEEN):
            if patch.start_anchor or patch.end_anchor:
                raise ValueError("файл не существует — якорь негде искать")
            if mode in (MODE_DELETE_BLOCK, MODE_DELETE_BETWEEN):
                return ""
            return patch.code
        raise ValueError(f"неизвестный режим: {mode}")

    lines = old.split('\n')
    ends_nl = old.endswith('\n')

    def _finish(result_lines: List[str]) -> str:
        text = '\n'.join(result_lines)
        if ends_nl and not text.endswith('\n'):
            text += '\n'
        return text

    # --- Замена по номерам строк ---
    if mode == MODE_REPLACE_LINES:
        if patch.start_line is None or patch.end_line is None:
            raise ValueError("не заданы номера строк")
        s, e = patch.start_line, patch.end_line
        if s < 1 or e < s or e > len(lines):
            raise ValueError(
                f"некорректный диапазон строк: {s}-{e} (в файле {len(lines)} строк)")
        block = patch.code.split('\n') if patch.code else []
        result = lines[:s - 1] + block + lines[e:]
        return _finish(result)

    # --- Блочные режимы (по якорям) ---
    if mode in (MODE_REPLACE_BLOCK, MODE_REPLACE_BETWEEN,
                MODE_DELETE_BLOCK, MODE_DELETE_BETWEEN):
        if not patch.start_anchor or not patch.end_anchor:
            raise ValueError("нужны ОБА якоря: НАЧАЛО и КОНЕЦ")
        s = _find_anchor_line(lines, patch.start_anchor)
        tail = lines[s:]
        try:
            e_rel = next(i for i, ln in enumerate(tail)
                         if patch.end_anchor in ln)
        except StopIteration:
            raise ValueError(
                f"якорь КОНЕЦ не найден после НАЧАЛО: {patch.end_anchor!r}")
        e = s + e_rel
        if e < s:
            raise ValueError("якорь КОНЕЦ расположен выше якоря НАЧАЛО")

        block = patch.code.split('\n') if patch.code else []

        if mode == MODE_REPLACE_BLOCK:
            result = lines[:s] + block + lines[e + 1:]
        elif mode == MODE_REPLACE_BETWEEN:
            result = lines[:s + 1] + block + lines[e:]
        elif mode == MODE_DELETE_BLOCK:
            result = lines[:s] + lines[e + 1:]
        else:  # MODE_DELETE_BETWEEN
            result = lines[:s + 1] + lines[e:]
        return _finish(result)

    # --- Вставка после/перед якорем ---
    if mode in (MODE_INSERT_AFTER, MODE_INSERT_BEFORE):
        if not patch.start_anchor:
            raise ValueError("нужен якорь НАЧАЛО (строка, возле которой вставляем)")
        s = _find_anchor_line(lines, patch.start_anchor)
        block = patch.code.split('\n') if patch.code else []
        if mode == MODE_INSERT_AFTER:
            result = lines[:s + 1] + block + lines[s + 1:]
        else:
            result = lines[:s] + block + lines[s:]
        return _finish(result)

    raise ValueError(f"неизвестный режим: {mode}")

# =========================================================================
# ПРИМЕНЕНИЕ
# =========================================================================

def _ends_with_newline(path: str) -> bool:
    """Проверяет, заканчивается ли файл переводом строки.
    Оставлено для обратной совместимости при APPEND."""
    try:
        with open(path, 'rb') as f:
            f.seek(-1, os.SEEK_END)
            return f.read(1) in (b'\n', b'\r')
    except Exception:
        return True

def _validate_python_syntax(patches: List[Patch]) -> List[tuple]:
    """🛡 Устаревшая проверка по «сырым» блокам. Оставлена для совместимости.
    Новый поток применения проверяет СКЛЕЕННЫЙ файл целиком внутри apply_patches."""
    issues = []
    for p in patches:
        if not p.path.lower().endswith('.py'):
            continue
        if p.mode != MODE_REPLACE:
            continue
        try:
            compile(p.code, p.path, 'exec')
        except SyntaxError as e:
            line_info = f"строка {e.lineno}" if e.lineno else "неизвестная строка"
            issues.append((p.rel_path, f"{line_info}: {e.msg}"))
        except Exception as e:
            issues.append((p.rel_path, f"не удалось скомпилировать: {e}"))
    return issues

def apply_patches(patches: List[Patch], version_history=None) -> dict:
    """Применяет правки на диск. Работает АТОМАРНО:
      1) собирает новую версию каждого файла в памяти;
      2) для .py — проверяет склеенный результат через compile();
      3) только если всё чисто — пишет на диск.

    Возвращает:
      {
        'applied': N,                — сколько файлов успешно записано
        'errors': [(rel_path, msg)], — что не удалось
        'syntax_rejected': bool,     — True если сработала защита синтаксиса
        'anchor_rejected': bool,     — True если сработала защита якорей
      }
    """
    # --- Шаг 1. Сборка новых версий ---
    composed = []   # [(patch, new_text), ...]
    anchor_errors = []

    for p in patches:
        try:
            new_text = _compose_new_content(p)
            composed.append((p, new_text))
        except ValueError as e:
            p.status = "failed"
            p.message = str(e)
            anchor_errors.append((p.rel_path, str(e)))
        except Exception as e:
            p.status = "failed"
            p.message = str(e)
            anchor_errors.append((p.rel_path, f"внутренняя ошибка сборки: {e}"))

    if anchor_errors:
        return {
            'applied': 0,
            'errors': anchor_errors,
            'syntax_rejected': False,
            'anchor_rejected': True,
        }

    # --- Шаг 2. Синтаксическая защита собранных .py ---
    syntax_issues = []
    for p, new_text in composed:
        if p.path.lower().endswith('.py'):
            try:
                compile(new_text, p.path, 'exec')
            except SyntaxError as e:
                line_info = f"строка {e.lineno}" if e.lineno else "неизвестная строка"
                syntax_issues.append(
                    (p.rel_path, f"{line_info}: {e.msg}"))
            except Exception as e:
                syntax_issues.append(
                    (p.rel_path, f"не удалось скомпилировать: {e}"))

    if syntax_issues:
        return {
            'applied': 0,
            'errors': syntax_issues,
            'syntax_rejected': True,
            'anchor_rejected': False,
        }

    # --- Шаг 3. Запись на диск ---
    applied = 0
    write_errors = []
    for p, new_text in composed:
        try:
            # Снимок старой версии — на случай отката
            if version_history and os.path.exists(p.path):
                try:
                    version_history.save_snapshot(p.path)
                except Exception:
                    pass

            # Создаём папку при необходимости
            parent = os.path.dirname(p.path)
            if parent:
                os.makedirs(parent, exist_ok=True)

            with open(p.path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(new_text)

            p.status = "applied"
            p.message = ""
            applied += 1
        except Exception as e:
            p.status = "failed"
            p.message = str(e)
            write_errors.append((p.rel_path, str(e)))

    return {
        'applied': applied,
        'errors': write_errors,
        'syntax_rejected': False,
        'anchor_rejected': False,
    }