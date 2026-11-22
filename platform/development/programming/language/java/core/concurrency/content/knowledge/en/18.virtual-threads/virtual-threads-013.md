# Structured Concurrency (preview in Java 21): role and limitations

## 1. The problem: the parent task must be responsible for its subtasks

Suppose a processing operation needs to concurrently fetch **user information** and **reward points**, then combine them into a single result. The two tasks are independent, so they can run in parallel. However, if the user cancels the operation, one task fails, or a timeout expires, what happens to the remaining task?

Unstructured asynchronous code often suffers from the following issues:

- **Fragmented lifecycle:** a subtask keeps running after the method that created it has exited, because there is no single place responsible for waiting and cleaning up.
- **Lost errors:** a future fails, yet its result is never retrieved, causing the error to go unhandled in the business flow.
- **Unsynchronized cancellation:** the parent task knows the result is no longer needed, but other subtasks continue consuming resources.
- **Poor observability:** when investigating an incident, it is difficult to see which threads belong to the same parent operation.

**Structured Concurrency** organizes subtasks into **a group with a clearly defined lifetime scope**. In Java 21, the preview API `StructuredTaskScope` allows starting subtasks within the same scope, waiting for them, applying a policy on success/failure, and closing the scope upon completion.

The core idea: **the code that creates and owns child work is responsible for terminating that scope of work**. Opening a scope, calling `fork`, `join`, and then `close` resembles a block with traceable entry and exit points. It makes managing a group of tasks safer and easier to read, though external non-JVM resources and operations that do not cooperate with cancellation still require separate handling.

This article focuses on **Java 21 / JEP 453**, in the context of Java Virtual Threads. Structured Concurrency in Java 21 is a **preview API**, not yet a stable API contract for porting source code unchanged across all newer JDK releases.

## 2. The scope model: `fork → join → result → close`

In Java 21, the primary class is `java.util.concurrent.StructuredTaskScope<T>`. A typical lifecycle looks like this:

~~~text
Calling thread (owner)
│
├─ Open StructuredTaskScope with try-with-resources
│   ├─ fork(task A) → child thread A ─────┐
│   ├─ fork(task B) → child thread B ─────┤ run concurrently
│   ├─ join()/joinUntil(...) ◀────────────┘
│   ├─ inspect results / handle errors
│   └─ close() upon exiting try
└─ Continue after the scope is closed
~~~

The steps and their meanings:

1. **Open the scope:** create a scope object on the calling thread, referred to as the *owner*. In Java 21, the default constructor creates a **virtual thread** for each subtask.
2. **`fork(Callable)`:** runs a subtask in its own thread and returns a `Subtask` object (some examples use the `Supplier<T>` type because `Subtask<T>` also provides `get()`). After `fork`, the two tasks can make progress concurrently.
3. **`join()` / `joinUntil(Instant)`:** the owner waits for results according to the scope's policy. `joinUntil` applies an absolute deadline and may throw `TimeoutException`.
4. **Inspect results and errors:** with a policy that requires all tasks to succeed, `throwIfFailed()` prevents reading results as if everything succeeded when a task has failed.
5. **`close()`:** `try-with-resources` closes the scope, waiting for any remaining live child threads to finish when necessary. `close` must not be mistaken for forcibly killing a task that refuses to terminate.

Skeleton code for Java 21:

~~~java
try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
    var first = scope.fork(() -> loadFirst());
    var second = scope.fork(() -> loadSecond());

    scope.join().throwIfFailed();

    return combine(first.get(), second.get());
}
~~~

The snippet above is **illustrative only**: `loadFirst()`, `loadSecond()`, and `combine(...)` are application functions not defined in the snippet. Section 4 provides a standalone Java 21 program with deterministic stdout.

Unlike calling `Thread.startVirtualThread(...)` directly and discarding the thread reference, a scope establishes a parent/child relationship and a shared synchronization point. Unlike sequential calls, subtasks within a scope can still execute in parallel with one another.

### A scope is an ownership boundary, not just a list of threads

