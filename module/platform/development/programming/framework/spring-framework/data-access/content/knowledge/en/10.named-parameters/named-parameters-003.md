# MapSqlParameterSource and Declaring SQL Types

## 1. Why Do Named Parameters Still Need SQL Type Declarations?

In Spring JDBC, `NamedParameterJdbcTemplate` lets you write `:customerCode`, `:amount`, or `:remark` instead of positional `?` markers. This makes long SQL statements easier to read, reduces confusion when multiple parameters share the same type, and allows reusing the same name.

Example:

~~~sql
INSERT INTO invoices (customer_code, amount, remark)
VALUES (:customerCode, :amount, :remark)
~~~

To supply values by name, you can pass a `Map<String, ?>` or a `SqlParameterSource`. **`MapSqlParameterSource`** is the common `SqlParameterSource` implementation: it holds name → value pairs and can also provide the **JDBC SQL type** and **type name** for each parameter.

Points to distinguish:

- **Parameter name** identifies which Java value attaches to a bind position in the SQL statement.
- **Java value** is the data sent to the database, such as `"C001"`, `new BigDecimal("125.50")`, `LocalDate`, or `null`.
- **SQL type** tells JDBC how to handle a parameter, such as `Types.VARCHAR`, `Types.DECIMAL`, `Types.DATE`, or `Types.BIGINT`.
- **Type name** may be needed for special/vendor-specific types; not every query requires declaring it.
- **Column definition** still lives in database DDL: specifying `Types.DECIMAL` at bind time does **not** create a DECIMAL column or automatically enforce business rules.
- **Validation** is a separate concern: binding the right type does not guarantee a positive price, valid code, or user authorization to access data.

Declaring an SQL type is especially useful when a Java **`null` carries no Java class metadata**, with non-obvious JDBC types, or when a driver/database requires an explicit type. When the value is non-null and the driver infers it well, Spring can usually infer or pick an appropriate setter; there is no need to mechanically declare types for every parameter.

## 2. Where MapSqlParameterSource Fits in Spring JDBC

`NamedParameterJdbcTemplate` is the helper class for named parameters and delegates most JDBC work to the underlying `JdbcTemplate`. `MapSqlParameterSource` does not execute SQL and does not hold a Connection: it is solely a **parameter metadata source** passed to `query`, `queryForObject`, `update`, and `batchUpdate`.

~~~text
Repository/Service
    |
    | SQL:  UPDATE invoices
    |       SET remark = :remark
    |       WHERE id = :id
    |
    | MapSqlParameterSource:
    |   remark -> null, Types.VARCHAR
    |   id     -> 5L, Types.BIGINT
    v
NamedParameterJdbcTemplate
    |
    | parse parameter names and bind values/types
    | equivalent JDBC SQL: UPDATE invoices
    |                      SET remark = ?
    |                      WHERE id = ?
    v
JdbcTemplate -> PreparedStatement -> JDBC driver -> Database
    |
    v
Affected row count / List DTO / query result
~~~

Parameter names improve code readability; they are not sent verbatim to the JDBC PreparedStatement. Spring parses and replaces matching names with JDBC placeholders, then binds values in order. One name may appear multiple times in the same SQL: Spring takes the supplied value and binds it at each corresponding position.

Do not confuse `:id` with the `id` column name. `:id` is a value placeholder; table names, column names, and SQL syntax fragments cannot be replaced by data placeholders. For dynamic identifiers, use only a pre-validated set of allowed names when building SQL.

## 3. Essential API of MapSqlParameterSource

The class belongs to package `org.springframework.jdbc.core.namedparam` and extends `AbstractSqlParameterSource`. Common usage patterns:

~~~java
import java.math.BigDecimal;
import java.sql.Types;
import java.util.Map;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;

// Without declaring SQL types:
MapSqlParameterSource simple = new MapSqlParameterSource()
        .addValue("id", 10L)
        .addValue("status", "NEW");

// Declaring SQL types with java.sql.Types constants:
MapSqlParameterSource explicit = new MapSqlParameterSource()
        .addValue("id", 10L, Types.BIGINT)
        .addValue("amount", new BigDecimal("125.50"), Types.DECIMAL)
        .addValue("remark", null, Types.VARCHAR);

// Initializing from an existing Map:
MapSqlParameterSource fromMap = new MapSqlParameterSource(
        Map.of("id", 10L, "status", "NEW"));

// Can be passed via the interface:
SqlParameterSource source = explicit;
~~~

This is an **API usage snippet inside a method or JShell with required imports**, not a standalone Java file. Note that `Map.of` **forbids null values**; when a typed NULL is needed, use `MapSqlParameterSource.addValue(..., null, sqlType)`.

