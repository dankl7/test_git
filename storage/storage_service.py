import asyncio
import json
import structlog
from typing import Optional
from datetime import datetime
import redis.asyncio as redis
from sqlalchemy.orm import Session
from common.config import settings
from common.models import ParsedProduct
from common.database import get_db, Product, PriceHistory, Category
from .repository import ProductRepository, CategoryRepository

logger = structlog.get_logger(__name__)


class StorageService:
    """
    Storage service - persists parsed products to database (FR-3.1)
    Listens to parsed products queue and stores in PostgreSQL
    """
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.product_repo: Optional[ProductRepository] = None
        self.category_repo: Optional[CategoryRepository] = None
        self._running = False
        
    async def initialize(self):
        """Initialize Redis and database connections"""
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )
        
        db = next(get_db())
        self.product_repo = ProductRepository(db)
        self.category_repo = CategoryRepository(db)
        
        logger.info("Storage service initialized")
    
    async def start(self):
        """Start listening for parsed products"""
        self._running = True
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe(settings.PARSED_PRODUCTS_CHANNEL)
        
        logger.info("Storage service started, listening for products")
        
        while self._running:
            try:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0
                )
                
                if message and message['type'] == 'message':
                    await self._store_product(message['data'])
                    
            except Exception as e:
                logger.error("Error in storage loop", error=str(e))
                await asyncio.sleep(1)
    
    async def _store_product(self, data: str):
        """Store parsed product in database (FR-3.2, FR-3.3)"""
        try:
            product_data = json.loads(data)
            
            category_id = product_data.get('category_id')
            category = await self.category_repo.get_or_create(category_id)
            
            if not category:
                logger.error("Category not found and couldn't create", id=category_id)
                return
            
            existing = await self.product_repo.get_by_message_link(
                product_data.get('message_link')
            )
            
            if existing:
                logger.info("Product already exists, skipping", link=product_data.get('message_link'))
                return
            
            product = await self.product_repo.create(product_data)
            
            if product:
                await self._store_price_history(product.id, product_data)
                logger.info(
                    "Product stored",
                    product_id=product.id,
                    category=category_id
                )
            
        except Exception as e:
            logger.error("Error storing product", error=str(e))
    
    async def _store_price_history(self, product_id: str, product_data: dict):
        """Store price history entry (FR-3.3)"""
        price_history = {
            "product_id": product_id,
            "price": product_data.get('price'),
            "timestamp": product_data.get('timestamp', datetime.utcnow()),
            "source_channel": product_data.get('source_channel')
        }
        
        await self.product_repo.add_price_history(price_history)
    
    async def stop(self):
        """Stop the storage service"""
        self._running = False
        if self.redis_client:
            await self.redis_client.close()
        logger.info("Storage service stopped")
