# Submitting a Resultless Runnable with execute()

## 1. The Problem: Handing Off Work to an Executor

In a Spring application, a thread handling a request may need to delegate a unit of work to another component: writing business logs, updating a counter, dispatching an event, cleaning up temporary data, or triggering a background operation. When the work **does not need to return a value to the caller**, Java provides `Runnable` and the `execute(Runnable)` method on `Executor`; Spring provides the same approach through `TaskExecutor`.

We need to distinguish two responsibilities:

1. **The task (`Runnable`)** describes what must be performed.
2. **The executor (`Executor` or `TaskExecutor`)** decides where, when, and with what resource policy to execute the task.

Example of the caller's intent:

```java
Runnable task = () -> System.out.println("Event processed");
executor.execute(task);
```

This is an **illustrative code snippet**, assuming `executor` has already been declared and initialized. The `execute` call returns `void`. The caller does not receive a return value from `run()`, has no `Future` to wait on, and does not automatically receive a success/failure notification after the task runs.

One particularly important point: **`execute()` does not mean "always runs on a new thread"**. With a direct executor, `run()` may be invoked immediately on the submitting thread; with a thread pool, the task typically runs on a worker thread after being accepted, possibly after spending time in a queue. Therefore, using `execute` only expresses the *work submission contract*, while asynchronicity depends on the **executor implementation**.

### Learning Objectives

After this lesson, you will be able to:

- Write a `Runnable` using a lambda, a method reference, or an implementing class.
- Submit tasks with `execute(Runnable)` through Java's `Executor` and Spring's `TaskExecutor`.
- Distinguish between `run()`, `Thread.start()`, `execute()`, and `submit()`.
- Understand that `void` does not mean a task is guaranteed to succeed or execute asynchronously.
- Handle cases where the executor rejects a task; observe errors, completion, and lifecycle through separate mechanisms when needed.
- Integrate the submission pattern into a Spring bean while still controlling worker limits, queues, shared state, and application shutdown.

## 2. The Contract of Runnable and execute()

### 2.1. Runnable Represents a Task That Returns No Value

`Runnable` is a functional interface in `java.lang`:

```java
@FunctionalInterface
public interface Runnable {
    void run();
}
```

The signature `void run()` means calling `run()` does not directly return data. This method also does not declare `throws Exception` for checked exceptions. However, the task can still fail, can throw a `RuntimeException` or `Error`, and can perform side effects such as writing data or sending requests.

Three representations equivalent in purpose:

```java
// Lambda:
Runnable lambda = () -> System.out.println("Working");

// Method reference, placed in a scope that has a logMessage() method:
Runnable reference = this::logMessage;

// Anonymous class:
Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println("Working");
    }
};
```

This snippet **only illustrates declaration styles inside an appropriate class**; `this::logMessage` requires an existing instance method `logMessage()`. In real applications, a lambda is usually concise enough for small tasks; for complex logic, you should put the business logic into a clearly named method or service.

Do not infer from the name `Runnable` that Java has created or started a thread. `Runnable` is merely an object holding behavior until something calls `run()` or hands it to an executor.

### 2.2. Executor Has One Core Method

Java defines:

```java
public interface Executor {
    void execute(Runnable command);
}
```

Spring defines a compatible abstraction:

```java
public interface TaskExecutor extends java.util.concurrent.Executor {
    void execute(Runnable task);
}
```

These are **summarized API signatures**, not the full library source code. In Spring, `TaskExecutor` carries the contract for executing a `Runnable`, throwing `TaskRejectedException` if the task is not accepted. Implementations may execute directly, create a new thread, or reuse workers in a pool.

When calling:

```java
executor.execute(task);
```

- `task` is the work to be done, not a thread name.
- `execute(...)` does **not** return a `Future`, a job ID, a completion status, or a computation result.
- If the executor uses an asynchronous strategy, the call may return very quickly after accepting the task; the work may not have started yet.
- If the executor runs synchronously or applies a policy that makes the caller run the task itself, the call may block until the task finishes running.
- The executor may reject the task when it has been shut down or exceeds its limits; in Spring's `ThreadPoolTaskExecutor` with the default rejection policy, this typically surfaces as `TaskRejectedException`.
- An exception thrown **when calling execute** must be distinguished from a task failure occurring **after the task has been accepted for execution**.

