# Server-thread transactions differ from test-method transactions in @SpringBootTest

## 1. Understanding the problem properly: `@Transactional` on a test does not wrap real HTTP requests

A very common mistake when writing Spring Boot integration tests is putting `@Transactional` on a test method, calling an API over HTTP, and assuming **all data changes made by the API will roll back when the test ends**. This is usually **false** when using `@SpringBootTest(webEnvironment = RANDOM_PORT)` or `DEFINED_PORT`.

Reason: the **test-managed transaction** is started by Spring TestContext and bound to **the thread executing the test method**. Meanwhile, a real HTTP request is processed by the embedded server on a **different request-handling thread** (or a different execution context in reactive models). A thread-bound test transaction context does not automatically propagate across an HTTP socket to the server.

Example of two independently operating threads:

```text
TEST THREAD / JUnit                      HTTP SERVER THREAD / application

@Transactional @Test
  |
  |-- [test transaction T1 starts]
  |
  |-- HTTP POST /visits  ------------->  Controller receives HTTP request
  |                                        |
  |                                        v
  |                                      Service @Transactional
  |                                        |
  |                                      [transaction T2 starts]
  |                                        |
  |                                      Repository.save(...)
  |                                        |
  |                                      [T2 commits if successful]
  |                                        |
  |<------------- HTTP 201 -------------  Response
  |
  |-- [T1 rolls back via test framework]
  |
  v
The row committed by T2
DOES NOT disappear because T1 rolled back
```

The diagram depicts a typical setup: a real service invoked through Spring's transaction proxy, default `REQUIRED` propagation, and an appropriate transaction manager and database. **Not every HTTP request automatically has a transaction**; transaction T2 only exists if server-side code/configuration actually starts one.

**Core rule:** test rollback only guarantees rolling back operations **that joined test-managed transaction T1**. It does not undo the server's independent transaction T2 merely because T1 and T2 share a JVM, a test class, or a database.

## 2. How do test-managed transactions and application-managed transactions differ?

Spring TestContext provides `TransactionalTestExecutionListener`, collaborating with `PlatformTransactionManager` to open a transaction for `@Transactional` test methods/classes. With standard default configuration, the test transaction **rolls back after each test**.

On the application side, `@Transactional` on a Spring bean is handled by a transaction interceptor/proxy or matching transaction infrastructure. When an HTTP request is processed on a server thread, the interceptor starts or joins a transaction **within that request's server-side context**, not borrowing the test thread's transaction.

| Characteristic | Test-managed transaction | HTTP server-side transaction |
|---|---|---|
| Who starts it? | Spring TestContext when running a `@Transactional` test | Application transaction infrastructure when server invokes a transactional bean |
| Thread/context | Test execution thread (thread-bound) | Server request-processing thread or context |
| Scope | Code participating in the transaction bound to the test thread | Server code managed by the transaction interceptor |
| Default completion | TestContext rolls back after the test, unless policy is changed | Usually commits when the transactional call succeeds; rollback depends on exception/rules |
| `@Rollback`/`@Commit` on test | Controls the test-managed transaction | **Does not directly control** independent transactions on the server |
| Real HTTP POST from test | A client call; does not pull the server into T1 | Handled on the server, creating its own transaction if configured |
| Synchronous MockMvc on test thread | May join T1 under appropriate conditions | Normally opens no real HTTP server thread; see section 7 |

An important point: `@Transactional` is a **declaration of transactional intent**, not proof that a transaction was applied to a given call. Proxy boundaries, propagation, transaction managers, self-invocation via `this`, and thread switches all affect the outcome.

## 3. `@SpringBootTest` with `RANDOM_PORT`, `DEFINED_PORT`, and `MOCK`

`@SpringBootTest` lets you pick the web environment. For transactions, the difference in the **request path** is decisive.

