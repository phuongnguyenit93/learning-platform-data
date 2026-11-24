# Isolating Contexts, Threads, and Hooks So Test Runs Do Not Affect Each Other

A Spring Boot test can **PASS when run alone** yet **FAIL when running the entire suite**, or cause `gradle test` to hang after all assertions finish. The cause usually lies in resource lifecycles rather than business logic: `ApplicationContext` is cached and reused by Spring TestContext; executors/threads remain alive; `Runtime.addShutdownHook` leaves callbacks until JVM exit; `ThreadLocal`, static state, or system properties persist across tests; and files, ports, and test data outside the JVM remain uncleaned.

This Knowledge article belongs to module **Spring Boot Application Runtime**, parent section **Lifecycle Testing**, topic **"Isolating contexts, threads, and hooks so test runs do not affect each other"**. Examples apply to **Spring Boot 3.3.x, Spring Framework 6.1, Java 17+, and JUnit 5**. The focus is **resource ownership, cleanup timing, and verification**, rather than disabling the context cache everywhere or running every test in a separate JVM unnecessarily.

After this lesson, you should be able to:

- Distinguish **Spring context**, **JVM/process**, and **out-of-JVM resources**; each scope requires different cleanup.
- Understand why `@SpringBootTest` can share a context across multiple tests and when `@DirtiesContext` is needed.
- Use `ApplicationContextRunner` or `try-with-resources` to create contexts closed immediately after each run.
- Design worker-managing beans with destroy methods, interrupts, and bounded `awaitTermination`.
- Avoid testing `System.exit` or JVM hooks directly inside the JUnit process; use subprocesses with timeouts.
- Restore system properties, static caches, and `ThreadLocal`, and isolate ports/files/DBs/queues.
- Run tests in different orders and on CI to confirm zero cross-run interference.

## 1. Three resource scopes that are not interchangeable

| Scope | Examples | Primary cleanup mechanism |
| --- | --- | --- |
| **Spring ApplicationContext** | Singleton beans, `@PreDestroy`, `SmartLifecycle`, bean-managed schedulers/executors | `context.close()`, `@DirtiesContext`, Spring TestContext, or context runner |
| **JVM/process** | `Runtime.addShutdownHook`, `System.setProperty`, static mutable state, unmanaged threads | Restore in test/`finally` or controlled JVM exit |
| **Out-of-JVM** | Databases, Testcontainers, temp files, ports, message brokers, mock servers | Test fixtures, unique namespaces, transactions/cleanup, and process management |

Never rely on the following false equivalences:

~~~text
context.close()  !=  JVM shutdown
@DirtiesContext  !=  reset all static Java fields
@PreDestroy      !=  auto-close every ExecutorService outside Spring
System.exit(0)   !=  stop only one test method
Thread.interrupt !=  guaranteed worker exited
~~~

**Principle:** every object must have a clear **owner**. If a Spring bean creates an executor, the lifecycle bean is responsible for closing it. If a test creates an executor itself, the test must close it. If a test registers a JVM hook, the test must remove the hook before finishing or isolate the entire experiment in a child JVM.

### A common interference timeline

~~~text
JUnit worker JVM starts
  |
  +-- Test A creates context A
  |      +-- Bean Counter state = 1
  |      +-- Thread pool not shut down
  |      +-- Hook A registered on Runtime
  |
  +-- Test A PASS
  |
  +-- Test B reuses context A from cache
  |      +-- Counter still = 1 -> Test B FAIL
  |
  +-- Test C starts server on port held by old thread -> FAIL
  |
  +-- End of suite: JVM shutdown -> Hook A finally runs
         +-- Hook references expired file/bean -> error or hang
~~~

Each root cause can be fixed by **blocking shared mutable state**, rather than adding random timeouts or sleeps.

## 2. Spring TestContext cache: why can two tests share the same context?

Spring Framework TestContext holds created `ApplicationContext`s in a **static cache inside the test worker JVM**. A new test with the **same context configuration key** can receive the existing context to save the cost of component scanning, auto-configuration, and singleton initialization.

The cache key may factor in configuration classes/locations, context initializers/customizers, profiles, property sources, context hierarchy, mock/bean overrides, and other customizations. Therefore:

- Not every `@SpringBootTest` uses the same context.
- Not every JUnit class gets a new context.
- Tests with equivalent configuration can receive the **same singleton beans**, even across different classes.
- A test normally finishes only its **method**, while the context stays in the cache.
- Contexts may close when marked dirty, on cache eviction, or when the test suite JVM shuts down.

Caching is beneficial. The problem is **dirty state that tests fail to restore**, for example:

~~~java
@Service
class MutableCounter {
    private int count;

    int increment() {
        return ++count;
    }

    int current() {
        return count;
    }
}
~~~

This is an illustrative class requiring importing `@Service`. If two tests share the same singleton and the first increments `count`, the second cannot be sure the initial value is `0`. Solutions include making state immutable, resetting state in a controlled manner, or marking the context dirty.

### Cache is not an isolated JVM

If the build tool runs each test group in a different JVM, the cache is not shared across the two processes. However, **databases, files, network ports, and queues** can still be shared across JVMs. Isolating the TestContext cache solves only **one** scope.

To investigate, enable cache logging in test config:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

The purpose is inspecting cache hits/misses and context closing activity; never treat cache hit counts as proof that all threads or external state were cleaned up.

## 3. `@DirtiesContext`: closing the context at the right time

