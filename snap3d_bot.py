"""
╔═══════════════════════════════════════════════════════════════════╗
║                     SNAP3D BOT  v2.0                              ║
║  Rasm / Matn → 3D model qidirish (Ko'p manbali)                   ║
║                                                                   ║
║  O'rnatish:                                                       ║
║    pip install python-telegram-bot aiohttp                        ║
║    python snap3d_bot.py                                           ║
╚═══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import csv
import io
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Optional

import aiohttp
from telegram import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ─────────────────────────────────────────────────────
# ⚙️  SOZLAMALAR  —  faqat shu blokni o'zgartiring
# ─────────────────────────────────────────────────────
BOT_TOKEN    = "8388408417:AAEt5cmJsC0jd2j6QAkk8oANXWKb7dhBA8o"   # BotFather'dan oling
ADMIN_IDS    = [1834797470]             # Sizning Telegram ID (@userinfobot dan bilib oling)
CHANNEL_LINK = "https://t.me/snap3d"

# ─────────────────────────────────────────────────────
# 📝  LOGGING
# ─────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("Snap3D")

# ─────────────────────────────────────────────────────
# 💾  JSON MA'LUMOTLAR BAZASI
# ─────────────────────────────────────────────────────
DB_FILE = "snap3d_db.json"


def _default_db() -> dict:
    return {
        "users": {},
        "banned": [],
        "stats": {
            "total_searches": 0,
            "total_users": 0,
            "daily": {},
        },
        "settings": {
            "free_daily_limit": 5,
            "premium_price_stars": 150,
            "welcome_extra": "",
            "maintenance": False,
        },
        "categories": {
            "🛋️ Divan & Kreslo": ["sofa", "armchair", "couch", "divan"],
            "🪑 Stul & Taburet":  ["chair", "stool", "seat"],
            "🛏️ Karavot":         ["bed", "mattress", "bedroom"],
            "🚿 Hammom":           ["bathroom", "toilet", "sink", "shower", "bathtub"],
            "💡 Chiroq & Lampa":   ["lamp", "light", "chandelier", "pendant"],
            "🌿 O'simlik":         ["plant", "tree", "indoor", "pot"],
            "🍽️ Oshxona":          ["kitchen", "table", "dining", "cabinet"],
            "🖼️ Dekor":            ["decor", "vase", "sculpture", "frame", "mirror"],
            "🚪 Eshik & Deraza":   ["door", "window", "frame"],
            "🧱 Tuzilma":          ["wall", "column", "ceiling", "structure"],
        },
        "sources": {
            # Admin /addsource gdrive  Nom | CSV_URL  buyrug'i bilan qo'shadi
            "gdrive":     [],
            # Admin /addsource tgchannel @kanal  buyrug'i bilan qo'shadi
            "tgchannel":  [],
            # Admin /addsource url  Nom | JSON_URL  buyrug'i bilan qo'shadi
            "custom_url": [],
        },
        # /addmodel yoki /uploaddb orqali to'ldiriladi
        "local_models":    [],
        # Telegram kanallardan avtomatik indekslangan
        "indexed_models":  [],
        # 24 soatlik kesh
        "source_cache":  {},
        "cache_updated": {},
    }


def load_db() -> dict:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Yangi kalitlarni qo'shish (eski DB uchun)
        for k, v in _default_db().items():
            if k not in data:
                data[k] = v
        return data
    db = _default_db()
    save_db(db)
    return db


def save_db(db: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def get_user(db: dict, uid: int, username: str = "") -> dict:
    key = str(uid)
    if key not in db["users"]:
        db["users"][key] = {
            "lang": "uz",
            "premium": False,
            "premium_until": None,
            "searches_today": 0,
            "last_search_date": None,
            "total_searches": 0,
            "favorites": [],
            "history": [],
            "joined": datetime.now().isoformat(),
            "username": username,
        }
        db["stats"]["total_users"] = len(db["users"])
        save_db(db)
    elif username:
        db["users"][key]["username"] = username
    return db["users"][key]


def reset_daily(user: dict, db: dict):
    today = datetime.now().date().isoformat()
    if user.get("last_search_date") != today:
        user["searches_today"] = 0
        user["last_search_date"] = today
        save_db(db)


# ─────────────────────────────────────────────────────
# 🌐  KO'P TILLIK KOMANDALAR MENYUSI
# ─────────────────────────────────────────────────────
CMDS = {
    "uz": [
        BotCommand("start",      "🏠 Bosh menyu"),
        BotCommand("search",     "🔎 Matn bilan qidirish"),
        BotCommand("categories", "📂 Kategoriyalar"),
        BotCommand("favorites",  "❤️ Saqlanganlar"),
        BotCommand("history",    "📋 Qidirish tarixi"),
        BotCommand("premium",    "⭐ Premium a'zolik"),
        BotCommand("settings",   "⚙️ Sozlamalar"),
        BotCommand("help",       "❓ Yordam"),
    ],
    "ru": [
        BotCommand("start",      "🏠 Главное меню"),
        BotCommand("search",     "🔎 Поиск по тексту"),
        BotCommand("categories", "📂 Категории"),
        BotCommand("favorites",  "❤️ Сохранённые"),
        BotCommand("history",    "📋 История поиска"),
        BotCommand("premium",    "⭐ Premium подписка"),
        BotCommand("settings",   "⚙️ Настройки"),
        BotCommand("help",       "❓ Помощь"),
    ],
    "en": [
        BotCommand("start",      "🏠 Main menu"),
        BotCommand("search",     "🔎 Search by text"),
        BotCommand("categories", "📂 Categories"),
        BotCommand("favorites",  "❤️ Saved models"),
        BotCommand("history",    "📋 Search history"),
        BotCommand("premium",    "⭐ Premium plan"),
        BotCommand("settings",   "⚙️ Settings"),
        BotCommand("help",       "❓ Help"),
    ],
}

# ─────────────────────────────────────────────────────
# 🌐  TARJIMALAR
# ─────────────────────────────────────────────────────
TR = {
    "uz": {
        "choose_lang":          "🌍 <b>Tilni tanlang:</b>",
        "welcome": (
            "👋 <b>Snap3D ga xush kelibsiz!</b>\n\n"
            "📸 Rasm yuboring → 🤖 AI ob'ektni taniydi → 🎁 3D model topiladi\n\n"
            "🔥 <b>100,000+ haqiqiy 3D model</b>\n"
            "✅ Interyer dizaynerlar, arxitektor va 3D artistlar uchun\n\n"
            "👇 Kerakli bo'limni tanlang:"
        ),
        "btn_photo":     "📸 Rasm yuborish",
        "btn_search":    "🔎 Matn bilan qidirish",
        "btn_cats":      "📂 Kategoriyalar",
        "btn_favs":      "❤️ Saqlanganlar",
        "btn_premium":   "⭐ Premium",
        "btn_help":      "❓ Yordam",
        "btn_settings":  "⚙️ Sozlamalar",
        "btn_back":      "◀️ Orqaga",
        "btn_download":  "⬇️ Yuklab olish",
        "btn_save":      "❤️ Saqlash",
        "btn_unsave":    "💔 O'chirish",
        "btn_filter":    "🎛️ Format filtri",
        "photo_tip": (
            "📸 <b>Rasmni qanday yuborish kerak?</b>\n\n"
            "✅ <b>To'g'ri:</b>\n"
            "• Ob'ekt to'liq va aniq ko'rinsin\n"
            "• Fon oddiy va toza bo'lsin\n"
            "• Ob'ekt markazda joylashsin\n\n"
            "❌ <b>Noto'g'ri:</b>\n"
            "• Ko'p narsalar bir rasmda\n"
            "• Uzoqdagi mayda ob'ektlar\n"
            "• Xira yoki qorong'u rasm\n\n"
            "📤 <i>Endi rasmingizni yuboring...</i>"
        ),
        "searching":     "🔍 Barcha manbalar qidirilmoqda...",
        "found":         "✅ <b>Topildi!</b>",
        "found_count":   "({count} ta natija)",
        "not_found": (
            "😕 <b>Model topilmadi</b>\n\n"
            "💡 <b>Maslahat:</b>\n"
            "• Boshqa burchakdan rasm oling\n"
            "• Fon oddiyroq bo'lsin\n"
            "• /search orqali matn bilan qidiring\n"
            "• Kategoriyalar bo'limiga qarang\n\n"
            "❓ Muammo davom etsa: @grabit3d_admin"
        ),
        "search_prompt": "🔎 Qidirmoqchi bo'lgan modelni yozing:\n<i>Misol: sofa, chair, lamp, door...</i>",
        "cats_title":    "📂 <b>Kategoriyalar</b>\nBirini tanlang:",
        "favs_title":    "❤️ <b>Saqlanganlar:</b>\n\n",
        "favs_empty":    "❤️ Savichangiz bo'sh.\nNatija kelganda <b>❤️ Saqlash</b> tugmasini bosing.",
        "hist_title":    "📋 <b>Oxirgi qidiruvlar:</b>\n\n",
        "hist_empty":    "📋 Qidirish tarixi yo'q.",
        "limit_reached": (
            "⛔ <b>Kunlik limit tugadi</b>\n\n"
            "🆓 Bepul: kuniga <b>{limit}</b> ta qidiruv\n"
            "⭐ Premium: <b>cheksiz</b> qidiruv\n\n"
            "Premium olish: /premium"
        ),
        "premium_info": (
            "⭐ <b>Premium a'zolik</b>\n\n"
            "✅ Cheksiz qidiruv\n"
            "✅ Format filtri (FBX, OBJ, MAX...)\n"
            "✅ Cheksiz sevimlilar\n"
            "✅ Ustuvor qidiruv\n\n"
            "💰 Narxi: <b>{price}</b> Telegram Stars / oy"
        ),
        "premium_btn":   "⭐ {price} Stars bilan xarid",
        "saved":         "❤️ Saqlab qo'yildi!",
        "unsaved":       "💔 O'chirildi.",
        "model_info":    "📦 <b>{name}</b>\n🏷️ Format: {fmt}\n📁 Manba: {src}\n",
        "settings_title":"⚙️ <b>Sozlamalar</b>\nTilni tanlang:",
        "help": (
            "❓ <b>Yordam</b>\n\n"
            "/start — Bosh menyu\n"
            "/search — Matn bilan qidirish\n"
            "/categories — Kategoriyalar\n"
            "/favorites — Saqlanganlar\n"
            "/history — Qidirish tarixi\n"
            "/premium — Premium a'zolik\n"
            "/settings — Sozlamalar\n\n"
            "📞 Muammo: @grabit3d_admin\n"
            "📢 Kanal: " + CHANNEL_LINK
        ),
        "banned":        "🚫 Siz bloklangansiz. Murojaat: @grabit3d_admin",
        "maintenance":   "🔧 Bot texnik ishlar uchun to'xtatilgan. Tez orada qaytamiz!",
        "admin_only":    "⛔ Bu buyruq faqat adminlar uchun.",
        "broadcast_prompt": "📢 Barcha foydalanuvchilarga yuboriladigan xabarni yozing:",
        "broadcast_done":   "✅ {count} ta foydalanuvchiga yuborildi.",
        "cache_refreshed":  "✅ Barcha manbalar yangilandi.",
        "no_sources":    "Hali hech qanday manba qo'shilmagan.",
        "sources_list":  "📡 <b>Qidiruv manbalari:</b>\n\n",
        "model_added":   "✅ Model qo'shildi: {name}",
        "fmt_choose":    "🎛️ Format tanlang:",
        "all_formats":   "🔍 Barchasi",
    },
    "ru": {
        "choose_lang":          "🌍 <b>Выберите язык:</b>",
        "welcome": (
            "👋 <b>Добро пожаловать в Snap3D!</b>\n\n"
            "📸 Отправьте фото → 🤖 AI распознаёт → 🎁 3D модель найдена\n\n"
            "🔥 <b>100,000+ уникальных 3D моделей</b>\n"
            "✅ Для дизайнеров интерьера, архитекторов и 3D художников\n\n"
            "👇 Выберите нужный раздел:"
        ),
        "btn_photo":     "📸 Отправить фото",
        "btn_search":    "🔎 Поиск по тексту",
        "btn_cats":      "📂 Категории",
        "btn_favs":      "❤️ Сохранённые",
        "btn_premium":   "⭐ Premium",
        "btn_help":      "❓ Помощь",
        "btn_settings":  "⚙️ Настройки",
        "btn_back":      "◀️ Назад",
        "btn_download":  "⬇️ Скачать",
        "btn_save":      "❤️ Сохранить",
        "btn_unsave":    "💔 Удалить",
        "btn_filter":    "🎛️ Фильтр форматов",
        "photo_tip": (
            "📸 <b>Как правильно отправить фото?</b>\n\n"
            "✅ <b>Правильно:</b>\n"
            "• Объект полностью и чётко виден\n"
            "• Фон простой и чистый\n"
            "• Объект по центру кадра\n\n"
            "❌ <b>Неправильно:</b>\n"
            "• Слишком много предметов на фото\n"
            "• Маленькие объекты вдали\n"
            "• Размытое или тёмное фото\n\n"
            "📤 <i>Теперь отправьте ваше фото...</i>"
        ),
        "searching":     "🔍 Поиск по всем источникам...",
        "found":         "✅ <b>Найдено!</b>",
        "found_count":   "({count} результатов)",
        "not_found": (
            "😕 <b>Модель не найдена</b>\n\n"
            "💡 <b>Совет:</b>\n"
            "• Сфотографируйте с другого угла\n"
            "• Фон должен быть проще\n"
            "• Попробуйте /search по тексту\n"
            "• Посмотрите в категориях\n\n"
            "❓ Если проблема продолжается: @grabit3d_admin"
        ),
        "search_prompt": "🔎 Введите название модели:\n<i>Пример: sofa, chair, lamp, door...</i>",
        "cats_title":    "📂 <b>Категории</b>\nВыберите одну:",
        "favs_title":    "❤️ <b>Сохранённые:</b>\n\n",
        "favs_empty":    "❤️ Список сохранённых пуст.\nНажмите <b>❤️ Сохранить</b> при получении результата.",
        "hist_title":    "📋 <b>Последние поиски:</b>\n\n",
        "hist_empty":    "📋 История поиска пуста.",
        "limit_reached": (
            "⛔ <b>Дневной лимит исчерпан</b>\n\n"
            "🆓 Бесплатно: <b>{limit}</b> поисков в день\n"
            "⭐ Premium: <b>безлимитный</b> поиск\n\n"
            "Получить Premium: /premium"
        ),
        "premium_info": (
            "⭐ <b>Premium подписка</b>\n\n"
            "✅ Безлимитный поиск\n"
            "✅ Фильтр форматов (FBX, OBJ, MAX...)\n"
            "✅ Безлимитные сохранения\n"
            "✅ Приоритетный поиск\n\n"
            "💰 Цена: <b>{price}</b> Telegram Stars / месяц"
        ),
        "premium_btn":   "⭐ Купить за {price} Stars",
        "saved":         "❤️ Модель сохранена!",
        "unsaved":       "💔 Модель удалена.",
        "model_info":    "📦 <b>{name}</b>\n🏷️ Формат: {fmt}\n📁 Источник: {src}\n",
        "settings_title":"⚙️ <b>Настройки</b>\nВыберите язык:",
        "help": (
            "❓ <b>Помощь</b>\n\n"
            "/start — Главное меню\n"
            "/search — Поиск по тексту\n"
            "/categories — Категории\n"
            "/favorites — Сохранённые\n"
            "/history — История поиска\n"
            "/premium — Premium подписка\n"
            "/settings — Настройки\n\n"
            "📞 Проблемы: @grabit3d_admin\n"
            "📢 Канал: " + CHANNEL_LINK
        ),
        "banned":        "🚫 Вы заблокированы. Обратитесь: @grabit3d_admin",
        "maintenance":   "🔧 Бот на техобслуживании. Скоро вернёмся!",
        "admin_only":    "⛔ Эта команда только для администраторов.",
        "broadcast_prompt": "📢 Введите сообщение для всех пользователей:",
        "broadcast_done":   "✅ Отправлено {count} пользователям.",
        "cache_refreshed":  "✅ Все источники обновлены.",
        "no_sources":    "Источники ещё не добавлены.",
        "sources_list":  "📡 <b>Источники поиска:</b>\n\n",
        "model_added":   "✅ Модель добавлена: {name}",
        "fmt_choose":    "🎛️ Выберите формат:",
        "all_formats":   "🔍 Все",
    },
    "en": {
        "choose_lang":          "🌍 <b>Choose language:</b>",
        "welcome": (
            "👋 <b>Welcome to Snap3D!</b>\n\n"
            "📸 Send a photo → 🤖 AI recognizes object → 🎁 3D model found\n\n"
            "🔥 <b>100,000+ unique 3D models</b>\n"
            "✅ For interior designers, architects and 3D artists\n\n"
            "👇 Choose a section:"
        ),
        "btn_photo":     "📸 Send photo",
        "btn_search":    "🔎 Search by text",
        "btn_cats":      "📂 Categories",
        "btn_favs":      "❤️ Favorites",
        "btn_premium":   "⭐ Premium",
        "btn_help":      "❓ Help",
        "btn_settings":  "⚙️ Settings",
        "btn_back":      "◀️ Back",
        "btn_download":  "⬇️ Download",
        "btn_save":      "❤️ Save",
        "btn_unsave":    "💔 Remove",
        "btn_filter":    "🎛️ Format filter",
        "photo_tip": (
            "📸 <b>How to send the best photo?</b>\n\n"
            "✅ <b>Good:</b>\n"
            "• Object fully and clearly visible\n"
            "• Simple and clean background\n"
            "• Object centered in the frame\n\n"
            "❌ <b>Bad:</b>\n"
            "• Too many objects in one photo\n"
            "• Small distant objects\n"
            "• Blurry or dark photo\n\n"
            "📤 <i>Now send your photo...</i>"
        ),
        "searching":     "🔍 Searching all sources...",
        "found":         "✅ <b>Found!</b>",
        "found_count":   "({count} results)",
        "not_found": (
            "😕 <b>No model found</b>\n\n"
            "💡 <b>Tips:</b>\n"
            "• Try a different angle\n"
            "• Use a simpler background\n"
            "• Try /search with text\n"
            "• Browse categories\n\n"
            "❓ If issue persists: @grabit3d_admin"
        ),
        "search_prompt": "🔎 Type the model name:\n<i>Example: sofa, chair, lamp, door...</i>",
        "cats_title":    "📂 <b>Categories</b>\nChoose one:",
        "favs_title":    "❤️ <b>Favorites:</b>\n\n",
        "favs_empty":    "❤️ Your favorites list is empty.\nPress <b>❤️ Save</b> when you get a result.",
        "hist_title":    "📋 <b>Recent searches:</b>\n\n",
        "hist_empty":    "📋 No search history yet.",
        "limit_reached": (
            "⛔ <b>Daily limit reached</b>\n\n"
            "🆓 Free: <b>{limit}</b> searches/day\n"
            "⭐ Premium: <b>unlimited</b> search\n\n"
            "Get Premium: /premium"
        ),
        "premium_info": (
            "⭐ <b>Premium subscription</b>\n\n"
            "✅ Unlimited searches\n"
            "✅ Format filter (FBX, OBJ, MAX...)\n"
            "✅ Unlimited favorites\n"
            "✅ Priority search\n\n"
            "💰 Price: <b>{price}</b> Telegram Stars / month"
        ),
        "premium_btn":   "⭐ Buy for {price} Stars",
        "saved":         "❤️ Model saved!",
        "unsaved":       "💔 Model removed.",
        "model_info":    "📦 <b>{name}</b>\n🏷️ Format: {fmt}\n📁 Source: {src}\n",
        "settings_title":"⚙️ <b>Settings</b>\nChoose language:",
        "help": (
            "❓ <b>Help</b>\n\n"
            "/start — Main menu\n"
            "/search — Search by text\n"
            "/categories — Categories\n"
            "/favorites — Saved models\n"
            "/history — Search history\n"
            "/premium — Premium plan\n"
            "/settings — Settings\n\n"
            "📞 Issues: @grabit3d_admin\n"
            "📢 Channel: " + CHANNEL_LINK
        ),
        "banned":        "🚫 You are banned. Contact: @grabit3d_admin",
        "maintenance":   "🔧 Bot is under maintenance. Back soon!",
        "admin_only":    "⛔ This command is for admins only.",
        "broadcast_prompt": "📢 Write message to send to all users:",
        "broadcast_done":   "✅ Sent to {count} users.",
        "cache_refreshed":  "✅ All sources refreshed.",
        "no_sources":    "No sources have been added yet.",
        "sources_list":  "📡 <b>Search sources:</b>\n\n",
        "model_added":   "✅ Model added: {name}",
        "fmt_choose":    "🎛️ Choose format:",
        "all_formats":   "🔍 All",
    },
}


def tr(lang: str, key: str, **kw) -> str:
    lang = lang if lang in TR else "uz"
    text = TR[lang].get(key, TR["uz"].get(key, key))
    return text.format(**kw) if kw else text


# ─────────────────────────────────────────────────────
# 🔎  KO'P MANBALI QIDIRUV TIZIMI
# ─────────────────────────────────────────────────────
def normalize(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def relevance_score(model: dict, tokens: list) -> int:
    score = 0
    name = normalize(model.get("name", ""))
    tags = [normalize(tg) for tg in model.get("tags", [])]
    cat  = normalize(model.get("category", ""))
    for tok in tokens:
        if tok in name:
            score += 3 if name.startswith(tok) else 2
        for tg in tags:
            if tok in tg:
                score += 2
        if tok in cat:
            score += 1
    return score


def search_local(db: dict, query: str, fmt_filter: str = "") -> list:
    tokens = normalize(query).split()
    pool   = db.get("local_models", []) + db.get("indexed_models", [])
    scored = []
    for m in pool:
        if fmt_filter and fmt_filter.upper() not in m.get("format", "").upper():
            continue
        s = relevance_score(m, tokens)
        if s > 0:
            scored.append((s, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:10]]


async def _fetch_url(url: str, cache: dict, updated: dict, source_name: str) -> list:
    key  = url
    last = updated.get(key)
    if last:
        if (datetime.now() - datetime.fromisoformat(last)).total_seconds() < 86400:
            return cache.get(key, [])
    models = []
    try:
        async with aiohttp.ClientSession() as ses:
            async with ses.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                raw = await resp.text()
                ct  = resp.content_type or ""
                # JSON
                if "json" in ct or url.endswith(".json"):
                    data = json.loads(raw)
                    if isinstance(data, list):
                        for item in data:
                            n = item.get("name", "")
                            if n:
                                models.append({
                                    "name":     n,
                                    "url":      item.get("url", ""),
                                    "format":   item.get("format", "FBX/OBJ"),
                                    "tags":     item.get("tags", normalize(n).split()),
                                    "category": item.get("category", ""),
                                    "source":   source_name,
                                })
                # CSV
                else:
                    reader = csv.DictReader(io.StringIO(raw))
                    for row in reader:
                        n  = row.get("name") or row.get("Name") or ""
                        u  = row.get("url")  or row.get("URL")  or row.get("link") or ""
                        fm = row.get("format") or row.get("Format") or "FBX/OBJ"
                        tr_raw = row.get("tags") or row.get("Tags") or ""
                        tgs = [x.strip() for x in tr_raw.split(",") if x.strip()] or normalize(n).split()
                        if n:
                            models.append({
                                "name": n, "url": u, "format": fm,
                                "tags": tgs, "category": "", "source": source_name,
                            })
        cache[key]   = models
        updated[key] = datetime.now().isoformat()
        logger.info(f"Fetched '{source_name}': {len(models)} models")
    except Exception as e:
        logger.warning(f"Fetch error '{source_name}' ({url}): {e}")
        return cache.get(key, [])
    return models


async def multi_search(db: dict, query: str, fmt_filter: str = "") -> list:
    tokens = normalize(query).split()
    cache  = db.setdefault("source_cache", {})
    upd    = db.setdefault("cache_updated", {})

    # 1. Lokal qidiruv (sinxron, tez)
    local = search_local(db, query, fmt_filter)

    # 2. Tashqi manbalar parallel yuklanadi
    tasks = []
    for src in db["sources"].get("gdrive", []):
        if src.get("enabled", True) and src.get("url"):
            tasks.append(_fetch_url(src["url"], cache, upd, src.get("name","GDrive")))
    for src in db["sources"].get("custom_url", []):
        if src.get("enabled", True) and src.get("url"):
            tasks.append(_fetch_url(src["url"], cache, upd, src.get("name","URL")))

    external = []
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                external.extend(r)

    # 3. Tashqi modellarni ham filtrlash va tartiblash
    all_models = local[:]
    seen_urls  = {m.get("url") for m in local if m.get("url")}
    for m in external:
        if fmt_filter and fmt_filter.upper() not in m.get("format", "").upper():
            continue
        s = relevance_score(m, tokens)
        url_ = m.get("url", "")
        if url_ and url_ in seen_urls:
            continue
        seen_urls.add(url_)
        all_models.append(m)

    # 4. Tartiblash
    def _score(m):
        return relevance_score(m, tokens)
    all_models.sort(key=_score, reverse=True)

    # 5. Hech narsa topilmasa — birinchi 5 tani qaytarish (agar qidiruv bo'sh bo'lsa)
    final = all_models[:10]
    if not final and (local or external):
        final = (local + external)[:5]

    # Keshni saqlash
    db["source_cache"]  = cache
    db["cache_updated"] = upd
    save_db(db)
    return final


# ─────────────────────────────────────────────────────
# 🎛️  KLAVIATURALAR
# ─────────────────────────────────────────────────────
def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇺🇿 O'zbek",  callback_data="lang_uz"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
    ]])


def main_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(tr(lang,"btn_photo"),   callback_data="mn_photo"),
            InlineKeyboardButton(tr(lang,"btn_search"),  callback_data="mn_search"),
        ],
        [
            InlineKeyboardButton(tr(lang,"btn_cats"),    callback_data="mn_cats"),
            InlineKeyboardButton(tr(lang,"btn_favs"),    callback_data="mn_favs"),
        ],
        [
            InlineKeyboardButton(tr(lang,"btn_premium"), callback_data="mn_premium"),
            InlineKeyboardButton(tr(lang,"btn_help"),    callback_data="mn_help"),
        ],
        [InlineKeyboardButton(tr(lang,"btn_settings"),   callback_data="mn_settings")],
    ])


def back_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(tr(lang,"btn_back"), callback_data="back_main")
    ]])


def results_kb(lang: str, results: list, idx: int, is_saved: bool) -> InlineKeyboardMarkup:
    model = results[idx]
    rows  = []
    if model.get("url"):
        rows.append([InlineKeyboardButton(tr(lang,"btn_download"), url=model["url"])])
    save_lbl = tr(lang,"btn_unsave") if is_saved else tr(lang,"btn_save")
    nav_row  = [InlineKeyboardButton(save_lbl, callback_data=f"save_{idx}")]
    if idx > 0:
        nav_row.insert(0, InlineKeyboardButton("◀️", callback_data=f"res_{idx-1}"))
    if idx < len(results) - 1:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"res_{idx+1}"))
    rows.append(nav_row)
    rows.append([
        InlineKeyboardButton(tr(lang,"btn_filter"), callback_data="fmt_filter"),
        InlineKeyboardButton(tr(lang,"btn_back"),   callback_data="back_main"),
    ])
    return InlineKeyboardMarkup(rows)


def cats_kb(db: dict, lang: str) -> InlineKeyboardMarkup:
    cats = list(db.get("categories", {}).keys())
    rows = []
    for i in range(0, len(cats), 2):
        row = [InlineKeyboardButton(cats[i], callback_data=f"cat_{i}")]
        if i + 1 < len(cats):
            row.append(InlineKeyboardButton(cats[i+1], callback_data=f"cat_{i+1}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(tr(lang,"btn_back"), callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def fmt_kb(lang: str) -> InlineKeyboardMarkup:
    fmts = ["FBX", "OBJ", "MAX", "GLB", "C4D", tr(lang,"all_formats")]
    rows = [[InlineKeyboardButton(f, callback_data=f"fmt_{f}") for f in fmts[i:i+3]]
            for i in range(0, len(fmts), 3)]
    rows.append([InlineKeyboardButton(tr(lang,"btn_back"), callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def premium_kb(lang: str, price: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr(lang,"premium_btn",price=price), callback_data="buy_premium")],
        [InlineKeyboardButton(tr(lang,"btn_back"), callback_data="back_main")],
    ])


def settings_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇺🇿 O'zbek",  callback_data="lang_uz"),
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        ],
        [InlineKeyboardButton(tr(lang,"btn_back"), callback_data="back_main")],
    ])


# ─────────────────────────────────────────────────────
# 🛠️  YORDAMCHI FUNKSIYALAR
# ─────────────────────────────────────────────────────
def check_access(db: dict, uid: int) -> Optional[str]:
    if str(uid) in db.get("banned", []):
        return "banned"
    if db["settings"].get("maintenance") and uid not in ADMIN_IDS:
        return "maintenance"
    return None


async def set_commands_for_user(bot, uid: int, lang: str):
    try:
        scope = BotCommandScopeChat(chat_id=uid)
        await bot.set_my_commands(CMDS.get(lang, CMDS["uz"]), scope=scope)
    except Exception:
        pass


def _model_text(lang: str, results: list, idx: int) -> str:
    model  = results[idx]
    header = tr(lang,"found") + " " + tr(lang,"found_count", count=len(results)) + "\n\n"
    body   = tr(lang,"model_info",
                name=model.get("name","?"),
                fmt=model.get("format","FBX/OBJ"),
                src=model.get("source","Snap3D"))
    counter = f"<i>{idx+1}/{len(results)}</i>"
    return header + body + counter


def _is_saved(user: dict, model: dict) -> bool:
    return any(f.get("url") == model.get("url") for f in user.get("favorites", []))


async def _show_results(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE,
    results: list, lang: str, user: dict, db: dict,
    edit: bool = False,
):
    ctx.user_data["results"] = results
    if not results:
        text = tr(lang,"not_found")
        kb   = back_kb(lang)
        if edit:
            await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        return
    model    = results[0]
    saved    = _is_saved(user, model)
    text     = _model_text(lang, results, 0)
    kb       = results_kb(lang, results, 0, saved)
    if edit:
        await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


async def _do_search(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE,
    db: dict, user: dict, uid: int, lang: str,
    query: str, fmt_filter: str = "", edit: bool = False,
):
    reset_daily(user, db)
    limit = db["settings"]["free_daily_limit"]
    if not user.get("premium") and user.get("searches_today", 0) >= limit:
        text = tr(lang,"limit_reached", limit=limit)
        kb   = InlineKeyboardMarkup([[InlineKeyboardButton("⭐ Premium", callback_data="mn_premium")]])
        if edit:
            await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        return

    results = await multi_search(db, query, fmt_filter)

    # Statistika
    user["searches_today"] = user.get("searches_today", 0) + 1
    user["total_searches"]  = user.get("total_searches",  0) + 1
    db["stats"]["total_searches"] = db["stats"].get("total_searches", 0) + 1
    today = datetime.now().date().isoformat()
    db["stats"]["daily"][today] = db["stats"]["daily"].get(today, 0) + 1
    hist = user.setdefault("history", [])
    hist.append({"query": query, "time": datetime.now().isoformat()})
    user["history"] = hist[-20:]
    ctx.user_data["last_query"] = query
    save_db(db)

    await _show_results(update, ctx, results, lang, user, db, edit=edit)


# ─────────────────────────────────────────────────────
# 📨  FOYDALANUVCHI HANDLERLARI
# ─────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db  = load_db()
    uid = update.effective_user.id
    err = check_access(db, uid)
    if err:
        user = get_user(db, uid)
        await update.message.reply_text(tr(user.get("lang","uz"), err))
        return
    get_user(db, uid, update.effective_user.username or "")
    await update.message.reply_text(
        tr("uz","choose_lang"), reply_markup=lang_kb(), parse_mode=ParseMode.HTML
    )


async def cb_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    data = q.data
    db   = load_db()
    uid  = q.from_user.id
    user = get_user(db, uid, q.from_user.username or "")
    lang = user.get("lang", "uz")
    err  = check_access(db, uid)
    if err:
        await q.edit_message_text(tr(lang, err))
        return

    # ── Til tanlash
    if data.startswith("lang_"):
        new_lang = data.split("_", 1)[1]
        user["lang"] = new_lang
        save_db(db)
        lang = new_lang
        await set_commands_for_user(ctx.bot, uid, lang)
        extra = db["settings"].get("welcome_extra", "")
        txt   = tr(lang,"welcome") + (f"\n\n📣 {extra}" if extra else "")
        await q.edit_message_text(txt, reply_markup=main_kb(lang), parse_mode=ParseMode.HTML)

    # ── Bosh menyu
    elif data == "back_main":
        extra = db["settings"].get("welcome_extra", "")
        txt   = tr(lang,"welcome") + (f"\n\n📣 {extra}" if extra else "")
        await q.edit_message_text(txt, reply_markup=main_kb(lang), parse_mode=ParseMode.HTML)

    elif data == "mn_photo":
        ctx.user_data["awaiting_photo"] = True
        await q.edit_message_text(tr(lang,"photo_tip"), reply_markup=back_kb(lang), parse_mode=ParseMode.HTML)

    elif data == "mn_search":
        ctx.user_data["awaiting_search"] = True
        await q.edit_message_text(tr(lang,"search_prompt"), reply_markup=back_kb(lang), parse_mode=ParseMode.HTML)

    elif data == "mn_cats":
        await q.edit_message_text(tr(lang,"cats_title"), reply_markup=cats_kb(db,lang), parse_mode=ParseMode.HTML)

    elif data.startswith("cat_"):
        idx_c = int(data.split("_", 1)[1])
        cats  = list(db.get("categories", {}).items())
        if idx_c < len(cats):
            _, cat_tags = cats[idx_c]
            q_str = " ".join(cat_tags[:3]) if isinstance(cat_tags, list) else str(cat_tags).split()[0]
            await q.edit_message_text(tr(lang,"searching"), parse_mode=ParseMode.HTML)
            await _do_search(update, ctx, db, user, uid, lang, q_str, edit=True)

    elif data == "mn_favs":
        favs = user.get("favorites", [])
        if not favs:
            await q.edit_message_text(tr(lang,"favs_empty"), reply_markup=back_kb(lang), parse_mode=ParseMode.HTML)
        else:
            lines = tr(lang,"favs_title")
            for i, fav in enumerate(favs[-10:], 1):
                u_ = fav.get("url","")
                n_ = fav.get("name","?")
                lines += (f"{i}. <a href='{u_}'>{n_}</a>\n" if u_ else f"{i}. {n_}\n")
            await q.edit_message_text(lines, reply_markup=back_kb(lang),
                                      parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    elif data == "mn_help":
        await q.edit_message_text(tr(lang,"help"), reply_markup=back_kb(lang),
                                  parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    elif data == "mn_premium":
        price = db["settings"].get("premium_price_stars", 150)
        await q.edit_message_text(tr(lang,"premium_info",price=price),
                                  reply_markup=premium_kb(lang,price), parse_mode=ParseMode.HTML)

    elif data == "buy_premium":
        price = db["settings"].get("premium_price_stars", 150)
        await q.message.reply_invoice(
            title="Snap3D Premium",
            description="1 oy cheksiz qidiruv / 1 month unlimited searches",
            payload="premium_1m",
            currency="XTR",
            prices=[{"label":"Premium 1 month","amount":price}],
        )

    elif data == "mn_settings":
        await q.edit_message_text(tr(lang,"settings_title"), reply_markup=settings_kb(lang), parse_mode=ParseMode.HTML)

    # ── Natijalar navigatsiya
    elif data.startswith("res_"):
        idx_r   = int(data.split("_", 1)[1])
        results = ctx.user_data.get("results", [])
        if not results:
            return
        idx_r = max(0, min(idx_r, len(results)-1))
        model  = results[idx_r]
        saved  = _is_saved(user, model)
        await q.edit_message_text(_model_text(lang,results,idx_r),
                                  reply_markup=results_kb(lang,results,idx_r,saved),
                                  parse_mode=ParseMode.HTML)

    # ── Saqlash / O'chirish
    elif data.startswith("save_"):
        idx_s   = int(data.split("_", 1)[1])
        results = ctx.user_data.get("results", [])
        if idx_s >= len(results):
            return
        model   = results[idx_s]
        favs    = user.setdefault("favorites", [])
        existing = next((f for f in favs if f.get("url") == model.get("url")), None)
        if existing:
            favs.remove(existing)
            await q.answer(tr(lang,"unsaved"))
        else:
            favs.append(model)
            await q.answer(tr(lang,"saved"))
        save_db(db)
        saved_now = not bool(existing)
        try:
            await q.edit_message_reply_markup(reply_markup=results_kb(lang,results,idx_s,saved_now))
        except Exception:
            pass

    # ── Format filtri
    elif data == "fmt_filter":
        await q.edit_message_text(tr(lang,"fmt_choose"), reply_markup=fmt_kb(lang), parse_mode=ParseMode.HTML)

    elif data.startswith("fmt_"):
        fmt   = data[4:]
        all_f = [tr(l,"all_formats") for l in ("uz","ru","en")]
        if fmt in all_f:
            fmt = ""
        q_str = ctx.user_data.get("last_query", "furniture")
        await q.edit_message_text(tr(lang,"searching"), parse_mode=ParseMode.HTML)
        await _do_search(update, ctx, db, user, uid, lang, q_str, fmt_filter=fmt, edit=True)


async def photo_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db   = load_db()
    uid  = update.effective_user.id
    user = get_user(db, uid, update.effective_user.username or "")
    lang = user.get("lang","uz")
    err  = check_access(db, uid)
    if err:
        await update.message.reply_text(tr(lang, err))
        return

    msg    = await update.message.reply_text(tr(lang,"searching"), parse_mode=ParseMode.HTML)
    caption = (update.message.caption or "").strip()
    query   = caption if caption else "furniture 3d model"

    # ─── AI Vision ulanish joyi ─────────────────────────────
    # OpenAI Vision misoli (ochib qo'ying):
    #
    # photo  = update.message.photo[-1]
    # file   = await ctx.bot.get_file(photo.file_id)
    # query  = await analyze_with_openai(file.file_path) or caption or "furniture"
    #
    # ────────────────────────────────────────────────────────

    reset_daily(user, db)
    limit = db["settings"]["free_daily_limit"]
    if not user.get("premium") and user.get("searches_today", 0) >= limit:
        await msg.edit_text(tr(lang,"limit_reached",limit=limit),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⭐ Premium",callback_data="mn_premium")]]),
            parse_mode=ParseMode.HTML)
        return

    results = await multi_search(db, query)
    user["searches_today"] = user.get("searches_today", 0) + 1
    user["total_searches"]  = user.get("total_searches",  0) + 1
    db["stats"]["total_searches"] = db["stats"].get("total_searches", 0) + 1
    today = datetime.now().date().isoformat()
    db["stats"]["daily"][today] = db["stats"]["daily"].get(today, 0) + 1
    ctx.user_data["results"]    = results
    ctx.user_data["last_query"] = query
    save_db(db)

    if not results:
        await msg.edit_text(tr(lang,"not_found"), reply_markup=back_kb(lang), parse_mode=ParseMode.HTML)
        return
    model = results[0]
    saved = _is_saved(user, model)
    await msg.edit_text(_model_text(lang,results,0), reply_markup=results_kb(lang,results,0,saved), parse_mode=ParseMode.HTML)


async def text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db   = load_db()
    uid  = update.effective_user.id
    user = get_user(db, uid, update.effective_user.username or "")
    lang = user.get("lang","uz")
    text = update.message.text.strip()
    err  = check_access(db, uid)
    if err:
        await update.message.reply_text(tr(lang, err))
        return

    # Admin broadcast
    if ctx.user_data.pop("awaiting_broadcast", False) and uid in ADMIN_IDS:
        count = 0
        for u_id in list(db["users"].keys()):
            try:
                await ctx.bot.send_message(int(u_id), f"📢 {text}", parse_mode=ParseMode.HTML)
                count += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass
        await update.message.reply_text(tr(lang,"broadcast_done",count=count))
        return

    # Matn qidiruvi
    if ctx.user_data.pop("awaiting_search", False):
        msg = await update.message.reply_text(tr(lang,"searching"), parse_mode=ParseMode.HTML)
        reset_daily(user, db)
        limit = db["settings"]["free_daily_limit"]
        if not user.get("premium") and user.get("searches_today", 0) >= limit:
            await msg.edit_text(tr(lang,"limit_reached",limit=limit),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⭐ Premium",callback_data="mn_premium")]]),
                parse_mode=ParseMode.HTML)
            return
        results = await multi_search(db, text)
        user["searches_today"] = user.get("searches_today", 0) + 1
        user["total_searches"]  = user.get("total_searches",  0) + 1
        db["stats"]["total_searches"] = db["stats"].get("total_searches", 0) + 1
        today = datetime.now().date().isoformat()
        db["stats"]["daily"][today] = db["stats"]["daily"].get(today, 0) + 1
        hist = user.setdefault("history", [])
        hist.append({"query": text, "time": datetime.now().isoformat()})
        user["history"] = hist[-20:]
        ctx.user_data["results"]    = results
        ctx.user_data["last_query"] = text
        save_db(db)
        if not results:
            await msg.edit_text(tr(lang,"not_found"), reply_markup=back_kb(lang), parse_mode=ParseMode.HTML)
            return
        model = results[0]
        saved = _is_saved(user, model)
        await msg.edit_text(_model_text(lang,results,0), reply_markup=results_kb(lang,results,0,saved), parse_mode=ParseMode.HTML)
        return

    # Bosh menyu
    extra = db["settings"].get("welcome_extra","")
    txt   = tr(lang,"welcome") + (f"\n\n📣 {extra}" if extra else "")
    await update.message.reply_text(txt, reply_markup=main_kb(lang), parse_mode=ParseMode.HTML)


async def channel_post_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Kuzatilayotgan TG kanaldan yangi post → avtomatik indekslash."""
    msg = update.channel_post
    if not msg:
        return
    chat_user = (msg.chat.username or "").lower()
    db = load_db()
    tracked = [s.get("username","").lower() for s in db["sources"].get("tgchannel",[]) if s.get("enabled",True)]
    if chat_user not in tracked:
        return

    caption = (msg.caption or msg.text or "").strip()
    if not caption:
        return

    # URL topish
    url = ""
    if msg.entities:
        for ent in msg.entities or []:
            if ent.type in ("url","text_link"):
                url = getattr(ent,"url","") or caption[ent.offset:ent.offset+ent.length]
                break
    if not url:
        found = re.findall(r"https?://\S+", caption)
        if found:
            url = found[0]

    # Format
    fmt_found = re.findall(r"\b(FBX|OBJ|MAX|GLB|C4D|SKP|DAE)\b", caption.upper())
    fmt = " / ".join(set(fmt_found)) if fmt_found else "FBX/OBJ"

    name = caption.split("\n")[0][:80].strip()
    tags = list(set(normalize(name).split()))

    model = {"name":name,"url":url,"format":fmt,"tags":tags,"category":"","source":f"@{chat_user}"}
    indexed = db.setdefault("indexed_models",[])
    if url and any(m.get("url")==url for m in indexed):
        return
    indexed.append(model)
    if len(indexed) > 50000:
        db["indexed_models"] = indexed[-50000:]
    save_db(db)
    logger.info(f"Indexed @{chat_user}: {name}")


