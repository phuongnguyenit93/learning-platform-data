# Projection and Reducing Data Transferred to the Application in Apache Cassandra

## Learning Objectives

After this lesson, you will be able to:

1. Explain **projection** in CQL `SELECT`: retrieving only the needed columns and expressions instead of fetching entire rows by default.
2. Compare `SELECT *` with an explicit column-list `SELECT` tailored to UI/API needs.
3. Distinguish **partitions read**, **result rows**, **columns returned**, and **bytes transferred to the client**.
4. Combine projection with partition keys, clustering ranges, `LIMIT`, and pagination—retaining enough key columns to build lossless cursors.
5. Understand the difference between reducing network payload and reducing internal disk I/O, CPU, tombstone scans, or replica overhead.
6. Apply prepared statements and typed getters in Java Driver 4.x, avoiding reading, decoding, or retaining unneeded large fields.
7. Decide when to split list/detail tables or offload large payloads to external object storage.

This lesson belongs to the **SELECT and Paging** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. In Apache Cassandra, a distributed wide-column database, the partition key governs data location, clustering columns govern read order within a partition, and replication/consistency shape execution paths. Projection is an important **output** optimization for Java applications, yet it must go hand in hand with query-driven table design, pagination, and real measurements.

## 1. What Is Projection?

**Projection** is choosing **which columns or expressions appear in the `SELECT` result**.

Consider the same event set:

```sql
-- Fetch every column the table provides.
SELECT *
FROM events_by_account_day
WHERE account_id = ?
  AND event_day = ?;

-- Fetch only the columns the event list needs to display.
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = ?
  AND event_day = ?;
```

Key differences:

| Aspect | `SELECT *` | Explicit projection |
| --- | --- | --- |
| Result columns | All columns in the schema | Only the listed columns |
| Can return large `blob`/`text` fields | Yes | No, if omitted |
| Affected when schema adds columns | Response shape can change | More stable column contract |
| Potential to cut network payload | Suboptimal for narrow endpoints | Usually better |
| Changes partitions selected | No | **No** — governed by `WHERE` |
| Changes row ordering | No | **No** — governed by clustering order/`ORDER BY` |
| Guarantees cutting all disk I/O | No | **Cannot be guaranteed** |

For a list-view API, clients typically only need timestamp, event type, and a short summary. Fetching a detailed payload only for Java to discard it wastes bandwidth, decoding CPU, object allocations, and memory.

> Rule: **put display fields in projection**, and **put data-locating predicates in `WHERE`**. Both parts do different jobs.

## 2. CQL Lab: Short Fields and Large Fields on the Same Row

Suppose a product logs activity history per account and day. The list view needs only a few fields, whereas the detail view needs extended attributes and raw binary content.

### 2.1. Creating the Keyspace and Table

```sql
-- Single-node lab; SimpleStrategy and RF=1 are not recommended
-- configurations for multi-node/datacenter production environments.
CREATE KEYSPACE IF NOT EXISTS cassandra_projection_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_projection_lab;

CREATE TABLE IF NOT EXISTS events_by_account_day (
    account_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    summary text,
    attributes map<text, text>,
    raw_payload blob,
    PRIMARY KEY ((account_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

Column roles:

| Column | Type | Role in queries |
| --- | --- | --- |
| `account_id`, `event_day` | Composite partition key | Together locate one partition and its replicas. |
| `occurred_at`, `event_id` | Clustering columns | Identify and order events within the partition. |
| `event_type` | Regular column | Event type name for display. |
| `summary` | Regular column | Short description for list views. |
| `attributes` | Collection column | Extended metadata map; not needed on every screen. |
| `raw_payload` | `blob` column | Raw binary content; easily grows large in real data. |

**Modeling note:** Every row sharing `(account_id, event_day)` lives in the same partition. Selecting only `event_type` does not grant direct access to "all `VIEW` events system-wide" without a tailored access path for that column.

### 2.2. Loading Small Sample Data with Duplicate Timestamps

```sql
-- Account A, Nov 20: four rows in the same partition.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id,
     event_type, summary, attributes, raw_payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'LOGIN', 'Logged in',
    {'device': 'web', 'source': 'browser'},
    0x01020304
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id,
     event_type, summary, attributes, raw_payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000002,
    'VIEW', 'Viewed order details',
    {'device': 'mobile', 'source': 'app'},
    0x05060708
);

