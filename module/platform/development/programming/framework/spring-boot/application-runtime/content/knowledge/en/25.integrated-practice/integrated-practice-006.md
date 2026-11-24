# Building a Background Component with SmartLifecycle Using Two Dependent Phases

## 1. Practice Objectives

A Spring Boot application sometimes has a **background component** that must only start after an infrastructure component is ready. Examples: a message consumer must wait for a broker connection; a polling worker uses a database pool; a stream processor depends on a client or cache.

The challenge is not just **starting in the right order**. When the application stops, the worker must **stop accepting new work and finish in-flight work before the infrastructure closes**. If the order is reversed, the worker may use a connection that has already been shut down; data may be lost or half-processed.

This lab builds **two dependent `SmartLifecycle` beans**:

1. `Gateway` — simulates an opened infrastructure resource, **phase 100**.
2. `BackgroundWorker` — simulates a consumer running on a background thread that requires `Gateway`, **phase 200**.

The outcome we want to verify:

```text
STARTUP
    Gateway.start()       (phase=100)
          |
          v
    BackgroundWorker.start() (phase=200)
          |
          v
    ApplicationReadyEvent

WHILE RUNNING
    Main requests a job
          |
          v
    BackgroundWorker calls Gateway.handle(...)
          |
          v
    Main receives completed Future

NORMAL CLOSE
    ContextClosedEvent
          |
          v
    BackgroundWorker.stop(Runnable)   (phase=200)
      -> stop accepting work, wait for worker exit, invoke callback
          |
          v
    Gateway.stop(Runnable)            (phase=100)
          |
          v
    @PreDestroy on singletons
          |
          v
    context.close() returns
```

This is an **integrated practice lab** for Spring Boot Application Runtime. It combines context lifecycle, `SmartLifecycle`, phases, bean dependencies, background threads, `CompletableFuture`, shutdown callbacks, events, and destruction. The demo uses an **in-memory** gateway without connecting to a real broker or database, so the sequence can be proven via output independent of network or machine speed.

**Versions:** Java 17+, Spring Boot 3.3.13, Spring Framework 6.1.x, Gradle Groovy. In this lab, phases 100 and 200 are **application-chosen values**, not two special phases reserved by Spring.

## 2. Understanding Three Lifecycles Before Coding

Distinguish between:

| Concept | When Does It Occur? | Purpose |
| --- | --- | --- |
| **Bean creation / initialization** | Spring instantiates objects, injects dependencies, invokes `@PostConstruct` | Prepare object configuration and state |
| **Lifecycle start / running** | `LifecycleProcessor.onRefresh()` calls `SmartLifecycle.start()` if auto-start | Start component activity |
| **Boot started / ready** | `SpringApplication` publishes started/ready events around runners | Mark application startup milestones |
| **Lifecycle stop** | During normal `context.stop()` or `context.close()` | Stop activity by phase/dependency |
| **Singleton destruction** | When context closes and destroys eligible beans | Reclaim resources / `@PreDestroy` |

A singleton can be **created but not yet running**. Conversely, during shutdown, a bean still exists in the container while lifecycle stop is executing. Therefore, do not treat constructors or `@PostConstruct` as a signal that "the consumer is allowed to receive messages" if the underlying resource is not running yet.

`SmartLifecycle` is designed for the container to coordinate components with a `start/stop/running` concept. This is a **Spring Framework**-level lifecycle contract, not specific to Spring Boot.

### 2.1. Distinguishing `Lifecycle` and `SmartLifecycle`

`Lifecycle` defines:

```java
void start();
void stop();
boolean isRunning();
```

`SmartLifecycle` extends `Lifecycle` and `Phased`, adding:

```java
boolean isAutoStartup();
int getPhase();
void stop(Runnable callback);
```

The two snippets above are **abbreviated signatures for learning the API**, not standalone Java files. The lab's classes will implement all appropriate methods in full.

- `isAutoStartup()`: whether to start automatically on `ApplicationContext.refresh()`; the default on `SmartLifecycle` in Spring 6.1 is `true`.
- `getPhase()`: orders start/stop. Smaller values start earlier; larger values stop earlier.
- `stop(Runnable callback)`: lets a component stop asynchronously and signal **actual completion** back to `LifecycleProcessor`.
- `isRunning()`: reflects the **actual state published by the implementation**; never return `true` unconditionally.

`SmartLifecycle.DEFAULT_PHASE` in Spring Framework 6.1 equals `Integer.MAX_VALUE`. Without overriding `getPhase()`, a typical `SmartLifecycle` sits at a very high phase: starting late and stopping early. In systems with clear dependencies, **choosing explicit phases** is usually easier to reason about. Plain `Lifecycle` implementations not implementing `Phased` are treated as phase 0 by the processor.

### 2.2. How Phase Determines Order

| Component | Phase | On Start | On Stop |
| --- | ---: | --- | --- |
| Infrastructure `Gateway` | 100 | **First** | **Second** |
| Consumer `BackgroundWorker` | 200 | **Second** | **First** |

General rule:

```text
START:     low phase ---------> high phase
STOP:      high phase --------> low phase
```

This reflects the dependency principle: the consumer **must have the gateway running before operating**, and the gateway **must remain alive while the consumer is stopping**.

### 2.3. `@DependsOn` and Phase: Two Layers of Assurance

We declare the worker bean with dependency injection and `@DependsOn("gateway")`:

```java
@Bean
@DependsOn("gateway")
BackgroundWorker worker(Gateway gateway, Trace trace) {
    return new BackgroundWorker(gateway, trace);
}
```

This is a snippet inside a configuration class, not standalone. Two points:

1. The `Gateway gateway` parameter indicates the worker actually needs the gateway object; without the gateway, the worker cannot be constructed.
2. `@DependsOn("gateway")` expresses an explicit bean definition relationship: **the dependent starts after its dependency and stops before its dependency**, even if phases conflict.

In the demo, phases 100/200 and the dependency align in **the same direction**, making it easy for readers to verify. If phases conflict, Spring Framework prioritizes explicit depends-on relationships when coordinating the related beans.

**Do not confuse:** `@DependsOn` does not replace passing `Gateway` into the constructor. It is lifecycle/initialization relationship metadata; the worker still needs the gateway reference to call `handle(...)`. Conversely, phase is not a tool for choosing constructor or `@Bean` method call order; those are also governed by the dependency graph.

## 3. Designing Two Background Components with Clear Ownership

### 3.1. `Gateway` (phase 100)

The simulated infrastructure is responsible for:

- `start()`: marks the resource open/available.
- `handle("sample")`: processes a message and returns an acknowledgement; rejects if already stopped.
- `stop()`: stops accepting I/O for the gateway.
- `@PreDestroy`: defensive cleanup if an abnormal shutdown bypasses normal stop.

In real systems, Gateway may be a broker producer, TCP client, database connection, or API client. However, if using a library with its own lifecycle, follow that library's contract; `SmartLifecycle` does not turn network operations into durable transactions.

### 3.2. `BackgroundWorker` (phase 200)

The worker is responsible for:

- `start()`: starts only when the gateway is running; spawns a background thread **owned by the worker**.
- `submitOnce()`: signals the thread to process **one job** and returns a `CompletableFuture<String>` so the caller can wait for the result.
- `stop(Runnable)`: stops accepting new jobs, wakes the worker if no job has arrived yet, lets any in-flight job finish, and **invokes the callback only after the worker exits**.
- `stop()`: provides a synchronous variant for callers wanting an explicit stop; waits on the callback with a deadline.
- `@PreDestroy`: defensively calls stop if needed, then records destruction.

This is a **one-shot worker** for deterministic experiments: it accepts only one message per context lifetime. A multi-message production consumer needs a queue, concurrency limits, state checks, and restartability by recreating runtime resources; a later section details how to extend it.

### 3.3. Separating "Submitted" from "Completed"

`submitOnce()` signals a job request and returns a Future. It **does not guarantee the job has completed at the moment it returns**. In `main` we call `future.get(5, TimeUnit.SECONDS)` to wait for the result or receive an exception/timeout.

Thus tests do not conflate:

- Thread `start()`.
- A job being **submitted** to the worker.
- Job **execution** via the gateway.
- Future **completing successfully**.
- Component **fully stopping**.

`stop(Runnable)` must likewise distinguish **stop requested** from **stop completed**, because Spring must wait for the callback before moving on to stop lower-phase dependencies.

## 4. Practice Project Structure

Create a Gradle Groovy project. Full layout:

```text
two-phase-lifecycle-lab/
├── build.gradle
├── settings.gradle
└── src/
    ├── main/
    │   ├── java/com/example/twophase/
    │   │   └── TwoPhaseLifecycleApplication.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/twophase/
            └── TwoPhaseLifecycleApplicationTest.java
```

`Trace`, `Gateway`, `BackgroundWorker`, and `LifecycleEvents` are placed as **nested static classes** inside the application file so learners only need to copy one Java file. The test uses those exact classes from the same package; no component scan or bean file is left out.

The project requires **JDK 17+** and a Gradle Wrapper compatible with the chosen JVM. If there is no Gradle Wrapper yet, generate one using an installed Gradle; `gradlew` commands below assume the wrapper is present.

### 4.1. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot starter provides `ApplicationContext`, annotations, and JDK logging integration needed for the demo. Test starter provides JUnit Jupiter and AssertJ.

**`spring-boot-starter-web` is not needed**, because the lab verifies background component lifecycles, not an HTTP server. A context without Tomcat keeps the trace free from web server events.

### 4.2. `settings.gradle`

```groovy
rootProject.name = 'two-phase-lifecycle-lab'
```

### 4.3. `application.properties`

Create `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=ERROR

# Each phase waits up to 10 seconds when stopping.
spring.lifecycle.timeout-per-shutdown-phase=10s
```

The two lab phases are **distinct** (100 and 200). The timeout applies to `DefaultLifecycleProcessor` waiting for each phase's callbacks; it does not automatically set timeouts on I/O inside the worker. The demo explicitly uses a Future timeout in main and a deadline on synchronous stop to avoid an example that "waits forever".

### 4.4. Preparing the Right Package

Create **`src/main/java/com/example/twophase/TwoPhaseLifecycleApplication.java`**. The entire program below resides in this file; the public class name matches the filename, and the package matches the directory.


## 5. Complete Java File: Gateway Phase 100 and BackgroundWorker Phase 200

```java
package com.example.twophase;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class TwoPhaseLifecycleApplication {

    public static void main(String[] args) throws Exception {
        Trace trace;

        try (ConfigurableApplicationContext context =
                SpringApplication.run(TwoPhaseLifecycleApplication.class, args)) {

            trace = context.getBean(Trace.class);
            BackgroundWorker worker = context.getBean(BackgroundWorker.class);

            trace.record("04 main: submit sample");
            String result = worker.submitOnce().get(5, TimeUnit.SECONDS);

            if (!"ACK:sample".equals(result)) {
                throw new IllegalStateException("Unexpected result: " + result);
            }
            trace.record("06 main: job observed");
        }

        // try-with-resources has closed the Spring context here.
        trace.record("12 main: context closed");

        List<String> expected = List.of(
                "01 gateway.start phase=100",
                "02 worker.start phase=200",
                "03 ApplicationReadyEvent",
                "04 main: submit sample",
                "05 gateway: handled sample",
                "06 main: job observed",
                "07 ContextClosedEvent",
                "08 worker.stop completed phase=200",
                "09 gateway.stop phase=100",
                "10 worker.@PreDestroy",
                "11 gateway.@PreDestroy",
                "12 main: context closed");

        if (!trace.snapshot().equals(expected)) {
            throw new IllegalStateException(
                    "Unexpected lifecycle trace: " + trace.snapshot());
        }
        System.out.println("CHECK PASS");
    }

    @Bean
    Trace trace() {
        return new Trace();
    }

    @Bean("gateway")
    Gateway gateway(Trace trace) {
        return new Gateway(trace);
    }

    @Bean("worker")
    @DependsOn("gateway")
    BackgroundWorker worker(Gateway gateway, Trace trace) {
        return new BackgroundWorker(gateway, trace);
    }

    @Bean
    LifecycleEvents lifecycleEvents(Trace trace) {
        return new LifecycleEvents(trace);
    }

    // Collector resides in context, while main retains a reference after close.
    static final class Trace {
        private final List<String> items = new ArrayList<>();

        synchronized void record(String value) {
            items.add(value);
            System.out.println(value);
        }

        synchronized List<String> snapshot() {
            return List.copyOf(items);
        }
    }

    // Infrastructure component; must start before worker.
    static final class Gateway implements SmartLifecycle {
        private final Trace trace;
        private volatile boolean running;

        Gateway(Trace trace) {
            this.trace = trace;
        }

        @Override
        public synchronized void start() {
            if (running) {
                return;
            }
            running = true;
            trace.record("01 gateway.start phase=100");
        }

        @Override
        public synchronized void stop() {
            if (!running) {
                return;
            }
            running = false;
            trace.record("09 gateway.stop phase=100");
        }

        @Override
        public void stop(Runnable callback) {
            try {
                stop();
            } finally {
                callback.run();
            }
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public int getPhase() {
            return 100;
        }

        synchronized String handle(String value) {
            if (!running) {
                throw new IllegalStateException("Gateway is stopped");
            }
            trace.record("05 gateway: handled " + value);
            return "ACK:" + value;
        }

        @PreDestroy
        public void destroy() {
            if (isRunning()) {
                stop(); // Defensive fallback if cleanup bypasses normal stop.
            }
            trace.record("11 gateway.@PreDestroy");
        }
    }

    // Background component requiring Gateway to remain active.
    static final class BackgroundWorker implements SmartLifecycle {
        private final Gateway gateway;
        private final Trace trace;

        private final CountDownLatch jobRequested = new CountDownLatch(1);
        private final CountDownLatch shutdownRequested = new CountDownLatch(1);
        private final CompletableFuture<String> result =
                new CompletableFuture<>();

        private volatile boolean running;
        private volatile boolean stopping;
        private volatile Runnable shutdownCallback;
        private Thread workerThread;

        BackgroundWorker(Gateway gateway, Trace trace) {
            this.gateway = gateway;
            this.trace = trace;
        }

        @Override
        public synchronized void start() {
            if (running) {
                return;
            }
            if (workerThread != null) {
                throw new IllegalStateException(
                        "This demo worker is one-shot and cannot restart");
            }
            if (!gateway.isRunning()) {
                throw new IllegalStateException(
                        "Gateway must be started before worker");
            }

            running = true;
            trace.record("02 worker.start phase=200");

            workerThread = new Thread(this::workLoop, "two-phase-worker");
            workerThread.setDaemon(true);
            workerThread.start();
        }

        CompletableFuture<String> submitOnce() {
            if (!running || stopping) {
                throw new IllegalStateException("Worker is not accepting jobs");
            }
            jobRequested.countDown();
            return result;
        }

        private void workLoop() {
            try {
                jobRequested.await();

                if (!stopping) {
                    try {
                        result.complete(gateway.handle("sample"));
                    } catch (RuntimeException ex) {
                        result.completeExceptionally(ex);
                    }
                } else {
                    result.cancel(false);
                }

                // Keep worker alive until lifecycle stop.
                shutdownRequested.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                result.completeExceptionally(ex);
            } finally {
                running = false;
                trace.record("08 worker.stop completed phase=200");

                Runnable callback = shutdownCallback;
                if (callback != null) {
                    callback.run();
                }
            }
        }

        // Spring invokes this variant via DefaultLifecycleProcessor.
        @Override
        public void stop(Runnable callback) {
            if (!running) {
                callback.run();
                return;
            }

            shutdownCallback = callback;
            stopping = true;            // Reject new jobs.
            jobRequested.countDown();   // Wake worker if no job arrived yet.
            shutdownRequested.countDown();

            // DO NOT call callback.run() here.
            // Worker will invoke callback after exiting workLoop().
        }

        // Synchronous variant for callers invoking stop() directly.
        @Override
        public void stop() {
            CountDownLatch finished = new CountDownLatch(1);
            stop(finished::countDown);
            try {
                if (!finished.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Worker stop timed out");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Interrupted while stopping worker", ex);
            }
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public int getPhase() {
            return 200;
        }

        @PreDestroy
        public void destroy() {
            if (isRunning()) {
                stop();
            }
            trace.record("10 worker.@PreDestroy");
        }
    }

    static final class LifecycleEvents {
        private final Trace trace;

        LifecycleEvents(Trace trace) {
            this.trace = trace;
        }

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            trace.record("03 ApplicationReadyEvent");
        }

        @EventListener
        public void onClosed(ContextClosedEvent event) {
            trace.record("07 ContextClosedEvent");
        }
    }
}
```

