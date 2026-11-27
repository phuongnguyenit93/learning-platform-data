# ResultSet, Row, and Reading Values by Column Name or Index in the Cassandra Java Driver

## 1. Objectives and Context

Apache Cassandra is a distributed **wide-column** database. Applications design tables around queries, use **partition keys** to locate the appropriate replicas, execute CQL through a coordinator, and choose **consistency levels** per correctness/availability needs.

From Java, when running a `SELECT` with **Apache Cassandra Java Driver 4.x**, a basic flow is:

~~~text
CqlSession
    |
    | execute(Statement)
    v
ResultSet
    |
    | one() / iterator()
    v
Row
    |
    | getUuid("device_id")
    | getInstant("event_time")
    | getDouble("reading_value")
    v
Java values / DTO
~~~

This lesson belongs to the **Java Driver Basics** chapter in the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. Its focus is understanding **what `ResultSet` contains, how to retrieve `Row` safely, and the difference between reading values by column name vs. column index**.

After this lesson, you will be able to:

1. Explain what `CqlSession.execute()` returns and distinguish `ResultSet` from `Row`.
2. Use `one()`, iteration, and `all()` appropriately for expected result sizes.
3. Read values using **Java/CQL-type-matched** getters by **column name** or **0-based index**.
4. Check `null`, unselected columns, and aliases to prevent silent conversion bugs.
5. Understand automatic paging in `ResultSet` and the risk of retaining too many `Row` objects in RAM.
6. Use `ColumnDefinitions`, write safe tests, and log safely when schemas or queries change.
7. Distinguish standard `SELECT` results from **LWT** (`IF NOT EXISTS`, `IF ...`) responses.

**Version scope:** Java examples use the DataStax/Apache Cassandra Java Driver **4.x** API with `com.datastax.oss.driver.api.*` packages. Driver **3.x** uses `com.datastax.driver.core.*` and different methods/Java types; never copy 4.x code into a 3.x project without migrating.

## 2. Preparing CQL Table and Data for Practice

### 2.1. Table with Clear Partition Key and Clustering Key

Assume the lab cluster has a datacenter named `dc1` and enough nodes for RF=3:

~~~cql
-- Run on an authorized LAB CLUSTER; never recreate a production
-- keyspace that already holds data.
CREATE KEYSPACE telemetry
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry.readings_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    reading_value double,
    status text,
    tags list<text>,
    calibration_factor decimal,
    valid boolean,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

- **Partition key** is `(device_id, event_day)`. Queries providing both values target a single partition.
- **Clustering key** `event_time` orders rows within the partition from newest to oldest.
- `reading_value` is `double`, `status` is `text`, `calibration_factor` is `decimal`, and `tags` is a collection.
- Non-primary-key columns may have no value in a given row; the application must handle `null`.

Example inserting two rows:

~~~cql
INSERT INTO telemetry.readings_by_device_day (
    device_id, event_day, event_time,
    reading_value, status, tags, calibration_factor, valid
) VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:30:00Z',
    24.6, 'OK', ['indoor', 'sample'], 1.02, true
);

-- Omit status, tags, and calibration_factor.
INSERT INTO telemetry.readings_by_device_day (
    device_id, event_day, event_time, reading_value, valid
) VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:29:00Z',
    24.1, true
);
~~~

This dataset separates **"row exists with some null columns"** from **"query found no row"**.

### 2.2. Base Query and Column Order

~~~cql
SELECT event_time, reading_value, status, valid
FROM telemetry.readings_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 10;
~~~

The four selected columns and their positions are:

| `Row` Index (0-based) | Column Name | CQL Type | Java Getter |
|---:|---|---|---|
| 0 | `event_time` | `timestamp` | `getInstant(0)` |
| 1 | `reading_value` | `double` | `getDouble(1)` |
| 2 | `status` | `text` | `getString(2)` |
| 3 | `valid` | `boolean` | `getBoolean(3)` |

**Indices follow the column list in the `SELECT` projection**, not the column order declared in `CREATE TABLE` or SSTable storage order.

## 3. Roles of CqlSession, ResultSet, and Row

### 3.1. Processing Flow Diagram

~~~mermaid
sequenceDiagram
    participant A as Java Application
    participant D as CqlSession / Driver
    participant C as Coordinator
    participant R as Replica
    A->>D: execute(boundStatement)
    D->>C: CQL request
    C->>R: Read partition per CL
    R-->>C: Matching data
    C-->>D: First result page
    D-->>A: ResultSet
    A->>A: one() or iterate Rows
    Note over A,D: May auto-fetch next page as needed
    A->>A: Row.getString / getInstant / getDouble
~~~

`CqlSession` manages connections, metadata, requests, and driver lifecycle. It should be **reused** across service requests rather than created per HTTP call.

`ResultSet` is the **synchronous result consumption interface** of a statement execution. It yields rows in result order, integrated with paging and execution metadata. A `ResultSet` **does not mean an entire table is already loaded in the heap**.

`Row` is **a single row in the result**; it holds values matching the columns/projections selected or returned by the statement. A `Row` never magically includes columns you did not request.

### 3.2. Core Methods Reference

