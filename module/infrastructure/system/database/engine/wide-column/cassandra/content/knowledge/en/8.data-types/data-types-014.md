# Type Conversion, Literals, Boundary Data, and Java Mapping in Apache Cassandra

When using **Apache Cassandra** from Java, data crosses multiple boundaries: external JSON/HTTP or message queues, Java objects in the application, Java Driver **codecs**, **CQL** typed values, and finally cells and partition keys inside the cluster. A value `"42"` could be a **two-character string**, the **integer 42**, or a slice of text-encoded bytes; Cassandra **does not guess** your intent.

This lesson belongs to the **Data Types** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. The module covers distributed wide-column architecture, partition keys, query-driven table design, read/write consistency levels, CQL, replication, compaction, repair, error handling, and Java integration. Beyond literal syntax and `CAST`, this lesson explains why **the right type and the right unit** govern the correctness of keys, boundary data, retries, and queries across replicas.

## 1. Distinguishing Four Operations Commonly Called "Type Conversion"

| Mechanism | Where It Happens | Examples | Key Limitation |
|---|---|---|---|
| **Input parsing** | Java app / API | `Integer.parseInt("42")`, `UUID.fromString(s)` | Must validate format, range, time zone, dimensions |
| **CQL literal** | CQL parser based on target type/context | `42`, `'Việt Nam'`, `0x4f4b` | Literals are not arbitrary strings assignable to any column |
| **CQL `CAST`** | CQL on native types with supported casts | `CAST(amount AS bigint)` | **Not** every source/target pair is supported; can lose data |
| **Driver codec** | Java Driver native-protocol encoding/decoding | `setBigDecimal`, `getInstant` | Java type must match the CQL column type and registered codec |

Data flow should follow this pipeline:

~~~text
Untrusted source data
  -> Parse and validate into Java domain types
  -> Check boundary values, units, time zones, Unicode, IDs
  -> Prepared statement + strongly typed codec
  -> CQL partition/clustering keys and data columns
  -> Replicas / SSTables
  -> Driver decode -> null checks -> DTO / domain object
~~~

Never expect `CAST` in a `SELECT` to alter the underlying type stored in the table. Nor assume swapping a Java getter—such as switching `getInt` to `getString`—will convert types on demand: **codecs follow the CQL column type**, not an arbitrary casting engine.

## 2. CQL Literals: Value Syntax vs. Identifier Syntax

In CQL, a **literal** writes a value directly, unlike an **identifier** naming a table, column, or type.

| Value Type | Example Literal | Interpretation |
|---|---|---|
| `int`, `bigint`, `varint` | `42`, `-7`, `9000000000` | Unquoted integer |
| `decimal`, `float`, `double` | `19.95`, `1.25e-3` | Number with decimal point or exponent |
| `boolean` | `true`, `false` | Boolean keywords; not strings |
| `text`/`varchar`/`ascii` | `'Việt Nam'`, `'OK'` | String enclosed in **single quotes** |
| `uuid` | `550e8400-e29b-41d4-a716-446655440000` | Canonical UUID format, not an arbitrary string |
| `timeuuid` | Valid UUID **v1** | Must match time-based UUID v1 |
| `blob` | `0x4f4b00ff` | Four binary bytes written in hex |
| `inet` | `'203.0.113.24'`, `'2001:db8::1'` | Quoted IPv4/IPv6 literal |
| `date` | `'2026-11-21'` | Calendar date |
| `timestamp` | `'2026-11-21T08:30:15.123Z'` | UTC instant to millisecond precision |
| `time` | `'09:30:15.123456789'` | Time of day to nanosecond precision |
| `duration` | `1mo2d3h` | Months/days/nanoseconds; not a generic second count |
| `list<text>` | `['a', 'b']` | Ordered sequence, duplicates allowed |
| `set<text>` | `{'java', 'cassandra'}` | Duplicate-free set |
| `map<text,int>` | `{'red': 1, 'blue': 2}` | Key → value |
| `tuple<int,text>` | `(10, 'OK')` | Positional values |
| UDT | `{street: 'A', city: 'B'}` | **Named** fields defined in the UDT |
| `vector<float,3>` (Cassandra 5.0+) | `[0.1, 0.2, 0.3]` | Exactly three float elements, non-null |

**Similar-looking syntax does not make two types identical.** `[0.1,0.2,0.3]` can be a list literal or a vector literal depending on **column type/context**. `'123'` is a text literal, distinct from the number `123`; `'false'` is text, distinct from `false`.

### 2.1. Single Quotes, Double Quotes, and Escaping

**Single** quotes delimit string literals; an embedded single quote is escaped as **two single quotes**:

~~~cql
CREATE TABLE labels_by_id (
    label_id uuid PRIMARY KEY,
    display_text text
);

INSERT INTO labels_by_id (label_id, display_text)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'O''Reilly learns Cassandra'
);
~~~

Here the actual stored value is `O'Reilly learns Cassandra`. Never rely on backslash escaping from Java, JSON, or other SQL dialects to construct CQL; each layer has its own rules.

**Double** quotes delimit **identifiers containing uppercase letters or special characters**:

~~~cql
-- Valid, though inconvenient because exact casing must always be preserved.
CREATE TABLE "CaseSensitiveNames" (
    id uuid PRIMARY KEY,
    "DisplayName" text
);
~~~

`"DisplayName"` is an **identifier**, not the string `'DisplayName'`. For new projects, lowercase `snake_case` CQL names prevent lookup and codec metadata headaches.

In production Java, **use prepared statements instead of manual escaping via string concatenation**. Never treat manual `'` → `''` replacement as a substitute for bind variables.

### 2.2. Literals Can Be NULL, but NULL Is Not "Omitted"

~~~cql
UPDATE labels_by_id
SET display_text = null
WHERE label_id = 11111111-1111-4111-8111-111111111111;
~~~

In a CQL mutation, writing NULL to a regular column means **delete the value** and generates a tombstone. Omitting the column from an INSERT/UPDATE, or binding **UNSET** from the driver where supported, means **do not touch that column**. Both can make `SELECT` return null, yet their distributed semantics and tombstone costs differ.

## 3. CQL Table Used Throughout This Lesson

Sample system requirement: store API observations per tenant by **UTC day**, read the 100 newest samples for a day, recording status code, duration, exact bill amount, client IP, verification flag, and a small diagnostic byte sample.

~~~cql
CREATE TABLE api_observations_by_tenant_day (
    tenant_id uuid,
    observation_day date,
    observed_at timestamp,
    observation_id uuid,
    status_code smallint,
    latency_us bigint,
    bill_amount decimal,
    attempt_count varint,
    client_ip inet,
    verified boolean,
    display_label text,
    trace_sample blob,
    tags set<text>,
    PRIMARY KEY (
        (tenant_id, observation_day),
        observed_at, observation_id
    )
) WITH CLUSTERING ORDER BY (observed_at DESC, observation_id ASC);
~~~

Design rationale:

- **`(tenant_id, observation_day)`** is the composite partition key; UTC day bounds partition growth over time.
- **`observed_at timestamp`** is the primary clustering column sorting by source occurrence time at **millisecond** resolution.
- **`observation_id uuid`** disambiguates observations sharing the same millisecond `observed_at`. Keep the ID stable on retries.
- **`status_code smallint`** holds HTTP status codes within application bounds; Java uses `short`.
- **`latency_us bigint`** measures **microseconds**; never interpret it as an epoch timestamp or milliseconds.
- **`bill_amount decimal`** requires decimal precision; Java uses `BigDecimal`.
- **`attempt_count varint`** illustrates an arbitrary-length integer; for small bounded retry counts in practice, `int` is usually better.
- **`client_ip inet`**, **`verified boolean`**, **`display_label text`**, **`trace_sample blob`**, and **`tags set<text>`** preserve distinct semantics; never coerce them all into `text` for convenience.

