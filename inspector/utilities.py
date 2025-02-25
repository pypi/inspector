import urllib.parse

import requests


def mailto_report_link(project_name, version, platform, file_path, request_url):
    """
    Generate a mailto report link for malicious code.
    """
    message_body = (
        "RubyGems Malicious Package Report\n"
        "--\n"
        f"Gem: {project_name}\n"
        f"Version: {version}\n"
        f"Platform: {platform}\n"
        f"File Path: {file_path}\n"
        f"Inspector URL: {request_url}\n\n"
        "Additional Information:\n\n"
    )

    subject = f"Malicious Package Report: {project_name}"

    return (
        f"mailto:security@rubygems.org?"
        f"subject={urllib.parse.quote(subject)}"
        f"&body={urllib.parse.quote(message_body)}"
    )


def requests_session(
    custom_user_agent: str = "inspector.rubygems.info",
) -> requests.Session:
    """
    Custom `requests` session with default headers applied.

    Usage:

    >>> from inspector.utilities import requests_session
    >>> response = requests_session().get(<url>)
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": custom_user_agent,
        }
    )

    return session
