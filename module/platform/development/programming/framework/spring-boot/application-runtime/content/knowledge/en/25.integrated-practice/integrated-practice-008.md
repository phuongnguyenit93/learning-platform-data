# Simulating an In-Flight Job and Performing Controlled Shutdown in Spring Boot

## 1. Objectives and What to Observe

A Spring Boot application may be processing messages, running a batch job, generating reports, calling external services, or serving HTTP requests when it receives a stop signal. Merely calling `ExecutorService.shutdownNow()` or `System.exit(0)` immediately can interrupt active work, lose results, or fail to commit/acknowledge in time. Conversely, continuing to accept new work during shutdown can prevent the application from ever finishing shutdown.

This integrated practice lab simulates **a task that has started but not yet finished**, then executes a **controlled/graceful shutdown** in a verifiable order:

1. Spring Boot initializes a `SmartLifecycle` bean with a managed worker thread.
2. The worker accepts **one job** and clearly signals the job is running.
3. The job intentionally pauses at a `CountDownLatch` to simulate long-running work.
4. Another thread invokes `ApplicationContext.close()`.
5. The context publishes `ContextClosedEvent`, then asks the worker to stop via `stop(Runnable)`.
6. The worker **stops accepting new work** yet **does not immediately abort** the in-flight job.
7. An attempt to submit a new job is rejected; the existing job remains in-flight.
8. The coordinating thread releases the latch so the existing job finishes.
9. The executor terminates, and the `SmartLifecycle.stop(Runnable)` callback is invoked after draining completes.
10. Spring then finishes destruction callbacks and closes the `ApplicationContext`.

**Success criteria:** evidence that no new work is accepted after the shutdown request, prior work completes before the stop callback, the bean is destroyed after stop, and `context.close()` returns only after the system has stopped per contract.

The example uses **Java 17+**, **Spring Boot 3.5.16**, Maven, `ExecutorService`, and `CountDownLatch`. No database, Kafka, HTTP server, artificial sleep, or external resources are needed to run.

> This is a controlled lifecycle simulation, not an exactly-once guarantee across distributed systems. With real message brokers, transactions, or external services, dedicated timeouts, idempotency, acknowledgement, and recovery policies are still required.

## 2. What Is Graceful Shutdown?

A controlled shutdown is not merely "closing resources quickly". It is a sequence of states:

~~~text
RUNNING
   |
   | Shutdown requested
   v
STOPPING / DRAINING
   |
   +-- Reject new jobs
   +-- Do not spawn additional long-lived work
   +-- Wait for in-flight jobs to finish within deadline
   +-- Commit/ack/flush per business contract
   +-- Close bean-owned executor/connection/subscription
   |
   v
STOPPED
   |
   +-- Send SmartLifecycle stop callback
   +-- Spring proceeds to close remaining phases
   +-- Run @PreDestroy / destroy callbacks
   |
   v
CONTEXT CLOSED
~~~

Three concepts that must be distinguished:

| Concept | Meaning | Example |
| --- | --- | --- |
| **Stop accepting** | Accept no new work | Consumer stops polling; scheduler submits no new tasks |
| **Drain in-flight** | Let accepted work finish or hit timeout policy | Await task, ack message after commit |
| **Release resources** | Close resources actually owned by the component | Shut down executor, close client/pool, unsubscribe |

If you only **stop accepting** without waiting to drain, jobs can be abandoned. If you only drain while still accepting new jobs, the in-flight list can grow unboundedly. If you close connection pools before jobs finish, still-running jobs can fail mid-way.

### Graceful vs. Forced Shutdown

- **Graceful:** prioritizes finishing already-accepted work within the allowed time budget, avoids accepting new work, then closes resources in order.
- **Forced:** after the deadline, uses interrupt/cancellation/kill or stops accepting results. Incomplete work may need retrying on another instance.
- **Crash/SIGKILL:** Spring lifecycle callbacks may not run; external recovery is required.

A production solution must have **deadlines and an overdue-handling policy**, never waiting indefinitely just because it is labeled graceful.

## 3. Why Choose `SmartLifecycle` Instead of Only `@PreDestroy`?

Spring Framework provides `Lifecycle` and `SmartLifecycle` to coordinate starting/stopping beans with background activity. `SmartLifecycle` provides:

~~~java
void start();
void stop();
void stop(Runnable callback);
boolean isRunning();
boolean isAutoStartup();
int getPhase();
~~~

These are **core method signatures extracted for study**, not an interface you rewrite yourself. Use `org.springframework.context.SmartLifecycle` from Spring Framework.

On the normal `ApplicationContext.close()` path:
- Spring publishes `ContextClosedEvent`.
- `LifecycleProcessor.onClose()` asks lifecycle beans to stop.
- For `SmartLifecycle`, the processor uses `stop(Runnable callback)` to learn when the component has truly stopped.
- Shutdown phases are coordinated with a wait timeout.
- Afterward, Spring invokes destruction callbacks such as `@PreDestroy` and `@Bean(destroyMethod=...)`.

**Core point:** `@PreDestroy` belongs to the **destruction** path, whereas `stop(Runnable)` serves **coordinated stopping**. If you must wait for running jobs to preserve ordering before other beans are destroyed, merely calling `executor.shutdown()` inside `@PreDestroy` is usually insufficient.

### Difference Between `stop()` and `stop(Runnable)`

`Lifecycle.stop()` is a synchronous stop form. `SmartLifecycle.stop(Runnable)` provides a completion callback so the lifecycle processor can coordinate **asynchronous shutdown**:

~~~text
stop(callback) called
   |
   +-- Mark no longer accepting new work
   +-- Ask executor to stop accepting tasks
   +-- DO NOT invoke callback while tasks are still running
   +-- Once executor has actually terminated:
          callback.run()
~~~

If `stop(Runnable)` simply calls `ExecutorService.shutdown()` and immediately calls `callback.run()`, the callback **reports completion too early**: `shutdown()` does not wait for running tasks.

Conversely, failing to call the callback when actually stopped causes Spring to wait until the shutdown phase timeout expires. Thus the callback is a critical part of the **lifecycle contract**, not a decorative log line.

## 4. Designing the State Machine for the Simulation

Use explicit states instead of scattered booleans:

~~~text
NEW
  |
  | start() (auto-start on ApplicationContext refresh)
  v
RUNNING
  |
  | stop(Runnable) / context.close()
  v
STOPPING
  | \
  |  +-- trySubmit() -> REJECTED
  |  +-- in-flight job still completes
  |  +-- callbacks retained to fire after completion
  |
  +-- awaitTermination success
  v
STOPPED

If executor does not terminate within deadline:
STOPPING -> FAILED_STOP / record timeout for investigation
~~~

### Invariants to Maintain

1. While `RUNNING`, the component is permitted to accept jobs.
2. From the moment it transitions to `STOPPING`, **every new submission must be rejected**.
3. State transitions and calling `ExecutorService.shutdown()` must be protected by the same monitor/lock as the submission path to prevent races.
4. `isRunning()` can remain true during `STOPPING` because the underlying resource has not finished yet; flip to false only when stopping completes.
5. Never invoke callbacks before the executor has terminated.
6. If multiple `stop(callback)` calls arrive during `STOPPING`, retain all callbacks; do not run shutdown a second time.
7. After `STOPPED`, repeated stop calls are no-ops, yet new callbacks are still completed.
8. Destruction callbacks can safely invoke the same stop path without double-closing.
9. If a timeout occurs, record the error and avoid claiming successful shutdown while resources are still running.
10. Do not rely on `Thread.sleep(...)` to enforce ordering between two threads; use synchronization primitives.

### Race Condition Without a Lock