### 5.1. Why Is This Source a Self-Contained Example?

- One public top-level class named exactly `TwoPhaseLifecycleApplication`, in package `com.example.twophase`.
- Supporting classes `Trace`, `Gateway`, `BackgroundWorker`, and `LifecycleEvents` reside in the same Java file.
- Beans are registered via `@Bean` methods in the `@SpringBootApplication` class, needing no extra `@ComponentScan` or XML.
- `@DependsOn("gateway")` points to the declared bean named `gateway`.
- `Gateway` and `BackgroundWorker` both implement `SmartLifecycle`; `start`, `stop`, `isRunning`, `isAutoStartup`, and `getPhase` have complete signatures.
- `@PreDestroy` uses Spring Boot 3.x's proper `jakarta.annotation` namespace.
- `CountDownLatch` and `CompletableFuture` belong to JDK 17; no external concurrency library is needed.
- `LifecycleEvents` is a context-managed singleton, so its `@EventListener` methods receive the application's events.
- The code creates no web listener, calls no database or network API, and requires no Spring thread scheduler.

### 5.2. What Happens During Context Refresh?

1. Spring creates/injects required beans according to the dependency graph.
2. `Gateway` and `BackgroundWorker` exist as objects, initially with `running=false`.
3. `DefaultLifecycleProcessor.onRefresh()` finds `SmartLifecycle` beans that require auto-start.
4. Phase 100 starts before phase 200: `Gateway.start()` sets `running=true`.
5. `BackgroundWorker.start()` checks `gateway.isRunning()`, then spawns a daemon thread to wait for a job.
6. Boot proceeds to `ApplicationStartedEvent`, any runners, and then `ApplicationReadyEvent`.
7. `main` only submits a job after `SpringApplication.run` returns.

**Why doesn't the worker process a job before line 04?** Because the thread waits on `jobRequested.await()`; only `submitOnce()` calls `jobRequested.countDown()`. Regardless of whether the CPU scheduler runs the thread earlier or later, no job processing log occurs before that signal.

### 5.3. What Happens When Processing a Job?

- Main logs line 04 and calls `submitOnce()`.
- `submitOnce()` counts down `jobRequested` and returns `CompletableFuture<String>`.
- The worker thread proceeds to call `gateway.handle("sample")`. Gateway verifies `running`, logs line 05, and returns `ACK:sample`.
- The worker calls `result.complete("ACK:sample")`.
- Main waiting in `get(5, SECONDS)` wakes up, verifies the result, and logs line 06.

This is a synchronization relationship **that does not rely on sleep**: the CompletableFuture cannot complete normally in this code before gateway handle finishes. `CountDownLatch` and Future also establish memory visibility per the Java Concurrency API.

### 5.4. What Happens on `context.close()`?

Because `main` uses try-with-resources, exiting the block after line 06 causes Java to call `context.close()`.

- Spring publishes `ContextClosedEvent` when normal close begins → line 07.
- The lifecycle processor picks the higher phase first → calls `BackgroundWorker.stop(Runnable)`.
- The worker sets `stopping=true`, releases the shutdown latch, and **does not invoke the callback immediately**.
- The worker thread exits `workLoop()`. In `finally`, it logs line 08 and invokes `shutdownCallback.run()`.
- The processor receives notification that phase 200 has stopped and proceeds to phase 100.
- `Gateway.stop()` logs line 09. No worker is using the gateway anymore.
- During singleton destruction, `BackgroundWorker.@PreDestroy` logs line 10, followed by `Gateway.@PreDestroy` logging line 11 per the dependency relationship.
- `context.close()` returns; main logs line 12, validates the trace, and prints `CHECK PASS`.

**The most important point:** the worker **does not** report stop complete at the instant stop is requested. Spring waits for the callback after the worker thread reaches `finally`, so the lower-phase gateway stays alive while the worker finishes stopping.

### 5.5. Why Also Include `@PreDestroy`?

`SmartLifecycle.stop(...)` coordinates **stopping active operations** in order. `@PreDestroy` handles **cleanup when singletons are destroyed**. A bean may need both: for example, stopping message intake and draining first, then closing remaining auxiliary resources.

In the demo, `@PreDestroy` calls `stop()` **only if still running** as a defensive measure in case bootstrap fails midway or a special shutdown path runs. On the normal close path, `stop` has already completed, so the destroy callback only logs.

