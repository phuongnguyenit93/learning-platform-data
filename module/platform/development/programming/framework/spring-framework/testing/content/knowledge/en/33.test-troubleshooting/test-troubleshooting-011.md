# Tests Pass Individually Yet Fail in the Suite Due to Shared State

A test that always passes when run in isolation yet fails when executed as part of the full suite typically depends on state created, mutated, or cleaned up by another test. That state may reside in the JVM, Spring `ApplicationContext`, mock beans, databases, files, caches, environment variables, threads, or an asynchronous task still running after a test finishes.

This is a form of order-dependent test failure or resource contention (race condition). The effective fix is to locate the exact shared state, identify which test writes and which test consumes that state, and then isolate or synchronize the resource at the right scope.

## 1. Why Does an Individual Test Pass While the Suite Fails?

When running a single test on its own, it usually starts with a relatively clean JVM or test context state. When running the full suite, that test may execute after another test that has:

- Mutated a static field or singleton bean.
- Written data to the database without deleting it after the test.
- Stubbed or reset a mock bean shared across multiple tests.
- Registered expectations on a mock HTTP server and left them for another test to consume.
- Changed a system property, default locale, timezone, or working directory.
- Put data into a cache, message broker, or in-memory store.
- Started a background task without waiting for it to finish.
- Closed the Spring `ApplicationContext` while another test was still using that context.

The failing test may not be wrong in isolation. It is simply relying on an implicit assumption, such as an empty table, an unstubbed mock, a cold cache, or a singleton still holding its default value. That assumption no longer holds once other tests in the suite have run.

Example of order dependency:

```text
Test A                                 Test B
------                                 ------
writes activeTenant = "tenant-a"
                                       reads activeTenant
                                       expects default value
                                       receives "tenant-a" and fails
```

When B runs alone, `activeTenant` may still hold its default value so the test passes. When running the full suite, A leaves state behind that causes B to fail.

## 2. Distinguishing Shared-State Failures from Parallel Execution Failures

Both failure categories look similar on the surface yet have different causes:

| Failure category | Mechanism | Common symptoms |
|---|---|---|
| Order dependency | An earlier test leaves state for a later test | Fails consistently when run sequentially in a given order; reordering can change which test fails |
| Race condition | Multiple tests read/write a resource concurrently | Flaky failures, timing-dependent, or disappears when parallel execution is disabled |
| Resource leak | A test fails to close files, executors, subscriptions, servers, or contexts | Later tests in the suite hang, exhaust threads/ports/file handles, or emit logs after test completion |
| Altered environment config | A test modifies system properties, locale, timezone, or global variables | Tests involving date formatting, encoding, or paths fail only inside the suite |

A suite can exhibit several of these at once. Disabling parallel execution is a helpful diagnostic step, yet if the test still fails when run sequentially, look for leftover state or order dependencies.

## 3. Commonly Shared State Areas

### 3.1. Static Fields and Mutable Singletons

Static fields live at the class loader/JVM scope. Spring beans default to singleton scope within an `ApplicationContext`. If a test mutates the state of these objects, other tests can observe the change.

```java
@Component
class CurrentTenantHolder {

    private String tenantId = "default";

    void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }

    String getTenantId() {
        return tenantId;
    }
}
```

Suppose one test calls `setTenantId("tenant-a")` without restoring the value. The next test sharing the same context will read `tenant-a`.

Prefer designing beans not to hold per-request or per-test state. If state is necessary, pass it as parameters, store it in an appropriate scope, or provide an explicit reset API. In tests, restore state after each method if separate instances cannot be created.

### 3.2. Spring `ApplicationContext` Cache

The Spring TestContext Framework caches `ApplicationContext` instances so multiple tests with equivalent configurations can reuse the same context. This reduces startup time, yet it also means singleton beans, caches, and mock beans inside the context can be shared.

JUnit Jupiter creates a new test instance per test method by default (`PER_METHOD`), but that does not create a new Spring `ApplicationContext`. Hence, instance fields of the test class may be fresh while injected beans remain the same singletons.

Do not treat `@BeforeEach` as proof that all Spring state has been reset. It only runs before each method; beans inside the context retain their state unless tests or the framework explicitly reset them.

