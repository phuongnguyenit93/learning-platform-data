# Detecting Order-Dependent Tests or Leftover Data

A Spring Boot test can **PASS when run alone yet FAIL in the full suite**, **PASS locally yet be flaky on CI**, or change outcome whenever JUnit executes tests in a different order. Usually the cause is not broken assertion syntax, but **one test depending on state left behind by another**: leftover DB rows, an unreset Spring singleton bean, a static collection, a system property, a temp file, a mock stubbing, an unconsumed message, a clock, or an unfinished asynchronous task.

This lesson covers **"Detecting Order-Dependent Tests or Leftover Data"**, under **Isolation and Parallel Execution** in **Spring Boot - testing**. The goal is not just getting green builds, but **proving tests are independent, reproducible, repeatable, and harmless to other tests' data**. It covers symptoms, leak mechanisms, reproducible detection with JUnit 5/Jupiter, distinguishing randomized order from concurrency, setup/teardown strategies, Spring TestContext caching, `@Transactional`/`@DirtiesContext`, cases where `REQUIRES_NEW` or worker threads escape rollback, and a **Java 17 + Spring Boot 3.5 + H2 JDBC + JUnit Jupiter** runnable project.

> **Foundational rule:** a test must establish all its own preconditions, assert only on data under its own control, and clean up side effects within its own scope. Forcing tests green with `@Order` does **not** fix order dependence.

## 1. Recognizing Symptoms of Order-Dependent Tests

### 1.1. Common Symptoms

- `mvn -Dtest=OrderServiceTest test` PASSES, while `mvn test` FAILS.
- Test A PASSES when run before B yet FAILS when run after B.
- The first run PASSES, while re-running in the same JVM or CI worker FAILS due to leftover file/table/Redis key data.
- Under parallel execution, `count(*)` fluctuates unpredictably even though the test inserts only one record.
- An assertion expects one email/message yet receives two because the previous test did not reset a fake collector.
- A test inserts a fixed row ID `"order-1"` and the next run hits a duplicate-key error.
- A `@Transactional` test assumes the DB rolls back automatically, yet the service uses `REQUIRES_NEW` or an `@Async` task commits on another transaction.
- Tests use `@TestInstance(PER_CLASS)` or a `static List`, letting state survive across multiple test methods.
- After a test fails, `@AfterEach` fails to clean up resources properly, leaving dirty state for the next test.
- A test calls `@DirtiesContext` or mutates global configuration, causing parallel tests to lose their context/beans unpredictably.

A single successful run **does not prove** test independence: the test may simply have gotten lucky with execution order. A failure under parallel mode **does not prove** JUnit has a bug: shared state or races usually exist in the code or test fixtures.

### 1.2. Distinguishing Concepts

| Failure Type | Sign | Example |
|---|---|---|
| **Order dependency** | Changing test order changes outcomes | B only PASSES if A already inserted a fixture |
| **Residue/leaked state** | Subsequent test sees prior test's data | Leftover row in table, undeleted file |
| **Race condition** | Concurrent runs change outcomes | Two tests wiping/inserting into the same table concurrently |
| **Timing flakiness** | Test asserts before async work finishes | Listener hasn't appended to collector yet |
| **Environment dependence** | Test relies on timezone, locale, port, secrets, real DB | Test behaves differently across machines/CI |
| **Context cache contamination** | Spring singleton bean reused with mutated state | Service map/cache not reset |
| **Transaction boundary mismatch** | Test rollback misses other side effects | `REQUIRES_NEW`, other threads, HTTP server |
| **Nondeterministic fixture** | Randomness/time used uncontrolled | Data lacking seeds/correlation IDs |

Diagnose **evidence and scope** before fixing. If the bug is a leftover DB row, changing `@TestMethodOrder` will not help; if the bug is asserting before an async consumer finishes, adding sleep guarantees no stability.

## 2. Minimal Example: Two Tests Depending on the Same Table

A **broken** test sample (snippet for analysis, **not part of the runnable suite**):

```java
@SpringBootTest
class BadOrderTests {
    @Autowired JdbcTemplate jdbc;

    @Test
    void a_createsOrder() {
        jdbc.update(
            "INSERT INTO demo_order(order_id, run_key, order_state, quantity)"
            + " VALUES ('fixed-id', 'shared', 'NEW', 1)");
        assertEquals(1L,
            jdbc.queryForObject(
                "SELECT COUNT(*) FROM demo_order",
                Long.class));
    }

    @Test
    void b_expectsEmptyDatabase() {
        assertEquals(0L,
            jdbc.queryForObject(
                "SELECT COUNT(*) FROM demo_order",
                Long.class));
    }
}
```

In a shared DB:
- If `b_expectsEmptyDatabase` runs **before** A, it may PASS.
- If B runs **after** A, it typically FAILS because A did not clean up.
- If a test C inserts another row concurrently, even A can FAIL on `COUNT(*)==1`.
- On a second run against a non-reset DB, A fails because `fixed-id` already exists.

You cannot cure this by putting `@Order(1)` on B and `@Order(2)` on A: that only **hides** the dependency and still leaves data residue after the suite. The proper fix is **scoping data by test ID, querying within that scope, and cleaning up/rolling back**.

Transformed example:

```java
String runKey = "run-" + UUID.randomUUID();
String orderId = "ord-" + UUID.randomUUID();

try {
    jdbc.update("""
        INSERT INTO demo_order
          (order_id, run_key, order_state, quantity)
        VALUES (?, ?, ?, ?)
        """, orderId, runKey, "NEW", 1);

    Long actual = jdbc.queryForObject("""
        SELECT COUNT(*) FROM demo_order WHERE run_key = ?
        """, Long.class, runKey);

    assertEquals(1L, actual);
} finally {
    jdbc.update(
        "DELETE FROM demo_order WHERE run_key = ?", runKey);
}
```

This snippet requires `JdbcTemplate`, `UUID`, and the project schema below. It illustrates **ownership**: Test A counts and deletes only its own rows; Test B uses a different `runKey` and is unaffected. `UUID` prevents ID collisions, yet **random IDs do not replace cleanup**: leaving a new row on every run causes unbounded DB growth.

## 3. Detecting Order Dependence with JUnit Jupiter

### 3.1. JUnit Does Not Promise Name-Based Default Ordering

JUnit Jupiter defaults to an ordering that is **deterministic yet intentionally non-obvious**; never assume `testA` runs before `testB`. `@TestMethodOrder(MethodOrderer.OrderAnnotation.class)` and `@Order` can sequence genuine multi-step workflow scenarios, yet using them to mask uncleaned data leaves tests non-independent.

