from datetime import date

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import MurabahahCommon


@tagged('post_install', '-at_install', 'koperasi')
class TestReschedule(MurabahahCommon):
    """Penjadwalan kembali: the remaining receivable and margin are spread again, never increased."""

    def setUp(self):
        super().setUp()
        # cost 9.650.000, down payment 650.000, margin 1.800.000, receivable 10.800.000 = 12 x 900.000
        self.akad = self.activate(self.create_akad())
        self.pay(self.akad, 900000, pay_date=date(2026, 2, 10))   # installment 1 in full
        self.pay(self.akad, 400000, pay_date=date(2026, 3, 10))   # installment 2 partly

    def reschedule(self, user=None, **kwargs):
        values = dict(date=date(2026, 5, 1), first_due_date=date(2026, 6, 10), reason='Penghasilan turun')
        values.update(kwargs)
        return self.akad.with_user(user or self.user_pengurus)._reschedule(**values)

    def balances(self):
        self.akad.invalidate_recordset()
        return (self.akad.remaining_receivable, self.akad.remaining_margin,
                self.ledger(self.akad, self.acc_receivable), -self.ledger(self.akad, self.acc_deferred))

    def test_spread_without_increase(self):
        before = self.balances()
        self.assertEqual(before[0], 10800000 - 1300000)
        moves_before = self.akad.move_ids
        record = self.reschedule(count=20)

        self.assertEqual(self.balances(), before)          # nothing owed added or removed
        self.assertEqual(self.akad.move_ids, moves_before)  # no journal entry
        self.assert_invariants(self.akad)

        lines = self.akad.line_ids.sorted('sequence')
        self.assertEqual([l.sequence for l in lines], list(range(1, 23)))
        # Installment 2 closed at what was paid; still "lunas", nothing left on it
        second = lines[1]
        self.assertEqual(second.amount_total, 400000)
        self.assertEqual(second.state, 'lunas')
        new = lines[2:]
        self.assertEqual(len(new), 20)
        self.assertEqual(sum(new.mapped('amount_total')), before[0])
        self.assertEqual(sum(new.mapped('amount_margin')), before[1])
        self.assertEqual(new[0].date_due, date(2026, 6, 10))
        self.assertEqual(new[-1].date_due, date(2028, 1, 10))
        self.assertTrue(all(l.amount_total == 475000 for l in new))  # 9.500.000 / 20

        self.assertEqual(record.name, '%s/R1' % self.akad.name)
        self.assertEqual((record.old_count, record.new_count, record.new_installment), (11, 20, 475000))
        self.assertEqual(record.remaining_receivable, before[0])
        self.assertEqual(record.user_id, self.user_pengurus)
        self.assertIn('Ke-2', record.old_schedule)
        self.assertEqual(self.akad.reschedule_count, 1)

    def test_by_installment_amount(self):
        self.reschedule(installment=2000000)
        new = self.akad.line_ids.filtered(lambda l: l.state != 'lunas').sorted('sequence')
        # 9.500.000 = 4 x 2.000.000 + 1.500.000
        self.assertEqual(new.mapped('amount_total'), [2000000] * 4 + [1500000])
        self.assert_invariants(self.akad)

    def test_pay_off_after_reschedule(self):
        self.reschedule(count=3)
        for amount in self.akad.line_ids.filtered(lambda l: l.residual > 0).sorted('sequence').mapped('residual'):
            self.pay(self.akad, amount, pay_date=date(2026, 7, 1))
        self.assertEqual(self.akad.state, 'lunas')
        self.assert_invariants(self.akad)
        # all margin recognized, none lost by the rescheduling
        self.assertEqual(self.akad.margin_recognized, self.akad.margin_amount)

    def test_twice_and_arrears(self):
        # Today the schedule from 10/02/2026 is overdue; a new schedule starting next year clears arrears
        self.assertGreater(self.akad.arrears_days, 0)
        first = self.reschedule(count=10, date=date(2026, 5, 1), first_due_date=date(2030, 1, 10))
        self.assertGreater(first.arrears_days, 0)
        self.akad.invalidate_recordset()
        self.assertEqual(self.akad.arrears_amount, 0)
        self.assertEqual(self.akad.collectibility, 'lancar')
        second = self.reschedule(count=5, date=date(2026, 6, 1), first_due_date=date(2030, 3, 10))
        self.assertEqual(second.name, '%s/R2' % self.akad.name)
        self.assertEqual(self.akad.reschedule_count, 2)
        self.assert_invariants(self.akad)

    def test_rules(self):
        with self.assertRaises((UserError, AccessError)):
            self.reschedule(user=self.user_petugas, count=10)
        with self.assertRaises(UserError):
            self.reschedule(count=10, date=date(2026, 3, 1))           # before the last payment
        with self.assertRaises(UserError):
            self.reschedule(count=10, first_due_date=date(2026, 4, 1))  # first due before the rescheduling
        with self.assertRaises(UserError):
            self.reschedule(count=10, reason='  ')
        with self.assertRaises(UserError):
            self.reschedule()                                           # neither count nor installment
        draft = self.create_akad()
        with self.assertRaises(UserError):
            draft.with_user(self.user_pengurus)._reschedule(date(2026, 5, 1), date(2026, 6, 1), 'x', count=3)
        # history is read-only
        record = self.reschedule(count=10)
        with self.assertRaises(UserError):
            record.with_user(self.user_pengurus).write({'reason': 'ubah'})
        with self.assertRaises(UserError):
            record.with_user(self.user_pengurus).unlink()

    def test_cancel_payment_around_reschedule(self):
        older = self.akad.payment_ids.sorted('date')[-1]
        self.reschedule(count=10)
        with self.assertRaises(UserError):
            older.with_user(self.user_pengurus).action_cancel()
        newer = self.pay(self.akad, 500000, pay_date=date(2026, 6, 10))
        newer.with_user(self.user_pengurus).action_cancel()
        self.assertEqual(newer.state, 'cancel')
        self.assert_invariants(self.akad)

    def test_wizard(self):
        Wizard = self.env['koperasi.murabahah.reschedule.wizard'].with_user(self.user_pengurus)
        wizard = Wizard.with_context(default_akad_id=self.akad.id).create({
            'date': date(2026, 5, 1), 'first_due_date': date(2026, 6, 10), 'mode': 'count',
            'reason': 'Kesepakatan 1 Mei 2026'})
        self.assertEqual(wizard.new_count, 11)  # default: number of unpaid installments
        wizard.new_count = 19
        self.assertFalse(wizard.plan_error)
        self.assertEqual(wizard.plan_count, 19)
        self.assertEqual(wizard.plan_installment, 500000)
        self.assertIn('9,500,000', wizard.preview)
        wizard.first_due_date = date(2026, 4, 1)
        self.assertTrue(wizard.plan_error)
        wizard.first_due_date = date(2026, 6, 10)
        wizard.action_confirm()
        self.assertEqual(self.akad.reschedule_count, 1)
        self.assert_invariants(self.akad)
        with self.assertRaises(AccessError):
            self.env['koperasi.murabahah.reschedule.wizard'].with_user(self.user_petugas).create({
                'akad_id': self.akad.id, 'reason': 'x'})
