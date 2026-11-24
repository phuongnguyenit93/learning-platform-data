# SqlParameterValue and Declaring java.sql.Types in Spring JDBC

## 1. Goal and Problem to Solve

When executing SQL via `JdbcTemplate`, developers often pass only Java values:

```java
jdbc.update(
    "INSERT INTO customer_notes(customer_id, note) VALUES (?, ?)",
    customerId,
    note
);
```

In most cases, Spring and the JDBC driver can infer how to bind `Long`, `String`, `BigDecimal`, or `Boolean`. However, with **`null`, vendor-specific SQL types, scaled decimals, or drivers with custom casting rules**, the Java value does not always provide enough information. That is when you declare the **JDBC SQL type** using `java.sql.Types` and use `org.springframework.jdbc.core.SqlParameterValue`.

Lesson contents:
- Distinguish **Java types**, **JDBC `Types` codes**, and **database column data types**.
- Understand accurately how `SqlParameterValue` stores `value`, `sqlType`, `scale`, or `typeName`, and how to pass it to `JdbcTemplate`.
- Safely bind `null` values with explicit types instead of guessing types from Java null.
- Compare 3 ways to declare SQL types: `SqlParameterValue`, `int[] argTypes` array, and `MapSqlParameterSource`/`BeanPropertySqlParameterSource`.
- Apply to DECIMAL/NUMERIC numbers, strings, integers, dates/times, and special types.
- Recognize limitations: declaring an SQL type **does not make NULL behave like a normal value**, does not turn a wrong query into a right one, does not replace constraints, and does not guarantee every driver supports the same types.
- Write and test a Java 17+, Spring Boot, H2 program with verifiable output.

Context: **Spring Framework 6.x, `spring-jdbc`, blocking JDBC, Java 17+**. The content focuses on **SQL input parameters** of `JdbcTemplate`/`NamedParameterJdbcTemplate`, not `OUT` parameters in stored procedures.

## 2. Three Layers of Concepts Easily Confused

### 2.1. Java Type Is the Type of the Object in the Application

`String`, `Long`, `Integer`, `BigDecimal`, `LocalDate`, `java.sql.Date`, `Boolean`... define values on the Java side. When a Java variable is `null`, the object itself **no longer carries runtime information about the type to bind**.

Example:

```java
String nickname = null;
java.math.BigDecimal price = new java.math.BigDecimal("19.90");
```

`nickname` has static type `String` in Java, yet a varargs overload accepting `Object...` may receive only a null reference at runtime; Spring/the driver cannot always guarantee it is SQL `VARCHAR` from null alone.

### 2.2. java.sql.Types Are Standard JDBC Type Codes

`java.sql.Types` contains **`int` constants** indicating general SQL/JDBC data types:

| JDBC Code | General Meaning | Common SQL Column Examples |
|---|---|---|
| `Types.VARCHAR` | Variable-length character string | `VARCHAR(100)` |
| `Types.CHAR` | Fixed-length string | `CHAR(2)` |
| `Types.NVARCHAR` | International / NCHAR family string | `NVARCHAR(100)` |
| `Types.INTEGER` | Common 32-bit integer | `INTEGER` |
| `Types.BIGINT` | Large integer | `BIGINT` |
| `Types.SMALLINT` | Small integer | `SMALLINT` |
| `Types.DECIMAL` / `Types.NUMERIC` | Exact decimal number | `DECIMAL(12,2)` |
| `Types.REAL` / `Types.DOUBLE` | Floating-point number | `REAL` / `DOUBLE PRECISION` |
| `Types.BOOLEAN` | SQL boolean | `BOOLEAN` |
| `Types.DATE` | Date (without time) | `DATE` |
| `Types.TIME` | Time (without date) | `TIME` |
| `Types.TIMESTAMP` | Date-time without timezone info in this SQL type | `TIMESTAMP` |
| `Types.TIMESTAMP_WITH_TIMEZONE` | Date-time with timezone handling per SQL/JDBC | `TIMESTAMP WITH TIME ZONE` (DB-dependent) |
| `Types.BINARY` / `Types.VARBINARY` | Binary data | `BINARY` / `VARBINARY` |
| `Types.BLOB` / `Types.CLOB` | Large binary/character objects | `BLOB` / `CLOB` |
| `Types.ARRAY` | SQL array | Support depends on DB/driver |
| `Types.OTHER` | DB-specific type / no suitable generic code | UUID, JSONB, enum... depending on DB/driver |
| `Types.NULL` | Generic SQL NULL code | **Not a "nullable column type"** |

`Types.VARCHAR` is just a **constant integer**, not the `String` class. These codes serve as inputs to JDBC methods like `PreparedStatement.setNull(position, Types.VARCHAR)`, and to Spring APIs accepting `sqlType`.

### 2.3. The Database's Actual Type Still Governs Validity

A `DECIMAL(12,2)` column has its own precision/scale and constraints; a PostgreSQL `JSONB` column does not magically become a standard `VARCHAR`. The SQL type code helps **tell the driver your binding intent**, but does not guarantee the database will accept the value or convert it as the developer wishes.

