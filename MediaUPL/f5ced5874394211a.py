# name: TG Forwarder Stable
# version: 4.0.0
# developer: Maxli User
# id: tg_forwarder
# min-maxli: 35
# dependencies: aiohttp

import aiohttp
import json
import os
import asyncio

# --- CONFIGURATION MANAGER ---
CONFIG_FILE = "tg_forwarder_config.json"

def load_config():
    """Загрузка настроек из локального файла."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"source_chat_id": 0, "enabled": True}

def save_config(config):
    """Сохранение настроек в файл."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f)

# --- TELEGRAM CONSTANTS ---
TG_BOT_TOKEN = "7973325359:AAFTGBJ7y-B4Mh3egbKoqCOHzIWu0Hb3dMk"
TG_TARGET_CHAT = "-1003155878849"
TG_API_URL = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/"

# --- MODULE COMMANDS ---

async def register(api):
    """Регистрация команд."""
    # Пытаемся зарегистрировать настройки для красоты (если поддерживается), но не падаем при ошибке
    try:
        from core.config import register_module_settings
        register_module_settings("tg_forwarder", {
            "source_chat_id": {"default": 0, "description": "ID чата источника"},
            "enabled": {"default": True, "description": "Включить пересылку"}
        })
    except ImportError:
        pass

    api.register_command("tgsrc", set_source_command)
    api.register_command("tgstate", toggle_state_command)
    api.register_watcher(message_watcher)

async def set_source_command(api, message, args):
    """Установка текущего чата как источника."""
    config = load_config()
    chat_id = await api.get_chat_id_for_message(message)
    
    config["source_chat_id"] = chat_id
    save_config(config)
    
    await api.edit(message, f"✅ **Источник установлен:** `{chat_id}`", markdown=True)

async def toggle_state_command(api, message, args):
    """Включение/выключение пересылки."""
    config = load_config()
    new_state = not config.get("enabled", True)
    
    config["enabled"] = new_state
    save_config(config)
    
    status = "включена" if new_state else "выключена"
    await api.edit(message, f"🔄 Пересылка **{status}**.", markdown=True)

async def send_to_telegram(method, data, file_field=None, file_data=None, filename=None, mime_type=None):
    """Асинхронная отправка запроса в Telegram API."""
    async with aiohttp.ClientSession() as session:
        url = TG_API_URL + method
        
        try:
            if file_data:
                form = aiohttp.FormData()
                for key, value in data.items():
                    form.add_field(key, str(value))
                
                if file_field:
                    form.add_field(
                        file_field,
                        file_data,
                        filename=filename or "file",
                        content_type=mime_type or "application/octet-stream"
                    )
                
                async with session.post(url, data=form) as resp:
                    return await resp.json()
            else:
                async with session.post(url, json=data) as resp:
                    return await resp.json()
        except Exception as e:
            return {"error": str(e)}

async def message_watcher(api, message):
    """Watcher для перехвата сообщений."""
    config = load_config()
    
    if not config.get("enabled", True):
        return

    # Получаем ID чата
    msg_chat_id = getattr(message, 'chat_id', None)
    if not msg_chat_id:
        msg_chat_id = await api.get_chat_id_for_message(message)

    source_chat = config.get("source_chat_id", 0)
    
    # Сравнение ID (строгое приведение к строке)
    if str(msg_chat_id) != str(source_chat):
        return

    sender_name = api.get_sender_name(message)
    text = getattr(message, 'text', '') or getattr(message, 'caption', '')
    
    caption_prefix = f"👤 **{sender_name}**:\n"
    final_caption = caption_prefix + text if text else caption_prefix

    try:
        # 1. Обработка ВЛОЖЕНИЙ (Картинки, видео, файлы, голосовые)
        if hasattr(message, 'attaches') and message.attaches:
            async with aiohttp.ClientSession() as session:
                for attach in message.attaches:
                    # Получаем прямую ссылку через API Maxli
                    file_url = await api.get_file_url(
                        file_id=attach.file_id, token=attach.token,
                        message_id=message.id, chat_id=msg_chat_id
                    )
                    
                    if not file_url: continue

                    # Скачиваем файл в память
                    async with session.get(file_url) as resp:
                        if resp.status != 200: continue
                        file_content = await resp.read()

                    # Определяем тип контента
                    mime = getattr(attach, 'mime_type', '').lower()
                    filename = getattr(attach, 'name', 'file')
                    
                    method = "sendDocument"
                    file_key = 'document'
                    
                    if 'image' in mime: method, file_key = "sendPhoto", 'photo'
                    elif 'video' in mime: method, file_key = "sendVideo", 'video'
                    elif 'audio' in mime or 'mpeg' in mime: method, file_key = "sendAudio", 'audio'
                    elif 'voice' in mime or 'ogg' in mime: method, file_key = "sendVoice", 'voice'
                    elif 'sticker' in mime: method, file_key = "sendSticker", 'sticker'

                    params = {'chat_id': TG_TARGET_CHAT, 'parse_mode': 'Markdown'}

                    # Стикеры не поддерживают подписи, текст шлем отдельно
                    if method != "sendSticker":
                        params['caption'] = final_caption
                    elif text:
                        await send_to_telegram("sendMessage", {
                            'chat_id': TG_TARGET_CHAT,
                            'text': final_caption,
                            'parse_mode': 'Markdown'
                        })

                    # Отправляем файл в ТГ
                    await send_to_telegram(
                        method, params, 
                        file_field=file_key, file_data=file_content, 
                        filename=filename, mime_type=mime
                    )
                    
                    # Очищаем подпись, чтобы она не дублировалась на каждом фото в альбоме
                    final_caption = "" 

        # 2. Обработка ПРОСТОГО ТЕКСТА
        elif text:
            await send_to_telegram("sendMessage", {
                'chat_id': TG_TARGET_CHAT,
                'text': final_caption,
                'parse_mode': 'Markdown'
            })

    except Exception as e:
        # Логирование ошибок в буфер Maxli
        api.LOG_BUFFER.append(f"[TG Forwarder] Error: {e}")
