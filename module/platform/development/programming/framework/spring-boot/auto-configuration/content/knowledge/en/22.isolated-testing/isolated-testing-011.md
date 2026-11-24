# Closing the Context After Each Run and Keeping Test Cases Independent

> **Goal:** Write auto-configuration tests so each case gets its own Spring context, the context closes immediately after the test completes, and bean-managed resources are released per their lifecycle. At the same time, distinguish context-scoped state from JVM-wide or external system state that can still leak across tests.

This lesson belongs to **Isolated Testing**, using Spring Boot 3.3.x, Java 17+, JUnit Jupiter, and AssertJ. The focus is `ApplicationContextRunner` and test isolation principles when verifying conditions, default beans, properties, classpaths, and resource lifecycles.

## 1. Why close the context after each run?

An `ApplicationContext` holds many objects and resources throughout its lifetime:

- Singleton beans and their mutable state.
- Connection pools, HTTP clients, caches, schedulers, and executors.
- Listeners, callbacks, lifecycle components, and shutdown hooks.
- Beans created during refresh and dependency injection.
- Resources registered by beans to be released on context close.

If a test creates multiple contexts and abandons old ones, resources can persist after assertions complete. An unclosed connection pool can hold connections; an unstopped executor can keep threads alive; an unregistered listener can keep receiving events; temporary files or sockets may remain held.

Spring Boot provides runners to create a small context per test case. With `ApplicationContextRunner`, each call to `run(...)` creates and refreshes a new context, passes it into the callback for assertions, and then automatically closes it once the callback finishes.

Lifecycle flow:

~~~text
ApplicationContextRunner.run(...)
          |
          v
Create new ApplicationContext
          |
          v
Register configurations, beans, and properties
          |
          v
Refresh context
          |
          v
Run callback / assertions
          |
          v
Close ApplicationContext
          |
          v
Invoke bean destroy callbacks
          |
          v
Release context-managed resources
~~~

Closing the context is part of the runner's contract. Tests do not need to call `context.close()` inside a typical callback. Let the runner manage the lifecycle so you do not accidentally close the context while assertions are still using beans.

## 2. ApplicationContextRunner creates a fresh context for each run

`ApplicationContextRunner` is the runner for standard non-web environments. Its default constructor uses `AnnotationConfigApplicationContext` as the underlying context.

A runner is commonly declared as a field on the test class to share base configuration:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(MyServiceAutoConfiguration.class));
~~~

Sharing a runner does not mean tests share a context. The runner stores the configuration to apply; each `run(...)` call creates a fresh context from the current configuration.

Example:

~~~java
contextRunner.run(context -> {
    // First context.
});

contextRunner.run(context -> {
    // Second context, freshly created.
});
~~~

The two callbacks receive two different contexts. A singleton bean in the first context is not reused as the second context's singleton. Once the first callback finishes, the first context closes before `run(...)` returns.

### 2.1. Runners can be reused

Customization methods such as `withPropertyValues`, `withUserConfiguration`, `withBean`, `withClassLoader`, and `withInitializer` return a new runner instance with updated configuration.

Example:

~~~java
contextRunner.withPropertyValues("demo.mode=first").run(context -> {
    // Test the first case.
});

contextRunner.withPropertyValues("demo.mode=second").run(context -> {
    // Test the second case.
});

contextRunner.run(context -> {
    // Reuses the base configuration, without demo.mode added by the two calls above.
});
~~~

Each variant is a separate runner configuration. Do not reassign a variant back onto the base runner unless you want all subsequent tests to receive the altered configuration:

~~~java
// Avoid this approach if tests must remain independent:
contextRunner = contextRunner.withPropertyValues("demo.mode=first");
~~~

Normally declare the runner as `private final`, keep shared setup in the field, and derive variants inside each test. This makes it obvious to readers which properties or configurations belong to a single case.

## 3. When the context is closed

The contract of `AbstractApplicationContextRunner.run(...)` states that the runner creates and refreshes the context, passes it to the consumer, and closes it when the consumer completes.

This has several practical implications:

1. Beans can be used inside the callback to check state, dependencies, and behavior.
2. Once the callback returns, the context is closed; do not keep using or fetching beans from that context.
3. Whether the callback ends with passing assertions or throws an exception, the test must still let the runner manage the context lifecycle.
4. If startup fails, the runner still invokes the callback with a context in the failed state so the test can inspect the cause.
5. Do not retain a reference to the context for use in another test method.

Example of what not to do:

~~~java
AtomicReference<AssertableApplicationContext> saved =
        new AtomicReference<>();

contextRunner.run(context -> saved.set(context));

// Context is already closed after run returns.
// Do not use saved.get() to keep fetching beans or reading Environment.
~~~

Put all necessary assertions inside the callback:

~~~java
contextRunner.run(context -> {
    assertThat(context).hasNotFailed();
    assertThat(context).hasSingleBean(MyService.class);

    MyService service = context.getBean(MyService.class);
    assertThat(service.process("hello")).isEqualTo("HELLO");
});
~~~

### 3.1. prepare(...) vs. run(...)

`prepare(...)` also creates a context and closes it after the callback, but does not refresh the context. It fits cases where you need to inspect or customize pre-refresh state, such as bean definitions or initializers. For testing bean behavior after application startup, use `run(...)`.

### 3.2. Failed context startup

When refresh fails, the runner passes a failed context into the callback. Operations requiring a running context will not work; inspect the cause via `getFailure()` assertions:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(BrokenConfiguration.class)
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context)
                    .getFailure()
                    .hasCauseInstanceOf(IllegalStateException.class);
        });
~~~

Do not just let the test throw a generic error on context startup failure. Asserting the specific cause distinguishes errors from conditions, binding, constructors, or dependencies.

## 4. Spring invokes destroy callbacks on context close

When the context closes, Spring executes lifecycle shutdown for managed singleton beans. Common mechanisms:

- `DisposableBean.destroy()`.
- Methods annotated with `@PreDestroy`.
- Destroy methods declared via `@Bean(destroyMethod = "...")`.
- Lifecycle components such as `Lifecycle` or `SmartLifecycle` stopped per their contract.
- Framework-managed listeners and resource cleanup.

Example bean holding a resource that must close:

~~~java
package example.testing;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.DisposableBean;

public final class LifecycleProbe implements DisposableBean {

    private final AtomicInteger closeCount;

    public LifecycleProbe(AtomicInteger closeCount) {
        this.closeCount = closeCount;
    }

    @Override
    public void destroy() {
        closeCount.incrementAndGet();
    }
}
~~~

If the bean is registered in the context, `destroy()` is called when the context closes. In tests, a counter can confirm the callback ran.

For beans creating executors themselves, declare an explicit destroy method:

~~~java
@Bean(destroyMethod = "shutdown")
ExecutorService backgroundExecutor() {
    return Executors.newFixedThreadPool(2);
}
~~~

For library-provided resources, prefer having beans manage their lifecycle via `AutoCloseable`, `DisposableBean`, `@PreDestroy`, or an appropriate destroy method. Avoid creating resources in static initializers because static resources sit outside the context's lifecycle.

**Note:** Spring only releases resources it knows how to manage. If a test opens sockets, creates temporary directories, or starts servers outside the context, the test itself must close them via `try-with-resources`, `@AfterEach`, or appropriate cleanup APIs.

## 5. Testing that each run gets fresh beans and closes the context

The following example is a complete test class. It proves three things:

1. Each `run(...)` creates a new bean instance.
2. Properties of each variant do not leak onto the base runner.
3. Destroy callbacks execute right after each `run(...)` callback.

**File:** `src/test/java/example/testing/ContextIsolationTests.java`

