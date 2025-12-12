# name: TG Forwarder Final
# version: 7.0.0
# developer: Maxli User
# id: tg_forwarder
# min-maxli: 35
# dependencies: aiohttp

import aiohttp
import json
import os
import asyncio

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

# --- TELEGRAM API ---
TG_BOT_TOKEN = "7973325359:AAFTGBJ7y-B4Mh3egbKoqCOHzIWu0Hb3dMk"
TG_TARGET_CHAT = "-1003155878849"
TG_API_URL = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/"

async def send_to_telegram(method, data, file_field=None, file_data=None, filename=None, mime_type=None):
    """Асинхронная отправка в Telegram."""
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

# --- ОБРАБОТЧИК СООБЩЕНИЙ ---

async def process_message(api, message):
    """Основная логика пересылки."""
    config = load_config()
    
    # 1. Проверяем, включен ли модуль
    if not config.get("enabled", True):
        return

    # 2. Получаем ID чата
    msg_chat_id = getattr(message, 'chat_id', None)
    # Если chat_id нет (редкий случай в raw events), пробуем peer_id
    if msg_chat_id is None:
        msg_chat_id = getattr(message, 'peer_id', None)

    # 3. Сверяем с целевым чатом
    source_chat = config.get("source_chat_id", 0)
    
    # Строгое сравнение строк (чтобы избежать проблем с типами int/str)
    if str(msg_chat_id) != str(source_chat):
        return

    # 4. Формируем контент
    try:
        sender_name = api.get_sender_name(message)
    except:
        sender_name = "User"

    text = getattr(message, 'text', '') or getattr(message, 'caption', '')
    caption_prefix = f"👤 **{sender_name}**:\n"
    final_caption = caption_prefix + text if text else caption_prefix

    try:
        # A. ОБРАБОТКА ВЛОЖЕНИЙ
        if hasattr(message, 'attaches') and message.attaches:
            async with aiohttp.ClientSession() as session:
                for attach in message.attaches:
                    # Пытаемся получить ссылку
                    file_url = await api.get_file_url(
                        file_id=attach.file_id, 
                        token=attach.token, 
                        message_id=message.id, 
                        chat_id=msg_chat_id
                    )
                    
                    if not file_url: continue

                    # Скачиваем файл
                    async with session.get(file_url) as resp:
                        if resp.status != 200: continue
                        file_content = await resp.read()

                    # Определяем тип
                    mime = getattr(attach, 'mime_type', '').lower()
                    filename = getattr(attach, 'name', 'file')
                    
                    method, file_key = "sendDocument", 'document'
                    if 'image' in mime: method, file_key = "sendPhoto", 'photo'
                    elif 'video' in mime: method, file_key = "sendVideo", 'video'
                    elif 'audio' in mime or 'mpeg' in mime: method, file_key = "sendAudio", 'audio'
                    elif 'voice' in mime or 'ogg' in mime: method, file_key = "sendVoice", 'voice'
                    elif 'sticker' in mime: method, file_key = "sendSticker", 'sticker'

                    params = {'chat_id': TG_TARGET_CHAT, 'parse_mode': 'Markdown'}
                    
                    # Логика подписи
                    if method != "sendSticker":
                        params['caption'] = final_caption
                    elif text:
                        # Текст отдельно для стикеров
                        await send_to_telegram("sendMessage", {
                            'chat_id': TG_TARGET_CHAT, 
                            'text': final_caption, 
                            'parse_mode': 'Markdown'
                        })

                    # Отправка
                    await send_to_telegram(
                        method, params, 
                        file_field=file_key, 
                        file_data=file_content, 
                        filename=filename, 
                        mime_type=mime
                    )
                    
                    final_caption = "" # Очищаем caption для следующих файлов

        # B. ОБРАБОТКА ТЕКСТА (если нет вложений)
        elif text:
            await send_to_telegram("sendMessage", {
                'chat_id': TG_TARGET_CHAT,
                'text': final_caption,
                'parse_mode': 'Markdown'
            })

    except Exception as e:
        print(f"[TG Forwarder] Process Error: {e}")

# --- РЕГИСТРАЦИЯ МОДУЛЯ ---

async def register(api):
    # Регистрируем команды
    api.register_command("tgsrc", set_source_command)
    api.register_command("tgstate", toggle_state_command)

    # РЕГИСТРИРУЕМ ПРЯМОЙ ХУК (БЕЗ ФИЛЬТРОВ)
    # Это перехватит ВСЕ сообщения, а фильтрацию мы сделаем внутри process_message
    @api.client.on_message()
    async def _direct_wrapper(message):
        # Передаем 'api' внутрь, так как декоратор pymax дает только 'message'
        await process_message(api, message)

    print("[TG Forwarder] Hook registered successfully")

async def set_source_command(api, message, args):
    """Запоминает ID чата."""
    config = load_config()
    chat_id = await api.get_chat_id_for_message(message)
    config["source_chat_id"] = chat_id
    save_config(config)
    await api.edit(message, f"✅ **Источник установлен:** `{chat_id}`", markdown=True)

async def toggle_state_command(api, message, args):
    """Вкл/Выкл."""
    config = load_config()
    config["enabled"] = not config.get("enabled", True)
    save_config(config)
    state = "ВКЛЮЧЕНО" if config["enabled"] else "ВЫКЛЮЧЕНО"
    await api.edit(message, f"🔄 Пересылка **{state}**", markdown=True)
