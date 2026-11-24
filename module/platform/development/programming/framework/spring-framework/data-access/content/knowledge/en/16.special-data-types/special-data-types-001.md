# Converting Between SQL Types and Java Types in Spring JDBC

## 1. Goals and Context

In a Spring Framework application accessing a database via JDBC, a value passes through three type layers:

1. **Database column type**: `VARCHAR`, `DECIMAL`, `DATE`, `TIMESTAMP`, `BLOB`, `ARRAY`, `JSON`, `UUID`…
2. **JDBC and driver type**: `java.sql.Types` / `JDBCType` describes the SQL data type; `PreparedStatement` binds input values; `ResultSet` reads output values. The driver determines conversion support and specific representations.
3. **Java application type**: `String`, `BigDecimal`, `Long`, `LocalDate`, `LocalDateTime`, `OffsetDateTime`, `UUID`, `byte[]`, Java records/beans, and domain objects.

Spring JDBC (`JdbcTemplate`, `NamedParameterJdbcTemplate`, `SimpleJdbcInsert`, `SimpleJdbcCall`) manages resource lifecycles, binds parameters, maps result rows, and translates SQL errors into `DataAccessException`. **Spring does not eliminate type differences across databases.** For special types, you still need to decide on the Java type, how to bind, how to read, how to handle `NULL`, and sometimes write a driver-specific converter.

This lesson focuses on choosing and controlling conversions between SQL ↔ Java in Spring JDBC, covering both common types as a foundation and **special data types**. Do not conflate Spring JDBC mechanisms with JPA/Hibernate: JPA's `@Column`, `AttributeConverter`, and dialect are not automatically applied by `JdbcTemplate`.

### The Path of a Value

~~~text
Java value
  -> Spring JDBC parameter binding
  -> PreparedStatement.setXxx/setObject/setNull
  -> JDBC driver -> SQL column
  -> ResultSet.getXxx/getObject/getArray/getBlob...
  -> RowMapper/ResultSetExtractor
  -> Java value / domain model
~~~

What must be verified is **bidirectional**. Just because a driver can write a `UUID` or a JSON string does not guarantee reading it back will produce the exact `UUID` or POJO you expect. Nor is there a single mapping that works for every DBMS, every driver version, and every extension type.

## 2. Three Distinct Concepts: SQL Type, JDBC Type, and Java Type

- **SQL type**: how the database stores and interprets data; for example, `NUMERIC(12,2)` has precision 12 and scale 2; `TIMESTAMP WITH TIME ZONE` has different semantics from plain `TIMESTAMP`.
- **JDBC type code**: constants such as `Types.DECIMAL`, `Types.VARCHAR`, `Types.TIMESTAMP`, `Types.ARRAY`, `Types.OTHER`; used when binding or declaring parameters. `JDBCType` is the modern enum implementing `SQLType`, e.g., `JDBCType.DECIMAL`. Many Spring JDBC APIs accept an `int` from `Types`.
- **Java type**: the value in the program; the choice should be based on nullability, numeric range, precision, timezone, immutability, and business requirements.

Two columns with the same name `id`, one `INTEGER` and one `BIGINT`, may require different types `Integer` and `Long`; likewise, two columns `TIMESTAMP` and `TIMESTAMP WITH TIME ZONE` should not automatically be treated as the same `Instant` without agreeing on how time zones are stored.

### Practical Mapping Table

These are the **recommended Java types to choose**, not a guarantee that `ResultSet.getObject(column)` will always return that exact class.

