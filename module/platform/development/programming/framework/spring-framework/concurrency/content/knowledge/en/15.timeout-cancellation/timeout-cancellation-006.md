# Handling InterruptedException and Preserving the Interrupt Signal Appropriately

## 1. Why Does InterruptedException Matter in Spring Applications?

When a Spring application runs background work via `TaskExecutor`, `ThreadPoolTaskExecutor`, `@Async`, `TaskScheduler`, or an application-owned `ExecutorService`, it needs a way to ask work to **stop early**: the client no longer needs the result, the job expired, the executor is shutting down, or a workflow needs to cancel remaining branches.

In Java, **interruption** is a cooperative mechanism: one thread can send an **interrupt request** to another thread via `Thread.interrupt()`. Interruptible blocking operations such as `Thread.sleep`, `Object.wait`, `BlockingQueue.take`, `CountDownLatch.await`, or `Future.get` can respond with `InterruptedException`. This is **not** a forced thread-kill command, nor does it mean all I/O, JDBC queries, or CPU tasks stop immediately.

The right handling depends on **who owns the task's lifecycle**:

- If a method **is allowed to throw `InterruptedException`**, typically **propagate** the exception so higher layers decide how to stop and clean up.
- If a method **cannot throw checked exceptions**, typically **restore the interrupt flag** via `Thread.currentThread().interrupt()`, and then **exit the work or transition to a semantic cancellation contract**.
- If the code **genuinely owns** the signal and has a policy that completes cancellation handling, it may intentionally consume the signal; however, the boundary must be crystal clear—never swallow the exception and continue business logic as if nothing happened.

> Practical rule: **never silently swallow `InterruptedException`**. Propagate it if possible; if you must convert it to an unchecked exception or return, restore the interrupt flag before leaving the boundary, unless the code actively handles the entire cancellation protocol and is designed to consume the signal.

This lesson belongs to **Timeouts and Cancellation** of **Spring Framework – concurrency**. The focus is understanding the status bit, `InterruptedException`, and how to write workers/callers that do not accidentally destroy cancellation signals, especially with Spring `@Async` and Futures.

## 2. Interrupt Is a Cooperative Request, Not a Forced Stop

### 2.1. Threads Have an Interrupted Status

Every Java thread has an **interrupted status**. Key APIs:

| API | Meaning | Clears the interrupt flag? |
| --- | --- | --- |
| `someThread.interrupt()` | Requests interrupting the specified thread, typically setting interrupted status or waking a supporting blocking call | Not a flag-reading/clearing API; how a blocking call reacts depends on the API |
| `Thread.currentThread().isInterrupted()` | Reads the **current thread's** flag | **No** |
| `someThread.isInterrupted()` | Reads that thread's flag | **No** |
| `Thread.interrupted()` | Reads the **current thread's** flag and **clears that status** | **Yes** |
| `Thread.sleep(...)`, `Object.wait(...)`, `CountDownLatch.await()` | When interrupted while waiting, typically throw `InterruptedException` | **Yes**, they clear the flag when throwing |

Carefully distinguish two easily confused calls:

~~~java
boolean peek = Thread.currentThread().isInterrupted();
// Observes only, keeps the status.

boolean consume = Thread.interrupted();
// Observes and clears the current thread's interrupted status.
~~~

These are two **illustrative snippets**. `Thread.interrupted()` is a **static** method despite looking like `isInterrupted()`; calling it accidentally inside a helper method can erase a cancellation signal that outer layers need to observe.

### 2.2. Why Is the Flag False After Catching InterruptedException?

Example:

~~~java
try {
    Thread.sleep(10_000L);
} catch (InterruptedException ex) {
    System.out.println(Thread.currentThread().isInterrupted());
}
~~~

When `sleep` is interrupted and throws `InterruptedException`, the thread's status has already been **cleared per `sleep`'s contract**. Therefore, in the typical case, `isInterrupted()` inside `catch` prints `false`—which does not mean no interrupt request occurred earlier.

This is where bugs arise:

~~~java
try {
    queue.take();
} catch (InterruptedException ex) {
    // Only logs and continues the loop — the signal was cleared!
}
~~~

The snippet above requires an appropriate `queue` and must not be copied as a production pattern. If the worker continues its loop without telling anyone, a shutdown/cancel request can be **ignored**. Operators observe the job still running despite having sent an interrupt request.

## 3. Three Strategies for Handling InterruptedException

### 3.1. Strategy A: Propagate the Exception If the Contract Allows

If a method declares `throws InterruptedException`, the clearest approach is usually **not catching it** so it propagates upward:

~~~java
public JobResult waitForData(BlockingQueue<JobResult> queue)
        throws InterruptedException {
    return queue.take();
}
~~~

This is a valid method inside a class with `BlockingQueue` and `JobResult` imported/declared. It is not a standalone runnable program. The calling layer, which knows whether to cancel the workflow, will receive `InterruptedException`.

If resources need cleanup, use `finally` or `try-with-resources`:

~~~java
public void runInterruptibly(BlockingQueue<String> queue)
        throws InterruptedException {
    openResource();
    try {
        String item = queue.take();
        process(item);
    } finally {
        closeResource();
    }
}
~~~

This illustrative snippet requires `openResource`, `process`, and `closeResource`. When `queue.take()` throws `InterruptedException`, control enters `finally` and then propagates the exception, unless `closeResource()` throws another error. Production code should decide how cleanup failures are prioritized/logged and may use `try-with-resources` to preserve suppressed exceptions.

