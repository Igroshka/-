# name: TG Forwarder Async
# version: 3.0.0
# developer: Maxli User
# id: tg_forwarder
# min-maxli: 35
# dependencies: aiohttp

import aiohttp
import io
from core.config import register_module_settings, get_module_setting, set_module_setting

# Настройки Telegram
TG_BOT_TOKEN = "7973325359:AAFTGBJ7y-B4Mh3egbKoqCOHzIWu0Hb3dMk"
TG_TARGET_CHAT = "-1003155878849"
TG_API_URL = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/"

async def register(api):
    register_module_settings("tg_forwarder", {
        "source_chat_id": {"default": 0, "description": "ID чата источника"},
        "enabled": {"default": True, "description": "Включить пересылку"}
    })
    api.register_command("tgsrc", set_source_command)
    api.register_command("tgstate", toggle_state_command)
    api.register_watcher(message_watcher)

async def set_source_command(api, message, args):
    """Установка текущего чата как источника."""
    chat_id = await api.get_chat_id_for_message(message)
    set_module_setting("tg_forwarder", "source_chat_id", chat_id)
    await api.edit(message, f"✅ **Источник установлен:** `{chat_id}`", markdown=True)

async def toggle_state_command(api, message, args):
    """Включение/выключение."""
    current = get_module_setting("tg_forwarder", "enabled", True)
    set_module_setting("tg_forwarder", "enabled", not current)
    status = "включена" if not current else "выключена"
    await api.edit(message, f"🔄 Пересылка **{status}**.", markdown=True)

async def send_to_telegram(method, data, file_field=None, file_data=None, filename=None, mime_type=None):
    """Асинхронная отправка запроса в Telegram."""
    async with aiohttp.ClientSession() as session:
        url = TG_API_URL + method
        
        # Если есть файл, используем FormData
        if file_data:
            form = aiohttp.FormData()
            # Добавляем обычные поля
            for key, value in data.items():
                form.add_field(key, str(value))
            
            # Добавляем файл
            if file_field and file_data:
                form.add_field(
                    file_field,
                    file_data,
                    filename=filename,
                    content_type=mime_type
                )
            
            try:
                async with session.post(url, data=form) as resp:
                    return await resp.json()
            except Exception as e:
                return {"error": str(e)}
        
        # Обычный JSON запрос (для текста)
        else:
            try:
                async with session.post(url, json=data) as resp:
                    return await resp.json()
            except Exception as e:
                return {"error": str(e)}

async def message_watcher(api, message):
    if not get_module_setting("tg_forwarder", "enabled", True):
        return

    msg_chat_id = getattr(message, 'chat_id', None)
    if not msg_chat_id:
        msg_chat_id = await api.get_chat_id_for_message(message)

    source_chat = get_module_setting("tg_forwarder", "source_chat_id", 0)
    
    # Приводим к строке для надежности
    if str(msg_chat_id) != str(source_chat):
        return

    sender_name = api.get_sender_name(message)
    text = getattr(message, 'text', '') or getattr(message, 'caption', '')
    
    caption_prefix = f"👤 **{sender_name}**:\n"
    final_caption = caption_prefix + text if text else caption_prefix

    try:
        # 1. Обработка вложений
        if hasattr(message, 'attaches') and message.attaches:
            async with aiohttp.ClientSession() as session:
                for attach in message.attaches:
                    # Получаем URL файла
                    file_url = await api.get_file_url(
                        file_id=attach.file_id, token=attach.token,
                        message_id=message.id, chat_id=msg_chat_id
                    )
                    
                    if not file_url: continue

                    # Асинхронно скачиваем файл
                    async with session.get(file_url) as resp:
                        if resp.status != 200: continue
                        file_content = await resp.read()

                    # Определяем тип
                    mime = getattr(attach, 'mime_type', '').lower()
                    filename = getattr(attach, 'name', 'file')
                    
                    method = "sendDocument"
                    file_key = 'document'
                    
                    if 'image' in mime:
                        method, file_key = "sendPhoto", 'photo'
                    elif 'video' in mime:
                        method, file_key = "sendVideo", 'video'
                    elif 'audio' in mime or 'mpeg' in mime:
                        method, file_key = "sendAudio", 'audio'
                    elif 'voice' in mime or 'ogg' in mime:
                        method, file_key = "sendVoice", 'voice'
                    elif 'sticker' in mime or 'webp' in mime:
                        method, file_key = "sendSticker", 'sticker'

                    params = {
                        'chat_id': TG_TARGET_CHAT,
                        'parse_mode': 'Markdown'
                    }

                    # Логика подписей
                    if method != "sendSticker":
                        params['caption'] = final_caption
                    elif text:
                        # Для стикеров текст отдельно
                        await send_to_telegram("sendMessage", {
                            'chat_id': TG_TARGET_CHAT,
                            'text': final_caption,
                            'parse_mode': 'Markdown'
                        })

                    # Отправляем файл
                    await send_to_telegram(
                        method, 
                        params, 
                        file_field=file_key, 
                        file_data=file_content, 
                        filename=filename, 
                        mime_type=mime
                    )
                    
                    final_caption = "" # Очищаем подпись для следующих файлов

        # 2. Обработка чистого текста
        elif text:
            await send_to_telegram("sendMessage", {
                'chat_id': TG_TARGET_CHAT,
                'text': final_caption,
                'parse_mode': 'Markdown'
            })

    except Exception as e:
        api.LOG_BUFFER.append(f"[TG Forwarder] Async Error: {e}")
