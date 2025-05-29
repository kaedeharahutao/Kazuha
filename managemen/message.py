import os
import logging
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

router = Router()

ADMIN_USERNAMES = ["KazuhaID02"]  # Ganti dengan username admin kamu (tanpa @)
USER_DATA_FILE = "managemen/message.txt"

class MessageStates:
    waiting_message = "waiting_message"

def save_user_for_broadcast(user: types.User):
    os.makedirs("managemen", exist_ok=True)
    user_id = str(user.id)
    # Simpan hanya user_id (bukan username)
    if not os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
            f.write(user_id + "\n")
        return
    with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
        users = set(line.strip() for line in f if line.strip())
    if user_id not in users:
        with open(USER_DATA_FILE, "a", encoding="utf-8") as f:
            f.write(user_id + "\n")

@router.message(Command("message"), F.chat.type == "private")
async def message_start(message: types.Message, state: FSMContext):
    username = (message.from_user.username or "").lower()
    if username not in [u.lower() for u in ADMIN_USERNAMES]:
        await message.answer("❌ Hanya admin yang bisa pakai perintah ini.")
        return
    await state.set_state(MessageStates.waiting_message)
    await message.answer("📝 Masukkan pesan yang mau dikirim ke semua user:")

@router.message(F.chat.type == "private")
async def message_send(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != MessageStates.waiting_message:
        # Simpan user ke data broadcast setiap kali user kirim pesan ke bot
        save_user_for_broadcast(message.from_user)
        return  # Bukan proses broadcast, abaikan
    username = (message.from_user.username or "").lower()
    if username not in [u.lower() for u in ADMIN_USERNAMES]:
        await state.clear()
        await message.answer("❌ Hanya admin yang bisa pakai perintah ini.")
        return
    text = message.text.strip()
    if not text:
        await message.answer("Pesan tidak boleh kosong. Masukkan pesan yang mau dikirim:")
        return
    # Baca semua user dari file
    if not os.path.exists(USER_DATA_FILE):
        await message.answer("Tidak ada user yang bisa dikirimi pesan.")
        await state.clear()
        return
    with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
        users = [line.strip() for line in f if line.strip()]
    if not users:
        await message.answer("Tidak ada user yang bisa dikirimi pesan.")
        await state.clear()
        return
    bot = message.bot
    sent = 0
    failed = 0
    for user in users:
        try:
            await bot.send_message(int(user), text)
            sent += 1
        except Exception as e:
            logging.warning(f"Gagal kirim ke {user}: {e}")
            failed += 1
    await message.answer(f"✅ Pesan telah dikirim ke {sent} user.")
    if failed:
        await message.answer(f"⚠️ {failed} user gagal dikirimi pesan (mungkin blokir bot).")
    await state.clear()