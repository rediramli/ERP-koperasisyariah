/**
 * Koperasi Syariah - Interactive Financing Simulation Calculator
 */
(function () {
    'use strict';

    function formatRupiah(number) {
        return new Intl.NumberFormat('id-ID', {
            style: 'currency',
            currency: 'IDR',
            maximumFractionDigits: 0,
        }).format(Math.round(number));
    }

    function parseRupiah(str) {
        if (!str) return 0;
        return parseFloat(String(str).replace(/[^0-9]/g, '')) || 0;
    }

    function initCalculator() {
        var calcElement = document.getElementById('ksbk-calc-widget');
        if (!calcElement) return;

        var sliderPlafon = document.getElementById('calc-plafon-slider');
        var inputPlafon = document.getElementById('calc-plafon-input');
        var selectTenor = document.getElementById('calc-tenor-select');
        var inputDp = document.getElementById('calc-dp-input');

        var displayAngsuran = document.getElementById('calc-result-angsuran');
        var displayPokok = document.getElementById('calc-result-pokok');
        var displayMargin = document.getElementById('calc-result-margin');
        var displayTotal = document.getElementById('calc-result-total');
        var btnLanjut = document.getElementById('calc-btn-ajukan');

        var defaultMarginPct = parseFloat(calcElement.getAttribute('data-margin-pct')) || 20.0;

        function hitung() {
            var plafon = parseFloat(sliderPlafon ? sliderPlafon.value : inputPlafon.value) || 0;
            var tenor = parseInt(selectTenor ? selectTenor.value : 12, 10) || 12;
            var dp = parseRupiah(inputDp ? inputDp.value : 0);

            if (dp >= plafon) {
                dp = 0;
                if (inputDp) inputDp.value = "0";
            }

            var pokok = plafon - dp;
            // Rumus Murabahah Syariah: margin flat proporsional per tahun
            var marginTahun = defaultMarginPct / 100.0;
            var totalMargin = Math.round(pokok * marginTahun * (tenor / 12.0));
            var totalPiutang = pokok + totalMargin;
            var cicilanPerBulan = Math.round(totalPiutang / tenor);
            var cicilanPokok = Math.round(pokok / tenor);
            var cicilanMargin = cicilanPerBulan - cicilanPokok;

            if (displayAngsuran) displayAngsuran.textContent = formatRupiah(cicilanPerBulan);
            if (displayPokok) displayPokok.textContent = formatRupiah(cicilanPokok);
            if (displayMargin) displayMargin.textContent = formatRupiah(cicilanMargin);
            if (displayTotal) displayTotal.textContent = formatRupiah(totalPiutang);

            if (btnLanjut) {
                btnLanjut.href = '/pengajuan?cost_price=' + plafon + '&tenor=' + tenor + '&dp=' + dp;
            }
        }

        if (sliderPlafon && inputPlafon) {
            sliderPlafon.addEventListener('input', function () {
                inputPlafon.value = formatRupiah(sliderPlafon.value);
                hitung();
            });

            inputPlafon.addEventListener('change', function () {
                var val = parseRupiah(inputPlafon.value);
                if (val < 1000000) val = 1000000;
                if (val > 100000000) val = 100000000;
                sliderPlafon.value = val;
                inputPlafon.value = formatRupiah(val);
                hitung();
            });
        }

        if (selectTenor) {
            selectTenor.addEventListener('change', hitung);
        }

        if (inputDp) {
            inputDp.addEventListener('input', function () {
                var raw = parseRupiah(inputDp.value);
                inputDp.value = formatRupiah(raw);
                hitung();
            });
        }

        // Jalankan kalkulasi pertama kali
        if (sliderPlafon && inputPlafon) {
            inputPlafon.value = formatRupiah(sliderPlafon.value);
        }
        hitung();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCalculator);
    } else {
        initCalculator();
    }
})();
