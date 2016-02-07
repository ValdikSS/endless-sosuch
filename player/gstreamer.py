# coding: utf-8 
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkX11', '3.0')
gi.require_version('GstVideo', '1.0')
gi.require_version('Gst', '1.0')
from gi.repository import GObject, GLib, Gst, Gtk, Gdk
from gi.repository import GdkX11, GstVideo
import queue
import os
import os.path
import random
import time
import logging
import glob
import sys
import ctypes

GObject.threads_init()
Gst.init(None)

class NoDirectoryException(Exception):
    pass

class Player(object):
    cursor_none = Gdk.Cursor.new(Gdk.CursorType.BLANK_CURSOR)
    cursor_left = Gdk.Cursor.new(Gdk.CursorType.LEFT_PTR)
    if sys.platform == 'linux':
        ctypes.cdll.LoadLibrary('libX11.so').XInitThreads()

    def __init__(self, file_save_dir=False, use_compressor=False, video_sink='autovideosink',
                 audio_sink='autoaudiosink', add_sink=None, buffering=True):
        self.logger = logging.getLogger('video')
        self.window = Gtk.Window()
        self.window.connect('destroy', self.quit)
        self.window.set_default_size(800, 450)
        self.window.set_title('Endless Sosuch')

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
        self.video_sink = video_sink
        self.audio_sink = audio_sink
        self.add_sink = add_sink
        self.window_is_fullscreen = False
        self.is_paused = True
        self.uri = None
        self.empty_queue_callback = None
        self.user_agent = None
        self.cookie = None
        self.buffering = buffering

        self.build_pipeline()

    def build_pipeline(self):
        # Create GStreamer elements
        self.videobin = Gst.parse_bin_from_description('queue max-size-buffers=0 max-size-bytes=0 max-size-time=1000000000 ! '
            + self.video_sink, True)
        self.audiobin = Gst.parse_bin_from_description('queue max-size-buffers=0 max-size-bytes=0 max-size-time=1000000000 ! \
                audioconvert name=audiosink ! ' + \
                ('ladspa-sc4-1882-so-sc4 ratio=5 attack-time=5 release-time=120 threshold-level=-10 ! \
                ladspa-fast-lookahead-limiter-1913-so-fastlookaheadlimiter input-gain=10 limit=-3 ! ' if self.use_compressor
                else 'queue max-size-buffers=0 max-size-bytes=0 max-size-time=1000000000 ! ') \
                    + self.audio_sink, True)
        self.decodebin = Gst.ElementFactory.make('decodebin', 'dec')
        self.audioconvert_tee = Gst.ElementFactory.make('audioconvert', 'audioconvert_tee')
        self.videoconvert_tee = Gst.ElementFactory.make('videoconvert', 'videoconvert_tee')
        self.audiotee = Gst.ElementFactory.make('tee', 'audiotee')
        self.videotee = Gst.ElementFactory.make('tee', 'videotee')
        if self.add_sink:
            self.add_pipeline = Gst.parse_bin_from_description(self.add_sink, False)
            self.pipeline.add(self.add_pipeline)

        # Add everything to the pipeline
        self.pipeline.add(self.decodebin)
        self.pipeline.add(self.audioconvert_tee)
        self.pipeline.add(self.videoconvert_tee)
        self.pipeline.add(self.audiotee)
        self.pipeline.add(self.videotee)

        self.audioconvert_tee.link(self.audiotee)
        self.videoconvert_tee.link(self.videotee)

        self.decodebin.connect('pad-added', self.on_pad_added)
        self.decodebin.connect('no-more-pads', self.on_no_more_pads)

    def reinit_pipeline(self, uri):
        if self.pipeline.get_by_name('tee'):
            self.pipeline.remove(self.tee_queue)
        if self.pipeline.get_by_name('uri'):
            self.pipeline.remove(self.source)
        if self.pipeline.get_by_name('filesink'):
            self.pipeline.remove(self.filesink)

        if 'http://' in uri or 'https://' in uri:
            self.source = Gst.ElementFactory.make('souphttpsrc' ,'uri')
            self.source.set_property('user-agent', self.user_agent) if self.user_agent else None
            self.source.set_property('cookies', ['cf_clearance=' + self.cookie]) if self.cookie else None

            if self.file_save_dir and not os.path.isfile(self.file_save_dir + '/' + os.path.basename(uri)):
                self.tee_queue = Gst.parse_bin_from_description('tee name=tee \
                                tee. ! queue name=filequeue \
                                tee. ! queue2 name=decodequeue use-buffering=true', False)
                self.filesink = Gst.ElementFactory.make('filesink' ,'filesink')
                self.filesink.set_property('location', self.file_save_dir + '/' + os.path.basename(uri))
                self.filesink.set_property('async', False)
            else:
                self.tee_queue = Gst.parse_bin_from_description('tee name=tee ! queue2 name=decodequeue use-buffering=true', False)
                self.filesink = None
        else:
            self.tee_queue = Gst.parse_bin_from_description('tee name=tee ! queue2 name=decodequeue use-buffering=true', False)
            self.source = Gst.ElementFactory.make('filesrc' ,'uri')
            self.filesink = None

        self.pipeline.add(self.tee_queue)
        self.pipeline.get_by_name('decodequeue').link(self.decodebin)
        self.pipeline.add(self.source)
        if self.filesink:
            self.pipeline.add(self.filesink)
            self.pipeline.get_by_name('filequeue').link(self.filesink)
        self.source.link(self.pipeline.get_by_name('tee'))
        self.source.set_property('location', uri)

        self.has_audio = False
        self.has_video = False

    def seturi(self, uri):
        self.reinit_pipeline(uri)
        self.uri = uri
        self.update_titlebar()

    def run(self):
        self.window.show_all()
        # You need to get the XID after window.show_all().  You shouldn't get it
        # in the on_sync_message() handler because threading issues will cause
        # segfaults there.
        videowindow = self.window.get_window()
        if sys.platform == 'win32':
            ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
            ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object]
            drawingarea_gpointer = ctypes.pythonapi.PyCapsule_GetPointer(videowindow.__gpointer__, None)
            gdkdll = ctypes.CDLL ("libgdk-3-0.dll")
            self.xid = gdkdll.gdk_win32_window_get_handle(drawingarea_gpointer)
        else:
            self.xid = videowindow.get_xid()
        self.seturi(self.get_queued_or_random())
        self.play()
        Gtk.main()

    def play(self):
        if not self.is_paused:
            return

        self.pipeline.set_state(Gst.State.PLAYING)
        self.logger.info('Playing {}'.format(self.uri))
        self.is_paused = False
        GObject.timeout_add_seconds(1, self.update_titlebar)

    def pause(self):
        if self.is_paused:
            return

        self.pipeline.set_state(Gst.State.PAUSED)
        self.is_paused = True

    def stop(self, should_delete=False):
        location = None
        if should_delete:
            try:
                location = self.filesink.get_property('location')
            except:
                pass

        self.pipeline.set_state(Gst.State.NULL)
        if location:
            os.remove(location)
        self.is_paused = True

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
            self.window.get_window().set_cursor(self.cursor_none)
            self.window_is_fullscreen = True
        else:
            self.window.unfullscreen()
            self.window.get_window().set_cursor(self.cursor_left)
            self.window_is_fullscreen = False

    def toggle_play(self):
        if not self.is_paused:
            self.pause()
        else:
            self.play()

    def update_titlebar(self):
        time_str = None
        try:
            dur = self.pipeline.query_duration(Gst.Format.TIME)[1]
            pos = self.pipeline.query_position(Gst.Format.TIME)[1]

            time_str = '%d:%.2d / %d:%.2d' % (
                int(float(pos) / Gst.SECOND) // 60,
                int(float(pos) / Gst.SECOND) % 60,
                int(float(dur) / Gst.SECOND) // 60,
                int(float(dur) / Gst.SECOND) % 60
            )
        except:
            pass

        self.window.set_title('Endless Sosuch | ' +
                              os.path.basename(self.uri) + 
                              (' | ' + time_str if time_str else ''))
        
        return not self.is_paused

    def link_video(self, element=None, pad=None):
        if not self.pipeline.get_by_name(self.videobin.get_name()):
            self.pipeline.add(self.videobin)
        if element and pad:
            # If we have an element with a pad, we link exact pad to the
            # video output. If not, link any pad from the decoder.
            element.link_pads(pad.get_name(), self.videoconvert_tee, None)
        else:
            self.decodebin.link(self.videoconvert_tee)
        self.videotee.link(self.videobin)
        if self.add_sink:
            self.videotee.link(self.pipeline.get_by_name('vq'))
        self.videobin.sync_state_with_parent()

    def on_sync_message(self, bus, msg):
        if msg.get_structure().get_name() == 'prepare-window-handle':
            self.logger.debug('prepare-window-handle')
            msg.src.set_window_handle(self.xid)

    def on_buffering(self, bus, msg):
        buf = msg.parse_buffering()
        if self.buffering:
            if buf < 20:
                self.pause()
            elif buf >= 80:
                self.play()

    def on_pad_added(self, element, pad):
        string = pad.query_caps(None).to_string()
        self.logger.debug('Pad added: {}'.format(string))
        event = pad.get_sticky_event(Gst.EventType.STREAM_START, 0)
        stream_flags = event.parse_stream_flags().value_names
        if string.startswith('audio/'):
            self.has_audio = True
            if not self.pipeline.get_by_name(self.audiobin.get_name()):
                self.pipeline.add(self.audiobin)
            self.decodebin.link(self.audioconvert_tee)
            self.audiotee.link(self.audiobin)
            if self.add_sink:
                self.audiotee.link(self.pipeline.get_by_name('aq'))
            self.audiobin.sync_state_with_parent()
        if string.startswith('video/'):
            if self.has_video or ('GST_STREAM_FLAG_SELECT' not in stream_flags and not self.has_video):
                # Not linking a video stream without default flag (probably a preview) or if it's not
                # a first video stream
                self.logger.debug('Not linking stream with flags {}'.format(stream_flags))
                return False
            self.has_video = True
            self.link_video(element, pad)

    def on_no_more_pads(self, element):
        self.logger.debug('No more pads')
        if not self.has_audio and self.add_sink:
            # Can't handle it since additional pipeline always assumes audio
            GLib.idle_add(self.on_eos, 0)
        elif not self.has_audio:
            self.pipeline.remove(self.audiobin)
        if not self.has_video:
            # A workaround for a bit wrongly muxed video files with no default flag on a video stream.
            # If we haven't linked a video in on_pad_added and there are no other video streams, we should
            # re-link it to the output.
            self.logger.info('Wrongly muxed video file detected. Re-linking video output.')
            self.has_video = True
            self.link_video()

    def on_eos(self, bus=None, msg=None):
        self.logger.debug('on_eos()')
        self.stop(not(bus))
        uri = self.get_queued_or_random()
        self.seturi(uri)
        self.play()

    def on_error(self, bus, msg):
        self.logger.error('on_error(): {}'.format(msg.parse_error()))
        time.sleep(1)
        self.on_eos()

    def on_key_release(self, window, ev, data=None):
        keyval = Gdk.keyval_to_lower(ev.keyval)
        if keyval == Gdk.KEY_s:
            self.on_eos()
        if keyval == Gdk.KEY_d:
            for i in range(9):
                try:
                    self.videoqueue.get_nowait()
                except queue.Empty:
                    break
            self.on_eos()
            # get random video from folder
        elif keyval in (Gdk.KEY_Escape, Gdk.KEY_q):
            self.quit()
        elif keyval == Gdk.KEY_f:
            self.toggle_fullscreen()
        elif keyval == Gdk.KEY_space:
            self.toggle_play()
