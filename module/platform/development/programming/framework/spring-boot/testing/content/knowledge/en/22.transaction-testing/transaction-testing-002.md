# @Transactional on Tests and Default Rollback Scope

## 1. The Problem: Tests Pass Green, But Was Data Committed or Not?

In a Spring Boot application, you can add `@Transactional` on a **business method** to manage a transaction, or add that same annotation on a **JUnit test class/test method** to set up a *test-managed transaction*. Both places use the same annotation, yet their **lifecycle, commit/rollback policy, and purpose are not the same**.

A familiar example:

```java
@SpringBootTest
@Transactional
class OrderRepositoryTest {

    @Autowired JdbcTemplate jdbc;

    @Test
    void createsOrder() {
        jdbc.update(
                "insert into orders(code) values (?)",
                "ORDER-001");
        // Test ends -> Spring TestContext rolls back by default.
    }
}
```

This is an **illustrative snippet** (assuming the `orders` table exists and classes are imported). If the application has an appropriate `PlatformTransactionManager` and Spring TestContext is managing the test, data inserted in the test transaction is typically **rolled back by default after each test method**. Therefore, an INSERT returning success and a SELECT in the same transaction reading the new row **do not prove the database committed**.

An even trickier pitfall: from that test you send a real HTTP request to the embedded server, call a service with `REQUIRES_NEW`, spawn a secondary thread, or interact with an external system. Those operations can execute **outside** the test-managed transaction and be committed even though the JUnit test later rolls back.

### What You Will Learn

- Exactly what `@Transactional` on a test does, and when Spring TestContext begins/ends the transaction.
- Default rollback and how to change it with `@Rollback`, `@Commit`, and `TestTransaction`.
- Distinguishing test-managed transactions, Spring-managed service transactions, and application-managed transactions.
- The roles of `@BeforeTransaction`, `@BeforeEach`, `@AfterEach`, and `@AfterTransaction`.
- The limits of `@Transactional` **on tests**: which attributes the listener uses and which it does not.
- Differences between `@SpringBootTest`, `@JdbcTest`, `@DataJpaTest`, and `@DataR2dbcTest`.
- Why another thread, `@SpringBootTest(RANDOM_PORT)`, `REQUIRES_NEW`, or `@Sql(ISOLATED)` can leave data behind.
- How to use Java 17+, Spring Boot 3.x, H2, JUnit Jupiter, and JDBC to **measure state after the transaction ends**.
- How to avoid false-positive green tests caused by the JPA persistence context, unflushed SQL, database isolation, or incomplete cleanup.

**Focus:** Spring TestContext of Spring Framework 6.x / Spring Boot 3.x. The complete code examples below use **Servlet MVC + JDBC/H2** to demonstrate transaction boundaries directly, without requiring a production database. R2DBC/Reactive and Spring Boot 4.x are distinguished separately; do not assume they share the same rollback behavior.

## 2. Three Types of Transactions to Distinguish

Spring Framework describes three common scopes:

1. **Test-managed transaction:** created by Spring TestContext's `TransactionalTestExecutionListener` for a test method, typically rolled back after the test.
2. **Spring-managed transaction:** managed by Spring transaction AOP/interceptor when calling a `@Transactional` bean/method, with the application's propagation and rollback policies.
3. **Application-managed transaction:** explicitly opened/ended by code, for example `TransactionTemplate` or transaction manager APIs.

They can **participate in the same database transaction** when using the same resource/manager and compatible propagation; however, they do not by default form a single transaction for every side effect.

```text
SpringExtension / TestContext
    |
    +-- TransactionalTestExecutionListener
    |      |
    |      +-- BEGIN test-managed transaction (test thread)
    |      |
    |      +-- @BeforeEach
    |      +-- @Test
    |      |     |
    |      |     +-- JdbcTemplate JDBC operation
    |      |     +-- @Transactional service (REQUIRED)
    |      |     +-- @Transactional service (REQUIRES_NEW) [different tx!]
    |      |
    |      +-- @AfterEach
    |      |
    |      +-- ROLLBACK (default) / COMMIT (if requested)
    |
    +-- @AfterTransaction (outside transaction)
```

For standard JDBC transactions, Spring holds transaction state on the **current thread** (via ThreadLocal). When a `@Transactional(propagation=REQUIRED)` service is called from the test thread with the same datasource/manager, it can join that test transaction. If the service uses `REQUIRES_NEW`, Spring can suspend the existing transaction and **open an independent transaction** that commits or rolls back on its own.

### 2.1. Test-Managed Rollback Does Not Mean Production Service Rollback

In production, a typical `@Transactional` service **commits when the method completes normally** and rolls back when an exception matches rollback rules or the transaction is marked rollback-only.

On a JUnit test, `@Transactional` combined with Spring TestContext creates a transaction with a **default end-of-test rollback policy**, even when the test method throws no error. The reason is that tests need data isolation to be repeatable.

| Case | Final transaction decision |
|---|---|
| JUnit test `@Transactional`, no override | Spring TestContext **rolls back by default** |
| Test `@Transactional @Commit` | Spring TestContext **attempts to commit** the transaction when the test ends |
| Test `@Transactional @Rollback(false)` | Equivalent to requesting no default rollback, i.e., **commit** |
| Test `@Transactional @Rollback(true)` | Requests rollback, which is also the default |
| Production service `@Transactional(REQUIRED)` inside test tx | Usually joins the test transaction; rolled back at end of test |
| Service `@Transactional(REQUIRES_NEW)` inside test tx | Independent transaction, can **commit** and survive test rollback |
| HTTP request to `RANDOM_PORT` | Handled on a different server thread/transaction; test rollback does not auto-roll back server |
| JDBC operation outside test-managed transaction | Follows service manager or JDBC auto-commit, not auto-rolled back by listener |

**Note:** a `@Commit` request does not guarantee a successful commit if a database exception, rollback-only flag, or transaction error occurs. It is best to verify data after the boundary with another query.

### 2.2. "In the Same Transaction" Must Include Connection, Manager, and Thread

A check like:

```java
jdbc.update("insert into ledger_entries(code, amount) values (?, ?)",
        "T-1", 100);
assertThat(count("T-1")).isEqualTo(1);
```

only proves that the INSERT and SELECT used by the test see the data **within the current access context**. If both participate in the test transaction, they can see uncommitted data. To prove rollback/commit, check **after the test transaction ends**, such as via `@AfterTransaction` or `TestTransaction.end()` and querying again.

Do not treat `count=1` inside the test as proof that "data was permanently persisted." Nor should you treat a JPA entity having an ID as proof that the transaction committed.

## 3. How Does Spring TestContext Activate @Transactional on Tests?

### 3.1. TransactionalTestExecutionListener

Spring TestContext includes `TransactionalTestExecutionListener`, which by default participates in the standard test listener set. For a JUnit test to run inside a transaction, you need:

- A Spring TestContext created (e.g., `@SpringBootTest`, `@JdbcTest`, `@DataJpaTest`, or `@SpringJUnitConfig`).
- A matching `PlatformTransactionManager` bean in the `ApplicationContext`.
- Spring's `org.springframework.transaction.annotation.Transactional` declared on the test method or class, **or** a test slice that is already meta-annotated as transactional.
- Test execution managed by SpringExtension/TestContext; not simply running a plain JUnit class without the Spring extension.
- Not intentionally disabling the test transaction via special propagation.

You **do not need** to add `@ExtendWith(SpringExtension.class)` manually when using Spring Boot test annotations that already include `SpringExtension`.

### 3.2. Import the Right @Transactional

With Spring Framework 6.x/Spring Boot 3.x:

```java
import org.springframework.transaction.annotation.Transactional;
```

This lesson uses **Spring `@Transactional`**, rather than automatically equating it with all transaction annotations from `jakarta.transaction.*` or annotations provided by other frameworks. The TestContext transaction listener recognizes/interprets the annotations it supports. If using multiple transaction annotations/managers, check the documentation for the branch you are using.

### 3.3. What If There Are Multiple PlatformTransactionManagers?

If an application has multiple databases or multiple managers, a test may fail to pick the intended manager. Specify explicitly:

```java
@Transactional(transactionManager = "ordersTransactionManager")
class OrdersTransactionTest {
    // ...
}
```

This is an illustrative snippet: a bean named `ordersTransactionManager` must actually exist, have the right datasource/repository, and be capable of managing the operations under test.

**Do not** infer that simply because a transaction is active, all JDBC/JPA/Redis/Kafka/HTTP resources belong to the same transaction. Coordinating multiple resources requires appropriate configuration/transaction architecture.

### 3.4. @SpringBootTest Does Not Open a Test Transaction by Default

```java
@SpringBootTest
class PlainIntegrationTest {
    @Test void example() {
        // No test-managed tx solely from @SpringBootTest.
    }
}
```

This is an illustrative snippet. In a full-context test, if you need automatic rollback, you must declare `@Transactional` on the test or class, or use another configuration that intentionally creates a test-managed transaction.

