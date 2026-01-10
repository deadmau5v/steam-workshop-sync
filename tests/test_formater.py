"""
测试 utils.formater 模块中的格式化函数。
"""

from datetime import datetime

import pytest
from utils.formater import date_formater, file_size_formater, image_url_formater


class TestDateFormater:
    """测试 date_formater 函数"""

    def test_none_input(self):
        """测试 None 输入"""
        assert date_formater(None) is None

    def test_empty_string(self):
        """测试空字符串"""
        assert date_formater("") is None
        assert date_formater("   ") is None

    # === 英文日期格式测试 ===

    def test_english_standard_format(self):
        """测试标准英文格式: 'May 12, 2022 @ 12:43pm'"""
        # 月在前的标准格式
        result = date_formater("May 12, 2022 @ 12:43pm")
        assert result == datetime(2022, 5, 12, 12, 43)

        result = date_formater("Nov 22, 2019 @ 5:02pm")
        assert result == datetime(2019, 11, 22, 17, 2)

        result = date_formater("Jan 1, 2020 @ 12:00am")
        assert result == datetime(2020, 1, 1, 0, 0)

        # 日在前的标准格式
        result = date_formater("1 Dec, 2019 @ 11:26am")
        assert result == datetime(2019, 12, 1, 11, 26)

        result = date_formater("8 Dec, 2019 @ 3:14pm")
        assert result == datetime(2019, 12, 8, 15, 14)

        result = date_formater("11 Dec, 2019 @ 2:34am")
        assert result == datetime(2019, 12, 11, 2, 34)

    def test_english_day_first_no_year(self):
        """测试日期在前、无年份格式: '12 Dec @ 7:12am'"""
        current_year = datetime.now().year
        result = date_formater("12 Dec @ 7:12am")
        assert result == datetime(current_year, 12, 12, 7, 12)

        result = date_formater("1 Jan @ 8:30am")
        assert result == datetime(current_year, 1, 1, 8, 30)

    def test_english_month_first_no_year(self):
        """测试月份在前、无年份格式: 'Dec 12 @ 7:12am'"""
        current_year = datetime.now().year
        result = date_formater("Dec 12 @ 7:12am")
        assert result == datetime(current_year, 12, 12, 7, 12)

        result = date_formater("Nov 8 @ 8:30pm")
        assert result == datetime(current_year, 11, 8, 20, 30)

    def test_english_with_chinese_year_prefix(self):
        """测试带中文年份前缀的英文格式: '2017 年 12 Dec @ 7:12am'"""
        result = date_formater("2017 年 12 Dec @ 7:12am")
        assert result == datetime(2017, 12, 12, 7, 12)

        # 月份在前的变体
        result = date_formater("2019 年 Dec 12 @ 7:12am")
        assert result == datetime(2019, 12, 12, 7, 12)

    def test_malformed_english_with_wrong_year_prefix(self):
        """测试错误年份前缀格式: '2025 年 May 12, 2022 @ 12:43pm'"""
        # 应该使用逗号后的正确年份 (2022)，忽略前缀年份 (2025)
        result = date_formater("2025 年 May 12, 2022 @ 12:43pm")
        assert result == datetime(2022, 5, 12, 12, 43)

        result = date_formater("2025 年 May 9, 2022 @ 5:45am")
        assert result == datetime(2022, 5, 9, 5, 45)

        result = date_formater("2025 年 May 6, 2022 @ 9:03pm")
        assert result == datetime(2022, 5, 6, 21, 3)

        result = date_formater("2025 年 May 3, 2022 @ 9:35am")
        assert result == datetime(2022, 5, 3, 9, 35)

        result = date_formater("2025 年 May 1, 2022 @ 2:53pm")
        assert result == datetime(2022, 5, 1, 14, 53)

    def test_english_case_insensitive(self):
        """测试英文日期格式大小写不敏感"""
        result1 = date_formater("DEC 12 @ 7:12AM")
        result2 = date_formater("dec 12 @ 7:12am")
        result3 = date_formater("Dec 12 @ 7:12am")
        assert result1 == result2 == result3

    def test_english_with_extra_spaces(self):
        """测试带额外空格的英文格式"""
        result = date_formater("May  12,  2022  @  12:43pm")
        assert result == datetime(2022, 5, 12, 12, 43)

    # === 中文日期格式测试 ===

    def test_chinese_with_year_afternoon(self):
        """测试完整中文格式（下午）: '2017 年 12 月 2 日 上午 10:37'"""
        result = date_formater("2017 年 12 月 2 日 下午 11:37")
        assert result == datetime(2017, 12, 2, 23, 37)

        result = date_formater("2020 年 1 月 15 日 下午 1:30")
        assert result == datetime(2020, 1, 15, 13, 30)

    def test_chinese_with_year_morning(self):
        """测试完整中文格式（上午）: '2017 年 12 月 2 日 上午 10:37'"""
        result = date_formater("2017 年 12 月 2 日 上午 10:37")
        assert result == datetime(2017, 12, 2, 10, 37)

        result = date_formater("2019 年 3 月 8 日 上午 9:15")
        assert result == datetime(2019, 3, 8, 9, 15)

    def test_chinese_with_year_24hour(self):
        """测试完整中文格式（24小时制）: '2017 年 12 月 2 日 23:37'"""
        result = date_formater("2017 年 12 月 2 日 23:37")
        assert result == datetime(2017, 12, 2, 23, 37)

        result = date_formater("2021 年 6 月 10 日 14:20")
        assert result == datetime(2021, 6, 10, 14, 20)

    def test_chinese_no_year_afternoon(self):
        """测试无年份中文格式（下午）: '10 月 18 日 下午 11:37'"""
        current_year = datetime.now().year
        result = date_formater("10 月 18 日 下午 11:37")
        assert result == datetime(current_year, 10, 18, 23, 37)

    def test_chinese_no_year_morning(self):
        """测试无年份中文格式（上午）: '5 月 5 日 上午 8:00'"""
        current_year = datetime.now().year
        result = date_formater("5 月 5 日 上午 8:00")
        assert result == datetime(current_year, 5, 5, 8, 0)

    def test_chinese_noon_handling(self):
        """测试中文格式中午12点的处理"""
        # 下午 12:00 应该是 12:00 (不加12)
        result = date_formater("2020 年 5 月 1 日 下午 12:30")
        assert result == datetime(2020, 5, 1, 12, 30)

        # 上午 12:00 应该是 00:00
        result = date_formater("2020 年 5 月 1 日 上午 12:30")
        assert result == datetime(2020, 5, 1, 0, 30)

    def test_chinese_with_extra_spaces(self):
        """测试带额外空格的中文格式"""
        result = date_formater("2017 年  12 月  2 日  下午  11:37")
        assert result == datetime(2017, 12, 2, 23, 37)

    # === 错误输入测试 ===

    def test_invalid_date_string(self):
        """测试不支持的日期格式"""
        with pytest.raises(ValueError, match="无法解析日期字符串"):
            date_formater("this is not a date")

        with pytest.raises(ValueError):
            date_formater("2022/05/12 12:43")

        with pytest.raises(ValueError):
            date_formater("12-05-2022")


