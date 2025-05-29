import logging
import os
import aiofiles
import asyncio
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command
from utils.retry_send import retry_send_document
import time
from managemen.membership import check_membership, send_membership_message, delete_join_message
from managemen.status import save_user
from managemen.message import save_user_for_broadcast

router = Router()

DATA_DIR = "data"

class ManualStates(StatesGroup):
    waiting_numbers = State()
    waiting_contact_name = State()
    waiting_filename = State()

def log_user(message: types.Message):
    logging.info(f"user: {message.text}")

def log_bot(text: str):
    logging.info(f"bot: {text}")

def clean_and_validate_number(line):
    """
    Bersihkan dan validasi nomor:
    - Hapus semua karakter kecuali angka dan +
    - Jika ada + di awal, pertahankan, sisanya hanya angka
    - Jika tidak ada + di awal, tambahkan + di depan
    - Nomor valid: minimal 8 digit angka (tanpa +)
    - Return nomor valid dengan + di depan, atau None jika tidak valid
    """
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

def extract_valid_numbers_from_lines(lines):
    numbers = []
    for line in lines:
        nomor = clean_and_validate_number(line)
        if nomor:
            numbers.append(nomor)
    return numbers

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

def create_vcf_content(contact_names, numbers):
    vcf_entries = []
    for name, number in zip(contact_names, numbers):
        vcf_entries.append(
            f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{number}\nEND:VCARD"
        )
    return "\n".join(vcf_entries)

# Handler global: selalu clear state sebelum lanjut ke handler utama
@router.message(Command("manual"), F.chat.type == "private")
async def manual_global(message: types.Message, state: FSMContext):
    await state.clear()
    await manual_start(message, state)

@router.message(Command("to_vcf"), F.chat.type == "private")
async def to_vcf_from_manual(message: types.Message, state: FSMContext):
    await state.clear()
    from handlers.to_vcf import to_vcf_start
    await to_vcf_start(message, state)

@router.message(Command("to_txt"), F.chat.type == "private")
async def to_txt_from_manual(message: types.Message, state: FSMContext):
    await state.clear()
    from handlers.to_txt import to_txt_start
    await to_txt_start(message, state)

@router.message(Command("start"), F.chat.type == "private")
async def start_from_manual(message: types.Message, state: FSMContext):
    await state.clear()
    from handlers.start import start_handler
    await start_handler(message, state)

@router.message(Command("help"), F.chat.type == "private")
async def help_from_manual(message: types.Message, state: FSMContext):
    await state.clear()
    from handlers.start import help_handler
    await help_handler(message, state)

#Handler utama
@router.message(Command("manual"), F.chat.type == "private")
async def manual_start(message: types.Message, state: FSMContext):
    save_user_for_broadcast(message.from_user)
    save_user(message.from_user.username)
    in_group, in_channel = await check_membership(message.bot, message.from_user.id)
    if not (in_group and in_channel):
        await send_membership_message(message, in_group, in_channel)
        return
    await delete_join_message(message.bot, message.from_user.id, message.chat.id)
    log_user(message)
    bot_msg = "Masukkan nomor:"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(ManualStates.waiting_numbers)

@router.message(ManualStates.waiting_numbers, F.chat.type == "private")
async def manual_receive_numbers(message: types.Message, state: FSMContext):
    if message.text.strip().startswith("/"):
        await state.clear()
        await router.emit(message)
        return

    log_user(message)
    lines = message.text.strip().splitlines()
    numbers = extract_valid_numbers_from_lines(lines)
    numbers = list(dict.fromkeys(numbers))  # Hapus duplikat, urutan tetap
    if not numbers:
        bot_msg = "Nomor tidak valid. Masukkan ulang nomor (pisahkan per baris):"
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return
    await state.update_data(numbers=numbers)
    bot_msg = "Masukkan nama kontak:"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(ManualStates.waiting_contact_name)

@router.message(ManualStates.waiting_contact_name, F.chat.type == "private")
async def manual_receive_contact_name(message: types.Message, state: FSMContext):
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
    await state.update_data(contact_name=contact_name)
    bot_msg = "Masukkan nama file:"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(ManualStates.waiting_filename)

@router.message(ManualStates.waiting_filename, F.chat.type == "private")
async def manual_receive_filename(message: types.Message, state: FSMContext):
    if message.text.strip().startswith("/"):
        await state.clear()
        await router.emit(message)
        return

    log_user(message)
    filename = message.text.strip()
    if not filename:
        bot_msg = "Nama file tidak boleh kosong. Masukkan nama file:"
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return

    data = await state.get_data()
    numbers = data.get("numbers", [])
    contact_name = data.get("contact_name", "Kontak")

    # Penamaan kontak: urut 01, 02, dst
    contact_names = [f"{contact_name} {i+1:02d}" for i in range(len(numbers))]

    # Nama file hasil sesuai input user, tanpa kode unik/timestamp
    output_name = f"{filename}.vcf"
    output_path = os.path.join(DATA_DIR, output_name)
    vcf_content = create_vcf_content(contact_names, numbers)
    try:
        await write_vcf_file(output_path, vcf_content)
        await retry_send_document(message, output_path, output_name)
        log_bot(f"kirim file {output_name}")
        bot_msg = "File berhasil dikirim."
        await message.answer(bot_msg)
        log_bot(bot_msg)
    except Exception as e:
        err_msg = f"Gagal membuat/mengirim file: {e}"
        logging.error(err_msg)
        log_bot(err_msg)
        await message.answer(err_msg)
    finally:
        # Hapus file hasil setelah dikirim
        try:
            if os.path.exists(output_path):
                os.remove(output_path)
                logging.info(f"File hasil dihapus: {output_path}")
        except Exception as e:
            logging.error(f"Gagal hapus file hasil: {output_path} ({e})")
        await state.clear()