| Configuration | Typical call path | Real HTTP server? | Does test transaction automatically cover request? |
|---|---|---|---|
| `RANDOM_PORT` | `TestRestTemplate`/HTTP client → socket → embedded server | Yes | **No**; server executes independently |
| `DEFINED_PORT` | HTTP client → fixed/configured port → server | Yes | **No** |
| `MOCK` + `@AutoConfigureMockMvc` | `MockMvc.perform(...)` → Servlet MVC in-process, usually same test thread | Opens no real HTTP listener | **May** join T1 when synchronous on the same thread with compatible propagation |
| `NONE` | Creates no web environment | No | No real HTTP requests in this config |

With `MOCK`, `@SpringBootTest` by itself **does not mean a `MockMvc` bean is ready**: in Spring Boot MVC tests, `@AutoConfigureMockMvc` is normally required to configure and inject `MockMvc`.

**Avoid absolute claims** that every `MockMvc.perform` shares the transaction: async dispatch, `@Async`, application-spawned threads, `REQUIRES_NEW`, out-of-transaction callbacks, or calls to another process can fall outside T1. Conversely, when using real HTTP, you can never use `@Transactional` on a test method to automatically roll back server-committed changes.

## 4. Complete Java 17+ / Spring Boot 3.x / JPA / H2 example

We build a tiny application with a `POST /visits?label=...` endpoint that writes a record to the database, followed by **two tests**:

1. `RANDOM_PORT` + `TestRestTemplate`: roll back the test's transaction and verify the row committed by the HTTP server **still exists**.
2. `MOCK` + synchronous `MockMvc`: same service and same `REQUIRED` propagation, yet the request executes on the test thread; rolling back T1 makes the row **vanish**.

This is a hands-on illustration, not a recommendation to substitute H2 for every production test database. H2 is used to demonstrate transactions within the same JVM. When a project depends on specific SQL dialects, locking, or constraints, use an appropriate database (such as Testcontainers with PostgreSQL).

### 4.1. Required dependencies

In a Spring Boot 3.x project managing dependency versions and targeting Java 17+, add equivalent libraries:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **Gradle configuration snippet**, assuming the build script already configures the Spring Boot/Java plugins and repositories. With Maven, use equivalent dependencies and a matching JUnit Jupiter plugin. The example uses `jakarta.persistence` (Spring Boot 3.x), not `javax.persistence` from older projects. For Spring Boot 4 or different test module layouts, verify starter coordinates and imports for your version.

Suggested source layout:

```text
src/main/java/com/example/txhttp/
  TxHttpDemoApplication.java
  Visit.java
  VisitRepository.java
  VisitService.java
  VisitController.java

src/test/java/com/example/txhttp/
  RealHttpTransactionTest.java
  MockMvcTransactionTest.java
```

### 4.2. Application bootstrap

File `src/main/java/com/example/txhttp/TxHttpDemoApplication.java`:

```java
package com.example.txhttp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxHttpDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxHttpDemoApplication.class, args);
    }
}
```

Place the application class in parent package `com.example.txhttp` so Spring Boot discovers the example's controller, service, JPA entity, and repository. No manual server startup is needed in tests: `@SpringBootTest(RANDOM_PORT)` starts the embedded server using Boot's mechanism.

### 4.3. Real entity and repository

File `src/main/java/com/example/txhttp/Visit.java`:

```java
package com.example.txhttp;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.util.Objects;

@Entity
@Table(name = "visits")
public class Visit {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String label;

    protected Visit() {
    }

    public Visit(String label) {
        this.label = Objects.requireNonNull(label, "label");
    }

    public Long getId() {
        return id;
    }

    public String getLabel() {
        return label;
    }
}
```

File `src/main/java/com/example/txhttp/VisitRepository.java`:

```java
package com.example.txhttp;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface VisitRepository extends JpaRepository<Visit, Long> {
    long countByLabel(String label);
    Optional<Visit> findByLabel(String label);
}
```

The repository here is a **real Spring Data JPA repository**, not a Mockito mock. This is essential: to observe rollback differences, tests must write real data to a database shared across connections. `label` is unique so each test case can identify and clean up its own record.

### 4.4. Service creating an application-side transaction

File `src/main/java/com/example/txhttp/VisitService.java`:

```java
package com.example.txhttp;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class VisitService {

    private final VisitRepository repository;

    public VisitService(VisitRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long record(String label) {
        Visit saved = repository.save(new Visit(label));
        return saved.getId();
    }
}
```

