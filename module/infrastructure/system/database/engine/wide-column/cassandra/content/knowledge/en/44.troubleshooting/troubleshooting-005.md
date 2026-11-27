# InvalidQuery Due to Key Restrictions, Data Types, or Unsupported Queries in Apache Cassandra

## 1. Learning Objectives and Scope

In Apache Cassandra, a **syntactically valid** CQL statement can still be rejected at runtime because it violates **partition key, clustering key, type, index, statement type, or query rules**. In a Java Driver application, this failure may appear as `InvalidQueryException`, another server exception, or a **client-side codec/bind error** before any request leaves the JVM.

This lesson belongs to the **Troubleshooting** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. It connects directly to the module's core goals: understanding the wide-column model and partition routing, query-driven table design, replication/consistency, hands-on CQL, and Java connectivity.

After completing this lesson, you will be able to:

1. Distinguish `InvalidQuery` from `SyntaxError`, `Unauthorized`, CQL prepare/bind errors, timeouts, and `Unavailable`.
2. Read server error messages accurately without **hardcoding brittle string matches** across Cassandra releases.
3. Diagnose missing or mismatched **partition keys** and invalid clustering column orders or ranges.
4. Fix invalid `ORDER BY`, `IN`, filtering, secondary-index, and aggregation queries.
5. Map CQL data types cleanly to Java Driver 4.x: `uuid`, `date`, `timestamp`, `timeuuid`, `decimal`, `varint`, collections, and UDTs.
6. Understand unsupported DML patterns—especially **counters, TTL, LWT, and batches**—without falsely extrapolating from relational SQL.
7. Write safe CQL queries using **prepared statements and bind parameters**, handling `null`/`unset` properly.
8. Build a triage runbook anchored on error class, actual schema, query template, and live workload.
9. Design negative/positive tests and pre-fix checklists before changing application code or migrating schemas.

**Version scope:** Examples use common CQL concepts across Cassandra 4.x/5.x and Java Driver 4.x. Specific restrictions, index support, `GROUP BY`, `IN`, `LIKE`, `ANN`, JSON, SAI/SASI, `duration`, DDL, and exception names vary by Cassandra server, distribution, and driver release. **Never assert a CQL query is unsupported in every version based solely on one cluster's message.** Where differences matter, the lesson notes what to verify.

**Practical guardrail:** Execute mutations and DDL only inside authorized lab keyspaces. Never run `ALLOW FILTERING`, large scans, `TRUNCATE`, or production migrations merely to "see if the error goes away".

## 2. Where Does `InvalidQuery` Sit in the Request Lifecycle?

~~~mermaid
flowchart TD
    A["Java app constructs statement"] --> B{"Valid bind/codec?"}
    B -->|"No"| C["Client-side type/bind/codec exception"]
    B -->|"Yes"| D["Native protocol to coordinator"]
    D --> E{"Parses CQL syntax?"}
    E -->|"No"| F["SyntaxError or equivalent"]
    E -->|"Yes"| G{"Validates schema, keys, types, CQL rules?"}
    G -->|"No"| H["InvalidQuery or server validation error"]
    G -->|"Yes"| I{"Role authorized?"}
    I -->|"No"| J["Unauthorized/auth-related error"]
    I -->|"Yes"| K["Route / replica read-write per CL"]
    K --> L{"Served successfully?"}
    L -->|"No"| M["Timeout / Unavailable / execution error"]
    L -->|"Yes"| N["ResultSet / AsyncResultSet"]
~~~

This diagram illustrates **conceptual validation layers**, not a guaranteed internal execution order in every release (for example, authorization, schema validation, or preparation may occur at different stages).

### 2.1. Common Exception Categories

| Category | Typical Signal | Where to Investigate? |
|---|---|---|
| `InvalidQueryException` | Server rejects CQL after parsing/validation | Schema, PK, clustering, types, CQL operation |
| `SyntaxError` | Statement fails CQL grammar parsing | Keywords, commas, parentheses, quoting |
| Client codec/bind error | Java value cannot encode into target CQL type | `PreparedStatement` metadata, Java getters/setters, codecs |
| `UnauthorizedException` | Role lacks permissions | Roles/grants/authorizer; do not change PK |
| `AuthenticationException` | Invalid credentials or `LOGIN` role | Authenticator, session credentials |
| `UnpreparedException` or prepare-related | Prepared statement ID unknown to node | Driver prepare/reprepare, schema changes |
| `ReadTimeoutException` / `WriteTimeoutException` | Request likely reached replicas, insufficient timely replies | RF/CL, latency, node health |
| `UnavailableException` | Insufficient live replicas for CL before execution | Topology/liveness, RF/CL |
| `AllNodesFailedException` | Driver had no usable coordinator candidate | Per-node causes; network/TLS/server availability |

An HTTP 500 or `CompletionException` is a **wrapper**, not a root cause. Preserve exception class/cause chain, operation type, keyspace, query template ID, and versions for classification.

### 2.2. Do Not Guess Root Cause from One Message Line

Illustrative server messages (**not guaranteed verbatim** across versions):

~~~text
Cannot execute this query as it might involve data filtering...
Some partition key parts are missing...
Cannot restrict clustering column ...
ORDER BY is only supported when ...
Invalid ... constant ...
Cannot use ... for counters ...
~~~

A message mentioning "filtering" usually points to an access path lacking a suitable partition key or index—it does not indicate a heap memory problem. An "Invalid ... constant" message points to a CQL literal/type mismatch, distinct from a Java codec exception thrown before any network call.

## 3. Baseline Schema Used Throughout This Lesson

### 3.1. Single-Node Lab Keyspace

~~~cql
-- Strictly for a single-node Cassandra lab.
CREATE KEYSPACE IF NOT EXISTS troubleshooting_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
}
AND durable_writes = true;
~~~

`SimpleStrategy` RF=1 is **only for single-node labs**. Multi-datacenter production normally requires `NetworkTopologyStrategy`, per-DC RF, and matching consistency levels. **Never alter production RF/CL to make an `InvalidQuery` succeed.**

### 3.2. Query-Driven Table Design: "Device Readings by Day"

~~~cql
CREATE TABLE IF NOT EXISTS
    troubleshooting_lab.readings_by_device_day (
        device_id uuid,
        event_day date,
        event_time timestamp,
        reading_value double,
        status text,
        source text,
        PRIMARY KEY ((device_id, event_day), event_time)
    )
WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Here:

- **Composite partition key:** `(device_id, event_day)`. Both values jointly determine the partition and token.
- **Clustering column:** `event_time`, ordered descending within each partition.
- **Regular columns:** `reading_value`, `status`, `source`—not indexed by default.
- No foreign keys or relational joins exist.
- The **full primary key** is `(device_id, event_day, event_time)`; two events arriving in the same millisecond within the same partition overwrite/compete on the same row. Add `event_id` to the clustering key if same-millisecond events must remain distinct.

### 3.3. Hypothetical Seed Data

~~~cql
INSERT INTO troubleshooting_lab.readings_by_device_day
  (device_id, event_day, event_time, reading_value,
   status, source)
VALUES
  (11111111-1111-1111-1111-111111111111,
   '2026-11-21', '2026-11-21T09:00:00Z',
   25.4, 'OK', 'edge');

INSERT INTO troubleshooting_lab.readings_by_device_day
  (device_id, event_day, event_time, reading_value,
   status, source)
VALUES
  (11111111-1111-1111-1111-111111111111,
   '2026-11-21', '2026-11-21T09:05:00Z',
   25.9, 'WARN', 'edge');
~~~

**Note:** This is illustrative CQL not executed against a live environment. `date` represents a calendar day, while `timestamp` represents an instant typically at millisecond precision. Java writers and readers must agree on whether `event_day` uses UTC or a business timezone—if the bucket disagrees, the query is **valid yet returns 0 rows**, which is not `InvalidQuery`.

### 3.4. Valid Query for This Table

~~~cql
SELECT event_time, reading_value, status
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
ORDER BY event_time DESC
LIMIT 20;
~~~

In production, use **prepared statements and bind parameters**, never concatenating user-supplied UUIDs or dates directly into CQL strings.

## 4. Invalid Partition Key Restrictions

### 4.1. Missing Part of a Composite Partition Key

~~~cql
-- Invalid for the normal access path of this table.
SELECT *
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111;
~~~

Cassandra cannot deduce `event_day` to pinpoint a partition; the query is typically rejected or requires supported filtering/indexing. This does **not** mean "Cassandra lost data".

Fix when the API already knows the day:

~~~cql
SELECT event_time, reading_value
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

### 4.2. Supplying Only the Day Without Device ID

~~~cql
-- Incompatible with the partition key above:
SELECT *
FROM troubleshooting_lab.readings_by_device_day
WHERE event_day = '2026-11-21';
~~~

If the business requires "all devices for a given day", that is a **different query**. Consider a separate table keyed by day/shard/user/tenant, an analytics pipeline, or an appropriate query engine; never turn full-table Cassandra scans into online API traffic.

### 4.3. Querying Multiple Days for One Device

Cassandra does not store a single partition spanning every `event_day` for a device. For a bounded date range:

~~~text
Requested: device A, 2026-11-19 .. 2026-11-21

Application:
  SELECT partition (A, 2026-11-19)
  SELECT partition (A, 2026-11-20)
  SELECT partition (A, 2026-11-21)
  Merge results by timestamp, capping fan-out and bytes.
~~~

This is **controlled orchestration**, rather than issuing a keyless CQL query. Some releases permit `IN` within limits, yet querying thousands of partitions will still perform poorly. Cap partition/bucket counts, deadlines, concurrency, and pagination; if multi-day queries are frequent, design a **table tailored to that query**.

