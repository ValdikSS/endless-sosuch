#!/usr/bin/env python3
# coding: utf-8
import updater.updater
import signal
import logging
import config
import re

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
signal.signal(signal.SIGINT, signal.SIG_DFL)
logger = logging.getLogger('main')

if config.BACKEND == 'gstreamer':
    import player.gstreamer
    player = player.gstreamer.Player(
        config.RANDOM_PATH if config.SAVE_FILES else None,
        config.AUDIO_COMPRESSOR,
        config.GSTREAMER_VIDEO_SINK,
        config.GSTREAMER_AUDIO_SINK,
        config.GSTREAMER_ADDITIONAL_PIPELINE,
        config.GSTREAMER_BUFFERING
    )
elif config.BACKEND == 'vlc':
    import player.vlc
    player = player.vlc.Player(
        config.RANDOM_PATH if config.SAVE_FILES else None,
        config.AUDIO_COMPRESSOR,
        config.VLC_VIDEO_SINK,
        config.VLC_AUDIO_SINK
    )
else:
    logger.error('No working backend set!')
    quit()

player.set_random_directory(config.RANDOM_PATH)

player.cookie = config.CF_COOKIE
player.user_agent = config.CF_USER_AGENT

board = updater.updater.Board()
board.req.cookies.set('cf_clearance', config.CF_COOKIE)
board.req.headers['User-Agent'] = config.CF_USER_AGENT

try:
    compiled_include_keywords = re.compile(config.INCLUDE_KEYWORDS)
    compiled_exclude_keywords = re.compile(config.EXCLUDE_KEYWORDS) if config.EXCLUDE_KEYWORDS else ''
except (ConfigurationError, AttributeError, TypeError, NameError):
    logger.fatal("You should set both INCLUDE_KEYWORDS and EXCLUDE_KEYWORDS in the configuration file!")
    quit(1)

def on_empty_queue():
    logger.info('Queue is empty, updating')
    board.update()
    board.find_threads(compiled_include_keywords, compiled_exclude_keywords)
    board.parse_threads()
    for video in board.get_new_videos_list():
        logger.debug('Got video {}'.format(video))
        player.videoqueue.put(video)

player.register_on_video_queue_empty_callback(on_empty_queue)
on_empty_queue()

if __name__ == '__main__':
    player.run()
