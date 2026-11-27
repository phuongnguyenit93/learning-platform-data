# Reconciling Encoding, Numeric Types, UUIDs, Timestamps, and Timezones During Import

## Objective and context

In a **data migration into Apache Cassandra**, an `INSERT` returning success only proves Cassandra accepted a mutation at the requested consistency level. It **does not prove the data was interpreted accurately** from CSV, JSON, source databases, or APIs. For example, monetary amounts can suffer rounding via `double`; UUIDs can lose formatting; timestamps without offsets can be parsed in the ETL host's timezone; or Vietnamese strings with broken encoding can still be stored as valid `text` values.

This lesson belongs to the **Migration and Schema** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It connects the wide-column model, partition keys, query-driven table design, CQL, replication, read/write consistency levels, repair/compaction, troubleshooting, and Java Driver 4.x integration.

After completing it, you will be able to:

1. Build a **data-type contract** prior to import, specifying source encoding, Unicode normalization, target types, and error handling.
2. Distinguish `text`/`varchar` from `ascii`, UTF-8 encoding, Unicode normalization, and CSV/JSON/BOM pitfalls.
3. Choose `int`, `bigint`, `varint`, `decimal`, `float`, and `double` properly without precision loss during type conversion.
4. Validate canonical UUIDs; distinguish `uuid` from `timeuuid` and avoid using UUIDs as timestamps when conditions are unmet.
5. Convert timestamps with **explicit offsets** into instants, store business timezone metadata separately when needed, and avoid confusing `date`/`time` with UTC instants.
6. Implement an ETL flow **parse → validate → normalize → bind → write → reconcile**, separating input errors from write timeouts.
7. Practice CQL and the Java Driver to verify imported values by primary key and an independent manifest.

> **Data safety:** run import examples only in a lab keyspace. In real systems, take and test backups, define rollback/backfill, throttle load on Cassandra, protect PII/secrets, and verify edge-case samples before full-dataset runs. Never edit SSTables directly or ignore parse errors just to "hit row counts."

## 1. Why must migration start with a data contract?

A pipeline crosses multiple representation boundaries:

~~~mermaid
flowchart LR
    S["Source: CSV / JSON / RDBMS"] --> B["Bytes + encoding"]
    B --> P["CSV/JSON parser"]
    P --> V["Schema and value validation"]
    V --> N["Rule-based normalization"]
    N --> T["Typed CQL binding"]
    T --> C["Cassandra replicas"]
    C --> R["Read reconciliation"]
    M["Independent manifest / source log"] -.-> R
    V -. "Invalid" .-> Q["Quarantine with error code"]
    T -. "Timeout / uncertain" .-> U["UNKNOWN_WRITE for verification"]
~~~

Each boundary introduces distinct failure modes:

| Boundary | Error example | Proper detection |
| --- | --- | --- |
| Bytes → characters | Windows-1258 file decoded as UTF-8 | Strict decoder error or character mismatch against source |
| Characters → fields | CSV field contains a comma inside quotes | Compliant CSV parser and column-count validation |
| String → number | `9007199254740993` passes through JavaScript `Number` | Precision lost before reaching Java |
| String → UUID | `timeuuid` receives a version-4 UUID | UUID version check and schema contract |
| String → instant | `2026-11-21 16:30:00` lacks a zone/offset | Cannot determine UTC instant without a source rule |
| Parsed values → Cassandra | Wrong column binding, null PK, CL timeout | Typed prepared statements, validation, and ACK/UNKNOWN tracking |
| Cassandra → readers | Query observes stale version | Read at target CL, reconcile against source, verify repair and timing |

**Rule:** **ambiguous** data must be flagged and sent to a review queue (*quarantine*) rather than guessed. Especially for datetimes and money, "guessing so it parses" creates silent business errors invisible to `COUNT(*)`.

### Sample import contract

| Source field | Source type/format | Target Cassandra type | Mandatory rules |
| --- | --- | --- | --- |
| `event_id` | Canonical UUID | `uuid` | Exact 36-char `8-4-4-4-12` format; never regenerated on retry |
| `display_name` | UTF-8 | `text` | Strict decode; NFC if contract permits |
| `sku_code` | ASCII | `ascii` | U+0000..U+007F only per code policy |
| `quantity` | Integer string | `int` | Validate 32-bit signed range |
| `total_minor` | Minor-unit integer | `bigint` | Validate 64-bit signed range; never route through `double` |
| `amount` | Decimal string | `decimal` | `BigDecimal` with business scale limits |
| `sequence_no` | Large integer | `varint` | `BigInteger` with reasonable size bounds |
| `occurred_at` | ISO-8601 with offset | `timestamp` | Convert to instant; enforce millisecond precision policy |
| `business_date` | `YYYY-MM-DD` | `date` | Local calendar date; never blindly shift to UTC |
| `local_clock` | `HH:mm:ss[.fraction]` | `time` | Time of day; never attach an assumed timezone |
| `source_zone` | IANA name like `Asia/Ho_Chi_Minh` | `text` | Preserve zone ID separately to reconstruct context |

The contract must also specify nullable columns, empty-string behavior, currency units, precision/scale, who originates source timestamps, any **proven** default timezone, primary-key ownership, and re-import conflict policies.

## 2. Encoding: `text`, `varchar`, `ascii`, and Unicode

### 2.1. How does Cassandra store text?

In CQL, `text` and `varchar` represent **UTF-8** strings; `ascii` restricts values to ASCII. All three are string types, yet they are **not interchangeable** when inputs include Vietnamese diacritics, emojis, or non-ASCII characters.