### 2.3. Four Behaviors That Are Not the Same

| Invocation | Who decides the execution thread? | What does the caller receive? | When should it be used? |
|---|---|---|---|
| `task.run()` | The calling thread itself | `void` | When you want to call the task like a normal method |
| `new Thread(task).start()` | The JVM starts the created thread | `void` | When you need low-level management of a specific thread |
| `executor.execute(task)` | The `Executor` implementation | `void` | When you want to decouple task submission from execution policy |
| `executorService.submit(task)` | The `ExecutorService` | `Future<?>` | When you need to track completion, errors, cancellation, or wait |

**Key takeaway of this lesson:** `execute()` hands off a `Runnable` under the simplest contract; it **does not provide a channel to retrieve a completion result**. If the caller truly needs to know whether the task finished or failed, design a signaling mechanism or choose `submit` when appropriate. Do not invent a `Future` in your head and assume `execute` provided one automatically.

## 3. The Path of a Task After execute()

Model when the executor uses a pool:

```text
Submitting thread (caller)
     |
     | creates Runnable
     |
     +--> execute(task)
             |
             v
      Executor / TaskExecutor
             |
             +--> Available suitable worker -> runs run()
             |
             +--> Workers busy -> queued (if capacity remains)
             |
             +--> Cannot accept more -> rejection
             |
             v
       execute() may have already returned to caller
             |
             ... at another point in time ...
             v
           task.run()
             |
             +--> executes successfully
             |
             +--> throws exception
```

Note the word "may": a direct executor has no queue and runs `run()` before `execute()` returns. Java does not require every executor to create a new thread.

`execute` returning normally **only indicates that the executor did not immediately report an error to that call**. It does not guarantee that all side effects inside the task succeeded. With certain `RejectedExecutionHandler` implementations such as `DiscardPolicy`, a task may even be dropped under overload without throwing an exception. Therefore, concluding "the task has been executed" from `execute` returning is only valid when you know the specific executor's policy.

There is no general guarantee that tasks are processed in exact submission order: this depends on the executor, queue structure, number of workers, and scheduling. In a multi-worker pool, the order of starting, finishing, and logging can differ.

## 4. Standalone Java 17 Example: Direct and via Worker Pool

This example demonstrates that the same `execute` call can run on `main` or on a worker thread. `CountDownLatch` makes the printed order predictable without needing to sleep and guess whether the task has finished.

**File `ExecuteRunnableDemo.java`:**

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

public class ExecuteRunnableDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Executor direct = Runnable::run;

        direct.execute(() -> System.out.println(
                "Direct: " + Thread.currentThread().getName()));

        ThreadFactory namedThread = task ->
                new Thread(task, "background-worker");

        ExecutorService pool =
                Executors.newSingleThreadExecutor(namedThread);

        CountDownLatch finished = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                try {
                    System.out.println("In pool: "
                            + Thread.currentThread().getName());
                } finally {
                    finished.countDown();
                }
            });

            finished.await();
            System.out.println("Caller confirmed completion");
        } finally {
            pool.shutdown();
        }
    }
}
```

**Compile and run (JDK 17+):**

```bash
javac ExecuteRunnableDemo.java
java ExecuteRunnableDemo
```

**Deterministic output:**

```text
Direct: main
In pool: background-worker
Caller confirmed completion
```

Explanation:

1. `Executor direct = Runnable::run` creates an executor whose implementation is equivalent to `command.run()`. It runs **immediately on main** and returns once the lambda completes.
2. `Executors.newSingleThreadExecutor(...)` uses a worker created by the factory, named `background-worker`. The code creating the task does not need to know the pool details.
3. `pool.execute(...)` returns `void`. By itself, it does not produce a "success" value.
4. The task calls `finished.countDown()` in `finally`; `finished.await()` only lets the caller proceed after that signal.
5. `pool.shutdown()` is the responsibility of the code that created the pool. It stops accepting new work; `shutdown()` alone is not a command that waits for completion.
6. The first two lines appear before the last line: direct runs first, while the pool task must signal `finished` before main prints the confirmation line.

In the example above, `CountDownLatch` serves as an **explicitly designed completion channel**, not something returned by `execute()`. If the application does not need to wait, the latch can be omitted; however, in that case it cannot claim the task has completed right after `execute`.

**Do not confuse with:**

```java
Runnable task = () -> System.out.println("Running on caller");
task.run();  // A regular method call; does not create a thread.
```

## 5. Spring Integration: Configuring a Bounded TaskExecutor

In Spring Framework, a common choice for an application-managed pool is `ThreadPoolTaskExecutor`. This class implements `TaskExecutor`, is backed by Java's `ThreadPoolExecutor`, and supports configuring worker counts, queue capacity, thread names, and rejection handling.

**File `BackgroundExecutorConfig.java` — a Spring configuration class, without a standalone `main`:**

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class BackgroundExecutorConfig {

    @Bean("backgroundTaskExecutor")
    public ThreadPoolTaskExecutor backgroundTaskExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("background-");

        return executor;
    }
}
```

