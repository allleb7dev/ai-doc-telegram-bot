import base64
import json
import logging
import os
import tempfile

from google.oauth2 import service_account
from googleapiclient.discovery import build
from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import ChatOpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")


llm = ChatOpenAI(
    base_url="https://api.deepseek.com/v1",
    api_key=DEEPSEEK_API_KEY,
    openai_api_key=DEEPSEEK_API_KEY,
    model="deepseek-chat",
    temperature=0,
    max_tokens=1000,
)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(f"Environment variable {name} is required")
    return value


def get_google_creds():
    b64_str = require_env("GOOGLE_CREDENTIALS_B64")

    try:
        creds_json = base64.b64decode(b64_str).decode("utf-8")
        creds_dict = json.loads(creds_json)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Invalid GOOGLE_CREDENTIALS_B64 value") from exc

    return service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )


def analyze_document(text: str) -> dict:
    prompt = f"""Проанализируй документ и извлеки:
- Тип документа
- Имя человека (если есть)
- Ключевые факты: должность, город, дата, организация
- Краткое резюме в 1-2 предложениях

Верни только валидный JSON без markdown-обертки.

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

Текст документа:
{text}
"""
    response = llm.invoke(prompt).content.strip()
    if response.startswith("```json"):
        response = response[7:]
    if response.endswith("```"):
        response = response[:-3]
    return json.loads(response.strip())


def write_to_sheet(data: dict, sheet_id: str) -> None:
    creds = get_google_creds()
    service = build("sheets", "v4", credentials=creds)
    facts = data.get("факты", {})
    row = [
        data.get("файл", ""),
        data.get("тип", ""),
        data.get("имя", ""),
        facts.get("должность", ""),
        facts.get("город", ""),
        facts.get("дата", ""),
        facts.get("организация", ""),
        data.get("резюме", ""),
    ]
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="A:A",
        valueInputOption="RAW",
        body={"values": [row]},
    ).execute()


def format_response(result: dict) -> str:
    facts = result.get("факты", {})
    return (
        f"Тип: {result.get('тип', '-')}\n"
        f"Имя: {result.get('имя', '-')}\n"
        f"Должность: {facts.get('должность', '-')}\n"
        f"Город: {facts.get('город', '-')}\n"
        f"Дата: {facts.get('дата', '-')}\n"
        f"Организация: {facts.get('организация', '-')}\n\n"
        f"Резюме: {result.get('резюме', '-')}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if update.message:
        await update.message.reply_text(
            "Привет. Отправь PDF-файл, и я проанализирую его содержимое.\n"
            "Результат будет сохранен в Google Sheets."
        )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.document:
        return

    document = update.message.document
    if document.mime_type != "application/pdf":
        await update.message.reply_text("Пожалуйста, отправь PDF-файл.")
        return

    await update.message.reply_text("Получаю файл...")
    tmp_path = None

    try:
        tg_file = await context.bot.get_file(document.file_id)
        file_bytes = await tg_file.download_as_bytearray()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        loader = PyPDFLoader(tmp_path)
        pages = loader.load()
        full_text = "\n".join(page.page_content for page in pages)

        await update.message.reply_text("Анализирую документ...")
        result = analyze_document(full_text)

        await update.message.reply_text(format_response(result))

        result["файл"] = document.file_name or "document.pdf"
        write_to_sheet(result, require_env("SPREADSHEET_ID"))
        await update.message.reply_text("Результат сохранен в Google Sheets.")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Document processing failed")
        await update.message.reply_text(f"Ошибка: {exc}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def main() -> None:
    require_env("TELEGRAM_BOT_TOKEN")
    require_env("DEEPSEEK_API_KEY")
    require_env("SPREADSHEET_ID")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.run_polling()


if __name__ == "__main__":
    main()
