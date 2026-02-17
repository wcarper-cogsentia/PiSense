"""Download cardboard box detection model from Roboflow"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load API key from .env file
load_dotenv(Path(__file__).parent.parent / ".env")

api_key = os.getenv("ROBOFLOW_API_KEY")
if not api_key:
    raise ValueError("ROBOFLOW_API_KEY not found in .env file")

print("Connecting to Roboflow...")
from roboflow import Roboflow

rf = Roboflow(api_key=api_key)

print("Downloading cardboard box dataset (v4, YOLOv8 format)...")
project = rf.workspace("carboard-box").project("carboard-box")
version = project.version(4)

# Download into models/ directory at project root
models_dir = Path(__file__).parent.parent / "models"
models_dir.mkdir(exist_ok=True)

dataset = version.download("yolov8", location=str(models_dir / "cardboard-box"))

print(f"\nDownload complete.")
print(f"Dataset saved to: {models_dir / 'cardboard-box'}")
print(f"\nContents:")
for f in sorted((models_dir / "cardboard-box").rglob("*")):
    if f.is_file():
        print(f"  {f.relative_to(models_dir)}")
