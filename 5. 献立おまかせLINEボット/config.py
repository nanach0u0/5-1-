import os

from dotenv import load_dotenv

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_RECIPE_DS_ID = os.getenv("NOTION_RECIPE_DS_ID", "9a833992-d10e-4ff2-be5d-46556c73702c")
NOTION_LOG_DS_ID = os.getenv("NOTION_LOG_DS_ID", "71f767d5-843a-4e2b-9af5-011afb30db38")
