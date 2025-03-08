import asyncio
import random
from collections.abc import Awaitable, Callable, Iterable
from functools import wraps
from typing import Any, Optional, ParamSpec, TypeVar

from .errs import ClavataPluginTypeError


class RetriesExceededError(Exception):
    """Exception raised when the maximum number of retries is exceeded."""

    retries: int
    max_retries: int
    last_exception: Optional[Exception]

    def __init__(
        self, retries: int, max_retries: int, last_exception: Optional[Exception]
    ):
        self.retries = retries
        self.max_retries = max_retries
        self.last_exception = last_exception
        super().__init__(
            f"Maximum number of retries ({max_retries}) exceeded after {retries} retries."
            f"Last exception: {last_exception}"
        )


ReturnT = TypeVar("ReturnT")
P = ParamSpec("P")


def exponential_backoff(
    *,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    factor: float = 2.0,
    jitter: float = 0.2,  # 20% jitter, set to 0 to disable jitter
    retry_exceptions: type[Exception] | Iterable[type[Exception]] = Exception,
    on_permanent_failure: Optional[Callable[[int, Exception], Awaitable[Any]]] = None,
):
    """Exponential backoff retry mechanism."""

    # Ensure retry_exceptions is a tuple of exceptions
    retry_exceptions = (
        (retry_exceptions,)
        if isinstance(retry_exceptions, type)
        else tuple(retry_exceptions)
    )

    # Sanity check, make sure the types in the retry_exceptions are all exceptions
    if not all(
        isinstance(e, type) and issubclass(e, Exception) for e in retry_exceptions
    ):
        raise ClavataPluginTypeError(
            "retry_exceptions must be a tuple of exception types"
        )

    def calculate_exp_delay(retries: int) -> float:
        delay = min(
            initial_delay * (factor**retries),
            max_delay,
        )
        if jitter:
            delay += random.uniform(-delay * jitter, delay * jitter)
        return delay

    def decorator(
        func: Callable[P, Awaitable[ReturnT]],
    ) -> Callable[P, Awaitable[ReturnT]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> ReturnT:
            retries = 0
            last_exception: Optional[Exception] = None
            while retries < max_retries:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:  # noqa: BLE001
                    # If the exception is not in the list of retry exceptions, raise it rather than retrying
                    last_exception = e
                    if not isinstance(e, retry_exceptions):
                        if on_permanent_failure is None:
                            raise

                        perm_rv = await on_permanent_failure(retries, e)
                        if isinstance(perm_rv, Exception):
                            raise perm_rv from e
                        return perm_rv

                    # We want to calculate the delay before incrementing because we want the first
                    # delay to be exactly the initial delay
                    delay = calculate_exp_delay(retries)
                    await asyncio.sleep(delay)
                    retries += 1

            # Max retries exceeded, raise or if a custom handler is provided, call it and then decide what to do
            retried_exc = RetriesExceededError(retries, max_retries, last_exception)
            if on_permanent_failure is None:
                raise retried_exc
            perm_rv = await on_permanent_failure(retries, retried_exc)
            if isinstance(perm_rv, Exception):
                raise perm_rv
            return perm_rv

        return wrapper

    return decorator