### 4.4. Partition Keys Must Never Be Null or Unset

~~~cql
-- Invalid: primary key columns cannot be null.
INSERT INTO troubleshooting_lab.readings_by_device_day
  (device_id, event_day, event_time, reading_value)
VALUES (null, '2026-11-21',
        '2026-11-21T09:00:00Z', 23.4);
~~~

Every **primary key** component of a row must be defined under CQL semantics. In Java, validate `device_id`/`event_day`/`event_time` before executing; binding `null` or leaving a key `unset` causes a server validation error or client-side bind error depending on path and version.

### 4.5. Never Add `ALLOW FILTERING` Just to "Clear the Error"

~~~cql
-- WARNING: anti-pattern example;
-- never run on large tables.
SELECT *
FROM troubleshooting_lab.readings_by_device_day
WHERE status = 'WARN'
ALLOW FILTERING;
~~~

In supported configurations/releases, `ALLOW FILTERING` tells Cassandra to scan partitions/rows and discard non-matching ones; exact validity depends on query, version, and indexes. However:

- The number of scanned partitions/rows can be huge.
- Latency and read amplification are not bounded by the returned row count.
- Even `LIMIT 10` may scan massive amounts of data.
- It readily triggers timeouts, tombstone warnings, and heap/GC/disk pressure.
- It does not turn a regular column into an indexed lookup.

**The true fix is a proper data model or access path**, never treating filtering as a query fix.

## 5. Clustering Keys: Equality Prefixes and Ranges

### 5.1. Table with Multiple Clustering Columns

To distinguish multiple events within the same millisecond:

~~~cql
CREATE TABLE IF NOT EXISTS
    troubleshooting_lab.events_by_device_day (
        device_id uuid,
        event_day date,
        event_time timestamp,
        event_id uuid,
        event_type text,
        reading_value double,
        PRIMARY KEY (
          (device_id, event_day),
          event_time,
          event_id
        )
    )
WITH CLUSTERING ORDER BY (
  event_time DESC,
  event_id ASC
);
~~~

Core structure:

~~~text
Partition key:
  (device_id, event_day)

Clustering order:
  event_time -> event_id

Regular columns:
  event_type, reading_value
~~~

### 5.2. Valid Queries Using Partition Key + Clustering Prefix

~~~cql
SELECT event_time, event_id, event_type
FROM troubleshooting_lab.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time >= ?
  AND event_time < ?;
~~~

This specifies the full partition key plus a range on the **first clustering column**, fitting hour/minute window reads within a day.

~~~cql
SELECT event_time, event_id, event_type
FROM troubleshooting_lab.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?
  AND event_id = ?;
~~~

Full primary key lookup reading one exact event.

### 5.3. Queries Skipping a Clustering Prefix

~~~cql
-- Unsuitable for the standard access path:
SELECT *
FROM troubleshooting_lab.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_id = ?;
~~~

`event_id` follows `event_time` in the clustering order. Without restricting `event_time`, Cassandra generally disallows restricting `event_id` as an exact clustering lookup unless supported by an index or filtering in that version.

Fixes:

- If `event_time` is known, bind both timestamp and ID.
- If the business looks up directly by `event_id`, design a dedicated `events_by_id` table.
- If filtering by another column, evaluate version-appropriate indexes/SAI and benchmark performance.
- Never slap `ALLOW FILTERING` onto high-volume traffic.

### 5.4. Range Restrictions and Trailing Column Predicates

~~~cql
-- Use only with exact understanding of version rules:
SELECT *
FROM troubleshooting_lab.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time > ?
  AND event_id = ?;
~~~

Once an earlier clustering column has a range predicate, restricting a later column may be rejected or force filtering depending on query shape and release. Practical rule: **equality prefix first, then the needed range**; to search by event ID independently of timestamp, build a table keyed by ID.

### 5.5. Clustering Columns Cannot Be Updated via `SET`

~~~cql
-- Invalid: primary key columns cannot be modified with SET.
UPDATE troubleshooting_lab.events_by_device_day
SET event_time = ?
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?
  AND event_id = ?;
~~~

The primary key defines row placement; you cannot relocate a row's `event_time` via `SET`. To "change a key", plan an **INSERT at the new key plus DELETE of the old row** following idempotency, consistency, and controlled backfill rules. Those two mutations do not form a general ACID transaction.

## 6. `ORDER BY` and Sort Scope

### 6.1. `ORDER BY` Is Not Arbitrary Column Sorting

~~~cql
-- Valid: sorts by clustering column within a single partition.
SELECT event_time, reading_value
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
ORDER BY event_time DESC
LIMIT 20;
~~~

~~~cql
-- Invalid per schema: reading_value is a regular column,
-- not a clustering column.
SELECT event_time, reading_value
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
ORDER BY reading_value DESC
LIMIT 20;
~~~

If the app needs "top 20 largest values":

1. Consider a dedicated table or materialized view shaped to that query and retention.
2. Bucket data appropriately so clustering order serves the sort directly.
3. Sort in the application only when the result set is **strictly bounded** and within SLO.
4. Use an analytical engine for global top-N across huge datasets.

### 6.2. `ORDER BY` Does Not Impose Cluster-Wide Order

A query with `ORDER BY event_time` does not sort rows globally across all device/day partitions. When querying multiple partition values (such as `IN` where supported by the release), verify ordering semantics and cost separately.

**Never claim cluster-wide ordering** based on single-partition clustering order.

### 6.3. Sort Direction and Multiple Clustering Columns

With multiple clustering columns, Cassandra supports the declared clustering order and, in compatible cases, its exact reverse. Combinations like `ORDER BY event_time ASC, event_id ASC` are not automatically valid when the table defines **mixed directions**. Check your release's `ORDER BY` rules and bake the access order directly into the schema.

## 7. `IN`, Regular-Column Filters, and Secondary Indexes

### 7.1. `IN` May Be Valid Yet Expensive

`IN` is not a relational `JOIN`. Restrictions on partition/clustering columns and combining `IN` with `ORDER BY` depend on the Cassandra release and query shape.

~~~cql
-- Some Cassandra versions allow IN under specific conditions.
-- Shown for lab testing only; not guaranteed on every release.
SELECT event_time, reading_value
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day IN ('2026-11-20', '2026-11-21');
~~~

If your release/path rejects it, issue **two prepared reads** targeting each partition with bounded concurrency and result merging. Even when supported, cap the key/partition count, timeout, and resource budget.

### 7.2. Regular-Column Predicates May Require an Index

~~~cql
-- No index on status in the example schema:
SELECT device_id, event_day, event_time
FROM troubleshooting_lab.readings_by_device_day
WHERE status = 'WARN';
~~~

Cassandra **does not** automatically serve regular-column predicates like an RDBMS query planner using B-tree indexes. Queries like this are commonly rejected for filtering or lack of support.

Options:

| Requirement | Approach |
|---|---|
| `status` within one device/day | Read the bounded partition and filter in the app if rows are few |
| Query `status` broadly across partitions | Dedicated table keyed by status/time bucket/shard for frequent reads |
| Index-backed predicate | Evaluate secondary indexes / SAI for your Cassandra version/distribution |
| Full-text / complex search | Dedicated search engine when warranted |
| Analytical scans/aggregations | Batch/analytical system; do not force onto online CQL |

### 7.3. Indexes Are Not Free

Indexes add **write amplification**, memory/disk footprint, index build/rebuild work, compaction load, and availability risks. A passing `CREATE INDEX` does not prove the new query meets SLO.

Evaluate against real workload:

- Value selectivity and cardinality.
- Matched partition and row counts.
- Read p95/p99, tombstone scans, CPU/heap/disk.
- Write throughput and background compaction.
- Multi-predicate combinations actually supported by the engine.
- Version/distribution differences: `2i`, `SAI`, and `SASI` do not share identical semantics.

### 7.4. `LIKE`, `CONTAINS`, and Search Operators Depend on Index and Type

~~~cql
-- Do not assume this works on an unindexed text column:
SELECT *
FROM troubleshooting_lab.readings_by_device_day
WHERE source LIKE '%edge%';
~~~

`LIKE`/pattern matching requires checking index support and exact release syntax; never assume SQL-style wildcard matching works out of the box.

`CONTAINS` normally applies to **collection membership** with supporting indexes/queries, not arbitrary substring matching in `text`. Distinguish collection `CONTAINS`, map key `CONTAINS KEY`, and text search.

## 8. Data Types: CQL Literal Errors vs. Java Codecs

### 8.1. Common CQL ↔ Java Mappings

| CQL | Typical Java Driver 4.x Type | Pitfall |
|---|---|---|
| `uuid` | `java.util.UUID` | Do not bind arbitrary strings to a UUID marker |
| `timeuuid` | `UUID` version 1 (time-based) | Not a random UUID v4 |
| `date` | `java.time.LocalDate` | Carries no timezone or time of day |
| `timestamp` | `java.time.Instant` | Typically millisecond precision; stores no `ZoneId` |
| `time` | `java.time.LocalTime` | Time of day, not a full timestamp |
| `bigint` | `long` / `Long` | Do not pass `int` if values exceed 32-bit range |
| `int` | `int` / `Integer` | Signed 32-bit bounds |
| `smallint` | `short` / `Short` | Narrow range |
| `tinyint` | `byte` / `Byte` | Very narrow range |
| `float` | `float` / `Float` | Floating-point precision |
| `double` | `double` / `Double` | Unsuitable for currency needing exact decimals |
| `decimal` | `java.math.BigDecimal` | Scale/rounding; avoid `double` |
| `varint` | `java.math.BigInteger` | Do not coerce to `long` if unbounded |
| `boolean` | `boolean` / `Boolean` | String `"yes"` is not a boolean |
| `text` / `varchar` | `String` | UTF-8 encoding and payload size |
| `blob` | `ByteBuffer` | Direct/heap, buffer position, byte limits |
| `list<text>` | `List<String>` | Element types/null rules, update semantics |
| `set<uuid>` | `Set<UUID>` | Codec and element type |
| `map<text,int>` | `Map<String,Integer>` | Key and value types |
| UDT | `UdtValue` or mapped codec | Schema/version, frozen vs. non-frozen fields |
| tuple | `TupleValue` | Positional exact element types |
| `duration` | Cassandra/driver-specific duration type | Not interchangeable with `java.time.Duration` in all semantics |

