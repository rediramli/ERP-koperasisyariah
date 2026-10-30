from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from ..models.akad import split_schedule
from .common import MurabahahCommon


@tagged('post_install', '-at_install', 'koperasi')
class TestSchedule(MurabahahCommon):

    def test_split_exact_to_rupiah(self):
        cases = [
            # (total, margin, count, installment) from sample contracts
            (12500000, 2500000, 15, 833333),   # 15 bulan
            (2640000, 440000, 6, 440000),      # 6 bulan
            (6000000, 1000000, 7, 857143),     # last installment smaller
            (10800000, 1800000, 12, 900000),   # 12 bulan
            (1000000, 333333, 3, 333333),
            (5000, 1000, 1, 5000),
        ]
        for total, margin, count, installment in cases:
            parts = split_schedule(total, margin, count, installment)
            self.assertEqual(len(parts), count)
            self.assertEqual(sum(p + m for p, m in parts), total)
            self.assertEqual(sum(m for _p, m in parts), margin)
            for principal, line_margin in parts:
                self.assertGreaterEqual(principal, 0)
                self.assertGreaterEqual(line_margin, 0)
                self.assertEqual(principal, round(principal))
                self.assertEqual(line_margin, round(line_margin))

    def test_split_proportional(self):
        parts = split_schedule(10800000, 1800000, 12, 900000)
        self.assertTrue(all(p == (750000, 150000) for p in parts))
        parts = split_schedule(6000000, 1000000, 7, 857143)
        self.assertEqual(parts[0], (714286, 142857))
        self.assertEqual(parts[-1][0] + parts[-1][1], 6000000 - 6 * 857143)

    def test_split_invalid(self):
        with self.assertRaises(UserError):
            split_schedule(1000, 100, 3, 600)
        with self.assertRaises(UserError):
            split_schedule(1000, 2000, 3, 333)

    def test_akad_amounts_and_schedule(self):
        akad = self.create_akad()
        # Margin = 20% x (9.650.000 - 650.000)
        self.assertEqual(akad.margin_amount, 1800000)
        self.assertEqual(akad.sale_price, 11450000)
        self.assertEqual(akad.financed_amount, 10800000)
        self.assertEqual(akad.installment_amount, 900000)
        akad.action_compute_schedule()
        self.assertEqual(len(akad.line_ids), 12)
        self.assertEqual(sum(akad.line_ids.mapped('amount_total')), 10800000)
        self.assertEqual(akad.remaining_receivable, 10800000)

    def test_rounding_setting(self):
        self.company.murabahah_installment_rounding = 1000
        akad = self.create_akad(cost=5500000, dp=500000, tenor=7)
        self.assertEqual(akad.installment_amount, 857000)
        akad.action_compute_schedule()
        totals = akad.line_ids.sorted('sequence').mapped('amount_total')
        self.assertEqual(totals[:6], [857000] * 6)
        self.assertEqual(totals[-1], 6000000 - 6 * 857000)

    def test_constraints(self):
        with self.assertRaises(ValidationError):
            self.create_akad(cost=1000000, dp=1000000)
        with self.assertRaises(ValidationError):
            self.create_akad(tenor=0)
