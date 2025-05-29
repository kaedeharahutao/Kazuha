from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from handlers.to_vcf import ToVcfStates
from handlers.to_txt import ToTxtStates
import logging

router = Router()

def log_user(message: types.Message):
    logging.info(f"user: {message.text}")

def log_bot(text: str):
    logging.info(f"bot: {text}")

@router.message(Command("done"), F.chat.type == "private")
async def done_handler(message: types.Message, state: FSMContext):
    log_user(message)
    current_state = await state.get_state()
    # Hanya respon jika user sedang di proses to_vcf atau to_txt
    if current_state and (
        current_state.startswith(ToVcfStates.waiting_files.state)
        or current_state.startswith(ToTxtStates.waiting_files.state)
    ):
        # Biarkan handler to_vcf atau to_txt yang handle /done
        return
    # Jika user /done di luar proses, abaikan (tidak ada respon)