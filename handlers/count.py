import logging
import os
import aiofiles
import asyncio
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command
from utils.retry_send import retry_send_document
from managemen.membership import check_membership, send_membership_message, delete_join_message
from managemen.status import save_user
from managemen.data_file import log_file_upload
from managemen.message import save_user_for_broadcast

router = Router()
DATA_DIR = "data"

class CountStates(StatesGroup):
    waiting_files = State()
    waiting_done = State()

def log_user(message: types.Message):
    if getattr(message, "document", None):
        logging.info(f"user: kirim file {message.document.file_name}")
    else:
        logging.info(f"user: {message.text}")

def log_bot(text: str):
    logging.info(f"bot: {text}")

def clean_and_validate_number(line):
    import re
    line = line.strip()
    if not line:
        return None
    if line.startswith("+"):
        nomor = "+" + re.sub(r"[^\d]", "", line[1:])
    else:
        nomor = re.sub(r"[^\d]", "", line)
        nomor = "+" + nomor
    digit_count = len(re.sub(r"[^\d]", "", nomor))
    if digit_count < 8:
        return None
    return nomor

async def extract_numbers_from_file(file_path, ext):
    numbers = []
    if ext == ".vcf":
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
        cards = content.split("BEGIN:VCARD")
        for card in cards:
            card = card.strip()
            if not card:
                continue
            for line in card.splitlines():
                if line.strip().startswith("TEL"):
                    nomor = line.split(":")[-1].strip()
                    nomor_bersih = clean_and_validate_number(nomor)
                    if nomor_bersih:
                        numbers.append(nomor_bersih)
    elif ext in [".txt", ".csv"]:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            lines = await f.readlines()
        for line in lines:
            nomor = clean_and_validate_number(line)
            if nomor:
                numbers.append(nomor)
    elif ext in [".xlsx", ".xls"]:
        import pandas as pd
        df = pd.read_excel(file_path)
        for col in df.columns:
            for val in df[col]:
                nomor = clean_and_validate_number(str(val))
                if nomor:
                    numbers.append(nomor)
    else:
        # Format lain: treat as txt
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            lines = await f.readlines()
        for line in lines:
            nomor = clean_and_validate_number(line)
            if nomor:
                numbers.append(nomor)
    return numbers

@router.message(Command("count"), F.chat.type == "private")
async def count_global(message: types.Message, state: FSMContext):
    await state.clear()
    save_user_for_broadcast(message.from_user)
    save_user(message.from_user.username)
    in_group, in_channel = await check_membership(message.bot, message.from_user.id)
    if not (in_group and in_channel):
        await send_membership_message(message, in_group, in_channel)
        return
    await delete_join_message(message.bot, message.from_user.id, message.chat.id)
    log_user(message)
    bot_msg = "📎 Kirim file yang mau dihitung kontaknya."
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(CountStates.waiting_files)
    await state.update_data(files=[], logs=[], file_error=False)

@router.message(CountStates.waiting_files, F.document, F.chat.type == "private")
async def count_receive_file(message: types.Message, state: FSMContext, bot: Bot):
    log_user(message)
    await log_file_upload(message)
    file = message.document
    _, ext = os.path.splitext(file.file_name.lower())
    allowed_ext = [".txt", ".xlsx", ".xls", ".vcf", ".csv"]
    data = await state.get_data()
    if data.get("file_error"):
        return
    if ext not in allowed_ext:
        await state.update_data(files=[], logs=[], file_error=True)
        bot_msg = "❌ Format file tidak didukung!\nUlangi dengan /count"
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return
    try:
        files = data.get("files", [])
        logs = data.get("logs", [])
        filename, ext_real = os.path.splitext(file.file_name)
        import time
        timestamp = int(time.time() * 1000)
        unique_name = f"{filename}_{timestamp}{ext_real}"
        file_path = os.path.join(DATA_DIR, unique_name)
        await bot.download(file, destination=file_path)
        files.append((file_path, file.file_name, message.message_id))
        logs.append((message.message_id, f"bot: File {file.file_name} diterima"))
        await state.update_data(files=files, logs=logs)
        state_now = await state.get_data()
        if len(state_now.get("files", [])) == 1 and not state_now.get("file_error"):
            bot_msg = "✅ File diterima. Ketik /done jika sudah."
            await message.answer(bot_msg)
            log_bot(bot_msg)
    except Exception as e:
        err_msg = "⚠️ Gagal menerima file. Coba lagi."
        log_bot(err_msg)
        logging.error(f"user: kirim file {file.file_name if 'file' in locals() else '[unknown]'} error: {e}")
        await message.answer(err_msg)

@router.message(CountStates.waiting_files, Command("done"), F.chat.type == "private")
async def count_done(message: types.Message, state: FSMContext):
    log_user(message)
    data = await state.get_data()
    files = data.get("files", [])
    logs = data.get("logs", [])
    if not files:
        bot_msg = "⚠️ Belum ada file. Kirim file dulu."
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return
    files = sorted(files, key=lambda x: x[2])
    logs = sorted(logs, key=lambda x: x[0])
    await state.update_data(files=files, logs=logs)
    for _, log_msg in logs:
        logging.info(log_msg)
    total_all = 0
    msg_lines = []
    try:
        for file_path, original_filename, _ in files:
            _, ext = os.path.splitext(original_filename.lower())
            numbers = await extract_numbers_from_file(file_path, ext)
            jumlah = len(numbers)
            total_all += jumlah
            msg_lines.append(f"{original_filename}: {jumlah} kontak")
        msg_lines.append(f"Total semua file: {total_all} kontak")
        bot_msg = "📊 Hasil hitung kontak:\n" + "\n".join(msg_lines)
        await message.answer(bot_msg)
        log_bot(bot_msg)
    except Exception as e:
        err_msg = f"❌ Gagal hitung kontak. Ulangi dengan /count\n{e}"
        logging.error(err_msg)
        log_bot(err_msg)
        await message.answer(err_msg)
    finally:
        # Hapus file upload setelah proses
        async def remove_file(path):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logging.info(f"File upload dihapus: {path}")
            except Exception as e:
                logging.error(f"Gagal hapus file upload: {path} ({e})")
        await asyncio.gather(*(remove_file(f[0]) for f in files))
        await state.clear()