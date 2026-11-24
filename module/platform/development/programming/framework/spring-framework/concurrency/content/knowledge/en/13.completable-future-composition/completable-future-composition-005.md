# thenAccept() and thenRun() for Steps Without a Return Value

## 1. Context and Goals

When composing tasks with `CompletableFuture`, not every processing step produces a new result. Sometimes you need to read the previous step's result to record an audit log, print output, or send a notification; other times you only need to perform an action after the previous task completes. The two methods designed for such steps are **`thenAccept()` and `thenRun()`**.

- `thenAccept(Consumer<? super T>)`: **receives the value T** from the previous stage; the callback performs an action with a `void` return type.
- `thenRun(Runnable)`: **does not receive the result T** of the previous stage; the callback simply runs after the previous stage completes normally.
- Both return `CompletableFuture<Void>` when called on `CompletableFuture<T>`. The new stage is still a future for **tracking whether the action has finished or failed**.

After this lesson, you will be able to accurately explain `Void` in a pipeline; choose the right callback based on data needs; control ordering between steps; understand failure/cancellation and non-Async/Async variants; use a Spring-managed executor when chaining onto `@Async` results; and write tests that do not rely on accidental timing.

**Focus:** steps that **do not produce a new result** in a `CompletableFuture` chain. Choosing `thenAccept` or `thenRun` does not by itself guarantee durable side effects, create a transaction, prevent race conditions, or free the request thread if the caller immediately calls `join()`.

## 2. CompletionStage Mechanism and the Void Type

A `CompletableFuture<T>` can be:

1. Completed normally with result `T`.
2. Completed exceptionally with an exception or cancellation.
3. Incomplete; callbacks are waiting for their trigger condition.

When a continuation is registered, the API creates a **dependent stage**. The dependent stage completes normally only when the previous stage succeeds and the callback finishes without throwing an error. The callback is skipped if the predecessor completed exceptionally.

```text
CompletableFuture<T> source
       |
       +------ success(T) ------+
       |                        |
       |                thenAccept(T -> action)
       |                    returns
       |                CompletableFuture<Void>
       |                        |
       |                thenRun(() -> signal)
       |                    returns
       |                CompletableFuture<Void>
       |
       +------ exceptional completion
                                |
                        normal-only callback skipped
                        dependent stage ends exceptionally
```

In Java, `void` is the keyword for a method with no return value. `java.lang.Void` is a reference type that can be used as a generic type argument. For `CompletableFuture<Void>`, the result upon **normal** completion is `null`. It does not mean the future is ignored or cannot fail.

| API | Callback parameter | Receives source's value? | Produces a new value? | New stage result type |
| --- | --- | --- | --- | --- |
| `thenApply(fn)` | `Function<T, U>` | Yes | Yes, `U` | `CompletableFuture<U>` |
| `thenAccept(action)` | `Consumer<T>` | Yes | No | `CompletableFuture<Void>` |
| `thenRun(action)` | `Runnable` | No | No | `CompletableFuture<Void>` |
| `thenCompose(fn)` | `Function<T, CompletionStage<U>>` | Yes | Chains another future | `CompletableFuture<U>` |
| `whenComplete(action)` | `BiConsumer<T, Throwable>` | Value and error | Not meant to produce a new value | Stage with the same type `T` |
| `handle(fn)` | `BiFunction<T, Throwable, U>` | Value and error | Yes, `U` | `CompletableFuture<U>` |

These are the types when methods are called on `CompletableFuture`; the `CompletionStage` interface declares corresponding methods returning `CompletionStage`.

**Mnemonic:** *apply* produces a value, *accept* consumes a value, *run* needs no value. When a secondary operation itself returns another future, *compose* is how you flatten that future into the result flow.

## 3. thenAccept(): Receiving a Result and Performing an Action

Signature:

```java
CompletableFuture<Void> thenAccept(Consumer<? super T> action)
```

