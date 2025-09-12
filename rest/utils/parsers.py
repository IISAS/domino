from datetime import datetime


def parse_iso_z(dt_str: str) -> datetime:
    # If dt_str ends with "Z", replace it
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    return datetime.fromisoformat(dt_str)
