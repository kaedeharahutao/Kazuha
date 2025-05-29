import os
import time
import aiofiles

USER_DATA_DIR = "managemen/user_data_file"

def get_user_identity(user):
    """
    Urutan prioritas: username, full_name, id, '-'
    """
    if hasattr(user, "username") and user.username:
        return f"@{user.username}"
    if hasattr(user, "full_name") and user.full_name:
        return user.full_name
    if hasattr(user, "id") and user.id:
        return str(user.id)
    return "-"

async def log_file_upload(message):
    """
    Simpan log upload file ke managemen/user_data_file/{username}.csv
    Format: pengirim,penerus,nama file,tanggal dan Waktu
    """
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    pengirim = get_user_identity(message.from_user)
    # Cek penerus (forwarded)
    if getattr(message, "forward_from", None):
        penerus = get_user_identity(message.forward_from)
    elif getattr(message, "forward_sender_name", None):
        penerus = message.forward_sender_name
    else:
        penerus = pengirim
    nama_file = message.document.file_name if getattr(message, "document", None) else "-"
    waktu = time.strftime("%d-%m %H:%M")
    # Nama file csv fokus ke username pengirim
    pengirim_csv = pengirim if pengirim.startswith("@") else pengirim.replace(" ", "_")
    csv_path = os.path.join(USER_DATA_DIR, f"{pengirim_csv}.csv")
    header = ["pengirim", "penerus", "nama file", "tanggal dan Waktu"]
    row = [pengirim, penerus, nama_file, waktu]
    # Tulis/append ke csv
    file_exists = os.path.exists(csv_path)
    async with aiofiles.open(csv_path, "a", encoding="utf-8") as f:
        if not file_exists:
            await f.write(",".join(header) + "\n")
        await f.write(",".join(row) + "\n")