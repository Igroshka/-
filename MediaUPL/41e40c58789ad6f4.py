# name: Debug Chat
# version: 1.0.0
# developer: Maxli User
# id: debug_chat
# min-maxli: 35

"""
Отладочный модуль для получения информации о текущем чате.
"""

async def chat_command(api, message, args):
    """Отправляет известную информацию о текущем чате."""
    try:
        # Получаем ID чата
        chat_id = await api.get_chat_id_for_message(message)
        
        # Формируем базовый ответ
        info_text = (
            f"🔍 **Debug Chat Info**\n\n"
            f"🆔 **Chat ID**: `{chat_id}`\n"
        )

        # Пытаемся получить расширенную информацию через PyMax клиент
        try:
            chat_info = await api.client.get_chat(chat_id)
            
            if chat_info:
                # Добавляем название, если есть
                title = getattr(chat_info, 'title', None)
                if title:
                    info_text += f"📛 **Title**: `{title}`\n"
                
                # Добавляем тип чата, если есть
                chat_type = getattr(chat_info, 'type', None)
                if chat_type:
                    info_text += f"📂 **Type**: `{chat_type}`\n"
                    
                # Добавляем описание, если есть
                description = getattr(chat_info, 'description', None)
                if description:
                    info_text += f"📝 **Desc**: {description[:50]}...\n"

        except Exception as e:
            # Если не удалось получить детали, добавляем ошибку в вывод, но не ломаем основной ID
            info_text += f"\n⚠️ **Fetch Error**: {e}"

        # Отправляем результат (редактируем сообщение команды)
        await api.edit(message, info_text, markdown=True)

    except Exception as e:
        # Глобальная защита от ошибок
        await api.edit(message, f"❌ **Error**: {e}", markdown=True)

async def register(api):
    api.register_command("chat", chat_command)