~~~java
if (accepting) {
    executor.submit(job);
}
~~~

This is **pseudocode**, with `accepting`, `executor`, and `job` undefined. If thread A checks `accepting=true`, and thread B transitions to STOPPING and shuts down the executor, thread A can submit afterward and get `RejectedExecutionException`. That does not necessarily compromise safety if callers handle errors properly, yet it makes upholding a consistent "accept/reject" contract difficult.

In the demo, the same `monitor` guards **state + submission path + shutdown decision**, so a submission cannot slip in between stop updating state and closing the intake gate.

## 5. Why Use `CountDownLatch` Instead of `Thread.sleep`?

`Thread.sleep(1000)` only sleeps for a duration; it does not prove the worker **has started** before shutdown, and it can cause flakiness on slow CI machines.

We use three latches:

| Latch | Signaler | Waiter | What It Proves |
| --- | --- | --- | --- |
| `jobStarted` | Worker thread when processing begins | Main/test | The job has genuinely entered the in-flight region |
| `releaseJob` | Main/test when allowing completion | Worker thread | The job is intentionally held until measurements finish |
| `stopRequested` | `SmartLifecycle.stop(Runnable)` after halting intake | Main/test | The close path has reached the component's stop command |

Deterministic sequence:

~~~text
Main                Worker                   Close thread         Stop coordinator
 |                     |                          |                     |
 | submit job          |                          |                     |
 |-------------------->| jobStarted.countDown     |                     |
 | await jobStarted    | await releaseJob         |                     |
 |<--------------------|                          |                     |
 | request context.close()                        |                     |
 |----------------------------------------------->| ContextClosedEvent  |
 |                     |                          | stop(callback)      |
 |                     |                          | -> STOPPING         |
 | await stopRequested |                          | -> executor.shutdown|
 |<-----------------------------------------------|                     |
 | trySubmit -> false  |                          |                     |
 | releaseJob.countDown|                          |                     |
 |-------------------->| job finishes             |                     |
 |                     |-------------------------? | awaitTermination    |
 |                     |                          |                     |
 |                     |                          | callback invoked <--|
 |                     |                          | @PreDestroy         |
 |                     |                          | close() returns     |
 | join close thread  <--------------------------|                     |
~~~

The diagram illustrates synchronization; the `?` mark simply indicates the handoff point between the worker and coordinator. There is no requirement that the job and stop coordinator run on the same thread.

## 6. Complete Runnable Java 17+ Spring Boot Project

The lab creates a single Maven project containing:

- One non-web `@SpringBootApplication`.
- One singleton bean `ManagedWorker implements SmartLifecycle`.
- One single-threaded `ExecutorService` simulating a long task.
- One `ApplicationListener<ContextClosedEvent>` to observe the context closing milestone.
- One separate thread requesting `context.close()`.
- One completion coordinator awaiting executor termination before invoking stop callbacks.
- One `@PreDestroy` method acting as backup cleanup.
- One JUnit 5 test verifying no premature callbacks and no new jobs accepted during STOPPING.

The example **does not connect to a database, web server, or message broker**. Real latency scenarios and force-kills are discussed separately.

### 6.1. Directory Structure

~~~text
controlled-shutdown-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/shutdown/
    │   │   └── ControlledShutdownApplication.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/shutdown/
            └── ManagedWorkerTest.java
~~~

### 6.2. `pom.xml` File

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
    <artifactId>controlled-shutdown-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

`spring-boot-starter` is sufficient for a non-web application. `spring-boot-starter-test` supplies JUnit Jupiter for testing; it does not need to spin up a Spring test context because unit tests can instantiate `ManagedWorker` directly.

### 6.3. `application.properties` File

~~~properties
spring.application.name=controlled-shutdown-demo
spring.main.banner-mode=off

# Limit total time Spring waits for callbacks in each shutdown phase.
spring.lifecycle.timeout-per-shutdown-phase=25s
~~~

The 25-second value is solely for the practice lab. **Spring's timeout does not forcibly stop executors or tasks**: it only bounds how long the lifecycle processor waits for phase callbacks. The code includes a dedicated deadline for `ExecutorService.awaitTermination(...)`.

### 6.4. Complete Java File

Save as `src/main/java/com/example/shutdown/ControlledShutdownApplication.java`:

~~~java
package com.example.shutdown;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.annotation.PreDestroy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;

@SpringBootApplication
public class ControlledShutdownApplication {

