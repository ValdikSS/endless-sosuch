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

player = player.gstreamer.Player(config.RANDOM_PATH if config.SAVE_FILES else None)
player.set_random_directory(config.RANDOM_PATH)

player.cookie = config.CF_COOKIE
player.user_agent = config.CF_USER_AGENT

board = updater.updater.Board()
board.req.cookies.set('cf_clearance', config.CF_COOKIE)
board.req.headers['User-Agent'] = config.CF_USER_AGENT

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