Do not treat `@PreDestroy` as a replacement for `stop(Runnable)`: if you wait until destruction to stop a consumer, Gateway may already be undergoing destruction and the worker could touch a closed resource.

## 6. Running the Program and Predicting the Result

### 6.1. Windows PowerShell

```powershell
.\gradlew.bat bootRun
```

### 6.2. macOS/Linux

```bash
./gradlew bootRun
```

JDK 17+ with a compatible Gradle Wrapper is required. Run from the project root, ensuring Gradle resolves Spring Boot 3.3.13 and its dependencies. Do not run commands inside `src/main/java`.

Given the exact source and a normal environment, **lines printed by `Trace.record` and `System.out.println` in this source** appear in order:

```text
01 gateway.start phase=100
02 worker.start phase=200
03 ApplicationReadyEvent
04 main: submit sample
05 gateway: handled sample
06 main: job observed
07 ContextClosedEvent
08 worker.stop completed phase=200
09 gateway.stop phase=100
10 worker.@PreDestroy
11 gateway.@PreDestroy
12 main: context closed
CHECK PASS
```

Gradle may print additional task/build lines. Because `logging.level.root=ERROR`, normal Boot startup logs are suppressed; the verification output only lists lines **explicitly printed by the lesson's code**, without claiming the entire console has only 13 lines across every launcher.

### 6.3. Why Is the Order Stable?

| Milestone | Guaranteed Relationship |
| --- | --- |
| 01 before 02 | Phase 100 starts before phase 200; worker also checks gateway running |
| 02 before 03 | `SmartLifecycle` auto-starts during context refresh; Boot ready event arrives afterward |
| 03 before 04 | `SpringApplication.run` publishes the Ready event before returning on a successful startup path |
| 04 before 05 | Main logs before opening the `jobRequested` latch |
| 05 before 06 | Worker completes `CompletableFuture` after gateway.handle; main calls `get` before logging |
| 07 before 08 | `ContextClosedEvent` precedes normal `LifecycleProcessor.onClose()` |
| 08 before 09 | Phase 200 only invokes callback when worker exits; only then does phase 100 stop |
| 09 before 10 | Lifecycle stop precedes normal singleton destruction |
| 10 before 11 | Worker is declared dependent on Gateway; dependent bean destroys before its dependency |
| 11 before 12 | `context.close()` finishes before exiting try-with-resources |

The table describes **ordering relationships in this exact program**, not a global order across arbitrary Java threads, arbitrary Spring beans, or arbitrary OSes. Adding a custom asynchronous event multicaster or complex dependencies may require redesigning the trace; do not copy ordering assertions to other systems without inspecting context.

### 6.4. A Note on Daemon Threads

The demo's thread is marked `setDaemon(true)`. This prevents the example from accidentally keeping the JVM alive forever if a test fails; it does **not** mean daemon threads are guaranteed to finish before process exit.

In the demo, main awaits the Future, and `context.close()` awaits `SmartLifecycle.stop(Runnable)` completion. Thus lifecycle manages controlled worker shutdown; the daemon flag does not replace that logic. For long-lived services, let the container manage executors/schedulers or proper worker ownership rather than relying on daemon threads as a shutdown strategy.

### 6.5. Why Not Use `Thread.sleep` to Wait?

Code like:

```java
worker.submitOnce();
Thread.sleep(100);
context.close();
```

is an **anti-pattern**. On a busy machine, the job might not even be scheduled within 100 ms; on a fast machine, it finishes early. `sleep` merely guesses timing instead of proving success.

In the full source, `CompletableFuture.get(5, TimeUnit.SECONDS)` checks **the actual result**, has a deadline, and can propagate failures. On stop, the callback signals **actual exit** rather than logging "stop requested" and immediately closing the dependency.


## 7. Automated Test: Asserting Phase and Shutdown Trace

Since this lab has a specific milestone sequence, add a JUnit 5 test running a real `SpringApplication` to verify order. It reuses the project and source above without creating separate beans.

Create **`src/test/java/com/example/twophase/TwoPhaseLifecycleApplicationTest.java`**:

```java
package com.example.twophase;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

class TwoPhaseLifecycleApplicationTest {

    @Test
    void workerStartsAfterGatewayAndStopsBeforeGateway() throws Exception {
        SpringApplication app =
                new SpringApplication(TwoPhaseLifecycleApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        TwoPhaseLifecycleApplication.Trace trace;

        try (ConfigurableApplicationContext context = app.run()) {
            trace = context.getBean(
                    TwoPhaseLifecycleApplication.Trace.class);

            var gateway = context.getBean(
                    TwoPhaseLifecycleApplication.Gateway.class);
            var worker = context.getBean(
                    TwoPhaseLifecycleApplication.BackgroundWorker.class);

            assertThat(gateway.isRunning()).isTrue();
            assertThat(worker.isRunning()).isTrue();

            trace.record("04 main: submit sample");
            assertThat(worker.submitOnce().get(5, TimeUnit.SECONDS))
                    .isEqualTo("ACK:sample");
            trace.record("06 main: job observed");

            assertThat(trace.snapshot()).containsExactly(
                    "01 gateway.start phase=100",
                    "02 worker.start phase=200",
                    "03 ApplicationReadyEvent",
                    "04 main: submit sample",
                    "05 gateway: handled sample",
                    "06 main: job observed");
        }

        // try-with-resources closed the context.
        trace.record("12 main: context closed");

        assertThat(trace.snapshot()).containsExactly(
                "01 gateway.start phase=100",
                "02 worker.start phase=200",
                "03 ApplicationReadyEvent",
                "04 main: submit sample",
                "05 gateway: handled sample",
                "06 main: job observed",
                "07 ContextClosedEvent",
                "08 worker.stop completed phase=200",
                "09 gateway.stop phase=100",
                "10 worker.@PreDestroy",
                "11 gateway.@PreDestroy",
                "12 main: context closed");
    }
}
```

The code uses `var` (supported since Java 10) to avoid long nested static class names in the test. Because the test sits in the same `com.example.twophase` package, it can access the demo's package-private nested classes and methods.

### 7.1. Running the Test

macOS/Linux:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

To run only the created test:

```bash
./gradlew test --tests "com.example.twophase.TwoPhaseLifecycleApplicationTest"
```

If assertions hold, the Gradle `test` task succeeds. No guarantee is made that test runner stdout formatting is identical across every Gradle version; the strings inside `containsExactly` are the primary verification result.

### 7.2. Why Use `SpringApplication` Instead of `ApplicationContextRunner`?

`ApplicationContextRunner` also creates and refreshes an `ApplicationContext`, so it can test `SmartLifecycle.start()`, `stop(Runnable)`, and `ContextClosedEvent`. However, it **does not invoke `SpringApplication.run`**, so it does not automatically emit `ApplicationReadyEvent`. This section's test wants to verify both **context lifecycle** and **Boot's Ready milestone**, so running a real `SpringApplication` with `WebApplicationType.NONE` fits the scope.

If you want to test **only** phase order and destruction callbacks, you can use `ApplicationContextRunner` in a unit/auto-config test; omit assertions based on `ApplicationReadyEvent` or test that separately.

