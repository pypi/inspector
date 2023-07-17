from dataclasses import dataclass
from enum import Enum

import jinja2.filters


class DetailSeverity(Enum):
    NORMAL = 1
    MEDIUM = 2
    HIGH = 3


@dataclass
class Detail:
    severity: DetailSeverity
    prop_name: str
    value: str | None = None
    unsafe: bool = False

    def html(self):
        match self.severity:
            case DetailSeverity.MEDIUM:
                color = "orange"
            case DetailSeverity.HIGH:
                color = "red"
            case _:
                color = "#000000"

        # just to be safe here, sanitize the property name and value...
        propname_sanitized = self.prop_name if self.unsafe else jinja2.filters.escape(self.prop_name)

        if self.value:
            value_sanitized = self.value if self.unsafe else jinja2.filters.escape(self.value)
            return f"<strong>{propname_sanitized}</strong>: <span style='color: {color};'>{value_sanitized}</span>"

        return f"<strong><span style='color: {color};'>{propname_sanitized}</span></strong>"


