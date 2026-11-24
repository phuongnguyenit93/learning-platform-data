# Future.get(timeout) Does Not Automatically Stop Background Work

In a Spring Framework application, a request may submit a task to generate a report, call an external API, or process data on an `ExecutorService`/`ThreadPoolTaskExecutor`, and then wait for the result using `Future.get(timeout, unit)`. If the wait time expires, Java throws `TimeoutException`. **That only means the waiting thread did not receive the result within the allowed duration; it does not mean the task was cancelled, the worker stopped, or business side effects were undone.**

This is the core distinction in the **Timeouts and Cancellation** group of the **Spring Framework – concurrency** module. Three questions must be understood independently:

1. **Is the caller still waiting or has it stopped waiting?** `Future.get(timeout)` controls the caller's blocking duration.
2. **What state is the Future in?** A Future may be incomplete, completed normally, completed exceptionally, or cancelled.
3. **Has the actual work on the worker stopped?** Stopping work requires cooperative cancellation/interruption mechanisms and per-resource timeouts; it cannot be inferred from the caller's exception.

A system may return a “timed out” response while the worker is still calling the database, writing files, or sending emails. If the client retries without idempotency, the effect can happen **twice**.

## 1. Timing Model: Caller Expires First, Worker Continues

```text
Time ───────────────────────────────────────────────────────────────────>

HTTP caller / main thread
  | submit(task)
  |--------------- Future<?> ----------------|
  | get(100, MILLISECONDS)
  |          └──── 100 ms ────> TimeoutException
  |                              |
  |                              └─ Caller continues / returns HTTP response
  |
Worker thread
  |        [queued]    [start]   [processing I/O .....................]
  |                                                        [DB write]
  |                                                          [done]
  |
  +-- Caller timeout does NOT automatically send interrupt to worker +
```

The two timelines are **independent**:

- `get(timeout)` ends **waiting for the result** upon expiration.
- The task handed to the executor may still be **QUEUED** or **RUNNING**.
- The worker may finish normally right after the caller receives `TimeoutException`.
- The task may fail after the timeout and nobody will observe the exception if the system drops the handle.
- A task may already have produced external side effects even though the caller considers the request “failed”.

Therefore, an accurate response should be **“timed out waiting for result”**, not automatically **“cancelled work”** or **“transaction did not happen”**.

## 2. What Exactly Does Future.get(timeout) Guarantee?

JDK API:

```java
V get(long timeout, TimeUnit unit)
        throws InterruptedException,
               ExecutionException,
               TimeoutException;
```

On a `Future<V>`, this call **waits at most the requested duration** for the computation to complete. Possible outcomes:

| Outcome from `get(timeout)` | Definite meaning | What must not be inferred |
| --- | --- | --- |
| Returns value `V` | Computation completed normally per the Future contract | All external side effects are durable if code did not guarantee it |
| `TimeoutException` | No result received within the wait duration | Task cancelled / stopped / rolled back |
| `ExecutionException` | Task completed exceptionally; original exception is in `getCause()` | Task never performed side effects |
| `InterruptedException` | **The thread calling `get`** was interrupted while waiting | Worker was automatically interrupted or stopped |
| `CancellationException` | Future was cancelled according to Future state | Worker definitely stopped instantaneously |

`Future.get()` without a timeout waits until a result is available or an error/interruption occurs. `Future.get(timeout, unit)` changes the **wait limit**; it does not add a “kill task” capability.

**Note on timeouts:** the duration is counted for the caller's wait step, not as a business execution deadline. If a task waits in the executor queue for 90 ms before starting, `get(100ms)` may have very little time left to see the result. If a task has already been running for 10 minutes before the caller invokes `get(100ms)`, this call only waits up to about 100 ms from the moment it is called.

`get` is a blocking operation. If called directly on an HTTP request thread, the request thread can remain occupied for the entire timeout duration. Choose returning `CompletableFuture` directly, polling job status, or async HTTP responses where appropriate.

### Three States That Are Not the Same

```text
Caller wait state:  WAITING --timeout--> NOT_WAITING
Future state:       PENDING -----------→ PENDING / SUCCESS / FAILURE / CANCELLED
Worker state:       QUEUED ------------→ RUNNING --------→ TERMINATED
```

**There is no automatic arrow from `TimeoutException` to `CANCELLED`**. Only code that actively cancels or another system policy can issue a cancel signal, and even once a cancel request is recorded, the worker may not stop instantaneously.

## 3. Standalone Java 17 Example: Timeout Occurs, Yet Task Still Completes

To demonstrate without depending on machine speed or the thread scheduler, use `CountDownLatch`. The worker starts and waits on a latch; the caller waits with `Future.get(50, MILLISECONDS)`. Because the latch **has not been opened**, the worker cannot complete before the timeout.

Create file **TimeoutDoesNotStopDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

public class TimeoutDoesNotStopDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch allowFinish = new CountDownLatch(1);
        AtomicBoolean businessEffect = new AtomicBoolean(false);

        try {
            Future<String> future = pool.submit(() -> {
                started.countDown();
                allowFinish.await(); // Intentionally keep worker from finishing yet
                businessEffect.set(true);
                return "report-saved";
            });

            started.await(); // Ensure task has started

            try {
                future.get(50, TimeUnit.MILLISECONDS);
                throw new AssertionError("Task should still be waiting");
            } catch (TimeoutException expected) {
                System.out.println("wait timed out");
            }

            System.out.println("future done after timeout: "
                    + future.isDone());
            System.out.println("effect after timeout: "
                    + businessEffect.get());

            allowFinish.countDown(); // Worker may now finish
            System.out.println("later result: " + future.get());
            System.out.println("effect after release: "
                    + businessEffect.get());
        } finally {
            allowFinish.countDown();
            pool.shutdownNow();
        }
    }
}
```

Compile/run:

```bash
javac TimeoutDoesNotStopDemo.java
java TimeoutDoesNotStopDemo
```

**Deterministic stdout when the program runs normally:**

```text
wait timed out
future done after timeout: false
effect after timeout: false
later result: report-saved
effect after release: true
```

Step-by-step explanation:

1. `pool.submit` **accepts** the callable and returns `Future<String>`, without waiting for the work to finish.
2. `started.await()` proves the worker entered the task; the worker blocks on `allowFinish.await()`. This is an intentional synchronization point, not an assumption that “sleeping 50 ms is enough”.
3. `future.get(50, MILLISECONDS)` has no way to receive a result while the latch is closed, so it throws `TimeoutException`.
4. `Future.isDone()` is still `false` and the business flag is still `false` because the worker has not reached writing the result yet.
5. The caller opens the latch; **the exact same prior task resumes processing**, sets the flag, and returns `report-saved`.
6. The second `future.get()` successfully receives the result. No second task was created by this `get` call.

**Do not infer from this demo that whenever a timeout happens `isDone() == false`.** In a real system, the worker could finish **right after** `get` throws `TimeoutException` but **before** the caller reads `isDone()`, so the read could return `true`. The latch in the example intentionally eliminates the race to illustrate the mechanism.

The `businessEffect` flag only simulates an in-memory effect; it does not prove a database commit or external system occurred. The lesson is that **the worker's permission to continue running does not vanish when the caller stops waiting**.

## 4. `get(timeout)`, `cancel(...)`, and Interrupt Are Three Distinct Operations

After catching `TimeoutException`, code may decide **not to cancel** or **to request cancellation**. That choice belongs to business policy.

```java
try {
    return future.get(200, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    // No automatic cancel here.
    // If business logic permits cancellation:
    boolean requested = future.cancel(true);
    throw e;
}
```

This is a **fragment**, not a standalone class: `future` must be initialized and the method/caller must declare or handle exceptions. Crucially, the line `future.cancel(true)` **is added by the developer**, not behavior built into `get(timeout)`.

### 4.1. `cancel(false)`

For `FutureTask` / many tasks created by `ExecutorService.submit`, `cancel(false)` can mark the Future as **cancelled** without **issuing an interrupt** to the worker. If the task is already running, the code may still continue producing side effects even though the caller sees `future.isCancelled() == true`. Do not describe `cancel(false)` as a command that “definitely stops if not yet running and waits to finish if already running”.

### 4.2. `cancel(true)`

With a `FutureTask` running in a standard `ThreadPoolExecutor`, `cancel(true)` **attempts to request an interrupt** on the thread executing the task. However:

- The task may already have completed before cancel is called; in that case `cancel` returns `false`.
- If the task is waiting in the queue, cancellation can prevent it from needing to run; removing cancelled items from the queue depends on the executor and cleanup policy.
- If the task is running, interrupt is a **cooperative signal**, not a forced termination of the JVM thread.
- `Thread.sleep`, `Object.wait`, `CountDownLatch.await`, and many JDK blocking methods can throw `InterruptedException`.
- A CPU loop that does not check the interrupt status can keep running.
- Some I/O/SDKs do not react to interrupts or have already dispatched external effects before the signal arrives.
- `isCancelled() == true` and `isDone() == true` reflect Future state; **they are not proof that the physical worker died or all side effects were undone**.

### 4.3. `Thread.interrupt()` Is Not `Thread.stop()`

`Thread.interrupt()` sets the interrupt flag or causes a blocking operation that supports interruption to throw `InterruptedException`. It does not forcibly kill a thread and does not roll back transactions in external systems.

`Thread.stop()` has been deprecated because it is unsafe; do not use it to “fix timeouts”. The right approach is **cooperative cancellation**: code periodically checks the flag, configures timeouts on blocking APIs, releases resources in `finally`, and never catches and swallows interrupts.

## 5. Runnable Java 17: cancel(true) Only Issues a Cooperative Interrupt Request

This example uses a task intentionally waiting on a `CountDownLatch`, an **interruptible** operation. Only when the worker receives the interrupt and enters the `catch` branch do we have evidence the task observed the signal.

Save as **CooperativeCancelDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CooperativeCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch observedInterrupt = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        try {
            Future<?> future = pool.submit(() -> {
                started.countDown();
                try {
                    neverReleased.await();
                } catch (InterruptedException ex) {
                    observedInterrupt.countDown();
                    Thread.currentThread().interrupt();
                }
            });

            started.await();
            boolean requested = future.cancel(true);
            observedInterrupt.await();

            System.out.println("cancel requested: " + requested);
            System.out.println("future cancelled: "
                    + future.isCancelled());
            System.out.println("worker observed interrupt: true");
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile/run:

```bash
javac CooperativeCancelDemo.java
java CooperativeCancelDemo
```

**Stdout under normal demo conditions:**

```text
cancel requested: true
future cancelled: true
worker observed interrupt: true
```

`started.await()` guarantees the callable entered the wait section before `main` calls `cancel(true)`. In this default executor, `FutureTask` sends an interrupt to the runner. When `CountDownLatch.await()` is interrupted, the worker executes `catch` and marks `observedInterrupt`; `main` waits on that latch before printing. Therefore **do not print “observed” based solely on `isCancelled()`**.

Note that the demo **intentionally cooperates with interruption**. If `neverReleased.await()` were replaced with a library call that does not support interruption, or an infinite CPU loop ignoring the interrupt flag, the “worker observed interrupt” outcome would no longer be guaranteed. In production, avoid indefinite waits in tests and add appropriate deadline/timeout tests.

### 5.1. How to Handle InterruptedException?

Commonly seen code:

```java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    // Catching and ignoring is dangerous.
}
```

If you can propagate the exception upward, let the method declare `throws InterruptedException`. If you must catch it and cannot rethrow the same exception type, you typically need:

```java
catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Clean up resources / record appropriate cancellation state.
    return;
}
```

This is a fragment inside a method with a compatible return type. **Restoring the interrupt flag** lets higher layers observe that the signal occurred; afterward, do not continue running unnecessary side effects. Do not turn every interrupt into “permanent business failure” if it is a legitimate shutdown request.

## 6. `CompletableFuture`: Timeout/Cancel Have Their Own Limitations

`CompletableFuture` implements both `Future` and `CompletionStage`. It provides convenient timeout APIs from Java 9 onward, yet **does not automatically stop the underlying supplier/worker**.

| Usage | Effect on waiting / Future state | Auto-interrupts worker? |
| --- | --- | --- |
| `cf.get(100, MILLISECONDS)` | Caller waits up to 100 ms; may throw `TimeoutException` | **No** |
| `cf.orTimeout(100, MILLISECONDS)` | Arranges for **cf itself** to complete exceptionally with `TimeoutException` if not done by deadline | **No** |
| `cf.completeOnTimeout(fallback, 100, MILLISECONDS)` | Arranges for **cf itself** to complete normally with fallback if not done | **No** |
| `cf.cancel(true)` | Completes `cf` in cancellation state if still possible | With JDK's `CompletableFuture` implementation: **no** |
| `futureTask.cancel(true)` | Requests FutureTask cancellation; may send interrupt to runner | **May send**, but stopping is best effort |

The `CompletableFuture.cancel(boolean)` Javadoc states clearly that `mayInterruptIfRunning` **has no effect in this implementation**, because `CompletableFuture` does not use interrupts to control processing. This is an important difference from `FutureTask` returned by `ExecutorService.submit(...)`.

### 6.1. `orTimeout` Is “Result Expiration”, Not “Stop Supplier”

```java
CompletableFuture<String> cf =
        CompletableFuture.supplyAsync(() -> callSlowService(), executor);

