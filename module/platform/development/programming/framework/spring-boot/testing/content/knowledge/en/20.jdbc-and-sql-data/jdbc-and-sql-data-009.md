# JDBC and SQL Data: Testing Stored Procedures and Database-Specific Features When Used

## 1. When Does a Test Need a Real Database?

A Spring Boot application typically runs standard SQL queries: `SELECT`, `INSERT`, `UPDATE`, `DELETE`. However, some systems also use **stored procedures**, **database functions**, `JSONB` types, UPSERTs, `RETURNING`, triggers, sequences, locking, window functions, or SQL dialect-specific features. In those cases, **H2 or a mocked repository cannot prove the code works on PostgreSQL, SQL Server, Oracle, or MySQL**.

For example, the application sends an inventory reservation command asking the database to **atomically** decrement stock and return the remaining quantity. A unit test that only stubs:

~~~java
when(gateway.reserve("SKU-101", 3)).thenReturn(4);
~~~

proves only that the mock returns `4`; it **does not prove**:

- The procedure name and parameter count/order/types match.
- Spring JDBC and the JDBC driver execute `CALL` properly.
- The procedure updates rows conditionally and returns the right output.
- On insufficient stock or invalid quantity, the transaction rolls back and SQLSTATE matches.
- Concurrent transactions cannot drive inventory negative.
- `JSONB`, `ON CONFLICT`, and `RETURNING` match production database syntax and semantics.

**Test selection rule:** whenever implementation relies on database-specific SQL, at least one integration test layer must run against **the exact engine** and a version sufficiently close to production. SQL-independent business rules should still be tested fast with unit tests.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish stored **procedures** from **functions**, `CALL` from `SELECT`, and `IN`/`OUT`/`INOUT` parameters.
2. Choose `JdbcTemplate`, `SimpleJdbcCall`, `CallableStatement`, `@JdbcTest`, and `@DataJdbcTest` appropriately.
3. Connect to real PostgreSQL via Testcontainers and `@ServiceConnection`, preventing Spring from replacing the datasource with H2.
4. Prepare repeatable fixtures, invoke production data-access code, and assert **both outputs and side effects**.
5. Test `JSONB`, `INSERT ... ON CONFLICT ... RETURNING`, unique constraints, and SQLSTATE codes.
6. Understand default transaction rollback in JDBC slices and PostgreSQL's **aborted transaction** state after a SQL error.
7. Plan additional tests for concurrency, migrations, permissions, timeouts, and locking without assuming a single-threaded test proves all of them.
8. Distinguish runnable code, non-standalone illustrative snippets, and expected Gradle results.

## 2. Scope: Do Not Add Stored Procedures Unless Needed

Stored procedures help when multiple data-adjacent operations belong in one DB call, logic is shared across systems, or security, privilege control, and synchronization are needed close to data. However, if an application does not use procedures, do not invent artificial routines merely to make tests look "thorough".

| Application Case | Appropriate Test |
| --- | --- |
| Standard SQL only, simple repositories | `@JdbcTest` or `@DataJdbcTest` with real fixtures and queries |
| Calling a PostgreSQL procedure with `CALL` | Test real PostgreSQL; assert inputs/outputs and side effects |
| Calling `SELECT some_function(...)` | Test function with boundary inputs, nulls, return types, empty sets |
| Using `JSONB @>`/`->>` | Test PostgreSQL with exact column types, parameter types, and indexes |
| Using vendor-specific UPSERT | Test both conflict and insert branches, constraints, `RETURNING` |
| Using Oracle/SQL Server/MySQL stored routines | Test exact driver, engine, schema/package, and parameter modes |
| Using triggers/sequences/generated columns | Test post-`INSERT/UPDATE` effects, rollback, and permissions |
| Preventing lost updates, overselling, deadlocks | Concurrency integration tests with multiple connections/transactions |
| Verifying service transaction policies | Integration tests keeping real service + transaction manager + DB |
| Reading millions of rows or tuning SQL plans | Performance tests/`EXPLAIN` on production-like datasets and engines |

**Do not mix goals:** JDBC tests prove real SQL and mapping; they do not prove HTTP endpoints or status codes. If a feature is exposed via an API, add scoped web/integration tests as well.

## 3. Comparing Procedures, Functions, and SQL Statements

"Stored procedure" is sometimes used loosely for any DB routine, yet **PostgreSQL distinguishes them** clearly:

| Kind | PostgreSQL Declaration | Invocation | Return Value |
| --- | --- | --- | --- |
| Procedure | `CREATE PROCEDURE` | `CALL procedure(...)` | Can return output row(s) from `OUT/INOUT` |
| Scalar function | `CREATE FUNCTION ... RETURNS ...` | `SELECT function(...)` | Single declared value |
| Table-returning function | `RETURNS TABLE(...)` or `SETOF` | `SELECT * FROM function(...)` | Row set |
| SQL statement | `SELECT/INSERT/UPDATE/DELETE` | JDBC query/update | `ResultSet` or update count |
| Trigger function | Function invoked by a trigger | Not usually called directly by app | Effects via DML/trigger |

Example procedure taking a quantity and returning remaining stock:

~~~sql
CALL reserve_stock('SKU-101', 3, NULL);
~~~

In PostgreSQL, `CALL` with output parameters returns **a single result row**. With `INOUT p_remaining integer`, the third argument is an input/output placeholder; passing `NULL` lets the procedure assign the output value via `UPDATE ... RETURNING`.

Example read-only function:

~~~sql
SELECT stock_total('SKU-');
~~~

**Do not invoke a PostgreSQL procedure via `SELECT reserve_stock(...)`**, and do not blindly invoke a function via `CALL stock_total(...)`. JDBC escape syntax `{call ...}` varies depending on driver and connection settings; in this lesson we use **native `CALL`** and **native `SELECT`** to avoid ambiguity.

### 3.1 IN, OUT, INOUT, and JDBC Drivers

- **IN:** caller passes an input value into the routine.
- **OUT:** routine returns an output value.
- **INOUT:** accepts an input and returns an output; in this example the input can be null, and after the routine it holds the remaining stock.
- JDBC parameter types must match PostgreSQL: `text`, `integer`, `bigint`, `numeric`, `uuid`, `jsonb`, etc.
- SQL `NULL` differs from the string `"null"`, and differs from Java `null` passed with an unspecified type; with overloaded procedures, type inference may require an explicit `CAST`.
- A `CALL` result set containing output parameters **does not mean** a procedure can arbitrarily return a multi-row table. To return multiple rows, use a `RETURNS TABLE` function or cursors depending on the engine.

### 3.2 Why Routines Cannot Be Copied Across Database Engines

PostgreSQL uses `LANGUAGE plpgsql` and dollar-quoted bodies `$$...$$`. MySQL uses `CREATE PROCEDURE ... BEGIN ... END` with client delimiter rules, SQL Server uses `CREATE OR ALTER PROCEDURE` and `EXEC`, and Oracle uses PL/SQL/packages and `REF CURSOR`. Parameter modes, transactions, exceptions, temporary tables, and `EXECUTE` privileges all differ.

**When a database-specific feature itself is under test, H2 compatibility mode cannot replace the real engine.** A passing H2 test may only prove SQL adapted for H2, not production migrations or driver behavior.

## 4. Which Test Support Does Spring Boot Provide?

### @JdbcTest

