# coding: utf-8  

# Path to directory with WebM files
RANDOM_PATH = 'webm'

# Should we save all played to the end files to that directory?
SAVE_FILES = True

# Keywords in an OP's post to search for
INCLUDE_KEYWORDS = r'(?i)(([WEBM]|[ЦУИЬ])|([ВШ][ЕБМ]))'
#INCLUDE_KEYWORDS = None

# Keywords to exclude
#EXCLUDE_KEYWORDS = r'(?i)((анимублядский)|(порн))'
EXCLUDE_KEYWORDS = None

# Cloudflare "cf_clearance" cookie value
# Currently supported only by gstreamer backend
CF_COOKIE = '861a0566de1421f863f81936700d70e6f9d15356-1444513397-604800'

# Your User-Agent for that cookie
CF_USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64; rv:41.0) Gecko/20100101 Firefox/41.0'

# Backend to use
# 'gstreamer' or 'vlc'
BACKEND = 'gstreamer'

# Use audio compressor and limiter to normalize volume level between different video files
# Requires LADSPA with swh-plugins for gstreamer
# Uses compressor and volnorm in VLC (works worse than in gstreamer)
AUDIO_COMPRESSOR = False

# Select GStreamer sinks that work for you
# See: http://gstreamer.freedesktop.org/data/doc/gstreamer/head/gst-plugins-good-plugins/html/
GSTREAMER_VIDEO_SINK = 'autovideosink'
GSTREAMER_AUDIO_SINK = 'autoaudiosink'

# Use gstreamer buffering
# Generally works fine but sometimes could stale a stream
GSTREAMER_BUFFERING = True

# Additional GStreamer pipeline. Can be used to stream video to the remote server
# In order to use it, you should create two queues with names "vq" and "aq"
#GSTREAMER_ADDITIONAL_PIPELINE = 'queue name=vq ! fakesink queue name=aq ! fakesink'
GSTREAMER_ADDITIONAL_PIPELINE = None

# Select VLC sinks
VLC_AUDIO_SINK = None
VLC_VIDEO_SINK = None
