# Test fails only in the full suite or on CI

## 1. Symptom: a test passes on its own, yet fails when run with other tests

In **Spring Boot - testing**, under **Test Troubleshooting**, the question to answer is not just “why is the test failing?” but **“which condition appears only when running the full suite or on CI?”**. If `OrderServiceTest` passes when targeted individually with `--tests` yet fails under `./gradlew test`, the test likely depends on state or an environment condition absent in isolated runs.

Examples include:

- Test A leaves a row in the database; Test B assumes an empty table.
- An earlier test class increments a counter on a singleton Spring bean; a later class reuses the same `ApplicationContext` and observes that counter.
- JUnit `@TestMethodOrder` accidentally hides that Test B requires Test A to run first.
- A `@MockBean`/Mockito stub is reset or retains state unexpectedly when the Spring TestContext cache is reused.
- A test invokes `@Async`/`CompletableFuture` and asserts immediately before the worker finishes.
- Two test classes share the same port, file, Redis key, Kafka topic, or container; running in parallel causes collisions.
- A `@Transactional` test method rolls back JDBC writes, while asynchronous work or remote API calls execute outside the transaction and leave side effects.
- CI uses a different JDK, timezone, locale, OS, filesystem case sensitivity, dependency versions, or secrets setup than a developer laptop.
- A test calls `new Random()`, `Instant.now()`, `Thread.sleep`, or depends on thread scheduling order.
- A Spring context is closed via `@DirtiesContext` or cache eviction while another test is using it.
- Gradle splits tests across multiple JVM forks; static state and the Spring cache are not shared the way they are in a single IDE process.
- The full suite triggers a code path, rate limit, connection pool limit, timeout, memory pressure, or data volume never hit by an isolated test.

**Goal:** replace “re-run until green” with a reproducible investigation workflow: identify the **first failing test**, task/fork, data source, execution order, concurrency, and environment; collect evidence; minimize the failing test set; fix the root leak source; and confirm **both isolated runs and the full suite**.

This article provides a Java 17 + Spring Boot 3.3.0 + JUnit Jupiter + Spring JDBC/H2 project containing **inherently stable** tests demonstrating data cleanup, singleton state reset, commit/rollback, a fake Clock bean, and safe context reuse across test classes. Flaky anti-patterns appear only as **diagnostic snippets, excluded from the runnable suite**. Expected results are described as **expected**, not claims of actual Gradle execution.

## 2. Learning objectives

After this article, you will be able to:

1. Distinguish **suite-only**, **CI-only**, **intermittent flaky**, **order-dependent**, and **parallelism** failures.
2. Capture a reliable baseline covering full suite, single test, and test pairs along with exact command/commit/JDK.
3. Read Gradle/JUnit XML reports and distinguish failed, skipped, aborted, no-tests, and build-cache results.
4. Separate test failures from Spring `ApplicationContext` startup failures and container readiness failures.
5. Understand that the Spring TestContext cache retains singleton beans and does not automatically wipe application state.
6. Know that `@DirtiesContext` closes/evicts a context without automatically wiping data in external systems.
7. Use `@BeforeEach`/`@AfterEach` with properly scoped cleanup, independent of test method order.
8. Understand test-managed `@Transactional` and default rollback, especially around background threads.
9. Distinguish shared static fields, singletons, in-memory caches, databases, filesystems, and remote resources.
10. Scope test data by unique IDs/namespaces/transactions so parallel execution is safe.
11. Apply `@ResourceLock`/`@Execution(SAME_THREAD)` when resources are genuinely shared, while knowing per-JVM limits.
12. Distinguish Gradle `maxParallelForks` from JUnit Jupiter in-JVM parallel execution.
13. Hunt down race conditions without using `Thread.sleep` as an oracle.
14. Understand why `ThreadLocalRandom`/`new Random()`, the system clock, and timezones introduce flakiness.
15. Inject `Clock` and fixed times into Spring tests; use seeded PRNGs when deterministic replay is needed.
16. Diagnose Linux/CI-only failures caused by case-sensitive paths, line endings, charsets, or permissions.
17. Verify JDK vendor/version, Gradle wrapper, dependency locks/BOMs, timezone, locale, and CI service health.
18. Inspect Hikari pools, socket/file handles, port bindings, thread leaks, and shutdown lifecycles.
19. Shrink a failing suite via **test pairs/bisection** without jumping to premature conclusions.
20. Use `--rerun-tasks`/`--no-build-cache` for fresh execution without confusing cache bypass with fixing flakiness.
21. Explain why running a single test alters failure conditions and turns bugs into heisenbugs.
22. Avoid slapping `@TestMethodOrder` onto tests to “patch” undefined state dependencies.
23. Avoid applying `@DirtiesContext` to every test instead of proper DB/cache cleanup.
24. Distinguish CI environment misconfiguration from real production bugs triggered under load.
25. Design CI failure artifacts containing seeds, selectors, executed tests, failure stacks, logs, and resource IDs.
26. Write regression tests reproducing the real failure and verify fixes across repeated full-suite runs when appropriate.
27. Never report “passed successfully” after merely authoring code and expected assertions.

## 3. Diagnostic diagram

```text
Single test PASS, suite FAIL?
       |
       +-- Same commit/build inputs?
       |      -> Verify branch, JDK, dependencies, task.
       |
       +-- Fails only after another test?
       |      -> Shared static/singleton/DB/cache/file/mock state.
       |
       +-- Fails only with parallel enabled?
       |      -> Race, resource collision, context eviction.
       |
       +-- Fails only on CI OS/host?
       |      -> Time zone, locale, env vars, paths,
       |         startup readiness, CPU, ports, memory.
       |
       +-- Fails randomly even alone?
       |      -> Clock, PRNG, asynchronous timing,
       |         network/service nondeterminism.
       |
       +-- Fails after many tests?
       |      -> Connection/thread/file leak,
       |         resource exhaustion, eventual quotas.
       |
       +-- Changes when --tests selects subset?
              -> Test order, discovery/filter,
                 shared state or different context lifetime.
```

**Do not modify code immediately after the first failure** without knowing the reproduction condition. A failure might mean “cannot connect to Redis” because a service is not ready, or “expected 0, actual 1” because an earlier test failed to clean the DB. Those two bugs require completely different fixes.

## 4. One failure can have multiple dimensions

| Failure type | Running alone | Running in suite | Running on CI | Initial hypothesis |
| --- | --- | --- | --- | --- |
| Shared state pollution | Pass | Fail | May fail | Static/bean/DB state leaked |
| Method-order dependency | Passes via one path | Fails when reordered | Order-dependent | Missing fixture setup |
| Parallel race | Usually passes | Fails intermittently | Higher core count exposes it | Unsynchronized state |
| Machine-dependent test | Passes locally | May pass local suite | Fails on CI | TZ, locale, OS, JDK |
| Timeout under load | Pass | Fails near threshold | Fails on slower CI | Sleep/busy wait/IO |
| External service not ready | Passes if service warm | Fails by startup order | Fails on fresh CI | Readiness/health |
| TestContext mutation | Pass | Fails on cached context reuse | Depends on JVM | Singleton/context cache |
| Resource leak | Pass | Fails after many tests | Fails on longer CI jobs | Pools, threads, files |
| Random input | Passes or fails by seed | Pass/fail | Hard to reproduce | Seed not recorded |
| Wrong CI command | Passes locally | Unrelated | Tests skipped/not discovered | Task/filter/build setup |

This is a **hypothesis matrix**, not a guaranteed diagnosis for every exception. Corroborate it with logs and test outputs.

## 5. Evidence-based investigation workflow

### Step 1: capture the failing environment

Record the **exact Gradle/Maven command**, repository revision, OS, architecture, JDK vendor/version, Gradle wrapper, timezone, locale, Spring Boot/JUnit versions, CI image digest, profiles, secrets availability, test worker settings, and service addresses. Preserve the full initial stack trace rather than only “There were failing tests”.

Example commands:

```bash
java -version
./gradlew --version
./gradlew test --info
```

Gradle 8.x can report `:test UP-TO-DATE`/`FROM-CACHE` when reusing prior outputs. That alone does not prove tests executed in the current invocation. When you need a **fresh reproduction**:

```bash
./gradlew test --rerun-tasks --no-build-cache --info
```

`--rerun-tasks` also forces unrelated tasks to re-execute; use it deliberately for diagnosis rather than enabling it permanently across all CI builds.

### Step 2: run a single test

```bash
./gradlew test --tests 'example.suite.OrderSuiteIsolationTest'
```

If the test class passes, try running the full suite. If one method fails inside the suite, target its exact FQN:

```bash
./gradlew test --tests \
  'example.suite.OrderSuiteIsolationTest.rollbackRemovesRowButMemoryStateRequiresReset'
```

**Selecting a single test changes many variables:** other classes do not run, contexts start fresh, the database is empty, random draws shift, and parallelism and memory pressure drop. Therefore “passes alone” is **a clue for narrowing the scope**, not proof that the test itself is sound.

### Step 3: find the polluting test

If A passes alone and B passes alone, yet A→B fails, check:

- Which row/file/key did A create without cleaning up?
- Did A mutate static `System.setProperty`/`TimeZone.setDefault`/`Locale.setDefault` without restoring it?
- Did A alter singleton/cache/mock state in a context shared with B?
- Did A launch background threads, scheduled jobs, or unfinished async tasks?
- Did A close/`@DirtiesContext` a context or DB container that B relies on?
- Did A leave a test clock or singleton PRNG in an altered state?
- Did A change an external service, message offset, or port listener?

### Step 4: separate sequential from parallel

Keeping the **same test set** and data, toggle JUnit parallelism and Gradle forks independently. If failures appear only in parallel, hunt for resource collisions/races. If failures occur sequentially depending on class order, look for leaked state or missing cleanup.

### Step 5: minimize the reproducer

Avoid simply re-running a 20-minute suite repeatedly. Shrink down to a pair of classes A/B or a minimal subset (delta debugging/bisection). Preserve the necessary conditions: same JVM/fork, same cache key, same database/container, and the same order or parallel mode if timing-sensitive. Dropping the polluting class yields a green subset and misleads the diagnosis.

### Step 6: fix the actual root cause

For example, if Test A forgot to delete a row, fix fixture cleanup/transaction isolation rather than adding a retry assertion in Test B. If an async callback has not finished, use proper synchronization/await conditions instead of endlessly inflating `Thread.sleep`.

### Step 7: verify

Re-run the **minimal reproducer** (red before fix, green after), then the **full suite**, and finally an equivalent CI environment. For rare race bugs, run an appropriately justified number of iterations and inspect results—never declare 0% failure probability from a single green run.

## 6. Spring TestContext cache and singleton state

The Spring TestContext Framework caches `ApplicationContext` instances keyed by merged configuration. Two test classes with equivalent `@SpringBootTest` configurations can reuse the **same bean graph**, including singletons, JPA/entity manager factories, caches, executors, and DB connection pools.

```text
Class A -- @SpringBootTest(config X) ---+
                                       |
                                       v
                             ApplicationContext X
                             (singleton state, clients)
                                       ^
                                       |
Class B -- @SpringBootTest(config X) ---+
```

If Class A calls `attemptCounter.increment()` without resetting state, Class B can observe A's count even though JUnit instantiates a brand-new test class object for B.

### 6.1. Context reuse does not reset test state

Spring may create a fresh JUnit test class instance per test method, yet injected singleton beans still come from the cached context. Thus:

```java
@BeforeEach
void setUp() {
    // A new test object is not necessarily
    // a new Spring ApplicationContext.
}
```

does not clear DB/Redis/bean state on its own. Tests must manage state at the right layer.

### 6.2. Different cache keys alter outcomes

Two classes differing in `@ActiveProfiles`, inline properties, `@DynamicPropertySource`, `@MockBean`/`@SpyBean` (Boot 3.3), or test customizers can produce **two separate contexts**, preventing singleton leaks from crossing between them. If tweaking an annotation makes the error vanish, do not declare it fixed: you may have forced Spring to create a second context and merely hidden the state pollution.

### 6.3. The context cache is per JVM

The static Spring TestContext cache is not shared across Gradle forks, IDE processes, or CI shards. A test that passes in its own fork yet fails when sharing a fork with other classes points toward context reuse. Switching forks may mask the bug at the price of slower startup.

### 6.4. @DirtiesContext

`@DirtiesContext` marks a context for closure/eviction so the next lookup loads a fresh one. It helps when a test genuinely mutates unresettable config/bean graphs, yet **should not be used as a default database cleaner**. Out-of-process databases still retain rows even if the context restarts. Excessive `@DirtiesContext` slows suites down, and parallel tests can encounter closed contexts mid-execution.

### 6.5. Cache eviction

Even without `@DirtiesContext`, the cache is a bounded LRU cache (maximum 32 contexts by default). When a suite generates many cache keys, an earlier context gets evicted and reloaded. Never hardcode assumptions that “Class A and B always share the exact same bean instance” if contexts in between trigger eviction. Enable DEBUG logging on `org.springframework.test.context.cache` when diagnosing.

## 7. Test order dependency

An anti-pattern:

```java
class BadOrderTests {

    static String lastReference;

    @Test
    void createReference() {
        lastReference = "ORDER-7";
    }

    @Test
    void useReference() {
        assertEquals("ORDER-7", lastReference);
    }
}
```

**Intentionally broken snippet, not part of the runnable project.** When `useReference` runs first or executes alone in a fresh JVM, the static field is null. Passing under one specific order does not make tests independent.

**Fix:** each test creates the fixture it needs:

```java
class GoodOrderTests {

    @Test
    void usesOwnReference() {
        String reference = "ORDER-7";
        assertEquals("ORDER-7", reference);
    }
}
```

### 7.1. Why shouldn't `@TestMethodOrder` be used as a patch?

`@TestMethodOrder(MethodOrderer.OrderAnnotation.class)` can enforce ordering to express an intentional workflow integration scenario. Yet it does not make tests independent and causes failures whenever someone runs a single method alone. If a test depends on an earlier step's state, put **all steps of that scenario into one test** or use explicit per-test fixture lifecycle setup.

### 7.2. `@BeforeAll` is not `@BeforeEach`

`@BeforeAll` runs once per class/container and does not reset state between methods. When each method requires an empty DB, use `@BeforeEach` or controlled transaction rollback. JUnit `@TestInstance(PER_CLASS)` reuses the same test instance; mutable instance fields can likewise leak across methods.

### 7.3. Random test order to expose hidden dependencies

JUnit Jupiter can configure a random method orderer:

```properties
junit.jupiter.testmethod.order.default = org.junit.jupiter.api.MethodOrderer$Random
```

This is an **experimental diagnostic configuration**; placed in `junit-platform.properties`, it varies method order. It exposes order coupling without replacing proper fixture cleanup; record the random order seed/runner details per your JUnit version if exact replay is needed.

## 8. `@Transactional` tests and data isolation

Spring TestContext `@Transactional` on a test method/class creates a **test-managed transaction** that normally rolls back after the test when a suitable transaction manager is detected.

```java
@SpringBootTest
@Transactional
class TransactionalRepositoryTest {
    @Test
    void savesSomething() {
        repository.save(...);
        // By default test transaction rolls back.
    }
}
```

This snippet is not runnable because repository and imports are omitted. It illustrates Spring Test's default rollback behavior.

### 8.1. Rollback covers only its own transaction boundary

If test code publishes a Kafka message, calls a REST service, writes a file, sets a Redis key, or spawns a background thread on a separate transaction, test JDBC/JPA rollback **does not undo those side effects**. A test may pass alone while leaving a Redis key that breaks the next class.

### 8.2. `@SpringBootTest` RANDOM_PORT

With a live HTTP server and client in tests, the client/test thread's transaction **does not wrap the server thread's transaction**. The server handles requests in its own transaction or auto-commit mode. Thus `@Transactional` on the JUnit method does not roll back data written by HTTP handlers; use proper cleanup or isolated databases instead.

### 8.3. `@BeforeEach`/`@AfterEach` and test-managed transactions

In Spring TestContext transactional tests, JUnit `@BeforeEach`/`@AfterEach` methods normally execute inside the test-managed transaction. If cleanup must run **outside** that transaction so deletes actually commit, use `@BeforeTransaction`/`@AfterTransaction` or appropriate fixture mechanics; never drop `jdbc.deleteAll()` into `@AfterEach` and assume it always commits.

### 8.4. `@Sql`

`@Sql` runs database setup/cleanup scripts with configurable execution phase and transaction mode. On a shared DB under parallel tests, a script running `DELETE FROM orders` on a shared table deletes other tests' rows. Use per-test schemas/namespaces or locking rather than ambiguous cleanup ordering.

### 8.5. Tests without `@Transactional`

The lab below **does not put `@Transactional` on the JUnit test methods**. Service methods open their own transactions. That lets the test inspect committed/rolled-back DB state **after the service call returns**, while `@BeforeEach`/`@AfterEach` clean up independently. This makes transaction ownership explicit.

## 9. Mockito `@MockBean` and state between test methods

In Spring Boot 3.3, `@MockBean` replaces a Spring bean with a Mockito mock in the `ApplicationContext`. Mock definitions contribute to the context cache key, and bean mocks are reset by Spring Boot test support according to configuration/lifecycle.

Common traps:

- Test A stubs a mock, and Test B assumes that stub remains active.
- Test B verifies interactions originating in Test A (if a mock is not reset as expected).
- One test manually invokes `Mockito.reset(mock)` while another test uses the same cached mock in parallel.
- A test specifies `@MockBean(reset=MockReset.NONE)` and forgets manual cleanup.
- Using `@SpyBean` wraps a target object carrying real mutable internal state.
- Placing `Mockito.when(...).thenReturn(...)` in `@BeforeAll` clashes with per-method reset lifecycles.
- Divergent mock definitions across test classes spawn **many contexts**, altering startup profiles.

### 9.1. Never rely on another test's stubbing

```java
@MockBean
PaymentClient paymentClient;

@BeforeEach
void stubGateway() {
    when(paymentClient.charge(any()))
            .thenReturn(new Receipt("ok"));
}
```

This is an **illustrative snippet** (types and Mockito imports omitted), not part of the runnable lab. When per-test mock behavior is needed, define stubs inside each test's own lifecycle rather than relying on execution order. For plain unit tests, prefer `@Mock`/`@InjectMocks` or standalone fake collaborators.

