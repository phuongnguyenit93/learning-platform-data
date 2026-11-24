# Data Cleanup Strategies When Rollback Does Not Cover All Operations

In Spring Boot testing, `@Transactional` often creates a false sense of safety: the test writes data, runs assertions, and Spring automatically rolls back. That holds **only for changes that actually participate in the transaction managed by Spring TestContext**. When a test sends an HTTP request to a real server, the business transaction runs in a separate thread/server context. When a service uses `REQUIRES_NEW`, part of the work commits in an independent transaction. Effects on Redis, Kafka, email, object storage, the filesystem, or payment APIs are also not automatically rolled back by a `JpaTransactionManager`.

Consequently, a test suite can pass on the first run and fail on the second: duplicate unique keys, orphan rows, stale caches, messages processed late by consumers, or uploaded files left behind. A proper cleanup strategy is not merely calling `deleteAll()`, but **explicitly identifying transaction boundaries, data ownership, task completion timing, deletion mechanisms, idempotency, and verification of a clean state**.

This Knowledge lesson belongs to the **Transaction Testing** track and explains how to choose among `@AfterEach`, `@Sql` with an isolated transaction, `REQUIRES_NEW` cleanup services, `TestTransaction`, fake resets, dedicated namespaces/containers, and compensation. The complete example uses **Java 17, Spring Boot 3.5, JPA/H2, and `@SpringBootTest(RANDOM_PORT)`** to demonstrate both server-side commits and side effects outside the DB transaction.

## 1. Why Doesn't Test Rollback Cover Everything?

Trace the execution path:

```text
JUnit test method
    |
    +-- Spring TestContext test-managed transaction (if any)
    |       +-- repository operations on same thread, same manager
    |           normally join and roll back after the test
    |
    +-- HTTP client: TestRestTemplate
            |
            v
        Embedded HTTP server (different thread)
            |
            +-- @Transactional service
            |      +-- JPA INSERT/UPDATE/DELETE
            |      +-- server commit / rollback
            |
            +-- side effects outside DB
                   +-- Redis / Kafka / file / fake payment /
                        external API / async worker
```

Spring Boot explicitly notes: with `@SpringBootTest(webEnvironment = RANDOM_PORT)` or `DEFINED_PORT`, client and server run on different threads, so **server transactions do not roll back with the test-managed transaction**. An HTTP 201 response can mean the server already committed data, even when the test method is annotated with `@Transactional`.

**Three critical questions before choosing a cleanup strategy:**

1. **Who owns the resource?** The current test, one test class, the entire CI run, a shared staging DB, or an external service?
2. **Which transaction contains the operation?** Outer test transaction, server-side `@Transactional`, `REQUIRES_NEW`, reactive `TransactionalOperator`, or no transaction?
3. **Beyond which boundary must state be observed?** Before test rollback, after server commit, after event consumer ACK, or after search index refresh?

Without answering these questions, an assertion that "count equals 0" might just be reading from an uncommitted transaction, a stale cache, or before cleanup actually finished.

## 2. Scenarios Prone to Leaving Data Behind

| Scenario | What rollback cannot do | How to handle |
|---|---|---|
| HTTP request under `RANDOM_PORT` | Does not undo committed server transaction | Clean by test key via service/JDBC with its own committed transaction |
| `REQUIRES_NEW` in service/audit | Commits independent inner transaction | Clean up committed rows, or use an isolated database |
| `@Async`, scheduled tasks, background consumers | Work runs on another thread, may finish after the test | Await/cancel then clean up, with bounded timeouts |
| Reactive R2DBC/Mongo | Test-managed `ThreadLocal` does not cover Reactor Context | Clean up via subscribed Publisher, proper reactive transaction |
| Redis/cache | Cache commands do not follow JPA transactions | Delete keys by run ID; never `FLUSHALL` on a shared server |
| Kafka/RabbitMQ | Messages, offsets, queues have their own lifecycles | Test-specific topic/queue/consumer-group, fakes, controlled drain/purge |
| S3/object storage/filesystem | Uploads and file writes sit outside DB transactions | Test-specific prefix/temp directory; delete in `finally` |
| Email, SMS, payment providers | Effects may be irreversible by DB rollback | Sandbox/fakes, controlled void/refund/compensation and idempotency |
| `@TransactionalEventListener(AFTER_COMMIT)` | Event runs after transaction commits | Track outbox, await consumer, clean up generated state too |
| Sequence/identity allocators | Many DBs do not roll back allocated IDs | Do not assert contiguous IDs; use test-owned business keys |
| Multiple datasources/stores | One transaction manager does not manage all stores | Clean up each store or coordinate with verifiable checks |

