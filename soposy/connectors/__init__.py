import abc
import http.server
import logging
import subprocess
import threading
import time
import urllib.parse

import iso8601

import requests
from requests_oauthlib import OAuth1, OAuth1Session, OAuth2Session

import tweepy

from soposy.data import Entry


class Connector(abc.ABC):

    def __init__(self):
        self.name = None

    @abc.abstractmethod
    def configure(self, name, section):
        """Configures this connector with the given name and options.

        The default implementation assigns the name to a property.
        """
        self.name = name

    @classmethod
    @abc.abstractclassmethod
    def register_parser(cls, subparsers):
        """Registers command line parsers for utility commands.

        Callable actions must assign a function to the 'action' field, which is
        callable with three arguments. The first is a Namespace object
        representing the command line arguments. The second is a ConfigParser
        instance representing the configuration of the system. The third
        argument is an sqlite3 database connection for the temporary storage.
        """
        pass

    @abc.abstractmethod
    def entries(self, after):
        pass

    @abc.abstractmethod
    def push(self, entry):
        """Pushes a new entry to the target."""
        pass


class FivehundredPx(Connector):

    _CONSUMER_KEY = 'jyFhcpFS2la9kbu5cJMH2bg5wvI8woHj3BnSnggU'
    _CONSUMER_SECRET = 'mRqTMiOGh1rCRPUl0FdO3GSDTr9xb8S1amfLTQmS'

    _URL_API = "https://api.500px.com/v1/"
    _URL_REQUEST_TOKEN = _URL_API + "oauth/request_token"
    _URL_AUTHORIZE = _URL_API + "oauth/authorize"
    _URL_ACCESS_TOKEN = _URL_API + "oauth/access_token"
    _URL_PHOTOS = _URL_API + "photos"

    logger = logging.getLogger('soposy.connectors.500px')

    def configure(self, name, section):
        Connector.configure(self, name, section)
        self.oauth_token = section['token']
        self.oauth_token_secret = section['token_secret']
        self.username = section['username']

    @classmethod
    def register_parser(cls, subparsers):
        cls.logger.debug('registering argument parser')
        parser = subparsers.add_parser('500px')
        subparsers = parser.add_subparsers(title='Subcommands')

        # register
        parser_register = subparsers.add_parser(
            'register',
            description='Register at the 500px service using OAuth1')
        parser_register.set_defaults(action=cls.action_register)

    @classmethod
    def action_register(cls, args, config, conn):
        cls.logger.debug('Starting registration process')

        got_data_event = threading.Event()
        verifier = [None]

        class WaitingHandler(http.server.BaseHTTPRequestHandler):

            def do_GET(self):
                self.send_response(200)

                self.send_header('Content-type', 'text/html')
                self.end_headers()

                request = urllib.parse.parse_qs(self.path)
                if 'oauth_verifier' not in request:
                    self.wfile.write(
                        bytes('Authorization error. Close this window.',
                              "utf8"))
                else:
                    self.wfile.write(
                        bytes('Authorized. Close this window.', "utf8"))
                    verifier[0] = request['oauth_verifier'][0]

                got_data_event.set()

        server = http.server.HTTPServer(('localhost', 0), WaitingHandler)
        thread = threading.Thread(target=server.serve_forever,
                                  daemon=True)
        try:
            cls.logger.debug('Started reply server on port %s',
                             server.server_port)
            thread.start()

            # request a token
            cls.logger.debug('Requesting a token')
            reply = requests.post(
                cls._URL_REQUEST_TOKEN,
                data={'oauth_callback':
                      'http://localhost:{}'.format(server.server_port)},
                auth=OAuth1(cls._CONSUMER_KEY,
                            client_secret=cls._CONSUMER_SECRET))
            cls.logger.debug('API reply: %s: %s', reply, reply.text)
            reply.raise_for_status()
            parsed = urllib.parse.parse_qs(reply.text)
            token = parsed['oauth_token'][0]
            token_secret = parsed['oauth_token_secret'][0]
            token_confirmed = parsed['oauth_callback_confirmed'][0]

            if not bool(token_confirmed):
                raise RuntimeError('OAuth request was not confirmed')

            # request user authorization
            cls.logger.debug('Requesting user authorization')
            url = '{}?oauth_token={}'.format(cls._URL_AUTHORIZE, token)
            subprocess.check_call(['xdg-open', url])

            if not got_data_event.wait(120):
                raise RuntimeError("Timeout while waiting for oauth_verifier")
            if not verifier[0]:
                raise RuntimeError("Did not receive the oauth verifier")

            cls.logger.debug('Received verifier %s', verifier[0])

        finally:
            server.shutdown()
            thread.join(timeout=15)

        # get the access token
        reply = requests.post(url=cls._URL_ACCESS_TOKEN,
                              auth=OAuth1(cls._CONSUMER_KEY,
                                          client_secret=cls._CONSUMER_SECRET,
                                          resource_owner_key=token,
                                          resource_owner_secret=token_secret,
                                          verifier=verifier[0]))
        reply.raise_for_status()
        parsed = urllib.parse.parse_qs(reply.text)
        token = parsed['oauth_token'][0]
        token_secret = parsed['oauth_token_secret'][0]

        print('''Use the following for your config:

  token = {token}
  token_secret = {token_secret}'''.format(token=token,
                                          token_secret=token_secret))

    def _session(self):
        return OAuth1Session(self._CONSUMER_KEY,
                             client_secret=self._CONSUMER_SECRET,
                             resource_owner_key=self.oauth_token,
                             resource_owner_secret=self.oauth_token_secret)

    def entries(self, after):
        reply = self._session().get(self._URL_PHOTOS,
                                    params={'feature': 'user',
                                            'username': self.username,
                                            'sort': 'created_at',
                                            'sort_direction': 'desc',
                                            'rpp': 100,
                                            'tags': 1,
                                            'image_size': 1080})
        reply.raise_for_status()

        results = []
        for entry in reply.json()['photos']:
            uniqueId = entry['id']
            title = entry['name']
            link = 'https://500px.com' + entry['url']
            created_at = iso8601.parse_date(entry['created_at'])
            description = entry['description']
            tags = entry['tags']
            photo = entry['image_url'][0]
            coordinates = None
            if 'latitude' in entry and 'longitutde' in entry:
                coordinates = (float(entry['latitude']),
                               float(entry['longitutde']))

            if created_at > after:
                results.append(Entry(uniqueId,
                                     title,
                                     link,
                                     created_at,
                                     description=description,
                                     tags=tags,
                                     photo=photo,
                                     coordinates=coordinates))

        return list(reversed(results))

    def push(self, entry):
        raise NotImplementedError()


