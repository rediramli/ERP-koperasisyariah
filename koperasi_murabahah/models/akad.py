import math

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero, float_round

from ..utils import format_date_id, format_day_id, format_rp, terbilang

GROUP_PETUGAS = 'koperasi_base.group_koperasi_petugas'
GROUP_PENGURUS = 'koperasi_base.group_koperasi_pengurus'

# Numbers fixed at approval; after that a correction is cancel + new contract.
LOCKED_FIELDS = {
    'partner_id', 'cost_price', 'down_payment', 'margin_pct', 'margin_amount',
    'tenor', 'installment_amount', 'first_due_date', 'company_id',
    'purchase_price', 'direct_cost', 'supplier_discount', 'penjamin_id',
}

# Description of the goods and contract terms: fixed once the contract is signed (aktif).
SPEC_FIELDS = {
    'product_desc', 'product_id', 'supplier_id', 'product_brand', 'product_model', 'product_color',
    'product_serial', 'product_serial2', 'product_condition', 'product_spec', 'supplier_invoice_ref',
    'khiyar_days', 'khiyar_terms', 'tazir_terms', 'date_supplier_handover',
    'purchase_method', 'wad_date', 'wakalah_date', 'wakil_id', 'wakalah_scope', 'wakalah_max_price',
}

DEFAULT_WAKALAH_SCOPE = (
    "Memesan dan membeli barang sesuai spesifikasi di atas atas nama KOPERASI, menerima barang dari pemasok, "
    "dan menyerahkan faktur/nota pembelian kepada KOPERASI. Pembayaran kepada pemasok dilakukan oleh KOPERASI.")
SIGNED_STATES = ('aktif', 'lunas', 'batal')

# Feasibility analysis: fixed once the financing is approved (OJK guideline, schemes step "analisis kelayakan")
ANALYSIS_FIELDS = {
    'income_source', 'monthly_income', 'other_obligations', 'dependents', 'financing_purpose', 'purpose_note',
    'analysis_note', 'officer_recommendation', 'analyst_id', 'analysis_date',
}

DEFAULT_KHIYAR_TERMS = (
    "Cacat atau kerusakan bawaan (cacat produksi, barang tidak berfungsi, tidak sesuai spesifikasi) "
    "yang ditemukan saat serah terima dan bukan karena kelalaian Anggota.")

COLLECTIBILITY = [
    ('lancar', 'Lancar'),
    ('dpk', 'Dalam Perhatian Khusus'),
    ('kurang_lancar', 'Kurang Lancar'),
    ('diragukan', 'Diragukan'),
    ('macet', 'Macet'),
]


def round_rp(amount):
    """Margin portions and allocations are kept in whole rupiah (owner decision 18 Oct 2026)."""
    return float_round(amount, precision_rounding=1.0)


def split_schedule(total, margin, count, installment):
    """Split ``total`` (of which ``margin`` is margin) into ``count`` installments.

    Installments 1..count-1 equal ``installment``; the last one takes the remainder.
    The margin portion of each installment is proportional (installment x margin / total),
    rounded to Rp 1, with the rounding remainder in the last installment, so that the sums
    of principal and margin are exact to the rupiah.
    Returns a list of (principal, margin) tuples.
    """
    if count < 1:
        raise UserError("Jumlah angsuran minimal 1.")
    if float_compare(total, 0.0, precision_digits=2) <= 0:
        raise UserError("Total angsuran harus lebih dari nol.")
    if margin < 0 or float_compare(margin, total, precision_digits=2) > 0:
        raise UserError("Margin harus di antara 0 dan total angsuran.")
    last_total = round_rp(total - installment * (count - 1))
    if count > 1 and (installment <= 0 or last_total <= 0):
        raise UserError(
            "Angsuran %s x %s melebihi total %s. Periksa tenor atau aturan pembulatan."
            % (count - 1, installment, total))
    ratio = margin / total
    result = []
    margin_sum = 0.0
    for i in range(count):
        line_total = installment if i < count - 1 else last_total
        if i < count - 1:
            line_margin = round_rp(line_total * ratio)
        else:
            line_margin = round_rp(margin - margin_sum)
        if line_margin < 0 or float_compare(line_margin, line_total, precision_digits=2) > 0:
            raise UserError("Pembagian margin angsuran terakhir tidak valid. Periksa aturan pembulatan.")
        margin_sum += line_margin
        result.append((round_rp(line_total - line_margin), line_margin))
    return result


def _round_half_down(value):
    """Rupiah rounding used in the OJK simulation (x,5 goes down, x,67 goes up)."""
    return float(math.ceil(round(value - 0.5, 6)))


def pupmsjt(principal, first_margin, debt, tenor, months, settled, remaining_principal, remaining_receivable):
    """Pelunasan Utang Pembiayaan Murabahah Sebelum Jatuh Tempo (Fatwa DSN-MUI 153/2022,
    OJK murabahah guideline 2023 p. 14-15 and simulations p. 42-45).

    principal: harga perolehan dikurangi uang muka (pokok yang dibiayai)
    first_margin: margin of the first month (tsaman naqdy = principal + first_margin)
    debt: harga cicilan = principal + total margin (= piutang setelah uang muka)
    months: months elapsed up to the payoff, counting the month of the contract as 1
    settled: angsuran yang telah dibayar (including earlier discounts)
    Returns the amount to collect and the resulting discount.
    """
    tenor = max(int(tenor or 1), 1)
    months = min(max(int(months or 1), 1), tenor)
    tsaman_naqdy = principal + first_margin
    monthly = (debt - tsaman_naqdy) / tenor
    qimah_haliyyah = tsaman_naqdy + monthly * months
    rest = _round_half_down(qimah_haliyyah - settled)
    if rest < remaining_principal:
        due, basis = remaining_principal, 'pokok'
    else:
        due, basis = rest, 'pupmsjt'
    due = min(due, remaining_receivable)
    return {
        'tsaman_naqdy': tsaman_naqdy,
        'monthly_margin': monthly,
        'months': months,
        'qimah_haliyyah': _round_half_down(qimah_haliyyah),
        'settled': settled,
        'rest_pupmsjt': rest,
        'remaining_principal': remaining_principal,
        'due': due,
        'basis': basis,
        'discount': round_rp(remaining_receivable - due),
    }


