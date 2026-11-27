# Mapping PostgreSQL Data Types to Java via JDBC

When a Java application accesses PostgreSQL, data crosses two distinct type systems: **SQL types managed by PostgreSQL** and **Java types exposed by the JDBC driver**. A `numeric(18,4)` column must not be casually read into `double` when representing money; `timestamp with time zone` is not the same as `timestamp without time zone`; a `jsonb` column does not automatically turn into a Java domain object; and SQL `NULL` is not the same as a Java primitive's default value of 0.

This guide explains how to choose Java types, how to call `ResultSet.getXxx()`, `getObject()`, `PreparedStatement.setXxx()`, `setObject()`, and `setNull()`, and covers cases requiring PostgreSQL JDBC driver-specific types such as `PGobject`, `PGInterval`, or `java.sql.Array`. Examples emphasize accuracy for money, dates and times, JSON, UUIDs, arrays, `bytea`, and PostgreSQL-specific types.

This lesson belongs to the **Application Connections** chapter of the **Database Engine Relational PostgreSQL** module. All code snippets focus on PostgreSQL and Java/JDBC; table names, roles, and URLs in examples are illustrative. PostgreSQL JDBC Driver (*pgJDBC*) features can change across versions, so use a supported driver version and test specific behavior on your actual version before deploying.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Distinguish between PostgreSQL data types, JDBC type codes, and Java object types.
2. Read and write `boolean`, integers, floating-point numbers, `numeric`, and strings without losing data semantics.
3. Use `java.time` types properly for `date`, `time`, `timestamp`, and `timestamptz`.
4. Explain why PostgreSQL does not store the original time zone name inside `timestamptz`.
5. Map UUID, JSON/JSONB, ARRAY, BYTEA, ENUM, INTERVAL, and several extended types.
6. Distinguish SQL NULL from Java null, JSON null, empty arrays, and empty strings.
7. Use `PreparedStatement` and placeholders safely to pass values.
8. Choose `getObject(column, Type.class)` properly where supported by the driver; know when another API is required.
9. Inspect column metadata via JDBC and system catalogs instead of guessing types.
10. Set up a runnable PostgreSQL and Java practice lab.
11. Identify precision loss, time zone drift, wrong casts, encoding mistakes, and data leaks.
12. Design domain models, DTOs, and database schemas with clean boundaries that evolve safely.

## 2. Three Mapping Layers That Must Be Separated

~~~text
PostgreSQL
   |
   | SQL type and value
   | numeric, uuid, timestamptz, jsonb, text[], ...
   v
PostgreSQL Wire Protocol / pgJDBC
   |
   | JDBC type code + driver conversion
   | Types.NUMERIC, Types.OTHER, ...
   v
ResultSet / PreparedStatement
   |
   | getBigDecimal / getObject(UUID.class)
   | setObject / setNull / ...
   v
Java model
   |
   | BigDecimal, UUID, OffsetDateTime, List<String>, ...
   v
Service / API / Business logic
~~~

### 2.1. PostgreSQL Types

PostgreSQL understands `numeric(12,2)`, `timestamptz`, `jsonb`, `text[]`, or user-defined enum names. PostgreSQL enforces operators, constraints, and type casts on the server side.

### 2.2. JDBC Type Codes

`java.sql.Types` provides standard type codes such as `INTEGER`, `BIGINT`, `NUMERIC`, `DATE`, `TIMESTAMP`, `TIMESTAMP_WITH_TIMEZONE`, `ARRAY`, `BINARY`, and `OTHER`.

A PostgreSQL-specific type may be reported by the driver as `Types.OTHER`; this does not mean the data is "untyped".

### 2.3. Java Types

A PostgreSQL `bigint` column can be read as `long` or `Long`, yet if the column is nullable, primitive `long` cannot represent SQL NULL. Choose Java types according to the business contract.

### 2.4. Metadata Does Not Replace Domain Semantics

PostgreSQL `numeric(18,2)` might represent money, weight, or a ratio. JDBC sees `BigDecimal` in every case, while the application still needs to track units, currency, rounding rules, and validation.

## 3. JDBC Standard and pgJDBC Extensions

In Java, JDBC is the standard API comprising:

- `java.sql.Connection`
- `java.sql.PreparedStatement`
- `java.sql.ResultSet`
- `java.sql.ResultSetMetaData`
- `java.sql.Types`
- `java.sql.Array`
- `java.sql.SQLXML`
- `java.sql.Date`, `Time`, `Timestamp` in older applications.

The PostgreSQL JDBC driver adds capabilities needed for PostgreSQL-specific types:

- `org.postgresql.util.PGobject`
- `org.postgresql.util.PGInterval`
- Notification mechanisms, `COPY`, large objects, and other driver-specific APIs when used by the application.

### 3.1. Prefer Standard JDBC When Sufficient

For `integer`, `numeric`, `date`, or `timestamp`, there is usually no need to depend on `PGobject`. Standard getters or `getObject(..., Class)` are typically clearer and easier to test.

### 3.2. Specific Types Do Not Auto-Map to POJOs

A `jsonb` column does not automatically become an `OrderPayload`. You must serialize/deserialize JSON data according to your application's library and schema contract.

### 3.3. Driver Version Matters

JDBC 4.2 introduced `java.time` support; pgJDBC supports a specific set of conversions. Do not assume that merely because Java has `Instant` or `OffsetTime`, `getObject(..., Instant.class)` or `setObject(OffsetTime)` works on every pgJDBC version.

### 3.4. Documentation Must Be Backed by Testing

For less common types such as range, multirange, enum, network, or interval, the driver may return `PGobject` or another representation depending on type and version. In critical applications, write integration tests instead of assuming every column maps to a particular Java class.

## 4. Baseline Mapping Table

| PostgreSQL | Preferred Java Type | JDBC Read | JDBC Write |
|---|---|---|---|
| `boolean` | `Boolean` / `boolean` | `getBoolean`, `getObject(..., Boolean.class)` | `setBoolean`, `setObject` |
| `smallint` | `Short` / `short` | `getShort` | `setShort` |
| `integer` | `Integer` / `int` | `getInt` | `setInt` |
| `bigint` | `Long` / `long` | `getLong` | `setLong` |
| `numeric`, `decimal` | `BigDecimal` | `getBigDecimal` | `setBigDecimal` |
| `real` | `Float` / `float` | `getFloat` | `setFloat` |
| `double precision` | `Double` / `double` | `getDouble` | `setDouble` |
| `text`, `varchar` | `String` | `getString` | `setString` |
| `date` | `LocalDate` | `getObject(..., LocalDate.class)` | `setObject(LocalDate)` |
| `time` without time zone | `LocalTime` | `getObject(..., LocalTime.class)` | `setObject(LocalTime)` |
| `timestamp` without time zone | `LocalDateTime` | `getObject(..., LocalDateTime.class)` | `setObject(LocalDateTime)` |
| `timestamptz` | `OffsetDateTime` | `getObject(..., OffsetDateTime.class)` | `setObject(OffsetDateTime)` |
| `uuid` | `UUID` | `getObject(..., UUID.class)` | `setObject(UUID)` |
| `bytea` | `byte[]` | `getBytes` | `setBytes` |
| `text[]`, `integer[]` | `java.sql.Array`, matching Java array | `getArray` | `createArrayOf` + `setArray` |
| `json`, `jsonb` | JSON string / `PGobject` / domain model via JSON parser | `getString`, `getObject` | `PGobject` or explicit cast |
| `interval` | `PGInterval` or domain type | `getObject` then check type | `PGInterval` / appropriate SQL expression |
| PostgreSQL ENUM | `String` / Java enum via converter | `getString` | `setObject` + cast/type |
| `inet`, `cidr`, range... | `String` / `PGobject` / converter | `getString`, `getObject` | Explicit cast / `PGobject` |

This table reflects **common best practices**, not a promise that every overload or Java type is supported identically across all driver versions. Specifically for SQL NULL, extreme date/time values, and PostgreSQL-specific types, refer to the sections below.

## 5. Integer Types and Range Limits

PostgreSQL provides:

| PostgreSQL | Size | Typical Range | Java |
|---|---:|---|---|
| `smallint` | 2 bytes | -32,768 to 32,767 | `short` / `Short` |
| `integer` | 4 bytes | -2,147,483,648 to 2,147,483,647 | `int` / `Integer` |
| `bigint` | 8 bytes | -2^63 to 2^63−1 | `long` / `Long` |

Read example:

~~~java
short priority = rs.getShort("priority");
int attemptCount = rs.getInt("attempt_count");
long orderId = rs.getLong("order_id");
~~~

Write example:

~~~java
ps.setShort(1, (short) 2);
ps.setInt(2, 3);
ps.setLong(3, 9_223_372_036L);
~~~

### 5.1. Do Not Use `int` for `BIGINT` Just Because Current Data Is Small

A `bigint` column is typically chosen for its wide range. If read via `getInt()`, values growing beyond 32-bit range can cause conversion errors or break the application. Choose `Long` for `BIGINT` contracts.

### 5.2. `SERIAL` Is Not a Separate Numeric Type

`smallserial`, `serial`, and `bigserial` are shorthand notations that create numeric columns with associated sequences/defaults. In JDBC, values are still handled as their underlying numeric types: `smallint`, `integer`, or `bigint`.

### 5.3. `IDENTITY` Is Also a Value-Generation Mechanism

~~~sql
event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
~~~

On the Java side, `event_id` is read as `Long`; there is no Java type named "Identity". To retrieve generated IDs on `INSERT`, use `RETURNING` or appropriate JDBC generated keys.

### 5.4. Nullable Columns Should Use Wrapper Types

If `attempt_count integer NULL`, use `Integer` instead of `int` to represent missing values. Primitives cannot hold `null`.

## 6. SQL NULL Differs From 0 and `false`

This is one of the most serious and subtle mapping bugs.

~~~java
int count = rs.getInt("attempt_count");
~~~

If the SQL column is NULL, a JDBC primitive getter returns a default value (such as `0`), making it impossible to distinguish NULL from "0 attempts".

### 6.1. Check `wasNull()` Immediately After the Getter

~~~java
int value = rs.getInt("attempt_count");
Integer attemptCount = rs.wasNull() ? null : value;
~~~

Similarly:

~~~java
boolean value = rs.getBoolean("enabled");
Boolean enabled = rs.wasNull() ? null : value;
~~~

### 6.2. `wasNull()` Reflects Only the Most Recently Read Value

Do not call another getter before checking `wasNull()`, because it reflects the NULL status of the last column value read.

### 6.3. `getObject` With Wrapper Types

When supported by the driver:

~~~java
Integer attemptCount =
    rs.getObject("attempt_count", Integer.class);
~~~

If the SQL column is NULL, returning an object can yield Java `null` directly. Verify behavior on your driver version.

### 6.4. SQL NULL Is Not an Empty String

`NULL` in `text` differs from `''`. `getString()` returns `null` for SQL NULL and an empty string for `''`.