### 9.2. Do not rush to `@DirtiesContext` on mock verification failures

When failures stem from retained Mockito interactions/stubs, fix mock reset lifecycles and test isolation. `@DirtiesContext` can hide symptoms while re-bootstrapping contexts repeatedly without fixing external state.

### 9.3. Boot version boundary

This article pins Spring Boot 3.3. Newer releases introduce `@MockitoBean`/`@MockitoSpyBean` in Spring Framework. Never copy annotations or configuration semantics from another Boot generation without verifying version compatibility.

## 10. Parallel execution: two different kinds of parallelism

### 10.1. JUnit Jupiter parallel inside the same JVM

JUnit Jupiter executes sequentially unless parallelism is enabled:

```properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
```

This is an **illustrative configuration**; it is disabled by default in the runnable project. In parallel mode, JUnit methods/classes run concurrently on multiple threads in the **same JVM**, sharing static fields and the Spring context cache.

### 10.2. Gradle `maxParallelForks`

`maxParallelForks=2` runs up to two **test worker JVM processes** concurrently; each JVM gets its own static state and Spring TestContext cache. This differs from JUnit thread-level parallelism:

- JUnit parallel: shared memory, prone to races on static/bean fields.
- Gradle forks: separate JVM memory, yet still capable of colliding on external DBs, Redis, files, and ports.
- CI shards: multiple machines/containers; external resource namespacing becomes even more critical.

### 10.3. `@ResourceLock`

JUnit Jupiter provides `@ResourceLock` to coordinate tests **within the same JUnit execution/JVM** when accessing a shared resource:

```java
@ResourceLock(
        value = "suite-lab-database",
        mode = ResourceAccessMode.READ_WRITE)
class DatabaseIsolationTest {
    // Its @BeforeEach and @AfterEach participate
    // in the resource lock's protected lifecycle.
}
```

**Snippet**; real imports and tests appear in the runnable lab. Apply the same lock key across classes that must mutually exclude concurrent access to a shared database. Locks do not span Gradle forks or CI machines, so multi-process setups still require isolated namespaces/databases.

### 10.4. `@Execution(SAME_THREAD)`

`@Execution(ExecutionMode.SAME_THREAD)` controls execution mode for JUnit nodes and helps when a class depends on thread affinity. Yet it **does not provide global mutual exclusion** across unrelated classes. For shared resources, use `@ResourceLock` or provider-level isolation rather than assuming one annotation eliminates all races.

### 10.5. `@DirtiesContext` + parallel

Spring advises against or warns carefully about parallelizing tests using `@DirtiesContext`, `@MockBean`/`@SpyBean`, mutable shared services, or order constraints. If Context A is in use by one test while another thread evicts/closes it, A can hit “ApplicationContext no longer active” or resource failures. Fix lifecycle and serialization instead of adding blind retries.

## 11. Race conditions and hard-to-reproduce bugs

Anti-pattern:

```java
class UnsafeCounter {
    int count;

    void increment() {
        count++; // read-modify-write, not atomic
    }
}
```

Two threads can read the same old value and write back the same new value, losing an increment. Locally under low load, timing may hide the bug; under heavy CI load or parallel runs, it surfaces.

Fix:

```java
class SafeCounter {
    private final AtomicInteger count =
            new AtomicInteger();

    int increment() {
        return count.incrementAndGet();
    }
}
```

This snippet requires importing `java.util.concurrent.atomic.AtomicInteger`. **`AtomicInteger` does not automatically make a compound business flow atomic** (such as “check existence → insert → publish message”); boundary-level transactions, locks, or idempotency remain essential.

### 11.1. `Thread.sleep` does not synchronize threads

```java
startAsyncJob();
Thread.sleep(100);
assertEquals("DONE", status());
```

Anti-pattern: 100ms is pure guesswork. A slower CI runner may not finish in time while a fast laptop passes. Use `Future.get(timeout)`, `CompletableFuture.join()` with timeouts, `CountDownLatch`, `Awaitility`, or virtual-time schedulers where appropriate.

### 11.2. Never use unbounded timeouts

Synchronization needs a **finite deadline** so a hung test does not stall CI indefinitely. Choose timeouts based on real SLOs/test scale, without asserting that an operation must finish under 1ms on virtualized runners. The lab uses 30 seconds for tiny CPU tasks—that acts as a hang guard, not a latency benchmark.

### 11.3. Synchronizing tests can still hide production races

If switching all tests to sequential makes the error vanish, you have confirmed concurrency plays a role. However, production code may still have a race. Verify thread safety on code paths invoked concurrently in production rather than merely disabling test parallelism to turn CI green.

## 12. Filesystem, ports, and CI environment

### 12.1. File paths and case sensitivity

On some OSes/filesystems, `src/test/resources/Users.json` and `users.json` are distinct; on another developer machine, mismatches get masked. Always load classpath resources with exact **filename casing** without relying on the current working directory:

```java
try (InputStream in =
        getClass().getResourceAsStream(
                "/fixtures/users.json")) {
    assertNotNull(in);
}
```

This snippet assumes imports and an existing resource; not part of the runnable lab. If CI gets null, verify what actually ended up packaged in `build/resources/test` rather than randomly tweaking slashes.

### 12.2. Line endings and charsets

Windows often uses CRLF while Linux uses LF. Comparing raw file strings can fail due to line endings or platform default charsets. When the contract is newline-agnostic text content, normalize intentionally. When testing wire serialization requiring fixed newlines, **assert the exact contract** and read using `StandardCharsets.UTF_8`.

### 12.3. Temp files

Do not share `/tmp/test-output.json` across tests. JUnit `@TempDir Path tempDir` gives each test its own directory; with multi-fork runs or external resources, still guard against collisions if code writes outside `tempDir`.

### 12.4. Ports

Binding a server or test service to fixed `8080`/`9092` collides with parallel tests or CI services. Use random ports (`@SpringBootTest(webEnvironment=RANDOM_PORT)`) and inject the actual local server port in HTTP tests; with Testcontainers, read the runtime-assigned mapped port.

### 12.5. Timezone, locale, and dates

`LocalDate.now()` reads the process default timezone. Asserting “today equals ...” can fail around midnight or when CI runs in UTC vs UTC+07 locally. Inject `Clock` and `ZoneId`. When formatting numbers or currencies, specify an explicit `Locale`.

### 12.6. Permissions and working directory

CI agents may run as a user without write permission under the repository root, or mount the workspace read-only. Use test-specific temp directories; write only to permitted paths and never modify source files during tests.

## 13. External dependencies and readiness

Tests may use Docker/Testcontainers, PostgreSQL, Redis, Kafka, LocalStack, or HTTP servers. A dev machine might have a pre-warmed container running, whereas fresh CI containers need time for health checks.

**Never use `Thread.sleep(10_000)` as a default readiness gate.** Use provider-specific wait/health mechanisms such as Testcontainers `waitingFor(...)`, JDBC connection validation, HTTP health endpoints, or bounded **backoff retries with finite timeouts**.

### 13.1. Testcontainers lifecycle

When reusing a cached Spring context, containers must outlive clients held inside that context. If a per-class container stops after Test A while Test B reuses the cached context, cached clients can point to a dead mapped port. Align container lifecycles with the context/JVM or apply `@DirtiesContext` intentionally—never leave cached contexts pointing to dead resources.

### 13.2. Database schemas and fixtures

Embedded H2 and production PostgreSQL differ in SQL dialect, transaction isolation, and constraints. A green H2 suite does not prove PostgreSQL concurrency behavior. When failures happen only on CI against real DBs, run Testcontainers matching the production engine/version with stable migrations and fixtures.

### 13.3. Remote services and secrets

CI may lack credentials/env vars, hit proxy/network blocks, face API rate limits, or target different endpoints. Never make tests pass by logging raw tokens/credentials. For unit tests, mock/fake external dependencies; for integration tests, manage credentials, sandbox accounts, and health/permission checks cleanly.

### 13.4. Container mapped ports and addresses

Never hardcode laptop host/port values. Use `@ServiceConnection` (Boot 3.1+) or `@DynamicPropertySource`/version-appropriate container APIs while managing context cache lifecycles.

## 14. JVM, Gradle, JUnit, and profiles

A suite might run locally on JDK 17/Gradle 8.7 while CI runs JDK 21/another Gradle version or enables test parallelism. Even on identical source code, serialization, timezones, reflection/module access, or dependency resolution can diverge.

Environment checklist:

```text
Commit SHA
JDK vendor + java -version
Gradle wrapper version
Spring Boot + Spring Framework + JUnit versions
OS/arch and container image digest
Default timezone and locale
JAVA_TOOL_OPTIONS / JVM args
Active Spring profiles
Gradle -P properties / --tests selectors
JUnit parallel configuration parameters
Gradle maxParallelForks + forkEvery
Datasource URL/schema/migration version
Docker engine + Testcontainers version
External service versions, ports, health
Filesystem permissions, path case, charset
Test source data and random seed
```

### 14.1. Gradle test JVM differs from Gradle daemon JVM

System properties passed to the Gradle daemon do not automatically propagate to **forked test JVMs**. Configure test properties directly on the `Test` task:

```groovy
tasks.named('test', Test) {
    systemProperty 'user.timezone', 'UTC'
    systemProperty 'junit.jupiter.execution.parallel.enabled',
            'false'
}
```

Illustrative snippet; the runnable `build.gradle` in section 16 provides the full configuration. When business rules depend on a specific local timezone, pass `ZoneId` explicitly into business logic instead of forcing the entire JVM's default timezone.

### 14.2. JUnit seeds

JUnit method execution order may be deterministic yet must never be relied upon by business tests. When using random ordering or randomized fixture generators, save the seed and exact failing command. Seeds still do not govern thread scheduling, networking, DB state, or class order across every runner.

### 14.3. Module/test selectors

`./gradlew :orders:test` does not run `:billing:test`; `--tests` runs only a subset. A “green” CI job that skipped tasks or discovered zero tests is a coverage gap—always check actual XML/HTML reports rather than confusing zero-test runs with suite-only issues.

## 15. Lab design: deterministic tests that still reveal state-leak mechanics

We build:

1. A small Spring Boot app using in-memory H2 and JDBC transactions.
2. `OrderStore` operating on the `orders` table.
3. `OrderService` executing `@Transactional` commits and rollbacks.
4. `AttemptCounter` holding mutable singleton state; increments on every service call and **does not roll back when the DB transaction rolls back**.
5. `FixedClockTestConfig` as shared test configuration providing `Clock.fixed`.
6. Two `@SpringBootTest` classes sharing **the same configuration** so Spring context reuse is possible, while each class resets DB rows and the counter in `@BeforeEach`/`@AfterEach`.
7. A plain JUnit class testing time, randomness, and concurrency with no Spring context.
8. `@ResourceLock("suite-lab-database")` guarding H2/bean state access when JUnit parallel execution runs inside one JVM.
9. Zero `@DirtiesContext` and zero `@TestMethodOrder` in the runnable tests.
10. Every test is independent; running one class or the entire suite exhibits identical expected behavior.

**Note:** `@ResourceLock` coordinates Jupiter tests within a single JVM execution sharing the same lock key; it does not guard an external DB shared across multiple Gradle test worker JVMs. The lab uses embedded H2 and `maxParallelForks=1` for a clean baseline. In real projects using multiple forks/shards, isolate external resources per process.

## 16. Runnable Java 17 + Spring Boot 3.3 project

### 16.1. Directory layout

```text
suite-isolation-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/suite/
    │   │   ├── SuiteLabApplication.java
    │   │   ├── Receipt.java
    │   │   ├── OrderStore.java
    │   │   ├── AttemptCounter.java
    │   │   └── OrderService.java
    │   └── resources/
    │       └── schema.sql
    └── test/java/example/suite/
        ├── FixedClockTestConfig.java
        ├── OrderSuiteIsolationTest.java
        ├── AnotherOrderSuiteTest.java
        └── PureIsolationTest.java
```

No web server, Kafka, Redis, or Docker required. This is an H2/`JdbcTemplate` integration setup with a real transaction manager and fixed test clock. If the project has no Gradle Wrapper yet, generate one with Gradle 8.7 or a compatible version and commit wrapper files; `./gradlew` works only once the wrapper is present.

### 16.2. settings.gradle

```groovy
rootProject.name = 'suite-isolation-lab'
```

### 16.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0

    systemProperty 'user.timezone', 'UTC'
    systemProperty 'junit.jupiter.execution.parallel.enabled',
            providers.gradleProperty('junitParallel')
                    .orElse('false')
                    .get()

    testLogging {
        events 'passed', 'failed', 'skipped'
        exceptionFormat 'full'
    }
}
```

**Breakdown:**

- `spring-boot-starter-jdbc` enables JDBC/`JdbcTemplate`/transaction support.
- H2 is a runtime dependency; Boot auto-configures an embedded DataSource when no other datasource is provided.
- `spring-boot-starter-test` supplies JUnit Jupiter, Spring Test, Mockito, and AssertJ.
- `junit-platform-launcher` avoids implicit launcher mismatches across Gradle versions.
- `useJUnitPlatform()` selects the JUnit 5 engine.
- `junitParallel=false` by default keeps a deterministic baseline. To experiment with JUnit parallelism, run `-PjunitParallel=true`; for genuine concurrent node execution, add the corresponding Jupiter mode setting (enabling `enabled` alone may not run all methods concurrently).
- `maxParallelForks=1` and `forkEvery=0` keep a single test worker JVM in the lab, distinct from JUnit threads.
- `systemProperty user.timezone` configures the **test JVM**, not just the Gradle daemon.

## 17. SuiteLabApplication.java and schema.sql

### 17.1. SuiteLabApplication.java

**src/main/java/example/suite/SuiteLabApplication.java**

```java
package example.suite;

import java.time.Clock;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SuiteLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                SuiteLabApplication.class, args);
    }

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

`Clock` is an explicit dependency. Tests can override it with a frozen clock via `@TestConfiguration` without altering production business code. Injecting `Clock` avoids midnight boundary and CI timezone flakiness.

### 17.2. schema.sql

**src/main/resources/schema.sql**

```sql
create table if not exists orders (
    ref varchar(80) primary key
);
```

Spring Boot SQL initialization with embedded H2 creates the table when the `ApplicationContext` boots. The lab uses H2 so cleanup is `DELETE FROM orders` without complex foreign keys. **In production databases**, migrations (Flyway/Liquibase), schemas, and transactional isolation must be managed separately.

### 17.3. Why doesn't the table use auto-generated IDs?

All tests choose `ref` explicitly, making duplicate keys and cleanup crystal clear. We want an exercise on **test isolation**, free from noise caused by H2 identity sequences. If production logic depends on generated IDs or uniqueness, test those separately against the real provider.

## 18. Receipt.java and AttemptCounter.java

### 18.1. Receipt.java

**src/main/java/example/suite/Receipt.java**

```java
package example.suite;

import java.time.Instant;

public record Receipt(
        String ref,
        Instant createdAt) {}
```

An immutable Java 17 record simplifies assertions with `assertEquals` and prevents shared mutable DTO state.

### 18.2. AttemptCounter.java

**src/main/java/example/suite/AttemptCounter.java**

```java
package example.suite;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

@Component
public class AttemptCounter {

    private final AtomicInteger attempts =
            new AtomicInteger();

    public void mark() {
        attempts.incrementAndGet();
    }

    public int value() {
        return attempts.get();
    }

    public void reset() {
        attempts.set(0);
    }
}
```

`AttemptCounter` is a Spring-managed singleton intentionally holding mutable state to simulate metrics or in-memory state. It is thread-safe at the increment level, yet **resets and increments across independent tests can still race** if run concurrently without a resource lock. The lab's test classes guard access with `@ResourceLock` and keep sequential execution by default.

**Key insight:** data inside `AtomicInteger` is outside the JDBC transaction; when the service rolls back, its value **does not decrement automatically**. Tests must reset it at fixture boundaries when expecting 0.

## 19. OrderStore.java — JDBC repository

**src/main/java/example/suite/OrderStore.java**

```java
package example.suite;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderStore {

    private final JdbcTemplate jdbc;

    public OrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(String ref) {
        jdbc.update(
                "insert into orders(ref) values (?)",
                ref);
    }

    public int count() {
        Integer count = jdbc.queryForObject(
                "select count(*) from orders",
                Integer.class);
        return count == null ? 0 : count;
    }

    public int countByRef(String ref) {
        Integer count = jdbc.queryForObject(
                "select count(*) from orders where ref = ?",
                Integer.class,
                ref);
        return count == null ? 0 : count;
    }

    public void deleteAll() {
        jdbc.update("delete from orders");
    }
}
```

Using `JdbcTemplate` rather than a mocked repository lets us verify **real H2 transaction rollback and commit**. Avoiding `@DataJpaTest` ensures default test-managed rollbacks do not obscure the service's own commit boundary.

### 19.1. Shared in-memory H2 is still shared state across the context

When two `@SpringBootTest` classes reuse the same DataSource, they read and write the same embedded H2 instance. Even though JUnit instantiates new test class objects, rows persist in the DB unless cleaned up. Changing test or class order can trigger unexpected failures.

### 19.2. When is full-table cleanup safe?

`deleteAll()` clears the **entire** table inside this self-contained lab. In large applications or CI using a shared external DB, never wipe entire tables belonging to other services or tests. Use per-worker schemas/containers, clear namespaces, or seeded IDs with targeted cleanup.

## 20. OrderService.java — real transactions, non-rolling-back counter

**src/main/java/example/suite/OrderService.java**

```java
package example.suite;

import java.time.Clock;
import java.util.Objects;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderStore store;
    private final AttemptCounter counter;
    private final Clock clock;

    public OrderService(
            OrderStore store,
            AttemptCounter counter,
            Clock clock) {
        this.store = store;
        this.counter = counter;
        this.clock = clock;
    }

    @Transactional
    public Receipt place(String ref) {
        return insertOnce(ref);
    }

    @Transactional
    public void placeAndFail(String ref) {
        insertOnce(ref);
        throw new IllegalStateException(
                "planned rollback");
    }

    private Receipt insertOnce(String ref) {
        if (ref == null || ref.isBlank()) {
            throw new IllegalArgumentException(
                    "ref must not be blank");
        }

        Objects.requireNonNull(clock);

        counter.mark();
        store.insert(ref);

        return new Receipt(
                ref,
                clock.instant());
    }
}
```