Examples:
- `String "123"` bound as `Types.VARCHAR` does not mean the DB must accept it for an integer column.
- `BigDecimal("123.456")` with `Types.DECIMAL` does not force a `DECIMAL(5,2)` column to retain all 3 decimal digits.
- `Types.OTHER` does not mean "use this for anything unfamiliar"; binding JSON/UUID/enum may require `typeName`, vendor-specific objects, or SQL casts per driver.

**Proper design:** read the schema and actual JDBC driver docs; use `Types` matching the SQL parameter, then verify on the target database.

## 3. What Is SqlParameterValue?

The class `org.springframework.jdbc.core.SqlParameterValue` **extends `SqlParameter`**. It represents **a concrete input parameter value** together with declared SQL type information. Spring documents it for use in `JdbcTemplate` operations accepting **plain parameter value arrays** (including varargs overloads).

Common constructors in Spring Framework 6.x:

```java
new SqlParameterValue(int sqlType, Object value);

new SqlParameterValue(int sqlType, int scale, Object value);

new SqlParameterValue(int sqlType, String typeName, Object value);

new SqlParameterValue(SqlParameter declaredParam, Object value);
```

The signatures above are illustrative; in real Java code, there are **no** parameter types like `int sqlType` inside a `new` expression. Each constructor takes the corresponding value/info. A `SqlParameterValue` exposes:
- `getSqlType()` — JDBC SQL type code (inherited from `SqlParameter`).
- `getScale()` — declared scale if present (especially for DECIMAL/NUMERIC).
- `getTypeName()` — optional DB-specific type name if present.
- `getValue()` — actual value, which may be Java `null`.

Valid examples:

```java
import java.math.BigDecimal;
import java.sql.Types;
import org.springframework.jdbc.core.SqlParameterValue;

SqlParameterValue note =
    new SqlParameterValue(Types.VARCHAR, null);

SqlParameterValue customerId =
    new SqlParameterValue(Types.BIGINT, 42L);

SqlParameterValue amount =
    new SqlParameterValue(
        Types.DECIMAL, 2, new BigDecimal("19.90"));
```

**Meaning:** `note` says "bind a VARCHAR-typed SQL parameter with value NULL." It is neither "a NULL value whose Java type is String" nor a declaration of a new column. When used with the right `JdbcTemplate` overload, Spring reads the type info from the wrapper to configure the `PreparedStatement` accordingly.

### Choosing the Right Place to Use It

`SqlParameterValue` is typically passed **at a parameter's position** in a value list:
- `jdbc.update(sql, new SqlParameterValue(...), otherValue)`.
- `jdbc.query(sql, rowMapper, new SqlParameterValue(...))`.
- `jdbc.queryForObject(sql, Long.class, new SqlParameterValue(...))` when the overload supports varargs arguments.
- Inside `Object[]` parameter values used with the overloads above.

It is **not** a query result DTO, not a `RowMapper`, not a schema creation directive, and **does not execute SQL by itself**. You need `JdbcTemplate`/an SQL binding API to pass the type info to the JDBC driver.

## 4. When Do You Truly Need to Declare an SQL Type?

In ordinary applications, Spring usually infers the SQL type from the Java value and the driver's binding mechanism. There is no need to mechanically wrap every `String`/`Long`.

Explicit declaration is useful when:
1. **Nullable values:** `note = null` and the driver needs to know the column/parameter is `VARCHAR`, `DATE`, `DECIMAL`, etc.
2. **DECIMAL/NUMERIC numbers needing scale:** storing currency/exact quantities where scale should be stated explicitly per contract.
3. **Drivers that fail to infer certain types:** a Java value has multiple possible SQL mappings.
4. **Queries with expressions or typed function parameters:** the driver needs the type even when the SQL lacks sufficient context.
5. **Cross-driver/cross-database portability:** one database/driver accepts untyped null while another fails, or type mapping affects the execution plan. Real testing is required, not guesswork.
6. **Clearer contracts in repositories:** parameters updating multiple nullable columns carry target types, making code easier to review and maintain.

**Unnecessary** when a value and schema are clear, the driver handles it reliably, and adding wrappers only makes code verbose. The goal is **right types where needed**, not "as many `Types` as possible."

## 5. Passing SqlParameterValue Directly to JdbcTemplate

Suppose the schema is:

```sql
CREATE TABLE catalog_products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    note VARCHAR(200),
    price DECIMAL(12,2) NOT NULL,
    active BOOLEAN NOT NULL,
    published_on DATE
);
```

`note` and `published_on` allow NULL. With JDBC, the INSERT statement uses six `?` markers, corresponding to six parameters from left to right:

```java
// Method inside a Spring class that already has field JdbcTemplate jdbc.
public int addProduct(long id, String sku,
        String note, BigDecimal price,
        boolean active, LocalDate publishedOn) {

    return jdbc.update("""
            INSERT INTO catalog_products
                (id, sku, note, price, active, published_on)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
        new SqlParameterValue(Types.BIGINT, id),
        new SqlParameterValue(Types.VARCHAR, sku),
        new SqlParameterValue(Types.VARCHAR, note),
        new SqlParameterValue(Types.DECIMAL, 2, price),
        new SqlParameterValue(Types.BOOLEAN, active),
        new SqlParameterValue(Types.DATE,
            publishedOn == null
                ? null
                : java.sql.Date.valueOf(publishedOn))
    );
}
```

