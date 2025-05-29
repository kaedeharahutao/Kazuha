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
from utils.number_cleaner import extract_valid_numbers_from_lines
from utils.retry_send import retry_send_document
from managemen.membership import check_membership, send_membership_message, delete_join_message
from managemen.status import save_user
from managemen.data_file import log_file_upload
from managemen.message import save_user_for_broadcast

router = Router()

DATA_DIR = "data"

class AddStates(StatesGroup):
    waiting_files = State()
    waiting_done = State()
    waiting_numbers = State()
    waiting_contact_name = State()

def log_user(message: types.Message):
    if getattr(message, "document", None):
        logging.info(f"user: kirim file {message.document.file_name}")
    else:
        logging.info(f"user: {message.text}")

def log_bot(text: str):
    logging.info(f"bot: {text}")

@router.message(Command("add"), F.chat.type == "private")
async def add_global(message: types.Message, state: FSMContext):
    await state.clear()
    await add_start(message, state)

async def add_start(message: types.Message, state: FSMContext):
    save_user_for_broadcast(message.from_user)
    save_user(message.from_user.username)
    in_group, in_channel = await check_membership(message.bot, message.from_user.id)
    if not (in_group and in_channel):
        await send_membership_message(message, in_group, in_channel)
        return
    await delete_join_message(message.bot, message.from_user.id, message.chat.id)
    log_user(message)
    bot_msg = "📥 Kirim file yang ingin ditambah nomor"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(AddStates.waiting_files)
    await state.update_data(files=[], logs=[], file_error=False)

@router.message(AddStates.waiting_files, F.document, F.chat.type == "private")
async def add_receive_file(message: types.Message, state: FSMContext, bot: Bot):
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
        bot_msg = "❌ Format file tidak didukung!\nKetik /add untuk mulai ulang."
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
        # Pesan /done hanya muncul jika ini file valid pertama DAN tidak ada file_error di state
        if len(state_now.get("files", [])) == 1 and not state_now.get("file_error"):
            bot_msg = "✅ File diterima. Ketik /done untuk lanjut."
            await message.answer(bot_msg)
            log_bot(bot_msg)
    except Exception as e:
        err_msg = "⚠️ Gagal menerima file. Coba lagi."
        log_bot(err_msg)
        logging.error(f"user: kirim file {file.file_name if 'file' in locals() else '[unknown]'} error: {e}")
        await message.answer(err_msg)

@router.message(AddStates.waiting_files, Command("done"), F.chat.type == "private")
async def add_done(message: types.Message, state: FSMContext):
    # Cek jika user mengetik perintah utama lain di tengah proses
    if message.text.strip().startswith("/to_vcf"):
        await state.clear()
        from handlers.to_vcf import to_vcf_start
        await to_vcf_start(message, state)
        return
    if message.text.strip().startswith("/to_txt"):
        await state.clear()
        from handlers.to_txt import to_txt_start
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
    files = sorted(files, key=lambda x: x[2])
    logs = sorted(logs, key=lambda x: x[0])
    await state.update_data(files=files, logs=logs)
    for _, log_msg in logs:
        logging.info(log_msg)
    bot_msg = "📝 Masukkan nomor yang ingin ditambahkan:"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(AddStates.waiting_numbers)

@router.message(AddStates.waiting_numbers, F.chat.type == "private")
async def add_receive_numbers(message: types.Message, state: FSMContext):
    if message.text.strip().startswith("/"):
        await state.clear()
        await router.emit(message)
        return

    log_user(message)
    lines = message.text.strip().splitlines()
    numbers = extract_valid_numbers_from_lines(lines)
    numbers = list(dict.fromkeys(numbers))
    if not numbers:
        bot_msg = "Nomor tidak valid. Masukkan ulang nomor (pisahkan per baris):"
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return
    await state.update_data(add_numbers=numbers)

    # CEK: Apakah ada file .vcf?
    data = await state.get_data()
    files = data.get("files", [])
    ada_vcf = any(os.path.splitext(f[1].lower())[1] == ".vcf" for f in files)
    if ada_vcf:
        bot_msg = "Masukkan nama kontak untuk nomor baru:"
        await message.answer(bot_msg)
        log_bot(bot_msg)
        await state.set_state(AddStates.waiting_contact_name)
    else:
        # Tidak ada file .vcf, langsung proses
        await process_add(message, state)