```java
@TestMethodOrder(MethodOrderer.Random.class)
class IndependenceTest {
    @Test
    void createWithoutAssumingOtherTestsRan() {
        // seed own fixture
    }

    @Test
    void queryWithoutAssumingOtherTestsHaveNotRun() {
        // query only test-owned data
    }
}
```

This is an illustrative snippet; the runnable project contains concrete test classes. `MethodOrderer.Random` shuffles **methods within a class** using a reproducible seed. To shuffle **test class order**, use `ClassOrderer.Random` in JUnit Platform. These are two separate mechanisms: shuffling methods does not shuffle classes.

### 3.2. Pinning Seeds for Reproduction

`src/test/resources/junit-platform.properties` can contain:

```properties
junit.jupiter.execution.order.random.seed=4232026
junit.jupiter.testclass.order.default=org.junit.jupiter.api.ClassOrderer$Random
```

A seed **is not a bug fix**; it is a **schedule reproduction key**. To uncover order-dependent tests, run the suite across **multiple seeds**, save any failing seed in bug reports/CI logs, and fix the fixture/cleanup. Passing with one seed does not prove all permutations pass.

Maven command examples:

```bash
mvn test -Djunit.jupiter.execution.order.random.seed=41
mvn test -Djunit.jupiter.execution.order.random.seed=97
mvn test -Djunit.jupiter.execution.order.random.seed=4232026
```

`-D` forwards appropriate system/user properties to JUnit Platform under a compatible Maven Surefire setup. If a custom build passes JUnit config differently, verify the seed actually reaches the test runtime before trusting it as evidence.

**Never guess the culprit solely from the test immediately preceding a failure:** Test A may pollute an external DB and cause Tests B, C, and D to fail. Locate the **polluter** and the **victim**; they do not have to be adjacent.

### 3.3. Running Individual Tests, Classes, and Full Suites

A useful workflow:

1. Run the suspected Test B **alone**.
2. Run A alone and then B alone in **two separate processes**; if an external DB retains rows, B can still be affected.
3. Run A and B **in the same JVM** in both orders to test static/Spring context state.
4. Run the **entire suite with a logged seed** to catch other polluters.
5. Run repeatedly under **CI-like concurrency** against a data store reset like the production test environment.
6. After fixing, add regression assertions for **clean state before and after** the scenario rather than checking only the happy path.

With Maven Surefire, `-Dtest=...` selects classes or methods (syntax depends on plugin version), yet each `mvn test` command usually starts a fresh test process. That isolates processes, yet can **hide static state leaks** that manifest only when two classes share one JVM.

### 3.4. Testing Ordering Is Not Testing Concurrency

Sequential random method ordering catches A dirtying state for B. Yet two methods writing to the same table concurrently require **concurrent stress testing**, locking, or data isolation. Avoid flipping on random ordering and full parallelism simultaneously at first, as it obscures root causes.

Spring Framework 6.2 warns against arbitrarily parallelizing tests with `@DirtiesContext`, shared external systems, mutable mocks, or test-order coordination. The demo project separates:
- A suite demonstrating **order shuffling** sequentially.
- A suite **deliberately opting into parallel execution** using only unique run keys and scoped cleanup.

With real production DBs, even when IDs differ, shared sequences, locks, quotas, truncates, broker offsets, or global caches can remain; audit them before enabling parallelism.

## 4. Detecting Residue Before Running Assertions

Add a scoped **baseline** check in setup:

```java
@BeforeEach
void begin() {
    runKey = "run-" + UUID.randomUUID();
    assertThat(store.countByRunKey(runKey)).isZero();
}
```

When using a fixed `runKey` from CI/build metadata, baseline checks catch missed prior cleanup. When generating a fresh UUID per test, the baseline confirms no accidental fixture collision within that scope, yet **does not prove the whole database has zero leftover rows**; therefore add environment-level **janitor/TTL/cleanup audits** to detect global residue. These are two distinct goals:
- **Test isolation:** each test touches only its own rows; queries and cleanups are scoped.
- **Environment hygiene:** after a suite ends, no fixtures with test prefixes/tags linger, or every fixture carries a TTL; check total test-namespaced rows when no tests are running.

Never assert `SELECT COUNT(*) FROM demo_order = 0` at the start of every test if other tests can write concurrently. A global count cannot distinguish other tests' rows, schema seed data, or baseline data.

### Using a Correlation/Test-Run ID

For example, a schema with `order_id` and `run_key`:

```sql
SELECT COUNT(*) FROM demo_order WHERE run_key = ?;
DELETE FROM demo_order WHERE run_key = ?;
```

`run_key` belongs to each test invocation, not "one key for the entire test suite" when tests run in parallel. With `@RepeatedTest`, **each repetition** also needs a fresh run key. If CI retries a flaky test, each retry must clean up prior rows and use a traceable ID for investigation.

### Scoped Cleanup

- **Prefer deleting by run key/owner**, never unconditional `DELETE FROM demo_order` or `TRUNCATE` in a parallel suite.
- Place cleanup in `@AfterEach` for each test invocation, or in `finally` right around blocks creating extra side effects.
- If a test opens and rolls back a transaction, check whether application code uses a **different transaction**.
- If cleanup fails, let the cleanup error **fail the test** instead of silently logging and ignoring it.
- Data committed by background threads/outboxes/brokers may need cleanup outside the test transaction.

## 5. Sources of Order Dependence Outside JDBC

| Shared State | Failure Example | How to Detect and Isolate |
|---|---|---|
| `static Map`, static counter | Test A increments, Test B expects 0 | Reproduce in same JVM, reset/eliminate global mutable state |
| Spring singleton | Bean with mutable `List`/`AtomicInteger` | Intentional reset, never assume new context per test |
| Mockito mock/spy | Stubbing/interactions left from prior test | Framework mock reset/`Mockito.reset` at proper lifecycle |
| Database/JPA | Committed inserts, `REQUIRES_NEW`, sequences | Scoped keys, rollback + cleanup, DB queries |
| Redis/cache | Keys surviving past test | Run-scoped prefix, TTL, delete own keys |
| Kafka/RabbitMQ | Remaining consumer group/offsets, duplicate events | Unique topic/group/ID, acks and bounded waits |
| Files/temp directories | Unremoved fixed file `/tmp/report.csv` | JUnit `@TempDir`, cleanup, unique paths |
| OS processes/ports | Fixed port already bound | Ephemeral ports or resource locks |
| System properties | Test changes `user.timezone` without restoring | Save old value and restore in `finally`, `@ResourceLock` |
| Locale/timezone/Clock | Test relies on current time/date | `Clock.fixed`, explicit `ZoneId`/`Locale` |
| `ThreadLocal`/`SecurityContext` | Context left uncleared on reused async thread | Security listener/clear in `finally`, context propagation |
| Executors/schedulers | Task keeps running/writing after test ends | Await terminal stage, proper shutdown/cancel |
| HTTP mock servers | Stubs/calls left from previous test | Reset stubs + request journal per test |
| Testcontainers | Reused DB/container, changed ports | Align lifecycles, clean schemas/test data |
| Browser cookies/`localStorage` | Leftover login session/cookies | Dedicated browser context and logout/clear state |
| Dynamic properties | Supplier/container port changes while context cache reuses | `@DirtiesContext` if needed, or suite-scoped container |

