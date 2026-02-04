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
BOUNCE_TIME = 0.2  # seconds to debounce

# Camera Configuration
IMAGES_DIR = Path("images")
IMAGES_DIR.mkdir(exist_ok=True)

# Global camera instance
camera = None


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
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] GPIO Pin {PIN} changed to HIGH (value: 1)")

    # Capture image on state change
    image_path = capture_image()
    if image_path:
        print(f"View image at: {image_path}")


def on_released():
    """Callback function when GPIO pin goes LOW"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] GPIO Pin {PIN} changed to LOW (value: 0)")

    # Optionally capture on release as well
    # Uncomment the lines below if you want to capture on both transitions
    # image_path = capture_image()
    # if image_path:
    #     print(f"View image at: {image_path}")


def main():
    """Main application function"""
    global camera

    logger.info("PiSense GPIO Monitor starting...")
    logger.info(f"Monitoring GPIO pin {PIN} for state changes")

    try:
        # Initialize camera if available
        if CAMERA_AVAILABLE:
            logger.info("Initializing camera...")
            camera = Picamera2()
            camera.configure(camera.create_still_configuration())
            camera.start()
            logger.info("Camera ready")
        else:
            logger.warning("Camera not available - running in GPIO-only mode")

        # Set up GPIO pin as input with pull-down resistor
        # Change pull_up=True if you're using a pull-up configuration
        button = Button(PIN, pull_up=False, bounce_time=BOUNCE_TIME)

        # Read and print initial state
        initial_state = button.is_pressed
        initial_state_str = "HIGH" if initial_state else "LOW"
        print(f"Initial state of GPIO pin {PIN}: {initial_state_str} (value: {int(initial_state)})")
        print(f"Listening for state changes... (Press Ctrl+C to exit)")
        print("-" * 60)

        # Set up event handlers
        button.when_pressed = on_pressed
        button.when_released = on_released

        # Keep the program running
        pause()

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