| Value | CQL `text`/`varchar` | CQL `ascii` |
| --- | --- | --- |
| `HELLO-123` | Valid | Valid |
| `Cà phê sữa` | Valid when decoded properly | Unsuitable; contains non-ASCII characters |
| `Đơn hàng số 1` | Valid | Unsuitable |
| `📦` | Valid with proper UTF-8 | Unsuitable |

Never pick `ascii` merely because data is "usually English." Product codes may be restricted to ASCII, while customer names, addresses, notes, and free text typically require `text`.

### 2.2. Common bugs before data even reaches Cassandra

- **Wrong source charset:** a file written in a Windows code page is decoded as UTF-8. If the decoder replaces bad bytes with replacement characters, Cassandra happily stores the corrupted string.
- **UTF-8 BOM:** leading bytes `EF BB BF` may get prepended to the first column header if the parser does not strip them.
- **CSV quoting:** `"Cà phê, rang xay"` contains an embedded comma and must not be split with `split(",")`.
- **Embedded newlines:** CSV permits newlines inside quotes; naive line-by-line reading splits one record into two.
- **Unicode normalization:** visually identical strings can have different code-point sequences (precomposed NFC vs. decomposed NFD), causing byte/key mismatches.
- **Unplanned trimming/case-folding:** blindly stripping whitespace or lowercasing identifiers can collapse two distinct source keys into one.

Valid CSV record with an embedded comma in `display_name`:

~~~csv
event_id,display_name,sku_code,amount,occurred_at
11111111-1111-4111-8111-111111111111,"Cà phê, rang xay",SKU-001,123.4500,2026-11-21T16:30:00.123+07:00
~~~

**Never import CSVs using `line.split(",")`.** Use a compliant CSV parser handling quotes/escapes/newlines, enforce the source contract charset, and **decode in strict error-reporting mode** on invalid byte sequences.

### 2.3. Should you apply Unicode NFC normalization?

NFC normalizes canonically equivalent Unicode sequences, aiding key lookups and text matching across diverse sources. However, it must be a **contract-level decision**:

- For `display_name`, NFC normalization usually makes sense for consistent text representation.
- For **external IDs, digital signatures, tokens, byte payloads**, or externally issued keys, changing encoding/normalization can break identifiers or checksums.
- Store the **raw-byte hash** separately and record the normalization version to keep input provenance auditable.

Java:

~~~java
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;

var decoder = StandardCharsets.UTF_8.newDecoder()
    .onMalformedInput(CodingErrorAction.REPORT)
    .onUnmappableCharacter(CodingErrorAction.REPORT);

// rawBytes are bytes read directly from a valid source record/file.
String original = decoder.decode(
    java.nio.ByteBuffer.wrap(rawBytes)).toString();
String normalized = Normalizer.normalize(
    original, Normalizer.Form.NFC);
~~~

This snippet illustrates only **strict decoding + normalization**. For huge CSV files, stream-decode and parse quotes properly—never load a multi-GiB file into a single heap string. Convert `CharacterCodingException` into an import error tagged with offset/record ID rather than swallowing it and writing garbage strings.

## 3. Numeric types: precision matters more than "it parsed"

Cassandra provides integer and floating-point types with distinct representations. Choose types from the **true value domain**, not just the first few sample rows.

### 3.1. Integers

| CQL type | Range / semantics | Common Java Driver 4.x type |
| --- | --- | --- |
| `tinyint` | 8-bit signed integer | `byte`/`Byte` |
| `smallint` | 16-bit signed integer | `short`/`Short` |
| `int` | 32-bit signed integer | `int`/`Integer` |
| `bigint` | 64-bit signed integer | `long`/`Long` |
| `varint` | Arbitrary-precision integer, practically bounded by system resources | `java.math.BigInteger` |
| `counter` | Specialized increment/decrement counter | Never import like an ordinary `bigint` column |

Example:

~~~text
int:
    min = -2147483648
    max =  2147483647

bigint:
    min = -9223372036854775808
    max =  9223372036854775807

Value: 9007199254740993
    fits comfortably in bigint,
    but exceeds JavaScript Number's safe integer limit 2^53 - 1;
    if routed through Number, it rounds silently.
~~~

A classic bug is exporting huge integers from Excel or JavaScript into JSON as `number`, then importing into `bigint`. Once Cassandra receives `9007199254740992` instead of `9007199254740993`, the driver cannot recover lost digits. **Keep large integers as strings or exact integer types end to end.**

Never use `counter` for imported sequential IDs or monetary totals: counters obey special increment rules, are not absolute assignments, and non-idempotent retries risk double-counting. Store aggregates as `bigint`/`varint` or recompute them via controlled pipelines depending on requirements.

### 3.2. Decimals and binary floating-point numbers

| CQL type | Property | When to use |
| --- | --- | --- |
| `decimal` | Exact decimal via unscaled integer + scale | Money, rates requiring exact decimal representation |
| `float` | 32-bit binary floating point | Telemetry/measurements tolerating rounding error |
| `double` | 64-bit binary floating point | Measurements, bounded-error approximations |

For instance, `0.1` has no exact finite binary representation in `float`/`double`. Never compute `amount` in `double` and convert to `decimal` expecting all digits to match the source.

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;

BigDecimal exactAmount = new BigDecimal("123.4500");
BigInteger exactSequence =
    new BigInteger("123456789012345678901234567890");
long exactMinor = Long.parseLong("9007199254740993");

// Avoid when the source requires exact decimal values:
// new BigDecimal(0.1)  // carries double representation error
~~~

**Scale is part of the contract.** `123.45` and `123.4500` have equal numerical value yet differ in `BigDecimal` scale. `BigDecimal.equals()` compares scale too, while `compareTo()` compares numerical value. During reconciliation, decide explicitly whether to compare **numerical value** or **original scale/formatting**.

