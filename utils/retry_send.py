import asyncio
from aiogram.types import FSInputFile
from aiogram.exceptions import TelegramNetworkError

async def retry_send_document(message, file_path, filename, max_retry=5, delay=2):
    """
    Kirim dokumen ke Telegram dengan retry jika timeout/network error.
    Tidak ada pesan ke user saat retry, hanya jika sudah gagal 5x.
    """
    for attempt in range(1, max_retry + 1):
        try:
            await message.answer_document(FSInputFile(file_path, filename=filename))
            return True
        except (asyncio.TimeoutError, TelegramNetworkError):
            if attempt == max_retry:
                await message.answer("Terjadi kesalahan saat mengirim file. Silakan coba lagi nanti atau hubungi admin.")
                return False
            await asyncio.sleep(delay)
        except Exception:
            await message.answer("Terjadi kesalahan saat mengirim file. Silakan coba lagi nanti atau hubungi admin.")
            return False
    return False