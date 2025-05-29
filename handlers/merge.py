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

class MergeStates(StatesGroup):
    waiting_files = State()
    waiting_done = State()
    waiting_filename = State()

def log_user(message: types.Message):
    if getattr(message, "document", None):
        logging.info(f"user: kirim file {message.document.file_name}")
    else:
        logging.info(f"user: {message.text}")

def log_bot(text: str):
    logging.info(f"bot: {text}")

@router.message(Command("merge"), F.chat.type == "private")
async def merge_global(message: types.Message, state: FSMContext):
    await state.clear()
    await merge_start(message, state)

async def merge_start(message: types.Message, state: FSMContext):
    save_user_for_broadcast(message.from_user)
    save_user(message.from_user.username)
    in_group, in_channel = await check_membership(message.bot, message.from_user.id)
    if not (in_group and in_channel):
        await send_membership_message(message, in_group, in_channel)
        return
    await delete_join_message(message.bot, message.from_user.id, message.chat.id)
    log_user(message)
    bot_msg = "📎 Kirim file yang mau digabung.\nminimal 2 file, format sama."
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(MergeStates.waiting_files)
    await state.update_data(files=[], logs=[], file_error=False, ext=None)

@router.message(MergeStates.waiting_files, F.document, F.chat.type == "private")
async def merge_receive_file(message: types.Message, state: FSMContext, bot: Bot):
    log_user(message)
    await log_file_upload(message)
    file = message.document
    _, ext = os.path.splitext(file.file_name.lower())
    data = await state.get_data()
    if data.get("file_error"):
        return

    # Cek format file pertama
    if data.get("ext") is None:
        await state.update_data(ext=ext)
    # Jika format file berikutnya beda, error
    elif ext != data.get("ext"):
        await state.update_data(files=[], logs=[], file_error=True, ext=None)
        bot_msg = "❌ Semua file harus format sama!\nUlangi dengan /merge"
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
        if len(state_now.get("files", [])) == 2 and not state_now.get("file_error"):
            bot_msg = "✅ File diterima. Ketik /done jika sudah."
            await message.answer(bot_msg)
            log_bot(bot_msg)
    except Exception as e:
        err_msg = "⚠️ Gagal menerima file. Coba lagi."
        log_bot(err_msg)
        logging.error(f"user: kirim file {file.file_name if 'file' in locals() else '[unknown]'} error: {e}")
        await message.answer(err_msg)

@router.message(MergeStates.waiting_files, Command("done"), F.chat.type == "private")
async def merge_done(message: types.Message, state: FSMContext):
    log_user(message)
    data = await state.get_data()
    files = data.get("files", [])
    logs = data.get("logs", [])
    if not files or len(files) < 2:
        bot_msg = "⚠️ Minimal 2 file. Kirim file lagi."
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return
    files = sorted(files, key=lambda x: x[2])
    logs = sorted(logs, key=lambda x: x[0])
    await state.update_data(files=files, logs=logs)
    for _, log_msg in logs:
        logging.info(log_msg)
    bot_msg = "📝 Nama file hasil gabung (tanpa ekstensi)?"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(MergeStates.waiting_filename)

@router.message(MergeStates.waiting_filename, F.chat.type == "private")
async def merge_receive_filename(message: types.Message, state: FSMContext):
    if message.text.strip().startswith("/"):
        await state.clear()
        await router.emit(message)
        return

    log_user(message)
    filename = message.text.strip()
    if not filename:
        bot_msg = "Nama file tidak boleh kosong. Coba lagi:"
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return

    data = await state.get_data()
    files = data.get("files", [])
    ext = data.get("ext")
    output_name = f"{filename}{ext}"
    output_path = os.path.join(DATA_DIR, output_name)
    file_paths_to_delete = []

    try:
        # Gabung file sesuai format
        if ext == ".vcf":
            # Gabung semua blok BEGIN:VCARD ... END:VCARD
            all_vcards = []
            for file_path, _, _ in files:
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    content = await f.read()
                cards = content.split("BEGIN:VCARD")
                for card in cards:
                    card = card.strip()
                    if not card:
                        continue
                    if not card.startswith("BEGIN:VCARD"):
                        card = "BEGIN:VCARD\n" + card
                    all_vcards.append(card)
            merged_content = "\n".join(all_vcards)
            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write(merged_content)
        elif ext in [".txt", ".csv"]:
            # Gabung semua baris
            all_lines = []
            for file_path, _, _ in files:
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    lines = await f.readlines()
                all_lines.extend([line.rstrip("\n") for line in lines])
            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write("\n".join(all_lines))
        elif ext in [".xlsx", ".xls"]:
            import pandas as pd
            all_dfs = []
            for file_path, _, _ in files:
                df = pd.read_excel(file_path)
                all_dfs.append(df)
            merged_df = pd.concat(all_dfs, ignore_index=True)
            merged_df.to_excel(output_path, index=False)
        else:
            bot_msg = f"Format {ext} belum didukung untuk merge."
            await message.answer(bot_msg)
            log_bot(bot_msg)
            await state.clear()
            return

        await retry_send_document(message, output_path, output_name)
        log_bot(f"kirim file {output_name}")
        bot_msg = "✅ File gabungan sudah dikirim!"
        await message.answer(bot_msg)
        log_bot(bot_msg)
        file_paths_to_delete.append(output_path)
    except Exception as e:
        err_msg = f"❌ Gagal gabung file. Ulangi dengan /merge\n{e}"
        logging.error(err_msg)
        log_bot(err_msg)
        await message.answer(err_msg)
    finally:
        # Hapus file hasil setelah dikirim
        async def remove_file(path):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logging.info(f"File hasil dihapus: {path}")
            except Exception as e:
                logging.error(f"Gagal hapus file hasil: {path} ({e})")
        await asyncio.gather(*(remove_file(path) for path in file_paths_to_delete))
        await state.clear()