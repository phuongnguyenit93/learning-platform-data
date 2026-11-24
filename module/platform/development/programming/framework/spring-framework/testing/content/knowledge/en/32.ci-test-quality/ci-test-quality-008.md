# Investigating Flaky Tests Instead of Retrying to Mask Failures

A flaky test is a test that sometimes passes and sometimes fails even though the code and inputs are supposedly unchanged. For example, the same Spring MVC test may be green when run alone yet red when run with the full suite; a repository test may find a record on some runs and miss it on others; or an async test may fail sporadically in CI while rarely failing on a developer's machine.

Re-running a test can help detect this phenomenon, but simply increasing retry counts until a build turns green leaves the underlying cause intact. A passing retry does not prove a test is stable. It may be masking a race condition, shared data, ordering dependence, an overly tight timeout, or an environment failure.

The goal of investigation is to gather enough evidence to reproduce the failure, identify the source of instability, fix the root cause, and prove the test is stable afterward. Retries should only be a temporary, tracked measure in CI—never a fix for a test.

## 1. Recognizing Flaky Tests

A test is considered flaky when the same test scenario yields inconsistent outcomes without any intentional change to code, data, or environment. Common signs include:

- The test passes when run alone yet fails when run with the full suite.
- The test fails only when parallel execution is enabled.
- The test fails in CI yet passes on a personal machine.
- Assertions on timing, element ordering, or async state fail without an obvious pattern.
- The first run fails and an immediate rerun succeeds.
- One failing test triggers failures in subsequent tests by leaving behind state or corrupting shared resources.

Not every test that turns red once is flaky. If the failure reproduces consistently with the same inputs, it may be a deterministic application bug or an incorrect assertion. If many tests fail together when the database is unreachable, the cause may be CI infrastructure. Classify before concluding.

### Distinguishing failure categories

| Category | Symptom | Example |
| --- | --- | --- |
| Reproducible product bug | Same conditions always yield the same error | Controller always returns 500 for a valid request |
| Unstable assertion or test data | Result depends on ordering, timing, or random data | Test assumes the first element of an unordered collection is fixed |
| Race condition | Multiple threads access shared state and outcome depends on timing | Two tests update the same record or static field concurrently |
| Timing/async | Test asserts before work completes | Assertion executes before a `CompletableFuture` finishes |
| Environment dependence | Result varies by machine, timezone, locale, or resources | Test parses dates using the runner's default timezone |
| External infrastructure failure | Database, broker, container, or HTTP service is unstable | Testcontainers fails to start the Docker daemon |
| State leakage across tests | An earlier test leaves data or mutates configuration | System properties, temporary files, or mock servers were not reset |

Accurate classification guides the next experiment. For example, if a failure occurs only under parallel runs, retrying sequentially can hide a race condition without solving it.

## 2. Capture Evidence Immediately When a Test Fails

Before re-running, record enough information so a failing run can be compared against a passing one. Saving only a `Tests failed` line makes finding the cause very difficult.

Information to capture:

- Full name of the test class and method.
- Commit SHA, JDK, Spring Boot/Spring Framework, JUnit, and build tool versions.
- Operating system, available CPUs, memory, timezone, and locale.
- Which JVM worker and thread ran the test, and whether parallel execution was enabled.
- Test ordering, random seed if any, active profiles, and system properties.
- Full logs before and after the failure timestamp, stack traces, and suppressed exceptions.
- State of the database, containers, mock servers, and dependent services when the error occurred.
- Run count, which attempts failed or passed, and which test ran immediately beforehand.

In Spring integration tests, enable selective detailed logging for Spring TestContext, transactions, or HTTP requests to see which context was reused and what operations the test performed. Avoid turning on debug logging for the entire framework on every job if logs become huge; prefer reproducing in a dedicated investigation job.

A simple capture template:

| Field | Value to record |
| --- | --- |
| Test | `OrderRepositoryTest.findsReadyOrders` |
| Commit/JDK | Commit SHA and JDK version |
| Runner | OS, CPU, RAM, timezone |
| Execution | Parallel on/off, worker, thread, test ordering |
| Dependencies | Database/container and version |
| Result | Pass/fail counts, stack trace, and relevant logs |
| Reproduction | Run command, profiles, seed, and configuration |

## 3. Reproduce in a Controlled Manner

Do not start by running the entire suite hundreds of times. Broaden scope step by step to learn which condition triggers the failure.

### Step 1: run the exact failing test

With Gradle:

```bash
./gradlew test --tests "com.example.orders.OrderRepositoryTest.findsReadyOrders" --no-daemon
```

With Maven Surefire:

```bash
./mvnw -Dtest=OrderRepositoryTest#findsReadyOrders test
```

Running a single test method removes interference from other tests. If the error reproduces consistently, investigate the code, data, or direct dependencies of that test. If it does not reproduce, widen the scope.

### Step 2: run the entire class

Run the full test class to check for dependencies between methods within the class. If the test fails only here, examine:

- Did an earlier test method mutate shared state?
- Do `@BeforeEach` and `@AfterEach` reset data thoroughly?
- Does the test assume a method execution order?
- Does the test class use `@TestInstance(PER_CLASS)` with mutable fields?
- Did one method mark `@DirtiesContext` or close a resource another method still uses?

### Step 3: run with the related group of tests

If the class passes alone yet fails in the full suite, add classes sharing the same database, context, files, system properties, mock server, or container. Expand the group incrementally to pinpoint the interfering test.

### Step 4: compare sequential and parallel runs

Temporarily disable parallel execution in a diagnostic run or put suspect tests on `SAME_THREAD`. If the failure disappears when run sequentially, that is strong evidence of a race condition or resource contention—not proof that the root cause has been fixed.

JUnit Jupiter can override parallel settings for a single run via system property:

```bash
./gradlew test -Djunit.jupiter.execution.parallel.enabled=false
```

If the build tool does not forward this system property to the test JVM under its current config, forward it via the `Test` task's `systemProperty` or use a `junit-platform.properties` file for the diagnostic run. Check logs to confirm tests actually ran sequentially.

### Step 5: repeat intentionally and record outcomes

Repeating a test helps estimate failure frequency or verify whether a fix works. Keep conditions constant and log pass/fail counts. If you change a variable such as parallelism, timezone, or input data, document that variable so outcomes stay comparable.

Do not merely write “rerun passed.” Record “ran 30 times with identical configuration, 0 failures” or “ran 20 times, failed 3 times with parallel enabled, 0 times with parallel disabled.” Those numbers still do not prove absolute non-flakiness, yet they provide far better evidence.

## 4. Find Order Dependencies and Shared State

A test should set up the data it needs and clean up state it creates. A test must not depend on another test having run beforehand.

### Static fields and mutable singleton beans

Error-prone example:

```java
@Component
public class CurrentTenant {

    private String tenantId;

    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }

    public String getTenantId() {
        return tenantId;
    }
}
```

Spring beans are singletons by default. If multiple requests or tests call `setTenantId` concurrently, one test can read another test's tenant. This is a shared-state design defect that cannot be fixed reliably with retries.

If tenant is per-request data, pass it as a parameter, via a request-scoped context, or through an appropriate thread-safe context mechanism. Never store request-specific state in a mutable field on a singleton.

### System properties, locale, and timezone

Values set by `System.setProperty`, `Locale.setDefault`, and `TimeZone.setDefault` are JVM-wide. If a test alters them, save the prior value and restore it in `finally`, while locking access when other tests use the same resource.

JUnit provides `@ResourceLock` to coordinate tests declaring the same resource key:

```java
@ResourceLock(value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
class SystemPropertyTest {

    @Test
    void changesApplicationMode() {
        String previous = System.getProperty("app.mode");
        try {
            System.setProperty("app.mode", "test");
            assertThat(System.getProperty("app.mode")).isEqualTo("test");
        }
        finally {
            if (previous == null) {
                System.clearProperty("app.mode");
            }
            else {
                System.setProperty("app.mode", previous);
            }
        }
    }
}
```

Every test with conflicting access must declare the same resource key. `@ResourceLock` coordinates tests only within the same JUnit execution; it does not lock resources across separate JVMs or builds.

### Colliding database data

Two tests may insert the same unique email or update the same record. Even if each test has transaction rollback, concurrent runs can still trigger unique-constraint violations or read each other's uncommitted/committed data depending on isolation.

Common solutions:

- Create isolated data per test using unique IDs or keys.
- Never rely on data created by another test.
- Clean up scoped data properly and ensure cleanup never deletes another test's data.
- Avoid sharing one account, record, or queue if tests mutate it concurrently.
- If a test requires exclusive access to a resource, serialize it with an appropriate lock or use a separate database/schema.

## 5. Check Timing and Asynchronous Handling

Async flakiness usually happens when assertions run before work finishes or when timeouts are too short for the CI environment.

### Avoid `Thread.sleep` to guess completion time

Unstable example:

```java
service.startAsyncJob();
Thread.sleep(200);
assertThat(repository.findById(42L)).isPresent();
```

The job may finish in 50 ms on a developer machine yet take 500 ms in CI. Raising `sleep` to several seconds just slows down tests while still offering no guarantee the condition completed.

Wait for the required condition with a bounded timeout:

```java
service.startAsyncJob();

await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() ->
                assertThat(repository.findById(42L)).isPresent());
```

This example uses Awaitility. Declare the Awaitility dependency in test scope. `untilAsserted` polls the assertion until it succeeds or times out; this is intentionally awaiting an asynchronous condition, unlike retrying a whole test to mask failures. Timeouts must reflect reasonable system bounds, and failure messages should help identify which condition remained unmet.

### Use latches or futures when the test controls the task

If the code returns a `CompletableFuture`, wait on the future rather than guessing timing:

```java
CompletableFuture<Order> result = service.createOrderAsync(command);

Order order = result.get(5, TimeUnit.SECONDS);

assertThat(order.getStatus()).isEqualTo("CREATED");
```

`get(timeout, unit)` bounds wait time and fails if the future does not complete on time. When using callbacks or listeners, `CountDownLatch` lets the test wait until the callback fires.

### MockMvc async tests must dispatch the final result

For controllers returning `Callable`, `DeferredResult`, or `CompletableFuture`, the first request may only confirm that async processing started. The test must invoke `asyncDispatch(...)` once the result is ready to assert the final response.

```java
MvcResult initial = mockMvc.perform(get("/async-orders/42"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(initial))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42));
```

If the task awaits a callback triggered by the test, trigger the callback before dispatching. Do not call `asyncDispatch` before async processing has started or before the result is complete.

## 6. Control Time, Randomness, and Environmental Data

Tests depending on current time, randomness, default timezone, or default locale easily behave differently across machines and runs.

### Inject `Clock` instead of calling system time directly

Production code:

```java
@Service
public class ExpirationService {

    private final Clock clock;

    public ExpirationService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        return !expiresAt.isAfter(Instant.now(clock));
    }
}
```

Test supplies a fixed clock:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"), ZoneOffset.UTC);

ExpirationService service = new ExpirationService(fixedClock);

assertThat(service.isExpired(Instant.parse("2025-12-31T23:59:59Z")))
        .isTrue();
