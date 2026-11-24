# Real HTTP, @Async, and Calls Running Outside the Test Transaction Thread

In the **Transaction Testing** track of the **Spring Boot - testing** module, a very dangerous misconception is: "Since I annotated the test with `@Transactional`, every database change originating from the test will be rolled back." That claim **holds true only for work that actually participates in the test-managed transaction**. HTTP requests processed on a server thread, tasks running via `@Async`/executors, calls with an independent transaction, or code moved by the test framework onto another thread can **write and commit data outside the JUnit test's transaction**.

Spring TestContext binds test-managed transaction state to the **current thread** (via `ThreadLocal`). It does not automatically propagate a JDBC transaction/connection to HTTP server threads, `@Async` workers, `CompletableFuture.supplyAsync(...)`, or task schedulers. Thus, a test that passes green when run alone can leave data behind that breaks subsequent tests—or worse, write accidentally into a non-test database.

This lesson clearly distinguishes:

1. **Direct service calls** or **synchronous `MockMvc`** on the same thread: usually able to join the test transaction and roll back via Spring Test.
2. **Real HTTP via `@SpringBootTest(webEnvironment = RANDOM_PORT)`**: the test client and server handle requests on different threads; the server's transaction **is not part of test rollback**.
3. **`@Async` invoked through a Spring proxy**: logic runs on another thread; if the worker starts its own transaction and commits, rolling back the caller test does not undo that commit.
4. **Thread breaks/preemptive timeouts/`REQUIRES_NEW`/event listeners**: boundaries that alter transaction behavior even when method names or annotations look identical.

Complete examples are provided for **Java 17+, Spring Boot 3.5, JUnit Jupiter, Spring JDBC + H2**, covering application code, schema, direct rollback tests, `MockMvc` tests, real HTTP server tests, success/failure `@Async` tests, and a standalone Java SE program proving the `ThreadLocal` principle.

## 1. What Is a Test-Managed Transaction?

In Spring TestContext, `TransactionalTestExecutionListener` can open a **test-managed transaction** before a `@Transactional` test method. By default, Spring Test rolls it back when the method finishes, unless you change the policy with `@Commit`, `@Rollback(false)`, or `TestTransaction.flagForCommit()`.

Simple example:

```java
@SpringBootTest
class NoteWriterTest {

    @Autowired NoteWriter writer;
    @Autowired NoteStore store;

    @Test
    @Transactional
    void directCallUsesTestTransaction() {
        writer.create(new NoteRequest("TEST-A", "message"));
        assertEquals(1, store.countByKey("TEST-A"));
        // TestContext rolls back after the method finishes.
    }
}
```

This is an **illustrative skeleton**, not a complete file: it needs imports and the `NoteWriter`/`NoteRequest`/`NoteStore` classes defined below. Valid conclusion: when `writer.create(...)` is called **on the same thread**, the transaction started by the service with `REQUIRED` propagation usually **joins the existing test transaction**. The data is visible inside the test, yet rolls back when the test transaction ends.

**Do not conclude:** that all asynchronous side effects spawned by the method will roll back, or that `store.countByKey(...) == 1` inside the test proves data committed durably. A transaction can always see **its own uncommitted changes**.

### Three Easily Confused Transaction Types

| Scope | Managed by whom? | Example | Covered by test rollback? |
| --- | --- | --- | --- |
| **Test-managed** | Spring TestContext | `@Transactional` on a JUnit method | **Yes** for work joining this transaction |
| **Spring-managed application transaction** | Spring AOP/transaction manager | `@Transactional` on a service bean | **Yes if joining test transaction**; no if opening an independent transaction |
| **Application-managed** | Code using `TransactionTemplate`/transaction manager directly | Worker manually creating a transaction | Depends on whether it joins or opens its own transaction |

Two methods both annotated with `@Transactional` are not guaranteed to share the same transaction: propagation, thread, proxy, and transaction manager must all be considered together.

## 2. Thread Boundaries Determine Transaction Participation

With imperative transaction managers (JDBC/JPA), Spring binds transaction state to the executing thread. When code runs on another thread, that thread does not automatically see the caller's `TransactionSynchronizationManager` state.

```text
JUnit test thread                    HTTP / @Async worker thread
----------------                    --------------------------
TestContext BEGIN test-tx
    |
    +-- writer.create()                  (nothing if not called)
    |       joins test-tx
    |
    +-- HTTP POST ---------------------> request handler
    |                                    writer.create()
    |                                    BEGIN app-tx
    |                                    INSERT
    |                                    COMMIT app-tx
    |
    +-- asyncNotes.submit() -----------> executor worker
    |                                    writer.create()
    |                                    BEGIN app-tx
    |                                    INSERT
    |                                    COMMIT app-tx
    |
TestContext ROLLBACK test-tx          server/worker commits still persist
```

A **Spring-managed transaction on the worker** can still exist and work properly, yet it is a **different** transaction. The issue is not "`@Async` breaks all `@Transactional`," but rather **the caller's transaction does not propagate**. When the worker calls through a `@Transactional` service proxy, the worker can open a new transaction of its own.

### What Is TransactionSynchronizationManager For?

In diagnostic tests you can ask:

```java
boolean active =
        TransactionSynchronizationManager
                .isActualTransactionActive();
```

The result reports on the **current thread**; it does not prove other threads also have a transaction, nor whether the transaction will commit or roll back when the method ends. It is purely a debugging aid.

**Warning:** For **reactive transactions** (R2DBC/Reactor), Spring uses `Reactor Context` instead of traditional `ThreadLocal`. Remarks and runnable code in this lesson use **blocking JDBC/JPA-style imperative transactions**. Do not copy `ThreadLocal` rules verbatim onto every reactive pipeline.

## 3. Distinguishing MockMvc, Real HTTP, and Direct Calls

