# AGENTS.md - AI Agent Development Guide for tap-mambu



This document provides guidance for AI coding agents and developers working on this Singer tap. The **Project Overview** reflects the options used when this project was generated.

## Project Overview

- **Project Type**: Singer Tap
- **Source**: Mambu
- **Stream Type**: REST
- **Authentication**: API Key
- **Framework**: Hotglue Singer SDK (hotglue_singer_sdk)

## Architecture

This tap follows the Singer specification and uses the Hotglue Singer SDK (hotglue_singer_sdk) to extract data from Mambu.

### Key Components

1. **Tap Class** (`tap_mambu/tap.py`): Main entry point, defines streams and configuration
2. **Client** (`tap_mambu/client.py`): HTTP client, stream base class, and (where applicable) how auth is attached to requests
3. **Streams** (`tap_mambu/streams.py`): Stream classes, schemas (`th.PropertiesList`), and—depending on stream type—`path`, `query`, or custom extraction hooks

## Development Guidelines for AI Agents

### Understanding Singer Concepts

Before making changes, ensure you understand these Singer concepts:

- **Streams**: Individual data endpoints (e.g., users, orders, transactions)
- **State**: Tracks incremental sync progress using bookmarks
- **Catalog**: Metadata about available streams and their schemas
- **Records**: Individual data items emitted by the tap
- **Schemas**: JSON Schema definitions for stream data

### Stream type notes (this template)

- **REST**: Each stream typically sets **`path`** (under `url_base`), **`records_jsonpath`**, and pagination via **`get_next_page_token()`** / URL params in **`client.py`** or overrides on the stream class—match your vendor’s API.

### Parent-Child Streams

The Tap SDK supports parent-child streams, by which one stream type can be declared to
be a parent to another stream, and the child stream will automatically receive `context`
from a parent record each time the child stream is invoked.

To utilize parent-child streams

1. Set [`parent_stream_type`](singer_sdk.Stream.parent_stream_type) in the child-stream's class to the class of the parent.
2. Implement one of the below methods to pass context from the parent to the child:
   1. Override [`get_child_context`](singer_sdk.Stream.get_child_context) to return a new
      child context object based on records and any existing context from the parent stream.
   1. If you need to sync more than one child stream per parent record, you can override
      [`generate_child_contexts`](singer_sdk.Stream.generate_child_contexts) to yield as many
      contexts as you need.
3. If the parent stream's replication key won't get updated when child items are changed,
   indicate this by adding [`ignore_parent_replication_key = True`](singer_sdk.Stream.ignore_parent_replication_key)
   in the child stream class declaration.
4. If the number of _parent_ items is very large (thousands or tens of thousands), you can
   optionally set [`state_partitioning_keys`](singer_sdk.Stream.state_partitioning_keys) on the child stream to specify a subset of context keys to use
   in state bookmarks. (When not set, the number of bookmarks will be equal to the number
   of parent items.) If you do not wish to store any state bookmarks for the child stream, set [`state_partitioning_keys`](singer_sdk.Stream.state_partitioning_keys) to `[]`.

#### Example parent-child implementation

Here is an abbreviated example which uses the above techniques.
In this example, EpicIssuesStream is a child of EpicsStream.

```py
class GitlabStream(RESTStream):
    # Base stream definition with auth and pagination logic
    # This logic works for other base classes as well, including Stream, GraphQLStream, etc.


class EpicsStream(GitlabStream):

    name = "epics"

    # ...

    def get_child_context(self, record: dict, context: Optional[dict]) -> dict:
        """Return a context dictionary for child streams."""
        return {
            "group_id": record["group_id"],
            "epic_id": record["id"],
            "epic_iid": record["iid"],
        }


class EpicIssuesStream(GitlabStream):
    # Note that this class inherits from the GitlabStream base class, and not from
    # the EpicsStream class.

    name = "epic_issues"

    # EpicIssues streams should be invoked once per parent epic:
    parent_stream_type = EpicsStream

    # Assume epics don't have `updated_at` incremented when issues are changed:
    ignore_parent_replication_key = True

    # Path is auto-populated using parent context keys:
    path = "/groups/{group_id}/epics/{epic_iid}/issues"

    # ...
```

#### How Path Parameter Replacement Works

In the example above, the `path` contains placeholders like `{group_id}` and `{epic_iid}`. These are **not** instance properties—they're context variables that get automatically replaced.