`@Transactional` is placed on a `public` method of a Spring-managed service. The external controller invokes it through the Spring-injected service bean, so in standard Spring Boot/JPA setups, the transaction interceptor starts or joins a transaction.

With default `REQUIRED` propagation:
- **On the HTTP server thread**, no T1 is bound from the test, so the service typically opens transaction T2 and commits when `record` finishes successfully.
- **In synchronous MockMvc on the same test thread**, test-managed T1 is active; the service call with `REQUIRED` typically **joins T1** rather than committing independently.

An `INSERT` statement may be flushed to the database before the transaction commits (for instance, because `GenerationType.IDENTITY` needs an ID). **An issued INSERT does not mean committed**. That is why we must verify state **after rollback**, not merely observe an ID or `save` return value.

### 4.5. HTTP controller

File `src/main/java/com/example/txhttp/VisitController.java`:

```java
package com.example.txhttp;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/visits")
public class VisitController {

    private final VisitService service;

    public VisitController(VisitService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<Long> create(@RequestParam String label) {
        Long id = service.record(label);
        return ResponseEntity.status(HttpStatus.CREATED).body(id);
    }
}
```

HTTP response `201 Created` indicates the controller succeeded per the logic above. In this synchronous example, the service transaction has already finished before the controller sends the response. In applications with queues, async background workers, or transactional events, a 201 response **does not necessarily** prove all background work has committed.

## 5. Test 1: `RANDOM_PORT` and real HTTP — server commit survives test rollback

File `src/test/java/com/example/txhttp/RealHttpTransactionTest.java`:

```java
package com.example.txhttp;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.datasource.url=jdbc:h2:mem:tx_http_real;DB_CLOSE_DELAY=-1",
                "spring.jpa.hibernate.ddl-auto=create-drop",
                "spring.jpa.open-in-view=false"
        })
class RealHttpTransactionTest {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    VisitRepository visits;

    @Test
    @Transactional
    void serverWriteSurvivesRollbackOfTheTestTransaction() {
        String label = "real-" + UUID.randomUUID();

        try {
            assertTrue(TestTransaction.isActive());

            ResponseEntity<Long> response = rest.postForEntity(
                    "/visits?label={label}",
                    null,
                    Long.class,
                    label);

            assertEquals(HttpStatus.CREATED, response.getStatusCode());
            assertNotNull(response.getBody());

            // End test-managed T1 with rollback RIGHT NOW.
            TestTransaction.flagForRollback();
            TestTransaction.end();
            assertFalse(TestTransaction.isActive());

            // Transaction T2 created by the HTTP server committed independently.
            assertEquals(1L, visits.countByLabel(label));
        } finally {
            // Even if an earlier assertion fails, do not leave T1 active during cleanup.
            if (TestTransaction.isActive()) {
                TestTransaction.flagForRollback();
                TestTransaction.end();
            }

            // Clean up this test case's own record outside T1.
            visits.findByLabel(label).ifPresent(visits::delete);
        }
    }
}
```

### 5.1. Why does this test prove the lesson's point?

- `@SpringBootTest(RANDOM_PORT)` starts a real HTTP server on an allocated port. `TestRestTemplate` is configured with the local server's base URL, so relative path `/visits` sends an HTTP request to the server.
- `@Transactional` on the test causes Spring TestContext to start transaction **T1** for the test thread.
- `rest.postForEntity(...)` travels over loopback to an HTTP worker thread. Even in the same JVM, the server does not automatically see thread-bound T1.
- The controller invokes `VisitService.record`; the service's transaction proxy runs transaction **T2** on the server side and commits on success.
- `TestTransaction.flagForRollback(); TestTransaction.end();` **rolls back T1 before the test finishes**, letting the test verify post-rollback state inside the same method.
- `visits.countByLabel(label) == 1` **after T1 rolls back** proves the row created by the HTTP request was not rolled back with T1.
- The `finally` block deletes the row via the real repository outside the test transaction. Relying on T1 rollback without cleanup leaves HTTP-committed data behind to affect subsequent tests.

