from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    murabahah_journal_id = fields.Many2one(
        related='company_id.murabahah_journal_id', readonly=False,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]")
    murabahah_cash_journal_id = fields.Many2one(
        related='company_id.murabahah_cash_journal_id', readonly=False,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]")
    murabahah_receivable_account_id = fields.Many2one(
        related='company_id.murabahah_receivable_account_id', readonly=False)
    murabahah_deferred_margin_account_id = fields.Many2one(
        related='company_id.murabahah_deferred_margin_account_id', readonly=False)
    murabahah_inventory_account_id = fields.Many2one(
        related='company_id.murabahah_inventory_account_id', readonly=False)
    murabahah_down_payment_account_id = fields.Many2one(
        related='company_id.murabahah_down_payment_account_id', readonly=False)
    murabahah_charity_account_id = fields.Many2one(
        related='company_id.murabahah_charity_account_id', readonly=False)
    murabahah_income_account_id = fields.Many2one(
        related='company_id.murabahah_income_account_id', readonly=False)
    murabahah_real_cost_account_id = fields.Many2one(
        related='company_id.murabahah_real_cost_account_id', readonly=False)
    koperasi_simpanan_pokok_account_id = fields.Many2one(
        related='company_id.koperasi_simpanan_pokok_account_id', readonly=False)
    murabahah_margin_method = fields.Selection(
        related='company_id.murabahah_margin_method', readonly=False)
    murabahah_payoff_method = fields.Selection(related='company_id.murabahah_payoff_method', readonly=False)
    murabahah_installment_rounding = fields.Float(
        related='company_id.murabahah_installment_rounding', readonly=False)
    murabahah_days_dpk = fields.Integer(related='company_id.murabahah_days_dpk', readonly=False)
    murabahah_days_kurang_lancar = fields.Integer(related='company_id.murabahah_days_kurang_lancar', readonly=False)
    murabahah_days_diragukan = fields.Integer(related='company_id.murabahah_days_diragukan', readonly=False)
    murabahah_template_approved = fields.Boolean(related='company_id.murabahah_template_approved', readonly=False)
    murabahah_signatory_name = fields.Char(related='company_id.murabahah_signatory_name', readonly=False)
    murabahah_signatory_title = fields.Char(related='company_id.murabahah_signatory_title', readonly=False)
    murabahah_document_city = fields.Char(related='company_id.murabahah_document_city', readonly=False)
    murabahah_max_dsr = fields.Float(related='company_id.murabahah_max_dsr', readonly=False)
    murabahah_pengurus_limit = fields.Float(related='company_id.murabahah_pengurus_limit', readonly=False)
    murabahah_require_application = fields.Boolean(related='company_id.murabahah_require_application', readonly=False)
    murabahah_min_age = fields.Integer(related='company_id.murabahah_min_age', readonly=False)
    murabahah_max_age = fields.Integer(related='company_id.murabahah_max_age', readonly=False)
    murabahah_non_member_policy = fields.Selection(related='company_id.murabahah_non_member_policy', readonly=False)