The SDK's [`get_url()`](singer_sdk.RESTStream.get_url) method extracts these values from each context dictionary yielded by the parent's [`generate_child_contexts()`](singer_sdk.Stream.generate_child_contexts). For each parent record, the child stream receives one or more context dictionaries like:

```python
{
    "group_id": 123,
    "epic_id": 456,
    "epic_iid": 789,
}
```

The SDK then substitutes these into the path, producing URLs like:

```
/groups/123/epics/789/issues
```

```{note}
All the keys in the `context` dictionary are added to the child's record, but they will be automatically removed if they are not present in the child's schema. If you wish to preserve these keys in the child's record, you must add them to the child's schema.
```

### Common Tasks

#### Adding a New Stream

1. Add a stream class in `tap_mambu/streams.py` (follow naming: PascalCase + `Stream`, Singer **`name`** in snake_case—consistent with existing streams).
2. Set **`primary_keys`** and **`replication_key`** (use `None` if not incremental).
3. Set **`name`** and **`path`** (relative to `url_base` in `client.py`).
4. Define **`schema`** with `th.PropertiesList` / `th.Property` (same style as the generated streams).
5. Add the class to **`STREAM_TYPES`** in `tap.py` and to the **`from tap_mambu.streams import (...)`** block (Cookiecutter pre-fills both from **`stream_names`**).

Example (aligned with `streams.py`):

```python
from hotglue_singer_sdk import typing as th

from tap_mambu.client import MambuStream


class MyNewStream(MambuStream):
    name = "my_new_stream"
    path = "/api/v1/my_resource"
    primary_keys = ["id"]
    replication_key = "updated_at"

    schema = th.PropertiesList(
        th.Property("id", th.StringType, description="Primary key"),
        th.Property("name", th.StringType),
        th.Property("updated_at", th.DateTimeType),
    ).to_dict()
```

#### Briefing an AI agent with `curl` and a sample response

To get a useful update to **`streams.py`**, **`client.py`** (pagination / JSON paths), and—if it is a **new** stream—**`tap.py`** (`STREAM_TYPES` + import), send a message shaped roughly like this:

1. **Goal**: e.g. “Add stream `payouts`” or “Fix schema + pagination on `FinancialTransactionsStream`.”
2. **Request**: Paste the **`curl`** (or HTTP method + path + query) you use. **Redact** tokens, keys, and cookies; placeholders like `REDACTED` are fine.
3. **Response**: Paste a **realistic JSON** body (trim huge arrays to a few items). If the list is nested (e.g. `data.items`), say where records live.
4. **Pagination**: State how the next page is indicated (cursor in JSON, `Link` header, `page` / `offset`, or none).
5. **Incremental sync**: Which field should be the **replication key** (if any), and which field(s) are **primary keys**—or say “full table” if not incremental.
6. **Optional**: Auth quirks (special headers, required query params) if they affect this endpoint.

The agent should align **`name`**, **`path`** (or **`query`** for GraphQL), **`schema`**, **`records_jsonpath`** / **`get_next_page_token()`** in **`tap_mambu/client.py`** when needed, and **`STREAM_TYPES`** + imports in **`tap.py`** for new streams. See **Handling Pagination** and **Adding a New Stream** above.

#### Modifying Authentication

- Update `authenticator` in client class
- API key should be passed via headers or query parameters
- Configuration defined in `tap.py` config schema

#### Handling Pagination

The scaffold pages over HTTP using **`get_next_page_token()`** on the stream class (see **`tap_mambu/client.py`** for the default implementation using JSONPath / headers). Return the value the SDK should pass on the next request (page number, cursor, URL, etc.); return **`None`** when there is no next page. **GraphQL** APIs often expose cursors inside the JSON body—parse those here and thread the token into the request builder your client uses.

The method signature matches the base stream (roughly: `response`, `previous_token`). Adapt the body to your API.

**Next token in the JSON body** (cursor, page number, etc.):

```python
from typing import Any

import requests
from typing_extensions import override

class MyStream(MambuStream):
    @override
    def get_next_page_token(
        self,
        response: requests.Response,
        previous_token: Any | None,
    ) -> Any | None:
        body = response.json()
        # TODO: Adjust keys to match your API.
        if not body.get("has_more", False):
            return None
        return body.get("pagination", {}).get("next_cursor")
```

_The snippets below assume the same imports: `from typing import Any`, `import requests`, and `from typing_extensions import override`._

**Next page via `Link` header** (or similar):

