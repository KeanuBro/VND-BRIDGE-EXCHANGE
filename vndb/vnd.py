import asyncio
import logging
import sqlite3
import datetime
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile

# === НАСТРОЙКИ ===
BOT_TOKEN = "8938074523:AAGVPyZCPT0GEKNCeHTPnYVn719LrrX4c-c"
ADMIN_CHAT_ID = 5653910526

# === ПУТИ К КАРТИНКАМ (Папка img должна лежать рядом с bot.py) ===
IMG_MAIN = "img/main.jpg"
IMG_CALC = "img/calc.jpg"
IMG_DELIVERY = "img/delivery.jpg"
IMG_SUCCESS = "img/success.jpg"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === БАЗА ДАННЫХ (Оптимизированная для скорости) ===
def get_db():
    conn = sqlite3.connect("exchange.db", timeout=10)
    # Включаем WAL-режим для мгновенного чтения/записи без блокировок
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            currency TEXT,
            min_sum REAL,
            max_sum REAL,
            rate REAL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            currency TEXT,
            amount_in REAL,
            amount_out REAL,
            delivery_method TEXT,
            details TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cur.execute("SELECT COUNT(*) FROM rates")
    if cur.fetchone()[0] == 0:
        test_rates = [
            ("RUB_VND", 2000, 9999, 286),
            ("RUB_VND", 10000, 29999, 290),
            ("RUB_VND", 30000, 1000000, 299),
            ("USDT_VND", 1, 999999, 25300),
            ("USD_VND", 1, 999999, 25000)
        ]
        cur.executemany("INSERT INTO rates (currency, min_sum, max_sum, rate) VALUES (?, ?, ?, ?)", test_rates)
    conn.commit()
    conn.close()

init_db()

# === FSM СОСТОЯНИЯ ===
class ExchangeFlow(StatesGroup):
    waiting_for_amount = State()
    waiting_for_details = State()
    live_support = State()

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def get_greeting():
    hour = datetime.datetime.now().hour
    if 5 <= hour < 12: return "🌅 Доброе утро!"
    elif 12 <= hour < 18: return "☀️ Добрый день!"
    elif 18 <= hour < 23: return "🌇 Добрый вечер!"
    else: return "🌙 Доброй ночи!"

def get_current_rates_text():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT currency, min_sum, max_sum, rate FROM rates ORDER BY currency, min_sum")
    rates = cur.fetchall()
    conn.close()
    
    text = "📊 <b>Актуальные курсы обмена:</b>\n"
    for r in rates:
        curr, m_min, m_max, rate = r
        if curr == "RUB_VND":
            text += f"🇷🇺 RUB: <b>{m_min:,.0f} - {m_max:,.0f} ₽</b> ➡️ Курс: <b>{rate}</b>\n"
        elif curr == "USDT_VND":
            text += f"🪙 USDT ➡️ Курс: <b>{rate}</b>\n"
        elif curr == "USD_VND":
            text += f"💵 USD ➡️ Курс: <b>{rate}</b>\n"
    return text.replace(',', ' ')

# Быстрая отправка шагов
async def send_step(callback_or_message, photo_path, text, markup):
    if os.path.exists(photo_path):
        photo = FSInputFile(photo_path)
        if isinstance(callback_or_message, types.CallbackQuery):
            try:
                await callback_or_message.message.delete()
            except:
                pass
            await callback_or_message.message.answer_photo(photo=photo, caption=text, parse_mode="HTML", reply_markup=markup)
        else:
            await callback_or_message.answer_photo(photo=photo, caption=text, parse_mode="HTML", reply_markup=markup)
    else:
        if isinstance(callback_or_message, types.CallbackQuery):
            try:
                await callback_or_message.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
            except TelegramBadRequest:
                pass
        else:
            await callback_or_message.answer(text, parse_mode="HTML", reply_markup=markup)

# === ГЛАВНОЕ МЕНЮ ===
async def send_main_menu(message: types.Message | types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="🌐 Наше сообщество", url="https://t.me/vnd_bridge_service")
    builder.button(text="👤 Личный кабинет", callback_data="cabinet")
    builder.button(text="🇷🇺 RUB ➡️ VND", callback_data="dir_RUB_VND")
    builder.button(text="🪙 USDT ➡️ VND", callback_data="dir_USDT_VND")
    builder.button(text="💵 USD (Наличные) ➡️ VND", callback_data="dir_USD_VND")
    builder.button(text="💬 Связь с оператором", callback_data="support")
    
    if message.from_user.id == ADMIN_CHAT_ID:
        builder.button(text="🛠 Админ-панель", callback_data="admin_panel_btn")
    builder.adjust(1)
    
    text = (
        f"{get_greeting()}\n\n"
        f"🇻🇳 Добро пожаловать в <b>VND Bridge EXCHANGE</b>!\n"
        f"Ваш надежный сервис обмена валют во Вьетнаме.\n\n"
        f"{get_current_rates_text()}\n"
        f"👇 <i>Выберите нужное действие ниже:</i>"
    )
    
    await send_step(message, IMG_MAIN, text, builder.as_markup())

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await send_main_menu(message)

