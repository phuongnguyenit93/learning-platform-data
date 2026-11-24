# Independence by Method, Class, JVM, and External Resources in Spring Boot Testing

> **Module:** Spring Boot – testing  
> **Group:** Isolation and Parallel Execution  
> **Topic:** Independence by method, class, JVM, and external resources  
> **Objective:** Accurately distinguish four isolation levels: test method, test class/Spring ApplicationContext, JVM process, and database/broker/filesystem/external services. Build tests that run reliably when changing execution order or enabling JUnit parallelism; control state, transactions, resource ownership, Spring TestContext cache, Testcontainers lifecycle, and Maven Surefire forks. Examples use Java 17 + Spring Boot 3.5.0 + JUnit Jupiter + PostgreSQL Testcontainers.

## 1. Defining an Independent Test: Not Relying on What Other Tests Did

An **independent** test must satisfy the following conditions:

- Its setup fully defines all necessary preconditions.
- The result does not depend on which test runs before, runs after, or is skipped.
- No undeclared state is implicitly used from another test.
- The test only modifies resources it owns or uses a synchronization mechanism when sharing is required.
- Cleanup does not destroy resources of tests running in parallel.
- When changing test order, thread count, JVM fork, or CI runner machine, the contract still holds — unless the suite is designed and explicitly documented with a serialization scope.
- Any infrastructure failure (Docker unavailable, database container fails to start) is reported as an environment error, never labeled as a "business assertion pass".

**Important:** "Running each test in a new Java object" does not mean "each test has a new database". The four levels below are distinct boundaries that can overlap.

### 1.1. Four Layers of Isolation

```text
Maven / CI job
│
├── Forked JVM #1                          [JVM boundary]
│   ├── JUnit test plan
│   │   ├── Class A                        [class boundary]
│   │   │   ├── method a()  test object A1 [method boundary]
│   │   │   └── method b()  test object A2
│   │   └── Class B
│   │       ├── method c()  test object B1
│   │       └── method d()  test object B2
│   └── Spring TestContext static cache
│       └── ApplicationContext X
│           ├── singleton Service bean
│           ├── CacheManager / DataSource
│           └── background listeners/schedulers
│
├── Forked JVM #2                          [separate static state]
│   └── Spring TestContext static cache #2
│
└── External resources                     [not automatically split by JVM]
    ├── PostgreSQL database/schema/table/row
    ├── Redis DB/key namespace
    ├── RabbitMQ broker/vhost/queue/exchange
    ├── Kafka topic/consumer group
    ├── Filesystem/object store
    └── Remote HTTP sandbox
```

Two JVMs have **separate heap/static state**, yet can still point to the same PostgreSQL schema or RabbitMQ queue. Two test classes using **different ApplicationContexts** can still race if both delete from the same data table. Two test methods with separate objects can still share a singleton bean inside the Spring context.

### 1.2. Shareability Matrix

| Scope | What is typically isolated | What can still be shared |
| --- | --- | --- |
| Per `@Test` method | Instance fields if JUnit `PER_METHOD` | `static`, singleton beans, System properties, files, DB, broker |
| Per JUnit test class | `@BeforeAll`/`@AfterAll` lifecycle, class-level fixtures | Spring cached context, same-JVM static state, external resources |
| Per Spring `ApplicationContext` | Bean instances of that context | JVM static state, OS ports, Redis/DB/broker, other contexts pointing to the same endpoints |
| Per forked JVM | Heap, classloader, static cache, and System properties of that JVM | Database, broker, filesystem, ports, cloud APIs, test credentials |
| Per Testcontainers container | Usually separate process/broker/database server | Host filesystem, bind mounts, external network, image registry, global daemon |
| Per DB schema/vhost/namespace | Data within the isolated scope | DB instance capacity, global limits, permissions, network, and shared services |
| Per CI job | Workspace/runner depending on platform | Shared database, Docker daemon, artifact bucket, service account, staging |

**Conclusion from the matrix:** To make tests independent, you must control **state + lifecycle + naming + cleanup** across every relevant layer. No single annotation makes every resource independent automatically.

## 2. Method-Level Isolation: JUnit Jupiter `PER_METHOD`

### 2.1. JUnit 5 Default

In JUnit Jupiter, the default lifecycle is:

```java
@TestInstance(TestInstance.Lifecycle.PER_METHOD)
class ExampleTest {
    // each @Test gets a new instance of the test class
}
```

If no annotation is declared, the default is also `PER_METHOD` unless overridden by suite/config defaults.

Example:

```java
class SafeInstanceStateTest {

    private final List<String> values = new ArrayList<>();

    @Test
    void firstMethod() {
        assertThat(values).isEmpty();
        values.add("first");
        assertThat(values).containsExactly("first");
    }

    @Test
    void secondMethod() {
        assertThat(values).isEmpty();
        values.add("second");
        assertThat(values).containsExactly("second");
    }
}
```

This is a snippet; JUnit, AssertJ, and `java.util` imports are required. Each test has its own `values`, so it does not rely on method order. A runnable version with `@Execution(CONCURRENT)` is in Section 8.

### 2.2. `PER_METHOD` Does **Not** Isolate `static`

**Anti-pattern** example:

```java
class BrokenStaticStateTest {

    private static final List<String> SHARED =
            new ArrayList<>();

    @Test
    void first() {
        SHARED.add("first");
        assertThat(SHARED).hasSize(1);
    }

    @Test
    void second() {
        SHARED.add("second");
        assertThat(SHARED).hasSize(1); // order-dependent
    }
}
```

If the first test has already run, the subsequent test sees stale state. When running concurrently, `ArrayList` is also not thread-safe. `PER_METHOD` only creates a new **test object**; static fields belong to the classloader/JVM.

Solution: use instance-local state, immutable shared fixtures, or disciplined resets if a resource must be shared. Avoid `static HashMap`/`static cache`/`static sequence counter` as test fixtures without defined concurrency and cleanup.

### 2.3. What Risks Does `PER_CLASS` Carry?

With:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class PerClassTest {
    private int counter;

    @Test void a() { counter++; }
    @Test void b() { counter++; }
}
```

Both methods use the **same instance**. If a test depends on `counter==1`, test order becomes a hidden input. With parallel execution, mutable fields introduce data races.

`PER_CLASS` is useful when you need non-static `@BeforeAll`/`@AfterAll` or expensive fixtures, but you must:

- Reset state per method (`@BeforeEach`) or use immutable shared state.
- Synchronize if methods run concurrently.
- Never use test order as a mechanism to pass data between steps.
- Never enable concurrency if fixtures are not thread-safe.
- Explicitly document resource ownership and teardown at the proper lifecycle stage.

**Do not confuse:** `@BeforeEach` runs before each method, but it does not make wiping a global database safe for other tests, especially when methods/classes run in parallel.

### 2.4. Method Parameters and `@TempDir`

JUnit provides `@TempDir` to create a temporary directory per field/parameter declaration:

```java
@Test
void generateReport(@TempDir Path dir) throws IOException {
    Path report = dir.resolve("report.txt");
    Files.writeString(report, "ok");
    assertThat(Files.readString(report)).isEqualTo("ok");
}
```

Using a JUnit-managed temporary directory is better than writing every test to `/tmp/report.txt` or `C:\temp\report.txt`. Do not use a single global filename when CI jobs might share the same runner/volume. For external temp dirs outside JUnit, create a unique path and clean up according to ownership.

### 2.5. Distinguishing "Object Reuse" from "Side Effect Reuse"

Even when a new test object is created, the following can still persist:

- Spring singleton `@Service` or `@Repository` in the cached `ApplicationContext`.
- In-memory caches on beans.
- Hikari connection pools and persisted database rows.
- RabbitMQ listener containers or scheduler threads.
- JVM-wide static System properties/TimeZone/Locale.
- Redis keys/TTL, bucket files, test messages.

Calling `new Service(...)` in unit tests helps control state inside that object, but does not automatically isolate static dependencies or external singleton clients.

## 3. Class-Level Isolation: Spring TestContext Cache Does Not Mean a New Context per Class

### 3.1. Spring TestContext Cache Is Shared Across Classes

The Spring Framework TestContext cache stores `ApplicationContext` instances by **configuration key**, including:

- `@ContextConfiguration` classes/locations, initializers, loaders.
- Active profiles (`@ActiveProfiles`).
- Test property sources and inline properties.
- Context customizers: Spring Boot test features, `@DynamicPropertySource`, `@MockitoBean`/bean overrides.
- Parent context, web resource base path, and other configurations.

Two test classes with equivalent configuration keys **can reuse the same `ApplicationContext`** within the same JVM. This makes the suite faster, but singleton beans and background workers can persist across classes.

Do not assume:

> "Class A finished ⇒ Spring context closed ⇒ singleton state is clean."

In reality, the same context can remain alive and be used by Class B. Even though Class B gets a new test object, it still injects the same singleton bean.

### 3.2. **Different** Test Contexts Can Still Share the Same Database

Two classes:

```java
@SpringBootTest(properties = "feature.alpha=true")
class ATest { }