For example, a business rule for `amount` might enforce at most 4 decimal places, max precision 18 digits, and non-negative values. That is an **application policy**, not a universal limit of Cassandra's `decimal` type.

### 3.3. Distinguishing decimal points from grouping separators

`1,234` can mean **one thousand two hundred thirty-four** or **one point two three four**, depending on locale. In exchange formats, mandate a single machine-readable convention, such as:

~~~text
quantity:    "1234"
total_minor: "123400"
amount:      "1234.00"
ratio:       "0.125"
~~~

Never implicitly rely on OS-locale `NumberFormat`. Never blindly replace all commas with dots, which corrupts `1,234.56`. Reject or quarantine any value violating the published format so it is fixed at the source.

## 4. UUIDs: identification and time ordering are distinct concerns

### 4.1. The `uuid` type

Cassandra `uuid` stores UUID identifiers. Common canonical text representation:

~~~text
11111111-1111-4111-8111-111111111111
xxxxxxxx-xxxx-Mxxx-Nxxx-xxxxxxxxxxxx
~~~

In this diagram, `M` indicates the UUID version and `N` encodes variant bits. `uuid` does not mean "must be UUID version 4"; applications may use whichever UUID version fits their data contract.

When importing:

1. Validate the `8-4-4-4-12` canonical form if guaranteed by the source.
2. Parse via `UUID.fromString(...)` and verify version/variant rules if required by business policy.
3. Keep IDs **stable across retries**: never call `UUID.randomUUID()` again for the same source record.
4. Do not treat all-zeros as `null` if the source genuinely emits nil UUIDs; separate missing-value rules explicitly.
5. Do not compare text case arbitrarily; once parsed, compare typed `UUID` objects and canonical serialization.

**Why keep IDs stable?** If ETL retries an event while generating a fresh UUID, Cassandra sees **two distinct primary keys**. Even raising CL to `LOCAL_QUORUM` will not merge them.

### 4.2. The `timeuuid` type

Cassandra's `timeuuid` specifically represents **version-1 time-based UUIDs**. It works well in certain time-ordered table designs, yet:

- **UUIDv4** cannot substitute directly for `timeuuid`.
- Other UUID versions, such as UUIDv7, **are not automatically `timeuuid`** in Cassandra's sense.
- `timeuuid` does not encode full business timezones; extract time using appropriate version/format helpers.
- Concurrent events at identical or close timestamps still need explicit disambiguation/ordering rules; never treat `timeuuid` alone as a global total order across distributed writers.

Example table when the source genuinely provides valid timeuuids:

~~~sql
CREATE TABLE IF NOT EXISTS migration_lab.events_by_time (
    run_id text,
    event_time_id timeuuid,
    marker text,
    PRIMARY KEY ((run_id), event_time_id)
) WITH CLUSTERING ORDER BY (event_time_id DESC);
~~~

Cassandra provides CQL functions for `timeuuid` such as `now()`, `toTimestamp(...)`, and time-bound range helpers in supported versions. **Never generate a UUIDv1 at import time and treat it as proof of "when the event occurred"**: that only reflects ETL processing time.

## 5. Timestamp, date, and time: three distinct semantics

### 5.1. `timestamp` is an instant; it does not preserve the original timezone

In Cassandra, `timestamp` is stored as milliseconds since the UTC Unix epoch. Strings with **different offsets referring to the same instant** represent the same point in time:

~~~text
2026-11-21T16:30:00.123+07:00
2026-11-21T09:30:00.123Z

Both represent the exact same instant.
When stored in CQL timestamp, the "+07:00" offset
is not retained as an original timezone inside the column itself.
~~~

In `cqlsh`, display timezone and formatting depend on client/session settings. Reading back `09:30Z` instead of `16:30+07:00` **does not mean seven hours were lost**, provided both represent the same instant.

**Precision:** CQL `timestamp` has **millisecond** resolution. If the source contains microseconds or nanoseconds, decide upfront per policy whether to **reject**, **round**, or **truncate**. Never let a driver/serializer silently drop sub-millisecond digits while reporting a 100% match.

### 5.2. `date` is not midnight UTC

CQL `date` represents a **calendar date** with no timezone or time-of-day attached. For example, `2026-11-21` may be a store's business date in Vietnam—it is **not** the timestamp `2026-11-21T00:00:00Z`.

If the business date is computed in `Asia/Ho_Chi_Minh`:

~~~text
UTC instant:      2026-11-20T18:30:00Z
at +07:00:        2026-11-21T01:30:00+07:00
business_date:    2026-11-21
~~~

Computing `instant.atZone(zone).toLocalDate()` can yield a different date than UTC. If `business_date` is an **authoritative value published by the source** (such as an accounting day with a 05:00 cutoff), never recompute it via pure timezone conversion; preserve that cutoff rule.

### 5.3. `time` carries no date or timezone

CQL `time` is **time of day** at nanosecond precision, typically mapped to `java.time.LocalTime` in the Java Driver. A value like `16:30:00.123000000` **cannot define an instant** without a date and timezone/offset.

Therefore:

| Column | Can store | Cannot store |
| --- | --- | --- |
| `timestamp` | An instant at millisecond resolution | Original IANA zone ID, local calendar context |
| `date` | Calendar date | UTC instant, offset, clock time |
| `time` | Time of day | Date, offset, timezone |
| `source_zone text` | E.g., `Asia/Ho_Chi_Minh` | No instant by itself |

If the business must display "16:30 Hanoi time" and handle historical DST regions, store the **instant** plus **zone ID** and required business attributes—not just a bare timestamp column.

## 6. Offsets are not the same as IANA timezones

An **offset** is the shift from UTC at a specific instant, such as `+07:00`. An **IANA timezone**, such as `Asia/Ho_Chi_Minh`, encodes historical rules and seasonal/yearly offset transitions.

