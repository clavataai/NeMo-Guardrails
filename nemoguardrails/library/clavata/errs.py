class ClavataPluginError(Exception):
    """
    Base exception for all Clavata plugin errors.
    """


class ClavataPluginAPIError(ClavataPluginError):
    """
    Exception raised when the Clavata plugin API returns an error.
    """


class ClavataPluginConfigurationError(ClavataPluginError):
    """
    Exception raised when the Clavata plugin is not configured correctly.
    """


class ClavataPluginValueError(ClavataPluginError):
    """
    Exception raised when the Clavata plugin is used incorrectly.
    """