**When propagating `InterruptedException` cleanly per contract, you normally do not need to restore the flag in that same layer.** The exception itself is an explicit signal to the caller; the upper layer is responsible for not dropping it. If a layer wraps it into another exception, consider restoring the interrupt status before crossing that boundary.

### 3.2. Strategy B: Cannot Throw Checked Exception — Restore Then Exit

`Runnable.run()` does not declare `throws InterruptedException`. When it needs `sleep`, `take`, or `await`, the standard choice is:

~~~java
@Override
public void run() {
    try {
        processNextItem();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return; // Stop this Runnable's lifecycle; do not continue processing the job.
    }
}
~~~

This is an **illustrative snippet**: `processNextItem()` must be defined as capable of throwing `InterruptedException`. If logging or reporting job cancellation is needed, do so without breaking the interrupt contract.

If you want to translate into an unchecked error so a supervisor/caller sees failure:

~~~java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Job interrupted", ex);
}
~~~

Requires `blockingOperation()` to be defined. **Both actions have distinct roles**: restoring the flag avoids losing the thread's signal, and throwing the exception communicates the task outcome to supervision mechanisms. Only throwing `new RuntimeException(ex)` without restoring can leave thread-management layers unaware that the flag was interrupted, even though the cause remains.

### 3.3. Strategy C: Convert Intentionally into a Cancelled Status

At a job orchestration boundary, a contract may explicitly define `JobResult.cancelled(...)` instead of an exception. Even then, you must still **stop further processing** and update status consistently:

~~~java
try {
    waitForExternalSignal();
    return JobResult.completed();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return JobResult.cancelled();
}
~~~

This is a conceptual snippet requiring `JobResult` and `waitForExternalSignal`. Never return `JobResult.completed()` inside `catch`, because the caller would think the operation succeeded. If the method were to run more blocking calls after restoring, it would immediately hit interruption again; therefore **restore and exit the boundary** is usually clearer than restoring and continuing execution.

In frameworks with their own **cancellation protocol**, the thread-owning boundary may choose to consume the signal per documentation after stopping the task and recording state. Application service authors should not arbitrarily assume they own the entire lifecycle of Spring-managed threads.

## 4. Bad Patterns: Swallowing, Looping Forever, or Restoring at the Wrong Time

### 4.1. Swallowing the Exception and Continuing

~~~java
while (running) {
    try {
        String job = queue.take();
        process(job);
    } catch (InterruptedException ignored) {
        // Wrong: ignores the signal and goes back to queue.take().
    }
}
~~~

This is an **intentionally wrong example**, requiring `running`, `queue`, and `process`. With `BlockingQueue.take`, once the exception is thrown, the flag is cleared; the loop can keep waiting indefinitely even when the system needs to shut down.

Fix:

~~~java
while (running) {
    try {
        String job = queue.take();
        process(job);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        break; // Exit the worker loop.
    }
}
~~~

If cleanup must run, wrap the loop in `try/finally`. Do not place another loop below it just to have the worker start pulling work again after breaking.

### 4.2. Restoring the Flag and Continuing to Sleep in a Loop

~~~java
while (true) {
    try {
        Thread.sleep(1000L);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        // Wrong if continuing the loop: the next sleep will be interrupted immediately.
    }
}
~~~

This is an anti-pattern snippet. Restoring the flag **is not a license to keep working**. For many blocking APIs, having the status set causes the very next wait to immediately throw `InterruptedException`, producing a CPU-burning busy loop or log spam.

Fix with `break`, `return`, or propagation, depending on the contract. If continuing because interruption does not mean stopping for a specific API, you need an explicit policy to handle/consume the status—never do this silently inside business tasks.

### 4.3. Using Thread.interrupted() Merely to Check

~~~java
if (Thread.interrupted()) {
    logCancellation();
}
// The signal was just cleared! A later method may no longer see it.
~~~

This is an illustrative snippet. If you only want to **peek** at the status, use `Thread.currentThread().isInterrupted()`. If you use `Thread.interrupted()` to actively consume it—for instance in a status-normalizing loop of a thread-management component—you must know exactly why consuming it is safe.

### 4.4. Catching Exception Too Broadly and Losing Meaning

~~~java
try {
    future.get();
} catch (Exception ex) {
    logFailure(ex);
    return null;
}
~~~

This is an intentionally wrong example. `Future.get()` can report `InterruptedException`, `ExecutionException`, or `CancellationException` with distinct meanings. Catching all of them and returning `null` both swallows interruption and turns failure into a result easily mistaken for success.

Separate the `InterruptedException` branch to preserve the signal, classify `ExecutionException.getCause()` for execution errors, and handle cancellation/timeouts per contract.

## 5. Standalone Java 17 Example: Flag Cleared Then Restored

This demo uses `CountDownLatch` to coordinate threads without relying on random sleeps. It proves:

1. After `await()` is interrupted and throws `InterruptedException`, the flag is normally cleared.
2. `Thread.currentThread().interrupt()` inside `catch` sets the status again.
3. `Thread.currentThread().isInterrupted()` only observes.
4. `Thread.interrupted()` both reads and **clears** the current thread's status.