-- Another row at the same 10:00 timestamp with a different event_id.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id,
     event_type, summary, attributes, raw_payload)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000003,
    'CLICK', 'Opened checkout page',
    {'device': 'mobile'},
    0x090a0b0c
);

-- Intentionally omit attributes and raw_payload on this row.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 11:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'PAY', 'Payment succeeded'
);

-- Account A, Nov 21: another partition.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 08:00:00+0000',
    00000000-0000-4000-8000-000000000005,
    'LOGIN', 'Logged in next day'
);

-- Account B, Nov 20: third partition.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-20', '2026-11-20 07:00:00+0000',
    00000000-0000-4000-8000-000000000006,
    'LOGIN', 'Logged in account B'
);
```

Summary:

| Partition key | Rows | Order within partition |
| --- | ---: | --- |
| Account A, Nov 20 | 4 | 11:00/id4, 10:00/id3, 10:00/id2, 09:00/id1 |
| Account A, Nov 21 | 1 | 08:00/id5 |
| Account B, Nov 20 | 1 | 07:00/id6 |
| **Entire lab** | **6** | **3 partitions** |

The `INSERT` statements use fixed full primary keys; re-running on the same table performs upserts without creating duplicate rows. Expected results assume no other writes or deletes. Payloads in the lab are only four bytes long for easy CQL testing; in reality, binary fields can be much larger and need size policies.

## 3. Comparing SELECT * and Projection with Concrete Results

### 3.1. SELECT * Returns Every Defined Column

```sql
SELECT *
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

CQL returns `account_id`, `event_day`, `occurred_at`, `event_id`, `event_type`, `summary`, `attributes`, and `raw_payload` for all **four rows** in partition A / Nov 20.

For the `PAY` row, `attributes` and `raw_payload` were not written; in the result they are represented as `null`. Even when `null`, metadata and result framing still incur overhead. For the other rows, `SELECT *` drags along binary fields that the list screen does not need.

### 3.2. SELECT Only Columns Needed for the List Screen

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

Logical result:

| `occurred_at` UTC | `event_id` (suffix) | `event_type` | `summary` |
| --- | --- | --- | --- |
| 11:00 | `...0004` | `PAY` | Payment succeeded |
| 10:00 | `...0003` | `CLICK` | Opened checkout page |
| 10:00 | `...0002` | `VIEW` | Viewed order details |
| 09:00 | `...0001` | `LOGIN` | Logged in |

It is still **one partition and four rows**. What changed is the **shape of each returned row**:

- `account_id` and `event_day` are omitted if the endpoint already fixed both in the request and does not need to repeat them per row.
- `attributes` and `raw_payload` are omitted.
- `occurred_at` and `event_id` are retained because they are needed for **ordering and pagination cursors**.

This is a clean output contract for a list API. In another endpoint that merges multiple tenants/days or queries multiple buckets, retain the relevant key columns so each row can be tied to its partition.

### 3.3. Selecting a Single Column Does Not Change Read Scope

```sql
SELECT event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

This query still returns **four result rows**, each containing one `event_type` value. Cassandra does not automatically run `DISTINCT` just because you select one column, nor does it collapse output to **one row**.

To return fewer **rows**, use key predicates, clustering ranges, and `LIMIT`. To return fewer **columns**, use projection. To touch fewer **partitions**, specify the exact partition key in `WHERE`.

## 4. Three Layers of Data Reduction: Partition, Row, and Column

In Cassandra, optimize in this order of thought:

| Layer | Question | CQL Tool | Primary reduction |
| --- | --- | --- | --- |
| **Partition** | Which partitions are read? | Full partition key, finite `IN` list | Distributed scope, replica/token fan-out |
| **Row** | Within a partition, which rows are fetched? | Clustering range, `LIMIT`, `PER PARTITION LIMIT` | Rows matched/returned |
| **Column** | For each row, which fields are needed? | Column list in `SELECT` | Values and bytes returned |

Example combining all three:

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 09:30:00+0000'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 2;
```