### 6.5. Domain Types Must Express Intent

If a nullable boolean means "unknown", use `Boolean` or a three-state enum instead of silently defaulting to `false`.

## 7. `NUMERIC`/`DECIMAL` and `BigDecimal`

For monetary data or decimal values requiring exactness, use `numeric(p,s)` in PostgreSQL and `java.math.BigDecimal` in Java.

~~~sql
CREATE TABLE billing_examples (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(18,4) NOT NULL,
    tax_rate NUMERIC(9,6) NOT NULL
);
~~~

~~~java
BigDecimal amount = rs.getBigDecimal("amount");
BigDecimal taxRate = rs.getBigDecimal("tax_rate");
~~~

### 7.1. Why Avoid `double` for Money?

`double` is binary floating-point. Many decimal values like 0.1 have no exact finite binary representation, so arithmetic can introduce rounding errors.

### 7.2. Construct `BigDecimal` From Strings

~~~java
BigDecimal price = new BigDecimal("1250.75");
~~~

Avoid:

~~~java
BigDecimal price = new BigDecimal(0.1);
~~~

The `double` constructor preserves binary representation error. When the input is already a `double`, `BigDecimal.valueOf(double)` may be used if the source's limitations are understood, though receiving values from a string/decimal source from the start is better.

### 7.3. Writing `BigDecimal`

~~~java
ps.setBigDecimal(1, new BigDecimal("199.9900"));
~~~

PostgreSQL applies the column's typmod precision/scale per SQL semantics. The application should still validate business rules before writing.

### 7.4. Watch Precision and Scale

- **Precision**: total number of significant digits per `numeric` definition.
- **Scale**: number of digits after the decimal point declared on the column.
- A value exceeding precision bounds can be rejected by PostgreSQL.
- A value with more decimal digits than scale can be rounded upon storage.

### 7.5. `BigDecimal.equals` Differs From `compareTo`

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));         // false
System.out.println(a.compareTo(b) == 0); // true
~~~

`equals` considers scale, whereas `compareTo` compares numeric value. This matters when using `BigDecimal` as a `Set`/`Map` key or in domain comparisons.

## 8. Rounding Rules for Money and Rates

Some systems require exact rounding per business policy:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("99.995");
BigDecimal rounded = price.setScale(2, RoundingMode.HALF_UP);
~~~

### 8.1. Do Not Assume PostgreSQL and Java Use Identical Rules

PostgreSQL `numeric` and Java `BigDecimal` have differing rounding behavior in certain tie cases or when converting between `numeric` and floating-point. Pick an explicit business rule and test with identical inputs.

### 8.2. Do Not Round Too Many Times

If amounts are rounded per line item and then summed, the result can differ from summing first and rounding once. Rules must be consistent across SQL, Java, and reports.

### 8.3. Avoid Converting `BigDecimal` to `double` Mid-Pipeline

~~~java
// Unsuitable when exact decimal precision must be preserved:
double asDouble = amount.doubleValue();
~~~

Once precision is lost, converting back to `BigDecimal` cannot recover the original digits.

### 8.4. Special Values of `NUMERIC`

PostgreSQL supports special values such as `NaN` and, depending on version, `Infinity` in `numeric`. Java `BigDecimal` **cannot represent `NaN` or `Infinity`**. If a column can hold them, define a clear domain policy and test conversion; for money, enforce constraints to reject invalid values.

## 9. `REAL` and `DOUBLE PRECISION`

PostgreSQL:

- `real`: single-precision floating-point number.
- `double precision`: double-precision floating-point number.

Java:

~~~java
float f = rs.getFloat("sensor_value");
double d = rs.getDouble("confidence");
~~~

Write:

~~~java
ps.setFloat(1, 0.75f);
ps.setDouble(2, 0.987654321);
~~~

### 9.1. When to Use Them?

Suitable for scientific calculations, measurements, or approximate results where floating-point error is acceptable.

### 9.2. `NaN` and `Infinity`

Java `Float`/`Double` can represent `NaN` and `±Infinity`; PostgreSQL floating-point types have corresponding behavior. However, JSON serializers, reports, and database constraints may reject these values. Define rules at the domain layer.

### 9.3. Do Not Compare Approximate Values With Exact Equality

Floating-point comparisons typically need a tolerance matching the units/precision. Never apply a tolerance strategy to money where `BigDecimal` should be used.

## 10. `BOOLEAN`

PostgreSQL `boolean` supports `TRUE`/`FALSE`/`NULL`. In Java:

~~~java
Boolean verified = rs.getObject("verified", Boolean.class);
~~~

or:

~~~java
boolean verifiedPrimitive = rs.getBoolean("verified");
boolean isUnknown = rs.wasNull();
~~~

### 10.1. `getBoolean` Returns `false` for SQL NULL

If `wasNull()` is omitted, three states (`TRUE`, `FALSE`, `NULL`) collapse into two, silently altering business logic.

### 10.2. Writing Typed NULL

~~~java
ps.setNull(1, java.sql.Types.BOOLEAN);
~~~

or use `setObject(..., null, Types.BOOLEAN)` when supported properly by the API/driver.

### 10.3. Do Not Read `boolean` via `getString` to Parse Manually Without Reason

The PostgreSQL driver understands `boolean`; manually parsing `"t"`, `"true"`, and `"1"` from `String` introduces unnecessary bugs.

## 11. `TEXT`, `VARCHAR`, and `CHAR`

Common text types:

| PostgreSQL | Java | Notes |
|---|---|---|
| `text` | `String` | No `VARCHAR(n)` length cap |
| `varchar(n)` | `String` | PostgreSQL enforces length limit |
| `varchar` | `String` | No specific length typmod |
| `char(n)` / `character(n)` | `String` | Padding and trailing-space semantics require care |
| `citext` (extension) | `String` | Case-insensitive comparison per extension/collation |

~~~java
String title = rs.getString("title");
ps.setString(1, "PostgreSQL and Java");
~~~

### 11.1. PostgreSQL `text` and Java `String` Count Length Differently

Java `String.length()` counts UTF-16 code units, not necessarily code points or perceived characters. PostgreSQL `char_length` counts characters per encoding; `octet_length` counts bytes.

### 11.2. Vietnamese Unicode

Accented strings can exist in different composed or decomposed Unicode forms. Two visually identical strings may not compare equal under every comparison/collation. When Unicode normalization is needed, define where it occurs and keep the contract consistent.

### 11.3. Do Not Auto-Trim Data Unless the Contract Requires It

`text` preserves meaningful whitespace. Automatically calling `.trim()` or `.strip()` in DTO mappers can corrupt text data, tokens, or identifiers.

### 11.4. PostgreSQL Cannot Store NUL Characters in `text`

A Java `String` can contain `\u0000` as a zero code unit; PostgreSQL `text` rejects NUL bytes. Validate input if data might include special bytes/characters. For binary data, use `BYTEA` instead of forcing it into `TEXT`.

### 11.5. `CHAR(n)` Is Rarely the Optimal Default

`character(n)` has padding/trailing-space semantics that often surprise developers. Most names, descriptions, and free-form codes fit `text` or `varchar(n)` better.

## 12. Date and Time Is the Most Sensitive Mapping Group

PostgreSQL provides:

- `date`: calendar date, no time of day.
- `time without time zone`: time of day, no offset.
- `timestamp without time zone`: local date + time, no time zone attached to the value.
- `timestamp with time zone` / `timestamptz`: absolute point in time (instant), displayed in the session time zone.
- `time with time zone` / `timetz`: time with offset; has many practical limitations and is rarely recommended for new business designs.
- `interval`: span of time / calendar components.

| PostgreSQL | Typical Java 8+ Fit | Example Meaning |
|---|---|---|
| `date` | `LocalDate` | Birth date, date-based deadline |
| `time` | `LocalTime` | Scheduled opening hour |
| `timestamp` | `LocalDateTime` | Local appointment time without zone |
| `timestamptz` | `OffsetDateTime`, convert to `Instant` | Transaction timestamp |
| `timetz` | Driver-specific handling | Time + offset; no timezone ID stored |
| `interval` | `PGInterval` / multi-component domain type | 2 months, 3 days, 4 hours |

### 12.1. Do Not Attach a Time Zone Implicitly

A `LocalDateTime` is only a calendar date and wall-clock time; it does not identify a global instant until a `ZoneId` rule is applied.

### 12.2. `TIMESTAMPTZ` Does Not Store the Original `ZoneId`

PostgreSQL normalizes the value to an instant and formats it using the session `TimeZone`. Whether a user entered `Asia/Ho_Chi_Minh` or `Europe/Paris`, PostgreSQL does not retain that zone name in a `timestamptz` column.

### 12.3. Offsets in Timestamp Literals

PostgreSQL supports explicit syntax:

~~~sql
TIMESTAMPTZ '2026-11-14 10:30:00+07'
~~~

This represents an instant given with a `+07:00` offset at input time; that offset is not a full timezone ID carrying historical DST rules.

## 13. `DATE` ↔ `LocalDate`

PostgreSQL:

~~~sql
SELECT DATE '2026-11-14' AS event_date;
~~~

JDBC 4.2/pgJDBC:

~~~java
LocalDate date = rs.getObject("event_date", LocalDate.class);
ps.setObject(1, LocalDate.of(2026, 11, 14));
~~~

### 13.1. Avoid `java.util.Date` When Unnecessary

`java.util.Date` represents an epoch-millisecond instant, which differs semantically from a calendar date without time or zone. `LocalDate` is usually a better fit for SQL `DATE`.

### 13.2. Legacy API

~~~java
java.sql.Date sqlDate = rs.getDate("event_date");
LocalDate localDate = sqlDate == null ? null : sqlDate.toLocalDate();
~~~

When using legacy `Date`/`Timestamp` APIs, watch out for conversions and default time zones in relevant contexts.

### 13.3. `DATE` Infinity and Extreme Values

PostgreSQL supports special values such as `infinity` and `-infinity` for dates/timestamps per type. Do not assume every value maps naturally to `LocalDate` across all versions. If your domain allows extreme values, define an explicit policy and write integration tests.

### 13.4. A Date of Birth Is Not an Instant

A birth date `2000-01-01` should not be shifted across UTC offsets. Forcing a `DATE` into an `Instant` can display the wrong day in other time zones.

## 14. `TIME WITHOUT TIME ZONE` ↔ `LocalTime`

PostgreSQL:

~~~sql
SELECT TIME '09:15:30.123456' AS opening_time;
~~~

Java:

~~~java
LocalTime t = rs.getObject("opening_time", LocalTime.class);
ps.setObject(1, LocalTime.of(9, 15, 30, 123_456_000));
~~~

### 14.1. How to Interpret It

`LocalTime` represents hour-minute-second within a day **without a date or zone**. Useful for work schedules or local opening hours.

### 14.2. 09:00 Is Not 09:00 UTC