Create file **`InterruptFlagDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class InterruptFlagDemo {

    public static void main(String[] args) throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch keepBlocked = new CountDownLatch(1);

        AtomicBoolean flagInCatch = new AtomicBoolean(true);
        AtomicBoolean flagAfterRestore = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            entered.countDown();
            try {
                keepBlocked.await();
            } catch (InterruptedException ex) {
                // await cleared the interrupted status before throwing.
                flagInCatch.set(Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                flagAfterRestore.set(
                        Thread.currentThread().isInterrupted());
            }
        }, "interruptible-worker");

        worker.start();
        if (!entered.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Worker did not start");
        }

        // Request interrupt regardless of whether the worker already entered await.
        worker.interrupt();
        worker.join(5000L);
        if (worker.isAlive()) {
            throw new IllegalStateException("Worker did not stop");
        }

        System.out.println("caught flag cleared: " +
                !flagInCatch.get());
        System.out.println("flag restored: " +
                flagAfterRestore.get());

        AtomicBoolean peek = new AtomicBoolean(false);
        AtomicBoolean consume = new AtomicBoolean(false);
        AtomicBoolean afterConsume = new AtomicBoolean(true);

        Thread probe = new Thread(() -> {
            Thread.currentThread().interrupt();
            peek.set(Thread.currentThread().isInterrupted());
            consume.set(Thread.interrupted());
            afterConsume.set(Thread.currentThread().isInterrupted());
        }, "flag-probe");

        probe.start();
        probe.join(5000L);
        if (probe.isAlive()) {
            throw new IllegalStateException("Probe did not stop");
        }

        System.out.println("isInterrupted observes: " + peek.get());
        System.out.println("Thread.interrupted observes: " +
                consume.get());
        System.out.println("Thread.interrupted clears: " +
                !afterConsume.get());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac InterruptFlagDemo.java
java InterruptFlagDemo
~~~

**Five lines of stdout printed by the program during normal execution:**

~~~text
caught flag cleared: true
flag restored: true
isInterrupted observes: true
Thread.interrupted observes: true
Thread.interrupted clears: true
~~~

Why the output is deterministic:

- `entered` signals the thread entered the method, after which `main` sends the interruption. If the interrupt arrives before `keepBlocked.await()`, `await` still detects the flag and throws `InterruptedException`. If it arrives while waiting, it wakes the method. Both cases enter `catch`.
- `catch` sees the status cleared by `await`. Calling `interrupt()` on the **current thread** restores the status. The example observes the flag again, then the worker exits.
- A separate `probe` thread sets its own flag, uses `isInterrupted` to observe without clearing, and then uses `Thread.interrupted()` to consume it. We do not touch the `main` thread's interrupt flag.
- Both `join(5000)` calls use finite waits and check `isAlive()` to avoid reporting success if a worker failed to exit as expected.

This is a **semantics** demo, not a recipe for arbitrarily calling `interrupt()` on production threads. In practice, callers use `Future.cancel(true)` or executor lifecycle management rather than holding direct references to worker threads.

## 6. How Does Future.cancel(true) Differ from InterruptedException?

`Future.cancel(boolean mayInterruptIfRunning)` is a **cancellation attempt** on a task:

- `cancel(false)`: attempts to cancel the Future without **requesting an interrupt** on the running thread via the parameter flag; an already-running task may still complete its real work depending on implementation.
- `cancel(true)`: if the task is running and the implementation knows the worker thread, it may **request interrupting the worker** so it exits early. This is **not a guarantee** that the work stopped, nor that downstream I/O rolled back.
- `isCancelled()`: reports cancellation state per the Future contract, **not proof** that all external side effects ceased.
- `isDone()`: true when the Future succeeded, failed, or was cancelled. It does not mean the task committed successfully.
- `get()` on a cancelled Future throws `CancellationException`, not the worker's `InterruptedException`.

**Do not confuse the two threads**:

~~~text
Caller / request thread                      Worker thread
-----------------------                      ----------------------
future.cancel(true)  --------------------->  interrupt attempt
                                             |
                                             +-- sleep / await / take
                                                    |
                                                    +-- InterruptedException
                                                    +-- catch, cleanup,
                                                        propagate/restore

caller's future.get() may throw:
    - CancellationException if the Future was cancelled;
    - InterruptedException if the CALLER ITSELF was interrupted while waiting;
    - ExecutionException if the computation failed with an error (not cancelled).
~~~

`InterruptedException` inside the worker method and `InterruptedException` on the caller waiting in `Future.get()` are **two events on two different threads**. Restoring the flag must happen on **the thread that just caught the exception**, not on another thread.

### 6.1. CompletableFuture.cancel(boolean) Does Not Guarantee Interrupting the Worker

JDK's `CompletableFuture` has distinct semantics: the `mayInterruptIfRunning` parameter of `CompletableFuture.cancel(boolean)` **is not used to control worker execution**. It primarily completes the Future in a cancelled state and notifies dependent stages. Therefore **do not infer** that `someCompletableFuture.cancel(true)` will interrupt actual running I/O or threads.

In Spring `@Async`, the returned Future type and how Spring/the Executor construct the handle affect cancellation. `@Async` returning `Future<T>` from an executor supporting cancellation may allow interrupt requests; `CompletableFuture<T>` and composed stages must not be mistaken for a guaranteed “kill task” button. **Check the specific API/runtime and test cancellation**, rather than relying solely on variable types or method names.

If a long job must be stoppable, consider designing a dedicated **cancellation token**/business flag with periodic checkpoints, explicit deadlines, and I/O operations with timeouts. Use interruption as one cooperative signal, not the sole guarantee.

### 6.2. Wait Timeout Is Not a Cancel Command

~~~java
try {
    return future.get(3, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    // Caller waited past timeout; job may still be running.
    boolean requested = future.cancel(true);
    throw new TaskTimeoutException(requested, ex);
}
~~~

This is an illustrative snippet requiring `future`, imports, and application `TaskTimeoutException`. `get(timeout)` throwing `TimeoutException` only states **the caller waited past the deadline**; whether to call `cancel(true)` is a **business decision**. Not every timeout should cancel the job—for example, a background report allowed to continue while the client polls status.

## 7. Worker Loops: Cooperative Shutdown and Cleanup

A loop-based worker commonly waits on a `BlockingQueue`. Here is a proper interruption design when **the worker is owned by the application**:

~~~java
public void consume(BlockingQueue<Job> queue)
        throws InterruptedException {
    while (!Thread.currentThread().isInterrupted()) {
        Job job = queue.take();
        process(job);
    }
}
~~~

This illustrative snippet requires type `Job` and `process(Job)`. If `queue.take()` is interrupted, it throws `InterruptedException` and the method propagates it instead of swallowing it. If `process` is non-interruptible, the stop request may only be observed after `process` returns.

A `Runnable` cannot declare `throws InterruptedException`, so the equivalent version is:

~~~java
public final class QueueConsumer implements Runnable {
    private final BlockingQueue<String> queue;

    public QueueConsumer(BlockingQueue<String> queue) {
        this.queue = queue;
    }

    @Override
    public void run() {
        try {
            while (!Thread.currentThread().isInterrupted()) {
                String message = queue.take();
                handle(message);
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        } finally {
            releaseOwnedResources();
        }
    }

    private void handle(String message) {
        // Handle one message. Real implementation needs appropriate timeout/retry.
    }

    private void releaseOwnedResources() {
        // Close resources genuinely owned by this consumer.
    }
}
~~~

This is an **illustrative class** requiring importing `BlockingQueue`; it compiles once that import is added, though it has no standalone `main()`. When `take` throws, `catch` restores the flag, `finally` cleans up, and `run()` exits. This avoids pulling further work after a stop was requested.

**Note on Spring-managed executors:** when a thread belongs to a Spring-managed `ThreadPoolTaskExecutor`, an application task **does not own the entire lifecycle of the worker thread**. The task should finish early upon receiving an interrupt request and let the executor decide whether to reuse or replace the worker. Do not use `Thread.stop()`, mutate internal worker state, or try to shut down the whole executor from inside a task that does not own it.

## 8. Complete Spring Framework Example: Future.cancel(true) and @Async Worker

This demo shows an observable cancellation path with a **`Future<T>` returned from an `@Async` method** and a Spring-managed `ThreadPoolTaskExecutor` bean. It uses `CountDownLatch` to confirm the task actually started before the caller requests cancellation. The worker waits on a latch that is never released so it can react via `InterruptedException`.

**Environment:** Java 17+, Spring Framework 6.1.14, Gradle 8.5+. This is a CLI application; Spring Boot is not needed.

### 8.1. Structure

~~~text
spring-interrupt-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SpringInterruptDemo.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-interrupt-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
}

application {
    mainClass = 'demo.SpringInterruptDemo'
}
~~~

**src/main/java/demo/SpringInterruptDemo.java**

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class SpringInterruptDemo {

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            CancelWorker worker = context.getBean(CancelWorker.class);
            CountDownLatch started = new CountDownLatch(1);
            CompletableFuture<Boolean> observed = new CompletableFuture<>();

            Future<String> handle = worker.runInterruptibly(
                    started, observed);

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            // With ThreadPoolTaskExecutor's Future in this configuration,
            // cancel(true) attempts to send interruption to the worker.
            boolean cancellationAccepted = handle.cancel(true);

            // Future cancellation is not proof all cleanup finished;
            // use a separate observer to know the worker entered catch.
            boolean workerRestored = observed.get(5, TimeUnit.SECONDS);

            System.out.println("cancel accepted: " +
                    cancellationAccepted);
            System.out.println("worker restored flag: " +
                    workerRestored);
            System.out.println("handle is cancelled: " +
                    handle.isCancelled());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {

        @Bean("workerExecutor")
        public ThreadPoolTaskExecutor workerExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(4);
            executor.setThreadNamePrefix("cancel-worker-");
            return executor;
        }

        @Bean
        public CancelWorker cancelWorker() {
            return new CancelWorker();
        }
    }

    public static class CancelWorker {

        @Async("workerExecutor")
        public Future<String> runInterruptibly(
                CountDownLatch started,
                CompletableFuture<Boolean> observed) {

            CountDownLatch neverReleased = new CountDownLatch(1);
            started.countDown();

            try {
                neverReleased.await();
                return CompletableFuture.completedFuture("unexpected");
            } catch (InterruptedException ex) {
                // 'await' cleared the flag.
                Thread.currentThread().interrupt();
                observed.complete(
                        Thread.currentThread().isInterrupted());

                // Do not continue processing the job after interruption.
                throw new IllegalStateException("Job interrupted", ex);
            }
        }
    }
}
~~~

**Run** from the `spring-interrupt-demo` directory:

~~~bash
gradle run
~~~

If the project includes Gradle Wrapper, use `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows.

