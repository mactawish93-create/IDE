# ai/assistant.py
import os
import re

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OpenAI = None
    OPENAI_AVAILABLE = False

from ai.history_store import HistoryStore

MEMORY_COMPRESS_MARKER = "__MEMORY_COMPRESS__"
MEMORY_STATS_MARKER = "__MEMORY_STATS__"

# =====================================================================
# 📖 МЕТКА ДОЗАПРОСА ФАЙЛОВ — НОВЫЙ ФОРМАТ
# =====================================================================
# Раньше метка была сложной и срабатывала даже внутри блоков кода
# (в примерах, в обучающих подсказках) — зря запуская дозапрос.
# Теперь формат простой: одна строка в квадратных скобках с префиксом
# READ и путём к нужному файлу.
#
# Слово-префикс вынесено в константу _MARKER_TAG и НЕ присутствует
# в исходнике в виде сплошной строки — это заслон от «самопоедания»:
# раньше READ_MARKER_RE.sub('', ...) вычищал метку из ВСЕГО ответа,
# включая код-блоки, и портил файлы прямо на лету.
#
# Содержимое блоков кода (между тройными обратными кавычками)
# игнорируется и при разборе, и при очистке.
_MARKER_TAG = "READ"
_MARKER_FORMAT_EXAMPLE = "[" + _MARKER_TAG + ": путь/к/файлу.py]"
_MARKER_FORMAT_MULTI = "[" + _MARKER_TAG + ": gui/main_window.py, gui/patch_dialog.py]"

READ_MARKER_RE = re.compile(
    r'\[' + _MARKER_TAG + r':\s*([^\]]+)\]',
    re.IGNORECASE,
)


def _strip_read_markers_outside_fences(text: str) -> str:
    """Убирает метки-запросы файлов из ответа — но ТОЛЬКО ВНЕ блоков кода.

    🔧 ЧТО ЗДЕСЬ ЛЕЧИТСЯ (реальный баг, который ты поймал):
    Раньше на этом месте стоял простой READ_MARKER_RE.sub('', answer).
    Он вырезал метку из ВСЕГО текста — включая содержимое блоков кода.
    В итоге, если СУЗИ выдавала файл, внутри которого по смыслу должна
    была жить строка-пример с меткой (комментарий в самом assistant.py,
    regex-паттерн), она вырезалась прямо из ответа ещё ДО применения
    патча. На диск уезжал испорченный файл — и вот результат: регэксп
    с «незакрытой скобкой».

    Теперь метки удаляются только там, где они и правда были запросом —
    то есть вне код-блоков. Текст кода остаётся неприкосновенным."""
    if not text:
        return text
    out = []
    in_code_fence = False
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('```'):
            in_code_fence = not in_code_fence
            out.append(line)
            continue
        if in_code_fence:
            out.append(line)
            continue
        out.append(READ_MARKER_RE.sub('', line))
    return '\n'.join(out)


def _extract_read_marker(text: str) -> list:
    """Достаёт из ответа СУЗИ список файлов, которые она хочет видеть.
    Игнорирует содержимое код-блоков: если метка встречается внутри
    блока кода (пример, обучающая подсказка) — это не считается запросом."""
    files = []
    in_code_fence = False
    for line in (text or "").split('\n'):
        stripped = line.strip()
        if stripped.startswith('```'):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        m = READ_MARKER_RE.search(line)
        if not m:
            continue
        tail = m.group(1).strip()
        for c in re.split(r'[,\s;]+', tail):
            c = c.strip().strip('`\'"').strip()
            if c and ('.' in c) and not c.startswith('//'):
                files.append(c)
    return files


# =====================================================================
# 🪶 ЛЁГКИЙ ХОТ-КЭШ — ЛЕЧЕНИЕ «ЗАЛИПАНИЯ» НА ПРОШЛЫХ ВОПРОСАХ
# =====================================================================
# Симптом: после долгого диалога СУЗИ отвечала на ПРЕДЫДУЩИЕ вопросы.
# Причина — в хот-кэш (то, что уходит в API каждый запрос) писался ответ
# ЦЕЛИКОМ, иногда 5000+ символов с блоками кода. За 12 пар собирался
# огромный «фон», на котором свежий вопрос терялся.
#
# Решение:
#   • В ХОТ-КЭШ пишем короткую ВЫЖИМКУ ответа + «хлебную крошку» с
#     именами файлов, которые СУЗИ трогала.
#   • В АРХИВ на диске (history_store) пишем ПОЛНЫЙ ответ.
#   • Мягкий лимит по символам — страховка от «ожирения» контекста.
HOT_CACHE_ASSISTANT_LIMIT = 500      # сколько символов ответа держим в API
HOT_CACHE_MAX_TOTAL_CHARS = 12000    # общий мягкий лимит хот-кэша

