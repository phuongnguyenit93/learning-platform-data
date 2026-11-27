# Keeping Results Independent of Execution Order and Parallelism

A reliable CI test suite must produce the exact same verdict whether tests run in different orders or execute concurrently within configured resource limits. If a test only passes when run after another test, or fails when two tests run simultaneously, build outcomes depend on hidden environmental state.

These two requirements are related yet distinct:

- **Order independence:** a test's outcome does not depend on which tests ran before it. Each test prepares its own data and leaves no lingering state that alters later tests.
- **Parallel safety:** multiple tests can execute concurrently without contending for shared resources, overwriting each other's data, or corrupting each other's results.

A test suite can be order-independent yet still unsafe in parallel. For example, every test creates its own records, yet all tests write to the same file. Conversely, a suite might run in parallel without race conditions in a particular run yet still depend on execution order because Test A creates data required by Test B. Verify both properties.

In CI/CD, this directly impacts test gate quality. A single green run is insufficient if outcomes shift with execution order, worker count, timing, or runner load. The goal is designing tests with explicit inputs, isolated state, proper synchronization, and sufficient evidence to reproduce failures.

## 1. Why Order and Parallelism Can Break Tests

On developer machines, tests are often run infrequently, in a familiar order, and in a lightly loaded environment. CI can execute multiple classes or methods concurrently, split tests across processes, run across different runners, or repeat runs in randomized order. These differences expose dependencies that prior sequential runs hid.

Common sources of coupling:

| State source | Failure example | Control approach |
|---|---|---|
| Static variables or singletons | Earlier test mutates a static field; later test sees leftover value | Avoid mutable global state, initialize separately, or restore state |
| System properties, locales, timezones | One test calls `Locale.setDefault`, another formats numbers under the new locale | Avoid mutating global settings or guard with shared resource locks |
| Fixed files and directories | Multiple tests write to `target/test-output.json` | Use a dedicated temporary directory per test |
| Shared database | A test truncates tables or reads records created by another test | Isolated data, separate schemas/tenants, or clearly bounded transactions |
| Fixed ports | Two test servers both bind port 8080 | Bind port 0 and read the OS-assigned port |
| Clocks and time-dependent data | Tests cross midnight boundaries or different timezones | Inject `Clock` and use fixed instants |
| Randomness and UUIDs | Non-reproducible failures due to varying inputs per run | Use recordable seeds, log seeds, and isolate random generators |
| Shared caches or directories | One test warms a cache; another relies on stale contents | Use isolated caches or reset per test |
| Message brokers and queues | A test reads a message meant for another test | Separate topics, queues, or correlation IDs |
| Async tasks and threads | A test finishes before callbacks complete | Use latches/futures and wait with timeouts |
| Nondeterministic data ordering | A test assumes a query always returns rows in one order | Add `ORDER BY` when ordering is required |

A telltale sign is a test that passes when run alone yet fails when running the full suite. That usually points to leaked state or resource contention, though the exact root cause must still be verified via logs and reproduction.

## 2. Distinguishing Order Independence from Parallel Safety

Consider two illustrative tests:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CounterTest {
    private static int counter = 0;

    @Test
    void startsAtZero() {
        assertEquals(0, counter);
    }

    @Test
    void incrementsCounter() {
        counter++;
        assertEquals(1, counter);
    }
}
```

The `startsAtZero` test only passes if no other test has modified `counter` yet. When execution order shifts, the outcome can flip. If both methods run concurrently, both can read and write the variable at unpredictable times. This is simultaneously an order dependency and a race condition.

Another example: each test creates its own database records, yet both execute `TRUNCATE orders` inside `@BeforeEach`. One test's records can be wiped right as another test starts. Each test assumes it owns its setup, yet the reset step mutates a shared resource.

Design each test to own its lifecycle:

1. Create data and resources owned solely by that test.
2. Execute the action under verification.
3. Assert outcomes using the records created by that test.
4. Clean up only that test's resources without deleting another test's data.

If a resource truly must be shared, declare synchronization rules explicitly and ensure every test accessing it obeys the exact same rule.

## 3. Writing Tests Independent of Global State

### Avoid Mutable Static State

Never use mutable static fields to share test data across tests. Instead, instantiate fresh objects inside each test or use factories to build isolated fixtures.

Example:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

class CartTest {
    @Test
    void addsItemToEmptyCart() {
        var cart = new Cart();

        cart.add(new Item("book", 1));

        assertEquals(1, cart.items().size());
    }

    @Test
    void newCartStartsEmpty() {
        var cart = new Cart();

        assertTrue(cart.items().isEmpty());
    }
}
```

