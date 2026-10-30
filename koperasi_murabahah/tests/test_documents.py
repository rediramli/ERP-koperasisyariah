from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from ..utils import format_day_id, terbilang
from .common import MurabahahCommon


@tagged('post_install', '-at_install', 'koperasi')
class TestDocuments(MurabahahCommon):

    def setUp(self):
        super().setUp()
        self.company.write({'murabahah_signatory_name': 'TEST Ketua', 'murabahah_document_city': 'Pariaman',
                            'murabahah_template_approved': False})
        # cost 9.650.000, down payment 650.000, margin 1.800.000, sale price 11.450.000, debt 10.800.000
        self.akad = self.create_akad()
        self.akad.write({
            'product_brand': 'Yamaha', 'product_model': 'Mio Gear', 'product_color': 'Hitam',
            'product_serial': 'MH3SG1234567890', 'supplier_invoice_ref': 'INV-TEST-01',
            'date_supplier_handover': date(2026, 1, 10), 'tazir_terms': False,
        })
        self.activate(self.akad)

    def html(self, report):
        content, _type = self.env['ir.actions.report']._render_qweb_html(
            'koperasi_murabahah.%s' % report, self.akad.ids)
        return content.decode()

    def test_helpers(self):
        self.assertEqual(terbilang(2501335), 'dua juta lima ratus satu ribu tiga ratus tiga puluh lima rupiah')
        self.assertEqual(terbilang(10800000), 'sepuluh juta delapan ratus ribu rupiah')
        self.assertEqual(terbilang(0), 'nol rupiah')
        self.assertEqual(format_day_id(date(2026, 10, 19)), 'Senin')
        self.assertEqual(format_day_id(date(2026, 10, 25)), 'Ahad')

    def test_akad_document(self):
        html = self.html('report_akad_murabahah')
        for text in ['AKAD PEMBIAYAAN MURABAHAH', self.akad.name, 'TEST Anggota', 'TEST Ketua', 'Pariaman',
                     'Mio Gear', 'MH3SG1234567890', 'INV-TEST-01', 'TEST Pemasok',
                     'Rp 9.650.000', 'Rp 1.800.000', 'Rp 11.450.000', 'Rp 650.000', 'Rp 10.800.000',
                     'sebelas juta empat ratus lima puluh ribu rupiah', 'sepuluh juta delapan ratus ribu rupiah',
                     'Rp 900.000', 'Pasal 5', 'tidak mengenakan denda keterlambatan', 'Lampiran: Jadwal Angsuran',
                     'DRAF']:
            self.assertIn(text, html)
        # 12 installments in the attached schedule, total = debt
        self.assertEqual(html.count('Rp 900.000'), 12 + 1)  # 12 rows + Pasal 3
        # a discount must not be promised in the contract (Fatwa DSN-MUI): only "ditetapkan pada saat pelunasan"
        self.assertIn('tidak diperjanjikan dalam akad ini', html)

    def test_tazir_clause_and_approved_template(self):
        self.akad.with_context(murabahah_allow_write=True).tazir_terms = 'Rp 10.000 per angsuran terlambat.'
        self.company.murabahah_template_approved = True
        html = self.html('report_akad_murabahah')
        self.assertIn('Rp 10.000 per angsuran terlambat.', html)
        self.assertIn('dana kebajikan', html)
        self.assertNotIn('DRAF', html)

    def test_pengakuan_utang_and_bast(self):
        html = self.html('report_pengakuan_utang')
        for text in ['SURAT PENGAKUAN UTANG MURABAHAH', '%s/SPU' % self.akad.name, 'Rp 10.800.000',
                     'sepuluh juta delapan ratus ribu rupiah', '12 kali angsuran']:
            self.assertIn(text, html)
        html = self.html('report_bast')
        self.assertEqual(html.count('BERITA ACARA SERAH TERIMA BARANG'), 2)
        for text in ['dari Pemasok kepada Koperasi', 'dari Koperasi kepada Anggota', 'MH3SG1234567890',
                     '10 Januari 2026', 'Sabtu', 'hak khiyar']:
            self.assertIn(text, html)

    def test_pdf_renders(self):
        for report in ['action_report_akad_murabahah', 'action_report_pengakuan_utang', 'action_report_bast']:
            # Odoo renders HTML instead of PDF in tests unless forced (wkhtmltopdf must really work here)
            pdf, report_type = self.env['ir.actions.report'].with_context(force_report_rendering=True)._render_qweb_pdf(
                'koperasi_murabahah.%s' % report, self.akad.ids)
            self.assertEqual(report_type, 'pdf')
            self.assertTrue(pdf.startswith(b'%PDF'))

    def test_spec_locked_after_signing(self):
        with self.assertRaises(UserError):
            self.akad.with_user(self.user_pengurus).write({'product_serial': 'LAIN'})
        with self.assertRaises(UserError):
            self.akad.with_user(self.user_pengurus).write({'khiyar_days': 30})
        # handover to the member and the checklist are recorded after signing
        self.akad.with_user(self.user_petugas).write({
            'date_member_handover': date(2026, 1, 11), 'handover_place': 'Kantor koperasi',
            'akad_explained': True, 'akad_copy_given': True})
        self.assertIn('11 Januari 2026', self.html('report_bast'))
        # before signing the description can still be completed
        draft = self.create_akad()
        draft.with_user(self.user_petugas).write({'product_serial': 'BARU-123', 'khiyar_days': 7})
        self.assertEqual(draft.khiyar_days, 7)