**Context caching is not data cleanup.** Even if Spring TestContext recreates a fresh context, an external PostgreSQL/Redis service retains its data. Conversely, a fresh context is unnecessary when singletons are properly reset and DB fixtures have transaction isolation.

## 6. `@Transactional` and Rollback Limits in Spring TestContext

In Spring Framework, when a test is annotated `@Transactional` with an active transaction manager, `TransactionalTestExecutionListener` starts a **test-managed transaction** and normally **rolls it back at the end of the test**. This works well for JDBC/JPA operations on the **same thread and transaction**.

However, rollback does not automatically cover:

1. **`@Transactional(propagation=REQUIRES_NEW)`** on a service bean: this method deliberately starts a new transaction and can **commit independently** of the outer transaction.
2. **`@Async` or separate worker threads**: transaction context is typically thread-bound; tasks on other threads can commit outside the test transaction.
3. **Real HTTP via `RANDOM_PORT`**: the server handles requests on another thread with its own transaction; test `@Transactional` does not roll back server requests.
4. **`assertTimeoutPreemptively`**: JUnit executes the executable on a different thread, escaping the `ThreadLocal`-bound test-managed transaction. Spring docs explicitly warn about this.
5. **External DBs/brokers**: writes to Kafka, Redis, or S3 do not roll back with a JDBC transaction without specialized coordination.
6. **Intentional commits**: `@Commit`, `@Rollback(false)`, or `TestTransaction.flagForCommit()` override the default rollback.

```text
JUnit test thread          Spring service with REQUIRED
   |                               |
   +-- test transaction ---------> joins transaction
   |                               |
   +-- test ends/rollback ---------+ -> uncommitted row rolled back

JUnit test thread          Service with REQUIRES_NEW
   |                               |
   +-- test transaction --> suspended
   |                               |
   +-- REQUIRES_NEW tx --> commits independently
   |
   +-- test rollback -> does NOT undo the new transaction

JUnit test thread          @Async worker
   |                               |
   +-- test transaction --> does NOT propagate ThreadLocal
   |                               |
   +-- async worker --> can commit independently
```

With `@JdbcTest` or `@DataJpaTest`, test slices enable transactional rollback by default; however, full `@SpringBootTest` tests are **not transactional** unless annotated with `@Transactional`. In the runnable project, the parallel integration test **omits `@Transactional`** so inserts/commits are explicit and cleaned up by run key. A separate test uses `TestTransaction` to observe rollback and includes a `REQUIRES_NEW` test to prove the boundary.

**Do not treat `@Transactional` as magic residue prevention**: verify the transaction manager, calling thread, propagation, DB connections, async tasks, and whether the final operation committed. Inside a `@Transactional` test, `@BeforeEach`/`@AfterEach` run inside the test transaction; a cleanup `DELETE` in `@AfterEach` may itself get rolled back, failing to delete rows committed via `REQUIRES_NEW`.

## 7. Is `@DirtiesContext` a Way to Clear Leftover Data?

`@DirtiesContext` instructs Spring TestContext to evict the `ApplicationContext` from its static cache and recreate it when needed. This can reset mutable Spring singletons, mocks, and context-level registries; however:

- It does not delete **committed** rows in an external DB.
- It does not roll back sent messages, written files, or remote API calls.
- It does not clear static state living outside the Spring bean lifecycle.
- It **slows down** the suite by restarting contexts; with many beans/auto-configurations, the cost is substantial.
- Spring Framework 6.2 warns against running `@DirtiesContext` in parallel when another thread closes the active context.
- It does not fix Test B depending on Test A; tests must still set up their own fixtures.

Use `@DirtiesContext` only when a test truly **corrupts configuration/bean state** that cannot be reset safely. When the cause is a DB row, prefer transactions or ID-based cleanup. If a singleton bean holds an internal cache, consider a test clear/reset API or proper invalidation policy instead of forcing every test to rebuild the context.

## 8. Parallel Execution: Enable Intentionally and Define Resource Ownership

### 8.1. Enabling JUnit Parallelism Does Not Automatically Run Tests in Parallel

In `junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=same_thread
```

Here, the parallel engine is **enabled**, yet default modes remain **`SAME_THREAD`**. Only test classes explicitly designed to be safe opt in via `@Execution(ExecutionMode.CONCURRENT)`. Never flip every test to `concurrent` hoping they magically handle shared state.

Per Spring Framework 6.2 guidance, avoid arbitrarily parallelizing tests that use `@DirtiesContext`, Mockito bean overrides/spy beans, execution-order dependencies, or shared database/broker/filesystem mutations. In this educational example, the parallel JDBC suite **modifies only rows tagged with its own `runKey`, with no truncates/global clears**, intentionally demonstrating a minimal ownership boundary. In production DBs with shared locks, sequences, brokers, or global counters, evaluate thoroughly and serialize if needed.

### 8.2. `@ResourceLock` for Global Resources

Illustrative snippet:

```java
@Execution(ExecutionMode.CONCURRENT)
class SystemPropertyTests {

    @Test
    @ResourceLock(
        value = "global-system-properties",
        mode = ResourceAccessMode.READ_WRITE)
    void changesProperty() {
        String before = System.getProperty("demo.flag");
        try {
            System.setProperty("demo.flag", "on");
            // assertions here
        } finally {
            if (before == null) {
                System.clearProperty("demo.flag");
            } else {
                System.setProperty("demo.flag", before);
            }
        }
    }
}
```

This snippet requires JUnit imports; it is not part of the runnable demo. `@ResourceLock` **coordinates only among tests declaring the same lock name**; it does not make System properties thread-local and does not prevent code outside JUnit from touching the resource. For tests altering shared global environments, running sequentially or in an isolated JVM is often simpler.

### 8.3. `@Isolated`, `@TestInstance`, and Ordering

