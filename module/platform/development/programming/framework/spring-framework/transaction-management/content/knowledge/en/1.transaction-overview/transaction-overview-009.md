# Roadmap from Commit and Rollback Mechanisms to Behavior Verification

## 1. Lesson destination

In Spring Framework, understanding transactions does not stop at putting `@Transactional` on a method. What must be proven is: **when a business operation finishes, which data changes are retained, which changes are discarded, and why**.

This lesson guides learners from commit/rollback concepts to setting transaction boundaries, creating controlled failure scenarios, writing integration tests, and observing real outcomes. Examples use **Spring Boot 3.x, Java 17+, Spring JDBC, and the H2 database** to stay focused on transactions; the core rules also apply to Spring Data JPA, though when SQL reaches the database may differ due to flushing mechanisms.

After this lesson, you will be able to:

1. Describe the `begin → execute → commit/rollback → release resources` lifecycle.
2. Identify which methods and calls actually run inside a Spring-managed transaction.
3. Predict outcomes for `RuntimeException`, checked exceptions, and exceptions caught inside a method.
4. Distinguish genuine rollback from *the test itself rolling back* and mistakenly assuming the application works.
5. Write tests that measure data state **after the call through the transactional proxy has finished**.
6. Recognize when to progress to propagation, isolation, rollback-only, and multi-resource transactions.

## 2. Learning map: from mechanism to evidence

| Stage | Question to answer | Proof of completion |
| --- | --- | --- |
| 1. Model | What do commit and rollback do? | Able to sketch the transaction lifecycle and before/after states |
| 2. Boundary | Who opens/closes the transaction in Spring? | Able to identify proxy, service, transaction manager, and database |
| 3. Error rules | Which errors roll back by default? | Correctly predict the scenario table in section 5 |
| 4. Experiment | How do we create success and failure cases? | Able to run a service that intentionally triggers errors |
| 5. Verification | Is data actually persisted or discarded? | Integration test queries state after the call completes |
| 6. Extension | What changes with nested transactions or multiple resources? | Knows to ask about propagation, isolation, and atomicity limits |

Do not jump straight from stage 1 to advanced attributes. Without first proving that an `INSERT` commits or rolls back in a simple transaction, debating `REQUIRES_NEW` or `NESTED` is easily built on false assumptions.

## 3. Commit, rollback, and atomicity

A transaction groups multiple database operations into one unit of work. The **atomicity** property in ACID requires the group of operations to be accepted as a single block or discarded according to the capabilities of the transaction manager and database. **Consistency** depends on both data constraints and business rules; transactions do not automatically guarantee that business logic was written correctly. **Isolation** governs interactions with concurrent transactions; **durability** concerns committed changes being retained by the DBMS per its guarantees.

- **Commit**: instructs the database to finalize the transaction; valid changes become the accepted result of the transaction.
- **Rollback**: instructs the database to discard **uncommitted** changes belonging to that transaction.
- **Transaction boundary**: the start and end points of the transaction scope; in Spring, usually placed on a business operation in the service layer.
- **Rollback-only**: a state indicating a transaction has been marked for mandatory rollback; a subsequent commit call cannot turn it into a successful commit.

Example transferring money between two accounts in the same database:

```text
BEGIN
  UPDATE account SET balance = balance - 100 WHERE id = 'A';
  UPDATE account SET balance = balance + 100 WHERE id = 'B';
COMMIT            ← both updates are retained

BEGIN
  UPDATE account SET balance = balance - 100 WHERE id = 'A';
  UPDATE account ...  ← error before the credit step
ROLLBACK          ← uncommitted debit update is discarded
```

Key condition: both statements must participate in **the same transaction of the same resource management system**. If the first statement commits on its own before the second fails, rolling back the second transaction cannot undo the earlier commit. An email, HTTP request, or event already sent to another system is not automatically rolled back by the database either.

## 4. How does Spring apply a transaction to a call?

With standard **imperative** transaction configuration, `@Transactional` is metadata. Spring uses transaction infrastructure and typically an **AOP proxy** to apply that metadata when a Spring bean method is invoked externally through the proxy.

```text
Caller / Controller
       |
       v
Transactional proxy
       |
       +--> TransactionManager: start or join transaction
       |
       v
Service method ---> JdbcTemplate / Repository ---> Database
       |
       +--> Returns normally?            -> evaluate commit
       +--> Throws past the proxy?       -> evaluate rollback rules
       |
       v
TransactionManager: commit / roll back, clean up resources
       |
       v
Caller receives result or exception
```