Exact class/method signatures depend on driver 4.x minor versions and custom codecs. Always check `PreparedStatement.getVariableDefinitions()` and expected CQL types before binding.

### 8.2. Type-Mismatched Literals in CQL

~~~cql
-- Type error: double column rejects string 'high'.
UPDATE troubleshooting_lab.readings_by_device_day
SET reading_value = 'high'
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T09:00:00Z';
~~~

~~~cql
-- Type error: date cannot parse 'yesterday'.
SELECT *
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = 'yesterday';
~~~

The literal `'2026-11-21'` is parsed into a `date` by CQL when the column expects `date`; however, arbitrary string literals and binding a Java `String` to a `date` marker **are not equivalent**. Prepared markers enforce expected CQL types, requiring compatible Java values or codecs.

### 8.3. Type Mismatches Are Not Always `InvalidQueryException`

If Java calls `bound.setString("event_day", "2026-11-21")` for a CQL `date` marker, the driver throws a client-side codec/type error before sending anything to the coordinator. This is a **client programming bug**—never retry it, run `nodetool repair`, or treat it like a server timeout.

### 8.4. `timeuuid` Differs from `uuid`

A valid UUID v4 matching `uuid` format is **not guaranteed** to be accepted in a `timeuuid` column, because CQL `timeuuid` requires a time-based UUID version. Do not convert every event ID to `timeuuid` solely for ordering; weigh identity, uniqueness, and write-time semantics.

### 8.5. Timestamps, Timezones, and Partition Days

~~~text
Instant event_time: 2026-11-21T17:30:00Z
event_day UTC:       2026-11-21
event_day VN +07:    2026-11-22
~~~

If the writer binds UTC `event_day` and the reader binds a local date, the query has **the full partition key and is 100% valid**, yet returns **zero rows**. Distinguish "valid query, wrong bucket" from server `InvalidQuery` so you do not modify schemas by mistake.

## 9. Prepared Statements: Preventing Bind Errors and Injection

### 9.1. Parameterized Queries

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class ReadingsRepository {
    private final CqlSession session;
    private final PreparedStatement latestByDeviceDay;

    public ReadingsRepository(CqlSession session) {
        this.session = session;
        this.latestByDeviceDay = session.prepare(
            "SELECT event_time, reading_value, status " +
            "FROM troubleshooting_lab.readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? " +
            "LIMIT ?"
        );
    }

    public ResultSet latest(
            UUID deviceId, LocalDate eventDay, int limit) {
        if (deviceId == null || eventDay == null) {
            throw new IllegalArgumentException(
                "Partition key components are required");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                "limit must be within 1..100");
        }

        BoundStatement bound = latestByDeviceDay.bind(
            deviceId, eventDay, limit
        ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE);

        return session.execute(bound);
    }
}
~~~

**Note:** Because this is a single-node RF=1 lab, `LOCAL_ONE` is used for simplicity; production must use a CL matching correctness and availability requirements—never copy `LOCAL_ONE` blindly. `ResultSet` pages results; callers must still cap result counts/bytes and manage resources. Never interpret `LIMIT 100` as a guarantee that only 100 storage cells are read.

### 9.2. Avoid Concatenating User Input into CQL Strings

~~~java
// ANTI-PATTERN: injection risk + literal/type issues.
String cql =
    "SELECT * FROM troubleshooting_lab.readings_by_device_day " +
    "WHERE device_id = " + userInput +
    " AND event_day = '" + dayInput + "'";
~~~

Better practice:

- Use prepared bind markers for **values**.
- Parse `UUID`, `LocalDate`, and `Instant` early and validate at application boundaries.
- Identifiers such as keyspace/table/column names **cannot be bound with `?` like values**; validate dynamic identifiers against a strict allowlist or approved schema metadata.
- Never place raw CQL or bound values into metric labels or exception logs.

### 9.3. `null` and `unset` Are Not Equivalent

During updates/upserts, Cassandra and the driver distinguish **explicit null** (which writes a cell deletion/tombstone depending on the operation) from **unset** (which omits writing that column) in supported versions. Keep in mind:

- Primary-key components must never be null or unset.
- Never casually call `setToNull` when business logic meant "leave unchanged".
- In JSON patches or partial API updates, explicitly distinguish omitted fields from explicit nulls.
- Counters, collections, TTL, and update semantics each impose specific rules.
- Verify Driver 4.x `BoundStatement.setToNull(...)`/`unset(...)` behavior against your Cassandra version.

### 9.4. Inspect Expected Marker Types Instead of Guessing

~~~java
PreparedStatement prepared = session.prepare(
    "SELECT event_time FROM " +
    "troubleshooting_lab.readings_by_device_day " +
    "WHERE device_id = ? AND event_day = ?"
);

// Inspect metadata in debugger/tests; never log sensitive data.
var definitions = prepared.getVariableDefinitions();
// Verify exact method/iterator signatures against your driver version.
~~~

If the error reports expected `date` while Java supplies `String`, fix the mapping in the application layer. Never coerce every column to `String` to "avoid mismatches".

## 10. `INSERT`, `UPDATE`, `DELETE`, and Full-Key Requirements

### 10.1. `INSERT` Must Include Every Primary-Key Component

~~~cql
-- Invalid: missing mandatory clustering component event_time.
INSERT INTO troubleshooting_lab.readings_by_device_day
  (device_id, event_day, reading_value)
VALUES
  (11111111-1111-1111-1111-111111111111,
   '2026-11-21', 25.0);
~~~

Fix by providing the real, properly typed `event_time`; never substitute a date for a timestamp or invent random timestamps to mask a modeling flaw.

### 10.2. `UPDATE` of a Regular Cell Requires the Full Key

~~~cql
-- Invalid for updating a regular cell: missing event_time.
UPDATE troubleshooting_lab.readings_by_device_day
SET status = 'WARN'
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21';
~~~

~~~cql
-- Valid with the full primary key:
UPDATE troubleshooting_lab.readings_by_device_day
SET status = 'WARN'
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

CQL `UPDATE` acts as an **upsert** for standard mutations: a missing row can be created at the full PK unless conditional (`IF`). It does not return "rows affected=0" the way many SQL APIs do.

### 10.3. `DELETE` of One Row vs. Deleting an Entire Partition

~~~cql
-- Delete a single row: full primary key.
DELETE FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;

-- Delete the ENTIRE partition for that device/day.
DELETE FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?;
~~~

These two statements have drastically different consequences. `DELETE` with a full partition key is valid even though `UPDATE` on a regular cell requires the full row key; **never delete an entire partition to work around an UPDATE error**.

~~~cql
-- Delete a single regular cell within a row.
DELETE status
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

### 10.4. Primary-Key Columns Cannot Be Modified via `SET`

~~~cql
-- Invalid: event_time belongs to PRIMARY KEY.
UPDATE troubleshooting_lab.readings_by_device_day
SET event_time = ?
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

Changing a primary key requires planning an `INSERT` at the new key plus `DELETE` at the old key, accounting for idempotency, concurrency, CL, read consistency, and tombstones/compaction. The two mutations do not automatically behave as a relational ACID transaction.

## 11. Counters Are a Special Data Type and Mutation Model

### 11.1. Counter Table

~~~cql
CREATE TABLE IF NOT EXISTS
    troubleshooting_lab.device_daily_counts (
        device_id uuid,
        event_day date,
        total_events counter,
        PRIMARY KEY ((device_id, event_day))
    );
~~~

Non-primary-key columns in a counter table must obey Cassandra's counter rules. Never mix ordinary `text`/`int` columns with `counter` columns in the same table as in a conventional schema.

### 11.2. Incrementing and Decrementing Counters

~~~cql
UPDATE troubleshooting_lab.device_daily_counts
SET total_events = total_events + 1
WHERE device_id = ?
  AND event_day = ?;
~~~

~~~cql
-- Invalid: assigning an arbitrary value to a counter.
UPDATE troubleshooting_lab.device_daily_counts
SET total_events = 10
WHERE device_id = ?
  AND event_day = ?;

-- Invalid: inserting a counter value directly.
INSERT INTO troubleshooting_lab.device_daily_counts
  (device_id, event_day, total_events)
VALUES (?, ?, 10);
~~~

Additional counter restrictions:

- Cannot use `USING TTL` as with ordinary cells.
- No LWT/conditional updates as on regular columns in common Cassandra versions.
- Cannot mix counter mutations with regular mutations in the same batch contrary to CQL rules.
- Retrying increments **is not idempotent**; if the initial attempt applied before a client timeout, retrying double-counts.
- Never casually `ALTER` a `counter` type to `bigint` to "fix errors"; you generally need a new table and reconciled migration.

## 12. TTL, Mutation Timestamps, and LWT

### 12.1. Valid TTL on Regular Cells

~~~cql
INSERT INTO troubleshooting_lab.readings_by_device_day
  (device_id, event_day, event_time, reading_value, status)
VALUES (?, ?, ?, ?, ?)
USING TTL 86400;

