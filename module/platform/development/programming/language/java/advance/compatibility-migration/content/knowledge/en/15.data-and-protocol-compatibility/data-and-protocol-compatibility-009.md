# JDBC Driver Changes and Data Type Mapping

When upgrading Java, not every database error comes from SQL statements or business logic. A **JDBC driver** change can affect how an application connects, authenticates, reads metadata, maps SQL data types to Java, and writes Java values back to the database. With the same table, the same `SELECT` statement, and the same JDK version, two driver versions can still differ in the object returned by `ResultSet.getObject()`, rounding behavior, timezone handling, or rules for converting invalid values.

In **Java Advance Compatibility Migration**, updating the JDK often requires updating the JDBC driver due to class-file version requirements, TLS, `java.time` support, or compatibility with a newer database server. The danger is seeing the application start up and execute a few queries and concluding that the migration is complete. The hardest bugs to detect often lie in **data semantics**: being off by one day due to timezone, losing fractional digits of currency, changing how `NULL` is represented, truncating Unicode strings, or having a JSON/UUID value returned with a different Java type than before.

This lesson explains the compatibility layers related to JDBC, the SQL types that need to be tested, how to implement mappers with explicit contracts, and how to design test evidence when changing the driver or JDK.

## 1. JDBC Is the Abstraction Layer; the Driver Is the Implementation

JDBC provides the standard Java API for applications to connect to and execute operations against relational databases. Common interfaces belong to the `java.sql` and `javax.sql` packages:

- `Connection`: logical connection to the database and transaction management.
- `Statement` and `PreparedStatement`: execute SQL; PreparedStatement supports parameter binding.
- `ResultSet`: read result rows.
- `ResultSetMetaData` and `DatabaseMetaData`: inspect column types and driver/database characteristics.
- `DataSource`: provides connections, usually managed by a pool or framework.
- `SQLType`, `JDBCType`, `Types`: represent standard SQL type codes.

A **JDBC driver** implements or provides the components needed for these interfaces to communicate with the protocol, server, and data types of a specific database management system.

Overview diagram:

~~~text
Java application / repository / ORM
              |
         JDBC API
              |
     DataSource / Connection pool
              |
         JDBC driver
              |
 Database wire protocol + TLS + auth
              |
       Database server
              |
          SQL schema
~~~

Changing the driver can affect upper layers even when source code does not change. The driver has discretion over many conversions and over how vendor extensions are handled; JDBC standardizes part of the contract, but it does not make every database or every driver behave the same.

## 2. Distinguishing JDK, Driver, and Database Server Versions

A migration has at least three version axes that must be controlled separately:

| Axis | Key Question | Risk Example |
|---|---|---|
| JDK / JVM | Is the driver compiled for a release supported by the runtime? | `UnsupportedClassVersionError` |
| JDBC driver | Does the driver support the JDBC API, authentication, TLS, mapping, and database protocol in use? | `SQLFeatureNotSupportedException`, different mapping |
| Database server | Does the driver support the corresponding server version, data types, and dialect? | Handshake failure, different metadata, different SQL |

If an application moves from JDK 11 to JDK 21 while upgrading both the driver and the server at the same time, when a `Timestamp` bug appears it will be difficult to know which layer caused it without a separate baseline for each axis.

A better practice is to record:

~~~yaml
environment:
  java:
    feature: 21
    distribution: "record actual JDK vendor and build"
  jdbcDriver:
    artifact: "vendor JDBC driver artifact"
    version: "record resolved version"
  database:
    product: "record database product"
    version: "record server version"
  deployment:
    os: "record OS and architecture"
    timezone: "UTC"
~~~

This is an information-recording template, not a required JDBC configuration. You should not infer from the JAR filename alone that the runtime is actually loading the intended driver version.

## 3. Why Changing the Driver Can Change Mapping Even When the Java API Does Not Change

JDBC defines many getters and setters such as `getString`, `getInt`, `getBigDecimal`, `getTimestamp`, and `getObject`. However, the path from the database storage type to the Java object can depend on:

1. The SQL column type and metadata returned by the server.
2. The server version and protocol.
3. The driver/version and its JDBC support level.
4. The getter method chosen by the application.
5. `NULL` values and framework converters.
6. Timezone, locale, encoding, and session settings.
7. The ORM library, dialect, and custom `AttributeConverter`.
8. Driver configuration properties that affect conversion; names and meanings vary by vendor.

Example:

~~~java
Object value = resultSet.getObject("created_at");
~~~

The application should not assume `value` is always `java.sql.Timestamp` for every temporal column type, every database, and every driver. If code casts directly:

~~~java
Timestamp timestamp = (Timestamp) resultSet.getObject("created_at");
~~~

a mapping change can result in `ClassCastException`, or the value may still have the same class but different timezone semantics.

When building a long-lived data API, you should choose getters according to the **desired data type contract** and explicitly handle conversions that may differ, rather than relying on the concrete class returned by a current driver.

## 4. JDBC Changes to Inventory Before Upgrading the Driver

You should start from the actual integration points:

| Component | What to Check |
|---|---|
| Driver dependency | Artifact, version, JDBC support, minimum Java version |
| Driver loading | `DriverManager`, service discovery, classpath/module path |
| DataSource/pool | Driver class, connection URL, credentials, timeouts, validation |
| Authentication/TLS | TLS configuration, truststore, hostname validation, database auth plugin |
| Numeric mapping | DECIMAL/NUMERIC, INTEGER/BIGINT, unsigned types, scale and rounding |
| Temporal mapping | DATE, TIME, TIMESTAMP, timezone, DST, precision |
| Nullable columns | `NULL` versus 0/false/empty values |
| Text/binary | Unicode, charset, collation, BLOB/CLOB/stream |
| Vendor types | UUID, JSON, ARRAY, XML, enum, geometry |
| SQL metadata | Column label/name, alias, generated keys, type name |
| Transactions | Autocommit, isolation, savepoints, batch, commit/rollback |
| ORM mapping | Dialect, converters, custom types, schema validation |
| Runtime | Class file, modules, resource lifecycle, driver behavior in container |

A driver change is only safe within the scope that the application uses and has tested. "Driver supports JDK 21" does not prove that all mappings and transactions of the application remain unchanged.

## 5. Table of SQL Types and Commonly Used Java Types

The table below is a **mapping guideline**, not a guarantee that every vendor returns these exact classes through `getObject()`. For database-specific columns, consult the documentation for the specific driver/version.

| SQL type | Commonly Chosen Java Type | Notes |
|---|---|---|
| `SMALLINT`, `INTEGER` | `short`, `int`, or wrapper | Check value bounds and `NULL` |
| `BIGINT` | `long` / `Long` | Do not blindly assign to `int` |
| `DECIMAL`, `NUMERIC` | `BigDecimal` | Essential for money and exact numbers |
| `REAL`, `FLOAT`, `DOUBLE` | `float` / `double` | Approximate numbers with binary rounding error |
| `BOOLEAN` / `BIT` | `boolean` / `Boolean` | Behavior depends on dialect, especially multi-bit BIT |
| `CHAR`, `VARCHAR`, `LONGVARCHAR` | `String` | Charset, trailing spaces, collation |
| `BINARY`, `VARBINARY` | `byte[]` | Data copying, size limits |
| `BLOB` | `Blob` or stream/bytes | Lifetime and memory management |
| `CLOB`, `NCLOB` | `Clob` / `NClob` or stream/string | Unicode and reading large data |
| `DATE` | `LocalDate` or `java.sql.Date` | Has no time-of-day |
| `TIME` | `LocalTime` or `java.sql.Time` | Has no inherent timezone |
| `TIMESTAMP` without timezone | `LocalDateTime` or `Timestamp` | Does not inherently represent a global instant |
| `TIMESTAMP_WITH_TIMEZONE` | `OffsetDateTime` when supported by driver | Vendors differ on semantics and offset storage |
| `SQLXML` | `SQLXML` | Lifecycle, encoding, XML input security |
| `ARRAY` | `java.sql.Array` | Element type and vendor support |
| Vendor JSON/UUID/enum | `String`, `UUID`, or vendor object | Do not apply one mapping across all databases |

The `Types.TIMESTAMP_WITH_TIMEZONE` type code and `java.time` API can be used under the JDBC 4.2 contract when supported by the driver, but you must not assume all older drivers implement them uniformly.

## 6. `getObject()` and Typed `getObject(..., Class)`

There are two common ways to read values:

~~~java
Object raw = resultSet.getObject("issue_date");

LocalDate date =
        resultSet.getObject("issue_date", LocalDate.class);
~~~

The first form returns an object chosen by the driver according to its default mapping. The second form asks the driver to convert to the specified Java type if the conversion is supported. If unsupported, the driver may throw `SQLException` or `SQLFeatureNotSupportedException`.

You should not write:

~~~java
LocalDate issueDate =
        (LocalDate) resultSet.getObject("issue_date");
~~~

just because one driver version happened to return `LocalDate`. Another version may return `java.sql.Date` for the same column.

Example of explicit typed access:

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class InvoiceMapper {
    public static InvoiceRow read(ResultSet rs) throws SQLException {
        long id = rs.getLong("invoice_id");
        BigDecimal amount = rs.getBigDecimal("amount");
        LocalDate issuedOn =
                rs.getObject("issue_date", LocalDate.class);

        return new InvoiceRow(id, amount, issuedOn);
    }
}
~~~

`InvoiceRow` is an application-defined domain type. The example assumes the `invoice_id` column is non-nullable and that the driver supports reading `DATE` into `LocalDate`.

If the driver does not support typed `getObject`, place the conversion inside a tested adapter, for example using `getDate` and `toLocalDate` for `DATE`:

~~~java
java.sql.Date sqlDate = rs.getDate("issue_date");

LocalDate issuedOn = sqlDate == null
        ? null
        : sqlDate.toLocalDate();
~~~

Even this fallback must be tested at timezone/driver boundaries when the server uses temporal types with special semantics. Do not turn a vendor-specific fallback into a universal rule without tests.

## 7. `NULL`: Distinguishing Missing Data from Default Values

A dangerous data bug occurs when reading a nullable column with a primitive getter.

Example:

~~~java
int discountPercent = rs.getInt("discount_percent");
~~~

If the column has SQL `NULL`, a primitive getter usually returns `0`. To know whether the value is actually 0 or `NULL`, check `wasNull()` **immediately after calling the getter**:

~~~java
int raw = rs.getInt("discount_percent");
Integer discountPercent = rs.wasNull() ? null : raw;
~~~

Do not call another getter before `wasNull()`, because `wasNull()` reflects the most recent read operation.

For reference types:

~~~java
BigDecimal total = rs.getBigDecimal("total_amount");
String note = rs.getString("note");
~~~

SQL `NULL` is normally represented by Java `null`. When upgrading the driver, verify:

- Nullable and NOT NULL columns are handled properly by mappers.
- `NULL` is not turned into `0`, `false`, an empty string, or epoch time.
- ORM converter logic preserves null semantics.
- When binding nullable parameters, the JDBC type is specified explicitly if the driver requires type information.

Example of typed null binding:

~~~java
if (note == null) {
    ps.setNull(2, java.sql.Types.VARCHAR);
} else {
    ps.setString(2, note);
}
~~~

`setObject(index, null)` may not be unambiguous enough for specific drivers or types. When the column type is known, `setNull(index, Types.XXX)` or `setObject` with a target SQL type usually relies less on inference.

## 8. DECIMAL, NUMERIC, and Precision-Loss Risks

Money, balances, taxes, financial rates, and values requiring exact precision should be handled using appropriate types, usually SQL `DECIMAL(p, s)` or `NUMERIC(p, s)` and Java `BigDecimal`.

Example table:

~~~sql
CREATE TABLE invoice (
    invoice_id BIGINT PRIMARY KEY,
    total_amount DECIMAL(18, 4) NOT NULL
);
~~~

Reading:

~~~java
BigDecimal totalAmount = rs.getBigDecimal("total_amount");
~~~

You should not read as `double` and then construct `new BigDecimal(double)` when exact decimal representation must be preserved: binary floating-point numbers cannot represent many decimal fractions such as `0.1` accurately.

Binding a value:

~~~java
BigDecimal amount = new BigDecimal("12345.6700");
ps.setBigDecimal(1, amount);
~~~

Things to check when changing the driver:

1. **Precision:** what is the maximum number of digits stored and read?
2. **Scale:** is the number of digits after the decimal point preserved?
3. **Rounding:** does a write exceeding the scale get rounded, truncated, fail with an error, or get handled by the database under a specific mode?
4. **Overflow:** does exceeding precision raise an error or perform a conversion?
5. **Equality:** `BigDecimal.equals()` considers scale as well, whereas `compareTo()` compares numerical value; choose test assertions that match the contract.
6. **Metadata:** do `getPrecision()` and `getScale()` match expectations when using views, expressions, or aggregates?
7. **Nullability:** `NULL` values must not be conflated with 0.

Do not assume that a new driver that "rounds better" is compatible with already stored data. A difference of one unit in the last digit can affect totals and reconciliation.

## 9. INTEGER, BIGINT, Unsigned Types, and Value Bounds

An SQL column may use `INTEGER` or `BIGINT`, while its value range and unsigned policy depend on the database.

Example:

~~~java
long customerId = rs.getLong("customer_id");
~~~

If the database uses an unsigned type capable of exceeding `Long.MAX_VALUE`, do not assume `long` can represent the full domain. A driver may provide a different conversion or fail when the value is too large.

Tests you should include:

- Values 0, 1, and -1 if allowed by the domain.
- Boundaries `Integer.MAX_VALUE` / `Integer.MIN_VALUE`.
- Values near the `Long.MAX_VALUE` limit.
- Values outside the representable range of the Java type used by the mapper.
- `NULL` for nullable columns.
- Large server-side generated keys.

Choose Java types based on the **data/domain contract**, not just whatever type the old driver returned on the happy path.

## 10. DATE, TIME, and TIMESTAMP: Do Not Mix Calendar Date/Time with Instants

Date and time handling is one of the highest-risk areas when upgrading a JDBC driver. Distinguish carefully:

| Type | Appropriate Java Meaning in Many Cases | Things to Note |
|---|---|---|
| SQL `DATE` | `LocalDate` | Calendar date, with no inherent time of day or timezone |
| SQL `TIME` | `LocalTime` | Time of day, does not inherently represent an instant |
| SQL `TIMESTAMP` without timezone | `LocalDateTime` | Local date and time, lacking timezone/offset |
| SQL `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` if supported by driver/dialect | Semantics and offset storage vary by database |
| Event at an absolute point in time | `Instant` at the domain layer | Requires an explicit convention mapping between Instant and SQL type |

Database management systems differ in type names, precision, storage, and how temporal values are converted. A column named `timestamp` does not guarantee identical semantics across databases.

### 10.1. Reading DATE Using java.time When Supported

~~~java
LocalDate billingDate =
        rs.getObject("billing_date", LocalDate.class);
~~~

### 10.2. Reading TIMESTAMP Without Timezone

~~~java
LocalDateTime scheduledAt =
        rs.getObject("scheduled_at", LocalDateTime.class);
~~~

If the data genuinely represents a local scheduled appointment, `LocalDateTime` may be a reasonable model, with the appointment's zone managed separately if an instant needs to be determined.

If it is a global event timestamp, an exact `Instant` cannot be inferred automatically from `LocalDateTime` without a timezone convention.

### 10.3. TIMESTAMP WITH TIME ZONE Does Not Mean Storing the Timezone Region

Some databases normalize timestamps to UTC or retain an offset; others return an offset based on session/server settings. An **offset** such as `+07:00` and a timezone region such as `Asia/Ho_Chi_Minh` are not the same. A region carries DST/historical rules, whereas an offset is a fixed difference from UTC at a given point in time.

Example of reading if supported by the driver:

~~~java
OffsetDateTime eventTime =
        rs.getObject("event_time", OffsetDateTime.class);
~~~

From `OffsetDateTime`, you can convert to `Instant` via `toInstant()`, but you must verify the offset value and database semantics. Do not assume the driver will always return the exact offset passed in during insert.

### 10.4. Temporal Tests Must Include Boundaries

The test suite should include:

- Near midnight in UTC and in the business timezone.
- End-of-month dates, leap years, and calendar transition years if relevant.
- Values with microsecond/nanosecond fractional seconds and differing precisions.
- DST transition intervals for timezones with DST.
- Values with negative and positive offsets.
- `NULL` and min/max dates supported by the database.
- Changing the JVM default timezone or database session timezone.

If you only test midday values in a single timezone, conversion changes can remain hidden.

## 11. Legacy `java.sql.Date`, `Time`, and `Timestamp`

Many older applications use:

~~~java
java.sql.Date date = rs.getDate("billing_date");
java.sql.Time time = rs.getTime("scheduled_time");
java.sql.Timestamp timestamp = rs.getTimestamp("created_at");
~~~

These classes still exist in the JDBC API, but they are not always the best domain representation. In modern Java, consider `java.time` to separate calendar dates, local times, offsets, and instants.

Even so, do not mechanically replace them with:

~~~java
Instant instant = rs.getTimestamp("created_at").toInstant();
~~~

if the column does not carry clear instant semantics. The result may depend on the timezone used by the driver/JVM to interpret a timezone-less timestamp.

Some JDBC APIs have overloads taking a `Calendar`, such as `getTimestamp(column, calendar)`. They can be useful for certain drivers and schemas, but they are **not a universal fix for all timezone issues**. You need to define clearly what the column stores and test against the specific database and driver.

For legacy code relying on `Timestamp.equals()`, `toString()`, or `getTime()`, observe precision and conversion differences before switching to `Instant` or `LocalDateTime`.

## 12. Binding Temporal Parameters Intentionally

JDBC 4.2 added support for working with many `java.time` types, but actual driver support levels must be verified.

Example:

~~~java
LocalDate invoiceDate = LocalDate.of(2026, 11, 12);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO invoice (invoice_id, issue_date) VALUES (?, ?)")) {
    ps.setLong(1, 42L);
    ps.setObject(2, invoiceDate, java.sql.JDBCType.DATE);
    ps.executeUpdate();
}
~~~

Some drivers require traditional `setDate` forms or custom conversions. If typed `setObject` is not supported on the driver in use, an adapter can use:

~~~java
ps.setDate(2, java.sql.Date.valueOf(invoiceDate));
~~~

Even so, verify the actual mapping against the SQL `DATE` column. Do not convert a `LocalDateTime` to `Timestamp` without controlling timezone, precision, and data semantics.

When the target SQL type is known, pass it explicitly to reduce automatic inference. However, standard type names do not guarantee identical implementation across all databases.

## 13. BOOLEAN, BIT, and Status-Flag Representations

Database management systems may offer `BOOLEAN`, `BIT`, or small numeric types used as flags. Each type has its own characteristics, and dialects may represent `true/false` values differently.

Example:

~~~java
boolean active = rs.getBoolean("is_active");
boolean wasNull = rs.wasNull();
~~~

If the column is nullable, `false` could be a real value or simply the primitive result for SQL `NULL`. When three states are needed:

~~~java
Boolean activeValue = wasNull ? null : active;
~~~

Avoid confusing `BIT(1)` with multi-bit bit-strings in databases that distinguish the two. The driver may return byte[], Boolean, or a vendor type depending on the SQL type and getter chosen.

Tests must cover true, false, null, and any special representations used by the schema/dialect.

## 14. Strings, Unicode, Encoding, and Collation

A JDBC driver does more than turn bytes into characters. Databases also have charsets/collations, normalization forms, trailing spaces, and column lengths measured in characters or bytes.

Example where an application reads:

~~~java
String displayName = rs.getString("display_name");
~~~

When changing the driver or server, check:

- Diacritical Vietnamese text and non-ASCII characters.
- Emoji and Unicode characters outside the Basic Multilingual Plane.
- Empty string versus SQL `NULL` according to database semantics.
- How `CHAR` handles padding/trailing spaces.
- Whether column length is measured in bytes or characters.
- Encoding at both the connection and database levels.
- Collation affecting sorting as well as case-insensitive and accent-insensitive comparisons.
- How the driver returns `NCHAR` / `NVARCHAR` data if supported by the database.

An application starting up and returning ASCII data correctly does not prove Unicode mapping compatibility.

Do not silently trim or normalize strings after upgrading the driver to mask a difference that occurred. If business contracts require normalization, define and test it transparently.

## 15. BLOB, CLOB, and Large Data

For large binary or text data, drivers may support:

- `getBytes` / `setBytes` for small data.
- `getBinaryStream` / `setBinaryStream` for streams.
- `getBlob` / `getClob` / `getNClob`.
- `getCharacterStream` / `setCharacterStream`.

One point to watch is that stream/LOB lifetimes may depend on `ResultSet`, `Statement`, and `Connection`. If a stream is returned outside after closing the connection, some drivers may fail or silently buffer all data in memory.

Example of reading bytes when the size is within acceptable limits:

~~~java
byte[] payload = rs.getBytes("payload");
~~~

For large files, prefer streaming designs and closing resources promptly. Test:

- Empty files and large files.
- Binary data containing all byte values, without string conversion.
- Multi-MB/GB payloads according to actual needs.
- Multiple concurrent clients.
- Behavior on connection drops and retries.
- How memory usage changes between the old and new driver.

Do not attribute every performance difference to the JDK if the driver changed its fetch/buffering strategy.

## 16. UUID, JSON, ARRAY, SQLXML, and Vendor-Specific Types

These types often have varying support across database management systems and driver versions.

### 16.1. UUID