To see literals in action, insert a sample row:

~~~cql
INSERT INTO api_observations_by_tenant_day (
    tenant_id, observation_day, observed_at, observation_id,
    status_code, latency_us, bill_amount, attempt_count,
    client_ip, verified, display_label, trace_sample, tags
) VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-21',
    '2026-11-21T08:30:15.123Z',
    33333333-3333-4333-8333-333333333333,
    200, 123456, 19.95, 3,
    '203.0.113.42', true,
    'Test payment', 0x4f4b,
    {'payment', 'verified'}
);
~~~

The IP `203.0.113.42` belongs to the documentation address block, not a live host. `0x4f4b` is **two hex bytes** that happen to decode in ASCII as `"OK"`; `blob` carries no charset metadata.

Key-aligned query:

~~~cql
SELECT observed_at, observation_id, status_code, latency_us,
       bill_amount, verified, client_ip
FROM api_observations_by_tenant_day
WHERE tenant_id = 22222222-2222-4222-8222-222222222222
  AND observation_day = '2026-11-21'
LIMIT 100;
~~~

**Do not assume** giving a data column the right type creates a query path on that column. `WHERE client_ip = ...` or `WHERE verified = false` across all tenants/days still requires an index or dedicated query table; `CAST` creates no index.

## 4. Integers and Boundary Values: Validate Before Binding

CQL integer types have distinct ranges:

| CQL | Value Range (Signed) | Typical Java Type | Use Case |
|---|---|---|---|
| `tinyint` | -128 to 127 | `byte` | Small tightly bounded status values |
| `smallint` | -32,768 to 32,767 | `short` | Small codes, e.g., status codes |
| `int` | -2,147,483,648 to 2,147,483,647 | `int` | Bounded counts |
| `bigint` | -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 | `long` | Epoch millis, microsecond latency, 64-bit numeric IDs |
| `varint` | **Arbitrary-precision** integer by type | `BigInteger` | Values exceeding 64 bits |
| `counter` | 64-bit counter with dedicated mutation rules | `long` | Increments/decrements, not regular scalar upserts |

Sizes and ranges belong in the **data contract**. For example:

- HTTP status `200` fits `smallint`; `32768` does not. HTTP statuses also have a **business domain** (three-digit codes), so `12000` fits `smallint` yet must still be rejected as invalid.
- `latency_us = 123456` means 123.456 **milliseconds**, not 123.456 seconds. Use the `_us` suffix to prevent unit confusion.
- `attempt_count` does not need `varint` merely because Java has `BigInteger`; pick a right-sized type to save bytes and clarify the contract.

### 4.1. Java Narrowing Casts Silently Alter Values

~~~java
int raw = 200;
byte narrowed = (byte) raw;

System.out.println(narrowed); // -56, NOT 200.
~~~

In Java, casting `int` to `byte` keeps only the low 8 bits without throwing an overflow exception. Therefore, for values coming from JSON/HTTP, **never write `setByte(0, (byte) raw)`** without validating bounds first.

Helper to validate before narrowing:

~~~java
static byte checkedTinyInt(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new IllegalArgumentException("tinyint out of range");
    }
    return (byte) value;
}

static short checkedSmallInt(int value) {
    if (value < Short.MIN_VALUE || value > Short.MAX_VALUE) {
        throw new IllegalArgumentException("smallint out of range");
    }
    return (short) value;
}
~~~

Nor should CQL serve as your only input validator. Out-of-range literals get rejected, yet the application should raise clear validation errors **before** sending network requests to the cluster.

### 4.2. BigInteger and Exact Conversions

~~~java
import java.math.BigInteger;

BigInteger huge = new BigInteger("9223372036854775808");
// Exceeds Long.MAX_VALUE.

try {
    long exact = huge.longValueExact();
} catch (ArithmeticException outsideLongRange) {
    // Cannot be represented as CQL bigint.
}
~~~

`huge.longValue()` **does not** substitute for `longValueExact()`: unchecked conversion truncates high bits. When storing `varint`, bind `BigInteger` directly through the `varint` codec rather than detouring through `double` or `long`.

**Overflow does not happen only during INSERT.** If an in-app counter sums using `int`, arithmetic overflows **before** binding to Cassandra. Use `Math.addExact`/`Math.multiplyExact` to catch overflow, or choose `long`/`BigInteger` upfront.

## 5. decimal, float, and double: "Both Are Numbers" Does Not Mean Equal Precision

CQL provides:

- **`decimal`**: variable-precision decimal, Java `BigDecimal`.
- **`float`**: 32-bit IEEE 754 binary floating-point, Java `float`.
- **`double`**: 64-bit IEEE 754 binary floating-point, Java `double`.

Example:

~~~java
import java.math.BigDecimal;

BigDecimal exact = new BigDecimal("0.10");
BigDecimal fromBinaryFloat = new BigDecimal(0.1);

System.out.println(exact);           // 0.10
System.out.println(fromBinaryFloat); // Long decimal expansion from double.
~~~

For **money, taxes, and reconciliation**, construct `BigDecimal` from **decimal strings or integer minor units**, never from `new BigDecimal(double)` after `double` math expecting original decimal accuracy.

~~~java
BigDecimal amount = new BigDecimal("19.95");
BigDecimal taxRate = new BigDecimal("0.10");

BigDecimal tax = amount.multiply(taxRate);
BigDecimal rounded = tax.setScale(2, java.math.RoundingMode.HALF_UP);
// rounded = 2.00 under the illustrative rounding rule.
~~~

**Rounding rules must be dictated by the business.** Never assume `HALF_UP` fits every transaction; financial systems may use `HALF_EVEN`, line-item vs. invoice-total rounding, or different scales.

### 5.1. Boundaries of float and double

Checks to perform at the API boundary:

- `Float.isFinite(value)` / `Double.isFinite(value)` to catch `NaN` and `Infinity` in numeric pipelines. Never pass them into keys or embeddings without checking semantics.
- `0.1` has no finite binary representation, so `float`/`double` arithmetic can fail exact `==` comparisons.
- `-0.0` and `+0.0` can behave differently in string formatting or comparisons across layers; never rely on zero's sign for business identity.
- `float` retains roughly 6–9 significant decimal digits and `double` roughly 15–17; large integers can lose unit precision when converted to `double`.

If storing money in **minor units**, `bigint amount_minor` is also a strong choice when currency and scale are explicit. Just never mix `19.95` **major units** with `1995` **minor units** in the same column.

### 5.2. Decimal Has Scale; Java equals Differs from compareTo

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b) == 0); // true: numerically equal.
System.out.println(a.equals(b));         // false: different scale.
~~~

This affects validation, cache keys, round-trip tests, and serialization. If an API enforces a fixed monetary scale, **normalize scale and rounding** before binding; never expect CQL `decimal` to enforce one scale across all callers.

## 6. CQL CAST: A Supported Matrix, Not a Universal Parser

Syntax on CQL expressions:

~~~cql
SELECT
    latency_us,
    CAST(latency_us AS int) AS latency_narrowed,
    CAST(latency_us AS decimal) AS latency_decimal,
    CAST(status_code AS text) AS status_as_text,
    CAST(bill_amount AS bigint) AS amount_truncated
FROM api_observations_by_tenant_day
WHERE tenant_id = 22222222-2222-4222-8222-222222222222
  AND observation_day = '2026-11-21'
LIMIT 10;
~~~

Read those lines strictly as **SELECT return expressions**, not schema changes:

- `latency_us bigint → int`: safe only when values fit in `int`. Larger values silently lose information per Java narrowing semantics.
- `bigint → decimal`: converts to decimal representation without changing magnitude or unit.
- `smallint → text`: formats a **string for display** without turning `status_code` into text on disk.
- `decimal → bigint`: can **truncate fractional digits**; never use this as monetary rounding.

Apache Cassandra documentation defines a **native type CAST matrix**. Main groups:

| Source | Typical Supported Targets | Things to Remember |
|---|---|---|
| `tinyint/smallint/int/bigint/varint` | Other numeric types, `text`, `varchar` per matrix | Narrowing casts can drop digits/bits |
| `float/double/decimal` | Matching numeric and text types per matrix | Casting to integer is not business rounding |
| `ascii` | `text`, `varchar` | Does not normalize Unicode |
| `boolean` | `text`, `varchar` | No general reverse text → boolean CAST |
| `inet`, `uuid`, `timeuuid` | Select targets like text; `timeuuid` also supports date/timestamp | No general text → inet/uuid CAST |
| `timestamp` | `date`, `text`, `varchar` | Extracting date drops hours/minutes/seconds |
| `date` | `timestamp` | Produces a CQL timestamp; loses source calendar meaning if shifted across zones |
| `blob`, collections, tuple, UDT, vector | Not part of the general native CAST matrix | Use dedicated APIs/functions/converters instead of guessing CAST |

**Never assume the following are valid:**

~~~cql
-- No general text -> int CAST:
-- SELECT CAST(display_label AS int) FROM ...;

-- No general text -> uuid CAST:
-- SELECT CAST(display_label AS uuid) FROM ...;

-- No general bigint -> timestamp CAST:
-- SELECT CAST(latency_us AS timestamp) FROM ...;
~~~

Even when a **`CAST` is allowed**, it **never changes the stored column type**. In `WHERE` clauses on a partition key, you must still bind the original key type; never write `WHERE CAST(tenant_id AS text) = ...` to avoid parsing UUIDs in Java. Partition-key access paths match **properly typed encoded keys**.

### 6.1. Why Can CAST Silently Lose Data?

Cassandra docs note that `CAST` conversions follow **Java semantics**. For `decimal` values with fractional digits, casting to an integer **is not equivalent** to `setScale` with a business rounding mode. For out-of-range numbers, narrowing conversions can also truncate or saturate depending on source and target.

**Safety rule:** treat `CAST` as a display/projection convenience when **values are already known to be valid**, never as a validation layer. When exactness is mandatory, validate and convert in Java using `...Exact()` methods and tested range guards.

### 6.2. Never "Migrate" a Column's Physical Type Using SELECT CAST

Suppose a table has `status_code text` with `"200"`, and the team wants `smallint`. `SELECT CAST(status_code AS smallint)` is not a solution—text → smallint **is not in the general CAST matrix**.

The durable approach:

1. Parse `"200"` in the application with explicit rules.
2. Validate both the `short` range and HTTP status domain.
3. Write to a **new `smallint` column/table**.
4. Switch read/write traffic and reconcile data.
5. Clean up old data only after verifying rollback/retention plans.

**Never run ad-hoc `ALTER TABLE`** when a column is in `PRIMARY KEY` or old/new types are incompatible. In Cassandra, changing key types typically requires **a new table + migration**, not a query-time cast.

## 7. Time and Unit Conversion Functions

CQL temporal functions:

| Function | Source | Result |
|---|---|---|
| `to_date(value)` | `timestamp`, `timeuuid` | CQL `date` |
| `to_timestamp(value)` | `date`, `timeuuid` | CQL `timestamp` |
| `to_unix_timestamp(value)` | `date`, `timestamp`, `timeuuid` | Unix **milliseconds** as `bigint` |
| `CAST(timestamp AS date)` | `timestamp` | CQL `date` per Cassandra semantics |
| `current_timestamp()` | No arguments | Current CQL `timestamp` at execution node |

Example:

~~~cql
SELECT
    observed_at,
    to_date(observed_at) AS observation_date,
    to_unix_timestamp(observed_at) AS epoch_ms,
    CAST(observed_at AS text) AS observation_as_text
FROM api_observations_by_tenant_day
WHERE tenant_id = 22222222-2222-4222-8222-222222222222
  AND observation_day = '2026-11-21'
LIMIT 10;
~~~

Distinguish at least **three kinds of timestamps**:

| Concept | Unit | Role |
|---|---|---|
| **`timestamp`** column | Unix **milliseconds** | When the business event occurred |
| Cassandra **write timestamp** (`USING TIMESTAMP`, `WRITETIME`) | Unix **microseconds** | Cell-level conflict resolution metadata |
| `time` | **Nanoseconds since midnight** | Time of day, without date or time zone |

**A number that looks like a timestamp does not specify its unit.** For instance, `1234567890000` might be read as milliseconds by one service while another API sends microseconds. Name fields explicitly (`epoch_ms`, `epoch_us`, `elapsed_ns`) and validate units at protocol boundaries.

### 7.1. date vs. timestamp

`date` is strictly a calendar date; it has no time zone. `timestamp` is an absolute instant, just like `Instant`.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

Instant sourceTime = Instant.parse("2026-11-20T18:30:00Z");
LocalDate utcDay = sourceTime.atZone(ZoneOffset.UTC).toLocalDate();

System.out.println(utcDay); // 2026-11-20
~~~

In Vietnam (UTC+07:00), that instant falls on **November 21** locally. If the table partitions by UTC `observation_day`, Java must compute the UTC date **on both writes and reads**. Never derive partition dates from the default JVM or cqlsh time zone.

### 7.2. Precision and DST

Java `Instant` holds nanoseconds, whereas CQL `timestamp` stores **milliseconds**. Events at `08:30:15.123456Z` and `08:30:15.123987Z` collapse to the **exact same `timestamp`** at millisecond resolution. That is why timeline tables need `observation_id uuid` as a tie-breaker.

Conversely, `time` keeps nanoseconds of time-of-day **without** a date or time zone. Converting `LocalDate + LocalTime + ZoneId` into `Instant` requires handling DST gaps and overlaps.

~~~java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.Instant;

LocalDate calendarDay = LocalDate.parse("2026-11-21");
LocalTime openingTime = LocalTime.parse("08:30");
ZoneId storeZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant openingInstant =
    calendarDay.atTime(openingTime).atZone(storeZone).toInstant();
~~~

Never force a `LocalDate` into a "midnight UTC" `timestamp` just to store a **birth date**. Never use `LocalTime` for a **payment timestamp**. The conversion may be syntactically valid yet destroy business semantics.

### 7.3. duration Does Not Default to java.time.Duration

CQL `duration` stores **months, days, and nanoseconds**. Java Driver maps it to **`CqlDuration`**; JDK's `java.time.Duration` models elapsed seconds/nanoseconds without **calendar months**.

~~~java
import com.datastax.oss.driver.api.core.data.CqlDuration;

CqlDuration billingCycle = CqlDuration.from("1mo");
CqlDuration retryDelay = CqlDuration.from("30m");

System.out.println(billingCycle.getMonths());   // 1
System.out.println(retryDelay.getNanoseconds()); // 1800000000000
~~~

`1mo` does not always equal `30d`; `1d` does not always equal **24 elapsed hours** under DST. When you need a queryable deadline in Cassandra, compute **`due_at timestamp`** using calendar/`ZoneId` rules and store it separately; `duration` lacks a total ordering for clustering keys.

## 8. Unicode, ASCII, VARCHAR, and String Keys