What each part does:

1. `account_id = ... AND event_day = ...` targets **one partition**.
2. `occurred_at >= 09:30` bounds candidate rows within the partition via a clustering column.
3. `ORDER BY ... DESC` selects traversal direction along the schema's clustering order.
4. `LIMIT 2` returns **at most the first two rows** in that order.
5. Projection returns only **four columns**, omitting `attributes` and `raw_payload`.

On the sample data, the two rows returned are **PAY 11:00** and **CLICK 10:00/id3**. **VIEW 10:00/id2** is omitted because of `LIMIT 2`, even though its timestamp falls within the range.

**Do not confuse:** `LIMIT 2` does not guarantee the storage engine reads only two physical cells. With TTLs or tombstones, scanning and reconciliation may still process more items than the returned rows.

## 5. Estimating Network Payload: Rows × Column Sizes

To inform design decisions, estimate relative scale:

```text
Raw result bytes (estimate)
  ≈ sum across result rows [
        size of selected column values
        + encoding / null / protocol overhead
    ]

Total response time also depends on:
  + read and filter work at replicas
  + coordinator / consistency coordination
  + serialization, compression, network transfer, deserialization
  + DTO mapping / HTTP response serialization
```

### 5.1. Illustrative Example with a Large Blob Field

Suppose in production data, a list page contains **500 rows** and:

- List fields total roughly **150 bytes/row** (excluding overhead).
- `raw_payload` averages **3,000 bytes/row**.

Compare selected value sizes:

| Retrieval approach | Estimated value bytes |
| --- | ---: |
| List projection: `500 × 150` | **75,000 bytes** |
| Including `raw_payload`: `500 × (150 + 3,000)` | **1,575,000 bytes** |
| Difference saved by omitting payload from result | **1,500,000 bytes** |

These numbers illustrate **logical value bytes**, not exact bytes on the wire. Cassandra's native protocol adds framing overhead and may apply compression; actual wire size depends on value types, encoding, network, page size, and driver configuration. Still, the example shows why **dropping one large column** saves far more than trimming a few bytes off tiny columns.

### 5.2. Value of Dropping Columns Before Java Receives Them

If a Java API does:

```text
SELECT * -- fetches both blob and map
     |
     v
Row in Java driver
     |
     v
DTO keeping only occurred_at, event_id, event_type, summary
     |
     v
List HTTP JSON
```

discarding `blob` **after** receiving it does not eliminate the cost of transmitting it from Cassandra to the driver. Projection must be placed **in CQL**:

```text
SELECT occurred_at, event_id, event_type, summary
     |
     v
Row containing only selected columns
     |
     v
DTO / List HTTP JSON
```

Cassandra does not necessarily read proportionally fewer disk blocks for every byte omitted from the response; the storage engine may still read row metadata, check tombstones, or inspect adjacent data. **Network payload**, **deserialization CPU**, and **client memory footprint** are usually the clearest benefits and should be measured directly.

### 5.3. SELECT * Also Makes API Contracts Fragile

Suppose the schema is later altered:

```sql
ALTER TABLE events_by_account_day
ADD debug_trace text;
```

If code uses `SELECT *`, the new column arrives in the CQL result set even if the DTO/API does not need it. When schemas evolve or internal fields are added, explicit projection keeps **unneeded data** from reaching the application layer. However, projection **never replaces** access control, sensitive-data handling, and logging restrictions.

## 6. Which Columns to Select for Lists vs. Details?

An API may have two distinct read paths:

| Endpoint | Required columns | Reason |
| --- | --- | --- |
| `GET /accounts/{id}/events?day=...` | `occurred_at`, `event_id`, `event_type`, `summary` | Render list and build cursor |
| `GET /accounts/{id}/events/{eventId}?day=...&at=...` | Above columns, `attributes`, `raw_payload` | Display/read full details |