Each test constructs a fresh `Cart`, so adding items never alters another test's state. For production singleton caches or registries, provide controlled reset mechanisms or substitute isolated implementations in tests.

### Understand JUnit Jupiter Test Lifecycles

By default, JUnit Jupiter creates a new test instance per test method (`PER_METHOD`). This prevents instance fields from being shared across methods. However, it does not isolate static fields, singletons, system properties, files, databases, or external services.

When using `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, multiple methods share a single test instance. If parallel execution is enabled, mutable fields on that instance can be accessed concurrently. Use `PER_CLASS` only when instance state is immutable or properly synchronized.

Do not rely on `@BeforeAll` to build one shared dataset that every test mutates. If tests need baseline data, keep it read-only or clone fresh copies per test.

### Restore System Properties and Global Settings

A test may need to modify a system property or locale to check behavior. When mutating global state, save the previous value and restore it in `finally`:

```java
String previous = System.getProperty("app.mode");
try {
    System.setProperty("app.mode", "test");
    // Run assertions that depend on app.mode.
} finally {
    if (previous == null) {
        System.clearProperty("app.mode");
    } else {
        System.setProperty("app.mode", previous);
    }
}
```

Restoring prevents subsequent tests from inheriting altered state. Still, if another concurrent test reads the property mid-mutation, results can still break. Guard global resources with synchronization locks or redesign to avoid mutating global state altogether.

## 4. Injecting Clock and Controlling Random Data

Time and randomness are two input sources notorious for causing intermittent passes and failures.

### Use `Clock` Instead of System Time

Never call `Instant.now()` or `LocalDate.now()` directly deep inside business logic if outcomes require deterministic testing. Inject `Clock` so tests can supply a fixed instant.

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

final class ExpirationPolicy {
    private final Clock clock;

    ExpirationPolicy(Clock clock) {
        this.clock = clock;
    }

    boolean isExpired(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }
}
```

Test:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

@Test
void expiresAtConfiguredInstant() {
    var now = Instant.parse("2026-11-18T10:00:00Z");
    var clock = Clock.fixed(now, ZoneOffset.UTC);
    var policy = new ExpirationPolicy(clock);

    assertTrue(policy.isExpired(now));
}
```

The test no longer depends on the wall-clock time when the runner executes. Before-expiration, exact-expiration, and post-expiration cases can all be verified with distinct fixed `Clock` instances.

### Use Reproducible Seeds for Randomness

If an algorithm needs randomness, inject the random source rather than scattering `new Random()` calls inside logic. In tests, pass a fixed seed so each run gets the exact same sequence.

```java
import java.util.Random;

final class SampleSelector {
    private final Random random;

    SampleSelector(Random random) {
        this.random = random;
    }

    int chooseIndex(int size) {
        if (size <= 0) {
            throw new IllegalArgumentException("size must be positive");
        }
        return random.nextInt(size);
    }
}
```

```java
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

