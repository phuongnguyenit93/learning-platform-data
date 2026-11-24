# Stopping New Work Intake and Draining Running Tasks on Application Shutdown

## Learning objectives

When a Spring Boot application stops to deploy a new version, scale down, perform maintenance, or restart, the process **should not keep accepting new work and abandon already-accepted tasks**. Safe shutdown usually consists of two related yet distinct parts:

1. **Close the intake gate for new work** (*stop admission*): new HTTP requests, new queue messages, or executor submissions are no longer accepted per application policy.
2. **Wait for accepted work to finish under control** (*drain in-flight work*): running or queued tasks are processed to completion, or routed to an explicit timeout/cancellation/retry branch.

Both steps belong to **Spring Boot Application Runtime → Threads and Tasks**. They tie into `ApplicationContext.close()`, `ContextClosedEvent`, `SmartLifecycle`, `ExecutorService`, `ThreadPoolTaskExecutor`, graceful HTTP shutdown, and deployment platform deadlines.

After this lesson, you will be able to:

- Distinguish in-flight requests (*in-flight*), accepted tasks still in the queue (*queued*), new submissions (*new submission*), and completed tasks.
- Accurately explain `ExecutorService.shutdown()`, `shutdownNow()`, `awaitTermination(...)`, and behavior with `RejectedExecutionException`.
- Write an **admission gate** guaranteeing no gap between checking "still accepting work" and submitting a task to the executor.
- Use `SmartLifecycle.stop(Runnable callback)` to stop intake and signal completion only when workers have truly stopped per contract.
- Configure Spring Boot **3.3.13** to handle in-flight HTTP requests with `server.shutdown=graceful` and understand `spring.lifecycle.timeout-per-shutdown-phase`.
- Configure `ThreadPoolTaskExecutor` to wait for queued/running jobs during bean destruction; know the limits of that option for new tasks submitted during close.
- Run a Java 17+ / Spring Boot 3.3 example with a blocked task, a separate thread closing the context, new requests rejected, and old work finishing before context close completes.
- Design timeouts, retry/idempotency, SIGTERM, readiness, and grace periods to reduce lost-work risk in production.

**Reference versions:** Spring Boot 3.3.x (example uses **3.3.13**), Spring Framework 6.1.x, Java 17+. Newer Spring Boot versions may change graceful shutdown **defaults** or executor details; do not apply a newer version's defaults to Boot 3.3.

## 1. The problem: "stopping the app" does not mean "no work remains"

Suppose an application:

- Serves an HTTP endpoint `POST /jobs` accepting report-processing requests.
- Enqueues work onto a thread pool or queue.
- Has a running job that takes 12 seconds.
- Receives a stop signal when container orchestration wants to replace the pod.

If the process closes database connections or exits the JVM immediately, the job can be cut off mid-flight. If it merely waits for running jobs without **blocking new submissions**, another thread can keep adding work and stretch the wait indefinitely.

Two boundaries must be designed:

~~~text
                        BEFORE STOPPING
request / message -----> [ACCEPT] -----> queue -----> workers
                             |                           |
                             +---------------------------+
                                 complete / write results

                            WHEN STOP IS ORDERED
                                    |
                                    v
                         close admission gate
                                    |
                 +------------------+------------------+
                 |                                     |
             new work                            accepted work
             [REJECT]                               [DRAIN]
                 |                                     |
      return error / retry-after                 run or queued
      / do not ack message                       until completion
                                                       |
                                      timeout? -------+------> handle error
                                                       |
                                                       v
                                            close executor/resources
                                                       |
                                                       v
                                            complete context close
~~~

A well-operated application must define **what counts as "accepted"**. For example, returning HTTP `202 Accepted` before persisting the job to a durable DB/queue is dangerous, because the client thinks the server took responsibility while the process could vanish before the job is saved.

**Rule:** Stop accepting new work first, then wait for accepted work; do not treat stopping HTTP requests as sufficient to stop all background jobs.

## 2. Four states to distinguish

| State | Meaning | Handling during shutdown |
| --- | --- | --- |
| `NEW` | Request not yet accepted or undergoing admission check | Reject explicitly, return appropriate response, or let source retry |
| `QUEUED` | Task accepted and placed in executor/queue, not yet started | Allow finishing under drain policy, or move to durable store |
| `RUNNING` | Worker started task, possibly holding connections/transactions | Wait to finish within deadline; interrupt only per cancellation policy |
| `COMPLETED` | Task finished per business criteria, results/acks durable as needed | No rerun needed; resources can close afterward |

Do not use **active threads = 0** as the sole criterion: if the queue still holds tasks, having zero running threads at one instant does not mean all work has been processed.

Likewise, **queue size = 0** does not mean every task finished: workers may have pulled every task out of the queue and still be processing them.

To track draining, use appropriate metrics such as **accepted**, **running**, **queued**, **completed**, **failed**, **rejected**, **in-flight**, **await timeout**, and jobs needing retry.

### "Stop accepting new work" has multiple sources

A Spring Boot app can have several ingress paths:

1. **HTTP:** Spring MVC/Tomcat, WebFlux/Reactor Netty, or a reverse proxy.
2. **Message queues:** Kafka/RabbitMQ/JMS listeners may continue polling/consuming unless paused.
3. **Schedulers:** `@Scheduled` or custom schedulers may continue triggering tasks.
4. **Task executors:** Other beans may call `execute`/`submit`.
5. **Manual threads:** `new Thread(...)` or `Executors.new...` outside Spring management.

Each source needs its **corresponding intake blocker**. `server.shutdown=graceful` does not automatically send "stop polling" to a Kafka consumer or stop a custom executor Spring does not manage.

## 3. Safe closing sequence: quiesce → drain → dispose

Shutdown can be split into three stages:

### 3.1. Quiesce: stop admitting new work into the system

Quiesce means transitioning the instance to stop accepting further work. Examples:

- Deregister from receiving new traffic at the load balancer, combined with graceful server shutdown.
- Block job-submission endpoints at the admission layer.
- Pause/stop message listeners per library contract so they stop polling when unable to process.
- Stop schedules creating new jobs or reject requests entering the executor.

