"""
Train YOLOv8n on the cardboard box dataset.

Run with venv active:
    source venv/bin/activate
    python src/train_model.py

Training will take several hours on Pi CPU.
Output model saved to: models/trained/weights/best.pt
"""

import os
import yaml
import time
from pathlib import Path

# Resolve project root relative to this script
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DATASET_DIR = PROJECT_ROOT / "models" / "cardboard-box"
DATA_YAML = DATASET_DIR / "data.yaml"
OUTPUT_DIR = PROJECT_ROOT / "models" / "trained"

def patch_data_yaml():
    """Rewrite data.yaml with absolute paths so YOLO can find images from any cwd."""
    with open(DATA_YAML) as f:
        config = yaml.safe_load(f)

    config["train"] = str(DATASET_DIR / "train" / "images")
    config["val"] = str(DATASET_DIR / "valid" / "images")
    config["test"] = str(DATASET_DIR / "test" / "images")

    # Ensure only the 'box' class (ignore class '0' and 'snake-in-cardboard-boxes')
    config["names"] = ["box"]
    config["nc"] = 1

    patched_path = DATASET_DIR / "data_train.yaml"
    with open(patched_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    print(f"Patched data yaml written to: {patched_path}")
    return patched_path


def main():
    print("=" * 60)
    print("PiSense - Cardboard Box Model Training")
    print("=" * 60)
    print(f"Project root:  {PROJECT_ROOT}")
    print(f"Dataset:       {DATASET_DIR}")
    print(f"Output:        {OUTPUT_DIR}")
    print()

    # Verify dataset exists
    if not DATASET_DIR.exists():
        print("ERROR: Dataset not found. Run src/download_model.py first.")
        return

    train_images = list((DATASET_DIR / "train" / "images").glob("*.jpg"))
    val_images = list((DATASET_DIR / "valid" / "images").glob("*.jpg"))
    print(f"Training images:   {len(train_images)}")
    print(f"Validation images: {len(val_images)}")
    print()

    if len(train_images) == 0:
        print("ERROR: No training images found.")
        return

    # Patch data.yaml with absolute paths
    data_yaml_path = patch_data_yaml()

    # Import Ultralytics
    print("Loading Ultralytics...")
    try:
        from ultralytics import YOLO
    except ImportError:
        print("ERROR: ultralytics not installed.")
        print("Run: pip install ultralytics")
        return

    # Load base YOLOv8n model (nano - fastest, smallest, good for Pi inference)
    print("Loading YOLOv8n base model...")
    model = YOLO("yolov8n.pt")  # Downloads ~6MB COCO-pretrained weights on first run

    print()
    print("Starting training...")
    print("This will take several hours on Pi CPU.")
    print("You can safely leave this running overnight.")
    print("Progress is saved after every epoch - safe to Ctrl+C and resume later.")
    print()

    start_time = time.time()

    results = model.train(
        data=str(data_yaml_path),
        epochs=50,           # 50 epochs is sufficient for fine-tuning
        imgsz=640,           # Match our recording resolution
        batch=4,             # Small batch for Pi RAM constraints (4GB)
        workers=2,           # 2 CPU workers for data loading
        device="cpu",        # Pi has no CUDA GPU
        project=str(OUTPUT_DIR),
        name="box_detector",
        exist_ok=True,       # Resume/overwrite existing run
        patience=10,         # Stop early if no improvement for 10 epochs
        save=True,
        plots=False,         # Skip matplotlib plots (saves memory)
        verbose=True,
        # Class filtering: only train on class index 1 ('box'), ignore 0 and 2
        # Note: done via data.yaml nc=1 - labels with class 0 map to 'box'
    )

    elapsed = time.time() - start_time
    hours = int(elapsed // 3600)
    mins = int((elapsed % 3600) // 60)

    print()
    print("=" * 60)
    print(f"Training complete in {hours}h {mins}m")
    print()

    best_pt = OUTPUT_DIR / "box_detector" / "weights" / "best.pt"
    if best_pt.exists():
        print(f"Best model saved to: {best_pt}")
        print()
        print("Next step: run analyze_video.py to test the model on a recording")
        print("    python src/analyze_video.py videos/your_video.h264")
    else:
        print("WARNING: best.pt not found - check training output above for errors")


if __name__ == "__main__":
    main()
