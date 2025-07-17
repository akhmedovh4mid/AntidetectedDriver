from src.models.proxy_unit import ProxyUnit


class ProxyManager:
    count = 0
    regions = []
    proxies = {}

    def add_proxy(self, country_name: str, value: ProxyUnit) -> None:
        self.proxies[country_name] = value
        self.regions.append(country_name)
        self.count += 1

    def get_proxy(self, country_name: str) -> ProxyUnit:
        return self.proxies.get(country_name)