Example of a future fetching an order summary:

```java
CompletableFuture<OrderSummary> source = loadOrder(orderId);
CompletableFuture<Void> audited =
        source.thenAccept(order -> auditService.record(order.id()));
```

This is a **project fragment**: `OrderSummary`, `loadOrder`, and `auditService` must exist in the application. The callback receives `OrderSummary` so it can access ID, amount, status, etc. Only when `auditService.record` returns normally is `audited` marked complete. If auditing throws an error, `audited` completes exceptionally while `source` can still be successful.

Do not treat `thenAccept` as a data transformation operator. Its callback follows `Consumer.accept(T)` returning `void`, so it cannot return a `String`/`OrderId` as the result for a subsequent stage.

**Intentionally ill-typed example, does not compile:**

```java
source.thenAccept(order -> {
    return order.id();
});
```

If you need the ID to pass downstream, use `thenApply(order -> order.id())`. If you only need to log the ID, use `thenAccept(order -> System.out.println(order.id()))`.

### 3.1. Complete Java 17+ Example

File `ThenAcceptThenRunDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class ThenAcceptThenRunDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source =
                CompletableFuture.completedFuture(21);

        CompletableFuture<Void> accepted =
                source.thenAccept(value ->
                        System.out.println("received=" + value));

        CompletableFuture<Void> finished =
                accepted.thenRun(() ->
                        System.out.println("audit-done"));

        finished.join();

        System.out.println("source=" + source.join());
        System.out.println("terminal=" + finished.join());
    }
}
```

Run with Java 17+:

```bash
javac ThenAcceptThenRunDemo.java
java ThenAcceptThenRunDemo
```

Output:

```text
received=21
audit-done
source=21
terminal=null
```

Explanation:

1. `source` already has the value 21.
2. `thenAccept` receives that value and prints the first line.
3. `thenRun` is chained onto **`accepted`**, not registered as an independent branch off `source`, so it runs only after `thenAccept` finishes normally.
4. `join()` waits for the final future; the `null` result is normal for `Void`.
5. `source.join()` still returns 21: the callback does not consume or erase `source`'s result.

This example creates no executor; its purpose is to prove **data flow and dependency**, not concurrent speed.

### 3.2. Writing a Method Reference

```java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("ORDER-7");

CompletableFuture<Void> printed =
        source.thenAccept(System.out::println);
printed.join();
```

This is a Java 17+ fragment and prints `ORDER-7`. Here the method reference `System.out::println` acts as a `Consumer<String>`; the source's result is passed to `println`. Using `thenRun(() -> System.out.println("done"))` would only print a fixed message without receiving `ORDER-7`.

## 4. thenRun(): Needs Only Completion, Does Not Receive T

Signature:

```java
CompletableFuture<Void> thenRun(Runnable action)
```

`thenRun` accepts a zero-argument `Runnable`. The action runs only after the previous stage completes **normally**. Whether the source has a `String`, `Integer`, or `OrderSummary` result, `Runnable` does not receive that value through the API.

Appropriate case:

```java
CompletableFuture<Invoice> source = invoiceService.load(invoiceId);
CompletableFuture<Void> signaled =
        source.thenRun(() -> completionSignal.countDown());
```

This is a fragment requiring the corresponding variables and services. If you only need to fire a signal once the invoice has finished loading successfully without reading `Invoice`, `thenRun` is appropriate.

If the action **must use the invoice loaded from source**, `thenAccept(invoice -> ...)` is usually clearer. Do not store the invoice in a singleton field just so a `thenRun` callback can access the data, as that introduces shared mutable state prone to races.

### 4.1. thenRun Can Still Capture Outer Variables

```java
String requestId = "REQ-9";
CompletableFuture<Void> done =
        source.thenRun(() -> System.out.println(requestId));
```

This is **variable capture** of an effectively final local variable, not `source` passing its result to `thenRun`. If the captured variable points to a mutable object, that object can still be shared across threads.