cf.orTimeout(100, TimeUnit.MILLISECONDS);
```

This is a fragment; `callSlowService` and `executor` must exist. If the supplier has not finished after 100 ms, `cf` is completed exceptionally due to timeout. **The underlying supplier can still run and cause external effects.** When it finishes late, it cannot replace `cf`'s already-completed exceptional value.

Consequence: `cf.get()` afterward can throw `ExecutionException` whose cause is `TimeoutException`; unlike `get(100, MILLISECONDS)` directly throwing `TimeoutException` because the caller waited too long.

### 6.2. `completeOnTimeout` Can Mask Late Results

```java
CompletableFuture<String> cf =
        CompletableFuture.supplyAsync(() -> callSlowService(), executor)
                .completeOnTimeout("cached-fallback", 100,
                        TimeUnit.MILLISECONDS);
```

Upon expiration, the caller may see `"cached-fallback"` as a **successful Future result value**, while the original supplier has not necessarily stopped. If the supplier is writing data, the late execution can still cause side effects. Hence **do not use fallback completion as proof that the underlying business work was cancelled**.

A valid fallback must be designed around the domain: returning stale cached data for a read-only query may be acceptable; “charging failed so retry” when the provider's status is unknown is dangerous.

### 6.3. Mini Example of the Difference Between the Two Timeouts

```java
CompletableFuture<String> pending = new CompletableFuture<>();
try {
    pending.get(10, TimeUnit.MILLISECONDS);
} catch (TimeoutException ex) {
    System.out.println("caller timed out");
}
System.out.println("still pending: " + !pending.isDone());
```

This is a **fragment** requiring JDK imports. Because `pending` is not completed by any thread, the last line prints `still pending: true`. If replaced with `pending.orTimeout(10, TimeUnit.MILLISECONDS)` followed by awaiting the stage, that future itself transitions to **exceptional** completion, yet no worker is interrupted because the example has no worker at all.

**Rule of thumb:** `get(timeout)` is a **wait timeout**, `orTimeout` is a **Future result timeout**, and both differ from an **actual operation timeout**.

## 7. Four Timeout Layers in a Spring Application

Do not set one `1000 ms` value and think it controls everything. There are usually at least four layers:

| Layer | Example | Affected resource | What may still run after timeout? |
| --- | --- | --- | --- |
| HTTP client timeout | Client waits past deadline for response | Client / caller side | Server may still be processing request/job |
| HTTP async request timeout | Servlet async / MVC `DeferredResult`/`WebAsyncTask` | HTTP response lifecycle | Background work may continue if cancellation is not wired |
| Future wait timeout | `future.get(200, MILLISECONDS)` | Waiting thread | Future task remains queued/running |
| Dependency operation timeout | JDBC query timeout, HTTP connect/read/response timeout | Specific I/O call | Cleanup/retry logic may remain; dispatched effects may still happen |
| Job business deadline | Deadline checked inside worker/job store | Business state and policy | Already-started steps may need reconciliation/compensation |

**They do not automatically inherit from one another.** An HTTP client closing its connection does not guarantee Spring actively cancels the worker; `Future.get(timeout)` also does not automatically attach timeouts to JDBC queries or HTTP clients inside the worker.

### 7.1. When There Is an HTTP Request Deadline

An API whose client waits at most 2 seconds does not mean a 30-second report must be killed at second 2. There are two different designs:

- **Synchronous processing with deadline:** bound I/O steps, return a timeout error per contract, and decide whether to request cancellation and free resources.
- **Background processing:** acknowledge job acceptance, return HTTP **202 Accepted + job ID**, and provide a status endpoint. The HTTP response ends while the job can continue; this is not a failure.

The mandatory requirement is **accurate communication to the client**, because “timed out waiting for response” differs from “no job exists”, and “job accepted” differs from “job completed”.

### 7.2. Transaction Timeout Differs from Future Timeout

With Spring `@Transactional`, transactions are normally bound to the executing thread and managed by the transaction manager. A caller timing out on `Future.get(timeout)` **does not automatically roll back a transaction running on another worker**. Conversely, a transaction timeout can cause a DB operation to fail at a certain checkpoint, but does not resolve all effects on external services.

Do not rely on interrupts to reverse a committed transaction. For multi-system business workflows, you need idempotency, explicit transaction boundaries, and dedicated compensation/reconciliation.

## 8. Spring Boot 3.x: Demo Endpoint Times Out Waiting While Worker Continues

The following example uses **Java 17+**, **Spring Boot 3.x / Spring Framework 6.x**, and dependency `spring-boot-starter-web`. It clearly illustrates:

- `ThreadPoolTaskExecutor` accepts the background task.
- Controller waits for the result for at most **100 ms**.
- If the controller times out waiting, it returns **202 Accepted** with an ID for lookup, **without calling `cancel`**.
- The worker is simulated to take **600 ms** and continues updating state in a `ConcurrentHashMap`.
- This is an **in-memory demo only**, with no durable job store or crash-recovery guarantees.

Place all code in **src/main/java/com/example/demo/TimeoutApplication.java**:

```java
package com.example.demo;

