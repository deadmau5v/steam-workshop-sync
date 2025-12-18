import logging


handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("[%(levelname)s] %(message)s")
handler.setFormatter(formatter)


def get_logger(name: str):
    logger = logging.Logger(name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)

    return logger