`@DirtiesContext` marks a context as no longer reusable and tells Spring to close/evict it from the cache according to the selected mode. This measure is for tests that genuinely alter context or singleton state that cannot be safely restored. It incurs the cost of recreating the context and can cause errors if another test is using that same context concurrently.

### 3.3. Shared Mockito Mocks

Mocks injected via `@MockitoBean` or the corresponding Spring Boot annotation typically reside in the `ApplicationContext`. Tests sharing the same context can access the same mock instance.

Example of two tests stubbing the same method with different outcomes:

```java
@SpringBootTest
class InventoryServiceTests {

    @MockitoBean
    InventoryGateway inventoryGateway;

    @Autowired
    InventoryService inventoryService;

    @Test
    void reportsTenItems() {
        when(inventoryGateway.available("SKU-1")).thenReturn(10);
        assertThat(inventoryService.available("SKU-1")).isEqualTo(10);
    }

    @Test
    void reportsTwentyItems() {
        when(inventoryGateway.available("SKU-1")).thenReturn(20);
        assertThat(inventoryService.available("SKU-1")).isEqualTo(20);
    }
}
```

Under parallel execution, one test's stubbing can overwrite the other's. Having the framework reset mocks after each test method reduces leakage during sequential execution, yet resetting is also a mutation on the shared mock instance. If one method resets while another method is still using the mock, behavior becomes unstable.

The preferred solution is creating separate mocks for unit tests that do not need a Spring context, or ensuring tests sharing mutable mocks do not run concurrently. Never use a singleton mock bean as an independent fixture across concurrent tests.

### 3.4. Databases, Files, and External Systems

A database does not automatically become clean just because a test method ends. Transaction rollbacks only affect operations participating in the test's transaction; data written via another thread, an independent transaction, an async worker, or an external system can persist.

Conflict-prone scenarios:

- Two tests insert the same email or business key with a unique constraint.
- One test deletes data that another test is reading.
- A test assumes an empty table while data from a previous test remains.
- Multiple tests share the same filename, temp directory, queue, or topic.
- Tests share an external account and mutate that account's state.

Prefer generating distinct data per test using unique IDs or namespaces. Use transaction rollbacks where appropriate; if data is written outside the transaction, clean up explicitly or provision per-test resources.

### 3.5. Mock HTTP Servers, Caches, and Message Brokers

`MockRestServiceServer`, mock HTTP servers, fake repositories, in-memory caches, and test message brokers can hold expectations or mutable data. When multiple tests share a single instance, one test's requests or messages can consume another test's expectations.

With `MockRestServiceServer`, the simplest fix is creating a dedicated `RestTemplate` and server in each test. With shared brokers or caches, use isolated topics/keys/namespaces and clean up data after the test. Do not share one expectation manager across independent tests.

## 4. Less Obvious Causes

Beyond beans and mocks, global JVM state can also couple tests together:

| State | Failure example | How to control |
|---|---|---|
| System properties | Test modifies `user.timezone` or a feature flag | Save the previous value and restore it in `finally` |
| Default locale/timezone | Date formatting differs across tests | Pass `Locale`/`ZoneId` explicitly; restore defaults if changing them is unavoidable |
| System clock | Test depends on current wall-clock time | Inject `Clock` and use `Clock.fixed(...)` |
| Random/UUID | Assertions depend on randomly generated values | Inject a generator or assert format/relationships instead of hard-coding |
| ThreadLocal/SecurityContext | Request data remains on a reused thread | Use cleanup mechanisms and assert the context is cleared |
| Static cache | Test reads stale cached data from a previous run | Use isolated caches or clear by key/namespace |
| Port/socket | Two test servers attempt to bind the same port | Use random ports and close servers after tests |
| Working directory/files | Tests overwrite the same file | Use a separate temp directory per test |

Do not mutate global state in tests when you can pass dependencies or per-object configuration instead. If mutating global state is unavoidable, ensure restoration runs even when assertions or test code throw exceptions.

## 5. Systematic Diagnostic Workflow

### Step 1: Confirm the Test Is Truly Independent in Isolation

Run the exact failing test method or class on its own. Then run it several times to see whether it is flaky by itself or only fails when other tests run beforehand.

