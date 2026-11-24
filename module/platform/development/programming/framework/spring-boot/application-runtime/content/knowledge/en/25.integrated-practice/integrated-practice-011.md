# Testing Resource Leaks Across Repeated ApplicationContext Open and Close Cycles in Spring Boot

## 1. Practice Objectives

A Spring Boot application may run fine on its initial startup yet still **leak resources** when the same JVM must create, close, and recreate an `ApplicationContext` multiple times. This situation arises in:

- Integration tests creating multiple contexts.
- Spring Boot DevTools restarts in development environments.
- Applications with child contexts or dynamically toggled plugins/modules.
- Batch/CLI programs launching individual processing sessions within one process.
- Applications experimenting with lifecycle, configuration, and hot-reload.
- Libraries registering listeners, spawning executors, or opening sockets/files without releasing resources on context close.

Some bugs appear **only after 10, 20, or 100 rounds**. The context has closed, yet stray threads, file descriptors, connection pools, subscriptions, or static references retain old beans/classloaders.

**Lab objective:** build a Java 17+/Spring Boot 3.3 practice lab with two real resources: **an executor with its own thread** and **an open temporary file via `FileChannel`**. Repeatedly create and close contexts in a loop, check open/close counts, write JUnit tests for both the valid case and an intentionally missing destructor, and generalize to resources commonly seen in production applications.

The expected outcome is **zero active resources remaining after each round**, creation count matching cleanup count, without restarting the JVM to mask leaks.

### 1.1. Acceptance Criteria

After `N` context open/close rounds in **the same JVM**:

1. Each round starts the context cleanly or fails as expected.
2. Created resources belong to the right context with clear ownership.
3. Context `close()` is called **even if code inside the context throws an exception**.
4. Singleton beans with destructors are invoked by Spring per lifecycle.
5. Each executor is requested to shut down and confirmed terminated within a finite deadline.
6. Every file handle is closed; created temporary files are cleaned up per policy.
7. The `active` counter returns to baseline after each round, not merely at the end of the entire loop.
8. Resources on the startup failure path are also tested, not just the happy path.
9. Tests leave no zombie threads or open file handles after completion.
10. Do not use a single heap snapshot as "proof of no leak".

## 2. First: What Is a Resource Leak?

**A resource leak** means an object or handle remains held **after it is no longer needed**, exhausting system limits or preventing reclamation.

| Resource Type | Example | Signal to Measure |
| --- | --- | --- |
| Java threads | `ExecutorService`, scheduler, manual workers | Surviving threads, unterminated executors |
| File handles | `InputStream`, `FileChannel`, `WatchService` | Open channels, open file descriptor count not dropping |
| Network sockets | `ServerSocket`, HTTP client, gRPC channel | Unclosed sockets, lingering connections/state |
| Database connection pools | HikariCP, custom pools | Pool not shut down, active/idle connections remaining |
| External subscriptions | Message broker consumers, listeners, callbacks | Subscriptions/listeners still registered |
| Heap objects | Caches, sessions, unused beans | Retained references across GC cycles |
| Classloaders | DevTools restart loaders or plugin loaders | Old loaders retained by static caches/threads |
| Native memory | Direct buffers, JNI libraries | Native allocations retained off-heap |
| Scheduled tasks | Timers, schedulers, repeating jobs | Tasks still running after context close |
| External resources | Leases, distributed locks, temp cloud objects | Locks/leases not released or expired properly |

**Not all growth is a leak.** A JVM may expand committed heap, warm up JIT, cache metadata, or create valid caches. After several rounds, those measurements stabilize. Distinguish:

- **Live resource count**: resources genuinely open right now.
- **Total created count**: cumulative resources created.
- **Total closed count**: cumulative resources closed cleanly.
- **Heap used/committed**: JVM memory state, which does not directly prove handles are closed.
- **Retained object graph**: reference paths preventing objects/classloaders from being collected.

A useful invariant formula for consistently tracked resources:

```text
active = opened - closed
```

This is the **sample counter's logic invariant**. It does not replace OS-level measurement: a bug misupdating counters could still report 0 while real file descriptors remain unclosed.

## 3. Why Repeat Within the Same JVM?

If you simply run:

```bash
java -jar app.jar
java -jar app.jar
java -jar app.jar
```

each command spawns a new process. The operating system usually reclaims handles when a process exits, so **you cannot detect a static cache or abandoned executor surviving across context closes inside one JVM**.

A proper test for this goal requires:

```text
JVM process: start
    |
    +-- context #1 open -> use -> close
    |
    +-- context #2 open -> use -> close
    |
    +-- context #3 open -> use -> close
    |
    ...
    |
    +-- context #N open -> use -> close
    |
JVM process: exit
```

Specifically, you must **create a fresh context per round**. Reusing the same cached context from the test framework N times is not equivalent to N fresh startups.

### 3.1. Do Not Confuse `@SpringBootTest` with N Open/Close Rounds

The Spring TestContext Framework uses **context caching** to speed up test runs. A suite of `@SpringBootTest` methods sharing the same configuration may be served by **one reused context**, not a new context per test.

Thus, when the goal is repeated lifecycle testing:

- Use `SpringApplicationBuilder` / `SpringApplication.run` to explicitly create fresh contexts in a loop.
- Or use `ApplicationContextRunner` creating a context per callback run when the test only needs a lightweight configuration.
- Avoid defaulting to `@DirtiesContext` on every test to force context creation when a short, focused harness suffices.
- When using `@DirtiesContext`, understand it is a cache-eviction mechanism, **not a resource leak detector**.

## 4. What Does Spring Manage on `ApplicationContext.close()`?

For a context that has refreshed successfully, `ConfigurableApplicationContext.close()` executes lifecycle stopping and destroys eligible singletons.

A conceptual model:

```text
context.close()
    |
    +-- ContextClosedEvent
    |
    +-- LifecycleProcessor.onClose()
    |      +-- stop appropriate Lifecycle/SmartLifecycle beans
    |      +-- SmartLifecycle.stop(Runnable) with callback
    |
    +-- destroySingletons()
           +-- @PreDestroy
           +-- DisposableBean.destroy()
           +-- custom destroy method / close / shutdown
    |
    +-- release context-specific infrastructure
```

This is a **conceptual diagram**; exact ordering depends on context type, with exceptions when refresh fails.

Key points:

1. Spring can only destroy instances **within its managed lifecycle**.
2. `@Bean(destroyMethod = "close")` explicitly declares the cleanup method.
3. For `@Bean` methods, Spring Framework also **infers** suitable `close()`/`shutdown()` methods; an explicit `destroyMethod` is easier to read and audit.
4. `prototype` beans do not have their full destruction lifecycle managed by Spring like singletons.
5. An object instantiated with `new` and stored in a static field without registered ownership can outlive context close.
6. Resources opened in a constructor/factory that **fail before the bean finishes creation** must be cleaned up right at the allocation site.
7. `context.stop()` only coordinates lifecycle stopping; it is **not equivalent** to `context.close()` and does not destroy all singletons.
8. When a context closes, Spring does not automatically delete **external temporary files** unless the resource owner is written to clean them up.

### 4.1. `@Bean` `destroyMethod` Inference and Disabling Inference

A bean declared as:

```java
@Bean
SomeCloseableClient client() {
    return new SomeCloseableClient();
}
```

can have `close()`/`shutdown()` automatically registered by Spring if a matching method exists. This is a convenience contract for `@Bean`.

If you write:

```java
@Bean(destroyMethod = "")
SomeCloseableClient client() {
    return new SomeCloseableClient();
}
```

you **disable destroy-method inference** for that bean. If the object relies solely on inferred `close()`, closing the context will not invoke it.

This is a **counter-example variant** and should not be used on a handle-owning resource unless a different owner truly closes it.