@Test
void selectsWithinRangeWithKnownSeed() {
    var selector = new SampleSelector(new Random(12345L));

    int index = selector.chooseIndex(5);

    assertTrue(index >= 0 && index < 5);
}
```

Fixed seeds make random inputs reproducible. When the goal is testing many random sequences, iterate over multiple recorded seeds rather than letting tests pick untraceable seeds. For security features, never use `java.util.Random` as a production randomness source; this example only illustrates controlling test inputs.

## 5. Isolating Filesystems, Ports, and External Services

### Use Dedicated Temporary Directories

Never write test files to a shared hardcoded path. JUnit provides `@TempDir` to create a temporary directory per test and clean it up afterward.

```java
import java.nio.file.Files;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ReportWriterTest {
    @Test
    void writesReportIntoTemporaryDirectory(@TempDir Path tempDir) throws Exception {
        Path report = tempDir.resolve("report.txt");

        Files.writeString(report, "build passed");

        assertEquals("build passed", Files.readString(report));
    }
}
```

Each test receives its own directory so it never overwrites another test's files. If a test creates subdirectories or child files, keep them rooted under this temporary directory.

### Do Not Bind Fixed Ports

Two tests starting servers on the same port will collide. Ask the operating system for an ephemeral port by binding port `0`, then read the assigned port from the bound socket or started server.

```java
try (var serverSocket = new java.net.ServerSocket(0)) {
    int assignedPort = serverSocket.getLocalPort();
    assertTrue(assignedPort > 0);
}
```

This snippet illustrates obtaining an available port while the socket remains bound. For test HTTP servers, configure the server itself to bind port `0` and query the port from the running server. Avoid finding a free port, closing the probe socket, and then starting the server on that port; another process can claim the port in the gap between closing and rebinding.

### Databases and Message Brokers

When multiple tests share one database, each test needs its own records. Options include:

- Provision separate schemas or databases per test class, worker, or test run.
- Create a dedicated tenant or namespace per test.
- Use unique primary keys and correlation IDs to query only the test's own records.
- Clean up only records created by that test rather than truncating shared tables.
- Use transaction rollbacks when all test actions genuinely execute within the same transaction.

Transaction rollbacks do not isolate every scenario. If the application opens a separate connection, runs async tasks, calls out-of-process services, or publishes committed messages, the test transaction cannot undo those effects. In those cases, use separate namespaces, explicit cleanup, or disposable environments.

For message brokers, use dedicated queues/topics or message keys carrying correlation IDs. Tests should only consume messages matching their own requests and clean up subscriptions afterward.

## 6. Synchronizing Asynchronous Tests Properly

Never use `Thread.sleep()` to guess when an asynchronous task finishes. Execution duration varies with CPU load, network conditions, and runners; short sleeps cause intermittent failures, while long sleeps slow down the suite.

Wait for a completion signal with a bounded timeout, such as `CompletableFuture`, `CountDownLatch`, or a conditional await utility.

Example using `CountDownLatch`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

@Test
void waitsForBackgroundWork() throws Exception {
    var completed = new java.util.concurrent.CountDownLatch(1);
    var result = new java.util.concurrent.atomic.AtomicReference<String>();

    var executor = java.util.concurrent.Executors.newSingleThreadExecutor();
    try {
        executor.submit(() -> {
            result.set("done");
            completed.countDown();
        });

        assertTrue(completed.await(2, java.util.concurrent.TimeUnit.SECONDS));
        assertEquals("done", result.get());
    } finally {
        executor.shutdownNow();
    }
}
```

Timeouts ensure tests fail with a clear error if work never completes. The `finally` block shuts down the executor even if assertions fail. In production code, manage executor lifecycles through dependencies or application lifecycle hooks rather than creating unmanaged global thread pools.

Synchronization should wait on the condition under verification rather than an arbitrary delay. When polling external system state, use bounded-interval polling with a timeout and log the last observed state upon expiration.

## 7. Do Not Rely on Implicit Data Ordering

Databases do not guarantee row ordering when SQL lacks an `ORDER BY` clause. Unordered collections or maps without defined iteration order must not be asserted as ordered lists either.

For example, if an API must return newest orders first, express that explicitly in the query:

```sql
SELECT id, created_at, total
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC, id DESC;
```

`id` serves as a tie-breaker so ordering remains deterministic when two records share the same `created_at`. When ordering is not a business requirement, tests should compare sets or check membership instead of relying on returned order.