`@JdbcTest` belongs to `org.springframework.boot.test.autoconfigure.jdbc.JdbcTest` (Spring Boot 3.5.x). It focuses on **`DataSource`**, `JdbcTemplate`, the transaction manager, and related JDBC auto-configurations rather than loading the full web/server/service graph.

By default, `@JdbcTest`:

- May replace `DataSource` with an embedded database if found.
- Runs test methods inside a transaction and **rolls back after each test**.
- Does not scan all regular business `@Component`/`@Repository` beans as a full application does.
- Fits adapters that directly use `JdbcTemplate` or `NamedParameterJdbcTemplate`.

Because the example's production `@Repository InventoryGateway` needs to be tested for real, we use `@Import(InventoryGateway.class)` to include just that bean in the slice without loading the whole application.

### @DataJdbcTest

`@DataJdbcTest` targets **Spring Data JDBC repositories** along with JDBC infrastructure. It **differs from `@DataJpaTest`**: Spring Data JDBC does not use a Hibernate/JPA entity manager. If a project uses Spring Data JDBC `CrudRepository`, choose `@DataJdbcTest`; if it only uses `JdbcTemplate` + SQL/procedures, `@JdbcTest` is leaner.

### @SpringBootTest

`@SpringBootTest` loads a wider context suited for verifying service wiring, transactions, scheduling, or multiple layers. Do not reach for it by default just to test one SQL statement.

### @AutoConfigureTestDatabase

For database-specific code, use:

~~~java
@JdbcTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
class MyPostgresJdbcTest {
    // Connects to the real test database without replacing it with H2.
}
~~~

This is a **sample annotation** without a container or datasource yet. In the complete example, `@ServiceConnection` supplies JDBC connection details from a PostgreSQL Testcontainer.

**Avoid pointing tests at a production DB.** Never use production connection details for integration tests that run `DROP TABLE`, `TRUNCATE`, or rollbacks. Prefer containers or dedicated databases with isolated schemas and restricted privileges.

## 5. Testcontainers and @ServiceConnection: Why Are Both Needed?

**Testcontainers** starts a real PostgreSQL instance inside Docker/a container runtime for testing. **Spring Boot `@ServiceConnection`** consumes the container's connection metadata to build matching `JdbcConnectionDetails` for `DataSource`.

~~~text
JUnit Jupiter
    |
    v
@Testcontainers + @Container PostgreSQLContainer
    |
    v
PostgreSQL 16 (container runtime, random mapped port)
    |
    v
@ServiceConnection -> DataSource -> JdbcTemplate
    |
    v
@JdbcTest + @Import(InventoryGateway.class)
    |
    v
Production InventoryGateway -> native CALL / SELECT / JSONB / UPSERT
~~~

What Testcontainers helps verify:

- The PostgreSQL driver connects, sends bind parameters, and reads result sets from the real engine.
- PostgreSQL parses `CREATE PROCEDURE`/`PLpgSQL`, `JSONB`, and `ON CONFLICT` accurately.
- PostgreSQL-specific constraints/SQLSTATEs, transactions, and isolation behave as expected.
- Repeatable test data runs against a pinned image version.

What Testcontainers **does not automatically prove**: network proxies, production TLS/certificates, production role privileges, real/high-volume data sizes, HA/replication, and all concurrency races.

### 5.1 Pin Engine and Driver

For this example, use PostgreSQL 16 via image `postgres:16-alpine` with JDBC driver `org.postgresql:postgresql` managed by the Spring Boot BOM. Another release may differ in function/procedure behavior, JSONB indexing, or SQLSTATE codes for newer features.

Whenever production upgrades PostgreSQL major versions, run integration tests against the target version before deploying.

### 5.2 Docker Is a Practical Prerequisite

Testcontainers requires Docker Engine or a compatible container runtime with permission to pull images and run containers. If CI lacks a runtime, tests will **fail to start**; never mistake that environment error for a "SQL assertion status". Separate fast unit tests that run everywhere from integration tests executed on container-capable CI runners.

## 6. Hands-On Exercise: Testing Both SQL Routines and Production Java Code

Build a mini inventory application:

~~~text
inventory_item
+----------+-----------+------------------------+
| sku      | available | attributes (jsonb)     |
+----------+-----------+------------------------+
| SKU-101  |         7 | {"origin":"VN"}        |
| SKU-102  |         4 | {"origin":"US"}        |
+----------+-----------+------------------------+

PROCEDURE reserve_stock(p_sku, p_quantity, INOUT p_remaining)
  -> check p_quantity > 0
  -> UPDATE ... WHERE available >= quantity
  -> return remaining after update
  -> raise error if SKU missing or insufficient stock

FUNCTION stock_total(p_prefix)
  -> SUM(available) or 0 if no rows

InventoryGateway (real Java)
  -> reserve(): CALL reserve_stock
  -> totalAvailable(): SELECT stock_total
  -> upsert(): INSERT ... ON CONFLICT ... RETURNING
  -> findByAttributes(): JSONB @> CAST(? AS jsonb)
~~~

**Testing goal:** the procedure and function run **for real inside PostgreSQL**, the gateway is **real** production code, and tests vary **fixture data** without mocking JDBC.

### 6.1 File Structure

~~~text
src/
  main/
    java/example/pgsql/
      InventoryApplication.java
      InventoryGateway.java
  test/
    java/example/pgsql/
      PostgreSqlInventoryTest.java
~~~

All Java sources belong to `package example.pgsql;`. The test lives under the same package hierarchy as the root `@SpringBootApplication` so Boot locates the primary configuration.

### 6.2 Gradle Dependencies

