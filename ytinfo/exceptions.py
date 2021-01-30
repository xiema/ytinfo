class Error(Exception):
    """Base exception class"""

class RetryError(Error):
    """Exceeded maximum number of retries"""