Similarly, never rely on file creation order, directory traversal order, or event arrival order across threads unless the system contract guarantees it. When order matters, sort or synchronize at the responsible layer.

## 8. Detecting Order-Dependent Tests via Randomization

Running tests in a familiar fixed order can hide hidden coupling. One way to expose it is varying class and method execution order across runs.

JUnit Jupiter supports randomized orderers. Configure them in `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.testmethod.order.default=org.junit.jupiter.api.MethodOrderer$Random
junit.jupiter.testclass.order.default=org.junit.jupiter.api.ClassOrderer$Random
junit.jupiter.execution.order.random.seed=20261118
```

With a fixed seed, the randomized order is reproducible across matching runs. When a failure occurs, save the seed alongside failing classes and methods so you can replay the exact order.

A single fixed seed cannot explore every possible order. Use a stable seed in pull request pipelines for comparable results, and add a scheduled job cycling through varying seeds to uncover rare dependencies. Whenever changing seeds, log the seed value in test output or reports.

Never use `@TestMethodOrder` to force tests into a specific sequence just to keep a suite green. If two tests belong to one workflow scenario, combine them into one explicit scenario test or give each test its own isolated fixture. Explicit ordering is only valid when ordering itself is part of the behavior under test, never to mask leaked state.

## 9. Enabling Controlled Parallel Execution with JUnit 5

JUnit Jupiter disables parallel execution by default. Enable it via `junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=2
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
```

With this configuration, JUnit uses the `fixed` strategy with parallelism `2` and permits methods and classes to run concurrently per the declared modes. The value `2` is just an example; tune it to runner CPU, memory, and backing service capacity.

Do not turn on parallel execution across an entire suite before tests have solid isolation. Start with an independent subset, monitor failure rates and resource consumption, then expand gradually.

### Locking Shared Resources with `@ResourceLock`

If certain tests must access a global resource, JUnit provides `@ResourceLock` to serialize tests declaring the same lock key.

```java
import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;

@ResourceLock(value = "default-locale", mode = ResourceAccessMode.READ_WRITE)
class LocaleSensitiveTest {
    @Test
    void formatsUsingConfiguredLocale() {
        Locale previous = Locale.getDefault();
        try {
            Locale.setDefault(Locale.US);
            // Run locale-dependent assertions.
        } finally {
            Locale.setDefault(previous);
        }
    }
}
```

Every other test reading or writing the default locale within the same test plan must declare the same lock to coordinate properly. Any test omitting the lock can still run concurrently and observe mid-mutation state. `@ResourceLock` coordinates tests inside the JUnit engine; it does not lock across separate Gradle worker processes, separate CI jobs, or external applications.

### Using `@Isolated` When an Entire Class Must Run Alone

`@Isolated` marks a test class so it never runs concurrently with other tests in the same execution plan. This fits legacy tests mutating multiple global states that are hard to lock individually.

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Isolated;

