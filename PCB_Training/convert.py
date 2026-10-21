# convert_pt_to_onnx.py
# Usage:
#   python3 convert_pt_to_onnx.py
# Make sure best.pt is in the same folder (or change PT_PATH).

import os
import sys

PT_PATH = r"C:\Users\csp\Desktop\training\training\result\tomato,grass2\weights\best.pt"          # input .pt
IMG_SIZE = 512               # must match your app.py IMG_SIZE
OPSET = 12                   # good default for Raspberry Pi ONNX Runtime
SIMPLIFY = True              # simplifies graph (recommended)

def main():
    # 1) Install ultralytics if missing
    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics not found. Install it with:\n  pip3 install ultralytics")
        sys.exit(1)

    if not os.path.exists(PT_PATH):
        print(f"File not found: {PT_PATH}")
        sys.exit(1)

    # 2) Load model
    model = YOLO(PT_PATH)

    # 3) Export to ONNX
    # This will create best.onnx in the same directory by default.
    out = model.export(
        format="onnx",
        imgsz=IMG_SIZE,
        opset=OPSET,
        simplify=SIMPLIFY,
        dynamic=False
    )

    print("\nExport completed.")
    print("Output:", out)
    print("Check for best.onnx in the same folder.\n")

if __name__ == "__main__":
    main()