Neither `@DirtiesContext` nor creating a fresh `ApplicationContext` **automatically deletes** committed rows in an external DB, remote Redis, Kafka topic, or object storage. It only affects the Spring context lifecycle and in-context bean state.

## 3. Decision Matrix for Choosing a Cleanup Strategy

| Condition | Preferred approach | Notes |
|---|---|---|
| All writes share test-managed JPA/JDBC transaction | Default rollback | Flush when proving SQL/constraints; does not cover external state |
| HTTP test creates data with an owned key | `@AfterEach` + independent cleanup service tx | Use `REQUIRES_NEW` and verify after commit |
| Static SQL fixtures with known keys | `@Sql(AFTER_TEST_METHOD, transactionMode=ISOLATED)` | SQL targets right datasource/manager without deleting other tests' data |
| Data across multiple tables with FKs | Delete child before parent, or designed cascades | Never disable FKs just to keep tests green |
| Test needs to reset entire tables/schemas | **Dedicated** schema/DB/container then `TRUNCATE`/recreate | Never run destructive DDL on shared resources |
| Data in Redis, object storage | Dedicated prefix/namespace + delete by ID | TTL is only a safety net, not a substitute for immediate cleanup |
| External system with irreversible effects | Fake/sandbox, controlled compensation | Compensation is not ACID rollback |
| Parallel/concurrent tests | Run ID/schema/topic separated per worker | Avoid global `DELETE WHERE prefix LIKE 'it-%'` |
| HTTP timeout, uncertain commit | Idempotency key + query final state + bounded retry | Do not assume error response = nothing written |

Good cleanup has **scope**, **idempotency**, **verification**, **failure reporting**, and **ownership**. You can combine strategies: separate DB transaction + resetting fakes in `finally` + TTL fallback for test resources abandoned on process crash.

## 4. Designing Test Keys: Never Delete Everything

For example, each test generates a key:

```java
String testKey = "it-" + UUID.randomUUID();
```

Snippet for JUnit tests requiring `java.util.UUID`. Write `testKey` into orders, outboxes, cache keys, filenames, or message headers so cleanup targets strictly the resources created by that test. In parallel CI, add a run ID or tenant ID for extra isolation.

**Never use** `DELETE FROM orders`, `Redis FLUSHALL`, or wipe an entire Elasticsearch index when the resource is shared. If you need a full reset, first provision a dedicated database/schema/container owned by the test. A test might create two orders, and cleanup must delete **only those two orders**.

Use clear namespaces in logs and when investigating leftover test debris:

```text
it-run-7d21/test-593d/order-01
it-run-7d21/test-593d/outbox-01
it-run-7d21/test-593d/cache:order-01
```

This is an ID format example, not real content. Never place passwords, real emails, or PII inside test keys.

## 5. Runnable Java 17 Example: Server-Side DB Transaction and Out-of-DB Side Effects

Suppose `POST /api/demo-orders` creates an order:

- The service calls `repository.saveAndFlush` inside `@Transactional`.
- The service calls fake `PaymentCaptureSimulator.capture(testKey)` outside the DB transaction.
- If `failAfterCapture` is set, the service throws an unchecked exception: DB **rolls back**, yet the fake **still retains the capture**.
- Without error, the DB commits and HTTP returns `201 Created`.
- The test calls HTTP over a `RANDOM_PORT` server, **without test-managed `@Transactional`**.
- `@AfterEach` deletes the DB record by `testKey` through a public `REQUIRES_NEW` service, clears the fake in `finally`, and asserts the data is gone.

This example uses an **in-JVM fake side effect outside the JPA transaction**, reproducing the problem safely. It does not simulate a real payment gateway; for production payments use sandboxes/refund APIs and never expose `failAfterCapture` on a public endpoint.

### 5.1. Directory Tree

```text
cleanup-transaction-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/cleanup/
    │   ├── CleanupDemoApplication.java
    │   ├── DemoOrder.java
    │   ├── DemoOrderRepository.java
    │   ├── PaymentCaptureSimulator.java
    │   ├── OrderCreationService.java
    │   ├── OrderCleanupService.java
    │   └── DemoOrderController.java
    └── test/java/com/example/cleanup/
        └── CleanupAcrossTransactionsTest.java
```