If a store opens at 9 AM in Hanoi, store the `Asia/Ho_Chi_Minh` zone in business metadata or use dedicated configuration rules. `LocalTime` alone carries no time zone.

### 14.3. `TIME WITH TIME ZONE`

`timetz` carries an offset with the time, yet lacks a date to apply DST accurately in all cases. Do not assume pgJDBC always supports `OffsetTime` on every version just because Java has that class. Only use it when needed and tested on your specific driver.

### 14.4. Time Resolution

PostgreSQL `timestamp`/`time` typically has microsecond precision, whereas Java time types support nanoseconds. Nanosecond data may be truncated or rounded on write. Test sub-microsecond edge cases instead of expecting all nanosecond digits to round-trip.

## 15. `TIMESTAMP WITHOUT TIME ZONE` ↔ `LocalDateTime`

PostgreSQL:

~~~sql
SELECT TIMESTAMP '2026-11-14 08:45:00' AS local_meeting;
~~~

Java:

~~~java
LocalDateTime local = rs.getObject(
    "local_meeting",
    LocalDateTime.class
);
ps.setObject(1, LocalDateTime.of(2026, 11, 14, 8, 45));
~~~

### 15.1. Do Not Assume UTC Implicitly

SQL `timestamp without time zone` does not represent a unique instant. Calling `local.toInstant(ZoneOffset.UTC)` is only valid if the application has an **explicit convention** that the column stores UTC wall-clock time.

### 15.2. JVM Timezone Config Should Not Define an Implicit Contract

One instance running in UTC and another in `Asia/Ho_Chi_Minh` can handle legacy `Timestamp` differently if the app converts via epoch/Calendar without a consistent rule.

### 15.3. When Storing Future Appointments

A 09:00 appointment in a zone with DST needs both **`LocalDateTime` and `ZoneId`** or an explicit schedule model. If you only store an instant computed today and DST rules later change, "9 AM local time" can shift.

### 15.4. Do Not Use `LocalDateTime` for Absolute Transaction Instants

Fields like `created_at`, `paid_at`, and audit timestamps represent instants; prefer `timestamptz` and instant/offset-carrying Java types.

## 16. `TIMESTAMPTZ` ↔ `OffsetDateTime`

PostgreSQL:

~~~sql
SELECT TIMESTAMPTZ '2026-11-14 10:00:00+07' AS occurred_at;
~~~

Java:

~~~java
OffsetDateTime value = rs.getObject(
    "occurred_at",
    OffsetDateTime.class
);
Instant instant = value.toInstant();
~~~

Write:

~~~java
OffsetDateTime moment = OffsetDateTime.now(ZoneOffset.UTC);
ps.setObject(1, moment);
~~~

### 16.1. PostgreSQL Stores an Instant, Not the Input Offset

`2026-11-14 10:00+07` and `2026-11-14 03:00+00` represent the exact same instant. When reading into `OffsetDateTime`, pgJDBC typically returns UTC offset for `timestamptz`; do not expect to get back the `+07:00` offset the client passed in.

### 16.2. `OffsetDateTime` Differs From `ZonedDateTime`

`ZoneOffset.ofHours(7)` is a fixed offset. `ZoneId.of("Europe/Paris")` carries regional rules across dates. A `timestamptz` column cannot recover the original `ZoneId` name.

### 16.3. Java `Instant` Can Fit the Domain

If business logic only needs an instant, convert:

~~~java
Instant occurredAt = rs.getObject(
    "occurred_at", OffsetDateTime.class
).toInstant();
~~~

For nullable columns, check for `null` before calling `.toInstant()`.

### 16.4. Do Not Assume `getObject(..., Instant.class)`

Depending on the pgJDBC version, `Instant` may not be directly supported by JDBC getters/setters. The safer path for `timestamptz` is `OffsetDateTime`, then converting to `Instant`.

### 16.5. Session `TimeZone` Affects SQL Text Formatting

~~~sql
SHOW TimeZone;
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT TIMESTAMPTZ '2026-11-14 10:00:00+07';
~~~

The displayed text changes with the session `TimeZone`, yet the underlying instant remains unchanged.

## 17. DST and Local Time Conversion

A wall-clock time in a zone with DST can encounter:

- **Gap**: a local hour that does not exist when clocks spring forward.
- **Overlap**: the same local hour occurring twice when clocks fall back.

Java:

~~~java
ZoneId zone = ZoneId.of("Europe/Paris");
LocalDateTime local =
    LocalDateTime.of(2026, 10, 25, 2, 30);

ZonedDateTime zoned = local.atZone(zone);
Instant instant = zoned.toInstant();
~~~

### 17.1. `atZone` Applies Gap/Overlap Resolution Rules

Do not treat `atZone` as a check for "does this date-time map to a unique instant"; Java applies default rules to resolve gaps and overlaps. For critical scheduling systems, confirm which offset the user intended or whether non-existent times are disallowed.

### 17.2. Where to Store the Zone ID?

If regional schedule intent must be preserved, store a separate `text` column such as `time_zone_id` alongside local date/time and conversion rules.

### 17.3. Never Treat Server Timezone as Policy

Production containers often run in UTC while serving users in Vietnam or Europe. The zone must come from domain/user/business requirements, never from whichever timezone the host happens to be configured with.

### 17.4. An Offset Does Not Fully Solve Future Schedules

`+01:00` in January does not necessarily apply in July in the same region. For recurring schedules, `ZoneId` matters more than a fixed offset.

## 18. Legacy `Timestamp`, `Calendar`, and Compatibility

Older codebases often use:

~~~java
Timestamp ts = rs.getTimestamp("occurred_at");
Date date = rs.getDate("birth_date");
Time time = rs.getTime("opens_at");
~~~

### 18.1. Do Not Mix `java.sql.Date` and `java.util.Date` Casually

Both share the name `Date`, yet have different semantics. Prefer `java.time` in new code.

### 18.2. `Timestamp` Has a Nanoseconds API

`java.sql.Timestamp` supports nanoseconds in Java, while PostgreSQL `timestamp` precision is limited; do not assume all 9 nanosecond digits round-trip intact.

### 18.3. `Calendar` Overloads

JDBC offers overloads such as `getTimestamp(column, Calendar)` to influence reading/interpretation in legacy scenarios. When migrating to `LocalDateTime`/`OffsetDateTime`, test actual outputs rather than bulk-replacing getters just because the method names look shorter.

### 18.4. Migration Rule

Pick one clear convention per column: `DATE` = calendar date, `TIMESTAMP` = local wall-clock, `TIMESTAMPTZ` = instant. Then update domain models, serializers, tests, and queries together.

## 19. `UUID` ↔ `java.util.UUID`

PostgreSQL has a native `uuid` type:

~~~sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY,
    label TEXT NOT NULL
);
~~~

Java:

~~~java
UUID id = rs.getObject("id", UUID.class);
ps.setObject(1, UUID.randomUUID());
~~~

### 19.1. UUID Is a Logical Binary Value, Not Arbitrary Text

You can use `getString()` for display, yet Java's `UUID` type expresses the domain cleanly and prevents parsing bugs.

### 19.2. When JSON String Serialization Is Needed

~~~java
String serialized = id.toString();
UUID restored = UUID.fromString(serialized);
~~~

Check for `null` before calling methods.

### 19.3. A UUID Is Not Inherently a Security Token

A random UUID should not automatically be treated as a privileged authentication token solely because it looks hard to guess; security also depends on generator version, entropy, lifetime, and authorization.

### 19.4. Distinguish Primary Keys From Business Identifiers

A UUID can serve as a surrogate key, yet does not replace `UNIQUE` constraints on business fields like `order_number` when those must be unique.

## 20. `JSON` and `JSONB`: PostgreSQL Types Are Not Java Objects

PostgreSQL:

~~~sql
CREATE TABLE events_json (
    event_id BIGINT PRIMARY KEY,
    payload JSONB NOT NULL
);
~~~

`JSONB` stores JSON data in an internal parsed/normalized binary representation; it does not necessarily preserve whitespace, key order, or exact input text. `JSON` preserves input text more closely, with different parsing/validation behavior.

### 20.1. `getString`

~~~java
String jsonText = rs.getString("payload");
~~~

Use a JSON parser such as Jackson or Gson to turn the string into a domain class or tree. `getString()` does not automatically convert JSON into a `Map` or DTO.

### 20.2. `PGobject`

A common read pattern with pgJDBC:

~~~java
Object raw = rs.getObject("payload");
if (raw instanceof org.postgresql.util.PGobject) {
    org.postgresql.util.PGobject obj =
        (org.postgresql.util.PGobject) raw;
    String postgresTypeName = obj.getType();
    String json = obj.getValue();
}
~~~

For types without a standard Java mapping in the driver, `PGobject` carries the PostgreSQL type name and corresponding text value.

### 20.3. Do Not Pass `Types.VARCHAR` When Writing `JSONB`

A `String` parameter sent by JDBC as `varchar`/`text` may not be implicitly cast to `jsonb` by PostgreSQL in every statement context. Use an explicit cast or a `PGobject` with type `jsonb`.

### 20.4. `JSONB` Only Validates JSON Syntax, Not the Full Business Schema

`{"price":"abc"}` is valid JSON yet may be invalid for a monetary price domain. Enforce JSON schema/domain validation at the appropriate layer, paired with database constraints where needed.

## 21. Writing `JSONB` via `PGobject` and Explicit Casts

### 21.1. Using `PGobject`

~~~java
import org.postgresql.util.PGobject;

PGobject jsonb = new PGobject();
jsonb.setType("jsonb");
jsonb.setValue("{\"source\":\"jdbc\",\"attempt\":2}");

ps.setObject(1, jsonb);
~~~

### 21.2. Using a SQL Cast

~~~sql
INSERT INTO events_json(event_id, payload)
VALUES (?, ?::jsonb);
~~~

~~~java
ps.setLong(1, 101L);
ps.setString(2, "{\"source\":\"jdbc\"}");
~~~

### 21.3. Two Approaches, One Goal

Both help PostgreSQL recognize the parameter as `JSONB` where needed. Test with your driver, prepared statements, casts, and real SQL.

### 21.4. Avoid Concatenating JSON Strings Directly Into SQL

Never build:

~~~java
// WRONG: concatenating JSON/user input into SQL text
String sql = "INSERT INTO events_json(payload) VALUES ('"
           + jsonFromUser + "')";
~~~

Quoting bugs, escaping issues, and SQL injection can occur. Parameterize data using `PreparedStatement`.

## 22. SQL NULL Differs From JSON `null`

Three distinct cases:

~~~sql
SELECT
    NULL::jsonb                  AS sql_null,
    'null'::jsonb                AS json_null,
    '{}'::jsonb                  AS empty_object;
~~~

- `NULL::jsonb`: SQL NULL value; the column has no value.
- `'null'::jsonb`: JSON literal `null`; the SQL column itself is NOT NULL.
- `'{}'::jsonb`: empty JSON object.

### 22.1. JDBC `getString`

If SQL NULL: `getString()` normally returns Java `null`.