# ─────────────────────────────────────────────────────
# 👮  ADMIN KOMANDALARI
# ─────────────────────────────────────────────────────
def admin_only(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if uid not in ADMIN_IDS:
            db   = load_db()
            user = get_user(db, uid)
            await update.message.reply_text(tr(user.get("lang","uz"),"admin_only"))
            return
        return await func(update, ctx)
    wrapper.__name__ = func.__name__
    return wrapper


@admin_only
async def cmd_addsource(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /addsource gdrive  Nom | https://docs.google.com/spreadsheets/.../pub?output=csv
    /addsource tgchannel @kanal_username
    /addsource url     Nom | https://example.com/models.json
    """
    db   = load_db()
    args = " ".join(ctx.args).strip() if ctx.args else ""
    if not args:
        await update.message.reply_text(
            "📡 <b>Manba qo'shish:</b>\n\n"
            "<b>Google Drive CSV:</b>\n"
            "<code>/addsource gdrive Mening Bazam | https://docs.google.com/.../pub?output=csv</code>\n\n"
            "<b>Telegram kanal:</b>\n"
            "<code>/addsource tgchannel @mening_kanalim</code>\n\n"
            "<b>Ixtiyoriy JSON URL:</b>\n"
            "<code>/addsource url Boshqa Baza | https://example.com/models.json</code>\n\n"
            "📌 Google Drive: Fayl → Nashr etish → CSV sifatida URL oling",
            parse_mode=ParseMode.HTML
        )
        return
    parts    = args.split(None, 1)
    src_type = parts[0].lower()
    if src_type == "tgchannel":
        if len(parts) < 2:
            await update.message.reply_text("Misol: /addsource tgchannel @mening_kanalim")
            return
        uname = parts[1].strip().lstrip("@")
        db["sources"]["tgchannel"].append({"username":uname,"enabled":True})
        save_db(db)
        await update.message.reply_text(
            f"✅ Telegram kanal qo'shildi: @{uname}\n\n"
            f"⚠️ Botni <b>@{uname}</b> kanalingizga <b>Admin</b> sifatida qo'shing,\n"
            "shunda yangi postlar avtomatik indekslanadi.",
            parse_mode=ParseMode.HTML
        )
    elif src_type in ("gdrive","url"):
        if "|" not in args:
            await update.message.reply_text("Format: /addsource gdrive Nom | https://...")
            return
        _, rest = args.split(None, 1)
        name, link = rest.split("|", 1)
        name = name.strip(); link = link.strip()
        key  = "gdrive" if src_type == "gdrive" else "custom_url"
        db["sources"][key].append({"name":name,"url":link,"enabled":True})
        save_db(db)
        await update.message.reply_text(f"✅ Manba qo'shildi: <b>{name}</b>\n🔗 {link}", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("Tur noto'g'ri. gdrive | tgchannel | url bo'lishi kerak.")


@admin_only
async def cmd_listsources(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db   = load_db()
    uid  = update.effective_user.id
    user = get_user(db, uid)
    lang = user.get("lang","uz")
    lines = tr(lang,"sources_list")
    has   = False
    for i, s in enumerate(db["sources"].get("gdrive",[])):
        lines += f"[{i}] 📊 GDrive: <b>{s['name']}</b> {'✅' if s.get('enabled') else '❌'}\n"
        has = True
    for i, s in enumerate(db["sources"].get("tgchannel",[])):
        lines += f"[{i}] 📢 TG: @{s['username']} {'✅' if s.get('enabled') else '❌'}\n"
        has = True
    for i, s in enumerate(db["sources"].get("custom_url",[])):
        lines += f"[{i}] 🌐 URL: <b>{s['name']}</b> {'✅' if s.get('enabled') else '❌'}\n"
        has = True
    if not has:
        lines += tr(lang,"no_sources")
    lines += f"\n\n📦 Lokal modellar: <b>{len(db.get('local_models',[]))}</b>"
    lines += f"\n📥 TG indeks: <b>{len(db.get('indexed_models',[]))}</b>"
    await update.message.reply_text(lines, parse_mode=ParseMode.HTML)


@admin_only
async def cmd_delsource(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/delsource gdrive|tgchannel|url <indeks>"""
    db = load_db()
    if len(ctx.args) < 2:
        await update.message.reply_text("Foydalanish: /delsource gdrive|tgchannel|url <indeks>")
        return
    src_type = ctx.args[0]
    try: idx = int(ctx.args[1])
    except ValueError:
        await update.message.reply_text("Indeks raqam bo'lishi kerak.")
        return
    key = "tgchannel" if src_type=="tgchannel" else ("gdrive" if src_type=="gdrive" else "custom_url")
    lst = db["sources"].get(key,[])
    if idx < len(lst):
        lst.pop(idx)
        save_db(db)
        await update.message.reply_text("✅ Manba o'chirildi.")
    else:
        await update.message.reply_text("❌ Bunday indeks topilmadi.")


@admin_only
async def cmd_refreshsources(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    db["cache_updated"] = {}
    save_db(db)
    user = get_user(db, update.effective_user.id)
    await update.message.reply_text(tr(user.get("lang","uz"),"cache_refreshed"))


@admin_only
async def cmd_addmodel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /addmodel Model nomi | https://link | FBX | tag1 tag2 tag3
    """
    db   = load_db()
    user = get_user(db, update.effective_user.id)
    lang = user.get("lang","uz")
    args = " ".join(ctx.args).strip() if ctx.args else ""
    if not args or "|" not in args:
        await update.message.reply_text(
            "📦 <b>Model qo'shish:</b>\n"
            "<code>/addmodel Model nomi | https://link | FBX | tag1 tag2</code>\n\n"
            "Misol:\n"
            "<code>/addmodel Modern Sofa | https://sketchfab.com/... | FBX | sofa furniture</code>",
            parse_mode=ParseMode.HTML
        )
        return
    parts = [p.strip() for p in args.split("|")]
    name  = parts[0] if len(parts)>0 else "Unknown"
    link  = parts[1] if len(parts)>1 else ""
    fmt   = parts[2].upper() if len(parts)>2 else "FBX/OBJ"
    tags  = parts[3].split() if len(parts)>3 else normalize(name).split()
    db.setdefault("local_models",[]).append({
        "name":name,"url":link,"format":fmt,"tags":tags,"category":"","source":"Snap3D Local"
    })
    save_db(db)
    await update.message.reply_text(tr(lang,"model_added",name=name))


@admin_only
async def cmd_uploaddb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """JSON fayl yuklash: [{name,url,format,tags,category}]"""
    await update.message.reply_text(
        "📤 JSON faylni yuboring.\n"
        "Format: <code>[{\"name\":\"Sofa\",\"url\":\"https://...\",\"format\":\"FBX\",\"tags\":[\"sofa\"]}]</code>",
        parse_mode=ParseMode.HTML
    )
    ctx.user_data["awaiting_db_upload"] = True


async def doc_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db  = load_db()
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        return
    if not ctx.user_data.pop("awaiting_db_upload", False):
        return
    doc  = update.message.document
    file = await ctx.bot.get_file(doc.file_id)
    raw  = await file.download_as_bytearray()
    try:
        models = json.loads(raw.decode("utf-8"))
        if not isinstance(models, list):
            await update.message.reply_text("❌ JSON list bo'lishi kerak.")
            return
        count = 0
        for item in models:
            if item.get("name"):
                item.setdefault("source","Snap3D Local")
                db.setdefault("local_models",[]).append(item)
                count += 1
        save_db(db)
        await update.message.reply_text(f"✅ {count} ta model qo'shildi. Jami: {len(db['local_models'])}")
    except Exception as e:
        await update.message.reply_text(f"❌ Xato: {e}")


@admin_only
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db    = load_db()
    s     = db["stats"]
    today = datetime.now().date().isoformat()
    yest  = (datetime.now()-timedelta(1)).date().isoformat()
    prems = sum(1 for u in db["users"].values() if u.get("premium"))
    await update.message.reply_text(
        "📊 <b>Snap3D Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{len(db['users'])}</b>\n"
        f"⭐ Premium: <b>{prems}</b>\n"
        f"🚫 Bloklangan: <b>{len(db.get('banned',[]))}</b>\n\n"
        f"🔍 Jami qidiruvlar: <b>{s.get('total_searches',0)}</b>\n"
        f"📅 Bugun: <b>{s.get('daily',{}).get(today,0)}</b>\n"
        f"📅 Kecha: <b>{s.get('daily',{}).get(yest,0)}</b>\n\n"
        f"📦 Lokal modellar: <b>{len(db.get('local_models',[]))}</b>\n"
        f"📥 TG indeks: <b>{len(db.get('indexed_models',[]))}</b>\n"
        f"📡 Manbalar: gdrive={len(db['sources'].get('gdrive',[]))}, "
        f"tg={len(db['sources'].get('tgchannel',[]))}, "
        f"url={len(db['sources'].get('custom_url',[]))}",
        parse_mode=ParseMode.HTML
    )


@admin_only
async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db   = load_db()
    user = get_user(db, update.effective_user.id)
    lang = user.get("lang","uz")
    ctx.user_data["awaiting_broadcast"] = True
    await update.message.reply_text(tr(lang,"broadcast_prompt"))


@admin_only
async def cmd_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    t_ = ctx.args[0] if ctx.args else ""
    if not t_:
        await update.message.reply_text("Foydalanish: /ban <user_id>")
        return
    if t_ not in db.get("banned",[]):
        db.setdefault("banned",[]).append(t_)
        save_db(db)
    await update.message.reply_text(f"✅ Bloklandi: {t_}")


@admin_only
async def cmd_unban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    t_ = ctx.args[0] if ctx.args else ""
    if t_ in db.get("banned",[]):
        db["banned"].remove(t_)
        save_db(db)
    await update.message.reply_text(f"✅ Blok olib tashlandi: {t_}")


@admin_only
async def cmd_givepremium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    if len(ctx.args) < 2:
        await update.message.reply_text("Foydalanish: /givepremium <user_id> <kunlar>")
        return
    uid_s, days_s = ctx.args[0], ctx.args[1]
    if uid_s not in db["users"]:
        await update.message.reply_text("Foydalanuvchi topilmadi.")
        return
    db["users"][uid_s]["premium"]       = True
    db["users"][uid_s]["premium_until"] = (datetime.now()+timedelta(days=int(days_s))).isoformat()
    save_db(db)
    await update.message.reply_text(f"✅ {uid_s} ga {days_s} kunlik premium berildi.")


@admin_only
async def cmd_setprice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("Foydalanish: /setprice <stars>")
        return
    db["settings"]["premium_price_stars"] = int(ctx.args[0])
    save_db(db)
    await update.message.reply_text(f"✅ Premium narxi: {ctx.args[0]} Stars")


@admin_only
async def cmd_setlimit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("Foydalanish: /setlimit <son>")
        return
    db["settings"]["free_daily_limit"] = int(ctx.args[0])
    save_db(db)
    await update.message.reply_text(f"✅ Kunlik bepul limit: {ctx.args[0]}")


@admin_only
async def cmd_setwelcome(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db   = load_db()
    text = " ".join(ctx.args) if ctx.args else ""
    db["settings"]["welcome_extra"] = text
    save_db(db)
    await update.message.reply_text(f"✅ Qo'shimcha xabar: {text or '(o\\'chirildi)'}")


@admin_only
async def cmd_maintenance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db  = load_db()
    cur = db["settings"].get("maintenance",False)
    db["settings"]["maintenance"] = not cur
    save_db(db)
    await update.message.reply_text(f"🔧 Maintenance: {'ON ✅' if not cur else 'OFF ❌'}")


@admin_only
async def cmd_adminhelp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👮 <b>Admin komandalari:</b>\n\n"
        "<b>── Manbalar ──</b>\n"
        "/addsource — manba qo'shish (ko'rsatma)\n"
        "/listsources — barcha manbalar\n"
        "/delsource gdrive|tgchannel|url &lt;indeks&gt;\n"
        "/refreshsources — keshni yangilash\n\n"
        "<b>── Modellar ──</b>\n"
        "/addmodel Nom | URL | FBX | tag1 tag2\n"
        "/uploaddb — JSON fayl yuklash\n\n"
        "<b>── Foydalanuvchilar ──</b>\n"
        "/stats — statistika\n"
        "/broadcast — xabar tarqatish\n"
        "/ban &lt;id&gt; — bloklash\n"
        "/unban &lt;id&gt; — blokdan chiqarish\n"
        "/givepremium &lt;id&gt; &lt;kun&gt;\n\n"
        "<b>── Sozlamalar ──</b>\n"
        "/setprice &lt;stars&gt;\n"
        "/setlimit &lt;son&gt;\n"
        "/setwelcome &lt;matn&gt;\n"
        "/maintenance\n"
        "/adminhelp",
        parse_mode=ParseMode.HTML
    )


# Foydalanuvchi komandalar (slash)
async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db   = load_db()
    uid  = update.effective_user.id
    user = get_user(db, uid)
    lang = user.get("lang","uz")
    err  = check_access(db, uid)
    if err:
        await update.message.reply_text(tr(lang,err))
        return
    q_str = " ".join(ctx.args).strip() if ctx.args else ""
    if not q_str:
        ctx.user_data["awaiting_search"] = True
        await update.message.reply_text(tr(lang,"search_prompt"), parse_mode=ParseMode.HTML)
        return
    await update.message.reply_text(tr(lang,"searching"), parse_mode=ParseMode.HTML)
    await _do_search(update, ctx, db, user, uid, lang, q_str)


async def cmd_categories(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db   = load_db()
    user = get_user(db, update.effective_user.id)
    lang = user.get("lang","uz")
    await update.message.reply_text(tr(lang,"cats_title"), reply_markup=cats_kb(db,lang), parse_mode=ParseMode.HTML)


async def cmd_favorites(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db   = load_db()
    user = get_user(db, update.effective_user.id)
    lang = user.get("lang","uz")
    favs = user.get("favorites",[])
    if not favs:
        await update.message.reply_text(tr(lang,"favs_empty"), parse_mode=ParseMode.HTML)
        return
    lines = tr(lang,"favs_title")
    for i, fav in enumerate(favs[-10:],1):
        u_ = fav.get("url","")
        lines += (f"{i}. <a href='{u_}'>{fav.get('name','?')}</a>\n" if u_ else f"{i}. {fav.get('name','?')}\n")
    await update.message.reply_text(lines, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def cmd_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db   = load_db()
    user = get_user(db, update.effective_user.id)
    lang = user.get("lang","uz")
    hist = user.get("history",[])
    if not hist:
        await update.message.reply_text(tr(lang,"hist_empty"))
        return
    lines = tr(lang,"hist_title")
    for h in reversed(hist[-10:]):
        lines += f"• <code>{h['query']}</code> — {h.get('time','')[:10]}\n"
    await update.message.reply_text(lines, parse_mode=ParseMode.HTML)


async def cmd_premium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db    = load_db()
    user  = get_user(db, update.effective_user.id)
    lang  = user.get("lang","uz")
    price = db["settings"].get("premium_price_stars",150)
    await update.message.reply_text(tr(lang,"premium_info",price=price),
        reply_markup=premium_kb(lang,price), parse_mode=ParseMode.HTML)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db   = load_db()
    user = get_user(db, update.effective_user.id)
    lang = user.get("lang","uz")
    await update.message.reply_text(tr(lang,"help"), parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db   = load_db()
    user = get_user(db, update.effective_user.id)
    lang = user.get("lang","uz")
    await update.message.reply_text(tr(lang,"settings_title"), reply_markup=settings_kb(lang), parse_mode=ParseMode.HTML)


# ─────────────────────────────────────────────────────
# 🚀  ISHGA TUSHIRISH
# ─────────────────────────────────────────────────────
async def on_startup(app: Application):
    await app.bot.set_my_commands(CMDS["uz"], scope=BotCommandScopeDefault())
    logger.info("✅ Snap3D bot ishga tushdi!")


def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("\n" + "="*60)
        print("  ❌  BOT_TOKEN o'rnatilmagan!")
        print("  snap3d_bot.py ichida BOT_TOKEN ni o'zgartiring.")
        print("  BotFather: https://t.me/BotFather")
        print("="*60 + "\n")
        return

    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()

    # ── Foydalanuvchi komandalar
    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("search",     cmd_search))
    app.add_handler(CommandHandler("categories", cmd_categories))
    app.add_handler(CommandHandler("favorites",  cmd_favorites))
    app.add_handler(CommandHandler("history",    cmd_history))
    app.add_handler(CommandHandler("premium",    cmd_premium))
    app.add_handler(CommandHandler("help",       cmd_help))
    app.add_handler(CommandHandler("settings",   cmd_settings))

    # ── Admin komandalar
    app.add_handler(CommandHandler("addsource",      cmd_addsource))
    app.add_handler(CommandHandler("listsources",    cmd_listsources))
    app.add_handler(CommandHandler("delsource",      cmd_delsource))
    app.add_handler(CommandHandler("refreshsources", cmd_refreshsources))
    app.add_handler(CommandHandler("addmodel",       cmd_addmodel))
    app.add_handler(CommandHandler("uploaddb",       cmd_uploaddb))
    app.add_handler(CommandHandler("stats",          cmd_stats))
    app.add_handler(CommandHandler("broadcast",      cmd_broadcast))
    app.add_handler(CommandHandler("ban",            cmd_ban))
    app.add_handler(CommandHandler("unban",          cmd_unban))
    app.add_handler(CommandHandler("givepremium",    cmd_givepremium))
    app.add_handler(CommandHandler("setprice",       cmd_setprice))
    app.add_handler(CommandHandler("setlimit",       cmd_setlimit))
    app.add_handler(CommandHandler("setwelcome",     cmd_setwelcome))
    app.add_handler(CommandHandler("maintenance",    cmd_maintenance))
    app.add_handler(CommandHandler("adminhelp",      cmd_adminhelp))

    # ── Media va matn
    app.add_handler(MessageHandler(filters.PHOTO,                    photo_handler))
    app.add_handler(MessageHandler(filters.Document.ALL,             doc_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,  text_handler))
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POSTS, channel_post_handler))

    # ── Callback tugmalar
    app.add_handler(CallbackQueryHandler(cb_handler))

    logger.info("🚀 Snap3D ishga tushmoqda...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
