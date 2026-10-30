import datetime
import re

from odoo import api, fields, models

MONTHS_ID = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober',
             'November', 'Desember']


def parse_nik(nik, today=None):
    """Read what a 16-digit NIK encodes (Permendagri layout).

    Digits 1-6: province/regency/district code where the NIK was issued; 7-12: date of birth DDMMYY, with 40 added
    to the day for women; 13-16: serial number. Returns a dict with ``region_code``, ``birth_date``, ``gender``
    ('l'/'p') and ``error`` (text, or False). Does not prove that the NIK exists: that needs Dukcapil.
    """
    nik = (nik or '').strip()
    if not re.fullmatch(r'\d{16}', nik):
        return {'region_code': False, 'birth_date': False, 'gender': False,
                'error': 'NIK harus 16 digit angka.'}
    today = today or datetime.date.today()
    day, month, year2 = int(nik[6:8]), int(nik[8:10]), int(nik[10:12])
    gender = 'l'
    if day > 40:
        day -= 40
        gender = 'p'
    year = 2000 + year2 if 2000 + year2 <= today.year else 1900 + year2
    try:
        birth = datetime.date(year, month, day)
    except ValueError:
        return {'region_code': nik[:6], 'birth_date': False, 'gender': False,
                'error': 'Digit tanggal lahir di NIK tidak valid (digit 7-12).'}
    if birth > today:
        birth = birth.replace(year=birth.year - 100)
    return {'region_code': nik[:6], 'birth_date': birth, 'gender': gender, 'error': False}


def format_date_id(value):
    return f"{value.day} {MONTHS_ID[value.month - 1]} {value.year}" if value else ''


class KoperasiWilayah(models.Model):
    _name = 'koperasi.wilayah'
    _description = 'Kode Wilayah Kemendagri'
    _order = 'code'
    _rec_name = 'name'

    code = fields.Char(string='Kode', required=True, index=True, help="Tanpa titik: 2 (provinsi), 4 (kab/kota), 6 (kecamatan).")
    name = fields.Char(string='Nama', required=True)
    level = fields.Selection([('provinsi', 'Provinsi'), ('kabupaten', 'Kabupaten/Kota'), ('kecamatan', 'Kecamatan')],
                             string='Tingkat', required=True)
    parent_id = fields.Many2one('koperasi.wilayah', string='Induk', index=True)

    _code_uniq = models.Constraint('unique(code)', 'Kode wilayah sudah ada.')

    @api.model
    def _describe_code(self, code):
        """'Kec. Padang Selatan, Kota Padang, Sumatera Barat' for a 6-digit code; partial when unknown."""
        code = code or ''
        found = {r.code: r for r in self.sudo().search([('code', 'in', [code[:2], code[:4], code[:6]])])}
        parts = []
        kec, kab, prov = found.get(code[:6]), found.get(code[:4]), found.get(code[:2])
        if kec:
            parts.append('Kec. ' + kec.name)
        if kab:
            parts.append(kab.name)
        if prov:
            parts.append(prov.name)
        return ', '.join(parts), bool(prov), bool(kec)
