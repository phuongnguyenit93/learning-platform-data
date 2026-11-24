# @Sql, @SqlGroup, and SQL Script Execution Timing in Spring Boot Testing

## 1. The Problem: When Is Test Data Prepared and Is It Truly Cleaned Up?

A repository test often needs consistent SQL data to verify a query or business rule. Calling `jdbcTemplate.update(...)` directly inside each method can be quick, but when many tests share the same dataset, repeated statements become hard to maintain. Conversely, seeding data only once at application startup can make tests order-dependent, cause interference across tests, or obscure when data gets rolled back.

Spring TestContext provides **`@Sql`**, **`@SqlGroup`**, and **`@SqlConfig`** to define the exact SQL statements or script files to execute **before/after a test method** or **before/after the entire test class**. `SqlScriptsTestExecutionListener` executes these annotations within the Spring TestContext lifecycle.

A minimal declaration:

~~~java
@Test
@Sql(scripts = "/sql/books.sql")
void findBooks() {
    // SQL runs before the method by default.
}
~~~

This is an illustrative snippet. `/sql/books.sql` is a classpath resource path, not an OS filesystem path starting from the root directory. The method only runs when the test context has a suitable `DataSource` and the script actually exists.

**After this lesson, you will be able to:**

1. Explain what executes `@Sql` and the `BEFORE_TEST_METHOD`, `AFTER_TEST_METHOD`, `BEFORE_TEST_CLASS`, and `AFTER_TEST_CLASS` phases.
2. Understand the difference between Spring Boot **`schema.sql`/`data.sql`** running at DataSource/ApplicationContext initialization and Spring Test **`@Sql`** running per test lifecycle.
3. Combine multiple `@Sql` annotations using repeatable annotations or **`@SqlGroup`**.
4. Distinguish method-level `@Sql` defaulting to **OVERRIDE** class-level `@Sql`, and **`@SqlMergeMode(MERGE)`** when both must be merged.
5. Know the exception: class-level `BEFORE_TEST_CLASS`/`AFTER_TEST_CLASS` are **not overridden by method-level `@Sql`**.
6. Choose `@SqlConfig(transactionMode = INFERRED)` or `ISOLATED` depending on whether data should roll back or commit.
7. Understand why **`AFTER_TEST_METHOD` usually runs before the test-managed transaction rolls back**, due to listener order; it does not automatically clean up independently committed data.
8. Use `@AfterTransaction` to verify data **after rollback**, rather than checking only inside the test method.
9. Write a Java 17 + **Spring Boot 3.3.5** + Gradle + `@JdbcTest` + H2 example with SQL files and **9 JUnit Jupiter `@Test` methods**.
10. Avoid SQL scripts hitting the wrong schema, data leaks under `ISOLATED`, resource path errors, ordering conflicts, and flaky CI tests.

**Parent context “Test Data”:** This lesson focuses strictly on the mechanisms for creating, loading, and cleaning up **SQL fixtures** in Spring Boot testing. No HTTP server, Spring MVC controller, Hibernate/JPA, R2DBC, or Testcontainers are required to understand the core lifecycle. Other technologies can still use `@Sql` if the test context provides the required `DataSource`/transaction manager, while this sample keeps things fixed on JDBC/H2 for clear observation.

**Pinned versions:** Java 17, Spring Boot **3.3.5**, Spring Framework **6.1.x** selected by the Boot BOM, Gradle, H2, and JUnit Jupiter. Specifically, `BEFORE_TEST_CLASS` and `AFTER_TEST_CLASS` were introduced in **Spring Framework 6.1**; do not copy this example verbatim into a Spring 5.x project assuming those enum constants exist.

## 2. What Executes @Sql and Why Does the Annotation Take Effect?

`@Sql` belongs to the package `org.springframework.test.context.jdbc`, not `org.springframework.boot` and not JUnit. Spring TestContext registers `SqlScriptsTestExecutionListener` in its default listener set when integrating Spring testing. The listener inspects annotations on the test class and test method, resolves paths/configuration, and executes scripts via Spring JDBC infrastructure.

~~~text
Spring TestContext
  |
  | SqlScriptsTestExecutionListener
  +-- beforeTestClass()   -> @Sql BEFORE_TEST_CLASS
  |
  +-- beforeTestMethod()  -> @Sql BEFORE_TEST_METHOD
  |                          (default when phase is omitted)
  |
  +-- JUnit @BeforeEach, @Test, @AfterEach
  |
  +-- afterTestMethod()   -> @Sql AFTER_TEST_METHOD
  |
  +-- afterTestClass()    -> @Sql AFTER_TEST_CLASS
~~~

Each `@Sql` can specify:
- **`scripts`**: one or more `.sql` files.
- **`statements`**: one or more inline SQL statements.
- **`executionPhase`**: the execution phase.
- **`config = @SqlConfig(...)`**: parsing, error handling, and transaction mode for that script group.

**Database infrastructure is required:** The listener requires a `DataSource`, and may require a `PlatformTransactionManager` depending on `transactionMode`. In the sample project, `@JdbcTest` + Spring Boot Starter JDBC + H2 provide the `DataSource`, `JdbcTemplate`, and transaction manager. If an application has multiple databases or transaction managers, select the exact beans with `@SqlConfig(dataSource = "...", transactionManager = "...")` instead of relying on default Spring lookup.

**Do not invoke JDBC resources manually inside the annotation.** Files live on the test classpath, and execution is handled by the listener. If a resource is missing, SQL syntax is invalid, or no `DataSource` exists, test setup/teardown fails either before `@Test` code runs or after it finishes.

### 2.1. Annotation Placement and Resource Paths

~~~java
// On the class: runs before EACH method in the class by default.
@Sql(scripts = "/sql/base-books.sql")
class BookRepositoryTest {

    @Test
    void testOne() { }

    @Test
    void testTwo() { }
}
~~~

This snippet illustrates annotation behavior. Placing `@Sql` on a **class** with the default phase does not mean “run once before the entire class”; it is applied **before each test method**. To run once before the entire class, use `executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS` on Spring Framework 6.1+.

Script paths:
- `"/sql/base-books.sql"`: **absolute on the classpath**, corresponding to `src/test/resources/sql/base-books.sql`.
- `"base-books.sql"` without a leading `/`: resource **relative to the test class's package**. For package `demo.sql`, this resolves to `demo/sql/base-books.sql` on the classpath.
- `"classpath:sql/base-books.sql"`: resource with an explicit `classpath:` prefix.
- Use a `file:` path pointing outside the project only when justified and in a stable runner environment; machine-specific absolute paths routinely break CI.