Conversely, many test slices **already have a transactional policy**, even if you do not place `@Transactional` directly.

## 4. Common Test Annotations and Default Rollback

| Test style on Spring Boot 3.x | Default transaction? | Notes |
|---|---|---|
| `@SpringBootTest` | Not activated by this annotation alone | Add `@Transactional` when a test-managed tx is needed |
| `@JdbcTest` | **Yes**, rolled back at end of each test | For JDBC, `JdbcTemplate`, DataSource |
| `@DataJdbcTest` | **Yes**, rolled back at end of each test | For Spring Data JDBC repositories/aggregates |
| `@DataJpaTest` | **Yes**, rolled back at end of each test | For JPA repositories/entities, with persistence context |
| `@JooqTest` | **Yes**, rolled back by default | For jOOQ, using the right DataSource/manager |
| `@DataR2dbcTest` | **No default reactive test-managed transaction** | R2DBC requires managing Publisher + ReactiveTransactionManager |
| `@WebMvcTest` | Not inherently a JPA/JDBC transactional test | Typically loads only web slice; do not assume a manager exists |
| Plain JUnit, without Spring TestContext | No | `@Transactional` does not automatically turn a Java class into a Spring bean/proxy |

Even when a slice has auto-rollback, operations running in a **different service transaction**, on a different thread, or on a different connection can still commit. Conversely, `@SpringBootTest` with a test-managed tx can create the illusion that "every service always rolls back" even though production behavior differs.

### 4.1. Why Does @DataJpaTest Often Not Need Explicit @Transactional?

According to Spring Boot 3.5, `@DataJpaTest` is designed to test JPA repositories in isolation, transactional and rolled back by default. Writing:

```java
@DataJpaTest
class ProductRepositoryTest {
    @Autowired ProductRepository repository;

    @Test
    void savesProduct() {
        // Has a test-managed tx under the default configuration.
    }
}
```

is enough to get default rollback (the snippet assumes a real repository). Adding `@Transactional` can make intent explicit for readers, but you should not think it is "enabling a missing feature" in the default slice.

In JPA, **flush is not commit**: to catch constraint violations or listener/mapping errors, you sometimes need `entityManager.flush()` or `repository.flush()` in the test. Without flushing before the test rolls back, errors that only occur when SQL is sent may go undetected.

### 4.2. Do Not Carry This Habit Over to @DataR2dbcTest

Spring Boot 3.x's `@DataR2dbcTest` **does not auto-roll back every test**. A Publisher that writes data can be subscribed to and commit outside a transaction if you do not wrap it with `TransactionalOperator` or an appropriate proxied reactive `@Transactional`. `@Transactional` on a `void` JUnit test method does not automatically create a Reactor transaction for every Publisher in the test.

This lesson focuses on imperative test-managed transactions; reactive transactions must be tested through **Publisher/subscription and Reactor Context**, not by assuming ThreadLocal rollback.

## 5. Lifecycle of a Transactional Test Method

Spring TestContext organizes the following phases:

```text
@BeforeAll                       (not part of test-managed tx)
  |
@BeforeTransaction               (outside transaction)
  |
BEGIN test-managed transaction
  |
@BeforeEach                      (inside transaction)
  |
@Test                            (inside transaction)
  |
@AfterEach                       (inside transaction)
  |
ROLLBACK by default / COMMIT if configured
  |
@AfterTransaction                (outside transaction)
  |
@AfterAll                        (not part of test-managed tx)
```

The diagram reflects the typical JUnit Jupiter/`SpringExtension` flow. `@BeforeTransaction` and `@AfterTransaction` **only run for transactional test methods**. If a method has `Propagation.NOT_SUPPORTED` or `NEVER`, TestContext does not open a test-managed transaction for that method, so the corresponding before/after-transaction callbacks do not apply.

### 5.1. @BeforeEach and @AfterEach Inside the Transaction

When a test method's transaction is managed by TestContext:

- `@BeforeEach` fixture setup can INSERT data within the test transaction itself.
- `@Test` runs after setup.
- `@AfterEach` also typically runs **before rollback/commit**, so it can still read data inside the transaction.
- Afterward, TestContext rolls back by default.

Therefore, if you want to test "is the row gone after rollback," **do not put that assertion in `@AfterEach`**. Use `@AfterTransaction` or `TestTransaction.end()`, and then execute the query outside the finished transaction.

### 5.2. @BeforeTransaction and @AfterTransaction

Spring supports:

```java
@BeforeTransaction
void beforeTransaction() {
    // Verify committed baseline/fixtures outside the test transaction.
}

@AfterTransaction
void afterTransaction() {
    // Verify state outside the test transaction after rollback/commit.
}
```

This is a lifecycle snippet, not a standalone runnable file. With JUnit Jupiter/`SpringExtension` on Spring Framework 6.1+, certain arguments can be injected via resolvers; the code samples in this lesson use zero-argument methods for compatibility and readability.

These two hooks are especially useful for:

- Confirming the baseline has no leftover data before the test begins.
- Proving data was rolled back after the method.
- Proving `@Commit` leaves data persisted after the test.
- Controlled cleanup of data committed during transaction-boundary tests.

Do not create sensitive production-like fixtures in these hooks; use dummy data and an isolated database.

### 5.3. @BeforeAll Is Not Automatically Inside a Test Transaction

If you create fixtures in `@BeforeAll`, do not expect per-test rollback to remove those fixtures. `@BeforeAll` runs outside each method's test-managed transaction; you may need `TransactionTemplate` if you want a separate transaction during class-level setup.

Similarly, `@AfterAll` is not automatically rolled back by TestContext as part of any finished test method's transaction.

## 6. @Rollback, @Commit, and TestTransaction

### 6.1. @Rollback(true): Explicit but Usually Unnecessary

```java
@Test
@Transactional
@Rollback
void rollbackAtEnd() {
    // @Rollback defaults to value=true.
}
```

In Spring Test, if `@Transactional` is present and nothing else is configured, rollback is already the default. `@Rollback(true)` can be written to state intent explicitly or to override a class-level `@Commit`.

### 6.2. @Rollback(false): Requesting Commit

```java
@Test
@Transactional
@Rollback(false)
void commitAtEnd() {
    // The test transaction will be committed when the test ends,
    // unless marked rollback-only or a transaction error occurs.
}
```

`@Rollback(false)` **does not** turn every service method into `REQUIRES_NEW`; it only changes **the ending policy of the test-managed transaction**. You must clean up committed data if the database is reused across tests.

### 6.3. @Commit: Shorthand for @Rollback(false)

```java
@Test
@Transactional
@Commit
void commitsTestTransaction() {
    // Equivalent to requesting @Rollback(false).
}
```

If `@Commit` is at the class level, a method-level `@Rollback` can override it to request rollback for that method. Method annotations take appropriate precedence over class-level defaults; do not place conflicting `@Commit` and `@Rollback` on the same element.

### 6.4. TestTransaction: Controlling a Running Transaction

Spring Test provides the helper `org.springframework.test.context.transaction.TestTransaction`:

| Method | Meaning |
|---|---|
| `isActive()` | Is there an active test-managed transaction on the current thread? |
| `isFlaggedForRollback()` | Is the current transaction scheduled to roll back when ended? |
| `flagForRollback()` | Marks the current test-managed transaction to roll back when ended |
| `flagForCommit()` | Marks the current test-managed transaction to commit when ended |
| `end()` | Immediately ends the current test transaction according to the flag |
| `start()` | Opens a new test transaction when no test transaction is active |

**Key point:** `flagForRollback()` and `flagForCommit()` only set **intent**; they do not commit/roll back immediately. `end()` is what ends the transaction. After `end()`, you can call `start()` to continue testing in a new transaction; starting requires that the test-managed transaction is configured by Spring.

Illustrative example:

```java
assertThat(TestTransaction.isActive()).isTrue();
TestTransaction.flagForRollback();
TestTransaction.end();
assertThat(TestTransaction.isActive()).isFalse();
// Execute a query to observe state after rollback.
TestTransaction.start();
// New test transaction is active; rolls back at end of test per policy.
```

Use `TestTransaction` in **test** code, not in production services. If you use `flagForCommit()` and end the transaction, real data can remain in the test database; explicit cleanup is required.

### 6.5. Do Not Confuse @Transactional's rollbackFor with TestContext Rollback Rules

An easily overlooked distinction from the Spring Framework 6.2 documentation:

**Test-managed transactions do not support all `@Transactional` attributes the way service transactions do.**

| `@Transactional` attribute on test | Does the TestContext listener use it for the test-managed transaction? |
|---|---|
| `value` / `transactionManager` | **Yes**, selects the transaction manager |
| `propagation` | Explicitly handles only `NOT_SUPPORTED` and `NEVER` to **not open** a test-managed transaction |
| `isolation` | **Not** applied as you might expect by the listener |
| `timeout` | **Not** applied as you might expect by the listener |
| `readOnly` | **Not** applied as you might expect by the listener |
| `rollbackFor` / `rollbackForClassName` | **No**; use `TestTransaction`/`@Rollback` |
| `noRollbackFor` / `noRollbackForClassName` | **No**; use `TestTransaction`/`@Commit` |