### 4.2. Java 17+ Example: Action Without Reading Value

File `ThenRunSignalDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

public class ThenRunSignalDemo {
    public static void main(String[] args) {
        AtomicInteger signals = new AtomicInteger();

        CompletableFuture<String> source =
                CompletableFuture.completedFuture("READY");
        CompletableFuture<Void> signaled =
                source.thenRun(() -> signals.incrementAndGet());

        signaled.join();

        System.out.println("signals=" + signals.get());
        System.out.println("source=" + source.join());
        System.out.println("result=" + signaled.join());
    }
}
```

```bash
javac ThenRunSignalDemo.java
java ThenRunSignalDemo
```

Output:

```text
signals=1
source=READY
result=null
```

`thenRun` only cares that `source` succeeded, and does not receive the string `READY`. Using `AtomicInteger` makes updating the counter thread-safe if the example is switched to Async callbacks. In this simple example there is no concurrent contention.

## 5. Two Independent Branches Do Not Imply a Sequential Chain

An important mistake:

```java
source.thenAccept(order -> audit(order));
source.thenRun(() -> sendSignal());
```

These are two **separate dependent stages**, both attached to `source`. They depend only on `source`, **not on each other**. Therefore there is no guarantee `audit` finishes before `sendSignal`. If `source` is already complete, you might observe the two callbacks run in registration order in one test; that is not a contract for all situations.

If `sendSignal` must run after `audit` succeeds, chain them:

```java
CompletableFuture<Void> workflow =
        source.thenAccept(order -> audit(order))
              .thenRun(() -> sendSignal());

workflow.join();
```

If `audit` fails, the stage after `audit` completes exceptionally and `sendSignal` is skipped. That is the desired behavior when the signal should only fire after a successful audit.

### 5.1. When Two Branches Are Truly Independent

File `TwoBranchesDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

public class TwoBranchesDemo {
    public static void main(String[] args) {
        AtomicInteger actions = new AtomicInteger();
        CompletableFuture<String> source =
                CompletableFuture.completedFuture("INVOICE-1");

        CompletableFuture<Void> audit =
                source.thenAccept(value -> actions.incrementAndGet());
        CompletableFuture<Void> notify =
                source.thenRun(() -> actions.incrementAndGet());

        CompletableFuture.allOf(audit, notify).join();

        System.out.println("actions=" + actions.get());
        System.out.println("source=" + source.join());
    }
}
```

```bash
javac TwoBranchesDemo.java
java TwoBranchesDemo
```

Output:

```text
actions=2
source=INVOICE-1
```

`CompletableFuture.allOf(...)` creates a `Void` stage to wait for both branches. The example intentionally **does not** print individual callback order because there is no guaranteed order between the two branches. When branches run concurrently, using a thread-safe counter like `AtomicInteger` is better than updating an unsynchronized shared `int`.

### 5.2. Why You Must Not Discard the Callback's Future Reference

**Anti-pattern:**

```java
source.thenAccept(this::sendEmail);
return source;
```

If sending the email fails, the error lives on the **dependent stage** created by `thenAccept`; a caller holding only `source` may think `source` succeeded. For mandatory side effects:

```java
return source.thenAccept(this::sendEmail);
```

The line above is a fragment suitable for a method returning `CompletableFuture<Void>`. What matters is that the caller/service actually observes that future; if it is created and discarded, you have no reliable outcome contract.

## 6. Non-Async and Async: Which Thread Runs the Callback?

**Having no Async suffix does not mean always running on the main/caller thread.** With `CompletableFuture`, a `thenAccept`/`thenRun` action can run on the thread that just completed the previous stage or on another thread participating in completion. If the stage already completed before the callback is registered, the action may run immediately during registration. The API does not provide a fixed thread identity.

Suffixed variants:

| API | Receives T? | Execution mechanism |
| --- | --- | --- |
| `thenAccept(action)` | Yes | No executor specified |
| `thenAcceptAsync(action)` | Yes | Default asynchronous execution facility |
| `thenAcceptAsync(action, executor)` | Yes | Passed executor |
| `thenRun(action)` | No | No executor specified |
| `thenRunAsync(action)` | No | Default asynchronous execution facility |
| `thenRunAsync(action, executor)` | No | Passed executor |

In standard Java `CompletableFuture`, Async variants **without an executor** normally rely on `ForkJoinPool.commonPool()`, with a fallback condition if the common pool lacks sufficient parallelism. They **do not automatically use** Spring `@Async`'s pool.

Especially in Spring, if a callback performs blocking HTTP calls, DB queries, or very slow logging, use a properly bounded executor instead of defaulting to holding the source-completing thread or the common pool.

### 6.1. Java 17+ Example: Specifying an Executor

File `NamedExecutorDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class NamedExecutorDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor =
                Executors.newSingleThreadExecutor(
                        task -> new Thread(task, "audit-worker"));

        try {
            CompletableFuture<String> source = new CompletableFuture<>();

            CompletableFuture<Void> done =
                    source.thenAcceptAsync(value -> {
                        System.out.println("value=" + value);
                        System.out.println("accept-thread="
                                + Thread.currentThread().getName());
                    }, executor).thenRunAsync(() ->
                        System.out.println("run-thread="
                                + Thread.currentThread().getName()),
                        executor);

            source.complete("A-17");
            done.get(5, TimeUnit.SECONDS);
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac NamedExecutorDemo.java
java NamedExecutorDemo
```

Output:

```text
value=A-17
accept-thread=audit-worker
run-thread=audit-worker
```

Explanation: `source` completes via `complete("A-17")`, the first callback is submitted to the executor with a deterministic thread name; the second callback is submitted only after the first callback's dependent stage succeeds. `get(5, TimeUnit.SECONDS)` sets a wait bound for the caller. `shutdown()` is the responsibility of the code creating the executor; in Spring, the executor should be a container-managed bean rather than creating a new pool per request.

**Do not conclude that every `thenAcceptAsync` overload definitely creates a new platform thread:** if you pass an `Executor` that runs inline or uses a virtual-thread strategy, where it runs depends on that executor. What the API provides is a **mechanism to submit the task to an execution facility**.

### 6.2. Non-Async Callbacks Can Slow Down the Source Worker

If a worker finishes `loadFromDb` and then runs a `thenAccept` doing blocking I/O for several seconds, that thread can be tied up longer than planned. Splitting out `thenAcceptAsync(..., auditExecutor)` decides which resources the callback uses, though it does not make a slow service faster than its true capacity. You still need timeouts, queue capacity, rate limits, backpressure, and a shutdown policy.

## 7. Exceptional Completion: When Callbacks Are Skipped

Both `thenAccept` and `thenRun` run only when **the predecessor completes normally**. If the previous stage fails or is cancelled, the callback is skipped and the dependent stage completes exceptionally.

If the callback itself throws an exception, the dependent stage fails while the original stage may remain successful. Hence a workflow can have **source success + audit failure**: that is not a contradiction, just two different stages.

### 7.1. Java 17+ Example: Source Failure and Recovery

File `RecoveryDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicBoolean;

public class RecoveryDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> source = new CompletableFuture<>();
        AtomicBoolean invoked = new AtomicBoolean(false);

        CompletableFuture<Void> skipped =
                source.thenAccept(value -> invoked.set(true))
                      .thenRun(() -> System.out.println("unexpected"));

        source.completeExceptionally(
                new IllegalStateException("service unavailable"));

        try {
            skipped.join();
        } catch (CompletionException ex) {
            System.out.println("cause="
                    + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("accept-called=" + invoked.get());

        CompletableFuture<Void> recovered =
                source.exceptionally(error -> 0)
                      .thenAccept(value ->
                              System.out.println("fallback=" + value));
        recovered.join();
    }
}
```

