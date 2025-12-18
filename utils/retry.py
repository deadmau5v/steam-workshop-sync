import time
import functools
from typing import Callable, Any
from utils.log import get_logger

logger = get_logger(__name__)


def _calculate_wait_time(retry_count: int, base: float, maximum: float) -> float:
    """计算指数退避等待时间"""
    return min(base * (2 ** (retry_count - 1)), maximum)


def _should_retry_status(status_code: int, retry_config: dict, default_retry: bool) -> bool:
    """判断状态码是否需要重试"""
    if status_code in retry_config:
        return True
    return default_retry and status_code >= 400


def _get_max_retry_for_status(status_code: int, retry_config: dict, default_max: int) -> int | None:
    """获取状态码对应的最大重试次数"""
    return retry_config.get(status_code, default_max)


def _log_retry(error_key: str, current: int, maximum: int | None, wait: float):
    """记录重试日志"""
    max_str = "" if maximum is None else f"/{maximum}"
    logger.warning(f"{error_key} 错误，第 {current} 次重试{max_str}，等待 {wait:.1f} 秒...")


def retry_on_error(
    max_retries: int = 3,
    backoff_base: float = 1.0,
    backoff_max: float = 300.0,
    retry_on_status: dict[int, int | None] = None,
    default_retry: bool = True
):
    """
    通用重试装饰器
    
    Args:
        max_retries: 默认最大重试次数（None表示无限重试）
        backoff_base: 退避基数（秒）
        backoff_max: 最大退避时间（秒）
        retry_on_status: HTTP状态码重试策略 {状态码: 重试次数}，None表示无限重试
        default_retry: 对于未指定的状态码，是否使用默认重试次数
        
    示例:
        @retry_on_error(
            max_retries=3,
            retry_on_status={429: None, 500: 5},  # 429无限重试，500重试5次
        )
        def my_request():
            ...
    """
    retry_config = retry_on_status or {}
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            retry_counts = {}
            
            while True:
                try:
                    result = func(*args, **kwargs)
                    
                    # 非 Response 对象直接返回
                    if not hasattr(result, 'status_code'):
                        return result
                    
                    status_code = result.status_code
                    
                    # 不需要重试，直接返回
                    if not _should_retry_status(status_code, retry_config, default_retry):
                        return result
                    
                    # 初始化并递增重试计数
                    retry_counts[status_code] = retry_counts.get(status_code, 0) + 1
                    current_retry = retry_counts[status_code]
                    
                    # 获取最大重试次数
                    max_retry = _get_max_retry_for_status(status_code, retry_config, max_retries)
                    
                    # 超过最大重试次数
                    if max_retry is not None and current_retry > max_retry:
                        return result
                    
                    # 等待并重试
                    wait_time = _calculate_wait_time(current_retry, backoff_base, backoff_max)
                    _log_retry(f"HTTP {status_code}", current_retry, max_retry, wait_time)
                    time.sleep(wait_time)
                    
                except Exception as e:
                    if not _handle_exception(e, retry_counts, retry_config, backoff_base, backoff_max):
                        raise
        
        return wrapper
    return decorator


def _handle_exception(
    exception: Exception,
    retry_counts: dict,
    retry_config: dict,
    backoff_base: float,
    backoff_max: float
) -> bool:
    """
    处理异常，判断是否需要重试
    
    Returns:
        bool: True表示已处理并需要重试，False表示未处理需要抛出
    """
    error_type = type(exception).__name__
    exception_str = str(exception)
    
    # 查找异常中包含的状态码
    for status_code, max_retry in retry_config.items():
        if str(status_code) not in exception_str:
            continue
        
        # 初始化并递增重试计数
        retry_counts[error_type] = retry_counts.get(error_type, 0) + 1
        current_retry = retry_counts[error_type]
        
        # 超过最大重试次数
        if max_retry is not None and current_retry > max_retry:
            return False
        
        # 等待并重试
        wait_time = _calculate_wait_time(current_retry, backoff_base, backoff_max)
        _log_retry(f"{error_type} (HTTP {status_code})", current_retry, max_retry, wait_time)
        time.sleep(wait_time)
        return True
    
    # 未找到匹配的状态码
    return False

