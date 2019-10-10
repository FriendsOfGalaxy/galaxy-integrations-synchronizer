import os
import sys
import requests

event_type = sys.argv[1]
token = os.environ['TEST_REPO_TOKEN']

url = 'https://api.github.com/repos/FriendsOfGalaxy/test-integration-fork/dispatches'
body = {
    "event_type": event_type
}
headers = {
    "Authorization": "token " + token,
    "Accept": "application/vnd.github.everest-preview+json, application/vnd.github.v3+json",
    "Content-Type": "application/json"
}

r = requests.post(url=url, json=body, headers=headers)

if r.status_code > 300:
    text = '<parsing failed>'
    try:
        text = r.json()
    finally:
        raise RuntimeError(f'Reqeust failed; status_code: {str(r.status_code)}, response: {text}')
