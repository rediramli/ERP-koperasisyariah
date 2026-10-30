# SOP Pembiayaan Murabahah — Template Koperasi Syariah

Versi draf 29 Okt 2026. Disusun mengikuti pola yang umum dipakai bank syariah, BPRS, dan perusahaan pembiayaan (multifinance), lalu disederhanakan untuk koperasi kecil (mis. 2 pengurus).
**Status: DRAF.** Angka batas (plafon, uang muka minimal, wewenang memutus) adalah usulan dan harus ditetapkan pengurus. Hasil akhirnya disahkan rapat pengurus, ditinjau DPS, dan dilaporkan di RAT.

Contoh kasus yang dipakai di dokumen ini: **Budi (fiktif), pengajuan sepeda motor.** Budi adalah pelanggan lama (bukan anggota) yang beberapa akad lamanya sudah lunas.

---

## 1. Prinsip dasar

| Prinsip | Artinya di koperasi |
|---|---|
| **Empat mata (four-eyes)** | Orang yang menganalisis tidak boleh sekaligus memutus. Orang yang memutus tidak boleh sekaligus membayar dana. Minimal 2 orang terlibat di setiap pembiayaan. |
| **Kenali pemohon (KYC/CDD)** | Identitas, alamat, pekerjaan, penghasilan, dan tujuan pembiayaan diverifikasi dengan dokumen asli, bukan cukup dari pengakuan lisan. |
| **Berbasis risiko** | Pemeriksaan dibuat sederhana untuk pemohon lama dengan riwayat baik dan nilai kecil, dan diperketat untuk pemohon baru, nilai besar, atau tanda bahaya. |
| **Syariah** | Barang halal. Barang **dimiliki koperasi dulu** sebelum dijual. Harga jual disebut jelas dan tetap. Tidak ada denda yang menjadi pendapatan. |
| **Dana tidak lewat tangan pemohon** | Koperasi membayar langsung ke rekening dealer/pemasok. Wakalah (anggota membeli sendiri) hanya dipakai kalau pembelian langsung memang tidak mungkin. |
| **Data pribadi dilindungi** (UU 27/2022 PDP) | Salinan KTP/KK/slip gaji hanya dilihat petugas yang berwenang, disimpan di Odoo (bukan di HP/WA pribadi), dan dipakai hanya untuk pembiayaan. |
| **Semua tercatat** | Setiap tahap punya bukti di Odoo: siapa, kapan, dan apa keputusannya. |

---

## 2. Peran

| Peran | Diisi koperasi | Tugas |
|---|---|---|
| **Petugas / Analis** (*account officer*) | [nama] (grup Petugas) | Menerima permohonan, mengumpulkan dokumen, KYC, survei, analisis, rekomendasi, menerima angsuran, penagihan awal |
| **Pemutus** (Pengurus) | [nama] (grup Pengurus) | Menyetujui atau menolak, menandatangani akad, menyetujui pembayaran ke dealer |
| **Kasir / Bendahara** | [belum ditetapkan] | Membayar dealer setelah ada persetujuan dan dokumen lengkap |
| **Pengawas / DPS** | [belum ditetapkan] | Memutus pembiayaan untuk pengurus, meninjau sampel berkas, meninjau format akad |

> Bila pengurus hanya 2 orang, pembiayaan untuk salah satu pengurus diputus oleh pengurus lainnya ditambah Pengawas. Sistem menolak orang yang menyetujui akad atas namanya sendiri.

---

## 3. Alur ringkas

```
 1 Permohonan ─► 2 Pra-skrining ─► 3 KYC & dokumen ─► 4 Survei/verifikasi
        │                │ tolak                                   │
        ▼                ▼                                         ▼
 (WA / website / kantor)  surat penolakan          5 Analisis kelayakan (5C + DSR)
                                                                   │
 10 Pelunasan & ◄─ 9 Monitoring & ◄─ 8 Akad, serah ◄─ 7 Pembelian ◄─ 6 Keputusan &
   kembalikan BPKB    penagihan        terima, BPKB      barang         penawaran (wa'd)
```

Target waktu (SLA) dari dokumen lengkap sampai keputusan: **≤ 3 hari kerja**. Dari keputusan sampai barang diterima: mengikuti dealer, biasanya 1–7 hari.

---

## 4. Tahap demi tahap

### Tahap 1 — Permohonan (*intake*)