@Isolated
class LegacyGlobalConfigurationTest {
    @Test
    void verifiesLegacyConfiguration() {
        // Test requiring exclusive access to global state.
    }
}
```

`@Isolated` reduces concurrency and lengthens suite runtime. Use it strictly as a temporary guardrail for hard-to-isolate tests while scheduling refactoring work to eliminate global state long term.

## 10. Configuring Parallelism in Gradle

JUnit controls parallelism inside the test engine. Gradle can also launch multiple test worker processes. These two layers are independent and multiply total concurrency.

In `build.gradle.kts`:

```kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()

    // Maximum of two JVM test workers per Test task.
    maxParallelForks = 2

    // Keep workers alive throughout the task; do not re-fork after each test.
    forkEvery = 0
}
```

If each worker JVM lets JUnit run 2 tests concurrently, one `Test` task can have roughly 4 tests executing simultaneously. If Gradle runs multiple `Test` tasks in parallel or CI shards the suite across jobs, total concurrency climbs even higher.

Distinguish the mechanisms:

| Mechanism | Scope | Effect |
|---|---|---|
| JUnit parallel execution | Methods/classes inside one test JVM | Multiple tests run concurrently inside one process |
| Gradle `maxParallelForks` | Multiple JVM test workers for one `Test` task | Isolates static state across worker processes, yet external DBs/files/ports can still contend |
| Gradle `org.gradle.parallel` | Eligible projects/tasks within the build | Not synonymous with JUnit method parallelism |
| CI matrix or test sharding | Multiple jobs/runners | Scales concurrency across machines; requires isolated resource namespaces |

`maxParallelForks` defaults to 1. Increasing worker count can shorten test time while increasing memory footprint and service connections. Do not size workers based solely on CPU count; account for databases, containers, file descriptors, and API rate limits as well.

## 11. Determining an Appropriate Parallelism Level

Optimal parallelism reduces feedback latency without significantly increasing flaky tests or overloading shared services.

When tuning, consider:

- Available CPU cores and memory on the runner.
- Utilization of database connection pools, message brokers, and containers.
- Number of tests spawning servers or child processes.
- I/O wait time versus CPU execution time.
- Gradle worker count and JUnit thread count per worker.
- Concurrent CI jobs or shards hitting the same test environment.

Start with a sequential baseline, then incrementally raise JUnit parallelism or Gradle forks while measuring p50/p95 duration, failure rate, peak memory, and service load. If runtime stops dropping while failures climb, concurrency has exceeded what tests or infrastructure can sustain.

Some integration tests may need sequential execution because they share an environment that lacks per-test namespacing. Limit serialization strictly to that resource group; never disable parallelism for the entire suite just because of a few legacy tests.

## 12. Diagnosing Order- or Parallel-Related Failures

When a flaky test surfaces, preserve enough data to reproduce it. Never record just "test fails sometimes." Collect:

- Failing class and method names, test engine, and JUnit version.
- Commit SHA, JDK/Gradle versions, and CI configuration.
- Test execution order or random seed.
- JUnit thread count and Gradle worker count.
- Whether the test passes alone yet fails in the full suite.
- Whether the test passes sequentially yet fails in parallel.
- Relevant worker ID, schema/database/tenant, port, or temporary directory.
- Logs of the first failing test and any tests executing concurrently with it.

### Reproduction Matrix

| Run | Order | Parallelism | Purpose |
|---|---|---|---|
| A | Default order | 1 | Establish sequential baseline |
| B | Randomized, fixed seed | 1 | Detect order dependencies |
| C | Default order | 2 or more | Detect race conditions |
| D | Randomized, fixed seed | 2 or more | Combine both dependency types |
| E | Failing test run alone | 1 | Separate pure logic bugs from interaction bugs |

If only Run B fails, look first for state leaking between tests. If only Run C or D fails, look for resource contention and race conditions. If Run E also fails, it is likely a logic bug independent of order. This narrows investigation rather than serving as an automatic conclusion.

### Re-Running a Specific Test

Gradle supports filtering tests by class or method:

```bash
./gradlew test --tests "com.example.OrderServiceTest.createsOrder" --info
```

Run the full suite with a specific seed by passing the seed via a Gradle property. For example, in `build.gradle.kts`:

```kotlin
val testOrderSeed = providers.gradleProperty("testOrderSeed").orElse("20261118")

tasks.withType<Test>().configureEach {
    systemProperty("junit.jupiter.execution.order.random.seed", testOrderSeed.get())
}
```

Then run:

```bash
./gradlew test -PtestOrderSeed=987654321 --info
```

Archive the seed alongside logs whenever a test fails. Keep the exact seed while reproducing, then explore additional seeds to uncover hidden dependencies.

### Reading Logs Across Test Workers

When Gradle runs multiple workers, log lines can interleave. Enable sufficiently detailed logging or emit per-test reports so worker identity and timestamps stay clear. Avoid logging sensitive data. When tests use dedicated schemas or namespaces, include non-sensitive identifiers in logs to correlate each test with the resources it created.

## 13. Example CI Workflow Running Tests with Controlled Configuration

The GitHub Actions workflow below illustrates a job running tests on a pinned JDK and preserving logs/reports on failure:

```yaml
name: Java tests

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 25
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Run tests
        run: ./gradlew --no-daemon test --info

      - name: Upload test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-reports-${{ github.sha }}
          path: build/reports/tests/test/
          if-no-files-found: ignore
          retention-days: 7