@SpringBootTest(properties = "feature.alpha=false")
class BTest { }
```

can produce two different Spring contexts due to different inline properties; however, if both point to the same `spring.datasource.url`, they still access the same database. Do not confuse context uniqueness with external data isolation.

### 3.3. `@DirtiesContext`: Must Be Used for the Right Purpose

`@DirtiesContext` marks a context as modified and removes it from the cache/closes it, for example:

```java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBootTest
class ContextMutatingTest { }
```

It is useful when a test modifies bean definitions, singleton application state that is difficult to reset, or a context that depends on a test class container that has already stopped.

However:

- It is expensive because Spring must reload the context afterward.
- It does not roll back a database in another JVM.
- It does not delete RabbitMQ/Redis/filesystem resources.
- It can break other tests using the shared context **if running in parallel**.
- It should not be placed on every test as a way to "clean up everything".
- If you only need to delete a test database row, scoped cleanup is usually better than reloading the entire context.

Spring Framework 6.2 recommends **not parallelizing** test classes that use `@DirtiesContext`, `@MockitoBean`/`@MockitoSpyBean`, method ordering, or mutate shared DB/broker/filesystem state unless contention is controlled.

### 3.4. `@MockitoBean`, Mock Reset, and Parallel Tests

Spring 6.2 introduces `@MockitoBean`/`@MockitoSpyBean`. When two test methods share a context/mock bean and both stub/verify/reset it, they can interfere with each other. Mockito stubbing is not "thread isolation".

- Isolate test scope or use class-level serialization for tests with shared mock beans.
- Prefer pure unit tests with Mockito mocks created separately per test method.
- Do not force all test slices/full-context tests into parallel execution if mock lifecycle is not guaranteed.
- Do not use `Thread.sleep` hoping two tests avoid colliding.

### 3.5. Singleton Beans with Mutable State Must Be Treated as Shared Resources

```java
@Service
class CounterService {
    private int counter;      // mutable singleton state
    void increment() { counter++; }
    int count() { return counter; }
}
```

Even when JUnit creates two test objects, `CounterService` in the Spring context can still be **a single singleton**. Across multiple threads, `counter++` also causes a data race. Solution: design beans to be stateless or thread-safe, and avoid using a global counter as a test fixture unless isolation is explicit.

## 4. JVM-Level Isolation: Surefire Forks and Limits of the Static Cache

### 4.1. Forks Are Not Threads

Maven Surefire's `forkCount` controls the maximum number of **JVM processes** running tests. `reuseForks` determines whether JVMs are reused between test classes.

Illustrative example:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <forkCount>1</forkCount>
        <reuseForks>true</reuseForks>
    </configuration>
</plugin>
```

Meaning:

- `forkCount=1,reuseForks=true`: typically one test JVM is reused across test classes in the module; the Spring context cache can take effect.
- `forkCount=2,reuseForks=true`: up to two test JVMs in parallel; each fork has its **own static fields/context cache**.
- `forkCount=1,reuseForks=false`: creates a fresh JVM fork per test class, providing stronger process isolation at higher cost.
- `forkCount=0`: tests run inside the Maven JVM, with its own trade-offs in isolation/classloading and performance.
- `reuseForks=false` does not eliminate shared databases/brokers; it only reduces sharing in **JVM state**.

The Spring Context cache is a static cache **per JVM**, not distributed across forks. Therefore, the context restarts when the test suite splits across processes; increasing forks can multiply DB connections, containers, and startup jobs.

### 4.2. Running from the Maven Command Line

```bash
# Single JVM fork (matching the sample project's pom configuration):
mvn -B -ntp test

# A fresh JVM for each test class:
mvn -B -ntp -DforkCount=1 -DreuseForks=false test

# Up to 2 concurrent JVM forks:
mvn -B -ntp -DforkCount=2 -DreuseForks=true test
```

These parameters are Surefire user properties; the test engine inside each fork still follows `junit-platform.properties`. **Two separate JVMs cannot use `@ResourceLock` to lock the same database row**. To synchronize across processes, use separate namespaces or an external coordination mechanism outside the JVM.

### 4.3. System Properties, JVM Locale, TimeZone, and Security Providers

Process-wide objects include:

- `System.getProperties()`/`System.setProperty(...)`.
- `TimeZone.setDefault(...)`, `Locale.setDefault(...)`.
- Static caches/singletons, JVM shutdown hooks.
- Testcontainers singleton objects and the Spring static TestContext cache.
- Classloader-specific registries.
- Port assignments/cached DNS/SSL contexts in many libraries.

When tests share a JVM, modifying these states without restoring them can affect other tests. Across multiple forks, in-JVM state is separated, but **OS ports/filesystem and external services remain shared**.

### 4.4. Example Observing PID and Static State

```java
package com.example.isolab;

import java.util.UUID;

public class ProcessProbe {

    private static final String STARTUP_TOKEN =
            UUID.randomUUID().toString();

    public static void main(String[] args) {
        System.out.println("pid=" +
                ProcessHandle.current().pid());
        System.out.println("token=" + STARTUP_TOKEN);
    }
}
```

After building:

```bash
mvn -B -ntp -DskipTests package

java -cp target/classes com.example.isolab.ProcessProbe
java -cp target/classes com.example.isolab.ProcessProbe
```

Output format looks like:

```text
pid=<OS-assigned process id>
token=<random UUID>
```

Two invocations of `java` start new JVMs; PID/token differ in practice, but **do not hard-code PID numbers or UUIDs**. This illustrates the process boundary, not a JUnit test. Do not treat random output as an absolute 100% uniqueness assertion: uniqueness should be designed with UUIDs + constraints/namespaces and collision handling by policy when side effects matter.

### 4.5. Using Too Many Forks Can Make the Suite Worse

- Each fork may load its own Spring context, increasing RAM/CPU.
- If each fork starts PostgreSQL/Rabbit containers, pressure on the Docker daemon/registry increases.
- If all forks share the same schema and run `TRUNCATE tables` in setup, tests can break one another.
- Static `@ResourceLock` and `@Isolated` only apply within their respective JUnit test plan, **not across forks**.
- `reuseForks=false` sometimes hides shared-static-state bugs without fixing external races.
- Do not rely on forks as the primary fix for tests that depend on production-like data.

## 5. External Resource Isolation: Database, Redis, Broker, Files, and HTTP

### 5.1. Ways to Achieve Isolation, from Strongest to Weakest

| Strategy | Scope | Pros | Trade-off |
| --- | --- | --- | --- |
| Dedicated container per test class | Broker/DB process/container | Zero data collision with other classes | High startup/RAM cost |
| Dedicated database/schema per worker | DB namespace | Scales well in parallel, easy cleanup | Requires provisioning schemas/migrations |
| Dedicated Redis prefix/vhost/queue/topic | Logical resource | Controlled service sharing | Requires naming + permission discipline |
| Dedicated UUID/request ID per test | Row/message/object | Lightweight, no new database needed | Does not isolate global DDL/flush or shared counters |
| Transaction rollback for one test | Test-thread DB writes | Fast if all work shares the transaction | Does not cover async threads/HTTP/REQUIRES_NEW/broker |
| Lock/serialization | One shared resource | Reduces races when splitting isn't possible | Slower, does not protect cross-process if local lock |
| Run entire suite sequentially | Test plan | Easy temporary workaround | Hides state dependencies and does not protect CI forks/jobs |

