#!/usr/bin/env python
"""
The Video Migration Script! -- 
pared down to just export a set of xml files from studio

@benjilee - wrote it

@yro - deleted a lot of stuff and made it a lot less good

optimized for use with ham_sandwiches (VEDA intake mobile migrator)
creates a crawlable (date stamped) xml repo for ham_sandwiches
in the same dir as the Script

TODO: add hooks for VEDA API and/or tie to ham_sandwiches 
use: flags are optional

"""
import argparse
import sys
import getpass
import os
import requests
import io
import tarfile
import shutil
import time
import copy
import time

requests.packages.urllib3.disable_warnings()


class ExportError(Exception):
    """
    Studio Export Error
    """
    pass



class Migrator(object):
    """
    The Migration class for using one login for multiple queries

    We want to be able to take a list of course_ids and process them
    in one session, the Migrator object only needs to log in once.
    """
    def __init__(self,
                 course_id=None,
                 studio_url=None):
        self.studio_url = studio_url
        self.sess = requests.Session()
        self.course_id = course_id


    def get_csrf(self, url):
        """
        return csrf token retrieved from the given url
        """
        try:
            response = self.sess.get(url)
            csrf = response.cookies['csrftoken']
            return {'X-CSRFToken': csrf, 'Referer': url}
        except Exception as error:  # pylint: disable=W0703
            print "Error when retrieving csrf token.", error


    def login_to_studio(self, email, password):
        """
        Use given credentials to login to studio.

        Attributes:
            email (str): Login email
            password (str): Login password
        """
        signin_url = '%s/signin' % self.studio_url
        headers = self.get_csrf(signin_url)

        login_url = '%s/login_post' % self.studio_url
        print 'Logging in to %s' % self.studio_url

        response = self.sess.post(login_url, {
            'email': email,
            'password': password,
            'honor_code': 'true'
        }, headers=headers).json()

        if not response['success']:
            raise Exception(str(response))

        print 'Login successful'


    def convert_courses_from_studio(self, courses):
        """
        Takes a single course or courses and converts them from studio

        Conversion involves adding an edx_video_id to the old course data which
        may or may not have an edx_video_id.

        Attributes:
            courses (list): a list of courses. Could be a single course

        """
        for course in courses:
            #get the course data from studio
            course_id = course.strip()
            self.course_id = course_id

            response = self.export_course_data_from_studio(course_id)

            if response.status_code == 500:
                self.log_and_print(
                    "\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
                    "{}: Cannot find course in studio {}\n".
                    format(course_id, response))
            elif response.status_code != 200:
                self.log_and_print("{}: Error {}".format(course_id, response))
            else:
                old_course_data = io.BytesIO(response.content)

                outfile = '{}{}.tar.gz'.format(
                    tag_time(), self.course_id.replace('/', '_')
                )

                print "Saving to {}".format(outfile)

                self.archive_course_data(
                    copy.deepcopy(old_course_data),
                    outfile
                )
                return outfile


    def export_course_data_from_studio(self, course_id):
        """
        Given the URL, gets the data for the given course_id from studio

        Returns:
            response (Response object)
        """
        export_url = '{studio_url}/export/{course}'.format(
            studio_url=self.studio_url,
            course=course_id)
        print 'Exporting from %s' % export_url
        print "This may take a while depending on course size."
        response = self.sess.get(
            export_url,
            params={'_accept': 'application/x-tgz'},
            headers={'Referer': export_url},
            stream=True)
        return response


    def archive_course_data(self, old_course_data, archive_filename):
        """
        Saves the course_data in studio in case import data was bad

        Attributes:
            old_course_data (_io.BytesIO): Stream of course information
            archive_filename (str): Name of the file
        """
        #Opens old_course_data and creates new tarfile to write to
        kwargs = {}
        file_name = old_course_data
        if hasattr(old_course_data, 'read'):
            kwargs['fileobj'] = old_course_data
            file_name = ''
        try:
            old_data = tarfile.TarFile.gzopen(file_name, **kwargs)
        except tarfile.ReadError:
            raise ExportError
        converted_tar = tarfile.TarFile.gzopen(
            (archive_filename), mode='w'
        )
        for item in old_data:
            infile = old_data.extractfile(item.name)
            converted_tar.addfile(item, fileobj=infile)


    def log_and_print(self, message):
        """
        Just prints a message. 
        """
        print message



def tag_time():
    """
    Get's date and time for filename

    Returns:
        (str): Date and time
    """
    return time.strftime("%Y-%m-%d_%I.%M%p_")


def main():
    """
    Exports data from studio

    Takes login credentials for studio where we will pull course data.
    """

    ## just to make the xml files easy to fine
    os.chdir(os.path.dirname(__file__))

    parser = argparse.ArgumentParser()
    parser.usage = '''
    {cmd} -c org/course/run [-e email@domain]

    # To export a course, use -c "course_id".

    # Use --help to see all options.
    # '''.format(cmd=sys.argv[0])
    parser.add_argument('-c', '--course', help='Course', default='')
    parser.add_argument('-s', '--studio', help='Studio URL', default='https://studio.edx.org')
    args = parser.parse_args()

    """
    Protect against unflagged run
    """
    if len(args.course) == 0:
        course_input = raw_input('Course URL: ')
        """
        just in case, this should catch any unflagged stuff
        """
        if 'https' in course_input:
            args.studio = '/'.join((course_input).split('/')[0:3])
            args.course = '/'.join((course_input).split('/')[3:len((course_input).split('/'))+1])
            print args.studio
            print args.course
    """"""

    migration = Migrator(studio_url=args.studio)

    email = raw_input('Studio email address: ')
    password = getpass.getpass('Studio password: ')

    migration.login_to_studio(email, password)

    courses = [args.course]
    tarfile = migration.convert_courses_from_studio(courses)

    return

if __name__ == "__main__":
    sys.exit(main())

