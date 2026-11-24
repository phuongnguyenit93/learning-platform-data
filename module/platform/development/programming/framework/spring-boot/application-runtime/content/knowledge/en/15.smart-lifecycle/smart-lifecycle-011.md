# Designing Idempotent start and stop on Repeated Calls with SmartLifecycle

## 1. The real-world problem

In Spring Boot Application Runtime, a bean implementing **SmartLifecycle** can auto-start when `ApplicationContext` refreshes and be asked to stop when the context closes. However, the lifecycle is not always a single `start() → stop()` sequence:

- Spring calls `start()` itself during refresh; admin code or tests call `start()` again.
- The component is already RUNNING, yet a synchronous operation calls `start()` one more time.
- A `context.stop()` followed by `context.start()` forces the bean to stop and restart.
- Two threads call `start()` or `stop()` close together, or `stop()` arrives before `start()` finishes.
- On shutdown, `DefaultLifecycleProcessor` calls `stop(Runnable)`; afterward a destruction callback such as `DisposableBean.destroy()` or `@PreDestroy` cleans up the same resource.
- A new `stop` call arrives while an asynchronous stop is still running.
- Startup fails after opening part of a resource, before marking RUNNING.

If written naively:

~~~java
public void start() {
    executor = Executors.newSingleThreadExecutor();
}
~~~

then calling `start()` twice can create two pools, lose the reference to the first pool, and leak threads. The snippet above only illustrates a design flaw, not a standalone program.

Similarly:

~~~java
public void stop() {
    executor.shutdown();
    executor = null;
}
~~~

can throw `NullPointerException` if `stop()` is called before `start()` or called a second time. Worse, if `start`/`stop` run on two threads, one thread can close a resource the other thread just replaced.

**Goal of this lesson:** a repeated start or stop call must be safe, never create or close resources twice, maintain truthful state, deliver completion callbacks accurately, and not block shutdown excessively.

The closest concept is **idempotence**. When the component is already RUNNING, calling `start` again opens no additional resources. When already STOPPED, calling `stop` again closes no resources again. However, that **does not forbid** starting a new generation after a successful stop.

## 2. Spring Framework's SmartLifecycle contract

`org.springframework.context.SmartLifecycle` extends `Lifecycle` and `Phased`. Key APIs:

| API | Meaning | Practical requirement |
| --- | --- | --- |
| `start()` | Start the component | Must not open a new resource if already RUNNING |
| `stop()` | Synchronous stop per Lifecycle contract | Must not fail when component is not running or already stopped |
| `stop(Runnable callback)` | Stop and notify completion to lifecycle processor | Callback runs after stopping completes |
| `isRunning()` | Actual operational state | Consistent with resource/state |
| `isAutoStartup()` | Auto-run on context refresh? | SmartLifecycle defaults to true |
| `getPhase()` | Group and start/stop order | Low phase starts first, high phase stops first |

Basically, the interface provides these signatures:

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
}
~~~

This is an **abbreviated illustration**. Do not redefine the interface in your project; use the official interface from Spring Framework. Depending on the version, several methods have default implementations.

### Lifecycle in Spring Boot

~~~text
SpringApplication.run(...)
   |
   +-- Prepare and refresh ApplicationContext
   |     +-- Instantiate SmartLifecycle bean
   |     +-- DefaultLifecycleProcessor.onRefresh()
   |           +-- Auto-start SmartLifecycle (by phase)
   |
   +-- ApplicationStartedEvent
   +-- ApplicationRunner / CommandLineRunner
   +-- ApplicationReadyEvent
   |
   +-- Application running ...
   |
   +-- context.close() / JVM shutdown hook
         +-- ContextClosedEvent
         +-- LifecycleProcessor.onClose()
         |     +-- SmartLifecycle.stop(Runnable)
         |           +-- Callback after stop completes
         +-- Destroy singletons
               +-- @PreDestroy / DisposableBean.destroy()
~~~

Startup events belong to Spring Boot, while `SmartLifecycle` and `DefaultLifecycleProcessor` belong to Spring Framework. On the normal startup path, `SmartLifecycle` auto-start occurs during refresh, **before** `ApplicationStartedEvent` and before runners.

