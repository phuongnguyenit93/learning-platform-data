# Managing Test Data and Cleaning Up Resources After Tests

An integration test can pass when executed alone yet fail when run as part of the full suite. Often the root cause is not an assertion line: leftover rows in a database, uncleaned cache keys, messages from an earlier run, an occupied HTTP port, unremoved temporary files, or an asynchronous worker continuing to mutate data after the test finished. Consequently, **test data preparation** and **resource cleanup** are part of the testing contract, not an afterthought.

This lesson belongs to the **Integration Testing** chapter of **SPRING_BOOT_INTEGRATION**. In Spring Boot systems connecting HTTP clients, databases, caches, message brokers, and Spring Integration adapters, the goal is to construct realistic test state while controlling transactions, failures, duplicate handling, and ensuring tests run repeatably and in parallel in CI with diagnosable failures.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Identify which resources and state each integration test creates or mutates.
2. Choose between **transaction rollback**, **targeted cleanup**, **schema reset**, **isolated resources**, and **disposable environments**.
3. Build reproducible fixtures using SQL, builders/factories, APIs, or migrations with stable identifiers.
4. Explain why **`@Transactional`** on a test cannot revert effects from HTTP servers, message listeners, caches, or external APIs.
5. Use JUnit Jupiter, Spring Test, **`@Sql`**, Testcontainers, and supporting tools to set up and clean up state at the right lifecycle phase.
6. Design tests that avoid parallel collisions, protect shared data, and detect resource leaks after completion.
7. Verify a real integration flow from DB to Redis/brokers, including asynchronous effects and repeatability.

## 2. Identifying the State Boundaries of an Integration Test

Integration tests typically boot an `ApplicationContext`, connect to a real database, access Redis, publish to a broker, and call stubbed services. Each component has distinct lifecycle, ownership, and recovery rules.

~~~mermaid
flowchart TD
    TEST["JUnit integration test"] --> APP["Spring Boot ApplicationContext"]
    TEST --> FIXTURE["Setup test fixtures"]
    APP --> DB[("SQL database")]
    APP --> CACHE[("Redis / cache")]
    APP --> BROKER[("Kafka / RabbitMQ")]
    APP --> HTTP["HTTP mock server / external stub"]
    APP --> FS["Filesystem / SFTP"]
    TEST --> VERIFY["Assert outcomes + no unwanted side effects"]
    VERIFY --> CLEAN["Cleanup / rollback / dispose"]
    CLEAN --> DB
    CLEAN --> CACHE
    CLEAN --> BROKER
    CLEAN --> HTTP
    CLEAN --> FS
~~~

| Resource | Potential leftover state | Common management approach |
|---|---|---|
| **Database** | Rows, sequences, locks, staging tables, outbox/inbox, open transactions | Rollback if same transaction; cleanup by business key; isolated schema/container |
| **Redis/cache** | Keys, TTLs, lock tokens, consumer state, counters | Test-scoped prefixes, tracking created keys, targeted deletion; fallback TTL |
| **Message broker** | Topics/queues, pending messages, offsets, consumer groups, DLQs | Dedicated topics/queues or groups, draining/acking per contract, disposable environments |
| **Mock HTTP** | Stub mappings, request history, response queues, open ports | Reset stubs/history per test; shut down server per suite or test |
| **Files/SFTP/object storage** | Uploaded files, processed files, markers, checksums, directories | Dedicated directory/bucket prefixes; scoped deletion and stream closing |
| **Spring context** | Stateful singleton beans, schedulers, in-memory caches, thread pools | Reset test-owned state, close contexts per lifecycle, `@DirtiesContext` only when truly needed |
| **Docker/Testcontainers infrastructure** | Containers, volumes, networks, service data | Disposable containers; Testcontainers-managed lifecycle; avoid reuse when strict cleanliness is required |

First distinguish **test-owned resources** from **shared resources**. Only the owning test may delete its own resources. Truncating a table or wiping all Redis keys is harmless inside an exclusively owned test database, yet catastrophic if other concurrent tests share that environment.

## 3. Invariants of Reliable Test Data

A trustworthy integration test satisfies these principles:

1. **Repeatable:** running the test twice under identical conditions yields the same business result.
2. **Order-independent:** test B never relies on test A seeding data beforehand or cleaning up afterward.
3. **Isolated:** test A's data is never read accidentally by test B, even under parallel execution.
4. **Owned:** every created row, key, topic, file, or stub has a clear identifier and cleanup scope.
5. **Realistic:** fixtures honor unique constraints, foreign keys, schemas, encodings, versions, and production business rules.
6. **Evidenced:** if setup or cleanup fails, the test fails explicitly—never swallow exceptions to make suites look green.
7. **Recoverable:** JVM crashes, test timeouts, or lost CI agents never permanently poison shared resources.

