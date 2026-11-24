# spring.lifecycle.timeout-per-shutdown-phase and Shutdown Time Limits in Spring Boot

**Topic:** Spring Boot Application Runtime → **Application Shutdown**. This lesson explains `spring.lifecycle.timeout-per-shutdown-phase`, Spring's rule for stopping `SmartLifecycle` beans by `phase`, the boundaries of this wait time, the difference between web server graceful shutdown and stopping background work, and coordination with OS and Kubernetes deadlines. It includes a runnable **Java 17+ / Spring Boot 3.5.x** project to measure callback milestones yourself, simulate one slow phase and one fast phase, and verify behavior when exceeding the timeout.

**Key takeaway:** This timeout is the **wait budget per shutdown phase**, not "the entire app is forced to stop after N seconds", nor "Spring automatically kills threads/rolls back transactions after N seconds". Safe shutdown requires controlling new requests, in-flight tasks, completion callbacks, external I/O timeouts, and platform deadlines.

## 1. Learning Outcomes

After this lesson, you can:

1. Correctly read `spring.lifecycle.timeout-per-shutdown-phase=20s` and explain the time unit.
2. Know that Spring Boot 3.5 defaults to **30 seconds per phase**; distinguish this from the **10-second** default of `DefaultLifecycleProcessor` in standalone Spring Framework 6.2 without Boot's override.
3. Distinguish `SmartLifecycle.stop(Runnable)`, `Lifecycle.stop()`, `@PreDestroy`, `DisposableBean.destroy()`, and JVM shutdown hooks.
4. State the `phase` stop rule **higher first, lower later**; beans in the same phase share one wait budget.
5. Know that the `Runnable` callback tells Spring "the component finished its stop procedure", and why you must neither forget it nor call it too early.
6. Measure directly that when a slow phase times out, the next phase still runs, **without claiming** the slow task was cancelled.
7. Demonstrate that a component stopping asynchronously can keep running after `ApplicationContext.close()` returns due to timeout expiration.
8. Distinguish the lifecycle processor timeout from graceful HTTP request draining, executor termination, JDBC/socket timeouts, and Kubernetes `terminationGracePeriodSeconds`.
9. Run an example with an in-flight HTTP request and explain why the response may succeed, reset, or error depending on server, connection, and timing.
10. Design worker → dependency stop ordering, halt new work intake, handle retries/idempotency, and verify no resource leaks.
11. Identify startup/shutdown errors and QA criteria using log timestamps, callbacks, and resource state.
12. Choose shutdown budgets from real measurements rather than raising properties arbitrarily.

## 2. What Does This Property Actually Control?

Standard configuration in `src/main/resources/application.properties`:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Equivalent YAML form:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Both configure the wait duration Spring Boot passes to lifecycle processing when the context closes. `Duration` values should include **explicit units**, such as `500ms`, `5s`, `20s`, `1m`. Do not omit units and guess whether readers will interpret seconds or milliseconds.

**Exact scope:** Spring Framework provides `DefaultLifecycleProcessor`, which manages `Lifecycle`/`SmartLifecycle` beans in the `ApplicationContext`. `SmartLifecycle` beans stop in descending phase order. For each phase group, the processor invokes `stop(Runnable callback)` and waits for callbacks up to that phase's configured duration. Once time expires, the processor may log components that have not called back yet and **move on** to the next phase.

**Outside its guarantee:** This property does not impose a global deadline on `@PreDestroy`, custom callbacks, HTTP clients, network sockets, manually created thread pools, committing transactions, or non-Spring shutdown hooks. A poorly implemented synchronous `stop(Runnable)` that never returns can stall the entire shutdown chain past the configured time; this is not preemptive cancellation.

### 2.1. Boot Defaults Differ from Plain Framework Defaults

| Subject | Default in the version covered here | Meaning |
|---|---|---|
| Spring Boot **3.5** — `spring.lifecycle.timeout-per-shutdown-phase` | **30s** | Boot applies this to the lifecycle processor it configures |
| Spring Framework **6.2** — standalone `DefaultLifecycleProcessor` | **10,000 ms (10s)** | Default of the implementation without Boot/custom override |
| `server.shutdown` in Spring Boot **3.5** | `graceful` | Graceful shutdown is enabled by default for supported embedded web servers |
| `spring.main.register-shutdown-hook` in Spring Boot **3.5** | `true` | Spring Boot registers the standard JVM shutdown hook |

Do not read 10 seconds from Spring Framework Javadoc and claim Spring Boot 3.5 defaults to 10 seconds. Likewise, do not assume Boot 3.5 defaults match all Boot 2.x/3.x/4.x lines. When an app uses a custom `LifecycleProcessor` or another version, check configuration metadata and actual runtime behavior.

### 2.2. Does This Timeout Apply Per Bean?

**No.** The property name explicitly says `per-shutdown-phase`. Consider three beans:

- `workerA` phase 200
- `workerB` phase 200
- `databaseAdapter` phase 100

With a 10s timeout per phase, both beans in phase 200 are asked to stop and the processor waits on **a single shared 10-second budget** for phase 200 callbacks; it does not become 10 + 10 seconds merely because two beans exist. Afterward, phase 100 gets its **own** wait budget. Total duration can exceed 10 seconds, especially with multiple phases, bean destruction, hooks, or blocking I/O.

The key rule is **grouping by phase value, not by package or business type**.

## 3. Diagram from SIGTERM to Application Termination

~~~text
Kubernetes / systemd / terminal sends SIGTERM
         |
         v
JVM shutdown hook registered by Spring Boot
         |
         v
ApplicationContext.close()
         |
         +--> ContextClosedEvent
         |
         +--> LifecycleProcessor.onClose()
         |       |
         |       +--> highest phase: e.g. web-server graceful stop
         |       |       - stop intake / drain requests per server
         |       |       - wait for callback up to timeout for this phase
         |       |
         |       +--> phase 200: ask worker to stop
         |       |       - stop(Runnable callback)
         |       |       - wait for callback up to phase 200 timeout
         |       |
         |       +--> phase 100: stop dependency
         |               - stop(Runnable callback)
         |               - separate phase 100 timeout budget
         |
         +--> destroyBeans()
         |       - @PreDestroy / DisposableBean / destroy-method
         |
         +--> close BeanFactory and remaining context work
         |
         v
