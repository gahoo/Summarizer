import functools
import os

def set_proxy(func, proxy_env='GEMINI_PROXY'):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        proxy = os.getenv(proxy_env, '')
        if proxy:
            http_proxy = os.environ.pop('http_proxy', '')
            https_proxy = os.environ.pop('https_proxy', '')

            os.environ['http_proxy'] = os.getenv(proxy_env, '')
            os.environ['https_proxy'] = os.getenv(proxy_env, '')

        result = func(*args, **kwargs)

        if proxy:
            os.environ['http_proxy'] = http_proxy
            os.environ['https_proxy'] = https_proxy
        return result
    return wrapper

def undo_proxy(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        http_proxy = os.environ.pop('http_proxy', None)
        https_proxy = os.environ.pop('https_proxy', None)

        result = func(*args, **kwargs)

        os.environ['http_proxy'] = http_proxy
        os.environ['https_proxy'] = https_proxy
        return result
    return wrapper