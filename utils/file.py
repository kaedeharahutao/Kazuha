import pandas as pd
import logging
import aiofiles
import re
import asyncio
from utils.number_cleaner import extract_valid_numbers_from_lines

def extract_numbers_from_vcf(file_path, max_retry=3, delay=2):
    """Extract valid phone numbers from vcf file dengan retry."""
    for attempt in range(1, max_retry + 1):
        try:
            numbers = []
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("TEL"):
                        nomor = line.split(":")[-1].strip()
                        # Tetap validasi dan bersihkan nomor
                        numbers.append(nomor)
            # Terapkan validasi juga pada hasil vcf
            numbers = extract_valid_numbers_from_lines(numbers)
            return numbers
        except Exception as e:
            logging.error(f"Error reading vcf: {e} (percobaan {attempt})")
            if attempt == max_retry:
                return []
            import time
            time.sleep(delay)

async def extract_numbers_from_txt(file_path, timeout=10, max_retry=3, delay=2):
    """Extract valid phone numbers from txt file (one per line) asynchronously, dengan timeout dan retry."""
    for attempt in range(1, max_retry + 1):
        try:
            lines = []
            async def read_lines():
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    async for line in f:
                        lines.append(line)
            await asyncio.wait_for(read_lines(), timeout=timeout)
            numbers = extract_valid_numbers_from_lines(lines)
            return numbers
        except asyncio.TimeoutError:
            logging.error(f"Timeout membaca file txt: {file_path} (percobaan {attempt})")
            if attempt == max_retry:
                return []
            await asyncio.sleep(delay)
        except Exception as e:
            logging.error(f"Error reading txt: {e} (percobaan {attempt})")
            if attempt == max_retry:
                return []
            await asyncio.sleep(delay)
    return []

def extract_numbers_from_csv(file_path, max_retry=3, delay=2):
    """Extract valid phone numbers from csv file (first column) dengan retry."""
    for attempt in range(1, max_retry + 1):
        try:
            df = pd.read_csv(file_path)
            col = df.columns[0]
            numbers = df[col].astype(str).str.strip().tolist()
            numbers = extract_valid_numbers_from_lines(numbers)
            return numbers
        except Exception as e:
            logging.error(f"Error reading csv: {e} (percobaan {attempt})")
            if attempt == max_retry:
                return []
            import time
            time.sleep(delay)

# ...
def extract_numbers_from_xlsx(file_path, max_retry=3, delay=2):
    for attempt in range(1, max_retry + 1):
        try:
            numbers = []
            xls = pd.ExcelFile(file_path)
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name)
                for col in df.columns:
                    col_data = df[col].dropna().astype(str).str.strip().tolist()
                    col_data = [x for x in col_data if x and x.lower() != "nan"]
                    valid_numbers = extract_valid_numbers_from_lines(col_data)
                    numbers.extend(valid_numbers)
            numbers = list(dict.fromkeys(numbers))
            # logging.info(f"DEBUG XLSX: total nomor valid dari semua kolom/sheet: {numbers}")  # HAPUS/COMMENT BARIS INI
            return numbers
        except Exception as e:
            logging.error(f"Error reading xlsx: {e} (percobaan {attempt})")
            if attempt == max_retry:
                return []
            import time
            time.sleep(delay)

async def extract_numbers(file_path):
    """Detect file type and extract numbers."""
    if file_path.endswith(".txt"):
        return await extract_numbers_from_txt(file_path)
    elif file_path.endswith(".csv"):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, extract_numbers_from_csv, file_path)
    elif file_path.endswith(".xlsx") or file_path.endswith(".xls"):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, extract_numbers_from_xlsx, file_path)
    elif file_path.endswith(".vcf"):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, extract_numbers_from_vcf, file_path)
    else:
        logging.error("Unsupported file type")
        return []