| Test approach | Actually starts a TCP HTTP server? | Typical handling thread | Same test-managed transaction? |
| --- | --- | --- | --- |
| Calling `noteWriter.create(...)` directly | No | JUnit test thread | **Yes**, if Spring proxy and `REQUIRED` join |
| `MockMvc.perform(...)` for a **synchronous controller** | No | Usually same test thread | **Often yes**, usually joins test transaction |
| `@SpringBootTest(webEnvironment = MOCK)` + `MockMvc` | No | Mock servlet request, usually synchronous | Usually same thread when synchronous |
| `@SpringBootTest(webEnvironment = RANDOM_PORT)` + `TestRestTemplate` | **Yes** | Different HTTP client and server threads | **No**, test transaction does not cross sockets |
| `@SpringBootTest(webEnvironment = DEFINED_PORT)` | **Yes** | Different server thread | Does not propagate test transaction |
| `@Async` via Spring proxy + executor | Not necessarily | Worker thread | Does not auto-join test transaction |
| `CompletableFuture.runAsync(...)` | Not necessarily | Executor/common pool | Does not auto-join test transaction |
| `@Async` calling method in same bean (**self-invocation**) | No | May still be caller thread | `@Async` is normally **not applied** via proxy |

**`MockMvc` is not "real HTTP"** even though its API looks like issuing GET/POST requests. `MockMvc` can run controllers, validation, and Jackson through mock servlet infrastructure; for synchronous controllers, most work stays on the test thread. That allows `@Transactional` tests to roll back DB operations from `MockMvc`, sharply differing from `RANDOM_PORT`.

However, **do not claim every `MockMvc` request stays in the same transaction**: async MVC controllers, `Callable`, `DeferredResult`, task offloading, explicit transaction propagation, or external I/O can cross this boundary. Whenever asynchronous dispatch exists, inspect the worker and its lifecycle.

## 4. @SpringBootTest RANDOM_PORT Does Not Roll Back Server Transactions

Per Spring Boot 3.5, when using `RANDOM_PORT` or `DEFINED_PORT`, the HTTP test client and embedded server **run on different threads**, and thus **different transactions**. Suppose a JUnit test:

```java
@Test
@Transactional
void testHttpPost() {
    restTemplate.postForEntity(
            "/notes",
            new NoteRequest("HTTP-A", "hello"),
            NoteView.class);
}
```

This is a skeleton of a test with `TestRestTemplate` and the app running on a random port. `@Transactional` on the test method **does not cause code inside the server controller to inherit the test's transaction**. When the server service calls `@Transactional` and returns normally, the server transaction can commit; subsequent rollback of the test **cannot undo a commit from another thread**.

### A Sneaky Pitfall: Green Test, Leftover Data

A test that only asserts HTTP 201 without inspecting the DB after the transaction can pass green, and then on the next suite run hit a duplicate key error because the previous request committed.

Anti-pattern example:

```java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class HttpRollbackAssumptionTest {
    @Test
    void createsNote() {
        // HTTP POST actually commits on the server.
        // The test's @Transactional does not clean server writes.
    }
}
```

Do not mistake this snippet for a complete test. It warns against **putting `@Transactional` on the whole class to "auto-clean the DB"** while making real HTTP calls.

### The Right Way

- Use a **dedicated** database/container/schema for integration tests.
- Choose a unique test key per method, never sharing production data.
- Clean **committed data outside the test transaction** via `finally`, an independent cleanup transaction, or an appropriate DB/container lifecycle reset.
- Verify committed data from a **different** connection/transaction after the test transaction ends.
- Never rely on rollback inside the test method to wipe server-side side effects.
- If testing business logic without needing an HTTP socket, consider service-level tests or synchronous `MockMvc` tests for an easier-to-control scope.

## 5. @Async and Executors: Do Not Inherit the Caller's Transaction

To enable async processing:

```java
@Configuration
@EnableAsync
class AsyncConfiguration {
    // Can define a dedicated executor bean.
}
```

A method:

```java
@Async("lessonExecutor")
public CompletableFuture<String> work() {
    return CompletableFuture.completedFuture("done");
}
```

If the method is invoked **through a Spring proxy**, the work runs on the designated executor and typically on a different thread from the caller. `@Transactional` on the test manages only the transaction on the test thread; the worker does not automatically receive that transaction.

### How Do @Async and @Transactional Work Together?

Recommended clear transaction boundary:

```text
Caller test thread
    |
    v
AsyncNoteWriter proxy (@Async)
    |
    +-- executor worker thread
            |
            v
        NoteWriter bean proxy (@Transactional)
            |
            v
        repository/JdbcTemplate INSERT
            |
            v
        COMMIT worker's transaction
```

This example separates `@Async` and `@Transactional` onto **two different beans**, avoiding AOP advice ordering confusion. Important points:

- `@Async` must be enabled with `@EnableAsync` or equivalent configuration.
- The call must **pass through the proxy**. `this.asyncMethod()` in the same class normally runs synchronously under default proxy mode.
- Picking a specific `Executor` makes tests deterministic, with clear thread names, pool size, and shutdown lifecycle.
- Use `CompletableFuture<T>` or `Future<T>` to **await results and observe exceptions**, rather than using `void @Async` and guessing when the task finished.
- Place `@Transactional` on the service performing SQL and call it from the worker through the bean proxy; it creates/joins a transaction based on the **worker thread's** state.
- Timeout in `future.get(5, SECONDS)` only limits how long the test waits; it does not automatically roll back transactions already committed on the worker.

### A Failed Future Does Not Mean an Outer Transaction Also Rolls Back

If the worker service has:

```java
@Transactional
public void createThenFail(NoteRequest request) {
    store.insert(request.key(), request.body());
    throw new IllegalStateException("controlled failure");
}
```

then the unchecked exception rolls back the **worker service's** transaction per default rules. A test calling `CompletableFuture.get(...)` can receive an `ExecutionException` wrapping the original error; that proves the future failed, yet proving DB rollback still requires checking that the row is actually absent.

Conversely, if the worker already committed and a later step subsequently fails, **an exceptional future does not undo prior commits**. Always distinguish transaction boundaries from the ordering of side effects.

## 6. Complete Java 17+ Code: JDBC H2, REST, and @Async

We build a small app storing test notes across three flows:

1. `NoteWriter.create(...)` saves a row transactionally.
2. `NoteController POST /notes` calls the service over **real HTTP**.
3. `AsyncNoteWriter.submit(...)` runs on an executor and calls the same service from a **worker thread**.

Every test uses a unique key to avoid collisions. The H2 schema is created on the **test classpath**; production Java code does not depend on H2 specifically.

### 6.1. File Structure