If JSON literal `null`: `getString()` normally returns the string `"null"` (four characters n-u-l-l), not Java `null`.

### 22.2. Jackson Tree Model

A JSON parser may represent JSON `null` with its own node, distinct from the absence of a SQL value. If the application needs to tell them apart, do not collapse both into Java `null`.

### 22.3. Empty JSON Array Differs From Empty SQL `ARRAY`

JSON `[]` stored in `jsonb` differs from a PostgreSQL `text[]` column holding `ARRAY[]::text[]`. They have different operators, indexes, and schema semantics.

### 22.4. JSON Types and Java Schema Evolution

If a `JSONB` payload contains a new field, older Java DTOs may need to ignore unknown fields or handle versioning; conversely, PostgreSQL does not automatically validate the domain schema of every property.

## 23. The `?` Character in JSONB Operators and JDBC

PostgreSQL JSONB includes key-existence operators where `?` is a SQL operator. Yet JDBC also uses `?` as the **parameter placeholder**.

~~~sql
SELECT payload ? 'customerId'
FROM events_json;
~~~

### 23.1. Conflict When Writing `PreparedStatement`

In PostgreSQL JDBC, when sending a literal `?` belonging to a PostgreSQL operator, the driver supports escaping `??` in `PreparedStatement` SQL where appropriate.

~~~java
String sql =
    "SELECT event_id FROM events_json WHERE payload ?? ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "customerId");
    // query...
}
~~~

The driver sends the JSONB key-existence operator and one parameter; the placeholder count seen by JDBC is one.

### 23.2. Function Syntax Alternative

When you want to avoid token conflicts and the API has an equivalent function, you can use supported SQL expressions such as `jsonb_exists(payload, ?)` for key-existence checks.

### 23.3. Do Not Escape Question Marks Arbitrarily

`??` is a pgJDBC-specific mechanism to distinguish an operator from a placeholder. Never replace normal parameter bind `?` placeholders with `??`, as that removes the bind slot.

### 23.4. Test the Actual SQL

When complex queries combine multiple JSON operators and parameters, write integration tests verifying placeholder counts and results instead of debugging by logging sensitive parameters.

## 24. PostgreSQL Arrays and `java.sql.Array`

PostgreSQL supports array types such as `text[]`, `integer[]`, `uuid[]`, and `numeric[]`.

~~~sql
SELECT ARRAY['java', 'jdbc', 'postgresql']::text[] AS tags;
~~~

### 24.1. `java.sql.Array` Is Not `java.util.List`

`ResultSet.getArray()` returns an object implementing JDBC `java.sql.Array`, from which you can extract a matching Java array or a `ResultSet` representing elements.

~~~java
java.sql.Array sqlArray = rs.getArray("tags");
if (sqlArray != null) {
    Object nativeArray = sqlArray.getArray();
    // For text[] and a compatible driver, usually String[].
}
~~~

### 24.2. Creating an Array Parameter

~~~java
String[] tags = {"jdbc", "postgresql"};
java.sql.Array array =
    connection.createArrayOf("text", tags);

try {
    ps.setArray(1, array);
    ps.executeUpdate();
} finally {
    array.free();
}
~~~

### 24.3. Element Type Names Must Be Accurate

For `uuid[]`, you can use element type `"uuid"`; for `int4[]`, use the PostgreSQL element type supported by the driver such as `"int4"` or `"integer"`. Do not pass the Java class name `"Integer"` assuming the server understands it.

### 24.4. NULL Array Differs From Empty Array

- SQL NULL: no array value.
- `ARRAY[]::text[]`: empty array.
- `ARRAY[NULL]::text[]`: single-element array containing NULL.

Do not convert all three into `Collections.emptyList()` if your contract needs to distinguish them.

## 25. Reading and Writing `ARRAY` Safely

### 25.1. Reading `text[]`

~~~java
java.sql.Array sqlArray = rs.getArray("tags");

List<String> tags;
if (sqlArray == null) {
    tags = null;
} else {
    try {
        String[] values = (String[]) sqlArray.getArray();
        tags = Arrays.asList(values);
    } finally {
        sqlArray.free();
    }
}
~~~

This snippet requires `import java.util.Arrays` and `import java.util.List`. Verify the exact element type returned by the driver; do not cast every kind of SQL `ARRAY` blindly to `String[]`.

### 25.2. For `integer[]`

~~~java
java.sql.Array sqlArray = rs.getArray("scores");
Integer[] scores = sqlArray == null
    ? null
    : (Integer[]) sqlArray.getArray();
~~~

In real code, free resources as needed and verify driver conversion. Avoid casting to `int[]` when elements can be NULL.

### 25.3. For `UUID[]`

You can create the array via:

~~~java
UUID[] ids = {UUID.randomUUID(), UUID.randomUUID()};
java.sql.Array dbIds = connection.createArrayOf("uuid", ids);
ps.setArray(1, dbIds);
~~~

Free `dbIds` after statement execution completes per supported lifecycle.

### 25.4. Multidimensional Arrays

PostgreSQL supports multidimensional arrays; Java may receive nested arrays from the driver. Test shapes, dimensions, and NULL elements. Never assume `java.sql.Array.getArray()` always returns a one-dimensional array.

### 25.5. PostgreSQL Array Lower Bounds

PostgreSQL arrays can have lower bounds not starting at 1. When converted to Java arrays (0-based), lower-bound metadata is not automatically preserved. If business logic depends on original SQL subscripts, inspect `array_lower`/`array_dims` or query elements in SQL.

## 26. `BYTEA` ↔ `byte[]`

The `bytea` type stores byte sequences, unlike `text` which stores character strings.

~~~sql
CREATE TABLE attachments_small (
    id BIGINT PRIMARY KEY,
    content BYTEA
);
~~~

Java:

~~~java
byte[] bytes = rs.getBytes("content");
ps.setBytes(1, bytes);
~~~

### 26.1. Use `BYTEA` for Binary Data

Bytes from images, small files, hash digests, or encrypted payloads are not Unicode text. Never construct a `String` from arbitrary bytes and store it in `text` without an explicit encoding.

### 26.2. Writing via Stream

~~~java
try (InputStream input = Files.newInputStream(path)) {
    ps.setBinaryStream(1, input);
    ps.executeUpdate();
}
~~~

This pattern requires `java.io.InputStream`, `java.nio.file.Files`, and `Path`. The stream's lifetime must cover statement execution.

### 26.3. Reading via Stream

~~~java
try (InputStream input = rs.getBinaryStream("content")) {
    if (input != null) {
        // Read in chunks to avoid holding large payloads in RAM.
    }
}
~~~

### 26.4. `BYTEA` Is Not Equivalent to PostgreSQL's Large Object API

PostgreSQL has a separate Large Objects facility, typically referenced via OIDs and driver-specific APIs. Do not call `getBytes()` on an OID expecting the driver to fetch the entire large object. When using Large Objects, manage transactions, permissions, cleanup lifecycles, and backup strategies properly.

### 26.5. Storage Size Trade-Offs

Storing large files inside the database introduces trade-offs for WAL, backups, replication, bloat, and latency. In some cases, storing blobs in object storage and metadata in PostgreSQL is preferable, provided data consistency and deletion/retention workflows are addressed.

## 27. `BIT` and `VARBIT` Types

PostgreSQL:

~~~sql
SELECT B'1010'::bit(4) AS feature_flags;
SELECT B'101001'::varbit AS variable_flags;
~~~

### 27.1. Do Not Equate `bit(1)` With `boolean`

`bit(1)` is a one-bit string, whereas `boolean` is logical `TRUE`/`FALSE`/`NULL`. Some driver conversions may yield close values, yet schema semantics differ.

### 27.2. Reading Bit String Types

For bit strings, you can read the string representation via `getString()` depending on type, or use another mapping supported by the driver. Inspect the exact output of `getObject()` and `getColumnType()` on your current driver.

### 27.3. Do Not Overuse Bitfields

If flags have independent business meanings and need frequent querying, indexing, or constraints, separate `boolean` columns or another structure are often easier to maintain than an opaque bit string.

### 27.4. Passing Parameters

Use explicit PostgreSQL casts and conversions as needed, rather than assuming `setBoolean()` can write arbitrary-length bit strings.

## 28. `INTERVAL`, `Duration`, and `Period` Are Not Equivalent

PostgreSQL has the `interval` type to represent durations that can combine **months, days, and hours/minutes/seconds**:

~~~sql
SELECT INTERVAL '2 months 3 days 04:05:06' AS elapsed;
~~~

A common read approach with the PostgreSQL JDBC driver:

~~~java
Object raw = rs.getObject("elapsed");
if (raw instanceof org.postgresql.util.PGInterval) {
    org.postgresql.util.PGInterval interval =
        (org.postgresql.util.PGInterval) raw;

    int years = interval.getYears();
    int months = interval.getMonths();
    int days = interval.getDays();
    int hours = interval.getHours();
    double seconds = interval.getSeconds();
}
~~~

### 28.1. `PGInterval` Is a pgJDBC-Specific Class

`PGInterval` does not belong to `java.sql`. If you want to keep service layers decoupled from the driver, translate it into a domain model capturing both calendar and time components.

### 28.2. `Duration` Cannot Represent Calendar Months

`java.time.Duration` is strictly based on seconds/nanoseconds. A month can be 28, 29, 30, or 31 days. Never turn `interval '1 month'` into `Duration.ofDays(30)` when business logic truly means "add one calendar month".

### 28.3. `Period` Does Not Hold Time of Day Either

`java.time.Period` holds years/months/days without hours/minutes/seconds. A PostgreSQL `interval` can combine both calendar and time-of-day components, so it does not always map losslessly to a single `Period` or `Duration`.

### 28.4. Writing Intervals via Cast or Driver Extension

~~~sql
INSERT INTO timing_events(elapsed)
VALUES (?::interval);
~~~

~~~java
ps.setString(1, "2 months 3 days 04:05:06");
~~~

This example uses validated text input for the server to parse as an interval. You can also use `PGInterval` when supported by the API/driver. For lock durations or TTLs, define unambiguous units before storing.

### 28.5. A Calendar Day Differs From 24 Hours Under DST

If you "add one calendar day" in a time zone with daylight saving time, the resulting instant may be 23 or 25 hours from the start instant. Never silently convert calendar periods into fixed `Duration`s.

## 29. PostgreSQL `ENUM` and Java `enum`

PostgreSQL lets you declare an enum set of labels:

~~~sql
CREATE TYPE workflow_state AS ENUM (
    'new', 'processing', 'completed', 'failed'
);
~~~

Java:

~~~java
enum WorkflowState {
    NEW, PROCESSING, COMPLETED, FAILED
}
~~~

### 29.1. Labels Do Not Have to Match Constant Names

PostgreSQL enum labels can be lowercase, contain spaces, or use arbitrary naming; Java enum identifiers follow different rules. Use an explicit converter:

~~~java
static WorkflowState parseDbState(String dbLabel) {
    if (dbLabel == null) {
        return null;
    }
    return switch (dbLabel) {
        case "new" -> WorkflowState.NEW;
        case "processing" -> WorkflowState.PROCESSING;
        case "completed" -> WorkflowState.COMPLETED;
        case "failed" -> WorkflowState.FAILED;
        default -> throw new IllegalArgumentException(
            "Unknown DB workflow state"
        );
    };
}
~~~

This switch expression uses Java 14+; on older Java versions, use a standard switch statement.

### 29.2. Reading Enums Commonly via `getString`

~~~java
String label = rs.getString("state");
WorkflowState state = parseDbState(label);
~~~

### 29.3. Writing Enums With Explicit Cast

~~~sql
UPDATE workflows
SET state = ?::workflow_state
WHERE workflow_id = ?;
~~~

~~~java
ps.setString(1, "completed");
ps.setLong(2, 101L);
~~~

You can use `PGobject` with the PostgreSQL type name, though an explicit cast keeps the SQL readable.

### 29.4. Adding an Enum Label Can Break Java Code

When the database adds a `'paused'` label, applications using `Enum.valueOf` or old exhaustive converters can fail. That is a contract-versioning issue even though the column keeps the same PostgreSQL enum type.

### 29.5. Do Not Unconditionally Replace `text` With `ENUM`

`ENUM` fits stable sets of states. If values change frequently, a lookup table with a foreign key or `text` with a `CHECK` constraint can offer more flexible administration depending on the use case.

## 30. Network Types: `INET`, `CIDR`, and `MACADDR`

PostgreSQL provides network types:

~~~sql
SELECT INET '192.0.2.45' AS client_ip;
SELECT CIDR '192.0.2.0/24' AS network_block;
~~~

A simple approach is reading as text:

~~~java
String ip = rs.getString("client_ip");
~~~

### 30.1. Why Not Use `InetAddress` for All Types?

`java.net.InetAddress` represents an IP address, yet does not inherently carry a CIDR prefix length. If subnet semantics are needed, define a domain type holding both address and prefix.

### 30.2. Writing Typed `INET`

~~~sql
INSERT INTO access_logs(client_ip) VALUES (?::inet);
~~~

~~~java
ps.setString(1, "192.0.2.46");
~~~

### 30.3. Do Not Confuse Parsing With IP Origin Verification

An IP stored in a table might come from a client-supplied HTTP header; storing it as `INET` does not verify the remote peer or prevent proxy-header spoofing.

### 30.4. Specific Mapping Classes

Depending on pgJDBC version, `getObject` may return `PGobject` or an extension class for certain PostgreSQL-specific types. If used, test the returned runtime class and converter.

## 31. PostgreSQL `Range` and `Multirange`

PostgreSQL supports range types such as:

~~~sql
SELECT int4range(1, 10, '[)') AS valid_numbers;

SELECT tstzrange(
    TIMESTAMPTZ '2026-11-14 10:00+07',
    TIMESTAMPTZ '2026-11-14 11:00+07',
    '[)'
) AS booking_window;
~~~

### 31.1. A Range Is More Than Two Bound Values

It also encodes:

- Inclusive or exclusive bounds.
- Unbounded endpoints.
- Empty ranges.
- Subtype canonicalization rules.
- Containment, intersection, and overlap operations over the domain.

### 31.2. A Java Start/End Pair Can Lose Meaning

For range `[1,10)`, storing only the two numbers 1 and 10 does not tell you whether 10 is included. Empty and unbounded ranges also need dedicated states.

### 31.3. Drivers Lack One Standard Java `Range` Type for All Cases

You may need `PGobject` or to read the string and parse it with a converter that understands PostgreSQL range grammar; never naively split the string on commas.

### 31.4. Let PostgreSQL Perform Range Operations When Appropriate

If the goal is finding overlapping booking windows, use appropriate SQL operators and indexes instead of loading all ranges into Java to compare manually.

## 32. `XML` and `SQLXML`

PostgreSQL has an `xml` type. JDBC provides the `java.sql.SQLXML` interface in supporting drivers.

~~~java
SQLXML xml = rs.getSQLXML("document_xml");
if (xml != null) {
    try {
        String xmlText = xml.getString();
        // Safely parse XML after reading.
    } finally {
        xml.free();
    }
}
~~~

### 32.1. Release Resources

Call `SQLXML.free()` when finished, per driver lifecycle rules.

### 32.2. Prevent XXE

When parsing XML text into Java DOM/SAX/StAX, configure protection against XML External Entities (XXE) and unauthorized network resource fetches. Storing XML in PostgreSQL does not make the Java parser safe automatically.

### 32.3. The `xml` Type Does Not Guarantee Full Business Validity

Validity against application schemas, namespaces, and content rules must still be checked separately if required by the domain.

## 33. `MONEY` and Currency Units

PostgreSQL has a `money` type, yet it is locale- and format-sensitive. For most business systems needing exact calculation, it is easier to control with:

~~~sql
amount NUMERIC(18,2) NOT NULL,
currency_code CHAR(3) NOT NULL
~~~

Java:

~~~java
BigDecimal amount = rs.getBigDecimal("amount");
String currency = rs.getString("currency_code");
~~~

### 33.1. `BigDecimal` Does Not Carry Currency

`100.00` does not say whether the unit is VND or USD. Pair it with a currency code or a `Money` domain object.

### 33.2. Other Systems May Use Minor Units

Storing `BIGINT` counts of cents/smallest currency units is also reasonable given a clear currency/scale contract, overflow handling, and multi-currency support.

### 33.3. Never Change `NUMERIC` to `DOUBLE` Just to Simplify a Mapper

That can be a breaking semantic change due to precision loss, regardless of whether the Java mapper compiles.

## 34. JDBC Metadata to Verify Actual Types

Never guess mappings for a complex query. JDBC provides `ResultSetMetaData`:

~~~java
ResultSetMetaData md = rs.getMetaData();

for (int i = 1; i <= md.getColumnCount(); i++) {
    System.out.printf(
        "%s | JDBC type=%d | SQL type=%s | Java=%s%n",
        md.getColumnLabel(i),
        md.getColumnType(i),
        md.getColumnTypeName(i),
        md.getColumnClassName(i)
    );
}
~~~

### 34.1. `getColumnType` Is Not the PostgreSQL OID

This value comes from `java.sql.Types`. PostgreSQL-specific types may be reported as `Types.OTHER`.

### 34.2. `getColumnTypeName` Reveals the Type Name

It may return `jsonb`, `uuid`, an enum name, or a PostgreSQL array type name depending on the driver. Use it for diagnostics rather than treating it as a default domain class.

### 34.3. Precision, Scale, Nullable

~~~java
int precision = md.getPrecision(i);
int scale = md.getScale(i);
int nullableFlag = md.isNullable(i);
~~~

For complex expressions and views, metadata does not always guarantee every business invariant regarding nullability.

### 34.4. Still Restrict Metadata Logging

Metadata can reveal internal schema names; never dump an entire `ResultSet` containing personal data or tokens just to inspect types.

## 35. Cross-Checking PostgreSQL `information_schema`

~~~sql
SELECT
    column_name,
    data_type,
    udt_schema,
    udt_name,
    character_maximum_length,
    numeric_precision,
    numeric_scale,
    datetime_precision,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'jdbc_types_lab'
  AND table_name = 'events'
ORDER BY ordinal_position;
~~~

### 35.1. `udt_name` Is Useful for Arrays and Enums

A PostgreSQL array may show `data_type='ARRAY'` with its internal representation in `udt_name`. A PostgreSQL enum may show `USER-DEFINED` with the enum name in `udt_name`.

### 35.2. Do Not Confuse `getString` Compatibility With a `text` Schema

Many types have a text representation. Being readable via `String` does not mean a column can be turned into `TEXT` without changing semantics.

### 35.3. Schema-Qualified Casting

If two schemas both define an enum named `status`, an unqualified cast can resolve via `search_path` to the wrong type. In migrations and critical prepared SQL, use schema-qualified type names.

## 36. Lab: Creating a Practice Table With Diverse Data Types

Run this lab only in a **test** database, never in production. If schema `jdbc_types_lab` already exists, use another name instead of overwriting someone else's data.

~~~sql
CREATE SCHEMA jdbc_types_lab;

CREATE TYPE jdbc_types_lab.event_state AS ENUM (
    'new', 'processed', 'failed'
);

CREATE TABLE jdbc_types_lab.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_id UUID NOT NULL UNIQUE,
    owner_name TEXT NOT NULL,
    note VARCHAR(200),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    attempts INTEGER,
    total_amount NUMERIC(18,4) NOT NULL
        CHECK (total_amount >= 0),
    confidence DOUBLE PRECISION,
    event_day DATE NOT NULL,
    local_time TIME WITHOUT TIME ZONE,
    local_deadline TIMESTAMP WITHOUT TIME ZONE,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    duration INTERVAL,
    payload JSONB,
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::text[],
    data BYTEA,
    source_ip INET,
    state jdbc_types_lab.event_state NOT NULL
        DEFAULT 'new'
);
~~~

### 36.1. Why Choose Explicit Data Types?

PostgreSQL can validate UUIDs, parse JSONB, enforce NUMERIC bounds, and apply INET operators and date/time rules per type. If everything is stored as `TEXT`, the application must re-implement many constraints and risks bad data.

### 36.2. Columns Allowing NULL

`note`, `attempts`, `duration`, `payload`, and several other fields allow NULL to test mappers. `active`, `total_amount`, `event_day`, `occurred_at`, and `tags` have `NOT NULL` per schema.

### 36.3. `event_day` Does Not Always Equal the UTC Date of `occurred_at`

If `event_day` is a business date in Vietnam, it can differ from the UTC calendar date of the exact same instant. This is a domain contract, not something to infer from column names alone.

## 37. Lab: `INSERT` From SQL to Create Fixture Data

~~~sql
INSERT INTO jdbc_types_lab.events (
    external_id, owner_name, note, active, attempts,
    total_amount, confidence, event_day, local_time,
    local_deadline, occurred_at, duration, payload,
    tags, data, source_ip, state
)
VALUES (
    UUID '550e8400-e29b-41d4-a716-446655440000',
    'Nguyen An',
    NULL,
    TRUE,
    NULL,
    1234.5600,
    0.98,
    DATE '2026-11-14',
    TIME '09:30:00.123456',
    TIMESTAMP '2026-11-14 09:30:00',
    TIMESTAMPTZ '2026-11-14 09:30:00+07',
    INTERVAL '1 month 2 days 03:04:05',
    '{"source":"jdbc-lab","attempt":null}'::jsonb,
    ARRAY['jdbc','postgresql']::text[],
    decode('DEADBEEF', 'hex'),
    INET '192.0.2.45',
    'new'
)
RETURNING event_id;
~~~

### 37.1. Verify the Data

~~~sql
SELECT
    event_id, external_id, owner_name, attempts,
    total_amount, occurred_at, tags, state
