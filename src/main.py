"""Main application entry point for PiSense"""

import logging
import time
from signal import pause

try:
    from gpiozero import Button
except ImportError:
    print("Warning: gpiozero not available. This script must run on a Raspberry Pi.")
    print("Install with: pip install gpiozero")
    exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# GPIO Configuration
PIN = 20  # GPIO 20 (Physical pin 38 on Pi 5)
BOUNCE_TIME = 0.2  # seconds to debounce


def on_pressed():
    """Callback function when GPIO pin goes HIGH"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] GPIO Pin {PIN} changed to HIGH (value: 1)")


def on_released():
    """Callback function when GPIO pin goes LOW"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] GPIO Pin {PIN} changed to LOW (value: 0)")


def main():
    """Main application function"""
    logger.info("PiSense GPIO Monitor starting...")
    logger.info(f"Monitoring GPIO pin {PIN} for state changes")

    try:
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
        logger.info("PiSense application finished")


if __name__ == "__main__":
    main()
