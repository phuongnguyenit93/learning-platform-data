# uuid, timeuuid, and Identifier vs. Ordering Requirements in Apache Cassandra

In **Apache Cassandra**, `uuid` and `timeuuid` are both 128-bit identifier types, yet they serve two different goals. `uuid` represents **a general UUID identifier**; `timeuuid` represents a **UUID version 1 (v1)** carrying a timestamp component that Cassandra compares chronologically when used as a *clustering column*. Choose the type based on the business question: do you need to identify a stable entity, or do you need to both distinguish events and retrieve them in ID-generation order?

This lesson belongs to the **Data Types** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. The concepts sit within the distributed wide-column model: the **partition key** determines where rows are distributed, and **clustering columns** determine sort order *within a partition*. CQL and Java Driver examples illustrate how UUID choices relate to query-driven table design, retries after timeouts, read/write consistency levels, replication, compaction, and repair.

## 1. Distinguishing Identification from Chronological Ordering

A problem often raises two requirements:

1. **Identification:** each customer or transaction needs a stable ID for lookups, updates, and deduplication on retries.
2. **Ordering:** for a given customer, fetch the 100 latest events or events within a time window.

These two requirements do not have to rely on the same column. A random ID works well for identification, whereas a `timestamp` column may be better suited for sorting by **when the event actually occurred**. `timeuuid` is useful when IDs are generated at the exact moment ordering represents and using a time-based key is acceptable.

| Criterion | `uuid` | `timeuuid` |
|---|---|---|
| Size | 128 bits (16 bytes) | 128 bits (16 bytes) |
| Semantics | General UUID identifier | Time-based UUID **v1** |
| CQL generator | `uuid()` generates a random UUID v4 | `now()` generates a UUID v1 using the coordinator's clock |
| Common Java generator | `UUID.randomUUID()` (v4) | `Uuids.timeBased()` in Java Driver 4.x (v1) |
| Java read/write | `UUID`, `getUuid`/`setUuid` | Also `UUID`, `getUuid`/`setUuid` |
| Suitable role | Account IDs, order IDs, entities, lookup keys | Clustering key for timelines/events ordered by ID generation time |
| Chronological ordering | **Not guaranteed**, especially for UUID v4 | Cassandra compares by the UUID v1 timestamp component |
| Can creation time be extracted? | Not a general property of all UUIDs | Can be converted to a timestamp at timestamp resolution |
| Pitfall to avoid | Assuming random UUIDs sort chronologically | Equating ID generation time with source event occurrence time |

**Note:** a UUID is an *identifier*, not a "cluster-wide auto-incrementing sequence" or an authorization mechanism. An unguessable ID does not replace authentication and access control checks.

## 2. UUID Structure and Key Versions

### 2.1. How to Read a UUID

A UUID is commonly displayed as 36 characters: 32 hexadecimal digits and 4 hyphens in the `8-4-4-4-12` format.

Example:

~~~text
550e8400-e29b-41d4-a716-446655440000
             ^
             4 -> version 4, random UUID
~~~

That string is only the **textual display** of a 16-byte binary value. When using a CQL `uuid`/`timeuuid` column, Cassandra stores the native UUID type rather than treating it as a 36-character `text` string.

In Java:

~~~java
import java.util.UUID;

UUID id = UUID.fromString("550e8400-e29b-41d4-a716-446655440000");

System.out.println(id.version());  // 4
System.out.println(id.toString()); // 8-4-4-4-12 format

UUID anotherId = UUID.randomUUID();
System.out.println(anotherId.version()); // 4
~~~

Java's `UUID.randomUUID()` generates a **UUID v4**; it fits a CQL `uuid` column. Do not pass it directly into a `timeuuid` column, because `timeuuid` requires UUID v1 format.

### 2.2. UUID v1 in timeuuid

UUID **version 1** contains a timestamp component, a **clock sequence**, and a node identifier component. The timestamp is encoded in **100-nanosecond intervals since October 15, 1582**, unlike the Unix epoch starting in 1970. The node component of a UUID v1 may be derived from network information or synthesized by a library's own algorithm; **never** treat it as a trusted host identity.

Example of a UUID v1:

~~~text
f47ac10b-58cc-11cf-a447-001122334455
             ^
             1 -> version 1
~~~

The timestamp embedded in UUID v1 allows chronological comparison **by ID generation time**. However:

- The 100-ns resolution of the **timestamp field** does not imply 100-ns accuracy of the physical clock or measurements.
- Clocks across hosts can skew; cluster-wide event history does not automatically form an absolute business order.
- If an event occurred at 09:00 but reached the system at 09:10, an ID generated on ingest carries **09:10**, not 09:00.
- A UUID v1 does not prove which host, user, or trusted source created it.

### 2.3. Other UUID Versions

UUID v4 uses random data; UUID v3/v5 are name- and namespace-based; newer UUID versions also exist in the ecosystem. However, for **Cassandra CQL `timeuuid`**, use **UUID v1** per the type contract. Never assume timestamped UUIDs from other standards, such as UUID v7, can be inserted straight into `timeuuid` or will sort identically to v1 in Cassandra.

If an external system issues UUIDs of another version, you may need to store them in **`uuid`** alongside a separate **`timestamp`** column for time-based queries; verify driver and cluster compatibility before ingesting external UUIDs.

## 3. CQL Functions for Generating UUID and timeuuid

Cassandra provides several commonly used built-in functions:

| CQL Function | Returns | Purpose |
|---|---|---|
| `uuid()` | Random `uuid` v4 | Generate a new entity ID |
| `now()` | `timeuuid` v1 | Generate an event ID at statement execution time |
| `current_timeuuid()` | `timeuuid` | Equivalent name for `now()` in current CQL documentation |
| `min_timeuuid(t)` | Minimum *sentinel* timeuuid at `t` | Lower bound when filtering by time range |
| `max_timeuuid(t)` | Maximum *sentinel* timeuuid at `t` | Upper bound when filtering by time range |
| `to_timestamp(timeuuid)` | `timestamp` | Extract the timestamp embedded in a timeuuid at timestamp resolution |
| `to_unix_timestamp(timeuuid)` | `bigint` | Extract the timestamp as Unix milliseconds |

Function names may appear in alternate forms across CQL versions/documentation, such as **`minTimeuuid`**/`maxTimeuuid` vs. **`min_timeuuid`**/`max_timeuuid`. Examples in this lesson use the underscore form per current CQL documentation; check the exact syntax of your deployed Cassandra version.

Example creating an entity with a random UUID:

~~~cql
CREATE TABLE accounts_by_id (
    account_id uuid PRIMARY KEY,
    account_name text,
    created_at timestamp
);

INSERT INTO accounts_by_id (account_id, account_name, created_at)
VALUES (uuid(), 'Test Customer', '2026-11-21T00:00:00Z');
~~~

Every execution of `uuid()` generates a brand-new ID. If this statement times out and the application re-runs it verbatim, **it can create two rows** instead of rewriting the same row. For idempotent write paths, the application should generate the ID **once**, persist it, and reuse that exact ID on retries.

`now()` also generates a new timeuuid on the coordinator at execution time. Never write:

~~~cql
-- NOT the way to find a record created earlier with now():
SELECT * FROM some_events WHERE event_id = now();
~~~

This function generates a fresh UUID at query time, so it will almost certainly never match an existing record's ID. To look up a known record, pass the **stored ID**; to query by time, use **timestamps** or **bounding timeuuid sentinels**.

## 4. uuid Is a Great Identifier Key, Not a Time-Sorting Key

Suppose the application needs to "fetch customer details by ID." A simple table:

~~~cql
CREATE TABLE customers_by_id (
    customer_id uuid PRIMARY KEY,
    full_name text,
    registered_at timestamp,
    status text
);
~~~

`customer_id` is the **partition key**. Cassandra hashes the key through the partitioner to distribute data and replicas; consequently, UUIDs with similar prefixes or generated close together **do not sit adjacent to each other across the cluster**.

A `customers_by_id` table keyed by UUID works very well for point lookups:

~~~cql
SELECT full_name, registered_at, status
FROM customers_by_id
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

However, if you need "the 50 most recently registered customers" or "customers registered this week," using `uuid` alone as the partition key does not serve that query directly. You need **a time-based access path**, such as a table partitioned by a time bucket with clustering columns.

**There is no cluster-wide AUTO_INCREMENT** for UUID keys. Cassandra is a distributed system; issuing globally sequential IDs can introduce coordination bottlenecks if poorly designed. UUIDs are convenient precisely because processes can generate IDs independently without requesting sequence numbers from a central allocator.