**Do not merely flip a boolean and call `executor.execute(...)` without locking.** Two threads can race: thread A reads `accepting == true`, thread B closes the gate and shuts down the executor, and thread A still tries to submit. You need a linearizing synchronization mechanism (*linearization point*) or proper handling of `RejectedExecutionException`.

### 3.2. Drain: complete already-accepted work

Once no new jobs enter, allow:

- Running tasks to finish.
- Queued tasks to be processed by workers if the policy intends to **drain the entire backlog**.
- Commit/flush/ack operations to execute in order without closing needed resources prematurely.

**Deadlines are mandatory in production:** An infinitely hung task or one ignoring interrupts must not hold the process forever. When time expires, enforce an explicit policy: mark incomplete, retry/redeliver, save checkpoint, route to dead-letter, request forced stop, or let the orchestrator intervene.

### 3.3. Dispose: close resources once tasks no longer need them

Only after relevant work finishes should you close the resources they rely on: database connection pools, HTTP clients, producers/consumers, file handles, and executors.

If you close the database pool **before** a worker commits its result, draining might finish on paper while data is corrupted. Therefore lifecycle/dependency ordering between **consumers**, **worker executors**, and **resource providers** is critical.

## 4. ExecutorService.shutdown() and shutdownNow() differ

Java SE provides `java.util.concurrent.ExecutorService` with two methods carrying very different semantics.

### shutdown(): stop accepting new tasks, let existing ones continue

~~~java
executor.shutdown();
~~~

`shutdown()` requests an **orderly shutdown**:

- Tasks submitted **before shutdown** remain eligible to run, including running and queued tasks.
- Tasks submitted **after shutdown** are rejected.
- `shutdown()` **does not wait** for tasks to finish; it returns after issuing the stop signal.

To wait, call `awaitTermination(...)`:

~~~java
executor.shutdown();

boolean terminated =
        executor.awaitTermination(15, TimeUnit.SECONDS);

if (!terminated) {
    System.err.println("Executor did not finish within deadline");
}
~~~

This is a **partial illustrative snippet**, requiring an `ExecutorService executor`, `TimeUnit` import, and `InterruptedException` handling. When `awaitTermination(...)` returns `true`, the executor has terminated per Java's definition. If `false`, the deadline elapsed before completion.

### shutdownNow(): attempts to stop, does not guarantee stopped

~~~java
List<Runnable> neverStarted = executor.shutdownNow();
~~~

`shutdownNow()` typically:

- Attempts to interrupt running tasks (via `Thread.interrupt()`).
- Returns tasks that were in the queue and never started.
- Does not guarantee running tasks actually stop. Tasks ignoring interrupts or blocked on uninterruptible I/O may continue.

**Never use `shutdownNow()` as the default replacement for graceful draining.** For non-idempotent work or work requiring completion, it can leave half-finished state, data loss, or duplicates on job retry.

### awaitTermination() does not block new tasks by itself

~~~java
boolean done = executor.awaitTermination(10, TimeUnit.SECONDS);
~~~

Calling `awaitTermination` alone **before** any shutdown signal does not shut down the executor. It only waits until the executor reaches terminated state, or until the deadline/interrupt. Typical flow:

~~~text
1. stop application admission
2. executor.shutdown()
3. executor.awaitTermination(timeout)
4. if unfinished → escalation per policy
~~~

Do not invert steps 1 and 2 if publishers can submit work to the executor between those steps.

### API table

| API | Blocks new tasks? | Waits synchronously? | Handles queued tasks? |
| --- | --- | --- | --- |
| `execute(task)`/`submit(task)` | No; this submits | Does not wait for task result | Adds job if space exists and executor accepts |
| `shutdown()` | Yes, at executor | No | Keeps already-submitted jobs to finish |
| `awaitTermination(t,u)` | Does not close itself; depends on executor state | Yes, until deadline or terminated | Does not alter queue itself |
| `shutdownNow()` | Yes, and tries interrupting workers | Does not wait for terminated | Returns unstarted queued tasks |
| `isShutdown()` | Checks if shutdown requested | No | Does not confirm tasks finished |
| `isTerminated()` | Checks if executor terminated | No | True only after tasks have ended |

## 5. The admission gate must prevent race conditions

A common buggy pattern:

~~~java
if (accepting.get()) {
    executor.execute(task);
}
~~~

If the shutting-down thread sets `accepting=false` right after the submitting thread reads `true`, the executor may already be shut down and `execute` throws `RejectedExecutionException`. `AtomicBoolean` gives visibility to boolean reads/writes, yet **does not combine** "check then submit" into a single atomic operation.

A simple approach for this lesson uses one monitor guarding **checking, submitting, and closing the gate**:

~~~java
private final Object admissionLock = new Object();
private boolean accepting = true;

public boolean submit(Runnable task) {
    synchronized (admissionLock) {
        if (!accepting) {
            return false;
        }

        try {
            executor.execute(task);
            return true;
        }
        catch (RejectedExecutionException rejected) {
            return false;
        }
    }
}

public void closeAdmission() {
    synchronized (admissionLock) {
        accepting = false;
    }
}
~~~

This is an **illustrative snippet** requiring an `executor` field of type `Executor`/`ExecutorService` and importing `RejectedExecutionException`. Real code should also report rejection reasons and metrics.

With the shared lock:

- A submission succeeding before the gate closes is recorded as **accepted**.
- A submission arriving after the gate closes is rejected.
- No logical gap exists between checking the gate and `executor.execute(...)` for callers obeying the same monitor.
- `RejectedExecutionException` must still be handled: the pool may be full or closed by another mechanism.

Do not hold the admission lock **for the entire duration of running the task**. The lock only protects submission and state transition; otherwise stopping would be blocked by the running work itself.

### What does rejection mean to the caller?

A method returning `false` must make clear to the caller that the job **was not accepted**. Over HTTP, return an appropriate status (often 503 or an app error with `Retry-After` if policy allows); for message consumers, handle ack/nack/redelivery accurately; for internal producers, record for retry or return an error to the caller.

**Avoid the worst-case failure:** the intake layer returns success while in reality the executor rejected the work and no durable log/queue exists to recover it.

