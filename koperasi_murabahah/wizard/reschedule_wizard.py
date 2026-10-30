from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError


class KoperasiMurabahahRescheduleWizard(models.TransientModel):
    _name = 'koperasi.murabahah.reschedule.wizard'
    _description = 'Penjadwalan Kembali Murabahah'

    akad_id = fields.Many2one('koperasi.murabahah.akad', string='Akad', required=True, readonly=True)
    partner_id = fields.Many2one(related='akad_id.partner_id')
    company_id = fields.Many2one(related='akad_id.company_id')
    currency_id = fields.Many2one(related='akad_id.currency_id')
    remaining_receivable = fields.Monetary(related='akad_id.remaining_receivable')
    remaining_principal = fields.Monetary(related='akad_id.remaining_principal')
    remaining_margin = fields.Monetary(related='akad_id.remaining_margin')
    arrears_amount = fields.Monetary(related='akad_id.arrears_amount')
    arrears_days = fields.Integer(related='akad_id.arrears_days')
    collectibility = fields.Selection(related='akad_id.collectibility')
    reschedule_count = fields.Integer(related='akad_id.reschedule_count')

    date = fields.Date(string='Tanggal Restrukturisasi', required=True, default=fields.Date.context_today)
    first_due_date = fields.Date(
        string='Jatuh Tempo Pertama (Baru)', required=True,
        default=lambda self: fields.Date.context_today(self) + relativedelta(months=1))
    mode = fields.Selection(
        [('count', 'Tentukan jumlah angsuran'), ('amount', 'Tentukan besar angsuran')],
        string='Cara', required=True, default='count')
    new_count = fields.Integer(string='Jumlah Angsuran Baru')
    new_installment = fields.Monetary(string='Besar Angsuran Baru')
    reason = fields.Text(string='Alasan / Dasar Persetujuan', required=True,
                         help="Mis. penghasilan anggota turun; kesepakatan pengurus dan anggota tanggal ...")

    plan_count = fields.Integer(string='Jumlah Angsuran', compute='_compute_plan')
    plan_installment = fields.Monetary(string='Angsuran per Bulan', compute='_compute_plan')
    plan_last_due = fields.Date(string='Jatuh Tempo Terakhir', compute='_compute_plan')
    preview = fields.Html(string='Jadwal Baru', compute='_compute_plan', sanitize=False)
    plan_error = fields.Char(compute='_compute_plan')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        akad = self.env['koperasi.murabahah.akad'].browse(res.get('akad_id'))
        if akad and 'new_count' in fields_list:
            res['new_count'] = len(akad._open_lines())
        return res

    def _plan(self):
        self.ensure_one()
        if self.mode == 'count':
            return self.akad_id._reschedule_plan(self.date, self.first_due_date, count=self.new_count)
        return self.akad_id._reschedule_plan(self.date, self.first_due_date, installment=self.new_installment)

    @api.depends('akad_id', 'date', 'first_due_date', 'mode', 'new_count', 'new_installment')
    def _compute_plan(self):
        for wizard in self:
            wizard.plan_count = 0
            wizard.plan_installment = 0.0
            wizard.plan_last_due = False
            wizard.preview = False
            wizard.plan_error = False
            if not wizard.akad_id:
                continue
            try:
                plan = wizard._plan()
            except UserError as error:
                wizard.plan_error = error.args[0] if error.args else str(error)
                continue
            wizard.plan_count = plan['count']
            wizard.plan_installment = plan['installment']
            wizard.plan_last_due = plan['lines'][-1]['date_due']
            wizard.preview = wizard._render_preview(plan)

    def _render_preview(self, plan):
        rows = Markup()
        total_p = total_m = 0.0
        for i, line in enumerate(plan['lines'], start=1):
            total_p += line['amount_principal']
            total_m += line['amount_margin']
            rows += Markup(
                "<tr><td class='text-center'>%s</td><td>%s</td><td class='text-end'>%s</td>"
                "<td class='text-end'>%s</td><td class='text-end'>%s</td></tr>") % (
                i, line['date_due'].strftime('%d/%m/%Y'), f"{line['amount_principal']:,.0f}",
                f"{line['amount_margin']:,.0f}", f"{line['amount_principal'] + line['amount_margin']:,.0f}")
        head = Markup(
            "<table class='table table-sm table-bordered mb-0'><thead><tr>"
            "<th class='text-center'>Baru Ke-</th><th>Jatuh Tempo</th><th class='text-end'>Pokok</th>"
            "<th class='text-end'>Margin</th><th class='text-end'>Angsuran</th></tr></thead><tbody>")
        foot = Markup(
            "</tbody><tfoot><tr><th colspan='2'>Total (= sisa piutang, tidak bertambah)</th>"
            "<th class='text-end'>%s</th><th class='text-end'>%s</th><th class='text-end'>%s</th></tr></tfoot></table>") % (
            f"{total_p:,.0f}", f"{total_m:,.0f}", f"{total_p + total_m:,.0f}")
        return head + rows + foot

    def action_confirm(self):
        self.ensure_one()
        if self.mode == 'count':
            record = self.akad_id._reschedule(self.date, self.first_due_date, self.reason, count=self.new_count)
        else:
            record = self.akad_id._reschedule(self.date, self.first_due_date, self.reason,
                                              installment=self.new_installment)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'koperasi.murabahah.akad',
            'res_id': record.akad_id.id,
            'view_mode': 'form',
        }