```text
src/
├── main/
│   └── java/example/testing/transactions/
│       ├── TransactionDemoApplication.java
│       ├── NoteRequest.java
│       ├── NoteView.java
│       ├── NoteStore.java
│       ├── NoteWriter.java
│       ├── NoteController.java
│       ├── AsyncConfig.java
│       ├── AsyncNoteWriter.java
│       └── ThreadLocalScopeDemo.java
└── test/
    ├── resources/schema.sql
    └── java/example/testing/transactions/
        ├── DirectRollbackTest.java
        ├── MockMvcRollbackTest.java
        ├── RealHttpTransactionTest.java
        └── AsyncTransactionTest.java
```

### 6.2. Gradle Dependencies

In a Spring Boot **3.5.x** project generated by Spring Initializr with compatible plugins/repositories/Java toolchain already set up, the `dependencies` section in `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an **incremental configuration snippet**, not a complete standalone build file. Java 17 is the minimum for this example; the Boot BOM manages compatible JDBC, H2, JUnit, and Spring Framework versions.

Because H2 is in `testRuntimeOnly`, **do not assume `main()` runs in production without a datasource**. To run the application outside tests, you must supply production DB/datasource configuration, schemas, and migrations. H2 here is strictly for tests.

### 6.3. Application: TransactionDemoApplication.java

Create `src/main/java/example/testing/transactions/TransactionDemoApplication.java`:

```java
package example.testing.transactions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TransactionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                TransactionDemoApplication.class, args);
    }
}
```

A shared root package lets Spring Boot scan the controller, repository, and services in the example. When tests invoke `@SpringBootTest`, Spring finds the application in this package and configures the beans accordingly.

### 6.4. Test H2 Schema: schema.sql

Create `src/test/resources/schema.sql`:

```sql
CREATE TABLE notes (
    note_key VARCHAR(100) PRIMARY KEY,
    note_text VARCHAR(400) NOT NULL
);
```

With `spring-boot-starter-jdbc` and embedded H2 on the test classpath, Spring Boot's default SQL initializer can execute `schema.sql` when creating the test datasource. Do not combine Flyway/Liquibase with `schema.sql` if they create the same table twice. In production, use proper migrations and lifecycle tooling.

Never store real passwords, tokens, or PII in the demo table. Tests use keys shaped like `HTTP-<UUID>`/`ASYNC-<UUID>` and synthetic content.

### 6.5. Request/Response DTOs

Create `src/main/java/example/testing/transactions/NoteRequest.java`:

```java
package example.testing.transactions;

public record NoteRequest(String key, String body) {
}
```

Create `src/main/java/example/testing/transactions/NoteView.java`:

```java
package example.testing.transactions;

public record NoteView(String key, String state) {
}
```

These are two separate Java records, each file holding one public top-level type matching its name. The demo omits validation annotations to keep focus on transaction behavior. In a production HTTP API, validate inputs, enforce authorization, check length limits, handle duplicate keys, and map errors safely.

### 6.6. JDBC Storage: NoteStore.java

Create `src/main/java/example/testing/transactions/NoteStore.java`:

```java
package example.testing.transactions;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class NoteStore {
    private final JdbcTemplate jdbc;

    public NoteStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String key, String body) {
        jdbc.update(
                "INSERT INTO notes(note_key, note_text) VALUES (?, ?)",
                key, body);
    }

    public int countByKey(String key) {
        Integer result = jdbc.queryForObject(
                "SELECT COUNT(*) FROM notes WHERE note_key = ?",
                Integer.class, key);
        return result == null ? 0 : result;
    }

    public void deleteByKey(String key) {
        jdbc.update(
                "DELETE FROM notes WHERE note_key = ?", key);
    }
}
```

The code uses **parameterized SQL** with `?` placeholders instead of concatenating keys into SQL strings. `NoteStore` does not configure transactions itself; `JdbcTemplate` participates in the Spring-managed connection/transaction context on the current thread. Without a transaction, JDBC operations normally execute with connection auto-commit per configuration.

**Important:** `countByKey` inside a test transaction can see that transaction's own uncommitted records. To prove data committed externally, the tests will **end the test transaction before querying again**.

### 6.7. Transactional Service: NoteWriter.java

Create `src/main/java/example/testing/transactions/NoteWriter.java`:

```java
package example.testing.transactions;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NoteWriter {
    private final NoteStore store;

    public NoteWriter(NoteStore store) {
        this.store = store;
    }

    @Transactional
    public void create(NoteRequest request) {
        store.insert(request.key(), request.body());
    }

    @Transactional
    public void createThenFail(NoteRequest request) {
        store.insert(request.key(), request.body());
        throw new IllegalStateException(
                "controlled failure");
    }
}
```

With an appropriate `PlatformTransactionManager` and Spring's proxy applied, an external bean call to `create(...)` will:

- **Join** an existing transaction on that same thread if default `REQUIRED` propagation and a compatible transaction manager apply.
- **Open a new transaction** if none exists on the worker/server thread.
- **Commit** upon normal method return if the interceptor itself opened the transaction.
- **Roll back** when the method throws an unchecked exception (such as `IllegalStateException`) under default rules.

Therefore, the very same `NoteWriter.create(...)` can roll back in a direct/JUnit test yet commit over real HTTP or `@Async`. That is precisely the contract to test.

### 6.8. Controller: NoteController.java

Create `src/main/java/example/testing/transactions/NoteController.java`:

```java
package example.testing.transactions;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/notes")
public class NoteController {
    private final NoteWriter writer;

    public NoteController(NoteWriter writer) {
        this.writer = writer;
    }