### 7.3. Why Doesn't the Test Use `Thread.sleep`?

It awaits `Future.get(timeout)`, which is tied to computation completion. `stop(Runnable)` coordinates with the lifecycle processor to guarantee phase 200 finishes before phase 100 is stopped. Tests running under varying scheduler timings still preserve **relative ordering**.

Do not assert "worker thread ID must be 42", "job completes in under 5 ms", or "phase 200 thread always gets CPU before ready event". Those are not contracts guaranteed by `SmartLifecycle`.

### 7.4. Testing the Shutdown Path When No Job Arrived

Extension exercise: start the Spring context **without calling `submitOnce()`**, then close immediately. In the source, `stop(Runnable)` releases `jobRequested` to wake the worker; `stopping=true` causes the thread to **skip the job** and exit rather than blocking forever on the latch. Outcome:

- No `05 gateway: handled sample` line.
- No `06 main: job observed` line.
- `worker.stop completed phase=200` still precedes `gateway.stop phase=100`.

When testing this variant, drop the default assertions for lines 04–06 and check the remaining milestones. This proves shutdown must work even when the worker **never received any work**.

## 8. Deep Dive into `SmartLifecycle.stop(Runnable)`

### 8.1. Why Must the Callback Fire Only After Stopping for Real?

Spring Framework 6.1 specifies that `DefaultLifecycleProcessor` uses `stop(Runnable)` and waits for callbacks from components in a phase to know when that shutdown phase is complete. For an asynchronous worker:

```text
Context closing thread              Background worker thread
----------------------              ------------------------
stop(callback) called
  |
  +-- stopping=true
  +-- release shutdown latch ----> sees shutdown signal
  |                                |
  |                                +--> finishes in-flight work
  |                                +--> exits workLoop
  |                                +--> running=false
  |                                +--> callback.run()
  |                                         |
  +<-------- callback acknowledged --------+
  |
  +--> moves to lower phase
  +--> gateway.stop()
```

If the code invoked the callback right after `shutdownRequested.countDown()`, that would only be **stop requested**, not **stop completed**. The lifecycle processor could stop the gateway while the worker was still processing a message.

### 8.2. When Must the Callback Run?

By contract, when `DefaultLifecycleProcessor` invokes `SmartLifecycle.stop(Runnable)` on a running component, the implementation must invoke the callback **once stopping finishes**. If the component is already stopped, the implementation may invoke the callback immediately so the processor does not have to wait.

In the demo:
- `stop(Runnable)` when running: saves callback, sets `stopping`, releases latches; worker invokes callback in `finally`.
- `stop(Runnable)` when not running: callback runs immediately.
- `stop()`: uses a caller latch to wait for the callback; must not skip the callback or return before stopping when a caller requests the synchronous variant.

**Intentional demo limitation:** It is a single-thread, single-job worker assuming one lifecycle coordinator stops the component during a single context close. If multiple callers can invoke `stop(Runnable)` concurrently, the code must **safely register/complete multiple callbacks** without overwriting an earlier callback. That is a production requirement, not something to hide under "the method is synchronized".

### 8.3. Why Implement Both `stop()` and `stop(Runnable)`?

`SmartLifecycle` extends `Lifecycle.stop()`. During Spring lifecycle shutdown, the processor invokes the **`stop(Runnable)` variant**, not automatically `stop()` in its place; to share logic, delegate explicitly.

In the demo:
- `stop(Runnable)` defines the primary shutdown protocol.
- `stop()` is a synchronous adapter waiting on the callback with a five-second timeout.

In production, both variants must agree on state, idempotency, and interrupt handling. Never make one variant call `shutdownNow()` while the other merely flips a boolean, causing behavior to differ depending on which API is called.

### 8.4. Spring's Timeout Is Per Phase

In Spring Framework 6.1, `DefaultLifecycleProcessor` defaults to **30 seconds per shutdown phase**. Spring Boot 3.3 provides the property:

```properties
spring.lifecycle.timeout-per-shutdown-phase=10s
```

In the demo, 10 seconds is the deadline the processor waits for a phase's callbacks. An application with multiple phases must also budget time for the other phases and subsequent cleanup.

**On timeout:** the processor may proceed to the next phase or destruction even if the worker has not actually stopped. Therefore apps need I/O timeouts, interrupt/cooperative cancellation support, and safe dependency design. Do not interpret the timeout as "the JVM kills the thread and rolls back all side effects after 10s".

### 8.5. The Callback Signals a Technical Milestone, Not Business Commit

A worker may stop its thread yet still leave an unacknowledged message on a broker or an uncommitted transaction. In real systems, define `stop complete` as:

- stop accepting new jobs;
- wait for or checkpoint in-flight jobs;
- ack/nack messages per protocol;
- flush/commit/close resources in the right order;
- only then invoke the callback.

If these steps cannot finish, do not silently report **success** merely because the thread exited. Log errors, timeouts, retry state, idempotency, and clear recovery policies.

## 9. Why Use `@DependsOn` When `getPhase()` Already Exists?

The two mechanisms have different scopes:

| Mechanism | Definition | When Appropriate |
| --- | --- | --- |
| `getPhase()` | Start/stop order by **phase group** | System knows "infra runs before consumers" without necessarily having direct references |
| Constructor injection | Worker receives the exact `Gateway` object | Direct interaction and concrete dependency type exist |
| `@DependsOn("gateway")` | Explicit bean definition relationship | Want lifecycle order guaranteed even if phases change |
| `@Order` | Ordering for specific collections/extension points | Not the primary API for sorting `SmartLifecycle` phases |
| `@PostConstruct` | Bean initialization callback | Not an operational start/stop milestone |
| `ContextClosedEvent` | Notification that context is closing | Does not prove workers have stopped |

In the example, all three align consistently:

```text
worker ---- uses ----> gateway
phase(worker)=200 > phase(gateway)=100
@DependsOn(worker -> gateway)
```

When adding a third infrastructure piece, design the dependency graph explicitly rather than picking phases arbitrarily. For example, if `consumer(200)` needs `decoder(150)` and `gateway(100)`: start 100→150→200, shutdown 200→150→100 provided dependencies align without conflicting constraints.

### 9.1. Experiment: Making Phases "Wrong"

Keep `@DependsOn("gateway")` but change:

```java
// Inside BackgroundWorker.getPhase()
return 50;  // Lower than Gateway 100, intentionally creating a conflict.
```

This is an **edit inside the existing class**, not a second method to paste in. By Spring's contract, explicit dependencies take precedence when starting/stopping related beans; thus gateway still starts before worker, and worker still stops before gateway.

However, configuring phases that conflict with dependencies is a **design smell**: hard for readers to follow and prone to surprising orderings with third components. In production, keep phases and dependencies aligned like 100/200.

### 9.2. Experiment: Removing `@DependsOn` While Keeping Injection

If you remove the `@DependsOn` annotation, the worker still receives a `Gateway` via the `@Bean` method, so Spring must create that dependency before creating the worker. However, how the processor handles explicit lifecycle relationships can differ in complex designs. This lab intentionally keeps `@DependsOn` to **declare an explicit lifecycle constraint** rather than relying on assumptions about constructor order.

