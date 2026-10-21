import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from ultralytics import YOLO
import threading
import sys
import psutil  # For CPU and RAM usage monitoring
import time
from contextlib import redirect_stdout
from io import StringIO
import logging
import torch

# Global flag to stop training
stop_training_flag = False


def detect_device():
    """Return ('0', description) if a CUDA GPU is available, else ('cpu', description)."""
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        return "0", f"GPU detected: {gpu_name} (using GPU)"
    return "cpu", "No GPU detected (using CPU)"


class RedirectOutput:
    """Class to redirect stdout and logger output to a Tkinter Text widget."""

    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, message):
        self.text_widget.insert(tk.END, message)
        self.text_widget.see(tk.END)  # Auto-scroll to the bottom
        self.text_widget.update_idletasks()  # Ensure immediate update

    def flush(self):
        pass  # Required for Python's print function

    def emit(self, record):
        """For redirecting logging output."""
        msg = self.format(record)
        self.write(msg + '\n')


def setup_logger(output_widget):
    """Configure logging to redirect to the output widget."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Clear existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Add a handler to redirect logs to the text widget
    handler = logging.StreamHandler(RedirectOutput(output_widget))
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)


def start_training():
    """Start the YOLO training process."""
    global stop_training_flag
    stop_training_flag = False  # Reset the flag when training starts

    def run_training():
        try:
            # Get user inputs
            model_path = model_path_entry.get().strip()
            data_yaml = data_yaml_entry.get().strip()
            epochs = epochs_entry.get().strip()
            imgsz = imgsz_entry.get().strip()
            batch = batch_entry.get().strip()
            workers = workers_entry.get().strip()
            project_name = project_entry.get().strip()
            experiment_name = experiment_name_entry.get().strip()
            device = device_entry.get().strip()

            # Auto-detect GPU/CPU if the user leaves the device field as "auto" or blank
            if not device or device.lower() == "auto":
                device, device_msg = detect_device()
            else:
                device_msg = f"Using user-specified device: {device}"
            print(device_msg)

            # Logging inputs for debugging
            print("Starting training with the following configuration:")
            print(f"Model Path: {model_path}")
            print(f"Data YAML Path: {data_yaml}")
            print(f"Epochs: {epochs}")
            print(f"Image Size: {imgsz}")
            print(f"Batch Size: {batch}")
            print(f"Number of Workers: {workers}")
            print(f"Project: {project_name}")
            print(f"Experiment Name: {experiment_name}")
            print(f"Device: {device}")

            # Validate mandatory fields
            if not all([model_path, data_yaml, epochs, imgsz, batch, workers, project_name, experiment_name, device]):
                messagebox.showerror("Error", "All fields except 'Resume Training' are mandatory. Please fill them in!")
                return

            # Convert numeric inputs
            try:
                epochs = int(epochs)
                imgsz = int(imgsz)
                batch = int(batch)
                workers = int(workers)
            except ValueError:
                messagebox.showerror("Error", "Epochs, Image Size, Batch Size, and Number of Workers must be integers.")
                return

            resume = resume_var.get()

            # Redirect training output to the text widget
            buffer = StringIO()

            with redirect_stdout(buffer):
                # Load YOLO model
                model = YOLO(model_path)
                print("Model loaded successfully!")

                model.train(
                    data=data_yaml,
                    epochs=epochs,
                    imgsz=imgsz,
                    batch=batch,
                    workers=workers,
                    amp=False,
                    cache=True,
                    project=project_name,
                    name=experiment_name,
                    device=device,
                    resume=resume
                )

            # Write training logs to the output text widget
            output_text.insert(tk.END, buffer.getvalue())
            output_text.see(tk.END)

        except Exception as e:
            print("An error occurred:", e)
            messagebox.showerror("Training Error", str(e))

    # Run training in a separate thread to keep UI responsive
    threading.Thread(target=run_training, daemon=True).start()


def update_resource_usage():
    """Updates CPU and RAM usage in the UI."""
    while True:
        cpu_usage.set(f"CPU Usage: {psutil.cpu_percent()}%")
        ram_usage.set(f"RAM Usage: {psutil.virtual_memory().percent}%")
        time.sleep(1)


# Create Tkinter GUI
root = tk.Tk()
root.title("YOLOv8 Training Configuration")
root.geometry(f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}")  # Fit to screen

# CPU and RAM Usage Labels
cpu_usage = tk.StringVar(value="CPU Usage: 0%")
ram_usage = tk.StringVar(value="RAM Usage: 0%")

tk.Label(root, textvariable=cpu_usage, fg="blue", font=("Arial", 12)).grid(row=0, column=0, padx=10, pady=5, sticky="w")
tk.Label(root, textvariable=ram_usage, fg="blue", font=("Arial", 12)).grid(row=0, column=1, padx=10, pady=5, sticky="w")

# Model Path
tk.Label(root, text="Model Path:").grid(row=1, column=0, sticky='e', padx=10, pady=5)
model_path_entry = tk.Entry(root, width=70)
model_path_entry.grid(row=1, column=1, padx=10, pady=5)
tk.Button(root, text="Browse", command=lambda: model_path_entry.insert(0, filedialog.askopenfilename())).grid(row=1,
                                                                                                              column=2,
                                                                                                              padx=10,
                                                                                                              pady=5)

# Data YAML Path
tk.Label(root, text="Data YAML Path:").grid(row=2, column=0, sticky='e', padx=10, pady=5)
data_yaml_entry = tk.Entry(root, width=70)
data_yaml_entry.grid(row=2, column=1, padx=10, pady=5)
tk.Button(root, text="Browse", command=lambda: data_yaml_entry.insert(0, filedialog.askopenfilename())).grid(row=2,
                                                                                                             column=2,
                                                                                                             padx=10,
                                                                                                             pady=5)

# Number of Epochs
tk.Label(root, text="Number of Epochs:").grid(row=3, column=0, sticky='e', padx=10, pady=5)
epochs_entry = tk.Entry(root, width=20)
epochs_entry.grid(row=3, column=1, padx=10, pady=5)
epochs_entry.insert(0, "120")  # Default value

# Image Size
tk.Label(root, text="Image Size:").grid(row=4, column=0, sticky='e', padx=10, pady=5)
imgsz_entry = tk.Entry(root, width=20)
imgsz_entry.grid(row=4, column=1, padx=10, pady=5)
imgsz_entry.insert(0, "512")  # Default value

# Batch Size
tk.Label(root, text="Batch Size:").grid(row=5, column=0, sticky='e', padx=10, pady=5)
batch_entry = tk.Entry(root, width=20)
batch_entry.grid(row=5, column=1, padx=10, pady=5)
batch_entry.insert(0, "1")  # Default value

# Number of Workers
tk.Label(root, text="Number of Workers:").grid(row=6, column=0, sticky='e', padx=10, pady=5)
workers_entry = tk.Entry(root, width=20)
workers_entry.grid(row=6, column=1, padx=10, pady=5)
workers_entry.insert(0, "0")  # Default value

# Project Directory
tk.Label(root, text="Project Directory:").grid(row=7, column=0, sticky='e', padx=10, pady=5)
project_entry = tk.Entry(root, width=70)
project_entry.grid(row=7, column=1, padx=10, pady=5)
tk.Button(
    root,
    text="Browse",
    command=lambda: project_entry.delete(0, tk.END) or project_entry.insert(0, filedialog.askdirectory()),
).grid(row=7, column=2, padx=10, pady=5)

# Experiment Name
tk.Label(root, text="Experiment Name:").grid(row=8, column=0, sticky='e', padx=10, pady=5)
experiment_name_entry = tk.Entry(root, width=70)
experiment_name_entry.grid(row=8, column=1, padx=10, pady=5)
experiment_name_entry.insert(0, "yolov8_experiment")  # Default value

# Device
tk.Label(root, text="Device ('auto', 'cpu', or '0'):").grid(row=9, column=0, sticky='e', padx=10, pady=5)
device_entry = tk.Entry(root, width=20)
device_entry.grid(row=9, column=1, padx=10, pady=5)

_default_device, _device_status = detect_device()
device_entry.insert(0, _default_device)  # Auto-detected default (GPU if available, else CPU)

tk.Label(root, text=_device_status, fg=("green" if _default_device != "cpu" else "orange"),
         font=("Arial", 9, "italic")).grid(row=9, column=2, sticky='w', padx=10, pady=5)

# Resume Training
tk.Label(root, text="Resume Training:").grid(row=10, column=0, sticky='e', padx=10, pady=5)
resume_var = tk.BooleanVar(value=False)
tk.Checkbutton(root, text="Resume", variable=resume_var).grid(row=10, column=1, padx=10, pady=5, sticky='w')

# Start Training Button
tk.Button(root, text="Start Training", command=start_training, bg="green", fg="white").grid(row=11, column=0,
                                                                                            columnspan=1, pady=10)
# Output Log
tk.Label(root, text="Training Progress:").grid(row=12, column=0, sticky='nw', padx=10, pady=5)
output_text = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=120, height=10)
output_text.grid(row=15, column=1, columnspan=2, padx=10, pady=5)

# Redirect stdout to Text widget
sys.stdout = RedirectOutput(output_text)

# Footer
footer_label = tk.Label(root, text="Powered by V V Technologies, Bangalore", fg="gray", font=("Arial", 10, "italic"))
footer_label.grid(row=16, column=0, columnspan=3, pady=5)

# Start resource usage thread
threading.Thread(target=update_resource_usage, daemon=True).start()

root.mainloop()