## 6. Spring Boot HTTP graceful shutdown: scope of protection

Spring Boot 3.3 supports graceful shutdown for embedded Tomcat, Jetty, Reactor Netty, and Undertow across Servlet and Reactive web applications. To enable it in 3.3, configure:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Or YAML:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Pick whichever format fits your project; these lines are example settings, not a separate file in the section 9 CLI demo.

### What actually happens

- Spring Boot executes graceful web-server shutdown as part of `ApplicationContext.close()`.
- The server **stops accepting new requests in an implementation-specific way** while letting previously accepted requests complete within the grace period.
- `spring.lifecycle.timeout-per-shutdown-phase` caps wait time per **lifecycle processor phase group**, not a single timeout spanning all shutdown work.
- Tomcat/Jetty/Reactor Netty may refuse new connections at the network layer; Undertow in Boot 3.3 docs may return HTTP **503** for new connections/requests. Never write code assuming one uniform rejection style across all servers.

**Limitation:** Graceful web shutdown primarily protects **in-flight HTTP requests**. If a request submitted a job to an executor and returned 202 immediately, the HTTP request finishing **does not prove the background job finished**. You must **drain the executor separately** or hand the job to durable storage/brokers.

### Do not apply newer Spring Boot defaults to 3.3

Some newer Spring Boot versions enable graceful shutdown by default. This lesson uses **Spring Boot 3.3**, so set `server.shutdown=graceful` explicitly when graceful behavior is wanted. Do not extrapolate from current-version docs onto a project still on Boot 3.3.

### An open port is not readiness

The web server can bind its port before the application publishes `ApplicationReadyEvent`, and draining can begin while sockets transition. Load balancers or orchestrators should rely on proper readiness/termination signals rather than merely probing TCP connectivity.

In Kubernetes, the sequence typically involves marking the pod not ready for new traffic, allowing routing propagation, sending SIGTERM, draining, and waiting up to `terminationGracePeriodSeconds`. **PreStop hooks and propagation delays** also consume that same budget; budget end-to-end time rather than only setting one timeout in the application.

## 7. Spring lifecycle and component stopping order

### ContextClosedEvent

Spring Framework publishes `ContextClosedEvent` when `ApplicationContext` is closing. A listener can **signal stopping intake** right when context close begins:

~~~java
@EventListener(ContextClosedEvent.class)
public void rejectNewJobs() {
    accepting.set(false);
}
~~~

This is an **illustrative snippet**, needing an enclosing bean, imports for `EventListener` and `ContextClosedEvent`, and a thread-safe admission gate. Note that `AtomicBoolean` alone does not solve the full "check-then-submit" race shown in section 5; design the gate and rejection handling properly.

Do not cram a tens-of-seconds wait inside a `ContextClosedEvent` listener assuming lifecycle components have already stopped. This event announces that the context is closing; ordered stopping belongs in dedicated lifecycle/destroy hooks.

### SmartLifecycle.stop(Runnable callback)

`org.springframework.context.SmartLifecycle` supports:

~~~java
@Override
public void stop(Runnable callback) {
    // 1) Stop admission
    // 2) Ask workers to stop accepting work
    // 3) Wait for accepted work to complete / handle errors
    // 4) Once truly stopped, callback.run()
}
~~~

This is a **guide snippet**, not a standalone implementation. The `callback` notifies `DefaultLifecycleProcessor` that this component's stop step finished. If the component stops asynchronously, the callback must run **once stopping truly finishes**, not right after submitting a "stop" task.

`SmartLifecycle` also provides:

- `start()` to start the service.
- `isRunning()` to reflect state.
- `isAutoStartup()` to auto-start during context refresh.
- `getPhase()` to coordinate lifecycle group ordering.
- `stop()` from `Lifecycle` for synchronous/explicit stop paths.

**Lower phases start first; higher phases stop first.** Use phases/`@DependsOn` to stop producers/ingress before consumers, and consumers before their underlying resources when appropriate. **Independent beans in the same phase have no guaranteed strict order**; never rely on bean definition order or `@Order` to control stop order.

### Distinguish stop callbacks from "work durably persisted"

A worker may have exited while a job was not yet properly acked/committed. Conversely, a durably persisted job can be reprocessed after restart even if it did not finish in the old process. Therefore lifecycle "stopped cleanly" and business "zero lost jobs" require different criteria, including transactions and retry policies.

## 8. ThreadPoolTaskExecutor and waiting for tasks on Spring shutdown

In Spring applications, `ThreadPoolTaskExecutor` in `org.springframework.scheduling.concurrent` is a convenient wrapper for a Spring-lifecycle-managed thread pool.

A typical configuration:

~~~java
@Configuration
public class ExecutorConfiguration {

    @Bean("backgroundExecutor")
    ThreadPoolTaskExecutor backgroundExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("background-");

        // Allow running tasks and queued tasks to finish on shutdown.
        executor.setWaitForTasksToCompleteOnShutdown(true);

        // Wait up to 20 seconds during executor destruction.
        executor.setAwaitTerminationSeconds(20);

        return executor;
    }
}
~~~

The above is an **illustrative configuration file**; do not add it to section 9's project. In real usage, import `@Configuration`, `@Bean`, and `ThreadPoolTaskExecutor`. Spring initializes the executor bean and manages destruction/lifecycle when the context closes.

### Exact meaning of the two flags

**`setWaitForTasksToCompleteOnShutdown(true)`** instructs the executor to perform a soft/orderly shutdown, not actively interrupt running tasks, and continue executing queued tasks per contract. It can **bypass the coordinated lifecycle stop phase** and defer waiting to the executor's own destruction step.

**`setAwaitTerminationSeconds(20)`** makes the executor's shutdown step **block up to ~20 seconds** awaiting termination before the rest of context destruction continues. This is a wait timeout, **not a guarantee that jobs will finish within 20 seconds**.

Neither setting creates a business-level admission gate by itself. Specifically, `waitForTasksToCompleteOnShutdown(true)` has semantics that allow certain late submissions before the executor actually enters destroy/shutdown; therefore, if the application must say "the moment close begins, accept no more work", **close the publisher/consumer gate first**.

### A specific note for Spring Framework 6.1

