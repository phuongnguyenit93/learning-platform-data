# Test Transactions: Test-Managed Transactions, Application Transactions, and Database Transactions

## 1. Why is @Transactional on Tests Easily Misunderstood?

A Spring Boot test calls `orderService.save(...)`, queries the database, sees the newly inserted record, and all assertions PASS. Yet when the test ends, the record disappears. In another test, you make a real HTTP call to `POST /orders` from a test that also has `@Transactional`, yet the record **does not disappear**. Both outcomes can be completely valid, because **test-managed transactions**, **application-managed transactions**, and **physical transactions executed by the database** have different boundaries.

This lesson focuses on exactly these three mechanisms:

- **Test-managed transaction:** opened by Spring TestContext before a test method and **rolled back by default** after the test.
- **Spring/application transaction:** requested by a service's `@Transactional`/proxy or `TransactionTemplate`. It can join an existing transaction or open/commit/roll back its own.
- **Database transaction:** executed by the DB/driver through connections, isolation, locks, `COMMIT`, `ROLLBACK`, and savepoints. An application transaction does not mean a "fake database."

There is no default rule that "three layers = three separate transactions." When the test and the service use the same transaction manager, the same thread, and `REQUIRED` propagation, they usually share **a single physical transaction**.

### Objectives

After this lesson, you can:

1. Identify **who opens and who owns commit/rollback** in `@SpringBootTest`, `@JdbcTest`, and `@DataJpaTest` tests.
2. Explain how `@Transactional` on a test differs from `@Transactional` on a service.
3. Know when `REQUIRED` joins the test transaction and when `REQUIRES_NEW` commits independently.
4. Use `@BeforeTransaction`, `@AfterTransaction`, `TestTransaction`, `@Commit`, and `@Rollback`.
5. Test checked/unchecked exception rollback rules without being masked by a test transaction.
6. Prove that an HTTP request over `RANDOM_PORT` does not automatically share the JUnit thread's transaction.
7. Distinguish `flush()`, constraint enforcement, savepoints, rollback-only, database isolation, and commit.
8. Write repeatable integration tests, knowing when to clean up instead of relying on rollback.
9. Avoid pitfalls with `assertTimeoutPreemptively`, self-invocation, `@Async`, reactive contexts, and different DB transactions.
10. Choose the right test to prove real application behavior rather than only testing code inside a "test-supplied transaction."

## 2. Three-Layer Transaction Diagram

~~~text
JUnit Jupiter test thread
      |
      v
Spring TransactionalTestExecutionListener
      |        @Transactional test => BEGIN test-managed TX
      |        JDBC connection A is bound to the test thread
      v
@Test method
      |
      +----> Spring proxy OrderService.create() @Transactional(REQUIRED)
                   |
                   +-- TransactionInterceptor / PlatformTransactionManager
                   |      sees the current transaction
                   |      joins the transaction on connection A
                   |
                   +-- JdbcTemplate INSERT
                           |
                           v
                        Database
                           |
                           +-- row present in TX A, NOT YET COMMITTED
      |
      v
@Test ends
      |
      +-- Spring TestContext rolls back TX A by default
      |
      +-- row disappears, even though the service returned normally
~~~

Replacing `REQUIRED` with `REQUIRES_NEW`:

~~~text
Connection A: test transaction (uncommitted)
      |
      +--- calls another bean, @Transactional(REQUIRES_NEW) method
                  |
                  +-- temporarily suspends TX A resources
                  +-- acquires Connection B
                  +-- BEGIN TX B
                  +-- INSERT audit
                  +-- COMMIT TX B
                  +-- resumes TX A
      |
      +--- TestContext ROLLBACK TX A

RESULT: row from TX A is gone; audit from TX B remains.
~~~

The scenario above requires the Spring proxy to actually intercept the bean call, the transaction manager to support propagation, and the connection pool to have enough connections.

### Precise Terminology

Spring Framework may refer to:

- **Test-managed:** managed by `TransactionalTestExecutionListener` or `TestTransaction`.
- **Spring-managed:** transactions managed directly by Spring within the application context, typically via `@Transactional`.
- **Application-managed:** the application uses the transaction manager programmatically, for example `TransactionTemplate`.

In this topic, "application transaction" covers both **declarative transactions on Spring services** and **transactions controlled programmatically by application code**. Both can use `PlatformTransactionManager`. A "database transaction" is the **real physical transaction**, not another name for an annotation.

## 3. Comparison Table

| Question | Test-managed | Application/Spring-managed | Database transaction |
| --- | --- | --- | --- |
| Who triggers it? | TestContext listener or `TestTransaction` | Transactional proxy or `TransactionTemplate` | Transaction manager/JDBC driver/DB session |
| Where configured | Test `@Transactional`, `@Rollback`/`@Commit` | Service `@Transactional`, propagation, rollback rules | Connection, isolation, autocommit, constraints |
| Default ending | **Rollback after test** | Commit on success, roll back per rules | Actual commit/rollback controlled by caller |
| Can share same physical TX? | Yes | Yes if REQUIRED joins | Only one TX when sharing connection |
| Crosses HTTP? | Not automatically | HTTP server usually opens its own TX | Independent server connection |
| What it proves | Test code runs in a TX and rolls back per TestContext | Business commit/rollback at real boundary | Visibility, constraints, locks, durable state |
| Rolls back mail/Kafka/files? | Not automatically | Not automatically | No |
| Rolls back committed REQUIRES_NEW? | No | Outer TX does not roll back inner commit | Commit B is independent of rollback A |

**When verifying the database:** always answer four questions: which transaction manager, which connection, which thread, and who commits/rolls back?

## 4. Test-Managed Transaction: Spring TestContext Mechanism

`TransactionalTestExecutionListener` is registered by default by Spring TestContext. When a test class/method has Spring's `@Transactional` and the context has a matching `PlatformTransactionManager`, the listener starts a test-managed transaction before the test body, typically binds the resource to the current thread, and rolls it back after the method.

This is why the following test does not persist data permanently even though the SQL executes successfully:

~~~java
@SpringBootTest
@Transactional
class ExampleTest {
    @Autowired OrderService service;