    @PostMapping
    public ResponseEntity<NoteView> create(
            @RequestBody NoteRequest request) {
        writer.create(request);

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new NoteView(request.key(), "stored"));
    }

    @PostMapping("/fail")
    public ResponseEntity<NoteView> createThenFail(
            @RequestBody NoteRequest request) {
        writer.createThenFail(request);
        throw new AssertionError(
                "Expected service exception");
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<ApiError> mapFailure(
            IllegalStateException error) {
        return ResponseEntity.status(
                        HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ApiError("WRITE_FAILED"));
    }

    public record ApiError(String code) {
    }
}
```

Points to note:

- The controller calls `NoteWriter` through **another bean**, so the `@Transactional` service is intercepted by the Spring proxy. Do not self-invoke `this.create(...)` on the service itself expecting the proxy to activate.
- When `POST /notes` succeeds, the server transaction can commit **before the HTTP 201 response reaches the test**.
- `POST /notes/fail` calls the service throwing `IllegalStateException`, rolling back the **server-side service** transaction; the exception handler returns a stable public error code.
- The `throw new AssertionError(...)` line after the service call simply clarifies that branch must not execute when the service behaves properly. It is **not an expected runtime path** and is never exposed to clients in the tested scenario.
- The example does not implement production authentication/authorization, request validation, rate limiting, or error taxonomy. Never deploy as-is publicly without adding those boundaries.

### 6.9. Async Executor Configuration: AsyncConfig.java

Create `src/main/java/example/testing/transactions/AsyncConfig.java`:

```java
package example.testing.transactions;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfig {

    @Bean(name = "lessonExecutor")
    public ThreadPoolTaskExecutor lessonExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("lesson-async-");
        executor.initialize();

        return executor;
    }
}
```

`@EnableAsync` lets Spring intercept `@Async`; naming `lessonExecutor` makes it clear in tests which executor ran the task. `ThreadPoolTaskExecutor` is a Spring-managed bean; when the context closes, lifecycle destruction shuts down the executor. Do not create a brand-new executor inside every test and leak threads.

**Never use `Thread.sleep` to "wait for async completion."** Wait on `CompletableFuture.get(timeout, unit)` or use appropriate synchronization primitives/events when tests need to observe state.

### 6.10. Async Worker: AsyncNoteWriter.java

Create `src/main/java/example/testing/transactions/AsyncNoteWriter.java`:

```java
package example.testing.transactions;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncNoteWriter {
    private final NoteWriter writer;

    public AsyncNoteWriter(NoteWriter writer) {
        this.writer = writer;
    }

    @Async("lessonExecutor")
    public CompletableFuture<AsyncReceipt> submit(
            NoteRequest request) {
        writer.create(request);

        return CompletableFuture.completedFuture(
                new AsyncReceipt(
                        request.key(),
                        Thread.currentThread().getName()));
    }

    @Async("lessonExecutor")
    public CompletableFuture<Void> submitThenFail(
            NoteRequest request) {
        writer.createThenFail(request);
        return CompletableFuture.completedFuture(null);
    }

    public record AsyncReceipt(
            String key, String threadName) {
    }
}
```

`AsyncNoteWriter` and `NoteWriter` **are two separate Spring beans**. When a caller invokes `asyncNoteWriter.submit(...)` through the bean proxy, Spring selects `lessonExecutor` and runs the method body on a worker thread; the body calls `writer.create(...)` through its transactional proxy. If SQL commits cleanly, the future completes with `AsyncReceipt`; if SQL/logic fails, the future completes **exceptionally**.

Why does the method return `CompletableFuture.completedFuture(...)` even though it is async? In Spring `@Async`, the target method can return a temporary already-completed future; the proxy returns the **task's future** submitted to the executor for the caller. When the caller awaits `get(...)`, it receives the value or exception after the worker finishes.

**Note:** `@Async void` does not propagate exceptions through a `Future`; if you need to catch failures in tests or production workflows, prefer `CompletableFuture<T>` or a dedicated monitoring/ack mechanism. Never assume the task finished just because the method was invoked.

## 7. Test 1: Calling the Service Directly and Real Rollback

Create `src/test/java/example/testing/transactions/DirectRollbackTest.java`:

```java
package example.testing.transactions;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.NONE)
class DirectRollbackTest {
    @Autowired
    private NoteWriter writer;

    @Autowired
    private NoteStore store;

    private String key;

    @BeforeTransaction
    void createUniqueTestKey() {
        key = "DIRECT-" + UUID.randomUUID();
    }

    @Test
    @Transactional
    void directCallIsVisibleInsideTestTransaction() {
        writer.create(new NoteRequest(key, "direct"));

        assertEquals(1, store.countByKey(key));
        // Does not commit. Spring Test rolls back after method.
    }

