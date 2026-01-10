#!/usr/bin/env python3
"""测试下载 Workshop mod"""

from dotenv import load_dotenv
from spiders.workshop import Wrokshop

load_dotenv()

if __name__ == "__main__":
    ws = Wrokshop()
    item_id = "3458325698"

    print(f"开始测试下载 mod: {item_id}")
    print(f"Steam CMD 路径: {ws.steamcmd_path}")
    print(f"下载目录: {ws.download_dir}")
    print(f"Steam 用户名: {ws.steam_username}")
    print(f"APP ID: {ws.appid}")
    print("-" * 50)

    success = ws.download_mod(item_id)

    if success:
        print(f"✓ mod {item_id} 下载成功！")
    else:
        print(f"✗ mod {item_id} 下载失败！")
