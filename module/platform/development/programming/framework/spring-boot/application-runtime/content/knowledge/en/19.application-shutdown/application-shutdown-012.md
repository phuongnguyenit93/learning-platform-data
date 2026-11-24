# Diagnosing Stuck Hooks, Unfinished Tasks, and Forgotten Stop Callbacks

## 1. Why Does a Spring Boot App "Refuse to Shut Down"?

When a running Spring Boot application is asked to stop, what follows is not a single `kill` operation. The JVM, `ApplicationContext`, `LifecycleProcessor`, bean destroy callbacks, worker threads, and external resources each have different shutdown contracts.

Three common symptoms look alike yet have distinct root causes:

1. **Stuck shutdown hook or context-closing callback:** the thread responsible for closing is waiting on a lock, network I/O, `Future.get()`, `CountDownLatch.await()`, `@PreDestroy`, or another hook. Here **the close call has not finished**.
2. **Background task does not exit:** Spring already issued shutdown—perhaps `ApplicationContext.close()` even returned—yet a **non-daemon thread** or resource remains alive. The JVM can stay running when closing the context does not itself terminate the process; on shutdown triggered by `System.exit`, the JVM waits for shutdown hooks rather than waiting on all non-daemon threads in the same way.
3. **`SmartLifecycle.stop(Runnable)` forgot its callback:** the bean may already have stopped working, yet `DefaultLifecycleProcessor` never received the completion signal, so it waits until the **phase timeout** before moving on. This is usually a **bounded wait**, not always an infinite hang.

This lesson shows how to **classify symptoms**, gather evidence from thread dumps and logs, reproduce cleanly in a controlled way, find root causes, and fix code according to the contracts of Spring Boot 3.3, Spring Framework 6.1, and Java 17+.

**First principle:** do not bump timeouts or reach for `kill -9` the moment shutdown looks slow. Identify **which stage has not completed**, **which thread is waiting on whom**, and **which resource has not confirmed stopping**. If tasks handle critical data, a forced kill can leave work unacked/uncommitted and require recovery.

## 2. Distinguishing JVM Shutdown Hook, Lifecycle Stop, and Bean Destruction

A normal shutdown path can be depicted as:

```text
SIGTERM / System.exit / context close request
                     |
                     v
       JVM shutdown hook (during JVM shutdown)
            or direct context.close()
                     |
                     v
      Spring ApplicationContext starts closing
                     |
             ContextClosedEvent
                     |
             LifecycleProcessor.onClose()
                     |
           SmartLifecycle.stop(callback)
             in descending phase order
                     |
      wait for callback or per-phase timeout
                     |
                     v
            Destroy singleton beans
         @PreDestroy / DisposableBean /
             @Bean destroy method
                     |
                     v
         ApplicationContext.close() completes
                     |
          JVM proceeds to exit if eligible
```

**This is a simplified logical flow**. `ContextClosedEvent` fires at the start of context closure; receiving it **does not prove** lifecycle stop, bean destruction, and resource flushing have finished. When closing via `System.exit()` or signals, the Java VM runs its shutdown hooks. When calling `context.close()` directly, closing code runs on the calling thread—not necessarily a JVM shutdown-hook thread.

### 2.1. JVM Shutdown Hook

Spring Boot's `SpringApplication` registers a shutdown hook mechanism by default to close `ApplicationContext` when the JVM exits via a supported path. `SpringApplication.setRegisterShutdownHook(boolean)` can configure this before `run`. Do not disable the hook merely to make the process exit faster when resources still need cleanup.

Java's `Runtime.addShutdownHook(Thread)` lets libraries or apps register custom hooks. The JVM starts hooks in an **unspecified order** and allows them to run **concurrently**. Thus you cannot rely on "registering hook A before hook B" to guarantee B runs only after A. If one hook waits for another while both hold mutually dependent locks, the entire shutdown can deadlock.

**Never** call `System.exit()` from inside a shutdown hook as a second-chance stop mechanism. Create hooks only when genuinely required; for resources already belonging to the Spring container, prefer Spring lifecycle/destruction rather than registering a duplicate JVM hook.

### 2.2. SmartLifecycle and Phases

`SmartLifecycle` extends `Lifecycle` and `Phased`. For running beans, `DefaultLifecycleProcessor` invokes:

```java
void stop(Runnable callback);
```

It **does not call parameterless `stop()`** on a `SmartLifecycle` if the implementation provides the callback overload without delegating. To coordinate asynchronous stopping, the callback **must execute after the bean genuinely stops**.

Phase determines order:

```text
Start: lower phase before higher phase
Stop:  higher phase before lower phase
```

For example, a consumer at phase 200 depends on a writer at phase 100: the consumer is asked to stop before the writer. Once the consumer finishes draining, it calls the callback so the processor can move to phase 100. If the callback is missing, the processor waits out the timeout before attempting to stop the writer. If the callback is **called too early**, the writer can close while the consumer is still using it.

In Spring Framework 6.1, `DefaultLifecycleProcessor` defaults to **30,000 ms per shutdown phase** unless adjusted; in Spring Boot 3.3 you can configure:

```properties
spring.lifecycle.timeout-per-shutdown-phase=3s
```

This is the wait budget for **one phase group**, not a total timeout for the entire context-closing sequence.

### 2.3. @PreDestroy and Destroy Methods

After lifecycle stopping, Spring destroys singleton beans and invokes callbacks such as:

- `@PreDestroy` on Spring beans (`jakarta.annotation.PreDestroy` in Spring Boot 3.x).
- `DisposableBean.destroy()`.
- Explicit `@Bean(destroyMethod="close")` destroy methods or suitable inferred methods.

These callbacks can **run synchronously and block the context-closing thread**. Setting `spring.lifecycle.timeout-per-shutdown-phase` **does not impose a deadline** on a `@PreDestroy` method stuck in an unbounded socket read, `Thread.join()`, or `CountDownLatch.await()`.

Do not slap `@PreDestroy` on every component assuming Spring guarantees clean async stopping. Each resource needs its own timeouts/cancellation or an appropriate completion mechanism.

## 3. Classifying Symptoms with Three Questions

When a deployment or terminal appears frozen at shutdown, answer in order:

**Question 1 — Has `ApplicationContext.close()` returned yet?**

- If **no**, suspect a `SmartLifecycle` phase waiting for a callback, a blocking destroy method, a hook thread holding a lock, or another cleanup step.
- If **yes**, yet the process stays alive along a direct context-close path, suspect a still-running **non-daemon thread**, an unshut-down library-managed executor, a timer, or a background worker. Some processes stay alive because other code keeps running; verify via thread dumps.
- If handling `System.exit()`, remember the JVM waits for **all shutdown hooks to finish**. Do not infer identical behavior from a direct context close.

**Question 2 — Which phase/callback did the logs stop at?**

