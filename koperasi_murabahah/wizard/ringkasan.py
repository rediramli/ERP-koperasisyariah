from datetime import date

from odoo import api, fields, models

from ..models.akad import COLLECTIBILITY
from ..utils import format_date_id, format_rp  # noqa: F401 (re-exported for tests)


class KoperasiRingkasan(models.TransientModel):
    """One-screen summary for the board and a ready-to-paste broadcast text for the members' group.

    Ledger figures are read from posted journal items up to ``date_to``. Arrears and collectibility
    are always as of today (they come from the schedule). No member names appear in the text.
    """
    _name = 'koperasi.ringkasan'
    _description = 'Ringkasan Koperasi'

    company_id = fields.Many2one('res.company', required=True, readonly=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_to = fields.Date(string='Per Tanggal', required=True, default=fields.Date.context_today)
    date_from = fields.Date(string='Pendapatan Margin Sejak', required=True,
                            default=lambda self: date(fields.Date.context_today(self).year, 1, 1))

    cash_balance = fields.Monetary(string='Kas & Bank', compute='_compute_summary')
    receivable_balance = fields.Monetary(string='Sisa Piutang Murabahah', compute='_compute_summary')
    deferred_margin_balance = fields.Monetary(string='Margin Belum Diterima', compute='_compute_summary')
    receivable_net = fields.Monetary(string='Piutang Bersih (Pokok)', compute='_compute_summary')
    margin_income = fields.Monetary(string='Pendapatan Margin', compute='_compute_summary')
    simpanan_pokok = fields.Monetary(string='Simpanan Pokok', compute='_compute_summary')
    total_assets = fields.Monetary(string='Total Aset', compute='_compute_summary')
    total_liabilities = fields.Monetary(string='Total Kewajiban', compute='_compute_summary')
    net_assets = fields.Monetary(string='Aset Bersih', compute='_compute_summary',
                                 help="Total aset dikurangi kewajiban (= ekuitas termasuk hasil berjalan).")

    active_count = fields.Integer(string='Akad Aktif', compute='_compute_summary')
    closed_count = fields.Integer(string='Akad Lunas dalam Periode', compute='_compute_summary')
    member_count = fields.Integer(string='Anggota Aktif', compute='_compute_summary')
    arrears_count = fields.Integer(string='Akad Menunggak (hari ini)', compute='_compute_summary')
    arrears_amount = fields.Monetary(string='Total Tunggakan (hari ini)', compute='_compute_summary')
    collectibility_text = fields.Char(string='Kolektibilitas (hari ini)', compute='_compute_summary')

    message = fields.Text(string='Teks Broadcast', compute='_compute_summary')

    def _ledger_balances(self, domain):
        groups = self.env['account.move.line'].sudo()._read_group(
            domain + [('company_id', '=', self.company_id.id), ('parent_state', '=', 'posted')],
            groupby=['account_id'], aggregates=['balance:sum'])
        return {account: balance for account, balance in groups}

    @api.depends('company_id', 'date_to', 'date_from')
    def _compute_summary(self):
        for rec in self:
            rec._compute_one()

    def _compute_one(self):
        company = self.company_id
        date_to = self.date_to or fields.Date.context_today(self)
        date_from = self.date_from or date(date_to.year, 1, 1)
        balances = self._ledger_balances([('date', '<=', date_to)])

        def total(predicate):
            return sum(bal for acc, bal in balances.items() if predicate(acc))

        receivable_acc = company.murabahah_receivable_account_id
        deferred_acc = company.murabahah_deferred_margin_account_id
        simpanan_acc = company.koperasi_simpanan_pokok_account_id
        self.cash_balance = total(lambda a: a.account_type == 'asset_cash')
        self.receivable_balance = total(lambda a: a == receivable_acc) if receivable_acc else 0.0
        self.deferred_margin_balance = -total(lambda a: a == deferred_acc) if deferred_acc else 0.0
        self.receivable_net = self.receivable_balance - self.deferred_margin_balance
        self.simpanan_pokok = -total(lambda a: a == simpanan_acc) if simpanan_acc else 0.0
        self.total_assets = total(lambda a: (a.account_type or '').startswith('asset_'))
        self.total_liabilities = -total(lambda a: (a.account_type or '').startswith('liability_'))
        self.net_assets = self.total_assets - self.total_liabilities

        income_acc = company.murabahah_income_account_id
        if income_acc:
            income = self._ledger_balances([('date', '>=', date_from), ('date', '<=', date_to),
                                            ('account_id', '=', income_acc.id)])
            self.margin_income = -sum(income.values())
        else:
            self.margin_income = 0.0

        Akad = self.env['koperasi.murabahah.akad'].sudo()
        # Active as of date_to: signed on or before it and still owing at that date (ledger per contract)
        per_akad = {}
        if receivable_acc:
            groups = self.env['account.move.line'].sudo()._read_group(
                [('company_id', '=', company.id), ('parent_state', '=', 'posted'), ('date', '<=', date_to),
                 ('account_id', '=', receivable_acc.id), ('murabahah_akad_id', '!=', False)],
                groupby=['murabahah_akad_id'], aggregates=['balance:sum'])
            per_akad = {akad: balance for akad, balance in groups}
        self.active_count = len([a for a, bal in per_akad.items() if bal > 0.5 and a.state in ('aktif', 'lunas')])
        self.closed_count = Akad.search_count([
            ('company_id', '=', company.id), ('state', '=', 'lunas'),
            ('date_done', '>=', date_from), ('date_done', '<=', date_to)])
        self.member_count = self.env['res.partner'].sudo().search_count([('koperasi_status', '=', 'anggota')])

        # Arrears and collectibility come from the schedule, so they are as of today
        active_now = Akad.search([('company_id', '=', company.id), ('state', '=', 'aktif')])
        overdue = active_now.filtered(lambda a: a.arrears_amount > 0.5)
        self.arrears_count = len(overdue)
        self.arrears_amount = sum(overdue.mapped('arrears_amount'))
        labels = dict(COLLECTIBILITY)
        counts = {key: len(active_now.filtered(lambda a, k=key: a.collectibility == k)) for key, _ in COLLECTIBILITY}
        self.collectibility_text = ', '.join(f"{labels[k]} {n}" for k, n in counts.items() if n) or '-'
        self.message = self._build_message(date_from, date_to)

    def _build_message(self, date_from, date_to):
        company = self.company_id
        lines = [
            "Assalamu'alaikum warahmatullahi wabarakatuh,",
            f"Bapak/Ibu anggota {company.name} yang kami hormati.",
            "",
            f"Berikut ringkasan keuangan koperasi per {format_date_id(date_to)}:",
            "",
            f"💰 Kas & bank: {format_rp(self.cash_balance)}",
            "",
            "📄 Pembiayaan murabahah",
            f"• Akad aktif: {self.active_count} akad",
            f"• Sisa piutang: {format_rp(self.receivable_balance)}",
            f"  (termasuk margin yang belum diterima {format_rp(self.deferred_margin_balance)})",
        ]
        if self.closed_count:
            lines.append(f"• Akad lunas sejak {format_date_id(date_from)}: {self.closed_count} akad")
        lines += [
            "",
            f"📈 Pendapatan margin sejak {format_date_id(date_from)}: {format_rp(self.margin_income)}",
            "",
            f"👥 Anggota aktif: {self.member_count} orang",
        ]
        if company.koperasi_simpanan_pokok_account_id:
            lines.append(f"• Total simpanan pokok: {format_rp(self.simpanan_pokok)}")
        lines += [
            "",
            f"Aset bersih koperasi: {format_rp(self.net_assets)}",
            "",
            "Jazakumullahu khairan atas amanah dan kepercayaannya.",
            "Wassalamu'alaikum warahmatullahi wabarakatuh.",
            "",
            f"Pengurus {company.name}",
        ]
        return "\n".join(lines)
