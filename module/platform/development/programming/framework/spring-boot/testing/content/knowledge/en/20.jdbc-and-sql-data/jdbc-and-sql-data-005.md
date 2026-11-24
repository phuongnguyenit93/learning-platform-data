# Testing Row Mapping, Null Values, and Type Conversions in Spring JDBC

## 1. Objectives and Common Pitfalls

In a JDBC-based application, the SELECT statement can be valid and the returned row count can be right, yet the Java object can still carry wrong data. For example, an INTEGER **SQL NULL** column turns into **0**, an unknown BOOLEAN column becomes **false**, a DECIMAL monetary value gets rounded through `double`, or a VARCHAR status code is mapped to the wrong enum. These bugs are dangerous because the code often runs without throwing an exception.

In Spring JDBC, **`RowMapper<T>`** is responsible for converting **the single ResultSet row currently pointed to** into a Java object. **`JdbcTemplate`** prepares the `PreparedStatement`, invokes the JDBC driver, advances the `ResultSet` across rows, and manages the resource lifecycle. Therefore, tests for the row-mapping layer must prove behavior **from SQL data all the way to the Java domain**, not merely that a non-null object was returned.

After this lesson, you will be able to:

- Understand the **`RowMapper.mapRow(ResultSet, rowNum)`** contract, column labels, and `JdbcTemplate`'s scope of responsibility.
- Distinguish **no row** from **a row containing SQL NULL**.
- Understand that **`ResultSet.getInt`/`getBoolean` return `0`/`false` on SQL NULL**, and why **`wasNull()` must be called immediately after the matching getter**.
- Map BIGINT, nullable INTEGER/BOOLEAN, DECIMAL(12,2), DATE, and VARCHAR status codes to Java 17.
- Use **`Integer`/`Boolean`** when preserving the three states NULL, `0`/`FALSE`, and normal values is required.
- Preserve precision with **`BigDecimal`**, check null before converting **`java.sql.Date` → `LocalDate`**, and use **`Locale.ROOT`** when normalizing enums.
- Verify SQL aliases, row counts, `query` vs. `queryForObject`, and invalid data errors.
- Build a Java 17 / Spring Boot **3.3.5** Gradle project using embedded H2 with **`@JdbcTest`, `schema.sql`/`data.sql`, `JdbcTemplate`, and 12 JUnit Jupiter tests**.
- Distinguish JDBC/`SQLException` failures from **`IllegalArgumentException`** thrown by a custom converter.
- Know when H2 tests are enough and when a production JDBC driver via Testcontainers is required.

**Context:** This lesson belongs to JDBC and SQL data, not Spring Data JPA/Hibernate or reactive R2DBC. It does not need an HTTP server, Spring MVC, or Spring Security to verify `RowMapper` behavior. The APIs correspond to Spring Framework 6.1.x managed by Spring Boot 3.3.

## 2. Where Does RowMapper Operate?

A repository call into `JdbcTemplate` can be visualized as follows:

~~~text
Repository
  |
  | jdbcTemplate.query(sql, rowMapper, args...)
  v
JdbcTemplate
  +-- Open or obtain JDBC Connection
  +-- Create PreparedStatement, bind parameters
  +-- Driver executes SELECT -> ResultSet
  +-- while (resultSet.next()):
  |      rowMapper.mapRow(rs, rowNum)
  |      -> CustomerView
  +-- Collect list of results
  +-- Close ResultSet/Statement per JDBC lifecycle
  v
List<CustomerView>
~~~

Core signature:

~~~java
public interface RowMapper<T> {
    T mapRow(ResultSet rs, int rowNum) throws SQLException;
}
~~~

This is a **condensed explanatory signature**, not a standalone Java file. Important rules:

1. When `mapRow` is called, `ResultSet` is **already positioned on the row to read**. Do not call `rs.next()` inside the mapper, because `JdbcTemplate` advances the cursor.
2. `ResultSet` getters use **1-based** column indices when calling `getString(1)`, whereas Spring's `rowNum` is **0-based** within the result set. Do not use `rowNum` as an ID key.
3. Getters taking a String such as `rs.getString("full_name")` read the **column label**. If SELECT uses `AS display_name`, the label is `display_name`.
4. `RowMapper` processes **one row**, not the entire `List`, and should not issue extra queries per row (avoid N+1).
5. JDBC resource closing, query exception translation, and transaction boundaries are managed by `JdbcTemplate` and Spring. The mapper must not close the connection or result set.
6. JDBC getters can throw `SQLException`; inside `JdbcTemplate`, errors are typically translated into a Spring `DataAccessException`. However, conversion errors you throw explicitly—such as `IllegalArgumentException`—do not automatically share that exception type.

**Very practical bug with JOINs:** `SELECT *` across two tables that both have an `id` column can make the mapper read the wrong `id`. Explicitly list each column with aliases like `customer_id` and `order_id`, then test the exact labels.

## 3. SQL NULL, Java null, 0, FALSE, and Empty Strings

SQL NULL does not mean 0, FALSE, an empty String, or a default date. These are distinct states, and mapping must accurately reflect both nullability and domain meaning.

| SQL Type | JDBC Getter | On SQL NULL | Recommended Java Type |
|---|---|---|---|
| Nullable INTEGER | getInt | Returns **0**; `wasNull()` distinguishes | **Integer** |
| Nullable BOOLEAN | getBoolean | Returns **false**; `wasNull()` distinguishes | **Boolean** |
| BIGINT NOT NULL | getLong | Schema disallows NULL | **long** |
| Nullable VARCHAR | getString | Returns Java null | String |
| Nullable DECIMAL | getBigDecimal | Returns Java null | BigDecimal |
| Nullable DATE | getDate | Returns Java null | LocalDate after null check |
| Nullable TIMESTAMP | getTimestamp | Returns Java null | Temporal type per contract |
| Any column | getObject | SQL NULL normally → Java null | Driver-dependent type |

