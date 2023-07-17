import urllib.parse


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
