# Binding String, Numbers, Boolean, Date/Time, and byte[] to SQL Parameters with Spring JDBC

> **Learning objective:** Write proper SQL statements with placeholders, choose Java/JDBC types for **`String`, integers/decimals, `boolean`, `LocalDate`/`LocalTime`/`LocalDateTime`, and `byte[]`**, pass them via `PreparedStatement` or `JdbcTemplate`, handle typed `NULL`, verify readback data, and understand portability limits across JDBC drivers/databases.

Scope: **Spring Framework → Data Access → SQL Parameters**, focusing on JDBC and `JdbcTemplate`. Examples use Java 17+ and Spring Boot to provide a `DataSource`, though the binding mechanism belongs to JDBC/Spring JDBC; no JPA or Hibernate is needed.

## 1. What Does "Binding SQL Parameters" Actually Mean?

When running an SQL statement with input data, **do not concatenate values into the SQL string**. Instead, write an **SQL template** with `?` placeholders, then bind Java values to each position using `PreparedStatement`. The driver is responsible for transmitting values to the DB using the appropriate JDBC type.

```text
Java data:
  id = 101L
  label = "Spring JDBC"
  enabled = true
          |
          v
SQL template:
  INSERT INTO bind_demo (id, label, enabled)
  VALUES (?, ?, ?)
           1  2  3
          |
          v
PreparedStatement:
  setLong(1, 101L)
  setString(2, "Spring JDBC")
  setBoolean(3, true)
          |
          v
JDBC driver -> database
```

**Core principles:**

1. JDBC parameter positions **start at 1**, not 0. The first `?` corresponds to index 1.
2. Each `?` is for a **value**, not a table name, column name, SQL keyword, `ASC/DESC` direction, or arbitrary SQL fragment.
3. You must match the **count, order, and data types** of placeholders against the SQL schema.
4. Binding helps prevent **value-based SQL injection** because values are not parsed as SQL syntax. Dynamic table/column names still require an allowlist/trusted logic.
5. Binding does not automatically validate business rules: string length, numeric range, date format, timezone, and DB constraints still need handling.

**Wrong example:**

```java
String sql = "SELECT id FROM users WHERE email = '" + email + "'";
// Input with quotes or SQL payloads can break syntax/semantics.
```

**Right approach (snippet, assuming Connection and email variable already exist):**

```java
String sql = "SELECT id FROM users WHERE email = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("id");
            // Process id while ResultSet is still open.
        }
    }
}
```

`PreparedStatement` still needs to be closed via `try-with-resources`; `Connection` must also be returned according to its owner. With `JdbcTemplate`, Spring manages closing resources for each operation.

## 2. Common Type Mapping Table

| Java Type | Typical SQL Type | `PreparedStatement` setter | Common getter | Notes |
| --- | --- | --- | --- | --- |
| `String` | `VARCHAR`, `CHAR`, sometimes `NVARCHAR`/`CLOB` | `setString(i, value)`; national API has `setNString` when DB supports it | `getString` | Unicode/length/collation depend on DB |
| `byte`, `short`, `int` | `TINYINT`, `SMALLINT`, `INTEGER` | `setByte`, `setShort`, `setInt` | `getInt`/`getObject` | Check value range and NULL |
| `long` | `BIGINT` | `setLong` | `getLong` | Large IDs/sizes; 64-bit limit |
| `BigDecimal` | `DECIMAL(p,s)`, `NUMERIC(p,s)` | `setBigDecimal` | `getBigDecimal` | Usually preferred for money, preserves precision/scale |
| `float`, `double` | `REAL`, `FLOAT`/`DOUBLE` | `setFloat`, `setDouble` | `getDouble` | Binary approximation, does not replace exact money |
| `boolean` / `Boolean` | `BOOLEAN`, `BIT`, or DB-defined convention | `setBoolean`, `setObject`, or `setNull` | `getBoolean` + `wasNull` / `getObject` | `NULL` differs from `false` |
| `LocalDate` | `DATE` | `setObject(i, localDate)` (JDBC 4.2 + driver support), or `setDate(i, java.sql.Date.valueOf(localDate))` | `getObject(..., LocalDate.class)` or `getDate().toLocalDate()` | Date only, **no time/timezone** |
| `LocalTime` | `TIME` | `setObject` or `setTime(i, Time.valueOf(localTime))` | `getObject(..., LocalTime.class)` or `getTime().toLocalTime()` | No date/zone; watch precision |
| `LocalDateTime` | `TIMESTAMP` without time zone | `setObject` or `setTimestamp(i, Timestamp.valueOf(value))` | `getObject(..., LocalDateTime.class)` | A local calendar date-time, does not represent a UTC instant |
| `OffsetDateTime` | `TIMESTAMP WITH TIME ZONE` (if DB supports) | `setObject(i, value)`, or `setObject(i, value, JDBCType.TIMESTAMP_WITH_TIMEZONE)` | `getObject(..., OffsetDateTime.class)` | Offset/zone storage depends on DB |
| `byte[]` | `VARBINARY`/`BINARY` or `BLOB` | `setBytes(i, bytes)`; streams for large LOBs | `getBytes`, binary stream | Raw bytes, not hex/base64 text |