@router.message(AddStates.waiting_contact_name, F.chat.type == "private")
async def add_receive_contact_name(message: types.Message, state: FSMContext):
    if message.text.strip().startswith("/"):
        await state.clear()
        await router.emit(message)
        return

    log_user(message)
    contact_name = message.text.strip()
    if not contact_name:
        bot_msg = "Nama kontak tidak boleh kosong. Masukkan nama kontak:"
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return
    await state.update_data(add_contact_name=contact_name)
    await process_add(message, state)

async def process_add(message: types.Message, state: FSMContext):
    data = await state.get_data()
    files = data.get("files", [])
    add_numbers = data.get("add_numbers", [])
    add_contact_name = data.get("add_contact_name", "Kontak")
    file_paths_to_delete = []
    try:
        for file_path, original_filename, _ in files:
            logging.info(f"user: proses file {os.path.basename(file_path)}")
            # Ekstrak nomor lama dan nama kontak lama (khusus vcf)
            _, ext = os.path.splitext(original_filename.lower())
            old_numbers = await extract_numbers(file_path)
            old_numbers = list(dict.fromkeys(old_numbers))
            all_numbers = add_numbers + [n for n in old_numbers if n not in add_numbers]

            # --- Penamaan kontak ---
            contact_names = []
            # Untuk file VCF, ambil nama kontak lama dari file user
            old_contact_names = []
            if ext == ".vcf":
                # Ambil nama kontak lama dari file VCF
                old_contact_names = await extract_vcf_names(file_path)
            # Nomor baru diberi nama baru, sisanya pakai nama lama (atau default jika tidak ada)
            for i in range(len(add_numbers)):
                contact_names.append(f"{add_contact_name} {i+1:02d}")
            for i, nomor in enumerate(old_numbers):
                if nomor in add_numbers:
                    continue  # Sudah di atas
                if ext == ".vcf" and i < len(old_contact_names):
                    contact_names.append(old_contact_names[i])
                else:
                    contact_names.append(f"Kontak {i+1+len(add_numbers):02d}")

            # Format file output sesuai ekstensi input
            output_name = original_filename
            output_path = os.path.join(DATA_DIR, output_name)
            if ext == ".vcf":
                vcf_content = create_vcf_content(contact_names, all_numbers)
                await write_vcf_file(output_path, vcf_content)
            elif ext in [".txt", ".csv"]:
                async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                    await f.write("\n".join(all_numbers))
            elif ext in [".xlsx", ".xls"]:
                import pandas as pd
                df = pd.DataFrame({"Nomor": all_numbers})
                df.to_excel(output_path, index=False)
            else:
                async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                    await f.write("\n".join(all_numbers))
            await retry_send_document(message, output_path, output_name)
            log_bot(f"kirim file {output_name}")
            file_paths_to_delete.append(output_path)
        bot_msg = "📤 File berhasil dikirim!"
        await message.answer(bot_msg)
        log_bot(bot_msg)
    except Exception as e:
        err_msg = f"❌ Gagal proses file. Ketik /add untuk ulang.\n{e}"
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

# Tambahkan fungsi ini di bawah process_add:
async def extract_vcf_names(file_path):
    """Ambil nama kontak dari file VCF, urut sesuai urutan nomor."""
    names = []
    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
        cards = content.split("BEGIN:VCARD")
        for card in cards:
            if "FN:" in card:
                name_line = [line for line in card.splitlines() if line.startswith("FN:")]
                if name_line:
                    names.append(name_line[0][3:].strip())
    except Exception as e:
        logging.error(f"extract_vcf_names error: {e}")
    return names

# --- Fungsi pendukung ---
def create_vcf_content(contact_names, numbers):
    vcf_entries = []
    for name, number in zip(contact_names, numbers):
        vcf_entries.append(
            f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{number}\nEND:VCARD"
        )
    return "\n".join(vcf_entries)

async def write_vcf_file(output_path, vcf_content, max_retry=3, delay=2):
    for attempt in range(1, max_retry + 1):
        try:
            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write(vcf_content)
            return True
        except Exception as e:
            logging.error(f"Error writing vcf: {e} (percobaan {attempt})")
            if attempt == max_retry:
                raise
            await asyncio.sleep(delay)