**Priority:** Design tests with a **unique resource namespace** and owner-based cleanup; use transaction rollback within its proper scope; serialize only when isolation is genuinely impossible.

### 5.2. PostgreSQL: Avoid Unconditional `DELETE FROM table`

Anti-pattern:

```java
@BeforeEach
void reset() {
    jdbc.execute("TRUNCATE TABLE orders CASCADE");
}
```

If Class A and Class B share the database in parallel, Class A can truncate data that B just created. B fails even though business code is correct.

Better:

```java
String id = "test-" + UUID.randomUUID();
service.create(id, "test-payload");
try {
    assertThat(service.exists(id)).isTrue();
}
finally {
    service.delete(id); // only data owned by this test
}
```

On a real database, use a unique primary key/tenant key and delete by **exact ID**, not global cleanup. With multiple related tables, clean up using an FK-aware strategy; even safer is a dedicated schema per CI worker.

`@Sql(scripts="cleanup.sql")` or `@SqlConfig(transactionMode=ISOLATED)` can be useful, but you must understand which transaction they run in. A global truncate script does not become parallel-safe merely by being declared via `@Sql`.

### 5.3. `@Transactional` in Tests: Rollback Has Limits

Spring TestContext on a JUnit `@Transactional` method typically opens a **test-managed transaction** on the test thread and rolls it back after the method:

```java
@Test
@Transactional
void insertsThenRollsBack() {
    notes.insert("unique-id", "alice", "hello");
    assertThat(notes.count("unique-id")).isEqualTo(1);
}
```

When the test method finishes, Spring rolls back the transaction by default. However:

- `@BeforeEach`/`@AfterEach` of a **transactional test** normally run in that transaction; `@BeforeAll`/`@AfterAll` do not.
- `@Async`, schedulers, Rabbit/Kafka listeners, and HTTP server request threads do not automatically join the test-managed transaction.
- A service using `REQUIRES_NEW` can commit outside the test's transaction.
- `assertTimeoutPreemptively(...)` or JUnit preemptive separate-thread timeouts can move test code onto another thread, bypassing the transaction.
- DB writes outside the DataSource/transaction manager are not rolled back.
- Transactions do not delete object store objects, Redis keys, or broker messages.
- A failed SQL statement can mark the transaction rollback-only; subsequent test cleanup/queries must account for DB behavior.

**Do not treat `@Transactional` as the sole cleanup strategy** for multi-resource workflows.

### 5.4. Verifying Rollback **After** the Transaction Ends

Spring TestContext provides `@AfterTransaction` to assert database state after rollback/commit:

```java
@AfterTransaction
void afterTestTransaction() {
    // At this point, the test-managed transaction has ended
    // You can query the DB to verify the test's insert no longer exists.
}
```

The runnable project includes a test following this pattern. It is stronger than only checking results inside the transaction before rollback, yet still does not prove there are no side effects in brokers/HTTP.

### 5.5. Redis: Logical Namespaces and TTL

- Do not run `FLUSHDB`/`FLUSHALL` on a Redis instance shared with other tests.
- Keys should include `app:testRunId:testId:tenantId:businessKey` or an equivalent namespace, depending on the security contract.
- Cache prefix and tenant/user scope are two distinct requirements.
- Clean up by **self-owned key prefix**; avoid wildcard `KEYS *` on clusters.
- Do not generate a random prefix on every read without the same mechanism in the writer.
- TTL on test entries helps collect garbage if the process crashes, but does not replace explicit cleanup for assertion isolation.
- Test TTL using bounded polling/Redis PTTL; do not assert exact milliseconds.
- When testing caches concurrently, avoid one test calling `cache.clear()` across another tenant's cache.

### 5.6. RabbitMQ: Queue/Vhost/Exchange and Competing Consumers

If two consumer tests read from the same queue on the same broker, a message from test A can be consumed first by consumer B. Test A times out, test B receives the "wrong" payload, and the test author suspects a routing bug.

Solution:

- Namespace queues/vhosts per test class/job; check broker policies for dynamic names.
- Unique event IDs/tenant IDs; consumers only process events belonging to their test.
- When testing routing, create dedicated bindings and read from the **exact queue**.
- Do not purge a global queue in `@BeforeEach`.
- Do not call `RabbitTemplate.receiveAndConvert` from two tests on the same queue in parallel if each expects to own its messages.
- Publisher confirms, mandatory returns, and consumer ACKs are separate contracts; an empty queue does not prove a business side effect committed.
- Dead-letter queues/poison messages must also be namespaced and cleaned up.

With a class-dedicated ephemeral broker container, fixed names can be used **inside that container**; with a shared broker, a run-specific prefix is mandatory. Never send messages to a production broker.

### 5.7. Kafka: Topics and Consumer Groups

- Two tests sharing a consumer group on a shared topic can trigger rebalances and compete with each other.
- Use a unique group ID/test namespace, and isolate topics where appropriate.
- Consumer offsets/retention persist after tests and independently of the JVM process.
- Starting/stopping a broker via Testcontainers does not mean consumer offsets are reset if state is mounted or the cluster is shared.
- A test requiring replay must explicitly reset offsets or use a new group ID rather than relying on class order.
- Embedded Kafka and broker containers have semantic differences that should be documented explicitly.

### 5.8. Filesystem and Object Storage

- `@TempDir` for method-level files, while S3 buckets/object keys must include a run namespace.
- Do not use a single filename such as `output.csv` at the project root for all tests.
- For filesystem cleanup, verify the path resides inside a test-owned directory before recursive deletion.
- If two JVMs mount the same volume, a local Java `synchronized` block does not resolve collisions.
- Use UUID-named directories and `finally`/teardown; configure TTL/lifecycle policies for remote objects.
- Do not delete an entire bucket to clean up one test.

### 5.9. HTTP Stubs and Random Ports

Use WireMock/MockWebServer/JDK HttpServer with a dynamically chosen port:

```text
Test A: stub server at 127.0.0.1:<port-A>
Test B: stub server at 127.0.0.1:<port-B>
```

Do not hard-code `8080`/`9999` when running in parallel. If the Spring context cache retains an HTTP client bean pointing to an old base URL after class A stops its stub, class B might reuse the stale client. Separate contexts via configuration, align stub lifecycle with the context, or intentionally use `@DirtiesContext` and serialize related tests.

## 6. JUnit Jupiter Parallel Mode: Enabling at the Right Scope Without Breaking Isolation

### 6.1. Sequential by Default, Must Opt In

JUnit Jupiter runs sequentially by default. To enable parallelism:

```properties
junit.jupiter.execution.parallel.enabled=true
```

However, enabling that flag alone **does not guarantee methods run concurrently**. It also depends on `mode.default`, `mode.classes.default`, and `@Execution` annotations. In the sample project, we enable **concurrent classes**, keep methods `same_thread` by default, and opt in only selected pure unit classes to concurrent methods.

### 6.2. Configuration for a Mixed Suite

```properties
# src/test/resources/junit-platform.properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=4
```

This is a pragmatic baseline:

- Top-level test classes can run concurrently.
- Methods within a class run on the same thread by default according to JUnit's execution tree.
- Pure unit classes can use `@Execution(CONCURRENT)` if they share no state.
- DB integration classes use `@Isolated`/`@DirtiesContext` to avoid running concurrently with other classes in the same JUnit plan.
- JUnit fixed parallelism is a target concurrency level, not a guarantee that exactly 4 threads are always active.
- Does not handle synchronization **between two JVMs** spawned by Maven forks.

### 6.3. `@ResourceLock` for In-JVM State

Example of two tests modifying System properties:

```java
@Execution(ExecutionMode.CONCURRENT)
class SystemPropertyTest {

    @Test
    @ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
    void changesProperty() {
        String before = System.getProperty("lab.flag");
        try {
            System.setProperty("lab.flag", "on");
            assertThat(System.getProperty("lab.flag")).isEqualTo("on");
        }
        finally {
            if (before == null) {
                System.clearProperty("lab.flag");
            }
            else {
                System.setProperty("lab.flag", before);
            }
        }
    }
}
```

This is a snippet; the runnable project contains the full class with two methods and imports.

**Characteristics:** `@ResourceLock` coordinates JUnit nodes participating under the same resource lock key in the test plan, including their lifecycle methods. It does not lock other Java processes, OS files, or global Redis. If another test modifies the property without declaring the same lock, the lock does not protect it.

`ResourceAccessMode.READ` suits multiple readers; `READ_WRITE` is for writers and prevents conflicting operations in the engine. Avoid overusing a single global lock that needlessly serializes the entire suite.

### 6.4. `@Isolated` on a Test Class

JUnit Jupiter's `@Isolated` prevents that class from running concurrently with other classes in the **same JUnit test plan**. It is suitable when a class uses Spring `@DirtiesContext` or mutates a shared resource that is hard to isolate.

However, it has no effect on **another Maven Surefire fork** or a CI job on another runner. When a DB/broker is shared across forks, external isolation or external coordination is required.

### 6.5. Warning Regarding `@MockitoBean` and `@DirtiesContext`

Spring Framework 6.2 recommends avoiding parallel tests that use `@DirtiesContext`, bean overrides/mocks, or mutate shared resources. Configuring JUnit classes as concurrent **does not mean every Spring Boot test class is safe**. Choose selective parallelism:

- Stateless pure unit tests: can run concurrently.
- JDBC tests using row namespaces: can run in parallel if connection/transaction/schema design is sufficient.
- Bean overrides or dirty contexts: typically serialize.
- Shared broker queues, global DDL, scheduler startup: serialize or refactor resource ownership.
- External cloud sandboxes: isolate per-job namespace/account, not just in-JVM locks.

## 7. Testcontainers Lifecycle and Spring Context Cache: A Common Trap

### 7.1. Static `@Container` Lives by Test Class

```java
@Testcontainers
@SpringBootTest
class PostgresIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

The JUnit Testcontainers extension starts/stops a static container according to the **test class lifecycle**. However, Spring TestContext may cache the `ApplicationContext` beyond that class.

Failure example:

```text
Class A: starts container A → builds Spring context X → tests PASS
Class A ends: Testcontainers stops container A
Class B: context key matches → Spring reuses context X
Class B: DataSource still points to stopped container A → FAIL
```

**Important:** a static field belonging to a class does not mean the container stays alive until JVM exit. It is the `@Container` lifecycle of the Testcontainers extension that stops it after the class.

### 7.2. Three Intentional Lifecycle Strategies

1. **Class-scoped container + `@DirtiesContext(AFTER_CLASS)`:** simple when one test class owns the container; closes the Spring context so a stale DataSource is not reused.
2. **Spring-managed container bean:** when the context should be cached across multiple test classes, bind the container lifecycle to the Spring context (via Spring Boot `@ServiceConnection`/supported test configuration).
3. **Suite-wide singleton container:** started manually, shared across classes, and stopped per suite/JVM lifecycle; **do not** combine the singleton pattern with `@Testcontainers @Container` stopping after each class.

Pick one approach; do not mix lifecycles implicitly. Testcontainers reusable containers are not an automatic fix for context cache issues, and should not be used in mandatory CI when clean per-job environments are required.

### 7.3. Spring Boot `@ServiceConnection` Does Not Create Data Isolation

`@ServiceConnection` derives connection details from the container, avoiding hard-coded host/port/password. Yet two tests using the same `PostgreSQLContainer` can still write to the same table/rows. Data isolation is a separate responsibility.

Test code should assert records by exact ID, not `SELECT COUNT(*) FROM all_notes = 1` when multiple tests may insert concurrently.

## 8. Java 17 + Spring Boot 3.5.0 + PostgreSQL Testcontainers Project

The complete project demonstrates:

- `PER_METHOD` instance state and optional method-level parallel execution.
- `@TempDir` creating method-scoped filesystem paths.
- `@ResourceLock` protecting System properties within the JVM.
- Spring JDBC + real Postgres integration with unique rows/cleanup.
- `@Transactional` test rollback verified via `@AfterTransaction`.
- `@Isolated`/`@DirtiesContext` to keep Testcontainers/context lifecycles aligned.
- A `ProcessProbe` Java program demonstrating JVM boundaries.

**Total: 10 JUnit `@Test` methods** across four test classes: 2 instance fields, 2 temp dirs, 2 JVM property resource locks, 4 DB integration tests. Redis, RabbitMQ, and Kafka are not required in the runnable sample; they are explained and included as extension exercises matching external resource scopes.

### 8.1. Structure

```text
isolation-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/isolab/
    │   │   ├── IsolationLabApplication.java
    │   │   ├── NoteService.java
    │   │   └── ProcessProbe.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        ├── resources/junit-platform.properties
        └── java/com/example/isolab/
            ├── MethodStateIsolationTest.java
            ├── TempDirectoryIsolationTest.java
            ├── SystemPropertyLockTest.java
            └── NoteStoreIntegrationTest.java
```

Each `public` Java top-level class lives in a file of the same name under package `com.example.isolab`. Test sources use exact imports for JUnit Jupiter 5/AssertJ and Spring Boot 3.5/Framework 6.2.

### 8.2. `pom.xml`

```xml
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
    <artifactId>isolation-lab</artifactId>
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
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-testcontainers</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>postgresql</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <configuration>
                    <forkCount>1</forkCount>
                    <reuseForks>true</reuseForks>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

The Spring Boot parent manages compatible versions; `spring-boot-starter-test` includes Jupiter and AssertJ. Boot 3.5 BOM uses Testcontainers 1.x, so `org.testcontainers.containers.PostgreSQLContainer` and the `org.testcontainers:postgresql` artifact are the right choices; do not mix imports/packages from Testcontainers 2.x without updating the BOM consistently.

Do not add an in-memory H2 database and claim PostgreSQL transactions/constraints were tested: the integration test uses real PostgreSQL inside a container.

### 8.3. `application.properties`

```properties
# src/main/resources/application.properties
spring.sql.init.mode=always
```

`spring.sql.init.mode=always` runs `schema.sql` on a non-embedded database in the lab. Do not use this initialization mode unconditionally on a production DB; real applications should use Flyway/Liquibase migrations with explicit environment scopes.

### 8.4. `schema.sql`

```sql
-- src/main/resources/schema.sql
CREATE TABLE test_notes (
    note_id VARCHAR(80) PRIMARY KEY,
    owner_id VARCHAR(80) NOT NULL,
    content VARCHAR(200) NOT NULL
);
```

Test cases generate prefixed UUID IDs; each test deletes only the row matching the ID it created. If two test classes/forks share a real database, unique PKs and scoped cleanup are necessary to avoid row collisions; schema-level migrations and unique constraints still require dedicated test isolation.

### 8.5. `IsolationLabApplication.java`

```java
// src/main/java/com/example/isolab/IsolationLabApplication.java
package com.example.isolab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IsolationLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(IsolationLabApplication.class, args);
    }
}
```

Spring Boot JDBC auto-configuration creates `DataSource`/`JdbcTemplate` from the PostgreSQL connection details provided by the test container.

### 8.6. `NoteService.java`

```java
// src/main/java/com/example/isolab/NoteService.java
package com.example.isolab;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class NoteService {

    private final JdbcTemplate jdbc;

    public NoteService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(
            String id, String owner, String content) {
        jdbc.update(
                "INSERT INTO test_notes"
                        + "(note_id,owner_id,content) "
                        + "VALUES (?,?,?)",
                id, owner, content);
    }

    public String content(String id) {
        return jdbc.queryForObject(
                "SELECT content FROM test_notes "
                        + "WHERE note_id = ?",
                String.class,
                id);
    }

    public int countById(String id) {
        Integer n = jdbc.queryForObject(
                "SELECT COUNT(*) FROM test_notes "
                        + "WHERE note_id = ?",
                Integer.class,
                id);
        return n == null ? 0 : n;
    }

    public void delete(String id) {
        jdbc.update(
                "DELETE FROM test_notes WHERE note_id = ?",
                id);
    }
}
```

