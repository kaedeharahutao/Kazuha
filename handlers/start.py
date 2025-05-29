from aiogram import Router, types, F
from aiogram.filters import Command
import logging
from aiogram.fsm.context import FSMContext
from managemen.status import save_user
from managemen.membership import check_membership, send_membership_message, delete_join_message
from managemen.message import save_user_for_broadcast

router = Router()

def log_user(message: types.Message):
    logging.info(f"user: {message.text}")

def log_bot(text: str):
    logging.info(f"bot: {text}")

fitur = [
    "/to_vcf      - konversi file ke .vcf",
    "/to_txt      - konversi file ke .txt",
    "/admin       - fitur admin/navy",
    "/manual      - input kontak manual",
    "/add         - tambah kontak ke .vcf",
    "/delete      - hapus kontak dari file",
    "/renamectc   - ganti nama kontak",
    "/renamefile  - ganti nama file",
    "/merge       - gabungkan file",
    "/split       - pecah file",
    "/count       - hitung jumlah kontak",
    "/nodup       - hapus kontak duplikat",
]

keyboard = types.ReplyKeyboardMarkup(
    keyboard=[
        [
            types.KeyboardButton(text="/to_vcf"),
            types.KeyboardButton(text="/to_txt"),
            types.KeyboardButton(text="/admin"),
            types.KeyboardButton(text="/manual"),
        ],
        [
            types.KeyboardButton(text="/add"),
            types.KeyboardButton(text="/delete"),
            types.KeyboardButton(text="/renamectc"),
            types.KeyboardButton(text="/renamefile"),
        ],
        [
            types.KeyboardButton(text="/merge"),
            types.KeyboardButton(text="/split"),
            types.KeyboardButton(text="/count"),
            types.KeyboardButton(text="/nodup"),
        ],
        [
            types.KeyboardButton(text="/help"),
        ],
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

INFO_BOT = "*Bot milik @KazuhaID02*\n\n"

@router.message(Command("start"), F.chat.type == "private")
async def start_global(message: types.Message, state: FSMContext):
    await state.clear()
    await start_handler(message, state)

@router.message(Command("to_vcf"), F.chat.type == "private")
async def to_vcf_from_start(message: types.Message, state: FSMContext):
    await state.clear()
    in_group, in_channel = await check_membership(message.bot, message.from_user.id)
    if not (in_group and in_channel):
        await send_membership_message(message, in_group, in_channel)
        return
    await delete_join_message(message.bot, message.from_user.id, message.chat.id)
    from handlers.to_vcf import to_vcf_start
    await to_vcf_start(message, state)

@router.message(Command("to_txt"), F.chat.type == "private")
async def to_txt_from_start(message: types.Message, state: FSMContext):
    await state.clear()
    in_group, in_channel = await check_membership(message.bot, message.from_user.id)
    if not (in_group and in_channel):
        await send_membership_message(message, in_group, in_channel)
        return
    await delete_join_message(message.bot, message.from_user.id, message.chat.id)
    from handlers.to_txt import to_txt_start
    await to_txt_start(message, state)

@router.message(Command("help"), F.chat.type == "private")
async def help_global(message: types.Message, state: FSMContext):
    await state.clear()
    await help_handler(message, state)

@router.message(Command("start"), F.chat.type == "private")
async def start_handler(message: types.Message, state: FSMContext):
    in_group, in_channel = await check_membership(message.bot, message.from_user.id)
    if not (in_group and in_channel):
        await send_membership_message(message, in_group, in_channel)
        return
    await delete_join_message(message.bot, message.from_user.id, message.chat.id)
    save_user(message.from_user.username)
    save_user_for_broadcast(message.from_user)  # <-- PENTING: simpan user id
    nama = message.from_user.full_name or message.from_user.username or "pengguna"
    bot_msg = (
        f"Hallo *{nama}*, selamat datang di bot\n"
        f"*Fitur bot:*\n"
        "```\n" +
        "\n".join(fitur) +
        "\n```\n" +
        INFO_BOT
    )
    await message.answer(bot_msg, parse_mode="Markdown", reply_markup=keyboard)
    log_bot(bot_msg)

@router.message(Command("help"), F.chat.type == "private")
async def help_handler(message: types.Message, state: FSMContext):
    in_group, in_channel = await check_membership(message.bot, message.from_user.id)
    if not (in_group and in_channel):
        await send_membership_message(message, in_group, in_channel)
        return
    await delete_join_message(message.bot, message.from_user.id, message.chat.id)
    log_user(message)
    bot_msg = (
        "*Fitur bot:*\n"
        "```\n" +
        "\n".join(fitur) +
        "\n```\n" +
        INFO_BOT
    )
    await message.answer(bot_msg, parse_mode="Markdown", reply_markup=keyboard)
    log_bot(bot_msg)