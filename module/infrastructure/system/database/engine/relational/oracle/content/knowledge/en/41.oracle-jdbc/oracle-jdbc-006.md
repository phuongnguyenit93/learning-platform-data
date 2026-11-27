# Binding Data Types, setNull, and Distinguishing JDBC Types from Oracle Types

In Oracle JDBC, a bind variable is not just a value sent to the database. The driver must also pass the data type, length, precision, scale, and related metadata so Oracle parses and executes the SQL properly. If an application binds a NUMBER column as a string, binds a DATE with an unsuitable temporal type, or sends NULL without specifying a type, Oracle may have to infer or convert types, raise errors, or produce unstable execution plans.

There are multiple distinct type layers: Java types in the program, standard JDBC types in java.sql.Types/JDBCType, Oracle SQL types such as NUMBER, VARCHAR2, DATE, TIMESTAMP, RAW, CLOB, and vendor-specific types in Oracle JDBC such as OracleTypes. They have mapping relationships, but they are not a single unified type system. Types.NUMERIC is a JDBC type code, whereas NUMBER(p,s) is an Oracle SQL type; Types.TIMESTAMP does not capture the full distinction among TIMESTAMP, TIMESTAMP WITH TIME ZONE, and TIMESTAMP WITH LOCAL TIME ZONE.

This lesson focuses on choosing the right setters, passing typed NULLs with setNull, using setObject with a target type, handling dates/times, numbers, text, national characters, LOBs, and Oracle-specific types. It also explains the impact of bind data types on implicit conversion, index access, cursor sharing, and compatibility across Java versions and Oracle JDBC drivers.

After this lesson, you will be able to:

- Distinguish Java types, JDBC types, and Oracle SQL types.
- Choose the setter corresponding to a column's data type.
- Use PreparedStatement.setNull with the right JDBC type.
- Understand why calling setObject(index, null) or using setString for all parameters easily causes issues.
- Handle NUMBER precision/scale with BigDecimal.
- Distinguish DATE, TIMESTAMP, TIMESTAMP WITH TIME ZONE, and TIMESTAMP WITH LOCAL TIME ZONE.
- Choose between setString and setNString, and between setBytes and stream/LOB setters.
- Bind Oracle collections, object types, and REF CURSORs when supported by the driver.
- Register OUT parameters with the right type using CallableStatement.
- Diagnose implicit conversion, ORA-01722, ORA-01861, and cursor child mismatches.
- Test bind metadata, SQL plans, and behavior on the exact Oracle JDBC driver.

> APIs and mappings can vary by JDK, JDBC specification, and Oracle JDBC driver (ojdbc8/ojdbc11/ojdbc17...). Examples use common JDBC; check the Oracle JDBC Developer's Guide and driver documentation matching your application/database versions.

## 1. Three data type layers to distinguish

### 1.1. Java types

These are data types in a Java program, for example:

- String
- Integer, Long, Short
- BigDecimal
- Float, Double
- Boolean
- LocalDate, LocalDateTime, OffsetDateTime
- java.sql.Date, java.sql.Timestamp
- byte[], InputStream
- Reader, Clob, Blob

A Java type represents data inside the JVM. It does not by itself determine which SQL data type Oracle will assign to a bind variable in every case.

### 1.2. JDBC types

JDBC defines standard data types for the driver to communicate with the database. Traditional codes live in java.sql.Types, for example:

- Types.VARCHAR
- Types.CHAR
- Types.INTEGER
- Types.BIGINT
- Types.NUMERIC
- Types.DECIMAL
- Types.DATE
- Types.TIMESTAMP
- Types.BINARY
- Types.VARBINARY
- Types.BLOB
- Types.CLOB
- Types.NCLOB
- Types.ARRAY
- Types.STRUCT
- Types.REF_CURSOR (JDBC 4.2)

Since JDBC 4.2, the java.sql.JDBCType enum exists, e.g., JDBCType.VARCHAR, JDBCType.NUMERIC, JDBCType.TIMESTAMP. This enum implements SQLType and makes code more readable.

### 1.3. Oracle SQL types

These are the actual data types of columns/expressions in Oracle Database, for example:

- NUMBER(p,s), BINARY_FLOAT, BINARY_DOUBLE.
- CHAR, VARCHAR2, NCHAR, NVARCHAR2.
- DATE, TIMESTAMP, TIMESTAMP WITH TIME ZONE, TIMESTAMP WITH LOCAL TIME ZONE.
- RAW, LONG RAW.
- CLOB, NCLOB, BLOB, BFILE.
- ROWID, UROWID.
- INTERVAL YEAR TO MONTH, INTERVAL DAY TO SECOND.
- XMLTYPE, JSON, and release-specific data types/features.
- Object types, collection types (nested table/VARRAY), REF CURSOR in API/PLSQL contexts.

Oracle SQL types have their own semantics. For instance, Oracle DATE stores both date and time down to the second; JDBC Types.DATE generally carries date-only semantics without time-of-day. Oracle NUMBER has precision/scale different from Java double.

### 1.4. Oracle JDBC type extensions

Oracle JDBC provides extended APIs and constants, typically via the oracle.jdbc package, such as OracleTypes and OracleConnection. They are needed when standard JDBC does not fully represent an Oracle-specific type or feature.

Vendor-specific examples can include CURSOR, BINARY_FLOAT, BINARY_DOUBLE, TIMESTAMP WITH TIME ZONE, TIMESTAMP WITH LOCAL TIME ZONE, INTERVAL, STRUCT, ARRAY, and other Oracle types. Exact constant/API names depend on the driver version.

### 1.5. Relationships between layers

```text
JAVA VALUE
   String / BigDecimal / LocalDateTime / byte[]
             |
             v
JDBC BIND API
   setString / setBigDecimal / setTimestamp / setBytes
   setNull(index, jdbcType)
   setObject(index, value, targetSqlType)
             |
             v
ORACLE JDBC DRIVER
   Mapping + conversion + bind metadata
             |
             v
ORACLE SQL TYPE
   VARCHAR2 / NUMBER / DATE / TIMESTAMP / RAW / CLOB ...
             |
             v
SQL EXECUTION
   Comparison / INSERT / UPDATE / procedure call
```

### 1.6. Key rule

The setter determines how the driver represents the bind value. The column's data type is defined in the schema. Both sides should align to avoid implicit conversion and keep SQL semantics stable.

A JDBC type does not always map one-to-one to a single Oracle type. The driver may use internal representations or Oracle extensions; focus on the final SQL semantics and driver documentation.

## 2. java.sql.Types and JDBCType

### 2.1. java.sql.Types

Types is a class containing int constants used by JDBC in setNull, registerOutParameter, metadata, and similar APIs.

Example:

```java
import java.sql.Types;

int textType = Types.VARCHAR;
int numberType = Types.NUMERIC;
int timestampType = Types.TIMESTAMP;
```

These are JDBC type codes, not Oracle data type names.

### 2.2. java.sql.JDBCType

JDBC 4.2 added the JDBCType enum, which implements SQLType:

```java
import java.sql.JDBCType;

JDBCType textType = JDBCType.VARCHAR;
JDBCType numberType = JDBCType.NUMERIC;
JDBCType timestampType = JDBCType.TIMESTAMP;
```

JDBCType can be used with setObject/registerOutParameter overloads accepting SQLType if the driver supports that JDBC version.

### 2.3. When to use Types and when to use JDBCType?

- Use Types.* when the API takes an int, such as PreparedStatement.setNull(index, sqlType).
- Use JDBCType.* when the API takes SQLType and the driver/JDK supports it.
- Use OracleTypes.* when an Oracle-specific type is needed that standard JDBC cannot adequately describe.

Do not pass an OracleTypes code to an API expecting an Oracle SQL data type name string, or vice versa.

### 2.4. Types.NUMERIC and Types.DECIMAL

These two types are closely related in JDBC and are commonly used for Oracle NUMBER. NUMERIC/DECIMAL are generic JDBC categories; Oracle NUMBER(p,s) still has its own precision/scale. For exact decimal values, Java BigDecimal is usually the appropriate choice.

### 2.5. Types.DATE and Types.TIMESTAMP

JDBC DATE carries date-only semantics, while TIMESTAMP includes fractional seconds. Oracle DATE also stores time down to the second, so do not infer mapping solely from similar names. Choose APIs based on business semantics and check your driver's mapping.

## 3. PreparedStatement setters

### 3.1. Using PreparedStatement

PreparedStatement separates SQL text from bind values:

```java
String sql = """
    INSERT INTO customers (customer_id, full_name, credit_limit)
    VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setString(2, fullName);
    ps.setBigDecimal(3, creditLimit);
    ps.executeUpdate();
}
```

The driver sends bind values with metadata, avoiding direct value concatenation into SQL text and enabling statement reuse.

### 3.2. Choosing a setter by Java value and column

| Java value | Common setter | Common JDBC category | Common Oracle column |
| --- | --- | --- | --- |
| String | setString | VARCHAR | VARCHAR2 |
| String for fixed-width | setString | CHAR/VARCHAR | CHAR |
| Integer | setInt | INTEGER | NUMBER(p,0) |
| Long | setLong | BIGINT | NUMBER(p,0) |
| BigDecimal | setBigDecimal | DECIMAL/NUMERIC | NUMBER(p,s) |
| Float | setFloat | REAL/FLOAT | BINARY_FLOAT or NUMBER depending on schema/driver |
| Double | setDouble | DOUBLE | BINARY_DOUBLE or NUMBER depending on schema/driver |
| Boolean | setBoolean | BOOLEAN | SQL BOOLEAN if release supports; different mapping in older releases |
| java.sql.Date | setDate | DATE | DATE |
| java.sql.Timestamp | setTimestamp | TIMESTAMP | TIMESTAMP or Oracle DATE per contract |
| byte[] | setBytes | VARBINARY/BINARY | RAW |
| InputStream | setBinaryStream | BLOB/binary stream | BLOB |
| Reader | setCharacterStream | CLOB/text stream | CLOB |
| National String | setNString | NVARCHAR | NVARCHAR2/NCHAR |

This table is a starting guide, not an absolute mapping for every driver/release.

### 3.3. Do not bind everything with setString

If a column is NUMBER and the application calls setString, Oracle/the driver may have to convert the character value to a number. This depends on the SQL expression and bind metadata; conversion can trigger ORA-01722, depend on NLS settings, or make predicates less index-friendly.

Similarly, binding dates/times as strings makes parsing dependent on format/NLS unless SQL uses TO_DATE/TO_TIMESTAMP with an explicit mask. Pass typed values instead.

### 3.4. Do not bind all numbers with setDouble

Double uses binary floating-point and cannot represent every decimal accurately. Currency, rates, and numbers requiring exact decimals should use BigDecimal and setBigDecimal.

### 3.5. Setters must match placeholder order

Parameter indexes start at 1, not 0:

```java
String sql = "UPDATE orders SET status = ?, amount = ? WHERE order_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, status);
    ps.setBigDecimal(2, amount);
    ps.setLong(3, orderId);
    ps.executeUpdate();
}
```

Misaligning indexes can cause data type errors or write wrong data. Use named index constants or sequential bind helpers to reduce errors in long SQL statements.

### 3.6. Binding the same parameter multiple times?

Each `?` is a separate parameter. If the same value appears twice in SQL, both positions must be bound:

```java
String sql = """
    SELECT *
    FROM orders
    WHERE created_at >= ?
      AND updated_at < ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setTimestamp(1, fromTime);
    ps.setTimestamp(2, toTime);
}
```

## 4. setNull and typed NULL

### 4.1. NULL does not carry a data type on its own

In SQL, NULL represents an unknown/absent value. When binding a NULL, the driver needs to know the SQL type of the parameter to send proper metadata, and Oracle needs to resolve the expression's data type.

A NULL of type VARCHAR2 differs from a NULL of type NUMBER or DATE in a SQL context. Thus, setNull requires both parameter index and JDBC type.

### 4.2. setNull syntax

```java
ps.setNull(parameterIndex, sqlType);
```

Example:

```java
ps.setNull(1, Types.VARCHAR);
ps.setNull(2, Types.NUMERIC);
ps.setNull(3, Types.DATE);
ps.setNull(4, Types.TIMESTAMP);
```

Parameter index starts at 1. sqlType is a JDBC type code from java.sql.Types, or a compatible type code supported by the driver.

### 4.3. INSERT example with nullable columns

Suppose the schema is:

```sql
CREATE TABLE jdbc_bind_lab (
    id NUMBER PRIMARY KEY,
    note VARCHAR2(100),
    amount NUMBER(12,2),
    event_time TIMESTAMP
);
```

Java:

```java
String sql = """
    INSERT INTO jdbc_bind_lab (id, note, amount, event_time)
    VALUES (?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 10L);
    ps.setNull(2, Types.VARCHAR);
    ps.setNull(3, Types.NUMERIC);
    ps.setNull(4, Types.TIMESTAMP);
    ps.executeUpdate();
}
```

### 4.4. Why not just call setObject(index, null)?

setObject(index, null) does not state the intended type in code. How the driver handles it can depend on driver/JDBC version and SQL context; some expressions or procedure overloads cannot uniquely infer the data type. Using setNull(index, jdbcType) makes intent explicit and avoids relying on inference.

If using overloads setObject(index, null, targetSqlType) or setObject(index, null, JDBCType.VARCHAR), still confirm the driver supports that overload and the target type is accurate.

### 4.5. NULL inside expressions can be ambiguous

Example SQL:

```sql
SELECT COALESCE(?, ?) FROM dual;
```

If both binds are NULL and there is no clear context type, Oracle may be unable to determine the desired result type. You can CAST the bind/NULL:

```sql
SELECT COALESCE(
         CAST(? AS VARCHAR2(30)),
         CAST(? AS VARCHAR2(30))
       )
FROM dual;
```

Typed NULL helps the driver and SQL engine resolve expressions more accurately.

### 4.6. NULL for NUMBER

```java
ps.setNull(1, Types.NUMERIC);
```

If SQL/procedures require specific precision/scale, the column or expression defines NUMBER(p,s). JDBC Types.NUMERIC does not transmit column precision/scale; it only classifies the parameter type. Use BigDecimal for non-NULL values and the schema/procedure contract to determine precision/scale.

### 4.7. NULL for character and national character types

```java
ps.setNull(1, Types.VARCHAR);  // VARCHAR2/character
ps.setNull(2, Types.NVARCHAR); // national character
ps.setNull(3, Types.CLOB);     // CLOB
ps.setNull(4, Types.NCLOB);    // NCLOB
```

Ensure the JDBC type matches the actual column/parameter. If the driver requires an Oracle-specific type for NCLOB or a vendor type, use the API supported by the driver documentation.

### 4.8. NULL for LOB and binary types

```java
ps.setNull(1, Types.BLOB);
ps.setNull(2, Types.CLOB);
ps.setNull(3, Types.VARBINARY);
```

Do not use Types.VARCHAR for a BLOB parameter simply because the current Java value is null. The type must reflect the SQL contract, not whether a value is present.

### 4.9. NULL in an IN list

```sql
WHERE customer_id IN (?, ?, ?)
```

Binding NULL in an IN list is not equivalent to omitting the parameter from the list. SQL three-valued logic makes comparisons with NULL evaluate to UNKNOWN. If the application needs to skip a filter when a value is null, design an explicit predicate or construct the appropriate SQL structure; do not expect setNull to skip the condition automatically.

## 5. setObject and target SQL types

### 5.1. setObject without target type

```java
ps.setObject(1, value);
```

The driver infers the JDBC type from the runtime Java class. This is convenient for standard Java types, but can produce unintended mappings with custom classes, nulls, temporal types, or Oracle-specific types.

### 5.2. setObject with JDBC type

```java
ps.setObject(1, value, Types.NUMERIC);
ps.setObject(2, value, Types.VARCHAR);
```

This overload explicitly specifies the target JDBC type. JDBCType/SQLType can be used in the corresponding overload if the driver supports JDBC 4.2.

### 5.3. Scale for DECIMAL/NUMERIC

Some setObject overloads accept a target SQL type and scale/length. Scale matters for numeric conversion; define rounding/truncation policies before binding.

```java
ps.setObject(1, new BigDecimal("123.456"),
            Types.DECIMAL, 2);
```

Do not assume every driver handles rounding identically when adjusting scale. If business logic requires specific rounding, normalize the BigDecimal with setScale and an explicit RoundingMode before binding.

### 5.4. setObject with java.time

JDBC 4.2 supports several java.time classes via setObject, though exact support depends on the driver:

```java
ps.setObject(1, LocalDate.of(2026, 11, 14));
ps.setObject(2, LocalDateTime.of(2026, 11, 14, 10, 30));
ps.setObject(3, OffsetDateTime.parse("2026-11-14T10:30:00+07:00"));
```

Test round-trip behavior and timezone semantics on the deployed driver. For code needing compatibility with older drivers, use java.sql.Date/Timestamp or documented Oracle JDBC extensions.

### 5.5. Do not force a target type to mask schema mismatch

setObject(index, value, Types.VARCHAR) does not turn a NUMBER column into VARCHAR2. If the schema is NUMBER, bind NUMBER per contract; bind character types only when the SQL/procedure actually defines a character parameter.

## 6. Numeric mapping: NUMBER and Java numerics

### 6.1. Oracle NUMBER

NUMBER supports wide precision/scale, including exact decimal numbers. Use BigDecimal to preserve decimal values in Java:

```java
BigDecimal amount = new BigDecimal("12345.67");
ps.setBigDecimal(1, amount);
```

Do not construct BigDecimal from double when decimal exactness is required:

```java
new BigDecimal(0.1);       // carries binary error from double
new BigDecimal("0.1");     // exact decimal from string
```

### 6.2. NUMBER(p,0)

For NUMBER(p,0), a Java integral type fits if the value range stays within bounds:

| Oracle | Suggested Java |
| --- | --- |
| NUMBER(3,0) | short/int |
| NUMBER(9,0) | int |
| NUMBER(18,0) | long if range fits |
| NUMBER(38,0) | BigDecimal |

These numbers are guidelines and do not replace checking actual min/max values and signed Java type ranges.

### 6.3. NUMBER(p,s)

For decimals, use BigDecimal and check:

- precision: total significant digits.
- scale: digits after the decimal point.
- rounding mode.
- overflow and scale mismatch.

Example:

```java
BigDecimal value = new BigDecimal("123.4567");
BigDecimal normalized =
    value.setScale(2, RoundingMode.HALF_UP);
ps.setBigDecimal(1, normalized);
```

Choose RoundingMode according to business rules; do not automatically round all data.

### 6.4. BINARY_FLOAT and BINARY_DOUBLE

Oracle BINARY_FLOAT/BINARY_DOUBLE are binary floating-point types. setFloat/setDouble can be used when columns/parameters are designed for floating point. They differ from NUMBER in precision, rounding, and representation.

### 6.5. Do not confuse BIGINT with NUMBER(38)

JDBC BIGINT corresponds to the Java long range; Oracle NUMBER can hold a wider range. If a NUMBER column can exceed Long.MAX_VALUE or Long.MIN_VALUE, use BigDecimal instead of getLong/setLong.

### 6.6. Numeric NULL

Use setNull(index, Types.NUMERIC) or the corresponding API type. Do not use setInt(index, 0) to represent NULL; zero is a valid value distinct from NULL.

## 7. Mapping DATE and TIMESTAMP

### 7.1. Oracle DATE is not identical to JDBC DATE

Oracle DATE stores year, month, day, hour, minute, and second. JDBC DATE was designed for SQL DATE with date-only semantics, does not represent fractional seconds, and does not always preserve time-of-day as applications expect.

If an Oracle DATE column holds both date and time, check the driver mapping and consider java.sql.Timestamp/setTimestamp or java.time LocalDateTime with a supporting driver. Do not use getDate if time components must be preserved.

### 7.2. java.sql.Date

java.sql.Date represents date-only. Use it when business logic truly only needs a date:

```java
LocalDate localDate = LocalDate.of(2026, 11, 14);
java.sql.Date sqlDate = java.sql.Date.valueOf(localDate);
ps.setDate(1, sqlDate);
```

Do not use it for timestamps whose hours/minutes/seconds must be preserved.

### 7.3. java.sql.Timestamp

Timestamp represents date-time with fractional seconds:

```java
LocalDateTime localDateTime =
    LocalDateTime.of(2026, 11, 14, 21, 18, 30, 123_000_000);
Timestamp timestamp = Timestamp.valueOf(localDateTime);
ps.setTimestamp(1, timestamp);
```

Oracle TIMESTAMP supports fractional seconds according to column precision. Check scale/precision and rounding when Java has nanoseconds while the column stores fewer digits.

### 7.4. Calendar overloads

JDBC provides setDate(index, date, Calendar) and setTimestamp(index, timestamp, Calendar). Calendar specifies the timezone used when converting values in certain driver/API paths.

```java
Calendar utc = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
ps.setTimestamp(1, timestamp, utc);
```

Do not pass Calendar arbitrarily; align the timezone contract across the application, JDBC connection/session, and Oracle data type.

### 7.5. TIMESTAMP WITH TIME ZONE

Oracle TIMESTAMP WITH TIME ZONE retains timezone/offset information with the timestamp per Oracle semantics. With java.time, OffsetDateTime is the natural type for an instant with an offset:

```java
OffsetDateTime value =
    OffsetDateTime.parse("2026-11-14T21:18:30+07:00");
ps.setObject(1, value);
```

Direct mapping support depends on the JDBC driver. If Oracle-specific APIs are needed, consult the Oracle JDBC guide for Oracle TIMESTAMPTZ/OracleTypes.TIMESTAMPTZ.

### 7.6. OffsetDateTime and ZonedDateTime

OffsetDateTime retains local date-time and UTC offset. ZonedDateTime also retains a ZoneId such as Asia/Ho_Chi_Minh. Not every Oracle JDBC driver binds ZonedDateTime directly in a way that preserves ZoneId. If business logic must persist the timezone region name, store ZoneId separately or use a documented Oracle mapping.

### 7.7. TIMESTAMP WITH LOCAL TIME ZONE

TIMESTAMP WITH LOCAL TIME ZONE normalizes instants to the database timezone when stored and displays them in the session timezone when queried. Returned values do not preserve the original zone identifier/offset as TSTZ does.

This makes session timezone an integral part of the semantics. The same stored value can display differently across two sessions with different TIME_ZONE settings.

