from odoo import api, fields, models


class KoperasiMurabahahPaymentWizard(models.TransientModel):
    _name = 'koperasi.murabahah.payment.wizard'
    _description = 'Terima Angsuran Murabahah'

    akad_id = fields.Many2one('koperasi.murabahah.akad', string='Akad', required=True,
                              domain="[('state', '=', 'aktif')]")
    partner_id = fields.Many2one(related='akad_id.partner_id')
    company_id = fields.Many2one(related='akad_id.company_id')
    currency_id = fields.Many2one(related='akad_id.currency_id')
    remaining_receivable = fields.Monetary(related='akad_id.remaining_receivable')
    arrears_amount = fields.Monetary(related='akad_id.arrears_amount')
    date = fields.Date(string='Tanggal Bayar', required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one(
        'account.journal', string='Kas/Bank', required=True,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]")
    amount = fields.Monetary(string='Jumlah Angsuran', required=True)
    amount_tazir = fields.Monetary(string="Denda Ta'zir",
                                   help="Hanya jika diatur di akad. Dicatat ke Dana Kebajikan, bukan pendapatan koperasi.")
    tazir_confirmed = fields.Boolean(string='Anggota mampu tetapi sengaja menunda (bukan force majeure)')
    akad_tazir_terms = fields.Text(related='akad_id.tazir_terms')
    discount_amount = fields.Monetary(
        string='Potongan Tagihan',
        help="Opsional, khusus Pengurus (Fatwa DSN-MUI 46/2005). Mengurangi margin angsuran yang dibayar "
             "(PSAK 102 par. 24). Tidak diperjanjikan di akad.")
    discount_type = fields.Selection(
        [('tepat_waktu', 'Penghargaan bayar tepat waktu'), ('keringanan', 'Keringanan: kemampuan bayar menurun')],
        string='Jenis Potongan')
    discount_note = fields.Char(string='Alasan Potongan')
    preview_settled = fields.Monetary(string='Total Angsuran Diselesaikan', compute='_compute_preview')
    preview_discount = fields.Monetary(string='Potongan Margin', compute='_compute_preview')
    memo = fields.Char(string='Keterangan')
    preview_principal = fields.Monetary(string='Porsi Pokok', compute='_compute_preview')
    preview_margin = fields.Monetary(string='Margin Diakui', compute='_compute_preview')
    preview_installments = fields.Char(string='Dialokasikan ke Angsuran', compute='_compute_preview')
    preview_error = fields.Char(compute='_compute_preview')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        akad = self.env['koperasi.murabahah.akad'].browse(res.get('akad_id'))
        if akad:
            if 'journal_id' in fields_list:
                res['journal_id'] = akad.company_id.murabahah_cash_journal_id.id
            if 'amount' in fields_list:
                first_open = akad._open_lines()[:1]
                res['amount'] = akad.arrears_amount or first_open.residual
        return res

    @api.depends('akad_id', 'amount', 'discount_amount')
    def _compute_preview(self):
        for wizard in self:
            wizard.preview_principal = wizard.preview_margin = 0.0
            wizard.preview_settled = wizard.preview_discount = 0.0
            wizard.preview_installments = wizard.preview_error = False
            if not wizard.akad_id or wizard.amount <= 0:
                continue
            try:
                allocations = wizard.akad_id._allocate(wizard.amount, wizard.discount_amount)
            except Exception as error:  # noqa: BLE001 - only shown as a hint in the form
                wizard.preview_error = str(error.args[0]) if error.args else str(error)
                continue
            wizard.preview_principal = sum(a['principal'] for a in allocations)
            wizard.preview_margin = sum(a['margin'] for a in allocations)
            wizard.preview_discount = sum(a['discount'] for a in allocations)
            wizard.preview_settled = wizard.preview_principal + wizard.preview_margin + wizard.preview_discount
            wizard.preview_installments = ", ".join(
                "ke-%s%s" % (a['line'].sequence,
                             "" if a['principal'] + a['margin'] + a['discount'] >= a['line'].residual - 0.5
                             else " (sebagian)")
                for a in allocations)

    def action_confirm(self):
        self.ensure_one()
        payment = self.akad_id._register_payment(
            self.date, self.journal_id, amount=self.amount, tazir=self.amount_tazir, memo=self.memo,
            discount=self.discount_amount, discount_type=self.discount_type, discount_note=self.discount_note,
            tazir_confirmed=self.tazir_confirmed)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'koperasi.murabahah.payment',
            'res_id': payment.id,
            'view_mode': 'form',
        }