UPDATE troubleshooting_lab.readings_by_device_day
USING TTL 600
SET status = ?
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

TTL follows mutation expiration semantics—it does not subtract from `event_time`. `TTL 0` and table-level `default_time_to_live` have release-specific semantics; never assume `TTL 0` means "expire immediately". You cannot apply TTL independently to primary-key components alone, and TTL on counters obeys separate restrictions.

### 12.2. `USING TIMESTAMP` Differs from the `event_time` Column

CQL mutation write timestamps are normally in microseconds, whereas an `event_time timestamp` column holds domain data typically at millisecond precision. `WRITETIME(reading_value)` is not the same as `event_time`.

Certain combinations of `USING TIMESTAMP`, conditional statements, and counters are rejected. On an invalid query:

1. Identify which mutation uses `TIMESTAMP`.
2. Check for `IF`/LWT or counters.
3. Verify whether your CQL release permits that combination.
4. Never strip `IF` just for speed when the business requires compare-and-set.

### 12.3. LWT Has Specific Conditions

~~~cql
INSERT INTO troubleshooting_lab.readings_by_device_day
  (device_id, event_day, event_time, reading_value)
VALUES (?, ?, ?, ?)
IF NOT EXISTS;
~~~

~~~cql
UPDATE troubleshooting_lab.readings_by_device_day
SET status = 'DONE'
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?
IF status = 'NEW';
~~~

LWT/Paxos carries extra cost, `wasApplied()`, and serial consistency; do not assume arbitrary SQL `IF` expressions are valid CQL. A `ReadTimeout` or `WriteTimeout` on a conditional write is an **uncertain outcome**, not a simple validation error; never blindly retry or overwrite.

## 13. `BATCH` Neither Fixes Invalid Queries Nor Acts as a Bulk SQL Transaction

### 13.1. Valid Batch of Two Prepared Mutations

~~~cql
BEGIN BATCH
  INSERT INTO troubleshooting_lab.readings_by_device_day
    (device_id, event_day, event_time, reading_value)
  VALUES (?, ?, ?, ?);
  INSERT INTO troubleshooting_lab.readings_by_device_day
    (device_id, event_day, event_time, reading_value)
  VALUES (?, ?, ?, ?);
APPLY BATCH;
~~~

If any PK or typing inside is wrong, `BATCH` will not make it valid.

### 13.2. Common Batch Misconceptions

| Case | Why Inspect Carefully? |
|---|---|
| Counter + non-counter in one batch | Restricted by mutation type rules |
| Multi-partition batch | Coordinator/batchlog/timeout overhead |
| Conditional/LWT batch | Condition, partition, and serial-semantics limits |
| Huge batch for "bulk ingest" | Spikes memory/network/latency instead of throughput |
| Expecting SQL-style rollback/isolation | CQL batches have different guarantees from SQL ACID transactions |

Use bounded concurrent prepared writes with rate/byte limits when the goal is throughput; reserve `BATCH` for documented atomicity cases.

## 14. Collections, Frozen Values, and UDTs

### 14.1. Collections Must Bind Exact CQL Element Types

~~~cql
CREATE TABLE IF NOT EXISTS
    troubleshooting_lab.device_metadata (
        device_id uuid PRIMARY KEY,
        tags set<text>,
        attributes map<text, text>,
        owners list<uuid>
    );

INSERT INTO troubleshooting_lab.device_metadata
  (device_id, tags, attributes, owners)
VALUES
  (11111111-1111-1111-1111-111111111111,
   {'edge', 'critical'},
   {'region': 'vn', 'team': 'ops'},
   [22222222-2222-2222-2222-222222222222]);
~~~

Java needs `Set<String>`, `Map<String,String>`, `List<UUID>`, and matching codecs. A `String` containing JSON does not automatically convert into a CQL map without an explicit parser or custom codec.

Never insert null collection elements or mismatched element types, and check list/set/map limits for your server release. Huge collections inside a single cell/partition also cause p99 and compaction pressure.

### 14.2. UDTs and `frozen`

~~~cql
CREATE TYPE IF NOT EXISTS troubleshooting_lab.geo_point (
  latitude double,
  longitude double
);

CREATE TABLE IF NOT EXISTS troubleshooting_lab.device_locations (
  device_id uuid PRIMARY KEY,
  last_point frozen<geo_point>
);
~~~

`frozen` makes a value atomic at mutation level; you cannot update individual subfields the way supported non-frozen UDTs allow. If an error mentions `frozen`, UDT, or collection, inspect **the schema type** and mutation syntax rather than adding filtering.

### 14.3. `CONTAINS` Does Not Mean Substring Search

~~~cql
-- Requires supporting index/query capability per release.
SELECT *
FROM troubleshooting_lab.device_metadata
WHERE attributes CONTAINS KEY 'region';
~~~

`CONTAINS`/`CONTAINS KEY` test collection membership, while `LIKE` on `text` depends on index/release support. Neither provides arbitrary out-of-the-box `WHERE` filtering on every regular column.

## 15. SQL Operations That Do Not Translate Directly to CQL

### 15.1. No General-Purpose `JOIN`

~~~sql
-- Illustrative relational SQL, NOT valid CQL:
SELECT d.name, r.value
FROM devices d
JOIN readings r ON d.id = r.device_id
WHERE d.region = 'vn';
~~~

Cassandra offers no general relational `JOIN` or subquery planner. Typical solutions are query-driven tables, denormalization, bounded application fan-out, read models, or analytical/search engines.

### 15.2. No Arbitrary Subqueries, `OR`, or Unbounded Predicates

~~~sql
-- SQL-style subquery, NOT standard CQL:
SELECT *
FROM readings
WHERE device_id IN (
  SELECT device_id FROM devices WHERE region = 'vn'
);
~~~

Boolean `OR` and index combinations vary across Cassandra releases and index types; **never claim `OR` is forbidden in every version**, yet never guess CQL validity from SQL syntax. Verify queries against the exact release's CQL documentation.

### 15.3. Aggregations Are Not Automatically Cheap

~~~cql
SELECT count(*)
FROM troubleshooting_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?;
~~~

A `COUNT(*)` may be valid yet still read vast amounts of data inside a partition. Never run it on every HTTP request over wide partitions; precompute read models, counters, or analytics based on requirements and trade-offs.

### 15.4. `GROUP BY`, `DISTINCT`, and `PER PARTITION LIMIT`

These CQL features exist in specific releases, subject to strict rules on **primary keys, partitions, clustering order, and query shape**. Never assume:

~~~sql
-- SQL-style query not necessarily valid in CQL:
SELECT status, avg(reading_value)
FROM readings
GROUP BY status;
~~~

With `status` as a regular column, this does not fit `readings_by_device_day`. Pre-aggregate by status/time bucket or use an analytical system.

### 15.5. No Standard SQL `OFFSET` Pagination

~~~sql
-- Never assume CQL supports random-access OFFSET:
SELECT * FROM readings LIMIT 50 OFFSET 10000;
~~~

Java Driver and Cassandra paginate via **paging state**, which carries version, routing, and correctness caveats—not numeric offsets. Paging does not guarantee snapshot isolation across pages, and paging state should be treated as an opaque token rather than user-editable input.

## 16. `token()` and Range Scans Belong to a Different Scope

~~~cql
-- Syntax illustration only for labs/tooling. Exact token bounds
-- depend on partitioner and Cassandra release.
SELECT device_id, event_day, event_time
FROM troubleshooting_lab.readings_by_device_day
WHERE token(device_id, event_day) > ?
  AND token(device_id, event_day) <= ?;
~~~

Token-range scans help ETL and backfill jobs, **not filtering on regular columns**. Operational usage requires pagination, checkpoints, per-node load budgets, disk/GC headroom, topology-change handling, and proper read CL.

Never embed unbounded token scans inside latency-sensitive APIs; if you only need one device/day, supply the exact partition key.

## 17. Real Schemas, Identifiers, and Caches

### 17.1. Inspecting Schemas on a Real Cluster

~~~cql
-- cqlsh client commands, NOT native CQL sent directly
-- via session.execute():
DESCRIBE KEYSPACE troubleshooting_lab;
DESCRIBE TABLE troubleshooting_lab.readings_by_device_day;
~~~

`DESCRIBE` is executed by `cqlsh`/clients. From Java, use driver metadata APIs or version-supported `system_schema` queries—**never modify system tables**.

Right after a deployment runs DDL:

- Verify schema agreement.
- Verify keyspace, table, and column types across all coordinator candidates.
- Check migration version/order and driver schema metadata.
- Account for driver prepare/re-prepare behavior after schema changes.
- `UnpreparedException` differs fundamentally from `InvalidQuery` caused by missing PKs.

### 17.2. Quoted Identifiers Are Case-Sensitive

~~~cql
CREATE TABLE troubleshooting_lab."DeviceEvents" (
  id uuid PRIMARY KEY
);

-- Must use identical quoted name:
SELECT * FROM troubleshooting_lab."DeviceEvents"
WHERE id = ?;
~~~

Unquoted names fold per CQL rules; double-quoted names preserve case sensitivity. `"DeviceEvents"` and `deviceevents` are not the same table.

### 17.3. Default Keyspace and Reserved Keywords

When CQL works in `cqlsh` after `USE troubleshooting_lab` yet fails in a Java session with no keyspace set, unqualified table names hit the wrong keyspace or report unknown table. Prefer fully qualified CQL templates.

Column names colliding with reserved keywords may require quoting depending on CQL release, though clean, non-reserved identifiers are far better.

## 18. Valid Queries Do Not Guarantee Business Correctness or SLO