### 20.1. `@Transactional` on public methods

Tests inject the `OrderService` bean and call public `place`/`placeAndFail` through Spring's AOP proxy. Spring's JDBC transaction manager opens a transaction, commits when the method returns normally, and rolls back when an unchecked exception propagates.

Private `insertOnce` is simply a helper **invoked inside the already-opened transaction**; never assume `@Transactional` on private methods or self-invocations activates by itself.

### 20.2. Rolling back the DB without rolling back AtomicInteger

Inside `placeAndFail`:

1. The service starts a JDBC transaction.
2. `counter.mark()` increments the singleton counter immediately.
3. `store.insert` sends an INSERT inside the transaction.
4. `IllegalStateException` is thrown out of the method.
5. The transaction interceptor rolls back the JDBC row.
6. The counter remains at 1 because it lives in memory, outside the transaction.

Takeaway: if a test asserts only DB rollback without resetting singleton state before the next test, another test in the suite becomes polluted. The same applies to files, Redis, logs, HTTP calls, and background messages.

## 21. FixedClockTestConfig.java — a shared test bean

**src/test/java/example/suite/FixedClockTestConfig.java**

```java
package example.suite;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
public class FixedClockTestConfig {

    public static final Instant FIXED =
            Instant.parse("2026-11-08T03:00:00Z");

    @Bean
    @Primary
    Clock fixedClock() {
        return Clock.fixed(
                FIXED,
                ZoneOffset.UTC);
    }
}
```

Production config provides `Clock.systemUTC()`; test config adds a `@Primary` `Clock.fixed` bean. Both Spring integration test classes annotate `@Import(FixedClockTestConfig.class)` with matching `@SpringBootTest` settings so their **cache keys match** and the same context can be reused. Still, assertions never rely on context identity or class order.

### 21.1. Why not define a separate `@TestConfiguration` inside each test class?

If each class defines its own distinct nested `@TestConfiguration`, context customizers/configuration classes differ, prompting Spring to build separate contexts. That would mask shared-bean-state behavior. A shared test config class makes the mechanism visible.

### 21.2. Why not try to override `System.currentTimeMillis`?

You cannot cleanly override the JVM-wide system clock from Java tests, and global clock hacks create side effects. Injecting `Clock` and supplying a fixed `Clock` keeps tests deterministic without touching other tests.

## 22. OrderSuiteIsolationTest.java — four Spring integration tests

**src/test/java/example/suite/OrderSuiteIsolationTest.java**

```java
package example.suite;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
        classes = SuiteLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@Import(FixedClockTestConfig.class)
@ResourceLock(
        value = "suite-lab-database",
        mode = ResourceAccessMode.READ_WRITE)
class OrderSuiteIsolationTest {

    @Autowired
    OrderService service;

    @Autowired
    OrderStore store;

    @Autowired
    AttemptCounter counter;

    @BeforeEach
    void cleanBefore() {
        store.deleteAll();
        counter.reset();
    }

    @AfterEach
    void cleanAfter() {
        store.deleteAll();
        counter.reset();
    }

    @Test
    void startsWithEmptyDatabaseAndCounter() {
        assertEquals(0, store.count());
        assertEquals(0, counter.value());
    }

    @Test
    void orderCreationCommitsAndUsesFixedClock() {
        Receipt receipt =
                service.place("ORDER-A");

        assertNotNull(receipt);
        assertEquals("ORDER-A", receipt.ref());

        assertEquals(
                FixedClockTestConfig.FIXED,
                receipt.createdAt());

        assertEquals(1, store.count());
        assertEquals(
                1,
                store.countByRef("ORDER-A"));
        assertEquals(1, counter.value());
    }

    @Test
    void rollbackRemovesRowButMemoryStateRequiresReset() {
        IllegalStateException ex =
                assertThrows(
                        IllegalStateException.class,
                        () -> service.placeAndFail(
                                "ORDER-ROLLBACK"));

        assertEquals(
                "planned rollback",
                ex.getMessage());

        assertEquals(
                0,
                store.countByRef("ORDER-ROLLBACK"));

        // JDBC rollback cannot undo a singleton counter.
        assertEquals(1, counter.value());
    }

    @Test
    void multipleCallsAreLocalToThisTestFixture() {
        service.place("ORDER-X");
        service.place("ORDER-Y");

        assertEquals(2, store.count());
        assertEquals(1, store.countByRef("ORDER-X"));
        assertEquals(1, store.countByRef("ORDER-Y"));
        assertEquals(2, counter.value());
    }
}
```

### 22.1. Why clean in both `@BeforeEach` and `@AfterEach`?

- `@BeforeEach` guarantees a test **does not depend on prior tests** and starts from a clean baseline.
- `@AfterEach` proactively leaves shared fixtures clean for the next test or class.
- If a test fails mid-method, JUnit Jupiter still runs `@AfterEach` under normal lifecycles; if the process crashes or is killed, cleanup is skipped, so external CI resources still need namespaces/TTLs/teardown.
- Without `@Transactional` on the JUnit method, `deleteAll()` outside the service transaction commits via datasource auto-commit. This differs from cleanup inside a rolled-back test-managed transaction.

### 22.2. Why is double cleanup not always the right fit?

In real DBs with foreign keys, large tables, or parallel tests sharing one DB, full-table deletes cause contention and slowdowns. Prefer **per-test schemas/databases/transaction isolation/targeted cleanup**. The lab uses dedicated embedded H2 tables, keeping the model easy to follow.

### 22.3. Why does the rollback test assert `counter=1`?

It is an **intentional** assertion demonstrating that memory side effects do not roll back. The fixture resets the counter before the next test, keeping the class self-contained. If any subsequent test expected `counter=0` without proper setup, full-suite runs would fail.

## 23. AnotherOrderSuiteTest.java — two tests in another class

**src/test/java/example/suite/AnotherOrderSuiteTest.java**

```java
package example.suite;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(
        classes = SuiteLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@Import(FixedClockTestConfig.class)
@ResourceLock(
        value = "suite-lab-database",
        mode = ResourceAccessMode.READ_WRITE)
class AnotherOrderSuiteTest {

    @Autowired
    OrderService service;

    @Autowired
    OrderStore store;

    @Autowired
    AttemptCounter counter;

    @BeforeEach
    void cleanBefore() {
        store.deleteAll();
        counter.reset();
    }

    @AfterEach
    void cleanAfter() {
        store.deleteAll();
        counter.reset();
    }

    @Test
    void anotherClassStillStartsWithCleanState() {
        assertEquals(0, store.count());
        assertEquals(0, counter.value());

        service.place("OTHER-A");

        assertEquals(1, store.count());
        assertEquals(1, counter.value());
    }

    @Test
    void duplicateKeyFailureDoesNotCorruptNextTest() {
        service.place("DUPLICATE");

        assertThrows(
                DataIntegrityViolationException.class,
                () -> service.place("DUPLICATE"));

        assertEquals(
                1,
                store.countByRef("DUPLICATE"));

        // The second attempt incremented before DB rejected it.
        assertEquals(2, counter.value());
    }
}
```

### 23.1. Both classes can reuse the context

Both classes share `@SpringBootTest(classes=...)`, `@Import(FixedClockTestConfig.class)`, and bootstrap settings. Inside the same JVM, unless evicted or dirtied, Spring TestContext can reuse the context; each class still resets the table and counter around each test.

The tests **never assume Class A runs before Class B**. If Gradle executes B before A, both still pass by design.

### 23.2. What does the duplicate-key test teach?

The first `service.place("DUPLICATE")` commits. The second violates the primary key; Spring JDBC exception translation maps H2's constraint error to `DataIntegrityViolationException` or a subclass (such as `DuplicateKeyException`). The second attempt rolls back while the first stays committed; the test verifies 1 row in DB and 2 attempts on the counter. If an assertion fails under another DB provider's exception translation, verify that vendor's specific exception rather than swallowing exceptions to pass.

### 23.3. Why avoid `@DirtiesContext` on this class?

It only needs **the DB table and counter bean** reset, without altering Spring bean definitions or configuration. Dirtying the context re-initializes the datasource and every bean unnecessarily, hurting performance without fixing the underlying design.

## 24. PureIsolationTest.java — three unit tests without Spring

**src/test/java/example/suite/PureIsolationTest.java**