This snippet illustrates **a method inside a class that imports** `BigDecimal`, `LocalDate`, `Types`, and `SqlParameterValue`, along with a `jdbc` field. It is not a standalone Java file.

**Position notes:**
- `id` is parameter 1, `sku` is 2, `note` is 3, `price` is 4, `active` is 5, `published_on` is 6.
- Every `SqlParameterValue` preserves the chosen JDBC type; Spring unwraps the content when binding the statement.
- `publishedOn == null` is still bound with `Types.DATE` via the wrapper, avoiding type ambiguity when no date is present.
- `Types.DECIMAL, 2` declares scale 2, yet **does not automatically ensure** `price` has a valid scale or is non-negative. Validate inputs, add schema `CHECK` constraints if business rules require them, and test rounding/overflow.
- `jdbc.update(...)` returns the affected row count, not an object/row from a query. If a unique constraint is violated, Spring may throw `DataIntegrityViolationException` or a related subtype rather than returning 0.

To pass `null` into SQL, **never write** `'null'` as a string or concatenate the word NULL via SQL string assembly. Always use a `?` placeholder with a typed parameter.

## 6. Binding Typed SQL NULL: The Most Important Use Case

Standard JDBC supports:

```java
preparedStatement.setNull(3, Types.VARCHAR);
```

At position 3, the driver knows the parameter has SQL type VARCHAR even without a concrete Java object. `SqlParameterValue` lets you pass that intent to `JdbcTemplate` without writing a `PreparedStatementSetter` for every command:

```java
jdbc.update("""
        UPDATE catalog_products
        SET note = ?
        WHERE id = ?
        """,
    new SqlParameterValue(Types.VARCHAR, null),
    new SqlParameterValue(Types.BIGINT, 42L));
```

Depending on the driver, omitting the type for null **may still work**, but do not rely on one driver succeeding to claim every driver accepts it. The Spring JDBC documentation section on **Providing SQL Type Information for Parameters** notes that declaring the type is sometimes necessary to set `NULL` properly.

### Things Not to Confuse

- `new SqlParameterValue(Types.VARCHAR, null)`: SQL parameter carrying NULL, **intended type is VARCHAR**.
- `new SqlParameterValue(Types.NULL, null)`: only signals a generic SQL NULL type, **does not express the target column type**. If the column is VARCHAR, usually choose `Types.VARCHAR` rather than preferring `Types.NULL`.
- `new SqlParameterValue(Types.VARCHAR, "null")`: the **four-letter string** n-u-l-l; not SQL NULL.
- `new SqlParameterValue(Types.INTEGER, 0)`: the numeric value 0; **not equivalent** to SQL NULL.
- `Optional.empty()` does not automatically translate to JDBC NULL across every overload. Pass Java null with a type and define clear mapping at the boundary.
- If a database column is `NOT NULL`, a typed NULL still **violates the constraint**. Declaring a type does not make NULL allowed.

## 7. Typed NULL Is Completely Different from WHERE = NULL

This is a business-logic bug easily masked when first adopting typed parameters.

Suppose the `note` column has a row with SQL NULL:

```sql
SELECT id
FROM catalog_products
WHERE note = ?;
```

Even if you bind:

```java
new SqlParameterValue(Types.VARCHAR, null)
```

`note = NULL` in SQL **does not return TRUE**, instead evaluating to UNKNOWN under SQL three-valued logic. Therefore filtering with `= ?` and a null parameter **will not find rows with a NULL note** as beginners often assume.

To find NULL rows:

```sql
SELECT id FROM catalog_products WHERE note IS NULL;
```

If a filter can be null and business rules state "null means filter for rows where note is SQL NULL," separate the SQL statements or use a null-safe comparison expression appropriate to the **dialect** (for example, PostgreSQL has `IS NOT DISTINCT FROM`). Do not blindly apply vendor-specific syntax across all DBs.

**Distinguish three meanings when updating a nullable field:**
1. Sending a new non-null value → write that value.
2. Sending **typed null** → set the column to SQL NULL.
3. Wanting to leave the field unchanged → **omit the field from SET**, or use an explicit patch contract; **do not** treat "null input" as both "clear column" and "skip update" unless the API defines it precisely.

With HTTP PATCH or message events, services need a type representing three states—absent/null/value; `Optional<T>` alone is sometimes insufficient to separate absent from present-null.

## 8. Scale with DECIMAL/NUMERIC and BigDecimal

Constructor:

```java
new SqlParameterValue(
    Types.DECIMAL,
    2,
    new java.math.BigDecimal("19.90"));
```

registers SQL type DECIMAL and scale 2. Scale is the **number of digits after the decimal point**. For `DECIMAL(p,s)`, `p` is the maximum total significant digits and `s` is the maximum fractional digits; actual limits/adjustments depend on the SQL dialect and schema.

| Value / Target Type | Assessment |
|---|---|
| `BigDecimal("19.90")`, `DECIMAL(12,2)` | Fits 2-decimal-place currency units |
| `BigDecimal("19.999")`, `DECIMAL(12,2)` | May be rounded or rejected depending on DB/driver/config; must test and define a policy |
| `double 19.90` as money | Avoid because binary representation can lack exactness |
| `new SqlParameterValue(Types.DECIMAL, 2, amount)` | Declares metadata; **not** a validator that checks currency rules |
| `BigDecimal#setScale(2, RoundingMode.UNNECESSARY)` | Rejects values not exactly representable at scale=2; suitable if business rules disallow automatic rounding |

