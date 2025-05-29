import logging
import os
import time
import aiofiles
import asyncio
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command
from utils.file import extract_numbers
from utils.number_cleaner import extract_valid_numbers_from_lines, clean_and_validate_number
from utils.retry_send import retry_send_document
from managemen.membership import check_membership, send_membership_message, delete_join_message
from managemen.status import save_user
from managemen.data_file import log_file_upload
from managemen.message import save_user_for_broadcast

router = Router()

DATA_DIR = "data"

class DeleteStates(StatesGroup):
    waiting_files = State()
    waiting_done = State()
    waiting_numbers = State()

def log_user(message: types.Message):
    if getattr(message, "document", None):
        logging.info(f"user: kirim file {message.document.file_name}")
    else:
        logging.info(f"user: {message.text}")

def log_bot(text: str):
    logging.info(f"bot: {text}")

@router.message(Command("delete"), F.chat.type == "private")
async def delete_global(message: types.Message, state: FSMContext):
    await state.clear()
    await delete_start(message, state)

async def delete_start(message: types.Message, state: FSMContext):
    save_user_for_broadcast(message.from_user)
    save_user(message.from_user.username)
    in_group, in_channel = await check_membership(message.bot, message.from_user.id)
    if not (in_group and in_channel):
        await send_membership_message(message, in_group, in_channel)
        return
    await delete_join_message(message.bot, message.from_user.id, message.chat.id)
    log_user(message)
    bot_msg = "🗑️ Kirim file yang ingin dihapus nomornya"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(DeleteStates.waiting_files)
    await state.update_data(files=[], logs=[], file_error=False)

@router.message(DeleteStates.waiting_files, F.document, F.chat.type == "private")
async def delete_receive_file(message: types.Message, state: FSMContext, bot: Bot):
    log_user(message)
    # Logging upload file
    await log_file_upload(message)
    file = message.document
    _, ext = os.path.splitext(file.file_name.lower())
    allowed_ext = [".txt", ".xlsx", ".xls", ".vcf", ".csv"]

    data = await state.get_data()
    if data.get("file_error"):
        return

    if ext not in allowed_ext:
        await state.update_data(files=[], logs=[], file_error=True)
        bot_msg = "❌ Format file tidak didukung!\nKetik /delete untuk mulai ulang."
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return

    try:
        files = data.get("files", [])
        logs = data.get("logs", [])
        filename, ext_real = os.path.splitext(file.file_name)
        timestamp = int(time.time() * 1000)
        unique_name = f"{filename}_{timestamp}{ext_real}"
        file_path = os.path.join(DATA_DIR, unique_name)
        await bot.download(file, destination=file_path)
        files.append((file_path, file.file_name, message.message_id))
        logs.append((message.message_id, f"bot: File {file.file_name} diterima"))
        await state.update_data(files=files, logs=logs)
        state_now = await state.get_data()
        if len(state_now.get("files", [])) == 1 and not state_now.get("file_error"):
            bot_msg = "✅ File diterima. Ketik /done untuk lanjut."
            await message.answer(bot_msg)
            log_bot(bot_msg)
    except Exception as e:
        err_msg = "⚠️ Gagal menerima file. Coba lagi."
        log_bot(err_msg)
        logging.error(f"user: kirim file {file.file_name if 'file' in locals() else '[unknown]'} error: {e}")
        await message.answer(err_msg)

@router.message(DeleteStates.waiting_files, Command("done"), F.chat.type == "private")
async def delete_done(message: types.Message, state: FSMContext):
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
    bot_msg = "🚫 Masukkan nomor yang ingin dihapus (satu per baris):"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(DeleteStates.waiting_numbers)

@router.message(DeleteStates.waiting_numbers, F.chat.type == "private")
async def delete_receive_numbers(message: types.Message, state: FSMContext):
    if message.text.strip().startswith("/"):
        await state.clear()
        await router.emit(message)
        return

    log_user(message)
    lines = message.text.strip().splitlines()
    numbers_to_delete = extract_valid_numbers_from_lines(lines)
    numbers_to_delete = list(dict.fromkeys(numbers_to_delete))
    if not numbers_to_delete:
        bot_msg = "Nomor tidak valid. Masukkan ulang nomor yang ingin dihapus (pisahkan per baris):"
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return
    await state.update_data(numbers_to_delete=numbers_to_delete)
    await process_delete(message, state)

async def process_delete(message: types.Message, state: FSMContext):
    data = await state.get_data()
    files = data.get("files", [])
    numbers_to_delete = set(data.get("numbers_to_delete", []))
    file_paths_to_delete = []
    try:
        for file_path, original_filename, _ in files:
            logging.info(f"user: proses file {os.path.basename(file_path)}")
            _, ext = os.path.splitext(original_filename.lower())
            if ext == ".vcf":
                # Hapus hanya baris TEL yang nomornya cocok, struktur lain tetap
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    lines = await f.readlines()
                new_lines = []
                for line in lines:
                    if line.strip().startswith("TEL"):
                        nomor = line.split(":")[-1].strip()
                        nomor_bersih = clean_and_validate_number(nomor)
                        if nomor_bersih and nomor_bersih in numbers_to_delete:
                            continue  # skip baris ini
                    new_lines.append(line)
                output_path = os.path.join(DATA_DIR, original_filename)
                async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                    await f.writelines(new_lines)
            elif ext in [".txt", ".csv"]:
                old_numbers = await extract_numbers(file_path)
                new_numbers = [n for n in old_numbers if n not in numbers_to_delete]
                async with aiofiles.open(os.path.join(DATA_DIR, original_filename), "w", encoding="utf-8") as f:
                    await f.write("\n".join(new_numbers))
            elif ext in [".xlsx", ".xls"]:
                import pandas as pd
                old_numbers = await extract_numbers(file_path)
                new_numbers = [n for n in old_numbers if n not in numbers_to_delete]
                df = pd.DataFrame({"Nomor": new_numbers})
                df.to_excel(os.path.join(DATA_DIR, original_filename), index=False)
            else:
                old_numbers = await extract_numbers(file_path)
                new_numbers = [n for n in old_numbers if n not in numbers_to_delete]
                async with aiofiles.open(os.path.join(DATA_DIR, original_filename), "w", encoding="utf-8") as f:
                    await f.write("\n".join(new_numbers))
            await retry_send_document(message, os.path.join(DATA_DIR, original_filename), original_filename)
            log_bot(f"kirim file {original_filename}")
            file_paths_to_delete.append(os.path.join(DATA_DIR, original_filename))
        bot_msg = "📤 File berhasil dikirim!"
        await message.answer(bot_msg)
        log_bot(bot_msg)
    except Exception as e:
        err_msg = f"❌ Gagal proses file. Ketik /delete untuk ulang.\n{e}"
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