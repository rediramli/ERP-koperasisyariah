import re

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .wilayah import format_date_id, parse_nik


KYC_GROUPS = 'koperasi_base.group_koperasi_petugas,koperasi_base.group_koperasi_akuntan'
KYC_REVIEW_YEARS = {'tinggi': 1, 'menengah': 2, 'rendah': 3}


class ResPartner(models.Model):
    _inherit = 'res.partner'

    koperasi_member_no = fields.Char(string='No. Anggota', copy=False, index=True, tracking=True)
    koperasi_status = fields.Selection(
        [
            ('anggota', 'Anggota'),
            ('mantan', 'Mantan Anggota'),
            ('non_anggota', 'Bukan Anggota'),
        ],
        string='Status Keanggotaan', default='non_anggota', required=True, index=True, tracking=True,
    )
    koperasi_join_date = fields.Date(string='Tanggal Masuk', tracking=True)
    koperasi_exit_date = fields.Date(string='Tanggal Keluar', tracking=True)
    koperasi_is_member = fields.Boolean(
        string='Anggota Aktif', compute='_compute_koperasi_is_member', store=True,
    )
    koperasi_is_pengurus = fields.Boolean(
        string='Pengurus Koperasi', tracking=True,
        help="Pembiayaan untuk pengurus memerlukan dasar persetujuan dan tidak boleh disetujui orang yang bersangkutan.")
    koperasi_user_id = fields.Many2one(
        'res.users', string='Akun Odoo', copy=False, tracking=True,
        help="Akun Odoo milik orang ini. Dipakai untuk mencegah seseorang menyetujui atau memberi potongan "
             "atas pembiayaannya sendiri.")

    # ------------------------------------------------------------------
    # KYC / CDD profile (SOP-PEMBIAYAAN.md tahap 3). Personal data (UU 27/2022 PDP):
    # readable only by the Koperasi groups.
    # ------------------------------------------------------------------
    koperasi_nik = fields.Char(string='NIK / No. KTP', tracking=True, copy=False, index=True, groups=KYC_GROUPS)
    koperasi_nik_info = fields.Char(string='Isi NIK', compute='_compute_koperasi_nik_info', groups=KYC_GROUPS,
                                    help="Dibaca dari NIK: tanggal lahir, jenis kelamin, dan wilayah penerbitan. "
                                         "Bukan bukti NIK terdaftar di Dukcapil.")
    koperasi_nik_warning = fields.Text(string='Ketidakcocokan NIK', compute='_compute_koperasi_nik_info',
                                       groups=KYC_GROUPS)
    koperasi_kk_no = fields.Char(string='No. Kartu Keluarga', copy=False, groups=KYC_GROUPS)
    koperasi_birth_place = fields.Char(string='Tempat Lahir', groups=KYC_GROUPS)
    koperasi_birth_date = fields.Date(string='Tanggal Lahir', groups=KYC_GROUPS)
    koperasi_age = fields.Integer(string='Usia', compute='_compute_koperasi_age', groups=KYC_GROUPS)
    koperasi_gender = fields.Selection([('l', 'Laki-laki'), ('p', 'Perempuan')], string='Jenis Kelamin',
                                       groups=KYC_GROUPS)
    koperasi_marital = fields.Selection(
        [('belum', 'Belum Menikah'), ('menikah', 'Menikah'), ('cerai_hidup', 'Cerai Hidup'),
         ('cerai_mati', 'Cerai Mati')], string='Status Perkawinan', groups=KYC_GROUPS)
    koperasi_spouse_name = fields.Char(string='Nama Pasangan', groups=KYC_GROUPS)
    koperasi_spouse_nik = fields.Char(string='NIK Pasangan', groups=KYC_GROUPS)
    koperasi_mother_name = fields.Char(string='Nama Ibu Kandung', groups=KYC_GROUPS,
                                       help="Dipakai untuk verifikasi identitas lewat telepon.")
    koperasi_domicile = fields.Text(string='Alamat Domisili', groups=KYC_GROUPS,
                                    help="Kosongkan bila sama dengan alamat KTP (alamat kontak).")
    koperasi_home_status = fields.Selection(
        [('milik', 'Milik Sendiri'), ('keluarga', 'Milik Keluarga/Orang Tua'), ('sewa', 'Sewa/Kontrak'),
         ('dinas', 'Rumah Dinas'), ('lainnya', 'Lainnya')], string='Status Tempat Tinggal', groups=KYC_GROUPS)
    koperasi_stay_years = fields.Integer(string='Lama Tinggal (tahun)', groups=KYC_GROUPS)
    koperasi_pekerjaan = fields.Char(string='Pekerjaan / Instansi', tracking=True, groups=KYC_GROUPS)
    koperasi_employer = fields.Char(string='Nama Kantor / Usaha', groups=KYC_GROUPS)
    koperasi_work_years = fields.Integer(string='Lama Bekerja / Usaha (tahun)', groups=KYC_GROUPS)
    koperasi_emergency_name = fields.Char(string='Kontak Darurat', groups=KYC_GROUPS,
                                          help="Kerabat yang tidak serumah.")
    koperasi_emergency_relation = fields.Char(string='Hubungan', groups=KYC_GROUPS)
    koperasi_emergency_phone = fields.Char(string='No. HP Kontak Darurat', groups=KYC_GROUPS)
    koperasi_is_pep = fields.Boolean(
        string='Orang yang Populer secara Politis (PEP)', groups=KYC_GROUPS,
        help="Pejabat negara/partai/BUMN atau keluarga dekatnya. Pemeriksaan diperketat (risiko tinggi).")
    koperasi_dttot_date = fields.Date(string='Tanggal Cek DTTOT/DPPSPM', groups=KYC_GROUPS,
                                      help="Pengecekan nama ke Daftar Terduga Teroris dan Organisasi Teroris "
                                           "serta daftar pendanaan proliferasi senjata pemusnah massal.")
    koperasi_dttot_result = fields.Selection(
        [('tidak', 'Tidak Ditemukan'), ('ditemukan', 'Ditemukan / Mirip')], string='Hasil Cek DTTOT/DPPSPM',
        groups=KYC_GROUPS)
    koperasi_risk_level = fields.Selection(
        [('rendah', 'Rendah'), ('menengah', 'Menengah'), ('tinggi', 'Tinggi')], string='Tingkat Risiko',
        tracking=True, groups=KYC_GROUPS)
    koperasi_kyc_date = fields.Date(string='Tanggal Verifikasi KYC', readonly=True, copy=False, groups=KYC_GROUPS)
    koperasi_kyc_user_id = fields.Many2one('res.users', string='Diverifikasi Oleh', readonly=True, copy=False,
                                           groups=KYC_GROUPS)
    koperasi_kyc_review_date = fields.Date(
        string='Tinjau Ulang KYC', compute='_compute_koperasi_kyc_review_date', groups=KYC_GROUPS,
        help="Risiko tinggi: 1 tahun, menengah: 2 tahun, rendah: 3 tahun setelah verifikasi.")

    _koperasi_member_no_uniq = models.Constraint(
        'unique(koperasi_member_no)',
        'Nomor anggota sudah dipakai kontak lain.',
    )

    @api.depends('koperasi_status')
    def _compute_koperasi_is_member(self):
        for partner in self:
            partner.koperasi_is_member = partner.koperasi_status == 'anggota'

    @api.depends('koperasi_nik', 'koperasi_birth_date', 'koperasi_gender')
    def _compute_koperasi_nik_info(self):
        Wilayah = self.env['koperasi.wilayah']
        for partner in self:
            nik = partner.koperasi_nik
            if not nik:
                partner.koperasi_nik_info = partner.koperasi_nik_warning = False
                continue
            info = parse_nik(nik, fields.Date.context_today(partner))
            problems = partner._koperasi_nik_problems(info)
            parts = []
            if info['birth_date']:
                parts.append(self.env._("Lahir %s", format_date_id(info['birth_date'])))
                parts.append(self.env._("Perempuan") if info['gender'] == 'p' else self.env._("Laki-laki"))
            if info['region_code']:
                region, __, __ = Wilayah._describe_code(info['region_code'])
                parts.append(region or self.env._("kode wilayah %s tidak dikenal", info['region_code']))
            partner.koperasi_nik_info = ' · '.join(parts) or False
            partner.koperasi_nik_warning = '\n'.join('• ' + p for p in problems) or False

    def _koperasi_nik_problems(self, info=None):
        """Inconsistencies between the NIK and the entered data (blocking for KYC)."""
        self.ensure_one()
        partner = self.sudo()
        if not partner.koperasi_nik:
            return []
        info = info or parse_nik(partner.koperasi_nik, fields.Date.context_today(self))
        if info['error']:
            return [info['error']]
        problems = []
        __, prov_ok, __ = self.env['koperasi.wilayah']._describe_code(info['region_code'])
        if not prov_ok:
            problems.append(self.env._("Kode provinsi %s di NIK tidak dikenal.", info['region_code'][:2]))
        if partner.koperasi_birth_date and partner.koperasi_birth_date != info['birth_date']:
            problems.append(self.env._("Tanggal lahir %(entered)s berbeda dengan NIK (%(nik)s).",
                                       entered=format_date_id(partner.koperasi_birth_date),
                                       nik=format_date_id(info['birth_date'])))
        if partner.koperasi_gender and partner.koperasi_gender != info['gender']:
            problems.append(self.env._("Jenis kelamin berbeda dengan NIK."))
        return problems

    def _koperasi_nik_fill_vals(self, vals):
        """Birth date and gender from the NIK, only for fields not given and still empty."""
        nik = vals.get('koperasi_nik')
        if not nik:
            return {}
        info = parse_nik(nik, fields.Date.context_today(self))
        if info['error']:
            return {}
        fill = {}
        if 'koperasi_birth_date' not in vals and not (self and self.sudo().koperasi_birth_date):
            fill['koperasi_birth_date'] = info['birth_date']
        if 'koperasi_gender' not in vals and not (self and self.sudo().koperasi_gender):
            fill['koperasi_gender'] = info['gender']
        return fill

    @api.onchange('koperasi_nik')
    def _onchange_koperasi_nik(self):
        nik = (self.koperasi_nik or '').strip()
        if not nik:
            return
        info = parse_nik(nik, fields.Date.context_today(self))
        if info['error']:
            return {'warning': {'title': self.env._("NIK"), 'message': info['error']}}
        if not self.koperasi_birth_date:
            self.koperasi_birth_date = info['birth_date']
        if not self.koperasi_gender:
            self.koperasi_gender = info['gender']
        other = self.sudo().search([('koperasi_nik', '=', nik), ('id', '!=', self._origin.id or 0)], limit=1)
        if other:
            return {'warning': {'title': self.env._("NIK sudah terdaftar"), 'message': self.env._(
                "NIK ini sudah dipakai kontak %s. Gunakan kontak tersebut (data KYC lama bisa dipakai ulang), "
                "jangan membuat kontak baru.", other.display_name)}}

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.update(self.browse()._koperasi_nik_fill_vals(vals))
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('koperasi_nik') and len(self) == 1:
            vals = dict(vals, **self._koperasi_nik_fill_vals(vals))
        return super().write(vals)

    @api.depends('koperasi_birth_date')
    def _compute_koperasi_age(self):
        today = fields.Date.context_today(self)
        for partner in self:
            birth = partner.koperasi_birth_date
            partner.koperasi_age = relativedelta(today, birth).years if birth else 0

    @api.depends('koperasi_kyc_date', 'koperasi_risk_level')
    def _compute_koperasi_kyc_review_date(self):
        for partner in self:
            years = KYC_REVIEW_YEARS.get(partner.koperasi_risk_level)
            partner.koperasi_kyc_review_date = (
                partner.koperasi_kyc_date + relativedelta(years=years)
                if partner.koperasi_kyc_date and years else False)

    @api.constrains('koperasi_nik', 'koperasi_spouse_nik')
    def _check_koperasi_nik(self):
        for partner in self.sudo():
            for nik in (partner.koperasi_nik, partner.koperasi_spouse_nik):
                if nik and not re.fullmatch(r'\d{16}', nik):
                    raise ValidationError(self.env._("NIK harus 16 digit angka (%s).", partner.display_name))
            if partner.koperasi_nik and self.sudo().search_count(
                    [('koperasi_nik', '=', partner.koperasi_nik), ('id', '!=', partner.id)]):
                raise ValidationError(self.env._(
                    "NIK %(nik)s sudah dipakai kontak lain. Gunakan kontak yang sudah ada (%(name)s).",
                    nik=partner.koperasi_nik, name=partner.display_name))

    def _koperasi_kyc_missing(self):
        """Identity data the SOP requires before a financing decision. Returns a list of labels."""
        self.ensure_one()
        partner = self.sudo()
        missing = []
        for fname in ('koperasi_nik', 'koperasi_birth_date', 'koperasi_marital', 'koperasi_mother_name',
                      'koperasi_pekerjaan', 'koperasi_emergency_name', 'koperasi_emergency_phone',
                      'koperasi_dttot_date', 'koperasi_dttot_result', 'koperasi_risk_level'):
            if not partner[fname]:
                missing.append(partner._fields[fname].string)
        if not (partner.street or partner.koperasi_domicile):
            missing.append(self.env._('Alamat'))
        mobile = partner['mobile'] if 'mobile' in partner._fields else False
        if not (partner.phone or mobile):
            missing.append(self.env._('No. HP'))
        missing += partner._koperasi_nik_problems()
        if partner.koperasi_marital == 'menikah' and not partner.koperasi_spouse_name:
            missing.append(partner._fields['koperasi_spouse_name'].string)
        return missing

    @api.constrains('koperasi_status', 'koperasi_member_no', 'koperasi_join_date', 'koperasi_exit_date')
    def _check_koperasi_membership(self):
        for partner in self:
            if partner.koperasi_status in ('anggota', 'mantan') and not partner.koperasi_member_no:
                raise ValidationError(self.env._("Anggota dan mantan anggota wajib punya nomor anggota (%s).", partner.display_name))
            if (partner.koperasi_join_date and partner.koperasi_exit_date
                    and partner.koperasi_exit_date < partner.koperasi_join_date):
                raise ValidationError(self.env._("Tanggal keluar tidak boleh sebelum tanggal masuk (%s).", partner.display_name))

    def _koperasi_is_user(self, user):
        """True when ``user`` is this person (own Odoo contact or the linked member contact)."""
        self.ensure_one()
        return self == user.partner_id or self.koperasi_user_id == user
