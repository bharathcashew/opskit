"""Built-in AWS checks. All are read-only; see docs/iam-policy.json for the minimal policy."""


def paginate(client, method: str, key: str, **kwargs):
    """Yield items from a paginated AWS API call."""
    paginator = client.get_paginator(method)
    for page in paginator.paginate(**kwargs):
        yield from page.get(key, [])


def name_tag(tags: list[dict] | None) -> str | None:
    for t in tags or []:
        if t.get("Key") == "Name":
            return t.get("Value")
    return None