In CQL, `text` and `varchar` are semantically identical UTF-8 string types; `ascii` accepts ASCII characters only. Java uses **`String`** for all three, yet **`String` does not verify `ascii` compliance automatically**.

### 8.1. Visually Identical Unicode Forms

Two `"Café"` strings can be encoded differently:

~~~java
import java.text.Normalizer;
import java.nio.charset.StandardCharsets;

String composed = "Caf\u00e9";
String decomposed = "Cafe\u0301";

System.out.println(composed.equals(decomposed)); // false
System.out.println(composed.getBytes(StandardCharsets.UTF_8).length);
System.out.println(decomposed.getBytes(StandardCharsets.UTF_8).length);

String nfc = Normalizer.normalize(decomposed, Normalizer.Form.NFC);
System.out.println(composed.equals(nfc)); // true
~~~

For a **text partition key**, strings with different bytes land in **different partitions**. Canonicalize at the application layer whenever business rules treat two forms as the same identifier—e.g., NFC normalization plus a case policy for usernames.

**Never blindly lowercase every string.** Display names, case-sensitive SKUs, email local-parts, and legal text have distinct rules. Store a **normalized lookup key** alongside the **original display value** when needed.

### 8.2. Java String.length Does Not Count User-Visible Characters

`String.length()` returns **UTF-16 code units**, not necessarily Unicode code points, grapheme clusters, or UTF-8 bytes.

~~~java
String label = "💡";
System.out.println(label.length()); // 2 UTF-16 code units
System.out.println(label.codePointCount(0, label.length())); // 1 code point
System.out.println(label.getBytes(StandardCharsets.UTF_8).length); // 4 bytes
~~~

For key/cell byte caps, validate **encoded UTF-8 byte length** rather than treating `String.length()` as a storage proxy. For UI limits like "30 visible characters," count Unicode grapheme clusters rather than code points alone.

### 8.3. Validating ascii

~~~java
static boolean isAscii(String value) {
    for (int i = 0; i < value.length(); i++) {
        if (value.charAt(i) > 0x7F) {
            return false;
        }
    }
    return true;
}
~~~

`"VND"` fits ASCII; `"Việt"` contains non-ASCII characters and cannot be written to an `ascii` column. Yet **valid ASCII does not equal valid domain data**: currency codes must also be three uppercase letters from an allowed catalog.

## 9. UUID, timeuuid, inet, and blob: Four Types Requiring Dedicated Parsers

### 9.1. UUID Is Not Arbitrary Text

~~~java
import java.util.UUID;

UUID userId = UUID.fromString("550e8400-e29b-41d4-a716-446655440000");
UUID newId = UUID.randomUUID(); // UUID v4
~~~

Use `UUID.fromString` and validate per contract before binding `uuid`; avoid storing arbitrary strings in text columns with inconsistent ID formats.

`timeuuid` is strictly UUID **v1**, not any UUID. Java Driver provides `Uuids.timeBased()` for client-side timeuuid generation. Never pass `UUID.randomUUID()` (v4) to a `timeuuid` column.

If you call CQL `uuid()` or `now()` directly inside an INSERT, retrying after a timeout **generates a brand-new ID**. For idempotent events, generate the ID once in the application and reuse it across attempts.

### 9.2. inet Stores IP Addresses Only

CQL `inet` literals are written as IP strings:

~~~cql
-- inet column:
-- '203.0.113.42'
-- '2001:db8::42'
~~~

`'api.example.com'` is a **hostname**, not an IP literal; `'203.0.113.0/24'` is a **CIDR block**, not a single address. Java's `InetAddress.getByName(input)` can trigger DNS resolution on hostnames, so **never use it directly to validate that input is an IP literal**.

Constructing an address from already parsed bytes:

~~~java
import java.net.InetAddress;

InetAddress address = InetAddress.getByAddress(
    new byte[]{(byte)203, 0, 113, 42}
);
System.out.println(address.getHostAddress()); // 203.0.113.42
~~~

For API inputs, use a parser accepting IPv4/IPv6 literals only to prevent unintended DNS lookups. Remember logged IPs may be proxy/NAT addresses; **passing `inet` validation does not prove IP provenance**.

### 9.3. Blob Is Raw Bytes, Not a String Whose Charset You Guess

Literal:

~~~cql
-- Four bytes: 00 4f 4b ff
-- 0x004f4bff
~~~

In Java:

~~~java
import java.nio.ByteBuffer;

byte[] raw = {0x00, 0x4f, 0x4b, (byte) 0xff};
ByteBuffer snapshot = ByteBuffer.wrap(raw.clone());

ByteBuffer view = snapshot.duplicate();
byte[] actual = new byte[view.remaining()];
view.get(actual);
~~~

`ByteBuffer` tracks `position`, `limit`, and `remaining()`. Avoid calling `buffer.array()` blindly: direct/read-only buffers may throw, and backing arrays can contain bytes outside the active slice.

Base64 (`T0s=`) and hex (`0x4f4b`) are **text encodings of bytes**, not raw bytes in every protocol. When an API sends Base64, **decode** it before binding `blob`, and document the output format when reading.

### 9.4. Blob Conversion Functions Differ from CAST

CQL provides functions converting native types to their byte representation as **`type_as_blob(...)`** and back as **`blob_as_type(...)`** for matching types. Example:

~~~cql
SELECT
    latency_us,
    bigint_as_blob(latency_us) AS latency_binary
FROM api_observations_by_tenant_day
WHERE tenant_id = 22222222-2222-4222-8222-222222222222
  AND observation_day = '2026-11-21'
LIMIT 5;
~~~

`bigint_as_blob(3)` produces the 8-byte CQL binary encoding of `bigint` `3`; this is **not** the UTF-8 string `"3"`. Blob functions **interpret/emit bytes using native codecs**, unlike `CAST(... AS text)` which formats text.

Never feed arbitrary blobs into `blob_as_bigint` without guaranteeing **exact byte length and format**, or decoding will fail.

## 10. Collections, Tuples, UDTs, and Vectors Need Typed Codecs

Several CQL types cannot simply be "CAST to text and reparsed" as a standard data pattern:

| CQL | Literal | Java Driver 4.x |
|---|---|---|
| `list<uuid>` | `[uuid1, uuid2]` | `List<UUID>`, `setList`/`getList` |
| `set<text>` | `{'a','b'}` | `Set<String>`, `setSet`/`getSet` |
| `map<text,int>` | `{'x':1}` | `Map<String,Integer>`, `setMap`/`getMap` |
| `tuple<double,double>` | `(10.77,106.70)` | `TupleValue`, `setTupleValue`/`getTupleValue` |
| `frozen<address_udt>` | `{street:'A',city:'B'}` | `UdtValue`, `setUdtValue`/`getUdtValue` |
| `vector<float,3>` (5.0+) | `[0.1,0.2,0.3]` | `CqlVector<Float>`, `setVector`/`getVector` on supporting drivers |

**Boundary notes:**

- `list` permits duplicates; `set` deduplicates members; `map` enforces unique keys. These are type semantics, not literal syntax differences.
- Never insert **NULL elements** or null map keys/values as if collections were arbitrary JSON.
- Tuples are always treated as **frozen**; changing one element replaces the entire tuple.
- Frozen UDTs/collections behave as a single value; non-frozen ones support select field/entry updates in CQL.
- Vectors have **fixed N dimensions**, no NULL elements, and depend on **Cassandra and Java Driver version**. Storing a vector **does not automatically create an ANN index**.
- Unboundedly growing collections must never be stuffed into one cell/row. Whenever items need independent pagination, TTL, or lookups, use a **multi-row table** with an aligned primary key.

### 10.1. Java Sample with set

~~~java
import java.util.Set;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

