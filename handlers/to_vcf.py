import logging
import os
import time
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import FSInputFile
from aiogram.filters import Command
from utils import file_naming, contact_naming, file as file_utils, format as format_utils
from utils.retry_send import retry_send_document  # Tambahan import retry
from managemen.membership import check_membership, send_membership_message, delete_join_message
import asyncio
from managemen.status import save_user
from managemen.data_file import log_file_upload
from managemen.message import save_user_for_broadcast

router = Router()

DATA_DIR = "data"

class ToVcfStates(StatesGroup):
    waiting_files = State()
    waiting_contactname = State()
    waiting_filename = State()
    waiting_split_choice = State()

def log_user(message: types.Message):
    if getattr(message, "document", None):
        logging.info(f"user: kirim file {message.document.file_name}")
    else:
        logging.info(f"user: {message.text}")

def log_bot(text: str):
    logging.info(f"bot: {text}")

# Handler global: selalu clear state sebelum lanjut ke handler utama
@router.message(Command("to_vcf"), F.chat.type == "private")
async def to_vcf_global(message: types.Message, state: FSMContext):
    await state.clear()
    await to_vcf_start(message, state)

# Handler global untuk perintah lain agar bisa membatalkan proses ini
@router.message(Command("to_txt"), F.chat.type == "private")
async def to_txt_from_vcf(message: types.Message, state: FSMContext):
    await state.clear()
    from handlers.to_txt import to_txt_start
    await to_txt_start(message, state)

@router.message(Command("start"), F.chat.type == "private")
async def start_from_vcf(message: types.Message, state: FSMContext):
    await state.clear()
    from handlers.start import start_handler
    await start_handler(message, state)

@router.message(Command("help"), F.chat.type == "private")
async def help_from_vcf(message: types.Message, state: FSMContext):
    await state.clear()
    from handlers.start import help_handler
    await help_handler(message, state)

# Handler utama
@router.message(Command("to_vcf"), F.chat.type == "private")
async def to_vcf_start(message: types.Message, state: FSMContext):
    save_user_for_broadcast(message.from_user)
    save_user(message.from_user.username)
    in_group, in_channel = await check_membership(message.bot, message.from_user.id)
    if not (in_group and in_channel):
        await send_membership_message(message, in_group, in_channel)
        return
    await delete_join_message(message.bot, message.from_user.id, message.chat.id)
    log_user(message)
    bot_msg = "📥 Kirim file .txt atau .xlsx"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(ToVcfStates.waiting_files)
    await state.update_data(files=[], logs=[])

@router.message(ToVcfStates.waiting_files, F.document, F.chat.type == "private")
async def to_vcf_receive_file(message: types.Message, state: FSMContext, bot):
    log_user(message)
    # === Tambahkan logging upload file ===
    await log_file_upload(message)
    # =====================================
    file = message.document
    allowed_ext = [".txt", ".xlsx", ".xls"]
    _, ext = os.path.splitext(file.file_name.lower())

    data = await state.get_data()
    # Jika sudah pernah error, abaikan SEMUA upload berikutnya (tidak kirim pesan apapun, tidak proses file apapun)
    if data.get("file_error"):
        return

    # Jika ada file salah format, set flag error, kirim error, dan JANGAN proses apapun lagi
    if ext not in allowed_ext:
        await state.update_data(files=[], logs=[], file_error=True)
        bot_msg = "❌ Format file tidak didukung!\nKetik /to_vcf untuk mulai ulang."
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
        state_now = await state.get_data()
        if len(state_now.get("files", [])) == 1 and not state_now.get("file_error"):
            bot_msg = "✅ File diterima. Ketik /done untuk lanjut."
            await message.answer(bot_msg)
            log_bot(bot_msg)
    except Exception as e:
        err_msg = "⚠️ Gagal menerima file. Coba lagi."
        log_bot(err_msg)
        logging.error(f"user: kirim file error: {e}")
        await message.answer(err_msg)

@router.message(ToVcfStates.waiting_files, Command("done"), F.chat.type == "private")
async def to_vcf_done(message: types.Message, state: FSMContext):
    # Cek jika user mengetik perintah utama lain di tengah proses
    if message.text.strip().startswith("/to_txt"):
        await state.clear()
        from handlers.to_txt import to_txt_start
        await to_txt_start(message, state)
        return
    if message.text.strip().startswith("/to_vcf"):
        await state.clear()
        await to_vcf_start(message, state)
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
    bot_msg = "📝 Masukkan nama kontak:"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(ToVcfStates.waiting_contactname)

@router.message(ToVcfStates.waiting_contactname, F.chat.type == "private")
async def to_vcf_contactname(message: types.Message, state: FSMContext):
    # Cek jika user mengetik perintah utama lain di tengah proses
    if message.text.strip().startswith("/to_txt"):
        await state.clear()
        from handlers.to_txt import to_txt_start
        await to_txt_start(message, state)
        return
    if message.text.strip().startswith("/to_vcf"):
        await state.clear()
        await to_vcf_start(message, state)
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
    await state.update_data(contactname=message.text.strip())
    bot_msg = "💾 Masukkan nama file:"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(ToVcfStates.waiting_filename)

@router.message(ToVcfStates.waiting_filename, F.chat.type == "private")
async def to_vcf_filename(message: types.Message, state: FSMContext):
    # Cek jika user mengetik perintah utama lain di tengah proses
    if message.text.strip().startswith("/to_txt"):
        await state.clear()
        from handlers.to_txt import to_txt_start
        await to_txt_start(message, state)
        return
    if message.text.strip().startswith("/to_vcf"):
        await state.clear()
        await to_vcf_start(message, state)
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
    await state.update_data(filename=message.text.strip())
    bot_msg = "🔢 Jumlah kontak per file atau ketik 'semua':"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(ToVcfStates.waiting_split_choice)

