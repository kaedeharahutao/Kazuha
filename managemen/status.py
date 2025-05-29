from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import os
import logging

router = Router()

# Ganti dengan username admin kamu (tanpa @)
ADMIN_USERNAMES = ["KazuhaID02"]

USER_LOG_FILE = "managemen/user_log.txt"

def save_user(username):
    if not username:
        return
    username = username.lower()
    os.makedirs("managemen", exist_ok=True)
    try:
        # Simpan username unik saja
        if os.path.exists(USER_LOG_FILE):
            with open(USER_LOG_FILE, "r", encoding="utf-8") as f:
                users = set(line.strip().lower() for line in f if line.strip())
        else:
            users = set()
        if username not in users:
            with open(USER_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(username + "\n")
    except Exception as e:
        logging.error(f"Gagal simpan user log: {e}")

@router.message(Command("status"))
async def status_handler(message: types.Message, state: FSMContext):
    username = (message.from_user.username or "").lower()
    if username not in [u.lower() for u in ADMIN_USERNAMES]:
        await message.answer("Kamu tidak punya akses untuk perintah ini.")
        return

    # Baca user log
    if not os.path.exists(USER_LOG_FILE):
        await message.answer("Belum ada pengguna yang tercatat.")
        return

    with open(USER_LOG_FILE, "r", encoding="utf-8") as f:
        users = [line.strip() for line in f if line.strip()]
    if not users:
        await message.answer("Belum ada pengguna yang tercatat.")
        return

    msg = f"{len(users)} pengguna aktif:\n"
    for i, user in enumerate(users, 1):
        msg += f"{i}. @{user}\n"
    await message.answer(msg.strip())