class Twitter(Connector):

    _CONSUMER_KEY = 'iF297JTU1bBTZx2jo8XkYBSzd'
    _CONSUMER_SECRET = '9mfE136ApHGUWpyPlMXJYAxBveTRN0pSebgOmwkt9ZXYXdOrp5'

    logger = logging.getLogger('soposy.connectors.twitter')

    def configure(self, name, section):
        Connector.configure(self, name, section)
        self.oauth_token = section['token']
        self.oauth_token_secret = section['token_secret']

    @classmethod
    def register_parser(cls, subparsers):
        cls.logger.debug('registering argument parser')
        parser = subparsers.add_parser('twitter')
        subparsers = parser.add_subparsers(title='Subcommands')

        # register
        parser_register = subparsers.add_parser(
            'register',
            description='Register at the twitter service using OAuth2')
        parser_register.set_defaults(action=cls.action_register)

    @classmethod
    def action_register(cls, args, config, conn):
        cls.logger.debug('Starting registration process')

        auth = tweepy.OAuthHandler(cls._CONSUMER_KEY, cls._CONSUMER_SECRET)
        redirect_url = auth.get_authorization_url()
        subprocess.check_call(['xdg-open', redirect_url])
        verifier = input('Enter generated verifier here and press enter: ')
        token = auth.get_access_token(verifier)

        print('''Use the following for your config:

  token = {token}
  token_secret = {token_secret}'''.format(token=token[0],
                                          token_secret=token[1]))

    def entries(self, after):
        raise NotImplementedError()

    def push(self, entry):
        auth = tweepy.OAuthHandler(self._CONSUMER_KEY, self._CONSUMER_SECRET)
        auth.set_access_token(self.oauth_token, self.oauth_token_secret)
        api = tweepy.API(auth)
        lat = None
        lon = None
        if entry.coordinates:
            lat = entry.coordinates[0]
            lon = entry.coordinates[1]
        api.update_status(self.template.format(entry=entry), lat=lat, long=lon)