When closing the context, Spring typically invokes `stop(Runnable)`, **not necessarily no-argument `stop()`**. If your cleanup lives in `stop()`, make sure `stop(Runnable)` delegates appropriately. `SmartLifecycle`'s default implementation may delegate and then invoke the callback, but for async resources you must override it properly.

Do not assume a stop callback always precedes destruction: on some abort-refresh paths or destruction outside normal shutdown, a resource may be destroyed without a prior lifecycle stop.

## 3. State machine: why two states are sometimes insufficient

### Lightweight synchronous resources

~~~text
STOPPED --start succeeds--------> RUNNING
RUNNING --stop completes--------> STOPPED

RUNNING --additional start------> RUNNING  (no-op)
STOPPED --additional stop-------> STOPPED  (no-op)
~~~

For in-memory resources or very brief open/close operations, using a single monitor/lock to serialize `start`, `stop`, and `isRunning` is usually enough.

### Resources with I/O or asynchronous stopping

~~~text
             start request
STOPPED -----------------------> STARTING
   ^                               |
   |                               +-- open success --> RUNNING
   |                               +-- open error ----> cleanup / FAILED
   |                                                    |
   |                       stop request                 |
   +----------- STOPPING <------------------------ RUNNING
                   |
                   +-- drain/close completes --> STOPPED
                   +-- error/timeout ---------> FAILED_STOP / policy
~~~

When using networks, executors, consumers, or scheduled tasks, the `STARTING`/`STOPPING` intervals matter. Do not report RUNNING merely when *requesting* to open a connection; report RUNNING only once the resource is ready per contract.

Do not report STOPPED right after calling a command like `ExecutorService.shutdown()`, because running tasks may not have finished yet.

### Transition table on repeated calls

| Current state | `start()` | `stop()`/`stop(callback)` |
| --- | --- | --- |
| STOPPED | Open resource, transition STARTING/RUNNING | Do not close again; complete callback |
| STARTING | Do not open duplicate; wait, coalesce, or report clear error | Record stop request to run after start finishes |
| RUNNING | No-op | Begin stopping, transition STOPPING |
| STOPPING | Do not open new generation overlapping old resource | Join in-progress stop, register additional callback |
| FAILED | Cleanup/rollback then conditional retry | Clean up leftover resources; do not pretend already stopped |

No single policy fits every resource. Implementers must decide whether `start` during `STOPPING` will **wait**, **queue**, or **be rejected**. What is forbidden is lacking a policy and opening a new resource while the old resource is still closing.

## 4. Invariants: what must always hold true?

The following rules should become test criteria:

1. **At most one active real resource per running generation.** Two concurrent start commands cannot open two duplicate connections, consumers, or workers.
2. **A generation is closed at most once.** Stopping while STOPPED never invokes close a second time causing an error.
3. **Restartable if the resource supports it.** RUNNING → STOPPED → RUNNING creates a valid new generation.
4. **`isRunning()` is consistent.** Never true before the resource is ready; never false while the lifecycle still considers the resource active, unless an explicit state exists.
5. **No dangerous overlap.** Starting a new generation never reopens a port/lease still held by the previous generation.
6. **Callback truly completes.** `stop(Runnable)` never signals done before stopping finishes.
7. **Additional stop calls never drop callbacks.** Every valid `stop(callback)` call receives a completion notification.
8. **Cleanup tolerates repeated calls from destroy.** `@PreDestroy` / `DisposableBean.destroy()` can share the same cleanup path without double-closing.
9. **Timeouts and failure policies exist.** Never hold a monitor or wait on I/O indefinitely.
10. **Observable.** Logs/metrics distinguish how many times methods were called vs. how many times resources actually opened/closed.

Do not only test `assertDoesNotThrow`; verify open counts, close counts, generations, final state, and callback timing.

## 5. Why are volatile or AtomicBoolean alone insufficient?

This example has a race:

~~~java
private volatile boolean running;

public void start() {
    if (!running) {
        openConnection();
        running = true;
    }
}
~~~

This is pseudocode; `openConnection()` is undefined. Two threads can both read `false` and both allocate resources. `volatile` gives visibility guarantees; it **does not combine check/allocate/publish into one atomic operation**.