A Java 17 utility illustrating pre-bind validation:

```java
// Standalone method inside a class with BigDecimal and RoundingMode imported.
static BigDecimal money(BigDecimal value) {
    if (value == null || value.signum() < 0) {
        throw new IllegalArgumentException("Price must be nonnegative");
    }
    return value.setScale(2, java.math.RoundingMode.UNNECESSARY);
}
```

If business rules **allow rounding**, explicitly specify `RoundingMode.HALF_UP`/`HALF_EVEN` or the appropriate rule rather than letting the driver/database silently decide. For large numbers, also consider overflow and column precision.

`SqlParameterValue` does not replace `BigDecimal`. It describes **how to bind**, whereas `BigDecimal` holds the **exact value** in Java.

## 9. Another Approach: Passing `int[] argTypes` Alongside `Object[] args`

Spring JDBC supports overloads that let you supply explicit SQL types **in parallel** with values.

Example:

```java
Object[] args = {
    42L,
    null,
    new BigDecimal("19.90")
};

int[] argTypes = {
    Types.BIGINT,
    Types.VARCHAR,
    Types.DECIMAL
};

int changed = jdbc.update("""
        UPDATE catalog_products
        SET note = ?, price = ?
        WHERE id = ?
        """,
    new Object[] {
        null,
        new BigDecimal("19.90"),
        42L
    },
    new int[] {
        Types.VARCHAR,
        Types.DECIMAL,
        Types.BIGINT
    });
```

Here the first `args` array only illustrates three value types and their matching types; **the actual UPDATE statement** uses new arrays in the exact SQL order: `note`, `price`, `id`. When using a type array, the element count must match the `?` count and each type's index must match the argument at the same index.

Concise practical pattern:

```java
int affected = jdbc.update(
    "UPDATE catalog_products SET note = ? WHERE id = ?",
    new Object[]{null, 42L},
    new int[]{Types.VARCHAR, Types.BIGINT});
```

**Comparison:**

```java
// A: metadata sits next to each value (only two parameters need typing):
jdbc.update("UPDATE catalog_products SET note = ? WHERE id = ?",
    new SqlParameterValue(Types.VARCHAR, null),
    42L);

// B: metadata sits in a parallel array (every position has an SQL type):
jdbc.update("UPDATE catalog_products SET note = ? WHERE id = ?",
    new Object[]{null, 42L},
    new int[]{Types.VARCHAR, Types.BIGINT});
```

Both express equivalent semantics when used with the right overload. **Do not both wrap every argument in `SqlParameterValue` and also pass an `argTypes` array**: Spring documentation describes the wrapper for overloads taking a "plain" value array, not to combine with the type-array variant and create confusing precedence rules.

**Which to choose?** `SqlParameterValue` is useful when only a couple of special parameters need declaration; `argTypes` can fit generic adapters holding value–type pairs for every position. When queries are long and order is easy to mix up, named parameters are usually easier to read.

## 10. Named Parameters: MapSqlParameterSource

With `NamedParameterJdbcTemplate`, SQL uses `:name` instead of `?`. `MapSqlParameterSource.addValue` accepts a dedicated SQL type for each name:

```java
// Method inside a class with NamedParameterJdbcTemplate namedJdbc.
public int clearNote(long productId) {
    var params = new MapSqlParameterSource()
        .addValue("note", null, Types.VARCHAR)
        .addValue("id", productId, Types.BIGINT);

    return namedJdbc.update("""
            UPDATE catalog_products
            SET note = :note
            WHERE id = :id
            """, params);
}
```

Benefits:
- Names `note`/`id` avoid remembering positions in long SQL statements.
- Typed null is registered directly on the corresponding named parameter.
- A named parameter repeated in an SQL statement still uses the same value and type definition.
- No manual SQL literal concatenation or escaping.

`MapSqlParameterSource` has an overload `addValue(name, value, sqlType, typeName)` when the SQL type needs a detailed type name. This differs from the constructor `SqlParameterValue(sqlType, typeName, value)`; **do not swap parameter order**.

### Using BeanPropertySqlParameterSource When Reading Properties from an Object

`BeanPropertySqlParameterSource` can read JavaBean/record properties and lets you register SQL types when needed:

```java
// Sketch inside a service/repository that already has input object and namedJdbc.
BeanPropertySqlParameterSource source =
    new BeanPropertySqlParameterSource(input);
source.registerSqlType("note", Types.VARCHAR);
source.registerSqlType("id", Types.BIGINT);

namedJdbc.update("""
    UPDATE catalog_products
    SET note = :note
    WHERE id = :id
    """, source);
```

`input` must have accessible `note` and `id` properties. This is a **project snippet**, not a standalone Java class. If the object lacks a matching property name, registering an SQL type does not supply a value for that property. Test actual mapping instead of assuming.

**Do not confuse `Map.of("note", null)` with a nullable named parameter source:** Java `Map.of` **does not accept null values**. Use `MapSqlParameterSource` or a regular `HashMap` and declare the SQL type.

## 11. SqlParameterValue vs. SqlParameter and OUT Types

