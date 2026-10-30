from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    koperasi_nik = fields.Char(string='NIK / No. KTP', tracking=True, copy=False, index=True,
                               groups='koperasi_base.group_koperasi_petugas,koperasi_base.group_koperasi_akuntan')
    koperasi_pekerjaan = fields.Char(string='Pekerjaan / Instansi', tracking=True,
                                     groups='koperasi_base.group_koperasi_petugas,koperasi_base.group_koperasi_akuntan')
    koperasi_ktp_image = fields.Binary(
        string='Foto KTP', attachment=True,
        groups='koperasi_base.group_koperasi_petugas,koperasi_base.group_koperasi_akuntan')
    koperasi_is_applicant = fields.Boolean(
        string='Pendaftar Online', default=False, tracking=True, index=True,
        help="Ditandai otomatis jika kontak ini mendaftar dari website publik.",
    )
    koperasi_application_date = fields.Datetime(
        string='Waktu Pendaftaran Online', tracking=True, readonly=True,
    )
    # Pastikan field mobile selalu tersedia walaupun modul sms belum terpasang
    mobile = fields.Char(string='No. Handphone / WhatsApp', copy=False)

    def action_approve_as_member(self):
        """Ubah pendaftar online menjadi Anggota resmi."""
        for partner in self:
            vals = {
                'koperasi_status': 'anggota',
                'koperasi_join_date': fields.Date.context_today(partner),
            }
            if not partner.koperasi_member_no:
                # Format nomor anggota sederhana jika belum diisi: AGG-YYYY-ID
                year = fields.Date.context_today(partner).year
                vals['koperasi_member_no'] = f"AGG-{year}-{partner.id:04d}"
            partner.write(vals)
        return True