Some databases have a native `UUID` type; others store UUIDs as `CHAR(36)` or binary. `getObject` may return `UUID`, `String`, or another type depending on the driver and type.

If the schema stores standard strings, it can be converted in a controlled way:

~~~java
String rawUuid = rs.getString("external_id");

UUID externalId = rawUuid == null
        ? null
        : UUID.fromString(rawUuid);
~~~

This is not a formula for every UUID schema. If the column is a native/binary type, use the corresponding mapping supported by the driver and database.

### 16.2. JSON

JSON may be stored as a native JSON/JSONB type, string, or vendor-specific binary format. Do not assume:

~~~java
String json = (String) rs.getObject("metadata");
~~~

is always valid. The driver may return a vendor-specific object. Build an adapter per driver/version or use documented getters/mechanisms, then deserialize JSON using the application's managed library and validate the schema.

An easily overlooked bug is when the driver returns the same JSON content but changes numeric representation, key ordering, duplicate keys, or null types. Validate against the **data contract**, not just string comparison if key ordering is not guaranteed.

### 16.3. ARRAY

When the database supports SQL arrays:

~~~java
java.sql.Array array = rs.getArray("tags");

if (array != null) {
    try {
        Object values = array.getArray();
        // Convert according to element type and driver contract.
    } finally {
        array.free();
    }
}
~~~

The element type and returned object/array type can differ. Do not assume every array is `String[]`. Check null elements, empty arrays, and multidimensional arrays if used by the system.

### 16.4. SQLXML

`SQLXML` has its own lifecycle and can be returned via `getSQLXML`. For XML data from untrusted sources, parser/transformer processing must follow the application's XML security policy. Do not weaken XML protection settings to restore compatibility.

## 17. Do Not Rely Blindly on `ResultSetMetaData` from a Single Driver

A dynamic mapper may infer types from metadata:

~~~java
ResultSetMetaData md = rs.getMetaData();

for (int i = 1; i <= md.getColumnCount(); i++) {
    System.out.println(md.getColumnLabel(i));
    System.out.println(md.getColumnType(i));
    System.out.println(md.getColumnTypeName(i));
    System.out.println(md.getPrecision(i));
    System.out.println(md.getScale(i));
}
~~~

When changing the driver, these values can differ because:

- The driver fixed a bug in reporting SQL types.
- The database changed how expressions/aggregates/views are described.
- `getColumnLabel` reflects the alias while `getColumnName` reflects the source name as provided by the driver/database.
- `getColumnClassName` describes the expected Java class of the default getter under specific conditions.
- Precision/scale of a computed expression or vendor type may be reported differently.

If a generic mapper uses metadata to choose a Java class, test SQL aliases, case sensitivity, joins, and computed columns thoroughly. Do not treat metadata as an immutable promise beyond the JDBC and vendor specifications.

Example:

~~~sql
SELECT total_amount AS total FROM invoice
~~~

In mappers, it is usually better to look up values by the declared column label `total`. Accessing by the physical name `total_amount` may be driver-dependent in some contexts.

## 18. Driver Loading, Classpath, and Module Path

Since JDBC 4.0, drivers can be discovered and registered automatically via the appropriate service-provider mechanism. Many modern applications do not need:

~~~java
Class.forName("com.vendor.jdbc.Driver");
~~~

just to register the driver, provided the right driver artifact is on the classpath/module path and visible to service discovery. However, older code may reference the driver class name directly, and that name can change across driver generations or when switching vendors.

Example using the standard API:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;

Connection connection = DriverManager.getConnection(
        "jdbc:example://database-host:5432/app",
        "app_user",
        "credential-from-secure-source");
~~~

The URL here is a placeholder; in real applications, the URL format and properties depend on the driver. Do not hardcode credentials in source code. The example above does not depict a secure production configuration.

Things to check:

- The driver JAR actually resolved at runtime.
- Whether the driver version matches the JVM class-file baseline.
- Whether service discovery still works after building a fat/shaded JAR.
- What module descriptor or automatic module name the driver has when moving to the module path.
- Whether the framework/app server loads another driver in a different class loader.
- Whether two driver versions coexist and cause the wrong one to be selected.
- Driver registration/deregistration and thread/context class loader behavior in container environments.

Do not blindly add `requires java.sql` to every project if they are not modularized yet; distinguish classpath applications from named-module applications.

## 19. DataSource, Connection Pools, and Connection Ownership

In real applications, `DataSource` is preferred for connection management, especially with pooling and transaction frameworks.

Model example:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;

public final class ConnectionCheck {
    private final DataSource dataSource;