Analysis:

- `corePoolSize=2`: when needed, the executor creates up to two core workers before preferring the queue.
- `maxPoolSize=4`: limits the maximum number of workers to four. With `ThreadPoolExecutor`, after core workers are busy, work is typically queued first; only when the queue cannot accept more does it consider scaling workers up to max.
- `queueCapacity=32`: limits the maximum to 32 tasks waiting in the pool's queue, **not** 32 currently running tasks.
- `threadNamePrefix` makes logs and thread dumps easier to read.
- Because the bean is managed by Spring, initializing and shutting down the executor follows the `ApplicationContext` lifecycle according to Spring configuration.

The example uses `ThreadPoolTaskExecutor` to teach the submission contract; **the numbers 2/4/32 are purely illustrative**. In production, you must size them according to latency, memory per task, incoming load, downstream capacity, and rejection policy. An overly large queue can cause wait times and retained heap memory to grow dramatically.

### 5.1. Using TaskExecutor in a Service

**File `EventDispatchService.java` — a Spring component requiring Spring dependencies and context:**

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class EventDispatchService {
    private final TaskExecutor executor;
    private final AtomicInteger processed = new AtomicInteger();

    public EventDispatchService(
            @Qualifier("backgroundTaskExecutor")
            TaskExecutor executor) {
        this.executor = executor;
    }

    public void dispatch(String eventId) {
        String id = Objects.requireNonNull(eventId, "eventId");

        executor.execute(() -> {
            // Illustrative work: record that an event has been processed.
            processed.incrementAndGet();
            System.out.println("Processed event: " + id);
        });
    }

    public int processedCount() {
        return processed.get();
    }
}
```

This code illustrates a Spring bean using an executor with **constructor injection**. You do not need `@EnableAsync` just to call `TaskExecutor.execute(...)` directly: `@EnableAsync` is for `@Async` processing.

`dispatch` returns `void` after calling `execute`. If the pool is asynchronous, calling `processedCount()` immediately after `dispatch` **may not yet observe the newly submitted task**. `AtomicInteger` makes incrementing safe when multiple workers update concurrently, but it does not force the task to finish before the caller reads; **data safety** and **waiting for completion** are two different concerns.

`System.out.println(...)` only helps observe the example, and is not a reliable auditing mechanism. If the business requires guaranteeing that events are not lost when the JVM dies, submitting to an in-memory executor is not enough; you need persistent job storage, retry/idempotency handling, and an acknowledgment mechanism suited to the requirements.

### 5.2. A Controller Call Can Return Before the Task

Example controller that only accepts a work submission request:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EventController {
    private final EventDispatchService dispatchService;

    public EventController(EventDispatchService dispatchService) {
        this.dispatchService = dispatchService;
    }

    @PostMapping("/events/{id}/dispatch")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public void dispatch(@PathVariable String id) {
        dispatchService.dispatch(id);
    }
}
```

This is a **Spring Web** component, not standalone Java SE code. This code uses HTTP `202 Accepted` to indicate that the submission operation was performed at the application layer when there is no synchronous error. **202 does not prove that the background task succeeded**, does not guarantee durable persistence, and provides no way to query job status in this example. For a production API that requires job status, you must design a job ID and a separate status store.

If the executor rejects the task and `TaskRejectedException` propagates from `dispatch`, the request should not still return 202. You must handle the exception at the web layer to return an appropriate response, such as 503 or 429 depending on the API contract. Do not swallow the rejection and pretend the work was accepted.

