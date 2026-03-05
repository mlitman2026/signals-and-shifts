#!/usr/bin/env python3
"""Deploy to Netlify using the REST API with SHA1 digest uploads."""
import os
import hashlib
import json
import urllib.request
import urllib.error
import sys
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_SCRIPT_DIR)
_DEPLOY_ENV = os.environ.get('DEPLOY_DIR', '')
DEPLOY_DIR = os.path.abspath(_DEPLOY_ENV) if _DEPLOY_ENV else os.path.join(_PROJECT_DIR, 'deploy')
SITE_ID = os.environ.get('NETLIFY_SITE_ID', '976ac64e-9d8a-41b5-9ce9-5f886b205e57')
AUTH_TOKEN = os.environ.get('NETLIFY_TOKEN', 'nfp_PLKgWZbdCNqyN8Cbvob9n2JszWQGXvkC927c')
API_BASE = 'https://api.netlify.com/api/v1'


def sha1_file(filepath):
    h = hashlib.sha1()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def collect_files(deploy_dir):
    files = {}
    for root, dirs, filenames in os.walk(deploy_dir):
        for fname in filenames:
            filepath = os.path.join(root, fname)
            rel_path = '/' + os.path.relpath(filepath, deploy_dir)
            sha = sha1_file(filepath)
            files[rel_path] = sha
    return files


def api_request(method, path, data=None, content_type='application/json'):
    url = f'{API_BASE}{path}'
    headers = {
        'Authorization': f'Bearer {AUTH_TOKEN}',
        'Content-Type': content_type,
    }
    if data is not None and content_type == 'application/json':
        body = json.dumps(data).encode('utf-8')
    elif data is not None:
        body = data
    else:
        body = None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"HTTP {e.code}: {error_body[:500]}")
        raise


def main():
    print(f"Deploy directory: {DEPLOY_DIR}")
    print("Collecting files...")
    file_digests = collect_files(DEPLOY_DIR)
    print(f"Found {len(file_digests)} files to deploy.")

    print("\nCreating deploy...")
    deploy_data = {'files': file_digests}
    deploy = api_request('POST', f'/sites/{SITE_ID}/deploys', deploy_data)
    deploy_id = deploy['id']
    required = deploy.get('required', [])
    print(f"Deploy ID: {deploy_id}")
    print(f"Files to upload: {len(required)} of {len(file_digests)}")

    if required:
        sha_to_path = {}
        for root, dirs, filenames in os.walk(DEPLOY_DIR):
            for fname in filenames:
                filepath = os.path.join(root, fname)
                sha = sha1_file(filepath)
                if sha in required:
                    rel_path = '/' + os.path.relpath(filepath, DEPLOY_DIR)
                    sha_to_path[sha] = (filepath, rel_path)

        uploaded = 0
        for sha in required:
            if sha not in sha_to_path:
                print(f"  Warning: SHA {sha} not found locally, skipping")
                continue
            filepath, rel_path = sha_to_path[sha]
            with open(filepath, 'rb') as f:
                file_data = f.read()
            if filepath.endswith('.html'):
                ct = 'text/html'
            elif filepath.endswith('.js'):
                ct = 'application/javascript'
            elif filepath.endswith('.css'):
                ct = 'text/css'
            elif filepath.endswith('.json'):
                ct = 'application/octet-stream'
            elif filepath.endswith('.xml'):
                ct = 'application/xml'
            elif filepath.endswith('.png'):
                ct = 'image/png'
            elif filepath.endswith('.jpg') or filepath.endswith('.jpeg'):
                ct = 'image/jpeg'
            elif filepath.endswith('.svg'):
                ct = 'image/svg+xml'
            elif filepath.endswith('.webp'):
                ct = 'image/webp'
            elif filepath.endswith('.txt'):
                ct = 'text/plain'
            else:
                ct = 'application/octet-stream'
            try:
                api_request('PUT', f'/deploys/{deploy_id}/files{rel_path}', file_data, ct)
                uploaded += 1
                if uploaded % 20 == 0 or uploaded == len(required):
                    print(f"  Uploaded {uploaded}/{len(required)} files...")
            except Exception as e:
                print(f"  Error uploading {rel_path}: {e}")
        print(f"\nUploaded {uploaded} files.")

    print("\nChecking deploy status...")
    for attempt in range(10):
        time.sleep(3)
        status = api_request('GET', f'/deploys/{deploy_id}')
        state = status.get('state', 'unknown')
        print(f"  Status: {state}")
        if state == 'ready':
            print(f"\nDeploy successful!")
            print(f"  URL: {status.get('ssl_url', status.get('url', 'unknown'))}")
            print(f"  Deploy URL: {status.get('deploy_ssl_url', 'unknown')}")
            return
        elif state in ('error', 'failed'):
            print(f"\nDeploy failed: {status.get('error_message', 'unknown error')}")
            return
    print("\nDeploy still processing. Check Netlify dashboard.")


if __name__ == '__main__':
    main()