```bash
javac RecoveryDemo.java
java RecoveryDemo
```

Output:

```text
cause=IllegalStateException
accept-called=false
fallback=0
```

The first branch skips both callbacks because `source` failed. `exceptionally(error -> 0)` creates a new stage succeeding with fallback 0, allowing `thenAccept` in the second branch to run. Fallback values must be chosen based on business logic; do not replace a payment error with 0 or treat an error as success if the contract forbids it.

### 7.2. Java 17+ Example: Callback Error Leaves Source Unchanged

File `CallbackFailureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class CallbackFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source =
                CompletableFuture.completedFuture("ORDER-9");

        CompletableFuture<Void> audited =
                source.thenAccept(value -> {
                    throw new IllegalArgumentException("audit failed");
                });

        try {
            audited.join();
        } catch (CompletionException ex) {
            System.out.println("audit-error="
                    + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("source=" + source.join());
    }
}
```

```bash
javac CallbackFailureDemo.java
java CallbackFailureDemo
```

Output:

```text
audit-error=IllegalArgumentException
source=ORDER-9
```

`join()` typically throws `CompletionException` when a stage completes exceptionally; `get()` wraps errors in the checked exception `ExecutionException`. Do not only wrap **callback registration** in try/catch, because with async continuations errors can occur later and live in the dependent future.

### 7.3. Distinguishing from whenComplete and handle

- `whenComplete((value, error) -> ...)` runs when the previous stage **succeeds or fails**, making it suitable for recording both paths; it follows rules that preserve the original outcome and handle exceptions thrown by the callback itself.
- `handle((value, error) -> result)` also runs on success or error, but returns **a new result U**, so it can be used for recovery/transformation.
- `exceptionally(error -> fallback)` recovers from an error with an appropriate fallback.
- `thenAccept` and `thenRun` do not run on exceptional completion; **do not use them as a finally/cleanup block for all outcomes**.

Fragment example:

```java
CompletableFuture<Void> done =
        source.whenComplete((value, error) -> {
            if (error != null) {
                reportFailure(error);
            }
        }).thenRun(() -> markSucceeded());
```

`markSucceeded` at the end still runs only after normal completion. `whenComplete` helps observe errors, **and does not fix** them by itself. If you want cleanup that always runs, use a cleanup callback/primitive with the right semantics and handle cleanup exceptions.

## 8. Combining with Spring @Async

A Spring `@Async` method can return `CompletableFuture<T>` when invoked **through a Spring-managed proxy** with async processing enabled (e.g., `@EnableAsync`). Callers can attach `thenAccept`/`thenRun` to the returned future.

**Spring integration snippet (does not compile standalone with javac):**

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

record InvoiceSummary(String invoiceId, int lineCount) {}