Maven example:

```bash
./mvnw -Dtest=InventoryServiceTests#reportsTwentyItems test
```

Gradle example:

```bash
./gradlew test --tests "com.example.InventoryServiceTests.reportsTwentyItems"
```

### Step 2: Run the Whole Class and the Whole Suite

If the method passes alone yet fails within its class, suspect state shared across methods or test class lifecycle. If the class passes alone yet fails in the suite, suspect context caching, static state, or resources shared across classes.

Note which test ran immediately before the failing test. Do not look only at the stack trace; locate the first test that mutated the relevant state.

### Step 3: Disable Parallel Execution to Classify the Bug

Temporarily disable JUnit parallel execution and re-run the suite. If the failure disappears, there is likely a race condition or shared resource unsafe for concurrent access. If the failure persists depending on order, focus on cleanup and test ordering.

With JUnit Platform, you can configure:

```properties
junit.jupiter.execution.parallel.enabled = false
```

This is an isolation step. If the suite needs to run in parallel, fix the specific resource rather than leaving parallel execution disabled permanently.

### Step 4: Try Shuffling Order and Repeating the Suite

Run tests in randomized order or repeat multiple times to pinpoint the pair of tests causing the failure. If the failure surfaces after a specific test, inspect the resources that test mutates and the failing test reads.

When using a JUnit orderer or random seed, record the seed so you can reproduce the failure. Do not add `@Order` merely to force the failing test to run after another test; that usually hides the dependency instead of fixing it.

### Step 5: Inspect State Before and After Tests

For each suspected resource, determine:

1. Who creates or mutates it?
2. Who reads or depends on it?
3. Is its lifetime method, test instance, class, Spring context, JVM, or external system?
4. Where is it reset, and does reset run when a test fails?
5. Can two tests access it at the same time?

You can log context IDs, thread names, data keys, or mock invocations to determine the sharing scope. Add targeted logs only; avoid letting heavy logging alter timing enough to mask a race condition.

### Step 6: Create a Minimal Reproduction

When suspecting two tests interact, run them together in a single class or tiny suite. If the pair reproduces the failure, you have narrowed down the state source. Then isolate fixtures or add cleanup and re-run the full suite.

## 6. Fixes by State Category

### 6.1. Create Fresh Fixtures Per Test

For unit tests, instantiate mocks and objects under test inside each method:

```java
@Test
void reportsTenItems() {
    InventoryGateway gateway = mock(InventoryGateway.class);
    when(gateway.available("SKU-1")).thenReturn(10);

    InventoryService service = new InventoryService(gateway);

    assertThat(service.available("SKU-1")).isEqualTo(10);
}
```

Each method owns its own mock and service. No stubbing or invocation history is shared with other tests.

### 6.2. Reset State in a Controlled Manner

When you must use a singleton or static fixture, provide a reset API and invoke it in lifecycle hooks:

```java
@BeforeEach
void setUp() {
    tenantHolder.reset();
    cache.clear();
}

@AfterEach
void tearDown() {
    tenantHolder.reset();
    cache.clear();
}
```

Cleaning up in `@AfterEach` protects the next test; resetting in `@BeforeEach` protects the current test from stale state. Only use this if resetting is safe and tests do not run concurrently against the same resource. If multiple parallel tests mutate a singleton simultaneously, cleanup can still wipe state another test is actively using.

For system properties, restore the previous value rather than always deleting:

```java
String previous = System.getProperty("feature.mode");
try {
    System.setProperty("feature.mode", "test");
    // Perform assertions.
} finally {
    if (previous == null) {
        System.clearProperty("feature.mode");
    } else {
        System.setProperty("feature.mode", previous);
    }
}
```

### 6.3. Use Isolated Database Data

Generate a unique ID per test, such as a UUID or a namespace derived from the test method. All queries and cleanup operate strictly on data owned by that test.

```java
String email = "user-" + UUID.randomUUID() + "@example.test";
User saved = repository.save(new User(email));

assertThat(repository.findByEmail(email)).isPresent();

repository.deleteById(saved.getId());
```

This example illustrates per-test data isolation; in real projects, place cleanup in fixtures or lifecycle hooks so it still runs when assertions fail.

