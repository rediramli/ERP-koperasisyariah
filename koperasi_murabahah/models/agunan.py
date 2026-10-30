from odoo import api, fields, models
from odoo.exceptions import UserError

from .akad import GROUP_PENGURUS

RETURN_REMINDER = 'Kembalikan agunan'

AGUNAN_TYPES = [
    ('bpkb', 'BPKB Kendaraan'),
    ('sertifikat', 'Sertifikat Tanah / Bangunan'),
    ('barang', 'Barang yang Dibiayai'),
    ('elektronik', 'Barang Elektronik'),
    ('surat_berharga', 'Surat Berharga / Buku Tabungan'),
    ('lainnya', 'Lainnya'),
]


class KoperasiMurabahahAgunan(models.Model):
    """Collateral for a murabahah receivable (OJK murabahah guideline Bab III C and H.3).

    Only a register: holding or returning a collateral posts no journal entry. Selling a collateral
    to settle a defaulted contract is recorded here as 'dieksekusi'; the cash goes through a normal payment.
    """
    _name = 'koperasi.murabahah.agunan'
    _description = 'Agunan Murabahah'
    _inherit = ['mail.thread']
    _order = 'akad_id, id'

    name = fields.Char(string='Nomor', required=True, readonly=True, copy=False, default='/')
    akad_id = fields.Many2one('koperasi.murabahah.akad', string='Akad', required=True, index=True,
                              ondelete='restrict', tracking=True)
    partner_id = fields.Many2one(related='akad_id.partner_id', store=True, string='Anggota / Nasabah')
    akad_state = fields.Selection(related='akad_id.state', store=True, string='Status Akad')
    company_id = fields.Many2one(related='akad_id.company_id', store=True)
    currency_id = fields.Many2one(related='akad_id.currency_id')

    agunan_type = fields.Selection(AGUNAN_TYPES, string='Jenis Agunan', required=True, default='bpkb', tracking=True)
    description = fields.Char(string='Uraian', required=True, tracking=True,
                              help="Mis. BPKB Yamaha Mio Gear BA 1234 XY, tahun 2025.")
    document_no = fields.Char(string='No. Dokumen', tracking=True, help="No. BPKB, sertifikat, atau dokumen lain.")
    owner_name = fields.Char(string='Atas Nama', tracking=True)
    held_form = fields.Selection(
        [('dokumen', 'Dokumen kepemilikan (fisik barang tetap dipakai anggota)'),
         ('fisik', 'Fisik barang disimpan koperasi')],
        string='Yang Dipegang Koperasi', required=True, default='dokumen', tracking=True)
    appraisal_value = fields.Monetary(string='Nilai Taksiran', tracking=True)
    appraisal_date = fields.Date(string='Tanggal Taksiran')
    appraiser = fields.Char(string='Penaksir')
    storage_location = fields.Char(string='Lokasi Penyimpanan', tracking=True,
                                   help="Mis. lemari arsip kantor koperasi, map no. ...")

    state = fields.Selection(
        [('draft', 'Rencana'), ('dipegang', 'Dipegang Koperasi'),
         ('dikembalikan', 'Dikembalikan'), ('dieksekusi', 'Dieksekusi')],
        string='Status', required=True, default='draft', tracking=True, index=True, copy=False)
    date_received = fields.Date(string='Tanggal Diterima', tracking=True, copy=False)
    received_by_id = fields.Many2one('res.users', string='Diterima Oleh', readonly=True, copy=False)
    date_returned = fields.Date(string='Tanggal Dikembalikan', tracking=True, copy=False)
    returned_by_id = fields.Many2one('res.users', string='Dikembalikan Oleh', readonly=True, copy=False)
    returned_to = fields.Char(string='Diterima Kembali Oleh', help="Nama penerima agunan (anggota atau kuasanya).", copy=False)
    date_executed = fields.Date(string='Tanggal Eksekusi', tracking=True, copy=False)
    execution_note = fields.Text(string='Catatan Eksekusi', copy=False)
    note = fields.Text(string='Catatan')
    must_return = fields.Boolean(string='Harus Dikembalikan', compute='_compute_must_return', store=True,
                                 help="Agunan masih dipegang padahal akad sudah lunas atau batal.")

    @api.depends('state', 'akad_id.state')
    def _compute_must_return(self):
        for agunan in self:
            agunan.must_return = agunan.state == 'dipegang' and agunan.akad_id.state in ('lunas', 'batal')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for agunan in records.filtered(lambda a: a.name == '/'):
            number = self.search_count([('akad_id', '=', agunan.akad_id.id), ('id', '<=', agunan.id)])
            agunan.name = "%s/AG%s" % (agunan.akad_id.name, number)
        return records

    def get_labels(self):
        """Selection labels for the printed receipt."""
        self.ensure_one()
        return {
            'type': dict(self._fields['agunan_type'].selection).get(self.agunan_type),
            'held': dict(self._fields['held_form'].selection).get(self.held_form),
        }

    def unlink(self):
        if any(agunan.state != 'draft' for agunan in self):
            raise UserError(self.env._("Agunan yang sudah diterima tidak boleh dihapus."))
        return super().unlink()

    def _check_pengurus(self):
        if not self.env.su and not self.env.user.has_group(GROUP_PENGURUS):
            raise UserError(self.env._("Tindakan ini hanya untuk grup Koperasi / Pengurus."))

    def action_receive(self):
        for agunan in self:
            if agunan.state != 'draft':
                raise UserError(self.env._("Agunan %s sudah diterima.", agunan.name))
            if agunan.akad_id.state in ('lunas', 'batal'):
                raise UserError(self.env._("Akad %s sudah lunas atau batal.", agunan.akad_id.name))
            if not agunan.storage_location:
                raise UserError(self.env._("Isi lokasi penyimpanan agunan %s.", agunan.name))
            agunan.write({
                'state': 'dipegang',
                'date_received': agunan.date_received or fields.Date.context_today(self),
                'received_by_id': self.env.user.id,
            })

    def action_return(self, returned_to=False, date=False):
        self._check_pengurus()
        for agunan in self:
            if agunan.state != 'dipegang':
                raise UserError(self.env._("Agunan %s tidak sedang dipegang koperasi.", agunan.name))
            if agunan.akad_id.state not in ('lunas', 'batal'):
                raise UserError(self.env._(
                    "Agunan %(ag)s dikembalikan setelah akad %(akad)s lunas atau batal.",
                    ag=agunan.name, akad=agunan.akad_id.name))
            name = returned_to or agunan.returned_to
            if not name:
                raise UserError(self.env._("Isi nama penerima kembali agunan %s.", agunan.name))
            agunan.write({
                'state': 'dikembalikan',
                'returned_to': name,
                'date_returned': date or agunan.date_returned or fields.Date.context_today(self),
                'returned_by_id': self.env.user.id,
            })
            agunan.akad_id.message_post(body=self.env._(
                "Agunan %(ag)s (%(desc)s) dikembalikan kepada %(to)s.", ag=agunan.name, desc=agunan.description,
                to=name))
            if not agunan.akad_id.agunan_ids.filtered(lambda a: a.state == 'dipegang'):
                agunan.akad_id.sudo().activity_ids.filtered(
                    lambda act: act.summary == RETURN_REMINDER).action_feedback(
                    feedback=self.env._("Semua agunan sudah dikembalikan."))

    def action_execute(self, note=False, date=False):
        """Collateral sold or taken over after default (Bab III C.5, H.3). No journal entry here."""
        self._check_pengurus()
        for agunan in self:
            if agunan.state != 'dipegang':
                raise UserError(self.env._("Agunan %s tidak sedang dipegang koperasi.", agunan.name))
            text = note or agunan.execution_note
            if not (text or '').strip():
                raise UserError(self.env._(
                    "Isi catatan eksekusi agunan %s (dasar, harga jual, penyelesaian sisa/kelebihan).", agunan.name))
            agunan.write({'state': 'dieksekusi', 'execution_note': text,
                          'date_executed': date or fields.Date.context_today(self)})