The service holds no mutable instance counter; each JDBC method queries by **exact row ID**. Test-managed transactions use Spring `DataSourceTransactionManager` auto-configured by Boot JDBC; when a `@Transactional` test calls the service on the same thread, `JdbcTemplate` participates in the same thread-bound transaction.

### 8.7. `ProcessProbe.java`

```java
// src/main/java/com/example/isolab/ProcessProbe.java
package com.example.isolab;

import java.util.UUID;

public class ProcessProbe {

    private static final String STARTUP_TOKEN =
            UUID.randomUUID().toString();

    public static void main(String[] args) {
        System.out.println("pid=" +
                ProcessHandle.current().pid());
        System.out.println("token=" + STARTUP_TOKEN);
    }
}
```

This is a standalone Java program for observing the boundary of static state/JVM. It is not among the 10 JUnit tests, because tests should not depend on a specific PID/UUID.

### 8.8. `junit-platform.properties`

```properties
# src/test/resources/junit-platform.properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=4
```

Classes annotated with `@Execution(CONCURRENT)` actively run methods concurrently. The integration class uses `@Isolated` so it does not run concurrently with other test classes **within the same JUnit plan**. JVM forking remains controlled by Maven Surefire.

## 9. Pure JUnit Method Isolation Tests

### 9.1. `MethodStateIsolationTest.java`

```java
// src/test/java/com/example/isolab/MethodStateIsolationTest.java
package com.example.isolab;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import static org.assertj.core.api.Assertions.assertThat;

@TestInstance(TestInstance.Lifecycle.PER_METHOD)
@Execution(ExecutionMode.CONCURRENT)
class MethodStateIsolationTest {

    private final List<String> ownValues =
            new ArrayList<>();

    @Test
    void firstMethodOwnsIndependentList() {
        assertThat(ownValues).isEmpty();
        ownValues.add("first");
        assertThat(ownValues).containsExactly("first");
    }

    @Test
    void secondMethodOwnsIndependentList() {
        assertThat(ownValues).isEmpty();
        ownValues.add("second");
        assertThat(ownValues).containsExactly("second");
    }
}
```

**2 methods.** Because `PER_METHOD` creates a new test class instance, each method uses a separate `ArrayList`. Even when JUnit runs them concurrently per the annotation, they do not mutate the same object.

**Do not replace with `static final List<String> ownValues`.** With a static list, every method mutates global state and the tests are no longer independent. `final` on the reference does not make `ArrayList` immutable or thread-safe.

### 9.2. `TempDirectoryIsolationTest.java`

```java
// src/test/java/com/example/isolab/TempDirectoryIsolationTest.java
package com.example.isolab;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import static org.assertj.core.api.Assertions.assertThat;

@Execution(ExecutionMode.CONCURRENT)
class TempDirectoryIsolationTest {

    @Test
    void firstReportIsWrittenInOwnDirectory(
            @TempDir Path dir) throws IOException {
        Path report = dir.resolve("report.txt");

        assertThat(Files.exists(report)).isFalse();
        Files.writeString(report, "report-one");

        assertThat(Files.readString(report))
                .isEqualTo("report-one");
    }

    @Test
    void secondReportIsIndependent(
            @TempDir Path dir) throws IOException {
        Path report = dir.resolve("report.txt");

        assertThat(Files.exists(report)).isFalse();
        Files.writeString(report, "report-two");

        assertThat(Files.readString(report))
                .isEqualTo("report-two");
    }
}
```

**2 methods.** Both use the filename `report.txt`, but inside two separate `@TempDir` scopes, so they do not clobber each other's file. This is test isolation through **resource naming**, not merely Java object instances.

JUnit manages temporary folder lifecycles. For a remote object store, you must design a unique prefix/bucket scope and cleanup yourself.

## 10. JVM-Global State: Intentional Locking

### 10.1. `SystemPropertyLockTest.java`

```java
// src/test/java/com/example/isolab/SystemPropertyLockTest.java
package com.example.isolab;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

import static org.assertj.core.api.Assertions.assertThat;

@Execution(ExecutionMode.CONCURRENT)
class SystemPropertyLockTest {

    private static final String KEY =
            "isolation.lab.mode";

    private void withProperty(String expected) {
        String previous = System.getProperty(KEY);
        try {
            System.setProperty(KEY, expected);
            assertThat(System.getProperty(KEY))
                    .isEqualTo(expected);
        }
        finally {
            if (previous == null) {
                System.clearProperty(KEY);
            }
            else {
                System.setProperty(KEY, previous);
            }
        }
    }

    @Test
    @ResourceLock(
            value = Resources.SYSTEM_PROPERTIES,
            mode = ResourceAccessMode.READ_WRITE)
    void writerOneRestoresGlobalState() {
        withProperty("one");
    }

    @Test
    @ResourceLock(
            value = Resources.SYSTEM_PROPERTIES,
            mode = ResourceAccessMode.READ_WRITE)
    void writerTwoRestoresGlobalState() {
        withProperty("two");
    }
}
```

**2 methods.** `@ResourceLock` prevents two writers participating under the same JUnit lock from overlapping on `System.properties`. `finally` restores the previous value even if an assertion fails. This is an option when global state **cannot be avoided**, not a pattern to encourage mutating System properties in every unit test.

**Important limits:**

- The lock only coordinates tests declaring the exact resource key within the **same test plan/engine**.
- It does not protect production threads or unannotated tests that arbitrarily modify the property.
- It does not protect across Maven Surefire forks/JVMs; each fork has its own System properties.
- It does not lock a shared DB or external broker.
- If a test modifies OS environment variables of another process, Java ResourceLock provides no protection.
- If a test must change global timezone/locale/security providers, it must restore them and declare a consistent resource lock across the entire suite.

## 11. PostgreSQL Integration: Row Ownership, Transactions, and Context Lifetime

### 11.1. `NoteStoreIntegrationTest.java`

```java
// src/test/java/com/example/isolab/NoteStoreIntegrationTest.java
package com.example.isolab;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Isolated;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.transaction.annotation.Transactional;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Isolated
@Testcontainers
@SpringBootTest
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class NoteStoreIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    NoteService notes;

    // Each JUnit test method gets its own test object:
    private String ownedId;
    private String rolledBackId;

    private static String nextId() {
        return "test-" + UUID.randomUUID();
    }

    @AfterEach
    void cleanOnlyMyCommittedRow() {
        if (ownedId != null) {
            notes.delete(ownedId);
        }
    }

    @AfterTransaction
    void verifyRollbackAfterTransactionalTest() {
        if (rolledBackId != null) {
            assertThat(notes.countById(rolledBackId))
                    .isZero();
        }
    }

    @Test
    void firstMethodOwnsAUniqueCommittedRow() {
        ownedId = nextId();

        notes.insert(ownedId, "team-a", "first");

        assertThat(notes.countById(ownedId))
                .isEqualTo(1);
        assertThat(notes.content(ownedId))
                .isEqualTo("first");
    }

    @Test
    void secondMethodDoesNotDependOnFirst() {
        ownedId = nextId();

        notes.insert(ownedId, "team-b", "second");

        assertThat(notes.countById(ownedId))
                .isEqualTo(1);
        assertThat(notes.content(ownedId))
                .isEqualTo("second");
    }

    @Test
    @Transactional
    void insertionIsRolledBackBySpringTest() {
        rolledBackId = nextId();

        notes.insert(rolledBackId, "team-c", "tx");

        // Same test thread: sees the insert within the transaction.
        assertThat(notes.countById(rolledBackId))
                .isEqualTo(1);
        // After rollback, @AfterTransaction verifies no row remains.
    }

    @Test
    void duplicateIdFailsWithoutOverwritingOwnedRow() {
        ownedId = nextId();

        notes.insert(ownedId, "team-d", "original");

        assertThatThrownBy(() ->
                notes.insert(ownedId, "team-e", "duplicate"))
                .isInstanceOf(
                        DataIntegrityViolationException.class);

        assertThat(notes.content(ownedId))
                .isEqualTo("original");
    }
}
```