    public ConnectionCheck(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean canConnect() throws Exception {
        try (Connection conn = dataSource.getConnection()) {
            return conn.isValid(3);
        }
    }
}
~~~

`DataSource` may be wrapped by a pooling library around a driver-specific DataSource. When changing the driver, check:

- Whether the driver class and URL/configuration properties are still valid.
- Whether the validation query or `Connection.isValid` works.
- How connection timeout, socket timeout, and login timeout differ.
- Whether `autoCommit`, transaction isolation, read-only, and catalog/schema are reset when returning connections to the pool.
- Whether session timezone, search path, and encoding leak across connection reuses.
- Whether prepared statement caches, server-side prepares, and fetch sizes behave differently.
- Whether broken connections are evicted from the pool and recreated appropriately.
- Whether leak detection and pool size limits suit real workloads.

A new driver may handle network timeouts differently than the old driver. Verify in the corresponding database/proxy environment, not just by opening one connection successfully.

## 20. Transactions, Autocommit, and Isolation

A change in driver or pool can affect transaction semantics, even when column mappings are right.

JDBC pattern example:

~~~java
Connection conn = dataSource.getConnection();

try {
    conn.setAutoCommit(false);

    try (PreparedStatement ps = conn.prepareStatement(
            "UPDATE account SET balance = ? WHERE account_id = ?")) {
        ps.setBigDecimal(1, new BigDecimal("120.50"));
        ps.setLong(2, 42L);
        ps.executeUpdate();
    }

    conn.commit();
} catch (SQLException failure) {
    try {
        conn.rollback();
    } catch (SQLException rollbackFailure) {
        failure.addSuppressed(rollbackFailure);
    }
    throw failure;
} finally {
    conn.close();
}
~~~

This is an illustrative pattern; in a system with a transaction manager/connection pool, code must let the framework manage connections and state per the framework's contract, avoiding breaking active transactions.

Things to test when upgrading the driver:

- `autoCommit` and how the connection pool resets state.
- Default transaction isolation and levels supported by the server.
- Savepoints, rollbacks, and commits on error branches.
- Generated keys and how the driver returns results after inserts.
- Batch execution, update counts, and partial failures.
- Deadlock/timeout exceptions and `SQLState`.
- Connection acquisition/closing times, network errors, and retries.
- How the framework maps `SQLException` to domain exceptions.

### 20.1. Checking SQLState and Vendor Error Codes

An application may classify errors based on:

~~~java
String state = exception.getSQLState();
int vendorCode = exception.getErrorCode();
~~~

A new JDBC driver may refine or change exception/subclass mapping, SQLState, or vendor codes in certain situations. If retry logic relies on error codes, test actual deadlocks, unique constraints, connection resets, and syntax errors.

Do not retry every `SQLException`. Some errors are permanent or can cause side effects if the operation is not idempotent.

## 21. PreparedStatement: Staying Safe and Explicitly Typed

Driver migration is never a reason to fall back to SQL string concatenation:

~~~java
// Do not do this:
String sql = "SELECT * FROM customer WHERE name = '" + name + "'";
~~~

Instead, use parameter binding:

~~~java
String sql = "SELECT customer_id FROM customer WHERE name = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, name);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("customer_id"));
        }
    }
}
~~~

However, parameter binding does not automatically normalize every data type. For `DECIMAL`, `DATE`, `TIMESTAMP`, JSON, or vendor types, specify types and conversions that match the schema.

Drivers/servers may differ in server-side prepared statements, parameter inference, and plan caching. If type mismatch errors appear after upgrading the driver, fix the binding or declare types explicitly according to documentation rather than switching to SQL concatenation.

## 22. ORM/JPA: The Driver Is One Layer in the Mapping Chain

Applications using JPA/Hibernate or another ORM usually do not call `ResultSet.getObject` directly. Even so, the driver still performs conversions at the lower layer.

Example flow:

~~~text
Database SQL type
       |
JDBC driver conversion
       |
ORM JDBC type/dialect
       |
AttributeConverter / custom UserType
       |
Java entity attribute
       |
Business DTO / API
~~~

When changing the driver while also upgrading Hibernate or switching dialects, multiple layers can change at once. Try to isolate changes to pinpoint causes:

1. Keep the database schema fixed, upgrade the driver, and test the existing repository/ORM.
2. Upgrade the framework/dialect if required by the new driver, and retest.
3. Perform controlled schema migrations if needed.
4. Verify the data API exposed to consumers.

Cases to pay attention to with ORMs:

- `BigDecimal` precision/scale mapping.
- `LocalDateTime`, `Instant`, and timestamp timezones.
- Enums stored by ordinal or string.
- UUID/JSON custom types.
- LOB lazy loading and session lifetime.
- Generated identifiers and sequence/identity strategies.
- Dirty checking with mutable objects.
- Query pagination, fetch size, and dialect-specific SQL.
- Schema validation when driver metadata changes.

Do not resolve an ORM column-type warning by automatically altering the production schema without evaluating data impact and backward compatibility.

## 23. Testing Schema Migration Concurrently While Separating Evidence

Driver changes often happen within a larger project that also includes schema changes. Two changes can mask each other:

- The schema changes `INT` to `BIGINT`.
- The driver changes the Java type of a vendor-specific column.
- The ORM changes an attribute mapping.
- The service exposes a new API type.

You should test in clear pairs:

| Driver | Schema | Purpose |
|---|---|---|
| Old | Old | Baseline |
| New | Old | Isolated impact from the driver |
| Old | New | If still supported, isolated impact of the schema |
| New | New | Target migration state |

Not all combinations are supported, especially if the server/database version changes. If a combination cannot be run, explicitly record **NOT_SUPPORTED** or **NOT_TESTED**, rather than treating it as PASS.

With rolling deployments running multiple application versions, ensure the schema during the transition period satisfies both old and new consumers if that is an operational requirement. Expand–migrate–contract may be needed for columns, constraints, or JSON formats.

## 24. Designing a Boundary-Data Mapping Test Suite

Do not test only a single sample record. Build fixtures with values likely to expose conversion differences.