**The goal is not necessarily "every resource completely empty after each test."** In a suite-exclusive database, static migrations/schemas can stay in place to save time, while changing business rows are cleaned or strictly namespaced. What matters is that the next test observes the declared contract state.

## 4. Choosing an Isolation and Cleanup Strategy

| Strategy | Scope | Strengths | Risks / limitations |
|---|---|---|---|
| **Test transaction rollback** | Data within the same test transaction | Fast, no row-by-row deletion needed | Does not cover other threads/transactions, real HTTP, brokers, Redis, or external side effects |
| **Cleanup by business key / test ID** | Only rows/keys owned by the test | Works on conditionally shared DBs; clear ownership | Must follow FK order and await async workers |
| **`@Sql` setup/teardown** | Predefined SQL fixtures | Readable, reproducible, aligned with Spring Test lifecycle | Scripts must match schema, transaction mode, and scope |
| **Schema reset / truncate** | Entire test schema | Thoroughly clean across many tables | Costly; unsafe on shared environments; affects FKs/sequences |
| **Dedicated schema or DB per test** | Isolated within one DB server | Parallel-friendly, reduces fine-grained cleanup logic | Resource overhead; requires migrations and schema teardown |
| **Disposable container** | Whole service and internal state | Strong environment isolation; closer to real runtime | Slower startup; external non-container resources still need management |
| **TTL-backed namespaces** | Redis keys, object prefixes, queue/topic names | Easy to trace and target for deletion | TTL does not replace active cleanup when checking for leaks |

**Selection rule:** for small single-thread repository tests, rollback usually suffices. For integration tests crossing real HTTP, queues/brokers, or schedulers, treat the test as a multi-transaction workflow: seed with explicit IDs, await side effects, verify, and clean each resource individually.

## 5. Designing Fixtures: Input Data Must Be Meaningful

A fixture is the data and configuration required before the tested action starts. Good fixtures are small yet express critical contracts: parent–child relationships, unique keys, states, versions, timestamps, and failure conditions.

### 5.1. Which Fixture Creation Method Should You Prefer?

| Method | Best fit | Caveats |
|---|---|---|
| **SQL seed scripts / `@Sql`** | Stable DB schema where explicit rows and FKs must be visible | Avoid guessing sequence IDs; pair with matching cleanup |
| **Java factories / builders** | Many business variants differing across test cases | Provide valid defaults; don't hide critical fields behind magic values |
| **Repositories / DAOs** | Testing services or endpoints needing internal state seeded | Decide deliberately whether to bypass or traverse validation/services |
| **HTTP API setup** | Testing strictly through public contracts | Slower with broader side effects; avoid extra API calls if simpler seeding suffices |
| **Snapshots/migrations** | Standard schema with mostly static reference data | Version cleanly; never let tests mutate shared reference rows |
| **Docker init scripts** | Baseline DB/broker/container state | Remember init scripts run once on container/volume init, not before every test |

For instance, an order reconciliation test should create **customer**, **order**, and **order_item** rows with explicit business keys such as **it-order-...**, plus an outbox record if needed. Never copy an anonymized production dump containing thousands of unrelated records; bloated fixtures make tests opaque and create accidental data dependencies.

### 5.2. Test IDs and Namespaces

Generate a unique identifier per test or run:

~~~java
String testRunId = "it-" + java.util.UUID.randomUUID();
String externalOrderId = testRunId + "-order-1";
String redisKey = "it:order:" + testRunId;
~~~

Propagate the same **`testRunId`** across business keys, correlation headers, Redis prefixes, and temporary filenames. On failure, filtering logs by `testRunId` traces the whole flow. Never put per-test UUIDs into metric labels, which explodes cardinality; keep them in logs, traces, and test data.

**Never depend on auto-increment IDs:** two parallel tests cannot both expect the next row to receive `id = 101`. Use unique business keys or capture the DB-generated ID before passing it to subsequent steps.

### 5.3. Defining Clear Before/Action/After State

Example for an integrated order:

~~~text
BEFORE:
  customer: ACTIVE
  order.externalId: it-xxx-order-1
  order.status: NEW
  outbox: no ORDER_CONFIRMED event for this order
  Redis: no cache key for this order
  broker: isolated consumer group ready

ACTION:
  POST /orders/{externalId}/confirm