Note: `destroyMethod = ""` **does not disable all destruction mechanisms**; for instance, `DisposableBean` still has its own callback. Therefore, know every lifecycle contract a bean implements.

## 5. Measurement Design: Baseline, Inside, After-Close

A test should measure at least three checkpoints:

| Checkpoint | Objective |
| --- | --- |
| Baseline before loop | Capture active resource counts before opening a new context |
| Inside active context | Prove resources were genuinely created and used |
| After `context.close()` | Confirm resources returned to baseline |

Example with **one executor and one file handle per context**:

```text
Before round 1: worker.active=0, file.active=0

Inside context 1:
    worker.active=1
    file.active=1

After closing context 1:
    worker.active=0
    file.active=0

Inside context 2:
    worker.active=1
    file.active=1

After closing context 2:
    worker.active=0
    file.active=0

...
```

Include **opened/closed counter pairs** to check creation count equals cleanup count, rather than checking active count at just one instant.

**Do not manually reset the active counter after each test round.** Resetting with `ACTIVE.set(0)` can hide real leaks. To compare against pre-test baseline, save an integer `beforeActive` and assert `afterActive == beforeActive`; never artificially force global state back to 0.

## 6. Runnable Spring Boot 3.3 / Java 17 Project

The example uses:

- A `TrackedWorker` bean owning an `ExecutorService`.
- A `TrackedTempFile` bean owning a `FileChannel` and temporary file.
- A loop explicitly opening/closing **five application contexts in the same JVM**.
- Two beans with `@Bean(destroyMethod = "close")`.
- A JUnit suite testing multiple rounds and a test intentionally disabling destruction.
- No database, web server, or external service needed, keeping it easy to run in learning environments.

### 6.1. Structure

```text
context-leak-lab/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          contextleak/
            ContextLeakLabApplication.java
            TrackedWorker.java
            TrackedTempFile.java
      resources/
        application.properties
    test/
      java/
        qa/
          contextleak/
            RepeatedContextTests.java
```

Isolate the test package `qa.contextleak` from `demo.contextleak` so test-only `@Configuration` classes are **not picked up by the main application's component scan**.

### 6.2. `settings.gradle`

```groovy
rootProject.name = 'context-leak-lab'
```

### 6.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.3.13 illustrates the 3.3 API branch; for new projects, choose a currently supported release. Compatible Gradle/Gradle wrapper and JDK 17+ are required. These files **do not auto-generate** `gradlew`: if no wrapper exists yet, run `gradle wrapper` using an installed Gradle.

### 6.4. `application.properties`

```properties
spring.application.name=context-leak-lab
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=OFF
```

`WebApplicationType.NONE` omits the web server so tests do not depend on ports. The log level merely reduces noise for the example; in production, never disable all logging as it hides operational errors.

## 7. `TrackedWorker.java`: Creating, Using, and Closing an Executor

File `src/main/java/demo/contextleak/TrackedWorker.java`:

```java
package demo.contextleak;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class TrackedWorker implements AutoCloseable {

    private static final AtomicInteger OPENED = new AtomicInteger();
    private static final AtomicInteger CLOSED = new AtomicInteger();
    private static final AtomicInteger ACTIVE = new AtomicInteger();
    private static final AtomicInteger THREAD_IDS = new AtomicInteger();

    private final AtomicBoolean closed = new AtomicBoolean(false);
    private final ExecutorService executor;

    public TrackedWorker() {
        ThreadFactory factory = task -> {
            Thread thread = new Thread(
                    task,
                    "context-leak-worker-"
                            + THREAD_IDS.incrementAndGet());
            thread.setDaemon(true);
            return thread;
        };

        this.executor = Executors.newSingleThreadExecutor(factory);

        OPENED.incrementAndGet();
        ACTIVE.incrementAndGet();
    }

    public String executeProbe() throws Exception {
        Future<String> result = executor.submit(
                () -> Thread.currentThread().getName());

        return result.get(5, TimeUnit.SECONDS);
    }

    @Override
    public void close() {
        if (!closed.compareAndSet(false, true)) {
            return;
        }

        executor.shutdown();

        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();

                if (!executor.awaitTermination(
                        5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Worker did not terminate.");
                }
            }
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted while closing worker.", ex);
        }

        CLOSED.incrementAndGet();
        ACTIVE.decrementAndGet();
    }

    public static int opened() {
        return OPENED.get();
    }

    public static int closed() {
        return CLOSED.get();
    }

    public static int active() {
        return ACTIVE.get();
    }
}
```

### 7.1. Key Explanations

- `Executors.newSingleThreadExecutor(...)` creates an executor managing a worker thread when tasks are submitted.
- `ThreadFactory` names threads so they are easy to spot in thread dumps.
- `setDaemon(true)` is used **only in the lab** to reduce the risk of a test bug keeping the Java process alive forever; **daemon status is not cleanup**. A leaked thread, even if daemon, consumes resources until the JVM exits.
- `executeProbe()` genuinely submits a task rather than checking an unused `ExecutorService` object.
- `Future.get(5, TimeUnit.SECONDS)` enforces a timeout so tests never hang forever.
- `close()` calls `shutdown()` and awaits termination with a deadline; on expiry, it sends interrupts via `shutdownNow()`.
- `shutdownNow()` is **best-effort interruption** and does not guarantee tasks blocked in arbitrary I/O will stop.
- `AtomicBoolean closed` prevents double-closing and double-counting.
- `ACTIVE` decrements only once shutdown is confirmed complete.

**Meaning of counters:** `OPENED`/`CLOSED`/`ACTIVE` are logical metrics to test the example's lifecycle. They do not by themselves prove threads are not leaking at the JVM level if other code spawns threads bypassing the tracker.

### 7.2. A Limitation of the Illustrative Design

If `close()` throws because the executor failed to terminate, `closed` has already flipped to true while `ACTIVE` has not decremented. Tests detect the abnormal state instead of pretending success. A real implementation may need a full `OPEN → CLOSING → CLOSED/FAILED` state machine for better retries or error reporting. This is an intentional lab with short tasks, not a general-purpose executor management library.

## 8. `TrackedTempFile.java`: `FileChannel` and Temporary File

File `src/main/java/demo/contextleak/TrackedTempFile.java`:

```java
package demo.contextleak;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class TrackedTempFile implements AutoCloseable {

    private static final AtomicInteger OPENED = new AtomicInteger();
    private static final AtomicInteger CLOSED = new AtomicInteger();
    private static final AtomicInteger ACTIVE = new AtomicInteger();

    private final AtomicBoolean closed = new AtomicBoolean(false);
    private final Path path;
    private final FileChannel channel;

    public TrackedTempFile() throws IOException {
        Path created = Files.createTempFile(
                "context-leak-lab-", ".tmp");

        FileChannel openedChannel;

        try {
            openedChannel = FileChannel.open(
                    created, StandardOpenOption.WRITE);
        } catch (IOException | RuntimeException failure) {
            try {
                Files.deleteIfExists(created);
            } catch (IOException cleanupFailure) {
                failure.addSuppressed(cleanupFailure);
            }

            throw failure;
        }

        this.path = created;
        this.channel = openedChannel;

        OPENED.incrementAndGet();
        ACTIVE.incrementAndGet();
    }

    public void writeOneByte() throws IOException {
        ByteBuffer buffer = ByteBuffer.wrap(new byte[] { 1 });

        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }
    }

    @Override
    public void close() throws IOException {
        if (!closed.compareAndSet(false, true)) {
            return;
        }

        IOException failure = null;

        try {
            channel.close();
        } catch (IOException ex) {
            failure = ex;
        }

        try {
            Files.deleteIfExists(path);
        } catch (IOException ex) {
            if (failure == null) {
                failure = ex;
            } else {
                failure.addSuppressed(ex);
            }
        }

        if (failure != null) {
            throw failure;
        }

        CLOSED.incrementAndGet();
        ACTIVE.decrementAndGet();
    }

    public static int opened() {
        return OPENED.get();
    }

    public static int closed() {
        return CLOSED.get();
    }

    public static int active() {
        return ACTIVE.get();
    }
}
```

