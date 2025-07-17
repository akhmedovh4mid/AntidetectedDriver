window.loadedResources = []; // Теперь доступна везде, включая консоль
// Далее ваш код:
const initialResources = performance.getEntriesByType('resource');
initialResources.forEach(resource => {
    window.loadedResources.push({ // Используем window.loadedResources
        name: resource.name,
        type: resource.initiatorType,
        duration: resource.duration,
        size: resource.transferSize,
        startTime: resource.startTime
    });
});

const observer = new PerformanceObserver((list) => {
    list.getEntries().forEach(entry => {
        window.loadedResources.push({ // Записываем в глобальную переменную
            name: entry.name,
            type: entry.initiatorType,
            duration: entry.duration,
            size: entry.transferSize,
            startTime: entry.startTime
        });
    });
});
observer.observe({ entryTypes: ['resource'] });