### 6.4. Isolate Files and Temporary Directories

JUnit Jupiter supports `@TempDir` so each test receives its own temporary directory:

```java
@Test
void writesReport(@TempDir Path tempDir) throws IOException {
    Path report = tempDir.resolve("report.txt");
    Files.writeString(report, "test report");

    assertThat(Files.readString(report)).isEqualTo("test report");
}
```

Never write test files to a fixed path in the working directory when multiple tests may execute concurrently.

### 6.5. Inject `Clock` Instead of Depending on System Time

Code calling `Instant.now()` directly makes tests dependent on execution time. Inject a `Clock` to fix time:

```java
Instant fixedInstant = Instant.parse("2026-01-15T10:00:00Z");
Clock clock = Clock.fixed(fixedInstant, ZoneOffset.UTC);
OrderService service = new OrderService(repository, clock);
```

Tests no longer depend on the default timezone or when the suite runs.

## 7. Special Handling for Spring `ApplicationContext` and `@DirtiesContext`

The Spring context cache is a performance optimization, not a per-test data isolation mechanism. If a test only mutates business data in a repository, clean up the data. If a test mutates a singleton bean, reset the bean. Only use `@DirtiesContext` when the context itself is mutated beyond safe reuse.

Example marking a context dirty after the class:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutationTests {
    // Test mutates configuration or a singleton that cannot be restored.
}
```

Method and class modes of `@DirtiesContext` determine when the context is marked dirty and closed. Using the wrong scope can slow down the suite or disrupt other tests sharing the same context.

Under JUnit parallel execution, class A may close a context while class B is still using that context. When this cannot be avoided, isolate the class or lock the shared resource using appropriate JUnit mechanisms. `@DirtiesContext` does not automatically wait for all other tests to finish before closing the context.

## 8. Controlling Parallel Execution When Resources Cannot Be Isolated

Prefer isolating resources first. When a group of tests must share mutable state, JUnit Jupiter offers serialization mechanisms:

### `@Execution(SAME_THREAD)`

Instructs nodes in the class's execution tree to run on the same thread:

```java
@SpringBootTest
@Execution(ExecutionMode.SAME_THREAD)
class SharedSingletonTests {
    // Methods in this class do not run concurrently with each other.
}
```

This annotation does not lock other classes sharing the same singleton. Only use it when sharing is confined to that class.

### `@ResourceLock`

Declares a shared resource name across all tests that access that state:

```java
@ResourceLock(value = "shared-inventory-cache",
        mode = ResourceAccessMode.READ_WRITE)
class InventoryCacheTests {
    // Every other test using this cache must also declare the same lock name.
}
```

Tests declaring the same resource name are coordinated by JUnit to prevent conflicts according to access mode. If a test omits the lock, JUnit has no way of knowing it also touches that resource. Locks coordinate only within the same JUnit execution, not across separate JVMs or forked builds.

### `@Isolated`

When a class must run exclusively relative to all other Jupiter tests, use `@Isolated`:

```java
@SpringBootTest
@Isolated
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class GlobalContextMutationTests {
    // This class runs in isolation within the JUnit execution.
}
```

`@Isolated` is helpful for tests mutating global resources or closing contexts that cannot be expressed with a fine-grained lock. It is a broad-scope measure; restrict it to classes that genuinely need it.

### Disabling Parallel Execution

If a suite was not designed for concurrent execution, temporarily disable parallel execution in `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled = false
```

This stabilizes the suite in the short term and helps confirm race conditions. When possible, return to isolating state or locking specific test groups rather than slowing down the entire suite.

## 9. Awaiting and Cleaning Up Asynchronous Work

A test method can finish before tasks it launched complete. Background tasks can still write to the database, mutate mocks, or call beans in the Spring context after the next test has already started.

For `CompletableFuture`, wait for the result within a timeout:

```java
CompletableFuture<Result> future = service.startAsyncWork();
Result result = future.get(5, TimeUnit.SECONDS);

assertThat(result.status()).isEqualTo("DONE");
```

For Reactor, verify publisher completion or cancel subscriptions:

```java
StepVerifier.create(service.process())
        .expectNextMatches(Result::isSuccessful)
        .verifyComplete();
