from aiogram import Router, types
import logging

router = Router()

@router.message()
async def clean_system_message(message: types.Message):
    if message.chat.type in ("group", "supergroup"):
        if message.new_chat_members:
            try:
                await message.delete()
            except Exception as e:
                logging.error(f"Failed to delete join message: {e}")
        if message.left_chat_member:
            try:
                await message.delete()
            except Exception as e:
                logging.error(f"Failed to delete leave message: {e}")