from odoo import fields, models
from odoo.exceptions import UserError


class KoperasiMurabahahReschedule(models.Model):
    """History of reschedulings (penjadwalan kembali, Fatwa DSN-MUI 48/2005).

    The remaining receivable and margin are only spread over a new schedule; they never grow,
    so a rescheduling posts no journal entry.
    """
    _name = 'koperasi.murabahah.reschedule'
    _description = 'Restrukturisasi (Penjadwalan Kembali) Murabahah'
    _order = 'akad_id, sequence_no'

    name = fields.Char(string='Nomor', required=True, readonly=True)
    akad_id = fields.Many2one('koperasi.murabahah.akad', string='Akad', required=True, readonly=True,
                              ondelete='restrict', index=True)
    partner_id = fields.Many2one(related='akad_id.partner_id', store=True, string='Anggota / Nasabah')
    company_id = fields.Many2one(related='akad_id.company_id', store=True)
    currency_id = fields.Many2one(related='akad_id.currency_id')
    sequence_no = fields.Integer(string='Restrukturisasi Ke-', required=True, readonly=True)
    date = fields.Date(string='Tanggal', required=True, readonly=True)
    user_id = fields.Many2one('res.users', string='Disetujui Oleh', required=True, readonly=True)
    reason = fields.Text(string='Alasan', required=True, readonly=True)
    remaining_receivable = fields.Monetary(string='Sisa Piutang', readonly=True,
                                           help="Sama sebelum dan sesudah restrukturisasi.")
    remaining_margin = fields.Monetary(string='Sisa Margin', readonly=True)
    arrears_amount = fields.Monetary(string='Tunggakan Sebelumnya', readonly=True)
    arrears_days = fields.Integer(string='Hari Tunggakan Sebelumnya', readonly=True)
    old_count = fields.Integer(string='Angsuran Belum Lunas (Lama)', readonly=True)
    new_count = fields.Integer(string='Jumlah Angsuran Baru', readonly=True)
    new_installment = fields.Monetary(string='Angsuran Baru', readonly=True)
    first_due_date = fields.Date(string='Jatuh Tempo Pertama (Baru)', readonly=True)
    last_due_date = fields.Date(string='Jatuh Tempo Terakhir (Baru)', readonly=True)
    old_schedule = fields.Text(string='Jadwal Lama (Belum Lunas)', readonly=True)
    last_payment_id = fields.Many2one('koperasi.murabahah.payment', string='Pembayaran Terakhir Sebelumnya',
                                      readonly=True, ondelete='restrict')

    def write(self, vals):
        raise UserError(self.env._("Riwayat restrukturisasi tidak boleh diubah."))

    def unlink(self):
        raise UserError(self.env._("Riwayat restrukturisasi tidak boleh dihapus."))
