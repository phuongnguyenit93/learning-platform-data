# TestExecutionListener and Test Lifecycle Phases

## 1. What Is TestExecutionListener?

The **Spring TestContext Framework** is the infrastructure that lets JUnit Jupiter integrate with Spring to load and cache an `ApplicationContext`, inject beans into tests, manage transactions, run SQL scripts, handle `@DirtiesContext`, and perform other setup/cleanup tasks.

`org.springframework.test.context.TestExecutionListener` is an **SPI (Service Provider Interface)** for behaviors that want to participate in that test lifecycle. A listener receives a `TestContext` object at defined points and can log, prepare resources, inspect state, or clean up after a phase.

Three core components:

- **`TestContext`**: carries the testing context such as the test class, current instance, current method, test method exception, and access to the `ApplicationContext` when needed.
- **`TestContextManager`**: manages the test context and orchestrates listeners. It invokes each callback by phase and determines processing order.
- **`TestExecutionListener`**: provides hooks at the Spring TestContext level; each implementation only needs to override the hooks it actually uses.

In JUnit Jupiter, **`SpringExtension`** connects the JUnit lifecycle with `TestContextManager`. Annotations like `@SpringBootTest` or `@SpringJUnitConfig` typically already integrate SpringExtension, so you do not need to register `@ExtendWith(SpringExtension.class)` redundantly.

**Important distinction:** a listener is not a `@Test` method and does not directly drive application business rules. Plain Java unit tests using `new Service(...)` normally do not need TestContext or listeners; this mechanism is useful when testing interactions with a Spring context or needing a shared lifecycle hook.

## 2. Seven Callbacks in a Spring TestContext Lifecycle

`TestExecutionListener` defines the following callbacks (in Spring Framework 6.x/7.x; the API names are stable across the versions mentioned). Each callback receives a `TestContext` parameter.

| Callback | Corresponding JUnit Jupiter Point | Common Purpose |
| --- | --- | --- |
| `beforeTestClass(TestContext)` | Before the class's `@BeforeAll` methods | Prepare class-level resources or record test start |
| `prepareTestInstance(TestContext)` | Right after JUnit creates the test class instance | Inject dependencies into the test instance, process instance-level data |
| `beforeTestMethod(TestContext)` | Before `@BeforeEach` | Set up fixtures, start a test-managed transaction |
| `beforeTestExecution(TestContext)` | After `@BeforeEach`, right before the `@Test` body | Start timing just the test body, start tracing |
| `afterTestExecution(TestContext)` | Right after the `@Test` body, before `@AfterEach` | Record outcome, stop timing the test body |
| `afterTestMethod(TestContext)` | After `@AfterEach` | Clean up resources, finish transaction, wrap up around each test |
| `afterTestClass(TestContext)` | After `@AfterAll` | Clean up class-level resources, summarize trace or final class report |

The word "Method" in `beforeTestMethod` and `afterTestMethod` **is easy to misunderstand**. `beforeTestMethod` does not mean "right at the first line of `@Test`": it runs **before setup**. Likewise, `afterTestMethod` runs **after teardown**. If you want points wrapping strictly the **test body**, use the `beforeTestExecution` / `afterTestExecution` pair.

`prepareTestInstance` is called on each test instance created by JUnit. Under the default `PER_METHOD` lifecycle, each normal test invocation gets its own instance. When switching to `@TestInstance(PER_CLASS)`, the number of instance creations/preparations can differ; do not assume this callback always runs once per test method.

### Overview Diagram for a Single Test

~~~text
Spring: listener.beforeTestClass
JUnit : @BeforeAll
JUnit : create test class instance
Spring: listener.prepareTestInstance
Spring: listener.beforeTestMethod
JUnit : @BeforeEach
Spring: listener.beforeTestExecution
JUnit : @Test / test method body
Spring: listener.afterTestExecution
JUnit : @AfterEach
Spring: listener.afterTestMethod
JUnit : @AfterAll
Spring: listener.afterTestClass
~~~

The diagram shows the **main hook points**, not every internal Spring/JUnit operation. Spring also executes default listeners, extensions, and context management logic not drawn in the diagram. With multiple test invocations, the block from `beforeTestMethod` to `afterTestMethod` repeats per invocation; class-level callbacks wrap the entire class.

## 3. How Does SpringExtension Connect JUnit Jupiter to Spring?

