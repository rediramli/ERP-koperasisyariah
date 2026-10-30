from odoo import api, fields, models
from odoo.exceptions import UserError

from ..utils import format_rp


class KoperasiMurabahahPayoffWizard(models.TransientModel):
    _name = 'koperasi.murabahah.payoff.wizard'
    _description = 'Pelunasan Dipercepat Murabahah'

    akad_id = fields.Many2one('koperasi.murabahah.akad', string='Akad', required=True, readonly=True)
    partner_id = fields.Many2one(related='akad_id.partner_id')
    company_id = fields.Many2one(related='akad_id.company_id')
    currency_id = fields.Many2one(related='akad_id.currency_id')
    payoff_method = fields.Selection(related='company_id.murabahah_payoff_method')
    akad_tazir_terms = fields.Text(related='akad_id.tazir_terms')
    remaining_receivable = fields.Monetary(related='akad_id.remaining_receivable')
    remaining_principal = fields.Monetary(related='akad_id.remaining_principal')
    remaining_margin = fields.Monetary(related='akad_id.remaining_margin')
    date = fields.Date(string='Tanggal Pelunasan', required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one(
        'account.journal', string='Kas/Bank', required=True,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]")

    # PUPMSJT (Fatwa DSN-MUI 153/2022, OJK guideline p. 14-15)
    calc_tsaman_naqdy = fields.Monetary(string='Tsaman Naqdy', compute='_compute_calc',
                                        help="Pokok pembiayaan + margin satu bulan.")
    calc_months = fields.Integer(string='Bulan Berjalan', compute='_compute_calc')
    calc_qimah_haliyyah = fields.Monetary(string='Qimah Haliyyah', compute='_compute_calc',
                                          help="Tsaman naqdy + margin waktu yang telah dilewati.")
    calc_settled = fields.Monetary(string='Angsuran Telah Dibayar', compute='_compute_calc')
    calc_rest = fields.Monetary(string='Sisa Harga PUPMSJT', compute='_compute_calc')
    calc_basis = fields.Char(string='Dasar Tagihan', compute='_compute_calc')
    calc_discount = fields.Monetary(string='Potongan Sesuai Rumus', compute='_compute_calc')

    discount_policy = fields.Selection(
        [('rumus', 'Sesuai rumus PUPMSJT'),
         ('tanpa', 'Anggota melunasi tanpa meminta potongan'),
         ('manual', 'Nilai lain (kebijakan Pengurus)')],
        string='Potongan', required=True,
        default=lambda self: 'rumus' if self.env.company.murabahah_payoff_method == 'pupmsjt' else 'manual')
    manual_discount = fields.Monetary(string='Potongan (Nilai Lain)')
    discount_note = fields.Char(string='Dasar / Alasan Potongan')
    discount_amount = fields.Monetary(string='Potongan Pelunasan', compute='_compute_discount_amount')
    amount_tazir = fields.Monetary(string="Denda Ta'zir", help="Hanya jika diatur di akad. Dicatat ke Dana Kebajikan.")
    tazir_confirmed = fields.Boolean(string='Anggota mampu tetapi sengaja menunda (bukan force majeure)')
    amount_to_pay = fields.Monetary(string='Jumlah Dibayar', compute='_compute_discount_amount')
    memo = fields.Char(string='Keterangan')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        akad = self.env['koperasi.murabahah.akad'].browse(res.get('akad_id'))
        if akad and 'journal_id' in fields_list:
            res['journal_id'] = akad.company_id.murabahah_cash_journal_id.id
        return res

    @api.depends('akad_id', 'date')
    def _compute_calc(self):
        for wizard in self:
            values = wizard.akad_id._payoff_calculation(wizard.date) if wizard.akad_id and wizard.date else {}
            wizard.calc_tsaman_naqdy = values.get('tsaman_naqdy', 0.0)
            wizard.calc_months = values.get('months', 0)
            wizard.calc_qimah_haliyyah = values.get('qimah_haliyyah', 0.0)
            wizard.calc_settled = values.get('settled', 0.0)
            wizard.calc_rest = values.get('rest_pupmsjt', 0.0)
            wizard.calc_basis = {
                'pupmsjt': self.env._("Sisa harga PUPMSJT"),
                'pokok': self.env._("Sisa pokok (sisa PUPMSJT lebih kecil dari sisa pokok)"),
            }.get(values.get('basis'), False)
            wizard.calc_discount = values.get('discount', 0.0)

    @api.depends('discount_policy', 'manual_discount', 'calc_discount', 'remaining_receivable', 'amount_tazir')
    def _compute_discount_amount(self):
        for wizard in self:
            if wizard.discount_policy == 'rumus':
                wizard.discount_amount = wizard.calc_discount
            elif wizard.discount_policy == 'manual':
                wizard.discount_amount = wizard.manual_discount
            else:
                wizard.discount_amount = 0.0
            wizard.amount_to_pay = wizard.remaining_receivable - wizard.discount_amount + wizard.amount_tazir

    def _discount_note(self):
        self.ensure_one()
        if self.discount_policy == 'rumus':
            return self.env._(
                "Rumus PUPMSJT: tsaman naqdy %(tn)s, bulan ke-%(n)s, qimah haliyyah %(qh)s, telah dibayar %(paid)s, "
                "sisa PUPMSJT %(rest)s; ditagih %(basis)s",
                tn=format_rp(self.calc_tsaman_naqdy), n=self.calc_months, qh=format_rp(self.calc_qimah_haliyyah),
                paid=format_rp(self.calc_settled), rest=format_rp(self.calc_rest), basis=self.calc_basis)
        return (self.discount_note or '').strip()

    def action_confirm(self):
        self.ensure_one()
        if self.discount_amount < 0 or self.discount_amount > self.remaining_margin + 0.005:
            raise UserError(self.env._("Potongan pelunasan harus di antara 0 dan sisa margin."))
        if self.discount_policy == 'manual' and not (self.discount_note or '').strip():
            raise UserError(self.env._("Isi dasar / alasan potongan dengan nilai lain."))
        if self.discount_policy == 'tanpa':
            note = self.env._("Anggota melunasi tanpa meminta potongan (pedoman OJK Bab III B.2.k).")
            memo = " - ".join(filter(None, [self.memo, note]))
        else:
            memo = self.memo
        payment = self.akad_id._register_payment(
            self.date, self.journal_id, tazir=self.amount_tazir, memo=memo, payoff=True,
            discount=self.discount_amount, discount_note=self._discount_note() if self.discount_amount else False,
            tazir_confirmed=self.tazir_confirmed)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'koperasi.murabahah.payment',
            'res_id': payment.id,
            'view_mode': 'form',
        }