`org.springframework.test.annotation.DirtiesContext` tells Spring TestContext to treat the context as modified, **evict it from cache, and close it** at the specified point.

Modes:

| Usage | Timing |
| --- | --- |
| `@DirtiesContext` on method | After method, default `AFTER_METHOD` |
| `methodMode = BEFORE_METHOD` | Before method |
| `classMode = BEFORE_CLASS` | Before entire class |
| `classMode = AFTER_CLASS` | After entire class, class default |
| `classMode = BEFORE_EACH_TEST_METHOD` | Before each method |
| `classMode = AFTER_EACH_TEST_METHOD` | After each method |

Example:

~~~java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class TestThatMutatesSingletonState {
    // ... @Test methods ...
}
~~~

This is a fragment requiring imports for `@SpringBootTest`/`@DirtiesContext` and test methods. It prevents **reusing the dirtied context after the class**. Yet it does not guarantee the context is **fresh right before the class**, because a context with the same key could already be cached from an earlier test.

If you genuinely require a fresh context at the start:

~~~java
@DirtiesContext(classMode = DirtiesContext.ClassMode.BEFORE_CLASS)
~~~

To close after a specific test:

~~~java
@Test
@DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
void mutatingTest() {
    // ...
}
~~~

**Do not scatter `@DirtiesContext` indiscriminately** across the entire suite. It forces contexts that could be safely reused to be rebuilt, slows tests down, and masks shared-state design flaws instead of fixing them.

### When should it be used?

- Tests that alter configuration or singleton state that is hard to restore safely.
- Tests intentionally measuring context startup/shutdown lifecycles managed by TestContext.
- Tests for JMX, stateful infrastructure, or context configurations mutated after initialization.
- Tests requiring context isolation before/after a specific scenario.

### When is it insufficient?

- Tests calling `System.setProperty` and forgetting to restore.
- Tests spawning `new Thread`/`Executors` outside beans.
- Tests registering `Runtime.addShutdownHook`.
- Tests creating files, database records, broker messages, or local ports outside the context.
- Tests using `ThreadLocal` on executor workers without clearing.

**`@DirtiesContext` only controls the Spring context**; it does not reset the entire JVM.

## 4. `@SpringBootTest`: context owned by TestContext

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class MyIntegrationTest {
    // @Autowired beans ...
}
~~~

The Spring test framework decides when to load, cache, and close the context. **Never call `context.close()` arbitrarily** on an `@Autowired ConfigurableApplicationContext` from `@SpringBootTest`: the next test could receive a reference to an already-closed context if the cache was not updated properly.

To test closing the context yourself, use `ApplicationContextRunner` or instantiate `AnnotationConfigApplicationContext` inside `try-with-resources`. To tell the framework a shared context should not be reused, use `@DirtiesContext`.

For web integration tests:

| `webEnvironment` | Real embedded web server? | Scenario |
| --- | --- | --- |
| `MOCK` | No | MVC/mock web tests |
| `NONE` | No | Bean/lifecycle tests without HTTP |
| `RANDOM_PORT` | Yes, dynamic port | HTTP end-to-end, reduces port conflicts |
| `DEFINED_PORT` | Yes, fixed/configured port | Only when fixed port must be tested |

When running suites in parallel, `DEFINED_PORT` easily collides with ports of other tests, local processes, or running services. For real HTTP tests, prefer `RANDOM_PORT` and read the assigned port instead of hardcoding `8080`.

### Transaction rollback does not guarantee isolation across server threads

A `@Transactional` test can roll back the test thread's transaction. However, when using `RANDOM_PORT`, the HTTP client and server run on **different threads**, so server transactions can commit independently. Thus, cleaning up data created by HTTP requests requires appropriate test fixtures or cleanup rather than relying solely on the JUnit caller's rollback.

## 5. Does closing the context stop every thread?

On the normal closing path of `AbstractApplicationContext`, Spring typically performs:

~~~text
context.close()
  -> ContextClosedEvent
  -> LifecycleProcessor.onClose()
       -> Lifecycle/SmartLifecycle.stop(...)
  -> destroy singleton beans
       -> @PreDestroy
       -> DisposableBean.destroy()
       -> @Bean(destroyMethod=...)
  -> context inactive
~~~

These steps manage **beans and lifecycle contracts**. If the app creates an `ExecutorService` in a field outside Spring or a task runs on an unmanaged thread, the context does not automatically know to shut down that resource.

Example bean:

~~~java
@Bean(destroyMethod = "shutdown")
ExecutorService reportExecutor() {
    return Executors.newSingleThreadExecutor();
}
~~~

This is a fragment inside a configuration class, requiring imports for `@Bean`, `ExecutorService`, and `Executors`. Spring calls `shutdown` when destroying the bean, yet **`shutdown()` does not mean all tasks have finished**. A test needing to ensure cleanup before the next method runs should enforce a bounded await and tasks that cooperate with cancellation.

With `SmartLifecycle.stop(Runnable callback)`, the callback must be invoked **when stopping genuinely completes**. Forgetting the callback can cause the lifecycle processor to wait for the timeout. Never place an infinite wait loop inside `@PreDestroy` or a stop callback.

## 6. Threads and executors: tests must verify real stopping

Bad example (for reading only, **do not run**):

~~~java
@Test
void badTest() {
    ExecutorService pool = Executors.newSingleThreadExecutor();
    pool.submit(() -> {
        while (true) {
            // Non-daemon worker runs forever, no cancellation.
        }
    });
    // Test PASSES yet pool remains alive.
}
~~~