Method summary:

| API | Meaning |
| --- | --- |
| `new MapSqlParameterSource()` | Creates an empty parameter source. |
| `new MapSqlParameterSource(name, value)` | Creates a source with a single parameter. |
| `new MapSqlParameterSource(map)` | Copies/supplies parameter pairs from a Map (without SQL types, as Map carries no type metadata). |
| `addValue(name, value)` | Adds a value without an explicit SQL type. |
| `addValue(name, value, sqlType)` | Adds a value along with a JDBC SQL type code. |
| `addValue(name, value, sqlType, typeName)` | Adds a value, SQL type code, and specific SQL type name. |
| `addValues(map)` | Adds multiple name/value pairs. |
| `registerSqlType(name, sqlType)` | Registers an SQL type for an existing or future parameter name. |
| `registerTypeName(name, typeName)` | Registers an SQL type name for a parameter when needed. |
| `hasValue(name)` / `getValue(name)` | Checks whether a name exists and retrieves its value. |
| `getSqlType(name)` / `getTypeName(name)` | Retrieves registered SQL type/type name metadata. |
| `getValues()` | Returns a read-only Map view of the values. |

The `addValue` overloads return `MapSqlParameterSource` itself for method chaining. `getValues()` does not promise that the underlying `MapSqlParameterSource` is immutable; typically you should create a fresh parameter source per request/SQL statement instead of sharing and mutating one instance across threads.

### 3.1. Two Equivalent Ways to Declare an SQL Type

~~~java
MapSqlParameterSource a = new MapSqlParameterSource()
        .addValue("remark", null, Types.VARCHAR);

MapSqlParameterSource b = new MapSqlParameterSource()
        .addValue("remark", null);
b.registerSqlType("remark", Types.VARCHAR);
~~~

When passed to `NamedParameterJdbcTemplate`, both sources hold `remark=null` with `Types.VARCHAR` metadata. The first approach is usually shorter and easier to read; the second helps when type-registration logic and value-population logic are separated.

### 3.2. Undeclared Type Does Not Mean Types.NULL

~~~java
MapSqlParameterSource p = new MapSqlParameterSource()
        .addValue("remark", null);

boolean present = p.hasValue("remark");       // true
Object value = p.getValue("remark");          // null
int sqlType = p.getSqlType("remark");
// sqlType == SqlParameterSource.TYPE_UNKNOWN
~~~

This is an illustrative snippet. `hasValue` distinguishes **name declared with null value** from **name not declared**. `SqlParameterSource.TYPE_UNKNOWN` means Spring has not been given an explicit SQL type; it is **not equivalent** to `java.sql.Types.NULL`. When a driver cannot infer the type of null, specifying the exact `Types.VARCHAR`/`Types.INTEGER`/… handles the issue; the choice must match the column type and driver conventions.

## 4. Understanding java.sql.Types and typeName Properly

`addValue(name, value, sqlType)` takes a **JDBC SQL type integer**, usually written using `java.sql.Types` constants. Do not pass `String.class`, `Integer.class`, or an SQL type name string as the `sqlType` parameter.

| Java value / purpose | Typically suitable SQL type | Notes |
| --- | --- | --- |
| `String` for VARCHAR | `Types.VARCHAR` | CHAR/NVARCHAR may have different semantics depending on schema/driver. |
| `Long` for BIGINT | `Types.BIGINT` | Check numeric bounds; do not coerce to the wrong column type. |
| `Integer` for INTEGER | `Types.INTEGER` | Distinguish NULL from 0. |
| `BigDecimal` for DECIMAL | `Types.DECIMAL` or `Types.NUMERIC` | Column must have sufficient precision/scale; does not replace currency validation. |
| `java.sql.Date` for DATE | `Types.DATE` | Use `Date.valueOf(LocalDate)` when an explicit JDBC DATE is needed. |
| `java.sql.Timestamp` for TIMESTAMP | `Types.TIMESTAMP` | Verify timezone/driver and instant semantics. |
| `Boolean` for BOOLEAN | `Types.BOOLEAN` | Support and mapping can differ across databases. |
| `byte[]` for BINARY/VARBINARY | `Types.VARBINARY` (depends on column) | BLOB/streams have separate resource lifecycles. |
| SQL NULL for a VARCHAR column | `null` with `Types.VARCHAR` | Type metadata guides null binding. |
| JSONB, UUID, ARRAY, custom types | Possibly `Types.OTHER`, `Types.ARRAY`, and `typeName` | Vendor/driver-dependent; do not extrapolate from one database to another. |