`SqlParameter` describes an **SQL parameter metadata declaration**, such as name, sqlType, scale, and typeName; `SqlParameterValue` adds the **concrete value**. Example:

```java
import java.sql.Types;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.SqlParameterValue;

SqlParameter declared = new SqlParameter(Types.DECIMAL);
SqlParameterValue value = new SqlParameterValue(
    declared, new java.math.BigDecimal("15.25"));
```

`SqlParameterValue` represents an input value. For stored procedures and callable statements, Spring also has `SqlOutParameter`, `SqlInOutParameter`, `SimpleJdbcCall`, etc.; do not use a `SqlParameterValue` object to replace the entire OUT parameter declaration and reading mechanism.

Spring docs state that `SqlParameterValue` is intended for operations accepting **plain argument arrays**. When using `PreparedStatementCreatorFactory` or stored procedures, follow the specific **API/metadata contract** of that component; do not assume they all take parameters the exact same way.

## 12. java.sql.Types Is Binding Info, Not a Schema Validator

Common misconceptions when beginners see `Types` names:
- `Types.VARCHAR` **does not squeeze** a 500-character string into a `VARCHAR(50)` column. The database may reject it.
- `Types.INTEGER` **does not safely convert** a Java `Long` of 9,000,000,000 into a 32-bit int. Overflow or a driver exception can occur.
- `Types.DECIMAL` **does not enforce** the column's scale/precision without input validation.
- `Types.DATE` does not solve timezones or convert arbitrary date/time formats. Choose `LocalDate`/`java.sql.Date` properly and test the driver.
- `Types.TIMESTAMP_WITH_TIMEZONE` does not mean every DB stores the original timezone the same way; for example, PostgreSQL normalizes the instant and does not retain the supplied timezone name.
- `Types.OTHER` does not mean any arbitrary object gets serialized; JSON/UUID may require driver-specific objects or `CAST`.
- `Types.NULL` is not the right code to describe every nullable column; choose the **actual** parameter type code.

**Protect your data:** validate in the service and use `NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY`, and real datatypes in the DB. JDBC type declarations only help **communicate accurately with the driver**.

## 13. Special Driver/Database Cases

### 13.1. UUID

Some drivers map `java.util.UUID` to a native DB UUID type; some use `Types.OTHER`, while others require strings/casts or support `setObject` with a target SQL type. Do not default to `new SqlParameterValue(Types.VARCHAR, UUID)` as portable.

PostgreSQL example with a `uuid` datatype:

```sql
SELECT id FROM customers WHERE external_id = CAST(? AS uuid);
```

Java binding must be verified against pgjdbc and the argument type. An explicit SQL cast can clarify type in some queries, yet **does not** replace validating the input UUID.

### 13.2. JSON/JSONB or Enum

A PostgreSQL `jsonb` column is a specialized type, not a generic `VARCHAR`. If required by the driver, you can use a vendor-specific object with `Types.OTHER`/typeName or cast `?::jsonb` per the official driver documentation. **Do not** promise that this pattern works identically on H2, MySQL, and PostgreSQL.

### 13.3. Arrays and LOBs

- `Types.ARRAY` describes an SQL array, yet JDBC `java.sql.Array` has its own lifecycle, often requiring `Connection.createArrayOf` and proper release per contract. Do not simply pass `List<String>` assuming every driver understands it.
- `Types.BLOB`, `CLOB`, and large streams need `LobHandler`/`LobCreator` or appropriate JDBC APIs with memory and lifecycle bounds; a typed parameter does not manage the full stream lifecycle.
- With `TIMESTAMP` and `TIMESTAMP_WITH_TIMEZONE`, date-time strings from APIs must be parsed/validated at the boundary; avoid sending raw strings expecting the DB to guess the timezone.

**Portability rule:** `java.sql.Types` provides standard names, but specific API support, object conversion, and NULL handling remain driver-dependent. Write integration tests against the **same DB engine** used in production whenever specialized types are involved.

## 14. Runnable Spring Boot + H2 + Java 17 Example

The complete example below demonstrates all three ways: `SqlParameterValue`, `int[] argTypes`, and `MapSqlParameterSource`. H2 is an embedded DB for learning. For production PostgreSQL/MySQL/Oracle, swap driver/schema configuration and re-verify with integration tests.

### 14.1. Creating the Project

```text
sql-typed-params-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jdbc/SqlTypedParamsDemoApplication.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

`settings.gradle`:

```groovy
rootProject.name = 'sql-typed-params-demo'
```

`build.gradle` — Java 17, Spring Boot 3.3.5:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:typedparamsdemo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE catalog_products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    note VARCHAR(200),
    price DECIMAL(12,2) NOT NULL,
    active BOOLEAN NOT NULL,
    published_on DATE
);
```

`src/main/java/example/jdbc/SqlTypedParamsDemoApplication.java`:

```java
package example.jdbc;

import java.math.BigDecimal;
import java.sql.Date;
import java.sql.Types;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlParameterValue;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@SpringBootApplication
public class SqlTypedParamsDemoApplication {

    private static final String INSERT = """
        INSERT INTO catalog_products
            (id, sku, note, price, active, published_on)
        VALUES (?, ?, ?, ?, ?, ?)
        """;

    public static void main(String[] args) {
        SpringApplication.run(SqlTypedParamsDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner runDemo(
            JdbcTemplate jdbc, NamedParameterJdbcTemplate namedJdbc) {
        return args -> {
            // A: Wrapper containing sqlType/scale and a VARCHAR NULL.
            jdbc.update(INSERT,
                new SqlParameterValue(Types.BIGINT, 1L),
                new SqlParameterValue(Types.VARCHAR, "BOOK-1"),
                new SqlParameterValue(Types.VARCHAR, null),
                new SqlParameterValue(
                    Types.DECIMAL, 2, new BigDecimal("19.90")),
                new SqlParameterValue(Types.BOOLEAN, true),
                new SqlParameterValue(
                    Types.DATE, Date.valueOf("2026-10-30"))
            );

            // B: Parallel values array and JDBC type array.
            jdbc.update(INSERT,
                new Object[] {
                    2L,
                    "BOOK-2",
                    "second",
                    new BigDecimal("39.00"),
                    true,
                    Date.valueOf("2026-10-31")
                },
                new int[] {
                    Types.BIGINT,
                    Types.VARCHAR,
                    Types.VARCHAR,
                    Types.DECIMAL,
                    Types.BOOLEAN,
                    Types.DATE
                }
            );

            Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM catalog_products",
                Long.class);
            System.out.println("products=" + count);

            String firstNote = jdbc.queryForObject(
                "SELECT note FROM catalog_products WHERE id = ?",
                String.class,
                new SqlParameterValue(Types.BIGINT, 1L));
            System.out.println(
                "firstNoteNull=" + (firstNote == null));

            BigDecimal price = jdbc.queryForObject(
                "SELECT price FROM catalog_products WHERE id = ?",
                BigDecimal.class,
                new SqlParameterValue(Types.BIGINT, 1L));
            System.out.println(
                "firstPrice=" + price.toPlainString());

            // C: Named parameter with type even when value=null.
            MapSqlParameterSource params =
                new MapSqlParameterSource()
                    .addValue("note", null, Types.VARCHAR)
                    .addValue("id", 2L, Types.BIGINT);

            int changed = namedJdbc.update("""
                    UPDATE catalog_products
                    SET note = :note
                    WHERE id = :id
                    """, params);
            System.out.println("updatedRows=" + changed);

            String secondNote = jdbc.queryForObject(
                "SELECT note FROM catalog_products WHERE id = ?",
                String.class,
                2L);
            System.out.println(
                "secondNoteNull=" + (secondNote == null));
        };
    }
}
```

**How to run:** install Java 17 and a Gradle 8.x compatible with the Spring Boot plugin in the example, open a terminal in `sql-typed-params-demo`:

```bash
gradle bootRun
```

If Gradle Wrapper has been generated in the project, you can replace it with `./gradlew bootRun` (Unix/macOS) or `gradlew.bat bootRun` (Windows).

Lines generated by `System.out.println` in exact order, excluding Spring/Gradle startup logs:

```text
products=2
firstNoteNull=true
firstPrice=19.90
updatedRows=1
secondNoteNull=true
```

Why do those values appear?
- Step A inserts `BOOK-1`, with `note` as **VARCHAR-typed** SQL NULL and `price` 19.90 as DECIMAL.
- Step B inserts `BOOK-2` using a values array and 1:1 JDBC type codes; total two rows.
- `SELECT COUNT(*)` returns 2.
- Fetching `note` of row 1 returns Java null because the column holds SQL NULL (not "row not found").
- Reading `price` of row 1 from `DECIMAL(12,2)` yields BigDecimal, representing 19.90.
- Step C uses named parameters to write SQL NULL into `note` of row 2; updates exactly one row.
- Querying `note` of row 2 returns null after the UPDATE.

**Demo limitations:** H2 only proves behavior in one specific environment; do not claim every JDBC driver infers NULL/DATE/BOOLEAN identically. The code needs the Gradle plugin, dependencies, and H2 to run; **it cannot be compiled with bare `javac`** without Spring jars on the classpath.

## 15. Plain Java 17 Program: Inspecting Types Values and Scale

No database or Spring is needed to run the snippet below. It illustrates that `Types` are `int` constants, while scale control belongs to `BigDecimal`/business logic handling.

Filename: `SqlTypeAndScaleDemo.java`.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Types;

public class SqlTypeAndScaleDemo {

    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("19.90");
        BigDecimal normalized = amount.setScale(
            2, RoundingMode.UNNECESSARY);

        System.out.println("VARCHAR=" + Types.VARCHAR);
        System.out.println("DECIMAL=" + Types.DECIMAL);
        System.out.println("BIGINT=" + Types.BIGINT);
        System.out.println("amount=" + normalized.toPlainString());
        System.out.println("scale=" + normalized.scale());
    }
}
```

Run:

```bash
javac SqlTypeAndScaleDemo.java
java SqlTypeAndScaleDemo
```

Exact stdout per JDBC codes defined in Java 17:

```text
VARCHAR=12
DECIMAL=3
BIGINT=-5
amount=19.90
scale=2
```

This snippet **does not perform SQL binding**, so it does not prove what types a driver supports. It only proves `Types` are standard integer codes and `BigDecimal#setScale` lets you verify a scale policy before writing.

## 16. Testing Binding: What Should Be Tested?

### Minimum Matrix