This bug can hang `gradle test` because the JVM still has a non-daemon thread.

Better pattern when the test **owns the executor**:

~~~java
ExecutorService pool = Executors.newSingleThreadExecutor();
try {
    Future<String> result = pool.submit(() -> "OK");
    assertEquals("OK", result.get(2, TimeUnit.SECONDS));
} finally {
    pool.shutdownNow();
    assertTrue(pool.awaitTermination(2, TimeUnit.SECONDS));
}
~~~

This is a fragment inside a method with `throws Exception` and appropriate imports. `shutdownNow()` primarily sends interrupts; **it cannot force a task ignoring interrupts to stop**. Write workers that honor cancellation/interrupts, then assert termination.

### `CountDownLatch` is better than `Thread.sleep` for synchronization

Do not assume:

~~~java
worker.start();
Thread.sleep(100);
assertTrue(worker.isReady());
~~~

because 100 ms may be insufficient on heavily loaded CI. Use `CountDownLatch.await(timeout)`, `Future.get(timeout)`, or an explicit completion signal. A timeout is a deadline allowing the test to fail, **not a trick to make threads run faster**.

## 7. Hooks are JVM-level, not context-level

~~~java
Thread hook = new Thread(
        () -> System.out.println("JVM shutting down"),
        "my-shutdown-hook");
Runtime.getRuntime().addShutdownHook(hook);
~~~

`Runtime.addShutdownHook` registers a thread for the JVM to run on normal shutdown. Hooks can run **concurrently with no guaranteed order**. Finishing a test, dirtying a context, or calling `@PreDestroy` **does not trigger JVM shutdown hooks automatically**.

If Test A registers a hook and forgets to remove it, the hook may sit dormant until the end of the suite, then run and try to access deleted files or destroyed beans.

If a test must create a temporary hook:

~~~java
Runtime runtime = Runtime.getRuntime();
Thread hook = new Thread(() -> {
    // Register temporarily to test API.
}, "temporary-hook");

runtime.addShutdownHook(hook);
try {
    // Test registration; do not call System.exit here.
} finally {
    boolean removed = runtime.removeShutdownHook(hook);
    if (!removed) {
        throw new IllegalStateException("Hook registration missing");
    }
}
~~~

This is a fragment. `removeShutdownHook` is valid only **before the JVM begins shutting down**. Removing a hook does not run its callback. Never test callback logic by calling `hook.run()` and concluding the shutdown lifecycle was truly tested: that is merely a method call on the caller thread.

### `System.exit` and `Runtime.halt`

- `System.exit(code)` requests **the entire JVM** to shut down and runs hooks normally.
- `Runtime.getRuntime().halt(code)` terminates the JVM forcibly, skipping hooks.
- Neither is **safe to call directly inside the JUnit worker JVM** merely to test a hook.

**Running a subprocess with a timeout** is the proper isolation method when testing process-level shutdown.

## 8. Spring Boot hooks and TestContext cache: two different mechanisms

`SpringApplication` has `setRegisterShutdownHook(boolean)`, **defaulting to `true`**. Standalone Spring Boot applications normally rely on this hook to close the context during normal JVM shutdown.

Conversely, `@SpringBootTest` uses the Spring TestContext Framework to manage test contexts and caching. Contexts may close due to `@DirtiesContext`, cache eviction, or test suite shutdown. **Never equate `SpringApplication`'s shutdown hook with TestContext's cache lifecycle**.

Decision table:

| Case | Owner | How to clean up |
| --- | --- | --- |
| `@SpringBootTest` context | Spring TestContext | `@DirtiesContext` as needed; do not call `close()` yourself |
| `ApplicationContextRunner` context | Runner | Closes after callback |
| `new AnnotationConfigApplicationContext(...)` | Test caller | `try-with-resources` |
| `SpringApplication.run` in standalone app | App/Boot | Explicit `close()` or shutdown hook on JVM exit |
| `Runtime.addShutdownHook` registered by test | JVM/test code | Remove before test finishes |
| Testing `System.exit`/Boot shutdown hook | Subprocess | Wait, read exit/marker, kill child on timeout |

Disable `SpringApplication.setRegisterShutdownHook(false)` in a test program owning its own context only with good reason and **ensure the context is closed by other code**. Disabling the hook does not stop leaked threads and can lose cleanup at JVM shutdown.

## 9. Choosing the right isolation level

| Test style | Isolation / benefit | Cost |
| --- | --- | --- |
| Pure Java unit test | No context; instantiates only the target object | Low |
| `ApplicationContextRunner` | Small context, fresh per `run`, closed after callback | Low–medium |
| Self-managed `AnnotationConfigApplicationContext` | Direct control over Framework context start/stop | Low–medium |
| Cached `@SpringBootTest` | Close to real Boot app, fast reuse | Medium–high |
| `@SpringBootTest` + `@DirtiesContext` | Context evicted from cache/closed | Higher |
| JVM subprocess | Real JVM hooks, `System.exit`, signals, and process status | Highest |

**Do not run every unit test in a separate JVM** unnecessarily. Yet never force a `System.exit` test to be in-process merely to save time.

## 10. Runnable project: Spring Boot 3.3 / Java 17 / Gradle

We build an example covering all three scopes:

- `WorkerConfig` creates the `TrackedWorker` bean with a destroy method.
- `TrackedWorker` uses a **non-daemon thread** and stops via interrupt/await.
- `WorkerIsolationTest` uses `ApplicationContextRunner`, verifying context close and worker exit across runs.
- `BootLifecycleTest` demonstrates TestContext caching with before/after dirty modes.
- `HookChild` registers a JVM hook and calls `System.exit(23)`, **but only inside a child JVM**.
- `HookProcessTest` uses `ProcessBuilder` to verify exit code/marker, timeout, and cleanup.

### 10.1. Structure

~~~text
lifecycle-isolation-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/lifecycle/
    │   ├── LifecycleIsolationApplication.java
    │   ├── WorkerConfig.java
    │   ├── TrackedWorker.java
    │   └── HookChild.java
    └── test/java/com/example/lifecycle/
        ├── WorkerIsolationTest.java
        ├── BootLifecycleTest.java
        └── HookProcessTest.java
~~~

### 10.2. `settings.gradle`

~~~groovy
rootProject.name = 'lifecycle-isolation-demo'
~~~

### 10.3. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    // Use Gradle native BOM instead of leaving dependency version blank.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

With Spring Boot 3.3 and Java 17+, a compatible Gradle version is required. Starter dependencies do not get versions automatically without dependency management; the example declares the **BOM** for both `implementation` and `testImplementation`.

### 10.4. `LifecycleIsolationApplication.java`

~~~java
package com.example.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifecycleIsolationApplication {

    public static void main(String[] args) {
        SpringApplication.run(LifecycleIsolationApplication.class, args);
    }
}
~~~

The main class does not call `System.exit` itself. It can run Spring Boot standalone; the worker bean is scanned from `WorkerConfig` in the same package and managed by the context.

### 10.5. `WorkerConfig.java`

~~~java
package com.example.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class WorkerConfig {

    @Bean(destroyMethod = "close")
    TrackedWorker trackedWorker() {
        return new TrackedWorker();
    }
}
~~~

`@Bean(destroyMethod = "close")` binds `TrackedWorker` cleanup to the singleton bean lifecycle. When tests call `ApplicationContextRunner.run(...)` and the callback ends, the context closes and calls `close()`.

### 10.6. `TrackedWorker.java`

~~~java
package com.example.lifecycle;

import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class TrackedWorker implements AutoCloseable {

    private final String id = UUID.randomUUID().toString();
    private final CountDownLatch started = new CountDownLatch(1);
    private final CountDownLatch finished = new CountDownLatch(1);
    private final AtomicBoolean closed = new AtomicBoolean();
    private final ExecutorService executor;

    public TrackedWorker() {
        executor = Executors.newSingleThreadExecutor(task -> {
            Thread thread = new Thread(task, "tracked-worker-" + id);
            thread.setDaemon(false);
            return thread;
        });

        executor.execute(() -> {
            started.countDown();
            try {
                while (!Thread.currentThread().isInterrupted()) {
                    Thread.sleep(50);
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                finished.countDown();
            }
        });
    }

    public String id() {
        return id;
    }

    // Does not throw checked exception; ContextRunner callback
    // can call this method without catching InterruptedException.
    public boolean awaitStarted(long timeout, TimeUnit unit) {
        try {
            return started.await(timeout, unit);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted while waiting for worker startup", ex);
        }
    }

    public boolean isClosed() {
        return closed.get();
    }

    public boolean isFinished() {
        return finished.getCount() == 0;
    }

    @Override
    public void close() {
        executor.shutdownNow();
        try {
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Worker executor did not terminate");
            }
            closed.set(true);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted while stopping worker", ex);
        }
    }
}
~~~

**Key checkpoints:**

1. The worker is a **non-daemon** thread so forgetting shutdown visibly exposes the bug.
2. `started` signals the worker actually ran; never use sleep to guess timing.
3. `shutdownNow` requests an interrupt; the task handles `InterruptedException` and exits.
4. `awaitTermination(2, SECONDS)` sets a deadline instead of waiting forever.
5. `finished` counts down when the task exits, inside `finally`.
6. `closed` turns `true` only after the executor terminates, preventing false positives.
7. `id` confirms two fresh contexts have two distinct beans.

This is a **demo**, not a full production worker implementation. Real tasks must consider queues, backpressure, external resources, premature task creation in constructors, and cleanup if bean creation fails midway.

### 10.7. `WorkerIsolationTest.java`

~~~java
package com.example.lifecycle;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class WorkerIsolationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(WorkerConfig.class);

    @Test
    void contextCloseStopsItsOwnWorker() {
        AtomicReference<TrackedWorker> ref = new AtomicReference<>();

        runner.run(context -> {
            TrackedWorker worker = context.getBean(TrackedWorker.class);
            assertThat(worker.awaitStarted(2, TimeUnit.SECONDS)).isTrue();
            assertThat(worker.isClosed()).isFalse();
            ref.set(worker);
        });

        // ContextRunner already closed the context after the callback finished.
        TrackedWorker worker = ref.get();
        assertThat(worker).isNotNull();
        assertThat(worker.isClosed()).isTrue();
        assertThat(worker.isFinished()).isTrue();
    }

    @Test
    void repeatedRunsDoNotShareBean() {
        AtomicReference<TrackedWorker> first = new AtomicReference<>();
        AtomicReference<TrackedWorker> second = new AtomicReference<>();

        runner.run(context -> {
            TrackedWorker worker = context.getBean(TrackedWorker.class);
            assertThat(worker.awaitStarted(2, TimeUnit.SECONDS)).isTrue();
            first.set(worker);
        });

        runner.run(context -> {
            TrackedWorker worker = context.getBean(TrackedWorker.class);
            assertThat(worker.awaitStarted(2, TimeUnit.SECONDS)).isTrue();
            second.set(worker);
        });

        assertThat(first.get()).isNotNull();
        assertThat(second.get()).isNotNull();
        assertThat(first.get()).isNotSameAs(second.get());
        assertThat(first.get().id()).isNotEqualTo(second.get().id());
        assertThat(first.get().isClosed()).isTrue();
        assertThat(second.get().isClosed()).isTrue();
        assertThat(first.get().isFinished()).isTrue();
        assertThat(second.get().isFinished()).isTrue();
    }
}
~~~