AFTER:
  order.status = CONFIRMED
  outbox / broker holds exactly one event per business key
  Redis cache invalidated or refreshed per contract
~~~

Writing out **before/action/after** state prevents tests from asserting only HTTP `200` while overlooking critical side effects.

## 6. `@Transactional` in Spring Test: Use at the Right Boundary

Spring TestContext provides **test-managed transactions** when a test carries `@Transactional` and a compatible transaction manager exists. By default, the test transaction rolls back when the method completes—ideal for single-thread repository and synchronous service tests.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Transactional
class OrderRepositoryIT {

    @Autowired OrderRepository orders;

    @Test
    void savesOrderInsideTestTransaction() {
        Order order = orders.save(new Order("it-order-123"));
        assertThat(orders.findByExternalId("it-order-123")).isPresent();
        // By default, the test-managed transaction rolls back.
    }
}
~~~

Here `OrderRepository` and `Order` illustrate application domain types; replace them with your real entities and repositories. This demonstrates rollback within one transaction and does not verify that a real HTTP transaction commits.

### 6.1. Why Rollback Is Not Enough for End-to-End Tests

When `@SpringBootTest(webEnvironment = RANDOM_PORT)` starts a web server and the test makes real HTTP calls, the controller/service handles requests on a different thread from the test thread. The test's transaction **does not wrap** the server's transaction; DB writes on the server commit normally.

The same applies to:

- Async listeners executing on an executor.
- Kafka/RabbitMQ consumers running on consumer threads.
- Schedulers or Spring Integration pollers running independently.
- HTTP calls to external systems.
- Redis or file/object-storage writes outside the test's DB transaction.
- Methods opening independent transactions such as `REQUIRES_NEW`.

**Common anti-pattern:** annotating a test with `@Transactional`, calling `TestRestTemplate.postForEntity(...)`, and believing the server DB rolls back at the end. In reality, endpoint writes persist and break subsequent tests.

### 6.2. `@Rollback` and `@Commit`

`@Rollback(false)` or `@Commit` makes the test-managed transaction commit instead of rolling back. Use them only when the test genuinely needs post-commit checks and has an explicit cleanup plan. Never enable them blindly just because another thread couldn't see uncommitted data without understanding isolation.

JUnit and Spring TestContext callbacks follow strict lifecycle ordering; for transaction-managed tests, **`@BeforeTransaction`** and **`@AfterTransaction`** run outside transaction boundaries when needed. If cleanup must run after commit/rollback, never assume every `@AfterEach` executes outside the test transaction.

### 6.3. When Should You Choose Rollback?

Choose rollback for tests targeting repositories/DAOs or synchronous single-transaction services. When verifying real commits, retries, brokers, HTTP, or polling, prefer real application transactions paired with targeted cleanup or isolated environments.

## 7. Using `@Sql` to Seed and Clean Up Data

Spring Test provides `@Sql` to run SQL scripts before or after test methods. Example for a real HTTP test against PostgreSQL via Testcontainers:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlConfig;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Testcontainers
@Sql(
    scripts = "/sql/order-seed.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD,
    config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED)
)
@Sql(
    scripts = "/sql/order-clean.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
    config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED)
)
class OrderHttpIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    TestRestTemplate http;

    @Test
    void readsSeededOrder() {
        ResponseEntity<String> response =
            http.getForEntity("/orders/it-order-fixture", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).contains("it-order-fixture");
    }
}
~~~

This assumes the app exposes `GET /orders/{externalId}`, owns the orders table, and provides the two SQL scripts under `src/test/resources/sql`; the scripts are illustrated below and **are not created by this lesson**. When implementing, ensure scripts run after Flyway/Liquibase migrations, target the right datasource, and have a compatible transaction manager.

~~~sql
-- /sql/order-seed.sql (illustrative; match table/column names to your real schema)
INSERT INTO customers (id, external_code)
VALUES (910001, 'it-customer-fixture');

INSERT INTO orders (id, customer_id, external_id, status)
VALUES (920001, 910001, 'it-order-fixture', 'NEW');

-- /sql/order-clean.sql: DELETE statements executed after the test
DELETE FROM order_items WHERE order_id = 920001;
DELETE FROM outbox_events WHERE aggregate_id = 'it-order-fixture';
DELETE FROM orders WHERE external_id = 'it-order-fixture';
DELETE FROM customers WHERE external_code = 'it-customer-fixture';
~~~

**Important:** the SQL above is illustrative only and asserts no fixed production schema. Include any related tables per FK constraints. If two test classes share `it-order-fixture` on the same database simultaneously, they collide; here a per-class container isolates classes, yet parallel methods in the same class still require coordination or unique fixtures.

