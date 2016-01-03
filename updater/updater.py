# coding: utf-8
import requests
import json
import re
import logging
import sys

URL = 'https://2ch.hk/b/index.json'
BASEURL = 'https://2ch.hk/b/'
if sys.platform == 'win32':
    # GnuTLS crashes on HTTPS, dunno why.
    BASEURL = 'http://2ch.hk/b/'

class Thread(object):
    def __init__(self, url=None):
        self.logger = logging.getLogger('thread')
        self.url = url
        self.data = None
        self.videos = list()
        self.lastupdated = None
        self.old_latest_video_index = -1
        self.latest_video_index = -1

    def __str__(self):
        return self.url

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        return self.url == other.url

    def download(self, requests_session = None):
        if requests_session:
            req = requests_session
        else:
            req = requests.Session()

        self.data = req.get(BASEURL + self.url)
        if self.data.status_code != requests.codes.ok:
            self.logger.info('Thread is unavailable')
            return False
        return True

    def parsevideos(self):
        self.videos.clear()

        try:
            parser = json.loads(self.data.text)
        except:
            self.logger.error('Cannot parse thread JSON')
            return

        for post in parser['threads'][0]['posts']:
            for postfile in post['files']:
                if '.webm' in postfile['path']:
                    webm = BASEURL + postfile['path']
                    self.videos.append(webm)

        self.logger.info("New videos: {}".format(len(self.videos) - self.latest_video_index))
        self.old_latest_video_index = self.latest_video_index
        self.latest_video_index = len(self.videos)

    def get_new_videos_list(self):
        ret = list()
        self.logger.debug('old_latest {}'.format(self.old_latest_video_index))
        for i, video in enumerate(self.videos):
            if i > self.old_latest_video_index:
                ret.append(video)
        self.old_latest_video_index = self.latest_video_index
        return ret
                

class Board(object):
    def __init__(self):
        self.logger = logging.getLogger('board')
        self.req = requests.Session()
        self.threads = list()
        self.data = None

    def update(self):
        self.data = self.req.get(URL)

    def find_threads(self):
        try:
            parser = json.loads(self.data.text)
        except:
            self.logger.error('Cannot parse board JSON')
            return

        for thread in parser['threads']:
                url = '/res/' + thread['posts'][0]['num'] + '.json'
                body = thread['posts'][0]['comment']
                is_webm = any(['webm' in file['path'] for file in thread['posts'][0]['files']])
                if re.search(r'([Ww][Ee][Bb][Mm])|([Цц][Уу][Ии][Ьь])|([ВвШш][Ее][Бб][Мм])', body) and is_webm:
                    if Thread(url) not in self.threads:
                        self.logger.info('Found new Webm thread: {}'.format(BASEURL + url))
                        self.threads.append(Thread(url))
        if not self.threads:
            self.logger.info('No threads found!')

    def parse_threads(self):
        for thread in self.threads:
            if not thread.download(self.req):
                self.logger.debug('removing thread')
                self.threads.remove(thread)
            else:
                self.logger.debug('parsing thread')
                thread.parsevideos()
    
    def get_new_videos_list(self):
        ret = list()
        for thread in self.threads:
            for video in thread.get_new_videos_list():
                ret.append(video)
        return ret
