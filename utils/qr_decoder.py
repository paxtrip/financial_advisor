from pyzbar.pyzbar import decode
from PIL import Image
import io


def try_decode_qr(image_bytes: bytes) -> str | None:
    """
    Пытается найти и декодировать QR-код из изображения.

    QR чека содержит параметры: t=, s=, fn=, i=, fp=, n=
    Возвращает строку QR-кода или None.
    """
    image = Image.open(io.BytesIO(image_bytes))
    decoded = decode(image)

    for obj in decoded:
        data = obj.data.decode("utf-8")
        # QR российского чека содержит fn= и fp=
        if "fn=" in data and "fp=" in data:
            return data

    return None
