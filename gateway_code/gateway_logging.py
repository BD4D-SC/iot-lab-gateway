#!/usr/bin/env python
# -*- coding: utf-8 -*-


"""

Logger for gateway code

Set 'logfile' path with 'add_rotating_handler'.

Get logger with 'logger()'


"""

import logging
from logging.handlers import RotatingFileHandler

LOGGER = logging.getLogger()

# on met le niveau du logger � DEBUG, comme �a il �crit tout
LOGGER.setLevel(logging.DEBUG)


FORMATTER = logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s')
# cr�ation d'un handler qui va rediriger une �criture du log vers
# un fichier en mode 'append', avec 1 backup et une taille max de 1Mo

def add_rotating_handler(logfile):
    """
    Add a rotating file handler
    """
    file_handler = RotatingFileHandler(logfile, 'a', \
           maxBytes=1000000, backupCount=1)

    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(FORMATTER)

    LOGGER.addHandler(file_handler)

def logger():
    """
    :return: the logger
    """

    return LOGGER


# cr�ation d'un second handler qui va rediriger chaque �criture de log
# sur la console
#stream_handler = logging.StreamHandler()
#stream_handler.setLevel(logging.DEBUG)
#LOGGER.addHandler(stream_handler)

# Apr�s 3 heures, on peut enfin logguer
# Il est temps de spammer votre code avec des logs partout :
#LOGGER.info('Hello')
#LOGGER.warning('Testing %s', 'foo')