### 5.2. Maven `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>cleanup-transaction-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The POM uses Spring MVC embedded server, Spring Data JPA, H2, and JUnit Jupiter. `spring-boot-starter-test` on Boot 3.5 includes `TestRestTemplate` and AssertJ. No WebFlux/reactive HTTP client is needed for this example; if the real app uses WebFlux/R2DBC, transaction/lifecycle semantics differ as covered later.

### 5.3. `CleanupDemoApplication.java`

```java
package com.example.cleanup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CleanupDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CleanupDemoApplication.class, args);
    }
}
```

File located at **`src/main/java/com/example/cleanup/CleanupDemoApplication.java`**. Spring scans beans in the same package; the test belongs to this package as well.

### 5.4. Entity `DemoOrder`

File **`src/main/java/com/example/cleanup/DemoOrder.java`**:

```java
package com.example.cleanup;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
        name = "demo_orders",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_demo_orders_test_key",
                columnNames = "test_key"))
public class DemoOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
            name = "test_key",
            nullable = false,
            updatable = false,
            length = 80)
    private String testKey;

    @Column(name = "sku", nullable = false, length = 80)
    private String sku;

    protected DemoOrder() {
    }

    public DemoOrder(String testKey, String sku) {
        this.testKey = testKey;
        this.sku = sku;
    }

    public Long getId() {
        return id;
    }

    public String getTestKey() {
        return testKey;
    }

    public String getSku() {
        return sku;
    }
}
```

A unique `test_key` identifies which test owns a row. `GenerationType.IDENTITY` can cause Hibernate to INSERT early to acquire the ID, yet **an executed INSERT does not mean commit**. An exception at the end of the transaction can still roll it back.

### 5.5. Repository

File **`src/main/java/com/example/cleanup/DemoOrderRepository.java`**:

```java
package com.example.cleanup;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DemoOrderRepository
        extends JpaRepository<DemoOrder, Long> {

    Optional<DemoOrder> findByTestKey(String testKey);
}
```

The repository exposes `saveAndFlush`, `findByTestKey`, `delete`, and `flush`. Cleanup uses `findByTestKey` rather than deleting the whole table.

### 5.6. Fake Payment Side Effect

File **`src/main/java/com/example/cleanup/PaymentCaptureSimulator.java`**:

```java
package com.example.cleanup;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class PaymentCaptureSimulator {

    private final Set<String> captures =
            ConcurrentHashMap.newKeySet();

    public void capture(String testKey) {
        captures.add(testKey);
    }

    public boolean hasCapture(String testKey) {
        return captures.contains(testKey);
    }

    public void forget(String testKey) {
        captures.remove(testKey);
    }
}
```

`ConcurrentHashMap.newKeySet()` is safe across the test thread and server thread. Even though `capture` is called inside a `@Transactional` service, this state is **not** part of the H2 transaction, so JPA rollback cannot clean it. In production you cannot call `forget` to cancel a real charge; you must use sandboxes and proper refund/void/compensating APIs.

### 5.7. Service Saving to DB and Creating Side Effects

File **`src/main/java/com/example/cleanup/OrderCreationService.java`**:

```java
package com.example.cleanup;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCreationService {

    private final DemoOrderRepository repository;
    private final PaymentCaptureSimulator payments;

    public OrderCreationService(
            DemoOrderRepository repository,
            PaymentCaptureSimulator payments) {
        this.repository = repository;
        this.payments = payments;
    }

    @Transactional
    public DemoOrder create(
            String testKey, String sku, boolean failAfterCapture) {

        DemoOrder saved = repository.saveAndFlush(
                new DemoOrder(testKey, sku));

        payments.capture(testKey);

        if (failAfterCapture) {
            throw new IllegalStateException(
                    "simulated failure after capture");
        }
        return saved;
    }
}
```

The public method `create` is called by the controller through a Spring bean proxy. When `failAfterCapture` is `true`, the unchecked exception rolls back the DB transaction while the fake keeps the capture; when `false`, the DB transaction commits on normal completion. Never treat `saveAndFlush` as commit; it only syncs SQL inside the current transaction.

### 5.8. Cleanup Service with Its Own Transaction

File **`src/main/java/com/example/cleanup/OrderCleanupService.java`**:

```java
package com.example.cleanup;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCleanupService {

    private final DemoOrderRepository repository;

    public OrderCleanupService(DemoOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void removePersistedOrder(String testKey) {
        repository.findByTestKey(testKey)
                .ifPresent(repository::delete);
        repository.flush();
    }
}
```