```

If a test creates its own executor, shut it down in `@AfterEach` or `try/finally`, and await task termination. Never leave background threads holding references to test mocks or contexts after the method ends.

## 10. Avoid Fixing Tests by Making Them Order-Dependent

When discovering that A must run before B to pass, do not default to adding `@Order` to enforce that sequence. Ordering merely hides state leakage and can break under suite configuration, test engine, or build tool changes.

Independent tests should be able to run in any order. If a test needs data created by a prior step, merge the steps into one meaningful workflow test or construct the data fixture directly inside that test.

`@TestMethodOrder` is appropriate when ordering is an intentional part of a scenario (such as testing a state machine across inseparable steps), but should not be used to patch over a test suite with uncleaned shared state.

## 11. Quick Investigation Checklist

When a test fails only in the suite, check step by step:

1. Does the test fail alone, within its class, or only across the full suite?
2. Does disabling parallel execution make the failure disappear?
3. Which resource did the immediately preceding test write or modify?
4. Do both tests share the same `ApplicationContext`, singleton bean, or mock bean?
5. Do databases, files, caches, queues, or mock servers contain leftover data/expectations?
6. Did a test modify system properties, locale, timezone, static fields, or `ThreadLocal`?
7. Are background tasks or reactive subscriptions still active after the method finishes?
8. Does cleanup run in every case, including when assertions fail?
9. Can each test create its own fixtures or isolated data namespace?
10. If isolation is impossible, do all participating tests declare the same `@ResourceLock` or serialization mechanism?

## 12. Common Pitfalls

| Symptom | Common cause | Resolution |
|---|---|---|
| Test passes alone yet fails after another test | Earlier test left state in static fields, singletons, or caches | Find the state's writer and reader; reset or create isolated fixtures |
| Mock returns unexpected results during suite run | Multiple tests stub/reset the same mock bean in the context cache | Create separate mocks or serialize all tests using that mock |
| Test fails intermittently only with parallel enabled | Multiple threads write to mutable resources concurrently | Isolate resources or use `@ResourceLock` at the right scope |
| Database test reports duplicate key | Data from another test remains or tests share a fixed business key | Generate unique data and clean up explicitly |
| File test reads wrong data | Multiple tests write to the same path | Use `@TempDir` or per-test filenames |
| Later test sees a different timezone/locale | Earlier test mutated global defaults without restoring them | Pass configuration explicitly or restore in `finally` |
| Context closes mid-request | Another test used `@DirtiesContext` while the context was still shared | Avoid unnecessary dirtying; isolate/lock affected classes |
| Logs or database change after test finished | Background task did not finish | Await futures, verify/cancel publishers, and shut down executors |
| Adding `@Order` makes suite pass yet reordering breaks it | Tests are order-dependent rather than independent | Fix fixtures and cleanup; never rely on suite-wide order |

## 13. Principles for Designing a Stable Suite

- Every test creates its own input data and never relies on data from another test.
- Minimize mutable static fields and mutable singleton beans in test contexts.
- Create dedicated mocks, mock servers, and fixtures whenever possible.
- Clean up databases, files, caches, messages, and system properties at the appropriate scope.
- Use `Clock`, ID generators, and dependency injection to control time- or environment-dependent values.
- Await or cancel all asynchronous work before the test method finishes.
- Use `@DirtiesContext` only when the context genuinely cannot be reused.
- When concurrent execution over shared state is unavoidable, lock the right resource and ensure every participating test declares the lock.
- Never use `@Order` to mask dependencies between independent tests.

## 14. Key Takeaways

A test passing alone yet failing in the suite usually signals shared state or incomplete cleanup. Locate where the state lives, which test writes it, and which test reads it, then classify it as an order dependency, a race condition, or a resource leak. Prefer per-test fixtures and data; reset global state safely; await async work; and use `@DirtiesContext` only when necessary. When a resource cannot be isolated, use `@ResourceLock`, `@Execution(SAME_THREAD)`, `@Isolated`, or disable parallel execution within the appropriate scope. A stable suite should yield identical results whether tests run alone, in different orders, or alongside any other independent tests.

