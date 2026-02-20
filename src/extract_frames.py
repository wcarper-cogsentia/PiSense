"""
Extract frames from videos for training data labeling.

Hybrid approach:
- Extracts 1 random frame per video (captures environment diversity)
- Extracts up to 5 frames where the model detected objects (problem cases)
- Saves frames with metadata for easy labeling workflow

Usage:
    # Process all videos in videos/ directory
    python src/extract_frames.py

    # Process specific videos
    python src/extract_frames.py videos/video_20250220_*.h264

    # Adjust extraction parameters
    python src/extract_frames.py --random-per-video 2 --detections-per-video 3
"""

import sys
import random
import argparse
import logging
import subprocess
from pathlib import Path
import cv2
from ultralytics import YOLO

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
MODEL_PATH = PROJECT_ROOT / "models" / "trained" / "box_detector" / "weights" / "best.pt"
VIDEOS_DIR = PROJECT_ROOT / "videos"
OUTPUT_DIR = PROJECT_ROOT / "training_data" / "extracted_frames"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def remux_to_mp4(h264_path: Path) -> Path:
    """Remux raw .h264 to .mp4 container."""
    mp4_path = h264_path.with_suffix(".mp4")

    if mp4_path.exists():
        logger.info(f"MP4 already exists: {mp4_path.name}")
        return mp4_path

    logger.info(f"Remuxing {h264_path.name}...")
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(h264_path), "-c", "copy", str(mp4_path)],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")

    return mp4_path


def extract_frames_from_video(video_path: Path, model: YOLO,
                               random_count: int = 1,
                               detection_count: int = 5,
                               conf_threshold: float = 0.3) -> list:
    """
    Extract frames from a single video using hybrid approach.

    Args:
        video_path:       Path to video file
        model:            YOLO model for detection
        random_count:     Number of random frames to extract
        detection_count:  Max frames with detections to extract
        conf_threshold:   Confidence threshold for detections

    Returns:
        List of saved frame paths
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.error(f"Could not open: {video_path}")
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

    logger.info(f"Processing {video_path.name}: {total_frames} frames @ {fps:.1f}fps")

    # Select random frame indices
    random_indices = set(random.sample(range(total_frames), min(random_count, total_frames)))

    # Track frames with detections
    detection_candidates = []  # (frame_num, num_detections, frame)

    saved_frames = []
    frame_num = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Save random frames immediately
        if frame_num in random_indices:
            frame_name = f"{video_path.stem}_frame{frame_num:06d}_random.jpg"
            frame_path = OUTPUT_DIR / frame_name
            cv2.imwrite(str(frame_path), frame)
            saved_frames.append(frame_path)
            logger.info(f"  Saved random frame {frame_num}")

        # Run detection to find candidate frames
        # Only check every 30 frames to speed up processing
        if frame_num % 30 == 0:
            results = model.predict(frame, conf=conf_threshold, verbose=False)
            if len(results) > 0 and results[0].boxes is not None:
                num_detections = len(results[0].boxes)
                if num_detections > 0:
                    # Store frame with detection count
                    detection_candidates.append((frame_num, num_detections, frame.copy()))
                    logger.debug(f"  Frame {frame_num}: {num_detections} detections")

        frame_num += 1

    cap.release()

    # Select top N frames by detection count
    # Prioritize frames with more detections (likely more interesting/challenging)
    detection_candidates.sort(key=lambda x: x[1], reverse=True)

    for i, (fnum, num_dets, frame) in enumerate(detection_candidates[:detection_count]):
        frame_name = f"{video_path.stem}_frame{fnum:06d}_det{num_dets}.jpg"
        frame_path = OUTPUT_DIR / frame_name
        cv2.imwrite(str(frame_path), frame)
        saved_frames.append(frame_path)
        logger.info(f"  Saved detection frame {fnum} ({num_dets} detections)")

    return saved_frames


def main():
    parser = argparse.ArgumentParser(description="Extract frames from videos for training data")
    parser.add_argument("videos", nargs="*", help="Video files to process (default: all in videos/)")
    parser.add_argument("--random-per-video", type=int, default=1,
                        help="Number of random frames per video (default: 1)")
    parser.add_argument("--detections-per-video", type=int, default=5,
                        help="Max frames with detections per video (default: 5)")
    parser.add_argument("--conf", type=float, default=0.3,
                        help="Detection confidence threshold (default: 0.3)")
    args = parser.parse_args()

    # Load model
    if not MODEL_PATH.exists():
        logger.error(f"Model not found: {MODEL_PATH}")
        logger.error("Train the model first with: python src/train_model.py")
        return

    logger.info(f"Loading model: {MODEL_PATH}")
    model = YOLO(str(MODEL_PATH))

    # Find videos to process
    if args.videos:
        video_files = [Path(v) for v in args.videos]
    else:
        video_files = list(VIDEOS_DIR.glob("video_*.h264"))

    if not video_files:
        logger.error("No video files found")
        return

    logger.info(f"Found {len(video_files)} videos to process")
    logger.info(f"Extracting {args.random_per_video} random + up to {args.detections_per_video} detection frames per video")
    logger.info(f"Output directory: {OUTPUT_DIR}")
    print()

    all_saved = []

    for i, video_file in enumerate(video_files, 1):
        logger.info(f"[{i}/{len(video_files)}] Processing {video_file.name}")

        # Remux if needed
        if video_file.suffix.lower() == ".h264":
            try:
                mp4_path = remux_to_mp4(video_file)
            except Exception as e:
                logger.error(f"Failed to remux: {e}")
                continue
        else:
            mp4_path = video_file

        # Extract frames
        try:
            saved = extract_frames_from_video(
                mp4_path,
                model,
                random_count=args.random_per_video,
                detection_count=args.detections_per_video,
                conf_threshold=args.conf
            )
            all_saved.extend(saved)
            logger.info(f"  Total saved from this video: {len(saved)}")
        except Exception as e:
            logger.error(f"Failed to extract frames: {e}")
            import traceback
            logger.error(traceback.format_exc())

    print()
    print("=" * 60)
    print(f"Extraction complete")
    print(f"Total frames extracted: {len(all_saved)}")
    print(f"Saved to: {OUTPUT_DIR}")
    print()
    print("Next steps:")
    print("1. Upload frames to Roboflow for labeling:")
    print(f"   https://app.roboflow.com/")
    print("2. Label boxes in each image")
    print("3. Export as YOLOv8 format")
    print("4. Merge with existing dataset and retrain")
    print("=" * 60)


if __name__ == "__main__":
    main()