### 7.8. Session timezone

Check:

```sql
SELECT
    SESSIONTIMEZONE,
    DBTIMEZONE,
    CURRENT_TIMESTAMP,
    SYSTIMESTAMP,
    CURRENT_DATE,
    SYSDATE
FROM dual;
```

DBTIMEZONE and SESSIONTIMEZONE serve different purposes. Never assume server timezone, JVM default timezone, and Oracle session timezone are the same.

### 7.9. java.time API

Starting mapping guide:

| Java time type | Typical JDBC/Oracle semantics |
| --- | --- |
| LocalDate | SQL DATE/date-only |
| LocalTime | TIME semantics; standalone Oracle SQL TIME is uncommon |
| LocalDateTime | TIMESTAMP without timezone |
| OffsetDateTime | TIMESTAMP WITH TIME ZONE if supported by driver |
| Instant | A UTC instant; typically converted to Timestamp/OffsetDateTime per contract |
| ZonedDateTime | Requires driver verification; ZoneId may need separate storage |

Do not blindly convert Instant to LocalDateTime by stripping UTC/offset if identifying a unique point in time is required.

### 7.10. Avoid binding dates/times as String

Avoid:

```java
ps.setString(1, "14/11/2026 21:18:30");
```

If SQL compares against DATE/TIMESTAMP, Oracle may implicitly convert using NLS formats and cause errors or differing results across environments. Use typed setters or explicit conversions with an explicit format mask when the input contract mandates text.

## 8. Mapping characters: CHAR, VARCHAR2, NCHAR, NVARCHAR2

### 8.1. setString

setString is the common choice for VARCHAR2/CHAR:

```java
ps.setString(1, "Nguyen Van A");
```

The driver binds using the corresponding character type. The Oracle column still governs length semantics, collation, and constraints.

### 8.2. CHAR and blank padding

CHAR is a fixed-length character type with blank-padding semantics. During comparisons or retrieval, trailing spaces can behave differently from VARCHAR2. Java String does not capture this distinction automatically; the application must understand column definitions.

### 8.3. VARCHAR2

VARCHAR2 stores variable-length strings. Use setString for regular text values. Check max length against BYTE/CHAR semantics and the database character set.

### 8.4. NCHAR and NVARCHAR2

National character types use the national character set. For binding, JDBC provides setNString/setNCharacterStream for NCHAR/NVARCHAR2/NCLOB:

```java
ps.setNString(1, "Vietnamese – Unicode data");
```

setString can work in many cases via driver/database conversion, but setNString makes national character intent explicit. Verify driver and character sets for multilingual data.

### 8.5. setNCharacterStream

For streamed Unicode text:

```java
try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    ps.setNCharacterStream(1, reader);
    ps.executeUpdate();
}
```

Ensure the stream stays open during execution; close the stream once the driver has finished consuming it per contract.

### 8.6. BYTE and CHAR length semantics

VARCHAR2(100 BYTE) limits by bytes; VARCHAR2(100 CHAR) limits by characters. With UTF-8/multibyte characters, 100 characters can exceed 100 bytes. Applications should not rely solely on String.length() to predict Oracle byte length.

### 8.7. Empty strings and NULL

In Oracle SQL, zero-length strings for character data types are treated as NULL in many contexts. An empty Java String and Java null are distinct values in code, but when bound to Oracle VARCHAR2, an empty string can become NULL. If business logic must distinguish "not entered" from "empty string", store an explicit status/flag or define clear conventions.

### 8.8. Collation and case sensitivity

The character bind type does not determine collation. Comparison outcomes depend on data type/collation, NLS_COMP/NLS_SORT, and configured collation. Do not assume setString automatically performs case-insensitive comparisons.

## 9. RAW, BLOB, and binary values

### 9.1. RAW

RAW stores byte sequences with release-specific length limits. Use setBytes for small payloads:

```java
byte[] digest = MessageDigest.getInstance("SHA-256")
    .digest(payload);
ps.setBytes(1, digest);
```

Do not encode byte[] into a hex string and bind VARCHAR2 if the column is RAW, unless the SQL contract specifically requires text encoding.

### 9.2. BLOB

BLOB suits large binary values. Use setBinaryStream or setBlob:

```java
try (InputStream in = Files.newInputStream(filePath)) {
    ps.setBinaryStream(1, in, Files.size(filePath));
    ps.executeUpdate();
}
```

Overloads with length take long/int depending on the JDBC API/driver. Ensure the length is accurate and the stream stays open until execution completes.

### 9.3. Blob objects

When using java.sql.Blob, bind via setBlob. Blobs are typically tied to a connection/transaction; do not retain locators beyond the connection's lifecycle.

### 9.4. RAW vs. BLOB

RAW is a scalar binary value with a length limit; BLOB is a large object locator/content. Choose the data type based on size, access pattern, and streaming requirements. Do not use RAW for large files.

### 9.5. Binary NULL

```java
ps.setNull(1, Types.VARBINARY); // RAW-like binary mapping
ps.setNull(2, Types.BLOB);
```

For Oracle RAW specifically, check the driver's JDBC VARBINARY/BINARY mapping and use Oracle extensions if needed.

## 10. CLOB, NCLOB, and character streams

### 10.1. CLOB

CLOB stores character large objects. Strings may be bound for small values if limits/driver allow, or use setCharacterStream/Clob for large data.

```java
try (Reader reader = Files.newBufferedReader(textPath, StandardCharsets.UTF_8)) {
    ps.setCharacterStream(1, reader);
    ps.executeUpdate();
}
```

### 10.2. NCLOB

NCLOB stores national character large objects. Use setNCharacterStream/setNClob per driver support:

```java
try (Reader reader = Files.newBufferedReader(textPath, StandardCharsets.UTF_8)) {
    ps.setNCharacterStream(1, reader);
    ps.executeUpdate();
}
```

### 10.3. Length and stream lifecycle

Some overloads require specifying length; newer JDBC adds overloads taking a long length. Do not supply an inaccurate length or close the stream before execution. For streams of unknown length, use a lengthless overload if supported by the driver and verify performance.

### 10.4. LOB locators and transactions

LOB locators are generally bound to a connection/transaction. Reading/writing a LOB after closing the connection or ending the transaction can fail. Keep lifecycles explicit and do not return raw locators out of the repository layer without managing resources.

### 10.5. LOB NULL

Use setNull with the corresponding Types.CLOB/NCLOB/BLOB. Do not pass an empty Reader/empty InputStream in place of NULL unless business logic intends an empty LOB (and understands Oracle semantics).

## 11. Oracle-specific types and OracleTypes

### 11.1. When are Oracle extensions needed?

Standard JDBC covers most common scalar types. Some Oracle types/features lack sufficiently detailed standard mappings, or older driver versions require vendor-specific APIs. In those cases, OracleTypes, OracleConnection, or classes in oracle.jdbc may be needed.

Prefer standard JDBC types whenever they capture the semantics accurately and the driver supports them. Use Oracle extensions only when Oracle-specific features are needed or standard mappings fall short.

### 11.2. OracleTypes

Oracle JDBC has the OracleTypes constants class representing Oracle data types/features. Depending on driver version, constants may include CURSOR, TIMESTAMP, TIMESTAMPTZ, TIMESTAMPLTZ, INTERVALYM, INTERVALDS, BINARY_FLOAT, BINARY_DOUBLE, STRUCT, ARRAY, and others.

Legacy API style example:

```java
import oracle.jdbc.OracleTypes;

callable.registerOutParameter(1, OracleTypes.CURSOR);
```

With drivers supporting JDBC 4.2, Types.REF_CURSOR can be used for REF CURSOR. Check your Oracle JDBC version before selecting an API; do not copy constants from one ojdbc version to another driver without building/testing.

### 11.3. REF CURSOR

REF CURSOR is a cursor handle returned by PL/SQL to the client. Standard JDBC has Types.REF_CURSOR since JDBC 4.2; older Oracle drivers may use OracleTypes.CURSOR.

Example:

```java
String call = "{ call customer_api.list_customers(?) }";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.registerOutParameter(1, Types.REF_CURSOR);
    cs.execute();

    try (ResultSet rs = (ResultSet) cs.getObject(1)) {
        while (rs.next()) {
            long id = rs.getLong("customer_id");
            String name = rs.getString("full_name");
        }
    }
}
```

Check whether the driver supports Types.REF_CURSOR and check the actual procedure signature. Cursor ResultSets must be closed; they can hold server cursors and database resources.

### 11.4. STRUCT and Oracle object types

Oracle object types can be represented via java.sql.Struct or Java class mappings depending on driver/API. Example:

```sql
CREATE TYPE address_t AS OBJECT (
    street VARCHAR2(100),
    city   VARCHAR2(60)
);

CREATE TABLE customer_address (
    customer_id NUMBER,
    address     address_t
);
```

JDBC:

```java
Object[] attributes = {"12 Nguyen Hue", "Ho Chi Minh City"};
Struct address = connection.createStruct(
    "APP.ADDRESS_T", attributes);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO customer_address(customer_id, address) VALUES (?, ?)")) {
    ps.setLong(1, 100L);
    ps.setObject(2, address);
    ps.executeUpdate();
}
```

Type names generally must include the exact schema. How Struct is created and UDT support depend on the Oracle JDBC driver; Oracle-specific type mapping may require OracleConnection/OracleData APIs.

### 11.5. NULL for STRUCT/ARRAY with type name

JDBC provides a setNull overload accepting typeName:

```java
ps.setNull(1, Types.STRUCT, "APP.ADDRESS_T");
```

The type name helps the driver identify the named SQL type. For collections, use Types.ARRAY and the matching collection type name if supported by the driver. Verify schema qualification and EXECUTE privileges on the type.

### 11.6. Collections and ARRAY

Oracle nested tables/VARRAYs are named collection types. Do not assume Connection.createArrayOf behaves identically across all databases; Oracle JDBC typically provides OracleConnection.createOracleArray with the SQL collection type name:

```java
OracleConnection oracleConnection =
    connection.unwrap(OracleConnection.class);

Array values = oracleConnection.createOracleArray(
    "APP.NUMBER_LIST_T",
    new BigDecimal[] {
        new BigDecimal("10"),
        new BigDecimal("20")
    });

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO batch_ids(ids) VALUES (?)")) {
    ps.setArray(1, values);
    ps.executeUpdate();
} finally {
    values.free();
}
```

This is an illustrative example. The collection type must already exist in Oracle and the name must match exactly. Exact Oracle JDBC APIs depend on the driver; avoid legacy oracle.sql.ARRAY classes if newer drivers provide replacement APIs.

### 11.7. INTERVAL

Oracle INTERVAL YEAR TO MONTH and INTERVAL DAY TO SECOND do not map cleanly one-to-one to every Java Duration/Period. Period represents years/months; Duration represents durations in seconds/nanoseconds. Choose mappings by semantics and use Oracle-specific APIs if exact interval types must be preserved.

### 11.8. ROWID and UROWID

JDBC has java.sql.RowId. Oracle ROWID/UROWID carries row-location semantics; do not use it as a stable business key or cross-database identifier. If binding, use RowId/setRowId when supported by the driver and never serialize ROWID as a business key.

### 11.9. BFILE