| Driver 4.x API | Purpose | Notes |
|---|---|---|
| `session.execute(statement)` | Executes synchronously, returns `ResultSet` | May wait on network; never create a session per request |
| `resultSet.one()` | Gets the **next row**, or `null` if exhausted | Consumes the row; iteration resumes from the following row |
| `for (Row row : resultSet)` | Iterates remaining rows | May trigger fetching the next page |
| `resultSet.all()` | Collects **all remaining rows** into a `List` | Risks high memory consumption |
| `resultSet.getColumnDefinitions()` | Result column metadata | Useful to inspect names/order/types |
| `row.getString("status")` | Reads column value by name | Column must be returned and type must match |
| `row.getString(2)` | Reads column value by index | 0-based index; fragile when `SELECT` order changes |
| `row.isNull("status")` | Checks whether cell is null | Prevents confusing null with primitive defaults |
| `resultSet.getAvailableWithoutFetching()` | Rows immediately readable without fetching | **Not the total row count** of the query |
| `resultSet.isFullyFetched()` | Whether all pages have been fetched | Unconsumed buffered rows may still remain |
| `resultSet.wasApplied()` | Application status of conditional/LWT query | Never substitute `one()` for regular `SELECT`s |

This lesson uses synchronous `ResultSet`. Java Driver 4.x also provides `AsyncResultSet` for async, which handles paging differently; do not treat `ResultSet` and `AsyncResultSet` as sharing identical methods.

## 4. Complete Java Example: Querying and Reading the First Row

### 4.1. A Simple Repository

The snippet below assumes `CqlSession` is configured with valid contact points, local DC, authentication, and TLS for the environment, and passed into the repository at construction time.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

public final class ReadingRepository {
    private final CqlSession session;
    private final PreparedStatement latestQuery;

    public ReadingRepository(CqlSession session) {
        this.session = Objects.requireNonNull(session);
        this.latestQuery = session.prepare(
            "SELECT event_time, reading_value, status, valid " +
            "FROM telemetry.readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT 1"
        );
    }

    public void printLatest(UUID deviceId, LocalDate day) {
        BoundStatement statement = latestQuery.bind(deviceId, day)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        ResultSet result = session.execute(statement);
        Row row = result.one();

        if (row == null) {
            System.out.println("No data for partition/day");
            return;
        }

        Instant time = row.getInstant("event_time");
        double value = row.getDouble("reading_value");
        String status = row.getString("status");
        boolean valid = row.getBoolean("valid");

        System.out.println(
            "At " + time + ": " + value +
            ", status=" + status + ", valid=" + valid);
    }
}
~~~

Here `SELECT ... LIMIT 1` caps total returned rows. For `getInstant("event_time")` to work, `SELECT` must include that column. `status` can be `null`; printing `"null"` is for demonstration only—production needs explicit null/mapping handling.

### 4.2. What Happens If There Is No Row?

~~~java
ResultSet rs = session.execute(statement);
Row first = rs.one();

if (first == null) {
    // No row matched the query.
    return;
}

// Never call first.getString(...) when first == null.
String status = first.getString("status");
~~~

**`Row == null`** is completely different from **`Row != null` with `row.getString("status") == null`**:

- Row absent: `WHERE` matched no live record, or `LIMIT`/state produced an empty result.
- Row present with null column: the row was selected, yet that specific cell has no live value at read time.

This distinction matters when a Java app decides between returning HTTP `404` vs. returning a record with an unset field.

## 5. Reading Values by **Column Name**

### 5.1. Name-Based Getters Are Readable and Resilient to SELECT Reordering

~~~java
Instant at = row.getInstant("event_time");
double value = row.getDouble("reading_value");
String status = row.getString("status");
boolean valid = row.getBoolean("valid");
~~~

Pros:

- Code clearly expresses each field's business meaning.
- Reordering columns in `SELECT` while keeping names preserves valid mapping.
- Code reviews easily verify which Java type is extracted.
- Adding or removing columns keeps focus on schema and related getters.

Cons:

- Must ensure the exact name or **alias** actually appears in the result.
- Selecting multiple columns with colliding names/aliases makes name lookup ambiguous.
- Quoted case-sensitive CQL identifiers behave differently from unquoted names.

**Best practice:** write explicit column lists in `SELECT` and treat column names/aliases as a stable contract between repository and DTO.

### 5.2. Column Aliases Change the Name Visible in ResultSet

Example:

~~~cql
SELECT event_time AS occurred_at,
       reading_value AS measured_value,
       status
FROM telemetry.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 10;
~~~

Results are mapped using the **returned column names**:

~~~java
Instant occurredAt = row.getInstant("occurred_at");
double measuredValue = row.getDouble("measured_value");
String status = row.getString("status");
~~~

Never keep calling `row.getInstant("event_time")` when the projection aliases that column as `occurred_at`. Whenever aliases change, update mappers and tests to match.

### 5.3. Quoted Identifiers and Case Sensitivity

Standard CQL normalizes **unquoted identifiers** to lowercase; **quoted identifiers** preserve case.

~~~cql
-- Illustrating a legacy table with special schema naming.
-- If a column was declared as "SensorValue", use the exact
-- quoted name in CQL rather than sensorvalue.
SELECT "SensorValue"
FROM legacy.samples
WHERE device_id = ?;
~~~

In Java, if returned names use special quoting, use `CqlIdentifier.fromCql(...)` after inspecting the actual schema/alias. **Never lowercase every string blindly** as a blanket workaround, as that breaks quoted identifiers.

For standard development, stick to clear lowercase `snake_case` identifiers and avoid quoted identifiers unless required by business constraints.

## 6. Reading Values by **Column Index**

### 6.1. Indices Are 0-Based

Given:

~~~cql
SELECT event_time, reading_value, status, valid
FROM telemetry.readings_by_device_day
WHERE device_id = ? AND event_day = ?
LIMIT 10;
~~~

Java:

~~~java
Instant at = row.getInstant(0);     // event_time
double value = row.getDouble(1);    // reading_value
String status = row.getString(2);   // status
boolean valid = row.getBoolean(3); // valid
~~~

The result has four positions: **0, 1, 2, 3**. Index `4` is invalid for this projection.

### 6.2. Index Is Result Position, Not DDL Column Order

