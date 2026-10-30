import base64
import urllib.parse
from odoo import http, fields, _
from odoo.http import request


class KoperasiWebsiteController(http.Controller):

    def _get_wa_number(self):
        icp = request.env['ir.config_parameter'].sudo()
        if hasattr(icp, 'get_str'):
            wa = icp.get_str('koperasi_website.wa_number', '')
        elif hasattr(icp, 'get_param'):
            wa = icp.get_param('koperasi_website.wa_number', '')
        else:
            rec = icp.search([('key', '=', 'koperasi_website.wa_number')], limit=1)
            wa = rec.value if rec else ''
        return (wa or '').strip().replace('+', '').replace('-', '').replace(' ', '')

    @staticmethod
    def _mask_nik(nik):
        return (nik[:4] + '*' * 8 + nik[-4:]) if nik and len(nik) == 16 else '-'

    @staticmethod
    def _check_upload(content, images_only=False):
        """Error message for an unacceptable public upload, else None."""
        magics = {b'\xff\xd8\xff': 'JPG', b'\x89PNG': 'PNG'}
        if not images_only:
            magics[b'%PDF'] = 'PDF'
        if len(content) > 5 * 1024 * 1024:
            return "Ukuran file maksimal 5 MB."
        if not any(content.startswith(m) for m in magics):
            return "File harus berupa %s." % ", ".join(magics.values())
        return None

    @staticmethod
    def _parse_rp(raw):
        digits = ''.join(ch for ch in (raw or '') if ch.isdigit())
        return float(digits) if digits else 0.0

    def _get_margin_pct(self):
        icp = request.env['ir.config_parameter'].sudo()
        if hasattr(icp, 'get_float'):
            return icp.get_float('koperasi_website.simulasi_margin_pct', 20.0)
        elif hasattr(icp, 'get_param'):
            val = icp.get_param('koperasi_website.simulasi_margin_pct', '20.0')
            try:
                return float(val)
            except (ValueError, TypeError):
                return 20.0
        else:
            rec = icp.search([('key', '=', 'koperasi_website.simulasi_margin_pct')], limit=1)
            try:
                return float(rec.value) if rec and rec.value else 20.0
            except (ValueError, TypeError):
                return 20.0

    @http.route(['/', '/home'], type='http', auth='public', website=True)
    def index(self, **kw):
        """Halaman Utama (Landing Page)"""
        wa_number = self._get_wa_number()
        margin_pct = self._get_margin_pct()

        # Statistik dinamis koperasi
        partner_obj = request.env['res.partner'].sudo()
        akad_obj = request.env['koperasi.murabahah.akad'].sudo()

        total_members = partner_obj.search_count([('koperasi_status', '=', 'anggota')])
        # Fallback angka representatif jika database masih baru
        if total_members < 10:
            total_members = 350 + total_members

        total_akad = akad_obj.search_count([('state', 'in', ['aktif', 'lunas'])])
        if total_akad < 5:
            total_akad = 85 + total_akad

        values = {
            'wa_number': wa_number,
            'margin_pct': margin_pct,
            'total_members': total_members,
            'total_akad': total_akad,
        }
        return request.render('koperasi_website.homepage', values)

    @http.route('/daftar', type='http', auth='public', website=True, methods=['GET', 'POST'], csrf=True)
    def daftar_anggota(self, **post):
        """Formulir Pendaftaran Anggota Koperasi"""
        wa_number = self._get_wa_number()
        errors = []

        if request.httprequest.method == 'POST':
            name = (post.get('name') or '').strip()
            nik = (post.get('nik') or '').strip()
            phone = (post.get('phone') or '').strip()
            email = (post.get('email') or '').strip()
            street = (post.get('street') or '').strip()
            city = (post.get('city') or '').strip()
            pekerjaan = (post.get('pekerjaan') or '').strip()
            ktp_file = request.httprequest.files.get('ktp_file')

            # Validasi form
            if not name:
                errors.append("Nama Lengkap wajib diisi.")
            if not nik:
                errors.append("NIK / No. KTP wajib diisi.")
            elif len(nik) < 16 or not nik.isdigit():
                errors.append("NIK harus berupa 16 digit angka.")
            if not phone:
                errors.append("Nomor WhatsApp wajib diisi.")

            # Cek apakah NIK sudah pernah terdaftar
            partner_obj = request.env['res.partner'].sudo()
            existing_nik = partner_obj.search([('koperasi_nik', '=', nik)], limit=1)
            if existing_nik:
                # Do not reveal whose NIK it is (personal data)
                errors.append("NIK ini sudah terdaftar di koperasi. Silakan hubungi pengurus lewat WhatsApp.")
            ktp_content = None
            if ktp_file and ktp_file.filename:
                ktp_content = ktp_file.read()
                upload_error = self._check_upload(ktp_content, images_only=True)
                if upload_error:
                    errors.append(upload_error)
            if (post.get('website_url') or '').strip():
                errors.append("Permintaan tidak dapat diproses.")

            if not errors:
                vals = {
                    'name': name,
                    'koperasi_nik': nik,
                    'phone': phone,
                    'email': email or False,
                    'street': street or False,
                    'city': city or False,
                    'koperasi_pekerjaan': pekerjaan or False,
                    'koperasi_status': 'non_anggota',
                    'koperasi_is_applicant': True,
                    'koperasi_application_date': fields.Datetime.now(),
                    'comment': f"Pendaftaran via website pada {fields.Date.today()}.",
                }
                if 'mobile' in partner_obj._fields:
                    vals['mobile'] = phone

                if ktp_content:
                    vals['koperasi_ktp_image'] = base64.b64encode(ktp_content).decode()

                new_partner = partner_obj.create(vals)
                request.session['koperasi_daftar_id'] = new_partner.id
                return request.redirect('/daftar/sukses')

        return request.render('koperasi_website.form_daftar', {
            'wa_number': wa_number,
            'errors': errors,
            'post': post,
        })

    @http.route('/daftar/sukses', type='http', auth='public', website=True)
    def daftar_sukses(self, **kw):
        """Halaman Konfirmasi Berhasil Daftar Anggota (hanya untuk sesi browser yang baru mendaftar)"""
        partner_id = request.session.get('koperasi_daftar_id')
        partner = request.env['res.partner'].sudo().browse(int(partner_id)) if partner_id else None
        if not partner or not partner.exists():
            return request.redirect('/')

        partner_sudo = partner.sudo()
        user_phone = partner_sudo.phone or (hasattr(partner_sudo, 'mobile') and partner_sudo.mobile) or '-'
        wa_number = self._get_wa_number()
        pesan_wa = (
            f"Assalamu'alaikum Admin {request.env.company.name}, saya sudah mendaftar menjadi calon anggota "
            f"melalui website.\n"
            f"Nama: {partner_sudo.name}\n"
            f"NIK: {self._mask_nik(partner_sudo.koperasi_nik)}\n"
            f"No HP: {user_phone}\n"
            f"Mohon informasi langkah verifikasi selanjutnya. Terima kasih."
        )
        wa_url = f"https://wa.me/{wa_number}?text={urllib.parse.quote(pesan_wa)}"

        return request.render('koperasi_website.daftar_sukses', {
            'partner': partner_sudo,
            'partner_name': partner_sudo.name,
            'partner_nik': self._mask_nik(partner_sudo.koperasi_nik),
            'partner_phone': user_phone,
            'wa_url': wa_url,
            'wa_number': wa_number,
        })

    @http.route('/pengajuan', type='http', auth='public', website=True, methods=['GET', 'POST'], csrf=True)
    def pengajuan_pembiayaan(self, **post):
        """Formulir Pengajuan Pembiayaan Murabahah Online -> koperasi.murabahah.pengajuan (SOP tahap 1)"""
        wa_number = self._get_wa_number()
        margin_pct = self._get_margin_pct()
        kategori_list = request.env['koperasi.pembiayaan.kategori'].sudo().search([])
        errors = []

        if request.httprequest.method == 'POST':
            name = (post.get('name') or '').strip()
            nik = (post.get('nik') or '').strip()
            phone = (post.get('phone') or '').strip()
            email = (post.get('email') or '').strip()
            product_desc = (post.get('product_desc') or '').strip()
            cost_price = self._parse_rp(post.get('cost_price'))
            down_payment = self._parse_rp(post.get('down_payment'))
            monthly_income = self._parse_rp(post.get('monthly_income'))
            try:
                tenor = int(post.get('tenor') or 12)
            except ValueError:
                tenor = 12
            try:
                kategori_id = int(post.get('kategori_id') or 0)
            except ValueError:
                kategori_id = 0

            if not name:
                errors.append("Nama Lengkap wajib diisi.")
            if not phone:
                errors.append("Nomor WhatsApp wajib diisi.")
            if nik and (len(nik) != 16 or not nik.isdigit()):
                errors.append("NIK harus 16 digit angka.")
            if kategori_id not in kategori_list.ids:
                errors.append("Pilih kategori barang.")
            if not product_desc:
                errors.append("Deskripsi barang / kebutuhan yang diajukan wajib diisi.")
            if cost_price <= 0:
                errors.append("Estimasi harga / nilai pengajuan harus lebih dari nol.")
            if tenor < 1:
                errors.append("Tenor minimal 1 bulan.")
            if down_payment >= cost_price > 0:
                errors.append("Uang muka tidak boleh melebihi atau sama dengan harga barang.")
            if not post.get('consent'):
                errors.append("Centang persetujuan penggunaan data pribadi.")
            if (post.get('website_url') or '').strip():
                errors.append("Permintaan tidak dapat diproses.")

            files = {}
            for field_name, code in (('ktp_file', 'ktp'), ('penawaran_file', 'penawaran')):
                upload = request.httprequest.files.get(field_name)
                if upload and upload.filename:
                    content = upload.read()
                    upload_error = self._check_upload(content)
                    if upload_error:
                        errors.append("%s: %s" % (upload.filename, upload_error))
                    else:
                        files[code] = (upload.filename, content)

            if not errors:
                pengajuan = request.env['koperasi.murabahah.pengajuan'].sudo()._website_submit({
                    'name': name,
                    'nik': nik,
                    'phone': phone,
                    'email': email,
                    'kategori_id': kategori_id,
                    'product_desc': product_desc,
                    'supplier_name': (post.get('supplier_name') or '').strip(),
                    'estimated_price': cost_price,
                    'down_payment': down_payment,
                    'tenor': tenor,
                    'income_source': (post.get('income_source') or '').strip(),
                    'monthly_income': monthly_income,
                    'note': (post.get('note') or '').strip(),
                }, files)
                request.session['koperasi_pengajuan'] = [pengajuan.id, pengajuan.access_token]
                return request.redirect('/pengajuan/sukses')

        # Pre-fill jika dilempar dari kalkulator homepage
        default_cost = post.get('cost_price') or post.get('plafon') or '10000000'
        default_tenor = post.get('tenor') or '12'
        default_dp = post.get('dp') or post.get('down_payment') or '0'

        return request.render('koperasi_website.form_pengajuan', {
            'wa_number': wa_number,
            'margin_pct': margin_pct,
            'errors': errors,
            'post': post,
            'kategori_list': kategori_list,
            'default_cost': default_cost,
            'default_tenor': default_tenor,
            'default_dp': default_dp,
        })

    @http.route('/pengajuan/sukses', type='http', auth='public', website=True)
    def pengajuan_sukses(self, **kw):
        """Halaman Konfirmasi Berhasil Mengajukan Pembiayaan (hanya untuk sesi browser pengirim)"""
        rec_id, token = (request.session.get('koperasi_pengajuan') or [None, None])[:2]
        pengajuan = request.env['koperasi.murabahah.pengajuan'].sudo()._website_get(rec_id, token)
        if not pengajuan:
            return request.redirect('/')

        info = pengajuan._website_summary()
        wa_number = self._get_wa_number()
        pesan_wa = (
            f"Assalamu'alaikum Admin {request.env.company.name}, saya sudah mengirimkan pengajuan pembiayaan "
            f"melalui website.\n"
            f"No. Pengajuan: {info['name']}\n"
            f"Nama Pemohon: {info['applicant']}\n"
            f"Barang/Kebutuhan: {info['product_desc']}\n"
            f"Perkiraan Harga: {info['estimated_price']}\n"
            f"Tenor: {info['tenor']} Bulan\n"
            f"Mohon informasi dokumen yang perlu saya siapkan. Terima kasih."
        )
        wa_url = f"https://wa.me/{wa_number}?text={urllib.parse.quote(pesan_wa)}"

        return request.render('koperasi_website.pengajuan_sukses', {
            'akad_name': info['name'],
            'applicant_name': info['applicant'],
            'product_desc': info['product_desc'],
            'cost_price_formatted': info['estimated_price'].replace('Rp ', '').replace('Rp', ''),
            'tenor': info['tenor'],
            'wa_url': wa_url,
            'wa_number': wa_number,
        })

    @http.route('/simulasi', type='http', auth='public', website=True)
    def simulasi_page(self, **kw):
        """Halaman Mandiri Kalkulator Simulasi Pembiayaan Syariah"""
        wa_number = self._get_wa_number()
        margin_pct = self._get_margin_pct()
        return request.render('koperasi_website.simulasi_page', {
            'wa_number': wa_number,
            'margin_pct': margin_pct,
        })
