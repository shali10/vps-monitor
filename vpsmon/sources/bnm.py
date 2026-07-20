from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
import requests

from vpsmon.models import Money, VpsOffer
from vpsmon.rules.parsing import parse_ram_gb, parse_usd_year
from vpsmon.sources import register


def _clean(value: object) -> str:
    return str(value or '').strip()


def _offer_id(url: str, fallback: str) -> str:
    qs = parse_qs(urlparse(url).query)
    package = (qs.get('package') or [''])[0]
    plan = (qs.get('plan') or [''])[0]
    if package or plan:
        return f'{package}:{plan}'
    return fallback


def _stock(row) -> int | None:
    for cell in row.find_all('td'):
        text = cell.get_text(' ', strip=True)
        if text.isdigit():
            # the second numeric-looking short field is ports, not stock; BNM only exposes sold-out flag.
            continue
    return None


def _price(raw: str) -> Money | None:
    raw = _clean(raw)
    if not raw:
        return None
    # bnm.uw.to displays bare RMB price. SHLII create page plans are monthly, so normalize for yearly USD sorting.
    normalized = raw if any(unit in raw for unit in ('月', '年', '季')) else f'{raw}/月'
    usd_year = parse_usd_year(normalized)
    return Money(raw=normalized, usd_year=usd_year) if usd_year is not None else None


class BnmSource:
    SOURCE_NAME = "bnm"
    def __init__(self, config: dict):
        self.url = config.get('url') or config.get('api_url') or 'https://bnm.uw.to/'
        self.timeout = int(config.get('timeout', 20))
        self.user_agent = config.get('user_agent', 'Mozilla/5.0')

    def fetch(self) -> list[VpsOffer]:
        resp = requests.get(self.url, timeout=self.timeout, headers={'User-Agent': self.user_agent})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, 'html.parser')
        offers: list[VpsOffer] = []
        for idx, tr in enumerate(soup.select('#stockTable tbody tr'), 1):
            cells = [td.get_text(' ', strip=True) for td in tr.find_all('td')]
            if len(cells) < 12:
                continue
            source, row_id, package, plan, ram, disk, traffic, bandwidth, network, ports, price_raw, _action = cells[:12]
            link = tr.find('a')
            href = link.get('href', '') if link else ''
            offer_id = _offer_id(href, f'{row_id}:{package}:{plan}')
            available = tr.get('data-sold-out') != 'true' and 'sold-out' not in (tr.get('class') or [])
            price = _price(price_raw)
            provider = f'SHLII-{source}' if source else 'SHLII'
            route_parts = [network]
            search = tr.get('data-search') or ''
            if search and search != '—':
                route_parts.append(search)
            offers.append(VpsOffer(
                source='bnm',
                offer_id=offer_id,
                title=plan or package or f'BNM-{idx}',
                provider=provider,
                location=package,
                cpu_cores=1.0,
                ram_gb=parse_ram_gb(ram),
                disk='',
                bandwidth=bandwidth,
                traffic=traffic,
                route=' / '.join(p for p in route_parts if p),
                price=price,
                available=available,
                stock=None,
                url=href or self.url,
                raw={
                    'source': source,
                    'id': row_id,
                    'package': package,
                    'plan': plan,
                    'ram': ram,
                    'traffic': traffic,
                    'bandwidth': bandwidth,
                    'network': network,
                    'ports': ports,
                    'price': price_raw,
                    'url': href,
                },
            ))
        return offers


register("bnm", BnmSource)