```java
package example.suite;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Random;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PureIsolationTest {

    @Test
    void fixedClockMakesLocalDateIndependentOfCiZone() {
        Instant moment =
                Instant.parse("2026-12-31T23:30:00Z");

        Clock utc = Clock.fixed(
                moment, ZoneId.of("UTC"));

        Clock hcm = Clock.fixed(
                moment, ZoneId.of(
                        "Asia/Ho_Chi_Minh"));

        assertEquals(
                LocalDate.of(2026, 12, 31),
                LocalDate.now(utc));

        assertEquals(
                LocalDate.of(2027, 1, 1),
                LocalDate.now(hcm));
    }

    @Test
    void equalSeedsYieldEqualIndependentDraws() {
        Random left = new Random(314159L);
        Random right = new Random(314159L);

        for (int i = 0; i < 100; i++) {
            assertEquals(
                    left.nextInt(1_000_000),
                    right.nextInt(1_000_000));
        }
    }

    @Test
    void concurrentCounterUsesAtomicOperation()
            throws Exception {
        AtomicInteger total =
                new AtomicInteger();

        int workers = 4;
        int loops = 500;

        ExecutorService pool =
                Executors.newFixedThreadPool(workers);
        CountDownLatch start =
                new CountDownLatch(1);

        List<Future<?>> futures =
                new ArrayList<>();

        try {
            for (int worker = 0;
                    worker < workers;
                    worker++) {
                futures.add(pool.submit(() -> {
                    start.await();
                    for (int i = 0; i < loops; i++) {
                        total.incrementAndGet();
                    }
                    return null;
                }));
            }

            start.countDown();

            for (Future<?> future : futures) {
                future.get(30, TimeUnit.SECONDS);
            }

            assertEquals(
                    workers * loops,
                    total.get());
        }
        finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

### 24.1. Three independent tests with clear oracles

- `fixedClockMakesLocalDateIndependentOfCiZone`: same Instant, two explicit ZoneIds yield the two expected dates without relying on host timezone.
- `equalSeedsYieldEqualIndependentDraws`: two PRNG instances with matching seeds and draw sequences yield identical numbers without sharing state across test threads.
- `concurrentCounterUsesAtomicOperation`: four worker tasks increment `AtomicInteger` concurrently; the test uses `Future.get(30s)` for bounded completion rather than `Thread.sleep`. It verifies a safe code path rather than **trying to force an unguarded race**.

### 24.2. 30 seconds is not an SLA

The 30s timeout protects CI from hanging; it does not assert “4 workers must always finish in 30ms”. If CI contention is ever severe enough that 2,000 atomic increments exceed 30s, investigate host contention or thread-pool starvation rather than extending timeouts forever.

### 24.3. Why avoid a shared static `Random`?

If multiple tests/threads consume one shared `Random`, which test gets draw #N depends on scheduling. Here each `Random` is instantiated **inside the test method** and never leaks.

## 25. Running the lab

Requires JDK 17, a Gradle Wrapper compatible with Spring Boot 3.3 (e.g., Gradle 8.7), and Maven Central/dependency cache. No Docker or external DB needed.

### 25.1. Run the unfiltered suite

```bash
./gradlew clean test
```

Or on Windows PowerShell:

```powershell
.\gradlew.bat clean test
```

### 25.2. Run each class individually

```bash
./gradlew test --tests example.suite.OrderSuiteIsolationTest
./gradlew test --tests example.suite.AnotherOrderSuiteTest
./gradlew test --tests example.suite.PureIsolationTest
```

### 25.3. Run a single failing method

```bash
./gradlew test --tests \
  'example.suite.OrderSuiteIsolationTest.rollbackRemovesRowButMemoryStateRequiresReset'
```

On Windows PowerShell, avoid Bash backslash line continuations; pass a single line or use PowerShell's backtick if needed. Selecting a single method alters test context/resource lifecycles compared to the full suite, so record both commands when reporting failures.

### 25.4. Force fresh execution for diagnosis

```bash
./gradlew test --rerun-tasks --no-build-cache --info
```

Never use `--dry-run` to prove tests executed; it only builds the task plan.

### 25.5. Reading JUnit XML/HTML reports

Gradle normally generates:

```text
build/test-results/test/TEST-*.xml
build/reports/tests/test/index.html
```

**Expected 9 JUnit methods** across three classes:

| Class | `@Test` methods | Uses Spring context? |
| --- | ---: | --- |
| `OrderSuiteIsolationTest` | 4 | Yes |
| `AnotherOrderSuiteTest` | 2 | Yes |
| `PureIsolationTest` | 3 | No |
| **Total** | **9** | Per class |

Never report tests as PASSED without checking the real reports. If a CI job filters down to two classes, its executed count will legitimately be smaller than 9; document filters so they are not mistaken for “JUnit skipped tests”.

### 25.6. Trying parallel execution in a sandbox

To test JUnit concurrency, you can add `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
```

Because the runnable `build.gradle` passes `junit.jupiter.execution.parallel.enabled=false` as a default system property, you **must** override it when running:

```bash
./gradlew test -PjunitParallel=true --rerun-tasks
```

JUnit configuration parameters follow precedence rules; JVM system properties on the test task override the properties file. Before enabling parallelism, verify resource locks and lifecycles. Both Spring classes share `@ResourceLock`, preventing concurrent table clears within **one Jupiter execution**; the unit tests touch no DB and are parallel-safe by design.

**Do not conclude full multi-fork CI safety** solely from this lab: resource locks do not cross JVM boundaries.

## 26. Testing anti-patterns separately without mixing into the runnable suite

### 26.1. Static state leak

```java
class BadSuiteStateTest {
    static int count;

    @Test
    void testA() {
        count++;
    }

    @Test
    void testB() {
        assertEquals(0, count);
    }
}
```

If `testA` runs before `testB` in the same JVM, `testB` fails. Because Java/JUnit do not guarantee A/B ordering without order configuration, a full suite can fail unpredictably. **This is an intentionally flawed demo; do not copy it into the main lab's `src/test/java`.**

Fix via per-test local state, `@BeforeEach` resets on the resource-owning class, or encapsulating the full scenario in one self-contained test.

### 26.2. Mutable singleton state leak

```java
@SpringBootTest
class BadSpringStateTest {

    @Autowired AttemptCounter counter;

    @Test
    void assumesFreshApplicationContext() {
        assertEquals(0, counter.value());
    }
}
```

If another test using the same cached context incremented the counter without resetting, the assertion can fail in the full suite while passing alone. Fix fixture ownership instead of sprinkling `@DirtiesContext`.

### 26.3. DB pollution

```java
@Test
void testA() {
    jdbc.update(
            "insert into orders(ref) values (?)",
            "DUP");
}