```python
@override
def get_next_page_token(
    self,
    response: requests.Response,
    previous_token: Any | None,
) -> Any | None:
    links = getattr(response, "links", None) or {}
    nxt = links.get("next", {}).get("url")
    return nxt  # or parse out ?page=… / cursor if your client expects a token, not a full URL
```

**Numeric page index** (increment each call):

```python
@override
def get_next_page_token(
    self,
    response: requests.Response,
    previous_token: Any | None,
) -> Any | None:
    page = 1 if previous_token is None else int(previous_token) + 1
    data = response.json()
    if page > data.get("total_pages", 1):
        return None
    return page
```

**Single-page / no pagination:**

```python
@override
def get_next_page_token(
    self,
    response: requests.Response,
    previous_token: Any | None,
) -> Any | None:
    return None
```

Wire the token into query params or headers in **`get_url_params()`** (or equivalent) using `next_page_token` so each request uses the value you return here.

#### State and Incremental Sync

- Set `replication_key` to enable incremental sync (e.g., "updated_at")
- Override `get_starting_timestamp()` to set initial sync point
- State automatically managed by SDK
- Access current state via `get_context_state()`

#### Schema Evolution

- Use flexible schemas during development
- Add new properties without breaking changes
- Consider making fields optional when unsure
- Use `th.Property("field", th.StringType)` for basic types
- Nest objects with `th.ObjectType(...)`

### Testing

Run tests to verify your changes (same virtualenv workflow as `README.md`: `python3 -m venv .venv`, activate it, then `pip install -e .`):

```bash
pip install pytest
pytest

# Run a specific test
pytest tests/test_core.py -k test_name
```

### Configuration

Configuration properties are defined in the tap class:

- Required vs optional properties
- Defaults specified in config schema
- Sensitive credentials (tokens, passwords) — flag them as `sensitive: true` in `meltano.yml` and document them as sensitive in `README.md`.

Example configuration schema:

```python
from hotglue_singer_sdk import typing as th

config_jsonschema = th.PropertiesList(
    th.Property("api_url", th.StringType, required=True),
    th.Property("access_key", th.StringType, required=True),
    th.Property("start_date", th.DateTimeType),
).to_dict()
```

Example test with config:

```bash
tap-mambu --config config.json --discover
tap-mambu --config config.json --catalog catalog.json
```

### Keeping tap config, docs, and env in sync

Authoritative settings live in **`config_jsonschema`** on the tap class in `tap_mambu/tap.py` (Hotglue Singer SDK). Everything operators and Hotglue jobs read should match that schema.

**When to sync:**

- Adding new configuration properties to the tap
- Removing or renaming existing properties
- Changing property types, defaults, or descriptions
- Marking properties as required, or flagging sensitive credentials in `meltano.yml`

**How to sync (typical flow for this template):**

