import os
from dotenv import load_dotenv
from multipart.multipart import parse_options_header

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
