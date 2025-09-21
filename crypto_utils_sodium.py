# crypto_utils_sodium.py — libsodium sealed box helpers
from __future__ import annotations

import base64
from nacl.public import PrivateKey, PublicKey, SealedBox

def load_public_key_b64(data: bytes) -> PublicKey:
    """Input: raw file bytes containing base64 of 32-byte public key."""
    return PublicKey(base64.b64decode(data))

def load_private_key_b64(data: bytes) -> PrivateKey:
    """Input: raw file bytes containing base64 of 32-byte secret key."""
    return PrivateKey(base64.b64decode(data))

def sealedbox_encrypt(pk: PublicKey, plaintext: bytes) -> bytes:
    return SealedBox(pk).encrypt(plaintext)

def sealedbox_decrypt(sk: PrivateKey, ciphertext: bytes) -> bytes:
    return SealedBox(sk).decrypt(ciphertext)

