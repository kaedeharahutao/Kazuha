import re

def clean_and_validate_number(line):
    """
    Bersihkan dan validasi nomor:
    - Hapus semua karakter kecuali angka dan +
    - Jika ada + di awal, pertahankan, sisanya hanya angka
    - Jika tidak ada + di awal, tambahkan + di depan
    - Nomor valid: minimal 8 digit angka (tanpa +)
    - Return nomor valid dengan + di depan, atau None jika tidak valid
    """
    line = line.strip()
    if not line:
        return None
    # Hapus semua karakter kecuali angka dan +
    if line.startswith("+"):
        # Pertahankan + di depan, sisanya hanya angka
        nomor = "+" + re.sub(r"[^\d]", "", line[1:])
    else:
        nomor = re.sub(r"[^\d]", "", line)
        nomor = "+" + nomor
    # Validasi: minimal 8 digit angka (tanpa +)
    digit_count = len(re.sub(r"[^\d]", "", nomor))
    if digit_count < 8:
        return None
    return nomor

def extract_valid_numbers_from_lines(lines):
    """
    Dari list baris, ambil hanya nomor valid (sudah dibersihkan dan diverifikasi).
    """
    numbers = []
    for line in lines:
        nomor = clean_and_validate_number(line)
        if nomor:
            numbers.append(nomor)
    return numbers