**Kanal:** chat WhatsApp, formulir website (`/pengajuan`), atau datang langsung. Apa pun kanalnya, petugas **mencatatnya di Odoo pada hari yang sama**, supaya permohonan yang masuk lewat WA tidak hilang.

Data minimum saat permohonan:
- Nama lengkap sesuai KTP, NIK, nomor HP/WA
- Barang yang diinginkan (merek, tipe, tahun, warna), perkiraan harga, dan dealer/penjual (kalau sudah ada)
- Uang muka yang sanggup dibayar, tenor yang diinginkan, kisaran angsuran yang sanggup
- Pekerjaan dan perkiraan penghasilan per bulan
- Tujuan: dipakai sendiri, untuk kerja/usaha, atau untuk keluarga
- Status: anggota / bukan anggota / ingin menjadi anggota

**Contoh balasan WA untuk Budi** (bisa langsung dipakai):

> Wa'alaikumsalam Budi, terima kasih sudah mengajukan lagi ke koperasi. Supaya bisa kami proses, tolong kirim data berikut:
> 1. Motor yang diinginkan: merek, tipe, warna, dan dealer kalau sudah ada (atau kirim foto brosur/penawaran harga OTR)
> 2. Uang muka yang disiapkan dan tenor yang diinginkan (mis. 12/18/24 bulan)
> 3. Pekerjaan sekarang dan penghasilan per bulan
> 4. Foto KTP dan KK (nanti aslinya dicek saat bertemu)
> 5. Slip gaji atau mutasi rekening 3 bulan terakhir
> 6. Kalau sudah menikah: KTP pasangan
>
> Setelah lengkap, kami hitung simulasi angsurannya dan jadwalkan bertemu. Data Budi hanya dipakai untuk pengajuan ini.

> Sebaiknya foto KTP/KK dikirim lewat formulir website atau langsung diunggah petugas ke Odoo, lalu **dihapus dari chat WA**.

### Tahap 2 — Pra-skrining (maks. 1 hari)

Petugas mengecek syarat dasar sebelum meminta dokumen lengkap. Kalau ada syarat yang tidak terpenuhi, permohonan langsung ditolak dengan sopan, tanpa perlu survei.

| Syarat | Usulan |
|---|---|
| Usia | 21 tahun (atau sudah menikah) s.d. 60 tahun saat angsuran terakhir |
| Keanggotaan | Anggota aktif, **atau** bukan anggota dengan **penjamin dari anggota aktif** yang tidak menunggak (contoh kebijakan K1) |
| Barang | Halal dan jelas spesifikasinya. Tidak untuk melunasi utang berbunga (bukan murabahah) |
| Domisili/kerja | Dalam jangkauan penagihan koperasi |
| Uang muka minimal kendaraan | Usulan **≥ 20% harga OTR** untuk motor (lihat **K3**) |
| Tenor maksimal kendaraan | Usulan **≤ 24 bulan** untuk motor |
| Riwayat di koperasi | Tidak sedang menunggak di akad lain. Akad lama yang macet atau direstrukturisasi menjadi catatan |
| Plafon | Total sisa pembiayaan pemohon ≤ batas yang ditetapkan pengurus |

**Budi:** pelanggan lama dengan 4 akad yang sudah lunas, jadi riwayat internalnya menjadi nilai tambah. Ketepatan bayarnya di akad lama dicek di kartu angsuran lama. Satu-satunya syarat yang terbuka adalah status **bukan anggota** (K1).

### Tahap 3 — KYC dan dokumen

**3a. Verifikasi identitas (wajib, setiap pemohon):**

| Pemeriksaan | Cara |
|---|---|
| NIK | Odoo membaca NIK otomatis (tanggal lahir, jenis kelamin, kecamatan/kabupaten penerbitan) dan memberi peringatan bila tidak cocok dengan KTP/KK. Ini hanya cek format, **bukan** bukti NIK terdaftar di Dukcapil. |
| KTP asli | Dilihat langsung. NIK, nama, dan tanggal lahir dicocokkan dengan KK. Foto KTP dicocokkan dengan wajah pemohon. Petugas memotret pemohon memegang KTP |
| KK | Dipakai untuk memastikan status keluarga, tanggungan, dan pasangan |
| Alamat | Alamat KTP dibandingkan dengan alamat domisili. Kalau berbeda, minta bukti tinggal (rekening listrik, surat RT, kontrak sewa) |
| Nomor HP | Ditelepon sekali dan harus dijawab pemohon sendiri |
| Kontak darurat | 1 orang yang **tidak serumah**. Ditelepon untuk konfirmasi bahwa ia kenal pemohon |
| Pasangan | Kalau sudah menikah, pasangan ikut tanda tangan **persetujuan** (praktik standar bank dan multifinance, karena barang menjadi harta bersama) |
| Daftar terduga terorisme/pendanaan senjata (DTTOT/DPPSPM) | Nama dicek ke daftar resmi PPATK/Polri. Hasil dan tanggal cek dicatat. Penerapan APU-PPT untuk koperasi diatur Kemenkop UKM; **cek pasal yang berlaku** |
| Orang yang populer secara politis (PEP) | Ditanyakan dan dicatat. Kalau ya, pemeriksaan diperketat |