`ThreadPoolTaskExecutor` participates in lifecycle stop and handles context-close signals. Properties such as `acceptTasksAfterContextClose`, `strictEarlyShutdown` (since 6.1.4), and `waitForTasksToCompleteOnShutdown` interact with one another. Specifically, options allowing late shutdown can bypass coordinated stop and move waiting to the destroy phase.

Therefore:

- **Do not** randomly set all three flags to `true` hoping "more trues mean more graceful".
- If new jobs must be blocked the instant context close begins, enforce **independent admission control** and test `RejectedExecutionException`.
- If tasks need database/client beans while draining, ensure they **are not destroyed** before the executor finishes waiting; a finite `awaitTerminationSeconds` helps, yet bean ordering must still be designed.
- To tightly govern a producer → worker → dependent resources chain, consider explicit coordination via `SmartLifecycle` instead of only tweaking executor flags.

**Never replace `ThreadPoolTaskExecutor` with `Executors.newFixedThreadPool(...)` in a `@Bean` and forget lifecycle:** if an application creates a raw executor, ensure a destroy hook or owning component manages it as in section 9.

## 9. Complete example: block new tasks, drain old tasks on context close

The Java 17+ / Spring Boot 3.3.13 example below uses a **self-managed executor** inside a `SmartLifecycle` bean. With no HTTP server or database, it focuses on **the admission and drain protocol**.

In the demo:

1. Spring Boot refreshes the context and invokes `WorkCoordinator.start()`.
2. Main submits an initial task and lets it advance to a barrier.
3. Main spawns another thread to call `context.close()`.
4. `stop(Runnable)` closes the gate and signals main that from this point on no further tasks are accepted.
5. Main tries submitting a late task and receives `false`.
6. Main allows the initial task to finish.
7. The lifecycle processor awaits executor termination, receives the callback, and finishes closing.
8. Main waits for the closer thread to finish, then prints the final state.

**Why are there CountDownLatches?** They exist solely to make example log order **deterministic and testable**, independent of `Thread.sleep(...)` or CPU speed.

### 9.1. Project structure

~~~text
graceful-drain-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/drain/
    ├── GracefulDrainApplication.java
    └── WorkCoordinator.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'graceful-drain-demo'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.drain.GracefulDrainApplication'
}
~~~

The project does not use the web starter. If Gradle is not installed, you can add a Gradle Wrapper compatible with Spring Boot 3.3; the structure above omits pre-generated wrapper files. Requires JDK 17+.

### 9.2. WorkCoordinator: SmartLifecycle owning the executor

**`src/main/java/com/example/drain/WorkCoordinator.java`:**

~~~java
package com.example.drain;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;

import org.springframework.context.SmartLifecycle;

public final class WorkCoordinator implements SmartLifecycle {

    private final Object admissionLock = new Object();

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor(r ->
                    new Thread(r, "demo-worker"));

    private final CountDownLatch taskStartPermit =
            new CountDownLatch(1);

    private final CountDownLatch taskStarted =
            new CountDownLatch(1);

    private final CountDownLatch taskFinishPermit =
            new CountDownLatch(1);

    private final CountDownLatch admissionClosed =
            new CountDownLatch(1);

    private volatile boolean running;
    private boolean accepting;

    @Override
    public void start() {
        synchronized (admissionLock) {
            accepting = true;
            running = true;
        }
        System.out.println("LIFECYCLE: started");
    }

    public boolean submitFirstTask() {
        synchronized (admissionLock) {
            if (!accepting) {
                return false;
            }
            try {
                executor.execute(() -> {
                    try {
                        taskStartPermit.await();
                        System.out.println("TASK: running");
                        taskStarted.countDown();

                        taskFinishPermit.await();
                        System.out.println("TASK: completed");
                    }
                    catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        System.out.println("TASK: interrupted");
                    }
                });
                return true;
            }
            catch (RejectedExecutionException rejected) {
                return false;
            }
        }
    }

    public boolean submitLateTask() {
        synchronized (admissionLock) {
            if (!accepting) {
                return false;
            }
            try {
                executor.execute(() ->
                        System.out.println("TASK: unexpected late work"));
                return true;
            }
            catch (RejectedExecutionException rejected) {
                return false;
            }
        }
    }

    public void allowTaskToStart() {
        taskStartPermit.countDown();
    }

    public void awaitTaskStarted() throws InterruptedException {
        if (!taskStarted.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                    "Demo task did not start in time");
        }
    }

    public void awaitAdmissionClosed() throws InterruptedException {
        if (!admissionClosed.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                    "Demo shutdown did not start in time");
        }
    }

    public void allowTaskToFinish() {
        taskFinishPermit.countDown();
    }

    @Override
    public void stop(Runnable callback) {

        // Gate closes before the executor stops accepting tasks.
        synchronized (admissionLock) {
            accepting = false;
        }
        System.out.println("SHUTDOWN: admission closed");
        admissionClosed.countDown();

        executor.shutdown();

        try {
            boolean terminated =
                    executor.awaitTermination(15, TimeUnit.SECONDS);

            if (!terminated) {
                System.err.println(
                        "SHUTDOWN: deadline exceeded; interrupt requested");
                executor.shutdownNow();
                terminated =
                        executor.awaitTermination(2, TimeUnit.SECONDS);
            }

            if (terminated) {
                running = false;
                System.out.println("SHUTDOWN: drained");
                callback.run();
            }
            else {
                // Do not report "stopped" while a worker is still alive.
                System.err.println(
                        "SHUTDOWN: incomplete; worker may still run");
            }
        }
        catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            executor.shutdownNow();
            System.err.println(
                    "SHUTDOWN: waiting thread interrupted");
        }
    }

    @Override
    public void stop() {
        stop(() -> { });
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
        return 0;
    }
}
~~~

**Key points in the code:**

