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
        """Setup the GUI layout - Horizontal layout for limited vertical space"""
        # Main container with minimal padding
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)  # Image preview gets most space

        # Left Panel - Controls and Status
        left_panel = ttk.Frame(main_frame)
        left_panel.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5)

        # Title
        title = ttk.Label(left_panel, text="PiSense", font=('Arial', 16, 'bold'))
        title.pack(pady=5)

        # Status Frame - Compact
        status_frame = ttk.LabelFrame(left_panel, text="Status", padding="5")
        status_frame.pack(fill=tk.X, pady=5)

        # Status grid - more compact
        ttk.Label(status_frame, text="Status:", font=('Arial', 9)).grid(row=0, column=0, sticky=tk.W)
        status_label = ttk.Label(status_frame, textvariable=self.status_var,
                                font=('Arial', 9, 'bold'))
        status_label.grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(status_frame, text="GPIO:", font=('Arial', 9)).grid(row=1, column=0, sticky=tk.W)
        self.gpio_label = ttk.Label(status_frame, textvariable=self.gpio_state_var,
                                    font=('Arial', 9, 'bold'))
        self.gpio_label.grid(row=1, column=1, sticky=tk.W, padx=5)

        ttk.Label(status_frame, text="Count:", font=('Arial', 9)).grid(row=2, column=0, sticky=tk.W)
        ttk.Label(status_frame, textvariable=self.capture_count_var,
                 font=('Arial', 9)).grid(row=2, column=1, sticky=tk.W, padx=5)

        # Settings Frame - Adjustable parameters
        settings_frame = ttk.LabelFrame(left_panel, text="Settings", padding="5")
        settings_frame.pack(fill=tk.X, pady=5)

        # Debounce time setting (in milliseconds)
        ttk.Label(settings_frame, text="Debounce (ms):", font=('Arial', 9)).grid(row=0, column=0, sticky=tk.W, pady=3)
        self.debounce_var = tk.IntVar(value=int(BOUNCE_TIME * 1000))

        debounce_control = ttk.Frame(settings_frame)
        debounce_control.grid(row=0, column=1, sticky=tk.W, padx=5, pady=3)

        tk.Button(debounce_control, text="-", font=('Arial', 14, 'bold'),
                 width=2, command=lambda: self.adjust_debounce(-10)).pack(side=tk.LEFT, padx=1)
        ttk.Label(debounce_control, textvariable=self.debounce_var,
                 font=('Arial', 11, 'bold'), width=5, anchor=tk.CENTER).pack(side=tk.LEFT, padx=3)
        tk.Button(debounce_control, text="+", font=('Arial', 14, 'bold'),
                 width=2, command=lambda: self.adjust_debounce(10)).pack(side=tk.LEFT, padx=1)

        # Camera cooldown setting (in seconds)
        ttk.Label(settings_frame, text="Cooldown (s):", font=('Arial', 9)).grid(row=1, column=0, sticky=tk.W, pady=3)
        self.cooldown_var = tk.DoubleVar(value=CAMERA_COOLDOWN)

        cooldown_control = ttk.Frame(settings_frame)
        cooldown_control.grid(row=1, column=1, sticky=tk.W, padx=5, pady=3)

        tk.Button(cooldown_control, text="-", font=('Arial', 14, 'bold'),
                 width=2, command=lambda: self.adjust_cooldown(-0.5)).pack(side=tk.LEFT, padx=1)
        ttk.Label(cooldown_control, textvariable=self.cooldown_var,
                 font=('Arial', 11, 'bold'), width=5, anchor=tk.CENTER).pack(side=tk.LEFT, padx=3)
        tk.Button(cooldown_control, text="+", font=('Arial', 14, 'bold'),
                 width=2, command=lambda: self.adjust_cooldown(0.5)).pack(side=tk.LEFT, padx=1)

        # Control Buttons Frame - Vertical stack
        button_frame = ttk.Frame(left_panel)
        button_frame.pack(fill=tk.X, pady=5)

        # Start/Stop Button
        self.start_button = tk.Button(button_frame, text="Start",
                                      command=self.toggle_monitoring,
                                      bg="#4CAF50", fg="white",
                                      font=('Arial', 12, 'bold'),
                                      height=2)
        self.start_button.pack(fill=tk.X, pady=2)

        # Manual Capture Button
        self.capture_button = tk.Button(button_frame, text="Capture",
                                       command=self.manual_capture,
                                       bg="#2196F3", fg="white",
                                       font=('Arial', 12, 'bold'),
                                       height=2,
                                       state=tk.DISABLED)
        self.capture_button.pack(fill=tk.X, pady=2)

        # Delete Images Button
        delete_button = tk.Button(button_frame, text="Delete All",
                                  command=self.delete_all_images,
                                  bg="#f44336", fg="white",
                                  font=('Arial', 12, 'bold'),
                                  height=2)
        delete_button.pack(fill=tk.X, pady=2)

        # Right Panel - Image preview (takes most of the space)
        preview_frame = ttk.LabelFrame(main_frame, text="Camera View", padding="5")
        preview_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5)
        main_frame.rowconfigure(0, weight=1)

        self.image_label = ttk.Label(preview_frame, text="No image",
                                     relief=tk.SUNKEN, anchor=tk.CENTER,
                                     background="black", foreground="white")
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
            self.start_button.config(text="Stop", bg="#f44336")
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
        self.start_button.config(text="Start", bg="#4CAF50")
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

                # Get current settings from UI
                debounce_time = self.debounce_var.get() / 1000.0  # Convert ms to seconds
                camera_cooldown = self.cooldown_var.get()

                # Check for state change with debouncing
                if current_state != last_state and (current_time - last_trigger_time) >= debounce_time:
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

                    if current_state:
                        logger.info(f"GPIO Pin {PIN} changed to HIGH")

                        # Trigger camera if enough time has passed
                        if self.camera:
                            time_since_last_capture = current_time - self.last_camera_capture_time
                            if time_since_last_capture >= camera_cooldown:
                                self.capture_image()
                                self.last_camera_capture_time = current_time
                            else:
                                remaining = camera_cooldown - time_since_last_capture
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

            # Update UI from main thread using after()
            self.root.after(0, lambda: self.last_capture_var.set(filename.name))
            self.root.after(0, self.update_capture_count)
            self.root.after(0, lambda: self.display_image(filename))

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
            # Larger area since we have horizontal layout
            max_width = 580
            max_height = 440
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(img)

            # Update label
            self.image_label.config(image=photo, text="", background="black")
            self.image_label.image = photo  # Keep a reference

        except Exception as e:
            logger.error(f"Failed to display image: {e}")

    def adjust_debounce(self, delta):
        """Adjust debounce value with bounds checking"""
        current = self.debounce_var.get()
        new_value = max(10, min(1000, current + delta))
        self.debounce_var.set(new_value)

    def adjust_cooldown(self, delta):
        """Adjust cooldown value with bounds checking"""
        current = self.cooldown_var.get()
        new_value = max(0.5, min(30.0, current + delta))
        self.cooldown_var.set(round(new_value, 1))

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
