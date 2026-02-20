"""
Analyze a recorded video for cardboard box counting.

Usage:
    python src/analyze_video.py videos/video_20250218_120000.h264
    python src/analyze_video.py videos/video_20250218_120000.h264 --show
    python src/analyze_video.py videos/video_20250218_120000.h264 --vline 0.5
    python src/analyze_video.py videos/video_20250218_120000.h264 --hline 0.6

Arguments:
    video_path      Path to .h264 or .mp4 video file
    --vline FLOAT   Vertical counting line position as fraction of frame width
                    (default: 0.5 = middle). Use for boxes moving left-to-right.
    --hline FLOAT   Horizontal counting line position as fraction of frame height
                    (default: None). Use for boxes moving top-to-bottom.
    --conf FLOAT    Detection confidence threshold (default: 0.4)
    --show          Display annotated video while processing (requires display)
    --no-cleanup    Keep the temporary .mp4 file after processing

Note: If neither --vline nor --hline is specified, defaults to vertical line at 0.5
"""

import sys
import json
import time
import argparse
import logging
import subprocess
import tempfile
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
MODEL_PATH = PROJECT_ROOT / "models" / "trained" / "box_detector" / "weights" / "best.pt"
RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def remux_to_mp4(h264_path: Path) -> Path:
    """Remux raw .h264 to .mp4 container so OpenCV can read it."""
    mp4_path = h264_path.with_suffix(".mp4")
    logger.info(f"Remuxing {h264_path.name} -> {mp4_path.name}...")

    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(h264_path), "-c", "copy", str(mp4_path)],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")

    logger.info(f"Remux complete: {mp4_path}")
    return mp4_path


