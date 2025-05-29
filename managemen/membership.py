from aiogram import Bot, types

GROUP_LINK = "https://t.me/+RbL9QMFO47M4YmI1"
CHANNEL_LINK = "https://t.me/+hW94C6eF1Bk1Y2I1"
GROUP_ID = -1002674942804
CHANNEL_ID = -1002314507632

# Simpan message_id pesan join per user (hanya untuk sesi bot berjalan)
join_message_ids = {}

async def check_membership(bot: Bot, user_id: int):
    in_group = False
    in_channel = False
    try:
        gr = await bot.get_chat_member(GROUP_ID, user_id)
        if gr.status in ("member", "administrator", "creator"):
            in_group = True
    except Exception:
        pass
    try:
        ch = await bot.get_chat_member(CHANNEL_ID, user_id)
        if ch.status in ("member", "administrator", "creator"):
            in_channel = True
    except Exception:
        pass
    return in_group, in_channel

async def send_membership_message(message: types.Message, in_group: bool, in_channel: bool):
    keyboard = []
    if not in_group:
        keyboard.append([types.InlineKeyboardButton(text="👥 Gabung Grup", url=GROUP_LINK)])
    if not in_channel:
        keyboard.append([types.InlineKeyboardButton(text="📢 Join Channel", url=CHANNEL_LINK)])

    if not in_group and not in_channel:
        text = (
            "🚫 Kamu belum gabung grup & channel!\n"
            "Setelah join, balik lagi dan ketik /start👍\n\n"
            "Yuk gabung dulu biar bisa pakai bot ini 👇"
        )
    elif not in_group:
        text = (
            "👥 Gabung grup dulu ya biar bisa lanjut.\n"
            "Setelah join, balik lagi dan ketik /start👍\n\n"
            "Klik tombol di bawah ini 👇"
        )
    elif not in_channel:
        text = (
            "📢 Join channel dulu ya biar bisa lanjut.\n"
            "Setelah join, balik lagi dan ketik /start👍\n\n"
            "Klik tombol di bawah ini 👇"
        )

    else:
        return

    sent = await message.answer(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard))
    # Simpan message_id pesan join terakhir user
    join_message_ids[message.from_user.id] = sent.message_id

async def delete_join_message(bot: Bot, user_id: int, chat_id: int):
    msg_id = join_message_ids.get(user_id)
    if msg_id:
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
        join_message_ids.pop(user_id, None)