For business codes like `"000041"`, external account numbers, or phone numbers, **`text`** may be more appropriate than UUID. Never force an arbitrary string into UUID if the data contract does not guarantee a valid UUID.

## 5. timeuuid as a Clustering Key for Timelines

Consider the requirement: **"Fetch the 100 most recently recorded events for an account on a given day, and support reading events within an ID-generation time range."**

A query-driven table design:

~~~cql
CREATE TABLE events_by_account_day (
    account_id uuid,
    event_day date,
    event_id timeuuid,
    occurred_at timestamp,
    event_type text,
    payload text,
    PRIMARY KEY ((account_id, event_day), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);
~~~

Explanation:

- **`(account_id, event_day)`** is the composite partition key. It scopes an account's daily event partition; if daily event volume is too high, consider smaller buckets.
- **`event_id timeuuid`** is the clustering key. Cassandra sorts rows **within the same partition** by the time embedded in UUID v1, here in descending order.
- **`occurred_at timestamp`** is when the event occurred **according to the business source**. It may differ from when the timeuuid was created.
- **`event_type`, `payload`** are content columns; they do not automatically enable querying all events of a given `event_type` across the cluster.

A query matching the pattern:

~~~cql
SELECT event_id, occurred_at, event_type, payload
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 100;
~~~

Because of `CLUSTERING ORDER BY (event_id DESC)`, the query returns the latest events **by the timestamp embedded in timeuuid**, not by `occurred_at` if the two differ.

To illustrate generating an event directly in CQL, you can write:

~~~cql
-- Example when executed on 2026-11-21 (UTC).
INSERT INTO events_by_account_day (
    account_id, event_day, event_id, occurred_at, event_type, payload
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    now(),
    '2026-11-21T02:15:00Z',
    'LOGIN',
    'Access succeeded'
);
~~~

This statement only illustrates syntax. In production, **do not call `now()` directly on retries of the same event**, because each call generates a different ID. Also derive `event_day` using a consistent time zone and reference timestamp; a hardcoded date in an example is unsuitable for other days.

### 5.1. Partitioning and Ordering Implications

Cassandra does not sort **across the entire cluster** by `event_id`. It only sorts clustering values within **each partition**. A query like "the 100 latest events across all accounts" cannot be served efficiently by `events_by_account_day` alone.

To span consecutive days, query each daily partition and merge results in the application, or design a different table/bucket suited to the query. Querying by day or account can be very fast, yet unboundedly growing partitions still strain SSTables, tombstones, compaction, and repair.

**Never compute `event_day` using one time zone on writes and another on reads.** For example, 00:30 AM Vietnam time is still the previous calendar day in UTC. Explicitly document whether the partition bucket is UTC day or customer local day, and apply the exact same rule in every Java service.

## 6. Querying timeuuid by Time Range

The **`min_timeuuid`** and **`max_timeuuid`** functions construct boundary values for comparing against `timeuuid` columns; they are **not real event IDs**. Use them strictly as **query sentinels**, never for INSERT keys.

Example fetching events whose IDs were generated in **[01:00, 02:00) UTC** on November 21, 2026:

~~~cql
SELECT event_id, event_type, occurred_at
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
  AND event_id >= min_timeuuid('2026-11-21T01:00:00Z')
  AND event_id <  min_timeuuid('2026-11-21T02:00:00Z')
LIMIT 100;
~~~

Here the **half-open** interval `[start, end)` means:

- Includes every timeuuid with a timestamp from `01:00:00Z` onward.
- Excludes every timeuuid with a timestamp from `02:00:00Z` onward.
- Avoids boundary ambiguity across adjacent hourly windows.

When fetching events strictly **after** a timestamp (excluding all UUIDs generated at that exact instant), you can use `> max_timeuuid(start)`. When fetching **through** a timestamp at the boundary's resolution, choose the matching upper sentinel carefully. Avoid mixing comparison operators and sentinel functions intuitively without checking inclusive/exclusive semantics at boundary timestamps.

Do not do this:

~~~cql
-- DO NOT use sentinels as real record IDs:
-- INSERT INTO events_by_account_day (..., event_id, ...) VALUES (..., min_timeuuid(...), ...);
~~~

Because sentinels do not follow normal v1 ID generation rules and **do not guarantee uniqueness**. This is critical on retries: sentinels can cause key collisions or overwrite existing data.

Additionally, time-conversion functions help when presenting results:

~~~cql
SELECT event_id, to_timestamp(event_id) AS id_generated_at,
       occurred_at, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

`to_timestamp(event_id)` returns the ID-embedded time at the **millisecond** resolution of CQL `timestamp`. Although UUID v1 timestamps use 100-ns ticks, **never infer 100-ns clock or event accuracy** from this conversion.

### 6.1. Do You Also Need to Store occurred_at?

Yes, if the domain distinguishes:

- **Occurred at:** when the source device/client recorded the event.
- **Recorded at:** when the storage system received/logged it.
- **Generated at:** when the timeuuid was created.
- **Cassandra write timestamp:** internal metadata for last-write-wins conflict resolution (in microseconds), **distinct from CQL `timestamp`** and the UUID timestamp field.

A timeuuid created at ingestion time cannot substitute for `occurred_at` when events arrive late, are backfilled, or suffer clock skew. If you need to sort by when the event occurred, see the `timestamp + uuid` design in the next section.

## 7. Alternative: timestamp + uuid for Business Event Order

When a system must display events **ordered by source occurrence time**, do not default to a timeuuid generated upon receipt. You can use a composite clustering key:

~~~cql
CREATE TABLE source_events_by_account_day (
    account_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((account_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Why **two clustering columns**?

1. `occurred_at timestamp` establishes primary ordering by source occurrence time.
2. `event_id uuid` acts as a tie-breaker so two events occurring within the same millisecond are still stored as **two distinct rows**, provided their IDs differ.

If you used only `occurred_at` as the clustering key, two events in the same partition with the same timestamp would share the **exact same primary key** and overwrite one row. Adding `event_id` prevents that collision.

~~~cql
SELECT occurred_at, event_id, event_type
FROM source_events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T01:00:00Z'
  AND occurred_at <  '2026-11-21T02:00:00Z'
LIMIT 100;
~~~

This explicitly models **business order**, though you must still validate `occurred_at` quality from sources: wrong device clocks or late arrivals can still skew the expected ordering.

| Requirement | Starting Design |
|---|---|
| Look up a specific customer/transaction by ID | `uuid` as partition key |
| Timeline ordered by **ID generation time** | `timeuuid` as clustering key |
| Timeline ordered by **source occurrence time** | `timestamp` + `uuid` as clustering columns |
| External identifier not in UUID format | `text` or a type matching the external contract |
| Strict global/total sequence order across all writers | Dedicated sequence allocator or coordination model; UUID/timeuuid **do not guarantee this** |
| Global lookup by ID on an account/bucket timeline table | Add an ID lookup table / query-driven table if needed |

## 8. Java Driver 4.x: Generating and Writing the Right UUID Type

In Java Driver 4.x, both `uuid` and `timeuuid` map to Java **`java.util.UUID`**. Common methods are:

- `BoundStatementBuilder.setUuid(index, value)` for binding.
- `Row.getUuid("column_name")` for reading.
- `Uuids.timeBased()` from `com.datastax.oss.driver.api.core.uuid.Uuids` to generate a **UUID v1** suitable for `timeuuid`.
- `Uuids.unixTimestamp(id)` to extract **Unix milliseconds** when the ID is a UUID v1.

### 8.1. Generate Once and Reuse on Retry

Here is an example writing to `events_by_account_day`. Assume `session` is a `CqlSession` configured with the target keyspace and connected to Cassandra:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.uuid.Uuids;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

// CqlSession session = ...; // Initialized outside this example.

UUID accountId = UUID.fromString("11111111-1111-4111-8111-111111111111");
UUID eventId = Uuids.timeBased(); // Generate once per event.
if (eventId.version() != 1) {
    throw new IllegalStateException("eventId must be UUID version 1");
}

// Bucket by eventId generation time, consistently in UTC.
Instant generatedAt = Instant.ofEpochMilli(Uuids.unixTimestamp(eventId));
LocalDate eventDay = generatedAt.atZone(ZoneOffset.UTC).toLocalDate();

// Source timestamp if it may differ from generatedAt:
Instant occurredAt = generatedAt;

PreparedStatement insert = session.prepare(
    "INSERT INTO events_by_account_day "
  + "(account_id, event_day, event_id, occurred_at, event_type, payload) "
  + "VALUES (?, ?, ?, ?, ?, ?)");

BoundStatement statement = insert.boundStatementBuilder()
    .setUuid(0, accountId)
    .setLocalDate(1, eventDay)
    .setUuid(2, eventId)
    .setInstant(3, occurredAt)
    .setString(4, "LOGIN")
    .setString(5, "Access succeeded")
    .build();

session.execute(statement);

// When retrying after a timeout, reuse the EXACT statement or ID/bucket above.
~~~

**Critical rule:** the ID and bucket must live in a stable work envelope across retries. If after a timeout the process generates a fresh timeuuid and retries, Cassandra treats it as a **different row** because the clustering key changed. If the event must survive process restarts, persist the ID alongside the event payload or derive it deterministically from a trusted source.

`Uuids.timeBased()` stamps the time from the **Java application** calling it. Calling CQL `now()` stamps the time on the **coordinator** executing the statement. Clock drift between clients and nodes affects the embedded timestamps; choose a deliberate ID generation point and monitor clock synchronization.

### 8.2. Exact Lookup by ID

~~~java
import com.datastax.oss.driver.api.core.cql.Row;

PreparedStatement find = session.prepare(
    "SELECT event_id, occurred_at, event_type "
  + "FROM events_by_account_day "
  + "WHERE account_id = ? AND event_day = ? AND event_id = ?");

Row row = session.execute(
    find.bind(accountId, eventDay, eventId)
).one();

if (row != null) {
    UUID storedId = row.getUuid("event_id");
    Instant sourceTime = row.getInstant("occurred_at");
}
~~~

This query supplies the full **partition key** and clustering key, allowing Cassandra to read the exact row. A query knowing only `event_id` without `accountId`/`eventDay` is not well served by this table alone. If global lookup by ID is needed, consider adding an `events_by_id` table or an `event_id -> partition key` mapping table as required, along with a strategy to keep tables consistent.

### 8.3. Querying by Time Range from Java

The Java Driver provides **`Uuids.startOf(epochMillis)`** and **`Uuids.endOf(epochMillis)`**, which return **synthetic boundary UUIDs for queries**, not real event IDs.

~~~java
import com.datastax.oss.driver.api.core.uuid.Uuids;
import java.time.Instant;
import java.util.UUID;

Instant from = Instant.parse("2026-11-21T01:00:00Z");
Instant until = Instant.parse("2026-11-21T02:00:00Z");

// Strictly for binding to comparison predicates in SELECT:
UUID lowerBound = Uuids.startOf(from.toEpochMilli());
UUID exclusiveUpperBound = Uuids.startOf(until.toEpochMilli());

PreparedStatement range = session.prepare(
    "SELECT event_id, occurred_at, event_type "
  + "FROM events_by_account_day "
  + "WHERE account_id = ? AND event_day = ? "
  + "AND event_id >= ? AND event_id < ? LIMIT 100");

for (Row event : session.execute(
    range.bind(accountId, LocalDate.parse("2026-11-21"),
               lowerBound, exclusiveUpperBound)
)) {
    UUID id = event.getUuid("event_id");
    // Process results in Cassandra's timeuuid clustering order.
}
~~~

Sentinels take **Unix milliseconds**; never pass `UUID.timestamp()` directly because that returns 100-ns ticks since 1582. To extract Unix milliseconds from a UUID v1, use `Uuids.unixTimestamp(id)`.

Also never call `UUID.compareTo()` on the client assuming it matches **Cassandra's `timeuuid` order**; `java.util.UUID.compareTo()` is not equivalent to Cassandra's `timeuuid` comparator in all cases. When you need Cassandra ordering, rely on clustering order in the query.

## 9. Distributed Operations: Clock Skew, Consistency, and Idempotency

### 9.1. timeuuid Is Not a Cluster-Wide Clock

Two independent nodes can generate UUID v1s whose timestamps come from imperfectly synchronized clocks. Ordering by `timeuuid` reflects **the timestamp embedded in the ID**, not necessarily the real-world occurrence order or write-completion order of events.

Consider:

- **Clock skew:** synchronize host clocks with standard mechanisms and monitor drift.
- **Time source:** timeuuids generated by Java clients can diverge from coordinator clocks; timeuuids generated by `now()` can diverge from event sources.
- **Late arrival/backfill:** older events arriving late land in unexpected positions if IDs are created at ingestion time.
- **Tie-breaker:** distinct UUID v1s with the same timestamp carry other fields to stay unique, but do not establish causal ordering in a distributed system.

If the domain demands **strict total ordering** (such as a ledger sequence) or proving "event A definitely occurred before B" across services, you need a dedicated sequencing or versioning mechanism; `timeuuid` does not provide that guarantee.

### 9.2. Retries After Timeout

In distributed Cassandra, a write may succeed on some replicas even if the client receives a timeout or connection error. When retrying:

- **Keep the exact same primary key** (`account_id`, `event_day`, `event_id`) for the same event.
- Keep column values and write-timestamp rules consistent with business requirements; prevent a retry from unintentionally flipping state from A to B.
- For multi-partition/multi-table writes, implement recovery/reconciliation; retrying one statement does not turn the workflow into a multi-table ACID transaction.
- When using LWT (`IF NOT EXISTS`) for uniqueness, handle both the result and the ambiguous timeout outcome where you do not know whether the command applied.

An `INSERT` with the same primary key in Cassandra overwrites matching cells by write timestamp metadata; **reusing the same ID** is generally necessary for idempotency, but **insufficient by itself** if payload values differ between attempts.

### 9.3. Replication, Consistency, Compaction, and Repair

- **Replication** places data copies by partition token; UUIDs in a partition key are hashed to determine tokens rather than grouping partitions by ID generation time.
- **Consistency levels** (such as `LOCAL_QUORUM`) define read/write acknowledgment thresholds, not whether a timeuuid's embedded time matches source event time.
- **Compaction** merges SSTables and purges expired/tombstoned data per storage rules; it does not detect duplicate events written under different IDs during retries.
- **Repair** synchronizes replicas; it does not merge two rows for the same event written with two different `timeuuid` values.

Daily/hourly timeline partitioning requires measuring throughput, row counts, partition sizes, and retention. Daily buckets are insufficient for sources producing millions of events per day; hourly buckets or sharding plus benchmarked query designs may be necessary.

## 10. Privacy and Security Aspects of UUIDs

UUIDs are for **identification**, not **authorization**. A URL containing a random ID still requires verifying that the caller is permitted to read the record for that ID.

In UUID v1, the timestamp component reveals roughly when the ID was created; some v1 generators also expose node/environment traces. Therefore, never treat `timeuuid` as an opaque secret or metadata-free token.

In UUID v4, guessing a high-entropy random UUID is practically infeasible under normal conditions, yet it still **cannot replace** authentication, authorization, rate limiting, or auditing.

If a business ID is sensitive, enforce proper access control and data isolation. Never rely on UUID version to decide whether a caller may view a record.

## 11. Common Design Mistakes

| Mistake | Consequence | Solution |
|---|---|---|
| Writing `UUID.randomUUID()` to a `timeuuid` column | UUID v4 does not match `timeuuid` | Use UUID v1, e.g., `Uuids.timeBased()` |
| Calling `now()` on every retry of the same event | Generates a new key, creating duplicate rows | Generate once and preserve the ID across all retries |
| Calling `uuid()` in CQL when inserting accounts on a retried path | Multiple account IDs may be created | Generate the UUID in the application and reuse it |
| Assuming `uuid` increases chronologically | No guaranteed time order | Cluster by `timestamp` or `timeuuid` as appropriate |
| Using `timeuuid` to infer source occurrence time | Wrong under late ingest or clock skew | Store an independent `occurred_at timestamp` |
| Using `min_timeuuid` as an INSERT ID | Sentinels are not unique | Use sentinels only in WHERE range predicates |
| Querying only by `event_id` on an account/day partitioned table | Missing full partition key | Include full partition key or add a lookup table |
| Making `timeuuid` the partition key expecting account events to cluster together | Token hashing destroys global time order | Partition by account/bucket; use `timeuuid` for clustering |
| Calling `UUID.compareTo()` expecting Cassandra's order | May disagree with `timeuuid` ordering | Let Cassandra sort via clustering or use a matching comparator |
| Deriving `event_day` with inconsistent time zones | Same event lands in different daily partitions | Standardize UTC or a single business time zone |
| Treating a UUID as an authorization token | Leaking the ID exposes data | Enforce authorization checks on every operation |
| Failing to size timeline partitions | Oversized partitions, poor latency/compaction | Choose buckets/sharding based on throughput and retention |

## 12. Practice Exercises

### Exercise 1 — Choosing Types

An application has three columns: `customer_id` for customer lookups; `login_id` to sort logins by **server receipt time**; and `occurred_at` for when the client recorded the action.

**Recommendation:** `customer_id uuid`; `login_id timeuuid` if the server generates the ID on receipt; `occurred_at timestamp`. If sorting must strictly follow client occurrence time, consider `occurred_at` as a clustering key with a UUID tie-breaker.

### Exercise 2 — Why Are Events Duplicated on Retry?

A CQL statement uses `now()` to insert an event. The first attempt times out on the client after the coordinator wrote it; the second attempt re-runs the query.

**Answer:** `now()` generates a new timeuuid on every execution, so the retry inserts a second row. Fix it by generating the timeuuid once in the application, storing it in the event envelope, and rebinding the exact same ID on retries.

### Exercise 3 — Time Range [08:00, 09:00)

A table has partition key `(device_id, day)` and clustering key `event_id timeuuid`. Write the CQL query for 08:00–09:00 UTC on a given day.

~~~cql
SELECT event_id
FROM events_by_device_day
WHERE device_id = 22222222-2222-4222-8222-222222222222
  AND day = '2026-11-21'
  AND event_id >= min_timeuuid('2026-11-21T08:00:00Z')
  AND event_id <  min_timeuuid('2026-11-21T09:00:00Z');
~~~

This snippet assumes `events_by_device_day` is created with the stated keys; the essentials are providing the **full partition key** and **bounding the clustering key**. Never put `now()` on the right-hand side when querying a known historical window.

### Exercise 4 — Same Timestamp, Two Events

A table has primary key `((account_id, day), occurred_at)`. Two distinct events arrive with the exact same `occurred_at` to the millisecond. What happens?

**Answer:** they share the exact same primary key, so writes overwrite the same row. Add `event_id uuid` as the final clustering column, or use a `timeuuid` matching ordering requirements, to keep both rows distinct.

### Exercise 5 — Is UUID v1 Guaranteed True Physical Time?

Machines A and B have a 3-minute clock skew and generate UUID v1s for two events that physically occurred 1 second apart. Can CQL order serve as exact proof of physical event sequence?

**Answer:** no. Cassandra sorts by the timestamp embedded in the timeuuid, and source clocks can drift. You need synchronized/calibrated source timestamps or a business-trusted sequencing mechanism.

## 13. Checklist for Reviewing uuid and timeuuid

- [ ] Does the field require a **stable identifier**, **ordering by ID generation time**, or **ordering by event occurrence time**?
- [ ] Do `timeuuid` columns receive UUID v1 only; are CQL `now()` and Java `Uuids.timeBased()` used properly?
- [ ] Do all retryable paths reuse the **exact same ID and primary key** instead of regenerating UUIDs inside statements?
- [ ] Are `occurred_at`, `generated_at`, `recorded_at`, and **Cassandra write timestamp** clearly separated by role?
- [ ] Do all services share the same time zone policy and daily/hourly bucketing rule?
- [ ] Do queries provide the full **partition key** and valid clustering predicates?
- [ ] Are `min_timeuuid`/`max_timeuuid` (or `Uuids.startOf/endOf`) sentinels used solely as query bounds and never inserted into tables?
- [ ] Is global ordering needed, or only per-partition ordering? Have clock skew and late arrivals been considered?
- [ ] If multiple events can share a timestamp, does the key include a **tie-breaker** to prevent overwrites?
- [ ] Does the Java Driver map `UUID` cleanly with `getUuid`/`setUuid` without mixing versions?
- [ ] Are partition sizes bounded with appropriate retention, compaction, and repair plans?
- [ ] Is data protected by proper authorization rather than treating UUIDs as secret access tokens?

## References

- [Apache Cassandra — CQL native functions, UUID and timeuuid](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/functions.html).
- [DataStax Java Driver 4.x — Uuids class](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/uuid/Uuids.html).

**Remember:** `uuid` is the natural choice for **stable UUID identifiers**; `timeuuid` is a **UUID v1** suited for **clustering by ID generation time**. When ordering must follow **actual source occurrence time**, store a business `timestamp` and design clustering keys accordingly. In Cassandra, **ID type, partition keys, clustering order, and retry idempotency** determine the correctness and efficiency of the system.
