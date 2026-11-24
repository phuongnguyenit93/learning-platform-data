# Testing Round-Trip Conversions to Detect Data Loss

> **Context:** Spring Framework → Data Access → Special Data Types. This lesson teaches **round-trip** testing when persisting Java values through Spring JDBC into a database and reading them back, to catch silent rounding, truncation, timezone shifts, representation changes, wrong types, or data loss that may occur without raising any exception.

## 1. What Is a Round-Trip Conversion?

A write/read flow typically passes through several stages:

```text
Initial Java domain value
        |
        v
Parameter preparation / converter / PreparedStatement
        |
        v
JDBC driver -> SQL type -> DB column and storage rules
        |
        v
Committed data in the database
        |
        v
ResultSet / RowMapper / converter
        |
        v
Read-back Java domain value
```

The basic check is:

```text
original = input Java value
persisted = readFromDatabase(writeToDatabase(original))

assert equivalent(original, persisted)
```

The key word is **`equivalent` (equivalent under the business contract)**. `Object.equals(...)` is not always the right comparison:
- `BigDecimal("12.0").equals(BigDecimal("12.00"))` is `false` due to differing `scale`, yet `compareTo(...) == 0` shows they have equal **numeric value**.
- Two `OffsetDateTime` instances with different offsets can still represent **the same instant**. If business logic only cares about the instant, compare `toInstant()`.
- Two JSON payloads with different key orders may be structurally equivalent, whereas differences in numeric types, duplicate keys, array element order, or `null` may matter.
- Two `byte[]` arrays must be compared with `Arrays.equals(...)`, not `byte[].equals(...)` (which compares array reference identity).

**First question:** "What must be preserved?" There are three common levels:

1. **No loss of business value:** e.g., `12.0` and `12.00` are treated as the same monetary amount if scale carries no meaning.
2. **No loss of representation:** besides value, preserve scale, original offset, exact Unicode form, JSON field order, every byte, or metadata.
3. **Controlled transformation:** e.g., allowing rounding to 2 decimal places, UTC normalization, Unicode normalization, or canonical JSON; the policy must be documented, compared against **expected post-normalization results**, and never silently hide dropped information.

Without defining the preservation level, a "passing" test may be overlooking real data loss.

## 2. Three Places Where Data Loss Can Occur

Round-trip tests should isolate three layers to diagnose bugs:

| Location | Example Failure | Verification Measure |
| --- | --- | --- |
| **Before writing:** DTO → domain mapping or JDBC binder | Converting `BigDecimal` to `double`, using `enum.name()` instead of stable codes, formatting dates without nanos | Inspect value right after converter; unit test encode/decode |
| **In the DB:** column/driver coercion, rounding, length limits | `DECIMAL(8,2)` lacks fractional digits; `TIMESTAMP(3)` drops nanos; `CHAR` pads spaces | Inspect DDL, SQL types, read raw value via SQL/JDBC, test on real DB |
| **After reading:** `ResultSet`/`RowMapper`/converter | `getInt()` loses null without `wasNull()`, parsing JSON numbers as `double`, wrong timezone conversion | Compare raw DB value against domain value after mapper |

Spring JDBC helps manage connections, bind parameters, and map results, but **does not guarantee lossless round-tripping for every special value** across all DBs/drivers. Column structures, data types, converters, and comparison logic must be designed and tested by the application.

When a discrepancy appears, capture three samples in the test environment (input, DB representation, output) to pinpoint whether the bug is on write or read. For sensitive data, log only checksums/lengths/redacted info; avoid putting raw values in production logs.

## 3. Storage Contracts for Special Types

Before writing tests, state **Java type → SQL type → preservation expectation**:

| Java Value | Typical SQL Type | Round-Trip Risk | Contract-Appropriate Comparison |
| --- | --- | --- | --- |
| `BigDecimal` | `DECIMAL(p,s)` / `NUMERIC(p,s)` | Scale reduction, rounding, precision overflow | `compareTo == 0` for value; also check `scale` if scale matters |
| `LocalDateTime` | Zone-less `TIMESTAMP(p)` | Lost nanos; ambiguity if treated as absolute instant | `equals` when exact local date/time is expected |
| `Instant`/`OffsetDateTime` | `TIMESTAMP WITH TIME ZONE` or contract-defined epoch | Offset changes, timezone shift, lost fractional seconds | `toInstant().equals(...)` if only instant matters; check offset separately if required |
| `LocalDate` | `DATE` | Date shift if forced through timestamp + timezone | `LocalDate.equals` |
| `UUID` | `UUID`, `BINARY(16)`, or `CHAR(36)` | Wrong byte order, hyphens, case/parsing | Compare `UUID` objects after decoding |
| `byte[]` | `VARBINARY`/`BLOB` | Truncation, wrong encoding, text conversion corrupting bytes | `Arrays.equals`, verify length/hash |
| Unicode `String` | `VARCHAR`/`NVARCHAR`/`TEXT` | Wrong charset, length limits, normalization, trimming | Exact code points or documented NFC/NFD rule |
| JSON | `JSON`/`JSONB`/DB-specific text | Numeric precision loss, keys/arrays, `null`, canonicalization | Compare JSON tree + per-field invariants or byte-for-byte when needed |
| Enum/domain code | `VARCHAR`, `SMALLINT`, DB-specific enum | Renamed constants, changed ordinal, case/default | Round-trip stable business codes, reject unknown values |
| Lists/arrays | SQL `ARRAY`, child table, JSON | Wrong order, null elements, numeric type changes | Compare by index/size/nulls, or as a set if contract is a set |

**Data limits must be explicit:** `DECIMAL(p,s)` holds at most `p` significant digits and `s` fractional digits (details vary by DB); `TIMESTAMP(p)` holds `p` fractional second digits; `VARCHAR(n)` length, char-vs-byte counting, truncation behavior, and `JSON` rules depend on the DBMS.

If an application claims zero nanosecond loss while the column is `TIMESTAMP(3)`, that expectation already contradicts the schema. Round-trip tests expose the mismatch and point toward **widening the column**, **restricting inputs**, or **updating the business contract**.

## 4. Designing Comparisons: Neither False Passes Nor False Failures

Money example:

```java
import java.math.BigDecimal;

BigDecimal before = new BigDecimal("12.0");
BigDecimal after = new BigDecimal("12.00");

System.out.println(before.equals(after));         // false: different scale
System.out.println(before.compareTo(after) == 0); // true: same numeric value
```

If scale is part of the data domain (e.g., expressing rates with distinct precisions), also compare `before.scale() == after.scale()`. If policy only cares about numeric value, use `compareTo == 0`.

**Avoid overly permissive comparators:** using an `epsilon` tolerance for money can let a 0.01 discrepancy slip through—real financial loss. For measurements where tolerance is allowed, define explicit absolute/relative tolerances per unit, handle `NaN`, infinity, and boundary values; never default to `epsilon = 0.001` everywhere.

Time example:

```java
import java.time.OffsetDateTime;

OffsetDateTime a = OffsetDateTime.parse("2026-10-30T09:00:00+07:00");
OffsetDateTime b = OffsetDateTime.parse("2026-10-30T02:00:00Z");

System.out.println(a.equals(b)); // false: different offsets
System.out.println(
    a.toInstant().equals(b.toInstant())
); // true: same instant
```

If the system must display the exact original offset, instant-only comparison is **insufficient**; store offset/zone separately. Conversely, if the contract only needs the absolute instant, comparing offsets with `equals` can cause false failures even though no instant was lost.

For JSON, parse into a tree supporting exact numeric types and compare meaningful fields and elements. Do not simply compare `JSON.stringify`/serialized strings when object key order does not matter; equally, do not automatically sort arrays or drop `null`s unless the contract permits it.

## 5. Runnable Example: Detecting Monetary Rounding and Lost Nanoseconds

Standalone example using **Java 17+, Maven, Spring JDBC 6.2.19, H2 2.3.232**. The program writes a `BigDecimal`, a `LocalDateTime` with nanoseconds, and a byte array. After DB persistence, it reads them back via `JdbcTemplate` and `RowMapper`, then runs round-trip checks on each field.

To observe data loss, the schema intentionally uses:
- `DECIMAL(8,2)`: stores only 2 digits after the decimal point.
- `TIMESTAMP(3)`: stores only milliseconds.
- `VARBINARY(8)`: large enough for a 3-byte array, so no byte loss is expected.

Directory structure:

```text
jdbc-roundtrip-demo/
├── pom.xml
└── src/main/java/demo/RoundTripDemo.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>jdbc-roundtrip-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-jdbc</artifactId>
      <version>6.2.19</version>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <version>2.3.232</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.6.3</version>
      </plugin>
    </plugins>
  </build>
</project>
```

Create `src/main/java/demo/RoundTripDemo.java`:

```java
package demo;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class RoundTripDemo {
    private RoundTripDemo() {
    }

    private record Measurement(
            BigDecimal amount,
            LocalDateTime occurredAt,
            byte[] payload) {
    }

    public static void main(String[] args) {
        var dataSource = new DriverManagerDataSource(
            "jdbc:h2:mem:roundtrip;DB_CLOSE_DELAY=-1", "sa", ""
        );
        var jdbc = new JdbcTemplate(dataSource);

        jdbc.execute(
            "CREATE TABLE measurement (" +
            "id BIGINT PRIMARY KEY, " +
            "amount DECIMAL(8,2) NOT NULL, " +
            "occurred_at TIMESTAMP(3) NOT NULL, " +
            "payload VARBINARY(8) NOT NULL)"
        );

        Measurement before = new Measurement(
            new BigDecimal("12.3456"),
            LocalDateTime.parse("2026-10-30T09:10:11.123456789"),
            new byte[] {0x01, (byte) 0x80, 0x7f}
        );

        int inserted = jdbc.update(
            "INSERT INTO measurement " +
            "(id, amount, occurred_at, payload) VALUES (?, ?, ?, ?)",
            1L, before.amount(), before.occurredAt(), before.payload()
        );

        Measurement after = Objects.requireNonNull(
            jdbc.queryForObject(
                "SELECT amount, occurred_at, payload " +
                "FROM measurement WHERE id = ?",
                (rs, rowNum) -> new Measurement(
                    rs.getBigDecimal("amount"),
                    rs.getObject("occurred_at", LocalDateTime.class),
                    rs.getBytes("payload")
                ),
                1L
            )
        );

        System.out.println("inserted=" + inserted);
        System.out.println(
            "amount=" + before.amount() + " -> " + after.amount()
        );
        System.out.println(
            "amountEqual=" +
            (before.amount().compareTo(after.amount()) == 0)
        );
        System.out.println(
            "time=" + before.occurredAt() + " -> " + after.occurredAt()
        );
        System.out.println(
            "timeEqual=" + before.occurredAt().equals(after.occurredAt())
        );
        System.out.println(
            "bytesEqual=" +
            Arrays.equals(before.payload(), after.payload())
        );
    }
}
```

In the `jdbc-roundtrip-demo` directory, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.RoundTripDemo
```

Lines **printed by the program** when run with the H2 version above (excluding Maven messages):

```text
inserted=1
amount=12.3456 -> 12.35
amountEqual=false
time=2026-10-30T09:10:11.123456789 -> 2026-10-30T09:10:11.123
timeEqual=false
bytesEqual=true
```

Explanation:
1. `JdbcTemplate.update(...)` returns `1` because one row was inserted. **A count of 1 does not prove the contents were stored intact.**
2. H2 rounds `12.3456` to `12.35` when coercing into `DECIMAL(8,2)`. Numeric comparison `compareTo(...) == 0` is `false`: precision was lost.
3. `TIMESTAMP(3)` stores milliseconds: `.123456789` drops to `.123`. `LocalDateTime.equals` is `false`: sub-millisecond info was lost.
4. The three original bytes `01 80 7F` are preserved in `VARBINARY(8)`; `Arrays.equals` is `true`.

The example uses `LocalDateTime` intentionally to isolate **precision**, without mixing timezones into the same test. For absolute instants, run a separate test using `OffsetDateTime`/`Instant` and a compatible DB column/configuration.

**Note:** this example is not proof that all DBs/drivers round like H2. Some DBs round, truncate, or reject data; run integration tests against your real DB and driver version. For `VARBINARY`, some drivers treat `byte[]`/BLOB differently depending on column type and payload size; re-test with your actual column type.

## 6. Catching Issues Early Before Sending SQL

Round-trip tests find loss after writing. To reject unrepresentable values **as soon as input arrives**, validate schema bounds before `INSERT` or `UPDATE`.

For `DECIMAL(8,2)`, if fractional digits must not be lost, use:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

static BigDecimal requireScale2(BigDecimal value) {
    BigDecimal exact = value.setScale(2, RoundingMode.UNNECESSARY);
    if (exact.precision() > 8) {
        throw new IllegalArgumentException("Value exceeds DECIMAL(8,2)");
    }
    return exact;
}
```

