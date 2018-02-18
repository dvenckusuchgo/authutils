# pylint: disable=redefined-outer-name,unused-variable
"""
Define pytest fixtures for testing auth utils.
"""

from datetime import datetime, timedelta
import os
import uuid

import flask
import jwt
import mock
import pytest
import requests

from authutils.token.validate import require_auth_header

from tests.utils import TEST_RESPONSE_JSON


USER_API = 'https://user-api.test.net'
KEYS_URL = 'https://user-api.test.net/jwt/keys'


@pytest.fixture(scope='session')
def iss():
    """
    Return the token issuer (``USER_API``).
    """
    return USER_API


@pytest.fixture(scope='session')
def default_audiences():
    """
    Return some default audiences to put in the claims of a JWT.
    """
    # Note that ``test_aud`` here is the audience expected on the test endpoint
    # in the test application.
    return ['openid', 'access', 'user', 'test_aud']


@pytest.fixture(scope='session')
def claims(default_audiences, iss):
    """
    Return some generic claims to put in a JWT.

    Return:
        dict: dictionary of claims
    """
    now = datetime.now()
    iat = int(now.strftime('%s'))
    exp = int((now + timedelta(seconds=60)).strftime('%s'))
    return {
        'pur': 'access',
        'aud': default_audiences,
        'sub': '1234',
        'iss': iss,
        'iat': iat,
        'exp': exp,
        'jti': str(uuid.uuid4()),
        'context': {
            'user': {
                'name': 'test-user',
                'projects': [
                ],
            },
        },
    }


@pytest.fixture(scope='session')
def default_kid():
    return 'key-01'


@pytest.fixture(scope='session')
def token_headers(default_kid):
    return {'kid': default_kid}


@pytest.fixture(scope='session')
def example_keys_response(default_kid, public_key, different_public_key):
    """
    Return an example response JSON returned from the ``/jwt/keys`` endpoint in
    fence.
    """
    return {
        'keys': [
            [default_kid, public_key],
            ['key-02', different_public_key],
        ]
    }


@pytest.fixture(scope='session')
def public_key():
    """
    Return a public key for testing.
    """
    os.path.dirname(os.path.realpath(__file__))
    here = os.path.dirname(os.path.realpath(__file__))
    with open(os.path.join(here, 'test_public_key.pem')) as f:
        return f.read()


@pytest.fixture(scope='session')
def different_public_key():
    """
    Return a public key for testing that doesn't form a correct keypair with
    ``private_key``.
    """
    os.path.dirname(os.path.realpath(__file__))
    here = os.path.dirname(os.path.realpath(__file__))
    with open(os.path.join(here, 'test_public_key_2.pem')) as f:
        return f.read()


@pytest.fixture(scope='session')
def private_key():
    """
    Return a private key for testing. (Use only a private key that is
    specifically set aside for testing, and never actually used for auth.)
    """
    os.path.dirname(os.path.realpath(__file__))
    here = os.path.dirname(os.path.realpath(__file__))
    with open(os.path.join(here, 'test_private_key.pem')) as f:
        return f.read()


@pytest.fixture(scope='session')
def encoded_jwt(claims, token_headers, private_key):
    """
    Return an example JWT containing the claims and encoded with the private
    key.

    Args:
        claims (dict): fixture
        private_key (str): fixture

    Return:
        str: JWT containing claims encoded with private key
    """
    return jwt.encode(
        claims, headers=token_headers, key=private_key, algorithm='RS256'
    )


@pytest.fixture(scope='session')
def encoded_jwt_expired(claims, token_headers, private_key):
    claims_expired = claims.copy()
    # Move issued and expiration times into the past.
    claims_expired['iat'] -= 100000
    claims_expired['exp'] -= 100000
    return jwt.encode(
        claims_expired,
        headers=token_headers,
        key=private_key,
        algorithm='RS256',
    )


@pytest.fixture(scope='session')
def auth_header(encoded_jwt):
    """
    Return an authorization header containing the example JWT.

    Args:
        encoded_jwt (str): fixture

    Return:
        List[Tuple[str, str]]: the authorization header
    """
    return [('Authorization', 'Bearer {}'.format(encoded_jwt))]


@pytest.fixture(scope='function')
def app():
    """
    Set up a basic flask app for testing.
    """
    app = flask.Flask(__name__)
    app.debug = True
    app.config['USER_API'] = USER_API

    @app.route('/test')
    @require_auth_header({'test_aud'}, 'access')
    def test_endpoint():
        """
        Define a simple endpoint for testing which requires a JWT header for
        authorization.
        """
        return flask.jsonify(TEST_RESPONSE_JSON)

    context = app.app_context()
    context.push()
    yield app
    context.pop()


@pytest.fixture(scope='function')
def mock_get(monkeypatch, example_keys_response):
    """
    Provide a function to patch the value of the JSON returned by
    ``requests.get``.

    (NOTE that this only patches what will return from ``requests.get`` so if
    the implementation of ``refresh_jwt_public_keys`` is changed to use a
    different method to access the fence endpoint, this should be updated.)

    Args:
        monkeypatch (pytest.monkeypatch.MonkeyPatch): fixture

    Return:
        Calllable[dict, None]:
            function which sets the reponse JSON of ``requests.get``
    """

    def do_patch(urls_to_responses=None):
        """
        Args:
            keys_response_json (dict): value to set /jwt/keys return value to

        Return:
            None

        Side Effects:
            Patch ``requests.get``
        """
        urls_to_responses = urls_to_responses or {}
        defaults = {KEYS_URL: example_keys_response}
        defaults.update(urls_to_responses)
        urls_to_responses = defaults

        def get(url):
            """Define a mock ``get`` function to return a mocked response."""
            mocked_response = mock.MagicMock(requests.Response)
            mocked_response.json.return_value = urls_to_responses[url]
            return mocked_response

        monkeypatch.setattr('requests.get', mock.MagicMock(side_effect=get))

    return do_patch