### 9.3. Experiment: Two Beans in the Same Phase

If two workers have `getPhase()==200` with no dependency between them, do not rely on the start/stop order the JVM happens to log. `SmartLifecycle` allows same-phase components to be coordinated without guaranteeing a business ordering contract. Use distinct phases or explicit dependencies if one worker must wait for the other.

## 10. Do Not Confuse Lifecycle Start with Application Ready

`SmartLifecycle.start()` runs during `ApplicationContext.refresh()` (when `isAutoStartup()==true`), meaning **before** Spring Boot 3.3's `ApplicationStartedEvent` and `ApplicationReadyEvent`. Yet in many implementations, `start()` merely **submits** a background task and returns.

Distinguish:

1. **Bean exists:** object is registered.
2. **Lifecycle received start:** `start()` was called.
3. **Worker truly accepts work:** thread/executor/consumer is ready.
4. **Boot publishes app ready:** `ApplicationReadyEvent` and Boot readiness state along the normal pipeline.
5. **Business ready:** specific conditions such as broker connection, permissions, and required data are confirmed.

In the demo, `BackgroundWorker.start()` creates a daemon thread and returns. Main only submits work **after `SpringApplication.run` returns**. That does not mean a production worker has finished connecting to a real broker the moment `start` returns.

If worker readiness is a prerequisite before receiving traffic:

- Perform handshake/health checks with a deadline before publishing readiness, or
- Track a dedicated application-level readiness state and transition to `ACCEPTING_TRAFFIC` only when conditions are met, or
- Use a runner/initialization orchestration that awaits mandatory results.

**Do not** set `running=true` before a connection is opened and call it success. `isRunning()` should reflect a state the component can genuinely guarantee, and readiness can be an even stronger signal.

## 11. Closing Context vs Destroying Singletons: Different Events

On Spring Framework 6.1's normal close path:

```text
context.close()
  |
  +--> ContextClosedEvent
  +--> LifecycleProcessor.onClose()
  |      +--> stop high phase first
  |      +--> stop low phase later
  +--> destroyBeans()
  |      +--> @PreDestroy / DisposableBean / custom destroy method
  +--> close bean factory and clean up context
```

Therefore in the demo:

- Line **07 `ContextClosedEvent`** states shutdown **has started**.
- Line **08** states the worker thread **has exited** and the stop callback was signaled.
- Line **09** states the gateway **has stopped**.
- Lines **10, 11 `@PreDestroy`** are singleton destruction steps after normal lifecycle stop.
- Line **12** confirms `context.close()` has returned.

**Do not treat `ContextClosedEvent` as proof that "all tasks are done"**. If a context-closing listener submits additional async work and returns, Spring may proceed to shut down executors right afterward. Work needing draining must reside in the `SmartLifecycle.stop(Runnable)` protocol or an equivalent owner.

### 11.1. `context.stop()` Differs from `context.close()`

`context.stop()` is a lifecycle operation telling the container to stop components per contract, potentially allowing `context.start()` while the context remains active. It **does not** destroy all beans and does not mean the JVM has exited.

`context.close()` closes the context, stops lifecycle components, and destroys eligible singletons; a closed context should not be started again.

**A demo limitation:** The worker is written as one-shot and intentionally throws an exception if `start()` is called again after the old thread has finished. Therefore, **do not use the demo verbatim to test `context.stop(); context.start()`**. For a real restartable component, create a fresh `RunState` per start (thread, latches, future, callback state), ensure idempotent start/stop, and finish closing old state before opening new state.

### 11.2. Startup Failure and `@PreDestroy`

If `Gateway.start()` throws during context refresh, or `BackgroundWorker.start()` throws because a dependency isn't ready, Spring Boot may enter startup failure handling. On an aborted refresh path, **there is no guarantee every lifecycle bean received stop before destruction**.

Hence the example's `@PreDestroy` methods **check state** and defensively call stop if still running. In production, cleanup must tolerate partially constructed objects, unopened connections, or unstarted worker threads.

Never write `@PreDestroy` to unconditionally call `thread.join()` when `thread==null`, or close a connection that was never opened without checking state.

### 11.3. SIGTERM and SIGKILL

- When `context.close()` is called or the JVM gets to run its normal shutdown hook, Spring can coordinate phase-ordered stopping.
- On SIGKILL, JVM crash, power loss, or forced termination, Java callbacks **are not guaranteed to run**.
- Spring lifecycle does not replace durable queues, checkpoints, idempotency, or transaction protocols when recovering already-accepted jobs.

This is why real workers need **crash recovery** alongside graceful stop.

## 12. Common Mistakes When Implementing `SmartLifecycle` Yourself

| Symptom / Flawed Design | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| Worker phase lower than gateway despite depending on gateway | May start before dependency or stop after dependency if no explicit relation exists | Gateway phase 100, worker 200; declare dependency |
| Using only `@Order` to order worker lifecycle | `@Order` is not `SmartLifecycle.getPhase` | Override `getPhase` |
| `isRunning()` always returns true | Processor lacks real state; hard to stop idempotently | Use thread-safe state updated accurately |
| `start()` spawns a thread every call without checking running | Duplicate workers, double-consuming messages | Idempotent start or explicit restartable RunState |
| `stop(Runnable)` invokes callback right after requesting shutdown | Worker may still be using gateway | Invoke callback after drain and thread exit |
| `stop(Runnable)` forgets to invoke callback | Processor waits for phase timeout; slow shutdown | Invoke callback promptly, including on error paths |
| `stop()` is a no-op while `stop(Runnable)` actually stops | Inconsistent API | Share shutdown logic |
| Worker creates unmanaged non-daemon thread | JVM may fail to exit | Owner manages thread, stop/join/deadline |
| Daemon thread treated as graceful shutdown | Daemon does not guarantee work finishes | Await Future + lifecycle callback |
| Worker keeps accepting messages after stop requested | Work may be lost when gateway stops | Set stopping flag / unsubscribe before draining |
| Not awaiting in-flight tasks | Incomplete transactions, lost messages | Await/checkpoint/ack before callback |
| `Thread.sleep` used to test ordering | Scheduling-dependent races | Synchronized Latch/Future/trace |
| Calling `context.close()` inside `@PostConstruct` | Context may not have finished refreshing | Manage shutdown in an appropriate orchestrator |
| Using `@PreDestroy` instead of full stop protocol | Dependencies may stop at the wrong time | Stop via SmartLifecycle before destroy |
| Using `@DependsOn` with wrong bean name | Bean creation can fail | Verify exact bean names |
| Two beans in same phase without constraints yet asserting order | Ordering is not a business contract | Declare distinct phases/dependencies |
| Overusing `Integer.MAX_VALUE` for every worker | Hard to coordinate with servers/executors that have their own phases | Use explicit phases and check infrastructure interactions |
| Setting `running=false` before thread actually stops | Spring may treat component as stopped too early | Update state only upon actual stop |
| Stop times out and error is ignored | Gateway may close while worker still uses it | Bounded drain, logging, interrupt/retry/recovery |
| Calling callback twice or from multiple stop callers | Processor/collector may be double-notified | Design single-completion callback signaling |
| Worker startup fails yet app returns ready | Service accepts traffic with unready dependency | Fail-fast or readiness gate |
| Assuming lifecycle callbacks always run after SIGKILL | Crash prevents Java cleanup | Checkpoints/durable queues and reconciliation |