@Test
void testB() {
    jdbc.update(
            "insert into orders(ref) values (?)",
            "DUP");
}
```

Without test-managed transactions or cleanup, the second test hits a duplicate key error. Fix: unique per-test refs or cleanup at the right boundary. On shared external DBs, isolate namespaces/schemas/containers instead of wiping each other's tables.

### 26.4. `@Transactional` false assurance

```java
@Transactional
@Test
void sendsHttpRequest() {
    httpClient.post("/orders", request);
}
```

The test thread's transaction does not cover the HTTP server thread. The server can commit real rows visible to subsequent tests. Add API-level cleanup or DB isolation rather than trusting test-thread rollback.

### 26.5. Missing async awaits

```java
@Test
void badAsyncTest() {
    eventPublisher.publishEvent(new Event());
    assertEquals(1, asyncObserver.count());
}
```

If the listener executes asynchronously, the count may still be 0 when asserted. Use `CountDownLatch`/Awaitility/CompletionStage designed around finite timeouts instead of `Thread.sleep(2000)`.

### 26.6. Shared port

```java
@BeforeEach
void startServer() {
    server = new TestServer(8080);
    server.start();
}
```

Two classes binding port 8080 concurrently on CI collide. Use port 0/random ports and query the bound port, or run a single suite-owned shared server with guaranteed teardown and health checks.

## 27. Separating leaks from races via controlled experiments

| Experiment | If it fails | If it passes | Limitations |
| --- | --- | --- | --- |
| Run single method | Standalone/pure/environment error | Likely needs pollution/order/load | Does not prove test is sound |
| Run pair A then B | B likely affected by A | May still lack prerequisite state | Pair order matters |
| Run full suite sequentially | State leak or resource exhaustion | Concurrency races may hide | Does not rule out CI env diffs |
| Run full suite in parallel | Race, collision, or load issue | Rare races can still exist | Not proof of thread safety |
| Run single JVM fork | Max context/static reuse | Changes resource pressure | Differs from multi-fork CI |
| Run multiple forks | Cross-process external collision/leak | Static leaks are masked | Cache/process isolation differs |
| Run CI container locally | Closer OS/JDK/config to CI | Network/secret differences remain | Not identical to real CI |
| Apply fixed Clock + seed | Reduces time/random noise | DB/scheduling issues may remain | Seeds do not synchronize threads |
| Reset DB/bean state | If resetting fixes it → state pollution | May mask deeper lifecycle issues | Check proper cleanup scope |

Make **one change at a time**, recording commands and test counts. Changing Spring profiles, JDK, parallel settings, and test order all at once and getting a green run will not pinpoint the root cause.

## 28. Investigating failures that appear only after many tests

When a suite fails near the end after hundreds of methods, check **resource exhaustion** alongside state leaks:

- Unreturned Hikari pool connections and leak-detection warnings.
- Unclosed HTTP clients and response bodies.
- `ExecutorService` threads never shut down.
- Scheduled tasks still firing after tests finish.
- Unclosed files, `InputStream`s, and socket handles.
- Testcontainers containers/services started too frequently or never cleaned up.
- Excessive Spring contexts due to differing profiles/`@MockBean` customizers or `@DirtiesContext`.
- JVM heap/off-heap pressure, GC pauses, native memory, and file descriptors.
- Unbounded global caches, maps, and listeners growing across tests.
- Broker consumer groups, Redis keys, and sessions accumulating across tests.
- Dynamic ports or ephemeral connections exhausted on the CI host.

### 28.1. Do not diagnose “memory leak” solely from `OutOfMemoryError`

CI might have smaller heap limits or heavy test fixtures. Inspect heap/GC diagnostics, process limits, and context/resource counts. Tuning pool/cache sizes can help, provided integration test fidelity stays intact.

### 28.2. Logs should include correlation context

Log test class/method, thread name, worker process ID, container ID/port, datasource URL/schema, and **test-only** contextual request IDs so resource owners can be traced. Never log customer PII, secrets, or credentials.

### 28.3. Hikari pool leaks

With HikariCP, monitor active/idle/pending connection metrics and optionally enable leak detection thresholds in the test profile. Watch out for false positives caused by CI CPU pauses or GC stalls. A connection “unreturned for N seconds” is a clue, not automatic proof of a permanent leak.

## 29. CI-specific mismatches

### 29.1. JDK/Gradle/dependency versions

Use the Gradle Wrapper and Java toolchains, pinning Spring Boot BOM/dependency locks where appropriate. If CI runs the Gradle daemon and toolchain on different JDKs, check the **actual test worker JDK**. Never rely on IDE Project SDK settings to describe CI.

### 29.2. Timezone and locale

One UTC instant can fall on the next calendar day in `Asia/Ho_Chi_Minh`; `LocalDate.now()` diverges accordingly. Inject `Clock`/`ZoneId`. Never assert hardcoded “today” dates against a moving system clock.

### 29.3. OS and file paths

Linux paths are case-sensitive; Windows usually is not. macOS behavior varies with filesystem formatting. Use `ClassLoader.getResource(...)` with exact casing instead of trusting the working directory.

### 29.4. Environment variables and profiles

A CI profile might activate schedulers, auto-migrations, external clients, or security filters absent on laptops. Log **`activeProfiles`** and property names/sanitized values without printing raw secrets.

### 29.5. Container startup and readiness

Cold CI startups fail more often than warm local Docker daemons; use readiness/health checks, module-appropriate Testcontainers wait strategies, and check image pulls/networking rather than increasing fixed sleeps.

### 29.6. Clock speed and CPU quotas

CI shares CPUs and hits cold JIT/classloading, causing tight timeouts to trip. A method taking 200ms locally and 2s on CI does not mean business logic is wrong if the test asserts overly tight wall-clock timing. When latency is a genuine requirement, test in a dedicated benchmark/SLO environment rather than a sleep-based unit test.

### 29.7. CI sharding

Shards may run different subsets or collide on shared external namespaces. Use per-shard schemas, topics, and Redis prefixes; when aggregating test reports, avoid double-counting reruns.

## 30. Failure table → diagnostic steps

| Symptom | Primary hypothesis | Evidence / fix |
| --- | --- | --- |
| Expected zero, actual one | Earlier test left DB/bean state | `@BeforeEach`, DB query, trace owner in logs |
| Duplicate key only in suite | Fixed fixture ID reused | Per-test IDs, cleanup, isolated schema |
| Mockito verify sees unexpected calls | Mock state reused/reset wrongly | `@MockBean` lifecycle, local stubs |
| `ApplicationContext` no longer active | `@DirtiesContext`/eviction in parallel | Cache DEBUG logs, serialize or avoid dirtying |
| Tests pass with `@DirtiesContext` | Hidden mutable state | Reset state properly, measure context cost |
| `Connection refused` after Class A | Container stopped while context cached | Align container and context lifecycles |
| `Address already in use` | Fixed port collisions | Random ports, clear resource ownership |
| Timed out only on CI | Sleep oracle, host load, or readiness | Await conditions with finite timeouts |
| Clock-related date mismatch | Default timezone or midnight boundary | Fixed `Clock` and `ZoneId` |
| Random failure differs every run | Unlogged seed or shared state | Per-test seeds and deterministic replay |
| `@Transactional` test data leaks | Separate thread, HTTP, or external side effect | Check boundaries, add explicit cleanup |
| Resource path missing only on Linux | Case-sensitive file path | Exact resource casing, UTF-8 |
| Passes alone, fails in suite on same JVM | Shared static or singleton bean | Isolation and fixture reset |
| Fails only with `maxParallelForks>1` | Cross-JVM external resource collision | Per-worker namespaces, worker logs |
| Fails only under JUnit parallel | Shared-memory data race | `@ResourceLock`, atomics, immutable data |
| Fails after 300 methods | Resource exhaustion | Pools, threads, file descriptors, cache size |
| Different JDK on CI | Runtime semantics, tzdb, dependencies | `java -version`, Gradle toolchain |
| `BUILD SUCCESSFUL` yet zero tests | Filter, skipped task, no discovery | XML test counts and Gradle task outcome |
| `Failed to load ApplicationContext` | Config or dependency error | First root cause exception, not just test order |
| Error only on fresh CI | Service unready or missing schema | Health checks and migrations |
| Flaky `@Async` event test | Asserting before completion | `CountDownLatch`/`CompletableFuture`/Awaitility |
| Race vanishes sequentially | Concurrency confirmed as a factor | Fix thread safety; don't stop at sequential workaround |

## 31. Failure artifact so others can reproduce

```yaml
# Illustrative template, not output from a real run.
repositoryRevision: "exact-commit-sha"
testTask: ":test"
failingTest: "example.suite.OrderSuiteIsolationTest.method"
failingCommand: "./gradlew test --rerun-tasks --no-build-cache"
minimalReproducer: "list the smallest test set and order"
jdk: "record java -version and test JVM toolchain"
gradle: "record wrapper version"
springBoot: "3.3.0"
junit: "resolved platform/Jupiter versions"
os: "record CI image digest and architecture"
timezone: "UTC"
locale: "explicit value"
profiles: "list active profiles; no secret values"
execution:
  maxParallelForks: 1
  forkEvery: 0
  junitParallel: false
  ciShard: "name or index"
externalResources:
  database: "sanitized url/schema/container image"
  broker: "sanitized topic and consumer group"
  serviceHealth: "health check summary"
random:
  seed: "record if used"
  scenarioIndex: "record if randomized"
failure:
  exceptionClass: "fully-qualified exception"
  expected: "expected outcome"
  actual: "observed outcome"
artifacts:
  - "JUnit XML"
  - "Gradle HTML report"
  - "sanitized test logs"
  - "thread dump or heap data if needed"