```

The test no longer depends on real wall-clock dates or times. For code testing elapsed time, use a controllable test clock.

### Specify timezone and locale explicitly

When parsing/formatting dates and times, use `Instant`, `OffsetDateTime`, `ZoneId`, or explicitly configured `DateTimeFormatter` instances. Never rely on the machine's default timezone. If a test genuinely must change the default timezone, guard the change with a resource lock and restore it in `finally`.

### Pin random seeds or control generators

If a test uses randomness to build data, pass a `Random`/generator with a fixed seed so it is reproducible. When testing across many random cases, log the seed on failure so that exact case can be replayed.

### Do not rely on unguaranteed ordering

If a result is a `Set`, a query without `ORDER BY`, or an API that does not promise ordering, never assert on the first element. Compare collections without order sensitivity or request explicit ordering in the query when order is part of the contract.

## 7. Investigate Spring `ApplicationContext` and `@DirtiesContext`

Spring TestContext Framework caches `ApplicationContext` instances to avoid recreating the same context across tests. This improves speed, yet allows mutable state or closed resources to leak between tests.

Check:

- Did a test mutate a singleton bean or configuration after context initialization?
- Did a test close a shared datasource, executor, mock server, or client?
- Did a test use `@DirtiesContext` while another class still depended on that context?
- Was the context built with different profiles/properties locally vs. in CI?
- Does a bean retain caches, counters, or mutable collections that tests fail to reset?

`@DirtiesContext` marks a context for cache eviction and shutdown according to its scope. It is useful when a test genuinely alters the context beyond recovery. Do not slap this annotation on every test to hide leaked state: closing and rebuilding contexts slows down the suite and does not fix race conditions in external resources.

If a test only alters database data, clean up the data properly rather than dirtying the entire application context. If a singleton bean holds mutable state, consider making the bean stateless or providing an explicit reset API for tests.

## 8. Investigate Transactions and Databases in Spring Tests

Spring tests frequently run test methods inside a transaction and roll back afterward. That helps isolate data, yet does not guarantee every operation in the test participates in that transaction.

Situations to watch:

- `@Async` tasks run on another thread and do not automatically join the test's transaction.
- `REQUIRES_NEW` opens a separate transaction and can commit data even when the outer test transaction rolls back.
- A request to an embedded server executes on a server thread different from the test thread; the test's transaction does not wrap the server transaction.
- Two concurrent tests writing data can contend on locks or unique keys.
- Tests sharing the same sequence, fixed IDs, or shared seed data can interfere with one another.

When tests involve async work or a real server, identify which transaction committed and who is responsible for cleanup. Never assume end-of-test rollback deletes data written by independent threads or transactions.

For intermittent database failures, capture SQL logs and operation timestamps, transaction boundaries, isolation levels, lock wait timeouts, and container state. When possible, create test data with unique IDs and avoid insert-order dependencies between tests.

## 9. Inspect Testcontainers and External Services

Testcontainers, WireMock, embedded brokers, and external services bring integration tests closer to real environments, while also introducing new sources of instability.

Questions to verify:

- Did the container start cleanly and finish readiness checks?
- Does the test use a fixed port that collides during parallel runs?
- Is the container stopped while other tests still use it?
- Does the database have enough connections for the current concurrency level?
- Does the mock server reset stubs and request journals after each test?
- Does the test depend on the Internet, DNS, or an uncontrolled external service?
- Are client timeouts adequate for CI load?

Prefer library-allocated dynamic ports, readiness checks over `sleep`, clear container lifecycles, and per-test data. If an external service cannot be controlled, consider replacing it with a fake/mock server for unit or slice tests while keeping dedicated integration tests to verify real integration.

## 10. Using Retries for the Right Purpose

Retries can be useful in two scenarios:

1. **Investigation:** controlled reruns to measure failure rates, check reproduction conditions, or confirm a fix's effectiveness.
2. **Temporary mitigation in CI:** a test depending on unstable infrastructure may be retried briefly, accompanied by alerts, an owner, and a clear remediation deadline.

Retries must never be treated as normal passing results. When the first attempt fails and the second passes, CI must record that test as flaky. Reporting a green build while ignoring the initial failure costs the team critical quality signals.

### Temporary retry policy

If retries are temporarily unavoidable in CI:

- Keep the retry limit small.
- Save logs and stack traces from the initial failure.
- Report tests that passed only after retry separately.
- Attach an issue, owner, and deadline to remove the retry.
- Never retry tests that can cause dangerous side effects when executed multiple times.
- Never retry deterministic failures such as consistent assertion errors, compilation errors, or missing configuration.
- Track flaky rates per test over time.

Gradle's retry plugin and Maven Surefire's rerun settings can automate this policy. Exact syntax and reporting behavior depend on plugin versions. Check your build tool documentation and configure it so passing after retry is still flagged as flaky rather than silently turning into a clean pass.

### Test quarantine

If a test severely disrupts the pipeline, it can be temporarily moved out of blocking jobs while under investigation. Quarantine requires:

- The test name and concrete justification.
- A tracking issue for the root cause.
- An assigned owner and expiration date.
- A separate job that continues executing the test so signal is not lost.
- Criteria for returning the test to the main pipeline.

Quarantine does not mean deleting or forgetting the test. A test removed from the pipeline without an owner and deadline is usually forgotten and turns into a lasting quality blind spot.

## 11. Example Workflow for Investigating an Intermittent Spring Test

Suppose `OrderIntegrationTest.createsOrder` occasionally fails to find the newly created order.

**Initial observations:**

- Running the method alone: 20/20 passes.
- Running the full class: 18/20 passes.
- Running the full suite in parallel: 14/20 passes.
- Running the full suite sequentially: 20/20 passes.

These numbers suggest contention or shared-state dependence between tests. They do not yet pinpoint which test causes the interference.

**Further investigation:**

1. Record which test classes run concurrently and their thread IDs.
2. Find tests sharing the `orders` table, the same email, or the same business keys.
3. Check whether seed data and cleanup use fixed IDs.
4. Temporarily isolate classes sharing that database to pinpoint the conflicting group.
5. Give each test isolated data or guard exclusive resources.
6. Re-run at the same concurrency level and record results.

For example, two tests share `customer@example.test` under a unique constraint. One test cleans up by deleting the customer by email while another test has just created a related order. Depending on timing, cleanup deletes the other test's data or an insert hits a conflict. Generating a unique email per test and cleaning up by test-owned IDs eliminates the conflict.

After fixing, run the test alone, the full class, related groups, and the entire suite with CI's parallel settings. Once the failure no longer reproduces across many runs, save the evidence and remove temporary retries unless an independent infrastructure reason remains.

## 12. Actionable Investigation Checklist

| Question | Evidence to gather |
| --- | --- |
| Does the failure reproduce when run alone? | Exact launch command and multi-run results |
| Does it appear only in the class/suite? | Preceding tests and shared state |
| Does it appear only under parallelism? | Threads, workers, resource contention, and shared state |
| Does the test depend on time? | Clock, timezone, timeouts, sleeps, and async completion |
| Does the test depend on ordering? | Collection/query ordering, seed data, and lifecycle callbacks |
| Do tests share a database? | IDs/keys, transaction boundaries, locks, and cleanup |
| Do tests share a context? | Context cache, mutable singleton beans, `@DirtiesContext` |
| Does the test depend on external services? | Container readiness, ports, connection pools, DNS, and timeouts |
| Do retries hide the first failure? | Separate flaky report, first-attempt logs, and tracking issue |
| Is the fix proven stable? | Re-runs under identical conditions, full suite, and CI parity |

## 13. Conclusion

A flaky test signals that the test or its execution environment depends on an uncontrolled factor. Reproduce across expanding scopes, retain evidence, compare isolated vs. full-suite and sequential vs. parallel runs, then investigate shared state, async timing, time, data, transactions, context caching, and external services.

Retries can aid investigation or soften temporary impact from unstable infrastructure, yet a pass after retry must still be recorded as flaky with an owner responsible for fixing it. A test is trustworthy only when it stays stable through deterministic data, proper synchronization, isolated resources, and controlled environmental conditions—not because CI retried enough times to turn green once.
