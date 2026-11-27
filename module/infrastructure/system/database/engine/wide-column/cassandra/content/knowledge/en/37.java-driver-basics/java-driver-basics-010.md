# Mapping Numbers, `BigDecimal`, `UUID`, `Instant`, and Date/Time Types in the Cassandra Java Driver

## 1. Objectives and Context

In Apache Cassandra, a Java application sends CQL via the **Java Driver** to a coordinator; data is stored by **partition key**, replicated across nodes according to **replication factor (RF)**, and read/written per **consistency level (CL)**. Alongside query-driven table design and consistency guarantees, accurate **CQL ↔ Java type mapping** determines whether a request preserves the true meaning of your data.

Consider a billing system storing `total_amount` as a decimal, `event_id` as a UUID, and `occurred_at` as a timestamp. Three common mistakes:

- Converting `decimal` to `double` for monetary arithmetic, introducing rounding drift.
- Inserting `UUID.randomUUID()` into a `timeuuid` column, which requires a time-based UUID.
- Treating `LocalDateTime` as an absolute instant without a timezone, shifting dates/times when read in another DC.

This lesson uses the **Java Driver 4.x API** under namespace `com.datastax.oss.driver.api.core` and Java 8+ `java.time` types. Exact syntax, artifact dependencies, low-level APIs, and compatibility matrices vary by **driver release/Cassandra distribution**; verify your project's target release before deploying to production.

### After This Lesson, You Should Be Able To

1. Choose matching Java types for numeric types `tinyint`, `smallint`, `int`, `bigint`, `varint`, `decimal`, `float`, `double`, and `counter`.
2. Understand `BigDecimal`, `BigInteger`, scale, precision, rounding, and overflow risks.
3. Distinguish `uuid` from `timeuuid`, and random UUIDs from time-based UUIDs.
4. Map `timestamp` ↔ `Instant`, `date` ↔ `LocalDate`, `time` ↔ `LocalTime`, and `duration` ↔ `CqlDuration`.
5. Bind and read data properly with `PreparedStatement`, handling `null` and `UNSET`.
6. Write round-trip tests proving types, precision, and timezones remain intact.

## 2. CQL ↔ Java Driver 4.x Mapping Table

Common default mappings:

| CQL Type | Java Type | Reading from `Row` | Key Point |
| --- | --- | --- | --- |
| `tinyint` | `byte` / `Byte` | `getByte(...)` | 8-bit signed integer |
| `smallint` | `short` / `Short` | `getShort(...)` | 16-bit signed integer |
| `int` | `int` / `Integer` | `getInt(...)` | 32-bit signed integer |
| `bigint` | `long` / `Long` | `getLong(...)` | 64-bit signed integer |
| `varint` | `BigInteger` | `getBigInteger(...)` | Arbitrary-length integer |
| `decimal` | `BigDecimal` | `getBigDecimal(...)` | Arbitrary-precision decimal within resource bounds |
| `float` | `float` / `Float` | `getFloat(...)` | IEEE 754 32-bit; has representation error |
| `double` | `double` / `Double` | `getDouble(...)` | IEEE 754 64-bit; still has representation error |
| `counter` | `long` / `Long` | `getLong(...)` | Read value is `long`; counter mutations have special semantics |
| `uuid` | `UUID` | `getUuid(...)` | Identifier; not inherently time-ordered |
| `timeuuid` | `UUID` | `getUuid(...)` | Version-1 UUID containing a timestamp component |
| `timestamp` | `Instant` | `getInstant(...)` | Absolute point in time, stored at millisecond precision |
| `date` | `LocalDate` | `getLocalDate(...)` | Calendar date without time or timezone |
| `time` | `LocalTime` | `getLocalTime(...)` | Time of day at nanosecond precision |
| `duration` | `CqlDuration` | `getCqlDuration(...)` | Months + days + nanoseconds; not `java.time.Duration` by default |

**Critical point:** `float`/`double` and `decimal` are distinct types; so are `bigint` and `varint`. Just because `Row` offers convenient getters **does not mean** the driver silently converts any column to any Java type losslessly. Getters, codecs, and CQL column types must match.

For nullable columns, always **check `row.isNull("column")` before calling primitive numeric getters**. `0` is never a safe stand-in for missing data.

## 3. Integer Types: Pick by Value Range, Not Variable Name

Standard signed integer types:

| CQL | Bits | Min | Max | Java |
| --- | ---: | ---: | ---: | --- |
| `tinyint` | 8 | -128 | 127 | `byte` |
| `smallint` | 16 | -32,768 | 32,767 | `short` |
| `int` | 32 | -2,147,483,648 | 2,147,483,647 | `int` |
| `bigint` | 64 | -9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 | `long` |
| `varint` | Variable | No fixed 8/16/32/64-bit cap | Bounded practically by system resources | `BigInteger` |

Example:

```java
byte priority = 3;
short sensorNumber = 240;
int sampleCount = 1_000_000;
long sequenceNumber = 9_000_000_000L;
java.math.BigInteger veryLargeCount =
    new java.math.BigInteger("123456789012345678901234567890");
```

