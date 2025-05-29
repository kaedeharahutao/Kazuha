from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import os
import logging

router = Router()

# Ganti dengan username admin kamu (tanpa @)
ADMIN_USERNAMES = ["KazuhaID02"]  # contoh: ["KazuhaID02"]

@router.message(Command("clear_vcf"), F.chat.type == "private")
async def clear_vcf_handler(message: types.Message, state: FSMContext):
    username = (message.from_user.username or "").lower()
    if username not in [u.lower() for u in ADMIN_USERNAMES]:
        await message.answer("Kamu tidak punya akses untuk perintah ini.")
        return

    data_dir = "data"
    deleted = 0
    for fname in os.listdir(data_dir):
        if fname.lower().endswith(".vcf"):
            try:
                os.remove(os.path.join(data_dir, fname))
                deleted += 1
            except Exception as e:
                logging.error(f"Gagal hapus {fname}: {e}")
    await message.answer(f"Berhasil menghapus {deleted} file .vcf di folder data.")