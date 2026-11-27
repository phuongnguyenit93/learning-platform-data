# tinyint, smallint, int, bigint, and varint in Apache Cassandra

In Apache Cassandra, **tinyint**, **smallint**, **int**, **bigint**, and **varint** all represent **signed integers**, differing in value range, encoded byte size, and corresponding types in a Java application. Choosing the wrong one can cause write failures on overflow, silent data truncation when casting in Java, or unnecessary overhead on a table with billions of rows.

This lesson belongs to the **Data Types** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module, which covers distributed architecture, the wide-column model, partition keys, query-driven table design, read/write consistency levels, and connecting to Cassandra from Java. For these five integer types, the first decision is the **actual value domain and expected growth**, followed by storage size, the column's role in keys, and application handling. Replication, compaction, repair, and retries cannot compensate for an integer type chosen with the wrong domain.

## 1. Comparing the Five CQL Integer Types

| CQL Type | Representation | Value Range | Default Java Type (Driver 4.x) | Typical Use Cases |
|---|---:|---|---|---|
| **tinyint** | 1 byte (8 bits) | −128 to 127 | `byte` / `Byte` | Quality levels 0–5, small bounded status codes |
| **smallint** | 2 bytes (16 bits) | −32,768 to 32,767 | `short` / `Short` | Retry counts with clear bounds, protocol codes |
| **int** | 4 bytes (32 bits) | −2,147,483,648 to 2,147,483,647 | `int` / `Integer` | Quantities, indices, lengths within 32-bit bounds |
| **bigint** | 8 bytes (64 bits) | −9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 | `long` / `Long` | Cumulative byte counts, event sequences, money in minor units |
| **varint** | Variable length | Arbitrary-precision signed integers, subject to practical resource limits | `BigInteger` | Integers exceeding 64 bits, mathematical combinatorics counts |

Each fixed-width range is a **two's complement signed integer** range: from \( -2^{n-1} \) to \( 2^{n-1}-1 \) for \(n\) bits. Because half of the range is reserved for negative numbers, **int cannot hold 4,000,000,000**, even though that value fits in a 32-bit *unsigned* integer in some other systems. Cassandra does not provide `uint8`, `uint16`, `uint32`, or `uint64` equivalents as direct substitutes.

**varint** has no fixed 8/16/32/64-bit limit; values can exceed `bigint`. However, "arbitrary" refers to representational precision, not that Cassandra can store an infinitely long number. Value size, memory, protocol limits, encoding overhead, and operational costs still apply.

## 2. Rules for Choosing by Value Domain

### 2.1. Size for Future Bounds, Not Just Current Data

Suppose a device currently has 25 connection attempts, but the system may retain the cumulative attempt count over its entire lifetime. **tinyint** only holds up to 127; **smallint** holds 32,767; if the total can grow larger, you must choose **int** or **bigint** based on projections.

How to evaluate:

1. Identify the **business minimum and maximum**: can values be negative, and do they reset or accumulate indefinitely?
2. Determine the **growth rate** and data retention period: 10,000 events/second accumulated over years differs vastly from 10 retries for a single request.
3. Account for **products and sums** in Java: two operands fitting in `int` does not guarantee their sum or product fits in `int`.
4. Choose a type with a sufficient range and safety margin, especially for key columns or fields that are difficult to change after deployment.

Examples:

| Value to Store | Chosen Type | Reason |
|---|---|---|
| Quality rating from 0 to 5 | **tinyint** | Closed, very small domain |
| Protocol status codes between 100 and 599 | **smallint** | Exceeds 127 but fits in 16 bits |
| Millidegrees Celsius between −50,000 and 150,000 | **int** | Includes negatives, exceeds `smallint`; uses integers to preserve 0.001 °C resolution |
| Transferred bytes: 5,000,000,000 | **bigint** | Exceeds `int` but fits in 64 bits |
| Combinatorial count: 18,446,744,073,709,551,616 | **varint** | Equals \(2^{64}\), exceeds `bigint` |
| Product code `"0000123"` | **text**, not a numeric type | Leading zeros are part of the identifier |
| Monetary amount 19.95 in major currency units | **decimal** or **bigint** in minor units | None of these five integer types represent fractional parts directly |

Never assume a "positive-only" value gets double the positive range of a signed type. For instance, if you receive an **unsigned 32-bit** integer from an external protocol (0 to 4,294,967,295), map it to **bigint** while validating the 0..4,294,967,295 range at the application layer.

### 2.2. tinyint and smallint: Small Values with Explicit Bounds