### 12.1. Debugging Out-of-Order Output

If the worker starts before the gateway:

1. Verify both beans actually implement `SmartLifecycle` and are managed by Spring.
2. Print `getPhase()` of the actual **instance**, avoiding confusing configuration classes with bean objects.
3. Check `@DependsOn`, bean dependency graph, and bean names.
4. Is anything manually calling `worker.start()` in a constructor/`@PostConstruct`/listener?
5. Does the worker spawn a thread inside its constructor before the lifecycle processor runs?
6. Are you reading logs from async threads and mistaking them for synchronous callback order?

If the gateway stops before the worker finishes:

1. Did the worker's `stop(Runnable)` invoke the callback **too early**?
2. Did the worker actually stop accepting jobs and drain in-flight work?
3. Did a phase timeout cause the processor to move on?
4. Is another component outside Spring closing the gateway manually?
5. Was an explicit bean dependency or phase altered in another profile?
6. Did a refresh failure/SIGKILL occur that you mistook for normal close?

### 12.2. Better Observability in Production

Minimal log:

```text
component=gateway phase=100 transition=starting
component=gateway phase=100 transition=running
component=consumer phase=200 transition=starting
component=consumer phase=200 transition=running
component=consumer phase=200 transition=stopping inflight=3
component=consumer phase=200 transition=stopped inflight=0
component=gateway phase=100 transition=stopped
```

This is a **suggested log schema**, not demo stdout. As needed, add job ID, durations, queue backlog, lastSuccessAt, cancellation count, retry count, and exception type; avoid logging tokens/passwords/sensitive payloads.

For production incidents, a trace with timestamps and phases is far more useful than a single `running` boolean. Still, never deduce happens-before from timestamps logged across unsynchronized threads; rely on contractual completion signals.


## 13. Extending the Demo into a Real Background Worker

The demo has just one message so learners see phases clearly. To use this for a long-running message consumer or poller, design these additional aspects.

### 13.1. Queues and Backpressure

If using a `BlockingQueue<Job>`:

- `start()` registers/starts the worker loop.
- Callers `submit` jobs into a queue with **bounded capacity**.
- When full, return rejected/busy or route to a durable broker.
- `stop` stops accepting jobs, waits for queue drain, or moves pending jobs to a recoverable state.
- `stop(Runnable)` reports completion only after policy requirements are satisfied.

Do not treat an unbounded queue as proof against losing work: a JVM crash can wipe out all pending jobs held only in memory.

### 13.2. Using Spring-Managed Executors

A complex service should usually use `ThreadPoolTaskExecutor`, `TaskExecutor`, schedulers, or Spring-managed consumer libraries rather than manually spawning `new Thread(...)`. You then need to understand **two lifecycle owners**:

- The worker bean manages subscription/job semantics.
- The executor bean manages the thread pool and task execution.

If a worker depends on an executor, choose phases/depends-on so the worker **stops and drains** before the executor shuts down. Never manually shut down a shared executor still used by other beans.

### 13.3. Designing Multiple Stop Calls Without Overwriting Callbacks

In the demo, `shutdownCallback` only stores **one** callback for one Spring-coordinated stop. Production should define a terminal completion signal, such as `CompletableFuture<Void> stopped`, and let every caller attach callbacks to **the same future**:

```java
stopped.whenComplete((ignored, error) -> callback.run());
requestShutdownOnce();
```

This is an **illustrative snippet**, requiring `stopped`/`requestShutdownOnce` and a policy determining true stop completion. Idea: every caller gets notified without overwriting earlier callers' callbacks. If shutdown fails, log/record metrics and report the appropriate outcome rather than silently claiming clean completion.

### 13.4. Supporting Multiple `context.stop()`/`start()` Cycles

A production-grade `SmartLifecycle` may be started/stopped multiple times while the context stays alive. To support this, design a state machine:

```text
NEW -> STARTING -> RUNNING -> STOPPING -> STOPPED
                       ^                    |
                       +---- STARTING <-----+
```

Each `start` from `STOPPED` must recreate threads, latches, subscriptions, futures, and callback registries; avoid reusing `CountDownLatch(0)` or a completed Future from a prior cycle. Use locking/CAS between `STARTING` and `STOPPING` to avoid spawning duplicate workers.

If restart is not supported, **document the contract clearly and do not advertise the component as an infinitely pauseable/resumable lifecycle bean**. The demo intentionally throws on restart instead of silently holding onto a dead thread.

### 13.5. Layered Timeouts

Do not rely on `spring.lifecycle.timeout-per-shutdown-phase` alone to cover everything. Budget for:

- HTTP/database/broker I/O.
- Queue drain and acks.
- Executor awaitTermination.
- Spring phase stop callbacks.
- Shutdown hooks and Kubernetes termination grace period.
- Caller `Future.get` timeouts.

Budgets must be **compatible with headroom**. If Kubernetes kills the process after 10 seconds while each phase waits 30 seconds, graceful shutdown cannot be expected to finish.

### 13.6. Phases Across Libraries

Real Spring Boot apps have embedded web servers, schedulers, task executors, message listener containers, and many infrastructure beans that also implement `SmartLifecycle`. Any chosen phase must account for the stop order of **all dependencies**. Numbers 100/200 in this lab suffice for illustration, not as standard phases for brokers/JDBC/executors.

If a consumer needs a shared HTTP client, message broker connector, and thread pool, draw the real dependency graph and assign phases accordingly; add explicit dependencies when needed. Do not blindly assign `Integer.MAX_VALUE` to every consumer thinking "higher is always better" without checking servers/executors that also have high phases.

## 14. Extended Practice Exercises

**Exercise 1 — Change phases.** Change `Gateway.getPhase()` to 50 while keeping worker at 200. Expect gateway to still start before and stop after worker. Observe the trace and update labels/expected output accordingly.

**Exercise 2 — Test conflicting phase and dependency.** Keep `@DependsOn("gateway")` but set worker phase to 50 and gateway phase to 100. Explain why explicit dependencies can override phases. Do not keep conflicting configurations in production.

**Exercise 3 — Omit the callback.** In `BackgroundWorker.stop(Runnable)`, intentionally never invoke the callback after worker exit. Observe shutdown duration per `spring.lifecycle.timeout-per-shutdown-phase`. This is a controlled failure exercise; restore the callback afterward.

**Exercise 4 — Callback too early.** Invoke `callback.run()` immediately inside `stop(Runnable)` before the thread exits. Add simulated slow I/O with a latch and observe how the gateway can be stopped before the worker finishes. This is an anti-pattern; never use in real code.

**Exercise 5 — No job submitted.** Start the context and close without calling `submitOnce()`. The worker must exit and phase 200 must complete without hanging at `jobRequested.await()`.