`removePersistedOrder` is a public bean method invoked by tests via the Spring proxy; `REQUIRES_NEW` starts a separate transaction and **commits the `DELETE` on normal return**. `findByTestKey(...).ifPresent(delete)` ensures **idempotency** when the row does not exist, while `flush` surfaces any FK/SQL errors early before the method ends. This cleanup transaction **does not** touch fake payments, so the test calls `payments.forget` separately in `finally`.

If a test holds an outer transaction with a lock on the same row, `REQUIRES_NEW` can block or deadlock. That is why the example omits `@Transactional` on the test class; when applying elsewhere, account for the specific transaction/connection pool setup.

### 5.9. HTTP Controller

File **`src/main/java/com/example/cleanup/DemoOrderController.java`**:

```java
package com.example.cleanup;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo-orders")
public class DemoOrderController {

    private final OrderCreationService creation;

    public DemoOrderController(OrderCreationService creation) {
        this.creation = creation;
    }

    public record CreateRequest(
            String testKey, String sku, boolean failAfterCapture) {
    }

    public record CreatedResponse(Long id, String testKey, String sku) {
    }

    @PostMapping
    public ResponseEntity<CreatedResponse> create(
            @RequestBody CreateRequest request) {

        DemoOrder saved = creation.create(
                request.testKey(),
                request.sku(),
                request.failAfterCapture());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new CreatedResponse(
                        saved.getId(),
                        saved.getTestKey(),
                        saved.getSku()));
    }
}
```

Valid calls return HTTP **201 Created**; when the service throws without a custom error handler, the server returns HTTP **5xx**. The `failAfterCapture` flag is a failure-path testing toggle **for this lesson only**; never expose such a parameter in a real public API. The lesson omits validation/authentication to keep focus on transactions.

### 5.10. Test Running Against a Real HTTP Server

File **`src/test/java/com/example/cleanup/CleanupAcrossTransactionsTest.java`**:

```java
package com.example.cleanup;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.jpa.hibernate.ddl-auto=create-drop",
                "spring.datasource.url=jdbc:h2:mem:cleanup_demo;DB_CLOSE_DELAY=-1"
        })
class CleanupAcrossTransactionsTest {

    @Autowired
    private TestRestTemplate http;

    @Autowired
    private DemoOrderRepository repository;

    @Autowired
    private OrderCleanupService cleanup;

    @Autowired
    private PaymentCaptureSimulator payments;

    private String testKey;

    @BeforeEach
    void createUniqueKey() {
        testKey = "it-" + UUID.randomUUID();
    }

    @AfterEach
    void alwaysCleanupAndVerify() {
        if (testKey == null) {
            return;
        }
        try {
            cleanup.removePersistedOrder(testKey);
        } finally {
            payments.forget(testKey);
        }

        assertThat(repository.findByTestKey(testKey)).isEmpty();
        assertThat(payments.hasCapture(testKey)).isFalse();
    }

    private ResponseEntity<String> post(
            String key, boolean failAfterCapture) {
        var request = new DemoOrderController.CreateRequest(
                key, "BOOK-9", failAfterCapture);
        return http.postForEntity(
                "/api/demo-orders", request, String.class);
    }

    @Test
    void httpCommitProducesServerRowAndExternalEffect() {
        var response = post(testKey, false);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody()).contains(testKey);
        assertThat(repository.findByTestKey(testKey)).isPresent();
        assertThat(payments.hasCapture(testKey)).isTrue();
    }

    @Test
    void serverRollbackDoesNotUndoExternalEffect() {
        var response = post(testKey, true);

        assertThat(response.getStatusCode().is5xxServerError())
                .isTrue();
        assertThat(repository.findByTestKey(testKey)).isEmpty();
        assertThat(payments.hasCapture(testKey)).isTrue();
    }

    @Test
    void cleanupIsCommittedAndIdempotent() {
        assertThat(post(testKey, false).getStatusCode())
                .isEqualTo(HttpStatus.CREATED);

        cleanup.removePersistedOrder(testKey);
        payments.forget(testKey);

        cleanup.removePersistedOrder(testKey);
        payments.forget(testKey);

        assertThat(repository.findByTestKey(testKey)).isEmpty();
        assertThat(payments.hasCapture(testKey)).isFalse();
    }

    @Test
    void cleanupDoesNotDeleteUnrelatedOwnedKey() {
        String anotherKey = "it-other-" + UUID.randomUUID();
        try {
            assertThat(post(testKey, false).getStatusCode())
                    .isEqualTo(HttpStatus.CREATED);
            assertThat(post(anotherKey, false).getStatusCode())
                    .isEqualTo(HttpStatus.CREATED);

            cleanup.removePersistedOrder(testKey);
            payments.forget(testKey);

            assertThat(repository.findByTestKey(testKey)).isEmpty();
            assertThat(repository.findByTestKey(anotherKey)).isPresent();
            assertThat(payments.hasCapture(anotherKey)).isTrue();
        } finally {
            try {
                cleanup.removePersistedOrder(anotherKey);
            } finally {
                payments.forget(anotherKey);
            }
        }
    }

    @Test
    void cleanupOfNonexistentResourceIsSafe() {
        cleanup.removePersistedOrder(testKey);
        payments.forget(testKey);

        assertThat(repository.findByTestKey(testKey)).isEmpty();
        assertThat(payments.hasCapture(testKey)).isFalse();
    }
}
```

