#!/usr/bin/env python
# -*- coding: utf-8 -*-
 
import logging
 
from logging.handlers import RotatingFileHandler

class GtwLogger():
    def __init__(self, name ):
        
        # cr�ation de l'objet logger qui va nous servir � �crire dans les logs
        self.logger = logging.getLogger(name)
        
        # on met le niveau du logger � DEBUG, comme �a il �crit tout
        self.logger.setLevel(logging.DEBUG)
        
        logfile = "/var/log/gateway.log"
        # cr�ation d'un formateur qui va ajouter le temps, le niveau
        # de chaque message quand on �crira un message dans le log
        self.formatter = logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s')
        # cr�ation d'un handler qui va rediriger une �criture du log vers
        # un fichier en mode 'append', avec 1 backup et une taille max de 1Mo
        self.file_handler = RotatingFileHandler(logfile, , 'a', maxBytes=1000000, backupCount=1)
        # on lui met le niveau sur DEBUG, on lui dit qu'il doit utiliser le formateur
        # cr�� pr�c�dement et on ajoute ce handler au logger
        self.file_handler.setLevel(logging.DEBUG)
        self.file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        # cr�ation d'un second handler qui va rediriger chaque �criture de log
        # sur la console
        #stream_handler = logging.StreamHandler()
        #stream_handler.setLevel(logging.DEBUG)
        #logger.addHandler(stream_handler)
        
        # Apr�s 3 heures, on peut enfin logguer
        # Il est temps de spammer votre code avec des logs partout :
        #logger.info('Hello')
        #logger.warning('Testing %s', 'foo')
        
logger = GtwLogger('gtw_log')