### 7.1. Why Use `TransactionMode.ISOLATED`?

With `@SqlConfig(transactionMode = ISOLATED)`, Spring Test runs scripts in an independent transaction and commits before the test (setup) or after the test (cleanup) when a transaction manager is present. This is essential for tests hitting an HTTP server on another thread: seeded rows must **commit** so the server can read them under normal isolation.

Do not default to `ISOLATED` everywhere. In `@Transactional` repository tests meant to roll back everything, running scripts inside the test transaction is cleaner. Pick transaction modes based on test scope and objectives rather than applying one setting suite-wide.

### 7.2. Limitations of Script Cleanup

- Cannot know dynamic IDs generated by application code at runtime.
- Does not clean up side effects in Redis, brokers, or external APIs.
- Can violate foreign keys if deletes run out of order.
- Cannot stop asynchronous handlers that write rows after the cleanup script finishes.
- Will not execute if the JVM is killed abruptly or a CI agent loses power.

For dynamically generated records, track business keys or use dedicated schemas/containers for safe cleanup. When a cleanup script fails, surface the cleanup error rather than silently treating the test as passed.

## 8. Dynamic Fixtures and Cleanup by Business Key

When tests call endpoints that insert new records, primary keys cannot be predicted ahead of time. Use a test-scoped **`externalId`** to trace and delete all related rows.

~~~java
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderFlowIT {

    @Autowired TestRestTemplate http;
    @Autowired JdbcTemplate jdbc;
    @Autowired StringRedisTemplate redis;

    private String orderKey;

    @BeforeEach
    void prepare() {
        orderKey = "it-" + UUID.randomUUID();
    }

    @Test
    void confirmsOrder() {
        // Assumes an endpoint accepting orderKey.
        http.postForEntity("/orders/" + orderKey + "/confirm",
                null, Void.class);
        // Assert DB/event/cache per contract, not just HTTP status.
    }

    @AfterEach
    void cleanup() {
        // If Redis fails, still attempt DB cleanup; cleanup failures fail the test.
        try {
            redis.delete("order:summary:" + orderKey);
        } finally {
            jdbc.update(
                "DELETE FROM outbox_events WHERE aggregate_id = ?",
                orderKey
            );
            jdbc.update(
                "DELETE FROM order_items WHERE order_id IN "
                + "(SELECT id FROM orders WHERE external_id = ?)",
                orderKey
            );
            jdbc.update(
                "DELETE FROM orders WHERE external_id = ?",
                orderKey
            );
        }
    }
}
~~~

This is a **structural template** to adapt to your application's schema and endpoints; it is not a complete test because assertions are omitted. The `DELETE`s run after the real request; if an async listener is still executing, it may insert rows after cleanup. Always await terminal completion or manage consumer lifecycles before cleaning up.

The `try/finally` ensures DB cleanup still runs if Redis deletion throws. When cleaning multiple independent resources, consider a cleanup utility that executes every step, collects all exceptions, and fails the test with the aggregated causes rather than swallowing cleanup errors.

### 8.1. Do Not Use `TRUNCATE` Recklessly

If the entire database/container **belongs exclusively to that test**, truncating or dropping the schema can be simple and reliable. On a shared database, however, **`TRUNCATE orders CASCADE`** wipes other tests' rows, destroys failure diagnostics, and causes non-reproducible parallel test bugs.

On shared databases, isolate by namespace/schema or delete by business key/tenant; on exclusive schemas, resetting the schema is often cleaner than deleting table by table.

## 9. Testcontainers: Isolating Services and Managing Lifecycles

**Testcontainers** spins up PostgreSQL, Redis, Kafka, RabbitMQ, or other services in containers for integration tests. Real service behaviors and transactions are tested far more faithfully than with in-memory mocks, and containers are discarded afterward.

### 9.1. Typical Lifecycle

~~~mermaid
sequenceDiagram
    participant J as JUnit / Testcontainers
    participant C as PostgreSQL container
    participant S as Spring ApplicationContext
    J->>C: Start container
    C-->>J: JDBC URL, port, credentials
    J->>S: Inject DynamicPropertySource
    S->>C: Run schema migration / connect
    J->>S: Execute tests
    S->>C: Queries + transactions
    J->>S: Close context at lifecycle boundary
    J->>C: Stop container
~~~