context.close() returns; JVM still follows the shutdown process
~~~

In this example, the ordering is a conceptual model; Spring Boot's own infrastructure beans have specific phases that you do not rearrange arbitrarily, and `depends-on` relationships can alter order relative to phases. `ContextClosedEvent` is published when `doClose` begins, **before** `LifecycleProcessor` stop coordination in standard `AbstractApplicationContext`.

**Two independent boundaries:** Spring may finish traversing all phase groups after timeouts expire while an asynchronous thread is still running. When the JVM is shutting down from SIGTERM, it can terminate the process once hooks finish **without waiting** for that background thread to end. Do not think "thread still running" means it is allowed to finish in every process-termination mode.

### 3.1. Readiness Milestone

When an app begins valid shutdown, Spring Boot can publish `ReadinessState.REFUSING_TRAFFIC` so infrastructure stops routing traffic. This signal **does not** immediately block requests sent directly to the Pod IP while the HTTP connector is still active. Once the web server actually enters graceful shutdown, it applies its policy to stop accepting new requests.

Therefore, distinguish **publishing availability state**, **readiness probes**, **EndpointSlice/load-balancer routing updates**, and **the web server stopping new acceptance**. Those actions are not guaranteed to synchronize instantaneously.

## 4. Phase Rule: Start Lower First, Stop Higher First

`SmartLifecycle` lets a bean declare its phase via `getPhase()`. Spring Framework uses phases to determine order:

~~~text
Startup (onRefresh):
 phase -100 → phase 0 → phase 100 → phase 200

Shutdown (onClose):
 phase 200 → phase 100 → phase 0 → phase -100
~~~

This helps ensure during shutdown that a **dependent worker** stops before the **dependency service** it needs for cleanup. If component A needs database adapter B during stop to flush final data, B must not be closed before A.

Key details to remember:

- `SmartLifecycle` defaults to `getPhase() = Integer.MAX_VALUE` in Spring Framework 6.2 unless overridden; this differs from phase 0 of some plain `Lifecycle` beans.
- `SmartLifecycle.isAutoStartup()` defaults to true; eligible beans auto-start on refresh and are managed on close.
- `depends-on` affects real ordering: dependent beans stop before dependencies even if some phases suggest otherwise.
- Beans sharing the same phase have no guaranteed business sequence to rely on. When order matters, use distinct phases or explicit dependencies.
- The framework manages **running `Lifecycle` beans**; beans not running do not have the same obligation to receive stop.
- Setting arbitrary min/max phase values can interact unexpectedly with the framework's web server, listener containers, or schedulers. Check the phases of actual components before overriding.

**Example problem:** An HTTP listener receives commands, a worker processes a queue, and an adapter sends results to a broker. Safe design: block intake, let the worker drain/cancel, then close the broker adapter. Combine phases, dependencies, readiness, and broker acknowledgements—do not just tweak two phase numbers.

## 5. Stop Callback: The Obligation That Governs Waiting

### 5.1. The SmartLifecycle.stop(Runnable) Contract

`org.springframework.context.SmartLifecycle` declares:

~~~java
void stop(Runnable callback);
~~~

When the processor asks a `SmartLifecycle` bean to stop, it supplies a callback. **The bean must call `callback.run()` once its stop procedure has finished**. For a fast synchronous stop:

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    } finally {
        callback.run();
    }
}
~~~

This is a **method snippet** to place inside a class implementing `SmartLifecycle` with a contract-compliant `stop()` method. In systems with cleanup errors, log/apply appropriate error policies rather than blindly reporting success.

For an asynchronous stop:

~~~java
@Override
public void stop(Runnable callback) {
    executor.execute(() -> {
        try {
            stopReceivingNewMessages();
            awaitOrCancelInFlightWork();
            closeOwnedResources();
        } finally {
            callback.run();
        }
    });
}
~~~

This is **pseudocode in the form of a Java method**, since `executor` and the three cleanup helpers depend on the real system. Watch out for `executor.execute(...)` rejecting tasks during shutdown: if a stop task cannot be scheduled, have a synchronous fallback, log the failure, and still satisfy the lifecycle contract per policy.

### 5.2. Two Opposite Bugs

- **Forgetting the callback:** The processor waits until the phase timeout expires, records the bean as unfinished, and moves to the next phase. Shutdown stretches out, and the app risks destroying dependencies while the worker is still running.
- **Calling the callback too early:** The bean calls `callback.run()` when the task was merely *asked* to stop, while queued work remains and resources are still open. The processor thinks it finished and stops other dependencies, causing lost events, transaction errors, or use-after-close bugs.

Both are lifecycle bugs. The callback does not mean "stop request received", it means "**stop processing completed per contract**", including designed and verified timeout/failure policies.

### 5.3. The Property Does Not Cancel a Blocking stop()

If code does:

~~~java
@Override
public void stop(Runnable callback) {
    doBlockingNetworkCallWithNoTimeout();
    callback.run();
}
~~~

then `stop(Runnable)` may never return for the processor to reach its latch-wait step. Depending on the implementation, configuring "2s" **does not turn** this network call into one interrupted after 2 seconds. The right approach is configuring a network client timeout, or launching the stop operation asynchronously and returning so the lifecycle processor waits on the callback within the budget.

Do not put `Thread.sleep(60000)` inside a synchronous `stop(Runnable)` and conclude Spring ignores the property when shutdown takes 60 seconds. That tests a **blocking method**, not the callback-wait timeout.

## 6. Hands-On Java 17 and Spring Boot 3.5 Application

The project below has two auto-starting `SmartLifecycle` beans, with **two independent stop phases** on close: the phase 200 bean stops slowly, and the phase 100 bean stops fast. A separate `Thread` performs async stopping to illustrate the callback and show that timeout **does not automatically kill threads**. A sleeping HTTP endpoint lets you observe graceful web server behavior in server mode.

### 6.1. Create the Maven Project

In Spring Initializr, generate:

- Group: `com.example`
- Artifact: `shutdown-phase-lab`
- Package: `com.example.shutdownphase`
- Java: **17**
- Spring Boot: **3.5.x**
- Build: Maven, Packaging: Jar
- Dependency: **Spring Web**

