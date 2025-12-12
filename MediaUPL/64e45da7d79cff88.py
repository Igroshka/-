# name: TG Forwarder v5 (Debug)
# version: 5.0.0
# developer: Maxli User
# id: tg_forwarder
# min-maxli: 35
# dependencies: aiohttp

import aiohttp
import json
import os
import asyncio
import sys

# --- КОНФИГУРАЦИЯ ---
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
        json.dump(config, f, ensure_ascii=False, indent=4)

# --- TELEGRAM ---
TG_BOT_TOKEN = "7973325359:AAFTGBJ7y-B4Mh3egbKoqCOHzIWu0Hb3dMk"
TG_TARGET_CHAT = "-1003155878849"
TG_API_URL = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/"

async def register(api):
    api.register_command("tgsrc", set_source_command)   # Установить этот чат
    api.register_command("tgstate", toggle_state_command) # Вкл/Выкл пересылку
    api.register_command("tgdebug", toggle_debug_command) # Вкл/Выкл режим отладки
    api.register_command("tgid", show_id_command)       # Показать ID текущего чата
    api.register_watcher(message_watcher)

# --- КОМАНДЫ ---

async def show_id_command(api, message, args):
    """Показывает ID чата, в котором написана команда."""
    chat_id = await api.get_chat_id_for_message(message)
    await api.edit(message, f"🆔 **ID этого чата:** `{chat_id}`", markdown=True)

async def set_source_command(api, message, args):
    """Автоматически запоминает ID чата."""
    config = load_config()
    chat_id = await api.get_chat_id_for_message(message)
    
    config["source_chat_id"] = chat_id
    save_config(config)
    
    await api.edit(message, f"✅ **Источник установлен!**\nСлежу за чатом: `{chat_id}`", markdown=True)

async def toggle_debug_command(api, message, args):
    """Включает режим отладки в консоль."""
    config = load_config()
    new_state = not config.get("debug", False)
    config["debug"] = new_state
    save_config(config)
    
    state = "ВКЛЮЧЕН" if new_state else "выключен"
    await api.edit(message, f"🐞 Debug режим **{state}**.\nСмотрите консоль/логи при входящих сообщениях.", markdown=True)

async def toggle_state_command(api, message, args):
    config = load_config()
    new_state = not config.get("enabled", True)
    config["enabled"] = new_state
    save_config(config)
    status = "включена" if new_state else "выключена"
    await api.edit(message, f"🔄 Пересылка **{status}**.", markdown=True)

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

async def message_watcher(api, message):
    config = load_config()
    
    # 1. Получаем реальный ID сообщения
    msg_chat_id = getattr(message, 'chat_id', None)
    if not msg_chat_id:
        msg_chat_id = await api.get_chat_id_for_message(message)

    # DEBUG: Пишем в консоль каждое входящее сообщение, если включена отладка
    if config.get("debug", False):
        sender = api.get_sender_name(message)
        print(f"\n[TG DEBUG] New Message | ChatID: {msg_chat_id} | From: {sender}")
        print(f"[TG DEBUG] Expected Source ID: {config.get('source_chat_id')}")

    # Проверка включения
    if not config.get("enabled", True):
        return

    # Сравнение ID
    source_chat = config.get("source_chat_id", 0)
    if str(msg_chat_id) != str(source_chat):
        return
    
    if config.get("debug", False):
        print("[TG DEBUG] -> MATCH! Starting forward process...")

    # --- Сборка контента ---
    sender_name = api.get_sender_name(message)
    text = getattr(message, 'text', '') or getattr(message, 'caption', '')
    
    caption_prefix = f"👤 **{sender_name}**:\n"
    final_caption = caption_prefix + text if text else caption_prefix

    try:
        # ВЛОЖЕНИЯ
        if hasattr(message, 'attaches') and message.attaches:
            async with aiohttp.ClientSession() as session:
                for attach in message.attaches:
                    file_url = await api.get_file_url(file_id=attach.file_id, token=attach.token, message_id=message.id, chat_id=msg_chat_id)
                    if not file_url: continue

                    if config.get("debug", False): print(f"[TG DEBUG] Downloading file: {file_url[:50]}...")

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

                    res = await send_to_telegram(method, params, file_field=file_key, file_data=file_content, filename=filename, mime_type=mime)
                    if config.get("debug", False): print(f"[TG DEBUG] Send Result: {res}")
                    
                    final_caption = "" 

        # ТЕКСТ
        elif text:
            await send_to_telegram("sendMessage", {'chat_id': TG_TARGET_CHAT, 'text': final_caption, 'parse_mode': 'Markdown'})
            if config.get("debug", False): print("[TG DEBUG] Text sent.")

    except Exception as e:
        err = f"[TG Forwarder] Error: {e}"
        api.LOG_BUFFER.append(err)
        if config.get("debug", False): print(err)