**Default path when both `scripts` and `statements` are omitted:** If `@Sql` is placed on class `demo.sql.BookTest`, Spring looks for `classpath:demo/sql/BookTest.sql`. If placed on method `findBook()` of that class, Spring looks for `classpath:demo/sql/BookTest.findBook.sql`. If the default script is missing, it throws `IllegalStateException`; in tutorials and team codebases, explicit paths are far easier to trace.

## 3. Four Execution Phases: Method and Class Are Not the Same

### 3.1. BEFORE_TEST_METHOD — Default

~~~java
@Test
@Sql(
    scripts = "/sql/base-books.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
void hasSeededBooks() {
    // The test sees seeded data before running.
}
~~~

The annotation may omit `executionPhase` because **BEFORE_TEST_METHOD is the default**. In a transactional test (`@JdbcTest`, `@DataJpaTest`, or `@Transactional` with a transaction manager), scripts in this phase typically run **inside the test's already-open transaction** and roll back after the method. This gives every test the same fixture without repeating `@BeforeEach` INSERT statements.

**Ordering in JUnit Jupiter:** Spring `beforeTestMethod` callbacks run before `@BeforeEach` and before `@Test` code. Therefore, if `@BeforeEach` queries the database, data seeded by `BEFORE_TEST_METHOD` is already visible inside the test transaction.

### 3.2. AFTER_TEST_METHOD — After the Method, Usually Before Rollback

~~~java
@Test
@Sql(
    scripts = "/sql/after-method.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
void businessTest() {
    // After the method, the listener runs after-method.sql.
}
~~~

**This is the most common source of confusion.** In Spring TestContext, `TransactionalTestExecutionListener` has order **4000**, while `SqlScriptsTestExecutionListener` has order **5000**. `beforeTestMethod` listeners run in ascending order (transaction opens first, SQL runs second), whereas `afterTestMethod` listeners run in **reverse order** (after-method SQL runs first, and only then does the test transaction end/roll back).

Consequently, in a default-transactional `@JdbcTest` with the default `@SqlConfig` `INFERRED`, an `AFTER_TEST_METHOD` SQL script can execute **still inside the test transaction**, and then get rolled back alongside all test DML. Do not assume that because the phase name says AFTER it runs *after rollback*. Use `@AfterTransaction` to observe data once rollback has actually completed.

**`@AfterEach` and `AFTER_TEST_METHOD`:** JUnit `@AfterEach` runs before the Spring TestContext `afterTestMethod` callback. Thus `@AfterEach` is not the place to assert that an `AFTER_TEST_METHOD` SQL script has already run. It also still executes inside the test transaction when the test is transactional.

### 3.3. BEFORE_TEST_CLASS — Once Before the Entire Class (Spring 6.1+)

~~~java
@Sql(
    scripts = "/sql/class-before.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS
)
class ClassPhaseExample {
    // Script runs once before all test methods.
}
~~~

The class phase is used to prepare shared state for an entire class, such as reference data or lookup tables. **It has no method-scoped test-managed transaction to automatically roll back**. When a transaction manager is present and mode is `INFERRED` with no active transaction, Spring typically opens a **new transaction that commits immediately**. Therefore, this data persists across methods in the class and does not disappear on per-method rollback.

**Do not use class-phase seeds as mutable per-method fixtures.** For records that tests may update, use method-phase with transaction rollback or database isolation. Class phase is best suited for immutable reference data or explicitly cleaned-up state.

### 3.4. AFTER_TEST_CLASS — Once After the Entire Class (Spring 6.1+)

~~~java
@Sql(
    scripts = "/sql/class-after.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_CLASS
)
class ClassPhaseExample {
    // Script runs once all methods in the class have finished.
}
~~~

This phase can clean up data committed during `BEFORE_TEST_CLASS`. However, it **does not** guarantee that another test class running later will see a clean state if test classes run in parallel or share a database/schema without isolation. When class-level setup has side effects on an external database, ensure proper cleanup, use unique namespaces/keys, and never depend on suite execution order.

**Important exception:** Class-level `@Sql` with `BEFORE_TEST_CLASS`/`AFTER_TEST_CLASS` is **not overridden by a method-level `@Sql`**; class phases still run once before and after the class. Standard override rules apply to method-phase SQL declarations.

### 3.5. Summary Timeline Table

| Phase | How Often? | Timing | In a Transactional @JdbcTest? |
|---|---:|---|---|
| `BEFORE_TEST_CLASS` | Once per class | Before all test methods | No method test TX; usually commits independently |
| `BEFORE_TEST_METHOD` | Before each method | After test transaction starts, before JUnit `@BeforeEach` | Usually inside test TX; rolls back at end of method |
| `AFTER_TEST_METHOD` | After each method | After JUnit `@AfterEach`, before transaction rollback under default listener order | Usually inside test TX; rolls back at end of method |
| `AFTER_TEST_CLASS` | Once per class | After all test methods | No method test TX; usually commits independently |

Do not generalize this across projects without a transaction manager or with `@SqlConfig(ISOLATED)`: commit/rollback behavior differs there. The table above describes Spring TestContext defaults for JDBC tests with a transaction manager.

## 4. @SqlGroup, Repeatable @Sql, and Script Ordering

### 4.1. @Sql Can Appear Multiple Times

In Java, `@Sql` is a repeatable annotation. Both styles below declare multiple SQL groups with distinct configurations or phases.

**Repeatable @Sql:**

~~~java
@Test
@Sql(
    scripts = "/sql/seed.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Sql(
    scripts = "/sql/cleanup.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
void testWithTwoPhases() {
    // Not a complete file; seed.sql and cleanup.sql must exist.
}
~~~

**@SqlGroup:**

~~~java
@Test
@SqlGroup({
    @Sql(
        scripts = "/sql/seed.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
    ),
    @Sql(
        scripts = "/sql/cleanup.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
    )
})
void testWithGroup() {
    // Equivalent to the repeatable form above.
}
~~~

`@SqlGroup` is a **container annotation** for `@Sql` declarations, not a “new combined transaction mechanism.” Each `@Sql` element can specify its own scripts, inline statements, phase, and config. Entries in the same phase are processed in their declared order; scripts referencing tables created by another script must be ordered intentionally. A group containing `BEFORE` and `AFTER` entries dispatches each into its respective lifecycle phase rather than running them back-to-back before the method just because they sit next to each other in the array.

If the same phase needs a sequence of scripts, you can also write:

~~~java
@Sql(scripts = {
    "/sql/create-reference-data.sql",
    "/sql/create-test-orders.sql"
})
~~~

Spring executes the listed scripts in configured order; avoid relying on undefined glob ordering or test method ordering. For application schema initialization, prefer Flyway/Liquibase; `@Sql` is suited for test-specific data.

### 4.2. Default Override: Method-Level Overrides Class-Level

Consider:

~~~java
@Sql("/sql/base-books.sql")
class BookTest {

    @Test
    void normalTest() {
        // base-books.sql runs beforehand.
    }

    @Test
    @Sql("/sql/one-book.sql")
    void specialTest() {
        // By default, class-level script is OVERRIDDEN.
        // Only one-book.sql runs before this method.
    }
}
~~~

Do not assume a method-level script **automatically appends** to the class-level script. By default, Spring uses `SqlMergeMode.MergeMode.OVERRIDE`. Adding `@Sql` to a method suppresses class-level BEFORE/AFTER method-phase declarations for that method. If you expected background data to still be present, the test will fail with missing rows or foreign-key violations.

### 4.3. Merging Explicitly with @SqlMergeMode(MERGE)

~~~java
@Sql("/sql/base-books.sql")
class BookTest {

    @Test
    @Sql("/sql/one-book.sql")
    @SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
    void specialTest() {
        // class-level base-books.sql + method-level one-book.sql.
    }
}
~~~

`MERGE` lets the class's shared fixture execute **alongside** the method's specific fixture. Class-level scripts in the same method phase run before method-level scripts, which works well when the method script has foreign keys pointing to background data. You can place `@SqlMergeMode(MERGE)` on the class as the default for all methods, then add `@SqlMergeMode(OVERRIDE)` on specific methods that need replacement. Method-level merge mode takes precedence over class-level.

**Note:** `@SqlMergeMode` does not change the `BEFORE_TEST_CLASS`/`AFTER_TEST_CLASS` rule from Section 3; those two class phases are independent and are not skipped by method-level scripts.

## 5. Transaction Modes: INFERRED, ISOLATED, and the Risk of Data Leakage

`@Sql` neither defaults to “commit everything” nor defaults to “roll back everything”; it inspects Spring TestContext to see whether an active transaction and suitable transaction manager exist.

### 5.1. INFERRED — The Default Choice

`SqlConfig.TransactionMode.INFERRED` deduces:
1. Neither a `DataSource` nor a transaction manager → script execution fails.
2. `DataSource` present without a transaction manager → executes directly against the `DataSource` with no Spring-managed transaction.
3. Transaction manager present and a transaction is already active (e.g., a test-managed TX) → the script **joins the existing transaction**.
4. Transaction manager present and no transaction is active → starts a **new transaction**, runs the script, and **commits immediately**.

For a default-transactional `@JdbcTest`, a **BEFORE_TEST_METHOD** script runs inside the test transaction and seeded data rolls back at the end of the method. An **AFTER_TEST_METHOD** script under default listener ordering also runs before rollback, so its DML rolls back as well. For **BEFORE_TEST_CLASS** and **AFTER_TEST_CLASS**, no per-method test-managed transaction exists, so scripts typically commit.

### 5.2. ISOLATED — Independent Transaction and Commit

~~~java
@Sql(
    scripts = "/sql/seed-for-external-client.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    ),
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
~~~

This is an annotation snippet, not a complete source class. `ISOLATED` requires a resolvable transaction manager and `DataSource`; Spring opens an **independent transaction**, executes, and commits, even if the test method has its own transaction. This is useful when an HTTP server thread or async worker must see a committed fixture, but **committed data is not automatically removed by test rollback**.

A pair of `ISOLATED` BEFORE/AFTER scripts can seed and later clean up committed data:

~~~java
@SqlGroup({
    @Sql(
        scripts = "/sql/seed-committed.sql",
        config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.ISOLATED
        ),
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
    ),
    @Sql(
        scripts = "/sql/delete-committed.sql",
        config = @SqlConfig(
            transactionMode = SqlConfig.TransactionMode.ISOLATED
        ),
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
    )
})
~~~

Both scripts in the snippet only illustrate configuration; they must be defined and tested against a disposable database. If the test skips teardown callbacks because the JVM dies, SQL fails, or a background thread writes after cleanup, data can still linger. Avoid this pattern on shared databases when stronger isolation is available.

**Never pair an ISOLATED INSERT with an INFERRED DELETE assuming cleanup will stick.** If DELETE runs inside the test-managed transaction and rolls back, the rows committed by the ISOLATED INSERT **reappear** after rollback. Any cleanup of independently committed data must also use an explicit committing transaction/teardown.

### 5.3. @SqlConfig: Parsing and Error Policy Settings

Beyond transaction mode, `@SqlConfig` configures encoding, statement separators, comment delimiters, error handling, `DataSource`, and transaction manager bean names. For example:

~~~java
@Sql(
    scripts = "/sql/seed-utf8.sql",
    config = @SqlConfig(
        encoding = "UTF-8",
        separator = ";"
    )
)
~~~

This is a snippet, not part of the runnable files in Section 7. For scripts containing stored procedure syntax or special SQL dialects, `;` may be inadequate as a separator; verify the appropriate configuration rather than making the parser ignore syntax errors. Never set `errorMode` to ignore all errors just to make tests green; a partially failed script leaves an incomplete fixture.

**Class-level and local config:** `@SqlConfig` on the class serves as global configuration for `@Sql` in the class hierarchy, while `@Sql(config=@SqlConfig(...))` overrides specific attributes explicitly. Attributes left at `DEFAULT`/empty in local config inherit from global config per Spring rules. If a project has multiple `DataSource` beans, configure explicit bean names and verify scripts target the intended database.

## 6. Complete Project: Spring Boot 3.3.5, Java 17, Gradle, H2

This example is designed to **run standalone without PostgreSQL, Redis, or an HTTP server**. To distinguish phases, we use three tables:
- **books**: per-method fixture; INSERTs inside the transaction roll back after the method.
- **phase_events**: a marker intentionally committed by an `ISOLATED` `AFTER_TEST_METHOD` script to prove it runs in the after phase; `@AfterTransaction` verifies and cleans it in `finally`.
- **class_events**: a marker created once by `BEFORE_TEST_CLASS` and deleted once by `AFTER_TEST_CLASS`.

**Do not test against a production database.** The example uses embedded H2 only, distinct demo IDs, and no shared database. Most fixtures live solely inside the test transaction; all independently committed side effects have explicit cleanup.

### 6.1. File Structure

~~~text
settings.gradle
build.gradle
src/main/java/demo/sql/SqlLessonApplication.java
src/test/resources/schema.sql
src/test/resources/sql/base-books.sql
src/test/resources/sql/one-book.sql
src/test/resources/sql/after-method-marker.sql
src/test/resources/sql/class-before.sql
src/test/resources/sql/class-after.sql
src/test/java/demo/sql/SqlMergeModeTest.java
src/test/java/demo/sql/SqlGroupTimingTest.java
src/test/java/demo/sql/SqlClassPhasesTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'sql-test-script-lifecycle'
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

**Gradle rationale:** `starter-jdbc` provides Spring JDBC and transaction support; H2 is on the test runtime classpath; `starter-test` brings JUnit Jupiter, Spring Test, AssertJ, and testing utilities. Spring Boot dependency management selects compatible Spring Framework 6.1 and H2 versions. Spring Data JPA is intentionally omitted so entity flushing and persistence context concepts do not obscure basic `@Sql` behavior.

**src/main/java/demo/sql/SqlLessonApplication.java**

~~~java
package demo.sql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SqlLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(SqlLessonApplication.class, args);
    }
}
~~~

Having the Spring Boot application class in package `demo.sql` lets `@JdbcTest` discover `@SpringBootConfiguration` in the package hierarchy without loading the entire application. There are no REST endpoints or business services in this example.

### 6.2. Schema SQL Created Once When the Test Context Starts

**src/test/resources/schema.sql**

~~~sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(100) NOT NULL
);