Keep the `pom.xml` and `mvnw`/`mvnw.cmd` generated by Initializr. Structure:

~~~text
shutdown-phase-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/shutdownphase/
    ShutdownPhaseLabApplication.java
    TimedLifecycle.java
    LifecycleBeans.java
    SlowController.java
  src/main/resources/application.properties
~~~

All four Java files below are complete when placed in the exact package with Spring Boot's Maven classpath. Java 17+ suffices; virtual thread APIs are not used here. Do not create extra classes with the same public class names.

### 6.2. Main: Controlled Context Closure to Measure Budget

File `ShutdownPhaseLabApplication.java`:

~~~java
package com.example.shutdownphase;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import java.util.concurrent.TimeUnit;

@SpringBootApplication
public class ShutdownPhaseLabApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(
                        ShutdownPhaseLabApplication.class, args);

        boolean autoClose = context.getEnvironment()
                .getProperty("lab.auto-close", Boolean.class, true);

        if (!autoClose) {
            System.out.println("LAB_WEB_MODE_READY");
            return;
        }

        System.out.println("LAB_CLOSE_REQUESTED");
        long begin = System.nanoTime();
        context.close();
        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - begin);
        System.out.println(
                "LAB_CLOSE_RETURNED elapsedMs=" + elapsedMs);
    }

    @EventListener(ContextClosedEvent.class)
    public void onContextClosed() {
        System.out.println("LAB_CONTEXT_CLOSED_EVENT");
    }
}
~~~

**Two modes:** By default `lab.auto-close=true` makes `main` call `context.close()` immediately after Boot completes startup, letting us measure close time **outside the JVM shutdown hook**. When `lab.auto-close=false`, the app keeps the web server running for HTTP testing and awaits a stop signal from the terminal/container.

Because `ContextClosedEvent` belongs to context close lifecycle, `LAB_CONTEXT_CLOSED_EVENT` appears before the stop-phase markers in the example. `elapsedMs` is the **duration of `context.close()`**, not actual JVM exit time, excluding external shutdown hook waits or external supervisors. Lab-spawned stop threads may still exist when close returns due to timeout.

### 6.3. TimedLifecycle: Simulating Asynchronous Cleanup

File `TimedLifecycle.java`:

~~~java
package com.example.shutdownphase;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;

public final class TimedLifecycle implements SmartLifecycle {

    private final String name;
    private final int phase;
    private final long stopDelayMs;
    private final AtomicBoolean running = new AtomicBoolean();

    public TimedLifecycle(
            String name, int phase, long stopDelayMs) {
        if (stopDelayMs < 0) {
            throw new IllegalArgumentException(
                    "stopDelayMs must be >= 0");
        }
        this.name = name;
        this.phase = phase;
        this.stopDelayMs = stopDelayMs;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return phase;
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("LAB_START " + name
                    + " phase=" + phase);
        }
    }

    @Override
    public void stop() {
        if (running.compareAndSet(true, false)) {
            System.out.println("LAB_STOP_DONE " + name
                    + " phase=" + phase);
        }
    }

    @Override
    public void stop(Runnable callback) {
        if (!isRunning()) {
            callback.run();
            return;
        }

        System.out.println("LAB_STOP_BEGIN " + name
                + " phase=" + phase
                + " delayMs=" + stopDelayMs);

        Thread cleanup = new Thread(() -> {
            try {
                Thread.sleep(stopDelayMs);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                System.out.println("LAB_STOP_INTERRUPTED " + name);
            } finally {
                // No real external I/O in this lab.
                stop();
                System.out.println("LAB_STOP_CALLBACK " + name);
                callback.run();
            }
        }, "lab-cleanup-" + name);

        // Demo only: so we can observe the callback arriving late
        // after context.close() returns due to phase timeout.
        cleanup.setDaemon(false);
        cleanup.start();
    }
}
~~~

**Mechanism:**

1. `start()` updates `running=true` when the container starts the bean (auto-start by default). Since there is no external resource in the lab, the flag models state accurately.
2. `stop(Runnable)` **does not block the caller**. It spawns a cleanup thread and returns. Thus `DefaultLifecycleProcessor` can start counting/waiting for the callback against the phase timeout.
3. `Thread.sleep(stopDelayMs)` only simulates a delay. It performs **no** real business work or network I/O.
4. `stop()` uses compare-and-set to mark stopped only once.
5. `callback.run()` executes **after** `stop()` inside `finally`, even if sleep is interrupted. Without real resources in the demo, interruption finishes the stop procedure immediately.
6. The cleanup thread is set **non-daemon** so when `context.close()` is called directly from `main`, we have a chance to see the callback arrive after timeout. **Never copy keeping a non-daemon thread like this into production**: it can keep the JVM alive, and when the JVM runs shutdown hooks on SIGTERM, non-daemon threads are **still not guaranteed** to finish before the JVM exits.
7. Do not spawn `new Thread` per stop operation in a real app when a lifecycle owner and managed executor already exist. This example uses it solely to clearly illustrate "processor stops waiting" vs. "task actually stops".

A production component must release its own resources and coordinate task state. `stop()`/`stop(Runnable)` must be idempotent and tolerate repeated calls; the sample code is designed for **one start/stop cycle in the lab**, not a full state machine for repeated restarts.

### 6.4. Two Beans with Specific Phases

File `LifecycleBeans.java`:

~~~java
package com.example.shutdownphase;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LifecycleBeans {

    @Bean("highPhase")
    SmartLifecycle highPhase(
            @Value("${lab.high-stop-ms:1000}") long delayMs) {
        return new TimedLifecycle("high", 200, delayMs);
    }

    @Bean("lowPhase")
    SmartLifecycle lowPhase(
            @Value("${lab.low-stop-ms:0}") long delayMs) {
        return new TimedLifecycle("low", 100, delayMs);
    }
}
~~~

Both beans have no mandatory dependency on each other, so phase governs ordering. Spring starts from phase 100 to phase 200 and stops **in reverse**. Declare the `@Bean` return type as `SmartLifecycle` so the container recognizes the interface properly. Because `@Configuration(proxyBeanMethods=false)` does not call factory methods from one another, no bean factory proxying is needed here.