**tinyint** is an 8-bit signed integer. It fits scores, levels, or small codes known never to exceed 127. A common mistake is thinking **255 fits in tinyint** in Cassandra—it does not.

**smallint** is a 16-bit signed integer. It is a sensible choice when a value catalog exceeds 127 yet stays within ±32,767. For example, HTTP status codes 200/404/503 fit in `smallint`; storing them as `tinyint` will overflow.

Distinguish numeric business codes from text-meaningful codes. If statuses are `"OK"`, `"TIMEOUT"`, `"PENDING_REVIEW"`, use **text** or a standardized cross-service representation; do not assign ordinal numbers and rely on Java enum ordering without a durable mapping contract.

### 2.3. int and bigint: Pragmatic Defaults for Most Counts

**int** usually fits page item counts, 0-based indices, short durations in milliseconds, or bounded quantities. **bigint** suits large offsets, cumulative counters, byte counts, 64-bit numeric IDs issued externally, and monetary amounts in minor units.

However, `bigint` **does not automatically make an increment atomic**. If two applications both read `total = 10` and both write `total = 11`, one increment can be lost. Cassandra resolves conflicts via write metadata and the consistency model, not the width of `bigint`. When distributed counting is needed, design an event-logging/aggregation mechanism or evaluate **counter** with its specific trade-offs.

**Do not equate timestamp with bigint** merely because both involve 64-bit numbers. If a column carries point-in-time semantics at millisecond resolution, **timestamp** and Java **Instant** express that meaning clearly; `bigint` is appropriate when you genuinely need an integer—such as custom epoch nanoseconds or event offsets—and the unit must be documented.

### 2.4. varint: Use Only When >64-bit Integers Are Truly Required

**varint** encodes signed integers with variable length based on magnitude using two's complement representation. Larger values require more bytes. It fits:

- Exact combinatorial or statistical results exceeding \(2^{63}-1\).
- External inputs using integers larger than 64 bits.
- Calculation results where every digit must be preserved without rounding.

**varint is not a smart compression substitute for bigint by default**. Although small integer values take fewer payload bytes, overall storage depends on cell metadata, row count, access patterns, and decoding overhead; do not assume `varint` is always smaller or faster than `bigint`.

If a number has a fractional part, **varint cannot preserve the fraction**. Use **decimal** when exact decimal arithmetic is needed; use **float/double** when measurements tolerate floating-point approximation.

## 3. Choosing Types in a Query-Driven Table

Data collection scenario: "Fetch up to the 100 latest samples for a device on a given day; each sample has a status, retry count, temperature in millidegrees, and total bytes transferred."

~~~cql
CREATE TABLE readings_by_device_day (
    device_id uuid,
    reading_day date,
    sample_no bigint,
    quality_code tinyint,
    retry_count smallint,
    temperature_milli_c int,
    transferred_bytes bigint,
    PRIMARY KEY ((device_id, reading_day), sample_no)
) WITH CLUSTERING ORDER BY (sample_no DESC);
~~~

Numeric columns here are chosen by semantics:

| Column | Type | Explanation |
|---|---|---|
| `sample_no` | **bigint** | Sequence number assigned by the data source, may grow past 32 bits |
| `quality_code` | **tinyint** | Quality code 0–5, bounded domain |
| `retry_count` | **smallint** | Retry count per sample, with a business constraint of 0–32,767 |
| `temperature_milli_c` | **int** | Integer scaled by 1,000; stores negative values and avoids binary float error for fixed resolution |
| `transferred_bytes` | **bigint** | A sample may report cumulative bytes exceeding 2.147 billion |

The **primary key** comprises the composite partition key `(device_id, reading_day)` and the clustering key `sample_no`. Cassandra hashes the partition key to distribute data across the cluster; `sample_no` determines descending sort order **within the partition**. Rows across the entire cluster are not globally sorted by sequence number.

~~~cql
INSERT INTO readings_by_device_day (
    device_id, reading_day, sample_no,
    quality_code, retry_count, temperature_milli_c, transferred_bytes
) VALUES (
    123e4567-e89b-12d3-a456-426614174000, '2026-11-21', 1002,
    2, 300, 23875, 5000000000
);

SELECT sample_no, quality_code, retry_count,
       temperature_milli_c, transferred_bytes
FROM readings_by_device_day
WHERE device_id = 123e4567-e89b-12d3-a456-426614174000
  AND reading_day = '2026-11-21'
LIMIT 100;
~~~

The query provides the full partition key and leverages the `sample_no DESC` clustering order. If a requirement asks to "find all samples with `quality_code = 2` across all devices," merely changing `quality_code` to `int` or `bigint` will **not** make that query efficient: you must design a separate access path suited to actual data volume.

