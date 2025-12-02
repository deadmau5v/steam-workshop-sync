from datetime import datetime


def date_formater(date_str: str):
    """
    10 月 18 日 下午 11:37
    2017 年 12 月 2 日 上午 10:37
    转为datetime格式
    """
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
    
    return datetime.strptime(date_str, "%Y 年 %m 月 %d 日 %H:%M")
