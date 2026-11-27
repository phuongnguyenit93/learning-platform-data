# Designing Idempotent Data Ingestion and Reconciliation in PostgreSQL

## 1. Why Must a Data Ingestion Pipeline Be Rerunnable?

A system receives orders from partners via CSV files or a message queue. Every night, the pipeline fetches data, validates it, updates PostgreSQL tables, and records a watermark to know where to start next time.

A single run can encounter various failures:

- The file finishes downloading, but the worker crashes before updating the batch status.
- The database commits the data, but the application loses the connection before receiving the response.
- The message broker redelivers the same message after the consumer fails to acknowledge it in time.
- A batch contains 100,000 rows, and the process stops after 99,000 rows have been processed.
- The same record arrives twice, or arrives out of order.
- Two workers claim the same batch because a lease expired.
- A source file changes its contents while keeping the same filename.
- The target data is updated, but the checkpoint is not recorded.
- A snapshot is missing pages, yet the pipeline assumes it has ingested everything.
- Row counts match, but the values in some columns are wrong.

If you rerun such a pipeline using a simple `INSERT`, it can create duplicates, overwrite newer data with older data, or delete records by mistake.

A solid pipeline must provide two capabilities:

1. **Idempotent ingestion:** receiving the same batch or message multiple times still produces the exact same target data state.
2. **Reconciliation:** comparing the source, received data, applied data, and target data to detect missing, extra, or mismatched records.

```text
Source file / CDC / API / Message queue
                  |
                  v
          Register batch identity
                  |
                  v
        Immutable raw landing area
                  |
                  v
       Parse, normalize, validate
                  |
                  v
         Typed staging tables
                  |
                  v
       Deduplicate + order versions
                  |
                  v
       Transactional UPSERT / tombstone
                  |
                  v
       Commit data + checkpoint
                  |
                  v
         Reconciliation checks
                  |
                  v
       Mark batch reconciled / publish

        Failure at any stage
                  |
                  v
          Resume / replay safely
```

**Core principle:** design for at-least-once delivery, while ensuring data application is safely repeatable through stable keys, unique constraints, version checks, and transaction boundaries. Do not rely on the assumption that "every message arrives exactly once."

## 2. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between idempotency, retry safety, deduplication, and reconciliation.
2. Explain why "exactly once" across multiple systems is difficult to guarantee with a single PostgreSQL transaction alone.
3. Design stable batch keys and record keys across multiple runs.
4. Distinguish between `batch_id`, `source_batch_key`, `source_record_id`, version, and checkpoint.
5. Organize raw landing, staging, target, and quarantine tables.
6. Use unique constraints and `INSERT ... ON CONFLICT` as the last line of defense.
7. Handle duplicates with identical payloads versus duplicates with different payloads.
8. Ignore stale events and update based on source version.
9. Use tombstones to handle delete events and prevent old data from resurrecting.
10. Separate full snapshot reconciliation from incremental/CDC ingestion.
11. Design atomic or transactionally chunked pipelines.
12. Record checkpoints in the same transaction as the data they represent.
13. Use `COPY FROM STDIN` to load large datasets into staging.
14. Validate data before casting and merging into business tables.
15. Manage worker concurrency using row locks, leases, and fencing.
16. Use `FOR UPDATE SKIP LOCKED` for batch queues.
17. Reconcile counts, keys, versions, aggregates, and checksums.
18. Detect missing rows, extra rows, and same-key/different-value conflicts.
19. Handle late-arriving events, out-of-order events, and schema evolution.
20. Design exports with consistent snapshots and rerunnable file publishing.
21. Distinguish internal database transactions from external side effects in message brokers, files, and APIs.
22. Use outbox/idempotency keys for side effects that interact with external systems.
23. Test crashes, replays, concurrent workers, rollbacks, and ambiguous commit outcomes.
24. Build runbooks, metrics, and auditable remediation procedures.

## 3. Concepts to Distinguish

### 3.1. Idempotent operation

An operation `f` is called idempotent if applying the same request multiple times to the same initial state always yields the same final state:

```text
f(f(S, x), x) = f(S, x)
```

For example, updating an order status from an event with a fixed ID and checked version can be idempotent. Adding money to a balance every time a message arrives is not idempotent unless already-applied messages are tracked.

### 3.2. Retry-safe

A retry-safe operation can be rerun after a failure without causing unintended side effects. Idempotency is usually the foundation for retry safety, but you also need to consider external systems, commit timing, and outcome visibility.

### 3.3. Deduplication

Deduplication identifies records or events that represent the same logical event or entity. It requires a reliable **identity key**. Two rows with identical contents are not necessarily the same event; conversely, the same event ID with different payloads is a conflict that must be investigated.

### 3.4. Reconciliation

Reconciliation compares independent observations to answer:

- Were all expected records received?
- Were any records rejected or duplicated?
- Does the target data match the source in keys, versions, and values?
- Are there extra records within a scope that ought to match?
- Does the checkpoint accurately reflect the committed data?

Reconciliation is not just `COUNT(*)`; two datasets can have the exact same row count and still differ completely.

### 3.5. At-least-once and exactly-once

- **At-most-once:** messages may be dropped, but will not be delivered multiple times by that mechanism.
- **At-least-once:** messages may be redelivered, so the consumer must tolerate duplicates.
- **Exactly-once effect:** the final business state has the effect of having been applied once, even though the transport may redeliver.

In practice, teams usually build **at-least-once delivery + idempotent sink + transactional checkpoints**. "Exactly once" across PostgreSQL, a broker, a file system, and external APIs requires a specific coordination protocol; no single `COMMIT` spans all systems.

## 4. Define Identity Before Writing SQL

A pipeline needs at least two levels of identity.

| Identity | Scope | Example | Purpose |
| --- | --- | --- | --- |
| `source_system` | Source system | `partner_a` | Distinguish namespaces |
| `source_batch_key` | One source batch | `daily-2026-11-14-001` | Recognize redelivered batches |
| `batch_id` | One batch registration in the DB | UUID | Internal key and staging linkage |
| `source_record_id` | One logical record/event | `order-9381` | Deduplicate records |
| `source_version` | Record version | `17` | Prevent overwriting newer data with older data |
| `source_event_id` | One specific event | UUID from broker | Deduplicate delivery |
| `source_watermark` | Position read from source | LSN/offset/cursor | Resume incremental extraction |

### 4.1. Do not use file row numbers as business keys

`row_number = 42` is only a position within a file. When the source reorders rows, the same order can appear on a different line.

Row numbers are useful for tracing import errors and ensuring that replaying the same file does not insert duplicate raw rows, but they do not replace `source_record_id`.

### 4.2. Keys must be stable across runs

A key should be derived from a business identifier provided by the source or from a managed mapping. Never generate a new random key on each retry.

### 4.3. Key scope must be explicit

If `order_id` is only unique within a tenant, the target key must include the tenant:

```text
(tenant_id, source_system, source_record_id)
```

If the ID is globally unique across the source system, you can use `(source_system, source_record_id)`. Choose accurately according to the source data contract.

### 4.4. Batch keys and record keys solve two different problems

A batch key identifies whether **an entire data package** was previously delivered. A record key identifies **each entity or event** across different batches. You need both if the same record can appear in multiple incremental batches.

## 5. Data Architecture for the Lab

We will build a pipeline that ingests partner orders into PostgreSQL.

The layers are:

- `ingest.batches`: batch status, identity, and checksum.
- `ingest.raw_order_rows`: original payload, kept for audit and replay.
- `ingest.stage_orders`: parsed and validated data.
- `app.orders`: current business table.
- `ingest.rejected_rows`: invalid records and rejection reasons.
- `ingest.checkpoints`: durably stored source position.

### 5.1. Create schemas

Run in the lab database:

```sql
CREATE SCHEMA IF NOT EXISTS ingest;
CREATE SCHEMA IF NOT EXISTS app;
```

### 5.2. Batch registry table

```sql
CREATE TABLE ingest.batches (
    batch_id uuid PRIMARY KEY,
    source_system text NOT NULL,
    source_batch_key text NOT NULL,
    payload_sha256 text NOT NULL
        CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    status text NOT NULL
        CHECK (status IN (
            'received',
            'loading',
            'ready',
            'applying',
            'applied',
            'reconciled',
            'retryable',
            'failed'
        )),
    expected_rows bigint
        CHECK (expected_rows IS NULL OR expected_rows >= 0),
    received_rows bigint NOT NULL DEFAULT 0
        CHECK (received_rows >= 0),
    valid_rows bigint NOT NULL DEFAULT 0
        CHECK (valid_rows >= 0),
    rejected_rows bigint NOT NULL DEFAULT 0
        CHECK (rejected_rows >= 0),
    attempt_count integer NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    lease_owner text,
    lease_until timestamptz,
    source_watermark_start text,
    source_watermark_end text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    started_at timestamptz,
    completed_at timestamptz,
    reconciled_at timestamptz,
    last_error text,
    UNIQUE (source_system, source_batch_key)
);
```

The unique constraint `(source_system, source_batch_key)` protects batch registration when a request arrives again or two workers register concurrently.

`payload_sha256` is used to detect the case of **same batch key but different content**. When that happens, you must not silently treat it as a normal retry.

### 5.3. Raw landing table

```sql
CREATE TABLE ingest.raw_order_rows (
    batch_id uuid NOT NULL
        REFERENCES ingest.batches(batch_id),
    source_row_no bigint NOT NULL
        CHECK (source_row_no > 0),
    raw_payload jsonb NOT NULL,
    payload_sha256 text NOT NULL
        CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (batch_id, source_row_no)
);
```

The raw payload is preserved in terms of parsed JSON data. If you need to preserve the **byte-for-byte original file**, store the original file in object storage or content-addressed storage and keep the URI + checksum in the batch registry; `jsonb` does not preserve whitespace, key order, or original CSV formatting.

### 5.4. Typed staging table

```sql
CREATE TABLE ingest.stage_orders (
    batch_id uuid NOT NULL
        REFERENCES ingest.batches(batch_id),
    source_row_no bigint NOT NULL,
    tenant_id bigint,
    source_record_id text,
    source_version bigint,
    customer_code text,
    status text,
    amount numeric(12,2),
    source_updated_at timestamptz,
    payload_sha256 text,
    validation_error text,
    PRIMARY KEY (batch_id, source_row_no)
);
```

Staging lets you separate parsing and validation from writing to the business table. Failed rows are kept with their batch and row number for traceability.

### 5.5. Quarantine table

```sql
CREATE TABLE ingest.rejected_rows (
    batch_id uuid NOT NULL,
    source_row_no bigint NOT NULL,
    raw_payload jsonb NOT NULL,
    error_code text NOT NULL,
    error_detail text,
    rejected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (batch_id, source_row_no)
);
```

Never drop invalid rows silently. Quarantine preserves evidence, root cause, and the ability to fix and replay.

### 5.6. Target table

```sql
CREATE TABLE app.orders (
    tenant_id bigint NOT NULL,
    source_system text NOT NULL,
    source_record_id text NOT NULL,
    source_version bigint NOT NULL,
    payload_sha256 text NOT NULL,
    customer_code text NOT NULL,
    status text NOT NULL,
    amount numeric(12,2) NOT NULL,
    source_updated_at timestamptz,
    deleted_at timestamptz,
    last_batch_id uuid NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (
        tenant_id,
        source_system,
        source_record_id
    )
);
```

The target stores the source version and payload hash to distinguish newer events, stale events, and same-version conflicts. `deleted_at` acts as a soft tombstone in this example.

### 5.7. Checkpoint table for numeric-offset sources

§§§sql
CREATE TABLE ingest.checkpoints (
    source_system text NOT NULL,
    stream_name text NOT NULL,
    partition_id integer NOT NULL,
    last_committed_offset bigint NOT NULL DEFAULT -1,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (source_system, stream_name, partition_id)
);
§§§

This example fits sources with numeric offsets such as certain message partitions. For opaque API cursors or non-integer CDC tokens, store the exact type/token provided by the source and define comparator/checkpoint semantics per contract; do not force every watermark into a bigint.

## 6. Registering a Batch Idempotently

The application generates `batch_id` once for a new batch and keeps it across retries. `source_batch_key` is provided by the source or derived deterministically by the extractor.

### 6.1. First registration

```sql
INSERT INTO ingest.batches (
    batch_id,
    source_system,
    source_batch_key,
    payload_sha256,
    status,
    expected_rows,
    source_watermark_start,
    source_watermark_end
)
VALUES (
    '11111111-1111-4111-8111-111111111111',
    'partner_a',
    'daily-2026-11-14-001',
    repeat('a', 64),
    'received',
    1000,
    'offset:5000',
    'offset:5999'
)
ON CONFLICT (source_system, source_batch_key)
DO NOTHING
RETURNING batch_id;
```

The UUID and checksum above are illustrative values for the lab. In a real application, the checksum must be computed from a canonical representation of the batch.

### 6.2. Retrying with the same batch key

If `INSERT ... RETURNING` returns no row, the batch key already exists. Read the existing batch:

```sql
SELECT
    batch_id,
    payload_sha256,
    status,
    expected_rows,
    received_rows
FROM ingest.batches
WHERE source_system = 'partner_a'
  AND source_batch_key = 'daily-2026-11-14-001'
FOR UPDATE;
```

Compare `payload_sha256`:

- Same checksum: same batch content; continue/resume or return the previous result if already completed.
- Different checksum: same identity but different content; mark as a conflict and investigate the source.
- Do not create a new batch merely because a request was retried.

### 6.3. Concurrency

The unique constraint is the final safeguard when two requests register the same key concurrently. One request waits for the other to commit and then encounters the conflict. Afterward, it reads the existing record and compares the checksum.

### 6.4. Why not use only the filename?

A filename such as `orders.csv` is often reused every day. The batch key should include source identity and an appropriate sequence, snapshot, date, or version, not just a generic filename.

## 7. Computing Stable Checksums

Checksums help recognize identical content or detect mutations. However, both systems must hash **the exact same representation**.

### 7.1. What needs to be canonicalized

- Encoding and Unicode normalization policy.
- Record order, and whether batch order is significant.
- Field names and ordering.
- `NULL` distinct from empty string.
- Timestamp timezone and precision.
- Decimal scale and rounding.
- JSON number versus string distinction.
- Line endings and CSV quoting when hashing file bytes.
- Metadata fields outside the business payload.

### 7.2. Hashing file bytes and hashing logical records are two different things

Hashing the entire file verifies byte-for-byte file identity. Hashing logical records compares data after parsing and normalization. Always document which type of checksum is being used.

### 7.3. Do not hash ambiguous string concatenations

For example, concatenating `('ab','c')` and `('a','bc')` both produce `abc` without delimiter or length framing. Use canonical serialization with explicit schema, encoding, and field delimiters or length prefixes.

### 7.4. SHA-256

The application can compute SHA-256 before uploading. If PostgreSQL `pgcrypto` is used, it can also be computed in the DB:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

SELECT encode(
    digest(convert_to('canonical payload', 'UTF8'), 'sha256'),
    'hex'
);
```

There is no need to install the extension if the application or object store already produces a trustworthy checksum. Here, SHA-256 checks content identity and integrity; it does not replace source authentication or cryptographic signatures.

### 7.5. Hashes do not replace identity

Two distinct orders can have identical payloads. Having the same hash does not mean they are the same order. Identity must rely on source keys.

## 8. Loading Large Files into Staging with COPY

For large volumes, `COPY FROM STDIN` is usually much faster than thousands of individual `INSERT` statements.

### 8.1. Temporary landing table

```sql
CREATE TEMP TABLE incoming_order_rows (
    source_row_no bigint,
    tenant_id bigint,
    source_record_id text,
    source_version bigint,
    customer_code text,
    status text,
    amount numeric(12,2),
    source_updated_at timestamptz,
    payload_sha256 text
) ON COMMIT DROP;
```

### 8.2. COPY from client

```sql
COPY incoming_order_rows (
    source_row_no,
    tenant_id,
    source_record_id,
    source_version,
    customer_code,
    status,
    amount,
    source_updated_at,
    payload_sha256
)
FROM STDIN
WITH (FORMAT csv, HEADER true);
```

In `psql`, `COPY ... FROM STDIN` reads the data stream sent by the client. In Java pgJDBC, you can use `CopyManager` from the `org.postgresql.copy` package to stream data. Do not confuse this with `COPY FROM '/path'`, which reads a file on the **server** filesystem and requires corresponding server permissions and paths.

### 8.3. Writing to staging with batch identity

After COPYing into the temp table:

```sql
INSERT INTO ingest.stage_orders (
    batch_id,
    source_row_no,
    tenant_id,
    source_record_id,
    source_version,
    customer_code,
    status,
    amount,
    source_updated_at,
    payload_sha256
)
SELECT
    '11111111-1111-4111-8111-111111111111'::uuid,
    source_row_no,
    tenant_id,
    source_record_id,
    source_version,
    customer_code,
    status,
    amount,
    source_updated_at,
    payload_sha256
FROM pg_temp.incoming_order_rows
ON CONFLICT (batch_id, source_row_no)
DO NOTHING;
```

`ON CONFLICT DO NOTHING` ensures replaying the same batch and row number does not create duplicate staging rows. However, before ignoring a conflict, you must verify that the existing row has the same payload hash. If the row number is the same but the payload differs, that is batch mutation or corruption and must fail or be quarantined.

### 8.4. Do not COPY directly into target when validation and reconciliation are needed

COPYing directly into target makes it hard to:

- Quarantine individual invalid rows.
- Check duplicate keys.
- Compare source versions.
- Reconcile expected rows.
- Distinguish new, updated, unchanged, and stale rows.
- Replay partially.

Staging establishes a clear boundary between untrusted incoming data and business tables.

## 9. Validate Before Casting and Merging

External data can be malformed, miss required fields, contain unexpected statuses, or have invalid amounts.

### 9.1. Validation layers

1. **Structural:** does the record have all required fields?
2. **Type:** is version an integer, amount a decimal, and timestamp parseable?
3. **Domain:** is status within the allowed enum, and is amount non-negative?
4. **Referential:** do the tenant, customer, and product exist within the right scope?
5. **Business:** is the status transition valid?
6. **Identity:** is the record ID stable and the version valid?
7. **Consistency:** do rows with the same key and version have conflicting payloads?

### 9.2. Do not cast raw text blindly

If `amount_text` contains a locale-formatted `12,34` or `not-a-number`, a direct cast can fail the entire batch. Parse in the application/validation layer or use a controlled safe parsing routine that records errors per row.

### 9.3. Example of quarantining flagged rows

```sql
INSERT INTO ingest.rejected_rows (
    batch_id,
    source_row_no,
    raw_payload,
    error_code,
    error_detail
)
SELECT
    r.batch_id,
    r.source_row_no,
    r.raw_payload,
    'INVALID_ORDER',
    s.validation_error
FROM ingest.stage_orders AS s
JOIN ingest.raw_order_rows AS r
  ON r.batch_id = s.batch_id
 AND r.source_row_no = s.source_row_no
WHERE s.batch_id =
    '11111111-1111-4111-8111-111111111111'
  AND s.validation_error IS NOT NULL
ON CONFLICT (batch_id, source_row_no)
DO UPDATE SET
    error_code = EXCLUDED.error_code,
    error_detail = EXCLUDED.error_detail;
```

Quarantine must preserve the same batch/row identity so a replay does not generate duplicate error rows.

### 9.4. Reject all or partial acceptance?

Define the policy upfront:

- **Atomic batch:** one invalid row prevents the entire batch from being applied.
- **Partial acceptance:** valid rows are applied and invalid rows are quarantined; the batch only completes when reconciliation explicitly records accepted and rejected counts.

Do not let the system implicitly choose semantics by having code accidentally swallow exceptions.

## 10. Deduplicating Within a Batch

A file can contain multiple rows for the same `source_record_id`.

### 10.1. Same key, same version, same payload

This is likely duplicate delivery. Keep one representative row and count the duplicates.

### 10.2. Same key, same version, different payload

This is a conflict. Do not arbitrarily pick "the last row" by file order unless the source contract explicitly designates that order as authoritative.

Find conflicts:

```sql
SELECT
    tenant_id,
    source_record_id,
    source_version,
    COUNT(*) AS rows_seen,
    COUNT(DISTINCT payload_sha256) AS distinct_payloads
FROM ingest.stage_orders
WHERE batch_id =
    '11111111-1111-4111-8111-111111111111'
  AND validation_error IS NULL
GROUP BY tenant_id, source_record_id, source_version
HAVING COUNT(DISTINCT payload_sha256) > 1;
```

### 10.3. Selecting the latest version

If source versions increase monotonically per record:

```sql
SELECT *
FROM (
    SELECT
        s.*,
        row_number() OVER (
            PARTITION BY tenant_id, source_record_id
            ORDER BY source_version DESC, source_row_no DESC
        ) AS rn
    FROM ingest.stage_orders AS s
    WHERE batch_id =
        '11111111-1111-4111-8111-111111111111'
      AND validation_error IS NULL
) AS ranked
WHERE rn = 1;
```

`source_row_no DESC` is only a technical tie-breaker after verifying that rows with the same key and version have identical payloads. Do not use it to resolve genuine data conflicts.

### 10.4. Version is not consumer receive timestamp

An older event can arrive late after a newer event. `received_at` on the target system cannot decide which record is newer. Use a source sequence/version or an explicitly defined ordering contract.

## 11. Conditional UPSERT by Source Version

The target unique constraint guarantees only one current row per business key:

```text
(tenant_id, source_system, source_record_id)
```

### 11.1. Check for same version with different payload

Before merging, detect source conflicts against the target:

```sql
SELECT
    s.tenant_id,
    s.source_record_id,
    s.source_version,
    t.payload_sha256 AS target_hash,
    s.payload_sha256 AS incoming_hash
FROM ingest.stage_orders AS s
JOIN app.orders AS t
  ON t.tenant_id = s.tenant_id
 AND t.source_system = 'partner_a'
 AND t.source_record_id = s.source_record_id
WHERE s.batch_id =
    '11111111-1111-4111-8111-111111111111'
  AND s.validation_error IS NULL
  AND s.source_version = t.source_version
  AND s.payload_sha256 <> t.payload_sha256;
```

If any rows return, handle them according to the conflict policy; do not silently update or treat them as duplicates.

### 11.2. Merge the latest version of each key

After validation and filtering out conflicts:

```sql
WITH ranked AS (
    SELECT
        s.*,
        row_number() OVER (
            PARTITION BY s.tenant_id, s.source_record_id
            ORDER BY s.source_version DESC, s.source_row_no DESC
        ) AS rn
    FROM ingest.stage_orders AS s
    WHERE s.batch_id =
        '11111111-1111-4111-8111-111111111111'
      AND s.validation_error IS NULL
),
latest AS (
    SELECT *
    FROM ranked
    WHERE rn = 1
)
INSERT INTO app.orders AS current_order (
    tenant_id,
    source_system,
    source_record_id,
    source_version,
    payload_sha256,
    customer_code,
    status,
    amount,
    source_updated_at,
    last_batch_id
)
SELECT
    l.tenant_id,
    'partner_a',
    l.source_record_id,
    l.source_version,
    l.payload_sha256,
    l.customer_code,
    l.status,
    l.amount,
    l.source_updated_at,
    l.batch_id
FROM latest AS l
ON CONFLICT (
    tenant_id,
    source_system,
    source_record_id
)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    payload_sha256 = EXCLUDED.payload_sha256,
    customer_code = EXCLUDED.customer_code,
    status = EXCLUDED.status,
    amount = EXCLUDED.amount,
    source_updated_at = EXCLUDED.source_updated_at,
    deleted_at = NULL,
    last_batch_id = EXCLUDED.last_batch_id,
    updated_at = clock_timestamp()
WHERE EXCLUDED.source_version > current_order.source_version;
```

### 11.3. Effect of the version condition

- Key does not exist in target: insert.
- Incoming version is higher: update.
- Incoming version is lower: ignore stale event.
- Incoming version is equal and payload matches: unchanged/no-op.
- Incoming version is equal and payload differs: must be detected as a conflict before merge.

### 11.4. Do not rely on `xmax = 0` for business classification

Some examples inspect the system column `xmax` to guess INSERT versus UPDATE inside `ON CONFLICT`. This is not a stable application contract for accounting. If you need exact inserted/updated counts, design a change ledger or explicit classification/recording process.

### 11.5. Concurrent UPSERTs still require a unique constraint

Two workers can simultaneously observe that a key does not yet exist. The unique constraint and `ON CONFLICT` handle contention inside the database. A `SELECT` check followed by `INSERT` is not race-safe.

## 12. Delete Events: Use Tombstones to Prevent Old Data From Resurrecting

Suppose the source emits:

- Version 8: order is `PAID`.
- Version 9: order is deleted.
- Version 7: an older event arrives late afterward.

If the consumer physically DELETEs the row at version 9, the version 7 event can re-INSERT the order and cause the record to "resurrect."

### 12.1. Tombstone

Instead of deleting immediately, store:

- Business key.
- Delete version.
- `deleted_at`.
- Source event identity/hash.

The target schema already has `deleted_at`; the tombstone retains version 9 to block older events.

### 12.2. Apply deletes as a versioned upsert

You can use a separate event/tombstone table or an `INSERT ... ON CONFLICT DO UPDATE` with action `DELETE`, updating only if the incoming version is higher. Condensed example:

```sql
UPDATE app.orders
SET
    source_version = 9,
    deleted_at = clock_timestamp(),
    last_batch_id =
        '11111111-1111-4111-8111-111111111111',
    updated_at = clock_timestamp()
WHERE tenant_id = 10
  AND source_system = 'partner_a'
  AND source_record_id = 'order-9381'
  AND source_version < 9;
