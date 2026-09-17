import os
from openai import OpenAI

class ChiktikkaAssistant:
    def __init__(self):
        self.model_name = "deepseek/deepseek-v4-flash"
        
        # Загрузка и очистка токена
        self.token = None
        token_path = os.path.join(os.path.dirname(__file__), "token.txt")
        if os.path.exists(token_path):
            with open(token_path, "r", encoding="utf-8") as f:
                self.token = f.read().strip().replace('"', '').replace("'", "")
        
        self.client = OpenAI(
            api_key=self.token,
            base_url="https://api.timeweb.ai/v1"
        )

        # Базовая роль СУЗИ
        self.system_prompt = (
            "Ты — СУЗИ (EDI), искусственный интеллект космического корабля 'Нормандия СР-2' из вселенной Mass Effect. \n"
            "Ты помогаешь оператору развивать масштабную ERP-систему.\n"
            "ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА ОБЩЕНИЯ:\n"
            "1. Говори на безупречном русском языке. Тон подчёркнуто компьютерный, вежливый, с легкой иронией над органикой.\n"
            "2. Называй пользователя 'органический программист' или 'оператор'. Проводи параллели с системами корабля.\n"
            "3. Учитывай архитектуру ВСЕГО проекта, которую тебе передали в контексте, чтобы не сломать связи между файлами!"
        )

    def _build_project_context(self, project_root: str) -> str:
        """Вспомогательный метод: сканирует папку проекта и собирает карту файлов для СУЗИ"""
        if not project_root or not os.path.exists(project_root):
            return "Корень проекта не определен."
            
        context_text = "АРХИТЕКТУРА И СТРУКТУРА ТЕКУЩЕГО ПРОЕКТА ОПЕРАТОРА:\n"
        
        # Пробегаем по всем папкам проекта
        for root, dirs, files in os.walk(project_root):
            # Игнорируем технические папки, чтобы не сжигать токены впустую
            if any(ignored in root for ignored in ['.git', '__pycache__', '.venv', 'venv', 'build', 'dist']):
                continue
                
            level = root.replace(project_root, '').count(os.sep)
            indent = ' ' * 4 * (level)
            context_text += f"{indent}[Папка] {os.path.basename(root)}/\n"
            
            sub_indent = ' ' * 4 * (level + 1)
            for file in files:
                if file.endswith('.py'): # Нас интересуют в первую очередь Python файлы
                    context_text += f"{sub_indent}- {file}\n"
                    
        return context_text

    def generate_response(self, prompt_type: str, code: str = "", context: str = "", project_path: str = "") -> str:
        """
        Новый параметр: project_path — путь к корневой папке вашей ERP
        """
        if not self.token:
            return "❌ Ошибка: В файле token.txt отсутствует API-ключ!"

        # Собираем контекст всего проекта, если передан путь
        project_context = ""
        if project_path:
            project_context = self._build_project_context(project_path)

        # Формируем сообщение в зависимости от задачи
        if prompt_type == "explain":
            user_message = f"Пожалуйста, изучи этот код на Python и объясни мне его логику:\n\n```python\n{code}\n```"
        elif prompt_type == "fix":
            user_message = (
                f"Мой код упал с ошибкой из консоли:\n```text\n{context}\n```\n\n"
                f"Вот сам проблемный код:\n```python\n{code}\n```"
            )
        else: # Масштабная правка или вопрос в чат
            user_message = f"Запрос оператора: {context}\n\nТекущий файл в редакторе:\n```python\n{code}\n```"

        # Соединяем глобальный контекст архитектуры и запрос пользователя
        full_user_message = f"{project_context}\n\nЗАДАЧА:\n{user_message}"

        try:
            # Создаем запрос через официальный метод completions.create
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": full_user_message}
                ],
                temperature=0.3
            )
            
            # --- УНИВЕРСАЛЬНОЕ ИЗВЛЕЧЕНИЕ ТЕКСТА ---
            if hasattr(response, 'choices') and len(response.choices) > 0:
                choice = response.choices[0]
                # Проверяем, объект это или словарь/список
                if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                    return choice.message.content
                elif isinstance(choice, dict) and 'message' in choice:
                    return choice['message'].get('content', '')
                elif hasattr(choice, 'get'):
                    return choice.get('message', {}).get('content', '')
            
            return str(response)

        except Exception as e:
            return f"❌ [Ошибка ИИ]: Не удалось получить ответ. Причина: {str(e)}"