| Input | Can determine instant? | Key caution |
| --- | --- | --- |
| `2026-11-21T16:30:00+07:00` | Yes | Explicit offset; parse as `OffsetDateTime` then `Instant` |
| `2026-11-21T09:30:00Z` | Yes | `Z` means UTC |
| `2026-11-21 16:30:00` | **Uncertain** | Missing offset/zone; requires a verified source rule |
| `2026-11-21 16:30:00 + Asia/Ho_Chi_Minh` | Yes, with valid zone rules | Parse local datetime and `ZoneId` properly |
| `2026-11-01 01:30:00 + DST zone` | Potentially **ambiguous** | Some wall-clock times repeat; needs offset or disambiguation rule |

During daylight saving transitions, **non-existent** or **ambiguous (repeated)** local times occur. `LocalDateTime.atZone(...)` silently applies library defaults; never rely on it silently in financial or audit migrations. When the source provides both offset and zone, verify that **the offset is valid for that zone at that instant**.

### Java validation snippet

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

OffsetDateTime input =
    OffsetDateTime.parse("2026-11-21T16:30:00.123+07:00");
Instant instant = input.toInstant();
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime atBusinessZone = instant.atZone(businessZone);

if (!input.getOffset().equals(atBusinessZone.getOffset())) {
    throw new IllegalArgumentException(
        "Offset does not match declared timezone");
}
~~~

When inputs contain local times without zones or offsets, require upstream metadata or an **approved conversion rule**. Defaulting to the ETL host's system timezone produces inconsistent results across containers, laptops, and servers.

## 7. Nulls, empty strings, missing fields, and internal write timestamps

### 7.1. One "blank cell" can mean several different things

| Source case | Possible meaning | Handling |
| --- | --- | --- |
| Field omitted in JSON | Not provided | Distinguish from `null`; decide update vs. insert semantics |
| `null` in JSON | Absent value | Write null only if contract permits |
| `""` | Genuine empty string | Do not silently convert to null |
| `"NULL"` in CSV | Could be literal text `NULL` or a sentinel | Define escaping and CSV null-marker rules |
| Numeric column containing `""` | Missing/malformed | Reject or apply explicit missing-value policy |
| Nil UUID `00000000-0000-0000-0000-000000000000` | A valid parseable UUID | Never treat as null unless specified |

In Cassandra, **primary-key components cannot be null**. For non-key columns, writing `null` can generate a **tombstone**, whereas the driver supports **UNSET** to leave a column untouched where applicable. Never conflate `NULL` and `UNSET`. Avoid turning thousands of missing values into thousands of accidental tombstones.

### 7.2. `writetime` differs from `occurred_at`

The business column `occurred_at timestamp` records **when the event happened**. Cassandra also maintains an **internal write timestamp** (microsecond precision) for cell reconciliation:

~~~sql
SELECT event_id, occurred_at, WRITETIME(amount)
FROM migration_lab.import_events_by_run
WHERE run_id = 'migration-demo-01'
  AND event_id = 11111111-1111-4111-8111-111111111111;
~~~

`WRITETIME(amount)` returns the write timestamp of cell `amount`; it **does not automatically equal** `occurred_at` nor guarantee when the client received an ACK. Importing an old event today with a server-generated write timestamp naturally leaves those two times different.

For replay/dual-write/idempotency, design a **stable write-timestamp policy**, key ownership, and conflict rules. CQL `USING TIMESTAMP` takes **microseconds**; never pass milliseconds into it by mistake.

## 8. Designing a lab schema for an import run

Assume inputs contain UUIDs, Vietnamese UTF-8 text, ASCII codes, 32/64-bit integers, large integers, decimals, offset timestamps, and business dates/times. The lab table partitions by **run ID** to reconcile a small test batch:

~~~sql
CREATE KEYSPACE IF NOT EXISTS migration_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS migration_lab.import_events_by_run (
    run_id text,
    event_id uuid,
    source_id text,
    customer_id uuid,
    display_name text,
    sku_code ascii,
    quantity int,
    total_minor bigint,
    amount decimal,
    sequence_no varint,
    metric double,
    occurred_at timestamp,
    business_date date,
    local_clock time,
    source_zone text,
    raw_sha256 text,
    PRIMARY KEY ((run_id), event_id)
);
~~~

**Notes:**

- `(run_id)` is the partition key and `event_id` is the clustering key. Use a fresh `run_id` per exercise.
- This schema is for **small lab batches**, not a recommendation to stuff tens of millions of production events into a single `run_id` partition. Production schemas must bucket by tenant/time/shard and real queries.
- `source_id` preserves the source system identifier; when merging multiple sources, include `source_system`/namespace in the contract to avoid collisions.
- `raw_sha256` can hold a hash of **source record bytes** or a defined canonical form; document the choice clearly. Hashing does not replace encryption/access control and can leak low-entropy inputs.
- `IF NOT EXISTS` does not modify an existing keyspace or table. Before assuming `LOCAL_QUORUM`, verify the real RF and datacenter name.

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'migration_lab';

SELECT data_center, release_version, host_id
FROM system.local;
~~~

`system.local` describes only **the node answering CQL**; to inspect multi-node topology, also run `nodetool status` from an admin context. On a single-node lab, adjust RF/CL accordingly instead of assuming three replicas exist.

## 9. CQL practice: importing a multi-type record

### 9.1. Expected source record

~~~text
run_id:          migration-demo-01
event_id:        11111111-1111-4111-8111-111111111111
source_id:       invoice-0001
customer_id:     22222222-2222-4222-8222-222222222222
display_name:    Cà phê rang
sku_code:        SKU-001
quantity:        2
total_minor:     9007199254740993
amount:          123.4500
sequence_no:     123456789012345678901234567890
metric:          0.125
occurred_at:     2026-11-21T16:30:00.123+07:00
business_date:   2026-11-21
local_clock:     16:30:00.123000000
source_zone:     Asia/Ho_Chi_Minh
~~~