~~~java
package example.testing;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class ContextIsolationTests {

    private final AtomicInteger destroyedBeans = new AtomicInteger();

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withBean(
                            LifecycleProbe.class,
                            () -> new LifecycleProbe(destroyedBeans));

    @Test
    void eachRunCreatesFreshBeansAndClosesContextAfterCallback() {
        AtomicReference<LifecycleProbe> firstBean = new AtomicReference<>();

        runner.withPropertyValues("demo.case=first").run(context -> {
            assertThat(context).hasNotFailed();

            LifecycleProbe bean = context.getBean(LifecycleProbe.class);
            firstBean.set(bean);

            assertThat(context.getEnvironment().getProperty("demo.case"))
                    .isEqualTo("first");
            assertThat(destroyedBeans).hasValue(0);
        });

        // run() has returned: the first context's destroy callback has executed.
        assertThat(destroyedBeans).hasValue(1);

        runner.withPropertyValues("demo.case=second").run(context -> {
            assertThat(context).hasNotFailed();

            LifecycleProbe secondBean =
                    context.getBean(LifecycleProbe.class);

            assertThat(secondBean).isNotSameAs(firstBean.get());
            assertThat(context.getEnvironment().getProperty("demo.case"))
                    .isEqualTo("second");
            assertThat(destroyedBeans).hasValue(1);
        });

        assertThat(destroyedBeans).hasValue(2);

        // The original runner was not mutated by the two property variants above.
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context.getEnvironment().containsProperty("demo.case"))
                    .isFalse();

            LifecycleProbe thirdBean =
                    context.getBean(LifecycleProbe.class);

            assertThat(thirdBean).isNotSameAs(firstBean.get());
            assertThat(destroyedBeans).hasValue(2);
        });

        assertThat(destroyedBeans).hasValue(3);
    }

    @Test
    void systemPropertyIsRestoredWhenRunCompletes() {
        String original =
                System.getProperty("example.runner.lifecycle.marker");

        runner.withSystemProperties(
                "example.runner.lifecycle.marker=inside")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(System.getProperty(
                            "example.runner.lifecycle.marker"))
                            .isEqualTo("inside");
                });

        assertThat(System.getProperty(
                "example.runner.lifecycle.marker"))
                .isEqualTo(original);
    }

    @Test
    void failedStartupCanBeAssertedInsideCallback() {
        new ApplicationContextRunner()
                .withUserConfiguration(BrokenConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context)
                            .getFailure()
                            .hasCauseInstanceOf(IllegalStateException.class);
                });
    }

    static final class LifecycleProbe implements DisposableBean {

        private final AtomicInteger destroyedBeans;

        LifecycleProbe(AtomicInteger destroyedBeans) {
            this.destroyedBeans = destroyedBeans;
        }

        @Override
        public void destroy() {
            destroyedBeans.incrementAndGet();
        }
    }

    @org.springframework.context.annotation.Configuration(
            proxyBeanMethods = false)
    static class BrokenConfiguration {

        @org.springframework.context.annotation.Bean
        String brokenBean() {
            throw new IllegalStateException("Expected startup failure");
        }
    }
}
~~~

The first test intentionally uses a shared `AtomicInteger` to count destroy callbacks. This is a lifecycle observer, not application state. Each run still receives a distinct `LifecycleProbe`; the counter increments after the callback finishes.

The second test confirms `withSystemProperties` restores the original JVM value when the context closes. The third test illustrates asserting a startup failure inside the callback.

### Expected output

With Spring Boot 3.3.x, JUnit Jupiter, and AssertJ configured on the test classpath:

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This is the expected result when tests pass, not a log generated by this article.

Common dependency:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}
~~~

Run with Maven:

~~~bash
mvn -Dtest=ContextIsolationTests test
~~~

Or Gradle wrapper:

~~~bash
./gradlew test --tests example.testing.ContextIsolationTests
~~~

## 6. Keeping each test case independent

An independent test must fully declare its own conditions. It should never require an earlier test to succeed to prepare state for a later test.

For example, do not design two order-dependent tests:

~~~java
@Test
void firstTestCreatesSharedState() {
    SharedState.currentMode = "enabled";
}

@Test
void secondTestRequiresFirstTest() {
    assertThat(SharedState.currentMode).isEqualTo("enabled");
}
~~~

The second test can fail when run in isolation, when JUnit changes execution order, or when tests run in parallel. Instead, each test sets up its own state:

~~~java
@Test
void enabledModeCreatesService() {
    runner.withPropertyValues("demo.enabled=true").run(context -> {
        assertThat(context).hasSingleBean(MyService.class);
    });
}

@Test
void disabledModeSkipsService() {
    runner.withPropertyValues("demo.enabled=false").run(context -> {
        assertThat(context).doesNotHaveBean(MyService.class);
    });
}
~~~