**Do not pick `int` just because counts are small today** if business growth could exceed ~2.1 billion. Conversely, do not make every column `varint`: unbounded integers add serialization, storage, arithmetic, and testing overhead; choose schema types from real domain bounds.

### Java Overflow Happens Before Cassandra Sees the Data

```java
int oldValue = Integer.MAX_VALUE;
int wrong = oldValue + 1;  // Overflow: wraps to negative.

long safeSum = Math.addExact((long) oldValue, 1L);
```

If arithmetic already overflowed in Java, binding into a `bigint` column **cannot recover the true value**. Use `Math.addExact`, range validation, or `BigInteger` when truly needed.

### `bigint` Differs from `varint`

`bigint` is a 64-bit integer; `varint` is variable-length. In Java Driver 4.x:

```java
long fixed64 = 10_000_000_000L;
java.math.BigInteger variablePrecision =
    new java.math.BigInteger("1000000000000000000000000000000");
```

Never bind a `BigInteger` into `bigint` expecting silent truncation to `long`. To convert explicitly with bounds checking:

```java
long converted = variablePrecision.longValueExact();
// Throws ArithmeticException if outside long range.
```

Similarly, `BigInteger.intValue()` can silently drop bits; prefer `intValueExact()` when exactness is required.

## 4. `decimal` and `BigDecimal`: Money, Taxes, and Precision

`decimal` is an arbitrary-precision decimal type, suited for money, financial rates, and values needing exact decimal digits. In Java, the matching type is `java.math.BigDecimal`.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("129.95");
BigDecimal taxRate = new BigDecimal("0.08");

BigDecimal gross = price.multiply(BigDecimal.ONE.add(taxRate));
BigDecimal payable = gross.setScale(2, RoundingMode.HALF_EVEN);
```

**Avoid:**

```java
BigDecimal fragile = new BigDecimal(0.1);
// Captures the exact binary double value, not the intended "0.1".

double money = 0.1 + 0.2;
// double cannot represent every decimal fraction exactly.
```

**Prefer** `new BigDecimal("0.1")` for decimal literals, or `BigDecimal.valueOf(doubleValue)` when you already have a `double` and accept its string representation. If incoming JSON contains monetary numbers, parse directly to `BigDecimal` rather than going through `double`.

### Precision and Scale

A `BigDecimal` holds an **unscaled integer** and a **scale**:

```java
BigDecimal a = new BigDecimal("12.30");
BigDecimal b = new BigDecimal("12.3");

System.out.println(a.scale());        // 2
System.out.println(b.scale());        // 1
System.out.println(a.compareTo(b));   // 0: numerically equal
System.out.println(a.equals(b));      // false: different scale
```

For currency amounts, establish clear rules for **currency unit, decimal places, rounding mode, and valid scale**. Cassandra's `decimal` does not automatically enforce scale 2 per your business rules; **validate at application boundaries**.

### When to Use `bigint` Instead of `decimal` for Money?

Many systems use `bigint total_cents` to store **minor units** (e.g., cents) and avoid decimal math. This fits when:

- The currency's minor unit is fixed and well-defined.
- Totals are always integer multiples of that unit.
- Values fit safely within `long`.

When flexible scales, exchange rates, or multi-decimal units are needed, `decimal`/`BigDecimal` usually expresses intent more directly. **You cannot pick the right type solely because a field name contains "amount".**

## 5. `float` and `double`: For Measurements, Not Default Money

`float` is 32-bit IEEE 754 floating point; `double` is 64-bit. Both store **approximate** values suitable for sensor readings, telemetry, or probability scores where tiny representation error is acceptable. They do not guarantee exact decimal addition.

```java
float signalStrength = 0.875f;
double confidence = 0.99d;

double sum = 0.1d + 0.2d;
System.out.println(sum);  // May print 0.30000000000000004
```

Comparing floating-point numbers requires tolerances and domain awareness; `==` is rarely safe after arithmetic. Check special values like `NaN`/`Infinity`, storage/bind validity, and ordering behavior against your data policy and driver version.

**Name units explicitly:** `temperature_celsius`, `distance_meters`, `ratio`. Never mix a `float` storing "0–100 percentage" with a `double` storing "0–1 ratio" and blame the Java Driver.

## 6. `counter` Reads Like `long` but Writes Very Differently from `bigint`

A CQL `counter` column is also read via `Row.getLong(...)`, yet it is not a normal `bigint` column.

Example dedicated counter table:

```sql
CREATE TABLE IF NOT EXISTS driver_types_lab.views_by_tenant_day (
    tenant_id text,
    bucket_day date,
    views counter,
    PRIMARY KEY ((tenant_id), bucket_day)
);

UPDATE driver_types_lab.views_by_tenant_day
SET views = views + 1
WHERE tenant_id = 'tenant-01'
  AND bucket_day = '2026-11-20';