In a **Spring Boot 3.5.x** project already configured with the Boot Gradle plugin, dependency management, and Java 17 toolchain, add to `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'

    testRuntimeOnly 'org.postgresql:postgresql'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is a **configuration snippet**, not a complete Gradle build file. The Spring Boot BOM should manage starter, driver, and Testcontainers versions. `testRuntimeOnly` fits the driver here because test code does not reference pgjdbc classes directly; a deployed production application needs the driver on its runtime classpath per deployment config.

For a project using only JDBC repositories, `spring-boot-starter-data-jpa` and Hibernate are unnecessary. Adding JPA just to test procedures adds startup and auto-configuration overhead without producing the needed evidence.

## 7. Production Java: InventoryApplication.java

~~~java
package example.pgsql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InventoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
~~~

This class serves as the primary configuration so Spring Boot scans the right package. A standalone production app needs external `spring.datasource.*`/secrets and migrations to create the schema; the tests avoid production connections because `@ServiceConnection` provides the PostgreSQL container.

## 8. Production Java: InventoryGateway.java

~~~java
package example.pgsql;

import java.util.List;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class InventoryGateway {

    private final JdbcTemplate jdbc;

    public InventoryGateway(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /**
     * Calls a PostgreSQL procedure with an INOUT parameter:
     * p_sku and p_quantity are IN; p_remaining is INOUT.
     * CALL with an output parameter returns a single result row.
     */
    public int reserve(String sku, int quantity) {
        Integer remaining = jdbc.queryForObject(
                "CALL reserve_stock(?, ?, NULL)",
                Integer.class,
                sku, quantity);

        return Objects.requireNonNull(
                remaining, "procedure returned null remaining");
    }

    /** Calls a PostgreSQL scalar function via SELECT. */
    public long totalAvailable(String prefix) {
        Long total = jdbc.queryForObject(
                "SELECT stock_total(?)",
                Long.class, prefix);
        return Objects.requireNonNull(
                total, "function returned null total");
    }

    /** PostgreSQL UPSERT + RETURNING brings new stock back to Java. */
    public int upsert(String sku, int increment) {
        Integer next = jdbc.queryForObject("""
                INSERT INTO inventory_item(
                    sku, available, attributes)
                VALUES (?, ?, '{}'::jsonb)
                ON CONFLICT (sku)
                DO UPDATE SET
                    available =
                        inventory_item.available + EXCLUDED.available
                RETURNING available
                """, Integer.class, sku, increment);

        return Objects.requireNonNull(
                next, "UPSERT returned null available");
    }

    /** JSONB containment operator, binding JSON via CAST(? AS jsonb). */
    public List<String> findByAttributes(String jsonFilter) {
        return jdbc.query("""
                SELECT sku
                FROM inventory_item
                WHERE attributes @> CAST(? AS jsonb)
                ORDER BY sku
                """,
                (rs, rowNum) -> rs.getString("sku"),
                jsonFilter);
    }

    /** Reads stock to assert routine/upsert side effects. */
    public int available(String sku) {
        Integer value = jdbc.queryForObject("""
                SELECT available
                FROM inventory_item
                WHERE sku = ?
                """, Integer.class, sku);

        return Objects.requireNonNull(
                value, "row has null available");
    }
}
~~~

Key points:

- `reserve` uses **native PostgreSQL `CALL`** and reads a single result row from the `INOUT` parameter, avoiding assumptions that JDBC escape syntax `{call...}` selects `CALL` across every driver.
- `totalAvailable` invokes the function with `SELECT`.
- `upsert` uses `ON CONFLICT (sku) DO UPDATE ... RETURNING available`, exercising both insert and update branches.
- `findByAttributes` binds `?` as a parameter instead of concatenating client JSON filters into SQL strings; `@>` is PostgreSQL's `jsonb` containment operator.
- `available` is a state-reading helper so tests verify **real side effects** of the procedure. It also uses parameter binding rather than concatenating SKU into the query.
- `Objects.requireNonNull` prevents silent null auto-unboxing into confusing errors; in production you may swap in domain exceptions or `Optional` per contract.

**Security note:** parameter binding prevents SQL injection in **values**, yet does not protect dynamic identifiers (table names, column names, ORDER BY), `EXECUTE` permission rules, or oversized JSON filters. Whitelist identifiers and validate inputs at the API/service boundary.

## 9. Complete Test Java: PostgreSqlInventoryTest.java

The test uses `@JdbcTest` + `@Import(InventoryGateway.class)` to test the real production gateway, `@Testcontainers` + `@ServiceConnection` for real PostgreSQL, and `@AutoConfigureTestDatabase(replace=NONE)` to avoid replacing it with H2.

**Fixtures and routines for this exercise** are created with `JdbcTemplate.execute(...)` inside `@BeforeEach`. Each `CREATE TABLE`/`CREATE PROCEDURE`/`CREATE FUNCTION` is sent as **one verbatim SQL statement** to PostgreSQL because `$$...;...$$` bodies contain internal semicolons. Do not pass them through a `@Sql` script with the default splitter that could split the routine mid-body on a semicolon.

~~~java
package example.pgsql;

import java.sql.SQLException;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

@JdbcTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(InventoryGateway.class)
@Testcontainers
@DisplayName("JDBC integration: PostgreSQL procedure/function/JSONB")
class PostgreSqlInventoryTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    InventoryGateway gateway;

    @BeforeEach
    void setUp() {
        jdbc.execute("""
                CREATE TABLE inventory_item (
                    sku text PRIMARY KEY,
                    available integer NOT NULL
                        CHECK (available >= 0),
                    attributes jsonb NOT NULL
                        DEFAULT '{}'::jsonb
                )
                """);

        jdbc.execute("""
                CREATE OR REPLACE PROCEDURE reserve_stock(
                    IN p_sku text,
                    IN p_quantity integer,
                    INOUT p_remaining integer
                )
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF p_quantity IS NULL
                       OR p_quantity <= 0 THEN
                        RAISE EXCEPTION
                            'quantity must be positive'
                            USING ERRCODE = '22023';
                    END IF;

                    UPDATE inventory_item
                    SET available = available - p_quantity
                    WHERE sku = p_sku
                      AND available >= p_quantity
                    RETURNING available INTO p_remaining;

                    IF NOT FOUND THEN
                        RAISE EXCEPTION
                            'missing SKU or insufficient stock'
                            USING ERRCODE = 'P0001';
                    END IF;
                END;
                $$;
                """);

        jdbc.execute("""
                CREATE OR REPLACE FUNCTION stock_total(
                    p_prefix text
                )
                RETURNS bigint
                LANGUAGE sql
                STABLE
                AS $$
                    SELECT COALESCE(SUM(available), 0)
                    FROM inventory_item
                    WHERE sku LIKE p_prefix || '%'
                $$;
                """);

        jdbc.update("""
                INSERT INTO inventory_item(
                    sku, available, attributes)
                VALUES (?, ?, CAST(? AS jsonb))
                """,
                "SKU-101", 7, "{\"origin\":\"VN\",\"fragile\":false}");

        jdbc.update("""
                INSERT INTO inventory_item(
                    sku, available, attributes)
                VALUES (?, ?, CAST(? AS jsonb))
                """,
                "SKU-102", 4, "{\"origin\":\"US\",\"fragile\":true}");
    }

    @Test
    @DisplayName("CALL INOUT returns remaining and updates real row")
    void reserveReturnsRemainingAndUpdatesDatabase() {
        int remaining = gateway.reserve("SKU-101", 3);

        assertEquals(4, remaining);
        assertEquals(4, gateway.available("SKU-101"));
        assertEquals(4, gateway.available("SKU-102"));
    }

    @Test
    @DisplayName("Reserving entire remaining stock leaves zero")
    void exactReservationLeavesZero() {
        int remaining = gateway.reserve("SKU-101", 7);

        assertEquals(0, remaining);
        assertEquals(0, gateway.available("SKU-101"));
    }

    @Test
    @DisplayName("Zero quantity is rejected with SQLSTATE 22023")
    void zeroQuantityRaisesSqlState22023() {
        DataAccessException failure = assertThrows(
                DataAccessException.class,
                () -> gateway.reserve("SKU-101", 0));

        assertSqlState(failure, "22023");
        // PostgreSQL transaction is now marked aborted.
        // Do not send further DB queries in this test method.
    }

    @Test
    @DisplayName("Insufficient stock raises business error SQLSTATE P0001")
    void insufficientStockRaisesDomainSqlState() {
        DataAccessException failure = assertThrows(
                DataAccessException.class,
                () -> gateway.reserve("SKU-101", 8));

        assertSqlState(failure, "P0001");
    }

    @Test
    @DisplayName("Missing SKU is also handled intentionally")
    void missingSkuRaisesDomainSqlState() {
        DataAccessException failure = assertThrows(
                DataAccessException.class,
                () -> gateway.reserve("DOES-NOT-EXIST", 1));

        assertSqlState(failure, "P0001");
    }

    @Test
    @DisplayName("SELECT function: sums accurately and empty set returns 0")
    void functionReturnsExpectedTotals() {
        assertEquals(11L, gateway.totalAvailable("SKU-"));
        assertEquals(0L, gateway.totalAvailable("UNKNOWN-"));
    }

    @Test
    @DisplayName("ON CONFLICT updates row and RETURNING matches")
    void upsertConflictBranch() {
        int next = gateway.upsert("SKU-101", 3);

        assertEquals(10, next);
        assertEquals(10, gateway.available("SKU-101"));
    }

    @Test
    @DisplayName("UPSERT insert branch creates a new SKU")
    void upsertInsertBranch() {
        int next = gateway.upsert("SKU-NEW", 2);

        assertEquals(2, next);
        assertEquals(2, gateway.available("SKU-NEW"));
    }

    @Test
    @DisplayName("JSONB containment @> and CAST bind parameter")
    void jsonbFilterFindsOnlyMatchingSku() {
        List<String> result = gateway.findByAttributes(
                "{\"origin\":\"VN\"}");

        assertEquals(List.of("SKU-101"), result);
        assertEquals(List.of(),
                gateway.findByAttributes("{\"origin\":\"FR\"}"));
    }

    @Test
    @DisplayName("JSON filter with quotes is not interpreted as SQL")
    void jsonFilterIsBoundAsValue() {
        List<String> result = gateway.findByAttributes(
                "{\"origin\":\"VN' OR '1'='1\"}");

        assertTrue(result.isEmpty());
        assertEquals(11L, gateway.totalAvailable("SKU-"));
    }

    @Test
    @DisplayName("Unique key violation raises SQLSTATE 23505")
    void duplicateSkuViolatesUniqueConstraint() {
        DataAccessException failure = assertThrows(
                DataAccessException.class,
                () -> jdbc.update("""
                        INSERT INTO inventory_item(
                            sku, available, attributes)
                        VALUES (?, ?, '{}'::jsonb)
                        """,
                        "SKU-101", 1));

        assertSqlState(failure, "23505");
        // Do not query further because the PostgreSQL transaction is aborted.
    }

    private static void assertSqlState(
            Throwable failure, String expected) {
        Throwable current = failure;

        while (current != null) {
            if (current instanceof SQLException sql
                    && expected.equals(sql.getSQLState())) {
                return;
            }
            current = current.getCause();
        }

        fail("Expected SQLSTATE " + expected, failure);
    }
}
~~~

**Total: 11 JUnit Jupiter `@Test` methods.** They use the real repository/gateway and real PostgreSQL. `SKU-101` starts with 7 units and `SKU-102` with 4; tests verify both the routine's returned output and **accurate state updates**.

### 9.1 Why Create the Schema and Procedures in @BeforeEach?

With `@JdbcTest`, Spring TestContext starts a test transaction before JUnit Jupiter `@BeforeEach` callbacks and rolls back after each test by default. **PostgreSQL supports transactional DDL**, so tables, procedures, and functions created inside the test transaction disappear upon rollback. The next test builds a fresh fixture from scratch.

This approach keeps the standalone example simple, though it does not replace how production deploys schemas. Production should manage DDL via **Flyway/Liquibase**, with versioning and forward/rollback migration policies. On a database engine that **does not fully support DDL rollback**, `CREATE TABLE` in `@BeforeEach` can persist across tests; use isolated schemas, migrations, and explicit cleanup.

**Do not run test methods in parallel** against the same schema when they share fixed table/routine names, unless each test gets its own schema or database. Even when transaction rollback isolates row data, concurrent DDL and locks still cause races.

### 9.2 Why Not Query the DB Right After Catching an Error?

PostgreSQL enforces an important rule: **after a SQL error inside the current transaction, the transaction is marked aborted**. Even though `assertThrows` caught the Java exception, PostgreSQL rejects any subsequent SQL statement with an error like:

~~~text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
SQLSTATE 25P02
~~~

Hence in `zeroQuantityRaisesSqlState22023`, `insufficientStockRaisesDomainSqlState`, and `duplicateSkuViolatesUniqueConstraint`, the test checks SQLSTATE and finishes. Spring's post-method test transaction rollback clears the aborted state.

If you need to assert "after the error, the database contains no partial changes", **end the failed transaction first**, then open a new transaction/connection to observe. Never run `SELECT` on the aborted transaction itself. Section 13 explains how to test atomicity and rollback properly.

### 9.3 Why Is SQLSTATE Better Than Exact Error Text?

`getSQLState()` gives a meaningful driver/DB error code that is far more stable than messages containing SQL, localization, parameter values, or implementation details.

In this example:

| SQLSTATE | Meaning |
| --- | --- |
| `22023` | PostgreSQL `invalid_parameter_value`, raised by the routine for `quantity <= 0` |
| `P0001` | `raise_exception`, raised by the routine for missing SKU or insufficient stock |
| `23505` | `unique_violation` on the primary key |
| `25P02` | Transaction is already aborted, rejecting subsequent SQL |

**Note:** SQLSTATE also includes **vendor-specific codes**; do not map it to a "universal cross-database enum" without testing each driver. If the app maps `P0001` to `OutOfStockException`/HTTP 409, add tests for that service/error-translation layer too.

### 9.4 Why Not Test with Mocks?

If you mock `JdbcTemplate` and stub `queryForObject` to return `4`, the test will miss:

- Wrong `CALL` routine name or missing `INOUT` argument.
- `PostgreSQLContainer` schema incompatibility.
- Invalid `JSONB @>` query syntax.
- `ON CONFLICT` failing to match the unique key.
- Missing DB constraints in migrations.
- Driver returning a different SQLSTATE than expected.

Unit tests can verify Java mapping/exception translation, yet **never replace database integration tests** when vendor-specific SQL itself must be guaranteed.

## 10. How to Run and Expected Output

In the project directory configured with Spring Boot 3.5.x and Java 17+:

~~~bash
./gradlew test --tests example.pgsql.PostgreSqlInventoryTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.pgsql.PostgreSqlInventoryTest
~~~

Requirements:

- Docker or a compatible container runtime running, with CI account permissions.
- Ability to pull `postgres:16-alpine`; the first run may require internet access.
- Java 17+ and compatible Gradle wrapper/Boot plugin and dependency versions.
- Test classes in the proper package/path, with no other test datasource overriding `@ServiceConnection`.

**Expected outcome:** JUnit Jupiter discovers **11 tests** and all PASS, with Gradle reporting `BUILD SUCCESSFUL`. This is **the expected design outcome**, not observed Gradle stdout captured in this article. Startup logs, mapped container ports, SQL debug statement counts, and execution times are not fixed.

If the container fails to start, read the root cause (unreachable Docker socket, image pull failure, resource limits); do not mistake that environment issue for a stored-procedure assertion bug. If tests cannot find `InventoryApplication`, verify the package hierarchy and Boot configuration.

## 11. When to Use SimpleJdbcCall?

Spring JDBC provides `SimpleJdbcCall` to invoke stored procedures and functions via metadata and/or explicit parameter declarations. It shines when procedures take many parameters, have multiple `OUT` parameters, or when an application standardizes routine invocations.

Illustrative example of a **typical stored procedure** (not a standalone file and **not guaranteed to run verbatim across every JDBC driver**):

~~~java
SimpleJdbcCall call = new SimpleJdbcCall(jdbcTemplate)
        .withProcedureName("reserve_stock")
        .withoutProcedureColumnMetaDataAccess()
        .declareParameters(
                new SqlParameter("p_sku", Types.VARCHAR),
                new SqlParameter("p_quantity", Types.INTEGER),
                new SqlInOutParameter("p_remaining", Types.INTEGER));

Map<String, Object> result = call.execute(
        Map.of(
                "p_sku", "SKU-101",
                "p_quantity", 3,
                "p_remaining", 0));
~~~

Requires imports from `org.springframework.jdbc.core.simple.SimpleJdbcCall`, `org.springframework.jdbc.core.SqlParameter`, `org.springframework.jdbc.core.SqlInOutParameter`, `java.sql.Types`, and `java.util.Map`. With PostgreSQL, the **driver's call escape mode** and how `INOUT`/output parameters are registered affect how `SimpleJdbcCall` sends SQL and reads outputs.

- Metadata lookup can miss parameters, reorder them, or be schema-sensitive; use `withoutProcedureColumnMetaDataAccess()` and declare parameters explicitly when clarity is needed.
- The PostgreSQL JDBC driver offers the `escapeSyntaxCallMode` connection property, controlling whether JDBC escape syntax translates to `SELECT` or `CALL`.
- If production uses `SimpleJdbcCall`, **integration tests must invoke the application's actual `SimpleJdbcCall`**, rather than swapping in native SQL in tests and assuming the wrapper works.
- When native `CALL ...` via `JdbcTemplate` is simple, testable, and fits the goal, do not add extra abstraction merely because the API exists.

### 11.1 Distinguishing CallableStatement

Plain JDBC offers `CallableStatement`:

~~~java
Connection connection = ...;
CallableStatement call =
        connection.prepareCall("{call some_procedure(?, ?)}");
call.setString(1, "SKU-101");
call.registerOutParameter(2, Types.INTEGER);
call.execute();
int value = call.getInt(2);
~~~

This is an **illustrative skeleton** missing connection lifecycle management, matching procedure DDL, and exception handling. Inside Spring JDBC, execute it via `JdbcTemplate.execute(ConnectionCallback)`/`CallableStatementCallback` so Spring manages connections, exception translation, and transactions.

Never copy a `{call...}` snippet from SQL Server straight into PostgreSQL assuming the driver always translates it cleanly. Consult pgjdbc docs on `escapeSyntaxCallMode=callIfNoReturn` whenever procedures with `OUT/INOUT` misbehave.

## 12. Functions Returning One Value, Multiple Rows, or Refcursors

Our `stock_total` function returns a `bigint` aggregate. Not every function returns a scalar:

| Result | PostgreSQL | Typical Java API |
| --- | --- | --- |
| Scalar | `RETURNS bigint` | `queryForObject("SELECT fn(?)", Long.class, ...)` |
| Single record/composite | `RETURNS record` / custom type | Specific `ResultSet` mapping |
| Multiple rows | `RETURNS TABLE(...)` or `SETOF` | `jdbc.query("SELECT * FROM fn(?)", rowMapper, ...)` |
| Cursor | `refcursor` | Driver-specific handling, often requires active transaction |
| No result set | `CALL procedure_without_out(...)` | `JdbcTemplate.update/execute` per JDBC behavior |

For table-returning functions, assert **row count, order (if `ORDER BY` is present), types, nullability, and filtering**. Never assume the database returns rows in insertion order when the query lacks `ORDER BY`.

For `refcursor`, drivers require the session/transaction to remain open while fetching the cursor. A test "passing on H2" usually fails to reproduce PostgreSQL/Oracle cursor semantics. Test using the exact driver and ensure resource cleanup.

## 13. Transactions, Rollback, and Atomicity Understood Accurately

### 13.1 Default Test Rollback Is Not a Production Commit

`@JdbcTest` runs tests transactionally and rolls back at the end. While convenient for fixtures, it **does not prove a production transaction commits cleanly** via another service or connection.

A procedure can execute an `UPDATE` inside the open test transaction; reading the row back sees the change before rollback removes it. That proves the **UPDATE logic works**, not that commits persist across restarts.

### 13.2 When Can a PostgreSQL Procedure Issue Its Own COMMIT?

PostgreSQL allows procedures to perform transaction control (`COMMIT`/`ROLLBACK`) **only when `CALL` runs at top level outside an explicit transaction block**. A procedure containing `COMMIT` will fail to run as expected if called inside `@JdbcTest`'s test transaction.

If a production routine manages its own transactions:

- Do not call it from a default transactional test method.
- Use `@Transactional(propagation = Propagation.NOT_SUPPORTED)` to disable Spring TestContext's transaction for that test.
- Initialize schemas/fixtures explicitly and clean up afterward since automatic rollback is off.
- Ensure the test database is dedicated and never production.
- Assert post-commit/rollback behavior via **another connection** with the proper isolation level.

In our example, `reserve_stock` has **no** internal `COMMIT/ROLLBACK`, so it runs inside Spring's test transaction.

### 13.3 Atomic Updates and Preventing Overselling

The procedure uses a single statement:

~~~sql
UPDATE inventory_item
SET available = available - p_quantity
WHERE sku = p_sku
  AND available >= p_quantity
RETURNING available INTO p_remaining;
~~~

The `available >= p_quantity` check lives **inside the UPDATE itself**; database row locking and re-evaluation per transaction semantics prevent concurrent statements from driving stock negative. This is far safer than "SELECT available in Java → if enough, UPDATE", where two concurrent requests can read the same stale stock.

Still, a **single-threaded** unit or integration test cannot prove the absence of lost updates under concurrent execution. Write a **concurrency test** with at least two real connections, synchronization barriers to coordinate timing, finite timeouts, and post-commit assertions.

### 13.4 How to Test Rollback After a Procedure Throws an Exception

To check that the DB rolled back cleanly, do not write:

~~~java
// Wrong inside the same PostgreSQL transaction after a SQL error:
assertThrows(DataAccessException.class,
        () -> gateway.reserve("SKU-101", 99));
assertEquals(7, gateway.available("SKU-101"));
~~~

Because the transaction is already aborted, the final `SELECT` fails with SQLSTATE `25P02`, even though the row itself never changed.

Correct principle-level sequence:

1. Use a dedicated test database and seed data in a **committed transaction**.
2. Start **a new transaction**, perform changes, and call the failing procedure.
3. Roll back the failed transaction.
4. Open **a new connection/transaction** and query stock to confirm no partial state remains.
5. Clean up fixtures via an independent transaction/schema.

When using `TransactionTemplate`, remember the exception must escape the callback or call `setRollbackOnly()`. On PostgreSQL, merely catching the exception and issuing more SQL in the same transaction does not heal the transaction; you must roll back and start a new one.

## 14. Error Verification: Exception Translation and SQLSTATE

`JdbcTemplate` uses Spring's `SQLExceptionTranslator` to map many `SQLException`s into `DataAccessException` subclasses. Exact subclassing can vary by database, driver, and version, whereas the root cause normally retains the SQLSTATE.

Example:

~~~java
DataAccessException thrown = assertThrows(
        DataAccessException.class,
        () -> gateway.reserve("SKU-101", 0));

assertSqlState(thrown, "22023");
~~~

Here `assertSqlState` is the helper defined in section 9's runnable file.

**Why not assert exact message text?**

- Messages may be localized or include server-specific details.
- Drivers may wrap the message with SQL/parameters.
- `RAISE EXCEPTION` wording can change in future routine versions.
- Messages can expose sensitive details if raw SQL/parameters appear in public logs.

If the application translates `P0001` to a custom domain exception, unit tests can check that translation, while database tests verify the underlying SQLSTATE. Avoid relying solely on `getMessage().contains("inventory")` to identify business conflicts.

### 14.1 Errors When a PostgreSQL Transaction Aborts

After a SQL exception:

~~~text
SQLSTATE 22023 / P0001 / 23505   <-- original error
SQLSTATE 25P02                   <-- secondary error on continued querying
~~~

Never report "the database returned the wrong error" if the second statement receives `25P02`; that indicates the test reused an un-rolled-back transaction.

### 14.2 Negative Cases to Test

| Scenario | Expected Outcome |
| --- | --- |
| Quantity = 0 or negative | Input error `22023`, no reservation occurs |
| Missing SKU | `P0001` error per routine |
| Quantity exceeds stock | `P0001` error; stock is not deducted |
| Duplicate SKU on regular INSERT | `23505` unique violation |
| Invalid JSON in `attributes` | PostgreSQL reports JSON cast error with matching driver/vendor SQLSTATE |
| SQL user lacks EXECUTE privilege | Permission denied / SQLSTATE `42501` under matching role |
| Routine signature changed | Driver/DB reports missing routine or parameter mismatch |
| Query deadline too low | Timeout/cancellation; never assume DB rollback undoes external side effects |
| Connection drop | Connection-level exception; handle retries/idempotency per policy |

When testing SQL exceptions, use a separate transaction **for each failure case** rather than trying to run multiple failing cases inside one aborted transaction.

## 15. PostgreSQL JSONB: Testing the Right Operators and Data Types

PostgreSQL `JSONB` is not a `VARCHAR` holding raw JSON text. It is a dedicated type with parsing, indexing, and operators:

~~~sql
SELECT sku
FROM inventory_item
WHERE attributes @> '{"origin":"VN"}'::jsonb;
~~~

`@>` asks whether the left JSON structure contains the right JSON structure under PostgreSQL containment semantics. Given:

~~~json
{"origin":"VN","fragile":false}
~~~

the filter `{"origin":"VN"}` matches, while `{"origin":"US"}` does not.

In Java, to prevent SQL injection, code uses:

~~~java
jdbc.query("""
    SELECT sku
    FROM inventory_item
    WHERE attributes @> CAST(? AS jsonb)
    ORDER BY sku
    """, rowMapper, jsonFilter);
~~~

With the PostgreSQL JDBC driver, binding a string to `?` and using `CAST(... AS jsonb)` lets the database parse it cleanly as JSONB. Never construct SQL via:

~~~java
// Wrong: concatenating untrusted input into SQL.
String sql = "SELECT sku FROM inventory_item WHERE attributes @> '"
        + userJson + "'::jsonb";
~~~

Tests should cover **both valid JSON filters and inputs containing quotes**; `jsonFilterIsBoundAsValue()` passes `' OR ...`, yet it remains strictly a JSON string value rather than becoming a SQL condition.