    @Test
    void create() {
        service.create("O-1");
        // Data is present inside the test transaction.
    } // Spring TestContext rolls back after the test
}
~~~

**This snippet is illustrative**: it requires a real `OrderService`, datasource/transaction manager, and imports. Do not claim the service method commits on its own if it is joining an outer transaction.

### 4.1 Full Lifecycle of a Test Method

~~~text
Create ApplicationContext and inject dependencies
          |
          v
@BeforeTransaction         OUTSIDE transaction
          |
          v
TestContext BEGIN transaction
          |
          v
JUnit Jupiter @BeforeEach  INSIDE transaction
          |
          v
JUnit Jupiter @Test        INSIDE transaction
          |
          v
JUnit Jupiter @AfterEach   INSIDE transaction
          |
          v
TestContext ROLLBACK (default) / COMMIT (when requested)
          |
          v
@AfterTransaction          OUTSIDE transaction
~~~

`@BeforeTransaction` and `@AfterTransaction` only run for **test methods that actually have a test-managed transaction**. `@BeforeAll`/`@AfterAll` are not inside any individual method's transaction. Placing `@Transactional` solely on a `@BeforeEach` lifecycle method does not create a new test-managed transaction just for that method.

### 4.2 @Transactional Attribute Support at the Test Level

| @Transactional Attribute | Does Spring TestContext use it to manage the test TX? |
| --- | --- |
| `value` or `transactionManager` | Yes, to select the manager |
| `propagation=NOT_SUPPORTED` or `NEVER` | Yes, the test will **not** be wrapped in a test-managed TX |
| `REQUIRED`/`REQUIRES_NEW`/`NESTED` and other propagations | Does not apply full proxy-level propagation semantics to the test itself |
| `isolation` | Not supported by TestContext |
| `timeout` | Not supported by TestContext |
| `readOnly` | Not supported by TestContext |
| `rollbackFor`/`noRollbackFor` | Not used for the test rollback policy |

Instead of `@Transactional(rollbackFor=...)` **on a test**, use `@Rollback`, `@Commit`, or `TestTransaction.flagForRollback()/flagForCommit()`. Meanwhile, `rollbackFor` **on a Spring service** is application transaction configuration that takes effect when transactional advice runs.

## 5. @Rollback, @Commit, and TestTransaction

By default, Spring TestContext **rolls back** the test transaction whether assertions PASS or FAIL.

~~~java
@SpringBootTest
@Transactional
class ExampleTest {

    @Test
    void defaultRollback() {
        // rolled back after the test
    }

    @Test
    @Commit
    void commitAfterTest() {
        // committed after the test; database cleanup required
    }

    @Test
    @Rollback(false)
    void equivalentCommit() {
        // committed after the test
    }
}
~~~

This is an **annotation pattern, not a standalone runnable project**.

`TestTransaction` provides an API to control the transaction **directly inside the test**:

~~~java
assertTrue(TestTransaction.isActive());

service.create("DEMO-1");

TestTransaction.flagForCommit();   // only sets the flag
TestTransaction.end();             // actual COMMIT happens here
assertFalse(TestTransaction.isActive());

assertEquals(1, countRows("DEMO-1")); // read outside test TX

// You can call TestTransaction.start() to open a new test-managed TX.
~~~

This is an illustrative snippet inside a test that already has Spring transactions and helpers configured. If you actually commit without cleaning up, the record remains for subsequent tests.

**Distinction:** `TestTransaction` is a Spring TestContext API; `TransactionTemplate` is the application's programmatic transaction API. `TestTransaction.flagForCommit()` does not execute SQL COMMIT until the transaction ends.

## 6. Service @Transactional and Propagation

Important propagation modes:

| Propagation | If a test TX already exists | Notable outcome |
| --- | --- | --- |
| `REQUIRED` | Joins test TX | Test rollback also cancels service writes |
| `SUPPORTS` | Joins if present | A test with a TX can mask non-production behavior |
| `MANDATORY` | Succeeds because test has TX | Production caller without TX will be rejected |
| `REQUIRES_NEW` | Suspends test TX, opens independent TX | Inner commit survives test rollback |
| `NESTED` | Usually uses a savepoint on same physical TX | Does not commit independently like REQUIRES_NEW |
| `NOT_SUPPORTED` | Suspends test TX, runs without Spring TX | JDBC auto-commit may persist writes |
| `NEVER` | Throws error if a TX exists | Test-level @Transactional causes the method to be rejected |

`REQUIRES_NEW` typically requires an additional connection; if the outer TX holds one connection and the pool maximum is only one, the inner TX may wait until timeout. Spring recommends that the pool size exceed the number of concurrent threads by at least one connection if the design uses `REQUIRES_NEW`.

### 6.1 REQUIRED and UnexpectedRollbackException

An inner `@Transactional(REQUIRED)` service throwing an unchecked exception through a proxy can mark the shared transaction `rollback-only`. Catching the Java exception in the outer service does not mean the transaction can commit:

~~~java
@Transactional
public void outer() {
    try {
        collaborator.writeAndFail(); // @Transactional(REQUIRED)
    } catch (RuntimeException ex) {
        // Caught, but physical TX may already be marked rollback-only.
    }
    // When outer tries to commit, it may receive UnexpectedRollbackException.
}
~~~

This is an explanatory example (requires `collaborator`). When designing for partial failure, use savepoints/`NESTED` or an independent transaction if business semantics allow, rather than arbitrarily swallowing exceptions.

### 6.2 REQUIRES_NEW vs. NESTED

**REQUIRES_NEW** opens an independent physical transaction with its own commit/isolation/locks/connection. **NESTED** usually sets a savepoint inside a single physical transaction; rolling back to the savepoint does not terminate the outer transaction, yet an outer rollback still cancels all writes in the nested scope.

Do not use REQUIRES_NEW just to "work around test failures": if an audit transaction committed while the order transaction rolled back, the audit must be designed with the right meaning (e.g., recording an attempt, not completion).

## 7. Checked Exceptions, Runtime Exceptions, and Rollback Rules

Standard Spring `@Transactional` (with Spring Framework 6.2 defaults):

