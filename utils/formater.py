from datetime import datetime
import re


def date_formater(date_str: str | None) -> datetime | None:
    """解析 Steam Workshop 多种日期格式"""
    if not date_str:
        return None

    # strip() will remove most whitespace but not all Unicode space categories
    date_str = "".join(date_str.split())
    if not date_str:
        return None

    # 尝试多种日期格式解析器
    parsers = [
        _parse_malformed_english_with_year,
        _parse_english_with_chinese_year_prefix,
        _parse_english_simple,
        _parse_chinese,
    ]

    for parser in parsers:
        result = parser(date_str)
        if result is not None:
            return result

    raise ValueError(f"无法解析日期字符串: '{date_str}'")


def _parse_malformed_english_with_year(date_str: str) -> datetime | None:
    """解析错误年份前缀格式: '2025 年 May 12, 2022 @ 12:43pm'"""
    pattern = r"^(?:\d{4})\s*年\s*([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})\s*@\s*(\d{1,2}:\d{2}[ap]m)$"
    match = re.match(pattern, date_str, re.IGNORECASE)

    if match:
        month, day, year, time_str = match.groups()
        return _parse_datetime(f"{year} {month} {day} {time_str}", "%Y %b %d %I:%M%p")

    return None


def _parse_english_with_chinese_year_prefix(date_str: str) -> datetime | None:
    """解析带中文年份前缀的英文日期"""
    pattern = r"^(\d{4})\s*年\s*(\d{1,2}|[A-Za-z]{3})\s+([A-Za-z]{3}|\d{1,2})\s*@\s*(\d{1,2}:\d{2}[ap]m)$"
    match = re.match(pattern, date_str, re.IGNORECASE)

    if match:
        year, part1, part2, time_str = match.groups()

        # 判断月份和日期
        if part1.isdigit():
            day, month = part1, part2
        else:
            month, day = part1, part2

        return _parse_datetime(f"{year} {month} {day} {time_str}", "%Y %b %d %I:%M%p")

    return None


def _parse_english_simple(date_str: str) -> datetime | None:
    """解析简单英文日期格式"""
    current_year = datetime.now().year

    # MMM DD, YYYY @ HH:MMam/pm
    pattern1 = r"^([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})\s*@\s*(\d{1,2}:\d{2}[ap]m)$"
    match = re.match(pattern1, date_str, re.IGNORECASE)
    if match:
        month, day, year, time_str = match.groups()
        return _parse_datetime(f"{year} {month} {day} {time_str}", "%Y %b %d %I:%M%p")

    # DD MMM, YYYY @ HH:MMam/pm
    pattern1b = r"^(\d{1,2})\s+([A-Za-z]{3}),\s*(\d{4})\s*@\s*(\d{1,2}:\d{2}[ap]m)$"
    match = re.match(pattern1b, date_str, re.IGNORECASE)
    if match:
        day, month, year, time_str = match.groups()
        return _parse_datetime(f"{year} {month} {day} {time_str}", "%Y %b %d %I:%M%p")

    # DD MMM @ HH:MMam/pm (无年份)
    pattern2 = r"^(\d{1,2})\s+([A-Za-z]{3})\s*@\s*(\d{1,2}:\d{2}[ap]m)$"
    match = re.match(pattern2, date_str, re.IGNORECASE)
    if match:
        day, month, time_str = match.groups()
        return _parse_datetime(f"{current_year} {month} {day} {time_str}", "%Y %b %d %I:%M%p")

    # MMM DD @ HH:MMam/pm (无年份)
    pattern3 = r"^([A-Za-z]{3})\s+(\d{1,2})\s*@\s*(\d{1,2}:\d{2}[ap]m)$"
    match = re.match(pattern3, date_str, re.IGNORECASE)
    if match:
        month, day, time_str = match.groups()
        return _parse_datetime(f"{current_year} {month} {day} {time_str}", "%Y %b %d %I:%M%p")

    return None


def _parse_chinese(date_str: str) -> datetime | None:
    """解析中文日期格式"""
    current_year = datetime.now().year

    # 无年份则添加当前年份
    if "年" not in date_str:
        date_str = f"{current_year} 年 {date_str}"

    # 转换上午/下午为24小时制
    if "下午" in date_str:
        time_match = re.search(r"下午\s*(\d{1,2}):(\d{2})", date_str)
        if time_match:
            hour = int(time_match.group(1))
            if hour != 12:
                hour += 12
            date_str = re.sub(r"下午\s*\d{1,2}:\d{2}", f"{hour}:{time_match.group(2)}", date_str)
        date_str = date_str.replace("下午", "").strip()
    elif "上午" in date_str:
        time_match = re.search(r"上午\s*(\d{1,2}):(\d{2})", date_str)
        if time_match:
            hour = int(time_match.group(1))
            if hour == 12:
                hour = 0
            date_str = re.sub(r"上午\s*\d{1,2}:\d{2}", f"{hour}:{time_match.group(2)}", date_str)
        date_str = date_str.replace("上午", "").strip()

    # 标准化并解析
    date_str = re.sub(r"\s+", " ", date_str).strip()
    return _parse_datetime(date_str, "%Y 年 %m 月 %d 日 %H:%M")


def _parse_datetime(date_str: str, format_str: str) -> datetime | None:
    """使用指定格式解析日期"""
    try:
        return datetime.strptime(date_str, format_str)
    except (ValueError, TypeError):
        return None


def file_size_formater(file_size: str | None) -> int:
    """文件大小字符串转换为字节数"""
    if not file_size:
        return 0

    size_str = file_size.strip()
    match = re.match(r"^([\d.]+)\s*(KB|MB|GB|bytes?)?$", size_str, re.IGNORECASE)

    if match:
        value = float(match.group(1))
        unit = match.group(2)

        if unit:
            unit_upper = unit.upper()
            if "KB" in unit_upper:
                return int(value * 1024)
            elif "MB" in unit_upper:
                return int(value * 1024 * 1024)
            elif "GB" in unit_upper:
                return int(value * 1024 * 1024 * 1024)
            elif "BYTE" in unit_upper:
                return int(value)
        else:
            return int(value)

    digits = re.sub(r"[^0-9]", "", size_str)
    return int(digits) if digits else 0


def image_url_formater(image_url: str | None) -> str | None:
    """过滤和格式化图片 URL"""
    if not image_url:
        return None

    blocked_images = [
        "zoom_icon.png",
        "icon_thumbsup.png",
        "icon_thumbsdown.png",
        "trans.gif",
        "steam_workshop_default_image.png",
    ]

    for blocked_image in blocked_images:
        if blocked_image in image_url:
            return None

    if "?" in image_url:
        return image_url.split("?")[0]

    return image_url


def format_number(text: str) -> int:
    """数字字符串转换为整数"""
    if not text:
        return 0
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else 0
