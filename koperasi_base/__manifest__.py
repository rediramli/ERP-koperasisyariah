{
    'name': 'Koperasi Syariah - Dasar',
    'version': '20.0.1.3.1',
    'summary': 'Data anggota, menu utama Koperasi, dan grup akses',
    'description': """
Modul dasar koperasi syariah:
- Baca NIK otomatis: tanggal lahir, jenis kelamin, wilayah (kode Kemendagri 2025), cek ketidakcocokan
- Profil KYC (identitas, pasangan, domisili, pekerjaan, kontak darurat, DTTOT/PEP, tingkat risiko), hanya grup Koperasi
- Perluasan kontak: nomor anggota, tanggal masuk/keluar, status keanggotaan, tanda pengurus, akun Odoo terkait
- Menu utama "Koperasi"
- Grup akses: Petugas, Pengurus, Akuntan
""",
    'category': 'Accounting',
    'author': 'Redi Ramli',
    'website': 'https://github.com/rediramli/ERP-koperasisyariah',
    'license': 'LGPL-3',
    'depends': ['base', 'contacts', 'account'],
    'data': [
        'security/koperasi_security.xml',
        'security/ir.access.csv',
        'data/koperasi.wilayah.csv',
        'views/res_partner_views.xml',
        'views/koperasi_menus.xml',
    ],
    'installable': True,
    'application': True,
}
