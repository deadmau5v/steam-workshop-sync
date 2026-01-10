from datetime import datetime
import re


def date_formater(date_str: str | None) -> datetime | None:
    """
    解析 Steam Workshop 的多种日期格式并转换为 datetime 对象。

    支持的格式：

    英文格式：
        - 'May 12, 2022 @ 12:43pm'          # 标准格式
        - '12 Dec @ 7:12am'                 # 无年份（使用当前年份）
        - 'Dec 12 @ 7:12am'                 # 月份在前
        - '2017 年 12 Dec @ 7:12am'          # 带中文年份前缀
        - '2025 年 May 12, 2022 @ 12:43pm'  # 错误年份前缀（使用逗号后的年份）

    中文格式：
        - '10 月 18 日 下午 11:37'           # 无年份（使用当前年份）
        - '2017 年 12 月 2 日 上午 10:37'    # 完整日期时间

    Args:
        date_str: 日期字符串，可能为 None

    Returns:
        datetime 对象，如果输入为 None 则返回 None

    Raises:
        ValueError: 如果日期字符串格式不被支持
    """
    if not date_str:
        return None

    date_str = date_str.strip()
    if not date_str:
        return None

    # 定义日期解析器列表，按优先级排序
    parsers = [
        _parse_malformed_english_with_year,
        _parse_english_with_chinese_year_prefix,
        _parse_english_simple,
        _parse_chinese,
    ]

    # 尝试每个解析器
    for parser in parsers:
        result = parser(date_str)
        if result is not None:
            return result

    # 如果所有解析器都失败，抛出异常
    raise ValueError(f"无法解析日期字符串: '{date_str}'\n支持的格式请参考 date_formater 函数文档")


def _parse_malformed_english_with_year(date_str: str) -> datetime | None:
    """
    解析错误的年份前缀格式: '2025 年 May 12, 2022 @ 12:43pm'

    Steam 有时会返回带有错误年份前缀的日期，实际年份在逗号之后。
    这个解析器提取逗号后的正确年份。
    """
    pattern = r"^(?:\d{4})\s*年\s*([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})\s*@\s*(\d{1,2}:\d{2}[ap]m)$"
    match = re.match(pattern, date_str, re.IGNORECASE)

    if match:
        month, day, year, time_str = match.groups()
        return _parse_datetime(f"{year} {month} {day} {time_str}", "%Y %b %d %I:%M%p")

    return None


def _parse_english_with_chinese_year_prefix(date_str: str) -> datetime | None:
    """
    解析带中文年份前缀的英文日期格式。

    支持的格式：
        - '2017 年 12 Dec @ 7:12am'
        - '2017 年 Dec 12 @ 7:12am'
    """
    # 格式：YYYY 年 DD MMM @ HH:MMam/pm 或 YYYY 年 MMM DD @ HH:MMam/pm
    pattern = r"^(\d{4})\s*年\s*(\d{1,2}|[A-Za-z]{3})\s+([A-Za-z]{3}|\d{1,2})\s*@\s*(\d{1,2}:\d{2}[ap]m)$"
    match = re.match(pattern, date_str, re.IGNORECASE)

    if match:
        year, part1, part2, time_str = match.groups()

        # 判断哪个是月份，哪个是日期
        if part1.isdigit():
            # part1 是日期，part2 是月份
            day, month = part1, part2
        else:
            # part1 是月份，part2 是日期
            month, day = part1, part2

        return _parse_datetime(f"{year} {month} {day} {time_str}", "%Y %b %d %I:%M%p")

    return None


def _parse_english_simple(date_str: str) -> datetime | None:
    """
    解析简单的英文日期格式（无年份或带逗号的标准格式）。

    支持的格式：
        - 'May 12, 2022 @ 12:43pm'  # 标准格式（月在前）
        - '1 Dec, 2019 @ 11:26am'    # 标准格式（日在前）
        - '12 Dec @ 7:12am'          # 日在前，无年份
        - 'Dec 12 @ 7:12am'          # 月在前，无年份
    """
    current_year = datetime.now().year

    # 格式：MMM DD, YYYY @ HH:MMam/pm (标准格式，月在前)
    pattern1 = r"^([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})\s*@\s*(\d{1,2}:\d{2}[ap]m)$"
    match = re.match(pattern1, date_str, re.IGNORECASE)
    if match:
        month, day, year, time_str = match.groups()
        return _parse_datetime(f"{year} {month} {day} {time_str}", "%Y %b %d %I:%M%p")

    # 格式：DD MMM, YYYY @ HH:MMam/pm (标准格式，日在前)
    pattern1b = r"^(\d{1,2})\s+([A-Za-z]{3}),\s*(\d{4})\s*@\s*(\d{1,2}:\d{2}[ap]m)$"
    match = re.match(pattern1b, date_str, re.IGNORECASE)
    if match:
        day, month, year, time_str = match.groups()
        return _parse_datetime(f"{year} {month} {day} {time_str}", "%Y %b %d %I:%M%p")

    # 格式：DD MMM @ HH:MMam/pm (日在前，无年份)
    pattern2 = r"^(\d{1,2})\s+([A-Za-z]{3})\s*@\s*(\d{1,2}:\d{2}[ap]m)$"
    match = re.match(pattern2, date_str, re.IGNORECASE)
    if match:
        day, month, time_str = match.groups()
        return _parse_datetime(f"{current_year} {month} {day} {time_str}", "%Y %b %d %I:%M%p")

    # 格式：MMM DD @ HH:MMam/pm (月在前，无年份)
    pattern3 = r"^([A-Za-z]{3})\s+(\d{1,2})\s*@\s*(\d{1,2}:\d{2}[ap]m)$"
    match = re.match(pattern3, date_str, re.IGNORECASE)
    if match:
        month, day, time_str = match.groups()
        return _parse_datetime(f"{current_year} {month} {day} {time_str}", "%Y %b %d %I:%M%p")

    return None