| SQL/JDBC Type | Commonly Used Java Type | Conversion Notes |
|---|---|---|
| `CHAR`, `VARCHAR`, `LONGVARCHAR`, `NCHAR`, `NVARCHAR` | `String` | `CHAR` may be space-padded; collation and Unicode depend on the DB |
| `TINYINT`, `SMALLINT` | `Byte`, `Short`, or `Integer` depending on range | Do not assume every driver returns the exact wrapper when using untyped `getObject()` |
| `INTEGER` | `Integer` / `int` | `int` cannot represent SQL `NULL` |
| `BIGINT` | `Long` / `long` | Check for unsigned numeric columns or numbers exceeding `long` on a specific DB |
| `DECIMAL(p,s)`, `NUMERIC(p,s)` | `BigDecimal` | Right choice when exact decimal values are needed, especially for money |
| `REAL`, `FLOAT`, `DOUBLE PRECISION` | `Float` or `Double` depending on actual type | Binary floating-point numbers have representation inaccuracy |
| `BOOLEAN`, `BIT` | `Boolean` / `boolean` or driver-specific | `BIT(n)` is not necessarily a single boolean; it can be a bit string |
| `DATE` | `LocalDate` | Calendar date only, carries no instant/timezone |
| `TIME [WITHOUT TIME ZONE]` | `LocalTime` | Time of day only |
| `TIMESTAMP [WITHOUT TIME ZONE]` | `LocalDateTime` | Contains no offset/zone; avoid assuming UTC by default |
| `TIME WITH TIME ZONE` | `OffsetTime` | DB/driver dependent |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` | Preserving original offset, normalizing to UTC, and read-back behavior depend on the DB |
| `BINARY`, `VARBINARY`, `LONGVARBINARY` | `byte[]` | Small binary data; do not blindly convert to UTF-8 strings |
| `BLOB` | `Blob` or stream/`byte[]` | Pay attention to memory, size, and connection lifecycle |
| `CLOB`, `NCLOB` | `Clob`/`NClob`, `Reader`, or `String` | Large text; check encoding and streaming |
| `ARRAY` | `java.sql.Array` and driver-returned Java elements | Different from Java array/List and different from Spring's `IN (:ids)` expansion |
| `STRUCT`, composite types | `java.sql.Struct`, `SQLData`, or converter-created object | Depends on DB type name and structure |
| `SQLXML` | `java.sql.SQLXML`, XML text/DOM/StAX after parsing | Must handle XML content and resource cleanup |
| `UUID`, `JSON/JSONB`, `ENUM`, non-standard types | `UUID`, `String`/POJO, Java enum | **No uniform cross-DB mapping**; drivers may use `Types.OTHER` |

**Principle:** do not infer the SQL type just from the Java type name. When in doubt, inspect the DDL, `ResultSetMetaData.getColumnType()`, `getColumnTypeName()`, and the class of the value returned by the driver. `java.sql.Types.OTHER` is usually a signal of an extension type, not a universal JSON/UUID converter.

## 3. Converting from Java to SQL: Binding Parameters

### What Does Plain JDBC Do?

JDBC binds parameters by **1-based** position:

~~~java
// Illustrative snippet within a scope that already has PreparedStatement ps.
ps.setLong(1, 42L);
ps.setBigDecimal(2, new java.math.BigDecimal("19.90"));
ps.setObject(3, java.time.LocalDate.of(2026, 10, 30));
ps.setNull(4, java.sql.Types.VARCHAR);
~~~

`setLong`, `setBigDecimal`, etc. make the input type explicit. `setObject` asks the driver to convert a Java object to SQL; JDBC 4.2 supports many `java.time` types via `setObject`/`getObject`. When a driver lacks support or compatibility is needed, convert to `java.sql.Date.valueOf(localDate)`, `Time.valueOf(localTime)`, or `Timestamp.valueOf(localDateTime)` for columns without a timezone. This approach does not automatically resolve the timezone of an absolute instant.

`ps.setObject(index, value, targetSqlType)` or `ps.setNull(index, sqlType)` specifies the target SQL type explicitly. Do not use `setString` for every data type and rely on the DB to CAST arbitrarily.

### `JdbcTemplate`: Positional Parameters and `Types`

~~~java
// Illustration with a configured JdbcTemplate jdbc; table account exists.
int changed = jdbc.update(
        "UPDATE account SET balance = ?, closed_at = ? WHERE id = ?",
        new Object[] {new java.math.BigDecimal("125.50"), null, 10L},
        new int[] {
                java.sql.Types.DECIMAL,
                java.sql.Types.TIMESTAMP,
                java.sql.Types.BIGINT
        }
);
~~~

The SQL type array has **one element per `?` placeholder**, in the same SQL order. This is the safe way to pass a typed `null`, especially with drivers that require explicit metadata. Passing the type array does not change the column's nullability: a `NOT NULL` schema constraint will still reject it.

Another approach is `SqlParameterValue`:

~~~java
// Illustration with a configured JdbcTemplate jdbc.
jdbc.update(
        "UPDATE account SET balance = ? WHERE id = ?",
        new org.springframework.jdbc.core.SqlParameterValue(
                java.sql.Types.DECIMAL,
                new java.math.BigDecimal("125.50")),
        10L
);
~~~

`SqlParameterValue` carries the SQL type along with a value, and can include scale for numeric types. When the driver cannot infer the type from the Java value (especially `NULL` and exotic types), this is clearer than passing a bare `Object`.

### `NamedParameterJdbcTemplate`: Named Parameters and SQL Types

~~~java
// Illustration: NamedParameterJdbcTemplate named is already available.
var params = new org.springframework.jdbc.core.namedparam.MapSqlParameterSource()
        .addValue("id", 10L, java.sql.Types.BIGINT)
        .addValue("balance", new java.math.BigDecimal("125.50"),
                java.sql.Types.DECIMAL)
        .addValue("closedAt", null, java.sql.Types.TIMESTAMP);

int changed = named.update("""
        UPDATE account
        SET balance = :balance, closed_at = :closedAt
        WHERE id = :id
        """, params);
~~~

`MapSqlParameterSource.addValue(name, value, sqlType)` and `registerSqlType(name, sqlType)` let you specify the type by **name**. `BeanPropertySqlParameterSource` reads values from bean getters and can also register types; use it when Java properties match parameter names. For `null`, `Map.of(...)` is not an option because it does not accept null values.

**Note:** parameter binding applies only to **values**. Table names, column names, sort order, or SQL types are not protected if strings are concatenated directly from untrusted data. For dynamic identifiers, validate against an allowlist and construct SQL in a controlled manner.

## 4. Converting from SQL to Java: Reading `ResultSet` Intentionally

Three common approaches:

~~~java
String label = rs.getString("label");
java.math.BigDecimal amount = rs.getBigDecimal("amount");
java.time.LocalDate when = rs.getObject("booked_on",
        java.time.LocalDate.class);
~~~

`rs.getObject("booked_on", LocalDate.class)` requests conversion of the value to a specific Java class, if the driver supports it. Unlike `rs.getObject("booked_on")`: the form without a class parameter uses the driver's default type and may return `java.sql.Date` instead of `LocalDate`.

In Spring JDBC, use `RowMapper<T>` to decide how objects are constructed:

~~~java
// Illustration in a DAO's RowMapper<Item> mapper variable.
(rs, rowNum) -> new Item(
        rs.getLong("id"),
        rs.getString("name"),
        rs.getBigDecimal("amount"),
        rs.getObject("created_on", java.time.LocalDate.class)
)
~~~

This snippet only illustrates mapper logic and assumes the corresponding `Item` record/class is already declared. `JdbcTemplate` closes the statement and result set according to their lifecycle, while `RowMapper` decides which fields are meaningful and how to check nulls/types. When SQL returns only a single column, you can use `queryForObject(sql, BigDecimal.class, args...)`; do not apply single-column mapping to multi-column queries.

**Distinctions to keep in mind:**

- `ResultSet#getInt/getLong/getBoolean` return primitives; SQL `NULL` is represented as 0/false, so you must call `wasNull()` if the column allows null.
- `getString/getBigDecimal/getBytes/getObject` return references that can be `null`.
- `getObject(column, Integer.class)` retrieves a nullable wrapper when the driver supports the requested type.
- `ResultSet.getObject(...)` does not automatically turn JSON into an application record, database enums into Java enums, or binary data into formatted documents.

