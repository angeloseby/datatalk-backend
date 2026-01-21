from sqlalchemy import create_engine, text

# PASTE YOUR FULL CONNECTION STRING INSIDE THE QUOTES
# Example: "postgresql://postgres:password@db.your-project.supabase.co:5432/postgres"
TEST_URL = "postgresql://neondb_owner:4io-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

print(f"Attempting to connect to: {TEST_URL.split('@')[1]}") # Prints host only for safety

try:
    engine = create_engine(TEST_URL)
    with engine.connect() as conn:
        print("✅ SUCCESS! The database is reachable.")
except Exception as e:
    print("\n❌ FAILED.")
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {e}")