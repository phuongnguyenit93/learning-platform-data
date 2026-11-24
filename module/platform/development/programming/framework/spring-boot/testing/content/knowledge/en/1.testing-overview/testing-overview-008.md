# Test Suite Independence, Repeatability, and Fast Feedback

> Scope: building and operating a test suite for Spring Boot applications so every test is trustworthy, results are stable across runs, and bugs are caught early enough for developers to fix within a short feedback loop.

## 1. Three Desired Properties and How to Recognize Them

A good test suite must answer three questions:

1. **Independence:** If you run one test alone, run the whole class, change execution order, or run on another machine, does the result stay the same? Test A must never require that “test B already created data” or leave state behind that breaks test C.
2. **Repeatability/determinism:** When code and inputs do not change, does a test produce the same outcome across many runs? Results should not depend on wall-clock time, leftover data, random seeds, machine speed, or flaky network services.
3. **Fast feedback:** Right after introducing a bug in code, does the author get a pinpointed failure signal quickly enough to fix it easily? Fast tests that give false signals, or fail too vaguely, produce poor feedback.

These three properties reinforce one another: isolating dependencies enables safe parallel runs; deterministic inputs make failures trustworthy; layering runs cheap checks first. However, **speed does not justify missing verification**, and “100% green” does not mean independent if the outcome depends on order.

| Property | Signs of Success | Warning Signs |
|---|---|---|
| Independence | Each test builds its own preconditions and manages its resources; passes when run alone | Passes only when running the full suite; relies on data created by another test |
| Repeatability | Same code and config yield the same expectations; failures are reproducible | Flips between green and red; re-running makes it “heal itself” |
| Fast feedback | Unit tests run very fast; small changes yield clear, early failures | Every test starts a Spring context, DB, and network; CI is slow |

## 2. Independence: Every Test Is a Complete Experiment

Think in **Arrange – Act – Assert**:

- **Arrange:** Prepare all inputs and state the test needs on its own.
- **Act:** Invoke one specific system behavior.
- **Assert:** Verify observable outcomes and relevant side effects.

A test should not depend on running *before*, *after*, or *alongside* another test. In JUnit Jupiter, default ordering is deterministic rather than guaranteed as a cross-test contract; it is not meant for chaining tests into an ordered scenario. If a business process truly consists of sequential steps, generally test the entire process inside **one** integration test with explicit Arrange/Act/Assert steps.

### 2.1. Common Sources of Shared State

- **`static` variables, singletons, caches, shared collections:** one test inserts data and another test sees it. Prefer instantiating fresh objects per test; if testing stateful Spring beans, reset state cleanly or redesign the bean.
- **Databases:** records from earlier tests remain; auto-increment IDs or unordered records break assertions. Use isolated fixtures, unique identifying keys, rollback where appropriate, or verified cleanup.
- **Files, directories, network ports, message queues, Redis caches:** tests collide on resource names or leave garbage data. Assign distinct namespaces and close resources after use; prefer JUnit's temporary directories for files.
- **Global configuration mutations:** JVM timezone, default locale, system properties, global clocks, static mocks. Minimize mutations; if unavoidable, restore them in `finally`/teardown and avoid running in parallel with tests using that configuration.
- **External resources:** sharing real accounts, real endpoints, or shared QA resources. Use fakes/mocks for unit tests and isolated test environments for integration tests.

**Anti-pattern example** (abbreviated snippet, not a standalone runnable class):

```java
static int createdOrders = 0;

@Test
void createsOrder() {
    createdOrders++;
    assertEquals(1, createdOrders);
}

@Test
void seesOrderFromPreviousTest() {
    assertEquals(1, createdOrders);
}
```

The second test depends on the first; running it alone fails, and repeating or reordering easily fails too. Fix by creating the required state directly inside each test. If you genuinely want to test a “create then read” flow, put both operations into **the same test**.

### 2.2. Fixture Lifecycle

JUnit Jupiter by default creates a new test class instance per test method; this helps for *instance* fields, yet **does not automatically reset static fields, databases, or Spring singletons**. `@BeforeEach` is useful for preparing fresh data; `@AfterEach` or `try-with-resources` handles releasing resources. Never turn teardown into a band-aid that indiscriminately wipes an entire shared database.

With Spring Boot:

- **Unit tests:** instantiate the class under test directly and fake/mock dependencies; do not boot `ApplicationContext` unnecessarily.
- **Slice tests:** use an appropriate scope like `@WebMvcTest` for web MVC or `@DataJpaTest` for JPA; load only relevant components.
- **Integration tests:** use `@SpringBootTest` when you genuinely need to verify configuration, multiple beans, or cross-layer flows.

**Transaction note:** `@DataJpaTest` usually runs inside a transaction and rolls back after each test; check actual configuration before relying on that behavior. In `@SpringBootTest(webEnvironment = RANDOM_PORT)`, the HTTP server handles requests on a different thread/transaction from the test thread; `@Transactional` on the test **does not guarantee rolling back** DB writes performed by server requests. In that case, use explicit seed/cleanup or an isolated database.

## 3. Repeatability: Control Everything That Can Change Outcomes

A deterministic behavioral test must depend on controlled inputs, not unrelated circumstances.

### 3.1. Time, Time Zones, and Calendars

Do not let business logic call `Instant.now()` or `LocalDate.now()` directly where timestamps need testing. Inject `java.time.Clock` and use `Clock.fixed(...)` in tests to fix “now” precisely. Use ISO-8601 timestamps with explicit offsets/UTC; test boundaries *before*, *right at*, and *after* deadlines. Only change time zones/locales when that itself is the behavior under test.

### 3.2. Randomness, Data Ordering, and Environment

- If random sequences are needed for testing, supply a fixed seed for deterministic behavioral tests; assert business invariants rather than one arbitrary random value. Never share a mutable `Random` object across tests.
- Do not assume `SELECT` without `ORDER BY` returns a stable order. When business rules require order, make the query sort; when order is not required, assert as a set.
- Pin or manage dependency versions, schema migrations, test configs, and container images; avoid sharing data with real systems.
- Never rely on CPU speed, thread count, CI execution timing, or Internet access to determine test results.

### 3.3. Never Use Fixed Delays as Synchronization

**Anti-pattern:** publish an async event, `Thread.sleep(1000)`, then assert. Fast machines may go green while loaded CI goes red; raising it to 10 seconds slows the suite down and still guarantees nothing.

**Alternative:** wait on an observable condition with a bounded timeout (e.g., Awaitility, proper synchronization primitives, or status-checking APIs). Set a timeout for the entire wait, include what condition wasn't met in the error message, and never swallow errors on expiration. If tests need simulated time, use a controllable scheduler/clock rather than waiting in real time.

### 3.4. External Dependencies and Test Data

- Unit tests for HTTP clients: replace external servers with stubs/fakes returning deterministic responses; test key requests, timeouts, and error paths.
- Integration tests for databases/queues: use isolated resources such as test containers with explicit initial data. Testcontainers runs real services from chosen images, yet **a shared container does not automatically mean isolated test data**.
- Never call production APIs or send real emails in the default suite. End-to-end runs against external resources must have their own environment and lifecycle.

## 4. Hands-on Java 17+ / JUnit Jupiter Example: Controlling `Clock`

Suppose a service checks that an access token is expired when the current time is **greater than or equal to** the deadline. The two files below run in any Java/Spring Boot project with JUnit Jupiter on the test classpath.