- `STOP begin` present with no `STOP callback`, followed seconds later by a phase-timeout log: suspect a forgotten callback, a callback inside a failing worker, or unfinished cleanup.
- `DESTROY begin` present with no `DESTROY end`: suspect a synchronous blocking destroy callback.
- `CONTEXT close completed` present yet process does not exit: suspect threads living outside the lifecycle; check daemon flags and thread stacks.

**Question 3 — What do thread dumps show threads are waiting on?**

- `CountDownLatch.await`, `Future.get`, `Thread.join`, `ConditionObject.await`: find **who is supposed to signal** and what that thread is doing.
- `ThreadPoolExecutor.awaitTermination`: find unfinished tasks and whether they respond to interruption.
- `BLOCKED` on a monitor: find the monitor owner; suspect lock contention/deadlock.
- `SocketInputStream`, driver I/O, native read: check client/resource-level timeouts.
- `DefaultLifecycleProcessor` waiting on a phase latch: inspect `stop(Runnable)` logs to see which bean has not called back.

Do not equate `TIMED_WAITING` with "stuck": an idle thread pool normally waits on its queue. Combine **stack location**, **shutdown stage**, **elapsed time**, and **multiple dump samples**.

## 4. Quick Diagnostic Matrix

| Symptom | Evidence to look for | Probable cause | Fix |
|---|---|---|---|
| Slow stop matching phase timeout | `DefaultLifecycleProcessor` log; callback never appeared | `SmartLifecycle` forgot callback | Call callback only after real cleanup finishes; test timeout |
| Suspiciously fast stop while work continues | Callback arrived right after `shutdown()` | Premature callback | Wait on `awaitTermination`/completion per semantics |
| `@PreDestroy begin` present without end | Thread dump inside destroy method | Untimed I/O, lock, or Future | Resource-level deadlines, controlled force-close |
| Context closed yet Java process stays alive | Dump shows non-daemon worker | Unshut-down executor / task ignoring interrupts | Design shutdown/rejection/cancellation |
| Hook thread waiting on `CountDownLatch.await` | Dump shows hook stack | No thread calls `countDown` or deadlock | Fix completion protocol |
| Hook and worker hold/wait on locks | Dump shows `BLOCKED` cycle | Deadlock | Consistent lock order; never await Future while holding lock |
| High CPU during shutdown | Multiple dumps show `RUNNABLE` loop | Spin loop lacking stop flag/visibility | Check `volatile`/atomics/cancellation |
| Hangs only in IDE | IDE uses forced stop or different signal | Never traversed graceful shutdown path | Reproduce with valid signal or close |
| Hangs only in container | Grace period too short, sidecar/network dependency stopped early | Wrong shutdown budget/order | Align multi-layer timeouts |
| `jcmd` fails to connect | Different PID/namespace/user/JDK, attach unavailable | Environment restriction | Run tools inside container or use supported dump signals |
| `ContextClosedEvent` logged yet still waiting | Event occurs before stop/destroy | Misunderstood lifecycle milestone | Add start/end logs for every phase/callback |
| Stop runs twice | Both JVM hook and direct close, or multiple destroy paths | Resource close lacks idempotency | Single owner, OPEN/CLOSING/CLOSED state, shared completion |

Each row is a **hypothesis**, not an automatic conclusion. Collect stack traces and timelines to prove root cause before changing architecture.

## 5. Gathering Evidence While the JVM Is Alive

### 5.1. Record the Timeline Before Intervening

From logs/telemetry, record:

1. Timestamp when `SIGTERM`/stop request arrived.
2. Timestamp when `ApplicationContext.close()` or the shutdown hook started.
3. Bean names/phases when `stop(Runnable)` is invoked.
4. Timestamp when intake stopped, in-flight count, and queue length.
5. Timestamp when callbacks were invoked and phases advanced.
6. Timestamps when `@PreDestroy` started/ended.
7. Timestamp when context closure finished and when the process actually exited.

Example of helpful logging (pseudocode):

```text
15:00:00.000 shutdown-requested pid=12345
15:00:00.008 lifecycle-stop-begin bean=consumer phase=200 inflight=3
15:00:00.180 consumer-drained inflight=0
15:00:00.181 lifecycle-stop-callback bean=consumer phase=200
15:00:00.185 lifecycle-stop-begin bean=writer phase=100
15:00:00.250 lifecycle-stop-callback bean=writer phase=100
15:00:00.260 bean-destroy-begin bean=dbClient
15:00:00.310 bean-destroy-end bean=dbClient
15:00:00.312 context-closed
```

This is an **illustrative timeline**, not default logs printed automatically by Spring Boot. In production, structure logs with `bean`, `phase`, `thread`, `durationMs`, and `outcome`; avoid logging payloads/secrets.

### 5.2. Finding the Java PID

Linux/macOS with JDK:

```bash
jcmd -l
```

or:

```bash
jps -lv
```

In containers, the PID seen from the host may differ from the PID inside the namespace. Run tools **in the same PID namespace with matching permissions and JDK/attach tooling**, never guessing a PID from another instance's logs.

Windows PowerShell:

```powershell
jcmd -l
```

If tools are missing from the JVM host (e.g., JRE-only image), prepare an environment-appropriate capture procedure—do not install ad-hoc tooling directly into production pods lightly.

### 5.3. Capturing Multiple Thread Dumps

Suppose the PID is `12345`:

```bash
jcmd 12345 Thread.print -l > dump-1.txt
sleep 2
jcmd 12345 Thread.print -l > dump-2.txt
```

Or try:

```bash
jstack -l 12345 > dump-jstack.txt
```

Your JDK/VM may support additional options; check `jcmd 12345 help Thread.print`. One dump helps, while **two or three dumps spaced briefly apart** reveal whether stacks are progressing or frozen. Capture only while the JVM is alive; once hit by `SIGKILL`, attaching for final state is impossible.

Windows PowerShell (once PID is known):

```powershell
jcmd 12345 Thread.print -l | Out-File dump-1.txt
Start-Sleep -Seconds 2
jcmd 12345 Thread.print -l | Out-File dump-2.txt
```

With HotSpot on Linux, you can request a dump to process stdout/logs via:

```bash
kill -QUIT 12345
```

**`SIGQUIT`** triggers a thread dump in many HotSpot/Linux builds; it differs from `SIGTERM`, which requests termination. Verify VM, platform, and permissions before sending signals. Never confuse `kill -9` (forced kill) with a stack-collection tool.

### 5.4. Which Thread Stacks to Read First?

Prioritize:

- Threads related to `SpringApplicationShutdownHook` or `SpringContextShutdownHook` if similarly named, or threads with `AbstractApplicationContext.doClose` and `DefaultLifecycleProcessor.stopBeans` on the stack.
- Threads executing `DisposableBeanAdapter.destroy`, `@PreDestroy`, or custom `close()`.
- Workers named after executors/message consumers/queues that refuse to exit.
- Threads waiting on `CountDownLatch.await`, `FutureTask.get`, or `ThreadPoolExecutor.awaitTermination`.
- Threads holding monitors that other threads are waiting on.

