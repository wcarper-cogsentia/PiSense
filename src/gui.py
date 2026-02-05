"""PiSense GUI Application - Tkinter Interface"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import logging
from pathlib import Path
from PIL import Image, ImageTk

try:
    from gpiozero import Button as GPIOButton
except ImportError:
    print("Warning: gpiozero not available.")
    GPIOButton = None

try:
    from picamera2 import Picamera2
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False

# Configuration
PIN = 20  # GPIO 20 (Physical pin 38 on Pi 5)
BOUNCE_TIME = 0.1  # seconds to debounce
IMAGES_DIR = Path("images")
IMAGES_DIR.mkdir(exist_ok=True)
CAMERA_COOLDOWN = 3.0  # Minimum seconds between camera captures

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PiSenseGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PiSense - GPIO Camera Monitor")
        self.root.geometry("800x480")  # 7" touchscreen resolution

        # State variables
        self.monitoring = False
        self.camera = None
        self.gpio_button = None
        self.last_camera_capture_time = 0
        self.monitor_thread = None
        self.stop_monitoring_flag = False

        # GUI variables
        self.status_var = tk.StringVar(value="Stopped")
        self.gpio_state_var = tk.StringVar(value="LOW")
        self.capture_count_var = tk.StringVar(value="0")
        self.last_capture_var = tk.StringVar(value="None")

        self.setup_gui()

    def setup_gui(self):
        """Setup the GUI layout"""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        # Title
        title = ttk.Label(main_frame, text="PiSense Camera Monitor",
                         font=('Arial', 20, 'bold'))
        title.grid(row=0, column=0, columnspan=2, pady=10)

        # Status Frame
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        status_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)

        ttk.Label(status_frame, text="Monitoring:").grid(row=0, column=0, sticky=tk.W)
        status_label = ttk.Label(status_frame, textvariable=self.status_var,
                                font=('Arial', 12, 'bold'))
        status_label.grid(row=0, column=1, sticky=tk.W, padx=10)

        ttk.Label(status_frame, text="GPIO State:").grid(row=1, column=0, sticky=tk.W)
        self.gpio_label = ttk.Label(status_frame, textvariable=self.gpio_state_var,
                                    font=('Arial', 12, 'bold'))
        self.gpio_label.grid(row=1, column=1, sticky=tk.W, padx=10)

        ttk.Label(status_frame, text="Images Captured:").grid(row=2, column=0, sticky=tk.W)
        ttk.Label(status_frame, textvariable=self.capture_count_var,
                 font=('Arial', 12)).grid(row=2, column=1, sticky=tk.W, padx=10)

        ttk.Label(status_frame, text="Last Capture:").grid(row=3, column=0, sticky=tk.W)
        ttk.Label(status_frame, textvariable=self.last_capture_var,
                 font=('Arial', 10)).grid(row=3, column=1, sticky=tk.W, padx=10)

        # Control Buttons Frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=20)

        # Start/Stop Button
        self.start_button = tk.Button(button_frame, text="Start Monitoring",
                                      command=self.toggle_monitoring,
                                      bg="#4CAF50", fg="white",
                                      font=('Arial', 14, 'bold'),
                                      width=15, height=2)
        self.start_button.grid(row=0, column=0, padx=5)

        # Delete Images Button
        delete_button = tk.Button(button_frame, text="Delete All Images",
                                  command=self.delete_all_images,
                                  bg="#f44336", fg="white",
                                  font=('Arial', 14, 'bold'),
                                  width=15, height=2)
        delete_button.grid(row=0, column=1, padx=5)

        # Manual Capture Button
        self.capture_button = tk.Button(button_frame, text="Manual Capture",
                                       command=self.manual_capture,
                                       bg="#2196F3", fg="white",
                                       font=('Arial', 14, 'bold'),
                                       width=15, height=2,
                                       state=tk.DISABLED)
        self.capture_button.grid(row=0, column=2, padx=5)

        # Image preview area
        preview_frame = ttk.LabelFrame(main_frame, text="Last Captured Image", padding="10")
        preview_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        main_frame.rowconfigure(3, weight=1)

        self.image_label = ttk.Label(preview_frame, text="No image captured yet",
                                     relief=tk.SUNKEN, anchor=tk.CENTER)
        self.image_label.pack(fill=tk.BOTH, expand=True)

        # Update capture count on startup
        self.update_capture_count()

    def toggle_monitoring(self):
        """Start or stop GPIO monitoring"""
        if not self.monitoring:
            self.start_monitoring()
        else:
            self.stop_monitoring()

    def start_monitoring(self):
        """Start monitoring GPIO pin"""
        try:
            # Initialize camera
            if CAMERA_AVAILABLE:
                logger.info("Initializing camera...")
                cameras = Picamera2.global_camera_info()

                if cameras:
                    self.camera = Picamera2(0)
                    self.camera.configure(self.camera.create_still_configuration())
                    self.camera.start()
                    logger.info("Camera ready")
                else:
                    messagebox.showwarning("Camera Warning",
                                         "No camera detected. Running in GPIO-only mode.")

            # Initialize GPIO
            if GPIOButton:
                self.gpio_button = GPIOButton(PIN, pull_up=False, bounce_time=None)
                logger.info("GPIO initialized")
            else:
                messagebox.showerror("Error", "GPIO library not available")
                return

            # Update UI
            self.monitoring = True
            self.stop_monitoring_flag = False
            self.status_var.set("Running")
            self.start_button.config(text="Stop Monitoring", bg="#f44336")
            self.capture_button.config(state=tk.NORMAL)

            # Start monitoring thread
            self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.monitor_thread.start()

            logger.info("Monitoring started")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to start monitoring: {e}")
            logger.error(f"Failed to start monitoring: {e}")

    def stop_monitoring(self):
        """Stop monitoring GPIO pin"""
        self.monitoring = False
        self.stop_monitoring_flag = True
        self.status_var.set("Stopped")
        self.start_button.config(text="Start Monitoring", bg="#4CAF50")
        self.capture_button.config(state=tk.DISABLED)

        # Clean up camera
        if self.camera:
            try:
                self.camera.stop()
                self.camera.close()
                self.camera = None
                logger.info("Camera stopped")
            except Exception as e:
                logger.error(f"Error stopping camera: {e}")

        logger.info("Monitoring stopped")

    def monitor_loop(self):
        """Main monitoring loop (runs in separate thread)"""
        last_state = self.gpio_button.is_pressed
        last_trigger_time = 0

        while not self.stop_monitoring_flag:
            try:
                current_state = self.gpio_button.is_pressed
                current_time = time.time()

                # Update GPIO state display
                state_str = "HIGH" if current_state else "LOW"
                self.gpio_state_var.set(state_str)

                # Update GPIO label color
                if current_state:
                    self.gpio_label.config(foreground="green")
                else:
                    self.gpio_label.config(foreground="red")

                # Check for state change with debouncing
                if current_state != last_state and (current_time - last_trigger_time) >= BOUNCE_TIME:
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

                    if current_state:
                        logger.info(f"GPIO Pin {PIN} changed to HIGH")

                        # Trigger camera if enough time has passed
                        if self.camera:
                            time_since_last_capture = current_time - self.last_camera_capture_time
                            if time_since_last_capture >= CAMERA_COOLDOWN:
                                self.capture_image()
                                self.last_camera_capture_time = current_time
                            else:
                                remaining = CAMERA_COOLDOWN - time_since_last_capture
                                logger.info(f"Camera on cooldown - {remaining:.1f}s remaining")
                    else:
                        logger.info(f"GPIO Pin {PIN} changed to LOW")

                    last_state = current_state
                    last_trigger_time = current_time

                time.sleep(0.001)  # 1ms polling interval

            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                break

    def capture_image(self):
        """Capture image from camera"""
        if not self.camera:
            return

        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = IMAGES_DIR / f"capture_{timestamp}.jpg"

            logger.info(f"Capturing image: {filename}")
            self.camera.capture_file(str(filename))

            # Rotate image 90 degrees clockwise
            img = Image.open(filename)
            img_rotated = img.rotate(-90, expand=True)
            img_rotated.save(filename)

            # Update UI
            self.last_capture_var.set(filename.name)
            self.update_capture_count()
            self.display_image(filename)

            logger.info(f"Image saved: {filename}")

        except Exception as e:
            logger.error(f"Failed to capture image: {e}")

    def manual_capture(self):
        """Manually trigger a camera capture"""
        if self.camera and self.monitoring:
            self.capture_image()
            self.last_camera_capture_time = time.time()

    def display_image(self, image_path):
        """Display captured image in preview area"""
        try:
            img = Image.open(image_path)

            # Resize to fit preview area (maintain aspect ratio)
            max_width = 760
            max_height = 200
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(img)

            # Update label
            self.image_label.config(image=photo, text="")
            self.image_label.image = photo  # Keep a reference

        except Exception as e:
            logger.error(f"Failed to display image: {e}")

    def update_capture_count(self):
        """Update the count of captured images"""
        try:
            image_files = list(IMAGES_DIR.glob("capture_*.jpg"))
            count = len(image_files)
            self.capture_count_var.set(str(count))
        except Exception as e:
            logger.error(f"Failed to update capture count: {e}")

    def delete_all_images(self):
        """Delete all images in the images directory"""
        result = messagebox.askyesno("Confirm Delete",
                                     "Are you sure you want to delete all captured images?")
        if result:
            try:
                image_files = list(IMAGES_DIR.glob("capture_*.jpg"))
                count = 0
                for img_file in image_files:
                    img_file.unlink()
                    count += 1

                # Clear preview
                self.image_label.config(image="", text="No image captured yet")
                self.last_capture_var.set("None")
                self.update_capture_count()

                messagebox.showinfo("Success", f"Deleted {count} images")
                logger.info(f"Deleted {count} images")

            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete images: {e}")
                logger.error(f"Failed to delete images: {e}")

    def on_closing(self):
        """Handle window closing"""
        if self.monitoring:
            self.stop_monitoring()
        self.root.destroy()


def main():
    """Main entry point for GUI application"""
    root = tk.Tk()
    app = PiSenseGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