## 6. Not Returning a Result Does Not Mean Error Handling Is Unnecessary

There are two separate points of failure:

### 6.1. Submission Failure: Task Was Not Accepted

`ThreadPoolTaskExecutor` can reject tasks when the pool is shut down or has reached its worker and queue limits. With the default policy, Spring reports `TaskRejectedException` per the `TaskExecutor` contract.

```java
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.TaskRejectedException;

// Snippet placed inside a method with executor and eventId variables:
try {
    executor.execute(() ->
            System.out.println("Processing: " + eventId));
} catch (TaskRejectedException rejected) {
    // Propagate error to the layer authorized to return overload/retry status.
    throw rejected;
}
```

This snippet only illustrates **where synchronous error catching occurs**. Catching and rethrowing is valid if you want to add logging/metrics before propagating the error; if doing nothing else, this `try/catch` block is unnecessary. Do not assume every rejection policy throws an exception: `DiscardPolicy` may drop the task, while `CallerRunsPolicy` may make the submitting thread run the task when the executor is not shut down.

### 6.2. Failure While the Task Is Running: No Future to Retrieve

`Runnable.run()` does not declare checked exceptions, but runtime exceptions can still arise in its body:

```java
executor.execute(() -> {
    throw new IllegalStateException("Unable to process");
});
```

If `executor` is a synchronous executor, the error may be thrown back during the same `execute` call. If `executor` is an asynchronous worker pool, the caller has usually already exited the submission method; there is no `Future.get()` to report this error to the caller. With default `ThreadPoolExecutor.execute(...)`, an unhandled runtime exception can cause the worker to terminate abnormally and go through `UncaughtExceptionHandler`; how logs appear depends on the thread factory, runtime, and monitoring setup.

Do not write a unit test that only catches exceptions directly around `execute` and think you have covered errors inside an asynchronous worker.

**Pattern for handling errors directly inside the task** when an appropriate monitoring channel exists:

```java
executor.execute(() -> {
    try {
        processEvent(eventId);
    } catch (RuntimeException failure) {
        reportFailure(eventId, failure);
    }
});
```

This is a **snippet placed inside a business class** that already has `processEvent(...)` and `reportFailure(...)`; it is not a standalone program. `reportFailure` must actually handle recording the failure, such as structured logs/metrics or a job status store. If the task has dangerous side effects, you must decide whether it can be retried and avoid duplicate execution.

**Specifically:** Do not catch `Throwable` and silently ignore all errors. Serious JVM-level errors may need to be left for the monitoring system or handled according to policy. For `InterruptedException` in blocking logic, you should terminate the task or propagate the appropriate signal; when catching without rethrowing, typically restore it via `Thread.currentThread().interrupt()`.

## 7. Java 17: Observing a Full Queue and Rejected execute()

The following example uses Java SE to demonstrate when `execute` stops accepting additional tasks. It has **one worker**, a queue capacity of **one**, and a latch holding the worker busy while we submit the remaining tasks. Thus, the printed output does not depend on machine speed.

