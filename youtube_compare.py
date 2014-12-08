import sys

from datetime import timedelta
from urllib2 import urlopen
from xml.dom.minidom import parseString
import argparse
import time

def compare_youtube(file_path):
    """
    Attributes:
        file_path (str): Path to the logfile
    """

    log_data = open(file_path, 'r')

    for line in log_data:
        if "Mismatching youtube URLS" in line:
            s = line.split(" - ")[1]
            urls = s.split(" ")
            try:
                comparison = compare_times(urls[1].rstrip("\n"), urls[3].rstrip("\n"))
                if comparison == "Match":
                    print line.rstrip("\n")
                    print comparison
                else:
                    print line.rstrip("\n")
                    print comparison
            except Exception as e:
                print line
                print "Exception", e
            time.sleep(1)

def compare_times(studio, VAL):
    compare_to = None
    for vid in (studio , VAL):
        url = 'https://gdata.youtube.com/feeds/api/videos/{0}?v=2'.format(vid)
        try:
            s = urlopen(url).read()
        except Exception:
            import traceback
            raise Exception(traceback.format_exc())
        d = parseString(s)
        e = d.getElementsByTagName('yt:duration')[0]
        a = e.attributes['seconds']
        v = int(a.value)
        t = timedelta(seconds=v)
        if compare_to is None:
            compare_to = t
        else:
            if compare_to == t:
                return "Match"
            else:
                return str(compare_to)+" - "+str(t)


def main():
    parser = argparse.ArgumentParser()
    parser.usage = '''
    {cmd} -d path/to/data
    '''.format(cmd=sys.argv[0])
    parser.add_argument('-d', '--file', help='Path to data', default='')

    args = parser.parse_args()

    if not args.file:
        parser.print_usage()
        return

    compare_youtube(args.file)

if __name__ == "__main__":
    main()