class Pinterest(Connector):

    _CONSUMER_KEY = '4953521705369746033'
    _CONSUMER_SECRET = '8ec9c977b401734355728670d9a89e9b64ed43906' \
                       'ff9e4e35d36889ae7148c60'

    logger = logging.getLogger('soposy.connectors.pinterest')

    def configure(self, name, section):
        Connector.configure(self, name, section)
        self.oauth_token = section['token']
        self.board = section['board']

    @classmethod
    def register_parser(cls, subparsers):
        cls.logger.debug('registering argument parser')
        parser = subparsers.add_parser('pinterest')
        subparsers = parser.add_subparsers(title='Subcommands')

        # register
        parser_register = subparsers.add_parser(
            'register',
            description='Register at the pinterest service using OAuth2')
        parser_register.set_defaults(action=cls.action_register)

    @classmethod
    def action_register(cls, args, config, conn):
        cls.logger.debug('Starting registration process')

        oauth = OAuth2Session(
            cls._CONSUMER_KEY,
            # I'd be happy with write_public, but fetching the token fails
            # without all the others (bug in oauthlib?)
            scope=['read_public', 'read_private', 'read_write_all',
                   'write_private', 'write_public'],
            redirect_uri='https://localhost')
        authorization_url, state = oauth.authorization_url(
            'https://api.pinterest.com/oauth/')
        print('Please go to {} and authorize access.'.format(authorization_url))
        authorization_response = input(
            'Paste the full redirect localhost URL and press enter: ')
        token = oauth.fetch_token(
            'https://api.pinterest.com/v1/oauth/token',
            authorization_response=authorization_response,
            client_secret=cls._CONSUMER_SECRET)

        print('''Use the following for your config:

  token = {token}'''.format(token=token))

    def entries(self, after):
        raise NotImplementedError()

    def push(self, entry):
        self.logger.debug('Pushing entry %s', entry)
        if not entry.photo:
            raise RuntimeError("Entries need to have a photo")
        auth = OAuth2Session(self._CONSUMER_KEY,
                             token={'token_type': 'bearer',
                                    'access_token': self.oauth_token})
        data = {'board': self.board,
                'note': entry.title,
                'link': entry.link,
                'image_url': entry.photo}
        reply = auth.post('https://api.pinterest.com/v1/pins/',
                          data=data)
        reply.raise_for_status()


class Facebook(Connector):

    _ACCESS_TOKEN = '176692323109563|dc84928efe8874c7f00e5b1e08cf753b'

    logger = logging.getLogger('soposy.connectors.facebook')

    def configure(self, name, section):
        Connector.configure(self, name, section)
        self.access_token = section['token']
        self.template = section['template']

    @classmethod
    def register_parser(cls, subparsers):
        cls.logger.debug('registering argument parser')
        parser = subparsers.add_parser('facebook')
        subparsers = parser.add_subparsers(title='Subcommands')

        # register
        parser_register = subparsers.add_parser(
            'register',
            description='Register at the facebook service using OAuth2')
        parser_register.set_defaults(action=cls.action_register)

    @classmethod
    def action_register(cls, args, config, conn):
        cls.logger.debug('Starting registration process')

        reply = requests.post(
            'https://graph.facebook.com/v2.12/device/login',
            data={'access_token':
                  cls._ACCESS_TOKEN,
                  'scope': 'publish_actions'})
        reply.raise_for_status()
        request_data = reply.json()

        print("Open {} and insert {}".format(request_data['verification_uri'],
                                             request_data['user_code']))

        # poll for user reply
        wait_end = time.time() + request_data['expires_in']
        while time.time() < wait_end:
            time.sleep(request_data['interval'])
            reply = requests.post(
                'https://graph.facebook.com/v2.12/device/login_status',
                data={'access_token': cls._ACCESS_TOKEN,
                      'code': request_data['code']})
            # don't raise status, 400 is expected here
            wait_data = reply.json()

            if 'access_token' in wait_data:
                print('''Use the following for your config:

  token = {}'''.format(wait_data["access_token"]))
                break
            elif 'error' in wait_data:
                subcode = wait_data['error']['error_subcode']
                if subcode == 1349174:
                    # still have to wait
                    pass
                elif subcode == 1349172:
                    print('Polling too fast...')
                elif subcode == 1349152:
                    print('Request expired')
                    break
                else:
                    print('Unknown code {}'.format(subcode))

    def entries(self, after):
        raise NotImplementedError()

    def push(self, entry):
        self.logger.debug('Pushing entry %s', entry)
        reply = requests.post(
            'https://graph.facebook.com/v2.12/me/feed',
            data={'access_token': self.access_token,
                  'message': self.template.format(entry=entry),
                  'link': entry.link})
        reply.raise_for_status()


class Console(Connector):

    def configure(self, name, section):
        Connector.configure(self, name, section)
        self.template = section['template']

    @classmethod
    def register_parser(cls, subparsers):
        pass

    def entries(self, since):
        return []

    def push(self, entry):
        print(self.template.format(entry=entry))