A `static @Container` under `@Testcontainers` typically lives for the entire test class; non-static instance containers live per test method. Check lifecycle details for your Testcontainers version and how the framework caches `ApplicationContext` instances. `@DynamicPropertySource` supplies dynamic endpoints/credentials from the container—never hardcode `localhost:5432` when ports are mapped randomly.

Spring Boot 3.1+ supports `@ServiceConnection` with compatible Testcontainers integration modules, replacing manual property registration. Do not configure both mechanisms redundantly for the same connection.

### 9.2. Dedicated Containers Do Not Eliminate All Cleanup

If a suite shares one container across multiple tests that write to it, tests can still interfere with one another. Choose one approach:

- Separate containers per class/test when startup cost is acceptable.
- Separate databases or schemas inside the same container.
- Unique business keys per test paired with targeted cleanup.
- Full schema reset between classes when truly exclusively owned.

Enable container reuse during local development only when you intentionally accept leftover state and run explicit resets. CI must remain reproducible without relying on stale local volumes.

### 9.3. Never Use `@DirtiesContext` as a Substitute for DB Cleanup

`@DirtiesContext` tells Spring TestContext to evict the cached `ApplicationContext` so it is closed and rebuilt as needed. That is valid when a test mutates configuration or unrecoverable singleton state.

However, **`@DirtiesContext` does not delete PostgreSQL rows, Redis keys, broker messages, or files**. Using it as a band-aid for dirty test data slows suites down without fixing state pollution. Reserve it strictly for mutated context state that truly needs rebuilding.

## 10. Redis: Cleaning Up Keys, Locks, and Cache Entries

Redis sits outside the test's SQL transaction. When a test writes `order:summary:it-abc`, test-managed transaction rollback does not delete that key.

Prefer:

1. **Test-specific prefixes:** e.g., `it:<runId>:...` or tracking every created key.
2. **Deleting the exact tracked key list** instead of scanning all of Redis unnecessarily.
3. **Fallback TTLs** on short-lived entries to prevent permanent accumulation if processes crash; TTL never replaces active cleanup.
4. **Dedicated Redis containers** when tests wipe all keys, mutate eviction policies, or test failover.
5. For **distributed locks**, release using the matching ownership token rather than deleting locks held by another worker.

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

import org.junit.jupiter.api.AfterEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.StringRedisTemplate;

class RedisFixtureScope {

    @Autowired StringRedisTemplate redis;

    private final Set<String> keys = new LinkedHashSet<>();

    void putFixture(String key, String value) {
        redis.opsForValue().set(key, value);
        keys.add(key);
    }

    @AfterEach
    void deleteFixtureKeys() {
        if (!keys.isEmpty()) {
            redis.delete(keys);
            keys.clear();
        }
    }
}
~~~

**Example limitation:** this illustrates a scoped helper, not a full test class. Track keys via a registry only if all test keys go through the helper or register themselves; keys generated dynamically by application/consumer code must also be tracked per contract. Record `keys.add(key)` before or inside write-error handling so ambiguous timeout writes are still cleaned up.

Avoid `FLUSHALL`, `FLUSHDB`, or `KEYS *` on shared Redis servers. If prefix scanning is unavoidable, use batched `SCAN` after verifying exclusive ownership of the namespace; note `SCAN` is non-atomic and new keys may appear during cleanup.

## 11. Brokers: Kafka, RabbitMQ, JMS, and Leftover Messages

Integration tests publishing events to brokers can leave unacknowledged messages, retry queue items, dead-letter records, consumer offsets, or subscription state behind. Rebuilding the Spring `ApplicationContext` does not clear broker state.

| Component | Isolation / cleanup approach |
|---|---|
| **Kafka topic** | Create a dedicated topic per test suite when suitable; or use unique event keys/correlation IDs and consumer groups |
| **Kafka consumer group** | Dedicated group IDs to avoid partition contention; control offsets/lag and broker readiness |
| **RabbitMQ queue** | Test-specific queues, optionally `auto-delete`/`exclusive` where appropriate; ensure ACKs complete and queues drain |
| **DLQ / retry topic** | Assert expected items and clean from those destinations too, not just the main queue |
| **JMS destination** | Isolated test queues/topics; close consumers/sessions per lifecycle |
| **Spring Integration adapter** | Stop/close adapters or manage lifecycles cleanly, awaiting in-flight messages before cleaning target stores |

### 11.1. Asynchronous Consumers May Still Be Running When the Test Returns

~~~mermaid
sequenceDiagram
    participant T as Test
    participant B as Broker
    participant C as Consumer
    participant D as Database
    T->>B: Publish event X
    B-->>T: ACK publish
    T->>D: Query state immediately
    D-->>T: Not updated yet
    Note over T,D: Producer ACK does not equal consumer commit
    B->>C: Deliver X
    C->>D: Commit business state
    T->>D: Await eventual expected state
    D-->>T: Updated