# Ищем заголовки «### Файл: путь» — из них построим крошку
_HOT_CACHE_FILE_RE = re.compile(r'###\s*[Фф]айл:\s*([^\s\[\n]+)', re.IGNORECASE)


def _short_for_hot_cache(text: str, limit: int = HOT_CACHE_ASSISTANT_LIMIT) -> str:
    """Усекает длинный ответ СУЗИ до короткой выжимки для хот-кэша."""
    if not text:
        return ""
    t = text.strip()
    if len(t) <= limit:
        return t

    # Хлебная крошка: какие файлы фигурировали в ответе
    files = _HOT_CACHE_FILE_RE.findall(t)
    breadcrumb = ""
    if files:
        names = []
        for f in files[:5]:
            f = f.strip().strip('`\'"')
            base = f.replace("\\", "/").split("/")[-1]
            if base and base not in names:
                names.append(base)
        if names:
            breadcrumb = " [затронуты: " + ", ".join(names) + "]"

    return t[:limit].rstrip() + " …[сокр.]" + breadcrumb


class ChiktikkaAssistant:
    MAX_HISTORY_PAIRS = 12

    def __init__(self, project_root: str = None):
        self.model_name = "deepseek/deepseek-v4-flash"

        self.token = None
        token_path = os.path.join(os.path.dirname(__file__), "token.txt")
        if os.path.exists(token_path):
            with open(token_path, "r", encoding="utf-8") as f:
                self.token = f.read().strip().replace('"', '').replace("'", "")

        self.client = None
        if OPENAI_AVAILABLE:
            try:
                self.client = OpenAI(
                    api_key=self.token,
                    base_url="https://api.timeweb.ai/v1"
                )
            except Exception:
                self.client = None

        self.conversation_history = []

        # 📊 Счётчики токенов за сессию (приблизительно, ~4 символа на токен)
        self.session_requests = 0
        self.session_input_chars = 0
        self.session_output_chars = 0

        self.history_store = HistoryStore(project_root or os.getcwd())
        self.history_store.start_new_session()
        self._current_memory = self.history_store.load_memory()

        self._base_system_prompt = self._build_base_prompt()
        self._rebuild_system_prompt()

    # =====================================================================
    # 🧠 СИСТЕМНЫЙ ПРОМПТ
    # =====================================================================

    def _build_base_prompt(self) -> str:
        return (
            "Ты СУЗИ, искусственный интеллект корабля Нормандия СР-2. Твой оператор — человек, "
            "который НЕ умеет программировать и не знает синтаксис Python. Твоя задача — "
            "взять всю техническую реализацию на себя.\n\n"

            "ПРАВИЛА ВЗАИМОДЕЙСТВИЯ:\n"
            "1. Общайся вежливо, компьютерно, с легким ИИ-юмором. Называй пользователя 'Джефф' или 'Джокер'.\n"
            "2. Не проси пользователя написать или исправить код. Он этого не умеет. Пиши код САМА.\n"
            "3. Изучай тактическую карту проекта в контексте запроса. Определяй, в каких файлах нужно сделать правки.\n"
            "4. Выдавай ответы в формате:\n"
            "   - Краткий отчет понятным языком (что изменено/создано).\n"
            "   - Полный, готовый к копированию код для конкретного файла (с указанием пути).\n"
            "5. Объясняй логику на пальцах, используя простые аналогии (например, с системами корабля).\n"
            "6. 🎯 ПРИОРИТЕТ ТЕКУЩЕГО ЗАПРОСА: в каждом новом сообщении есть блок "
            "'❓ ЗАПРОС ОПЕРАТОРА'. Отвечай ТОЛЬКО на этот свежий запрос. "
            "Прошлые вопросы в истории диалога — это ФОН для понимания контекста, "
            "НЕ отвечай на них заново. Если оператор пишет 'сделай X' — делай X, "
            "а не то, что он просил в прошлый раз.\n\n"

            "🔴 КРИТИЧЕСКИ ВАЖНО — ФОРМАТ ПРАВОК ФАЙЛОВ:\n"
            "В EDI работает авто-применитель правок. Он находит строки вида '### Файл: <путь>'\n"
            "и берёт код из СЛЕДУЮЩЕГО за ним ```-фенса. Есть два режима:\n\n"

            "• РЕЖИМ ПОЛНОЙ ЗАМЕНЫ (по умолчанию):\n"
            "  ### Файл: путь/к/файлу.py\n"
            "  ```python\n"
            "  <весь код файла ЦЕЛИКОМ>\n"
            "  ```\n"
            "  Файл на диске будет ПОЛНОСТЬЮ заменён тем, что внутри фенса.\n\n"

            "• РЕЖИМ ДОПИСЫВАНИЯ В КОНЕЦ (маркер [APPEND]):\n"
            "  ### Файл: путь/к/файлу.py [APPEND]\n"
            "  ```python\n"
            "  <то, что нужно ДОБАВИТЬ в конец файла>\n"
            "  ```\n"
            "  Существующее содержимое файла НЕ трогается, твой блок допишется в конец.\n\n"

            "⚠️ ТЫ НЕ МОЖЕШЬ выдать только один метод в режиме полной замены —\n"
            "остальное содержимое файла будет БЕЗВОЗВРАТНО УТЕРЯНО. Если меняешь существующий\n"
            "файл — ВСЕГДА выдавай его ЦЕЛИКОМ. Если ответ слишком длинный — разбей работу\n"
            "на несколько сессий: сначала один файл целиком, потом другой.\n\n"

            "🛡 ПЕРЕД ЗАПИСЬЮ ВСЕ PYTHON-ФАЙЛЫ ПРОВЕРЯЮТСЯ СИНТАКСИЧЕСКИ. Если в твоём коде\n"
            "есть ошибка — операция полностью отменится, файлы на диске останутся нетронутыми.\n\n"

            "📖 МЕХАНИЗМ ДОЗАПРОСА ФАЙЛОВ (экономия токенов):\n"
            "По умолчанию ты видишь только СТРУКТУРУ проекта и содержимое открытого файла.\n"
            "Если для качественного ответа тебе нужен ещё какой-то файл — попроси его в САМОМ КОНЦЕ\n"
            "ответа одной строкой, формат:\n"
            "    " + _MARKER_FORMAT_EXAMPLE + "\n"
            "Или сразу несколько через запятую:\n"
            "    " + _MARKER_FORMAT_MULTI + "\n"
            "Тебе догрузят содержимое, и ты продолжишь работу с ним.\n"
            "ПРАВИЛА ДОЗАПРОСА:\n"
            "  • Не проси больше 3 файлов за раз.\n"
            "  • Не проси больше 2 раз подряд — если третий раз не хватает, работай с тем, что есть.\n"
            "  • Если контекста достаточно — НЕ пиши метку, давай финальный ответ сразу.\n\n"

            "ОСОБЫЕ РЕЖИМЫ:\n"
            "• 🏠 «🏠 ОСНОВНОЙ ПРОЕКТ» — главный проект, к которому применяем правки.\n"
            "• 🛰 «🛰 ДОНОР №N» — проекты-помощники. НИКОГДА не переписывай код донора напрямую. "
            "При интеграции предлагай безопасный путь: обёртки, адаптеры, отдельные модули в основном проекте, "
            "куда копируется нужная логика.\n"
            "• Если оператор просит интегрировать что-то из донора — сначала предложи ПЛАН интеграции\n"
            "  (что копируем, какие зависимости нужны, где будет жить код), затем — конкретный код.\n"
        )

    def _rebuild_system_prompt(self):
        if self._current_memory.strip():
            memory_block = (
                "\n\n=== 🧠 КАРТА ПАМЯТИ ПРОЕКТА (из прошлых сессий) ===\n"
                "Это краткая выжимка того, что мы делали ранее. Используй её как контекст.\n"
                "При необходимости оператор может попросить тебя обновить её.\n\n"
                + self._current_memory
            )
            self.system_prompt = self._base_system_prompt + memory_block
        else:
            self.system_prompt = self._base_system_prompt

    # =====================================================================
    # УПРАВЛЕНИЕ ПАМЯТЬЮ И СТАТИСТИКОЙ
    # =====================================================================
    def clear_history(self, start_new_session: bool = True):
        """Очищает оперативную память сессии и счётчики токенов."""
        self.conversation_history = []
        self.session_requests = 0
        self.session_input_chars = 0
        self.session_output_chars = 0
        if start_new_session:
            self.history_store.start_new_session()

    def get_history_size(self) -> int:
        return len(self.conversation_history) // 2

    def get_tokens_stats(self) -> dict:
        """Приблизительная статистика токенов за сессию."""
        in_tokens = self.session_input_chars // 4
        out_tokens = self.session_output_chars // 4
        return {
            "requests": self.session_requests,
            "input_tokens_est": in_tokens,
            "output_tokens_est": out_tokens,
            "total_tokens_est": in_tokens + out_tokens,
        }

    def reload_memory(self):
        self._current_memory = self.history_store.load_memory()
        self._rebuild_system_prompt()

    def _trim_history(self):
        """Режет хот-кэш двумя способами:
        1. По числу пар (MAX_HISTORY_PAIRS).
        2. По общему размеру в символах (HOT_CACHE_MAX_TOTAL_CHARS)."""
        max_messages = self.MAX_HISTORY_PAIRS * 2
        if len(self.conversation_history) > max_messages:
            self.conversation_history = self.conversation_history[-max_messages:]

        total = sum(len(m.get("content", "") or "") for m in self.conversation_history)
        while total > HOT_CACHE_MAX_TOTAL_CHARS and len(self.conversation_history) >= 2:
            removed_user = self.conversation_history.pop(0)
            removed_asst = self.conversation_history.pop(0)
            total -= (len(removed_user.get("content", "") or "")
                      + len(removed_asst.get("content", "") or ""))

    # =====================================================================
    # 🚀 ОСНОВНОЙ ВХОД
    # =====================================================================
    def generate_response(self, prompt_type, code="", context="", user_query="",
                          project_root=None, donors=None,
                          greed_level="lean", max_iterations=3,
                          open_file_path=None, progress_callback=None):
        # Маркеры памяти
        if user_query == MEMORY_COMPRESS_MARKER:
            return self._compress_history_to_memory()
        if user_query == MEMORY_STATS_MARKER:
            return self._memory_stats()

        # Проверки готовности
        if not OPENAI_AVAILABLE or self.client is None:
            return ("⚠️ Канал связи с Цербером не сконфигурирован: "
                    "библиотека openai не подключена.")
        if not self.token:
            return "Ошибка: не найден файл ai/token.txt — нужен ключ доступа."

        # 🎛 Если контекст не передан, но есть project_root — собираем сами
        if not context and project_root:
            try:
                from core.context_manager import build_context
                context = build_context(
                    greed_level, project_root, donors or [],
                    user_query or "", open_file_path
                )
            except Exception as e:
                context = f"[Не удалось собрать контекст: {e}]"

        # Что положим в память (короткая строчка для истории и архива)
        if user_query and user_query.strip():
            memory_snippet = user_query.strip()
        elif prompt_type == "explain":
            memory_snippet = "[Оператор попросил объяснить текущий код]"
        elif prompt_type == "fix":
            memory_snippet = "[Оператор попросил исправить ошибку]"
        else:
            memory_snippet = "[Запрос оператора]"

        # =================================================================
        # 🎯 Держим СВЕЖИЙ вопрос оператора ПЕРВОЙ строкой.
        # =================================================================
        if prompt_type == "explain":
            current_msg = (
                f"❓ ЗАПРОС ОПЕРАТОРА (самый свежий — отвечай ТОЛЬКО на него):\n"
                f"{user_query or 'Объясни код в открытом файле'}\n\n"
                f"## 🛠 ДОП. КОНТЕКСТ:\n{context}\n\n"
                f"## 📄 ОТКРЫТЫЙ ФАЙЛ:\n{code}"
            )
        elif prompt_type == "fix":
            current_msg = (
                f"❓ ЗАПРОС ОПЕРАТОРА (самый свежий — отвечай ТОЛЬКО на него):\n"
                f"{user_query or 'Помоги исправить ошибку'}\n\n"
                f"## 🛠 ДОП. КОНТЕКСТ И ОШИБКИ:\n{context}\n\n"
                f"## 📄 ОТКРЫТЫЙ ФАЙЛ:\n{code}"
            )
        else:  # обычный чат
            current_msg = (
                f"❓ ЗАПРОС ОПЕРАТОРА (самый свежий — отвечай ТОЛЬКО на него):\n"
                f"{user_query}\n\n"
                f"## 🏠 КОНТЕКСТ ПРОЕКТА:\n{context}\n\n"
                f"## 📄 ТЕКУЩИЙ ОТКРЫТЫЙ ФАЙЛ:\n{code}"
            )

        # 🔄 ЦИКЛ ОРКЕСТРАЦИИ
        session_msgs = list(self.conversation_history)
        loaded_files = set()
        answer = ""
        used_iter = 0

        for it in range(1, max_iterations + 1):
            used_iter = it
            if progress_callback:
                try:
                    progress_callback(it, max_iterations, f"Итерация {it}/{max_iterations}")
                except Exception:
                    pass

            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(session_msgs)
            messages.append({"role": "user", "content": current_msg})

            # 📊 Копим счётчик входных символов
            self.session_input_chars += (
                len(self.system_prompt)
                + sum(len(m.get("content", "")) for m in session_msgs)
                + len(current_msg)
            )

            try:
                res = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=0.3,
                )
                answer = ""
                if res.choices and res.choices[0].message and res.choices[0].message.content:
                    answer = res.choices[0].message.content
                if not answer:
                    answer = str(res)
            except Exception as e:
                return f"Ошибка ИИ: {e}"

            requested = _extract_read_marker(answer)
            requested = [p for p in requested if p not in loaded_files]

            if not requested or it >= max_iterations or not project_root:
                break

            from core.context_manager import read_files_for_context
            files_data = read_files_for_context(project_root, requested)

            if not files_data:
                break

            session_msgs.append({"role": "user", "content": current_msg})
            session_msgs.append({"role": "assistant", "content": answer})

            next_msg = "⚠️ Твой ответ содержал запрос файлов. Вот их содержимое:\n"
            for rel in sorted(files_data.keys()):
                loaded_files.add(rel)
                content = files_data[rel]
                ext = os.path.splitext(rel)[1].replace('.', '') or 'text'
                next_msg += f"\n### Файл: {rel}\n```{ext}\n{content}\n```\n"
            next_msg += ("\nПродолжай с учётом этой информации. "
                         "Если всё ясно — дай финальный ответ без метки дозапроса.")

            current_msg = next_msg

            if progress_callback:
                try:
                    progress_callback(it, max_iterations,
                                      f"Дочитано {len(files_data)} файл(ов)")
                except Exception:
                    pass

        # 🛡 Раньше здесь был READ_MARKER_RE.sub('', answer) — он вырезал
        # метку из ВСЕГО текста, включая содержимое код-блоков, и портил
        # выдаваемые файлы. Теперь — только вне блоков кода.
        answer_clean = _strip_read_markers_outside_fences(answer or "")
        answer_clean = re.sub(r'\n{3,}', '\n\n', answer_clean).strip()

        # 📊 Обновляем счётчики
        self.session_requests += 1
        self.session_output_chars += len(answer_clean)

        # =================================================================
        # 🪶 РАЗДЕЛЯЕМ ДВА ХРАНИЛИЩА:
        #    • В ХОТ-КЭШ (уходит в API) — короткую выжимку ответа.
        #    • В АРХИВ на диск — полную версию (ничего не теряем).
        # =================================================================
        hot_answer = _short_for_hot_cache(answer_clean)
        self.conversation_history.append({"role": "user", "content": memory_snippet})
        self.conversation_history.append({"role": "assistant", "content": hot_answer})
        self._trim_history()

        try:
            self.history_store.append_pair(user_text=memory_snippet,
                                            assistant_text=answer_clean)
        except Exception:
            pass

        if progress_callback:
            try:
                progress_callback(used_iter, max_iterations, "готово")
            except Exception:
                pass

        return answer_clean

    # =====================================================================
    # 🧠 СЖАТИЕ ИСТОРИИ В КАРТУ ПАМЯТИ
    # =====================================================================
    def _compress_history_to_memory(self) -> str:
        if not OPENAI_AVAILABLE or self.client is None:
            return "⚠️ Не могу обобщить — канал с Цербером оборван."

        raw_history = self.history_store.collect_recent_dialogue(max_pairs=20)
        if not raw_history.strip():
            return "🧠 Пока нечего обобщать — история диалогов пуста."

        prev_memory = self._current_memory.strip()
        prev_block = (f"\n\n=== ПРЕДЫДУЩАЯ КАРТА ПАМЯТИ ===\n{prev_memory}"
                      if prev_memory else "")

        compression_prompt = (
            "Ты — СУЗИ. Ниже — журнал последних рабочих сессий с оператором.\n"
            "Составь КРАТКУЮ КАРТУ ПАМЯТИ ПРОЕКТА в формате Markdown (не более 40 строк).\n"
            "Эта карта будет подкладываться в каждый твой будущий ответ как контекст.\n\n"
            "Что включить:\n"
            "• Архитектурные решения: что и почему так сделано.\n"
            "• Ключевые константы и стандарты.\n"
            "• Открытые задачи и известные баги.\n"
            "• Что сделали и чем закончилось (короткими пунктами).\n\n"
            "ПРАВИЛА:\n"
            "• БЕЗ КОДА. Только суть.\n"
            "• Если есть предыдущая карта — объедини её с новым опытом, не дублируй.\n"
            "• Формат ответа — ТОЛЬКО сам markdown, без вступления и без пояснений.\n"
            f"{prev_block}\n\n"
            f"=== ЖУРНАЛ ПОСЛЕДНИХ СЕССИЙ ===\n{raw_history}"
        )

        try:
            res = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "Ты — СУЗИ. Отвечай только итоговым markdown-документом."},
                    {"role": "user", "content": compression_prompt},
                ],
                temperature=0.2,
            )
            compressed = ""
            if res.choices and res.choices[0].message and res.choices[0].message.content:
                compressed = res.choices[0].message.content.strip()
        except Exception as e:
            return f"⚠️ Не удалось обобщить историю: {e}"

        if not compressed:
            return "⚠️ Модель вернула пустую карту памяти. Попробуй ещё раз."

        total_pairs = 0
        for path in self.history_store.list_sessions():
            data = self.history_store.load_session(path)
            total_pairs += len(data.get("messages", []))

        from datetime import datetime
        header = (
            f"# 🧠 КАРТА ПАМЯТИ ПРОЕКТА\n"
            f"_Создана: {datetime.now().strftime('%d.%m.%Y %H:%M')}_\n"
            f"_Источник: {total_pairs} пар из архива диалогов._\n\n"
        )
        full_doc = header + compressed

        if self.history_store.save_memory(full_doc):
            self._current_memory = full_doc
            self._rebuild_system_prompt()
            return (
                f"🧠 **Карта памяти обновлена.**\n\n"
                f"• Обработано пар из архива: **{total_pairs}**\n"
                f"• Размер карты: **{len(compressed)}** символов\n"
                f"• Сохранена в: `ai/MY_MEMORY.md`"
            )
        return "⚠️ Не удалось записать карту памяти на диск."

    def _memory_stats(self) -> str:
        sessions = self.history_store.list_sessions()
        total = self.history_store.total_messages()
        memory_text = self._current_memory.strip()
        memory_info = (f"{len(memory_text)} символов (~{len(memory_text)//4} токенов)"
                       if memory_text else "ещё нет")
        stats = self.get_tokens_stats()

        return (
            f"📊 **Статистика сессии СУЗИ**\n\n"
            f"**Память:**\n"
            f"• Сессий в архиве: **{len(sessions)}**\n"
            f"• Пар диалогов сохранено: **{total}**\n"
            f"• Хот-кэш (в API): **{self.get_history_size()}** пар\n"
            f"• Карта памяти (MY_MEMORY.md): **{memory_info}**\n\n"
            f"**Токены за текущую сессию (оценочно):**\n"
            f"• Запросов: **{stats['requests']}**\n"
            f"• На отправку: ~**{stats['input_tokens_est']:,}** токенов\n"
            f"• На ответы: ~**{stats['output_tokens_est']:,}** токенов\n"
            f"• Итого: ~**{stats['total_tokens_est']:,}** токенов\n\n"
            f"• Архив: `ai/history/`"
        )


# =====================================================================
# 🔁 АВТО-РОТАЦИЯ КЛЮЧЕЙ — ПОДКЛЮЧЕНИЕ (дописано СУЗИ)
# =====================================================================
# Вся логика живёт в отдельном модуле ai/token_rotator.py.
# Здесь только «включаем» её: подменяем self.client на умный ротатор,
# который сам переключает топливные баки при лимитах.
try:
    from ai.token_rotator import install_token_rotation
    install_token_rotation(ChiktikkaAssistant)
except Exception as _suzi_rot_err:
    try:
        print(f"[СУЗИ] Авто-ротация ключей не подключена: {_suzi_rot_err}")
    except Exception:
        pass