**Limitation:** bind parameters protect SQL syntax, yet they do not validate JSON against a business schema or block oversized payloads. Production systems should enforce depth/size limits and schema validation on client-supplied JSON.

### 15.1 Indexes and Performance

PostgreSQL can often accelerate `jsonb` containment queries with a GIN index:

~~~sql
CREATE INDEX idx_inventory_attributes
ON inventory_item
USING GIN (attributes);
~~~

This is PostgreSQL DDL, omitted from the runnable fixture because our focus is correctness rather than benchmarking. A filter test returning matching records **does not prove** the query hits the index or scales to a million rows. Whenever performance matters, inspect `EXPLAIN (ANALYZE, BUFFERS)` against a production-like dataset and DB.

## 16. UPSERT, RETURNING, and the Boundary Between Update Count and Result Set

PostgreSQL supports:

~~~sql
INSERT INTO inventory_item(sku, available, attributes)
VALUES ('SKU-101', 3, '{}'::jsonb)
ON CONFLICT (sku)
DO UPDATE SET
  available = inventory_item.available + EXCLUDED.available
RETURNING available;
~~~

In the example, `SKU-101` starts with `available=7`, so the conflict branch returns **10**. For a brand-new `SKU-NEW`, the insert branch returns **2**.

**Common Spring JDBC pitfall:** because the SQL includes `RETURNING`, it **returns a `ResultSet`**. `JdbcTemplate.queryForObject(...)` reads the returned value; never call `jdbc.update(...)` expecting the new stock amount. `update(...)` returns **affected row count**, not the `available` column.