@dp.callback_query(F.data == "back_to_start")
async def back_to_start_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await send_main_menu(callback)
    await callback.answer()

# === ЛИЧНЫЙ КАБИНЕТ И ИСТОРИЯ ===
@dp.callback_query(F.data == "cabinet")
async def personal_cabinet(callback: types.CallbackQuery):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM orders WHERE user_id = ? AND status != 'CANCELLED'", (callback.from_user.id,))
    orders_count = cur.fetchone()[0]
    conn.close()

    text = (
        f"👤 <b>Личный кабинет</b>\n\n"
        f"🆔 Ваш ID: <code>{callback.from_user.id}</code>\n"
        f"✅ Успешных обменов: <b>{orders_count}</b>\n\n"
        f"<i>Здесь вы можете посмотреть историю ваших заявок.</i>"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="📜 История обменов", callback_data="history")
    builder.button(text="🔙 Назад в меню", callback_data="back_to_start")
    builder.adjust(1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except TelegramBadRequest:
        pass
    await callback.answer()

@dp.callback_query(F.data == "history")
async def exchange_history(callback: types.CallbackQuery):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, currency, amount_in, amount_out, status FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 5", (callback.from_user.id,))
    orders = cur.fetchall()
    conn.close()

    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 В кабинет", callback_data="cabinet")
    builder.button(text="🔙 В главное меню", callback_data="back_to_start")
    builder.adjust(1)

    if not orders:
        text = "📭 У вас пока нет истории обменов."
    else:
        text = "📜 <b>Ваши последние 5 заявок:</b>\n\n"
        for o in orders:
            order_id, curr_full, a_in, a_out, status = o
            curr = curr_full.split('_')[0]
            
            if status == "NEW":
                status_icon = "⏳ В обработке"
            elif status == "CANCELLED":
                status_icon = "❌ Отменена"
            else:
                status_icon = "✅ Выполнена"

            a_in_str = f"{a_in:,.0f}".replace(',', ' ')
            a_out_str = f"{a_out:,.0f}".replace(',', ' ')
            
            text += f"<b>Заявка #{order_id}</b> | {status_icon}\nОтдали: {a_in_str} {curr}\nПолучили: {a_out_str} VND\n〰️〰️〰️〰️〰️〰️〰️\n"

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except TelegramBadRequest:
        pass
    await callback.answer()

# === ЛОГИКА ОБМЕНА ===
@dp.callback_query(F.data.startswith("dir_"))
async def process_direction(callback: types.CallbackQuery, state: FSMContext):
    direction = callback.data.replace("dir_", "")
    await state.update_data(direction=direction)
    
    currency_name = direction.split('_')[0]
    
    if currency_name == "RUB":
        min_sum_text = "2 000"
    elif currency_name == "USD":
        min_sum_text = "200"
    else:
        min_sum_text = "10"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад в меню", callback_data="back_to_start")
    
    text = (
        f"💱 Выбрано направление: <b>{currency_name} ➡️ VND</b>\n\n"
        f"✍️ <b>Введите сумму</b>, которую хотите обменять (только число).\n\n"
        f"<i>Минимальная сумма: {min_sum_text} {currency_name}</i>"
    )
    
    await send_step(callback, IMG_CALC, text, builder.as_markup())
    await state.set_state(ExchangeFlow.waiting_for_amount)
    await callback.answer()

@dp.message(ExchangeFlow.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.').replace(' ', ''))
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите корректное число (например: 15000).")
        return

    data = await state.get_data()
    direction = data['direction']
    currency_name = direction.split('_')[0]

    if currency_name == "RUB" and amount < 2000:
        await message.answer("⚠️ Минимальная сумма обмена: 2 000 RUB. Введите сумму больше.")
        return
    if currency_name == "USD" and amount < 200:
        await message.answer("⚠️ Минимальная сумма обмена: 200 USD. Введите сумму больше.")
        return
    if currency_name == "USDT" and amount < 10:
        await message.answer("⚠️ Минимальная сумма обмена: 10 USDT. Введите сумму больше.")
        return

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT rate FROM rates WHERE currency = ? AND min_sum <= ? AND max_sum >= ?", (direction, amount, amount))
    result = cur.fetchone()
    conn.close()

    if not result:
        await message.answer("❌ Для данной суммы курс не установлен. Измените сумму или напишите оператору.")
        return

    rate = result[0]
    amount_out = amount * rate
    await state.update_data(amount_in=amount, amount_out=amount_out, rate=rate)

    builder = InlineKeyboardBuilder()
    builder.button(text="🏧 Банкомат Vietcombank", callback_data="del_atm")
    
    if (currency_name == "RUB" and amount >= 10000) or \
       (currency_name == "USD" and amount >= 200) or \
       (currency_name == "USDT" and amount >= 200):
        builder.button(text="🛵 Наличные курьером", callback_data="del_courier")
        
    builder.button(text="🏦 На вьетнамский счет", callback_data="del_account")
    builder.button(text="🔙 Назад", callback_data="back_to_amount")
    builder.adjust(1)

    a_in_str = f"{amount:,.0f}".replace(',', ' ')
    a_out_str = f"{amount_out:,.0f}".replace(',', ' ')

    text = (
        f"🔄 <b>Ваш расчет:</b>\n\n"
        f"📤 Вы отдаете: <b>{a_in_str} {currency_name}</b>\n"
        f"📥 Вы получаете: <b>{a_out_str} VND</b>\n"
        f"<i>(Применен курс: {rate})</i>\n\n"
        f"👇 <b>Выберите удобный способ получения:</b>"
    )
    
    await send_step(message, IMG_DELIVERY, text, builder.as_markup())

@dp.callback_query(F.data == "back_to_amount")
async def back_to_amount_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    direction = data.get('direction', 'RUB_VND')
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад в меню", callback_data="back_to_start")
    
    text = (
        f"💱 Направление: <b>{direction.split('_')[0]} ➡️ VND</b>\n\n"
        f"✍️ <b>Введите сумму обмена</b> (только число):"
    )
    await send_step(callback, IMG_CALC, text, builder.as_markup())
    await state.set_state(ExchangeFlow.waiting_for_amount)
    await callback.answer()

@dp.callback_query(F.data.startswith("del_"))
async def process_delivery(callback: types.CallbackQuery, state: FSMContext):
    method = callback.data
    if method == "del_atm":
        method_text = "Банкомат Vietcombank"
        instruction = (
            "🏧 <b>Снятие в банкомате Vietcombank (По всему Вьетнаму)</b>\n\n"
            "Вы присылаете свое местоположение, на экране банкомата жмете «Rút tiền bằng QR», "
            "скидываете нам фото QR-кода. Мы отправляем код подтверждения — и вы забираете VND.\n\n"
            "👉 <i>Напишите ваш город (например: Нячанг) для продолжения:</i>"
        )
    elif method == "del_courier":
        method_text = "Наличные курьером"
        instruction = (
            "🛵 <b>Доставка курьером (Нячанг и Камрань)</b>\n\n"
            "👉 <i>Укажите название отеля/заведения или прикрепите гео-точку, "
            "а также желаемое время доставки:</i>"
        )
    else:
        method_text = "Перевод на счет / Оплата услуг"
        instruction = (
            "🏦 <b>Перевод на счет или оплата услуг</b>\n\n"
            "Мы можем отправить донги на ваш счет или дистанционно оплатить за вас отель/ресторан.\n\n"
            "👉 <i>Пришлите скриншот QR-кода из приложения банка, либо укажите банк, номер счета и имя получателя:</i>"
        )
        
    await state.update_data(delivery=method_text)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад к выбору", callback_data="back_to_amount_from_del")
    
    try:
        await callback.message.edit_text(instruction, parse_mode="HTML", reply_markup=builder.as_markup())
    except TelegramBadRequest:
        pass
        
    await state.set_state(ExchangeFlow.waiting_for_details)
    await callback.answer()

@dp.callback_query(F.data == "back_to_amount_from_del")
async def back_to_calc(callback: types.CallbackQuery, state: FSMContext):
    await back_to_amount_handler(callback, state)

@dp.message(ExchangeFlow.waiting_for_details)
async def process_details(message: types.Message, state: FSMContext):
    details_text = ""
    if message.text:
        details_text = message.text
    elif message.location:
        details_text = f"📍 Отправлена гео-локация: {message.location.latitude}, {message.location.longitude}"
    elif message.photo:
        details_text = f"📸 Отправлено фото (Подпись: {message.caption or 'нет'})"
    else:
        details_text = "📎 Отправлен файл/контакт"

    data = await state.get_data()
    currency_name = data['direction'].split('_')[0]
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO orders (user_id, username, currency, amount_in, amount_out, delivery_method, details, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (message.from_user.id, message.from_user.username, data['direction'], data['amount_in'], data['amount_out'], data['delivery'], details_text, "NEW"))
    order_id = cur.lastrowid
    conn.commit()
    conn.close()

    a_in_str = f"{data['amount_in']:,.0f}".replace(',', ' ')
    a_out_str = f"{data['amount_out']:,.0f}".replace(',', ' ')

    admin_text = (
        f"🔔 <b>НОВАЯ ЗАЯВКА #{order_id}</b>\n\n"
        f"Отдает: {a_in_str} {currency_name}\n"
        f"Получает: {a_out_str} VND\n"
        f"Способ: {data['delivery']}\n"
        f"Детали (Текст): {details_text}\n"
        f"Клиент: @{message.from_user.username} (ID: {message.from_user.id})\n\n"
        f"👇 <i>Вложение от клиента переслано ниже:</i>"
    )
    await bot.send_message(ADMIN_CHAT_ID, admin_text, parse_mode="HTML")
    await message.forward(chat_id=ADMIN_CHAT_ID)

    payment_info = ""
    if currency_name == "RUB":
        payment_info = "\n🛡 <i>Оплата рублями осуществляется переводом по QR-коду СБП с любого банка. Платеж проходит как оплата услуги — безопасно и без блокировок.</i>\n"

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить заявку", callback_data=f"cancel_{order_id}")
    builder.button(text="💬 Связь с оператором", callback_data="support")
    builder.adjust(1)
    
    success_text = (
        f"✅ <b>Заявка #{order_id} успешно создана!</b>\n\n"
        f"Оператор свяжется с вами в течение 2 минут для проведения сделки.\n"
        f"{payment_info}"
    )
    
    await send_step(message, IMG_SUCCESS, success_text, builder.as_markup())
    await state.clear()

@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_order(callback: types.CallbackQuery):
    order_id = callback.data.split("_")[1]
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE orders SET status = 'CANCELLED' WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

    await bot.send_message(ADMIN_CHAT_ID, f"⚠️ <b>Заявка #{order_id} ОТМЕНЕНА клиентом!</b>", parse_mode="HTML")
    
    try:
        await callback.message.edit_text(f"❌ Заявка #{order_id} отменена.\nНажмите /start, чтобы создать новую.", parse_mode="HTML")
    except TelegramBadRequest:
        pass
    await callback.answer("Заявка отменена")

# === ПОДДЕРЖКА ===
@dp.callback_query(F.data == "support")
async def live_support_start(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Вернуться в меню", callback_data="back_to_start")
    
    text = (
        "💬 <b>Связь с оператором</b>\n\n"
        "Напишите ваш вопрос ниже, и оператор ответит вам в течение 2 минут прямо в этом чате:"
    )
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except TelegramBadRequest:
        pass
        
    await state.set_state(ExchangeFlow.live_support)
    await callback.answer()

@dp.message(ExchangeFlow.live_support)
async def forward_to_admin(message: types.Message):
    await bot.forward_message(chat_id=ADMIN_CHAT_ID, from_chat_id=message.chat.id, message_id=message.message_id)
    await message.answer("<i>Сообщение передано оператору 📩</i>", parse_mode="HTML")

@dp.message(F.reply_to_message & F.chat.id == ADMIN_CHAT_ID)
async def reply_to_client(message: types.Message):
    if message.reply_to_message.forward_from:
        client_id = message.reply_to_message.forward_from.id
        await bot.send_message(chat_id=client_id, text=f"👨‍💻 <b>Оператор VND Bridge:</b>\n{message.text}", parse_mode="HTML")

# === АДМИН ПАНЕЛЬ ===
@dp.callback_query(F.data == "admin_panel_btn")
async def admin_panel_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_CHAT_ID:
        await callback.answer("У вас нет доступа!", show_alert=True)
        return
        
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, currency, min_sum, max_sum, rate FROM rates")
    rates = cur.fetchall()
    conn.close()
    
    text = "🛠 <b>УПРАВЛЕНИЕ КУРСАМИ</b>\n\nТекущие настройки:\n"
    for r in rates:
        text += f"ID {r[0]}: {r[1]} | {r[2]:.0f} - {r[3]:.0f} | Курс: <b>{r[4]}</b>\n"
        
    text += "\n📝 <b>Как изменить курс:</b>\n"
    text += "Просто отправьте боту сообщение в формате:\n<code>/setrate [ID] [НОВЫЙ_КУРС]</code>\n"
    text += "<i>Пример: /setrate 1 295</i>"
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 В главное меню", callback_data="back_to_start")
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except TelegramBadRequest:
        pass
    await callback.answer()

@dp.message(Command("setrate"))
async def change_rate(message: types.Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    try:
        _, rate_id, new_rate = message.text.split()
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE rates SET rate = ? WHERE id = ?", (new_rate, rate_id))
        conn.commit()
        conn.close()
        await message.answer(f"✅ Курс для ID {rate_id} успешно изменен на {new_rate}!\nНажмите /start чтобы обновить меню.")
    except Exception:
        await message.answer("⚠️ Ошибка. Формат: /setrate ID НОВЫЙ_КУРС")

# === ЗАПУСК ===
async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())