BFILE is a locator to a file external to the database and is typically read-only via Oracle-specific APIs. It is not like BLOB; file content is not stored inside datafiles as internal LOBs are. Working with BFILE requires directory object privileges and proper locator lifecycle management.

### 11.10. XMLTYPE and JSON

XMLTYPE/JSON support depends on the Oracle Database release and JDBC driver. Some releases provide Oracle-specific XML/JSON APIs; newer releases add JDBC mappings for JSON. Do not assume calling setString on every JSON parameter preserves binary/native JSON semantics. Verify column type, driver API, and round-trip behavior.

## 12. BOOLEAN: SQL BOOLEAN and PL/SQL BOOLEAN

### 12.1. PL/SQL BOOLEAN

PL/SQL BOOLEAN has existed in PL/SQL for a long time, but Oracle Database releases before 23ai lacked a SQL BOOLEAN column type for direct use in tables/queries as a regular SQL data type.

Some Oracle JDBC drivers provide extensions to bind PL/SQL BOOLEAN in procedure/function calls. Exact constants/APIs depend on the driver, such as OracleTypes.PLSQL_BOOLEAN in supporting versions.

### 12.2. SQL BOOLEAN in newer releases

Oracle Database 23ai adds SQL BOOLEAN. With a supporting database/driver, JDBC boolean mapping can use setBoolean/getBoolean or JDBCType.BOOLEAN depending on driver version.

Do not use JDBC BOOLEAN with older databases assuming it will automatically and safely map to NUMBER(1) or CHAR(1).

### 12.3. Legacy mappings

For databases without SQL BOOLEAN, schemas commonly use:

- NUMBER(1) with 0/1.
- CHAR(1)/VARCHAR2 with Y/N or T/F.

Pick a consistent contract. Add CHECK constraints to reject out-of-set values and handle null mappings separately.

### 12.4. Boolean NULL

A nullable boolean has three business states: TRUE, FALSE, and UNKNOWN/NULL. Do not automatically map NULL to false if business logic needs to distinguish them. Use setNull with the JDBC type supported by the driver/database or represent it via the legacy schema contract.

## 13. CallableStatement and procedure parameters

### 13.1. IN parameters

IN parameters use setters just like PreparedStatement:

```java
String call = "{ call order_api.update_status(?, ?) }";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setLong(1, orderId);
    cs.setString(2, "SHIPPED");
    cs.execute();
}
```

### 13.2. OUT parameters

OUT parameters must register their JDBC type before execute:

```java
String call = "{ call order_api.get_total(?, ?) }";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setLong(1, customerId);
    cs.registerOutParameter(2, Types.NUMERIC);
    cs.execute();

    BigDecimal total = cs.getBigDecimal(2);
}
```

JDBC indexes start at 1. The registered type in registerOutParameter must be compatible with the procedure parameter.

### 13.3. IN OUT parameters

An IN OUT parameter both binds input and registers output:

```java
cs.setBigDecimal(1, startingBalance);
cs.registerOutParameter(1, Types.NUMERIC);
cs.execute();
BigDecimal resultingBalance = cs.getBigDecimal(1);
```

Some drivers require registering before setting or vice versa per API; follow the JDBC/Oracle driver documentation and test.

### 13.4. NULL IN parameters

If an IN parameter is nullable:

```java
if (note == null) {
    cs.setNull(1, Types.VARCHAR);
} else {
    cs.setString(1, note);
}
```

Do not skip binding because the parameter index still must be assigned. If a procedure has overloads with the same name, untyped NULL can make overload resolution ambiguous; typed NULL and explicit signatures reduce issues.

### 13.5. Named parameters

CallableStatement supports setting parameters by name in some JDBC drivers, e.g., setString("P_STATUS", value). Oracle drivers support named notation via driver-specific APIs. Check the docs; with positional call syntax, keep indexes and signature order exact.

### 13.6. OUT REF CURSOR

Register an OUT cursor with Types.REF_CURSOR or OracleTypes.CURSOR depending on the driver:

```java
cs.registerOutParameter(1, Types.REF_CURSOR);
cs.execute();
try (ResultSet rs = (ResultSet) cs.getObject(1)) {
    while (rs.next()) {
        // consume rows
    }
}
```

Close the ResultSet and CallableStatement to release the server cursor.

### 13.7. Procedure overloads and NULL

PL/SQL allows overloading procedures/functions by parameter type. If a client binds NULL without an explicit type, Oracle may fail to pick the intended overload or the driver may report a type mismatch. Call package procedures with explicit signatures, use typed NULLs, or write wrapper procedures with unambiguous contracts.

## 14. Implicit conversion caused by bind data types

### 14.1. NUMBER column bound as VARCHAR

Example:

```sql
SELECT *
FROM orders
WHERE order_id = :p_id;
```

If order_id is NUMBER while the driver binds p_id as VARCHAR, Oracle must resolve the type mismatch. Depending on expression/type precedence, Oracle may convert either the bind or the expression. Inspect Predicate Information to determine the actual conversion.

### 14.2. Binding NUMBER for a VARCHAR2 column

If a column is VARCHAR2 while the application binds NUMBER, Oracle may convert character values or bind with unexpected semantics. Codes with leading zeros like 000123 can lose meaning when converted to numbers.

### 14.3. Binding DATE/TIMESTAMP as text

Date/time strings can depend on NLS_DATE_FORMAT, NLS_TIMESTAMP_FORMAT, NLS_DATE_LANGUAGE, and timezone. Use typed setters or explicit TO_DATE/TO_TIMESTAMP with explicit masks and NLS parameters.

### 14.4. Impact on indexes

If an implicit conversion/function is applied to an indexed column, the predicate may no longer qualify for normal index access. Do not guess from Java setters alone; inspect the actual cursor plan and Predicate Information.

### 14.5. Impact on partition pruning

If the partition key is wrapped in a function or conversion, partition pruning may degrade. Bind the exact type of the partition key and use range predicates matching its data type.

### 14.6. ORA-01722 and ORA-01861

- ORA-01722: invalid number, can occur when a character bind/value is converted to NUMBER with an invalid value.
- ORA-01861: literal does not match format string, can occur when text date/time does not match the format mask.

Fix the bind type and input contract; do not catch the error and retry the same invalid value.

### 14.7. Reading the execution plan

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE'
    )
);
```

PEEKED_BINDS only shows bind values/types peeked/captured by the optimizer subject to conditions and privileges; not every execution/bind is guaranteed to appear. Exercise caution when outputs contain sensitive values.

## 15. Bind metadata, cursor sharing, and child cursors

### 15.1. Bind data type is part of cursor semantics

Identical SQL text with different bind metadata can cause Oracle to create a different child cursor or fail to share cursors in some cases. Differences in data type, length, precision/scale, and optimizer environment can affect cursor compatibility.

### 15.2. Bind peeking

Oracle may peek bind values at parse time to estimate cardinality/plans. Bind data types also influence how predicates are interpreted. Adaptive Cursor Sharing can create multiple child cursors for varying selectivity; it does not fix an application binding the wrong type.

### 15.3. Checking child cursors

```sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    parse_calls,
    is_bind_sensitive,
    is_bind_aware
FROM v$sql
WHERE sql_text LIKE '%FROM orders%'
ORDER BY sql_id, child_number;
```

Searching SQL_TEXT is just an example; you can search by a known SQL_ID. Query V$SQL_SHARED_CURSOR to find why child cursors are not shared per release.

### 15.4. V$SQL_SHARED_CURSOR

This view provides reason flags explaining why child cursors are not shared. Columns and reasons can differ by release; inspect columns related to bind mismatch/optimizer mismatch when investigating.

### 15.5. Parameter metadata

PreparedStatement.getParameterMetaData can provide parameter info depending on the driver. Do not rely completely on the driver inferring every parameter type before binding, especially with NULLs, expressions, or PL/SQL calls. Applications should know the schema/procedure contract and bind explicitly.

## 26. Lab: creating a schema and binding exact types

Run only on a lab schema or authorized database. Do not use table/column names colliding with production objects.

### 26.1. Create the test table

```sql
CREATE TABLE jdbc_bind_lab (
    id             NUMBER(12,0) PRIMARY KEY,
    code           VARCHAR2(30 CHAR),
    note           NVARCHAR2(100),
    amount         NUMBER(12,2),
    event_date     DATE,
    event_time     TIMESTAMP(6),
    raw_value      RAW(32),
    payload        CLOB
);
```

### 26.2. Insert non-NULL values

```java
String sql = """
    INSERT INTO jdbc_bind_lab
      (id, code, note, amount, event_date, event_time, raw_value)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1L);
    ps.setString(2, "ORD-0001");
    ps.setNString(3, "Test order");
    ps.setBigDecimal(4, new BigDecimal("1250.75"));
    ps.setDate(5, java.sql.Date.valueOf(LocalDate.of(2026, 11, 14)));
    ps.setTimestamp(6, Timestamp.valueOf(
        LocalDateTime.of(2026, 11, 14, 21, 18, 30)));
    ps.setBytes(7, new byte[] {1, 2, 3, 4});
    ps.executeUpdate();
}
```

### 26.3. Insert typed NULLs

```java
String sql = """
    INSERT INTO jdbc_bind_lab
      (id, code, note, amount, event_date, event_time, raw_value, payload)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 2L);
    ps.setNull(2, Types.VARCHAR);
    ps.setNull(3, Types.NVARCHAR);
    ps.setNull(4, Types.NUMERIC);
    ps.setNull(5, Types.DATE);
    ps.setNull(6, Types.TIMESTAMP);
    ps.setNull(7, Types.VARBINARY);
    ps.setNull(8, Types.CLOB);
    ps.executeUpdate();
}
```

### 26.4. Verify data

```sql
SELECT
    id,
    code,
    note,
    amount,
    event_date,
    event_time,
    RAWTOHEX(raw_value) AS raw_hex,
    CASE WHEN payload IS NULL THEN 'NULL' ELSE 'NOT NULL' END AS payload_state
FROM jdbc_bind_lab
ORDER BY id;
```

Compare null/non-null rows and Unicode data. Confirm event_time retains fractional seconds according to column precision.

### 26.5. Check null getter

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT amount FROM jdbc_bind_lab WHERE id = ?")) {
    ps.setLong(1, 2L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal amount = rs.getBigDecimal(1);
            if (amount == null) {
                // SQL NULL
            }
        }
    }
}
```

### 26.6. Check wasNull

```java
int id = rs.getInt("id");
boolean wasNull = rs.wasNull();
```

This example illustrates getter/wasNull ordering; do not use getInt for NUMBER(12,2) if decimals are needed. To check NULL for amount, call the getter on the exact column and then call wasNull immediately afterward.

## 27. Lab: comparing bind types and conversions

### 27.1. Create numeric table and index

```sql
CREATE TABLE jdbc_number_lab (
    id NUMBER(12,0) PRIMARY KEY,
    description VARCHAR2(50)
);

INSERT INTO jdbc_number_lab
SELECT LEVEL, 'row-' || LEVEL
FROM dual
CONNECT BY LEVEL <= 10000;

CREATE INDEX ix_jdbc_number_lab_id
ON jdbc_number_lab(id);

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'JDBC_NUMBER_LAB',
        cascade => TRUE
    );
END;
/
```

### 27.2. Bind NUMBER