```

This workflow does not turn on JUnit parallel execution directly; that configuration lives in `junit-platform.properties`. Separating this configuration lets the repository state parallelism explicitly and vary it per test group. `if: always()` only preserves reports after test completion; it does not mark the test job successful if the test command fails.

When CI uses a matrix or shards tests across jobs, each job needs isolated namespaces for databases, queues, buckets, and external resources. Include `run ID + shard ID` in schema or namespace names so two jobs never write into the same dataset.

## 14. Practices That Hide Bugs

| Practice | Consequence | Improvement |
|---|---|---|
| Running tests in a fixed order so later tests inherit earlier data | Suite becomes order-dependent and hard to run individually | Have each test build its own fixtures and data |
| Using mutable static fields to share fixtures | Leaked state or race conditions | Build isolated fixtures and immutable objects |
| Using hardcoded ports or file paths | Multiple tests/workers overwrite or collide on binds | Allocate dynamic ports and `@TempDir` |
| Truncating shared database tables in `@BeforeEach` | One test wipes another test's data | Use per-test schemas/tenants or owner-scoped cleanup |
| Using `Thread.sleep()` to wait for async work | Flaky under runner load and slows down the suite | Wait on conditions/futures/latches with timeouts |
| Enabling maximum parallelism immediately | Infrastructure overload and hard-to-diagnose failures | Ramp up gradually and measure per layer |
| Increasing retries to keep the pipeline green | Masks race conditions and unstable tests | Preserve failures, reproduce, and fix root causes |
| Putting `@Isolated` on every test | Eliminates benefits of parallelism | Lock only contested resources or isolate fixtures |
| Re-running only the failing test alone and assuming it is fixed | Ignores interactions with other tests | Re-run the suite using the failing seed and concurrency |
| Using one single random seed forever | Fails to exercise other execution orders | Use a stable seed on PRs and rotate seeds in scheduled jobs |

## 15. Independence Checklist

Before enabling or increasing parallelism in CI, verify:

- [ ] Every test can run standalone without relying on other tests to prepare data.
- [ ] Tests create their own fixtures and assert only data they own.
- [ ] No unintended mutable static state or shared singletons exist.
- [ ] System properties, locales, timezones, and global settings are avoided or safely restored.
- [ ] Tests inject `Clock` or fixed timestamps when deterministic behavior is required.
- [ ] Random seeds are recordable and reproducible; randomness never alters expected outcomes unpredictably.
- [ ] Files use dedicated temporary directories; ports are dynamically allocated.
- [ ] Databases, queues, buckets, and services use isolated namespaces or explicit synchronization.
- [ ] Async tests await completion signals with timeouts rather than arbitrary sleeps.
- [ ] Queries and collections depend on ordering only when ordering is explicitly specified.
- [ ] Suites are exercised under randomized order with reproducible seeds.
- [ ] JUnit parallelism and Gradle `maxParallelForks` are configured deliberately.
- [ ] Combined concurrency across JUnit, Gradle, and CI matrices fits runner and service capacity.
- [ ] Shared resources use `@ResourceLock`, `@Isolated`, or equivalent isolation when needed.
- [ ] CI archives test reports, seeds, worker info, and diagnostics needed for investigation.
- [ ] Flaky tests are fixed at root cause; retries are never used to hide failures.

A well-engineered test suite does not require a secret execution sequence to pass. Every test manages its own state, while genuinely shared resources obey clear synchronization rules and boundaries. When execution order is shuffled and concurrency increases while outcomes remain stable, teams gain higher confidence in test gates and shorter CI feedback cycles.
