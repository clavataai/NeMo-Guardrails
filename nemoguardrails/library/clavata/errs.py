class ClavataPluginError(Exception):
    """
    Base exception for all Clavata plugin errors.
    """


class ClavataPluginConfigurationError(ClavataPluginError):
    """
    Exception raised when the Clavata plugin is not configured correctly.
    """


class ClavataPluginValueError(ClavataPluginError):
    """
    Exception raised when the Clavata plugin is used incorrectly.
    """


class ClavataPluginTypeError(ClavataPluginError):
    """
    Exception raised when the Clavata plugin is used incorrectly due to type mismatches.
    """


class ClavataPluginAPIError(ClavataPluginError):
    """
    Exception raised when the Clavata plugin API returns an error.
    """


class ClavataPluginAPIRateLimitError(ClavataPluginAPIError):
    """
    Exception raised when the Clavata plugin API rate limit is exceeded.
    """