```

**Never print secrets, access tokens, customer PII, private URLs with credentials, or full payment payloads.** To verify external services, log sanitized resource identifiers and safe correlation IDs.

## 32. From failure artifact to regression test

1. Reproduce on the old commit with the exact test set.
2. Identify the state owner: static field, singleton, DB, cache, file, external service, or scheduler.
3. Prove the trigger: an earlier test polluting state or a thread finishing late.
4. Fix the fixture or business implementation; never relax expectations for a fake green.
5. Add a **regression test** reproducing the behavior: e.g., verifying DB rows do not leak to the next test or an async listener completes before asserting.
6. Run the isolated reproducer in both orders (A→B and B→A) when relevant.
7. Run the full suite sequentially and in parallel when parallelism is supported.
8. Run inside the target CI environment.
9. Record actual test counts, wall time, and remaining risks.
10. When helpful, keep the failing seed/fixture snapshot in the regression corpus.

### 32.1. When are reruns helpful?

Rerunning helps estimate failure frequency and gather logs, yet **is not a fix by itself**. If a bug hits 1 in 100 runs, 100 passing runs after a fix still do not prove failure probability is zero—they increase confidence under the measured conditions.

### 32.2. When must tests remain sequential?

Some integration tests mutate shared external state or rely on engines/drivers that do not tolerate concurrency. Serializing intentionally via task settings or resource locks is valid when the runtime cost is acceptable. That is distinct from leaving a real concurrency race unfixed in production services where concurrent requests are expected.

### 32.3. When are separate contract/integration tests required?

When bugs involve Kafka ordering, database serializability, Redis TTLs, or HTTP timeouts, pure unit tests are insufficient. Split out provider integration tests using Testcontainers/embedded servers and a production-like environment with explicit fixture ownership to reproduce the real failure mode.

## 33. Practice exercises

### Exercise 1 — Check the baseline

Copy the runnable project, generate a Gradle Wrapper, and run `./gradlew clean test`. Read the reports and record actual executed/passed/failed/skipped counts. Do not cite the expected count of 9 as observed output without running it.

### Exercise 2 — Observe Spring context reuse

Add `logging.level.org.springframework.test.context.cache=DEBUG` in a test profile and run both Spring test classes. Inspect cache hit/miss/size metrics. Never equate `hitCount` with the number of test methods.

### Exercise 3 — Remove `@BeforeEach` reset

In a sandbox, temporarily remove `counter.reset()` in one of the two Spring test classes. Run the class alone and then the full suite, observing how singleton state creates order dependency. Restore the reset afterward.

### Exercise 4 — Remove DB cleanup

Temporarily remove `store.deleteAll()` in `@AfterEach`, run tests reusing the same `ref`, and observe the cleanup/duplicate-key failure. Keep this strictly in the isolated H2 lab—never against a shared staging DB.

### Exercise 5 — `@DirtiesContext` as a workaround

Temporarily annotate one class with `@DirtiesContext`. Compare startup time and cache misses, noting how a fresh context hides the bean counter leak; then remove `@DirtiesContext` and fix it properly with fixture reset.

### Exercise 6 — Add a third test class with matching config

Create a third class sharing the same `@SpringBootTest`/`@Import` config with full cleanup. Run all three classes in varying orders without depending on earlier classes.

### Exercise 7 — Rollback side effect

Call `service.placeAndFail`, asserting 0 DB rows yet counter equal to 1. Explain why rolling back a database transaction does not reset in-memory state.

### Exercise 8 — `@Transactional` test

Add `@Transactional` to a JUnit test in a sandbox and observe rollback alongside `@AfterEach` semantics. Remove it when you want to verify real service commits as in the lab.

### Exercise 9 — JUnit parallel

Add `junit-platform.properties` enabling parallelism and run `-PjunitParallel=true`. Keep `@ResourceLock` on DB tests and audit any other shared resources.

### Exercise 10 — Remove `@ResourceLock`

In a sandbox, remove the locks and run JUnit in parallel repeatedly. If no race surfaces, do **not** claim the suite is safe—either prove resource isolation or add deterministic overlap checks.

### Exercise 11 — Gradle forks

Raise `maxParallelForks` to 2 in a sandbox and observe per-worker context caches and external resource isolation. Never treat JUnit `@ResourceLock` as a cross-process lock.

### Exercise 12 — Fixed timezone

Set the Gradle test JVM timezone to `Asia/Ho_Chi_Minh` and verify `PureIsolationTest` still passes thanks to explicit clocks. Compare with the `LocalDate.now()` anti-pattern.

### Exercise 13 — Case-sensitive resources

Add a test resource `fixtures/sample.json` and request `Fixtures/Sample.json` to observe failures on case-sensitive filesystems. Fix the exact path without resorting to platform-specific workarounds.

### Exercise 14 — Async event

Create an async listener test using `CountDownLatch` and assert after awaiting completion. Compare with a short sleep anti-pattern to observe flakiness, then remove the sleep.

### Exercise 15 — Startup readiness

Build an integration test with a container or HTTP test server using a bounded health check. Compare stability on CI against a fixed sleep.

### Exercise 16 — Duplicate key

Run `duplicateKeyFailureDoesNotCorruptNextTest`; if another provider's exception translation differs from H2, assert the real root exception rather than altering expectations blindly.

### Exercise 17 — Random seed

Use a seeded generator for randomized fixtures and log the seed. Replay using the same seed, algorithm, and call order. Never share one static `Random` across parallel JUnit tests.

### Exercise 18 — Test pairs

Create Fixture A mutating a property or global static without restoring it, read by Fixture B. Reproduce A→B, then fix with `try/finally` restoration or injected properties instead of global state.

### Exercise 19 — Resource exhaustion

Create an executor per test in a sandbox without shutting it down and run many tests. Use a thread dump to confirm the leak, then fix via `try/finally` or `@AfterEach`.

### Exercise 20 — CI artifacts

Configure CI to archive Gradle JUnit XML/HTML reports and sanitized logs for failed tests, recording exact command, seed, JDK, worker, and external service health.

### Exercise 21 — Investigating Spring profiles

Run the same test under two profiles (one enabling schedulers, one without), recording active properties and background jobs. Never assume a bug is fixed simply because switching profiles passes.

### Exercise 22 — Testcontainers lifecycle

Observe how a shared cached context retains a connection to a stopped container after Class A tears down. Align lifecycles to the context/JVM or isolate per class.

### Exercise 23 — Rerunning one class

Run `--tests example.suite.OrderSuiteIsolationTest` and then the full suite on the same commit. Compare reports without mistaking filtered runs for full-suite lifecycles.

### Exercise 24 — CI-only bugs

Build a matrix across OS/JDK/timezone/locale/forks changing one variable at a time. Gather evidence instead of guessing “CI failed because it is slower”.

### Exercise 25 — Before/after regression check

After fixing a leak from Test A, run A→B and B→A (if supported by the harness), the full suite, and the CI pipeline. Record run counts; never declare 100% certainty from a single pass.

## 34. Pre-merge QA checklist

- [ ] Exact failing command, commit, JDK, task path, and active profiles captured.
- [ ] JUnit XML/HTML reports, full stack trace, and actual test counts recorded.
- [ ] Failure classified as single-test, pair-test, suite-only, CI-only, or intermittent.
- [ ] Every test provisions its own fixture/data without depending on method order.
- [ ] `@TestMethodOrder` is not used to mask state leakage outside explicit workflow tests.
- [ ] Static fields and singleton beans do not retain unintended mutable state across tests.
- [ ] A shared Spring `ApplicationContext` is never confused with a fresh per-test context.
- [ ] `@DirtiesContext` is used only when the context is genuinely dirty, not for DB cleanup.
- [ ] Test-managed `@Transactional` and rollback boundaries are understood accurately.
- [ ] HTTP/async/external calls are never assumed to roll back with the test thread.
- [ ] Database rows, Redis keys, queues, and files have explicit ownership and cleanup.
- [ ] Shared external DBs never suffer full-table deletes from parallel tests.
- [ ] Mockito mocks/spies are reset and stubbed within the right scope.
- [ ] JUnit parallelism and Gradle forks are controlled independently.
- [ ] `@ResourceLock`/`SAME_THREAD` are used when appropriate within their per-JVM scope.
- [ ] `Thread.sleep` is never used to synchronize async work.
- [ ] Background futures/executors are awaited/closed with finite timeouts.
- [ ] Test clocks, `ZoneId`, and `Locale` are explicit rather than host-midnight dependent.
- [ ] Random seeds, algorithms, and draw orders are logged when replay is needed.
- [ ] Filesystem resource paths use exact casing and explicit charsets.
- [ ] Network tests check readiness/health rather than guessing sleeps.
- [ ] Ports, DB schemas, topics, and Redis prefixes are isolated across CI forks/shards.
- [ ] Testcontainers lifecycles match cached Spring contexts.
- [ ] Hikari connections, threads, file handles, and resources do not leak across many tests.
- [ ] CI secrets and external credentials are never printed to public logs.
- [ ] Gradle `--rerun-tasks`/`--no-build-cache` are used intentionally for fresh runs.
- [ ] Every failure is classified (assertion vs config vs discovery vs infra).
- [ ] A minimal reproducer failed before the fix and passed afterward where feasible.
- [ ] Both the full suite and target CI environment passed verification after the fix.
- [ ] Execution/pass results are never claimed from unexecuted examples.

## 35. Decision guide for picking a fix

```text
Failure occurs only in suite/CI
     |
     +-- State from an earlier test?
     |     -> Per-test fixtures, cleanup, immutable data,
     |        no global mutable state.
     |
     +-- Context reuse?
     |     -> Reset singletons/DB/cache; review @MockBean,
     |        use @DirtiesContext only when truly needed.
     |
     +-- Transaction boundaries?
     |     -> Test real DB commit/rollback; async/HTTP
     |        side effects require independent cleanup.
     |
     +-- Parallel execution?
     |     -> Resource isolation, JUnit @ResourceLock,
     |        atomics/locking, no shared external IDs.
     |
     +-- Time/randomness?
     |     -> Clock.fixed, explicit ZoneId, per-case seeds.
     |
     +-- CI environment mismatch?
     |     -> JDK/OS/locale/TZ/profiles/dependencies,
     |        resource readiness, permissions.
     |
     +-- Fails after many tests?
     |     -> Pool/thread/file/context cache exhaustion.
     |
     +-- Root cause still unclear?
           -> Capture artifacts, minimize subset,
              change one variable, reproduce before fixing.
```

**Conclusion:** Whenever a test fails only in the full suite or on CI, the crucial step is **identifying the state and boundary the test left uncontrolled**. Spring's context cache can reuse singletons; database transactions do not undo external or in-memory side effects; parallel JVMs/threads introduce races and resource collisions; and CI environments differ in timezone, JDK, OS, and timing. A trustworthy test suite prepares its own data, cleans up at the right scope, controls time and randomness, and captures full execution diagnostics. Never reorder tests, add sleeps, disable parallelism globally, or abuse `@DirtiesContext` merely to force a green build without fixing the root cause.

## 36. Official references

- Spring Framework — Context caching in TestContext: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework — `@DirtiesContext`: https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html
- Spring Framework — Transaction management in tests: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
- Spring Framework — Parallel test execution: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html
- Spring Boot 3.3 — Testing Spring Boot applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Testcontainers and service connections: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Gradle — Testing Java/JVM projects, `maxParallelForks`, `forkEvery`, filters: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Test task reference and test logging: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html
- JUnit 5 Jupiter — Writing tests, `@ResourceLock`, parallel execution: https://docs.junit.org/5.10.5/user-guide/index.html
- JUnit Jupiter — `@ResourceLock` API: https://junit.org/junit5/docs/5.10.5/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/ResourceLock.html
- JUnit Jupiter — ExecutionMode/parallel tests: https://junit.org/junit5/docs/5.10.5/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/Execution.html
- Java 17 — Clock fixed/zone semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html
- Java 17 — AtomicInteger concurrency semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- Java 17 — Random seeded sequences: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html
- HikariCP — Connection-pool configuration and leak detection: https://github.com/brettwooldridge/HikariCP