If changed to:

~~~cql
SELECT status, event_time, valid, reading_value
FROM telemetry.readings_by_device_day
WHERE device_id = ? AND event_day = ?
LIMIT 10;
~~~

then mapping shifts:

| Index | Name After Reordering Projection | Matching Getter |
|---:|---|---|
| 0 | `status` | `getString(0)` |
| 1 | `event_time` | `getInstant(1)` |
| 2 | `valid` | `getBoolean(2)` |
| 3 | `reading_value` | `getDouble(3)` |

Old code calling `row.getInstant(0)` breaks because index 0 is now `text`. The failure surfaces as a codec decode error rather than a clear "you reordered SELECT" message.

### 6.3. When Should You Use Indices?

Index access is useful when:

- Writing a mapper for a **fixed projection** covered by unit/integration tests.
- Reading a single expression whose generated column name is awkward or unstable.
- Handling dynamic column definitions cleanly, such as metadata rendering for an allowlisted query.

Still, **index-based getters do not automatically make the whole system noticeably faster**. Cassandra latency is dominated by networking, replicas, tombstones/SSTables, pagination, and payload size rather than column-name lookup on a `Row`.

### 6.4. Resolving Indices Safely from Metadata

Avoid hardcoding `2` when you can look up the name via `ColumnDefinitions`:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.cql.ColumnDefinitions;

ColumnDefinitions defs = row.getColumnDefinitions();
int statusIndex =
    defs.firstIndexOf(CqlIdentifier.fromCql("status"));

if (statusIndex < 0) {
    throw new IllegalStateException(
        "SELECT result did not contain status");
}

String status = row.getString(statusIndex);
~~~

`firstIndexOf` locates the first occurrence of the column name. If a projection has duplicate column names/aliases, disambiguate the projection instead of hoping "first" is the intended one.

## 7. `ColumnDefinitions`: Knowing Which Columns a Row Contains

### 7.1. Inspecting Row Metadata

~~~java
import com.datastax.oss.driver.api.core.cql.ColumnDefinition;
import com.datastax.oss.driver.api.core.cql.ColumnDefinitions;

ColumnDefinitions defs = row.getColumnDefinitions();

for (int i = 0; i < defs.size(); i++) {
    ColumnDefinition def = defs.get(i);
    System.out.println(
        "index=" + i +
        " name=" + def.getName().asInternal() +
        " cqlType=" + def.getType());
}
~~~

`ColumnDefinitions` is available on both `ResultSet` and `Row`. Useful checks when debugging:

- **Column count**: how many projections were selected?
- **Actual names/aliases**: does the mapper match them?
- **CQL data types**: do getters match the expected Java types?
- **Return order**: is index-based code still valid after a query edit?

Never dump entire `Row` contents to production logs just while debugging metadata. **Column names and types** are less sensitive than **values**, though you must still obey system schema security policies.

### 7.2. Distinguishing Unselected Columns from Null Values

Case A:

~~~cql
SELECT event_time, reading_value
FROM telemetry.readings_by_device_day
WHERE device_id = ? AND event_day = ?
LIMIT 1;
~~~

`status` **is not in `ColumnDefinitions`**. Calling `getString("status")` in Java is a mapping/projection bug, **not** a valid `null` value.

Case B:

~~~cql
SELECT event_time, reading_value, status
FROM telemetry.readings_by_device_day
WHERE device_id = ? AND event_day = ?
LIMIT 1;
~~~

`status` is in the projection. If the cell has no value, `row.isNull("status")` is `true` and `getString("status")` returns `null`.

This distinction lets APIs cleanly separate "attribute not requested" from "selected, currently unset".

### 7.3. Avoid Duplicate Column Names

A projection with duplicate aliases makes name-based access ambiguous. When selecting two distinct expressions, assign **two distinct aliases** or use verified indices.

Never treat `row.getString("x")` as unambiguous when `ColumnDefinitions` lists multiple projections named `x`.

## 8. Getters Must Match CQL Types

### 8.1. Common Mappings in Driver 4.x

| CQL Type | Common Java Type | `Row` Getter |
|---|---|---|
| `text` / `varchar` / `ascii` | `String` | `getString(...)` |
| `uuid` / `timeuuid` | `UUID` | `getUuid(...)` |
| `tinyint` | `byte` | `getByte(...)` |
| `smallint` | `short` | `getShort(...)` |
| `int` | `int` | `getInt(...)` |
| `bigint` / `counter` | `long` | `getLong(...)` |
| `varint` | `BigInteger` | `getBigInteger(...)` |
| `float` | `float` | `getFloat(...)` |
| `double` | `double` | `getDouble(...)` |
| `decimal` | `BigDecimal` | `getBigDecimal(...)` |
| `boolean` | `boolean` | `getBoolean(...)` |
| `timestamp` | `Instant` | `getInstant(...)` |
| `date` | `LocalDate` | `getLocalDate(...)` |
| `time` | `LocalTime` | `getLocalTime(...)` |
| `blob` | `ByteBuffer` | `getByteBuffer(...)` |
| `list<text>` | `List<String>` | `getList(..., String.class)` |
| `set<uuid>` | `Set<UUID>` | `getSet(..., UUID.class)` |
| `map<text,int>` | `Map<String,Integer>` | `getMap(..., String.class, Integer.class)` |

This table reflects common **default codecs**. Custom codecs or user-defined types may expose different APIs; verify against your actual Java Driver version.

Example:

~~~java
java.util.UUID id = row.getUuid("device_id");
java.time.Instant time = row.getInstant("event_time");
java.time.LocalDate day = row.getLocalDate("event_day");
java.math.BigDecimal factor =
    row.getBigDecimal("calibration_factor");
