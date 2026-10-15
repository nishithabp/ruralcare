"""Read a QR code (OpenCV) or barcode (pyzbar, optional) from a photo."""
import cv2
import numpy as np

MAX_SIDE = 1800


def decode_image(data: bytes) -> str | None:
    """Returns the code text, None if no code is found. Raises ValueError if not an image."""
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("not an image")
    h, w = img.shape[:2]
    k = min(1.0, MAX_SIDE / max(h, w))
    if k < 1.0:
        img = cv2.resize(img, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)

    detector = cv2.QRCodeDetector()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    variants = [img, gray, cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10)]
    for variant in variants:
        for scale in (1.0, 0.6, 1.6):
            v = variant if scale == 1.0 else cv2.resize(variant, None, fx=scale, fy=scale)
            try:
                text, _, _ = detector.detectAndDecode(v)
            except cv2.error:
                continue
            if text:
                return text.strip()

    try:  # 1D barcodes, if pyzbar and libzbar are installed
        from pyzbar.pyzbar import decode as zbar_decode
        found = zbar_decode(gray)
        if found:
            return found[0].data.decode(errors="ignore").strip()
    except Exception:
        pass
    return None
