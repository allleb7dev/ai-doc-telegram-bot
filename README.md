# AI Document Telegram Bot

Telegram bot that accepts PDF documents, extracts text, analyzes the content with DeepSeek, and writes structured results to Google Sheets.

## What It Does

- accepts PDF files from Telegram users;
- extracts document text;
- sends the extracted content to DeepSeek for structured analysis;
- returns a concise result to the user in Telegram;
- appends parsed data to Google Sheets.

## Use Case

This project is a practical example of a document-processing assistant for administrative workflows, lead intake, CV parsing, and internal document classification.

## Tech Stack

- Python
- python-telegram-bot
- DeepSeek API via LangChain
- Google Sheets API
- PyPDF

## Environment Variables

Set these variables locally or in your deployment platform:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
DEEPSEEK_API_KEY=your_deepseek_api_key
SPREADSHEET_ID=your_google_sheet_id
GOOGLE_CREDENTIALS_B64=base64_service_account_json
```

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python bot.py
```

## Notes

- Secrets should be loaded from environment variables and never committed.
- This repository is intended as a portfolio example of a real-world Telegram + LLM + Google Sheets workflow.
