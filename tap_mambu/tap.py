"""Mambu tap class."""

from __future__ import annotations

from hotglue_singer_sdk import Stream, Tap
from hotglue_singer_sdk import typing as th  # JSON schema typing helpers
from typing_extensions import override

from tap_mambu.streams import JournalEntriesStream, TransactionsStream

STREAM_TYPES = [
    JournalEntriesStream,
    TransactionsStream,
]


class TapMambu(Tap):
    """Singer tap for Mambu."""

    name = "tap-mambu"

    # TODO: Update this section with the actual config values you expect:
    config_jsonschema = th.PropertiesList(
        th.Property(
            "start_date",
            th.DateTimeType,
            description="The earliest record date to sync",
            default="2000-01-01T00:00:00Z",
        ),
        th.Property(
            "api_url",
            th.StringType,
            description="Base URL for the Mambu API",
            default="https://mbuhotglue.sandbox.mambu.com/api",
        ),
        th.Property(
            "access_key",
            th.StringType,
            required=True,
            description="The API key sent in the ``apiKey`` header for Mambu v2 REST calls",
        ),
        th.Property(
            "page_size",
            th.IntegerType,
            description="Page size (``limit``) for offset pagination on GL journal entries",
            default=50,
        ),
    ).to_dict()

    @override
    def discover_streams(self) -> list[Stream]:
        """Return a list of discovered streams."""
        return [stream_class(tap=self) for stream_class in STREAM_TYPES]


if __name__ == "__main__":
    TapMambu.cli()
