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
from utils.retry_send import retry_send_document
from managemen.membership import check_membership, send_membership_message, delete_join_message
from managemen.status import save_user
from managemen.data_file import log_file_upload
from managemen.message import save_user_for_broadcast

router = Router()

DATA_DIR = "data"

class ToTxtStates(StatesGroup):
    waiting_files = State()

def log_user(message: types.Message):
    if getattr(message, "document", None):
        logging.info(f"user: kirim file {message.document.file_name}")
    else:
        logging.info(f"user: {message.text}")

def log_bot(text: str):
    logging.info(f"bot: {text}")

# Fungsi tulis file txt dengan retry
async def write_txt_file(output_path, content, max_retry=3, delay=2):
    for attempt in range(1, max_retry + 1):
        try:
            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write(content)
            return True
        except Exception as e:
            logging.error(f"Error writing txt: {e} (percobaan {attempt})")
            if attempt == max_retry:
                raise
            await asyncio.sleep(delay)

# Handler global: selalu clear state sebelum lanjut ke handler utama
@router.message(Command("to_txt"), F.chat.type == "private")
async def to_txt_global(message: types.Message, state: FSMContext):
    await state.clear()
    await to_txt_start(message, state)

# Handler global untuk perintah lain agar bisa membatalkan proses ini
@router.message(Command("to_vcf"), F.chat.type == "private")
async def to_vcf_from_txt(message: types.Message, state: FSMContext):
    await state.clear()
    from handlers.to_vcf import to_vcf_start
    await to_vcf_start(message, state)

@router.message(Command("start"), F.chat.type == "private")
async def start_from_txt(message: types.Message, state: FSMContext):
    await state.clear()
    from handlers.start import start_handler
    await start_handler(message, state)

@router.message(Command("help"), F.chat.type == "private")
async def help_from_txt(message: types.Message, state: FSMContext):
    await state.clear()
    from handlers.start import help_handler
    await help_handler(message, state)

# Handler utama
@router.message(Command("to_txt"), F.chat.type == "private")
async def to_txt_start(message: types.Message, state: FSMContext):
    save_user_for_broadcast(message.from_user)
    save_user(message.from_user.username)
    in_group, in_channel = await check_membership(message.bot, message.from_user.id)
    if not (in_group and in_channel):
        await send_membership_message(message, in_group, in_channel)
        return
    await delete_join_message(message.bot, message.from_user.id, message.chat.id)
    log_user(message)
    bot_msg = "📄 Kirim file untuk diubah ke .txt"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(ToTxtStates.waiting_files)
    await state.update_data(files=[], logs=[])

@router.message(ToTxtStates.waiting_files, F.document, F.chat.type == "private")
async def to_txt_receive_file(message: types.Message, state: FSMContext, bot: Bot):
    log_user(message)
    # === Tambahkan logging upload file ===
    await log_file_upload(message)
    # =====================================
    file = message.document
    _, ext = os.path.splitext(file.file_name.lower())

    data = await state.get_data()
    # Jika sudah pernah error, abaikan SEMUA upload berikutnya (tidak kirim pesan apapun, tidak proses file apapun)
    if data.get("file_error"):
        return

    # Jika ada file salah format, reset semua file & logs, set flag error, kirim error, dan JANGAN proses apapun lagi
    if ext == ".txt":
        await state.update_data(files=[], logs=[], file_error=True)
        bot_msg = "❌ Format .txt tidak didukung!\nKetik /to_txt untuk mulai ulang."
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return

    # File valid, proses seperti biasa (hanya jika belum pernah error)
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
        # Pesan /done hanya muncul jika ini file valid pertama DAN tidak ada file_error di state
        # Cek ulang state setelah update
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

@router.message(ToTxtStates.waiting_files, Command("done"), F.chat.type == "private")
async def to_txt_done(message: types.Message, state: FSMContext):
    # Cek jika user mengetik perintah utama lain di tengah proses
    if message.text.strip().startswith("/to_vcf"):
        await state.clear()
        from handlers.to_vcf import to_vcf_start
        await to_vcf_start(message, state)
        return
    if message.text.strip().startswith("/to_txt"):
        await state.clear()
        await to_txt_start(message, state)
        return
    if message.text.strip().startswith("/start"):
        await state.clear()
        from handlers.start import start_handler
        await start_handler(message, state)
        return
    if message.text.strip().startswith("/help"):
        await state.clear()
        from handlers.start import help_handler
        await help_handler(message, state)
        return

    log_user(message)
    data = await state.get_data()
    files = data.get("files", [])
    logs = data.get("logs", [])
    if not files:
        bot_msg = "⚠️ Belum ada file. Kirim file dulu."
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return
    # Urutkan files dan logs berdasarkan message_id agar urutan sesuai upload user
    files = sorted(files, key=lambda x: x[2])
    logs = sorted(logs, key=lambda x: x[0])
    await state.update_data(files=files, logs=logs)
    # Cetak log penerimaan file sesuai urutan upload user
    for _, log_msg in logs:
        logging.info(log_msg)
    file_paths_to_delete = []
    try:
        for file_path, original_filename, _ in files:
            logging.info(f"user: proses file {os.path.basename(file_path)}")
            if not os.path.exists(file_path):
                logging.error(f"File tidak ditemukan: {file_path}")
                await message.answer(f"⚠️ File tidak ditemukan: {os.path.basename(file_path)}")
                continue
            numbers = await extract_numbers(file_path)
            logging.info(f"extract_numbers result: {len(numbers)} nomor ditemukan")
            if not numbers:
                bot_msg = f"⚠️ Tidak ada nomor di {original_filename}."
                await message.answer(bot_msg)
                log_bot(bot_msg)
                continue
            base_name, _ = os.path.splitext(original_filename)
            output_name = f"{base_name}.txt"
            output_path = os.path.join(DATA_DIR, output_name)
            # Tulis file txt dengan retry
            await write_txt_file(output_path, "\n".join(numbers))
            logging.info(f"File hasil ditulis: {output_path}")
            await retry_send_document(message, output_path, output_name)
            log_bot(f"kirim file {output_name}")
            file_paths_to_delete.append(output_path)
        bot_msg = "📤 File berhasil dikirim!"
        await message.answer(bot_msg)
        log_bot(bot_msg)
    except Exception as e:
        err_msg = f"❌ Gagal proses file. Ketik /to_txt untuk ulang.\n{e}"
        logging.error(err_msg)
        log_bot(err_msg)
        await message.answer(err_msg)
    finally:
        # Hapus semua file hasil sekaligus (paralel)
        async def remove_file(path):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logging.info(f"File hasil dihapus: {path}")
            except Exception as e:
                logging.error(f"Gagal hapus file hasil: {path} ({e})")
        await asyncio.gather(*(remove_file(path) for path in file_paths_to_delete))
        await state.clear()