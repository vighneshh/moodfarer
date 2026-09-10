"""
Generates a VAPID keypair for Web Push notifications.

Usage:
    python generate_vapid_keys.py

Copy the printed values into your environment as VAPID_PUBLIC_KEY and
VAPID_PRIVATE_KEY, and set VAPID_CLAIMS_EMAIL to a contact address
(e.g. "mailto:you@example.com").
"""

from py_vapid import Vapid02
import base64


def main():
    vapid = Vapid02()
    vapid.generate_keys()

    public_raw = vapid.public_key.public_bytes(
        encoding=__import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.X962,
        format=__import__("cryptography.hazmat.primitives.serialization", fromlist=["PublicFormat"]).PublicFormat.UncompressedPoint,
    )
    private_raw = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")

    public_b64 = base64.urlsafe_b64encode(public_raw).rstrip(b"=").decode()
    private_b64 = base64.urlsafe_b64encode(private_raw).rstrip(b"=").decode()

    print("VAPID_PUBLIC_KEY=" + public_b64)
    print("VAPID_PRIVATE_KEY=" + private_b64)
    print("VAPID_CLAIMS_EMAIL=mailto:you@example.com")


if __name__ == "__main__":
    main()
