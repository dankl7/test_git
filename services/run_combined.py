"""
Window of Light - Combined Service
Запускает Ingestion + Parser + Storage в одном процессе
"""
import asyncio
import structlog
import sys
import io

# Fix Windows console encoding for UTF-8
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from pathlib import Path
import sys
import os
import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader
import yaml
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from common.config import settings
from common.database import engine, Base, get_db
from common.database import Product, PriceHistory, Category, Channel, APIKey
from common.models import SearchCriteria
from ingestion.telegram_client import TelegramIngestionService
from parser.parser_service import ParserService
from ingestion.config_loader import ChannelConfigLoader
from storage.repository import ProductRepository, CategoryRepository

logger = structlog.get_logger(__name__)

# Global state
db_ready = False

# FastAPI приложение
app = FastAPI(title="Window of Light")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global services
ingestion_service = None
parser_service = None
config_loader = None
channels_file = Path("config/channels.yaml")

# API Key authentication
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Pydantic models for API
class ProductSearchRequest(BaseModel):
    category_id: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    attributes: Optional[Dict[str, Any]] = None
    limit: int = 100
    offset: int = 0


class ProductResponse(BaseModel):
    id: str
    category_id: str
    brand: str
    model: str
    price: float
    source_channel: str
    message_link: str
    timestamp: datetime
    attributes: Dict[str, Any]