~~~

Use bounded waits with **explicit deadlines** such as Awaitility or polling assertions rather than fixed `Thread.sleep(2000)`. In event-driven flows, assert committed business effects, duplicate counts, queue/DLQ states, and that no test-owned consumer work remains pending before cleanup.

Never delete shared queues/topics to tidy up a test. On Testcontainers-managed exclusive brokers, stopping/destroying the container reliably resets suite-level state, while tests must still enforce contract checks while running.

### 11.2. Ensuring Idempotency in Tests

Events can replay during test retries or broker redeliveries. Attach unique `eventId`/business IDs and assert that receiving the same ID twice produces **only one business effect** when required by contract. Never judge correctness by counting exact handler invocations; handlers may execute multiple times while idempotency keeps business outcomes intact.

## 12. HTTP Mocks and External Services

When tests use **WireMock**, **MockWebServer**, mock OAuth servers, or partner stubs, manage three forms of state: response stubs, request journals, and network resources (ports/sockets/threads).

- Scope each test's stubs to explicit URLs, methods, headers, and request bodies; avoid catch-all stubs that mask contract bugs.
- Reset **request journals/history** and **stub mappings** at the right boundary so assertions never inspect requests from prior tests.
- Avoid fixed ports whenever dynamic port allocation is possible; inject base URLs via Spring Boot properties.
- Shut down servers cleanly per lifecycle, closing streams/bodies and custom client connections.
- For HTTP retry tests, assert both request counts and consistent idempotency keys across attempts—not just the final response.

Conceptual lifecycle pattern:

~~~text
@BeforeAll:
  start mock HTTP server (dynamic port)
  configure base URL for the HTTP client under test

@BeforeEach:
  reset request history + stub mappings
  register responses for this specific test scenario

@Test:
  invoke integration flow
  assert request contract, retry count, business result

@AfterAll:
  shut down mock server and release port/threads
~~~

**Note:** in Spring Test, align mock server startup and `@DynamicPropertySource` registration so the server is running before the app resolves its base URL. If using static `@DynamicPropertySource` with a static mock server, manage initialization order carefully rather than assuming `@BeforeAll` always executes before `ApplicationContext` creation in every setup.

## 13. Temporary Files, SFTP, and Object Storage

JUnit Jupiter provides **`@TempDir`** to provision temporary directories per test or declared scope—ideal for file adapters, batch imports, CSV parsers, and file staging.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FileImportIT {

    @TempDir
    Path workDir;

    @Test
    void writesFixtureToOwnedDirectory() throws Exception {
        Path input = workDir.resolve("orders.csv");

        Files.writeString(input,
                "externalId,status\nit-order-1,NEW\n",
                StandardCharsets.UTF_8);

        assertThat(Files.readString(input)).contains("it-order-1");
        // Integration adapter will be configured to read from workDir.
    }
}
~~~

`@TempDir` cleans up directories per JUnit lifecycle; if a child process or adapter still holds an open file handle, deletion can fail depending on the OS. Close streams, stop file watchers/pollers, and wait for processing to finish before test exit.

For SFTP or object storage:

- Create dedicated directories/prefixes keyed by `testRunId`, e.g., `/it/<runId>/inbound/`.
- Write files using production conventions: temporary name then atomic rename, `.done` markers, checksums if used.
- Check `processed`, `archive`, `error`, and marker files for thorough cleanup.
- Never wipe shared root buckets or directories; avoid broad wildcards against live endpoints.
- On eventually consistent object stores, await deletion visibility when subsequent assertions depend on it.

When testing only a CSV parser, you do not need a real SFTP server—`@TempDir` and file fixtures suffice. When testing an SFTP adapter, run a mock or containerized SFTP server to verify handshakes, permissions, file filtering, and reconnects.

## 14. Threads, Schedulers, Connections, and Resource Leaks

A test can clean its data rows yet still leak connections, threads, or sockets:

- An `ExecutorService` created in a test without shutting it down.
- A `ScheduledExecutorService` still polling after the test exits.
- `CloseableHttpClient`, `WebClient` connection pools, or `MockWebServer` left open.
- Manually opened JDBC `ResultSet`/`Statement`/`Connection` not wrapped in `try-with-resources`.
- File watchers, `InputStream`s, or NIO channels holding open handles.
- Active broker consumers consuming messages meant for later tests.