- `RuntimeException` or `Error` exiting the transactional proxy → rollback.
- Checked exception such as `IOException` → **does not roll back by default**.
- You can use `@Transactional(rollbackFor = IOException.class)` when a domain rule requires rollback.
- Once a transaction is marked rollback-only, an outer method returning normally still does not guarantee a commit.

~~~java
@Transactional
public void afterUnchecked() {
    insert();
    throw new IllegalStateException("fail");   // rollback
}

@Transactional
public void afterChecked() throws IOException {
    insert();
    throw new IOException("checked");            // commits by default
}

@Transactional(rollbackFor = IOException.class)
public void afterCheckedWithRollback() throws IOException {
    insert();
    throw new IOException("checked");            // rollback
}
~~~

These three methods are samples in a service that already has `insert()`. **You must verify from outside the application transaction**—do not place test-level `@Transactional` and conclude that the service itself committed or rolled back.

## 8. Physical Database Transactions, Connections, and Isolation

An actual transaction occurs on a connection/session:

~~~text
Connection A: BEGIN
  INSERT order O-1
  SELECT O-1     -> sees the transaction's own row
Connection B: SELECT O-1 -> may NOT see it (READ COMMITTED)
Connection A: ROLLBACK
Connection B: SELECT O-1 -> does not see it

COMMIT case:
Connection A: BEGIN -> INSERT -> COMMIT
Connection B: SELECT O-1 -> sees the committed row
~~~

`JdbcTemplate` uses Spring's transaction-aware connection retrieval; on the same thread with the same transaction manager, multiple JDBC calls can share the same connection/transaction.

**Notes:**

- JDBC outside a Spring TX typically runs in auto-commit mode. Calling `JdbcTemplate.update` without an enclosing transaction can commit the statement immediately.
- Read-your-writes is **not** proof of commit. A query right inside the test transaction can see uncommitted data.
- DB-level isolation (`READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`…) has different semantics across PostgreSQL, MySQL, and H2.
- DB constraints/triggers/DDL may execute at SQL/flush time or at commit time, depending on the feature.
- A DB rollback does not undo sent emails, executed HTTP payment calls, or written files.
- With PostgreSQL, after an SQL error inside a transaction, subsequent statements may receive SQLSTATE `25P02` until rollback. H2 does not fully emulate this behavior.

### 8.1 Flush vs. Commit

With JPA/Hibernate:

~~~text
repository.save(entity) -> entity is managed in the persistence context
entityManager.flush()   -> pushes pending SQL to the DB inside the transaction
entityManager.clear()   -> evicts cached/managed entities from the persistence context
transaction.commit()    -> commits the physical transaction
~~~

`flush()` is often needed to catch SQL/unique constraints early and avoid false positives, but **flush is not commit**. After flush, Spring TestContext can still roll back.

Illustrative example in `@DataJpaTest`:

~~~java
repository.save(entity);
entityManager.flush();
entityManager.clear();

var found = repository.findById(id).orElseThrow();
assertEquals(expected, found.getValue());
~~~

This tests the real persistence query better than just re-reading a managed entity. However, if the goal is **deferred constraints or after-commit listeners**, you need a test with a **real commit**.

## 9. @JdbcTest, @DataJpaTest, @DataJdbcTest, and @SpringBootTest

| Annotation | Scope | Default test-managed TX |
| --- | --- | --- |
| `@JdbcTest` | DataSource, JdbcTemplate, and JDBC infrastructure | Yes, rolled back after test |
| `@DataJdbcTest` | Spring Data JDBC repositories and JDBC infrastructure | Yes, rolled back after test |
| `@DataJpaTest` | EntityManager, JPA repositories, and transaction support | Yes, rolled back after test |
| `@SpringBootTest` | Full application context, server depending on webEnvironment | Does not wrap each test by default; add `@Transactional` if needed |

Data/JPA/JDBC slices typically use an embedded database when the dependency is on the classpath and configuration allows it. If SQL depends on vendor features, use Testcontainers with the appropriate DB. You cannot prove PostgreSQL locking/SQLSTATE on H2 just because tests PASS.

A common mistake is using `@DataJpaTest` with its built-in transaction and concluding that a production service has `@Transactional` configured properly. Data slice tests verify repository SQL; service transaction boundaries need a **separate test without a test-managed transaction**.

## 10. Complete Example: Java 17+ / Spring Boot 3.5.x

The practice suite has **four test classes and 12 JUnit Jupiter methods**:

- 3 tests: Spring TestContext test-managed lifecycle, REQUIRED/MANDATORY, uncommitted data invisible to another connection.
- 6 tests: application-level commit, runtime rollback, checked exception, rollbackFor, REQUIRES_NEW, MANDATORY without a transaction.
- 2 tests: `TestTransaction` commit/rollback/end/start.
- 1 test: real HTTP server running its own transaction and committing despite test-level rollback.

Uses **Spring JDBC + H2 test database**, no Docker required. For production, separate real database/migration/security configuration is required.

### 10.1 Structure

~~~text
src/
  main/java/example/txdemo/
    TxDemoApplication.java
    AuditService.java
    OrderService.java
    OrderController.java
  test/java/example/txdemo/
    TestManagedTransactionTest.java
    ApplicationTransactionTest.java
    TestTransactionControlTest.java
    HttpTransactionBoundaryTest.java
  test/resources/
    schema.sql
    application.properties
~~~

The files use package `example.txdemo`. Tests sit under the same package hierarchy as `@SpringBootApplication`.

### 10.2 build.gradle Dependencies

In a project already configured with the Spring Boot 3.5.x plugin/dependency management and Java 17 toolchain, you need:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is a **dependencies snippet**, not a complete `build.gradle`. `starter-web` is only needed for the HTTP example; core JDBC tests can run without an MVC server.

### 10.3 src/test/resources/schema.sql

~~~sql
CREATE TABLE IF NOT EXISTS tx_order (
    order_id VARCHAR(80) PRIMARY KEY,
    note VARCHAR(200) NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_event (
    event_key VARCHAR(80) PRIMARY KEY
);
~~~

Tests use H2 in-memory. Production should use Flyway/Liquibase migrations; **do not use test DDL directly on a production DB**.

### 10.4 src/test/resources/application.properties

~~~properties
spring.datasource.generate-unique-name=true
spring.datasource.hikari.maximum-pool-size=8
spring.datasource.hikari.transaction-isolation=TRANSACTION_READ_COMMITTED
spring.sql.init.mode=always
~~~

Unique in-memory database per ApplicationContext; pool large enough for 2 connections during REQUIRES_NEW; READ_COMMITTED isolation for visibility testing; SQL init reads the schema. This configuration does not imply H2 behaves like every DB vendor.

## 11. Production Code: Application and Services

### 11.1 TxDemoApplication.java

~~~java
package example.txdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxDemoApplication.class, args);
    }
}
~~~