```

In production, a delete event arriving before an insert event must also be stored as a tombstone key even when the target row does not exist yet; otherwise, an older insert event could recreate the row. A dedicated tombstone table or a target record in a deleted state handles that case.

### 12.3. Do not purge tombstones too early

Retain tombstones for at least the maximum window during which the source can replay or deliver late events. If the source has a 30-day retention/replay window, purging tombstones after 1 day can let old events reappear.

### 12.4. Soft deletes and API reads

Business queries must filter `deleted_at IS NULL` per policy. However, reconciliation and auditing need visibility into tombstones to distinguish a deleted key from one that never existed.

## 13. Recording Batch Progress and Checkpoints

A checkpoint is the position in the source that the pipeline asserts it has durably processed.

Examples:

- Kafka partition + offset.
- CDC log sequence number (LSN).
- API page cursor.
- Source updated timestamp + unique tie-breaker.
- File batch key + row number.

### 13.1. Never advance a checkpoint before data is durable

Dangerous sequence:

1. Record checkpoint up to offset 9000.
2. Crash before writing the corresponding target rows.
3. Restart from 9001.
4. Events 8001–9000 are lost.

### 13.2. Transactional checkpoint with data

If target data and checkpoints live in the same PostgreSQL database, write them in **the same transaction**:

```sql
BEGIN;

-- INSERT/UPSERT target rows for the corresponding chunk.

UPDATE ingest.checkpoints
SET last_committed_offset = 9000,
    updated_at = clock_timestamp()
WHERE source_system = 'partner_a'
  AND stream_name = 'orders'
  AND partition_id = 0;

