"""PiSense GUI Application - Tkinter Interface"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import logging
from pathlib import Path
from PIL import Image, ImageTk
from queue import Queue
import numpy as np

try:
    from gpiozero import Button as GPIOButton
except ImportError:
    print("Warning: gpiozero not available.")
    GPIOButton = None

try:
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FileOutput
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False

# Configuration
PIN = 20  # GPIO 20 (Physical pin 38 on Pi 5)
BOUNCE_TIME = 0.1  # seconds to debounce
VIDEOS_DIR = Path("videos")
VIDEOS_DIR.mkdir(exist_ok=True)
RECORDING_DURATION = 60.0  # Base recording duration in seconds (1 minute)
MAX_RECORDING_DURATION = 300.0  # Maximum recording duration in seconds (5 minutes)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PiSenseGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PiSense - GPIO Video Monitor")
        self.root.geometry("800x480")  # 7" touchscreen resolution

        # State variables
        self.monitoring = False
        self.camera = None
        self.gpio_button = None
        self.monitor_thread = None
        self.stop_monitoring_flag = False

        # Video recording state
        self.recording = False
        self.recording_start_time = 0
        self.recording_end_time = 0
        self.trigger_queue = Queue()
        self.current_video_file = None
        self.encoder = None
        self.preview_update_thread = None

        # GUI variables
        self.status_var = tk.StringVar(value="Stopped")
        self.gpio_state_var = tk.StringVar(value="LOW")
        self.capture_count_var = tk.StringVar(value="0")
        self.recording_time_var = tk.StringVar(value="0:00")
        self.queued_triggers_var = tk.StringVar(value="0")

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
        status_frame = ttk.LabelFrame(left_panel, text="Status", padding="3")
        status_frame.pack(fill=tk.X, pady=3)

        # Status grid - more compact
        ttk.Label(status_frame, text="Status:", font=('Arial', 9)).grid(row=0, column=0, sticky=tk.W)
        status_label = ttk.Label(status_frame, textvariable=self.status_var,
                                font=('Arial', 9, 'bold'))
        status_label.grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(status_frame, text="GPIO:", font=('Arial', 9)).grid(row=1, column=0, sticky=tk.W)
        self.gpio_label = ttk.Label(status_frame, textvariable=self.gpio_state_var,
                                    font=('Arial', 9, 'bold'))
        self.gpio_label.grid(row=1, column=1, sticky=tk.W, padx=5)

        ttk.Label(status_frame, text="Videos:", font=('Arial', 9)).grid(row=2, column=0, sticky=tk.W)
        ttk.Label(status_frame, textvariable=self.capture_count_var,
                 font=('Arial', 9)).grid(row=2, column=1, sticky=tk.W, padx=5)

        ttk.Label(status_frame, text="Recording:", font=('Arial', 9)).grid(row=3, column=0, sticky=tk.W)
        self.recording_label = ttk.Label(status_frame, textvariable=self.recording_time_var,
                                        font=('Arial', 9, 'bold'), foreground="red")
        self.recording_label.grid(row=3, column=1, sticky=tk.W, padx=5)

        ttk.Label(status_frame, text="Queued:", font=('Arial', 9)).grid(row=4, column=0, sticky=tk.W)
        ttk.Label(status_frame, textvariable=self.queued_triggers_var,
                 font=('Arial', 9)).grid(row=4, column=1, sticky=tk.W, padx=5)

        # Settings Frame - Adjustable parameters
        settings_frame = ttk.LabelFrame(left_panel, text="Settings", padding="3")
        settings_frame.pack(fill=tk.X, pady=3)

        # Debounce time setting (in milliseconds)
        ttk.Label(settings_frame, text="Debounce (ms):", font=('Arial', 9)).grid(row=0, column=0, sticky=tk.W, pady=1)
        self.debounce_var = tk.IntVar(value=int(BOUNCE_TIME * 1000))

        debounce_control = ttk.Frame(settings_frame)
        debounce_control.grid(row=0, column=1, sticky=tk.W, padx=5, pady=1)

        tk.Button(debounce_control, text="-", font=('Arial', 14, 'bold'),
                 width=2, command=lambda: self.adjust_debounce(-10)).pack(side=tk.LEFT, padx=1)
        ttk.Label(debounce_control, textvariable=self.debounce_var,
                 font=('Arial', 11, 'bold'), width=5, anchor=tk.CENTER).pack(side=tk.LEFT, padx=3)
        tk.Button(debounce_control, text="+", font=('Arial', 14, 'bold'),
                 width=2, command=lambda: self.adjust_debounce(10)).pack(side=tk.LEFT, padx=1)

        # Max recording time setting (in minutes)
        ttk.Label(settings_frame, text="Max Rec (min):", font=('Arial', 9)).grid(row=1, column=0, sticky=tk.W, pady=1)
        self.max_recording_var = tk.IntVar(value=int(MAX_RECORDING_DURATION / 60))

        max_rec_control = ttk.Frame(settings_frame)
        max_rec_control.grid(row=1, column=1, sticky=tk.W, padx=5, pady=1)

        tk.Button(max_rec_control, text="-", font=('Arial', 14, 'bold'),
                 width=2, command=lambda: self.adjust_max_recording(-1)).pack(side=tk.LEFT, padx=1)
        ttk.Label(max_rec_control, textvariable=self.max_recording_var,
                 font=('Arial', 11, 'bold'), width=5, anchor=tk.CENTER).pack(side=tk.LEFT, padx=3)
        tk.Button(max_rec_control, text="+", font=('Arial', 14, 'bold'),
                 width=2, command=lambda: self.adjust_max_recording(1)).pack(side=tk.LEFT, padx=1)

        # Control Buttons Frame - Vertical stack
        button_frame = ttk.Frame(left_panel)
        button_frame.pack(fill=tk.X, pady=3)

        # Start/Stop Button
        self.start_button = tk.Button(button_frame, text="Start",
                                      command=self.toggle_monitoring,
                                      bg="#4CAF50", fg="white",
                                      font=('Arial', 11, 'bold'),
                                      height=2)
        self.start_button.pack(fill=tk.X, pady=1)

        # Manual Record Button
        self.capture_button = tk.Button(button_frame, text="Record Video",
                                       command=self.manual_record,
                                       bg="#2196F3", fg="white",
                                       font=('Arial', 11, 'bold'),
                                       height=2,
                                       state=tk.DISABLED)
        self.capture_button.pack(fill=tk.X, pady=1)

        # Delete All Videos/Images Button
        delete_button = tk.Button(button_frame, text="Delete All",
                                  command=self.delete_all_files,
                                  bg="#f44336", fg="white",
                                  font=('Arial', 11, 'bold'),
                                  height=2)
        delete_button.pack(fill=tk.X, pady=1)

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
                    # Configure for 640x640 video (YOLO optimized)
                    # Let picamera2 choose appropriate formats
                    video_config = self.camera.create_video_configuration(
                        main={"size": (640, 640)},
                        lores={"size": (640, 480)},
                        encode="main",
                        buffer_count=4
                    )
                    self.camera.configure(video_config)
                    self.camera.start()
                    logger.info("Camera ready for video recording (640x640)")
                    logger.info(f"Camera configuration: {self.camera.camera_configuration()}")

                    # Log the actual stream configurations
                    config = self.camera.camera_configuration()
                    logger.info(f"Main stream config: {config.get('main', {})}")
                    logger.info(f"Lores stream config: {config.get('lores', {})}")
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

            # Clear trigger queue
            while not self.trigger_queue.empty():
                self.trigger_queue.get()

            # Start monitoring thread
            self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.monitor_thread.start()

            # Start preview update thread
            self.preview_update_thread = threading.Thread(target=self.update_preview_loop, daemon=True)
            self.preview_update_thread.start()

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

        # Stop any ongoing recording
        if self.recording:
            self.stop_recording()

        # Clean up GPIO
        if self.gpio_button:
            try:
                self.gpio_button.close()
                self.gpio_button = None
                logger.info("GPIO released")
            except Exception as e:
                logger.error(f"Error releasing GPIO: {e}")

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
        if not self.gpio_button:
            return
        last_state = self.gpio_button.is_pressed
        last_trigger_time = 0

        while not self.stop_monitoring_flag:
            try:
                if not self.gpio_button:
                    break
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

                # Check for state change with debouncing
                if current_state != last_state and (current_time - last_trigger_time) >= debounce_time:
                    if current_state:
                        logger.info(f"GPIO Pin {PIN} changed to HIGH - Trigger detected")

                        # Add trigger to queue
                        if self.camera:
                            self.trigger_queue.put(current_time)
                            queue_size = self.trigger_queue.qsize()
                            self.root.after(0, lambda size=queue_size: self.queued_triggers_var.set(str(size)))
                            logger.info(f"Trigger queued - queue size: {queue_size}")

                            # Start recording if not already recording
                            if not self.recording:
                                threading.Thread(target=self.start_recording, daemon=True).start()
                            else:
                                # Extend recording time
                                self.extend_recording()
                    else:
                        logger.info(f"GPIO Pin {PIN} changed to LOW")

                    last_state = current_state
                    last_trigger_time = current_time

                # Update recording timer and check if should stop
                if self.recording:
                    elapsed = current_time - self.recording_start_time
                    remaining = max(0, self.recording_end_time - current_time)
                    mins = int(elapsed // 60)
                    secs = int(elapsed % 60)
                    self.root.after(0, lambda m=mins, s=secs: self.recording_time_var.set(f"{m}:{s:02d}"))

                    # Debug logging every 10 seconds
                    if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                        logger.debug(f"Recording status - elapsed: {elapsed:.1f}s, end_time: {self.recording_end_time}, current_time: {current_time}, remaining: {remaining:.1f}s")

                    # Check if recording should stop
                    if current_time >= self.recording_end_time:
                        logger.info(f"Recording time expired - stopping (elapsed: {elapsed:.1f}s, end_time: {self.recording_end_time}, current_time: {current_time})")
                        self.stop_recording()

                time.sleep(0.01)  # 10ms polling interval

            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                break

    def start_recording(self):
        """Start video recording"""
        if not self.camera or self.recording:
            return

        try:
            # Process queue - get first trigger
            if not self.trigger_queue.empty():
                self.trigger_queue.get()
                queue_size = self.trigger_queue.qsize()
                self.root.after(0, lambda size=queue_size: self.queued_triggers_var.set(str(size)))
                logger.info(f"Processing trigger from queue - remaining: {queue_size}")

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            self.current_video_file = VIDEOS_DIR / f"video_{timestamp}.h264"

            logger.info(f"Starting video recording: {self.current_video_file}")

            # Configure encoder
            self.encoder = H264Encoder(bitrate=10000000)

            # Start recording
            self.camera.start_recording(self.encoder, str(self.current_video_file))

            # Set recording state
            self.recording = True
            self.recording_start_time = time.time()
            self.recording_end_time = self.recording_start_time + RECORDING_DURATION

            logger.info(f"Recording started - start_time: {self.recording_start_time:.3f}, end_time: {self.recording_end_time:.3f}, duration: {RECORDING_DURATION}s")
            logger.info(f"Recording will end at: {time.strftime('%H:%M:%S', time.localtime(self.recording_end_time))}")

        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.recording = False

    def extend_recording(self):
        """Extend recording time by processing trigger from queue"""
        if not self.recording:
            return

        try:
            # Process trigger from queue
            if not self.trigger_queue.empty():
                self.trigger_queue.get()
                queue_size = self.trigger_queue.qsize()
                self.root.after(0, lambda size=queue_size: self.queued_triggers_var.set(str(size)))
                logger.info(f"Processing trigger from queue - remaining: {queue_size}")

            # Add 1 minute to recording time
            new_end_time = self.recording_end_time + RECORDING_DURATION

            # Check max recording duration
            max_duration = self.max_recording_var.get() * 60  # Convert minutes to seconds
            max_end_time = self.recording_start_time + max_duration

            if new_end_time <= max_end_time:
                self.recording_end_time = new_end_time
                elapsed = time.time() - self.recording_start_time
                logger.info(f"Recording extended - new duration: {self.recording_end_time - self.recording_start_time:.1f}s (elapsed: {elapsed:.1f}s)")
            else:
                self.recording_end_time = max_end_time
                logger.info(f"Recording extended to maximum duration: {max_duration}s")

        except Exception as e:
            logger.error(f"Failed to extend recording: {e}")

    def stop_recording(self):
        """Stop video recording"""
        if not self.recording:
            logger.warning("stop_recording called but recording is False")
            return

        try:
            logger.info(f"Stopping video recording - file: {self.current_video_file}")

            # Stop the camera recording
            if self.camera:
                self.camera.stop_recording()
                logger.info("Camera stop_recording() completed")
            else:
                logger.error("Camera is None when trying to stop recording")

            # Reset recording state
            self.recording = False
            self.recording_start_time = 0
            self.recording_end_time = 0

            # Check if there are more triggers to process
            queue_size = self.trigger_queue.qsize()

            self.root.after(0, lambda: self.recording_time_var.set("0:00"))
            self.root.after(0, lambda size=queue_size: self.queued_triggers_var.set(str(size)))
            self.root.after(0, self.update_capture_count)

            logger.info(f"Recording saved: {self.current_video_file}")

            # Small delay before starting next recording
            time.sleep(0.5)

            # If there are more triggers in queue, start a new recording
            if queue_size > 0:
                logger.info(f"Starting new recording for queued triggers ({queue_size} remaining)")
                threading.Thread(target=self.start_recording, daemon=True).start()

        except Exception as e:
            logger.error(f"Failed to stop recording: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Force reset recording state on error
            self.recording = False
            self.recording_start_time = 0
            self.recording_end_time = 0

    def manual_record(self):
        """Manually trigger a 1-minute video recording"""
        if self.camera and self.monitoring:
            current_time = time.time()
            self.trigger_queue.put(current_time)
            queue_size = self.trigger_queue.qsize()
            self.root.after(0, lambda size=queue_size: self.queued_triggers_var.set(str(size)))
            logger.info(f"Manual trigger - queue size: {queue_size}")

            if not self.recording:
                threading.Thread(target=self.start_recording, daemon=True).start()
            else:
                self.extend_recording()

    def update_preview_loop(self):
        """Update live camera preview (runs in separate thread)"""
        import cv2  # Import here to avoid issues if not available

        while not self.stop_monitoring_flag:
            try:
                if self.camera and self.monitoring:
                    # Capture preview frame from lores stream
                    frame = self.camera.capture_array("lores")

                    # Debug: log frame info on first capture
                    if not hasattr(self, '_frame_info_logged'):
                        logger.info(f"Frame shape: {frame.shape}, dtype: {frame.dtype}")
                        self._frame_info_logged = True

                    # Convert YUV420 to RGB
                    # YUV420 has shape (height * 1.5, width) where extra 0.5 is chroma
                    if len(frame.shape) == 2:
                        # YUV420 is stored as a 2D array, need to convert to RGB
                        height = 480
                        width = 640
                        # Reshape and convert YUV420 to RGB
                        yuv = frame.reshape((int(height * 1.5), width))
                        rgb_frame = cv2.cvtColor(yuv, cv2.COLOR_YUV2RGB_I420)
                        img = Image.fromarray(rgb_frame)
                    elif len(frame.shape) == 3 and frame.shape[2] == 3:
                        # Already RGB format
                        img = Image.fromarray(frame, mode='RGB')
                    else:
                        # Unknown format, try to use as-is
                        logger.warning(f"Unknown frame format: {frame.shape}")
                        img = Image.fromarray(frame)

                    # Resize to fit preview area (no rotation needed - camera is correctly positioned)
                    max_width = 580
                    max_height = 440
                    img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

                    # Add recording indicator if recording
                    if self.recording:
                        # Add red border or dot to indicate recording
                        from PIL import ImageDraw
                        draw = ImageDraw.Draw(img)
                        # Draw red circle in top-right corner
                        draw.ellipse([img.width - 30, 10, img.width - 10, 30], fill='red')

                    # Update preview on main thread
                    self.root.after(0, lambda i=img: self.display_preview(i))

                time.sleep(0.1)  # Update preview at ~10 fps

            except Exception as e:
                logger.error(f"Error in preview loop: {e}")
                import traceback
                logger.error(traceback.format_exc())
                time.sleep(0.5)

    def display_preview(self, img):
        """Display preview image in GUI (must be called from main thread)"""
        try:
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(img)

            # Update label
            self.image_label.config(image=photo, text="", background="black")
            self.image_label.image = photo  # Keep a reference

        except Exception as e:
            logger.error(f"Failed to display preview: {e}")

    def adjust_debounce(self, delta):
        """Adjust debounce value with bounds checking"""
        current = self.debounce_var.get()
        new_value = max(10, min(1000, current + delta))
        self.debounce_var.set(new_value)

    def adjust_max_recording(self, delta):
        """Adjust max recording time with bounds checking"""
        current = self.max_recording_var.get()
        new_value = max(1, min(30, current + delta))  # 1-30 minutes
        self.max_recording_var.set(new_value)

    def update_capture_count(self):
        """Update the count of captured videos"""
        try:
            video_files = list(VIDEOS_DIR.glob("video_*.h264"))
            count = len(video_files)
            self.capture_count_var.set(str(count))
        except Exception as e:
            logger.error(f"Failed to update capture count: {e}")

    def delete_all_files(self):
        """Delete all videos and images"""
        result = messagebox.askyesno("Confirm Delete",
                                     "Are you sure you want to delete all captured videos?")
        if result:
            try:
                # Delete videos
                video_files = list(VIDEOS_DIR.glob("video_*.h264"))
                video_count = 0
                for video_file in video_files:
                    video_file.unlink()
                    video_count += 1

                # Delete any remaining images from old photo capture mode (if any exist)
                image_files = list(VIDEOS_DIR.glob("capture_*.jpg"))
                image_count = 0
                for img_file in image_files:
                    img_file.unlink()
                    image_count += 1

                # Clear preview
                self.image_label.config(image="", text="No preview")

                self.update_capture_count()

                total = video_count + image_count
                messagebox.showinfo("Success", f"Deleted {total} file(s)")
                logger.info(f"Deleted {video_count} videos and {image_count} images")

            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete files: {e}")
                logger.error(f"Failed to delete files: {e}")

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