### 11.2 AuditService.java

~~~java
package example.txdemo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditService {

    private final JdbcTemplate jdbc;

    public AuditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String eventKey) {
        jdbc.update(
                "INSERT INTO audit_event(event_key) VALUES (?)",
                eventKey);
    }
}
~~~

Calling `AuditService.record` through **another bean** ensures the Spring AOP proxy handles REQUIRES_NEW. The audit action commits independently and **should not be mistaken for final order success** if the outer transaction subsequently rolls back.

### 11.3 OrderService.java

~~~java
package example.txdemo;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final JdbcTemplate jdbc;
    private final AuditService audit;

    public OrderService(
            JdbcTemplate jdbc,
            AuditService audit) {
        this.jdbc = jdbc;
        this.audit = audit;
    }

    @Transactional
    public void create(String id) {
        insert(id, "created");
    }

    @Transactional
    public void createThenThrowRuntime(String id) {
        insert(id, "runtime");
        throw new IllegalStateException("runtime failure");
    }

    @Transactional
    public void createThenThrowChecked(String id)
            throws IOException {
        insert(id, "checked");
        throw new IOException("checked failure");
    }

    @Transactional(rollbackFor = IOException.class)
    public void createThenRollbackChecked(String id)
            throws IOException {
        insert(id, "checked rollback");
        throw new IOException("checked failure");
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void createMandatory(String id) {
        insert(id, "mandatory");
    }

    @Transactional
    public void createThenFailAfterAudit(
            String orderId, String eventKey) {
        insert(orderId, "outer");
        audit.record(eventKey);
        throw new IllegalStateException("outer failure");
    }

    private void insert(String id, String note) {
        jdbc.update(
                "INSERT INTO tx_order(order_id, note) VALUES (?, ?)",
                id, note);
    }
}
~~~

The `public` methods are entrypoints called through the bean/proxy from tests/controller. `createThenThrowChecked` tests default Spring 6.2 behavior: checked exceptions do not automatically roll back unless the policy has been changed. The `createThenFailAfterAudit` method demonstrates outer rollback and independent audit commit.

### 11.4 OrderController.java

~~~java
package example.txdemo;

import java.net.URI;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @PostMapping("/orders/{id}")
    public ResponseEntity<Void> create(@PathVariable("id") String id) {
        orders.create(id);
        return ResponseEntity
                .created(URI.create("/orders/" + id))
                .build();
    }
}
~~~

The endpoint is intentionally simple. In production, ID validation, authentication/authorization, and idempotency are required; this example is not a complete order API.

## 12. Test-Managed Transaction: Checking Both Before and After Rollback

File `src/test/java/example/txdemo/TestManagedTransactionTest.java`:

~~~java
package example.txdemo;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@Transactional
@DisplayName("Test transaction: lifecycle and rollback")
class TestManagedTransactionTest {

    @Autowired OrderService orders;
    @Autowired JdbcTemplate jdbc;
    @Autowired PlatformTransactionManager txManager;

    @BeforeTransaction
    void beforeTransaction() {
        assertFalse(
                TransactionSynchronizationManager
                        .isActualTransactionActive());
    }

    @BeforeEach
    void beforeEachRunsInsideTransaction() {
        assertTrue(TestTransaction.isActive());
        assertTrue(
                TransactionSynchronizationManager
                        .isActualTransactionActive());
    }

    @AfterEach
    void afterEachStillInsideTransaction() {
        assertTrue(TestTransaction.isActive());
    }

    @AfterTransaction
    void afterRollbackRowsAreGone() {
        assertFalse(TestTransaction.isActive());

        Integer remaining = jdbc.queryForObject("""
                SELECT COUNT(*) FROM tx_order
                WHERE order_id LIKE 'TMT-%'
                """, Integer.class);
        assertEquals(0, remaining.intValue());
    }

    @Test
    @DisplayName("REQUIRED service shares the test transaction")
    void requiredJoinsTestTransaction() {
        orders.create("TMT-REQUIRED");

        assertEquals(1, count("TMT-REQUIRED"));
        assertTrue(TestTransaction.isActive());
        // After the test TestContext rolls back, @AfterTransaction checks again.
    }

    @Test
    @DisplayName("MANDATORY PASSES because the test already has a transaction")
    void mandatorySeesTestTransaction() {
        orders.createMandatory("TMT-MANDATORY");

        assertEquals(1, count("TMT-MANDATORY"));
        // A production caller without a transaction will behave differently.
    }

    @Test
    @DisplayName("Another connection does not see uncommitted row")
    void independentTransactionCannotSeeUncommittedRow() {
        orders.create("TMT-ISOLATION");
        assertEquals(1, count("TMT-ISOLATION"));

        TransactionTemplate separate =
                new TransactionTemplate(txManager);
        separate.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);

        Integer observed = separate.execute(status ->
                jdbc.queryForObject("""
                        SELECT COUNT(*) FROM tx_order
                        WHERE order_id = ?
                        """,
                        Integer.class, "TMT-ISOLATION"));

        assertEquals(0, observed.intValue());
    }

    private int count(String id) {
        return jdbc.queryForObject("""
                SELECT COUNT(*) FROM tx_order
                WHERE order_id = ?
                """, Integer.class, id);
    }
}
~~~

**Three tests**. `@BeforeEach`/`@AfterEach` run inside the test-managed TX, whereas `@BeforeTransaction`/`@AfterTransaction` sit outside. The count inside the test sees the transaction's own uncommitted row; after the default rollback, no row remains.

`independentTransactionCannotSeeUncommittedRow` temporarily suspends the outer TX, opens another transaction, and queries the same ID. With H2 READ_COMMITTED, the inner query sees 0 because the row has not been committed. This test does not prove all DB isolation levels or production concurrency behavior.

