# coding: utf-8
import requests
import pyquery
import re
import logging

URL = 'https://2ch.hk/b/'
BASEURL = 'https://2ch.hk'

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
        parser = pyquery.PyQuery(self.data.text)
        root = parser(".post-wrapper")

        for i, post in enumerate(root):
            is_webm = pyquery.PyQuery(post)(".webm-file")
            if is_webm:
                if i >= self.latest_video_index:
                    webm = is_webm.parent().attr('href')
                    self.videos.append(BASEURL + webm)
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
        parser = pyquery.PyQuery(self.data.text)
        root = parser("div.oppost-wrapper")
        
        for thread in root:
            url = pyquery.PyQuery(thread)(".orange").attr('href')
            body = pyquery.PyQuery(thread)(".post-message:first").text()
            op_data = pyquery.PyQuery(thread)("a.desktop").attr('href')
            is_webm = pyquery.PyQuery(thread)(".webm-file")
            if re.search(r'([Ww][Ee][Bb][Mm])|([Цц][Уу][Ии][Ьь])', body) and is_webm:
                if Thread(url) not in self.threads:
                    self.logger.info('Found new Webm thread: {}'.format(BASEURL + op_data))
                    self.threads.append(Thread(url))

    def parse_threads(self):
        for thread in self.threads:
            if not thread.download():
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
