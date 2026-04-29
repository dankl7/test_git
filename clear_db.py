"""
Clear all data from database
WARNING: This will delete ALL products, price history, categories, and API keys!
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from common.database import engine, Base, Product, PriceHistory, Category, Channel, APIKey
from sqlalchemy import text

def clear_database():
    """Clear all tables"""
    print("="*60)
    print("Window of Light - Database Clear Utility")
    print("="*60)
    print()
    print("⚠️  WARNING: This will delete ALL data from the following tables:")
    print("   - products")
    print("   - price_history")
    print("   - categories")
    print("   - channels")
    print("   - api_keys")
    print()
    
    confirm = input("Are you sure? Type 'YES' to confirm: ").strip()
    if confirm != 'YES':
        print("❌ Operation cancelled")
        return
    
    print()
    print("🗑️  Clearing database...")
    
    try:
        # Create tables if they don't exist
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created/verified")
        
        # Clear data in correct order (respecting foreign keys)
        with engine.connect() as conn:
            # Clear price_history first (has FK to products)
            result = conn.execute(text("DELETE FROM price_history"))
            print(f"   - Cleared {result.rowcount} price history records")
            conn.commit()
            
            # Clear products
            result = conn.execute(text("DELETE FROM products"))
            print(f"   - Cleared {result.rowcount} products")
            conn.commit()
            
            # Clear categories
            result = conn.execute(text("DELETE FROM categories"))
            print(f"   - Cleared {result.rowcount} categories")
            conn.commit()
            
            # Clear channels
            result = conn.execute(text("DELETE FROM channels"))
            print(f"   - Cleared {result.rowcount} channels")
            conn.commit()
            
            # Clear api_keys
            result = conn.execute(text("DELETE FROM api_keys"))
            print(f"   - Cleared {result.rowcount} API keys")
            conn.commit()
        
        print()
        print("✅ Database cleared successfully!")
        print()
        print("Next steps:")
        print("1. Run: python services/run_combined.py")
        print("2. Or run: python -m uvicorn services.run_combined:app --reload")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise

if __name__ == "__main__":
    clear_database()
