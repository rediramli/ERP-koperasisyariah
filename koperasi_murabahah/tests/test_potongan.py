from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from ..models.akad import pupmsjt
from .common import MurabahahCommon


@tagged('post_install', '-at_install', 'koperasi')
class TestPotongan(MurabahahCommon):
    """Early payoff (PUPMSJT), installment discount (khashm) and ta'zir rules."""

    def test_pupmsjt_ojk_simulations(self):
        # Pedoman Produk Pembiayaan Murabahah OJK 2023, simulasi A dan B (hal. 42-45) dan jurnal PUPMSJT (hal. 54)
        a = pupmsjt(100000000, 1797604, 124000000, 24, 3, 10333333, 93201312, 113666667)
        self.assertEqual((a['tsaman_naqdy'], a['qimah_haliyyah'], a['rest_pupmsjt']), (101797604, 104572903, 94239570))
        self.assertEqual((a['basis'], a['due'], a['discount']), ('pupmsjt', 94239570, 19427097))
        b = pupmsjt(100000000, 1797604, 124000000, 24, 20, 98166667, 24496590, 25833333)
        self.assertEqual((b['qimah_haliyyah'], b['rest_pupmsjt']), (120299601, 22132934))
        self.assertEqual((b['basis'], b['due']), ('pokok', 24496590))  # sisa PUPMSJT < sisa pokok: ambil sisa pokok
        # past maturity: no discount, the whole remaining receivable is due
        c = pupmsjt(100000000, 1797604, 124000000, 24, 30, 98166667, 24496590, 25833333)
        self.assertEqual(c['discount'], 0)

    def payoff_wizard(self, akad, when, **values):
        return self.env['koperasi.murabahah.payoff.wizard'].with_user(self.user_pengurus).with_context(
            default_akad_id=akad.id).create(dict({'date': when, 'journal_id': self.journal_cash.id}, **values))

    def test_payoff_by_formula(self):
        # principal 9.000.000, margin 1.800.000 (150.000/month), debt 10.800.000, 12 months, akad 10/01/2026
        akad = self.activate(self.create_akad())
        self.pay(akad, 900000 * 3)
        wizard = self.payoff_wizard(akad, date(2026, 5, 10))
        self.assertEqual(wizard.discount_policy, 'rumus')
        # tsaman naqdy 9.150.000; month 5: + 5 x 137.500 = 9.837.500; minus 2.700.000 paid = 7.137.500 (> sisa pokok 6.750.000)
        self.assertEqual((wizard.calc_tsaman_naqdy, wizard.calc_months, wizard.calc_qimah_haliyyah),
                         (9150000, 5, 9837500))
        self.assertEqual((wizard.calc_rest, wizard.calc_discount), (7137500, 8100000 - 7137500))
        self.assertEqual(wizard.amount_to_pay, 7137500)
        wizard.action_confirm()
        self.assertEqual(akad.state, 'lunas')
        payment = akad.payment_ids.filtered(lambda p: p.payment_type == 'pelunasan')
        self.assertEqual((payment.amount, payment.amount_discount, payment.discount_type), (7137500, 962500, 'pelunasan'))
        self.assertIn('PUPMSJT', payment.discount_note)
        # PSAK 102 par. 23: the discount reduces murabahah income
        self.assertEqual(-self.ledger(akad, self.acc_income), 1800000 - 962500)
        self.assert_invariants(akad)

    def test_payoff_without_discount_and_late(self):
        akad = self.activate(self.create_akad())
        wizard = self.payoff_wizard(akad, date(2026, 2, 10), discount_policy='tanpa')
        self.assertGreater(wizard.calc_discount, 0)
        self.assertEqual(wizard.discount_amount, 0)
        wizard.action_confirm()
        self.assertEqual(-self.ledger(akad, self.acc_income), 1800000)
        self.assert_invariants(akad)
        late = self.activate(self.create_akad())
        self.assertEqual(self.payoff_wizard(late, date(2027, 6, 10)).calc_discount, 0)  # past maturity

    def test_payoff_manual_and_company_policy(self):
        akad = self.activate(self.create_akad())
        wizard = self.payoff_wizard(akad, date(2026, 3, 10), discount_policy='manual', manual_discount=100000)
        with self.assertRaises(UserError):  # reason required
            wizard.action_confirm()
        self.company.murabahah_payoff_method = 'kebijakan'
        self.assertEqual(self.payoff_wizard(akad, date(2026, 3, 10)).discount_policy, 'manual')

    def test_installment_discount(self):
        akad = self.activate(self.create_akad())
        payment = akad.with_user(self.user_pengurus)._register_payment(
            date(2026, 2, 10), self.journal_cash, amount=850000, discount=50000,
            discount_type='tepat_waktu', discount_note='Selalu bayar sebelum jatuh tempo')
        first = akad.line_ids.sorted('sequence')[0]
        self.assertEqual(first.state, 'lunas')
        self.assertEqual((first.paid_margin, first.discount_margin), (100000, 50000))
        self.assertEqual((payment.amount, payment.amount_discount, payment.discount_type), (850000, 50000, 'tepat_waktu'))
        self.assertEqual(self.ledger(akad, self.acc_cash), -9650000 + 650000 + 850000)
        self.assertEqual(-self.ledger(akad, self.acc_income), 100000)
        self.assertEqual(akad.remaining_receivable, 10800000 - 900000)
        disc_lines = payment.margin_move_id.line_ids.filtered(lambda l: 'Potongan tagihan' in (l.name or ''))
        self.assertEqual(sum(disc_lines.mapped('debit')), 50000)
        self.assert_invariants(akad)

    def test_installment_discount_rules(self):
        akad = self.activate(self.create_akad())
        with self.assertRaises(UserError):  # Petugas may not give a discount
            akad.with_user(self.user_petugas)._register_payment(
                date(2026, 2, 10), self.journal_cash, amount=850000, discount=50000,
                discount_type='tepat_waktu', discount_note='x')
        with self.assertRaises(UserError):  # type and reason required
            akad.with_user(self.user_pengurus)._register_payment(
                date(2026, 2, 10), self.journal_cash, amount=850000, discount=50000)
        with self.assertRaises(UserError):  # only margin can be discounted
            akad.with_user(self.user_pengurus)._register_payment(
                date(2026, 2, 10), self.journal_cash, amount=100000, discount=200000,
                discount_type='keringanan', discount_note='x')

    def test_payment_wizard_discount_preview(self):
        akad = self.activate(self.create_akad())
        wizard = self.env['koperasi.murabahah.payment.wizard'].with_user(self.user_pengurus).create({
            'akad_id': akad.id, 'date': date(2026, 2, 10), 'journal_id': self.journal_cash.id,
            'amount': 800000, 'discount_amount': 100000, 'discount_type': 'keringanan',
            'discount_note': 'Penghasilan turun'})
        self.assertEqual((wizard.preview_discount, wizard.preview_settled, wizard.preview_margin), (100000, 900000, 50000))
        self.assertEqual(wizard.preview_installments, 'ke-1')
        wizard.action_confirm()
        self.assert_invariants(akad)

    def test_tazir_only_when_agreed(self):
        akad = self.activate(self.create_akad())
        with self.assertRaises(UserError):  # the contract does not set a ta'zir
            self.pay(akad, 900000, tazir=10000)
        other = self.create_akad()
        other.tazir_terms = 'Rp 10.000 per angsuran terlambat.'
        self.activate(other)
        with self.assertRaises(UserError):  # not confirmed as deliberate delay (force majeure excluded)
            other.with_user(self.user_petugas)._register_payment(
                date(2026, 2, 10), self.journal_cash, amount=900000, tazir=10000)
        payment = self.pay(other, 900000, tazir=10000)
        self.assertEqual(payment.amount_tazir, 10000)
        self.assertEqual(self.ledger(other, self.acc_charity), -10000)