| Layer | Example |
|---|---|
| Syntax | CQL parses cleanly |
| Server validation | Full PK, types, restrictions, and statement rules satisfied |
| Security | Role/tenant authorized to access |
| Business data | Writer/reader agree on UTC `event_day` |
| Operations | p99, CPU/disk/tombstone load within targets |

A `SELECT` with the full PK yet wrong-timezone `event_day` returns **0 rows**, not `InvalidQuery`. A `SELECT` with `ALLOW FILTERING` might return 5 matching rows while scanning excessive data and causing timeouts or GC pauses.

CL `ONE`/`LOCAL_QUORUM` never turns a regular column into an indexed key or fixes Java codecs. When a valid query times out, investigate **RF/CL/replica liveness/disk/compaction** instead of guessing `WHERE` edits.

In multi-tenant systems, binding a typed `UUID` **does not replace application-level authorization**: verify the principal owns or may access the requested device/tenant.

## 19. Java Driver 4.x: Classify Failures Before Retrying

### 19.1. Separate Prepare, Bind, and Execute

~~~text
User input -> UUID/LocalDate/Instant validation
  -> Prepare CQL, server parse/validate
  -> Bind typed markers, driver codec
  -> Execute, server semantic/permission check
  -> Replica read/write per CL
  -> ResultSet / AsyncResultSet
~~~

- `session.prepare(...)` can receive server `InvalidQueryException` or `SyntaxError` **before any execute**.
- `bound.setString(...)` on a CQL `date` marker throws a codec/type error **inside the Java client**.
- The server may also reject statements at execution time if validation or schemas differ.
- Dispatched requests that time out represent a separate branch with **uncertain write outcomes**.

### 19.2. Classifying Java Driver 4.x Exceptions

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.servererrors.InvalidQueryException;
import com.datastax.oss.driver.api.core.servererrors.SyntaxError;
import com.datastax.oss.driver.api.core.servererrors.UnauthorizedException;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;

import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public final class CqlFailureKinds {
    private CqlFailureKinds() {}

    static Throwable unwrap(Throwable failure) {
        Throwable t = failure;
        for (int i = 0; i < 8; i++) {
            if ((t instanceof CompletionException
                    || t instanceof ExecutionException)
                    && t.getCause() != null) {
                t = t.getCause();
            } else {
                return t;
            }
        }
        return t;
    }

    static String classify(Throwable failure) {
        Throwable t = unwrap(failure);
        if (t instanceof InvalidQueryException)
            return "CQL_SEMANTIC_VALIDATION";
        if (t instanceof SyntaxError)
            return "CQL_SYNTAX";
        if (t instanceof UnauthorizedException)
            return "CQL_AUTHORIZATION";
        if (t instanceof ReadTimeoutException)
            return "READ_TIMEOUT";
        if (t instanceof AllNodesFailedException)
            return "NO_COORDINATOR_CANDIDATE";
        return "CLIENT_CODEC_OR_OTHER";
    }
}
~~~

**Limitations:** This minimal classifier does not separate `WriteTimeout`, `DriverTimeout`, `Unavailable`, `Unprepared`, custom codecs, or per-node root causes. Verify exact API/type names against your driver artifact. On `AllNodesFailedException`, inspect `getAllErrors()` by **coordinator candidates**, not as a full replica list.

### 19.3. Safe Logging

~~~text
event=cql_execution_failure
timestamp_utc=2026-11-21T10:10:00Z
service=telemetry-reader
query_template=latest20_by_device_day
error_kind=CQL_SEMANTIC_VALIDATION
schema_release=known_or_unknown
driver_major=4
consistency=LOCAL_QUORUM
~~~

This is an **application-defined log schema**, not Cassandra's default output. Never log raw bind values, tenant/device UUIDs, passwords, user-concatenated CQL strings, or unredacted error messages. Query template IDs and error classes keep metric/log cardinality bounded.

### 19.4. Retry Policy by Error Kind

| Category | Auto-Retry? | Reason |
|---|---|---|
| InvalidQuery/SyntaxError | **No** | Query/schema/type mismatch is deterministic |
| Client codec/type error | **No** | Java bind bug, not a slow node |
| Unauthorized | **No** | Retrying never grants permissions |
| Unprepared | Handled via driver reprepare mechanism | Do not wrap in infinite outer retries |
| Timeout/Unavailable | Conditional | Depends on CL, idempotency, deadline, budget |
| AllNodesFailed/network | Conditional | Classify causes; TLS errors will not self-heal |

If `InvalidQuery` spikes right after a deployment, **rolling back or fixing the query template / migration mismatch** makes far more sense than raising timeouts or pool sizes.

## 20. Evidence to Collect Before Altering Schema

### 20.1. Minimum Checklist

1. Cassandra server and Java Driver versions.
2. Actual keyspace/table, PRIMARY KEY, clustering order, data types, and indexes.
3. Sanitized query template and statement type.
4. Whether failure happens at prepare, bind, execute, or page fetch.
5. Exception class, cause chain, and sanitized message excerpt.
6. Local DC, consistency level, and coordinator candidate if known.
7. UTC timeline, app/DDL migration version, and schema agreement.
8. Query intent: lookup by device/day, event ID, status, or aggregation?
9. Payload/partition width, TTL/tombstone mix, and latency budget.
10. Authorized lab/staging environment and rollback owner.

### 20.2. Do Not Run Production Scans to Experiment

~~~cql
-- WARNING: anti-pattern on large tables.
SELECT *
FROM troubleshooting_lab.readings_by_device_day
WHERE status = 'WARN'
ALLOW FILTERING;
~~~

To validate query semantics, use a **small lab dataset**. An `ALLOW FILTERING` query returning rows on tiny data proves nothing about behavior over millions of partitions and heavy tombstones.

### 20.3. Schema Metadata and Migrations

Compare `cqlsh` `DESCRIBE` with Java Driver metadata and `system_schema`/schema agreement per release. Remember `DESCRIBE` is a `cqlsh` command, **not a native CQL statement** for `session.execute`. Never edit system tables directly. An `UnpreparedException` after DDL does not mean Cassandra SSTables are corrupt.

## 21. Runbook A — `WHERE` Missing Partition Key

**Scenario:** `WHERE device_id=?` on a table with partition key `(device_id, event_day)` is rejected.

1. Identify the exact SELECT/UPDATE/DELETE and query template.
2. Inspect the live PRIMARY KEY, not merely DDL checked into Git.
3. Check whether `event_day` is available in the request or business context.
4. If available, bind a typed `LocalDate` using consistent writer/reader timezone policy.
5. If unavailable, design bounded fan-out across day partitions or a query-driven table.
6. Never add `ALLOW FILTERING` as the default fix.
7. Write positive tests with the full partition key and negative tests missing key parts.
8. If adding a new table, plan migration, backfill, dual-write, and rollback.
9. Monitor request p99, timeouts, bytes, and node read load.
10. Verify tenant ownership/data access controls remain intact.

**Downgrading consistency from `LOCAL_QUORUM` to `ONE` will not fix a missing partition key.**

## 22. Runbook B — Clustering Restriction or `ORDER BY` Rejected

**Scenario:** Query filters by `event_id` without `event_time` on clustering `(event_time, event_id)`, or tries `ORDER BY reading_value`.

1. Read the full partition/clustering keys and sort directions.
2. Verify equality prefix, range position, and any trailing restrictions after a range.
3. Verify whether `ORDER BY` uses clustering columns within a partition.
4. If `event_time` is known, bind both timestamp and event ID.
5. For direct lookup by ID, consider an `events_by_id` read model.
6. For top-N by reading value, align clustering order with the query.
7. Sort in Java only when results are strictly bounded and permitted.
8. Never guess that an index enables arbitrary ordering; check release/operators.
9. Test timestamp ties, uniqueness, and reverse-order cases.
10. Measure p95/p99, Cassandra read amplification, and correctness.

**`ORDER BY` within one partition never guarantees cluster-wide ordering.**

## 23. Runbook C — Wrong Literal Type or Java Codec

**Scenario:** `cqlsh` rejects an invalid date literal; Java binding a `String` to a `date` marker fails.

1. Pinpoint whether the error occurs during Java bind, server prepare, or server execution.
2. Verify schema types: `uuid`, `date`, `timestamp`, `decimal`, `timeuuid`, collections.
3. Inspect expected types of prepared markers.
4. Parse inputs early via `UUID.fromString`/`LocalDate.parse`/`Instant.parse`.
5. Use `BigDecimal` for exact decimals and `BigInteger` for large varints.
6. Verify UTC day bucketing and millisecond timestamp precision.
7. Check element types, frozen UDTs, and `null`/`unset` semantics.
8. Never "fix" by casting every value to `String`.
9. Add unit tests for invalid inputs and integration round-trips against real Cassandra.
10. Never retry client codec errors; log type mismatches without sensitive values.

**`cqlsh` literal parsing differs from typed binds in Java Driver.**

## 24. Runbook D — Filtering/Index: `InvalidQuery` Disappears Yet Performance Collapses

**Scenario:** `WHERE status='WARN'` failed; developers added `ALLOW FILTERING`, small lab data worked, and staging p99 spiked.

1. Clarify query intent: status within **one device/day** or system-wide?
2. If full partition key is known and row count is small, consider a bounded read and app-side filter.
3. To find all WARN events across partitions, design a `status/day/shard` table or indexed access path.
4. Verify index type (`2i`/SAI/SASI) and exact release/distribution operators—never assume parity.
5. Measure selectivity, matched partitions, tombstones, and SSTables scanned.
6. Cap response bytes, concurrency, and workload measurements.
7. Compare read p50/p95/p99, CPU/GC/disk, and index write amplification.
8. Never scan production to "prove" filtering works.
9. Canary the new query path with rollback triggers if SLO degrades.
10. Add negative tests preventing unauthorized filtering regressions.

