"""Тесты для специализированных парсеров"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.models import RawMessage
from parser.parser_service import ParserService


async def test_smartphone_parsing():
    """Тест парсинга смартфонов"""
    parser = ParserService()
    
    test_text = """
iPhone 17 Pro Max 256GB Black 🇺🇸 121000 RUB
iPhone 17 Pro 256GB Blue 🇪🇺 110000 RUB
    """
    
    raw = RawMessage(
        id='test_iphone_001',
        text=test_text,
        timestamp=datetime.utcnow(),
        channel_id='top_resale',
        message_link='https://t.me/test/1'
    )
    
    result = await parser.parse_raw_message(raw)
    if result:
        print(f"[OK] iPhone: {result.brand} {result.model} - {result.price} RUB")
        print(f"  Attributes: {result.attributes}")
    else:
        print("[ERR] iPhone: не распаршено")
    
    # Samsung тест
    test_samsung = """
Samsung Galaxy S25 Ultra
S25 Ultra 256GB Black 🇰🇷 121000 RUB
S25+ 512GB Blue 🇪🇺 110000 RUB
    """
    
    raw_samsung = RawMessage(
        id='test_samsung_001',
        text=test_samsung,
        timestamp=datetime.utcnow(),
        channel_id='top_resale',
        message_link='https://t.me/test/2'
    )
    
    result_samsung = await parser.parse_raw_message(raw_samsung)
    if result_samsung:
        print(f"[OK] Samsung: {result_samsung.brand} {result_samsung.model} - {result_samsung.price} RUB")
        print(f"  Attributes: {result_samsung.attributes}")
    else:
        print("[ERR] Samsung: не распаршено")


async def test_laptop_parsing():
    """Тест парсинга ноутбуков"""
    parser = ParserService()
    
    test_text = """
MacBook Air 13 M2 256GB Starlight 🇪🇺 105000 RUB
MacBook Pro 14 M3 512GB Black 🇺🇸 180000 RUB
    """
    
    raw = RawMessage(
        id='test_macbook_001',
        text=test_text,
        timestamp=datetime.utcnow(),
        channel_id='top_resale',
        message_link='https://t.me/test/3'
    )
    
    result = await parser.parse_raw_message(raw)
    if result:
        print(f"[OK] MacBook: {result.brand} {result.model} - {result.price} RUB")
        print(f"  Attributes: {result.attributes}")
    else:
        print("[ERR] MacBook: не распаршено")


async def test_sim_types():
    """Тест SIM типов для разных регионов"""
    parser = ParserService()
    
    # Китай - 2 SIM
    test_cn = "iPhone 17 Pro 256GB 🇨🇳 100000 RUB"
    raw_cn = RawMessage(
        id='test_cn',
        text=test_cn,
        timestamp=datetime.utcnow(),
        channel_id='test',
        message_link='https://t.me/test/cn'
    )
    
    # Европа - SIM + eSIM
    test_eu = "iPhone 17 Pro 256GB 🇪🇺 100000 RUB"
    raw_eu = RawMessage(
        id='test_eu',
        text=test_eu,
        timestamp=datetime.utcnow(),
        channel_id='test',
        message_link='https://t.me/test/eu'
    )
    
    # США - eSIM only
    test_us = "iPhone 17 Pro 256GB 🇺🇸 100000 RUB"
    raw_us = RawMessage(
        id='test_us',
        text=test_us,
        timestamp=datetime.utcnow(),
        channel_id='test',
        message_link='https://t.me/test/us'
    )
    
    result_cn = await parser.parse_raw_message(raw_cn)
    result_eu = await parser.parse_raw_message(raw_eu)
    result_us = await parser.parse_raw_message(raw_us)
    
    print("\nSIM Type Tests:")
    if result_cn:
        print(f"  CN (Китай): {result_cn.attributes.get('sim_type')} (ожидалось: 2sim)")
    if result_eu:
        print(f"  EU (Европа): {result_eu.attributes.get('sim_type')} (ожидалось: sim+esim)")
    if result_us:
        print(f"  US (США): {result_us.attributes.get('sim_type')} (ожидалось: esim)")


async def main():
    print("=== Тест парсеров ===\n")
    
    print("1. iPhone парсинг:")
    await test_smartphone_parsing()
    
    print("\n2. MacBook парсинг:")
    await test_laptop_parsing()
    
    print("\n3. SIM типы:")
    await test_sim_types()
    
    print(f"\n=== Итого распаршено: {ParserService().products_parsed} ===")


if __name__ == '__main__':
    asyncio.run(main())
