import sys

if sys.platform == "darwin":
    from macapi import *
    from macapi import missing_permissions

    def single_instance() -> bool:
        return True

    def dark_titlebar(widget_id: int) -> None:
        return None
else:
    from winapi import *

    def missing_permissions(ask: bool = True) -> list:
        return []
