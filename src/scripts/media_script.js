(async () => {
    // Загружаем html2canvas и jspdf динамически
    await loadScript('https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js');
    await loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js');
    await loadScript('https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js');

    // 1. Скриншот (ваш код с оптимизацией)
    console.log('Делаем скриншот...');
    const canvas = await html2canvas(document.body, {
        scale: 1,
        logging: false,
        useCORS: true,
        allowTaint: true,
    });

    const screenshotBlob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png', 0.9));
    window.screenshotBytes = new Uint8Array(await screenshotBlob.arrayBuffer());
    console.log('Скриншот сохранён в window.screenshotBytes', window.screenshotBytes);

    console.log('Начало генерации PDF...');
    // const options = {
    //     margin: 10,
    //     filename: 'full_site.pdf',
    //     image: { type: 'jpeg', quality: 0.98 },
    //     html2canvas: { scale: 2, logging: true, useCORS: true },
    //     jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
    // };
    const options = {
        margin: [0, 0, 0, 0],
        filename: 'custom_filename.pdf',
        enableLinks: true,
        image: {
            type: 'jpeg',
            quality: 0.95,
            dpi: 300,
        },
        html2canvas: {
            scale: 2,
            logging: false,
            useCORS: true,
            allowTaint: false,
            scrollX: 0,
            scrollY: 0,
            backgroundColor: '#FFFFFF',
            ignoreElements: (element) => element.classList.contains('no-print'),
        },
        jsPDF: {
            unit: 'mm',
            format: 'a4',
            orientation: 'landscape',
            compress: true,
            hotfixes: ['px_scaling'],
        },
        pagebreak: {
            mode: 'avoid-all',
            before: '.page-break-before',
            after: '.page-break-after',
        },
    };

    const pdf = await html2pdf().set(options).from(document.documentElement).outputPdf('arraybuffer');

    window.pdfBytes = new Uint8Array(pdf);
    console.log('PDF сгенерирован и сохранён в window.pdfBytes');

    // Функция для загрузки скриптов
    function loadScript(src) {
        return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = src;
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
        });
    }
})();