CREATE TABLE phase_events (
    code VARCHAR(40) PRIMARY KEY,
    note VARCHAR(100) NOT NULL
);

CREATE TABLE class_events (
    code VARCHAR(40) PRIMARY KEY,
    note VARCHAR(100) NOT NULL
);
~~~

`schema.sql` is processed by Spring Boot SQL initialization when creating the embedded H2 `DataSource`/`ApplicationContext`, **not by `@Sql`**. This differs fundamentally from `/sql/base-books.sql`, which runs according to the test lifecycle. The project omits a default `data.sql` because data is intentionally loaded via `@Sql`.

**Do not confuse the order:**
1. Boot initializes the H2 `DataSource` and runs `schema.sql`.
2. Spring TestContext runs class-level `BEFORE_TEST_CLASS` (if declared on the class).
3. Before each test method, Spring starts the test-managed transaction and runs `@Sql BEFORE_TEST_METHOD`.
4. After the method, `@Sql AFTER_TEST_METHOD` runs according to listener order.
5. Spring rolls back the test transaction.
6. After the whole class, `@Sql AFTER_TEST_CLASS` runs if declared.

When using Flyway/Liquibase for schemas, do not let `schema.sql` and migrations create the same tables and conflict. For real databases, pick one controlled schema migration source.