**Do not diagnose from thread names alone.** Names depend on Spring Boot/JDK/library versions and app naming. Stack frames, monitor owners, and runtime data are the hard evidence.

### 5.5. Sample Dumps Distinguishing Normal Waits from Bugs

An illustrative excerpt **not taken from a live Spring dump**:

```text
"SpringApplicationShutdownHook" ... TIMED_WAITING
  at java.util.concurrent.CountDownLatch.await(...)
  at org.springframework.context.support.DefaultLifecycleProcessor...
```

This may be the lifecycle processor awaiting a phase callback. If it continues after timeout and the context closes, a callback was missing or too slow.

Another pattern:

```text
"SpringApplicationShutdownHook" ... TIMED_WAITING
  at java.util.concurrent.ThreadPoolExecutor.awaitTermination(...)
  at com.example.Worker.close(...)
  at ... DisposableBeanAdapter.destroy(...)
```

This is waiting inside a destroy callback. **`timeout-per-shutdown-phase` does not necessarily affect this await.**

Another pattern:

```text
"custom-worker-1" ... RUNNABLE/TIMED_WAITING
  at com.example.Worker.longRunningLoop(...)
```

When the context is already closed yet this non-daemon thread stays alive, inspect the loop for exit conditions or interrupt handling.

### 5.6. JFR and Actuator

JDK Flight Recorder can analyze blocking, lock contention, CPU, and I/O prior to shutdown. Example (if the process still allows attach):

```bash
jcmd 12345 JFR.start name=shutdown-check settings=profile duration=30s filename=shutdown-check.jfr
```

Start the recording **before or during the problematic window**; a recording started after the process dies captures nothing. With `duration`, ensure the JVM lives long enough to dump the file and profiling overhead fits the environment.

If Actuator is configured, `/actuator/threaddump` can expose info while the HTTP server still serves requests. During shutdown, the server may have stopped accepting new requests, so **do not rely solely on this endpoint**. Protect it from public access to avoid leaking stacks, paths, or sensitive info.

## 6. Diagnosing Forgotten SmartLifecycle Callbacks

### 6.1. The stop(Runnable) Contract

In Spring Framework 6.1's `SmartLifecycle`, `stop(Runnable callback)` has two jobs:

1. Request/execute stopping the component.
2. **Invoke the exact Spring-provided callback once stopping finishes.**

`DefaultLifecycleProcessor` uses this callback to know the bean finished. Whether you spawn a thread or use a `CompletableFuture`, the callback will not run itself if you forget it.

Wrong way:

```java
@Override
public void stop(Runnable callback) {
    consumer.stopAsync();
    // Callback not attached to completion.
}
```

This is an intentionally buggy snippet; `consumer` is a hypothetical library. Calling `stopAsync()` does not mean cleanup finished, and Spring has no way to know when stopping ends.

Another wrong way:

```java
@Override
public void stop(Runnable callback) {
    consumer.stopAsync();
    callback.run(); // Reports completion too early.
}
```

When the callback fires before the resource truly stops, Spring can move on to stopping lower-phase beans (e.g., writers/databases) while the consumer is still using them.

### 6.2. How to Identify Which Bean Forgot Its Callback?

Add logs **before calling stop**, **when the resource actually finishes**, and **right before the callback**:

```java
@Override
public void stop(Runnable callback) {
    log.info("stop-begin bean={} phase={}", "consumer", getPhase());

    CompletionStage<Void> stage = consumer.stopAsync();

    stage.whenComplete((ignored, error) -> {
        try {
            if (error != null) {
                log.error("consumer-stop-failed", error);
                forceCloseIfNecessary();
            }
        } finally {
            log.info("stop-callback bean={}", "consumer");
            callback.run();
        }
    });
}
```

This is **integration pseudocode**, not a self-contained class: `consumer`, `log`, and `forceCloseIfNecessary()` must be properly implemented. Error branches must ensure stop/force-close finishes per policy before signaling completion; never assume `finally` proves all data flushed.

If `stage` never completes due to hung I/O, the callback never runs. That is why you need **resource/future-level timeouts**, not just `LifecycleProcessor` timeouts.

### 6.3. Easily Missed Branches

- `stop(Runnable)` returns early because `!running` yet forgets to invoke the callback.
- `executor.execute(cleanupTask)` throws `RejectedExecutionException` before scheduling the callback.
- Cleanup throws mid-way; the callback sits only at the end of the happy path.
- `CompletableFuture.thenRun(...)` skips when the future completes exceptionally; use `whenComplete`/`handle` with an error policy.
- A callback is queued onto an executor whose own pool already shut down.
- Parameterless `stop()` holds the stop logic, while the `stop(Runnable)` overload does not delegate.
- The callback is called **twice** from both `try` and `finally`; the second call is not a valid retry.

Inspect **every control-flow path**, not just the happy path. Within a single `stop(Runnable)` invocation, invoke the callback exactly once and only after the resource reaches its stopped state per contract.

## 7. Diagnosing Tasks That Do Not Exit After shutdown()

### 7.1. ExecutorService Shutdown APIs Differ

| API | What it guarantees | What it does not guarantee |
|---|---|---|
| `shutdown()` | Stops accepting new tasks, lets accepted tasks finish | Does not wait for tasks to finish |
| `isShutdown()` | Shutdown was requested | Not equivalent to terminated |
| `awaitTermination(timeout, unit)` | Waits up to a bound, returns `true` if terminated | Does not kill running tasks |
| `shutdownNow()` | Attempts to interrupt running tasks and returns unstarted ones | Cannot force tasks that ignore interrupts to stop |
| `isTerminated()` | Executor finished after shutdown | Does not prove business transactions committed |
| `Future.get(timeout, unit)` | Waits on a future within a bound | Caller timeout does not cancel the task itself |

Easy mistake:

```java
executor.shutdown();
System.out.println("All tasks stopped"); // Unfounded!
```

A standard pattern uses `shutdown()`, `awaitTermination`, then `shutdownNow()` at deadline, waits a bounded interval again, and **reports unconfirmed status** if still not terminated.

### 7.2. Why Doesn't shutdownNow() Solve It?

Interruption is a **cooperative** mechanism. If a task writes:

```java
while (true) {
    try {
        Thread.sleep(1000);
    } catch (InterruptedException ignored) {
        // Wrong: swallows interrupt and loops forever.
    }
}
```

calling `shutdownNow()` may never terminate that thread. This is intentionally buggy code; **never run it in a production process**.

Likewise, blocking I/O or native code lacking proper timeouts may not react to interrupts as expected.

Fix this by designing **stop flags**, cancellation, I/O library timeouts, closing sockets/channels to unblock where supported, and recovery paths when completion is unconfirmed.

### 7.3. Self-Wait Deadlock Bug

A task running on a single-worker executor calls:

```java
executor.shutdown();
executor.awaitTermination(30, TimeUnit.SECONDS);
```