    @AfterTransaction
    void verifyOutsideTransaction() {
        assertEquals(0, store.countByKey(key));
    }
}
```

**Two different observation moments:**

- Inside `@Test @Transactional`, `NoteWriter.create` with `REQUIRED` joins the test transaction, so `countByKey(key) == 1`.
- `@AfterTransaction` runs **after Spring TestContext ends the transaction**; the query finds zero rows because the test rolled back.

`@BeforeTransaction` and `@AfterTransaction` are invoked by Spring TestContext for test methods with a test-managed transaction. They are not regular JUnit `@BeforeEach`/`@AfterEach` callbacks. This is a far more reliable way to **measure post-transaction rollback** than reading inside the transaction itself.

**Never use fixed keys** across multiple test classes or CI jobs. UUIDs make data more independent, though they do not replace a dedicated test database.

## 8. Test 2: Synchronous MockMvc Can Join the Test Transaction

Create `src/test/java/example/testing/transactions/MockMvcRollbackTest.java`:

```java
package example.testing.transactions;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.test.context.transaction.BeforeTransaction;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MockMvcRollbackTest {
    @Autowired
    private MockMvc mvc;

    @Autowired
    private NoteStore store;

    private String key;

    @BeforeTransaction
    void setKey() {
        key = "MOCK-" + UUID.randomUUID();
    }

    @Test
    @Transactional
    void synchronousControllerJoinsCallerTestTransaction()
            throws Exception {
        String json = """
                {"key":"%s","body":"through mock mvc"}
                """.formatted(key);

        mvc.perform(post("/notes")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.key").value(key))
                .andExpect(jsonPath("$.state").value("stored"));

        assertEquals(1, store.countByKey(key));
    }

    @AfterTransaction
    void noRowAfterRollback() {
        assertEquals(0, store.countByKey(key));
    }
}
```

`MockMvc` here executes a **synchronous controller** through mock servlet infrastructure rather than an HTTP socket and independent server thread. In this example, request processing joins the test thread/transaction; hence `@AfterTransaction` confirms the row was rolled back.

**Do not overgeneralize:** if the controller uses `@Async`, `DeferredResult`, executors, messaging, or another `REQUIRES_NEW` transaction, some side effects can still run outside the test-managed transaction even when called through `MockMvc`.

## 9. Test 3: Real HTTP Commits on the Server, Test Rollback Cannot Erase It

Create `src/test/java/example/testing/transactions/RealHttpTransactionTest.java`:

```java
package example.testing.transactions;

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
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpTransactionTest {
    @Autowired
    private TestRestTemplate http;

    @Autowired
    private NoteStore store;

    @Test
    @Transactional
    void testRollbackDoesNotUndoServerCommit() {
        String serverKey = "HTTP-" + UUID.randomUUID();
        String localKey = "LOCAL-" + UUID.randomUUID();

        try {
            ResponseEntity<NoteView> response =
                    http.postForEntity(
                            "/notes",
                            new NoteRequest(serverKey, "from server"),
                            NoteView.class);

            assertEquals(
                    HttpStatus.CREATED,
                    response.getStatusCode());
            assertNotNull(response.getBody());
            assertEquals(serverKey, response.getBody().key());

            // This write happens right inside the test-managed tx.
            store.insert(localKey, "from junit thread");
            assertEquals(1, store.countByKey(localKey));

            // Explicitly end the test transaction.
            TestTransaction.flagForRollback();
            TestTransaction.end();

            // Now both SELECTs run outside the test transaction.
            assertEquals(0, store.countByKey(localKey));
            assertEquals(1, store.countByKey(serverKey));
        } finally {
            if (TestTransaction.isActive()) {
                TestTransaction.flagForRollback();
                TestTransaction.end();
            }
            // Cleanup outside test tx, even if assertions fail.
            store.deleteByKey(localKey);
            store.deleteByKey(serverKey);
        }
    }

    @Test
    void failedServerTransactionRollsBackItsOwnWrite() {
        String key = "FAIL-HTTP-" + UUID.randomUUID();

        try {
            ResponseEntity<NoteController.ApiError> response =
                    http.postForEntity(
                            "/notes/fail",
                            new NoteRequest(key, "should rollback"),
                            NoteController.ApiError.class);

            assertEquals(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    response.getStatusCode());
            assertNotNull(response.getBody());
            assertEquals(
                    "WRITE_FAILED",
                    response.getBody().code());
            assertEquals(0, store.countByKey(key));
        } finally {
            store.deleteByKey(key);
        }
    }
}
```

**These two tests prove two independent conclusions:**

1. **Server commits survive JUnit rollback:** HTTP `POST /notes` is handled by the server on another thread and the service creates/commits its own transaction. After `TestTransaction.end()` rolls back the test transaction, **`localKey` disappears** while **`serverKey` still exists**. The test then cleans up the server-committed row via JDBC outside the test transaction.
2. **Server errors roll back the server's own transaction:** `/notes/fail` hits `NoteWriter.createThenFail`, throws an unchecked exception, and returns public HTTP 500; the database keeps no new row because the **server service transaction** rolled back. Never assume an HTTP error automatically rolls back earlier operations if they already committed separately.

### Why End the Test Transaction Before Inspecting?

If you only query the DB from inside the same test-managed transaction, you could observe uncommitted state or be affected by connection isolation. `TestTransaction.end()` lets the test **exit the caller transaction cleanly**, after which `store.countByKey(...)` observes data in a separate transaction/connection.

**Lifecycle note:** `TestTransaction.end()` is only valid while a test-managed transaction is active. When calling it manually, you are responsible for flagging rollback first and never leaving the method in an ambiguous state. The `finally` block handles cases where an assertion fails before ending the transaction.

### Cleanup in finally Must Sit Outside the Test Transaction

An anti-pattern is adding `@AfterEach void cleanup(){ store.deleteByKey(serverKey); }` on a `@Transactional` class and assuming the `DELETE` will stick. With an active test transaction, `@AfterEach` can also run **inside the test transaction and get rolled back**, leaving the server's committed row behind.

The example places `TestTransaction.end()` before `store.deleteByKey(...)` in `finally` to guarantee cleanup runs **outside the test transaction**. Every test needs an isolated database/distinct test key so it does not delete someone else's data.

**Never use a production database** for tests with real HTTP calls or explicit cleanup. Configure `spring.datasource.*` under a dedicated test profile/container.

## 10. Test 4: @Async Commits on a Worker Outside the Test Transaction

Create `src/test/java/example/testing/transactions/AsyncTransactionTest.java`:

```java
package example.testing.transactions;

import java.util.UUID;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.NONE)
class AsyncTransactionTest {
    @Autowired
    private AsyncNoteWriter asyncWriter;

    @Autowired
    private NoteStore store;

    @Test
    @Transactional
    void asyncWorkerCommitSurvivesCallerRollback()
            throws Exception {
        String asyncKey = "ASYNC-" + UUID.randomUUID();
        String localKey = "LOCAL-" + UUID.randomUUID();

        try {
            AsyncNoteWriter.AsyncReceipt receipt =
                    asyncWriter.submit(
                            new NoteRequest(asyncKey, "worker"))
                            .get(5, TimeUnit.SECONDS);

            assertEquals(asyncKey, receipt.key());
            assertTrue(receipt.threadName()
                    .startsWith("lesson-async-"));

            // Caller write sits inside the test-managed transaction.
            store.insert(localKey, "caller");
            assertEquals(1, store.countByKey(localKey));

            TestTransaction.flagForRollback();
            TestTransaction.end();

            assertEquals(0, store.countByKey(localKey));
            assertEquals(1, store.countByKey(asyncKey));
        } finally {
            if (TestTransaction.isActive()) {
                TestTransaction.flagForRollback();
                TestTransaction.end();
            }
            store.deleteByKey(localKey);
            store.deleteByKey(asyncKey);
        }
    }

