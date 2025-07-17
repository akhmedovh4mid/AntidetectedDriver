function getAllPageResources() {
  const resources = [];

  // Функция для добавления ресурса в массив
  function addResource(url, type) {
    if (!url || resources.some(res => res.url === url)) return;
    resources.push({ url, type });
  }

  // 1. Собираем все теги <link> (CSS, favicon и т.д.)
  document.querySelectorAll('link[href]').forEach(link => {
    const type = link.rel.includes('stylesheet') ? 'css' : link.rel || 'link';
    addResource(link.href, type);
  });

  // 2. Собираем все теги <script>
  document.querySelectorAll('script[src]').forEach(script => {
    addResource(script.src, 'js');
  });

  // 3. Собираем все изображения
  document.querySelectorAll('img[src], source[src], image[href]').forEach(img => {
    const url = img.src || img.href;
    const type = 'image';
    addResource(url, type);
  });

  // 4. Собираем все видео
  document.querySelectorAll('video source[src], video[poster]').forEach(video => {
    if (video.src) {
      addResource(video.src, 'video');
    }
    if (video.poster) {
      addResource(video.poster, 'video_poster');
    }
  });

  // 5. Собираем все аудио
  document.querySelectorAll('audio source[src]').forEach(audio => {
    addResource(audio.src, 'audio');
  });

  // 6. Собираем фоновые изображения из CSS
  document.querySelectorAll('*').forEach(element => {
    const style = window.getComputedStyle(element);
    const bgImage = style.backgroundImage.match(/url\(["']?(.*?)["']?\)/);
    if (bgImage && bgImage[1]) {
      addResource(bgImage[1], 'css_background_image');
    }
  });

  // 7. Собираем все iframe и embed
  document.querySelectorAll('iframe[src], embed[src]').forEach(frame => {
    addResource(frame.src, 'embedded_content');
  });

  // 8. Собираем объекты (object data)
  document.querySelectorAll('object[data]').forEach(obj => {
    addResource(obj.data, 'object_data');
  });

  // 9. Собираем ссылки на шрифты (@font-face)
  Array.from(document.styleSheets).forEach(sheet => {
    try {
      Array.from(sheet.cssRules || []).forEach(rule => {
        if (rule instanceof CSSFontFaceRule) {
          const srcMatch = rule.style.src.match(/url\(["']?(.*?)["']?\)/);
          if (srcMatch && srcMatch[1]) {
            addResource(srcMatch[1], 'font');
          }
        }
      });
    } catch (e) {
      // Игнорируем ошибки CORS
    }
  });

  return resources;
}

return getAllPageResources()