### 8.1. Why Put `try/catch` Directly in the Constructor?

Allocation order:

1. `Files.createTempFile(...)` creates a file on the filesystem.
2. `FileChannel.open(...)` opens a channel for writing.
3. If opening the channel succeeds, the object takes ownership of path/channel.
4. If opening the channel fails, the constructor attempts to delete the temporary file itself.

If the constructor throws at step 2, the bean has not been fully constructed by Spring. **Never rely on `@PreDestroy` of a non-existent bean** to clean up the temporary file.

`failure.addSuppressed(cleanupFailure)` preserves the channel-open error as the primary cause without losing file-deletion error details.

### 8.2. Why Close the Channel Before Deleting?

Some operating systems, especially Windows, forbid deleting a file while an open handle remains. Closing the channel before deleting the file respects ownership and maximizes cleanup success.

This is a **real file resource**, not just an object counter. Even so, file deletion can still be affected by permissions, antivirus, filesystems, or external processes. In CI, ensure the JVM temp directory allows write/delete and treat OS errors as signals to investigate rather than tweaking counters to pass tests.

### 8.3. Signs of Uncleaned Resources

- `TrackedTempFile.active() > 0` after context close.
- `opened() > closed()`.
- Temporary files still lingering after the context closed cleanly.
- Open file descriptor count steadily climbing across iterations.
- On Windows, deleting or moving a test file may fail due to an unclosed handle; still, do not treat file deletion ability as the sole measurement across every OS.

## 9. `ContextLeakLabApplication.java`: Repeatedly Opening and Closing Contexts

File `src/main/java/demo/contextleak/ContextLeakLabApplication.java`:

```java
package demo.contextleak;

import java.io.IOException;

import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(proxyBeanMethods = false)
public class ContextLeakLabApplication {

    @Bean(destroyMethod = "close")
    TrackedWorker trackedWorker() {
        return new TrackedWorker();
    }

    @Bean(destroyMethod = "close")
    TrackedTempFile trackedTempFile() throws IOException {
        return new TrackedTempFile();
    }

    public static ConfigurableApplicationContext openContext() {
        return new SpringApplicationBuilder(
                ContextLeakLabApplication.class)
                .web(WebApplicationType.NONE)
                .run();
    }

    public static void main(String[] args) throws Exception {
        final int rounds = 5;

        for (int round = 1; round <= rounds; round++) {
            try (ConfigurableApplicationContext context =
                    openContext()) {

                TrackedWorker worker =
                        context.getBean(TrackedWorker.class);
                TrackedTempFile file =
                        context.getBean(TrackedTempFile.class);

                worker.executeProbe();
                file.writeOneByte();

                require(TrackedWorker.active() == 1,
                        "Worker count inside context is wrong.");
                require(TrackedTempFile.active() == 1,
                        "File count inside context is wrong.");

                System.out.printf(
                        "round=%d inside worker=%d file=%d%n",
                        round,
                        TrackedWorker.active(),
                        TrackedTempFile.active());
            }

            require(TrackedWorker.active() == 0,
                    "Worker leak after context close.");
            require(TrackedTempFile.active() == 0,
                    "File leak after context close.");

            System.out.printf(
                    "round=%d after worker=%d file=%d%n",
                    round,
                    TrackedWorker.active(),
                    TrackedTempFile.active());
        }

        require(TrackedWorker.opened() == rounds,
                "Unexpected worker allocation count.");
        require(TrackedWorker.closed() == rounds,
                "Not all workers were closed.");
        require(TrackedTempFile.opened() == rounds,
                "Unexpected file allocation count.");
        require(TrackedTempFile.closed() == rounds,
                "Not all temp files were closed.");

        System.out.printf(
                "PASS openedWorkers=%d closedWorkers=%d "
                + "openedFiles=%d closedFiles=%d%n",
                TrackedWorker.opened(),
                TrackedWorker.closed(),
                TrackedTempFile.opened(),
                TrackedTempFile.closed());
    }

    private static void require(
            boolean condition, String explanation) {

        if (!condition) {
            throw new IllegalStateException(explanation);
        }
    }
}
```

### 9.1. Why Use `SpringApplicationBuilder` Instead of a Plain Context?

`SpringApplicationBuilder` genuinely executes Spring Boot's startup mechanism and builds a new application context with Boot's environment. This stays closer to runtime than a plain `AnnotationConfigApplicationContext`.

`WebApplicationType.NONE` avoids starting a web server in the demo, so only the declared resources need measurement. When building a real web service, add measurements for embedded server threads/connections rather than extrapolating solely from a non-web lab.

### 9.2. Why Use `try-with-resources`?

`ConfigurableApplicationContext` implements `close()` and `AutoCloseable`, so:

```java
try (ConfigurableApplicationContext context = openContext()) {
    // Use beans.
}
```

guarantees Java calls `close()` upon leaving the block, even if code inside throws an exception. This is central to leak testing: **never let the test itself cause a leak by forgetting to close the context**.

**Avoid:**

```java
ConfigurableApplicationContext context = openContext();
doSomethingThatCanFail(context);
context.close();
```

This is **pseudocode**; `doSomethingThatCanFail` is undefined. If the intermediate call throws, `close()` may never execute. Use `try-with-resources` or `finally` properly.

### 9.3. Why Check After Every Round?

If you only check after the fifth round, a lazily opened bean or a failure occurring on one specific iteration becomes hard to isolate. Checking after **every context close** pinpoints which round first lost balance, drastically reducing debugging effort.

### 9.4. Reliable Output of the Demo

Assuming the application runs standalone, beans initialize/close cleanly, and no external resources interfere with the static counters, the lines **printed by the application itself** are:

```text
round=1 inside worker=1 file=1
round=1 after worker=0 file=0
round=2 inside worker=1 file=1
round=2 after worker=0 file=0
round=3 inside worker=1 file=1
round=3 after worker=0 file=0
round=4 inside worker=1 file=1
round=4 after worker=0 file=0
round=5 inside worker=1 file=1
round=5 after worker=0 file=0
PASS openedWorkers=5 closedWorkers=5 openedFiles=5 closedFiles=5
```

Additional output from Gradle/JVM may appear when running via a build tool; the lines above are the markers printed by the code, without claiming all of stdout contains strictly 11 lines.

Points to examine closely:

- Inside each context: each resource type has **exactly one active instance**.
- After `close()`: both counts drop to 0.
- Each type is created and closed exactly five times.
- No `System.gc()` is needed for the counters to match.
- No process restarts between rounds: a single `main` executes all five rounds.

## 10. Compiling, Running, and Reading Results

Once the Gradle wrapper is in place:

```bash
./gradlew clean test
./gradlew bootRun
```

Or build and run the JAR:

```bash
./gradlew bootJar
java -jar build/libs/context-leak-lab-1.0.0.jar
```

The JAR name comes from `settings.gradle` and the version in the illustrative `build.gradle`; if custom archive settings are used, use the actual built filename.

**If the system lacks permission to write temporary files**, `TrackedTempFile` can fail at startup. This test intentionally uses real files, so OS permissions are an environmental prerequisite. Run with a valid temp directory rather than "fixing" the test by dropping cleanup checks.

### 10.1. Increasing the Number of Rounds

You can change:

```java
final int rounds = 5;
```

to:

```java
final int rounds = 50;
```

