# Boundaries Between Lifecycle Management and Deep Concurrency Design in Spring Boot

## 1. The problem: "Spring manages threads" does not mean "the program is concurrency-correct"

A Spring Boot application may run concurrent tasks via `@Async`, `@Scheduled`, `TaskExecutor`, `TaskScheduler`, `CompletableFuture`, `ExecutorService`, or background message consumers. Spring helps you **register components, provision executors, trigger certain callbacks, and close resources alongside `ApplicationContext`**. Yet Spring does not automatically solve every issue arising when two or more tasks touch the same data.

Simple example:

```java
private int total;

public void addOne() {
    total++;
}
```

If two tasks concurrently call `addOne()`, the expression `total++` is not an atomic operation: it consists of read, compute, and write. Placing the class in `@Service`, adding `@Async`, or letting Spring close the executor **does not** automatically make this increment race-free. The program can suffer **lost updates** despite zero thread leaks and a completely clean shutdown.

Conversely, you might use `AtomicInteger` to increment safely inside one JVM yet forget to stop a worker on shutdown. In that case, **runtime concurrency logic** may be right while **lifecycle management** is broken.

Two sets of responsibilities must be verified independently:

- **Lifecycle management:** when resources are created, started, begin intake, stop intake, await completion, close, and release.
- **Concurrency design:** when tasks interleave, which data invariants hold; who owns state; which ordering must be preserved; how overload is handled; and what cancellation, failures, and retries can produce.

**Core principle:** Spring manages *the framework of resource existence and usage*. The application is responsible for *the correctness of work running on those resources*. The two halves must coordinate, yet neither can substitute for the other.

## 2. Responsibility boundary table

| Question | Lifecycle / Spring Boot support | Deep concurrency still needing design |
|---|---|---|
| When is the executor created? | `@Bean`, auto-configuration, bean init/destroy | Choosing the right pool/worker model and resources for the workload |
| Where are tasks submitted? | `TaskExecutor`, `@Async`, `@Scheduled`, qualifiers | Distribution, load shedding, deadlines, and work ownership |
| When do beans start operating? | `SmartLifecycle.start()`, `ApplicationRunner`, events | Initializing shared state and safe publication across threads |
| Two tasks mutate the same data? | Framework does not add business locks automatically | `synchronized`, locks, atomics, immutable data, actors, or suitable transactions |
| Tasks must run in order A then B? | Can choose an executor/scheduler and start-stop phases | Happens-before constraints, queues, completion dependencies, handling reordering |
| What if the queue is full? | Configuring capacity and rejection policy | Backpressure, accepting rejection, retries, and controlling lost work |
| Who learns if a task fails? | `Future`/`CompletableFuture`, `@Async` handlers | Error policies, idempotency, retries, dead-lettering, and observability |
| What when context closes? | `SmartLifecycle.stop(Runnable)`, destroy callbacks, shutdown timeouts | Stopping intake, draining/flushing, cancellation, and dependency closing order |
| Received message must process once? | No guarantee from bean lifecycle alone | Acks, checkpoints, deduplication, transactions, and broker semantics |
| Multiple replicas avoid colliding? | Each instance has its own context and executor | Distributed locks, partition assignment, idempotency, fencing, and leases |
| Security/request context across threads? | Can use `TaskDecorator` or configured propagation mechanisms | Deciding which context to pass, clearing timely, avoiding data leaks |

This table does not say Spring *lacks concurrency tools*. On the contrary, Spring offers many useful abstractions. The boundary is that **the framework provides execution machinery**, while **business logic decides what that machinery must preserve**.

## 3. Distinguishing processing layers in an application

Think of four layers from outside in:

```text
Layer A — Platform procedures
  JVM/process, container, orchestration, readiness, SIGTERM
                         |
Layer B — Spring ApplicationContext lifecycle
  bean creation, refresh, SmartLifecycle, @PreDestroy
                         |
Layer C — Task execution infrastructure
  TaskExecutor, ThreadPoolTaskExecutor, TaskScheduler, queue
                         |
Layer D — Business algorithms and data
  ordering, mutex/atomic, dedupe, retry, transaction, state machine
```

**Layer A** can send `SIGTERM` and wait for JVM exit; it does not know whether a business transaction committed. **Layer B** signals closing the context; it does not know which tasks must be ordered. **Layer C** provides worker threads and queues; it does not know whether receiving the same event twice is valid. **Layer D** is where invariants and failure consequences are defined.

A clean shutdown flow can propagate signals from A down through B and C, after which C gives D time to finish work. Yet if D lacks cancellation, idempotency, or deadlines, lifecycle can only wait for a fixed timeout — **it cannot make business logic safe on its own**.

## 4. Spring Boot milestones affecting tasks

In Spring Boot 3.3, a `SpringApplication.run(args)` call passes through major steps:

```text
Prepare Environment
       |
Create ApplicationContext and bean definitions
       |
refresh()
  +--> create required beans
  +--> SmartLifecycle auto-start by phase
       |
ApplicationStartedEvent
       |
ApplicationRunner / CommandLineRunner
       |
ApplicationReadyEvent
       |
ReadinessState.ACCEPTING_TRAFFIC (default)
       |
Application running
       |
ApplicationContext.close() / shutdown hook
  +--> stop SmartLifecycle by phase
  +--> destroy beans, close resources
       |
JVM exits (when no non-daemon threads remain)
```

**Do not conflate milestones:**

