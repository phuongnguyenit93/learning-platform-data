# Asynchronous Stopping with stop(Runnable) and the Callback Obligation in SmartLifecycle

## 1. Problem to solve: stopping resources is not always instantaneous

A Spring Boot application can create long-lived components such as message consumers, event receivers, background processors, write buffers, streaming connections, or worker pools. When the application closes `ApplicationContext`, many components cannot stop instantly; they need to:

- Stop accepting new work.
- Let in-flight work finish within a reasonable time window.
- Flush data or acknowledge the last messages.
- Close connections, threads, or executors.
- Signal that **the stop stage has ended** so Spring can proceed to shut down dependent components.

Spring Framework provides the `SmartLifecycle` interface for beans needing lifecycle control and start/stop ordering. The special method:

```java
void stop(Runnable callback);
```

enables **asynchronous stopping**: the stop request begins on the context-closing thread, while another thread can continue handling cleanup. Once shutdown finishes, the bean **must invoke `callback.run()`**.

This is the core contract of this lesson:

> **The callback is the completion signal for `LifecycleProcessor`. Failing to call the callback can make Spring wait until the phase timeout expires; calling the callback too early can make Spring close dependencies while the bean is still active.**

It is **not** a callback that performs cleanup for you. Cleanup is the bean's responsibility; the callback merely confirms to the coordinator that the bean's stop step has finished.

## 2. How does SmartLifecycle differ from Lifecycle?

In Spring Framework 6.1, `SmartLifecycle` extends two interfaces:

```java
public interface SmartLifecycle extends Lifecycle, Phased {
    // Methods provided by SmartLifecycle and parent interfaces:
    boolean isAutoStartup();
    int getPhase();
    void stop(Runnable callback);
    // start(), stop(), isRunning() come from Lifecycle.
}
```

This is an **abbreviated diagram of key signatures**, not code to redeclare interfaces already present in the Spring library.

| Component | Practical meaning |
|---|---|
| `start()` | Start the component, e.g., open consumer or worker |
| `isRunning()` | Return running state so the lifecycle processor determines appropriate start/stop |
| `stop()` | `Lifecycle` stop method, without callback |
| `stop(Runnable callback)` | Stop method with completion signal; used by lifecycle processor for `SmartLifecycle` |
| `isAutoStartup()` | Whether to auto-start on context refresh; defaults to `true` |
| `getPhase()` | Defines start/stop order among components; `SmartLifecycle` defaults to `Integer.MAX_VALUE` |

**Most common pitfall:** in a shutdown coordinated by `DefaultLifecycleProcessor`, Spring **calls `stop(Runnable)`**, **not `stop()`**, for a `SmartLifecycle` implementation. If you only put resource-closing logic in `stop()` and override `stop(Runnable)` without invoking that logic, resources may never be stopped.

Conversely, if you **do not override `stop(Runnable)`**, the default implementation in `SmartLifecycle` calls `Lifecycle.stop()` and then immediately invokes the callback on the current thread. That is useful for **synchronous** stopping, but **unsuitable** if `stop()` merely sends a command to an async worker and returns before the worker actually stops.

## 3. Why does Spring need the callback?

In a context with multiple `SmartLifecycle` beans, Spring cannot simply call a `void` method and guess that resources have stopped. With asynchronous stopping, `stop(Runnable)` can **return before cleanup finishes**.

Diagram:

```text
ApplicationContext closing thread       Bean cleanup thread
                |                                  |
                | call stop(callback)              |
                +--------------------------------->|
                |                                  | stop intake
                | stop(...) returns                | wait for in-flight work
                |                                  | flush & close
                | DefaultLifecycleProcessor        |
                | waits for callback in phase      |
                |                                  |
                |<---------------------------------+
                |       callback.run()
                |
                | confirm bean has stopped
                | proceed to lower phases
                v
          context closes
```

`LifecycleProcessor` uses the callback to know when **a bean has completed its stop command**, thereby coordinating multiple beans in the **same phase** and deciding whether it can advance to the next phase. A phase can hold multiple beans, so total stop time of the group does not necessarily equal the sum of individual bean times; asynchronous steps can overlap.

Do not think of the callback as a Java `Future` or `CompletionStage`: the signature is simply `Runnable`. A bean may use threads, I/O library callbacks, or `CompletableFuture` internally, but ultimately must invoke **the exact `Runnable` supplied by Spring**.

### Two opposite errors

**Error A — never calling the callback:**

```java
@Override
public void stop(Runnable callback) {
    worker.shutdown();
    // Forgot callback.run().
}
```

This is an **intentionally broken snippet**, assuming a `worker` variable. Even after the worker stops, the lifecycle processor may still wait until the phase timeout. It has no way to know that stopping has finished.

**Error B — calling the callback right when sending the stop request:**

```java
@Override
public void stop(Runnable callback) {
    worker.shutdown(); // Requests stopping new work, does not guarantee worker finished.
    callback.run();    // Wrong if work is still running.
}
```