This is a **variant**; do not add a second `rounds` declaration. Run 5 rounds to verify logic; increase to 50–100 rounds when observing long-term trends. Increasing round count does not by itself prove correctness if you only take one snapshot at the end.

### 10.2. Only Running Inside the Same JVM Is Meaningful

`./gradlew bootRun` launches one Java process. Inside **that process**, `main` creates 5 or 50 application contexts. That is what constitutes testing leaks across multiple contexts.

Running `./gradlew bootRun` 50 separate times, each in a fresh process, is not equivalent.

## 11. JUnit Tests for Repeated Open/Close Cycles

File `src/test/java/qa/contextleak/RepeatedContextTests.java`:

```java
package qa.contextleak;

import java.util.concurrent.atomic.AtomicReference;

import demo.contextleak.ContextLeakLabApplication;
import demo.contextleak.TrackedTempFile;
import demo.contextleak.TrackedWorker;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class RepeatedContextTests {

    @Test
    void closesEveryContextAndReturnsToBaseline() throws Exception {
        int workerActiveBefore = TrackedWorker.active();
        int fileActiveBefore = TrackedTempFile.active();

        int workerOpenedBefore = TrackedWorker.opened();
        int workerClosedBefore = TrackedWorker.closed();
        int fileOpenedBefore = TrackedTempFile.opened();
        int fileClosedBefore = TrackedTempFile.closed();

        final int rounds = 3;

        for (int i = 0; i < rounds; i++) {
            try (ConfigurableApplicationContext context =
                    ContextLeakLabApplication.openContext()) {

                context.getBean(TrackedWorker.class).executeProbe();
                context.getBean(TrackedTempFile.class).writeOneByte();

                assertThat(TrackedWorker.active())
                        .isEqualTo(workerActiveBefore + 1);
                assertThat(TrackedTempFile.active())
                        .isEqualTo(fileActiveBefore + 1);
            }

            assertThat(TrackedWorker.active())
                    .isEqualTo(workerActiveBefore);
            assertThat(TrackedTempFile.active())
                    .isEqualTo(fileActiveBefore);
        }

        assertThat(TrackedWorker.opened() - workerOpenedBefore)
                .isEqualTo(rounds);
        assertThat(TrackedWorker.closed() - workerClosedBefore)
                .isEqualTo(rounds);
        assertThat(TrackedTempFile.opened() - fileOpenedBefore)
                .isEqualTo(rounds);
        assertThat(TrackedTempFile.closed() - fileClosedBefore)
                .isEqualTo(rounds);
    }

    @Test
    void detectsMissingDestroyMethodThenCleansTestResource() {
        int activeBefore = TrackedWorker.active();
        AtomicReference<TrackedWorker> created =
                new AtomicReference<>();

        try {
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            MissingDestroyConfiguration.class)
                    .run(context -> {
                        assertThat(context).hasNotFailed();
                        created.set(
                                context.getBean(TrackedWorker.class));

                        try {
                            created.get().executeProbe();
                        } catch (Exception ex) {
                            throw new IllegalStateException(ex);
                        }
                    });

            // ApplicationContextRunner already closed the context,
            // yet destroyMethod="" disabled close() inference.
            assertThat(TrackedWorker.active())
                    .isEqualTo(activeBefore + 1);
        } finally {
            TrackedWorker worker = created.get();

            if (worker != null) {
                worker.close();
            }
        }

        assertThat(TrackedWorker.active())
                .isEqualTo(activeBefore);
    }

    @Test
    void cleansCreatedSingletonWhenLaterBeanFails() {
        int activeBefore = TrackedWorker.active();
        int closedBefore = TrackedWorker.closed();

        new ApplicationContextRunner()
                .withUserConfiguration(FailingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    IllegalStateException.class);
                });

        assertThat(TrackedWorker.active())
                .isEqualTo(activeBefore);
        assertThat(TrackedWorker.closed())
                .isEqualTo(closedBefore + 1);
    }

    @Configuration(proxyBeanMethods = false)
    static class MissingDestroyConfiguration {

        @Bean(destroyMethod = "")
        TrackedWorker unmanagedWorker() {
            return new TrackedWorker();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class FailingConfiguration {

        @Bean(destroyMethod = "close")
        TrackedWorker resource() {
            return new TrackedWorker();
        }

        @Bean
        String failingBean(TrackedWorker resource) {
            throw new IllegalStateException(
                    "simulated-refresh-failure");
        }
    }
}
```

The tests above compile inside the project's `spring-boot-starter-test` setup with JUnit Jupiter and AssertJ.

### 11.1. What Does Test 1 Prove?

- The same test JVM opens **three fresh contexts**.
- Inside each context, the worker and file are actually exercised.
- After every `close()`, active counts return to baseline.
- Total opened/closed counts increment by exactly three.
- The test does not need `@SpringBootTest` and does not depend on context caching.

Baselines are captured **before the test runs**, so it does not assume no other test in the JVM ever created resources. Still, tests sharing static counters should run **non-concurrently** or with proper resource isolation; this test is not designed for simultaneous concurrent context creation.

### 11.2. Test 2 Is a Negative Control with Safe Cleanup

`MissingDestroyConfiguration` declares:

```java
@Bean(destroyMethod = "")
TrackedWorker unmanagedWorker() {
    return new TrackedWorker();
}
```

Spring does not auto-invoke `close()` via destroy-method inference for this bean. `ApplicationContextRunner` closes the context after the callback, yet the resource remains active according to the tracker.

Critically, the test uses `finally` to **close the worker itself**, preventing an "intentional leak demo" from leaking into subsequent tests.

The goal of the **negative control** is to prove the counters actually catch a missing destructor, rather than always passing blindly.

### 11.3. Test 3 Verifies the Refresh Failure Path

`FailingConfiguration` declares the resource first, then `failingBean(TrackedWorker resource)` depends on it and throws. Because the resource was already instantiated as a singleton with a registered destructor, Spring Framework attempts to destroy it when refresh fails.

The test verifies:

- The context reports failed.
- The root cause is the intentionally thrown error.
- Active count returns to baseline.
- Close count increases by one.

**Limitation:** if `TrackedWorker`'s own constructor throws **before returning the bean**, Spring may not yet have an instance registered with a destructor. Half-opened resources must be cleaned up directly inside the constructor/factory.

### 11.4. Why Place Test Configuration in a Different Package?

The main application lives in `demo.contextleak`, while tests live in `qa.contextleak`. If test-only `@Configuration` classes resided inside packages scanned by the main component scan, they could accidentally be instantiated during the main test loop, inflating bean/resource counts beyond expectations.

Keeping test configuration outside the application's base package prevents **test configurations from affecting the startup of the program under test**.

## 12. Testing Failure Inside a `@Bean` Factory: Ownership Before Return

Consider this anti-pattern:

```java
@Bean(destroyMethod = "close")
RemoteSession remoteSession() throws Exception {
    RemoteSession session = new RemoteSession();
    session.open();
    throw new IllegalStateException("after-open failure");
}
```

This is a **snippet**; no `RemoteSession` class is defined in the demo project.

The `session` resource was opened, yet the bean factory never `return`ed. The container may **not know which instance to close**, because no completed bean was registered. Do not rely on `@PreDestroy`/destroyMethod for an incomplete bean.

A safer approach:

```java
@Bean(destroyMethod = "close")
RemoteSession remoteSession() throws Exception {
    RemoteSession session = new RemoteSession();

    try {
        session.open();
        return session;
    } catch (Exception | Error failure) {
        try {
            session.close();
        } catch (Exception cleanupFailure) {
            failure.addSuppressed(cleanupFailure);
        }

        throw failure;
    }
}
```

This is also a **snippet**, requiring a `RemoteSession` type implementing `open/close`. Principle: **before returning the bean, the factory still owns the resource and must roll back on error**; after returning cleanly, Spring owns destroying the resource.