java.util.List<String> tags =
    row.getList("tags", String.class);
~~~

These calls only work when **those exact columns appear in `SELECT`**. Even though `device_id` is the table's partition key, `getUuid("device_id")` still fails if `SELECT` omits `device_id`.

### 8.2. `timestamp` Is Not `LocalDateTime`

CQL `timestamp` represents an epoch instant; in Driver 4.x, `getInstant(...)` is the right way to read absolute instants. `LocalDateTime` carries no timezone and is **not the default mapping replacement for `Instant`**.

When displaying in a specific timezone:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant eventTime = row.getInstant("event_time");
ZonedDateTime local =
    eventTime.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Use this strictly for presentation/business formatting. Never convert timezones before comparing replica timestamps or event ordering.

### 8.3. `decimal` and `double` Have Different Semantics

- `double` is binary floating point—suitable for measurements, poor for currency.
- `decimal` maps to `BigDecimal`—suitable for exact decimal precision.

Never replace `getBigDecimal("amount")` with `getDouble("amount")` just because both are "numbers". For monetary amounts and exact comparisons, preserve exact types, scales, and rounding rules.

### 8.4. Collections, UDTs, and Blobs

Example reading tags:

~~~cql
SELECT tags, calibration_factor
FROM telemetry.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 10;
~~~

Java:

~~~java
List<String> tags = row.getList("tags", String.class);
BigDecimal factor =
    row.getBigDecimal("calibration_factor");

if (tags != null) {
    for (String tag : tags) {
        useTag(tag); // Illustrative helper.
    }
}
~~~

Collections can cause heavy allocations if rows contain many elements. For blobs, watch size, reference retention, and quotas before materializing giant `byte[]` arrays.

For UDTs, typically retrieve `UdtValue` and read fields by name/type or register a custom codec. **Never coerce UDTs with `getString`** when the CQL type is not text.

## 9. Handling Nulls Safely and Preserving Data Meaning

### 9.1. `isNull` Before Primitive Getters

CQL allows cells to have no live value. Java **primitive** getters like `getDouble` or `getBoolean` cannot represent `null` in their return type.

Therefore, whenever null has business meaning, check first:

~~~java
Double value = row.isNull("reading_value")
    ? null
    : row.getDouble("reading_value");

Boolean valid = row.isNull("valid")
    ? null
    : row.getBoolean("valid");

String status = row.getString("status");
// status may be null.
~~~

**Never assume "missing reading" equals `0.0`** or "missing valid flag" equals `false`. If a mapper skips null checks, business data can silently corrupt without throwing an exception.

### 9.2. A DTO Expressing Nulls Intentionally

~~~java
import java.time.Instant;

public record ReadingDto(
    Instant eventTime,
    Double value,
    String status,
    Boolean valid
) {}

static ReadingDto mapReading(Row row) {
    return new ReadingDto(
        row.getInstant("event_time"),
        row.isNull("reading_value")
            ? null : row.getDouble("reading_value"),
        row.getString("status"),
        row.isNull("valid")
            ? null : row.getBoolean("valid")
    );
}
~~~

This uses a Java `record` (Java 16+). On Java 11 or other driver/JDK versions, use a standard DTO class. Before upgrading JDKs, verify the compatibility matrix of your Cassandra driver/libraries and platform.

In larger codebases, `Optional` may fit return boundaries or domain objects with explicit state. **Never invent fake default values** merely to avoid nullable fields.

### 9.3. Nulls, Missing Rows, and Missing Projections

| Situation | How to Detect | Interpretation |
|---|---|---|
| Query returned no row | `resultSet.one() == null` | No matching live record |
| Row includes `status` with no value | `row.isNull("status")` | Null cell in CQL result |
| `status` omitted from `SELECT` | `ColumnDefinitions` lacks column | Mapper/projection mismatch |
| Java reads wrong type | Getter/codec throws error | Schema or mapper bug |
| Row exists, `valid=false` | `isNull("valid")==false` and `getBoolean(...)==false` | Valid `false` value, not null |

Never store the literal string `"null"` in data or JSON just because a logger printed `null`.

## 10. `one()`, Iteration, and `all()`: Three Different Consumption Patterns

### 10.1. `one()` Consumes the Next Row

~~~java
ResultSet rs = session.execute(statement);

Row first = rs.one();
Row second = rs.one();

// If rows remain, iteration starts from the next unconsumed row.
for (Row rest : rs) {
    process(rest);
}
~~~

`one()` **advances** the `ResultSet` cursor. Therefore:

~~~java
Row first = rs.one();
for (Row row : rs) {
    // Does not revisit 'first' unless the query is executed again.
}
~~~

does not mean "peek at first then iterate from the start". To process everything, handle `first` explicitly or start the loop from the beginning.

### 10.2. Iterating Row by Row Suits Large Results

~~~java
ResultSet rs = session.execute(statement);
long count = 0;

for (Row row : rs) {
    Instant at = row.getInstant("event_time");
    Double value = row.isNull("reading_value")
        ? null : row.getDouble("reading_value");

    writeToBoundedSink(at, value); // Illustrative helper.
    count++;
}

System.out.println("Processed rows: " + count);
~~~

This keeps application memory bounded **provided `writeToBoundedSink` does not accumulate every row in memory**. The driver still allocates page buffers and internal resources; streaming row-by-row does not mean peak heap is literally one `Row`.

### 10.3. `all()` Materializes All Remaining Rows

~~~java
ResultSet rs = session.execute(statement);
List<Row> allRemaining = rs.all();
~~~

`all()` is convenient for **small, bounded queries**, yet dangerous for hundreds of thousands or millions of rows:

- The driver fetches every remaining page.
- A Java `List` retains all rows and references to decoded values/buffers.
- Heap allocation, GC pauses, and `OutOfMemoryError` risk climb.
- Long-running scans stress replicas and networks as the client pulls everything.

**Page size 100 does not stop `all()` from fetching 100,000 rows across 1,000 pages.** Page size targets rows per page, not total result count.

### 10.4. A ResultSet Is Not a Reusable Container

Never assume you can call `rs.iterator()` repeatedly to re-read rows from the start. `ResultSet` is a stateful consumption interface; rows consumed via `one()` or iteration **cannot be reset like an `ArrayList`**.

If you need to re-read data:

- Re-execute the query with appropriate conditions.
- Buffer a small, bounded subset in a DTO `List` when business logic truly needs it.
- For large datasets, stream to a bounded file/sink and account for consistency between separate reads.

## 11. Paging: ResultSet Does Not Necessarily Hold All Rows Up Front

### 11.1. Synchronous Paging Mechanics

Java Driver 4.x automatically **fetches the next page when the iterator/`one()` needs more rows**. Example query:

~~~cql
SELECT event_time, reading_value, status, valid
FROM telemetry.readings_by_device_day
WHERE device_id = ? AND event_day = ?
LIMIT 200;
~~~

Java:

~~~java
BoundStatement bs = prepared.bind(deviceId, eventDay)
    .setPageSize(50)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

ResultSet rs = session.execute(bs);
for (Row row : rs) {
    process(row);
}
~~~

Under ideal conditions, up to 200 rows split into roughly 4 pages of 50 rows each. In practice, a page may hold fewer rows due to byte limits, data sizes/versions, or server conditions.

**`LIMIT 200`** caps *total query rows*. **`setPageSize(50)`** sets *target rows per page*. They do not replace each other.

### 11.2. Two Page Inspection Methods

~~~java
int ready = rs.getAvailableWithoutFetching();
boolean fullyFetched = rs.isFullyFetched();

System.out.println(
    "Ready locally=" + ready + ", fullyFetched=" + fullyFetched);
~~~

- `getAvailableWithoutFetching()` returns how many rows can be read immediately **without another network fetch**.
- `isFullyFetched()` tells whether all pages of the query have been retrieved.
- `ready == 0` **does not prove results are exhausted** while `fullyFetched == false`.
- `fullyFetched == true` **does not prove the application consumed all rows**; buffered rows may remain client-side.

Never use these methods as `COUNT(*)` or total table row count.

### 11.3. Time to First Page Differs from Total Consume Time

~~~text
T0: session.execute(statement) starts
T1: first page arrives, ResultSet returns
T2: app iterates/fetches remaining required pages
T3: all results processed

Execute latency: roughly T1 - T0
Consume latency: roughly T3 - T0
~~~

For multi-page queries, timing only `session.execute()` misses the time spent fetching subsequent pages. When logging slow queries or benchmarks, explicitly state whether timing measures **time to first page or full consumption**.

### 11.4. Pages Are Not a Transactional Snapshot

Pages can be fetched at **different points in time**. While iterating, concurrent writes, deletes, or TTL expirations can alter data read in later pages. Paging does not create an isolated snapshot like a long RDBMS transaction.

When APIs need stable time-ordered pagination, design around partition/clustering keys and evaluate **paging state or keyset pagination**. Never emulate SQL `OFFSET` by fetching and discarding thousands of rows each time.

## 12. Rows Returned by Standard SELECT, Aggregates, and LWT

### 12.1. Standard SELECT

~~~cql
SELECT event_time, reading_value
FROM telemetry.readings_by_device_day
WHERE device_id = ? AND event_day = ?
LIMIT 10;
~~~

Returns `Row` objects with **two columns**: `event_time` and `reading_value`.

### 12.2. Aggregates Return Different Types

Example counting rows inside a **known small partition**:

~~~cql
SELECT COUNT(*) AS total
FROM telemetry.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?;
~~~

Java:

~~~java
Row countRow = session.execute(statement).one();
if (countRow == null) {
    throw new IllegalStateException(
        "Aggregate query returned no row");
}
long total = countRow.getLong("total");
~~~

`COUNT(*)` normally returns **`bigint`/`long`**, not `int`. **Never run `COUNT(*)` across large tables as a routine size metric**: aggregation scans vast amounts of data and consumes heavy CPU/I/O.

### 12.3. Conditional Writes/LWT: `wasApplied()`

Example conditional insert:

~~~cql
INSERT INTO telemetry.readings_by_device_day (
    device_id, event_day, event_time, reading_value
) VALUES (?, ?, ?, ?)
IF NOT EXISTS;
~~~

Java:

~~~java
ResultSet rs = session.execute(conditionalInsertStatement);

if (rs.wasApplied()) {
    System.out.println("Conditional insert applied");
} else {
    System.out.println("Condition was not satisfied");
}
~~~

`wasApplied()` is the clear way to check **whether a conditional statement succeeded**. Never check `resultSet.one() == null` as an LWT success test.

When a condition fails, some conditional responses include the existing row's data; the schema of that row depends on the statement and version. If you read it, inspect `ColumnDefinitions` carefully. LWT incurs higher consensus cost than regular writes; **never add `IF NOT EXISTS` to every `INSERT` just to get a boolean flag**.

## 13. Getters by Name vs. by Index: Which Is Better?

| Criterion | By Name, e.g. `getString("status")` | By Index, e.g. `getString(2)` |
|---|---|---|
| Readability | High; names convey intent | Requires checking `SELECT` order |
| Reordering projections | Usually keeps working if names stay | Can read wrong column/type |
| Renaming aliases | Mapper must update name | Unaffected if position stays |
| Fixed projection, few columns | Great fit | Works if covered by tests |
| Query picked from allowlist | Easy if aliases stay consistent | Requires per-template index map |
| Debugging mapping bugs | Missing column spotted easily | Prone to off-by-one or order drift |
| Performance optimization | Usually fast enough | Does not noticeably cut Cassandra latency |
| Duplicate column names | Must avoid or check definitions | Index is positional, requires strict projection contract |