**4 integration methods** sharing a Spring context and a test-class-scoped PostgreSQL container:

- Each method uses a UUID record ID, without relying on rows from a previous method.
- The two non-transactional methods create committed rows and `@AfterEach` deletes **only `ownedId`**.
- The transactional method generates a separate ID without assigning `ownedId`; Spring automatically rolls back after the test method. `@AfterTransaction` queries the DB **after rollback** to prove the row does not exist.
- The duplicate-key test proves the real database enforces the primary key rather than silently overwriting.
- `@Isolated` prevents the class from running in parallel with other JUnit classes in the same test plan, because it uses `@DirtiesContext` and a class-scoped container lifecycle.
- `@DirtiesContext(AFTER_CLASS)` closes the Spring context when the class finishes so the datasource to the stopped container is not reused.
- `@ServiceConnection` supplies the mapped PostgreSQL JDBC connection details without hard-coding `localhost:5432`.

**Limit:** The sample does not run DB test methods concurrently because Spring TestContext/`@DirtiesContext`/Testcontainers class lifecycles require control. Unique-row DB isolation supports refactoring for safe parallelization, but **does not yet prove the entire class is parallel-safe** when DDL, integration setup, or backend concurrency are involved.

### 11.2. Why Not Use `@BeforeEach DELETE FROM test_notes`?

Two methods A/B can run concurrently, or two forks can share the DB. If A's setup deletes all notes right after B inserts its fixture, B fails. In this project, cleanup is conditional on `ownedId != null` and `WHERE note_id = ?`; the transactional method cleans up via rollback.

If a test suite uses a dedicated schema per class, it can reset the schema within that ownership boundary, but it has no business truncating another CI job's database globally.

### 11.3. Why `@Transactional` Is Not Enough for Every Test

In `insertionIsRolledBackBySpringTest`, SQL runs directly on the **same thread**, sharing the Spring test-managed transaction, so rollback works. But if the method calls:

```java
CompletableFuture.runAsync(() ->
        notes.insert("async-row", "x", "y")).join();
```

the INSERT executes on another thread and does not inherit the test transaction. Similarly, a real HTTP request to `@SpringBootTest(webEnvironment=RANDOM_PORT)` runs on a server thread and does not roll back with the test client thread's transaction.

The snippet above is **deliberately risky**, and not part of the runnable test project. When testing async side effects, use unique IDs, bounded waits, and explicit test cleanup; do not rely on the parent method's rollback.

### 11.4. With JPA, Flushing Is Required

When using Spring Data JPA instead of JdbcTemplate, `save()` may not send SQL to the database until flush/commit. A test asserting on an in-memory entity and rolling back can pass falsely even with invalid constraints. Tests need `entityManager.flush()` or repository `saveAndFlush()` when verifying real constraints; with `@AfterTransaction`, you must also understand appropriate transaction propagation.

## 12. Running the Project, Verifying Total Test Count, and JVM Forks

### 12.1. Execution Sequence

```bash
java -version
mvn -version

# Pure unit JUnit tests, no Docker needed:
mvn -B -ntp -Dtest=MethodStateIsolationTest,TempDirectoryIsolationTest,SystemPropertyLockTest test

# Run PostgreSQL Testcontainers integration:
docker version
docker info
mvn -B -ntp -Dtest=NoteStoreIntegrationTest test

# Full suite (10 JUnit methods):
mvn -B -ntp test

# Try a separate fork per test class:
mvn -B -ntp -DforkCount=1 -DreuseForks=false test
```

When changing fork options, the database integration test will start a PostgreSQL container inside the fork running that class. If a real project has multiple classes sharing a broker/DB, fork-per-class only changes JVM state; external isolation must still be maintained.

| Test class | `@Test` methods | Test scope | Docker? |
| --- | ---: | --- | --- |
| `MethodStateIsolationTest` | 2 | JUnit PER_METHOD, concurrent | No |
| `TempDirectoryIsolationTest` | 2 | Filesystem @TempDir, concurrent | No |
| `SystemPropertyLockTest` | 2 | System properties lock, JVM | No |
| `NoteStoreIntegrationTest` | 4 | Spring/Postgres, isolated class | Yes |
| **Total** | **10** | Four isolation layers | Full suite yes |

These commands are instructions for the learner to **run themselves**, and do not claim that the source was compiled or executed in the authoring environment. Maven stdout, PIDs, UUIDs, Docker container IDs, and startup times depend on the host.

### 12.2. Reading Logs Effectively

- JUnit/Surefire reports: `target/surefire-reports`.
- Spring context cache DEBUG: set `logging.level.org.springframework.test.context.cache=DEBUG` in the test env when investigating reuse/cost; avoid leaving noisy logs enabled indefinitely.
- Testcontainers logs: inspect container start/stop and mapped ports.
- PostgreSQL: test-owned schema/rows; do not print credentials.
- Maven fork count/process ID: distinguish two forks from two threads in the same JVM.
- Do not rely on console log ordering of concurrent tests to infer data integrity.

### 12.3. Running Sequential Mode for Diagnostics

```bash
# Example overriding JUnit Jupiter config when comparing:
mvn -B -ntp -Djunit.jupiter.execution.parallel.enabled=false test
```

If a test passes with parallel disabled but fails when enabled, suspect shared state/races. However, "turning off parallel makes it green" does not fix the root cause. Investigate state layers, test fixture ownership, resource locks, container/cache lifecycles, and transactional boundaries.

In some build/test engines, system-property overrides may need `configurationParameters` in Surefire or test resources configured accordingly; verify that JUnit actually picked up the override rather than assuming from the command line.

## 13. Distinguishing a Test That "Passes by Luck" from an Independent Test

### 13.1. Running Tests in Random Order

A test that relies on `@TestMethodOrder` to create state for the next method is not independent. Check by:

- Running the method alone via `-Dtest=Class#method`.
- Running the class alone.
- Running the entire module.
- Changing order (random JUnit class/method order) with multiple seeds.
- Toggling concurrency within a safe scope.
- Varying fork count.
- Running on a fresh CI runner.

If a test only passes after another test, that usually indicates missing setup or state leakage.

### 13.2. Controlled Repetitions

A flaky test can pass 99 times and fail once due to a narrow race window. Run repetitions in a CI test environment, save the seed/stacktrace/timestamps on failure, and do not add `Thread.sleep(500)` as a general cure.

### 13.3. Assert Specific Signals, Not a Shared Global Counter

For message brokers:

```text
Good: receive event with the eventId created by this test, on the right queue/vhost.
Weak: queue depth increased from 0 to 1 on a shared broker.
Wrong: sleep 3s then assert "some message arrived".
```

For databases:

```text
Good: SELECT ... WHERE id = :uniqueTestId
Weak: SELECT COUNT(*) FROM orders = 1 on a shared schema
Wrong: TRUNCATE orders before each test without ownership
```

For filesystems:

```text
Good: @TempDir / unique path per method
Weak: ./target/output.json across all test classes
Wrong: delete the entire shared folder after each method
```

### 13.4. Verifying Real Cleanup

A test with `@AfterEach` whose cleanup fails can contaminate the next test. Use `try/finally` for manually created resources, assert cleanup where guarantees matter, and log clear resource IDs/namespaces (without exposing credentials).

Cleanup should be **idempotent**: calling it again should not break other data. When resource ownership is unclear or cleanup fails, report the real error; never delete more broadly just to "keep things clean".

## 14. Case Studies: Why "Run Individually PASS, Run All FAIL"?

### 14.1. Redis Flush Breaks Another Class

Class A calls `FLUSHDB` to reset cache; Class B is testing TTL on the same Redis DB. B fails because keys vanish before expiration.

**Fix:** Separate Redis Testcontainers per class or unique app/run namespaces with scoped key cleanup; never use global flush.

### 14.2. RabbitMQ Queue Has Messages "Stolen"