In JDBC applications, the corresponding `PlatformTransactionManager` (e.g., `JdbcTransactionManager`/`DataSourceTransactionManager`) coordinates transactions over the `DataSource`. Spring binds JDBC resources to the corresponding execution thread so `JdbcTemplate` calls use the right connection within the transaction. You normally do not manually call `setAutoCommit(false)`, `commit()`, or `rollback()` when using `@Transactional`.

Practical usage rules:

- Place `@Transactional` on a **business-meaningful service method**, usually public, managed by Spring, and called by another bean through its proxy.
- If `this.innerMethod()` calls another `@Transactional` method in the same object, that call **bypasses the proxy** under default proxy mode; `innerMethod`'s own transaction attributes do not take effect automatically.
- `@Transactional` does not work merely because the annotation exists: the application needs a transaction manager and enabled transaction management. In properly configured Spring Boot JDBC/JPA projects, Boot usually auto-configures these components.
- Imperative transactions are tied to the current thread's execution context. Spawning a new thread manually or invoking `@Async` does not automatically propagate the original transaction to the new thread. Reactive transactions use a different context mechanism and should be studied separately.
- Method-call completion **is not sufficient proof** of a successful commit: errors can occur during flush or when the transaction manager executes commit.

### 4.1. Key defaults of `@Transactional`

| Attribute | Common value | Meaning |
| --- | --- | --- |
| `propagation` | `REQUIRED` | Joins existing transaction, or creates a new one if none exists |
| `isolation` | `DEFAULT` | Follows database/transaction manager default level |
| `readOnly` | `false` | Standard read/write transaction |
| `rollback rule` | `RuntimeException` and `Error` | Marks rollback by default when these unchecked errors escape past the interceptor |
| Checked `Exception` | Does not roll back by default | Requires configuring `rollbackFor` when business logic demands it |
| `timeout` | Infrastructure default | Does not guarantee a fixed time limit across all systems by default |

These settings do not replace locking rules, durability guarantees, or actual database capabilities.

## 5. Predicting behavior before running code

Consider a `@Transactional` method that has executed an `INSERT` into the database. The following table assumes **a single independent Spring transaction**, using JDBC, not marked rollback-only by another mechanism:

| Scenario | What happens at the proxy boundary | Expected outcome |
| --- | --- | --- |
| Normal completion | No error forcing rollback | **Commit**; row exists |
| Throws `IllegalStateException` out | `RuntimeException` escapes past interceptor | **Rollback**; row does not exist |
| Throws `IOException` out | Checked exception, no custom rollback rule | **Commit** by default, even though caller receives exception |
| Throws `IOException` with `rollbackFor = IOException.class` | Rule requires rollback | **Rollback** |
| Throws then `catch`es inside, then returns normally | Interceptor never sees that exception | Usually **commits**, unless transaction is already rollback-only or another error occurs |
| Error from a participating transaction marks outer transaction rollback-only | Outer caller may catch the error, but rollback-only state persists | **Rollback**; when outer tries to commit, `UnexpectedRollbackException` may occur |

Point to remember: "an exception occurred" and "it rolled back" are **not synonymous**. You must know the exception type, where it is caught, the rollback rules, and which actual transaction is active.

### 5.1. Transaction boundaries are business decisions

Suppose `placeOrder` must save an order and deduct inventory. If both must succeed together, the transaction usually wraps **the entire operation** rather than each save statement individually:

```java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderService(OrderRepository orders, InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void placeOrder(Order order) {
        orders.save(order);
        inventory.reserve(order.items());
    }
}
```

This is **structural illustrative code**, not a standalone program: `Order`, `OrderRepository`, `InventoryRepository`, and `reserve` must be defined in a real project. When both repositories share the same transaction manager/database, if `reserve` throws a runtime exception out, uncommitted changes from `save` are also rolled back. If `reserve` calls an HTTP service or writes to a database managed by a different transaction manager, this atomic guarantee no longer holds automatically.

## 6. Hands-on: producing commit and rollback evidence with Spring JDBC

We build a small example: each operation inserts a row into `tx_events`. Whether the save "succeeded" or "failed" can be inspected by row count **after** the service returns or throws an exception.

### 6.1. Structure and dependencies

