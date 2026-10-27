"""Face detection and recognition with OpenCV's YuNet detector and SFace model."""
import base64
import binascii
import threading
from pathlib import Path

import cv2
import numpy as np

DETECTION_SCORE = 0.9   # minimum YuNet confidence for a detection to count as a face
AMBIGUITY_RATIO = 0.5   # a second face at least half the area of the largest makes the image ambiguous


class FaceError(ValueError):
    """Raised when an image cannot be used: unreadable, no face, several faces or face too small."""


def face_area(face: np.ndarray) -> float:
    """Area of a YuNet detection, whose row is [x, y, w, h, five landmark points, score]."""
    return face[2] * face[3]


def decode_image(data_url: str) -> np.ndarray:
    """Turn the 'data:image/jpeg;base64,...' string sent by the browser into a BGR image."""
    payload = data_url.split(",", 1)[1] if "," in data_url else data_url
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise FaceError("The image could not be read. Please capture it again.")
    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise FaceError("The image could not be read. Please capture it again.")
    return image


class FaceEngine:
    def __init__(self, models_dir: Path):
        self._detector = cv2.FaceDetectorYN.create(
            str(models_dir / "face_detection_yunet_2023mar.onnx"), "", (320, 320), DETECTION_SCORE)
        self._recognizer = cv2.FaceRecognizerSF.create(
            str(models_dir / "face_recognition_sface_2021dec.onnx"), "")
        # The OpenCV model objects keep per-call state, so requests use them one at a time.
        self._lock = threading.Lock()

    def template(self, image: np.ndarray, min_face_px: int) -> np.ndarray:
        """Detect the one clear face in an image and return its 128-value template, scaled to unit length."""
        with self._lock:
            height, width = image.shape[:2]
            self._detector.setInputSize((width, height))
            _, faces = self._detector.detect(image)
            if faces is None or len(faces) == 0:
                raise FaceError("No face detected. Please face the camera and try again.")

            faces = sorted(faces, key=face_area, reverse=True)   # largest face first
            face = faces[0]
            if len(faces) > 1 and face_area(faces[1]) >= AMBIGUITY_RATIO * face_area(face):
                raise FaceError("More than one face detected. Only one person should face the camera.")
            if min(face[2], face[3]) < min_face_px:
                raise FaceError("The face is too small. Please move closer to the camera.")

            aligned = self._recognizer.alignCrop(image, face)   # rotate and crop to 112 x 112 using the landmarks
            feature = self._recognizer.feature(aligned).flatten().astype(np.float32)
        return feature / np.linalg.norm(feature)


def best_match(probe: np.ndarray, templates: np.ndarray) -> tuple[int, float]:
    """Compare a probe with every enrolled template and return the closest one and its cosine similarity."""
    scores = templates @ probe   # templates are unit length, so the dot product is the cosine similarity
    index = int(np.argmax(scores))
    return index, float(scores[index])
