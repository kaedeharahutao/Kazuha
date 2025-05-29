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

class NodupStates(StatesGroup):
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

async def extract_numbers_from_vcf(file_path):
    numbers = []
    vcards = []
    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
        content = await f.read()
    cards = content.split("BEGIN:VCARD")
    for card in cards:
        card = card.strip()
        if not card:
            continue
        if not card.startswith("BEGIN:VCARD"):
            card = "BEGIN:VCARD\n" + card
        tel_lines = [line for line in card.splitlines() if line.strip().startswith("TEL")]
        nomor = None
        for line in tel_lines:
            nomor_raw = line.split(":")[-1].strip()
            nomor = clean_and_validate_number(nomor_raw)
            if nomor:
                break
        vcards.append((card, nomor))
        numbers.append(nomor)
    return vcards

async def extract_numbers_from_file(file_path, ext):
    numbers = []
    if ext == ".vcf":
        vcards = await extract_numbers_from_vcf(file_path)
        numbers = [n for _, n in vcards if n]
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
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            lines = await f.readlines()
        for line in lines:
            nomor = clean_and_validate_number(line)
            if nomor:
                numbers.append(nomor)
    return numbers

@router.message(Command("nodup"), F.chat.type == "private")
async def nodup_global(message: types.Message, state: FSMContext):
    await state.clear()
    save_user_for_broadcast(message.from_user)
    save_user(message.from_user.username)
    in_group, in_channel = await check_membership(message.bot, message.from_user.id)
    if not (in_group and in_channel):
        await send_membership_message(message, in_group, in_channel)
        return
    await delete_join_message(message.bot, message.from_user.id, message.chat.id)
    log_user(message)
    bot_msg = "📎 Kirim file yang mau dihapus nomor duplikatnya."
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(NodupStates.waiting_files)
    await state.update_data(files=[], logs=[], file_error=False)

@router.message(NodupStates.waiting_files, F.document, F.chat.type == "private")
async def nodup_receive_file(message: types.Message, state: FSMContext, bot: Bot):
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
        bot_msg = "❌ Format file tidak didukung!\nUlangi dengan /nodup"
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

@router.message(NodupStates.waiting_files, Command("done"), F.chat.type == "private")
async def nodup_done(message: types.Message, state: FSMContext):
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
    total_dupes = 0
    file_paths_to_delete = []
    try:
        for file_path, original_filename, _ in files:
            _, ext = os.path.splitext(original_filename.lower())
            if ext == ".vcf":
                vcards = await extract_numbers_from_vcf(file_path)
                seen = set()
                new_vcards = []
                dupes = 0
                for card, nomor in vcards:
                    if nomor and nomor not in seen:
                        seen.add(nomor)
                        new_vcards.append(card)
                    elif nomor:
                        dupes += 1
                total_dupes += dupes
                output_path = os.path.join(DATA_DIR, original_filename)
                async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                    await f.write("\n".join(new_vcards))
                await retry_send_document(message, output_path, original_filename)
                log_bot(f"kirim file {original_filename}")
                file_paths_to_delete.append(output_path)
            elif ext in [".txt", ".csv"]:
                numbers = await extract_numbers_from_file(file_path, ext)
                seen = set()
                new_numbers = []
                dupes = 0
                for nomor in numbers:
                    if nomor not in seen:
                        seen.add(nomor)
                        new_numbers.append(nomor)
                    else:
                        dupes += 1
                total_dupes += dupes
                output_path = os.path.join(DATA_DIR, original_filename)
                async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                    await f.write("\n".join(new_numbers))
                await retry_send_document(message, output_path, original_filename)
                log_bot(f"kirim file {original_filename}")
                file_paths_to_delete.append(output_path)
            elif ext in [".xlsx", ".xls"]:
                import pandas as pd
                numbers = await extract_numbers_from_file(file_path, ext)
                seen = set()
                new_numbers = []
                dupes = 0
                for nomor in numbers:
                    if nomor not in seen:
                        seen.add(nomor)
                        new_numbers.append(nomor)
                    else:
                        dupes += 1
                total_dupes += dupes
                output_path = os.path.join(DATA_DIR, original_filename)
                df = pd.DataFrame({"Nomor": new_numbers})
                df.to_excel(output_path, index=False)
                await retry_send_document(message, output_path, original_filename)
                log_bot(f"kirim file {original_filename}")
                file_paths_to_delete.append(output_path)
            else:
                numbers = await extract_numbers_from_file(file_path, ext)
                seen = set()
                new_numbers = []
                dupes = 0
                for nomor in numbers:
                    if nomor not in seen:
                        seen.add(nomor)
                        new_numbers.append(nomor)
                    else:
                        dupes += 1
                total_dupes += dupes
                output_path = os.path.join(DATA_DIR, original_filename)
                async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                    await f.write("\n".join(new_numbers))
                await retry_send_document(message, output_path, original_filename)
                log_bot(f"kirim file {original_filename}")
                file_paths_to_delete.append(output_path)
        if total_dupes > 0:
            bot_msg = f"🔎 {total_dupes} nomor duplikat dihapus di semua file."
        else:
            bot_msg = "✅ Nomor duplikat tidak ditemukan di file manapun."
        await message.answer(bot_msg)
        log_bot(bot_msg)
    except Exception as e:
        err_msg = f"❌ Gagal hapus duplikat. Ulangi dengan /nodup\n{e}"
        logging.error(err_msg)
        log_bot(err_msg)
        await message.answer(err_msg)
    finally:
        async def remove_file(path):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logging.info(f"File hasil dihapus: {path}")
            except Exception as e:
                logging.error(f"Gagal hapus file hasil: {path} ({e})")
        await asyncio.gather(*(remove_file(path) for path in file_paths_to_delete))
        await state.clear()