- `@PostConstruct` runs when **one bean** initializes, not proving the whole app is Ready.
- `SmartLifecycle.start()` runs under lifecycle coordination during context refresh; suited for long-lived components.
- `ApplicationStartedEvent` fires after refresh yet before runners.
- `ApplicationRunner` and `CommandLineRunner` handle startup logic using initialized beans and must finish before Ready.
- `ApplicationReadyEvent` arrives after runners, **not** proving all background tasks have finished.
- `@PreDestroy` and `DisposableBean.destroy()` relate to bean destruction; they do not automatically provide an ordered drain protocol like `SmartLifecycle.stop(Runnable)`.

A task submitted in a runner without awaiting its result can still **keep running after `ApplicationReadyEvent`**. A runner finishing does not mean the task it just submitted finished. If the work is a prerequisite for receiving traffic, the runner must await/verify completion within a sensible deadline or use an appropriate readiness mechanism.

## 5. What do @Async, TaskExecutor, and @Scheduled actually do?

### 5.1. @Async routes a call to an executor

Spring Framework provides `@Async`, though async processing must be enabled, typically via `@EnableAsync`. When another bean calls an eligible `@Async` method **through a Spring proxy**, Spring delegates execution to an executor:

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
```

```java
@Service
public class ReportService {

    @Async
    public CompletableFuture<String> build(String input) {
        return CompletableFuture.completedFuture(
                "report-for-" + input);
    }
}
```

The snippets above are **integration code**, requiring Spring/Java imports, component scanning, and appropriate executor configuration. An `@Async` method returning `CompletableFuture` lets the caller observe results/errors. Even if `build` is very fast, switching threads carries overhead and brings no automatic benefit to CPU-bound code.

Things `@Async` does **not** automatically do:

1. Does not make a shared `int` field thread-safe.
2. Does not solve self-invocation: calling `this.build(...)` on the same target bypasses proxy-based advice.
3. Does not guarantee the task completes before `ApplicationReadyEvent`.
4. Does not automatically guarantee propagation of all `ThreadLocal`, transaction, or security contexts.
5. Does not add deadlines, retries, idempotency, or message ordering unless the application designs them.
6. Does not guarantee the caller sees exceptions if an `@Async` method returns `void`: errors must be handled via `AsyncUncaughtExceptionHandler`/appropriate logging; with futures, callers must check completion.

### 5.2. TaskExecutor is a thread-provisioning mechanism, not an algorithm

Spring `TaskExecutor` abstracts `execute(Runnable)`; `ThreadPoolTaskExecutor` provides a configurable pool. Spring Boot 3.3 can auto-configure an `AsyncTaskExecutor` when no matching application-declared executor exists:

- Java 17 in default platform-thread mode: typically uses `ThreadPoolTaskExecutor`.
- Java 21+ with `spring.threads.virtual.enabled=true`: can use `SimpleAsyncTaskExecutor` backed by virtual threads.
- Bean names, executor types, and auto-wiring for `@Async`/Spring MVC/GraphQL follow specific rules when the application declares one or more `Executor` beans; **never guess from a generic "executor" name**.

Example Spring Boot 3.3 pool configuration:

```properties
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=32
spring.task.execution.thread-name-prefix=jobs-
```

These properties apply to the **matching auto-configured executor**, not every `ExecutorService` created with `Executors.newFixedThreadPool`. Bounded queues make overload thresholds observable. With `ThreadPoolExecutor`, the pool prioritizes queuing once core size is reached before growing to max size, so **merely setting a large max-size does not guarantee the pool grows if the queue is unbounded**.

### 5.3. @Scheduled decides when to trigger, not concurrency safety

`@Scheduled` is commonly paired with `@EnableScheduling`:

```java
@Component
public class PollingJob {

    @Scheduled(fixedDelay = 5000)
    public void poll() {
        // Start a scheduled check.
    }
}
```

This is an integration snippet needing imports and scheduling enabled. `fixedDelay` sets the wait interval **after one execution finishes** (for standard synchronous scheduling); `fixedRate` expresses cadence by wall-clock timestamps. If the method itself submits async work and returns immediately, the duration of the **actual work** may not match when the scheduled method returns.

`@Scheduled` does not automatically provide a **distributed singleton**: two replicas running the same app can both execute the scheduled job. If the job must run only once system-wide, add distributed coordination or use a job runner with appropriate leases/leader election.

## 6. When should you use SmartLifecycle?

`SmartLifecycle` fits **long-lived components**, such as a worker continuously consuming messages or a consumer connected to a broker. It provides:

```java
void start();
void stop();
void stop(Runnable callback);
boolean isRunning();
int getPhase();
boolean isAutoStartup();
```

These signatures are a conceptual list from `SmartLifecycle`, `Lifecycle`, and `Phased`. Do not copy them into a new interface; implement Spring's existing interface.

Meaning:

- `start()` initializes resources and begins intake; do not run an infinite loop **directly on the thread calling start**.
- `isRunning()` reflects state for Spring coordination, not a lock against races.
- `getPhase()` controls ordering: **lower start phases run first; higher stop phases stop first**. `SmartLifecycle` defaults to phase `Integer.MAX_VALUE`, which can be kept unless specific ordering is needed.
- `stop(Runnable)` allows asynchronous stopping, yet **the callback must run only after actually stopping**; calling it early lets Spring close lower-phase beans while workers still use them.

A state machine should distinguish at minimum:

```text
NEW -> STARTING -> RUNNING -> STOPPING -> STOPPED
                  |
                  +-> FAILED