@Service
public class InvoiceQueryService {
    @Async("queryExecutor")
    public CompletableFuture<InvoiceSummary> load(String id) {
        return CompletableFuture.completedFuture(
                new InvoiceSummary(id, 3));
    }
}
```

In another bean, inject `InvoiceQueryService`, `AuditService`, and the executor:

```java
public CompletableFuture<Void> auditInvoice(String id) {
    return queryService.load(id)
            .thenAcceptAsync(summary ->
                    auditService.record(
                            summary.invoiceId(),
                            summary.lineCount()),
                    auditExecutor)
            .thenRun(() -> auditService.markCompleted(id));
}
```

The fragment above assumes `queryService`, `auditService`, and `auditExecutor` are declared/injected dependencies. The final stage represents the chain: load summary successfully -> audit successfully -> mark completed.

**Note:** `thenRun` at the end is non-Async, so the `markCompleted` callback may run on the thread that finished the audit. If it also performs blocking I/O, consider `thenRunAsync(..., auditExecutor)` or another suitable executor. `thenAcceptAsync` without an executor argument typically uses the default Java async facility, **not Spring's `queryExecutor` by default**.

### 8.1. Thread Boundaries and Transactions

`@Async` may already have switched threads, and `thenAcceptAsync` may switch to another executor. Thread-bound Spring transaction contexts, request-scoped objects, MDC/trace contexts, and security contexts **do not automatically follow** the future chain. If auditing needs a transaction, open/define the transaction at the boundary running the audit using the proper Spring mechanism; prefer passing immutable IDs/DTOs instead of managed JPA entities and `EntityManager` instances from the caller.

If a callback calls an API whose side effect must finish inside the request's transaction, revisit the design; do not treat an asynchronous continuation as an automatic participant in the caller's transaction.

### 8.2. Pools and Overload

`thenAcceptAsync(action, executor)` can fail if the executor is shutting down or rejects tasks due to overload. When side effects matter, observe the dependent stage, configure admission control / bounded queues, and report errors per SLA; do not discard the future and hope the callback surely ran.

Spring's `ThreadPoolTaskExecutor` provides bean-managed pools. Do not call `Executors.newFixedThreadPool(...)` inside every request to run callbacks; those resources will not be closed automatically by Spring when left as local objects.

### 8.3. Returning API Results and Mandatory Side Effects

If the caller should receive a response only after auditing succeeds, return/await the **final** future rather than the source. If sending an email can complete after the HTTP response yet must not be lost on restart, persist the work using a **durable queue/outbox/job store** and return a job ID/status per contract; in-memory continuations do not replace durability.

## 9. Preserving the Source Value If the Pipeline Still Needs T

After `thenAccept`, the new stage is `Void`. If you need to keep processing `T`, do not try to pass a value out of `thenRun`:

### 9.1. Keep T with thenApply

```java
CompletableFuture<Order> withAudit =
        source.thenApply(order -> {
            audit(order);
            return order;
        });
```

This fragment preserves the `Order` type on the new stage and makes `audit` a precondition for success. If `audit` fails, `withAudit` fails.

### 9.2. Observe Outcomes with whenComplete

```java
CompletableFuture<Order> observed =
        source.whenComplete((order, error) -> {
            if (error == null) {
                audit(order);
            } else {
                logFailure(error);
            }
        });
```

`whenComplete` keeps the original result type. However, this callback runs **on the exceptional path too**, so check conditions explicitly to avoid unwanted side effects; if the callback throws, the dependent stage has specific exceptional completion rules.

### 9.3. If the Secondary Action Returns a Future: Use thenCompose

**Easy mistake:**

```java
source.thenAccept(order -> auditAsync(order));
```

If `auditAsync(order)` returns `CompletableFuture<Void>`, the `thenAccept` callback simply calls the method and drops the child future; the `Void` stage returned by `thenAccept` **does not wait** for that future to finish.

**Correct if you need to wait for the audit:**

```java
CompletableFuture<Void> done =
        source.thenCompose(order -> auditAsync(order));
```

`thenCompose` chains the dependent stage onto the future returned by `auditAsync`, allowing the caller to track its completion and errors. This rule is especially important when secondary Spring services return `CompletableFuture`.

## 10. Testing Ordering with CountDownLatch

Using `Thread.sleep(50)` to guess when callbacks run often makes tests flaky. Instead, use a latch to hold the first callback and verify the next callback cannot finish yet.

File `OrderedContinuationDemo.java` (Java 17+):

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class OrderedContinuationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<String> source = new CompletableFuture<>();

            CompletableFuture<Void> done =
                    source.thenAcceptAsync(value -> {
                        entered.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(ex);
                        }
                    }, executor).thenRun(() ->
                            System.out.println("next-step-ran"));

            source.complete("ok");

            if (!entered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("callback not started");
            }

            System.out.println("before-release=" + done.isDone());
            release.countDown();
            done.get(5, TimeUnit.SECONDS);
            System.out.println("after-release=" + done.isDone());
        } finally {
            release.countDown();
            executor.shutdown();
        }
    }
}
```

