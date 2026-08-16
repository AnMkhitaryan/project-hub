import json
import os
import urllib.parse
import urllib.request

API_BASE_URL = os.environ["API_BASE_URL"]
INTERNAL_API_SECRET = os.environ["INTERNAL_API_SECRET"]


def _project_id_from_key(key):
    decoded = urllib.parse.unquote_plus(key)
    parts = decoded.split("/")
    if len(parts) < 2 or parts[0] != "projects":
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def handler(event, context):
    project_ids = set()
    for record in event.get("Records", []):
        key = record.get("s3", {}).get("object", {}).get("key", "")
        project_id = _project_id_from_key(key)
        if project_id is not None:
            project_ids.add(project_id)

    results = []
    for project_id in project_ids:
        url = f"{API_BASE_URL}/internal/projects/{project_id}/recalculate-size"
        request = urllib.request.Request(
            url,
            method="POST",
            headers={"X-Internal-Secret": INTERNAL_API_SECRET},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            results.append(json.loads(response.read()))

    return {"recalculated": results}
