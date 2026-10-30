from odoo import api, fields, models


class KoperasiMurabahahDpRefundWizard(models.TransientModel):
    _name = 'koperasi.murabahah.dp.refund.wizard'
    _description = 'Kembalikan Uang Muka Murabahah'

    akad_id = fields.Many2one('koperasi.murabahah.akad', string='Akad', required=True, readonly=True)
    partner_id = fields.Many2one(related='akad_id.partner_id')
    company_id = fields.Many2one(related='akad_id.company_id')
    currency_id = fields.Many2one(related='akad_id.currency_id')
    dp_held = fields.Monetary(related='akad_id.dp_held')
    date = fields.Date(string='Tanggal', required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one(
        'account.journal', string='Kas/Bank', required=True,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]")
    real_cost = fields.Monetary(string='Biaya Riil Dipotong',
                                help="Biaya yang benar-benar sudah dikeluarkan koperasi. Kosongkan jika tidak ada.")
    real_cost_note = fields.Char(string='Rincian Biaya Riil')
    refund_amount = fields.Monetary(string='Dikembalikan ke Anggota', compute='_compute_refund_amount')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        akad = self.env['koperasi.murabahah.akad'].browse(res.get('akad_id'))
        if akad and 'journal_id' in fields_list:
            res['journal_id'] = akad.company_id.murabahah_cash_journal_id.id
        return res

    @api.depends('dp_held', 'real_cost')
    def _compute_refund_amount(self):
        for wizard in self:
            wizard.refund_amount = wizard.dp_held - (wizard.real_cost or 0.0)

    def action_confirm(self):
        self.ensure_one()
        self.akad_id._refund_down_payment(self.date, self.journal_id, real_cost=self.real_cost,
                                          note=self.real_cost_note)
        return {'type': 'ir.actions.act_window_close'}