1. Update `config_jsonschema` in `tap_mambu/tap.py`.
2. Update **`README.md`**: the configuration table, the example `config.json`, and any prose that names settings.
3. Update **`.env.example`** so variable names stay aligned with `tap-mambu --about` / `--config=ENV` (keys are derived from config property names).
4. If the tap runs on **Hotglue**, align connector or job configuration in the Hotglue product with the same keys and types ([Hotglue documentation](https://docs.hotglue.com)).

Example — adding a new `batch_size` setting:

```python
# tap_mambu/tap.py
config_jsonschema = th.PropertiesList(
    th.Property("api_url", th.StringType, required=True),
    th.Property("access_key", th.StringType, required=True),
    th.Property("batch_size", th.IntegerType, default=100),  # New setting
).to_dict()
```

Example snippet for `README.md`’s **Example `config.json`** section:

```json
{
  "api_url": "https://api.example.com",
  "access_key": "YOUR_ACCESS_KEY",
  "batch_size": 100
}
```

```bash
# .env.example (prefix matches this tap’s env mapping; see --about)
TAP_MAMBU_API_URL=https://api.example.com
TAP_MAMBU_ACCESS_KEY=your_access_key_here
TAP_MAMBU_BATCH_SIZE=100
```

**JSON shape vs SDK types:**

| `th.*` in `config_jsonschema` | Typical JSON in `config.json` |
|-------------------------------|-------------------------------|
| `StringType` | string |
| `IntegerType` | integer |
| `BooleanType` | boolean |
| `NumberType` | number |
| `DateTimeType` | string (ISO-8601 datetime) |
| `ArrayType` | array |
| `ObjectType` | object |

For credentials, set `sensitive: true` on the matching setting in `meltano.yml`, document them as sensitive in `README.md`, and never commit real values.

**Best practices:**

- Update `tap.py`, `README.md`, and `.env.example` together so CLI, docs, and env-based runs stay consistent.
- Prefer `tap-mambu --about` (or `--format=markdown`) as the generated reference for your tree.

> **Note:** Target and mapper patterns in the [Hotglue Singer SDK](https://github.com/hotgluexyz/HotglueSingerSDK) follow the same idea: one source of truth for settings in code, reflected everywhere operators look.

### Common Pitfalls

1. **Rate Limiting**: Implement backoff using `RESTStream` built-in retry logic
2. **Large Responses**: Use pagination, don't load entire dataset into memory
3. **Schema Mismatches**: Validate data matches schema, handle null values
4. **State Management**: Don't modify state directly, use SDK methods
5. **Timezone Handling**: Use UTC, parse ISO 8601 datetime strings
6. **Error Handling**: Let SDK handle retries, log warnings for data issues

### SDK Resources

- [Hotglue Singer SDK (GitHub)](https://github.com/hotgluexyz/HotglueSingerSDK)
- [Singer specification](https://github.com/singer-io/getting-started/blob/master/docs/SPEC.md) (community reference)
- Stream maps and SDK APIs: installed `hotglue_singer_sdk` package and the HotglueSingerSDK repository

### Best Practices

1. **Logging**: Use `self.logger` for structured logging
2. **Validation**: Validate API responses before emitting records
3. **Documentation**: Update README with new streams and config options
4. **Type Hints**: Add type hints to improve code clarity
5. **Testing**: Write tests for new streams and edge cases
6. **Performance**: Profile slow streams, optimize API calls
7. **Error Messages**: Provide clear, actionable error messages

## File Structure

```
tap-mambu/
├── tap_mambu/
│   ├── __init__.py
│   ├── tap.py          # Main tap class
│   ├── client.py       # API client
│   └── streams.py      # Stream definitions
├── tests/
│   ├── __init__.py
│   └── test_core.py
├── config.json         # Example configuration
├── pyproject.toml      # Dependencies and metadata
└── README.md          # User documentation
```

## Additional Resources

- Project README: `README.md` (venv, `pip install -e .`, `config.json`, CLI examples)
- Hotglue Singer SDK: https://github.com/hotgluexyz/HotglueSingerSDK
- Hotglue docs: https://docs.hotglue.com
- Singer specification: https://github.com/singer-io/getting-started/blob/master/docs/SPEC.md

## Making Changes

When implementing changes:

1. Understand the existing code structure
2. Follow Singer and SDK patterns
3. Test thoroughly with real API credentials
4. Update documentation and docstrings
5. Ensure backward compatibility when possible
6. Run linting and type checking

## Questions?

If you're uncertain about an implementation:

- Check SDK documentation for similar examples
- Review other Singer taps for patterns
- Test incrementally with small changes
- Validate against the Singer specification

## Bumping the Singer SDK Version

When upgrading the `hotglue-singer-sdk` dependency in `pyproject.toml`, follow these steps to avoid breaking changes:

1. **Check the deprecation guide** before upgrading:
   https://github.com/hotgluexyz/HotglueSingerSDK (check release notes for your version)

   The deprecation page lists APIs scheduled for removal in each release, along with migration instructions. Review the entries for every version between your current version and the target version.

2. **Update the dependency** in `pyproject.toml`:

   ```toml
   [project]
   dependencies = [
       "hotglue-singer-sdk~=X.Y",  # Bump to the new version
   ]
   ```

3. **Reinstall in your virtualenv** and run the full test suite:

   ```bash
   pip install -e .
   pip install pytest
   pytest
   ```

4. **Address deprecation warnings**: Run with warnings enabled to catch anything that will become an error in a future release:

   ```bash
   pytest -W error::DeprecationWarning
   ```

5. **Check the changelog** for any behavioral changes that affect your tap, even if not surfaced by warnings (e.g. pagination, authentication, state handling).

## Reporting SDK Issues

If you encounter a bug or missing feature in the **Hotglue Singer SDK (`hotglue_singer_sdk`)** itself (not in this tap), report it to the [HotglueSingerSDK](https://github.com/hotgluexyz/HotglueSingerSDK) maintainers using their issue tracker.

Before filing, search existing issues to avoid duplicates. Include the SDK version (`tap-mambu --version` with your venv activated), Python version, and a minimal reproduction case when reporting bugs.