**Exercise 6 — Gateway error.** Change `Gateway.handle` to throw `IllegalStateException`. Main must receive an exceptional completion from `CompletableFuture.get`; since the code uses try-with-resources, the context still closes. The original success trace no longer applies; assert the failure path separately.

**Exercise 7 — `isAutoStartup=false`.** Change worker's `isAutoStartup()` to false. Confirm the worker does not auto-start on refresh. Try calling `context.start()` or `worker.start()` explicitly, then stop properly. Do not reuse `main` verbatim since it assumes the worker is already running.

**Exercise 8 — Thread safety.** Call `submitOnce()` from multiple threads. Observe the one-shot worker's limitation; modify into a queued API, reject duplicates, or use `AtomicBoolean` to accept strictly one submission. Never claim the demo supports multiple jobs when it has only one Future.

**Exercise 9 — Readiness timing.** Have `Gateway.start` simulate a failing handshake. Decide between failing fast during refresh or using a readiness gate if the component can recover. Explain why proof of readiness must be stronger than thread creation.

**Exercise 10 — Real broker integration.** Replace the in-memory Gateway with a test-container broker adapter; implement consumer stop to unsubscribe/drain/ack before the connector stops. Specify timeouts/acks/recovery for already-received messages.

## 15. Self-Check Questions

**Q1.** In what order will two beans with phase 100 and 200 start?

**A:** Phase 100 first, phase 200 second, unless an explicit dependency requires a stronger relationship to be respected.

**Q2.** During normal shutdown, which phase stops first?

**A:** Phase 200 stops before phase 100.

**Q3.** Why does the phase-200 worker need the phase-100 Gateway?

**A:** The worker calls `Gateway.handle(...)`. The gateway must start before the worker operates, and stay alive while the worker drains/stops.

**Q4.** Is `@DependsOn("gateway")` the same as constructor injection?

**A:** No. Constructor injection supplies the dependency object, whereas `@DependsOn` expresses an explicit bean definition/lifecycle relationship.

**Q5.** Does `@Order(1)` on a worker automatically change `getPhase()`?

**A:** No. The SmartLifecycle processor reads phases from `getPhase()`/`Phased` and the dependency graph.

**Q6.** When does `SmartLifecycle` auto-start?

**A:** During context refresh when `isAutoStartup()` returns true; not triggered by `ApplicationReadyEvent`.

**Q7.** What is `SmartLifecycle.DEFAULT_PHASE` in Spring 6.1?

**A:** `Integer.MAX_VALUE`. This lab explicitly overrides it with 100/200.

**Q8.** Why not call the callback right when `stop(Runnable)` sets stopping?

**A:** The worker may still be running; the callback must signal **actual stop completion** so lower-phase dependencies are not closed prematurely.

**Q9.** Does Spring call `stop()` or `stop(Runnable)` when stopping SmartLifecycle via the processor?

**A:** The `stop(Runnable)` variant. The implementation is responsible for delegating to shared logic if needed.

**Q10.** If a worker was never given a job, how must stop be handled?

**A:** Wake it from waiting on its latch/queue, set stopping state, let the worker exit, and then invoke the callback.

**Q11.** Can `@PreDestroy` in Gateway replace `worker.stop`?

**A:** No. If Gateway is destroyed before the consumer stops, the consumer may touch a closed resource.

**Q12.** Does `ContextClosedEvent` mean all workers have stopped?

**A:** Not yet. It is published before lifecycle stop on the normal close path.

**Q13.** What is Spring 6.1's default `DefaultLifecycleProcessor` timeout?

**A:** 30 seconds **per phase**; configurable via `spring.lifecycle.timeout-per-shutdown-phase` in Boot 3.3.

**Q14.** What does `CompletableFuture.get` verify in the demo?

**A:** The caller waits for the job result processed through Gateway, not merely for `submitOnce` to return.

**Q15.** Why is a shutdown callback still needed even though the worker thread is a daemon?

**A:** Daemon status does not guarantee work completion; lifecycle must wait for the worker to stop so dependencies close in order.

**Q16.** Does the demo run `worker.start()` again after stop?

**A:** No. It is a one-shot worker with single-use latches/future; production needs recreated run state.

**Q17.** If `Gateway.start()` throws an exception, is `worker.stop` guaranteed to run before destruction?

**A:** No. Refresh failure can jump to destruction without full stop callbacks; cleanup must be defensive.

**Q18.** When should `SmartLifecycle` be used instead of `ApplicationRunner`?

**A:** When a component is responsible for **long-running execution and coordinated stopping**, especially with phases/dependencies and asynchronous shutdown. Runners suit one-time startup work; they can collaborate but do not replace each other's roles.

**Q19.** With two components in the same phase and no dependency, should you assert which starts first?

**A:** No. Business ordering requires distinct phases or explicit depends-on.

**Q20.** If a container receives SIGKILL, is the stop callback guaranteed to run?

**A:** No. Critical work needs checkpoints, durable queues, and recovery.

## 16. Summary and Official Documentation

Remember seven principles:

1. `SmartLifecycle` separates **bean created** from **component running**, letting Spring's `LifecycleProcessor` start/stop it per contract.
2. **Lower phase starts first, higher phase stops first.** In the demo: Gateway **100** before Worker **200** on start; Worker **200** before Gateway **100** on stop.
3. **Explicit dependencies take precedence over phases** when they conflict. Use injection and `@DependsOn` to state clearly that the worker needs the gateway.
4. **`stop(Runnable callback)` must signal after stop completes**. Never invoke the callback prematurely right after shutdown request, and never forget to invoke it.
5. **`ContextClosedEvent` → lifecycle stop → singleton destruction** is the normal close sequence. `@PreDestroy` does not replace phase-ordered stop protocols.
6. **Future/CountDownLatch** lets tests verify job completion and shutdown order without relying on `Thread.sleep`.
7. **A single-job demo is not equivalent to a production worker**: multi-task/restartable systems need queues, state machines, timeouts, idempotent shutdown, metrics, durability, and crash recovery.

Official documentation:

- [Spring Framework 6.1 — SmartLifecycle API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html): phases, auto-start, dependency precedence over phase, stop callbacks.
- [Spring Framework 6.1 — DefaultLifecycleProcessor API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): `onRefresh`, `onClose`, phase-ordered stopping, and timeouts.
- [Spring Framework — Bean Lifecycle / Startup and Shutdown Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): differences between bean destruction and `Lifecycle`, 30-second per-phase default in Spring 6.1.
- [Spring Framework — Depends-on](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-dependson.html): dependent starts after and destroys/stops before dependency.
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): configuring `spring.lifecycle.timeout-per-shutdown-phase`; web-server graceful shutdown is another form of lifecycle stop.
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): `ApplicationStartedEvent`/`ApplicationReadyEvent` and startup milestones.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html) and [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): synchronization and background task outcome observation.

**Conclusion:** A safe background component is more than `new Thread(...)` and `boolean running`. It must know **who must run before it**, **who must wait for it to stop**, **when tasks have truly finished**, and **when the shutdown callback may be invoked**. `SmartLifecycle` together with phases, dependencies, and completion signaling provides the foundation for Spring Boot to coordinate those boundaries verifiably.
