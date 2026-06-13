import hashlib
import secrets


def hash_password(password: str) -> str:

    salt = secrets.token_hex(16)

    password_hash = hashlib.sha256(
        (salt + password).encode()
    ).hexdigest()

    return f"{salt}${password_hash}"


def verify_password(
    password: str,
    stored_hash: str
) -> bool:

    salt, password_hash = stored_hash.split("$")

    check_hash = hashlib.sha256(
        (salt + password).encode()
    ).hexdigest()

    return check_hash == password_hash