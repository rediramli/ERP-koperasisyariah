from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    koperasi_wa_number = fields.Char(
        string='Nomor WhatsApp CS Koperasi',
        config_parameter='koperasi_website.wa_number',
        help='Nomor WhatsApp (format internasional tanpa +, contoh: 6281234567890)',
    )
    koperasi_simulasi_margin_pct = fields.Float(
        string='Margin Default Simulasi (%)',
        config_parameter='koperasi_website.simulasi_margin_pct',
        default=20.0,
        help='Persentase margin yang dipakai kalkulator simulasi website publik',
    )