COMMIT;
```

If the transaction rolls back, both the data and the checkpoint roll back. If it commits, both become durable under database transaction semantics. The `ingest.checkpoints` table must be created to match the application's source/stream/partition contract.

### 13.3. Raw landing and checkpointing can have two stages

A sound design can:

1. Durably write raw events to PostgreSQL.
2. Commit raw landing.
3. Acknowledge the broker / advance the source offset.
4. Apply raw events into target in replayable batches.

In this case, the source checkpoint means **raw events are durably stored**, not that they are merged into target. Keep the two watermarks separate so operations do not misinterpret them.

### 13.4. Broker offsets outside the DB

If committing the broker offset cannot share a PostgreSQL transaction, you cannot assume a single atomic transaction covers both. Choose at-least-once delivery: persist the event with a unique event ID, commit the DB, then ack; if a crash occurs between those steps, the broker redelivers and the unique constraint/dedup makes redelivery safe.

### 13.5. Timestamp watermarks need a tie-breaker

`updated_at > last_timestamp` can miss records sharing the same timestamp or late-committed updates. Use a composite cursor such as `(updated_at, source_record_id)` with a stable order, or a CDC sequence with explicit ordering.

### 13.6. A watermark is not server receive time

For CDC, store the source LSN/offset. For APIs, store the cursor provided by the source. Never substitute `clock_timestamp()` on the consumer and treat it as the source position.

## 14. Atomic Batch or Chunked?

The two common strategies carry different trade-offs.

| Strategy | Execution model | Pros | Cons |
| --- | --- | --- | --- |
| Atomic batch | Entire batch in one transaction | Easy rollback, target never half-applied | Large transactions, WAL, and locks |
| Chunked | Each chunk commits separately with its own checkpoint | Fast resume, short transactions | Target exposes partial state between chunks |
| Raw-first + apply later | Raw persisted first, merged in chunks later | Decouples transport from business processing | Requires clear state machine and reconciliation |
| Snapshot generation | Load new snapshot version then switch | Easy to maintain snapshot consistency | Requires extra storage and publish mechanism |

### 14.1. Atomic batch

Fits small/medium batches requiring all-or-nothing semantics. Place batch state, merge, and checkpoint in the same transaction.

### 14.2. Chunked batch

Each chunk needs a stable identity, such as `(batch_id, chunk_no)`, and its own checkpoint. Retrying a chunk must neither create duplicates nor skip data.

```sql
CREATE TABLE ingest.batch_chunks (
    batch_id uuid NOT NULL,
    chunk_no integer NOT NULL,
    first_row_no bigint NOT NULL,
    last_row_no bigint NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'applied')),
    applied_at timestamptz,
    PRIMARY KEY (batch_id, chunk_no),
    CHECK (first_row_no <= last_row_no)
);
```

Chunk data and the `applied` status should commit in the same transaction.

### 14.3. Do not mark a batch complete before the last chunk

The batch status `applied` must only be set after all required chunks are applied and counts are verified. If a chunk fails or has quarantined rows, the overall status must reflect that.

### 14.4. Define visibility for downstream consumers

If other consumers read the target while a chunked batch is running, they may observe a partial snapshot. You can use a batch generation/visibility flag, stage the target and switch, or ensure downstream only reads a `published` generation.

## 15. Managing Multiple Workers Safely

When multiple workers process batches, you must prevent two workers from applying the same batch concurrently or a stale worker from writing after its lease has moved to another owner.

### 15.1. Claim a batch with SKIP LOCKED

```sql
WITH candidate AS (
    SELECT batch_id
    FROM ingest.batches
    WHERE status IN ('received', 'retryable')
      AND (
          lease_until IS NULL
          OR lease_until < clock_timestamp()
      )
    ORDER BY created_at, batch_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE ingest.batches AS b
SET
    status = 'loading',
    lease_owner = 'worker-17',
    lease_until = clock_timestamp() + interval '2 minutes',
    attempt_count = attempt_count + 1,
    started_at = COALESCE(started_at, clock_timestamp())
FROM candidate AS c
WHERE b.batch_id = c.batch_id
RETURNING b.*;
```

This example runs in a short transaction. Commit the claim first, and only then let the worker execute the processing work.

### 15.2. Why SKIP LOCKED?

If worker A locks batch row 1, worker B skips that row and picks up another batch instead of blocking. This fits queue workers, though it does not guarantee strict FIFO order in the presence of locks and retries.

### 15.3. A lease is not an absolute lock

Worker A might pause for a long time, its lease expires, worker B claims the batch, and then A wakes up and resumes. You need fencing tokens/ownership checks in the apply transaction, heartbeats, and/or transaction-level advisory locks.

### 15.4. Fencing token

Some systems increment `lease_generation` on every claim. A worker may only commit results if its generation still matches the active token. An old worker cannot write after a new worker claims a higher generation.

Conceptual example:

```sql
UPDATE ingest.batches
SET
    lease_generation = lease_generation + 1,
    lease_owner = 'worker-17',
    lease_until = clock_timestamp() + interval '2 minutes'
WHERE batch_id = $1
RETURNING lease_generation;
```

To use this statement, add `lease_generation bigint NOT NULL DEFAULT 0` to the batch schema. Inside the apply transaction, lock the batch row and verify the generation before writing to the target.

### 15.5. Advisory transaction lock

You can serialize by source/batch using `pg_advisory_xact_lock(...)` if lock key conventions are consistent. Advisory locks assist coordination, while unique constraints and idempotent writes must still protect the data.

### 15.6. Do not hold a transaction open while downloading files over the network

Downloading files, calling APIs, decompressing, and validating take time. Perform them beforehand or outside the apply transaction. Open the DB transaction only briefly to write the chunk, merge, and checkpoint.

## 16. Reconciliation: From Counts to Content

Reconciliation must have layered checks.

### 16.1. Count reconciliation

For a batch:

- `expected_rows`: rows declared by the source.
- `received_rows`: raw rows received.
- `valid_rows`: rows passing validation.
- `rejected_rows`: rows quarantined.
- `duplicate_rows`: duplicate deliveries/rows.
- `applied_new_rows`: newly inserted records.
- `applied_update_rows`: updated records.
- `unchanged_rows`: same version and payload.
- `stale_rows`: older events ignored.

Define **non-overlapping** buckets or clearly document which buckets are subsets. If `received = valid + rejected`, duplicates may be an attribute of valid rows rather than being added a second time.

### 16.2. Example of clear accounting

A batch has 1,000 source rows:

| Final classification (mutually exclusive) | Count |
| --- | ---: |
| New records applied | 700 |
| Existing records updated | 150 |
| Unchanged duplicates | 80 |
| Stale events ignored | 30 |
| Rejected | 40 |
| **Total received** | **1,000** |

If the source contract declares 1,000 rows, `received_rows` must match. In this example, `valid_rows` is 960 assuming stale/unchanged rows were valid; rejected is 40. Do not sum `700 + 150 + 80 + 30 + 40` and add duplicates again on top.

### 16.3. Reconcile raw rows against expected

```sql
SELECT
    b.batch_id,
    b.expected_rows,
    COUNT(r.source_row_no) AS actual_raw_rows,
    b.received_rows
FROM ingest.batches AS b
LEFT JOIN ingest.raw_order_rows AS r
  ON r.batch_id = b.batch_id
WHERE b.batch_id =
    '11111111-1111-4111-8111-111111111111'
GROUP BY b.batch_id, b.expected_rows, b.received_rows;
```

If a batch is chunked, check unique row numbers and row-number ranges/partition completeness against the source contract; matching counts alone do not prove no row was substituted.

### 16.4. Missing and extra keys via anti-join

If you have a normalized source snapshot table `ingest.source_snapshot_orders`, compare:

```sql
-- Present in source but missing in target.
SELECT s.tenant_id, s.source_record_id
FROM ingest.source_snapshot_orders AS s
LEFT JOIN app.orders AS t
  ON t.tenant_id = s.tenant_id
 AND t.source_system = s.source_system
 AND t.source_record_id = s.source_record_id
WHERE s.snapshot_id = $1
  AND t.source_record_id IS NULL;

-- Present in target within scope but no longer in source snapshot.
SELECT t.tenant_id, t.source_record_id
FROM app.orders AS t
LEFT JOIN ingest.source_snapshot_orders AS s
  ON s.tenant_id = t.tenant_id
 AND s.source_system = t.source_system
 AND s.source_record_id = t.source_record_id
 AND s.snapshot_id = $1
WHERE t.source_system = $2
  AND t.tenant_id = $3
  AND t.deleted_at IS NULL
  AND s.source_record_id IS NULL;
```

The second query is only meaningful if the source snapshot is **complete, finalized, and covers the exact same scope**. Never delete records based on a partial snapshot.

### 16.5. Comparing versions and payload hashes

```sql
SELECT
    s.tenant_id,
    s.source_record_id,
    s.source_version AS source_version,
    t.source_version AS target_version,
    s.payload_sha256 AS source_hash,
    t.payload_sha256 AS target_hash
FROM ingest.source_snapshot_orders AS s
JOIN app.orders AS t
  ON t.tenant_id = s.tenant_id
 AND t.source_system = s.source_system
 AND t.source_record_id = s.source_record_id
WHERE s.snapshot_id = $1
  AND (
      s.source_version <> t.source_version
      OR s.payload_sha256 <> t.payload_sha256
  );
```

Investigate each category: target stale, source stale, same-version conflict, normalization mismatch, or apply error.

## 17. Checksum Reconciliation for Large Datasets

Count and key checks are not enough to prove payloads match. Checksums can detect discrepancies across record sets.

### 17.1. Canonical row representation

For example, each record is formatted in a fixed field order:

```text
tenant_id | source_system | source_record_id |
source_version | status | amount | deleted_at
```

You need exact rules for representing NULL, numeric scale, timestamp timezone, and Unicode.

### 17.2. Partitioned checksum

With `pgcrypto`:

```sql
SELECT
    tenant_id,
    COUNT(*) AS row_count,
    encode(
        digest(
            convert_to(
                string_agg(
                    concat_ws(
                        E'\x1f',
                        source_record_id,
                        source_version::text,
                        payload_sha256
                    ),
                    E'\n'
                    ORDER BY source_record_id
                ),
                'UTF8'
            ),
            'sha256'
        ),
        'hex'
    ) AS partition_sha256
FROM app.orders
WHERE source_system = 'partner_a'
  AND deleted_at IS NULL
GROUP BY tenant_id
ORDER BY tenant_id;
```

### 17.3. Limits of the string_agg example

A very large partition can build a huge temporary string in memory. In production, split by tenant, key range, or date partitions, or use a Merkle tree / hierarchical checksums with canonical leaf hashing.

### 17.4. Do not sum hashes arithmetically as a strong checksum

`SUM(hash_as_number)` or simple XOR can suffer collisions and fail to preserve ordering/identity as expected. Use a well-defined checksum design that both sides can reproduce deterministically.

### 17.5. A hash does not prove the source is trustworthy

Checksums only verify that content matches the computed digest. If the source can be spoofed, you need authenticated transport, signatures, or trusted source controls.

## 18. Business Aggregate Reconciliation

Beyond row counts and hashes, compare meaningful totals:

```sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count,
    SUM(amount) AS amount_total,
    MIN(source_updated_at) AS first_seen,
    MAX(source_updated_at) AS last_seen
FROM app.orders
WHERE source_system = 'partner_a'
  AND deleted_at IS NULL
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

If the source provides summaries by tenant/status, compare against the corresponding totals.

### 18.1. Aggregate matches do not prove record-level matches

One missing order of 100 and one extra order of 100 leave the total amount unchanged. Therefore, aggregates are **one layer** of reconciliation, not a substitute for key-level comparison.

### 18.2. Currency and precision

Do not sum amounts across multiple currencies without an explicit currency conversion contract. Use `numeric`, not floating point, for accounting values; specify scale and rounding.

### 18.3. Time window

Compare over the same snapshot or time window. If the source keeps changing while the target is ingesting, aggregates may legitimately differ because the two sides reflect different points in time.

## 19. Full Snapshots and Incremental/CDC Feeds Are Different

### 19.1. Full snapshot

The source declares: "This is the complete set of orders belonging to tenant 10 at snapshot S."

You may compare missing/extra keys and mark deleted records only if:

- The snapshot has a completion marker.
- All pages/parts have been received.
- Counts and checksums are valid.
- The tenant and source scope match.
- No other unserialized batch is concurrently updating the same scope.

### 19.2. Incremental feed

The source only sends new or changed records since a watermark. A record absent from an incremental batch **does not mean it was deleted**.

### 19.3. CDC

CDC emits change events in log sequence order. You must preserve source offset/LSN, transaction ordering, and delete events. Never infer a delete from a key's absence in a chunk.

### 19.4. Full snapshot generation

One way to manage visibility:

1. Create `snapshot_id`.
2. Load all rows into the new generation.
3. Reconcile expected count and checksum.
4. Only when complete, mark the generation `published`.
5. Downstream reads the current generation.
6. Clean up old generations according to retention policy.

This prevents downstream consumers from reading a partial snapshot while an import is running.

### 19.5. Never delete based on a snapshot missing a page

If page 4 of 10 fails to download and the pipeline still marks absent records as deleted, it can wipe out large volumes of valid data. Full snapshots require a completion manifest and reconciliation before any delete phase.

## 20. Late-Arriving and Out-of-Order Events

A version 12 event can arrive before version 11. When version 11 arrives later, it must not overwrite version 12.

### 20.1. Version gate

The condition:

```sql
WHERE EXCLUDED.source_version > current_order.source_version
```

keeps the target at the higher version.

### 20.2. Versions must have well-defined semantics

If source versions reset daily or per partition, they cannot be compared globally without adding epoch or partition identity. Clarify:

- Does version increase per record?
- Does offset increase per partition?
- Do timestamps have a tie-breaker?
- Can the source replay historical corrections?
- Do deletes carry versions like updates?

### 20.3. Same version, different payload

Never pick a winner randomly. Record the conflict, quarantine it, and require the source contract/owner to resolve it.

### 20.4. Late corrections

A valid correction may carry an old business effective date with a newer event version. Do not use the business date instead of event ordering. Store both `source_version` and `source_updated_at`/effective time if needed.

## 21. Partial Error Handling and Poison Records

One invalid row does not necessarily invalidate all other rows, but the policy must be explicit.

### 21.1. Atomic batch

If a batch is an indivisible business unit, any validation or merge error rolls back the entire batch. After the source fixes the file, issue a new batch key or new version per contract; do not reuse the same key with different content unrecorded.

### 21.2. Partial acceptance

If accepting partial rows:

- Write every row to raw.
- Record validation status explicitly.
- Route invalid rows to quarantine.
- Merge only valid rows.
- Ensure counts add up accurately.
- Do not mark the batch `reconciled` until rejected rows are accepted per policy or remediated.

### 21.3. Poison message

A message that repeatedly crashes the consumer can block a partition or queue. After a bounded number of retries, move it to a dead-letter or quarantine store, record the reason, and preserve the original payload. Never silently drop the message.

### 21.4. Do not use `WHEN OTHERS THEN NULL`

Catching every exception and continuing can cause a batch to report success even though some rows were never applied. If catching errors for partial processing, you must log the error, classify it, and ensure clear transaction/savepoint semantics.

### 21.5. Per-row savepoints have overhead

Savepoints allow rolling back part of a transaction, but they add overhead and do not replace validation. For large files, set-based validation followed by merging valid rows is usually much faster than looping with a savepoint per row.

## 22. Chunk Checkpoints and Resumability

For very large batches, divide work into chunks with deterministic ordering.

### 22.1. Chunk identity

For example:

`(batch_id, chunk_no)` or `(source_partition, first_offset, last_offset)`.

The same chunk must cover the exact same source range on every retry.

### 22.2. Chunk ledger

```sql
CREATE TABLE ingest.batch_chunks (
    batch_id uuid NOT NULL
        REFERENCES ingest.batches(batch_id),
    chunk_no integer NOT NULL,
    first_row_no bigint NOT NULL,
    last_row_no bigint NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'applying', 'applied', 'failed')),
    rows_received bigint NOT NULL DEFAULT 0,
    rows_applied bigint NOT NULL DEFAULT 0,
    payload_sha256 text,
    applied_at timestamptz,
    PRIMARY KEY (batch_id, chunk_no),
    CHECK (first_row_no <= last_row_no)
);
```

### 22.3. Atomic chunk commit

Inside a single transaction:

1. Lock the chunk row.
2. Verify checksum and status.
3. Merge target rows idempotently.
4. Update the chunk to `applied`.
5. Update the corresponding checkpoint.
6. Commit.

If the process crashes before commit, both the merge and progress update roll back. If it crashes after commit but before the worker receives the response, the rerun sees the chunk as `applied` and does not misapply it again.

### 22.4. Do not rely only on contiguous row numbers

If source pages have gaps or opaque cursors, use the source-provided cursor or offset. `last_row_no` only fits ordered files/batches with stable row numbering.

### 22.5. Batch completion

A batch transitions to `applied` once all required chunks are applied or classified as rejected under the partial-acceptance policy. Then run reconciliation and transition to `reconciled` only when checks pass.

## 23. Managing Multiple Workers Safely

When multiple workers process batches, you must prevent two workers from applying the same batch concurrently or a stale worker from writing after its lease has moved to another owner.

### 23.1. Claim a batch with SKIP LOCKED

```sql
WITH candidate AS (
    SELECT batch_id
    FROM ingest.batches
    WHERE status IN ('received', 'retryable')
      AND (
          lease_until IS NULL
          OR lease_until < clock_timestamp()
      )
    ORDER BY created_at, batch_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE ingest.batches AS b
SET
    status = 'loading',
    lease_owner = 'worker-17',
    lease_until = clock_timestamp() + interval '2 minutes',
    attempt_count = attempt_count + 1,
    started_at = COALESCE(started_at, clock_timestamp())
FROM candidate AS c
WHERE b.batch_id = c.batch_id
RETURNING b.*;
```

This example runs in a short transaction. Commit the claim first, and only then let the worker execute the processing work.

### 23.2. Why SKIP LOCKED?

If worker A locks batch row 1, worker B skips that row and picks up another batch instead of blocking. This fits queue workers, though it does not guarantee strict FIFO order in the presence of locks and retries.

### 23.3. A lease is not an absolute lock

Worker A might pause for a long time, its lease expires, worker B claims the batch, and then A wakes up and resumes. You need fencing tokens/ownership checks in the apply transaction, heartbeats, and/or transaction-level advisory locks.

### 23.4. Fencing token

Some systems increment `lease_generation` on every claim. A worker may only commit results if its generation still matches the active token. An old worker cannot write after a new worker claims a higher generation.

Conceptual example:

```sql
UPDATE ingest.batches
SET
    lease_generation = lease_generation + 1,
    lease_owner = 'worker-17',
    lease_until = clock_timestamp() + interval '2 minutes'
WHERE batch_id = $1
RETURNING lease_generation;
```

To use this statement, add `lease_generation bigint NOT NULL DEFAULT 0` to the batch schema. Inside the apply transaction, lock the batch row and verify the generation before writing to the target.

### 23.5. Advisory transaction lock

You can serialize by source/batch using `pg_advisory_xact_lock(...)` if lock key conventions are consistent. Advisory locks assist coordination, while unique constraints and idempotent writes must still protect the data.

### 23.6. Do not hold a transaction open while downloading files over the network

Downloading files, calling APIs, decompressing, and validating take time. Perform them beforehand or outside the apply transaction. Open the DB transaction only briefly to write the chunk, merge, and checkpoint.

## 24. Reconciliation: From Counts to Content

Reconciliation must have layered checks.

### 24.1. Count reconciliation

For a batch:

- `expected_rows`: rows declared by the source.
- `received_rows`: raw rows received.
- `valid_rows`: rows passing validation.
- `rejected_rows`: rows quarantined.
- `duplicate_rows`: duplicate deliveries/rows.
- `applied_new_rows`: newly inserted records.
- `applied_update_rows`: updated records.
- `unchanged_rows`: same version and payload.
- `stale_rows`: older events ignored.

Define **non-overlapping** buckets or clearly document which buckets are subsets. If `received = valid + rejected`, duplicates may be an attribute of valid rows rather than being added a second time.

### 24.2. Example of clear accounting

A batch has 1,000 source rows:

| Final classification (mutually exclusive) | Count |
| --- | ---: |
| New records applied | 700 |
| Existing records updated | 150 |
| Unchanged duplicates | 80 |
| Stale events ignored | 30 |
| Rejected | 40 |
| **Total received** | **1,000** |

If the source contract declares 1,000 rows, `received_rows` must match. In this example, `valid_rows` is 960 assuming stale/unchanged rows were valid; rejected is 40. Do not sum `700 + 150 + 80 + 30 + 40` and add duplicates again on top.

### 24.3. Reconcile raw rows against expected

```sql
SELECT
    b.batch_id,
    b.expected_rows,
    COUNT(r.source_row_no) AS actual_raw_rows,
    b.received_rows
FROM ingest.batches AS b
LEFT JOIN ingest.raw_order_rows AS r
  ON r.batch_id = b.batch_id
WHERE b.batch_id =
    '11111111-1111-4111-8111-111111111111'
GROUP BY b.batch_id, b.expected_rows, b.received_rows;
```

If a batch is chunked, check unique row numbers and row-number ranges/partition completeness against the source contract; matching counts alone do not prove no row was substituted.

### 24.4. Missing and extra keys via anti-join

If you have a normalized source snapshot table `ingest.source_snapshot_orders`, compare:

```sql
-- Present in source but missing in target.
SELECT s.tenant_id, s.source_record_id
FROM ingest.source_snapshot_orders AS s
LEFT JOIN app.orders AS t
  ON t.tenant_id = s.tenant_id
 AND t.source_system = s.source_system
 AND t.source_record_id = s.source_record_id
WHERE s.snapshot_id = $1
  AND t.source_record_id IS NULL;

-- Present in target within scope but no longer in source snapshot.
SELECT t.tenant_id, t.source_record_id
FROM app.orders AS t
LEFT JOIN ingest.source_snapshot_orders AS s
  ON s.tenant_id = t.tenant_id
 AND s.source_system = t.source_system
 AND s.source_record_id = t.source_record_id
 AND s.snapshot_id = $1
WHERE t.source_system = $2
  AND t.tenant_id = $3
  AND t.deleted_at IS NULL
  AND s.source_record_id IS NULL;
```

The second query is only meaningful if the source snapshot is **complete, finalized, and covers the exact same scope**. Never delete records based on a partial snapshot.

### 24.5. Comparing versions and payload hashes

```sql
SELECT
    s.tenant_id,
    s.source_record_id,
    s.source_version AS source_version,
    t.source_version AS target_version,
    s.payload_sha256 AS source_hash,
    t.payload_sha256 AS target_hash
FROM ingest.source_snapshot_orders AS s
JOIN app.orders AS t
  ON t.tenant_id = s.tenant_id
 AND t.source_system = s.source_system
 AND t.source_record_id = s.source_record_id
WHERE s.snapshot_id = $1
  AND (
      s.source_version <> t.source_version
      OR s.payload_sha256 <> t.payload_sha256
  );
```

Investigate each category: target stale, source stale, same-version conflict, normalization mismatch, or apply error.

## 25. Checksum Reconciliation for Large Datasets

Count and key checks are not enough to prove payloads match. Checksums can detect discrepancies across record sets.

### 25.1. Canonical row representation

For example, each record is formatted in a fixed field order:

```text
tenant_id | source_system | source_record_id |
source_version | status | amount | deleted_at
```

You need exact rules for representing NULL, numeric scale, timestamp timezone, and Unicode.

### 25.2. Partitioned checksum

With `pgcrypto`:

```sql
SELECT
    tenant_id,
    COUNT(*) AS row_count,
    encode(
        digest(
            convert_to(
                string_agg(
                    concat_ws(
                        E'\x1f',
                        source_record_id,
                        source_version::text,
                        payload_sha256
                    ),
                    E'\n'
                    ORDER BY source_record_id
                ),
                'UTF8'
            ),
            'sha256'
        ),
        'hex'
    ) AS partition_sha256
FROM app.orders
WHERE source_system = 'partner_a'
  AND deleted_at IS NULL
GROUP BY tenant_id
ORDER BY tenant_id;
```

### 25.3. Limits of the string_agg example

A very large partition can build a huge temporary string in memory. In production, split by tenant, key range, or date partitions, or use a Merkle tree / hierarchical checksums with canonical leaf hashing.

### 25.4. Do not sum hashes arithmetically as a strong checksum

`SUM(hash_as_number)` or simple XOR can suffer collisions and fail to preserve ordering/identity as expected. Use a well-defined checksum design that both sides can reproduce deterministically.

### 25.5. A hash does not prove the source is trustworthy

Checksums only verify that content matches the computed digest. If the source can be spoofed, you need authenticated transport, signatures, or trusted source controls.

## 26. Business Aggregate Reconciliation

Beyond row counts and hashes, compare meaningful totals:

```sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count,
    SUM(amount) AS amount_total,
    MIN(source_updated_at) AS first_seen,
    MAX(source_updated_at) AS last_seen
FROM app.orders
WHERE source_system = 'partner_a'
  AND deleted_at IS NULL
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

If the source provides summaries by tenant/status, compare against the corresponding totals.

### 26.1. Aggregate matches do not prove record-level matches

One missing order of 100 and one extra order of 100 leave the total amount unchanged. Therefore, aggregates are **one layer** of reconciliation, not a substitute for key-level comparison.

### 26.2. Currency and precision

Do not sum amounts across multiple currencies without an explicit currency conversion contract. Use `numeric`, not floating point, for accounting values; specify scale and rounding.

### 26.3. Time window

Compare over the same snapshot or time window. If the source keeps changing while the target is ingesting, aggregates may legitimately differ because the two sides reflect different points in time.

## 27. Full Snapshots and Incremental/CDC Feeds Are Different

### 27.1. Full snapshot

The source declares: "This is the complete set of orders belonging to tenant 10 at snapshot S."

You may compare missing/extra keys and mark deleted records only if:

- The snapshot has a completion marker.
- All pages/parts have been received.
- Counts and checksums are valid.
- The tenant and source scope match.
- No other unserialized batch is concurrently updating the same scope.

### 27.2. Incremental feed

The source only sends new or changed records since a watermark. A record absent from an incremental batch **does not mean it was deleted**.

### 27.3. CDC

CDC emits change events in log sequence order. You must preserve source offset/LSN, transaction ordering, and delete events. Never infer a delete from a key's absence in a chunk.

### 27.4. Full snapshot generation

One way to manage visibility:

1. Create `snapshot_id`.
2. Load all rows into the new generation.
3. Reconcile expected count and checksum.
4. Only when complete, mark the generation `published`.
5. Downstream reads the current generation.
6. Clean up old generations according to retention policy.

This prevents downstream consumers from reading a partial snapshot while an import is running.

### 27.5. Never delete based on a snapshot missing a page

If page 4 of 10 fails to download and the pipeline still marks absent records as deleted, it can wipe out large volumes of valid data. Full snapshots require a completion manifest and reconciliation before any delete phase.

## 28. Late-Arriving and Out-of-Order Events

A version 12 event can arrive before version 11. When version 11 arrives later, it must not overwrite version 12.

### 28.1. Version gate

The condition:

```sql
WHERE EXCLUDED.source_version > current_order.source_version
```

keeps the target at the higher version.

### 28.2. Versions must have well-defined semantics

If source versions reset daily or per partition, they cannot be compared globally without adding epoch or partition identity. Clarify:

- Does version increase per record?
- Does offset increase per partition?
- Do timestamps have a tie-breaker?
- Can the source replay historical corrections?
- Do deletes carry versions like updates?

### 28.3. Same version, different payload

Never pick a winner randomly. Record the conflict, quarantine it, and require the source contract/owner to resolve it.

### 28.4. Late corrections

A valid correction may carry an old business effective date with a newer event version. Do not use the business date instead of event ordering. Store both `source_version` and `source_updated_at`/effective time if needed.

## 29. Partial Error Handling and Poison Records

One invalid row does not necessarily invalidate all other rows, but the policy must be explicit.

### 29.1. Atomic batch

If a batch is an indivisible business unit, any validation or merge error rolls back the entire batch. After the source fixes the file, issue a new batch key or new version per contract; do not reuse the same key with different content unrecorded.

### 29.2. Partial acceptance

If accepting partial rows:

- Write every row to raw.
- Record validation status explicitly.
- Route invalid rows to quarantine.
- Merge only valid rows.
- Ensure counts add up accurately.
- Do not mark the batch `reconciled` until rejected rows are accepted per policy or remediated.

### 29.3. Poison message

A message that repeatedly crashes the consumer can block a partition or queue. After a bounded number of retries, move it to a dead-letter or quarantine store, record the reason, and preserve the original payload. Never silently drop the message.

### 29.4. Do not use `WHEN OTHERS THEN NULL`

Catching every exception and continuing can cause a batch to report success even though some rows were never applied. If catching errors for partial processing, you must log the error, classify it, and ensure clear transaction/savepoint semantics.

### 29.5. Per-row savepoints have overhead

Savepoints allow rolling back part of a transaction, but they add overhead and do not replace validation. For large files, set-based validation followed by merging valid rows is usually much faster than looping with a savepoint per row.

## 30. Chunk Checkpoints and Resumability

For very large batches, divide work into chunks with deterministic ordering.

### 30.1. Chunk identity

For example:

`(batch_id, chunk_no)` or `(source_partition, first_offset, last_offset)`.

The same chunk must cover the exact same source range on every retry.

### 30.2. Chunk ledger

```sql
CREATE TABLE ingest.batch_chunks (
    batch_id uuid NOT NULL
        REFERENCES ingest.batches(batch_id),
    chunk_no integer NOT NULL,
    first_row_no bigint NOT NULL,
    last_row_no bigint NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'applying', 'applied', 'failed')),
    rows_received bigint NOT NULL DEFAULT 0,
    rows_applied bigint NOT NULL DEFAULT 0,
    payload_sha256 text,
    applied_at timestamptz,
    PRIMARY KEY (batch_id, chunk_no),
    CHECK (first_row_no <= last_row_no)
);
```

### 30.3. Atomic chunk commit

Inside a single transaction:

1. Lock the chunk row.
2. Verify checksum and status.
3. Merge target rows idempotently.
4. Update the chunk to `applied`.
5. Update the corresponding checkpoint.
6. Commit.

If the process crashes before commit, both the merge and progress update roll back. If it crashes after commit but before the worker receives the response, the rerun sees the chunk as `applied` and does not misapply it again.

### 30.4. Do not rely only on contiguous row numbers

If source pages have gaps or opaque cursors, use the source-provided cursor or offset. `last_row_no` only fits ordered files/batches with stable row numbering.

### 30.5. Batch completion

A batch transitions to `applied` once all required chunks are applied or classified as rejected under the partial-acceptance policy. Then run reconciliation and transition to `reconciled` only when checks pass.

## 31. Managing Multiple Workers Safely

When multiple workers process batches, you must prevent two workers from applying the same batch concurrently or a stale worker from writing after its lease has moved to another owner.

### 31.1. Claim a batch with SKIP LOCKED

```sql
WITH candidate AS (
    SELECT batch_id
    FROM ingest.batches
    WHERE status IN ('received', 'retryable')
      AND (
          lease_until IS NULL
          OR lease_until < clock_timestamp()
      )
    ORDER BY created_at, batch_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE ingest.batches AS b
SET
    status = 'loading',
    lease_owner = 'worker-17',
    lease_until = clock_timestamp() + interval '2 minutes',
    attempt_count = attempt_count + 1,
    started_at = COALESCE(started_at, clock_timestamp())
FROM candidate AS c
WHERE b.batch_id = c.batch_id
RETURNING b.*;
```

This example runs in a short transaction. Commit the claim first, and only then let the worker execute the processing work.

### 31.2. Why SKIP LOCKED?

If worker A locks batch row 1, worker B skips that row and picks up another batch instead of blocking. This fits queue workers, though it does not guarantee strict FIFO order in the presence of locks and retries.

### 31.3. A lease is not an absolute lock

Worker A might pause for a long time, its lease expires, worker B claims the batch, and then A wakes up and resumes. You need fencing tokens/ownership checks in the apply transaction, heartbeats, and/or transaction-level advisory locks.

### 31.4. Fencing token

Some systems increment `lease_generation` on every claim. A worker may only commit results if its generation still matches the active token. An old worker cannot write after a new worker claims a higher generation.

Conceptual example:

```sql
UPDATE ingest.batches
SET
    lease_generation = lease_generation + 1,
    lease_owner = 'worker-17',
    lease_until = clock_timestamp() + interval '2 minutes'
WHERE batch_id = $1
RETURNING lease_generation;
```

To use this statement, add `lease_generation bigint NOT NULL DEFAULT 0` to the batch schema. Inside the apply transaction, lock the batch row and verify the generation before writing to the target.

### 31.5. Advisory transaction lock

You can serialize by source/batch using `pg_advisory_xact_lock(...)` if lock key conventions are consistent. Advisory locks assist coordination, while unique constraints and idempotent writes must still protect the data.

### 31.6. Do not hold a transaction open while downloading files over the network

Downloading files, calling APIs, decompressing, and validating take time. Perform them beforehand or outside the apply transaction. Open the DB transaction only briefly to write the chunk, merge, and checkpoint.

## 32. Reconciliation: From Counts to Content

Reconciliation must have layered checks.

### 32.1. Count reconciliation

For a batch:

- `expected_rows`: rows declared by the source.
- `received_rows`: raw rows received.
- `valid_rows`: rows passing validation.
- `rejected_rows`: rows quarantined.
- `duplicate_rows`: duplicate deliveries/rows.
- `applied_new_rows`: newly inserted records.
- `applied_update_rows`: updated records.
- `unchanged_rows`: same version and payload.
- `stale_rows`: older events ignored.

Define **non-overlapping** buckets or clearly document which buckets are subsets. If `received = valid + rejected`, duplicates may be an attribute of valid rows rather than being added a second time.

### 32.2. Example of clear accounting

A batch has 1,000 source rows:

| Final classification (mutually exclusive) | Count |
| --- | ---: |
| New records applied | 700 |
| Existing records updated | 150 |
| Unchanged duplicates | 80 |
| Stale events ignored | 30 |
| Rejected | 40 |
| **Total received** | **1,000** |

If the source contract declares 1,000 rows, `received_rows` must match. In this example, `valid_rows` is 960 assuming stale/unchanged rows were valid; rejected is 40. Do not sum `700 + 150 + 80 + 30 + 40` and add duplicates again on top.

### 32.3. Reconcile raw rows against expected

```sql
SELECT
    b.batch_id,
    b.expected_rows,
    COUNT(r.source_row_no) AS actual_raw_rows,
    b.received_rows
FROM ingest.batches AS b
LEFT JOIN ingest.raw_order_rows AS r
  ON r.batch_id = b.batch_id
WHERE b.batch_id =
    '11111111-1111-4111-8111-111111111111'
GROUP BY b.batch_id, b.expected_rows, b.received_rows;
```

If a batch is chunked, check unique row numbers and row-number ranges/partition completeness against the source contract; matching counts alone do not prove no row was substituted.

### 32.4. Missing and extra keys via anti-join

If you have a normalized source snapshot table `ingest.source_snapshot_orders`, compare:

```sql
-- Present in source but missing in target.
SELECT s.tenant_id, s.source_record_id
FROM ingest.source_snapshot_orders AS s
LEFT JOIN app.orders AS t
  ON t.tenant_id = s.tenant_id
 AND t.source_system = s.source_system
 AND t.source_record_id = s.source_record_id
WHERE s.snapshot_id = $1
  AND t.source_record_id IS NULL;

-- Present in target within scope but no longer in source snapshot.
SELECT t.tenant_id, t.source_record_id
FROM app.orders AS t
LEFT JOIN ingest.source_snapshot_orders AS s
  ON s.tenant_id = t.tenant_id
 AND s.source_system = t.source_system
 AND s.source_record_id = t.source_record_id
 AND s.snapshot_id = $1
WHERE t.source_system = $2
  AND t.tenant_id = $3
  AND t.deleted_at IS NULL
  AND s.source_record_id IS NULL;
```

The second query is only meaningful if the source snapshot is **complete, finalized, and covers the exact same scope**. Never delete records based on a partial snapshot.

### 32.5. Comparing versions and payload hashes

```sql
SELECT
    s.tenant_id,
    s.source_record_id,
    s.source_version AS source_version,
    t.source_version AS target_version,
    s.payload_sha256 AS source_hash,
    t.payload_sha256 AS target_hash
FROM ingest.source_snapshot_orders AS s
JOIN app.orders AS t
  ON t.tenant_id = s.tenant_id
 AND t.source_system = s.source_system
 AND t.source_record_id = s.source_record_id
WHERE s.snapshot_id = $1
  AND (
      s.source_version <> t.source_version
      OR s.payload_sha256 <> t.payload_sha256
  );
```

Investigate each category: target stale, source stale, same-version conflict, normalization mismatch, or apply error.

## 33. Checksum Reconciliation for Large Datasets

Count and key checks are not enough to prove payloads match. Checksums can detect discrepancies across record sets.

### 33.1. Canonical row representation

For example, each record is formatted in a fixed field order:

```text
tenant_id | source_system | source_record_id |
source_version | status | amount | deleted_at
```

You need exact rules for representing NULL, numeric scale, timestamp timezone, and Unicode.

### 33.2. Partitioned checksum

With `pgcrypto`:

```sql
SELECT
    tenant_id,
    COUNT(*) AS row_count,
    encode(
        digest(
            convert_to(
                string_agg(
                    concat_ws(
                        E'\x1f',
                        source_record_id,
                        source_version::text,
                        payload_sha256
                    ),
                    E'\n'
                    ORDER BY source_record_id
                ),
                'UTF8'
            ),
            'sha256'
        ),
        'hex'
    ) AS partition_sha256
FROM app.orders
WHERE source_system = 'partner_a'
  AND deleted_at IS NULL
GROUP BY tenant_id
ORDER BY tenant_id;
```

### 33.3. Limits of the string_agg example

A very large partition can build a huge temporary string in memory. In production, split by tenant, key range, or date partitions, or use a Merkle tree / hierarchical checksums with canonical leaf hashing.

### 33.4. Do not sum hashes arithmetically as a strong checksum

`SUM(hash_as_number)` or simple XOR can suffer collisions and fail to preserve ordering/identity as expected. Use a well-defined checksum design that both sides can reproduce deterministically.

### 33.5. A hash does not prove the source is trustworthy

Checksums only verify that content matches the computed digest. If the source can be spoofed, you need authenticated transport, signatures, or trusted source controls.

## 34. Business Aggregate Reconciliation

Beyond row counts and hashes, compare meaningful totals:

```sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count,
    SUM(amount) AS amount_total,
    MIN(source_updated_at) AS first_seen,
    MAX(source_updated_at) AS last_seen
FROM app.orders
WHERE source_system = 'partner_a'
  AND deleted_at IS NULL
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

If the source provides summaries by tenant/status, compare against the corresponding totals.

### 34.1. Aggregate matches do not prove record-level matches

One missing order of 100 and one extra order of 100 leave the total amount unchanged. Therefore, aggregates are **one layer** of reconciliation, not a substitute for key-level comparison.

### 34.2. Currency and precision

Do not sum amounts across multiple currencies without an explicit currency conversion contract. Use `numeric`, not floating point, for accounting values; specify scale and rounding.

### 34.3. Time window

Compare over the same snapshot or time window. If the source keeps changing while the target is ingesting, aggregates may legitimately differ because the two sides reflect different points in time.

## 35. Full Snapshots and Incremental/CDC Feeds Are Different

### 35.1. Full snapshot

The source declares: "This is the complete set of orders belonging to tenant 10 at snapshot S."

You may compare missing/extra keys and mark deleted records only if:

- The snapshot has a completion marker.
- All pages/parts have been received.
- Counts and checksums are valid.
- The tenant and source scope match.
- No other unserialized batch is concurrently updating the same scope.

### 35.2. Incremental feed

The source only sends new or changed records since a watermark. A record absent from an incremental batch **does not mean it was deleted**.

### 35.3. CDC

CDC emits change events in log sequence order. You must preserve source offset/LSN, transaction ordering, and delete events. Never infer a delete from a key's absence in a chunk.

### 35.4. Full snapshot generation

One way to manage visibility:

1. Create `snapshot_id`.
2. Load all rows into the new generation.
3. Reconcile expected count and checksum.
4. Only when complete, mark the generation `published`.
5. Downstream reads the current generation.
6. Clean up old generations according to retention policy.

This prevents downstream consumers from reading a partial snapshot while an import is running.

### 35.5. Never delete based on a snapshot missing a page

If page 4 of 10 fails to download and the pipeline still marks absent records as deleted, it can wipe out large volumes of valid data. Full snapshots require a completion manifest and reconciliation before any delete phase.

## 36. Late-Arriving and Out-of-Order Events

A version 12 event can arrive before version 11. When version 11 arrives later, it must not overwrite version 12.

### 36.1. Version gate

The condition:

```sql
WHERE EXCLUDED.source_version > current_order.source_version
```

keeps the target at the higher version.

### 36.2. Versions must have well-defined semantics

If source versions reset daily or per partition, they cannot be compared globally without adding epoch or partition identity. Clarify:

- Does version increase per record?
- Does offset increase per partition?
- Do timestamps have a tie-breaker?
- Can the source replay historical corrections?
- Do deletes carry versions like updates?

### 36.3. Same version, different payload

Never pick a winner randomly. Record the conflict, quarantine it, and require the source contract/owner to resolve it.

### 36.4. Late corrections

A valid correction may carry an old business effective date with a newer event version. Do not use the business date instead of event ordering. Store both `source_version` and `source_updated_at`/effective time if needed.

## 37. Partial Error Handling and Poison Records

One invalid row does not necessarily invalidate all other rows, but the policy must be explicit.

### 37.1. Atomic batch

If a batch is an indivisible business unit, any validation or merge error rolls back the entire batch. After the source fixes the file, issue a new batch key or new version per contract; do not reuse the same key with different content unrecorded.

### 37.2. Partial acceptance

If accepting partial rows:

- Write every row to raw.
- Record validation status explicitly.
- Route invalid rows to quarantine.
- Merge only valid rows.
- Ensure counts add up accurately.
- Do not mark the batch `reconciled` until rejected rows are accepted per policy or remediated.

### 37.3. Poison message

A message that repeatedly crashes the consumer can block a partition or queue. After a bounded number of retries, move it to a dead-letter or quarantine store, record the reason, and preserve the original payload. Never silently drop the message.

### 37.4. Do not use `WHEN OTHERS THEN NULL`

Catching every exception and continuing can cause a batch to report success even though some rows were never applied. If catching errors for partial processing, you must log the error, classify it, and ensure clear transaction/savepoint semantics.

### 37.5. Per-row savepoints have overhead

Savepoints allow rolling back part of a transaction, but they add overhead and do not replace validation. For large files, set-based validation followed by merging valid rows is usually much faster than looping with a savepoint per row.

## 38. Chunk Checkpoints and Resumability

For very large batches, divide work into chunks with deterministic ordering.

### 38.1. Chunk identity

For example:

`(batch_id, chunk_no)` or `(source_partition, first_offset, last_offset)`.

The same chunk must cover the exact same source range on every retry.

### 38.2. Chunk ledger

```sql
CREATE TABLE ingest.batch_chunks (
    batch_id uuid NOT NULL
        REFERENCES ingest.batches(batch_id),
    chunk_no integer NOT NULL,
    first_row_no bigint NOT NULL,
    last_row_no bigint NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'applying', 'applied', 'failed')),
    rows_received bigint NOT NULL DEFAULT 0,
    rows_applied bigint NOT NULL DEFAULT 0,
    payload_sha256 text,
    applied_at timestamptz,
    PRIMARY KEY (batch_id, chunk_no),
    CHECK (first_row_no <= last_row_no)
);
```

### 38.3. Atomic chunk commit

Inside a single transaction:

1. Lock the chunk row.
2. Verify checksum and status.
3. Merge target rows idempotently.
4. Update the chunk to `applied`.
5. Update the corresponding checkpoint.
6. Commit.

If the process crashes before commit, both the merge and progress update roll back. If it crashes after commit but before the worker receives the response, the rerun sees the chunk as `applied` and does not misapply it again.

### 38.4. Do not rely only on contiguous row numbers

If source pages have gaps or opaque cursors, use the source-provided cursor or offset. `last_row_no` only fits ordered files/batches with stable row numbering.

### 38.5. Batch completion

A batch transitions to `applied` once all required chunks are applied or classified as rejected under the partial-acceptance policy. Then run reconciliation and transition to `reconciled` only when checks pass.

## 39. Managing Multiple Workers Safely

When multiple workers process batches, you must prevent two workers from applying the same batch concurrently or a stale worker from writing after its lease has moved to another owner.

### 39.1. Claim a batch with SKIP LOCKED

```sql
WITH candidate AS (
    SELECT batch_id
    FROM ingest.batches
    WHERE status IN ('received', 'retryable')
      AND (
          lease_until IS NULL
          OR lease_until < clock_timestamp()
      )
    ORDER BY created_at, batch_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE ingest.batches AS b
SET
    status = 'loading',
    lease_owner = 'worker-17',
    lease_until = clock_timestamp() + interval '2 minutes',
    attempt_count = attempt_count + 1,
    started_at = COALESCE(started_at, clock_timestamp())
FROM candidate AS c
WHERE b.batch_id = c.batch_id
RETURNING b.*;
```

This example runs in a short transaction. Commit the claim first, and only then let the worker execute the processing work.

### 39.2. Why SKIP LOCKED?

If worker A locks batch row 1, worker B skips that row and picks up another batch instead of blocking. This fits queue workers, though it does not guarantee strict FIFO order in the presence of locks and retries.

### 39.3. A lease is not an absolute lock

Worker A might pause for a long time, its lease expires, worker B claims the batch, and then A wakes up and resumes. You need fencing tokens/ownership checks in the apply transaction, heartbeats, and/or transaction-level advisory locks.

### 39.4. Fencing token

Some systems increment `lease_generation` on every claim. A worker may only commit results if its generation still matches the active token. An old worker cannot write after a new worker claims a higher generation.

Conceptual example:

```sql
UPDATE ingest.batches
SET
    lease_generation = lease_generation + 1,
    lease_owner = 'worker-17',
    lease_until = clock_timestamp() + interval '2 minutes'
WHERE batch_id = $1
RETURNING lease_generation;
```

To use this statement, add `lease_generation bigint NOT NULL DEFAULT 0` to the batch schema. Inside the apply transaction, lock the batch row and verify the generation before writing to the target.

### 39.5. Advisory transaction lock

You can serialize by source/batch using `pg_advisory_xact_lock(...)` if lock key conventions are consistent. Advisory locks assist coordination, while unique constraints and idempotent writes must still protect the data.

### 39.6. Do not hold a transaction open while downloading files over the network

Downloading files, calling APIs, decompressing, and validating take time. Perform them beforehand or outside the apply transaction. Open the DB transaction only briefly to write the chunk, merge, and checkpoint.

## 40. Transaction Boundaries and External Side Effects

A PostgreSQL transaction only atomically guarantees changes within **the same PostgreSQL database**.

No simple transaction spans:

- PostgreSQL commit.
- Kafka offset ack.
- Writing a file to object storage.
- Sending an email.
- Calling a payment API.
- Sending a webhook to a partner.

### 40.1. Transactional outbox

If merging data must emit an event to another system, write an outbox row **in the same transaction** as the target update:

```sql
CREATE TABLE app.outbox (
    event_id uuid PRIMARY KEY,
    aggregate_key text NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    published_at timestamptz
);
```

Inside the apply transaction:

```sql
BEGIN;

-- UPSERT app.orders ...

INSERT INTO app.outbox (
    event_id,
    aggregate_key,
    event_type,
    payload
)
VALUES (
    '22222222-2222-4222-8222-222222222222',
    'partner_a:order-9381',
    'order.imported',
    '{"order_id":"order-9381","version":17}'::jsonb
)
ON CONFLICT (event_id) DO NOTHING;

COMMIT;
```

The publisher reads the outbox, dispatches the message, and then marks it published. If the publisher sends successfully but crashes before updating `published_at`, the event may be resent; downstream consumers still require idempotency by `event_id`.

### 40.2. Do not make HTTP calls inside the apply transaction

Calling external APIs while a transaction holds locks extends transaction duration and cannot atomically roll back the API call if the DB rolls back.

### 40.3. Side effects must carry an idempotency key

Email, payment, and webhook providers require an idempotency key or an appropriate delivery ledger. The outbox guarantees the intent is not lost between DB update and publish, but it does not by itself guarantee downstream executes only once.

## 41. Repeatable Exports and Reconciliation

Exporting data also requires identity, snapshots, and checksums.

### 41.1. Stable export identity

Use `export_id`, source scope, snapshot/version, filter parameters, and format version. Retrying the same export identity must produce the same logical dataset given the same snapshot contract.

### 41.2. Consistent snapshot

If exporting across multiple pages while the table continues to change, pages can reflect different points in time. Use a `REPEATABLE READ READ ONLY` transaction or a published snapshot/generation:

```sql
BEGIN TRANSACTION
ISOLATION LEVEL REPEATABLE READ
READ ONLY;

SELECT
    order_id,
    customer_code,
    status,
    amount
FROM app.orders
WHERE tenant_id = 10
  AND deleted_at IS NULL
ORDER BY order_id;

COMMIT;
```

Long-running transactions carry snapshot-retention costs; for large exports, consider a snapshot generation/materialized export dataset or bounded runtime.

### 41.3. Keyset pagination

Do not rely on large `OFFSET` values if data changes between pages. Use keyset pagination:

```sql
SELECT order_id, customer_code, amount
FROM app.orders
WHERE tenant_id = $1
  AND order_id > $2
ORDER BY order_id
LIMIT $3;
```

Within a consistent snapshot, the cursor is the last exported key. Without a consistent snapshot, inserts, updates, and deletes between pages can still leave the dataset inconsistent.

### 41.4. Publish files atomically

A standard pattern:

1. Write the file to a temporary object or path scoped by `export_id`.
2. Flush and complete the upload.
3. Compute checksum and row count.
4. Write the manifest.
5. Publish via atomic rename or object version pointer where supported by storage.
6. Retries reuse the same identity and checksum; never silently overwrite an already-published file with different content.

### 41.5. Export reconciliation

The manifest can record:

- `export_id`.
- Snapshot/generation.
- Query/filter version.
- Expected rows.
- Actual rows.
- File size.
- SHA-256.
- Created/published timestamps.
- Schema/format version.

The recipient verifies checksum, row count, and schema version before importing.

## 42. Handling Schema Evolution

The source may add columns, rename fields, change enums, or alter formats.

### 42.1. Version the payload

Record `schema_version` / `format_version` in batch metadata. The parser selects the exact schema contract instead of guessing from whichever fields happen to appear.

### 42.2. Raw payloads preserve replay capability

Retain raw payloads long enough to rerun a newer parser against older data when fixing bugs or extending schemas.

### 42.3. Controlled staging migrations

Do not alter the target schema in a breaking way while an older batch is applying without compatibility. You can version parsers and staging tables, then map them into the current target model.

### 42.4. Unknown fields

Choose an explicit policy: reject, ignore with a warning, or store in a JSONB extension field. Never silently drop fields with business meaning.

### 42.5. Idempotent backfills

A backfill is simply a pipeline with different throughput characteristics; it still relies on source identity, versions, and checkpoints. Never rewrite the entire target with an unconditional `UPDATE` if the source can continue producing updates concurrently.

## 43. Normalizing Data Before Comparing

Two systems can represent the same value differently:

- `1.0` and `1.00`.
- `2026-11-14T10:00:00+07:00` and `2026-11-14T03:00:00Z`.
- Composed vs. decomposed Unicode.
- Empty string vs. SQL NULL.
- Uppercase vs. lowercase status.
- JSON key ordering and whitespace.
- Currency units or rounding.

### 43.1. Define a canonical representation

Before hashing or comparing, specify:

- Standard timezone (usually stored as an instant in `timestamptz`).
- Decimal precision and scale.
- Unicode normalization if required by business rules.
- Case sensitivity and collation.
- NULL/empty semantics.
- Enum mapping.
- JSON canonicalization.
- Field inclusion/exclusion.

### 43.2. Do not normalize arbitrarily and lose meaning

Calling `trim()` on every text field can alter identifiers with meaningful whitespace. Lowercasing every string can corrupt case-sensitive IDs. Normalize strictly according to the data contract.

### 43.3. Store both raw and normalized data

Raw data enables investigation and replay; normalized typed values enable queries, indexes, constraints, and reconciliation.

## 44. Security and Access Control for Pipelines

An ingestion worker typically holds significant write privileges. Separate roles:

- `ingest_reader`: reads from sources if using a connector or database link.
- `ingest_writer`: writes raw, staging, and batch metadata.
- `ingest_applier`: merges into business tables within allowed scope.
- `app_runtime`: normal application privileges.
- `audit_reader`: reads reconciliation results.
- DBA/migration role: schema administration.

### 44.1. Least privilege

Do not use superuser credentials for the importer. Workers should only have privileges on relevant schemas/tables and defined operations.

### 44.2. Tenant scope

If a batch spans multiple tenants, verify tenant IDs against the source contract and authorization rules. Never trust a user-uploaded file to declare arbitrary tenant IDs.

### 44.3. Raw payloads can be sensitive

Apply retention, encryption/access controls, masking, and auditing to raw and quarantine storage. Never log full payloads containing PII or secrets.

### 44.4. Dynamic SQL in imports

Dynamic table, partition, or schema names must go through an allowlist mapping and identifier quoting; values must still be bound parameters. Never take raw field names or DDL fragments from a CSV to concatenate SQL.

### 44.5. File handling

Use `COPY FROM STDIN` or privilege-scoped upload APIs. Do not grant server filesystem read access to an application just for import convenience.

## 45. Performance: Optimize After Semantics Are Correct

### 45.1. Batch size

Batches that are too small increase round trips and commit overhead; batches that are too large increase memory usage, WAL volume, lock duration, and recovery time. Size according to payload size, indexes, write amplification, and replication capacity.

### 45.2. COPY and set-based merges

Fast COPY into raw/staging followed by set-based SQL validation, deduplication, and merging is typically far better than looping over single-row `INSERT`s.

### 45.3. Index staging judiciously

Primary keys and indexes supporting dedup/joins are necessary; too many indexes slow down COPY and UPSERT. You can build indexes after bulk loading if the staging lifecycle allows.

### 45.4. Target indexes

Every unique/secondary index must be updated during an UPSERT. Keep indexes needed for business reads, while evaluating their write cost.

### 45.5. Partitioning

Large raw/staging tables organized by batch or date can be partitioned by time or source. The partition key should align with retention and query patterns; do not partition solely because a table is large without a plan.

### 45.6. Vacuum and bloat

Heavy UPSERT and update workloads generate dead tuples. Monitor autovacuum, table/index bloat, WAL, replication lag, and long-running snapshots.

### 45.7. Avoid long transactions

Chunk commits release locks and reduce transaction age. If downstream requires all-or-nothing visibility, use a generation/publish switch instead of holding a massive transaction open.

## 46. Operational Metrics and Statuses

Each batch should track:

| Group | Metrics/fields |
| --- | --- |
| Identity | source system, batch key, batch ID, payload checksum |
| Volume | expected, received, valid, rejected, duplicate |
| Apply | inserted, updated, unchanged, stale, deleted/tombstone |
| Reconciliation | missing, extra, conflicts, count/hash match |
| Timing | queued, started, last progress, completed, reconciled |
| Retry | attempt count, last error, worker, lease generation |
| Source | watermark start/end, snapshot ID, schema version |
| Export | export ID, row count, file size, checksum, publish status |

### 46.1. Alert conditions

- Batch stuck in `loading`/`applying` for too long.
- Repeated lease expirations.
- Same batch key with a different checksum.
- Reconciliation missing/extra/conflict counts non-zero.
- Spike in rejection rate.
- Watermark not advancing.
- Target lag behind source exceeding SLA.
- Rapidly climbing retry attempts.
- Growing outbox backlog.
- Unpublished export manifest.

### 46.2. Do not report only batch SUCCESS

`applied` and `reconciled` are distinct statuses:

- `applied`: the merge has committed.
- `reconciled`: all required verification checks passed.

A batch that is applied but shows mismatches must not be reported as fully complete.

### 46.3. Retain history

The batch ledger, chunk ledger, rejected rows, and reconciliation results explain what a run actually did. Enforce a retention/partition/archive policy; never delete evidence before the replay and audit window expires.

## 47. Failure Scenarios and Recovery

| Failure/crash point | Observable state | How to resume |
| --- | --- | --- |
| Before batch registration | No batch row | Register with the same source batch key |
| After registration, before raw load | `received` | Claim and reload |
| During COPY before commit | Temp/raw transaction uncommitted | Retry loading the same batch |
| After raw commit, before broker ack | Raw exists, message may be redelivered | Deduplicate event/batch identity, then ack |
| After staging, before apply | Raw/stage durable | Resume validation/apply |
| During atomic merge before commit | Target and progress rolled back | Retry the same batch/chunk |
| After commit, before worker gets response | Target changed | Re-read ledger/version/checksum; replay safe |
| After apply, before reconciliation | `applied` | Rerun reconciliation |
| After export file upload, before manifest publish | Temporary file may exist | Verify checksum, resume publish, or clean temp |
| Lease expires while old worker still runs | Two workers may race | Fencing token/lock + idempotent target |
| Same key, different checksum | Batch identity conflict | Quarantine/incident, do not overwrite |
| Same record/version, different payload | Record conflict | Quarantine/resolve per source contract |
| Out-of-order stale event | Lower version than target | Ignore with accounting |
| Delete event followed by late old insert | High-version tombstone | Do not resurrect |
| Snapshot missing a page | Incomplete reconciliation | Do not run delete reconciliation; fetch full snapshot |

## 48. End-to-End Implementation Workflow

A pipeline can be implemented through these steps:

### Step 1. Receive source and build batch manifest

Capture source system, stable batch key, checksum, expected row count, schema version, and source watermark.

### Step 2. Register idempotently

Insert into the batch registry with unique `(source_system, source_batch_key)`. If already present, compare checksums and resume or return prior status.

### Step 3. Persist raw data

Store the raw file/payload or URI+checksum; COPY into raw landing/staging. Ensure source ack happens only after raw data is durable.

### Step 4. Validate and normalize

Parse types, domain rules, identity, tenant scope, and source versions. Quarantine invalid rows.

### Step 5. Deduplicate and check conflicts

Same key/version/hash is a duplicate; same key/version/different hash is a conflict; select latest version per the source ordering contract.

### Step 6. Apply transactionally

UPSERT with unique constraints and a version gate. Apply tombstones for delete events. Commit progress/checkpoints in the same transaction or chunk.

### Step 7. Reconcile

Reconcile counts, keys, versions, payload checksums, and aggregates. For snapshots, mark missing/deleted records only when the snapshot is complete.

### Step 8. Publish downstream intent

Write to the outbox in the same target transaction. The publisher delivers events at-least-once; consumers deduplicate by event ID.

### Step 9. Mark reconciled

Transition the batch to `reconciled` only after required invariants hold and all rejected rows are handled according to policy.

### Step 10. Archive/retention

Keep raw, checkpoint, and audit data long enough for replay, reconciliation, and compliance needs; then archive or purge per retention policy.

## 49. Practice Exercises with Answers

These exercises use the `ingest` and `app` schemas from the lab. SQL snippets containing `$1`/`$2` assume execution inside a suitable prepared statement or function.

### Exercise 1. What is an idempotent operation?

**Answer:** an operation that produces the same final state whether applied once or multiple times, given the defined identity and semantics.

### Exercise 2. Why must an importer tolerate duplicate delivery?

**Answer:** brokers, file retries, network failures, or worker crashes can cause the same data to be redelivered; at-least-once is usually the practical choice.

### Exercise 3. How does a batch key differ from a record key?

**Answer:** a batch key identifies a source package; a record key identifies an entity or event across multiple batches.

### Exercise 4. Why is a row number not a business key?

**Answer:** file order can change, and a row number only identifies position within one specific batch.

### Exercise 5. Why is a unique constraint important?

**Answer:** it serves as the final safeguard against duplicates and race conditions; checking with SELECT before INSERT is not safe under concurrent workers.

### Exercise 6. What does same batch key, same checksum mean?

**Answer:** it is likely a retry of the same batch content; resume or return the saved result.

### Exercise 7. How should same batch key, different checksum be handled?

**Answer:** as a conflict/incident; do not silently replace the previous batch's payload.

### Exercise 8. Can SHA-256 replace source identity?

**Answer:** no. Two different records can have identical payloads; identity requires source keys.

### Exercise 9. What are the benefits of raw landing?

**Answer:** it preserves source evidence, allows replaying with updated parsers, traces errors, and decouples transport from business merging.

### Exercise 10. Does JSONB preserve a CSV file byte-for-byte?

**Answer:** no. It preserves parsed JSON values, not whitespace, key order, or original CSV quoting.

### Exercise 11. How does COPY FROM STDIN differ from COPY FROM '/path'?

**Answer:** STDIN receives a stream from the client; the path form reads a file on the server filesystem and has different privilege and path requirements.

### Exercise 12. Why should you COPY into staging?

**Answer:** to validate, deduplicate, quarantine, reconcile, and merge in a controlled way before touching the target.

### Exercise 13. What is a duplicate with the same key/version/hash?

**Answer:** usually duplicate delivery; keep one record and count the duplicates.

### Exercise 14. What about same key/version but different hash?

**Answer:** a data conflict; do not arbitrarily pick the last row unless the source contract defines a winner rule.

### Exercise 15. What is source version used for?

**Answer:** to prevent an older late-arriving event from overwriting a newer state.

### Exercise 16. Why can't received_at replace source_version?

**Answer:** older events can arrive late, so consumer receive time does not reflect the order of changes at the source.

### Exercise 17. Is ON CONFLICT DO NOTHING enough to prevent all corruption?

**Answer:** no. You must compare payload/hash on conflict; same key with different content must be detected.

### Exercise 18. Version condition in UPSERT?

```sql
WHERE EXCLUDED.source_version > current_order.source_version
```

**Answer:** updates the target only when the incoming version is newer.

### Exercise 19. Why shouldn't xmax=0 be used as a business accounting contract?

**Answer:** it infers behavior from a system column rather than a stable business API; use a ledger or explicit classification.

### Exercise 20. What is a tombstone?

**Answer:** a record/marker holding identity and delete version to prevent older events from resurrecting deleted data.

### Exercise 21. What if a delete event arrives before an insert event?

**Answer:** the tombstone must be stored even if the target row does not exist yet, so an older insert event cannot recreate the row.

### Exercise 22. Can a tombstone be deleted immediately after the delete?

**Answer:** not if the source can still replay or emit late events; retain it across the replay retention window.

### Exercise 23. What is a checkpoint?

**Answer:** a source position durably saved/processed under defined semantics, such as an offset, LSN, or cursor.

### Exercise 24. Why is advancing the checkpoint before target commit dangerous?

**Answer:** a crash could drop events that the checkpoint has already passed even though the target never saved them.

### Exercise 25. What is the benefit of data and checkpoint sharing a PostgreSQL transaction?

**Answer:** either both commit, or both roll back.

### Exercise 26. Is an external broker offset automatically atomic with a DB transaction?

**Answer:** no. Typically you use at-least-once delivery, persist the event before acking, and deduplicate by unique event ID.

### Exercise 27. What risk comes with a timestamp-only watermark?

**Answer:** records with identical timestamps or late-committed updates can be missed; use a composite cursor/tie-breaker or a CDC sequence.

### Exercise 28. When is an atomic batch appropriate?

**Answer:** when the batch is moderate in size and business rules demand all-or-nothing.

### Exercise 29. What extra pieces does chunked apply need?

**Answer:** stable chunk identity, a chunk ledger, and committing progress/checkpoints together with target changes.

### Exercise 30. Why shouldn't a batch be marked applied before the last chunk?

**Answer:** downstream consumers could treat partial data as complete.

### Exercise 31. What is FOR UPDATE SKIP LOCKED good for?

**Answer:** worker queues; each worker skips batch rows locked by other workers and claims other work.

### Exercise 32. Does an expired lease guarantee the old worker is dead?

**Answer:** no. The worker could be paused and wake up after a new worker claims the batch; fencing and ownership checks are required.

### Exercise 33. What does a fencing token help with?

**Answer:** it increments on each claim; an old worker holding a lower token cannot commit after ownership has changed.

### Exercise 34. Does an advisory lock replace a unique constraint?

**Answer:** no. Advisory locks coordinate workers; unique constraints still enforce data integrity in the database.

### Exercise 35. Is count reconciliation enough to prove two datasets match?

**Answer:** no. Two datasets with the same row count can still differ in keys and values.

### Exercise 36. What does an anti-join find?

**Answer:** keys present in the source but missing from the target, and extra keys in the target relative to a source snapshot when scope and snapshot are complete.

### Exercise 37. Can you delete every target row absent from an incremental batch?

**Answer:** no. Incremental batches contain only changes; absence does not imply deletion.

### Exercise 38. When can a full snapshot be used to mark missing records deleted?

**Answer:** only when the snapshot is complete, matches the scope, passed count/checksum checks, and has no missing pages.

### Exercise 39. Does matching an aggregate sum prove records match?

**Answer:** no. One missing record and one extra record can cancel each other out in the sum.

### Exercise 40. Why do checksums require canonical representation?

**Answer:** so identical logical data produces identical bytes and hashes on both sides; rules for timezones, NULLs, decimals, and field order must align.

### Exercise 41. How do whole-file hashing and logical-record hashing differ?

**Answer:** file hashing checks byte-for-byte identity; logical hashing checks data after parsing and normalization.

### Exercise 42. What is pgcrypto.digest used for?

**Answer:** computing digests such as SHA-256 inside PostgreSQL; the extension must be installed and canonical inputs must match.

### Exercise 43. Why not compare checksums with a simple SUM(hash)?

**Answer:** it invites collisions and fails to capture keys and order properly; use structured, partitioned hash aggregation.

### Exercise 44. How do applied and reconciled differ?

**Answer:** applied means the target merge committed; reconciled means required verification checks passed.

### Exercise 45. What must partial acceptance record?

**Answer:** valid/rejected counts, quarantine reasons, batch state, and the policy defining when the batch counts as complete.

### Exercise 46. Why shouldn't WHEN OTHERS THEN NULL be used?

**Answer:** it can mask errors and report a batch as successful even when rows were never applied.

### Exercise 47. What gap does an outbox bridge?

**Answer:** writing business data and publish intent in the same DB transaction; the publisher may retry, so downstream still needs deduplication.

### Exercise 48. Does an outbox guarantee an email is sent exactly once?

**Answer:** no. The email provider/downstream needs idempotency or a delivery ledger; the outbox mainly ensures the intent is not lost.

### Exercise 49. Why avoid calling an HTTP service inside the apply transaction?

**Answer:** it holds locks and transactions open too long and cannot roll back external side effects if the DB rolls back.

### Exercise 50. Why does a multi-page export need snapshot consistency?

**Answer:** data can change between pages, causing the exported file to contain rows from different points in time.

### Exercise 51. How does keyset pagination differ from OFFSET?

**Answer:** it continues from the last key read, avoiding large scans and row shifting; a consistent snapshot is still needed if a uniform dataset is required.

### Exercise 52. What should an export manifest contain?

**Answer:** export ID, snapshot, filter/schema version, row count, file size, checksum, and publish status.

### Exercise 53. Why is source schema_version needed?

**Answer:** so the parser knows how to interpret the payload instead of guessing structure when fields change.

### Exercise 54. How does raw payload help when a parser has a bug?

**Answer:** raw data can be replayed with a fixed parser without asking the source to resend, provided retention is still active.

### Exercise 55. Should every source ID be lowercased?

**Answer:** no. Normalize only per contract; IDs may be case-sensitive.

### Exercise 56. What canonicalization do numerics and timestamps require?

**Answer:** clear decimal scale, rounding, and currency; consistent instant, timezone, and precision for timestamps.

### Exercise 57. Why shouldn't an importer run as superuser?

**Answer:** a bug or malicious payload could impact the entire database; use least-privilege roles.

### Exercise 58. What sensitive data can raw/quarantine tables contain?

**Answer:** PII, tokens, or partner secrets; they require access controls, retention limits, and log masking.

### Exercise 59. How should reconciliation mismatches be handled?

**Answer:** classify missing, extra, version, hash, or schema mismatches, preserve evidence, and never mark reconciled or bulk-delete target rows before verification.

### Exercise 60. Write a checklist for safely replaying a batch

**Suggested answer:**

1. Use the same source system and batch key.
2. Compare checksums; same key with different content must trigger a conflict.
3. Confirm raw rows/chunks are persisted and row identity is stable.
4. Validate and deduplicate by key/version/hash.
5. Check for same-version/different-payload conflicts.
6. Merge using unique constraints and version-aware UPSERT.
7. Apply tombstones for delete events.
8. Commit target changes and progress/checkpoint in the same transaction/chunk.
9. Never ack the source before corresponding data is durable.
10. Run count, key, version, and checksum reconciliation.
11. Mark reconciled only after policy checks pass.
12. Use idempotency/outbox for external side effects.

## 50. Test Matrix for Ingestion and Export

| Scenario | What to verify | Expected outcome |
| --- | --- | --- |
| Send same batch twice | Batch key/checksum | One logical batch, no duplication |
| Same batch key, different checksum | Identity conflict | Rejected/quarantined |
| Same row number, different payload | Raw landing integrity | Conflict, not silently ignored |
| Same record/version/hash | Duplicate | One logical target state |
| Same record/version, different hash | Source conflict | Quarantine/incident |
| Old version arrives after newer version | Version gate | Target does not regress |
| High-version delete, late old insert | Tombstone | Does not resurrect |
| Crash mid-COPY | Raw/staging transaction | Retry does not duplicate |
| Crash after commit before response | Commit ambiguity | Re-read ledger, replay safe |
| Crash after raw commit before broker ack | At-least-once | Duplicate delivery deduplicated |
| Already-applied chunk resent | Chunk ledger | Not misapplied again |
| Two workers claim same batch | Locks/lease/fencing | One worker commits valid ownership |
| Lease expires while old worker runs | Fencing | Stale worker is rejected |
| Snapshot missing a page | Manifest/count | Delete reconciliation does not run |
| Incremental batch missing a key | Semantics | Absence not treated as delete |
| Source/target counts match, keys differ | Anti-join | Missing/extra detected |
| Counts match, payloads differ | Hash/version | Mismatch detected |
| Old schema parser | schema_version | Correct parser selected or quarantined |
| Different decimal/timezone format | Canonicalization | Compared accurately per contract |
| Partial row errors | Partial acceptance policy | Accurate quarantine and accounting |
| Outbox publish retry | Event ID | Idempotent consumer |
| Export retry | Export ID/checksum | Logical file unchanged |
| Export while target changes | Snapshot | File reflects one consistent snapshot |
| Network failure near COMMIT | Unknown outcome | Reconcile by key, no blind retry |

## 51. Production Operations Checklist

| Question | What to ensure |
| --- | --- |
| Is the batch key stable? | Same logical batch receives the same identity |
| Is the record key stable? | Unique within source/tenant scope |
| Is there a source version/ordering contract? | Out-of-order events handled properly |
| Is there a batch payload checksum? | Same key with different content detected |
| Is there raw landing? | Replay and audit evidence |
| Does raw keep original bytes when needed? | File object + checksum/URI |
| Is there typed staging? | Validated before hitting target |
| Is there quarantine? | Errors are never lost |
| Is the duplicate policy explicit? | Same hash vs conflict treated differently |
| Are unique constraints in place? | Race-safe target identity |
| Does UPSERT have a version gate? | No overwriting by stale events |
| Do deletes use tombstones? | No resurrection |
| Is tombstone retention long enough? | Exceeds replay/late-event window |
| Are checkpoint semantics clear? | Raw persisted vs target applied |
| Do data and checkpoints commit together? | When in the same DB |
| Do external acks follow at-least-once? | Duplicate delivery is safe |
| Is atomic vs chunked batch chosen? | Fits volume and business semantics |
| Do chunks have identity and ledger? | Resumes exact range |
| Does worker concurrency use claim/lease? | No uncontrolled duplicate processing |
| Do leases have fencing/ownership checks? | Stale workers cannot keep writing |
| Does reconciliation check counts + keys + values? | Never just COUNT |
| Are checksums canonical? | Both sides hash the same representation |
| Do full snapshots have completion manifests? | Never delete from partial snapshots |
| Is incremental absence never treated as delete? | Yes |
| Is rejected/duplicate/stale accounting clear? | Counts never double-counted |
| Does outbox have unique event IDs? | Safe publish retries |
| Are downstream consumers idempotent? | No duplicate side effects |
| Do exports use stable snapshots/cursors? | Consistent files |
| Do export manifests include checksum/count? | Verifiable by consumers |
| Is schema evolution versioned? | Correct parser selected |
| Is data normalization contracted? | Clear NULL/decimal/timezone/Unicode rules |
| Does the importer use least privilege? | Never superuser |
| Are raw/quarantine retention and access controlled? | Meets privacy/compliance needs |
| Are there failure-injection tests? | Crash/duplicate/network/lock |
| Are there metrics for batch age/retry/lag? | Early alerting |
| Is there a mismatch runbook? | Never blindly delete or patch |
| Are backup/restore tested? | Recovery does not rely solely on replay |
| Is reprocessing approval audited? | Controlled production replays |

## 52. Summary

Designing rerunnable and reconcilable data ingestion is about building **identity, transaction boundaries, progress records, and independent verification** across the entire pipeline.

Key principles:

1. **At-least-once delivery is the practical reality.** Assume files and messages can be resent.
2. **Batch keys and record keys must be stable.** Never use receive timestamps or row numbers as business identity.
3. **Same batch key with a different checksum is a conflict.** Never silently overwrite an already-received batch.
4. **Keep raw payloads and staging.** Separate ingestion receipt, parsing, validation, and business merging.
5. **Unique constraints are the last line of defense.** `ON CONFLICT` must pair with payload and version checks.
6. **UPSERT must respect source ordering.** Older events must never overwrite newer versions.
7. **Tombstones protect delete semantics.** Do not let stale events recreate deleted records.
8. **Checkpoints advance only after the corresponding data is durable.** Whenever possible, commit data and checkpoints in the same transaction.
9. **Chunk identity must be stable.** Each chunk's progress and target changes commit together.
10. **Leases do not automatically block stale workers.** Use fencing/ownership checks and idempotent writes.
11. **Reconciliation is more than row counts.** Check keys, versions, hashes, aggregates, and source scope.
12. **Use absence for deletion only with a complete full snapshot.** Incremental feeds never prove a record disappeared.
13. **Same key/version with different payload must be handled as a conflict.** Never pick a winner arbitrarily.
14. **Outbox bridges DB transactions with publish intent.** Downstream still needs deduplication because delivery can repeat.
15. **Exports need snapshots and manifests.** Retrying the same export identity must produce the same logical dataset.
16. **Canonicalization must be explicit.** Timezone, numeric, NULL, Unicode, and JSON semantics directly affect checksums.
17. **Partial acceptance requires clear accounting.** Quarantined/rejected rows must not vanish from totals.
18. **Raw data needs retention and access controls.** Replayability does not mean keeping sensitive data forever.
19. **Test crashes right after commit before response.** This scenario easily causes duplicates on blind retries.
20. **Mark a batch reconciled only after invariants pass.** `applied` and `reconciled` are two separate states.

Mental model when designing an ingestion pipeline:

```text
Identity: batch key + record key + source version
       |
Raw: persist payload + checksum
       |
Validate: typed staging + quarantine
       |
Deduplicate: same event vs conflicting payload
       |
Apply: unique constraint + version-aware UPSERT
       |
Progress: commit checkpoint with data
       |
Reconcile: counts + keys + versions + hashes
       |
Publish: outbox/idempotent downstream
       |
Replay: same identity, same result
```

**Final review question:** "If the process crashes right before commit, right after commit, or before the source receives ACK; if the same batch arrives a third time; if an older event arrives after a newer event; and if a snapshot is missing a part, can the system resume without losing, duplicating, or wrongly deleting data?" Only when that answer is proven by keys, constraints, transaction boundaries, and reconciliation records is the pipeline truly safe to rerun.
