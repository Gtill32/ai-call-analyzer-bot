import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from groq import Groq
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = Groq(api_key=config.GROQ_API_KEY)

PRESETS = {
    "sales": {
        "name": "💼 Продажи / B2B",
        "prompt": """Ты — эксперт по анализу звонков отдела продаж. Проанализируй транскрипцию и выдай структурированный отчёт строго в таком формате:

👥 УЧАСТНИКИ
Определи сколько человек в разговоре и роль каждого (менеджер, клиент, и тд)

📋 КРАТКОЕ СОДЕРЖАНИЕ
2-3 предложения о чём был разговор

📊 НАСТРОЕНИЕ КЛИЕНТА
— В начале: [эмодзи + слово]
— В середине: [эмодзи + слово]  
— В конце: [эмодзи + слово]

😣 БОЛИ И ЗАПРОСЫ КЛИЕНТА
— [боль 1]
— [боль 2]

🎯 КЛЮЧЕВЫЕ ТЕМЫ
[тема1] [тема2] [тема3]

📈 ОЦЕНКА ЗВОНКА
— Работа с возражениями: X/10
— Соблюдение скрипта: X/10
— Вероятность сделки: X%

✅ ДОГОВОРЁННОСТИ / NEXT STEPS
Что решили, какие следующие шаги

🏷 ТЕГИ
#тег1 #тег2 #тег3"""
    },
    "support": {
        "name": "🎧 Поддержка / Саппорт",
        "prompt": """Ты — эксперт по анализу звонков службы поддержки. Проанализируй транскрипцию и выдай структурированный отчёт строго в таком формате:

👥 УЧАСТНИКИ
Определи сколько человек в разговоре и роль каждого

📋 КРАТКОЕ СОДЕРЖАНИЕ
2-3 предложения о чём был разговор

📊 НАСТРОЕНИЕ КЛИЕНТА
— В начале: [эмодзи + слово]
— В середине: [эмодзи + слово]
— В конце: [эмодзи + слово]

🔧 ПРОБЛЕМА КЛИЕНТА
Подробно опиши с чем обратился клиент

✅ РЕШЕНА ЛИ ПРОБЛЕМА
Да / Нет / Частично — и почему

📈 ОЦЕНКА ОПЕРАТОРА
— Вежливость: X/10
— Компетентность: X/10
— Скорость решения: X/10

🏷 ТЕГИ
#тег1 #тег2 #тег3"""
    },
    "conflict": {
        "name": "⚠️ Конфликт / Фрод",
        "prompt": """Ты — эксперт по анализу конфликтных звонков и мошенничества. Проанализируй транскрипцию и выдай структурированный отчёт строго в таком формате:

👥 УЧАСТНИКИ
Определи сколько человек в разговоре и роль каждого

📋 КРАТКОЕ СОДЕРЖАНИЕ
2-3 предложения о чём был разговор

⚠️ ТИП ИНЦИДЕНТА
Конфликт / Мошенничество / Угрозы / Другое

😡 УРОВЕНЬ АГРЕССИИ
Низкий / Средний / Высокий / Критический

🚨 ОПАСНЫЕ МОМЕНТЫ
— [момент 1]
— [момент 2]

📊 НАСТРОЕНИЕ ПО ХОДУ ЗВОНКА
Опиши динамику как менялось настроение

✅ РЕКОМЕНДУЕМЫЕ ДЕЙСТВИЯ
Что нужно сделать после этого звонка

🏷 ТЕГИ
#тег1 #тег2 #тег3"""
    }
}

user_presets = {}


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(PRESETS["sales"]["name"], callback_data="preset_sales")],
        [InlineKeyboardButton(PRESETS["support"]["name"], callback_data="preset_support")],
        [InlineKeyboardButton(PRESETS["conflict"]["name"], callback_data="preset_conflict")],
    ])


def back_to_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Назад в меню", callback_data="go_menu")]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я анализирую звонки с помощью ИИ.\n\n"
        "Сначала выбери тип звонка:",
        reply_markup=main_menu_keyboard()
    )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выбери тип звонка:",
        reply_markup=main_menu_keyboard()
    )


