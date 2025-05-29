import logging
import os
import aiofiles
import asyncio
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.retry_send import retry_send_document
from managemen.membership import check_membership, send_membership_message, delete_join_message
from managemen.status import save_user
from managemen.data_file import log_file_upload
from managemen.message import save_user_for_broadcast

router = Router()
DATA_DIR = "data"

class RenameFileStates(StatesGroup):
    waiting_mode = State()
    waiting_files_auto = State()
    waiting_files_manual = State()
    waiting_done_auto = State()
    waiting_done_manual = State()
    waiting_base_name = State()
    waiting_manual_names = State()

def log_user(message: types.Message):
    if getattr(message, "document", None):
        logging.info(f"user: kirim file {message.document.file_name}")
    else:
        logging.info(f"user: {message.text}")

def log_bot(text: str):
    logging.info(f"bot: {text}")

@router.message(Command("renamefile"), F.chat.type == "private")
async def renamefile_global(message: types.Message, state: FSMContext):
    await state.clear()
    save_user_for_broadcast(message.from_user)
    save_user(message.from_user.username)
    in_group, in_channel = await check_membership(message.bot, message.from_user.id)
    if not (in_group and in_channel):
        await send_membership_message(message, in_group, in_channel)
        return
    await delete_join_message(message.bot, message.from_user.id, message.chat.id)
    log_user(message)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Otomatis", callback_data="renamefile_auto")],
            [InlineKeyboardButton(text="✏️ Manual", callback_data="renamefile_manual")]
        ]
    )
    bot_msg = "Pilih mode rename file:"
    await message.answer(bot_msg, reply_markup=keyboard)
    log_bot(bot_msg)
    await state.set_state(RenameFileStates.waiting_mode)
    await state.update_data(files=[], logs=[], file_error=False)

