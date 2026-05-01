import re
from typing import Optional, Dict, List


class BaseParser:
    """Базовый класс с общими утилитами для всех парсеров"""

    # Карта флагов -> SIM тип
    FLAG_MAP = {
        '🇧🇭': 'esim', '🇨🇦': 'esim', '🇬🇺': 'esim', '🇯🇵': 'esim',
        '🇰🇼': 'esim', '🇲🇽': 'esim', '🇴🇲': 'esim', '🇶🇦': 'esim',
        '🇸🇦': 'esim', '🇦🇪': 'esim', '🇺🇸': 'esim', '🇻🇮': 'esim',
        '🇪🇺': 'sim+esim', '🇮🇳': 'sim+esim', '🇻🇳': 'sim+esim',
        '🇦🇺': 'sim+esim', '🇳🇿': 'sim+esim', '🇰🇷': 'sim+esim',
        '🇸🇬': 'sim+esim', '🇭🇰': 'sim+esim', '🇨🇳': '2sim',
        '🇷🇺': 'sim+esim', '🇰🇿': 'sim+esim', '🇮🇩': 'sim+esim',
        '🇹🇭': 'sim+esim', '🇵🇭': 'sim+esim', '🇲🇾': 'sim+esim',
        '🇵🇦': 'sim+esim', '🇨🇱': 'sim+esim', '🇿🇦': 'sim+esim',
        '🇬🇧': 'sim+esim', '🇮🇱': 'sim+esim', '🇹🇼': 'sim+esim',
        '🇹🇷': 'sim+esim', '🇧🇷': 'sim+esim', '🇮🇹': 'sim+esim',
        '🇩🇪': 'sim+esim', '🇫🇷': 'sim+esim', '🇪🇸': 'sim+esim',
        '🇵🇹': 'sim+esim', '🇵🇱': 'sim+esim', '🇸🇪': 'sim+esim',
        '🇳🇴': 'sim+esim', '🇩🇰': 'sim+esim', '🇫🇮': 'sim+esim',
        '🇵🇾': 'sim+esim'
    }

    FLAGS_REGEX = '(' + '|'.join(FLAG_MAP.keys()) + ')'

    @staticmethod
    def clean_text(text: str) -> str:
        return text.strip()

    @staticmethod
    def extract_price(text: str) -> Optional[float]:
        """Извлекает цену из строки"""
        # Ищем цену в конце строки или после флага - число с пробелами/точками
        # Паттерн: цифры с разделителями, за которыми следует RUB/₽/руб или конец строки
        match = re.search(r'(\d[\d\s\.]*)\s*(?:₽|руб|rub|RUB)?\s*$', text.strip(), re.IGNORECASE)
        if match:
            try:
                price_str = match.group(1).replace(' ', '').replace('.', '').strip()
                if price_str and price_str.isdigit():
                    return float(price_str)
            except:
                pass

        # Второй паттерн - просто большое число в строке
        match = re.search(r'(\d{5,})', text)
        if match:
            try:
                return float(match.group(1))
            except:
                pass

        return None

    @staticmethod
    def extract_flag(text: str) -> Optional[str]:
        """Извлекает флаг из строки"""
        match = re.search(BaseParser.FLAGS_REGEX, text)
        return match.group(1) if match else None

    @staticmethod
    def get_sim_type(flag: Optional[str], category_id: str) -> Optional[str]:
        """Возвращает тип SIM или None, если категория не поддерживает SIM"""
        if not flag:
            return None
        if category_id in ['laptops', 'tablets', 'consoles', 'accessories']:
            return None
        return BaseParser.FLAG_MAP.get(flag)

    def parse_block(self, header: str, lines: List[str]) -> List[Dict]:
        """Основной метод парсинга блока. Переопределяется в наследниках."""
        raise NotImplementedError

    def _is_skip_line(self, line: str) -> bool:
        """Проверка, нужно ли пропускать строку"""
        if len(line.strip()) < 5:
            return True
        skip_keywords = ['асис', 'asis', 'refurbished', 'б/у', 'обменки', 'обмена', 'trade in']
        if any(x in line.lower() for x in skip_keywords):
            return True
        return False