    @Test
    void asyncFailureRollsBackWorkerTransaction()
            throws Exception {
        String key = "FAIL-ASYNC-" + UUID.randomUUID();

        try {
            ExecutionException error = assertThrows(
                    ExecutionException.class,
                    () -> asyncWriter.submitThenFail(
                                    new NoteRequest(key, "bad"))
                            .get(5, TimeUnit.SECONDS));

            assertNotNull(error.getCause());
            assertInstanceOf(
                    IllegalStateException.class,
                    error.getCause());

            assertEquals(0, store.countByKey(key));
        } finally {
            store.deleteByKey(key);
        }
    }
}
```

**Why `get(5, SECONDS)`?** It forces the test to await future completion before inspecting the DB and cleaning up. Never use `Thread.sleep(100)` hoping the worker has already committed or rolled back. Checking the thread prefix `lesson-async-...` verifies the test went through the named executor, catching self-invocation mistakes where `@Async` is never intercepted.

**However, distinguish two timeout layers:** `future.get(5, SECONDS)` bounds **how long the test waits**; upon timeout, the worker may keep running. If a real test could hang, coordinate task cancellation and lifecycle cleanup before wiping the DB. A test timeout does not prove the task itself stopped.

**Two outcomes:**

- Success: `NoteWriter.create` opens/commits the worker's transaction; rolling back the JUnit caller does not delete the row.
- Failure: `NoteWriter.createThenFail` on the worker throws an unchecked exception; the worker's transaction rolls back and the `Future` reports the failure. The test asserts **both the exception and the absence of the row**.

This test does not prove "every `@Async` commits" — it only proves this configured flow where the worker invokes a transactional service whose transaction completes normally.

## 11. Running the Tests with Gradle

From the project root with the Gradle wrapper:

```bash
./gradlew test --tests example.testing.transactions.DirectRollbackTest
./gradlew test --tests example.testing.transactions.MockMvcRollbackTest
./gradlew test --tests example.testing.transactions.RealHttpTransactionTest
./gradlew test --tests example.testing.transactions.AsyncTransactionTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.transactions.DirectRollbackTest"
.\gradlew.bat test --tests "example.testing.transactions.MockMvcRollbackTest"
.\gradlew.bat test --tests "example.testing.transactions.RealHttpTransactionTest"
.\gradlew.bat test --tests "example.testing.transactions.AsyncTransactionTest"
```

**Expected when project, driver, and schema are right:** there are **6 JUnit test methods**: one direct, one `MockMvc`, two real HTTP, and two async. All pass. Console output varies by Gradle/JUnit/logging configuration, so there is no single exact stdout string for these commands.

**Why does test isolation still matter even when each class passes?** `@SpringBootTest` tests with different web environments may create separate contexts; each context may have its own `DataSource` or share database configuration depending on setup. UUID keys + `finally` cleanup reduce collisions, yet with a shared container/test DB and parallel execution, you must still enforce isolation.

If the DB is missing `notes`, check `src/test/resources/schema.sql`, the H2 test runtime datasource, Spring SQL initialization, and migration conflicts. If a real test container replaces H2, schema initialization may require `spring.sql.init.mode=always` or proper migrations.

## 12. Plain Java 17: ThreadLocal Does Not Automatically Cross Executors

To see the difference between caller and worker threads **without Spring**, create `src/main/java/example/testing/transactions/ThreadLocalScopeDemo.java`:

```java
package example.testing.transactions;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThreadLocalScopeDemo {
    public static void main(String[] args) throws Exception {
        ThreadLocal<String> marker = new ThreadLocal<>();
        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        marker.set("test-transaction");
        try {
            String workerValue = executor.submit(
                    () -> marker.get())
                    .get(2, TimeUnit.SECONDS);

            System.out.println(
                    "caller=" + marker.get());
            System.out.println(
                    "worker=" + (workerValue == null
                            ? "no-test-transaction"
                            : workerValue));
        } finally {
            marker.remove();
            executor.shutdownNow();
        }
    }
}
```

Compile and run with JDK 17+ from the project root:

```bash
javac -d out src/main/java/example/testing/transactions/ThreadLocalScopeDemo.java
java -cp out example.testing.transactions.ThreadLocalScopeDemo
```

**Exact** stdout:

```text
caller=test-transaction
worker=no-test-transaction
```

This program **does not open a JDBC transaction**; it simply illustrates one trait of `ThreadLocal`: a value bound on the caller thread does not automatically appear inside an executor worker thread. This is a **useful analogy**, not evidence replacing the integration tests with DB and Spring AOP proxies in sections 7–10.

**Note:** manually copying a `ThreadLocal` marker to a worker does not mean you safely propagated a real transaction. Never copy transaction state/connections across threads with a custom `TaskDecorator`, as doing so breaks thread-safety and resource ownership. If atomicity is required across asynchronous steps, design proper transaction boundaries, outbox/saga patterns, or orchestration.

## 13. @Transactional REQUIRES_NEW and Transactions Outside the Test

Even **on the same thread**, code can commit separately if a Spring-managed bean uses `REQUIRES_NEW` propagation:

```java
@Service
public class IndependentWriter {
    @Transactional(
            propagation = Propagation.REQUIRES_NEW)
    public void writeIndependent() {
        // An independent transaction is started.
    }
}
```

This is an **illustrative snippet** (requires source file, imports, and repository); not part of the runnable suite. When called through a proxy, Spring can **suspend** the existing transaction and create a new one that commits/rolls back independently. Hence a `@Transactional` test does not guarantee rolling back side effects committed by `REQUIRES_NEW`.

Conversely, `Propagation.REQUIRED` on a service called on the same thread normally joins the test transaction, so rollback applies cleanly to that transaction's operations. Other propagations such as `NOT_SUPPORTED`/`NEVER` alter the contract as well, though `@Transactional` on a test method supports only a specific subset of annotation attributes for test-managed transactions.

### @Transactional on a Test Method Does Not Apply All Attributes Like a Service

Per Spring TestContext:

- `@Transactional` on a test: decides whether to open a test transaction and which transaction manager to use. `@Transactional(propagation = NOT_SUPPORTED)` or `NEVER` skips running a test-managed transaction.
- Many attributes such as `isolation`, `timeout`, `readOnly`, `rollbackFor`/`noRollbackFor` on the test annotation **are not processed with full application-service semantics** in test-managed transactions.
- Use `@Commit`, `@Rollback`, or `TestTransaction.flagForCommit/flagForRollback` to control the test transaction's outcome.
- To test real service transaction propagation, call the bean through its proxy and write appropriate assertions outside the transaction.

### Do Not Expect Self-Invocation to Start a New Transaction

A method inside a class calling `this.otherTransactionalMethod()` usually bypasses the Spring proxy, so `@Transactional(REQUIRES_NEW)` on the internally called method may **not apply** under default proxy mode. The same trap hits `@Async` self-invocation. Extract a separate bean or design explicit proxy-based orchestration.

## 14. Preemptive Timeouts Can Bypass the Test Transaction

The official Spring TestContext documentation warns about a subtle trap:

```java
@Test
@Transactional
void dangerousPreemptiveTest() {
    assertTimeoutPreemptively(
            Duration.ofSeconds(2),
            () -> noteWriter.create(
                    new NoteRequest("X", "value")));
}
```

This snippet is an illustrative anti-pattern requiring JUnit and service imports; it is **not run in the runnable test suite**.

Why is it dangerous? `assertTimeoutPreemptively(...)` can execute the callback on a **different thread** from the thread where Spring bound transaction state. When the callback invokes a `@Transactional(REQUIRED)` service, the service sees no caller transaction and can open and commit its own transaction. The test framework still rolls back the test-managed transaction on the original thread — yet the callback's commit already happened outside it.

**When you need a timeout assertion:**

- JUnit's `assertTimeout(...)` is normally **non-preemptive**, running the executable on the calling thread and measuring duration; its limitation is that it cannot interrupt a hung call.
- For integration tests needing hang protection, use runner/build-level timeouts, specific API timeouts, or JUnit configuration mindful of thread modes rather than blindly reaching for `assertTimeoutPreemptively`.
- JUnit's `@Timeout` has configurable thread modes. Never equate it with `assertTimeoutPreemptively` without checking runner configuration.
- If a test already produced committed side effects, a timeout does not guarantee cleanup ran; explicit lifecycle/compensating cleanup is needed.

## 15. Event Listeners, Message Queues, and After-Commit Callbacks

Other flows also easily fall outside test rollback:

### 15.1. @TransactionalEventListener(AFTER_COMMIT)

An event listener with `@TransactionalEventListener(phase = AFTER_COMMIT)` runs only when the matching transaction **commits**. In a default-rollback `@Transactional` test, the `AFTER_COMMIT` listener normally **does not run**. If a test expects the event side effect, the listener is not necessarily broken; the transaction may never have committed in that phase.

Conversely, if the event is published inside a committing **HTTP server transaction** or **worker transaction**, the `AFTER_COMMIT` listener can run even though the test thread rolls back. If the listener is also `@Async`, side effects can arrive late; the test must await a controlled acknowledgement/event and clean up properly.

### 15.2. @Async Event Handlers / Messaging

If a service sends a message to a queue or calls an external HTTP client directly inside the test transaction, DB rollback does not "recall" the sent message. Message brokers and remote services do not participate in JDBC rollback just because the caller has `@Transactional`. That is why transaction-aware event publication, transactional outboxes, or sagas matter in production.

**Limitation of fake-based tests:** if a mock broker merely appends to a `List` on the same thread, tests can miss real-system side effects/visibility/retries. Use appropriate integration tests when contracts involve external messages.

### 15.3. CompletableFuture and Schedulers Do Not Inherit Transactions

`CompletableFuture.supplyAsync(...)` typically runs on the common pool or a provided executor. This is also a thread boundary. If the task calls a DAO directly without a transaction interceptor, commit behavior depends on the JDBC connection/autocommit. If it calls a transactional service bean through a proxy, it uses the worker's transaction, not JUnit's.

## 16. Test Data: Setup, Cleanup, and @Sql

**Test data design principles for cross-thread tests:**

1. **Dedicated test database** (isolated H2 per context, Testcontainers for real engines) with safe credentials.
2. Each test generates unique keys; zero dependence on method order.
3. Never point a test datasource at production or shared staging with real data.
4. Await HTTP responses/futures before inspecting final results.
5. Clean committed data **outside the rolled-back transaction**, e.g., in `finally` after `TestTransaction.end()`, or via a cleanup component with its own controlled transaction.
6. If a task might still be running after a timeout, do not clean up the DB concurrently and declare the environment clean; cancel/await the worker or isolate containers/suites so they cannot race.
7. Use `@AfterTransaction` to verify state **after rollback** in Spring TestContext-managed tests, not only inside the test method.
8. With multi-threaded tests, check database isolation/transaction managers to understand which sessions can see uncommitted data.

### Where Do @BeforeEach and @AfterEach Sit?

With test-managed `@Transactional`, JUnit's `@BeforeEach` and `@AfterEach` lifecycle methods normally run **inside the test transaction**. Consequently:

```java
@AfterEach
void cleanup() {
    store.deleteByKey("HTTP-A");
}
```

may **fail to clean up a server-side committed row**: the `DELETE` gets rolled back with the test transaction. If you need logic before/after the transaction, Spring Test provides `@BeforeTransaction`/`@AfterTransaction`. In the runnable suite, for HTTP/async tests, cleanup is placed explicitly **after ending the test-managed transaction** to avoid misunderstanding.

### @Sql and Transaction Modes

`@Sql` is handy for seeding/cleaning fixtures, yet you must watch its transaction mode:

- With default `@Sql` sharing the test transaction, seeded/deleted data can roll back with the test transaction.
- `@SqlConfig(transactionMode = ISOLATED)` runs the script in a **separate committed transaction**, suitable for some setup/cleanup yet prone to leaking state if used carelessly.
- `@Sql(executionPhase = AFTER_TEST_METHOD)` does not automatically guarantee running outside the test-managed transaction; that depends on listener ordering and mode.
- Never assume an arbitrary `@Sql` `DELETE` will wipe server-committed writes if cleanup runs inside the wrong transaction.

When an entire database is dedicated to an integration suite, resetting schemas, truncating, or recreating ephemeral containers between tests can work; weigh startup cost against stability. Never run unconditional `DELETE FROM ...` on a database you are not sure is isolated.

## 17. Comparing Testing Strategies When Thread Boundaries Exist

| Goal | Recommended test layer | Transaction/cleanup strategy |
| --- | --- | --- |
| Pure Java/service logic without DB | JUnit unit + fake/mock | No real transaction needed |
| Service JDBC business method & tx join | `@SpringBootTest` or JDBC slice | `@Transactional` rollback + `@AfterTransaction` when needed |
| Synchronous MVC controller, JSON mapping | `MockMvc` / `@WebMvcTest` | Can join caller tx; still test boundaries if async exists |
| Real HTTP status/headers/serialization/sockets | `@SpringBootTest(RANDOM_PORT)` + `TestRestTemplate`/HTTP client | **Do not trust test rollback; clean up committed rows** |
| Async executor + transactional service | `@SpringBootTest` with `@EnableAsync` + real executor | `CompletableFuture.get(timeout)`, inspect DB after completion, independent cleanup |
| Post-commit events / queues | Integration + appropriate broker/container | Await acknowledgement, clean up messages/DB, verify idempotency |
| `REQUIRES_NEW` propagation | Integration test with real proxy | Observe committed state outside caller tx |
| Reactive database pipeline | R2DBC slice/integration + Reactor tx tools | `Reactor Context` + `TransactionalOperator`, do not rely on JDBC `ThreadLocal` |

**Do not choose a broader test tier just because you feel like it:** if a pure service only sums amounts, plain JUnit without Spring/DB is faster and more stable. Yet for real HTTP boundaries, `@Async`, commit/rollback, and DB visibility, **mocks prove nothing** about real side effects.

## 18. Common Mistakes

**1. Putting `@Transactional` on a `@SpringBootTest(RANDOM_PORT)` class and expecting HTTP writes to auto-roll back.** The server thread uses a different transaction, so commits can persist.

**2. Confusing `MockMvc` with HTTP over sockets.** Synchronous `MockMvc` controllers typically run on the test thread; `RANDOM_PORT` has a separate server. The two styles have different rollback semantics.

**3. Asserting only HTTP 201 without inspecting the DB after the test transaction.** You can miss committed side effects or data contamination.

**4. Querying the DB inside the same transaction and calling it committed.** Same-transaction reads see uncommitted writes.

**5. Using `@AfterEach` `DELETE` in a `@Transactional` test to clean server commits.** The `DELETE` can roll back; move cleanup outside the transaction.

**6. Ending `TestTransaction` while forgetting to flag rollback.** Produces confusing state; call `flagForRollback()` and `end()` explicitly as intended.

**7. Calling an `@Async` method via `this.method()` in the same bean.** Proxy does not intercept, the method runs synchronously, and the test passes falsely.

**8. Adding `@Async` without `@EnableAsync` or the right executor.** The method never runs on the expected worker. Assert thread names or observable behavior.

**9. Using `Thread.sleep` to await tasks.** Flaky on CI; use a `Future`/acknowledgement with a bounded timeout.

**10. Failing to check `CompletableFuture` exceptions.** A `void @Async` can fail in the background with only a log line while the test stays green. Use typed `Future`s when asserting failures.

**11. Thinking an exceptional `Future` rolls back all prior transactions.** Commits completed before the exception still persist; inspect transaction boundaries.

**12. Thinking `@Transactional(REQUIRES_NEW)` joins caller rollback.** It opens and commits an independent transaction, even on the same thread.

**13. Using `assertTimeoutPreemptively` with a test-managed transaction.** The callback runs on another thread and can commit outside the test transaction.

**14. Expecting `@TransactionalEventListener(AFTER_COMMIT)` to run in a default-rollback test.** It requires an actual commit phase; under test rollback it may never run.

**15. Sharing the same key/DB state across tests.** Commits from HTTP/async tests cause duplicate keys or order-dependent failures.

**16. Accidentally pointing the test DB at production.** Test inserts/cleanups are destructive side effects; always use a dedicated test instance/schema.

**17. Forgetting the difference between JDBC and reactive transactions.** Imperative `ThreadLocal` is not `Reactor Context` transaction propagation.

**18. Misusing `@DirtiesContext` to erase committed DB rows.** Reloading the Spring context does not guarantee wiping the database; use real cleanup/migrations/container lifecycles.

**19. Treating HTTP 500 as proof the DB rolled back.** If another operation committed before the error, data remains. Assert database state after the request.

**20. Cleaning data on test timeout while an async worker is still running.** The worker can insert **after** cleanup and leave data behind. Cancel/await the task or isolate the environment.

## 19. QA Checklist Before Concluding Rollback Is Safe

**Identify boundaries:**

- Does the test call the service directly, synchronous `MockMvc`, a real HTTP socket, or an executor?
- Is there a Spring TestContext test transaction? Where is `@Transactional` placed?
- Is there a proper `PlatformTransactionManager` and real bean proxy?
- Which **thread** runs the data-writing code? Does it go through `@Async`/`CompletableFuture`?
- Is the service's transaction propagation `REQUIRED`, `REQUIRES_NEW`, or `NOT_SUPPORTED`?
- Does the test invoke an internal method via `this` bypassing the AOP proxy?

**Observe data:**

- Are uncommitted local rows distinguished from committed server/worker rows?
- Does the test inspect data after the **test transaction has ended/rolled back**?
- When HTTP returns an error or a future fails, does the test assert DB state instead of only status/exception?
- Do results depend on DB isolation or a separate connection?
- Are both success and failure paths of workers/servers tested?

**Async and timeouts:**

- Are `@EnableAsync`, executor, thread prefix, and `@Async("...")` configured correctly?
- Does the test await a `Future`/ack with a bounded timeout instead of `Thread.sleep`?
- On timeout/cancellation, has the worker actually stopped before cleanup?
- Is `assertTimeoutPreemptively` avoided on transaction-sensitive operations?
- Are async errors captured into the `Future` or handled/logged cleanly?

**Cleanup and CI:**

- Dedicated DB for integration tests, with no production credentials?
- Unique key/fixture per method, independent of test order?
- Committed HTTP/`@Async` rows cleaned up **outside the test transaction**?
- If using `@AfterEach`/`@Sql`, is the cleanup's transaction mode right?
- Are parallel tests prevented from corrupting each other's data or misusing container lifecycles?
- Are conclusions scoped strictly to what actually ran, without treating mock tests as real DB/network checks?

**Conclusion:** `@Transactional` in a JUnit test **is not a mechanism for rolling back all side effects of a workflow**. With imperative Spring TestContext, transactions are bound to the thread. Direct calls or synchronous `MockMvc` can normally roll back, whereas **real HTTP via `RANDOM_PORT`**, **`@Async` workers**, and independent transactions can commit outside the test transaction. Proper testing requires identifying **thread + proxy + propagation + transaction manager**, awaiting task completion, reading the DB after caller rollback, and cleaning committed writes in a lifecycle **outside the test transaction**.

## 20. Official References

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `RANDOM_PORT`/`DEFINED_PORT` and HTTP client/server running in separate transactions.
- [Spring Framework 6.2 — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): `ThreadLocal`, rollback, `TestTransaction`, `@BeforeTransaction`/`@AfterTransaction`, preemptive timeouts.
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `@EnableAsync`, `@Async`, executor qualification, proxy self-invocation, and `Future` exceptions.
- [Spring Framework — @Transactional API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html): thread-bound transaction semantics and propagation.
- [Spring Boot — SQL Database Initialization](https://docs.spring.io/spring-boot/3.5/reference/how-to/data-initialization.html): `schema.sql` and embedded database initialization.
