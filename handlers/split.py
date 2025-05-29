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

class SplitStates(StatesGroup):
    waiting_mode = State()
    waiting_files = State()
    waiting_done = State()
    waiting_count = State()

def log_user(message: types.Message):
    if getattr(message, "document", None):
        logging.info(f"user: kirim file {message.document.file_name}")
    else:
        logging.info(f"user: {message.text}")

def log_bot(text: str):
    logging.info(f"bot: {text}")

@router.message(Command("split"), F.chat.type == "private")
async def split_global(message: types.Message, state: FSMContext):
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
            [InlineKeyboardButton(text="🔢 Per File", callback_data="split_file")],
            [InlineKeyboardButton(text="📦 Per Kontak", callback_data="split_kontak")]
        ]
    )
    bot_msg = "Pilih cara split:\n🔢 Per File\n📦 Per Kontak"
    await message.answer(bot_msg, reply_markup=keyboard)
    log_bot(bot_msg)
    await state.set_state(SplitStates.waiting_mode)
    await state.update_data(files=[], logs=[], file_error=False, split_mode=None)

@router.callback_query(F.data == "split_file")
async def split_file_mode(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_reply_markup(reply_markup=None)
    bot_msg = "📎 Kirim file yang mau dipecah."
    await callback.message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(SplitStates.waiting_files)
    await state.update_data(files=[], logs=[], file_error=False, split_mode="file")

@router.callback_query(F.data == "split_kontak")
async def split_kontak_mode(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_reply_markup(reply_markup=None)
    bot_msg = "📎 Kirim file yang mau dipecah."
    await callback.message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(SplitStates.waiting_files)
    await state.update_data(files=[], logs=[], file_error=False, split_mode="kontak")

@router.message(SplitStates.waiting_files, F.document, F.chat.type == "private")
async def split_receive_file(message: types.Message, state: FSMContext, bot: Bot):
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
        bot_msg = "❌ Format file tidak didukung!\nUlangi dengan /split"
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

@router.message(SplitStates.waiting_files, Command("done"), F.chat.type == "private")
async def split_done(message: types.Message, state: FSMContext):
    log_user(message)
    data = await state.get_data()
    files = data.get("files", [])
    logs = data.get("logs", [])
    split_mode = data.get("split_mode")
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
    if split_mode == "file":
        bot_msg = "🔢 Mau dipecah jadi berapa file?"
    else:
        bot_msg = "📦 Berapa kontak per file?"
    await message.answer(bot_msg)
    log_bot(bot_msg)
    await state.set_state(SplitStates.waiting_count)

@router.message(SplitStates.waiting_count, F.chat.type == "private")
async def split_receive_count(message: types.Message, state: FSMContext):
    if message.text.strip().startswith("/"):
        await state.clear()
        await router.emit(message)
        return

    log_user(message)
    data = await state.get_data()
    files = data.get("files", [])
    split_mode = data.get("split_mode")
    try:
        count = int(message.text.strip())
        if count < 1:
            raise ValueError
    except Exception:
        bot_msg = "❌ Input harus angka > 0. Coba lagi."
        await message.answer(bot_msg)
        log_bot(bot_msg)
        return

    await process_split(message, state, files, split_mode, count)

async def process_split(message: types.Message, state: FSMContext, files, split_mode, count):
    file_paths_to_delete = []
    try:
        for file_path, original_filename, _ in files:
            _, ext = os.path.splitext(original_filename)
            base_name = os.path.splitext(original_filename)[0]
            # --- Ambil data kontak ---
            if ext == ".vcf":
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    content = await f.read()
                cards = content.split("BEGIN:VCARD")
                vcards = []
                for card in cards:
                    card = card.strip()
                    if not card:
                        continue
                    if not card.startswith("BEGIN:VCARD"):
                        card = "BEGIN:VCARD\n" + card
                    vcards.append(card)
                total = len(vcards)
                if split_mode == "file":
                    if count > total:
                        bot_msg = f"⚠️ Kontak cuma {total}. Tidak bisa dipecah jadi {count} file."
                        await message.answer(bot_msg)
                        log_bot(bot_msg)
                        continue
                    per_file = total // count
                    sisa = total % count
                    idx = 0
                    for i in range(count):
                        n = per_file + (1 if i < sisa else 0)
                        part = vcards[idx:idx+n]
                        idx += n
                        output_name = f"{base_name}_{i+1}{ext}"
                        output_path = os.path.join(DATA_DIR, output_name)
                        async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                            await f.write("\n".join(part))
                        await retry_send_document(message, output_path, output_name)
                        log_bot(f"kirim file {output_name}")
                        file_paths_to_delete.append(output_path)
                else:
                    part_total = (total + count - 1) // count
                    for i in range(part_total):
                        part = vcards[i*count:(i+1)*count]
                        output_name = f"{base_name}_{i+1}{ext}"
                        output_path = os.path.join(DATA_DIR, output_name)
                        async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                            await f.write("\n".join(part))
                        await retry_send_document(message, output_path, output_name)
                        log_bot(f"kirim file {output_name}")
                        file_paths_to_delete.append(output_path)
            elif ext in [".txt", ".csv"]:
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    lines = [line.rstrip("\n") for line in await f.readlines()]
                total = len(lines)
                if split_mode == "file":
                    if count > total:
                        bot_msg = f"⚠️ Baris cuma {total}. Tidak bisa dipecah jadi {count} file."
                        await message.answer(bot_msg)
                        log_bot(bot_msg)
                        continue
                    per_file = total // count
                    sisa = total % count
                    idx = 0
                    for i in range(count):
                        n = per_file + (1 if i < sisa else 0)
                        part = lines[idx:idx+n]
                        idx += n
                        output_name = f"{base_name}_{i+1}{ext}"
                        output_path = os.path.join(DATA_DIR, output_name)
                        async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                            await f.write("\n".join(part))
                        await retry_send_document(message, output_path, output_name)
                        log_bot(f"kirim file {output_name}")
                        file_paths_to_delete.append(output_path)
                else:
                    part_total = (total + count - 1) // count
                    for i in range(part_total):
                        part = lines[i*count:(i+1)*count]
                        output_name = f"{base_name}_{i+1}{ext}"
                        output_path = os.path.join(DATA_DIR, output_name)
                        async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                            await f.write("\n".join(part))
                        await retry_send_document(message, output_path, output_name)
                        log_bot(f"kirim file {output_name}")
                        file_paths_to_delete.append(output_path)
            elif ext in [".xlsx", ".xls"]:
                import pandas as pd
                df = pd.read_excel(file_path)
                total = len(df)
                if split_mode == "file":
                    if count > total:
                        bot_msg = f"⚠️ Data cuma {total}. Tidak bisa dipecah jadi {count} file."
                        await message.answer(bot_msg)
                        log_bot(bot_msg)
                        continue
                    per_file = total // count
                    sisa = total % count
                    idx = 0
                    for i in range(count):
                        n = per_file + (1 if i < sisa else 0)
                        part = df.iloc[idx:idx+n]
                        idx += n
                        output_name = f"{base_name}_{i+1}{ext}"
                        output_path = os.path.join(DATA_DIR, output_name)
                        part.to_excel(output_path, index=False)
                        await retry_send_document(message, output_path, output_name)
                        log_bot(f"kirim file {output_name}")
                        file_paths_to_delete.append(output_path)
                else:
                    part_total = (total + count - 1) // count
                    for i in range(part_total):
                        part = df.iloc[i*count:(i+1)*count]
                        output_name = f"{base_name}_{i+1}{ext}"
                        output_path = os.path.join(DATA_DIR, output_name)
                        part.to_excel(output_path, index=False)
                        await retry_send_document(message, output_path, output_name)
                        log_bot(f"kirim file {output_name}")
                        file_paths_to_delete.append(output_path)
            else:
                bot_msg = f"Format {ext} belum didukung untuk split."
                await message.answer(bot_msg)
                log_bot(bot_msg)
                continue
        bot_msg = "📤 File hasil split sudah dikirim!"
        await message.answer(bot_msg)
        log_bot(bot_msg)
    except Exception as e:
        err_msg = f"❌ Gagal split file. Ulangi dengan /split\n{e}"
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