- JUnit Jupiter's `@Isolated` runs a class separately from other tests in the same engine when protecting shared state.
- `@TestInstance(PER_METHOD)` (default) creates a **new test instance per test method/invocation**; it does not reset Spring singletons or DBs.
- `@TestInstance(PER_CLASS)` reuses **one instance** across methods; mutable instance fields can leak and require concurrency handling.
- `@TestMethodOrder(OrderAnnotation.class)` fits **intentional workflow tests** where steps truly depend on prior state, not general unit/integration tests.
- `@RepeatedTest` executes a method multiple times; each repetition must be independent, assuming neither presence nor absence of prior-run data.
- `@TestFactory` dynamic tests have a different lifecycle from `@Test`: `@BeforeEach`/`@AfterEach` wrap the factory method, not **each dynamic child**. Handle fixtures/cleanup inside each dynamic executable if needed.
- A JUnit random seed reproduces ordering, yet **parallel scheduling** remains nondeterministic even with the same seed; log execution start/end and resource ownership as well.

## 9. Runnable Project: Java 17 + Spring Boot 3.5 + H2

The demo contains:

- `IsolationDemoApplication`: bootstraps Spring Boot without a web server.
- `demo_order` H2 table: rows with `order_id`, `run_key`, `order_state`, and `quantity`.
- `OrderStore`: JDBC repository for insert/find/count/update/delete **scoped by run key**.
- `OrderService`: business service generating new order IDs and validating quantity.
- `CommittedWriter`: service illustrating `REQUIRES_NEW` commits surviving an outer transaction rollback.
- `OrderSensitivitySimulationTest`: unit tests deterministically simulating order-sensitivity bugs and their fixes.
- `ParallelJdbcIsolationTest`: integration tests with `@Execution(CONCURRENT)`, unique run keys, `@AfterEach` cleanup, and a repeated test.
- `TransactionBoundaryTest`: explicit rollback, test-managed transactions, `REQUIRES_NEW`, and exception-triggered rollback.
- `junit-platform.properties`: random class ordering with a fixed seed, sequential defaults, and opt-in concurrency.

**The anti-patterns from earlier sections are excluded from the runnable suite**, so the project is expected to PASS while still **demonstrating the bug** via a simulation test asserting the exact expected failure prior to fixing.

### 9.1. Directory Tree

```text
test-isolation-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/isolation/
    │   │   ├── IsolationDemoApplication.java
    │   │   ├── OrderRow.java
    │   │   ├── OrderStore.java
    │   │   ├── OrderService.java
    │   │   └── CommittedWriter.java
    │   └── resources/
    │       └── schema.sql
    └── test/
        ├── java/com/example/isolation/
        │   ├── OrderSensitivitySimulationTest.java
        │   ├── ParallelJdbcIsolationTest.java
        │   └── TransactionBoundaryTest.java
        └── resources/
            └── junit-platform.properties
```

### 9.2. Maven `pom.xml`

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
    <artifactId>test-isolation-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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

`spring-boot-starter-jdbc` provides `JdbcTemplate`/DataSource/transaction manager; H2 is the embedded database; `spring-boot-starter-aop` enables proxy interception for service `@Transactional`; `spring-boot-starter-test` supplies JUnit Jupiter and AssertJ. Boot 3.5 parent manages compatible versions. No Docker or HTTP server is needed.

### 9.3. Main Spring Boot Application

File **`src/main/java/com/example/isolation/IsolationDemoApplication.java`**:

```java
package com.example.isolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IsolationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(IsolationDemoApplication.class, args);
    }
}
```

`@SpringBootTest(webEnvironment=NONE)` in integration tests creates only the context and H2 DataSource without opening a servlet port. Beans in the same package are component-scanned.

### 9.4. SQL Schema: Embedded H2

File **`src/main/resources/schema.sql`**:

```sql
CREATE TABLE IF NOT EXISTS demo_order (
    order_id VARCHAR(80) NOT NULL PRIMARY KEY,
    run_key VARCHAR(80) NOT NULL,
    order_state VARCHAR(24) NOT NULL,
    quantity INT NOT NULL
);

CREATE INDEX idx_demo_order_run_key
    ON demo_order(run_key);
```

Spring Boot executes `schema.sql` by default when initializing an embedded H2 DataSource. Use a single schema initialization mechanism; if a real project already uses Flyway/Liquibase, **do not arbitrarily mix** it with default `schema.sql`. No `data.sql` is needed: every test seeds its own data.

**Purpose of `run_key`:** a DB context can be cached/shared across tests; all cleanup scoped by `run_key` stays local. `order_id` is also UUID-unique, preventing duplicate keys even in parallel runs.

### 9.5. Value Object

File **`src/main/java/com/example/isolation/OrderRow.java`**:

```java
package com.example.isolation;

public record OrderRow(
        String orderId,
        String runKey,
        String state,
        int quantity) {
}
```

A Java 17 record provides deterministic equality and accessors, letting tests assert whole objects. This is a demo row DTO, not a JPA entity; JDBC mapping is explicit.

### 9.6. JDBC Store Querying and Cleaning Up by Run Key

File **`src/main/java/com/example/isolation/OrderStore.java`**:

```java
package com.example.isolation;

import java.util.Objects;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderStore {

    private final JdbcTemplate jdbc;

    public OrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(
            String orderId, String runKey,
            String state, int quantity) {

        jdbc.update("""
                INSERT INTO demo_order
                    (order_id, run_key, order_state, quantity)
                VALUES (?, ?, ?, ?)
                """, orderId, runKey, state, quantity);
    }

    public Optional<OrderRow> find(
            String runKey, String orderId) {

        return jdbc.query("""
                SELECT order_id, run_key, order_state, quantity
                FROM demo_order
                WHERE run_key = ? AND order_id = ?
                """,
                (rs, index) -> new OrderRow(
                        rs.getString("order_id"),
                        rs.getString("run_key"),
                        rs.getString("order_state"),
                        rs.getInt("quantity")),
                runKey, orderId)
                .stream()
                .findFirst();
    }

    public long countByRunKey(String runKey) {
        Long count = jdbc.queryForObject("""
                SELECT COUNT(*) FROM demo_order
                WHERE run_key = ?
                """, Long.class, runKey);
        return Objects.requireNonNull(count);
    }

    public int updateState(
            String runKey, String orderId, String state) {

        return jdbc.update("""
                UPDATE demo_order SET order_state = ?
                WHERE run_key = ? AND order_id = ?
                """, state, runKey, orderId);
    }

    public int deleteByRunKey(String runKey) {
        return jdbc.update("""
                DELETE FROM demo_order WHERE run_key = ?
                """, runKey);
    }
}
```

**No `DELETE FROM demo_order` without a `WHERE` clause.** Tests cannot wipe another test's rows. `find` also scopes by `run_key` so it cannot accidentally read an order with the same business ID in another data model. In production multi-tenancy, always enforce tenant keys/authorization in SQL; `run_key` here is test fixture ownership, not a real security boundary.

### 9.7. Service Generating Unique IDs and Validating Input

File **`src/main/java/com/example/isolation/OrderService.java`**:

```java
package com.example.isolation;

import java.util.UUID;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderStore store;

    public OrderService(OrderStore store) {
        this.store = store;
    }

    public String place(String runKey, int quantity) {
        if (runKey == null || runKey.isBlank()) {
            throw new IllegalArgumentException(
                    "runKey must be non-blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }

        String orderId = "ord-" + UUID.randomUUID();
        store.insert(orderId, runKey, "NEW", quantity);
        return orderId;
    }
}
```

Tests verify the returned ID by reading the corresponding row rather than expecting a fixed UUID across invocations. `UUID.randomUUID()` is not automatically a business idempotency key. Real systems may use an injectable ID generator or client-supplied idempotency key; this lesson uses UUID solely to prevent demo collisions.

### 9.8. Service Opening a New Transaction

File **`src/main/java/com/example/isolation/CommittedWriter.java`**:

```java
package com.example.isolation;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CommittedWriter {

    private final OrderStore store;

    public CommittedWriter(OrderStore store) {
        this.store = store;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void insertCommitted(
            String runKey, String orderId) {

        store.insert(orderId, runKey, "NEW", 1);
    }
}
```

Calls go through the **Spring-managed bean proxy**, so `REQUIRES_NEW` starts a fresh transaction independent of the caller's transaction. Once committed, rolling back the caller's transaction does not delete the row. The test highlights this and cleans up the row in `finally` to leave zero residue. This is not a recommendation to put `REQUIRES_NEW` on every business method.

### 9.9. JUnit Platform Configuration

File **`src/test/resources/junit-platform.properties`**:

```properties
# Shuffle test class order reproducibly with this seed.
junit.jupiter.testclass.order.default=org.junit.jupiter.api.ClassOrderer$Random
junit.jupiter.execution.order.random.seed=4232026

# Enable parallel engine while keeping sequential defaults.
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=same_thread

# Only classes with @Execution(CONCURRENT) opt into parallelism.
```

`OrderSensitivitySimulationTest` below uses `@TestMethodOrder(MethodOrderer.Random.class)`, so its methods are also shuffled by the seed. `ParallelJdbcIsolationTest` omits `@TestMethodOrder` and opts into `@Execution(CONCURRENT)`. This is intentional: Spring warns against mixing test-order coordination with arbitrary parallel execution.

Seeds aid reproducibility, not OS/thread scheduling when execution is concurrent. When CI uses different JVM forks, static context caches and DB lifecycles can differ; record seed, versions, forks, and test selection in flaky failure reports.

### 9.10. Unit Tests: Safely Simulating an Order-Dependency Bug

File **`src/test/java/com/example/isolation/OrderSensitivitySimulationTest.java`**:

```java
package com.example.isolation;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;

import static org.assertj.core.api.Assertions.assertThat;

@TestMethodOrder(MethodOrderer.Random.class)
class OrderSensitivitySimulationTest {

    // Synthetic suite: two "test scenarios" sharing one Set.
    // Not actual JUnit @Test methods depending on each other.
    private static List<String> runBrokenSequence(
            List<String> sequence) {

        Set<String> database = new HashSet<>();
        List<String> failures = new ArrayList<>();

        for (String scenario : sequence) {
            switch (scenario) {
                case "writer" -> database.add("fixed-order");
                case "expectsEmpty" -> {
                    if (!database.isEmpty()) {
                        failures.add("expectsEmpty");
                    }
                }
                default -> throw new IllegalArgumentException(
                        "unknown scenario: " + scenario);
            }
        }
        return failures;
    }

    private static List<String> runWithFreshStatePerScenario(
            List<String> sequence) {

        List<String> failures = new ArrayList<>();

        for (String scenario : sequence) {
            Set<String> database = new HashSet<>();
            switch (scenario) {
                case "writer" -> database.add("fixed-order");
                case "expectsEmpty" -> {
                    if (!database.isEmpty()) {
                        failures.add("expectsEmpty");
                    }
                }
                default -> throw new IllegalArgumentException(
                        "unknown scenario: " + scenario);
            }
        }
        return failures;
    }

    @Test
    void reversedOrderExposesHiddenDependency() {
        assertThat(runBrokenSequence(
                List.of("expectsEmpty", "writer")))
                .isEmpty();

        assertThat(runBrokenSequence(
                List.of("writer", "expectsEmpty")))
                .containsExactly("expectsEmpty");
    }

    @Test
    void freshFixtureMakesBothOrdersIndependent() {
        assertThat(runWithFreshStatePerScenario(
                List.of("expectsEmpty", "writer")))
                .isEmpty();

        assertThat(runWithFreshStatePerScenario(
                List.of("writer", "expectsEmpty")))
                .isEmpty();
    }

    @Test
    void finallyRestoresOwnedMutableState() {
        Set<String> database = new HashSet<>();
        try {
            database.add("order-in-test");
            assertThat(database).containsExactly("order-in-test");
        } finally {
            database.clear();
        }
        assertThat(database).isEmpty();
    }
}
```

**All 3 `@Test`s** PASS: the first confirms a **broken synthetic suite** yields order-dependent failures without causing the Maven project itself to fail randomly; the second shows a fresh fixture per scenario eliminates the dependency; the third verifies `finally` cleanup. This keeps the lesson's **reproducible failure** runnable without breaking default Maven builds.

This is an **in-memory simulation**, not a JDBC integration test; the next class tests real DB isolation.

### 9.11. Integration Tests: Per-Invocation Run Key and Safe Demo-Scoped Parallelism

File **`src/test/java/com/example/isolation/ParallelJdbcIsolationTest.java`**:

```java
package com.example.isolation;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.RepeatedTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Execution(ExecutionMode.CONCURRENT)
@TestInstance(TestInstance.Lifecycle.PER_METHOD)
class ParallelJdbcIsolationTest {

    @Autowired
    private OrderStore store;

    @Autowired
    private OrderService service;

    private String runKey;

    @BeforeEach
    void prepareUniqueRun() {
        runKey = "run-" + UUID.randomUUID();
        assertThat(store.countByRunKey(runKey)).isZero();
    }

    @AfterEach
    void removeOnlyOwnRows() {
        store.deleteByRunKey(runKey);
        assertThat(store.countByRunKey(runKey)).isZero();
    }

    @Test
    void oneOrderIsVisibleOnlyWithinItsRun() {
        String id = service.place(runKey, 2);

        assertThat(store.countByRunKey(runKey)).isEqualTo(1L);
        assertThat(store.find(runKey, id))
                .contains(new OrderRow(id, runKey, "NEW", 2));
    }

    @Test
    void twoOrdersProduceExactlyTwoScopedRows() {
        String first = service.place(runKey, 1);
        String second = service.place(runKey, 3);

        assertThat(first).isNotEqualTo(second);
        assertThat(store.countByRunKey(runKey)).isEqualTo(2L);
    }

    @Test
    void anotherRunCannotSeeTheCurrentOrders() {
        String id = service.place(runKey, 5);
        String otherRun = "other-" + UUID.randomUUID();

        assertThat(store.find(otherRun, id)).isEmpty();
        assertThat(store.countByRunKey(otherRun)).isZero();
    }

    @Test
    void lookingUpUnknownIdNeverFindsAnotherTestsRows() {
        String missing = "missing-" + UUID.randomUUID();

        assertThat(store.find(runKey, missing)).isEmpty();
        assertThat(store.countByRunKey(runKey)).isZero();
    }

    @Test
    void updateUsesBothOrderIdAndRunKey() {
        String id = service.place(runKey, 2);
        String otherRun = "other-" + UUID.randomUUID();

        assertThat(store.updateState(
                otherRun, id, "DONE")).isZero();

        assertThat(store.updateState(
                runKey, id, "DONE")).isEqualTo(1);

        assertThat(store.find(runKey, id))
                .contains(new OrderRow(id, runKey, "DONE", 2));
    }

    @Test
    void invalidQuantityCannotLeaveAnyRecord() {
        assertThatThrownBy(() -> service.place(runKey, 0))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(store.countByRunKey(runKey)).isZero();
    }

    @Test
    void duplicatePrimaryKeyFailsWithoutAddingAnotherRow() {
        String id = service.place(runKey, 4);

        assertThatThrownBy(() ->
                store.insert(id, runKey, "NEW", 4))
                .isInstanceOf(
                        DataIntegrityViolationException.class);

        assertThat(store.countByRunKey(runKey)).isEqualTo(1L);
    }

    @Test
    void cleanupOfOneRunDoesNotDeleteAnotherRun() {
        String otherRun = "other-" + UUID.randomUUID();
        try {
            String ownId = service.place(runKey, 1);
            String otherId = service.place(otherRun, 2);

            assertThat(store.deleteByRunKey(runKey))
                    .isEqualTo(1);
            assertThat(store.countByRunKey(runKey)).isZero();

            assertThat(store.find(otherRun, otherId))
                    .contains(new OrderRow(
                            otherId, otherRun, "NEW", 2));
            assertThat(store.find(runKey, ownId)).isEmpty();
        } finally {
            store.deleteByRunKey(otherRun);
        }
    }

    @Test
    void cleanupMayBeCalledMoreThanOnce() {
        service.place(runKey, 1);

        assertThat(store.deleteByRunKey(runKey)).isEqualTo(1);
        assertThat(store.deleteByRunKey(runKey)).isZero();
        // @AfterEach can still clean up safely.
    }

    @RepeatedTest(4)
    void repeatedRunUsesNewOwnerAndCanStartClean() {
        assertThat(store.countByRunKey(runKey)).isZero();
        String id = service.place(runKey, 1);

        assertThat(store.find(runKey, id)).isPresent();
        assertThat(store.countByRunKey(runKey)).isEqualTo(1L);
    }
}
```

**9 `@Test` methods + one `@RepeatedTest(4)`**: totaling **13 invocations** in this class. `@BeforeEach`/`@AfterEach` run for **each repetition**; the class uses `PER_METHOD` so `runKey` is dedicated per test instance. All SQL reads/writes/deletes are scoped by unique ID; no fixed row IDs or full-table resets are used.

Methods can execute concurrently thanks to `@Execution(CONCURRENT)` and the enabled JUnit parallel engine, though **concurrency is not guaranteed in every environment** (thread pools may be small). The suite remains valid when run sequentially. If a real DB app has global mutable state, triggers, sequences, or shared Kafka resources, never assume adding a UUID alone makes concurrency safe.

**Why doesn't `@AfterEach` delete another test's data?** It runs `DELETE ... WHERE run_key = ?` strictly for the current method/repetition's run key, never `TRUNCATE`. In the two-run test, `otherRun`'s row is cleaned up in its own `finally` block so no data escapes the fixture's run key.

### 9.12. Integration Tests: Rollback, Test Transactions, REQUIRES_NEW

File **`src/test/java/com/example/isolation/TransactionBoundaryTest.java`**:

```java
package com.example.isolation;

import java.util.UUID;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class TransactionBoundaryTest {

    @Autowired
    private OrderStore store;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Autowired
    private CommittedWriter committedWriter;

    @Test
    void explicitRollbackRemovesUncommittedJdbCChanges() {
        String run = "tx-" + UUID.randomUUID();
        String id = "ord-" + UUID.randomUUID();

        try {
            TransactionTemplate tx =
                    new TransactionTemplate(transactionManager);

            tx.executeWithoutResult(status -> {
                store.insert(id, run, "NEW", 1);
                assertThat(store.countByRunKey(run))
                        .isEqualTo(1L);
                status.setRollbackOnly();
            });

            assertThat(store.countByRunKey(run)).isZero();
        } finally {
            store.deleteByRunKey(run);
        }
    }

    @Test
    void requiresNewCommitSurvivesOuterRollback() {
        String run = "tx-" + UUID.randomUUID();
        String id = "ord-" + UUID.randomUUID();

        try {
            TransactionTemplate outer =
                    new TransactionTemplate(transactionManager);

            outer.executeWithoutResult(status -> {
                committedWriter.insertCommitted(run, id);
                // Outer transaction is rolled back;
                // REQUIRES_NEW already committed independently.
                status.setRollbackOnly();
            });

            assertThat(store.countByRunKey(run))
                    .isEqualTo(1L);
        } finally {
            // Clean up the COMMITTED row; do not rely on outer rollback.
            store.deleteByRunKey(run);
        }
    }

    @Test
    @Transactional
    void testManagedRollbackCanBeVerifiedInSameMethod() {
        String run = "tx-" + UUID.randomUUID();
        String id = "ord-" + UUID.randomUUID();

        try {
            assertThat(TestTransaction.isActive()).isTrue();
            store.insert(id, run, "NEW", 1);

            assertThat(store.countByRunKey(run))
                    .isEqualTo(1L);

            TestTransaction.flagForRollback();
            TestTransaction.end();

            assertThat(store.countByRunKey(run)).isZero();
        } finally {
            if (TestTransaction.isActive()) {
                TestTransaction.flagForRollback();
                TestTransaction.end();
            }
            store.deleteByRunKey(run);
        }
    }

    @Test
    void unhandledExceptionRollsBackTransactionTemplate() {
        String run = "tx-" + UUID.randomUUID();
        String id = "ord-" + UUID.randomUUID();

        try {
            assertThatThrownBy(() ->
                new TransactionTemplate(transactionManager)
                    .executeWithoutResult(status -> {
                        store.insert(id, run, "NEW", 1);
                        throw new IllegalStateException(
                                "simulated-failure");
                    }))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessage("simulated-failure");

            assertThat(store.countByRunKey(run)).isZero();
        } finally {
            store.deleteByRunKey(run);
        }
    }
}
```

