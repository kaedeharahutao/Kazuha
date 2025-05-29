import logging
import os
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from handlers import (
    to_vcf, done, start, to_txt, admin, manual, add, delete,
    renamectc, renamefile, merge, split, count, nodup,
)
from managemen import clear_data, status, message
from managemen import clean_system_message

# Setup logging tanpa tanggal/waktu, pastikan log info tampil di terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
    stream=sys.stdout
)

# Sembunyikan log internal aiogram "Update id=... is handled..." dari terminal
logging.getLogger("aiogram.event").setLevel(logging.WARNING)
logging.getLogger("aiogram.dispatcher").setLevel(logging.WARNING)
logging.getLogger("aiogram.dispatcher.dispatcher").setLevel(logging.WARNING)

# Pastikan folder data dan managemen ada
os.makedirs("data", exist_ok=True)
os.makedirs("managemen", exist_ok=True)

# Reset user_log.txt setiap bot dijalankan (agar /status hanya menampilkan user aktif di sesi ini)
user_log_path = os.path.join("managemen", "user_log.txt")
with open(user_log_path, "w", encoding="utf-8") as f:
    pass  # Kosongkan file

async def main():
    logging.info("Bot is starting...")
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Register routers
    dp.include_router(start.router)
    dp.include_router(to_vcf.router)
    dp.include_router(to_txt.router)
    dp.include_router(add.router)
    dp.include_router(delete.router)
    dp.include_router(renamectc.router)
    dp.include_router(renamefile.router)
    dp.include_router(merge.router)
    dp.include_router(split.router)
    dp.include_router(count.router)
    dp.include_router(nodup.router)
    dp.include_router(done.router)
    dp.include_router(clear_data.router)
    dp.include_router(status.router)
    dp.include_router(admin.router)
    dp.include_router(manual.router)
    dp.include_router(message.router)
    dp.include_router(clean_system_message.router)

    await dp.start_polling(bot)
    logging.info("Bot stopped.")

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot terminated by user.")