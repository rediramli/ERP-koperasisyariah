# ERP Koperasi Syariah (Odoo 20 Community)

Modul Odoo 20 Community untuk koperasi syariah, dengan fokus pada pembiayaan **murabahah**: pengajuan dan KYC, akad, jadwal angsuran, jurnal otomatis sesuai PSAK 102, laporan, sampai website pengajuan online.

Semua label, menu, dan dokumen cetak dalam Bahasa Indonesia. Tidak butuh Odoo Enterprise.

> **Status:** dipakai di satu koperasi sejak Oktober 2026. Format dokumen akad, rumus potongan pelunasan, dan kebijakan pembiayaan **wajib ditinjau Dewan Pengawas Syariah (DPS) dan akuntan koperasi Anda** sebelum dipakai. Selama format dokumen belum ditandai "disetujui DPS" di Pengaturan, semua dokumen cetak bertanda **DRAF**.

## Modul

| Modul | Isi |
|---|---|
| `koperasi_base` | Data anggota (no. anggota, status, tanggal masuk/keluar, pengurus), profil **KYC** (identitas, pasangan, domisili, pekerjaan, kontak darurat, cek DTTOT/PEP, tingkat risiko), **pembacaan NIK otomatis** (tanggal lahir, jenis kelamin, wilayah dari kode Kemendagri 2025), grup akses Petugas / Pengurus / Akuntan, menu Koperasi. Data KYC hanya terbaca oleh grup Koperasi. |
| `koperasi_murabahah` | Pengajuan → akad → angsuran → pelunasan. Detailnya di bawah. |
| `koperasi_website` | Landing page, kalkulator simulasi angsuran, formulir pendaftaran anggota, dan formulir pengajuan pembiayaan online (membuat Pengajuan, tidak langsung membuat kontak/akad), tombol WhatsApp. |

### Fitur `koperasi_murabahah`

