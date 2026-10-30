from datetime import date

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from ..models.agunan import RETURN_REMINDER
from .common import MurabahahCommon


@tagged('post_install', '-at_install', 'koperasi')
class TestAgunan(MurabahahCommon):

    def setUp(self):
        super().setUp()
        self.akad = self.activate(self.create_akad())  # receivable 10.800.000
        self.agunan = self.env['koperasi.murabahah.agunan'].with_user(self.user_petugas).create({
            'akad_id': self.akad.id, 'agunan_type': 'bpkb', 'description': 'BPKB Yamaha Mio Gear BA 1234 XY',
            'document_no': 'BPKB-TEST-0001', 'owner_name': 'TEST Anggota', 'appraisal_value': 9000000,
            'storage_location': 'Lemari arsip kantor, map 3',
        })

    def reminders(self, akad):
        return akad.sudo().activity_ids.filtered(lambda act: act.summary == RETURN_REMINDER)

    def html(self, report, records):
        content, _type = self.env['ir.actions.report']._render_qweb_html('koperasi_murabahah.%s' % report, records.ids)
        return content.decode()

    def test_receive_and_coverage(self):
        self.assertEqual(self.agunan.name, '%s/AG1' % self.akad.name)
        self.assertEqual(self.agunan.state, 'draft')
        self.agunan.action_receive()
        self.assertEqual(self.agunan.state, 'dipegang')
        self.assertEqual(self.agunan.received_by_id, self.user_petugas)
        self.assertTrue(self.agunan.date_received)
        self.akad.invalidate_recordset()
        self.assertEqual(self.akad.agunan_value_held, 9000000)
        self.assertAlmostEqual(self.akad.agunan_coverage, 9000000 / 10800000 * 100, places=1)
        second = self.agunan.copy({'description': 'Buku tabungan', 'storage_location': False})
        self.assertEqual(second.name, '%s/AG2' % self.akad.name)
        with self.assertRaises(UserError):  # storage location required
            second.with_user(self.user_petugas).action_receive()

    def test_return_only_after_settled(self):
        self.agunan.action_receive()
        with self.assertRaises(UserError):  # Petugas may not release collateral
            self.agunan.with_user(self.user_petugas).action_return(returned_to='TEST Anggota')
        with self.assertRaises(UserError):  # contract still active
            self.agunan.with_user(self.user_pengurus).action_return(returned_to='TEST Anggota')
        self.assertFalse(self.reminders(self.akad))
        self.akad.with_user(self.user_pengurus)._register_payment(date(2026, 3, 10), self.journal_cash, payoff=True)
        self.assertEqual(self.akad.state, 'lunas')
        self.assertEqual(len(self.reminders(self.akad)), 1)
        self.assertTrue(self.agunan.must_return)
        with self.assertRaises(UserError):  # who receives it back
            self.agunan.with_user(self.user_pengurus).action_return()
        self.agunan.with_user(self.user_pengurus).action_return(returned_to='TEST Anggota', date=date(2026, 3, 12))
        self.assertEqual((self.agunan.state, self.agunan.date_returned), ('dikembalikan', date(2026, 3, 12)))
        self.assertEqual(self.agunan.returned_by_id, self.user_pengurus)
        self.assertFalse(self.agunan.must_return)
        self.assertFalse(self.reminders(self.akad))  # to-do closed once everything is back
        html = self.html('report_tanda_terima_agunan', self.agunan)
        for text in ['TANDA TERIMA AGUNAN', '%s/AG1' % self.akad.name, 'BPKB-TEST-0001', 'Rp 9.000.000',
                     'PENGEMBALIAN AGUNAN', '12 Maret 2026', 'Kelebihan hasil penjualan']:
            self.assertIn(text, html)

    def test_cancel_reminds_return(self):
        akad = self.create_akad()
        akad.with_user(self.user_pengurus).action_approve()
        agunan = self.env['koperasi.murabahah.agunan'].with_user(self.user_petugas).create({
            'akad_id': akad.id, 'agunan_type': 'sertifikat', 'description': 'SHM No. 123',
            'storage_location': 'Brankas'})
        agunan.action_receive()
        akad.with_user(self.user_pengurus).action_cancel()
        self.assertEqual(len(self.reminders(akad)), 1)
        self.assertTrue(agunan.must_return)

    def test_execute(self):
        self.agunan.action_receive()
        with self.assertRaises(UserError):
            self.agunan.with_user(self.user_pengurus).action_execute()  # note required
        self.agunan.with_user(self.user_pengurus).action_execute(
            note='Dijual Rp 8.000.000 atas kesepakatan; hasil dipakai melunasi, kekurangan tetap utang.')
        self.assertEqual(self.agunan.state, 'dieksekusi')

    def test_delete_and_access(self):
        draft = self.env['koperasi.murabahah.agunan'].with_user(self.user_petugas).create({
            'akad_id': self.akad.id, 'description': 'Rencana agunan', 'storage_location': 'x'})
        draft.unlink()
        self.agunan.action_receive()
        with self.assertRaises(UserError):
            self.agunan.with_user(self.user_pengurus).unlink()
        with self.assertRaises(AccessError):
            self.env['koperasi.murabahah.agunan'].with_user(self.user_akuntan).create({
                'akad_id': self.akad.id, 'description': 'x'})
        self.assertEqual(self.agunan.with_user(self.user_akuntan).description, 'BPKB Yamaha Mio Gear BA 1234 XY')

    def test_akad_document_clause(self):
        self.agunan.action_receive()
        html = self.html('report_akad_murabahah', self.akad)
        for text in ['Kepemilikan, Serah Terima, dan Agunan', 'BPKB Yamaha Mio Gear BA 1234 XY', 'BPKB-TEST-0001',
                     'kelebihan hasil penjualan dikembalikan kepada ANGGOTA']:
            self.assertIn(text, html)
        other = self.activate(self.create_akad())
        self.assertNotIn('menyerahkan agunan', self.html('report_akad_murabahah', other))