### 12.1. Testing Partial Allocation Failures

A solid test should exercise:

- Opening file 1 succeeds.
- Opening file 2 fails.
- Confirming file 1 is closed even though the bean never finished creation.
- Preserving file 2's root cause.
- Attaching cleanup errors as suppressed exceptions if any occur.
- Never assuming bean post-processors/destructors are guaranteed to run for an incomplete bean.

If a resource cannot be closed safely after a constructor failure, fix the resource design or use a rollback-capable factory rather than merely adding lifecycle annotations.

## 13. Do Tests Genuinely Catch Thread Leaks?

Counters may say worker `active=0`, yet for real-world diagnostics you can also inspect **live threads by prefix**, thread dumps, or Java Flight Recorder.

### 13.1. Thread Names

In `TrackedWorker`, threads are named:

```text
context-leak-worker-1
context-leak-worker-2
...
```

This lets you locate matching threads in JVM thread dumps. However, **thread names can repeat or be changed** in real libraries; never rely solely on thread names as business identifiers.

### 13.2. `java.lang.management.ThreadMXBean`

A JVM can query:

```java
ThreadMXBean bean =
        ManagementFactory.getThreadMXBean();

int total = bean.getThreadCount();
System.out.println("jvm.threadCount=" + total);
```

This is a snippet requiring imports `java.lang.management.ManagementFactory` and `ThreadMXBean`.

This metric shows the **live platform thread** count per API/VM scope, yet fluctuates due to GC, JIT, timers, agents, and Spring internals. Never assert `getThreadCount()` equals an exact fixed number after each round; many unrelated subsystems can spawn or terminate threads in the same JVM.

**For Java 21+ virtual threads, use appropriate tooling**; some thread enumeration APIs do not represent every virtual thread, so do not use a single `ThreadMXBean` snapshot to conclude there is no virtual-thread leak.

### 13.3. Tracking Specific Thread Prefixes via Instrumentation

In a simple JVM test using platform threads, you can check:

```java
long count = Thread.getAllStackTraces()
        .keySet()
        .stream()
        .filter(Thread::isAlive)
        .filter(thread -> thread.getName()
                .startsWith("context-leak-worker-"))
        .count();

System.out.println("matchingThreads=" + count);
```

This snippet fits inside a Java 17+ method with standard imports; it counts threads still visible at the instant sampled. A terminating thread may not have vanished in one snapshot, so use bounded polling if a thread-liveness test genuinely needs it. Never use arbitrary `Thread.sleep` as the sole pass condition.

The primary test should still rely on `ExecutorService.awaitTermination` and trackers because they tie directly to the resource owner's contract.

## 14. File Descriptors: Measuring Directly at the OS Level

On Linux, you can inspect a process:

```bash
ls /proc/<PID>/fd | wc -l
```

Here `<PID>` is a **placeholder** for the real PID, not a verbatim copy-and-run command. `/proc` availability depends on OS/container and permissions.

In a shell holding the Java process PID:

```bash
ls "/proc/$PID/fd" | wc -l
```

File descriptor counts include sockets, pipes, regular files, and other handles—not just the lab's temporary files. Look for **a stable baseline trend** and inspect specific resources rather than asserting the whole JVM's FD count matches to the exact unit.

On Windows, use Resource Monitor, Process Explorer, or equivalent tools to inspect open handles/threads in a process.

### 14.1. `UnixOperatingSystemMXBean`

Some Unix-based JVMs provide an extended MBean with `getOpenFileDescriptorCount()`:

```java
OperatingSystemMXBean os =
        ManagementFactory.getOperatingSystemMXBean();

if (os instanceof UnixOperatingSystemMXBean unix) {
    System.out.println("openFd="
            + unix.getOpenFileDescriptorCount());
}
```

This snippet targets runtimes offering `com.sun.management.UnixOperatingSystemMXBean` and `java.lang.management.ManagementFactory`; **it does not run identically on every OS/JVM**. Check availability at runtime rather than treating this interface as a mandatory portable API.

If FD counts rise steadily after every round, that is a **signal to investigate**. If it rises only during the first few rounds and then plateaus, it may be legitimate warm-up/caching. Inspect specific handles with OS tools before declaring a leak.

## 15. Heap and GC: Measuring Correctly to Avoid False Alarms

Many developers try:

```java
long before = Runtime.getRuntime().totalMemory()
        - Runtime.getRuntime().freeMemory();
```

then open/close contexts and assert memory **must return to the exact `before` value**. This is a **fragile test**.

Reasons:

- The JVM may expand committed heap and retain it.
- GC does not necessarily run at the moment you read `freeMemory()`.
- JIT, reflection, class metadata, and caches warm up gradually.
- Logging, metrics, and drivers maintain legitimate caches.
- Heap objects may remain alive without representing a resource leak.
- Native memory, file handles, and DB connections are not fully reflected in heap used.

### 15.1. `System.gc()` Is Not Proof

`System.gc()` is a hint to the JVM to perform GC, not a contract forcing immediate collection of every object. Calling it repeatedly in tests slows execution, depends on GC flags, and causes false negatives/positives.

Do not write acceptance tests following the pattern:

```text
System.gc()
assert(heapUsed == exactBaseline)
```

Instead:

1. Measure counters and lifecycle contracts directly.
2. Run multiple rounds to spot trends.
3. Use JFR/heap dumps when sustained growth appears.
4. Trace **retaining paths** of objects/classloaders that should not persist.
5. Evaluate memory plateaus under realistic workloads and environments rather than demanding an exact byte count.

### 15.2. `WeakReference` Is Not an Absolute Assertion

An advanced check retains a `WeakReference<ApplicationContext>` after closing the context and dropping strong references. Yet `weakRef.get() != null` right after `close()` does not prove a leak: GC may simply not have run. Conversely, a single `weakRef.get()==null` does not prove every native resource was closed.

If using weak references for diagnostics:

- Do not store contexts in static test collections.
- Do not let lambdas or `ThreadLocal`s accidentally capture the context.
- Use finite waits and multiple observations.
- Treat the result as an investigative signal, not sole proof.

## 16. HikariCP, JDBC, and Database Connections

In real projects, the easiest resource to leak can be a database connection pool.

When Spring Boot creates a `HikariDataSource` and the bean is properly managed, the destroy callback closes the pool per lifecycle. However, you might still create a pool outside Spring:

```java
HikariDataSource ds = new HikariDataSource();
ds.setJdbcUrl("jdbc:example:...");
ds.setMaximumPoolSize(10);
// Forgot ds.close() when no longer needed.
```

This is an **illustrative snippet**, not runnable JDBC configuration: the URL is intentionally a logical placeholder to avoid real connections, and HikariCP plus valid credentials/drivers are required.

When testing repeated contexts against a real DB or Testcontainers:

- Distinguish **per-context `DataSource` beans** from an external/static `DataSource`.
- Check `HikariPoolMXBean.getActiveConnections()` and `getIdleConnections()` when using Hikari.
- Close connections, statements, and result sets per call AND **close the pool** when the context is destroyed.
- Monitor physical connections from the database side.
- Test cleanup on the startup failure path if the connection pool was created and a later bean failed.
- Do not conclude `activeConnections == 0` means the pool is closed; a pool may still hold **idle connections** and housekeeping threads.
- Do not check only DB processes: server-side sessions time out eventually; client-side leaks still require testing.

### 16.1. Why Not Add a Real DB to the Baseline Demo?

A real DB introduces extra failure modes: networking, credentials, container availability, migrations, transaction timeouts, and driver quirks. The lab uses a worker and file first to prove Spring's close mechanics reproducibly; add database metrics afterward when needed.