If `worker` is an `ExecutorService`, `shutdown()` **only initiates an orderly shutdown**; it does not wait for already-submitted tasks to finish. Calling the callback right after `shutdown()` marks completion **too early**. Lower-phase dependencies can begin closing while the worker's tasks are still accessing them.

**Right approach:** invoke the callback **after actual stopping finishes**, or after a controlled termination procedure (for instance, an internal timeout with force-close and state confirmation). If clean stop fails, log/emit metrics for the failure state; do not call the callback and claim all data was processed safely.

## 4. Phase order: ascending start, descending stop

`SmartLifecycle` extends `Phased`. Spring Framework uses `getPhase()` to order coordinated lifecycle components.

```text
START (ascending phase):
  phase -100 -> phase 0 -> phase 100 -> phase 200

STOP (descending phase):
  phase 200 -> phase 100 -> phase 0 -> phase -100
```

If component **Consumer** needs **Writer** active before receiving messages:

- Writer has `getPhase() = 100`.
- Consumer has `getPhase() = 200`.
- On start, Writer is started **before** Consumer.
- On stop, Consumer is asked to stop **before** Writer.
- When Consumer uses asynchronous `stop(Runnable)`, Spring waits for the phase-200 group's callbacks (or timeout) before moving to phase 100 containing Writer.

This arrangement prevents closing Writer while Consumer still needs to write data during drain.

| Phase | Component | Start | Stop |
|---|---|---|---|
| 100 | Writer | Earlier | Later |
| 200 | Consumer | Later | Earlier |

**Nuances to remember:**

1. `SmartLifecycle.getPhase()` **defaults to `Integer.MAX_VALUE`**, not 0. So default SmartLifecycle beans usually start very late and stop very early compared to `Lifecycle` beans at phase 0.
2. A bean implementing only `Lifecycle` and **not** `SmartLifecycle` is treated by the lifecycle processor as phase **0**.
3. Among beans in the **same phase**, ordering is not a stable contract. If there is a real dependency, do not rely solely on sharing a phase.
4. An explicit `depends-on` relationship can **take precedence over phase**: the dependent bean starts after and stops before its dependency.
5. `@Order` on a bean is not synonymous with `getPhase()`; do not use `@Order` ordering as a substitute for lifecycle phases.
6. A phase has a **shared group timeout**, not an independent timer per bean in the group.

## 5. When must the callback run?

Strict principles for designing an async stop:

- If the bean is **already stopped**, there is nothing to wait on—invoke the callback immediately to fulfill the request.
- If the bean is **running**, issue the stop command and perform cleanup.
- If cleanup **completed**, update `isRunning()` accordingly and then call `callback.run()`.
- If an **exception** occurs, handle errors per policy: try closing/force-closing resources if needed, record the failure, yet do not forget to signal completion to the lifecycle processor once the stop procedure actually ends.
- If starting the async task fails (e.g., executor rejects task), have a **fallback path**; never leave the callback uncalled in a code branch.

Within one `stop(Runnable)` invocation, structure logic so the **callback executes exactly once** and **after stopping finishes**. Spring should not receive a "completed" signal twice for the same stop request.

**Do not confuse two kinds of completion:**

- "Cancel requested": `shutdown()`, `cancel()`, `closeAsync()` was called.
- "Stopped": tasks exited processing, resources closed or terminated per timeout/force-close policy.

Only the second milestone is appropriate for invoking the callback if the goal is orderly shutdown.

## 6. Runnable example: two SmartLifecycle beans and an async stop

The example uses **Java 17+, Spring Boot 3.3.x**, needing no Web server or database. There are two lifecycle beans:

- **WriterLifecycle** at phase 100: stops synchronously.
- **AsyncConsumerLifecycle** at phase 200: stops asynchronously on a new thread, simulating a 300 ms drain.

They process no real data. The goal is observing that phase 100 **is not stopped** until phase 200 **invokes the callback**.

### 6.1. Project structure

```text
smart-lifecycle-stop-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/shutdown/
    │   ├── ShutdownDemoApplication.java
    │   ├── WriterLifecycle.java
    │   └── AsyncConsumerLifecycle.java
    └── resources/
        └── application.properties
```

**`settings.gradle`:**

```groovy
rootProject.name = 'smart-lifecycle-stop-demo'
```

**`build.gradle`** (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
}
```

**`src/main/resources/application.properties`:**

```properties
spring.application.name=smart-lifecycle-stop-demo