async def go_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "Выбери тип звонка:",
        reply_markup=main_menu_keyboard()
    )


async def preset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    preset_key = query.data.replace("preset_", "")
    user_presets[query.from_user.id] = preset_key
    preset_name = PRESETS[preset_key]["name"]

    await query.edit_message_text(
        f"✅ Выбран пресет: {preset_name}\n\n"
        f"Отправь аудиофайл или голосовое сообщение 🎙",
        reply_markup=back_to_menu_keyboard()
    )


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id not in user_presets:
        await update.message.reply_text(
            "⚠️ Сначала выбери тип звонка:",
            reply_markup=main_menu_keyboard()
        )
        return

    if update.message.voice:
        file = await update.message.voice.get_file()
        file_ext = "ogg"
    elif update.message.audio:
        file = await update.message.audio.get_file()
        file_ext = "mp3"
    elif update.message.document:
        file = await update.message.document.get_file()
        file_ext = update.message.document.file_name.split(".")[-1]
    else:
        await update.message.reply_text("❌ Отправь аудиофайл (mp3, wav, ogg) или голосовое сообщение")
        return

    await update.message.reply_text("⏳ Получил файл, начинаю анализ... Это займёт 20-40 секунд")

    file_path = f"temp_audio.{file_ext}"
    await file.download_to_drive(file_path)

    try:
        with open(file_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=(f"audio.{file_ext}", audio_file.read()),
                model="whisper-large-v3",
                language="ru",
                response_format="text"
            )

        transcript_text = transcription
        context.user_data["last_transcript"] = transcript_text

        preset_key = user_presets[user_id]
        system_prompt = PRESETS[preset_key]["prompt"]

        analysis = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Вот транскрипция звонка:\n\n{transcript_text}"}
            ],
            temperature=0.3,
            max_tokens=2000
        )

        analysis_text = analysis.choices[0].message.content

        await update.message.reply_text(
            f"📊 АНАЛИЗ ЗВОНКА\n\n{analysis_text}"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Показать транскрипцию", callback_data="show_transcript")],
            [InlineKeyboardButton("◀️ Назад в меню", callback_data="go_menu")]
        ])

        await update.message.reply_text("Что дальше?", reply_markup=keyboard)

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при обработке: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


async def show_transcript(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    transcript = context.user_data.get("last_transcript", "Транскрипция недоступна")

    context.user_data["what_next_message_id"] = query.message.message_id

    role_transcript = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "Разбей транскрипцию по ролям. Определи кто говорит и оформи так:\n\n👤 Менеджер: текст\n🙋 Клиент: текст\n\nКаждая реплика с новой строки. Больше ничего не добавляй."},
            {"role": "user", "content": transcript}
        ],
        max_tokens=2000
    )

    formatted = role_transcript.choices[0].message.content

    if len(formatted) > 4000:
        formatted = formatted[:4000] + "...\n[текст обрезан]"

    await query.edit_message_text(
        f"📝 ТРАНСКРИПЦИЯ ПО РОЛЯМ:\n\n{formatted}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Назад", callback_data="back_to_what_next")]
        ])
    )


async def back_to_what_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Показать транскрипцию", callback_data="show_transcript")],
        [InlineKeyboardButton("◀️ Назад в меню", callback_data="go_menu")]
    ])

    await query.edit_message_text(
        "Что дальше?",
        reply_markup=keyboard
    )


def main():
    app = Application.builder().token(config.TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CallbackQueryHandler(go_menu, pattern="^go_menu$"))
    app.add_handler(CallbackQueryHandler(preset_callback, pattern="^preset_"))
    app.add_handler(CallbackQueryHandler(show_transcript, pattern="^show_transcript$"))
    app.add_handler(CallbackQueryHandler(back_to_what_next, pattern="^back_to_what_next$"))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO | filters.Document.ALL, handle_audio))

    print("🤖 Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()