import java.net.URI;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableAsync
public class TimeoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(TimeoutApplication.class, args);
    }

    @Bean("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("report-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}

@Service
class JobStates {
    private final ConcurrentMap<String, String> states =
            new ConcurrentHashMap<>();

    void set(String id, String state) {
        states.put(id, state);
    }

    String get(String id) {
        return states.get(id);
    }

    void remove(String id) {
        states.remove(id);
    }
}

@Service
class ReportWorker {
    private final JobStates jobs;

    ReportWorker(JobStates jobs) {
        this.jobs = jobs;
    }

    @Async("reportExecutor")
    public CompletableFuture<String> generate(String jobId) {
        jobs.set(jobId, "RUNNING");
        try {
            Thread.sleep(600); // Only simulating blocking I/O.
            jobs.set(jobId, "SUCCEEDED");
            return CompletableFuture.completedFuture("report:" + jobId);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            jobs.set(jobId, "FAILED");
            return CompletableFuture.failedFuture(ex);
        }
    }
}

@RestController
class JobController {
    private final ReportWorker worker;
    private final JobStates jobs;

    JobController(ReportWorker worker, JobStates jobs) {
        this.worker = worker;
        this.jobs = jobs;
    }

    @PostMapping("/jobs")
    public ResponseEntity<?> submit() {
        String id = UUID.randomUUID().toString();
        jobs.set(id, "QUEUED");

        final CompletableFuture<String> result;
        try {
            result = worker.generate(id);
        } catch (TaskRejectedException rejected) {
            jobs.remove(id);
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(Map.of("error", "executor_overloaded"));
        }

        try {
            String report = result.get(100, TimeUnit.MILLISECONDS);
            return ResponseEntity.ok(
                    Map.of("jobId", id, "state", "SUCCEEDED",
                            "result", report));
        } catch (TimeoutException timeout) {
            // Do not call result.cancel(): worker can still run.
            return ResponseEntity.accepted()
                    .location(URI.create("/jobs/" + id))
                    .body(Map.of("jobId", id, "state", "PROCESSING",
                            "statusUrl", "/jobs/" + id));
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(Map.of("jobId", id, "error", "caller_interrupted"));
        } catch (ExecutionException failed) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("jobId", id, "error", "worker_failed"));
        }
    }

    @GetMapping("/jobs/{id}")
    public ResponseEntity<?> status(@PathVariable String id) {
        String state = jobs.get(id);
        if (state == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(Map.of("jobId", id, "state", state));
    }
}
```

Run using the project's Spring Boot build tool:

```bash
./gradlew bootRun
curl -i -X POST http://localhost:8080/jobs
```

On Windows, you can use `gradlew.bat bootRun`. Because the simulated worker sleeps 600 ms while the caller waits 100 ms, when the pool accepts the task and the JVM/scheduler behave normally, the endpoint typically returns:

```http
HTTP/1.1 202 Accepted
Location: /jobs/<id>