- The thread that creates the scope is called the **owner**; coordination operations such as `join` and `close` must be performed by the owner.
- Scopes can be **nested**: a subtask of a parent scope can open a child scope, forming a tree-structured hierarchy of work.
- When a scope is used with `try-with-resources`, exiting the block—whether normally or via an exception—still invokes `close`.
- After `join` completes and the necessary results have been processed, there is no business reason to keep the scope alive.
- Closing the scope prevents leaking threads belonging to that scope, but it can complete quickly only if subtasks respond to interruption/cancellation.

## 3. Two key policies in Java 21

Java 21 provides two preview subclasses to express completion rules for a group of tasks.

| Aspect | `ShutdownOnFailure` | `ShutdownOnSuccess<T>` |
|---|---|---|
| Suitable use case | **All results are required**; one failing task fails the entire operation | **Only one successful result is needed** among multiple alternatives |
| When it short-circuits | When the first subtask fails | When the first subtask succeeds |
| Behavior toward remaining subtasks | Requests shutdown, **interrupts** unfinished threads | Requests shutdown, **interrupts** unfinished threads |
| `join()` | Waits until all complete or a failure triggers scope shutdown | Waits until one subtask succeeds or all complete |
| Retrieving results | After `join().throwIfFailed()`, call `Supplier.get()` on each subtask | After `join()`, call `scope.result()` |
| All subtasks fail | `throwIfFailed()` throws an exception | `result()` throws an exception because there is no successful result |
| Semantic contract | Result components must be consistent; missing any component is an error | Alternative solutions; a single solution suffices |

### When all results are required: `ShutdownOnFailure`

Consider building a profile consisting of a name and points. If fetching the name fails, having points alone cannot produce a valid profile. `ShutdownOnFailure` proactively reports the failure and requests the remaining work to stop.

~~~java
try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
    var name = scope.fork(() -> "Lan");
    var points = scope.fork(() -> 120);

    scope.join().throwIfFailed();
    String summary = name.get() + ": " + points.get();
    System.out.println(summary);
}
~~~

After `join().throwIfFailed()`, both subtasks have succeeded, so calling `get()` is safe. With the Java 21 API, `throwIfFailed()` throws `ExecutionException` when a subtask fails; the original cause is typically in `getCause()`. Alternatively, the `throwIfFailed(Function<Throwable, ? extends X>)` overload lets you construct a custom exception that fits your application's contract.

### When only one good result is needed: `ShutdownOnSuccess<T>`

Consider reading equivalent data from a cache and a fallback replica:

~~~java
try (var scope = new StructuredTaskScope.ShutdownOnSuccess<String>()) {
    scope.fork(() -> readCache());
    scope.fork(() -> readReplica());

    scope.join();
    return scope.result();
}
~~~

Here `readCache()` and `readReplica()` are illustrative functions already present in the application. The result is **the first task to complete successfully**—not necessarily the task that was `fork`ed first, nor the task that *finishes first if it fails*. If one task fails first, the scope continues waiting for the remaining task to succeed. If all fail, `scope.result()` throws `ExecutionException`. Other read calls are requested to stop once one succeeds, though there is no guarantee they will stop instantaneously.

**Choose the policy based on business semantics before choosing how to run threads.** For a request that needs both A and B, using `ShutdownOnSuccess` is semantically wrong; for two alternative sources where only one is needed, `ShutdownOnFailure` may fail prematurely while the other source is still working.

## 4. A standalone, verifiable Java 21 program

Create the file **`StructuredConcurrencyDemo.java`**:

~~~java
import java.time.Instant;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