**Type name** is used when a driver or specialized type requires the exact SQL type name, such as `jsonb` or an ARRAY type name in a specific database:

~~~java
MapSqlParameterSource vendorSpecific =
        new MapSqlParameterSource()
                .addValue("payload", "{\"enabled\":true}",
                        Types.OTHER, "jsonb");
~~~

This is only a **metadata registration syntax illustration**, **not an example runnable on every database**. PostgreSQL JSONB may require `PGobject`, an SQL cast, or driver-specific binding; merely adding `Types.OTHER` and `"jsonb"` **does not guarantee** a String will always be accepted by the driver. Test directly against the target database/driver. For vendor-specific types, understand how the driver invokes `setObject`/`setNull` and uses `typeName` metadata.

Remember the distinction: `typeName` here is the **SQL type name of the parameter**, not the parameter name, column name, or Java class name. Do not specify `typeName` "just because" if the driver does not need it.

## 5. Typed NULL: The Most Important Use Case

When passing `null`, Java has no runtime value class to hint at the SQL type. Some drivers/JDBC paths handle untyped nulls, while in other SQL statements or drivers type resolution is ambiguous or fails. Supplying the SQL type in `MapSqlParameterSource` makes the intent explicit:

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
        .addValue("id", 5L, Types.BIGINT)
        .addValue("remark", null, Types.VARCHAR);

int updated = namedJdbc.update(
        "UPDATE invoices SET remark = :remark WHERE id = :id",
        params);
~~~

This snippet belongs in a repository with a `NamedParameterJdbcTemplate namedJdbc` field. Both parameters are bound with their matching JDBC types. If `remark` is a nullable VARCHAR column, updating `remark` to SQL NULL is valid. If the column is NOT NULL, the database still rejects it. SQL type metadata **does not bypass** NOT NULL/CHECK/FK constraints.

**NULL is not the same as an empty string or a default value.** In SQL, equality comparison with NULL does not follow ordinary arithmetic rules:

~~~sql
-- Do not use this expression to find rows where remark IS NULL:
SELECT id FROM invoices WHERE remark = :remark;

-- Correct when looking for rows where remark is currently NULL:
SELECT id FROM invoices WHERE remark IS NULL;
~~~

If `:remark` is bound as NULL, `remark = NULL` evaluates to UNKNOWN under SQL three-valued logic and will not match rows as expected. This is an **SQL semantics** issue, not solved by merely declaring `Types.VARCHAR`.

### 5.1. When Should You Declare Types?

- The value is null and the driver cannot determine it or requires an explicit type.
- The driver needs `setNull` with the exact column/custom type.
- Data is passed via an overly broad Java type (such as `Object`) and you do not want inconsistent driver choices.
- A batch contains rows where the same parameter is null in some rows and non-null in others.
- Specialized types such as SQL ARRAY, STRUCT, JSONB, or UUID require a clear driver contract.

It is unnecessary to add SQL types for every known String/Long/BigDecimal parameter. Declare types selectively when it clarifies the contract or is required. Declaring the **wrong** type can break conversion, lose precision, or produce harder-to-diagnose errors than letting Spring infer it.

## 6. Runnable Example: NamedParameterJdbcTemplate + MapSqlParameterSource + H2

Let us build a Spring Boot console application storing invoices in H2. The repository uses typed SQL parameters for `BIGINT`, `VARCHAR`, `DECIMAL`, and `DATE`, including `remark = null`. The app also runs an `IN (:statuses)` query to show how named-parameter collections are handled.

Demo prerequisites:

- Java 21, a Java 21–compatible Gradle version (e.g., Gradle 8.5).
- Spring Boot 3.3.5 and Spring JDBC starter, in-memory H2.
- No external database server or HTTP layer needed.
- The table is freshly created on each run in an isolated process.
- Input data is fixed so output stays deterministic.

### 6.1. Project Structure

~~~text
named-sql-types-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/namedsql/
    │   ├── NamedSqlApplication.java
    │   ├── InvoiceView.java
    │   ├── InvoiceRepository.java
    │   └── InvoiceService.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'named-sql-types-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

File `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:namedsqldemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
logging.level.root=ERROR
~~~

File `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE invoices (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_code VARCHAR(20) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    issue_date DATE NOT NULL,
    remark VARCHAR(200),
    status VARCHAR(16) NOT NULL
);
~~~

Here the SQL type of each **column** is defined by the schema. `MapSqlParameterSource` will declare the corresponding **types of bound values**. The `remark` column allows SQL NULL; `amount` does not.

### 6.2. Result Model

