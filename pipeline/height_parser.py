"""Fix Excel date-corruption of height strings.

Excel converts "6-2" -> "2-Jun", "5-11" -> "11-May", etc.
This module detects and reverses that corruption.
"""
import re
import pandas as pd

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# Reverse: if we see "2-Jun", that means original was "6-2" -> 6'2" = 74 inches
# Pattern: digit-Month or Month-digit
CORRUPTED_RE = re.compile(r"^(\d{1,2})-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$", re.IGNORECASE)
CORRUPTED_RE2 = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(\d{1,2})$", re.IGNORECASE)

# Normal format: "6-2", "5-11"
NORMAL_RE = re.compile(r"^(\d)-(\d{1,2})$")


def parse_height(h_str, default=78):
    """Parse a height string to total inches, handling Excel corruption.

    Returns total inches (int).
    """
    if pd.isna(h_str):
        return default

    h_str = str(h_str).strip()

    # Already a number (inches)?
    try:
        val = float(h_str)
        if 60 <= val <= 96:
            return int(round(val))
        # Could be a small number that doesn't make sense as inches
        return default
    except ValueError:
        pass

    # Normal "6-2" format
    m = NORMAL_RE.match(h_str)
    if m:
        feet, inches = int(m.group(1)), int(m.group(2))
        if 4 <= feet <= 7 and 0 <= inches <= 11:
            return feet * 12 + inches

    # Corrupted "2-Jun" format (digit-Month)
    m = CORRUPTED_RE.match(h_str)
    if m:
        inches_part = int(m.group(1))
        month = m.group(2).capitalize()
        feet = MONTH_MAP.get(month, 6)
        # Original was "feet-inches" -> Excel read as "inches-MonthName"
        if 4 <= feet <= 7 and 0 <= inches_part <= 11:
            return feet * 12 + inches_part

    # Corrupted "Jun-2" format (Month-digit)
    m = CORRUPTED_RE2.match(h_str)
    if m:
        month = m.group(1).capitalize()
        inches_part = int(m.group(2))
        feet = MONTH_MAP.get(month, 6)
        if 4 <= feet <= 7 and 0 <= inches_part <= 11:
            return feet * 12 + inches_part

    return default
