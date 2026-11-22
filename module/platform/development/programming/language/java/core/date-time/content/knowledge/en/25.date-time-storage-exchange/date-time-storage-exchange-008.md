# JDBC getObject() and setObject() with java.time: Checking Driver Capabilities

## 1. Available APIs Do Not Guarantee Identical Behavior Across All Drivers

JDBC allows passing many `java.time` values directly via `PreparedStatement.setObject` and reading them in a type-safe manner with `ResultSet.getObject(column, Class<T>)`. This approach preserves the exact semantics of a date, local time, or instant with an offset, rather than manually converting everything into strings.

However, the actual outcome depends on the **Java type + SQL type + driver version + database management system + connection configuration**. Running a program on JDK 21 does not automatically make an old driver fully support JDBC 4.2 mappings.

Therefore, you need to distinguish three layers: whether the method signature exists in the JDK, whether the driver implements the conversion, and whether data passing through a real column preserves the intended semantics and precision.

## 2. Choosing Mappings by Data Semantics

| SQL type per JDBC contract | Appropriate Java type | Semantics to preserve |
| --- | --- | --- |
| `DATE` | `LocalDate` | Date, without time |
| `TIME` | `LocalTime` | Local time, without date |
| `TIMESTAMP` | `LocalDateTime` | Local date and time, without offset/time zone |
| `TIME_WITH_TIMEZONE` | `OffsetTime` | Time with offset, if supported by DB/driver |
| `TIMESTAMP_WITH_TIMEZONE` | `OffsetDateTime` | Date and time with offset according to DB/driver capability |

