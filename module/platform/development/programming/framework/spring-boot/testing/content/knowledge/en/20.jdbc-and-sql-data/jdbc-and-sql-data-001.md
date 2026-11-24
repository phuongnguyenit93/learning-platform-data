# @JdbcTest and Testing JdbcTemplate in Spring Boot

## 1. Goal: Testing Real SQL and JDBC in a Spring Test Slice

When a Spring Boot application accesses a database directly through `JdbcTemplate`, bugs usually lie in **SQL statements, parameters, data types, query results, record ordering, affected row counts, and database constraints**. A unit test using Mockito to mock `JdbcTemplate` can verify that a DAO calls a method with a certain SQL string, but it **does not prove** that the SQL executes on the database, that the real columns exist, or that the `RowMapper` reads the right types.

`@JdbcTest` is a Spring Boot **test slice** dedicated to **plain JDBC**. It creates a small Spring application context focused on `DataSource`, `JdbcTemplate`, JDBC transaction support, and appropriate database initialization parts. Typically, it uses an embedded database for tests and **automatically rolls back changes belonging to the test transaction** after each test.

This lesson helps you:
- Understand which beans are auto-configured and which beans are **not** loaded by `@JdbcTest` component scanning.
- Write a realistic DAO using `JdbcTemplate.update`, `query`, `queryForObject`, and `RowMapper`.
- Test insert/read/update/filter/sort, correctness of prepared-statement placeholders, missing records, and constraint violations.
- Distinguish real JDBC results from Mockito mocks, `@DataJdbcTest` (Spring Data JDBC), and `@DataJpaTest` (JPA/Hibernate).
- Control SQL schema/fixtures, test-managed transactions, rollback, and datasource replacement.
- Know when H2 is sufficient and when real PostgreSQL via Testcontainers is needed.

**Version scope for runnable code:** Java 17+, Spring Boot **3.5.x**, Spring Framework 6.x, Spring JDBC, JUnit Jupiter, and H2 2.x. The final section notes import/module changes in Spring Boot 4.x; do not mix test APIs from two major versions.

## 2. What Does @JdbcTest Auto-Configure?

A simple declaration:

```java
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;

@JdbcTest
class InventoryJdbcTest {
    // @Autowired JdbcTemplate jdbcTemplate;
}
```

This is only a declaration skeleton, not a standalone runnable test file. When initializing the test context, Spring Boot applies slice-specific filtering and JDBC-supporting auto-configurations.

High-level diagram:

```text
JUnit Jupiter
      |
      v
Spring TestContext + @JdbcTest
      |
      +---- DataSource + JDBC driver / connection pool
      +---- JdbcTemplateAutoConfiguration
      |       |
      |       +---- JdbcTemplate
      |       +---- NamedParameterJdbcTemplate (when appropriate)
      +---- JdbcClientAutoConfiguration (based on classpath)
      +---- DataSourceTransactionManager / JdbcTransactionManager
      +---- TestDatabaseAutoConfiguration
      +---- SQL initialization / migrations if enabled
      |
      +---- NOT included by default:
               @Service, @RestController,
               ordinary custom @Repository/@Component,
               JPA EntityManager, HibernateJpaAutoConfiguration,
               Spring Data JDBC repository auto-configuration
```

**Note:** This is the group of infrastructure allowed by the slice, not a guarantee that every bean appears unconditionally. The classpath, Boot version, datasource configuration, SQL initialization, and test `@Import` annotations determine the concrete context.

According to Boot 3.5's list of test slices, `@JdbcTest` typically imports auto-configurations related to `DataSource`, JDBC template/client, JDBC transaction manager, transaction support, test database, and SQL initialization; conditionally, it also includes Flyway/Liquibase and optional Testcontainers service connections. It **does not automatically import JPA repository or Spring Data JDBC repository auto-configurations** as other slices do.

### 2.1. Which Beans Are Selected and Which Need to Be Imported?

| Component | In @JdbcTest? | Meaning |
|---|---|---|
| `DataSource` | Usually present when database/driver is configured | Provides real JDBC connections |
| `JdbcTemplate` | Usually auto-configured | JDBC query, update, batch |
| `NamedParameterJdbcTemplate` | May be auto-configured when conditions match | Uses `:name` instead of `?` |
| `JdbcClient` | May be configured in Boot 3.x / newer Spring JDBC | Fluent JDBC API, not JPA |
| `PlatformTransactionManager` | Usually present per JDBC setup | Transaction and rollback for tests |
| Embedded H2/HSQLDB/Derby | When driver is present and test replacement opts in | Real database running in-process |
| Hand-written `@Repository` | **Not automatically scanned as in full app** | Use `@Import(InventoryJdbcDao.class)` to test the real DAO |
| Business `@Service` | Not by default | Separate unit/service integration test |
| `JpaRepository`, `EntityManager` | Not the target of this slice | Use `@DataJpaTest` |
| Spring Data JDBC repositories | Not the target of `@JdbcTest` | Use `@DataJdbcTest` |
| HTTP server/Controller | Not by default | Use MVC/WebFlux/HTTP integration test |

When a test needs a manual DAO like `InventoryJdbcDao`, the explicit approach is:

```java
@JdbcTest
@Import(InventoryJdbcDao.class)
class InventoryJdbcDaoTest {
    @Autowired InventoryJdbcDao dao;
}
```

Here `@Import` **intentionally loads a regular bean**, without turning the whole application into a full integration context. Conversely, when adding **an auto-configuration class** to a slice, Spring Boot guides you to use `@ImportAutoConfiguration` or an equivalent mechanism, rather than arbitrarily using `@Import` for an auto-configuration. Keep these two purposes clearly distinct.

## 3. Differences Between @JdbcTest, @DataJdbcTest, @DataJpaTest, and @SpringBootTest

