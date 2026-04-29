import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from common.database import Product, Category, PriceHistory
from common.models import SearchCriteria

class CategoryRepository:
    """Repository for category operations (FR-3.4, FR-3.5)"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def get(self, category_id: str) -> Optional[Category]:
        """Get category by ID"""
        result = self.db.execute(
            select(Category).where(Category.id == category_id)
        )
        return result.scalar_one_or_none()
    
    async def get_or_create(self, category_id: str) -> Optional[Category]:
        """Get existing category or create new one dynamically"""
        category = await self.get(category_id)
        
        if not category:
            category = Category(
                id=category_id,
                name=category_id.capitalize(),
                attributes=[],
                keywords=[],
                is_active=True
            )
            self.db.add(category)
            self.db.commit()
            self.db.refresh(category)
        
        return category
    
    async def add_attribute(self, category_id: str, attribute: str):
        """Add new attribute to category without migration (FR-3.5)"""
        category = await self.get(category_id)
        if category:
            if attribute not in (category.attributes or []):
                category.attributes = (category.attributes or []) + [attribute]
                self.db.commit()
    
    async def get_all(self) -> List[Category]:
        """Get all active categories"""
        result = self.db.execute(
            select(Category).where(Category.is_active == True)
        )
        return result.scalars().all()


class ProductRepository:
    """Repository for product operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def create(self, product_data: Dict[str, Any]) -> Optional[Product]:
        """Create new product"""
        try:
            product = Product(
                id=product_data.get('id', str(uuid.uuid4())),
                category_id=product_data.get('category_id'),
                brand=product_data.get('brand'),
                model=product_data.get('model'),
                price=product_data.get('price'),
                source_channel=product_data.get('source_channel'),
                message_link=product_data.get('message_link'),
                timestamp=product_data.get('timestamp', datetime.utcnow()),
                attributes=product_data.get('attributes', {}),
                raw_message_id=product_data.get('raw_message_id')
            )
            
            self.db.add(product)
            self.db.commit()
            self.db.refresh(product)
            
            return product
            
        except Exception as e:
            self.db.rollback()
            raise
    
    async def get(self, product_id: str) -> Optional[Product]:
        """Get product by ID"""
        result = self.db.execute(
            select(Product).where(Product.id == product_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_message_link(self, message_link: str) -> Optional[Product]:
        """Get product by message link (uniqueness check)"""
        result = self.db.execute(
            select(Product).where(Product.message_link == message_link)
        )
        return result.scalar_one_or_none()
    
    async def search(self, criteria: SearchCriteria) -> List[Product]:
        """Search products by criteria (FR-4.1)"""
        query = select(Product)
        
        if criteria.category_id:
            query = query.where(Product.category_id == criteria.category_id)
        
        if criteria.brand:
            query = query.where(Product.brand.ilike(f"%{criteria.brand}%"))
        
        if criteria.model:
            query = query.where(Product.model.ilike(f"%{criteria.model}%"))
        
        if criteria.min_price:
            query = query.where(Product.price >= criteria.min_price)
        
        if criteria.max_price:
            query = query.where(Product.price <= criteria.max_price)
        
        if criteria.attributes:
            for key, value in criteria.attributes.items():
                query = query.where(
                    Product.attributes[key].astext == str(value)
                )
        
        query = query.order_by(Product.timestamp.desc())
        query = query.limit(criteria.limit).offset(criteria.offset)
        
        result = self.db.execute(query)
        return result.scalars().all()
    
    async def get_price_history(
        self, 
        product_id: str, 
        limit: int = 100,
        offset: int = 0
    ) -> List[PriceHistory]:
        """Get price history for product (FR-3.3, FR-4.1)"""
        result = self.db.execute(
            select(PriceHistory)
            .where(PriceHistory.product_id == product_id)
            .order_by(PriceHistory.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()
    
    async def add_price_history(self, price_data: Dict[str, Any]):
        """Add price history entry"""
        price_history = PriceHistory(
            id=str(uuid.uuid4()),
            product_id=price_data['product_id'],
            price=price_data['price'],
            timestamp=price_data.get('timestamp', datetime.utcnow()),
            source_channel=price_data.get('source_channel')
        )
        
        self.db.add(price_history)
        self.db.commit()
    
    async def get_current_prices(
        self, 
        category_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Product]:
        """Get current/latest prices for products"""
        subquery = select(
            Product.message_link,
            func.max(Product.timestamp).label('max_ts')
        ).group_by(Product.message_link)
        
        if category_id:
            subquery = subquery.where(Product.category_id == category_id)
        
        query = select(Product).join(
            subquery,
            Product.message_link == subquery.c.message_link
        ).where(
            Product.timestamp == subquery.c.max_ts
        ).order_by(
            Product.timestamp.desc()
        ).limit(limit)
        
        result = self.db.execute(query)
        return result.scalars().all()
