import os
import sys
import requests
import argparse


token = os.environ['FOG_GITHUB_TOKEN']

parser = argparse.ArgumentParser()
parser.add_argument('repo', help='repository_name, for example "galaxy-integrations-updater"')
parser.add_argument('event_type', help='event type, for example "update_templates"')
args = parser.parse_args()

url = f'https://api.github.com/repos/FriendsOfGalaxy/{args.repo}/dispatches'
body = {
    "event_type": args.event_type
}
headers = {
    "Authorization": "token " + token,
    "Accept": "application/vnd.github.everest-preview+json, application/vnd.github.v3+json",
    "Content-Type": "application/json"
}

print(f'Sending url={url}, body={body}, headers={headers}')
r = requests.post(url=url, json=body, headers=headers)

if r.status_code > 300:
    text = '<parsing failed>'
    try:
        text = r.json()
    finally:
        raise RuntimeError(f'Reqeust failed; status_code: {str(r.status_code)}, response: {text}')
print(f"Success (status: {r.status_code})")