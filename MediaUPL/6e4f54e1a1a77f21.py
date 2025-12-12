# name: TG Forwarder Direct
# version: 6.6.6
# developer: Maxli User
# id: tg_forwarder
# min-maxli: 35
# dependencies: aiohttp

import aiohttp
import json
import os
import asyncio
from pymax.filters import filters # Импортируем фильтры для PyMax

# --- КОНФИГУРАЦИЯ ---
CONFIG_FILE = "tg_forwarder_config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"source_chat_id": 0, "enabled": True}

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

# --- TELEGRAM ---
TG_BOT_TOKEN = "7973325359:AAFTGBJ7y-B4Mh3egbKoqCOHzIWu0Hb3dMk"
TG_TARGET_CHAT = "-1003155878849"
TG_API_URL = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/"

async def send_to_telegram(method, data, file_field=None, file_data=None, filename=None, mime_type=None):
    async with aiohttp.ClientSession() as session:
        url = TG_API_URL + method
        try:
            if file_data:
                form = aiohttp.FormData()
                for key, value in data.items():
                    form.add_field(key, str(value))
                if file_field:
                    form.add_field(file_field, file_data, filename=filename or "file", content_type=mime_type or "application/octet-stream")
                async with session.post(url, data=form) as resp:
                    return await resp.json()
            else:
                async with session.post(url, json=data) as resp:
                    return await resp.json()
        except Exception as e:
            return {"error": str(e)}

# --- LOGIC ---

# Глобальная переменная для API, чтобы использовать в декораторе
_api_instance = None

async def direct_message_handler(message):
    """
    Прямой обработчик PyMax.
    Срабатывает на ЛЮБОЕ входящее событие сообщения.
    """
    global _api_instance
    if not _api_instance: return # API еще не готов

    config = load_config()
    if not config.get("enabled", True): return

    # Пробуем достать ID чата всеми способами
    msg_chat_id = getattr(message, 'chat_id', None) or getattr(message, 'peer_id', None)
    
    # Сверяем с сохраненным
    source_chat = config.get("source_chat_id", 0)
    
    # Если ID не совпадает - выходим сразу
    if str(msg_chat_id) != str(source_chat):
        return

    # --- Обработка ---
    # Пытаемся получить имя отправителя (безопасно)
    try:
        if getattr(message, 'sender', None):
             # Пробуем через кэш API
            sender_name = _api_instance.get_sender_name(message)
        else:
            sender_name = "Unknown"
    except:
        sender_name = "User"

    text = getattr(message, 'text', '') or getattr(message, 'caption', '')
    
    caption_prefix = f"👤 **{sender_name}**:\n"
    final_caption = caption_prefix + text if text else caption_prefix

    try:
        # ВЛОЖЕНИЯ
        if hasattr(message, 'attaches') and message.attaches:
            async with aiohttp.ClientSession() as session:
                for attach in message.attaches:
                    # Используем метод API для получения ссылки
                    file_url = await _api_instance.get_file_url(
                        file_id=attach.file_id, 
                        token=attach.token, 
                        message_id=message.id, 
                        chat_id=msg_chat_id
                    )
                    
                    if not file_url: continue

                    async with session.get(file_url) as resp:
                        if resp.status != 200: continue
                        file_content = await resp.read()

                    mime = getattr(attach, 'mime_type', '').lower()
                    filename = getattr(attach, 'name', 'file')
                    
                    method, file_key = "sendDocument", 'document'
                    if 'image' in mime: method, file_key = "sendPhoto", 'photo'
                    elif 'video' in mime: method, file_key = "sendVideo", 'video'
                    elif 'audio' in mime or 'mpeg' in mime: method, file_key = "sendAudio", 'audio'
                    elif 'voice' in mime or 'ogg' in mime: method, file_key = "sendVoice", 'voice'
                    elif 'sticker' in mime: method, file_key = "sendSticker", 'sticker'

                    params = {'chat_id': TG_TARGET_CHAT, 'parse_mode': 'Markdown'}
                    if method != "sendSticker": params['caption'] = final_caption
                    elif text: await send_to_telegram("sendMessage", {'chat_id': TG_TARGET_CHAT, 'text': final_caption, 'parse_mode': 'Markdown'})

                    await send_to_telegram(method, params, file_field=file_key, file_data=file_content, filename=filename, mime_type=mime)
                    final_caption = "" 

        # ТЕКСТ
        elif text:
            await send_to_telegram("sendMessage", {'chat_id': TG_TARGET_CHAT, 'text': final_caption, 'parse_mode': 'Markdown'})

    except Exception as e:
        print(f"[TG Forwarder] Error: {e}")


# --- РЕГИСТРАЦИЯ ---

async def register(api):
    global _api_instance
    _api_instance = api
    
    api.register_command("tgsrc", set_source_command)
    api.register_command("tgstate", toggle_state_command)

    # ВМЕСТО api.register_watcher МЫ ВЕШАЕМ ХУК НА КЛИЕНТА
    # Это работает на уровень ниже, чем вотчеры Maxli
    @api.client.on_message()
    async def _wrapper(message):
        await direct_message_handler(message)

    print("[TG Forwarder] Direct hook registered!")

async def set_source_command(api, message, args):
    config = load_config()
    chat_id = await api.get_chat_id_for_message(message)
    config["source_chat_id"] = chat_id
    save_config(config)
    await api.edit(message, f"✅ **Источник установлен:** `{chat_id}`", markdown=True)

async def toggle_state_command(api, message, args):
    config = load_config()
    config["enabled"] = not config.get("enabled", True)
    save_config(config)
    await api.edit(message, f"🔄 Состояние изменено", markdown=True)