The test reads the HTTP body as a **`String`** so the 5xx failure case does not depend on how the JSON error envelope deserializes. There is no `@Transactional` on the test class. `@AfterEach` cleans up DB and fake per method; `finally` ensures the fake is still cleaned even if DB cleanup throws. If DB `DELETE` fails, the exception still fails the test — no `catch(Exception ignored)`.

**Key evidence:**

| Test | Expected outcome |
|---|---|
| `httpCommitProducesServerRowAndExternalEffect` | Server returns 201, order really exists before cleanup, fake capture exists |
| `serverRollbackDoesNotUndoExternalEffect` | HTTP 5xx, DB row absent due to rollback, fake capture still exists |
| `cleanupIsCommittedAndIdempotent` | Deleting twice is safe, DB and fake are both clean |
| `cleanupDoesNotDeleteUnrelatedOwnedKey` | Cleaning key A does not delete key B; key B is also cleaned in `finally` |
| `cleanupOfNonexistentResourceIsSafe` | Cleaning a non-existent resource raises no error |

With proper files/mappings, there are **5 `@Test` methods**, each generating its own key. Zero dependence on run order. The 5xx case is a **negative test that PASSES when response and final data match**, not a JUnit failure.

### 5.11. Running Maven

Requires Java 17+, Maven, and permission to bind a random loopback HTTP port:

```bash
mvn test
```

Run individually:

```bash
mvn -Dtest=CleanupAcrossTransactionsTest test
```

If the project has the Maven Wrapper, use `./mvnw test` or `mvnw.cmd test` on Windows. When run with proper example code and dependencies, expect **Tests run: 5, Failures: 0, Errors: 0**. The server may log a stack trace for the intentional 5xx failure path; that does not fail the test.

**Scope:** the example has been checked for content and Java signatures so it can run, **not claiming Maven was executed during the writing of this article**. In a real project, run in CI and check your version's database/schema and error mappings.

## 6. Cleaning Up with @Sql When Data Committed Outside the Test Transaction

Spring TestContext supports `@Sql` to execute scripts before/after a test. Use `SqlConfig.TransactionMode.ISOLATED` when a cleanup script must run in an **independent, committed transaction** instead of accidentally sitting inside a test transaction that later rolls back.

```java
@Test
@Sql(
    scripts = "/cleanup-fixed-fixture.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
void exercisesRealHttpEndpoint() {
    // Sends request to real server, creating a committed row.
}
```

This is a **snippet** requiring JUnit, `org.springframework.test.context.jdbc.Sql`, `SqlConfig`, Spring test context, and defined fixtures. Example **`src/test/resources/cleanup-fixed-fixture.sql`**:

```sql
DELETE FROM demo_orders
WHERE test_key = 'fixture-owned-by-exactly-one-test';
```

Use a fixed key only when the test **exclusively owns** that key. Never change the statement to `DELETE FROM demo_orders WHERE test_key LIKE 'it-%'` if CI runs tests in parallel. `@Sql` manages only SQL databases; it does not delete messages, files, Redis keys, or external payments.

When multiple datasources/transaction managers exist, explicit configuration in `@SqlConfig` must point to the right resource. If a test seeds with an **`ISOLATED`** `@Sql` script that commits, test rollback will not remove that fixture; symmetric cleanup is required. For dynamic UUIDs or multiple resource types, the cleanup service in section 5 is far more flexible than static SQL scripts.

## 7. `TestTransaction` and `REQUIRES_NEW`: Checking Whose Transaction It Is