In `cqlsh`, set consistency matching the lab cluster. In one DC with RF=3 and healthy nodes, for example:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO migration_lab.import_events_by_run (
    run_id, event_id, source_id, customer_id, display_name,
    sku_code, quantity, total_minor, amount, sequence_no,
    metric, occurred_at, business_date, local_clock, source_zone
) VALUES (
    'migration-demo-01',
    11111111-1111-4111-8111-111111111111,
    'invoice-0001',
    22222222-2222-4222-8222-222222222222,
    'Cà phê rang',
    'SKU-001',
    2,
    9007199254740993,
    123.4500,
    123456789012345678901234567890,
    0.125,
    '2026-11-21T16:30:00.123+0700',
    '2026-11-21',
    '16:30:00.123000000',
    'Asia/Ho_Chi_Minh'
);
~~~

`CONSISTENCY` is a **`cqlsh`** command, not CQL syntax for the Java Driver. This `INSERT` omits `raw_sha256` because hashes must be computed from real source bytes, never filled with fake placeholders.

### 9.2. Reading back for reconciliation

~~~sql
SELECT event_id, source_id, customer_id, display_name,
       sku_code, quantity, total_minor, amount, sequence_no,
       metric, occurred_at, business_date, local_clock, source_zone
FROM migration_lab.import_events_by_run
WHERE run_id = 'migration-demo-01'
  AND event_id = 11111111-1111-4111-8111-111111111111;
~~~

Do not reconcile timestamps by **display string** when clients use different timezones: compare `Instant` or epoch milliseconds. For `amount`, compare per contract: `compareTo()` for numerical equality or scale/canonical string if representation must match. For text, compare under the agreed Unicode normalization—**never blindly lowercase personal names**.

Row counts within a tiny lab partition can be helpful, yet **never run production-wide `COUNT(*)`** to prove import completeness. Two sets of records with different IDs can still have identical counts.

### 9.3. Deliberate invalid cases—without writing garbage

| Invalid source data | Detection stage | Handling |
| --- | --- | --- |
| `display_name` has truncated multi-byte UTF-8 | Decoder | `ENCODING_ERROR`, quarantine |
| `sku_code = "ĐƠN-01"` on `ascii` column | ASCII validation | `TYPE_ERROR`; do not strip accents |
| `quantity = 2147483648` | `int` parse/range check | `OUT_OF_RANGE` |
| `total_minor = 9223372036854775808` | `bigint` parse/range check | `OUT_OF_RANGE` or planned schema upgrade |
| `amount = "1,234.56"` without locale rule | Decimal parser | `FORMAT_AMBIGUOUS` |
| `event_id = "not-an-uuid"` | UUID parser | `INVALID_UUID` |
| `occurred_at = "2026-11-21 16:30:00"` | Timestamp parser | `MISSING_OFFSET_OR_ZONE` |
| `2026-11-21T16:30:00.123456+07:00` | Precision policy | Reject or round/truncate **per contract** |
| Invalid `source_zone` | `ZoneId`/zone rules | `INVALID_TIMEZONE` |

**Never confuse input errors with replication errors:** malformed records must be stopped before hitting Cassandra. Valid records hitting a `WriteTimeout` enter **UNKNOWN_WRITE** and must be reconciled by stable key before retrying.

## 10. Java Driver 4.x: strongly typed parsing and binding

The example below targets **Cassandra Java Driver 4.x** and Java 17. The goal is avoiding passing everything as strings for CQL to guess, avoiding `double` for money, and avoiding dependence on the JVM's default timezone.

### 10.1. Source validation and parsing function

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.UUID;
import java.util.regex.Pattern;

public final class ImportTypes {
    private static final Pattern UUID_CANONICAL = Pattern.compile(
        "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" +
        "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}");
    private static final Pattern AMOUNT_FORMAT = Pattern.compile(
        "-?[0-9]+(\\.[0-9]{1,4})?");

    public record Raw(
        String eventId, String sourceId, String customerId,
        String displayName, String skuCode, String quantity,
        String totalMinor, String amount, String sequenceNo,
        String metric, String occurredAt, String businessDate,
        String zoneId) {}

    public record Parsed(
        UUID eventId, String sourceId, UUID customerId,
        String displayName, String skuCode, int quantity,
        long totalMinor, BigDecimal amount, BigInteger sequenceNo,
        double metric, Instant occurredAt, LocalDate businessDate,
        LocalTime localClock, String sourceZone) {}

    private static UUID parseUuid(String text) {
        if (text == null || !UUID_CANONICAL.matcher(text).matches()) {
            throw new IllegalArgumentException("Non-canonical UUID");
        }
        return UUID.fromString(text);
    }