**File `ExecuteRejectionDemo.java`:**

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class ExecuteRejectionDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1, 1,
                0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            executor.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();

            executor.execute(() -> {});
            System.out.println("Queued tasks: "
                    + executor.getQueue().size());

            try {
                executor.execute(() -> {});
                System.out.println("Unexpectedly accepted additional task");
            } catch (RejectedExecutionException rejected) {
                System.out.println("Third task was rejected");
            }
        } finally {
            release.countDown();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Compile and run:

```bash
javac ExecuteRejectionDemo.java
java ExecuteRejectionDemo
```

Exact output:

```text
Queued tasks: 1
Third task was rejected
```

Why is this deterministic? `started.await()` waits until the first task has occupied the worker. That task must wait for `release`, so the worker has not yet pulled the second task from the queue. `ArrayBlockingQueue<>(1)` allows only one waiting task. The third task cannot run and has no queue space left, so `AbortPolicy` throws `RejectedExecutionException` immediately on the caller.

**Distinguishing exceptions:** In the direct Java `ThreadPoolExecutor` example, the caught type is `RejectedExecutionException`. In Spring's `ThreadPoolTaskExecutor`, the rejection contract is typically `TaskRejectedException` (a rejection error type used by Spring). How conversion and handling work depends on the chosen implementation/policy; do not lump all task errors together with submission rejection errors.

In real environments, `getQueue().size()` changes continuously; use it to observe load, not as an absolute guarantee for business decisions on another thread. The pattern above holds the worker in a controlled way to illustrate a completely deterministic scenario.

## 8. When Should execute() Not Be Used Alone?

`execute` is appropriate if the calling code truly **does not need to receive a task result**. However, "returns no data" is different from "does not need to know when it is done". There are several categories of needs:

| Need | Suitable approach | Notes |
|---|---|---|
| Submit an independent task without needing a return value | `TaskExecutor.execute(Runnable)` | Design error handling, overload handling, and lifecycle separately |
| Task returns no value, but caller must know when it finishes/fails | `ExecutorService.submit(Runnable)` or `AsyncTaskExecutor.submit(Runnable)` to obtain `Future<?>` | `get()` may block; must handle `ExecutionException`/cancellation |
| Task produces a result of type `T` | `Callable<T>` + `submit`, or a suitable async API | Provides a result and an exception path |
| Coordinate multiple async steps and results | `CompletableFuture` or an orchestration mechanism | Must configure executors for async steps |
| Work must survive crashes/restarts | Persistent queue, database, or dedicated job mechanism | An in-heap pool does not guarantee durable delivery |

With `submit(Runnable)`, `Future.get()` returns `null` if the task completes normally; task errors are typically wrapped in `ExecutionException`. `execute(Runnable)` provides no corresponding `Future`. This is an **API distinction**, and does not mean `submit` will automatically guarantee the task completes during application shutdown or system failure.

If you only need to count successful tasks or record status, you can place an observation channel inside the `Runnable` body using thread-safe structures. However, when the caller relies on that state for correctness, you still must coordinate the read timing via a latch, Future, callback, or appropriate synchronization condition.

## 9. Observing Completion While Still Using execute()

Sometimes the architecture requires depending only on `Executor`, yet a test or coordination step still needs to know when the task finishes. You can pass a `CountDownLatch` or a callback separately to emit a signal. The following example also demonstrates that `execute` returns no result.

**File `ExecuteCompletionDemo.java`:**

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class ExecuteCompletionDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ExecutorService owner = Executors.newFixedThreadPool(2);
        Executor executor = owner;
        AtomicInteger completed = new AtomicInteger();
        CountDownLatch done = new CountDownLatch(3);

        try {
            for (int i = 0; i < 3; i++) {
                executor.execute(() -> {
                    try {
                        completed.incrementAndGet();
                    } finally {
                        done.countDown();
                    }
                });
            }

            done.await();
            System.out.println("Completed: " + completed.get());
        } finally {
            owner.shutdown();
        }
    }
}
```

Run commands:

```bash
javac ExecuteCompletionDemo.java
java ExecuteCompletionDemo
```

Output:

```text
Completed: 3
```

Although the pool has two workers and the execution order of the three tasks is indeterminate, `AtomicInteger` protects the increment from lost updates and `CountDownLatch` only unblocks main once all three `countDown()` calls have occurred. Therefore, the printing of the final line is deterministic.

**Warning on metric semantics:** `completed` here is actually **the number of tasks that performed the increment**, not a guarantee that external business side effects succeeded. Name counters after the milestone the program actually checks (submitted, started, succeeded, failed); do not equate an accepted task with a successfully completed task.

If you need error feedback while waiting, a plain latch is not enough; you must add a thread-safe error channel or switch to `Future`/`CompletableFuture`. If task loss is possible, design a timeout for waiting rather than waiting indefinitely.

## 10. Concurrency Does Not Automatically Make Singleton Beans Thread-Safe

Singleton Spring beans are typically called concurrently by multiple requests. When a bean submits multiple `Runnable` instances to a pool, those tasks may concurrently read or write fields of that bean.

**Dangerous example:**

```java
private int count;

void dispatch(TaskExecutor executor) {
    executor.execute(() -> count++);
}
```

This is an **illustrative buggy snippet** placed inside a class. `count++` consists of a read, compute, and write; multiple workers may see the same stale value and cause lost updates. Using `execute` does not create automatic synchronization.

One option when only an independent counter is needed:

```java
private final AtomicInteger count = new AtomicInteger();

