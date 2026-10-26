import json
import os

from dotenv import load_dotenv
load_dotenv()

from app.main import app

os.makedirs("docs", exist_ok=True)

with open("docs/openapi.json", "w") as f:
    json.dump(app.openapi(), f, indent=2)

print("Saved docs/openapi.json")