Class A sends a payload to `test.orders`; Class B also has a listener on the same queue. A waits for a message that B already consumed. Increasing timeouts does not solve competing routing.

**Fix:** Dedicated queues/vhosts, event correlation IDs, or separating consumer/routing tests by ownership.

### 14.3. Spring Singleton Mutated in a Previous Class

Class A mutates a `@Service` mutable field via a setter. Class B uses the same cached Spring context and sees the modified field even though B has a new test instance.

**Fix:** Design immutable/stateless beans, reset state intentionally, separate configs/contexts if genuinely needed, and avoid running parallel with `@DirtiesContext`.

### 14.4. Static Testcontainers Stops While Spring Cache Reuses

Class A stops `@Container` after the class. Class B's Spring TestContext reuses context A, so the DataSource points to the old port. B fails immediately with connection refused on query.

**Fix:** Align lifetimes (class-scoped + dirty context, context-managed container bean, or manually started suite singleton container).

### 14.5. Two JVMs Hard-Code the Same TCP Port

Surefire `forkCount=2` and two tests start an HTTP stub on `localhost:9999`. One JVM hits a bind error even though unit logic is correct.

**Fix:** Port 0/dynamic URL and proper process lifecycle management.

### 14.6. Two Jobs Delete the Same S3 Test Bucket

Each CI job has its own JVM and `@Isolated`, but shares `shared-test-bucket`. Job A's teardown deletes Job B's objects.

**Fix:** CI run ID prefix, scoped IAM policies, deletion only by owned prefix, never global bucket cleanup.

### 14.7. Preemptive Timeout Causes Transaction Leak

A JUnit method has `@Transactional`, but `assertTimeoutPreemptively(...)` runs JDBC code on another thread; data can commit outside the test transaction.

**Fix:** Bounded async logic with explicit cleanup; use `assertTimeout(...)` or an appropriate thread mode when a test-managed transaction is required, understanding test framework semantics.

### 14.8. Parallel Tests with `@MockitoBean`

Two methods share a mock inside a cached context. Method A is verifying call counts while Method B calls `reset` or stubs differently. Tests fail nondeterministically.

**Fix:** Serialize those methods/classes or refactor to per-method pure unit mocks; never assume the Spring cache creates a fresh mock per test object.

## 15. CI/CD: Designing Test Workers That Don't Step on Each Other

### 15.1. Run ID + Worker ID + Test ID

A pattern for external names:

```text
runId     = CI_PIPELINE_ID / GitHub run_id or UUID
workerId  = shard/fork/agent ID
testId    = UUID per method

postgres schema:   t_<runId>_<workerId>
redis key prefix:  it:<runId>:<workerId>:<testId>:
rabbit queue:      it.<runId>.<workerId>.<testId>.orders
kafka group:       it-<runId>-<workerId>-<testId>
s3 object prefix:  tests/<runId>/<workerId>/<testId>/
```

In real code, normalize IDs to fit each service's naming rules/length limits and permissions. Never put secrets, usernames, emails, or access tokens into resource names because they can appear in logs/metrics.

When using multiple Maven forks, you can pass `${surefire.forkNumber}` via Surefire system properties/argLine to create a per-fork prefix; `${surefire.forkNumber}` is only useful when the plugin manages the forks and does not automatically isolate resources if the app ignores the prefix.

### 15.2. CI Runner Resource Budget

- `forkCount=N` × Spring contexts × DB pools can open a huge number of connections.
- PostgreSQL containers + JVMs + Kafka/Rabbit VMs have significant memory/CPU footprints.
- Many test classes pulling images concurrently can stall the Docker daemon.
- Testcontainers Ryuk/cleanup requires proper Docker API permissions.
- A test suite timing out from an overloaded environment is not proof of broken business isolation.
- Prefer capping concurrency by RAM/CPU/DB max connections, not merely core count.
- Tests hitting external partner sandboxes must respect rate limits and request budgets rather than firing 100 parallel calls unconditionally.

### 15.3. Illustrative GitHub Actions Workflow

```yaml
name: Isolation Lab

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 20

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Check Docker
        run: |
          docker version
          docker info --format 'Engine={{.ServerVersion}}'
      - name: Run tests
        run: mvn -B -ntp test
      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: junit-surefire
          path: target/surefire-reports/
          if-no-files-found: ignore
```

This configuration uses the runner's Docker daemon to launch PostgreSQL Testcontainers. Do not hard-code mapped ports or touch a shared production DB. For untrusted PRs, do not mount a privileged Docker socket with shared secrets without an isolation policy.

Report UNIT PASS / INTEGRATION PASS / ENVIRONMENT FAILURE / SKIPPED clearly; if Docker is unavailable and mandatory integration tests are skipped, never label the entire suite "PASS".

### 15.4. Multi-Module Builds, Maven `-T`, and CI Matrices

Distinguish three different levels of concurrency:

1. **JUnit threads** within a single JVM/test engine.
2. **Maven Surefire JVM forks** within a module.
3. **Maven -T parallel modules / CI jobs** across multiple processes/containers.

A `@ResourceLock("database")` in module A **does not synchronize** with module B running in another JVM. Nor does a static lock prevent two CI jobs from sharing a namespace. That is why external resource names must include run/shard scope and perform owner-based cleanup.

### 15.5. Test Data Tenancy and Authorization

With a multi-tenant database, random fixture IDs are not enough if a query omits the tenant filter. You need unique tenant IDs/row-level security test fixtures and cross-tenant isolation tests. Test A must not delete all tenant B data with a faulty `DELETE ... WHERE tenant_id != ?`. Test resource isolation and tenant authorization are distinct boundaries.

## 16. Anti-Patterns to Avoid

| Anti-pattern | Problem | Fix |
| --- | --- | --- |
| Test method B reads data from method A | Hidden ordering | Own setup, independent fixtures |
| `@TestMethodOrder` to force a pass | Masks dependencies | Refactor test contracts |
| `static Map` as state fixture | Shared across JVM | Instance-local state/immutable |
| `@TestInstance(PER_CLASS)` + unreset mutable field | Shared test object | PER_METHOD or setup/locking |
| `@BeforeEach TRUNCATE` on shared DB | Deletes other tests' data | Unique rows/schemas |
| `@AfterEach cache.clear()` on shared Redis | Deletes other tests' entries | Namespace-scoped eviction |
| Skipping `@TempDir`, writing a fixed file | Port/path collisions | Unique directory/path |
| Hard-coding port 8080/5432/5672 | Collision/wrong mapped port | Random port/service connection |
| `@DirtiesContext` on every test | Slow, parallel hazards | Scoped state reset |
| `@MockitoBean` concurrent tests resetting mock | Stubbing races | Serialize or pure unit tests |
| `@Transactional` rolling back all side effects | Different threads/brokers | Explicit cleanup/idempotency |
| `assertTimeoutPreemptively` in a transactional test | Thread-bound tx bypassed | Same-thread deadline strategy |
| Expecting `@ResourceLock` to lock across JVMs | JUnit engine only | External coordination/namespaces |
| Expecting `@Isolated` to lock across CI jobs | Test plan scope | Per-job resources |
| Reusing Spring context with stopped Testcontainers | Connection refused | Align lifetimes |
| Unbounded container reuse in CI | Leaked fixtures, stale state | Managed lifecycle, cleanup |
| Asserting total table row count=1 | Shared data races | WHERE unique test ID |
| Fixed `Thread.sleep` for async | Timing flakiness | Bounded latches/await |
| Dropping shared DB/bucket in teardown | Destroys out-of-scope resources | Owner-only cleanup |
| Counting "No Docker" as integration pass | False PASS | Explicit environment failure |

## 17. Hands-On Exercises

**Exercise 1 — Controlled breakage of `PER_METHOD`.** Change `ownValues` to `static` in `MethodStateIsolationTest` and enable parallel execution. Observe races and cross-test contamination. Fix it with an instance field without relying on execution order.

**Exercise 2 — `PER_CLASS`.** Use `@TestInstance(PER_CLASS)` in another demo class. Add a mutable counter and determine where it must be reset and why concurrent methods require synchronization/ownership.