### 6.1. List Query

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 20;
```

`raw_payload` is omitted by default because the screen only needs summaries.

### 6.2. Detail Query by Full Primary Key

```sql
SELECT occurred_at, event_id, event_type, summary, attributes, raw_payload
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 10:00:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000003;
```

This is a **full primary-key lookup**, returning at most one row. Details are loaded **only when the user opens a record**, not for every item in the list.

If you only have `event_id` without `account_id`, `event_day`, or `occurred_at`, the current table **does not** support point lookups by `event_id` alone. The application must carry the full key from the list/cursor or maintain a separate lookup path. Projection does not alter key rules.

### 6.3. When Should Payloads Be Split into Another Table or Store?

If `raw_payload` is huge or rarely needed, one design option is:

```sql
-- Read table dedicated to list views: no blob column.
CREATE TABLE IF NOT EXISTS event_headers_by_account_day (
    account_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    summary text,
    PRIMARY KEY ((account_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);

-- Table dedicated to details with the same full primary key.
CREATE TABLE IF NOT EXISTS event_details_by_account_day (
    account_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    attributes map<text, text>,
    raw_payload blob,
    PRIMARY KEY ((account_id, event_day), occurred_at, event_id)
);
```

These are **two new empty tables**; creating them does not copy rows from the original table. The application/pipeline must write, delete, apply TTLs, and backfill both tables under chosen idempotency and consistency policies.

Trade-offs:

- **Pros:** List queries cannot carry payload columns even if someone accidentally selects all columns from the list table.
- **Cons:** Higher write/storage cost, and keeping two tables perfectly in sync when one write fails requires retries and reconciliation.
- For very large payloads, consider storing blobs in **object storage** and keeping metadata/references in Cassandra rather than treating Cassandra as an unbounded blob store. Manage access permissions, URLs/keys, TTLs, and object cleanup carefully.

Do not split tables just because a schema has one large column: **explicit projection on the same table may already meet** your API's network budget. Base table-splitting decisions on measured read, update, and operational costs.

## 7. Projection and Paging: Keep Enough Keys to Resume

Projection chooses which columns are returned, while a **keyset cursor** requires values from the clustering columns defining sort order. If an endpoint projects too few columns, it may be unable to build a safe cursor.

### 7.1. Duplicate Timestamp Example

In partition account A / Nov 20, the default `(occurred_at DESC, event_id DESC)` order is:

```text
11:00 / event 0004 / PAY
10:00 / event 0003 / CLICK
10:00 / event 0002 / VIEW
09:00 / event 0001 / LOGIN
```

Page one fetches two rows:

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 2;
```

Results are `PAY/0004` and `CLICK/0003`. The cursor for the next page needs **both columns** `occurred_at` and `event_id` from the last row:

```text
lastCursor = (2026-11-20T10:00:00Z, ...0003)
```

Next page:

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (occurred_at, event_id) < (
      '2026-11-20 10:00:00+0000',
      00000000-0000-4000-8000-000000000003
  )
ORDER BY occurred_at DESC, event_id DESC
LIMIT 2;
```

Next rows returned are `VIEW/0002` then `LOGIN/0001`. The tuple predicate excludes the exact last key of the previous page while preserving the remaining event sharing the same timestamp.

If projection only selects `event_type` and `summary`:

```sql
-- Can display data, but lacks sufficient info
-- to build a clustering-key cursor at the application layer.
SELECT event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
LIMIT 2;
```

then Java lacks `occurred_at` and `event_id` to mark the page end. **Never sacrifice cursor keys just to save a few bytes**, unless using a separate pagination mechanism with safe state storage.

### 7.2. Driver Paging State vs. Keyset Cursor

The Java Driver provides `setPageSize(n)` and paging state to continue fetching **the exact same CQL query**. With that mechanism, the application does not necessarily have to expose all clustering keys in the HTTP response to fetch the next page; however:

- Paging state must stay tied to the matching query and bind values—never apply it to a new projection or modified `WHERE` clause arbitrarily.
- Paging state cannot be fabricated or edited, and may break across incompatible query/schema changes.
- State does not provide an immutable snapshot across reads when writes, deletes, or TTL expirations occur.
- If sent to a client, bind paging state to authorization scope and protect its integrity to prevent tampering or cross-tenant token reuse.

Do not mistake **page size** for a total result limit. For example, `setPageSize(2)` fetches two rows in one page and continues fetching subsequent pages until the query finishes.

### 7.3. Multiple Partitions and IN Lists

```sql
SELECT account_id, event_day, occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21');
```

Because `event_day` is the last component of the composite partition key, this query targets **two candidate partitions**, holding five rows total in the lab. Here projection includes `event_day` because the application needs to know which day each row belongs to. Still:

- There is **no global chronological order** merely from each partition's clustering order.
- Selecting fewer columns does not reduce the number of partitions listed in `IN`.
- If events must be merged chronologically across multiple days, the application needs a merge/cursor strategy or a table modeled for that query.

## 8. Does Projection Reduce Disk I/O, CPU, and Tombstone Scans?

The accurate answer is: **it can reduce certain costs, with no linear guarantee or universal applicability**.

### 8.1. Where Projection Typically Helps

| Cost source | Potential benefit |
| --- | --- |
| Bytes Cassandra sends to Java | Usually drops significantly when dropping long strings or `blob` columns. |
| CQL protocol encode/decode CPU | Can drop when fewer values are processed. |
| Driver/DTO/HTTP layer memory | Can drop because less data is held and converted. |
| Inter-service network traffic | Can drop if the API response also omits unnecessary fields. |
| Stability across schema additions | Explicit projection keeps the query contract intact. |

### 8.2. Where Projection Cannot Replace Other Optimizations

| Cost source | Why changing `SELECT *` alone is not enough |
| --- | --- |
| Many partitions in `WHERE` | Projection does not change token hashing or replica fan-out. |
| Filtering by regular column | Does not create an index or fix broad `ALLOW FILTERING` scans. |
| Reading a huge partition | Requires clustering ranges, paging, bucketing, or redesign. |
| Tombstones/TTLs and reconciliation | Storage engine must still determine which rows are live. |
| Compaction/repair and SSTable read amplification | Returning fewer columns does not eliminate background storage work. |
| High consistency or slow replicas | Must evaluate topology, replicas, timeouts, and load. |
| Full-table `COUNT(*)` | Aggregates must still evaluate the counted row set despite returning one cell. |

Never claim "dropping 80% of columns makes queries five times faster." On tiny tables or workloads dominated by partition lookups/tombstones, savings may be modest. When large payloads saturate the network, savings can be dramatic. **Measure**, rather than extrapolating from column counts.

### 8.3. SELECT JSON Does Not Automatically Shrink Results

CQL can serialize rows directly as JSON:

```sql
SELECT JSON occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

`SELECT JSON` alters **output serialization**: columns are encoded into a JSON string. It does not select fewer rows or columns by itself, and JSON adds overhead from key names and escaping. If an API already maps Java DTOs to HTTP JSON, benchmark whether pushing JSON serialization to Cassandra helps; never assume it compresses payloads.

Similarly, `AS` aliases:

```sql
SELECT occurred_at AS event_time,
       event_id,
       event_type,
       summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

give readable result names without **shrinking value byte sizes**. Complex expressions, functions, or user-defined functions in projections can add CPU overhead; use them only when serving an actual requirement.

## 9. Java Driver: Prepared Statements and Lean DTOs

Examples use **Apache Cassandra Java Driver 4.x** with Java 17. Assume an active `CqlSession session` connected to keyspace `cassandra_projection_lab`.

### 9.1. List Read Path

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

// Assumes an active CqlSession session connected to cassandra_projection_lab.
UUID accountId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);
LocalDate day = LocalDate.parse("2026-11-20");

PreparedStatement listQuery = session.prepare("""
    SELECT occurred_at, event_id, event_type, summary
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
    ORDER BY occurred_at DESC, event_id DESC
    LIMIT ?
    """);

int requestedLimit = 20;
int safeLimit = Math.max(1, Math.min(requestedLimit, 100));
BoundStatement bound = listQuery.bind(accountId, day, safeLimit)
    .setPageSize(50);

ResultSet result = session.execute(bound);
for (Row row : result) {
    Instant time = row.getInstant("occurred_at");
    UUID eventId = row.getUuid("event_id");
    String type = row.getString("event_type");
    String summary = row.getString("summary");
    System.out.printf("%s %s %s %s%n", time, eventId, type, summary);
}
```

Key points:

- `SELECT` lists only **four columns**; the driver never receives `raw_payload` even though the table contains it.
- `LIMIT ?` uses a bind marker—never concatenate user input into CQL.
- `setPageSize(50)` configures **fetch size**, not a substitute for `LIMIT 20`. With four sample rows, the query returns four rows.
- `getInstant` matches CQL `timestamp`, `getUuid` matches `uuid`, and `getString` matches `text`.
- Iterating over `ResultSet` is shown for illustration; in production APIs, map rows into DTOs containing only fields defined by the endpoint contract.

Never run `SELECT *` and then only call `row.getString("summary")`: getters extract fields **only after the driver has already received the full result set**.

### 9.2. Detail Read Path

```java
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.util.UUID;

PreparedStatement detailQuery = session.prepare("""
    SELECT occurred_at, event_id, event_type, summary,
           attributes, raw_payload
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
      AND occurred_at = ?
      AND event_id = ?
    """);

BoundStatement detailBound = detailQuery.bind(
    accountId,
    day,
    Instant.parse("2026-11-20T10:00:00Z"),
    UUID.fromString("00000000-0000-4000-8000-000000000003")
);

Row detail = session.execute(detailBound).one();
if (detail != null) {
    String detailType = detail.getString("event_type");
    String detailSummary = detail.getString("summary");
    // Only when the endpoint genuinely needs them: read attributes/raw_payload
    // using exact CQL types and check size limits before use.
    System.out.printf("%s: %s%n", detailType, detailSummary);
}
```

If `raw_payload` can hold sensitive data, including it in the **detail endpoint's** projection does not automatically mean the caller is authorized to view it. Account/event authorization, logging redaction, and data protection policies remain mandatory.

### 9.3. Paging with a Keyset Cursor

Within one partition on a `DESC, DESC` schema, prepare the continuation query:

```java
PreparedStatement nextPage = session.prepare("""
    SELECT occurred_at, event_id, event_type, summary
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
      AND (occurred_at, event_id) < (?, ?)
    ORDER BY occurred_at DESC, event_id DESC
    LIMIT ?
    """);

BoundStatement nextBound = nextPage.bind(
    accountId,
    day,
    Instant.parse("2026-11-20T10:00:00Z"),
    UUID.fromString("00000000-0000-4000-8000-000000000003"),
    2
);
```

The statement keeps `occurred_at` and `event_id` in the projection **precisely because those two columns form the cursor**. In production, validate that the cursor belongs to the authorized account/day, sign or encrypt it to prevent tampering, and enforce access limits.

### 9.4. Measuring Payload and Latency in the Application

Never rely solely on single-request microbenchmarks. When comparing projections:

1. Run **the exact same partition set, `WHERE`, `LIMIT`, and consistency level** for both query versions.
2. Use production-like data distributions: realistic `blob` sizes, large and small partitions, and concurrent load.
3. Track response bytes or network throughput where measurable, plus deserialization and JSON serialization times.
4. Watch p50/p95/p99 latency, timeouts, GC/heap usage, and throughput under rising concurrency.
5. Account for hot/cold caches, compaction, repair, tombstones, and retries.
6. Confirm the API does not accidentally drop fields needed for cursors, auditing, or downstream logic.

Available metrics depend on your Java driver version, monitoring stack, and Cassandra release. Never claim an exact byte count from `row.getColumnDefinitions().size()`: column count is only **field count**, not a substitute for measuring serialized value sizes.

## 10. Projection and Read/Write Consistency

Projection does not alter consistency-level semantics. Running `SELECT occurred_at, event_id, event_type` at `LOCAL_ONE` vs. `LOCAL_QUORUM` (in a properly replicated cluster) still differs in how many replicas must respond and what data is observed when writes have not yet converged.

Points to understand:

- **Replication factor** does not multiply output rows by the number of replicas. Results represent logical table rows, not one copy per replica.
- **Consistency level** chooses read guarantees and required acknowledgments; projection cannot fix slow or unreachable replicas.
- **TTLs and tombstones:** omitting `raw_payload` trims output, yet does not eliminate every cost of checking expired/deleted records.
- **Compaction and repair:** affect data fragmentation, reconciliation, and read latency; they cannot be replaced simply by trimming `SELECT` columns.
- **Paging state:** paginated reads never yield an immutable snapshot, regardless of how few or many columns are projected.

If an endpoint is slow due to broad reads, verify key access paths, partition sizes, tombstones, and replica health **before** blaming network payload. Conversely, if an endpoint is slow due to giant blobs or maps, projection is a low-cost, clean win.

## 11. Common Mistakes

| Misconception or practice | Issue | Fix |
| --- | --- | --- |
| `SELECT *` then drop columns in Java DTO | Data was already transmitted from Cassandra to the driver. | Apply projection directly in CQL. |
| "Selecting one column reads only one partition." | Partitions are determined by `WHERE`, not projection. | Supply the full partition key appropriately. |
| "Selecting fewer columns makes `ALLOW FILTERING` fast." | May still scan many rows/partitions to find matches. | Design a table/index or bound the clustering range. |
| "`LIMIT 20` guarantees reading at most 20 cells." | Tombstones, TTLs, filtering, and reconciliation may inspect far more. | Distinguish output size from internal read work. |
| "`setPageSize(20)` equals `LIMIT 20`." | Page size only splits fetch round trips. | Use `LIMIT` for total cap; page size for fetch chunking. |
| "Omit all key columns from `SELECT` and still keyset-paginate." | No end-of-page key values remain to construct the cursor. | Retain the clustering columns defining deterministic order. |
| "`SELECT JSON` is always smaller than regular `SELECT`." | JSON adds key-name and escaping overhead plus serialization CPU. | Benchmark on real data and native protocol. |
| "`SELECT event_type` returns unique event types." | Returns one value **for every row** read. | Use a valid `DISTINCT`/grouping query or dedicated table. |
| "Adding a new column does not affect `SELECT *` callers." | Result sets change shape and grow payloads. | List columns explicitly per API contract. |
| "Projection makes full-table `COUNT(*)` O(1)." | Aggregates still evaluate the counted row set. | Scope `WHERE` or maintain summary tables. |
| "Only `event_id` is needed to fetch details." | The schema's full key also includes account, day, and timestamp. | Pass the full key or add a dedicated event-ID lookup table. |
| "Not returning the blob in HTTP means it never leaves Cassandra." | If CQL runs `SELECT *`, the blob is still sent to the driver. | Select the blob only in the detail query. |

## 12. Practice Exercises and Answers

### Exercise 1. Writing a List-View Projection

**Task:** Account A on Nov 20 needs timestamp, event ID, type, and summary—no blob or map. Write a query for at most the three newest events.

**Answer:**

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

Results are `PAY/0004`, `CLICK/0003`, and `VIEW/0002`. The query touches **one partition**, returning **three rows** and **four columns per row**.

### Exercise 2. Projection Does Not Reduce Partition Count

**Task:** For account A, query both `2026-11-20` and `2026-11-21`, selecting only `event_type`. How many candidate partitions and how many rows are returned in the lab?

**Answer:**

```sql
SELECT event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21');
```

There are **two candidate partitions**, returning **five rows total** on the sample data. Selecting one column neither turns the query into a single-partition read nor deduplicates event types.

### Exercise 3. Why Retain event_id for Cursors?

**Task:** Page one fetches the two newest rows for account A on Nov 20, ending at `10:00/id3`. Can you store only `occurred_at = 10:00` and use `occurred_at < 10:00` for the next page?

**Answer:** No. That would skip `VIEW/0002`, which also occurred at `10:00`. Use the descending tuple boundary `(occurred_at, event_id) < (10:00, id3)` and keep both columns in the projection.

### Exercise 4. Estimating Payload

**Task:** An endpoint returns 500 rows; list fields average 150 bytes/row, while `raw_payload` adds 3,000 bytes/row. Roughly how many logical value bytes are saved by omitting the payload?

**Answer:** `500 × 3,000 = 1,500,000 bytes`. This is an estimate of raw value bytes before protocol/compression overhead, not exact wire measurements. Benchmark to observe actual changes in p95/p99 latency and throughput.

### Exercise 5. Is SELECT JSON Always Better?

**Task:** A Java API converts short columns into HTTP JSON. Should every CQL query automatically switch to `SELECT JSON` to save bandwidth?

**Answer:** No. `SELECT JSON` changes serialization format, adding key names and escaping that can enlarge results or shift CPU work. Explicitly projecting needed columns and measuring real payloads comes first; use JSON in CQL only when a concrete need and benchmarks justify it.

### Exercise 6. Fetching Details When a User Opens a Row

**Task:** A user selects `CLICK/0003` at 10:00 on Nov 20 for account A. Which query fetches details for only that single event?

**Answer:**

```sql
SELECT occurred_at, event_id, event_type, summary, attributes, raw_payload
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 10:00:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000003;
```

It supplies the **full primary key**, so at most one row is returned; the detail projection may include map/blob because the endpoint genuinely needs them. Do not use `SELECT *` for the entire list view merely because one item might be opened later.

### Exercise 7. When Reducing Columns Is Not Enough

**Task:** A query has `WHERE event_type = 'VIEW' ALLOW FILTERING` without a partition key. The API switches from `SELECT *` to `SELECT event_type` and sees lower network traffic; can we conclude all wide-scan risks are gone?

**Answer:** No. Projection reduces returned bytes, yet filtering on a regular column can still force scanning many partitions and rows. Design a key- or index-backed access path and measure fan-out, tombstones, and latency.

## 13. Projection Checklist for Cassandra APIs

1. **Endpoint contract:** Which fields does the client truly need? Can list and detail paths be separated?
2. **Partition:** Does `WHERE` specify the full partition key or a finite partition list? Is fan-out bounded?
3. **Row:** Are clustering ranges, valid `ORDER BY`, `LIMIT`, and pagination policies clearly defined?
4. **Column:** Does the query use explicit projection, avoiding `SELECT *` on hot read paths?
5. **Cursor:** Are the columns needed for end-of-page keys—especially timestamps and tie-breaker IDs—included in the projection when using keyset paging?
6. **Large payloads:** Are `blob`/collection/map fields loaded only when needed? Should tables be split or blobs offloaded to object storage?
7. **Measured impact:** Have you measured transferred bytes, deserialization, heap/GC, p95/p99 latency, and throughput under identical `WHERE`, `LIMIT`, consistency, and datasets?
8. **Distributed behavior:** Are you separating payload savings from tombstone/TTL, compaction, repair, replication, and consistency costs?
9. **Java:** Are prepared statements and typed getters accurate, and are unbounded result buffers avoided?
10. **Security and schema evolution:** Are sensitive fields excluded from projections, logs protected, authorization enforced, and API contracts shielded from `SELECT *` surprises?

**Remember:** Projection reduces **columns and values returned**; `WHERE` reduces **partitions and rows searched**; `LIMIT` and paging control **result row/page counts**. All three must be designed together. In Cassandra, a well-crafted `SELECT` not only returns accurate data—it **avoids transmitting fields the application does not need**, preserves pagination keys, and avoids unpredictable distributed scans.

## References

- [Apache Cassandra Documentation — CQL Data Manipulation: SELECT, WHERE, ORDER BY, LIMIT](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — CQL Data Definition: PRIMARY KEY and CLUSTERING ORDER](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [Apache Cassandra Java Driver 4.x — Prepared Statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/index.html)
- [Apache Cassandra Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
