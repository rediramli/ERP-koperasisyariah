from odoo import api, fields, models


class KoperasiMurabahahPurchaseWizard(models.TransientModel):
    _name = 'koperasi.murabahah.purchase.wizard'
    _description = 'Catat Pembelian Barang Murabahah'

    akad_id = fields.Many2one('koperasi.murabahah.akad', string='Akad', required=True, readonly=True)
    currency_id = fields.Many2one(related='akad_id.currency_id')
    supplier_id = fields.Many2one(related='akad_id.supplier_id', readonly=False)
    amount = fields.Monetary(related='akad_id.cost_price', string='Harga Perolehan')
    date = fields.Date(string='Tanggal Pembelian', required=True, default=fields.Date.context_today)
    mode = fields.Selection(
        [('kas', 'Dibayar tunai (Kas/Bank)'), ('utang', 'Tagihan pemasok (Utang Usaha)')],
        string='Cara Bayar', required=True, default='kas')
    journal_id = fields.Many2one(
        'account.journal', string='Kas/Bank',
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]")
    company_id = fields.Many2one(related='akad_id.company_id')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        akad = self.env['koperasi.murabahah.akad'].browse(res.get('akad_id'))
        if akad and 'journal_id' in fields_list:
            res['journal_id'] = akad.company_id.murabahah_cash_journal_id.id
        return res

    def action_confirm(self):
        self.ensure_one()
        move = self.akad_id._record_purchase(self.date, self.mode, self.journal_id)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
        } if self.mode == 'utang' else {'type': 'ir.actions.act_window_close'}
