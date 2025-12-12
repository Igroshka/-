# name: TG Forwarder
# version: 1.0.0
# developer: Maxli User
# id: tg_forwarder
# min-maxli: 35

import requests
import io
from core.config import register_module_settings, get_module_setting, set_module_setting

# Константы Telegram API (из вашего запроса)
TG_BOT_TOKEN = "7973325359:AAFTGBJ7y-B4Mh3egbKoqCOHzIWu0Hb3dMk"
TG_TARGET_CHAT = "-1003155878849"
TG_API_URL = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/"

async def register(api):
    """Регистрация команд, настроек и вотчеров."""
    
    # 1. Регистрируем настройки (source_chat_id)
    register_module_settings("tg_forwarder", {
        "source_chat_id": {
            "default": 0,
            "description": "ID чата, из которого пересылать сообщения"
        },
        "enabled": {
            "default": True,
            "description": "Включить/выключить пересылку"
        }
    })

    # 2. Регистрируем команды управления
    api.register_command("tgsrc", set_source_command)
    api.register_command("tgstate", toggle_state_command)
    
    # 3. Регистрируем вотчер для слежки за сообщениями
    api.register_watcher(message_watcher)

async def set_source_command(api, message, args):
    """Устанавливает текущий чат как источник для пересылки."""
    chat_id = await api.get_chat_id_for_message(message)
    set_module_setting("tg_forwarder", "source_chat_id", chat_id)
    await api.edit(message, f"✅ **Источник установлен:** `{chat_id}`", markdown=True)

async def toggle_state_command(api, message, args):
    """Включает или выключает пересылку."""
    current = get_module_setting("tg_forwarder", "enabled", True)
    new_state = not current
    set_module_setting("tg_forwarder", "enabled", new_state)
    status = "включена" if new_state else "выключена"
    await api.edit(message, f"🔄 Пересылка **{status}**.", markdown=True)

async def message_watcher(api, message):
    """Следит за сообщениями и отправляет их в Telegram."""
    
    # Проверка: включен ли модуль
    if not get_module_setting("tg_forwarder", "enabled", True):
        return

    # Получаем ID чата сообщения
    msg_chat_id = getattr(message, 'chat_id', None)
    if not msg_chat_id:
        msg_chat_id = await api.get_chat_id_for_message(message)

    # Проверка: совпадает ли чат с настроенным
    source_chat = get_module_setting("tg_forwarder", "source_chat_id", 0)
    
    # Приводим к строке для надежного сравнения
    if str(msg_chat_id) != str(source_chat):
        return

    # Извлекаем текст и отправителя
    sender_name = api.get_sender_name(message)
    text = getattr(message, 'text', '') or getattr(message, 'caption', '')
    
    # Формируем подпись для Telegram
    caption_prefix = f"👤 **{sender_name}**:\n"
    final_caption = caption_prefix + text if text else caption_prefix

    try:
        # Если есть вложения (медиа, файлы)
        if hasattr(message, 'attaches') and message.attaches:
            for attach in message.attaches:
                # Получаем прямой URL файла через API Maxli
                file_url = await api.get_file_url(
                    file_id=attach.file_id,
                    token=attach.token,
                    message_id=message.id,
                    chat_id=msg_chat_id
                )

                if not file_url:
                    continue

                # Скачиваем файл в память (buffer)
                file_content = requests.get(file_url).content
                file_buffer = io.BytesIO(file_content)
                file_buffer.name = getattr(attach, 'name', 'file')

                # Определяем тип медиа и метод API
                mime = getattr(attach, 'mime_type', '').lower()
                method = "sendDocument" # Default
                files = {'document': file_buffer}
                data = {'chat_id': TG_TARGET_CHAT, 'caption': final_caption, 'parse_mode': 'Markdown'}

                if 'image' in mime:
                    method = "sendPhoto"
                    files = {'photo': file_buffer}
                elif 'video' in mime:
                    method = "sendVideo"
                    files = {'video': file_buffer}
                elif 'audio' in mime or 'mpeg' in mime:
                    method = "sendAudio"
                    files = {'audio': file_buffer}
                elif 'voice' in mime or 'ogg' in mime:
                    method = "sendVoice"
                    files = {'voice': file_buffer}
                elif 'sticker' in mime or 'webp' in mime:
                    method = "sendSticker"
                    files = {'sticker': file_buffer}
                    # Стикеры не поддерживают caption, отправляем текст отдельно
                    if text:
                        requests.post(TG_API_URL + "sendMessage", data={'chat_id': TG_TARGET_CHAT, 'text': final_caption, 'parse_mode': 'Markdown'})
                    del data['caption']

                # Отправляем запрос в Telegram
                requests.post(TG_API_URL + method, data=data, files=files)
                
                # Сбрасываем подпись после первого вложения, чтобы не дублировать
                final_caption = "" 

        # Если только текст (без вложений)
        elif text:
            requests.post(TG_API_URL + "sendMessage", data={
                'chat_id': TG_TARGET_CHAT,
                'text': final_caption,
                'parse_mode': 'Markdown'
            })

    except Exception as e:
        # Логируем ошибку в буфер Maxli, но не крашим модуль
        api.LOG_BUFFER.append(f"[TG Forwarder] Error: {e}")