{"jobId":"<id>","state":"PROCESSING","statusUrl":"/jobs/<id>"}
```

**`<id>` is a placeholder for an actual newly generated UUID**, not a fixed response string. Under overload, it may return 503; for tasks finishing fast enough before the wait limit, it may return 200. Calling `GET /jobs/{id}` with the real job ID may return `QUEUED`, `RUNNING`, and then `SUCCEEDED` once the worker finishes.

The example does not guarantee the task completes in exactly 600 ms: `Thread.sleep(600)` only blocks the worker for at least roughly that duration under execution conditions; the worker may also wait in the queue and on scheduling. **That is why an API should not promise completion timing based solely on the caller's timeout.**

### 8.1. Key Lines of Code

```java
String report = result.get(100, TimeUnit.MILLISECONDS);
```

This line **waits on the Future on the controller thread**, without cancelling when the wait expires.

```java
catch (TimeoutException timeout) {
    return ResponseEntity.accepted()
            .location(URI.create("/jobs/" + id))
            .body(Map.of("jobId", id, "state", "PROCESSING"));
}
```

This is an abbreviated fragment. It accurately communicates that the job is still processing rather than saying “failed”. The worker submitted to the pool runs independently until it completes or hits another error.

```java
@Async("reportExecutor")
public CompletableFuture<String> generate(String jobId) {
    // ...
}
```

`@Async` only takes effect when the call goes through the **Spring proxy** (in the example, the controller calls a separate `ReportWorker` bean). If code inside `ReportWorker` itself calls `this.generate(id)`, self-invocation normally bypasses the proxy in default mode, eliminating the intended executor boundary.

### 8.2. Scope of Guarantees in the Spring Example

This is a demo, not a production job platform:

- `JobStates` is an **in-memory** `ConcurrentHashMap`, usable on a single instance only. Restarts/crashes lose state and unfinished tasks; multiple replicas do not share jobs.
- HTTP 202 in the demo only confirms the task was accepted into the executor under current policy; it **does not promise durable delivery**.
- If the request thread is interrupted instead of timing out, job state may still continue being updated by the worker. You need an explicit cancel policy if you want cancellation.
- The worker only simulates processing with `sleep`; `SUCCEEDED` indicates demo completion, not proof a report file was persisted.
- `ThreadPoolTaskExecutor` needs appropriate core/max/queue/rejection sizing, and you should monitor accepted/completed/failed/rejected task counts.
- In a real API, status polling requires authorization, retention/TTL, idempotency keys, and stuck-job recovery.

**Another exception:** A custom `RejectedExecutionHandler` such as `CallerRunsPolicy` can run the task directly on the caller thread when the pool is overloaded. `@Async` does not guarantee the request thread always returns quickly under every configuration; know which executor policy you are using.

## 9. If You Really Want to Stop the Task After Timeout

Stopping work requires design at **multiple levels**, not just adding `get(timeout)`:

1. **Determine whether cancellation is allowed.** A best-effort email send might be cancelled before sending, whereas a payment request that reached a provider may require reconciliation before marking cancelled.
2. **Keep a cancellable handle to the task.** With `ExecutorService.submit`, the returned `Future` can take `cancel(true)`; with `CompletableFuture`, `cancel(true)` does not automatically interrupt the supplier.
3. **Cooperating tasks.** Check interrupt/deadline flags at safe points, exit early when appropriate, and clean up in `finally`.
4. **Configure timeouts on every blocking operation.** HTTP client connect/read timeouts, JDBC query timeouts, lock acquisition timeouts, or deadline-aware APIs.
5. **Reduce risk of partial side effects.** Record idempotency keys, transaction boundaries, intermediate states, and reconciliation routines.
6. **Distinguish requested cancellation from confirmed stop.** You can have `CANCEL_REQUESTED`, then `CANCELLED` only once the worker confirms stopping at a safe point, or `COMPLETED_AFTER_CANCEL_REQUEST` if side effects could not be prevented.
7. **Track jobs still running after caller timeout.** Requires metrics, log correlation IDs, a job store, and operational tooling.

### 9.1. Cooperative Deadline Pattern in a CPU-Bound Task

This is an illustrative **fragment** using a deadline based on `System.nanoTime()`:

```java
long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);