### 3.1. Primitive Getters Silently Lose Information Without Checking wasNull

**Wrong for nullable INTEGER:**

~~~java
Integer points = rs.getInt("reward_points");
~~~

Because `getInt` returns a primitive `int`, SQL NULL has already turned into `0` before autoboxing to `Integer`. Changing the variable type to `Integer` cannot recover the lost information.

**Right:**

~~~java
int rawPoints = rs.getInt("reward_points");
Integer points = rs.wasNull() ? null : rawPoints;
~~~

**Same for nullable BOOLEAN:**

~~~java
boolean rawVerified = rs.getBoolean("verified");
Boolean verified = rs.wasNull() ? null : rawVerified;
~~~

When `verified` is SQL NULL, the Java `Boolean` is assigned `null`. When SQL FALSE, `rs.wasNull()` is `false` and the Java `Boolean` is `Boolean.FALSE`. When TRUE, it is `Boolean.TRUE`.

### 3.2. wasNull Only Tracks the Most Recently Read Getter

A subtle bug is reading another column before calling `wasNull()`:

~~~java
// Wrong: getter for id overwrites the last-read status.
int raw = rs.getInt("reward_points");  // SQL NULL -> 0
long id = rs.getLong("id");            // BIGINT NOT NULL
Integer points = rs.wasNull() ? null : raw;

// Right:
int rawCorrect = rs.getInt("reward_points");
Integer pointsCorrect = rs.wasNull() ? null : rawCorrect;
long idCorrect = rs.getLong("id");
~~~

These snippets belong inside a method that has `ResultSet rs`, not separate Java files. **Do not place a single `rs.wasNull()` check at the end of `mapRow`**: it only describes the last column read, not any earlier nullable columns.

### 3.3. Should You Use ResultSet.getObject(..., Integer.class)?

JDBC offers `getObject(String, Class<T>)` and `getObject(String)`. SQL NULL maps to Java null; with a supporting driver, typed `getObject` can make wrapper mapping more concise. However, **type conversion support depends on the driver and SQL type**. H2, PostgreSQL, MySQL, Oracle, and SQL Server do not necessarily behave identically for BOOLEAN, UUID, JSON, ARRAY, or timezones.

In the main example, we use **`getInt`/`wasNull` and `getBoolean`/`wasNull`** to demonstrate the rule specified by `java.sql.ResultSet` and test it directly on H2.

### 3.4. An Absent Row Differs from a Row with Null Columns

A SELECT by ID may:
- Return no row: empty `List`, or repository returns `Optional.empty()`.
- Return one row where `reward_points`/`verified`/`credit_limit` are SQL NULL: repository returns an **`Optional` containing the object**, with those fields set to Java `null`.
- Return one row with `reward_points=0` and `verified=FALSE`: the object holds `Integer` 0 and `Boolean.FALSE`, distinct from `null`.

Never return `Optional.empty()` just because some columns are null. That conflates two separate concepts: **cardinality** and **nullability**.

## 4. Type Conversions Must Be Exact and Explicit

### 4.1. BIGINT, INTEGER, and Narrowing

SQL BIGINT should normally use Java `long`; INTEGER should use `int`/`Integer` depending on nullability. If you must narrow a `long` to an `int`, a regular Java cast can silently overflow:

~~~java
long largeId = 3_000_000_000L;
int lost = (int) largeId; // Original value is lost.

// Math.toIntExact(largeId) throws ArithmeticException,
// appropriate when the contract requires exact conversion.
~~~

For converting `BigDecimal` to `long`/`int`, `longValue()` and `intValue()` silently truncate fractional parts. If business rules prohibit truncation, use **`longValueExact`/`intValueExact`** to fail when the value cannot be represented exactly.

### 4.2. DECIMAL, NUMERIC, and BigDecimal

For SQL `DECIMAL(12,2)` representing money or limits, prefer **`BigDecimal`**:

~~~java
BigDecimal creditLimit = rs.getBigDecimal("credit_limit");
~~~

- SQL NULL → Java null.
- SQL `0.00` → `BigDecimal` with value `0.00`, **not null**.
- SQL `1234.50` → exact decimal value preserved per column definition.
- Never read with `getDouble` followed by `new BigDecimal(double)`: binary floating-point cannot accurately represent `0.1` and other decimal fractions.