# Wait limit to finish each phase group during shutdown.
spring.lifecycle.timeout-per-shutdown-phase=3s
```

The timeout property here is set to **3 seconds**, much longer than the simulated 300 ms duration. Do not set a timeout smaller than expected cleanup time and then treat the timeout warning as a Spring bug.

### 6.2. WriterLifecycle: phase 100, synchronous stop

**`src/main/java/com/example/shutdown/WriterLifecycle.java`:**

```java
package com.example.shutdown;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public final class WriterLifecycle implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("START writer (phase 100)");
        }
    }

    @Override
    public void stop() {
        stop(() -> { });
    }

    @Override
    public void stop(Runnable callback) {
        try {
            if (running.compareAndSet(true, false)) {
                System.out.println("STOP writer (phase 100)");
            }
        } finally {
            // Synchronous stop: cleanup already completed here.
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
```

This is a complete, self-contained implementation. `@Component` lets Spring Boot register it as a bean under component scanning.

Key points:

- `start()` sets the running state.
- Both `stop()` and `stop(Runnable)` work, though the **lifecycle processor prefers calling the callback overload**.
- Stopping Writer finishes directly on the caller thread, so it can invoke the callback before the method returns.
- `AtomicBoolean` gives proper visibility to state updates if callbacks/workers run on different threads; it is not proof the whole app is thread-safe solely from one field.
- `getPhase()` returns 100, lower than Consumer's phase 200.

### 6.3. AsyncConsumerLifecycle: phase 200, asynchronous stop

**`src/main/java/com/example/shutdown/AsyncConsumerLifecycle.java`:**

```java
package com.example.shutdown;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public final class AsyncConsumerLifecycle implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("START consumer (phase 200)");
        }
    }

    @Override
    public void stop(Runnable callback) {
        if (!running.get()) {
            callback.run();
            return;
        }

        // This only simulates drain; real projects must wait for real resources.
        Thread shutdownWorker = new Thread(() -> {
            try {
                System.out.println("STOP consumer: draining...");
                Thread.sleep(300);
                System.out.println("STOP consumer: drained");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                // Demo has no real I/O; in practice must force-close resources.
                System.err.println("STOP consumer: interrupted");
            } finally {
                running.set(false);
                System.out.println("STOP consumer: callback");
                callback.run();
            }
        }, "consumer-drainer");

        try {
            shutdownWorker.start();
        } catch (RuntimeException | Error ex) {
            // If worker cannot be created, demo has no real resources to close.
            running.set(false);
            callback.run();
            throw ex;
        }
    }

    @Override
    public void stop() {
        // Used when a caller invokes Lifecycle.stop() directly.
        // DefaultLifecycleProcessor uses stop(Runnable) above.
        CountDownLatch completed = new CountDownLatch(1);
        stop(completed::countDown);

        try {
            if (!completed.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Manual stop did not complete within 2 seconds");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Manual stop interrupted", ex);
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return 200;
    }
}
```

Reading each part:

1. `isRunning()` reflects initial running state and state after cleanup completes.
2. If `stop(Runnable)` is called when already stopped, the callback runs right away to avoid creating an unnecessary wait.
3. The new thread runs a simulated 300 ms drain task. `stop(Runnable)` **does not block 300 ms** before returning.
4. `finally` sets `running=false` and invokes `callback.run()`, so the callback still runs if the simulated sleep is interrupted.
5. If `Thread.start()` fails, the catch branch avoids losing the callback. The demo has no real I/O; real production code must have a fallback **closing actual resources**, log the error clearly, and ensure state is not misreported.
6. No-arg `stop()` is implemented separately to support direct callers, waiting up to 2 seconds for the demo. This is **not** the method Spring invokes during lifecycle shutdown of a `SmartLifecycle` bean.
7. `getPhase()=200` makes Consumer start after Writer and be asked to stop before Writer.

**Intentional limitation of the example:** this code demonstrates **a single context close** and is not a framework handling multiple concurrent stop requests. If two threads invoke `stop(Runnable)` simultaneously while `running=true`, two workers could be spawned. Production applications need idempotency—such as a state machine or a shared completion future registering each caller's callback to avoid running cleanup multiple times.

**Error nuance:** in the example, `finally` marks completion after simulating drain; on `InterruptedException`, that is only **ending demo work**, with no real data. In real systems, being interrupted **does not prove all data was flushed**; perform force-close or record lost/unfinished work before reporting completion.

### 6.4. Spring Boot class running the demo and closing the context

**`src/main/java/com/example/shutdown/ShutdownDemoApplication.java`:**

```java
package com.example.shutdown;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ShutdownDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ShutdownDemoApplication.class);

        // Do not create a Web server, easy to observe closing the context.
        application.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            System.out.println("MAIN: closing context");
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    ApplicationRunner startupReport() {
        return args -> System.out.println("RUNNER: application started");
    }
}
```

`try-with-resources` calls `context.close()` when leaving the block. Spring executes context closing, during which `LifecycleProcessor` stops lifecycle beans by phase. For a non-web learning app, closing right after `run` is intentional. For a Web service that must keep serving HTTP, **do not close the context right after startup** like this example.

### 6.5. Running

When the project already has Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

If you do not have the Wrapper yet, you can generate a skeleton with Spring Initializr or generate the Wrapper with a compatible Gradle installation. Writing `build.gradle` alone does not auto-generate `gradlew` or `gradlew.bat`.

### 6.6. Expected output

Ignoring the banner and usual logs from Spring Boot/Gradle, the lines printed by the **demo's Java code** appear in this logical order:

```text
START writer (phase 100)
START consumer (phase 200)
RUNNER: application started
MAIN: closing context
STOP consumer: draining...
STOP consumer: drained
STOP consumer: callback
STOP writer (phase 100)
MAIN: context closed
```

Notes:

- Writer starts before Consumer because phase 100 is smaller than 200.
- Runner is invoked only after context refresh and auto-starting `SmartLifecycle` beans.
- On `close()`, Consumer (phase 200) is stopped before Writer (phase 100).
- Consumer's stop call returns early, yet Spring **waits for the callback**, so Writer is stopped only after the `STOP consumer: callback` message.
- After the phases and other context close processing complete, `try-with-resources` ends and then prints `MAIN: context closed`.

**300 ms is purely simulated.** JVM scheduling can cause actual duration to vary; do not assert runtime equals exactly 300 ms. Also do not treat log order of **same-phase** beans as an ordering contract. The example intentionally uses distinct phases.

## 7. How long does LifecycleProcessor wait for callbacks?

Spring Framework uses `DefaultLifecycleProcessor` as its default lifecycle coordinator. It groups beans by phase, asks them to stop in **descending phase order**, and waits for the corresponding completion of each group. For `SmartLifecycle`, the callback signals that the bean finished stopping; if the callback is forgotten, the processor may have to wait for the entire **phase timeout**.

In Spring Boot 3.3, you can configure:

```properties
spring.lifecycle.timeout-per-shutdown-phase=20s
```

This is the **maximum duration for a phase group**, not a guarantee that every resource will close cleanly after exactly 20 seconds. If three beans share phase 200, they share that phase's wait budget; they do not each get an additive 20 seconds.

In Spring Framework 6.1, `DefaultLifecycleProcessor`'s default timeout is **30,000 ms (30 seconds)** unless configured otherwise. For the hands-on lab, we use 3 seconds to clearly observe its effect in a controlled environment.

**Timing warnings:**

- A 3-second per-phase timeout **does not mean** total shutdown is only 3 seconds. There may be multiple phases and additional bean destruction steps.
- Without a callback, Spring may log a timeout warning and continue to later phases; that **does not prove the bean actually stopped**.
- Invoking the callback after the phase has timed out can be too late to preserve dependency shutdown order; design cleanup to fit the deadline.
- Shutdown time allocated by deployment environments such as Kubernetes `terminationGracePeriodSeconds`, container runtimes, or process managers must cover the phases your app requires. If the OS forcefully terminates the JVM sooner, callbacks cannot save the process.
- Changing the timeout value does not fix forgetting to call the callback. It merely changes how long Spring is willing to wait.

### Why is an internal deadline needed?

If a consumer waits on an external call forever due to hung I/O, setting Spring's timeout does not automatically cancel that call. Add resource-level timeouts or cancellation to the drain step, and a force-close plan so the callback only runs after terminating per policy.

Timeline example:

```text
t=0s: phase 200 starts stopping
t=1s: consumer finishes -> callback -> can proceed to phase 100

