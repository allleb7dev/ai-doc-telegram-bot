import os
import tempfile
import json
import base64
from io import BytesIO

import telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from google.oauth2 import service_account
from googleapiclient.discovery import build
from langchain_openai import ChatOpenAI
from langchain_community.document_loaders import PyPDFLoader

# === НАСТРОЙКИ ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

llm = ChatOpenAI(
    base_url="https://api.deepseek.com/v1",
    api_key=DEEPSEEK_API_KEY,  # ← твой ключ
    model="deepseek-chat",
    temperature=0,
    max_tokens=1000,
    openai_api_key=DEEPSEEK_API_KEY  # ← явно передаём ключ
)


def get_google_creds():
    b64_str = os.getenv("GOOGLE_CREDENTIALS_B64")
    if not b64_str:
        raise EnvironmentError("GOOGLE_CREDENTIALS_B64 не задан!")
    creds_json = base64.b64decode(b64_str).decode("utf-8")
    creds_dict = json.loads(creds_json)
    return service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )


def analyze_document(text: str) -> dict:
    prompt = f"""Проанализируй документ и извлеки:
- Тип документа
- Имя человека (если есть)
- Ключевые факты: должность, город, дата, организация
- Краткое резюме (1–2 предложения)

Верни ТОЛЬКО валидный JSON без ```json.

Формат:
{{
  "тип": "...",
  "имя": "...",
  "факты": {{
    "должность": "...",
    "город": "...",
    "дата": "...",
    "организация": "..."
  }},
  "резюме": "..."
}}

Текст:
{text}

Ответ:"""
    response = llm.invoke(prompt).content.strip()
    if response.startswith("```json"):
        response = response[7:]
    if response.endswith("```"):
        response = response[:-3]
    return json.loads(response.strip())


def write_to_sheet(data: dict, sheet_id: str):  # ← параметр теперь `data`
    try:
        creds = get_google_creds()
        service = build('sheets', 'v4', credentials=creds)
        facts = data.get("факты", {})
        row = [
            data.get("файл", ""),
            data.get("тип", ""),
            data.get("имя", ""),
            facts.get("должность", ""),
            facts.get("город", ""),
            facts.get("дата", ""),
            facts.get("организация", ""),
            data.get("резюме", "")
        ]
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range="Data!A:A",
            valueInputOption="RAW",
            body={"values": [row]}
        ).execute()
    except Exception as e:
        print(f"Ошибка записи в таблицу: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 🧠 Отправь мне PDF-файл, и я его проанализирую.\n"
        "Результат сохраню в Google Таблицу."
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = update.message.document
    if file.mime_type != "application/pdf":
        await update.message.reply_text("Пожалуйста, отправь PDF-файл.")
        return

    await update.message.reply_text("📥 Получаю файл...")

    try:
        # Скачиваем файл
        tg_file = await context.bot.get_file(file.file_id)
        file_bytes = await tg_file.download_as_bytearray()

        # Читаем PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        loader = PyPDFLoader(tmp_path)
        pages = loader.load()
        full_text = "\n".join([p.page_content for p in pages])

        # Анализируем
        await update.message.reply_text("🧠 Анализирую документ...")
        result = analyze_document(full_text)

        # Форматируем ответ
        response = (
            f"✅ **Тип**: {result.get('тип', '-')}\n"
            f"👤 **Имя**: {result.get('имя', '-')}\n"
            f"💼 **Должность**: {result.get('факты', {}).get('должность', '-')}\n"
            f"🏙️ **Город**: {result.get('факты', {}).get('город', '-')}\n"
            f"📅 **Дата**: {result.get('факты', {}).get('дата', '-')}\n"
            f"🏢 **Организация**: {result.get('факты', {}).get('организация', '-')}\n\n"
            f"📝 **Резюме**: {result.get('резюме', '-')}"
        )
        await update.message.reply_text(response, parse_mode="Markdown")

        # Сохраняем в таблицу
        result["файл"] = file.file_name
        write_to_sheet(result, SPREADSHEET_ID)
        await update.message.reply_text("📤 Результат сохранён в Google Таблицу!")

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    finally:
        if 'tmp_path' in locals():
            os.unlink(tmp_path)


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.run_polling()


if __name__ == "__main__":
    main()