@router.callback_query(F.data == "renamefile_auto")
async def renamefile_auto_mode(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    # Hapus tombol dan teks "Pilih mode rename file:"
    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_reply_markup(reply_markup=None)
    bot_msg = "Kirim file yang mau diganti nama"
    await callback.message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(RenameFileStates.waiting_files_auto)
    await state.update_data(files=[], logs=[], file_error=False)

@router.callback_query(F.data == "renamefile_manual")
async def renamefile_manual_mode(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    # Hapus tombol dan teks "Pilih mode rename file:"
    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_reply_markup(reply_markup=None)
    bot_msg = "Kirim file yang mau diganti nama"
    await callback.message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(RenameFileStates.waiting_files_manual)
    await state.update_data(files=[], logs=[], file_error=False)

# --- File receive (auto/manual) ---
async def handle_file_receive(message, state, mode_state):
    log_user(message)
    await log_file_upload(message)
    file = message.document
    _, ext = os.path.splitext(file.file_name)
    # Semua format file didukung
    data = await state.get_data()
    if data.get("file_error"):
        return
    try:
        files = data.get("files", [])
        logs = data.get("logs", [])
        filename, ext_real = os.path.splitext(file.file_name)
        import time
        timestamp = int(time.time() * 1000)
        unique_name = f"{filename}_{timestamp}{ext_real}"
        file_path = os.path.join(DATA_DIR, unique_name)
        await message.bot.download(file, destination=file_path)
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

@router.message(RenameFileStates.waiting_files_auto, F.document, F.chat.type == "private")
async def renamefile_receive_file_auto(message: types.Message, state: FSMContext):
    await handle_file_receive(message, state, RenameFileStates.waiting_files_auto)

@router.message(RenameFileStates.waiting_files_manual, F.document, F.chat.type == "private")
async def renamefile_receive_file_manual(message: types.Message, state: FSMContext):
    await handle_file_receive(message, state, RenameFileStates.waiting_files_manual)

# --- /done handler (auto/manual) ---
@router.message(RenameFileStates.waiting_files_auto, Command("done"), F.chat.type == "private")
async def renamefile_done_auto(message: types.Message, state: FSMContext):
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
    bot_msg = "Masukkan nama file baru:"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(RenameFileStates.waiting_base_name)

@router.message(RenameFileStates.waiting_files_manual, Command("done"), F.chat.type == "private")
async def renamefile_done_manual(message: types.Message, state: FSMContext):
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
    await state.update_data(files=files, logs=logs, manual_idx=0, manual_names=[])
    for _, log_msg in logs:
        logging.info(log_msg)
    # Mulai tanya nama file baru untuk file pertama
    file_name = files[0][1]
    bot_msg = f"Nama baru untuk file {file_name}:"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(RenameFileStates.waiting_manual_names)

# --- Rename otomatis ---
@router.message(RenameFileStates.waiting_base_name, F.chat.type == "private")
async def renamefile_base_name(message: types.Message, state: FSMContext):
    log_user(message)
    base_name = message.text.strip()
    if not base_name:
        bot_msg = "Nama file tidak boleh kosong. Masukkan nama file baru:"
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return
    data = await state.get_data()
    files = data.get("files", [])
    # Cek jika base_name ada angka di akhir
    import re
    match = re.search(r'(.*?)(\d+)$', base_name)
    prefix, start_num = (match.group(1), int(match.group(2))) if match else (base_name, None)
    ext_list = [os.path.splitext(f[1])[1] for f in files]
    # Penamaan unik
    used_names = set()
    result_names = []
    for idx, ext in enumerate(ext_list):
        if start_num is not None:
            num = start_num + idx
            name = f"{prefix}{num}{ext}"
        else:
            name = f"{base_name} {idx+1}{ext}"
        # Cek duplikat
        orig_name = name
        dupe_idx = 1
        while name in used_names:
            name = f"{os.path.splitext(orig_name)[0]} ({dupe_idx}){ext}"
            dupe_idx += 1
        used_names.add(name)
        result_names.append(name)
    # Kirim file hasil rename
    file_paths_to_delete = []
    try:
        for (file_path, _, _), new_name in zip(files, result_names):
            output_path = os.path.join(DATA_DIR, new_name)
            async with aiofiles.open(file_path, "rb") as src, aiofiles.open(output_path, "wb") as dst:
                await dst.write(await src.read())
            await retry_send_document(message, output_path, new_name)
            log_bot(f"kirim file {new_name}")
            file_paths_to_delete.append(output_path)
        bot_msg = "📤 File sudah dikirim!"
        await message.answer(bot_msg)
        log_bot(bot_msg)
    except Exception as e:
        err_msg = f"❌ Gagal rename file. Ketik /renamefile untuk ulang.\n{e}"
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

# --- Rename manual ---
@router.message(RenameFileStates.waiting_manual_names, F.chat.type == "private")
async def renamefile_manual_names(message: types.Message, state: FSMContext):
    log_user(message)
    name = message.text.strip()
    if not name:
        bot_msg = "Nama file tidak boleh kosong. Masukkan nama file baru:"
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return
    data = await state.get_data()
    files = data.get("files", [])
    manual_idx = data.get("manual_idx", 0)
    manual_names = data.get("manual_names", [])
    ext = os.path.splitext(files[manual_idx][1])[1]
    # Cek duplikat
    orig_name = f"{name}{ext}"
    used_names = set(manual_names)
    dupe_idx = 1
    new_name = orig_name
    while new_name in used_names:
        new_name = f"{os.path.splitext(orig_name)[0]} ({dupe_idx}){ext}"
        dupe_idx += 1
    manual_names.append(new_name)
    manual_idx += 1
    if manual_idx < len(files):
        # Lanjut ke file berikutnya
        await state.update_data(manual_idx=manual_idx, manual_names=manual_names)
        next_file_name = files[manual_idx][1]
        bot_msg = f"Nama baru untuk file {next_file_name}:"
        await message.answer(bot_msg)
        log_bot(bot_msg)
    else:
        # Semua nama sudah didapat, proses rename dan kirim file
        file_paths_to_delete = []
        try:
            for (file_path, _, _), new_name in zip(files, manual_names):
                output_path = os.path.join(DATA_DIR, new_name)
                async with aiofiles.open(file_path, "rb") as src, aiofiles.open(output_path, "wb") as dst:
                    await dst.write(await src.read())
                await retry_send_document(message, output_path, new_name)
                log_bot(f"kirim file {new_name}")
                file_paths_to_delete.append(output_path)
            bot_msg = "📤 File sudah dikirim!"
            await message.answer(bot_msg)
            log_bot(bot_msg)
        except Exception as e:
            err_msg = f"❌ Gagal rename file. Ketik /renamefile untuk ulang.\n{e}"
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