### 6.3. SQL Fixtures

**src/test/resources/sql/base-books.sql**

~~~sql
INSERT INTO books (id, title) VALUES (1, 'Spring Testing');
INSERT INTO books (id, title) VALUES (2, 'SQL Fixtures');
~~~

**src/test/resources/sql/one-book.sql**

~~~sql
INSERT INTO books (id, title) VALUES (90, 'Method Only');
~~~

**src/test/resources/sql/after-method-marker.sql**

~~~sql
INSERT INTO phase_events (code, note)
VALUES ('AFTER_METHOD', 'committed after-method marker');
~~~

**src/test/resources/sql/class-before.sql**

~~~sql
INSERT INTO class_events (code, note)
VALUES ('CLASS_READY', 'created once before test class');
~~~

**src/test/resources/sql/class-after.sql**

~~~sql
DELETE FROM class_events
WHERE code = 'CLASS_READY';
~~~

**Fixture design explanation:**
- `base-books.sql` and `one-book.sql` only INSERT; they do not DROP tables.
- A test with `OVERRIDE` sees only book `id=90`; a test with `MERGE` sees `1`, `2`, and `90`.
- `after-method-marker.sql` writes to a different table from `books`, preventing test-managed transaction TX-A from holding a lock on rows that isolated script TX-B needs to modify.
- `class-before.sql` and `class-after.sql` form a class-level setup/teardown pair. They use a marker with a stable PK, run on disposable H2, and do not enable parallel execution against a shared schema.
- All SQL resource paths in annotations start with `/sql/`, pointing to files under `src/test/resources/sql/`.

### 6.4. Test 1 — Default @Sql OVERRIDE and @SqlMergeMode(MERGE)

**src/test/java/demo/sql/SqlMergeModeTest.java**

~~~java
package demo.sql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlMergeMode;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
@Sql(
        scripts = "/sql/base-books.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class SqlMergeModeTest {

    @Autowired
    JdbcTemplate jdbc;

    long countBooks() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM books", Long.class);
    }

    @Test
    void classLevelSqlRunsBeforeEachMethod() {
        assertEquals(2L, countBooks());
        assertEquals(
                "Spring Testing",
                jdbc.queryForObject(
                        "SELECT title FROM books WHERE id = ?",
                        String.class, 1L));
    }

    @Test
    @Sql(scripts = "/sql/one-book.sql")
    void methodSqlOverridesClassSqlByDefault() {
        // Method-level @Sql -> default OVERRIDE.
        assertEquals(1L, countBooks());
        assertEquals(
                "Method Only",
                jdbc.queryForObject(
                        "SELECT title FROM books WHERE id = ?",
                        String.class, 90L));
    }

    @Test
    @Sql(scripts = "/sql/one-book.sql")
    @SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
    void mergeRunsClassFixtureBeforeMethodFixture() {
        assertEquals(3L, countBooks());
        assertEquals(
                "SQL Fixtures",
                jdbc.queryForObject(
                        "SELECT title FROM books WHERE id = ?",
                        String.class, 2L));
        assertEquals(
                "Method Only",
                jdbc.queryForObject(
                        "SELECT title FROM books WHERE id = ?",
                        String.class, 90L));
    }

    @Test
    @Sql(statements = {
            "INSERT INTO books (id, title) VALUES (91, 'Inline SQL')"
    })
    void inlineStatementsAlsoOverrideClassScript() {
        assertEquals(1L, countBooks());
        assertEquals(
                "Inline SQL",
                jdbc.queryForObject(
                        "SELECT title FROM books WHERE id = ?",
                        String.class, 91L));
    }
}
~~~