```

Here **RUNNING** does not mean all business data is valid; it is merely resource state. Clearly design which work is accepted in `RUNNING`, how rejections happen in `STOPPING`, and who finishes in-flight tasks.

### Why don't lifecycle phases replace synchronization?

Suppose Bean A has phase 10 and Bean B has phase 20. Spring starts A before B and stops B before A. That **does not** prevent method invocations from B to A from racing if B spawns multiple threads calling A concurrently. Phases only coordinate **component start/stop milestones**, without adding mutual exclusion inside A's methods.

`@DependsOn` likewise provides no lock for mutable data; it only participates in dependency ordering. Never confuse bean initialization order with state-mutation ordering between tasks.

## 7. Concurrency problems outside lifecycle

### 7.1. Atomicity: can a business operation be torn apart?

`counter++` is read-modify-write; two threads can read the same value and overwrite each other:

```text
Initial Counter = 5

Thread A reads 5
Thread B reads 5
Thread A writes 6
Thread B writes 6

Final result = 6, whereas 7 is needed
```

You can use `AtomicInteger.incrementAndGet()` for a simple counter within one JVM:

```java
private final AtomicInteger counter = new AtomicInteger();

public int addOne() {
    return counter.incrementAndGet();
}
```

**Do not overgeneralize** that multi-step operations are safe merely because individual fields are atomic. Transferring an amount across two balances or checking then updating two separate structures must preserve **the whole-operation invariant**, potentially requiring locks, transactions, or a different state-ownership model.

### 7.2. Visibility: does one thread see another thread's update?

An unsynchronized shutdown flag can be read stale:

```java
// Not a recommended example when shared across threads:
private boolean stopRequested;
```

For an independent flag, `volatile boolean` or `AtomicBoolean` establishes appropriate visibility/happens-before:

```java
private volatile boolean stopRequested;
```

Yet `volatile` does **not** make `count++` atomic. Passing immutable structures through a `BlockingQueue` or `CompletableFuture` can also help establish clear synchronization edges.

### 7.3. Ordering: completion differs from submission order

With a multi-worker pool:

```text
submit A (takes 2 seconds)
submit B (takes 20 ms)

