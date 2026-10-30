from datetime import date

from odoo.exceptions import AccessError
from odoo.tests import tagged

from ..wizard.ringkasan import format_date_id, format_rp
from .common import MurabahahCommon

FIELDS = ['cash_balance', 'receivable_balance', 'deferred_margin_balance', 'receivable_net', 'margin_income',
          'simpanan_pokok', 'total_assets', 'total_liabilities', 'net_assets', 'active_count',
          'arrears_count', 'arrears_amount']


@tagged('post_install', '-at_install', 'koperasi')
class TestRingkasan(MurabahahCommon):
    """The database may already hold real entries, so the tests compare figures before and after."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acc_simpanan = cls.env['account.account'].create({
            'code': 'KT312001', 'name': 'TEST Simpanan Pokok', 'account_type': 'equity',
            'company_ids': [(6, 0, cls.company.ids)]})
        cls.company.koperasi_simpanan_pokok_account_id = cls.acc_simpanan

    def summary(self, date_to, date_from=date(2026, 1, 1), user=None):
        rec = self.env['koperasi.ringkasan'].with_user(user or self.user_akuntan).create(
            {'date_to': date_to, 'date_from': date_from})
        return {name: rec[name] for name in FIELDS} | {'message': rec.message}

    def delta(self, before, after):
        return {name: after[name] - before[name] for name in FIELDS}

    def post_simpanan(self, amount, when):
        move = self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.journal_general.id, 'date': when, 'ref': 'TEST simpanan',
            'line_ids': [(0, 0, {'account_id': self.acc_cash.id, 'debit': amount, 'name': 'simpanan'}),
                         (0, 0, {'account_id': self.acc_simpanan.id, 'credit': amount, 'name': 'simpanan'})],
        })
        move.action_post()

    def test_format(self):
        self.assertEqual(format_rp(31403512), 'Rp 31.403.512')
        self.assertEqual(format_rp(-2084267.4), '-Rp 2.084.267')
        self.assertEqual(format_rp(0), 'Rp 0')
        self.assertEqual(format_date_id(date(2026, 10, 19)), '19 Oktober 2026')

    def test_summary_figures(self):
        end, before_akad, march = date(2026, 12, 31), date(2026, 1, 9), date(2026, 3, 1)
        s0_end, s0_early = self.summary(end), self.summary(before_akad)
        s0_from_march = self.summary(end, date_from=march)

        self.post_simpanan(3000000, date(2026, 1, 5))
        # cost 9.650.000, down payment 650.000, margin 20% = 1.800.000, receivable 10.800.000 / 12
        akad = self.activate(self.create_akad())
        self.pay(akad, 900000)  # 750.000 principal + 150.000 margin
        self.assert_invariants(akad)

        d = self.delta(s0_end, self.summary(end))
        self.assertEqual(d['cash_balance'], 3000000 - 9650000 + 650000 + 900000)
        self.assertEqual(d['receivable_balance'], 10800000 - 900000)
        self.assertEqual(d['deferred_margin_balance'], 1800000 - 150000)
        self.assertEqual(d['receivable_net'], 9900000 - 1650000)
        self.assertEqual(d['margin_income'], 150000)
        self.assertEqual(d['simpanan_pokok'], 3000000)
        self.assertEqual(d['total_liabilities'], 0)  # down payment liability cleared at activation
        # Assets grew by exactly what equity gained: simpanan + recognized margin
        self.assertEqual(d['net_assets'], 3000000 + 150000)
        self.assertEqual(d['total_assets'], d['net_assets'])
        self.assertEqual(d['active_count'], 1)
        # Arrears are as of today (the schedule starts 10/02/2026, only one installment paid)
        akad.invalidate_recordset()
        self.assertEqual(d['arrears_count'], 1 if akad.arrears_amount > 0.5 else 0)
        self.assertEqual(d['arrears_amount'], akad.arrears_amount)

        # Cut-off: before the contract only the simpanan entry counts
        d_early = self.delta(s0_early, self.summary(before_akad))
        self.assertEqual(d_early['cash_balance'], 3000000)
        self.assertEqual(d_early['receivable_balance'], 0)
        self.assertEqual(d_early['active_count'], 0)

        # Margin income outside the period is excluded: the installment was paid on 10/02/2026
        d_from_march = self.delta(s0_from_march, self.summary(end, date_from=march))
        self.assertEqual(d_from_march['margin_income'], 0)
        self.assertEqual(d_from_march['cash_balance'], d['cash_balance'])  # balances do not depend on date_from

    def test_message(self):
        akad = self.activate(self.create_akad())
        self.pay(akad, 900000)
        rec = self.env['koperasi.ringkasan'].with_user(self.user_pengurus).create(
            {'date_to': date(2026, 12, 31), 'date_from': date(2026, 1, 1)})
        text = rec.message
        self.assertIn('per 31 Desember 2026', text)
        self.assertIn(f"Kas & bank: {format_rp(rec.cash_balance)}", text)
        self.assertIn(f"Sisa piutang: {format_rp(rec.receivable_balance)}", text)
        self.assertIn(f"Pendapatan margin sejak 1 Januari 2026: {format_rp(rec.margin_income)}", text)
        self.assertIn(f"Total simpanan pokok: {format_rp(rec.simpanan_pokok)}", text)
        self.assertIn(f"Aset bersih koperasi: {format_rp(rec.net_assets)}", text)
        # Privacy: no member names in a text meant for the whole group
        self.assertNotIn(self.member.name, text)
        self.assertNotIn(self.non_member.name, text)

    def test_access(self):
        with self.assertRaises(AccessError):
            self.env['koperasi.ringkasan'].with_user(self.user_petugas).create({})
        self.env['koperasi.ringkasan'].with_user(self.user_pengurus).create({})
        self.env['koperasi.ringkasan'].with_user(self.user_akuntan).create({})