**Why check `isClosed` outside the callback?** Because inside the callback, the context is still open. When `runner.run(...)` returns, the context has been closed and `@Bean(destroyMethod="close")` has had a chance to run. This is a direct lifecycle check rather than relying on `@PreDestroy` logs.

`ApplicationContextRunner` creates a fresh context per `run`, without needing `@DirtiesContext` to force the context cache. Tests do not leave running executors behind after the context ends.

### 10.8. `BootLifecycleTest.java`

~~~java
package com.example.lifecycle;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = LifecycleIsolationApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@DirtiesContext(classMode = DirtiesContext.ClassMode.BEFORE_CLASS)
class BootLifecycleTest {

    @Autowired
    TrackedWorker worker;

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void bootContextStartsManagedWorker() {
        assertThat(worker.awaitStarted(2, TimeUnit.SECONDS)).isTrue();
        assertThat(worker.isClosed()).isFalse();
    }
}
~~~

Explanation:

- `BEFORE_CLASS` evicts a context with the same configuration that might have been cached from a previous class.
- `AFTER_METHOD` causes Spring TestContext to mark the context dirty and close it after the method.
- The test **must not call `context.close()` itself** when TestContext owns it.
- When you want to assert cleanup after the context has closed, the `ApplicationContextRunner` test above is more suitable because it has a clear callback scope.

Do not force the dirty before/after pattern on every ordinary test. This pattern is specifically for **testing the lifecycle**, whereas state-reading tests should leverage the TestContext cache when safe.

### 10.9. `HookChild.java` — Java child process allowed to call `System.exit`

~~~java
package com.example.lifecycle;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class HookChild {

    private HookChild() {
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected marker path");
        }

        Path marker = Path.of(args[0]);

        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> {
                    try {
                        Files.writeString(
                                marker,
                                "HOOK_CALLED\n",
                                StandardCharsets.UTF_8,
                                StandardOpenOption.CREATE,
                                StandardOpenOption.TRUNCATE_EXISTING);
                    } catch (IOException ex) {
                        ex.printStackTrace(System.err);
                    }
                }, "hook-child-writer"));

        System.exit(23);
    }
}
~~~

`HookChild` has no Spring dependency and uses standard Java 17 APIs. Its job is to **demonstrate how to test a real JVM hook in an isolated JVM**. The marker file is written only when the hook executes; never pre-write expected content before starting the child.

### 10.10. `HookProcessTest.java` — with timeout and process cleanup

~~~java
package com.example.lifecycle;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

class HookProcessTest {

    @Test
    void childJvmRunsHookAndParentTestSurvives() throws Exception {
        Path marker = Files.createTempFile("hook-child-", ".txt");
        Process child = null;

        try {
            Files.deleteIfExists(marker);

            boolean windows = System.getProperty("os.name")
                    .toLowerCase().contains("win");

            Path javaBin = Path.of(
                    System.getProperty("java.home"),
                    "bin", windows ? "java.exe" : "java");

            // Standard Gradle Java test: class resides in
            // the main source set output directory.
            Path classes = Path.of(
                    HookChild.class.getProtectionDomain()
                            .getCodeSource().getLocation().toURI());

            child = new ProcessBuilder(
                    javaBin.toString(),
                    "-cp", classes.toString(),
                    HookChild.class.getName(),
                    marker.toString())
                    .redirectErrorStream(true)
                    .redirectOutput(ProcessBuilder.Redirect.DISCARD)
                    .start();

            if (!child.waitFor(15, TimeUnit.SECONDS)) {
                child.destroyForcibly();
                child.waitFor(3, TimeUnit.SECONDS);
                fail("Child JVM exceeded 15-second deadline");
            }

            assertEquals(23, child.exitValue());
            assertTrue(Files.exists(marker));
            assertEquals(
                    "HOOK_CALLED\n",
                    Files.readString(marker, StandardCharsets.UTF_8));
        } finally {
            if (child != null && child.isAlive()) {
                child.destroyForcibly();
                child.waitFor(3, TimeUnit.SECONDS);
            }
            Files.deleteIfExists(marker);
        }
    }
}
~~~

Isolation mechanism breakdown:

- The child uses `java` inside the test JVM's `java.home`.
- `HookChild` needs no Boot libraries, so the main output classpath is sufficient in a standard Gradle build. Custom classloaders or shaded JARs require adjustment.
- Each test run creates **a separate marker path**, avoiding collisions between runs or parallel tests.
- `waitFor(15, SECONDS)` sets a limit. If the child hangs, the parent attempts to kill it so the suite can still fail with clear diagnostics.
- `redirectOutput(DISCARD)` prevents the child from filling an unread stdout pipe.
- Asserts both **exit status `23`** and **file content `HOOK_CALLED`**; a clean exit alone does not prove the hook ran.
- `finally` cleans up the file and child process even if an assertion throws an exception.

