from datetime import datetime


def date_formater(date_str: str | None) -> datetime | None:
    """
    10 月 18 日 下午 11:37
    2017 年 12 月 2 日 上午 10:37
    转为datetime格式
    """
    if not date_str:
        return None

    if "年" not in date_str:
        date_str = f"{datetime.now().year} 年 {date_str}"

    if "下午" in date_str:
        time_str = date_str.split("下午")[1].strip()
        hour_str = int(time_str.split(":")[0]) + 12
        minute_str = time_str.split(":")[1]
        time_str = f"{hour_str}:{minute_str}"
        date_str = f"{date_str.split('下午')[0].strip()} {time_str}"
    else:
        date_str = date_str.replace("上午", "").replace("  ", " ")

    # Handle multiple date formats for robustness
    formats = [
        "%Y 年 %m 月 %d 日 %H:%M",
        "%Y 年 %m 月 %d 日 %H:%M",
        "%Y 年 %m %b @ %I:%M%p",  # e.g., 2025 年 1 Nov @ 8:30am
        "%Y 年 %d %b @ %I:%M%p",  # e.g., 2025 年 1 Nov @ 8:30am
        "%Y 年 %b %d @ %I:%M%p",  # e.g., 2025 年 Nov 1 @ 8:30am
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
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

    if "KB" in file_size:
        return int(float(file_size.split(" ")[0]) * 1024)
    elif "MB" in file_size:
        return int(float(file_size.split(" ")[0]) * 1024 * 1024)
    elif "GB" in file_size:
        return int(float(file_size.split(" ")[0]) * 1024 * 1024 * 1024)

    return file_size