public class StructuredConcurrencyDemo {
    static String combine() throws InterruptedException, ExecutionException {
        try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
            Supplier<String> name = scope.fork(() -> "Lan");
            Supplier<Integer> points = scope.fork(() -> 120);
            scope.join().throwIfFailed();
            return name.get() + ": " + points.get();
        }
    }

    static String firstSuccess() throws InterruptedException, ExecutionException {
        try (var scope = new StructuredTaskScope.ShutdownOnSuccess<String>()) {
            scope.fork(() -> "cache");
            scope.fork(() -> {
                Thread.sleep(1000);
                return "remote";
            });
            scope.join();
            return scope.result();
        }
    }

    static String firstFailure() throws InterruptedException {
        try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
            scope.fork(() -> { throw new IllegalStateException("bad data"); });
            scope.fork(() -> {
                Thread.sleep(1000);
                return "slow";
            });
            try {
                scope.join().throwIfFailed();
                return "unexpected";
            } catch (ExecutionException ex) {
                return ex.getCause().getClass().getSimpleName();
            }
        }
    }

    static String timeout() throws InterruptedException, ExecutionException {
        try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
            Supplier<String> slow = scope.fork(() -> {
                Thread.sleep(500);
                return "late";
            });
            try {
                scope.joinUntil(Instant.now().plusMillis(20));
                scope.throwIfFailed();
                return slow.get();
            } catch (TimeoutException ex) {
                scope.shutdown();
                scope.join();
                return "timeout";
            }
        }
    }

    static boolean usesVirtualThread() throws InterruptedException, ExecutionException {
        try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
            Supplier<Boolean> child = scope.fork(
                    () -> Thread.currentThread().isVirtual());
            scope.join().throwIfFailed();
            return child.get();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println(combine());
        System.out.println(firstSuccess());
        System.out.println(firstFailure());
        System.out.println(timeout());
        System.out.println(usesVirtualThread());
    }
}
~~~

Use an **actual JDK 21** to compile and run the preview API:

~~~bash
javac --enable-preview --release 21 -encoding UTF-8 StructuredConcurrencyDemo.java
java --enable-preview StructuredConcurrencyDemo
~~~

Program **stdout**:

~~~text
Lan: 120
cache
IllegalStateException
timeout
true
~~~

The Java 21 compiler may also print `Note: ... uses preview features of Java SE 21` to the diagnostic stream; that is not part of the program's stdout.

Walk through the five scenarios in order:

1. **`combine()`**: both callables complete successfully; the results are combined after `join().throwIfFailed()`, printing `Lan: 120`.
2. **`firstSuccess()`**: the cache callable returns immediately while the other sleeps for 1 second; the winning result is `cache`, and the slow callable receives an interrupt signal when the scope shuts down.
3. **`firstFailure()`**: one callable throws `IllegalStateException`; `throwIfFailed()` throws `ExecutionException` wrapping that `cause`; the result prints the original exception's class name.
4. **`timeout()`**: waits until an `Instant` about 20 ms after the call, while the task sleeps for 500 ms. Upon expiration, the code calls `shutdown()` and `join()` to ensure a clean scope close, then returns `timeout`.
5. **`usesVirtualThread()`**: the thread created by the Java 21 scope by default is a virtual thread, so it prints `true`.

To keep stdout deterministic, the program does not print from inside subtasks and does not depend on the completion order of two distinct results. `Thread.sleep` responds to interruption, so the short-circuit path and scope closing complete normally. In real applications, an I/O task that does not respond to cancellation can make closing the scope take much longer.

**Do not compile this with JDK 17:** neither virtual threads (`Thread.isVirtual()`) nor Java 21's Structured Concurrency preview exist there. The `--enable-preview --release 21` flags must also be run with a **JDK 21** compiler; you cannot ask `javac` from a newer JDK to compile JDK 21's preview features simply by changing `--release`.

## 5. `join`, exceptions, and correctness

### `join()` does not mean every task succeeded

The purpose of `join()` is to bring the owner to the scope's synchronization point. With `ShutdownOnFailure`, it may return when one task fails, even before other tasks have actually stopped running. Therefore, calling `scope.join()` and immediately reading every `get()` without checking the failure policy can lead to incorrect assumptions.

The correct pattern for the "all required" case is:

~~~java
scope.join().throwIfFailed();
var a = first.get();
var b = second.get();
~~~

`throwIfFailed()` checks for errors recorded by the policy. When it throws an exception, the subsequent code does not execute. An error inside a callable is still a real business failure; structured concurrency helps propagate and group errors by lifecycle, rather than fixing errors or providing fallbacks automatically.

### `joinUntil(Instant)` only bounds the wait time

~~~java
try {
    scope.joinUntil(Instant.now().plusSeconds(2));
    scope.throwIfFailed();
} catch (TimeoutException ex) {
    scope.shutdown();
    scope.join();
    throw ex;
}
~~~