**File `src/main/java/com/example/testing/ExpiryPolicy.java`:**

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class ExpiryPolicy {
    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public boolean isExpired(Instant deadline) {
        Objects.requireNonNull(deadline);
        return !clock.instant().isBefore(deadline);
    }
}
```

**File `src/test/java/com/example/testing/ExpiryPolicyTest.java`:**

```java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ExpiryPolicyTest {
    private final Instant now = Instant.parse("2026-01-01T10:00:00Z");
    private final ExpiryPolicy policy =
            new ExpiryPolicy(Clock.fixed(now, ZoneOffset.UTC));

    @Test
    void beforeDeadlineIsValid() {
        assertFalse(policy.isExpired(now.plusSeconds(1)));
    }

    @Test
    void exactlyAtDeadlineIsExpired() {
        assertTrue(policy.isExpired(now));
    }

    @Test
    void afterDeadlineIsExpired() {
        assertTrue(policy.isExpired(now.minusSeconds(1)));
    }
}
```

In a Spring Boot Gradle project with dependency management configured, ensure JUnit Jupiter and JUnit Platform are present (usually from `spring-boot-starter-test`):

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Run the test class using the Gradle Wrapper from the project directory:

```bash
./gradlew test --tests com.example.testing.ExpiryPolicyTest
```

On Windows PowerShell use `.\gradlew.bat test --tests com.example.testing.ExpiryPolicyTest`. Expected result: **3 tests succeed**, Gradle completes the `test` task; exact console output may vary by Gradle/plugin version, so do not assume a single exact stdout line.

**Why does this example meet all three criteria?** Each test instantiates its own object and clock, shares no state, needs no Spring context/DB/network; the timestamp never changes so boundary assertions are stable; and results arrive immediately upon running unit tests. Production logic still uses a real clock when the app injects `Clock.systemUTC()`; tests inject a fixed clock to control inputs.

## 5. Spring Boot: Choosing a Test Level Sufficient to Catch Bugs

| Test Level | Primary Goal | Common Practice | Relative Speed |
|---|---|---|---|
| Unit | Business rules, transformations, boundaries, error branches | JUnit + real objects, stub/mock dependencies; no Spring loaded | Very fast |
| Slice | A narrow integration layer, mapping/validation/JPA queries | `@WebMvcTest`, `@DataJpaTest` as needed | Medium |
| Integration | Multiple beans, transactions, DB/queue connections, config | `@SpringBootTest` and isolated test infrastructure | Slower |
| End-to-end | User behavior or real service paths | Running application and essential components | Most expensive |

Classify by **the level of collaboration you need to prove**, not annotation preference. For instance, do not put `@SpringBootTest` on 200 arithmetic tests just because the project uses Spring Boot. Conversely, mocking all repositories and HTTP clients in a test meant to verify real connection settings is also insufficient.

### 5.1. Reusing Spring Contexts Properly

Spring TestContext caches `ApplicationContext` for tests sharing the same configuration within the same process, so grouping tests with compatible configurations cuts startup time. Changing profiles, properties, bean overrides, dynamic properties, or context configuration creates distinct cache keys. Use `@DirtiesContext` only when a test genuinely corrupts the context; overusing it forces context reloads and slows the suite down.

**Never mutate state just to keep the cache.** Context reuse saves time, yet DB/singleton fixtures must still remain clean between tests. The optimal approach is usually an unchanging context paired with independent test data, rather than recreating the context for every test.

### 5.2. Databases and Testcontainers

When fidelity with real PostgreSQL/MySQL is needed, Testcontainers can boot the DB inside a container; pin image versions and apply migrations just like the target environment. A container declared `static` with the JUnit extension is usually shared across test methods in the class, reducing startup overhead. However, data across methods is still shared unless reset. Choose one clear strategy:

1. Each test prepares data with unique keys and cleans up only the data it created; or
2. Transaction rollback if all operations belong to the same transaction managed by Spring Test; or
3. Create an isolated schema/database per test group when running in parallel or against a real server.

Do not enable parallel execution for the Testcontainers JUnit 5 extension by default: lifecycle coordination and shared resources must be verified separately; Testcontainers documentation warns that the extension does not support parallel execution in general.

## 6. Optimizing Feedback: Time to Detection Matters More Than Test Count

An effective feedback loop usually has layers:

1. **In the IDE / per small edit:** run relevant unit tests and cheap static checks.
2. **Before push / on pull requests:** run all unit tests, necessary slice tests, then critical integration tests.
3. **Nightly / pre-release:** run end-to-end, heavy load, or slow infrequently changing integration tests.

If a test runs in 5 seconds yet fails randomly, 10 re-runs do not make the team faster. Prioritize **trustworthy, diagnosable failure signals**, then reduce execution time.

Effective levers:

- Keep unit tests free of Spring contexts, files, DBs, and networks.
- Load only the context matching the scope under test; leverage context caching and minimize unneeded config.
- Seed minimal fixtures; avoid generating large datasets in every test unless testing large data.
- Avoid fixed `sleep`s; wait on conditions with timeouts.
- Group slow tests with JUnit `@Tag("integration")` or build task/source set mechanisms with clear CI rules; do not simply drop slow tests from every pipeline.
- Consider parallel execution once all tests are independent and infrastructure can handle it; measure again because CPU, DB, or container contention can increase total runtime.

### 6.1. Parallel Execution Is a Later Step, Not Step One

JUnit Jupiter runs sequentially by default. Enabling the configuration below in `src/test/resources/junit-platform.properties` is one option to run **classes** concurrently while keeping **methods within each class** sequential:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=concurrent
```

Enable only when there is no shared static state/DB/port/cache causing conflicts. For unavoidable shared resources, `@ResourceLock` can guard declared resources, though locking only serializes access and does not make data-dependent tests independent. Compare runtime and stability before/after enabling; specifically check DB connection limits and container lifecycles.