```java
String sql =
    "SELECT description FROM jdbc_number_lab WHERE id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 500L);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString(1));
        }
    }
}
```

### 27.3. Bind character

In the lab, run the same SQL using setString(1, "500"). Observe the plan/predicates and bind metadata. The result may still be correct thanks to implicit conversion, but this is not a contract an application should use when the column is NUMBER.

### 27.4. Inspect the plan

Run the SQL with GATHER_PLAN_STATISTICS and read DBMS_XPLAN.DISPLAY_CURSOR. Determine whether Oracle converts the bind or the column, whether the index is used, and what the actual predicates are.

### 27.5. Test an invalid value

Binding "ABC" with setString for a NUMBER predicate can trigger ORA-01722. Observe the error and compare with setLong. Do not run this test on a shared system with real workloads.

### 27.6. Takeaway

A text value can be converted to a number by Oracle and return the right result in simple tests, yet it still creates conversion/NLS dependencies and a fragile contract. Binding the exact column type keeps SQL cleaner and more stable.

## 28. Lab: typed NULL and PL/SQL overloads

### 28.1. Create test package

```sql
CREATE OR REPLACE PACKAGE jdbc_null_lab AS
    PROCEDURE accept_text(p_value VARCHAR2);
    PROCEDURE accept_number(p_value NUMBER);
END;
/

CREATE OR REPLACE PACKAGE BODY jdbc_null_lab AS
    PROCEDURE accept_text(p_value VARCHAR2) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE('TEXT');
    END;

    PROCEDURE accept_number(p_value NUMBER) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE('NUMBER');
    END;
END;
/
```

### 28.2. Call with typed NULL

When package overloads have parameters of different types, bind NULL with an explicit type:

```java
try (CallableStatement cs = connection.prepareCall(
        "{ call jdbc_null_lab.accept_text(?) }")) {
    cs.setNull(1, Types.VARCHAR);
    cs.execute();
}
```

And for NUMBER:

```java
try (CallableStatement cs = connection.prepareCall(
        "{ call jdbc_null_lab.accept_number(?) }")) {
    cs.setNull(1, Types.NUMERIC);
    cs.execute();
}
```

### 28.3. Why explicit signatures?

The procedure name in the call already specified the package member/signature in this example. In complex calls or dynamic PL/SQL blocks, typed NULLs and explicit signatures help avoid ambiguity. Do not use Types.NULL for all overloads.

## 29. Lab: timezone round-trip

### 29.1. Create table

```sql
CREATE TABLE jdbc_time_lab (
    id NUMBER PRIMARY KEY,
    local_ts TIMESTAMP(6),
    tz_ts TIMESTAMP(6) WITH TIME ZONE,
    local_tz_ts TIMESTAMP(6) WITH LOCAL TIME ZONE
);
```

### 29.2. Insert using java.time

On drivers with JDBC 4.2 java.time support:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO jdbc_time_lab VALUES (?, ?, ?, ?)")) {
    ps.setLong(1, 1L);
    ps.setObject(2, LocalDateTime.of(2026, 11, 14, 21, 18));
    ps.setObject(3,
        OffsetDateTime.parse("2026-11-14T21:18:00+07:00"));
    ps.setObject(4,
        OffsetDateTime.parse("2026-11-14T21:18:00+07:00"));
    ps.executeUpdate();
}
```

### 29.3. Read under two session timezones

Read the data in two sessions with different SESSIONTIMEZONE values. Compare TIMESTAMP WITH TIME ZONE and TIMESTAMP WITH LOCAL TIME ZONE. Displayed LTZ output can shift with session timezone; TSTZ preserves the value's timezone semantics.

### 29.4. Verify

```sql
SELECT
    id,
    local_ts,
    tz_ts,
    local_tz_ts,
    SESSIONTIMEZONE,
    DBTIMEZONE
FROM jdbc_time_lab
WHERE id = 1;
```

Do not conclude data is wrong solely because local display differs. Convert to a common Instant/UTC or timezone contract before comparing.

## 30. Lab: driver metadata and bind capture

### 30.1. Record the driver

Run DatabaseMetaData.getDriverName/getDriverVersion/getDatabaseProductVersion in the application and save them alongside test logs.

### 30.2. Find the SQL_ID

After running a lab SQL statement, the DBA locates the SQL_ID in V$SQL using module/action or SQL text. Avoid searching by sensitive literals.

### 30.3. View bind metadata

```sql
SELECT
    sql_id,
    child_number,
    name,
    position,
    datatype_string,
    max_length,
    precision,
    scale,
    last_captured
FROM v$sql_bind_capture
WHERE sql_id = :p_sql_id
ORDER BY child_number, position;
```

Not every execution has captured binds. If no rows appear, do not conclude the driver did not bind parameters.

### 30.4. Compare child cursors

```sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    parse_calls
FROM v$sql
WHERE sql_id = :p_sql_id
ORDER BY child_number;
```

If multiple child cursors exist, check V$SQL_SHARED_CURSOR and bind mismatch. Compare the same SQL text with different setters/types in the lab to observe driver/Oracle behavior.

## 31. Troubleshooting matrix

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| ORA-01722 | Character bind/value converted to NUMBER with invalid value | Bind NUMBER with exact type, validate input, and inspect Predicate Information |
| ORA-01861/ORA-01843 | Text date does not match mask/NLS | Use typed date/time setters or explicit parsing |
| ORA-00932 | Expression/parameter mixes incompatible data types | Use explicit CAST and align bind contracts |
| ORA-01008 | Unbound placeholder remains | Count placeholders, check all null/non-null branches and indexes |
| ORA-17004 | Invalid JDBC type for driver/API | Distinguish Types/OracleTypes, check driver and SQL type |
| NULL does not enter intended overload | Untyped NULL or ambiguous overload | Use setNull with exact JDBC type, wrapper procedure with clear signature |
| Monetary values lose precision | Using double/float for exact decimals | Use BigDecimal and explicit rounding rules |
| Date/time hours shifted | Differing JVM/session/database timezones | Define timezone contract, use java.time/Calendar consistently |
| Time lost when reading Oracle DATE | Using getDate for column containing time | Use Timestamp/LocalDateTime mapping per driver semantics |
| Corrupted Unicode characters | Incorrect character set/NCHAR mapping | Check setNString, NLS_NCHAR_CHARACTERSET, and driver |
| Long string errors | Using setString past limits/LOB mapping | Use CLOB/NCLOB stream setters |
| Batch insert writes wrong data | Previous parameter retained or bind type changed | Bind every index per row, use typed setNull |
| Child cursor count grows | Differing bind metadata/length/optimizer env | Standardize setters and check V$SQL_SHARED_CURSOR |
| REF CURSOR cast fails | Unsupported driver/JDBC type or wrong OUT type | Use appropriate Types.REF_CURSOR/OracleTypes.CURSOR |
| ARRAY/STRUCT errors | Wrong type name/schema or vendor-specific API | Verify named type and Oracle JDBC API/version |

### 31.1. Investigation workflow

1. Confirm the Oracle column/procedure parameter data type.
2. Record the Java runtime class of the value, including null.
3. Record the actual setter/Types/OracleTypes called.
4. Confirm driver name/version and JDBC API support.
5. Retrieve SQL_ID/child cursor and bind metadata if available.
6. Read Predicate Information to detect implicit conversions.
7. Build a minimal reproducer on the exact driver/database version.
8. Fix the contract in the DAO/repository layer and run round-trip tests.

### 31.2. Distinguishing bind errors from data errors

If setBigDecimal still receives ORA-01438, the value may exceed column precision; this is data not fitting the schema, not a wrong JDBC bind type. If setString for VARCHAR2 hits ORA-12899, check BYTE/CHAR length and character expansion. Do not change JDBC types to mask constraint/data-size issues.

### 31.3. Distinguishing driver errors from SQL errors

ORA- errors usually stem from database semantics; SQLRecoverableException/SQLTransientConnectionException or vendor codes may come from transport/session layers. Record SQLState, vendor error code, cause chain, and driver version. Do not classify every SQLException as a bind error.

## 32. Best practice principles

1. **Read the schema before binding.** Know column data types, precision, scale, length semantics, and timezone semantics.
2. **Use specialized setters.** Use setLong/setBigDecimal for NUMBER; setString for VARCHAR2; appropriate temporal setters for DATE/TIMESTAMP.
3. **Always use explicit typed NULLs.** setNull(index, Types.X) reflects the SQL parameter contract.
4. **Avoid indiscriminate Types.NULL.** Use specific JDBC types, especially with procedure overloads, expressions, and UDTs.
5. **Do not bind everything as String.** Avoid implicit conversions and NLS dependencies.
6. **Use BigDecimal for exact decimals.** Never use double for currency or rates needing exact precision.
7. **Remember Oracle DATE carries time.** Pick get/set APIs so you do not accidentally drop the time component.
8. **Control timezones.** Distinguish TIMESTAMP, TSTZ, LTZ, JVM timezone, and session timezone.
9. **Use setNString when the contract is national character.** Verify Unicode round-trip.
10. **Use stream/LOB APIs for large data.** Manage length and lifecycle properly.
11. **Keep bind types consistent across executions.** The same placeholder must not change data type across code branches.
12. **Re-bind all parameters when reusing statements.** New nulls must call setNull rather than leaving old values.
13. **Isolate JDBC mapping in the DAO/repository.** One schema contract should have one consistent mapping.
14. **Prefer standard JDBC before Oracle extensions.** Use vendor APIs only when Oracle-specific features are required.
15. **Pin driver versions.** Never mix multiple ojdbc JARs at runtime.
16. **Test after driver/database upgrades.** Include nulls, temporals, LOBs, UDTs, and batches.
17. **Do not rely blindly on setObject inference.** Specify target SQL types when runtime inference is ambiguous.
18. **Use PreparedStatement.** Bind values instead of concatenating user input into SQL.
19. **Do not bind identifiers.** Dynamic table/column names must go through an allowlist.
20. **Check actual execution plans.** Inspect conversions, index access, and child cursors when issues arise.
21. **Do not rely solely on bind capture.** Capture views have sampling and limitations.
22. **Protect bind values.** Never log secrets/PII in application logs, traces, or plan output.
23. **Use wasNull with primitive getters.** Distinguish SQL NULL from 0/false.
24. **Close resources.** ResultSets, statements, streams, LOBs, and Arrays must have clear lifecycles.
25. **Test on the exact driver.** Test with the same JDK, ojdbc artifact, and Oracle release as production.

## 33. Self-check questions

1. How do Java types, JDBC types, and Oracle SQL types differ?
2. How does Types.NUMERIC differ from Oracle NUMBER(p,s)?
3. What is JDBCType and in which JDBC version was it added?
4. When is OracleTypes used?
5. Why is setString unsuitable for every column?
6. Why is setBigDecimal better suited than setDouble for currency?
7. How does Oracle DATE differ from JDBC DATE?
8. Which semantics do LocalDate, LocalDateTime, and OffsetDateTime match?
9. Which timezone does TIMESTAMP WITH LOCAL TIME ZONE display in?
10. Which parameters does setNull require?
11. Why is setObject(index, null) less explicit than a typed NULL?
12. When is setNull with typeName needed?
13. How does Types.NULL differ from Types.VARCHAR/NUMERIC?
14. Why can NULL make procedure overloads ambiguous?
15. How does Types.REF_CURSOR differ from OracleTypes.CURSOR?
16. Why does an Oracle named collection need a type name?
17. How does setNString differ from setString in intent?
18. How does RAW differ from BLOB?
19. When should setCharacterStream/setBinaryStream be used?
20. Why must batches re-bind every parameter on every row?
21. When should wasNull be called?
22. Why is status = NULL not equivalent to status IS NULL?
23. Why does IN (?) not automatically expand a Java list?
24. How do bind data types affect implicit conversion/index access?
25. Does V$SQL_BIND_CAPTURE record every bind value?
26. Why can the same SQL text have multiple child cursors?
27. Which components must the JDBC driver artifact be compatible with?
28. When is OracleConnection.unwrap needed?
29. How do you test timezone round-trip behavior?
30. What information should be recorded when investigating a bind type error?

## 34. Mental model

```text
JAVA VALUE
  String / BigDecimal / LocalDateTime / OffsetDateTime / byte[]
       |
       v
