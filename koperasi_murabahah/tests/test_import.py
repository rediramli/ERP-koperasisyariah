import base64
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import MurabahahCommon

CSV = """no_akad,anggota,barang,tanggal_akad,harga_perolehan,uang_muka,margin_pct,margin,harga_jual,tenor,angsuran_per_bulan,angsuran_dibayar,sisa_piutang,sisa_pokok,sisa_margin_ditangguhkan
KT008,TEST Nasabah,Honda Beat,29/07/2023,13000000,3000000,25%,2500000,15500000,15,833333,12,2501335,2001068,500267
KT028,TEST Anggota,Xiaomi Poco M6 Pro,29/09/2024,2536660,336660,20%,440000,2976660,6,440000,2,1760000,1466667,293333
KT035,TEST Anggota,Motor Yamaha Mio Gear,07/03/2025,9650000,650000,20%,1800000,11450000,12,900000,0,10800000,9000000,1800000
"""


@tagged('post_install', '-at_install', 'koperasi')
class TestImport(MurabahahCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Opening entry like MISC/2026/05/0001: the receivable is already posted
        equity = cls.env['account.account'].create({
            'code': 'KT313001', 'name': 'TEST Saldo Laba', 'account_type': 'equity',
            'company_ids': [(6, 0, cls.company.ids)]})
        rows = [
            (cls.acc_receivable, cls.non_member, 'KT008 Honda Beat - sisa piutang', 2501335, 0),
            (cls.acc_receivable, cls.member, 'KT028 Xiaomi Poco M6 Pro - sisa piutang', 1760000, 0),
            (cls.acc_receivable, cls.member, 'KT035 Motor Yamaha Mio Gear - sisa piutang', 10800000, 0),
            (cls.acc_deferred, cls.non_member, 'KT008 Honda Beat - margin ditangguhkan', 0, 500267),
            (cls.acc_deferred, cls.member, 'KT028 Xiaomi Poco M6 Pro - margin ditangguhkan', 0, 293333),
            (cls.acc_deferred, cls.member, 'KT035 Motor Yamaha Mio Gear - margin ditangguhkan', 0, 1800000),
        ]
        lines = [(0, 0, {'account_id': a.id, 'partner_id': p.id, 'name': n, 'debit': d, 'credit': c})
                 for a, p, n, d, c in rows]
        balance = sum(r[3] - r[4] for r in rows)
        lines.append((0, 0, {'account_id': equity.id, 'name': 'Saldo laba', 'debit': 0, 'credit': balance}))
        cls.opening = cls.env['account.move'].create({
            'move_type': 'entry', 'journal_id': cls.journal_general.id, 'date': date(2026, 5, 24),
            'ref': 'TEST SALDO AWAL', 'line_ids': lines})
        cls.opening.action_post()

    def run_import(self, content=CSV):
        wizard = self.env['koperasi.murabahah.import.wizard'].with_user(self.user_pengurus).create({
            'file': base64.b64encode(content.encode()).decode(),
            'filename': 'akad_aktif.csv',
            'opening_move_id': self.opening.id,
        })
        wizard.action_import()
        return wizard

    def test_import_does_not_post_twice(self):
        moves_before = self.env['account.move'].search_count([])
        wizard = self.run_import()
        self.assertEqual(self.env['account.move'].search_count([]), moves_before, "import must not post entries")
        self.assertIn('KT008: OK', wizard.result)
        akads = self.env['koperasi.murabahah.akad'].search([('name', 'in', ('KT008', 'KT028', 'KT035'))])
        self.assertEqual(len(akads), 3)
        expected = {'KT008': (2501335, 500267), 'KT028': (1760000, 293333), 'KT035': (10800000, 1800000)}
        for akad in akads:
            self.assertEqual(akad.state, 'aktif')
            self.assertTrue(akad.is_migrated)
            self.assertEqual((akad.remaining_receivable, akad.remaining_margin), expected[akad.name])
            self.assert_invariants(akad)
        kt028 = akads.filtered(lambda a: a.name == 'KT028')
        lines = kt028.line_ids.sorted('sequence')
        self.assertEqual(lines[:2].mapped('state'), ['lunas', 'lunas'])
        self.assertEqual(lines[2:].mapped('amount_total'), [440000] * 4)
        kt008 = akads.filtered(lambda a: a.name == 'KT008')
        self.assertEqual(len(kt008.line_ids.filtered(lambda l: l.state != 'lunas')), 3)

        # Second run skips existing contracts
        wizard = self.run_import()
        self.assertIn('dilewati', wizard.result)

    def test_imported_contract_paid_off(self):
        self.run_import()
        akad = self.env['koperasi.murabahah.akad'].search([('name', '=', 'KT028')])
        for line in akad._open_lines():
            self.pay(akad, line.residual, pay_date=date(2026, 6, 10))
            self.assert_invariants(akad)
        self.assertEqual(akad.state, 'lunas')
        # Only the margin received after migration is income of the period
        self.assertEqual(-self.ledger(akad, self.acc_income), 293333)
        self.assert_invariants(akad)

    def test_import_rejects_mismatch(self):
        bad = CSV.replace('2501335,2001068,500267', '2500004,2000003,500001')
        with self.assertRaises(UserError):
            self.run_import(bad)