**Disappearing `InvalidQuery` does not mean a query is production-safe.**

## 25. Runbook E — Counter, TTL, LWT, or `BATCH` Rejected

**Scenario:** App attempts `INSERT` into a counter, `SET count=10`, TTL on a counter, or mixing counters with regular mutations in a batch.

1. Check table column types: `counter` or regular `bigint`?
2. For counters, use `UPDATE ... SET count=count+delta` with the full key.
3. Never mix counter and non-counter columns contrary to CQL rules.
4. Verify whether `USING TTL` and `USING TIMESTAMP` are valid for that mutation.
5. If using `IF`, verify LWT semantics and supported conditions.
6. For batches, verify batch type and validity of every inner statement.
7. Assess idempotency: retrying a timed-out counter increment can double-count.
8. Never drop `IF` conditions into unconditional writes just to pass validation.
9. Consider a separate table if business needs absolute counts, TTL, or CAS instead of counters.
10. Test invalid statements, applied/not-applied LWT outcomes, and retries in the lab.

**Syntactically valid CQL alone does not guarantee correct counter or LWT semantics.**

## 26. Runbook F — Unknown Column/Table After Migration

**Scenario:** New app queries a newly added column; some coordinators report unknown column while `cqlsh` on another node already sees the new schema.

1. Confirm app cluster, keyspace, and local DC to avoid staging/prod mix-ups.
2. Check migration version/order and whether DDL completed.
3. Compare schemas across accessible nodes and check schema agreement.
4. Check quoted identifier casing and fully qualified keyspaces.
5. Inspect Java Driver schema metadata and prepare/re-prepare behavior.
6. Never delete `system_schema` entries or blindly drop/recreate data tables.
7. Apply additive schema migrations ahead of app rollouts whenever possible.
8. For rollbacks, verify compatibility across old/new apps and migration safety.
9. Canary CQL prepare+execute across nodes/clients until errors clear.
10. Post-mortem: update migration ordering, rollout gates, and schema tests.

**Unprepared/metadata races do not prove SSTable corruption.**

## 27. Runbook G — Valid Query Returns Zero Rows

**Scenario:** `SELECT` specifies both `device_id` and `event_day`, succeeds without error, yet returns 0 rows even though the producer ingested events.

1. Do not label this `InvalidQuery` when no server validation exception occurred.
2. Verify the actual `device_id` UUID and tenant ownership.
3. Compare writer vs. reader `event_day` calculation (UTC vs. local timezone).
4. Check `event_time` millisecond precision and full clustering key.
5. Verify the producer write actually succeeded; write timeouts have uncertain outcomes.
6. Check TTL, deletions, tombstones, and retention policies.
7. Check RF/CL, replica liveness, and read/write consistency levels.
8. Never run `ALLOW FILTERING` cluster-wide to hunt for "missing" rows.
9. If partition bucketing diverged, plan backfill, dual-read, and reconciliation.
10. Test date-boundary, late-arrival, deduplication, and read-back on the exact key.

**Zero rows is a valid query result, not the same class of failure as `InvalidQuery`.**

## 28. Designing Read Models for Required Queries

### 28.1. One Dataset May Require Multiple Tables

| Business Query | Query-Driven Read Model | Trade-Off |
|---|---|---|
| Latest 20 by device/day | `readings_by_device_day`, clustering time DESC | Multi-day needs bounded fan-out |
| Event by ID | `events_by_id`, partitioned by event ID | Extra table writes and reconciliation |
| WARN events by day | `events_by_status_day`, partitioned by status/day/shard | Hot partition / shard sizing |
| Events by tenant/day | `events_by_tenant_day_shard` | Per-shard fan-out |
| Realtime counts | Counter or pre-aggregated table | Retry/correctness trade-offs |
| Complex search/analytics | Search or analytical engine | Sync pipeline and extra ops |

Cassandra does not optimize a single normalized table for arbitrary `WHERE`/`JOIN`/`ORDER BY` queries like a relational SQL optimizer.

### 28.2. Example Direct Event-ID Lookup Table

~~~cql
CREATE TABLE IF NOT EXISTS troubleshooting_lab.events_by_id (
    event_id uuid PRIMARY KEY,
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_type text
);
~~~

The app looks up the event ID first, then queries the device/day table if full payload details are needed. When duplicating writes across tables, define consistency handling if one write succeeds while another times out; plan idempotency, repair/reconciliation, and aligned TTLs.

### 28.3. Query-First Migration Roadmap

~~~text
1. Document exact query and target p99/throughput.
2. Choose partition key/clustering aligned with the access path.
3. Test distribution, hotspots, tombstones, and TTL on staging.
4. Run additive versioned table/index migration safely.
5. Dual-write / backfill with checkpoints and rate limits.
6. Reconcile data against business invariants.
7. Canary readers with a rollback plan, then shift traffic gradually.
8. Monitor write amplification, disk, compaction, and repair.
9. Retire the old path once retention and consumer inventories permit.
~~~

Never attempt `ALTER TABLE` to transform an existing primary key into a new one; Cassandra imposes restrictions unlike RDBMS migrations. Changing a PK generally requires a new table and backfill.

### 28.4. Query Design and Security

Even when a request carries a full partition key and properly typed Java binds, the service must still **verify the principal has permission to read that device/tenant**. IDOR and cross-tenant leaks are application authorization failures that Cassandra `InvalidQuery` will not catch.

Likewise, never emit raw device or tenant IDs in metric labels, which inflates cardinality and leaks sensitive identifiers.

## 29. Positive/Negative Test Matrix for CQL Queries

| ID | Scenario | Expected Outcome | Test Layer |
|---|---|---|---|
| T01 | Full partition key by device/day | SELECT succeeds | Integration |
| T02 | Omit `event_day` from composite PK | Query rejected unless a supported access path exists | Integration |
| T03 | Only `event_day`, missing `device_id` | Not treated as a default indexed query | Integration |
| T04 | `device_id = null` on INSERT | PK invalid | Integration |
| T05 | Omit clustering key on INSERT | PK invalid | Integration |
| T06 | UPDATE regular cell missing `event_time` | Invalid key restrictions | Integration |
| T07 | DELETE full partition key | Verified as deleting whole partition | Isolated integration |
| T08 | Clustering prefix + range | Matches table design | Integration |
| T09 | Clustering suffix without prefix | Validation error or filtering per path/version | Integration |
| T10 | ORDER BY clustering column | Sorts within partition | Integration |
| T11 | ORDER BY regular column | Rejected when unsupported | Integration |
| T12 | Unindexed regular-column filter | Error/restriction per release | Integration |
| T13 | `IN` across multiple days | Verify support + bounded cost | Integration/load |
| T14 | Properly typed UUID bind | Succeeds | Unit + integration |
| T15 | Bind String to `date` marker | Driver codec/type error | Unit/driver |
| T16 | Unparseable date literal | Server validation error | Integration |
| T17 | Bind millisecond `Instant` | Exact precision round-trip | Integration |
| T18 | UUID v4 into `timeuuid` | Type/version validation error | Integration |
| T19 | Counter increment | Increments per counter semantics | Integration |
| T20 | Counter SET absolute value | Invalid counter mutation | Integration |
| T21 | Counter + TTL | Invalid/unsupported combination | Integration |
| T22 | LWT `IF NOT EXISTS` | `wasApplied()` accurate | Integration |
| T23 | LWT timeout/retry | Timeout never treated as rollback | Cluster integration |
| T24 | Wrong collection element type | Codec/validation error | Unit + integration |
| T25 | Invalid frozen UDT field mutation | Type/mutation restriction | Integration |
| T26 | `cqlsh` `DESCRIBE` in native execute | Not valid native CQL | Unit + integration |
| T27 | Quoted table name with different casing | Distinguishes identifiers | Integration |
| T28 | Schema migration pre-agreement | Fails/canaries and checks driver metadata | Multi-node lab |
| T29 | Wrong UTC/local `event_day` | 0 rows, valid query | Unit + integration |
| T30 | Missing tenant authorization | Rejected by app before CQL | Security integration |

### 29.1. Unit Tests Alone Do Not Prove CQL Support

A unit test mocking `CqlSession` confirms the app passes `UUID`/`LocalDate`, **not** whether the Cassandra server accepts the `WHERE`, `ORDER BY`, or schema/index combination. Run integration tests against the **real target server version**.

### 29.2. Negative Tests Must Stay Bounded and Safe

Test malformed queries and types in small lab keyspaces. Never run `DELETE partition`, `TRUNCATE`, or huge `ALLOW FILTERING` scans in production just to verify expected error paths.

### 29.3. Load-Test Queries That Just Became Valid

After adding a new index, table, or `ALLOW FILTERING`, "prepare/execute succeeded" is only the **functional gate**. You must also measure:

- Read p50/p95/p99 and timeout/availability budgets.
- Rows returned vs. rows scanned and tombstone density.
- SSTables per read, CPU/GC, and disk IOPS/await.
- Index build/compaction overhead and write amplification.
- Hot partitions/tenant skew and data growth.
- RF/CL and node failure/recovery headroom.

## 30. JUnit 5 Integration Test Example with Java Driver 4.x

### 30.1. Fixture for a Pre-Provisioned Cassandra Lab

This example assumes the keyspace/table from section 3 exists, Cassandra is running, and JUnit connects using controlled environment/secret configuration. It **illustrates contract tests** and was not compiled/run during authoring. Pin compatible Driver 4.x, JDK, and server versions.