**`BigDecimal.equals` compares both value and scale.** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` is `false`. In the H2 `DECIMAL(12,2)` example, asserting against `BigDecimal("1234.50")` verifies scale too. If business logic only requires numeric equality, use `compareTo(...) == 0` or AssertJ's `isEqualByComparingTo`; if scale is part of the contract, assert the exact scale.

### 4.3. DATE, TIMESTAMP, and Timezones

SQL DATE represents a calendar date without time of day. Common mapping:

~~~java
java.sql.Date sqlDate = rs.getDate("last_contact_date");
LocalDate lastContact =
        sqlDate == null ? null : sqlDate.toLocalDate();
~~~

You must check for SQL NULL before calling `toLocalDate`. Otherwise, nullable date tests will throw `NullPointerException`. Some JDBC 4.2 drivers support `getObject("last_contact_date", LocalDate.class)`; still test against the real driver.

**Do not blindly apply this rule to `TIMESTAMP WITH TIME ZONE`.** `DATE`, `TIMESTAMP WITHOUT TIME ZONE`, and `TIMESTAMP WITH TIME ZONE` have distinct semantics. When `Instant` or `OffsetDateTime` is required, define a UTC/timezone policy and test daylight-saving/timezone boundaries; never unknowingly rely on the CI machine's system default timezone.

### 4.4. VARCHAR Status → Enum Needs a Normalization Policy

The schema in this lesson stores `state_code` as `VARCHAR NOT NULL`, while fixtures include both `"active"` and `"ACTIVE"`. Java's `Enum.valueOf` is case-sensitive, so the example uses:

~~~java
String rawCode = rs.getString("state_code");
CustomerStatus status = CustomerStatus.valueOf(
        rawCode.trim().toUpperCase(Locale.ROOT));
~~~

**`Locale.ROOT`** ensures case-conversion rules for technical codes do not vary with the host machine's locale. Outcomes:
- `"active"` → `ACTIVE`.
- `"PAUSED"` → `PAUSED`.
- `"not-a-status"` → `IllegalArgumentException`.

Do not silently map unknown enum codes to `ACTIVE` or `PAUSED` to avoid errors. If the domain defines an `UNKNOWN` status, model it explicitly and test per contract; if an unknown code represents corrupt data, fail loudly so bad data is caught and fixed.

## 5. Choosing the Right Test Level

| Level | Real Driver/SQL? | What It Proves |
|---|---|---|
| Unit test custom RowMapper with mocked ResultSet | No | Getter/`wasNull` order and Java branching logic |
| **@JdbcTest + H2** | **Yes** | SQL, ResultSet, column labels, null/type conversions, JDBC behavior |
| @JdbcTest + production DB Testcontainers | Yes, close to production | Vendor/type/driver-specific SQL conversions |
| @SpringBootTest + DataSource | Yes | Full app context, service/repository wiring |
| HTTP integration above repository | Yes if configured | Adds HTTP/security/JSON; does not replace JDBC tests |

Spring Boot 3.3 **`@JdbcTest`** auto-configures an embedded database and `JdbcTemplate` when H2 is on the test classpath. It is transactional by default and rolls back test-managed changes after each test. It **does not automatically component-scan every `@Repository` or `@Service`**, so tests import only the repository they actually need.

A unit test that merely stubs `ResultSet` makes getters return pre-programmed values without proving JDBC SQL or type behavior. Thus, when the target is row mapping, NULL handling, and type conversion, **`@JdbcTest` with a real database** is the essential test layer.

## 6. Complete Spring Boot 3.3.5 / Java 17 / H2 Example

The `customer_profiles` table uses these column mappings:

| Column | SQL | Java |
|---|---|---|
| id | BIGINT PRIMARY KEY | long |
| full_name | VARCHAR(80) NOT NULL | String |
| reward_points | INTEGER NULL | Integer |
| verified | BOOLEAN NULL | Boolean |
| credit_limit | DECIMAL(12,2) NULL | BigDecimal |
| last_contact_date | DATE NULL | LocalDate |
| state_code | VARCHAR(20) NOT NULL | CustomerStatus |

The fixtures include a row with `0`/`FALSE`, a row with all nullable columns set to NULL, a row with `TRUE`/`0.00`, and a row with an invalid enum code. That forces the mapper to prove it distinguishes every case rather than just returning a happy-path object.

### 6.1. Project Structure

~~~text
settings.gradle
build.gradle
src/main/java/demo/jdbc/JdbcMappingApplication.java
src/main/java/demo/jdbc/CustomerStatus.java
src/main/java/demo/jdbc/CustomerView.java
src/main/java/demo/jdbc/CustomerRowMapper.java
src/main/java/demo/jdbc/CustomerRepository.java
src/test/resources/schema.sql
src/test/resources/data.sql
src/test/java/demo/jdbc/CustomerJdbcMappingTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'jdbc-row-mapping-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Dependency explanation:** `starter-jdbc` provides Spring JDBC/`JdbcTemplate`, H2 is the embedded JDBC database on the runtime/test classpath, and `starter-test` provides Spring Test, JUnit Jupiter, and assertions. There is no Hibernate/JPA or R2DBC because the focus is JDBC `ResultSet`. The Spring Boot BOM manages compatible versions; avoid manually pinning a different H2 or JDBC driver without reason.

### 6.2. Application and Java Data Types

**src/main/java/demo/jdbc/JdbcMappingApplication.java**

~~~java
package demo.jdbc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JdbcMappingApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdbcMappingApplication.class, args);
    }
}
~~~

**src/main/java/demo/jdbc/CustomerStatus.java**

~~~java
package demo.jdbc;

public enum CustomerStatus {
    ACTIVE,
    PAUSED
}
~~~

**src/main/java/demo/jdbc/CustomerView.java**

~~~java
package demo.jdbc;

import java.math.BigDecimal;
import java.time.LocalDate;

public record CustomerView(
        long id,
        String name,
        Integer rewardPoints,
        Boolean verified,
        BigDecimal creditLimit,
        LocalDate lastContactDate,
        CustomerStatus status) {
}
~~~

The Java 17 record keeps fields immutable by value. In particular, `Integer rewardPoints` and `Boolean verified` can be `null`, unlike `int`/`boolean`. If the domain disallows nulls, any normalization policy should be defined explicitly in an appropriate layer rather than relying silently on JDBC primitive getters.

### 6.3. SQL Schema and Data for Tests

**src/test/resources/schema.sql**

~~~sql
CREATE TABLE customer_profiles (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(80) NOT NULL,
    reward_points INTEGER NULL,
    verified BOOLEAN NULL,
    credit_limit DECIMAL(12,2) NULL,
    last_contact_date DATE NULL,
    state_code VARCHAR(20) NOT NULL
);
~~~

**src/test/resources/data.sql**

~~~sql
INSERT INTO customer_profiles (
    id, full_name, reward_points, verified,
    credit_limit, last_contact_date, state_code
) VALUES
    (1, 'Lan', 0, FALSE, 1234.50, DATE '2024-04-12', 'active'),
    (2, 'Minh', NULL, NULL, NULL, NULL, 'PAUSED'),
    (3, 'Hòa', 42, TRUE, 0.00, DATE '2024-05-01', 'ACTIVE'),
    (4, 'Invalid', 7, FALSE, 5.00, DATE '2024-06-01',
     'not-a-status');
~~~

**Why put these in `src/test/resources`?** With embedded H2 in `@JdbcTest`, Spring Boot 3.3 includes **`SqlInitializationAutoConfiguration`**, which by default executes `schema.sql` and then `data.sql` from the test classpath when initializing the DataSource. These test files are **not automatically included in a regular `bootRun`**, because `bootRun` does not put test resources onto the runtime classpath by default. In production, use Flyway/Liquibase or an environment-appropriate standalone schema initialization mechanism.

The tests below only perform SELECTs and do not modify the seeded rows, so they are independent of execution order. If you add DML, understand `@JdbcTest` transaction/rollback semantics; never run arbitrary CREATE/DROP DDL inside every test since databases handle DDL commits differently.

### 6.4. Complete RowMapper

**src/main/java/demo/jdbc/CustomerRowMapper.java**

~~~java
package demo.jdbc;

import java.math.BigDecimal;
import java.sql.Date;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.util.Locale;

import org.springframework.jdbc.core.RowMapper;

public final class CustomerRowMapper implements RowMapper<CustomerView> {

    @Override
    public CustomerView mapRow(ResultSet rs, int rowNum)
            throws SQLException {

        long id = rs.getLong("id");
        String name = rs.getString("full_name");

        int rawPoints = rs.getInt("reward_points");
        Integer points = rs.wasNull() ? null : rawPoints;

        boolean rawVerified = rs.getBoolean("verified");
        Boolean verified = rs.wasNull() ? null : rawVerified;

        BigDecimal creditLimit = rs.getBigDecimal("credit_limit");

        Date sqlDate = rs.getDate("last_contact_date");
        LocalDate lastContact =
                sqlDate == null ? null : sqlDate.toLocalDate();

        String rawStatus = rs.getString("state_code");
        CustomerStatus status;
        try {
            status = CustomerStatus.valueOf(
                    rawStatus.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "Unsupported state_code: " + rawStatus, ex);
        }

        return new CustomerView(
                id, name, points, verified,
                creditLimit, lastContact, status);
    }
}
~~~

**Analysis of key points:**
1. `id` is `BIGINT PRIMARY KEY NOT NULL`; Java `long` cannot lose a valid NULL because the schema disallows null.
2. `name` is `VARCHAR NOT NULL`, read via `getString`. If the schema were nullable, `getString` would return Java `null` instead of an empty String.
3. `reward_points` uses `getInt` followed **immediately by `wasNull`**, producing a proper nullable `Integer`.
4. `verified` uses `getBoolean` followed **immediately by `wasNull`**, preserving `TRUE`/`FALSE`/`NULL`.
5. `credit_limit` uses `getBigDecimal`; it never passes through `double` and never turns null into `BigDecimal.ZERO`.
6. `last_contact_date` uses `getDate` and checks null before calling `toLocalDate`, preventing an NPE.
7. `state_code` is NOT NULL, so `rawStatus.trim()` is valid under the current schema. If a real-world column allows NULL, design an explicit null branch.
8. Enum conversion uses `Locale.ROOT` and throws an exception naming both the column and raw code; it does not silently default unknown codes to `ACTIVE`.
9. The mapper never calls `rs.next()`, never closes `ResultSet`, and never sends additional SQL inside the callback.
10. `rowNum` is never used as a primary key. When logging row numbers, note that row order depends on `ORDER BY`.

### 6.5. Repository Using JdbcTemplate and Parameterized SQL

**src/main/java/demo/jdbc/CustomerRepository.java**

~~~java
package demo.jdbc;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerRepository {

    private static final String SELECT_COLUMNS = """
            SELECT id, full_name, reward_points, verified,
                   credit_limit, last_contact_date, state_code
            FROM customer_profiles
            """;

    private final JdbcTemplate jdbc;
    private final CustomerRowMapper mapper = new CustomerRowMapper();

    public CustomerRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<CustomerView> findById(long id) {
        List<CustomerView> rows = jdbc.query(
                SELECT_COLUMNS + " WHERE id = ?",
                mapper, id);

        return rows.stream().findFirst();
    }

    public List<CustomerView> findByStatus(CustomerStatus status) {
        return jdbc.query(
                SELECT_COLUMNS
                        + " WHERE UPPER(state_code) = ? ORDER BY id",
                mapper, status.name());
    }
}
~~~

`findById` queries by primary key so at most one row matches; `jdbc.query` returns an empty `List` when missing, yielding `Optional.empty()`. When a row exists with several SQL NULL columns, `Optional` still wraps the `CustomerView`. `findByStatus` reuses the same `RowMapper` across multiple rows; `ORDER BY` makes the expected order in tests deterministic.

The **`?`** placeholders bind parameters via `PreparedStatement`, avoiding concatenating untrusted input directly into SQL. `SELECT_COLUMNS` is concatenated only with **constant SQL fragments from source code**, containing no external data. SQL `UPPER` is simple for case normalization, though it can impact index usage in production; choose your normalization policy deliberately during table design.

**Why instantiate `RowMapper` with `new`?** The mapper is stateless and has no constructor dependencies, so it can be reused safely inside the repository. If it needs converters or configuration, use intentional bean injection; `RowMapper` does not have to be a `@Component`.

## 7. JUnit Jupiter Test Suite: 12 JDBC-Executing Methods

**src/test/java/demo/jdbc/CustomerJdbcMappingTest.java**

~~~java
package demo.jdbc;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
@Import(CustomerRepository.class)
class CustomerJdbcMappingTest {

    @Autowired
    CustomerRepository repository;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void mapsZeroFalseDecimalDateAndLowercaseStatus() {
        CustomerView row = repository.findById(1L).orElseThrow();

        assertEquals(1L, row.id());
        assertEquals("Lan", row.name());
        assertEquals(Integer.valueOf(0), row.rewardPoints());
        assertEquals(Boolean.FALSE, row.verified());
        assertEquals(new BigDecimal("1234.50"), row.creditLimit());
        assertEquals(
                LocalDate.of(2024, 4, 12), row.lastContactDate());
        assertEquals(CustomerStatus.ACTIVE, row.status());
    }

    @Test
    void preservesAllSqlNullColumns() {
        CustomerView row = repository.findById(2L).orElseThrow();

        assertEquals("Minh", row.name());
        assertNull(row.rewardPoints());
        assertNull(row.verified());
        assertNull(row.creditLimit());
        assertNull(row.lastContactDate());
        assertEquals(CustomerStatus.PAUSED, row.status());
    }

    @Test
    void mapsTrueZeroMoneyAndUnicode() {
        CustomerView row = repository.findById(3L).orElseThrow();

        assertEquals("Hòa", row.name());
        assertEquals(Integer.valueOf(42), row.rewardPoints());
        assertEquals(Boolean.TRUE, row.verified());
        assertEquals(new BigDecimal("0.00"), row.creditLimit());
        assertEquals(
                LocalDate.of(2024, 5, 1), row.lastContactDate());
        assertEquals(CustomerStatus.ACTIVE, row.status());
    }

    @Test
    void missingRowProducesOptionalEmpty() {
        assertTrue(repository.findById(999L).isEmpty());
    }

    @Test
    void mapsSeveralRowsInExplicitOrder() {
        List<CustomerView> rows =
                repository.findByStatus(CustomerStatus.ACTIVE);

        assertEquals(2, rows.size());
        assertEquals(
                List.of(1L, 3L),
                rows.stream().map(CustomerView::id).toList());
        assertEquals(
                List.of("Lan", "Hòa"),
                rows.stream().map(CustomerView::name).toList());
    }

    @Test
    void rejectsInvalidEnumCodeClearly() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> repository.findById(4L));

        assertTrue(error.getMessage().contains(
                "Unsupported state_code: not-a-status"));
    }

    @Test
    void bareGetIntCollapsesNullAndZero() {
        Integer zero = jdbc.queryForObject(
                "SELECT reward_points FROM customer_profiles WHERE id = ?",
                (rs, n) -> rs.getInt("reward_points"), 1L);

        Integer sqlNull = jdbc.queryForObject(
                "SELECT reward_points FROM customer_profiles WHERE id = ?",
                (rs, n) -> rs.getInt("reward_points"), 2L);

        assertEquals(Integer.valueOf(0), zero);
        assertEquals(Integer.valueOf(0), sqlNull);
    }

    @Test
    void wasNullObservesOnlyTheLastColumnRead() {
        Boolean tooLate = jdbc.queryForObject(
                """
                SELECT reward_points, id
                FROM customer_profiles WHERE id = 2
                """,
                (rs, n) -> {
                    rs.getInt("reward_points");
                    rs.getLong("id");
                    return rs.wasNull();
                });

        Boolean immediately = jdbc.queryForObject(
                """
                SELECT reward_points
                FROM customer_profiles WHERE id = 2
                """,
                (rs, n) -> {
                    rs.getInt("reward_points");
                    return rs.wasNull();
                });

        assertEquals(Boolean.FALSE, tooLate);
        assertEquals(Boolean.TRUE, immediately);
    }

    @Test
    void bareGetBooleanCollapsesNullAndFalse() {
        Boolean falseValue = jdbc.queryForObject(
                "SELECT verified FROM customer_profiles WHERE id = ?",
                (rs, n) -> rs.getBoolean("verified"), 1L);

        Boolean sqlNull = jdbc.queryForObject(
                "SELECT verified FROM customer_profiles WHERE id = ?",
                (rs, n) -> rs.getBoolean("verified"), 2L);

        assertEquals(Boolean.FALSE, falseValue);
        assertEquals(Boolean.FALSE, sqlNull);
    }

    @Test
    void readsSqlColumnAliasByColumnLabel() {
        String name = jdbc.queryForObject(
                """
                SELECT full_name AS screen_name
                FROM customer_profiles WHERE id = ?
                """,
                (rs, n) -> rs.getString("screen_name"), 1L);

        assertEquals("Lan", name);
    }

    @Test
    void queryForObjectRequiresExactlyOneRow() {
        assertThrows(
                EmptyResultDataAccessException.class,
                () -> jdbc.queryForObject(
                        """
                        SELECT full_name
                        FROM customer_profiles WHERE id = ?
                        """,
                        String.class, 999L));

        assertThrows(
                IncorrectResultSizeDataAccessException.class,
                () -> jdbc.queryForObject(
                        """
                        SELECT full_name
                        FROM customer_profiles WHERE id IN (1, 3)
                        """,
                        String.class));
    }

    @Test
    void exactNarrowingRejectsFractionsAndOverflow() {
        assertThrows(
                ArithmeticException.class,
                () -> new BigDecimal("12.50").intValueExact());

        assertThrows(
                ArithmeticException.class,
                () -> Math.toIntExact(3_000_000_000L));
    }
}
~~~

**Total: 12 `@Test` methods.** The fixtures are read-only, so no `@TestMethodOrder`, static mutable state, or test database reset between methods is needed. Tests 7–9 **deliberately assert the buggy behavior of primitive getters when `wasNull` is omitted** so learners see the pitfall: those are not production mappers. The real mapper calls `wasNull` in the proper order, and tests 1–3 guard the data.

### 7.1. Why Is Test id=1 Important?

Row 1 has `reward_points=0`, `verified=FALSE`, `credit_limit=1234.50`, `DATE '2024-04-12'`, and status `"active"`. A buggy mapper could still return `0`/`FALSE` for this row and pass a naive test. Test `id=1` must pair with `id=2` (NULL) and `id=3` (TRUE) to ensure **`0`/`FALSE` are not collapsed with SQL NULL**.

`BigDecimal("1234.50")` is compared with exact scale matching H2's `DECIMAL(12,2)`. The enum converter normalizes `"active"` to `ACTIVE` under the `Locale.ROOT` policy. `DATE` converts accurately to `LocalDate`, independent of the JVM's timezone for calendar dates.

### 7.2. Test id=2 Catches Missing wasNull

Row `id=2` has SQL NULL for `reward_points`, `verified`, `credit_limit`, and `last_contact_date`. `preservesAllSqlNullColumns()` checks **every nullable field**. If the mapper calls `getInt` and `getBoolean` without `wasNull`, it returns `Integer(0)` and `Boolean.FALSE`, failing the assertions. If it calls `date.toLocalDate()` without a null check, it throws `NullPointerException`.

This row is still a valid record because `id`/`full_name`/`state_code` are all `NOT NULL`. Do not turn the object into `Optional.empty()` merely because some fields have no value.

### 7.3. Test id=3 Protects TRUE, Zero Money, and Unicode

Row 3 has `points=42`, `verified=TRUE`, `credit_limit=0.00`, and `full_name` `"Hòa"`. The test proves `Boolean.TRUE` differs from `NULL`/`FALSE`, `BigDecimal("0.00")` differs from SQL NULL, `DATE '2024-05-01'` is preserved, and Vietnamese Unicode text passes cleanly through H2/JDBC/JVM.

For real-world data, also test negative amounts, very large numbers, special scales, and Unicode normalization if required by the domain. The 3 rows are an **intentionally minimal set** highlighting the most common bugs.

### 7.4. Testing wasNull and the Risk of Calling It Too Late

`bareGetIntCollapsesNullAndZero()` deliberately reads two rows containing `0` and `NULL` via `getInt` without `wasNull`; both yield `0`. `bareGetBooleanCollapsesNullAndFalse()` does the same: `FALSE` and `NULL` both yield `false`.

`wasNullObservesOnlyTheLastColumnRead()` demonstrates the call order:
- `getInt("reward_points")` on SQL NULL.
- `getLong("id")` on `BIGINT NOT NULL`.
- `wasNull()` now returns **`false`**, because the most recent getter was `id`.

Calling `wasNull` right after `getInt` returns **`true`**. The takeaway is **statement placement**, not statement count: you cannot put one `wasNull` at the end of a method and infer nullability for earlier columns.

### 7.5. Testing Status, Row Count, and Aliases

Row `id=4` intentionally stores `state_code="not-a-status"`. The custom enum converter explicitly throws `IllegalArgumentException` with `"Unsupported state_code"`. Never turn it into `Optional.empty()` or default to `ACTIVE`, which masks corrupt data.

`findByStatus(ACTIVE)` verifies a multi-row SELECT returns a `List` ordered by `ORDER BY`: `1, 3`. The SQL `UPPER(state_code)` matches both `"active"` and `"ACTIVE"`. This ensures the mapper works across multiple rows without relying on arbitrary database ordering.

`readsSqlColumnAliasByColumnLabel()` runs `SELECT full_name AS screen_name` with `rs.getString("screen_name")`. Per JDBC, the column label is the alias. Reading `full_name` when the `ResultSet` exposes only `screen_name` causes the driver to throw `SQLException`, which `JdbcTemplate` translates.

`queryForObjectRequiresExactlyOneRow()` explicitly tests:
- Zero rows → `EmptyResultDataAccessException`.
- More than one row → `IncorrectResultSizeDataAccessException`.

These are **cardinality errors**, not nullable SQL columns. `JdbcTemplate.query` returns a `List`, making it suited for collections or converting unique-key lookups to `Optional`.

## 8. Running the Tests and Verifying Results

If the project already has a Gradle Wrapper:

~~~bash
./gradlew test
~~~

In Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If you just created the source files without generating Wrapper scripts/JAR, `./gradlew` will not exist yet. Use a compatible Gradle installation to generate the wrapper or run **`gradle test`**. Embedded H2 requires no containers, HTTP sockets, PostgreSQL, or Redis.

Run the class individually:

~~~bash
./gradlew test --tests demo.jdbc.CustomerJdbcMappingTest
~~~

With the exact sources, scripts, and dependencies from the example, JUnit Jupiter discovers **12 test methods**. All are designed to PASS on H2; this is expected from the sample sources, **not a claim that tests have been executed in your environment**. Gradle's report is typically located at:

~~~text
build/reports/tests/test/index.html
~~~

**Self-practice mutations to see what the tests protect:**

- Remove `rs.wasNull()` after `getInt` or `getBoolean`: the NULL test must fail.
- Change `Integer`/`Boolean` to `int`/`boolean`: SQL NULL rows can no longer be preserved.
- Call `toLocalDate` without checking for a null date: test `id=2` fails with NPE.
- Convert `BigDecimal` through `double` before constructing the object: money/scale tests can catch precision loss.
- Remove `toUpperCase(Locale.ROOT)`: row `"active"` fails enum conversion.
- Replace invalid enum codes with a default status: the invalid-code test fails.
- Rename the SELECT alias without updating the getter label: JDBC reports column not found.
- Remove `ORDER BY` on multi-row queries: ordering is no longer guaranteed by the SQL contract.

Never edit expected assertions to hide failures. The purpose of mutation testing is to see **which behavior a test protects** and restore proper mapping.

## 9. Other Mapping Approaches: Pros and Cons

| Mapping Approach | Mechanism | Best Used When | Must Still Test |
|---|---|---|---|
| **Custom RowMapper<T>** | Manually reads ResultSet and builds DTO | Custom policies for NULL/enum/date/money | Every getter, nullability, conversions |
| **BeanPropertyRowMapper<T>** | Maps via JavaBean setters/properties | Simple beans | Null-to-primitive, naming, converters |
| **DataClassRowMapper<T>** | Constructor-based / data class / record | Simple Java records | Custom enums, nullable types, precision |
| **SingleColumnRowMapper<T>** | One column into a single value | COUNT/ID/String | Empty/multiple rows, null |
| **ColumnMapRowMapper** | Row into Map of labels/values | Dynamic queries/tooling | Duplicate labels, reduced type safety |

`BeanPropertyRowMapper` normally converts column `full_name` to property `fullName` on matching beans, though that does not mean it applies custom business enum conversions. `DataClassRowMapper` supports Java records depending on version, yet you still need tests for nulls, scale, and statuses. **Swapping mapper implementations must never silently alter the data contract.**

For multi-table JOIN queries or nested DTOs, a custom `RowMapper` is very useful; however, never query the database again inside `mapRow` per row, as that creates **N+1 queries**. Consider SQL joins, batch fetching, or an aggregate extractor instead.

## 10. Test Matrix by Data Type

| Data Type | Minimum Fixture | What Must Be Preserved |
|---|---|---|
| INTEGER NULL | SQL NULL, 0, 42, -1, near limits | NULL distinct from 0, no overflow |
| BOOLEAN NULL | NULL, FALSE, TRUE | Three distinct states |
| DECIMAL | NULL, 0.00, 0.10, 1234.50 | Exact BigDecimal, scale per contract |
| DATE | NULL, normal date, month/year boundaries | Exact LocalDate, no NPE |
| VARCHAR | null if nullable, empty, blank, Unicode | Never collapse distinct states |
| VARCHAR enum | ACTIVE, active, " paused ", unknown code | Normalization/failure policy |
| BIGINT | 1, large values, int overflow boundary | Java long / exact narrowing |
| SELECT | 0 rows, 1 row, >1 rows | Proper List/Optional/queryForObject |
| SQL alias | Original name, alias, JOIN duplicate labels | Read exact column labels |
| TIMESTAMP | Null, UTC, timezone transitions | Explicit temporal semantics |
| UUID/JSON/ARRAY | Valid, null, driver-specific invalid | Test with production JDBC driver |

Do not force every domain to share a single null policy. For example, `credit_limit=NULL` can mean undeclared while `0.00` means zero limit; in another domain, NULL might normalize to an explicit documented default. **What matters is making an intentional decision and backing it with tests**, rather than letting JDBC primitive defaults decide for you.

## 11. H2 Limitations and Production Database Requirements

H2 catches many common JDBC mistakes quickly, yet it does not replace PostgreSQL/MySQL/Oracle/SQL Server for all data types:
- Vendor SQL dialects, quoted identifiers, and column label case sensitivity.
- JSONB, native ENUM, UUID, ARRAY, and binary/CLOB types.
- BOOLEAN mappings for custom 0/1/CHAR representations.
- DECIMAL precision/scale, overflow, and rounding.
- TIMESTAMP/TIMESTAMP WITH TIME ZONE and driver-specific timezone conversions.
- Empty string vs. NULL, Unicode collation/case conversion.
- Transaction locking, isolation, and vendor SQLState/exception classes.

For vendor-dependent columns, add integration tests with **Testcontainers** and the real production JDBC driver and schema migrations. In `@JdbcTest`, the datasource can be replaced with an embedded DB by default; to keep a container datasource, configure explicitly with **`@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)`** alongside the test datasource/service connection.

Not every test needs a full `@SpringBootTest`. Layer appropriately: unit tests for mapper logic, `@JdbcTest` with H2 for JDBC fundamentals, Testcontainers for vendor-specific behavior, and full integration tests for business/HTTP boundaries.

## 12. Transactions, Exceptions, and Security When Testing JDBC

**Transactions:** `@JdbcTest` normally rolls back test-managed DML after each method. The sample suite only runs SELECTs, so no cleanup is needed. If you add INSERT/UPDATEs, understand transaction scope; DDL has separate commit semantics. When a `RANDOM_PORT` HTTP test calls the server on another thread/transaction, `@Transactional` on the JUnit method **does not automatically roll back** server-committed writes.

**Exceptions:** `SQLException` from SQL or the driver is translated by `JdbcTemplate` into `DataAccessException`; `IllegalArgumentException` from custom enum conversion can propagate straight to the caller. `EmptyResultDataAccessException` and `IncorrectResultSizeDataAccessException` are row-cardinality problems, not nullable-column mapping issues.

**Security:** use `JdbcTemplate` `?` parameters instead of concatenating user input into SQL to prevent SQL injection and enforce clean type binding. Never expose raw PII, tokens, sensitive bind values, or full database exceptions in responses. If the converter throws on an unrecognized `state_code`, the message is helpful for internal logs, yet must be filtered safely before reaching clients.

## 13. Common Errors and Debugging Process

| Symptom | Cause | Fix |
|---|---|---|
| SQL NULL becomes 0 | `getInt` without `wasNull` | Call `wasNull` right after getter, use `Integer` |
| SQL NULL becomes false | `getBoolean` without `wasNull` | Call `wasNull` right after getter, use `Boolean` |
| `wasNull` is false despite earlier NULL column | Another getter called in between | Put `wasNull` immediately after the checked column |
| `NullPointerException` on Date | `getDate` returned null | Check null before calling `toLocalDate` |
| Wrong `BigDecimal` | DECIMAL passed through `double` | Use `getBigDecimal`, test precision/scale |
| `BigDecimal.equals` fails on scale | `1.0` differs from `1.00` under `equals` | Choose `equals` vs `compareTo` per contract |
| `long` corrupted after `int` cast | Numeric overflow | Use `Math.toIntExact` when narrowing |
| Enum `"active"` rejected | `valueOf` is case-sensitive | Uppercase with `Locale.ROOT` if policy allows |
| Unknown enum code swallowed | Converter uses wrong default | Fail explicitly or map to defined `UNKNOWN` enum |
| SQL column not found | Alias in SELECT differs from getter | Read exact label and test real query |
| Wrong ID mapped in JOIN | Duplicate column names | Use explicit aliases |
| `queryForObject` throws on 0 rows | Mistaken for `Optional` | Use `query` + List/Optional when appropriate |
| `queryForObject` throws on multiple rows | Result not unique | Use `List` or add unique constraint |
| `@JdbcTest` missing repository bean | Slice does not scan all `@Repository` beans | `@Import` the target class |
| `schema.sql`/`data.sql` did not run | Wrong test classpath or SQL init config | Place in `src/test/resources`, check embedded DB config |
| H2 passes, production fails | Driver-specific conversion | Testcontainers with real DB |
| Passes alone, fails in suite | Static state / uncleaned DML | Isolated fixtures, explicit rollback |
| Mapper skips rows | Manually called `rs.next` | Let `JdbcTemplate` drive `ResultSet` |
| Unexpected exception type | Confused SQL exception with conversion error | Test each exception boundary explicitly |

**Recommended investigation order:** check schema/nullability → check SQL SELECT/aliases → check getters and `wasNull` call order → seed NULL/0/FALSE/TRUE → assert `BigDecimal`/DATE/enum → check row counts → run `@JdbcTest` → if only production fails, run the same fixtures against the real driver. Never use `Thread.sleep` or depend on test ordering to "fix" data issues.

## 14. Self-Practice Exercises

1. **Nullable BIGINT:** Add `referrer_id BIGINT NULL`, map with `Long` and `getLong`/`wasNull`; test null, 0, and large IDs.
2. **Tri-state BOOLEAN:** Change `verified` mapping to bare `getBoolean` and see which test fails; explain why SQL NULL differs from FALSE.
3. **DECIMAL:** Seed `0.00`, `0.10`, `100000.99`, and SQL NULL; use `BigDecimal` and verify scale per contract.
4. **Enum:** Add codes `" paused "` and `"DISABLED"`; pick a normalization, failure, or `UNKNOWN` policy and write tests.
5. **Alias:** Run `SELECT full_name AS preferred_name`; update the mapper to the label or write a test catching column-not-found.
6. **Row cardinality:** Use `queryForObject` for 0/1/2 rows and contrast it with a valid row having SQL NULL nullable fields.
7. **Date/time:** Add a `TIMESTAMP` column; choose `LocalDateTime` or `Instant` and test timezone/DST independently of the host machine.
8. **Generic mappers:** Swap custom `RowMapper` for `BeanPropertyRowMapper` or `DataClassRowMapper` and re-run the NULL/enum/money tests.
9. **Real driver:** Run the same fixtures on PostgreSQL Testcontainers and compare type conversions.
10. **Transactions:** Add an `INSERT` test and verify rollback; contrast it with a `RANDOM_PORT` test that has a separate server transaction.

## 15. Official Documentation

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html) — `@JdbcTest`, embedded databases, `JdbcTemplate`, and rollback.
- [Spring Boot 3.3 — Test Slices](https://docs.spring.io/spring-boot/3.3/appendix/test-auto-configuration/slices.html) — `SqlInitializationAutoConfiguration` in `@JdbcTest`.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html) — `schema.sql`, `data.sql`, and embedded DB defaults.
- [Spring Framework 6.1 — RowMapper API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/RowMapper.html) — `mapRow(ResultSet, rowNum)` contract.
- [Spring Framework 6.1 — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html) — `query`, `queryForObject`, JDBC exception translation.
- [Java SE 17 — ResultSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html) — primitive getters, `wasNull`, `getBigDecimal`, `getDate`.
- [Java SE 17 — BigDecimal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html) — scale, `equals`/`compareTo`, exact narrowing.
- [Spring JDBC — DataClassRowMapper](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/DataClassRowMapper.html) — constructor-based mapping and records.

**Key takeaway:** A good `RowMapper` must **preserve the true meaning of SQL data**. SQL NULL is not `0`/`FALSE`; for primitive getters, call `wasNull` **immediately after the getter** and use `Integer`/`Boolean` to keep nulls intact. Use `BigDecimal` for `DECIMAL`, check null before `LocalDate` for `DATE`, apply an explicit policy for enum conversion, and match SQL aliases with getter column labels. **`@JdbcTest` + H2 + NULL/zero/false/true/invalid-code tests** catch bugs quickly, while the production JDBC driver must also be tested whenever type conversion depends on the SQL vendor.