To thoroughly verify insert/update side effects:

- Assert the value returned by `RETURNING`.
- Query the row afterward with `SELECT` in the same transaction.
- Verify the underlying unique key/constraint.
- Test the conflict branch with an existing key, not only the insert branch.
- Test overflow or negative increments if business rules allow or restrict them.

If `increment` is negative, `CHECK (available >= 0)` stops stock from dropping below zero as an independent constraint. If business rules forbid decreasing stock via upsert altogether, the service must validate inputs explicitly—never assume PostgreSQL forbids negative increments as long as the sum stays `>= 0`.

## 17. Schema Management: Flyway, Liquibase, and SQL Scripts

In production systems, stored procedures and functions must be **version-controlled** just like Java code. Example Flyway migrations:

~~~text
src/main/resources/db/migration/
  V1__create_inventory_item.sql
  V2__reserve_stock_procedure.sql
  V3__stock_total_function.sql
  V4__inventory_constraints_and_indexes.sql
~~~

The example test defines routines inside `@BeforeEach` to remain **self-contained and readable**. However, production integration tests should run real migrations on the PostgreSQL container rather than maintaining **two diverging copies of DDL**. If tests spin up a "neat" hand-crafted procedure while real migrations deploy a broken one, tests pass misleadingly.

### 17.1 Dollar Quoting and Script Splitting