**3b. Verifikasi kemampuan bayar:**

| Pemeriksaan | Dokumen |
|---|---|
| Penghasilan | Slip gaji 3 bulan terakhir, **atau** mutasi rekening 3 bulan (pekerja informal/usaha), **atau** surat keterangan usaha + foto usaha |
| Pekerjaan | Surat keterangan kerja / ID karyawan, atau telepon ke kantor (*employment check*) |
| Kewajiban lain | Ditanyakan langsung, lalu **minta pemohon mencetak sendiri iDeb SLIK** di iDebku OJK (gratis). Koperasi bukan pelapor SLIK dan tidak bisa mengecek sendiri, jadi praktik koperasi yang lazim adalah meminta pemohon membawa hasilnya |
| Cicilan lain di koperasi | Otomatis dari Odoo (DSR sudah menghitung akad aktif lain milik pemohon) |

**3c. Dokumen barang (khusus kendaraan):**
- Surat penawaran harga OTR dari dealer resmi, berisi tipe, warna, harga, diskon, dan biaya (BBN, dll.)
- Pembanding harga dari 1 dealer lain atau situs resmi (supaya harga perolehan wajar)

**Tingkat risiko KYC** (dicatat di data pemohon):
- **Rendah:** pemohon lama dengan riwayat lancar, nilai ≤ plafon kecil, dokumen lengkap.
- **Menengah:** pemohon baru, atau penghasilan informal.
- **Tinggi:** PEP, data tidak cocok, sumber dana uang muka tidak jelas, atau ada riwayat macet. Wajib survei dan persetujuan 2 pengurus.

### Tahap 4 — Survei/verifikasi lapangan

Bentuknya kunjungan ke rumah (dan tempat kerja/usaha kalau informal). Untuk pemohon risiko rendah yang rumahnya sudah diketahui, survei boleh diganti telepon dan foto rumah terbaru.

Hasil survei dicatat:
- Tanggal, petugas, dan siapa yang ditemui
- Kondisi rumah dan status kepemilikan (milik sendiri / keluarga / sewa), lama tinggal
- Kecocokan alamat dengan KTP, konfirmasi tetangga/RT (opsional)
- Tempat usaha/kerja, perkiraan omzet
- Tempat motor akan disimpan
- Foto (minimal: depan rumah dengan nomor, pemohon di lokasi)
- Kesimpulan: sesuai / ada catatan / tidak sesuai

### Tahap 5 — Analisis kelayakan (sudah ada di Odoo)

Tab **Analisis & Persetujuan** di akad: sumber dan besar penghasilan, kewajiban lain, tanggungan, catatan 5C, rekomendasi, **DSR** otomatis (batas di Pengaturan, default 40%).

Analisis 5C yang biasa dipakai:
- **Character:** riwayat bayar (internal dan SLIK), kejujuran data, hasil survei.
- **Capacity:** penghasilan bersih dan DSR.
- **Capital:** besar uang muka (makin besar, makin rendah risikonya).
- **Collateral:** BPKB motor ditahan koperasi, plus agunan tambahan bila perlu.
- **Condition:** stabilitas pekerjaan/usaha, kegunaan motor (motor untuk kerja menambah kemampuan bayar).

Petugas menulis **rekomendasi**: layak / layak dengan syarat (mis. uang muka dinaikkan, tenor dipendekkan) / tidak layak.

### Tahap 6 — Keputusan dan penawaran

**Wewenang memutus** (usulan, ditetapkan pengurus, lihat K2):

