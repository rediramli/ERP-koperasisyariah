"""Formatting helpers for documents and messages read by members (Indonesian conventions)."""
from num2words import num2words

MONTHS_ID = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus',
             'September', 'Oktober', 'November', 'Desember']
DAYS_ID = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Ahad']


def format_rp(amount):
    """Rp 31.403.512 (whole rupiah, dot as thousands separator)."""
    value = int(round(amount or 0.0))
    text = f"{abs(value):,}".replace(',', '.')
    return f"-Rp {text}" if value < 0 else f"Rp {text}"


def format_date_id(value):
    return f"{value.day} {MONTHS_ID[value.month - 1]} {value.year}" if value else ''


def format_day_id(value):
    return DAYS_ID[value.weekday()] if value else ''


def terbilang(amount):
    """Amount in words for legal documents: 'dua juta lima ratus ribu rupiah'."""
    value = int(round(amount or 0.0))
    if value == 0:
        return 'nol rupiah'
    words = num2words(abs(value), lang='id')
    return f"{'minus ' if value < 0 else ''}{words} rupiah"
