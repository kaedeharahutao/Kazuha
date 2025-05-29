def _alphabet_label(idx):
    """Generate alphabet label: 0->A, 1->B, ..., 25->Z, 26->AA, 27->BB, ..."""
    # idx: 0-based
    repeat = idx // 26 + 1
    letter = chr(65 + (idx % 26))
    return letter * repeat

def generate_contact_names(base_name, count, file_idx=0, total_files=1):
    """
    Penamaan kontak:
    1. Nomor urut 01, 02, ..., 10, 11, dst.
    2. Jika split, penomoran lanjut ke file berikutnya (1 file).
    3. Jika multi file, penomoran ulang dari 01 tiap file.
    4. Jika multi file, tambahkan huruf A-Z, AA, BB, dst di depan nama kontak.
    5. Jika hanya 1 file, tidak ada huruf.
    6. Huruf berulang jika file > 26, > 52, dst.
    """
    names = []
    if total_files == 1:
        # Satu file, tanpa huruf
        for i in range(count):
            names.append(f"{base_name} {i+1:02d}")
    else:
        # Multi file, tambahkan huruf
        label = _alphabet_label(file_idx)
        for i in range(count):
            names.append(f"{base_name} {label} {i+1:02d}")
    return names