Trying CAS:

~~~java
if (running.compareAndSet(false, true)) {
    openConnection();
}
~~~

is also insufficient without a state machine. The flag is set `true` **before** opening the connection succeeds. If connecting fails, another `stop` may mistakenly think it is RUNNING; a subsequent `start` may also be skipped.

### Using a shared lock when start/stop are short

~~~java
private final Object monitor = new Object();
private boolean running;

public void start() {
    synchronized (monitor) {
        if (running) return;
        openResource();  // Publish RUNNING only after success.
        running = true;
    }
}

public void stop() {
    synchronized (monitor) {
        if (!running) return;
        closeResource();
        running = false;
    }
}

public boolean isRunning() {
    synchronized (monitor) {
        return running;
    }
}
~~~

This is only a **non-standalone illustrative snippet**: `openResource()` and `closeResource()` are hypothetical operations. Sharing the same monitor serializes check/state/resource. If I/O takes long, holding the lock across all of `openResource()` or `closeResource()` can block other threads; production code should use `STARTING`/`STOPPING` and finish I/O outside the lock via a state machine.

### Ordering between concurrent start and stop

Suppose two threads begin nearly simultaneously:

~~~text
A: stop()
B: start()
~~~

If operations are serialized, the outcome can be RUNNING or STOPPED depending on actual lock entry order. **Thread-safe does not mean the final state is always identical for two commands with opposite goals.**

To guarantee "shutdown wins over every start", you need a terminal `closing` flag or dedicated coordination policy, not merely `synchronized`.

## 6. Complete runnable Java 17+ Spring Boot example

The example below runs with **Spring Boot 3.5.16** and **Java 17+**. The resource is an in-memory object so every output line is deterministic. It does not pretend to simulate network latency: its goal is demonstrating repeated calls, stop callbacks, and destruction callbacks.

### 6.1. Project structure

~~~text
repeatable-lifecycle-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/lifecycle/
                └── RepeatableLifecycleApplication.java
~~~

**File pom.xml:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>repeatable-lifecycle-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot 3.5.16 is published and available on Maven Central. The example omits `spring-boot-starter-web` to avoid starting a server; the focus is a pure lifecycle bean.

### 6.2. Complete Java file

**File src/main/java/com/example/lifecycle/RepeatableLifecycleApplication.java:**

~~~java
package com.example.lifecycle;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RepeatableLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                RepeatableLifecycleApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        ManagedWorker worker;

        try (ConfigurableApplicationContext context = app.run(args)) {
            worker = context.getBean(ManagedWorker.class);
            System.out.println("MAIN running=" + worker.isRunning());
        }

        System.out.println(
                "AFTER_CLOSE running=" + worker.isRunning());
        System.out.println(
                "AFTER_CLOSE counts="
                        + worker.startCount() + "/"
                        + worker.stopCount());
    }

    @Bean
    ManagedWorker managedWorker() {
        return new ManagedWorker();
    }

    @Bean
    ApplicationRunner demonstrate(ManagedWorker worker) {
        return args -> {
            System.out.println(
                    "RUNNER running=" + worker.isRunning());

            worker.start();
            worker.start();

            worker.stop(() -> System.out.println("CALLBACK first"));
            worker.stop(() -> System.out.println("CALLBACK second"));

            // Restarting after STOPPED is a new generation.
            worker.start();
            worker.start();

            System.out.println(
                    "RUNNER counts="
                            + worker.startCount() + "/"
                            + worker.stopCount());
        };
    }

    public static final class ManagedWorker
            implements SmartLifecycle, DisposableBean {

        private final Object monitor = new Object();
        private Object resource;
        private int starts;
        private int stops;

        @Override
        public void start() {
            synchronized (monitor) {
                if (resource != null) {
                    System.out.println("START already-running");
                    return;
                }

                // In-memory resource is created immediately.
                resource = new Object();
                starts++;
                System.out.println("START count=" + starts);
            }
        }

        @Override
        public void stop() {
            synchronized (monitor) {
                if (resource == null) {
                    System.out.println("STOP already-stopped");
                    return;
                }

                // No async I/O in the demo.
                resource = null;
                stops++;
                System.out.println("STOP count=" + stops);
            }
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
            synchronized (monitor) {
                return resource != null;
            }
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public int getPhase() {
            return 100;
        }

        public int startCount() {
            synchronized (monitor) {
                return starts;
            }
        }

        public int stopCount() {
            synchronized (monitor) {
                return stops;
            }
        }

        @Override
        public void destroy() {
            System.out.println("DESTROY fallback");
            stop();
        }
    }
}
~~~