```bash
javac OrderedContinuationDemo.java
java OrderedContinuationDemo
```

Output on normal completion:

```text
before-release=false
next-step-ran
after-release=true
```

This tests a dependency relationship, **not** thread names. `source` completes, yet the first callback is waiting on the latch, so `done` cannot complete yet. Upon release, the first callback finishes, `thenRun` executes, and only then does the final future complete. The program sets a timeout to detect errors instead of hanging forever.

In JUnit, you can assert `assertFalse(done.isDone())` before release, `assertNull(done.get(timeout, unit))` after release, and `assertThrows(CompletionException.class, failed::join)` in failure tests. These assertions are fragments requiring JUnit and appropriate imports.

## 11. Safety When Handling Data and Side Effects

### 11.1. Callbacks Can Share Mutable Objects

`thenAccept` receives result `T` from `source`; it **does not automatically clone** that object. If two Async callbacks mutate the same `ArrayList` or a field on a singleton Spring bean, race conditions can occur.

**Anti-pattern:**

```java
List<String> shared = new ArrayList<>();
source.thenAcceptAsync(value -> shared.add("A"));
source.thenRunAsync(() -> shared.add("B"));
```

This is a fragment. Both tasks access a mutable `ArrayList` concurrently without synchronization. The fix is to establish ownership, create immutable snapshots, use concurrent collections/locks, or serialize mutations. Ordering stages only coordinates stages in that chain; threads outside the chain can still mutate the same state.

### 11.2. Idempotency and Retries

A callback writing to a DB or sending email may run again if the whole workflow retries. If the data write succeeds yet the future is marked failed before the caller receives acknowledgment, retries can cause **duplicate effects**. `thenAccept` does not guarantee exactly-once execution; use idempotency keys, unique constraints/deduplication, or transactional outboxes depending on business needs.

### 11.3. Timeouts, Cancellation, and Backpressure

- `get(timeout, unit)` only bounds how long **the caller waits**; it does not cancel the callback's I/O.
- `orTimeout(...)` transitions an expired stage to exceptional completion; subsequent normal-only callbacks are skipped if the timeout wins the completion race.
- `completeOnTimeout(value, ...)` can produce a fallback normal completion, so a following `thenAccept` may run with the fallback value.
- Cancelling a dependent future does not mean all upstream work or HTTP/DB clients are cancelled.
- With Async callbacks, bound queues, connections, deadlines, and rejections; do not pile up unbounded stages in RAM or worker queues.

### 11.4. Observing the Right Stage

Track **source completion** and **terminal callback completion** separately: a source returning the right result does not prove the audit or notification succeeded. Useful metrics: queue wait, task duration, completed/failed/rejected/cancelled counts, timeouts, p95/p99 latency, downstream connections, and pending work counts.

## 12. Common Mistakes and Solutions

| Mistake | Cause | Solution |
| --- | --- | --- |
| Using `thenRun` when `T` is needed | `Runnable` does not receive `T` | Use `thenAccept` |
| Using `thenAccept` and trying to return `U` | `Consumer` returns no value | Use `thenApply` |
| Thinking `CompletableFuture<Void>` needs no waiting | The stage still has completion and errors | Retain/return the terminal future |
| Registering two branches and assuming they are ordered | Both only depend on `source` | Chain `thenAccept(...).thenRun(...)` |
| Thinking non-Async always runs on caller thread | Continuation may run on completion thread | Do not rely on thread identity; specify an executor when needed |
| Thinking Async continuations default to Spring's pool | Omitting executor typically uses the common pool | Pass a Spring-managed `Executor` |
| Source fails yet expecting `thenRun` to run cleanup | Normal-only callbacks are skipped | Use `whenComplete` or appropriate cleanup |
| Callback fails while checking only `source` | Error lives on the dependent stage | Observe the terminal future |
| Calling a future-returning function inside `thenAccept` and ignoring it | Does not wait for the child task | Use `thenCompose` |
| Using in-memory callbacks for jobs that must not be lost | JVM restart loses pending stages | Durable queue/outbox |
| Callback mutating a shared mutable list/bean field | Data races and lost updates | Immutability/ownership/synchronization |
| Calling `join` immediately in a request and thinking it is non-blocking | `join` still waits for completion | Design async responses/deadlines properly |