~~~java
package demo.cassandra.validation;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.InvalidQueryException;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class CqlValidationIntegrationTest {
    static CqlSession session;

    @BeforeAll
    static void open() {
        // Lab/test container only; never commit secrets.
        session = CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress("127.0.0.1", 9042))
            .withLocalDatacenter("datacenter1")
            .build();
        // DC name must match the actual lab cluster.
    }

    @AfterAll
    static void close() {
        if (session != null) session.close();
    }

    @Test
    void fullPartitionKeyCanRead() {
        UUID id = UUID.fromString(
            "11111111-1111-1111-1111-111111111111");
        LocalDate day = LocalDate.of(2026, 11, 21);

        PreparedStatement stmt = session.prepare(
            "SELECT event_time, reading_value " +
            "FROM troubleshooting_lab.readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? " +
            "LIMIT 10");

        Row row = session.execute(stmt.bind(id, day)).one();

        // Seed data from section 3 must be loaded before this test.
        assertNotNull(row);
        assertNotNull(row.getInstant("event_time"));
    }

    @Test
    void missingCompositePartitionKeyPartIsRejected() {
        assertThrows(InvalidQueryException.class, () ->
            session.prepare(
                "SELECT event_time " +
                "FROM troubleshooting_lab.readings_by_device_day " +
                "WHERE device_id = ?"));
    }

    @Test
    void wrongDateLiteralIsRejected() {
        assertThrows(InvalidQueryException.class, () ->
            session.execute(
                "SELECT event_time " +
                "FROM troubleshooting_lab.readings_by_device_day " +
                "WHERE device_id = " +
                "11111111-1111-1111-1111-111111111111 " +
                "AND event_day = 'not-a-date'"));
    }

    @Test
    void sameInstantMayProduceDifferentLocalDateBuckets() {
        Instant eventTime =
            Instant.parse("2026-11-21T17:30:00Z");

        LocalDate utcDay = eventTime
            .atZone(java.time.ZoneOffset.UTC).toLocalDate();

        LocalDate vnDay = eventTime
            .atZone(java.time.ZoneId.of("Asia/Ho_Chi_Minh"))
            .toLocalDate();

        assertEquals(LocalDate.of(2026, 11, 21), utcDay);
        assertEquals(LocalDate.of(2026, 11, 22), vnDay);
    }
}
~~~

**Fixture limitations:**

- `127.0.0.1:9042`/`datacenter1` are assumptions; supply your lab's real contact points and local DC.
- When TLS/auth is enabled, configure the session with an approved `SSLContext`/auth provider—never disable security.
- Seed data must match the UUID, date, and schema before running tests.
- Different server/driver versions may raise distinct validation classes; pin versions in CI and assert the observed error contract without loosening tests to catch `RuntimeException`.
- This test does not validate RF=3, multi-DC, node failures, or index performance.

### 30.2. Fail Early at the Application Boundary

~~~java
import java.time.LocalDate;
import java.util.UUID;

record DeviceDayRequest(UUID deviceId, LocalDate eventDay) {
    DeviceDayRequest {
        if (deviceId == null || eventDay == null) {
            throw new IllegalArgumentException(
                "Both deviceId and eventDay are required");
        }
    }
}
~~~

Separate **HTTP 400 for invalid client input** from **server CQL `InvalidQuery` caused by developer/migration bugs**. Never return raw database exception messages to end users, as they can leak schema and query internals.

### 30.3. Catching Regressions When Partition Keys Change

If a migration evolves `readings_by_device_day` to include `tenant_id` in its composite partition key, update all positive tests to bind the tenant ID. Queries missing `tenant_id` must fail, and the API must reject them per policy rather than silently falling back to an unfiltered query.

## 31. Misconceptions That Cause Recurring Bugs

| Misconception | Reality |
|---|---|
| "CQL SELECT works like SQL; filter by any column." | Cassandra queries primarily follow partition/clustering/index paths |
| "Missing `event_day` just needs a higher timeout." | Timeouts cannot conjure a missing partition key |
| "Lowering CL from QUORUM to ONE fixes InvalidQuery." | CL does not alter CQL validation rules |
| "`ALLOW FILTERING` optimizes queries." | It can scan huge data at high cost |
| "`LIMIT 10` reads only 10 storage cells." | Tombstones and scan work may still be large |
| "`ORDER BY` regular column works because it's text/double." | `ORDER BY` depends on clustering order and query shape |
| "`IN` with 1,000 keys is always one cheap query." | Fan-out, latency, and resource costs have limits |
| "Clustering keys can skip prefixes freely." | Restrictions follow clustering order, indexes, and filtering rules |
| "`UPDATE` on missing row returns 0 affected rows." | CQL `UPDATE` is normally an upsert |
| "`DELETE` without clustering key is always invalid." | `DELETE` with full partition key deletes the entire partition |
| "Changing PK via `UPDATE SET` works." | Primary keys dictate row placement |
| "A Java date String matches a CQL `date` marker." | Prepared binds require `LocalDate` or a compatible codec |
| "`timeuuid` is any UUID." | `timeuuid` requires a time-based UUID version |
| "`double` works fine for decimal money." | Use `BigDecimal` when exact decimals are needed |
| "Counters allow `INSERT` or `SET 10`." | Counters require increment/decrement update semantics |
| "Retrying counters is harmless." | Retries can double-count |
| "TTL computes automatically from `event_time`." | TTL uses mutation expiration semantics |
| "LWT timeout means `IF` did not apply." | Outcome may be uncertain |
| "`BATCH` makes invalid statements valid." | Every inner mutation must still pass validation |
| "`BATCH` works like a multi-table SQL transaction." | Different guarantees; no arbitrary JOINs or rollback |
| "Cassandra joins tables automatically." | Design read models, denormalization, or an external layer |
| "`GROUP BY status` works on any table." | CQL aggregations enforce PK and release restrictions |
| "`OFFSET` paginates like SQL." | Use driver/CQL paging state |
| "`DESCRIBE` is native CQL in Java `execute`." | `DESCRIBE` is a `cqlsh`/client facility |
| "Unknown column means SSTables are corrupted." | Often schema, migration, keyspace, or casing mismatch |
| "Prepared statements stop all access bugs." | Binding stops injection; app must still enforce tenant authorization |
| "0 rows means `InvalidQuery`." | Query may be valid with wrong bucket, time, or TTL |
| "Driver codec exceptions need `nodetool repair`." | Fix Java type mapping, not replicas |
| "All OR/LIKE/index features behave identically across versions." | CQL/index support depends on release and distribution |

## 32. Practice Questions and Answers

### Question 1 — Partition Key

A table has `PRIMARY KEY ((device_id, event_day), event_time)`. A query uses only `WHERE device_id=?`. What is the main issue?

**Answer:** Missing `event_day` from the composite partition key for the normal access path. Supply a typed day or design a bounded multi-day read model/query—never raise timeouts.

### Question 2 — Zero Rows

A query supplies the full PK, throws no errors, yet returns 0 rows. Can we classify it as `InvalidQuery`?

**Answer:** No. Check key values, UTC vs. local day bucketing, timestamp precision, TTL, write outcomes, and CL. `InvalidQuery` is a distinct validation error.

### Question 3 — Clustering Prefix

A table has clustering `(event_time, event_id)`. Is querying by `event_id` without `event_time` efficient by default?

**Answer:** Not by default. Clustering restrictions require prefixes/ordering or index support. Direct lookup by event ID usually needs a dedicated ID-keyed table.

### Question 4 — `ORDER BY`

`ORDER BY reading_value DESC` fails when `reading_value` is a regular column. Why isn't it supported by default?

**Answer:** Cassandra orders data by clustering columns inside a partition, not arbitrary cluster-wide column sorts like SQL. Use a query-first schema or sort small bounded results in the app.

### Question 5 — `ALLOW FILTERING`

After adding `ALLOW FILTERING`, a query returns the expected 5 rows. Is it ready for production?

**Answer:** No. It may scan many partitions and tombstones; run load tests against realistic data sizes and SLOs, or fix the index/table design.

### Question 6 — `IN`

A query uses `event_day IN` for 1,000 days. If your release accepts the syntax, does that prove it is efficient?

**Answer:** No. Bound fan-out, bytes, concurrency, paging cost, and throughput. Narrow the query window or adopt a fitting data model.

### Question 7 — `UPDATE` Missing Clustering Key

`UPDATE ... SET status=? WHERE device_id=? AND event_day=?` fails on a table clustered by `event_time`. How do you fix it?

**Answer:** Identify the row with `event_time` (full key), or redesign the table if the business truly updates per-partition state.

### Question 8 — `DELETE` Partition

Can `DELETE FROM ... WHERE device_id=? AND event_day=?` be valid?

**Answer:** Yes—when all partition-key parts are given, it deletes the entire **partition**. This differs dramatically from deleting one row and must be used carefully.

### Question 9 — Immutable Primary Key

You want to change `event_time` using `UPDATE SET`. Is that valid?

**Answer:** No. Row placement is determined by the PK; usually you need an `INSERT` at the new key + `DELETE` of the old key with idempotency and reconciliation.

### Question 10 — `date` Type

A prepared CQL marker is `event_day date`, and Java binds `"2026-11-21"` as a `String`. Why can it fail even though `'2026-11-21'` works as a literal in `cqlsh`?

**Answer:** Contextual CQL literal parsing differs from typed Java Driver binds. Use `LocalDate` and the matching codec.

### Question 11 — `timestamp` vs. `date`

An event occurs at `2026-11-21T17:30:00Z`. Are the `event_day` dates in UTC and Vietnam the same?

**Answer:** No. UTC is `2026-11-21`, while Vietnam (+07) is `2026-11-22`. If writer and reader use different policies, the query is valid yet hits the wrong partition.