This table is a **guideline**, not a guarantee that every database maps identically. The SQL dialect and JDBC driver determine support, limits, implicit type conversions, precision, collation, LOBs, and timestamps. When portability matters, test against a real DB/driver.

## 3. String: Text Strings and Unicode

For SQL `VARCHAR`, the most common approach is:

```java
// Snippet inside a method that has PreparedStatement ps.
ps.setString(1, "Spring JDBC");
ps.setString(2, "Nguyễn An");
```

For a `VARCHAR(100)` column, a Java `String` longer than the column size may be rejected by the DB or truncated depending on configuration mode; **do not assume binding will safely shorten it**. Validate length per business rules, noting that databases count characters/bytes/Unicode units differently.

**Unicode:** Strings in Java use UTF-16; the driver/DB must have matching encoding and collation. A Vietnamese string with diacritics or emoji should be tested on both write and read paths. Some DBs distinguish `VARCHAR` from `NVARCHAR`, `CHAR`, and national-character APIs; if multilingual text fails to store properly, inspect the DDL, encoding, and JDBC driver before "fixing" it by manually escaping Unicode.

**Empty text and NULL are not synonymous** in every database. `""` is an empty Java string; SQL `NULL` represents the absence of a value. Some databases have special behavior for empty strings, so confirm the storage rules of the system you use.

**Wrong:** concatenating names/values into SQL; manually adding quotes around placeholders (`WHERE name = '?'`). The placeholder is `?` **without quotes**:

```sql
-- CORRECT
SELECT id FROM users WHERE display_name = ?;

-- WRONG: the question mark is treated as a text literal.
SELECT id FROM users WHERE display_name = '?';
```

If a column name used for `ORDER BY` is selected from a request, write a Java allowlist:

```java
// Illustrates whitelisting column names, not an SQL parameter.
String orderColumn = switch (requestedSort) {
    case "name" -> "display_name";
    case "created" -> "created_at";
    default -> throw new IllegalArgumentException("Unsupported sort");
};
String sql = "SELECT id FROM users ORDER BY " + orderColumn;
```

Only concatenate **identifiers hardcoded in an allowlist**, never raw input directly. `WHERE` values are still bound with `?`/named parameters.

## 4. Integers and Decimals: Choosing the Right Range and Precision

### Integer/Long

```java
// Java int -> SQL INTEGER, Java long -> SQL BIGINT.
ps.setInt(1, 42);
ps.setLong(2, 9_000_000_000L);
```

`int` is 32-bit signed, `long` is 64-bit signed. Check SQL `SMALLINT`/`INTEGER`/`BIGINT` limits as well, including cases where converters or drivers perform implicit casts. For large IDs, do not cast `long` down to `int` and hope the DB handles it.

**SQL NULL when reading primitives:** `ResultSet.getInt("count")` can return `0` when the column is NULL; the same goes for `getLong`. If you need to distinguish them, call `rs.wasNull()` **immediately after the getter** or use a wrapper with `getObject` when supported by the driver.

```java
int count = rs.getInt("count");
Integer nullableCount = rs.wasNull() ? null : count;
```

The snippet above assumes `rs.next()` has succeeded and the `count` column exists.

### BigDecimal and Monetary Values

`BigDecimal` preserves base-10 decimal numbers with chosen precision; `double` is binary floating-point and can introduce rounding errors when exact monetary matching is required.

```java
BigDecimal amount = new BigDecimal("1999.50");
ps.setBigDecimal(1, amount);
```

**Avoid preferring** `new BigDecimal(0.1)` because the `double` constructor reflects binary approximation; choose `new BigDecimal("0.10")` or `BigDecimal.valueOf(0.1)` when you already have a double, and ideally accept controlled decimal strings.

With SQL `DECIMAL(12,2)`: precision 12 is total digits; scale 2 is digits after the decimal point. If the input has more decimal digits, the DB may round or raise an error depending on dialect/mode. Define rounding rules in the domain, for example:

```java
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP);
```

Real financial problems must choose rounding rules per product/regulation rather than blindly applying `HALF_UP` everywhere.

### Why Does SQL Type Also Matter?

Spring `JdbcTemplate` normally infers the SQL type from the Java value. When the data type is unclear—such as `null` or vendor-specific types—you can supply `java.sql.Types.DECIMAL`/`BIGINT`, etc. to prevent the driver from mis-converting or failing to infer the type. Section 9 shows how to declare it explicitly.

## 5. Boolean: true, false, and NULL Are Three Distinct States

Java `boolean` only has two states, while the `Boolean` wrapper can be `null`. Many DBs support SQL `BOOLEAN`, while some legacy systems store it as `BIT`, `NUMBER(1)`, `TINYINT`, `CHAR(1)`, or custom conventions.

```java
ps.setBoolean(1, true);
ps.setBoolean(2, false);
```

**Do not assume** `setBoolean(1, true)` always means the driver sends the SQL literal `TRUE`. It sends a typed parameter value; the DB/driver decides the mapping. Read the DDL instead of guessing from a column name like `is_active`.

**When reading a nullable column:**

```java
boolean active = rs.getBoolean("active");
Boolean nullableActive = rs.wasNull() ? null : active;
```