def analyze_video(video_path: Path, vline: float = None, hline: float = None,
                  conf: float = 0.4, show: bool = False) -> dict:
    """
    Run box detection and counting on a video file.

    Args:
        video_path:     Path to .mp4 video file
        vline:          Vertical counting line X position as fraction of frame width (0.0=left, 1.0=right)
        hline:          Horizontal counting line Y position as fraction of frame height (0.0=top, 1.0=bottom)
        conf:           Detection confidence threshold
        show:           Display annotated frames while processing

    Returns:
        dict with count results and metadata
    """
    import cv2
    from ultralytics import YOLO

    logger.info(f"Loading model: {MODEL_PATH}")
    model = YOLO(str(MODEL_PATH))

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    frame_width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps          = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Default to vertical line if neither specified
    if vline is None and hline is None:
        vline = 0.5

    # Determine counting line coordinates
    if vline is not None:
        line_x = int(frame_width * vline)
        line_type = "vertical"
        logger.info(f"Video: {frame_width}x{frame_height} @ {fps:.1f}fps, {total_frames} frames")
        logger.info(f"Counting line: vertical at X={line_x} ({vline*100:.0f}% from left)")
    else:
        line_y = int(frame_height * hline)
        line_type = "horizontal"
        logger.info(f"Video: {frame_width}x{frame_height} @ {fps:.1f}fps, {total_frames} frames")
        logger.info(f"Counting line: horizontal at Y={line_y} ({hline*100:.0f}% from top)")

    # Tracking state
    counted_ids = set()       # IDs that have already crossed the line
    prev_centroids = {}       # track_id -> previous Y centroid
    box_count = 0
    frame_num = 0
    start_time = time.time()

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame_num += 1

        # Run inference with ByteTrack tracking
        # persist=True is critical - maintains track IDs across frames
        results = model.track(
            frame,
            persist=True,
            conf=conf,
            tracker="bytetrack.yaml",
            verbose=False
        )

        # Process detections
        if results[0].boxes.id is not None:
            boxes   = results[0].boxes.xyxy.cpu().tolist()
            ids     = results[0].boxes.id.int().cpu().tolist()
            confs   = results[0].boxes.conf.cpu().tolist()

            for box, track_id, confidence in zip(boxes, ids, confs):
                x1, y1, x2, y2 = box
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)

                # Draw bounding box and ID on frame
                color = (0, 255, 0) if track_id not in counted_ids else (128, 128, 128)
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                cv2.putText(frame, f"ID:{track_id} {confidence:.2f}",
                           (int(x1), int(y1) - 8),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                cv2.circle(frame, (cx, cy), 4, color, -1)

                # Line crossing detection
                if line_type == "vertical":
                    # Boxes moving left-to-right: check if centroid crosses vertical line
                    if track_id in prev_centroids:
                        prev_cx = prev_centroids[track_id]
                        crossed = (prev_cx < line_x <= cx) or (prev_cx > line_x >= cx)
                        if crossed and track_id not in counted_ids:
                            counted_ids.add(track_id)
                            box_count += 1
                            logger.info(f"Frame {frame_num}: Box ID {track_id} crossed line - count: {box_count}")
                    prev_centroids[track_id] = cx
                else:
                    # Boxes moving top-to-bottom: check if centroid crosses horizontal line
                    if track_id in prev_centroids:
                        prev_cy = prev_centroids[track_id]
                        crossed = (prev_cy < line_y <= cy) or (prev_cy > line_y >= cy)
                        if crossed and track_id not in counted_ids:
                            counted_ids.add(track_id)
                            box_count += 1
                            logger.info(f"Frame {frame_num}: Box ID {track_id} crossed line - count: {box_count}")
                    prev_centroids[track_id] = cy

        # Draw counting line and count on frame
        if line_type == "vertical":
            cv2.line(frame, (line_x, 0), (line_x, frame_height), (0, 0, 255), 2)
        else:
            cv2.line(frame, (0, line_y), (frame_width, line_y), (0, 0, 255), 2)
        cv2.putText(frame, f"Boxes counted: {box_count}",
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
        cv2.putText(frame, f"Frame: {frame_num}/{total_frames}",
                   (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        if show:
            cv2.imshow("Box Counter", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                logger.info("Stopped by user")
                break

        # Progress log every 500 frames
        if frame_num % 500 == 0:
            elapsed = time.time() - start_time
            pct = (frame_num / total_frames * 100) if total_frames > 0 else 0
            fps_proc = frame_num / elapsed if elapsed > 0 else 0
            logger.info(f"Progress: {frame_num}/{total_frames} ({pct:.0f}%) "
                       f"- {fps_proc:.1f} fps processing - boxes so far: {box_count}")

    cap.release()
    if show:
        cv2.destroyAllWindows()

    elapsed = time.time() - start_time
    fps_proc = frame_num / elapsed if elapsed > 0 else 0

    logger.info(f"Analysis complete: {frame_num} frames in {elapsed:.1f}s ({fps_proc:.1f} fps)")
    logger.info(f"Total boxes counted: {box_count}")

    return {
        "video_file": str(video_path),
        "box_count": box_count,
        "frames_processed": frame_num,
        "processing_time_seconds": round(elapsed, 1),
        "processing_fps": round(fps_proc, 1),
        "line_type": line_type,
        "line_position": vline if line_type == "vertical" else hline,
        "confidence_threshold": conf,
        "model": str(MODEL_PATH),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def main():
    parser = argparse.ArgumentParser(description="Count cardboard boxes in a recorded video")
    parser.add_argument("video_path", help="Path to .h264 or .mp4 video file")
    parser.add_argument("--vline", type=float, default=None,
                        help="Vertical counting line position as fraction of frame width (0.0=left, 1.0=right)")
    parser.add_argument("--hline", type=float, default=None,
                        help="Horizontal counting line position as fraction of frame height (0.0=top, 1.0=bottom)")
    parser.add_argument("--conf", type=float, default=0.4,
                        help="Detection confidence threshold (default: 0.4)")
    parser.add_argument("--show", action="store_true",
                        help="Display annotated video while processing")
    parser.add_argument("--no-cleanup", action="store_true",
                        help="Keep temporary .mp4 file after processing")
    args = parser.parse_args()

    video_path = Path(args.video_path)
    if not video_path.exists():
        print(f"ERROR: File not found: {video_path}")
        sys.exit(1)

    if not MODEL_PATH.exists():
        print(f"ERROR: Model not found: {MODEL_PATH}")
        print("Run src/train_model.py first to train the model.")
        sys.exit(1)

    # Remux if needed
    mp4_path = None
    cleanup_mp4 = False
    if video_path.suffix.lower() == ".h264":
        mp4_path = remux_to_mp4(video_path)
        cleanup_mp4 = not args.no_cleanup
    else:
        mp4_path = video_path

    try:
        results = analyze_video(
            mp4_path,
            vline=args.vline,
            hline=args.hline,
            conf=args.conf,
            show=args.show
        )
    finally:
        # Clean up temp mp4 if we created it
        if cleanup_mp4 and mp4_path and mp4_path != video_path and mp4_path.exists():
            mp4_path.unlink()
            logger.info(f"Cleaned up temporary file: {mp4_path}")

    # Save results to JSON
    result_file = RESULTS_DIR / f"result_{Path(args.video_path).stem}.json"
    with open(result_file, "w") as f:
        json.dump(results, f, indent=2)

    print()
    print("=" * 40)
    print(f"  Boxes counted: {results['box_count']}")
    print(f"  Processed {results['frames_processed']} frames in {results['processing_time_seconds']}s")
    print(f"  Results saved: {result_file}")
    print("=" * 40)

    return results


if __name__ == "__main__":
    main()