## 17. `@Async`, Schedulers, and Tasks Still Running After Context Close

Background tasks can invalidate leak tests if closing the bean does not wait for tasks to finish.

Example:

```java
@Component
class PollingService {

    private final ScheduledExecutorService scheduler =
            Executors.newSingleThreadScheduledExecutor();

    @PostConstruct
    void start() {
        scheduler.scheduleAtFixedRate(
                this::poll, 0, 1, TimeUnit.SECONDS);
    }

    @PreDestroy
    void stop() {
        scheduler.shutdownNow();
    }

    void poll() {
        // Business work.
    }
}
```

This is an **illustrative snippet**, needing imports for `Component`, `PostConstruct`, `PreDestroy`, `ScheduledExecutorService`, `Executors`, and `TimeUnit`.

Issues here:

- `shutdownNow()` sends a stop request but **does not guarantee tasks have finished**.
- `poll()` may make I/O calls without timeouts and ignore interrupts.
- If the context finishes closing while the task still holds DB/client handles, temporary leaks or post-shutdown errors can occur.
- If the bean is `@Lazy` and was never requested, `@PostConstruct`/`@PreDestroy` never run because no instance exists.
- If a task was spawned **outside bean lifecycle**, callbacks may have no control over it.

Better: manage the scheduler under a clear owner, stop intake, and use `awaitTermination` with a deadline. For components needing coordinated stop phases, `SmartLifecycle` fits better than a destructor calling non-blocking shutdown.

### 17.1. `SmartLifecycle.stop(Runnable)` Has Its Own Semantics

A `SmartLifecycle` component can implement `stop(Runnable callback)` to notify the lifecycle processor **when stopping has genuinely completed**. Never invoke the callback right after merely submitting an async stop request.

Phase ordering is helpful when:

```text
Start:
    database/client service (low phase)
             ↓
    message consumer (high phase)

Stop:
    message consumer (high phase)
             ↓
    database/client service (low phase)
```

If a consumer needs the DB to checkpoint while stopping, stopping the consumer before closing the DB makes sense. **A test that only counts threads does not prove dependency order is right.**

## 18. Event Listeners, Subscriptions, and Static Registries

A subtle leak occurs when a bean registers a listener into a registry outliving the context without unregistering:

```java
@Component
class Watcher {

    private final GlobalEventBus bus;
    private final EventListener listener;

    Watcher(GlobalEventBus bus) {
        this.bus = bus;
        this.listener = event -> handle(event);
        bus.register(listener);
    }

    @PreDestroy
    void close() {
        bus.unregister(listener);
    }

    private void handle(Event event) {
        // Handle event.
    }
}
```

This is a **conceptual snippet**: `GlobalEventBus`, `EventListener`, and `Event` from a specific library plus imports are needed. Do not treat it as a standalone Java file with all dependencies.

If `GlobalEventBus` is a singleton/static living outside the context, it can retain `Watcher` instances from old contexts across many rounds. Closing the context **does not automatically remove registrations from a registry outside Spring**.

### 18.1. How to Test Registry Leaks

Before round: `bus.listenerCount() == baseline`.

Inside context: listener count rises by the number of registrations.

After close: listener count must return to baseline.

Run multiple rounds and verify the exact listener unregistered. Avoid tests measuring only memory after `System.gc()`, as registry counts directly reflect the registration contract far more clearly.

### 18.2. `ThreadLocal` and MDC

A `ThreadLocal` attached to a long-lived thread pool can retain references to objects from a closed context. For logging MDC, libraries usually provide `clear()` or scoped context helpers.

When using custom executors:

- Clear `ThreadLocal` in the task's `finally` block.
- Never store `ApplicationContext` or short-lived beans in a static `ThreadLocal`.
- Stop/close context-owned executors.
- Do not assume switching contexts automatically resets data on threads reused from an external pool.

## 19. DevTools Restarts and Classloader Leaks

Spring Boot DevTools typically uses a **base classloader** for library JARs and a **restart classloader** for mutable application classes.

When a restart occurs:

```text
Base loader stays alive
        |
        +-- Restart loader R1 → app context R1
        |                         |
        |                         +-- context close
        |
        +-- Restart loader R2 → app context R2
        |
        +-- R1 is GC'd only once no strong references remain
```

If a static cache in the base loader holds a `Class<?>` or instance from R1, or an old thread retains R1 as its thread context classloader, **R1 may not be collected** even though the context closed.

This differs from a file-handle leak:

- File handles require `close()`.
- Restart classloaders require **clearing all strong references to the classloader and its classes/objects**.
- A static reference from base to an old class/application object can make metaspace climb across restarts.
- You cannot fix a classloader leak merely by increasing heap or calling `System.gc()`.

### 19.1. Is Looping Contexts Identical to a DevTools Restart?

**Not entirely.**

Looping `SpringApplicationBuilder` inside **the same classloader** tests the lifecycle of multiple contexts in one JVM, yet **does not swap restart classloaders** like DevTools.

To test DevTools-specific leaks:

- Run the app in development mode with DevTools restart active.
- Trigger multiple valid classpath changes.
- Inspect retained `RestartClassLoader` instances via heap dumps/JFR/profilers.
- Check thread TCCLs, static caches, and registrations held from the base loader.
- Ensure context-owned resources close before every restart.
- If the bug only appears with DevTools, run a control with restart completely disabled to narrow the cause.

**Do not attribute all memory growth across a context loop to a "DevTools classloader leak"** if your test never even created restart classloaders.

## 20. Counting Resources Without Causing Leaks in Tests

Some testing anti-patterns:

### 20.1. Holding Contexts in a Static List

```java
static final List<ApplicationContext> CONTEXTS =
        new ArrayList<>();

// Each round:
CONTEXTS.add(context);
```

This snippet needs imports and a `context` variable; it intentionally illustrates an **anti-pattern**.

Even when `context.close()` is called, the static list retains references to context/bean metadata. That skews GC test results. If statistics are needed, store lightweight metrics (numbers/counts/short strings) or weak references for observation, never whole contexts.

### 20.2. A Shared `@SpringBootTest` Context Cache

Running 50 test methods that only load one cached context does not prove resources were closed 50 times. Control lifecycles to match your goal.

### 20.3. Never Calling `getBean`

If a bean is marked `@Lazy` and you never request it, its constructor may never run, giving `opened=closed=0`. That result **does not prove the bean cleans up properly**.

In the demo, the code deliberately calls `getBean` and then `executeProbe()` / `writeOneByte()` so resources are genuinely allocated and exercised.

### 20.4. Manually Resetting Active Resource Counters

```java
TrackedWorker.ACTIVE.set(0);
```

This is a **counter-example** and would not compile against the demo's private field. Resetting counters merely hides discrepancies without closing executors. Never use this trick to turn a failure into a PASS.

### 20.5. Checking Too Early

An executor shutting down asynchronously may need time. Do not assert thread counts nanoseconds after issuing `shutdown()` and claim a leak if the component has an incomplete async stop contract.

Use `awaitTermination` or completion callbacks **with a deadline**. Conversely, do not wait indefinitely hoping a test "eventually passes" without bounds.

## 21. Extending to Spring Boot `ApplicationContextRunner`

Spring Boot's `ApplicationContextRunner` helps test a lightweight context:

```java
new ApplicationContextRunner()
        .withUserConfiguration(SmallConfig.class)
        .run(context -> {
            assertThat(context).hasNotFailed();
            // Inspect beans inside context.
        });
```

This **snippet** requires `SmallConfig` and AssertJ imports. The `run` callback can interact with the context, after which the runner closes the context per lifecycle.

Benefits:

- No need to boot all auto-configuration.
- Creates a fresh context on every `run`.
- Can assert context failure while still inspecting startup failures.
- Easy to test a single `@Bean`/conditional bean and destructor.
- Avoids opening web servers or network ports unnecessarily.