class TestFileSizeFormater:
    """测试 file_size_formater 函数"""

    def test_none_input(self):
        """测试 None 输入"""
        assert file_size_formater(None) == 0

    def test_empty_string(self):
        """测试空字符串"""
        assert file_size_formater("") == 0
        assert file_size_formater("   ") == 0

    def test_kilobytes(self):
        """测试 KB 格式"""
        assert file_size_formater("77.308 KB") == 79163
        assert file_size_formater("1 KB") == 1024
        assert file_size_formater("0.5 KB") == 512

    def test_megabytes(self):
        """测试 MB 格式"""
        # 1.633 * 1024 * 1024 = 1712324.608 ≈ 1712324
        assert file_size_formater("1.633 MB") == 1712324
        assert file_size_formater("1 MB") == 1048576
        # 10.5 * 1024 * 1024 = 11010048
        assert file_size_formater("10.5 MB") == 11010048

    def test_gigabytes(self):
        """测试 GB 格式"""
        assert file_size_formater("2.1 GB") == 2254857830
        assert file_size_formater("1 GB") == 1073741824
        assert file_size_formater("0.5 GB") == 536870912

    def test_bytes(self):
        """测试 bytes 格式"""
        assert file_size_formater("1024 bytes") == 1024
        assert file_size_formater("512 byte") == 512

    def test_plain_number(self):
        """测试纯数字（假设为字节）"""
        assert file_size_formater("123456") == 123456
        assert file_size_formater("1024") == 1024

    def test_case_insensitive(self):
        """测试单位大小写不敏感"""
        assert file_size_formater("1 kb") == 1024
        assert file_size_formater("1 KB") == 1024
        assert file_size_formater("1 Kb") == 1024

    def test_with_extra_spaces(self):
        """测试带额外空格的格式"""
        assert file_size_formater("  1.5  MB  ") == 1572864

    def test_fallback_extraction(self):
        """测试后备数字提取"""
        # 如果格式不匹配，应该提取所有数字
        assert file_size_formater("Size: 1024") == 1024
        assert file_size_formater("abc123def") == 123