**Baseline recommendation:** for business repositories, prefer **name-based getters** and explicit projections. If index-based getters are chosen for technical reasons, lock down a fixed projection definition and add tests to catch schema/query drift.

### 13.1. Never Rely on `SELECT *` Ordering for Row Access

~~~cql
SELECT *
FROM telemetry.readings_by_device_day
WHERE device_id = ? AND event_day = ?
LIMIT 10;
~~~

`SELECT *` helps when exploring schemas interactively, yet in production code it introduces brittle coupling:

- Returns unneeded columns, inflating network/decoding cost.
- Column set and order are not a durable mapper contract.
- Adding columns later makes the app silently fetch unexpected payloads.
- Index-based mappers break easily whenever projections shift.

**Explicitly listing only needed columns** improves maintainability and stabilizes performance.

## 14. PreparedStatement, Row Mappers, and Code Reuse

### 14.1. Avoid Duplicating Mapping Across Controllers

A repository should return DTOs rather than leaking `Row` up to the HTTP layer:

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;

public final class ReadingMapper {
    private ReadingMapper() {}

    public static ReadingDto map(Row row) {
        if (row == null) {
            throw new IllegalArgumentException("row cannot be null");
        }
        return new ReadingDto(
            row.getInstant("event_time"),
            row.isNull("reading_value")
                ? null : row.getDouble("reading_value"),
            row.getString("status"),
            row.isNull("valid")
                ? null : row.getBoolean("valid")
        );
    }
}
~~~

When using a mapper, ensure the repository selects all four columns (`event_time`, `reading_value`, `status`, `valid`). If another API only needs timestamp and value, define a narrower projection/DTO instead of over-fetching.

### 14.2. Prepared Statements Do Not Replace Row Type Safety

~~~java
PreparedStatement ps = session.prepare(
    "SELECT event_time, reading_value " +
    "FROM telemetry.readings_by_device_day " +
    "WHERE device_id = ? AND event_day = ? LIMIT 1");

BoundStatement bs = ps.bind(deviceId, day);
Row row = session.execute(bs).one();

if (row != null) {
    Instant t = row.getInstant("event_time");
    double d = row.getDouble("reading_value");
}
~~~

Prepared statements lock the CQL shape and parameter binding. Yet if a developer changes `getDouble("reading_value")` to `getString("reading_value")`, the driver will not arbitrarily coerce CQL `double` into `String`. **Compatible codecs/getters**, tests, and error handling remain essential.

### 14.3. Query Shape Relates to Schema

A partition-key-aligned table scopes reads cleanly. However, if a partition grows huge with millions of rows or heavy tombstones, iterating `ResultSet` still fetches massive data and degrades latency.

**The `Row` API only reads results**—it is not an automatic query optimizer. Keep tables query-driven, partitions bounded, and CL appropriate.

## 15. Connecting to Consistency, Replication, and ResultSet Limits

`ResultSet` reflects the **outcome of one CQL execution** through a coordinator. Server-side data retrieval depends on:

- **Partition key** determining token and replica placement.
- **Replication factor** controlling how many copies exist.
- **Consistency level** governing response requirements.
- **Read path** merging memtables/SSTables and scanning tombstones.
- **Compaction/repair** affecting load and availability.
- **Paging** issuing follow-up requests when more rows remain.

Example:

~~~java
BoundStatement query = prepared.bind(deviceId, day)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(50);
~~~

This sets CL and target page size, yet **never turns a query missing its partition key into a good query** and does not snapshot all pages.

### 15.1. An Empty Row Does Not Prove Data Loss

If `one()` returns `null` or the iterator yields nothing, check:

- `WHERE`/bind values targeted the wrong partition/date.
- The row was deleted (`DELETE`) or expired via TTL.
- Data was not written yet or had not reached replicas satisfying CL.
- A schema/query migration changed the target table.
- Data is missing due to replication/recovery failure, requiring separate verification.

Never "repair" data blindly just because a `SELECT ... LIMIT 1` returned empty; confirm consistency requirements and write timing first.

### 15.2. Index Shifts After `ALTER TABLE`

If an app uses `SELECT *` with `getString(5)`, schema changes can break the mapper or silently read the wrong column when columns are added/dropped.

For schema rollouts:

1. Prefer explicit `SELECT` column lists and name-based getters.
2. Record schema versions and query templates in tests.
3. Maintain compatibility between old and new app instances during transitions.
4. Never assume newly added columns are non-null in historical rows.
5. Check codecs and nullable fields when upgrading drivers/JDKs.

## 16. Observing and Handling Errors When Reading ResultSet/Row

### 16.1. Common Errors

| Symptom | Hypothesis | Resolution Step |
|---|---|---|
| `NullPointerException` on `row.get...` | `one()` returned `null` | Check `row == null` first |
| Column name lookup failure | Column absent from projection or alias changed | Print `ColumnDefinitions` in lab; align `SELECT`/mapper |
| Index out of bounds | Index >= column count or negative | Check `defs.size()` and 0-based indexing |
| Codec/type conversion error | Getter incompatible with CQL type | Compare `defs.get(i).getType()` with mapping |
| Field reads `0` when CQL is null | Primitive getter called without `isNull` | Map via nullable wrapper/`Optional` as needed |
| Memory spikes reading many rows | `all()`/List retains everything, huge pages | Stream incrementally, bound results, apply backpressure |
| Slow query despite `one()` | Underlying query expensive or scanning many SSTables/tombstones | Inspect query shape, partitions, CL, and metrics |
| `getAvailableWithoutFetching()==0` | Current page exhausted, more pages remain | Check `isFullyFetched()`/iterator |
| Unexpected nulls after deploy | `SELECT`/alias/schema mismatch or historical rows missing column | Inspect DDL diff, projections, migration logic |
| LWT returns unexpected `Row` | Conditional statement used | Call `wasApplied()` and inspect definitions |