PreparedStatement changeTags = session.prepare(
    "UPDATE api_observations_by_tenant_day "
  + "SET tags = tags + ? "
  + "WHERE tenant_id = ? AND observation_day = ? "
  + "AND observed_at = ? AND observation_id = ?");

session.execute(
    changeTags.boundStatementBuilder()
        .setSet(0, Set.of("reviewed"), String.class)
        .setUuid(1, tenantId)
        .setLocalDate(2, observationDay)
        .setInstant(3, observedAt)
        .setUuid(4, observationId)
        .build()
);
~~~

This demonstrates **adding a set element**. With `list`, retrying an append after a timeout can insert duplicates. With `map`, replacing the whole map to edit one key can lose concurrent updates; use single-entry updates when appropriate.

## 11. NULL, Missing Values, UNSET, and JSON Carry Different Semantics

A PATCH API must distinguish at least three states:

| API Input | Intent | CQL / Driver |
|---|---|---|
| Field **absent** | Keep existing value | Omit from mutation or bind **UNSET** |
| Field **present with null** | Clear value, if contract defines it | Bind **CQL NULL**/`setToNull`; creates tombstone |
| Field **present with a value** | Write new value | Bind typed value, including `false`, `0`, `""` |

Partial update example:

~~~java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

PreparedStatement patch = session.prepare(
    "UPDATE api_observations_by_tenant_day "
  + "SET display_label = ?, verified = ? "
  + "WHERE tenant_id = ? AND observation_day = ? "
  + "AND observed_at = ? AND observation_id = ?");

// Assumes keys and values are resolved outside this snippet.
session.execute(
    patch.boundStatementBuilder()
        .setString(0, "Verified")
        .unset(1)               // Leave verified unchanged.
        .setUuid(2, tenantId)
        .setLocalDate(3, observationDay)
        .setInstant(4, observedAt)
        .setUuid(5, observationId)
        .build()
);
~~~

When business logic requires **clearing** `display_label`, call `setToNull(0)`, not `unset(0)`. `verified = false` is a **real value**, not null; check `row.isNull("verified")` when distinguishing unverified states.

**Primary keys cannot be NULL or UNSET**: Cassandra needs full keys in an INSERT to locate the row. UNSET is a bind-variable state, not a cell value stored on disk.

### 11.1. Important Exception: INSERT JSON

CQL `INSERT JSON` defaults to treating **fields missing from the JSON** as **NULL**, which can generate tombstones and erase prior values when upserting an existing primary key. To "leave missing fields untouched," specify **`DEFAULT UNSET`**:

~~~cql
-- Partial JSON upsert: missing columns are skipped.
INSERT INTO api_observations_by_tenant_day
JSON '{"tenant_id":"22222222-2222-4222-8222-222222222222","observation_day":"2026-11-21","observed_at":"2026-11-21T08:30:15.123Z","observation_id":"33333333-3333-4333-8333-333333333333","display_label":"Updated label"}'
DEFAULT UNSET;
~~~

`DEFAULT UNSET` applies only to **absent fields** in the JSON; if the JSON explicitly contains `"display_label": null`, that remains an explicit NULL. Never splice client JSON input directly into CQL commands via string concatenation in production code.

### 11.2. A SELECT Returning null Does Not Prove Data Never Existed

A column can return null because it was **never written**, was **deleted (`DELETE`)**, or **expired via TTL**. Tombstones drive distributed deletion propagation; `UNSET` generates no tombstone for skipped columns. Never infer deletion history from a null read: when auditing is required, persist dedicated **audit events** with ID, timestamp, and actor.

## 12. CQL ↔ Java Driver 4.x Mapping Table

The table below lists common types/codecs; setter names correspond to `BoundStatementBuilder`, getters to `Row`.

| CQL | Java | Setter | Getter |
|---|---|---|---|
| `ascii`, `text`, `varchar` | `String` | `setString` | `getString` |
| `tinyint` | `byte` | `setByte` | `getByte` |
| `smallint` | `short` | `setShort` | `getShort` |
| `int` | `int` | `setInt` | `getInt` |
| `bigint`, `counter` | `long` | `setLong` for bigint; **counters update differently** | `getLong` |
| `varint` | `BigInteger` | `setBigInteger` | `getBigInteger` |
| `decimal` | `BigDecimal` | `setBigDecimal` | `getBigDecimal` |
| `float`, `double` | `float`, `double` | `setFloat`, `setDouble` | `getFloat`, `getDouble` |
| `boolean` | `boolean` | `setBoolean` | `getBoolean` |
| `uuid`, `timeuuid` | `UUID` | `setUuid` | `getUuid` |
| `date` | `LocalDate` | `setLocalDate` | `getLocalDate` |
| `time` | `LocalTime` | `setLocalTime` | `getLocalTime` |
| `timestamp` | `Instant` | `setInstant` | `getInstant` |
| `duration` | `CqlDuration` | `setCqlDuration` | `getCqlDuration` |
| `inet` | `InetAddress` | `setInetAddress` | `getInetAddress` |
| `blob` | `ByteBuffer` | `setByteBuffer` | `getByteBuffer` |
| `list<T>` | `List<T>` | `setList` | `getList` |
| `set<T>` | `Set<T>` | `setSet` | `getSet` |
| `map<K,V>` | `Map<K,V>` | `setMap` | `getMap` |
| `tuple<...>` | `TupleValue` | `setTupleValue` | `getTupleValue` |
| UDT | `UdtValue` | `setUdtValue` | `getUdtValue` |
| `vector<float,N>` (5.0+) | `CqlVector<Float>` | `setVector` | `getVector` |

**For `counter`**, never use `INSERT`/`setLong` like a regular bigint column to increment counts. Counters require `UPDATE ... SET count = count + ?` and are **non-idempotent** on retry, demanding a dedicated workflow.

**For Java primitive getters**, null maps to primitive defaults. Whenever null carries business meaning, check **`row.isNull("column")` first**:

~~~java
Integer status = row.isNull("status_code")
    ? null : (int) row.getShort("status_code");

Boolean verifiedValue = row.isNull("verified")
    ? null : row.getBoolean("verified");
~~~

`Boolean.FALSE` differs from **null**; `Integer` `0` differs from null. Never lose "unset" semantics by mapping straight to primitive defaults in a DTO.

### 12.1. Codecs Are Selected by CQL Type, Not Just Java Class

Java `String` can map to `text`, `varchar`, or `ascii`. `UUID` can map to `uuid` or `timeuuid`. Consequently, the driver needs the CQL type from **prepared bind-variable/column metadata** to choose the right codec.

With a **simple statement** lacking full type metadata, default inference may differ from intent—for instance, `String` infers `text`, not `ascii` or `inet`. Prepared statements make type binding explicit and avoid manual literal formatting.

Custom codecs can support custom domain objects, provided you test **round-trip encode/decode**, nulls, byte order, sizing, version compatibility, and all nodes/clients sharing the schema.

## 13. Java End-to-End: Validate Then Write with Prepared Statements

Suppose incoming JSON contains:

~~~json
{
  "statusCode": 200,
  "latencyMicros": 123456,
  "billAmount": "19.95",
  "attemptCount": "3",
  "clientIp": "203.0.113.42",
  "verified": true,
  "displayLabel": "Test payment"
}
~~~

Passing `"19.95"` and `"3"` as **JSON strings** is a deliberate contract choice to prevent intermediate JSON parsers from turning them into floating-point numbers or losing `BigInteger` precision. Not every API must do this; what is mandatory is consistent typing and validation.

### 13.1. Constructing Typed Java Values

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.net.InetAddress;
import java.nio.ByteBuffer;
import java.text.Normalizer;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Set;
import java.util.UUID;

