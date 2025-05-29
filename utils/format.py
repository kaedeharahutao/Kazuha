import aiofiles
import asyncio
import logging

def create_vcf_content(contact_names, numbers):
    """Create vcf content from contact names and numbers."""
    vcf_entries = []
    for name, number in zip(contact_names, numbers):
        vcf_entries.append(
            f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL;TYPE=CELL:{number}\nEND:VCARD"
        )
    return "\n".join(vcf_entries)

async def write_vcf_file(output_path, vcf_content, max_retry=3, delay=2):
    """Write vcf content to file asynchronously dengan retry."""
    for attempt in range(1, max_retry + 1):
        try:
            async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
                await f.write(vcf_content)
            return True
        except Exception as e:
            logging.error(f"Error writing vcf: {e} (percobaan {attempt})")
            if attempt == max_retry:
                raise
            await asyncio.sleep(delay)