This snippet illustrates code inside a `try` block that has already opened a `ShutdownOnFailure` scope, and is **not standalone**. `joinUntil` takes an **absolute point in time** (`Instant`), not a `Duration`. If the deadline expires, it throws `TimeoutException`, and the application must decide on the cancellation/cleanup policy. `scope.shutdown()` requests interruption of unfinished threads, while `scope.join()` ensures the owner follows the coordination protocol before closing the scope.

The deadline is **not a guarantee** that the parent method will always return in exactly two seconds: `close()` still waits for live tasks to finish, including tasks that ignore interruption. For external I/O communication, configure separate deadlines/timeouts on the actual client or operation API.

### `InterruptedException` is a control signal

`join()`, `joinUntil(...)`, and other waiting operations can throw `InterruptedException`. If the owner thread is interrupted, `try-with-resources` still calls `close` to terminate the scope. If code catches `InterruptedException` without propagating it, restore the interrupt flag when appropriate:

~~~java
try {
    doInterruptibleWork();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

This snippet only illustrates how to handle `doInterruptibleWork()` when it is an interruptible task inside a `void` method. If a method can declare `throws InterruptedException`, it is usually better to propagate the exception to the caller. Do not swallow an interrupt and continue an infinite loop; scopes requesting shutdown will be delayed or never terminate.

### Owner and operation ordering

The `join`/`joinUntil`/`close` methods are meant for the owner thread. Certain calls to a scope from an invalid thread may be rejected. Do not pass a scope object to an independent request and attempt to close it from another thread. Operations using `Subtask.get()` and `Subtask.exception()` also enforce state/owner checks; in typical usage, wait for `join` and verify success before reading results.

Forking tasks and exiting the `try` block without calling `join` is improper usage: Java 21 enforces structural checks, and `close()` may throw `IllegalStateException`. Structure your code so every normal path reaches `join`, while error/timeout paths handle shutdown and cleanup explicitly.

## 6. Cancellation within a scope: cooperative, not forced

`StructuredTaskScope.shutdown()` is designed to:

1. Prevent new tasks from being started in a shut-down scope.
2. Send an **interrupt** to running child threads that have not yet finished (excluding the current thread where appropriate).
3. Wake up the owner waiting in `join`/`joinUntil` to handle the group's state.

**Interruption is a cooperative request.** If a subtask calls `Thread.sleep`, `BlockingQueue.take`, or an interruptible API, it can usually exit promptly. If a subtask runs code that ignores interrupts, loops without checking the interrupt flag, or performs I/O without effective cancellation support, the thread may keep running. In that case, `close()` must wait.

Example of a subtask designed to cooperate with cancellation:

~~~java
static long countUntilInterrupted() {
    long count = 0;
    while (!Thread.currentThread().isInterrupted()) {
        count++;
        // In practice, interleave useful work with cancellation checks.
    }
    return count;
}
~~~

This method compiles standalone as a static method, but it **has no automatic stopping point**; it exits only when the thread is actually interrupted. Do not use a CPU-bound loop like this in real applications to wait for a condition; here it merely demonstrates the `isInterrupted()` flag. Real tasks must avoid busy-waiting and ensure resource cleanup in their own `finally` or `try-with-resources` blocks.

Suppose a callable has already sent a write request to another service. After a sibling fails, the scope can interrupt the callable waiting for a response, but it **does not roll back the external transaction**. Interrupting a Java thread does not mean the remote side stops processing either. Therefore, for operations with side effects, you need appropriate business mechanisms: idempotency, transactions, I/O deadlines, or compensating states.

## 7. Relationship to Virtual Threads and other concurrency APIs

**Virtual Threads** and **Structured Concurrency** solve two different problems:

- **Virtual threads:** provide threads much lighter than OS threads for suitable blocking I/O workloads, making it practical to create large numbers of threads in a synchronous style.
- **Structured Concurrency:** manages **lifecycle relationships, results, errors, and cancellation** across a group of subtasks. It uses virtual threads by default, but the structural concept does not depend exclusively on virtual threads.

In Java 21, `StructuredTaskScope`'s default constructor uses virtual threads. A constructor accepting a `ThreadFactory` lets you choose the thread type as needed. However, `Thread.ofVirtual()` by itself does **not** provide a scope, aggregate errors, or wait for child threads in a structured way.

| Tool | Primary role | What you must manage yourself |
|---|---|---|
| `Thread.startVirtualThread(...)` | Starts a single virtual thread | Waiting for threads, error propagation, cancellation, and parent/child ownership |
| `Executors.newVirtualThreadPerTaskExecutor()` | Executes tasks, one virtual thread per task | Task group conventions, result selection, error handling, and sibling cancellation |
| `CompletableFuture` | Represents and composes async pipelines, callbacks, and exceptions | Lexical parent/child task relationship, background execution cancellation, ownership |
| `StructuredTaskScope` (Java 21 preview) | Groups related subtasks into a scope with join/shutdown policies | Business logic, I/O timeouts, load limiting, and side effects |

`CompletableFuture` remains useful for long pipelines or dependency graphs, asynchronous responses spanning multiple layers, or callbacks driven by external events. Structured Concurrency is most valuable when an operation **splits into multiple subtasks that must be gathered back together before leaving the scope**. There is no need to convert every future and executor into a scope; choose the construct that expresses the lifecycle contract most clearly.

### Structured Concurrency is not a concurrency-limiting mechanism

Forking thousands of subtasks with virtual threads does not mean a database or external API can handle thousands of concurrent queries. **Connection limits, quotas, pools, rate limits, and backpressure** remain design responsibilities. A scope organizes tasks; it does not decide a safe concurrency level on its own. For very large fan-outs, pair the scope with a load-limiting mechanism.

### Relationship to Scoped Values

The parent/child structure allows child virtual threads to inherit `ScopedValue` bindings established at the point the scope is created, following Java 21 rules. `ScopedValue` is also a preview API in Java 21 and is useful for passing immutable data down a call scope. It is not a mechanism for automatically sharing mutable variables, nor does it replace synchronization for shared state between subtasks.

## 8. Specific limitations of Structured Concurrency preview in Java 21

### 8.1. The API is still experimental

- Java 21 introduces this preview under **JEP 453**. To use it, source code must be compiled and run with the corresponding `--enable-preview` flags.
- Preview APIs may change signatures, usage conditions, or be withdrawn in later releases. An application using a preview API must be re-verified when upgrading the JDK.
- Do not write documentation for Java 21 learners using API signatures from newer JDKs. For example, JDK 25 has a preview `StructuredTaskScope<T,R>` interface and `StructuredTaskScope.open(...)` method, whereas the **JDK 21** examples in this article use `new StructuredTaskScope.ShutdownOnFailure()` and `new StructuredTaskScope.ShutdownOnSuccess<T>()`. They belong to different API versions.
- Run `java -version` and `javac -version` to verify that both runtime and compiler match the preview syntax being used.

### 8.2. Cancellation is not guaranteed to be instantaneous

`shutdown()` primarily interrupts child threads. `close()` may block waiting for code that does not cooperate with interruption. No API on the scope guarantees safely killing an external write, stopping a native call, or reverting side effects.

### 8.3. No "fire-and-forget" by design

If a task must continue living independently after the parent operation returns, do not keep it inside a scope and skip `join`. That is not a structured fan-out/fan-in problem. Use a component with an explicit lifecycle instead (such as a separately managed executor/service), with an appropriate shutdown and monitoring policy.

### 8.4. Does not replace all coordination mechanisms

A scope is not a queue scheduler, does not throttle bandwidth, does not retry automatically, does not guarantee completion order, and does not turn callables into distributed transactions. Nor does it make CPU-bound tasks run faster than the available cores; actual parallelism still depends on CPU, I/O, and external non-JVM resources.

### 8.5. Does not automatically ensure shared-data safety

Two subtasks writing to the same mutable object can still cause a race condition. Use immutable data, synchronization, concurrent collections, or other state-sharing mechanisms as needed. `join` establishes a completion point and happens-before relationship; it does not make unsafe updates atomic.

### 8.6. Scopes are not portable across all JDK versions

For libraries that must support multiple Java versions—especially projects with a baseline lower than Java 21—depending on a preview feature carries a clear cost. Decide on version support before choosing the API. If preview features are unacceptable in production, use `ExecutorService`, `Future`, `CompletableFuture`, or a compatible platform and manage the lifecycle manually, even though it takes more steps.

## 9. Applying it with discipline

A practical design checklist:

1. **Define the unit of work:** for example, building a report or aggregating a response; clearly identify the parent task and the subtasks that must share its lifetime.
2. **Choose the policy:** whether all results are mandatory (a failure fails the entire request) or only one successful source is needed.
3. **Plan deadlines:** determine the total time budget as well as timeouts for I/O resources. `joinUntil` bounds the wait, but account for cleanup time too.
4. **Design cooperative cancellation:** callables must respond to interrupts, use `try/finally` to close resources, and avoid masking the root cause of errors.
5. **Limit fan-out:** when the task count is large or a downstream source has a low quota, add concurrency limits instead of forking unboundedly.
6. **Return results only after a valid state:** call `join` then `throwIfFailed` or `result` depending on the policy; never use a value not known to have succeeded.
7. **Observe behavior:** record parent operation latency, failed/cancelled task counts, and data sources; you can inspect the thread tree in a JDK thread dump to locate running subtask groups.
8. **Verify with the right JDK:** validate Java 21 preview sources with JDK 21 during builds, and re-check them as part of any version upgrade plan.

With nested scopes, a cancellation request from an ancestor can propagate down to subtasks via interruption and scope structure; however, **how quickly it finishes depends on whether subtasks respond to cancellation**. Design each layer as a responsible owner, avoiding child scopes that keep operations alive longer than intended.

### Common mistakes

- **Calling `fork` without `join`:** breaks the lifecycle contract and can throw an exception when closing the scope.
- **Using `ShutdownOnSuccess` when all components are required:** allows returning early with incomplete data.
- **Forgetting `throwIfFailed`:** ignores a failure in a forked task and treats the aggregate as successful.
- **Assuming `close()` always returns immediately:** tasks that ignore interrupts can stall closing.
- **Catching and swallowing `InterruptedException`:** slows down cancellation or prevents it from working.
- **Running Java 21 preview code on a compiler/runtime of a different release:** causes missing-API or syntax-mismatch errors.
- **Assuming virtual threads eliminate race conditions:** virtual threads still access shared memory under the Java Memory Model rules.
- **Forking too many queries without limits:** easily exhausts connection pools or exceeds upstream quotas.
- **Confusing a timeout with a rollback:** a deadline does not undo writes already committed to an external system.

## 10. Self-check questions

**1. Tasks A and B are both required to produce a result, and B fails. Which policy should be used?**  
`ShutdownOnFailure`, because the operation needs both; B's failure requests stopping A, which is no longer needed, and reports failure. A may take some time to respond to the interrupt.

**2. Three servers return the same data, and only one successful response is needed. What happens if the first server fails but the second succeeds?**  
`ShutdownOnSuccess` keeps waiting until one succeeds; `result()` returns the winning result. The first server's failure does not automatically fail the scope.

**3. Does `joinUntil` throwing `TimeoutException` guarantee that all tasks have stopped?**  
No. The owner must decide to call `shutdown` and complete cleanup. `close` may still have to wait for tasks that refuse to stop.

**4. Does using `Thread.startVirtualThread` automatically give you structured concurrency?**  
No. Virtual threads are a type of thread; structured concurrency provides lifecycle bounds and policies for a group of tasks.

**5. Can you copy an example using Java 21 constructors directly to Java 25, enable preview, and expect it to run?**  
You should not assume so: the preview API has changed. Check the Java API Specification and JEP for the version you are using, update the code, and run tests.

## 11. Primary references for version comparison

- [Oracle Java 21 — Structured Concurrency](https://docs.oracle.com/en/java/javase/21/core/structured-concurrency.html): guide to the `fork`, `join`, `close` model and completion policies.
- [Java 21 API — StructuredTaskScope](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): signatures and semantics of the Java 21 preview API.
- [OpenJDK JEP 453 — Structured Concurrency (Preview)](https://openjdk.org/jeps/453): background and design goals for Java 21.
- [Java 25 API — StructuredTaskScope](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): reference for comparing API evolution across releases.

Structured Concurrency clarifies **who owns the tasks, when results are used, and who is responsible on error or cancellation**. Its main strength is structured lifecycle scoping; overall correctness still depends on choosing the right policy, cooperative cancellation, resource limits, and real-world business constraints.