`new BigDecimal("12.3456")` causes `setScale(2, UNNECESSARY)` to throw `ArithmeticException` because reducing scale requires rounding. `new BigDecimal("12.3400")` can reduce to `12.34` without **changing numeric value**, even though its scale representation changes. For magnitudes exceeding precision, also check column limits and integer digits; DB constraints remain the final safeguard.

For `TIMESTAMP(3)`, accept only data already exact to milliseconds if nanosecond loss is disallowed:

```java
import java.time.LocalDateTime;

static LocalDateTime requireMillis(LocalDateTime value) {
    if (value.getNano() % 1_000_000 != 0) {
        throw new IllegalArgumentException(
            "Sub-millisecond precision is not representable"
        );
    }
    return value;
}
```

**Never truncate silently and claim "zero data loss".** If business rules deliberately allow dropping detail, state the policy—e.g., "round to milliseconds per DB rules"—persist the normalized value, and test:
- `normalized = normalize(original)` per policy;
- `actual = read(write(original))`;
- assert `equivalent(normalized, actual)`;
- separately verify whether the discarded portion is permissible.

Distinguish *normalizing before write* from *normalizing after read to mask a bug*. If both sides are merely normalized after a bug already occurred, tests can falsely pass.

## 7. Separating Write and Read Steps to Locate Faults

If `roundTrip(original) != original`, you cannot yet conclude whether the fault lies in JDBC binding, SQL types, or `RowMapper`. Diagnostic sequence:

1. Check type, range, precision, and scale of data **before the converter**. Never pass through `double` or temporary `String`s if that loses precision.
2. Inspect the value **after the converter and before binding** (if using `AttributeConverter`, custom mapper, or `ConversionService`).
3. Use `PreparedStatement` to bind the exact SQL type; for special types and `NULL`, explicit `java.sql.Types`/type names may be needed.
4. After commit, read the value via JDBC in the type closest to raw SQL, or use `CAST`/DB functions to inspect how it is stored.
5. Compare against the final `RowMapper` output. If raw SQL is right while domain is wrong, inspect the mapper; if raw SQL is already off, inspect binding, schema, and DB coercion.
6. Run the check over a **separate connection** or new transaction when verifying committed state rather than in-memory Java objects.

Spring lets you specify SQL types instead of letting the driver guess, e.g., with `MapSqlParameterSource`:

```java
import java.math.BigDecimal;
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

var params = new MapSqlParameterSource()
    .addValue("amount", new BigDecimal("12.34"), Types.DECIMAL)
    .addValue("externalId", null, Types.VARCHAR);
```

This is an **integration snippet** for named parameter APIs; `JdbcTemplate` also has overloads taking a SQL type array or `SqlParameterValue`. Specifying the type can fix binding errors (especially `null`), yet **does not replace testing width/precision/schema**. Special types like SQL `UUID`, `JSONB`, `ARRAY`, and `OTHER` require DB/driver-specific mappings; there is no universal `Types.OTHER` rule across all DBMSs.

`RowMapper` should preserve the information required by the domain:
- For nullable integers, use `getObject(..., Integer.class)` or `getInt()` paired with `wasNull()`; calling only `getInt` turns SQL `NULL` into `0`.
- For decimals, use `getBigDecimal`; avoid `getDouble` followed by `new BigDecimal(double)` when exactness is required.
- For bytes, use `getBytes` or handle `Blob` properly, checking length.
- For JDBC 4.2 date/time types, use `getObject(..., LocalDateTime.class)`/`OffsetDateTime.class` if supported by the DB/driver. Test in practice; never assume all SQL timestamps store the same timezone info.

## 8. Mandatory Test Cases for Special Types

### 8.1 Decimals / Money / Rates

