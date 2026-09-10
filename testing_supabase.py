import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

url = os.environ["DATABASE_URL"]

engine = create_engine(url)

with engine.connect() as conn:
    result = conn.execute(text("SELECT 1"))
    print(result.scalar())