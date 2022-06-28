import colorsys
from datetime import datetime
import time

def splitStringIntoChunks(s, n):
    # https://pythonexamples.org/python-split-string-into-specific-length-chunks/#3
    return [s[i:i+n] for i in range(0, len(s), n)]

splitIterableIntoChunks = splitStringIntoChunks

# colour utilities

class Colour:
    # https://pythonexamples.org/python-colorsys-convert-rgb-to-hsv/
    @staticmethod
    def rgbToHex(r,g,b):
        return '#{0:02x}{1:02x}{2:02x}'.format(r,g,b)
    @staticmethod
    def hexToRgb(hex):
        hex = hex[1:]
        return tuple(int(hex[i:i+2], 16) for i in (0, 2, 4))
    
    @staticmethod
    def rgbToHsv(r,g,b):
        h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
        return h, s, v
    @staticmethod
    def hsvToRgb(h,s,v):
        return tuple(round(i * 255) for i in colorsys.hsv_to_rgb(h,s,v))

class Time:
    @staticmethod
    def getUTCTs():
        """
        Get UTC timestamp
        """
        d = datetime.utcnow()
        dtt = d.timetuple()
        return int(time.mktime(dtt))
    @staticmethod
    def UTCToLocal(utc_ts):
        """
        Convert a UTC timestamp
        to a local datetime
        """
        utc_datetime = datetime.fromtimestamp(utc_ts)
        local_ts = time.time()
        local_datetime = datetime.fromtimestamp(local_ts)
        utc_now = datetime.utcfromtimestamp(local_ts)
        offset = local_datetime - utc_now
        return utc_datetime + offset