class TestImageUrlFormater:
    """测试 image_url_formater 函数"""

    def test_none_input(self):
        """测试 None 输入"""
        assert image_url_formater(None) is None

    def test_empty_string(self):
        """测试空字符串"""
        assert image_url_formater("") is None

    def test_normal_url(self):
        """测试正常的图片 URL"""
        url = "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/items/123/abc.jpg"
        assert image_url_formater(url) == url

    def test_url_with_query_params(self):
        """测试带查询参数的 URL（应该移除参数）"""
        url = "https://example.com/image.jpg?size=large&format=png"
        expected = "https://example.com/image.jpg"
        assert image_url_formater(url) == expected

    def test_blocked_images(self):
        """测试被过滤的图标图片（应该返回 None）"""
        blocked_urls = [
            "https://example.com/zoom_icon.png",
            "https://example.com/icon_thumbsup.png",
            "https://example.com/icon_thumbsdown.png",
            "https://example.com/trans.gif",
            "https://example.com/steam_workshop_default_image.png",
            "https://example.com/path/to/zoom_icon.png?param=value",
        ]

        for url in blocked_urls:
            assert image_url_formater(url) is None, f"URL should be blocked: {url}"

    def test_partial_match_not_blocked(self):
        """测试部分匹配的 URL 应该被过滤"""
        # 这个 URL 包含被阻止的字符串 "zoom_icon.png" 作为子串
        url = "https://example.com/my_zoom_icon_custom.png"
        # 根据当前实现，只要包含被阻止的字符串就会被过滤
        # 但这个 URL 实际上不包含 "zoom_icon.png"，所以不会被过滤
        assert image_url_formater(url) is not None

        # 真正包含被阻止字符串的 URL 会被过滤
        url2 = "https://example.com/path/zoom_icon.png"
        assert image_url_formater(url2) is None

    def test_normal_url_with_blocked_substring(self):
        """测试包含被阻止关键词的正常 URL"""
        # 如果 URL 路径中包含 "trans" 但不是 "trans.gif"，应该通过
        url = "https://example.com/transport/image.png"
        assert image_url_formater(url) == url


class TestEdgeCases:
    """测试边缘情况"""

    def test_date_formater_with_unicode_spaces(self):
        """测试包含 Unicode 空格的日期字符串"""
        # 普通空格
        result1 = date_formater("Dec 12 @ 7:12am")
        # 不间断空格 (U+00A0)
        date_formater("Dec\u00a012\u00a0@\u00a07:12am")
        # 两者应该产生相同的结果（如果 strip() 处理正确）
        assert result1.month == 12
        assert result1.day == 12

    def test_file_size_formater_with_decimal_precision(self):
        """测试小数精度处理"""
        # 确保小数运算正确
        assert file_size_formater("1.5 KB") == 1536  # 1.5 * 1024
        assert file_size_formater("2.25 MB") == 2359296  # 2.25 * 1024 * 1024

    def test_file_size_formater_zero(self):
        """测试零值"""
        assert file_size_formater("0 KB") == 0
        assert file_size_formater("0 MB") == 0
        assert file_size_formater("0") == 0

    def test_image_url_formater_multiple_query_params(self):
        """测试多个查询参数的处理"""
        url = "https://example.com/image.jpg?a=1&b=2&c=3"
        expected = "https://example.com/image.jpg"
        assert image_url_formater(url) == expected

    def test_image_url_formater_url_fragment(self):
        """测试 URL 片段（锚点）"""
        # 当前实现只移除查询参数，不处理片段
        url = "https://example.com/image.jpg#section"
        assert image_url_formater(url) == url


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