If a column is nullable and code uses `getBoolean` while ignoring `wasNull()`, `NULL` is typically read as `false` and information is lost. If the business domain only has two states, use `NOT NULL` in the DB to express that requirement clearly.

If you have `Boolean maybeActive = null`, do not pass it into `setBoolean` (which only accepts primitive); use:

```java
if (maybeActive == null) {
    ps.setNull(1, Types.BOOLEAN);
} else {
    ps.setBoolean(1, maybeActive);
}
```

This snippet illustrates code inside a callback that has `ps` and `maybeActive` variables; it is not a standalone runnable Java file.

## 6. Date, Time, and Timestamp: Four Types to Distinguish

**Common mistake:** using one "date time" type for all appointments, birthdates, and system instants. Before binding, decide what the data means.

| Business Meaning | Java Type to Consider | Typical SQL Type | Has zone/offset info? |
| --- | --- | --- | --- |
| Birthdate, calendar payment due date | `LocalDate` | `DATE` | No |
| Daily opening hours | `LocalTime` | `TIME` | No |
| Appointment in a fixed location's timezone (store zone separately if needed) | `LocalDateTime` | `TIMESTAMP` | No |
| A global event point in time | `Instant` or `OffsetDateTime` | `TIMESTAMP WITH TIME ZONE` or a defined UTC policy | Yes, when represented with a separate zone/offset |

### 6.1. LocalDate -> SQL DATE

```java
LocalDate day = LocalDate.of(2026, 10, 30);
ps.setDate(1, java.sql.Date.valueOf(day));
// JDBC 4.2 and compatible drivers: ps.setObject(1, day);
```

`java.sql.Date` and `java.util.Date` are two different classes. `LocalDate` has no time/zone. When reading, `rs.getDate("day").toLocalDate()` works if not NULL. With JDBC 4.2 and supporting drivers, use `rs.getObject("day", LocalDate.class)` to avoid converting through legacy `java.sql` types.

### 6.2. LocalTime -> SQL TIME

```java
LocalTime time = LocalTime.of(9, 15, 30);
ps.setTime(1, java.sql.Time.valueOf(time));
// JDBC 4.2 + compatible drivers: ps.setObject(1, time);
```

`TIME` only holds hour/minute/second, without date or timezone. `java.sql.Time` typically drops sub-second precision; if nanoseconds are required, verify the dialect, SQL column precision, and actual `setObject(LocalTime)` behavior.

### 6.3. LocalDateTime -> SQL TIMESTAMP

```java
LocalDateTime localTime = LocalDateTime.of(2026, 10, 30, 9, 15, 30);
ps.setTimestamp(1, java.sql.Timestamp.valueOf(localTime));
// Compatible JDBC 4.2 driver: ps.setObject(1, localTime);
```

`LocalDateTime` carries no timezone. The value `2026-10-30T09:15:30` **is not enough to deduce a UTC instant**: 09:15 in Hanoi and 09:15 in New York are two different instants. When using `TIMESTAMP` without timezone, define the timezone by business policy or store the zone separately if interpretation is needed.

### 6.4. Instant/OffsetDateTime and TIMESTAMP WITH TIME ZONE

`Instant` represents a point on the UTC timeline. `OffsetDateTime` keeps date-time alongside a specific UTC offset. With supporting DB/JDBC drivers, you can bind:

```java
OffsetDateTime moment = OffsetDateTime.parse(
        "2026-10-30T09:15:30+07:00");
ps.setObject(1, moment, JDBCType.TIMESTAMP_WITH_TIMEZONE);
```

**This is an illustrative snippet, not part of the runnable example in section 10**: SQL type, driver mapping, precision, and whether offsets are preserved or normalized depend on the DB. `TIMESTAMP WITH TIME ZONE` does not mean every database retains zone names like `Asia/Ho_Chi_Minh`; sometimes only the instant/offset is stored or normalized. If the application needs daylight-saving rules, store the zone ID as required.

Specifically avoid serializing `Instant` into a local time string and binding it into `TIMESTAMP` without timezone control. Test round-trips across JVM timezone, JDBC/session timezone, and DB configuration.

## 7. byte[]: Binary Is Different from Text

`byte[]` represents a raw sequence of bytes: hashes, checksums, small files, compressed content, or binary protocols. The corresponding SQL type is typically `VARBINARY`/`BINARY`, while large data uses `BLOB` with appropriate streaming/LOB mechanisms.

```java
byte[] digest = { 0x01, 0x23, (byte) 0xFF };
ps.setBytes(1, digest);
```

Explanation: Java `byte` is **signed** in the range -128..127, so `0xFF` is represented in the array as `-1`; it is the **exact same byte bit-pattern**, not corrupted data. `Arrays.toString(digest)` prints `[1, 35, -1]`. To print hex for debugging, convert each byte to unsigned representation without altering the underlying data:

```java
byte[] bytes = { 0x01, 0x23, (byte) 0xFF };
System.out.println(java.util.HexFormat.of().formatHex(bytes));
// 0123ff
```

`HexFormat` has existed since Java 17, so the snippet fits this lesson's JDK. However, avoid logging images/credentials/tokens or sensitive data in production.

**Distinguish three forms:**