This is **a complete program** inside a Maven project. Not pseudocode. `ManagedWorker` implements both `SmartLifecycle` and `DisposableBean` to observe how stop and destroy can both invoke cleanup.

**Code analysis:**

- `ManagedWorker` is managed by Spring as a singleton bean. On context refresh, `DefaultLifecycleProcessor` invokes `start()` because `isAutoStartup()` returns true.
- All operations on `resource` and counters are guarded by the same `monitor`. Two threads cannot pass the guard together and allocate two resources while a generation is active.
- The resource is simulated with `new Object()`, finishing creation before recording RUNNING state. With a real network client, allocate and verify readiness before publishing RUNNING.
- `stop()` when STOPPED simply prints a no-op. `stop(Runnable)` always invokes the callback after synchronous stop returns, even on calls with nothing to close.
- Because `stop()` in the example performs no I/O and has no cleanup failures, `finally` in `stop(Runnable)` is safe for the demo. In real apps, never invoke a "success" callback when cleanup has not actually completed.
- `destroy()` is a safety net: normal shutdown already stopped it, yet the destruction callback can invoke the same cleanup again without double-closing.
- `getPhase()` is 100. That phase does not make the runner run earlier and does not equate to `ApplicationRunner` priority.

### 6.3. Running and verifying stdout

From the project directory:

~~~bash
mvn package
java -jar target/repeatable-lifecycle-demo-0.0.1-SNAPSHOT.jar
~~~

Or:

~~~bash
mvn spring-boot:run
~~~

Lines printed by **the program itself** in this order; Maven and Spring Boot banners/logs may interleave:

~~~text
START count=1
RUNNER running=true
START already-running
START already-running
STOP count=1
CALLBACK first
STOP already-stopped
CALLBACK second
START count=2
START already-running
RUNNER counts=2/1
MAIN running=true
STOP count=2
DESTROY fallback
STOP already-stopped
AFTER_CLOSE running=false
AFTER_CLOSE counts=2/2
~~~

Explanation:

1. `START count=1`: auto-start during refresh before the runner runs.
2. `RUNNER running=true`: runner observes the bean already started.
3. Two more start calls are both skipped.
4. The first stop genuinely closes the first generation, then fires the first callback.
5. The second stop closes no extra resource yet **still fires the second callback**.
6. Starting after stop creates a second generation, so `START count=2` is valid.
7. The next start call is a no-op again.
8. `MAIN running=true` appears after `SpringApplication.run(...)` finishes.
9. When `try`-with-resources closes the context, the lifecycle processor runs stop once more.
10. Spring invokes `DisposableBean.destroy()` afterward. The extra stop is just a no-op.
11. After close, the worker is not running; both real creations have been stopped.

Note: this is output **for a synchronous demo with a simulated resource**, not a guarantee of log ordering in systems with multiple `SmartLifecycle` beans, async listeners, or I/O.

### 6.4. Boundaries of the synchronous example

The resource is merely an `Object`, so there are no threads, sockets, files, or remote connections to wait on. Production versions differ:

- `start()` must roll back when opening resources only partially succeeds.
- `stop()` must stop intake and wait for active tasks per policy.
- Never hold the monitor across unbounded I/O, as it blocks other calls.
- If cleanup can fail, record the error state and notify the system rather than silently marking STOPPED while resources persist.
- If closing asynchronously, the callback runs **after completion**, not after issuing the close request.

## 7. Designing stop(Runnable) without losing callbacks

### 7.1. What is SmartLifecycle's callback for?

Per Spring Framework, the callback is used by `DefaultLifecycleProcessor` to know when a component finished stopping. The lifecycle processor can wait for callbacks of same-phase beans before advancing to the next phase.

Therefore this code is wrong for a resource with running tasks:

~~~java
@Override
public void stop(Runnable callback) {
    executor.shutdown(); // Only rejects new tasks!
    callback.run();       // May report stopped too early.
}
~~~

This is a **non-standalone illustrative snippet**. `ExecutorService.shutdown()` does not wait for in-flight tasks to finish. For graceful stop, wait with a timeout or emit the callback from async completion.

### 7.2. Callback when already STOPPED

In a repeatable-call-safe implementation, a `stop(callback)` call when the resource is already STOPPED must still fulfill the caller's contract:

~~~text
Current state: STOPPED
stop(callbackA)
  -> Do not close resource again
  -> callbackA.run() (stop already completed)
~~~

Never "return early because already stopped" **and drop the callback**. `DefaultLifecycleProcessor` normally checks `isRunning()` before calling stop, yet other callers may invoke it directly. The bean should still uphold the API contract.

### 7.3. Callback when already STOPPING

Scenario requiring a state machine:

~~~text
Caller A: stop(callbackA) when RUNNING
  lock -> state=STOPPING, pendingCallbacks=[A]
  unlock
  start async shutdown once

Caller B: stop(callbackB) when STOPPING
  lock -> add B to pendingCallbacks
  unlock
  DO NOT start a second shutdown

Real shutdown completes:
  lock -> state=STOPPED, drain callback list and clear queue
  unlock
  callbackA.run()
  callbackB.run()
~~~

This is **pseudocode**, not standalone runnable Java. Updating state and adding callbacks must be atomic under the same lock or equivalent synchronization. Callbacks should run **outside the lock**, because framework or integration callbacks may call into other beans and deadlock if locks are held.

An anti-pattern:

~~~java
if (stopping.compareAndSet(false, true)) {
    shutdownAsync(callback);
}
// If already STOPPING, new callback is dropped.
~~~

This is an illustrative snippet. CAS only prevents cleanup from running twice; it does not retain late-arriving callbacks.

### 7.4. Error handling and exactly-once notification

With async shutdown, consider:

- One callback may throw an exception: do not let that skip the next callback; isolate and log errors.
- The executor used to run cleanup may already be closed: do not submit every callback to an executor that no longer accepts tasks.
- A new `stop` call may arrive right as completion transitions STOPPING → STOPPED: handle both cases without losing the callback.
- Do not invoke the callback before closing finishes, nor wait forever if the resource is stuck.
- On timeout or unrecoverable cleanup failure, explicitly define a `FAILED_STOP` state and escalation mechanism rather than pretending the callback substitutes for cleanup.

**Exactly-once callback** is a process-level goal. If an external system needs exactly-once side effects across crashes/restarts, you also need idempotency keys, transactions, leases, or external system protocols; one boolean cannot protect an entire distributed lifecycle.

## 8. Safe start on repeated calls and partial failures

A reliable `start` works in sequence:

~~~text
Check state
   |
   +-- RUNNING: no-op
   +-- STARTING: coalesce requests / wait / reject
   +-- STOPPING: wait for stop to finish / queue restart / reject
   +-- STOPPED: begin initialization
          |
          +-- open resource
          +-- configure
          +-- verify ready
          +-- success --> RUNNING
          +-- error --> roll back opened resource
                        --> STOPPED or FAILED
~~~

Do not write:

~~~java
running = true;
resource = connectToBroker();
subscribe(resource);
~~~

This is **pseudocode**. If connecting or subscribing fails, `running=true` retains a false state and the next start may be skipped. Publish RUNNING only when all mandatory steps succeed.

### Rolling back when start fails

If a socket was opened yet the next step fails:

1. Hold the initializing resource in a variable with clear ownership.
2. Clean up resources that were already created successfully.
3. Never leave the state field reporting RUNNING.
4. Preserve the original exception; if cleanup also fails, attach suppressed exceptions appropriately.
5. Retry only if the resource and policy permit (timeout, backoff, retry cap).
6. Never accidentally create two subscriptions during retries.

### Preventing new starts while the context is closing

Even when `synchronized` serializes calls, an admin thread may invoke `start()` **after** a `stop()` triggered by context close returns, reopening the resource while the context is destroying. If shutdown must strictly win, use a terminal `closing` flag or `TERMINATED` state set on the final close command. Once permanently closed, reject `start()` instead of allowing automatic restart.