FROM jdbc_types_lab.events
ORDER BY event_id;
~~~

### 37.2. Verify Types on the Server

~~~sql
SELECT
    pg_typeof(external_id),
    pg_typeof(total_amount),
    pg_typeof(occurred_at),
    pg_typeof(payload),
    pg_typeof(tags),
    pg_typeof(state)
FROM jdbc_types_lab.events
LIMIT 1;
~~~

### 37.3. Verify Precision and Byte Sizes

~~~sql
SELECT
    total_amount,
    octet_length(data) AS binary_size,
    cardinality(tags) AS num_tags
FROM jdbc_types_lab.events;
~~~

### 37.4. Do Not Claim the Input Offset Is Preserved

`TIMESTAMPTZ` stores an instant. How PostgreSQL formats it depends on the session `TimeZone`, without recording whether the input used `+07` or a particular `ZoneId`.

## 38. Lab: Java DTO Using Proper Types

A DTO can use a Java `record` (Java 16+):

~~~java
import java.math.BigDecimal;
import java.time.*;
import java.util.*;

record EventRow(
    long eventId,
    UUID externalId,
    String ownerName,
    String note,
    boolean active,
    Integer attempts,
    BigDecimal totalAmount,
    Double confidence,
    LocalDate eventDay,
    LocalTime localTime,
    LocalDateTime localDeadline,
    OffsetDateTime occurredAt,
    String payloadJson,
    List<String> tags,
    byte[] data,
    String sourceIp,
    String state
) {}
~~~

### 38.1. Use Wrapper Types for Nullable Columns

`attempts` and `confidence` can be NULL, so they use `Integer`/`Double`. `active` is `NOT NULL`, so primitive `boolean` is appropriate.

### 38.2. Separate `JSONB` Parsing

This example keeps `payload` as a `String`. A separate converter can use Jackson to parse it into a DTO. Do not assume pgJDBC deserializes it automatically.

### 38.3. Converters for Enums

At the initial mapping layer, `state` is a `String`. The business layer can convert it to a Java enum with an explicit converter, handling unknown labels cleanly when the schema evolves.

### 38.4. Record `toString` Can Leak Data

For records containing JSON, PII, or `byte[]`, never log the raw record to observability systems if sensitive data is present.

## 39. Lab: `ResultSet` Mapper

~~~java
import java.sql.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;

static EventRow mapEvent(ResultSet rs) throws SQLException {
    long id = rs.getLong("event_id");
    UUID externalId = rs.getObject("external_id", UUID.class);
    String ownerName = rs.getString("owner_name");
    String note = rs.getString("note");
    boolean active = rs.getBoolean("active");

    int n = rs.getInt("attempts");
    Integer attempts = rs.wasNull() ? null : n;

    BigDecimal amount = rs.getBigDecimal("total_amount");

    double c = rs.getDouble("confidence");
    Double confidence = rs.wasNull() ? null : c;

    LocalDate eventDay =
        rs.getObject("event_day", LocalDate.class);
    LocalTime localTime =
        rs.getObject("local_time", LocalTime.class);
    LocalDateTime localDeadline =
        rs.getObject("local_deadline", LocalDateTime.class);
    OffsetDateTime occurredAt =
        rs.getObject("occurred_at", OffsetDateTime.class);

    String payload = rs.getString("payload");

    Array sqlTags = rs.getArray("tags");
    List<String> tags = null;
    if (sqlTags != null) {
        try {
            tags = Arrays.asList((String[]) sqlTags.getArray());
        } finally {
            sqlTags.free();
        }
    }

    byte[] data = rs.getBytes("data");
    String sourceIp = rs.getString("source_ip");
    String state = rs.getString("state");

    return new EventRow(
        id, externalId, ownerName, note, active, attempts,
        amount, confidence, eventDay, localTime,
        localDeadline, occurredAt, payload, tags,
        data, sourceIp, state
    );
}
~~~

### 39.1. Call `wasNull()` Immediately After the Primitive Getter

If you call another getter before `rs.wasNull()`, the NULL indicator shifts to the new column. This is a very common mapping bug.

### 39.2. Free Resources Promptly

The SQL `Array` is freed right after extracting the Java `String[]`. If the driver, type, or shape differs, adapt the converter and cover it with integration tests.

### 39.3. The Mapper Is Not Responsible for Committing

A mapper reads one row; transactions, pagination, and resource lifetimes belong to the calling layer.

### 39.4. Typed `getObject` Requires Driver Support

This snippet assumes pgJDBC supports typed getters for `UUID`/`LocalDate`/`LocalTime`/`LocalDateTime`/`OffsetDateTime`. On older drivers lacking support, upgrade or use a tested converter.

## 40. Lab: `SELECT` Using `PreparedStatement`

~~~java
import java.sql.*;
import java.time.OffsetDateTime;

static void printEvents(Connection connection)
        throws SQLException {
    String sql = """
        SELECT event_id, external_id, owner_name, note,
               active, attempts, total_amount, confidence,
               event_day, local_time, local_deadline,
               occurred_at, payload, tags, data, source_ip, state
        FROM jdbc_types_lab.events
        WHERE occurred_at >= ?
        ORDER BY occurred_at, event_id
        """;

    try (PreparedStatement ps =
             connection.prepareStatement(sql)) {
        ps.setObject(
            1,
            OffsetDateTime.parse("2026-11-01T00:00:00Z")
        );

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                EventRow row = mapEvent(rs);
                System.out.println(row.eventId());
            }
        }
    }
}
~~~

### 40.1. Java Text Blocks

The `"""` delimiter requires Java 15+. On Java 8/11, write the `String` using classic concatenation.

### 40.2. Explicit Projection

Select only the columns you actually need; avoid `SELECT *` in long-lived APIs due to schema evolution.

### 40.3. Parameterize Timestamps

`ps.setObject(OffsetDateTime)` preserves instant semantics better than concatenating user timestamp strings into SQL.

### 40.4. Do Not Log Sensitive Data

Log only policy-compliant metadata/IDs; never print JSON payloads or full rows that might contain personal information.

## 41. Lab: `INSERT` With Multiple JDBC Types

Using `INSERT ... RETURNING event_id`:

~~~java
import java.sql.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.UUID;

static long insertEvent(
    Connection connection,
    String payloadJson
) throws SQLException {
    String sql = """
        INSERT INTO jdbc_types_lab.events (
            external_id, owner_name, active, attempts,
            total_amount, confidence, event_day, local_time,
            local_deadline, occurred_at, duration, payload,
            tags, data, source_ip, state
        )
        VALUES (
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?::interval, ?::jsonb,
            ?, ?, ?::inet, ?::jdbc_types_lab.event_state
        )
        RETURNING event_id
        """;

    try (PreparedStatement ps =
             connection.prepareStatement(sql)) {
        ps.setObject(1, UUID.randomUUID());
        ps.setString(2, "Tran Binh");
        ps.setBoolean(3, true);
        ps.setNull(4, Types.INTEGER);
        ps.setBigDecimal(5, new BigDecimal("75.1250"));
        ps.setDouble(6, 0.875);
        ps.setObject(7, LocalDate.of(2026, 11, 14));
        ps.setObject(8, LocalTime.of(9, 30));
        ps.setObject(
            9, LocalDateTime.of(2026, 11, 14, 9, 30)
        );
        ps.setObject(
            10,
            OffsetDateTime.parse("2026-11-14T09:30:00+07:00")
        );
        ps.setString(11, "2 days 3 hours");
        ps.setString(12, payloadJson);

        Array tags = connection.createArrayOf(
            "text", new String[] {"java", "jdbc", "jsonb"}
        );

        try {
            ps.setArray(13, tags);
            ps.setBytes(
                14,
                new byte[] {(byte) 0xDE, (byte) 0xAD}
            );
            ps.setString(15, "192.0.2.46");
            ps.setString(16, "new");

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException(
                        "INSERT RETURNING returned no ID"
                    );
                }
                return rs.getLong(1);
            }
        } finally {
            tags.free();
        }
    }
}
~~~

### 41.1. Counting Parameters

The SQL statement has 16 placeholders and `PreparedStatement` binds positions 1 through 16. Misaligned parameter positions easily cause cast errors or write into the wrong column.

### 41.2. `Types.INTEGER` for NULL

`ps.setNull(4, Types.INTEGER)` writes a typed SQL NULL, unlike `ps.setInt(4, 0)`.

### 41.3. Writing JSONB/Interval/Network/Enum via Casts

Text parameters are explicitly cast to the target PostgreSQL types at the exact bind positions, rather than concatenating SQL literals from user input.

### 41.4. SQL `Array` Lifecycle

`createArrayOf` creates the array parameter; `free()` is called after the statement finishes executing.

### 41.5. The Caller Owns the Transaction

The helper does not commit or rollback the passed `Connection`. The service layer can compose multiple DML operations inside one transaction.

## 42. `RETURNING` and `getGeneratedKeys`

A familiar PostgreSQL pattern is:

~~~sql
INSERT INTO orders(customer_id, total)
VALUES (?, ?)
RETURNING order_id;
~~~

In JDBC, use `executeQuery()` and read the `ResultSet`. Another option is `getGeneratedKeys()`:

~~~java
String sql = """
    INSERT INTO orders(customer_id, total)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(
        sql, new String[] {"order_id"})) {
    ps.setLong(1, customerId);
    ps.setBigDecimal(2, total);
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long id = keys.getLong(1);
        }
    }
}
~~~

### 42.1. Do Not Use `MAX(id)`

Running `SELECT MAX(id)` after an `INSERT` does not guarantee returning the ID of the row you just inserted when concurrent transactions run.

### 42.2. Generated Identity Has No Separate Java Type

A `BIGINT IDENTITY` column is still read as `long`/`Long`.

### 42.3. Batch Inserts Require Checking Driver Behavior

`RETURNING`/`getGeneratedKeys` behavior with batches, upserts, and multi-row inserts can vary from generic API assumptions. Write integration tests for the exact SQL being deployed.

## 43. Writing Properly Typed `NULL`

~~~java
ps.setNull(1, Types.INTEGER);
ps.setNull(2, Types.NUMERIC);
ps.setNull(3, Types.TIMESTAMP_WITH_TIMEZONE);
ps.setNull(4, Types.VARCHAR);
~~~

### 43.1. `setObject(index, null)` Is Not Always Enough

If PostgreSQL cannot infer the type of a NULL placeholder inside an expression, the SQL statement can fail. Use `setNull` with a JDBC type or an explicit SQL cast.

### 43.2. SQL NULL for `JSONB`

~~~sql
UPDATE jdbc_types_lab.events
SET payload = ?::jsonb
WHERE event_id = ?;
~~~

~~~java
ps.setNull(1, Types.OTHER);
ps.setLong(2, eventId);
~~~

### 43.3. JSON Literal `null`

~~~java
ps.setString(1, "null");
~~~

When using `?::jsonb`, this stores a JSON `null` inside a non-NULL SQL value. Never confuse it with `setNull`.

### 43.4. NULL Array Differs From Empty Array

A `NOT NULL` column forbids SQL NULL, yet still permits an empty array. The error message belongs to a schema constraint, not a JDBC `Array` bug.

## 44. SQL Casts and Typed Parameters

~~~sql
SELECT ?::uuid;
SELECT ?::jsonb;
SELECT ?::inet;
SELECT ?::date;
SELECT ?::jdbc_types_lab.event_state;
~~~

### 44.1. Cast Parameters Instead of Concatenating User SQL

SQL string concatenation with input data creates injection and escaping risks. Use `PreparedStatement` and SQL casts when needed.

### 44.2. Never Pass Identifiers Through Placeholders

Table, schema, or enum type names are not value parameters. For dynamic SQL, use an allowlist of valid names and quote identifiers properly.

### 44.3. Casts on Columns Can Affect Indexes

If you wrap an indexed column in an unnecessary function/cast inside `WHERE`, the planner may be unable to use the existing index. Generally bind the properly typed value on the parameter side instead.

### 44.4. Date/Time Casts Are Not Cosmetic

`timestamp` and `timestamptz` have different semantics when inputs have offsets or session time zones apply. Choose types and casts according to the domain contract, not merely whatever makes the SQL compile.

## 45. Deserializing JSON Into Domain Objects

A library like Jackson can transform the JSONB string read via JDBC into a domain object or JSON tree. This is an **application step**, not an automatic feature of `getObject()`.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

String jsonText = rs.getString("payload");
JsonNode json = jsonText == null
    ? null
    : mapper.readTree(jsonText);
~~~

Declare the Jackson dependency and handle its checked exceptions properly.

### 45.1. Three Kinds of "No Data"

- SQL NULL in a `JSONB` column → Java `null` from `getString`.
- JSON literal `null` → string `"null"` when reading JSON text.
- JSON object missing a key → the object exists, yet lacks that member.

Collapsing all three into Java `null` loses information in business logic.

### 45.2. Validation

PostgreSQL verifies that `JSONB` has valid JSON syntax; the application must still enforce business validation such as field types, versions, permissions, and constraints.

### 45.3. Payload Versioning

Consider including a `schema_version` or event type field. When producers add fields, Java consumers need an appropriate unknown-field policy.

### 45.4. Do Not Log Raw JSON

Payloads may contain PII or tokens; avoid logging `JsonNode.toString()` or serialized DTOs in real environments.

## 46. Driver Version, Java Version, and Protocol

### 46.1. pgJDBC Is a PostgreSQL-Specific Driver

`PGobject`, `PGInterval`, and JSONB operator escaping are not universal across all JDBC drivers.

### 46.2. Java Syntax in Examples

`java.time` arrived in Java 8; text blocks `"""` arrived in Java 15; Java `record`s stabilized in Java 16; switch expressions belong to newer Java releases. If your project targets Java 8/11, adjust syntax without changing data-type semantics.

### 46.3. Binary vs. Text Transfer

The PostgreSQL protocol/driver may transfer types in binary or text format depending on configuration and type. Mappers must preserve identical meaning regardless of transfer mode.

### 46.4. Do Not Parse Timestamps From `String` When Typed Getters Exist

Display formatting is subject to `TimeZone`/session settings, whereas typed getters reduce implicit conversions.

### 46.5. Driver Upgrades Require Testing

Specialized conversions for enums, arrays, JSONB, ranges, and date/time types are sensitive to driver changes. Pin versions and run integration tests on upgrade.

## 47. Connections, Transactions, and Fetch Size

~~~java
try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
         "SELECT event_id, total_amount, occurred_at "
       + "FROM jdbc_types_lab.events"
     );
     ResultSet rs = ps.executeQuery()) {

    while (rs.next()) {
        long id = rs.getLong("event_id");
        BigDecimal amount = rs.getBigDecimal("total_amount");
        OffsetDateTime occurredAt =
            rs.getObject("occurred_at", OffsetDateTime.class);
    }
}
~~~

### 47.1. try-with-resources

Close `ResultSet`, `PreparedStatement`, and `Connection` following their lifecycle. With a connection pool, `Connection.close()` normally returns the connection to the pool rather than closing the physical socket.

### 47.2. Fetch Size in pgJDBC

~~~java
conn.setAutoCommit(false);

try (PreparedStatement ps = conn.prepareStatement(
        "SELECT event_id, payload FROM jdbc_types_lab.events")) {
    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Process sequentially instead of loading everything into a List.
        }
    }
}

conn.commit();
~~~

Cursor-based fetching in pgJDBC requires specific conditions such as auto-commit disabled and an appropriate `ResultSet` type. Verify against your deployed driver.

### 47.3. Do Not Hold Transactions Open Indefinitely

A large streaming query can hold server snapshots and resources for a long time; consider batching, `COPY`, or keyset pagination.

### 47.4. Fetch Size Does Not Fix Missing Indexes

It changes how rows are fetched to the client, not the cost of server-side JOINs or sorts.

### 47.5. SQL `Array` and Stream Resources

Read needed data and release `Array`/stream handles promptly; never let a DTO hold references tied to a closed `ResultSet`.

## 48. Mapping Performance

### 48.1. Large `BYTEA`

`getBytes()` materializes a byte array on the heap; for large payloads, use streams and size limits or consider object storage.

### 48.2. Large `JSONB`

Do not fetch millions of payloads just so Java can filter a single field. PostgreSQL JSON operators and indexes can filter before crossing the network.

### 48.3. `BigDecimal` vs. `double`

`BigDecimal` has overhead, yet is right for money. Never switch to `double` to "optimize" when exact decimal arithmetic is required.

### 48.4. Large `ARRAY`

Multidimensional or huge arrays allocate many Java objects. When aggregating or filtering over sets, evaluate server-side SQL operations.

### 48.5. `SELECT` Only Required Columns

`SELECT *` may transfer unneeded `JSONB`/`BYTEA` columns, inflating network, GC, and serialization costs.

## 49. Security at the JDBC Boundary

### 49.1. Never Concatenate User Input Into SQL

~~~java
// UNSAFE:
String sql = "SELECT * FROM events WHERE owner_name = '"
           + userInput + "'";
~~~

Use `PreparedStatement` to bind values and enforce types.

### 49.2. Placeholders Are Not for Identifiers

Schema, table, column, and enum type names are not value parameters. For dynamic SQL, allowlist and properly quote identifiers.

### 49.3. Database Permissions Still Matter

A clean mapper does not replace `GRANT`/`RLS`; the JDBC role must follow least privilege.

### 49.4. Log Redaction

Avoid logging raw JSON, tokens, binary secrets, connection passwords, or entire DTOs containing sensitive fields. A Java record's `toString()` can expose fields.

### 49.5. Input Bounds and Safe Rendering

PostgreSQL `JSONB`/`BYTEA` does not automatically protect Java or browsers from HTML injection, forged data, or malicious files. Validate and encode per context.

## 50. Schema Migrations and Java Types

| PostgreSQL Change | Java Risk |
|---|---|
| `integer → bigint` | `Integer` lacks range; switch to `Long` |
| `numeric → double precision` | Loses exact-decimal semantics |
| `timestamp → timestamptz` | Changes time semantics |
| `text → enum` | `String` parameter needs converter/cast |
| `text → jsonb` | Needs JSON parser and validation |
| `text[] → jsonb` | Changes data type, operators, and Java model |
| `NOT NULL` → nullable | Primitive mappers may misread NULL |
| Add enum label | Older Java converters may fail |
| Change `NUMERIC` scale | Rounding/precision shifts |
| Rename column | Getters by old name fail |
| Add column to `SELECT *` | Positional mapping may break |

### 50.1. Expand–Contract

For breaking changes, consider adding the new column, backfilling, migrating the application, and dropping the old column only after all consumers are ready.

### 50.2. Do Not Use `String` for Every Field to Dodge Migrations

That merely defers numeric precision, null/timezone, and validation bugs to runtime.

### 50.3. Rolling Deployments

Two versions of the app may run side by side. Database migrations must preserve compatibility for the older app's mappings during cutover.

### 50.4. Contract Tests

Include fixtures for large `BIGINT`, `NUMERIC` scale, SQL NULL, Unicode, DST/time zones, empty arrays, and new enum values.

## 51. Mapping Error Diagnostic Table

| Symptom | What to Check |
|---|---|
| SQL NULL turns into `0`/`false` | Primitive getter and `wasNull()` |
| Money off by digits | `double`/rounding/scale |
| Cannot read `BIGINT` | `getInt` instead of `getLong` |
| Wrong timestamp hours | Confusing `TIMESTAMP` and `TIMESTAMPTZ` |
| `+07` offset becomes `+00` | Instant is preserved, original offset is not |
| `getObject(..., Instant.class)` fails | Driver lacks typed getter support |
| `JSONB` type mismatch | Missing cast or `PGobject` |
| JSON `null` treated as SQL NULL | Converter conflated the two states |
| Enum rejects `String` | Cast to the proper PostgreSQL enum type |
| Array cast `ClassCastException` | Mismatched Java element type |
| `ARRAY` NULL becomes empty | Mapper lost null semantics |
| `INTERVAL '1 month'` treated as 30 days | Confusing calendar intervals with `Duration` |
| `BYTEA` Unicode errors | Forcing bytes into `String` |
| New enum label breaks Java | Converter does not handle unknown values |
| JSONB `?` operator breaks JDBC | Placeholder conflict; escape as `??` |
| Memory spikes reading rows | Fetching too much `JSONB`/`BYTEA` |
| `SELECT` permission denied | DB privileges, not a type conversion issue |
| Driver upgrade causes regression | Driver-specific conversion/metadata changes |

### 51.1. Distinguish Error Layers

`SQLSTATE` and server errors pinpoint casts/constraints; `ClassCastException` or JSON parser errors happen inside Java conversion.

### 51.2. Do Not Leak Data While Debugging

Use schema metadata and synthetic fixtures; avoid printing passwords, PII, or payloads with tokens into logs.

## 52. Practice Exercises

### Exercise 1 — Nullable `BIGINT`

Which Java type should be used?

**Answer:** `Long`.

### Exercise 2 — `wasNull`

After `getInt()`, why must `wasNull()` be called immediately?

**Hint:** `0` can represent SQL NULL; `wasNull` reflects the most recent getter.

### Exercise 3 — Nullable `BOOLEAN`

Why can `Boolean` be better than `boolean`?

**Hint:** Preserves three states: `TRUE`/`FALSE`/`NULL`.

### Exercise 4 — Money

Why use `BigDecimal` instead of `double`?

**Hint:** Exact decimal arithmetic.

### Exercise 5 — `BigDecimal` Constructor

Which is safer: `new BigDecimal("0.1")` or `new BigDecimal(0.1)`?

**Answer:** The `String` constructor.

### Exercise 6 — `equals` vs. `compareTo`

Why can `1.0` and `1.00` have `equals=false` yet `compareTo=0`?

**Hint:** Different scales.

### Exercise 7 — `REAL`

Java type for PostgreSQL `real`?

**Answer:** `Float`.

### Exercise 8 — `DOUBLE PRECISION`

Java type for PostgreSQL `double precision`?

**Answer:** `Double`.

### Exercise 9 — `DATE`

Java type for PostgreSQL `date` birth date?

**Answer:** `LocalDate`.

### Exercise 10 — `TIME`

Java type for `time without time zone`?

**Answer:** `LocalTime`.

### Exercise 11 — `TIMESTAMP`

Does `timestamp without time zone` identify an `Instant` on its own?

**Answer:** No.

### Exercise 12 — `TIMESTAMPTZ`

Which `java.time` type does pgJDBC commonly support?

**Answer:** `OffsetDateTime`.

### Exercise 13 — `Instant`

If `getObject(..., Instant.class)` is not supported, what should you do?

**Hint:** Read `OffsetDateTime` and call `.toInstant()`.

### Exercise 14 — `ZoneId`

Does PostgreSQL `timestamptz` store the zone name `Asia/Ho_Chi_Minh`?

**Answer:** No.

### Exercise 15 — DST

Why can a `LocalDateTime` have zero or two `Instant`s?

**Hint:** DST gap/overlap.

### Exercise 16 — Microseconds

Java supports nanoseconds; what resolution does PostgreSQL `timestamp` normally have?

**Answer:** Microsecond.

### Exercise 17 — `UUID`

Which getter is used for `UUID`?

**Hint:** `getObject("col", UUID.class)`.

### Exercise 18 — `JSONB`

Does JDBC automatically convert `JSONB` into a domain DTO?

**Answer:** No; a parser is required.

### Exercise 19 — `PGobject`

What information does `PGobject` carry?

**Hint:** PostgreSQL type name and value.

### Exercise 20 — JSON `null`

How does SQL NULL differ from `'null'::jsonb`?

**Hint:** Missing column value vs. JSON literal.

### Exercise 21 — `JSONB` Parameter

Why is `?::jsonb` or `PGobject` needed when writing?

**Hint:** A `String` parameter may be sent as `VARCHAR`/text.

### Exercise 22 — `JSONB` Question Mark

In a pgJDBC `PreparedStatement`, how can a `JSONB` operator `?` be written?

**Answer:** `??`.

### Exercise 23 — `ARRAY` Getter

Which JDBC API type is used to read `text[]`?

**Answer:** `java.sql.Array` via `getArray`.

### Exercise 24 — `ARRAY` Parameter

How do you create a `text[]` parameter?

**Hint:** `connection.createArrayOf("text", String[])`, `setArray`.

### Exercise 25 — Empty `ARRAY`

Are SQL NULL, `ARRAY[]`, and `ARRAY[NULL]` identical?

**Answer:** No.

### Exercise 26 — `BYTEA`

Common Java type?

**Answer:** `byte[]`.

### Exercise 27 — Large Object

Is an OID pointing to a Large Object the same as a `BYTEA` column?

**Answer:** No; it requires the appropriate API.

### Exercise 28 — `INTERVAL`

Is a calendar month always exactly 30 days?

**Answer:** No.

### Exercise 29 — `ENUM`

What is needed between Java enum `NEW` and PostgreSQL `'new'`?

**Hint:** Converter.

### Exercise 30 — `CIDR`

Does `InetAddress` hold the prefix length on its own?

**Answer:** No.

### Exercise 31 — Range

What is needed besides the two bounds to express a range?

**Hint:** Inclusive/exclusive, empty/unbounded.

### Exercise 32 — XML

Which risk must Java XML parsers guard against?

**Hint:** XXE.

### Exercise 33 — Metadata SQL Type

Which JDBC method returns the PostgreSQL type name?

**Answer:** `getColumnTypeName`.

### Exercise 34 — Type Code

Does `getColumnType` return a PostgreSQL OID or a `java.sql.Types` constant?

**Answer:** `java.sql.Types` constant.

### Exercise 35 — Enum Metadata

What `data_type` can `information_schema` report for an enum?

**Hint:** `USER-DEFINED` with `udt_name`.

### Exercise 36 — Null Parameter

When `setObject(index, null)` lacks type context, what should you do?

**Hint:** `setNull(index, Types.X)` or explicit cast.

### Exercise 37 — `RETURNING`

What is the safe way to retrieve an ID after `INSERT`?

**Answer:** `INSERT ... RETURNING` or `getGeneratedKeys`.

### Exercise 38 — `MAX(id)`

Why should you not use `SELECT MAX(id)` to get the row just inserted?

**Hint:** Concurrency.

### Exercise 39 — Unicode

Why do Java `String.length()` and PostgreSQL `char_length` differ?

**Hint:** UTF-16 code units vs. DB character count.

### Exercise 40 — Empty String

What does `getString` return for SQL NULL vs. `''`?

**Answer:** Java `null` and an empty string.

### Exercise 41 — Fetch Size

Does fetch size always make the SQL server execute faster?

**Answer:** No.

### Exercise 42 — Schema Migration

How does changing `INTEGER` to `BIGINT` affect a Java mapper?

**Hint:** `Integer` → `Long`.

### Exercise 43 — Nullable Boolean

What happens if a column becomes nullable while the mapper keeps primitive `boolean`?

**Hint:** Cannot distinguish `NULL` from `FALSE`.

### Exercise 44 — SQL Injection

Why must you not use string concatenation for SQL user input?

**Hint:** Injection/escaping.

### Exercise 45 — Complete Design

An application has `amount NUMERIC(18,2)`, `created_at TIMESTAMPTZ`, `delivery_date DATE`, `tags TEXT[]`, `payload JSONB`, `external_id UUID`, `status ENUM`, and nullable `note TEXT`. Choose Java types, getters/setters, null policy, and migration tests.

**Hint:** `BigDecimal`, `OffsetDateTime`/`Instant`, `LocalDate`, `java.sql.Array`/`List`, JSON converter, `UUID`, enum converter, nullable `String`; appropriate `PreparedStatement`/casts.

## 53. Implementation Checklist

### 53.1. Types and Domain

- [ ] Do `BIGINT`/`INTEGER`/`NUMERIC` match Java width and precision?
- [ ] Does money avoid passing through `double`?
- [ ] Is `NULL` kept distinct from `0`, `false`, empty string, and empty array?
- [ ] Do `DATE`/`TIME`/`TIMESTAMP`/`TIMESTAMPTZ` use the right `java.time` types?
- [ ] Are `ZoneId`/DST and resolution handled intentionally?
- [ ] Do `JSONB`/`ENUM`/`ARRAY`/`INTERVAL`/`INET` have converters?
- [ ] Could special values exceed the Java type's capabilities?

### 53.2. JDBC API

- [ ] Are typed getters supported by the driver version?
- [ ] Is `wasNull()` called right after primitive getters?
- [ ] Do `setNull`/casts provide the right types?
- [ ] Are parameter positions accurate?
- [ ] Is user input never concatenated into SQL?
- [ ] Are `ResultSet`/`Statement`/`Connection` closed?
- [ ] Are `Array`/`SQLXML`/streams freed appropriately?

### 53.3. Testing and Operations

- [ ] Integration tests against real PostgreSQL and pgJDBC?
- [ ] Tests for NULL, empty arrays, JSON null, Unicode, and `BigDecimal`?
- [ ] Tests for different time zones and DST gap/overlap?
- [ ] Tests for new enum labels and schema migrations?
- [ ] Do queries `SELECT` only needed columns?
- [ ] Are PII/tokens/secrets excluded from logs?
- [ ] Is there a rollback plan when changing type/nullability?

## 54. Quick Reference Table

| PostgreSQL | Java/JDBC | Key Reminder |
|---|---|---|
| `smallint` | `Short` | 16-bit signed |
| `integer` | `Integer` | NULL needs wrapper/`wasNull` |
| `bigint` | `Long` | 64-bit signed |
| `numeric` | `BigDecimal` | Exact decimal |
| `real` | `Float` | Approximate |
| `double precision` | `Double` | Approximate |
| `boolean` | `Boolean` | NULL differs from `FALSE` |
| `text/varchar` | `String` | Unicode/NULL |
| `date` | `LocalDate` | Calendar date |
| `time` | `LocalTime` | Time of day |
| `timestamp` | `LocalDateTime` | Local wall-clock |
| `timestamptz` | `OffsetDateTime` | Instant, does not retain `ZoneId` |
| `uuid` | `UUID` | `getObject`/`setObject` |
| `jsonb` | `String`/`PGobject`/JSON converter | SQL NULL differs from JSON `null` |
| `ARRAY` | `java.sql.Array` | `getArray`/`createArrayOf`/`free` |
| `bytea` | `byte[]`/stream | Differs from Large Object OID |
| `interval` | `PGInterval`/domain | Month differs from `Duration` |
| `enum` | `String` + converter | Cast when writing |
| `inet/cidr` | `String`/`PGobject` | Prefix semantics |
| Range/multirange | `PGobject`/domain | Inclusive/exclusive/empty |
| `xml` | `SQLXML` | `free`/parser security |
| `Types.OTHER` | JDBC metadata | PostgreSQL-specific |
| `wasNull()` | `ResultSet` | Immediately after primitive getter |
| `setNull` | `PreparedStatement` | Typed SQL NULL |
| `RETURNING` | PostgreSQL SQL | Fetch generated ID |
| `setFetchSize` | JDBC | Fetch/memory control when supported |

---

## 55. Conclusion

**Mapping PostgreSQL data to Java via JDBC is about preserving data meaning, not merely coercing types so code compiles.** `NUMERIC` and `BigDecimal` prevent monetary rounding errors; `BIGINT` needs Java `Long`; SQL `NULL` needs wrapper types or `wasNull()`; `UUID` should use `UUID`; `JSONB` needs a parser; `ARRAY` needs JDBC `Array`; and `INTERVAL`, `ENUM`, `INET`, and ranges may require converters or PostgreSQL-specific classes.

**Date and time are where severe subtle bugs happen:** `DATE` fits `LocalDate`, `TIME` fits `LocalTime`, `TIMESTAMP WITHOUT TIME ZONE` fits `LocalDateTime`, and `TIMESTAMPTZ` fits `OffsetDateTime` (converting to `Instant` when the domain only needs a point in time). `timestamptz` does not preserve the original `ZoneId`; DST and microsecond resolution must be accounted for in design.

Use `PreparedStatement`, typed getters/setters, properly typed `NULL`s and casts, inspect metadata when needed, and manage JDBC resources with try-with-resources. When the database schema evolves, test Java mappers, DTOs, enum converters, numeric precision, nullable fields, and rolling-deployed application versions together. The most important principle: **choose the right SQL types upfront, preserve semantics across JDBC, and convert into domain models only after explicitly handling NULL, precision, time, and PostgreSQL-specific types**.
