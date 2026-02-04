"""Main application entry point for PiSense"""

import logging
import time
try:
    import RPi.GPIO as GPIO
except ImportError:
    print("Warning: RPi.GPIO not available. This script must run on a Raspberry Pi.")
    print("For testing purposes, install RPi.GPIO or use a GPIO simulator.")
    exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# GPIO Configuration
PIN = 20
BOUNCE_TIME = 200  # milliseconds to debounce


def gpio_callback(channel):
    """Callback function when GPIO pin state changes"""
    state = GPIO.input(channel)
    state_str = "HIGH" if state else "LOW"
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] GPIO Pin {channel} changed to {state_str} (value: {state})")


def main():
    """Main application function"""
    logger.info("PiSense GPIO Monitor starting...")
    logger.info(f"Monitoring GPIO pin {PIN} for state changes")

    try:
        # Set up GPIO mode (BCM numbering)
        GPIO.setmode(GPIO.BCM)

        # Set up pin as input with pull-down resistor
        # Change to GPIO.PUD_UP if you're using a pull-up configuration
        GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

        # Read and print initial state
        initial_state = GPIO.input(PIN)
        initial_state_str = "HIGH" if initial_state else "LOW"
        print(f"Initial state of GPIO pin {PIN}: {initial_state_str} (value: {initial_state})")
        print(f"Listening for state changes... (Press Ctrl+C to exit)")
        print("-" * 60)

        # Add event detection for both rising and falling edges
        GPIO.add_event_detect(PIN, GPIO.BOTH, callback=gpio_callback, bouncetime=BOUNCE_TIME)

        # Keep the program running
        while True:
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n" + "-" * 60)
        logger.info("Program interrupted by user")

    except Exception as e:
        logger.error(f"An error occurred: {e}")

    finally:
        # Clean up GPIO on exit
        GPIO.cleanup()
        logger.info("GPIO cleanup completed")
        logger.info("PiSense application finished")


if __name__ == "__main__":
    main()
