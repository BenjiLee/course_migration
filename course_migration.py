"""
The Video Migration Script!

Takes the exported course data from studio (old data), converts it using VAL,
and then optionally imports the new tarfile (converted data) back into studio.
The old data will be processed by either adding an edx_video_id,
compared against the Video Abstraction Layer (VAL) edx_video_id for differences,
or verifiying that the edx_video_id in the old data and VAL match. The
export (old data) is the same as a studio course export tarfile where the
information we are interested in is in the videos folder of the tarfile. Inside
of the videos folder, the videos are in a xml format, where we parse out the
target information such as youtube_id, source urls, (if available) exiting
edx_video_ids.

Possible conditions when processing videos:

Matching youtube URLs:
    Old video has an edx_video_id and matches in VAL.
        Great!

    Old video has an edx_video_id that does not match in VAL.
        This is possible if the edx_video_id was manually input. Update old
        edx_video_id with VAL edx_video_id.

            def add_edx_video_id_to_video(self, video_xml):
                ...
                elif studio_edx_video_id != edx_video_id:

    Old video does not have an edx_video_id.
        The urls for the video will be compared against VAL and the
        edx_video_id will be added accordingly.

            def add_edx_video_id_to_video(self, video_xml):
                ...
                if studio_edx_video_id == '' or studio_edx_video_id is None:

youtube URL mismatch:
    Old video has an edx_video_id and matches in VAL, but urls do not match.
        There could be broken/outdated links, or the wrong edx_video_id
        altogether. Defaults to studio urls.

            def get_youtube_mismatch(self, edx_video_id, youtube_id):

    #TODO Old video's edx_video_id is found, but there are missing urls.
        Sometimes there will be missing encodings for
        a video, i.e., there exists a desktop version but no mobile version.

Not found:
    Old video has no edx_video_id and no urls can be found in VAL.
        A report should be made to fix this issue. This means that there are
        videos (which also could be broken/outdated) that VAL isn't aware of.

            def process_course_data(self, old_course_data, new_filename):
                ...
                if not_found:

Note:

    Print statements are useful for whoever is running the script. Rather than
showing nothing for the duration of the script, messages are printed out to show
 the status of the script, and that the script is running. Messages such as
 logged in, or course processed appear in the print statements.
    Logged statements are for the log that gets sent to whomever needs to see
the details. Messages such as "56 videos processed" or "Missing video, this is
the url, etc." are shown in the log.
"""
#!/usr/bin/env python
import argparse
import sys
import getpass
import os
import requests
import io
import tarfile
import logging
from xml.etree.cElementTree import fromstring, tostring
import shutil
import time
import copy
import time


class EdxVideoIdError(Exception):
    """
    Cannot find an edx_video_id
    """
    pass


class PermissionsError(Exception):
    """
    Login was successful but permission not granted
    """
    pass


class ExportError(Exception):
    """
    Failure when exporting data
    """
    pass


class NotFoundError(Exception):
    """
    Item cannot be found
    """
    pass


class UnknownError(Exception):
    """
    Last case error when specific case is not handled
    """
    pass