### `NULL` and Primitives: A Silent Data Bug

~~~java
int raw = rs.getInt("rating");
Integer rating = rs.wasNull() ? null : raw;

// On drivers supporting typed conversion:
Integer rating2 = rs.getObject("rating", Integer.class);
~~~

If the `rating` column contains SQL `NULL` and the code only reads `int raw = rs.getInt("rating")`, you will see `0` and easily confuse "unrated" with "rated 0". `wasNull()` must be called **immediately after** the getter being checked, before reading any other column.

When designing models, use `Integer`/`Long`/`Boolean` if business logic needs to distinguish null; use primitives only when the column is guaranteed `NOT NULL` and the logic does not need an unknown state. `Optional<T>` can be a return type of a DAO/service, but do not assume the JDBC driver returns `Optional<T>` from `getObject`.

## 5. Complete Example: Java 17 + Spring JDBC + H2

A standalone Maven example, **without Spring Boot**. The data includes an exact decimal, boolean, date, timestamp, and a nullable integer column. Writing uses `NamedParameterJdbcTemplate` with explicit SQL types; reading uses `JdbcTemplate` with `RowMapper` and `getObject(column, Class)`.

File structure:

~~~text
sql-java-conversion-demo/
├── pom.xml
└── src/main/java/demo/SqlJavaTypeDemo.java
~~~

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>sql-java-conversion-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/demo/SqlJavaTypeDemo.java`:**

~~~java
package demo;

import java.math.BigDecimal;
import java.sql.Date;
import java.sql.Timestamp;
import java.sql.Types;
import java.time.LocalDate;
import java.time.LocalDateTime;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

public class SqlJavaTypeDemo {

    record Item(long id, String label, BigDecimal amount,
                boolean active, LocalDate bookedOn,
                LocalDateTime recordedAt, Integer rating) {}

    public static void main(String[] args) {
        JdbcDataSource ds = new JdbcDataSource();
        ds.setURL("jdbc:h2:mem:sql_types_demo;DB_CLOSE_DELAY=-1");
        ds.setUser("sa");

        JdbcTemplate jdbc = new JdbcTemplate(ds);
        NamedParameterJdbcTemplate named =
                new NamedParameterJdbcTemplate(ds);

        jdbc.execute("""
                CREATE TABLE item (
                    id BIGINT PRIMARY KEY,
                    label VARCHAR(80) NOT NULL,
                    amount DECIMAL(12, 2) NOT NULL,
                    active BOOLEAN NOT NULL,
                    booked_on DATE NOT NULL,
                    recorded_at TIMESTAMP NOT NULL,
                    rating INTEGER NULL
                )
                """);

        LocalDate day = LocalDate.of(2026, 10, 30);
        LocalDateTime localTime =
                LocalDateTime.of(2026, 10, 30, 9, 15, 30);

        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("id", 7L, Types.BIGINT)
                .addValue("label", "Book", Types.VARCHAR)
                .addValue("amount", new BigDecimal("259.90"), Types.DECIMAL)
                .addValue("active", true, Types.BOOLEAN)
                .addValue("bookedOn", Date.valueOf(day), Types.DATE)
                .addValue("recordedAt",
                        Timestamp.valueOf(localTime), Types.TIMESTAMP)
                .addValue("rating", null, Types.INTEGER);

        int inserted = named.update("""
                INSERT INTO item
                    (id, label, amount, active, booked_on, recorded_at, rating)
                VALUES
                    (:id, :label, :amount, :active, :bookedOn,
                     :recordedAt, :rating)
                """, params);

        Item row = jdbc.queryForObject("""
                SELECT id, label, amount, active,
                       booked_on, recorded_at, rating
                FROM item WHERE id = ?
                """, (rs, rowNum) -> new Item(
                rs.getLong("id"),
                rs.getString("label"),
                rs.getBigDecimal("amount"),
                rs.getBoolean("active"),
                rs.getObject("booked_on", LocalDate.class),
                rs.getObject("recorded_at", LocalDateTime.class),
                rs.getObject("rating", Integer.class)
        ), 7L);

        System.out.println("inserted=" + inserted);
        System.out.println("id=" + row.id());
        System.out.println("label=" + row.label());
        System.out.println("amount=" + row.amount().toPlainString());
        System.out.println("active=" + row.active());
        System.out.println("bookedOn=" + row.bookedOn());
        System.out.println("recordedAt=" + row.recordedAt());
        System.out.println("rating=" + row.rating());

        int updated = jdbc.update(
                "UPDATE item SET rating = ? WHERE id = ?",
                new Object[] {5, 7L},
                new int[] {Types.INTEGER, Types.BIGINT}
        );
        Integer newRating = jdbc.queryForObject(
                "SELECT rating FROM item WHERE id = ?",
                Integer.class, 7L
        );
        System.out.println("updated=" + updated);
        System.out.println("newRating=" + newRating);
    }
}
~~~

**Run** (with JDK 17+ and Maven installed, from the directory containing `pom.xml`):

~~~bash
mvn -q compile exec:java "-Dexec.mainClass=demo.SqlJavaTypeDemo"
~~~

**Logical output on a fresh in-memory H2 database:**

~~~text
inserted=1
id=7
label=Book
amount=259.90
active=true
bookedOn=2026-10-30
recordedAt=2026-10-30T09:15:30
rating=null
updated=1
newRating=5
~~~

Why is the result correct?

1. `BigDecimal("259.90")` preserves the exact decimal value; H2 stores it with scale 2. `toPlainString()` displays `259.90`.
2. Date input uses `java.sql.Date.valueOf(LocalDate)` and timestamp input uses `Timestamp.valueOf(LocalDateTime)` for an explicit SQL type; on read, JDBC 4.2/H2 supports `LocalDate` and `LocalDateTime` directly.
3. The `rating` column on INSERT is SQL `NULL`, so Java `Integer rating` receives `null` rather than being turned into 0.
4. The `JdbcTemplate.update(...)` call uses a `Types` array in the exact order for the two `?` placeholders, then `queryForObject(..., Integer.class)` reads a single scalar.
5. The `TIMESTAMP` value in the example is a calendar time *without an offset*; the string `2026-10-30T09:15:30` cannot by itself imply UTC or Vietnam time.

This is a standalone runnable program. The short snippets that follow illustrate other databases or tables; **do not paste them verbatim into the program above**.

## 6. SQL `DECIMAL`, `NUMERIC`, and Numeric Precision

### Money and Exact Decimals: Choose `BigDecimal`

`DECIMAL(12,2)` has up to 12 total digits and 2 digits after the decimal point (depending on how the DB enforces precision/scale). Java `double` stores numbers in binary, so it cannot accurately represent most decimal values such as 0.1:

~~~java
var safe = new java.math.BigDecimal("0.10");
var unsafe = new java.math.BigDecimal(0.1);

System.out.println(safe.toPlainString());
System.out.println(unsafe.toPlainString());
~~~

The first line prints `0.10`. The second line prints a long decimal representation of the `double` value 0.1, so never use the `double` constructor for money. The snippet above can run inside a Java method; it is unrelated to the H2 demo.

Choose `BigDecimal` for prices/money and measurements requiring precision; choose `Float`/`Double` for floating-point data suited to the domain. `BigDecimal.equals(...)` takes scale into account: `1.0` and `1.00` differ under `equals` but are equal under `compareTo(...) == 0`. When rounding, define `RoundingMode` explicitly at the business layer rather than letting implicit type conversions decide.

### Integer Ranges and Overflow

A standard `BIGINT` corresponds to Java's signed `long`. If a DB uses unsigned BIGINT, a large NUMBER, or `NUMERIC(38,0)`, a `long` may not be enough. `Number.longValue()` can silently drop out-of-range bits; `BigDecimal.longValueExact()` or `BigInteger.longValueExact()` helps detect values that cannot be represented exactly:

~~~java
java.math.BigDecimal n =
        new java.math.BigDecimal("9223372036854775808");

try {
    System.out.println(n.longValueExact());
} catch (ArithmeticException ex) {
    System.out.println("BIGINT exceeds long range");
}
~~~

Output of this standalone numeric example: `BIGINT exceeds long range`.

When mapping a schema, check **bounds**, **scale**, **signed/unsigned**, and whether the DB driver performs automatic type conversion. Do not cast `(Long) rs.getObject("id")` when the driver might return `BigDecimal` or `BigInteger`.

## 7. Dates, Times, and Timezone Issues

This is one of the most error-prone areas in SQL ↔ Java conversion.

| Value Category | Common SQL Type | Appropriate Java Type | Meaning |
|---|---|---|---|
| Birthday or accounting date | `DATE` | `LocalDate` | Calendar date, no time of day |
| Opening hours | `TIME` | `LocalTime` | Time of day, not tied to a date/zone |
| Local calendar appointment | `TIMESTAMP WITHOUT TIME ZONE` | `LocalDateTime` | Date + time, no offset |
| Instant with offset info | `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` | Can be converted to an `Instant` |
| Global instant for comparison | Choose a UTC storage strategy or explicit timezone type | `Instant` in domain layer | Do not treat `LocalDateTime` as an instant without attaching a zone |

Example using JDBC 4.2, assuming the DB/driver supports `TIMESTAMP WITH TIME ZONE`:

~~~java
// Illustrative snippet in RowMapper; column event_at has timezone.
java.time.OffsetDateTime dt =
        rs.getObject("event_at", java.time.OffsetDateTime.class);
java.time.Instant instant = dt == null ? null : dt.toInstant();
~~~

For input, modern drivers may support `ps.setObject(index, offsetDateTime)` or specifying `Types.TIMESTAMP_WITH_TIMEZONE`; an integration test is needed. `OffsetDateTime` carries an offset like `+07:00`, but does not store the full region name `Asia/Ho_Chi_Minh`. Some DBs normalize the value to UTC, while others preserve the offset in their own way. `TIMESTAMP WITHOUT TIME ZONE` typically stores no offset information at all.

**Mistakes to avoid:**

- Attaching `ZoneOffset.UTC` to a `LocalDateTime` recorded in local time without verifying the source. The result will be off by several hours.
- Assuming `java.sql.Timestamp` is always a UTC instant: it is a legacy type representing a timestamp whose interpretation across DB/driver depends on configuration.
- Using `java.util.Date` or `String` instead of `LocalDate` for birthdays increases the risk of accidental timezone shifts.
- Assuming the database returns the exact original offset just because the column is named `TIMESTAMP WITH TIME ZONE`. Verify the exact behavior of the production DB.

When handling temporal data, standardize a strategy: (1) store UTC/instant or an appropriate timezone type, (2) convert zones only at the presentation boundary, (3) configure session/driver timezone, and (4) test cases across midnight and Daylight Saving Time transitions if the system serves regions with DST.

## 8. Special Types: UUID, JSON, ENUM, and Vendor Types

These types do not share a single Java/JDBC contract across all databases.

### UUID

Some DBs provide a native `UUID` type, while others store it as `CHAR(36)`, `BINARY(16)`, or other combinations. With a DB/driver that supports `UUID` objects, such as PostgreSQL or H2:

~~~java
// Illustration with PreparedStatement ps and ResultSet rs on a DB supporting UUID.
java.util.UUID uuid =
        java.util.UUID.fromString("11111111-2222-4333-8444-555555555555");
ps.setObject(1, uuid); // driver supports converting UUID to SQL UUID
java.util.UUID readBack =
        rs.getObject("external_id", java.util.UUID.class);
~~~

This example only illustrates the JDBC API in a context that already has `ps` and `rs`; it does not contain standalone queries or tables. Configuring `MapSqlParameterSource.addValue("externalId", uuid, Types.OTHER)` may work for drivers that use `OTHER` for UUIDs, but you should not force `Types.OTHER` across every DB. If storing UUIDs as `BINARY(16)` or `CHAR(36)`, use a codec that clearly defines byte/string ordering; do not assume JDBC does this automatically.

### JSON and JSONB

SQL `JSON`/`JSONB` usually requires **serializing the Java object to JSON text** on write, and **parsing JSON back to a model** on read. Spring JDBC does not automatically turn `Map<String,Object>` into `JSONB` on all DBs.

**PostgreSQL-specific** SQL example, where `payloadJson` is already a valid JSON string (e.g., produced by Jackson) and `named` is a configured `NamedParameterJdbcTemplate`:

~~~java
var p = new org.springframework.jdbc.core.namedparam.MapSqlParameterSource()
        .addValue("id", 100L, java.sql.Types.BIGINT)
        .addValue("payload", payloadJson, java.sql.Types.VARCHAR);

named.update("""
        INSERT INTO event_store(id, payload)
        VALUES (:id, CAST(:payload AS jsonb))
        """, p);
~~~

`CAST(... AS jsonb)` is a PostgreSQL detail; other databases have different syntax. When reading, `rs.getString("payload")` can provide JSON text to parse with Jackson (e.g., `ObjectMapper.readValue(...)`). This is an **illustrative snippet** requiring the `event_store` table, the `payloadJson` variable, and a JSON library in the application—it is not part of the H2 demo. If the driver returns a `PGobject` via `getObject`, extract the JSON from the object using the driver API; do not blindly cast to `String`.

### ENUM

For a Java enum `Status.ACTIVE`, choose one of two policies and stay consistent:

- Store stable text (e.g., `"ACTIVE"`) in a `VARCHAR` column; read with `Status.valueOf(raw)` **after** validating the name and handling legacy/invalid values.
- Use the database's native enum with a driver-appropriate converter/SQL type.

Avoid storing Java enum `ordinal()` if declaration order may change; inserting a single enum constant into the middle of the list can invalidate old numeric meanings.

### Types Without a Standard Mapping

GIS, network address, range, composite, extended XML, JSONB, and vendor types often require `Types.OTHER`, driver-specific objects, or SQL casts. **`Types.OTHER` only declares a type code**; it does not guarantee the driver can serialize a POJO on its own. Keep converters in the repository/adapter layer and test against each driver version and schema.

## 9. SQL `ARRAY` Differs from Java `List` and `IN` Parameters

A SQL ARRAY is **a single column value** containing multiple elements. JDBC represents it with `java.sql.Array`, not `List<T>` by default.

~~~java
// Illustrative snippet in code with JdbcTemplate jdbc and table
// sample_array(id BIGINT, tags VARCHAR ARRAY) on a DB supporting ARRAY.
jdbc.execute((org.springframework.jdbc.core.ConnectionCallback<Void>) con -> {
    java.sql.Array sqlArray =
            con.createArrayOf("VARCHAR", new String[] {"spring", "jdbc"});
    try (java.sql.PreparedStatement ps = con.prepareStatement(
            "UPDATE sample_array SET tags = ? WHERE id = ?")) {
        ps.setArray(1, sqlArray);
        ps.setLong(2, 7L);
        ps.executeUpdate();
    } finally {
        sqlArray.free();
    }
    return null;
});
~~~

This is a **JDBC API example**, not a standalone runnable program: the type name passed to `createArrayOf`, DDL, storage format, and SQL ARRAY support must be verified per DB. Some drivers do not support `createArrayOf` or require specific element type names (e.g., `text`, `integer`). Closing the statement and freeing the `Array` avoids holding driver resources too long.

When reading:

~~~java
// Illustrative snippet inside RowMapper.
java.sql.Array sqlArray = rs.getArray("tags");
Object javaArray = null;
if (sqlArray != null) {
    try {
        javaArray = sqlArray.getArray();
    } finally {
        sqlArray.free();
    }
}
// javaArray is usually a Java array chosen by the driver; check its type before casting.
~~~

The shape of `getArray()` may be `String[]`, `Integer[]`, `Object[]`, or another type; do not cast rigidly when the driver/schema has not been verified.

**Do not confuse with `IN (:ids)`:** when passing `List<Long> ids` to `NamedParameterJdbcTemplate`, Spring expands it into multiple `?` placeholders inside a SQL `IN` predicate; that is **multiple scalar binds**, not a SQL ARRAY in a single column. Empty ID sets and parameter count limits must be handled separately per DB.

## 10. BLOB, CLOB, Binary, and SQLXML

### `BINARY/VARBINARY` and `BLOB`

- Small files/images can use `byte[]` with `getBytes`/`setBytes`; check data size and memory limits.
- Large `BLOB`s can be read via `ResultSet.getBinaryStream(...)` or `Blob.getBinaryStream()`; only read while the `ResultSet`/connection is still valid, and close the stream properly.
- Spring provides `LobHandler` / `DefaultLobHandler` with APIs such as `getBlobAsBytes`, `getBlobAsBinaryStream`, `LobCreator.setBlobAsBytes`, and `setBlobAsBinaryStream`. Avoid loading hundred-MB BLOBs into `byte[]` if streaming is possible.

Simple example for small binary data:

~~~java
// Illustration in RowMapper when bytes column is a small VARBINARY/BLOB.
byte[] content = rs.getBytes("binary_content");
if (content != null) {
    System.out.println("bytes=" + content.length);
}
~~~

`byte[]` stores raw bytes, not an image or decoded text. If the data is inherently text, store it in a text column; when converting binary to text, specify an explicit charset and format rather than using `new String(bytes)` without a charset.

### `CLOB/NCLOB`

Small/medium text can usually be read with `getString`. For large content, use `getCharacterStream`, `Clob`, or `LobHandler` while JDBC resources remain open. Storing Unicode data requires choosing the right column type and charset/collation. Do not assume `CLOB` is UTF-8 blob bytes across all drivers.

### `SQLXML`

`SQLXML` is a dedicated JDBC data type using `getSQLXML`/`setSQLXML` if the DB supports it. Reading example:

~~~java
// Illustration in RowMapper on a DB supporting SQLXML.
java.sql.SQLXML xml = rs.getSQLXML("xml_payload");
String xmlText = null;
if (xml != null) {
    try {
        xmlText = xml.getString();
    } finally {
        xml.free();
    }
}
// Parse XML safely if converting to DOM or an object.
~~~

For untrusted XML data, configure the parser against XXE and entity expansion; do not instantiate parsers with external resource access unless required.

### `STRUCT` and Custom SQL Types

`java.sql.Struct` can hold multiple attributes, accessed via `getAttributes()`. Types such as PostgreSQL composites or Oracle OBJECTs must be verified with the driver, SQL type name, and attribute order. When calling stored procedures with complex IN/OUT types, Spring provides `SqlTypeValue`/`AbstractSqlTypeValue` to create bound objects on the actual connection, and `SqlReturnType` for OUT results. These are specialized extension points; `JdbcTemplate` does not automatically turn every `STRUCT` into a Java record.

## 11. Combining Converters with `RowMapper`, `BeanPropertyRowMapper`, and `DataClassRowMapper`

### Explicit Control with `RowMapper`

For tricky types, write a custom `RowMapper<T>` so you know precisely:

1. Which SQL columns are read and what their aliases are.
2. What type the driver actually returns (`String`, `UUID`, `java.sql.Array`, `PGobject`…).
3. How null, range, format/timezone, and conversion errors are handled.
4. How the domain object is constructed and JDBC resources are cleaned up.

For example, if column `state` stores a valid enum string, you can write:

~~~java
// Illustrative code fragment inside a RowMapper for an object with State.
String rawState = rs.getString("state");
State state = rawState == null ? null : State.valueOf(rawState);
~~~

`State` must be an enum declared in the application; `valueOf` throws `IllegalArgumentException` if the DB contains an invalid name. You can proactively map legacy names, translate them into a clear data error, or declare a policy for handling unknown states.

### Limits of Auto-Mapping

`BeanPropertyRowMapper` matches columns to corresponding JavaBean properties, supporting naming rules such as `first_name` → `firstName` and leveraging Spring's conversion mechanism where applicable. `DataClassRowMapper` is useful for supported constructors/records. However:

- It does not guarantee mapping vendor JSON/ARRAY/STRUCT/UUID into arbitrary classes.
- It does not automatically resolve invalid nulls for primitives.
- It does not automatically determine the business timezone from a `TIMESTAMP` lacking timezone info.
- SQL aliases and property names must match; schema changes can cause runtime failures or missing data.

For special types, prefer explicit mappers/converters and test on a real DB. When using application-layer converters, keep a single consistent definition for both write and read directions; fixing only one direction easily produces data that cannot round-trip.

### What Role Does Spring's `ConversionService` Play?

Spring Core `ConversionService` can convert between Java types when a corresponding converter is registered; `BeanPropertyRowMapper` can leverage it. However, **Java → Java conversion** is different from a **JDBC driver's SQL ↔ Java bind/extract**. Registering `Converter<String, UUID>` in Spring does not automatically make the driver support `setObject(UUID)` or turn PostgreSQL JSONB into a POJO. Place the right logic in the right layer.

## 12. Verifying Mappings on a Real Database

When SQL contains special columns, looking at the DDL alone may not be enough. You can inspect metadata inside a `RowMapper`/`ResultSetExtractor`:

~~~java
// Illustrative snippet when ResultSet rs is available.
java.sql.ResultSetMetaData md = rs.getMetaData();
for (int i = 1; i <= md.getColumnCount(); i++) {
    System.out.println(md.getColumnLabel(i)
            + " sqlType=" + md.getColumnType(i)
            + " typeName=" + md.getColumnTypeName(i)
            + " className=" + md.getColumnClassName(i));
}
~~~

These values are **information reported by the driver**, not a guarantee that every desired conversion will succeed. To truly verify, test input and output separately, null/non-null, boundary values, and driver versions.

Key testing checklist:

| Category | Scenarios to Test | What to Assert |
|---|---|---|
| Numeric | `DECIMAL(12,2)`, negative numbers, boundary values | Value and scale match business rules; no precision loss |
| Null | `NULL`, empty string, 0, false | All four cases are distinguished properly |
| Date/time | Month-end dates, different offsets, DST if applicable | No date/time shift, no wrong timezone interpretation of timestamps |
| Text | Vietnamese, emoji, whitespace, quotes | Unicode/escaping is preserved through parameter binding |
| UUID | Native UUID and CHAR/BINARY types if used | Bidirectional conversion, byte order, and Java class are correct |
| JSON/JSONB | JSON null, SQL NULL, arrays/objects, unknown keys | Distinguish JSON literal `null` from SQL `NULL`; stable parse/serialize |
| ARRAY | Empty array, null elements, large numbers | Element type and shape match driver behavior |
| LOB | Empty data, large data, streams | No lost bytes/characters, no resource leaks |
| ENUM/STRUCT | New/legacy values, field order | Converter has a compatibility policy |
| Driver | H2 tests and production DB | Do not infer production capability solely from H2 |

## 13. Common Errors and How to Handle Them

| Symptom | Cause | Resolution |
|---|---|---|
| SQL receives `NULL` with wrong type | Driver cannot infer type or null was bound without explicit type | Use `Types`, `SqlParameterValue`, `MapSqlParameterSource.addValue(name, null, sqlType)` |
| A `NULL` column becomes 0/false | Primitive getter `getInt/getBoolean` used without `wasNull` | Use a wrapper or call `wasNull()` immediately after the getter |
| Monetary amounts have rounding fractions | Using `double`/`float` for money calculations | Use `BigDecimal(String)` and explicit rounding rules |
| Overflow error when reading numbers | Narrowing wide `NUMERIC` to `int/long` unchecked | Use `BigDecimal`/`BigInteger` and `*ValueExact()` |
| `ClassCastException` casting `getObject` | Driver returns a different class than expected | Use typed getters where supported or a specific converter |
| Reading `TIMESTAMP` off by several hours | Implicit zone attachment, differing session/driver config, confusing instant with local time | Clarify column semantics and timezone, test UTC/offsets |
| Spring doesn't auto-map JSONB | JSON is a vendor type; driver returns JSON string/PGobject | Explicit serializer/parser and appropriate SQL cast |
| Error binding `UUID`/`ARRAY` | DB/driver does not support default bind type | Verify type name, dedicated API, and integration tests |
| BLOB/CLOB fails after exiting DAO | Reading stream/LOB after ResultSet/connection is closed | Read within callback/transaction lifecycle, free resources |
| DB `ENUM` does not exist in Java | Schema and code are on different versions | Converter handles new/legacy values, migration strategy |
| Bean auto-maps wrong column | Column alias doesn't match property or converter missing | Set explicit aliases, test `RowMapper`/`DataClassRowMapper` |
| Data with quotes breaks SQL | Concatenating values into SQL instead of binding parameters | Use `?`/`:name`, never interpolate values directly into SQL |

When a driver does not support a conversion, JDBC errors are typically wrapped by Spring into `DataAccessException` (often containing the underlying `SQLException`). Log permitted SQL, SQL type, DB/driver version, and error cause; avoid logging sensitive data or entire BLOB/JSON payloads containing personal information.

## 14. Process for Choosing Mappings When Building a DAO

1. **Read the actual schema:** SQL type, precision, scale, nullability, timezone semantics, and how the DB generates values.
2. **Choose the Java domain type:** prioritize semantic accuracy, e.g., `BigDecimal` for money, `LocalDate` for dates, `OffsetDateTime/Instant` per instant policy, `Integer` if nullable.
3. **Design the write path:** choose `setXxx` or `setObject` supported by the driver; declare `Types` for nulls and special types.
4. **Design the read path:** use `RowMapper` and explicit getters; handle `wasNull`, overflow, and special converters.
5. **Verify round-trip:** write → read on a real DB, testing both non-null and null, boundary values, Unicode, precision, instants, and extension types.
6. **Handle resources and errors:** Spring manages ordinary connections/statements; streams/`Array`/`SQLXML`/LOBs still need to be read and freed in the proper lifecycle.
7. **Add to integration tests:** H2 helps learn syntax, but cannot replace PostgreSQL, Oracle, SQL Server, MySQL, etc. when testing driver-specific types.

## 15. Self-Practice

1. In `SqlJavaTypeDemo`, replace `new BigDecimal("259.90")` with `new BigDecimal(259.90)`, print `toPlainString()`, and explain the difference.
2. Add a `notes VARCHAR(60) NULL` column. Insert null using `MapSqlParameterSource` with `Types.VARCHAR`, read it with `rs.getString`, and verify Java null.
3. Change the `rating` column to required `NOT NULL`, try inserting null. Distinguish the SQL constraint error from a Java mapping error.
4. Add a `TIMESTAMP WITH TIME ZONE` column if the DB/driver supports it, write an `OffsetDateTime` at `+07:00`, read it back, and compare using `toInstant()`.
5. On a real DB, add a UUID or JSONB column, build bidirectional conversion functions; test handling of SQL NULL and JSON literal null.
6. With an `ARRAY` or `BLOB` column, write a test that reads the data while ensuring resources are freed in the proper lifecycle.
7. Use `ResultSetMetaData` to inspect the type code, type name, and class name reported by the driver, and compare them against the Java types decided by the application.

## References

- Spring Framework 6.2 — JDBC, Common Problems with Parameter and Data Value Handling: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/parameter-handling.html
- Spring Framework — Using JdbcTemplate: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — NamedParameterJdbcTemplate: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html#jdbc-NamedParameterJdbcTemplate
- Spring Framework 6.2 — `MapSqlParameterSource` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html
- Java SE 17 — `ResultSet` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html
- Java SE 17 — `PreparedStatement` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html
- Java SE 17 — `Types` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Types.html
- pgJDBC — Java 8 Date/Time Mappings (example of a specific driver): https://jdbc.postgresql.org/documentation/query/#using-java-8-date-and-time-classes
