import urllib.parse

import requests


def mailto_report_link(project_name, version, file_path, request_url):
    """
    Generate a mailto report link for malicious code.
    """
    message_body = (
        "PyPI Malicious Package Report\n"
        "--\n"
        f"Package Name: {project_name}\n"
        f"Version: {version}\n"
        f"File Path: {file_path}\n"
        f"Inspector URL: {request_url}\n\n"
        "Additional Information:\n\n"
    )

    subject = f"Malicious Package Report: {project_name}"

    return (
        f"mailto:security@pypi.org?"
        f"subject={urllib.parse.quote(subject)}"
        f"&body={urllib.parse.quote(message_body)}"
    )


def pypi_report_form(project_name, version, file_path, request_url):
    """
    Generate a URL to PyPI malware report for malicious code.
    """
    summary = (
        f"Version: {version}\n"
        f"File Path: {file_path}\n"
        "Additional Information:\n\n"
    )

    return (
        f"https://pypi.org/project/{project_name}/submit-malware-report/"
        f"?inspector_link={request_url}"
        f"&summary={urllib.parse.quote(summary)}"
    )


def requests_session(custom_user_agent: str = "inspector.pypi.io") -> requests.Session:
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