### Question 12 — `decimal`

Should a `decimal` column map through Java `double` before converting to `BigDecimal`, or bind `BigDecimal` directly?

**Answer:** Bind `BigDecimal` directly to preserve exact decimal precision when required; passing through `double` introduces rounding errors.

### Question 13 — `timeuuid`

Can a UUID v4 be bound to `timeuuid` simply because both use `java.util.UUID` in Java?

**Answer:** Not by default. CQL `timeuuid` requires a time-based UUID version/semantics.

### Question 14 — Null Primary Key

Is `INSERT` with `device_id=null` valid?

**Answer:** No. Every primary-key component must be non-null; validate at the API boundary before binding.

### Question 15 — Counter

Can you set `total_events=10` on a counter table via `SET total_events=10`?

**Answer:** No. Counters only support increment/decrement expressions; absolute values require a non-counter model.

### Question 16 — Counter Retry

A counter increment times out and the client retries. Could it count twice?

**Answer:** Yes. Counter increments are non-idempotent; a timeout does not prove the first attempt failed to apply.

### Question 17 — TTL

Does `USING TTL 3600` on a row whose `event_time` is from last week expire immediately because the event is old?

**Answer:** No. TTL follows mutation expiration semantics, not the value of the `event_time` data column.

### Question 18 — LWT

`INSERT IF NOT EXISTS` times out, and a retry returns `wasApplied()==false`. Can you conclude the first attempt failed?

**Answer:** No. The row may have been created by the first attempt; reconcile identity and outcome.

### Question 19 — `BATCH`

Does grouping 1,000 mutations with invalid `WHERE` clauses into a `BATCH` make them valid?

**Answer:** No. Every statement must pass validation, and large batches add heavy coordinator overhead.

### Question 20 — Collection Type

A CQL marker expects `map<text,int>`, yet Java binds `Map<String,String>`. Where does it fail?

**Answer:** Client codec/type check or server validation; fix the typed map and entry conversion instead of casting everything to text.

### Question 21 — `JOIN`

You need device names and readings in one CQL `JOIN`. Does Cassandra provide a general native SQL join planner?

**Answer:** No. Use denormalization/read models, bounded app orchestration, or an analytical engine depending on workload.

### Question 22 — `COUNT`

`SELECT count(*)` within a large partition can be valid. Is it always fast?

**Answer:** No. It may scan massive amounts of data; use pre-aggregated counters or read models when called frequently.

### Question 23 — `DESCRIBE`

`session.execute("DESCRIBE TABLE ...")` throws a syntax error. Why?

**Answer:** `DESCRIBE` is a `cqlsh`/client command, not a native CQL statement for `session.execute`. Use driver metadata or `system_schema` queries.

### Question 24 — Quoted Identifiers

Schema creates table `"DeviceEvents"`, and Java queries `deviceevents`. Why can it fail with unknown table?

**Answer:** Quoted identifiers are case-sensitive; use the exact qualified quoted name and keep migrations consistent.

### Question 25 — CL

`InvalidQuery` occurs due to a missing PK. Does downgrading `LOCAL_QUORUM` to `ONE` help?

**Answer:** No. CL alters replica acknowledgement/consistency guarantees, not CQL validation.

### Question 26 — Prepared Marker Error

`setString("event_day", ...)` throws an exception before `execute` is even called. Should you retry networking?

**Answer:** No. That is a client-side mapping bug; fix the setter/type and verify marker metadata.

### Question 27 — Schema Agreement

Some coordinators report unknown column right after a migration. What do you investigate?

**Answer:** Target cluster, migration order, schema agreement, quoted identifiers, and driver schema cache/re-prepare—never delete system tables.

### Question 28 — Tenant Authorization

CQL binds a properly typed device UUID belonging to another tenant. Does driver type safety prevent data exposure?

**Answer:** No. The application must enforce principal/tenant ownership before querying; prepared markers do not replace authorization.

### Question 29 — Error Handling

`InvalidQueryException` spikes after deployment. Should you catch it and return an empty list to avoid HTTP 500s?

**Answer:** No. An empty result differs from a validation failure and hides deployment bugs. Log error kind and query template safely, then roll back or fix.

### Question 30 — Query-First Design

A new requirement needs the top 20 WARN events per day across all devices. What are the right options?

**Answer:** Design a read model or release-appropriate index keyed by day/status/shard; evaluate hot partitions, write amplification, TTL, and SLOs rather than relying on full scans.

## 33. Checklist Before Merging an `InvalidQuery` Fix

### 33.1. Diagnosis

~~~text
[ ] Distinguished InvalidQuery, SyntaxError, codec, auth, timeout, and Unprepared.
[ ] Captured exception class, safe cause, query template, and UTC timestamp.
[ ] Identified whether failure happens at prepare, bind, execute, or paging.
[ ] Inspected live schema, PK, clustering order, columns/types, and indexes.
[ ] Verified keyspace, quoted identifiers, migration version, and schema agreement.
[ ] Verified exact Cassandra/driver releases and their CQL rules.
[ ] Did not blame server downtime for a client codec error or InvalidQuery.
~~~

### 33.2. Query and Data Model

~~~text
[ ] Reads/updates supply full appropriate partition/clustering keys.
[ ] Clustering ranges respect prefix rules; ORDER BY matches clustering rules.
[ ] ALLOW FILTERING is not used merely to silence production errors.
[ ] IN/fan-out enforces partition, byte, concurrency, and deadline caps.
[ ] Regular-column filters have a suitable access path/index/table.
[ ] No relational SQL JOIN/subquery/OFFSET assumptions exist in CQL.
[ ] Aggregations/GROUP BY/DISTINCT checked for support and scan cost.
[ ] DELETE partition vs. DELETE row clearly distinguished.
[ ] Primary-key changes use a new table + backfill where needed.
[ ] Query-first design applied for new lookup/sort needs.
~~~

### 33.3. Data Types and Mutation Semantics

~~~text
[ ] UUID/LocalDate/Instant/BigDecimal/BigInteger bound with exact types.
[ ] Timestamp precision and event_day timezone aligned between writers and readers.
[ ] timeuuid uses the right UUID version.
[ ] Collections/UDTs/tuples match exact element/field types.
[ ] null and unset semantics verified; null PKs disallowed.
[ ] Counter increments, TTL, and conditional limits match release rules.
[ ] BATCH holds only valid mutations, never misused for bulk transactions.
[ ] LWT conditions, wasApplied(), timeouts, and retries handled properly.
[ ] Counter/PK types never altered casually via ALTER.
~~~

### 33.4. Java, Tests, and Rollout

~~~text
[ ] Prepared CQL uses markers for values; dynamic identifiers strictly allowlisted.
[ ] API input validation fails fast before hitting Cassandra.
[ ] Codec/type errors are never retried infinitely.
[ ] Server InvalidQuery is never swallowed into an empty result.
[ ] Zero secrets, tenant IDs, bind values, or raw unsafe CQL in logs.
[ ] Unit tests validate UUID/date/Instant/limit/tenant ownership.
[ ] Integration tests run against the exact Cassandra/driver versions.
[ ] Negative tests verify missing key, wrong type, and invalid ORDER BY.
[ ] Positive read/write tests use seeded data and proper CL.
[ ] If adding an index/table, tested p99, timeouts, compaction, and write cost.
[ ] If changing PK, planned dual-write, backfill, checkpoints, and reconciliation.
[ ] Migrations deploy ahead of app rollout with clear canary and rollback.
[ ] STEP 6 specialized QA is not executed during this writing step.
~~~

## 34. Summary

To resolve **`InvalidQuery` caused by key restrictions, data types, or unsupported queries** in Cassandra:

1. **Separate server validation from parser, Java codec, auth, and timeout errors.** Each layer demands a different remedy.
2. **Design tables for queries:** partition keys govern placement, clustering keys govern in-partition range and sort order—never expect arbitrary SQL `WHERE`/`ORDER BY`.
3. **Never omit parts of a composite partition key** or skip clustering prefixes without a release-supported access path.
4. **`ALLOW FILTERING` is not query optimization**, and `LIMIT`/page size does not bound total scan/IO cost.
5. **Bind exact CQL types via Java Driver:** `UUID`, `LocalDate`, `Instant`, `BigDecimal`, collections/UDTs; literal parsing and typed binds behave differently.
6. **Verify DML rules per operation:** `INSERT`/`UPDATE`/`DELETE` differ on full-key rules, and counters/TTL/LWT/batches have distinct semantics.
7. **Do not treat CQL as relational SQL:** joins, subqueries, `OR`, `GROUP BY`, `ORDER BY`, and `OFFSET` carry version-specific limits and behaviors.
8. **A valid query can still return wrong data or perform poorly** due to `event_day` timezone drift, retention, low index selectivity, or skewed query distribution.
9. **Never lower CL, run repair, add retries, or return empty lists to hide `InvalidQuery`.** Fix the data model, mapping, schema migration, or query at its root cause.
10. **Verify with both negative and positive tests** on the real Cassandra version, and measure p99/CPU/disk whenever changing indexes or schemas.
11. **Track schema agreement, quoted identifiers, and driver prepared metadata** during rolling migrations.
12. **Preserve security and correctness:** prepared statements block value injection, yet tenant authorization and ownership remain the application's responsibility.

The most useful diagnostic question is not "What syntax makes the error disappear?", but: **"What data must this query return, which partition/clustering key supports that access path, is Java binding the exact types, does our Cassandra release support the operator, and does the fix preserve correctness and SLOs under real load?"** Answering these turns `InvalidQuery` into a clear design and validation signal—not an excuse for full scans, weakened consistency, or hidden failures.