| Group | Representative Cases |
|---|---|
| Numeric | 0, negative, max/min, overflow, `DECIMAL(18,4)`, rounding |
| Nullable | SQL NULL, 0/false/empty values, NOT NULL |
| Temporal | UTC, local zones, DST, midnight, leap day, fractional seconds |
| Strings | Vietnamese, emoji, Unicode beyond BMP, trailing spaces, near max length |
| Binary | Bytes 0x00/0xFF, empty blob, large payloads |
| UUID | Valid string, native UUID, binary representation, null |
| JSON | Null, large numbers, nested objects, Unicode, optional fields |
| Arrays | Empty, null elements, multi-dimensional if supported |
| SQLXML | XML with proper encoding and schema, invalid data |
| Transactions | Commit, rollback, deadlock, retry, batch partial failure |
| Metadata | Aliases, computed columns, views, joins, precision/scale |
| Connection | Timeouts, pool recycling, failover, session settings |

A good mapping test must compare **values and semantics**, not just the returned class. For example, with money, compare numeric value and scale according to the contract; with timestamps, compare instant or local date-time depending on the designed column type.

### 24.1. Round-Trip Tests

A generally useful test:

1. Write Java values using the new driver.
2. Read them back through that same driver.
3. Compare against the data contract.
4. If backward compatibility is required, read using the old driver.
5. Test data created by the old driver.
6. Verify column types and precision have not changed unexpectedly.

Not every round-trip preserves input data verbatim: the database may normalize timezones, truncate precision, or reorder JSON. What must be verified is the **guaranteed** behavior and that any differences are approved.

### 24.2. Testing Against Two Driver Versions

How to organize the fixture:

~~~text
same SQL schema
same input dataset
same server version
same JDK/runtime where supported
  |
  +-- Driver A -> capture values/errors/metadata
  |
  +-- Driver B -> capture values/errors/metadata
  |
compare according to explicit data contracts
~~~

If driver A does not support the new JDK, it may be necessary to test on the source and target JDKs respectively. In that case, results reflect the driver/JDK combination rather than isolating the driver's impact; the report must clearly state this limitation.

## 25. Checking Runtime Compatibility and Driver Artifacts

A newer driver version may require a higher minimum JDK than the version the application is currently running on. Even if application source compiles cleanly, the JVM can still throw:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version of the Java Runtime
~~~

Compare the driver's JDK requirements, class-file major version, dependencies, and runtime environment. Some common values:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

You can inspect the class-file version of a class inside a JAR:

~~~bash
javap -verbose -classpath jdbc-driver.jar \
  com.vendor.DriverClass
~~~

`com.vendor.DriverClass` is a placeholder; replace it with an actual class in the driver. Checking one class does not prove all classes and dependencies are compatible, especially with multi-release JARs; integration tests must be run on the supported runtime.

### 25.1. Gradle: Pinning the Right Driver Version

Kotlin DSL example:

~~~kotlin
dependencies {
    runtimeOnly("com.example:example-jdbc-driver:1.2.3")
}
~~~

The coordinates above are illustrative, not a real artifact. In a real project, use the exact coordinates from a verified vendor and version, avoiding uncontrolled dynamic versions.

You can inspect runtime dependency resolution:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

This is an **example command in the lesson**, not an instruction for workers to run during authoring. With multi-module builds, select the appropriate project/configuration. Inspecting the dependency graph helps confirm which driver is actually packaged, but does not by itself prove mappings are correct.

## 26. TLS, Authentication, and Security When Upgrading the Driver

A new driver may change defaults related to TLS, certificate validation, hostname verification, or authentication plugins. These changes must be analyzed separately from data mapping.

When connections fail:

- Check server/driver compatibility and protocol.
- Verify the TLS certificate chain, hostname/SAN, and truststore.
- Check the authentication mechanism and credential source.
- Review URL properties for the exact vendor/version.
- Verify proxies, firewalls, network timeouts, and server logs.

Do not disable TLS verification or enable trust-all just to make a connection succeed. A certificate error after upgrading the driver may indicate that the system previously skipped identity verification. The right fix is usually to repair the certificate, CA chain, truststore, or endpoint.

Likewise, do not put usernames/passwords into logs, source code, or migration reports. Use proper secret management and redact sensitive information when capturing stack traces.

## 27. Performance: Distinguishing Mapping from Fetch Behavior

A new driver may change how it:

- Prefetches/fetches rows.
- Uses server-side prepared statements.
- Buffers result sets or streams data.
- Sends batches.
- Configures query timeouts and network timeouts.
- Caches metadata and prepared statements.
- Handles connection failover.

A query that returns accurate data but consumes much more memory or runs much slower can still be an operational regression.

When measuring, keep the dataset, indexes, server load, and query plan as consistent as possible. Do not compare only a single run. Look at latency percentiles, throughput, allocation/memory, connection pool utilization, and round-trip counts.

Even so, performance differences do not justify changing precision/scale, dropping transactions, or lowering TLS security to regain old metrics.

## 28. Recording Reproducible Migration Evidence

A test record can follow a template:

~~~yaml
migration:
  component: "example-service JDBC integration"
  oldDriver: "vendor-driver:old-version"
  newDriver: "vendor-driver:new-version"
  jdk: "record actual vendor/build"
  database:
    product: "record actual DB"
    serverVersion: "record server version"
  schemaRevision: "record migration or schema version"
  testScope:
    - numeric-precision-scale
    - null-and-boolean
    - time-zone-and-timestamp
    - unicode-and-binary
    - vendor-json-uuid-array
    - transaction-rollback
    - tls-and-connection-pooling
  results:
    mapping: "NOT_YET_RUN"
    integration: "NOT_YET_RUN"
  limitations:
    - "list environments or drivers not yet tested"
~~~

This is an illustrative template, not actual results. When executing, add:

- Commit and artifact checksums.
- JDBC driver resolved version and classpath/module path.
- JDK distribution/build, DB vendor/version, and session settings.
- Database schema revision and fixture/dataset checksum.
- Test commands, logs, and test reports.
- Approved exceptions.
- Owner, go/no-go decision, and rollback plan.

Do not write a single line saying "JDBC compatible" after only running `SELECT 1`. That only shows a very small connection/query path worked.

## 29. A Controlled JDBC Driver Upgrade Process

### Step 1: Lock Down the Baseline

Record the working JDK, driver, database server, schema, timezone, pool/ORM versions, and dependency graph. Save mapping outputs for critical types.

### Step 2: Identify the New Driver and Support Scope

Check minimum Java requirements, database server versions, JDBC API level, support policy, and release notes covering data types, timezone, TLS, and authentication.

### Step 3: Inventory JDBC Usage

Find `getObject` calls with hardcoded casts, `Timestamp` mappings, custom converters, `setNull`, generated keys, batches, pool configurations, and driver-specific objects.

### Step 4: Upgrade One Axis When Possible

Keep the database and schema fixed to test the driver, or test the new driver on the target JDK if the old driver cannot run on that JDK. If multiple axes change, state clearly that conclusions are bounded by that combination.

### Step 5: Run Type Mapping Contract Tests

Cover numeric, null, date/time/timezone, Unicode, binary, JSON/UUID/ARRAY, and metadata as required by system contracts.

### Step 6: Run Transaction and Connection Tests

Verify commit, rollback, isolation, batch, retry, TLS, pool lifecycle, and connection drop scenarios.

### Step 7: Run Integration Tests with Real ORMs and Services

Verify repositories, DTOs, API responses, event payloads, and downstream systems. Data mappers affect not only the JDBC layer but also public contracts.

### Step 8: Trial Rollout

Deploy to a representative environment with controlled versions, metrics, and a rollback plan. Monitor SQL errors, deadlocks, pool exhaustion, data anomalies, and business metrics.

### Step 9: Document Intentional Differences

If the new driver fixes a previously buggy conversion, decide how to migrate and notify consumers. Do not label every behavior change as "non-breaking" when it can alter computed data or reports.

## 30. Common Mistakes

**"JDBC is a standard, so changing drivers is always safe."** Standardizing the API does not guarantee all vendor types, metadata, and conversions are identical.

**"`getObject()` always returns the same Java class."** Mapping depends on SQL type, driver, and database; request explicit types or use an adapter.

**"TIMESTAMP is always an Instant."** A timezone-less timestamp may just be a local date-time; a data convention is required.

**"Reading money with double is fine if the UI displays two decimal places."** Precision errors and rounding can affect totals; use DECIMAL/BigDecimal per contract.

**"0 and SQL NULL are equivalent for primitive getters."** `getInt`/`getBoolean` require `wasNull` for nullable columns.

**"New driver supports java.time means every type can be converted."** Support levels vary; test each SQL type and target Java type.

**"Adding a JDBC JAR is enough when a driver is not found."** Service discovery, classloaders, shading, and module paths can affect loading.

**"The ORM hides all driver differences."** ORMs add dialects/converters but still use the driver; mappings and metadata still need testing.

**"Running `SELECT 1` proves database compatibility."** It only verifies connectivity and a trivial query.

**"You can disable TLS validation to fix connection errors."** That weakens security controls, rather than providing a safe compatibility fix.

**"Testing on a developer machine is sufficient for production."** JVM, DB server, timezone, collation, container, pool, and network can differ.

**"Every SQL error after upgrading the JDK is caused by the JDK."** You must separate the effects of driver, server, ORM, schema, config, and data.

## 31. Checklist Upon Completing a JDBC Migration

- [ ] Recorded JDK, driver, database server, and actual environment versions.
- [ ] Confirmed class-file baseline and driver/JDK/server support matrix.
- [ ] Checked driver loading, dependency graph, and classpath/module path.
- [ ] Checked DataSource and connection pool lifecycle.
- [ ] Tested `NULL`, zero, false, and empty separately.
- [ ] Checked numeric precision, scale, rounding, and overflow.
- [ ] Defined contracts for DATE/TIME/TIMESTAMP and timezone/offset.
- [ ] Tested times at midnight, DST boundaries, and fractional seconds.
- [ ] Tested Unicode, emoji, collation, trailing spaces, and binary data.
- [ ] Tested UUID, JSON, ARRAY, SQLXML, and vendor-specific types if used.
- [ ] Verified metadata, aliases, and dynamic mapping.
- [ ] Checked transactions, generated keys, batches, rollback, and SQLState.
- [ ] Ran integration tests with ORM/dialect/framework.
- [ ] Checked TLS, certificate validation, authentication, and connection timeouts.
- [ ] Ran round-trip tests and tested reading historical data.
- [ ] Saved test reports, artifact checksums, schema revisions, and limitations.
- [ ] Established go/no-go decision, owner, and rollback plan.

## Conclusion

**Changing a JDBC driver is a change in communication and data semantics, not just swapping a JAR.** The standard JDBC API helps applications write less vendor-dependent code, but it does not eliminate differences in SQL types, precision, null, timezones, metadata, vendor-specific types, transactions, or connection behavior.

In Java Advance Compatibility Migration, you need to test the JDK, driver, database, and ORM separately, design mappers around data contracts rather than casting based on the current implementation, and use round-trip and boundary-data tests to catch discrepancies. Only when environment details, datasets, dependencies, verification results, and remaining risks are fully recorded does the team have a sound basis to state that the JDBC driver change fits real consumers without compromising data accuracy.