**Four facts confirmed by this test class:**

1. Without a method-level `@Sql`, the class-level fixture seeds two rows **before each test method**, not just once for the class.
2. When a method has its own `@Sql("/sql/one-book.sql")`, `OVERRIDE` applies by default, so **only** `id=90` is present without the two base rows.
3. When a method adds `@SqlMergeMode(MERGE)`, class-level scripts run before method-level scripts, yielding **three rows** (`id=1, 2, 90`).
4. Inline `statements` also act as method-level `@Sql`: they OVERRIDE the class-level fixture by default and insert `id=91`.

Rows in each method are INSERTed inside `@JdbcTest`'s **test-managed transaction** and rolled back after the method. The suite does not depend on method order; if `id=90` leaked from a previous method, count assertions would catch it. In this sample project, rollback works properly so data remains isolated.

**Key technical note:** Using class-level `@Sql` does not require writing `@BeforeEach` to invoke scripts. `SqlScriptsTestExecutionListener` runs scripts before JUnit's `@BeforeEach` lifecycle; tests simply query the data.

### 6.5. Test 2 — @SqlGroup BEFORE/AFTER_METHOD, ISOLATED, and @AfterTransaction

This class demonstrates the difference between **execution timing** and **transaction mode**. `base-books.sql` runs before the method in the test-managed transaction and rolls back. `after-method-marker.sql` runs after the method, but with `@SqlConfig(ISOLATED)`, so it opens a separate transaction and **commits**. `@AfterTransaction` inspects the marker **after rollback**, then cleans it up in `finally`.

**src/test/java/demo/sql/SqlGroupTimingTest.java**

~~~java
package demo.sql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlConfig;
import org.springframework.test.context.jdbc.SqlGroup;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
@SqlGroup({
        @Sql(
                scripts = "/sql/base-books.sql",
                executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD),
        @Sql(
                scripts = "/sql/after-method-marker.sql",
                executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
                config = @SqlConfig(
                        transactionMode =
                                SqlConfig.TransactionMode.ISOLATED))
})
class SqlGroupTimingTest {

    @Autowired
    JdbcTemplate jdbc;

    long countBooks() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM books", Long.class);
    }

    long countMarker() {
        return jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM phase_events
                WHERE code = 'AFTER_METHOD'
                """,
                Long.class);
    }

    @Test
    void beforeMethodDataIsVisibleButAfterMarkerIsNotYetThere() {
        assertTrue(TestTransaction.isActive());
        assertTrue(TransactionSynchronizationManager
                .isActualTransactionActive());

        assertEquals(2L, countBooks());
        assertEquals(0L, countMarker());
    }

    @Test
    void methodWritesAreRolledBackEvenWhenAfterScriptCommits() {
        assertEquals(2L, countBooks());
        jdbc.update(
                "INSERT INTO books (id, title) VALUES (?, ?)",
                3L, "Only During Test");

        assertEquals(3L, countBooks());
        assertEquals(0L, countMarker());
    }

    @AfterTransaction
    void verifyStateAfterTestRollbackAndAlwaysRemoveMarker() {
        assertFalse(TestTransaction.isActive());
        assertFalse(TransactionSynchronizationManager
                .isActualTransactionActive());

        try {
            // AFTER_TEST_METHOD + ISOLATED has committed.
            assertEquals(1L, countMarker());

            // BEFORE_TEST_METHOD and test writes were rolled back.
            assertEquals(0L, countBooks());
        } finally {
            // Independent cleanup: outside the rolled-back transaction.
            jdbc.update(
                    "DELETE FROM phase_events WHERE code = ?",
                    "AFTER_METHOD");
        }
    }
}
~~~

**Actual execution order of a method in this class:**

~~~text
(1) Spring Test opens TX-A for @JdbcTest.
(2) @Sql BEFORE_TEST_METHOD -> base-books.sql inside TX-A.
(3) JUnit @Test -> sees 2 books; does not see AFTER_METHOD marker.
(4) JUnit @AfterEach (if any) -> still before after-method SQL.
(5) @Sql AFTER_TEST_METHOD -> marker script in TX-B ISOLATED.
(6) TX-B commits -> phase_events now holds marker.
(7) Spring Test rolls back TX-A -> base books and test insert disappear.
(8) @AfterTransaction -> sees marker=1, books=0; finally DELETES marker.
~~~

**Why not DELETE from `books` in the ISOLATED AFTER script?** The book rows from step (2) are uncommitted inside TX-A. An independent transaction cannot normally see or delete those uncommitted rows, and may block waiting on a lock. To make the demo deterministic, the AFTER script writes to a **separate marker table**, avoiding row lock contention with TX-A.

**This is not a default cleanup pattern for every project.** It intentionally demonstrates that `ISOLATED` leaves committed side effects that `@JdbcTest` rollback does not undo. When committed fixtures are not needed, let `INFERRED` and test-transaction rollback clean up automatically instead of creating marker tables. When committed seeds are needed for HTTP integration tests, ensure cleanup runs in an appropriate transaction scope or use a disposable database.

**Test independence:** `@AfterTransaction` runs after every method with a test-managed transaction. Using `finally` ensures the marker is cleaned up even if an assertion fails; however, if the JVM is killed or a script/connection fails before cleanup, the marker could linger. Therefore, this project must run on disposable H2, not a shared database or parallel runs using the same marker ID.

### 6.6. Test 3 — @SqlGroup BEFORE_TEST_CLASS and AFTER_TEST_CLASS

The two class phases were added in Spring Framework 6.1. In `SqlClassPhasesTest`, `BEFORE_TEST_CLASS` inserts a committed `CLASS_READY` marker, which all methods can observe. Per-method rollback **does not** remove the committed marker. `AFTER_TEST_CLASS` deletes the marker once the entire class finishes.

**src/test/java/demo/sql/SqlClassPhasesTest.java**

~~~java
package demo.sql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlGroup;
import org.springframework.test.context.transaction.TestTransaction;

import static org.junit.jupiter.api.Assertions.*;

@JdbcTest
@SqlGroup({
        @Sql(
                scripts = "/sql/class-before.sql",
                executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS),
        @Sql(
                scripts = "/sql/class-after.sql",
                executionPhase = Sql.ExecutionPhase.AFTER_TEST_CLASS)
})
class SqlClassPhasesTest {

    @Autowired
    JdbcTemplate jdbc;

    long classMarkerCount() {
        return jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM class_events
                WHERE code = 'CLASS_READY'
                """,
                Long.class);
    }

    @Test
    void classSetupIsVisibleInsideFirstTransactionalMethod() {
        assertTrue(TestTransaction.isActive());
        assertEquals(1L, classMarkerCount());
    }

    @Test
    void classMarkerIsSeparateFromMethodLocalWrites() {
        assertEquals(1L, classMarkerCount());

        jdbc.update(
                "INSERT INTO books (id, title) VALUES (?, ?)",
                500L, "Temporary Book");

        long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM books WHERE id = ?",
                Long.class, 500L);

        assertEquals(1L, count);
        // Method insert will roll back; the class marker stays committed.
    }

    @Test
    @Sql(scripts = "/sql/one-book.sql")
    void methodSqlDoesNotOverrideClassPhases() {
        assertEquals(1L, classMarkerCount());

        long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM books WHERE id = ?",
                Long.class, 90L);

        assertEquals(1L, count);
    }
}
~~~