**Do not equate** `TestTransaction.end()` with the server's `TransactionTemplate`: it only ends the active test-managed transaction on the test thread. Here the test explicitly invokes `flagForRollback` instead of relying on an automatic post-method callback.

If a test fails before the request completes, the `finally` block still attempts to remove any matching record; however, if the app performs async work after the response or encounters a network outage, the system may need dedicated cleanup/retry strategies. This example uses a synchronous JPA service to keep results deterministic.

### 5.2. Conditions ensuring valid demonstration

- JDBC URL `jdbc:h2:mem:tx_http_real;DB_CLOSE_DELAY=-1` lets multiple connections in the **same JVM** access one named H2 in-memory database; `DB_CLOSE_DELAY=-1` keeps the database alive when connections temporarily close. This configuration is **strictly for test illustration**, never production.
- `spring.jpa.hibernate.ddl-auto=create-drop` creates/drops schema across the test's application context lifecycle. Never apply `create-drop` to production databases.
- `UUID.randomUUID()` generates a distinct label, preventing tests from sharing business keys.
- `VisitRepository` uses real JPA; `save` is not mocked.
- `TestRestTemplate` actually calls the HTTP endpoint, and the repository queries the DB afterward to assert post-rollback data.

Each condition is part of the proof. Replacing the repository with a Mockito mock and calling `verify(save(...))` **cannot** prove real data commit/rollback.

## 6. Test 2: Synchronous MockMvc — the call can join T1

For comparison, use the exact same controller, service, and repository, driving the request via `MockMvc` **on the same test thread**. There is no real HTTP server socket in this `MOCK` test.

File `src/test/java/com/example/txhttp/MockMvcTransactionTest.java`:

```java
package com.example.txhttp;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK,
        properties = {
                "spring.datasource.url=jdbc:h2:mem:tx_http_mock;DB_CLOSE_DELAY=-1",
                "spring.jpa.hibernate.ddl-auto=create-drop",
                "spring.jpa.open-in-view=false"
        })
@AutoConfigureMockMvc
class MockMvcTransactionTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    VisitRepository visits;

    @Test
    @Transactional
    void synchronousMockMvcWriteIsRolledBackWithTestTransaction()
            throws Exception {
        String label = "mock-" + UUID.randomUUID();

        mvc.perform(post("/visits").param("label", label))
                .andExpect(status().isCreated());

        // Same thread and REQUIRED propagation: data is visible within T1.
        assertEquals(1L, visits.countByLabel(label));

        TestTransaction.flagForRollback();
        TestTransaction.end();

        // After rolling back T1, the row from the synchronous call is gone.
        assertEquals(0L, visits.countByLabel(label));
    }
}
```

### 6.1. Why does the result differ from real HTTP?

In the standard **synchronous** `MockMvc` path:

```text
Test thread with transaction T1
    |
    +-- MockMvc.perform(...)
         |
         +-- DispatcherServlet + Controller (same thread)
             |
             +-- VisitService.record(...) via Spring proxy
                   |
                   +-- @Transactional(REQUIRED) joins T1
                         |
                         +-- Repository.save(...)
    |
    +-- TestTransaction.end() rolls back T1
         |
         +-- Uncommitted data is rolled back
```

Both tests invoke the same `VisitService`, the same `@Transactional` rules, and the same real repository. **What differs is the execution path**: synchronous `MockMvc` crosses no separate HTTP port, whereas `TestRestTemplate` with `RANDOM_PORT` does.

In practice, not every `MockMvc` execution stays inside T1. The following cases can alter that behavior:
- Controller/service offloads work to `@Async`, an executor, an async event listener, or async request dispatch.
- Service uses `REQUIRES_NEW` propagation and opens an independent transaction.
- Test uses a preemptive timeout causing code to run on another thread.
- Code sends a message or HTTP call to another service.
- Application uses a special transaction manager, reactive transaction context, or multiple datasources.

Therefore, when testing **transaction boundaries**, verify actual behavior along the concrete execution path rather than classifying solely by tool name.

### 6.2. Quick comparison