**These 4 `@Test` methods** distinguish:
- Explicit rollback inside `TransactionTemplate` → row disappears.
- Independent `REQUIRES_NEW` commit → row survives outer transaction rollback; `finally` cleans up outside the transaction.
- Test-managed `@Transactional` and `TestTransaction.flagForRollback()/end()` → verifies rollback **within the same test method**, without relying on a subsequent test to inspect data.
- Exception escaping `TransactionTemplate` → rolls back and no row remains.

**Total runnable suite:** 3 unit tests + 9 `@Test` JDBC + 4 repetitions + 4 transaction tests = **20 test invocations** (**16 `@Test` methods, 1 `@RepeatedTest(4)` method**). Tests involving commit/rollback all clean up by `run_key` and do not depend on class ordering.

### 9.13. Running Maven

Requires **JDK 17+** and Maven; no Docker needed:

```bash
mvn test
mvn -Dtest=OrderSensitivitySimulationTest test
mvn -Dtest=ParallelJdbcIsolationTest test
mvn -Dtest=TransactionBoundaryTest test
```

Vary seeds to repeat across different orders:

```bash
mvn test -Djunit.jupiter.execution.order.random.seed=20261108
mvn test -Djunit.jupiter.execution.order.random.seed=91
mvn test -Djunit.jupiter.execution.order.random.seed=7
```

All **20 test invocations** are expected to PASS in an appropriate environment. The project uses an in-memory H2 DB initialized on context startup, and every test cleans up its own data. **There is no fixed stdout** because Maven/JUnit/Spring logs vary by environment and scheduling. Code was reviewed for Java 17/JUnit Jupiter/Spring Boot 3.5, with **no claim of actual Maven execution** during authoring.

In real CI, log **seed**, test selection, JVM forks, timezone, database version, and first-failure details rather than saving only a screenshot of the final `BUILD FAILURE`.

## 10. Reading and Analyzing Failures Across Three Diagnostic Tests

### 10.1. "PASS Alone, FAIL in Full Suite"

Suspects:
- Singleton context reused from another test.
- Leftover static/system property/file/DB state.
- Fixed data with colliding IDs.
- Non-Spring test mutated a global object.
- Test class ordering may be involved.

Evidence to gather:
- Victim test passes when run alone.
- Running polluter before victim in the same JVM fails.
- After properly resetting state, the polluter-victim pair passes in either order.
- Never use `@Order` as a patch unless the scenario is genuinely a single workflow.

### 10.2. "FAIL Only When Parallel"

Suspects:
- Two tests running `TRUNCATE`/`DELETE` on the same table.
- One test clearing a singleton collector while another awaits a listener.
- Both sharing a `@MockBean`/`@MockitoBean` in a cached context and racing on stubbing/verify.
- Tests mutating System properties or sharing a file.
- Race between a DB transaction and an async worker.
- `@DirtiesContext` closing a context while another test uses it.

Evidence:
- Same seed passes sequentially yet fails in parallel.
- Add logging of sanitized test run keys, thread names, operation IDs, and insert/delete timestamps.
- Isolate resources or apply JUnit `@ResourceLock`/`@Isolated` (when shared resources truly cannot be split).
- Review Spring TestContext parallel caveats before enabling suite-wide.

### 10.3. "FAIL on Rerun or When CI Reuses an Environment"

Suspects:
- External DB/schema/Redis/volume reused.
- Cleanup skipped when an earlier test failed early.
- Testcontainers reusable volumes/data lingering.
- Temp files created outside `@TempDir`.
- Broker topics/groups/offsets reused.
- Clock/system properties leaked across the test JVM.

Evidence:
- List residue by **test namespace** after the suite finishes when no tests are running.
- Record `createdAt`/`runId` on fixtures to trace the owner that created leftover rows.
- Add a janitor that expires stale fixtures by TTL without deleting another active pipeline's data.
- Never rely on `schema.sql` of a **cached Spring context** as a per-test DB reset: scripts normally run at startup, not before every method.

## 11. Anti-Patterns That Commonly Cause Suite Flakiness

### 11.1. `@Order` Just So One Test Seeds Data for Another

```java
@Test @Order(1) void createFixture() { ... }
@Test @Order(2) void queryFixture() { ... }
```

This is an anti-pattern snippet, not runnable independently. If two tests only make sense as **one end-to-end workflow**, merge them into **one `@Test` with clear steps**, or use dedicated lifecycle fixtures for deliberate setup. When each method is an independent use case, never depend on data created by another method.

### 11.2. `@BeforeAll` Inserting a Fixture That Every Test Mutates

Shared data can be updated/deleted by one test while another reads unexpected values, especially in parallel. Use immutable shared fixtures if truly immutable, or seed/clone separate data per method. Since `@BeforeAll` runs at the test-class lifecycle level, do not assume per-method transaction rollback covers class-level setup.

### 11.3. Using `SELECT COUNT(*)` Across the Entire Table

When other tests insert rows into the same DB, a global count does not represent the current test. Filter by `WHERE run_key = ?`/tenant ID and assert exact IDs. If an assertion must inspect system-wide totals, run that test against an **isolated database/schema/container** and exclude it from running concurrently with tests sharing that DB.

### 11.4. `@AfterEach` Cleanup Without Waiting for Async Side Effects

A test invokes `service.processAsync()` and returns; `@AfterEach` deletes rows immediately, yet the worker keeps running and inserts rows after cleanup. The next test sees data from the "past". Always **await the terminal `CompletableFuture`** with a timeout, check errors, and then clean up. `Thread.sleep(100)` offers no synchronization guarantee.

### 11.5. Resetting Every Table with `TRUNCATE`

`TRUNCATE` ignores row ownership, has DB-specific transaction semantics, and easily breaks parallel tests. Use scoped cleanup. When resetting an **entire database** is truly required, give that test class/suite an isolated schema/container and reset only when no other worker uses it.

### 11.6. Running `assertTimeoutPreemptively` in a `@Transactional` Test

Spring TestContext transactions bind to the current thread. Preemptive timeouts may execute code on a separate thread whose inserts commit independently rather than rolling back with the test thread. Enforce timeouts at JDBC/HTTP client/async future boundaries or use `assertTimeout` thoughtfully instead of treating preemptive test timeouts as transaction-safe.

### 11.7. Catching and Swallowing Cleanup Exceptions

