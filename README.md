# tap-mambu

A [Singer](https://www.singer.io/) tap that extracts data from **Mambu**. It is built with [hotglue-singer-sdk](https://github.com/hotgluexyz/HotglueSingerSDK) and speaks the standard Singer message protocol on stdout, so you can pair it with any compatible target.

## Features

- **REST**-style HTTP streams (see `client.py` / `streams.py`).
- **API key** authentication.

- Configurable **`api_url`**, **`start_date`**, and optional **`page_size`** (see [Configuration](#configuration)).
- Mambu **v2 REST** headers: `Accept: application/vnd.mambu.v2+json` and `apiKey` authentication (see `client.py`).

### Streams

| Stream | Endpoint / notes | Primary key | Replication key |
| ------ | ---------------- | ----------- | ----------------- |
| `journal_entries` | `GET` `/gljournalentries` with `from` / `to` (UTC **calendar** window: config `start_date` through today), `paginationDetails=ON`, and `limit` / `offset` pagination using `Items-Limit`, `Items-Offset`, `Items-Total` response headers | `encodedKey` | — (full window each run) |
| `transactions` | **Child of `journal_entries`.** For each parent row with a `transactionId`, calls `GET /loans/transactions/{id}` when `productType` is `LOAN`, or `GET /deposits/transactions/{id}` when `productType` is `SAVINGS`, with `detailsLevel=FULL`. Rows without a `transactionId` skip the child request. Any other `productType` with a transaction id raises an error. Within one sync, each distinct ``(loans|deposits, transaction id)`` is fetched at most once; extra journal lines for the same id emit **no** extra `RECORD` (only a set of keys is tracked, not response bodies). ``journal_entry_encoded_key`` is the first parent line that triggered the fetch. | `encodedKey` | — |

The tap wires `transactions` as a child stream in code; discovery lists both streams, and loaders should follow parent-child ordering from the catalog.

## Requirements

- Python **3.10+** (see `requires-python` in `pyproject.toml`).

## Installation

1. **Clone** this repository and `cd` into the project directory.
2. **Create `config.json`** in the project root with your credentials and settings (see [Configuration](#configuration) for the fields and an example).
3. **Create a virtual environment** and activate it:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows, use `.venv\Scripts\activate` instead of `source .venv/bin/activate`.

4. **Install the package** in editable mode:

```bash
pip install -e .
```

5. **Run the tap** (with the venv still activated):

```bash
tap-mambu --help
```

## Configuration

| Setting | Type | Required | Default | Description |
| ------- | ---- | -------- | ------- | ----------- |
| `start_date` | string (datetime) | no | `2000-01-01T00:00:00Z` | Start of the `from=` query date (YYYY-MM-DD) for GL journal entries. |
| `api_url` | string | no | `https://mbuhotglue.sandbox.mambu.com/api` | Base URL for the API (must include the `/api` prefix). |
| `access_key` | string | yes | — | Mambu API key (sent as the `apiKey` request header). |
| `page_size` | integer | no | `50` | `limit` for `/gljournalentries` offset pagination. |

Run `tap-mambu --about` (or `tap-mambu --about --format=markdown`) for the authoritative schema for your installed version.

### Example `config.json`

```json
{
  "start_date": "2000-01-01T00:00:00Z",
  "api_url": "https://mbuhotglue.sandbox.mambu.com/api",
  "access_key": "YOUR_ACCESS_KEY",
  "page_size": 50
}
```

Do not commit real credentials. Prefer environment variables or a secrets manager in production.

### Environment-based config

You can load settings from the process environment using `--config=ENV` (the SDK merges env into config). Env names follow the tap’s setting keys (see `tap-mambu --about`).

## Usage

With your virtual environment **activated** and `config.json` in place:

Discover stream catalog:

```bash
tap-mambu --config config.json --discover > catalog.json
```

Run a sync (with optional state):

```bash
tap-mambu --config config.json --catalog catalog.json --state state.json
```

Pipe to any Singer target:

```bash
tap-mambu --config config.json --catalog catalog.json | target-jsonl
```

Inspect built-in settings and stream metadata:

```bash
tap-mambu --about
```

## API / documentation

TODO: Add your vendor’s base URLs, auth docs, and links (compare to the “API hosts” section in a finished tap README).


## License
MIT — see `LICENSE` and `pyproject.toml`.
