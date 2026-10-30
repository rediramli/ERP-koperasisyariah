"""Financing application (SOP-PEMBIAYAAN.md tahap 1-4): intake, pre-screening, KYC, document checklist, survey.

The feasibility analysis and the decision stay on the draft akad created from the application (tahap 5-6).
"""
import base64
import re
import uuid

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

from ..utils import format_rp

GROUP_PETUGAS = 'koperasi_base.group_koperasi_petugas'
GROUP_PENGURUS = 'koperasi_base.group_koperasi_pengurus'

DOC_PHASES = [
    ('pengajuan', 'Sebelum Keputusan'),
    ('akad', 'Sebelum Akad'),
    ('menyusul', 'Menyusul Setelah Akad'),
]

# Akad state -> application state
AKAD_STATE_MAP = {
    'draft': 'analisis',
    'disetujui': 'disetujui',
    'barang_dibeli': 'disetujui',
    'aktif': 'disetujui',
    'lunas': 'disetujui',
    'batal': 'batal',
}

WEBSITE_MAX_UPLOAD = 5 * 1024 * 1024
WEBSITE_MIMETYPES = {b'\xff\xd8\xff': 'image/jpeg', b'\x89PNG': 'image/png', b'%PDF': 'application/pdf'}


class KoperasiPembiayaanKategori(models.Model):
    _name = 'koperasi.pembiayaan.kategori'
    _description = 'Kategori Pembiayaan'
    _order = 'sequence, id'

    name = fields.Char(string='Kategori', required=True, translate=False)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    margin_pct = fields.Float(string='Margin Usulan (%)', digits=(5, 2), default=20.0)
    min_dp_pct = fields.Float(string='Uang Muka Minimal (%)', digits=(5, 2),
                              help="Persentase dari perkiraan harga. 0 = tanpa batas. Dipakai di pra-skrining.")
    max_tenor = fields.Integer(string='Tenor Maksimal (bulan)', help="0 = tanpa batas. Dipakai di pra-skrining.")
    is_vehicle = fields.Boolean(string='Kendaraan Bermotor',
                                help="BPKB/STNK, asuransi, dan fidusia masuk checklist.")
    note = fields.Text(string='Keterangan')