| Assertion | `RANDOM_PORT` + real HTTP | `MOCK` + synchronous MockMvc |
|---|---|---|
| Test has `@Transactional` | T1 starts on test thread | T1 starts on test thread |
| Service has `@Transactional(REQUIRED)` | Server thread usually opens T2 | Service usually joins T1 |
| Request returns 201 | May have already committed T2 | May remain uncommitted inside T1 |
| T1 rolls back | Does not affect committed T2 | Rolls back changes that joined T1 |
| Query after T1 rollback | HTTP row still exists in example | MockMvc row is gone in example |
| Cleanup needed? | **Yes**, if T2 committed data | Usually not for data strictly inside T1; still check other side effects |

## 7. Which transaction do `@Rollback`, `@Commit`, and `TestTransaction` affect?

Spring TestContext provides utilities to control the **test-managed transaction**:

- `@Transactional` on test method/class: asks Spring TestContext to start a transaction for the test when an appropriate transaction manager exists.
- `@Rollback` (default rollback) and `@Commit`: specify how the **test's transaction** should end.
- `TestTransaction.isActive()`: checks whether a test-managed transaction is currently active on the test thread.
- `TestTransaction.flagForRollback()` / `flagForCommit()`: specifies how the test transaction should terminate.
- `TestTransaction.end()`: ends the active test transaction according to the current flag.
- `TestTransaction.start()`: starts a new test-managed transaction where supported by the framework.

Example:

```java
assertTrue(TestTransaction.isActive());
TestTransaction.flagForRollback();
TestTransaction.end();
assertFalse(TestTransaction.isActive());
```

This is an **illustrative snippet inside a Spring transactional test**, not a standalone Java file; `TestTransaction` belongs to `org.springframework.test.context.transaction`.

**Mistake to avoid:** adding `@Rollback(true)` or `@Commit` onto a real HTTP test expecting it to control server transactions. They send no rollback/commit signal over HTTP. The server only knows its own transaction context.

If using `@BeforeTransaction`/`@AfterTransaction`, those lifecycle callbacks run **outside the test-managed transaction**, useful for preparing or verifying committed state after the test transaction ends. By contrast, `@BeforeEach` and `@AfterEach` normally run inside a Spring transactional test's transaction while it is active. Consequently, **deleting rows in `@AfterEach` can be rolled back with the test**, leaving rows committed by the HTTP server actually undeleted.

In section 5's example, the code explicitly calls `TestTransaction.end()` before repository cleanup, ensuring deletion executes outside T1.

## 8. Why don't same database and same JVM share a transaction?

Several misconceptions stem from the test and server starting inside a single JVM:

1. **Transaction contexts are typically thread-bound:** In Spring's imperative transaction model, resources/connections and transaction state are bound via mechanisms like `TransactionSynchronizationManager`. Another thread will not automatically share a transaction just because it shares the application context.
2. **One database can hold multiple connections:** T1 uses one connection/transaction state, T2 uses another. Commit/rollback occurs per transaction, not across the “entire JVM”.
3. **HTTP does not carry Spring's transaction manager:** Standard JSON, cookies, or headers do not transfer a database transaction T1 to a server request.
4. **Context propagation is a separate concern:** Propagating correlation IDs, MDC, trace IDs, or authentication does not propagate database transactions; do not use `TaskDecorator` to pretend two threads share one transaction.
5. **Test thread may not see server's uncommitted data and vice versa:** This depends on transaction isolation, locking, and the database. If a test creates a fixture inside an uncommitted transaction and then calls the HTTP server to read that fixture, the server may **fail to see** it — or even block on lock contention.

Design bug example:
- A `@Transactional` test calls `repository.save(new Customer(...))` to prepare data without **committing**.
- The test calls an endpoint via `TestRestTemplate` to process the newly created customer.
- The server uses another connection, queries without finding the customer, and returns 404.
- The test author blames the repository or service logic, when in fact setup data **was uncommitted and invisible to the server thread**.

The fix is creating pre-request data inside a **committed** transaction — using `@BeforeTransaction`, `TransactionTemplate` to commit explicitly, or `TestTransaction.end()` flagged for commit when appropriate. After the test, clean up in a separate transaction. Never just raise isolation or add `flush()` trying to “make data appear”: **flush does not mean commit**, so the server connection can still miss the data.