- `byte[]`: the raw bytes themselves; bind with `setBytes`/`Types.VARBINARY`.
- **Hex**: a character string like `"0123ff"`; 6 characters represent 3 bytes, not the original 3 bytes.
- **Base64**: a text string safely encoded for text transport; still must be decoded back to bytes if the DB column is binary.

Do not call `new String(bytes)` to store arbitrary binary data: bytes are not guaranteed to be valid UTF-8, making data loss/corruption likely. `String.getBytes(StandardCharsets.UTF_8)` is only for when *the original data really is text and you want to encode text*.

### VARBINARY, BINARY, or BLOB?

`BINARY(n)` is fixed-length and the driver/DB may pad it; `VARBINARY(n)` is variable-length within a limit; `BLOB` is for large data depending on the system. For multi-MB payloads, consider `setBinaryStream`/`getBinaryStream`, `Blob`, Spring's `LobHandler`, streaming reads/writes, and proper lifecycle cleanup. `setBytes` loads the entire array into JVM memory, making it unsuitable for very large files.

**Do not confuse `byte[]` with SQL ARRAY** (an SQL array of values like `INTEGER[]` in some DBs): SQL ARRAY uses a different API/dialect, not `setBytes`.

## 8. Plain JDBC: setXxx, setObject, and setNull

### 8.1. Use Explicit Setters When the Type Is Known

```java
// Illustrative snippet inside a method that already has Connection con.
String sql = "INSERT INTO documents (name, page_count, active) VALUES (?, ?, ?)";
try (PreparedStatement ps = con.prepareStatement(sql)) {
    ps.setString(1, name);
    ps.setInt(2, 12);
    ps.setBoolean(3, true);
    ps.executeUpdate();
}
```

Explicit setters make it easy to cross-check schema/params. Use `try-with-resources` on the connection too in the layer that owns it.

### 8.2. setObject Is Useful, Not Magical

`ps.setObject(1, value)` asks the driver to infer the SQL type from the Java object. For `LocalDate`/`LocalTime`/`LocalDateTime`, JDBC 4.2 standardizes basic mappings, though driver/DB support still requires testing. When type matters, use the overload with `Types`/`JDBCType`:

```java
ps.setObject(1, new BigDecimal("12.30"), JDBCType.DECIMAL);
```

You can also supply scale where the API supports it; cross-check the JDBC driver and column. Do not pass all data as `String` just for "easy binding": SQL types, indexes, and comparisons can be affected by implicit casts.

### 8.3. NULL Is a Value Without a Specific Java Type

**You cannot reliably infer SQL type from Java `null` alone**; use `setNull(index, Types.X)`:

```java
ps.setNull(1, Types.VARCHAR);
ps.setNull(2, Types.DECIMAL);
ps.setNull(3, Types.TIMESTAMP);
ps.setNull(4, Types.VARBINARY);
```

Only use `Types.NULL`/`setObject(index, null)` if you know your specific driver; some DBs reject untyped NULL in contexts where type knowledge is required. **SQL NULL is not equal to Java 0, false, an empty String, or an empty byte array.**

### 8.4. Read Nullable SQL Carefully

`ResultSet.getInt`/`getBoolean` returns primitive defaults on SQL NULL; call `wasNull` immediately after the getter. `getString`, `getBytes`, and `getBigDecimal` return `null` for SQL NULL. When `getDate` returns null, do not call `.toLocalDate()` on null. Model nullability directly in your DTO/record and schema; do not use fake sentinel values like `1970-01-01` to hide NULL unless the business domain genuinely requires it.

## 9. Binding via JdbcTemplate and NamedParameterJdbcTemplate

Spring Framework `JdbcTemplate` uses JDBC prepared statements under the hood while streamlining acquiring/closing `Connection`, `PreparedStatement`, and `ResultSet`, and translating `SQLException` into `DataAccessException`. For most use cases, letting Spring manage resources and passing parameters at the call site is sufficient.

### 9.1. Simple Varargs: Inferring Types from Java

```java
int updated = jdbcTemplate.update(
        "UPDATE users SET display_name = ? WHERE id = ?",
        "Nguyễn An", 101L);
```

`JdbcTemplate.update(String, Object...)` is convenient when values are unambiguous. `String`, `Integer`, `Long`, `Boolean`, `BigDecimal`, and `byte[]` are commonly supported by Spring/JDBC. Exact types and conversions depend on the schema/driver.

**Recognizing a `byte[]` pitfall:** Java `Object...` varargs can cause confusion if the wrong array type is passed. When you want to bind **one** `byte[]`, make sure it is treated as **a single value**; for example:

```java
byte[] bytes = { 0x01, 0x23 };
jdbcTemplate.update(
        "UPDATE docs SET body = ? WHERE id = ?",
        bytes, 101L);
```

Because `byte[]` is a primitive array, it is a single Java object and is not expanded into separate `Object` arguments. However, `Object[]` can be expanded into multiple arguments in varargs; if you truly want to bind an SQL ARRAY, a different JDBC mechanism is required.

### 9.2. PreparedStatementSetter / PreparedStatementCreator: Controlling setXxx

When explicit type setting is needed, use a callback:

```java
int changed = jdbcTemplate.update(
    "UPDATE tasks SET due_date = ?, enabled = ? WHERE id = ?",
    ps -> {
        ps.setDate(1, java.sql.Date.valueOf(
                LocalDate.of(2026, 10, 30)));
        ps.setBoolean(2, true);
        ps.setLong(3, 101L);
    });
```

