"""General utility functions."""

import atlantis


@public
async def get_unused():
    """Prints all functions wo callers"""
    return atlantis.get_uncalled_dynamic_functions()