**Program stdout when `Future.cancel(true)` is supported by Spring/`ThreadPoolTaskExecutor` as expected and both wait operations do not time out:**

~~~text
cancel accepted: true
worker restored flag: true
handle is cancelled: true
~~~

This example **tests a specific configuration**, not a guarantee that every `Future.cancel(true)` or `CompletableFuture.cancel(true)` in every runtime can interrupt the worker. If the implementation does not interrupt the worker, `observed.get(timeout)` can time out instead of printing the success lines; in practice, you need fallbacks and shutdown policies. Spring/Gradle may print additional logs alongside the program's three lines.

### 8.2. What the Demo Proves and Does Not Prove

- `@EnableAsync` enables annotation processing in the context. `CancelWorker` is registered as a `@Bean`; the caller retrieves it from `ApplicationContext`, so `@Async("workerExecutor")` goes through the proxy.
- The `@Async` method returns `Future<String>`; the worker portion runs on the pool prefixed `cancel-worker-`.
- `started` ensures the method entered the worker before the caller cancels; no `Thread.sleep` needed to guess timing.
- `handle.cancel(true)` requests cancelling the Future. Along `ThreadPoolTaskExecutor`'s interrupt-supporting execution path, it sends an interrupt to the worker waiting on `neverReleased.await()`.
- `InterruptedException` thrown by `await()` **clears the flag**, so the worker calls `interrupt()` to restore it, records `true` via the observer, and exits with an exception.
- `handle.isCancelled()` describes **the Future on the caller**, while `observed` shows the worker actually handled the interruption. Do not substitute Future state for proof that all side effects were cleaned up.
- Never promise transaction rollback or that a database driver stopped I/O merely because the worker received an interrupt; cancellation remains a cooperative protocol.