def load_channels_from_file():
    """Загрузить каналы из файла"""
    try:
        if channels_file.exists():
            with open(channels_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                channels = config.get('channels', [])
                logger.info(f"📂 Loaded {len(channels)} channels from config")
                return channels
    except Exception as e:
        logger.error(f"⚠️ Error loading channels: {e}")
    return []


def save_channels_to_file(channels):
    """Сохранить каналы в файл"""
    try:
        config = {"channels": channels}
        with open(channels_file, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        logger.info(f"💾 Saved {len(channels)} channels to file")
        return True
    except Exception as e:
        logger.error(f"⚠️ Error saving channels: {e}")
        return False


@app.get("/api/v1/channels/")
async def get_channels():
    """Получить список каналов"""
    if not ingestion_service:
        return JSONResponse({"error": "Service not ready"}, status_code=503)
    
    channels = ingestion_service.get_monitored_channels()
    return JSONResponse(channels)


@app.post("/api/v1/channels/add")
async def add_channel(request: dict):
    """Добавить канал"""
    if not ingestion_service:
        return JSONResponse({"error": "Service not ready"}, status_code=503)
    
    link = request.get('link')
    title = request.get('title')
    
    if not link:
        return JSONResponse({"status": "error", "message": "Link required"}, status_code=400)
    
    success = await ingestion_service.add_channel(link, title)
    
    if success:
        channels = load_channels_from_file()
        exists = any(ch.get('link') == link or ch.get('username') == link for ch in channels)
        
        if not exists:
            channels.append({"link": link, "title": title or link, "is_active": True})
            save_channels_to_file(channels)
        
        return JSONResponse({"status": "success", "message": f"Channel {link} added"})
    else:
        return JSONResponse({"status": "error", "message": "Failed to add"}, status_code=400)


@app.post("/api/v1/channels/remove")
async def remove_channel(request: dict):
    """Удалить канал"""
    if not ingestion_service:
        return JSONResponse({"error": "Service not ready"}, status_code=503)

    link = request.get('link')

    if not link:
        return JSONResponse({"status": "error", "message": "Link required"}, status_code=400)

    success = await ingestion_service.remove_channel(link)

    if success:
        channels = load_channels_from_file()
        original_count = len(channels)
        channels = [ch for ch in channels if ch.get('link') != link and ch.get('username') != link]

        if len(channels) < original_count:
            save_channels_to_file(channels)

        # Кэш отключен

        return JSONResponse({"status": "success", "message": f"Channel {link} removed"})
    else:
        return JSONResponse({"status": "error", "message": "Not found"}, status_code=404)


@app.post("/api/v1/api-keys")
async def create_api_key(request: dict):
    """Create new API key"""
    from common.database import APIKey
    import uuid
    from datetime import datetime, timedelta
    
    name = request.get('name', 'API Key')
    expires_days = request.get('expires_days', 365)
    
    # Generate new key
    new_key = f"wok_{uuid.uuid4().hex}"
    
    db = next(get_db())
    api_key = APIKey(
        id=str(uuid.uuid4()),
        key_hash=new_key,
        name=name,
        is_active=True,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=expires_days) if expires_days else None
    )
    
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    
    return {
        "api_key": new_key,
        "name": name,
        "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None
    }


@app.get("/status")
async def get_status():
    """Статус системы"""
    if not ingestion_service:
        return {"status": "not_ready"}
    
    return {
        "status": "running",
        "channels_monitored": len(ingestion_service.monitors),
        "messages_sent": ingestion_service.messages_sent,
        "messages_parsed": ingestion_service.messages_parsed,
        "parser_products": parser_service.products_parsed if parser_service else 0
    }


@app.get("/")
async def root():
    """Главная страница"""
    template_path = Path("templates/index.html")
    if template_path.exists():
        return FileResponse(str(template_path))
    return JSONResponse({"error": "Web UI not available"})


async def verify_api_key(api_key: str = Security(api_key_header)):
    """Verify API key from header"""
    if not api_key:
        # API key is optional for read endpoints
        return None
    
    # Check against environment variable
    env_api_key = getattr(settings, 'API_KEY', None)
    if env_api_key and api_key == env_api_key:
        return api_key
    
    # Check against database
    db = next(get_db())
    from sqlalchemy import select
    result = db.execute(
        select(APIKey).where(APIKey.key_hash == api_key).where(APIKey.is_active == True)
    )
    api_key_obj = result.scalar_one_or_none()
    
    if api_key_obj:
        return api_key_obj
    
    raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/health")
async def health():
    """Health check (Redis disabled)"""
    health_status = {
        "status": "healthy",
        "service": "window-of-light-combined",
        "dependencies": {
            "database": "unknown",
            "redis": "disabled",  # Redis отключен
            "telegram": "unknown"
        }
    }

    # Check database
    try:
        conn = engine.connect()
        conn.execute(text("SELECT 1"))
        conn.close()
        health_status["dependencies"]["database"] = "ok"
    except Exception as e:
        health_status["dependencies"]["database"] = f"error: {str(e)[:50]}"
        health_status["status"] = "degraded"

    # Redis отключен
    health_status["dependencies"]["redis"] = "disabled (no caching)"

    # Check Telegram
    try:
        if ingestion_service and ingestion_service.client:
            health_status["dependencies"]["telegram"] = "ok"
        else:
            health_status["dependencies"]["telegram"] = "not initialized"
    except Exception:
        health_status["dependencies"]["telegram"] = "error"

    return health_status


async def check_database_ready() -> bool:
    """Проверка готовности БД с retry"""
    max_retries = 10
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            conn = engine.connect()
            conn.execute(text("SELECT 1"))
            conn.close()
            logger.info("✅ Database connection successful")
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"⚠️ Database not ready (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"❌ Database connection failed after {max_retries} attempts: {e}")
    return False


# Redis функции удалены - Redis не используется


async def init_database():
    """Инициализация таблиц БД"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables created")
        return True
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")
        return False


# === Cache Functions удалены - Redis не используется ===


# === API Endpoints - Products ===
@app.get("/api/v1/products/{product_id}")
async def get_product(product_id: str):
    """Get current product data (кэш отключен)"""
    db = next(get_db())
    repo = ProductRepository(db)
    product = await repo.get(product_id)
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return {
        "id": product.id,
        "category_id": product.category_id,
        "brand": product.brand,
        "model": product.model,
        "price": product.price,
        "source_channel": product.source_channel,
        "message_link": product.message_link,
        "timestamp": product.timestamp.isoformat(),
        "attributes": product.attributes or {}
    }


@app.get("/api/v1/products/{product_id}/history")
async def get_price_history(product_id: str, limit: int = 100, offset: int = 0):
    """Get price history with pagination (FR-4.1)"""
    db = next(get_db())
    repo = ProductRepository(db)
    history = await repo.get_price_history(product_id, limit, offset)
    
    return {
        "product_id": product_id,
        "count": len(history),
        "limit": limit,
        "offset": offset,
        "history": [
            {
                "id": h.id,
                "price": h.price,
                "timestamp": h.timestamp.isoformat(),
                "source_channel": h.source_channel
            }
            for h in history
        ]
    }


@app.post("/api/v1/products/search")
async def search_products(criteria: ProductSearchRequest):
    """Search products by criteria (FR-4.1)"""
    db = next(get_db())
    repo = ProductRepository(db)
    
    search_criteria = SearchCriteria(
        category_id=criteria.category_id,
        brand=criteria.brand,
        model=criteria.model,
        min_price=criteria.min_price,
        max_price=criteria.max_price,
        attributes=criteria.attributes,
        limit=criteria.limit,
        offset=criteria.offset
    )
    
    products = await repo.search(search_criteria)
    
    return {
        "count": len(products),
        "offset": criteria.offset,
        "limit": criteria.limit,
        "products": [
            {
                "id": p.id,
                "category_id": p.category_id,
                "brand": p.brand,
                "model": p.model,
                "price": p.price,
                "source_channel": p.source_channel,
                "message_link": p.message_link,
                "timestamp": p.timestamp.isoformat(),
                "attributes": p.attributes or {}
            }
            for p in products
        ]
    }


@app.get("/api/v1/categories")
async def get_categories():
    """Get all categories with attributes (кэш отключен)"""
    db = next(get_db())
    repo = CategoryRepository(db)
    categories = await repo.get_all()
    
    return [
        {
            "id": c.id,
            "name": c.name,
            "parent_id": c.parent_id,
            "attributes": c.attributes or [],
            "keywords": c.keywords or [],
            "is_active": c.is_active
        }
        for c in categories
    ]


async def main():
    global ingestion_service, parser_service, config_loader, db_ready

    logger.info("🚀 Starting Window of Light - Combined Service")

    # === ЭТАП 1: Проверка БД ===
    logger.info("📊 Step 1/5: Checking database connection...")
    db_ready = await check_database_ready()
    if not db_ready:
        logger.error("❌ Database is not available. Exiting.")
        return
    
    # Инициализация таблиц
    if not await init_database():
        logger.error("❌ Failed to initialize database tables. Exiting.")
        return

    # === ЭТАП 2: Redis отключен ===
    logger.info("📊 Step 2/5: Redis disabled (no caching)")
    logger.info("⚠️  Redis not available, continuing without caching")

    # === ЭТАП 3: Загружаем каналы ===
    logger.info("📊 Step 3/5: Loading channels configuration...")
    channels = load_channels_from_file()
    logger.info(f"📂 Loaded {len(channels)} channels from config")

    # === ЭТАП 4: Инициализация Parser ===
    logger.info("📊 Step 4/5: Initializing Parser Service...")
    parser_service = ParserService()  # LLM отключен, используем только блочные парсеры
    logger.info("✅ Parser Service initialized")

    # === ЭТАП 5: Инициализация Telegram Ingestion ===
    logger.info("📊 Step 5/5: Initializing Telegram Ingestion...")
    ingestion_service = TelegramIngestionService(parser_service=parser_service)
    await ingestion_service.initialize()

    # Подключение к Telegram
    logger.info("📱 Connecting to Telegram...")
    await ingestion_service.client.start(phone=settings.TELEGRAM_PHONE)
    logger.info("✅ Telegram connected")

    # Добавляем каналы
    added_count = 0
    for channel_data in channels:
        link = channel_data.get('link') or channel_data.get('username')
        if link:
            success = await ingestion_service.add_channel(link, channel_data.get('title'))
            if success:
                added_count += 1

    logger.info(
        f"📺 Channels loaded",
        total=len(channels),
        added=added_count
    )

    # === Все этапы пройдены - запускаем API и мониторинг ===
    logger.info("🎉 All initialization steps completed successfully!")
    logger.info("🌐 Starting API on http://0.0.0.0:8002")
    logger.info("📱 Starting Telegram monitoring...")
    logger.info("="*80)
    logger.info("📊 SYSTEM READY - Waiting for new posts and price updates")
    logger.info("="*80)
    logger.info("💡 Parser Service will:")
    logger.info("   - Monitor channels for new messages")
    logger.info("   - Parse products from posts automatically")
    logger.info("   - Save raw posts for re-processing if needed")
    logger.info("   - Track price changes over time")
    logger.info("="*80)

    # Запускаем API и мониторинг параллельно
    config = uvicorn.Config(app, host="0.0.0.0", port=8002, log_level="info", access_log=True)
    server = uvicorn.Server(config)

    await asyncio.gather(
        server.serve(),
        ingestion_service.start_monitoring()
    )


async def shutdown():
    """Корректное завершение (Redis отключен)"""
    try:
        logger.info("🛑 Shutting down...")

        if ingestion_service:
            await ingestion_service.stop()

        if config_loader:
            config_loader.stop_watching()

        logger.info("✅ Shutdown complete")
    except Exception as e:
        logger.error(f"⚠️ Shutdown error: {e}")


if __name__ == "__main__":
    loop = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("⌨️ Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
    finally:
        try:
            if loop:
                loop.run_until_complete(asyncio.wait_for(shutdown(), timeout=5.0))
        except Exception:
            pass
        finally:
            try:
                if loop:
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    loop.close()
            except Exception:
                pass
