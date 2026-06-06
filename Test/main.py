import atlantis
import logging

logger = logging.getLogger("dynamic_function")


@visible
async def index():
    """
    Folder for Test
    """
    logger.info(f"Executing placeholder function: index...")

    await atlantis.client_log("index running")

    # Replace this return statement with your function's result
    return f"Placeholder function 'index' executed successfully."

# % ls

# % cursor show

# % foo 3 4

def _number(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number")


@visible
async def foo(x: int | float, y: int | float):
    """
    This is a placeholder function for 'foo'
    """
    logger.info(f"Executing placeholder function: foo...")

    #await atlantis.client_log("foo running")

    x = _number(x, "x")
    y = _number(y, "y")
    return x + y


@dynamic
async def foobar(path: str = "."):
    """
    Dynamic folder provider for Test/foobar.
    """
    logger.info(f"Listing dynamic folder foobar path={path!r}")
    return []
