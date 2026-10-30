from odoo import api, fields, models
from odoo.exceptions import UserError

AMOUNT_FIELDS = {'amount_principal', 'amount_margin', 'date_due', 'sequence', 'akad_id'}


class KoperasiMurabahahAngsuran(models.Model):
    _name = 'koperasi.murabahah.angsuran'
    _description = 'Jadwal Angsuran Murabahah'
    _order = 'akad_id, sequence'

    akad_id = fields.Many2one('koperasi.murabahah.akad', string='Akad', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one(related='akad_id.partner_id', store=True, string='Anggota / Nasabah')
    akad_state = fields.Selection(related='akad_id.state', store=True, string='Status Akad')
    company_id = fields.Many2one(related='akad_id.company_id', store=True)
    currency_id = fields.Many2one(related='akad_id.currency_id')
    sequence = fields.Integer(string='Ke-', required=True)
    date_due = fields.Date(string='Jatuh Tempo', required=True, index=True)
    amount_principal = fields.Monetary(string='Porsi Pokok', required=True)
    amount_margin = fields.Monetary(string='Porsi Margin', required=True)
    amount_total = fields.Monetary(string='Total Angsuran', compute='_compute_amount_total', store=True)

    allocation_ids = fields.One2many('koperasi.murabahah.payment.line', 'angsuran_id', string='Pembayaran')
    paid_principal = fields.Monetary(string='Pokok Terbayar', compute='_compute_paid', store=True)
    paid_margin = fields.Monetary(string='Margin Terbayar', compute='_compute_paid', store=True)
    discount_margin = fields.Monetary(string='Potongan Margin', compute='_compute_paid', store=True)
    paid_total = fields.Monetary(string='Terbayar', compute='_compute_paid', store=True)
    residual = fields.Monetary(string='Sisa', compute='_compute_paid', store=True)
    date_paid = fields.Date(string='Tanggal Bayar Terakhir', compute='_compute_paid', store=True)
    state = fields.Selection(
        [('belum', 'Belum Bayar'), ('sebagian', 'Sebagian'), ('lunas', 'Lunas')],
        string='Status Bayar', compute='_compute_paid', store=True)
    status = fields.Selection(
        [('belum', 'Belum Bayar'), ('sebagian', 'Sebagian'), ('lunas', 'Lunas'), ('telat', 'Telat')],
        string='Status', compute='_compute_status')
    days_late = fields.Integer(string='Hari Telat', compute='_compute_status')

    @api.depends('amount_principal', 'amount_margin')
    def _compute_amount_total(self):
        for line in self:
            line.amount_total = line.amount_principal + line.amount_margin

    @api.depends('amount_total', 'allocation_ids.amount_principal', 'allocation_ids.amount_margin',
                 'allocation_ids.amount_discount', 'allocation_ids.state', 'allocation_ids.date')
    def _compute_paid(self):
        for line in self:
            allocations = line.allocation_ids.filtered(lambda a: a.state == 'posted')
            line.paid_principal = sum(allocations.mapped('amount_principal'))
            line.paid_margin = sum(allocations.mapped('amount_margin'))
            line.discount_margin = sum(allocations.mapped('amount_discount'))
            line.paid_total = line.paid_principal + line.paid_margin
            line.residual = line.amount_total - line.paid_total - line.discount_margin
            line.date_paid = max(allocations.mapped('date')) if allocations else False
            if line.residual <= 0.5:
                line.state = 'lunas'
            elif line.paid_total or line.discount_margin:
                line.state = 'sebagian'
            else:
                line.state = 'belum'

    def _compute_status(self):
        today = fields.Date.context_today(self)
        for line in self:
            late = line.state != 'lunas' and line.date_due < today and line.akad_state == 'aktif'
            line.status = 'telat' if late else line.state
            line.days_late = (today - line.date_due).days if late else 0

    @api.depends('akad_id.name', 'sequence')
    def _compute_display_name(self):
        for line in self:
            line.display_name = "%s / %s" % (line.akad_id.name or '', line.sequence)

    def write(self, vals):
        if AMOUNT_FIELDS.intersection(vals) and not self.env.context.get('murabahah_allow_write'):
            if any(line.akad_id.state != 'draft' for line in self):
                raise UserError(self.env._("Jadwal angsuran akad yang sudah disetujui tidak boleh diubah."))
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get('murabahah_allow_write') and any(
                line.akad_id.state != 'draft' for line in self):
            raise UserError(self.env._("Jadwal angsuran akad yang sudah disetujui tidak boleh dihapus."))
        return super().unlink()