For resources created directly by tests, use **`try-with-resources`** for `AutoCloseable` types, or manage shutdown in `@AfterEach`/`@AfterAll`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;

class BackgroundTaskFixture {

    private ExecutorService executor;

    @BeforeEach
    void setup() {
        executor = Executors.newFixedThreadPool(2);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        executor.shutdown();
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }
}
~~~

This illustrates lifecycle management for test-created executors. For Spring-managed thread pools, let `ApplicationContext` or `Lifecycle`/`SmartLifecycle` manage shutdown; never manually shut down a bean shared across tests that later tests still depend on.

### 14.1. Cleaning Up in Dependency Order

In asynchronous adapter flows, follow this teardown order:

1. Stop submitting new test-owned events or requests.
2. Wait for in-flight test-owned tasks to complete, ACK, or reach a terminal state.
3. Stop test-managed consumers/pollers/adapters if needed to prevent late writes.
4. Assert business outcomes and error/DLQ states per contract.
5. Delete targeted data across brokers, caches, DBs, and files in dependency order.
6. Close HTTP mocks, connections, threads, and containers at their proper scope.

Never wipe the DB before consumers finish: a consumer can re-insert rows after cleanup and pollute the next test.

## 15. Parallel Test Execution and Avoiding "Flaky Tests"

When Maven, Gradle, or JUnit runs tests in parallel, sharing a single database, Redis, or topic without data partitioning produces intermittent failures.

### 15.1. Common Collision Patterns

| Conflict | Symptom | Remediation |
|---|---|---|
| Two tests share a fixed `externalId` | Unique constraint violations or wrong row asserted | Unique IDs, isolated DB/schemas |
| Test A runs `TRUNCATE` while Test B runs | Test B loses its rows | Never truncate shared resources; isolate schemas/containers |
| Two consumers share a group ID | Unexpected partition rebalance; test misses messages | Dedicated groups/topics or coordination |
| Shared mock server request journal | Wrong request counts asserted | Reset per scope or use separate server instances |
| Fixed Redis keys | Stale cache hits from earlier tests | Unique key prefixes and cleanup |
| Scheduler keeps firing | Unexpected rows appear after teardown | Stop/drain jobs or control trigger activation |
| Wall-clock/timezone dependency | TTL expires early, date boundary drift | Inject `Clock`/fake time and pin test timezone |
| Fixed sleeps | Fails on busy CI runners | Await observable conditions with clear deadlines and errors |

### 15.2. When Should Parallelism Be Disabled?

JUnit offers `@ResourceLock` to serialize tests touching shared resources inside the same execution engine, or you can disable parallel execution for specific suites. Still, the more durable design is test-owned namespaces, schemas, or containers so tests remain safe even when CI shards classes across separate JVMs/processes—in-process JUnit locks cannot protect a shared DB from another CI process.

## 16. Secrets and Test Environment Boundaries

Test data should be **synthetic data**. Never use real PII, production credentials, API tokens, or unsanitized production dumps. Key safeguards:

- Test passwords/tokens must be scoped strictly to test environments and fetched from secret management if needed; never commit real secrets to source control.
- External client endpoints must target controlled stubs/sandboxes; tests must never place real orders, email real customers, or transfer real funds.
- For PII-like fields, use fake values and mask them in logs and metrics.
- Before destructive cleanup, verify a **test environment marker** or explicit allowlist; `DROP SCHEMA` or `FLUSHALL` must run only against verified exclusive test environments.
- Never build fixtures by pulling live sensitive production data without formal sanitization and approval.

Environment misconfiguration is one of the deadliest risks in automated cleanup: a single wrong hostname can execute valid cleanup statements against the wrong system.

## 17. Testing the Cleanup Process Itself, Not Only Business Logic

A test can pass when leftover data happens to be harmless, then start failing the next night across the suite. Verify cleanup quality as an invariant:

1. Run the same test class at least twice against a reusable environment.
2. Permute test method execution order or run individual methods alone.
3. Query counts of test-owned rows/keys/files by `testRunId` before and after cleanup.
4. If tests emit async messages, await completion or DLQ routing before running cleanup.
5. Inject mid-flow faults—API timeouts, listener crashes, DB rollbacks, container restarts—and confirm no duplicate/orphaned resources remain.
6. Run a batch of parallel tests under CI-like resource sharing.
7. When cleanup fails, mark the test `FAILED` and print the remaining resource identifiers for diagnosis.

### 17.1. A Post-Teardown Verification Check

~~~text
Resource scope: testRunId = it-27ac...
DB:
  orders with external_id prefix: 0
  outbox_events for testRunId: 0