Principles:

- Each test declares its own required properties, configurations, and user beans.
- Do not depend on execution order between methods.
- Do not use mutable static fields to pass results from one test to another.
- Do not keep beans or contexts from one run to reuse in the next run.
- Use dedicated data per case and clean up data after the test.
- If tests use shared fixtures, fixtures must initialize independently per test class/method lifecycle.
- Assertions must verify behavior of the currently executing case, not rely on log or file outputs left over from a prior run.

### 6.1. A shared runner field does not mean tests share a context

Declaring a runner field is Spring Boot's recommended way to centralize base setup:

~~~java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(MyAutoConfiguration.class));
~~~

Each test calls `runner.with...(...).run(...)` with its own customizations. The runner is reusable configuration; the context is a fresh instance per run.

For readability, name tests after their behavior and scenario:

- `createsDefaultBeanWhenPropertyMissing`
- `backsOffWhenUserBeanExists`
- `skipsConfigurationWhenOptionalClassIsMissing`
- `closesResourceAfterRun`

Names like `test1`, `test2`, or `works` do not communicate the condition and outcome under test.

## 7. Context isolation is not process isolation

Closing an `ApplicationContext` releases beans and resources belonging to that context. However, tests still execute inside the same JVM and can access state outside the context.

Common leak sources:

| State | Reset on context close? | How to keep tests independent |
| --- | --- | --- |
| Context-owned singleton beans | Yes, when the context closes and destroy lifecycle completes | Do not retain references into another run |
| Beans with `DisposableBean` or `@PreDestroy` | Callback runs when bean is managed and context closes | Verify callbacks; avoid creating resources outside bean lifecycle |
| Properties added via `withPropertyValues` | Scoped only to that runner/context's Environment | Derive a separate runner variant per test |
| System properties via `withSystemProperties` | Runner restores values on context close | Use distinct keys; avoid parallel runs on the same key |
| Static fields or static caches | No | Explicitly reset or eliminate mutable global state |
| External databases | No | Use isolated database/schema/tables, transaction rollback, or cleanup |
| Temp files and directories | No if created by test outside context | Use unique directories and delete after the test |
| Self-started HTTP servers or sockets | No unless managed by bean lifecycle | Close servers/sockets in cleanup |
| Bean-managed executors/threads | Only if destroy callback actually stops them | Declare destroy methods and await task termination |
| External test containers or services | No | Use dedicated container/test-fixture lifecycles and cleanup |

A test can close its context properly and still break other tests by leaving behind database rows, temporary files, or system properties. When investigating test flakiness, ask whether the state lives in the context, the JVM, or an external system.

## 8. Environment properties and system properties are two different scopes

Prefer `withPropertyValues` for configuration needed only in the context under test:

~~~java
runner.withPropertyValues(
        "acme.feature.enabled=true",
        "acme.feature.timeout=2s")
        .run(context -> {
            assertThat(context.getEnvironment()
                    .getProperty("acme.feature.enabled"))
                    .isEqualTo("true");
        });
~~~

Properties are added to the context's Environment. They do not need to modify JVM-wide `System.getProperties()`.

Use `withSystemProperties` when code must read real system properties:

~~~java
runner.withSystemProperties("demo.external.mode=test")
        .run(context -> {
            assertThat(System.getProperty("demo.external.mode"))
                    .isEqualTo("test");
        });
~~~

The runner restores system properties when the context closes. However, while the callback is executing, system properties remain JVM-wide state. If two parallel tests modify the same key concurrently, they can observe each other's values. Whenever possible, use Environment properties instead of system properties; if system properties are unavoidable, avoid running tests on the same key in parallel or isolate tests at the process level.

Never call `System.setProperty` directly and forget to restore the old value. If test code must modify a system property manually, use `try/finally` to restore the exact pre-test state.

## 9. Asynchronous resources must stop before the test finishes

An easily missed scenario:

~~~java
runner.run(context -> {
    context.getBean(MyService.class).startBackgroundWork();
    // Callback returns immediately.
});
~~~

When the callback returns, the context closes. If background work is still running and holds references to context beans or resources, it may error out or keep threads alive after the test ends.

How to handle this:

1. Register executors/schedulers as lifecycle-managed beans.
2. When the context closes, stop accepting new tasks.
3. Wait for in-flight tasks to finish within a reasonable timeout.
4. Close related clients, pools, and resources.
5. In tests, await async results before returning from the callback.

Example executor bean with a destroy method:

~~~java
@Configuration(proxyBeanMethods = false)
class AsyncConfiguration {

    @Bean(destroyMethod = "shutdown")
    ExecutorService testExecutor() {
        return Executors.newSingleThreadExecutor();
    }
}
~~~

If you need to verify tasks stopped, tests can use `CountDownLatch`, `Future.get(timeout, unit)`, or equivalent APIs. Always set timeouts so tests do not hang indefinitely if a task fails.

Do not launch background threads in static initializers or constructors of classes not managed by Spring. Those threads are not automatically closed when the context closes.

## 10. Is using @DirtiesContext in SpringBootTest different?

Distinguish `ApplicationContextRunner` from the Spring TestContext Framework.

### With ApplicationContextRunner

Each call to `run(...)` creates a new context and closes it when the callback completes. Therefore, there is no need to add `@DirtiesContext` just to ask the runner to close the context. Self-closing is already built into the runner's contract.

### With @SpringBootTest and the TestContext Framework

The Spring TestContext Framework usually caches and reuses contexts across tests sharing the same configuration. Caching avoids rebooting a large application for every test method.

That means two tests sharing the same configuration can receive the same cached context. If one test corrupts singleton state, alters bean definitions, or leaves the context unusable, you can mark the context dirty:

~~~java
@SpringBootTest
class ApplicationIntegrationTests {

    @Test
    @DirtiesContext
    void testThatCorruptsContextState() {
        // Test intentionally mutates context state.
    }
}
~~~

`@DirtiesContext` marks the context so Spring TestContext evicts it from the cache and closes it; subsequent tests needing that configuration get a new context.

Do not put `@DirtiesContext` on every test merely to wipe data. It slows down the suite by forcing context restarts. For database rows, files, or external services, clean up those resources properly; for the context cache, use `@DirtiesContext` only when a test truly renders the context non-reusable.

## 11. Parent contexts and custom context factories

`ApplicationContextRunner.withParent(...)` lets you test a child context inheriting beans from a parent context. This is intentional, though no longer completely isolated:

- Beans in the child context belong to the child's lifecycle.
- Beans in the parent context are shared dependencies.
- Closing the child does not absolve the test of closing the parent it created and owns.
- If the parent holds a mutable singleton, multiple child runs observe that shared state.

Create the parent fixture explicitly and close it in the lifecycle of the test owning the parent. Do not use a shared parent context if the test's goal is proving every bean is fresh.

If creating a runner with a custom context factory:

~~~java
ApplicationContextRunner runner =
        new ApplicationContextRunner(
                AnnotationConfigApplicationContext::new);
~~~

The supplier must return **a brand-new context instance on every invocation**. Never return the same already-refreshed or closed instance across multiple runs. Reusing a context instance breaks the runner's isolation assumption and can trigger refresh/closed-context errors.

For web tests, pick an appropriate runner such as `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner`. `ApplicationContextRunner` is non-web by default; do not boot an embedded web server just because a test needs some MVC beans.

## 12. Common mistakes and fixes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Destroy callback never runs | Bean is not Spring-managed, never created, or destroy method unrecognized | Register the bean properly and declare lifecycle callbacks |
| Later test sees properties from earlier test | Reassigned base runner or mutated system properties directly | Derive new runner variants and use `withPropertyValues` |
| Test passes alone, fails in full suite | Shared static state, shared files/database, or order dependency | Create isolated fixtures and clean up external state |
| Threads remain alive after test | Executor or scheduler was not stopped | Register lifecycle beans and await shutdown |
| Context closed yet test still uses bean | Bean/context reference leaked out of callback | Perform assertions inside callback, do not use after run |
| Parallel tests flake intermittently | Shared system property, port, file, or database row | Use unique resource identifiers or proper synchronization |
| Context startup fails, assertions throw confusing error | Test fetches beans on a failed context | Use `hasFailed()` and `getFailure()` |
| `@DirtiesContext` slows down suite | Marking context dirty when only data cleanup was needed | Use only when the cached context is genuinely corrupted |
| Parent bean shared unintentionally | Runner shares a parent context | Create separate parents or explicitly test shared-state behavior |