```

Key notes:

- Never `INSERT` or overwrite a counter with `SET views = 100` like a `bigint`.
- Counter mutations are **not idempotent—retrying the same increment can count multiple times**. Never set `setIdempotent(true)` on increments or blindly retry after timeouts.
- Counters carry schema, TTL, and CQL restrictions; never mix them with regular data columns in the same table assuming normal semantics.
- If business logic needs "exactly-once" counting, design deduplication at the business layer rather than relying on the Java getter being `long`.

`counter` is a classic example of **identical Java types having completely different data semantics**.

## 7. `uuid` and `timeuuid`: Same Java `UUID`, Different Semantics

Java uses `java.util.UUID` for reading/binding both CQL `uuid` and `timeuuid`, **yet Cassandra enforces different constraints on their values**:

| CQL | Typical Purpose | Java | Notes |
| --- | --- | --- | --- |
| `uuid` | Random or system-assigned identifier | `UUID` | Usually UUID v4; implies no creation order |
| `timeuuid` | Version-1 UUID embedding a timestamp | `UUID` | Never bind a UUID v4 into `timeuuid` |

```java
import java.util.UUID;

UUID orderId = UUID.randomUUID();        // Typically UUID v4.
UUID parsed = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);

System.out.println(orderId.version());  // Typically returns 4.
System.out.println(parsed.version());   // 4 for this illustrative literal.
```

To generate a `timeuuid` in Java Driver 4.x, releases typically provide `Uuids.timeBased()`:

```java
import java.util.UUID;
import com.datastax.oss.driver.api.core.uuid.Uuids;

UUID eventTimeId = Uuids.timeBased();
if (eventTimeId.version() != 1) {
    throw new IllegalStateException("Expected a version-1 timeuuid");
}
```

Check the exact artifact/package of your project's 4.x driver. In CQL, `now()` generates a server-side `timeuuid`; **never use `now()` in place of a stable ID in a retry flow requiring idempotency**.

### Should You Use UUID v4 as a Clustering Key to Fetch Latest Events?

UUID v4 is random and **does not sort by creation time**. If queries need the latest events:

- Use `timestamp`/`created_at` as a clustering key paired with `event_id` for uniqueness; or
- Use `timeuuid` in a query-aligned design while understanding clock/timestamp limits.

`timeuuid` embeds a timestamp, yet **does not guarantee strict global ordering across distributed events** when clocks skew, retries occur, or multiple nodes mint IDs. Strict business ordering requires dedicated sequencing logic.

### `minTimeuuid` / `maxTimeuuid`

CQL functions `minTimeuuid(...)` and `maxTimeuuid(...)` help construct range bounds when querying **`timeuuid` clustering keys over a time window** in supported versions. They create **query bounds**, not real event IDs to persist as business identifiers.

## 8. `timestamp` ↔ `Instant`: Absolute Point in Time, Timezone-Free

CQL `timestamp` represents an **instant** in milliseconds since the Unix epoch. Java Driver 4.x naturally maps it to `java.time.Instant`.

```java
import java.time.Instant;

Instant occurredAt = Instant.parse("2026-11-20T14:35:12.123Z");
// Z denotes UTC.
```

**Never confuse Cassandra `timestamp` with `timestamp with timezone` in some RDBMSs.** Cassandra does not store an "Asia/Ho_Chi_Minh" or "Europe/Paris" tag inside a `timestamp` value. Displaying the same instant in different timezones changes the **wall-clock representation**, not the underlying instant.

### Milliseconds in Cassandra, Nanoseconds in Java

`Instant` carries nanosecond precision, whereas CQL `timestamp` has **millisecond** resolution. Example:

```java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

Instant original = Instant.parse("2026-11-20T14:35:12.123456789Z");
Instant normalized = original.truncatedTo(ChronoUnit.MILLIS);

System.out.println(normalized);
// 2026-11-20T14:35:12.123Z
```

When binding `original` into a `timestamp` column and reading it back, **do not expect the `456789` nanoseconds to survive**. Round-trip tests should compare against `normalized` or enforce millisecond precision up front.

### Never Confuse `timestamp` with `USING TIMESTAMP`

Two similarly named constructs with completely different meanings:

```sql
-- timestamp column: business timestamp value, millisecond precision.
INSERT INTO driver_types_lab.measurements_by_id (
    tenant_id, business_day, event_id, occurred_at
) VALUES (
    'tenant-01', '2026-11-20',
    11111111-1111-4111-8111-111111111111,
    '2026-11-20T14:35:12.123Z'
);
```

Whereas `USING TIMESTAMP 1795185312123456` (e.g., microseconds) is the **mutation write timestamp used by Cassandra for last-write-wins conflict resolution**, not necessarily the value of `occurred_at`. Never blindly pass `Instant.toEpochMilli()` as `USING TIMESTAMP`, because write timestamps are in **microseconds**.

The CQL snippet above assumes the keyspace/table created in Section 12; if following sequentially, create that schema first.

## 9. `date` ↔ `LocalDate`: Calendar Date Without Time

CQL `date` maps to `java.time.LocalDate`. It represents a **calendar date** only, without time of day or offset.

```java
import java.time.LocalDate;

