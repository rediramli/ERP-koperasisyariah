import base64
from datetime import date

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged

from .common import MurabahahCommon

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 32


class PengajuanCommon(MurabahahCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.write({'murabahah_require_application': True, 'murabahah_max_dsr': 40.0,
                           'murabahah_min_age': 21, 'murabahah_max_age': 60})
        cls.motor = cls.env.ref('koperasi_murabahah.kategori_motor')
        cls.applicant = cls.env['res.partner'].create({
            'name': 'TEST Pemohon Motor', 'phone': '081200000001', 'street': 'Jl. Contoh 1',
            'koperasi_nik': '1371010105950001', 'koperasi_birth_date': date(1995, 5, 1),
            'koperasi_marital': 'belum', 'koperasi_mother_name': 'Ibu Contoh', 'koperasi_pekerjaan': 'Karyawan',
            'koperasi_emergency_name': 'Kerabat', 'koperasi_emergency_phone': '081200000002',
            'koperasi_dttot_date': date(2026, 10, 29), 'koperasi_dttot_result': 'tidak',
            'koperasi_risk_level': 'rendah',
        })

    def new_pengajuan(self, **vals):
        values = {'partner_id': self.applicant.id, 'kategori_id': self.motor.id, 'product_desc': 'Motor matic',
                  'estimated_price': 25000000, 'down_payment': 5000000, 'tenor': 24, 'monthly_income': 6000000}
        values.update(vals)
        return self.env['koperasi.murabahah.pengajuan'].with_user(self.user_petugas).create(values)

    def complete_documents(self, pengajuan):
        for line in pengajuan.dokumen_ids.filtered(lambda d: d.phase == 'pengajuan' and d.required):
            line.write({'attachment': base64.b64encode(PNG).decode(), 'attachment_name': 'doc.png',
                        'original_seen': True, 'verified': True})

    def run_to_survey(self, pengajuan):
        pengajuan.action_start_kyc()
        self.complete_documents(pengajuan)
        pengajuan.write({'phone_verified': True, 'emergency_verified': True, 'address_verified': True,
                         'employment_verified': True})
        pengajuan.action_complete_kyc()
        pengajuan.write({'survey_method': 'kunjungan', 'survey_date': date(2026, 10, 30), 'survey_result': 'sesuai'})



@tagged('post_install', '-at_install')
class TestPengajuan(PengajuanCommon):

    def test_checklist_per_category_and_marital_status(self):
        p = self.new_pengajuan()
        self.assertTrue(p.name.startswith('PGJ/'))
        self.assertEqual(p.margin_pct, self.motor.margin_pct, "margin follows the category")
        codes = set(p.dokumen_ids.mapped('jenis_id.code'))
        self.assertIn('bpkb', codes, "vehicle documents for a motorcycle")
        self.assertNotIn('ktp_pasangan', codes, "no spouse documents when unmarried")
        hp = self.new_pengajuan(kategori_id=self.env.ref('koperasi_murabahah.kategori_elektronik').id,
                                estimated_price=5000000, down_payment=1000000, tenor=10)
        self.assertNotIn('bpkb', hp.dokumen_ids.mapped('jenis_id.code'))
        self.applicant.koperasi_marital = 'menikah'
        p.write({'partner_id': self.applicant.id})
        self.assertIn('ktp_pasangan', p.dokumen_ids.mapped('jenis_id.code'))
        self.assertIn('Nama Pasangan', p.kyc_missing or '')

    def test_prescreen_requires_exception_note(self):
        p = self.new_pengajuan(down_payment=1000000, tenor=36)
        issues = p._prescreen_list()
        self.assertTrue(any('Uang muka' in i for i in issues))
        self.assertTrue(any('Tenor 36' in i for i in issues))
        with self.assertRaises(UserError):
            p.action_start_kyc()
        p.prescreen_note = 'Disetujui rapat pengurus sebagai pengecualian'
        p.action_start_kyc()
        self.assertEqual(p.state, 'kyc')

    def test_prescreen_age_and_arrears(self):
        old = self.applicant.copy({'name': 'TEST Tua', 'koperasi_nik': '1371010101660009',
                                   'koperasi_birth_date': date(1966, 1, 1)})
        p = self.new_pengajuan(partner_id=old.id)
        self.assertTrue(any('angsuran terakhir' in i for i in p._prescreen_list()))
        self.company.murabahah_non_member_policy = 'dasar'
        self.assertTrue(any('bukan anggota' in i for i in p._prescreen_list()))

    def test_kyc_gate(self):
        p = self.new_pengajuan()
        p.action_start_kyc()
        with self.assertRaises(UserError):
            p.action_complete_kyc()          # documents and verification calls missing
        self.complete_documents(p)
        p.write({'phone_verified': True, 'emergency_verified': True, 'address_verified': True,
                 'employment_verified': True})
        self.applicant.koperasi_dttot_result = 'ditemukan'
        with self.assertRaises(UserError):
            p.action_complete_kyc()
        self.applicant.koperasi_dttot_result = 'tidak'
        p.action_complete_kyc()
        self.assertEqual(p.state, 'survei')
        self.assertEqual(self.applicant.koperasi_kyc_user_id, self.user_petugas)
        self.assertTrue(self.applicant.koperasi_kyc_review_date)

    def test_document_rules(self):
        p = self.new_pengajuan()
        slik = p.dokumen_ids.filtered(lambda d: d.jenis_id.code == 'slik')
        with self.assertRaises(ValidationError):
            slik.write({'verified': True})   # no file
        with self.assertRaises(ValidationError):
            slik.write({'not_applicable': True})   # no reason
        slik.write({'not_applicable': True, 'note': 'Belum ditetapkan pengurus (K6)'})
        self.assertTrue(slik.is_complete)
        ktp = p.dokumen_ids.filtered(lambda d: d.jenis_id.code == 'ktp')
        ktp.write({'attachment': base64.b64encode(PNG).decode(), 'attachment_name': 'ktp.png', 'verified': True})
        self.assertFalse(ktp.is_complete, "original document must be seen")
        ktp.original_seen = True
        self.assertTrue(ktp.is_complete)
        self.assertEqual(ktp.verified_by_id, self.user_petugas)
        self.assertNotIn('KTP pemohon', p.doc_request_text)
        self.assertIn('Kartu Keluarga', p.doc_request_text)

    def test_survey_skip_only_low_risk(self):
        p = self.new_pengajuan()
        self.run_to_survey(p)
        p.write({'survey_method': 'dilewati', 'survey_note': 'Pelanggan lama'})
        self.applicant.koperasi_risk_level = 'menengah'
        with self.assertRaises(UserError):
            p.action_complete_survey()
        self.applicant.koperasi_risk_level = 'rendah'
        p.action_complete_survey()
        self.assertEqual(p.state, 'analisis')

    def test_full_flow_to_akad_and_approval(self):
        direct = self.create_akad(partner=self.applicant)
        with self.assertRaises(UserError):
            direct.with_user(self.user_pengurus).action_approve()   # not from an application

        p = self.new_pengajuan(other_obligations=500000)
        self.run_to_survey(p)
        p.action_complete_survey()
        akad = p.akad_id
        self.assertEqual(p.state, 'analisis')
        self.assertEqual(akad.pengajuan_id, p)
        self.assertEqual((akad.partner_id, akad.cost_price, akad.down_payment, akad.tenor, akad.margin_pct),
                         (self.applicant, 25000000, 5000000, 24, 25.0))
        self.assertEqual(akad.monthly_income, 6000000)
        self.assertEqual(akad.analyst_id, self.user_petugas)
        akad.with_user(self.user_petugas).officer_recommendation = 'layak'
        akad.with_user(self.user_pengurus).action_approve()
        self.assertEqual(p.state, 'disetujui')
        # Back to draft keeps the application in analysis
        akad.with_user(self.user_pengurus).action_reset_draft()
        self.assertEqual(p.state, 'analisis')
        akad.with_user(self.user_pengurus).action_cancel()
        self.assertEqual(p.state, 'batal')

    def test_high_risk_needs_approval_basis(self):
        p = self.new_pengajuan()
        self.run_to_survey(p)
        p.action_complete_survey()
        p.akad_id.officer_recommendation = 'layak'
        self.applicant.koperasi_risk_level = 'tinggi'
        with self.assertRaises(UserError):
            p.akad_id.with_user(self.user_pengurus).action_approve()
        p.akad_id.approval_note = 'Rapat 2 pengurus 30/10/2026'
        p.akad_id.with_user(self.user_pengurus).action_approve()
        self.assertEqual(p.akad_id.state, 'disetujui')

    def test_non_member_policy_reject(self):
        self.company.murabahah_non_member_policy = 'tolak'
        p = self.new_pengajuan(prescreen_note='Uji')
        self.run_to_survey(p)
        p.action_complete_survey()
        p.akad_id.officer_recommendation = 'layak'
        with self.assertRaises(UserError):
            p.akad_id.with_user(self.user_pengurus).action_approve()

    def test_reject_needs_reason(self):
        p = self.new_pengajuan()
        with self.assertRaises(UserError):
            p.action_reject()
        p.reject_reason = 'Penghasilan tidak mencukupi'
        p.action_reject()
        self.assertEqual(p.state, 'ditolak')

    def test_website_submit_creates_no_contact(self):
        Partner = self.env['res.partner']
        before = Partner.search_count([])
        rec = self.env['koperasi.murabahah.pengajuan']._website_submit({
            'name': 'TEST Web', 'phone': '0812', 'nik': '1371010105950001', 'kategori_id': self.motor.id,
            'product_desc': 'Motor', 'estimated_price': 20000000, 'down_payment': 4000000, 'tenor': 12,
        }, {'ktp': ('ktp.png', PNG)})
        self.assertEqual(Partner.search_count([]), before, "no contact from a public form")
        self.assertEqual(rec.channel, 'website')
        self.assertTrue(rec.dokumen_ids.filtered(lambda d: d.jenis_id.code == 'ktp').attachment_name)
        with self.assertRaises(ValidationError):
            self.env['koperasi.murabahah.pengajuan']._website_submit({
                'name': 'X', 'kategori_id': self.motor.id, 'product_desc': 'Motor', 'estimated_price': 1,
            }, {'ktp': ('x.exe', b'MZ\x90\x00')})
        # Token-bound read
        self.assertEqual(self.env['koperasi.murabahah.pengajuan']._website_get(rec.id, rec.sudo().access_token), rec)
        self.assertFalse(self.env['koperasi.murabahah.pengajuan']._website_get(rec.id, 'salah'))
        # Petugas links the contact by NIK
        rec.with_user(self.user_petugas).action_find_or_create_partner()
        self.assertEqual(rec.partner_id, self.applicant)

    def test_nik_validation_and_privacy(self):
        with self.assertRaises(ValidationError):
            self.env['res.partner'].create({'name': 'X', 'koperasi_nik': '123'})
        with self.assertRaises(ValidationError):
            self.env['res.partner'].create({'name': 'Y', 'koperasi_nik': '1371010105950001'})   # duplicate
        plain = new_test_user(self.env, login='kt_plain', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.applicant.with_user(plain).read(['koperasi_nik'])
        with self.assertRaises(AccessError):
            self.env['koperasi.murabahah.pengajuan'].with_user(plain).search([])
        self.assertEqual(self.applicant.with_user(self.user_petugas).koperasi_nik, '1371010105950001')


@tagged('post_install', '-at_install')
class TestPenjamin(PengajuanCommon):
    """SOP K1 (owner 30 Oct 2026): non-members are financed only with a guarantor who is an active member."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.murabahah_non_member_policy = 'penjamin'

    def test_non_member_needs_member_guarantor(self):
        p = self.new_pengajuan()
        self.assertTrue(p.penjamin_required)
        self.assertTrue(any('penjamin' in i for i in p._prescreen_list()))
        self.assertNotIn('ktp_penjamin', p.dokumen_ids.mapped('jenis_id.code'))
        # A non-member cannot guarantee
        p.penjamin_id = self.non_member
        self.assertTrue(any('bukan anggota aktif' in i for i in p._penjamin_problems()))
        p.write({'penjamin_id': self.member.id, 'penjamin_relation': 'Teman kerja'})
        self.assertFalse(p._penjamin_problems())
        codes = p.dokumen_ids.mapped('jenis_id.code')
        self.assertIn('ktp_penjamin', codes)
        self.assertIn('surat_penjaminan', codes)
        self.run_to_survey(p)
        p.action_complete_survey()
        akad = p.akad_id
        self.assertEqual((akad.penjamin_id, akad.penjamin_relation), (self.member, 'Teman kerja'))
        akad.officer_recommendation = 'layak'
        akad.with_user(self.user_pengurus).action_approve()
        self.assertEqual(akad.state, 'disetujui')
        with self.assertRaises(UserError):
            akad.with_user(self.user_pengurus).write({'penjamin_id': False})   # locked after approval
        pdf, fmt = self.env['ir.actions.report'].with_context(force_report_rendering=True)._render_qweb_pdf(
            'koperasi_murabahah.action_report_penjaminan', akad.ids)
        self.assertEqual(fmt, 'pdf')
        html = self.env['ir.actions.report']._render_qweb_html(
            'koperasi_murabahah.action_report_penjaminan', akad.ids)[0].decode()
        self.assertIn('SURAT PENJAMINAN', html)
        self.assertIn(self.member.name, html)

    def test_approval_without_guarantor_blocked(self):
        p = self.new_pengajuan(prescreen_note='Penjamin menyusul')
        p.action_start_kyc()
        self.complete_documents(p)
        p.write({'phone_verified': True, 'emergency_verified': True, 'address_verified': True,
                 'employment_verified': True})
        with self.assertRaises(UserError):
            p.action_complete_kyc()          # guarantor missing is a KYC gap
        # Direct akad (application rule off) still refuses a non-member without guarantor
        self.company.murabahah_require_application = False
        akad = self.create_akad(partner=self.non_member)
        with self.assertRaises(UserError):
            akad.with_user(self.user_pengurus).action_approve()

    def test_guarantor_cannot_approve(self):
        self.company.murabahah_require_application = False
        self.member.koperasi_user_id = self.user_pengurus
        akad = self.create_akad(partner=self.non_member)
        akad.penjamin_id = self.member
        with self.assertRaises(UserError):
            akad.with_user(self.user_pengurus).action_approve()
        other = new_test_user(self.env, login='kt_pengurus2', groups='koperasi_base.group_koperasi_pengurus')
        akad.with_user(other).action_approve()
        self.assertEqual(akad.state, 'disetujui')


@tagged('post_install', '-at_install')
class TestNik(PengajuanCommon):
    """NIK layout: region (6), DDMMYY with +40 on the day for women, serial (4)."""

    def test_parse_nik(self):
        from odoo.addons.koperasi_base.models.wilayah import parse_nik
        today = date(2026, 10, 30)
        info = parse_nik('1371015203900002', today)
        self.assertEqual((info['birth_date'], info['gender'], info['region_code']), (date(1990, 3, 12), 'p', '137101'))
        self.assertEqual(parse_nik('1371011203050002', today)['birth_date'], date(2005, 3, 12))
        self.assertTrue(parse_nik('1371013213900002', today)['error'])   # month 13
        self.assertTrue(parse_nik('12345', today)['error'])

    def test_autofill_and_mismatch(self):
        partner = self.env['res.partner'].with_user(self.user_petugas).create(
            {'name': 'TEST NIK', 'koperasi_nik': '1371015203900002'})
        self.assertEqual((partner.koperasi_birth_date, partner.koperasi_gender), (date(1990, 3, 12), 'p'))
        self.assertIn('Padang', partner.koperasi_nik_info)
        self.assertIn('Perempuan', partner.koperasi_nik_info)
        self.assertFalse(partner.koperasi_nik_warning)
        partner.koperasi_birth_date = date(1990, 3, 13)
        self.assertIn('berbeda', partner.koperasi_nik_warning)
        self.assertTrue(any('berbeda' in m for m in partner._koperasi_kyc_missing()))
        # Entered data is never overwritten by the NIK
        other = self.env['res.partner'].create({'name': 'TEST NIK 2', 'koperasi_nik': '1371011203900003',
                                                'koperasi_gender': 'p'})
        self.assertEqual(other.koperasi_gender, 'p')
        self.assertTrue(other.koperasi_nik_warning)
        unknown = self.env['res.partner'].create({'name': 'TEST NIK 3', 'koperasi_nik': '9971011203900003'})
        self.assertIn('provinsi', unknown.koperasi_nik_warning)

    def test_applicant_nik_on_application(self):
        p = self.env['koperasi.murabahah.pengajuan']._website_submit({
            'name': 'TEST Web', 'phone': '0812', 'nik': self.applicant.koperasi_nik, 'kategori_id': self.motor.id,
            'product_desc': 'Motor', 'estimated_price': 20000000, 'down_payment': 4000000, 'tenor': 12})
        self.assertEqual(p.applicant_existing_id, self.applicant)
        self.assertIn('Lahir 1 Mei 1995', p.applicant_nik_info)