def _parse_chinese(date_str: str) -> datetime | None:
    """
    解析中文日期格式。

    支持的格式：
        - '10 月 18 日 下午 11:37'
        - '2017 年 12 月 2 日 上午 10:37'
        - '2017 年 12 月 2 日 23:37'  # 24小时制
    """
    original_str = date_str
    current_year = datetime.now().year

    # 如果没有年份，添加当前年份
    if "年" not in date_str:
        date_str = f"{current_year} 年 {date_str}"

    # 处理中文时间标识符（上午/下午）
    if "下午" in date_str:
        # 提取下午时间并转换为24小时制
        time_match = re.search(r"下午\s*(\d{1,2}):(\d{2})", date_str)
        if time_match:
            hour = int(time_match.group(1))
            minute = time_match.group(2)
            # 下午12点特殊处理（12:xx PM 仍是12:xx）
            if hour != 12:
                hour += 12
            date_str = re.sub(r"下午\s*\d{1,2}:\d{2}", f"{hour}:{minute}", date_str)
        date_str = date_str.replace("下午", "").strip()
    elif "上午" in date_str:
        # 上午时间需要处理12点的情况（12:xx AM 应该是 00:xx）
        time_match = re.search(r"上午\s*(\d{1,2}):(\d{2})", date_str)
        if time_match:
            hour = int(time_match.group(1))
            minute = time_match.group(2)
            if hour == 12:
                hour = 0
            date_str = re.sub(r"上午\s*\d{1,2}:\d{2}", f"{hour}:{minute}", date_str)
        date_str = date_str.replace("上午", "").strip()

    # 标准化空格
    date_str = re.sub(r"\s+", " ", date_str).strip()

    # 尝试中文日期格式
    formats = [
        "%Y 年 %m 月 %d 日 %H:%M",  # 2017 年 12 月 2 日 10:37
    ]

    for fmt in formats:
        result = _parse_datetime(date_str, fmt)
        if result is not None:
            return result

    return None


def _parse_datetime(date_str: str, format_str: str) -> datetime | None:
    """
    辅助函数：尝试使用指定格式解析日期字符串。

    Args:
        date_str: 日期字符串
        format_str: strptime 格式字符串

    Returns:
        datetime 对象，解析失败返回 None
    """
    try:
        return datetime.strptime(date_str, format_str)
    except (ValueError, TypeError):
        return None


def file_size_formater(file_size: str | None) -> int:
    """
    将 Steam Workshop 文件大小字符串转换为字节数。

    支持的格式：
        - '77.308 KB'  -> 79,163 bytes
        - '1.633 MB'   -> 1,712,128 bytes
        - '2.1 GB'     -> 2,254,857,830 bytes
        - '123456'     -> 123,456 bytes

    Args:
        file_size: 文件大小字符串，可能为 None

    Returns:
        文件大小（字节），如果输入为 None 或无法解析则返回 0
    """
    if not file_size:
        return 0

    size_str = file_size.strip()

    # 尝试提取数值和单位
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
            # 纯数字，假设为字节
            return int(value)

    # 如果正则匹配失败，尝试提取所有数字作为后备方案
    digits = re.sub(r"[^0-9]", "", size_str)
    return int(digits) if digits else 0


def image_url_formater(image_url: str | None) -> str | None:
    """
    格式化和过滤 Steam Workshop 图片 URL。

    功能：
        1. 过滤掉 Steam 的图标和占位符图片
        2. 移除 URL 中的查询参数

    Args:
        image_url: 图片 URL 字符串，可能为 None

    Returns:
        清理后的 URL，如果是需要过滤的图片则返回 None
    """
    if not image_url:
        return None

    # 需要过滤的 Steam 图标和占位符图片
    blocked_images = [
        "zoom_icon.png",
        "icon_thumbsup.png",
        "icon_thumbsdown.png",
        "trans.gif",
        "steam_workshop_default_image.png",
    ]

    # 检查是否包含需要过滤的图片
    for blocked_image in blocked_images:
        if blocked_image in image_url:
            return None

    # 移除 URL 查询参数
    if "?" in image_url:
        return image_url.split("?")[0]

    return image_url