**Lab defaults:** high phase 200 stops after about 1 second; low phase 100 stops almost immediately. You can vary each delay independently via command line `--lab.high-stop-ms=6000` and `--lab.low-stop-ms=6000`.

### 6.5. Endpoint to Test In-Flight HTTP Requests

File `SlowController.java`:

~~~java
package com.example.shutdownphase;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SlowController {

    @GetMapping("/lab/slow")
    public ResponseEntity<String> slow(
            @RequestParam(defaultValue = "7000") long ms) {
        if (ms < 0 || ms > 15_000) {
            return ResponseEntity.badRequest()
                    .body("ms must be between 0 and 15000");
        }

        System.out.println("LAB_REQUEST_BEGIN ms=" + ms);
        try {
            Thread.sleep(ms);
            System.out.println("LAB_REQUEST_DONE ms=" + ms);
            return ResponseEntity.ok("completed");
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            System.out.println("LAB_REQUEST_INTERRUPTED");
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("interrupted");
        }
    }
}
~~~

This endpoint exists only to simulate an in-flight request while the web server stops gracefully. Using `Thread.sleep` on a request thread is acceptable only in a **lab**; production must have real business logic and proper I/O timeouts. Never expose an unbounded sleeping API to the Internet. The HTTP status returned when a connection is shut down also depends on the server and connection state.

### 6.6. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=shutdown-phase-lab

# Listen locally only for the experiment.
server.address=127.0.0.1
server.port=8080

# Spring Boot 3.5 defaults to graceful; declare explicitly.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=2s

# Main closes automatically after run() by default.
lab.auto-close=true

# Two lifecycle beans for the lab.
lab.high-stop-ms=1000
lab.low-stop-ms=0
~~~

`2s` is **intentionally chosen for the lab**, not Spring Boot 3.5's default. Boot 3.5 defaults to **30s** when not overridden. To test the default, remove/stop overriding the property or pass your desired value; note that command-line arguments take precedence over file configuration per Boot's property sources mechanism.

With `lab.auto-close=true`, the web server starts and closes quickly; pass `--lab.auto-close=false` for HTTP tests, otherwise there will be no time to call `/lab/slow`.

## 7. Experiment A: Phases Complete Before Timeout

### 7.1. Build

From the project directory, Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw clean package
java -jar target/shutdown-phase-lab-0.0.1-SNAPSHOT.jar
~~~

Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd clean package
java -jar target/shutdown-phase-lab-0.0.1-SNAPSHOT.jar
~~~

If the version in `pom.xml` differs from `0.0.1-SNAPSHOT`, use the actual JAR name in `target/`. Java should be 17 or newer; Spring Boot 3.5 may require a newer version if you choose different dependencies/versions.

### 7.2. Milestones to Observe

A **valid illustrative** log excerpt (omitting framework and web server logs):

~~~text
LAB_START low phase=100
LAB_START high phase=200
LAB_CLOSE_REQUESTED
LAB_CONTEXT_CLOSED_EVENT
LAB_STOP_BEGIN high phase=200 delayMs=1000
LAB_STOP_DONE high phase=200
LAB_STOP_CALLBACK high
LAB_STOP_BEGIN low phase=100 delayMs=0
LAB_STOP_DONE low phase=100
LAB_STOP_CALLBACK low
LAB_CLOSE_RETURNED elapsedMs=...
~~~

`elapsedMs` and web server log verbosity are not fixed; the key points are:

- `LAB_START low` appears before `LAB_START high` during phase-ordered auto-start.
- `LAB_STOP_BEGIN high` happens before `LAB_STOP_BEGIN low`.
- Since high stop takes ~1 second and the phase budget is 2 seconds, `LAB_STOP_CALLBACK high` arrives **before** low starts stopping.
- `context.close()` returns after the callbacks provided no other phase blocks; HTTP web server infrastructure may add minor overhead.
- Hooks/context destruction may still print extra logs; do not byte-match the entire program's stdout.

This is the **positive control**: the timeout is large enough for the component in phase 200. Only upon seeing the callback can you conclude the component fulfilled its stop contract.

## 8. Experiment B: Phase 200 Exceeds Timeout Yet Phase 100 Still Runs

Keep `spring.lifecycle.timeout-per-shutdown-phase=2s` and raise the high delay to 6 seconds:

~~~bash
java -jar target/shutdown-phase-lab-0.0.1-SNAPSHOT.jar --lab.high-stop-ms=6000
~~~

The app will call `context.close()` after startup. An **expected chronological marker sequence**:

~~~text
LAB_CLOSE_REQUESTED
LAB_CONTEXT_CLOSED_EVENT
LAB_STOP_BEGIN high phase=200 delayMs=6000

... processor waited nearly 2000ms ...
... shutdown log that phase 200 still has unfinished beans, depending on logger ...

LAB_STOP_BEGIN low phase=100 delayMs=0
LAB_STOP_DONE low phase=100
LAB_STOP_CALLBACK low
LAB_CLOSE_RETURNED elapsedMs=...

... afterward the high cleanup thread may still be running ...
LAB_STOP_DONE high phase=200
LAB_STOP_CALLBACK high
~~~

Do not treat the ellipsis lines as literal stdout; they **explain the milestones**. In the lab, `context.close()` runs outside the JVM shutdown hook and the high cleanup thread is non-daemon, so you can see `LAB_STOP_DONE high` **after** `LAB_CLOSE_RETURNED`. That proves: timeout makes the processor **stop waiting for the callback**, without automatically cancelling sleep or guaranteeing all external resources are closed.

Expect `elapsedMs` around 2 seconds plus overhead from the web server, lower phase, and destruction—**not exactly 2000ms**. If the machine is slow or infrastructure has extra phases, the number can be noticeably higher.

### 8.1. Interpreting the Behavior Correctly

| Observation | Valid conclusion | Invalid inference |
|---|---|---|
| Phase 200 timed out | Processor did not receive callback within the 2s budget | The worker was definitely cancelled |
| Phase 100 still received stop | Processor moved forward after timeout | High's dependencies released all resources |
| `LAB_CLOSE_RETURNED` appeared before high callback | Context finished budget-bounded processing in the lab | The entire process exited |
| High callback appeared late | Demo cleanup thread kept running past the wait window | In production SIGTERM the callback will surely finish in time |
| Bean destroy ran while high had not called back | Risk of cleanup overlap under poor design | Spring rolls back external operations |