| Kondisi | Yang memutus |
|---|---|
| Harga jual − uang muka ≤ Rp 15 jt, risiko rendah/menengah, DSR ≤ batas | 1 Pengurus (bukan analis) |
| > Rp 15 jt, **atau** risiko tinggi, **atau** DSR > batas, **atau** rekomendasi "tidak layak" | 2 Pengurus (rapat pengurus) |
| Pemohon adalah pengurus/pengawas/keluarganya | Pengurus lain + Pengawas, dicatat sebagai pembiayaan pihak terkait |

Kalau ditolak: beri tahu pemohon secara tertulis (WA cukup) dengan alasan umum. Berkas tetap disimpan.

Kalau disetujui: buat **Surat Penawaran / Persetujuan Prinsip** yang berisi barang, harga perolehan, margin, harga jual, uang muka, tenor, angsuran, agunan, biaya (bila ada), syarat sebelum akad, dan **masa berlaku 14 hari**. Pemohon menandatangani **Surat Janji Pembelian (Wa'd)**, yang sudah bisa dicetak dari Odoo. Uang muka diterima setelah wa'd ditandatangani (sudah ada: *Terima Uang Muka*).

### Tahap 7 — Pembelian barang oleh koperasi

1. Koperasi memesan ke dealer **atas nama koperasi** (PO / surat pemesanan).
2. Kasir **membayar langsung ke rekening dealer** setelah dicek pengurus (dua orang). Pembayaran tidak boleh ditransfer ke pemohon.
3. Dealer menerbitkan faktur/kuitansi atas nama koperasi. Untuk BPKB/STNK, data pemilik yang dipakai adalah data pembeli akhir (anggota), sebagaimana praktik leasing. Yang penting, **faktur pembayaran dari dealer ditujukan ke koperasi**.
4. Catat di Odoo: *Catat Pembelian Barang* (sudah ada) dengan nomor faktur, nomor rangka, dan nomor mesin di tab Barang & Dokumen.
5. BAST dealer → koperasi (halaman 1 BAST di Odoo).

Kalau terpaksa memakai **wakalah** (pemohon membeli sendiri): akad wakalah ditandatangani dulu, ada batas harga, dan pemohon wajib menyerahkan faktur asli. Ini sudah ada di Odoo.

### Tahap 8 — Akad, serah terima, dan pengikatan agunan

Pada hari yang sama, berurutan:
1. **Akad Murabahah** dibacakan dan dijelaskan. Centang "klausul dijelaskan" di Odoo. Ditandatangani pemohon (+ pasangan) dan pengurus. Saksi 2 orang.
2. **Surat Pengakuan Utang**.
3. **BAST koperasi → anggota**: motor diserahkan, dicek fisik dan nomor rangka/mesin, difoto.
4. **Agunan:** BPKB dicatat sebagai agunan berstatus *Rencana*. BPKB biasanya terbit 1–3 bulan kemudian. Saat BPKB tiba dari dealer, langsung disimpan koperasi (tidak diserahkan ke pemohon), lalu *Terima Agunan* dan cetak tanda terima. Petugas memantau sampai BPKB masuk.
5. **Fidusia** (lihat K4): perusahaan pembiayaan wajib mendaftarkan jaminan fidusia (UU 42/1999), yang memberi hak eksekusi bila macet. Untuk koperasi, ini pilihan dengan biaya notaris.
6. **Asuransi** (lihat K5): asuransi kendaraan syariah (minimal *total loss only*/kehilangan) dan asuransi jiwa pembiayaan, dengan premi dibayar pemohon atau dimasukkan ke harga.
7. Salinan akad dan jadwal angsuran diserahkan ke pemohon. Centang "salinan diserahkan".
8. Odoo: **Aktifkan** akad (jurnal akad dibuat otomatis).

**Checklist kelengkapan berkas** sebelum akad diaktifkan (diperiksa pengurus):
☐ KTP/KK pemohon (+ pasangan) ☐ foto pemohon dengan KTP ☐ bukti penghasilan ☐ iDeb SLIK ☐ hasil survei ☐ analisis + rekomendasi ☐ persetujuan pemutus ☐ wa'd ☐ bukti uang muka ☐ faktur dealer ☐ bukti transfer ke dealer ☐ akad + SPU + BAST bertanda tangan ☐ foto serah terima ☐ (menyusul) BPKB, sertifikat fidusia, polis asuransi

### Tahap 9 — Monitoring dan penagihan

| Hari | Tindakan | Oleh |
|---|---|---|
| H−3 | Pengingat jatuh tempo (WA/email) | Petugas (rencana: email otomatis, roadmap no. 8) |
| H+1 | Telepon/WA ramah, tanyakan kendala | Petugas |
| H+7 | **Surat Peringatan 1** | Petugas |
| H+30 | **SP 2** + kunjungan rumah | Petugas |
| H+60 | **SP 3**, pembicaraan solusi: penjadwalan kembali (sudah ada di Odoo) bila kesulitan nyata, atau penjualan agunan bila tidak ada itikad baik | Pengurus |
| > H+90 | Penyelesaian agunan sesuai akad (Pasal 4), dengan kelebihan hasil penjualan dikembalikan ke pemohon | Pengurus + Pengawas |

Etika penagihan (mengacu ke aturan perilaku OJK untuk lembaga jasa keuangan): penagihan hanya ke pemohon atau kontak darurat; hanya pukul 08.00–20.00; tanpa ancaman, kekerasan, atau mempermalukan di depan umum; tidak menagih lewat media sosial atau grup. Setiap kontak penagihan dicatat (tanggal, cara, hasil, janji bayar).

### Tahap 10 — Pelunasan

Pelunasan bisa normal atau dipercepat (rumus PUPMSJT, sudah ada). Setelah lunas, BPKB dikembalikan dengan tanda terima (*Kembalikan* agunan, sudah ada), dan fidusia di-roya bila didaftarkan. Riwayat bayar menjadi bahan penilaian *Character* untuk pengajuan berikutnya.

---

## 5. Pemetaan ke Odoo: yang sudah ada dan yang belum

| Tahap | Sudah ada | Belum ada (usulan fitur) |
|---|---|---|
| 1 Permohonan | Formulir website `/pengajuan` (membuat kontak + akad draft) | **Model Pengajuan** terpisah dari akad, dengan tahapan (Baru → Pra-skrining → KYC → Survei → Analisis → Keputusan → Jadi Akad / Ditolak / Batal) dan kanal (WA/website/kantor). Saat ini formulir publik langsung membuat akad draft dan kontak, sehingga rawan spam dan kontak ganda (tidak dicek per NIK) |
| 2 Pra-skrining | — | Pemeriksaan otomatis: usia, uang muka minimal, tenor maksimal per jenis barang, tunggakan aktif, plafon |
| 3 KYC | NIK, pekerjaan, foto KTP di kontak (dari `koperasi_website`) | **Profil KYC**: tempat/tgl lahir, status nikah + pasangan, nama ibu kandung, alamat domisili vs KTP, status rumah, lama tinggal, kontak darurat, hasil cek DTTOT/PEP + tanggal, tingkat risiko. **Checklist dokumen per jenis barang** dengan unggahan dan tanda "asli sudah dilihat oleh … tanggal …". Akses data KYC dibatasi grup Koperasi |
| 4 Survei | — | Form hasil survei + foto |
| 5 Analisis | ✅ Tab Analisis & Persetujuan, DSR, 5C, rekomendasi | Kolom ringkas hasil SLIK, riwayat internal otomatis (jumlah akad lama, pernah telat/restrukturisasi) |
| 6 Keputusan | ✅ Persetujuan, aturan benturan kepentingan, plafon pengurus, dasar persetujuan | **Matriks wewenang memutus** (nilai/risiko → 1 atau 2 pemutus), **analis ≠ pemutus**, cetak **Surat Penawaran/Persetujuan Prinsip**, surat penolakan |
| 6 Wa'd & DP | ✅ Cetak Wa'd, Terima Uang Muka | — |
| 7 Pembelian | ✅ Catat Pembelian, wakalah, BAST, rincian harga perolehan | Cetak **PO ke dealer**, aturan pembayaran hanya ke rekening pemasok |
| 8 Akad | ✅ Akad, SPU, BAST, checklist klausul, aktivasi + jurnal, agunan BPKB | **Checklist kelengkapan berkas wajib** sebelum Aktifkan, kolom fidusia (no. sertifikat, tanggal) dan asuransi (polis, perusahaan, masa) |
| 9 Penagihan | ✅ Daftar Tunggakan, kolektibilitas, restrukturisasi | **Log penagihan** (kontak, janji bayar), cetak SP1–SP3, pengingat otomatis (roadmap 8) |
| 10 Pelunasan | ✅ Pelunasan dipercepat, pengembalian agunan | — |

### Tahap A: Pengajuan & KYC (sudah ada di modul)

Menu **Koperasi → Murabahah → Pengajuan** (kanban per tahap). Cara pakai untuk petugas:

1. **Baru:** catat permohonan (kanal WA/website/kantor), kategori, barang, harga, uang muka, tenor, dan penghasilan yang diakui pemohon. Pilih kontak pemohon. Untuk permohonan dari website, tekan **Cari/Buat Kontak Pemohon**: kontak dicari berdasarkan NIK dan baru dibuat kalau tidak ada. Formulir website sendiri tidak pernah membuat kontak. Kotak **Pra-skrining** menampilkan catatan (DP minimal dan tenor maksimal per kategori, usia, tunggakan, DSR perkiraan, risiko tinggi, bukan anggota). Kalau ada catatan, pengajuan hanya bisa dilanjutkan dengan *Dasar Pengecualian*. Tekan **Lolos Pra-skrining → KYC**.
2. **Verifikasi KYC:** isi tab **Identitas & KYC** di kontak pemohon (NIK 16 digit dan unik, tanggal lahir, ibu kandung, status perkawinan dan pasangan, pekerjaan, kontak darurat, cek DTTOT/DPPSPM, PEP, tingkat risiko). Di tab **Dokumen**, unggah file, centang *Asli Sudah Dicek* lalu *Terverifikasi*, atau *Tidak Berlaku* dengan alasan. Tombol **Pesan WA Permintaan Dokumen** menyalin daftar dokumen yang belum ada untuk dikirim ke pemohon. Centang 4 konfirmasi (HP, kontak darurat, alamat, pekerjaan). **KYC Selesai → Survei** menolak bila masih ada kekurangan atau nama ditemukan di DTTOT.
3. **Survei:** pilih kunjungan atau telepon + foto. Survei hanya boleh dilewati untuk pemohon berisiko rendah, dengan alasan. Kesimpulan *Tidak Sesuai* = tolak. **Survei Selesai → Buat Akad (Analisis)** membuat akad draft yang sudah terisi.
4. **Analisis & Keputusan** di akad (sama seperti sebelumnya: DSR, rekomendasi, Setujui). Status pengajuan mengikuti akad (Disetujui/Batal).

Aturan baru di persetujuan akad:
- Akad baru **wajib berasal dari Pengajuan** yang lolos KYC dan survei (bisa dimatikan di Pengaturan → Pengajuan & KYC). Akad saldo awal tidak terpengaruh.
- Risiko KYC **tinggi** mewajibkan Dasar Persetujuan.
- Pemohon bukan anggota (K1): **wajib penjamin anggota aktif** (kafalah). Penjamin tidak boleh pemohon sendiri, harus anggota aktif, dan tidak sedang menunggak. Penjamin tidak boleh ikut menyetujui akad yang ia jamin. Setelah penjamin dipilih, KTP penjamin (sebelum keputusan) dan Surat Penjaminan bertanda tangan (sebelum akad) masuk checklist. Cetak lewat akad: **Cetak → Surat Penjaminan (Kafalah)**, ditandatangani koperasi, anggota, dan penjamin.

Data awal yang bisa diubah Pengurus/Akuntan di Konfigurasi:
- **Kategori Pembiayaan:** motor DP 20% / 24 bulan / margin 25%, mobil, elektronik & HP, rumah tangga, barang usaha, lainnya (angka K3 masih usulan).
- **Checklist Dokumen:** 22 jenis dokumen dalam 3 tahap. Dokumen pasangan muncul hanya bila pemohon menikah. BPKB, STNK, polis, dan fidusia muncul hanya untuk kendaraan.

Perlindungan data:
- Data KYC (termasuk NIK, foto KTP, pekerjaan) hanya bisa dibaca grup Koperasi.
- Formulir website: wajib centang persetujuan pemakaian data, ada perangkap bot, unggahan dibatasi JPG/PNG/PDF maks. 5 MB.
- Halaman "berhasil" hanya bisa dibuka oleh browser pengirim. Pesan "NIK sudah terdaftar" di `/daftar` tidak menyebut nama pemilik NIK.

### Usulan urutan pembangunan

1. ✅ **Tahap A — Pengajuan & KYC** (sudah ada): model Pengajuan dengan tahapan, profil KYC, checklist dokumen per jenis barang (motor dulu), pra-skrining otomatis, formulir website diubah supaya membuat **Pengajuan** (bukan akad) dengan pencocokan NIK, dan pembatasan akses data pribadi. Tombol "Buat Akad" dari pengajuan yang disetujui.
2. **Tahap B — Keputusan**: matriks wewenang, analis ≠ pemutus, form survei, Surat Penawaran, surat penolakan, checklist berkas sebelum aktivasi, fidusia/asuransi.
3. **Tahap C — Penagihan**: log penagihan, SP1–SP3, pengingat otomatis.


---

## 6. Ringkasan berkas untuk Budi (motor)

| Saat | Berkas |
|---|---|
| Permohonan | Penawaran OTR dealer, uang muka & tenor yang diinginkan |
| KYC | KTP, KK, KTP pasangan (jika menikah), foto dengan KTP, kontak darurat |
| Kemampuan bayar | Slip gaji/mutasi 3 bulan, iDeb SLIK |
| Persetujuan | Analisis + rekomendasi petugas, keputusan pengurus, Surat Penawaran, Wa'd, bukti uang muka |
| Pembelian | PO, faktur dealer atas nama koperasi, bukti transfer ke dealer |
| Akad | Akad, SPU, BAST, foto serah terima, salinan untuk Budi |
| Menyusul | BPKB (disimpan koperasi), polis asuransi, sertifikat fidusia (jika dipakai) |

Contoh hitungan (ilustrasi, bukan penawaran): motor OTR Rp 25.000.000, uang muka 20% = Rp 5.000.000, margin motor 25% × (25 jt − 5 jt) = Rp 5.000.000, harga jual Rp 30.000.000, sisa dibiayai Rp 25.000.000, tenor 24 bulan → angsuran ≈ **Rp 1.041.667/bulan**. Dengan batas DSR 40%, penghasilan bersih minimal ≈ Rp 2,6 jt/bulan (bila tidak ada cicilan lain).

---

## 7. Keputusan yang perlu ditetapkan pengurus

| No | Pertanyaan | Usulan |
|---|---|---|
| ~~K1~~ | Non-anggota boleh dibiayai? | **Contoh keputusan: boleh, asalkan ada penjamin dari anggota aktif (kafalah, Fatwa DSN-MUI 11/2000).** Catatan: Permenkop UKM 8/2023 pasal 23(3) menyebut pinjaman kepada anggota dan/atau koperasi lain. Tetap tanyakan ke Dinas Koperasi sesuai jenis izin koperasi, dan pertimbangkan menawarkan keanggotaan kepada pelanggan tetap. |
| K2 | Batas wewenang memutus 1 vs 2 pengurus | Rp 15 jt |
| K3 | Uang muka minimal dan tenor maksimal per jenis barang | Motor: DP ≥ 20%, tenor ≤ 24 bln. Elektronik/HP: DP ≥ 10–25%, tenor ≤ 12 bln |
| K4 | Fidusia untuk kendaraan? | Wajib bila nilai dibiayai > Rp 20 jt, di bawahnya cukup tahan BPKB + surat kuasa jual |
| K5 | Asuransi kendaraan & jiwa wajib? | Kendaraan: wajib minimal kehilangan (TLO). Jiwa: disarankan |
| K6 | SLIK wajib? | Wajib untuk pemohon baru dan nilai > Rp 10 jt |
| K7 | Siapa kasir/bendahara (pembayar ke dealer)? | Bukan orang yang sama dengan pemutus |
| K8 | Batas usia, plafon per pemohon | 21–60 tahun, plafon mengikuti modal koperasi (mis. ≤ 30% kas tersedia per pemohon) |

---

## 8. Acuan

- Fatwa DSN-MUI 04/2000 (Murabahah), 13/2000 (Uang Muka), 10/2000 (Wakalah), 46/2005 (Potongan Tagihan), 48/2005 (Penjadwalan Kembali), 153/2022 (Pelunasan Dipercepat)
- Pedoman Produk Murabahah OJK (ojk.go.id), terutama bagian manajemen risiko dan proses pembiayaan
- PSAK 102 (PSAK 402) Akuntansi Murabahah
- UU 42/1999 tentang Jaminan Fidusia; UU 27/2022 tentang Pelindungan Data Pribadi
- Peraturan Kemenkop UKM tentang usaha simpan pinjam & pembiayaan syariah oleh koperasi dan penerapan prinsip mengenali pengguna jasa (APU-PPT). **Nomor dan pasal yang berlaku perlu dicek** sebelum SOP disahkan.