If your goal is solely observing the status bit, the demo in section 5 is independent of Spring and has fewer runtime variables. The demo in section 8 shows that even with a Spring proxy, **interruption remains a Java rule**, with no “Spring-specific interrupt flag”.

## 9. Spring @Async: Distinguishing Execution Errors from Caller Wait Errors

When a caller executes:

~~~java
Future<Report> future = reportWorker.generateAsync();
Report report = future.get();
~~~

This is an illustrative snippet requiring the bean and `Report` type. There are at least three failure paths:

1. **Worker is interrupted:** a method in `sleep`/`await` can throw `InterruptedException` inside **the worker**. The worker handles it by propagating or restoring/translating per contract.
2. **Caller is interrupted while waiting in `future.get()`:** `get()` itself on **the caller thread** throws `InterruptedException`. The catch on the caller should restore the flag if not propagating the checked exception, and decide whether to request cancelling the worker.
3. **Worker throws an error and the Future completes exceptionally:** `future.get()` typically throws `ExecutionException` wrapping the cause. If the Future was cancelled, `get()` throws `CancellationException` instead of `ExecutionException`.

Do not classify every `InterruptedException` as “the worker was cancelled”; identify **which thread** was interrupted and **which operation** was waiting.

### 9.1. Caller Waiting on Future Gets Interrupted

~~~java
try {
    return future.get(5, TimeUnit.SECONDS);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();

    // This is a business decision, not mandatory behavior:
    future.cancel(true);

    throw new JobWaitInterruptedException(ex);
} catch (TimeoutException ex) {
    throw new JobWaitTimeoutException(ex);
} catch (ExecutionException ex) {
    throw mapExecutionFailure(ex.getCause());
} catch (CancellationException ex) {
    throw new JobWasCancelledException(ex);
}
~~~

This is an **illustrative code snippet**, requiring declaring `future`, application exceptions, and mapping. If you want the worker to continue even when the caller request stops waiting, do not automatically call `future.cancel(true)`. If a task must produce a result for a job store/broker, an interrupted caller does not necessarily have authority to stop the job.

### 9.2. @Async void and Exception Handlers

An `@Async void` method returns no Future to the caller. If an `InterruptedException` is caught and converted into an exception in the worker, that error cannot automatically be thrown synchronously to the caller. Spring provides `AsyncUncaughtExceptionHandler` to observe exceptions from asynchronous `void` methods.

~~~java
@Async("workerExecutor")
public void doWork() {
    try {
        blockingStep();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Work interrupted", ex);
    }
}
~~~

This is an illustrative method inside a Spring-managed service; it requires imports and `blockingStep`. For work with an explicit cancellation contract, you can record a cancelled status and return; throwing an error on every normal cancellation is not mandatory. What must be avoided is losing the signal and continuing to create side effects.

## 10. When Cannot Interruption Be Used to Stop Quickly?

### 10.1. CPU-Bound Loops Must Check Explicitly

A computational loop containing no blocking calls can keep running even when the flag is set:

~~~java
public long calculate(long max) {
    long total = 0;
    for (long i = 0; i < max; i++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new CancellationException(
                    "Calculation interrupted");
        }
        total += (i % 17);
    }
    return total;
}
~~~

This is an illustrative Java method requiring importing `CancellationException`. `isInterrupted()` **does not clear the flag**, making it suitable for cooperative checks. In huge loops, checking every iteration can introduce overhead; you can check periodically, e.g., every few thousand iterations, with acceptable reaction latency.

A `CancellationException` thrown by application code inside the worker does not mean the Future transitioned to cancelled via `Future.cancel`; it may be recorded as a computation failure depending on the Future type. If the business logic needs to distinguish cancellation from failure, design an explicit status/job contract rather than relying solely on exception names.

### 10.2. Some I/O Does Not React to Interruption as Expected

- `BlockingQueue.take()`, `CountDownLatch.await()`, and `Thread.sleep()` normally react to interrupts with `InterruptedException`.
- An `InterruptibleChannel` may close the channel and throw `ClosedByInterruptException` rather than `InterruptedException`.
- Different JDBC drivers, HTTP clients, socket APIs, filesystem I/O, or native calls have **different interrupt contracts**; they may not stop immediately, may ignore interrupts, or may throw custom errors.
- Traditional `synchronized` lock acquisition is not equivalent to `Lock.lockInterruptibly()`; if you need interruptible lock waiting, choose the appropriate primitive and handle `InterruptedException`.
- Never use `Thread.stop()` because it is unsafe and deprecated.

