# name: TG Forwarder V8
# version: 8.0.0
# developer: Maxli User
# id: tg_forwarder
# min-maxli: 35
# dependencies: aiohttp

import aiohttp
import json
import os
import asyncio

# --- CONFIG ---
CONFIG_FILE = "tg_forwarder_config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"source_chat_id": 0, "enabled": True, "debug": False}

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

def log(api, text):
    """Пишет в буфер логов бота."""
    try:
        if hasattr(api, 'LOG_BUFFER'):
            api.LOG_BUFFER.append(f"[TG Fwd] {text}")
        else:
            print(f"[TG Fwd] {text}")
    except:
        pass

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

# --- HANDLER ---

async def message_watcher(api, message):
    try:
        config = load_config()
        
        # Получаем ID чата ЛЮБЫМИ способами
        msg_chat_id = getattr(message, 'chat_id', None)
        if msg_chat_id is None:
            msg_chat_id = getattr(message, 'peer_id', None)
        if msg_chat_id is None:
            # Пытаемся получить через API, но осторожно
            try:
                msg_chat_id = await api.get_chat_id_for_message(message)
            except:
                pass

        # DEBUG: Если включен, пишем в лог бота информацию о каждом сообщении
        if config.get("debug", False):
            log(api, f"Msg in: {msg_chat_id} | Target: {config.get('source_chat_id')}")

        if not config.get("enabled", True):
            return

        # Сравниваем как строки
        source_chat = str(config.get("source_chat_id", 0))
        current_chat = str(msg_chat_id)

        if current_chat != source_chat:
            return

        # --- СБОР ДАННЫХ ---
        sender_name = "User"
        try:
            sender_name = api.get_sender_name(message)
        except:
            pass

        text = getattr(message, 'text', '') or getattr(message, 'caption', '')
        caption_prefix = f"👤 **{sender_name}**:\n"
        final_caption = caption_prefix + text if text else caption_prefix

        # --- ОТПРАВКА ---
        # 1. Вложения
        if hasattr(message, 'attaches') and message.attaches:
            async with aiohttp.ClientSession() as session:
                for attach in message.attaches:
                    file_url = await api.get_file_url(file_id=attach.file_id, token=attach.token, message_id=message.id, chat_id=msg_chat_id)
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

        # 2. Текст
        elif text:
            await send_to_telegram("sendMessage", {'chat_id': TG_TARGET_CHAT, 'text': final_caption, 'parse_mode': 'Markdown'})

    except Exception as e:
        log(api, f"Error: {e}")

# --- COMMANDS ---

async def register(api):
    api.register_watcher(message_watcher)
    api.register_command("tgsrc", set_source_command)
    api.register_command("tginfo", info_command)
    api.register_command("tgdebug", debug_command)

async def set_source_command(api, message, args):
    """Установить текущий чат как источник."""
    chat_id = await api.get_chat_id_for_message(message)
    config = load_config()
    config["source_chat_id"] = chat_id
    save_config(config)
    await api.edit(message, f"✅ Source Set: `{chat_id}`", markdown=True)

async def info_command(api, message, args):
    """Показывает ID текущего чата."""
    chat_id = await api.get_chat_id_for_message(message)
    await api.edit(message, f"ℹ️ Chat ID: `{chat_id}`", markdown=True)

async def debug_command(api, message, args):
    """Включает логирование в .logs"""
    config = load_config()
    config["debug"] = not config.get("debug", False)
    save_config(config)
    state = "ON" if config["debug"] else "OFF"
    await api.edit(message, f"🐞 Debug: **{state}**\nCheck `.logs` if available.", markdown=True)