**The three tests do not rely on execution order**: the word “First” in the first test's name is purely descriptive and requires no JUnit ordering. All three expect the class marker to be created **before any test method runs**. One method INSERTs book 500, which rolls back at the end of the method so other tests stay isolated. The method-level `@Sql` `one-book` runs only within that method's transaction; it **does not disable** class-level `BEFORE_TEST_CLASS` or `AFTER_TEST_CLASS`.

**Why is there no direct assertion for `AFTER_TEST_CLASS` inside the class?** It runs **after all methods and JUnit `@AfterAll`**, so you cannot assert “cleaned up” inside a `@Test` method without fighting the lifecycle. If you must verify cleanup at the suite level, use a test harness/extension or a controlled disposable database—never rely on Class B “happening to run after Class A.” This example focuses on phase behavior and avoiding test-order coupling.

**Warning about class-level data:** If test classes run in parallel on the same schema and share the same class marker key, `class-before` can hit a key collision or `class-after` can delete another class's data. In larger CI suites, use a unique namespace/schema/DB per test class or keep data inside method transactions instead of shared committed state.

## 7. Total Test Count and Run Commands

The project has exactly **9 `@Test` methods**:

| Test Class | Method Count | Focus |
|---|---:|---|
| `SqlMergeModeTest` | **4** | class fixture, method OVERRIDE, MERGE, inline statements |
| `SqlGroupTimingTest` | **2** | BEFORE/AFTER_METHOD, ISOLATED marker, rollback, and `@AfterTransaction` |
| `SqlClassPhasesTest` | **3** | BEFORE/AFTER_CLASS, class scope, and method-level SQL |
| **Total** | **9** | No `@Disabled` methods in the complete example |

**Expected result:** all 9 tests PASS when run with the stated sources, SQL files, and dependencies; rollback and teardown leave empty tables at the end of the test classes in a disposable H2 environment. This is an **expected outcome from design and inspection**, not a claim that tests were executed on the reader's machine.

If the project has a Gradle Wrapper:

~~~bash
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If you just copied the sources without generating the Gradle Wrapper scripts/JAR, `./gradlew` does not exist yet; use a compatible Gradle installation to generate the wrapper or run `gradle test` temporarily. Inspect the report at:

~~~text
build/reports/tests/test/index.html
~~~

Run classes individually to verify scoping:

~~~bash
./gradlew test --tests demo.sql.SqlMergeModeTest
./gradlew test --tests demo.sql.SqlGroupTimingTest
./gradlew test --tests demo.sql.SqlClassPhasesTest
~~~

**If a test group fails due to duplicate marker PK:** verify it runs on a fresh/cleaned H2 database, that `@AfterTransaction` executes, and that classes/suites do not run in parallel with a shared key. Never delete rows arbitrarily in a shared database just to force a test green. Fixtures with committed side effects must be cleaned up within the proper transaction and test scope.

### 7.1. Checking Expected Order Without Relying on Method Names

Observe:
- `SqlMergeModeTest.classLevelSqlRunsBeforeEachMethod()` sees **2** rows.
- `methodSqlOverridesClassSqlByDefault()` sees **1** row (90).
- `mergeRunsClassFixtureBeforeMethodFixture()` sees **3** rows (1, 2, 90).
- `inlineStatementsAlsoOverrideClassScript()` sees **1** row (91).
- `SqlGroupTimingTest` sees **2** books and **0** after markers inside the method, then **1** marker in `@AfterTransaction`, and the `finally` block deletes the marker.
- `SqlClassPhasesTest` sees **1** class marker across all three methods; `class-after.sql` removes the marker when the class completes.

These describe the expected assertions in the source code rather than arbitrary stdout. JUnit does not guarantee method execution order unless explicitly configured; this example is designed to **require no ordering**.

## 8. Where Do @BeforeEach, @AfterEach, @BeforeTransaction, and @AfterTransaction Fit?

Many developers use JUnit lifecycle annotations to run SQL directly and confuse them with `@Sql` phases. In a transactional Spring test, the common timeline is:

~~~text
[Before class]     @Sql BEFORE_TEST_CLASS (once)
[Before method]    @BeforeTransaction
                   Spring opens test-managed transaction
                   @Sql BEFORE_TEST_METHOD
                   JUnit @BeforeEach
                   JUnit @Test
                   JUnit @AfterEach
                   @Sql AFTER_TEST_METHOD
                   Spring rolls back or commits test transaction
                   @AfterTransaction
[Repeat methods]
[After class]      @Sql AFTER_TEST_CLASS (once)
~~~

**Note:** `@BeforeTransaction` runs before each test transaction and `@AfterTransaction` runs after it; they are not invoked like `@BeforeEach`/`@AfterEach` when a test is non-transactional. Spring TestContext determines when to invoke hooks based on listeners. `@BeforeAll` and `@AfterAll` belong to the JUnit class lifecycle, which is distinct from `@Sql`'s `BEFORE_TEST_CLASS`/`AFTER_TEST_CLASS`.

Context-accurate illustrative snippet:

~~~java
@BeforeTransaction
void beforeTx() {
    assertFalse(TestTransaction.isActive());
}

@BeforeEach
void beforeEach() {
    assertTrue(TestTransaction.isActive());
}