Conversely, in systems needing `context.stop() → context.start()`, do not use a terminal flag for every stop. Distinguish **pausing** from **permanent closing**.

## 9. Phase, dependencies, and shutdown order

Spring Framework uses `getPhase()`:

~~~text
START: low phase -> high phase
STOP : high phase -> low phase
~~~

Illustrative table:

| Bean | Phase | Start | Stop |
| --- | ---: | --- | --- |
| Foundational connection | -100 | Early | Late |
| Regular component | 0 | Middle | Middle |
| Consumer depending on connection | 100 | Late | Early |

Thus the consumer can stop receiving messages before the foundational connection is closed. When Spring knows a `depends-on` relationship, the dependency also affects ordering accordingly.

`SmartLifecycle` defaults to a high phase (`Integer.MAX_VALUE` in Spring Framework 6.2); plain `Lifecycle` not implementing `SmartLifecycle` is usually treated as phase 0. Choose phases according to real dependencies, not the order of `@Bean` methods.

### isAutoStartup and lazy

`isAutoStartup()` defaults to `true`. A `SmartLifecycle` bean can be created so the lifecycle processor performs auto-start even when you think `@Lazy` will keep it unused. To skip auto-starting on refresh, override `isAutoStartup()` to return `false`, understanding that `context.start()` afterward can still start the bean.

### SmartLifecycle differs from ApplicationRunner

`SmartLifecycle.start()` usually runs during refresh, before `ApplicationStartedEvent`, before `ApplicationRunner`, and before `ApplicationReadyEvent`. Never write `start()` to wait for a runner to finish in a way that creates a startup dependency cycle. If work needs to happen after refresh or after runners, use the right-timed extension point.

## 10. Stop timeout and graceful shutdown

`DefaultLifecycleProcessor` has a per-phase callback wait timeout; in Spring Framework 6.2, the Javadoc describes a 10-second default per phase unless configured otherwise. Spring Boot allows configuring:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Do not rely on an immutable default across all versions. Spring's wait configuration only limits how long the **processor waits on a phase**; it does not force sockets, tasks, or remote APIs to finish closing.

If the callback is omitted, Spring may wait until timeout expires. If invoked too early, Spring believes the phase has stopped while resources still run. Both can cause shutdown failures.

### Procedure for stopping a message consumer

1. Transition state to STOPPING and reject new task creation.
2. Stop polling/receiving new messages.
3. Wait for in-flight tasks with a timeout.
4. Ack/commit per broker contract and business conditions.
5. Close connections and release resources.
6. Transition state to STOPPED.
7. Invoke all waiting callbacks, outside the lock.

If a timeout occurs, decide whether to force-stop, report failure, or let another instance retry tasks; never claim completion solely because time ran out.

### Forceful JVM termination

`SIGKILL`, crashes, power loss, and certain halt modes do not guarantee Spring callbacks run. Out-of-process resources need leases/heartbeats/timeouts; cluster-wide "no duplicate processing" requirements need distributed coordination, not just local `SmartLifecycle`.

## 11. Backup cleanup via destroy callbacks

Spring Framework docs note that stop notifications **are not guaranteed** to arrive before destruction in every case (e.g., refresh failures). During normal shutdown, lifecycle beans are stopped before Spring calls singleton destruction callbacks.

Appropriate resource cleanup paths:

- `@PreDestroy` on a Spring-managed bean.
- `DisposableBean.destroy()`.
- `@Bean(destroyMethod = "...")`.
- `AutoCloseable.close()` when owned and managed per contract.

If a `SmartLifecycle` **owns** a resource, its destroy callback can invoke the same idempotent cleanup method to cover startup failure paths. That is why the section 6 demo implements `DisposableBean`.

If a `SmartLifecycle` only **borrows** a resource owned by another bean, do not close it yourself unless ownership is agreed upon. For example, a consumer using a shared pool may only need to stop the consumer, letting the pool's owner release it during destruction.

**Never replace** `stop(Runnable)` with a destroy callback: the lifecycle processor needs the callback to coordinate phases and await completion. Destroy handles a different cleanup line.