Complete B
Complete A
```

Submission order does **not** imply completion order. If business rules require sequential processing per `accountId` or `aggregateId`, pick an explicit model: single-consumer queue, partitioning by key, per-key serial executor, or persisting events with sequence/version checks on processing. Never merely put `@Order` on two runner beans or adjust lifecycle phases.

### 7.4. Deadlock: locks or Futures waiting on each other

Two tasks can acquire two locks in opposite order:

```text
Thread A: lock X -> wait for lock Y
Thread B: lock Y -> wait for lock X
```

Spring can still create executors and close the context cleanly in order without fixing this cycle. Design **consistent lock ordering**, avoid holding locks across I/O or re-entrant callbacks, and use appropriate timeouts/cancellation.

**Thread pool starvation deadlock** can also happen if a task on a single-worker pool submits another task to the same pool and calls `future.get()` to wait: the sole worker is blocked, leaving the awaited task with no thread to run. This is a work-orchestration bug, not a bean lifecycle bug.

### 7.5. Shared data: ConcurrentHashMap does not make compound sequences atomic

`ConcurrentHashMap` is safe for individual map operations. Yet:

```java
if (!map.containsKey(key)) {
    map.put(key, newValue);
}
```

is still a **check-then-act** of two calls that can interleave. To insert if absent, use `putIfAbsent` or `computeIfAbsent` appropriately and understand the mapping function's semantics. For invariants spanning multiple resources, design broader coordination.

## 8. Backpressure: unbounded queues turn failures into memory growth

Suppose a service receives 1,000 tasks/second while the executor processes an average of 200 tasks/second. With an unbounded queue, backlog grows by roughly 800 tasks every second, eventually spiking latency, heap usage, and OOM risk.

`ThreadPoolTaskExecutor` lets you tune pool size, queue capacity, and rejection. Yet queue settings **do not decide the business policy** when full:

| Policy | Technical meaning | What must be decided |
|---|---|---|
| Fast reject | `RejectedExecutionException` or `TaskRejectedException` depending on API | When should callers retry? Return 429/503 or business error? |
| Wait for capacity | Caller waits until space frees | Max deadline and risk of exhausting request threads? |
| Caller-runs | Caller directly runs the rejected task if policy allows | Could it block an event loop or time out requests? |
| Drop | Discards a task from the queue or refuses intake | Is losing work acceptable? Who notices to recover? |
| Persist outside JVM | Writes to broker/database and processes later | How do acks/transactions/deduplication and durability work? |

No single policy fits every case. Marketing emails may tolerate queuing/retries; payments demand strict idempotency and durability. For short-deadline UI requests, waiting long in a queue can be worse than failing fast.

**Separate three limits**: concurrent workers, queued tasks, and total time from submit to completion. A small pool with a huge queue may appear "stable" with low CPU while latency is unacceptable.

## 9. Cancellation, interruption, and deadlines

Java provides `Thread.interrupt()`, `Future.cancel(...)`, `ExecutorService.shutdown()`, `shutdownNow()`, and `CompletableFuture`. None of those APIs guarantees an arbitrary task stops instantly and restores prior state.

- `ExecutorService.shutdown()` stops accepting new tasks and lets submitted ones finish; it **does not wait** for completion.
- `awaitTermination(...)` waits for the executor to finish up to a specified deadline.
- `shutdownNow()` attempts to stop running tasks (usually via interrupt) and returns unstarted tasks, yet cannot force a task ignoring interrupts to exit.
- `Future.cancel(true)` requests cancellation per implementation semantics; it is not a database rollback.
- `CompletableFuture.cancel(...)` should not be assumed to interrupt underlying I/O unless the implementation wires cancellation to the actual resource.

Example task respecting interruption:

```java
try {
    while (!Thread.currentThread().isInterrupted()) {
        doOneUnitOfWork();
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Exit the loop and perform appropriate cleanup.
}
```

This is an **integration snippet**; `doOneUnitOfWork()` must exist with clear interruption semantics and error handling. Never put infinite loops in constructors or `@PostConstruct`. In real systems, network/database calls also need their own timeouts; a `SmartLifecycle` timeout **does not automatically abort** an HTTP request.

### End-to-end deadlines

If a request only has 1 second remaining for total processing while you submit a task taking up to 4 seconds, the caller may time out before the task completes. The task keeps running after the client left, potentially writing unwanted data.

A sound design defines:

1. Absolute deadline or remaining budget.
2. Maximum queue wait.
3. I/O and processing budget.
4. How far cancellation propagates.
5. Which work must finish even if the caller canceled (such as durable commits).
6. Final result recording and idempotency if clients retry.

## 10. Transactions, ThreadLocal, MDC, and SecurityContext

A common real-world bug: assuming everything on the request thread automatically appears on the worker thread.

`@Transactional` in the standard Spring model binds the transaction context to **the executing thread**. When submitting a `Runnable` from a transactional method onto another thread, **never assume the active transaction transfers to the worker**. If the worker performs transactional data work, establish a new transaction boundary on the worker side via a proper bean/proxy or dedicated message processing.

Similarly:

- MDC/tracing context can rely on `ThreadLocal`. Switching threads without propagation loses trace IDs.
- Security context must be propagated through proper security mechanisms if the worker needs identity verification; never blindly copy arbitrary thread-locals.
- Request-scoped beans may be invalid once the request finishes.
- Uncleaned `ThreadLocal` values in a thread pool can cause **cross-request data leaks**.

Spring offers `TaskDecorator` and helpful tracing/security integrations, yet decorators only handle **propagating defined context**, not races, retries, or data invariants. For long-running background tasks, consider passing **minimal immutable context** such as correlation ID, tenant ID, command ID, or business key via task parameters instead of carrying the entire request context.

## 11. Java 17 + Spring Boot 3.3 example: a lifecycle-managed worker with queued data

This sample project illustrates the boundary by deliberately writing a `SmartLifecycle` component with **one worker thread**, a bounded queue, and shutdown via `stop(Runnable)`. It only performs integer addition, with no database, network, or broker.

We intentionally avoid `@Async` in the main demo to spotlight **two separate responsibilities**:

- Spring creates, starts, and stops `ManagedQueueWorker`.
- `ManagedQueueWorker`'s own code preserves **task intake/closing** and **processing order** through a single queue.

In production systems, consider Spring-managed `ThreadPoolTaskExecutor`/`TaskScheduler` rather than spawning raw threads. The demo is not a distributed processor or complete implementation for every crash/concurrent-stop scenario.

### 11.1. Project structure

```text
task-boundary-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/taskboundary/
    ├── TaskBoundaryApplication.java
    └── ManagedQueueWorker.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'task-boundary-demo'
```

**`build.gradle` (Groovy DSL):**

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

No Spring Web, Actuator, or third-party libraries are needed. If using `./gradlew`, the project needs a Gradle Wrapper generated by Spring Initializr or a compatible Gradle install; `build.gradle` alone does not generate wrapper scripts.

### 11.2. Worker: managing intake and state

**`src/main/java/com/example/taskboundary/ManagedQueueWorker.java`:**

```java
package com.example.taskboundary;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public final class ManagedQueueWorker implements SmartLifecycle {

    private record Job(int delta, CompletableFuture<Integer> answer) {}

    private static final Job END = new Job(0, null);

    private final BlockingQueue<Job> queue = new ArrayBlockingQueue<>(4);
    private final Object gate = new Object();
    private final AtomicInteger total = new AtomicInteger();

    private volatile boolean running;
    private boolean accepting;
    private Thread workerThread;

    @Override
    public void start() {
        synchronized (gate) {
            if (running) {
                return;
            }

            Thread newWorker =
                    new Thread(this::consume, "counter-worker");
            newWorker.start();

            workerThread = newWorker;
            accepting = true;
            running = true;
            System.out.println("START worker");
        }
    }

    public CompletableFuture<Integer> add(int delta) {
        CompletableFuture<Integer> answer = new CompletableFuture<>();

        synchronized (gate) {
            if (!accepting) {
                answer.completeExceptionally(
                        new IllegalStateException("worker not accepting"));
                return answer;
            }

            if (!queue.offer(new Job(delta, answer))) {
                answer.completeExceptionally(
                        new RejectedExecutionException("queue full"));
            }
        }

        return answer;
    }

    private void consume() {
        try {
            while (true) {
                Job job = queue.take();

                if (job == END) {
                    return;
                }

                // Only one consumer processes each Job in FIFO order.
                int value = total.addAndGet(job.delta());
                job.answer().complete(value);
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        } finally {
            // If worker exits abnormally, do not leave Futures waiting forever.
            Job pending;
            while ((pending = queue.poll()) != null) {
                if (pending != END) {
                    pending.answer().completeExceptionally(
                            new IllegalStateException("worker stopped"));
                }
            }
        }
    }

    public int total() {
        return total.get();
    }

    @Override
    public void stop(Runnable callback) {
        synchronized (gate) {
            accepting = false;
            if (!running) {
                callback.run();
                return;
            }
        }

        // Do not block lifecycle thread with a long drain operation.
        Thread closer = new Thread(() -> {
            boolean interrupted = false;

            // Place END AFTER all already-accepted Jobs.
            for (;;) {
                try {
                    queue.put(END);
                    break;
                } catch (InterruptedException ex) {
                    interrupted = true;
                }
            }

            // Only report finished after worker truly exits.
            for (;;) {
                try {
                    workerThread.join();
                    break;
                } catch (InterruptedException ex) {
                    interrupted = true;
                }
            }

            running = false;
            System.out.println("STOP worker drained");

            if (interrupted) {
                Thread.currentThread().interrupt();
            }
            callback.run();
        }, "counter-closer");

        closer.start();
    }

    @Override
    public void stop() {
        // Support callers wanting synchronous stop via Lifecycle.stop().
        CountDownLatch completed = new CountDownLatch(1);
        stop(completed::countDown);

        boolean interrupted = false;
        for (;;) {
            try {
                completed.await();
                break;
            } catch (InterruptedException ex) {
                interrupted = true;
            }
        }
        if (interrupted) {
            Thread.currentThread().interrupt();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
```

**Analysis of the key boundaries:**

1. `@Component` registers the component; `SmartLifecycle.start()` is invoked by Spring during refresh when the bean qualifies for auto-start.
2. `ArrayBlockingQueue<>(4)` caps the queue at 4 jobs rather than growing memory unboundedly.
3. `synchronized(gate)` guards **the intake decision** together with placing the job in the queue. Checking `accepting` outside the lock and calling `offer` afterward would introduce a race between shutdown and submission.
4. `BlockingQueue` provides synchronization when passing jobs from producer to consumer. `AtomicInteger` ensures atomic increments and safe visibility from other threads; having a single consumer also makes result ordering straightforward.
5. `CompletableFuture<Integer>` reports results or errors. When the queue is full, the method **returns a failed future** instead of silently dropping tasks.
6. `stop(Runnable)` closes intake first, then waits for the worker to process already-accepted jobs before invoking the callback. Spring can await the callback before stopping lower-phase beans.
7. Separate `stop()` supports callers wanting synchronous stopping; `LifecycleProcessor` calls the **callback overload** for `SmartLifecycle`.
8. `isRunning()` stays `true` while draining and only flips to `false` after the worker terminates; `accepting` is a separate rule.
9. `getPhase() = 100` only coordinates lifecycle with other beans if present; it does **not** determine job ordering inside the queue.

**Explicitly stated limitations:** the example is designed for **one start followed by one context close**. It does not guard against concurrent `stop(Runnable)` calls, restart the worker after STOPPED, enforce I/O-level deadlines/cancellation, or provide a durable queue. Production requires a state machine (`NEW/RUNNING/STOPPING/STOPPED`), multi-caller callback tracking, worker-death recovery, deadline enforcement, and persistence where required. Do not use the demo as a mini message broker.

**Abnormal cases to note:** if the worker thread exits unexpectedly, `finally` fails remaining queued jobs; in-flight jobs must ensure `completeExceptionally` on uncaught exceptions. In the demo, integer addition throws no realistic errors. In real business code, wrap each job in proper `try/catch`, complete the future on every path, and account for tasks lost on process death.

### 11.3. Startup class and runner for verification

**`src/main/java/com/example/taskboundary/TaskBoundaryApplication.java`:**

```java
package com.example.taskboundary;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class TaskBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(TaskBoundaryApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            System.out.println("MAIN: close requested");
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    ApplicationRunner showBoundary(ManagedQueueWorker worker) {
        return arguments -> {
            CompletableFuture<Integer> first = worker.add(2);
            CompletableFuture<Integer> second = worker.add(3);

            System.out.println(
                    "RESULT first = "
                    + first.get(3, TimeUnit.SECONDS));

            System.out.println(
                    "RESULT second = "
                    + second.get(3, TimeUnit.SECONDS));

            System.out.println("TOTAL = " + worker.total());
        };
    }
}
```

`ApplicationRunner` runs **after context refresh** and before `ApplicationReadyEvent`. By the time the runner submits tasks, `ManagedQueueWorker` has auto-started via `SmartLifecycle`. The runner **awaits results** with `Future.get(timeout)` because in this demo we want both calculations finished before treating the run phase as done.

Omitting `get(...)` and only submitting and returning lets the runner finish before the tasks. `ApplicationReadyEvent` could then fire while the worker is still processing. This shows **lifecycle does not automatically wait for all work** unless you establish explicit completion conditions.

### 11.4. Running the project

If Gradle Wrapper is present:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

The example intentionally runs no HTTP server, so `try-with-resources` closes the context when `run(args)` finishes. **Never close the context immediately after startup in a real Web service**, because it will stop serving requests.

While Spring Boot/Gradle print banners and logs, **the lines printed by this program itself** have the expected order:

```text
START worker
RESULT first = 2
RESULT second = 5
TOTAL = 5
MAIN: close requested
STOP worker drained
MAIN: context closed
```

Do not use this result to infer that every multi-threaded pool always returns `first` then `second` in order. This stems from **a single consumer** reading FIFO from `BlockingQueue` and `AtomicInteger.addAndGet`. `MAIN: context closed` appearing after `STOP worker drained` comes from Spring coordinating the lifecycle callback; the numbers 2 and 5 come from **the worker's concurrency logic and math**, not automatic framework computation.

### 11.5. Experiment: full queue

In the runner, try submitting many jobs without awaiting each future—for instance 20 times. Since the queue holds only 4 slots and the worker has one thread, depending on machine speed some futures may fail with `RejectedExecutionException`. **The count of rejected tasks is non-deterministic**; the worker dequeuing jobs races with the producer.

When testing, call `get`/`join` or observe completion on each future and log errors rather than ignoring them. Never assert "the 5th task always fails": dequeue timing varies across runs. To test backpressure deterministically, use a barrier/latch to hold the consumer rather than expecting random outcomes.

### 11.6. Experiment: intentionally removing the gate lock

If you move checking `accepting` outside `synchronized(gate)` and call `queue.offer(...)` afterward, the producer may see `accepting=true`, get preempted by the scheduler, and shutdown inserts the sentinel into the queue before the producer enqueues its job. When the producer resumes, the job may land **after** `END` and never get processed.

This is a race between **the intake-closing procedure (lifecycle)** and **the task-acceptance rule (concurrency)**. Wrapping the condition and enqueue atomically with synchronized or an atomic state machine is the application's responsibility; `SmartLifecycle` alone does not protect this operation.

## 12. Why isn't the demo a production concurrency framework?

This is intentional. Grasping the boundary means knowing **what the demo solved and what it left unsolved**.

**The demo solves:**

- A context starting and closing a worker along the lifecycle.
- A bounded queue; explicit results or clear rejections.
- A single sequential consumer preserving FIFO order for accepted jobs.
- An atomically updated counter.
- Stopping intake before inserting `END` and awaiting worker termination before the callback.

**The demo does NOT solve:**

- Process crashes, `kill -9`, power loss, restarts: in-memory jobs are lost.
- Tasks performing infinite I/O or ignoring interruption.
- Multiple callers concurrently calling stop/start/restart.
- Exactly-once guarantees for data outside the JVM.
- Transactions spanning "receive message → process → write result → ack".
- Deadlines and retries with backoff, jitter, and retry budgets.
- Multi-executor/connection dependency chains across phases.
- Tenant governance, authorization, and trace context rules.
- Distributing tasks across multiple replicas.
- Alerting on latency, backlog, task age, async failures, and resource saturation.

Do not "scale up the demo" merely by sprinkling a few `Thread.sleep` calls and calling it a durable queue. As requirements grow, adopt dedicated concurrency libraries, Spring Integration/Batch, message brokers, or separate worker architectures.

## 13. Choose tools by problem rather than by annotation

| Problem | Typical suitable choice | Boundary notes |
|---|---|---|
| Independent computation returning result to caller | `CompletableFuture`/`TaskExecutor` | Needs timeouts, exception propagation, avoiding shared mutable state |
| Scheduled background task on a single instance | `@Scheduled` + `TaskScheduler` | Across multiple replicas, scheduling does not guarantee cluster-wide single execution |
| Turning a service call asynchronous | `@EnableAsync` + `@Async` | Proxies/self-invocation, executors, and context propagation must be right |
| Long-lived component spanning app lifetime | `SmartLifecycle` | Start/stop/phase/callbacks must be right; internals still need concurrency safety |
| Task-processing pool with capacity bounds | `ThreadPoolTaskExecutor` | Pick queue/rejection/backpressure per SLA |
| Maintaining sequential mutable state | Actor/single-consumer/keyed partitioning | Queue must be bounded, stoppable, with clear work acknowledgment |
| Incrementing a counter within one JVM | `AtomicInteger`/`LongAdder` per use case | Insufficient for transactions or distributed counts |
| Updating multiple values with joint invariants | Locks, transactions, immutable snapshots | Cannot be replaced by independent atomic fields |
| Processing messages that may be redelivered | Broker + idempotent consumer + dedupe/ack | Lifecycle does not create system-wide exactly-once |
| Long job needing restarts/retries/checkpoints | Batch/job framework, durable checkpoints | Should not merely run an infinite loop in a runner |
| Massive blocking I/O concurrency | Consider Java 21+ virtual threads | Does not remove resource limits, deadlines, or race handling |

**Do not indiscriminately mark everything `@Async`.** Asynchrony carries observability, error-handling, and operational costs. If an operation is tiny, running synchronously can be simpler and easier to get right. Use concurrency when workload, latency, throughput, or isolation genuinely requires it.

## 14. Virtual threads in Spring Boot 3.3: changing execution, not design obligations

When running **Java 21 or newer**, you can enable:

```properties
spring.threads.virtual.enabled=true
```

Spring Boot 3.3 can configure `SimpleAsyncTaskExecutor` and `SimpleAsyncTaskScheduler` using virtual threads. Pool settings like `spring.task.execution.pool.max-size` do not carry the same meaning for an executor spawning a virtual thread per task; inspect which executor type is active.

Virtual threads help many **blocking I/O** tasks use thread resources more efficiently in certain workloads, yet:

- Do not make `counter++` atomic.
- Do not turn two transactions into one distributed transaction.
- Do not guarantee tasks finish in submission order.
- Do not create automatic queue capacity or quotas for remote services.
- Do not replace backpressure and connection limits.
- Do not give an external API a timeout if the API itself lacks one.
- Can hit performance issues from pinning on certain synchronized paths or native operations; measure on real workloads.

**Operational point:** virtual threads are daemon threads. For apps running only scheduling/background work with no remaining non-daemon threads keeping the JVM alive, the process may exit; Spring Boot 3.3 provides `spring.main.keep-alive=true` for suitable scenarios. This is **process lifecycle management**, separate from invariants of code running on virtual threads.

Do not "switch" a Java 17 project to virtual threads merely by setting the property: this feature requires Java 21+.

## 15. Real-world shutdown: stop, drain, and forced termination

A reliable shutdown typically includes:

```text
SIGTERM or context close request
         |
Mark instance to stop receiving new traffic
         |
Stop intake of new messages/requests/tasks
         |
Give in-flight tasks time to complete
         |
Write/flush results, controlled ack
         |
Close executor, scheduler, broker connections, clients
         |
Signal completion to LifecycleProcessor
         |
Close remaining dependencies, exit JVM
```

Exact ordering depends on architecture. `SmartLifecycle.getPhase()` assists **components inside the same context**: lower phases start first, higher phases stop first. Yet it does not control external message sources or guarantee load balancers stop routing instantly.

Spring Boot 3.3 offers configuration:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

`server.shutdown=graceful` targets the embedded Web server; `spring.lifecycle.timeout-per-shutdown-phase` sets a time limit per lifecycle phase. These two properties **do not automatically make your message consumers drainable**. Furthermore, Kubernetes/OS/container deadlines may be shorter than the sum of phases. On `SIGKILL`/`kill -9`, Java shutdown callbacks are not guaranteed to run.

For Spring-managed executors, options include `setWaitForTasksToCompleteOnShutdown`, `setAwaitTerminationSeconds`, or corresponding executor properties. **Read semantics specifically for Spring Framework 6.1 / Boot 3.3**: some options shift waiting from coordinated lifecycle stop into the destruction phase, affecting which dependencies remain alive when tasks finish. Never copy a property and declare every task guaranteed to complete.

### Limits of timeouts

Spring's timeout bounds how long **Spring waits**, not a timer that automatically rolls back business state or forcibly terminates every thread. If a task gets stuck in network I/O ignoring interrupts, Spring may time out waiting and proceed to close other beans. The still-running task can then hit already-closed dependencies.

Therefore enforce timeouts across layers: queue admission, task deadlines, network clients, executor termination, and orchestrator grace periods. Their timing must relate sensibly rather than picking random numbers per layer.

## 16. Multiple instances: per-JVM lifecycle does not ensure exactly-once

A Spring Boot application running three replicas has three `ApplicationContext` instances, three lifecycles, and likely three executors/schedulers. Each replica **can independently run** its `@Scheduled` jobs or consumers. Starting and stopping cleanly per replica is not enough to guarantee a cluster-wide operation happens once.

Distinguish these concepts:

- **At-most-once:** may lose messages yet avoids reprocessing under certain mechanisms.
- **At-least-once:** may receive and reprocess; requires idempotency/deduplication.
- **Exactly-once effect:** requires defining exact scope (broker, DB, external APIs) and matching transaction/locking/idempotency protocols; **does not come from `@Async` or `SmartLifecycle`**.
- **Ordering by partition/key:** a broker may guarantee order within a partition, yet multi-worker code can still reorder completions.
- **Shutdown/rebalance:** old instances must stop intake/acks at the right time; new instances must take over checkpoints/leases without dropping or duplicating beyond policy.

An idempotency example: store `eventId` with a unique constraint before/atomically with writing business results in a suitable transaction. Merely using an in-RAM `ConcurrentHashMap` to remember IDs does not prevent duplicates across restarts or other replicas.

## 17. Verifying two responsibility groups with two test suites

### 17.1. Lifecycle tests

- Are components registered as beans and started at the right milestone?
- Is `start()` idempotent if invoked again?
- On context close, do components stop accepting new tasks?
- Does `stop(Runnable)` invoke the callback **after draining finishes**, neither too early nor forgotten?
- Do higher-phase beans stop before lower-phase dependencies?
- On timeout, do services log unfinished work status?
- Do any non-daemon threads leak and keep the JVM from exiting?

### 17.2. Concurrency tests

- Do multiple concurrent producers lose or duplicate tasks?
- Does shared data preserve invariants under varied interleavings?
- When the queue is full, what error or backpressure do callers observe?
- Are cancellations and exceptions propagated to whoever needs to know?
- Can two tasks sharing a key execute out of order?
- On retries, can results be written twice?
- Can deadlocks/starvation occur when pools are small and tasks wait on each other?
- Are transaction/security/tracing contexts lost across thread hops?

The two test suites have **different purposes**. Never conclude "thread-safe" just because an integration test starts and closes the context; never conclude "clean shutdown" just because an `AtomicInteger` unit test passed.

### Use synchronization tools instead of guessing with Thread.sleep

In concurrency tests, `CountDownLatch`, `CyclicBarrier`, `Phaser`, or `CompletableFuture` create controlled rendezvous points across threads. `Thread.sleep(50)` does not prove two threads reached a specific point; tests can pass on fast machines and fail under different load.

Completion-testing snippet:

```java
CompletableFuture<Integer> result = worker.add(4);

try {
    int value = result.get(2, TimeUnit.SECONDS);
    System.out.println(value);
} catch (TimeoutException ex) {
    // Have a deadline yet must decide whether to cancel the work.
}
```

This is an **integration test snippet**, requiring `worker`, imports for `CompletableFuture`, `TimeUnit`, and `TimeoutException`, plus handling remaining checked exceptions in the test method. Timing out at the caller does not automatically stop the task; send cancellation to the proper worker/resource when needed.

## 18. Common reasoning errors

| False claim | Why it is wrong | What must be verified |
|---|---|---|
| "Using `@Async` makes it thread-safe" | Annotation only changes execution location | Shared state and happens-before |
| "`@Scheduled` guarantees one job cluster-wide" | Each instance can run its own scheduler | Distributed locks/leases, partition assignment |
| "`ThreadPoolTaskExecutor` never loses tasks" | Bounded queues, shutdown/crashes can drop tasks | Rejection, durability, ack/retry |
| "`shutdown()` means all tasks finished" | It only stops accepting new tasks | `awaitTermination`/completion status |
| "Calling `stop(Runnable)` callback immediately is right" | Workers may still be flushing | Callback after actual draining |
| "Once callback runs, deadlocks are impossible" | Deadlocks live in task/lock algorithms | Lock ordering, pool starvation |
| "`volatile` protects every update" | Visibility differs from atomicity | `Atomic*`, locks, immutable state |
| "`ConcurrentHashMap` makes business transactions atomic" | Sequential operations still race | Composite invariants and transactions |
| "`ApplicationReadyEvent` = all background tasks finished" | Tasks may not have been awaited | Futures/completion or dedicated readiness |
| "`@Transactional` transfers automatically to async threads" | Standard transactions are thread-bound | Worker-side transaction boundaries |
| "Adding virtual threads solves backpressure" | Connections and external capacity stay finite | Resource limits, admission control |
| "SmartLifecycle phase decides task ordering" | Phases only order component start/stop | Serial queues, dependency completion |
| "Spring timeouts force workers to stop" | Threads/I/O can ignore interrupts | Resource deadlines, force-close, recovery |
| "One passing test run means no races" | Interleavings are not guaranteed to recur | Stress tests, deterministic synchronization |
| "Using sleep to wait for init is enough" | Sleep creates no meaningful dependency | Latches/futures/callbacks and explicit state |

## 19. Practice exercises

**Exercise 1 — Identifying boundaries.** Run section 11's project. Classify each stdout line: which come from lifecycle coordination and which from queue/counter algorithms? Explain why `START worker` is not directly responsible for `TOTAL`'s atomicity.

**Exercise 2 — Increasing producer concurrency.** Create 4 producer threads concurrently calling `worker.add(1)`. Await all futures with a deadline. Verify the total equals the exact number of tasks actually accepted and processed; record tasks rejected if the queue fills. Never assume all succeed simply because there is one consumer.

**Exercise 3 — Removing the gate.** Create a test variant removing the lock around checking `accepting` and `queue.offer(...)`. Use a latch to force shutdown between those two steps, and observe the risk of a job landing after the sentinel. Restore the lock and explain why lifecycle callbacks alone cannot fix this bug.

**Exercise 4 — Slowing a job down.** Simulate work in the consumer with a bounded wait; call close before the job finishes. Measure when the stop callback arrives. Never use this example to claim all production tasks drain completely.

**Exercise 5 — Adding rejected futures.** Fill the queue by temporarily holding the consumer at a latch and submitting many jobs. Verify rejected job futures complete exceptionally with `RejectedExecutionException` rather than "disappearing silently".

**Exercise 6 — Non-atomic counter.** Write a plain Java test with multiple threads running `int counter++` and compare against `AtomicInteger.incrementAndGet()`. Note that a race test may coincidentally produce the right answer on one run; repeat runs and explain the memory model rather than relying on a single stdout.

**Exercise 7 — Future and deadlines.** Test `get(1, TimeUnit.MILLISECONDS)` against a controlled slow task. Explain why caller timeout does not mean the task stopped. Propose cancellation/deadline mechanics on the worker.

**Exercise 8 — Self-invoking @Async.** Create two beans, one with an `@Async` method and one caller. Compare calls through the proxy against `this.method()` on the same target. Enable `@EnableAsync` and observe thread names and exception handling.

**Exercise 9 — Two replicas.** Suppose two app instances both run `@Scheduled(fixedRate=1000)` updating the same table. Design a way to prevent duplicate writes: leases, partitioning, or moving to a job service; describe what state data can be in if an instance dies between commit and ack.

**Exercise 10 — Reviewing a production design.** For a message consumer with a database and REST client, specify: (a) worker/pool lifecycle; (b) queue capacity; (c) transaction boundaries; (d) deadlines; (e) duplicate handling; (f) crash recovery; (g) metrics; (h) dependency stop order. With only `@Async` and `@PreDestroy`, many design questions remain unanswered.

### Self-assessment questions

1. Why doesn't `@Async` make `counter++` safe?
2. What ordering does `SmartLifecycle.getPhase()` govern? Does it guarantee FIFO completion of all tasks?
3. If a task is submitted in a runner without awaiting, can `ApplicationReadyEvent` fire before completion?
4. How does `ExecutorService.shutdown()` differ from `awaitTermination(...)` and `shutdownNow()`?
5. Why is an atomic mechanism needed around checking "accepting work" and enqueueing?
6. When a queue is full, why is returning an explicit error usually better than silently dropping tasks?
7. Why shouldn't `@Transactional` on a request thread be assumed to propagate to workers?
8. Do Java 21+ virtual threads replace connection limits, timeouts, and backpressure?
9. If the process dies before acking a message, is a lifecycle shutdown callback guaranteed to run?
10. Which distinct tests are needed to prove **correct shutdown** versus **correct concurrent algorithms**?

## 20. Design summary

When working with threads and tasks in Spring Boot, start with two separate sets of questions:

**Lifecycle:** who creates the executor/worker? When does it start? When does intake stop? Who awaits draining? Which callbacks and phases govern closing dependencies? If the JVM is forcibly killed, how does recovery work?

**Concurrency:** what state is shared? Which operations must be atomic? What ordering is mandatory? What happens when the queue fills? What happens on task timeouts/cancellations/exceptions? If messages redeliver or two replicas run, can data be duplicated or lost?

Spring Boot 3.3 helps configure executors/schedulers and tie lifecycle to the context. Yet **being created and closed cleanly does not prove concurrent logic is right**. A quality design completes both halves: well-managed resources, and data invariants protected across interleaving, overload, cancellation, restarts, or multi-process distribution.

### Official documentation

- Spring Boot 3.3 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.3 — SpringApplication lifecycle/events/runners: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework 6.1 — SmartLifecycle Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/6.1/integration/scheduling.html
- Spring Framework 6.1 — ThreadPoolTaskExecutor Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Java 17 — java.util.concurrent package overview: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html