for (WorkItem item : items) {
    if (Thread.currentThread().isInterrupted()) {
        throw new CancellationException("Interrupted");
    }
    if (System.nanoTime() - deadline >= 0) {
        throw new TimeoutException("Job deadline reached");
    }
    processOneItem(item);
}
```

This snippet is not a standalone compilable program: `WorkItem`, `items`, and `processOneItem` must be declared; the method must handle/declare `TimeoutException` and import `TimeUnit` and `CancellationException`. `System.nanoTime()` is better suited for measuring **elapsed intervals** than a wall-clock time when computing deadlines.

**Caveat:** checking the deadline between items only works when `processOneItem` returns control. If a blocking JDBC/HTTP call hangs, the loop's deadline check cannot free the worker on its own. Timeouts must be configured in the underlying I/O library.

### 9.2. When the Task Calls an External System

Suppose a worker calls a payment gateway and the caller's `get(1, SECONDS)` times out. **Do not conclude the transaction failed.** The provider may already have executed the request while the response was lost. Retrying to create a new transaction risks double-charging.

Safer design:

- Use a stable **idempotency key** for the logical request.
- Query final status from the provider using a transaction/reference ID.
- Only mark `FAILED`/`SUCCEEDED` when there is contractual evidence.
- If the state is uncertain, record `UNKNOWN` or `RECONCILING` instead of guessing.
- Limit retries, add backoff/jitter, and avoid repeating non-idempotent side effects.

This is why cancellation is a **business decision with impact**, not an arbitrary technical call inside every `catch (TimeoutException)`.

## 10. Timing Out Does Not Mean the Task Is Broken

A task can be in many states when the caller stops waiting:

| At caller timeout | What may happen next | Action depending on needs |
| --- | --- | --- |
| Task still in queue | Worker may pick it up and run late | Poll status, check deadline before starting |
| Task is CPU-bound | Continues computing | Cooperative interrupt/deadline |
| Task waiting on DB connection | Keeps waiting until connection or timeout | Set acquire/query timeouts; limit concurrency |
| Task waiting on external API | Request may still reach provider | Appropriate client timeouts, idempotency/reconciliation |
| Task just finished normally | `Future.isDone()` may turn true right after timeout | Read result if contract allows, avoid creating duplicate job |
| Task failed inside worker | Future may complete exceptionally after caller leaves | Observe Future callbacks/metrics/status |
| Task was requested to cancel | Future may show cancelled before worker actually stops | Track confirmation from worker |
| Application shutting down | Queue/tasks may be interrupted per lifecycle | Graceful shutdown and durable job processing |

Do not mark a job `FAILED` solely because of the **caller's** `TimeoutException`; if a status is needed, record `WAIT_TIMEOUT` for the request/wait attempt while keeping the job as `QUEUED`/`RUNNING`/`UNKNOWN` per reality.

## 11. Race Conditions When Cancelling, Checking Status, and Retrying

### 11.1. Race Between Timeout and Completion

```text
T1: future.get(timeout) throws TimeoutException
T2: worker completes successfully
T1: checks future.isDone() -> true
```

There is no contradiction: timeout only describes that no result was available **before the wait deadline**, while the result can arrive right afterward. `isDone()` is a snapshot at read time, not proof of the worker's state at the exact instant `get` threw the exception.

### 11.2. Race Between cancel(true) and Task Completion

`Future.cancel(true)` returns `false` if the task already completed or could not be cancelled per its state machine. It can return `true` before the worker has a chance to process the interrupt. Thus, **the return value is only the result of the cancellation request at the Future level**, not the exact moment side effects stopped.

### 11.3. Retrying After an HTTP Timeout

A client that never receives a response may resend the same request while the server already accepted the first task. Without a request ID / idempotency key, both jobs can run and both produce side effects. The system should store the key with a request hash under a unique constraint and return the existing job ID if the payload matches.

### 11.4. Task Completing After the Request Ends

HTTP request-scoped objects, security context, MDC, or the request thread's transaction may **no longer be valid** while the worker continues. Do not retain mutable references to the request/response for use after timeout; pass minimal, controlled data into the job, open a new transaction when needed, and clean up thread-locals on the worker pool.

## 12. Distinguishing Easily Confused Timeout/Cancellation APIs

| API | Primary effect | Key point to remember |
| --- | --- | --- |
| `Future.get(timeout, unit)` | Bounds **caller** wait duration | Does not automatically call cancel |
| `Future.cancel(true)` | Requests cancellation, may interrupt runner depending on implementation | Does not guarantee stopping side effects |
| `CompletableFuture.orTimeout(...)` | Sets result deadline for the **`CompletableFuture`** | Does not interrupt the supplier |
| `CompletableFuture.completeOnTimeout(...)` | Completes CF with fallback if not finished | Underlying work can still continue |
| `ExecutorService.invokeAll(tasks, timeout, unit)` | Waits on batch within deadline; API **has a mechanism to cancel unfinished tasks** on expiration | Unlike `Future.get(timeout)`, though cancellation is still best effort |
| `ExecutorService.shutdown()` | Stops accepting new tasks, processes submitted tasks per executor | Does not cancel all tasks |
| `ExecutorService.shutdownNow()` | Attempts to stop running tasks and returns unstarted tasks | Uses best-effort interrupt; does not force-kill |
| `ExecutorService.awaitTermination(...)` | Waits for executor termination up to a duration | Does not send cancel just by waiting until expiration |
| HTTP client read timeout | Limits I/O wait time on client | Server/provider may already have processed it |
| Spring MVC async request timeout | Limits async HTTP response lifecycle | Does not guarantee background job stops |

Crucial point: **never equate APIs just because their names contain “timeout”**. There are APIs that limit waiting, APIs that complete Future state, I/O timeout APIs, and APIs with distinct cancellation behavior.

## 13. Architecture Choice When Work Can Exceed the Request Timeout

If generating a report takes 30 seconds while a reverse proxy allows HTTP requests at most 5 seconds, instead of having the request call `get(5, SECONDS)` and return an ambiguous error, use a background job protocol:

```text
POST /jobs + Idempotency-Key
    |
    v