// CqlSession session = ...; // Connected to cluster with keyspace selected.
UUID tenantId =
    UUID.fromString("22222222-2222-4222-8222-222222222222");
UUID observationId =
    UUID.fromString("33333333-3333-4333-8333-333333333333");

Instant observedAt = Instant.parse("2026-11-21T08:30:15.123Z");
LocalDate observationDay =
    observedAt.atZone(ZoneOffset.UTC).toLocalDate();

short statusCode = checkedSmallInt(200);
long latencyMicros = 123456L;
if (latencyMicros < 0) {
    throw new IllegalArgumentException("latency must not be negative");
}

BigDecimal amount = new BigDecimal("19.95");
if (amount.signum() < 0 || amount.scale() > 2) {
    throw new IllegalArgumentException("invalid billAmount");
}
BigInteger attempts = new BigInteger("3");
if (attempts.signum() < 0) {
    throw new IllegalArgumentException("attempts must be >= 0");
}

// IP already parsed/validated into 4 bytes, no DNS lookup.
InetAddress ip = InetAddress.getByAddress(
    new byte[]{(byte)203, 0, 113, 42}
);

String label = Normalizer.normalize(
    "Test payment", Normalizer.Form.NFC
);

byte[] traceBytes = {0x4f, 0x4b};
ByteBuffer trace = ByteBuffer.wrap(traceBytes.clone());
~~~

This snippet uses `checkedSmallInt(int)` defined in the integers section; in real projects, place validation helpers in the matching domain module. These illustrative checks do not replace full HTTP status policies, currency scales, business caps, or PII protections.

### 13.2. Bind the Right Types and Reuse the Statement on Retries

~~~java
PreparedStatement ps = session.prepare(
    "INSERT INTO api_observations_by_tenant_day "
  + "(tenant_id, observation_day, observed_at, observation_id, "
  + " status_code, latency_us, bill_amount, attempt_count, "
  + " client_ip, verified, display_label, trace_sample, tags) "
  + "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)");

BoundStatement stmt = ps.boundStatementBuilder()
    .setUuid(0, tenantId)
    .setLocalDate(1, observationDay)
    .setInstant(2, observedAt)
    .setUuid(3, observationId)
    .setShort(4, statusCode)
    .setLong(5, latencyMicros)
    .setBigDecimal(6, amount)
    .setBigInteger(7, attempts)
    .setInetAddress(8, ip)
    .setBoolean(9, true)
    .setString(10, label)
    .setByteBuffer(11, trace)
    .setSet(12, Set.of("payment", "verified"), String.class)
    .build();

session.execute(stmt);

// On timeout/connection reset, this unit of work can retry
// using the exact same tenantId, observationDay, observedAt,
// observationId, and finalized values above.
~~~

In async calls, never mutate `ByteBuffer`, backing arrays, collections, or mutable objects while the request is in flight; take snapshots when needed. Reusing **the same primary key** is necessary for idempotent event inserts/upserts, though if column values are recomputed with different write timestamps, conflict behavior still applies.

### 13.3. Reading with Null Checks

~~~java
import com.datastax.oss.driver.api.core.cql.Row;

PreparedStatement find = session.prepare(
    "SELECT status_code, latency_us, bill_amount, attempt_count, "
  + " client_ip, verified, display_label, trace_sample "
  + "FROM api_observations_by_tenant_day "
  + "WHERE tenant_id = ? AND observation_day = ? "
  + "AND observed_at = ? AND observation_id = ?");

Row row = session.execute(
    find.bind(tenantId, observationDay, observedAt, observationId)
).one();

if (row != null) {
    Integer status = row.isNull("status_code")
        ? null : (int) row.getShort("status_code");

    Long latency = row.isNull("latency_us")
        ? null : row.getLong("latency_us");

    BigDecimal bill = row.getBigDecimal("bill_amount");
    BigInteger attemptsRead = row.getBigInteger("attempt_count");
    InetAddress clientIp = row.getInetAddress("client_ip");

    Boolean verifiedRead = row.isNull("verified")
        ? null : row.getBoolean("verified");

    ByteBuffer binary = row.getByteBuffer("trace_sample");
    // If binary != null, read via remaining(); never assume
    // array() is safe to call on the buffer.
}
~~~

Distinguish two different states: **`row == null`** (no row matched the query key) and **`row.isNull("status_code")`** (row exists, but the column is missing/deleted/TTL-expired). Never conflate these two when building DTOs or making business decisions.

## 14. Query by Stored Types; Never CAST Around the Partition Key

The table in Section 3 is designed for reads by **tenant + UTC day**:

~~~cql
SELECT observed_at, observation_id, bill_amount
FROM api_observations_by_tenant_day
WHERE tenant_id = 22222222-2222-4222-8222-222222222222
  AND observation_day = '2026-11-21'
  AND observed_at >= '2026-11-21T08:00:00Z'
  AND observed_at <  '2026-11-21T09:00:00Z'
LIMIT 100;
~~~

Cassandra requires the full **partition key**, then supports a **clustering range**. Never expect `CAST(observed_at AS text)` to yield a more useful order than `timestamp`, nor wrap key columns in cast expressions inside `WHERE` expecting a "new index."

### 14.1. Key Boundary Bugs Cause Partitioning Errors

| Small Discrepancy | Potential Consequence |
|---|---|
| `observation_day` computed in UTC on write, system local zone on read | Queries look in the wrong daily partition |
| Username key in NFC vs. NFD | Two separate text partitions |
| Generating a new event ID after timeout | Two rows for one business event |
| Using `timestamp` alone without a secondary UUID | Two same-millisecond events share one primary key |
| Serializing binary keys with different byte orders across clients | Distinct binary keys |
| Using proxy IP instead of trusted source IP in an IP-keyed table | Many users collapse into one hotspot partition |
| Converting `bigint` IDs to `double` in an intermediate JSON layer | Low bits lost, wrong key |

**A valid CQL type does not guarantee a well-distributed partition key.** For instance, `boolean` is valid in keys by type rules, yet a partition key with only `true`/`false` produces two giant hotspot partitions at scale. Base key design on query patterns, cardinality, partition sizes, and real load.

### 14.2. When Key Schemas or Types Must Change

If you used `customer_id text` and later want `uuid`, do not expect `ALTER TABLE ...` or `CAST` to convert data safely in place, especially inside **`PRIMARY KEY`**. Keys dictate how Cassandra computes tokens and locates rows.

Safe migration workflow:

1. Create a **new schema/table** with the target types.
2. Normalize and validate all source IDs; classify unparseable records.
3. Build an **old ID → new UUID** mapping if existing IDs cannot convert 1-to-1 while preserving identity.
4. Write new traffic with **stable keys**, dual-writing as needed.
5. Run rate-limited, checkpointed, idempotent backfills.
6. Reconcile counts, keys, samples, boundary cases, partitions, and secondary query tables.
7. Cut over reads, monitor errors/latency, then retire the old table per your rollback plan.

**Changing a column's type is not changing its display format.** For `text → uuid`, `decimal → bigint`, or `timestamp → bigint`, design semantics and a migration plan separately.

## 15. Boundary Cases to Test from Day One

When testing Cassandra reads and writes, do not test only `1`, `"hello"`, a tidy UUID, and the current timestamp. Include at least this matrix:

| Category | Test Case | What to Verify |
|---|---|---|
| Integers | Min/max of tinyint/smallint/int/bigint | Lossless round-trip |
| Integers | Min−1 / Max+1 | Validation rejects before binding |
| BigInteger | `Long.MAX_VALUE + 1` | Preserved by `varint`, rejected for `bigint` |
| Decimal | `0.1`, `19.95`, `1.00`, large scales | Never built from `double`; explicit rounding |
| Floating point | `0.1f`, `-0.0`, `NaN`, infinity | Finite checks; never used for money/IDs |
| Boolean | `true`, `false`, null | `false` is not misread as "missing" |
| Unicode | NFC/NFD, emoji, single quotes, empty strings | Canonicalization, escaping, and byte length |
| ASCII | `ABC`, `Việt` | Strict ASCII domain validation |
| Time | UTC, non-UTC offsets, pre-epoch, DST | Exact round-trip and time-zone interpretation |
| Precision | Two `Instant` values <1 ms apart | Aware CQL `timestamp` collapses to same ms |
| Date | UTC date vs. local date | Consistent bucketing |
| UUID | UUID v4, timeuuid v1, malformed strings | Right version, no regeneration on retry |
| Blob | `0x00ff`, empty bytes, direct/read-only `ByteBuffer` | Read via `remaining`, independent of `array()` |
| IP | IPv4, IPv6, hostname, CIDR | Parse IP literals only for `inet` columns |
| Collections | Empty/null/missing, duplicates, NULL items | Exact CQL and API semantics |
| UDT/tuple | Missing fields, wrong index, frozen values | Right codec and unit of mutation |
| Vector | Wrong dimension, `NaN`, zero norm, different model | Tested only when cluster/driver support it |
| Mutation | Missing field, explicit null, UNSET, expired TTL | Right keep/delete behavior, intentional tombstones |
| Retry | Timeout after coordinator may have written | Identical primary key and business payload |

### 15.1. Test Round-Trips, Not Just Whether INSERT Succeeds

For an input \(x\), test:

~~~text
Input x
 -> Java parse + validate
 -> Driver encode
 -> CQL write
 -> CQL read
 -> Driver decode
 -> Value y
 -> Compare x and y under chosen domain semantics
~~~

Define **what equality means**:

- For `BigDecimal`, compare numerically via `compareTo == 0` or require **exact scale**.
- For `Instant` → CQL `timestamp`, compare at **millisecond resolution**; do not expect nanoseconds.
- For Unicode, when canonicalizing, compare **post-normalization** values rather than raw inputs.
- For `ByteBuffer`, compare **the bytes in `remaining()`**, not object identity.
- For `set`, do not compare display order; for `list`, order is part of semantics.

### 15.2. Do Not Forget Malformed Data and JSON Inputs

An ingest pipeline can receive:

~~~json
{
  "statusCode": 9999999999,
  "billAmount": "19,95",
  "verified": "false",
  "observedAt": "21/11/2026 15:30",
  "clientIp": "api.example.com"
}
~~~

Each field carries a distinct issue:

- `9999999999` overflows both `smallint` and `int`; reject or route to a dead-letter queue.
- `"19,95"` violates dot-decimal contract; never guess locales in financial parsers.
- `"false"` is a JSON string, not JSON boolean `false`; decide explicitly at the API whether string coercion is permitted.
- `"21/11/2026 15:30"` lacks time zone and standard ISO format; require an explicit schema contract.
- `"api.example.com"` is a hostname, not an IP literal for `inet`.

Never rely on **CQL CAST** to sanitize arbitrary inputs on coordinators: it is not a general ingestion validator, and pushing malformed data across the network wastes cluster capacity.

## 16. Common Mistakes and Solutions

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming `'123'` always auto-converts to int | Type mismatch or ambiguous semantics | Parse/validate in app, bind `setInt` |
| Using `CAST(text AS int)` as a parser | Unsupported by native CAST matrix | Convert in Java upfront; run controlled migrations |
| Casting `int` to `byte` without range checks | `200` silently becomes `-56` | Validate against `Byte.MIN_VALUE`/`MAX_VALUE` |
| Narrowing `BigInteger` with `longValue()` | Drops high bits silently | Use `longValueExact()` or keep `varint` |
| Constructing `BigDecimal` from `double` | Introduces binary floating-point error | Use `new BigDecimal("19.95")` |
| Using `float/double` for money | Reconciliation drift from binary precision | Use `decimal` or minor-unit `bigint` |
| Using `CAST(decimal AS int)` for rounding | Truncates fractions instead of business rounding | Round explicitly in Java |
| Confusing ms with `WRITETIME` µs | Timestamps off by 1,000x | Suffix names and verify units |
| Losing nanoseconds when writing `Instant` to `timestamp` | Events collapse to same millisecond | Add UUID tie-breaker / source sequence |
| Computing buckets with JVM default time zone | Writes and reads hit wrong partitions | Standardize `ZoneOffset.UTC` or one business `ZoneId` |
| Using `String.length()` as UTF-8 byte count | Wrong size limits for Unicode | Use `getBytes(UTF_8).length` |
| Putting accented Vietnamese text into `ascii` | Violates character domain | Use `text` for Unicode |
| Treating NFC and NFD as identical partition keys | Visually identical strings split across partitions | Apply Normalizer / canonical keys |
| Calling `InetAddress.getByName` to "just parse an IP" | Can trigger DNS lookups | Use literal parser + `getByAddress` |
| Binding UUID v4 into `timeuuid` | Violates CQL UUID v1 contract | Generate UUID v1 |
| Calling `ByteBuffer.array()` unchecked | Reads extra bytes or fails on direct buffers | Use `duplicate()` + `remaining()` |
| Sending NULL for omitted PATCH fields | Unwanted deletions and tombstones | Bind UNSET or omit column |
| Retrying list append after timeout | Can insert duplicate elements | Use stable event IDs or multi-row tables |
| Writing `vector<float,N>` to older clusters | Unsupported schema/codec | Verify Cassandra and driver versions |
| Changing key types via `ALTER` without migration | Breaks token/row layout | New table, backfill, reconcile, cutover |
| Expecting `LOCAL_QUORUM` to fix bad casts | Replicas simply copy bad written values | Validate and fix data at the source |

## 17. Distributed Operations: Bad Data Still Replicates Perfectly

Some data bugs stem not from CQL syntax, but from **interpretation**:

- `latency_us = 5000` read by another service as 5,000 **ms**;
- `display_label` normalized to NFC in service A and NFD in service B;
- `observation_day` computed in UTC on write and local time on lookup;
- `19.95` routed through `double` and stored as a noisy multi-digit decimal;
- two workers generating different `observation_id`s for one request after a timeout.

**Replication** faithfully copies whatever bytes and values were written. **Repair** converges replicas using write metadata. **Compaction** merges SSTables and clears eligible tombstones. **None of these mechanisms infer "the right currency unit," "UTC day," or "that two IDs represent one event."**

Cassandra `INSERT` generally acts as an **upsert** by primary key. On retries:

1. Keep the **same partition key / clustering key**—never generate a new ID.
2. Keep the **same normalized values**—never recompute `Instant.now()` or re-round under a different context.
3. When updating multiple query tables, implement reconciliation/recovery; separate CQL statements are not a multi-partition ACID transaction.
4. When guaranteeing "create only if absent," evaluate `IF NOT EXISTS` (LWT) and handle `[applied]`/timeouts rather than assuming UUIDs enforce business uniqueness by themselves.
5. Never use `LOCAL_QUORUM` as a cure for badly typed input; consistency levels tune replica acknowledgments, not business validation.

### 17.1. TTL and Write Timestamps Have Their Own Units Too

- `USING TTL` takes a lifetime in **seconds**.
- `USING TIMESTAMP` on a mutation takes **microseconds** for write-version resolution.
- CQL `timestamp` columns store **milliseconds** for business instants.
- `time` stores **nanoseconds within a day**, not an absolute deadline.
- `duration` stores months/days/nanoseconds and cannot convert to second-based TTLs while honoring calendar lengths everywhere.