Redis:
  keys explicitly registered by test: 0
Broker:
  pending messages/consumer state for testRunId: resolved
Filesystem:
  files under owned prefix: 0
HTTP mock:
  server closed or reset within documented scope

If any check fails:
  report FAILED (cleanup/teardown),
  log resource name + testRunId + root cause,
  never swallow exceptions.
~~~

Eventually consistent systems need a finite **deadline** to verify terminal state rather than checking immediately and misreporting slow commits as bugs. Conversely, waiting forever "just in case it finishes" stalls CI.

## 18. Synthesis Scenario: HTTP → DB → Outbox → Broker → Redis

A Spring Boot endpoint accepts order creation, saves to DB and outbox, and a publisher emits events to a broker. A consumer updates a Redis cache. The integration test must verify the contract and leave zero leftover state afterward.

~~~mermaid
flowchart TD
    FIX["Test fixture: customer + testRunId"] --> HTTP["POST /orders"]
    HTTP --> TX["DB transaction: order + outbox"]
    TX --> PUB["Outbox publisher"]
    PUB --> BROKER[("Broker test topic / queue")]
    BROKER --> CONS["Idempotent consumer"]
    CONS --> REDIS[("Redis test key")]
    TEST["JUnit assertions"] -.-> TX
    TEST -.-> BROKER
    TEST -.-> REDIS
    TEST --> DRAIN["Await completion / stop test work"]
    DRAIN --> CLEAN["Cleanup by testRunId"]
    CLEAN --> TX
    CLEAN --> REDIS
    CLEAN --> BROKER
~~~

**Test design:**

1. **Setup:** generate unique customer and `testRunId`; start PostgreSQL, Redis, and broker test containers (or equivalent isolated environment); inject test endpoints/credentials via properties.
2. **Action:** send HTTP `POST` with unique **idempotency key** and **`externalOrderId`**.
3. **Synchronous assertions:** verify HTTP status per contract, committed order row, and outbox row—never rely on test-level `@Transactional` to roll back real HTTP work.
4. **Asynchronous assertions:** await consumer processing within a timeout; verify event ID, business effect count, cache key/value, outbox state, and DLQ state.
5. **Duplicate check:** resend with the same idempotency key to confirm no duplicate order or duplicate events are emitted outside contract.
6. **Teardown:** stop test producers/consumers if needed, await completion, delete Redis keys and DB rows by business key, and dispose dedicated topics/queues or test containers.
7. **Post-cleanup check:** verify zero test-owned resources remain; on leftover state, fail with the ID for troubleshooting.

**Real-world trap:** if cleanup deletes outbox rows right after HTTP `201` before the publisher reads them, the HTTP assertions pass while the messaging assertions fail—or the publisher processes late and recreates messages/Redis keys after cleanup. Ordering **await completion → verify → cleanup** is essential to correctness.

## 19. Pre-CI Integration Test Checklist

- [ ] Every test declares its input data, expected state, and side-effecting resources.
- [ ] Fixtures use unique keys, honor schemas/FKs, and are reproducible.
- [ ] Rollback, targeted cleanup, schema reset, or disposable containers match resource scope.
- [ ] Tests never assume `@Transactional` rolls back HTTP requests, async listeners, or Redis/brokers.
- [ ] `@Sql` setup/cleanup uses the right transaction mode and FK deletion order.
- [ ] Testcontainers/connection properties align lifecycles with `ApplicationContext` and avoid hardcoded ports.
- [ ] Redis keys, broker groups/topics/queues, file prefixes, and mock servers are owned and cleaned by their test.
- [ ] Never run `FLUSHALL`, `TRUNCATE CASCADE`, or broad wildcards on shared resources.
- [ ] Consumers/pollers/schedulers are drained or stopped before cleanup to prevent late writes.
- [ ] Tests cover idempotency keys and duplicate HTTP/message delivery where needed.
- [ ] Async tests await conditions with bounded deadlines rather than fixed sleeps.
- [ ] Cleanup failures fail the test and log leftover resource diagnostics.
- [ ] Tests pass standalone, repeatedly, in shuffled order, and in parallel within declared limits.
- [ ] Test data is synthetic, free of production secrets or dangerous endpoints.

**Key takeaway:** integration tests are only trustworthy when **pre-test state is controlled**, **integration flow effects are verified**, and **post-test resources do not corrupt subsequent runs**. In Spring Boot, transactions, caches, brokers, files, and adapters each have distinct boundaries; your cleanup strategy must respect every one of those boundaries so test results remain reproducible and reliable.