In Spring TestContext, `TestTransaction` lets you actively end/start the **test-managed transaction**:

```java
assertTrue(TestTransaction.isActive());
TestTransaction.flagForCommit();
TestTransaction.end();   // Commits test-managed transaction.
TestTransaction.start(); // Starts a new test-managed transaction.
```

Snippet only illustrating inside a `@Transactional` JUnit test, requiring static `assertTrue` and `org.springframework.test.context.transaction.TestTransaction`. It **does not** commit or roll back finished HTTP server transactions, nor manage message brokers/S3.

Likewise, a service method:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAuditEvent(AuditEvent event) {
    // Saves an audit row in an independent transaction.
}
```

This is not a complete file: `AuditEvent` is assumed. If the public method is invoked **through a Spring proxy** and commits, rolling back the outer transaction **does not delete the audit row**. Audit cleanup needs its own transaction or a test DB namespace. If the method is called via `this.writeAuditEvent(...)` inside the same bean, Spring proxy-based transactions normally **do not trigger**, so test the real transaction boundary instead of guessing from annotations.

**A JUnit pitfall:** `@BeforeEach` and `@AfterEach` run **inside the test-managed transaction** by default when the test method has `@Transactional`; a `DELETE` inside `@AfterEach` can be rolled back. Spring's `@BeforeTransaction`/`@AfterTransaction` run outside the test-managed transaction, yet you must still ensure cleanup uses an appropriate transaction manager and check committed state.

## 8. Reactive and Background Data: Never Clean Up Before Work Finishes

With Spring Data R2DBC or Reactive Mongo, repository `deleteById`/`deleteAll` methods return a `Publisher`. Merely creating the `Publisher` without subscribing **cleans nothing**:

```java
StepVerifier.create(repository.deleteById(testId))
        .verifyComplete();