## 9. Propagation, rollback rules, and exceptions to the simple rule

Even when test and application logic share a thread, transaction propagation determines whether the call joins the active transaction:

| Service propagation | Simplified meaning | When test has T1 and calls via synchronous MockMvc |
|---|---|---|
| `REQUIRED` | Join existing transaction, or create new if none | Usually joins T1 |
| `REQUIRES_NEW` | Suspend existing transaction, start a new one | Can commit independently even if T1 rolls back |
| `SUPPORTS` | Use transaction if present, otherwise run non-transactionally | Can run inside T1 |
| `NOT_SUPPORTED` | Run outside any existing transaction | Changes not guaranteed inside T1 |
| `MANDATORY` | Require an existing transaction | May succeed under MockMvc/T1, yet fail under HTTP server if no server-side transaction exists |
| `NESTED` | Use nested transaction/savepoint when supported by manager | Not a fully independent transaction; depends on manager and database |

**With real HTTP**, even if a service specifies `REQUIRED`, it cannot join T1 from the test thread across a socket. It joins/creates a transaction based solely on the **server-side** transaction state.

**Rollback rules also matter.** In standard declarative Spring transactions, unchecked exceptions (`RuntimeException`, `Error`) trigger rollback by default; checked exceptions may not trigger rollback unless configured via `rollbackFor` or matching rules. Policies can vary by version/configuration. Never assume every HTTP 500 guarantees “all DB writes rolled back”; inspect exception paths, propagation, and final DB state.

An easy-to-miss case: a service catches an exception inside a transaction, swallows it, and returns normally. If the transaction was not marked rollback-only, the interceptor may commit; if already marked rollback-only, `UnexpectedRollbackException` may occur. Tests must verify the final data state.

## 10. Why can `@Transactional` on a test hide a service's transaction bug?

When `MockMvc` runs synchronously inside T1, a service missing `@Transactional` **can still see an active transaction** because the test supplied one. Result:
- `repository.save` succeeds in the test.
- Data rolls back at test completion.
- The author concludes the service is transactional and commits/rolls back properly in production.

That conclusion is **unproven**. A test intended to verify a **service's transaction boundary** should start with no test-managed transaction, invoke the service via the Spring proxy, and verify post-commit/rollback state using a real database or transaction instrumentation at the right boundary.

Diagnostic snippet (illustrative code inside a test with matching imports):

```java
boolean transactionActiveInCurrentThread =
        TransactionSynchronizationManager.isActualTransactionActive();
```

This statement only reflects the transaction of **the thread executing that line**. If run on the test thread, `true` does not prove the HTTP server thread shares that transaction. If run inside a service, `true` proves a transaction is active at that moment, yet **does not prove that specific method opened it** or that data ultimately committed.

Moreover, self-invocation under Spring AOP proxies bypasses advice: `this.innerTransactionalMethod()` does not pass through the proxy when called internally on the same bean. Tests cannot infer interceptor execution solely from annotations.

## 11. Proper isolation and cleanup strategies for real HTTP integration tests

When using `@SpringBootTest(RANDOM_PORT)`, assume by default that data committed by the HTTP server **requires active cleanup**. Solid strategies include:

### 11.1. Generate unique business keys and clean up outside T1

Section 5's example uses `"real-" + UUID.randomUUID()` to identify the test's exact record, then calls `findByLabel(...).ifPresent(delete)` after ending T1. This is straightforward and avoids deleting data belonging to other tests.

Prefer cleanup in `finally` or callbacks guaranteed to run after the test transaction, verifying it uses a connection/transaction that actually commits. Cleanup itself can fail; when it does, test results should surface the environment error or leaked state.

### 11.2. Prepare committed fixtures before the request

When an endpoint must read pre-existing data:
- Use setup outside any test-managed transaction, letting repository saves commit per actual configuration.
- Or use `TransactionTemplate` with the proper transaction manager to create and commit fixtures before calling HTTP.
- Or manage `TestTransaction` carefully: end the transaction with commit before sending HTTP; never call `TestTransaction.end()` when inactive.