### 16.2. Log Only Necessary Metadata

Safer diagnostic log example:

~~~text
operation=read_device_day
query_template=read_readings_v2
outcome=decode_error
column=reading_value
expected_java_type=double
cql_type=double
elapsed_ms=42
~~~

This is a **suggested application log schema**, not a default Java Driver log format. Never write raw `device_id` values, PII, tokens, raw row payloads, or secrets to shared logs. When investigating a specific record, use correlation IDs with proper access control.

### 16.3. Distinguish Client Mapping Errors from Cassandra Timeouts

Java errors like "could not decode column" usually happen after the driver already received data. Timeouts/unavailable errors involve coordinators/replicas and CL. Separate metrics:

- **CQL request success/timeout/error** at the driver.
- **Mapping success/error** in the application.
- **Rows returned/processed**, page counts, and bytes.
- **End-to-end p95/p99** at the endpoint.

If a request succeeds yet the DTO mapper throws, do not claim Cassandra returned no row. Conversely, if `SELECT` times out, do not blame `getString` or `getDouble`.

## 17. Unit Testing Mappers and Integration Testing ResultSet

### 17.1. Testing Name-Based Mapping

For a `Row` mapper, unit tests can mock `Row` (e.g., with Mockito) to verify each field is read properly. Conceptual example:

~~~java
// Unit test pseudocode: depends on project's Mockito/JUnit and DTO classes.
when(row.getInstant("event_time")).thenReturn(timestamp);
when(row.isNull("reading_value")).thenReturn(false);
when(row.getDouble("reading_value")).thenReturn(24.6);
when(row.getString("status")).thenReturn("OK");
when(row.isNull("valid")).thenReturn(false);
when(row.getBoolean("valid")).thenReturn(true);

ReadingDto dto = ReadingMapper.map(row);

assertEquals(timestamp, dto.eventTime());
assertEquals(24.6, dto.value());
assertEquals("OK", dto.status());
assertEquals(true, dto.valid());
~~~

This is an **illustrative snippet** without imports or mock setup; it is not standalone test code. It expresses the mapper contract.

### 17.2. Integration Testing Against a Cassandra Lab

A reliable integration test suite should:

1. Provision a test schema compatible with the target Cassandra version.
2. Insert rows covering `uuid`, `date`, `timestamp`, `double`, `text`, `decimal`, `list`, and `boolean`.
3. `SELECT` columns in a fixed order; compare **name-based and index-based** getters.
4. `SELECT` the same columns in a different order; confirm name-based mappers still pass while stale index mappings fail.
5. Insert rows omitting optional fields; verify `isNull` and nullable DTO fields.
6. Run a `WHERE` matching no rows; verify `one() == null`.
7. Query across multiple pages; verify loop reads all rows and `all()` is avoided for large sets.
8. `SELECT` with aliases; verify names in `ColumnDefinitions`.
9. Test LWT separately using `wasApplied()`.
10. Measure request/consume latency and ensure tests target only the lab, never production.

### 17.3. Code Review Checklist

~~~text
[ ] Session is reused and closed cleanly on shutdown.
[ ] CQL templates use bind values, never raw string concatenation.
[ ] WHERE includes the full partition key for the designed query.
[ ] SELECT lists only needed columns; avoid SELECT * in APIs.
[ ] one() is null-checked before calling getters.
[ ] Row getters match CQL types (Instant, LocalDate, BigDecimal, etc.).
[ ] Nullable columns use isNull checks, especially before primitive getters.
[ ] Name-based getters match aliases; index-based mappings have projection tests.
[ ] ResultSet is never treated like a rewindable List.
[ ] all() is restricted to small, bounded result sets.
[ ] Page size and LIMIT are clearly distinguished.
[ ] LWT uses wasApplied(), never inferring success from one().
[ ] Driver 4.x API version and JDK compatibility verified.
[ ] Logs never expose raw rows, PII, or bind values.
[ ] Metrics track timeouts, mapping errors, p99, and row/page counts.
~~~

## 18. Self-Check: Questions and Answers

### Question 1 — ResultSet and Row

`session.execute(SELECT...)` returns a `ResultSet` with two rows. Is `ResultSet` simply a `List<Row>` already loaded completely onto the Java heap?

**Answer:** No. It is a synchronous result consumption interface with paging; the driver may only have fetched the first page and fetches further pages as needed.

### Question 2 — Null Values

`Row row = rs.one();` returns `null`. Should you call `row.getString("status")` to check if status is null?

**Answer:** No. No row exists; calling a getter throws `NullPointerException`. Check `row == null` first.

### Question 3 — Indices

The query is `SELECT event_time, reading_value, status`. Which column does `row.getString(2)` read?

**Answer:** `status`, because indices are 0-based: 0=`event_time`, 1=`reading_value`, 2=`status`.

### Question 4 — Reordering SELECT

Changed to `SELECT status, event_time, reading_value`. Is `row.getInstant(0)` still valid?

**Answer:** No. Index 0 is now `status`. Prefer name-based getters or update tested index mappings.

### Question 5 — Unselected Column

The query only selects `event_time` and `reading_value`, yet Java calls `row.getString("status")`. Does that mean `status` is null in Cassandra?