@router.message(ToVcfStates.waiting_split_choice, F.chat.type == "private")
async def to_vcf_split_choice(message: types.Message, state: FSMContext):
    # Cek jika user mengetik perintah utama lain di tengah proses
    if message.text.strip().startswith("/to_txt"):
        await state.clear()
        from handlers.to_txt import to_txt_start
        await to_txt_start(message, state)
        return
    if message.text.strip().startswith("/to_vcf"):
        await state.clear()
        await to_vcf_start(message, state)
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
    text = message.text.strip().lower()
    if text == "semua":
        await state.update_data(split="all")
        log_bot("Proses semua kontak dalam satu file.")
        await process_vcf(message, state)
    elif text.isdigit() and int(text) > 0:
        await state.update_data(split=int(text))
        log_bot(f"Pecah kontak per {text} kontak.")
        await process_vcf(message, state)
    else:
        bot_msg = "⚠️ Input salah. Ketik 'semua' atau jumlah kontak per file."
        await message.answer(bot_msg)
        log_bot(bot_msg)

async def process_vcf(message: types.Message, state: FSMContext):
    data = await state.get_data()
    files = data.get("files", [])
    filename = data.get("filename", "kontak")
    contactname = data.get("contactname", "Kontak")
    split = data.get("split", "all")

    file_paths_to_delete = []
    try:
        file_paths = [f[0] for f in files]
        original_names = [f[1] for f in files]
        if split == "all":
            file_names = file_naming.generate_file_names(filename, len(file_paths), split_mode="all")
            for idx, (file_path, original_filename, _) in enumerate(files):
                logging.info(f"user: proses file {os.path.basename(file_path)}")
                numbers = await file_utils.extract_numbers(file_path)
                numbers = list(dict.fromkeys(numbers))
                if not numbers:
                    bot_msg = f"⚠️ Tidak ada nomor di {original_filename}."
                    await message.answer(bot_msg)
                    log_bot(bot_msg)
                    continue
                contact_names = contact_naming.generate_contact_names(contactname, len(numbers), file_idx=idx, total_files=len(files))
                output_name = file_names[idx]
                if not output_name.lower().endswith('.vcf'):
                    output_name += ".vcf"
                vcf_content = format_utils.create_vcf_content(contact_names, numbers)
                output_path = os.path.join(DATA_DIR, output_name)
                await format_utils.write_vcf_file(output_path, vcf_content)
                await retry_send_document(message, output_path, output_name)
                log_bot(f"kirim file {output_name}")
                file_paths_to_delete.append(output_path)
        else:
            split = int(split)
            part_counts = []
            numbers_list = []
            for file_path, original_filename, _ in files:
                numbers = await file_utils.extract_numbers(file_path)
                numbers = list(dict.fromkeys(numbers))
                numbers_list.append(numbers)
                total = len(numbers)
                part_total = (total + split - 1) // split
                part_counts.append(part_total)
            file_names = file_naming.generate_file_names(filename, len(files), part_counts=part_counts, split_mode=split)
            idx_name = 0
            for file_idx, numbers in enumerate(numbers_list):
                if not numbers:
                    bot_msg = f"⚠️ Tidak ada nomor di {original_names[file_idx]}."
                    await message.answer(bot_msg)
                    log_bot(bot_msg)
                    continue
                part_total = part_counts[file_idx]
                if len(files) == 1:
                    nomor_awal = 1
                    for part_idx in range(part_total):
                        part_numbers = numbers[part_idx*split:(part_idx+1)*split]
                        contact_names = [f"{contactname} {i+nomor_awal:02d}" for i in range(1, len(part_numbers)+1)]
                        output_name = file_names[idx_name]
                        idx_name += 1
                        if not output_name.lower().endswith('.vcf'):
                            output_name += ".vcf"
                        vcf_content = format_utils.create_vcf_content(contact_names, part_numbers)
                        output_path = os.path.join(DATA_DIR, output_name)
                        await format_utils.write_vcf_file(output_path, vcf_content)
                        await retry_send_document(message, output_path, output_name)
                        log_bot(f"kirim file {output_name}")
                        file_paths_to_delete.append(output_path)
                        nomor_awal += len(part_numbers)
                else:
                    label = contact_naming._alphabet_label(file_idx)
                    for part_idx in range(part_total):
                        part_numbers = numbers[part_idx*split:(part_idx+1)*split]
                        contact_names = [f"{contactname} {label} {i+1:02d}" for i in range(len(part_numbers))]
                        output_name = file_names[idx_name]
                        idx_name += 1
                        if not output_name.lower().endswith('.vcf'):
                            output_name += ".vcf"
                        vcf_content = format_utils.create_vcf_content(contact_names, part_numbers)
                        output_path = os.path.join(DATA_DIR, output_name)
                        await format_utils.write_vcf_file(output_path, vcf_content)
                        await retry_send_document(message, output_path, output_name)
                        log_bot(f"kirim file {output_name}")
                        file_paths_to_delete.append(output_path)
        bot_msg = "📤 File berhasil dikirim!"
        await message.answer(bot_msg)
        log_bot(bot_msg)
    except Exception as e:
        err_msg = "❌ Gagal proses file. Ketik /to_vcf untuk ulang."
        logging.error(f"user: error proses vcf: {e}")
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