After the request completes, clean up committed fixtures in a separate transaction. Never treat `saveAndFlush()` as “committed” while test T1 remains active.

### 11.3. `@Sql` and cleanup scripts

`@Sql` can create/reset data. However, in a transactional test, scripts running under default transaction mode may join T1 and roll back with T1, **failing to delete server-committed data**. To clean up outside T1, examine `@SqlConfig(transactionMode = ISOLATED)` and execution phase, or use explicit post-transaction cleanup. Only run `TRUNCATE`/full-table deletes when the test environment is sufficiently isolated and no parallel test uses that table.

### 11.4. Dedicated database/container per suite

Testcontainers can supply PostgreSQL or another database with an appropriate lifecycle. You can:
- Create a separate schema/database for a group of tests or per test class.
- Reset schemas with controlled migrations/fixtures between tests.
- Ensure data cleanup does not depend on test order or context cache reuse.

Never point a test that writes or deletes at a production database. With in-memory H2 as in the example, keep separate URLs across test classes so contexts do not clobber each other's schemas; when running tests in parallel, enforce explicit isolation.

### 11.5. Eventual consistency and asynchronous processing

If an HTTP request returns before message/event processing completes, **do not immediately assert the DB committed** and blame test flakiness. Check the API contract:
- If the synchronous API guarantees writes completed upon returning 201, assert state right away.
- If the API returns 202 Accepted for background processing, poll with an explicit timeout or await deterministic synchronization signals.
- Clean up data only after background work actually completes or has safe cancellation; avoid fixed `Thread.sleep` delays instead of proper synchronization.

## 12. Other risks when test thread and HTTP server thread are separate

Thread separation affects more than transactions:

- **SecurityContext:** Authentication placed on the test thread via thread-local mechanisms (e.g., in unit/method-security tests) does not automatically authenticate real HTTP requests. With `RANDOM_PORT`, send the needed tokens/cookies/headers via the HTTP client so the security filter chain authenticates just like production.
- **RequestContext and MDC:** Thread-local request attributes, logging MDC, or tracing state do not automatically cross to server threads without explicit propagation. Sending a correlation ID header aids tracing, yet shares no database transaction.
- **Hibernate persistence context:** An entity managed in T1 is not managed in T2. Pass IDs/DTOs over HTTP and let the server repository load entities from the database.
- **Isolation and locking:** Holding locks inside T1 while issuing a request to the server can cause the server to block, time out, or deadlock. Commit fixtures before making HTTP calls to avoid unnecessary lock contention.
- **Preemptive test timeouts:** Timeout wrappers executing test code on another thread can detach Spring's test-managed transaction from the thread running statements, potentially committing data unintentionally. Avoid preemptive timeouts around code relying on test-managed rollback unless you understand the threading mechanics.

All of these reinforce why **“same JVM” does not mean “same execution context”**.

## 13. Reading failure reports and verifying tests actually ran

In real HTTP integration tests, two distinct failure layers exist:
1. **HTTP/request path:** wrong response status, controller did not receive request, security blocked it, timeout, or server-side exception.
2. **Database/transaction path:** transaction did not commit, unexpected rollback, constraint error, isolation/locking issue, or broken data cleanup.

If `assertEquals(1, countByLabel(...))` fails after T1 rolls back, check in order:
- Is the test truly using `RANDOM_PORT` or `MOCK`/MockMvc?
- Does the service have a proper transaction boundary and is it invoked through a Spring proxy?
- Was the HTTP response 201 with a valid body?
- Do server and test repository point to the same datasource/schema?
- Had T1 **actually finished** before the readback query?
- Is an async worker or event listener committing after the response?
- Did cleanup run before the assertion, or did isolation differ across connections?

To run section 5's test class with Gradle Wrapper (Linux/macOS):

```bash
./gradlew test --tests "com.example.txhttp.RealHttpTransactionTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.txhttp.RealHttpTransactionTest"
```

To run the `MockMvc` class, substitute `com.example.txhttp.MockMvcTransactionTest`.

With Maven Wrapper (Linux/macOS):

```bash
./mvnw -Dtest=RealHttpTransactionTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=RealHttpTransactionTest test
```

