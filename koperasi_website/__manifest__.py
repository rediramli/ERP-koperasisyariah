{
    'name': 'Koperasi Syariah - Website & Portal Pengajuan',
    'version': '20.0.1.1.1',
    'summary': 'Landing page syariah, pendaftaran anggota online, dan form pengajuan pembiayaan murabahah',
    'description': """
Website publik koperasi syariah:
- Landing Page Profesional Syariah (Hero banner, keunggulan tanpa riba, simulasi angsuran, portofolio & FAQ)
- Formulir Online Pendaftaran Anggota Baru (/daftar) terhubung ke master kontak Odoo
- Formulir Online Pengajuan Pembiayaan Murabahah (/pengajuan) terhubung ke draft akad murabahah Odoo
- Widget Kalkulator Simulasi Pembiayaan Real-time
- Tombol WhatsApp CS terintegrasi
    """,
    'category': 'Website/Website',
    'author': 'Redi Ramli',
    'website': 'https://github.com/rediramli/ERP-koperasisyariah',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'website',
        'portal',
        'koperasi_base',
        'koperasi_murabahah',
    ],
    'data': [
        'data/website_menu_data.xml',
        'views/res_partner_views.xml',
        'views/res_config_settings_views.xml',
        'views/website_templates.xml',
        'views/form_daftar_templates.xml',
        'views/form_pengajuan_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'koperasi_website/static/src/css/style.css',
            'koperasi_website/static/src/js/simulasi.js',
        ],
    },
    'installable': True,
    'application': True,
}