- The same `admissionLock` guards checking `accepting`, enqueueing the task, and setting `accepting=false`; therefore submissions through this bean cannot slip past the gate after it closes.
- `CountDownLatch` is purely an experiment control mechanism: the initial task is submitted, waits for main's start signal, then waits for main's completion signal.
- `executor.shutdown()` rejects new jobs at the executor while allowing previously submitted jobs to continue.
- `awaitTermination(15, SECONDS)` waits with a deadline. The main demo always lets the task finish well before the deadline.
- If the deadline expires, the code requests interruption with `shutdownNow()` and waits briefly; it **does not claim interruption is guaranteed to stop the task**.
- `callback.run()` is called only in the branch where the executor **truly terminated**, and `running` switches to `false` in that branch. If termination cannot be confirmed, the code logs an error and lets the lifecycle processor handle timeout instead of falsely reporting a clean stop.
- For a production component, add policies if interrupted while awaiting (overall deadline, escalation, telemetry, external supervisor). The demo focuses on clarifying **when invoking the callback is permitted**.

On the error path after calling `shutdownNow()`, the task may be cut short; **never call that situation "business-drained successfully"** if the task was required to finish. `SHUTDOWN: drained` in the code means **executor terminated**, not certifying every job committed cleanly under interruption. The normal path of the example does not hit cancellation.

### 9.3. Main starting and deliberately closing the context

**`src/main/java/com/example/drain/GracefulDrainApplication.java`:**