**I/O-layer timeouts remain essential.** Cancellation signals do not replace socket read timeouts, connect timeouts, SQL query timeouts, deadlines, or bounded resources. If an API only provides non-interruptible blocking I/O, code may have to wait for I/O to finish before running cleanup; design bounded timeouts and shutdowns instead of assuming `cancel(true)` cancels instantaneously.

### 10.3. Interruption Does Not Automatically Roll Back Transactions

With Spring `@Transactional` running on a worker thread, interruption may stop the method or throw an exception; **transaction behavior** depends on how the exception propagates through the proxy, rollback rules, and database operation state. If the method catches `InterruptedException` and returns normally, the transaction can **commit** even though part of the work never finished.

When a transaction must roll back, define an explicit rollback contract—typically via an appropriate exception propagated to the transaction interceptor or marking the transaction status rollback-only. Never assume “thread was interrupted” automatically rolls back JDBC. If the task has side effects outside the database (sending email, calling APIs), interruption does not undo them either; design compensation/idempotency where needed.

## 11. Executor Shutdown, Job Cancellation, and Spring Lifecycle

In Spring, `ThreadPoolTaskExecutor` is a lifecycle-managed bean. During context shutdown, Spring and the executor coordinate running tasks, queued tasks, and termination wait timeouts per configuration. Do not assume every shutdown immediately interrupts every task or always lets every task run to completion: behavior depends on configuration, state, and version.

Related JDK operations:

| Operation | General goal | Note |
| --- | --- | --- |
| `ExecutorService.shutdown()` | Stops accepting new tasks, normally lets accepted tasks continue | **Not** a direct interrupt request to all running tasks |
| `ExecutorService.shutdownNow()` | Attempts to stop running tasks (usually via interrupt) and returns unstarted queued tasks | Best-effort; does not promise every worker exited |
| `Future.cancel(true)` | Attempts to cancel one task; may interrupt worker if supported by implementation | Does not automatically cancel downstream side effects |
| `Future.cancel(false)` | Attempts to transition Future to cancelled without requesting running-task interrupt via flag | Execution behavior depends on Future type |
| `awaitTermination(timeout, unit)` | Waits for executor workers to finish up to the limit | Can throw `InterruptedException` on **the waiting thread** |