class Migrator(object):
    """
    The Migration class for using one login for multiple queries

    We want to be able to take a list of course_ids and process them
    in one session, the Migrator object only needs to log in once.
    """
    def __init__(self,
                 save_imports,
                 save_exports,
                 course_id=None,
                 studio_url=None):
        self.studio_url = studio_url
        self.val_url = '{}/api/val/v0'.format(self.studio_url)
        self.sess = requests.Session()
        self.log = logging.getLogger('migrator')
        self.log.info("\n"+((70*"=")+"\n")*3)
        self.course_id = course_id
        self.course_videos = []
        self.videos_processed = 0
        self.save_imports = save_imports
        self.save_exports = save_exports

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

    def import_tar_to_studio(self, file_path=None, split_course_id=None):
        """
        Uploads given tar (file_path) to studio.
        """
        if split_course_id:
            course_id = split_course_id
        else:
            course_id = self.get_course_id_from_tar(file_path)
        url = '{}/import/{}'.format(self.studio_url, course_id)
        self.log.info(
            'Importing {} to {} from {}'.format(course_id, url, file_path)
        )
        print 'Importing {} to {} from {}'.format(course_id, url, file_path)
        print 'Upload may take a while depending on size of the course'
        headers = self.get_csrf(url)
        headers['Accept'] = 'application/json'
        with open(file_path, 'rb') as upload:
            filename = os.path.basename(file_path)
            start = 0
            upload.seek(0, 2)
            end = upload.tell()
            upload.seek(0, 0)

            while 1:
                start = upload.tell()
                data = upload.read(2 * 10**7)
                if not data:
                    break
                stop = upload.tell() - 1
                files = [
                    ('course-data', (filename, data, 'application/x-gzip'))
                ]
                headers['Content-Range'] = crange = '%d-%d/%d'\
                                                    % (start, stop, end)
                self.log.debug(crange)
                response = self.sess.post(url, files=files, headers=headers)
                self.log.debug(response.status_code)
            # now check import status
            self.log.info('Checking status')
            import_status_url = '{}/import_status/{}/{}'.format(
                self.studio_url, course_id, filename)
            status = 0
            while status != 4:
                status = self.sess.get(import_status_url).json()['ImportStatus']
                self.log.debug(status)
                time.sleep(3)
            self.log.info('Uploaded!')
            print 'Uploaded!'

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

                if self.save_exports:
                    #save the exported course
                    print "Saving to {}".format(outfile)

                    try:
                        self.archive_course_data(
                            copy.deepcopy(old_course_data),
                            outfile
                        )
                    except ExportError:
                        self.log_and_print(
                            "\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
                            "{}: Could not read export data\n"
                            .format(self.course_id)
                        )

                #Process the course
                print "Processing videos. This may take a while depending on " \
                      "the number of videos in the course."
                try:
                    self.process_course_data(old_course_data, outfile)
                    print "{}: Course processed".format(self.course_id)
                except ExportError:
                    self.log_and_print(
                        "\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
                        "{}: Could not read export data\n"
                        .format(self.course_id)
                    )

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

    def process_course_data(self, old_course_data, new_filename):
        """
        Process the old_course_data to include the edx_video_id, then saves it
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

        if self.save_imports:
            converted_tar = tarfile.TarFile.gzopen(
                ("imported_course_tarfile/"+new_filename), mode='w'
            )

        self.videos_processed = 0

        #Sets course_id and then populates course_videos from val.
        course_xml = old_data.extractfile(os.path.join(
            old_data.getnames()[0],
            'course.xml')).read()
        course_xml = fromstring(course_xml)
        if not self.course_id:
            self.course_id = '%s/%s/%s' % (
                course_xml.get('org'),
                course_xml.get('course'),
                course_xml.get('url_name')
            )

        try:
            self.course_videos = self.get_course_videos_from_val()
        except PermissionsError:
            return
        except UnknownError:
            return

        #Process videos, and save to tarfile
        not_found = []

        for item in old_data:
            infile = old_data.extractfile(item.name)
            if '/video/' in item.name:
                video_xml = fromstring(infile.read())
                try:
                    new_xml = self.sets_edx_video_id_to_video(video_xml)
                except EdxVideoIdError:
                    new_xml = None
                    not_found.append(video_xml)

                if new_xml:
                    infile = io.BytesIO(new_xml)
                    item.size = len(new_xml)
                else:
                    infile.seek(0)
            if self.save_imports:
                converted_tar.addfile(item, fileobj=infile)

        #Logs videos that were not found
        if not_found:
            self.log.info(
                "{}: {} Missing videos:".format(self.course_id, len(not_found))
            )
            for video_xml in not_found:
                youtube_id = video_xml.get('youtube_id_1_0')
                display_name = video_xml.get('display_name', u'').encode('utf8')
                url_name = video_xml.get("url_name")
                self.log.info(
                    '\t"url_name:"{}"\tyoutube_id:"{}"\tdisplay_name:"{}"'
                    .format(url_name, youtube_id, display_name)
                )
        self.log.info("{}:{} Videos have been processed".
                      format(self.course_id, self.videos_processed))

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
            ("exported_course_tarfile/"+archive_filename), mode='w'
        )
        for item in old_data:
            infile = old_data.extractfile(item.name)
            converted_tar.addfile(item, fileobj=infile)

    def get_course_videos_from_val(self):
        """
        Calls VAL api to get all available videos in given course_id

        Returns:
            videos (str): videos in json

        Raises:
            PermissionsError: Raised when user does not have permissions for VAL
            UnknownError: Raised when an unknown error occurs
        """
        url = self.val_url + '/videos/'
        response = self.sess.get(url, params={'course': self.course_id})
        if response.status_code == 200:
            videos = response.json()["results"]
            while response.json()["next"]:
                response = self.sess.get(response.json()["next"])
                videos += response.json()["results"]
            return videos
        elif response.status_code == 403:
            self.log.error("Permissions error for VAL access")
            print "Permissions error for VAL access"
            raise PermissionsError
        else:
            self.log.error("Could not obtain video_list from VAL")
            print "UnknownError in VAL:", response.status_code
            raise UnknownError

    def sets_edx_video_id_to_video(self, video_xml):
        """
        Takes a video's xml and compares/sets edx_video_id
        """
        source = video_xml.get('source') or ''
        studio_edx_video_id = video_xml.get('edx_video_id')
        youtube_id = video_xml.get('youtube_id_1_0')

        edx_video_id_found = False

        #Looking for edx_video_id via youtube_id/client_id
        # if self.course_id.startswith(('MITx', 'DelftX', 'LouvainX/Louv1.1x')) \
        if edx_video_id_found is False:
            # for mit, the filename will be the client id
            client_id = studio_edx_video_id
            edx_video_id_found, edx_video_id =\
                self.find_edx_video_id_from_ids(
                    client_id=client_id,
                    youtube_id=youtube_id
                )
        #Gets edx_video_id by parsing a url
        if edx_video_id_found is False:
            for line in video_xml.findall('./source'):
                source_url = line.get('src')
                if source_url:
                    edx_video_id = self.parse_edx_video_id_from_url(source_url)
                    source = source_url
                    edx_video_id_found = True
                    break
            else:
                if source:
                    edx_video_id = self.parse_edx_video_id_from_url(source)
                    edx_video_id_found = True

        #Assuming edx_video_id is 20 or 36 characters, if it is not, discard it.
        if edx_video_id_found:
            if (len(edx_video_id) != 20 and len(edx_video_id) != 36) or "." in edx_video_id:
                edx_video_id_found = False



        #Looking for edx_video_is via source, else report missing
        if edx_video_id_found is False:
            source = source.split('/')[-1].rsplit('.', 1)[0]
            edx_video_id_found, edx_video_id =\
                self.find_edx_video_id_from_ids(client_id=source)
            if edx_video_id_found is False:
                edx_video_id_found, edx_video_id =\
                    self.find_edx_video_id_from_ids(
                        client_id=source.replace('_', '-')
                    )
                #If all fails, use the studio edx_video_id
                if studio_edx_video_id:
                    edx_video_id = studio_edx_video_id
                    edx_video_id_found = True
                if edx_video_id_found is False:
                    raise EdxVideoIdError(source)

        #Set edx_video_id and log issues
        if edx_video_id_found:
            if studio_edx_video_id == '' or studio_edx_video_id is None:
                self.log.debug(
                    "{}: Empty edx_video_id in studio for {}".
                    format(self.course_id, edx_video_id)
                )
            elif studio_edx_video_id != edx_video_id:
                self.log.error(
                    "{}: Mismatching edx_video_ids - Studio: {} VAL: {}".
                    format(self.course_id, studio_edx_video_id, edx_video_id))
            if youtube_id:
                self.log_youtube_mismatches(edx_video_id, youtube_id)
            try:
                self.log_missing_video_profiles(edx_video_id)
            except PermissionsError:
                self.log_and_print(
                    "{}:Permissions error for VAL access for {}".
                    format(self.course_id, edx_video_id)
                )
            except NotFoundError:
                self.log_and_print(
                    "{}:Cannot find {} in VAL".
                    format(self.course_id, edx_video_id))
            except UnknownError as status_code:
                self.log_and_print(
                    "{}:UnknownError in VAL {} for {}".
                    format(self.course_id, status_code, edx_video_id)
                )


            video_xml.set('edx_video_id', edx_video_id)
            video_xml = tostring(video_xml)
            self.videos_processed += 1
            return video_xml

    def log_missing_video_profiles(self, edx_video_id):
        """
        Calls the VAL api to check to see if all profiles for the video are set

        Calls the VAL api for a video using the edx_video_id, parses the json
        for all the different profiles, and then logs any videos that are
        missing.

        Attributes:
            edx_video_id (str): The id of the video
        """
        url = self.val_url + '/videos/' + edx_video_id
        response = self.sess.get(url)
        if response.status_code == 200:
            videos = response.json()
            profiles = set([video["profile"] for video in videos.get("encoded_videos", [])])
            # no longer need webm
            if "desktop_webm" in profiles:
                profiles.remove("desktop_webm")
            explicit_formats_we_check_for = [
                "mobile_high",
                "mobile_low",
                "youtube",
                "desktop_mp4",
                "audio_mp3",
            ]
            missing_profiles = ""
            for profile in profiles:
                if profile not in explicit_formats_we_check_for:
                    missing_profiles += (profile+",")
            if missing_profiles:
                self.log_and_print(
                    "{}: Video with edx_video_id {} is missing these profiles: {}".
                    format(self.course_id, edx_video_id, missing_profiles)
                )
        elif response.status_code == 403:
            raise PermissionsError
        elif response.status_code == 404:
            raise NotFoundError
        else:
            raise UnknownError(response.status_code)

    def log_youtube_mismatches(self, edx_video_id, youtube_id):
        """
        Given a youtube_id and edx_video_id, logs mismatched in url

        Currently mismatches will default to saving the studio urls to the
        tarfile.
        """
        for vid in self.course_videos:
            if vid['edx_video_id'] == edx_video_id:
                for enc in vid['encoded_videos']:
                    if enc['profile'] == 'youtube':
                        if enc['url'].strip() != youtube_id:
                            val_url = enc['url']
                            self.log.error(
                                "{}: Mismatching youtube URLS for edx_video_id:"
                                " {} - Studio: {} VAL: {}".
                                format(
                                    self.course_id,
                                    edx_video_id,
                                    youtube_id,
                                    val_url
                                )
                            )

    def parse_edx_video_id_from_url(self, path):
        """
        Parses the edx_video_id from a source url

        Attributes:
            path (str): the url of the video source
        Returns:
            (str): the edx_video_id
        """
        split = path.split('/')[-1]
        return split.split('_')[0]

    def find_edx_video_id_from_ids(self, youtube_id=None, client_id=None):
        """
        Gets edx_video_id by searching course_videos with youtube or client ids

        Returns:
            Boolean, edx_video_id (bool, str): If successful returns True and
             the edx_video_id. Else, returns false, and an empty string.
        """
        for video in self.course_videos:
            if youtube_id:
                for enc in video['encoded_videos']:
                    if enc['profile'] == 'youtube' and enc['url'].strip() == youtube_id:
                        return True, video['edx_video_id']
            if video['client_video_id'] == client_id and client_id:
                return True, video['edx_video_id']
        return False, ''

    def get_course_id_from_tar(self, file_path):
        """
        Given a file_path to a tarfile, returns the course_id

        Attributes:
            files_path (str): String representation of the path to the tar
                or an already opened tar.

        Returns:
            course_id (str): course_id parsed from course.xml in tar
        """
        kwargs = {}
        file_name = file_path
        if hasattr(file_path, 'read'):
            kwargs['fileobj'] = file_path
            file_name = ''
        old_data = tarfile.TarFile.gzopen(file_name, **kwargs)
        course_xml = old_data.extractfile(os.path.join(
            old_data.getnames()[0],
            'course.xml')).read()
        course_xml = fromstring(course_xml)
        course_id = '%s/%s/%s' % (
            course_xml.get('org'),
            course_xml.get('course'),
            course_xml.get('url_name')
        )
        return course_id

    def log_and_print(self, message):
        """
        Logs and prints a message. Reduces spaces from repeated strings

        Attributes:
            message (str): The message
        """
        #TODO handle other logtypes. Not important
        self.log.error(message)
        print message

def make_or_clear_folder(folder):
    if not os.path.exists(folder):
        os.makedirs(folder)
    elif raw_input(('Empty %s folder? When importing, '
                       'all files in this folders will be marked for upload'
                       ' [y/n] ').lower().strip() % folder) == 'y':
        shutil.rmtree(folder)
        os.makedirs(folder)


def make_folder(folder):
    if not os.path.exists(folder):
        os.makedirs(folder)


def tag_time():
    """
    Get's date and time for filename

    Returns:
        (str): Date and time
    """
    return time.strftime("%Y-%m-%d_%I.%M%p_")

def main():
    """
    Exports data from studio, processes it, then optionally imports to studio

    Takes login credentials for studio where we will pull course data. This data
    will be processed through VAL. This data will be packed into a tar that can
    be optionally imported to studio.
    """

    parser = argparse.ArgumentParser()
    parser.usage = '''
    {cmd} -c org/course/run [-e email@domain]
    or
    {cmd} -f path/to/exported.tar.gz
    or
    {cmd} --import

    To export a course, use -c "course_id".
    To export a list of courses, use -l path/to/courses.txt
    To upload courses in the convert_tarfiles directory, use -u
    To skip saving imports use -ni
    To skip saving exports use -ne

    To import a single split course e.g. course+v1:edx/cs123/course use -sc
    A split course will use the given course_id to both export and import the
    course. Only a single course can be done at a time.

    Use --help to see all options.
    '''.format(cmd=sys.argv[0])
    parser.add_argument('-c', '--course', help='Course', default='')
    parser.add_argument('-l', '--courses', type=argparse.FileType('rb'), default=None)
    parser.add_argument('-f', '--export', help='Path to export directory', default='')
    parser.add_argument('-e', '--email', help='Studio email address', default='')
    parser.add_argument('-s', '--studio', help='Studio URL', default='https://studio.edx.org')
    parser.add_argument('-v', '--verbose', help='verbose', default=False, action='store_true')
    parser.add_argument('-u', '--upload', help='Upload to studio', default=False, action='store_true')
    parser.add_argument('-ne', '--noexports', help='Disable save export files', default=True, action='store_false')
    parser.add_argument('-ni', '--noimports', help='Disable save import files', default=True, action='store_false')
    parser.add_argument('-sc', '--splitcourse', help='For split courses', default='')



    args = parser.parse_args()

    if not (args.export or args.course or args.courses or args.upload or args.splitcourse):
        parser.print_usage()
        return -1
    #setup folders
    to_import_folder = "imported_course_tarfile"
    archive_folder = "exported_course_tarfile"
    local_folder = "local_tarfiles"
    log_folder = "logs"

    make_folder(log_folder)
    make_folder(local_folder)
    make_folder(archive_folder)
    make_or_clear_folder(to_import_folder)

    log_filename = log_folder+"/"+tag_time()+"migrator_log.txt"
    logging.basicConfig(
        filename=log_filename,
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S')

    migration = Migrator(studio_url=args.studio,
                         save_exports=args.noexports,
                         save_imports=args.noimports)

    email = args.email or raw_input('Studio email address: ')
    password = getpass.getpass('Studio password: ')
    migration.login_to_studio(email, password)

    #If not uploading right away, convert local files or studio exports
    if not args.upload:
        if args.export:
            for file_path in os.listdir(args.export):
                export_data = args.export + file_path
                fname = os.path.split(export_data)[1]
                new_filename = os.path.join(tag_time() + fname)
                print '\nSaving to %s' % new_filename
                migration.process_course_data(export_data, new_filename)
        elif args.courses or args.course:
            courses = args.courses or [args.course]
            migration.convert_courses_from_studio(courses)
        elif args.splitcourse:
            migration.convert_courses_from_studio([args.splitcourse])

        possible_issues = open(log_filename, 'r')

        print "Logged issues:"
        for line in possible_issues:
            print line

        print "Check the issues in {} before importing".format(log_filename)

    #upload prompt
    if args.noimports:
        upload_query = 'Upload courses in converted_tarfiles directory to %s [y/n] ' % args.studio
        if raw_input(upload_query) == 'y':
            upload_message = "*"*20+"Starting uploads"+"*"*20
            logging.info(upload_message)
            print upload_message
            if args.splitcourse:
                for filename in os.listdir(to_import_folder):
                    file_path = "%s/%s" % (to_import_folder, filename)
                    migration.import_tar_to_studio(file_path=file_path, split_course_id=args.splitcourse)
            else:
                for filename in os.listdir(to_import_folder):
                    file_path = "%s/%s" % (to_import_folder, filename)
                    migration.import_tar_to_studio(file_path=file_path)

    return

if __name__ == "__main__":
    sys.exit(main())