**Do not call `HookChild.main(...)` directly inside a test method**. It contains `System.exit(23)` and will terminate the very JVM running JUnit.

**Scope:** this test checks *JDK shutdown hook isolation*; it does not claim to have tested Boot's `SpringApplicationShutdownHook`. To test the real Boot hook, run an executable Spring Boot JAR in a subprocess and observe a marker from `@PreDestroy` or `SmartLifecycle.stop`, with an equivalent timeout and cleanup mechanism.

### 10.11. How to run

From the project directory if a compatible Gradle Wrapper is present:

~~~bash
./gradlew clean test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
~~~

If a suitable Gradle is already installed without a wrapper:

~~~bash
gradle clean test
~~~

The expected result when tests succeed is Gradle reporting **BUILD SUCCESSFUL**. That is the build expectation, not line-for-line exact stdout logs because of version, daemon, or logging differences. There are **four tests** across three classes: two in `WorkerIsolationTest`, one in `BootLifecycleTest`, and one in `HookProcessTest`.

**The code snippets have been reviewed against the APIs**, but actual results must be verified on JDK 17/Gradle and the project's CI environment. An environment that restricts subprocesses or file creation may cause `HookProcessTest` to fail and require infrastructure adjustment rather than silently skipping hook verification.

## 11. When using only Spring Framework core: `AnnotationConfigApplicationContext`

Another approach:

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(WorkerConfig.class)) {

    TrackedWorker worker = context.getBean(TrackedWorker.class);
    if (!worker.awaitStarted(2, TimeUnit.SECONDS)) {
        throw new AssertionError("Worker did not start");
    }
}
// When leaving the block, context.close() has already been called.
~~~

This is a **fragment** inside a test that imports `AnnotationConfigApplicationContext` and `TimeUnit`, along with the example project's classes. No Spring Boot TestContext cache is involved; the test owns the context itself.

Different purposes:

- `ApplicationContextRunner` is convenient for testing multiple bean/configuration variants, with automatic cleanup per `run`.
- `AnnotationConfigApplicationContext` lets the test control the lifecycle directly.
- `@SpringBootTest` is appropriate when real **Boot bootstrap/auto-configuration** is needed and cache reuse is beneficial.
- `ProcessBuilder` is necessary when testing **JVM-level hooks/exit**, not just the context.

## 12. System properties and static state must be restored

A test containing:

~~~java
System.setProperty("feature.mode", "test");
~~~

mutates state **for the entire JVM**. `@DirtiesContext` does not reset this value. Subsequent tests may read the wrong configuration.

Safe pattern:

~~~java
String key = "feature.mode";
String oldValue = System.getProperty(key);

try {
    System.setProperty(key, "test");
    // Run assertions requiring the temporary property.
} finally {
    if (oldValue == null) {
        System.clearProperty(key);
    } else {
        System.setProperty(key, oldValue);
    }
}
~~~

If JUnit runs in parallel, another test may read or write the property before this test restores it. When global mutation is unavoidable, use `@ResourceLock` with the **same resource name** on all related tests, or better yet, **avoid modifying System properties** by passing test properties into an isolated context instead.

Fragment example:

~~~java
@ResourceLock("GLOBAL_FEATURE_MODE")
@Test
void modifiesGlobalState() {
    // Read/write System property with try/finally restore.
}
~~~

Requires importing `org.junit.jupiter.api.parallel.ResourceLock`. A test using a lock that other tests do not use **does not create JVM-wide mutual exclusion**.

Commonly overlooked states: `Locale.setDefault`, `TimeZone.setDefault`, static maps/caches, `System.setOut`, system properties, security context, thread-local correlation IDs, and mock static instrumentation.

## 13. `ThreadLocal`, MDC, and SecurityContext on worker threads

`ThreadLocal` is stored on the **thread performing the work**. Clearing a `ThreadLocal` on the JUnit caller thread does not automatically clear data retained on an executor worker.

Correct example with a task running on a worker:

~~~java
private static final ThreadLocal<String> TENANT = new ThreadLocal<>();

// When submitting:
executor.submit(() -> {
    try {
        TENANT.set("tenant-test");
        doWork();
    } finally {
        TENANT.remove();
    }
}).get(2, TimeUnit.SECONDS);
~~~

This is a fragment inside a class with field `TENANT`, an executor, and method `doWork`. `finally` executes on the worker thread itself when the task finishes.

With Spring Security/MDC, inspect the corresponding propagation and context-clearing mechanisms. Do not assume `@Async` automatically transfers transaction context or security context across every thread boundary. If a task keeps running after the test ends, it can create data or write logs affecting other tests.

## 14. `@Scheduled`, `@Async`, listeners, and queue consumers

| Component | Common interference | Safeguard |
| --- | --- | --- |
| `@Scheduled` | Runs spontaneously while another test checks the DB | Use a narrow test configuration; check scheduler lifecycle |
| `@Async` | Future not finished yet, state unstable | Wait on `CompletableFuture`/`Future` with a deadline |
| `ApplicationListener` | Callback spawns workers or emits late events | Manage resources in beans and verify cleanup |
| Kafka/Rabbit/JMS | Consumer A reads messages from test B | Separate queues/topics/test IDs and explicitly stop containers |
| Mock HTTP server | Fixed port occupied | Dynamic port, stop server after test |
| DB/Redis cache | Data from a previous run remains | Transactions/fixtures/namespaces and cleanup |
| Testcontainers | Container lives across multiple classes or statically | Clarify container ownership and clean up accurately |