| Case | Input | Expectation |
|---|---|---|
| Nullable VARCHAR | `SqlParameterValue(Types.VARCHAR, null)` | Column receives SQL NULL when schema permits |
| Non-null String | `Types.VARCHAR, "hello"` | Stores/reads back "hello" |
| Scaled DECIMAL | `Types.DECIMAL, 2, BigDecimal("19.90")` | Stores exact number with schema/driver-matching scale |
| DATE | `Types.DATE, java.sql.Date.valueOf(...)` | Queries/reads back the right date |
| BOOLEAN | `Types.BOOLEAN, true` | Stores/reads back boolean true |
| Parallel argTypes | Each `?` has a value/type in order | Stores in right columns without index mix-up |
| Named parameter typed null | `addValue("note", null, Types.VARCHAR)` | Writes NULL to right column |
| Invalid precision/length | Value exceeding schema constraint | Receives error, not silent truncation/mis-conversion |
| NOT NULL constraint | Bind typed null to a NOT NULL column | Database rejects; typed NULL is not treated as valid |
| `WHERE note = ?` with null | Typed null | **Does not** match rows where note is SQL NULL via `=` |
| `WHERE note IS NULL` | No need to bind null for this comparison | Finds rows with SQL NULL properly |
| DB-specific UUID/JSONB/ARRAY | Driver-specific input | Test against real DB to confirm proper binding |

### JUnit 5 with Spring JDBC

Test example using a real `JdbcTemplate`, H2 schema as in section 14, in a project with `spring-boot-starter-test`:

```groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
```

Test method snippet inside a class with `@JdbcTest`, `@Autowired JdbcTemplate jdbc`, and AssertJ static imports:

```java
@Test
void typedNullIsPersistedAsSqlNull() {
    int inserted = jdbc.update("""
            INSERT INTO catalog_products
                (id, sku, note, price, active, published_on)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
        new SqlParameterValue(Types.BIGINT, 100L),
        new SqlParameterValue(Types.VARCHAR, "T-100"),
        new SqlParameterValue(Types.VARCHAR, null),
        new SqlParameterValue(
            Types.DECIMAL, 2, new BigDecimal("1.20")),
        new SqlParameterValue(Types.BOOLEAN, true),
        new SqlParameterValue(Types.DATE, null));

    assertThat(inserted).isEqualTo(1);

    Long count = jdbc.queryForObject("""
            SELECT COUNT(*) FROM catalog_products
            WHERE id = ? AND note IS NULL
            """, Long.class, 100L);

    assertThat(count).isEqualTo(1L);
}
```

This is an **illustrative test method**; running it requires importing `org.junit.jupiter.api.Test`, `org.assertj.core.api.Assertions.assertThat`, `Types`, `BigDecimal`, `SqlParameterValue`, and an initialized test context/schema/bean. Testing on H2 is insufficient when actually using PostgreSQL/Oracle vendor types; run Testcontainers with the matching driver/dialect.

To verify the SQL type is passed properly, you can spy/mock `PreparedStatement` and verify `setNull(index, sqlType)`/`setObject` calls when needed; however, Spring/drivers can pick different bind APIs depending on versions and JDBC metadata, so integration tests verifying **read-back values from a real DB** remain most important. Avoid writing tests overly coupled to implementation details when the real requirement is accurately persisted data.

## 17. Performance and Safety

### 17.1. Typed Binding Does Not Replace PreparedStatement

`SqlParameterValue` works alongside SQL placeholders, **not by doing manual SQL escaping**. Correct SQL:

```java
jdbc.update(
    "UPDATE catalog_products SET note = ? WHERE id = ?",
    new SqlParameterValue(Types.VARCHAR, userInput),
    new SqlParameterValue(Types.BIGINT, id));
```

Wrong SQL:

```java
// WRONG: SQL injection and broken escaping when concatenating raw input.
String sql = "UPDATE catalog_products SET note = '" +
    userInput + "' WHERE id = " + id;
jdbc.update(sql);
```

Both snippets are inside a method context that already has `jdbc`/`userInput`/`id`, not standalone Java files. SQL type metadata **provides no protection** if the developer drops placeholders and concatenates SQL strings. Table/column names cannot be bound like scalar values; if dynamic SQL is needed, use an identifier allowlist.

### 17.2. Do Not Assume Declaring SQL Types Always Improves Performance

- Type metadata helps some drivers/backends identify the right type, avoiding conversion errors or unexpected execution plans.
- Yet performance benefits depend on schema, indexes, how the database optimizes the SQL statement, the driver, and data distribution.
- Choosing the wrong type (e.g., binding VARCHAR when comparing against an indexed numeric column) can sometimes **increase casts / reduce index utilization**, depending on the optimizer.
- Measure query plans/latency on the real DB; do not "optimize" by wrapping every parameter without measuring.

### 17.3. Do Not Log Sensitive Values

SQL type declarations can be logged for diagnostics, but **values** like tokens, emails, note contents, and account numbers should not be logged in plaintext. When debugging a "type mismatch," log field names and JDBC type codes, correlation ID, and safe SQL operation names; restrict full SQL containing sensitive data.

## 18. Common Mistakes and Fixes

**Mistake 1 — Confusing `Types` with Java classes/types.**

`Types.VARCHAR` is an `int`, not `String.class`. When binding, still provide both the value object and the matching JDBC type code.