## 13. Practice Exercises and Completion Criteria

**Exercise 1 — Choosing the method.** Given `CompletableFuture<OrderSummary> future`: (a) print the total price without returning a new value; (b) emit a signal upon completion without reading the summary; (c) extract the ID as a new result. Choose `thenAccept`, `thenRun`, and `thenApply` respectively and explain the return types.

**Exercise 2 — Error testing.** Create a succeeding source, make `thenAccept` intentionally throw `IllegalStateException`, then chain `thenRun`. Prove the second callback is skipped, the dependent future fails, yet the original source remains successful.

**Exercise 3 — Two branches vs. chain.** Compare `source.thenAccept(audit)` and `source.thenRun(signal)` registered independently against `source.thenAccept(audit).thenRun(signal)`. Use latches to establish test ordering instead of `sleep`.

**Exercise 4 — Executor in Spring.** Put `@Async("queryExecutor")` on a service returning `CompletableFuture<Summary>`. Chain `thenAcceptAsync(..., auditExecutor)`. Verify `auditExecutor` is a Spring-managed bean, log thread names, and measure queue/rejection and timeouts.

**Exercise 5 — Child future.** Write `auditAsync` returning `CompletableFuture<Void>`. Observe the difference between `thenAccept(x -> auditAsync(x))` and `thenCompose(x -> auditAsync(x))` when you need to guarantee the audit finished.

**Exercise 6 — Business reliability.** Design a post-transaction notification flow. Distinguish best-effort continuations from durable delivery requirements; describe idempotency, outbox/job IDs, and how status is returned to callers.

### Checklist

- [ ] I accurately state that `thenAccept` receives `T`, while `thenRun` does not receive `T`.
- [ ] I understand `CompletableFuture<Void>` still has completion, errors, and waitability.
- [ ] I distinguish `thenApply`, `thenCompose`, `whenComplete`, and `exceptionally`.
- [ ] I understand two independent branches have no default execution order.
- [ ] I do not confuse non-Async with "always on the main thread."
- [ ] I know how to specify an explicit executor for `thenAcceptAsync`/`thenRunAsync`.
- [ ] I know normal-only callbacks are skipped when the source fails or is cancelled.
- [ ] I observe errors on the **dependent stage**, not only on `source`.
- [ ] I can test ordering using latches and timeouts.
- [ ] I understand Spring `@Async` pools do not automatically apply to all Java continuations.
- [ ] I know when side effects need transactions, idempotency, and durable storage.

**Conclusion:** `thenAccept()` **consumes result `T` without producing a new value**; `thenRun()` **does not receive `T` and only waits for success to run an action**. Both produce a `CompletableFuture<Void>` that can be chained and observed. In Spring, properly control dependent stages, executors, and side effects so that a step "returning no value" does not become a step "nobody is responsible for."

## 14. Official Documentation

- Java SE 17 — [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `thenAccept`/`thenRun` and their Async variants.
- Java SE 17 — [CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): semantics of Function, Consumer, Runnable, and exceptional completion.
- Java SE 17 — [Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): task submission contract and execution location.
- Spring Framework — [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, `TaskExecutor`, and execution source configuration.

When running in a real environment, check your project's JDK/Spring versions and measure actual threads, queues, and exceptions instead of guessing from method names.
