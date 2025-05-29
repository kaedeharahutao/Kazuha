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

class RenameCtcStates(StatesGroup):
    waiting_files = State()
    waiting_done = State()
    waiting_old_name = State()
    waiting_new_name = State()

def log_user(message: types.Message):
    if getattr(message, "document", None):
        logging.info(f"user: kirim file {message.document.file_name}")
    else:
        logging.info(f"user: {message.text}")

def log_bot(text: str):
    logging.info(f"bot: {text}")

@router.message(Command("renamectc"), F.chat.type == "private")
async def renamectc_global(message: types.Message, state: FSMContext):
    await state.clear()
    await renamectc_start(message, state)

async def renamectc_start(message: types.Message, state: FSMContext):
    save_user_for_broadcast(message.from_user)
    save_user(message.from_user.username)
    in_group, in_channel = await check_membership(message.bot, message.from_user.id)
    if not (in_group and in_channel):
        await send_membership_message(message, in_group, in_channel)
        return
    await delete_join_message(message.bot, message.from_user.id, message.chat.id)
    log_user(message)
    bot_msg = "Kirim file .vcf yang mau diganti nama kontaknya"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(RenameCtcStates.waiting_files)
    await state.update_data(files=[], logs=[], file_error=False)

@router.message(RenameCtcStates.waiting_files, F.document, F.chat.type == "private")
async def renamectc_receive_file(message: types.Message, state: FSMContext, bot: Bot):
    log_user(message)
    await log_file_upload(message)
    file = message.document
    _, ext = os.path.splitext(file.file_name.lower())
    allowed_ext = [".vcf"]

    data = await state.get_data()
    if data.get("file_error"):
        return

    if ext not in allowed_ext:
        await state.update_data(files=[], logs=[], file_error=True)
        bot_msg = "❌ Hanya file .vcf yang didukung!\nKetik /renamectc untuk mulai ulang."
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
            bot_msg = "✅ File diterima. Ketik /done untuk lanjut."
            await message.answer(bot_msg)
            log_bot(bot_msg)
    except Exception as e:
        err_msg = "⚠️ Gagal menerima file. Coba lagi."
        log_bot(err_msg)
        logging.error(f"user: kirim file {file.file_name if 'file' in locals() else '[unknown]'} error: {e}")
        await message.answer(err_msg)

@router.message(RenameCtcStates.waiting_files, Command("done"), F.chat.type == "private")
async def renamectc_done(message: types.Message, state: FSMContext):
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
    bot_msg = "Masukkan nama kontak yang mau diganti:"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(RenameCtcStates.waiting_old_name)

@router.message(RenameCtcStates.waiting_old_name, F.chat.type == "private")
async def renamectc_receive_old_name(message: types.Message, state: FSMContext):
    if message.text.strip().startswith("/"):
        await state.clear()
        await router.emit(message)
        return

    log_user(message)
    old_name = message.text.strip()
    if not old_name:
        bot_msg = "Nama kontak tidak boleh kosong. Masukkan nama kontak yang mau diganti:"
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return
    await state.update_data(old_name=old_name)
    # Cek apakah nama kontak ditemukan di salah satu file (di seluruh isi file)
    data = await state.get_data()
    files = data.get("files", [])
    found = False
    for file_path, original_filename, _ in files:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
        if old_name in content:
            found = True
            break
    if not found:
        bot_msg = "❌ Nama kontak tidak ditemukan di file manapun. Proses dibatalkan."
        await message.answer(bot_msg)
        log_bot(bot_msg)
        await state.clear()
        return
    bot_msg = f"Nama kontak ditemukan.\nMau diganti jadi apa?"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(RenameCtcStates.waiting_new_name)

@router.message(RenameCtcStates.waiting_new_name, F.chat.type == "private")
async def renamectc_receive_new_name(message: types.Message, state: FSMContext):
    if message.text.strip().startswith("/"):
        await state.clear()
        await router.emit(message)
        return

    log_user(message)
    new_name = message.text.strip()
    if not new_name:
        bot_msg = "Nama baru tidak boleh kosong. Masukkan nama baru:"
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return
    data = await state.get_data()
    files = data.get("files", [])
    old_name = data.get("old_name", "")
    file_paths_to_delete = []
    try:
        for file_path, original_filename, _ in files:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()
            if old_name in content:
                new_content = content.replace(old_name, new_name)
                output_name = original_filename
                output_path = os.path.join(DATA_DIR, output_name)
                async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                    await f.write(new_content)
                await retry_send_document(message, output_path, output_name)
                log_bot(f"kirim file {output_name}")
                file_paths_to_delete.append(output_path)
            else:
                # Kirim balik file tanpa perubahan
                await retry_send_document(message, file_path, original_filename)
                log_bot(f"kirim file {original_filename} (tidak ada perubahan)")
        bot_msg = "📤 File sudah dikirim!"
        await message.answer(bot_msg)
        log_bot(bot_msg)
    except Exception as e:
        err_msg = f"❌ Gagal proses file. Ketik /renamectc untuk ulang.\n{e}"
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