```

Snippet requires `reactor.test.StepVerifier`, a reactive repository, and an existing `testId`. For cleanup inside a reactive transaction, use `TransactionalOperator` and the right `ReactiveTransactionManager`; do not assume `@Transactional` on a `void` JUnit test creates a Reactor Context wrapping every subscription. Calling `Mono.block()` on a WebFlux event-loop thread can fail as blocking; on the JUnit test thread, `StepVerifier` is usually clearer.

### Async Workers Can Re-Write Data After Cleanup

Suppose the server returns 202 Accepted and a worker keeps running after the response:

```text
test sends request -> HTTP 202
test deletes DB rows
background worker processes event -> inserts row again
next test sees unwanted row
```

Right strategy:

1. Attach `testRunId` to the payload/job.
2. Await task completion or cancel using a signal/barrier/future with a **bounded timeout** rather than guessing with `Thread.sleep`.
3. Clean DB/cache/broker data matching that exact test ID.
4. Re-read from a reliable boundary and confirm no residual state remains.
5. For eventually consistent stores, use bounded polling up to a deadline instead of baseless instant assertions.
6. Tear down namespaces/containers/test clients only once workers can no longer write back.

Kafka/RabbitMQ: ACKing a message does not mean the broker/queue can roll back with a DB transaction. Elasticsearch/OpenSearch: a search not showing a document might only mean it hasn't refreshed yet, not that it was deleted. S3: delete requests can involve versioned objects; understand bucket versioning and cleanup permissions. For every system, use the right resource API and verification state.

## 9. Cleaning Non-SQL Resources by Namespace

| Resource | Test ownership key | Cleanup | Warning |
|---|---|---|---|
| **MongoDB** | `testRunId` in document | `deleteMany` by owner field | Do not drop shared databases; multi-document transactions depend on topology |
| **Redis** | `it:{runId}:...` | Delete/`UNLINK` exact keys by namespace | Never `FLUSHALL` on shared Redis; TTL does not replace immediate cleanup |
| **Elasticsearch** | Dedicated ID/index or `testRunId` | Delete by ID / by query in scope, verify completion/refresh | Bulk has partial failures; search visibility lags write ACK |
| **Object storage S3** | Dedicated object-key prefix | List/delete under prefix, verify final state | Versioning, delete markers, and external permissions |
| **Kafka/RabbitMQ** | Test topic, queue, consumer group | Create/clean test-specific resources or fake broker | Never purge shared topics/queues; messages can be retried |
| **Email/SMS/payment** | Sandbox request ID, idempotency key | Reset sandbox, void/refund/cancel per contract | Compensation is not ACID rollback; never use real credentials |
| **Local filesystem** | `@TempDir` or test temp path | JUnit-managed temp cleanup, `finally` | Never delete shared directories |
| **HTTP fake/WireMock** | Per-test stub/scenario | Reset exact stub/scenario/test server | Resetting the whole server can break parallel tests |

**TTL is a safety net**, useful when a process crashes before `@AfterEach`. A test running right afterward could still encounter leftover data before TTL expires, so explicit cleanup is needed—and in shared environments, a periodic janitor should delete **only resources with clear ownership that have expired**.

## 10. Cleaning Tables with Many Foreign Keys, Sequences, and Schemas

When a test creates orders and outbox rows with FKs:

```sql
DELETE FROM order_items WHERE test_key = ?;
DELETE FROM outbox_events WHERE test_key = ?;
DELETE FROM orders WHERE test_key = ?;
```

This SQL is **illustrative**, not the H2 demo's schema (the demo only has `demo_orders`). When child rows lack `test_key`, delete by parent ID or join/subquery before deleting the parent. Use bound parameters, never string-concatenated inputs in SQL. Never disable FKs globally just to "get cleanup done"; doing so lets tests mask integrity bugs.

When a database/schema is **dedicated solely to tests**, `TRUNCATE`, dropping/recreating the schema, or Testcontainers teardown can be cleaner than deleting hundreds of tables. Note that in some databases like MySQL, DDL/`TRUNCATE` implicitly commits and cannot roll back; never run them on shared DBs. After resetting a schema, run production-like migrations/seeds rather than relying solely on Hibernate auto-DDL when tests must validate migrations.

Sequence/identity IDs are typically non-contiguous across rollbacks; **never** assert that a new order receives ID = 1 or that a new test gets the ID just rolled back. Assert business keys and test ownership instead of resetting sequences to force tests green.

## 11. Cleanup Must Be Idempotent, Verified, and Loud on Failure

Technical checklist for reliable cleanup:

- **Delete only test-owned data** by explicit ID/prefix/tenant/schema.
- **Safe to call repeatedly** when resources are already gone; avoid unnecessary errors.
- **Run even on assertion failures** via JUnit lifecycle or `try`/`finally`.
- **Fail loudly** if cleanup fails; never `catch (Exception ignored) {}`.
- When multiple independent cleanups can fail, attempt all of them and **collect/suppress errors** instead of losing subsequent cleanups or hiding the first failure.
- Verify **the resource existed before cleanup** where appropriate, avoiding false positives when setup never ran.
- Verify **the resource is gone after cleanup** from a reliable transaction/connection or API, not merely an entity cache.
- Stop/await **in-flight workers** before cleanup; use timeouts and bounded retries for eventual consistency.
- Log diagnostic run ID, resource ID, cleaned count, and failure cause without logging PII/secrets.
- Plan recovery for CI crashes (TTL, strictly test-owned janitors, container teardown).

In the `@AfterEach` example, if `cleanup.removePersistedOrder(testKey)` throws an exception, `payments.forget(testKey)` still runs because of `finally`. The DB cleanup exception still propagates out and JUnit fails the test. After cleanup succeeds, the test verifies both the repository and fake are clean. That is much stronger evidence than calling `delete` and assuming everything is clean.

## 12. Cleanup Test Cases Real Projects Should Have

| Case | Setup | Assertion needed |
|---|---|---|
| Successful server request | Create row via real HTTP | Row exists before cleanup, absent after cleanup |
| Service throws after DB flush | DB transaction rolls back, non-DB side effect happened | DB absent, external effect exists, then clean external effect |
| Test assertion fails | Create resource then intentionally fail an assertion | `@AfterEach`/extension still invoked; CI reports test failure |
| Cleanup runs again | Resource already gone | No exception, state unchanged |
| Two parallel tests | Two different test IDs | Deleting A does not affect B |
| SQL FKs | Create parent/child | Clean child before parent, no orphans left |
| Async eventual write | Worker finishes after response | Await/cancel, clean up afterward, does not reappear |
| External API timeout | Uncertain commit/ACK outcome | Query state by idempotency key then clean up |
| Reactive repository | `Mono<Void>` delete | Subscribed and verified completion |
| Non-existent data | No row/cache key | Cleanup is idempotent and does not fail |
| DB cleanup throws | DB connection failure or constraint error | Test fails with diagnostics; other resources still attempted |
| Crash before `@AfterEach` | CI process terminates abruptly | Test namespace/container/TTL/janitor cleans up afterward |

**Never use a single in-process test with fakes to claim you verified database failover or real payment compensation.** Those goals require a dedicated test environment with controlled fault injection and real sandbox APIs.

## 13. Common Mistakes

| Mistake | Harm | Fix |
|---|---|---|
| `@Transactional` on `RANDOM_PORT` test expecting server writes to roll back | Leftover DB rows | Clean committed state by test ID |
| `DELETE` in `@AfterEach` rolled back by outer test transaction | Cleanup has no effect | `REQUIRES_NEW` or `@Sql(ISOLATED)`; avoid outer tx when unnecessary |
| Using `@DirtiesContext` instead of DB cleanup | DB/broker stays dirty | Real cleanup or isolated DB/container |
| Calling reactive delete without subscribing | Deletes nothing | `StepVerifier.verifyComplete` |
| Wiping whole shared Redis/SQL tables | Breaks other tests | Independent namespace/`testKey` |
| Using TTL as the sole cleanup | Next test sees stale data | Explicit cleanup + TTL backup |
| Cleaning DB before async worker finishes | Worker re-inserts after cleanup | Await/cancel then clean up |
| Deleting parent before child | FK violation | Delete child first or use proper cleanup transaction |
| Assuming `REQUIRES_NEW` rolls back with outer | Audit row still commits | Independent cleanup by owner key |
| Calling `deleteAll()` on a mock repository | Does not prove DB state is clean | Integration test against real DB |
| Not checking data existed before cleanup | False positive: resource was never created | Verify creation then verify cleanup |
| Swallowing cleanup exceptions | CI stays green despite leftovers | Fail loudly and log diagnostics |
| Resetting global fake/cache in parallel suite | Breaks other tests | Test-scoped fakes or namespaces |
| Truncating/DDL inside transaction expecting rollback | Database performs implicit commit | Run destructive resets only on isolated DBs |
| Treating network timeout as write failure | Retries create duplicates | Idempotency keys and state queries |
| Assuming reused container is a fresh DB for every test | Data bleeds across test classes | Per-class schemas/test IDs, lifecycle-aware cleanup |

## 14. Pre-Merge Checklist for Integration Tests

- [ ] Mapped transaction boundaries of the test thread, HTTP server, reactive pipeline, `REQUIRES_NEW` services, and external resources.
- [ ] Not assuming test rollback applies to server-side transactions.
- [ ] Every fixture/row/message/object created by tests carries a test-owned key.
- [ ] Cleanup covers each resource type outside the DB transaction.
- [ ] `@AfterEach` is invoked properly and cleanup **does not sit inside a transaction about to roll back**.
- [ ] If using `@Sql`, transaction mode/datasource/phase are configured accurately.
- [ ] If using reactive cleanup, the `Publisher` is subscribed and completion verified.
- [ ] If async consumers exist, work is awaited/cancelled before cleanup.
- [ ] Cleanup is idempotent; calling twice does not delete out-of-scope data.
- [ ] Resource exists before cleanup and is verified absent after cleanup.
- [ ] FK-linked data is deleted in a safe order.
- [ ] Parallel runs never share fixed keys or wipe shared resources.
- [ ] External payments/email use fakes or sandboxes, never real side effects.
- [ ] Not using `@DirtiesContext` as a substitute for cleaning external data.
- [ ] Cleanup failures fail CI builds loudly; no silent ignoring.
- [ ] Using Testcontainers/dedicated schemas when destructive resets or production-like DBs are needed.
- [ ] Scoped TTL/janitor with **least privilege** handles leftovers after process crashes.
- [ ] Re-ran tests multiple times or randomized order to detect leakage.
- [ ] Accurately described what tests prove; never conflated fakes with real integration.

**Conclusion:** Rollback is a **scoped** transaction management mechanism, not a "restore the entire system after every test" button. When real HTTP, nested/independent transactions, async work, and external systems are involved, you need **test-owned data + per-resource cleanup at the right boundary + clean-state verification**. Prefer isolated environments and safe cleanup design over indiscriminately wiping data just to keep tests temporarily green.

### Official References

- [Spring Boot 3.5 — Testing Spring Boot Applications and RANDOM_PORT transaction boundaries](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework — Test-managed Transactions, @BeforeTransaction/@AfterTransaction](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Framework — @Sql and transactionMode ISOLATED](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html)
- [Spring Framework — Transaction propagation REQUIRES_NEW](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Reactive transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