- Very small values (`0.0001`), negative signs, `0`, values right at `DECIMAL(p,s)` bounds, numbers with trailing zeros, numbers exceeding precision.
- With `BigDecimal`, construct from decimal strings (`new BigDecimal("0.1")`) when the source is an exact decimal; avoid `new BigDecimal(0.1)` because 0.1 as a `double` is inexact.
- When a value is **intentionally** rounded, test both original input and normalized expected value. Define `RoundingMode`, units, scale, and allowed tolerance clearly.
- Ensure non-negative/negative signs, total limits, and constraints hold; the DB may raise an exception on precision overflow, or coerce if permitted.

### 8.2 Dates, Times, and Timezones

Verify separately:
- `LocalDate` is for calendar dates (birthdays, holidays); do not convert it to an instant.
- `LocalDateTime` holds local date/time without a timezone; treating it as an instant introduces ambiguity.
- `Instant` represents an absolute point in time; after persisting via a SQL type, test the exact same instant on read-back.
- `OffsetDateTime` holds both time and offset; decide whether to preserve the **instant**, the **offset**, or both.

Test data should include DST boundary dates, 00:00, 23:59:59, before/after leap days, month ends, sub-second `.123456789`, offsets `+07:00`, `Z`, `-05:00`, and differing DB/session timezones.

**Never assume `TIMESTAMP WITHOUT TIME ZONE` and `TIMESTAMP WITH TIME ZONE` are equivalent.** How DBs store offsets and convert them is vendor-dependent; many DBs normalize instants and drop the input offset. If the original offset is business data, store offset/zone ID separately alongside the instant.

### 8.3 UUID / Binary IDs

When storing `UUID` in `BINARY(16)`, verify all 16 bytes and **the exact byte order** on decode. When storing in `CHAR(36)`/`VARCHAR(36)`, verify parsing back to the exact UUID; string letter case may vary while the UUID object stays identical.

Never alter byte order or base64/hex encoders without tests. For critical IDs, compare the decoded UUID against the input UUID and check DB uniqueness. One successful UUID round-trip does not prove all values succeed; include UUIDs with bytes `0x00`, `0x80`, `0xFF`, and random samples.

### 8.4 JSON / Custom Objects

Test JSON with:
- Vietnamese strings, emojis, escapes, combining Unicode characters;
- `null`, missing fields, empty arrays, empty objects, nested arrays;
- very large numbers / high-precision decimals; booleans and strings resembling numbers;
- near-duplicate field names and reordered keys.

If the contract is **JSON structure**, parse into a tree with exact numeric handling and compare meaningful fields. Never treat `{"a":1}` and `{"a":"1"}` as equivalent. If exact raw JSON bytes (casing, whitespace, key order, escapes) must be kept, store raw text/bytes by design; `JSONB` types in some DBs canonicalize representations.

Spring JDBC may read JSON via `getString`, `getObject`, or vendor-specific objects depending on the driver. Define an explicit converter/`RowMapper` and test both write and read directions. `ConversionService` does not automatically make **every** vendor-specific mapping via `JdbcTemplate` safe.

### 8.5 Binary / BLOB

Compare `Arrays.equals(before, after)` on `byte[]`; for large BLOBs, compute a SHA-256 digest and length **from both streams** to avoid loading everything into RAM. Digests detect corruption with very high probability, though they do not replace business semantic checks. Test `0x00` bytes, negative byte values in Java's signed `byte`, 0-length, exact limit, and over-limit payloads.

Never round-trip binary via `new String(bytes)` and `getBytes()` with the default charset; arbitrary byte sequences are not valid UTF-8 text. If the payload is text, specify `StandardCharsets.UTF_8` and an invalid-sequence policy.

### 8.6 Enum / Domain Codes

Never store `enum.ordinal()` if constant order can change across software releases; map to stable business codes (e.g., `PENDING`, `PAID`) and reject unknown codes instead of silently falling back to a default. Test legacy codes in historical data, renames/migrations, casing, new values, and `null`.

For enums with converters, test `decode(encode(value)) == value` across **all** supported constants and legacy codes the app must read. Also run integration tests against the real SQL column to verify DB type, constraints, and JDBC binding.

### 8.7 ARRAY / Collections / Vendor-Specific Types

If an array is ordered, compare by index and preserve `null` elements. If the contract is a **set**, you may normalize order while still checking duplicate policies. SQL `ARRAY`, PostgreSQL `JSONB`, geometry, and custom types have driver-dependent bind/read mechanisms; a `RowMapper` may need `java.sql.Array`, vendor objects, or custom converters. Test element types, empty arrays, nested data, scale, and boundary values.