Failure path:
t=0s: phase 200 starts stopping
t=3s: callback not arrived -> phase timeout, processor may proceed
t=4s: consumer actually finishes -> callback arrives LATE
```

On the failure path, phase-100 Writer may already be stopped before Consumer finishes, breaking the layered design. The issue lies in the **stopping process deadline**, not Spring "failing to wait".

## 8. State model for reliable async stop

A bean with background workers should define explicit states rather than relying on a single Boolean in all situations:

```text
NEW
 |
 v
STARTING -> RUNNING
               |
           stop requested
               v
           STOPPING
               |
           stop completed
               v
           STOPPED
```

You can add `FAILED` for runtime error situations or cleanup that failed to meet application criteria. Upon transitioning to `STOPPING`, reject new work and allow in-flight work to finish (or cancel cleanly under control).

**Implementation rules:**

1. `start()` must not launch resources twice when the bean is already running; it must also recognize an ongoing stop.
2. `stop(Runnable callback)` must be safe when the bean is already stopped; if there is nothing to wait for, invoke the callback immediately.
3. For closely spaced stop calls, launch only **one** cleanup path; register each callback to execute **upon the same stop outcome**.
4. If the callback is invoked via `CompletableFuture.whenComplete(...)`, ensure the future completes **after cleanup**, not right when issuing the shutdown command.
5. The callback must not be invoked while tasks still have permission to write to a dependency that a lower phase is about to close.
6. If the internal deadline expires, explicitly decide and record "force-stop", "unfinished tasks", unacknowledged message counts, or unflushed data.
7. Resources/workers should close in reverse order of their creation/dependencies, with step-level deadlines.
8. Ensure exceptions are never thrown in a way that skips the callback on an error branch; log the error and let close reach a proper terminal state.

### A production template with CompletionStage

When a library provides an async stop API, such as `CompletionStage<Void> stopAsync()`, you can connect the completion stage to the callback:

```java
@Override
public void stop(Runnable callback) {
    CompletionStage<Void> stage;

    try {
        stage = resource.stopAsync();
    } catch (RuntimeException ex) {
        // Must force-close or confirm resource finished first.
        safeForceClose(resource);
        recordShutdownFailure(ex);
        callback.run();
        return;
    }

    stage.whenComplete((ignored, error) -> {
        try {
            if (error != null) {
                recordShutdownFailure(error);
                safeForceClose(resource);
            }
            running.set(false);
        } finally {
            callback.run();
        }
    });
}
```

This is **well-structured integrated Java pseudocode**, **not a standalone runnable program**: `resource`, `safeForceClose`, `recordShutdownFailure`, and `running` are application-defined components. `safeForceClose` must have sound semantics; only invoke the callback after the resource has truly stopped or passed a verified force-close procedure. If `safeForceClose` can throw and leave the resource running, add dedicated handling and record the incomplete state. The template must also handle idempotency if `stop(Runnable)` can be called concurrently.

### Why must you never do the following?

```java
@Override
public void stop(Runnable callback) {
    resource.stopAsync();
    callback.run();
}
```

This is **intentionally broken**: receiving a `CompletionStage`/`Future` does not mean the operation has finished. Attach the callback **to completion** or wait using an approach with an appropriate deadline.

## 9. Failure scenarios and callback obligations

### 9.1. Cleanup throws an exception

A method can throw `IOException`, `TimeoutException`, or a library error during flush/close. Do not write:

```java
@Override
public void stop(Runnable callback) {
    flushDatabase();  // If it throws an exception, the next line does not run.
    callback.run();
}
```

This is an **intentionally broken snippet**, not standalone runnable code. When errors need reporting to logs/metrics, handle them with `try/catch/finally` and an appropriate fallback strategy. `finally` protects the callback against exceptions, but remember **stopped semantics**: use `finally` to signal completion only after cleanup or forced shutdown has genuinely ended, never masking a still-active resource.

### 9.2. Stop interrupted from another thread

In Java, an `InterruptedException` does not automatically close sockets, executors, or finish offset commits. Code should:

- Restore the interrupt flag where appropriate via `Thread.currentThread().interrupt()`.
- Trigger cancellation/force-close.
- Record unfinished work.
- Invoke the callback only after reaching a terminal stopped state per policy.

In the demo, with no real I/O, interrupt is handled as ending the simulation. Do not copy that behavior as a production data-durability guarantee.

### 9.3. Unable to submit task to executor

With `ExecutorService`, calling `execute(...)` can throw `RejectedExecutionException` if the executor is already shut down or saturated. If you only write:

```java
executor.execute(() -> {
    cleanup();
    callback.run();
});
```

then when task submission **is rejected**, the callback is never invoked. Have a `catch` branch that runs fallback cleanup (synchronously or via another mechanism) and signals completion once stop criteria are met.

**Do not use the same executor to coordinate cleanup if that executor itself was already shut down before scheduling cleanup.** You may need a separate executor that remains alive during shutdown, or perform bounded cleanup on the thread calling `stop`.

### 9.4. Callback invoked twice

In some buggy code:

```java
try {
    cleanup();
    callback.run();
} finally {
    callback.run(); // Runs twice if cleanup succeeds.
}
```

This is **intentionally broken**. Place **a single callback invocation point** in the termination flow, or use proper guards. `LifecycleProcessor`'s callback typically counts completion signals; calling it multiple times is not a valid "retry".

### 9.5. Marking isRunning false too early

If `isRunning()` returns false right upon receiving the stop command while the worker is still processing data, coordinator state and actual state diverge. In a clear shutdown flow, transition internally to `STOPPING` when stopping new intake, and reflect `STOPPED` only once resources close. You can define `isRunning()` per the resource contract, but never use it to mask unfinished cleanup and fire the callback early.

### 9.6. Shutdown hook never triggered

`SmartLifecycle.stop(Runnable)` is invoked when the context follows a valid lifecycle shutdown path. If the process receives `kill -9` or the JVM crashes, there is no guarantee callbacks or `@PreDestroy` will run. Test controlled closing separately and build data recovery mechanisms for forced termination.

### 9.7. Bean is not running

`DefaultLifecycleProcessor` normally stops only running lifecycle beans. If `isRunning()` never returns true due to a broken `start()` implementation, do not expect stop callbacks to clean up resources allocated in another phase. Manage resources with proper lifecycles; `@PreDestroy` can serve as supplemental cleanup when appropriate, but does not replace the phased stop contract.

## 10. Stopping ExecutorService better than shutdown() + immediate callback

A more realistic example: a consumer uses an `ExecutorService` to process messages. On stop:

1. Reject new work.
2. Call `executor.shutdown()`.
3. Await `executor.awaitTermination(timeout, unit)` on **another thread** (for async stop).
4. If timed out, call `shutdownNow()` and wait briefly; record remaining tasks.
5. Confirm shutdown completion only once the executor is actually terminated or resources are force-closed per policy.

Illustrative pseudocode:

```java
@Override
public void stop(Runnable callback) {
    acceptingNewWork.set(false);
    executor.shutdown();

    Thread monitor = new Thread(() -> {
        try {
            boolean done = executor.awaitTermination(4, TimeUnit.SECONDS);

            if (!done) {
                executor.shutdownNow();
                done = executor.awaitTermination(1, TimeUnit.SECONDS);
            }

            if (!done) {
                // A task may have ignored interrupt; do not claim graceful.
                recordUnfinishedTasks();
            }

            // Mark complete only if there is a policy handling
            // the done=false branch as well; see explanation below.
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            executor.shutdownNow();
            recordShutdownInterrupted();
        } finally {
            // Do not unconditionally claim worker stopped without
            // termination confirmation. Design real forced stop.
            onTerminationPolicyResolved(callback);
        }
    }, "executor-termination-monitor");

    monitor.start();
}
```

**This is an illustrative skeleton, not standalone runnable code**: `acceptingNewWork`, `executor`, `recordUnfinishedTasks`, `recordShutdownInterrupted`, and `onTerminationPolicyResolved` are project-built components. The key point is **not confusing `shutdown()` with `isTerminated()`** and not firing the callback at the start of draining.

One mandatory detail: if a hung task **ignores interrupts**, `shutdownNow()` is only a stop request; it cannot guarantee the executor terminated. Depending on business needs, close sockets/resources directly, recover on restart, or explicitly report an unclean shutdown. Spring's timeouts only prevent hanging forever; they do not fix unflushed data.

## 11. Relationship with @PreDestroy, DisposableBean, and closing ApplicationContext

Spring has multiple teardown mechanisms; they do not share the same job:

| Mechanism | Stage / meaning | Async waiting capability |
|---|---|---|
| `SmartLifecycle.stop(Runnable)` | Phased lifecycle stop before bean destruction step | Provides callback so `LifecycleProcessor` knows when stop ends |
| `Lifecycle.stop()` | Direct stop API; on SmartLifecycle shutdown, processor picks callback overload | Must implement waiting yourself if caller uses no-callback version |
| `@PreDestroy` | Destroy callback when bean is destroyed during context close | Does not provide the same phased callback contract |
| `DisposableBean.destroy()` | Bean destruction callback | Does not directly replace phase callbacks |
| `ConfigurableApplicationContext.close()` | Initiates full context closing procedure | Can wait for multiple phases and destroy callbacks |
| JVM shutdown hook | Trigger path closing context on normal process exit | Not guaranteed to execute on forced kill |

For a standard `ApplicationContext`, shutdown typically means:

```text
context.close()
       |
       v