class KoperasiDokumenJenis(models.Model):
    _name = 'koperasi.dokumen.jenis'
    _description = 'Jenis Dokumen Pembiayaan'
    _order = 'phase_sequence, sequence, id'

    name = fields.Char(string='Dokumen', required=True)
    code = fields.Char(string='Kode', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    phase = fields.Selection(DOC_PHASES, string='Tahap', required=True, default='pengajuan')
    phase_sequence = fields.Integer(compute='_compute_phase_sequence', store=True)
    required = fields.Boolean(string='Wajib', default=True,
                              help="Dokumen wajib harus ada dan diverifikasi, atau ditandai tidak berlaku dengan alasan.")
    original_check = fields.Boolean(string='Cek Dokumen Asli', default=True,
                                    help="Petugas wajib melihat dokumen asli, bukan cukup salinan/foto.")
    spouse_only = fields.Boolean(string='Hanya Jika Menikah')
    guarantor_only = fields.Boolean(string='Hanya Jika Ada Penjamin')
    vehicle_only = fields.Boolean(string='Hanya Kendaraan')
    kategori_ids = fields.Many2many('koperasi.pembiayaan.kategori', string='Hanya untuk Kategori',
                                    help="Kosong = semua kategori.")
    description = fields.Text(string='Keterangan')

    _code_uniq = models.Constraint('unique(code)', 'Kode dokumen sudah dipakai.')

    @api.depends('phase')
    def _compute_phase_sequence(self):
        order = [p[0] for p in DOC_PHASES]
        for doc in self:
            doc.phase_sequence = order.index(doc.phase) if doc.phase in order else 99

    def _applies_to(self, pengajuan):
        self.ensure_one()
        kategori = pengajuan.kategori_id
        if self.kategori_ids and kategori not in self.kategori_ids:
            return False
        if self.vehicle_only and not kategori.is_vehicle:
            return False
        if self.spouse_only and pengajuan.partner_id.sudo().koperasi_marital != 'menikah':
            return False
        if self.guarantor_only and not pengajuan.penjamin_id:
            return False
        return True


class KoperasiPengajuan(models.Model):
    _name = 'koperasi.murabahah.pengajuan'
    _description = 'Pengajuan Pembiayaan Murabahah'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_request desc, id desc'

    name = fields.Char(string='No. Pengajuan', required=True, copy=False, readonly=True, default='/', index=True)
    company_id = fields.Many2one('res.company', string='Perusahaan', required=True, default=lambda s: s.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    state = fields.Selection(
        [('baru', 'Baru'),
         ('kyc', 'Verifikasi KYC'),
         ('survei', 'Survei'),
         ('analisis', 'Analisis & Keputusan'),
         ('disetujui', 'Disetujui'),
         ('ditolak', 'Ditolak'),
         ('batal', 'Batal')],
        string='Tahap', default='baru', required=True, tracking=True, copy=False, index=True)
    channel = fields.Selection(
        [('wa', 'WhatsApp'), ('website', 'Website'), ('kantor', 'Datang Langsung'), ('telepon', 'Telepon'),
         ('lainnya', 'Lainnya')], string='Kanal', default='wa', required=True)
    date_request = fields.Date(string='Tanggal Permohonan', default=fields.Date.context_today, required=True)
    user_id = fields.Many2one('res.users', string='Petugas', default=lambda s: s.env.user, tracking=True)

    # Applicant as submitted (website / first chat); the verified identity lives on the contact
    applicant_name = fields.Char(string='Nama (sesuai permohonan)')
    applicant_phone = fields.Char(string='No. HP/WA (sesuai permohonan)')
    applicant_email = fields.Char(string='Email (sesuai permohonan)')
    applicant_nik = fields.Char(string='NIK (sesuai permohonan)', groups='koperasi_base.group_koperasi_petugas,'
                                                                       'koperasi_base.group_koperasi_akuntan')
    applicant_nik_info = fields.Char(string='Isi NIK', compute='_compute_applicant_nik_info',
                                     groups='koperasi_base.group_koperasi_petugas,koperasi_base.group_koperasi_akuntan')
    applicant_existing_id = fields.Many2one('res.partner', string='Kontak dengan NIK Ini',
                                            compute='_compute_applicant_nik_info',
                                            groups='koperasi_base.group_koperasi_petugas,'
                                                   'koperasi_base.group_koperasi_akuntan')
    partner_id = fields.Many2one('res.partner', string='Pemohon', tracking=True, index=True)
    partner_status = fields.Selection(related='partner_id.koperasi_status', string='Status Keanggotaan')
    partner_risk_level = fields.Selection(related='partner_id.koperasi_risk_level', string='Tingkat Risiko')
    partner_marital = fields.Selection(related='partner_id.koperasi_marital', string='Status Perkawinan')
    partner_age = fields.Integer(related='partner_id.koperasi_age', string='Usia')

    # Guarantor (kafalah, Fatwa DSN-MUI 11/2000): required for non-members when the policy says so (SOP K1)
    penjamin_id = fields.Many2one('res.partner', string='Penjamin', tracking=True,
                                  domain="[('koperasi_status', '=', 'anggota')]",
                                  help="Anggota aktif yang menjamin pembayaran (kafalah).")
    penjamin_relation = fields.Char(string='Hubungan Penjamin dengan Pemohon')
    penjamin_required = fields.Boolean(compute='_compute_penjamin_required')

    # Goods and requested terms
    kategori_id = fields.Many2one('koperasi.pembiayaan.kategori', string='Kategori', required=True, tracking=True)
    product_desc = fields.Char(string='Barang', required=True, tracking=True)
    supplier_name = fields.Char(string='Dealer / Penjual')
    supplier_id = fields.Many2one('res.partner', string='Pemasok (kontak)')
    estimated_price = fields.Monetary(string='Perkiraan Harga', tracking=True)
    down_payment = fields.Monetary(string='Uang Muka', tracking=True)
    dp_pct = fields.Float(string='Uang Muka (%)', compute='_compute_simulation', digits=(16, 1))
    tenor = fields.Integer(string='Tenor (bulan)', default=12, tracking=True)
    margin_pct = fields.Float(string='Margin (%)', digits=(5, 2), tracking=True)
    est_installment = fields.Monetary(string='Perkiraan Angsuran', compute='_compute_simulation',
                                      help="Simulasi: (harga − uang muka) × (1 + margin) ÷ tenor. Angka final di akad.")
    financing_purpose = fields.Selection([('konsumtif', 'Konsumtif'), ('produktif', 'Produktif / Usaha')],
                                         string='Tujuan', default='konsumtif')
    purpose_note = fields.Char(string='Keterangan Tujuan')
    income_source = fields.Char(string='Sumber Penghasilan')
    monthly_income = fields.Monetary(string='Penghasilan per Bulan (pengakuan)')
    other_obligations = fields.Monetary(string='Cicilan Lain per Bulan (pengakuan)')
    dependents = fields.Integer(string='Jumlah Tanggungan')
    note = fields.Text(string='Catatan Pemohon')

    # Pre-screening (tahap 2)
    prescreen_issues = fields.Text(string='Hasil Pra-skrining', compute='_compute_prescreen')
    prescreen_ok = fields.Boolean(compute='_compute_prescreen')
    prescreen_note = fields.Text(string='Dasar Pengecualian Pra-skrining', tracking=True,
                                 help="Wajib diisi bila pra-skrining menemukan catatan tetapi pengajuan tetap diproses.")

    # KYC (tahap 3)
    phone_verified = fields.Boolean(string='No. HP Sudah Ditelepon',
                                    help="Ditelepon dan dijawab oleh pemohon sendiri.")
    emergency_verified = fields.Boolean(string='Kontak Darurat Sudah Dikonfirmasi')
    address_verified = fields.Boolean(string='Alamat Sudah Dicocokkan',
                                      help="Alamat KTP vs domisili; bila beda ada bukti tinggal.")
    employment_verified = fields.Boolean(string='Pekerjaan/Usaha Sudah Dikonfirmasi')
    slik_note = fields.Text(string='Ringkasan iDeb SLIK',
                            help="Fasilitas di lembaga lain, kolektibilitas terburuk 12 bulan terakhir.")
    kyc_user_id = fields.Many2one('res.users', string='KYC Diverifikasi Oleh', readonly=True, copy=False)
    kyc_date = fields.Date(string='Tanggal Selesai KYC', readonly=True, copy=False)
    kyc_missing = fields.Text(string='Kekurangan KYC', compute='_compute_kyc_missing')

    # Documents
    dokumen_ids = fields.One2many('koperasi.murabahah.pengajuan.dokumen', 'pengajuan_id', string='Dokumen', copy=False)
    doc_progress = fields.Char(string='Dokumen Wajib', compute='_compute_doc_progress')
    doc_request_text = fields.Text(string='Pesan Permintaan Dokumen', compute='_compute_doc_request_text')

    # Survey (tahap 4)
    survey_method = fields.Selection(
        [('kunjungan', 'Kunjungan Rumah/Usaha'), ('jarak_jauh', 'Telepon + Foto Terbaru'), ('dilewati', 'Dilewati')],
        string='Cara Survei', tracking=True)
    survey_date = fields.Date(string='Tanggal Survei')
    survey_user_id = fields.Many2one('res.users', string='Petugas Survei')
    survey_met = fields.Char(string='Yang Ditemui')
    survey_location_match = fields.Boolean(string='Alamat Sesuai KTP/Domisili')
    survey_storage = fields.Char(string='Tempat Barang Disimpan/Dipakai')
    survey_note = fields.Text(string='Catatan Survei',
                              help="Kondisi rumah, lingkungan, usaha/omzet, konfirmasi tetangga/RT.")
    survey_result = fields.Selection(
        [('sesuai', 'Sesuai'), ('catatan', 'Sesuai dengan Catatan'), ('tidak_sesuai', 'Tidak Sesuai')],
        string='Kesimpulan Survei', tracking=True)

    # Outcome
    akad_id = fields.Many2one('koperasi.murabahah.akad', string='Akad', readonly=True, copy=False, index=True)
    akad_state = fields.Selection(related='akad_id.state', string='Status Akad')
    reject_reason = fields.Text(string='Alasan Ditolak / Batal', tracking=True, copy=False)
    access_token = fields.Char(copy=False, groups='base.group_system')

    _name_uniq = models.Constraint('unique(name)', 'Nomor pengajuan sudah dipakai.')

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('applicant_nik')
    def _compute_applicant_nik_info(self):
        from odoo.addons.koperasi_base.models.wilayah import format_date_id, parse_nik
        Partner = self.env['res.partner'].sudo()
        for rec in self:
            nik = (rec.sudo().applicant_nik or '').strip()
            if not nik:
                rec.applicant_nik_info = False
                rec.applicant_existing_id = False
                continue
            info = parse_nik(nik, fields.Date.context_today(rec))
            if info['error']:
                rec.applicant_nik_info = info['error']
            else:
                region, __, __ = self.env['koperasi.wilayah']._describe_code(info['region_code'])
                rec.applicant_nik_info = ' · '.join(filter(None, [
                    self.env._("Lahir %s", format_date_id(info['birth_date'])),
                    self.env._("Perempuan") if info['gender'] == 'p' else self.env._("Laki-laki"),
                    region]))
            rec.applicant_existing_id = Partner.search([('koperasi_nik', '=', nik)], limit=1)

    @api.depends('partner_id.koperasi_status', 'company_id.murabahah_non_member_policy')
    def _compute_penjamin_required(self):
        for rec in self:
            rec.penjamin_required = bool(rec.partner_id) and rec.partner_id.koperasi_status != 'anggota' \
                and rec.company_id.murabahah_non_member_policy == 'penjamin'

    def _penjamin_problems(self):
        """Blocking problems with the guarantor (empty when none is needed and none is given)."""
        self.ensure_one()
        problems = []
        if self.penjamin_required and not self.penjamin_id:
            problems.append(self.env._("Pemohon bukan anggota: wajib ada penjamin dari anggota aktif."))
        if self.penjamin_id:
            problems += self.env['koperasi.murabahah.akad']._penjamin_check(self.partner_id, self.penjamin_id)
        return problems

    @api.depends('estimated_price', 'down_payment', 'margin_pct', 'tenor')
    def _compute_simulation(self):
        for rec in self:
            financed = (rec.estimated_price or 0.0) - (rec.down_payment or 0.0)
            rec.dp_pct = rec.down_payment / rec.estimated_price * 100.0 if rec.estimated_price else 0.0
            rec.est_installment = (financed * (1 + (rec.margin_pct or 0.0) / 100.0) / rec.tenor
                                   if rec.tenor > 0 and financed > 0 else 0.0)

    def _prescreen_list(self):
        """Pre-screening findings (SOP tahap 2). Findings are warnings: processing further needs a written basis."""
        self.ensure_one()
        company = self.company_id
        kategori = self.kategori_id
        issues = []
        if self.estimated_price <= 0:
            issues.append(self.env._("Perkiraan harga belum diisi."))
        elif float_compare(self.down_payment, self.estimated_price, precision_digits=2) >= 0:
            issues.append(self.env._("Uang muka tidak boleh sama dengan atau melebihi harga."))
        if kategori.min_dp_pct and self.estimated_price > 0 and self.dp_pct + 1e-6 < kategori.min_dp_pct:
            issues.append(self.env._("Uang muka %(dp)s%% di bawah minimal %(min)s%% untuk %(cat)s.",
                                     dp=round(self.dp_pct, 1), min=kategori.min_dp_pct, cat=kategori.name))
        if kategori.max_tenor and self.tenor > kategori.max_tenor:
            issues.append(self.env._("Tenor %(t)s bulan melebihi maksimal %(max)s bulan untuk %(cat)s.",
                                     t=self.tenor, max=kategori.max_tenor, cat=kategori.name))
        partner = self.partner_id.sudo()
        if partner:
            birth = partner.koperasi_birth_date
            if birth:
                today = fields.Date.context_today(self)
                age = relativedelta(today, birth).years
                age_end = relativedelta(today + relativedelta(months=self.tenor or 0), birth).years
                if company.murabahah_min_age and age < company.murabahah_min_age and partner.koperasi_marital in (
                        False, 'belum'):
                    issues.append(self.env._("Usia %(age)s tahun di bawah minimal %(min)s tahun (dan belum menikah).",
                                             age=age, min=company.murabahah_min_age))
                if company.murabahah_max_age and age_end > company.murabahah_max_age:
                    issues.append(self.env._("Usia saat angsuran terakhir %(age)s tahun melebihi %(max)s tahun.",
                                             age=age_end, max=company.murabahah_max_age))
            if partner.koperasi_status != 'anggota':
                if company.murabahah_non_member_policy == 'penjamin':
                    issues += self._penjamin_problems()
                elif company.murabahah_non_member_policy == 'tolak':
                    issues.append(self.env._("Pemohon bukan anggota aktif; kebijakan koperasi: hanya anggota."))
                elif company.murabahah_non_member_policy == 'dasar':
                    issues.append(self.env._("Pemohon bukan anggota aktif."))
            overdue = self.env['koperasi.murabahah.akad'].sudo().search(
                [('partner_id', '=', partner.id), ('state', '=', 'aktif')]).filtered(lambda a: a.arrears_amount > 0)
            if overdue:
                issues.append(self.env._("Masih ada tunggakan di akad %s.", ", ".join(overdue.mapped('name'))))
            if partner.koperasi_risk_level == 'tinggi':
                issues.append(self.env._("Tingkat risiko KYC: tinggi."))
        if self.monthly_income and company.murabahah_max_dsr:
            dsr = (self.est_installment + (self.other_obligations or 0.0)) / self.monthly_income * 100.0
            if dsr > company.murabahah_max_dsr:
                issues.append(self.env._("Perkiraan DSR %(dsr)s%% melebihi batas %(max)s%%.",
                                         dsr=round(dsr, 1), max=company.murabahah_max_dsr))
        return issues

    @api.depends('estimated_price', 'down_payment', 'tenor', 'kategori_id', 'partner_id', 'monthly_income',
                 'other_obligations', 'margin_pct', 'penjamin_id')
    def _compute_prescreen(self):
        for rec in self:
            issues = rec._prescreen_list() if rec.kategori_id else []
            rec.prescreen_issues = "\n".join("• " + i for i in issues) if issues else False
            rec.prescreen_ok = not issues

    def _kyc_missing_list(self):
        self.ensure_one()
        missing = []
        if not self.partner_id:
            missing.append(self.env._("Pemohon (kontak) belum dipilih/dibuat"))
        else:
            missing += self.partner_id._koperasi_kyc_missing()
        for fname in ('phone_verified', 'emergency_verified', 'address_verified', 'employment_verified'):
            if not self[fname]:
                missing.append(self._fields[fname].string)
        missing += self._penjamin_problems()
        for line in self.dokumen_ids.filtered(lambda d: d.phase == 'pengajuan' and d.required and not d.is_complete):
            missing.append(self.env._("Dokumen: %s", line.name))
        return missing

    @api.depends('partner_id', 'penjamin_id', 'phone_verified', 'emergency_verified', 'address_verified',
                 'employment_verified',
                 'dokumen_ids.is_complete', 'dokumen_ids.required')
    def _compute_kyc_missing(self):
        for rec in self:
            missing = rec._kyc_missing_list()
            rec.kyc_missing = "\n".join("• " + m for m in missing) if missing else False

    @api.depends('dokumen_ids.is_complete', 'dokumen_ids.required', 'dokumen_ids.phase')
    def _compute_doc_progress(self):
        for rec in self:
            required = rec.dokumen_ids.filtered(lambda d: d.required and d.phase == 'pengajuan')
            rec.doc_progress = "%s / %s" % (len(required.filtered('is_complete')), len(required))

    @api.depends('dokumen_ids.attachment_name', 'dokumen_ids.not_applicable', 'applicant_name', 'partner_id')
    def _compute_doc_request_text(self):
        for rec in self:
            todo = rec.dokumen_ids.filtered(
                lambda d: d.phase == 'pengajuan' and not d.not_applicable and not d.attachment_name)
            if not todo:
                rec.doc_request_text = False
                continue
            name = rec.partner_id.name or rec.applicant_name or ''
            lines = [
                "Assalamu'alaikum %s," % name if name else "Assalamu'alaikum,",
                "terima kasih sudah mengajukan pembiayaan %s ke %s (%s)." % (
                    rec.product_desc or '', rec.company_id.name, rec.name),
                "Supaya bisa kami proses, mohon kirimkan:",
            ]
            lines += ["%s. %s" % (i, d.name) for i, d in enumerate(todo, 1)]
            lines += [
                "",
                "Dokumen asli akan kami cocokkan saat bertemu. Data hanya dipakai untuk pengajuan ini; "
                "setelah kami simpan, foto dokumen di chat boleh dihapus.",
            ]
            rec.doc_request_text = "\n".join(lines)

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('koperasi.murabahah.pengajuan') or '/'
            if not vals.get('margin_pct') and vals.get('kategori_id'):
                vals['margin_pct'] = self.env['koperasi.pembiayaan.kategori'].browse(vals['kategori_id']).margin_pct
        records = super().create(vals_list)
        records._sync_documents()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {'kategori_id', 'partner_id', 'penjamin_id'}.intersection(vals):
            self.filtered(lambda r: r.state in ('baru', 'kyc', 'survei', 'analisis'))._sync_documents()
        return res

    def unlink(self):
        if any(rec.state not in ('baru', 'batal') or rec.akad_id for rec in self):
            raise UserError(self.env._("Hanya pengajuan Baru (tanpa akad) yang boleh dihapus. Gunakan Tolak/Batal."))
        return super().unlink()

    @api.onchange('kategori_id')
    def _onchange_kategori_id(self):
        if self.kategori_id:
            self.margin_pct = self.kategori_id.margin_pct

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        partner = self.partner_id.sudo()
        if partner and not self.income_source and partner.koperasi_pekerjaan:
            self.income_source = partner.koperasi_pekerjaan

    def _sync_documents(self):
        """Add the checklist lines that apply (category, marital status); never removes lines with a file."""
        types = self.env['koperasi.dokumen.jenis'].sudo().search([])
        Line = self.env['koperasi.murabahah.pengajuan.dokumen'].sudo()
        for rec in self:
            if not rec.kategori_id:
                continue
            existing = rec.dokumen_ids.mapped('jenis_id')
            applicable = types.filtered(lambda t: t._applies_to(rec))
            Line.create([{'pengajuan_id': rec.id, 'jenis_id': t.id} for t in applicable - existing])
            stale = rec.dokumen_ids.filtered(
                lambda d: d.jenis_id not in applicable and not d.attachment_name and not d.verified)
            stale.unlink()

    # ------------------------------------------------------------------
    # Flow
    # ------------------------------------------------------------------
    def _check_group(self, xmlid):
        if not self.env.su and not self.env.user.has_group(xmlid):
            raise UserError(self.env._("Tindakan ini hanya untuk grup Koperasi / %s.", self.env.ref(xmlid).name))

    def _check_state(self, *states):
        for rec in self:
            if rec.state not in states:
                raise UserError(self.env._("Pengajuan %(name)s berstatus %(state)s.", name=rec.name,
                                           state=dict(self._fields['state'].selection)[rec.state]))

    def action_start_kyc(self):
        """Tahap 2 -> 3: pre-screening passed (or exception documented)."""
        self._check_group(GROUP_PETUGAS)
        self._check_state('baru')
        for rec in self:
            if not rec.partner_id:
                raise UserError(self.env._(
                    "Pengajuan %s: pilih kontak pemohon (atau buat kontak baru) sebelum verifikasi KYC. "
                    "Cari dulu berdasarkan NIK/nama supaya tidak ganda.", rec.name))
            issues = rec._prescreen_list()
            if issues and not (rec.prescreen_note or '').strip():
                raise UserError(self.env._(
                    "Pra-skrining %(name)s menemukan:\n%(issues)s\n\nTolak pengajuan, ubah syaratnya, "
                    "atau isi Dasar Pengecualian Pra-skrining.", name=rec.name,
                    issues="\n".join("• " + i for i in issues)))
            rec._sync_documents()
            rec.state = 'kyc'

    def action_complete_kyc(self):
        """Tahap 3 -> 4: identity, verification calls and pre-decision documents complete."""
        self._check_group(GROUP_PETUGAS)
        self._check_state('kyc')
        today = fields.Date.context_today(self)
        for rec in self:
            partner = rec.partner_id.sudo()
            if partner.koperasi_dttot_result == 'ditemukan':
                raise UserError(self.env._(
                    "Nama %s ditemukan/mirip di daftar DTTOT/DPPSPM. Pengajuan tidak boleh diproses; "
                    "laporkan ke pengurus.", partner.name))
            missing = rec._kyc_missing_list()
            if missing:
                raise UserError(self.env._("KYC %(name)s belum lengkap:\n%(missing)s", name=rec.name,
                                           missing="\n".join("• " + m for m in missing)))
            partner.write({'koperasi_kyc_date': today, 'koperasi_kyc_user_id': self.env.user.id})
            rec.write({'state': 'survei', 'kyc_user_id': self.env.user.id, 'kyc_date': today})

    def action_complete_survey(self):
        """Tahap 4 -> 5: survey recorded; create the draft akad for the analysis and decision."""
        self._check_group(GROUP_PETUGAS)
        self._check_state('survei')
        for rec in self:
            if not rec.survey_method or not rec.survey_result:
                raise UserError(self.env._("Pengajuan %s: isi cara survei dan kesimpulannya.", rec.name))
            if rec.survey_method == 'dilewati':
                if rec.partner_id.sudo().koperasi_risk_level != 'rendah':
                    raise UserError(self.env._(
                        "Survei hanya boleh dilewati untuk pemohon berisiko rendah (%s).", rec.name))
                if not (rec.survey_note or '').strip():
                    raise UserError(self.env._("Survei dilewati: tulis alasannya di Catatan Survei."))
            elif not rec.survey_date:
                raise UserError(self.env._("Pengajuan %s: isi tanggal survei.", rec.name))
            if rec.survey_result == 'tidak_sesuai':
                raise UserError(self.env._(
                    "Hasil survei %s tidak sesuai: tolak pengajuan atau ulangi survei.", rec.name))
            rec._create_akad()
            rec.state = 'analisis'
        return self[:1].action_view_akad() if len(self) == 1 else True

    def _create_akad(self):
        self.ensure_one()
        if self.akad_id:
            return self.akad_id
        if self.estimated_price <= 0 or self.tenor < 1:
            raise UserError(self.env._("Pengajuan %s: isi perkiraan harga dan tenor.", self.name))
        note = self.env._("Dari pengajuan %(name)s (%(channel)s).", name=self.name,
                          channel=dict(self._fields['channel'].selection)[self.channel])
        if self.note:
            note += "\n" + self.note
        akad = self.env['koperasi.murabahah.akad'].create({
            'company_id': self.company_id.id,
            'partner_id': self.partner_id.id,
            'pengajuan_id': self.id,
            'penjamin_id': self.penjamin_id.id,
            'penjamin_relation': self.penjamin_relation,
            'date_request': self.date_request,
            'product_desc': self.product_desc,
            'supplier_id': self.supplier_id.id,
            'cost_price': self.estimated_price,
            'down_payment': self.down_payment,
            'margin_pct': self.margin_pct,
            'tenor': self.tenor,
            'income_source': self.income_source or self.partner_id.sudo().koperasi_pekerjaan,
            'monthly_income': self.monthly_income,
            'other_obligations': self.other_obligations,
            'dependents': self.dependents,
            'financing_purpose': self.financing_purpose,
            'purpose_note': self.purpose_note,
            'analyst_id': self.user_id.id or self.env.user.id,
            'note': note,
        })
        self.akad_id = akad
        return akad

    def action_reject(self):
        self._check_group(GROUP_PETUGAS)
        self._check_state('baru', 'kyc', 'survei')
        for rec in self:
            if not (rec.reject_reason or '').strip():
                raise UserError(self.env._(
                    "Isi Alasan Ditolak (pengajuan %s). Sampaikan ke pemohon secara tertulis.", rec.name))
            rec.state = 'ditolak'

    def action_cancel(self):
        """Applicant withdraws."""
        self._check_group(GROUP_PETUGAS)
        self._check_state('baru', 'kyc', 'survei')
        for rec in self:
            if not (rec.reject_reason or '').strip():
                raise UserError(self.env._("Isi alasan pembatalan (pengajuan %s).", rec.name))
            rec.state = 'batal'

    def action_reset(self):
        """Back to Baru, e.g. after the applicant changed the request."""
        self._check_group(GROUP_PENGURUS)
        self._check_state('kyc', 'survei', 'ditolak', 'batal')
        if self.filtered('akad_id'):
            raise UserError(self.env._("Pengajuan yang sudah punya akad tidak bisa dikembalikan."))
        self.write({'state': 'baru'})

    def action_view_akad(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'koperasi.murabahah.akad',
            'res_id': self.akad_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_find_or_create_partner(self):
        """Link an existing contact by NIK, otherwise create one from the submitted data."""
        self._check_group(GROUP_PETUGAS)
        Partner = self.env['res.partner']
        for rec in self.filtered(lambda r: not r.partner_id):
            nik = (rec.sudo().applicant_nik or '').strip()
            partner = Partner.sudo().search([('koperasi_nik', '=', nik)], limit=1) if nik else Partner
            if not partner:
                if not rec.applicant_name:
                    raise UserError(self.env._("Isi nama pemohon atau pilih kontak yang sudah ada."))
                vals = {'name': rec.applicant_name, 'phone': rec.applicant_phone, 'email': rec.applicant_email,
                        'koperasi_status': 'non_anggota'}
                if nik and re.fullmatch(r'\d{16}', nik):
                    vals['koperasi_nik'] = nik
                partner = Partner.create(vals)
                rec.message_post(body=self.env._("Kontak baru dibuat: %s", partner.name))
            else:
                rec.message_post(body=self.env._(
                    "Dihubungkan ke kontak yang sudah ada berdasarkan NIK: %s. Cocokkan nama/HP dengan permohonan.",
                    partner.name))
            rec.partner_id = partner

    def _sync_from_akad(self, akad_state):
        target = AKAD_STATE_MAP.get(akad_state)
        for rec in self:
            if target and rec.state != target and rec.state in ('analisis', 'disetujui'):
                rec.state = target

    # ------------------------------------------------------------------
    # Website intake (koperasi_website): no contact is created from a public form
    # ------------------------------------------------------------------
    @api.model
    def _website_submit(self, data, files=None):
        """Create an application from the public form. ``data`` holds cleaned values; ``files`` maps a document
        code to (filename, bytes). Returns the new record (sudo)."""
        self = self.sudo()
        kategori = self.env['koperasi.pembiayaan.kategori'].browse(data.get('kategori_id')).exists() \
            or self.env['koperasi.pembiayaan.kategori'].search([], limit=1)
        if not kategori:
            raise ValidationError(self.env._("Kategori pembiayaan belum disiapkan."))
        nik = (data.get('nik') or '').strip()
        if nik and not re.fullmatch(r'\d{16}', nik):
            raise ValidationError(self.env._("NIK harus 16 digit angka."))
        rec = self.create({
            'channel': 'website',
            'user_id': False,
            'applicant_name': data.get('name'),
            'applicant_phone': data.get('phone'),
            'applicant_email': data.get('email') or False,
            'applicant_nik': nik or False,
            'kategori_id': kategori.id,
            'product_desc': data.get('product_desc'),
            'supplier_name': data.get('supplier_name') or False,
            'estimated_price': data.get('estimated_price') or 0.0,
            'down_payment': data.get('down_payment') or 0.0,
            'tenor': data.get('tenor') or 12,
            'income_source': data.get('income_source') or False,
            'monthly_income': data.get('monthly_income') or 0.0,
            'note': data.get('note') or False,
            'access_token': uuid.uuid4().hex,
        })
        for code, (filename, content) in (files or {}).items():
            line = rec.dokumen_ids.filtered(lambda d: d.jenis_id.code == code)[:1]
            if not line:
                continue
            if len(content) > WEBSITE_MAX_UPLOAD:
                raise ValidationError(self.env._("Ukuran file maksimal 5 MB."))
            if not any(content.startswith(magic) for magic in WEBSITE_MIMETYPES):
                raise ValidationError(self.env._("File harus berupa JPG, PNG, atau PDF."))
            line.write({'attachment': base64.b64encode(content).decode(), 'attachment_name': filename})
        rec.message_post(body=self.env._("Pengajuan masuk dari website. Cocokkan identitas lalu pilih/buat kontak."))
        return rec

    @api.model
    def _website_get(self, rec_id, token):
        """The record matching ``token`` (constant-time compare), else an empty recordset."""
        from odoo.tools import consteq
        rec = self.sudo().browse(int(rec_id)).exists() if rec_id else self.sudo()
        if rec and token and rec.access_token and consteq(rec.access_token, token):
            return rec
        return self.sudo().browse()

    def _website_summary(self):
        self.ensure_one()
        return {
            'name': self.name,
            'applicant': self.applicant_name or self.partner_id.name,
            'product_desc': self.product_desc,
            'estimated_price': format_rp(self.estimated_price),
            'tenor': self.tenor,
        }


class KoperasiPengajuanDokumen(models.Model):
    _name = 'koperasi.murabahah.pengajuan.dokumen'
    _description = 'Dokumen Pengajuan'
    _order = 'pengajuan_id, phase_sequence, sequence, id'

    pengajuan_id = fields.Many2one('koperasi.murabahah.pengajuan', required=True, ondelete='cascade', index=True)
    jenis_id = fields.Many2one('koperasi.dokumen.jenis', string='Jenis', required=True, ondelete='restrict')
    name = fields.Char(related='jenis_id.name', string='Dokumen')
    sequence = fields.Integer(related='jenis_id.sequence', store=True)
    phase = fields.Selection(related='jenis_id.phase', store=True, string='Tahap')
    phase_sequence = fields.Integer(related='jenis_id.phase_sequence', store=True)
    required = fields.Boolean(related='jenis_id.required', string='Wajib')
    original_check = fields.Boolean(related='jenis_id.original_check', string='Perlu Cek Asli')
    attachment = fields.Binary(string='File', attachment=True, copy=False)
    attachment_name = fields.Char(string='Nama File', copy=False)
    original_seen = fields.Boolean(string='Asli Sudah Dicek', copy=False)
    verified = fields.Boolean(string='Terverifikasi', copy=False)
    verified_by_id = fields.Many2one('res.users', string='Diverifikasi Oleh', readonly=True, copy=False)
    verified_date = fields.Date(string='Tgl Verifikasi', readonly=True, copy=False)
    not_applicable = fields.Boolean(string='Tidak Berlaku', copy=False)
    note = fields.Char(string='Catatan / Alasan')
    is_complete = fields.Boolean(string='Lengkap', compute='_compute_is_complete', store=True)

    @api.depends('attachment_name', 'verified', 'original_seen', 'original_check', 'not_applicable', 'note')
    def _compute_is_complete(self):
        for line in self:
            if line.not_applicable:
                line.is_complete = bool((line.note or '').strip())
            else:
                line.is_complete = bool(line.attachment_name and line.verified
                                        and (line.original_seen or not line.original_check))

    @api.constrains('not_applicable', 'note')
    def _check_na_reason(self):
        for line in self:
            if line.not_applicable and not (line.note or '').strip():
                raise ValidationError(self.env._("Dokumen %s ditandai tidak berlaku: isi alasannya.", line.name))

    @api.model_create_multi
    def create(self, vals_list):
        today = fields.Date.context_today(self)
        for vals in vals_list:
            if vals.get('verified'):
                vals.setdefault('verified_by_id', self.env.user.id)
                vals.setdefault('verified_date', today)
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('verified'):
            vals = dict(vals, verified_by_id=self.env.user.id, verified_date=fields.Date.context_today(self))
        elif 'verified' in vals and not vals['verified']:
            vals = dict(vals, verified_by_id=False, verified_date=False)
        res = super().write(vals)
        if vals.get('verified') or vals.get('original_seen'):
            for line in self:
                if line.verified and not line.attachment_name and not line.not_applicable:
                    raise ValidationError(self.env._("Unggah file %s sebelum menandai terverifikasi.", line.name))
        return res