JUnit Jupiter has its own extension model: `BeforeAllCallback`, `TestInstancePostProcessor`, `BeforeEachCallback`, `BeforeTestExecutionCallback`, `AfterTestExecutionCallback`, `AfterEachCallback`, and `AfterAllCallback`. `SpringExtension` implements the appropriate extension interfaces and forwards events to `TestContextManager`.

Example test class using a Spring context without declaring `@ExtendWith` directly:

~~~java
@SpringJUnitConfig(TestConfig.class)
class ExampleSpringTest {
    @Autowired
    Clock clock;

    @Test
    void readsClockFromSpring() {
        assertNotNull(clock);
    }
}
~~~

This is an **illustrative snippet**, requiring `TestConfig` and the corresponding imports. `@SpringJUnitConfig` is a composed annotation combining context configuration and `SpringExtension` registration. With Spring Boot, `@SpringBootTest` also integrates SpringExtension; slices like `@WebMvcTest` or `@DataJpaTest` are similarly supported by Boot.

If you place `@TestExecutionListeners(...)` on a plain JUnit class **without enabling Spring TestContext integration**, you cannot expect Spring to invoke the listener automatically. There must be a Spring integration mechanism such as `@SpringJUnitConfig`, `@SpringBootTest`, or `@ExtendWith(SpringExtension.class)` paired with appropriate Spring configuration.

### Ordering Relative to `@BeforeEach` / `@AfterEach`

Two distinctions to remember:

- `beforeTestMethod` happens **before** `@BeforeEach`. Therefore, a listener at this point must not assume fixtures created in `@BeforeEach` are already ready.
- `beforeTestExecution` happens **after** `@BeforeEach`. This is the right hook when measuring just the `@Test` body duration, excluding JUnit setup time.
- `afterTestExecution` happens **before** `@AfterEach`. It can observe the test method's exception, but teardown has not yet completed.
- `afterTestMethod` happens **after** `@AfterEach`. It can clean up resources kept alive throughout setup + test + teardown.

These differences matter especially for `@Transactional`, `@Sql`, timing metrics, and observing post-test state.

## 4. What Do Spring's Built-in Listeners Handle?

Most projects **do not need to write a custom** `TestExecutionListener`. Spring TestContext already registers default listeners; Spring Boot and other libraries can contribute additional listeners as well.

| Illustrative Listener | Primary Responsibility |
| --- | --- |
| `DependencyInjectionTestExecutionListener` | Injects beans/values into the test instance |
| `DirtiesContextBeforeModesTestExecutionListener` | Handles `@DirtiesContext` modes that occur before a test/class |
| `DirtiesContextTestExecutionListener` | Handles modes that mark a context dirty after a test/class |
| `TransactionalTestExecutionListener` | Manages test-managed transactions for `@Transactional` tests |
| `SqlScriptsTestExecutionListener` | Executes `@Sql` at the configured phase |
| `ServletTestExecutionListener` | Sets up servlet mocks for web test contexts |
| `EventPublishingTestExecutionListener` | Publishes test execution events when conditions allow |
| `ApplicationEventsTestExecutionListener` | Supports recording application events during tests |
| Listeners for bean overrides/mocks, caching, or observation | Depends on Spring Framework, Spring Boot versions, and integrations actually on the classpath |

**Do not hardcode assumptions about the listener list or `@Order` values across every version:** the default listener set can evolve across Spring/Boot upgrades. For example, listeners handling bean overrides and observation appeared in newer framework generations; check your project's documentation and actual dependencies for active configuration.

Example for transactions: `TransactionalTestExecutionListener` can start a transaction around a `@Transactional` test and roll it back by default after the test under typical test-managed transaction usage. JUnit's per-test callbacks run within that transaction scope; the transaction closes after `@AfterEach` in TestContext order.

**Do not write a custom listener to replace a default listener that already does the job.** Adding a new listener is justified only when there is a real need such as uniform tracing, specialized environment setup, shared test event capture, or integrating telemetry.

## 5. Registering Custom Listeners with `@TestExecutionListeners`

Place `@TestExecutionListeners` on the test class to declare one or more implementations:

~~~java
@TestExecutionListeners(
        listeners = AuditTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
~~~

This is an **annotation snippet on a test class**, and `AuditTestExecutionListener` is only an illustrative name; the runnable example in Section 6 uses a concrete listener class.

### How Do `REPLACE_DEFAULTS` and `MERGE_WITH_DEFAULTS` Differ?

| `mergeMode` | Meaning | Risk / Benefit |
| --- | --- | --- |
| `REPLACE_DEFAULTS` | The locally declared listeners replace the default set under Spring's config rules | Easy to accidentally lose dependency injection, transactions, `@Sql`, or default integrations |
| `MERGE_WITH_DEFAULTS` | Merges custom listeners with default listeners; deduplicates and orders them | Usually the safe choice when adding a listener to the existing infrastructure |

When declaring a custom listener without specifying `mergeMode`, the annotation defaults to `REPLACE_DEFAULTS`. Therefore, in most Spring Boot tests, **explicitly specify `MERGE_WITH_DEFAULTS`** when you only want to add functionality. Do not trade away all default mechanisms just to add a logging hook.

When inheriting from a base test class or using `@Nested`, also consider `inheritListeners` and TestContext inheritance policies. A listener can be declared on a superclass/enclosing class and inherited as configured; avoid duplicate registration unless intended.

### Execution Order of Multiple Listeners

When multiple listeners are present, Spring sorts them deterministically, taking `Ordered` or `@Order` into account (via `AnnotationAwareOrderComparator`) for listeners discovered/merged under that mechanism. **Lower** order numbers typically execute earlier on the "before" side.

If listener A comes before B:

~~~text
A.beforeTestMethod
  B.beforeTestMethod
  @BeforeEach / @Test / @AfterEach
  B.afterTestMethod
A.afterTestMethod
~~~

This is **wrapping behavior**: the "after" callbacks run in **reverse** order of "before." This is not cosmetic; for example, a transaction-managing listener must wrap a SQL-executing listener when SQL needs to run inside the transaction.

When a listener does not specify an order, Spring has rules for placing it in the chain; do not infer order from class position in the annotation list when default listeners are also present. When order affects behavior, declare `@Order`/`Ordered` intentionally and verify the rules against your project's dependencies.

## 6. Complete Example: Printing the Exact Phases of a Test

This illustrative example runs on **Spring Boot 3.x / Spring Framework 6.x, Java 17+, JUnit Jupiter**. We build a listener that records callbacks, a test with a Spring bean, and print the timeline in `afterTestClass`. The test **deliberately has only one `@Test`**, run sequentially, so the output is easy to follow; do not use an unsynchronized `static` list as a trace recorder across a parallel suite.

### 6.1. Listener Class

**File `src/test/java/com/example/testing/LifecycleTraceListener.java`:**

~~~java
package com.example.testing;

import java.util.ArrayList;
import java.util.List;

import org.springframework.test.context.TestContext;
import org.springframework.test.context.support.AbstractTestExecutionListener;

public class LifecycleTraceListener extends AbstractTestExecutionListener {
    static final List<String> EVENTS = new ArrayList<>();

    public LifecycleTraceListener() {
    }

    @Override
    public void beforeTestClass(TestContext context) {
        EVENTS.add("listener.beforeTestClass");
    }

    @Override
    public void prepareTestInstance(TestContext context) {
        EVENTS.add("listener.prepareTestInstance");
    }

    @Override
    public void beforeTestMethod(TestContext context) {
        EVENTS.add("listener.beforeTestMethod");
    }

    @Override
    public void beforeTestExecution(TestContext context) {
        EVENTS.add("listener.beforeTestExecution");
    }

    @Override
    public void afterTestExecution(TestContext context) {
        EVENTS.add("listener.afterTestExecution");
    }

    @Override
    public void afterTestMethod(TestContext context) {
        EVENTS.add("listener.afterTestMethod");
    }

    @Override
    public void afterTestClass(TestContext context) {
        EVENTS.add("listener.afterTestClass");
        EVENTS.forEach(System.out::println);
    }
}
~~~

`AbstractTestExecutionListener` provides no-op methods and a suitable default order when no custom priority is needed. Here only the methods we want to observe are overridden; the `TestExecutionListener` interface also provides empty default implementations so you can implement it directly if preferred.

`EVENTS` is only for demonstration; it is mutable static state and **not suitable as a real shared trace collector** when multiple classes use the listener or tests run in parallel. In real systems, use a logger, per-test/method data structures, or a properly synchronized reporter/extension.

### 6.2. Test Class Integrated with Spring TestContext

**File `src/test/java/com/example/testing/LifecycleTraceTest.java`:**

~~~java
package com.example.testing;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringJUnitConfig(LifecycleTraceTest.TestConfig.class)
@TestExecutionListeners(
        listeners = LifecycleTraceListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class LifecycleTraceTest {
    @Autowired
    Clock clock;

    @BeforeAll
    static void beforeAll() {
        LifecycleTraceListener.EVENTS.add("junit.BeforeAll");
    }

    @BeforeEach
    void beforeEach() {
        LifecycleTraceListener.EVENTS.add("junit.BeforeEach");
    }

    @Test
    void fixedClock_whenInjected_matchesExpectedInstant() {
        assertNotNull(clock);
        assertEquals(
                Instant.parse("2024-01-01T00:00:00Z"),
                clock.instant()
        );

        List<String> events = LifecycleTraceListener.EVENTS;
        assertEquals(
                "listener.beforeTestExecution",
                events.get(events.size() - 1)
        );

        events.add("junit.Test");
    }

    @AfterEach
    void afterEach() {
        LifecycleTraceListener.EVENTS.add("junit.AfterEach");
    }

    @AfterAll
    static void afterAll() {
        LifecycleTraceListener.EVENTS.add("junit.AfterAll");
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfig {
        @Bean
        Clock clock() {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }
    }
}
~~~

**Why does this code genuinely prove the lifecycle?**

- `@SpringJUnitConfig` registers SpringExtension and loads the `Clock` bean configuration without starting a full Spring Boot server.
- `@TestExecutionListeners(..., MERGE_WITH_DEFAULTS)` adds the listener while preserving `DependencyInjectionTestExecutionListener`; consequently `@Autowired Clock` is assigned before the test uses it.
- `@BeforeAll` and `@AfterAll` are `static` under JUnit Jupiter's default test instance lifecycle.
- The test method asserts that `Clock` has the value injected from the context and that `beforeTestExecution` just ran; it records `junit.Test` after assertions succeed.
- `afterTestClass` prints the recorded lines. If an assertion fails, `junit.Test` may not be recorded; the output below is expected for a **passing run**.

### 6.3. Configuration and Run Commands

In a Spring Boot 3.x project with plugins, repositories, and Java 17+ toolchain/JDK already configured, add standard test configuration in `build.gradle` (Groovy DSL):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        showStandardStreams = true
    }
}
~~~

`spring-boot-starter-test` provides JUnit Jupiter and Spring TestContext in common Spring Boot 3.x versions. This configuration snippet is not a complete standalone build file.

Run from the project directory containing the Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.testing.LifecycleTraceTest"
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.testing.LifecycleTraceTest"
~~~

With exactly the two files above, one test method, valid configuration, and no concurrent tests sharing `EVENTS`, **12 lines printed by `System.out.println` in the listener** appear in this order:

~~~text
listener.beforeTestClass
junit.BeforeAll
listener.prepareTestInstance
listener.beforeTestMethod
junit.BeforeEach
listener.beforeTestExecution
junit.Test
listener.afterTestExecution
junit.AfterEach
listener.afterTestMethod
junit.AfterAll
listener.afterTestClass
~~~

Gradle and Spring may print additional logs and test runner metadata. The list above is **the lines explicitly printed by the example**, not the entire Gradle stdout. Because the test code relies on Spring/JUnit libraries, you cannot just run `javac LifecycleTraceTest.java` without providing the dependency classpath; using configured Gradle/Maven is the proper way.

## 7. What Is Reading `TestContext` Used For?

Listeners receive `TestContext`. Useful APIs include:

| API | Meaning | When to Access |
| --- | --- | --- |
| `getTestClass()` | The test class being managed | When recording class-level information |
| `getTestInstance()` | Current test class instance | After the instance has been created |
| `getTestMethod()` | Current test method | When inside per-test phases |
| `getTestException()` | Exception thrown by the **test body**, if any | After `afterTestExecution`/appropriate phase per API contract |
| `getApplicationContext()` | Accesses the test's Spring context; may trigger loading if not yet loaded | When the listener genuinely needs beans/config |
| `setAttribute(...)` / `getAttribute(...)` | Stores data scoped to the test context | When small state is needed across callbacks; watch concurrency |

Do not call `getTestInstance()` in `beforeTestClass` and assume an object exists: at that milestone, test instance creation has not occurred yet. Similarly, do not use `getTestException()` to conclude whether the whole test passed or failed, because failures in `@BeforeEach`, `@AfterEach`, or other callbacks are not necessarily represented identically to a `@Test` body exception.

### Example Listener Timing the `@Test` Body

This is an **illustrative implementation snippet inside a listener class**, not a standalone Java file:

~~~java
private static final String START_KEY = "example.test.startNanos";

@Override
public void beforeTestExecution(TestContext context) {
    context.setAttribute(START_KEY, System.nanoTime());
}

@Override
public void afterTestExecution(TestContext context) {
    Long start = context.getAttribute(START_KEY);
    if (start != null) {
        long elapsedNanos = System.nanoTime() - start;
        System.out.println("Elapsed ns: " + elapsedNanos);
        context.removeAttribute(START_KEY);
    }
}
~~~

On `TestContext`, `getAttribute` returns `Object`; the code above **requires a cast** because the Java compiler does not implicitly convert `Object` to `Long`. The valid way to embed into the listener class is:

~~~java
@Override
public void afterTestExecution(TestContext context) {
    Object value = context.removeAttribute(START_KEY);
    if (value instanceof Long start) {
        long elapsedNanos = System.nanoTime() - start;
        System.out.println("Elapsed ns: " + elapsedNanos);
    }
}
~~~

Both snippets are shown side-by-side to highlight **type checking** when retrieving attributes; **do not paste both `afterTestExecution` methods into the same class**. Use only the second variant in real code, paired with `START_KEY` and `beforeTestExecution` above. `nanoTime` is suitable for elapsed durations, not wall-clock timestamps; measured values **have no fixed stdout**.

If the goal is to measure setup and teardown as well, the `beforeTestMethod`/`afterTestMethod` pair is the appropriate wrapper. Do not merge different intervals and misrepresent them as "business code duration."

## 8. Which Phases Do Transactions, `@Sql`, and `@DirtiesContext` Bind To?

### Test-Managed Transactions

In a Spring test with `@Transactional` and the default `TransactionalTestExecutionListener`, Spring typically starts the transaction at `beforeTestMethod` (that is, **before** `@BeforeEach`) and ends it after `@AfterEach` at `afterTestMethod`. With standard test-managed transactions, rollback is the default unless configured otherwise to commit.

~~~text
TransactionalTestExecutionListener.beforeTestMethod
    → starts transaction
JUnit @BeforeEach
JUnit @Test
JUnit @AfterEach
TransactionalTestExecutionListener.afterTestMethod
    → rolls back / commits per configuration
~~~

**Pitfall:** Data written in `@BeforeEach` typically participates in the test-managed transaction when using supported infrastructure. If the test spawns new threads, calls external systems, or opens separate transactions, do not assume every side effect rolls back. To run logic **outside** the test transaction, Spring provides `@BeforeTransaction`/`@AfterTransaction` for appropriate use.

### `@Sql`

`SqlScriptsTestExecutionListener` runs scripts for `@Sql` at the specified phase (for example `BEFORE_TEST_METHOD` or `AFTER_TEST_METHOD`). Relative ordering with `TransactionalTestExecutionListener` and `@SqlConfig(transactionMode=...)` settings determine whether the script runs inside the test transaction or a separate transaction.

Do not use a custom listener to wipe tables in `afterTestExecution` if `@AfterEach` or `@Sql(AFTER_TEST_METHOD)` still needs that data; understanding **listener order** and cleanup timing is essential to avoid flaky failures.

### `@DirtiesContext`

`@DirtiesContext` marks the `ApplicationContext` as no longer safe for reuse and affects context caching. Listeners handling before/after modes have specific execution points. This **is not equivalent** to rolling back a database, resetting every file, closing external system connections, or always creating a fresh context for each test.

Use `@DirtiesContext` when a test genuinely mutates context state in a way that affects other tests; overusing it slows down the suite by forcing context reloads.

## 9. Failures in Callbacks and Cleanup

Listener lifecycle hooks can fail, and an error in a setup hook can prevent the `@Test` body from running. Therefore:

- **"Before" hooks**: if a listener throws an exception in a "before" phase, remaining listeners in that same phase may not run; the test may be marked failed before entering the test body.
- **"After" hooks**: Spring `TestContextManager` attempts to invoke remaining cleanup listeners in reverse order even if an "after" listener fails; the first exception is reported and subsequent failures may be attached as suppressed exceptions.
- **Errors crashing the JVM**: end-of-class/test cleanup is not guaranteed to run.
- **State assumptions**: do not assume callbacks always have `TestContext.getTestMethod()`, an instance, or an `ApplicationContext` available in every phase.

Resources created by a listener should have clear ownership and be cleaned up in the matching counterpart hook. For per-test resources, `beforeTestMethod`/`afterTestMethod` may fit; for resources wrapping only the `@Test` body, use `beforeTestExecution`/`afterTestExecution`.

If listener code only logs information, avoid letting logging throw exceptions that cause an otherwise passing test to be marked FAIL. If a listener enforces a mandatory framework check, failures should produce clear messages distinguishing them from business errors.

## 10. `TestExecutionListener`, JUnit Extensions, and Application Events Are Not the Same

These three mechanisms have similar names or ideas, but differ in authority and execution context:

| Mechanism | Belongs To | Suitable When |
| --- | --- | --- |
| `org.springframework.test.context.TestExecutionListener` | Spring TestContext, invoked by `TestContextManager` | Need access to `TestContext` and coordination with DI, transactions, SQL, context |
| `org.junit.jupiter.api.extension.*Callback` and `@ExtendWith` | JUnit Jupiter | Need general test lifecycle extensions even without Spring |
| `@EventListener` receiving `BeforeTestMethodEvent`, `AfterTestMethodEvent`, etc. | Bean inside Spring's `ApplicationContext` | Want to use Spring DI to handle test execution events once the context is loaded |

There is also **`org.junit.platform.launcher.TestExecutionListener`**, which is a JUnit Platform Launcher API for tracking/reporting the test plan and launcher-level results. It **is not** `org.springframework.test.context.TestExecutionListener` and does not receive the same callbacks or context.

### `EventPublishingTestExecutionListener`

`EventPublishingTestExecutionListener` (registered by default in standard configurations) can translate lifecycle hooks into Spring application events:

- `BeforeTestClassEvent`, `PrepareTestInstanceEvent`.
- `BeforeTestMethodEvent`, `BeforeTestExecutionEvent`.
- `AfterTestExecutionEvent`, `AfterTestMethodEvent`, `AfterTestClassEvent`.

A bean can handle them with `@EventListener` or the corresponding composed annotations. However, **events are only published when the `ApplicationContext` has already been loaded**; the publishing listener does not force Spring to load the context early. Thus, `BeforeTestClassEvent` may **not fire** for the first class using an unloaded context, and `AfterTestClassEvent` may not fire if the context was closed or evicted from cache.

If you need a guarantee that a callback runs for every class, a direct custom `TestExecutionListener` is usually clearer than relying on bean events dependent on context state.

## 11. Practical Scenarios: Choosing the Right Callback for the Goal

| Requirement | Phase to Consider | Why? |
| --- | --- | --- |
| Log at the start/end of a test class | `beforeTestClass` / `afterTestClass` | Wraps the entire class lifecycle |
| Inject beans into the instance | `prepareTestInstance` | Default DI listener already handles this |
| Prepare data used by both `@BeforeEach` and `@Test` | `beforeTestMethod` | Runs before JUnit setup |
| Measure exact duration of the `@Test` body | `beforeTestExecution` / `afterTestExecution` | Excludes most JUnit setup/teardown |
| Clean up resources even after `@AfterEach` | `afterTestMethod` | Avoids wiping data while JUnit teardown still needs it |
| Manage transactions | Default `TransactionalTestExecutionListener` | Avoid reimplementing transaction handling manually |
| Run SQL before/after tests | `@Sql` with `SqlScriptsTestExecutionListener` | Uses built-in framework support |
| Mark context modified and non-reusable | `@DirtiesContext` | Lets Spring cache/loader coordinate |
| Emit metrics/tracing processed by Spring beans | Test execution events when conditions fit | Leverages DI and event infrastructure |

There is no single "best" hook for every need. Identify **over what interval a resource exists**, which callback wraps that interval, which listener owns the resource, and **precisely which JUnit lifecycle hook** the Spring callback runs before or after.

## 12. Common Mistakes and Fixes

1. **Placing `@TestExecutionListeners` without integrating SpringExtension.** JUnit Jupiter runs tests, but Spring does not orchestrate listeners. **Fix:** use `@SpringJUnitConfig`, `@SpringBootTest`, or proper SpringExtension integration.
2. **Adding a listener and losing default listeners.** Because of `REPLACE_DEFAULTS`, tests lose `@Autowired` or transaction/`@Sql` behavior. **Fix:** use `mergeMode = MERGE_WITH_DEFAULTS` when only adding a listener.
3. **Confusing `beforeTestMethod` with right before `@Test`.** It runs before `@BeforeEach`. **Fix:** time only the test body using `beforeTestExecution`.
4. **Confusing `afterTestMethod` with right after `@Test`.** It runs after `@AfterEach`. **Fix:** use `afterTestExecution` when inspecting before teardown.
5. **Assuming "after" order matches "before" order.** With two listeners A and B, "after" reverses to maintain wrapping. **Fix:** define order explicitly and manage resources like a stack.
6. **Accessing instance or method too early.** `beforeTestClass` does not yet have a test instance or method. **Fix:** use only data available at that phase.
7. **Assuming a listener is a Spring bean.** `@Autowired` on a custom listener does not work automatically as on beans. **Fix:** access `ApplicationContext` via `TestContext` when needed, or choose an event-listener bean.
8. **Sharing mutable static state during parallel runs.** Traces and fixtures from multiple classes/tests can interleave. **Fix:** store state per test or use a thread-safe reporter.
9. **Deleting data before `@AfterEach` completes.** Teardown fails to find expected fixtures. **Fix:** choose `afterTestMethod` or framework-managed cleanup.
10. **Writing a custom listener to replace built-in transaction/SQL/DI listeners.** Easy to get ordering wrong or drop default features. **Fix:** prefer standard listeners and annotations.
11. **Equating `getTestException()` with all test failures.** Setup/teardown can fail separately. **Fix:** understand the timing and scope of exceptions stored by TestContext.
12. **Tests failing due to auxiliary logging/reporting.** A listener throws an exception for a non-critical external task. **Fix:** handle errors proportionally to severity and log clearly.

## 13. Listener Design Workflow and Checklist

A short workflow before writing a custom listener:

1. **Describe what needs to be done:** time the test body, start a transaction, inject beans, log lifecycle, or clean up resources?
2. **Check built-in features:** do `@Transactional`, `@Sql`, `@DirtiesContext`, DI, or event listeners already solve it?
3. **Choose the scope:** class-level, test instance, before setup, right before test, right after test, or after teardown?
4. **Choose the implementation mechanism:** plain JUnit Extension, Spring `TestExecutionListener`, or bean receiving test execution events.
5. **Register safely:** when adding a custom listener, specify `MERGE_WITH_DEFAULTS` and ordering if needed.
6. **Run a verification test:** observe the exact callback order with a simple example, then add failure/parallel tests if the real use case requires them.
7. **Verify cleanup:** resources are closed by their rightful owner, setup failures are handled cleanly, and no state leaks across the suite.

Checklist before finishing:

- [ ] Distinguished Spring's `TestExecutionListener` from JUnit extensions and launcher listeners.
- [ ] Understood all seven callbacks and their exact positions relative to `@BeforeAll` / `@BeforeEach` / `@Test` / `@AfterEach` / `@AfterAll`.
- [ ] `beforeTestExecution` and `afterTestExecution` are used when measuring strictly the test body.
- [ ] `@SpringJUnitConfig` / `@SpringBootTest` or SpringExtension is integrated.
- [ ] Did not inadvertently drop default listeners when adding a custom listener.
- [ ] Relative ordering between important listeners is defined, avoiding accidental order reliance.
- [ ] Did not assume beans/instances/methods exist at every phase.
- [ ] Shared state is isolated or thread-safe when tests run in parallel.
- [ ] Considered transactions, `@Sql`, `@DirtiesContext`, and framework-managed cleanup.
- [ ] Test code and output are explained strictly according to **the events the example actually produces**.

**Key takeaway:** `TestExecutionListener` is how Spring TestContext injects logic into test lifecycle milestones. The two easiest pairs to confuse are **`beforeTestMethod` / `afterTestMethod` wrapping setup + test + teardown**, versus **`beforeTestExecution` / `afterTestExecution` wrapping only the `@Test` body**. To add custom behavior while retaining Spring's dependency injection and default features, prefer `@TestExecutionListeners(mergeMode = MERGE_WITH_DEFAULTS)`.

### References

- [Spring Framework 6.2 — TestContextManager API](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/test/context/TestContextManager.html)
- [Spring Framework — TestExecutionListener configuration](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tel-config.html)
- [Spring Framework 6.2 — TestExecutionListener API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/test/context/TestExecutionListener.html)
- [Spring Framework — Test execution events](https://docs.spring.io/spring/reference/6.2/testing/testcontext-framework/test-execution-events.html)