    public static void main(String[] args) throws InterruptedException {
        SpringApplication application =
                new SpringApplication(ControlledShutdownApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = application.run(args);
        ManagedWorker worker = context.getBean(ManagedWorker.class);
        AtomicReference<Throwable> closeError = new AtomicReference<>();

        try {
            System.out.println("02_CONTEXT_READY");

            worker.submitOneJob();
            worker.awaitJobStarted();
            System.out.println("04_IN_FLIGHT=" + worker.inFlight());

            System.out.println("05_MAIN_REQUEST_CLOSE");
            Thread closer = new Thread(() -> {
                try {
                    context.close();
                    System.out.println("13_CONTEXT_CLOSE_RETURNED");
                } catch (Throwable error) {
                    closeError.set(error);
                }
            }, "context-close-thread");
            closer.start();

            worker.awaitStopRequested();
            System.out.println("08_LATE_SUBMISSION_ACCEPTED="
                    + worker.tryLateSubmission());

            System.out.println("09_MAIN_RELEASE_JOB");
            worker.releaseJob();

            closer.join(20_000);
            if (closer.isAlive()) {
                throw new IllegalStateException("context close timed out");
            }
            if (closeError.get() != null) {
                throw new IllegalStateException(
                        "context close failed", closeError.get());
            }

            System.out.println("14_FINAL_RUNNING=" + worker.isRunning());
        } finally {
            // Ensure job is never held forever if an assertion/await fails.
            worker.releaseJob();
            if (context.isActive()) {
                context.close();
            }
        }
    }

    @Bean
    ManagedWorker managedWorker() {
        return new ManagedWorker();
    }

    @Bean
    ApplicationListener<ContextClosedEvent> closeEventListener() {
        return event -> System.out.println("06_CONTEXT_CLOSED_EVENT");
    }

    public static final class ManagedWorker implements SmartLifecycle {

        private enum State {
            NEW, RUNNING, STOPPING, STOPPED, FAILED
        }

        private final Object monitor = new Object();
        private final CountDownLatch jobStarted = new CountDownLatch(1);
        private final CountDownLatch releaseJob = new CountDownLatch(1);
        private final CountDownLatch stopRequested = new CountDownLatch(1);
        private final AtomicInteger inFlight = new AtomicInteger();
        private final List<Runnable> callbacks = new ArrayList<>();

        private State state = State.NEW;
        private ExecutorService executor;

        @Override
        public void start() {
            synchronized (monitor) {
                if (state == State.RUNNING) {
                    return;
                }
                if (state != State.NEW) {
                    throw new IllegalStateException(
                            "Restart not supported in this demo: " + state);
                }

                executor = Executors.newSingleThreadExecutor(task -> {
                    Thread thread = new Thread(task, "managed-job-thread");
                    thread.setDaemon(false);
                    return thread;
                });

                state = State.RUNNING;
                System.out.println("01_LIFECYCLE_STARTED");
            }
        }

        public void submitOneJob() {
            synchronized (monitor) {
                if (state != State.RUNNING) {
                    throw new IllegalStateException(
                            "Not accepting jobs: " + state);
                }

                inFlight.incrementAndGet();
                try {
                    executor.execute(() -> {
                        System.out.println("03_JOB_STARTED");
                        jobStarted.countDown();

                        try {
                            if (!releaseJob.await(15, TimeUnit.SECONDS)) {
                                System.err.println(
                                        "JOB_DEADLINE_EXPIRED");
                            }
                        } catch (InterruptedException exception) {
                            Thread.currentThread().interrupt();
                            System.err.println("JOB_INTERRUPTED");
                        } finally {
                            inFlight.decrementAndGet();
                            System.out.println("10_JOB_FINISHED");
                        }
                    });
                } catch (RuntimeException error) {
                    inFlight.decrementAndGet();
                    throw error;
                }
            }
        }

        public void awaitJobStarted() throws InterruptedException {
            if (!jobStarted.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("job did not start");
            }
        }

        public void awaitStopRequested() throws InterruptedException {
            if (!stopRequested.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "lifecycle stop was not requested");
            }
        }

        public void releaseJob() {
            releaseJob.countDown();
        }

        public int inFlight() {
            return inFlight.get();
        }

        public boolean tryLateSubmission() {
            synchronized (monitor) {
                if (state != State.RUNNING) {
                    return false;
                }
                executor.execute(() ->
                        System.out.println("UNEXPECTED_LATE_JOB_EXECUTED"));
                return true;
            }
        }

        @Override
        public void stop(Runnable callback) {
            Objects.requireNonNull(callback, "callback");
            ExecutorService executorToWait = null;
            boolean completeImmediately = false;

            synchronized (monitor) {
                if (state == State.NEW) {
                    state = State.STOPPED;
                    completeImmediately = true;
                } else if (state == State.STOPPED) {
                    completeImmediately = true;
                } else if (state == State.STOPPING) {
                    // Coalesce all callbacks into the same shutdown run.
                    callbacks.add(callback);
                } else if (state == State.FAILED) {
                    throw new IllegalStateException(
                            "Previous shutdown failed");
                } else {
                    // RUNNING: lock the intake gate before shutdown.
                    state = State.STOPPING;
                    callbacks.add(callback);
                    executor.shutdown();
                    System.out.println("07_STOP_REQUESTED");
                    stopRequested.countDown();
                    executorToWait = executor;
                }
            }

            if (completeImmediately) {
                callback.run();
            }
            if (executorToWait != null) {
                awaitTerminationInBackground(executorToWait);
            }
        }

        private void awaitTerminationInBackground(ExecutorService target) {
            Thread coordinator = new Thread(() -> {
                try {
                    boolean terminated =
                            target.awaitTermination(15, TimeUnit.SECONDS);
                    if (!terminated) {
                        System.err.println("SHUTDOWN_FORCE_INTERRUPT");
                        target.shutdownNow();
                        terminated = target.awaitTermination(
                                3, TimeUnit.SECONDS);
                    }

                    if (!terminated) {
                        failStop("executor did not terminate");
                        return;
                    }
                    completeStop();
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    target.shutdownNow();
                    failStop("stop coordinator interrupted");
                }
            }, "stop-coordinator");

            coordinator.setDaemon(true);
            coordinator.start();
        }

        private void completeStop() {
            List<Runnable> ready;
            synchronized (monitor) {
                state = State.STOPPED;
                ready = new ArrayList<>(callbacks);
                callbacks.clear();
                System.out.println("11_STOP_COMPLETED");
            }

            // Callbacks run outside monitor to avoid reentrant deadlock.
            for (Runnable callback : ready) {
                try {
                    callback.run();
                } catch (RuntimeException error) {
                    System.err.println(
                            "STOP_CALLBACK_FAILED="
                                    + error.getClass().getSimpleName());
                }
            }
        }

        private void failStop(String message) {
            synchronized (monitor) {
                state = State.FAILED;
                System.err.println("SHUTDOWN_FAILED=" + message);
            }
            // Do not fire completion callbacks if worker has not terminated.
            // LifecycleProcessor will use the phase timeout.
        }

        @Override
        public void stop() {
            CountDownLatch done = new CountDownLatch(1);
            stop(done::countDown);
            try {
                if (!done.await(20, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("stop() timed out");
                }
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Interrupted while waiting to stop", exception);
            }
        }

        @Override
        public boolean isRunning() {
            synchronized (monitor) {
                return state == State.RUNNING
                        || state == State.STOPPING;
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

        @PreDestroy
        public void destroy() {
            // Backup cleanup: does not trigger a second shutdown
            // if SmartLifecycle already transitioned to STOPPED.
            stop();
            System.out.println("12_BEAN_DESTROYED");
        }
    }
}
~~~

This is the **complete runnable Java code** of the application. There is no mock `doWork()` method, no external service configuration required, and no `System.exit` call.

### 6.5. Explaining the Implementation's Safety Properties

**Guarding state and submission path with a single monitor.** `start`, `submitOneJob`, `tryLateSubmission`, `stop(Runnable)`, and `isRunning` all access state synchronously. Once `STOPPING` is recorded, `tryLateSubmission` must return false. `executor.shutdown()` resides inside the same synchronized block as the state transition, preventing a successful submission from slipping between the decision to close the gate and shutdown.

**Scoping the in-flight counter properly.** `inFlight.incrementAndGet()` occurs before `executor.execute(...)`; if submission throws, the counter rolls back. The task decrements the counter in `finally`, even if interrupted. Thus the counter reflects accepted tasks not yet finished, not merely surviving threads.

**Not blocking the lifecycle callback thread for long.** `stop(Runnable)` quickly updates state, calls executor shutdown, and spawns a coordinator thread. That thread awaits `awaitTermination` without holding `monitor` while waiting. With `DefaultLifecycleProcessor`, callbacks let Spring coordinate per phase instead of forcing synchronous I/O waiting directly on the stop caller thread.

**Rejecting new tasks before awaiting old tasks.** `executor.shutdown()` stops accepting tasks; meanwhile, the `state != RUNNING` guard returns false for late calls. No new task can accidentally prolong draining.

**Callbacks run only after termination.** Only `completeStop()` invokes callbacks, and this method is only called when `awaitTermination` succeeds. If stopping fails after the deadlines, the code transitions to `FAILED` and intentionally omits signaling "completed". Spring may hit the phase timeout; production requires clear escalation.

**Callbacks from repeated stop calls are retained.** While state is `STOPPING`, a second callback is appended to `callbacks` instead of shutting down the executor again. `completeStop` takes a snapshot, clears the list, and invokes each callback outside the monitor.

**Backup cleanup with `@PreDestroy`.** On the normal close path, SmartLifecycle callbacks complete before bean destruction. Calling `stop()` inside `destroy()` becomes a safe no-op and prints the marker. If stop errored/timed out, the fallback may fail; do not use that log line as a promise that all resources were freed along a failure path.

**No generation restarts in the demo.** `start()` only permits NEW → RUNNING, avoiding reusing exhausted CountDownLatches and a closed executor. If a real app needs `context.stop() → context.start()`, create a new generation, replace all latches/executors properly, and add tests. Never pretend demo code supports restarts when it is not designed for them.

### 6.6. Why Use a Daemon Thread for the Coordinator?

`stop-coordinator` is a short-lived thread waiting for completion and firing callbacks. It is marked daemon so it does not keep the JVM alive forever **solely due to a bug in the coordinator thread**. However, the task thread `managed-job-thread` is non-daemon and **must be shut down cleanly**. Making the coordinator daemon **does not replace** timeouts/cleanup and does not guarantee callbacks if the JVM is force-killed.

On the normal path, `main` awaits `context.close()` completion, giving the coordinator the opportunity to finish before the process exits.

### 6.7. Why Have Two Deadlines for the Executor?

In `awaitTerminationInBackground`:
1. Wait up to **15 seconds** for tasks to finish naturally.
2. Otherwise, call `shutdownNow()` to attempt interrupting running tasks.
3. Wait up to an additional **3 seconds**.
4. If the executor still has not terminated, log `SHUTDOWN_FAILED` and **do not fire fake completion callbacks**.

These numbers are merely demo choices; Spring's `spring.lifecycle.timeout-per-shutdown-phase=25s` is a **processor-level deadline**, which does not stop the executor itself. Production applications should set deadlines compatible with external process orchestrators and account for phase time budgets.

**Important:** `shutdownNow()` only attempts to interrupt tasks; if a task ignores interrupts or is stuck in uninterruptible I/O, termination is not guaranteed. You then need compensation/idempotent retries or controlled forced termination from the orchestrator.

## 7. Running the Application and Reading Output in Order

### 7.1. Compile, Test, and Run the JAR

Open a terminal in the directory containing `pom.xml`:

~~~bash
mvn test
mvn package
java -jar target/controlled-shutdown-demo-0.0.1-SNAPSHOT.jar
~~~

`mvn test` runs the JUnit suite described in the next section. `mvn package` creates the executable JAR. When running `java -jar`, the program creates a job, spawns a thread requesting context close, and exits. You do not need to press Ctrl+C mid-run because `main` coordinates via latches.

### 7.2. Markers from the Program Itself

**On a successful run**, ignoring Spring Boot framework logs and Maven logs, the markers printed by this Java source appear in order:

~~~text
01_LIFECYCLE_STARTED
02_CONTEXT_READY
03_JOB_STARTED
04_IN_FLIGHT=1
05_MAIN_REQUEST_CLOSE
06_CONTEXT_CLOSED_EVENT
07_STOP_REQUESTED
08_LATE_SUBMISSION_ACCEPTED=false
09_MAIN_RELEASE_JOB
10_JOB_FINISHED
11_STOP_COMPLETED
12_BEAN_DESTROYED
13_CONTEXT_CLOSE_RETURNED
14_FINAL_RUNNING=false
~~~

The markers above are **the expected outcome based on the demo's latch and callback order**, not a verbatim log captured from a live run at writing time. If a task times out, the coordinator is interrupted, or a dependency/framework errors, output can differ and the program must be investigated on its failure path.

### 7.3. Analyzing Each Marker

**01_LIFECYCLE_STARTED** — `DefaultLifecycleProcessor` auto-starts the `ManagedWorker` bean during refresh because `isAutoStartup() == true`. When `SpringApplication.run` returns, the worker is ready to accept tasks.

**02_CONTEXT_READY** — the main thread has received the context and bean, and has not yet requested stop.

**03_JOB_STARTED** — the task actually began executing on the executor and signaled `jobStarted.countDown()`. Main only proceeds once the latch confirms it.

**04_IN_FLIGHT=1** — the task is still waiting on `releaseJob`, so the counter is 1. Never confuse "submitted but not yet started" with "genuinely in-flight".

**05_MAIN_REQUEST_CLOSE** — main spawns `context-close-thread` and calls `context.close()`. Main does not block on that call itself because it still has to release the latch for the job to finish.

**06_CONTEXT_CLOSED_EVENT** — Spring publishes the event indicating context close has started. At this milestone, destruction callbacks have not necessarily run.

**07_STOP_REQUESTED** — `SmartLifecycle.stop(Runnable)` transitions state RUNNING → STOPPING, calls `executor.shutdown()`, and signals `stopRequested.countDown()`. The old job is still running.

**08_LATE_SUBMISSION_ACCEPTED=false** — main waits for `stopRequested` before attempting late submission, so the decision is deterministically governed by STOPPING state; no new job sneaks into the queue.

**09_MAIN_RELEASE_JOB** — main allows the existing task to finish via `releaseJob.countDown()`. Without this call, the task would have to wait for timeout or interrupt.

**10_JOB_FINISHED** — the task runs `finally`, decrements in-flight from 1 to 0, and releases the worker thread once the runnable returns.

**11_STOP_COMPLETED** — the stop coordinator observes `ExecutorService.awaitTermination(...)` returning true, transitions state to STOPPED, and only then fires callbacks to the lifecycle processor.

**12_BEAN_DESTROYED** — Spring continues the close path and calls `@PreDestroy` on the bean. Because stop already completed, fallback stop does not re-close the executor.

**13_CONTEXT_CLOSE_RETURNED** — the `context.close()` call inside the context-closing thread returns after normal lifecycle/destruction steps finish.

**14_FINAL_RUNNING=false** — main has joined the context-closing thread and sees the bean is no longer running. This is not a new business call on a destroyed bean; the example merely reads monitor-guarded state.

### 7.4. The Most Important Proof

It is not just seeing the program "stop", it is **the invariant order**:

~~~text
STOP_REQUESTED
    < SUBMIT_AFTER_STOP_REJECTED
    < JOB_RELEASED
    < JOB_FINISHED
    < STOP_COMPLETED
    < BEAN_DESTROYED
    < CONTEXT_CLOSE_RETURNED
~~~

Here `<` means **happens before**, not a Java operator. These relationships are guaranteed by latches, locks, executor termination, and callbacks in the demo. Without synchronization, merely looking at timestamps a few milliseconds apart is insufficient evidence.

**You cannot infer from `ContextClosedEvent` that workers have stopped.** In Spring Framework, the event is published before lifecycle stop and singleton destruction on a normal close path. Marker 06 arriving before 07 is the proof.

## 8. Automated Testing with JUnit 5

In addition to the main program, use **a pure unit test** for the worker to verify:
- The stop callback has not been invoked while a job is still held at the latch.
- New jobs are rejected when state is STOPPING.
- After releasing the latch, the callback is invoked and in-flight equals 0.
- Two asynchronous stop calls do not double-close and every callback is delivered.

There is no need to start a Spring TestContext in these unit tests because lifecycle methods are plain Java and can be called directly. This reduces test time and keeps assertions deterministic.

### 8.1. `ManagedWorkerTest.java` File

Save to `src/test/java/com/example/shutdown/ManagedWorkerTest.java`:

~~~java
package com.example.shutdown;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ManagedWorkerTest {

    @Test
    void stopWaitsForInFlightWorkAndRejectsNewWork()
            throws InterruptedException {
        var worker =
                new ControlledShutdownApplication.ManagedWorker();
        worker.start();

        try {
            worker.submitOneJob();
            worker.awaitJobStarted();

            CountDownLatch stopped = new CountDownLatch(1);
            worker.stop(stopped::countDown);
            worker.awaitStopRequested();

            assertFalse(worker.tryLateSubmission());
            assertEquals(1, worker.inFlight());
            assertTrue(worker.isRunning());

            // Do not use sleep: callback cannot complete
            // while the job is still blocked by the releaseJob latch.
            assertFalse(stopped.await(50, TimeUnit.MILLISECONDS));

            worker.releaseJob();
            assertTrue(stopped.await(10, TimeUnit.SECONDS));
            assertEquals(0, worker.inFlight());
            assertFalse(worker.isRunning());
        } finally {
            worker.releaseJob();
            worker.stop();
        }
    }

    @Test
    void repeatedStopRequestsCompleteBothCallbacks()
            throws InterruptedException {
        var worker =
                new ControlledShutdownApplication.ManagedWorker();
        worker.start();

        try {
            worker.submitOneJob();
            worker.awaitJobStarted();

            CountDownLatch callbacks = new CountDownLatch(2);
            worker.stop(callbacks::countDown);
            worker.stop(callbacks::countDown);

            assertFalse(worker.tryLateSubmission());
            assertEquals(1, worker.inFlight());

            worker.releaseJob();
            assertTrue(callbacks.await(10, TimeUnit.SECONDS));
            assertEquals(0, worker.inFlight());
            assertFalse(worker.isRunning());
        } finally {
            worker.releaseJob();
            worker.stop();
        }
    }
}
~~~

This is a **complete Java test file**, using JUnit Jupiter from pom.xml's `spring-boot-starter-test`. The checks do not rely on sleep durations to establish order. `await(..., TimeUnit.SECONDS)` bounds are only safety caps preventing test hangs on regressions.

### 8.2. Command to Run the Test

~~~bash
mvn -Dtest=ManagedWorkerTest test
~~~

Expectation in a clean project: **2 tests, 0 failures, 0 errors**. Maven/Surefire logs vary by environment; do not assert fixed full stdout with fixed timestamps.

### 8.3. Why Wasn't the Callback Fired Early?

In the first test, the worker is running a job and waiting on `releaseJob`. The test calls `worker.stop(stopped::countDown)` and checks:

~~~java
assertFalse(stopped.await(50, TimeUnit.MILLISECONDS));
~~~

If the callback had been invoked immediately after `executor.shutdown()`, the `stopped` latch would hit 0 and the assertion would fail. When `releaseJob` is released, the task finishes; the coordinator sees the executor terminated and fires the callback, so the subsequent assertion passes.

### 8.4. Why Is `try/finally` Necessary in the Test?

If an assertion fails, the test must still release the latch and call stop to avoid leaving a non-daemon worker thread alive inside the Maven test JVM. Without `finally`, the test might report a failure yet the Maven process would refuse to exit, causing CI timeouts.

That is itself a lesson on **resource ownership in lifecycle testing**: whoever creates a worker outside Spring TestContext must provide its own cleanup path.

## 9. Testing an Intentional Bug: Callback Invoked Too Early

Suppose we temporarily modify `stop(Runnable callback)` to the following idea:

~~~java
@Override
public void stop(Runnable callback) {
    executor.shutdown();
    callback.run(); // Wrong while tasks are still in-flight!
}
~~~

This is a **bug illustration snippet**, not a complete replacement since state/lock/callback queue are missing. In the simulation:
- Spring receives the signal that the phase has stopped.
- Yet the job is still waiting on the latch.
- Spring begins destroying other singletons while the job might still be using them.
- The "callback has not arrived while job is running" test fails.

**Lesson:** SmartLifecycle's callback does not mean "stop request has been sent"; it means "the component has finished stopping per contract".

## 10. Testing Another Bug: Not Blocking New Work

If you remove the guard in `tryLateSubmission()` and always submit:

~~~java
executor.execute(newJob);
~~~

This is **pseudocode** because `newJob` is undefined. Once the executor has received `shutdown()`, `execute` may throw `RejectedExecutionException`. In other designs, submissions could still slip between the state check and shutdown, accepting a new job after the system has already started stopping.

Good design should provide an explicit API such as:
- `boolean trySubmit(Job job)` returning false when not accepting.
- Or `submit(...)` throwing a dedicated exception recognizable as "service unavailable/stopping".
- If an HTTP endpoint, returning a contractual status (such as 503 when the instance is no longer accepting work).
- If a message consumer, pausing polling/receiving rather than accepting and dropping messages.

Never silently "accept" a job that will never be executed.

## 11. Testing the Timeout Case: Job Refuses to Complete

In the demo, we release `releaseJob` so the job ends quickly. If we **do not release the latch**, the task waits up to 15 seconds and exits on its own with marker `JOB_DEADLINE_EXPIRED`. The coordinator also waits up to 15 seconds for the executor, then tries `shutdownNow()` and waits 3 more seconds.

To test this in practice, modify test/harness code intentionally rather than merely deleting one line in main while forgetting the `finally` block also releases the latch. A safe variant is creating a dedicated test driving the worker with an overall test timeout.

### Possible Outcomes

| Job Behavior | Coordinator | Spring Lifecycle | What to Note |
| --- | --- | --- | --- |
| Completes before 15s | awaitTermination=true | Callback after completion | Graceful success |
| Not done after 15s, responds to interrupt | shutdownNow → terminated | Callback after termination | Forced cancellation; may need retry |
| Ignores interrupt after 3 more seconds | FAILED, no callback | Processor may wait up to phase timeout | Must not report "clean shutdown" |
| JVM receives SIGKILL | Coordinator/callback not guaranteed | Destruction not guaranteed | External recovery mandatory |

**Never emit the "STOP_COMPLETED" marker on a timeout path while the executor is still alive.** If the system failed to stop, report an incomplete state and let the operations layer decide escalation.

### Does Interrupt Guarantee Rollback?

No. `Thread.interrupt()` only sends a cooperative signal to a thread. Operations calling `wait`, `sleep`, or `CountDownLatch.await` typically throw `InterruptedException`, yet business code must handle it properly. A native call, deadlock, or library without cancellation support may fail to exit in time.

In real jobs:
- Check `Thread.currentThread().isInterrupted()` at appropriate points.
- Never swallow `InterruptedException` and keep looping forever.
- Preserve the interrupt flag when transitioning to cleanup.
- Require transaction rollback or acknowledgement policies when a step did not finish.
- Do not claim external side effects outside the JVM were rolled back merely because the thread stopped.

### Demo Limitation on the Error Path

The code chooses **not to invoke callbacks** if the worker has not terminated to avoid false success. That causes Spring to wait until the phase timeout. When the lifecycle processor proceeds to destroy beans, `@PreDestroy` may raise errors if the worker is still STOPPING/FAILED. This is a failure outcome requiring alerts and production handling, not proof that graceful shutdown succeeded.

A production implementation may choose a different protocol: cancellation tokens, phased stopping, circuit breakers, resource fencing, or pre-deadline escalation, while remaining transparent about unfinished jobs.

## 12. `SmartLifecycle` Phase: Ordering Between Worker and Dependencies

If a worker shares a client or connection pool:
- The worker must **stop accepting jobs and drain** while the client is still alive.
- After the worker stops, the client's owning bean may close.

`SmartLifecycle.getPhase()` coordinates across lifecycle beans:

~~~text
START: low phase -> high phase
STOP : high phase -> low phase
~~~

Example:

| Component | Phase | On Start | On Stop |
| --- | ---: | --- | --- |
| Shared infrastructure/client (also Lifecycle) | -100 | Earlier | Later |
| Worker/consumer | 100 | Later | Earlier |
| User-facing endpoint/consumer | 200 | Last | Earliest |

If the client is just a regular singleton with a destruction callback, Spring normally stops `SmartLifecycle` beans in `onClose()` before destroying singletons. Even so, ensure the worker callback arrives only after jobs no longer use the client.

Do not pick phases by guesswork. `depends-on` relationships and specific container conditions can affect order. Components with multiple dependencies should have an ownership/phase diagram and shutdown tests to avoid closing clients too early.

### `isRunning()` Must Accurately Reflect State

In the demo, `isRunning()` returns true for both RUNNING and STOPPING. This is intentional: STOPPING still has active resources or in-flight jobs, so the bean **has not actually finished stopping**. Only after the coordinator confirms termination does it return false.

Do not report false right after `executor.shutdown()` if stopping is incomplete; frameworks or tests could assume resources are closed. Conversely, if a bean stopped successfully yet still reports true, the lifecycle processor may misbehave on repeated stops.

## 13. `context.stop()`, `context.close()`, and `System.exit()` in the Practice Lab

Three distinct operations:

| API | Action | Suitable for This Simulation? |
| --- | --- | --- |
| `worker.stop()` | Stops just the worker synchronously per contract | Yes, when stopping only the worker |
| `worker.stop(callback)` | Stops the worker and reports completion | Yes; used by lifecycle processor on close |
| `context.stop()` | Stops `Lifecycle` beans while keeping context and singletons | Usable if pause/restart is needed, though demo does not support generation restart |
| `context.close()` | Stops lifecycle, destroys managed singletons, closes context | **Yes**, the demo's choice |
| `SpringApplication.exit(context)` | Closes context and computes process exit code | Usable for CLIs needing exit codes |
| `System.exit(code)` | Initiates whole-JVM/process shutdown | Unnecessary in demo; do not substitute for graceful drain |

**Why does main spawn a separate thread to call `context.close()`?** If `main` called `context.close()` directly, it would block in the lifecycle processor waiting for the worker to stop, while `main` itself is still holding the `releaseJob` latch. Both sides would wait on each other. We separate:
- Close thread requests shutdown and waits for callbacks.
- Main thread retains control to open the latch.
- Worker thread executes the job.
- Stop coordinator awaits executor termination.

That simulates **work in flight during shutdown** without needing two processes or an HTTP client. In real applications, the shutdown requester is usually an OS/JVM hook, admin orchestration, or container runtime rather than the main thread spawning a close thread.

### Avoiding Deadlock Between `close` and `release`

Anti-pattern:

~~~java
worker.submitOneJob();
worker.awaitJobStarted();
context.close();       // Waits for job completion ...
worker.releaseJob();   // ... yet this line is never reached in time.
~~~

This illustrates a deadlock bug in main. `context.close()` can block waiting for the stop callback while the worker waits on `releaseJob`; that circular dependency leads to timeout. In the demo, a separate thread calls close so main can release the latch **after** knowing stop was requested.

### Spring Boot Shutdown Hook

Spring Boot registers a shutdown hook by default to close ApplicationContext when the JVM enters normal shutdown. That differs from a module calling `System.exit(0)` directly. If code disables the shutdown hook or the JVM receives SIGKILL, lifecycle callbacks are not guaranteed to run.

No hook trigger is needed to run the demo: we call `context.close()` explicitly and wait for it to finish. That makes milestone ordering far easier to verify than sending OS signals with hard-to-control timing.

## 14. Connection to HTTP Server Graceful Shutdown

The demo is a **non-web application**, so there are no in-flight HTTP requests. This is an intentional choice to focus solely on worker lifecycle. For a Spring Boot web application, the framework supports graceful shutdown for embedded web servers during `ApplicationContext` closing.

In Spring Boot 3.5:
- Graceful shutdown is enabled by default for supported embedded web servers.
- It runs during context closing, when `SmartLifecycle` beans stop.
- The server stops accepting new requests per each server's mechanism; active requests get a grace period.
- Per-phase wait duration can be configured via `spring.lifecycle.timeout-per-shutdown-phase`.

Example when translating the concept to a web app:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

This is a **reference configuration for a web app**, not a requirement of the non-web demo. Exact HTTP graceful shutdown behavior differs across Tomcat, Jetty, Reactor Netty, and Undertow; do not assume every server returns the exact same HTTP status while shutting down.

### HTTP Requests Differ from Background Jobs

- In-flight requests are typically managed and drained by the web server during graceful shutdown.
- Jobs on a manually created `ExecutorService` **are not automatically known to the web server**.
- Message consumers may be owned by framework listener containers with their own stop/ack semantics.
- An HTTP endpoint submitting jobs into an internal queue must coordinate: **stop accepting new requests + stop accepting new jobs + drain accepted jobs**.

Merely enabling `server.shutdown=graceful` does not automatically stop custom executors in the application. The bean owning the executor must still implement proper lifecycle cleanup.

### Readiness in Kubernetes

A pod needs time for the load balancer/Service to stop sending new traffic. In production:
1. Signal the instance is no longer ready for new requests, e.g., via readiness state/probe.
2. Allow routing to update.
3. Stop accepting new work.
4. Drain in-flight work within the deployment budget.
5. Close context and resources.
6. Let the process exit after cleanup or be force-killed by the orchestrator once the deadline expires.

Spring Boot's `ApplicationAvailability` and Actuator readiness probes support availability signaling. **`context.isRunning()` or `ContextClosedEvent` alone is not a complete readiness protocol.**

## 15. If the Work Is a Message Consumer Instead of an `ExecutorService`

For Kafka/JMS/RabbitMQ or another broker, add operations with business meaning:

~~~text
RUNNING
  |
  +-- pause/stop polling new deliveries
  +-- stop extending queue of unacked messages
  +-- keep in-flight task contexts alive
  +-- finish business transaction
  +-- commit/ack if successful
  +-- nack/requeue/let lease expire on incomplete work
  +-- close consumer/session/client as owner contract permits
  +-- signal SmartLifecycle stop callback
~~~

**Never ack a message merely because it was received or because the JVM is shutting down.** Acking must follow durable processing contracts. For unfinished work:
- Let the broker retry if appropriate.
- Require idempotency keys to guard against duplicate processing.
- With transactional outbox, ensure event/DB commits stay consistent.
- Use lease timeouts so abandoned work can be picked up by another instance.
- Ensure consumers stop before closing database connection pools used by handlers.

Do not copy the article's fake latch code verbatim into production Kafka. Use the listener container's lifecycle API and broker-specific semantics instead of assuming `executor.shutdown()` equals stopping polling.

## 16. If the Work Is a Long Batch Job

For batch jobs or scheduled jobs:
- Maintain chunk-level checkpoints.
- Stop accepting new jobs while letting the active chunk finish.
- Outcomes may be COMPLETED, STOPPED, FAILED, or CANCELED depending on the framework.
- Timeouts may require persisting progress and resuming when a new process starts.
- Critical jobs must never rely solely on in-memory state across shutdowns.

For example, with Spring Batch, use `JobRepository` and Spring Batch's stop/restart contracts rather than treating `SmartLifecycle` as a replacement for all job metadata. This simulation only provides **the lifecycle and synchronization mental model**.

### Good Stopping Is Observable Stopping

For real batch workloads, log:
- Job ID, attempt ID, or correlation ID.
- Timestamp when stop started.
- Count of unfinished tasks/chunks.
- Deadline and actual drain duration.
- Commit/rollback/ack outcome.
- Reason for failure/timeout.
- Whether retry is needed or marked succeeded.

Avoid logging personal payloads, secrets, or access tokens.

## 17. Tracking In-Flight Work Counts

In the demo, `AtomicInteger inFlight` tracks accepted jobs not yet finished. The counter is accurate because:
- Incremented before successful submission.
- Rolled back if submission throws an exception.
- Decremented in the task's `finally` block.
- Tests read it only after ordered signals.

In systems with multiple work states, separate:
- `queued`: accepted but not yet started.
- `inFlight`: currently executing.
- `completed`: finished.
- `failed`: errored.
- `cancelled`: aborted.
- `rejected`: turned away during shutdown.

**Do not look solely at an empty executor queue to conclude shutdown is finished.** The queue can be empty while a running task still holds a transaction or connection. `ExecutorService.awaitTermination(...)` returns true once the executor terminates after shutdown, yet even that does not prove an external side effect committed cleanly if task code mishandled errors.

### Metrics and Health/Readiness

In production, export metrics such as:
- Gauge `inflight_jobs`.
- Gauge `accepting_work` or RUNNING/STOPPING state.
- Counter `shutdown_rejected_total`.
- Timer `shutdown_drain_duration`.
- Counter `shutdown_forced_total`.
- Events/logs for timeouts.

Design health/liveness and readiness separately: a STOPPING instance may still have a live process yet must not receive new traffic. Never treat `liveness=false` as the first step of graceful shutdown, or the orchestrator may kill the instance sooner than intended.

## 18. Deterministic Concurrency Testing

### 18.1. Happy Path

Start a job, await `jobStarted`, request stop, await `stopRequested`, try submitting again and confirm rejection. Then release the job; await the callback; verify in-flight = 0 and `isRunning = false`.

### 18.2. Callback Not Invoked Before Job Completion

Hold `releaseJob` closed. `stop(Runnable)` has been called, yet `stopped.await(50ms)` returns false. This is the single most important check to prevent the "callback after `shutdown()` but before termination" bug.

### 18.3. Stopping Twice

Call `stop(callbackA)` then `stop(callbackB)` while in STOPPING state. Both callbacks must run after the same single executor shutdown. No duplicate executor or coordinator should be spawned; if `callbackA` throws a RuntimeException, `callbackB` must still get a chance to run.

### 18.4. Stop Before Start

A real-world implementation needs a clear contract when stop is called before start. In the demo, state NEW transitions to STOPPED and the callback runs immediately; there is no executor to clean up. Subsequent start is rejected because the demo does not support restarts. If real requirements allow starting after an unstarted stop, update the state machine and tests.

### 18.5. Stop After Already STOPPED

Calling stop again does not double-close resources; `stop(callback)` while STOPPED still invokes the callback immediately to satisfy the caller's contract. Inside `@PreDestroy`, synchronous stop therefore becomes a no-op.

### 18.6. Stop Racing with Submit

Use two threads and a barrier to enter the monitor together. Either a submission wins the lock and is accepted **before** state flips to STOPPING, or stop wins and the submission is rejected. The invariant is that **no submission is accepted once STOPPING has been published**. Never write a test asserting a single race outcome unless the race order is explicitly controlled.

### 18.7. Failure/Timeout

Create a task that never returns or ignores interrupts in a test environment with timeouts. Verify:
- Executor has not terminated.
- Callback does not report false success.
- Timeout diagnostic appears.
- Framework waits at most the configured phase timeout.
- Test harness provides forced cleanup in a subprocess so the whole suite cannot hang.

Tests that deliberately create unstoppable threads should run in an **isolated subprocess**, avoiding leaving non-daemon workers hanging indefinitely in the main test runner.

## 19. Common Mistakes Checklist

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `System.exit(0)` immediately with active jobs | Lost data / failed commits | Stop intake, drain, close context before exit |
| Calling `executor.shutdown()` and immediately invoking callback | Signals phase stopped while job still runs | Await `awaitTermination` before callback |
| Calling `shutdownNow()` right away | Interrupts active work; ungraceful | Provide grace period first, force per policy |
| Failing to block submissions during STOPPING | Queue keeps growing; shutdown drags | Guard state under lock, reject new arrivals |
| Using volatile boolean with unsynchronized check-then-submit | Race between submit and shutdown | Share monitor or state machine/queue protocol |
| Using `Thread.sleep` to force ordering | Flaky on CI | CountDownLatch/Phaser/Barrier |
| Dropping the second stop callback | Caller or framework waits uselessly | Queue callbacks during STOPPING |
| Invoking callbacks while holding the lock | Reentrant deadlock or needless blocking | Copy callback list, invoke outside lock |
| Setting `isRunning=false` too early | Framework/tests think resource stopped | Flip only after termination |
| No `@PreDestroy` fallback | Partial shutdown can leak resources | Idempotent cleanup from destroy |
| Closing shared client before worker | Active job fails mid-flight | Order stop phases/dependencies and owner lifetimes |
| Phase timeout shorter than task deadline | Spring destroys beans before callback | Align deadlines; test worst-case |
| Mishandling `InterruptedException` | Task keeps running or cancels improperly | Restore flag, clean up, enforce policy |
| Ignoring forced termination | Data loss on SIGKILL/crash | Checkpoints, retries, idempotency |
| Checking only task queue emptiness | Misses currently executing tasks | Track in-flight count and termination |
| Treating `ContextClosedEvent` as "fully closed" | Misreads lifecycle state | Distinguish close-start event from close return |
| Not joining close thread in tests | Assertions run before shutdown completes | Join/future with timeout |
| Copying demo latches to production | Deliberate blocking lacks business deadlines | Use real task completion/cancellation |
| Assuming restart works after stop | Executor/latches are exhausted | Create new generation if restarts required |
| Putting `System.exit` in a JUnit test | Kills the entire test JVM | Use a subprocess when testing process exit |

## 20. When to Choose a Different Approach

### A Simple Task in One Method

If work is synchronous and callers can wait on a normal method call, `SmartLifecycle` is unnecessary. Use `try-with-resources` to open and close resources in the appropriate scope.

### A Spring-Managed Task Pool

If using a Spring-managed `ThreadPoolTaskExecutor` or `TaskScheduler`, leverage the bean/framework's own shutdown and lifecycle configuration. Do not wrap a second executor around it and spawn unnecessary threads.

### A Background Consumer Needing Pause/Resume APIs

If you only want to pause message consumption while keeping the application context active, control the consumer/listener container directly. `context.close()` tears down the entire context and should not be used as a pause if you need to resume the same beans.

### A Running Web Server

Use the embedded web server's graceful shutdown, Actuator readiness, and deployment-layer coordination. Do not take a non-web demo and assume a single `CountDownLatch` alone will drain HTTP requests properly.

### Work That Must Survive Process Termination

If results must survive JVM restarts/crashes, use durable queues, database checkpoints, transactions, or workflow engines. Threads and latches exist only in process RAM and cannot guarantee durability.

## 21. Review Questions

**Q1:** Why isn't `ExecutorService.shutdown()` enough to prove a worker has stopped?

**A:** It stops accepting new tasks, yet does not wait for running tasks to finish. You must await termination or use a completion protocol.

**Q2:** Why must the test wait for `jobStarted` before requesting close?

**A:** To ensure the task has genuinely started executing, not merely been submitted. Otherwise, the test might inspect a job that never ran.

**Q3:** Why does the test wait for `stopRequested` before attempting late submission?

**A:** To guarantee state has transitioned to STOPPING, making submission rejection deterministic.

**Q4:** When may the `SmartLifecycle.stop(Runnable)` callback be invoked?

**A:** After the component has actually finished stopping per contract, not immediately upon sending the shutdown request.

**Q5:** Why are callbacks invoked outside `synchronized(monitor)`?

**A:** A callback may access state or other beans, risking reentrant deadlock or blocking if the lock is held.

**Q6:** When `ContextClosedEvent` fires, have all beans been destroyed?

**A:** Not yet. The event fires when closing starts, before lifecycle stop and singleton destruction on a normal close path.

**Q7:** Why doesn't `main` call `context.close()` directly before `releaseJob`?

**A:** Because close waits for the stop callback while the worker needs main to open the latch; doing both sequentially on the same thread causes deadlock/timeout.

**Q8:** Can `@PreDestroy` replace `stop(Runnable)`?

**A:** No. Destruction callbacks do not provide phase-level completion signaling to `LifecycleProcessor`; both have distinct roles.

**Q9:** Does `spring.lifecycle.timeout-per-shutdown-phase` automatically interrupt hanging tasks?

**A:** No. It bounds how long Spring waits for a phase; executors/tasks need their own timeouts and cancellation.

**Q10:** Why does `isRunning()` in the demo stay true during STOPPING?

**A:** Because the executor/job is still active; the component has not finished stopping. Only after termination does it become false.

**Q11:** If a job ignores interrupts, is `shutdownNow()` guaranteed to terminate it?

**A:** No. Java interruption is cooperative; different escalation, isolation, and recovery policies are required.

**Q12:** If stop is called twice while STOPPING, what should happen?

**A:** Do not shut down the resource a second time; coalesce into the ongoing stop and queue the new callback for completion.

**Q13:** In the demo, can `start()` be called after `stop()`?

**A:** No, the demo intentionally rejects it to avoid reusing exhausted latches/executor. Applications needing restarts must create a fresh generation.

**Q14:** If a worker uses a DataSource, which should stop first?

**A:** The worker must stop accepting work and finish transactions before the DataSource owner closes the pool, via proper lifecycle/ownership.

**Q15:** Does in-flight equal to 0 guarantee every external side effect is durable?

**A:** No. It only describes task state inside the JVM; commits/acks/durability follow business contracts.

**Q16:** Why isn't `SmartLifecycle` alone enough to guarantee exactly-once after a crash?

**A:** A JVM crash bypasses lifecycle and retries may re-run jobs; external idempotency, transactions, and leases/checkpoints are required.

**Q17:** Does `context.close()` mean `System.exit()`?

**A:** No. Close shuts down one context; `System.exit` initiates whole-JVM shutdown with a process exit status.

**Q18:** Why not rely solely on `Thread.sleep(100)` in concurrency tests?

**A:** It does not prove real before/after ordering, depends on system load, and causes flakiness; latches provide clear happens-before guarantees.

## 22. Extended Exercises

### Exercise A — More Than One Job

Change `newSingleThreadExecutor` to a fixed pool of 2 or 3 threads; accept three tasks, let two wait on a latch and one finish early. Track queued/in-flight separately. Fire callbacks only after all three jobs have finished.

### Exercise B — Premature Callback

Intentionally invoke the callback immediately after `executor.shutdown()` in a separate test branch. Verify section 8's test catches the bug. Restore the correct implementation and ensure tests PASS.

### Exercise C — Repeated Stops

Add three distinct callbacks while the worker is STOPPING. Use a counter or `CountDownLatch(3)` to confirm each callback runs exactly once with no duplicate executor shutdown.

### Exercise D — Interrupted Job

Create a job lasting longer than the graceful deadline, withholding the latch until after the deadline; verify `shutdownNow()` sends an interrupt. Document the difference between "natural completion" and "cancellation". Use a subprocess if a task risks hanging indefinitely.

### Exercise E — Web Graceful Shutdown

Create a separate version with `spring-boot-starter-web` and a slow request endpoint with a deadline. Enable `server.shutdown=graceful`; send SIGTERM from a separate script/terminal, measuring in-flight requests, readiness, and responses. Never put `System.exit` in a controller.

### Exercise F — Replace `CountDownLatch` with a Real Queue

Use a `BlockingQueue` with producer/consumer, stop accepting new work, and let the consumer drain the queue. Pay attention to races between an active producer and shutdown, poison pill/queue closing mechanisms, and timeouts.

### Exercise G — Restartable Generations

Extend the state machine so `STOPPED → RUNNING` allocates a fresh `ExecutorService` and fresh latches per generation. Test repeated start/stop cycles without spawning duplicate workers or reusing a zeroed `CountDownLatch`.

### Exercise H — Measuring Drain Duration

Use `System.nanoTime()` to measure from STOPPING to STOP_COMPLETED. Record histogram/timer metrics; do not measure using low-precision formatted text timestamps and never treat `nanoTime` as a wall clock.

### Exercise I — Multi-Phase Shutdown Coordination

Add a mock `SharedInfrastructure implements SmartLifecycle` bean with phase -100. Make the phase +100 worker depend on it. Assert the worker stops before the infrastructure and jobs never touch closed resources.

### Exercise J — Cleanup on Startup Failure

Have a worker bean open an executor, then let a subsequent dependency fail initialization. Implement startup rollback and fallback cleanup without relying unconditionally on `context.close`, since beans not yet registered successfully might not receive destroy callbacks.

### Exercise K — Active Counter on Exception

Have a task throw an exception after starting and before normal return. Confirm `finally` always decrements `inFlight` so the metric never sticks at 1. Add error logging without leaking sensitive payloads.

### Exercise L — Readiness and Traffic Drain

In an app with Actuator, transition readiness to refusing traffic before stopping the worker. Measure how long the load balancer takes to stop sending requests and ensure Kubernetes deadlines are never shorter than the sum of real drain steps.

## 23. Controlled Shutdown Review Checklist

Before turning the demo into a production system, answer:

1. **Work source:** HTTP, broker, scheduler, batch, or pool?
2. **Ownership:** who owns the worker/executor/client and who has authority to call shutdown?
3. **Intake cutoff:** where does new work stop? Are there races with producers?
4. **In-flight tracking:** from which point to which point is it counted? Does it roll back if submission fails?
5. **Completion waiting:** Future, latch, queue drain, `awaitTermination`, or broker ack?
6. **Stop callback:** fired only after termination, or reported prematurely?
7. **Multiple stop callers:** handled? Does each callback complete per contract?
8. **Deadlines:** aligned across task, executor, lifecycle phase, and orchestrator?
9. **Interrupt/cancel:** handled safely by tasks?
10. **Resource dependencies:** alive long enough for jobs to finish?
11. **`@PreDestroy`:** serves as idempotent fallback cleanup?
12. **`ContextClosedEvent`:** never mistaken for completed destruction?
13. **Readiness/traffic drain:** designed if web/microservice?
14. **Crash/SIGKILL:** external recovery/idempotency/checkpoints present?
15. **Metrics/logs:** clearly record in-flight, rejected, completed, timeout counts?
16. **Unit/integration tests:** verify exact shutdown ordering rather than just "no exception thrown"?
17. **Production restarts:** need new generations after stop?
18. **Security:** logs guaranteed free of tokens, customer payloads, or job secrets?

## 24. Official Documentation

- [Spring Framework — Lifecycle and SmartLifecycle](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): phase ordering, stop callbacks, Spring lifecycle processor, and bean destruction.
- [Spring Framework — SmartLifecycle Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html): `start`, `stop(Runnable)`, `isRunning`, callbacks, and auto-start.
- [Spring Framework — DefaultLifecycleProcessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): waiting for callbacks and phase timeouts.
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): closing web ApplicationContext, graceful server request drain, and `spring.lifecycle.timeout-per-shutdown-phase`.
- [Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): context creation, runners, events, and shutdown hook.
- [Spring Boot 3.5.16 — SpringApplication Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html): non-web configuration and shutdown hook registration.
- [Java SE 17 — ExecutorService Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `shutdownNow`, `awaitTermination`, termination contract.
- [Java SE 17 — CountDownLatch Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordination, memory consistency effects, and timeouts.
- [Java SE 17 — Thread Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): interrupts, daemon threads, and lifecycle.

### Final Takeaways

1. **Stop accepting new work before draining old work**; synchronize both to prevent races.
2. `ExecutorService.shutdown()` **does not wait for tasks to finish**; use `awaitTermination` and timely callbacks.
3. `SmartLifecycle.stop(Runnable)` must invoke callbacks **after the component has actually stopped**.
4. `CountDownLatch` enables simulating in-flight state and deterministic shutdown order without fake sleeps.
5. In the demo, `ContextClosedEvent` arrives **before** lifecycle stop, while `@PreDestroy` arrives **after** stop succeeds.
6. Never call `context.close()` directly on the sole thread holding task release control if it creates a circular dependency.
7. Enforce timeouts and failure policies; **never report STOPPED while the executor is still alive**.
8. `getPhase()` and resource ownership determine the closing order of workers, clients, and pools.
9. Forced JVM termination does not guarantee callbacks run; critical jobs need **transactions, retries, idempotency, and checkpoints**.
10. Reliable shutdown must be **tested for ordering, rejection, completion, timing, and cleanup**, not merely observing that the process eventually exits.
