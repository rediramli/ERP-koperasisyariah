{
    'name': 'Koperasi Syariah - Murabahah',
    'version': '20.0.1.9.1',
    'summary': 'Akad murabahah, jadwal angsuran, pembayaran, jurnal otomatis, laporan',
    'description': """
Pembiayaan murabahah koperasi syariah:
- Penjamin anggota (kafalah) untuk pemohon bukan anggota + cetak Surat Penjaminan
- Pengajuan (SOP-PEMBIAYAAN.md): pra-skrining, verifikasi KYC + checklist dokumen per kategori, survei, lalu akad draft untuk analisis
- Akad: draft -> disetujui -> barang dibeli -> aktif -> lunas / batal
- Jadwal angsuran (porsi pokok:margin proporsional, pembulatan Rp 1, selisih di angsuran terakhir)
- Terima angsuran: jurnal kas + jurnal pengakuan margin, alokasi ke angsuran tertua
- Pelunasan dipercepat (Pengurus): potongan rumus PUPMSJT (Fatwa 153/2022) atau kebijakan Pengurus
- Analisis kelayakan (DSR) dan persetujuan tercatat; benturan kepentingan pengurus
- Agunan: register per akad (taksiran, penyimpanan), tanda terima, pengingat pengembalian saat lunas/batal
- Potongan tagihan (khashm) di Terima Angsuran; ta'zir hanya jika diatur di akad (PSAK 102 par. 13)
- Penjadwalan kembali / restrukturisasi (Pengurus): sisa piutang dibagi ulang, tidak bertambah
- Denda ta'zir opsional ke Dana Kebajikan (bukan pendapatan)
- Import akad berjalan (saldo awal sudah dijurnal, tidak dijurnal ulang)
- Laporan: kartu angsuran, akad aktif, tunggakan, rekap pendapatan margin
- Rincian harga perolehan; wa'd & wakalah (validasi urutan); kembalikan uang muka saat batal (dikurangi biaya riil)
- Dokumen: Surat Janji Pembelian (Wa'd), Akad Wakalah, Akad Murabahah (+ lampiran jadwal), Surat Pengakuan Utang, Berita Acara Serah Terima; spesifikasi barang & khiyar
- Ringkasan Koperasi: kas, piutang, pendapatan margin, aset bersih + teks broadcast WhatsApp
""",
    'category': 'Accounting',
    'author': 'Redi Ramli',
    'website': 'https://github.com/rediramli/ERP-koperasisyariah',
    'license': 'LGPL-3',
    'depends': ['koperasi_base', 'account', 'mail'],
    'data': [
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'data/pengajuan_data.xml',
        'views/agunan_views.xml',
        'views/akad_views.xml',
        'views/pengajuan_views.xml',
        'views/angsuran_views.xml',
        'views/payment_views.xml',
        'views/reschedule_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/purchase_wizard_views.xml',
        'wizard/down_payment_wizard_views.xml',
        'wizard/payment_wizard_views.xml',
        'wizard/payoff_wizard_views.xml',
        'wizard/import_wizard_views.xml',
        'wizard/ringkasan_views.xml',
        'wizard/reschedule_wizard_views.xml',
        'wizard/dp_refund_wizard_views.xml',
        'report/report_actions.xml',
        'report/report_kartu_angsuran.xml',
        'report/report_akad_list.xml',
        'report/report_akad_documents.xml',
        'report/report_agunan.xml',
        'views/menus.xml',
    ],
    'post_init_hook': '_post_init_hook',
    'installable': True,
    'application': False,
}
