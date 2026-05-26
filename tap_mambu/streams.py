"""Stream type classes for tap-mambu."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable

import requests
from hotglue_singer_sdk.plugin_base import PluginBase as TapBaseClass
from hotglue_singer_sdk import typing as th  # JSON Schema typing helpers
from singer.schema import Schema
from typing_extensions import override

from tap_mambu.client import MambuStream

_JSON_OBJECT = th.CustomType({"type": "object", "additionalProperties": True})


def _to_api_date(value: Any) -> str:
    """Normalize tap ``start_date`` (string or datetime) to ``YYYY-MM-DD`` for Mambu query params."""
    if value is None:
        return "2000-01-01"
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and len(value) >= 10 and value[4] == "-" and value[7] == "-":
        return value[:10]
    return str(value)[:10]


_gl_currency_schema = th.ObjectType(
    th.Property("currencyCode", th.StringType),
    th.Property("code", th.StringType),
)

_gl_account_schema = th.ObjectType(
    th.Property("encodedKey", th.StringType),
    th.Property("creationDate", th.DateTimeType),
    th.Property("lastModifiedDate", th.DateTimeType),
    th.Property("glCode", th.StringType),
    th.Property("type", th.StringType),
    th.Property("usage", th.StringType),
    th.Property("name", th.StringType),
    th.Property("activated", th.BooleanType),
    th.Property("description", th.StringType),
    th.Property("allowManualJournalEntries", th.BooleanType),
    th.Property("stripTrailingZeros", th.BooleanType),
    th.Property("currency", _gl_currency_schema),
)

_affected_amounts_schema = th.ObjectType(
    th.Property("principalAmount", th.NumberType),
    th.Property("interestAmount", th.NumberType),
    th.Property("interestFromArrearsAmount", th.NumberType),
    th.Property("deferredInterestAmount", th.NumberType),
    th.Property("feesAmount", th.NumberType),
    th.Property("penaltyAmount", th.NumberType),
    th.Property("fundersInterestAmount", th.NumberType),
    th.Property("organizationCommissionAmount", th.NumberType),
)

_taxes_schema = th.ObjectType(
    th.Property("taxOnInterestAmount", th.NumberType),
    th.Property("taxOnInterestFromArrearsAmount", th.NumberType),
    th.Property("deferredTaxOnInterestAmount", th.NumberType),
    th.Property("taxOnFeesAmount", th.NumberType),
    th.Property("taxOnPenaltyAmount", th.NumberType),
)

_account_balances_schema = th.ObjectType(
    th.Property("totalBalance", th.NumberType),
    th.Property("advancePosition", th.NumberType),
    th.Property("arrearsPosition", th.NumberType),
    th.Property("expectedPrincipalRedraw", th.NumberType),
    th.Property("redrawBalance", th.NumberType),
    th.Property("principalBalance", th.NumberType),
)

_terms_schema = th.ObjectType(
    th.Property(
        "interestSettings",
        th.CustomType({"type": "object", "additionalProperties": True}),
    ),
)


class JournalEntriesStream(MambuStream):
    """General ledger journal entries (``GET /gljournalentries``).

    Requests the inclusive date window from configured ``start_date`` through today's UTC date,
    with offset/limit pagination driven by ``Items-*`` response headers.
    """

    name = "journal_entries"
    path = "/gljournalentries"
    primary_keys = ["encodedKey"]
    replication_key = None
    next_page_token_jsonpath = None

    schema = th.PropertiesList(
        th.Property("encodedKey", th.StringType, description="Mambu encoded key (primary identifier)"),
        th.Property("entryID", th.IntegerType),
        th.Property("creationDate", th.DateTimeType),
        th.Property("bookingDate", th.DateTimeType),
        th.Property("transactionId", th.StringType),
        th.Property("accountKey", th.StringType),
        th.Property("productKey", th.StringType),
        th.Property("productType", th.StringType),
        th.Property("amount", th.NumberType),
        th.Property("glAccount", _gl_account_schema),
        th.Property("type", th.StringType, description="Entry side, e.g. CREDIT or DEBIT"),
    ).to_dict()

    def _page_limit(self) -> int:
        return int(self.config.get("page_size", 50))

    def _date_from(self) -> str:
        return _to_api_date(self.config.get("start_date"))

    def _date_to(self) -> str:
        return datetime.now(timezone.utc).date().isoformat()

    @override
    def get_child_context(self, record: dict, context: dict | None) -> dict:
        """Build URL context for :class:`TransactionsStream` (skipped when no transaction id)."""
        tid = record.get("transactionId")
        if tid is None or str(tid).strip() == "":
            return {"_skip_transaction_sync": True}

        product_type = (record.get("productType") or "").strip().upper()
        if product_type == "LOAN":
            mambu_product = "loans"
        elif product_type == "SAVINGS":
            mambu_product = "deposits"
        else:
            msg = (
                "Unrecognized journal_entries productType "
                f"{record.get('productType')!r} (expected LOAN or SAVINGS) for "
                f"transactionId={tid!r}, encodedKey={record.get('encodedKey')!r}"
            )
            raise ValueError(msg)

        return {
            "_skip_transaction_sync": False,
            "mambu_product": mambu_product,
            "transaction_id": str(tid),
            "journal_entry_encoded_key": record.get("encodedKey"),
        }

    @override
    def get_url_params(
        self,
        context: dict | None,
        next_page_token: Any | None,
    ) -> dict[str, Any]:
        offset = 0 if next_page_token is None else int(next_page_token)
        return {
            "from": self._date_from(),
            "to": self._date_to(),
            "paginationDetails": "ON",
            "limit": self._page_limit(),
            "offset": offset,
        }

    @override
    def get_next_page_token(
        self,
        response: requests.Response,
        previous_token: Any | None,
    ) -> Any | None:
        try:
            offset = int(response.headers.get("Items-Offset", "0"))
            limit = int(response.headers.get("Items-Limit", str(self._page_limit())))
            total = int(response.headers.get("Items-Total", "0"))
        except ValueError:
            return None
        next_offset = offset + limit
        if next_offset >= total:
            return None
        return next_offset


class TransactionsStream(MambuStream):
    """Loan or deposit transaction detail, one GET per distinct transaction id.

    Parent :class:`JournalEntriesStream` supplies ``mambu_product`` (``loans`` or ``deposits``)
    and ``transaction_id`` so this stream calls either ``GET /loans/transactions/{id}`` or
    ``GET /deposits/transactions/{id}`` with ``detailsLevel=FULL``.

    Multiple GL lines often share the same ``transaction_id`` (e.g. debit/credit pair). During
    a sync we only keep a **set** of ``(mambu_product, transaction_id)`` keys already fetched;
    additional journal lines for the same id are skipped (no duplicate HTTP, no second RECORD).
    ``journal_entry_encoded_key`` refers to the **first** parent line that caused the fetch.
    """

    name = "transactions"
    path = "/{mambu_product}/transactions/{transaction_id}"
    primary_keys = ["encodedKey"]
    replication_key = None
    next_page_token_jsonpath = None
    parent_stream_type = JournalEntriesStream
    ignore_parent_replication_key = True

    schema = th.PropertiesList(
        th.Property(
            "journal_entry_encoded_key",
            th.StringType,
            description=(
                "Parent GL journal line ``encodedKey`` that triggered this fetch "
                "(first line seen when several lines share the same transaction id)."
            ),
        ),
        th.Property("encodedKey", th.StringType, description="Transaction encoded key"),
        th.Property("id", th.StringType, description="Transaction id (matches journal transactionId)"),
        th.Property("creationDate", th.DateTimeType),
        th.Property("valueDate", th.DateTimeType),
        th.Property("bookingDate", th.DateTimeType),
        th.Property("parentAccountKey", th.StringType),
        th.Property("type", th.StringType, description="Transaction type, e.g. PENALTY_APPLIED"),
        th.Property("amount", th.NumberType),
        th.Property("affectedAmounts", _affected_amounts_schema),
        th.Property("taxes", _taxes_schema),
        th.Property("accountBalances", _account_balances_schema),
        th.Property("terms", _terms_schema),
        th.Property("transactionDetails", _JSON_OBJECT),
        th.Property("fees", th.ArrayType(_JSON_OBJECT)),
    ).to_dict()

    def __init__(
        self,
        tap: TapBaseClass,
        name: str | None = None,
        schema: dict[str, Any] | Schema | None = None,
        path: str | None = None,
    ) -> None:
        super().__init__(tap, name=name, schema=schema, path=path)
        self.state_partitioning_keys = []
        self._seen_transaction_keys: set[tuple[str, str]] = set()

    @override
    def get_records(self, context: dict | None) -> Iterable[dict[str, Any]]:
        ctx = context or {}
        if ctx.get("_skip_transaction_sync"):
            return
        key = (str(ctx.get("mambu_product", "")), str(ctx.get("transaction_id", "")))
        if key in self._seen_transaction_keys:
            return
        yield from super().get_records(ctx)
        self._seen_transaction_keys.add(key)

    @override
    def get_url_params(
        self,
        context: dict | None,
        next_page_token: Any | None,
    ) -> dict[str, Any]:
        return {"detailsLevel": "FULL"}

    @override
    def get_next_page_token(
        self,
        response: requests.Response,
        previous_token: Any | None,
    ) -> Any | None:
        return None

    @override
    def parse_response(self, response: requests.Response) -> Iterable[dict]:
        body = response.json()
        if isinstance(body, list):
            yield from body
        elif isinstance(body, dict):
            yield body

    @override
    def post_process(self, row: dict, context: dict | None = None) -> dict | None:
        ctx = context or {}
        jkey = ctx.get("journal_entry_encoded_key")
        if jkey is not None:
            row["journal_entry_encoded_key"] = jkey
        return row