Authenticate, validate input
    |
    v
Persist job to DB / durable queue, commit
    |
    v
HTTP 202 + jobId + statusUrl
    |
    v
Dedicated worker processes, retries per policy
    |
    v
RUNNING → SUCCEEDED / FAILED / CANCELLED / RECONCILING
    |
    v
GET /jobs/{jobId} or webhook to retrieve final result
```

**Benefits:**

- HTTP clients do not need to hold an open connection for the entire processing time.
- The job has a status and ID independent of the HTTP request.
- Durability depends on the chosen job store/queue, not on a single process's RAM.
- Clients can retry requests using the idempotency key without creating duplicate logical jobs.
- Workers can handle retries, crash recovery, and dead-lettering separately.
- If cancellation is desired, `POST /jobs/{id}/cancel` can record `CANCEL_REQUESTED` and let the worker confirm safely.

**Do not promise exactly-once side effects merely because a queue is used.** Message brokers can redeliver, so workers need idempotency and reconciliation. A 202 after durable job commit confirms **durable acceptance**, not “business work finished”.

## 14. Common Errors

**Error 1 — Catching `TimeoutException` and logging “Task cancelled”.** Wrong if no cancellation was requested and no worker stop was confirmed. You only know the caller timed out waiting.

**Error 2 — Setting `get(100ms)` and assuming the JDBC query also has a 100 ms timeout.** Queries have their own deadlines; configure driver/query/transaction timeouts properly.

**Error 3 — Thinking an unfinished Future after timeout will be GC'd and stop running.** The task is held by the executor and the worker can keep running; dropping the caller's Future reference does not cancel the task.

**Error 4 — Calling `cancel(true)` and believing all effects were reversed.** Interrupts do not roll back HTTP calls, committed database transactions, or sent messages.

**Error 5 — Catching `InterruptedException` and silently continuing.** Easily ignores shutdown/cancellation, leaving the task holding resources and producing side effects after a stop was requested.

**Error 6 — Using `CompletableFuture.cancel(true)` to “force-interrupt” a supplier.** The boolean parameter has no interrupt effect in the JDK's `CompletableFuture` implementation.

**Error 7 — Using `orTimeout` and thinking backend I/O is cancelled.** It completes the CF exceptionally without automatically stopping the underlying supplier.

**Error 8 — Using `completeOnTimeout` with a fallback and declaring the underlying business operation succeeded/failed.** The fallback is only the Future's result under the current contract; background work can still produce side effects.

**Error 9 — Unlimited retries after timeout on the same non-idempotent operation.** Can trigger duplicate emails, file creations, or payments.

**Error 10 — Failing to separate queue wait time from execution time.** `get(timeout)` can expire because the task never got a worker, not because task logic hung.

**Error 11 — Waiting on `Future.get(timeout)` on a single-thread executor thread while needing another task on the same pool to finish.** Causes starvation/deadlock; timeout bounds how long it blocks but does not fix the circular dependency design.

**Error 12 — Looking only at `future.isCancelled()` to conclude the worker stopped.** Cancellation state and when the worker actually leaves the code can differ.

**Error 13 — Not tracking late-failing tasks.** The caller timed out, yet the worker throws an exception afterward; callbacks, metrics, or a job store are needed to observe final outcomes.

**Error 14 — Marking a job `FAILED` solely because the client closed the connection.** Client timeout is the caller's perspective, not automatic proof the job cannot continue.

**Error 15 — Failing to shut down executors.** Shared pools need lifecycle shutdown; in Spring, declare named executor beans and let the context manage them.

## 15. Safe Timeout Implementation Checklist

- [ ] Identify **whose timeout it is**: HTTP client, server request, `Future.get`, dependency I/O, or business deadline.
- [ ] After `TimeoutException`, **do not assume the task stopped**; retain the handle/job ID and observe status.
- [ ] Decide whether cancellation is permitted and who is authorized to cancel.
- [ ] If requesting cancellation via `Future.cancel(true)`, ensure the task has **cooperative interrupt handling** and timeouts on blocking I/O.
- [ ] If using `CompletableFuture.orTimeout/completeOnTimeout`, remember they manage **completion state**, not stopping the supplier.
- [ ] Configure transactions/commits, HTTP/JDBC/downstream timeouts, and retry policies explicitly.
- [ ] Avoid retrying non-idempotent effects; use idempotency keys and reconciliation.
- [ ] Do not transition a job to `FAILED` or `CANCELLED` merely because the caller timed out waiting.
- [ ] For long tasks, prefer a durable job store + HTTP 202 + status endpoint if the contract requires it.
- [ ] Monitor jobs running past timeout, active workers, queue age, task duration, requested/confirmed cancellations, and success/failure counts.
- [ ] Test with `CountDownLatch` to eliminate random timing; test timeout, `cancel(false)`, `cancel(true)`, interrupt, and shutdown separately.
- [ ] Verify cleanup of thread-locals, resources, and exceptions when a request ends before the background job.

## 16. Self-Check Questions

**Question 1.** `future.get(1, TimeUnit.SECONDS)` throws `TimeoutException`. Is the worker automatically interrupted?

**Answer:** No. The caller stopped waiting for the result within the one-second limit; the worker may still be running or waiting in the queue.

**Question 2.** Immediately after `TimeoutException`, `future.isDone()` returns `true`. Is that a contradiction?

**Answer:** No. The task could have completed right after the timeout instant but before `isDone()` was read. Distinguish the timestamps of the two observations.

**Question 3.** `cancel(true)` returns `true`. Can you conclude external transactions were rolled back?

**Answer:** No. Future-level cancellation does not prove the worker stopped all steps or that the provider/DB undid the effects.

**Question 4.** Why is `CompletableFuture.cancel(true)` not equivalent to `FutureTask.cancel(true)`?

**Answer:** The `CompletableFuture` implementation does not use interrupts to control execution; `mayInterruptIfRunning` has no effect. `FutureTask` can send an interrupt to the runner, though even that is only a cooperative signal.

**Question 5.** Does `cf.orTimeout(500, MILLISECONDS)` guarantee an HTTP call inside the supplier stops after 500 ms?

**Answer:** No. It only completes the CF exceptionally if not done yet; the HTTP call requires the HTTP client's own timeout/cancellation.

**Question 6.** A report job is accepted, the caller times out, and the client immediately retries. What is the biggest risk?

**Answer:** The old job may still be running; the retry may spawn a new job and duplicate side effects. Use idempotency keys, job IDs, and status queries before creating new work.

**Question 7.** If code catches `InterruptedException` inside a worker, what should it do?

**Answer:** Typically clean up resources, respect the cancellation request, propagate the exception or restore the flag with `Thread.currentThread().interrupt()` if it cannot be propagated; do not silently continue business work.

**Question 8.** Is `ExecutorService.invokeAll(tasks, timeout, unit)` identical to calling `get(timeout)` on each Future?

**Answer:** No. Timed `invokeAll` has a rule to cancel unfinished tasks when the deadline expires; `get(timeout)` on a single Future only bounds the caller's wait.

**Question 9.** Once an HTTP response returns “timeout”, does a Spring transaction in the background worker automatically roll back?

**Answer:** Not solely because of the response timeout. The worker's transaction boundary and rollback rules are separate; side effects on external services need reconciliation/compensation mechanisms.

**Question 10.** What evidence is stronger than `future.isCancelled()` when verifying a worker stopped safely?

**Answer:** A status signal updated by the worker after leaving processing/cleanup, or a job store reflecting `CANCELLED` per the defined state machine, along with logs/metrics and side-effect reconciliation.

## Conclusion

**`Future.get(timeout)` limits how long the caller waits for a result; it does not automatically cancel background work.** The caller's `TimeoutException`, `Future.cancel(...)`, and the worker actually stopping are three separate events.

- To **stop waiting**: use `get(timeout)` or an appropriate HTTP timeout mechanism.
- To **request cancellation**: invoke a cancellation API and make the task/operations cooperate with interrupts and deadlines.
- To **know whether a job finished**: use observable results, status, or exceptions.
- To **ensure side effects are neither lost nor duplicated**: use a job store, idempotency, transaction boundaries, and business-level reconciliation.

Do not turn one thread's timeout into a claim that the work, transaction, or external effects disappeared.

## References

1. Java SE 17 — `Future` (timed get, cancellation, `isDone`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
2. Java SE 17 — `CompletableFuture` (timeouts, `cancel`, execution policies): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
3. Java SE 17 — `ExecutorService` (`invokeAll` timeout, shutdown): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
4. Java SE 17 — `Thread` (interrupt semantics): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
5. Spring Framework — `@Async` and task execution: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
6. Spring Framework — `ThreadPoolTaskExecutor` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
7. HTTP Semantics — status 202 Accepted: https://httpwg.org/specs/rfc9110.html#status.202