PostgreSQL PL/pgSQL uses:

~~~sql
CREATE OR REPLACE PROCEDURE demo()
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'hello';
END;
$$;
~~~

The body contains internal semicolons. A SQL runner that splits statements on every semicolon **without understanding dollar-quoting** will slice the script in the middle of `BEGIN ... END`. Flyway and Liquibase handle PostgreSQL routine scripting when configured appropriately. With Spring `@Sql`/`ScriptUtils`, complex scripts need a **custom separator** or verbatim `JdbcTemplate.execute` calls as shown in this lesson.

**Never set `spring.sql.init.mode=always` while simultaneously running Flyway migrations without clear ordering.** Tests may create the schema twice or attempt to load fixtures before migrations finish.

### 17.2 Separate Migration Verification

A solid integration suite can include:

- **Migration smoke test:** empty PostgreSQL container, run from V1 to current, verify tables, routines, and privileges exist.
- **Routine contract test:** invoke the real production gateway and assert outputs and side effects against the migrated schema.
- **Upgrade test:** migrate from an older schema version populated with historical data to the latest version, verifying data integrity and routine behavior.
- **Permission test:** run with an app role granted only required privileges rather than the container default superuser.
- **Rollback policy:** if a migration is non-reversible, ensure a forward-fix, backup, and recovery plan.

Testcontainers isolates the environment, yet **does not run migrations automatically** unless Flyway/Liquibase/SQL initialization is configured in the test context.

## 18. Testing Other Vendor-Specific Features: Prioritize by Risk