```java
@AfterEach
void cleanup() {
    try {
        repository.deleteTestData();
    } catch (Exception ignored) {
        // Wrong: stale data persists, causing the NEXT test to fail.
    }
}
```

This is an anti-pattern: if cleanup fails, JUnit must fail visibly while logging sufficient context (test run ID, resource) to identify residue. Never log secrets/PII.

### 11.8. Test Mock Stubs Leaking Across Classes

A shared Spring context can contain Mockito bean overrides. Spring Framework TestContext includes a reset listener, yet custom reset modes, manually created mocks, static mocks, or background tasks can cause stubbing/calls to bleed. Scope mock lifecycles cleanly, avoid parallel tests sharing mutable mocks, and do not add `@DirtiesContext` just for a missed reset.

### 11.9. Treating Random Test Ordering as a "Fix"

A random seed only **exposes** dependencies. Passing under one order still allows failing under another permutation. After fixing, test across multiple seeds and parallel stress runs; capture the failing seed in the regression ticket.

### 11.10. Replacing the Context Cache by Restarting the App per Test

Disabling reuse makes tests painfully slow and still fails to clear external DBs/Redis/brokers/files. Determine whether the state lives inside or outside the context; do not sacrifice runtime when scoped cleanup suffices. `@DirtiesContext` is a last resort when a test genuinely leaves the context irrecoverably dirty.

## 12. Test Matrix for Detecting Order Dependence and Residue

| Scenario | Environment | Expected / Evidence |
|---|---|---|
| Single test run alone | Fresh process/DB | PASSES with self-contained setup |
| Same class across multiple orders | `MethodOrderer.Random` with multiple seeds | PASSES across all tested seeds |
| Classes across multiple orders | `ClassOrderer.Random` | No test requires another class to run first |
| Repeated single test | `@RepeatedTest`/Surefire rerun | Each iteration gets its own fixture |
| One writer and one reader | Reverse both scenarios | Outcome independent of order |
| DB contains another test's data | Two distinct run keys | Scoped queries never cross-read |
| Two tests insert concurrently | Distinct run keys, unique PKs | Zero races or data collisions |
| Cleanup of A | A and B share table | Only A's rows deleted |
| Invalid command | Invalid input | Zero new rows, zero side effects |
| Duplicate business ID | Constraint/failure case | Fails cleanly, no silent collision |
| Test-managed rollback | Same thread + `REQUIRED` transaction | Uncommitted row vanishes |
| `REQUIRES_NEW` | Outer test rollback | Committed row survives, cleaned separately |
| Async DB write | Different worker thread | Await + cleanup after completion |
| `@DirtiesContext` | Context-state mutation | Context reloads only when truly needed |
| Mock reuse | Shared test context | Stubbing/interactions reset cleanly |
| External resources | Redis/Kafka/files/HTTP | Dedicated IDs/cleanup/acks |
| CI rerun in same environment | Persistent DB/workspace | Zero residue from prior runs |
| CI parallel | Opt-in safe tests | No global truncates, no shared mutable state |
| Context cache reuse | Same Spring configuration | Tests stay independent even when beans are reused |

If a test demands "the whole table is empty" as a precondition while sharing the DB across tests, change the architecture: use an **isolated schema/container** or reformulate the contract as **scoped-to-test**, never an assertion demanding an empty shared environment.

## 13. QA Checklist Before Enabling Parallel CI

- [ ] Every test sets up its own fixtures without requiring another test A/B to run first.
- [ ] I ran an individual test, the whole class, and the full suite to cross-check.
- [ ] I tested with multiple `MethodOrderer.Random` and `ClassOrderer.Random` seeds.
- [ ] Failing seeds are saved for reproduction, never treating a fixed seed as a fix.
- [ ] I distinguished order dependency from concurrency races and async timing.
- [ ] I inventoried shared state: statics, singletons, databases, Redis, Kafka, files, mocks, properties.
- [ ] Test DB uses per-run or per-tenant IDs rather than hard-coded `"id=1"` across all tests.
- [ ] All critical queries/assertions are scoped to test-owned data.
- [ ] Cleanup deletes only the test's rows/keys, **never global DELETE/TRUNCATE** in parallel suites.
- [ ] `@BeforeEach` allocates a fresh run ID; `@AfterEach` cleans up every invocation without swallowing errors.
- [ ] `@RepeatedTest` also receives a fresh fixture/run ID per iteration.
- [ ] Tests do not assume automatic transaction rollback on `@SpringBootTest` without `@Transactional`.
- [ ] I checked `REQUIRES_NEW`, `@Async`, HTTP server threads, and external side effects.
- [ ] `@Transactional` tests avoid preemptive timeouts that break out of the transaction.
- [ ] `TestTransaction` or explicit transaction tests verify rollback **within the same test**, not via another method.
- [ ] `@DirtiesContext` is never used instead of DB/file/broker cleanup; context cache sharing is understood.
- [ ] `@MockitoBean`/`@DirtiesContext`/shared-database tests are not run in parallel without evaluating caveats.
- [ ] Inseparable shared resources use `@ResourceLock`/`@Isolated` or sequential execution.
- [ ] I await all async work before teardown and propagate errors to JUnit.
- [ ] `Thread.sleep` is never used to guess when workers finish.
- [ ] Stale CI data is scavenged via TTL/janitors scoped by namespace during idle windows.
- [ ] No credentials, PII, or sensitive payloads are logged when diagnosing test residue.
- [ ] I verified actual test invocation counts, JUnit parallel settings, and Surefire forks.
- [ ] Tests pass across multiple seeds and repeated runs in a CI-like environment.
- [ ] Failing run reports capture polluter/victim hypotheses, run keys, seeds, and cleanup evidence.

**Conclusion:** order-dependent tests and leftover data can be exposed by **reproducible seed-based shuffling, comparing isolated vs full-suite runs, baseline checks, and test-owned data**, combined with deliberate concurrency stress tests. The fix is never `@Order` hacks or blanket `@DirtiesContext`, but **independent setup, clear state ownership, accurate transaction boundaries, and complete side-effect teardown**. A trustworthy suite is one whose **results never change merely because another test ran before it**.

## Official Documentation

- [JUnit 5.12 — User Guide: Test Execution Order, Parallel Execution, @ResourceLock](https://docs.junit.org/5.12.0/user-guide/)
- [Spring Framework 6.2 — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html)
- [Spring Framework 6.2 — Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html)
- [Spring Framework 6.2 — Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework 6.2 — @DirtiesContext](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html)
- [Spring Boot 3.5 — SQL Database Initialization](https://docs.spring.io/spring-boot/3.5/how-to/data-initialization.html)
- [Spring Boot 3.5 — SQL Databases and JdbcTemplate](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)