This snippet needs imports, an injected `JdbcTemplate`, and matching tables/columns. Spring manages the connection/statement; callback code **must not close** `ps` or the connection. Use `PreparedStatementCreator` when special statement creation options are needed, or use `jdbc.update(connection -> prepareStatement(...))` as shown in the complete project in section 10.

### 9.3. SqlParameterValue and int[] SQL Types

Spring normally infers the SQL type from the object, but for `NULL`, special scale, or type-sensitive drivers, declare the type explicitly:

```java
int affected = jdbcTemplate.update(
        "UPDATE profiles SET nickname = ? WHERE id = ?",
        new SqlParameterValue(Types.VARCHAR, null),
        101L);
```

`SqlParameterValue` is in `org.springframework.jdbc.core`; the argument carries both `sqlType` and `value`. Some `JdbcTemplate.update`/`query` overloads also accept an **`int[] argTypes` array**:

```java
Object[] args = { null, 101L };
int[] types = { Types.VARCHAR, Types.BIGINT };
int count = jdbcTemplate.update(
        "UPDATE profiles SET nickname = ? WHERE id = ?",
        args, types);
```

In both snippets, the table is assumed to have a row with id 101; the code is not a standalone runnable program. When there are multiple parameters, **the length and order of `argTypes` must match `args` and the `?` markers**.

### 9.4. NamedParameterJdbcTemplate: Readable When There Are Many Parameters

`NamedParameterJdbcTemplate` supports `:name` SQL and a map/`SqlParameterSource`. Parsing and binding still rely on JDBC prepared statements, not concatenating input into SQL:

```java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("id", 101L, Types.BIGINT)
        .addValue("active", false, Types.BOOLEAN);

int rows = namedJdbc.update(
        "UPDATE users SET enabled = :active WHERE id = :id",
        params);
```

`MapSqlParameterSource.addValue(name, value, sqlType)` lets you specify the SQL type of each value, **which is especially useful for NULL**:

```java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("nickname", null, Types.VARCHAR)
        .addValue("id", 101L, Types.BIGINT);
```

`BeanPropertySqlParameterSource` maps JavaBean properties; if you choose to use it, understand naming, nullability, and property conversion. Named parameters do not turn SQL identifiers into parameters; `:tableName` in a table name position is not a safe solution for dynamic SQL.

### 9.5. Comparison Table of Binding Approaches

| Approach | What you provide | Who calls setters & cleanup? | When to use |
| --- | --- | --- | --- |
| Plain JDBC `PreparedStatement` | `setString/setInt/...` | You set and close statement/connection | Low-level JDBC or specialized operations |
| `JdbcTemplate.update(sql, values...)` | Java objects in order | Spring JDBC | Simple CRUD |
| `JdbcTemplate.update(sql, PreparedStatementSetter)` | Callback `ps.setXxx(...)` | You bind, Spring cleans up | Specific types/LOBs/vendor-specific behavior |
| `JdbcTemplate.update(PreparedStatementCreator)` | Callback creating prepared statement and binding | Spring cleans up statement/connection | Need statement flags/special handling |
| `SqlParameterValue` / `int[] argTypes` | Java value + SQL type | Spring JDBC | Nulls and SQL types must be explicit |
| `NamedParameterJdbcTemplate` | `:name` + `MapSqlParameterSource`/map | Spring JDBC | Many parameters, readable SQL |
| `JdbcClient` (Spring 6.1+) | Fluent SQL + `param(...)` | Spring JDBC | Newer API, concise syntax |

## 10. Complete Example: Binding All 9 Values and Reading Back via H2

**Java 17+ hands-on exercise**, Maven, Spring Boot **3.5.16**, Spring JDBC, and H2 in-memory. This version is used to keep the example reproducible; Spring Boot 3.5.x has reached OSS end-of-support, so new projects should choose a currently supported version and test compatibility. H2 helps illustrate the API, but does not guarantee identical behavior when switching to PostgreSQL, MySQL, SQL Server, or Oracle.

Goal: write `String`, `long`, `int`, `BigDecimal`, `boolean`, `LocalDate`, `LocalTime`, `LocalDateTime`, and `byte[]`; update using named parameters; explicitly bind SQL `NULL`.

**Project structure:**

```text
jdbc-bind-types/
├── pom.xml
└── src/main/
    ├── java/com/example/bind/BindTypesApplication.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

### 10.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jdbc-bind-types</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.2. src/main/resources/schema.sql

```sql
CREATE TABLE bind_demo (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL,
    quantity INTEGER NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    enabled BOOLEAN NOT NULL,
    work_date DATE NOT NULL,
    work_time TIME NOT NULL,
    created_local TIMESTAMP NOT NULL,
    payload VARBINARY(16) NOT NULL,
    nickname VARCHAR(120)
);
```

**Schema explanation:** `DECIMAL(12,2)` preserves fixed-point money; `DATE`/`TIME`/`TIMESTAMP` all carry no timezone; `payload` is raw bytes (not base64); nullable `nickname` is used to verify typed NULL.

### 10.3. src/main/resources/application.properties

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
spring.datasource.url=jdbc:h2:mem:bindtypes;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

Spring Boot creates an H2 datasource from the classpath and runs `schema.sql` before the runner. Using in-memory H2 lets the demo run without a DB server; when the JVM exits, demo data disappears.

### 10.4. src/main/java/com/example/bind/BindTypesApplication.java

```java
package com.example.bind;