| Feature | Example Engine | Verify Directly |
| --- | --- | --- |
| `JSONB` | PostgreSQL | Containment operators, casts/binds, JSON paths/indexes, null semantics |
| `ON CONFLICT ... RETURNING` | PostgreSQL | Insert/conflict branches and returned values |
| `MERGE` | SQL Server/Oracle/PostgreSQL (version-dependent) | Matched/unmatched branches, triggers/locking |
| `INSERT ... ON DUPLICATE KEY UPDATE` | MySQL/MariaDB | Conflict rules, affected row counts, generated IDs |
| `OUTPUT INSERTED.*` | SQL Server | Result sets and trigger interactions |
| Stored procedures/PLSQL packages | Oracle | Parameter modes, cursors, exception mapping |
| `UPSERT` and `RETURNING` | Vendor-specific | ResultSet vs. update count, actual updated rows |
| `FOR UPDATE SKIP LOCKED` | PostgreSQL/Oracle/MySQL (version-dependent) | Two-transaction lock skipping, queue claiming |
| Advisory locks | PostgreSQL | Acquisition, release, session vs. transaction scope |
| Window functions | Various DBs | Partition/order/frame boundaries and edge rows |
| Generated columns, triggers | Various DBs | Server-generated values after INSERT/UPDATE |
| Collations/timezones/case folding | Engine-specific | Sorting and comparisons for Vietnamese, Unicode, timezones |
| Sequences/identity columns | Engine-specific | Generated key types, gaps, rollback behavior |

**Never force these tests onto H2** when the app relies on vendor-specific semantics. For engines other than PostgreSQL, swap in the matching container/driver and write SQL fixtures for that real engine.

### 18.1 Testing Locks Requires Multiple Connections

If production uses `SELECT ... FOR UPDATE SKIP LOCKED` to claim queued jobs, a single-connection test cannot prove "two workers never claim the same job". You need:

1. Seed one or more jobs and commit.
2. Transaction A locks a job and stays open.
3. Transaction B on an **independent connection** runs the same claim query.
4. Assert B skips A's locked job (or claims another job per contract).
5. Commit/roll back both, verify final state, and clean up.

Never use one `JdbcTemplate` on **the same thread and same Spring transaction** pretending it simulates two transactions. Use `TransactionTemplate` with explicit propagation or two threads/connections with synchronization barriers.

### 18.2 Testing Isolation, Deadlocks, and Retries

SQLSTATE codes for serialization failures or deadlocks may warrant bounded retries, yet **never retry every `DataAccessException`**. Retrying a stored procedure that triggered side effects (emails, external payments, sequence IDs) can duplicate actions. Tests should isolate **idempotency**, isolation levels, timeouts, retry counts, and error mapping in separate scenarios.

## 19. Testing Exceptions with Independent Transactions

When you need to assert DB state after a failed transaction, structure a dedicated test following this **conceptual pattern**:

~~~java
// Pseudocode inside an integration test with a configured test DB:
// 1. Seed and COMMIT in a separate transaction.
// 2. Execute the operation under test inside TransactionTemplate.
// 3. Let the exception escape the callback -> transaction rolls back.
// 4. Query via a NEW transaction/connection after rollback.
// 5. Assert pre/post state snapshots match.
~~~

This is **pseudocode**, not compilable Java. It is kept separate from `PostgreSqlInventoryTest` because that class uses default transaction rollback and creates its schema **inside each test's own transaction**. A `REQUIRES_NEW` transaction would not see uncommitted DDL or fixture rows from the outer transaction on PostgreSQL.

To test real rollback properly, use **migrations/schemas already committed before the test**, seed fixtures in a committed transaction, and then execute the failing transaction and verify post-rollback state. Understanding that commit ordering matters far more than sticking an `assertEquals` after `assertThrows` and hitting `25P02`.

### 19.1 Why Is TestTransaction Not the Only Tool?

Spring TestContext provides `TestTransaction` to flag, end, and restart test transactions. It helps in certain integration tests, yet requires understanding fixture lifecycles, committed DDL, and cleanup. You do not need `TestTransaction` in every test when standard `@JdbcTest` rollback suffices to test routine outputs and success paths.

Whenever production code actually relies on `@Transactional(propagation = REQUIRES_NEW)` or self-committing procedures, test **those exact semantics** in a context with a real transaction manager.

## 20. SQL Injection and EXECUTE Privileges

Depending on engine and configuration, a routine executes with caller or definer rights. In PostgreSQL:

- By default many functions/procedures execute as invoker; `SECURITY DEFINER` runs with definer privileges.
- `SECURITY DEFINER` can escalate privileges significantly; verify owner, `search_path`, schema qualification, and `REVOKE`/`GRANT` rules.
- `?` bind parameters bind **values**, not procedure, schema, or table names.
- Never construct `CALL ` + `userInput` + `(...)` or unquoted/un-whitelisted dynamic SQL inside routines.
- Ordinary tests connecting as the container's superuser **will not catch** missing `EXECUTE` grants on the production app role.
- A real permission test must create a least-privilege application role and connect with those credentials.

When routines use dynamic SQL inside PL/pgSQL, prefer `EXECUTE ... USING` for values and `format('%I', identifier)` when identifiers truly must be dynamic. Never log raw connection credentials, PII, or raw SQL outside test environments.

### 20.1 A Valid Function Result Does Not Prove Security

`SELECT stock_total('SKU-')` returning `11` as a superuser does not prove the app role is authorized to call the function. If business rules require row-level security, test with the real role/tenant context to verify `SELECT`/`CALL` obeys visibility rules. That verification is separate from aggregate correctness.

## 21. Common Mistakes When Testing Stored Procedures / DB Features

**1. Using H2 to validate PostgreSQL PL/pgSQL.**  
H2 does not faithfully emulate PostgreSQL procedures, JSONB, UPSERT, or transaction semantics. Use a PostgreSQL container whenever production runs PostgreSQL.

**2. Tests only stubbing the gateway's return value.**  
Mocks do not prove the routine exists, SQL is valid, or side effects occurred. Test the production adapter against real JDBC.

**3. Calling a PostgreSQL procedure with `SELECT proc(...)`.**  
`CREATE PROCEDURE` uses `CALL`; `CREATE FUNCTION` normally uses `SELECT`.

**4. Omitting output/`INOUT` parameters in `CALL`.**  
PostgreSQL `CALL` expects positional placeholders; `OUT` and `INOUT` modes behave differently. Check the exact signature.

**5. Assuming `{call ...}` always translates to `CALL`.**  
pgjdbc's `escapeSyntaxCallMode` changes how JDBC escape syntax maps based on connection settings. Use native `CALL` when testing procedures directly, or configure and test the driver explicitly.

**6. Calling `JdbcTemplate.update(...)` on SQL with `RETURNING` expecting the column value.**  
`update` returns affected row count, not the result column. Use `queryForObject` or `ResultSet` mapping.

**7. Failing to assert database state after a successful `CALL`.**  
Checking only the output parameter can miss an UPDATE hitting the wrong table or filter. Inspect actual rows.

**8. Catching an exception and running `SELECT` in an aborted PostgreSQL transaction.**  
After an error, PostgreSQL throws `25P02`. Roll back and open a fresh transaction.

**9. Calling a self-committing procedure inside `@JdbcTest`'s default transaction.**  
PostgreSQL forbids transaction control inside a procedure when `CALL` executes inside an explicit transaction block. Use a non-transactional test with explicit cleanup.