    public static Parsed parse(Raw raw) {
        UUID eventId = parseUuid(raw.eventId());
        UUID customerId = parseUuid(raw.customerId());

        // Never alter external keys, but allow NFC on display fields.
        String display = Normalizer.normalize(
            raw.displayName(), Normalizer.Form.NFC);
        if (!StandardCharsets.US_ASCII.newEncoder()
                .canEncode(raw.skuCode())) {
            throw new IllegalArgumentException("skuCode is not ASCII");
        }

        int quantity = Integer.parseInt(raw.quantity());
        if (quantity < 0) {
            throw new IllegalArgumentException("negative quantity");
        }
        long minor = Long.parseLong(raw.totalMinor());
        BigInteger sequence = new BigInteger(raw.sequenceNo());

        if (raw.amount() == null ||
                !AMOUNT_FORMAT.matcher(raw.amount()).matches()) {
            throw new IllegalArgumentException("invalid amount format");
        }
        BigDecimal amount = new BigDecimal(raw.amount());
        if (amount.precision() > 18 || amount.signum() < 0) {
            throw new IllegalArgumentException("amount violates contract");
        }

        double metric = Double.parseDouble(raw.metric());
        if (!Double.isFinite(metric)) {
            throw new IllegalArgumentException("non-finite metric");
        }

        OffsetDateTime fromSource =
            OffsetDateTime.parse(raw.occurredAt());
        Instant instant = fromSource.toInstant();
        if (instant.getNano() % 1_000_000 != 0) {
            throw new IllegalArgumentException(
                "timestamp has sub-millisecond precision");
        }

        ZoneId zone = ZoneId.of(raw.zoneId());
        ZonedDateTime local = instant.atZone(zone);
        if (!local.getOffset().equals(fromSource.getOffset())) {
            throw new IllegalArgumentException(
                "offset does not match source timezone");
        }

        LocalDate businessDate = LocalDate.parse(raw.businessDate());
        // Contract example: business_date equals calendar date in zone.
        // Replace this check if a custom business cutoff applies.
        if (!businessDate.equals(local.toLocalDate())) {
            throw new IllegalArgumentException(
                "businessDate differs from calendar date in source_zone");
        }

        return new Parsed(
            eventId, raw.sourceId(), customerId,
            display, raw.skuCode(), quantity,
            minor, amount, sequence, metric, instant,
            businessDate, local.toLocalTime(), zone.getId());
    }
}
~~~

**Explicit limitations of this example:**

- Data is assumed to have already been **decoded from bytes using strict UTF-8** and parsed cleanly from CSV/JSON before constructing `Raw`. This class does not verify file-level encoding.
- `Integer.parseInt`/`Long.parseLong` throw on overflow rather than truncating to 32/64 bits.
- `AMOUNT_FORMAT` forbids grouping separators, scientific `e` notation, and >4 decimal places per the **sample contract**, not a limit of Cassandra `decimal`.
- `source_zone` and offset are cross-checked to catch mismatched zone IDs. A `business_date` governed by an accounting cutoff rather than calendar midnight needs custom validation.
- `LocalTime` holds local wall-clock time in the zone while `Instant` holds the canonical instant; never interchange them.
- Nullable columns, string-length limits, and `BigInteger` size bounds should be added before production to prevent oversized payloads.

### 10.2. Binding CQL with exact Java types

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class TypedImporter {
    private final CqlSession session;
    private final PreparedStatement insert;

    public TypedImporter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO migration_lab.import_events_by_run (" +
            "run_id, event_id, source_id, customer_id, display_name, " +
            "sku_code, quantity, total_minor, amount, sequence_no, " +
            "metric, occurred_at, business_date, local_clock, " +
            "source_zone, raw_sha256) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)");
    }

    public void write(String runId, ImportTypes.Parsed row,
                      String originalSha256) {
        BoundStatement statement = insert.bind(
                runId, row.eventId(), row.sourceId(), row.customerId(),
                row.displayName(), row.skuCode(), row.quantity(),
                row.totalMinor(), row.amount(), row.sequenceNo(),
                row.metric(), row.occurredAt(), row.businessDate(),
                row.localClock(), row.sourceZone(), originalSha256)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            // Do not mark idempotent without a fixed timestamp policy
            // and clear writer ownership.
            .setIdempotence(false);
        session.execute(statement);
    }
}
~~~

Reuse `CqlSession` and `PreparedStatement`. `bind(...)` supplies **strongly typed** values (`UUID`, `int`, `long`, `BigDecimal`, `BigInteger`, `Instant`, `LocalDate`, `LocalTime`) without concatenating literals or manually quoting strings.

On a write timeout, `write` may throw an exception even after some replicas persisted the mutation. The pipeline should track states:

~~~text
PARSE_FAILED    -> never sent to Cassandra; quarantined with error code
VALIDATED       -> passed parse/range/timezone checks; awaiting ACK
ACKNOWLEDGED    -> executed successfully at configured CL
UNKNOWN_WRITE   -> timeout/error after dispatch; replica persistence uncertain
READ_MISSING    -> read succeeded, row absent at key/CL
READ_MATCH      -> read succeeded, row matches manifest
READ_MISMATCH   -> read succeeded, at least one field diverges
READ_ERROR      -> read incomplete; never count as missing data
~~~

**Never blindly retry a mutation lacking an idempotency contract.** Safe re-import requires an immutable primary key, identical normalized values, stable timestamp/TTL policy, no competing writers, and verification of `UNKNOWN` outcomes. Enable `setIdempotence(true)` only after proving those invariants; it does not turn writes into exactly-once transactions.

## 11. Write timestamps and controlled replay

A dangerous migration bug is retrying the same primary key with seemingly identical values but a **newer write timestamp** while another writer already updated the row. Because Cassandra reconciles using timestamps/tombstones, unconditional re-imports can overwrite valid live data.

For a single-pass import with clear ownership, consider a **deterministic mutation timestamp** recorded in the manifest and reused across every retry of that mutation:

~~~sql
-- Illustrative syntax only for an insert in the lab:
INSERT INTO migration_lab.import_events_by_run
    (run_id, event_id, source_id)
VALUES (
    'migration-demo-02',
    33333333-3333-4333-8333-333333333333,
    'invoice-0002'
) USING TIMESTAMP 1795250000000000;
~~~

The number after `USING TIMESTAMP` is **microseconds since epoch** for the internal write timestamp—**not** a millisecond-precision CQL `timestamp` literal. The value above is illustrative, not a real clock source. Omitting remaining columns makes this only a single-column mutation, not a complete row import.

