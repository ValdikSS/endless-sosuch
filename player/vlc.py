# coding: utf-8 
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst, Gtk, Gdk
from gi.repository import GdkX11
import queue
import os
import sys
import os.path
import random
import time
import logging
import glob
import player.vlcbind.vlc as vlc
import ctypes
import threading

GObject.threads_init()
Gst.init(None)

class NoDirectoryException(Exception):
    pass


class Player(object):
    def __init__(self, file_save_dir=None, use_compressor=False, video_sink=None, audio_sink=None):
        self.logger = logging.getLogger('video')
        self.window = Gtk.Window()
        self.window.connect('destroy', self.quit)
        self.window.set_default_size(800, 450)
        self.window.set_title('Endless Sosuch')

        self.drawingarea = Gtk.DrawingArea()
        self.window.add(self.drawingarea)
        self.window.connect("key-release-event", self.on_key_release)

        if sys.platform == 'linux':
            self.x11 = ctypes.cdll.LoadLibrary('libX11.so')
            self.x11.XInitThreads()

        self.instance = vlc.Instance('--sout-mux-caching 100 ' + 
                                     ('--vout ' + video_sink if video_sink else '') +
                                     ('--aout ' + audio_sink if audio_sink else '') +
                                     ('--audio-filter compress,volnorm --compressor-ratio 5 --compressor-threshold -10 --norm-max-level -3' if use_compressor else '')
                                    )
        self.vlc = self.instance.media_player_new()

        # Add video queue
        self.videoqueue = queue.Queue()
        self.randomdir = None
        self.file_save_dir = file_save_dir
        self.use_compressor = use_compressor
        self.video_sink = video_sink
        self.audio_sink = audio_sink
        self.window_is_fullscreen = False
        self.is_paused = True
        self.uri = None
        self.empty_queue_callback = None
        self.user_agent = None
        self.cookie = None
        self.thread_queue = queue.Queue()
        self.thread = threading.Thread(target=self.on_eos_thread).start()

    def seturi(self, uri):
        media = self.instance.media_new(uri)
        if ('http://' in uri or 'https://' in uri) and self.file_save_dir \
            and not os.path.isfile(self.file_save_dir + '/' + os.path.basename(uri)):
                media.add_option(':sout=#duplicate{dst=display,dst=std{access=file,dst="' +\
                    self.file_save_dir + '/' + os.path.basename(uri) + '"}}')
        
        self.vlc.set_media(media)
        self.window.set_title('Endless Sosuch | ' + os.path.basename(uri))
        self.uri = uri

    def run(self):
        self.window.show_all()
        # You need to get the XID after window.show_all().  You shouldn't get it
        # in the on_sync_message() handler because threading issues will cause
        # segfaults there.
        videowindow = self.drawingarea.get_property('window')
        if sys.platform == 'win32':
            ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
            ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object]
            drawingarea_gpointer = ctypes.pythonapi.PyCapsule_GetPointer(videowindow.__gpointer__, None)
            gdkdll = ctypes.CDLL ("libgdk-3-0.dll")
            self.xid = gdkdll.gdk_win32_window_get_handle(drawingarea_gpointer)
            self.vlc.set_hwnd(self.xid)
        else:
            self.xid = videowindow.get_xid()
            self.vlc.set_xwindow(self.xid)

        self.vlc.event_manager().event_attach(vlc.EventType.MediaPlayerEndReached, self.on_eos, 1)
        self.vlc.event_manager().event_attach(vlc.EventType.MediaPlayerEncounteredError, self.on_error, 1)
        self.instance.set_user_agent('http', self.user_agent)
        self.seturi(self.get_queued_or_random())
        self.play()
        
        Gtk.main()
        
    def play(self):
        if not self.is_paused:
            return

        self.vlc.play()
        self.logger.info('Playing {}'.format(self.uri))
        self.is_paused = False

    def pause(self):
        if self.is_paused:
            return

        self.vlc.pause()
        self.is_paused = True
        
    def stop(self, should_delete=False):
        self.vlc.stop()
        self.is_paused = True

        if should_delete and ('http://' in self.uri or 'https://' in self.uri) \
            and self.file_save_dir:
                os.remove(self.file_save_dir + '/' + os.path.basename(self.uri))
    
    def quit(self, window = None):
        self.stop(True)
        self.thread_queue.put(False)
        self.vlc.release()
        self.instance.release()
        Gtk.main_quit()

    def set_random_directory(self, randomdir):
        self.randomdir = randomdir

    def add_queue(self, item):
        self.videoqueue.put(item)

    def register_on_video_queue_empty_callback(self, callback):
        self.empty_queue_callback = callback

    def get_random(self):
        if self.randomdir is None:
            raise NoDirectoryException('Directory path is not set!')
        try:
            return random.choice(glob.glob(os.path.abspath(self.randomdir) + '/*.webm'))
        except IndexError:
            self.logger.error('Directory with random files is empty!')

    def get_queued_or_random(self):
        try:
            video = self.videoqueue.get_nowait()
        except queue.Empty:
            # get random video from folder
            video = self.get_random()
            if self.empty_queue_callback:
                self.empty_queue_callback()
        return video

    def toggle_fullscreen(self):
        if not self.window_is_fullscreen:
            self.window.fullscreen()
            self.window_is_fullscreen = True
        else:
            self.window.unfullscreen()
            self.window_is_fullscreen = False
        #self.window.resize(*self.window.get_size())
        self.window.show_all()

    def toggle_play(self):
        if not self.is_paused:
            self.pause()
        else:
            self.play()
    
    def on_eos_thread(self):
        while True:
            message = self.thread_queue.get()
            if message:
                self.stop()
                uri = self.get_queued_or_random()
                self.seturi(uri)
                self.play()
            else:
                self.logger.info('Quitting thread')
                break

    def on_eos(self, bus=None, msg=None):
        self.logger.debug('on_eos()')
        if bus or msg:
            self.thread_queue.put(True)
        else:
            self.stop(True)
            uri = self.get_queued_or_random()
            self.seturi(uri)
            self.play()

    def on_error(self, bus, msg):
        self.logger.error('on_error(): {}'.format(msg.parse_error()))
        time.sleep(1)
        self.thread_queue.put(True)

    def on_key_release(self, window, ev, data=None):
        if ev.keyval == Gdk.KEY_s or ev.keyval == Gdk.KEY_S:
            self.on_eos()
        if ev.keyval == Gdk.KEY_d or ev.keyval == Gdk.KEY_d:
            for i in range(9):
                try:
                    self.videoqueue.get_nowait()
                except queue.Empty:
                    break
            self.on_eos()
            # get random video from folder
        elif ev.keyval == Gdk.KEY_Escape or ev.keyval == Gdk.KEY_q or ev.keyval == Gdk.KEY_Q:
            self.quit()
        elif ev.keyval == Gdk.KEY_f or ev.keyval == Gdk.KEY_F:
            self.toggle_fullscreen()
        elif ev.keyval == Gdk.KEY_space:
            self.toggle_play()