### 8.2. Why Are Late Callbacks So Dangerous?

Suppose the high phase 200 worker needs the low phase 100 adapter to commit results. When high takes 6 seconds with only a 2-second budget, the processor begins stopping the low adapter while the high worker still uses it. Closed-connection exceptions, lost acks, message redeliveries, or unpersisted data can result.

No single timeout number fixes dependency design by itself. You need:

- Stop **intake** before workers drain.
- Workers with deadlines and cooperative cancellation.
- Stop dependencies **after workers finish**, not merely after the processor loses patience.
- Coordinate `depends-on` and phases to match real needs.
- Persist results/offsets/transactions at the right boundaries and support idempotency on retry.

## 9. Experiment C: Both Phases Are Slow

Run:

~~~bash
java -jar target/shutdown-phase-lab-0.0.1-SNAPSHOT.jar --lab.high-stop-ms=6000 --lab.low-stop-ms=6000
~~~

With a **2s budget per phase**, the processor can wait roughly 2s on phase 200 and **another** roughly 2s on phase 100, so `close()` returns after roughly **4s plus overhead** (assuming no other slow phases). This is the clearest proof that the property is **not** a total 2s deadline.

If 10 phases exist with a 20s timeout, you cannot claim total process shutdown is always under 20s. Lifecycle waiting alone can exceed that, and `@PreDestroy` plus other cleanup do not automatically fall under that same budget.

In real apps, phases often stop much faster than their timeout; do not sum budgets as if every phase always hits its limit. Use **observed p95/p99 + worst-case budget** to set policies.

## 10. Experiment D: Graceful Shutdown of an In-Flight HTTP Request

To keep the app running and accept requests, start in a separate terminal:

~~~bash
java -jar target/shutdown-phase-lab-0.0.1-SNAPSHOT.jar --lab.auto-close=false --spring.lifecycle.timeout-per-shutdown-phase=10s
~~~

Once you see `LAB_WEB_MODE_READY`, use another terminal:

~~~bash
curl -i "http://127.0.0.1:8080/lab/slow?ms=7000"
~~~

Wait for the server console to print `LAB_REQUEST_BEGIN ms=7000`, then send Ctrl+C to the app terminal or use a valid SIGTERM to stop the process. Do not use `kill -9` or an IDE terminate button that kills immediately.

**When the phase timeout is large enough**, embedded Tomcat graceful shutdown gives the in-flight request a chance to finish, so `curl` can receive HTTP 200 with body `completed`. Real-world outcomes still depend on the server, how signals reach the process, connection state, timing, and whether anything else closes before the request. Never claim one test command across all OSes always returns 200.

Retry with a fresh process using `--spring.lifecycle.timeout-per-shutdown-phase=2s` and the same 7-second request. When the web server stop phase has a shorter budget than the request, the connection may be cut or the client may receive an error/status depending on the embedded server and network. For **Tomcat, Jetty, or Reactor Netty**, new connections can be blocked at the network layer; for **Undertow in Boot 3.5**, rejecting new requests can return HTTP **503**. Do not force expecting 503 on `curl` for an in-flight request or use that status code as the sole test.

### 10.1. Distinguishing Three Durations

- `spring.lifecycle.timeout-per-shutdown-phase`: wait budget for lifecycle beans per **phase group**, including the Boot-supported web server graceful stop phase.
- `server.tomcat.connection-timeout` (if configured): protocol/connection wait, **not** a replacement for the full context stop budget.
- Business/HTTP client timeouts: limit operations inside controllers; Spring lifecycle does not turn them into per-request deadlines.

If the app uses custom request executors, async servlet requests, streaming, or gRPC, inspect the corresponding drain mechanisms rather than relying solely on the synchronous controller's `Thread.sleep` example.

## 11. Per-Phase Timeout Does Not Replace Other Timeouts

| Timeout/deadline | Enforcing subject | Behavior on expiration | Same meaning as shutdown phase? |
|---|---|---|---|
| `spring.lifecycle.timeout-per-shutdown-phase` | Spring `LifecycleProcessor` | Stops waiting on phase callbacks, moves on | Itself |
| `spring.task.execution.shutdown.await-termination-period` | Eligible Boot-managed executor | Wait duration for task executor | No |
| `spring.task.scheduling.shutdown.await-termination-period` | Eligible Boot-managed scheduler | Wait duration for scheduled tasks | No |
| `ExecutorService.awaitTermination(...)` | Code-owned Java executor | Returns false on timeout; does not interrupt | No |
| JDBC connection/query timeout | JDBC driver/pool/database | Acquire/query may fail or cancel per contract | No |
| HTTP request/read timeout | HTTP client/library | Request fails/cancels per policy | No |
| Kafka/RabbitMQ/JMS consumer shutdown | Listener container/broker client | Stops polling/acks/closes per own timeout | No |
| `terminationGracePeriodSeconds` | Kubernetes kubelet/container runtime | May send SIGKILL after grace | No |
| systemd `TimeoutStopSec` | systemd | May kill service if stop takes too long | No |
| CI/deploy rollout timeout | CD controller/platform | Reports failure/rollback per tool | No |
| Business operation deadline | Business logic | Retries/cancels/compensates per contract | No |

An application might set shutdown phase to 20s, HTTP client call timeout to 60s, and Kubernetes grace to just 15s. Even though each setting is "syntactically valid", they **conflict in budget**. The platform may kill the process before Spring finishes waiting 20s; conversely, setting Kubernetes grace too high can keep a Pod terminating longer than necessary.

## 12. Kubernetes: Calculating Deadlines from Outside In

Kubernetes specifies the Pod termination deadline via `terminationGracePeriodSeconds`. The default for a Pod is typically **30 seconds**, though Deployments/Pods or delete calls can override it. The grace period includes the `preStop` hook (if any), signal delivery time, shutdown inside the JVM, and the container actually exiting.

Manifest snippet **belonging inside `spec.template.spec` of a Deployment**, not a full Deployment YAML:

~~~yaml
terminationGracePeriodSeconds: 45
containers:
  - name: app
    image: example/app:1.0
    ports:
      - containerPort: 8080
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
~~~

This example only illustrates **termination budget + readiness probe**; running it requires a real image, the Actuator dependency, and corresponding probe configs. `example/app:1.0` is an architectural placeholder, not a verified existing image.

### 12.1. Layered Budget

An approximate budgeting formula (for design, **not** a mandatory runtime formula):

~~~text
T_grace_platform
    >= T_preStop
     + T_drain_or_propagation_margin
     + T_lifecycle_phases_expected
     + T_destroy_other
     + T_termination_overhead
~~~

Some steps run in parallel or overlap; do not double-count durations if instrumentation proves overlap. However, when sizing, ensure headroom for realistic worst cases.

Example: `preStop` needs 5s, expected max web drain is 15s, worker stop is 10s, bean destruction is 3s, and margin is 5s → roughly **38s** if awaited sequentially. Setting `terminationGracePeriodSeconds=45` gives an illustrative budget; measure p95/p99 and worst case before production use. **This is a hypothetical calculation**, not a universal default recommendation for every service.

### 12.2. PreStop and Signal Timing

In Kubernetes pod termination flow, when a Pod is marked terminating, kubelet may run the `preStop` hook and then send TERM to the process. The grace period is already ticking; a long `preStop` **reduces** the actual time left for Spring shutdown. If Java runs behind a shell wrapper that does not forward SIGTERM properly, Java may never receive the graceful signal and get killed when grace expires.

Therefore:

- Prefer a container entrypoint with proper signal forwarding, e.g., `exec java ...` inside a script if a script is necessary.
- Never use an unbounded `preStop sleep` just to "wait for the load balancer".
- Measure real EndpointSlice/readiness propagation and in-flight requests.
- Budget appropriately for consumer acks, flushes, checkpoints, and resource releases.
- Once grace expires, kubelet can force-stop; `finally`/`@PreDestroy`/callbacks are **not guaranteed** to run on forced kills.

### 12.3. Processor Timeout Is Not a "Pod Always Exits on Time" Switch

If a synchronous worker stop hangs, JDBC lacks timeouts, or a scheduler holds non-daemon threads, the process can linger. Even if Spring hits a phase timeout, the OS/container may still hold unclosed elements. On `SIGTERM`, the JVM runs hooks yet may also exit once hooks finish before async cleanup threads complete. That is why **every stop task needs deadlines and cooperative cancellation**, not just framework-level properties.

## 13. Managing Background Tasks During Shutdown

### 13.1. Stop Intake Before Draining

A background consumer/service can follow:

~~~text
RUNNING
   |
   +-- receives stopping signal
   v
QUIESCING: reject new jobs, pause polling/message intake
   |
   v
DRAINING: wait for or cancel in-flight work within deadline
   |
   v
FLUSHING: write valid committed checkpoint/offset/result
   |
   v
CLOSED: close clients/executors and invoke completion callback
~~~

Do not just set `isRunning=false` and invoke the callback while threads and sockets remain active. If an in-flight task can trigger external side effects and the process gets killed partway, you need idempotency keys, queue redelivery/ack semantics, or a durable job store to recover safely.

### 13.2. Bounded ExecutorService Shutdown Example

Illustrative Java snippet inside a bean owning an `ExecutorService`:

~~~java
private void terminateExecutor(ExecutorService executor) {
    executor.shutdown();
    try {
        if (!executor.awaitTermination(3, TimeUnit.SECONDS)) {
            executor.shutdownNow();
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                System.err.println(
                        "Executor did not terminate within budget");
            }
        }
    } catch (InterruptedException ex) {
        executor.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

This is a **method snippet** requiring imports for `ExecutorService`/`TimeUnit` and called by an owner with an appropriate lifecycle. `shutdownNow()` is only an interruption attempt and cannot force uncooperative I/O to halt. To make Spring wait on an asynchronous stop callback, run termination inside a dedicated stop worker and invoke the callback only after completion or applying the failure policy.

**Do not reuse the same `ExecutorService` for both regular jobs and the final stop callback** if by shutdown time that executor rejects new tasks. The stop method needs a safe fallback, otherwise the callback may be dropped.

### 13.3. When @PreDestroy Still Takes Longer Than the Property

`@PreDestroy`/`DisposableBean.destroy()` is Spring's bean destruction phase, running **after** normal lifecycle stop. `timeout-per-shutdown-phase` does not impose a forced deadline on a blocking `@PreDestroy` method. Thus this snippet:

~~~java
@PreDestroy
public void destroy() throws InterruptedException {
    Thread.sleep(60_000);
}
~~~

is an **anti-pattern snippet** placed in a Spring bean with `jakarta.annotation.PreDestroy`. Even with a 2s shutdown phase timeout, this can delay context closure by roughly 60s (unless the process is killed). Never put such a `sleep` in real apps; use real client deadlines and idempotent cleanup.

### 13.4. Distinguishing Framework-Managed Workers from Self-Created Threads

Spring can manage task executors, task schedulers, and messaging listener containers through lifecycle callbacks. However, a `new Thread(...).start()` or `Executors.newCachedThreadPool()` stored in a field without `@PreDestroy`/`SmartLifecycle` **will not stop automatically merely because of this property**.

For reliable shutdown, assign explicit ownership for closing resources, a stop path, and state durability. If a resource is already framework-managed, avoid double-closing it; check the library contract and configure corresponding timeouts.

## 14. Common Errors and Diagnostics

| Symptom | Causes to inspect | Evidence / remediation |
|---|---|---|
| Set `2s` yet total shutdown took 8s | Multiple phases or destroy/other hooks | Log start/end of each phase and `context.close()` |
| Phase timed out yet worker still logs | Callback has not arrived, thread was not killed | Compare `LAB_CLOSE_RETURNED` vs `LAB_STOP_CALLBACK` |
| Configured 20s yet 30s request was cut | Web server graceful phase lacked budget; short platform grace | Compare HTTP start/end, Tomcat logs, and SIGTERM timing |
| No stop callback observed | Forgot `callback.run()` or bean was not running | Check `stop(Runnable)`, `isRunning()`, and phase |
| Callback arrived before worker actually stopped | Invoked callback too early | Add in-flight metrics and resource close markers |
| Low-phase bean stopped before high-phase worker | Wrong phase/dependency design or direct stop call | Check `getPhase()`, `depends-on`, lifecycle processor |
| No graceful behavior in IDE | IDE terminate does not send proper signal | Test via console JAR and SIGTERM |
| `ContextClosedEvent` seen yet shutdown hangs | Event does not prove stop/destroy finished | Check callbacks, thread dumps, external timeouts |
| Team docs say Spring Boot 3.5 "defaults to 10s" | Confused Framework Javadoc with Boot config | Boot common properties: default is **30s** |
| ThreadPoolTaskExecutor stopped early and lost jobs | In-memory queue and executor policy did not wait | Durable source, retries/acks/idempotency |
| Whole Pod killed before callbacks | Kubernetes grace expired or entrypoint did not forward signal | Check Pod events, `preStop`, TERM/SIGKILL |
| DB connections not returned to pool | Unfinished I/O/transaction or leak | Hikari active/pending, connection close markers |
| Web server stopped yet broker consumer still pulls | Missing quiesce step or wrong phase/order | Stop intake, consumer lifecycle, broker offsets |
| Shutdown timeout set too high | Slows deployments/rollouts and exceeds platform limit | Measure p99 drain and set a sensible cap |
| Shutdown timeout set too low | Dependencies closed before workers flush | Raise deadline appropriately, make cleanup non-blocking |
| App receives traffic after readiness refusing | Probe/route propagation delay or direct access | Check Service routes vs Pod IP, app admission |
| `LAB_STOP_DONE` missing after Ctrl+C | JVM shutdown hook may finish and exit JVM | Use the lab's direct `context.close()` mode |
| Phase log duration does not match expected time | Scheduling, infrastructure beans, I/O, logging | Measure wall-clock/monotonic time across multiple runs |
| Changing property has no effect | Custom `LifecycleProcessor` or overridden config | Inspect running app's environment/config metadata |

### 14.1. Four Non-Equivalent Pieces of Evidence

- **`ContextClosedEvent`:** closing started; not all tasks have stopped yet.
- **`LAB_STOP_BEGIN`:** bean received the stop request; cleanup has not completed.
- **`LAB_STOP_CALLBACK`:** bean reported completion of its stop procedure per its own implementation contract.
- **`LAB_CLOSE_RETURNED`:** `close` API returned; does not guarantee the JVM exited or all external side effects finished.

A "Shutting down..." log or the container disappearing from the network does not prove zero lost jobs. Add business-state check/ack logs and resource metrics.

## 15. Calculating Shutdown Budgets for Real Scenarios

### 15.1. Short Work, Frequent Restarts

Web request p99 is 3s, workers can drain in 4s, broker closes in 1s, destruction takes 1s. If steps run sequentially, an example budget with margin like 15–20s may be reasonable; still verify web server phase, worker phase, platform budget, and load testing. Do not set `timeout-per-shutdown-phase=1m` just thinking "bigger is safer".

### 15.2. 5-Minute Long Jobs

If a job can run for 5 minutes while Kubernetes grants only 30s to terminate, raising lifecycle timeout to 5m **does not guarantee the 5-minute job completes**. Move such jobs to a durable queue with ack/redelivery, checkpoints, or leases to resume/retry; shutdown then only needs enough time to stop new intake, commit completed work, and hand off/mark unfinished work.

### 15.3. Multiple Replicas Scaling Down Together

If all replicas enter rolling termination simultaneously, the Service can run out of capacity. Readiness/drain policies must align with rollout strategy (`maxUnavailable`, `maxSurge` accordingly), autoscaling, and external system quotas. Raising deadlines is only one piece; it does not replace maintaining enough serving replicas.

### 15.4. Uncooperative I/O

An external HTTP call without timeouts can keep shutdown stuck indefinitely. Minimum design needs connect/read/request timeouts, cancellation, and `finally` cleanup. If a client API does not support interruption, treat its stop as uncertain and rely on platform deadlines plus idempotency/reconciliation to protect business data—never mask errors with a fake success callback.

## 16. Additional Experiments: Varying Configurations and QA Assurance

### 16.1. Trying 2s, 5s, and 10s

Using the same project, `lab.high-stop-ms=6000`, `lab.low-stop-ms=0`. Run separate processes one at a time:

~~~bash
java -jar target/shutdown-phase-lab-0.0.1-SNAPSHOT.jar --spring.lifecycle.timeout-per-shutdown-phase=2s --lab.high-stop-ms=6000
java -jar target/shutdown-phase-lab-0.0.1-SNAPSHOT.jar --spring.lifecycle.timeout-per-shutdown-phase=5s --lab.high-stop-ms=6000
java -jar target/shutdown-phase-lab-0.0.1-SNAPSHOT.jar --spring.lifecycle.timeout-per-shutdown-phase=10s --lab.high-stop-ms=6000
~~~

**Do not run all three concurrently** if they all bind port 8080; run sequentially or add `--server.port=0` for a random port in auto-close mode. With 2s and 5s, phase 200 can exhaust its budget before the high callback arrives; with 10s, the 6s high callback typically arrives before timeout. Rely on actual markers and elapsed measurements rather than assumed values.

### 16.2. Measuring Duration Without Using Fake Sleeps as Real Results

Logging duration from `System.nanoTime()` as in `main` is useful for elapsed time within the **same JVM**; avoid `System.currentTimeMillis()` for durations since wall clocks can jump due to NTP. In production, add Micrometer timers/histograms, trace spans for quiesce/drain/cleanup, and controlled logging of phase/bean IDs.

### 16.3. QA Checklist for a Deployment

| Test | Input/condition | Result to verify |
|---|---|---|
| Normal stop | High delay 1s, phase timeout 2s | High callback before low stop; normal close |
| One phase timeout | High delay 6s, timeout 2s | Low receives stop after high exhausts budget; high callback may arrive late |
| Both phases timeout | High/low 6s, timeout 2s | Total wait can be ~4s; not a hard 2s cap |
| In-flight request | HTTP sleep 7s, graceful 10s | Has chance to complete; measure response and logs |
| Insufficient HTTP grace | HTTP sleep 7s, graceful 2s | May be cut; distinguish network failure/status |
| Real SIGTERM | Console/JAR web mode | Context closes and callbacks run before platform kill? |
| Hard kill | Container SIGKILL | No cleanup guarantee; durable redelivery handles it |
| Repeated startup/stop | Restart multiple times | No leaked threads, FDs, connections, consumers |
| Bad `stop()` | Long blocking synchronous stop | Phase timeout may not preempt the method |
| Missing callback | Intentionally omit callback in a copy | Processor waits until timeout and logs remaining bean |
| Worker dependency | Worker needs broker during stop | Worker stops before broker closes |
| K8s termination | Grace covers preStop + drain + stop | Pod is not killed before designed deadline |

**Note:** Scenarios intentionally breaking callbacks, leaking, or hard-killing must run only in isolated labs with dummy data. Never cause real outages to test shutdown procedures.

## 17. Knowledge Check Questions

**1. Does `timeout-per-shutdown-phase=20s` mean the app definitely stops within 20 seconds?** No. It is the budget **per phase group** of the lifecycle processor; other phases and cleanup may remain.

**2. Why must a `SmartLifecycle` bean call `callback.run()`?** To notify the phase processor that it finished its stop procedure; otherwise the processor may wait until the timeout expires.

**3. Does Spring interrupt an async thread immediately upon timeout?** There is no such guarantee from this property. Waiting for a callback timeout is not executor cancellation.

**4. What if a synchronous stop method runs untimed I/O for 30s while the property is 2s?** It can still block because the processor has not regained control to apply its callback-wait budget.

**5. Two beans in the same phase each take 8 seconds to stop, phase timeout 10 seconds: does it take 16 seconds?** If both implement asynchronous stop and are asked to stop in the same phase, they share one wait budget. However, if implementations block synchronously or dependencies force sequential execution, actual timing can differ; do not mechanically deduce 8 or 16 seconds from numbers alone.

**6. Why stop a worker before its database adapter?** The worker may still need the adapter to flush/commit/ack during shutdown; closing the adapter prematurely causes errors and data loss.

**7. Is Boot 3.5's default for this property 10s or 30s?** **30s**. Standalone Framework `DefaultLifecycleProcessor` Javadoc uses 10s.

**8. Can you see `ContextClosedEvent` and assume it is safe to release resources immediately?** No. That event occurs before lifecycle stop/destruction.

**9. Do graceful web server shutdown and a bean's `@PreDestroy` share the same timeout?** No. They belong to different stages and contracts.

**10. With Kubernetes `preStop` 10s and grace 30s, does Spring still get 30s?** No, `preStop` consumes the grace period; remaining time must subtract used time and overhead.

**11. On SIGKILL, is a `SmartLifecycle` callback guaranteed to run?** No. Proper durability/rollback/redelivery contracts are required.

**12. When a task runs longer than the termination budget, what is the solution?** Durable queues, idempotency, checkpoints/leases, and deadline-bounded drain/cancellation—not simply stretching the property.

## 18. Pre-Production Checklist

- [ ] Confirmed Spring Boot/Spring Framework versions and actual property defaults.
- [ ] Explicitly wrote `spring.lifecycle.timeout-per-shutdown-phase` with `ms/s/m` units.
- [ ] Listed running `SmartLifecycle` beans, `getPhase()`, and dependency graph.
- [ ] Verified descending phase stop order and `depends-on` match business requirements.
- [ ] Every `stop(Runnable)` invokes the callback **after** cleanup completes per policy.
- [ ] No unbounded blocking inside stop or destroy methods; all I/O has its own timeouts.
- [ ] Stop accepting requests/jobs/messages before draining queues and closing downstream dependencies.
- [ ] Distinguished HTTP graceful phase from task-executor shutdown and bean destruction.
- [ ] Tested in-flight HTTP requests both longer and shorter than grace under real load.
- [ ] Logged and instrumented shutdown duration by context/phase/bean with completion markers.
- [ ] Verified long-running tasks have idempotency/durable recovery if the Pod is killed.
- [ ] Sized `terminationGracePeriodSeconds` to cover `preStop`, routing margin, drain, callbacks, and overhead.
- [ ] Verified the JVM process receives real SIGTERM, not swallowed by a shell wrapper.
- [ ] Monitored phase-timeout warnings and incomplete cleanup; do not ignore warning/info logs.
- [ ] Tested callback failures, dependency outages, and interruptions in a safe lab.
- [ ] Did not equate `context.close()` duration with total JVM/container termination time.
- [ ] Tested rolling deployments without removing all capacity at once.

## 19. Official Documentation

1. Spring Boot 3.5 — **Graceful Shutdown**, explaining web server stop phase and `spring.lifecycle.timeout-per-shutdown-phase`: https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html
2. Spring Boot 3.5 — **Common Application Properties**, default `spring.lifecycle.timeout-per-shutdown-phase=30s` and `server.shutdown=graceful`: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
3. Spring Framework 6.2 — **DefaultLifecycleProcessor Javadoc**, phase grouping, timeout, and `setTimeoutForShutdownPhase(...)`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
4. Spring Framework 6.2 — **SmartLifecycle Javadoc**, `stop(Runnable callback)` and phase: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/SmartLifecycle.html
5. Spring Framework 6.2 — **Bean Lifecycle and Destruction**: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html
6. Spring Boot 3.5 — **Task Execution and Scheduling**, executor/scheduler shutdown configs: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
7. Kubernetes — **Pod Lifecycle, Termination Flow, preStop, and terminationGracePeriodSeconds**: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
8. Java SE 17 — **ExecutorService**, `shutdownNow`, `awaitTermination`, and interruption: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html

**Summary:** `spring.lifecycle.timeout-per-shutdown-phase` sets a **callback wait limit per shutdown phase**, preventing the lifecycle processor from waiting forever on an asynchronously stopping `SmartLifecycle` bean. It **does not interrupt I/O automatically, does not guarantee the entire JVM exits in N seconds, and does not replace platform termination budgets**. A safely shutting-down system stops intake, drains/cancels with deadlines, stops workers before dependencies, invokes callbacks at the right moment, measures durations, and maintains idempotency/durability when shutdown does not finish cleanly.