LifecycleProcessor.onClose()
  -> SmartLifecycle stop by phase
  -> wait for callback/timeout per phase
       |
       v
destroy singleton beans
  -> @PreDestroy / DisposableBean / destroy-method ...
       |
       v
release context
```

If a bean uses both `SmartLifecycle` and `@PreDestroy`, make the methods **idempotent** and divide responsibilities clearly. For example, `stop(Runnable)` stops message intake and drains; `@PreDestroy` only double-checks/backup-closes already-stopped resources. Never let both issue the same commit or write duplicate data.

**Do not** use `@PreDestroy` alone to perform async drain and expect Spring to wait by `getPhase()`: the callback in `stop(Runnable)` is what handles phase coordination.

## 12. Connection to Spring Boot graceful shutdown

Spring Boot 3.3 supports graceful shutdown for embedded Web servers when enabled:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

With the corresponding configuration, graceful Web server shutdown operates as part of context closing and is handled in a very early stop phase group among related `SmartLifecycle` beans. Here the Web server stops accepting new requests via its mechanism, giving active requests time to finish.

**Distinguish two things:**

- **Web server graceful shutdown:** stops accepting new requests, lets in-flight requests finish (depending on server and config).
- **Stopping a business `SmartLifecycle`:** stops the application's consumer/producer/job/worker, draining or closing resources according to the phase of the **bean you wrote**.

Enabling `server.shutdown=graceful` **does not automatically** force custom message consumers to drain properly; you still must implement your bean's `stop(Runnable)`. Conversely, implementing a consumer's callback does not make the Web server graceful.

**Do not assume changing `spring.lifecycle.timeout-per-shutdown-phase` alone is enough:** there can still be timeouts from message brokers, JDBC, HTTP clients, executors, Kubernetes/containers, and shutdown hooks. Design deadlines to fit the process's total time budget.

**Version note:** in Spring Boot 3.3, Web server graceful shutdown is enabled with `server.shutdown=graceful`; do not copy defaults from newer versions into a 3.3 app without checking.

## 13. How to test callbacks and phases quantitatively

### 13.1. Observing context closing time

In the demo, you can measure around `close()` using `System.nanoTime()`:

```java
long start = System.nanoTime();