**Exercise 3 — TempDir.** Replace `@TempDir` with `Path.of("target/report.txt")`, run tests concurrently, and evaluate data races. Restore per-method temp directories.

**Exercise 4 — System properties.** Remove `@ResourceLock` between two tests modifying `isolation.lab.mode`, run a stress test, and explain why restoring in `finally` is insufficient when both threads modify the property simultaneously.

**Exercise 5 — Spring context cache.** Create two `@SpringBootTest` classes with the same context configuration and inject a singleton bean with a mutable field. Verify state can persist across classes; ensure tests do not depend on which class runs first.

**Exercise 6 — Context lifetime.** Add another test class using the Spring context without managing the PostgreSQL container. Observe stale connection reuse errors after the class-scoped container stops. Switch to a context-managed container or use `@DirtiesContext(AFTER_CLASS)` appropriately.

**Exercise 7 — Transaction rollback.** Run `NoteStoreIntegrationTest` and verify `@AfterTransaction` sees the row disappear. Try creating a `CompletableFuture` writing off-thread and design proper cleanup.

**Exercise 8 — Database collision.** Have two test methods use the same `note_id="fixed-id"` and run in parallel; explain why a unique PK violation indicates fixture collision rather than a business bug.

**Exercise 9 — JVM forks.** Compare `forkCount=1,reuseForks=true` against `forkCount=1,reuseForks=false` and `forkCount=2`. Observe PID/context startup counts and explain why static state is separated while external resources are not.

**Exercise 10 — Redis cache.** Create two tests sharing cache keys on a shared Redis, then add unique namespaces; compare scoped deletion with `FLUSHDB`.

**Exercise 11 — RabbitMQ queue.** Create two consumers on the same queue and demonstrate how competing consumers can receive unexpected events. Switch to test-specific queues/IDs.

**Exercise 12 — CI shards.** Design a naming scheme using runId/shardId/testId, run two CI jobs in parallel, and verify teardown never deletes objects belonging to the other job.

## 18. Self-Check Questions

**1.** Does JUnit Jupiter create a new test instance for each method by default?  
**Answer:** Yes, `PER_METHOD` is the default (unless overridden in configuration).

**2.** Does `PER_METHOD` isolate static fields?  
**Answer:** No. Static state is shared per classloader/JVM.

**3.** Can two Spring test classes share a singleton bean?  
**Answer:** Yes, if the Spring TestContext cache reuses the same ApplicationContext.

**4.** Do two different `ApplicationContext` instances necessarily use separate databases?  
**Answer:** No, their connection details can still point to the same DB.

**5.** Does `@DirtiesContext` delete Redis/DB rows?  
**Answer:** No. It marks, closes, and reloads the Spring context.

**6.** Does `@ResourceLock` lock tests across two Surefire JVM forks?  
**Answer:** No. It coordinates only within the respective JUnit test plan/engine.

**7.** Does `@Isolated` block another CI job writing to the same bucket?  
**Answer:** No.

**8.** Does a `@Transactional` test roll back commits from an `@Async` thread?  
**Answer:** Not automatically; transaction state is normally bound to the test thread.

**9.** Why is `assertTimeoutPreemptively` dangerous in a transactional test?  
**Answer:** It runs code on a different thread, which may not participate in the test-managed transaction.

**10.** Why can a static `@Container` leave a stale datasource when a subsequent class reuses the Spring context?  
**Answer:** The JUnit extension stops the container after the class, while the Spring context can remain in the cache.

**11.** Should database rows be cleaned up by own ID or global `TRUNCATE`?  
**Answer:** By owned ID/namespace, especially when running in parallel.

**12.** If two JVMs have separate static state, is a RabbitMQ queue isolated?  
**Answer:** No; it is an external resource and requires its own namespace/vhost/queue.

**13.** Does enabling JUnit parallel automatically run all tests concurrently?  
**Answer:** No; execution mode/classes mode and annotations determine that.

**14.** What is the strongest evidence that a test is independent?  
**Answer:** Running alone and inside the suite under multiple orders/concurrency/forks produces the same result, with properly scoped fixtures/cleanup and no reliance on other tests.

## 19. Isolation and Parallel Execution Review Checklist

- [ ] Every test method sets up its own prerequisites without relying on a previous method's output.
- [ ] Test instance lifecycle is explicit: PER_METHOD/PER_CLASS.
- [ ] Mutable static state is not used as an implicit fixture.
- [ ] Spring singleton beans are stateless/thread-safe or have explicit reset/ownership.
- [ ] Context cache keys and active profiles/properties are properly understood.
- [ ] `@DirtiesContext`/`@MockitoBean` tests are not run in parallel without control.
- [ ] Spring-managed transaction rollback is only relied upon within the proper thread/propagation scope.
- [ ] Preemptive timeouts are not used in transactional tests without understanding thread semantics.
- [ ] Database fixtures use unique IDs/tenant scopes and owner-based cleanup.
- [ ] No global TRUNCATE/FLUSHDB/PURGE on shared external resources.
- [ ] Redis prefixes, broker vhosts/queues, Kafka topics/groups, and object storage prefixes are namespaced.
- [ ] Random ports or Boot/Testcontainers `@ServiceConnection` are used instead of hard-coded localhost mapped ports.
- [ ] Temp files use `@TempDir` or unique paths.
- [ ] System properties/TimeZone/Locale modifications are restored and appropriately synchronized.
- [ ] `@ResourceLock` is not mistaken for a distributed lock.
- [ ] `@Isolated` is not mistaken for fork/CI job isolation.
- [ ] Maven Surefire `forkCount`/`reuseForks` and JUnit parallel modes are intentionally configured.
- [ ] Spring Context cache lifetime aligns with Testcontainers container lifetime.
- [ ] Testcontainers extensions are not mixed with a conflicting singleton container lifecycle pattern.
- [ ] CI run/shard identifiers are used for external namespaces when needed.
- [ ] Cleanup uses `try/finally`/properly scoped teardown without breaking other tests.
- [ ] Async/background tasks are stopped or boundedly awaited before cleanup.
- [ ] Test counts/skips/environment errors are reported clearly; integration PASS is never claimed when Docker is missing.
- [ ] Tests are executed in multiple orders/shards when investigating flaky behavior.

## 20. Official Documentation

- [JUnit Jupiter 5.12 — Test Instance Lifecycle & Parallel Execution](https://docs.junit.org/5.12.0/user-guide/): `PER_METHOD`/`PER_CLASS`, parallel config, `@ResourceLock`, `@Isolated`, and `@TempDir`.
- [Spring Framework 6.2 — TestContext Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): static cache by context configuration, per JVM, and `@DirtiesContext`.
- [Spring Framework 6.2 — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html): cases where parallel execution should be avoided.
- [Spring Framework 6.2 — Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): thread-bound rollback and preemptive timeout warning.
- [Spring Framework 6.2 — @DirtiesContext](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html): context lifecycle.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, context configuration.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection` and container lifecycle.
- [Testcontainers — Container Lifecycle Management](https://testcontainers.com/guides/testcontainers-container-lifecycle/): class-scoped vs singleton vs cached Spring context.
- [Testcontainers — JUnit Jupiter integration](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, static vs instance `@Container` lifecycle.
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): real PostgreSQL isolation tests.
- [Apache Maven Surefire — Fork Options](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options.html): `forkCount` and `reuseForks`.
- [Apache Maven Surefire — Plugin Parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo): user properties and fork behavior.
- [Spring Framework 6.2 — Bean Overrides in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html): mocks, spies, context customization.
- [Spring Framework 6.2 — Executing SQL Scripts](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/executing-sql.html): `@Sql` and transactional modes.

**Conclusion:** Test independence is more than just "a new object per `@Test`". You must distinguish instance fields, cached Spring contexts, static state inside each JVM, and external resources shared across processes. Choose unique test data/resources, ownership-based cleanup, transaction rollback on the proper thread, selective parallelism, and aligned Testcontainers/context lifecycles. `@ResourceLock` and `@Isolated` are useful within JUnit's scope, but cannot replace external namespaces or locking across two JVMs/CI jobs.