Daily bucketing also does not guarantee small partitions for devices emitting millions of samples per second; in that case, adjust buckets, add sharding, or revise the ingestion architecture based on measured volume and load. Integer width affects value size, while partitioning and access patterns remain the primary drivers of read latency.

**Key note:** sequence numbers must be stably assigned by the source or a dedicated allocation mechanism. Cassandra does not auto-generate `AUTO_INCREMENT` sequences for `bigint` columns. When retrying the same event, reuse the **same `device_id`, `reading_day`, `sample_no`** to avoid duplicate rows.

## 4. Testing Value Ranges with CQL

A standalone table to test `varint` beyond the `bigint` range:

~~~cql
CREATE TABLE exact_totals_by_job (
    job_id uuid PRIMARY KEY,
    paths_count varint,
    completed_steps bigint
);

INSERT INTO exact_totals_by_job (job_id, paths_count, completed_steps)
VALUES (
    11111111-1111-4111-8111-111111111111,
    18446744073709551616,
    5000000000
);

SELECT paths_count, completed_steps
FROM exact_totals_by_job
WHERE job_id = 11111111-1111-4111-8111-111111111111;
~~~

`18446744073709551616` equals \(2^{64}\), which exceeds the maximum value of `bigint`. The `varint` type preserves the value in full. `5000000000` fits in `bigint`, but exceeds `int`.

**Invalid** boundary values:

~~~text
tinyint   :  128                   # exceeds positive limit 127
tinyint   : -129                   # below negative limit -128
smallint  :  32768                 # exceeds positive limit 32767
int       :  2147483648            # exceeds positive limit 2147483647
bigint    :  9223372036854775808   # exceeds positive limit 9223372036854775807
~~~

These are boundary examples for schema and validation checks, **not a CQL script to execute**. Validate data in the application before binding: a literal being syntactically valid as an integer in CQL does not mean it fits the target column's range.

**Negative numbers** are supported across all five types; for example, `temperature_milli_c = -5000` represents −5.000 °C if the unit is defined as thousandths of a degree. If business rules forbid negative values, Cassandra does not infer that rule from `int`; validation must happen at the write boundary.

## 5. Java Driver 4.x: Bind the Right Type, Avoid Silent Casts

In the Apache Cassandra Java Driver 4.x, commonly used methods are:

| CQL | Java | Write via Prepared Statement | Read from `Row` |
|---|---|---|---|
| `tinyint` | `byte` | `setByte(...)` | `getByte(...)` |
| `smallint` | `short` | `setShort(...)` | `getShort(...)` |
| `int` | `int` | `setInt(...)` | `getInt(...)` |
| `bigint` | `long` | `setLong(...)` | `getLong(...)` |
| `varint` | `BigInteger` | `setBigInteger(...)` | `getBigInteger(...)` |

Sample writes to the two tables created above (assuming `session` is a connected `CqlSession` with the appropriate keyspace selected):

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.math.BigInteger;
import java.time.LocalDate;
import java.util.UUID;

// CqlSession session = ...; // created per application cluster configuration

UUID deviceId = UUID.fromString("123e4567-e89b-12d3-a456-426614174000");

PreparedStatement insertReading = session.prepare(
    "INSERT INTO readings_by_device_day "
  + "(device_id, reading_day, sample_no, quality_code, retry_count, "
  + " temperature_milli_c, transferred_bytes) "
  + "VALUES (?, ?, ?, ?, ?, ?, ?)");

BoundStatement reading = insertReading.boundStatementBuilder()
    .setUuid(0, deviceId)
    .setLocalDate(1, LocalDate.parse("2026-11-21"))
    .setLong(2, 1002L)
    .setByte(3, (byte) 2)
    .setShort(4, (short) 300)
    .setInt(5, 23875)
    .setLong(6, 5_000_000_000L)
    .build();

session.execute(reading);

PreparedStatement insertTotal = session.prepare(
    "INSERT INTO exact_totals_by_job "
  + "(job_id, paths_count, completed_steps) VALUES (?, ?, ?)");

UUID jobId = UUID.fromString("11111111-1111-4111-8111-111111111111");

BigInteger pathsCount = new BigInteger("18446744073709551616");
BoundStatement total = insertTotal.boundStatementBuilder()
    .setUuid(0, jobId)
    .setBigInteger(1, pathsCount)
    .setLong(2, 5_000_000_000L)
    .build();

session.execute(total);
~~~

**Why does `5_000_000_000L` need the `L` suffix?** In Java, unsuffixed integer literals must fit in `int`; `L` specifies a `long` literal. This is a **Java** rule, not CQL literal syntax. `new BigInteger("...")` preserves every digit of very large numbers.