These pairs are based on JDBC 4.2 mappings; not every database provides all five types with identical semantics. [JDBC 4.2: java.time mapping](https://jcp.org/aboutJava/communityprocess/maintenance/jsr221/JDBC4.2MR-January2014.pdf) `Instant`, `ZonedDateTime`, `YearMonth`, or `MonthDay` do not have a single universal direct mapping to pass into every `setObject` call by default.

For a concrete example: the pgJDBC documentation lists `LocalDate`, `LocalTime`, `LocalDateTime`, and `OffsetDateTime`, while stating that `Instant`, `ZonedDateTime`, and `OffsetTime` are not directly supported in this group. This is why you must read the documentation of the exact driver rather than only looking at the list of types in Java. [pgJDBC: Java Time](https://jdbc.postgresql.org/documentation/query/#using-java-8-date-and-time-classes)

If you need to store an instant from `Instant`, you can choose an `OffsetDateTime` contract in UTC when the DB/driver supports it. If you need to preserve a zone such as `Asia/Ho_Chi_Minh`, you must store the zone identifier separately if the SQL type does not retain it. An offset like `+07:00` is not equivalent to a zone ID.

## 3. Writing with setObject: Distinguishing the Overloads

Illustrative snippet inside a method with an existing `PreparedStatement ps`:

```java
LocalDate date = LocalDate.of(2024, 6, 15);
LocalDateTime local = LocalDateTime.of(2024, 6, 15, 12, 30);

ps.setObject(1, date);                      // Driver infers type from the object.
ps.setObject(2, local, java.sql.Types.TIMESTAMP); // Explicitly specifies the SQL type code.
```

There is also an overload accepting `SQLType`, such as `JDBCType.TIMESTAMP`. This is a different signature from the overload accepting the numeric code `Types.TIMESTAMP`. A driver may support one call path while not yet supporting the other; the default implementation of the `SQLType` overloads may throw `SQLFeatureNotSupportedException`.

Specifying the SQL type explicitly helps avoid ambiguous inference when the conversion is supported; it does not force a driver to perform an arbitrary mapping that the driver has not implemented. Do not treat replacing `Types.TIMESTAMP` with `JDBCType.TIMESTAMP` as a universally valid fix. [PreparedStatement.setObject](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html)

For `null` values, prefer an explicit SQL type:

```java
ps.setNull(1, java.sql.Types.DATE);
// Or setObject with an SQL type when that call path has been verified.
```

An untyped `setObject(index, null)` may not provide enough information for some drivers or queries. JDBC parameter indices start at 1.

## 4. Reading as the Expected Type

The following snippet assumes `rs` has already been positioned on a valid row via `rs.next()`:

```java
LocalDate date = rs.getObject("business_date", LocalDate.class);
LocalDateTime local = rs.getObject("scheduled_local", LocalDateTime.class);
OffsetDateTime occurred = rs.getObject("occurred_at", OffsetDateTime.class);
```

`getObject(column, LocalDate.class)` asks the driver to convert to the requested type if supported. It differs from `(LocalDate) rs.getObject(column)`: the call without a `Class` argument may return a default type such as `java.sql.Date`, causing the Java cast to fail.

For SQL `NULL`, typed object getters return `null`; check for `null` before calling methods on the result. Do not replace `NULL` with `LocalDate.MIN` or the epoch instant unless business rules explicitly define a fallback value. [ResultSet.getObject](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html)

## 5. Checking Environment Metadata and Support Evidence

`DatabaseMetaData` provides the driver name/version, DB name/version, and declared JDBC version. This information helps reproduce issues and cross-check documentation. However, there is no single flag like `supportsAllJavaTimeMappings()`.

`supportsConvert` and SQL type metadata are not sufficient proof that a specific `getObject(column, SpecificClass.class)` pair or a specific `setObject` overload will work. You must test the exact conversion pair you intend to use. [DatabaseMetaData](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/DatabaseMetaData.html)

Practical workflow:

1. Lock down the column semantics and SQL type in the schema.
2. Record the driver/DB versions, time zone configuration, and precision.
3. Cross-check the driver's official mapping documentation.
4. Test parameter binding and typed reading, then test writing/reading through a real column.
5. Verify the exact property that must be preserved: local date/time, instant, offset, or zone name.

## 6. Probe Program for PostgreSQL and pgJDBC

The following program requires **a running PostgreSQL instance and the pgJDBC JAR on the classpath**. It uses a `SELECT` query with SQL-typed parameters to verify binding and read-back; it does not create or modify any tables.

The sample values use nanosecond parts that are multiples of 1,000, matching PostgreSQL's microsecond precision for the example. For offset-based types, check with `toInstant()` to compare instants; it does not require the original offset to be preserved.

Save as `JdbcTimeProbe.java`:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Types;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.Objects;

public class JdbcTimeProbe {
    static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing environment variable: " + name);
        }
        return value;
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }

    public static void main(String[] args) throws Exception {
        String url = requiredEnv("JDBC_URL");
        String user = requiredEnv("JDBC_USER");
        String password = Objects.requireNonNull(
                System.getenv("JDBC_PASSWORD"), "JDBC_PASSWORD");
        LocalDate date = LocalDate.of(2024, 6, 15);
        LocalDateTime local = LocalDateTime.parse("2024-06-15T12:30:45.123456");
        OffsetDateTime offset =
                OffsetDateTime.parse("2024-06-15T12:30:45.123456+07:00");

        String sql = "SELECT CAST(? AS DATE) AS d, "
                + "CAST(? AS TIMESTAMP) AS l, "
                + "CAST(? AS TIMESTAMP WITH TIME ZONE) AS o, "
                + "CAST(? AS DATE) AS n";

        try (Connection connection = DriverManager.getConnection(url, user, password)) {
            DatabaseMetaData meta = connection.getMetaData();
            System.out.println("driver=" + meta.getDriverName() + " "
                    + meta.getDriverVersion());
            System.out.println("database=" + meta.getDatabaseProductName() + " "
                    + meta.getDatabaseProductVersion());

            try (PreparedStatement ps = connection.prepareStatement(sql)) {
                ps.setObject(1, date);
                ps.setObject(2, local);
                ps.setObject(3, offset);
                ps.setNull(4, Types.DATE);
                try (ResultSet rs = ps.executeQuery()) {
                    check(rs.next(), "No result row");
                    LocalDate readDate = rs.getObject("d", LocalDate.class);
                    LocalDateTime readLocal = rs.getObject("l", LocalDateTime.class);
                    OffsetDateTime readOffset = rs.getObject("o", OffsetDateTime.class);
                    LocalDate readNull = rs.getObject("n", LocalDate.class);

                    check(date.equals(readDate), "DATE mismatch");
                    check(local.equals(readLocal), "TIMESTAMP mismatch");
                    check(readOffset != null
                            && offset.toInstant().equals(readOffset.toInstant()),
                            "TIMESTAMP WITH TIME ZONE instant mismatch");
                    check(readNull == null, "SQL NULL mismatch");
                    System.out.println("roundTrip=PASS");
                }
            }
        }
    }
}
```

Compiling requires only JDK 17 or later:

```shell
javac --release 17 JdbcTimeProbe.java
```

Set `JDBC_URL`, `JDBC_USER`, and `JDBC_PASSWORD` according to your test environment configuration; do not hardcode passwords in source code. With a chosen pgJDBC JAR renamed to `postgresql.jar`, run on Windows:

```shell
java -cp ".;postgresql.jar" JdbcTimeProbe
```

On Linux/macOS, the classpath separator is `:` instead of `;`. Modern JDBC drivers register via the service provider mechanism when the JAR is on the classpath; if the JAR is missing or the URL does not match the driver, connecting may report that no suitable driver was found.

The names/versions on the first two lines vary by environment. If all bindings, conversions, and comparisons succeed, the final line is:

```text
roundTrip=PASS
```

This is the pass condition of the probe, not proof that every driver passes. To confirm application storage behavior, add `INSERT`/read-back tests against **the exact columns and precision of the real schema** in a test database. The cast-based query above does not test constraints, triggers, or column configurations.

## 7. Losses Not Detected by Using the Wrong Comparison Criterion

PostgreSQL normalizes `TIMESTAMP WITH TIME ZONE` data by instant; pgJDBC materializes `OffsetDateTime` results with a UTC offset. Thus, a value sent with `+07:00` may be read back as `Z` while still representing the same instant. Comparing with `OffsetDateTime.equals` requires both the local components and the offset to match, whereas `toInstant().equals(...)` checks for the same instant.

Do not assume `TIMESTAMP WITH TIME ZONE` always preserves the original offset string or zone name across all databases. If those are business data that must be preserved, design separate columns and test them separately.

Conversely, a `LocalDateTime` used for "09:00 store local time" must not have UTC arbitrarily attached just to pass through the driver. It does not yet represent an instant. Choosing a time zone at the conversion boundary must follow an explicit rule.

## 8. Distinguishing Unsupported Features from Other Errors

`SQLFeatureNotSupportedException` is a clear signal that a feature or call path is not implemented. Another `SQLException` may stem from a column type mismatch, conversion error, data range limit, invalid SQL, or connection failure; do not treat every `SQLException` as "the driver does not support `java.time`".

Record the exception class, `SQLState`, vendor error code, and cause chain along with the environment versions. Do not log passwords or URLs containing credentials. Legacy drivers that are not binary-compatible should be upgraded rather than worked around by casting results.

If you must use legacy APIs such as `java.sql.Date.valueOf(localDate)` and `toLocalDate()`, isolate the conversion in a tested adapter. For timestamps, distinguish `Timestamp.valueOf(localDateTime)` for local data from `Timestamp.from(instant)` for instants; the schema and configuration must still match those semantics. Do not silently fall back to strings or epochs for all errors and alter the data contract.

## 9. Hands-On Practice

1. Try reading a `DATE` column with the `LocalDate.class` getter, then compare it against the runtime type returned by `getObject` without a `Class` argument.
2. Test SQL `NULL`, leap dates, timestamps with fractional seconds, and values with non-UTC offsets.
3. Run the check with the exact driver version before and after an upgrade; document any differences with evidence.
4. Decide whether the application needs to preserve the same instant or also the original offset/zone, then choose the appropriate comparison criterion.

The expected outcome is a verified conversion contract on a specific environment: the right data types, explicit null handling, known precision, and preserved temporal semantics.