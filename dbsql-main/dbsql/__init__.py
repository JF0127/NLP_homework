import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(filename)s | %(levelname)s | \n%(message)s')
handler.setFormatter(formatter)

logger.addHandler(handler)