Do not write:

```java
@Transactional(noRollbackFor = IllegalArgumentException.class)
@Test
void shouldCommitAfterException() {
    throw new IllegalArgumentException("invalid");
}
```

thinking Spring Test will commit automatically because of `noRollbackFor`. This is a **counter-example**: test-managed rollback policy differs from declarative service rollback rules. For test transactions, use `@Commit`/`@Rollback(false)` or `TestTransaction.flagForCommit()` as intended, and verify actual transaction status. A JUnit assertion failure also does not turn default rollback into a commit.

If you need to test isolation/timeout/readOnly as a **service policy**, test a real Spring bean annotated with `@Transactional` and a suitable manager, rather than assuming attributes on the JUnit test annotation were applied by the listener.

## 7. Runnable Example: Java 17+ / Spring Boot 3.x with JDBC and H2

We use one small application containing:

- One SQL table `ledger_entries`.
- `JdbcTemplate` for verifiable SELECT/INSERT/DELETE operations.
- A service with a `@Transactional(REQUIRED)` method and a `@Transactional(REQUIRES_NEW)` method.
- An HTTP endpoint allowing us to observe the difference between the server thread and the test-managed thread.
- **Five test classes, six `@Test` methods**. Each test uses a unique code key to avoid collisions.
- An in-memory H2 database configured **only for tests**, not a production DB.
- Committed fixtures cleaned up right after the test; fixtures inside rolled-back transactions do not persist.

**Environment:** Spring Boot **3.x** (e.g., Boot 3.5), Java 17+, Spring JDBC, Spring MVC, JUnit Jupiter, H2. The samples use Boot 3.x imports; Boot 4 has some different packages/starters, so cross-check against the BOM when migrating.

### 7.1. Build Dependencies

**Gradle Groovy DSL:** snippet from a `build.gradle` that already has the Spring Boot plugin, repositories, dependency management, and Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Maven:** dependencies snippet from a `pom.xml` that already has the Spring Boot parent/BOM, Java 17 compiler, and Surefire with JUnit Platform support:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

These are **snippets**, not complete build files. Do not manually pin Spring/H2 versions when the Boot BOM manages them. Use the project's wrapper instead of another build tool version in CI.

### 7.2. File Structure

