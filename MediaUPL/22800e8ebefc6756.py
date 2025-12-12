# name: TG Forwarder Native
# version: 2.0.0
# developer: Maxli User
# id: tg_forwarder
# min-maxli: 35

import urllib.request
import urllib.parse
import json
import uuid
import io
import mimetypes
from core.config import register_module_settings, get_module_setting, set_module_setting

# Константы Telegram
TG_BOT_TOKEN = "7973325359:AAFTGBJ7y-B4Mh3egbKoqCOHzIWu0Hb3dMk"
TG_TARGET_CHAT = "-1003155878849"
TG_API_URL = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/"

class MultipartForm:
    """Helper для создания multipart/form-data запросов без requests."""
    def __init__(self):
        self.boundary = uuid.uuid4().hex
        self.parts = []

    def add_field(self, name, value):
        self.parts.append(f'--{self.boundary}'.encode())
        self.parts.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        self.parts.append(b'')
        self.parts.append(str(value).encode())

    def add_file(self, name, filename, content, mimetype=None):
        if mimetype is None:
            mimetype = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        
        self.parts.append(f'--{self.boundary}'.encode())
        self.parts.append(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode())
        self.parts.append(f'Content-Type: {mimetype}'.encode())
        self.parts.append(b'')
        self.parts.append(content)

    def get_body(self):
        final_body = b'\r\n'.join(self.parts) + f'\r\n--{self.boundary}--\r\n'.encode()
        return final_body, f"multipart/form-data; boundary={self.boundary}"

def send_telegram_request(method, data=None, files=None):
    """Отправка запроса в Telegram через urllib."""
    url = TG_API_URL + method
    
    if files:
        # Если есть файлы, формируем multipart запрос
        form = MultipartForm()
        for key, value in data.items():
            form.add_field(key, value)
        
        # files expected as: {'param_name': (filename, bytes, mime)}
        for key, file_info in files.items():
            filename, content, mime = file_info
            form.add_file(key, filename, content, mime)
            
        body, content_type = form.get_body()
        req = urllib.request.Request(url, data=body)
        req.add_header('Content-Type', content_type)
    else:
        # Обычный JSON/Form запрос
        encoded_data = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(url, data=encoded_data)
        
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"[TG Forwarder] Request Error: {e}")
        return None

async def register(api):
    register_module_settings("tg_forwarder", {
        "source_chat_id": {"default": 0, "description": "ID чата источник"},
        "enabled": {"default": True, "description": "Включить пересылку"}
    })
    api.register_command("tgsrc", set_source_command)
    api.register_command("tgstate", toggle_state_command)
    api.register_watcher(message_watcher)

async def set_source_command(api, message, args):
    chat_id = await api.get_chat_id_for_message(message)
    set_module_setting("tg_forwarder", "source_chat_id", chat_id)
    await api.edit(message, f"✅ **Источник установлен:** `{chat_id}`", markdown=True)

async def toggle_state_command(api, message, args):
    current = get_module_setting("tg_forwarder", "enabled", True)
    set_module_setting("tg_forwarder", "enabled", not current)
    status = "включена" if not current else "выключена"
    await api.edit(message, f"🔄 Пересылка **{status}**.", markdown=True)

async def message_watcher(api, message):
    if not get_module_setting("tg_forwarder", "enabled", True):
        return

    msg_chat_id = getattr(message, 'chat_id', None)
    if not msg_chat_id:
        msg_chat_id = await api.get_chat_id_for_message(message)

    source_chat = get_module_setting("tg_forwarder", "source_chat_id", 0)
    if str(msg_chat_id) != str(source_chat):
        return

    sender_name = api.get_sender_name(message)
    text = getattr(message, 'text', '') or getattr(message, 'caption', '')
    
    caption_prefix = f"👤 **{sender_name}**:\n"
    final_caption = caption_prefix + text if text else caption_prefix

    try:
        if hasattr(message, 'attaches') and message.attaches:
            for attach in message.attaches:
                file_url = await api.get_file_url(
                    file_id=attach.file_id, token=attach.token,
                    message_id=message.id, chat_id=msg_chat_id
                )
                if not file_url: continue

                # Скачиваем файл через urllib
                with urllib.request.urlopen(file_url) as f:
                    file_content = f.read()

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
                elif 'sticker' in mime:
                    method, file_key = "sendSticker", 'sticker'

                data = {'chat_id': TG_TARGET_CHAT, 'parse_mode': 'Markdown'}
                
                # Стикеры не поддерживают caption
                if method != "sendSticker":
                    data['caption'] = final_caption
                elif text:
                    # Отправляем текст отдельно для стикеров
                    send_telegram_request("sendMessage", {'chat_id': TG_TARGET_CHAT, 'text': final_caption, 'parse_mode': 'Markdown'})

                files = {file_key: (filename, file_content, mime)}
                
                # Отправляем в Telegram
                send_telegram_request(method, data, files)
                final_caption = "" # Очищаем caption для следующих вложений

        elif text:
            send_telegram_request("sendMessage", {
                'chat_id': TG_TARGET_CHAT,
                'text': final_caption,
                'parse_mode': 'Markdown'
            })

    except Exception as e:
        api.LOG_BUFFER.append(f"[TG Forwarder] Error: {e}")
