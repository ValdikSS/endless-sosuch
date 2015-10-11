# coding: utf-8 
import gi
gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst, Gtk, Gdk
from gi.repository import GdkX11, GstVideo
import queue
import os
import os.path
import random
import time
import logging
import glob

GObject.threads_init()
Gst.init(None)

class NoDirectoryException(Exception):
    pass

class Player(object):
    def __init__(self, file_save_dir=False, use_compressor=False):
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
        self.bus.connect('message::buffering', self.on_buffering)

        # This is needed to make the video output in our DrawingArea:
        self.bus.enable_sync_message_emission()
        self.bus.connect('sync-message::element', self.on_sync_message)

        # Add video queue
        self.videoqueue = queue.Queue()
        self.randomdir = None
        self.file_save_dir = file_save_dir
        self.use_compressor = use_compressor
        self.window_is_fullscreen = False
        self.is_paused = False
        self.uri = None
        self.empty_queue_callback = None
        self.user_agent = None
        self.cookie = None

        self.build_playbin()

    def build_playbin(self):
        # Create GStreamer elements
        self.playbin = Gst.parse_launch('tee name=tee \
            tee. ! queue name=filequeue \
            tee. ! queue2 name=decodequeue use-buffering=true ! decodebin name=dec ! autovideosink \
            dec. ! ' + ('audioconvert ! \
                ladspa-sc4-1882-so-sc4 ratio=5 attack-time=5 release-time=120 threshold-level=-10 ! \
                ladspa-amp-so-amp-stereo gain=9 ! \
                ladspa-fast-lookahead-limiter-1913-so-fastlookaheadlimiter ! ' if self.use_compressor else '') \
                    + 'autoaudiosink')

        # Add playbin to the pipeline
        self.pipeline.add(self.playbin)
        
    def seturi(self, uri):
        if 'http://' in uri or 'https://' in uri:
            source = Gst.ElementFactory.make('souphttpsrc' ,'uri')
            source.set_property('user-agent', self.user_agent) if self.user_agent else None
            source.set_property('cookies', ['cf_clearance=' + self.cookie]) if self.cookie else None

            if self.file_save_dir and not os.path.isfile(self.file_save_dir + '/' + os.path.basename(uri)):
                filesink = Gst.ElementFactory.make('filesink' ,'filesink')
                filesink.set_property('location', self.file_save_dir + '/' + os.path.basename(uri))
                filesink.set_property('async', False)
            else:
                filesink = Gst.ElementFactory.make('fakesink' ,'filesink')
                filesink.set_property('async', False)
        else:
            source = Gst.ElementFactory.make('filesrc' ,'uri')
            filesink = Gst.ElementFactory.make('fakesink' ,'filesink')

        self.playbin.add(source)
        self.playbin.add(filesink)
        source.link(self.pipeline.get_by_name('tee'))
        self.pipeline.get_by_name('filequeue').link(filesink)

        self.pipeline.get_by_name('uri').set_property('location', uri)

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
        
    def stop(self, should_delete=False):
        if should_delete:
            try:
                location = self.pipeline.get_by_name('filesink').get_property('location')
                os.remove(location)
            except:
                pass

        self.pipeline.set_state(Gst.State.NULL)
        self.pipeline.remove(self.playbin)
    
    def quit(self, window = None):
        self.stop(True)
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

    def on_sync_message(self, bus, msg):
        if msg.get_structure().get_name() == 'prepare-window-handle':
            self.logger.debug('prepare-window-handle')
            msg.src.set_window_handle(self.xid)

    def on_buffering(self, bus, msg):
        buf = msg.parse_buffering()
        if buf < 20:
            self.pause()
        elif buf == 100:
            self.play()

    def on_eos(self, bus=None, msg=None):
        self.logger.debug('on_eos()')
        self.stop(not(bus))
        self.build_playbin()
        self.seturi(self.get_queued_or_random())
        self.play()

    def on_error(self, bus, msg):
        self.logger.error('on_error(): {}'.format(msg.parse_error()))
        time.sleep(1)
        self.on_eos()

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
