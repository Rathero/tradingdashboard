import hashlib
import logging

logger = logging.getLogger(__name__)

def get_password_hash(password):
    """Hash simple — ya no se usa autenticación real."""
    return hashlib.sha256(password.encode()).hexdigest()
