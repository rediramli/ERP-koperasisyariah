from odoo import api, fields, models


class KoperasiMurabahahDownPaymentWizard(models.TransientModel):
    _name = 'koperasi.murabahah.down.payment.wizard'
    _description = 'Terima Uang Muka Murabahah'

    akad_id = fields.Many2one('koperasi.murabahah.akad', string='Akad', required=True, readonly=True)
    company_id = fields.Many2one(related='akad_id.company_id')
    currency_id = fields.Many2one(related='akad_id.currency_id')
    amount = fields.Monetary(related='akad_id.down_payment', string='Uang Muka')
    date = fields.Date(string='Tanggal', required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one(
        'account.journal', string='Kas/Bank', required=True,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        akad = self.env['koperasi.murabahah.akad'].browse(res.get('akad_id'))
        if akad and 'journal_id' in fields_list:
            res['journal_id'] = akad.company_id.murabahah_cash_journal_id.id
        return res

    def action_confirm(self):
        self.ensure_one()
        self.akad_id._record_down_payment(self.date, self.journal_id)
        return {'type': 'ir.actions.act_window_close'}