## 12. Testing safety on repeated calls

### 12.1. Sequential testing

~~~text
Initially STOPPED:
start()             -> RUNNING, openCount=1
start()             -> RUNNING, openCount=1
stop(callbackA)     -> STOPPED, closeCount=1, callbackA=1
stop(callbackB)     -> STOPPED, closeCount=1, callbackB=1
start()             -> RUNNING, openCount=2
stop(callbackC)     -> STOPPED, closeCount=2, callbackC=1
destroy()           -> STOPPED, closeCount=2
~~~

These numbers are **expectations of an implementation designed like the demo**, not metrics Spring generates automatically.

### 12.2. Two threads starting concurrently

Use a `CountDownLatch` so two threads call `start()` at the exact same instant. After both finish, starting from STOPPED:

~~~text
isRunning() == true
openCount == 1
~~~

Run many iterations to increase race detection chances. Do not rely on a single run's result.

### 12.3. Two threads stopping concurrently

Two calls:

~~~text
A: stop(callbackA)
B: stop(callbackB)
~~~

Expectations:
- Only one real resource cleanup pass.
- `callbackA` and `callbackB` each invoked exactly once.
- Neither callback runs before the resource finishes closing.
- If stop is async, both share waiting on one completion without double-closing.

### 12.4. Start overlapping stop

~~~text
A: stop() is releasing resource
B: start() wants to open a new resource
~~~

With synchronous locks, operations do not overlap, yet the final result can be RUNNING or STOPPED depending on lock order. If the requirement is "once shutdown begins, all starts are forbidden", maintain a `CLOSING`/`TERMINATED` state.

### 12.5. Failure testing

Simulate these scenarios:
- `start` opens connection successfully, subscribe fails.
- `stop` throws an exception during close.
- Callback registered while STOPPING.
- Cleanup executor already shut down.
- User callback throws an exception.
- Destroy runs even though start never succeeded.
- Spring stop phase times out when task refuses to exit.

On every check: verify state, open resource count, received callback count, absence of deadlocks, and clear subsequent behavior.

## 13. Common mistakes

| Mistake | Consequence | Fix with |
| --- | --- | --- |
| Start always creates executor/connection | Resource leak on repeated calls | Guard state, one resource per generation |
| Stop nulls/closes resource unchecked | NPE when not started or already stopped | Safe no-op |
| Using only volatile boolean | Two threads both allocate | Lock or complete state machine |
| Setting running before connect succeeds | State stuck on failure | Publish RUNNING after ready, roll back |
| Marking STOPPED right after `shutdown()` | Tasks still running | Await completion/timeout |
| Dropping callback if already STOPPED | Caller waits needlessly | Invoke callback immediately since already done |
| Dropping new callback if STOPPING | Lost completion signal | Queue all callbacks |
| Invoking callbacks inside lock | Potential deadlock | Transition state inside lock, callback outside lock |
| Unbounded I/O inside `synchronized` | Blocks other callers | Timeouts and async state machine |
| Starting while old resource is still STOPPING | Port/lease conflict | Block/queue/await restart |
| Destroy closes already-closed resource | Double-close | Use idempotent cleanup |
| No rollback on start failure | Partial resource leak | Cleanup on failure path |
| No distinction between stop and permanent close | Reopened during shutdown | Terminal closing state |
| Phase ordered opposite to dependencies | Consumer uses closed client | Proper phases and `depends-on` |
| Using `@Lazy` to "disable" auto-start | SmartLifecycle can still start | Override `isAutoStartup` |
| Testing only happy path | Races and lost callbacks | Stress-test concurrency/failures |
| Treating callback as distributed idempotency | Duplicates across crash/retry | Leases, idempotency keys, transactions |

## 14. Review questions

**Question 1:** Why must `start()` be idempotent?

**Answer:** Because Spring and application code may call it again, or two threads may contend. Without guards, duplicate resources are created, leaked, and state breaks.

**Question 2:** Should calling `stop()` when STOPPED throw an exception?

**Answer:** No. The Lifecycle contract expects safe stopping when a component is not running; it should no-op.

**Question 3:** Should `stop(Runnable)` when STOPPED invoke the callback?

