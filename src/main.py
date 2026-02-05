"""Main application entry point for PiSense"""

import logging
import time
from pathlib import Path
from signal import pause

try:
    from gpiozero import Button
except ImportError:
    print("Warning: gpiozero not available. This script must run on a Raspberry Pi.")
    print("Install with: pip install gpiozero")
    exit(1)

try:
    from picamera2 import Picamera2
    CAMERA_AVAILABLE = True
except ImportError:
    print("Warning: picamera2 not available. Camera functionality will be disabled.")
    CAMERA_AVAILABLE = False

try:
    from PIL import Image
    import subprocess
    DISPLAY_AVAILABLE = True
except ImportError:
    print("Warning: PIL not available. Image display will be disabled.")
    DISPLAY_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# GPIO Configuration
PIN = 20  # GPIO 20 (Physical pin 38 on Pi 5)
BOUNCE_TIME = 0.1  # seconds to debounce (50ms)

# Camera Configuration
IMAGES_DIR = Path("images")
IMAGES_DIR.mkdir(exist_ok=True)
CAMERA_COOLDOWN = 3.0  # Minimum seconds between camera captures

# Global camera instance
camera = None
last_camera_capture_time = 0


def display_image(image_path):
    """Display an image using the default image viewer"""
    if not DISPLAY_AVAILABLE:
        logger.warning("Display not available")
        return

    try:
        # Open image with PIL and show it
        img = Image.open(image_path)

        # Print image info
        print(f"Image size: {img.size[0]}x{img.size[1]} pixels")

        # Try to display using system image viewer
        # This works if running with X11/Wayland display
        try:
            subprocess.Popen(['feh', str(image_path)],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            print(f"Displaying image with feh")
        except FileNotFoundError:
            # feh not installed, try other viewers
            try:
                subprocess.Popen(['display', str(image_path)],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
                print(f"Displaying image with ImageMagick display")
            except FileNotFoundError:
                print(f"Image viewer not found. View manually at: {image_path}")

    except Exception as e:
        logger.error(f"Failed to display image: {e}")


def capture_image():
    """Capture an image from the camera"""
    if camera is None:
        logger.warning("Camera not initialized")
        return None

    try:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = IMAGES_DIR / f"capture_{timestamp}.jpg"

        logger.info(f"Capturing image: {filename}")
        camera.capture_file(str(filename))

        print(f"Image saved: {filename}")

        # Display the captured image
        display_image(filename)

        return filename

    except Exception as e:
        logger.error(f"Failed to capture image: {e}")
        return None


def on_pressed():
    """Callback function when GPIO pin goes HIGH"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Include milliseconds
    print(f"[{timestamp}] GPIO Pin {PIN} changed to HIGH (value: 1)")

    # Camera capture temporarily disabled
    # image_path = capture_image()
    # if image_path:
    #     print(f"View image at: {image_path}")


def on_released():
    """Callback function when GPIO pin goes LOW"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Include milliseconds
    print(f"[{timestamp}] GPIO Pin {PIN} changed to LOW (value: 0)")

    # Optionally capture on release as well
    # Uncomment the lines below if you want to capture on both transitions
    # image_path = capture_image()
    # if image_path:
    #     print(f"View image at: {image_path}")


def main():
    """Main application function"""
    global camera, last_camera_capture_time

    logger.info("PiSense GPIO Monitor starting...")
    logger.info(f"Monitoring GPIO pin {PIN} for state changes")

    try:
        # Initialize camera if available
        if CAMERA_AVAILABLE:
            try:
                logger.info("Detecting cameras...")
                cameras = Picamera2.global_camera_info()

                if not cameras:
                    logger.warning("No cameras detected - running in GPIO-only mode")
                    logger.info("Check: 1) Camera is connected, 2) Cable is seated properly")
                else:
                    logger.info(f"Found {len(cameras)} camera(s)")
                    for idx, cam_info in enumerate(cameras):
                        logger.info(f"  Camera {idx}: {cam_info}")

                    logger.info("Initializing camera 0...")
                    camera = Picamera2(0)
                    camera.configure(camera.create_still_configuration())
                    camera.start()
                    logger.info("Camera ready")

            except Exception as e:
                logger.error(f"Failed to initialize camera: {e}")
                logger.warning("Continuing in GPIO-only mode")
                camera = None
        else:
            logger.warning("picamera2 not available - running in GPIO-only mode")

        # Set up GPIO pin as input with pull-down resistor
        # Using minimal bounce time, we'll handle debouncing manually
        button = Button(PIN, pull_up=False, bounce_time=None)

        # Track last state and last trigger time for manual debouncing
        last_state = button.is_pressed
        last_trigger_time = 0
        min_trigger_interval = BOUNCE_TIME  # Minimum time between triggers

        # Read and print initial state
        initial_state_str = "HIGH" if last_state else "LOW"
        print(f"Initial state of GPIO pin {PIN}: {initial_state_str} (value: {int(last_state)})")
        print(f"Listening for state changes... (Press Ctrl+C to exit)")
        print(f"Debounce time: {BOUNCE_TIME * 1000}ms")
        print("-" * 60)

        # Manual polling loop for better control
        while True:
            current_state = button.is_pressed
            current_time = time.time()

            # Check if state has changed AND enough time has passed since last trigger
            if current_state != last_state and (current_time - last_trigger_time) >= min_trigger_interval:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

                if current_state:
                    print(f"[{timestamp}] GPIO Pin {PIN} changed to HIGH (value: 1)")

                    # Trigger camera if enough time has passed since last capture
                    if camera is not None:
                        time_since_last_capture = current_time - last_camera_capture_time
                        if time_since_last_capture >= CAMERA_COOLDOWN:
                            image_path = capture_image()
                            if image_path:
                                print(f"View image at: {image_path}")
                                last_camera_capture_time = current_time
                        else:
                            remaining_cooldown = CAMERA_COOLDOWN - time_since_last_capture
                            print(f"Camera on cooldown - {remaining_cooldown:.1f}s remaining")
                else:
                    print(f"[{timestamp}] GPIO Pin {PIN} changed to LOW (value: 0)")

                last_state = current_state
                last_trigger_time = current_time

            time.sleep(0.001)  # 1ms polling interval

    except KeyboardInterrupt:
        print("\n" + "-" * 60)
        logger.info("Program interrupted by user")

    except Exception as e:
        logger.error(f"An error occurred: {e}")

    finally:
        # Clean up camera
        if camera is not None:
            logger.info("Stopping camera...")
            camera.stop()
            camera.close()
        logger.info("PiSense application finished")


if __name__ == "__main__":
    main()