Do not invent a "disable-all-scheduling" property and assume it turns off every `@Scheduled`; check whether the application uses `@EnableScheduling`, which scheduler beans exist, and the real configuration conditions.

When only testing bean lifecycle, **do not load the full application with schedulers and queue listeners** when `ApplicationContextRunner` or a small `@Import` configuration is enough. This reduces noise and overhead.

## 15. External resources: ports, DB, files, containers

`@DirtiesContext` does not automatically delete committed data in a DB or broker. For parallel test execution:

- Use dynamic ports when testing HTTP servers or mock servers.
- Use `@TempDir`/`Files.createTempFile`; do not share a single fixed-name marker file.
- Generate separate IDs/namespaces/schemas for test records.
- Clean up records by **owner/test-run ID**, without accidentally deleting shared data.
- With Testcontainers, distinguish per-test, per-class, and static shared containers.
- Do not share a queue without a correlation filter if multiple tests send messages in parallel.
- Ensure timeouts/rollbacks/cleanup run even when assertions fail.

For HTTP tests over a real port, do not assume `@Transactional` rolls back every side effect on the server thread: requests typically run in a separate transaction.

## 16. How to find leaks and hanging tests

### Enable context cache logging

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Inspect cache hits/misses and context shutdown lifecycles, but avoid concluding that a context close log proves **executors outside Spring** have stopped.

### Thread dump of the test worker

~~~bash
jcmd <PID> Thread.print
~~~

Replace `<PID>` with the PID of the actual test worker JVM, **not the Gradle daemon by mistake**. Look for threads named like `tracked-worker-*`, timers, schedulers, broker listeners, or threads waiting indefinitely on a latch.

Ask in order:

1. Which code created the thread?
2. Does it belong to a Spring bean or a test fixture?
3. Is there a cancel/interruption signal?
4. Did the cleanup method run?
5. Does the task have a loop ignoring interrupts?
6. Does the executor use `awaitTermination` with a timeout?
7. Is the TestContext cache still holding the context and worker?

### Do not use `Thread.activeCount()` as a hard assertion

Total active thread count can fluctuate due to Gradle, JUnit, GC, logging, and library timers. Some threads are daemons. A more reliable check is verifying that the **test-owned executor has terminated**, a specific thread has joined, or the worker's `finished` latch has counted down.

### Hook marker

Subprocess tests should verify **marker, exit code, and child timeout together**. Seeing only exit code `23` does not prove the hook executed successfully; seeing only the marker could be a stale file. Generate a unique name and delete it before the run.

## 17. Run matrix to confirm test independence

| Run mode | Goal |
| --- | --- |
| Single method | Basic logic |
| Full class | State shared across methods |
| Full suite | Context cache/static threads/hooks across classes |
| Reordered tests | Detect order assumptions |
| Repeated suite | Resource leaks and cleanup |
| Parallel runs when project permits | Contention on global resources, ports, DB |
| Low CPU/RAM CI | Expose sleep-based flaky tests |
| Timeout/exception tests | Whether `finally` and child cleanup still run |

Command to run one class in Gradle:

~~~bash
./gradlew test --tests 'com.example.lifecycle.WorkerIsolationTest'
~~~

Run the full suite:

~~~bash
./gradlew clean test
~~~

Do not fix flaky tests merely with `Thread.sleep(1000)`, raising timeouts indefinitely, or adding `@DirtiesContext` to all tests. Find the leaked resource at the right ownership level.

## 18. Common mistakes

1. **Manually closing an injected context from `@SpringBootTest`:** can corrupt the TestContext cache; use `@DirtiesContext`.
2. **Assuming every method gets a fresh context:** TestContext caches contexts by configuration key.
3. **Assuming `@DirtiesContext` resets all static variables:** wrong, JVM state remains.
4. **Marking all tests dirty:** slows the suite down and hides cleanup bugs.
5. **Creating an executor without shutting it down:** non-daemon workers can make Gradle tests hang.
6. **Calling `shutdownNow` and assuming the task is dead:** requires cooperative interruption + await.
7. **Using `Thread.sleep` to wait for events:** error-prone/flaky; use latches/futures.
8. **Registering a JVM shutdown hook in a test and forgetting to remove it:** the hook runs unexpectedly at suite end.
9. **Calling `System.exit` inside JUnit:** kills the entire test worker JVM.
10. **Assuming JVM hooks run in registration order:** not guaranteed.
11. **Using `Runtime.halt` to "test hooks":** halt skips hooks.
12. **Running a subprocess without a timeout:** a hanging child hangs the suite.
13. **Not cleaning up the child process in `finally`:** the child stays alive after an assertion failure.
14. **Using one shared marker file:** parallel tests overwrite results.
15. **Using `DEFINED_PORT` unnecessarily:** tests contend over ports.
16. **Assuming `@Transactional` rolls back HTTP server transactions:** client and server run on different threads.
17. **Forgetting to restore `System.setProperty`:** later tests read the wrong configuration.
18. **Clearing `ThreadLocal` only on the caller:** worker pool threads retain stale state.
19. **Confusing TestContext cache shutdown with Boot shutdown hooks:** different ownership levels.
20. **Believing a single isolated test run proves isolation:** you must run the full suite, repeated runs, and different orderings.
21. **Relying on `Thread.activeCount()`:** thread counts are noisy and do not verify a specific executor.
22. **Failing to check static Testcontainers resources:** closing a context does not necessarily clean up the container.
23. **Spawning a child process to test every service method:** far too expensive and unnecessary.
24. **Not clarifying bean and hook ownership:** cleanup gets missed or runs twice.
25. **Ignoring cancellation of async jobs:** tasks keep writing to the DB after another test has started.
26. **Assuming context close always runs every callback under a forced kill:** not guaranteed.