LocalDate businessDay = LocalDate.parse("2026-11-20");
LocalDate nextDay = businessDay.plusDays(1);
```

Appropriate uses:

- Date of birth (when exact birth instant is unneeded).
- Business day used as a **partition bucket**.
- Due/closing dates tied to a defined business timezone.

**Never compute a business day by calling `LocalDate.now()` on the app host without a timezone policy.** Two JVMs in different regions can observe two different calendar dates at the exact same instant.

Safer example:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant instant = Instant.parse("2026-11-20T18:30:00Z");

LocalDate businessDay = instant.atZone(businessZone).toLocalDate();
// Calendar date in the business timezone may differ from UTC.
```

Cassandra `date` does not shift by timezone on storage. **Timezone conversion must happen at application boundaries under an explicit policy**.

## 10. `time` ↔ `LocalTime`: Time of Day, Not an Instant

CQL `time` stores a time within a **calendar day** at nanosecond precision, without date or timezone; Java Driver 4.x maps it to `LocalTime`.

```java
import java.time.LocalTime;

LocalTime scheduledHour = LocalTime.of(14, 35, 12, 123_456_789);
// 14:35:12.123456789, specifying neither date nor timezone.
```

Appropriate uses: store opening hours or daily schedule triggers paired with a defined **`ZoneId`** and DST rules. Never use `LocalTime` to record when a customer clicked a button: time of day alone cannot distinguish two different days.

### What If Local Timestamp Context Is Needed?

An event can store:

- `occurred_at timestamp` → `Instant`, absolute UTC instant.
- `business_day date` → `LocalDate`, bucket computed in the business zone.
- `wall_time time` → `LocalTime`, local wall time for display/scheduling.
- `zone_id text` → `ZoneId` string in the app when origin timezone must be preserved.

Never combine `LocalDate` + `LocalTime` into an `Instant` assuming UTC when the business uses another zone; in DST zones, handle non-existent or ambiguous gap/overlap hours properly.

## 11. `duration` ↔ `CqlDuration`: Months, Days, and Nanoseconds

CQL `duration` carries three parts: **months**, **days**, and **nanoseconds**. Java Driver 4.x represents it as `com.datastax.oss.driver.api.core.data.CqlDuration` and **does not map it directly** to `java.time.Duration` or `Period` by default.

Example:

```java
import java.util.concurrent.TimeUnit;
import com.datastax.oss.driver.api.core.data.CqlDuration;

CqlDuration retentionWindow = CqlDuration.newInstance(
    1,                           // 1 month
    2,                           // 2 days
    TimeUnit.HOURS.toNanos(3)    // 3 hours
);
```

**Why not substitute `Duration.ofDays(32)`?** Calendar months vary in length, days can be affected by timezone/DST when added to local instants, and `java.time.Duration` models only fixed seconds/nanoseconds. When adding a CQL duration to a timestamp, specify **`ZoneId`, addition order (months/days/nanos), and calendar policy**.

Common `duration` constraints:

- Sign consistency: CQL enforces consistent signs across components; you cannot arbitrarily mix positive months with negative days.
- Never use `duration` as a clustering key expecting a clean total ordering across arbitrary values.
- Never convert `duration` into fixed milliseconds if it includes months/days without a base instant and timezone.
- For business TTLs, distinguish CQL `TTL` measured in **seconds** from a `duration` column value.

## 12. CQL Lab: Creating a Table Covering Numeric and Temporal Types

Practice on a **lab Cassandra cluster** with DC `dc1` and enough replicas for RF3. If you have only one node, adjust RF and CL accordingly; `LOCAL_QUORUM` with RF3 and insufficient replicas will fail.

### Step 1 — Create Keyspace

```sql
CREATE KEYSPACE IF NOT EXISTS driver_types_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;
```

### Step 2 — Create Table for a Concrete Read Pattern

```sql
CREATE TABLE IF NOT EXISTS driver_types_lab.measurements_by_id (
    tenant_id text,
    business_day date,
    event_id uuid,
    priority tinyint,
    sensor_number smallint,
    sample_count int,
    sequence_number bigint,
    huge_quantity varint,
    total_amount decimal,
    signal_strength float,
    confidence double,
    occurred_at timestamp,
    wall_time time,
    event_time_id timeuuid,
    retention_window duration,
    PRIMARY KEY ((tenant_id, business_day), event_id)
);
```

**Partition key** is `(tenant_id, business_day)`, scoping data per tenant/day; `event_id` is the clustering key. Because `event_id` is random, this table **does not sort events chronologically**. If an API needs the 20 latest events, redesign the clustering key around that query shape—never try to "fix" it with Java codecs.

### Step 3 — Insert a Sample Row in CQL

```sql
INSERT INTO driver_types_lab.measurements_by_id (
    tenant_id, business_day, event_id,
    priority, sensor_number, sample_count, sequence_number,
    huge_quantity, total_amount, signal_strength, confidence,
    occurred_at, wall_time, event_time_id
) VALUES (
    'tenant-01',
    '2026-11-20',
    11111111-1111-4111-8111-111111111111,
    3, 240, 150, 9000000000,
    123456789012345678901234567890,
    129.95, 0.875, 0.99,
    '2026-11-20T14:35:12.123Z',
    '14:35:12.123456789',
    now()
);
```

