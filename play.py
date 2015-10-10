#!/usr/bin/env python3
# coding: utf-8
import player.gstreamer
import updater.updater
import signal
import logging
import config

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
signal.signal(signal.SIGINT, signal.SIG_DFL)
logger = logging.getLogger('main')

player = player.gstreamer.Player()
player.set_random_directory(config.RANDOM_PATH)

board = updater.updater.Board()

def on_empty_queue():
    logger.info('Queue is empty, updating')
    board.update()
    board.find_threads()
    board.parse_threads()
    for video in board.get_new_videos_list():
        logger.debug('Got video {}'.format(video))
        player.videoqueue.put(video)

player.register_on_video_queue_empty_callback(on_empty_queue)
on_empty_queue()

try:
    player.run()
finally:
    player.quit()