Run `MockMvcTransactionTest` similarly. These commands require Java 17+, matching dependencies, and the JUnit Jupiter plugin; this article contains no `System.out.println` output, so there is no fixed stdout. Only the Gradle report `build/reports/tests/test/index.html` or Maven Surefire reports in `target/surefire-reports/` for that **exact module and run** confirm the result.

## 14. Common mistakes

| Mistake | Why it is wrong | Fix |
|---|---|---|
| `@SpringBootTest(RANDOM_PORT)` + `@Transactional` test expecting HTTP POST to roll back | Server request runs on another thread with its own transaction | Clean up committed data or use an isolated database |
| Assuming every `@SpringBootTest` starts an HTTP server | `MOCK` opens no real listener | Choose and verify `webEnvironment` |
| Thinking `MockMvc` always matches real HTTP for transactions | Synchronous dispatch usually runs on the test thread | Distinguish call paths and async/`REQUIRES_NEW` cases |
| Treating `@Rollback(true)` on a test as a server rollback command | Annotation only controls the test-managed transaction | Verify data after request and clean up outside T1 |
| Calling `saveAndFlush()` then HTTP assuming fixture is committed | Flush is not commit | Commit setup data before the HTTP request |
| Deleting DB in `@AfterEach` while T1 is active | Cleanup may roll back with the test | Clean up after T1, in `@AfterTransaction`, or isolated |
| Calling `verify(repository.save(...))` instead of checking real DB | Mocks do not prove commit/rollback | Integration test with real repository and database |
| Relying on generated ID as proof of commit | JPA/IDENTITY can assign IDs before commit | Re-query past the transaction boundary |
| `@Transactional` test passes even though service lacks annotation | Test T1 may provide a transaction for the service | Test service transaction boundaries outside test-managed T1 |
| Skipping cleanup of HTTP-committed records | Later tests see stale data, flaky suite | Use unique keys and committed deletes |
| HTTP test blocks because fixture in T1 holds a lock | Server uses another connection | Prepare and commit fixtures before the request |
| Assuming HTTP 201 means all background tasks committed | Async work can continue after the response | Follow sync/async contract, wait for bounded completion |
| Using `System.setProperty` or shared data across parallel tests | Pollutes JVM state and database | Use profiles/dynamic properties and proper resource isolation |

## 15. Review checklist for a data-writing `@SpringBootTest`

- [ ] Identified the exact `webEnvironment`: `RANDOM_PORT`, `DEFINED_PORT`, `MOCK`, or `NONE`.
- [ ] Know whether requests go **over an HTTP socket** or via `MockMvc`/in-process dispatcher.
- [ ] Distinguished **test-managed transaction T1** from application/server transactions on another thread.
- [ ] Do not use `@Rollback`, `@Commit`, or test `@Transactional` to promise rollback of HTTP server-committed data.
- [ ] Confirmed the service is invoked through a Spring proxy with the right transaction manager/propagation.
- [ ] For APIs depending on fixtures, setup data is **committed** before the server reads it.
- [ ] Verified data **past the transaction boundary**, not merely after `save` or `flush`.
- [ ] Designed independent cleanup for HTTP server-committed data: unique keys, `finally`, separate transaction, or DB reset.
- [ ] Accounted for `REQUIRES_NEW`, async threads, event listeners, timeouts, and test framework callbacks.
- [ ] Real rollback tests use an appropriate database and verify state after errors.
- [ ] Do not confuse an active transaction on the test thread with a transaction on the HTTP server thread.
- [ ] Executed the exact test class/CI job and inspected real reports before concluding PASS.

**Conclusion:** When `@SpringBootTest` starts a real HTTP server, **requests are processed in a different context from the test method**. A transaction created by `@Transactional` on the test **does not automatically propagate to the server**, so rolling back the test does not remove rows committed by server-side transactions. With synchronous `MockMvc`, calls typically share the test thread and can join the test transaction when propagation matches, yet that must not be generalized to all cases. To write reliable tests, trace **threads, proxies, propagation, and commit timing**, commit fixtures before requests, and clean up data created over real HTTP explicitly.