**Mistake 2 — Passing `null` and assuming the driver always knows the type.**

`jdbc.update(sql, (Object) null)` may succeed on one DB and fail on another. When the schema/driver needs it, use `new SqlParameterValue(Types.VARCHAR, null)`, an `argTypes` array, or a named SQL type.

**Mistake 3 — Using `Types.NULL` for every nullable field.**

`Types.NULL` is a generic NULL code. If the SQL parameter belongs to a VARCHAR/DECIMAL/DATE column, declare the matching SQL type when needed.

**Mistake 4 — Swapping scale constructor argument order.**

Correct: `new SqlParameterValue(Types.DECIMAL, 2, new BigDecimal("10.20"))`. Scale is the **second parameter** in the three-argument overload `(int sqlType, int scale, Object value)`. Not `new SqlParameterValue(value, Types.DECIMAL)`.

**Mistake 5 — Using a types array in the wrong order.**

`Object[]{note, id}` must pair with `int[]{Types.VARCHAR, Types.BIGINT}` when the SQL is `SET note = ? WHERE id = ?`. A misaligned types array can cause hard-to-spot bugs.

**Mistake 6 — Registering only the type without registering a value.**

`MapSqlParameterSource.registerSqlType("note", Types.VARCHAR)` does not necessarily provide a value for `:note`. With `MapSqlParameterSource`, use `addValue("note", null, Types.VARCHAR)` if you want to bind NULL.

**Mistake 7 — Confusing SQL NULL with the string "null" or number 0.**

They have different meanings. Test with `IS NULL` when needed, not only string comparisons from `ResultSet`.

**Mistake 8 — Using `WHERE col = ?` with typed null and expecting NULL rows back.**

Typed binding does not alter SQL three-valued logic. Write an appropriate `IS NULL`/null-safe predicate.

**Mistake 9 — Treating scale in SqlParameterValue as validation.**

You must check BigDecimal, currency policies, and schema precision/scale before writing; read back data to detect unintended rounding.

**Mistake 10 — Assuming `Types.OTHER` is portable for JSON/UUID.**

Check driver docs, type names/casts, and test on a real DB.

**Mistake 11 — Mixing typed wrappers with the `int[] argTypes` overload without a clear contract.**

Pick one SQL type declaration mechanism matching the overload supported by Spring.

**Mistake 12 — Treating typed null as an ignored value in UPDATE.**

`SET note = ?` with typed null **clears the value to SQL NULL**; it does not mean "keep existing note." Define PATCH semantics separately.

## 19. Checklist Before Merging Repository Code

- [ ] Every SQL `?` placeholder has values in the right order; named params match SQL names.
- [ ] Where types are needed, `java.sql.Types` codes reflect the actual SQL types.
- [ ] Nullable parameters are explicitly bound, e.g., `SqlParameterValue(Types.VARCHAR, null)`.
- [ ] `Types.NULL` is not used as a "column type" in place of VARCHAR/DECIMAL/DATE.
- [ ] Monetary/DECIMAL values use BigDecimal with defined precision/scale/range policies.
- [ ] If passing `Object[] args` and `int[] argTypes`, both have the same length and order as `?`.
- [ ] If using named parameters, typed nulls are registered via `MapSqlParameterSource.addValue(..., sqlType)` or an equivalent SqlParameterSource.
- [ ] `Map.of` is not used for a map containing null values.
- [ ] Java types, JDBC type codes, and database datatypes/constraints are not confused.
- [ ] Binding typed null is not confused with querying NULL data via `WHERE col = NULL`.
- [ ] User input is not concatenated into SQL; PreparedStatement placeholders are used.
- [ ] All special types like UUID/JSONB/ARRAY/LOB are verified with the target driver.
- [ ] Integration tests cover non-null, null, precision/scale, and constraint violations.
- [ ] SQL/driver errors are propagated and handled rather than turned into fake "no data."

## 20. Conclusion

**`SqlParameterValue` encapsulates an input parameter together with its JDBC SQL type and optional metadata**, allowing `JdbcTemplate` to bind values more accurately when automatic inference is insufficient—especially for **SQL NULL** and **DECIMAL/NUMERIC scale**. `java.sql.Types` is a system of **JDBC type codes**, not Java types or data validation rules.

The three core approaches are: **wrapping individual values with `SqlParameterValue`**, **passing parallel `Object[] args` / `int[] argTypes`**, or **declaring typed named parameters with `MapSqlParameterSource`/`SqlParameterSource`**. Choose the most readable approach for your current API, ensure order/types match the schema, keep binding through placeholders, and test against a real driver/database.

Type information **does not replace** SQL semantics, database constraints, or business validation: typed NULL is still NULL, `= NULL` is still not TRUE, numeric scale still needs control, and vendor-specific types still require appropriate binding.

## Official References

- Spring Framework — Providing SQL Type Information for Parameters: https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html
- Spring Framework 6.2 — `SqlParameterValue` API and constructors: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/SqlParameterValue.html
- Spring Framework 6.2 — `JdbcTemplate` API (typed arguments): https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework 6.2 — `MapSqlParameterSource` addValue and sqlType: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html
- Oracle Java SE 17 — Standard JDBC `java.sql.Types` constants: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Types.html