~~~java
package com.example.drain;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class GracefulDrainApplication {

    public static void main(String[] args)
            throws InterruptedException {

        SpringApplication app =
                new SpringApplication(GracefulDrainApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        ConfigurableApplicationContext context = app.run(args);
        WorkCoordinator work = context.getBean(WorkCoordinator.class);

        boolean accepted = work.submitFirstTask();
        System.out.println("MAIN: first accepted=" + accepted);

        // Ensure main prints before worker starts logging.
        work.allowTaskToStart();
        work.awaitTaskStarted();

        // close() will invoke SmartLifecycle.stop(Runnable).
        Thread closer = new Thread(context::close, "context-closer");
        closer.start();

        // Wait for gate to actually close, do not sleep/guess timing.
        work.awaitAdmissionClosed();

        boolean lateAccepted = work.submitLateTask();
        System.out.println("MAIN: late accepted=" + lateAccepted);

        // Let previously accepted task finish.
        work.allowTaskToFinish();

        closer.join();
        System.out.println("MAIN: context closed");
    }

    @Bean
    WorkCoordinator workCoordinator() {
        return new WorkCoordinator();
    }
}
~~~

**Key details to understand:**

1. `WorkCoordinator` is a Spring bean created via `@Bean`, with phase `0` and `isAutoStartup()==true`, started during context refresh.
2. `SpringApplication.run(args)` finishes before main submits tasks. The demo is a CLI, not a server app holding requests open indefinitely.
3. Calling `context.close()` on the `context-closer` thread lets main keep observing the gate while shutdown is waiting for the task.
4. `awaitAdmissionClosed()` ensures the test only submits the late request **after** the gate switched to closed. Thus `submitLateTask()` returns `false`.
5. The initial task remains in the executor; after main calls `allowTaskToFinish()`, the worker prints completion, the executor terminates, and the lifecycle callback runs.
6. `closer.join()` ensures main only prints "context closed" once the thread running `context.close()` finishes.

**Note:** In a real JVM, the framework, signal handlers, timeouts, and thread scheduling may emit other logs. The example only asserts the ordering of **lines printed by the two demo classes** on a normal run, not the ordering of all Spring/Gradle log lines.

### 9.4. Run and expected output

From the `graceful-drain-demo` directory:

~~~bash
gradle bootRun
~~~

If using a Gradle Wrapper, run `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` on Windows; the sample project does not generate a wrapper.

Lines explicitly printed by **the demo's code**, barring unexpected timeouts or interruptions:

~~~text
LIFECYCLE: started
MAIN: first accepted=true
TASK: running
SHUTDOWN: admission closed
MAIN: late accepted=false
TASK: completed
SHUTDOWN: drained
MAIN: context closed
~~~

Why the order is deterministic:

- `MAIN: first accepted=true` prints before main opens `taskStartPermit`.
- `TASK: running` prints before `taskStarted` counts down, and main only proceeds afterward.
- `SHUTDOWN: admission closed` prints before `admissionClosed` counts down.
- `MAIN: late accepted=false` prints after the gate closes and before main opens `taskFinishPermit`.
- `TASK: completed` appears before the worker thread exits; `awaitTermination` returns `true` only after the executor fully terminates.
- `SHUTDOWN: drained` appears before the callback and before `context.close()` returns.

If the program misses this output due to a timeout, **that is an error path to investigate**, not an alternate valid ordering of the latch-controlled success path.

### 9.5. Three useful experiments

**Experiment A — Omit closing the admission gate.** If only `executor.shutdown()` runs while intake has no gate or rejection handling, clients/producers may assume a job was accepted even though the executor rejected it. Run this experiment only in a sandbox project, never for production job intake.

**Experiment B — Never open `taskFinishPermit`.** The worker keeps waiting; after 15 seconds `awaitTermination` returns `false`, and the code requests an interrupt. In this case, logs must not be equated with business completion. You may see `TASK: interrupted` instead of `TASK: completed`.

**Experiment C — Replace `shutdown()` with `shutdownNow()` right when closing the gate.** If a task is running, it may be interrupted before finishing; if tasks sit in the queue, `shutdownNow()` can return unexecuted queued tasks. This shows why forced shutdown should only be an escalation path.

## 10. Why not use @PreDestroy alone for everything?

`@PreDestroy` typically runs during **bean destruction**. It makes sense for closing a resource no longer in use, but in systems with multiple producers/consumers, you usually need to **stop intake first** before destroying resources.

Dangerous example:

~~~java
@PreDestroy
public void close() {
    executor.shutdownNow();
    databaseClient.close();
}
~~~

This is an **anti-pattern**, not code to add to the example. It:

- Interrupts tasks without draining.
- May close the database client while a task is still committing.
- Specifies no deadline, queue policy, or incomplete-job state.
- Does not ensure producers stopped submitting before the executor closed.

You can use `@PreDestroy` after `SmartLifecycle` components have stopped in order, or have a resource-owning bean's destroy method wait until all tasks using it have finished.

### @DependsOn and resource ownership

In a multi-bean architecture, if component A uses component B, Spring learns the dependency via constructor injection or `@DependsOn`. This guides bean creation/destruction order. Yet it **does not automatically replace** designing a deadline-bounded drain protocol for jobs active outside bean lifecycles.

If a worker thread uses `DataSource`, ensure the DataSource stays alive until the worker finishes; when using a Spring-managed executor, understand the executor's stop/destruction phase relative to database/client beans.

## 11. In-flight HTTP requests and background jobs: two different deadlines

Suppose a request:

~~~text
T=0s   HTTP POST /reports
T=0.1s server submits report job to executor
T=0.2s HTTP returns 202 Accepted
T=5s   shutdown begins
T=12s  job finally finishes writing result
~~~

When graceful web server shutdown runs at `T=5s`, the HTTP request already finished at `T=0.2s`, so the server has no corresponding **in-flight HTTP request** left to wait for. Yet the background task keeps running for many more seconds.

Thus configuring:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

**does not automatically guarantee** a job submitted to a custom `ExecutorService` runs to completion. You need:

- An admission gate on the endpoint/publisher.
- An executor drain policy.
- Durable job state storage if needed.
- Readiness/health/telemetry for shutdown progress.
- Deadlines aligned with container/orchestrator budgets.

### For HTTP requests not decoupled into background jobs

If a handler holds the request open and processes synchronously for 8 seconds, graceful web shutdown can let that request finish within the grace phase. However, if the handler uses streaming, WebFlux, or long-lived async responses, understand the actual completion contracts of your server and app. Never use `Thread.sleep` in demos as a stand-in for all request types.

## 12. Message consumers, acks, and redelivery

For Kafka, RabbitMQ, JMS, or custom polling sources, "stop accepting new work" translates into each library's mechanism:

- Stop polling/consuming or pause listeners/containers via supported APIs.
- Wait for or checkpoint **already-received** in-flight messages.
- Ack/commit offsets only once results reach durable conditions.
- If the deadline expires, leave unacked messages for redelivery or route per retry/DLQ policy.
- Ensure consumers never ack messages too early and lose replayability.

Never write a generic `consumer.stop()` and claim it shares identical semantics across every broker. Depending on the client, stop may halt polling, cancel tasks, close connections, or await current processing — read the exact API/version.

### At-least-once and idempotency

In typical queue systems, this scenario can occur:

~~~text
worker completes side effect
    |
    +-- process is killed before ack/commit
    |
broker redelivers message to another instance
    |
    +-- risk of executing side effect a second time
~~~

Thus "graceful shutdown" can **reduce** interrupted tasks yet **cannot eliminate** duplicates. You need idempotency keys, unique constraints, transactions/outboxes, or appropriate deduplication mechanisms.

Never use an in-JVM `static Set<String> completedJobs` as a cluster-wide deduplication guarantee; this state vanishes on process restart and is not shared across replicas.

## 13. Schedulers and @Async: avoid starting new jobs during shutdown

A `@Scheduled` method can keep firing while the application context has not finished closing. During shutdown, ensure the scheduler does not create additional work waiting on a draining executor.

Strategies:

1. Stop or pause the scheduler via supported APIs before draining workers.
2. Place an admission gate where the scheduler submits tasks so late callbacks are rejected.
3. Ensure rejections are handled (logged, retried, checkpointed) instead of losing tasks.
4. For distributed scheduling, enforce leader/lock/next-run policies so new instances do not double-run.
5. For periodic tasks, distinguish "stop creating new runs" from "stop currently running work".

With `@Async`, target methods are normally submitted to a `TaskExecutor`. Executor configuration can change when it rejects or waits for tasks. With `@Async void`, exceptions in background jobs do not propagate to callers; configure exception handlers, logging, and telemetry.

**Do not rely blindly on `@Async` proxies:** self-invocation inside the same class can bypass the proxy, running synchronously unexpectedly. This impacts how you determine "which tasks are running on the executor" during shutdown.

## 14. Budgeting shutdown time

Budget shutdown time at the deployment level, not only inside Java:

~~~text
t0: decide to remove instance
    |
    +-- update readiness / drain load balancer
    |       (propagation delay exists)
    |
    +-- preStop / SIGTERM
    |       (mechanism depends on orchestration)
    |
    +-- Spring context close
    |       +-- stop HTTP ingress
    |       +-- stop job admission
    |       +-- drain worker/broker tasks
    |       +-- close connections / database / clients
    |
    +-- JVM exit before hard deadline
            |
            v
        if exceeded: may receive SIGKILL / forced termination
~~~

These milestones are a **logical model**; exact preStop/SIGTERM ordering and readiness propagation belong to your deployment platform. Never assume Kubernetes guarantees a pod vanishes instantaneously from every load balancer before sending SIGTERM.

### Three easily confused timers

| Timeout | Scope | Example |
| --- | --- | --- |
| `spring.lifecycle.timeout-per-shutdown-phase` | Each phase group of Spring's lifecycle processor | `20s` |
| `ThreadPoolTaskExecutor.setAwaitTerminationSeconds` | Executor destruction/await step | `20` |
| Container `terminationGracePeriodSeconds` | Pod/container-level hard-stop budget | Must cover preStop + close + buffer |

Timeouts **do not necessarily run purely sequentially** and do not guarantee an exact sum. Even so, setting every timer right up against the hard-stop limit can leave zero time to flush logs, close resources, and run shutdown hooks.

**Rule-of-thumb example:** If work usually takes 10 seconds and needs 5 seconds to flush state/acks, total grace budget must also include propagation and buffer. Never rigidly claim one specific configuration fits every system.

### SIGTERM and SIGKILL

- **SIGTERM** typically gives the app/JVM a chance to run shutdown hooks, close the Spring context, and release resources.
- **SIGKILL** prevents the JVM from running Java shutdown hooks, `@PreDestroy`, or `SmartLifecycle.stop`.
- Hardware failure, power loss, OOM, or container hard kills likewise cannot guarantee graceful callbacks.
- Some IDEs/task runners stop immediately without sending standard signals; never use an IDE's Stop button alone to evaluate production shutdown behavior.

Therefore every critical job needs recovery mechanisms **even when graceful shutdown does not happen**.

## 15. Cases requiring explicit business policies

### 15.1. Short, idempotent jobs with deadlines

Good candidates for draining: stop accepting new jobs, let running/queued jobs finish within budget, and log outcomes. If a job fails to finish, persist state and retry.

### 15.2. Multi-hour jobs

Do not hold a pod in terminating state for hours just waiting on a job. Instead consider checkpoints, durable queues, dedicated workers, leases/heartbeats, or resume mechanisms so another instance can continue.

### 15.3. Tasks holding transactions

If a task is inside a DB transaction, interrupting mid-flight may trigger a rollback, though exact behavior depends on driver, framework, and transaction boundaries. Never assume `shutdownNow()` rolls back all external non-DB side effects.

### 15.4. Tasks executing payments or sending emails

Jobs with external side effects must carry idempotency keys or transaction trails; blindly retrying after a timeout can double-charge or double-email.

### 15.5. Streaming / long polling

A streaming request can stay open indefinitely. Decide whether to allow natural completion, cut streams with a resume protocol, or trigger graceful reconnects. Set deadlines and document clearly for clients.

### 15.6. Multi-replica deployment

During rolling deployments, new instances can accept work while old instances are draining. Never use a local boolean to guarantee only one worker owns a job system-wide. Use queue leases/assignments, partition rebalancing, or appropriate distributed locks.

## 16. Recommended metrics and logs

A system can log milestones such as:

~~~text
shutdown_requested
admission_closed
inflight_before_drain=<N>
queued_before_drain=<N>
drain_completed=<N>
drain_failed=<N>
drain_timeout=<true|false>
resources_closed
context_closed
~~~

This is a **structured log example**, not actual output from section 9's project. Never print sensitive payload data into logs.

Useful metrics:

- `jobs.accepted.total`, `jobs.rejected.total`.
- `jobs.running`, `jobs.queued`, `jobs.inflight`.
- `jobs.completed.total`, `jobs.failed.total`, `jobs.cancelled.total`.
- `shutdown.drain.duration`, `shutdown.timeout.total`.
- `executor.active.count`, `executor.queue.size`, `executor.completed.task.count` when supported by the executor.
- Time from SIGTERM until new traffic stops arriving; time from intake closed until last job completes.

You do not need to expose every metric for every service; pick metrics answering: "Was any work accepted after shutdown?", "How many jobs remain unfinished?", "Were any jobs lost/duplicated?", and "Did we exceed the grace period?".

## 17. Testing shutdown without relying on Thread.sleep

A flaky test pattern:

~~~java
Thread.sleep(1000);
context.close();
assertEquals(0, activeTasks);
~~~

This is a **non-recommended illustration**; task ordering depends on scheduling and machine speed. `sleep` only adds delay and **does not prove** tasks reached expected milestones.

Instead use:

- `CountDownLatch` to synchronize "task started", "shutdown closed the gate", and "allow task to finish".
- `Future` or `CompletableFuture` to observe task outcomes.
- `awaitTermination` to prove the executor terminated.
- Synchronized in-flight counters and asserting `accepted == completed + failed + cancelled + pending` per business model.
- Timeouts on waits in tests to avoid hanging CI pipelines indefinitely.
- Testing both normal paths and deadline paths, not only the happy path.

### Invariants to assert

**On the normal stop path:**

1. Tasks accepted before gate close still get to finish.
2. Tasks arriving after gate close are always rejected.
3. Context does not report close finished before the drain callback runs.
4. Executor terminates before dependent resources are closed.
5. No "accepted" job vanishes without state or a recovery plan.

**On the timeout/interrupt path:**

1. Clear logs/metrics and failure reasons exist.
2. Never report "drained all work" when tasks did not finish.
3. Retry/redelivery/checkpoint paths exist if work must be durable.
4. Application timeouts are smaller than the hard-kill budget after subtracting buffers.
5. Tasks ignoring interrupts are handled as a safety boundary rather than assuming `shutdownNow()` magically stops them.

## 18. Common mistakes and fixes

**1. Calling only executor.shutdown() and treating it as done.** Wrong. `shutdown()` does not wait for tasks to finish; use `awaitTermination` or proper lifecycle coordination.

**2. Calling awaitTermination without a shutdown signal.** Does not actively stop the executor; stop intake first and then call shutdown.

**3. Using shutdownNow() as the standard shutdown path.** Can interrupt running tasks and drop queued tasks, leaving partial work or lost jobs.

**4. Failing to synchronize check-then-submit.** A boolean alone cannot make gate-check and enqueue atomic; use a monitor/lock or linearizing mechanism plus rejection handling.

**5. Closing the executor before stopping producers.** Producers may keep submitting and hit unhandled rejections. Stop work sources first.

**6. Stopping the HTTP server while forgetting queue consumers.** Graceful web shutdown does not automatically stop message listeners, schedulers, or custom background executors.

**7. Thinking HTTP 202 Accepted guarantees the background job finished.** 202 only indicates the server accepted the request per protocol/application; durable handoff and job tracking are needed for guarantees.

**8. Waiting for running tasks while forgetting queued tasks.** Queues may still hold backlogs; define whether to drain the full queue or move/retry unstarted tasks.

**9. Closing DataSource before jobs commit.** Workers may still need the DB; design lifecycle/dependencies so resources stay alive during draining.

**10. Calling the SmartLifecycle callback right after submitting async shutdown.** Wrong if the component has not actually stopped; the callback signals that stopping completed.

**11. Forgetting to invoke the callback when stop succeeds.** LifecycleProcessor may wait until timeout because it does not know the component stopped.

**12. Using @PreDestroy to kill threads immediately.** Destroy callbacks do not replace an ordered admission/drain protocol.

**13. Believing same-phase lifecycle beans have a guaranteed strict order.** No guarantee exists for independent peers; use distinct phases or `@DependsOn`.

**14. Assuming Spring Boot 3.3 enables graceful HTTP shutdown by default because newer versions do.** Do not infer old dependency behavior from newer docs; configure `server.shutdown=graceful` explicitly in 3.3.

**15. Treating timeout-per-shutdown-phase and awaitTerminationSeconds as the same timer.** Both apply at different steps; also factor in container budgets.

**16. Setting awaitTerminationSeconds without closing admission.** Awaiting termination does not stop publishers from submitting late jobs early on.

**17. Waiting indefinitely to "never lose a job".** One hung task can block deployment forever; enforce deadlines, recovery plans, and forced-stop policies.

**18. Thinking Thread.interrupt is a guaranteed kill switch.** Interruption is cooperative; code can ignore it or block on uninterruptible I/O.

**19. Mishandling InterruptedException.** Swallowing interruption makes shutdown uncontrollable; restore interrupt status when appropriate and perform cleanup/escalation.

**20. Acking messages before side effects persist durably.** Data can be lost if the process dies between ack and commit. Design ack/transaction/retry per broker.

**21. Missing idempotency on redelivery.** Jobs can execute twice when a process is killed after side effects but before ack.

**22. Running multiple replicas while relying on in-memory flags.** Admission flags apply per instance, not replacing distributed ownership or queue leases.

**23. Using fixed Thread.sleep in integration tests.** Flaky and fails to prove tested relationships; use latches/barriers/futures.

**24. Enabling every executor "wait for tasks" flag regardless of version.** In Spring Framework 6.1, executor flags interact across early shutdown, coordinated lifecycle stop, and destruction phase; test against exact dependency versions.

**25. Logging "graceful shutdown success" despite exceeding the deadline.** Distinguish executor terminated, task completed, business state committed, and message acked; never conflate signals.

## 19. Practice exercises

1. Why must admission close **before** waiting for running tasks? What happens if producers remain allowed to submit?
2. Compare `shutdown()` and `shutdownNow()` on an executor with one running task and two queued tasks.
3. Why can `awaitTermination(10, SECONDS)` return `false` even after you called `shutdown()`?
4. For an endpoint returning 202 and spawning a background job, why is `server.shutdown=graceful` **not enough** to guarantee job completion?
5. Run section 9's project and explain each output line. How did latches eliminate log races?
6. Try submitting a new task **before** `admissionClosed` is signaled. Can it be accepted? Why is that the expected outcome?
7. Why does `if (accepting.get()) executor.execute(task)` still race even when `accepting` is an `AtomicBoolean`?
8. Remove `work.allowTaskToFinish()` in the demo. Once the deadline passes, what happens? Did the task finish in business terms?
9. Replace `shutdown()` with `shutdownNow()` in the demo and observe the worker's `InterruptedException` branch.
10. Write an `inFlight` counter tracking accepted-but-unfinished tasks. How must you update the counter on rejections/exceptions?
11. Switch from a manual `ExecutorService` to `ThreadPoolTaskExecutor`; enable `setWaitForTasksToCompleteOnShutdown(true)` and `setAwaitTerminationSeconds(20)`. Why is an admission gate still necessary?
12. In Spring Framework 6.1, why shouldn't you blindly enable both `strictEarlyShutdown` and `waitForTasksToCompleteOnShutdown` and assume every task is handled "strictly gracefully"?
13. Create a `SmartLifecycle` producer and a `SmartLifecycle` worker. Choose phases/depends-on so the producer stops before the worker.
14. A worker needs a database connection to commit. How do you ensure the DB client bean stays alive while draining?
15. Use `ContextClosedEvent` to close admission at the start of closing. Why is this only one piece of the full shutdown protocol?
16. A consumer acks a message **before** finishing processing; if SIGKILL strikes, what can happen?
17. If side effects succeeded yet ack did not, the broker redelivers. How would you apply idempotency keys/unique constraints/outboxes?
18. When a pod has `terminationGracePeriodSeconds=30` and preStop takes 10 seconds, why shouldn't you configure a 30-second drain wait with zero buffer?
19. A task ignores interrupts because network I/O is stuck. Should you claim `shutdownNow()` stopped it? What client timeouts and cancellation policies are needed?
20. Write an integration test with `CountDownLatch` proving tasks accepted before close finish while tasks submitted after gate close are rejected.
21. Add metrics for `shutdown.drain.duration` and jobs rejected while terminating; what signs show the grace budget is insufficient?
22. For multi-hour jobs, why are checkpoints and resume usually better than waiting for the entire job inside one pod?
23. Explain the differences between executor terminated, job callback returned, database commit succeeded, and message broker ack succeeded.
24. In a WebFlux app with streaming responses, how would you decide when to close streams and provide resume mechanics?
25. If an IDE does not send a stop signal equivalent to SIGTERM, how can you test graceful shutdown closer to real deployment conditions?

## Key takeaways

- **Core rule:** stop accepting new work → let accepted tasks finish within deadline → clean up resources last.
- `ExecutorService.shutdown()` rejects new tasks yet **does not wait** for old tasks to finish; `awaitTermination(...)` is the timeout-bounded waiting step.
- `shutdownNow()` is the forced stop/cancellation branch, guaranteeing neither successful interruption nor committed work.
- Admission gates must prevent races between status checks and job submission, while also handling executor rejections.
- `SmartLifecycle.stop(Runnable)` coordinates lifecycle; invoke the callback only after the component truly stopped per contract.
- In Spring Boot **3.3**, configure `server.shutdown=graceful` for HTTP graceful shutdown and `spring.lifecycle.timeout-per-shutdown-phase` for per-phase waits; this **does not automatically drain custom executors or consumers**.
- With `ThreadPoolTaskExecutor`, `setWaitForTasksToCompleteOnShutdown(true)` and `setAwaitTerminationSeconds(...)` help await queued/running jobs during destruction, yet do not replace stopping producers.
- Graceful shutdown **does not replace** durable queues, checkpoints, retries, idempotency, transactions, and proper ack/commit ordering.
- No Java callback is guaranteed to run when a process receives SIGKILL or the host dies; design recovery for ungraceful shutdowns.
- Test shutdown with latches/futures and mandatory invariants, avoiding `Thread.sleep` and drawing conclusions from random logs.

### References

- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — Application Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework 6.1 — `SmartLifecycle`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `DefaultLifecycleProcessor`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Spring Framework 6.1 — `ThreadPoolTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework 6.1 — `ExecutorConfigurationSupport`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html
- Java SE 17 — `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 — `CountDownLatch`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