| Test Type | Target | What It Verifies Well |
|---|---|---|
| JUnit + Mockito | Isolated Java code, dependency call decisions | Branching, constructed SQL strings, mapping logic when manually constructing a fake ResultSet |
| `@JdbcTest` | Plain JDBC with DataSource and JdbcTemplate | Real SQL, RowMapper, updated row counts, constraints |
| `@DataJdbcTest` | Spring Data JDBC repositories | Aggregate mapping and Spring Data JDBC repository behavior |
| `@DataJpaTest` | Spring Data JPA/Hibernate | Entity lifecycle, persistence context, JPQL, JPA repositories |
| `@SpringBootTest` | Broader context (service, repository, config...) | Multiple layers loaded for real |
| `@SpringBootTest(RANDOM_PORT)` | Real HTTP server + application | Requests over HTTP socket, controllers/filters/service/DB if used for real |

An application using `JdbcTemplate` **does not need JPA**. Therefore, if you want to test a `RowMapper` or JDBC queries, `@DataJpaTest` is not a sensible default choice: it brings Hibernate/JPA into the test unnecessarily. If you are using Spring Data JDBC aggregate repositories, `@DataJdbcTest` is the appropriate one, not `@JdbcTest`.

**Do not equate "JDBC" with "Spring Data JDBC".** `JdbcTemplate` is a direct API belonging to Spring JDBC; Spring Data JDBC is a completely different repository/aggregate abstraction.

## 4. Preparing a Runnable Java 17+ Project

The example uses an `inventory_items` table to test simple CRUD and real SQL queries. We intentionally **do not use JPA/Hibernate** and **do not mock JdbcTemplate**.

Contract to verify:

1. `INSERT` a product with ID, SKU, title, and stock quantity.
2. Find by SKU: return `Optional<ProductRow>` if present, or `Optional.empty()` if absent.
3. List products with quantity less than or equal to a threshold, ordered by SKU ascending.
4. `UPDATE` stock returns the exact affected row count.
5. SKU must be **unique**, quantity non-negative; violating SQL statements are rejected by the database.
6. An SKU containing quotes and SQL-like strings is still bound as **data**, not injected into SQL structure.
7. `JdbcTemplate.queryForObject` and `query` behave differently when no record is found.
8. Records created in a test are **rolled back**, not polluting other tests.

### 4.1. File Structure

```text
build.gradle
src/main/java/com/example/jdbcslice/
    JdbcSliceApplication.java
    ProductRow.java
    InventoryJdbcDao.java
    InventoryService.java
src/test/resources/sql/
    inventory-schema.sql
src/test/java/com/example/jdbcslice/
    InventoryJdbcDaoTest.java
```

Place tests under the same root package `com.example.jdbcslice` so Spring Boot can locate the application configuration for test bootstrapping.

### 4.2. build.gradle Using a Specific Boot 3.5.x Version