context.close();

long elapsedMs =
        TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start);

System.out.println("Close duration (ms): " + elapsedMs);
```

This is an **integration snippet**, not a standalone runnable file; it requires importing `java.util.concurrent.TimeUnit` and a `context` variable. Because the demo already uses `try-with-resources` to call `close()` automatically, when measuring manually **replace the automatic close** with an explicit close at a chosen spot to avoid calling close twice and skewing measurements.

Expect total close time to include the 300 ms drain wait under normal conditions, though measurements depend on runtime scheduling; **do not write an assertion requiring exactly 300 ms**.

### 13.2. Checking callback after completion

In a unit test of your implementation, you can pass a custom `Runnable` to `stop(Runnable)` to see when the callback runs:

```java
CountDownLatch completed = new CountDownLatch(1);

consumer.stop(completed::countDown);

boolean finished = completed.await(2, TimeUnit.SECONDS);

if (!finished) {
    throw new AssertionError("Stop callback was not invoked");
}

if (consumer.isRunning()) {
    throw new AssertionError("Consumer is still running after callback");
}
```

This is an **integrated test snippet**, requiring a running `consumer` instance and importing `CountDownLatch`/`TimeUnit`. In real apps, also verify tasks stopped, resources closed, and no new messages are accepted after the callback. `isRunning()==false` alone could have been set wrongly in code.

### 13.3. Checking callback runs exactly once

```java
AtomicInteger callbacks = new AtomicInteger();
CountDownLatch completed = new CountDownLatch(1);