File `src/main/java/example/namedsql/InvoiceView.java`:

~~~java
package example.namedsql;

import java.math.BigDecimal;
import java.time.LocalDate;

public record InvoiceView(
        long id,
        String customerCode,
        BigDecimal amount,
        LocalDate issueDate,
        String remark,
        String status) {
}
~~~

The record holds already-read Java values: primitive `long`, `String`, `BigDecimal`, and `LocalDate`. Callers can use it after the query finishes without holding onto `ResultSet`/`Connection`.

### 6.3. Repository: Typed Parameters and Generated Keys

File `src/main/java/example/namedsql/InvoiceRepository.java`:

~~~java
package example.namedsql;

import java.math.BigDecimal;
import java.sql.Date;
import java.sql.Types;
import java.time.LocalDate;
import java.util.List;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class InvoiceRepository {
    private static final String INSERT_SQL = """
            INSERT INTO invoices
                (customer_code, amount, issue_date, remark, status)
            VALUES
                (:customerCode, :amount, :issueDate, :remark, :status)
            """;

    private final NamedParameterJdbcTemplate namedJdbc;

    public InvoiceRepository(NamedParameterJdbcTemplate namedJdbc) {
        this.namedJdbc = namedJdbc;
    }

    public long insert(
            String customerCode,
            BigDecimal amount,
            LocalDate issueDate,
            String remark,
            String status) {

        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("customerCode", customerCode, Types.VARCHAR)
                .addValue("amount", amount, Types.DECIMAL)
                .addValue("issueDate", Date.valueOf(issueDate), Types.DATE)
                .addValue("remark", remark, Types.VARCHAR)
                .addValue("status", status, Types.VARCHAR);

        KeyHolder keys = new GeneratedKeyHolder();
        int updated = namedJdbc.update(
                INSERT_SQL, params, keys, new String[] {"id"});

        if (updated != 1 || keys.getKey() == null) {
            throw new IllegalStateException(
                    "Failed to insert invoice with generated key");
        }
        return keys.getKey().longValue();
    }

    public int clearRemark(long invoiceId) {
        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("id", invoiceId, Types.BIGINT)
                .addValue("remark", null, Types.VARCHAR);

        return namedJdbc.update(
                "UPDATE invoices SET remark = :remark WHERE id = :id",
                params);
    }

    public List<InvoiceView> findByStatuses(List<String> statuses) {
        if (statuses.isEmpty()) {
            return List.of();
        }

        MapSqlParameterSource params =
                new MapSqlParameterSource()
                        .addValue("statuses", statuses);

        return namedJdbc.query("""
                SELECT id, customer_code, amount, issue_date, remark, status
                FROM invoices
                WHERE status IN (:statuses)
                ORDER BY id
                """,
                params,
                (rs, rowNum) -> new InvoiceView(
                        rs.getLong("id"),
                        rs.getString("customer_code"),
                        rs.getBigDecimal("amount"),
                        rs.getDate("issue_date").toLocalDate(),
                        rs.getString("remark"),
                        rs.getString("status")));
    }
}
~~~

**Key points in the code:**

1. `new MapSqlParameterSource()` is created separately per operation, so mutable parameter state is never shared across requests or threads.
2. `addValue("amount", amount, Types.DECIMAL)` specifies how to bind BigDecimal to the DECIMAL column. It does **not** replace validating that amount is positive or within limits; that belongs to domain logic and database constraints.
3. `Date.valueOf(issueDate)` constructs a JDBC DATE from `LocalDate` so the demo does not depend on the driver auto-converting `LocalDate` to DATE. In real applications, many modern drivers handle `LocalDate` directly; check compatibility.
4. `addValue("remark", remark, Types.VARCHAR)` works whether `remark` is a String or null. The null case is a prime example where declaring the type helps.
5. `KeyHolder` receives the generated key from the JDBC driver. The `update(sql, params, keyHolder, new String[]{"id"})` overload is supported by Spring JDBC; generated key column names can vary by database and identifier quoting. H2 in this demo supports it.
6. `clearRemark` passes the same name/value mechanics to UPDATE while binding null with a concrete SQL type. It returns an `int` row count; the caller must check for 0 rows if business rules require the invoice to exist.
7. `findByStatuses` passes a collection for `:statuses`. `NamedParameterJdbcTemplate` expands the list into the matching number of placeholders for SQL `IN`, rather than turning it into a JDBC `ARRAY` parameter. Therefore, do not declare `Types.ARRAY` for this `List`.
8. Check for an empty list before using `IN (:statuses)`. Do not rely on SQL `IN ()` because syntax/behavior is not portable. The repository defines an empty list as returning an empty result.
9. The `RowMapper` reads columns and builds `InvoiceView`; the `ResultSet` is closed by the template when the query completes. `issue_date` is `NOT NULL` in the schema, so `getDate(...).toLocalDate()` is safe in this demo.

