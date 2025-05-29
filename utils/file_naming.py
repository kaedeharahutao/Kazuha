import re

def _extract_last_number(s):
    """Ambil prefix dan angka terakhir dari string. Jika tidak ada angka, return (s, None)."""
    match = re.search(r'(.*?)(\d+)$', s)
    if match:
        prefix = match.group(1)
        number = int(match.group(2))
        return prefix, number
    return s, None

def generate_file_names(base_name, file_count, part_counts=None, split_mode="all"):
    """
    Generate file names sesuai 8 kondisi penamaan.
    - base_name: nama file dari user
    - file_count: jumlah file input user
    - part_counts: list jumlah part per file (jika split), contoh: [3,2] artinya file 1 dipecah 3, file 2 dipecah 2
    - split_mode: "all" jika user pilih semua, atau int jika split per N kontak
    """
    prefix, last_number = _extract_last_number(base_name)
    names = []

    # 1 file, semua kontak, nama file persis user
    if file_count == 1 and split_mode == "all":
        names.append(base_name)
        return names

    # Lebih dari 1 file, semua kontak, nama file diberi angka lanjut (dari last_number jika ada)
    if file_count > 1 and split_mode == "all":
        start = last_number if last_number is not None else 0
        for i in range(file_count):
            n = start + i
            if last_number is not None:
                # Tanpa tambah spasi, format persis user
                names.append(f"{prefix}{n}")
            else:
                # Tambah spasi sebelum angka
                names.append(f"{base_name} {i+1}")
        return names

    # 1 file, split per N kontak, nama file diberi angka lanjut (dari last_number jika ada)
    if file_count == 1 and isinstance(split_mode, int):
        part_total = part_counts[0] if part_counts else 1
        start = last_number if last_number is not None else 0
        for i in range(part_total):
            n = start + i
            if last_number is not None:
                names.append(f"{prefix}{n}")
            else:
                names.append(f"{base_name} {i+1}")
        return names

    # Lebih dari 1 file, split per N kontak
    if file_count > 1 and isinstance(split_mode, int):
        start = last_number if last_number is not None else 0
        for file_idx in range(file_count):
            file_number = start + file_idx
            part_total = part_counts[file_idx] if part_counts else 1
            for part_idx in range(part_total):
                part_number = part_idx + 1
                if last_number is not None:
                    # Tanpa tambah spasi, format persis user
                    names.append(f"{prefix}{file_number}_{part_number}")
                else:
                    names.append(f"{base_name} {file_idx+1}_{part_number}")
        return names

    # Default fallback
    names.append(base_name)
    return names