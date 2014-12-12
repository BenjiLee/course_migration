import argparse
import getpass
import requests
import logging


class MobileApi(object):

    def __init__(self):
        self.url = "https://courses.edx.org"
        self.mobile_api_url = '{}/api/mobile/v0.5/video_outlines/courses'.\
            format(self.url)
        self.sess = requests.Session()
        self.log = logging.getLogger('mobile')
        self.log.info("\n"+((70*"=")+"\n")*3)
        self.videos = []

    def get_csrf(self, url):
        """
        """
        try:
            response = self.sess.get(url)
            csrf = response.cookies['csrftoken']
            return {'X-CSRFToken': csrf, 'Referer': url}
        except Exception as error:  # pylint: disable=W0703
            print "Error when retrieving csrf token.", error

    def login(self, email, password):
        """
        """
        signin_url = '{}/login'.format(self.url)
        headers = self.get_csrf(signin_url)

        login_url = '%s/login_ajax' % self.url
        print 'Logging in to %s' % self.url

        response = self.sess.post(login_url, {
            'email': email,
            'password': password,
            'honor_code': 'true'
        }, headers=headers).json()
        if not response['success']:
            raise Exception(str(response))
        print 'Login successful'

    def check_course(self, courses):
        for course in courses:
            thing = self.get_course_data(course.rstrip("\n"))
            if thing[0] == True:
                self.process_video_data(thing[1])
            else:
                print course.rstrip("\n") + ": "+str(thing[1])

    @staticmethod
    def process_video_data(json_data):
        for video in json_data:
            if video['summary']['size'] == 0:
                print "\nMissing size: {}".format(video)
            if video['summary']['transcripts'] == "{}":
                print "\nMissing transcript: {}".format(video)

    def get_course_data(self, course):
        course_url = self.mobile_api_url + "/" + course
        print "\n"+"!"*40+course+"!"*40+"\n"
        response = self.sess.get(course_url)
        if response.status_code == 200:
            result = response.json()
            return True, result
        else:
            return False, response.status_code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--course', help='Course', default='')
    parser.add_argument('-l', '--courses', type=argparse.FileType('rb'), default=None)
    parser.add_argument('-e', '--email', help='Studio email address', default='')

    args = parser.parse_args()

    if not (args.course or args.courses):
        print "need courses"
        return
    mobile = MobileApi()
    email = args.email or raw_input('Email address: ')
    password = getpass.getpass('Password: ')
    mobile.login(email, password)

    courses = args.courses or [args.course]
    mobile.check_course(courses)

if __name__ == "__main__":
    main()