```text
src/
├── main/java/com/example/testtx/
│   ├── TestTxApplication.java
│   ├── LedgerService.java
│   └── LedgerController.java
└── test/
    ├── java/com/example/testtx/
    │   ├── RollbackLifecycleTest.java
    │   ├── CommitOverrideTest.java
    │   ├── TestTransactionBoundaryTest.java
    │   ├── RequiresNewBoundaryTest.java
    │   └── RealHttpRollbackBoundaryTest.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

Putting classes in the same package lets Spring Boot find configuration via `@SpringBootApplication`; each test class uses `@SpringBootTest(classes = TestTxApplication.class)` to specify the application explicitly.

### 7.3. Application Entry Point

**File `src/main/java/com/example/testtx/TestTxApplication.java`:**

```java
package com.example.testtx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestTxApplication {

    public static void main(String[] args) {
        SpringApplication.run(TestTxApplication.class, args);
    }
}
```

This class uses default component scanning. Do not declare `PlatformTransactionManager` manually; Spring Boot can auto-configure a JDBC transaction manager when a valid `DataSource` and transaction infrastructure are on the classpath.

### 7.4. Real Service — REQUIRED and REQUIRES_NEW

**File `src/main/java/com/example/testtx/LedgerService.java`:**

```java
package com.example.testtx;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LedgerService {

    private final JdbcTemplate jdbc;

    public LedgerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void writeRequired(String code) {
        jdbc.update(
                "insert into ledger_entries(code, amount) values (?, ?)",
                code, 1);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeRequiresNew(String code) {
        jdbc.update(
                "insert into ledger_entries(code, amount) values (?, ?)",
                code, 1);
    }
}
```

Both methods execute the same kind of INSERT, differing in **transaction propagation**.

- `writeRequired(...)` defaults to `Propagation.REQUIRED`: when called inside a test-managed transaction with the same manager/resource, it usually **joins the test transaction**. When called from a server thread without a transaction, Spring creates a new transaction and commits when the method completes normally.
- `writeRequiresNew(...)`: suspends the current transaction (if any) and creates an independent transaction. If the method completes normally, that separate transaction can commit **before** the JUnit test transaction rolls back.
- Both public methods are called via **Spring-managed bean proxies** in the example. If you instantiate the service with `new` or self-invoke `this.writeRequiresNew(...)` on the same instance, proxy semantics will differ.

**Do not replace this with a repository mock** if you want to genuinely verify transactions/DB behavior. The example uses real JDBC/H2 to observe data after the transaction.

### 7.5. HTTP Controller Using the REQUIRED Service

**File `src/main/java/com/example/testtx/LedgerController.java`:**

```java
package com.example.testtx;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/ledger")
public class LedgerController {

    private final LedgerService service;

    public LedgerController(LedgerService service) {
        this.service = service;
    }

    @PostMapping("/{code}")
    @ResponseStatus(HttpStatus.CREATED)
    public void add(@PathVariable String code) {
        service.writeRequired(code);
    }
}
```

With `@SpringBootTest(webEnvironment = RANDOM_PORT)`, the HTTP request goes through the embedded server and calls the service from a server thread. The transaction opened for `writeRequired(...)` on the **server thread** does not automatically join the transaction bound to the JUnit test thread. The controller returns 201 when the service succeeds.

### 7.6. Dedicated H2 Schema for Tests

**File `src/test/resources/schema.sql`:**

```sql
CREATE TABLE IF NOT EXISTS ledger_entries (
    code VARCHAR(80) PRIMARY KEY,
    amount INTEGER NOT NULL
);
```

`IF NOT EXISTS` syntax is used for H2 so the script is idempotent when Spring initializes multiple test application contexts pointing to the same named in-memory database. Do not blindly copy this SQL to every RDBMS without checking syntax/DDL semantics.

**File `src/test/resources/application.properties`:**

```properties
spring.datasource.url=jdbc:h2:mem:test_transaction_boundary;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

This properties file belongs only in **test resources**. A named H2 in-memory DB lets two Spring test contexts in the same JVM share the schema; every test uses a distinct code and committed rows are cleaned up immediately.

**Important:** `DB_CLOSE_DELAY=-1` means H2 keeps the named in-memory database alive for the lifetime of the JVM, making cleanup and isolated keys even more critical. If CI runs parallel tests or uses a different context lifecycle, use a separate database/schema per worker rather than relying on test order.

### 7.7. Test 1 — @BeforeEach/@AfterEach Inside a Rollback Transaction

**File `src/test/java/com/example/testtx/RollbackLifecycleTest.java`:**

```java
package com.example.testtx;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = TestTxApplication.class)
@Transactional
class RollbackLifecycleTest {

    private static final String CODE = "TEST-LIFECYCLE";

    @Autowired
    JdbcTemplate jdbc;

    private int count() {
        return jdbc.queryForObject(
                "select count(*) from ledger_entries where code = ?",
                Integer.class, CODE);
    }

    @BeforeTransaction
    void beforeTransaction() {
        assertThat(count()).isZero();
    }

    @BeforeEach
    void setUpInsideTransaction() {
        assertThat(TestTransaction.isActive()).isTrue();
        jdbc.update(
                "insert into ledger_entries(code, amount) values (?, ?)",
                CODE, 10);
        assertThat(count()).isEqualTo(1);
    }

    @Test
    void defaultRollbackIsScheduledForThisTest() {
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();
        assertThat(count()).isEqualTo(1);
    }

    @AfterEach
    void afterEachStillRunsInsideTransaction() {
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(count()).isEqualTo(1);
    }

    @AfterTransaction
    void afterTransactionSeesRolledBackState() {
        assertThat(count()).isZero();
    }
}
```

**Expected:** one test passes. Lifecycle:

1. `@BeforeTransaction`: test transaction is not open yet; the database does not have key `TEST-LIFECYCLE`.
2. `@BeforeEach`: already inside the test transaction; INSERT, SELECT sees 1.
3. `@Test`: `TestTransaction.isFlaggedForRollback() == true`; count is still 1.
4. `@AfterEach`: still in the transaction, so count is still 1.
5. Spring TestContext rolls back the transaction.
6. `@AfterTransaction`: queries outside the finished transaction; count returns to 0.

**This is a more accurate way to prove rollback** than only asserting data inside `@Test` or `@AfterEach`. No manual delete is needed here because the fixture was created inside the transaction that rolled back.

### 7.8. Test 2 — @Commit Overrides Default Rollback, Cleanup Required

**File `src/test/java/com/example/testtx/CommitOverrideTest.java`:**

```java
package com.example.testtx;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.Commit;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = TestTxApplication.class)
@Transactional
class CommitOverrideTest {

    private static final String CODE = "TEST-COMMIT";

    @Autowired
    JdbcTemplate jdbc;

    private int count() {
        return jdbc.queryForObject(
                "select count(*) from ledger_entries where code = ?",
                Integer.class, CODE);
    }

    @Test
    @Commit
    void commitOverridesTheDefaultRollback() {
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isFalse();

        jdbc.update(
                "insert into ledger_entries(code, amount) values (?, ?)",
                CODE, 20);

        assertThat(count()).isEqualTo(1);
    }

    @AfterTransaction
    void verifyCommittedRowAndCleanItUp() {
        try {
            assertThat(count()).isEqualTo(1);
        }
        finally {
            jdbc.update(
                    "delete from ledger_entries where code = ?",
                    CODE);
        }
        assertThat(count()).isZero();
    }
}
```

**Expected:** one test passes. `@Commit` on the method is a request to **commit the test-managed transaction**. `@AfterTransaction` reads the row in a separate operation after the boundary, then deletes the row in `finally` so it does not affect subsequent tests.

If you omit cleanup, the `TEST-COMMIT` data stays in the named H2 database until the DB is destroyed; in a project using a persistent/shared database, that causes even worse problems.

If a DB constraint or transaction error causes commit to fail, do not report the test as successful merely because `@Commit` is present. That is why the test includes an assertion after the transaction.

### 7.9. Test 3 — TestTransaction.end/start and NOT_SUPPORTED

**File `src/test/java/com/example/testtx/TestTransactionBoundaryTest.java`:**

```java
package com.example.testtx;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = TestTxApplication.class)
@Transactional
class TestTransactionBoundaryTest {

    @Autowired
    JdbcTemplate jdbc;

    private int count(String code) {
        return jdbc.queryForObject(
                "select count(*) from ledger_entries where code = ?",
                Integer.class, code);
    }

    @Test
    void canEndWithRollbackThenStartAnotherTestTransaction() {
        String code = "TEST-EXPLICIT-ROLLBACK";

        jdbc.update(
                "insert into ledger_entries(code, amount) values (?, ?)",
                code, 30);

        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();
        assertThat(count(code)).isEqualTo(1);

        TestTransaction.end();

        assertThat(TestTransaction.isActive()).isFalse();
        assertThat(count(code)).isZero();

        TestTransaction.start();

        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();
        assertThat(count(code)).isZero();
        // New transaction will roll back when the test ends.
    }

    @Test
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    void notSupportedDisablesTestManagedTransaction() {
        String code = "TEST-NOT-SUPPORTED";

        assertThat(TestTransaction.isActive()).isFalse();

        try {
            jdbc.update(
                    "insert into ledger_entries(code, amount) values (?, ?)",
                    code, 40);

            // No outer test-managed transaction.
            // H2 JDBC statement autocommits under this configuration.
            assertThat(count(code)).isEqualTo(1);
        }
        finally {
            jdbc.update(
                    "delete from ledger_entries where code = ?",
                    code);
        }

        assertThat(count(code)).isZero();
    }
}
```

**Expected:** two tests pass, bringing the example total so far to four tests.

In the first method, `TestTransaction.end()` immediately finishes the initial transaction according to the rollback flag. A SELECT after `end()` sees the row is gone. `TestTransaction.start()` creates a new test-managed transaction under the default rollback policy so the test ends cleanly.

In the second method, the class has `@Transactional`, but the method-level annotation with `Propagation.NOT_SUPPORTED` causes the listener **not to open a test-managed transaction** for that method. The SQL statement runs under datasource/JDBC autocommit in the H2 sample configuration; therefore cleanup in `finally` is required. Do not treat `NOT_SUPPORTED` as a "transaction that will roll back at the end of the test."

**Caution:** `Propagation.NEVER` is also among the values that cause TestContext not to open a test-managed transaction, yet that does not mean all propagation attributes on tests behave like on service methods. When you need to test `REQUIRES_NEW`, place it on a **Spring service bean** and invoke it through the proxy as in the next test.

### 7.10. Test 4 — REQUIRES_NEW Can Commit Even Though the Test Will Roll Back

**File `src/test/java/com/example/testtx/RequiresNewBoundaryTest.java`:**

```java
package com.example.testtx;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = TestTxApplication.class)
@Transactional
class RequiresNewBoundaryTest {

    private static final String CODE = "TEST-REQUIRES-NEW";

    @Autowired
    LedgerService service;

    @Autowired
    JdbcTemplate jdbc;

    private int count() {
        return jdbc.queryForObject(
                "select count(*) from ledger_entries where code = ?",
                Integer.class, CODE);
    }

    @BeforeTransaction
    void beforeTransaction() {
        assertThat(count()).isZero();
    }

    @Test
    void nestedNewTransactionCanCommitIndependently() {
        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();

        service.writeRequiresNew(CODE);

        assertThat(count()).isEqualTo(1);
    }

    @AfterTransaction
    void committedInnerRowSurvivesOuterRollback() {
        try {
            assertThat(count()).isEqualTo(1);
        }
        finally {
            jdbc.update(
                    "delete from ledger_entries where code = ?",
                    CODE);
        }
        assertThat(count()).isZero();
    }
}
```

**Expected:** one test passes. This illustrates **transaction propagation other than REQUIRED**, not advice to use `REQUIRES_NEW` everywhere.

Timeline:

```text
JUnit test thread:
  BEGIN TX-TEST (rollback by default)
  |
  +-- call Spring proxy LedgerService.writeRequiresNew()
        SUSPEND TX-TEST
        BEGIN TX-INNER
        INSERT TEST-REQUIRES-NEW
        COMMIT TX-INNER
        RESUME TX-TEST
  |
  SELECT sees committed row (H2 READ_COMMITTED)
  ROLLBACK TX-TEST
  |
  @AfterTransaction:
      row still exists -> delete cleanup
```

**Practical consequence:** a transactional test can leave database rows behind if a service uses `REQUIRES_NEW`, even when the test itself reports rollback and all assertions pass. You need cleanup or a dedicated test database/schema.

Cases where the service uses a different transaction manager/datasource are even more complex; the sample code uses a single DataSource and a single manager solely to illustrate propagation.

### 7.11. Test 5 — Real HTTP Is Not Included in JUnit Test Rollback

**File `src/test/java/com/example/testtx/RealHttpRollbackBoundaryTest.java`:**

```java
package com.example.testtx;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = TestTxApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@Transactional
class RealHttpRollbackBoundaryTest {

    private static final String CODE = "TEST-HTTP-SERVER";

    @LocalServerPort
    int port;

    @Autowired
    JdbcTemplate jdbc;

    private int count() {
        return jdbc.queryForObject(
                "select count(*) from ledger_entries where code = ?",
                Integer.class, CODE);
    }

    @Test
    void realHttpServerWorkDoesNotJoinTestThreadTransaction()
            throws Exception {

        assertThat(TestTransaction.isActive()).isTrue();
        assertThat(TestTransaction.isFlaggedForRollback()).isTrue();
        assertThat(port).isGreaterThan(0);

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create(
                        "http://127.0.0.1:" + port
                        + "/api/ledger/" + CODE))
                .timeout(Duration.ofSeconds(5))
                .POST(HttpRequest.BodyPublishers.noBody())
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertThat(response.statusCode()).isEqualTo(201);
        assertThat(count()).isEqualTo(1);
    }

    @AfterTransaction
    void serverCommittedRowSurvivesTestRollback() {
        try {
            assertThat(count()).isEqualTo(1);
        }
        finally {
            jdbc.update(
                    "delete from ledger_entries where code = ?",
                    CODE);
        }
        assertThat(count()).isZero();
    }
}
```

**Expected:** one test passes; total of **6 JUnit tests** in the example.

Even though the JUnit test has `@Transactional` and rolls back at the end of the method, the HTTP client sends a request to the embedded server listening on a random port, the server handles the request on a different thread, calls `LedgerService.writeRequired(...)` on the server thread, and **commits under the service transaction**. Rolling back the JUnit test thread **does not undo** the row committed by the server.

`@AfterTransaction` proves the row still exists after the test rollback and cleans it up. This is crucial when switching from `mockMvc.perform(...)` to live HTTP tests.

**Limitations:** the sample runs loopback HTTP/H2; it does not prove proxy/TLS, multi-instance routing, or production DB isolation. If Spring Security or other filters exist in a real project, appropriate credentials/CSRF tokens must be sent. The test intentionally avoids logging secrets or calling production endpoints.

## 8. Running the Example Suite and Reading Results

### 8.1. Gradle (Linux/macOS)

```bash
./gradlew test --tests "com.example.testtx.RollbackLifecycleTest"
./gradlew test --tests "com.example.testtx.CommitOverrideTest"
./gradlew test --tests "com.example.testtx.TestTransactionBoundaryTest"
./gradlew test --tests "com.example.testtx.RequiresNewBoundaryTest"
./gradlew test --tests "com.example.testtx.RealHttpRollbackBoundaryTest"

# Or run all tests in the module:
./gradlew test
```

### 8.2. Maven (Linux/macOS)

```bash
./mvnw -Dtest=RollbackLifecycleTest test
./mvnw -Dtest=CommitOverrideTest test
./mvnw -Dtest=TestTransactionBoundaryTest test
./mvnw -Dtest=RequiresNewBoundaryTest test
./mvnw -Dtest=RealHttpRollbackBoundaryTest test

# Or run the entire module:
./mvnw test
```

### 8.3. Windows PowerShell

```powershell
.\gradlew.bat test --tests "com.example.testtx.RollbackLifecycleTest"
.\gradlew.bat test --tests "com.example.testtx.CommitOverrideTest"
.\gradlew.bat test --tests "com.example.testtx.TestTransactionBoundaryTest"
.\gradlew.bat test --tests "com.example.testtx.RequiresNewBoundaryTest"
.\gradlew.bat test --tests "com.example.testtx.RealHttpRollbackBoundaryTest"

# If using Maven Wrapper:
.\mvnw.cmd "-Dtest=RollbackLifecycleTest" test
.\mvnw.cmd "-Dtest=CommitOverrideTest" test
.\mvnw.cmd "-Dtest=TestTransactionBoundaryTest" test
.\mvnw.cmd "-Dtest=RequiresNewBoundaryTest" test
.\mvnw.cmd "-Dtest=RealHttpRollbackBoundaryTest" test
```

Only run the commands corresponding to your project's build system; having the wrapper present and a suitable test platform is a prerequisite. **Do not mix Gradle/Maven commands in a module that does not support both**. You do not need a fixed port 8080 because the real HTTP test uses `RANDOM_PORT`.

**Expected outcome by design:** 6/6 JUnit methods succeed, `@AfterTransaction` callbacks complete. The source does not intentionally print to stdout; Spring startup logs, SQL initialization, and summaries depend on the IDE/Gradle/Maven/version. Read the test report to confirm the tests actually ran (not skipped, excluded, or falsely cached).

### 8.4. Per-Test Matrix and Post-Boundary Database State

| Test | Inside test method | After transaction | Cleanup |
|---|---|---|---|
| `RollbackLifecycleTest` | Count = 1, rollback flag true | Count = 0 | Not needed, rolled back |
| `CommitOverrideTest` | Count = 1, commit flag | Count = 1 | Deleted in @AfterTransaction |
| `TestTransactionBoundaryTest.canEnd...` | Count = 1 before `end()` | Count = 0 after `end()` | Not needed |
| `TestTransactionBoundaryTest.notSupported...` | No test tx; count = 1 | No listener rollback | Deleted in `finally` |
| `RequiresNewBoundaryTest` | Inner tx commits, count = 1 | Outer test rolls back, count still 1 | Deleted in @AfterTransaction |
| `RealHttpRollbackBoundaryTest` | Server tx commits, count = 1 | Test thread rolls back, count still 1 | Deleted in @AfterTransaction |

These states are **expected in the configured H2 environment**; if a real project uses different isolation or concurrent work, transaction visibility must be verified before hardening assertions.

## 9. When @Transactional on Tests Creates False-Positive Green Tests

### 9.1. A Service Accidentally Relies on the Test's Transaction

A production service without `@Transactional` might call two repository operations. Inside `@DataJpaTest @Transactional`, those operations accidentally run inside the test's enclosing transaction. The test passes, yet in production each repository method may use a separate transaction and fail to guarantee atomicity across the whole operation.

Anti-pattern in conclusions:

```java
@DataJpaTest
@Transactional
class TransferRepositoryTest {
    @Test
    void transferIsAtomic() {
        // Calling two repository methods here and seeing both roll back
        // does not prove the production service creates the right transaction.
    }
}
```

This is a **warning snippet**, not a standalone runnable program. To prove a service transaction boundary, test through the **Spring-managed service bean/proxy** in an environment with application transaction infrastructure and create a scenario where one operation fails after another. You must observe state after the service transaction, not just rely on an outer test-managed transaction.

### 9.2. JPA May Not Have Flushed SQL Before Test Rollback

With JPA, `repository.save(entity)` or modifying a managed entity may only update the persistence context. Hibernate usually flushes pending SQL before commit or before queries that require synchronization, yet **a test rollback may not flush all changes**. A test without a flush can pass even though a real constraint or SQL mapping will fail on production commit.

Example:

```java
repository.save(new OrderEntity(/* fields */));
entityManager.flush(); // explicitly forces SQL to run when testing DB constraints
```

This is an **illustrative snippet**, without complete DTO/repository code. When you need to test generated values, unique constraints, cascades, callbacks, or database triggers, choose the right flush/readback boundary.

Distinguish clearly:

- `flush()`: synchronizes SQL inside the transaction.
- `clear()`: detaches entities from the persistence context; **does not auto-flush**.
- `commit()`: confirms the transaction, typically flushing before commit.
- `rollback()`: undoes changes belonging to the transaction.

Do not use `findById(id)` in the same persistence context to conclude that a fresh SELECT read the row from the DB; it may return the managed instance from the first-level cache.

### 9.3. @DirtiesContext Does Not Delete Committed Data

`@DirtiesContext` marks the Spring `ApplicationContext` to be closed/removed from the test context cache; **it does not guarantee deleting committed rows** in a named H2 DB, PostgreSQL, Redis, or a message broker. For data committed by `@Commit`, `REQUIRES_NEW`, or an HTTP server, you still need cleanup/schema reset/isolated databases.

### 9.4. @Transactional(readOnly=true) on a Test Does Not Guarantee Read-Only Execution

Spring TestContext does not apply the `readOnly` attribute of a test's `@Transactional` as a service transaction contract. Even on a service, `readOnly=true` is typically a hint/optimization depending on the transaction manager/provider and should not be treated as an absolute security control forbidding all DML.

If you want to test read-only behavior of a DB or repository, check the actual database/manager and assert real effects rather than inferring from a single annotation.

## 10. Synchronous MockMvc vs. Real HTTP Can Differ in Rollback

### 10.1. Standard MockMvc Runs on the Test Thread

With `@SpringBootTest(webEnvironment=MOCK) + @AutoConfigureMockMvc`, `mockMvc.perform(...)` processes the request through mock Servlet request/response objects inside the JVM, typically synchronously on the test thread. If controller/service/JDBC code joins the current `ThreadLocal` transaction, the work can stay inside the test-managed transaction and roll back with the test.

Illustrative example:

```java
@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class MockMvcTransactionTest {

    @Autowired MockMvc mvc;

    @Test
    void postWithinMockRequest() throws Exception {
        mvc.perform(post("/api/ledger/MOCK-ENTRY"))
                .andExpect(status().isCreated());
        // If request runs synchronously and service joins test tx,
        // this row will roll back with the test transaction.
    }
}
```

This snippet assumes the endpoint from section 7 is available along with MockMvc imports. Do not generalize that `MockMvc` is always on the same thread for every async case: `Callable`, `DeferredResult`, `@Async`, or custom executors can shift work to another thread.

### 10.2. RANDOM_PORT Executes on a Server Thread

When using:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@Transactional
class RealHttpTest {
}
```

the test-managed transaction lives on the JUnit test thread. A real HTTP client sends a request to a different server thread; the service on the server can open/commit its own transaction. **Rollback of the JUnit test does not automatically roll back server work**, per the Spring Boot reference documentation.

Whether the test uses `@LocalServerPort` or a browser-like client, what matters is the **request path**. If you start a server on `RANDOM_PORT` yet still call `mockMvc.perform(...)`, the MockMvc call can still run in-process rather than over the HTTP network path.

### 10.3. Async, @Scheduled, and @TransactionalEventListener

The following tasks can execute outside the test thread's transaction or **after** the test method:

- `@Async` or `CompletableFuture.supplyAsync/runAsync`.
- Scheduled jobs or message listeners.
- Background queue consumers.
- `@TransactionalEventListener(phase = AFTER_COMMIT)`: an event listener that runs only when a transaction actually commits may **not run in a default-rollback test**.
- External broker/email/webhook/object storage side effects.

When testing event listeners or outboxes, do not "fix" tests by putting `@Commit` on everything without cleanup. Identify the event phase and transaction boundary, and test separately with appropriate fakes/outboxes/DB fixtures. If you need to test an `AFTER_COMMIT` listener, you can create a controlled committed transaction and clean up state.

## 11. @Sql: Are Fixtures Rolled Back Along with the Test?

Spring TestContext supports `@Sql` to run SQL scripts before/after a test. However, data created by a script **may** join the test-managed transaction or be committed independently, depending on `@SqlConfig.transactionMode` and execution phase.

### 11.1. By Default It Can Join the Test Transaction

Example:

```java
@SpringBootTest
@Transactional
@Sql(statements =
        "insert into ledger_entries(code, amount) values ('SQL-FIXTURE', 1)")
class SqlFixtureTest {
}
```

This is a snippet, not a complete test class; when `@Sql` executes inside a test-managed transaction under the default inference mode and the right transaction manager, the fixture INSERT can be rolled back along with the test.

Do not apply this conclusion to scripts running at `BEFORE_TEST_CLASS`/`AFTER_TEST_CLASS` or when `@SqlConfig(ISOLATED)` is requested.

### 11.2. ISOLATED Usually Creates a Separate Transaction and Commits

```java
@Sql(
    statements =
        "insert into ledger_entries(code, amount) values ('SQL-ISOLATED', 1)",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
```

This is an annotation snippet requiring proper imports and DB schema. Under isolated mode, Spring Test runs the script in an **independent transaction and commits it**. The data can remain after the test method rolls back, so cleanup at the right boundary is necessary.

You can declare `@Sql(executionPhase=AFTER_TEST_METHOD, config=ISOLATED)` to clean up fixtures, but ensure the cleanup script runs reliably, is idempotent, and does not delete data from other tests. Never run destructive scripts on a production database.

### 11.3. SQL Schema Initialization Differs from a Test Method Transaction

A `schema.sql` file run by Spring Boot's SQL initializer when starting the test context is **database setup**, not part of each test-managed transaction. Therefore, a table created at startup does not vanish after each test rollback, whereas rows INSERTed inside the test transaction can roll back. Distinguish **schema lifecycle** from **fixture data lifecycle**.

## 12. ThreadLocal, Preemptive Timeouts, and Parallel Tests

### 12.1. JDBC Transaction State Is Thread-Bound

Spring TestContext binds transaction state to the thread executing the test method. If test code switches to a worker thread, JDBC work on that worker **does not automatically join** the JUnit thread's test transaction.

Anti-pattern:

```java
CompletableFuture<Void> task =
        CompletableFuture.runAsync(() ->
                jdbc.update(
                        "insert into ledger_entries(code, amount) values (?, ?)",
                        "ASYNC-ENTRY", 1));

task.join();
```

This is a snippet, not a standalone runnable test. Even though `join()` waits for the task to finish, the task executes on a different thread and can use a different connection/autocommit. Rollback on the test thread does not automatically undo the row. Without `join()`, there is also the risk of the test ending before the work completes.

Do not rely on the test's `ThreadLocal` transaction as an atomicity mechanism for background tasks. Open a proper transaction at the executor/service boundary and clean up.

### 12.2. JUnit assertTimeoutPreemptively Is an Officially Documented Trap

The Spring Framework TestContext docs warn that JUnit's `assertTimeoutPreemptively(...)` can execute the code block on a **different thread**. If you rely on a test-managed transaction to roll back JDBC work inside that lambda, that work can run **outside the transaction**, commit, and leave data behind.

Anti-pattern:

```java
assertTimeoutPreemptively(Duration.ofSeconds(2), () -> {
    jdbc.update(
            "insert into ledger_entries(code, amount) values (?, ?)",
            "PREEMPTIVE", 1);
});
```

This snippet illustrates a potential bug and should not be copied into project transaction tests. If you need a timeout check without switching threads, consider non-preemptive `assertTimeout(...)` or an explicit transaction inside the worker thread with clear cleanup.

### 12.3. Parallel Tests Need Isolated Transaction Resources

Default rollback is **not magic** that eliminates all races:

- Two tests can target the same row/key in different transactions, causing locks/duplicate keys.
- One test can create a committed row via `REQUIRES_NEW` that another test reads.
- A test running an HTTP server or background worker can commit in the middle of another test's read.
- `@Sql(ISOLATED)` scripts can mutate shared fixtures.
- The context cache preserves Spring bean state, whereas transaction rollback only manages DB resources.
- An in-memory named H2 DB can be shared between contexts in the same JVM, depending on the URL.

In parallel CI runs, prefer a separate database/schema per worker or test suite, unique keys, idempotent setup/cleanup, and zero reliance on test order. Avoid fixed global IDs when the database is shared.

### 12.4. Do Not Use @TestMethodOrder as a Fix for Data Leakage

Ordering tests so that "test A creates data, test B deletes it" makes the suite order-dependent and hard to run in isolation. A test that commits data must clean up within its own fixture/lifecycle or environment reset. `@TestMethodOrder` is no substitute for isolation.

## 13. @Transactional on Tests vs. Services: Verifying Real Propagation

### 13.1. REQUIRED

A `@Transactional(propagation = REQUIRED)` service called from a test with an active transaction normally **joins** the test transaction if using the same `PlatformTransactionManager`. This is helpful when testing cooperating repository/service code, yet it can hide the fact that the production service is missing a transaction boundary for the entire workflow.

When the goal is to verify the service's production atomicity, leave the test method **non-transactional** so the service opens/ends its own transaction, then inspect the data after the service call. In that case, you must explicitly delete succeeded data during fixture cleanup.

### 13.2. REQUIRES_NEW

Demonstrated in section 7: the inner transaction commits separately and can survive outer rollback. With JDBC connection pools, `REQUIRES_NEW` also requires acquiring a **second connection** while the outer transaction holds the first; watch pool size and concurrency to avoid deadlock from connection starvation.

Do not use `REQUIRES_NEW` merely to dodge test rollback: it changes business semantics and production behavior.

### 13.3. NESTED, SUPPORTS, NOT_SUPPORTED, and NEVER

- `NESTED` can use savepoints in JDBC when supported by the manager/driver; its semantics are not the same as an independently committed transaction like `REQUIRES_NEW`.
- `SUPPORTS` joins a transaction if one exists, and runs non-transactionally if none exists.
- `NOT_SUPPORTED` on a **service** suspends the current transaction; on a **test method**, the listener does not open a test-managed transaction.
- `NEVER` on a **service** throws an error if a transaction exists; for the test listener, `NEVER` is a case where no test-managed transaction is opened.

Do not assume from annotations on a test that every propagation mode is emulated by the TestContext listener like Spring's service `TransactionInterceptor`. Spring Framework 6.2 supports only a **very limited** set of attributes for test-managed transactions.

### 13.4. Self-Invocation and Proxies

Spring `@Transactional` on a service is typically implemented via a Spring AOP proxy. Calling `this.innerRequiresNew()` from the same instance can bypass proxy interception, failing to open a new transaction as expected. To test propagation, call a public method through the Spring-managed bean/proxy or design an appropriate boundary.

The sample in section 7 injects `LedgerService` into the test/controller rather than constructing it with `new`, so transactions are managed properly.

## 14. Testing Rollback and Database Isolation

### 14.1. "A Query Sees the Row" Depends on Which Transaction Runs It

Suppose TX-A INSERTs a row and has not committed yet:

```text
TX-A: BEGIN
TX-A: INSERT code='A'
TX-A: SELECT code='A' -> sees 1
TX-B: SELECT code='A' -> may not see 1 yet
TX-A: ROLLBACK
TX-B: SELECT code='A' -> does not have 1
```

Under `READ_COMMITTED`, TX-B normally does not see TX-A's uncommitted row; other DBs may have lock/snapshot behaviors. Therefore:

- A SELECT in the same TX-A seeing the row **does not prove commit**.
- A SELECT in TX-B not seeing the row **does not prove the INSERT did not run**.
- A connection using `READ_UNCOMMITTED` seeing a dirty row does not make the row committed.
- An `@AfterTransaction` query or `TestTransaction.end` + query helps verify **the aftermath beyond the boundary**, provided you identify the right connection/isolation and manager.

### 14.2. H2 Differs from Production Databases

H2 is convenient for transaction and rollback demos, yet it does not represent all behaviors of PostgreSQL/MySQL/Oracle:

- Isolation/snapshot semantics differ.
- Transactional DDL and constraint checking differ.
- Generated keys/sequences/identity and triggers can differ.
- Lock waits/deadlocks/timeouts/pool behavior differ.
- SQL dialects can differ.
- FK/unique constraint timing can differ.

If production depends on locking/transaction isolation, also run Testcontainers with the **real database engine** and a controlled transaction lifecycle.

### 14.3. A Successful Commit Test Must Observe State After the Transaction

A `@Commit` test with assertions only mid-method does not prove the final state committed successfully. `@AfterTransaction` is invoked after the framework attempts commit/rollback and is therefore a good observation point; an alternative is explicitly calling `TestTransaction.flagForCommit(); TestTransaction.end();` and reading again outside the transaction.

If the database commit fails, the test must fail and the root cause must be preserved in the report. Do not catch and ignore commit exceptions just to keep the suite green.

## 15. Reactive Transactions and the Limits of Test-Managed @Transactional

### 15.1. Why Is R2DBC Not Like JDBC?

Imperative JDBC transactions are bound to a thread/connection. R2DBC transactions use `ReactiveTransactionManager` and Reactor's subscriber `Context`. A `Mono`/`Flux` generally executes database operations only when subscribed to.

Reactive service concept example:

```java
@Transactional
public Mono<Void> createOrder() {
    return databaseClient.sql(
            "insert into orders(code) values ('R-1')")
            .fetch()
            .rowsUpdated()
            .then();
}
```

This snippet needs a Spring bean class, database client/connection factory, and full imports; it is not a standalone runnable file. Simply calling `createOrder()` and `assertNotNull(publisher)` does not prove a transaction occurred. Use `StepVerifier` or a subscribe-aware integration test to verify.

### 15.2. TransactionalOperator Wraps a Publisher, Not a void JUnit Method

With R2DBC, you can use:

```java
TransactionalOperator operator =
        TransactionalOperator.create(reactiveTransactionManager);

Mono<Long> work = databaseClient.sql(
        "insert into orders(code) values ('R-2')")
        .fetch()
        .rowsUpdated()
        .as(operator::transactional);

StepVerifier.create(work)
        .expectNext(1L)
        .verifyComplete();
```

This snippet requires `reactor-test` and an R2DBC transaction manager; it is not the complete JDBC/H2 code from section 7. When the Publisher succeeds, the reactive operator commits; when `onError` occurs within the transaction scope, it typically rolls back. Cancellation also has rollback semantics under Spring Framework's `ReactiveTransactionManager`.

**Do not** place `@Transactional` on a `void` JUnit method and assume `ReactiveTransactionManager` will automatically roll back all Publishers when the method ends. To truly test reactive transactions, build a transactional Publisher, subscribe to it, and query the result after the terminal signal.

### 15.3. Do Not Wrap JDBC Inside Mono and Assume R2DBC Will Roll It Back

`Mono.fromRunnable(() -> jdbc.update(...)).as(operator::transactional)` does not convert a JDBC connection into an R2DBC connection managed by `ReactiveTransactionManager`. They are different SPIs; atomicity across heterogeneous resources requires explicit architecture, not relying on a single annotation/test.

## 16. Tips for Designing Reliable Fixtures and Cleanup

### 16.1. Prefer Rolled-Back Data When Appropriate

For repository slices or pure full-context transaction tests:

- Each test creates its own fake fixture inside the test-managed transaction.
- Do not use the same global identifiers.
- You can use `@BeforeEach` to seed if every test in the class is transactional.
- Rely on default rollback to clean up changes belonging to that transaction itself.
- Do not let asynchronous work or `REQUIRES_NEW` commit unintentionally.
- When testing JPA, flush if you need to check database constraints or persisted SQL.

### 16.2. For Tests That Must Commit, Cleanup Must Be Explicit

Cases that require a real commit:

- `@Commit`/`@Rollback(false)` tests.
- `REQUIRES_NEW` service tests.
- HTTP server tests over `RANDOM_PORT`.
- `@Sql(ISOLATED)` fixtures.
- Tests for scheduled/background operations that commit.
- Transaction tests on a real database engine for propagation/constraint timing.

Cleanup can live in `@AfterTransaction`, `finally`, test teardown in a separate transaction, or database/container resets. Use idempotent methods when possible and keep test data isolated so you do not accidentally delete other data.

**Do not use a production DB or real customer data** for rollback/commit tests. Never put secrets/passwords in SQL logs or repository examples.

### 16.3. After Commit, @AfterEach Does Not Necessarily See Final State

Remember that `@AfterEach` still runs **inside the test transaction**. With `@Commit`, the commit occurs **after** `@AfterEach`. If the goal is to test SQL commit constraints, `@AfterEach` is not enough; observe in `@AfterTransaction` or after `TestTransaction.end` once commit is requested.

### 16.4. Name Tests After What They Actually Prove

Misleading names:

- `savedPermanently()` when it only calls `repository.save` and asserts a getter.
- `rollsBackEverything()` when the test makes an HTTP call to the server.
- `transactionalServiceIsAtomic()` when an outer test transaction already wraps all operations.
- `cleanupRuns()` when the reactive delete Publisher is never subscribed to.

Names should reflect the actual **boundary and assertion**, such as `testManagedTransactionIsRolledBackAfterMethod()` or `requiresNewCommitSurvivesOuterTestRollback()`.

## 17. Common Issues and Troubleshooting Table

| Symptom | Possible cause | How to check and fix |
|---|---|---|
| `@Transactional` test still leaves rows behind | `REQUIRES_NEW`, async thread, HTTP server, isolated SQL, or another datasource | Identify transaction manager/thread/connection; clean up separately |
| `@SpringBootTest` writes SQL and data remains | Test has no `@Transactional`; service commits on its own | Add test-managed tx if appropriate, or clean up |
| `@DataJpaTest` row disappears after test | Slice rolls back by default | Expected behavior; do not confuse with a failed save |
| `@JdbcTest` sees INSERT inside method, gone afterward | Same-transaction read and end-of-test rollback | Use `TestTransaction`/`@AfterTransaction` to prove |
| `@DataR2dbcTest` leaves data behind | No default reactive test-managed rollback | Use `TransactionalOperator` + cleanup |
| `TestTransaction.isActive()` is false | No test tx, `NOT_SUPPORTED`/`NEVER` propagation, or different thread | Check annotations/listener/manager |
| `@Commit` test still does not commit | Transaction rollback-only, constraint, or manager/config error | Read exception/transaction status, verify after boundary |
| `@AfterEach` still sees row before rollback | Lifecycle callback is still inside the transaction | Use `@AfterTransaction` |
| `@BeforeAll` creates fixture that is not rolled back | Not part of per-method transaction | Clean up or use a separate transaction/template |
| `findById` sees managed state, DB constraint not thrown | JPA has not flushed | `entityManager.flush`/`repository.flush` |
| HTTP POST in `RANDOM_PORT` leaves data | Server transaction differs from test thread | HTTP integration cleanup, dedicated test DB |
| `mockMvc.perform` rolls back but HTTP does not | In-process path vs. separate server thread/connection | Clarify test type, assert at the right boundary |
| Preemptive timeout pollutes DB | Callback runs on another thread without `ThreadLocal` tx | Non-preemptive timeout/explicit worker transaction |
| `@Transactional(noRollbackFor=...)` on test does not commit as expected | Listener does not support `rollbackFor`/`noRollbackFor` attrs | Use `@Commit`/`@Rollback`/`TestTransaction` |
| `@Rollback(false)` test affects subsequent tests | Data was committed | Clean up in `@AfterTransaction` |
| `@Sql` fixture does not roll back | `TransactionMode.ISOLATED`/class-level phases | Check SQL config, scripts, cleanup |
| JDBC `@Async` writes row outside test transaction | Another thread does not inherit tx state | Manage transaction/cleanup on worker thread |
| `@DirtiesContext` yet row still remains | Context cache differs from persistent DB state | Reset DB/schema or delete explicitly |
| Tests pass alone, fail as a suite | Shared schema, committed leftovers, parallel conflicts | Unique fixture keys, isolation, deterministic cleanup |
| Multi-manager test connects to wrong DB | Transaction manager mismatches DataSource | Select manager via qualifier, check wiring |
| Real DB fails, H2 passes | Dialect/isolation/constraints differ | Also test against the production database engine |
| `@Transactional` on service does not run | Service instantiated with `new`/self-invocation or proxy bypassed | Invoke through Spring-managed proxy/bean |
| `readOnly` transaction does not forbid writes as expected | `readOnly` is not a hard security guarantee | Test actual manager/DB enforcement |

### 17.1. Effective Debugging Order

1. Confirm the class runs via `SpringExtension`/TestContext.
2. Confirm `PlatformTransactionManager` exists and the right one is selected.
3. Confirm `@Transactional` on the test class/method or an auto-transactional slice.
4. Check if the method has `NOT_SUPPORTED`/`NEVER`, `@Commit`, or `@Rollback(false)`.
5. Inside the test, inspect `TestTransaction.isActive()` and `isFlaggedForRollback()`.
6. Determine whether operations run on the **same thread**, same DataSource/manager.
7. For Spring services, check propagation and proxy interception.
8. For web tests, determine whether it is in-process `MockMvc` or real HTTP `RANDOM_PORT`.
9. For JPA, determine whether pending state has been flushed.
10. For `@Sql`, check transaction mode, execution phase, and scripts.
11. Measure database state after the transaction boundary, not only inside the method.
12. If data remains, clean it up; if environments differ, test on the real database engine.
13. Read reports and inspect connection/transaction logs safely without dumping secrets.

## 18. Exercises and Answers

### Exercise A — Why Doesn't @SpringBootTest Auto-Roll Back?

A test only has `@SpringBootTest` and calls a service that writes data. After the test, the row remains. Is Spring Test rollback broken?

**Answer:** no. `@SpringBootTest` loads the application context, but does not create a test-managed transaction by default. The service can open and commit its own transaction. If you want default rollback, put `@Transactional` on the test class/method with an appropriate `PlatformTransactionManager` or use a transactional test slice. If the test's goal is production commit behavior, do not wrap it in an outer test transaction just to make the row disappear; instead, verify the service boundary and clean up.

### Exercise B — How Does @BeforeEach Differ from @BeforeTransaction?

In a `@Transactional` test, `@BeforeEach` INSERTs a row and `@AfterEach` SELECT still sees the row. Can we conclude rollback did not run?

**No.** Both lifecycle methods run inside the test transaction. Rollback occurs **after `@AfterEach`**. To prove the row was rolled back, use `@AfterTransaction` or `TestTransaction.end()` and query again.

### Exercise C — Wanting to Commit One Test

A class has `@Transactional` and 20 tests that roll back by default. Only one test needs to commit to verify `AFTER_COMMIT`. What should you use?

**Answer:** place `@Commit` or `@Rollback(false)` on that specific **test method**; verify the effect after the transaction and clean up the committed data. Do not put `@Commit` on the entire class if the remaining 19 tests must roll back.

### Exercise D — Is TestTransaction.flagForCommit Enough?

A method calls `TestTransaction.flagForCommit()`, and immediately afterward asserts a DB query. Does it know whether the transaction committed?

**Not yet.** The flag only changes the ending plan. To check commit immediately, call `TestTransaction.end()` to finish the transaction and then read at the new boundary. If you want to continue with another test-managed tx, call `start()` following the lifecycle.

### Exercise E — REQUIRES_NEW Causes a Leak

A `@Transactional` JUnit test calls a Spring service using `REQUIRES_NEW`. After the outer test rolls back, the row from the service remains. Why?

**Answer:** the inner transaction committed independently. Rollback of the outer test transaction does not undo the inner commit. The test needs `@AfterTransaction`/`finally` cleanup or an isolated database. You should also verify the service method was actually invoked through the Spring proxy.

### Exercise F — Real HTTP Differs from MockMvc

A POST with `MockMvc` is rolled back after the test, yet switching to `RANDOM_PORT` + HTTP client leaves the row behind. Why?

**Answer:** synchronous `MockMvc` typically executes on the test thread; live HTTP is handled by the server on a different thread/transaction. `@Transactional` on the JUnit test does not automatically encompass the server transaction. You need cleanup and tests that match the real transaction boundary.

### Exercise G — JPA Without Flushing

A `@DataJpaTest` test calls `repository.save(...)`, asserts the entity ID, and finishes. Production later hits a unique constraint violation. Why did the test miss it?

**Answer:** JPA may hold pending inserts/updates in the persistence context, while the test transaction rolls back before the provider executes a flush path like production. The test should call `entityManager.flush()` or `repository.flush()` if the goal is to verify DB constraints, and account for the ID generator/DB engine.

### Exercise H — @Transactional(noRollbackFor=...) on a Test

You want to commit a test even if an assertion throws an exception, so you add `@Transactional(noRollbackFor = AssertionError.class)`. Will that reliably change test-managed rollback?

**No.** The Spring TestContext listener does not apply `noRollbackFor` to a test-managed tx. Use `@Commit`/`@Rollback(false)` for the test's transaction policy, but **do not use commit to mask a test assertion failure**; check transaction status and clean up data.

### Exercise I — A CompletableFuture Task Outside the Test Transaction

The test thread has a transaction, yet an asynchronous task performs a JDBC update and commits. Why did default rollback not save it?

**Answer:** imperative transaction state is thread-bound; worker threads do not inherit it automatically. Manage transactions/cleanup in the appropriate executor/service, and await task completion before asserting.

### Exercise J — R2DBC Mono Has No Data

A `@DataR2dbcTest` test creates an insert `Mono` without subscribing; the row never appears. Did test-managed rollback delete it?

**Answer:** SQL may never have run at all. Reactive Publishers are typically lazy; you must subscribe/verify for DB work to occur. Then check the transaction scope with `TransactionalOperator`/a proxied reactive service; do not infer from default JDBC rollback.

### Exercise K — @Sql ISOLATED

You use `@SqlConfig(transactionMode=ISOLATED)` to insert a fixture into the DB, yet after the `@Transactional` test rolls back, the fixture remains. Is this a Spring bug?

**No.** `ISOLATED` creates a separate transaction and commits it; outer test rollback does not undo it. Use an isolated cleanup script or a dedicated database/schema.

### Exercise L — Turning On @Rollback(false) for the Whole Suite?

A team wants to turn on `@Rollback(false)` for every integration test to "be like production." What are the risks?

**Answer:** data leakage, test order dependence, flakiness, database growth, unique key collisions, and difficult cleanup. Only enable commit when needed to prove a boundary; keep most repository tests on default rollback and maintain a focused group that tests real commit/rollback.

## 19. QA Checklist Before Concluding a Rollback Test Is Valid

- [ ] Identified whether the test uses `@SpringBootTest`, `@JdbcTest`, `@DataJpaTest`, or `@DataR2dbcTest`.
- [ ] Known whether the annotation creates a test transaction automatically.
- [ ] Appropriate `PlatformTransactionManager` is present for test-managed JDBC/JPA.
- [ ] Using Spring's `org.springframework.transaction.annotation.Transactional` import.
- [ ] Not confusing test-managed rollback with service declarative rollback rules.
- [ ] Distinguished an active transaction from the rollback flag.
- [ ] Not assuming `@Transactional` `rollbackFor`/`noRollbackFor` on a test behaves like on a service.
- [ ] Using `@BeforeEach`/`@AfterEach` and `@BeforeTransaction`/`@AfterTransaction` at the proper lifecycle points.
- [ ] Not using `@BeforeAll` to create fixtures expecting per-test rollback.
- [ ] If `@Commit`/`@Rollback(false)`, querying after the boundary and cleaning up.
- [ ] If `TestTransaction.end/start`, knowing clearly which transaction just ended.
- [ ] If `NOT_SUPPORTED`/`NEVER`, not relying on auto-rollback.
- [ ] If service uses `REQUIRES_NEW`, having tests proving independent inner commit/rollback.
- [ ] If testing via HTTP `RANDOM_PORT`, managing server-side committed data.
- [ ] With `MockMvc`, verified whether the request is synchronous or uses an async thread.
- [ ] With JPA, flushing when catching DB constraints and not mistaking the first-level cache for a persisted row.
- [ ] If using `@Sql(ISOLATED)`, aware that scripts commit separately.
- [ ] Not using JUnit `assertTimeoutPreemptively` when relying on thread-bound rollback.
- [ ] Not using `CompletableFuture`/`@Async` while assuming it inherits the test tx.
- [ ] Not using `@DirtiesContext` as a database cleanup mechanism.
- [ ] Not mixing JDBC with R2DBC and expecting them to share a transaction via annotation.
- [ ] For parallel CI, using separate databases/schemas/keys and deterministic cleanup.
- [ ] Not using production DBs/secrets or real customer fixture data.
- [ ] For DB-specific isolation/constraints, testing against the production engine.
- [ ] Tests were actually executed by JUnit, with reports showing pass/fail/skipped counts.
- [ ] Test names/assertions reflect the transaction boundary they prove.

## 20. Summary

**`@Transactional` on a Spring test method is a tool for managing a test-managed transaction with default rollback, not a promise that every application side effect will roll back.**

The default mechanism applies most cleanly to JDBC/JPA work sharing the same transaction manager, connection, and test thread. The test-managed transaction spans `@BeforeEach`, `@Test`, and `@AfterEach`; `@BeforeTransaction` and `@AfterTransaction` run outside that boundary.

When you need to change the policy, use `@Commit`, `@Rollback(false)`, or `TestTransaction`. When testing production behavior, watch out for `REQUIRES_NEW`, service proxies, HTTP server threads, async work, test SQL fixtures, database constraints, and isolation. **Default rollback only undoes work that actually belongs to that transaction.**

A good test does not merely say "transaction is active"—it **measures data after the transaction ends** and cleans up committed changes accurately. Keep test suites fast and isolated with rollback where appropriate, add a dedicated set of commit/boundary tests with intentional cleanup, and use a real database engine when rules depend on the RDBMS.

## Official References

- [Spring Framework 6.2 — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): Test-managed transactions, supported attributes, default rollback, lifecycle, `TestTransaction`, timeout thread caveats.
- [Spring Framework — @Rollback annotation](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-rollback.html): default rollback, `@Rollback(false)`, method/class override.
- [Spring Framework — @Commit annotation](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-commit.html): commit test-managed transaction.
- [Spring Framework — @BeforeTransaction / @AfterTransaction](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-beforetransaction.html): lifecycle hooks outside test transaction.
- [Spring Framework — TestTransaction Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/transaction/TestTransaction.html): `flagForRollback`, `flagForCommit`, `end`/`start`, `active`.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `RANDOM_PORT` thread caveat, JDBC/JPA slices transactional default.
- [Spring Framework — Executing SQL Scripts](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): `@Sql` and `@SqlConfig(TransactionMode.ISOLATED)`.
- [Spring Framework — Declarative @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): service transaction rules and propagation.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`/`REQUIRES_NEW`/`NESTED` and resource implications.
- [Spring Boot — SQL Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html): `schema.sql`, embedded DataSource initialization.