### 6.4. Service Setting the Transaction Boundary

File `src/main/java/example/namedsql/InvoiceService.java`:

~~~java
package example.namedsql;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceService {
    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public List<InvoiceView> createExamples() {
        long first = repository.insert(
                "C001", new BigDecimal("125.50"),
                LocalDate.of(2026, 10, 1), null, "NEW");

        repository.insert(
                "C002", new BigDecimal("80.00"),
                LocalDate.of(2026, 10, 2), "Express delivery", "PAID");

        if (repository.clearRemark(first) != 1) {
            throw new IllegalStateException(
                    "Failed to update remark");
        }

        return repository.findByStatuses(List.of("NEW", "PAID"));
    }
}
~~~

`@Transactional` wraps the insert/update/query operations in the same Spring JDBC transaction because `NamedParameterJdbcTemplate` and the transaction manager share the DataSource configured by Spring Boot. If a qualifying exception escapes the method, Spring rolls back. `MapSqlParameterSource` does not create a transaction itself, it only describes parameters; atomicity belongs to the service and transaction manager.

### 6.5. Runner and Stdout

File `src/main/java/example/namedsql/NamedSqlApplication.java`:

~~~java
package example.namedsql;

import java.sql.JDBCType;
import java.sql.Types;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

@SpringBootApplication
public class NamedSqlApplication {
    public static void main(String[] args) {
        SpringApplication.run(NamedSqlApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(InvoiceService service) {
        return args -> {
            MapSqlParameterSource typedNull =
                    new MapSqlParameterSource()
                            .addValue("remark", null, Types.VARCHAR);

            System.out.println("Remark JDBC type: "
                    + JDBCType.valueOf(
                            typedNull.getSqlType("remark")));

            List<InvoiceView> invoices = service.createExamples();
            System.out.println("Invoice count: " + invoices.size());

            for (InvoiceView row : invoices) {
                System.out.printf(
                        "id=%d | code=%s | amount=%s | date=%s"
                        + " | remark=%s | status=%s%n",
                        row.id(),
                        row.customerCode(),
                        row.amount().toPlainString(),
                        row.issueDate(),
                        row.remark(),
                        row.status());
            }
        };
    }
}
~~~

Run in the `named-sql-types-demo` directory with JDK 21 and a Java 21–compatible Gradle:

~~~bash
gradle bootRun
~~~

The lines **printed by the program** on a fresh H2 database (excluding Gradle output) are:

~~~text
Remark JDBC type: VARCHAR
Invoice count: 2
id=1 | code=C001 | amount=125.50 | date=2026-10-01 | remark=null | status=NEW
id=2 | code=C002 | amount=80.00 | date=2026-10-02 | remark=Express delivery | status=PAID
~~~

Explanation:

- `JDBCType.valueOf(typedNull.getSqlType("remark"))` returns the `JDBCType.VARCHAR` enum from the declared `Types.VARCHAR` code; the first line executes no SQL, it simply inspects metadata inside `MapSqlParameterSource`.
- Both INSERTs use named parameters with explicit SQL types; the first `remark` column is sent as a typed NULL.
- The subsequent UPDATE sets the first `remark` to NULL again to demonstrate `clearRemark`; it remains null on SELECT.
- Both statuses `NEW` and `PAID` are passed as a collection into SQL `IN`; results are ordered by `id`.
- Each DECIMAL value is read by `RowMapper` as `BigDecimal` and printed with `toPlainString`, avoiding float/double precision loss.
- The demo only assumes H2's auto-generated ID starts at 1 in a **fresh process**. On a database with existing data, identity/sequence values do not necessarily start at 1.

## 7. Ways to Declare and Inspect SQL Types

A `MapSqlParameterSource` stores both values and type metadata. You can inspect them to verify bind logic before running a query:

~~~java
MapSqlParameterSource p = new MapSqlParameterSource()
        .addValue("id", 42L, Types.BIGINT)
        .addValue("remark", null, Types.VARCHAR)
        .addValue("amount", new BigDecimal("19.90"), Types.DECIMAL);

System.out.println(p.hasValue("remark"));
System.out.println(p.getValue("remark") == null);
System.out.println(p.getSqlType("remark") == Types.VARCHAR);
System.out.println(p.getSqlType("amount") == Types.DECIMAL);
~~~

This is a Java snippet **inside a method with imports** for `MapSqlParameterSource`, `Types`, and `BigDecimal`; all four printed lines evaluate to `true`. Note: these only verify metadata on the Java side, not that the driver binds properly under every schema or database. Integration tests are needed for actual SQL execution.

### 7.1. registerSqlType and registerTypeName

~~~java
MapSqlParameterSource p = new MapSqlParameterSource()
        .addValue("payload", "{\"name\":\"A\"}");

p.registerSqlType("payload", Types.OTHER);
p.registerTypeName("payload", "jsonb");
~~~

This snippet **only demonstrates metadata registration**; it executes no SQL and does not guarantee that the PostgreSQL driver accepts a String as JSONB. The type name `jsonb` is PostgreSQL-specific; other databases handle JSON/JSONB differently. For real JSONB, check your driver—you may need `PGobject`, an SQL cast, or different binding. Never copy a vendor-specific `typeName` example blindly to H2, MySQL, SQL Server, or Oracle.

### 7.2. One Parameter Source Can Reuse Names

~~~sql
SELECT id
FROM invoices
WHERE status = :status
   OR (:status = 'ALL')
~~~

~~~java
MapSqlParameterSource args =
        new MapSqlParameterSource("status", "NEW");
~~~

Spring binds the same `NEW` value for both occurrences of `:status` in the `PreparedStatement`. This is purely a syntax illustration. With real data queries, design search criteria and indexes appropriately; avoid unnecessary `OR` expressions if they hurt query performance.

### 7.3. Null Data Cannot Be Passed via Map.of

~~~java
// Wrong: Map.of does not allow null values.
Map<String, Object> broken =
        Map.of("remark", null);

// Right: MapSqlParameterSource accepts null values
// and provides the corresponding SQL type.
MapSqlParameterSource ok =
        new MapSqlParameterSource()
                .addValue("remark", null, Types.VARCHAR);
~~~

The first part is an **anti-example**; running it throws `NullPointerException` before SQL is ever sent. `HashMap` can hold `null`, yet a plain `Map<String,Object>` still carries no explicit SQL type metadata; when a driver requires typed nulls, `MapSqlParameterSource` is more suitable.

## 8. Complex Parameter Types and Limitations

### 8.1. IN and Collection Expansion Differ from SQL ARRAY

Spring can expand a Java `Collection` at `IN (:ids)` into the corresponding bind placeholders:

~~~java
List<Long> ids = List.of(10L, 20L, 30L);
MapSqlParameterSource args =
        new MapSqlParameterSource()
                .addValue("ids", ids);

List<Long> result = namedJdbc.query(
        "SELECT id FROM invoices WHERE id IN (:ids)",
        args,
        (rs, rowNum) -> rs.getLong("id"));
~~~

This is an **illustrative snippet in a repository with `NamedParameterJdbcTemplate namedJdbc`**. With three IDs, the resulting SQL has three JDBC placeholders. This is not the same as creating a `java.sql.Array` or binding with `Types.ARRAY`. Avoid empty collections and watch database SQL parameter limits when lists grow very large; batching, temporary tables, or another approach may be needed.

### 8.2. DATE/TIMESTAMP Types and Timezones

`Types.DATE` fits calendar dates without a time component; `LocalDate` can be converted to `java.sql.Date` for a more portable example. `Types.TIMESTAMP` and `Types.TIMESTAMP_WITH_TIMEZONE` are not equivalent. If your domain needs an **absolute instant**, evaluate `Instant`/`OffsetDateTime`, column types, JDBC driver behavior, and UTC/offset conventions; do not claim that merely picking a `Types` constant automatically makes timezones right.

Typed timestamp example:

~~~java
MapSqlParameterSource p = new MapSqlParameterSource()
        .addValue("createdAt",
                java.sql.Timestamp.from(
                        java.time.Instant.parse("2026-10-01T09:00:00Z")),
                Types.TIMESTAMP);
~~~

This is a **parameter construction example**, without connecting to a database. Converting `Instant` to a timezone-less `TIMESTAMP` can depend on driver/timezone settings; test against the real database.

### 8.3. DECIMAL, Precision, and Scale

`Types.DECIMAL` describes how to bind `BigDecimal`, but does not enforce precision or business rounding. If a table uses `DECIMAL(12,2)`, ensure `BigDecimal` follows currency unit and scale policies before writing, and let the database enforce constraints. `new BigDecimal("125.50")` is more accurate than `new BigDecimal(125.50)` when you want the exact decimal string representation. For money, check both currency unit and precision, not just a `Types` constant.

### 8.4. JSON, UUID, ARRAY, BLOB, CLOB

There is no single SQL type that works across all databases for JSON/UUID, arrays, or large objects. Some drivers require vendor-specific objects, type names, or SQL casts. For BLOB/CLOB streams, control when streams are read and closed; never return a Connection-backed `InputStream` outside its scope. Using `Types.OTHER` or `Types.ARRAY` must follow the JDBC driver and target database documentation, not be picked simply out of uncertainty.

## 9. Batch Updates with Typed NULLs

When writing multiple rows, `NamedParameterJdbcTemplate.batchUpdate(sql, SqlParameterSource[])` lets each element carry SQL type metadata. Consider declaring types here when some rows have null parameters.

~~~java
SqlParameterSource[] batch = {
        new MapSqlParameterSource()
                .addValue("customerCode", "C010", Types.VARCHAR)
                .addValue("remark", null, Types.VARCHAR),

        new MapSqlParameterSource()
                .addValue("customerCode", "C011", Types.VARCHAR)
                .addValue("remark", "Call ahead", Types.VARCHAR)
};

int[] affected = namedJdbc.batchUpdate("""
        UPDATE invoices
        SET remark = :remark
        WHERE customer_code = :customerCode
        """,
        batch);
~~~

This is an **illustrative repository snippet** with `NamedParameterJdbcTemplate namedJdbc`, importing `SqlParameterSource`, `MapSqlParameterSource`, and `Types`. The two UPDATE statements may return 0 affected rows if a code is absent from the table; that is valid at the JDBC level, though business logic might reject it if one matching invoice is expected. A batch does not automatically create a transaction for the entire use case; wrap it in `@Transactional` if all items must commit/roll back together using the proper DataSource.

Another way to prepare a batch from beans/Maps is `SqlParameterSourceUtils.createBatch(...)`, but when SQL types must be specified per nullable or vendor parameter, constructing `MapSqlParameterSource` per element is clearer. Never assume all drivers execute batches identically, or that all items commit/roll back together without a transaction.

## 10. MapSqlParameterSource, Map, and BeanPropertySqlParameterSource

| Option | Strengths | Limitations / When to use |
| --- | --- | --- |
| `Map<String, ?>` | Concise for simple, non-null values; accepted directly by many overloads. | Carries no direct SQL type metadata; `Map.of` rejects null. |
| `MapSqlParameterSource` | Named values, typed NULLs, `sqlType`/`typeName`, chained `addValue`, `addValues`. | Mutable; construct fresh per operation; declared types must match schema/driver. |
| `BeanPropertySqlParameterSource` | Reads names/values from matching JavaBean/record properties. | Type metadata inferred from properties when possible; does not replace validation or custom driver mapping. |
| `SqlParameterSourceUtils.createBatch` | Quickly builds batch `SqlParameterSource` arrays from Maps/beans. | For vendor types or typed NULLs, verify actual metadata or use explicit `MapSqlParameterSource`. |

**Practical choice:** a SELECT with two clear String/Long values can use `Map`. A multi-column INSERT with nullable values, DATE/DECIMAL, or special driver needs should consider `MapSqlParameterSource` for explicit declarations. Simple CRUD from a JavaBean can use `BeanPropertySqlParameterSource`. `MapSqlParameterSource` is not automatically better than `Map` or `BeanProperty` in every situation.

## 11. Common Mistakes and How to Prevent Them

| Mistake | Why it is wrong | How to handle |
| --- | --- | --- |
| SQL uses `:customerCode` while source has `customer_code` | Parameter cannot be found by name; throws exception. | Keep SQL parameter names/aliases and source keys consistent. |
| Passing null without SQL type when driver requires a type | Driver may fail to determine the type of null. | Use `addValue(name, null, Types.X)` matching the column. |
| Using `Types.NULL` or `Types.OTHER` for every null | May clash with the column type and be rejected by the driver. | Choose the matching SQL type constant and test with the driver. |
| Confusing `SqlParameterSource.TYPE_UNKNOWN` with `Types.NULL` | One means undeclared; the other is a JDBC type constant. | Understand metadata semantics. |
| Using `Types.ARRAY` for a List in `IN` | `IN`-list expansion is not SQL ARRAY binding. | Pass a regular `Collection` and handle empty lists. |
| Ignoring empty lists | SQL `IN ()` is non-portable and may be a syntax error. | Define explicit behavior for empty lists. |
| Passing `new BigDecimal(0.1)` for money | Can introduce binary floating-point error. | Use decimal strings or a defined factory. |
| Believing `Types.DECIMAL` enforces positive prices | SQL types do not enforce domain rules. | Use Bean Validation/domain rules and DB constraints. |
| Calling `Map.of("x", null)` | Throws `NullPointerException` before calling JDBC. | Use `MapSqlParameterSource` for typed nulls. |
| Replacing tables/columns with `:table`, `:column` | Bind placeholders are only for values, not SQL identifiers. | Whitelist identifiers; never concatenate raw user input. |
| Sharing one mutable `MapSqlParameterSource` across requests | Parameters from another request can overwrite/race. | Create a fresh instance per operation/batch item. |
| Not checking UPDATE row counts | 0 rows may indicate business failure. | Compare affected rows with expectations. |
| Declaring vendor `typeName` without testing | Driver may need a specific object/cast. | Write integration tests directly against the DB/driver. |
| Expecting `MapSqlParameterSource` to manage transactions | It only holds values and metadata. | Use an appropriate transaction manager/`@Transactional`. |
| Assuming typed null makes every NULL query work | SQL NULL uses three-valued comparison logic. | Use `IS NULL` / `IS NOT NULL` when searching for nulls. |

### SQL Security and Input Data

`MapSqlParameterSource` and `PreparedStatement` binding ensure parameters are treated as **data**, not SQL syntax. However, they do not enforce authorization, identifier whitelisting, quantity bounds, negative prices, cross-table invariants, or dynamically constructed SQL logic. Validation and authorization belong in their appropriate layers; database constraints serve as an additional safeguard.

## 12. Testing and Diagnostics

To verify that a repository uses named parameters and type metadata properly:

1. **Local metadata checks:** Verify `hasValue`, `getValue`, `getSqlType`, and `getTypeName` for both null and non-null values; ensure `Types` match the schema.
2. **Integration tests with a real or compatible database:** Execute INSERT, typed-NULL UPDATE, and SELECT with `RowMapper`; verify read-back data and affected rows.
3. **NULL checks:** Nullable columns accept SQL NULL; NOT NULL columns reject it; also test null-lookup queries using `IS NULL` rather than `= :value`.
4. **Precision checks:** `BigDecimal` retains exact scale/precision round-tripping through JDBC without unintended conversion through `double`.
5. **DATE/TIMESTAMP checks:** Dates, instants, and timezones match contracts, especially on drivers other than H2.
6. **IN collection checks:** Lists with 1, many, and 0 items; empty lists follow repository policy.
7. **Invalid input checks:** Wrong parameter names, unexpected nulls, type mismatches, out-of-range values, or DECIMAL precision overflow.
8. **Transaction checks:** Multiple updates in the same service roll back together when an exception occurs, with no raw Connections outside the transaction.
9. **Driver-specific checks:** JSON, ARRAY, UUID, generated keys, and `typeName` tested against the production database, not only H2.
10. **Observability:** Log SQL and bind errors appropriately in test environments; do not leak PII or secrets into logs. Overly verbose driver logging can expose parameter data.

### Self-Check Questions

1. How does `MapSqlParameterSource` differ from `Map<String,Object>` in an important way for typed NULLs?
2. What does `addValue("remark", null, Types.VARCHAR)` declare, and what does it **not** guarantee?
3. Why is `SqlParameterSource.TYPE_UNKNOWN` not synonymous with `Types.NULL`?
4. When should you use `registerSqlType` or the four-argument overload including `typeName`?
5. With `WHERE status IN (:statuses)`, why should you not force `Types.ARRAY` on a regular `List`?
6. Does placing `:tableName` in a table-name position work like data binding? Why or why not?
7. In the demo, how was the `LocalDate` value converted to a JDBC DATE type?
8. If the `remark` column is `NOT NULL`, can a typed NULL write succeed?
9. In a batch where some remarks are null, what does type metadata help with, and where does transaction responsibility live?
10. To send JSONB to PostgreSQL, why might `addValue(..., Types.OTHER, "jsonb")` alone not be enough?

**Conclusion:** `MapSqlParameterSource` is a named-parameter source capable of describing **Java value + JDBC SQL type + SQL type name**. It is especially useful for typed NULLs and cases where the driver requires explicit types. Use it alongside `NamedParameterJdbcTemplate`, pick `Types` constants matching your schema/driver, validate data independently from binding, and place transactions at the service layer; never treat type metadata as a substitute for business contracts or database constraints.

### References

- Spring JDBC: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- MapSqlParameterSource API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html
- AbstractSqlParameterSource API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/AbstractSqlParameterSource.html
- NamedParameterJdbcTemplate API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html
- SqlParameterSource API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/SqlParameterSource.html
- JDBC Types (JDK 21): https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Types.html