class KoperasiMurabahahAkad(models.Model):
    _name = 'koperasi.murabahah.akad'
    _description = 'Akad Murabahah'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_akad desc, id desc'

    name = fields.Char(string='No. Akad', required=True, copy=False, readonly=True, default='/', index='trigram',
                       tracking=True)
    company_id = fields.Many2one('res.company', string='Perusahaan', required=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Mata Uang')
    partner_id = fields.Many2one('res.partner', string='Anggota / Nasabah', required=True, tracking=True, index=True)
    partner_status = fields.Selection(related='partner_id.koperasi_status', string='Status Keanggotaan')
    member_no = fields.Char(related='partner_id.koperasi_member_no', string='No. Anggota')
    state = fields.Selection(
        [
            ('draft', 'Pengajuan'),
            ('disetujui', 'Disetujui'),
            ('barang_dibeli', 'Barang Dibeli'),
            ('aktif', 'Aktif'),
            ('lunas', 'Lunas'),
            ('batal', 'Batal'),
        ],
        string='Status', default='draft', required=True, tracking=True, copy=False, index=True)
    date_request = fields.Date(string='Tanggal Pengajuan', default=fields.Date.context_today)
    date_akad = fields.Date(string='Tanggal Akad', tracking=True, copy=False)
    date_done = fields.Date(string='Tanggal Lunas', copy=False, readonly=True)

    product_desc = fields.Char(string='Barang', required=True)
    product_id = fields.Many2one('product.product', string='Produk')
    supplier_id = fields.Many2one('res.partner', string='Pemasok')
    note = fields.Text(string='Catatan')

    # Specification and contract terms (OJK murabahah guideline: Bab I no. 13, Bab III A no. 10-12, Bab V E)
    product_brand = fields.Char(string='Merek')
    product_model = fields.Char(string='Tipe / Model')
    product_color = fields.Char(string='Warna')
    product_serial = fields.Char(string='No. Seri / IMEI / Rangka')
    product_serial2 = fields.Char(string='No. Mesin / Seri Lain')
    product_condition = fields.Selection([('baru', 'Baru'), ('bekas', 'Bekas')], string='Kondisi', default='baru')
    product_spec = fields.Text(string='Spesifikasi Lain')
    supplier_invoice_ref = fields.Char(string='No. Faktur Pemasok')
    khiyar_days = fields.Integer(
        string='Batas Khiyar (hari)', default=3,
        help="Batas hari setelah serah terima untuk menukar barang yang cacat (hak khiyar anggota).")
    khiyar_terms = fields.Text(string='Jenis Cacat yang Dapat Ditukar', default=DEFAULT_KHIYAR_TERMS)
    tazir_terms = fields.Text(
        string="Ketentuan Ta'zir",
        help="Besaran atau rumus denda ta'zir yang disepakati. Kosongkan jika akad tidak mengenakan denda.")
    date_supplier_handover = fields.Date(string='Serah Terima Pemasok ke Koperasi')
    date_member_handover = fields.Date(string='Serah Terima Koperasi ke Anggota')
    handover_place = fields.Char(string='Tempat Serah Terima')
    akad_explained = fields.Boolean(string='Klausul Akad Sudah Dijelaskan',
                                    help="Pemahaman anggota atas klausul akad sudah dikonfirmasi (Bab IV no. 5).")
    akad_copy_given = fields.Boolean(string='Salinan Akad Diserahkan', help="Bab IV no. 6.")

    # Wa'd and wakalah (OJK guideline Bab V A-B): separate documents made before the murabahah contract
    purchase_method = fields.Selection(
        [('langsung', 'Dibeli langsung oleh Koperasi'), ('wakalah', 'Diwakilkan kepada Anggota/pihak lain (wakalah)')],
        string='Cara Pembelian Barang', default='langsung', required=True, tracking=True)
    wad_date = fields.Date(string="Tanggal Janji Pembelian (Wa'd)", tracking=True,
                           help="Janji anggota untuk membeli barang dari koperasi. Dibuat sebelum dan terpisah dari akad.")
    wakalah_date = fields.Date(string='Tanggal Akad Wakalah', tracking=True)
    wakil_id = fields.Many2one('res.partner', string='Wakil Pembelian', tracking=True,
                               help="Penerima kuasa pembelian. Umumnya anggota itu sendiri.")
    wakalah_scope = fields.Text(string='Ruang Lingkup Wakalah', default=DEFAULT_WAKALAH_SCOPE)
    wakalah_max_price = fields.Monetary(string='Batas Harga Pembelian',
                                        help="Harga maksimum yang boleh dibayar wakil. Kosong = harga perolehan.")

    # Feasibility analysis
    income_source = fields.Char(string='Sumber Penghasilan / Pekerjaan')
    monthly_income = fields.Monetary(string='Penghasilan per Bulan')
    other_obligations = fields.Monetary(string='Kewajiban Lain per Bulan',
                                        help="Cicilan/kewajiban rutin di luar koperasi.")
    dependents = fields.Integer(string='Jumlah Tanggungan')
    financing_purpose = fields.Selection([('konsumtif', 'Konsumtif'), ('produktif', 'Produktif / Usaha')],
                                         string='Tujuan Pembiayaan', default='konsumtif')
    purpose_note = fields.Char(string='Keterangan Tujuan')
    analysis_note = fields.Text(string='Catatan Analisis',
                                help="Karakter, kemampuan bayar, modal, agunan, kondisi (5C) dan hal lain yang relevan.")
    officer_recommendation = fields.Selection(
        [('layak', 'Layak'), ('layak_syarat', 'Layak dengan syarat'), ('tidak_layak', 'Tidak layak')],
        string='Rekomendasi Petugas', tracking=True)
    analyst_id = fields.Many2one('res.users', string='Analis', default=lambda self: self.env.user)
    analysis_date = fields.Date(string='Tanggal Analisis')
    existing_installments = fields.Monetary(string='Angsuran Akad Aktif Lain', compute='_compute_dsr',
                                            help="Angsuran per bulan akad murabahah lain yang masih aktif atas nama anggota ini.")
    total_monthly_obligation = fields.Monetary(string='Total Kewajiban per Bulan', compute='_compute_dsr')
    dsr = fields.Float(string='DSR (%)', compute='_compute_dsr', digits=(16, 1),
                       help="Debt service ratio: total kewajiban per bulan dibanding penghasilan per bulan.")
    dsr_over_limit = fields.Boolean(string='DSR Melebihi Batas', compute='_compute_dsr')
    is_pengurus_financing = fields.Boolean(string='Pembiayaan untuk Pengurus', compute='_compute_is_pengurus_financing',
                                           store=True)

    # Approval (who, when, on what basis)
    pengajuan_id = fields.Many2one('koperasi.murabahah.pengajuan', string='Pengajuan', readonly=True, copy=False,
                                   index=True)
    partner_risk_level = fields.Selection(related='partner_id.koperasi_risk_level', string='Tingkat Risiko KYC')
    penjamin_id = fields.Many2one('res.partner', string='Penjamin (Kafalah)', tracking=True,
                                  domain="[('koperasi_status', '=', 'anggota')]",
                                  help="Anggota aktif yang menjamin pembayaran pembiayaan ini (Fatwa DSN-MUI 11/2000).")
    penjamin_relation = fields.Char(string='Hubungan Penjamin')
    approved_by_id = fields.Many2one('res.users', string='Disetujui Oleh', readonly=True, copy=False, tracking=True)
    approval_date = fields.Date(string='Tanggal Persetujuan', readonly=True, copy=False)
    approval_note = fields.Text(string='Dasar Persetujuan', copy=False, tracking=True,
                                help="Wajib jika DSR melebihi batas, rekomendasi tidak layak, atau pembiayaan untuk pengurus "
                                     "(mis. keputusan rapat pengurus/pengawas tanggal ...).")

    # Down payment returned after a cancelled contract (OJK guideline Bab III B.1.f)
    dp_refund_move_id = fields.Many2one('account.move', string='Jurnal Pengembalian Uang Muka', copy=False, readonly=True)
    dp_refund_amount = fields.Monetary(string='Uang Muka Dikembalikan', copy=False, readonly=True)
    dp_real_cost = fields.Monetary(string='Biaya Riil Dipotong', copy=False, readonly=True)
    dp_held = fields.Monetary(string='Uang Muka Masih Dipegang', compute='_compute_dp_held',
                              help="Saldo akun Uang Muka Murabahah untuk akad ini.")

    # Breakdown of the acquisition cost (OJK guideline Bab III B.1): optional, but when used it must add up
    purchase_price = fields.Monetary(string='Harga Pokok Pembelian', tracking=True,
                                     help="Harga barang dari pemasok sebelum diskon.")
    direct_cost = fields.Monetary(string='Biaya Langsung', tracking=True,
                                  help="Biaya perolehan sebelum akad: ongkos kirim, asuransi kirim, perakitan.")
    supplier_discount = fields.Monetary(string='Diskon Pemasok', tracking=True,
                                        help="Diskon yang diterima koperasi saat membeli; mengurangi harga perolehan.")
    cost_price = fields.Monetary(string='Harga Perolehan', tracking=True,
                                 help="Harga pokok barang yang dibeli koperasi.")
    down_payment = fields.Monetary(string='Uang Muka', tracking=True)
    margin_pct = fields.Float(string='Margin (%)', digits=(5, 2), default=20.0, tracking=True)
    margin_amount = fields.Monetary(
        string='Margin', compute='_compute_margin_amount', store=True, readonly=False, precompute=True,
        tracking=True, help="Margin = % x (harga perolehan - uang muka), flat, tidak tergantung tenor.")
    sale_price = fields.Monetary(string='Harga Jual', compute='_compute_amounts', store=True, precompute=True,
                                 help="Harga perolehan + margin. Tetap selama akad.")
    financed_amount = fields.Monetary(string='Total Piutang', compute='_compute_amounts', store=True, precompute=True,
                                      help="Harga jual - uang muka = total yang diangsur.")
    tenor = fields.Integer(string='Tenor (bulan)', default=12, tracking=True)
    installment_amount = fields.Monetary(
        string='Angsuran per Bulan', compute='_compute_installment_amount', store=True, readonly=False,
        precompute=True)
    first_due_date = fields.Date(string='Jatuh Tempo Angsuran Pertama', copy=False)

    line_ids = fields.One2many('koperasi.murabahah.angsuran', 'akad_id', string='Jadwal Angsuran', copy=False)
    payment_ids = fields.One2many('koperasi.murabahah.payment', 'akad_id', string='Pembayaran', copy=False)
    payment_count = fields.Integer(compute='_compute_payment_count')

    purchase_move_id = fields.Many2one('account.move', string='Jurnal/Tagihan Pembelian', copy=False, readonly=True)
    down_payment_move_id = fields.Many2one('account.move', string='Jurnal Uang Muka', copy=False, readonly=True)
    akad_move_id = fields.Many2one('account.move', string='Jurnal Akad', copy=False, readonly=True)
    move_ids = fields.One2many('account.move', 'murabahah_akad_id', string='Jurnal')
    move_count = fields.Integer(compute='_compute_move_count')

    is_migrated = fields.Boolean(string='Akad Saldo Awal', readonly=True, copy=False,
                                 help="Akad berjalan yang diimpor. Saldo awalnya sudah ada di jurnal saldo awal.")
    opening_move_id = fields.Many2one('account.move', string='Jurnal Saldo Awal', readonly=True, copy=False)
    agunan_ids = fields.One2many('koperasi.murabahah.agunan', 'akad_id', string='Agunan', copy=False)
    agunan_count = fields.Integer(string='Jumlah Agunan', compute='_compute_agunan')
    agunan_value_held = fields.Monetary(string='Nilai Taksiran Agunan Dipegang', compute='_compute_agunan')
    agunan_coverage = fields.Float(string='Cakupan Agunan (%)', compute='_compute_agunan', digits=(16, 1),
                                   help="Nilai taksiran agunan yang dipegang dibanding sisa piutang.")
    reschedule_ids = fields.One2many('koperasi.murabahah.reschedule', 'akad_id', string='Restrukturisasi',
                                     copy=False)
    reschedule_count = fields.Integer(string='Jumlah Restrukturisasi', compute='_compute_reschedule_count',
                                      store=True)

    # Balances from the schedule (stored)
    amount_paid = fields.Monetary(string='Total Angsuran Diterima', compute='_compute_balances', store=True)
    margin_recognized = fields.Monetary(string='Margin Diakui', compute='_compute_balances', store=True)
    discount_amount = fields.Monetary(string='Potongan Margin', compute='_compute_balances', store=True)
    remaining_receivable = fields.Monetary(string='Sisa Piutang', compute='_compute_balances', store=True)
    remaining_margin = fields.Monetary(string='Sisa Margin', compute='_compute_balances', store=True)
    remaining_principal = fields.Monetary(string='Sisa Pokok', compute='_compute_balances', store=True)

    # Arrears depend on today, so they are not stored
    arrears_amount = fields.Monetary(string='Tunggakan', compute='_compute_arrears', search='_search_arrears_amount')
    arrears_days = fields.Integer(string='Hari Tunggakan', compute='_compute_arrears')
    arrears_count = fields.Integer(string='Angsuran Tertunggak', compute='_compute_arrears')
    collectibility = fields.Selection(COLLECTIBILITY, string='Kolektibilitas', compute='_compute_arrears')
    next_due_date = fields.Date(string='Jatuh Tempo Berikutnya', compute='_compute_arrears')

    # Ledger control (posted journal items tagged with this contract)
    ledger_receivable_balance = fields.Monetary(string='Saldo Buku Besar Piutang', compute='_compute_ledger')
    ledger_deferred_margin_balance = fields.Monetary(string='Saldo Buku Besar Margin Ditangguhkan',
                                                     compute='_compute_ledger')
    ledger_mismatch = fields.Boolean(string='Selisih Buku Besar', compute='_compute_ledger')

    _name_company_uniq = models.Constraint(
        'unique(name, company_id)',
        'Nomor akad harus unik.',
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends('cost_price', 'down_payment', 'margin_pct')
    def _compute_margin_amount(self):
        for akad in self:
            akad.margin_amount = round_rp((akad.margin_pct or 0.0) / 100.0 * ((akad.cost_price or 0.0) - (akad.down_payment or 0.0)))

    @api.depends('cost_price', 'down_payment', 'margin_amount')
    def _compute_amounts(self):
        for akad in self:
            akad.sale_price = (akad.cost_price or 0.0) + (akad.margin_amount or 0.0)
            akad.financed_amount = akad.sale_price - (akad.down_payment or 0.0)

    @api.depends('financed_amount', 'tenor', 'company_id.murabahah_installment_rounding')
    def _compute_installment_amount(self):
        for akad in self:
            if akad.tenor > 0 and akad.financed_amount > 0:
                akad.installment_amount = akad._round_installment(akad.financed_amount / akad.tenor)
            else:
                akad.installment_amount = 0.0

    @api.depends('line_ids.paid_principal', 'line_ids.paid_margin', 'line_ids.discount_margin',
                 'financed_amount', 'margin_amount', 'state')
    def _compute_balances(self):
        for akad in self:
            paid_principal = sum(akad.line_ids.mapped('paid_principal'))
            paid_margin = sum(akad.line_ids.mapped('paid_margin'))
            discount = sum(akad.line_ids.mapped('discount_margin'))
            akad.amount_paid = paid_principal + paid_margin
            akad.margin_recognized = paid_margin
            akad.discount_amount = discount
            if akad.state == 'batal':
                akad.remaining_receivable = akad.remaining_margin = akad.remaining_principal = 0.0
                continue
            # Invariants (CLAUDE.md section 6)
            akad.remaining_receivable = akad.financed_amount - akad.amount_paid - discount
            akad.remaining_margin = akad.margin_amount - paid_margin - discount
            akad.remaining_principal = akad.remaining_receivable - akad.remaining_margin

    def _compute_payment_count(self):
        for akad in self:
            akad.payment_count = len(akad.payment_ids)

    @api.depends('agunan_ids.state', 'agunan_ids.appraisal_value', 'remaining_receivable')
    def _compute_agunan(self):
        for akad in self:
            held = akad.agunan_ids.filtered(lambda a: a.state == 'dipegang')
            akad.agunan_count = len(akad.agunan_ids)
            akad.agunan_value_held = sum(held.mapped('appraisal_value'))
            akad.agunan_coverage = (akad.agunan_value_held / akad.remaining_receivable * 100.0
                                    if akad.remaining_receivable > 0 else 0.0)

    def _remind_agunan_return(self):
        """Contract settled or cancelled while the cooperative still holds collateral: schedule a to-do."""
        for akad in self:
            held = akad.agunan_ids.filtered(lambda a: a.state == 'dipegang')
            if not held:
                continue
            from .agunan import RETURN_REMINDER
            if akad.sudo().activity_ids.filtered(lambda act: act.summary == RETURN_REMINDER):
                continue
            listing = ", ".join("%s (%s)" % (a.name, a.description) for a in held)
            akad.sudo().activity_schedule(
                'mail.mail_activity_data_todo', summary=RETURN_REMINDER,
                note=self.env._("Akad %(akad)s %(state)s. Kembalikan agunan: %(list)s.",
                                akad=akad.name, state=dict(self._fields['state'].selection)[akad.state].lower(),
                                list=listing),
                user_id=self.env.user.id)

    @api.depends('reschedule_ids')
    def _compute_reschedule_count(self):
        for akad in self:
            akad.reschedule_count = len(akad.reschedule_ids)

    def _compute_move_count(self):
        for akad in self:
            akad.move_count = len(akad.move_ids)

    def _compute_arrears(self):
        today = fields.Date.context_today(self)
        for akad in self:
            company = akad.company_id
            open_lines = akad.line_ids.filtered(lambda l: l.residual > 0.5).sorted('sequence') \
                if akad.state == 'aktif' else akad.line_ids.browse()
            overdue = open_lines.filtered(lambda l: l.date_due < today)
            akad.arrears_amount = sum(overdue.mapped('residual'))
            akad.arrears_count = len(overdue)
            akad.arrears_days = (today - overdue[0].date_due).days if overdue else 0
            upcoming = open_lines.filtered(lambda l: l.date_due >= today)
            akad.next_due_date = upcoming[0].date_due if upcoming else False
            days = akad.arrears_days
            if days <= 0:
                akad.collectibility = 'lancar'
            elif days <= company.murabahah_days_dpk:
                akad.collectibility = 'dpk'
            elif days <= company.murabahah_days_kurang_lancar:
                akad.collectibility = 'kurang_lancar'
            elif days <= company.murabahah_days_diragukan:
                akad.collectibility = 'diragukan'
            else:
                akad.collectibility = 'macet'

    def _search_arrears_amount(self, operator, value):
        ops = {'>': float.__gt__, '>=': float.__ge__, '<': float.__lt__, '<=': float.__le__,
               '=': float.__eq__, '!=': float.__ne__}
        if operator not in ops:
            raise UserError(self.env._("Operator pencarian tunggakan tidak didukung."))
        akads = self.search([('state', '=', 'aktif')])
        return [('id', 'in', [a.id for a in akads if ops[operator](float(a.arrears_amount), float(value or 0.0))])]

    def _compute_ledger(self):
        for akad in self:
            company = akad.company_id
            receivable = deferred = 0.0
            if akad.id:
                lines = self.env['account.move.line'].sudo().search([
                    ('murabahah_akad_id', '=', akad.id), ('parent_state', '=', 'posted')])
                receivable = sum(lines.filtered(
                    lambda l: l.account_id == company.murabahah_receivable_account_id).mapped('balance'))
                # Deferred margin is a credit balance; show it as a positive amount
                deferred = -sum(lines.filtered(
                    lambda l: l.account_id == company.murabahah_deferred_margin_account_id).mapped('balance'))
            akad.ledger_receivable_balance = receivable
            akad.ledger_deferred_margin_balance = deferred
            akad.ledger_mismatch = akad.state in ('aktif', 'lunas') and (
                not float_is_zero(receivable - akad.remaining_receivable, precision_digits=2)
                or not float_is_zero(deferred - akad.remaining_margin, precision_digits=2))

    # ------------------------------------------------------------------
    # Constraints / ORM
    # ------------------------------------------------------------------
    @api.depends('partner_id.koperasi_is_pengurus')
    def _compute_is_pengurus_financing(self):
        for akad in self:
            akad.is_pengurus_financing = bool(akad.partner_id.koperasi_is_pengurus)

    @api.depends('partner_id', 'installment_amount', 'monthly_income', 'other_obligations', 'company_id.murabahah_max_dsr')
    def _compute_dsr(self):
        for akad in self:
            others = self.env['koperasi.murabahah.akad'].sudo().search([
                ('partner_id', '=', akad.partner_id.id), ('state', '=', 'aktif'),
                ('id', '!=', akad._origin.id or 0)]) if akad.partner_id else self.browse()
            akad.existing_installments = sum(others.mapped('installment_amount'))
            akad.total_monthly_obligation = (akad.installment_amount or 0.0) + akad.existing_installments + (
                akad.other_obligations or 0.0)
            akad.dsr = akad.total_monthly_obligation / akad.monthly_income * 100.0 if akad.monthly_income else 0.0
            limit = akad.company_id.murabahah_max_dsr
            akad.dsr_over_limit = bool(akad.monthly_income and limit and akad.dsr > limit)

    @api.model
    def _penjamin_check(self, partner, penjamin):
        """Problems that make ``penjamin`` unacceptable as guarantor of ``partner`` (list of messages)."""
        problems = []
        if penjamin == partner:
            problems.append(self.env._("Penjamin tidak boleh pemohon sendiri."))
        if penjamin.koperasi_status != 'anggota':
            problems.append(self.env._("Penjamin %s bukan anggota aktif.", penjamin.name))
        overdue = self.sudo().search([('partner_id', '=', penjamin.id), ('state', '=', 'aktif')]).filtered(
            lambda a: a.arrears_amount > 0)
        if overdue:
            problems.append(self.env._("Penjamin %(name)s masih menunggak (%(akad)s).", name=penjamin.name,
                                       akad=", ".join(overdue.mapped('name'))))
        return problems

    def _check_not_own(self, action):
        """Conflict of interest: nobody acts on his or her own financing."""
        for akad in self:
            if not self.env.su and akad.partner_id._koperasi_is_user(self.env.user):
                raise UserError(self.env._(
                    "Benturan kepentingan: %(user)s tidak boleh %(action)s akad %(akad)s atas namanya sendiri. "
                    "Minta pengurus lain.", user=self.env.user.name, action=action, akad=akad.name))

    def _check_approval_rules(self):
        self.ensure_one()
        company = self.company_id
        self._check_not_own(self.env._("menyetujui"))
        if company.murabahah_require_application and not self.is_migrated:
            if not self.pengajuan_id:
                raise UserError(self.env._(
                    "Akad %s tidak berasal dari Pengajuan. Buat lewat Murabahah > Pengajuan (KYC dan survei) "
                    "sebelum disetujui.", self.name))
            if not self.pengajuan_id.kyc_date or self.pengajuan_id.state != 'analisis':
                raise UserError(self.env._(
                    "Pengajuan %s belum selesai KYC dan survei.", self.pengajuan_id.name))
            if self.partner_id != self.pengajuan_id.partner_id:
                raise UserError(self.env._("Pemohon akad %s berbeda dengan pemohon pengajuan.", self.name))
        if not self.monthly_income or not self.officer_recommendation:
            raise UserError(self.env._(
                "Akad %s: isi analisis kelayakan (penghasilan per bulan dan rekomendasi petugas) sebelum menyetujui.",
                self.name))
        note = (self.approval_note or '').strip()
        reasons = []
        if self.dsr_over_limit:
            reasons.append(self.env._("DSR %(dsr)s%% melebihi batas %(max)s%%",
                                      dsr=round(self.dsr, 1), max=company.murabahah_max_dsr))
        if self.officer_recommendation == 'tidak_layak':
            reasons.append(self.env._("rekomendasi petugas: tidak layak"))
        if self.is_pengurus_financing:
            reasons.append(self.env._("pembiayaan untuk pengurus"))
        if self.partner_id.sudo().koperasi_risk_level == 'tinggi':
            reasons.append(self.env._("tingkat risiko KYC tinggi"))
        if self.penjamin_id:
            if self.penjamin_id._koperasi_is_user(self.env.user) and not self.env.su:
                raise UserError(self.env._(
                    "Benturan kepentingan: %(user)s adalah penjamin akad %(akad)s dan tidak boleh menyetujuinya.",
                    user=self.env.user.name, akad=self.name))
            problems = self._penjamin_check(self.partner_id, self.penjamin_id)
            if problems:
                raise UserError(self.env._("Akad %(akad)s:\n%(p)s", akad=self.name, p="\n".join(problems)))
        if self.partner_id.koperasi_status != 'anggota':
            if company.murabahah_non_member_policy == 'penjamin' and not self.penjamin_id:
                raise UserError(self.env._(
                    "Akad %s: pemohon bukan anggota, wajib ada penjamin dari anggota aktif (kafalah).", self.name))
            if company.murabahah_non_member_policy == 'tolak':
                raise UserError(self.env._(
                    "Akad %s: pemohon bukan anggota aktif, sedangkan kebijakan koperasi hanya membiayai anggota.",
                    self.name))
            if company.murabahah_non_member_policy == 'dasar':
                reasons.append(self.env._("pemohon bukan anggota"))
        if reasons and not note:
            raise UserError(self.env._(
                "Akad %(akad)s: isi Dasar Persetujuan karena %(why)s.", akad=self.name, why="; ".join(reasons)))
        limit = company.murabahah_pengurus_limit
        if self.is_pengurus_financing and limit:
            outstanding = sum(self.sudo().search([
                ('partner_id', '=', self.partner_id.id), ('state', 'in', ('disetujui', 'barang_dibeli', 'aktif')),
                ('id', '!=', self.id)]).mapped(lambda a: a.remaining_receivable if a.state == 'aktif' else a.financed_amount))
            if float_compare(outstanding + self.financed_amount, limit, precision_digits=2) > 0:
                raise UserError(self.env._(
                    "Plafon pembiayaan pengurus %(limit)s terlampaui: sisa pembiayaan %(out)s + akad ini %(new)s.",
                    limit=format_rp(limit), out=format_rp(outstanding), new=format_rp(self.financed_amount)))

    def _compute_dp_held(self):
        for akad in self:
            account = akad.company_id.murabahah_down_payment_account_id
            held = 0.0
            if akad.id and account:
                lines = self.env['account.move.line'].sudo().search([
                    ('murabahah_akad_id', '=', akad.id), ('parent_state', '=', 'posted'), ('account_id', '=', account.id)])
                held = -sum(lines.mapped('balance'))
            akad.dp_held = held

    def _has_cost_breakdown(self):
        self.ensure_one()
        return bool(self.purchase_price or self.direct_cost or self.supplier_discount)

    @api.onchange('purchase_price', 'direct_cost', 'supplier_discount')
    def _onchange_cost_breakdown(self):
        for akad in self:
            if akad._has_cost_breakdown():
                akad.cost_price = (akad.purchase_price or 0.0) + (akad.direct_cost or 0.0) - (akad.supplier_discount or 0.0)

    @api.onchange('purchase_method', 'partner_id')
    def _onchange_purchase_method(self):
        for akad in self:
            if akad.purchase_method == 'wakalah' and not akad.wakil_id:
                akad.wakil_id = akad.partner_id

    @api.constrains('purchase_price', 'direct_cost', 'supplier_discount', 'cost_price')
    def _check_cost_breakdown(self):
        for akad in self:
            if not akad._has_cost_breakdown():
                continue
            if akad.purchase_price < 0 or akad.direct_cost < 0 or akad.supplier_discount < 0:
                raise ValidationError(self.env._("Rincian harga perolehan tidak boleh negatif."))
            total = akad.purchase_price + akad.direct_cost - akad.supplier_discount
            if float_compare(total, akad.cost_price, precision_digits=2):
                raise ValidationError(self.env._(
                    "Akad %(name)s: harga pokok pembelian + biaya langsung - diskon (%(total)s) "
                    "harus sama dengan harga perolehan (%(cost)s).",
                    name=akad.name, total=format_rp(total), cost=format_rp(akad.cost_price)))

    def _check_wakalah_before_purchase(self, purchase_date):
        """Wakalah must exist before the agent buys (Bab V B.6) and the buyer is the cooperative."""
        self.ensure_one()
        if self.purchase_method != 'wakalah':
            return
        if not self.wakalah_date or not self.wakil_id:
            raise UserError(self.env._(
                "Akad %s memakai wakalah: isi tanggal akad wakalah dan wakil pembelian sebelum mencatat pembelian.",
                self.name))
        if purchase_date and self.wakalah_date > purchase_date:
            raise UserError(self.env._(
                "Akad wakalah (%(wakalah)s) harus dibuat sebelum barang dibeli (%(purchase)s).",
                wakalah=format_date_id(self.wakalah_date), purchase=format_date_id(purchase_date)))
        if self.wakalah_max_price and float_compare(self.cost_price, self.wakalah_max_price, precision_digits=2) > 0:
            raise UserError(self.env._(
                "Harga perolehan %(cost)s melebihi batas harga wakalah %(max)s.",
                cost=format_rp(self.cost_price), max=format_rp(self.wakalah_max_price)))

    def _check_sequence_before_signing(self):
        """The goods are owned by the cooperative before the contract, and the promise comes first (Bab III A, Bab V A)."""
        self.ensure_one()
        purchase_date = self.purchase_move_id.date
        if purchase_date and self.date_akad and purchase_date > self.date_akad:
            raise UserError(self.env._(
                "Barang dibeli %(purchase)s, setelah tanggal akad %(akad)s. Barang harus sudah dimiliki koperasi "
                "sebelum akad murabahah.",
                purchase=format_date_id(purchase_date), akad=format_date_id(self.date_akad)))
        if self.wad_date and self.date_akad and self.wad_date > self.date_akad:
            raise UserError(self.env._("Janji pembelian (wa'd) harus dibuat sebelum akad murabahah."))
        if self.wakalah_date and self.date_akad and self.wakalah_date > self.date_akad:
            raise UserError(self.env._("Akad wakalah harus dibuat sebelum akad murabahah."))

    @api.constrains('cost_price', 'down_payment', 'margin_amount', 'tenor', 'margin_pct')
    def _check_numbers(self):
        for akad in self:
            if akad.cost_price < 0 or akad.down_payment < 0 or akad.margin_amount < 0 or akad.margin_pct < 0:
                raise ValidationError(self.env._("Harga, uang muka, dan margin tidak boleh negatif."))
            if akad.cost_price and float_compare(akad.down_payment, akad.cost_price, precision_digits=2) >= 0:
                raise ValidationError(self.env._("Uang muka harus lebih kecil dari harga perolehan."))
            if akad.tenor < 1:
                raise ValidationError(self.env._("Tenor minimal 1 bulan."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('koperasi.murabahah.akad') or '/'
        return super().create(vals_list)

    def write(self, vals):
        analysis = ANALYSIS_FIELDS.intersection(vals)
        if analysis and not self.env.context.get('murabahah_allow_write'):
            for akad in self.filtered(lambda a: a.state != 'draft'):
                raise UserError(self.env._(
                    "Akad %s sudah disetujui: analisis kelayakan tidak boleh diubah.", akad.name))
        spec = SPEC_FIELDS.intersection(vals)
        if spec and not self.env.context.get('murabahah_allow_write'):
            for akad in self.filtered(lambda a: a.state in SIGNED_STATES):
                raise UserError(self.env._(
                    "Akad %s sudah ditandatangani: data barang dan ketentuan akad tidak boleh diubah.", akad.name))
        locked = LOCKED_FIELDS.intersection(vals)
        if locked and not self.env.context.get('murabahah_allow_write'):
            for akad in self:
                if akad.state != 'draft':
                    raise UserError(self.env._(
                        "Akad %(name)s berstatus %(state)s: angka akad tidak boleh diubah. "
                        "Koreksi dilakukan lewat pembatalan dan akad baru.",
                        name=akad.name, state=dict(self._fields['state'].selection)[akad.state]))
        res = super().write(vals)
        if 'state' in vals:
            for akad in self.filtered('pengajuan_id'):
                akad.pengajuan_id.sudo()._sync_from_akad(akad.state)
        return res

    def unlink(self):
        if any(akad.state != 'draft' for akad in self):
            raise UserError(self.env._("Hanya akad berstatus Pengajuan yang boleh dihapus. Gunakan Batal."))
        return super().unlink()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _round_installment(self, amount):
        rounding = self.company_id.murabahah_installment_rounding or 1.0
        return float_round(amount, precision_rounding=rounding)

    def _check_group(self, xmlid):
        if not self.env.su and not self.env.user.has_group(xmlid):
            group = self.env.ref(xmlid)
            raise UserError(self.env._("Tindakan ini hanya untuk grup Koperasi / %s.", group.name))

    def _check_config(self, *field_names):
        company = self.company_id
        missing = [company._fields[f].string for f in field_names if not company[f]]
        if missing:
            raise UserError(self.env._(
                "Pengaturan murabahah belum lengkap: %s. Isi di Koperasi > Konfigurasi > Pengaturan.",
                ", ".join(missing)))

    def _move_line(self, account, name, debit=0.0, credit=0.0):
        self.ensure_one()
        return Command.create({
            'account_id': account.id,
            'partner_id': self.partner_id.id,
            'name': name,
            'debit': debit,
            'credit': credit,
            'murabahah_akad_id': self.id,
        })

    def _create_move(self, journal, date, ref, lines, payment=None):
        """Create and post a balanced entry traceable to this contract (ref = akad number)."""
        self.ensure_one()
        move = self.env['account.move'].sudo().create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': date,
            'ref': ref,
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'murabahah_akad_id': self.id,
            'murabahah_payment_id': payment.id if payment else False,
            'line_ids': [line for line in lines if line[2]['debit'] or line[2]['credit']],
        })
        move.action_post()
        return move

    def _get_schedule_values(self):
        self.ensure_one()
        if not self.first_due_date:
            raise UserError(self.env._("Isi tanggal jatuh tempo angsuran pertama."))
        parts = split_schedule(self.financed_amount, self.margin_amount, self.tenor, self.installment_amount)
        return [
            {
                'sequence': i + 1,
                'date_due': self.first_due_date + relativedelta(months=i),
                'amount_principal': principal,
                'amount_margin': margin,
            }
            for i, (principal, margin) in enumerate(parts)
        ]

    def _generate_schedule(self):
        for akad in self:
            if akad.state in ('aktif', 'lunas', 'batal') or akad.payment_ids:
                raise UserError(self.env._("Jadwal akad %s sudah terkunci.", akad.name))
            akad.line_ids.with_context(murabahah_allow_write=True).unlink()
            akad.with_context(murabahah_allow_write=True).write({
                'line_ids': [Command.create(vals) for vals in akad._get_schedule_values()],
            })

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def action_compute_schedule(self):
        for akad in self:
            if not akad.first_due_date:
                start = akad.date_akad or fields.Date.context_today(self)
                akad.first_due_date = start + relativedelta(months=1)
        self._generate_schedule()

    def action_approve(self):
        self._check_group(GROUP_PENGURUS)
        for akad in self:
            if akad.state != 'draft':
                raise UserError(self.env._("Hanya pengajuan yang bisa disetujui."))
            if akad.cost_price <= 0 or akad.tenor < 1:
                raise UserError(self.env._("Isi harga perolehan dan tenor sebelum menyetujui."))
            akad._check_approval_rules()
            if not akad.first_due_date:
                start = akad.date_akad or fields.Date.context_today(self)
                akad.first_due_date = start + relativedelta(months=1)
            akad._generate_schedule()
            today = fields.Date.context_today(self)
            vals = {'state': 'disetujui', 'approved_by_id': self.env.user.id, 'approval_date': today}
            if not akad.analysis_date:
                vals['analysis_date'] = today
            akad.write(vals)

    def action_view_pengajuan(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'koperasi.murabahah.pengajuan',
            'res_id': self.pengajuan_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_reset_draft(self):
        self._check_group(GROUP_PENGURUS)
        for akad in self:
            if akad.state != 'disetujui' or akad.purchase_move_id or akad.down_payment_move_id:
                raise UserError(self.env._("Hanya akad disetujui tanpa jurnal yang bisa dikembalikan ke pengajuan."))
            akad.write({'state': 'draft', 'approved_by_id': False, 'approval_date': False})

    def action_open_purchase_wizard(self):
        self.ensure_one()
        self._check_group(GROUP_PETUGAS)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Catat Pembelian Barang'),
            'res_model': 'koperasi.murabahah.purchase.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_akad_id': self.id},
        }

    def action_open_down_payment_wizard(self):
        self.ensure_one()
        self._check_group(GROUP_PETUGAS)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Terima Uang Muka'),
            'res_model': 'koperasi.murabahah.down.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_akad_id': self.id},
        }

    def _record_purchase(self, date, mode, journal=None):
        """Purchase of the goods by the cooperative: Dr Persediaan / Cr Kas (mode 'kas')
        or a vendor bill on the inventory account (mode 'utang')."""
        self.ensure_one()
        self._check_group(GROUP_PETUGAS)
        if self.state != 'disetujui':
            raise UserError(self.env._("Pembelian barang dicatat setelah akad disetujui."))
        self._check_wakalah_before_purchase(date)
        self._check_config('murabahah_inventory_account_id')
        inventory = self.company_id.murabahah_inventory_account_id
        ref = "%s - Pembelian %s" % (self.name, self.product_desc)
        if mode == 'kas':
            if not journal or not journal.default_account_id:
                raise UserError(self.env._("Pilih jurnal kas/bank yang punya akun default."))
            move = self.env['account.move'].sudo().create({
                'move_type': 'entry',
                'journal_id': journal.id,
                'date': date,
                'ref': ref,
                'partner_id': (self.supplier_id or self.partner_id).id,
                'murabahah_akad_id': self.id,
                'line_ids': [
                    Command.create({'account_id': inventory.id, 'name': ref, 'debit': self.cost_price,
                                    'partner_id': (self.supplier_id or self.partner_id).id,
                                    'murabahah_akad_id': self.id}),
                    Command.create({'account_id': journal.default_account_id.id, 'name': ref,
                                    'credit': self.cost_price,
                                    'partner_id': (self.supplier_id or self.partner_id).id,
                                    'murabahah_akad_id': self.id}),
                ],
            })
        else:
            if not self.supplier_id:
                raise UserError(self.env._("Isi pemasok untuk membuat tagihan pembelian."))
            move = self.env['account.move'].sudo().create({
                'move_type': 'in_invoice',
                'partner_id': self.supplier_id.id,
                'invoice_date': date,
                'date': date,
                'ref': self.name,
                'murabahah_akad_id': self.id,
                'invoice_line_ids': [Command.create({
                    'name': ref,
                    'quantity': 1.0,
                    'price_unit': self.cost_price,
                    'account_id': inventory.id,
                    'tax_ids': [Command.clear()],
                    'murabahah_akad_id': self.id,
                })],
            })
        move.action_post()
        self.write({'purchase_move_id': move.id, 'state': 'barang_dibeli'})
        self.message_post(body=self.env._("Pembelian barang dicatat: %s", move.name))
        return move

    def _record_down_payment(self, date, journal):
        """Down payment received: Dr Kas / Cr Uang Muka Murabahah (liability)."""
        self.ensure_one()
        self._check_group(GROUP_PETUGAS)
        if self.state not in ('disetujui', 'barang_dibeli'):
            raise UserError(self.env._("Uang muka diterima setelah akad disetujui dan sebelum akad aktif."))
        if self.down_payment_move_id or self.down_payment <= 0:
            raise UserError(self.env._("Tidak ada uang muka yang perlu dicatat."))
        self._check_config('murabahah_down_payment_account_id')
        if not journal.default_account_id:
            raise UserError(self.env._("Jurnal %s tidak punya akun default.", journal.name))
        ref = "%s - Uang Muka" % self.name
        move = self._create_move(journal, date, ref, [
            self._move_line(journal.default_account_id, ref, debit=self.down_payment),
            self._move_line(self.company_id.murabahah_down_payment_account_id, ref, credit=self.down_payment),
        ])
        self.down_payment_move_id = move
        return move

    def action_activate(self):
        """Sign the contract: Dr Piutang (harga jual) / Cr Persediaan (pokok) / Cr Margin Ditangguhkan,
        and offset the down payment: Dr Uang Muka / Cr Piutang."""
        self._check_group(GROUP_PENGURUS)
        self._check_not_own(self.env._("mengaktifkan"))
        for akad in self:
            if akad.state != 'barang_dibeli':
                raise UserError(self.env._("Akad hanya bisa diaktifkan setelah barang dibeli (milik koperasi)."))
            if akad.down_payment > 0 and not akad.down_payment_move_id:
                raise UserError(self.env._("Uang muka belum diterima."))
            akad._check_config('murabahah_journal_id', 'murabahah_receivable_account_id',
                               'murabahah_inventory_account_id', 'murabahah_deferred_margin_account_id',
                               'murabahah_down_payment_account_id')
            company = akad.company_id
            if not akad.date_akad:
                akad.date_akad = fields.Date.context_today(self)
            akad._check_sequence_before_signing()
            if akad.first_due_date and akad.first_due_date <= akad.date_akad:
                raise UserError(self.env._("Jatuh tempo pertama harus setelah tanggal akad."))
            if not akad.first_due_date:
                akad.with_context(murabahah_allow_write=True).first_due_date = akad.date_akad + relativedelta(months=1)
            akad._generate_schedule()
            ref = "%s - Akad Murabahah %s" % (akad.name, akad.product_desc)
            lines = [
                akad._move_line(company.murabahah_receivable_account_id, ref, debit=akad.sale_price),
                akad._move_line(company.murabahah_inventory_account_id, ref, credit=akad.cost_price),
                akad._move_line(company.murabahah_deferred_margin_account_id, ref, credit=akad.margin_amount),
            ]
            if akad.down_payment:
                dp_ref = "%s - Uang muka diperhitungkan" % akad.name
                lines += [
                    akad._move_line(company.murabahah_down_payment_account_id, dp_ref, debit=akad.down_payment),
                    akad._move_line(company.murabahah_receivable_account_id, dp_ref, credit=akad.down_payment),
                ]
            move = akad._create_move(company.murabahah_journal_id, akad.date_akad, ref, lines)
            akad.write({'akad_move_id': move.id, 'state': 'aktif'})

    def action_cancel(self):
        self._check_group(GROUP_PENGURUS)
        for akad in self:
            if akad.state in ('lunas', 'batal'):
                raise UserError(self.env._("Akad lunas atau batal tidak bisa dibatalkan."))
            if akad.payment_ids.filtered(lambda p: p.state == 'posted'):
                raise UserError(self.env._(
                    "Akad %s sudah punya pembayaran. Batalkan pembayarannya dulu.", akad.name))
            if akad.akad_move_id:
                akad.akad_move_id.sudo()._reverse_moves(
                    [{'ref': "%s - Pembatalan akad" % akad.name, 'date': fields.Date.context_today(self),
                      'murabahah_akad_id': akad.id}], cancel=True)
            if akad.purchase_move_id or akad.down_payment_move_id:
                akad.message_post(body=self.env._(
                    "Akad dibatalkan. Jurnal pembelian barang dan uang muka tidak dibalik otomatis: "
                    "barang tetap di persediaan. Uang muka dikembalikan lewat tombol \"Kembalikan Uang Muka\"."))
            akad.state = 'batal'
            akad._remind_agunan_return()

    def action_open_payment_wizard(self):
        self.ensure_one()
        self._check_group(GROUP_PETUGAS)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Terima Angsuran'),
            'res_model': 'koperasi.murabahah.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_akad_id': self.id},
        }

    def action_open_payoff_wizard(self):
        self.ensure_one()
        self._check_group(GROUP_PENGURUS)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Pelunasan Dipercepat'),
            'res_model': 'koperasi.murabahah.payoff.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_akad_id': self.id},
        }

    def action_open_dp_refund_wizard(self):
        self.ensure_one()
        self._check_group(GROUP_PENGURUS)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Kembalikan Uang Muka'),
            'res_model': 'koperasi.murabahah.dp.refund.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_akad_id': self.id},
        }

    def _refund_down_payment(self, date, journal, real_cost=0.0, note=False):
        """Cancelled contract: return the down payment less the real costs incurred (biaya riil).

        Dr Uang Muka Murabahah (held) | Cr Kas (returned) | Cr Pendapatan Biaya Riil (real cost)
        """
        self.ensure_one()
        self._check_group(GROUP_PENGURUS)
        if self.state != 'batal':
            raise UserError(self.env._("Uang muka dikembalikan setelah akad dibatalkan."))
        if self.dp_refund_move_id:
            raise UserError(self.env._("Uang muka akad %s sudah dikembalikan.", self.name))
        held = round_rp(self.dp_held)
        if held <= 0:
            raise UserError(self.env._("Tidak ada uang muka akad %s yang masih dipegang koperasi.", self.name))
        real_cost = round_rp(real_cost or 0.0)
        if real_cost < 0 or float_compare(real_cost, held, precision_digits=2) > 0:
            raise UserError(self.env._(
                "Biaya riil harus di antara 0 dan uang muka (%s). Kekurangan di atas uang muka ditagih terpisah.",
                format_rp(held)))
        if real_cost and not (note or '').strip():
            raise UserError(self.env._("Isi rincian biaya riil yang dipotong."))
        self._check_config('murabahah_down_payment_account_id')
        if real_cost:
            self._check_config('murabahah_real_cost_account_id')
        if not journal or journal.type not in ('cash', 'bank') or not journal.default_account_id:
            raise UserError(self.env._("Pilih jurnal kas/bank yang punya akun default."))
        company = self.company_id
        refund = round_rp(held - real_cost)
        ref = "%s - Pengembalian uang muka" % self.name
        lines = [
            self._move_line(company.murabahah_down_payment_account_id, ref, debit=held),
            self._move_line(journal.default_account_id, ref, credit=refund),
        ]
        if real_cost:
            lines.append(self._move_line(company.murabahah_real_cost_account_id,
                                         "%s - Biaya riil: %s" % (self.name, note.strip()), credit=real_cost))
        move = self._create_move(journal, date, ref, lines)
        self.with_context(murabahah_allow_write=True).write({
            'dp_refund_move_id': move.id, 'dp_refund_amount': refund, 'dp_real_cost': real_cost})
        self.message_post(body=self.env._(
            "Uang muka %(held)s: dikembalikan %(refund)s, biaya riil dipotong %(cost)s%(note)s.",
            held=format_rp(held), refund=format_rp(refund), cost=format_rp(real_cost),
            note=(" (%s)" % note.strip()) if real_cost else ""))
        return move

    def action_open_reschedule_wizard(self):
        self.ensure_one()
        self._check_group(GROUP_PENGURUS)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Penjadwalan Kembali'),
            'res_model': 'koperasi.murabahah.reschedule.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_akad_id': self.id},
        }

    def action_view_payments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Pembayaran'),
            'res_model': 'koperasi.murabahah.payment',
            'view_mode': 'list,form',
            'domain': [('akad_id', '=', self.id)],
            'context': {'default_akad_id': self.id, 'create': False},
        }

    def action_view_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Jurnal'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': ['|', ('murabahah_akad_id', '=', self.id), ('line_ids.murabahah_akad_id', '=', self.id)],
            'context': {'create': False},
        }

    # ------------------------------------------------------------------
    # Payments
    # ------------------------------------------------------------------
    def _payoff_calculation(self, date):
        """PUPMSJT figures for an early payoff on ``date`` (see ``pupmsjt``)."""
        self.ensure_one()
        start = self.date_akad or date
        months = (date.year * 12 + date.month) - (start.year * 12 + start.month) + 1
        first = self.line_ids.sorted('sequence')[:1]
        return pupmsjt(
            principal=self.cost_price - self.down_payment,
            first_margin=first.amount_margin,
            debt=self.financed_amount,
            tenor=self.tenor,
            months=months,
            settled=self.financed_amount - self.remaining_receivable,
            remaining_principal=self.remaining_principal,
            remaining_receivable=self.remaining_receivable,
        )

    def _open_lines(self):
        return self.line_ids.filtered(lambda l: l.residual > 0.5).sorted('sequence')

    def _allocate(self, amount, discount=0.0):
        """Allocate ``amount`` (+ an installment discount, potongan tagihan) to the oldest open installments first.

        The discount reduces the margin of the installments it settles (PSAK 102 par. 24, example 2).

        A fully paid installment recognises all of its remaining margin; a partial
        payment recognises margin in proportion to the installment's margin share.
        Returns a list of dicts {line, principal, margin, discount}.
        """
        self.ensure_one()
        discount = round_rp(discount or 0.0)
        if discount < 0:
            raise UserError(self.env._("Potongan tagihan tidak boleh negatif."))
        remaining = round_rp((amount or 0.0) + discount)
        if round_rp(amount or 0.0) <= 0:
            raise UserError(self.env._("Jumlah pembayaran harus lebih dari nol."))
        if float_compare(remaining, self.remaining_receivable, precision_digits=2) > 0:
            raise UserError(self.env._(
                "Pembayaran %(amount)s melebihi sisa piutang %(rest)s. Gunakan pelunasan atau kurangi jumlahnya.",
                amount=amount, rest=self.remaining_receivable))
        allocations = []
        for line in self._open_lines():
            if remaining <= 0:
                break
            take = min(remaining, line.residual)
            margin_residual = line.amount_margin - line.paid_margin - line.discount_margin
            principal_residual = line.amount_principal - line.paid_principal
            if float_compare(take, line.residual, precision_digits=2) == 0:
                margin = margin_residual
            else:
                margin = round_rp(take * line.amount_margin / line.amount_total) if line.amount_total else 0.0
                margin = max(min(margin, margin_residual, take), take - principal_residual, 0.0)
            allocations.append({'line': line, 'principal': round_rp(take - margin), 'margin': margin, 'discount': 0.0})
            remaining = round_rp(remaining - take)
        left = discount
        for allocation in allocations:
            if left <= 0:
                break
            take = min(left, allocation['margin'])
            allocation['margin'] = round_rp(allocation['margin'] - take)
            allocation['discount'] = take
            left = round_rp(left - take)
        if left > 0:
            raise UserError(self.env._(
                "Potongan tagihan %s melebihi margin angsuran yang dibayar. Potongan hanya mengurangi margin.",
                format_rp(discount)))
        return allocations

    def _allocate_payoff(self, discount):
        """Close every open installment; ``discount`` is taken off margin starting from the latest installments."""
        self.ensure_one()
        if discount < 0 or float_compare(discount, self.remaining_margin, precision_digits=2) > 0:
            raise UserError(self.env._("Potongan margin harus di antara 0 dan sisa margin (%s).", self.remaining_margin))
        allocations = {}
        left = round_rp(discount)
        for line in reversed(self._open_lines()):
            margin_residual = line.amount_margin - line.paid_margin - line.discount_margin
            line_discount = min(left, margin_residual)
            left = round_rp(left - line_discount)
            allocations[line.id] = {
                'line': line,
                'principal': round_rp(line.amount_principal - line.paid_principal),
                'margin': round_rp(margin_residual - line_discount),
                'discount': line_discount,
            }
        return [allocations[line.id] for line in self._open_lines()]

    def _register_payment(self, date, journal, amount=0.0, tazir=0.0, memo=False, payoff=False, discount=0.0,
                          discount_type=False, discount_note=False, tazir_confirmed=False):
        """Post the cash entry and the margin recognition entry, and allocate to the schedule.

        Cash entry (cash/bank journal):   Dr Kas | Cr Piutang Murabahah | Cr Dana Kebajikan (ta'zir)
        Margin entry (murabahah journal): Dr Margin Ditangguhkan | Cr Pendapatan Margin
                                          Dr Margin Ditangguhkan | Cr Piutang (potongan pelunasan)
        """
        self.ensure_one()
        self._check_group(GROUP_PENGURUS if payoff else GROUP_PETUGAS)
        if self.state != 'aktif':
            raise UserError(self.env._("Pembayaran hanya untuk akad aktif."))
        if tazir < 0:
            raise UserError(self.env._("Denda ta'zir tidak boleh negatif."))
        if tazir:
            # PSAK 102 par. 13 / OJK Bab V E: only as agreed in the contract, not for force majeure
            if not (self.tazir_terms or '').strip():
                raise UserError(self.env._(
                    "Akad %s tidak mengatur denda ta'zir, jadi denda tidak boleh dikenakan.", self.name))
            if not tazir_confirmed:
                raise UserError(self.env._(
                    "Konfirmasi dulu bahwa anggota mampu membayar tetapi sengaja menunda (bukan force majeure)."))
        self._check_config('murabahah_journal_id', 'murabahah_receivable_account_id',
                           'murabahah_deferred_margin_account_id', 'murabahah_income_account_id')
        if tazir:
            self._check_config('murabahah_charity_account_id')
        if not journal or journal.type not in ('cash', 'bank') or not journal.default_account_id:
            raise UserError(self.env._("Pilih jurnal kas/bank yang punya akun default."))
        if discount and not self.env.su and not self.env.user.has_group(GROUP_PENGURUS):
            raise UserError(self.env._("Potongan hanya boleh diberikan Pengurus."))
        if discount:
            self._check_not_own(self.env._("memberi potongan pada"))
        if discount and not payoff:
            if discount_type not in ('tepat_waktu', 'keringanan'):
                raise UserError(self.env._("Pilih jenis potongan tagihan."))
            if not (discount_note or '').strip():
                raise UserError(self.env._("Isi alasan potongan tagihan."))
        if payoff and discount:
            discount_type = 'pelunasan'

        allocations = self._allocate_payoff(discount) if payoff else self._allocate(amount, discount)
        principal = round_rp(sum(a['principal'] for a in allocations))
        margin = round_rp(sum(a['margin'] for a in allocations))
        disc = round_rp(sum(a['discount'] for a in allocations))
        paid = round_rp(principal + margin)
        disc_total = disc

        payment = self.env['koperasi.murabahah.payment'].create({
            'akad_id': self.id,
            'date': date,
            'journal_id': journal.id,
            'payment_type': 'pelunasan' if payoff else 'angsuran',
            'amount': paid,
            'amount_tazir': tazir,
            'memo': memo,
            'discount_type': discount_type if disc_total else False,
            'discount_note': (discount_note or '').strip() or False if disc_total else False,
            'line_ids': [Command.create({
                'angsuran_id': a['line'].id,
                'amount_principal': a['principal'],
                'amount_margin': a['margin'],
                'amount_discount': a['discount'],
            }) for a in allocations],
        })
        company = self.company_id
        label = self.env._("Pelunasan") if payoff else self.env._("Angsuran")
        installments = ", ".join(str(a['line'].sequence) for a in allocations)
        ref = "%s - %s ke-%s" % (self.name, label, installments)
        cash_lines = [
            self._move_line(journal.default_account_id, ref, debit=paid + tazir),
            self._move_line(company.murabahah_receivable_account_id, ref, credit=paid),
        ]
        if tazir:
            cash_lines.append(self._move_line(
                company.murabahah_charity_account_id, "%s - Denda ta'zir" % self.name, credit=tazir))
        values = {}
        if paid or tazir:
            values['move_id'] = self._create_move(journal, date, ref, cash_lines, payment=payment).id
        if margin or disc:
            margin_ref = "%s - Pengakuan margin %s ke-%s" % (self.name, label.lower(), installments)
            margin_lines = [
                self._move_line(company.murabahah_deferred_margin_account_id, margin_ref, debit=margin),
                self._move_line(company.murabahah_income_account_id, margin_ref, credit=margin),
            ]
            if disc:
                disc_ref = "%s - %s" % (self.name, self.env._("Potongan pelunasan dipercepat") if payoff
                                        else self.env._("Potongan tagihan"))
                margin_lines += [
                    self._move_line(company.murabahah_deferred_margin_account_id, disc_ref, debit=disc),
                    self._move_line(company.murabahah_receivable_account_id, disc_ref, credit=disc),
                ]
            values['margin_move_id'] = self._create_move(
                company.murabahah_journal_id, date, margin_ref, margin_lines, payment=payment).id
        payment.write(values)
        self._check_done()
        return payment

    def _check_done(self):
        for akad in self:
            if akad.state == 'aktif' and float_is_zero(akad.remaining_receivable, precision_digits=2):
                last = akad.payment_ids.filtered(lambda p: p.state == 'posted').sorted('date')[-1:]
                akad.write({'state': 'lunas', 'date_done': last.date or fields.Date.context_today(self)})
                akad._remind_agunan_return()
            elif akad.state == 'lunas' and not float_is_zero(akad.remaining_receivable, precision_digits=2):
                akad.write({'state': 'aktif', 'date_done': False})

    # ------------------------------------------------------------------
    # Documents (akad, surat pengakuan utang, berita acara serah terima)
    # ------------------------------------------------------------------
    def get_document_values(self):
        """Formatted values for the printed documents (Indonesian wording and rupiah format)."""
        self.ensure_one()
        company = self.company_id
        lines = self.line_ids.sorted('sequence')
        spec = [(label, value) for label, value in [
            ('Barang', self.product_desc),
            ('Merek', self.product_brand),
            ('Tipe / Model', self.product_model),
            ('Warna', self.product_color),
            ('No. Seri / IMEI / Rangka', self.product_serial),
            ('No. Mesin / Seri Lain', self.product_serial2),
            ('Kondisi', dict(self._fields['product_condition'].selection).get(self.product_condition)),
            ('Spesifikasi Lain', self.product_spec),
        ] if value]
        cost_lines = [(label, format_rp(value)) for label, value in [
            ('Harga pokok pembelian', self.purchase_price),
            ('Biaya langsung', self.direct_cost),
            ('Diskon pemasok', -self.supplier_discount if self.supplier_discount else 0.0),
        ] if value] if self._has_cost_breakdown() else []
        purchase = self.purchase_move_id
        partner = self.partner_id
        dots = '.' * 40
        return {
            'dots': dots,
            'partner_address': ', '.join(filter(None, [partner.street, partner.street2, partner.city])) or dots,
            'partner_phone': partner.phone or dots,
            'penjamin_address': ', '.join(filter(None, [self.penjamin_id.street, self.penjamin_id.street2,
                                                        self.penjamin_id.city])) or dots,
            'penjamin_phone': self.penjamin_id.phone or dots,
            'member_no': self.member_no or '-',
            'company_address': ', '.join(filter(None, [company.partner_id.street, company.partner_id.city])) or dots,
            'company': company,
            'city': company.murabahah_document_city or company.partner_id.city or '',
            'signatory': company.murabahah_signatory_name or '',
            'signatory_title': company.murabahah_signatory_title or 'Pengurus',
            'approved': company.murabahah_template_approved,
            'date_akad': format_date_id(self.date_akad),
            'day_akad': format_day_id(self.date_akad),
            'date_supplier_handover': format_date_id(self.date_supplier_handover),
            'day_supplier_handover': format_day_id(self.date_supplier_handover),
            'date_member_handover': format_date_id(self.date_member_handover),
            'day_member_handover': format_day_id(self.date_member_handover),
            'date_purchase': format_date_id(purchase.date) if purchase else '',
            'date_wad': format_date_id(self.wad_date),
            'date_wakalah': format_date_id(self.wakalah_date),
            'day_wakalah': format_day_id(self.wakalah_date),
            'wakalah_max_price': format_rp(self.wakalah_max_price or self.cost_price),
            'first_due': format_date_id(lines[:1].date_due),
            'last_due': format_date_id(lines[-1:].date_due),
            'count': len(lines),
            'spec': spec,
            'cost_lines': cost_lines,
            'cost': format_rp(self.cost_price),
            'down_payment': format_rp(self.down_payment),
            'principal': format_rp(self.cost_price - self.down_payment),
            'margin': format_rp(self.margin_amount),
            'margin_pct': ('%g' % self.margin_pct).replace('.', ','),
            'sale_price': format_rp(self.sale_price),
            'sale_price_words': terbilang(self.sale_price),
            'financed': format_rp(self.financed_amount),
            'financed_words': terbilang(self.financed_amount),
            'installment': format_rp(self.installment_amount),
            'installment_words': terbilang(self.installment_amount),
            'remaining': format_rp(self.remaining_receivable),
            'lines': [{'no': l.sequence, 'date': format_date_id(l.date_due), 'principal': format_rp(l.amount_principal),
                       'margin': format_rp(l.amount_margin), 'total': format_rp(l.amount_total)} for l in lines],
            'total_lines': format_rp(sum(lines.mapped('amount_total'))),
            'format_rp': format_rp,
            'format_date': format_date_id,
            'agunan': [{'type': dict(a._fields['agunan_type'].selection).get(a.agunan_type),
                        'description': a.description, 'document_no': a.document_no or '',
                        'value': format_rp(a.appraisal_value) if a.appraisal_value else ''}
                       for a in self.agunan_ids.filtered(lambda a: a.state in ('draft', 'dipegang'))],
        }

    # ------------------------------------------------------------------
    # Penjadwalan kembali (restrukturisasi), Fatwa DSN-MUI 48/2005
    # ------------------------------------------------------------------
    def _last_posted_payment(self):
        self.ensure_one()
        return self.payment_ids.filtered(lambda p: p.state == 'posted').sorted(lambda p: (p.date, p.id))[-1:]

    def _reschedule_plan(self, date, first_due_date, count=0, installment=0.0):
        """New schedule for what is still owed. The remaining receivable and margin are only
        spread again: they never grow (OJK murabahah guideline, restructuring point 4a)."""
        self.ensure_one()
        if self.state != 'aktif':
            raise UserError(self.env._("Penjadwalan kembali hanya untuk akad aktif."))
        open_lines = self._open_lines()
        rest = round_rp(sum(open_lines.mapped('residual')))
        rest_margin = round_rp(sum(l.amount_margin - l.paid_margin - l.discount_margin for l in open_lines))
        if float_compare(rest, 0.0, precision_digits=2) <= 0:
            raise UserError(self.env._("Akad %s tidak punya sisa angsuran.", self.name))
        if float_compare(rest, self.remaining_receivable, precision_digits=2) \
                or float_compare(rest_margin, self.remaining_margin, precision_digits=2):
            raise UserError(self.env._(
                "Sisa jadwal akad %s tidak sama dengan sisa piutang/margin. Periksa jadwal sebelum restrukturisasi.",
                self.name))
        if not date or not first_due_date:
            raise UserError(self.env._("Isi tanggal restrukturisasi dan jatuh tempo pertama yang baru."))
        last_payment = self._last_posted_payment()
        if last_payment and date < last_payment.date:
            raise UserError(self.env._(
                "Tanggal restrukturisasi tidak boleh sebelum pembayaran terakhir (%s).", last_payment.date))
        if first_due_date < date:
            raise UserError(self.env._("Jatuh tempo pertama yang baru tidak boleh sebelum tanggal restrukturisasi."))
        if count:
            if count < 1:
                raise UserError(self.env._("Jumlah angsuran baru minimal 1."))
            installment = rest if count == 1 else self._round_installment(rest / count)
        elif installment:
            installment = round_rp(installment)
            if installment <= 0:
                raise UserError(self.env._("Angsuran baru harus lebih dari nol."))
            count = max(1, math.ceil(rest / installment - 1e-9))
            if count == 1:
                installment = rest
        else:
            raise UserError(self.env._("Isi jumlah angsuran baru atau besar angsuran baru."))
        parts = split_schedule(rest, rest_margin, count, installment)
        return {
            'open_lines': open_lines,
            'rest': rest,
            'rest_margin': rest_margin,
            'count': count,
            'installment': installment,
            'lines': [{'date_due': first_due_date + relativedelta(months=i),
                       'amount_principal': principal, 'amount_margin': margin}
                      for i, (principal, margin) in enumerate(parts)],
        }

    def _reschedule(self, date, first_due_date, reason, count=0, installment=0.0):
        """Replace the unpaid part of the schedule. Installments already paid stay as they are; a partly
        paid installment is closed at what was paid. No journal entry: the balances do not change."""
        self.ensure_one()
        self._check_group(GROUP_PENGURUS)
        self._check_not_own(self.env._("menjadwal ulang"))
        if not (reason or '').strip():
            raise UserError(self.env._("Isi alasan penjadwalan kembali."))
        plan = self._reschedule_plan(date, first_due_date, count=count, installment=installment)
        open_lines = plan['open_lines']
        arrears_amount, arrears_days = self.arrears_amount, self.arrears_days
        old_schedule = "\n".join(
            "Ke-%s  %s  pokok %s  margin %s  sisa %s" % (
                line.sequence, line.date_due.strftime('%d/%m/%Y'), f"{line.amount_principal:,.0f}",
                f"{line.amount_margin:,.0f}", f"{line.residual:,.0f}")
            for line in open_lines)

        lines_model = self.env['koperasi.murabahah.angsuran'].with_context(murabahah_allow_write=True)
        # Lines that ever received an allocation cannot be deleted (ondelete restrict): close them at what was paid
        touched = open_lines.filtered(lambda l: l.allocation_ids)
        for line in touched:
            line.with_context(murabahah_allow_write=True).write({
                'amount_principal': line.paid_principal,
                'amount_margin': line.paid_margin + line.discount_margin,
            })
        (open_lines - touched).with_context(murabahah_allow_write=True).unlink()
        self.invalidate_recordset(['line_ids'])
        next_seq = max(self.line_ids.mapped('sequence') or [0]) + 1
        lines_model.create([dict(vals, akad_id=self.id, sequence=next_seq + i) for i, vals in enumerate(plan['lines'])])

        number = len(self.reschedule_ids) + 1
        record = self.env['koperasi.murabahah.reschedule'].create({
            'name': "%s/R%s" % (self.name, number),
            'akad_id': self.id,
            'sequence_no': number,
            'date': date,
            'user_id': self.env.user.id,
            'reason': reason.strip(),
            'remaining_receivable': plan['rest'],
            'remaining_margin': plan['rest_margin'],
            'arrears_amount': arrears_amount,
            'arrears_days': arrears_days,
            'old_count': len(open_lines),
            'new_count': plan['count'],
            'new_installment': plan['installment'],
            'first_due_date': plan['lines'][0]['date_due'],
            'last_due_date': plan['lines'][-1]['date_due'],
            'old_schedule': old_schedule,
            'last_payment_id': self._last_posted_payment().id,
        })
        # Invariant: nothing owed was added or removed
        self.invalidate_recordset()
        if float_compare(self.remaining_receivable, plan['rest'], precision_digits=2) \
                or float_compare(self.remaining_margin, plan['rest_margin'], precision_digits=2) \
                or float_compare(sum(self.line_ids.mapped('amount_total')), self.financed_amount, precision_digits=2):
            raise UserError(self.env._("Penjadwalan kembali mengubah sisa piutang. Dibatalkan."))
        self.message_post(body=self.env._(
            "Penjadwalan kembali %(no)s: sisa %(rest)s dibagi menjadi %(count)s angsuran x %(inst)s, "
            "mulai %(first)s. Alasan: %(reason)s",
            no=record.name, rest=f"{plan['rest']:,.0f}", count=plan['count'], inst=f"{plan['installment']:,.0f}",
            first=plan['lines'][0]['date_due'].strftime('%d/%m/%Y'), reason=record.reason))
        return record