Create a Gradle project with Java 17+ and the following files:

```text
tx-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/txlab/
    │   │   ├── TxLabApplication.java
    │   │   └── LedgerService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/txlab/
        └── TransactionFlowTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'tx-lab'
```

`build.gradle` (a specific Spring Boot 3.x/Java 17 combination so the example runs reproducibly):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

You can generate an equivalent project via Spring Initializr and adjust plugin versions to match a currently maintained Spring Boot release in your environment. The example depends only on the JDBC starter and H2; no web server is needed. To use `./gradlew`, the project must have the Gradle Wrapper provided by Initializr or generated with an installed Gradle.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:txlab;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE tx_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    label VARCHAR(80) NOT NULL
);
```

In-memory H2 is well suited for controlled experiments. `spring.sql.init.mode=always` ensures Spring Boot runs the initialization script when building the context. The table structure is minimal to avoid JPA's complex flush behaviors in a first lesson.

### 6.2. Application and service with outcome branches

`src/main/java/com/example/txlab/TxLabApplication.java`:

```java
package com.example.txlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxLabApplication.class, args);
    }
}
```

`src/main/java/com/example/txlab/LedgerService.java`:

```java
package com.example.txlab;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LedgerService {
    private final JdbcTemplate jdbc;

    public LedgerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void saveSuccessfully(String label) {
        insert(label);
    }

    @Transactional
    public void saveThenThrowRuntime(String label) {
        insert(label);
        throw new IllegalStateException("Simulated runtime failure");
    }

    @Transactional
    public void saveThenThrowChecked(String label) throws IOException {
        insert(label);
        throw new IOException("Simulated checked failure");
    }

    @Transactional(rollbackFor = IOException.class)
    public void saveThenThrowCheckedWithRollback(String label) throws IOException {
        insert(label);
        throw new IOException("Simulated checked failure");
    }

    @Transactional
    public void saveThenCatchInside(String label) {
        insert(label);
        try {
            throw new IllegalStateException("Handled inside method");
        } catch (IllegalStateException ignored) {
            // Intentional exception-swallowing example: proxy sees normal return.
        }
    }

    private void insert(String label) {
        jdbc.update("INSERT INTO tx_events (label) VALUES (?)", label);
    }
}
```

All public methods above are **called by an external bean**, passing through Spring's proxy; `insert` is a private helper running inside the enclosing method's opened transaction. For `saveThenCatchInside`, the intent is demonstrating transaction observation, **not encouraging ignoring business errors**.

### 6.3. Integration test verifying real state

`src/test/java/com/example/txlab/TransactionFlowTest.java`:

```java
package com.example.txlab;