consumer.stop(() -> {
    callbacks.incrementAndGet();
    completed.countDown();
});

if (!completed.await(2, TimeUnit.SECONDS)) {
    throw new AssertionError("Callback missing");
}

if (callbacks.get() != 1) {
    throw new AssertionError("Expected exactly one callback");
}
```

This is a test snippet requiring imports for `AtomicInteger`, `CountDownLatch`, and `TimeUnit`, plus a real consumer. Checking right after the latch confirms at least one callback ran and the count up to that moment, yet **is not enough** to prove absolutely that no late invocation happens under a race condition. To test concurrency thoroughly, use multi-threaded controlled tests, state machines, or assertions on completion futures across all stop paths.

### 13.4. Testing multiple phases

With the section 6 project, observe these lines:

```text
START writer
START consumer
STOP consumer: callback
STOP writer
```

If you intentionally omit `callback.run()` in Consumer in a separate test copy, Spring may wait for the entire phase-200 timeout before stopping Writer. **Do not keep that broken code in production**; restore the callback after the experiment.

### 13.5. Simulating a controlled timeout

Change `Thread.sleep(300)` in Consumer to `Thread.sleep(5000)` while the phase timeout property remains `3s`. Expect the lifecycle processor to expire its phase-200 wait before Consumer finishes, breaking the desired shutdown order guarantee. Do not put this kind of test into a shared pipeline if threads/resources are not cleaned up. Always restore the proper value after experimenting.

## 14. Typical errors and fixes

| Symptom | Common cause | Fix |
|---|---|---|
| Context close waits nearly the exact phase timeout | `stop(Runnable)` forgot to invoke callback | Place completion signal at the end of stop path, test with latch |
| Context closes quickly yet worker still runs | Callback invoked right after `shutdown()` | Await real termination/flush before callback |
| Stop logic in `stop()` never runs | Overrode `stop(Runnable)` without delegating logic | Use one shared stop routine for both paths or delegate properly |
| Bean not stopped on context close | `isRunning()` returns false, bean unregistered, or context didn't close normally | Check `start`/`isRunning`, bean registration, and shutdown signal |
| Writer closed while Consumer still needs to write | Wrong phase, early callback, or phase timeout | Give Consumer higher phase than Writer; finish drain before callback |
| Same-phase beans stop in nondeterministic order | No phase/dependency constraint | Use distinct phases or proper dependency relationships |
| Only called `executor.shutdown()` | `shutdown` does not wait for accepted tasks | Use `awaitTermination`/completion callback and force-close fallback |
| Executor rejects cleanup task | Executor already shut down or queue full | Catch `RejectedExecutionException` with fallback that preserves callback |
| No callback on error | Exception escapes worker before `callback.run()` | Add error handling and one completion point in `finally` after cleanup |
| Callback runs twice | Called in `try` and `finally` or multiple success/error branches | Design a single callback point and guard under concurrency |
| Timed out yet resource still running | No resource-level timeout/force-close | Add deadlines, cancellation, termination check, and failure reporting |
| Used `@PreDestroy` instead of lifecycle callback | `@PreDestroy` does not participate in phase completion like `stop(Runnable)` | Put drain in lifecycle stop; keep destroy for supplemental cleanup |
| Ran `kill -9` and saw no callback | JVM had no chance for orderly shutdown | Test with close/SIGTERM and have recovery mechanisms for forced termination |
| `@Lazy` prevented SmartLifecycle bean creation | Confusing lazy policy with auto-start requirements | Auto-starting SmartLifecycle normally pulls bean at startup; check bean discovery |
| Multiple same-phase beans make shutdown time hard to estimate | Phase waits for group callbacks, not additive per-bean timeouts | Measure per phase, log durations, and balance shutdown budget |

### Code review checklist

- [ ] Bean is actually a Spring-managed `SmartLifecycle`.
- [ ] `start()` and `isRunning()` reflect the worker's real state.
- [ ] `getPhase()` expresses sensible dependency ordering.
- [ ] `stop(Runnable)` never invokes the callback before cleanup completes.
- [ ] All stop exit paths invoke the callback exactly once, including handled errors.
- [ ] If the bean is already stopped, the callback is not forgotten.
- [ ] Failure to submit/start the cleanup task is handled.
- [ ] Resource-level timeouts/cancellations exist, not just Spring's timeout.
- [ ] Required dependencies are not closed before draining consumers.
- [ ] Direct `stop()` and `stop(Runnable)` have no conflicting logic.
- [ ] Tests cover missing/double callbacks and phase ordering.
- [ ] Metrics/logs exist for forced shutdown and unfinished work.
- [ ] Shutdown duration fits within orchestrator limits.

## 15. Practice exercises

Using the section 6 project, change only one thing at a time and restore it before trying the next.

**Exercise 1 — verify the callback contract:** run the original demo. Explain why `STOP writer` appears only after `STOP consumer: callback`, even though `stop(Runnable)` returned before draining finished.

**Exercise 2 — intentionally drop the callback:** in a test copy, temporarily remove `callback.run()` in Consumer. Set the phase timeout to `3s` and measure `context.close()` duration; look for signs the phase waited until timeout, then restore the callback immediately.

**Exercise 3 — early callback:** move `callback.run()` right after `shutdownWorker.start()` in an experimental branch for learning only. Observe that Writer can stop before Consumer prints `drained`. Explain the risk when Consumer needs Writer to flush data.

**Exercise 4 — swap phases:** give Writer phase 300 and Consumer phase 200 and rerun. Explain why the new order no longer matches the dependency "Consumer uses Writer during drain".

**Exercise 5 — change timeout:** increase `Thread.sleep` from 300 ms to 5 seconds while keeping phase timeout at 3 seconds. Observe the impact on total shutdown and stop order; do not use this as a performance benchmark.

**Exercise 6 — test interrupt error:** in a unit test, interrupt the cleanup thread and check whether the callback is still invoked. Explain why **callback invoked** does not mean sufficient data was flushed.

**Exercise 7 — real executor:** replace the simulation with an `ExecutorService` running a short task; use `shutdown()`, `awaitTermination`, and finally the callback. Test a task that ignores interrupts in isolation to see `shutdownNow()`'s limits.

**Exercise 8 — stop called multiple times:** invoke `stop(Runnable)` concurrently from two threads in a unit test and observe that the demo code can spawn two shutdown workers. Redesign using a shared completion future before production use; each callback must receive one completion signal for its call.

**Exercise 9 — inspect relationship with destroy:** add `@PreDestroy` printing a marker in Writer. Verify lifecycle stop runs before the destroy callback during normal context close without closing resources twice.

**Exercise 10 — graceful Web server:** in a test Web application using Spring Boot 3.3, enable `server.shutdown=graceful` and write a `SmartLifecycle` consumer. Identify the two distinct stop jobs, their phase order, total shutdown budget, and why accurate readiness/termination is needed.

### Self-assessment questions

1. Why must `callback.run()` not be called right after `ExecutorService.shutdown()`?
2. If `stop(Runnable)` never invokes the callback, how does `DefaultLifecycleProcessor` typically react?
3. For beans at phases 100 and 200, what is the start/stop order?
4. Does `LifecycleProcessor` call `stop()` or `stop(Runnable)` on a `SmartLifecycle`?
5. What is `SmartLifecycle`'s default phase? What phase is a plain `Lifecycle` treated as?
6. If a worker finishes after the phase timeout, does invoking the callback late still guarantee Writer has not stopped?
7. Why is `@PreDestroy` not a direct substitute for phased callbacks?
8. When `Thread.start()` or `executor.execute()` fails, why must the callback path still be handled?
9. How do you ensure the callback runs exactly once when two concurrent stop requests arrive?
10. When `server.shutdown=graceful` is enabled, does the application's message consumer automatically stop gracefully?

## 16. Conclusion

`SmartLifecycle.stop(Runnable callback)` is a **shutdown coordination contract** between your bean and Spring's `LifecycleProcessor`. You are allowed to return immediately and stop resources asynchronously, yet you **must invoke `callback.run()` after stopping completes**. If you omit the callback, Spring may wait out the phase timeout; if you invoke it too early, Spring may proceed to stop dependencies the worker still needs.

In a system with dependencies, combine **proper `getPhase()`**, **a deadline-bounded drain process**, **truthful running state**, **error handling**, **exactly-once callbacks**, and **completion testing**. `spring.lifecycle.timeout-per-shutdown-phase` is Spring's waiting limit, not magic that closes hung resources.

### Official documentation

- Spring Framework 6.1 — `SmartLifecycle` Javadoc, callback obligation and phases: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `DefaultLifecycleProcessor` Javadoc, per-phase timeout and start/stop order: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Spring Framework 6.1 — Customizing the Nature of a Bean / `SmartLifecycle`: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-nature.html
- Spring Boot 3.3 — Graceful Shutdown, `server.shutdown=graceful`, and `spring.lifecycle.timeout-per-shutdown-phase`: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html