## 9. Boundary and Property-Based Test Datasets

A single round-trip test proves only **one case**. Build an intentional matrix, then add random/property-based tests:

| Case Group | Suggested Inputs | Bugs Likely Exposed |
| --- | --- | --- |
| Typical values | 2-decimal amounts, whole-second timestamps, standard UUIDs | Column/name/type mapping bugs |
| Precision/scale bounds | `0.001`, `-999999.99`, exceeding `p`, trailing zeros | Decimal loss, overflow, wrong comparator |
| Timestamp bounds | 1 ns, 999.999.999 ms, end of day, DST | Rounding, date shifts, timezone drift |
| Unicode | `Đặng`, `café`, `e\u0301`, emojis, control characters | Charset, normalization, truncation |
| Null/missing | SQL `NULL`, JSON `null`, missing JSON key, empty string | Lost null/zero/empty distinctions |
| Structured data | Nested JSON, arrays with nulls, unknown enums | Wrong type/structure/order |
| Binary | Bytes `00`, `80`, `FF`, exact/over length limits | Truncation, bad text decoding |
| Version upgrades | Data written by older version, schema migration | Non-backward-compatible converters |
| Different driver/config | H2 tests, real PostgreSQL/MySQL, varying session timezones | Vendor and session differences |

An example property to verify is "for every valid `x` in domain D, after storing and reading back, `equivalent(x, read(write(x)))` must hold." If D permits at most 2 decimal places, **restrict D before testing**; never "make the test pass" by silently stripping data from out-of-domain `x`.

When generating random inputs, log the seed so failing cases are reproducible. Add manual boundary values too, since random generation rarely hits exact DST transitions or max column limits.

## 10. Testing with Spring JDBC and a Real DB

To match production flows, integration tests should use:
1. **Real DDL/schema** (including `NOT NULL`, `CHECK`, precision/scale, collation, timezone/encoding).
2. **The same JDBC driver and major DB version** used in production, e.g., spun up via Testcontainers.
3. **The same bind code + RowMapper + converters** used by the application; never write mock test mappers that differ from production.
4. **Commit and read from a new transaction/connection** when verifying persisted state and transformations that occur only upon commit.
5. Verify both exceptions and silent coercion: throwing an error is a different outcome from succeeding with corrupted data.
6. Include **positive**, **intentional-failure**, and **permitted-normalization** tests.

In `JdbcTemplate` tests, do not assert only `jdbc.update(...) == 1`. A row count shows a row was affected, not that every field stayed intact. After writing, query back **all critical fields** and assert with the right comparator.

Additional assertion snippet extending the Java code in Section 5 (used only in a test context with `before` and `after`):

```java
if (before.amount().compareTo(after.amount()) != 0) {
    throw new AssertionError("Decimal changed during round-trip");
}
if (!before.occurredAt().equals(after.occurredAt())) {
    throw new AssertionError("Timestamp precision lost");
}
if (!java.util.Arrays.equals(before.payload(), after.payload())) {
    throw new AssertionError("Binary payload changed");
}
```

These assertions **intentionally fail** with the demo's `DECIMAL(8,2)` and `TIMESTAMP(3)` schema; that shows the test is doing its job. To satisfy exactness, widen `DECIMAL`/`TIMESTAMP` to the required precision, or validate inputs and normalize transparently per contract, then re-test.

## 11. Distinguishing Real Conversion Bugs from Permitted Representation Differences

Three easily confused scenarios:

**Case A — real numeric loss.** `12.3456` → `12.35` alters money when 4 decimal places matter. `BigDecimal.compareTo` catches this. This is a schema/mapping bug whenever the contract requires full scale 4.

**Case B — same numeric value, changed scale.** `12.3400` → `12.34` has `compareTo == 0`, yet `equals == false`. If scale carries no business meaning, this can be a valid round-trip; if exact scale must be preserved, the contract requires more.

**Case C — same instant, changed offset.** `2026-10-30T09:00+07:00` and `2026-10-30T02:00Z` represent the same moment. If the business only needs the instant, no value was lost; if the original offset or historical zone must be kept, representation info was lost and extra metadata must be stored.