void dispatch(TaskExecutor executor) {
    executor.execute(count::incrementAndGet);
}
```

This is an illustrative snippet inside a class importing `java.util.concurrent.atomic.AtomicInteger` and `org.springframework.core.task.TaskExecutor`. If you need to protect multiple fields sharing an invariant, a single atomic type may not suffice; consider short locks, immutable snapshots, or changing the data structure. Do not hold a bean lock during slow I/O calls just to perform a quick update.

**Also do not assume ThreadLocal is propagated automatically.** With a thread pool, workers may be reused across tasks. `ThreadLocal` values, request context, MDC, or `SecurityContextHolder` from the submitting thread are not automatically copied accurately for every executor. If you need a correlation ID or tenant ID, pass immutable parameters or configure an appropriate context propagation mechanism and verify context cleanup after each task.

## 11. execute() and Transaction Boundaries in Spring

A task running on another thread **does not automatically continue the transaction** of the submitting thread. For example:

```text
Request thread:
  starts @Transactional
  writes uncommitted data
  execute(runnable)
  ends transaction

Worker:
  may run before or after commit
  does not automatically join caller's transaction
```

If the task reads a record that was just modified but not yet committed, the result depends on isolation level and execution timing; do not assume it will see the new record. For actions that must only occur after the transaction succeeds, consider post-commit event handling, an outbox, or a durable work handoff mechanism. If the task itself needs a transaction, open a separate transaction boundary through an appropriately managed Spring component.

**Do not use `execute()` as a way to safely "hand off" an `EntityManager`, JDBC connection, or live request object to another thread.** These resources have their own lifecycles, thread-safety policies, and ownership rules.

## 12. Lifecycle Management and Load Resilience

When creating an `ExecutorService` yourself via `Executors` in Java SE, the code owning the pool is responsible for `shutdown()` and awaiting termination according to policy. In Spring, if `ThreadPoolTaskExecutor` is registered as a normal bean, Spring manages initialization and shutdown along with the `ApplicationContext`.

Some practical points:

- Avoid `new Thread(...)` or `Executors.newFixedThreadPool(...)` per request; this creates too many threads/pools and is hard to clean up.
- Avoid near-unbounded queues if tasks can arrive faster than they can be processed; they can retain huge numbers of objects on the heap.
- Configure worker limits, queue size, and rejection policy in alignment with latency and memory requirements.
- Choose the shutdown policy: wait for accepted tasks, reject new tasks, or request cancellation as needed. Spring lifecycle properties depend on version/configuration; check the documentation for the version in use.
- Do not call `shutdown()` yourself on a shared executor managed by Spring or an application server if the service is not the owner.
- Do not confuse `TaskExecutor.execute(...)` with a durable job system: JVM crashes/redeploys can lose incomplete tasks.

### 12.1. If the Executor Rejects, What Should the Caller Do?

A synchronous API can map rejection to an intentional overload error; a consumer can slow down intake; a critical task can be routed to a persistent queue if the design allows. No single policy fits every case.

With `ThreadPoolExecutor`'s `CallerRunsPolicy`, if the pool is not shut down, a task rejected by the worker/queue path may run immediately on the **submitting thread**. This creates backpressure, but can slow down the request or cause task exceptions to propagate to the caller. With `DiscardPolicy`, work may be dropped silently. Therefore, verify the actual policy before interpreting "`execute` returned normally".

## 13. Designing Error Handling and Observability for Resultless Tasks

When a task returns no value, clearly define **what evidence marks success**. At minimum, three milestones can be observed:

1. **Accepted for processing (`accepted`):** `execute` did not report an error under the chosen acceptance policy.
2. **Started (`started`):** the worker/caller actually invoked the task's `run()`.
3. **Completed successfully (`succeeded`) or failed (`failed`):** the business logic reached an outcome or threw an exception.

Metrics that should be separated:

| Metric | Interpretation |
|---|---|
| `tasks.submitted` | Number of times callers attempted to submit work |
| `tasks.rejected` | Number of tasks rejected under an observable policy |
| `tasks.started` | Number of tasks that entered `run()` |
| `tasks.succeeded` | Number of tasks whose business logic completed successfully |
| `tasks.failed` | Number of failed tasks |
| `queue.depth` | Number of tasks still waiting in the queue |
| `executor.active` | Number of currently busy workers |
| `task.queue.wait` | Time from acceptance to start |
| `task.run.duration` | Time the task spent executing |

In Spring, `ThreadPoolTaskExecutor` provides observation methods such as `getActiveCount()`, `getPoolSize()`, and `getQueueSize()` depending on the relevant Spring version. These values are point-in-time observations, not guaranteed atomic snapshots of the entire system.

If using `TaskDecorator` to capture context or measure time, remember the decorator may wrap a `Runnable` already wrapped by the framework; how errors surface differs between `execute` and `submit`. Verify behavior in the exact Spring version and choose a reliable place to record task failures.

### 13.1. Capture Minimal Data, Avoid Holding Entire Requests

A lambda can accidentally capture an entire request object, input stream, session, or large object graph; if the queue has many pending items, all of them stay retained on the heap. Instead, prefer minimal immutable data such as IDs, checksums, or small copies of parameters.

For tasks sending emails, processing payments, or writing to databases, the crucial issue is not just memory: you must define idempotency, when acknowledgment is given to the caller, bounded retries, and worker permissions. A single `execute` call does not solve those requirements on its own.

## 14. How to Test execute() Properly

Because `execute` returns `void`, a unit test written like the following usually misses the mark:

```java
service.dispatch("A-1");
// Wrong expectation with a pool: work may not have run yet.
assertEquals(1, service.processedCount());
```

This is an **illustrative test snippet**, not a standalone class; `assertEquals` belongs to a testing framework. With a real pool, the outcome depends on scheduling.

There are two testing approaches depending on your goal:

**Testing task logic synchronously:** inject Spring's `SyncTaskExecutor`. It invokes the task immediately on the test thread, keeping results deterministic. This is a good choice when you only need to verify that the service constructs and submits the right logic, without testing real threading.

```java
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.SyncTaskExecutor;