**Answer:** Yes. No resource needs closing again, yet the caller must be notified of completion.

**Question 4:** Does `ExecutorService.shutdown()` mean all tasks have finished?

**Answer:** No. It stops accepting new tasks; you must await termination or track task completion.

**Question 5:** Why is `volatile` insufficient to guard `start`?

**Answer:** Check and allocation are not atomic. Two threads can read `false` and both create resources.

**Question 6:** Does a higher phase start before or after a lower phase?

**Answer:** Starts later and stops earlier, absent additional dependency constraints.

**Question 7:** Does `isAutoStartup=false` forbid `context.start()` from starting the bean?

**Answer:** No. It only controls auto-start on refresh; `context.start()` is an explicit lifecycle request.

**Question 8:** Does starting again after a completed stop violate idempotence?

**Answer:** No. If the component supports restarts, that is a valid new generation.

**Question 9:** Why must stop callbacks not be invoked under a monitor?

**Answer:** The callback may call back into APIs or touch other locks, causing deadlocks or unwanted blocking.

**Question 10:** Does Spring guarantee lifecycle stop always runs before destroy?

**Answer:** Not on every path; provide fallback cleanup for resources owned by the bean.

**Question 11:** Does the shutdown phase timeout automatically force resources to finish closing?

**Answer:** No. It bounds how long Spring waits for callbacks; resources need their own timeout/cancellation logic.

**Question 12:** How do you ensure start never overlaps stop?

**Answer:** For short operations, serialize with a lock; for async operations, use `STARTING`/`STOPPING` states and an explicit queue/wait/reject policy.

## 15. Practice exercises

**Exercise A:** Run the section 6 demo. Count `start`/`stop` calls vs. how many times the resource was actually opened/closed. Explain why `startCount=2` and `stopCount=2` despite more method calls.

**Exercise B:** Add `worker.stop(() -> System.out.println("CALLBACK third"))` right after the second stop. The third callback must appear without increasing `stopCount`.

**Exercise C:** Change `isAutoStartup()` to false. Observe the runner initially sees STOPPED; then start explicitly and verify behavior.

**Exercise D:** Use `CountDownLatch` and two threads calling `start` concurrently from STOPPED. Expect `openCount=1`. Repeat with two stop callbacks to verify accurate completion.

**Exercise E:** Create a `ResourceFactory` that occasionally throws an exception after the first allocation step. Write rollback avoiding leaks and never reporting RUNNING when not ready.

**Exercise F:** Replace `Object` with a worker thread and implement `STOPPING` + a callback queue. Ensure tasks really stop before callbacks; use timeouts and test two concurrent stop calls.

**Exercise G:** Add a foundational bean at phase -100 and a consumer at phase +100. Observe start/stop order. Check what happens if the consumer stops before in-flight work finishes.

## 16. Official documentation and takeaways

Sources to cross-check against your actual dependency versions:

- [Spring Framework 6.2 — SmartLifecycle Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/SmartLifecycle.html): callbacks, phases, auto-start.
- [Spring Framework 6.2 — Lifecycle Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/Lifecycle.html): `start`/`stop`/`isRunning` contract.
- [Spring Framework 6.2 — DefaultLifecycleProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): ordering and shutdown timeouts.
- [Spring Framework — Bean Lifecycle](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): stop, phases, and destruction callbacks.
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): timeout configuration during shutdown.

**Remember:**

1. RUNNING + `start()` → no-op; STOPPED + `stop()` → no-op.
2. STOPPED + `start()` → new generation if the resource supports restarts.
3. Guards must protect both state and resource; simple `volatile`/CAS alone is insufficient.
4. `isRunning()` must be truthful about the resource and transitional phases.
5. `stop(Runnable)` must invoke the callback after really stopping, even on repeated calls.
6. Async `STOPPING` must retain all callbacks with only one cleanup execution.
7. `SmartLifecycle` starts in ascending phase order and stops in descending phase order.
8. Cleanup from destroy must be idempotent and never replace stop callbacks.
9. Never hold locks across unbounded I/O or report STOPPED while tasks still run.
10. Test concurrency, failures, restarts, and forced shutdowns, not only the happy path.