**Caution:** choosing arbitrary write timestamps or stamping events with years-old occurred times can cause new mutations to **lose** to existing data or tombstones with higher timestamps. Define explicit conflict policies and consider TTLs, tombstones, bulk loads, and bidirectional migrations. Never use `USING TIMESTAMP` to "make Cassandra store an event's timezone"; those two concepts are unrelated.

If your source design includes immutable operation IDs and an outbox/event log, use them to:

1. Identify the same event across multiple runs.
2. Persist mapping/schema versions and normalized values.
3. Reconcile outcomes before retrying when clients report `UNKNOWN`.
4. Detect two distinct source payloads claiming the same primary key.
5. Fence unauthorized writers from mutating partitions mid-backfill.

## 12. Post-import reconciliation: right types, right values, right data

A trustworthy migration verifies **expected keys from an independent source**, never building the expected set from a `SELECT` on the target Cassandra table itself.

### 12.1. What should the manifest contain?

| Manifest field | Meaning |
| --- | --- |
| `import_run_id` and `source_system` | Identifies scope and namespace boundaries |
| `source_record_id`, `event_id` | Stable keys enabling idempotent readback |
| `source_bytes_sha256` | Hash of raw source bytes to verify input files |
| `normalized_payload_sha256` | Hash of explicitly defined canonical representation |
| `encoding`, `normalization_version` | Records decoding and normalization logic |
| `numeric_contract_version` | Scale, units, range, rounding policy |
| `timestamp_contract_version` | Timezone/offset, DST, and precision policy |
| `write_outcome`, `ack_time`, `CL` | Distinguishes ACK from UNKNOWN or rejected |
| `target_key`, `read_result` | Key-based and CL-aware verification in Cassandra |
| `error_category` | Drives quarantine, retry, or investigation |

### 12.2. Per-type comparison

- **Text:** compare Unicode code points after agreed normalization; archive source byte hashes for audits.
- **ASCII:** compare exact values and code rules; never compare auto-transliterated outputs.
- **Integer:** compare `BigInteger` or exact integer types; never route through `double` for reporting.
- **Decimal:** compare `BigDecimal` numerical value and/or scale per contract.
- **UUID:** compare typed `UUID` objects after canonical parsing; check version for `timeuuid`.
- **Timestamp:** compare `Instant` or epoch milliseconds; record precision policy if source has micros/nanos.
- **Date/time/zone:** compare `LocalDate`, `LocalTime`, and `ZoneId` separately; never infer zone from a CQL timestamp.
- **Null/missing:** distinguish `null`, empty strings, omitted fields, and deleted values.

### 12.3. Reporting counters

~~~text
source_records_seen         = ...
decode_parse_valid          = ...
quarantined_input           = ...
target_writes_acked         = ...
target_writes_unknown       = ...
target_reads_match          = ...
target_reads_missing        = ...
target_reads_mismatch       = ...
target_reads_error          = ...
duplicate_source_ids        = ...
conflicting_same_target_pk  = ...
~~~

**Never lump `READ_ERROR` into `MISSING`.** If `LOCAL_QUORUM` times out, you do not know whether the event exists on replicas. Record node/DC/RF/CL, repair/compaction state, and timestamp, then retry boundedly to reclassify.

## 13. Safe operational pipeline design

### Step 1 — Lock down source definitions

Sample **edge cases**: Vietnamese diacritics and emojis, invalid bytes, CSVs with quotes/newlines, bad UUIDs, min/max-boundary integers, high-precision money, DST transition dates, offset-less timestamps, nulls, and duplicate IDs. Lock contract versions and source→Cassandra mappings.

### Step 2 — Choose a query-driven schema

Never cram tens of millions of production rows into one `run_id` partition purely for import convenience. Production partition keys must serve primary queries and avoid hot partitions, using bounded tenant/time buckets or capped shards. When denormalizing across multiple query tables, handle cross-table drift with idempotency and reconciliation.

### Step 3 — Pilot and prepare rollback

Run a small pilot with edge-case samples and compare CQL/Java results. Ensure tested backups/restores and a rollback or forward-fix plan exist. Never assume `TRUNCATE` or `DROP TABLE` is a safe production rollback.

### Step 4 — Parse and validate before opening load

Read inputs with explicit encoding and compliant parsers, routing invalid records to quarantine with structured metadata:

~~~text
source_file_id
record_offset_or_line
source_record_id (omit PII if logs are unprotected)
error_code
field_name
raw_bytes_hash
contract_version
~~~

Keep raw source bytes in secured storage for investigation—**never** print sensitive raw payloads to stdout or public log aggregators.

### Step 5 — Write via bounded prepared statements

Choose CL matching RF/local DC (`LOCAL_QUORUM` with RF3 requires two local replicas). Enforce concurrency caps, rate limits, backpressure, and metrics. **Never bundle huge multi-partition logged batches to "import faster"**: Cassandra batches are not bulk throughput accelerators and can bottleneck batchlogs.

On write timeouts, record **UNKNOWN_WRITE**. On parse/validation failures, record **QUARANTINED** without sending to Cassandra. Never silently skip failed records and declare "100% migrated."

### Step 6 — Check ACKs and bounded readback

Reconcile by primary key/bucket; avoid full-table `ALLOW FILTERING` scans or `COUNT(*)` as sole proof. For large datasets, use stratified sampling across data types plus full ID reconciliation against an independent source where feasible.

### Step 7 — Cut over and monitor

Switch applications only once schema agreement, RF/CL, reconciliation, and error budgets pass. Test reads/writes through the Java Driver against the right local DC; track p95/p99, retries, timeouts, and replica health. During dual-writes, enforce ownership/fencing and reconciliation so stale mutations never overwrite newer data.

