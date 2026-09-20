"""Logging centralisé pour le pipeline multi-processus.

Le processus principal configure les handlers (stream + fichier) et démarre un
QueueListener. Chaque sous-processus (spawn) attache un unique QueueHandler à
son root logger via `setup_worker_logging`, ce qui redirige tous ses logs vers
le processus principal pour un fichier unifié.
"""

import logging
import multiprocessing
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler

LOG_FORMAT = "%(asctime)s - %(processName)s - %(name)s - %(levelname)s - %(message)s"

# Rotation : 5 Mo par fichier, 3 archives conservées (.log.1, .log.2, .log.3)
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3


def setup_main_logging(log_path="compost_process.log", level=logging.INFO):
    """Configure le logging du processus principal et retourne la queue partagée.

    Returns (log_queue, listener). L'appelant doit garder une référence au
    listener et appeler listener.stop() en fin de vie pour flusher proprement.
    Le fichier de log est rotaté automatiquement (5 Mo × 3 archives).
    """
    formatter = logging.Formatter(LOG_FORMAT)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        str(log_path), maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    # Remplacer les handlers existants pour éviter les doublons sur re-init
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(stream_handler)
    root.addHandler(file_handler)

    log_queue = multiprocessing.Queue(-1)
    listener = QueueListener(log_queue, stream_handler, file_handler,
                             respect_handler_level=True)
    listener.start()
    return log_queue, listener


def setup_worker_logging(log_queue, level=logging.INFO):
    """À appeler au démarrage de chaque sous-processus.

    Si log_queue est None (process lancé hors orchestrateur), on retombe sur
    une config locale stream-only pour rester utilisable en standalone.
    """
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)

    if log_queue is not None:
        root.addHandler(QueueHandler(log_queue))
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(handler)