**Answer:** No. The column is absent from the projection; that is a mapper bug. Inspect `ColumnDefinitions`, fix `SELECT`, or remove the read.

### Question 6 — Primitives and Null

CQL `reading_value` has no value, and the app must distinguish "unmeasured" from `0.0`. Should you call `getDouble` directly?

**Answer:** No. Check `isNull("reading_value")` first and store in a nullable `Double` or domain object.

### Question 7 — Timestamp Type

Which getter reads CQL `timestamp` in Driver 4.x in this lesson?

**Answer:** `row.getInstant(...)`, returning `java.time.Instant`. CQL `date` uses `getLocalDate(...)`.

### Question 8 — Page Size

A query has no `LIMIT` and `pageSize = 100`. Does that mean total results cannot exceed 100 rows?

**Answer:** No. Page size is a target per fetch; the query can return many pages. Enforce total limits/stop conditions separately.

### Question 9 — `all()`

A loop must process one million rows, and the code calls `rs.all()` to get a `List` first. What is the risk?

**Answer:** It fetches and retains all remaining rows in the heap, spiking memory/GC and risking OOM. Consume incrementally with backpressure or bounded pipelines.

### Question 10 — `wasApplied`

After `INSERT ... IF NOT EXISTS`, should you check `rs.one() == null` or `rs.wasApplied()` to see if the condition held?

**Answer:** `rs.wasApplied()`, because it is the conditional/LWT result indicator. Returned rows have LWT-specific structure.

### Question 11 — Aggregates

`SELECT COUNT(*) AS total` returns a CQL `bigint`. Is the right getter `getInt("total")` or `getLong("total")`?

**Answer:** `getLong("total")`. Never run `COUNT` across huge tables routinely to check size, as it is resource-intensive.

### Question 12 — Name-Based Mapping

A query reorders `SELECT` while keeping aliases `event_time`, `reading_value`, and `status`. How does name-based access help?

**Answer:** Name-based mapping still targets the right columns regardless of projection order, though types, aliases, and column presence still require validation.

### Question 13 — Driver 3.x vs. 4.x

An older project uses `com.datastax.driver.core.ResultSet`. Can you paste `com.datastax.oss.driver.api.core.*` imports and leave all remaining code untouched?

**Answer:** No. Verify APIs, temporal getters, session/paging configuration, and compatibility when migrating major driver versions.

### Question 14 — Cassandra Consistency

A `SELECT` at `LOCAL_QUORUM` returns no row. Can you conclude Java's `getUuid` lost the data?

**Answer:** No. Without a `Row`, the getter was not even called. Check `WHERE` criteria, write timing, CL, replication, TTL/deletes, and request errors.

## 19. Misconceptions to Avoid

| Misconception | Reality |
|---|---|
| "`ResultSet` always holds every `Row` already downloaded." | It may hold only the first page; paging fetches on demand. |
| "`one()` returning `null` means a column is null." | It means no further row exists. |
| "`getString` reads any type and converts it to text." | Getters require compatible codecs/types. |
| "Column index 0 is the first column in `CREATE TABLE`." | It is the first column in the **query projection**. |
| "Adding a column to a table won't affect a `SELECT *` mapper." | It alters projection/payload size; tests are essential. |
| "`isNull` is unneeded since `getDouble` returns `0`." | `0` and `null` carry different business meanings. |
| "`all()` still saves RAM when `pageSize=50`." | `all()` collects every remaining page into memory. |
| "`getAvailableWithoutFetching()` is the query's `COUNT`." | It only counts locally buffered rows currently ready. |
| "`fullyFetched` means all `Row`s have been processed." | It only tracks fetch completion, not app consumption. |
| "LWT succeeded when `one() == null`." | Always use `wasApplied()` for conditional statements. |
| "Index getters are always drastically faster." | Any difference is minor; mapping resilience matters more. |
| "Prepared statements prevent all `Row` mapping bugs." | Preparing does not fix wrong getter types or aliases. |
| "`SELECT LIMIT 1` returning nothing proves replica data loss." | Check predicates, consistency, TTL, and timing first. |
| "Java Driver 3 and 4 share identical classes/APIs." | Packages and semantics differ; migrate per version. |

## 20. Summary

When reading Cassandra data with Java Driver 4.x:

1. **`CqlSession.execute()` returns a `ResultSet`**, from which you retrieve **`Row`s** via `one()` or iteration.
2. **`one()` consumes the next row** and returns `null` when exhausted. Never confuse an absent row with a null cell.
3. **Name-based getters** are easier to maintain and resilient to `SELECT` reordering; keep aliases/projections aligned.
4. **Index-based getters** are 0-based and follow **returned projection order**, not table DDL order; test whenever queries change.
5. **Getter types must match CQL types**: `timestamp → Instant`, `date → LocalDate`, `decimal → BigDecimal`, etc.
6. **`isNull` matters for primitive values**, because missing data does not equal numeric `0` or boolean `false`.
7. **`ColumnDefinitions`** lets you inspect names, indices, and types, especially across schema/alias changes.
8. **`ResultSet` pages automatically**, so `all()` can pull entire datasets into heap; distinguish `LIMIT` from page size.
9. **LWT uses `wasApplied()`** to check whether a conditional statement was applied.
10. **The `Row` API does not replace data modeling or consistency**: partition keys, replication, compaction, and CL still govern read-path quality.

During code reviews, do not ask only "which getter reads this field?", but **"Is the `Row` guaranteed to exist, does the projection include the exact columns/aliases, are type and null semantics right, and how many `Row`s will the app hold when paging further?"**. Getting those four right keeps Java–Cassandra integration safe, maintainable, and free of common performance pitfalls.