import java.math.BigDecimal;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.Time;
import java.sql.Timestamp;
import java.sql.Types;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.Arrays;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlParameterValue;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@SpringBootApplication
public class BindTypesApplication {

    public static void main(String[] args) {
        SpringApplication.run(BindTypesApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc) {
        return args -> {
            String insert = """
                    INSERT INTO bind_demo
                      (id, display_name, quantity, amount, enabled,
                       work_date, work_time, created_local, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """;

            // PreparedStatementCreator: Spring owns closing Connection/Statement.
            int inserted = jdbc.update(connection -> {
                PreparedStatement ps = connection.prepareStatement(insert);

                ps.setLong(1, 101L);
                ps.setString(2, "Spring JDBC");
                ps.setInt(3, 3);
                ps.setBigDecimal(4, new BigDecimal("1999.50"));
                ps.setBoolean(5, true);

                ps.setDate(6, Date.valueOf(
                        LocalDate.of(2026, 10, 30)));
                ps.setTime(7, Time.valueOf(
                        LocalTime.of(9, 15, 30)));
                ps.setTimestamp(8, Timestamp.valueOf(
                        LocalDateTime.of(2026, 10, 30, 9, 15, 30)));

                ps.setBytes(9, new byte[] { 1, 35, (byte) 0xFF });
                return ps;
            });
            System.out.println("inserted=" + inserted);

            // Verify readback of all main types.
            String row = jdbc.queryForObject(
                    "SELECT * FROM bind_demo WHERE id = ?",
                    (rs, number) ->
                        rs.getLong("id") + "|" +
                        rs.getString("display_name") + "|" +
                        rs.getInt("quantity") + "|" +
                        rs.getBigDecimal("amount") + "|" +
                        rs.getBoolean("enabled") + "|" +
                        rs.getDate("work_date").toLocalDate() + "|" +
                        rs.getTime("work_time").toLocalTime() + "|" +
                        rs.getTimestamp("created_local")
                                .toLocalDateTime() + "|" +
                        Arrays.toString(rs.getBytes("payload")),
                    101L);
            System.out.println("row=" + row);

            // SQL named params: toggle using Boolean with explicit SQL type.
            NamedParameterJdbcTemplate named =
                    new NamedParameterJdbcTemplate(jdbc);
            MapSqlParameterSource params = new MapSqlParameterSource()
                    .addValue("enabled", false, Types.BOOLEAN)
                    .addValue("id", 101L, Types.BIGINT);
            int changed = named.update(
                    "UPDATE bind_demo SET enabled = :enabled WHERE id = :id",
                    params);
            System.out.println("named-updated=" + changed);

            Boolean enabled = jdbc.queryForObject(
                    "SELECT enabled FROM bind_demo WHERE id = ?",
                    Boolean.class, 101L);
            System.out.println("enabled=" + enabled);

            // Typed SQL NULL in JdbcTemplate varargs.
            int nullChanged = jdbc.update(
                    "UPDATE bind_demo SET nickname = ? WHERE id = ?",
                    new SqlParameterValue(Types.VARCHAR, null),
                    101L);
            System.out.println("null-updated=" + nullChanged);

            String nickname = jdbc.queryForObject(
                    "SELECT nickname FROM bind_demo WHERE id = ?",
                    String.class, 101L);
            System.out.println("nickname-null=" + (nickname == null));
        };
    }
}
```

**Run from the `jdbc-bind-types` directory**, with JDK 17+ and Maven installed:

```bash
mvn spring-boot:run
```

**Six lines printed by the application**, excluding Maven/Spring lines:

```text
inserted=1
row=101|Spring JDBC|3|1999.50|true|2026-10-30|09:15:30|2026-10-30T09:15:30|[1, 35, -1]
named-updated=1
enabled=false
null-updated=1
nickname-null=true
```

**Technical explanation:**

1. Every input value is bound to `?`, not SQL string concatenation. `PreparedStatementCreator` returns the bound statement; `JdbcTemplate` closes the connection/statement per contract upon execution.
2. `id` BIGINT receives `long`, `quantity` INTEGER receives `int`; `amount` DECIMAL receives `BigDecimal("1999.50")`, preserving two decimal digits on readback.
3. `enabled` BOOLEAN receives true, then is updated via `MapSqlParameterSource` to false; `:enabled`/`:id` names are parsed by Spring into bind parameters.
4. Date and time are created with **fixed values**, not the system clock: `LocalDate`/`LocalTime`/`LocalDateTime` without timezone, corresponding to H2 `DATE`/`TIME`/`TIMESTAMP`.
5. `payload` contains 3 bytes; `Arrays.toString` displays byte `0xFF` as `-1` due to Java's signed byte.
6. `nickname` is initially NULL because it was not set; `SqlParameterValue(Types.VARCHAR, null)` illustrates binding NULL with an explicit SQL type. Querying for `String.class` returns Java `null`.
7. The example uses separate statements and standard H2 datasource autocommit; it does **not** imply all operations run inside a shared transaction. If multiple changes must be atomic, organize them in a `@Transactional` service.
8. This is a structurally/code-complete Maven project, unlike illustrative snippets in other sections. In real deployments, test with the real DB and supported dependency versions.

## 11. Choosing the Right Binding Form in a Spring Application

**Case 1 — Simple CRUD with a few parameters and no ambiguous NULLs:** use `JdbcTemplate.update(sql, values...)`. Concise code, low risk of resource leaks.

**Case 2 — Many placeholders or many conditions:** use `NamedParameterJdbcTemplate` and `MapSqlParameterSource`, making SQL easier to read, especially when parameters share types and could easily be swapped.

**Case 3 — Driver/DB handles NULL inconsistently:** declare the SQL type explicitly via `SqlParameterValue`, `int[] argTypes`, `MapSqlParameterSource.addValue(name,value,sqlType)`, or `PreparedStatement.setNull(index, Types.X)`.

**Case 4 — Specialized JDBC setters needed:** use `PreparedStatementSetter` or `PreparedStatementCreator`, e.g., setting timestamps with `Calendar`/driver options, LOB streaming, generated keys, or custom vendor types.

**Case 5 — Batch processing needed:** use `JdbcTemplate.batchUpdate`/`BatchPreparedStatementSetter` to bind each parameter set, checking batch results and transactions. Do not assume batches are automatically atomic without a proper transaction.

**Case 6 — Stored procedures/advanced behavior needed:** use `SimpleJdbcCall` or `CallableStatement` with exact IN/OUT types; do not force every case into a single `JdbcTemplate.update`.

**Note:** Binding bugs usually surface at query **execution time**, not Java compile time. Driver exceptions are translated by Spring into `DataAccessException`, yet you still need to read SQLSTATE, vendor error codes, parameter index, and database schema to fix the root cause.

## 12. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Concatenating user `String` into SQL | SQL injection, quoting errors | Use `?`/named params |
| Writing `'?'` instead of `?` | Literal question mark, no bind marker | Remove single quotes around placeholder |
| Starting index at 0 | Index `SQLException` | JDBC parameters start at 1 |
| Passing `id`/`status` in wrong order | Wrong data or type mismatch | Cross-check SQL, SQL types, and call site |
| Pushing large numbers into `setInt` | Overflow / out of SQL range | Choose `long`/`BIGINT` as required |
| Using `double` to store money into DECIMAL | Precision/scale drift | `BigDecimal` from string |
| Skipping `wasNull()` after `getBoolean/getInt` | NULL treated as false/0 | Use wrappers/null-aware reads |
| Calling `setObject(i, null)` on type-sensitive DBs | Driver/DB cannot determine type | `setNull(i,Types.X)` or Spring typed NULL |
| Storing `LocalDateTime` as a UTC instant | Wrong timezone upon conversion | Define zone, use OffsetDateTime/Instant per schema |
| Expecting TIMESTAMP to retain zone ID | Time drift / normalized offset | Check DB type and store zone ID if needed |
| Using `Time.valueOf` with nanoseconds | Loss of sub-second precision | Use `setObject(LocalTime)` when driver/column supports it |
| Saving `byte[]` into text columns via `new String(bytes)` | Binary corrupted / lost bytes | Use `VARBINARY`/`BLOB` |
| Logging byte arrays/secrets | Sensitive data exposure | Log only length/safe hash if needed |
| Using `setBytes` for very large files | High heap usage, buffer copies | Use LOB/streaming with cleanup |
| Binding table/column names with `?` | Invalid SQL syntax | Allowlist identifiers |
| Assuming every DB has BOOLEAN | Portability failure | Inspect schema/dialect |
| Ignoring `VARCHAR` length and `DECIMAL` precision | Truncation/rounding/rejection | Validate domain and integration test |
| Closing `PreparedStatement` provided by JdbcTemplate in callback | Resource usage errors | Let Spring clean up |
| Thinking commit happens automatically after each setter | Wrong lifecycle model | Bind only sets value; execute runs SQL; transaction governs commit |

## 13. Testing Thoroughly Enough to Trust Round-Trips

A good test does not just assert `update()==1`, it verifies data **after writing and reading it back**:

1. **String:** Vietnamese with diacritics, special characters `'`, empty string, length limits, Unicode.
2. **Integer/Long:** 0, negative (if allowed by business rules), column boundary values; overflow checks.
3. **BigDecimal:** multi-digit numbers, scales other than 2, rounding, and values larger than `DECIMAL(p,s)`.
4. **Boolean:** true/false and SQL NULL if column is nullable, ensuring NULL does not become false.
5. **DATE:** leap days, start/end of year, and same date when changing JVM timezone.
6. **TIME:** seconds/sub-seconds at the DB's actual precision.
7. **TIMESTAMP:** LocalDateTime round-trip, precision, and JVM/session timezone; use `Instant` when data is a global instant.
8. **byte[]:** zero bytes, `0x00`/`0xFF` bytes, empty array, lengths near `VARBINARY` limit, comparing with `Arrays.equals`.
9. **NULL:** `setNull`/`SqlParameterValue` and named `MapSqlParameterSource` through the same DB/driver.
10. **Rollback:** when inserting across multiple tables in one use case, simulate a mid-way failure and verify the transaction rolls back everything.

With H2, happy-path SQL may pass while PostgreSQL/Oracle/SQL Server differ in BOOLEAN, timestamp precision, national characters, NULL types, and binary LOBs. Prioritize integration tests on a production-like database, using Testcontainers when appropriate.

### Plain Java Assertion Tip

```java
byte[] written = { 0x00, 0x01, (byte) 0xFF };
byte[] read = /* rs.getBytes("payload") inside RowMapper */;
boolean exactlySame = java.util.Arrays.equals(written, read);
```

The snippet above is only an **illustrative comparison**, not a standalone file; `read` must come from an open JDBC result set. `Arrays.equals` compares **`byte[]` contents**, whereas `written.equals(read)` compares array references by default.

## 14. Self-Check Questions with Answers

**Question 1:** SQL `WHERE name = ?`, Java `ps.setString(0,"An")`. Where is the error?  
**Answer:** JDBC parameter indices start at **1**; use `setString(1,"An")`.

**Question 2:** When an SQL `DECIMAL(12,2)` column stores money, should you bind `new BigDecimal("0.10")` or `double 0.1`?  
**Answer:** prefer `BigDecimal` from a controlled string/decimal value so binary floating-point error is not introduced.

**Question 3:** `ResultSet.getBoolean("active")` returns false. Is SQL definitely FALSE?  
**Answer:** not if the column is nullable; it could be SQL NULL. Call `rs.wasNull()` immediately after the getter or read using an appropriate nullable method.

**Question 4:** Does `LocalDateTime.of(2026,10,30,9,15)` automatically indicate Vietnam timezone?  
**Answer:** no. `LocalDateTime` has no zone; to describe a global point in time you must attach a zone/offset per business rules or use `Instant`.

**Question 5:** An array `{(byte)0xFF}` prints `[-1]` when read back. Were bytes lost?  
**Answer:** no. Java `byte` is signed, yet the bit-pattern is still FF; use hex or `Byte.toUnsignedInt` if you need to view 255.

**Question 6:** Why does `UPDATE ... SET nickname = ?` with value `null` sometimes cause a driver error?  
**Answer:** the driver/DB may need the SQL type. Use `setNull(index,Types.VARCHAR)`, `SqlParameterValue(Types.VARCHAR,null)`, or a named source with `Types.VARCHAR`.

**Question 7:** Is `byte[]` automatically bound as an SQL array `INTEGER[]`?  
**Answer:** no. `byte[]` is normally binary bytes (`VARBINARY`/`BLOB`); SQL ARRAY is a different type with its own driver API.

**Question 8:** When using `JdbcTemplate.update(sql, setter)`, who closes the prepared statement and connection?  
**Answer:** Spring JDBC manages cleanup inside the call; the callback only binds and must not close resources provided by Spring.

**Question 9:** If you need to sort by a client-selected column, can you use `ORDER BY ?` with `setString`?  
**Answer:** no. `?` binds values, not identifiers/syntax. Use a trusted allowlist of column names.

**Question 10:** Does running `ps.setBytes(1, bytes)` immediately write the bytes to the DB?  
**Answer:** no. The setter assigns the parameter; `executeUpdate`/`execute` sends the statement. Commit depends on transaction/auto-commit.

## 15. Checklist Before Merging SQL Binding Code

- [ ] Dynamic data is bound via `?`/`:name`; dynamic identifiers use an allowlist.
- [ ] Every `?` has matching count, 1-based index, and binding order matching SQL.
- [ ] `String` has proper encoding/length, tested with Unicode and quotes.
- [ ] `int/long` is not narrowed, `BigDecimal` matches precision/scale.
- [ ] `boolean`/`Boolean` handles NULL per schema and domain.
- [ ] `DATE/TIME/TIMESTAMP` are used with right semantics; timezone policy is explicit.
- [ ] `byte[]` goes into a binary column, content compared, never converted to text arbitrarily.
- [ ] Type-sensitive `null`s have explicit `Types.X`.
- [ ] No resource leaks and no accidental closing of resources owned by `JdbcTemplate`.
- [ ] Readback tests, boundary values, and real DB driver tests are present.
- [ ] Transactions/use cases are clear when multiple SQL statements must be atomic.

## Official References

- Spring Framework — Common Problems with Parameter and Data Value Handling: https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html
- Spring Framework — JDBC Core Classes (`JdbcTemplate`, named params): https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — JDBC Batch Operations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Framework API — `SqlParameterValue`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/SqlParameterValue.html
- Spring Framework API — `MapSqlParameterSource`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html
- Java 17 JDBC — `PreparedStatement`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html
- Java 17 JDBC — `ResultSet`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html
- H2 Database — Data Types: https://h2database.com/html/datatypes.html
- Spring Boot 3.5.16 release and support status: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Takeaway:** **The SQL template holds placeholders; `PreparedStatement` or Spring JDBC binds Java values to JDBC types; the database executes per schema.** For String/numeric/boolean/date-time/binary, choose types by **business semantics**, pay attention to **typed NULL, BigDecimal for money, timezone for instants, VARBINARY for byte[]**, and always test round-trips against a real DB.