right **inside that same worker**. The executor cannot terminate until the current task returns, while the task waits for the executor to terminate. This is self-wait starvation. Run shutdown coordination on another thread, or use an async approach that does not block the finishing worker itself.

A similar case: task A in a single-thread pool submits task B to that same pool and calls `B.get()`. B has no worker available to run. Thread dumps show `FutureTask.get()` and queued tasks, yet Java monitor-based deadlock detectors **do not necessarily report a deadlock**. Hence "`jstack` found no deadlock" is **not** proof that all tasks can make progress.

### 7.4. Non-Daemon Workers Still Alive

A `daemon=false` thread can keep the JVM alive after application code finishes normally. While `System.exit()` initiates the JVM shutdown sequence and waits for hooks, closing the Spring context directly and returning from `main` leaves non-daemon threads as a common reason the process stays alive.

Never solve this by blindly marking every worker as daemon. Daemon threads can be abandoned by the JVM on exit, leaving in-flight work unflushed. Manage executors/workers through proper owners and shutdown.

## 8. Diagnosing Hooks Stuck on Locks, Futures, or I/O

### 8.1. JVM Hooks Have No Guaranteed Registration Order

Dangerous example:

```java
Runtime.getRuntime().addShutdownHook(new Thread(() -> {
    otherHookCompleted.await();
}));
```

This is buggy pseudocode with unhandled checked exceptions. If the "other" hook never signals or waits on a lock held by this hook, the JVM can hang forever. Never design dependencies among JVM shutdown hooks based on execution order.

When resources belong to a Spring context, use **one coordinator inside the context** for phase ordering rather than creating multiple JVM hooks waiting on each other.

### 8.2. Waiting on a Future While Holding a Lock

An anti-pattern:

```java
synchronized (sharedLock) {
    Future<?> result = executor.submit(() -> {
        synchronized (sharedLock) {
            flush();
        }
    });

    result.get(); // Caller holds sharedLock and waits for worker that needs sharedLock.
}
```

This is **buggy pseudocode**: it assumes real `sharedLock`, `executor`, and `flush()`, with checked exceptions handled. Hooks or destroy callbacks can hang in `Future.get` while workers hang `BLOCKED` waiting on the lock—a circular dependency.

Fix by **never awaiting Futures while holding locks the task needs**; flip state under lock, release the lock before draining, or design events/completions that do not re-enter the same monitor.

### 8.3. I/O Without Timeouts

A shutdown callback calls `client.close()`, which underneath flushes over the network and waits indefinitely for server acknowledgement. Spring cannot stop this with `spring.lifecycle.timeout-per-shutdown-phase` if it runs **synchronously inside a destroy method**. Configure timeouts on the client/driver or design bounded async stopping with a force-close policy.

Merely wrapping `client.close()` in a `CompletableFuture` and calling `get(2, SECONDS)` **does not interrupt** the close call on the underlying thread. If the source thread never exits, the problem just moved to another worker and still keeps the process alive.

### 8.4. Hook Stuck Due to Wrong Shutdown Order

Suppose a consumer needs a DB client to flush, yet the DB client closed first. The consumer retries forever or hangs on a Future whose result never arrives. Verify the relationship:

```text
Start: database client -> writer -> consumer
Stop:  consumer -> writer -> database client
```

`SmartLifecycle.getPhase()` and the dependency graph define order; higher phases are asked to stop first. Still, changing phases alone **does not help** if callbacks fire too early or tasks lack deadlines.

## 9. Runnable Example: Four Shutdown Diagnostics Modes

The project below targets **Spring Boot 3.3.x + Java 17**, Gradle Groovy DSL, **with no Web server**. We create two separate components:

- `DemoLifecycle`: a `SmartLifecycle` that can intentionally forget its callback in `missing-callback` mode.
- `DemoBlockingResource`: a `@PreDestroy` bean that can spawn a worker ignoring interrupts for a **bounded 25-second duration** (`stuck-task`) or wait **12 seconds** inside destroy (`stuck-destroy`).

Both failure modes are strictly for learning/testing, **never for production**. Durations are bounded for easy observation; runtime behavior may vary due to OS scheduling.

### 9.1. Project Structure

```text
shutdown-diagnostics-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/shutdowndiag/
    │   ├── ShutdownDiagnosticsApplication.java
    │   ├── DemoLifecycle.java
    │   └── DemoBlockingResource.java
    └── resources/
        └── application.properties
```

**`settings.gradle`:**

```groovy
rootProject.name = 'shutdown-diagnostics-demo'
```