### 12.1. Workflow for investigating non-independent tests

1. Run the failing test in isolation to confirm it can build its own context.
2. Run the entire test class to find dependencies between methods.
3. Run the whole module to detect static state or cross-class shared resources.
4. Check which beans have destroy callbacks and whether they run after each run.
5. Inspect threads, ports, databases, files, and system properties lingering after tests.
6. If using `@SpringBootTest`, inspect the context cache and check whether the test genuinely needs `@DirtiesContext`.
7. Re-run tests repeatedly or enable controlled parallel execution to expose resource collisions.

Do not mask flakiness by forcing test execution order before identifying which state is being shared. Ordering only hides the symptom; it does not release resources.

## 13. Checklist for every test using ApplicationContextRunner

- [ ] Base runner is declared `private final`.
- [ ] Each case uses its own `run(...)` call.
- [ ] Properties and user configurations are added via local runner variants.
- [ ] Assertions and bean usage happen inside the callback.
- [ ] No contexts or beans are saved for use after the callback ends.
- [ ] Resource-managing beans have explicit destroy callbacks.
- [ ] Background threads/executors are stopped and tasks awaited.
- [ ] System properties are restored; avoid parallel tests mutating the same key.
- [ ] External databases, files, sockets, and containers have dedicated cleanup.
- [ ] Tests remain order-independent whether run standalone or in a suite.
- [ ] Startup failures are checked via `hasFailed()` and `getFailure()`.
- [ ] `@DirtiesContext` is used only when a test makes the cached context non-reusable.

## 14. Self-check questions

1. Does each call to `ApplicationContextRunner.run(...)` reuse the previous context?  
   **Answer:** No. The runner creates and refreshes a new context for the callback, then closes it when the callback completes.

2. Why can a runner field be shared across multiple tests?  
   **Answer:** The runner holds configuration; `with...` methods return a new runner, and each `run(...)` creates a separate context.

3. When is `DisposableBean.destroy()` called?  
   **Answer:** When a Spring-managed bean is destroyed during context shutdown.

4. Does closing the context automatically clear static fields or database rows?  
   **Answer:** No. Static state and external data require separate cleanup.

5. How does `withPropertyValues` differ from `withSystemProperties`?  
   **Answer:** One adds properties to the context's Environment; the other changes JVM-wide system properties during the run and restores them on context close.

6. Should you call `context.close()` inside a typical callback?  
   **Answer:** No need. The runner closes the context after the callback; closing early can prevent subsequent assertions from using the context.

7. Is `@DirtiesContext` needed for every ApplicationContextRunner test?  
   **Answer:** No. The runner already closes the context after each run; `@DirtiesContext` is for contexts cached by Spring TestContext when a test renders that context non-reusable.

8. Why can tests still depend on execution order even though each run creates a fresh context?  
   **Answer:** Because state can live outside the context: static fields, system properties, files, databases, ports, or background threads.

9. When a callback returns while an async task is still running, what can happen?  
   **Answer:** The context closes while the task still uses beans/resources, causing errors or leaked threads. Tests must await task completion before the callback exits.

## Official documentation

- [Spring Boot 3.3 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): non-web contexts and default context factory.
- [Spring Boot 3.3 — AbstractApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html): `run`, `prepare`, `withPropertyValues`, `withSystemProperties`, `withBean`, and runner customizations.
- [Spring Boot 3.3 — Testing Your Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): using ApplicationContextRunner to test combinations of user configuration, Environment, and conditions.
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): how the TestContext Framework caches, reuses, and closes contexts.
- [Spring Framework — @DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html): when a context is marked dirty, evicted from cache, and recreated.

**Takeaway:** `ApplicationContextRunner` guarantees a fresh context for each `run(...)` call and closes it automatically after the callback. That releases context-owned beans and resources, but does not clear JVM-wide state or external data. To keep tests truly independent, each case must configure itself, assert itself, manage resource lifecycles, and clean up any state residing outside the context.