Example of a service owning its own `ExecutorService`:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(2);
try {
    // Submit and manage tasks belonging to this service.
} finally {
    pool.shutdown();
    try {
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            pool.shutdownNow();
        }
    } catch (InterruptedException ex) {
        pool.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

This is an **illustrative snippet**; it requires importing `ExecutorService`, `Executors`, `TimeUnit`, and defining which tasks the business permits cancelling. In the `catch` branch, **the thread awaiting termination itself** was interrupted: the code requests `shutdownNow` and then **restores the interrupt flag** before exiting the boundary, rather than swallowing it and waiting indefinitely.

With a **Spring-managed executor bean**, you normally let Spring manage shutdown rather than having a service call `shutdownNow()` from inside a task. The application still needs to define deadlines, which jobs must finish, job recovery mechanisms, and overall shutdown coordination.

## 12. Cancellation, CompletableFuture, and Wait Points

`CompletableFuture.join()` does not declare `InterruptedException` like `Future.get()`. It can block until the stage completes and typically throws `CompletionException` when the stage fails. **Do not conclude `join()` is non-blocking** or has a mechanism to stop workers when the caller is interrupted.

If a caller in `get()` is interrupted, valid strategies are:

- **Propagate `InterruptedException`** when the signature/contract permits.
- **Restore and throw unchecked cancellation** if the API cannot propagate checked exceptions.
- **Restore and return cancelled status** if business logic allows, without returning fake success.
- **Decide separately** whether to call `future.cancel(true)` to request stopping the worker; caller interruption and worker cancellation are not the same thing.

With `CompletableFuture`, a pipeline can span multiple stages across multiple executors. Cancelling the final Future does not guarantee all upstream stages and external requests stopped. If a workflow requires cancelling across multiple operations, you need tracked handles, cancellation tokens, downstream timeouts, and an explicit completion-status protocol.

### 12.1. Timeout and Interruption Are Two Different Events

| Event | Typical signal | Auto-cancels worker? |
| --- | --- | --- |
| Caller waits past `get(timeout)` | `TimeoutException` | No |
| Caller interrupted during `get()` | `InterruptedException` on caller | Not automatically in the sense of interrupting worker |
| Worker interrupted in `sleep/await/take` | `InterruptedException` on worker, flag usually cleared | Worker must handle cooperatively |
| `Future.cancel(true)` succeeds in state | Future cancelled; `get()` may throw `CancellationException` | May attempt interrupt; no guarantee all work stopped |
| `CompletableFuture.orTimeout(...)` expires | Future exceptional with `TimeoutException` | Does not guarantee interrupting computation |
| Thread awaiting `awaitTermination` interrupted | `InterruptedException` on waiting thread | Does not decide shutdown policy automatically |

A timeout API usually means “stop **waiting** after the deadline”, not “stop all processing and roll back”. Contracts must make this distinction clear.

## 13. Special Notes for ThreadPoolTaskExecutor, @Scheduled, and Event Listeners

### 13.1. @Async Methods Must Not Ignore Interruption

~~~java
@Service
public class ImportWorker {
    @Async("importExecutor")
    public CompletableFuture<String> importAsync() {
        try {
            return CompletableFuture.completedFuture(
                    fetchAndImportInterruptibly());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return CompletableFuture.failedFuture(ex);
        }
    }
}
~~~

This is an **illustrative class**, requiring Spring annotation imports, `CompletableFuture`, `fetchAndImportInterruptibly()`, and the `importExecutor` bean. `@Async` only takes effect through a Spring-managed proxy when `@EnableAsync` is active; self-invocation `this.importAsync()` normally bypasses the proxy.

Returning `failedFuture(ex)` reports the error to the caller via the Future, while restoring the flag avoids **silently consuming the signal on the thread**. Do not use `failedFuture` to imply the caller cancelled the Future; a failed stage and a cancelled stage can have different semantics.

### 13.2. Scheduled Tasks and Callbacks in Message/Event Processing

An `@Scheduled` callback must decide whether an interrupted run should be marked failed, aborted, or retried on the next scheduled trigger. **Do not put a catch-all `catch (Exception)` and keep looping infinitely** inside a scheduler thread after cancellation was requested. If the scheduler uses a single thread, blocking too long can delay other triggers.

For message consumers, when a task is interrupted **before completing successfully**, do not automatically ACK the message if the delivery contract requires ACK only after success. Depending on the system, you may need NACK/requeue/durable retry or dedicated job status. The interrupt signal does not undo an already-sent ACK, and cleanup code may need to guarantee idempotency.

For Spring application event listeners placed on an async executor, the caller normally does not receive listener exceptions synchronously. You must monitor errors, decide retries, and avoid promising exactly-once delivery with only an in-memory executor.

### 13.3. Spring Singleton Beans and ThreadLocal

Worker `@Service` beans are singletons by default; multiple tasks may invoke the same instance concurrently. Interruption does not make mutable fields thread-safe. Prefer stateless workers and immutable DTOs, and avoid storing `currentJobId` or request-specific state on shared fields.

Caller `ThreadLocal`/MDC/security context/transactions do not automatically travel across `@Async`. If context propagation is needed, use an appropriate mechanism or pass data explicitly via parameters, along with cleanup. Never use the interrupt flag as cross-request business data; it belongs to **the current thread**.

## 14. Observing and Testing Controlled Cancellation

### 14.1. Measure Separate States

In production systems, distinguish:

- **Cancellation requested**: who requested cancellation, for what reason, and under what deadline.
- **Future cancelled**: the handle state observed by the caller.
- **Worker observed cancellation**: the worker saw the flag/exception/token.
- **Worker stopped**: the worker stopped executing code.
- **Cleanup completed**: resources were closed and job status persisted.
- **Downstream side effects**: how far transactions, emails, payments, and message ACKs actually progressed.

Do not collapse these states into `future.cancel(true) == true` and conclude “everything stopped”. Especially for work that must survive restarts, you may need a job store, outbox, or broker to durably persist cancellation state and retries.

### 14.2. Testing Without Relying on Random Thread.sleep

Use `CountDownLatch` or `Phaser` to control state:

1. Worker signals it has started.
2. Caller sends `interrupt` or `Future.cancel(true)`.
3. Worker observes `InterruptedException` at a blocking point.
4. Test verifies inside `catch` that the flag was cleared, and after restoring, the flag becomes `true`.
5. Test verifies the worker **does not continue** executing subsequent business steps.
6. Verify `Future.isCancelled()` and worker cleanup separately; do not treat them as one event.
7. Always place timeouts on waits in tests and clean up in `finally` whenever possible.
8. Verify `cancel(false)` is not mistaken for interrupting a running task.
9. Test `CompletableFuture.cancel(true)` against its specific contract, avoiding assumptions from `FutureTask`.
10. Test caller interruption during `get()` and flag-restoration logic on the caller.
11. Verify exception mapping does not swallow `InterruptedException` when catching `Exception`.
12. Test shutdown and retry/idempotency of side-effecting jobs.

### 14.3. Warning Signs in Production Code

- Repeated `InterruptedException` log entries without the worker ever terminating.
- Thread dumps showing workers still alive after shutdown requests, especially inside loops catching and swallowing exceptions.
- Requests time out while background tasks keep executing unexpected side effects.
- `Future.cancel(true)` returns true, yet job status never transitions or downstream keeps processing.
- Code calls `Thread.interrupted()` in a “peek” helper and accidentally loses the flag.
- A method restores the flag and immediately calls another blocking API, throwing again in a tight busy loop.
- `@Async` is present, yet self-invocation runs it on the caller thread; `InterruptedException` appears on an unexpected thread.
- A catch-all logs and returns `null`, causing the workflow to treat cancelled work as success.
- A worker bean is shutting down while a producer keeps submitting tasks; rejections get mistaken for interruption.

When seeing these symptoms, investigate **which thread received the signal, which API threw the exception, which caller owns the Future, and what the job contract requires**.

## 15. Common Reasoning Errors

| Misconception | Truth |
| --- | --- |
| “`interrupt()` always kills the thread immediately.” | It is a cooperative request and does not automatically terminate all work |
| “When catching `InterruptedException`, the flag is still true.” | Many blocking APIs **clear the flag before throwing**, so decide whether to propagate or restore |
| “`Thread.interrupted()` is the same as `isInterrupted()`.” | `Thread.interrupted()` reads and then clears **the current thread's flag** |
| “Always restore and keep looping in `while(true)`.” | Can cause blocking APIs to throw repeatedly; usually stop or propagate |
| “Throwing `new RuntimeException(ex)` alone is enough.” | If you cannot propagate the checked signal, you usually also need to restore the flag |
| “Always restore even when declaring `throws InterruptedException`.” | When propagating the checked exception per contract, restoring in that layer is usually unnecessary |
| “`future.cancel(true)` guarantees the worker stops.” | Best-effort; implementation and blocking/CPU operations decide |
| “`CompletableFuture.cancel(true)` definitely interrupts.” | JDK `CompletableFuture` **does not use** the parameter to control workers |
| “`get(timeout)` auto-cancels the job on timeout.” | It only limits how long the caller waits |
| “Caller `get()` throwing `InterruptedException` means the worker was interrupted.” | It may be **the caller thread** that was interrupted while waiting |
| “A cancelled Future means the transaction rolled back.” | Cancellation state and transactions/side effects are separate contracts |
| “`ThreadPoolTaskExecutor` automatically makes all I/O interruptible.” | No; depends on each layer's APIs, drivers, and timeouts |
| “`catch (Exception)` and logging is enough.” | Can swallow the interrupt signal, breaking shutdown |
| “`Thread.stop()` guarantees clean cancellation.” | Unsafe API; never use it to solve task cancellation |

## 16. Code Review Checklist for Spring Concurrency

- [ ] Methods that can **propagate `InterruptedException`** do not swallow the signal.
- [ ] Methods that cannot throw checked exceptions **restore the flag and exit**, or apply an explicit cancellation protocol.
- [ ] `Thread.interrupted()` is never used just to **peek**, accidentally clearing the status.
- [ ] Infinite loops never continue after restoring the flag without a documented reason.
- [ ] `Future.cancel(true)` is treated as a **cancellation attempt**, not confirmation that the worker stopped/cleaned up.
- [ ] `CompletableFuture.cancel(true)` is not expected to automatically interrupt all upstream work.
- [ ] Timeouts are configured on I/O and downstream calls, not just on caller waits.
- [ ] Caller interruption during `Future.get()` is distinguished from worker interruption inside blocking tasks.
- [ ] `TimeoutException`, `ExecutionException`, `CancellationException`, and rejections are handled separately.
- [ ] `@Async` is invoked via Spring-managed proxies; executors are appropriate and resource-bounded.
- [ ] Executor shutdown belongs to the owning component; tasks do not shut down shared pools without ownership.
- [ ] Cleanup and appropriate job status/ACK recording occur if an operation stopped mid-way.
- [ ] Cancellation tests use latches, including races between completion and cancellation.
- [ ] Side effects have idempotency or compensation when business logic requires it.
- [ ] Interruption is not treated as a security/authorization mechanism or automatic transaction rollback.

## 17. Self-Check Questions

1. **Does interruption kill a thread immediately?** No; it requests cooperation and depends on observing code/operations.
2. **After `sleep` throws `InterruptedException`, is the flag normally still true?** No. `Thread.sleep` clears the flag when throwing on interrupt.
3. **If a method declares `throws InterruptedException`, what should it usually do?** Propagate it so upper layers handle it, while cleaning up in `finally` if needed.
4. **If `Runnable.run()` catches `InterruptedException`, what should it do?** Typically restore the flag, stop the task, and clean up; or transition to a designed cancelled state.
5. **Why is plain `catch (InterruptedException e) { }` dangerous?** It loses the signal and can keep running after shutdown/cancel.
6. **How does `Thread.interrupted()` differ from `isInterrupted()`?** The first static method reads and clears the current thread's flag; the second only reads it.
7. **Should you restore and continue sleeping inside `while(true)`?** Usually no. The next sleep can throw immediately, creating a busy loop.
8. **Does `cancel(true)` on a Future guarantee interrupting the worker?** No; it only attempts to send a request if the implementation supports it and the worker is still running.
9. **Does `CompletableFuture.cancel(true)` guarantee interrupting the task?** No. The parameter does not control computation under the JDK contract.
10. **Does `get(timeout)` timing out mean the job has stopped?** Not yet. That is the caller's **wait** timeout.
11. **Caller `get()` throws `InterruptedException`: which thread's flag must be restored?** **The caller thread** catching it, not the worker.
12. **For a non-blocking CPU loop, how do you respond to cancellation?** Check `isInterrupted()` or a cancellation token at reasonable points.
13. **Does an `@Async` singleton worker getting interrupted automatically roll back the database?** No; rollback depends on transaction boundaries and exceptions crossing the interceptor.
14. **Why must worker cleanup be observed separately from `Future.isCancelled`?** Because Future state does not prove side effects have stopped.
15. **Should you call `shutdownNow()` inside a regular `@Async` task?** No if the task does not own the executor; let the owner/context manage lifecycle.
16. **Should a message handler interrupted mid-way always ACK?** No; decide ACK/NACK based on the delivery contract and processing state.
17. **With `Thread.interrupted()`, what if the signal must be preserved for downstream layers?** Do not call it just to peek; if already consumed and the contract requires propagation, restore status appropriately.
18. **Are there cases where actively consuming interruption is valid?** Yes, when a component owning the cancellation protocol has fully handled the signal and the contract allows it; never do it covertly in business tasks.

**Conclusion:** `InterruptedException` is Java's **cooperative signal** when a thread is asked to stop while waiting. In Spring concurrency, the safe rule is **propagate if possible; otherwise, restore the flag via `Thread.currentThread().interrupt()` and stop or report the appropriate cancelled status**. At the same time, distinguish cancelling a `Future` from the worker actually stopping, wait timeouts from work timeouts, and operations that interruption alone cannot stop.

### Official References

- [Java 17 — Thread (interrupt, interrupted, isInterrupted)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html)
- [Java 17 — InterruptedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InterruptedException.html)
- [Java 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework 6.1 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.1 — @Async](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Async.html)