import java.io.IOException;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class TransactionFlowTest {
    @Autowired
    private LedgerService service;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void clearTable() {
        jdbc.update("DELETE FROM tx_events");
    }

    private long countRows() {
        return jdbc.queryForObject("SELECT COUNT(*) FROM tx_events", Long.class);
    }

    @Test
    void normalReturnCommits() {
        service.saveSuccessfully("ok");
        assertEquals(1L, countRows());
    }

    @Test
    void runtimeExceptionRollsBack() {
        assertThrows(IllegalStateException.class,
                () -> service.saveThenThrowRuntime("runtime"));
        assertEquals(0L, countRows());
    }

    @Test
    void checkedExceptionCommitsByDefault() {
        assertThrows(IOException.class,
                () -> service.saveThenThrowChecked("checked"));
        assertEquals(1L, countRows());
    }

    @Test
    void rollbackForMakesCheckedExceptionRollback() {
        assertThrows(IOException.class,
                () -> service.saveThenThrowCheckedWithRollback("checked-rollback"));
        assertEquals(0L, countRows());
    }

    @Test
    void caughtRuntimeExceptionDoesNotAutomaticallyRollback() {
        service.saveThenCatchInside("caught");
        assertEquals(1L, countRows());
    }
}
```

**Decisive point of the test:** this test class **is not annotated with `@Transactional`**. Each service call goes through the Spring proxy so the business transaction completes. Afterward, the `SELECT COUNT(*)` query from the test runs outside the service's transaction, measuring the observed commit/rollback outcome. `@BeforeEach` clears the previous case's data so tests remain independent under JUnit's default sequential execution.

Run from the `tx-lab` directory, with JDK 17+ and the Gradle Wrapper generated:

```bash
./gradlew test
```

On Windows:

```powershell
.\gradlew.bat test
```

**Expected result:** all **5 tests pass**. The row counts observed immediately after each corresponding call are `1, 0, 1, 0, 1` in the order of the test methods listed above. JUnit **does not guarantee test execution order** and there is no fixed application stdout for these 5 tests; therefore never infer results from log order. Detailed reports are located in `build/reports/tests/test/index.html`.

If the Gradle Wrapper is missing, install a compatible Gradle version and run `gradle test` or generate the wrapper first. Do not use plain `javac` for this Spring example because classes must be compiled with Spring/JUnit/H2 dependencies on the classpath; Gradle handles that.

### 6.4. Why does this test suite prove more than "no exception"?

- `normalReturnCommits` verifies **the data exists**, not merely that the method returned.
- `runtimeExceptionRollsBack` verifies both the exception **and** that the row disappeared; `assertThrows` alone does not prove rollback.
- `checkedExceptionCommitsByDefault` is a counterexample to the belief that "any error rolls back."
- `rollbackForMakesCheckedExceptionRollback` proves a declarative attribute change alters the persisted data outcome.
- `caughtRuntimeExceptionDoesNotAutomaticallyRollback` shows that **where an exception is caught** matters just as much as the exception type.

This is an example of verifying behavior at the application/database boundary. It does not prove full business correctness, does not replace concurrency tests, and does not imply H2 shares all locking or isolation behavior with PostgreSQL/MySQL in production.

## 7. A reusable verification workflow

When encountering a real transactional service, follow this sequence instead of guessing from annotations:

1. **Define the business invariant**: e.g., "a payment record must not remain if inventory deduction fails."
2. **Scope resources and boundaries**: which database, which transaction manager, and which bean method the caller invokes through a proxy.
3. **Choose the failure point**: after the first write operation but before the business operation finishes; specify runtime or checked exception.
4. **Capture baseline**: row counts, balances, and initial state; test data must be isolated.
5. **Invoke along the real path**: caller → service bean → repository/JDBC, never calling an internal method directly via `this` to test an annotation.
6. **Let the call finish**: receive success or catch the exception outside the transaction.
7. **Read back in an independent context**: run a post-transaction query to verify which rows exist. With JPA, consider `flush`/`clear` or querying in a new transaction to avoid reading stale persistence context state.
8. **Compare against the invariant**: if state is wrong, inspect the transaction manager, exception rules, transaction boundary, and propagation before tweaking annotations blindly.
9. **Test the control case too**: one success case where data is retained and one failure case where data is discarded.

When testing through HTTP, controllers should not be assumed to be the transaction boundary just because the request starts there. Trace the actually proxied services and remember that non-database calls (HTTP, email, messaging, filesystem) do not participate in ordinary JDBC transactions.

## 8. Common pitfalls that invalidate verification

### 8.1. `@Transactional` on the test masks real commits

In Spring TestContext, a test annotated with `@Transactional` typically opens a **test-managed transaction** and **rolls back by default after the test**. A service with `REQUIRED` may simply join the test's transaction, making data visible inside the test without ever having been committed by the boundary you meant to evaluate. `@Commit`, `@Rollback(false)`, or `TestTransaction` can control test-managed transactions when needed; they **do not replace** designing proper observation points.

Counterexample:

```java
@SpringBootTest
@Transactional
class MisleadingTest {
    // A REQUIRED service may just join the test-managed transaction.
    // assertEquals(1, count()) inside the test does not prove the service committed on its own.
}
```

The snippet above only illustrates an anti-pattern, **not a complete test**. With Hibernate/JPA, `flush` at the right point so database constraint violations surface during the test instead of being deferred until transaction end.

### 8.2. Self-invocation and unproxiable methods

`this.saveWithNewTransaction()` inside the same bean bypasses the default proxy. Putting `@Transactional(propagation = REQUIRES_NEW)` on an internally called method and expecting an independent transaction is wrong. Extract the behavior needing its own transaction into **another bean**, or use `TransactionTemplate` when explicit programmatic control is needed. Do not use `@PostConstruct` to test transaction proxies before bean initialization completes.

### 8.3. Catching errors too early or marking rollback-only

`catch`-and-continue is a business decision; it may allow the transaction to commit. If rollback is truly needed after handling an error, **rethrow an appropriate exception**, configure rollback rules, or in special cases mark rollback-only via `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()`. The last option couples code to Spring infrastructure and is only valid inside an interceptor-managed transaction context; do not overuse it for normal control flow.

### 8.4. Confusing propagation scopes

- **`REQUIRED`**: child scope can share the same *physical transaction* with the outer scope. If the inner scope marks rollback-only, the outer scope cannot commit successfully even if it catches the exception; `UnexpectedRollbackException` may be thrown.
- **`REQUIRES_NEW`**: suspends the outer transaction and opens an independent physical transaction; inner commit can persist even when the outer rolls back. Watch connection pool capacity.
- **`NESTED`**: uses a savepoint inside the same physical transaction when supported by the transaction manager and JDBC resource; can roll back to the savepoint without discarding all outer work. Do not assume every JPA/JTA provider or database supports it identically.

Only after verifying basic `REQUIRED` behavior should you add tests for other propagation policies, because outcomes depend on the caller/inner relationship, manager, and database.

### 8.5. Confusing `readOnly`, isolation, or cache with transaction outcomes

`@Transactional(readOnly = true)` is primarily an optimization hint for the infrastructure; **it is not a mechanism that blocks all writes by default** across every database/driver. `isolation` tunes concurrent data visibility, not business race conditions on its own. With ORMs, the first-level cache may return a managed entity; to prove a committed result, read in a context capable of seeing persisted data after the transaction ends.

### 8.6. Non-database side effects

JDBC rollback does not recall sent emails, messages already pushed to a message broker, or HTTP calls that already succeeded. For workflows spanning multiple systems, consider **transactional outbox**, idempotency, and saga/compensation as needed. Those are subsequent topics, not something a single `@Transactional` attribute solves automatically.

## 9. Observing and diagnosing when outcomes diverge from predictions

Selective logging can be enabled in lab environments:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Logs help locate when a transaction starts/joins/ends and where rollback is decided; exact logger names and messages vary by transaction manager and Spring version. **The final proof remains the data state queried after the transaction**, not a log line like "Executing rollback."

If a test fails, check systematically:

| Symptom | Hypothesis to verify | How to check |
| --- | --- | --- |
| Runtime exception thrown yet row remains | Call bypassed proxy; write ran outside transaction; another transaction already committed | Inspect bean/call path, manager, SQL connection, and earlier commits |
| Checked exception yet row is kept | That is the default unless a rollback rule is declared | Add `rollbackFor` per business requirements and re-run test |
| Test reads the row yet another context does not see it | Test is in its own transaction or reading from persistence context | Read after the transaction finishes, using an independent query/context |
| Outer catches error yet still cannot commit | Inner `REQUIRED` marked rollback-only | Locate the participating transaction and cause of `UnexpectedRollbackException` |
| Test fails only when run in parallel | Shared test data/connection/schema or concurrent transactions | Isolate fixtures, database, and observation timing |
| Constraint error appears only at the end | JPA had not flushed yet, or error occurred at commit | Explicitly flush at the point under test and verify after the boundary |

Avoid using a debugger or trace logs to deduce atomicity when data tests contradict your reasoning: first verify you are observing **the right database, the right row, and the right transaction**.

## 10. Completion criteria and next steps

Test yourself with three questions:

1. Method A inserts a row and throws `IOException`; why might the row still exist by default? What is the minimal declaration change to make it roll back?
2. Why is a test annotated with `@Transactional` followed by `assertEquals(1, countRows())` **insufficient** to prove a service committed?
3. Why can an outer `@Transactional` method that catches an exception from an inner `REQUIRED` method still receive `UnexpectedRollbackException` upon finishing?

Reference answers: **(1)** checked exceptions are not in the default rollback rules; use `rollbackFor = IOException.class` when needed. **(2)** the test may hold an uncommitted transaction that rolls back by default at the end of the test. **(3)** the inner scope joined the same physical transaction and marked it rollback-only; the outer scope cannot override that decision with a commit.

Once all 5 integration tests in section 6 pass and you can explain each `1/0` state, proceed in order: **propagation** (`REQUIRED` → `REQUIRES_NEW` → `NESTED` and savepoints), **isolation/concurrency**, **JPA flush and locking**, **rollback across multiple resources**, and finally **testing against real databases with Testcontainers**. Each stage should include at least one verified commit path and one verified rollback or failure path.

### Official documentation

- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Transaction Management in TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