`retention_window` is intentionally omitted and stays null on this row. In `cqlsh`, `now()` produces a `timeuuid`; **never use it in a write that may require idempotent retries with a stable ID**.

### Step 4 — Read with Full Partition Key

```text
CONSISTENCY LOCAL_QUORUM;
```

```sql
SELECT priority, sensor_number, sample_count, sequence_number,
       huge_quantity, total_amount, signal_strength, confidence,
       occurred_at, business_day, wall_time, event_time_id,
       retention_window
FROM driver_types_lab.measurements_by_id
WHERE tenant_id = 'tenant-01'
  AND business_day = '2026-11-20'
  AND event_id = 11111111-1111-4111-8111-111111111111;
```

Reading a known partition requires no `ALLOW FILTERING`. Results only reflect the chosen CL; `LOCAL_QUORUM` success does not prove replicas in other DCs are immediately synchronized.

## 13. Java Driver 4.x: Writing Types with `PreparedStatement`

The repository example below compiles once your project adds the matching Java Driver 4.x dependency and creates the Section 12 schema. It shows **one method binding multiple Java types**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.temporal.ChronoUnit;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.data.CqlDuration;
import com.datastax.oss.driver.api.core.uuid.Uuids;

public final class MeasurementWriter {
    private final CqlSession session;
    private final PreparedStatement insert;

    public MeasurementWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO driver_types_lab.measurements_by_id (" +
            "tenant_id, business_day, event_id, priority, sensor_number, " +
            "sample_count, sequence_number, huge_quantity, total_amount, " +
            "signal_strength, confidence, occurred_at, wall_time, " +
            "event_time_id, retention_window) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        );
    }