## 19. Pre-CI checklist

| Check item | Pass criteria |
| --- | --- |
| Context cache | Understand the cache key and know which tests reuse contexts |
| Dirty mode | Set before/after accurately when a context truly becomes dirty |
| Context owner | Clear ownership: TestContext, runner, or test caller |
| Bean cleanup | Appropriate destroy method/`@PreDestroy`/`SmartLifecycle` |
| Worker | Stops via interrupt/cancel and waits with a deadline |
| Async | No background tasks left affecting other tests |
| Hook | No leftover hooks in the parent JVM |
| Subprocess | Complete timeout, exit code, marker, and cleanup |
| Global state | Restore properties/Locale/TimeZone/static changes |
| ThreadLocal | Remove on the executing thread |
| Network | Use dynamic ports when possible |
| Data | Independent fixtures and namespaces/IDs, controlled cleanup |
| Parallelism | Synchronize or avoid global mutable state |
| Java/build | Java 17+, Spring Boot 3.3 BOM, JUnit 5 |
| Verification | Run single method, class, full suite, CI, and repeated runs |
| Failure evidence | Clear logs showing which process/context/thread was not cleaned up |

## 20. Self-check questions

1. **Why can two `@SpringBootTest` classes share a singleton?** Because TestContext caches contexts with the same configuration inside the JVM.
2. **What does `@DirtiesContext` do?** Marks the context dirty, removes it from the cache, and closes it according to its mode.
3. **Does `AFTER_CLASS` guarantee a fresh context before the class starts?** No; if you need a fresh one beforehand, use a `BEFORE` mode.
4. **Does `@DirtiesContext` reset static maps or JVM hooks?** No.
5. **When is `@DirtiesContext` unnecessary?** When a test does not dirty the context and reuse is safe.
6. **Who closes an `ApplicationContextRunner` context?** The runner closes it after the callback.
7. **Why check `isClosed` on a bean outside the callback?** Inside the callback the context is still open.
8. **Does `context.close()` automatically stop every `new Thread`?** No.
9. **Why can a non-daemon worker make Gradle tests hang?** Unfinished non-daemon threads keep the JVM alive.
10. **Can you rely on `shutdownNow` without await?** No, tasks must cooperate with interrupts.
11. **Why are latches/futures better than `sleep`?** They wait on a real condition with a deadline.
12. **Does a Runtime hook belong to the Spring context?** No, it belongs to the entire JVM.
13. **Should you call `System.exit(23)` inside a JUnit method?** No.
14. **Do hooks have a guaranteed execution order?** No, they can run concurrently.
15. **How do you remove a temporary hook?** `Runtime.removeShutdownHook` before JVM shutdown.
16. **What should a subprocess test verify?** Exit code, marker, timeout, and cleanup.
17. **Why use a unique marker file?** To avoid overwrites and stale results.
18. **Does a `@Transactional` test automatically roll back HTTP server-side work?** Not automatically.
19. **Should you modify System properties without restoring them?** No.
20. **Where must `ThreadLocal` on an executor worker be cleared?** Inside the worker thread.
21. **Why is `Thread.activeCount()` not reliable proof?** Many threads exist outside the test and the count fluctuates.
22. **When should you use a subprocess instead of a fresh context?** To test JVM-level hooks, `System.exit`/signals, or process exit.
23. **If a test only fails in the full suite, what should you inspect?** Context cache, static state, threads, hooks, ports, and external fixtures.
24. **How should you optimize test isolation?** Unit tests first, small contexts when sufficient, selective dirtying, and subprocesses only when a JVM boundary is needed.

**Conclusion:** Reliable lifecycle testing goes beyond "the context closed." Distinguish between the **Spring TestContext cache**, **threads/executors**, **JVM shutdown hooks**, **global state**, and **external fixtures**. Contexts managed by TestContext use dirty modes when appropriate; self-created contexts close immediately via `ApplicationContextRunner` or `try-with-resources`; workers need cancellation and bounded awaits; real hooks and `System.exit` run in child JVMs; and properties, files, ports, DBs, and `ThreadLocal`s need cleanup by their proper owner. When every test has clear boundaries and runs repeatedly in isolation, the suite truly verifies start/stop behavior without breaking other tests.

### References

- Spring Boot 3.3.13 — **Testing Spring Boot Applications**, `@SpringBootTest` and `webEnvironment`: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot — **ApplicationContextRunner** in auto-configuration authoring docs: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Framework 6.1 — **`@DirtiesContext` API**: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/test/annotation/DirtiesContext.html
- Spring Framework — **Context Caching**: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework — **Bean Lifecycle and `SmartLifecycle`**: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot 3.3.13 — **`SpringApplication.setRegisterShutdownHook`**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Oracle Java 17 — **Runtime shutdown hooks**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html
- Oracle Java 17 — **ProcessBuilder**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html
- Spring Boot 3.3 — **Gradle Managing Dependencies**: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