## 7. Identifying and Fixing Flaky Tests

A **flaky test** is a test that produces different results across runs when the code and expected conditions have not changed. Several common sources:

| Symptom | Possible Cause | Real Fix |
|---|---|---|
| Fails in full suite, passes alone | Shared state/fixtures, order assumptions | Find the shared writable resource, create isolated fixtures, clean up in the right scope |
| Fails only in CI | Timing, timezone, scarce resources, config differences | Fix clock/locale, specify environment explicitly, wait on conditions |
| Occasional timeouts | `sleep`, schedulers, external services, overload | Condition waits with timeouts, stub externals, isolate resources |
| Returned data changes order | Missing ORDER BY, index-based assertions | Sort when business rules require order, or compare as sets |
| Fails under parallel execution | Static mutable state, fixed ports, transaction/data contention | Isolate shared sources before enabling parallel runs |
| Spring tests sometimes fast, sometimes very slow | Cache misses, context reloads, container starts, differing profiling | Monitor context cache, reduce config variants, measure cold/warm separately |

Practical investigation workflow: record seed/inputs, profile, timezone, JDK, DB/image versions, threads, and full errors; re-run **a single test**, **the whole class**, and **the whole suite**, vary execution order, or repeat enough times to isolate it. JUnit `@RepeatedTest(20)` can help reproduce some bugs yet does not prove a test is independent; repeatable environments still need control. When fixing, add a regression test demonstrating the cause; never just bump timeouts, add infinite retries, or delete assertions to turn CI green.

## 8. A Before-and-After Design Example

Suppose an order-creation test calls a real API, reads `LocalDate.now()`, writes to a shared database, and expects the last row in the table to be its order. That test depends on network, wall clock, other tests' data, and DB ordering; it runs very slowly and flakes easily.

Redesign by verification goal:

- **Expiry/discount rules:** extract into a service taking `Clock`, repository interface, and inputs; unit test with fixed clock, fake repository, asserting exact boundaries.
- **HTTP contract:** use a web slice with deterministic request/response and validation; test authorization with appropriate test configuration.
- **Persistence:** test the repository on an isolated test database with per-test fixtures; assert record contents and key fields rather than guessing “the last row”.
- **Full path:** keep only a small number of integration tests truly going through server, DB, and necessary adapters; use a clear seed/cleanup strategy, explicit timeouts, and random ports where appropriate.

As a result, calculation bugs appear nearly instantaneously, mapping/database errors still have dedicated coverage, and end-to-end tests do not have to carry every edge case.

## 9. Self-Review Criteria for Tests or CI

Use these questions to validate the quality of **individual tests** and the **entire suite**:

- Does the test pass when run alone? Does it pass when repeated and when reordered within its group?
- Is there any static/singleton state, DB, file, topic, cache, system property, or shared environment resource the test implicitly relies on?
- Are fixtures created in Arrange with unique names/IDs and clear cleanup? Does rollback genuinely cover the relevant threads/transactions?
- Are time, timezone, locale, randomness, result ordering, and external responses controlled?
- Are there any `Thread.sleep` calls, infinite retries, vague assertions, or ignored failures just to keep tests green?
- Is the test at the right layer? Is it starting a context/container/network just to verify a calculation?
- On failure, do messages identify behavior, inputs, and expected/actual clearly enough to fix? Are useful logs kept without leaking secrets?
- Does PR CI give fast enough feedback? Have cold start, warm run, flake rate, and slow test groups been measured separately?
- Is parallel execution enabled only after verifying state and resource lifecycle independence?

**Operational principle:** a failure result must be meaningful. If a test frequently gives “false reds”, the whole team loses trust in the suite; if a test is fast yet misses critical bugs, feedback loses its value too. The goal is **independent to be trustworthy, deterministic to be repeatable, layered for early feedback**.

## References

- Spring Boot — [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html), including context caching and test slices.
- Spring Framework — [Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html).
- JUnit Jupiter — [Parallel Execution](https://docs.junit.org/5.13.1/user-guide/index.html#writing-tests-parallel-execution) and [Test Execution Order](https://docs.junit.org/5.13.1/user-guide/index.html#writing-tests-test-execution-order).
- Testcontainers — [JUnit Jupiter Extension](https://java.testcontainers.org/test_framework_integration/junit_5/).