Adding unit suffixes in code (`_sec`, `_ms`, `_us`, `_ns`) and writing round-trip tests prevents subtle bugs far better than relying on CQL CAST.

### 17.2. Monitoring Encode/Decode Errors and Schema Drift

In production, track:

- Validation failure counts by field and data source.
- `CodecNotFound`, type-mismatch, and invalid-query errors alongside Java Driver and cluster versions.
- Ingestion dead-letter rates, retries, and idempotency conflicts.
- Oversized/hot partitions by tenant/day; p95/p99 read/write latency.
- Tombstones and compaction/repair backlogs if applications write NULLs in bulk.
- Schema agreement and version rollouts when adding UDTs/vectors or updating codecs.

Never dump raw PII, IPs, payloads, or arbitrary blobs into logs just to debug type-conversion bugs. Use redaction, trace IDs, and synthetic fixtures in docs and tests.

## 18. Exercises with Answers

### Exercise 1 — Same-Looking Literals, Different Types

Given two CQL values:

~~~text
123
'123'
~~~

**Question:** are they equivalent? Should an app receive `"123"` from an API and bind it with `setString` into an `int` column?

**Answer:** no. One is an integer literal and the other is a string. For an `int` column, parse `"123"` to `int` in the application, validate bounds, and bind `setInt` on a prepared statement.

### Exercise 2 — Narrowing Overflow

~~~java
int incoming = 200;
byte status = (byte) incoming;
~~~

**Question:** does `status` equal 200?

**Answer:** no, it equals `-56`. Use `tinyint` only when valid values never exceed 127. HTTP status `200` typically belongs in `smallint` or `int`, never `tinyint`.

### Exercise 3 — Decimal vs. Double

~~~java
BigDecimal a = new BigDecimal("19.95");
BigDecimal b = new BigDecimal(19.95);
~~~

**Question:** why can these two results differ?

**Answer:** `b` starts from an IEEE 754 binary floating-point number that cannot represent 19.95 exactly; `a` parses decimal digits directly. Construct `BigDecimal` from strings or minor integer units for finance with explicit rounding rules.

### Exercise 4 — Timestamp, Time Zone, and Buckets

An event at `2026-11-20T18:30:00Z` is stored using UTC day buckets, yet one Java client computes the bucket using `ZoneId.of("Asia/Ho_Chi_Minh")`.

**Answer:** the UTC bucket is `2026-11-20`, while the local date in Vietnam is `2026-11-21`. If the table contract specifies UTC days, every writer and reader must use UTC.

### Exercise 5 — NULL vs. UNSET

A row already has `verified = true`. A PATCH request sends `displayLabel` only, omitting `verified`.

**Question:** bind `setToNull` or `unset` for `verified`?

**Answer:** **UNSET** (or omit the column from the mutation) to keep `true`. Calling `setToNull` deletes `verified` and creates a tombstone.

### Exercise 6 — Blob from a Base64 API

An API sends `"T0s="`, the Base64 encoding of bytes `4f 4b`.

**Question:** is storing `"T0s="` in a `text` column equivalent to storing `0x4f4b` in a `blob` column?

**Answer:** no. `text` holds four characters; `blob` holds two bytes. To store the raw bytes, call `Base64.getDecoder().decode(value)` and `ByteBuffer.wrap(...)`.

### Exercise 7 — Can CAST Solve a Migration?

A table has `customer_id text PRIMARY KEY`, with many codes like `"0000123"`. Engineering wants to switch the column to `uuid`.

**Answer:** you cannot simply run `CAST(customer_id AS uuid)` (not in the native CAST matrix) or swap Java getters. The source codes are **not even UUIDs**; you need an ID-issuance/mapping policy, a new table, backfill, and reconciliation.

### Exercise 8 — Is Time Order Enough?

Two requests share `observed_at = 08:30:15.123Z` for the same tenant/day, with different `observation_id` values.

**Question:** can the table store both rows? Can you tell which occurred first at nanosecond precision?

**Answer:** both rows are stored because their full primary keys differ. However, tie-breaking order at identical timestamps follows the UUID comparator, **not true sub-millisecond physical order**. If finer ordering is needed, add a validated source sequence or high-resolution timestamp.

## 19. Checklist for Reviewing Type Conversion, Literals, and Boundary Data

- [ ] Is all incoming data **parsed and validated** in Java rather than relying on Cassandra to guess types?
- [ ] Do CQL literals follow exact rules for single quotes, booleans, UUIDs, IPs, hex blobs, collections, UDTs, and vectors?
- [ ] Are **prepared statements** used instead of CQL string concatenation and manual escaping?
- [ ] Is `CAST` used only for pairs in the **supported matrix**, never abused as a text parser?
- [ ] Are narrowing conversions guarded with `...Exact()` or range checks to prevent silent truncation?
- [ ] Does money use `BigDecimal` or minor-unit `bigint`, **never** float/double?
- [ ] Are decimal scale/rounding rules defined, and `BigDecimal.equals` vs. `compareTo` accounted for?
- [ ] Are `NaN`, infinity, `-0.0`, and float/double tolerances checked per workload?
- [ ] Are **ms `timestamp`**, **µs write timestamps**, **second TTLs**, **ns `time`**, and **calendar `duration`** clearly separated?
- [ ] Do all ISO timestamp strings specify time zones/offsets, with consistent day bucketing?
- [ ] Do Unicode keys enforce **NFC/NFD, case folding, and UTF-8 byte limits** instead of `String.length()`?
- [ ] Are ASCII values validated against range, with accented Vietnamese stored as `text`?
- [ ] Do `uuid`/`timeuuid` match required versions, with stable IDs across retries?
- [ ] Are IPs validated as literals (without accidental DNS lookups), and blobs bound cleanly via `ByteBuffer` slices?
- [ ] Do collections/UDTs/tuples/vectors use matching codecs, frozen semantics, and supported cluster versions?
- [ ] Are NULL, UNSET, missing fields, and `false`/`0`/`""` clearly separated in the API and driver?
- [ ] Are primary keys valid, non-NULL/non-UNSET, and aligned with partition/clustering access paths?
- [ ] Do round-trip tests cover min/max, overflow, Unicode, DST, wrong dimensions, codecs, and timeouts?
- [ ] When changing key types or schemas, is there a full migration plan (new table, backfill/dual-write/cutover/rollback)?
- [ ] Are tombstones, compaction, repair, consistency, and codec errors monitored without leaking sensitive data?

## References

- [Apache Cassandra — CQL Data Types and Literal Syntax](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/types.html).
- [Apache Cassandra — CQL Functions: CAST, datetime, blob conversion](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/functions.html).
- [Apache Cassandra — CQL Data Manipulation: SELECT/INSERT/UPDATE/DELETE](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html).
- [Apache Cassandra — JSON Support and DEFAULT UNSET](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/json.html).
- [Apache Cassandra Java Driver 4.x — Data Types / Type Mapping](https://apache.github.io/cassandra-java-driver/4.19.0/core/).
- [Apache Cassandra Java Driver 4.x — Built-in TypeCodecs](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/type/codec/TypeCodecs.html).

**Remember:** CQL **literals** express values, **`CAST`** converts only among select supported types, and **Java Driver codecs** encode and decode against the schema. Nothing replaces **application-level parsing and validation**. In distributed Cassandra, values with the wrong unit, unnormalized Unicode, wrong timestamp bucket, or regenerated retry IDs will still replicate consistently while remaining **business-incorrect**. Choose the right types, validate boundaries, bind matching Java types, and design partition/clustering keys around real queries.