**10. Confusing SQLSTATE with error messages.**  
Messages shift across driver versions, locales, and versions; assert stable SQLSTATE codes and map them to domain errors cleanly.

**11. Using `ScriptUtils`/`@Sql` with the default `;` splitter on `$$` PL/pgSQL bodies.**  
Use a PostgreSQL-aware migration runner or a custom separator, never blindly splitting on every semicolon.

**12. Running tests in parallel on one schema with fixed `CREATE/DROP` names.**  
Causes races and lock contention; isolate schemas or run sequentially with proper rollback and cleanup.

**13. Assuming H2 rolls back DDL like PostgreSQL.**  
DDL rollback varies by engine; match your fixture strategy to the real DB.

**14. Assuming JSONB parameter binding needs no type cast.**  
The driver may bind as `varchar`, triggering operator/type mismatches. Use `CAST(? AS jsonb)` or an explicit type adapter.

**15. Concatenating JSON or ID inputs into SQL strings.**  
Creates SQL injection vulnerabilities. Bind values with `?`/named parameters and whitelist SQL identifiers.

**16. Testing only the INSERT branch of an UPSERT.**  
Misses the conflict clause, unique key matching, and `RETURNING` value after UPDATE.

**17. Skipping unique/foreign-key/check constraint tests.**  
A mocked repository happily returns "success" even when the production schema would reject the data.

**18. Using one connection and transaction to simulate concurrency.**  
Without two independent transactions, row-level locking and races are never tested.

**19. Assuming small PostgreSQL container tests prove production performance.**  
Indexes, query plans, cardinality, disk, vacuum, contention, and network latency matter enormously. Benchmark separately on production-like data.

**20. Skipping production migrations in the integration suite.**  
Hand-written test DDL can drift from production; test migrations and code against the same schema.

**21. Retrying every SQL exception blindly.**  
Unique violations and invalid quantities are not transient. Retry only appropriate transient errors under an idempotency policy.

**22. Omitting timeouts on lock/wait tests.**  
Blocked locks can hang CI indefinitely. Configure statement timeouts, test deadlines, and session cleanup.

## 22. Practical Test Design Workflow

1. **Inventory database-specific SQL:** procedures/functions, JSONB/arrays, UPSERT/RETURNING, locks/triggers/sequences.
2. **Pin features to the exact engine/version:** PostgreSQL 16, SQL Server 2022, Oracle, MySQL, etc.; test the matching dialect.
3. **Pick the test layer:** unit tests for Java rules; `@JdbcTest`/`@DataJdbcTest` for SQL; `@SpringBootTest` for service/transaction wiring.
4. **Use Testcontainers or an isolated test DB**, never production credentials.
5. **Run real migrations** when testing production contracts; use inline DDL only in small self-contained examples with documented limits.
6. **Build boundary fixtures:** zero, missing, insufficient, duplicate, valid/invalid JSON, conflict branches.
7. **Invoke the real production adapter**, not ad-hoc test SQL that skips Java mapping.
8. **Assert outputs AND side effects:** output params, return values, updated rows, constraints, and untouched rows.
9. **Assert SQLSTATE** on errors; never reuse an aborted PostgreSQL transaction.
10. **Verify rollback in a fresh transaction/connection** when atomicity is part of the contract, seeding in a committed transaction first.
11. **Write two-transaction tests** whenever features rely on locking or concurrency.
12. **Test restricted roles/permissions** when routines execute under special privilege rules.
13. **Keep tests deterministic:** pinned images, reset datasets, finite timeouts, no parallel runs sharing mutable DDL.
14. **Separate performance/SQL plan checks**, never substituting benchmarks for correctness.
15. **Report clearly in CI:** Docker runtime, DB image, migrations, versions, and verified code paths.

### Pre-Commit Checklist

- [ ] Only test stored procedures or vendor features actually used by the codebase.
- [ ] Run tests on the real DB engine rather than treating H2 compatibility mode as proof for PostgreSQL/Oracle/MySQL.
- [ ] Isolate the test database so production is never touched.
- [ ] Align DDL/migration versions with production, or explicitly document fixture limitations.
- [ ] Use `@JdbcTest` for `JdbcTemplate` and `@DataJdbcTest` for Spring Data JDBC.
- [ ] Point `@AutoConfigureTestDatabase(replace=NONE)`/`@ServiceConnection` cleanly to the PostgreSQL container.
- [ ] Invoke real production Java code rather than mocking the SQL adapter under test.
- [ ] Match `CALL`/`SELECT` and `OUT`/`INOUT` parameters to the routine signature.
- [ ] Assert both returned values and post-routine database state changes.
- [ ] Test invalid quantities, missing keys, insufficient stock, and constraint violations.
- [ ] Verify SQL exceptions via SQLSTATE without reusing an aborted transaction.
- [ ] If a routine performs internal `COMMIT`/`ROLLBACK`, do not force it inside an explicit test transaction block.
- [ ] Verify JSONB types and operators through the driver with parameter binding.
- [ ] Test both insert and conflict branches of UPSERT along with `RETURNING`.
- [ ] Test concurrency/locking, permissions, and migration upgrades separately where risk warrants.
- [ ] Configure timeouts, fixture reset/rollback, cleanup, and pinned CI versions.
- [ ] Never log secrets or run destructive DDL on shared environments.

**Summary:** stored procedures and database-specific features must be tested against **a real database** because the contract spans far more than Java return values: it covers SQL parsing, driver behavior, parameter types, transactions, output mapping, constraints, error codes, and side effects. In Spring Boot, `@JdbcTest` paired with PostgreSQL Testcontainers and the production gateway gives a focused setup. By thoroughly verifying **`CALL`/`SELECT`, `INOUT`, `JSONB`, `UPSERT`, SQLSTATE, rollback, and concurrency at the right layers**, tests catch bugs that mocks and H2 simply cannot expose.

### Official References

- [Spring Boot 3.5 — Auto-configured JDBC Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@JdbcTest`, `@DataJdbcTest`, transactional rollback, test database replacement.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection`, `PostgreSQLContainer`, and connection details.
- [Spring Framework — JdbcTemplate & SimpleJdbcCall](https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html): routine calls, stored procedure metadata, parameter declarations.
- [Spring Framework — Testing with @Sql](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): test scripts, separators, transactions, and script execution.
- [PostgreSQL 16 — CREATE PROCEDURE](https://www.postgresql.org/docs/16/sql-createprocedure.html): procedure signatures, PL/pgSQL, parameter modes.
- [PostgreSQL 16 — CALL](https://www.postgresql.org/docs/16/sql-call.html): output parameters, result rows, and transaction control restrictions.
- [PostgreSQL 16 — JSON Types](https://www.postgresql.org/docs/16/datatype-json.html): `jsonb` and data representation.
- [PostgreSQL 16 — JSON Functions and Operators](https://www.postgresql.org/docs/16/functions-json.html): `@>`, `->>`, and JSON operators.
- [PostgreSQL 16 — INSERT / ON CONFLICT / RETURNING](https://www.postgresql.org/docs/16/sql-insert.html): inserts, UPSERT, returned rows.
- [PostgreSQL 16 — Error Codes](https://www.postgresql.org/docs/16/errcodes-appendix.html): `22023`, `23505`, `25P02`, and `P0001`.
- [Testcontainers — PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/): starting PostgreSQL containers for integration tests.