Similarly, JSON may canonicalize key order, text UUIDs may change letter case, Unicode may be normalized, and `CHAR` may pad spaces. Do not lump all of these under "data loss" if the contract does not require preserving representation; equally, do not ignore differences the contract genuinely depends on.

A strong test design separates **two assertions**:
- `semanticEquivalent(expected, actual)` to check business value;
- `representationPreserved(expected, actual)` when exact original representation must be retained.

## 12. Common Real-World Mistakes

- **Checking only insert/update counts:** SQL succeeds while `DECIMAL` or `TIMESTAMP` quietly rounded the value.
- **Using `BigDecimal.equals` unconditionally:** produces false positives for differing scales with equal numeric values; conversely, arbitrary tolerances can hide real monetary errors.
- **Passing exact numbers through `double` before writing:** precision was already lost before SQL, so widening the DB column cannot fix it.
- **Using `LocalDateTime` as an instant:** across timezone/session changes, the same local clock string can point to different moments, especially around DST.
- **Reading SQL `NULL` with primitive `getInt` and forgetting `wasNull`:** turns null into 0, violating the contract.
- **Comparing arrays with `equals`:** checks reference identity, not element contents.
- **Comparing JSON as strings when the contract is structural, or coercing numbers through `double`:** invites both false failures and precision loss.
- **Testing converters only with unit tests:** misses SQL column and driver coercions; integration tests on a real DB are required.
- **Reading back from an unrefreshed cache/entity:** you may be inspecting the original in-memory object rather than persisted data; use another query/transaction when needed.
- **Using H2 to assert PostgreSQL/MySQL behavior:** timestamp, decimal, JSON, enum, and charset rules differ.
- **Testing only short/ASCII inputs:** misses Unicode, raw binary bytes, boundary values, and historical data.
- **Writing tests that only compare the end outputs of two symmetrically buggy converters:** if both write and read apply the same wrong transform, a weak comparison can still pass. Verify storage format contracts, schema, and intermediate DB values.

## 13. Checklist for Code Reviews and Schema Changes

Before shipping a special data type to production, confirm:

- Java/domain type names, SQL types, `precision/scale/length`, and `NULL` policies are explicitly declared.
- What constitutes **equivalence** is defined: value, scale, instant, offset, code points, JSON tree, bytes, or element ordering.
- Encode/bind and decode/map code share a single contract, with bidirectional tests.
- Write/read tests run with real SQL values on the right DB/driver, not only DTO/unit tests.
- Cases cover normal values, nulls, boundaries, invalid inputs, Unicode, random values, and legacy data.
- Negative tests verify **data loss is detected**, not just happy paths.
- Normalized data has explicit rules and dedicated tests; disallowed loss is rejected before writing.
- Whenever `DECIMAL`, `TIMESTAMP`, `VARCHAR`, JSON columns, or driver versions change, the round-trip test suite is re-run.
- When a discrepancy is found, its origin is isolated among the Java converter, JDBC driver, DB coercion, or read-back mapping.
- Error logging never leaks secrets or raw contents of sensitive BLOBs/JSON.

When migrating from `DECIMAL(12,4)` to `DECIMAL(12,2)`, tests should flag existing rows that cannot be represented exactly at scale 2 **before migration**, rather than only proving new rows can be inserted. For timezone/JSON mapping changes, cross-check a sample of historical data with both old and new readers under the same business invariants.

## 14. Summary and Official References

**Core principle:** Succeeding on write and reading without errors does not prove data integrity. Write a contract *`read(write(x)) ≡ x`*, define `≡` according to business meaning, run it through the actual schema + driver + converter, and inspect raw values when needed. If data loss is unacceptable, fix the schema or reject invalid inputs before writing; if normalization is permitted, document and test that normalization explicitly.

References:
- Spring Framework 6.2 — JDBC data access: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc.html
- Spring — Providing SQL type information and handling parameter values: https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html
- Spring — Using JdbcTemplate and mapping query results: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- H2 — Data types (DECIMAL, TIMESTAMP precision, VARBINARY): https://h2database.github.io/html/datatypes.html
- Java 17 — `ResultSet`/JDBC typed `getObject`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html
- Java 17 — `BigDecimal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java 17 — `OffsetDateTime`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/OffsetDateTime.html