**Do not use `(byte) userInput` or `(short) userInput` on unvalidated data.** Narrowing casts in Java silently truncate high-order bits:

~~~java
int input = 200;
byte wrong = (byte) input;    // -56, no longer 200

if (input < Byte.MIN_VALUE || input > Byte.MAX_VALUE) {
    throw new IllegalArgumentException("quality_code exceeds tinyint range");
}
byte checked = (byte) input;  // Cast only after validating
~~~

Similarly, if a `BigInteger` must be narrowed to `long`, use **`longValueExact()`** to throw an exception on overflow instead of `longValue()`, which silently drops high bits:

~~~java
BigInteger tooLarge = new BigInteger("9223372036854775808");

try {
    long value = tooLarge.longValueExact();
    // Never reaches here because the value exceeds Long.MAX_VALUE.
} catch (ArithmeticException ex) {
    // Choose to store as varint, reject the value, or update the data contract.
}
~~~

When reading columns that may be absent/`null`, check **`row.isNull("column_name")`** before calling a primitive getter. Zero, missing data, and unknown values carry three distinct business meanings.

## 6. Overflow Happens Before Writing to Cassandra

Cassandra does not check Java arithmetic for you. For example:

~~~java
int current = Integer.MAX_VALUE;
int incorrect = current + 1;  // -2147483648: Java int overflow

int safe = Math.addExact(current, 1); // throws ArithmeticException

long promoted = (long) current + 1L;  // 2147483648: valid in long

long large = Long.MAX_VALUE;
BigInteger exact = BigInteger.valueOf(large).add(BigInteger.ONE);
// 9223372036854775808: requires varint if stored in full
~~~

Rules based on the expected result:

- Adding or subtracting two `int` values can overflow `int`; check with **`Math.addExact`** or promote to `long` before computing.
- Multiplying two `long` values can overflow `long` very quickly; if results genuinely exceed 64 bits, use **`BigInteger`** from the start.
- When ingesting from JSON, CSV, or external APIs, parsers or serializers may cap numbers at 64 bits or turn all numbers into `double`. Preserve digit strings or `BigInteger` when receiving large integers; converting through `double` beforehand already destroys precision.
- If the system rounds temperatures or measurements into fixed-unit `int` columns, standardize rounding rules, units, and range checks before writing.

**Range errors and concurrency bugs are separate issues:** incrementing from 2,147,483,647 to 2,147,483,648 causes an `int` overflow; two workers both reading 99 and writing 100 causes a lost update. Widening the type to `bigint` solves the range issue, but does not resolve write contention.

## 7. bigint Is Not a Counter: Incrementing in a Distributed System

Three commonly confused cases:

| Requirement | Approach |
|---|---|
| Write a total already computed by another system | **int/bigint/varint** depending on range; write the full value |
| Increment/decrement a distributed counter, accepting Cassandra counter semantics | **counter** in a dedicated counter table |
| Count exact events for billing/auditing where retries must not double-count | Store events with stable IDs, handle idempotency, and aggregate via a controlled pipeline |

**counter** in Cassandra is a specialized type, even though Java typically reads its value as a `long`. It is not a `bigint` with shorthand addition syntax: counter columns have strict table constraints, updates use counter increment/decrement expressions, and retrying after a timeout can apply an increment multiple times.

~~~cql
-- Illustrates a dedicated counter table only; does not replace a source event table.
CREATE TABLE page_views_by_page (
    page_id uuid PRIMARY KEY,
    view_count counter
);

UPDATE page_views_by_page
SET view_count = view_count + 1
WHERE page_id = 11111111-1111-4111-8111-111111111111;
~~~

If an application resends the same `UPDATE` when unsure whether the previous attempt succeeded, it risks double-counting. Achieving **per-event exactly-once** semantics requires a domain design with unique IDs and deduplication; choosing a numeric type alone provides no such guarantee.

With regular `bigint`/`varint` columns, reading a number, incrementing on the client, and writing it back is not atomic under concurrent writers. Depending on consistency and throughput needs, you may require coordination, immutable event logging, or conditional writes (LWT).

## 8. Impact on Keys, Replication, Compaction, and Scalability

### 8.1. Numeric Columns in Keys Have Query Semantics

In the example table, `sample_no bigint` is a **clustering key**. Cassandra sorts this column in true **numerical** order matching its type, unlike storing numbers as `text`: strings `"100"` and `"20"` are compared lexicographically, not as integers 100 and 20.

