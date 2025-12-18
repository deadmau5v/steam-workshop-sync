from datetime import datetime
import re


def date_formater(date_str: str | None) -> datetime | None:
    """
    支持多种 Steam Workshop 日期格式：
    例：
    - 10 月 18 日 下午 11:37
    - 2017 年 12 月 2 日 上午 10:37
    - 12 Dec @ 7:12am
    - 2017 年 12 Dec @ 7:12am
    - 13 Dec @ 3:45am
    - 1 Nov @ 8:30am
    转为 datetime 格式
    """
    import re

    if not date_str:
        return None

    date_str = date_str.strip()

    # 英文格式: '12 Dec @ 7:12am' 或 '2017 年 12 Dec @ 7:12am'
    # 补全年份
    match_en = re.match(
        r"^(?:(\d{4}) 年 )?(\d{1,2}|[A-Za-z]{3,}) ([A-Za-z]{3}|[0-9]{1,2}) @ (\d{1,2}:\d{2}[ap]m)",
        date_str,
    )
    match_en_simple = re.match(
        r"^(\d{1,2}) ([A-Za-z]{3}) @ (\d{1,2}:\d{2}[ap]m)",
        date_str,
    )
    match_en_full = re.match(
        r"^(\d{4}) 年 (\d{1,2}) ([A-Za-z]{3}) @ (\d{1,2}:\d{2}[ap]m)",
        date_str,
    )
    match_en_month_first = re.match(
        r"^([A-Za-z]{3}) (\d{1,2}) @ (\d{1,2}:\d{2}[ap]m)",
        date_str,
    )

    if match_en:
        # 可能是 2017 年 12 Dec @ 7:12am 或 12 Dec @ 7:12am
        year = match_en.group(1) or str(datetime.now().year)
        d1 = match_en.group(2)
        d2 = match_en.group(3)
        time_str = match_en.group(4)
        # 解析月和日
        try:
            # d1 数字: 日，d2 英文: 月
            day = int(d1)
            month = d2
        except ValueError:
            # d1 英文: 月，d2 数字: 日
            month = d1
            day = int(d2)
        dt_str = f"{year} {month} {day} {time_str}"
        try:
            return datetime.strptime(dt_str, "%Y %b %d %I:%M%p")
        except Exception:
            pass

    elif match_en_full:
        # 2017 年 12 Dec @ 7:12am
        year = match_en_full.group(1)
        day = match_en_full.group(2)
        month = match_en_full.group(3)
        time_str = match_en_full.group(4)
        dt_str = f"{year} {month} {int(day)} {time_str}"
        try:
            return datetime.strptime(dt_str, "%Y %b %d %I:%M%p")
        except Exception:
            pass

    elif match_en_simple:
        # 12 Dec @ 7:12am
        day = int(match_en_simple.group(1))
        month = match_en_simple.group(2)
        time_str = match_en_simple.group(3)
        year = str(datetime.now().year)
        dt_str = f"{year} {month} {day} {time_str}"
        try:
            return datetime.strptime(dt_str, "%Y %b %d %I:%M%p")
        except Exception:
            pass

    elif match_en_month_first:
        # Dec 12 @ 7:12am
        month = match_en_month_first.group(1)
        day = int(match_en_month_first.group(2))
        time_str = match_en_month_first.group(3)
        year = str(datetime.now().year)
        dt_str = f"{year} {month} {day} {time_str}"
        try:
            return datetime.strptime(dt_str, "%Y %b %d %I:%M%p")
        except Exception:
            pass

    # 中文格式
    # 年份处理
    if "年" not in date_str:
        date_str = f"{datetime.now().year} 年 {date_str}"

    if "下午" in date_str:
        m = re.search(r"下午\s*(\d{1,2}):(\d{2})", date_str)
        if m:
            hour = int(m.group(1))
            minute = m.group(2)
            # 12 点特殊处理
            if hour < 12:
                hour += 12
            time_str = f"{hour}:{minute}"
            date_str = re.sub(r"下午\s*\d{1,2}:\d{2}", time_str, date_str)
        date_str = date_str.replace("下午", "")
    elif "上午" in date_str:
        date_str = date_str.replace("上午", "")
        # 保证没有多余空格
        date_str = re.sub(r"\s+", " ", date_str)
    else:
        date_str = re.sub(r"\s+", " ", date_str)

    # 尝试如常规中文日期
    formats = [
        "%Y 年 %m 月 %d 日 %H:%M",
        "%Y 年 %m 月 %d 日 %H:%M",
        "%Y 年 %m %b @ %I:%M%p",  # 为兼容保留
        "%Y 年 %d %b @ %I:%M%p",
        "%Y 年 %b %d @ %I:%M%p",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except Exception:
            continue

    raise ValueError(
        f"time data '{date_str}' does not match supported formats: {formats}"
    )


def file_size_formater(file_size: str | None) -> int:
    """
    文件大小格式化
    77.308 KB -> 77308
    1.633 MB -> 1633000

    """
    if not file_size:
        return 0

    s = file_size.strip()

    # Common Steam formats like "77.308 KB", "1.633 MB", "2.1 GB"
    if "KB" in s:
        return int(float(s.split(" ")[0]) * 1024)
    if "MB" in s:
        return int(float(s.split(" ")[0]) * 1024 * 1024)
    if "GB" in s:
        return int(float(s.split(" ")[0]) * 1024 * 1024 * 1024)

    # Plain integer strings like "123456"
    if s.isdigit():
        return int(s)

    # Fallback: extract digits from formats like "123 bytes", "Size: 1234"
    digits = re.sub(r"[^0-9]", "", s)
    return int(digits) if digits else 0

def image_url_formater(image_url: str | None) -> str | None:
    """
    图片URL格式化
    """
    if not image_url:
        return None
    
    block_images = ["zoom_icon.png", "icon_thumbsup.png", "icon_thumbsdown.png", 'trans.gif', "steam_workshop_default_image.png"]
    for block_image in block_images:
        if block_image in image_url:
            return None

    if "?" in image_url:
        return image_url.split("?")[0]
    

    return image_url