**Note:** if production code uses multiple transaction managers, the test must specify the right manager; checking `TestTransaction.isActive()` alone does not tell which transaction manages another resource.

## 13. Application Transactions: Without @Transactional on the Test

File `src/test/java/example/txdemo/ApplicationTransactionTest.java`:

~~~java
package example.txdemo;

import java.io.IOException;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
@DisplayName("Application transactions: real commit and rollback")
class ApplicationTransactionTest {

    @Autowired OrderService orders;
    @Autowired JdbcTemplate jdbc;

    @AfterEach
    void cleanupCommittedRows() {
        jdbc.update(
                "DELETE FROM tx_order WHERE order_id LIKE 'APP-%'");
        jdbc.update(
                "DELETE FROM audit_event WHERE event_key LIKE 'APP-%'");
    }

    @Test
    @DisplayName("Service commits when returning normally")
    void successCommits() {
        assertFalse(
                TransactionSynchronizationManager
                        .isActualTransactionActive());

        orders.create("APP-COMMIT");

        assertEquals(1, countOrder("APP-COMMIT"));
    }

    @Test
    @DisplayName("RuntimeException causes rollback")
    void uncheckedExceptionRollsBack() {
        assertThrows(IllegalStateException.class,
                () -> orders.createThenThrowRuntime("APP-RUNTIME"));

        assertEquals(0, countOrder("APP-RUNTIME"));
    }

    @Test
    @DisplayName("Checked exception can commit by default")
    void checkedExceptionDoesNotRollbackByDefault() {
        assertThrows(IOException.class,
                () -> orders.createThenThrowChecked("APP-CHECKED"));

        assertEquals(1, countOrder("APP-CHECKED"));
    }

    @Test
    @DisplayName("rollbackFor checked exception triggers rollback")
    void checkedExceptionWithRollbackRule() {
        assertThrows(IOException.class,
                () -> orders.createThenRollbackChecked("APP-CHECKED-RB"));

        assertEquals(0, countOrder("APP-CHECKED-RB"));
    }

    @Test
    @DisplayName("Audit REQUIRES_NEW commits even when outer rolls back")
    void requiresNewAuditSurvivesOuterRollback() {
        assertThrows(IllegalStateException.class,
                () -> orders.createThenFailAfterAudit(
                        "APP-OUTER", "APP-AUDIT"));

        assertEquals(0, countOrder("APP-OUTER"));
        assertEquals(1, countAudit("APP-AUDIT"));
    }

    @Test
    @DisplayName("MANDATORY fails if caller has no transaction")
    void mandatoryFailsWithoutTransaction() {
        assertThrows(IllegalTransactionStateException.class,
                () -> orders.createMandatory("APP-MANDATORY"));

        assertEquals(0, countOrder("APP-MANDATORY"));
    }

    private int countOrder(String id) {
        return jdbc.queryForObject("""
                SELECT COUNT(*) FROM tx_order
                WHERE order_id = ?
                """, Integer.class, id);
    }

    private int countAudit(String key) {
        return jdbc.queryForObject("""
                SELECT COUNT(*) FROM audit_event
                WHERE event_key = ?
                """, Integer.class, key);
    }
}
~~~

**Six tests** without `@Transactional` on the class or methods. Service transactions have authority to **commit/roll back at the real entrypoint**. After each test, `@AfterEach` deletes rows with prefix `APP-%` because **there is no TestContext rollback** to clean up for us.

The `mandatoryFailsWithoutTransaction` test is particularly useful: `createMandatory` PASSES when called from `TestManagedTransactionTest` because the test provides a TX; here it fails because there is no outer application transaction. It demonstrates how a test-managed transaction can **mask a missing transaction bug in a production caller**.

The `requiresNewAuditSurvivesOuterRollback` test has no shared test TX: the outer service opens its own TX; the inner audit opens TX B and commits; the outer throws and rolls back TX A. The DB result is order=0, audit=1. This is stronger evidence than mocking `AuditService` and guessing about commit.

## 14. TestTransaction: Committing and Rolling Back Mid-Test

File `src/test/java/example/txdemo/TestTransactionControlTest.java`:

~~~java
package example.txdemo;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@Transactional
@DisplayName("Controlling test-managed transaction with TestTransaction")
class TestTransactionControlTest {

    @Autowired OrderService orders;
    @Autowired JdbcTemplate jdbc;

    @Test
    @DisplayName("Commit mid-test then read outside transaction")
    void commitThenObserveOutsideTransaction() {
        orders.create("TT-COMMIT");
        assertTrue(TestTransaction.isActive());
        assertEquals(1, count("TT-COMMIT"));

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        try {
            assertEquals(1, count("TT-COMMIT"));
        } finally {
            // Transaction already COMMITTED so independent cleanup is required.
            jdbc.update(
                    "DELETE FROM tx_order WHERE order_id = ?",
                    "TT-COMMIT");
        }
    }

    @Test
    @DisplayName("Roll back then start a new test transaction")
    void rollbackThenStartAgain() {
        orders.create("TT-ROLLBACK");

        TestTransaction.flagForRollback();
        TestTransaction.end();

        assertFalse(TestTransaction.isActive());
        assertEquals(0, count("TT-ROLLBACK"));

        TestTransaction.start();
        assertTrue(TestTransaction.isActive());

        orders.create("TT-SECOND");
        assertEquals(1, count("TT-SECOND"));
        // Second transaction rolls back by default after test.
    }

    private int count(String id) {
        return jdbc.queryForObject("""
                SELECT COUNT(*) FROM tx_order
                WHERE order_id = ?
                """, Integer.class, id);
    }
}
~~~

**Two tests**. Checking right inside the initial transaction does not prove commit; after `TestTransaction.flagForCommit(); TestTransaction.end();`, the query runs outside the TX and proves the row was committed. At that point the test no longer gets automatic rollback for the committed row; `finally` cleans up the data.

Do not misuse `TestTransaction` to replace the application's transaction manager. It exists in the test lifecycle managed by TestContext, not for production services.

## 15. Real HTTP: Test Transaction Does Not Follow the Server Thread