- **Pengajuan (SOP pembiayaan):** pra-skrining (DP minimal dan tenor maksimal per kategori, usia, tunggakan, DSR, risiko), verifikasi KYC dengan **checklist dokumen** per kategori (dokumen pasangan hanya bila menikah, BPKB/STNK hanya untuk kendaraan), survei, lalu akad draft dibuat otomatis. Pesan WhatsApp permintaan dokumen siap salin.
- **Penjamin (kafalah)** untuk pemohon bukan anggota, dengan cetak Surat Penjaminan. Kebijakan non-anggota bisa diatur: boleh / dengan penjamin / dengan dasar persetujuan / tidak boleh.
- **Analisis kelayakan:** penghasilan, kewajiban lain, DSR otomatis, catatan 5C, rekomendasi petugas. Persetujuan tercatat. Aturan **benturan kepentingan**: tidak ada yang bisa menyetujui, menjadwal ulang, atau memberi potongan untuk pembiayaannya sendiri atau yang ia jamin. Plafon pembiayaan pengurus.
- **Akad:** draft → disetujui → barang dibeli → aktif → lunas/batal. Wa'd dan **wakalah** dengan validasi urutan (barang milik koperasi sebelum akad), rincian harga perolehan, uang muka (urbun) dan pengembaliannya bila batal.
- **Jadwal angsuran:** porsi pokok dan margin proporsional, pembulatan Rp 1, selisih di angsuran terakhir.
- **Jurnal otomatis** (PSAK 102): pembelian barang, uang muka, akad (piutang / persediaan / margin ditangguhkan), angsuran, pengakuan margin, ta'zir ke dana kebajikan (bukan pendapatan), potongan. Semua akun dan jurnal bisa diatur. Kontrol saldo buku besar per akad.
- **Terima angsuran:** alokasi ke angsuran tertua, potongan tagihan (khashm), ta'zir hanya bila diatur di akad dan bukan force majeure.
- **Pelunasan dipercepat** dengan rumus **PUPMSJT** (Fatwa DSN-MUI 153/2022, pedoman OJK) atau kebijakan pengurus.
- **Penjadwalan kembali** (restrukturisasi, Fatwa DSN-MUI 48/2005): sisa piutang dibagi ulang tanpa tambahan, riwayat tidak bisa diubah.
- **Agunan:** register, nilai taksiran, lokasi simpan, tanda terima, pengingat pengembalian saat lunas.
- **Dokumen cetak:** Akad Murabahah, Surat Pengakuan Utang, Berita Acara Serah Terima, Surat Janji Pembelian (Wa'd), Akad Wakalah, Surat Penjaminan (Kafalah), Tanda Terima Agunan, Kartu Angsuran.
- **Laporan:** daftar akad aktif dengan kolektibilitas (Lancar s.d. Macet, batas hari bisa diatur), daftar tunggakan, rekap pendapatan margin, **Ringkasan Koperasi** (kas, piutang, aset bersih) plus teks broadcast WhatsApp tanpa nama anggota.
- **Import akad berjalan** dari Excel/CSV untuk migrasi.
- 88 unit test (invarian saldo piutang dan margin, alokasi, jurnal, hak akses).

## Kebutuhan

- **Odoo 20 Community** (diuji dengan image Docker `odoo:20`, versi `20.0-20261015`) dan PostgreSQL 16.
- Modul bawaan: `account`, `contacts`, `mail`, `website`, `portal`. Bagan akun Indonesia (`l10n_id`) disarankan.
- Opsional, untuk Neraca/Laba Rugi/Buku Besar di Community: [Odoo Mates `accounting_pdf_reports` dan `om_account_accountant`](https://github.com/odoomates/odooapps) branch 20.0.
- Python: `num2words` (sudah ada di image resmi Odoo) untuk terbilang di dokumen.

## Instalasi singkat (Docker)

1. Salin ketiga folder modul ke folder addons yang di-mount ke container, mis. `./addons → /mnt/extra-addons`.
2. Pastikan `/mnt/extra-addons` ada di `addons_path` pada `odoo.conf`. Di Docker, Odoo 20 juga butuh `http_interface = 0.0.0.0`.
3. Restart Odoo, aktifkan mode pengembang, **Apps → Update Apps List**, lalu pasang **Koperasi Syariah - Murabahah** (dan **Website** bila perlu).
4. Buka **Koperasi → Konfigurasi → Pengaturan**: pilih jurnal, akun murabahah (piutang, margin ditangguhkan, persediaan, uang muka, dana kebajikan, pendapatan margin), aturan pembulatan, batas DSR, kebijakan non-anggota, penandatangan dokumen.
5. Beri pengguna grup **Koperasi / Petugas**, **Pengurus**, atau **Akuntan** (Pengaturan → Pengguna).
6. Atur **Kategori Pembiayaan** dan **Checklist Dokumen** sesuai kebijakan koperasi.

Menjalankan test:

```bash
odoo -c /etc/odoo/odoo.conf -d <db_test> -u koperasi_murabahah --test-enable \
  --test-tags /koperasi_murabahah --stop-after-init --no-http --http-port=8079
```

Selalu uji di database terpisah, jangan di database produksi.

## Dokumen

- [`docs/SOP-PEMBIAYAAN.md`](docs/SOP-PEMBIAYAAN.md): SOP pembiayaan murabahah 10 tahap (permohonan, pra-skrining, KYC, survei, analisis, keputusan, pembelian, akad, penagihan, pelunasan), peran four-eyes, checklist berkas, dan daftar keputusan yang harus ditetapkan pengurus.

## Acuan

Fatwa DSN-MUI 04/2000 (Murabahah), 10/2000 (Wakalah), 11/2000 (Kafalah), 13/2000 (Uang Muka), 46/2005 (Potongan Tagihan), 48/2005 (Penjadwalan Kembali), 153/2022 (Pelunasan Dipercepat); Pedoman Produk Murabahah OJK 2023; PSAK 102 (PSAK 402) Akuntansi Murabahah; UU 27/2022 Pelindungan Data Pribadi.

Modul ini membantu pencatatan dan kontrol. Modul ini bukan nasihat hukum, syariah, atau akuntansi.

## Lisensi dan jasa

Kode berlisensi [LGPL-3.0](LICENSE): bebas dipakai, diubah, dan disebarkan sesuai ketentuan lisensi.

Data kode wilayah (`koperasi_base/data/koperasi.wilayah.csv`) diolah dari [cahyadsn/wilayah](https://github.com/cahyadsn/wilayah) sesuai Kepmendagri No. 300.2.2-2138 Tahun 2025, copyright (c) 2025 cahya dsn, lisensi MIT.

Butuh bantuan instalasi, hosting, migrasi data dari Excel, penyesuaian, atau pelatihan untuk koperasi Anda? Hubungi **Redi Ramli** lewat [GitHub](https://github.com/rediramli).