JDBC TYPE CONTRACT
  Types.* / JDBCType.* / OracleTypes.*
       |
       +-- setString / setBigDecimal / setTimestamp
       +-- setNull(index, type)
       +-- setObject(index, value, targetType)
       +-- registerOutParameter(index, type)
       |
       v
ORACLE JDBC DRIVER
  Mapping + conversion + metadata
       |
       v
ORACLE SQL TYPE
  NUMBER / VARCHAR2 / DATE / TIMESTAMP / RAW / LOB / UDT
       |
       v
SQL EXECUTION
  Implicit conversion? Index access? Cursor sharing?
       |
       v
READ BACK
  getBigDecimal / getTimestamp / getObject
  wasNull / ResultSet / LOB lifecycle
       |
       v
DIAGNOSTICS
  Schema metadata / V$SQL_BIND_CAPTURE
  DBMS_XPLAN / driver version / SQL error
```

**Key takeaway:** Java classes, JDBC types, and Oracle SQL data types are three distinct layers. Bind exact types matching the schema and business logic; for NULLs, specify the JDBC type explicitly with setNull. Use BigDecimal for decimal NUMBERs, choose temporal mappings based on timezone semantics, and use Oracle extensions when standard JDBC is insufficient. When errors occur, cross-check the schema, setters, driver version, bind metadata, and actual execution plan rather than relying on displayed values in Java.

## 16. Parameter metadata and bind capture in Oracle

### 16.1. V$SQL_BIND_CAPTURE

DBAs can inspect bind metadata captured by Oracle:

```sql
SELECT
    sql_id,
    child_number,
    name,
    position,
    datatype_string,
    max_length,
    precision,
    scale,
    last_captured
FROM v$sql_bind_capture
WHERE sql_id = :p_sql_id
ORDER BY child_number, position;
```

Bind capture uses sampling and has limits; it does not record every bind on every execution. Some data types/values are not captured or values may be masked. It is a diagnostic tool, not a complete audit log.

### 16.2. Sensitive bind values

Bind capture/plan output can expose data such as account numbers, emails, tokens, or personal information. Restrict access permissions, mask outputs when sharing tickets, and follow retention/audit policies.

### 16.3. Checking column data types

Verify the schema:

```sql
SELECT
    column_name,
    data_type,
    data_length,
    char_length,
    char_used,
    data_precision,
    data_scale
FROM user_tab_columns
WHERE table_name = 'ORDERS'
ORDER BY column_id;
```

If the table belongs to another schema, use ALL_TAB_COLUMNS/DBA_TAB_COLUMNS with appropriate privileges. Column metadata is the basis for choosing setters and NULL types.

### 16.4. SQL Monitor and actual plans

When SQL is slow, combine SQL_ID, child_number, actual execution plan, bind metadata, wait events, and application tracing. Do not conclude bind type is the root cause solely because multiple child cursors appear.

## 17. JDBC driver versions and compatibility

### 17.1. Drivers must be compatible with JDK/database

Oracle JDBC offers multiple driver lines such as ojdbc8, ojdbc11, ojdbc17, and release-specific artifacts. Artifact names generally reflect the JDK baseline, not that they can only connect to a specific database version. Check Oracle's compatibility matrix for JDK, database release, and driver.

### 17.2. Do not mix multiple ojdbc JARs

A classpath containing multiple ojdbc versions can cause NoSuchMethodError, ClassCastException, unintended driver loading, or API extension mismatches. Deploy only one controlled driver version in the application runtime, unless a special tested architecture requires otherwise.

### 17.3. Checking driver at runtime

```java
DatabaseMetaData md = connection.getMetaData();

System.out.println(md.getDriverName());
System.out.println(md.getDriverVersion());
System.out.println(md.getDatabaseProductName());
System.out.println(md.getDatabaseProductVersion());
```

Record the driver version in diagnostics when investigating type mapping, timezone, or LOB issues.

### 17.4. JDBC version

```java
System.out.println(md.getJDBCMajorVersion());
System.out.println(md.getJDBCMinorVersion());
```

The JDK API may include the setObject(SQLType) overload, but the driver must support it. Successful compilation does not guarantee every runtime driver implements the overload with expected semantics.

### 17.5. Java 8 and Java 17+

Text blocks in Java examples require JDK 15+. On JDK 8, use concatenated string literals. java.time has existed since Java 8, but JDBC 4.2 mapping depends on the driver. Choose the ojdbc artifact matching your JDK and verify the feature matrix.

### 17.6. Driver upgrades

After upgrading the driver, test:

- setNull for every nullable parameter.
- NUMBER precision/scale and rounding.
- DATE/TIMESTAMP/timezone round-trip.
- NCHAR/NVARCHAR2 and Unicode.
- LOB streaming/length.
- ARRAY/STRUCT/REF CURSOR if used.
- Batching, statement caching, and cursor sharing.
- Failover/reconnect if using RAC/ONS.

Do not promote a driver upgrade to production without testing data correctness and performance.

## 18. Batch binding

### 18.1. addBatch with PreparedStatement

PreparedStatement allows binding multiple sets of values and calling addBatch:

```java
String sql =
    "INSERT INTO jdbc_bind_lab(id, note, amount) VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (LabRow row : rows) {
        ps.setLong(1, row.id());

        if (row.note() == null) {
            ps.setNull(2, Types.VARCHAR);
        } else {
            ps.setString(2, row.note());
        }

        if (row.amount() == null) {
            ps.setNull(3, Types.NUMERIC);
        } else {
            ps.setBigDecimal(3, row.amount());
        }

        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
}
```

The example uses record accessors, which require a JDK supporting records; on older JDKs, use getters.

### 18.2. Every batch row must keep the same parameter type

Avoid binding index 2 as VARCHAR on the first batch item and binding the same index as NUMBER or an untyped NULL on a later item. Maintain a consistent data type contract for each placeholder across the entire batch.

### 18.3. Batching and NULL

Null rows must use typed setNull just like non-null rows:

```java
if (row.amount() == null) {
    ps.setNull(3, Types.NUMERIC);
} else {
    ps.setBigDecimal(3, row.amount());
}
```

Do not skip calling a setter when a value is null, because PreparedStatement can retain the value from the previous bind at that parameter index.

### 18.4. Clearing parameters

clearParameters can be used to clear all parameter values when reusing a statement, though re-binding every parameter on each iteration is usually clearer. Never rely on stale bind values.

### 18.5. Batch update counts

executeBatch returns update counts or throws BatchUpdateException. Oracle JDBC may apply batch execution/array DML optimizations depending on the driver. On error, handle partial success, transaction rollback, and idempotency per batch semantics.

### 18.6. Batching and transactions

Manage autoCommit/commit explicitly around batch boundaries:

```java
connection.setAutoCommit(false);
try {
    // bind and execute batches
    connection.commit();
} catch (SQLException e) {
    connection.rollback();
    throw e;
}
```

Do not commit every row if business logic requires an atomic batch. For very large batches, design chunk sizes and recovery strategies.

## 19. NULL in dynamic SQL and filters

### 19.1. Optional filters

Applications often have optional filters. SQL:

```sql
WHERE (:p_status IS NULL OR status = :p_status)
```

may bind the same value at two positions, requiring both to be bound with the appropriate type. Depending on cardinality and optimizer behavior, optional predicates can affect execution plans.

### 19.2. Binding the same value multiple times

```java
if (status == null) {
    ps.setNull(1, Types.VARCHAR);
    ps.setNull(2, Types.VARCHAR);
} else {
    ps.setString(1, status);
    ps.setString(2, status);
}
```

### 19.3. IS NULL does not need binding NULL

To filter for NULL columns, the explicit SQL is:

```sql
WHERE status IS NULL
```

Do not write status = NULL and bind NULL expecting it to behave like IS NULL. In SQL, status = NULL does not evaluate to TRUE.

### 19.4. Dynamic-size IN lists

JDBC does not support a single placeholder expanding automatically to a list of scalar values like IN (?). Applications must generate the corresponding number of placeholders, use Oracle collection/array types, or use another designed mechanism.

Example generating placeholders:

```java
String placeholders = ids.stream()
    .map(id -> "?")
    .collect(Collectors.joining(","));
String sql = "SELECT * FROM orders WHERE order_id IN (" +
             placeholders + ")";
```

Only assemble SQL structure controlled by the application; values must still be bound separately. For large lists, consider Oracle collection types, global temporary tables, or staging tables.

### 19.5. Do not bind column/table names as values

Bind variables represent expression values; they cannot replace identifiers or keywords. You cannot use FROM ? to bind a table name. Dynamic identifiers must come from an allowlist and be properly quoted/validated; never concatenate arbitrary input to prevent SQL injection.

### 19.6. SQL injection

PreparedStatement separates values from SQL text. Never concatenate user input into predicates, ORDER BY clauses, or table names. If dynamic sort columns are needed, map logical sort keys to an allowlisted set of identifiers.

## 20. Oracle JDBC connection/session settings

### 20.1. NLS settings

Typed binding reduces NLS dependencies when handling numbers/dates. However, NLS still affects string conversions, sorting, collation, and certain format operations. Do not replace typed binds with setString and rely on NLS_DATE_FORMAT/NLS_NUMERIC_CHARACTERS.

### 20.2. Session timezone

If using TIMESTAMP WITH LOCAL TIME ZONE or conversions based on session timezone, verify SESSIONTIMEZONE. Connection pools reuse sessions; any change to session timezone must be reset before returning the connection to the pool.

### 20.3. NLS_NUMERIC_CHARACTERS

When an application binds BigDecimal, the driver transmits a numeric value rather than a text format. This avoids dependence on decimal/thousands separators. If numeric strings are bound instead, parsing can depend on NLS_NUMERIC_CHARACTERS and corrupt data.

### 20.4. Character sets

The database character set and national character set govern text storage. The driver handles conversions from Java Unicode; test round-trips with Vietnamese characters, supplementary characters, and long data.

### 20.5. Connection pool reset

The pool must manage transactions, autocommit, schema, roles, NLS, timezone, and other session settings. Never let one request alter session state and leak it to the next request. Consistent bind types are part of the connection/SQL contract.

## 21. Diagnostics for wrong bind types

### 21.1. ORA-01722

Commonly occurs when character data/binds are converted to NUMBER with an invalid value. Check:

- Column data type and bind data type.
- Whether input uses locale-specific commas/periods.
- Leading/trailing whitespace or non-numeric characters.
- Which predicate triggers implicit TO_NUMBER.
- SQL plan and bind capture.

### 21.2. ORA-01861 and ORA-01843

Date/time conversion errors usually stem from text failing to match format or language. Use setDate/setTimestamp or java.time mappings; if an API receives text, parse at the application boundary and validate the format.

### 21.3. ORA-00932

Inconsistent data types across expressions/parameters, often appearing when COALESCE/CASE/UNION/PLSQL overloads mix types. Add explicit CASTs and align bind contracts.

### 21.4. ORA-01461 / LOB errors

Errors related to binding long strings or exceeding limits can depend on driver version, SQL data type, and setter API. Use stream/LOB APIs matching the column type; do not assume setString handles arbitrary sizes.

### 21.5. ORA-01008: not all variables bound

A placeholder was not set. Check 1-based indexes, placeholder counts, null/non-null branches, and re-binding all parameters when reusing statements.

### 21.6. ORA-17004: invalid column type

The driver does not accept the JDBC/Oracle type passed to that API. Check Types vs. OracleTypes, driver version, the invoked overload, and column/procedure data types.

### 21.7. Cursor mismatch

If the same SQL text produces multiple child cursors, check V$SQL_SHARED_CURSOR, bind metadata, and optimizer environment. Standardize Java setters for each parameter position across all code paths.

### 21.8. Inspecting actual predicates

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_number,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE'
    )
);
```