File `src/test/java/example/txdemo/HttpTransactionBoundaryTest.java`:

~~~java
package example.txdemo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
@DisplayName("HTTP server transaction is independent of test thread")
class HttpTransactionBoundaryTest {

    @LocalServerPort int port;
    @Autowired JdbcTemplate jdbc;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    @Test
    @DisplayName("HTTP POST commits even though test will roll back")
    void httpServerCommitsIndependently() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port
                        + "/orders/HTTP-1"))
                .timeout(Duration.ofSeconds(20))
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        assertEquals(201, response.statusCode());
    }

    @AfterTransaction
    void observeAfterTestRollbackAndCleanup() {
        try {
            Integer total = jdbc.queryForObject("""
                    SELECT COUNT(*) FROM tx_order
                    WHERE order_id = ?
                    """, Integer.class, "HTTP-1");

            // Row committed by server TX still remains after test rollback.
            assertEquals(1, total.intValue());
        } finally {
            jdbc.update(
                    "DELETE FROM tx_order WHERE order_id = ?",
                    "HTTP-1");
        }
    }
}
~~~

**One test**. Spring Boot runs a real HTTP server on a random port. The HttpClient/JUnit thread has a test-managed transaction, but the controller/server service operates on a **server thread** with its own transaction. After Spring TestContext rolls back the JUnit transaction, `@AfterTransaction` still sees row `HTTP-1` committed by the server, and then cleans it up.

**Do not use `MockMvc` to draw conclusions about this case.** MockMvc normally processes requests in a mock servlet environment on the same test thread, so it can join the test-managed TX. Only `RANDOM_PORT` proves the real HTTP boundary.

### Total Number of Test Methods

| Test class | @Test count | What it checks |
| --- | ---: | --- |
| `TestManagedTransactionTest` | 3 | Test lifecycle, REQUIRED/MANDATORY, isolation |
| `ApplicationTransactionTest` | 6 | Commit, runtime/checked rollback, REQUIRES_NEW, MANDATORY |
| `TestTransactionControlTest` | 2 | Commit/rollback via TestTransaction |
| `HttpTransactionBoundaryTest` | 1 | HTTP server commits outside test TX |
| **Total** | **12** | JDBC transaction behavior on H2 |

## 16. Run Commands and Expected Output

In the project directory with the Gradle wrapper:

~~~bash
./gradlew test --tests example.txdemo.TestManagedTransactionTest --tests example.txdemo.ApplicationTransactionTest --tests example.txdemo.TestTransactionControlTest --tests example.txdemo.HttpTransactionBoundaryTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.txdemo.TestManagedTransactionTest --tests example.txdemo.ApplicationTransactionTest --tests example.txdemo.TestTransactionControlTest --tests example.txdemo.HttpTransactionBoundaryTest
~~~

**Expected outcome:** **12 JUnit Jupiter methods PASS** with Java 17+/Spring Boot 3.5.x, starter dependencies, and complete files. The tests have no `System.out.println`; Gradle/IDE may show `BUILD SUCCESSFUL`. This is **an expectation from the design, not stdout captured from an actual build run**.

If a test fails, check:

- `schema.sql` is actually loaded into H2 by Spring Boot SQL init.
- H2 is a test runtime dependency, and the datasource is not accidentally pointing to production.
- The context has a single transaction manager or an explicit manager configuration.
- Hikari has enough connections for `REQUIRES_NEW`.
- The HTTP endpoint is not blocked by Spring Security/CSRF if security is added to the project.
- Do not run test classes in parallel against a fixed-name database; `generate-unique-name=true` keeps context DBs isolated.

## 17. Fixtures and @Sql: When Is Data Committed?

A common mistake: `@BeforeEach` creates data inside the test transaction, then a `REQUIRES_NEW` method runs on another connection and needs to read that fixture. **The fixture is uncommitted**, so the inner transaction cannot see it under READ_COMMITTED.

~~~text
@BeforeTransaction -> can seed committed data
BEGIN test transaction A
@BeforeEach        -> inserts in A, uncommitted
@Test
  service REQUIRES_NEW -> transaction B does not see uncommitted data in A
@AfterEach
ROLLBACK A
@AfterTransaction  -> cleanup / verify outside A
~~~

If an inner transaction must see a fixture:

- Seed in `@BeforeTransaction` using committed JDBC/`TransactionTemplate`.
- Or use `@SqlConfig(transactionMode = ISOLATED)` to load SQL in a separate committed transaction.
- Or avoid REQUIRES_NEW in that scenario if the service itself does not use it.
- Clean up committed seed data after the test rather than relying on rolling back A.

Annotation illustration:

~~~java
@Sql(
    scripts = "/sql/seed-accounts.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
@SpringBootTest
@Transactional
class ExistingFixtureTest {
    // SQL fixture is committed independently of the test transaction.
}
~~~

This is a **sample**, not part of the 12-test suite; it requires `src/test/resources/sql/seed-accounts.sql` and imports. When using `@Sql` in practice, pay attention to `BEFORE_TEST_METHOD`/`AFTER_TEST_METHOD` timing, transaction mode, and cleanup scripts.

**Do not** mix `@Sql`, Flyway, and Boot SQL init without control, causing schemas to be recreated or fixture data duplicated.

## 18. Commit-Time Behavior, JPA, and Transaction Events

JPA `EntityManager` has a first-level cache and dirty checking. A test like:

~~~java
repository.save(account);
assertEquals(expected, repository.findById(id).orElseThrow());
~~~

may just read the managed object without necessarily forcing SQL/constraints to run. To verify mapping/constraints early:

~~~java
repository.save(account);
entityManager.flush();
entityManager.clear();
var loaded = repository.findById(id).orElseThrow();
assertEquals(expected, loaded.getBalance());
~~~

This is an **illustrative snippet**, requiring a real JPA entity/repository/EntityManager. `flush` does not commit; the DB can still roll back flushed data. For deferred constraints, `@TransactionalEventListener(phase=AFTER_COMMIT)`, or custom transaction synchronizations, you must test a **real commit**.

### Rollback Does Not Undo All Side Effects

- SQL rows in the same transaction: rolled back by the DB.
- Sent emails: not rolled back by an SQL transaction.
- Executed HTTP payment calls: not rolled back automatically.
- Kafka messages published outside a shared transaction: may remain.
- Written local files: not rolled back.
- Committed `REQUIRES_NEW` audit: not rolled back by the outer transaction.

When atomicity between DB writes and event publishing is needed, consider the outbox pattern, idempotency, after-commit events with crash-gap handling, or distributed transactions when genuinely appropriate.

## 19. Thread Boundaries, Preemptive Timeouts, and Reactive Transactions

Spring TestContext binds the transaction to the **thread running the test**. Therefore:

- `@Async`, `CompletableFuture.supplyAsync`, and schedulers/background workers use different threads.
- The HTTP server thread in `RANDOM_PORT` is a different thread.
- JUnit Jupiter's `assertTimeoutPreemptively` can run the test body on a different thread than the one to which TestContext bound the transaction.

Do not write:

~~~java
assertTimeoutPreemptively(
    Duration.ofSeconds(2),
    () -> orderService.create("PREEMPTIVE"));
~~~

inside a test-managed transaction and trust that all writes will roll back. The test transaction may not follow the new thread, and the service may commit independently. If you need a timeout test, consider non-preemptive `assertTimeout`, query/DB deadlines, or a dedicated test with cleanup and real cancellation mechanisms.

With **R2DBC/WebFlux**, reactive transactions can use `ReactiveTransactionManager` and **Reactor Context**, rather than relying simply on JDBC ThreadLocal. This example article uses **Spring JDBC + servlet MVC**, so do not copy its transaction assumptions to `Flux`/`Mono` without verifying context propagation.

## 20. Application Transactions Can Fail to Run Due to Self-Invocation

Spring declarative transactions usually rely on AOP proxies. Calling a method on the same object via `this.inner()` can bypass the proxy:

~~~java
@Service
class DangerousService {

    public void outer() {
        innerRequiresNew();  // self-invocation, bypasses proxy
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void innerRequiresNew() {
        // May NOT open a new transaction as expected.
    }
}
~~~

This is an explanatory sample, not included in the runnable example. In `OrderService`, the audit method is placed on a **separate `AuditService`** so the call goes through the proxy.

A test that already has a test transaction can mask a self-invocation bug: the code runs under the transaction opened by the test, yet production does not achieve the designed propagation. Solution: extract a separate bean, call through a real proxy, or use `TransactionTemplate` with explicitly configured propagation. Also write tests **without a test-level transaction**.

## 21. TransactionTemplate vs. TestTransaction

| Tool | Purpose | Used in production? |
| --- | --- | --- |
| `TestTransaction` | Controls the lifecycle of a test-managed transaction | No; for Spring TestContext |
| `TransactionTemplate` | Programmatic transaction management for the application | Yes |
| `PlatformTransactionManager` | Abstracts resource begin/commit/rollback | Yes; Spring wiring |
| `@Transactional` on service | Declarative transaction management via proxy | Yes |
| `@Transactional` on test | Activates a test-managed transaction | Yes in tests |

Application example using `TransactionTemplate`:

~~~java
@Service
public class ProgrammaticWriter {

    private final TransactionTemplate transactions;
    private final JdbcTemplate jdbc;

    public ProgrammaticWriter(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        this.transactions = new TransactionTemplate(manager);
        this.jdbc = jdbc;
    }

    public void save(String id) {
        transactions.executeWithoutResult(status ->
                jdbc.update(
                    "INSERT INTO tx_order(order_id,note) VALUES (?,?)",
                    id, "programmatic"));
    }
}
~~~

This is an illustrative class (requires package/imports). With default `REQUIRED` propagation, `TransactionTemplate` can also **join the test transaction** instead of committing separately; using a programmatic API does not automatically guarantee a new physical transaction.

## 22. Database-Specific Issues and Concurrency

H2 in-memory works well for examples, but does not replace PostgreSQL/MySQL/Oracle/SQL Server in all semantics:

- **Isolation:** `READ_COMMITTED`/`REPEATABLE_READ`/`SERIALIZABLE` have different implementations and lock behaviors.
- **Deferred constraints:** some constraints are only checked at commit time; flush in a test is not enough.
- **DDL rollback:** PostgreSQL supports transactional DDL much more broadly than many other DBs; some DDL auto-commits.
- **SQL exception:** PostgreSQL has transaction-aborted `25P02` after an error, requiring rollback before subsequent queries.
- **Savepoints:** `NESTED` depends on the JDBC driver/manager.
- **Locking:** `SELECT FOR UPDATE`, `SKIP LOCKED`, and deadlocks cannot be tested with a single connection.
- **Time zone/collation:** verify with the right driver/dialect if business logic depends on SQL behavior.

If production must prevent overselling or lost updates, the test must have **at least two independent connections/transactions**, a coordination barrier, timeouts, and post-commit assertions. Do not treat two sequential calls on the same thread/test transaction as a concurrency test.

### Testing with Testcontainers

For PostgreSQL, you can run `@SpringBootTest` or a JDBC slice connected to a `PostgreSQLContainer` via `@ServiceConnection`, apply real migrations, and verify state/SQLSTATE/locks. Depending on the test slice, configure `@AutoConfigureTestDatabase(replace=NONE)` to avoid replacing it with H2. Do not use production DB credentials.

## 23. Common Mistakes and How to Avoid Them

**1. A `@Transactional` test supplies a transaction to a service even though production lacks one.**  
Separate service transaction tests without `@Transactional` on the test to prove real commit/rollback.

**2. A service returning normally is treated as a commit.**  
With `REQUIRED` joining the test transaction, only TestContext owns commit/rollback.

**3. Using `@Commit` or `@Rollback(false)` and forgetting cleanup.**  
Data persists after the test. Use an isolated DB or fixture cleanup.

**4. Checking data before rollback and declaring it committed.**  
A transaction can read its own uncommitted writes.

**5. Thinking `@AfterEach` runs after rollback.**  
It runs inside the test TX; use `@AfterTransaction` to inspect the DB after rollback.

**6. Placing `@Transactional` on `@BeforeEach` without understanding TestContext.**  
The test-managed transaction annotation belongs on the test class/method; `@BeforeEach` joins the existing transaction if the test is transactional.

**7. Assuming `REQUIRES_NEW` will roll back along with the test.**  
An independent transaction can commit; cleanup and connection pool awareness are required.

**8. Confusing `NESTED` with `REQUIRES_NEW`.**  
`NESTED` usually uses a savepoint on the same physical TX and does not commit independently.

**9. Catching an exception while the transaction remains rollback-only.**  
An inner `REQUIRED` call may have already marked it rollback-only; the outer commit will fail.

**10. Assuming checked exceptions roll back by default like unchecked exceptions.**  
Spring 6.2 rolls back unchecked exceptions by default, not checked exceptions unless configured with a rule.

**11. Expecting `@Transactional(readOnly/isolation/timeout)` on a test to behave like a service.**  
TestContext supports only a limited set of attributes; verify configuration at the application boundary.

**12. Pool size too small for `REQUIRES_NEW`.**  
The outer TX holds one connection while the inner TX needs a second connection, which can time out.

**13. Seeding in `@BeforeEach` and finding `REQUIRES_NEW` cannot see the row.**  
The fixture is uncommitted; seed committed data outside the test transaction or use `@Sql` `ISOLATED`.

**14. Using `@DirtiesContext` to clean an external DB.**  
Resetting the context cache does not delete committed rows from the database.

**15. Using `@SpringBootTest` `RANDOM_PORT` and expecting test rollback to clean HTTP writes.**  
The server thread has an independent transaction and must be cleaned up.

**16. Using `MockMvc` to prove transactions over live HTTP.**  
`MockMvc` typically runs on the same test thread; a TCP server does not.

**17. `assertTimeoutPreemptively` causing a thread hop.**  
This can cause writes to escape the test-managed TX.

**18. JPA `save` followed by reading a managed entity without flush/clear.**  
Prone to false positives; SQL/constraints may not have executed yet.

**19. Treating `flush` as `commit`.**  
Flush pushes SQL; only commit determines durability and after-commit events.

**20. Seeing H2 PASS and assuming PostgreSQL locking/SQLSTATE is correct.**  
Use Testcontainers with a production-like DB when DB-specific behavior matters.

**21. Calling a `@Transactional` method via `this.method()`.**  
It bypasses the proxy, so propagation may not apply.

**22. Expecting a test transaction to roll back emails, HTTP payments, or files.**  
A DB rollback does not automatically undo external side effects.

**23. Parallel tests sharing a schema/IDs.**  
Can cause races and data leaks; partition fixtures or disable parallelism when needed.

**24. Equating reactive transactions with JDBC `ThreadLocal`.**  
R2DBC uses reactive context; design dedicated tests for it.

## 24. Test Decision Workflow

1. Specify the **goal**: repository SQL, service commit, error rollback, HTTP server, after-commit event, or DB isolation.
2. Identify the resource manager: JDBC/JPA/R2DBC/JTA, and which connection/datasource.
3. Clarify whether the caller already has a transaction before invoking the service; if so, what propagation is used.
4. Use a test-managed TX for fast repository tests that roll back automatically and do not require commit.
5. When verifying real business commit/rollback, **omit the test-level transaction** and check state after the call.
6. For `REQUIRES_NEW`, ensure sufficient pool size and clean up independently committed data.
7. For fixtures that need visibility from another connection, seed before the test TX or use `@Sql` `ISOLATED`.
8. For commit-time constraints/events, use `@Commit` or `TestTransaction` with cleanup.
9. For HTTP `RANDOM_PORT` and async work, assume a transaction boundary different from the test thread.
10. For JPA, flush/clear when verifying SQL state, and do not confuse it with commit.
11. When concurrency/isolation is needed, use multiple connections and a real production-like DB.
12. Do not use preemptive test timeouts for DB writes inside a test-managed TX if you expect rollback.
13. Clean up committed state explicitly rather than relying on test order or `@DirtiesContext`.
14. Avoid production credentials; keep test databases/schemas separate and use versioned migrations.
15. Test success, exception, and side-effect paths—not only the happy path.

### Final Checklist

- [ ] Identified test-managed/application/DB transaction boundaries and the transaction manager.
- [ ] Understood `@Transactional` on a test rolls back by default and is not equivalent to `@Transactional` on a service.
- [ ] Understood `REQUIRED`/`MANDATORY`/`REQUIRES_NEW`/`NESTED` relative to the current caller.
- [ ] Included service tests not wrapped in a test transaction when needing to prove commit.
- [ ] Used `@BeforeTransaction`/`@AfterTransaction` properly when inspecting state before/after TX.
- [ ] Did not mistake `@BeforeEach`/`@AfterEach` as running outside the test TX.
- [ ] Implemented explicit cleanup when using `@Commit`/`@Rollback(false)`/`TestTransaction.commit`.
- [ ] Included rollback tests for `RuntimeException` and checked exceptions when required by business logic.
- [ ] Ensured `REQUIRES_NEW` does not leak state or exhaust connections.
- [ ] Tested HTTP/server/async threads in a realistic environment when needed.
- [ ] Distinguished JPA flush/clear, constraints, and `afterCommit`.
- [ ] Avoided `assertTimeoutPreemptively` causing transactions to escape the test thread.
- [ ] Tested DB vendor-specific behavior on a real engine when needed.
- [ ] Avoided using production data/DB credentials for write/rollback tests.

**Remember:** a test-managed transaction is a **test isolation mechanism**, not proof that a production service commits or rolls back properly. A Spring application transaction may share a physical transaction with the test or open a separate one. The database determines visibility, constraints, and actual commit/rollback. By clearly identifying the **thread, connection, propagation, and commit owner**, you will avoid most false positives and leaked data in Spring Boot testing.

### Official References

- [Spring Framework 6.2 — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): lifecycle, supported `@Transactional` attributes, `TestTransaction`, timeouts.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED`, savepoints, connection pool.
- [Spring Framework — Declarative Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): checked and unchecked rollback rules.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate` and `PlatformTransactionManager`.
- [Spring Framework — Spring TestContext @Sql](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): SQL fixtures and isolated transaction mode.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): data slices, `@SpringBootTest`, `RANDOM_PORT` thread boundary.
- [Spring Framework — TestTransaction API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html): `isActive`, flags, `end`/`start`.
