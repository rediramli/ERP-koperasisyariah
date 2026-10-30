from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    murabahah_journal_id = fields.Many2one(
        'account.journal', string='Jurnal Murabahah',
        help="Jurnal umum untuk jurnal akad dan pengakuan margin.")
    murabahah_cash_journal_id = fields.Many2one(
        'account.journal', string='Jurnal Kas/Bank Default',
        help="Jurnal kas/bank default saat menerima angsuran dan uang muka.")
    murabahah_receivable_account_id = fields.Many2one('account.account', string='Akun Piutang Murabahah')
    murabahah_deferred_margin_account_id = fields.Many2one('account.account', string='Akun Margin Murabahah Ditangguhkan')
    murabahah_inventory_account_id = fields.Many2one('account.account', string='Akun Persediaan Murabahah')
    murabahah_down_payment_account_id = fields.Many2one('account.account', string='Akun Uang Muka Murabahah')
    murabahah_charity_account_id = fields.Many2one('account.account', string="Akun Dana Kebajikan (Ta'zir)")
    murabahah_income_account_id = fields.Many2one('account.account', string='Akun Pendapatan Margin Murabahah')
    murabahah_real_cost_account_id = fields.Many2one(
        'account.account', string='Akun Pendapatan Biaya Riil',
        help="Biaya riil yang dipotong dari uang muka saat anggota membatalkan janji pembelian (ta'widh).")
    # Only used by the summary (Ringkasan Koperasi) until koperasi_simpanan exists
    koperasi_simpanan_pokok_account_id = fields.Many2one(
        'account.account', string='Akun Simpanan Pokok',
        help="Dipakai di Ringkasan Koperasi untuk menampilkan total simpanan pokok anggota.")

    murabahah_margin_method = fields.Selection(
        [('flat', 'Flat: % x (harga perolehan - uang muka)')],
        string='Metode Margin', default='flat', required=True)
    murabahah_payoff_method = fields.Selection(
        [('pupmsjt', 'Rumus PUPMSJT (Fatwa DSN-MUI 153/2022, pedoman OJK 2023)'),
         ('kebijakan', 'Kebijakan Pengurus (tanpa rumus)')],
        string='Potongan Pelunasan Dipercepat', default='pupmsjt', required=True,
        help="Cara menghitung potongan saat anggota melunasi sebelum jatuh tempo. Keputusan DPS.")
    murabahah_installment_rounding = fields.Float(
        string='Pembulatan Angsuran (Rp)', default=1.0,
        help="Angsuran bulanan dibulatkan ke kelipatan ini (terdekat). Selisih pembulatan ditaruh di angsuran terakhir.")

    # Kolektibilitas: batas atas hari tunggakan untuk tiap kategori
    murabahah_days_dpk = fields.Integer(string='DPK s.d. (hari)', default=90)
    murabahah_days_kurang_lancar = fields.Integer(string='Kurang Lancar s.d. (hari)', default=120)
    murabahah_days_diragukan = fields.Integer(string='Diragukan s.d. (hari)', default=180)

    # Printed documents (akad, surat pengakuan utang, berita acara serah terima)
    murabahah_template_approved = fields.Boolean(
        string='Format Dokumen Akad Disetujui DPS',
        help="Selama belum dicentang, dokumen akad dicetak dengan tanda DRAF.")
    murabahah_signatory_name = fields.Char(string='Penandatangan Koperasi')
    murabahah_signatory_title = fields.Char(string='Jabatan Penandatangan', default='Ketua Pengurus')
    murabahah_document_city = fields.Char(string='Kota Penandatanganan')

    # Feasibility and conflict of interest
    murabahah_max_dsr = fields.Float(
        string='Batas DSR (%)', default=40.0,
        help="Batas total angsuran per bulan dibanding penghasilan. Di atas batas, persetujuan wajib disertai dasar.")
    murabahah_pengurus_limit = fields.Float(
        string='Plafon Pembiayaan per Pengurus (Rp)', default=0.0,
        help="Batas sisa pembiayaan seorang pengurus. 0 = tanpa batas (sampai diputuskan RAT).")

    # Application & KYC (SOP-PEMBIAYAAN.md)
    murabahah_require_application = fields.Boolean(
        string='Akad Baru Wajib Lewat Pengajuan', default=True,
        help="Akad hanya bisa disetujui bila dibuat dari Pengajuan yang sudah lolos KYC dan survei.")
    murabahah_min_age = fields.Integer(string='Usia Minimal Pemohon', default=21,
                                       help="Kecuali sudah menikah. 0 = tanpa batas. Pra-skrining.")
    murabahah_max_age = fields.Integer(string='Usia Maksimal saat Angsuran Terakhir', default=60,
                                       help="0 = tanpa batas. Pra-skrining.")
    murabahah_non_member_policy = fields.Selection(
        [('boleh', 'Boleh, tanpa syarat tambahan'),
         ('penjamin', 'Boleh, dengan penjamin anggota aktif (kafalah)'),
         ('dasar', 'Boleh, dengan Dasar Persetujuan'),
         ('tolak', 'Tidak boleh (hanya anggota)')],
        string='Pembiayaan Bukan Anggota', default='boleh', required=True,
        help="Keputusan pengurus (SOP K1). Cek aturan Kemenkop yang berlaku.")