    public UUID writeSample(String tenantId, LocalDate businessDay) {
        // Generate ID once; in production code, callers should supply
        // a stable ID to handle unknown outcomes and retries safely.
        UUID eventId = UUID.randomUUID();
        UUID timeUuid = Uuids.timeBased();
        Instant occurredAt = Instant.parse(
            "2026-11-20T14:35:12.123456789Z")
            .truncatedTo(ChronoUnit.MILLIS);

        BigDecimal amount = new BigDecimal("129.95");
        BigInteger hugeQuantity =
            new BigInteger("123456789012345678901234567890");
        CqlDuration duration = CqlDuration.newInstance(
            1, 2, TimeUnit.HOURS.toNanos(3));

        BoundStatement statement = insert.bind(
            tenantId,
            businessDay,
            eventId,
            (byte) 3,
            (short) 240,
            150,
            9_000_000_000L,
            hugeQuantity,
            amount,
            0.875f,
            0.99d,
            occurredAt,
            LocalTime.of(14, 35, 12, 123_456_789),
            timeUuid,
            duration
        ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        // Never blindly mark every write idempotent.
        session.execute(statement);
        return eventId;
    }
}
```

### Explaining the Bound Values

| Java Value | CQL Column | Meaning |
| --- | --- | --- |
| `(byte) 3` | `priority tinyint` | Prevents binding `Integer` into `tinyint` |
| `(short) 240` | `sensor_number smallint` | Explicit 16-bit range |
| `150` | `sample_count int` | 32-bit integer |
| `9_000_000_000L` | `sequence_number bigint` | `L` suffix for `long` |
| `BigInteger` | `huge_quantity varint` | Not truncated to `long` |
| `BigDecimal` | `total_amount decimal` | Avoids `double` |
| `0.875f` and `0.99d` | `float`, `double` | Distinct Java floating-point types |
| `Instant` | `occurred_at timestamp` | Normalized to milliseconds |
| `LocalDate` | `business_day date` | Timezone-free |
| `LocalTime` | `wall_time time` | Nanoseconds within day |
| `Uuids.timeBased()` | `event_time_id timeuuid` | Version-1 UUID |
| `CqlDuration` | `retention_window duration` | Months + days + nanoseconds |

**Never mint a new UUID on every retry of the same logical write.** If a request times out, the mutation may have succeeded while the ACK was lost. If the caller re-invokes the method and gets a different `eventId`, the system records **two events** instead of one recovered write.

In real apps, accept an operation/entity ID from the caller, define idempotency and timestamp policies, and handle unknown outcomes explicitly. Counters and LWTs have stricter retry rules still.

## 14. Java Driver 4.x: Reading Back with Type-Matched Getters

Example method reading from the same table, specifying the **full partition key and clustering key**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.data.CqlDuration;

public final class MeasurementReader {
    private final CqlSession session;
    private final PreparedStatement select;

    public MeasurementReader(CqlSession session) {
        this.session = session;
        this.select = session.prepare(
            "SELECT priority, sensor_number, sample_count, " +
            "sequence_number, huge_quantity, total_amount, " +
            "signal_strength, confidence, occurred_at, " +
            "business_day, wall_time, event_time_id, retention_window " +
            "FROM driver_types_lab.measurements_by_id " +
            "WHERE tenant_id = ? AND business_day = ? AND event_id = ?"
        );
    }

    public void inspect(String tenantId, LocalDate day, UUID eventId) {
        BoundStatement statement = select.bind(tenantId, day, eventId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);

        Row row = session.execute(statement).one();
        if (row == null) {
            throw new IllegalStateException("Event not found");
        }

        byte priority = row.getByte("priority");
        short sensor = row.getShort("sensor_number");
        int samples = row.getInt("sample_count");
        long sequence = row.getLong("sequence_number");
        BigInteger hugeQuantity = row.getBigInteger("huge_quantity");
        BigDecimal amount = row.getBigDecimal("total_amount");
        float strength = row.getFloat("signal_strength");
        double confidence = row.getDouble("confidence");
        Instant occurred = row.getInstant("occurred_at");
        LocalDate businessDay = row.getLocalDate("business_day");
        LocalTime wallTime = row.getLocalTime("wall_time");
        UUID timeId = row.getUuid("event_time_id");

        CqlDuration retention = row.isNull("retention_window")
            ? null : row.getCqlDuration("retention_window");

        // Use values to build DTOs/assertions; never log sensitive
        // business payloads or raw partition keys in production.
        if (timeId != null && timeId.version() != 1) {
            throw new IllegalStateException("Unexpected timeuuid version");
        }
    }
}
```

In this snippet, local variables simply demonstrate getters. A complete application builds immutable DTOs, validates business invariants, and returns results to the service. **Never skip `row.isNull(...)` checks on nullable columns**, especially with primitive numeric getters where `0` differs semantically from "unset".

### Why Avoid `SELECT *` in Repositories?

`SELECT *` can return newly added columns after schema migrations; rigid mappers or custom codecs may unexpectedly encounter altered shapes. Explicit column lists:

- Fetch only required data.
- Keep the database–application contract easy to control.
- Reduce payload size and breakage risk during schema evolution.
- Enable clear tests for every CQL/Java type.

## 15. `null` and `UNSET`: They Differ on the Write Path

A Cassandra table can have columns that were never written. On reads, `row.isNull("column")` distinguishes **unset/null** from real values; on writes, **NULL and UNSET behave differently**.

| Situation | Practical Meaning |
| --- | --- |
| Bind a valid value | Writes a new cell mutation for the column |
| `statement.setToNull("col")` | Sets the column to null/deletes its value per CQL semantics, potentially creating a tombstone |
| `statement.unset("col")` | Omits assigning that column in mutations supporting `UNSET` |
| Column omitted from `SELECT` | Column absent from `Row`; never call getters for it arbitrarily |
| Selected column is null | `row.isNull("col") == true` |

Conditional application update example:

```java
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

PreparedStatement prepared = session.prepare(
    "UPDATE driver_types_lab.measurements_by_id " +
    "SET total_amount = ?, confidence = ? " +
    "WHERE tenant_id = ? AND business_day = ? AND event_id = ?"
);

BoundStatement statement = prepared.bind(
    new java.math.BigDecimal("99.50"),
    0.95d, tenantId, businessDay, eventId
);

// Preserve existing confidence: skip writing this column.
statement = statement.unset(1);

// Avoid statement.setToNull(1) when the goal is "leave unchanged".
session.execute(statement);
```

This is a **snippet inside a method** where `session`, `tenantId`, `businessDay`, and `eventId` exist. `unset(1)` targets the second marker (0-based index). In real apps, use consistent marker names and verify bound variable definitions so editing CQL never shifts indices accidentally.

**`UNSET` is not a universal default for everything:** support depends on statement/protocol, and skipping columns changes "PATCH" vs. "REPLACE" semantics. Above all, never pass `null` unconsciously thinking it means "leave unchanged" in an update.

## 16. Time Units: Milliseconds, Microseconds, and Nanoseconds

Unit confusion is one of the sneakiest mapping bugs.

| Quantity | Unit/Meaning | Java/CQL |
| --- | --- | --- |
| `timestamp` column | Milliseconds since epoch | `Instant` via `getInstant` |
| `USING TIMESTAMP` | Microseconds used as write timestamp | `long` in CQL statement |
| `time` column | Nanoseconds since `00:00` of a day | `LocalTime` |
| `duration` nanoseconds component | Nanoseconds within a duration that may also add months/days | `CqlDuration` |
| `System.nanoTime()` | Monotonic clock for elapsed duration in JVM | Not a Unix timestamp |
| `System.currentTimeMillis()` | UTC epoch milliseconds from system clock | Can convert to `Instant` |

Example:

```java
import java.time.Instant;

Instant now = Instant.now();
long epochMillis = now.toEpochMilli();

// Illustrates unit conversion only: never blindly use this
// as a production write timestamp without a concurrency policy.
long epochMicros = Math.multiplyExact(epochMillis, 1_000L);
```

Multiplying milliseconds by `1,000` to get microseconds **does not recover lost sub-millisecond precision**; it pads the lower microsecond digits with zero. If a system requires true microsecond write timestamps, it needs a properly designed clock/coordination source.

### Timezones Are Not Fixed Hour Offsets

`Asia/Ho_Chi_Minh` currently uses `+07:00`, yet historical timezone rules or other regions have DST. **Never manually write `epoch + 7h`** to turn an `Instant` into local time. Use `ZoneId` and `ZonedDateTime`.

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant instant = Instant.parse("2026-11-20T18:30:00Z");
ZonedDateTime businessTime = instant.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh"));
```

## 17. Round-Trip Testing and Schema Compatibility

A round-trip test writes a value from Java to Cassandra, reads it back, and asserts equality using **each type's exact semantics**:

| Type | Valid Assertion | Pitfall Assertion |
| --- | --- | --- |
| `decimal` | `stored.compareTo(expected) == 0` when numeric value matters | `equals` when scale differs and business ignores scale |
| `varint` | `stored.equals(expectedBigInteger)` | Casting to `long` before comparing |
| `float`/`double` | Compare within required tolerance/precision | Exact equality against ideal decimal math |
| `uuid` | `stored.equals(expectedUuid)` | Expecting UUID v4 to sort chronologically |
| `timeuuid` | Valid version-1 UUID, stable per operation | Generating a new UUID per retry and expecting the same ID |
| `timestamp` | Compare against millisecond-truncated `Instant` | Expecting original sub-millisecond nanoseconds |
| `date` | `LocalDate.equals` in defined business timezone | Comparing `Instant` directly to date without zone |
| `time` | `LocalTime.equals` when stored validly | Inferring date/zone from `LocalTime` alone |
| `duration` | Compare months, days, and nanoseconds components | Converting every month to 30 days |

Include boundary data in tests:

- `tinyint` = -128, 0, 127; `smallint` bounds ±32,767 and valid negative values.
- `int`/`bigint` near extremes; test pre-bind overflow guards.
- `varint` exceeding 64 bits and `decimal` with varying scales.
- `float`/`double` representation edge cases, negatives, and zero.
- `timestamp` before and after epoch, plus sub-millisecond values.
- Month-end, year-end, leap years, and DST transitions in applicable zones.
- Nullable columns, prepared statements with `UNSET`, retries, and timeouts.

### Schema Evolution Can Break Codecs

If a column changes from `int` to `bigint` or `text` to `decimal`, **do not alter column types in place carelessly** assuming Java casts will cope. Many type changes are disallowed or break prepared contracts.

The safe workflow is usually adding `amount_v2 decimal`, deploying compatible readers/writers, backfilling, reconciling, and cutting over. Test old/new app versions together, driver metadata, CL, and null handling.

## 18. Diagnosing Type Mapping Errors in Java Applications

| Symptom | Likely Cause | Check Next |
| --- | --- | --- |
| Codec exception or invalid type | Java bind/getter mismatches CQL type | `system_schema.columns`, prepared metadata, Java types |
| `ArithmeticException` on numeric conversion | `BigInteger` exceeds `long`, exact `BigDecimal` rounding fails | Range, precision/scale, business bounds |
| Money off by a few minor units | `double` used instead of `BigDecimal` | Number source, arithmetic, rounding policy |
| `timeuuid` rejected | UUID v4 bound into CQL `timeuuid` | `UUID.version()` and generation method |
| Timestamps shifted by hours | `LocalDateTime`/zone/offset misunderstood | `Instant`, `ZoneId`, parsing timezone |
| Timestamps off by micro/nanoseconds | Cassandra `timestamp` stores milliseconds only | Normalize and test resolution explicitly |
| Day buckets drift across DCs | `LocalDate.now()` computed in host timezone | Fixed business timezone |
| Numbers read as `0` instead of null | Primitive getter without null check | `row.isNull(...)` |
| `UPDATE` accidentally wipes fields | Binding `null` instead of `UNSET` | PATCH/REPLACE semantics and tombstones |
| One event stored twice | Minting a new UUID on retry after unknown outcome | Stable IDs and idempotency |
| `Unavailable` or timeout | RF/CL, node/replica/network rather than Java codec | `nodetool status`, driver errors, CL, p99 |

Distinguish **type/codec failures** from **distributed-system failures**: the Java Driver refusing to bind `BigDecimal` into an incompatible column is a data/schema bug; a `LOCAL_QUORUM` timeout points to replicas, disks, networks, or deadlines.

Safe diagnostic commands in a lab:

```bash
nodetool status
nodetool tablestats driver_types_lab.measurements_by_id
nodetool tablehistograms driver_types_lab measurements_by_id
nodetool tpstats
```

`nodetool` metrics are **node-local** and do not directly show Java codec exceptions. Combine them with sanitized driver logs, query metadata, versions, and concrete test inputs.

## 19. Applied Exercises

### Scenario A — Money Off by 0.01

A service records totals as `double`, then passes them to `new BigDecimal(double)` and rounds. Some invoices are off by one cent after several calculations. Where is the fix?

**Guidance:** Use `decimal`/`BigDecimal` end-to-end or `bigint` minor units; parse directly from decimal strings and standardize rounding/scale. Do not just swap the getter at the end.

### Scenario B — Random `event_id` Yet Wants Latest Events

Schema has `PRIMARY KEY ((tenant_id, day), event_id uuid)` and code uses `UUID.randomUUID()`. The API runs `LIMIT 20` and calls it the 20 latest events. What is wrong?

**Guidance:** Clustering on UUID v4 does not sort by time. Cluster by `occurred_at` plus ID, or use `timeuuid` aligned with the query shape; `LIMIT` does not manufacture chronological order from UUID v4.

### Scenario C — Java Clock Has Nanoseconds

`Instant.parse("2026-11-20T14:35:12.123456789Z")` is bound into `timestamp`. Reading it back yields `.123Z`, failing an `equals` assertion. Did Cassandra lose data?

**Guidance:** `timestamp` stores milliseconds. This resolution limit must be accounted for up front; normalize or use another storage model when true nanosecond fidelity is needed.

### Scenario D — Wrong Bucket Date

Services in two timezones call `LocalDate.now()` for the same UTC event. One writes bucket day 20, the other day 21. Should they stop using `date`?

**Guidance:** `date` is fine if the bucket represents a business day; the bug is the **timezone policy**. Compute `businessDay = instant.atZone(businessZone).toLocalDate()` consistently instead of using the JVM's default timezone.

### Scenario E — One-Month `duration`

A learner converts `1mo` to `Duration.ofDays(30)` and adds it to January 31. Does that work across all calendar dates?

**Guidance:** No. Months have varying lengths; handle months/days using calendar rules, zones, and business logic rather than assuming 30 days.

### Scenario F — Confusing Null and Zero

A `sample_count int` column is added via migration. The repository calls `getInt` without a null check; the dashboard renders `0` for historical rows. Why is that dangerous?

**Guidance:** "No data recorded" differs from "0 samples measured". Check `row.isNull` first and map to `Integer`/`OptionalInt` or explicit domain state.

### Scenario G — Counter Retries

An app sends `UPDATE ... SET views = views + 1`, hits a timeout, and auto-retries twice assuming `counter` is just `long`. What can the resulting count be?

**Guidance:** Outcome is indeterminate; the increment may have applied before the timeout and retries can add again. Never mark counter mutations idempotent for retries; exact per-event counting needs dedicated deduplication.

### Scenario H — `BigDecimal.equals` Reports Inequality

Two rows return `12.30` and `12.3`, and `equals` returns `false` despite identical monetary value. Is the driver buggy?

**Guidance:** Not necessarily. `BigDecimal.equals` compares scale too; `compareTo` compares numeric value. Normalize scale/currency rules in the app before comparing.

## 20. Production Checklist

**Schema and Types**

- [ ] Choose `tinyint`/`smallint`/`int`/`bigint` based on value range; use `varint` only when exceeding 64 bits.
- [ ] Use `decimal` + `BigDecimal` for exact decimals; define scale, rounding, and currency units.
- [ ] Never confuse `counter` with `bigint` despite sharing the `long` Java getter.
- [ ] Use `UUID` for `uuid` and version-1 UUID for `timeuuid`; never assume UUID v4 is time-ordered.
- [ ] Use `Instant` for `timestamp` and document **millisecond** resolution.
- [ ] Use `LocalDate` for `date`, `LocalTime` for `time`, and `CqlDuration` for `duration`.
- [ ] Use an explicit business `ZoneId` for date/bucket calculations, never the JVM default timezone.

**Java Driver and Data Path**

- [ ] Reuse `CqlSession`, prepare `PreparedStatement`s, and bind exact types.
- [ ] Call matching getters and check `row == null` and `row.isNull`.
- [ ] Distinguish `setToNull` from `unset` in updates/PATCHes.
- [ ] Never mint a new ID on retries of the same logical operation; handle unknown outcomes and idempotency.
- [ ] Preserve business RF/CL; never tweak CL to hide codec bugs.
- [ ] Enable TLS/auth, configure local DC/contact points, and protect secrets per environment.
- [ ] Avoid `SELECT *` when mappers/schemas need a stable contract.

**Testing, Operations, and Migrations**

- [ ] Round-trip tests cover large integers, negatives, multi-scale decimals, nulls, UUID/timeuuid, and boundary dates/times.
- [ ] Compare `Instant` after truncating precision rather than expecting nanoseconds from CQL `timestamp`.
- [ ] Test timezones and DST across supported business regions.
- [ ] Test schema migrations across old data, old/new codecs, and rolling app versions.
- [ ] Track p95/p99, timeouts, retries, and codec errors separately; never lump everything into "database is slow".
- [ ] Verify the exact Java Driver 4.x API and Cassandra version/distribution before production rollout.

**Key takeaway:** Mapping Cassandra types to Java is a **contract about precision and semantics**. `decimal` maps to `BigDecimal`, `varint` to `BigInteger`, `uuid`/`timeuuid` both to `UUID` but with different constraints, `timestamp` to `Instant` at millisecond resolution, `date` to `LocalDate`, `time` to `LocalTime`, and `duration` to `CqlDuration`. Only by combining `PreparedStatement`, null/`UNSET` checks, timezone discipline, safe retries, and query-aligned partition keys will a Java application keep data accurate across a distributed Cassandra cluster.
