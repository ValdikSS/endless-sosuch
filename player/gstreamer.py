# coding: utf-8 
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst, Gtk, Gdk
from gi.repository import GdkX11, GstVideo
import queue
import os
import random
import time
import logging
import glob

GObject.threads_init()
Gst.init(None)

class NoDirectoryException(Exception):
    pass

class Player(object):
    def __init__(self):
        self.logger = logging.getLogger('video')
        self.window = Gtk.Window()
        self.window.connect('destroy', self.quit)
        self.window.set_default_size(800, 450)

        self.drawingarea = Gtk.DrawingArea()
        self.window.add(self.drawingarea)
        self.window.connect("key-release-event", self.on_key_release)

        # Create GStreamer pipeline
        self.pipeline = Gst.Pipeline()

        # Create bus to get events from GStreamer pipeline
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect('message::eos', self.on_eos)
        self.bus.connect('message::error', self.on_error)

        # This is needed to make the video output in our DrawingArea:
        self.bus.enable_sync_message_emission()
        self.bus.connect('sync-message::element', self.on_sync_message)

        # Create GStreamer elements
        self.playbin = Gst.ElementFactory.make('playbin', None)

        # Add playbin to the pipeline
        self.pipeline.add(self.playbin)
        
        # Add video queue
        self.videoqueue = queue.Queue()
        self.randomdir = None
        self.window_is_fullscreen = False
        self.is_paused = False
        self.uri = None
        self.empty_queue_callback = None
        
    def seturi(self, uri):
        # Set properties
        self.playbin.set_property('uri', uri)
        self.uri = uri

    def run(self):
        self.window.show_all()
        # You need to get the XID after window.show_all().  You shouldn't get it
        # in the on_sync_message() handler because threading issues will cause
        # segfaults there.
        self.xid = self.drawingarea.get_property('window').get_xid()
        self.seturi(self.get_queued_or_random())
        self.play()
        Gtk.main()
        
    def play(self):
        self.pipeline.set_state(Gst.State.PLAYING)
        self.logger.info('Playing {}'.format(self.uri))
        self.is_paused = False

    def pause(self):
        self.pipeline.set_state(Gst.State.PAUSED)
        self.is_paused = True
        
    def stop(self):
        self.pipeline.set_state(Gst.State.NULL)
    
    def quit(self, window = None):
        self.stop()
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
            return 'file://' + random.choice(glob.glob(os.path.abspath(self.randomdir) + '/*.webm'))
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

    def on_sync_message(self, bus, msg):
        if msg.get_structure().get_name() == 'prepare-window-handle':
            self.logger.debug('prepare-window-handle')
            msg.src.set_window_handle(self.xid)

    def on_eos(self, bus, msg):
        self.logger.debug('on_eos()')
        self.stop()
        self.pipeline.remove(self.playbin)
        self.playbin = Gst.ElementFactory.make('playbin', None)
        self.pipeline.add(self.playbin)
        self.seturi(self.get_queued_or_random())
        self.play()

    def on_error(self, bus, msg):
        self.logger.error('on_error(): {}'.format(msg.parse_error()))
        time.sleep(1)
        self.on_eos()

    def on_key_release(self, window, ev, data=None):
        if ev.keyval == Gdk.KEY_s or ev.keyval == Gdk.KEY_S:
            self.on_eos(None, None)
        elif ev.keyval == Gdk.KEY_Escape or ev.keyval == Gdk.KEY_q or ev.keyval == Gdk.KEY_Q:
            self.quit()
        elif ev.keyval == Gdk.KEY_f or ev.keyval == Gdk.KEY_F:
            self.toggle_fullscreen()
        elif ev.keyval == Gdk.KEY_space:
            self.toggle_play()