Choose `bigint` instead of `int` for a key if ordering values will exceed 32 bits; changing a key type on an existing populated table typically entails creating a new table, copying data, and migrating applications. If the key is an external ID like `"00042"`, keep **text** so the identifier retains its meaning.

### 8.2. Data Size and Operational Cost

In terms of encoded numeric values, `tinyint` / `smallint` / `int` / `bigint` use 1/2/4/8 bytes respectively, whereas `varint` varies with magnitude. However, every row/cell in Cassandra also carries metadata, tombstones, partition structures, indexes, and compression overhead, so total table footprint cannot be estimated by multiplying type byte width by row count.

Choosing narrower types saves value payload bytes at large row counts; choosing a type that is too narrow and later migrating billions of rows due to overflow is far costlier. Using wide `varint` columns on hot paths also carries different codec/CPU and storage costs than `bigint`; benchmark against real workloads if SLAs are affected.

**Compaction** sorts and merges SSTables and purges expired data according to storage rules; it does not automatically widen an `int` on overflow. **Repair** synchronizes data across replicas; it does not fix client-side casting overflows. Replication and consistency levels govern read/write acknowledgments, not numeric validation.

### 8.3. Caution When Changing Types

Changing `int` to `bigint` or `bigint` to `varint` in production requires verifying Cassandra version support and schema alteration restrictions, especially for **primary keys**. Do not assume `ALTER TABLE ... ALTER ... TYPE` will safely convert existing rows.

A reliable migration path typically includes:

1. Create a new table with columns and keys of the right range while still serving the target query.
2. Update Java code to use the matching codecs/getters/setters; verify calculation logic and input sources before writes.
3. Backfill historical data, coordinate dual-writes or controlled cutover of write streams; keep IDs and retry logic consistent.
4. Compare record counts and boundary values, switch read traffic, then decommission the old table according to retention policy.

If multiple services read/write the table, update API contracts and serialization first. A client still using `int` may fail or lose precision even after Cassandra has moved to `bigint` or `varint`.

## 9. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Solution |
|---|---|---|
| Using `tinyint` for values in 0–255 | 128–255 exceeds the signed range | Use `smallint`, validate 0–255 |
| Using `int` for unbounded byte totals | Overflows at 2,147,483,647 | Use `bigint`, or `varint` if truly exceeding 64 bits |
| Using `bigint` in schema but summing with `int` on client | Precision loss/overflow before binding | Compute using `long`/`BigInteger` with overflow checks |
| Calling `longValue()` on any `BigInteger` | Silently truncates high bits | Use `longValueExact()` and handle out-of-range cases |
| Storing identifiers with leading zeros as numbers | Identifier formatting is lost | Use `text` |
| Using `varint` for a price like 19.95 | Cannot represent fractional parts | Use `decimal` or `bigint` in minor units |
| Treating `bigint` as an atomic counter | Lost increments under concurrent writers | Design event/aggregation flow or appropriate counter |
| Changing a key type without considering queries | Forces schema and application migration | Choose headroom upfront and plan migrations early |
| Letting apps silently change `temperature_milli_c` units | Same number carries conflicting meanings | Document unit, scale, and rounding rules in the contract |

## 10. Review Checklist for Tables with Integers

- [ ] Does the column genuinely hold a **number** needing arithmetic or numeric ordering, rather than a **digit-only identifier**?
- [ ] Have min/max bounds, negative values, cumulative vs. resetting behavior, and growth projections been determined?
- [ ] Have `tinyint`, `smallint`, `int`, and `bigint` been checked against **signed** ranges, especially when ingesting unsigned values from external systems?
- [ ] If using `varint`, is there a genuine requirement for exact >64-bit integers, and have encoding/driver costs been checked?
- [ ] Can additions, multiplications, casts, or parsing in Java overflow **before writing to Cassandra**?
- [ ] Are measurement units (bytes, milliseconds, millidegrees, minor currency units) and rounding rules standardized?
- [ ] Do primary key columns have sufficient long-term range, match query patterns, and keep IDs stable across retries?
- [ ] Do `setByte`, `setShort`, `setInt`, `setLong`, `setBigInteger`, and getters match the CQL schema?
- [ ] Are increment/decrement requirements designed for concurrency and idempotency rather than just picking a wider integer type?
- [ ] If a type change is needed later, is there a plan for a new table, backfill, and application cutover?

**Remember:** **tinyint → smallint → int → bigint** progressively widen fixed signed integer ranges; **varint** is for exact integers exceeding 64 bits. The right type must match the **business domain**, **calculation precision**, **partition/clustering access pattern**, and **Java type**. Wider integer widths solve representational limits, but do not automatically provide atomic counters or business consistency in a distributed system.