File `build.gradle` (Gradle Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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

    testRuntimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot **3.5.8** is a concrete release of the 3.5 line, giving the example explicit plugin coordinates. For a project with newer security fixes or different version policies, update **in sync with the Boot BOM** rather than mixing starters/JUnit/Spring jars from multiple major versions.

If using Maven, you need `spring-boot-starter-parent` or an appropriate BOM, `spring-boot-starter-jdbc`, `spring-boot-starter-test`, and H2 in test scope; Surefire needs to support JUnit Jupiter. The `./gradlew`/`./mvnw` commands in section 6 assume the wrapper exists in the repo; `build.gradle` does not generate the Gradle wrapper by itself.

**Why is H2 `testRuntimeOnly`?** `@JdbcTest` needs H2 for tests, but a production application should not automatically carry H2 on the runtime classpath just for a lesson. Here the sample application does not run a web server or have its own production datasource; its goal is to run a **JDBC slice test**.

### 4.3. Application Class

File `src/main/java/com/example/jdbcslice/JdbcSliceApplication.java`:

```java
package com.example.jdbcslice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JdbcSliceApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdbcSliceApplication.class, args);
    }
}
```

This is a standard application configuration, but when running `@JdbcTest`, Spring Boot **restricts auto-configuration to the slice**, without starting an HTTP server or all services. Do not run `main` to test JDBC; run the test class directly.

### 4.4. Creating a Real SQL Schema

File `src/test/resources/sql/inventory-schema.sql`:

```sql
CREATE TABLE inventory_items (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    title VARCHAR(160) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);
```

This schema works with modern H2 and PostgreSQL for the types and constraints used. In the example we **supply IDs manually** to avoid depending on identity/sequence dialects and to focus on `JdbcTemplate`; no `@Entity` or Hibernate DDL is used.

The `CREATE TABLE` statement is executed by the Spring SQL script initializer **once when the application context starts**, not re-run after every `@Test`. Because tests roll back by default, inserted/updated rows from each test are cleaned up when the transaction ends. DDL/schema is context infrastructure, not part of per-test fixture rollback.

We **specify the schema path explicitly** in `@JdbcTest(properties=...)`. Without specifying it, Boot may look for default names like `schema.sql`/`data.sql` on the classpath; placing the script in `sql/inventory-schema.sql` avoids accidentally picking up a `schema.sql` from another environment.

### 4.5. DTO Read from JDBC ResultSet

File `src/main/java/com/example/jdbcslice/ProductRow.java`:

```java
package com.example.jdbcslice;

public record ProductRow(
        long id,
        String sku,
        String title,
        int quantity) {
}
```

`ProductRow` is a Java 17 record representing a mapped row. It is **not an `@Entity`**, and has no dirty checking or lazy loading. When a JDBC query returns data, we read each column from `ResultSet` and construct a new record; modifying the record in Java **does not automatically update the database**.

### 4.6. Real DAO Using JdbcTemplate

File `src/main/java/com/example/jdbcslice/InventoryJdbcDao.java`:

```java
package com.example.jdbcslice;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class InventoryJdbcDao {

    private static final RowMapper<ProductRow> ROW_MAPPER =
            (rs, rowNum) -> new ProductRow(
                    rs.getLong("id"),
                    rs.getString("sku"),
                    rs.getString("title"),
                    rs.getInt("quantity"));

    private final JdbcTemplate jdbc;

    public InventoryJdbcDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int insert(
            long id, String sku, String title, int quantity) {

        return jdbc.update("""
                INSERT INTO inventory_items (
                    id, sku, title, quantity
                ) VALUES (?, ?, ?, ?)
                """, id, sku, title, quantity);
    }

    public Optional<ProductRow> findBySku(String sku) {
        List<ProductRow> rows = jdbc.query("""
                SELECT id, sku, title, quantity
                  FROM inventory_items
                 WHERE sku = ?
                """, ROW_MAPPER, sku);

        return rows.stream().findFirst();
    }

    public List<ProductRow> findWithQuantityAtMost(
            int maximumQuantity) {

        return jdbc.query("""
                SELECT id, sku, title, quantity
                  FROM inventory_items
                 WHERE quantity <= ?
                 ORDER BY sku ASC
                """, ROW_MAPPER, maximumQuantity);
    }

    public int setQuantity(String sku, int quantity) {
        return jdbc.update("""
                UPDATE inventory_items
                   SET quantity = ?
                 WHERE sku = ?
                """, quantity, sku);
    }

    public int deleteBySku(String sku) {
        return jdbc.update("""
                DELETE FROM inventory_items
                 WHERE sku = ?
                """, sku);
    }

    public long countBySku(String sku) {
        Long count = jdbc.queryForObject("""
                SELECT COUNT(*) FROM inventory_items
                 WHERE sku = ?
                """, Long.class, sku);

        return count == null ? 0L : count;
    }
}
```

**Key points in the DAO snippet:**

- `JdbcTemplate` performs real JDBC access through the Spring-provided `DataSource`, not a Mockito mock.
- `?` are **bind placeholders**. When `sku` contains quotes, the JDBC driver receives it as a **value**, not concatenated into SQL text.
- `jdbc.update(...)` returns the **affected row count**, not an ID or entity. In the demo, a targeted single insert/update/delete normally returns 1.
- `jdbc.query(..., ROW_MAPPER, sku)` returns a `List<ProductRow>`; no rows gives an empty list. Hence `Optional.empty()` is the intentional contract result.
- `ROW_MAPPER` reads columns by name and builds a Java record. If an alias or SQL column name changes, mapping tests will report an error; there is no JPA provider auto-fixing field mappings.
- `countBySku` uses `queryForObject` because `COUNT(*)` normally returns one row even when the count is 0. If a query searches for an individual product and **no row exists**, `queryForObject` behaves differently (section 7).
- `@Repository` lets the DAO be recognized by Spring during full component scanning and applies exception translation when appropriate. However, **inside `@JdbcTest`, this class is loaded explicitly with `@Import`**, because the slice does not automatically scan all regular components.

### 4.7. Illustrative Service to Show Slice Boundaries

File `src/main/java/com/example/jdbcslice/InventoryService.java`:

```java
package com.example.jdbcslice;

import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final InventoryJdbcDao dao;

    public InventoryService(InventoryJdbcDao dao) {
        this.dao = dao;
    }

    public long countSku(String sku) {
        return dao.countBySku(sku);
    }
}
```

This service is **not the subject under test** in the JPA/JDBC slice. It exists to show that `@JdbcTest` does not automatically load ordinary `@Service` beans. The test only injects `InventoryJdbcDao` after `@Import`.

## 5. Complete JDBC Test Suite with JUnit 5 and H2

File `src/test/java/com/example/jdbcslice/InventoryJdbcDaoTest.java`:

```java
package com.example.jdbcslice;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.List;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest(properties = {
        "spring.sql.init.mode=always",
        "spring.sql.init.schema-locations=classpath:sql/inventory-schema.sql"
})
@Import(InventoryJdbcDao.class)
class InventoryJdbcDaoTest {

    @Autowired
    InventoryJdbcDao dao;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    DataSource dataSource;

    @Autowired
    ApplicationContext context;

    @Test
    void usesH2InThisEmbeddedDatabaseSetup() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            assertEquals(
                    "H2",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void sliceImportsDaoButNotOrdinaryService() {
        assertFalse(context.getBeansOfType(
                InventoryJdbcDao.class).isEmpty());
        assertTrue(context.getBeansOfType(
                InventoryService.class).isEmpty());
    }

    @Test
    void insertsAndMapsRecordFromRealSqlResultSet() {
        assertEquals(
                1, dao.insert(101L, "SKU-A", "Keyboard", 15));

        ProductRow row = dao.findBySku("SKU-A").orElseThrow();

        assertEquals(101L, row.id());
        assertEquals("SKU-A", row.sku());
        assertEquals("Keyboard", row.title());
        assertEquals(15, row.quantity());
        assertEquals(1L, dao.countBySku("SKU-A"));
    }

    @Test
    void missingSkuReturnsEmptyOptionalAndZeroCount() {
        assertTrue(dao.findBySku("NOT-EXIST").isEmpty());
        assertEquals(0L, dao.countBySku("NOT-EXIST"));
    }

    @Test
    void queryWithFilterHasExplicitStableSortOrder() {
        dao.insert(201L, "SKU-C", "C", 3);
        dao.insert(202L, "SKU-A", "A", 1);
        dao.insert(203L, "SKU-B", "B", 10);

        List<String> codes = dao.findWithQuantityAtMost(3)
                .stream()
                .map(ProductRow::sku)
                .toList();

        assertEquals(List.of("SKU-A", "SKU-C"), codes);
    }

    @Test
    void updateAndDeleteReportAffectedRowCount() {
        dao.insert(301L, "SKU-U", "Mouse", 9);

        assertEquals(1, dao.setQuantity("SKU-U", 4));
        assertEquals(
                4, dao.findBySku("SKU-U").orElseThrow().quantity());

        assertEquals(0, dao.setQuantity("MISSING", 5));
        assertEquals(1, dao.deleteBySku("SKU-U"));
        assertEquals(0, dao.deleteBySku("SKU-U"));
        assertTrue(dao.findBySku("SKU-U").isEmpty());
    }

    @Test
    void duplicateSkuIsRejectedByDatabaseConstraint() {
        dao.insert(401L, "SKU-DUP", "First", 5);

        assertThrows(
                DataIntegrityViolationException.class,
                () -> dao.insert(402L, "SKU-DUP", "Second", 7));

        // Do not continue sending SQL on a failed transaction:
        // some databases mark the transaction as aborted.
    }

    @Test
    void negativeQuantityIsRejectedByCheckConstraint() {
        assertThrows(
                DataIntegrityViolationException.class,
                () -> dao.insert(501L, "SKU-NEG", "Invalid", -1));
    }

    @Test
    void boundSkuIsDataNotSqlCode() {
        dao.insert(601L, "SAFE-1", "Safe", 2);

        String suspicious = "SAFE-1' OR '1'='1";
        assertTrue(dao.findBySku(suspicious).isEmpty());

        assertEquals(1L, dao.countBySku("SAFE-1"));
    }

    @Test
    void queryForObjectRequiresExactlyOneRow() {
        assertThrows(
                EmptyResultDataAccessException.class,
                () -> jdbc.queryForObject("""
                        SELECT title
                          FROM inventory_items
                         WHERE sku = ?
                        """, String.class, "NO-SUCH-SKU"));
    }
}
```

### 5.1. What Do the Test Cases Prove?

| Test Case | Evidence | Does Not Automatically Prove |
|---|---|---|
| `usesH2InThisEmbeddedDatabaseSetup` | The DataSource used in the test is real H2 | Production uses H2 or an identical SQL dialect |
| `sliceImportsDaoButNotOrdinaryService` | The DAO is imported, the ordinary service is excluded from the slice | Every custom component is excluded under every configuration |
| `insertsAndMapsRecordFromRealSqlResultSet` | INSERT, SELECT, RowMapper, and COUNT on a real DB | Data has been committed to another transaction |
| `missingSkuReturnsEmptyOptionalAndZeroCount` | Empty query list becomes Optional.empty, COUNT returns 0 | `queryForObject` also returns null when there is no row |
| `queryWithFilterHasExplicitStableSortOrder` | WHERE quantity and ORDER BY work with sample dataset | Query performance or collation on all databases |
| `updateAndDeleteReportAffectedRowCount` | Affected row counts and row state after update/delete | Multiple concurrent transactions have no races |
| `duplicateSkuIsRejectedByDatabaseConstraint` | UNIQUE constraint is active in H2 | Constraint is properly migrated in production PostgreSQL |
| `negativeQuantityIsRejectedByCheckConstraint` | CHECK quantity >= 0 rejects invalid input | Bean Validation at the HTTP layer is configured |
| `boundSkuIsDataNotSqlCode` | Placeholder does not turn suspicious input into an OR clause | All queries in the app are safe if string concatenation exists elsewhere |
| `queryForObjectRequiresExactlyOneRow` | Query with no row throws the expected exception type in this setup | A COUNT(*) query also throws when count is 0 |

**Note on runnability:** the `Application`, record, DAO, service, SQL script, Gradle, and JUnit class files are all provided. With Java 17+, Boot 3.5.8, and the right dependencies, this is a test suite **designed to compile and verify 10 scenarios**. Do not claim it has run in your environment unless you have actually run the corresponding build, runner, and database there.

With H2, UNIQUE/CHECK violations are translated by Spring JDBC exception translation into the appropriate `DataIntegrityViolationException` branch. Exception timing and subtype may differ on other drivers/databases: for example, PostgreSQL may mark a transaction aborted after a failed statement; isolate failing constraint cases into separate tests rather than attempting further queries in the same transaction.

## 6. Running the Test Class and Reading Real Results

In a project that already has a Gradle wrapper, on Linux/macOS:

```bash
./gradlew test --tests "com.example.jdbcslice.InventoryJdbcDaoTest"
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.jdbcslice.InventoryJdbcDaoTest"
```

If the project uses Maven wrapper and equivalent Spring Boot BOM/dependencies:

```bash
./mvnw -Dtest=InventoryJdbcDaoTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=InventoryJdbcDaoTest test
```

When the tests execute, check the Gradle report at `build/reports/tests/test/index.html` or Maven Surefire at `target/surefire-reports/` (for the **right module**). Make sure **all 10 test methods are actually discovered and run**, not `SKIPPED`, `NO-SOURCE`, or merely showing cached `UP-TO-DATE` results. The tests have no `System.out.println`, so do not invent a fixed stdout.

**An operational point:** the example only places H2 in `testRuntimeOnly`. If you run `JdbcSliceApplication.main` as in production without providing a runtime datasource/driver, the application may fail to start due to a missing datasource. That does **not** make the test wrong: the goal of the demo is `@JdbcTest`, not a full production server. For a real application, you must configure the production datasource explicitly.

## 7. Using JdbcTemplate: update, query, queryForObject, batchUpdate

### 7.1. update Returns a Row Count, Not an Entity

`JdbcTemplate.update(String sql, Object... args)` returns an integer representing the row count from JDBC. For example:

```java
int updated = jdbc.update("""
        UPDATE inventory_items
           SET quantity = ?
         WHERE sku = ?
        """, 8, "SKU-A");
```

The snippet above illustrates usage inside a class/test that already has `jdbc`, not a standalone Java file. It can return:
- `1`: one row updated.
- `0`: no matching row.
- Another value if the condition touches multiple rows and SQL/DB permits it.

Do not ignore the row count when business rules expect "only one order/product updated". `0` may mean the ID does not exist or an optimistic update condition did not match; a multi-row update may be a serious bug.

If you need generated IDs, you can use a `PreparedStatement` configured with `RETURN_GENERATED_KEYS` and `KeyHolder` (or `SimpleJdbcInsert`), though syntax/returned keys depend on driver/dialect. The demo uses explicit `id` values to stay focused on the `JdbcTemplate` contract.

### 7.2. query Uses RowMapper and Typically Returns a List

`jdbc.query(sql, rowMapper, args...)` runs a SELECT and turns each row into a Java object. For example:

```java
List<ProductRow> rows = jdbc.query("""
        SELECT id, sku, title, quantity
          FROM inventory_items
         WHERE quantity <= ?
         ORDER BY sku
        """,
        (rs, rowNum) -> new ProductRow(
                rs.getLong("id"),
                rs.getString("sku"),
                rs.getString("title"),
                rs.getInt("quantity")),
        5);
```

This snippet assumes `JdbcTemplate jdbc` and `ProductRow` are already defined in scope. If there are no rows, `query` returns an empty list; it **does not automatically throw `EmptyResultDataAccessException`**.

**RowMapper caveats:**
- `ResultSet.getInt(...)` returns `0` on SQL NULL; subsequently use `ResultSet.wasNull()` to distinguish NULL if the column is nullable. With the demo's `quantity NOT NULL`, `int` is an intentional choice.
- Use exact column names/aliases. If SQL returns `available_quantity AS quantity`, the RowMapper can read `quantity`; without the alias, the column name differs.
- `BeanPropertyRowMapper` supports JavaBean mapping by convention; it does not guarantee auto-mapping Java records across every version. `DataClassRowMapper` supports classes/records with suitable constructors, though real mapping should still be tested.
- `RowMapper` should focus on mapping a single row; do not make network I/O calls or open new transactions from the callback.

### 7.3. queryForObject Does Not Mean "Return Null When Not Found"

`queryForObject` is meant for queries **expecting exactly one row**. In Spring JDBC, if 0 rows or more than 1 row appear, it can throw `EmptyResultDataAccessException` or `IncorrectResultSizeDataAccessException`. If a single row has a SQL NULL value, the mapped result may be null depending on the chosen type/mapper, **which is different from having no row**.

Compare:

```sql
SELECT title FROM inventory_items WHERE sku = 'MISSING';
-- 0 rows: queryForObject does not automatically return Optional.empty.

SELECT COUNT(*) FROM inventory_items WHERE sku = 'MISSING';
-- 1 row with value 0: queryForObject(Long.class) can return 0.
```

If business logic needs `Optional` on 0 rows, you can use `query(..., rowMapper, args)` and `stream().findFirst()` as in the DAO in section 4, or carefully catch `EmptyResultDataAccessException` specifically. **Do not catch every `DataAccessException` and return empty**: connection, syntax, constraint, or timeout errors would then be masked as "not found".

### 7.4. batchUpdate Sends Multiple Statements Without Changing Transaction Policy

Illustrative example:

```java
List<Object[]> batchArgs = List.of(
        new Object[] {701L, "SKU-X", "X", 1},
        new Object[] {702L, "SKU-Y", "Y", 2});

int[] counts = jdbc.batchUpdate("""
        INSERT INTO inventory_items (id, sku, title, quantity)
        VALUES (?, ?, ?, ?)
        """, batchArgs);
```

This snippet requires `java.util.List`, `JdbcTemplate jdbc`, and the demo table. With JDBC drivers, elements of the update counts array may contain special JDBC constants like `Statement.SUCCESS_NO_INFO` rather than always `1`. Verify the number of submitted items, results/SQL exceptions, and proper business transaction boundaries. `batchUpdate` **does not automatically guarantee atomicity** if executed outside a transaction or if the driver/DB lacks the expected semantics.

### 7.5. NamedParameterJdbcTemplate and JdbcClient

In queries with many parameters, `NamedParameterJdbcTemplate` is often easier to read:

```java
int affected = named.update("""
        UPDATE inventory_items
           SET quantity = :quantity
         WHERE sku = :sku
        """,
        Map.of("quantity", 4, "sku", "SKU-A"));
```

This snippet assumes `NamedParameterJdbcTemplate named` and `import java.util.Map` are in scope. Spring converts named parameters into appropriate JDBC binds; it is still JDBC-based, not JPA/Hibernate.

`JdbcClient` is a fluent facade introduced in Spring Framework 6.1+ for many SQL operations. It can be auto-configured by Boot in `@JdbcTest` when appropriate. However, there is no need to rewrite a `JdbcTemplate` lesson into `JdbcClient` merely because of the new API: both approaches should be tested by the same principles regarding bind parameters, mapping, affected rows, and database dialect.

## 8. Transactions and Rollback: What Actually Gets Cleaned Up?

`@JdbcTest` is transactional by default and Spring TestContext **rolls back at the end of each test**. When `InventoryJdbcDaoTest` inserts `SKU-A` and then asserts the data, the `INSERT`/`SELECT` statements normally execute within **the same test-managed transaction T1**.

```text
JUnit test method (current thread)
      |
      +-- T1 started by Spring TestContext
      |       |
      |       +-- dao.insert(...)       -> SQL INSERT
      |       +-- dao.findBySku(...)    -> SELECT within T1
      |       +-- assertions
      |
      +-- Spring TestContext rolls back T1
      |
      v
Uncommitted record is gone after the test ends
```

### 8.1. A Query Seeing a Row Does Not Mean the Row Was Committed

Because the test is wrapped by T1, `jdbc.queryForObject("select count(*) ...")` **can see uncommitted changes made by T1 itself**. A green test after `dao.insert` does not prove another database connection or HTTP request sees that row before commit.

To genuinely verify **commit/rollback or isolation**:
- Control transaction boundaries explicitly using Spring transaction testing support.
- You can use `TestTransaction` to actively end the test's transaction when TestContext manages T1.
- When verifying committed data, read on an independent transaction/connection **after commit**.
- Clean up committed data using a separate transaction or an appropriate database test lifecycle; do not use a production database.

### 8.2. Enabling/Disabling Rollback

`@Rollback(false)` or `@Commit` can change the ending policy of the **test-managed transaction**, at the risk of leaving data behind. If you do not want a test-managed transaction:

```java
@JdbcTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class NonTransactionalJdbcTest {
    // Must clean up committed changes yourself.
}
```

This is an **annotation pattern**, requiring imports for `JdbcTest`, `Transactional`, and `Propagation`, not a complete test class. In this setup, code typically runs SQL operations under auto-commit or its own programmatic transactions, so the default test rollback **no longer protects the data**.

**Do not confuse transactions on the test thread with transactions opened by an HTTP server:** when testing via `@SpringBootTest(RANDOM_PORT)` and a real HTTP client, the server handles requests on another thread; `@Transactional` on the test **does not automatically roll back** transactions committed by the server.

### 8.3. Timeouts, @BeforeEach, and Transaction Context

Spring TestContext normally runs `@BeforeEach` and `@AfterEach` inside the test-managed transaction if it is active; `@BeforeTransaction`/`@AfterTransaction` run outside that transaction. Thus, cleanup inside `@AfterEach` may also be rolled back; if data was committed in another transaction, clean it up using `@AfterTransaction` or an explicit mechanism.

**Preemptive timeouts** like `assertTimeoutPreemptively` can run code on another thread and **lose the test's thread-bound transaction**, causing SQL to commit unintentionally. This is why you must not assume every change inside a `@JdbcTest` will be rolled back if code switches threads or starts a new transaction.

## 9. Test Database Replacement: H2 or Real PostgreSQL?

When H2 is on the classpath, `@JdbcTest` can normally create an embedded database. Under Boot's test database configuration, a datasource identified as a **test connection** may be retained when an appropriate replacement mode is used; one should not claim every datasource is replaced in every version or case.

If the goal is to verify **PostgreSQL-specific** SQL syntax or constraints, use a PostgreSQL test database and prevent test database auto-configuration from replacing it with H2.

### 9.1. Using @AutoConfigureTestDatabase(replace = NONE)

In Boot 3.5:

```java
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;

@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
```

This is an illustrative annotation placed on a test class. **`Replace.NONE` does not create a database by itself**: it only instructs Boot not to replace the supplied datasource; you must ensure the URL/driver/credentials point to a **test database**, not production.

Other modes may include `ANY`, `AUTO_CONFIGURED`, and `NON_TEST`; Boot 3.5's `NON_TEST` does not replace datasources that Boot recognizes as test DBs, such as certain service connections/Testcontainers or test URLs declared via `@DynamicPropertySource`. Choose based on **your actual Boot line and connection setup**, rather than just copying values from another article.

### 9.2. Differences Between H2 and PostgreSQL

H2 is usually great for fast testing of standard SQL:
- Basic queries, placeholders, mappings.
- `UNIQUE`, `NOT NULL`, `CHECK`, and simple CRUD.
- `JdbcTemplate` exception translation for a specific driver.

However, H2 **does not guarantee** parity with PostgreSQL regarding:
- `ON CONFLICT`, `RETURNING`, `ILIKE`, JSONB, arrays, indexes.
- Transaction isolation, locking, concurrent writes, and deadlocks.
- Unicode collation, case sensitivity, ordering.
- Date/timezone, decimal rounding, generated keys, and schema defaults.
- Flyway/Liquibase migrations using database-specific syntax.
- Vendor exception codes and the exact timing of constraint failures.

Therefore, keep fast H2 tests for most simple CRUD, and supplement with production-like database tests for critical queries and constraints.

## 10. Testcontainers PostgreSQL Example for a JDBC Slice

This section is an **additional test class**, not a replacement for the 10 H2 cases in section 5. It reuses `InventoryJdbcDao`, `ProductRow`, and the SQL script from the existing example.

### 10.1. Additional Dependencies

In Boot 3.5.8 `build.gradle`, add:

```groovy
dependencies {
    testRuntimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
```

This is an additional fragment, not the full build file. Testcontainers requires a container runtime (typically Docker or a supported equivalent). Do not attempt to run this test in an environment without a container runtime and treat that failure as a `JdbcTemplate` bug.

### 10.2. Complete Test Class

File `src/test/java/com/example/jdbcslice/InventoryPostgresJdbcTest.java`:

```java
package com.example.jdbcslice;

import java.sql.Connection;
import java.sql.SQLException;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
@JdbcTest(properties = {
        "spring.sql.init.mode=always",
        "spring.sql.init.schema-locations=classpath:sql/inventory-schema.sql"
})
@Import(InventoryJdbcDao.class)
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class InventoryPostgresJdbcTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("inventory_test")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void postgresProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    InventoryJdbcDao dao;

    @Autowired
    DataSource dataSource;

    @Test
    void usesPostgresRatherThanEmbeddedH2() throws SQLException {
        try (Connection c = dataSource.getConnection()) {
            assertEquals(
                    "PostgreSQL",
                    c.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void writesAndReadsThroughRealPostgres() {
        assertEquals(
                1, dao.insert(901L, "PG-A", "Postgres Test", 6));
        assertEquals(
                6, dao.findBySku("PG-A").orElseThrow().quantity());
    }
}
```

**Connection explanation:**
- `@Container` + `@Testcontainers` manage the PostgreSQL container lifecycle via the JUnit Jupiter extension.
- `@DynamicPropertySource` registers **suppliers** so Spring reads the JDBC URL, username, and password when configuring the datasource; the JDBC URL contains the container's host and mapped port, not a hard-coded `localhost:5432`.
- `@AutoConfigureTestDatabase(replace=NONE)` stops `@JdbcTest` from replacing the PostgreSQL datasource with H2.
- `spring.sql.init.mode=always` enables SQL script initialization even when the datasource is **not** embedded.
- `schema-locations` uses the example's shared SQL script; the DDL is designed using features compatible with both H2 and PostgreSQL.
- Each test still typically gets a **test-managed transaction and rollback**, even though the database server is real PostgreSQL.

**Lifecycle note:** if the application context cache retains a datasource after a class-level container has stopped, another test class might encounter a stale JDBC URL/port. When reusing resources across multiple tests, choose an appropriate container lifetime and cache scope rather than relying on an old port. For an isolated test class like this example, a static class-scoped container lifecycle keeps things manageable.

In a Boot project already using `@ServiceConnection` and the `spring-boot-testcontainers` module, you can use the service connection mechanism instead of `@DynamicPropertySource` where appropriate. Do not declare competing sources for the same properties without understanding precedence.

## 11. Are schema.sql, data.sql, @Sql, and Migrations the Same Thing?

**No.** These ways of managing schema/fixtures serve different purposes.

| Mechanism | When Does It Run? | Purpose |
|---|---|---|
| Boot `spring.sql.init.schema-locations` | When the DataSource context is initialized | Create tables/schema for the test context |
| Boot `spring.sql.init.data-locations` | When SQL initialization runs | Seed default data; watch state between tests |
| Spring Test `@Sql` | According to specified `BEFORE_TEST_METHOD`/`AFTER_TEST_METHOD` | Specific fixture for one class/method |
| Flyway/Liquibase | When migration auto-config is loaded and enabled | Run/verify versioned schema migrations |
| DAO setup via `jdbc.update` | Inside `@BeforeEach` or test body | Data explicitly tied to a test case |
| Testcontainers | When container lifecycle starts | Provides a database server, **does not create schema automatically** |

In the example, we use **only one SQL schema initializer** and then insert fixtures right inside each test. As a result, tests do not need to share `data.sql` or depend on execution order.

If the production project uses Flyway/Liquibase, it is usually best to let **migrations be the single source creating the schema** in relevant integration tests and not simultaneously run another `schema.sql` creating the same tables. Verify that the JPA/JDBC test slice actually loads the migration auto-configuration, that the datasource is right, and that the scripts run cleanly on the target database.

### 11.1. Sample @Sql Fixture

Example annotation inside a `@JdbcTest` with an actual SQL fixture file:

```java
@Sql(
        scripts = "/sql/inventory-fixture.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
@Test
void readsKnownFixture() {
    // Assertions on fixture data.
}
```

This is an illustration requiring `@Sql`, `Sql.ExecutionPhase` imports, and a `src/test/resources/sql/inventory-fixture.sql` script. With the default test-managed transaction, `@Sql` in the same transaction can roll back at the end of the test. With `@SqlConfig(transactionMode=ISOLATED)`, the script runs in its own transaction; if it commits, it will not roll back automatically with the method's transaction — proper cleanup is required.

**Do not expect "schema.sql to just work" if the real file sits in another package or path.** Use `spring.sql.init.schema-locations` to declare it accurately, and when a file might be missing, use a location without `optional:` to fail fast instead of silently creating a context without tables.

## 12. SQL Query Safety and Updated Row Counts

### 12.1. Prepared Placeholders Prevent Input from Becoming SQL Syntax

If a user passes `"A' OR '1'='1"` for SKU, using:

```java
jdbc.query(
        "SELECT sku FROM inventory_items WHERE sku = ?",
        (rs, rowNum) -> rs.getString("sku"),
        inputSku);
```

binds the parameter through JDBC, without creating a new OR clause. However, **SQL injection can still occur in non-bindable positions**, such as concatenating table names, column names, or `ORDER BY` from un-whitelisted input:

```java
// INTENTIONALLY WRONG: never concatenate client-chosen column names into SQL.
String sql = "SELECT * FROM inventory_items ORDER BY " + userSort;
```

`userSort` here is an illustrative variable not present in the sample program. If optional sorting is needed, map input against an **allowlist** such as `sku`, `title`, `quantity`; you can bind condition values, but you cannot bind a SQL identifier with a standard placeholder.

**Do not treat a single test with a suspicious string as a security certificate for the entire application.** It only proves the tested query path does not interpret that input as a SQL clause.

### 12.2. Checking Row Counts and Optimistic Updates

For example, when you only want to deduct stock if enough quantity exists:

```java
int changed = jdbc.update("""
        UPDATE inventory_items
           SET quantity = quantity - ?
         WHERE sku = ?
           AND quantity >= ?
        """,
        requested, sku, requested);
```

If `changed == 1`, a matching row had its quantity deducted. If `changed == 0`, either the SKU does not exist **or** stock is insufficient. You cannot tell which one from the row count alone; a contract and an extra query are needed if the API must distinguish 404 from 409.

This is an illustrative snippet inside a method with `requested`, `sku`, and `jdbc`. It demonstrates a better technique than reading quantity and updating unconditionally: a conditional SQL update reduces some races between two requests. **However**, to prove correctness under concurrent load/locking/isolation, you need integration tests against a real database with concurrent transactions, not just a sequential `@JdbcTest` on H2.

## 13. Common Pitfalls When Writing @JdbcTest

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `No qualifying bean of type InventoryJdbcDao` | Ordinary `@Repository` DAO is not scanned in the slice | `@Import(InventoryJdbcDao.class)` |
| `NoSuchBeanDefinitionException` for service | Services do not belong to the JDBC slice | Test DAO directly; use an appropriate context for service tests |
| `Failed to configure a DataSource` | Missing embedded driver/JDBC URL/credentials | Check `testRuntimeOnly` H2 or real test datasource |
| `Table INVENTORY_ITEMS not found` | Schema script not loaded, wrong location, or DB schema | Check `spring.sql.init.schema-locations`, mode, logs |
| H2 test green but PostgreSQL fails | Different dialect, collation, data types, migrations | Add PostgreSQL Testcontainers |
| SQL return maps wrong fields | RowMapper uses wrong column name or alias | Assert every record component from a real query |
| `queryForObject` throws when no row | API requires exactly one row | Use `query` + Optional per contract |
| `COUNT(*)` returning 0 mistaken for no row | COUNT still returns one row | Assert the count value, do not catch EmptyResult |
| UPDATE test green even when SKU missing | Affected row count ignored | Assert `jdbc.update(...)` returns 1/0 |
| SQL constraint missed in mocked unit test | Real SQL never executed | Use `@JdbcTest` + schema with constraints |
| Queries concatenate input directly | SQL injection | Use placeholders/named parameters; allowlist identifiers |
| Test with `@Transactional` sees newly written row | Same transaction reads its own uncommitted changes | Do not equate readable with committed |
| Test fails to roll back data after async/preemptive timeout | SQL ran on another thread/transaction | Control threads and TestTransaction/cleanup |
| Test fails to catch expected exception subtype on another DB | Driver/exception translation differs from H2 | Assert stable exception types per contract and database |
| Slow tests from full app startup | Using `@SpringBootTest` when only JDBC is needed | Narrow with `@JdbcTest`, import the needed DAO |
| Schema created twice | Both `schema.sql` and migrations create tables | Pick one schema owner |
| Test passes alone but fails in suite | Shared DB, duplicate fixture IDs, context cache, or leaked commits | Use rollback/unique fixtures/isolated database |
| Boot 4 fails to resolve `org.springframework.boot.test.autoconfigure.jdbc.JdbcTest` | Package/module moved since Boot 3 | Switch to the matching Boot 4 test module/import |

**Read the root cause** in the `Caused by` chain when the application context fails to start. If a `SQLException` names a table or column, inspect the real schema and SQL; do not "fix" it by mocking `JdbcTemplate`, because that removes the exact mechanism you need to verify.

## 14. Version Lines: Spring Boot 3.5 vs Spring Boot 4.x

Code in sections 4–10 uses **Spring Boot 3.5.x**, where `@JdbcTest` is imported from:

```java
org.springframework.boot.test.autoconfigure.jdbc.JdbcTest
org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase
```

This is a package reference list, not a standalone Java file.

In Spring Boot **4.x**, test slices are split into modules. The corresponding `@JdbcTest` resides in:

```java
org.springframework.boot.jdbc.test.autoconfigure.JdbcTest
org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase
```

The required module is **`spring-boot-jdbc-test`** and the matching test starter/dependencies from the Boot BOM. Do not try adding Boot 4 JARs to a Boot 3.5 runtime to fix imports; doing so breaks Spring Framework dependency alignment.

The principles remain identical:
- `@JdbcTest` is for JDBC + DataSource + templates, not JPA/Hibernate.
- Ordinary services and hand-written `@Repository` DAOs are not auto-scanned by default, so import the bean under test.
- Test transaction rollback does not replace cleanup for external transactions.
- H2 does not prove production SQL dialect; add Testcontainers when reliability depends on real PostgreSQL/MySQL.
- Migrations and test database replacement must be controlled according to **the version you are running**.

When upgrading Boot, check the exact `JdbcTest` and `AutoConfigureTestDatabase` imports, test dependencies, schema initialization properties, and integration test reports. If a project is already on Boot 4, follow **the Boot 4 documentation** rather than copying every Boot 3 import from this article.

## 15. Checklist Before Signing Off a JDBC Integration Test

- [ ] Correctly identified the target as **JdbcTemplate/SQL/JDBC DataSource**, not confused with Spring Data JDBC/JPA.
- [ ] `@JdbcTest` uses the right package/module for the Boot version, and the context loads only needed JDBC components.
- [ ] Real DAO is `@Import`ed if not auto-scanned by the slice; `JdbcTemplate` is not mocked.
- [ ] Verified that `DataSource` actually points to embedded H2 or the intended test database.
- [ ] SQL schema is created by **one clear mechanism** (script initializer or migration), with no conflicts.
- [ ] Tested `INSERT`, `SELECT`, `UPDATE`, `DELETE`, row counts, and RowMapper against real SQL.
- [ ] Queries use placeholders/named parameters, without concatenating user data directly into SQL.
- [ ] When results have no rows, distinguished `query` (empty list) from `queryForObject` (expected error).
- [ ] Representative data includes filter conditions, sorting, missing keys, and UNIQUE/CHECK/NOT NULL constraints.
- [ ] Understood test-managed rollback; do not treat rows visible in the same transaction as proof of commit.
- [ ] Do not continue querying on a failed transaction in DBs with transaction-aborted semantics.
- [ ] If SQL depends on dialect/locking, tests exist on PostgreSQL/MySQL or a production-like database.
- [ ] Controlled `@AutoConfigureTestDatabase`, `@DynamicPropertySource`, and container lifecycle when using Testcontainers.
- [ ] Ran the exact JUnit test class in the right module and inspected the report to verify tests actually executed rather than being skipped.
- [ ] Did not claim HTTP/service transactions/security work solely from a `@JdbcTest`.

## 16. Official Documentation

- [Spring Boot 3.5 – Auto-configured JDBC Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): scope of `@JdbcTest`, embedded database, `JdbcTemplate`, and rollback.
- [Spring Boot 3.5 – Test Slices](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): auto-configurations included in `@JdbcTest`.
- [Spring Boot – Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html): `schema.sql`, `data.sql`, init mode, migrations.
- [Spring Framework – JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, query, update, and mapping.
- [Spring Framework – Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback, `@BeforeTransaction`/`@AfterTransaction`, preemptive timeouts.
- [Spring Boot 4 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@JdbcTest` from the `spring-boot-jdbc-test` module and new namespace.

**Conclusion:** `@JdbcTest` allows testing **`JdbcTemplate` and SQL against a real database inside a small Spring slice**. Reliable tests must use the real DAO, appropriate schema/data, assertions on row mapping and affected row counts, understand that rollback applies only to **test-managed transactions**, and control database replacement. H2 helps catch many common SQL bugs quickly; when queries, constraints, or concurrency depend on PostgreSQL/MySQL, add Testcontainers with a production-like database.