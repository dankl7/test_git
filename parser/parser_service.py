import re
import structlog
from datetime import datetime
from typing import Optional, List, Dict
from common.models import RawMessage, ParsedProduct
from .category_parsers import SmartphoneParser, LaptopParser, TabletParser, ConsoleParser, AccessoryParser

logger = structlog.get_logger(__name__)


class ParserService:
    """Сервис парсинга сообщений с использованием специализированных парсеров"""
    
    def __init__(self):
        self.parsers = {
            'smartphones': SmartphoneParser(),
            'laptops': LaptopParser(),
            'tablets': TabletParser(),
            'consoles': ConsoleParser(),
            'accessories': AccessoryParser()
        }
        self.products_parsed = 0
        self.processed_hashes = set()

    async def parse_raw_message(self, raw_message: RawMessage) -> Optional[ParsedProduct]:
        """Парсит сырое сообщение и возвращает список продуктов"""
        if not raw_message.text or len(raw_message.text.strip()) < 5:
            return None
        
        # 1. Сбор и группировка по блокам
        blocks = self._collect_blocks(raw_message.text)
        products = []
        
        for category, header, lines in blocks:
            if category in self.parsers:
                parser = self.parsers[category]
                parsed_items = parser.parse_block(header, lines)
                
                for item in parsed_items:
                    prod = self._create_product(raw_message, category, item)
                    if prod:
                        products.append(prod)
        
        # 2. Сохранение
        for product in products:
            await self._save_to_storage(product)
            self.products_parsed += 1
        
        return products[0] if products else None

    def _collect_blocks(self, text: str) -> List[tuple]:
        """
        Собирает блоки: (category, header, lines).
        Логика: если строка похожа на заголовок категории - начинаем новый блок.
        Если строка содержит цену и флаг - это продукт.
        """
        blocks = []
        current_category = None
        current_header = ""
        current_lines = []
        
        lines = text.split('\n')
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            line_lower = line_stripped.lower()
            
            # Определение категории по заголовку
            new_category = self._detect_category(line_lower)
            
            # Если нашли новый заголовок категории
            if new_category:
                # Сохраняем предыдущий блок
                if current_category and current_lines:
                    blocks.append((current_category, current_header, current_lines))
                
                # Начинаем новый
                current_category = new_category
                current_header = line_stripped
                current_lines = []
                
                # Если строка также содержит цену и флаг - это продукт (заголовок + продукт в одной строке)
                if self._is_product_line(line_stripped):
                    current_lines.append(line_stripped)
            elif current_category:
                # Если категория уже выбрана, добавляем строку в текущий блок
                # Проверка: если строка содержит цену и флаг, это точно товар
                if self._is_product_line(line_stripped):
                    current_lines.append(line_stripped)
        
        # Добавляем последний блок
        if current_category and current_lines:
            blocks.append((current_category, current_header, current_lines))
        
        return blocks

    def _detect_category(self, line: str) -> Optional[str]:
        """Определяет категорию по строке"""
        # Smartphones
        if any(x in line for x in ['iphone', 'samsung', 'galaxy s', 'galaxy a', 'pixel', 'poco', 'xiaomi', 'honor', 'huawei']):
            return 'smartphones'
        
        # Laptops
        if any(x in line for x in ['macbook', 'macbook air', 'macbook pro']):
            return 'laptops'
        
        # Tablets
        if any(x in line for x in ['ipad', 'планшет']):
            return 'tablets'
        
        # Consoles
        if any(x in line for x in ['ps5', 'playstation', 'xbox', 'nintendo', 'console']):
            return 'consoles'
        
        # Accessories
        if any(x in line for x in ['airpods', 'watch', 'dyson', 'accessory', 'аксессуар']):
            return 'accessories'
        
        return None

    def _is_product_line(self, line: str) -> bool:
        """Проверяет, является ли строка описанием товара"""
        # Должна содержать цифры (цену) и валюту
        has_price = re.search(r'\d{3,}', line) and re.search(r'[₽$€\d]', line)
        return has_price and len(line.strip()) >= 5

    def _create_product(self, raw: RawMessage, category: str, item: dict) -> ParsedProduct:
        """Создает объект ParsedProduct"""
        h = hash(f"{raw.id}_{item['model']}_{item['price']}") & 0xffffffff
        return ParsedProduct(
            id=f"prod_{raw.id}_{h}_{int(datetime.utcnow().timestamp())}",
            category_id=category,
            brand=item['brand'],
            model=item['model'],
            price=item['price'],
            source_channel=raw.channel_id,
            message_link=raw.message_link,
            timestamp=raw.timestamp,
            attributes=item.get('attributes', {}),
            raw_message_id=raw.id
        )

    async def _save_to_storage(self, product: ParsedProduct):
        """Сохраняет продукт в БД через нормализатор"""
        try:
            from services.normalizer import NormalizerService
            from common.database import Database
            
            # Нормализуем продукт
            normalized_product = NormalizerService.normalize_product(product)
            
            # Сохраняем в БД
            db = Database()
            await db.save_product(
                product_id=normalized_product.id,
                category_id=normalized_product.category_id,
                brand=normalized_product.brand,
                model=normalized_product.model,
                price=normalized_product.price,
                attributes=normalized_product.attributes,
                source_channel=normalized_product.source_channel,
                message_link=normalized_product.message_link,
                timestamp=normalized_product.timestamp
            )
            
            logger.info(f"Product saved: {normalized_product.brand} {normalized_product.model} - {normalized_product.price} RUB")
        except Exception as e:
            logger.error(f"Error saving product: {e}")