Yet limitations:

- Does not automatically invoke `ApplicationRunner` / `CommandLineRunner` like `SpringApplication.run`.
- Does not test full Boot startup events or arbitrary out-of-context resources.
- Does not prove the production JAR closes resources under the same config if the runner registers only a subset of beans.
- Should not replace all integration tests of a real service.

### 21.1. Which Harness to Choose?

| Goal | Prefer |
| --- | --- |
| Test one resource bean and destroy method | `ApplicationContextRunner` |
| Test multiple real Boot startup rounds (non-web) | `SpringApplicationBuilder` |
| Test web server graceful shutdown | Process/service integration test with HTTP |
| Test database connection pool | Integration with DB/Testcontainers and pool metrics |
| Test DevTools classloader leak | Repeated DevTools restarts, heap analysis |
| Test port/socket cleanup | Run real server/socket, measure bound ports |
| Test pure Java resource handling logic | `AutoCloseable` unit test without Spring |
| Test shutdown under multi-request load | Load/integration test with in-flight operations |

## 22. Four-Layer Practical Leak-Testing Process

### Layer A — Logic Invariants

Track:

```text
Resource OPENED
Resource CLOSED
Resource ACTIVE
```

Check after-close == baseline and opened delta == closed delta.

### Layer B — Lifecycle Hooks

Record controlled markers for:

```text
context.refresh.complete
resource.constructed
resource.used
context.closed.event
resource.stop
resource.destroy
context.close.return
```

These are **illustrative marker names**, not standard event names Spring Boot prints automatically.

Distinguish `ContextClosedEvent` from bean destruction: the event fires at the start of context closing; never assert all destructors have finished at the event milestone itself.

### Layer C — JVM and OS Metrics

Observe:

- Appropriate live platform threads.
- Executor termination.
- Open file descriptors/handles.
- Pool connections and socket states.
- Stabilized heap used, GC patterns, metaspace.
- Active scheduled tasks/subscriptions.
- Retained references in heap dumps.

### Layer D — Soak / Repeated Runs

Repeat 20, 50, 100 rounds in the same JVM. Evaluate:

- Did any round fail to return to baseline?
- Does active count grow by 1 on every round?
- Do slow-closing resources accumulate a backlog?
- Is there continuous growth **after warm-up**?
- Do error paths leave resources behind?
- Are measurements skewed by parallel test execution?

**Not every system metric must return to the exact same byte or thread count after every round**; what is mandatory is the lifecycle contract of resources owned by the test.

## 23. Before–After Scenarios

### 23.1. Wrong: Resource in a Static Singleton Outside Spring

```java
public final class UnsafeResourceHolder {

    private static final ExecutorService EXECUTOR =
            Executors.newSingleThreadExecutor();

    public static void submit(Runnable task) {
        EXECUTOR.execute(task);
    }
}
```

This class snippet needs `ExecutorService` and `Executors` imports. `EXECUTOR` is static, scoped to the classloader rather than per `ApplicationContext`. Closing the context **does not automatically shut down** an executor with no registered lifecycle callback.

If multiple contexts sequentially submit tasks to the static executor, the resource stays alive across contexts. With a static singleton executor, thread counts might **not grow per round**, yet it remains an **ownership/lifecycle mismatch** if the executor was meant to close when the context closes.

### 23.2. Right: Spring Owns the Resource Bean

```java
@Bean(destroyMethod = "close")
TrackedWorker trackedWorker() {
    return new TrackedWorker();
}
```

When the singleton bean is created cleanly, Spring has an explicit destructor to invoke on context close. This is the demo's pattern.

### 23.3. Right: Local Resource with `try-with-resources`

```java
try (InputStream input = Files.newInputStream(path)) {
    process(input);
}
```

This snippet needs `path`, `process`, and `InputStream`/`Files` imports; it represents a method-scoped resource, **not Spring-context-scoped**. Java guarantees `close()` runs upon leaving scope if initialization succeeded.

### 23.4. Wrong: Destructor Only Logs

```java
@PreDestroy
void onDestroy() {
    log.info("Closing resource");
    // Does not actually close executor, socket, or file.
}
```

This is a counter-example snippet. Logging "Closing" does not prove the resource was released. Tests must inspect real resource state.

### 23.5. Wrong: Calling `System.exit` Mid-Test Loop

If `System.exit(...)` terminates the JVM, the loop stops and the OS reclaims many resources. That **does not test whether Spring destroyed them properly**. Never call exit inside multi-context tests; use a separate process-level test only to verify exit codes.

## 24. Symptom-Based Diagnosis

| Symptom | Likely Cause | Check / Fix |
| --- | --- | --- |
| Worker active grows by 1 after every close | Executor lacks destructor or close failed | Check `@Bean(destroyMethod)`, shutdown/awaitTermination |
| Test passes when no bean was created | Lazy bean was never accessed | Request the bean and use the resource in context |
| File handles grow while opened/closed match | Tracker missed another file or fake close | Measure OS FDs, locate other file channels/streams |
| Opened grows, closed stays flat | Missing destroy callback | Check ownership, scope, and callbacks |
| Thread stays alive right after close | Async stop or task ignores interrupts | Bounded wait, task cancellation, thread dumps |
| Heap grows first few rounds then stabilizes | Warm-up/caches/JIT | Compare after plateau; do not assert exact heap |
| Metaspace grows on every DevTools restart | R1 classloaders may be retained | Heap dump, static caches, TCCL |
| Tests fail with port in use | Web server binding a port | Use non-web context or dynamic ports in integration tests |
| Hikari active=0 yet connections remain open | Pool not closed; idle connections remain | Track pool lifecycle and server sessions |
| Resource closed twice | Two owners closing or duplicate callback | Idempotent close, single clear owner |
| `@PreDestroy` doesn't run on very early startup failure | Bean never finished creation | Clean up at the allocation site |
| `close()` throws yet context returns | Framework may log cleanup error | Assert resource counters and error metrics |
| Test passes solo, fails in full suite | Shared static state/parallel tests/context cache | Isolate metrics, coordinate test execution |
| Context closed yet listener still receives events | External registry outside context | Unregister in destroy callback |
| JVM refuses to exit | Non-daemon thread outside lifecycle | Thread dump, trace executor owner |
| JVM exits cleanly yet resources leaked during runtime | OS reclaimed handles on process exit | Test multiple contexts inside one process |
| `System.gc()` does not shrink heap | JVM/GC semantics, strong references | Heap dump retaining paths |
| Temp file still exists | Not deleted, OS error, or retention policy | Close channel, delete file, handle suppressed errors |
| Increasing rounds doesn't reproduce leak | Leak occurs only on error path or under load | Add failure/async/soak scenarios |

### Prioritized Debugging Workflow

1. Identify resource type, owner, and post-close state.
2. Try 3 rounds first, printing counters after each round.
3. Verify the bean was genuinely instantiated and used.
4. Check `@Bean`, `@PreDestroy`, `DisposableBean`, or `SmartLifecycle`.
5. Confirm the destructor **completed cleanup** rather than just logging or signaling.
6. Run a negative control with `finally` cleanup to prove the test detects leaks.
7. Add failure-path tests before trusting production safety.
8. If counters pass while OS resources grow, look for untracked resources.
9. If heap/metaspace grows, use JFR/heap dumps to find retaining paths.
10. Re-run multiple rounds in the same JVM with production-like config.
11. Document root cause and fix at **the resource owner**, never by resetting counters.
12. Keep tests self-cleaning even when assertions fail.

## 25. Measurement Tests Must Not Harm the Environment

A leak test can consume file handles, ports, or threads when deliberately triggering failures. Therefore:

- Run in isolated dev/CI environments, never on user-serving processes.
- Start with small round counts.
- Set finite timeouts.
- Never omit cleanup on an intentional leak just to "observe longer".
- For negative controls, keep the resource reference and close it in `finally`.
- Use temporary files and delete them afterward; never open real data files.
- Never log tokens, passwords, JDBC URLs with credentials, or sensitive data.
- Never test OS permissions with destructive actions outside test directories.
- For child processes, enforce timeouts and clean up process trees.
- For cloud resources, use naming/TTLs and dedicated cleanup policies.

In the demo, worker threads are daemon to reduce the risk of hanging the test JVM, yet tests still **must verify shutdown**. Never treat "daemon thread" as an excuse to ignore leaks.

## 26. Extension Exercises

### Exercise 1: Inducing a Leak with Empty `destroyMethod`

Based on the `MissingDestroyConfiguration` test: why does `@Bean(destroyMethod = "")` leave `activeBefore+1` after context close?

**Answer:** custom destroy-method inference for `close` is disabled, so the `TrackedWorker` bean gets no automatic close callback via that mechanism. The test calls close in `finally` to avoid causing a real leak.

### Exercise 2: Open/Close Round Counts

Change `rounds` to 20. Predict the final line.

**Answer** (when running in a fresh process with no interference):

```text
PASS openedWorkers=20 closedWorkers=20 openedFiles=20 closedFiles=20
```

Note that if `main` is called multiple times inside **the same JVM** where static counters retain earlier counts, asserting total equals `rounds` must switch to checking **deltas from baseline**, as the JUnit test already does.

### Exercise 3: Adding a Second Bean to the Context

Add a second `TrackedWorker` bean with a different name and observe what happens to the `worker.active==1` assertion.

**Answer:** if both are created, active count will be 2. Tests must update acceptance criteria to match the actual resource count, **never forcing the counter to 1** when the design creates two resources.

### Exercise 4: Lazy Resources

Annotate the temporary file bean with `@Bean @Lazy` and omit `context.getBean(TrackedTempFile.class)`. Why can the file counter stay 0 while the context is active?

**Answer:** the lazy bean has not been instantiated; cleanup checks are meaningless for resources that never existed. Add a dedicated test forcing creation then close if verifying its destructor.

### Exercise 5: Startup Failure After Resource Creation

Using `FailingConfiguration`: if `failingBean` drops the `TrackedWorker resource` parameter, what can change?

**Answer:** if no other bean forces `resource` to be created first, resource creation might still happen in pre-instantiation order, yet **you must not rely on that incidental order**. The dependency parameter guarantees `resource` is created before the failure occurs.

### Exercise 6: Failing File Close

Simulate `TrackedTempFile.close()` throwing `IOException`. What should the test assert?

**Answer:** it must not report cleanup success. Preserve the cleanup error, inspect actual file handles/paths, and implement proper retry/recovery. Counters must not decrement merely to pass tests.

### Exercise 7: `System.gc` and Heap

After 50 rounds, `totalMemory()` is higher than initially while `active=0` for all resources. Is that definitely a leak?

**Answer:** no. Inspect retained objects, post-GC heap used, plateaus, OS handles, and classloader references.

### Exercise 8: HikariCP

Replace the temporary file bean with a `HikariDataSource` against a test DB. Write tests comparing active/idle/pending connections and the number of pools actually closed. **Do not check only `activeConnections == 0`.**

### Exercise 9: DevTools and Static Registries

Create a listener in the restart classloader, register it in a static registry in the base loader, and forget to unregister it. After several DevTools restarts, how do you prove R1 is still retained?

**Answer:** use heap dumps/retaining paths and inspect the static registry/thread TCCLs; `context.close()` alone does not clear a static reference outside the context.

### Exercise 10: Testing Async Task Stopping

Create a scheduled task waiting on a latch. When the context closes, the stop callback must wait for the task to stop or time out. Write tests using `CountDownLatch`/`awaitTermination` with deadlines; avoid uncontrolled `Thread.sleep`.

## 27. Checklist Before Concluding "No Leaks"

- [ ] Created a fresh context in **every round within the same JVM**.
- [ ] `ConfigurableApplicationContext.close()` called inside `try-with-resources`/`finally`.
- [ ] Every resource has a clear owner.
- [ ] Every singleton resource bean has an appropriate destructor.
- [ ] Did not accidentally set `destroyMethod = ""` on beans relying solely on `close`.
- [ ] Beans under test were genuinely instantiated and used.
- [ ] Counters measure active/opened/closed at baseline/inside/after-close.
- [ ] After each round, active counts return to baseline.
- [ ] Total opened delta equals closed delta.
- [ ] Executors have bounded shutdown and report errors when failing to terminate.
- [ ] `FileChannel`/streams/sockets are genuinely closed, not merely logged.
- [ ] Test temporary files are deleted per policy.
- [ ] Negative control proves tests can detect missing cleanup.
- [ ] Negative control cleans up after itself in `finally`.
- [ ] Refresh failure tested after a resource has already been created.
- [ ] Never expect destructors to run on beans that failed before finishing creation.
- [ ] Tests sharing static state do not run concurrently without isolation.
- [ ] Never confuse `@SpringBootTest` context caching with multiple fresh contexts.
- [ ] Never use `System.gc()` or exact heap bytes as the sole assertion.
- [ ] If using a DB, also verify pool shutdown and idle connections.
- [ ] If using threads, verify termination rather than merely counting thread names.
- [ ] If using external listeners, verify unregistration after close.
- [ ] If using DevTools, include dedicated restart classloader tests.
- [ ] Bounded time and resource limits on soak tests.
- [ ] Zero real leaked resources left behind when tests finish.
- [ ] Dedicated diagnostics for OS/JVM metrics growing past warm-up.
- [ ] Error paths tested, not just successful startup/close.

## 28. Summary

- **Closing a context does not mean every resource in the JVM is automatically cleaned up.** Spring manages beans/instances within its lifecycle; out-of-container resources, static caches, prototypes, or failed allocations before bean return need dedicated ownership and cleanup.
- **To test leaks across multiple contexts, open and close repeatedly inside the same JVM.** Re-running a new process does not detect references or resources surviving across context closes.
- **Measure systematically:** baseline → inside context → after `close()`. Verify active returns to baseline and opened/closed balance.
- **Practicing with `TrackedWorker` and `TrackedTempFile`** exercises both a thread-owning executor and a file handle. Beans register `@Bean(destroyMethod="close")` and are verified via loops and JUnit.
- **Negative controls matter:** deliberately disable destroy-method inference in an isolated test, confirm the leak is detected, and clean up in `finally`.
- **Test startup failures too:** completed singletons get destruction callbacks; half-opened resources inside constructors/factories require rollback at the allocation site.
- **Separate real leaks from JVM warm-up:** counters, OS metrics, and retaining paths beat a single heap snapshot or `System.gc()`.
- **Scaling to production:** HikariCP, HTTP clients, schedulers, listeners, TCCLs, static caches, DevTools restarts, and shutdown timeouts all require dedicated checks.

### Official References

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, context caching, and testing infrastructure.
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing): `ApplicationContextRunner` and context testing.
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): startup, shutdown, and lifecycle.
- [Spring Framework — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `@PreDestroy`, `DisposableBean`, and destroy-method inference.
- [Spring Framework — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): `@Bean(destroyMethod)`, `close`/`shutdown`.
- [Spring Framework 6.1 — ConfigurableApplicationContext API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html): `close()`, `stop()`.
- [Java 17 — ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown and awaitTermination.
- [Java 17 — AutoCloseable API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): resource cleanup contract.
- [Java 17 — FileChannel API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): file channel lifecycle.
- [Java 17 — ManagementFactory / ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html): thread/OS metrics.