**`build.gradle`:**

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
spring.application.name=shutdown-diagnostics-demo
spring.lifecycle.timeout-per-shutdown-phase=2s
logging.level.org.springframework.context.support.DefaultLifecycleProcessor=DEBUG
demo.mode=normal
demo.via-hook=false
```

`demo.mode` and `demo.via-hook` are **custom example properties**, not built-in Spring Boot properties. `spring.lifecycle.timeout-per-shutdown-phase=2s` merely shortens the wait in lifecycle stop to demonstrate a forgotten callback; it does **not** cap `@PreDestroy`.

### 9.2. DemoLifecycle: Complete or Intentionally Forgotten Callback

**`src/main/java/com/example/shutdowndiag/DemoLifecycle.java`:**

```java
package com.example.shutdowndiag;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public final class DemoLifecycle implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean();
    private final String mode;

    public DemoLifecycle(@Value("${demo.mode:normal}") String mode) {
        this.mode = mode;
    }

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("LIFECYCLE: started phase=100");
        }
    }

    @Override
    public void stop(Runnable callback) {
        if (!running.getAndSet(false)) {
            callback.run();
            return;
        }

        System.out.println("LIFECYCLE: stop begin");

        if ("missing-callback".equals(mode)) {
            System.out.println("LIFECYCLE: callback intentionally missing");
            // INTENTIONALLY WRONG: demo only, to observe phase timeout.
            return;
        }

        System.out.println("LIFECYCLE: callback delivered");
        callback.run();
    }

    @Override
    public void stop() {
        running.set(false);
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

In `normal`, the callback runs after simulated stop work with no pending async tasks. In `missing-callback`, the bean sets `running=false` yet **intentionally skips calling the callback**. `DefaultLifecycleProcessor` still waits until the phase deadline even though the bean's flag shows stopped. This proves callbacks and status flags **cannot replace each other**.

Parameterless `stop()` is present to satisfy `Lifecycle`, yet **Spring calls `stop(Runnable)`** for `SmartLifecycle`. The example leaves `stop()` minimal so the callback path stands out clearly.

### 9.3. DemoBlockingResource: Uncooperative Worker and Slow Destroy

**`src/main/java/com/example/shutdowndiag/DemoBlockingResource.java`:**

```java
package com.example.shutdowndiag;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class DemoBlockingResource {

    private final String mode;
    private ExecutorService executor;

    public DemoBlockingResource(
            @Value("${demo.mode:normal}") String mode) {
        this.mode = mode;
    }

    @PostConstruct
    void init() {
        if (!"stuck-task".equals(mode)) {
            return;
        }

        executor = Executors.newSingleThreadExecutor(task -> {
            Thread thread = new Thread(task, "demo-uncooperative-worker");
            thread.setDaemon(false);
            return thread;
        });

        executor.submit(() -> {
            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(25);

            // INTENTIONALLY WRONG: ignores interruption signal in demo.
            while (System.nanoTime() - deadline < 0) {
                LockSupport.parkNanos(
                        TimeUnit.MILLISECONDS.toNanos(200));
                Thread.interrupted(); // reads and CLEARS interrupt flag
            }

            System.out.println("TASK: finite demo worker finally ended");
        });

        System.out.println("TASK: demo worker started");
    }

    @PreDestroy
    void destroy() {
        System.out.println("DESTROY: begin");

        if ("stuck-destroy".equals(mode)) {
            System.out.println("DESTROY: blocking for at most 12s");

            try {
                new CountDownLatch(1).await(
                        12, TimeUnit.SECONDS);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                System.out.println("DESTROY: interrupted");
            }
        }

        if (executor != null) {
            executor.shutdown();

            try {
                if (!executor.awaitTermination(
                        1, TimeUnit.SECONDS)) {
                    System.out.println(
                            "DESTROY: executor grace period expired");
                    executor.shutdownNow();

                    if (!executor.awaitTermination(
                            1, TimeUnit.SECONDS)) {
                        System.out.println(
                                "DESTROY: worker still alive!");
                    }
                }
            } catch (InterruptedException ex) {
                executor.shutdownNow();
                Thread.currentThread().interrupt();
                System.out.println(
                        "DESTROY: termination wait interrupted");
            }
        }

        System.out.println("DESTROY: end");
    }
}
```

**Why is this strictly a simulated failure scenario?**

- `stuck-task` intentionally uses `Thread.interrupted()` to clear the interrupt flag instead of stopping cleanly like production code. The worker still exits after ~25 seconds on a monotonic clock to avoid an infinite loop in the example.
- `ExecutorService.shutdown()` followed by `shutdownNow()` cannot force that task to end early, so destroy logs `worker still alive!` and returns.
- Because the worker is **non-daemon**, a run using direct context close can remain alive **after** `MAIN: context closed` until the thread finishes on its own.
- `stuck-destroy` simulates an overly slow bean destroy callback. It caps at 12 seconds via `CountDownLatch.await(timeout, unit)` so it does not hang forever.
- Never copy `Thread.interrupted()` in a loop to "handle" interrupts in real apps; that is an intentional bug illustration.

### 9.4. Main Class: Closing Context Directly or via JVM Shutdown Hook

**`src/main/java/com/example/shutdowndiag/ShutdownDiagnosticsApplication.java`:**

```java
package com.example.shutdowndiag;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ShutdownDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ShutdownDiagnosticsApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context =
                application.run(args);

        boolean viaHook = context.getEnvironment()
                .getProperty("demo.via-hook", Boolean.class, false);

        if (viaHook) {
            System.out.println("MAIN: System.exit invokes JVM shutdown");
            System.exit(0);
            return; // Does not return on the normal path.
        }

        System.out.println("MAIN: closing context directly");
        context.close();
        System.out.println("MAIN: context closed");
    }

    @Bean
    ApplicationRunner printReadyMarker() {
        return arguments ->
                System.out.println("RUNNER: completed");
    }
}
```

By default, the code calls `context.close()` **from the `main` thread**. With `--demo.via-hook=true`, it switches to `System.exit(0)` to trigger the JVM shutdown hook chain. Spring Boot 3.3 registers a hook by default to close the context; thread names in dumps/logs may vary by version. No manual `Runtime.addShutdownHook(...)` is needed.

**Never put `System.exit(0)` arbitrarily in libraries or production services.** This is an intentional test branch to observe **the difference between direct context close and JVM-initiated shutdown**.

### 9.5. Running in Normal Mode

If the project has Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

If writing the files manually, generate a Gradle Wrapper with a compatible Gradle installation or initialize via Spring Initializr; `build.gradle` does not generate `gradlew`/`gradlew.bat` automatically.

Lines **printed by the example code itself**, omitting Boot banners/logs:

```text
LIFECYCLE: started phase=100
RUNNER: completed
MAIN: closing context directly
LIFECYCLE: stop begin
LIFECYCLE: callback delivered
DESTROY: begin
DESTROY: end
MAIN: context closed
```

Most milestones appear in exact order because the context starts `SmartLifecycle` before runners, stops lifecycle before destroying singletons, and `main` prints `context closed` only after `close()` returns.

### 9.6. Reproducing a Forgotten Callback

```bash
./gradlew bootRun --args='--demo.mode=missing-callback'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.mode=missing-callback"
```

Lines to observe:

```text
LIFECYCLE: stop begin
LIFECYCLE: callback intentionally missing
... [wait close to the 2s phase timeout, Spring logs may appear] ...
DESTROY: begin
DESTROY: end
MAIN: context closed
```

**The ellipsis line is only a timing annotation**, not mandatory literal stdout. The defining event is that the callback was never invoked, and the processor waits out the phase's time budget before continuing closure. Different configs/versions may emit warnings or debug logs with varying text; do not write tests matching error text verbatim.

To fix, remove the `missing-callback` branch and ensure every exit path of `stop(Runnable)` invokes the callback after cleanup. **Do not "fix" by setting timeout to 0**: that only hides the symptom.

### 9.7. Reproducing an Unfinished Worker

```bash
./gradlew bootRun --args='--demo.mode=stuck-task'
```

Key lines:

```text
TASK: demo worker started
...
MAIN: closing context directly
LIFECYCLE: stop begin
LIFECYCLE: callback delivered
DESTROY: begin
DESTROY: executor grace period expired
DESTROY: worker still alive!
DESTROY: end
MAIN: context closed
... [process may stay alive due to non-daemon worker] ...
TASK: finite demo worker finally ended
```

Ordering between `TASK: demo worker started` and other Spring component creation milestones can vary; do not assert it as the sole app stdout. **Unlike a missing callback**, here lifecycle completed and the context already closed, yet the worker kept running because it intentionally ignored interruption.

Right after `worker still alive!`, run `jcmd` from another terminal to see the `demo-uncooperative-worker` thread. If you act too slowly, the 25-second demo task may already have finished; restart to observe. Never use `kill -9` for this exercise when the task is already time-bounded.

### 9.8. Reproducing a Slow Destroy Callback

```bash
./gradlew bootRun --args='--demo.mode=stuck-destroy'
```

You will see:

```text
MAIN: closing context directly
LIFECYCLE: stop begin
LIFECYCLE: callback delivered
DESTROY: begin
DESTROY: blocking for at most 12s
... [waiting inside @PreDestroy, not waiting for lifecycle callback] ...
DESTROY: end
MAIN: context closed
```

While waiting, capture a thread dump. The `main` thread will be inside `CountDownLatch.await` inside `DemoBlockingResource.destroy()` via Spring bean destruction. **Changing `spring.lifecycle.timeout-per-shutdown-phase=1s` does not shorten these 12 seconds**, because it happens **after the stop phase has already completed**.

### 9.9. Observing the Real JVM Shutdown Hook

Build the JAR:

```bash
./gradlew bootJar
```

Then launch the hook variant of the slow-destroy mode:

```bash
java -jar build/libs/shutdown-diagnostics-demo-0.0.1-SNAPSHOT.jar --demo.mode=stuck-destroy --demo.via-hook=true
```

Windows PowerShell:

```powershell
java -jar build/libs/shutdown-diagnostics-demo-0.0.1-SNAPSHOT.jar --demo.mode=stuck-destroy --demo.via-hook=true
```

This time `main` calls `System.exit(0)`. When Spring's shutdown hook runs context close, `@PreDestroy` again waits ~12 seconds; you can observe the **shutdown-hook thread** stack in `jcmd Thread.print` if you attach in time while the VM still accepts commands. If attaching during JVM shutdown fails, rely on instrumented logs/timelines or reproduce via `context.close()` to pinpoint the blocking callback. Attachability during VM exit depends on the JVM and OS.

**Important:** the JVM runs shutdown hooks concurrently and waits for them to finish; another hook may still be running while Spring's hook is stuck. Never assume hook ordering between Spring and third-party libraries.

## 10. Writing `stop(Runnable)` Properly: Callback After Real Stop

A pattern for a resource with an async API returning `CompletionStage`:

```java
@Override
public void stop(Runnable callback) {
    if (!running.get()) {
        callback.run();
        return;
    }

    CompletionStage<Void> completion;

    try {
        completion = client.stopAsync();
    } catch (RuntimeException error) {
        recordFailure(error);
        finishStopUsingFallback();
        callback.run();
        return;
    }

    completion.whenComplete((ignored, error) -> {
        try {
            if (error != null) {
                recordFailure(error);
                finishStopUsingFallback();
            }
            running.set(false);
        } finally {
            callback.run();
        }
    });
}
```

This is an **illustrative integration skeleton, not a standalone compiling class**: `running`, `client`, `recordFailure`, and `finishStopUsingFallback` are project-implemented components. The fallback must have real semantics and bounded duration; the callback must fire only after stop/force-close reaches its terminal state per policy. Never use `finally` to claim stopping finished if the fallback hung or only dispatched an interrupt.

When completion can arrive through multiple branches or concurrent stop calls, use a state machine:

```text
RUNNING
   |
   | stop requested (single owner)
   v
STOPPING
   |
   +-- success -> STOPPED
   |
   +-- timeout/error -> FAILED_TO_STOP / FORCE_STOPPED
```

If two callers invoke `stop(Runnable)`, the design should run **only one cleanup** while ensuring **every callback supplied by Spring/callers** is notified once upon completion. An `AtomicBoolean` picks the owner cleanly, though it **does not replace a completion object** for later callers. If the bean is not running, invoke the callback immediately.

### Testing the Callback with CountDownLatch

```java
CountDownLatch completed = new CountDownLatch(1);
AtomicInteger calls = new AtomicInteger();

component.stop(() -> {
    calls.incrementAndGet();
    completed.countDown();
});

if (!completed.await(3, TimeUnit.SECONDS)) {
    throw new AssertionError("stop callback missing");
}

if (calls.get() != 1) {
    throw new AssertionError("callback count=" + calls.get());
}
```

This is an **integration test snippet**: `component` is a started instance; import `CountDownLatch`, `AtomicInteger`, and `TimeUnit`, and handle `InterruptedException` in the test method. A single assertion right when the latch opens only checks the count **at that instant**; if duplicate late callbacks are suspected, test concurrency and full state transitions.

## 11. Writing Bounded Executor Shutdown

### 11.1. A Two-Step Policy

If a bean **owns** an executor:

```java
executor.shutdown();

try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        List<Runnable> notStarted = executor.shutdownNow();
        recordNotStarted(notStarted);

        if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
            reportUnconfirmedTermination();
        }
    }
} catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
    reportInterruptedShutdown(ex);
}
```

This is an **integration snippet** requiring an `ExecutorService` variable `executor`, helper functions `recordNotStarted`, `reportUnconfirmedTermination`, `reportInterruptedShutdown`, and imports. The `5s` and `2s` timeouts are examples; choose values from SLAs and process budgets.

**Separate the outcomes:** `shutdownNow()` is a *forced attempt*, whereas `isTerminated()` confirms *the executor finished*. If a task ignores interrupts, threads may still remain even after the second 2-second wait. Never log "graceful complete" on that branch.

### 11.2. Why Must Waiting Happen on the Right Thread?

If `@PreDestroy` runs `awaitTermination` synchronously, it blocks the context-closing thread. That can fit if deadlines are short and the work is critical. However, to coordinate phase-based stopping via `SmartLifecycle`, perform the work asynchronously and invoke the callback upon completion rather than running long waits **directly on the `LifecycleProcessor` thread** where the processor cannot track phase timeouts properly.

A `stop(Runnable)` implementation can still do tiny fast synchronous cleanup before dispatching async work; however, submitting that work must handle `RejectedExecutionException` in case the cleanup executor already closed.

### 11.3. Why Isn't Setting Pool Size Enough?

An executor with a large queue can still hold hundreds of tasks on stop; calling `shutdown()` means waiting for all accepted tasks, potentially exceeding budgets. You need to:

- Stop intake first.
- Track `inFlight` and queue depth.
- Prioritize finishing truly critical work.
- Set deadlines on I/O and tasks.
- Define which tasks may retry after restart.
- Handle unstarted tasks returned by `shutdownNow()`.

**A clean lifecycle does not mean zero lost messages.** When processing broker messages, acks/offsets/transactions and idempotency must be designed separately.

## 12. What Evidence Proves "Shutdown Is Done"?

Do not rely solely on a log line like:

```text
shutdown requested
```

Define clearer completion signals:

| Signal | What it proves | What it does not prove |
|---|---|---|
| `ContextClosedEvent` published | Context started closing | Beans finished destroying |
| `SmartLifecycle.stop(Runnable)` called | Bean was asked to stop | Resources stopped |
| Callback invoked | Bean **reported** completion to processor | Actual cleanup quality, if code called it wrongly |
| `DefaultLifecycleProcessor` timed out | Phase wait budget exhausted | Bean completed |
| `ExecutorService.isShutdown()` | Executor close was requested | Tasks finished |
| `ExecutorService.isTerminated()` | Executor terminated | All business side effects committed |
| `@PreDestroy` returned | Destroy method returned | External service received flush/ack unless verified |
| `ApplicationContext.close()` returned | Synchronous context close path finished | JVM has no remaining non-daemon threads |
| JVM process disappeared | OS no longer has that process | Zero data loss or zero duplicates on restart |

A well-instrumented shutdown should classify outcomes like **GRACEFUL_TERMINATED**, **FORCED_TERMINATED**, **TIMED_OUT_UNCONFIRMED**, **INTERRUPTED**, or **FAILED** per system standards. These are illustrative application labels, **not a built-in Spring Boot enum**.

## 13. Diagnosing from Logs to Code: An Actionable Investigation Workflow

### Step 1 — Identify the Shutdown Path

Ask: did the operator use `SIGTERM`, `System.exit()`, `context.close()`, IDE Stop, or `kill -9`? Wait budgets and hook execution **differ**.

With Kubernetes, also verify container termination grace period, `preStop` hooks, readiness, and traffic admission. An IDE may stop processes differently from server signals.

### Step 2 — Mark Milestones with Small, Safe Logs

Add logs at four points:

- Start/end of `stop(Runnable)`.
- Before/after `callback.run()`.
- Start/end of `@PreDestroy`/destroy methods.
- Before/after `ApplicationContext.close()` if the app owns that call.

Do not overhaul shutdown logic right before investigating; excessive logging changes can alter race timing. If tracing/metrics already exist, inspect them first.

### Step 3 — Capture 2–3 Thread Dumps While Alive

Compare thread names, states, stacks, and locks. If a thread stays in the same `Future.get()` across samples, find which future never completed; if in `ThreadPoolExecutor.awaitTermination()`, find which worker never exited. If `DefaultLifecycleProcessor` is awaiting a phase, find which callback never arrived.

### Step 4 — Compare Against Wait Budgets

Build a table:

```text
SIGTERM grace budget:                 30s (example)
SmartLifecycle phase consumer:         8s
SmartLifecycle phase web server:       8s
Destroy executor/database:             6s
Safety margin:                         8s
```

These numbers are **illustrative only**, not Spring Boot defaults. Multiple phases can add up; `@PreDestroy` and non-lifecycle I/O need separate budgets. If the worst-case sum exceeds the grace period, the OS can force-kill before cleanup completes.

### Step 5 — Reproduce with a Minimal Mode Before Fixing

Classify against the demo:

- `missing-callback`: stop log appears yet callback is missing, wait approximates phase timeout.
- `stuck-task`: context close finished, non-daemon task stays alive.
- `stuck-destroy`: close blocked in destroy method longer than phase timeout.
- `via-hook=true`: same destroy problem, running inside the JVM shutdown hook rather than `main`.

Remove failure-simulation snippets from production code after reproducing.

### Step 6 — Fix at the Right Layer

- **Missing callback:** fix `stop(Runnable)`; ensure callback runs on every completion branch.
- **Unfinished task:** fix loops, interruption, I/O timeouts, and executor ownership.
- **Blocked destroy:** add deadlines/cancellation/force-close on resources; fix lock/Future dependencies.
- **Hooks waiting on each other:** reduce JVM hooks; use Spring lifecycle phases/owners.
- **Short grace budget:** measure and allocate realistic time, never just raising timeouts to mask bugs.

### Step 7 — Re-Verify with Failure Scenarios

A solid shutdown fix should withstand: `close()` called twice, new jobs arriving during stop, worker interruption, task I/O timeouts, one bean throwing in stop, SIGTERM with in-flight tasks, and staying within controllable wait budgets.

## 14. Why Don't Phase Timeouts Fix Stuck Hooks?

`spring.lifecycle.timeout-per-shutdown-phase` helps while `DefaultLifecycleProcessor` waits for **callbacks within a phase**. However:

- A `@PreDestroy` calling `Thread.sleep(60000)` is not governed by that phase callback timer.
- A `DisposableBean.destroy()` waiting on an untimed socket can block long after every `SmartLifecycle` bean stopped cleanly.
- A JVM shutdown hook outside the Spring context can hang independently of Spring configuration.
- An unterminated non-daemon worker can keep the process alive after direct context closure.
- A task ignoring interrupts does not die when a phase times out.

Increasing `timeout-per-shutdown-phase` only changes how long Spring **is willing to wait** for those callbacks. It is not a thread-kill command. Once thread dumps identify the cause, fix **the exact blocking operation**.

## 15. Avoiding Deadlocks During Shutdown

Review rules that eliminate many bugs:

1. Never await a future while holding a lock that the future needs.
2. Never shut down an executor from a task inside that executor and await termination.
3. Never call `System.exit` again from a shutdown hook.
4. Never rely on JVM hook registration order.
5. Never close dependencies (writer/database) while consumers still need to flush.
6. Never use an already shut-down executor to submit its own cleanup task.
7. Never let exceptions drop callbacks.
8. Never invoke callbacks right when sending a stop request if resources remain active.
9. Never hold a `synchronized` lock across network I/O or custom code that may re-enter the same monitor.
10. Never treat `@Async`, `@Scheduled`, or `@PreDestroy` as an automatic "wait for everything to finish" mechanism.

Good designs avoid progress-blocking wait cycles. If shutdown needs workers to finish work, **workers themselves must listen for stop signals and exit blocking calls**.

## 16. Observability and Telemetry Checklist

A minimal dashboard/log set for shutdown can include:

- `shutdown_requested_timestamp`.
- `application_context_close_started` and `completed`.
- `lifecycle_stop_started{bean,phase}`.
- `lifecycle_callback_seen{bean,phase}`.
- `lifecycle_phase_timeout{phase}`.
- `executor_active_threads`, `executor_queue_size`, `executor_unfinished_tasks`.
- `executor_shutdown_requested` and `executor_terminated`.
- `destroy_started{bean}`, `destroy_completed{bean}`.
- `shutdown_duration_ms`.
- `shutdown_outcome` with values graceful, forced, timeout, or unconfirmed.

These are **suggested telemetry names**, not metrics built automatically into Spring Boot. Even with Actuator/Micrometer, you must still instrument custom metrics for your workers.

Avoid metric series with **unbounded-cardinality labels like job ID or user ID**. When diagnosing specific jobs, prefer controlled structured logs/traces instead of exploding time-series counts.

## 17. Common Premature Conclusions

| Premature conclusion | Why is it wrong? | How to verify |
|---|---|---|
| "Saw `ContextClosedEvent`, so shutdown is done." | Event fires before lifecycle stop/destroy | Log real completion |
| "No deadlock reported, so code isn't stuck." | Future waits, I/O, and starvation aren't always flagged by detectors | Read thread stacks and queues |
| "Thread in `TIMED_WAITING` must be deadlocked." | May be idle wait or valid deadline | Compare multiple dumps and timeline |
| "Calling `shutdownNow()` must kill tasks." | Interruption is cooperative | Check `isTerminated` and task code |
| "`isShutdown=true` means all tasks finished." | `isShutdown` only confirms the request | Check `isTerminated` |
| "`SmartLifecycle` set `running=false`, no callback needed." | Processor waits for callback | Invoke callback after stop |
| "Setting Spring timeout to 2s limits `@PreDestroy` to 2s." | Phase timeout does not govern destroy callbacks | Resource-level deadlines |
| "Process still alive means context hasn't closed." | Non-daemon workers can keep running | Distinguish close-complete from process-exit |
| "Raising the grace period is a fix." | May just hide an unbounded wait bug | Prove bounded cleanup |
| "Hook runs after an earlier-registered hook." | JVM hook order is not guaranteed | Use lifecycle/dependencies for order |
| "Callback arrived means all data committed." | Callback may fire early or code has bugs | Verify flush/ack/termination |
| "Stuck hook requires immediate `kill -9`." | Loses thread dumps and clean recovery chance | Capture evidence per safe runbook |
| "JFR captured after process death still shows root cause." | Recordings must capture data before death | Record early, dump while alive |

## 18. Step-by-Step Practice Lab

Run in a test environment using section 9's project. Change only one factor per exercise to isolate causes cleanly.

**Exercise A — Clean baseline.** Run `./gradlew bootRun`. Record lifecycle stop, callback, destroy, and context close milestones. Confirm zero lingering tasks.

**Exercise B — Missing callback.** Run `--demo.mode=missing-callback`. Measure duration from `LIFECYCLE: stop begin` to `DESTROY: begin`. Change phase timeout from 2s to 4s and observe the wait change; then revert.

**Exercise C — Forgotten callback on error branch.** In a test `SmartLifecycle` class, make cleanup throw before the callback. Use a `CountDownLatch` unit test to confirm the callback never arrives. Add an error/force-close path that still signals completion.

**Exercise D — Premature callback.** Call `executor.shutdown()` and invoke the callback immediately while tasks still run. Add a lower-phase writer bean and observe the risk of the writer stopping before tasks flush. Run only in a test environment with no real data.

**Exercise E — Unfinished task.** Run `--demo.mode=stuck-task`; capture a thread dump while `demo-uncooperative-worker` is alive. Explain why `Context.close()` already finished while the process still waits for the non-daemon worker to finish.

**Exercise F — Fix task to respect interrupts.** Replace the `Thread.interrupted()`-clearing loop with a valid stop-flag/`isInterrupted()` loop plus interrupt handling and cleanup. Verify `shutdownNow()` stops the task before the test deadline.

**Exercise G — Blocked destroy.** Run `--demo.mode=stuck-destroy`, capturing a dump while in `CountDownLatch.await`. Change `spring.lifecycle.timeout-per-shutdown-phase` and prove this timeout **does not** cap the destroy method.

**Exercise H — Shutdown hook.** Run the JAR with `--demo.mode=stuck-destroy --demo.via-hook=true`. Observe the destroy method executing from the JVM shutdown path. Compare stacks with `context.close()` from `main`.

**Exercise I — Future/get deadlock.** Write a small test with a single-worker executor: task A submits B to the same executor and waits on B. Inspect the dump showing `Future.get` blocking the sole worker; then fix by avoiding circular waits or expanding execution without self-blocking.

**Exercise J — Shutdown budget.** Determine your test environment's SIGTERM deadline and list timeouts for lifecycle phases, destroy, network, and executors. Size deadlines short enough to leave headroom before forced JVM termination.

**Exercise K — Idempotency test.** Invoke shutdown twice nearly concurrently and verify cleanup runs only once; subsequent callers still observe stopped state. Never treat a `closing=true` flag as proof of completion.

**Exercise L — Production scenario.** Write a runbook for a stuck deployment: PID, pod/container, signal sent, log timestamps, 2–3 thread dumps, waiting phase/bean, executor owner, in-flight job count, temporary mitigation, and long-term code fix.

### Self-Check Questions

1. Why doesn't receiving `ContextClosedEvent` prove shutdown finished?
2. What signal does `DefaultLifecycleProcessor` wait for after calling `SmartLifecycle.stop(Runnable)`?
3. When a callback is missing, what does the phase timeout do? Does it kill the stuck resource?
4. If `@PreDestroy` waits forever, does lowering `spring.lifecycle.timeout-per-shutdown-phase` fix it?
5. Why can't `shutdownNow()` guarantee an arbitrary task finishes?
6. What is the difference between `isShutdown()` and `isTerminated()`?
7. When the process stays alive after `context.close()`, which thread types should you inspect?
8. In thread dumps, are `WAITING` and `BLOCKED` enough to claim a deadlock?
9. Why isn't registration order guaranteed between two JVM shutdown hooks?
10. When should you run `jcmd Thread.print -l` instead of only raising log levels?
11. Can you call `Future.get()` while holding a lock that the task needs to finish?
12. How do you confirm a stop procedure has deadlines and avoids unintended data loss?

## 19. Decision-Making Summary

| What are you seeing? | What to check next |
|---|---|
| Waits roughly the shutdown phase timeout | Look for `SmartLifecycle.stop(Runnable)` missing its callback or slow cleanup |
| Context closed yet JVM stays alive | Thread dump: non-daemon threads, executors, and non-exiting loops |
| `@PreDestroy begin` logged then hangs | Dump destroy thread; resource-level locks, Futures, I/O timeouts |
| Hook thread holds lock while worker is BLOCKED | Find wait cycle; fix lock ordering, release locks before await |
| Called `shutdownNow()` yet worker won't stop | Check interrupt handling and I/O cancellation |
| JVM force-killed before cleanup | Compare budgets against grace period; prepare recovery |
| Callback invoked yet flush unfinished | Move callback after real completion; verify dependency phases |

**Conclusion:** shutdown diagnosis starts by identifying whether you are waiting on a **JVM shutdown hook**, a **Spring lifecycle callback**, a **destroy method**, or a **still-living worker**. Then use timelines and thread dumps to pinpoint the exact blocker. `SmartLifecycle.stop(Runnable)` needs its callback after stopping; `ExecutorService` needs real termination; `@PreDestroy` needs its own deadlines; and JVM hooks must never be assumed to run sequentially. Timeouts are wait limits, **not proof that stopping or data persistence succeeded**.

## 20. Official Documentation

- Spring Boot 3.3 — `SpringApplication`: shutdown hook registration and lifecycle milestones: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Graceful Shutdown and `spring.lifecycle.timeout-per-shutdown-phase`: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — `SpringApplication.setRegisterShutdownHook` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework 6.1 — `SmartLifecycle` Javadoc and callback requirements: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `DefaultLifecycleProcessor` and default phase timeout: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Java SE 17 — `Runtime.addShutdownHook`, JVM shutdown hook ordering: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html
- Java SE 17 — `ExecutorService`: `shutdown`, `shutdownNow`, `awaitTermination`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 — Diagnostic tools `jcmd`, `jstack`, and thread dumps: https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html
- Java SE 17 — Troubleshoot Process Hangs and Loops: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-process-hangs-and-loops.html