## 14. Real-world failure cases and troubleshooting

| Symptom | Likely cause | Verification action |
| --- | --- | --- |
| `Cà phê` turns into garbled characters | Wrong charset decode, replacement characters | Inspect source bytes, enforce strict UTF-8 and Unicode checks |
| Visually identical IDs miss key lookups | NFC vs. NFD or whitespace differences in text PK | Inspect code points; normalize consistently before keying |
| Accented SKU rejected | `ascii` column forbids non-ASCII | Verify contract; migrate schema via proper process if needed |
| `9007199254740993` becomes `9007199254740992` | Passed through IEEE-754 double / JS `Number` | Fix upstream pipeline; preserve exact integers as strings |
| `0.1 + 0.2` does not equal `0.3` | Used float/double for money | Construct `BigDecimal` from strings; enforce precision/scale |
| `123.4500` vs `123.45` flagged as mismatch | `BigDecimal.equals` checks scale | Choose `compareTo` or canonical scale per contract |
| CQL rejects UUID | Corrupted hyphens or wrong version for `timeuuid` | Validate canonical format and type/version |
| Timestamp shifts 7 hours across clients | Same instant formatted in UTC vs. +07 | Compare epoch milliseconds/`Instant`; store source zone separately |
| Date `2026-11-21` becomes `2026-11-20` | Derived date in UTC instead of local business zone | Check offset and source cutoff rules |
| DST hour shifts unexpectedly | Parsed local time without offset/ambiguity policy | Reject or apply approved disambiguation rules |
| Timestamp loses microseconds | CQL `timestamp` has millisecond resolution | Enforce precision policy: reject or truncate per contract |
| Re-import creates duplicate rows | Retry generated fresh UUID | Use immutable source event ID as key |
| Re-import loses newer updates | Write timestamp/tombstone vs. competing writers | Enforce ownership, replay timestamp policy, and reconciliation |
| `SELECT` times out post-import | CL/replica/network or import/repair load | Record `READ_ERROR`, check nodes/CL, never label `MISSING` |
| Replicas hold differing values | Unconverged writes, tombstones/repair, timestamps | Inspect write outcomes, controlled repair/tracing |

## 15. Practice exercises and self-check questions

**Exercise 1 — UTF-8 and NFC.** Prepare two visually identical Vietnamese strings encoded in NFC vs. NFD; insert into a `text` column and compare code points/bytes. If the string is a partition key, why must normalization be unified before token hashing?

**Exercise 2 — CSV.** A file contains `"Cà phê, rang xay"` and a multiline field. Explain why `split(",")` and naive line-by-line parsing fail. Design error codes for invalid UTF-8 bytes or a leading BOM in the header.

**Exercise 3 — Large integers.** The source emits `9007199254740993`. Convert it via `double` then `long`, and compare with `Long.parseLong` on the raw string. Why can routing through floating point corrupt IDs or money?

**Exercise 4 — Decimal.** Insert `123.4500` into a `decimal` column. Compare `BigDecimal.compareTo` and `BigDecimal.equals` against `123.45`. When business rules require two decimal places, where should scale normalization and rounding occur?

**Exercise 5 — UUID/timeuuid.** Generate a UUIDv4 and try inserting it into a `timeuuid` column in the lab. Why does a `uuid` schema behave differently? When event IDs come from an upstream system, should retries generate a new UUID?

**Exercise 6 — UTC/offset.** Given `2026-11-21T16:30:00.123+07:00` and `2026-11-21T09:30:00.123Z`, prove they are equal as `Instant`s. Does CQL `timestamp` retain the string `Asia/Ho_Chi_Minh`?

**Exercise 7 — Date/time and DST.** A record contains only `2026-11-01 01:30:00` and a DST timezone. Why can two distinct instants exist? State the minimum metadata needed to convert safely.

**Exercise 8 — Null/UNSET.** One JSON record omits `display_name`, another has `"display_name": null`, and a third has `""`. Explain why these three must not blindly become identical Cassandra mutations.

**Exercise 9 — CQL and Java.** Create `migration_lab.import_events_by_run`, write sample records via CQL and the Java Driver, and read back `UUID`, `BigDecimal`, `BigInteger`, `Instant`, `LocalDate`, and `LocalTime`. Also compare `WRITETIME(amount)` against `occurred_at`; why do they differ?

**Exercise 10 — Quarantine/timeout.** A file has 1,000 records: 20 parse errors, 970 write ACKs, and 10 write timeouts. Can you report 980 records imported successfully? Classify `QUARANTINED`, `ACKNOWLEDGED`, and `UNKNOWN_WRITE` before verifying the 10 keys.

**Exercise 11 — Schema change.** Previously `total_minor` was `int`, and new inputs exceed 2.1 billion. Why should you not coerce or silently overwrite? Propose a new table with `bigint`, backfill, dual-read/cutover, and ID-level reconciliation.

**Exercise 12 — Cross-region reads.** Import into `dc_a` with `LOCAL_QUORUM` in an RF3+3 cluster, then immediately read from `dc_b`. Why might remote reads miss some ACKed events? Design pre-failover reconciliation without equating read timeouts with missing data.

## Key takeaways

**A successful Cassandra migration is not merely `INSERT` returning success—it is semantically accurate data after every transformation.** Lock down charsets and Unicode normalization before loading; preserve integers and money with exact types; keep UUIDs stable; separate `timestamp` instants from `date`, `time`, and IANA timezones; and always require explicit offsets or verified conversion rules. Write CQL via strongly typed prepared statements, quarantine bad inputs, track `UNKNOWN_WRITE`, and **reconcile against independent primary keys/markers** before cutover. That foundation underpins reliable query-driven table design, replication, repair, and recovery.