@AfterEach
void afterEach() {
    // Test TX is usually still open here.
    assertTrue(TestTransaction.isActive());
}

@AfterTransaction
void afterTx() {
    assertFalse(TestTransaction.isActive());
}
~~~

This is an auxiliary snippet inside a `@JdbcTest` class with corresponding imports, **not a standalone source file**. If a test is annotated with `@Commit` or `@Rollback(false)`, uses special propagation, or switches threads inside callbacks, the rules and expected states differ. Never rely on `@AfterEach` to prove an `AFTER_TEST_METHOD` script has already run or that data has rolled back.

### 8.1. How to Verify Exactly When an AFTER Script Runs

There are three suitable approaches depending on your needs:
1. Inspect a marker table in `@AfterTransaction` as shown in the example, with the AFTER script running `ISOLATED` and cleanup in `finally`.
2. Write a custom `TestExecutionListener` that records events in memory, carefully managing listener order and test instances.
3. Enable `DEBUG` logs for `org.springframework.test.context.jdbc` and `org.springframework.jdbc.datasource.init` to trace script and statement execution.

Do not inspect a `SELECT` at the end of a `@Test` method and conclude that `AFTER_TEST_METHOD` failed or succeeded: the AFTER callback executes **after the test method body**.

## 9. How @Sql Differs from schema.sql, data.sql, @BeforeEach, and Migration Tools

| Tool | When It Runs | Best Fit | Risks |
|---|---|---|---|
| Boot `schema.sql` | At DataSource/context initialization | Creating base embedded schemas | Collides with migrations or production schemas |
| Boot `data.sql` | At initialization (per config) | Seeding simple reference data | Shared fixture, not reset per method |
| Spring Test `@Sql BEFORE_TEST_METHOD` | Before each method | Isolated rows/fixtures, easy rollback | Can be overridden by method-level `@Sql` |
| Spring Test `@Sql AFTER_TEST_METHOD` | After each method, before default rollback | Cleanup/custom state in TX; `ISOLATED` if commit needed | Cleanup inside TX can roll back |
| Spring Test `@Sql BEFORE_TEST_CLASS` | Before the whole class | Class-wide reference data/schema | Committed data persists across methods |
| Spring Test `@Sql AFTER_TEST_CLASS` | After the whole class | Teardown for class-level committed fixtures | Does not prevent parallel collisions on its own |
| JUnit `@BeforeEach` | Before test code | Setting up objects/mocks and tiny data | Repetitive setup code |
| Flyway/Liquibase | Schema migration at runtime/context startup | Versioned schema evolution | Does not automatically seed per-method test fixtures |
| Testcontainers | Container lifecycle managed by test setup | Production DB / dialect-specific tests | Slower startup and execution than H2 |

**Do not put the same `CREATE TABLE` in `schema.sql`, a Flyway migration, and `@Sql(BEFORE_TEST_CLASS)` without coordination**, or it may execute multiple times against the same `DataSource` and fail with “table already exists.” When a schema genuinely requires versioned migrations, let Flyway/Liquibase manage the schema and reserve `@Sql` for test-specific data fixtures.

**Do not force everything into `@BeforeEach` when `@Sql` is cleaner:** Scripts are reusable and allow fine control over phase and transaction mode. Conversely, a few simple rows or method-specific dynamic data may be clearer using `JdbcTemplate` or Java test data builders. Choose the tool that makes intent clearest.

## 10. Common Pitfalls and How to Fix Them

### 10.1. Using AFTER_TEST_METHOD DELETE, Yet Data Remains

Suppose:

~~~java
@Test
@Sql(
    scripts = "/sql/seed-committed.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
@Sql(
    scripts = "/sql/cleanup.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
void testExternalClient() {
    // Seed script committed independently; cleanup defaults to INFERRED.
}
~~~

If the test has a test-managed TX, an `INFERRED` AFTER cleanup can run **inside the test TX and roll back**, leaving the independently committed seed rows intact. You must declare matching `ISOLATED` cleanup or use a disposable DB with reliable teardown—never assume AFTER implies commit.

### 10.2. Adding Method-Level @Sql Drops the Class Fixture

~~~java
@Sql("/sql/base-books.sql")
class FixtureTest {

    @Test
    @Sql("/sql/one-book.sql")
    void specialCase() {
        // Class fixture does not run by default.
    }
}
~~~

If both are needed, add `@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)` on the method or class. If full replacement is desired, keep `OVERRIDE` and write assertions tailored strictly to the method's data.

### 10.3. Assuming Class-Level @Sql Runs Only Once

~~~java
@Sql("/sql/base-books.sql")
class ManyMethodsTest {
    // Default BEFORE_TEST_METHOD: runs before each test.
}
~~~

If the script performs an `INSERT` with a primary key and data is not rolled back or cleaned up, the second method will fail with a duplicate key error. In transactional `@JdbcTest`, inserts roll back cleanly; in non-transactional tests, add cleanup or switch to `BEFORE_TEST_CLASS` (if the data is class-level immutable and properly torn down).

### 10.4. `@Sql` Cannot Find the File

- Verify `src/test/resources/sql/...` is included on the test classpath.
- Check whether the path has a leading `/` or is relative to the package.
- If using `@Sql` without `scripts`/`statements`, verify the default class/method script naming convention.
- Do not expect Boot SQL init's `schema.sql` to be inferred automatically as `@Sql("/sql/...")`.
- Check encoding if scripts contain Unicode/SQL strings, and `separator` if using procedures or multi-statement blocks.

### 10.5. AFTER_TEST_CLASS Cleanup Does Not Run as Expected

If the test process is killed or the JVM crashes, teardown listeners cannot guarantee external data is always cleaned up. If the app connects to a shared database, another class may be running concurrently. Use a dedicated test database/schema per suite, Testcontainers, unique test keys, idempotent cleanup scripts, and avoid shared production resources.

### 10.6. Multiple DataSources or Transaction Managers

`@Sql` must target the right `DataSource`. When multiple beans of the same type exist in the context, Spring may fail to disambiguate or pick an unintended bean. Configure `@SqlConfig(dataSource = "reportingDataSource", transactionManager = "reportingTransactionManager")` when needed. Never convert every test into `@SpringBootTest` just to mask a bean selection issue.

### 10.7. SQL Dialect Differences

H2 is great for learning lifecycle mechanics, whereas PostgreSQL, MySQL, and Oracle differ in syntax, transactional DDL, locking, identity generation, and JSON/UUID types. If scripts use production-specific syntax, run them on Testcontainers with the matching driver and schema. `@Sql` does not translate SQL dialects.

## 11. Checklist for Designing Reliable SQL Fixtures

1. **Pick the right phase:** per-test data → `BEFORE_TEST_METHOD`; class-wide data → `BEFORE_TEST_CLASS` with cleanup; post-test hooks → `AFTER_TEST_METHOD`/`AFTER_TEST_CLASS`.
2. **Define rollback/commit policy explicitly:** test-managed transaction + `INFERRED` for rollback; `ISOLATED` only when external workers truly need committed data.
3. **Check class vs. method annotations:** method-level defaults to `OVERRIDE`; use `MERGE` when both must run.
4. **Use explicit absolute classpath paths** like `/sql/base-books.sql`, avoiding working-directory assumptions.
5. **Keep scripts simple and ordered intentionally:** schemas before data; reference tables before tables with foreign keys.
6. **Test at least 0, 1, and many rows** along with nonexistent rows or unique constraint violations when relevant to business rules.
7. **Keep IDs/namespaces isolated:** data shared across classes causes collisions when JUnit runs in parallel.
8. **Avoid production and shared DBs:** use only embedded H2 or dedicated test databases; cleanup scripts often contain dangerous DELETE/DROP statements.
9. **Never rely on test method execution order:** fixtures must let every test run independently.
10. **Verify after rollback when that is the contract:** use `@AfterTransaction`, not just `@AfterEach`.
11. **Inspect logs on failure:** `org.springframework.test.context.jdbc=DEBUG`, `org.springframework.jdbc.datasource.init=DEBUG`.
12. **With `ISOLATED`, ensure cleanup actually commits** and use `finally`/out-of-transaction teardown or disposable databases.
13. **Do not abuse `errorMode` to ignore errors:** failing SQL scripts should fail tests to prevent false positives.
14. **Verify against the production database engine** when vendor-specific SQL or type conversions are involved.
15. **Clarify the relationship with schema migrations** so schemas are never created twice.

## 12. Self-Practice Exercises

**Exercise 1 — Default phase:** Place class-level `@Sql("/sql/base-books.sql")` on a test class with three methods. Why does the script run before each method? If the class is non-transactional, what causes a duplicate-key failure?

**Exercise 2 — OVERRIDE/MERGE:** Create a method with `@Sql("/sql/one-book.sql")` and assert count = 1. Add `@SqlMergeMode(MERGE)` and assert count = 3. Why is this not merely a “cosmetic syntax change”?

**Exercise 3 — Two-phase group:** Build a `@SqlGroup` with `BEFORE_METHOD` seed and `AFTER_METHOD` cleanup. In a default `@JdbcTest`, does the AFTER cleanup commit independently? Explain using listener order.

**Exercise 4 — Isolated:** Switch AFTER cleanup to `ISOLATED`; in disposable H2, write a marker to a separate table, verify it in `@AfterTransaction`, and delete the marker. Why should you avoid updating the same row locked by TX-A?

**Exercise 5 — Class phases:** Use `BEFORE_TEST_CLASS`/`AFTER_TEST_CLASS` to create and clean up a reference row. Add a method-level `@Sql` and verify class-phase scripts are not overridden.

**Exercise 6 — Default resource:** Omit `scripts` and `statements` from `@Sql` on a class and method; determine the filenames Spring searches based on package + class/method. Create the matching file, then intentionally rename it to observe the setup error.

**Exercise 7 — Inline statements:** Write `@Sql(statements = "...")` for a simple case. When are inline statements more readable than a separate SQL file?

**Exercise 8 — Schema migration:** Add a Flyway migration to create tables. When should `schema.sql` be removed to avoid running DDL twice? When a test needs dedicated seed data, which phase fits `@Sql`?

**Exercise 9 — Two DataSources:** Suppose you have reader/writer DataSources or tenant databases. How do you configure `@SqlConfig(dataSource, transactionManager)` so scripts never hit the wrong DB?

**Exercise 10 — Parallel tests:** Have two classes share the same class-phase marker ID. What errors can happen in parallel runs? Design unique IDs, schemas, or separate containers.

**Exercise 11 — Specific database:** Run the same SQL scripts against PostgreSQL Testcontainers. Compare DDL, transaction isolation, and script separators with H2.

**Exercise 12 — Inspect lifecycle:** Enable `DEBUG` logging for Spring Test JDBC and read the sequence `BEFORE_METHOD` → test → `AFTER_METHOD` → transaction rollback. Use `@AfterTransaction` to assert the final state.

## 13. Official References

- [Spring Framework 6.1 — Executing SQL Scripts](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/executing-sql.html): `@Sql`, `@SqlGroup`, script paths, default detection, execution phases, merge, and transactions.
- [Spring Framework 6.1 — SqlScriptsTestExecutionListener API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/jdbc/SqlScriptsTestExecutionListener.html): listener methods, class phases, order 5000.
- [Spring Framework 6.1 — SqlConfig.TransactionMode API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/jdbc/SqlConfig.TransactionMode.html): `INFERRED`, `ISOLATED`, and commit/rollback conditions.
- [Spring Framework — @SqlMergeMode](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-sqlmergemode.html): `OVERRIDE`/`MERGE` at class and method levels.
- [Spring Framework — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): test-managed transactions, `@AfterTransaction`, listener ordering, and rollback.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@JdbcTest`, transactional rollback, and embedded databases.
- [Spring Boot 3.3 — Test Slice Auto-configurations](https://docs.spring.io/spring-boot/3.3/appendix/test-auto-configuration/slices.html): `@JdbcTest` and SQL initialization.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): `schema.sql`, `data.sql`, and interaction with migrations.
- [Spring Framework — @AfterTransaction API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/transaction/AfterTransaction.html): running after transactional tests.

**Remember:** `@Sql` has **phase**, **class/method scope**, **merge rules**, and **transaction mode**—you must inspect all four, not just the `.sql` filename. By default it runs before each test method; method-level scripts OVERRIDE class fixtures; `@SqlMergeMode(MERGE)` combines them. `@SqlGroup` only groups multiple `@Sql` declarations without creating a new transaction. `AFTER_TEST_METHOD` in transactional tests typically runs **before rollback**, whereas `ISOLATED` commits independently and requires explicit cleanup. From Spring 6.1+, class phases run once before/after the class and are not overridden by method-level `@Sql`.
