from odoo import api, fields, models
from odoo.exceptions import UserError

from .akad import GROUP_PENGURUS


class KoperasiMurabahahPayment(models.Model):
    _name = 'koperasi.murabahah.payment'
    _description = 'Pembayaran Angsuran Murabahah'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(string='Nomor', required=True, copy=False, readonly=True, default='/')
    akad_id = fields.Many2one('koperasi.murabahah.akad', string='Akad', required=True, ondelete='restrict',
                              index=True, readonly=True)
    partner_id = fields.Many2one(related='akad_id.partner_id', store=True, string='Anggota / Nasabah')
    company_id = fields.Many2one(related='akad_id.company_id', store=True)
    currency_id = fields.Many2one(related='akad_id.currency_id')
    date = fields.Date(string='Tanggal', required=True, readonly=True, default=fields.Date.context_today)
    payment_type = fields.Selection(
        [('angsuran', 'Angsuran'), ('pelunasan', 'Pelunasan Dipercepat'), ('saldo_awal', 'Saldo Awal (Migrasi)')],
        string='Jenis', required=True, default='angsuran', readonly=True)
    journal_id = fields.Many2one('account.journal', string='Kas/Bank', readonly=True)
    amount = fields.Monetary(string='Angsuran Diterima', readonly=True,
                             help="Bagian yang mengurangi piutang (pokok + margin).")
    amount_principal = fields.Monetary(string='Porsi Pokok', compute='_compute_amounts', store=True)
    amount_margin = fields.Monetary(string='Margin Diakui', compute='_compute_amounts', store=True)
    amount_discount = fields.Monetary(string='Potongan Margin', compute='_compute_amounts', store=True)
    amount_tazir = fields.Monetary(string="Denda Ta'zir", readonly=True,
                                   help="Dicatat ke Dana Kebajikan, bukan pendapatan koperasi.")
    amount_cash = fields.Monetary(string='Total Kas Diterima', compute='_compute_amounts', store=True)
    memo = fields.Char(string='Keterangan')
    discount_type = fields.Selection(
        [('pelunasan', 'Potongan pelunasan dipercepat'),
         ('tepat_waktu', 'Potongan tagihan: penghargaan bayar tepat waktu'),
         ('keringanan', 'Potongan tagihan: keringanan, kemampuan bayar menurun')],
        string='Jenis Potongan', readonly=True)
    discount_note = fields.Char(string='Dasar Potongan', readonly=True)
    line_ids = fields.One2many('koperasi.murabahah.payment.line', 'payment_id', string='Alokasi', readonly=True)
    move_id = fields.Many2one('account.move', string='Jurnal Kas', readonly=True, copy=False)
    margin_move_id = fields.Many2one('account.move', string='Jurnal Pengakuan Margin', readonly=True, copy=False)
    state = fields.Selection([('posted', 'Diposting'), ('cancel', 'Dibatalkan')], string='Status',
                             default='posted', required=True, readonly=True, tracking=True)

    @api.depends('line_ids.amount_principal', 'line_ids.amount_margin', 'line_ids.amount_discount',
                 'amount', 'amount_tazir', 'payment_type')
    def _compute_amounts(self):
        for payment in self:
            payment.amount_principal = sum(payment.line_ids.mapped('amount_principal'))
            payment.amount_margin = sum(payment.line_ids.mapped('amount_margin'))
            payment.amount_discount = sum(payment.line_ids.mapped('amount_discount'))
            payment.amount_cash = 0.0 if payment.payment_type == 'saldo_awal' else payment.amount + payment.amount_tazir

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('koperasi.murabahah.payment') or '/'
        return super().create(vals_list)

    def unlink(self):
        raise UserError(self.env._("Pembayaran tidak boleh dihapus. Gunakan Batalkan."))

    def action_cancel(self):
        """Reverse the entries of the latest payment and release its allocation."""
        akad_model = self.env['koperasi.murabahah.akad']
        if not self.env.su and not self.env.user.has_group(GROUP_PENGURUS):
            raise UserError(self.env._("Pembatalan pembayaran hanya untuk Pengurus."))
        for payment in self:
            if payment.state != 'posted':
                continue
            if payment.payment_type == 'saldo_awal':
                raise UserError(self.env._("Pembayaran saldo awal (migrasi) tidak bisa dibatalkan."))
            later = payment.akad_id.payment_ids.filtered(
                lambda p: p.state == 'posted' and p != payment and (p.date, p.id) > (payment.date, payment.id))
            if later:
                raise UserError(self.env._("Batalkan dulu pembayaran yang lebih baru: %s.", ", ".join(later.mapped('name'))))
            # A rescheduling was computed from the payments made so far: those stay final
            for reschedule in payment.akad_id.reschedule_ids:
                last = reschedule.last_payment_id
                if last and (payment.date, payment.id) <= (last.date, last.id):
                    raise UserError(self.env._(
                        "Pembayaran %(pay)s sudah diperhitungkan dalam restrukturisasi %(res)s dan tidak bisa dibatalkan.",
                        pay=payment.name, res=reschedule.name))
            moves = (payment.move_id | payment.margin_move_id).filtered(lambda m: m.state == 'posted')
            if moves:
                moves.sudo()._reverse_moves(
                    [{'ref': "%s - Batal %s" % (payment.akad_id.name, payment.name),
                      'date': fields.Date.context_today(self),
                      'murabahah_akad_id': payment.akad_id.id,
                      'murabahah_payment_id': payment.id} for _move in moves], cancel=True)
            payment.state = 'cancel'
            akad_model |= payment.akad_id
        akad_model._check_done()
        return True


class KoperasiMurabahahPaymentLine(models.Model):
    _name = 'koperasi.murabahah.payment.line'
    _description = 'Alokasi Pembayaran Murabahah'
    _order = 'date desc, id'

    payment_id = fields.Many2one('koperasi.murabahah.payment', string='Pembayaran', required=True,
                                 ondelete='cascade', index=True)
    angsuran_id = fields.Many2one('koperasi.murabahah.angsuran', string='Angsuran', required=True,
                                  ondelete='restrict', index=True)
    akad_id = fields.Many2one(related='payment_id.akad_id', store=True, string='Akad')
    partner_id = fields.Many2one(related='payment_id.partner_id', store=True, string='Anggota / Nasabah')
    company_id = fields.Many2one(related='payment_id.company_id', store=True)
    currency_id = fields.Many2one(related='payment_id.currency_id')
    date = fields.Date(related='payment_id.date', store=True, string='Tanggal')
    payment_type = fields.Selection(related='payment_id.payment_type', store=True, string='Jenis')
    state = fields.Selection(related='payment_id.state', store=True, string='Status')
    installment_no = fields.Integer(related='angsuran_id.sequence', string='Angsuran Ke-')
    amount_principal = fields.Monetary(string='Pokok')
    amount_margin = fields.Monetary(string='Margin Diakui')
    amount_discount = fields.Monetary(string='Potongan Margin')
    amount_total = fields.Monetary(string='Total', compute='_compute_amount_total', store=True)

    @api.depends('amount_principal', 'amount_margin')
    def _compute_amount_total(self):
        for line in self:
            line.amount_total = line.amount_principal + line.amount_margin