Depending on the DBMS_XPLAN overload, pass SQL_ID/child number or NULL for the current cursor. Do not share outputs containing sensitive bind values.

## 22. Reading data and handling SQL NULL

### 22.1. Scalar getters

JDBC provides corresponding getters:

| Oracle type | Common getter |
| --- | --- |
| NUMBER integer range | getInt/getLong |
| NUMBER decimal | getBigDecimal |
| VARCHAR2/CHAR | getString |
| DATE | getDate or getTimestamp per semantics |
| TIMESTAMP | getTimestamp |
| BLOB | getBlob/getBinaryStream |
| CLOB | getClob/getCharacterStream |
| RAW | getBytes |
| REF CURSOR | getObject/getResultSet per driver/API |

Choose getters according to column semantics and value range. getLong is unsuitable for NUMBER(38) values that may exceed the Long range.

### 22.2. wasNull with primitive getters

If a SQL value is NULL, primitive getters such as getInt/getLong/getBoolean return default values (0/false). Call wasNull immediately after the getter to determine whether the original value was NULL:

```java
int quantity = rs.getInt("quantity");
if (rs.wasNull()) {
    // SQL NULL
} else {
    // quantity has a value, including 0
}
```

wasNull applies to the most recently read value. Calling another getter before wasNull changes which value wasNull checks.

### 22.3. Using wrappers/BigDecimal to preserve NULL

```java
Integer quantity = (Integer) rs.getObject("quantity");
BigDecimal amount = rs.getBigDecimal("amount");
```

getBigDecimal returns null on SQL NULL. For primitive wrappers, getObject class mapping behavior depends on the driver/JDBC version; you can use getObject(column, Integer.class) if supported by the driver.

### 22.4. getObject with target Java class

JDBC 4.1+ offers getObject(index, Class<T>) for supported type mappings:

```java
LocalDate orderDate = rs.getObject("order_date", LocalDate.class);
LocalDateTime createdAt =
    rs.getObject("created_at", LocalDateTime.class);
```

Oracle driver support depends on version and Oracle data type. Test with specific DATE/TIMESTAMP columns; do not assume all Oracle timezone types map cleanly to every java.time class.

### 22.5. Reading TIMESTAMP WITH TIME ZONE

If supported by the driver:

```java
OffsetDateTime occurredAt =
    rs.getObject("occurred_at", OffsetDateTime.class);
```

If preserving region timezone is required, verify mapping and store ZoneId separately if Oracle/the driver does not return the region identifier.

### 22.6. NULL and primitive boolean

getBoolean returns false for SQL NULL; call wasNull to distinguish false from NULL. Do not map null to false if business logic needs an unknown state.

### 22.7. ResultSet getters and timezones

getTimestamp(column) has an overload accepting Calendar. When using that overload, timezone conversion must follow the application's contract. Never mix different JVM default timezones across nodes uncontrolled.

## 23. Safe code patterns for binding parameters

### 23.1. Helper for binding nullable String

```java
static void bindNullableVarchar(
        PreparedStatement ps, int index, String value)
        throws SQLException {
    if (value == null) {
        ps.setNull(index, Types.VARCHAR);
    } else {
        ps.setString(index, value);
    }
}
```

This helper should only be used when the parameter contract is VARCHAR2/character. Do not create a single generic helper that always uses VARCHAR for every NULL.

### 23.2. Helper for nullable BigDecimal

```java
static void bindNullableNumber(
        PreparedStatement ps, int index, BigDecimal value)
        throws SQLException {
    if (value == null) {
        ps.setNull(index, Types.NUMERIC);
    } else {
        ps.setBigDecimal(index, value);
    }
}
```

If the schema defines precision/scale and business rounding rules, normalize the BigDecimal before calling the helper.

### 23.3. Helper for nullable Timestamp

```java
static void bindNullableTimestamp(
        PreparedStatement ps, int index, Timestamp value)
        throws SQLException {
    if (value == null) {
        ps.setNull(index, Types.TIMESTAMP);
    } else {
        ps.setTimestamp(index, value);
    }
}
```

Use only for compatible TIMESTAMP semantics. If the column is TIMESTAMP WITH TIME ZONE, choose OffsetDateTime/Oracle type mapping instead of defaulting to Types.TIMESTAMP.

### 23.4. Separating SQL contracts from domain objects

Domain objects may use Optional, BigDecimal, or java.time. The Repository/DAO is responsible for converting to JDBC types per the schema. Do not let different application layers pick different Types.* for the same column.

### 23.5. Bind every placeholder on every execution

When reusing a PreparedStatement, every parameter index must be reassigned for each execution. If the new value is null, call typed setNull; otherwise, the driver may retain the old bind value or report a missing parameter depending on the situation.

### 23.6. Resource lifecycle

Use try-with-resources for PreparedStatement, CallableStatement, ResultSet, and streams. Ensure the connection/transaction remains open while binding, executing, and consuming LOBs or REF CURSORs.

### 23.7. Do not log bind values by default

Log SQL_ID, parameter position, JDBC type, null/non-null, and length when diagnosing. Avoid logging full sensitive values. If sampling is needed, mask or hash according to policy.

## 24. Advanced setNull and named SQL types

### 24.1. Overload with typeName

JDBC provides:

```java
ps.setNull(parameterIndex, sqlType, typeName);
```

This overload is useful for named user-defined types such as STRUCT/ARRAY. For ordinary scalar NUMBER/VARCHAR/DATE, typeName is unnecessary.

### 24.2. Types.NULL

Types.NULL is a generic JDBC null type. It does not accurately describe Oracle parameter types like VARCHAR, NUMBER, or TIMESTAMP. In simple SQL expressions, the driver/Oracle can sometimes infer from context, but for overloads/procedures/complex expressions, use a specific type.

### 24.3. Null for REF CURSOR

If a procedure parameter is a REF CURSOR IN/OUT, use JDBC Types.REF_CURSOR or OracleTypes.CURSOR per driver support. Do not use Types.VARCHAR just because the cursor is retrieved with getObject.

### 24.4. Null for named object types

```java
ps.setNull(1, Types.STRUCT, "APP.ADDRESS_T");
```

If the schema type changes or the name is not properly qualified, the driver may report an invalid type. Confirm the type name in ALL_TYPES/ALL_TYPE_ATTRS and the schema owner.

### 24.5. Null for collections

```java
ps.setNull(1, Types.ARRAY, "APP.NUMBER_LIST_T");
```

Some Oracle drivers require an Oracle-specific SQL type constant or specific type name format. Verify in integration tests with the exact driver; do not assume all databases/drivers handle Types.ARRAY identically.

### 24.6. Null and overload resolution

If a package declares:

```sql
PROCEDURE update_value(p_value NUMBER);
PROCEDURE update_value(p_value VARCHAR2);
```

then an untyped NULL can make overload resolution ambiguous. Call the intended signature via wrappers/typed binds. Another option is naming procedures distinctly so client APIs do not rely on complex overload resolution.

## 25. Driver-specific legacy APIs

### 25.1. oracle.sql package

Legacy classes in oracle.sql such as ARRAY, STRUCT, TIMESTAMP, TIMESTAMPTZ, and BLOB/CLOB may appear in older codebases. Oracle provides newer APIs in oracle.jdbc and standard JDBC; many legacy classes are deprecated or scheduled for replacement depending on version.

Do not refactor en masse without testing. When writing new code, prefer java.sql/java.time and current Oracle JDBC APIs documented for your driver.

### 25.2. OraclePreparedStatement

OraclePreparedStatement provides extensions such as bind form-of-use, batching, and Oracle-specific features. Use them when standard JDBC is insufficient; unwrap the connection/statement via supported APIs and isolate vendor-specific code inside a small adapter.

### 25.3. Legacy NCHAR form-of-use

Some legacy code uses OraclePreparedStatement.setFormOfUse with FORM_NCHAR to indicate national character semantics. Modern code usually uses setNString/setNCharacterStream. Do not mix both mechanisms simultaneously without understanding driver behavior.

### 25.4. OracleConnection unwrap

When extensions are needed:

```java
OracleConnection oracleConnection =
    connection.unwrap(OracleConnection.class);
```

unwrap is the standard JDBC way to obtain vendor interfaces from pooled/proxy connections. Do not cast a pooled connection directly to OracleConnection when the pool returns another wrapper.

### 25.5. Closing Oracle-specific resources

Array, Blob, Clob, ResultSet, and Oracle extension objects have their own lifecycles. Call free()/close() when required by the API; release them in appropriate finally/try-with-resources blocks.

## 11. Oracle-specific types and OracleTypes

### 11.1. When are Oracle extensions needed?

Standard JDBC covers most common scalar types. Some Oracle types/features lack sufficiently detailed standard mappings, or older driver versions require vendor-specific APIs. In those cases, OracleTypes, OracleConnection, or classes in oracle.jdbc may be needed.

Prefer standard JDBC types whenever they capture the semantics accurately and the driver supports them. Use Oracle extensions only when Oracle-specific features are needed or standard mappings fall short.

### 11.2. OracleTypes

Oracle JDBC has the OracleTypes constants class representing Oracle data types/features. Depending on driver version, constants may include CURSOR, TIMESTAMP, TIMESTAMPTZ, TIMESTAMPLTZ, INTERVALYM, INTERVALDS, BINARY_FLOAT, BINARY_DOUBLE, STRUCT, ARRAY, and others.

Legacy API style example:

```java
import oracle.jdbc.OracleTypes;

callable.registerOutParameter(1, OracleTypes.CURSOR);
```

With drivers supporting JDBC 4.2, Types.REF_CURSOR can be used for REF CURSOR. Check your Oracle JDBC version before selecting an API; do not copy constants from one ojdbc version to another driver without building/testing.

### 11.3. REF CURSOR