// Place inside test code / appropriate service setup.
TaskExecutor direct = new SyncTaskExecutor();
direct.execute(() -> System.out.println("Synchronous test"));
```

**Integration testing asynchronous execution:** use a latch, Future (if provided by the API), callback, or a bounded-timeout condition to await completion milestones; do not use `Thread.sleep(100)` and hope the worker has finished.

Tests should cover at minimum: task success, task failure, executor rejection, task cancellation or application shutdown while work remains, and correctness of shared state. In particular, test API behavior when `dispatch` returns before the task completes.

## 15. Common Misconceptions

| Misconception | Reality | Mental correction |
|---|---|---|
| `execute()` always creates a new thread | The executor may run directly, in a pool, or use another strategy | Check the implementation |
| When `execute()` returns, the task has finished | With an async pool, the task may still be queued or running | Distinguish accepted/started/succeeded |
| `Runnable` cannot fail because `run()` returns `void` | Runtime exceptions can still be thrown | Design observability and error handling |
| Catching exceptions around `execute` is enough | Cannot catch all errors occurring later on a worker | Handle inside the task or via a monitoring channel |
| `execute()` automatically provides a `Future` | The contract returns `void` | Use `submit` if a Future is needed |
| `@EnableAsync` is required to use `TaskExecutor.execute` | `execute` is a direct call; `@EnableAsync` serves `@Async` | Choose the right mechanism for the goal |
| Submitting tasks to a pool makes singleton fields thread-safe | Multiple workers can modify the same variable | Atomics, short locks, immutable data |
| `ThreadLocal`/transactions automatically follow the task | Contexts are usually thread-bound; switching threads does not auto-copy | Pass needed data, create separate transactions |
| Ignoring `TaskRejectedException` | Can falsely report acceptance or drop tasks | Handle overload at the caller boundary |
| A large queue guarantees no lost work | In-heap queues are not durable; can cause OOM | Bound queues, apply backpressure, persist if needed |
| Calling `shutdown()` after each `execute` on a shared bean | Pool closes, other requests cannot submit work | Let the owner manage lifecycle |
| Using `Thread.sleep` to test completion | Runtime varies by machine/load | Latches/Futures/conditions with timeouts |

## 16. Practice Exercises

### Exercise 1 — Same Task, Two Executors

Write a `Runnable` that prints the thread name. Submit it using `Runnable::run` and using `Executors.newSingleThreadExecutor(...)`. Explain why the output can differ even though both call sites use `execute`.

**Guidance:** The direct executor executes `run()` on the caller, while the pool has its own worker; the `execute` contract does not dictate thread name or type.

### Exercise 2 — Without a Future

Given the call `executor.execute(task)`, how can the caller know the task has completed without changing the executor API? Why is only using `execute` and polling a `boolean` variable usually insufficient?

**Guidance:** Use a latch, callback, or thread-safe state object with proper synchronization rules. A plain boolean can suffer from visibility and timing issues; even `volatile` alone does not provide waiting or error handling.

### Exercise 3 — Distinguishing Two Error Types

A pool is full and throws `TaskRejectedException` when submitting A. Task B is accepted, but throws `IllegalStateException` after running on a worker. Where do the two errors occur? Why might a `try/catch` around `execute(B)` fail to catch B's error?

**Guidance:** Rejection happens synchronously on the caller; B's runtime error happens on the execution thread. There is no `Future` from `execute` to observe B automatically.

### Exercise 4 — Java 17 Rejection Experiment

Run `ExecuteRejectionDemo.java`. Keep the worker count at 1, increase the queue from 1 to 2, and submit an additional task. While the worker is still waiting on the latch, which task number gets rejected?

**Guidance:** One task is running, two tasks are queued; the fourth task is rejected if `AbortPolicy` is in use.

### Exercise 5 — Choosing the Right API

Service A sends a data update that needs no return value for the caller; service B needs an `Integer` from a computation; service C needs no value but must know the work succeeded before committing another step. Choose `execute` or `submit` for each case and explain.

**Guidance:** A can use `execute` with proper error handling; B needs `Callable<Integer>` and an API returning a result; C needs a completion/error channel such as `Future` or an explicit orchestration design, not just `execute`.

### Exercise 6 — Real-World Spring Scenario

A controller returns HTTP 202 right after `eventDispatchService.dispatch(id)`. The pool accepts the task, but the process crashes before the worker executes it. Does the client have any basis to assert the event was processed or is guaranteed to be processed?

**Guidance:** No. 202 in the example only confirms the submission operation at that moment; durable storage, a job ID, and a tracking mechanism are required if a stronger guarantee is desired.

## 17. Project Usage Workflow

When you need to submit a `Runnable` that returns no value, check in order:

1. **Purpose:** Do you truly not need a return value, success outcome, or error feedback for the caller? If you do, reconsider `submit` or another API.
2. **Executor:** Identify the injected `TaskExecutor` bean clearly; know whether it runs synchronously or via a pool.
3. **Resources:** Set appropriate worker/queue bounds; handle overload and application shutdown.
4. **Task:** Write responsible logic, do not capture inappropriate request/transaction data; protect shared state.
5. **Errors:** Distinguish submission errors from runtime task errors; implement business-appropriate logging/metrics/retries.
6. **Observability:** If the task is important, define accepted/started/succeeded milestones and how to check for timeouts or lost tasks.
7. **Testing:** Use a direct executor to test logic, use latches/conditions with timeouts for integration tests, and verify rejection behavior.

## 18. Key Takeaways

- `Runnable` describes **the work** and `run()` returns `void`; `execute(Runnable)` is the way to **submit work** to an `Executor` or `TaskExecutor`.
- `execute()` **does not return a `Future`, does not propagate results, and does not guarantee task completion**.
- **Synchronous vs. asynchronous depends on the executor**: `SyncTaskExecutor` runs immediately, while `ThreadPoolTaskExecutor` uses a configured pool.
- **Catch errors at the right moment**: rejection occurs on the submission path; errors inside a worker require a separate recording channel.
- **Bean state and resources must still be managed**: thread safety, pool/queue limits, context, transactions, shutdown, and job durability.
- When you need to know definitively whether work succeeded or failed, design an appropriate completion signal or use an API such as `submit`.

### Official API Documentation

- [Java SE 17 — Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html)
- [Java SE 17 — Executor.execute](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Spring Framework — TaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskExecutor.html)
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