REF CURSOR is a cursor handle returned by PL/SQL to the client. Standard JDBC has Types.REF_CURSOR since JDBC 4.2; older Oracle drivers may use OracleTypes.CURSOR.

Example:

```java
String call = "{ call customer_api.list_customers(?) }";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.registerOutParameter(1, Types.REF_CURSOR);
    cs.execute();

    try (ResultSet rs = (ResultSet) cs.getObject(1)) {
        while (rs.next()) {
            long id = rs.getLong("customer_id");
            String name = rs.getString("full_name");
        }
    }
}
```

Check whether the driver supports Types.REF_CURSOR and check the actual procedure signature. Cursor ResultSets must be closed; they can hold server cursors and database resources.

### 11.4. STRUCT and Oracle object types

Oracle object types can be represented via java.sql.Struct or Java class mappings depending on driver/API. Example:

```sql
CREATE TYPE address_t AS OBJECT (
    street VARCHAR2(100),
    city   VARCHAR2(60)
);

CREATE TABLE customer_address (
    customer_id NUMBER,
    address     address_t
);
```

JDBC:

```java
Object[] attributes = {"12 Nguyen Hue", "Ho Chi Minh City"};
Struct address = connection.createStruct(
    "APP.ADDRESS_T", attributes);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO customer_address(customer_id, address) VALUES (?, ?)")) {
    ps.setLong(1, 100L);
    ps.setObject(2, address);
    ps.executeUpdate();
}
```

Type names generally must include the exact schema. How Struct is created and UDT support depend on the Oracle JDBC driver; Oracle-specific type mapping may require OracleConnection/OracleData APIs.

### 11.5. NULL for STRUCT/ARRAY with type name

JDBC provides a setNull overload accepting typeName:

```java
ps.setNull(1, Types.STRUCT, "APP.ADDRESS_T");
```

The type name helps the driver identify the named SQL type. For collections, use Types.ARRAY and the matching collection type name if supported by the driver. Verify schema qualification and EXECUTE privileges on the type.

### 11.6. Collections and ARRAY

Oracle nested tables/VARRAYs are named collection types. Do not assume Connection.createArrayOf behaves identically across all databases; Oracle JDBC typically provides OracleConnection.createOracleArray with the SQL collection type name:

```java
OracleConnection oracleConnection =
    connection.unwrap(OracleConnection.class);

Array values = oracleConnection.createOracleArray(
    "APP.NUMBER_LIST_T",
    new BigDecimal[] {
        new BigDecimal("10"),
        new BigDecimal("20")
    });

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO batch_ids(ids) VALUES (?)")) {
    ps.setArray(1, values);
    ps.executeUpdate();
} finally {
    values.free();
}
```

This is an illustrative example. The collection type must already exist in Oracle and the name must match exactly. Exact Oracle JDBC APIs depend on the driver; avoid legacy oracle.sql.ARRAY classes if newer drivers provide replacement APIs.

### 11.7. INTERVAL

Oracle INTERVAL YEAR TO MONTH and INTERVAL DAY TO SECOND do not map cleanly one-to-one to every Java Duration/Period. Period represents years/months; Duration represents durations in seconds/nanoseconds. Choose mappings by semantics and use Oracle-specific APIs if exact interval types must be preserved.

### 11.8. ROWID and UROWID

JDBC has java.sql.RowId. Oracle ROWID/UROWID carries row-location semantics; do not use it as a stable business key or cross-database identifier. If binding, use RowId/setRowId when supported by the driver and never serialize ROWID as a business key.

### 11.9. BFILE

BFILE is a locator to a file external to the database and is typically read-only via Oracle-specific APIs. It is not like BLOB; file content is not stored inside datafiles as internal LOBs are. Working with BFILE requires directory object privileges and proper locator lifecycle management.

### 11.10. XMLTYPE and JSON

XMLTYPE/JSON support depends on the Oracle Database release and JDBC driver. Some releases provide Oracle-specific XML/JSON APIs; newer releases add JDBC mappings for JSON. Do not assume calling setString on every JSON parameter preserves binary/native JSON semantics. Verify column type, driver API, and round-trip behavior.

## 12. BOOLEAN: SQL BOOLEAN and PL/SQL BOOLEAN

### 12.1. PL/SQL BOOLEAN

PL/SQL BOOLEAN has existed in PL/SQL for a long time, but Oracle Database releases before 23ai lacked a SQL BOOLEAN column type for direct use in tables/queries as a regular SQL data type.

Some Oracle JDBC drivers provide extensions to bind PL/SQL BOOLEAN in procedure/function calls. Exact constants/APIs depend on the driver, such as OracleTypes.PLSQL_BOOLEAN in supporting versions.

### 12.2. SQL BOOLEAN in newer releases

Oracle Database 23ai adds SQL BOOLEAN. With a supporting database/driver, JDBC boolean mapping can use setBoolean/getBoolean or JDBCType.BOOLEAN depending on driver version.

Do not use JDBC BOOLEAN with older databases assuming it will automatically and safely map to NUMBER(1) or CHAR(1).

### 12.3. Legacy mappings

For databases without SQL BOOLEAN, schemas commonly use:

- NUMBER(1) with 0/1.
- CHAR(1)/VARCHAR2 with Y/N or T/F.

Pick a consistent contract. Add CHECK constraints to reject out-of-set values and handle null mappings separately.

### 12.4. Boolean NULL

A nullable boolean has three business states: TRUE, FALSE, and UNKNOWN/NULL. Do not automatically map NULL to false if business logic needs to distinguish them. Use setNull with the JDBC type supported by the driver/database or represent it via the legacy schema contract.

## 13. CallableStatement and procedure parameters

### 13.1. IN parameters

IN parameters use setters just like PreparedStatement:

```java
String call = "{ call order_api.update_status(?, ?) }";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setLong(1, orderId);
    cs.setString(2, "SHIPPED");
    cs.execute();
}
```

### 13.2. OUT parameters

OUT parameters must register their JDBC type before execute:

```java
String call = "{ call order_api.get_total(?, ?) }";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setLong(1, customerId);
    cs.registerOutParameter(2, Types.NUMERIC);
    cs.execute();

    BigDecimal total = cs.getBigDecimal(2);
}
```

JDBC indexes start at 1. The registered type in registerOutParameter must be compatible with the procedure parameter.

### 13.3. IN OUT parameters

An IN OUT parameter both binds input and registers output:

```java
cs.setBigDecimal(1, startingBalance);
cs.registerOutParameter(1, Types.NUMERIC);
cs.execute();
BigDecimal resultingBalance = cs.getBigDecimal(1);
```

Some drivers require registering before setting or vice versa per API; follow the JDBC/Oracle driver documentation and test.

### 13.4. NULL IN parameters

If an IN parameter is nullable:

```java
if (note == null) {
    cs.setNull(1, Types.VARCHAR);
} else {
    cs.setString(1, note);
}
```

Do not skip binding because the parameter index still must be assigned. If a procedure has overloads with the same name, untyped NULL can make overload resolution ambiguous; typed NULL and explicit signatures reduce issues.

### 13.5. Named parameters

CallableStatement supports setting parameters by name in some JDBC drivers, e.g., setString("P_STATUS", value). Oracle drivers support named notation via driver-specific APIs. Check the docs; with positional call syntax, keep indexes and signature order exact.

### 13.6. OUT REF CURSOR

Register an OUT cursor with Types.REF_CURSOR or OracleTypes.CURSOR depending on the driver:

```java
cs.registerOutParameter(1, Types.REF_CURSOR);
cs.execute();
try (ResultSet rs = (ResultSet) cs.getObject(1)) {
    while (rs.next()) {
        // consume rows
    }
}
```

Close the ResultSet and CallableStatement to release the server cursor.

### 13.7. Procedure overloads and NULL

PL/SQL allows overloading procedures/functions by parameter type. If a client binds NULL without an explicit type, Oracle may fail to pick the intended overload or the driver may report a type mismatch. Call package procedures with explicit signatures, use typed NULLs, or write wrapper procedures with unambiguous contracts.

## 14. Implicit conversion caused by bind data types

### 14.1. NUMBER column bound as VARCHAR

Example:

```sql
SELECT *
FROM orders
WHERE order_id = :p_id;
```

If order_id is NUMBER while the driver binds p_id as VARCHAR, Oracle must resolve the type mismatch. Depending on expression/type precedence, Oracle may convert either the bind or the expression. Inspect Predicate Information to determine the actual conversion.

### 14.2. Binding NUMBER for a VARCHAR2 column

If a column is VARCHAR2 while the application binds NUMBER, Oracle may convert character values or bind with unexpected semantics. Codes with leading zeros like 000123 can lose meaning when converted to numbers.

### 14.3. Binding DATE/TIMESTAMP as text

Date/time strings can depend on NLS_DATE_FORMAT, NLS_TIMESTAMP_FORMAT, NLS_DATE_LANGUAGE, and timezone. Use typed setters or explicit TO_DATE/TO_TIMESTAMP with explicit masks and NLS parameters.

### 14.4. Impact on indexes

If an implicit conversion/function is applied to an indexed column, the predicate may no longer qualify for normal index access. Do not guess from Java setters alone; inspect the actual cursor plan and Predicate Information.

### 14.5. Impact on partition pruning

If the partition key is wrapped in a function or conversion, partition pruning may degrade. Bind the exact type of the partition key and use range predicates matching its data type.

### 14.6. ORA-01722 and ORA-01861

- ORA-01722: invalid number, can occur when a character bind/value is converted to NUMBER with an invalid value.
- ORA-01861: literal does not match format string, can occur when text date/time does not match the format mask.

Fix the bind type and input contract; do not catch the error and retry the same invalid value.

### 14.7. Reading the execution plan

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PEEKED_BINDS +PREDICATE'
    )
);
```

PEEKED_BINDS only shows bind values/types peeked/captured by the optimizer subject to conditions and privileges; not every execution/bind is guaranteed to appear. Exercise caution when outputs contain sensitive values.

## 15. Bind metadata, cursor sharing, and child cursors

### 15.1. Bind data type is part of cursor semantics

Identical SQL text with different bind metadata can cause Oracle to create a different child cursor or fail to share cursors in some cases. Differences in data type, length, precision/scale, and optimizer environment can affect cursor compatibility.

### 15.2. Bind peeking

Oracle may peek bind values at parse time to estimate cardinality/plans. Bind data types also influence how predicates are interpreted. Adaptive Cursor Sharing can create multiple child cursors for varying selectivity; it does not fix an application binding the wrong type.

### 15.3. Checking child cursors

```sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    parse_calls,
    is_bind_sensitive,
    is_bind_aware
FROM v$sql
WHERE sql_text LIKE '%FROM orders%'
ORDER BY sql_id, child_number;
```

Searching SQL_TEXT is just an example; you can search by a known SQL_ID. Query V$SQL_SHARED_CURSOR to find why child cursors are not shared per release.

### 15.4. V$SQL_SHARED_CURSOR

This view provides reason flags explaining why child cursors are not shared. Columns and reasons can differ by release; inspect columns related to bind mismatch/optimizer mismatch when investigating.

### 15.5. Parameter metadata

PreparedStatement.getParameterMetaData can provide parameter info depending on the driver. Do not rely completely on the driver inferring every parameter type before binding, especially with NULLs, expressions, or PL/SQL calls. Applications should know the schema/procedure contract and bind explicitly.
