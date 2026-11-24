# Never Hold Locks While Waiting on I/O or Dependent Tasks

## 1. The Problem in Stateful Beans

A Spring bean defaults to `singleton` scope: within a single `ApplicationContext`, there is normally one bean object shared across multiple request-processing threads. **Singleton does not mean thread-safe.** If the bean has mutable fields (`mutable state`), multiple threads can concurrently read or write those fields.

To protect shared data, we can use `synchronized`, `ReentrantLock`, atomic types, or concurrent data structures. However, protecting a variable correctly is not enough: **how long a lock is held also determines the application's responsiveness.**

Suppose a bean both manages state and makes HTTP calls, reads files, queries a database, or waits for another task to finish:

```text
Thread A: acquire lock ---- HTTP call / wait Future ............. update ---- release lock
Thread B:                   wait lock ........................... fast update
Thread C:                   wait lock ........................... read state

Lock hold duration of A ≈ external wait time + update time.
```

While A holds the lock waiting, B and C can be blocked even though the state manipulation itself takes negligible time. Network waits, I/O, or another task's scheduling latency are typically orders of magnitude longer and far less predictable than in-memory updates.

**Design principle:** Hold a lock only across the section truly needed to protect shared state or invariants (the `critical section`). Perform potentially blocking operations outside the lock; then reacquire the lock briefly to validate and publish the result.

This lesson focuses on **in-process Java locks** on stateful beans. Database row locks, transactions, and distributed locks are separate mechanisms; they relate to performance, yet cannot substitute for one another.

## 2. Why Is Waiting While Holding a Lock Dangerous?

### 2.1. Lock Contention and Latency Spikes

With `synchronized (guard)`, only one thread can own `guard`'s monitor at a time. With `ReentrantLock`, only the thread holding the lock can stay inside the protected region. Other threads needing the same lock must wait.

An 800 ms HTTP request inside a `synchronized` block means operations needing only 1 ms on **the same lock** may have to wait for most of those 800 ms. This is `lock contention`, which can build long queues and sharply inflate response times as request volume rises.

No universal timeout number guarantees safety: even normally fast I/O can turn abnormally slow under network congestion, pool exhaustion, load spikes, or external service failures.

### 2.2. Failure Propagation and Unfairness

One slow operation can stall unrelated tasks if everything shares a global lock. Threads sitting idle waiting for the lock also consume resources (such as server worker threads). `synchronized` does not guarantee serving waiting threads in arrival order.

Under heavy load, a dependency chain can form: many requests wait on the monitor, workers get tied up, other tasks cannot run on time, and the original requests keep waiting. Thus, holding a lock while waiting can amplify a minor glitch into an application-wide bottleneck.

### 2.3. Deadlock When Waiting on a Task That Needs the Same Lock

An even more dangerous case is when A **holds a lock** and calls `Future.get()` or `CompletableFuture.join()` to wait for B, while B must acquire **that same lock** to finish.

```text
Thread A:
  already holds monitor M
  |
  +--> waits for B's Future result
                ^
                |
Thread B: needs monitor M to finish
                |
                +---- M is still held by A

A waits for B; B waits for A to release M => circular wait (deadlock).
```

The risk is not limited to `Future`. A callback, background task, or logic in another bean may also need to call back and update the locked state. Whenever a resource-wait cycle forms, deadlock becomes possible.

Deadlock differs from ordinary lock contention: contention clears once the lock holder finishes; a circular-wait deadlock cannot make progress on its own without timeouts, interrupts, cancellations, or external intervention.

## 3. Operations You Should Not Perform While Holding a Lock

| Operation | Example | Harm if holding a lock |
|---|---|---|
| Synchronous HTTP or RPC calls | `HttpClient.send(...)`, remote API calls | Network latency and external failures stretch the critical section |
| Potentially blocking I/O | File read/write, sockets, database calls | Waiting on devices, connections, pools, or services |
| Waiting on dependent tasks | `Future.get()`, `CompletableFuture.join()` | The awaited task may need the lock currently held |
| Waiting on threads or signals | `Thread.join()`, `CountDownLatch.await()` | The signaling thread may need the locked state itself |
| Waiting on queues or resources | `BlockingQueue.take()/put()` | Wait duration is hard to bound |
| Sleeping inside a lock | `Thread.sleep(...)` | Sleeping does not release held monitors or `ReentrantLock`s |
| Calling arbitrary code/callbacks | Listeners, plugins, opaque hooks | May re-enter, block, call the network, or create unexpected dependencies |

These are signals to review **lock boundaries**, not a claim that all the APIs above always block. For instance, `Future.get()` can return immediately if the task is already done; yet safe design must not depend on that lucky case.

**Important distinction:** `Object.wait()`, when called properly inside `synchronized`, **temporarily releases the monitor of the waited-on object** while waiting and reacquires it before returning. `Condition.await()` likewise releases its corresponding `ReentrantLock` while waiting. These are state-coordination mechanisms with explicit condition-checking protocols; never confuse them with `Thread.sleep()`, `Future.get()`, or HTTP I/O, which **do not release any locks you hold**. Even with `wait()`/`await()`, if you still hold *other* locks, those other locks are not released automatically.

## 4. Bad Example: Holding a Monitor During an HTTP Call

The following Spring bean example uses a monitor to protect the character count received across requests. Because the HTTP call sits inside `synchronized`, a slow connection holds the lock far longer than necessary.

**Illustrative code using Spring and Java 17**, not a standalone runnable program; requires Spring on the classpath and a URI to a real server:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.springframework.stereotype.Service;

@Service
public class SlowLockedBean {
    private final Object guard = new Object();
    private final HttpClient httpClient = HttpClient.newHttpClient();
    private long totalCharacters;

    public long fetchAndRecord(URI uri)
            throws IOException, InterruptedException {
        synchronized (guard) {
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .GET()
                    .build();

            HttpResponse<String> response = httpClient.send(
                    request, HttpResponse.BodyHandlers.ofString());

            totalCharacters += response.body().length();
            return totalCharacters;
        }
    }
}
```

`totalCharacters += ...` is the operation that needs protection because multiple requests modify the variable concurrently. However, `httpClient.send(...)` does not need the monitor to download data: placing it inside the lock only forces other requests to wait through network time.

The `synchronized (guard)` block in this example also means every call shares **one lock on the same bean**. If the bean has other methods using `guard`, those methods suffer too. `httpClient.send` can throw `IOException` or `InterruptedException`; Java still releases the monitor automatically upon exiting `synchronized` due to an exception, yet other requests still had to wait until that point.

## 5. The Fix: I/O Outside, State Update in a Short Critical Section

When merely accumulating character counts, perform the HTTP fetch first and use the monitor only for the brief update:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.springframework.stereotype.Service;

@Service
public class ShortLockedBean {
    private final Object guard = new Object();
    private final HttpClient httpClient = HttpClient.newHttpClient();
    private long totalCharacters;

    public long fetchAndRecord(URI uri)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        // May take a long time, yet does not hold guard.
        HttpResponse<String> response = httpClient.send(
                request, HttpResponse.BodyHandlers.ofString());
        long delta = response.body().length();

        // Lock only the part updating the shared variable.
        synchronized (guard) {
            totalCharacters += delta;
            return totalCharacters;
        }
    }
}
```

Why is this version better?

1. Multiple requests can perform I/O independently without waiting on the same monitor.
2. Updates to `totalCharacters` remain serialized under the lock, so no updates are lost from overlapping additions.
3. If the HTTP call fails, the total variable is untouched. The monitor is never held during the external wait.
4. The returned value is the total **at the moment that request finishes updating**; network completion order and increment order can differ from request arrival order.

This example is valid because the I/O result **does not depend on a previously read state version**. You cannot mechanically "move everything out of the lock" if reading state, calling externally, and writing back must preserve an end-to-end invariant. That case needs the version-checking mechanism covered next.

A common design pattern is:

```text
Phase A — under lock:
    Read needed snapshot, allocate ID, check condition at read time
          |
          v
Release lock — external wait:
    HTTP / database / file / Future / expensive computation
          |
          v
Phase B — reacquire lock:
    Verify state is still valid, merge or reject result,
    update shared invariant
          |
          v
Release lock — respond/notify
```

In some problems, phase A needs no lock if state is read-only and safely published; in others, phase B can use `AtomicLong` or a concurrent structure instead of a monitor. The core rule is holding protection only where needed.

## 6. Java 17 Experiment: Fast Operations Still Run While Slow Tasks Wait

The runnable example below uses `CountDownLatch` in place of a real network. The latches hold the slow task at a wait point **outside the monitor** and prove that a fast update can still acquire the lock. Unlike tests relying on `Thread.sleep`, ordering is coordinated via signals so results do not depend on machine speed.

**File `LockBoundaryDemo.java`**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class LockBoundaryDemo {
    static final class StateBean {
        private final Object guard = new Object();
        private final List<String> history = new ArrayList<>();

        void slowOperation(CountDownLatch started,
                           CountDownLatch allowFinish)
                throws InterruptedException {

            // Represents the start of waiting on external I/O.
            started.countDown();
            allowFinish.await();  // Does not hold guard here.

            synchronized (guard) {
                history.add("slow");
            }
        }

        void quickUpdate() {
            synchronized (guard) {
                history.add("quick");
            }
        }

        List<String> snapshot() {
            synchronized (guard) {
                return List.copyOf(history);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        StateBean bean = new StateBean();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch allowFinish = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            Future<?> slow = executor.submit(() -> {
                try {
                    bean.slowOperation(started, allowFinish);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                            "Slow task was interrupted", interrupted);
                }
            });

            started.await();

            Future<?> quick = executor.submit(bean::quickUpdate);
            quick.get();
            System.out.println(bean.snapshot());

            allowFinish.countDown();
            slow.get();
            System.out.println(bean.snapshot());
        } finally {
            allowFinish.countDown();
            executor.shutdown();
        }
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac LockBoundaryDemo.java
java LockBoundaryDemo
```

Expected output:

```text
[quick]
[quick, slow]
```

Explanation:

- `started.await()` guarantees `main` knows the slow task reached the wait-signal point. `allowFinish` is still closed, so the slow task **cannot** add `slow` to the list yet.
- `quick.get()` only finishes after the fast task acquired `guard`, appended `quick`, and released the lock.
- `main` prints the first snapshot before the slow task's latch is opened, so it contains only `[quick]`.
- Once `allowFinish.countDown()` fires, the slow task resumes, briefly acquires the monitor, and appends `slow`. `slow.get()` ensures that update completes before printing the final line.
- `List.copyOf(history)` is created **inside the lock** to obtain a stable copy. Callers never hold a reference to the internal `ArrayList` and need not hold the lock while using the copy.

What matters is not that two threads necessarily execute in parallel at all times, but that **the waiting task does not occupy the monitor**, allowing other tasks to update protected state.

## 7. Waiting on a Future Inside `synchronized` Can Self-Deadlock

This is a **counter-example for analysis only, not to run directly**, because the `get()` call can block forever:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;

final class CircularWaitBean {
    private final Object guard = new Object();
    private String state = "ready";

    String dangerous(ExecutorService executor)
            throws InterruptedException, ExecutionException {
        synchronized (guard) {
            Future<String> dependent = executor.submit(() -> {
                synchronized (guard) {
                    return state;
                }
            });
            return dependent.get(); // Waits for B while holding guard.
        }
    }
}
```

Suppose `executor` has an available worker: A is running `dangerous` and holds `guard`; B is submitted to the pool, yet B needs to read `state` so it must acquire `guard`. Meanwhile A calls `dependent.get()` to wait for B. Because A cannot leave `synchronized` until B finishes, the two threads form a wait cycle.

The fix is separating **waiting for the result** from **holding the lock**:

```java
// Illustrative method snippet inside CircularWaitBean:
String safer(ExecutorService executor)
        throws InterruptedException, ExecutionException {
    Future<String> dependent = executor.submit(() -> {
        synchronized (guard) {
            return state;
        }
    });

    // Do not hold guard while waiting for the result.
    return dependent.get();
}
```

This fix eliminates the wait cycle **on `guard`** in the example. Still, `get()` can wait a long time or indefinitely if task B itself hangs. For explicit time bounds, use `get(timeout, TimeUnit.SECONDS)`, handle `TimeoutException`, and consider `cancel(true)` when cancellation is genuinely needed. Timing out on `get(timeout, ...)` **does not automatically cancel** the task; `cancel(true)` also only requests interruption cooperatively.

Another variant is **executor starvation deadlock**: task A runs in a single-worker pool, submits B to **that same pool**, and calls `B.get()`. B cannot start because A occupies the sole worker; this failure can occur **even with no monitor at all**. Therefore, inspect both lock dependencies and worker-resource dependencies.

## 8. Do Not Sacrifice Correctness When Moving I/O Out of Locks

Shortening critical sections reduces contention, yet can introduce **stale-result overwrites** if state changed while the lock was not held.

Consider this flow:

```text
A: [lock] read config version 7 [release]
A:       call slow service based on version 7 ...
B: [lock] update config to version 8 [release]
A:                                        [lock] write result from version 7?
```

If A blindly writes the old result, B's newer data can be overwritten or a business invariant broken. We need **snapshot + version check + commit only if still valid**. This is in-memory `optimistic concurrency control`.

**File `VersionGuardDemo.java` — standalone Java 17 example**

```java
public class VersionGuardDemo {
    static final class StateBean {
        private final Object guard = new Object();
        private String value = "initial";
        private long version = 0;

        record Snapshot(long version, String value) {}

        Snapshot readSnapshot() {
            synchronized (guard) {
                return new Snapshot(version, value);
            }
        }

        void updateFromAnotherRequest(String newValue) {
            synchronized (guard) {
                value = newValue;
                version++;
            }
        }

        boolean publishIfUnchanged(Snapshot snapshot, String result) {
            synchronized (guard) {
                if (version != snapshot.version()) {
                    return false;
                }

                value = result;
                version++;
                return true;
            }
        }
    }

    public static void main(String[] args) {
        StateBean bean = new StateBean();

        StateBean.Snapshot before = bean.readSnapshot();
        String resultOfSlowCall = "result from old data";

        // Simulate another request updating while the external call is running.
        bean.updateFromAnotherRequest("new data");

        boolean accepted = bean.publishIfUnchanged(
                before, resultOfSlowCall);

        System.out.println("Accepted stale result: " + accepted);
        System.out.println("Final state: "
                + bean.readSnapshot().value());
    }
}
```

```bash
javac VersionGuardDemo.java
java VersionGuardDemo
```

Result:

```text
Accepted stale result: false
Final state: new data
```

The example simulates the change in a fixed order to observe the result; in a real application, two requests can run on different threads. `readSnapshot()` captures both `version` and `value` under the same monitor. After external work completes, `publishIfUnchanged(...)` checks the version and writes inside **one single locked region**. Since the version changed, the stale result is rejected.

Depending on business rules, when the version check fails you can:

- Read a fresh snapshot and **retry outside the lock**, with a bounded retry limit and ensuring the operation is safe to re-run.
- Merge results if merging is valid, such as adding an independent delta instead of overwriting the whole value.
- Return a conflict status so the caller or user can decide.
- Redesign data so two requests do not have to update the same shared field.

**You cannot build cross-system atomic transactions with `synchronized` alone.** If the external call already sent an email, transferred money, or wrote to another system, rejecting the result in the bean **does not undo** the external side effect. When side effects exist, separate computation, external system calls, and local writes; you may need idempotency keys, transactions, outboxes, or business compensation flows. That is a different problem from shrinking monitor hold times.

## 9. Using ReentrantLock Without Stretching the Locked Region

`ReentrantLock` shares the core ownership behavior: **one thread holding the lock blocks others needing the same lock**. Unlike `synchronized`, code using `ReentrantLock` must release it manually via `unlock()`, normally inside `finally`.

**Illustrative code inside a class**, assuming `lock` and `count` fields exist:

```java
private final ReentrantLock lock = new ReentrantLock();
private long count;

long recordAfterSlowOperation(long amount)
        throws InterruptedException {
    // Simulate external waiting. Do not hold lock.
    Thread.sleep(20);

    lock.lock();
    try {
        count += amount;
        return count;
    } finally {
        lock.unlock();
    }
}
```

To place this in a complete class, import `java.util.concurrent.locks.ReentrantLock`. This is an illustrative method snippet; there is no `main` and the sleep merely stands in for a slow operation.

Never write it like this:

```java
lock.lock();
try {
    Thread.sleep(20); // Wrong placement: sleeping while still holding lock.
    count++;
} finally {
    lock.unlock();
}
```

`try/finally` releases the lock on success or exception, yet **does not make holding a lock while waiting acceptable**.

When you need to read multiple mutually consistent fields, read them in a short locked section and build an immutable snapshot. When writing multiple fields together, update all of them inside the same locked section to preserve invariants. Do not split a critical section so thinly that you break state atomicity.

## 10. Spring Beans: Choosing Where to Put State and Synchronization

### 10.1. Prefer Beans Without Per-Request State

The following bean uses only local variables:

```java
import org.springframework.stereotype.Service;

@Service
public class PriceService {
    public long calculateTotal(long unitPrice, int quantity) {
        return Math.multiplyExact(unitPrice, quantity);
    }
}
```

Invocations have separate parameters and local variables, never contending on a `total` variable inside the bean. This is a Spring component snippet requiring Spring dependencies and has no `main`; `Math.multiplyExact` signals `ArithmeticException` on `long` overflow.

A stateless singleton generally scales far better than a singleton holding temporary per-request data. When shared state is required, explicitly define the **owner**, sharing scope, invariants to protect, and load bounds.

### 10.2. When Shared State Is Necessary

| Need | Potentially suitable approach | Notes |
|---|---|---|
| Independent counting | `AtomicLong` | Eliminates need for a shared monitor; related multi-field updates still need coordination |
| Per-key lookup/write | `ConcurrentHashMap` | Compound operations need proper atomic APIs such as `compute`; do not assume every call sequence is atomic |
| Multiple fields with a shared invariant | Short `synchronized` or `ReentrantLock` | Maintain one consistent locking rule for both reads and writes |
| Reading a stable snapshot | Immutable snapshot created under the lock | Never return internal mutable collections directly |
| Calling APIs, databases, or files | I/O outside the lock; commit data inside the lock | Handle timeouts, errors, idempotency, and version conflicts |
| Asynchronous processing on a pool | Appropriate `ExecutorService` or `TaskExecutor` | Avoid circular worker waits; configure capacity and queues |

**The lock object should be an internal detail** (`private final Object guard = new Object()`) so code outside the bean cannot accidentally lock on the same monitor. Putting `synchronized` on an entire instance method uses `this`'s monitor; this easily creates overly broad locks and affects unrelated calls on the same instance. A private lock expresses synchronization scope more clearly, though you must still keep critical sections short.

### 10.3. @Async and Dependent Tasks

`@Async`, when properly activated through a Spring proxy, offloads method execution to a Spring-configured executor, yet **does not** automatically make instance fields thread-safe. If a singleton bean submits a background task and then calls `Future.get()` inside `synchronized`, the task can get stuck trying to update that very bean.

Conversely, with `CompletableFuture`, non-`Async` continuations (such as `thenApply`, `thenAccept`) can run directly on the thread that completed the previous stage or the thread registering the continuation if already complete. Do not assume callbacks always run on an independent worker or are always safe to invoke from inside a locked region. Define task boundaries, update results in small synchronized blocks, and wait only after leaving locked regions.

`@Transactional` manages transaction boundaries for supported resources; it **does not** make Java fields inside a bean thread-safe. Moreover, if a transaction holds database data locks, calling a slow network service inside the transaction can stretch how long those database locks are held. These are two distinct kinds of locks, yet both cause bottlenecks when held too long.

## 11. Timeouts, Interrupts, and Cleanup

Moving I/O outside monitors prevents blocking unrelated operations unfairly, yet **does not guarantee the I/O operation itself will finish**. Potentially blocking tasks need explicit timeout and cancellation policies:

1. **Place timeouts where latency originates.** Examples: HTTP client/request timeouts, database query timeouts, or `Future.get(timeout, unit)`. Setting a timeout also requires handling expiration.
2. **Ensure `finally` releases `ReentrantLock`.** With `synchronized`, the monitor is released automatically when leaving the block; `ReentrantLock` requires `unlock()`.
3. **Preserve the interrupt signal when catching without rethrowing.** `InterruptedException` is a cooperative cancellation signal; never swallow it and keep waiting indefinitely.
4. **Do not treat `cancel` as a forced kill.** `Future.cancel(true)` requests interrupting the task, yet the task must cooperate to stop. If a task ignores interrupts or an operation is non-interruptible, it may keep running.
5. **Do not shut down pools owned elsewhere.** In Spring, container-managed shared pools normally shut down with the application context lifecycle; business code should not call `shutdown()` after each request.

Example of waiting on a `Future` **outside every bean lock**, inside a method allowed to throw `InterruptedException` and `ExecutionException`:

```java
try {
    return future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException timeout) {
    future.cancel(true);
    throw new IllegalStateException("Task timed out", timeout);
}
```

Here `future` is `Future<T>`, the method returns `T`, and corresponding types from `java.util.concurrent` are imported. This is an illustrative snippet, not a standalone program. If the calling thread is interrupted, let `InterruptedException` propagate to the layer responsible for handling it; only restore the interrupt flag with `Thread.currentThread().interrupt()` when deciding to catch and not rethrow.

**Warning:** If this code still sits **inside** `synchronized`, up to 2 seconds spent waiting on `get` is still up to 2 seconds other threads may wait for the lock. A timeout is a policy for waiting; **not** a substitute for designing lock boundaries.

## 12. Distinguishing Locks, Thread States, and Observability

When issues occur in a running environment, thread dumps and pool metrics help reveal what a thread is waiting on and whether it holds locks.

- Threads in `BLOCKED` state are typically waiting to enter a `synchronized` monitor; check who owns the lock rather than merely counting states.
- Threads in `WAITING` or `TIMED_WAITING` state may be inside `Future.get()`, `join()`, `sleep()`, or `await()`. Being in WAITING **does not prove** the thread released all monitors; inspect its stack and owned monitors.
- For `ReentrantLock`, lock-waiting details may appear through park/AQS mechanisms; thread state alone is insufficient to draw conclusions.
- Monitor wait times, timeout rates, queue depth, busy worker counts, and p95/p99 request latency. Increasing worker counts sometimes merely hides a shared lock held for too long.

A design smell worth inspecting is a bean with a single `synchronized` method that calls HTTP, writes a cache, and runs callbacks. Ask: **"Which lines actually need the lock to preserve invariants?"** Move non-lock steps outside, re-check state transition conditions, and verify with concurrent tests.

## 13. Common Mistakes and Fixes

| Mistake | Possible consequence | Fix |
|---|---|---|
| Marking an entire method `synchronized` when most of it is I/O | Every request using that bean queues up behind I/O | Lock only around state reads/writes; move I/O outside |
| Calling `Future.get()` / `join()` inside a monitor | Can deadlock with a task needing the same monitor | Submit work and wait outside the monitor; check worker dependencies |
| Using `Thread.sleep()` in a critical section to "wait safely" | Never releases lock, inflates latency | Move waiting outside lock; use condition APIs if state coordination is needed |
| Moving I/O out of the lock then writing stale results unchecked | Lost updates or overwriting newer state | Snapshot + version check / merge / retry |
| Synchronizing writers only, reading mutable fields directly | Inconsistent or stale data observed | Follow the same synchronization rules on reads; immutable snapshots |
| Returning internal mutable `ArrayList`/`HashMap` to callers | Callers mutate data bypassing the lock | Return a copy or safe access view |
| Assuming `@Async` makes a singleton bean thread-safe | Race conditions still exist | Clarify ownership and synchronization |
| Assuming `@Transactional` protects bean fields | Java memory synchronization is not guaranteed | Separate DB transactions from JVM monitors |
| Forgetting `unlock()` when an exception occurs | Other threads hang indefinitely | `lock.lock(); try { ... } finally { lock.unlock(); }` |
| Relying on timeouts to keep holding locks while waiting | Contention lasts up to the timeout | Move waiting out of the critical section |
| Too many locks or inconsistent lock acquisition order | Risk of circular lock dependencies | Fixed lock ordering rule; reduce lock scope |

## 14. Practice Exercises

### Exercise 1 — Identify Lock Boundaries

Given a singleton bean with steps: read `version`, make HTTP call using `version`, parse JSON, update `cachedData` and `version`. Specify which steps need locking; if another request changes `version` while HTTP is running, what should happen to the stale result?

**Hint:** Capture a snapshot under the lock; perform HTTP and parsing outside; reacquire the lock to check whether the snapshot still matches before committing. If not, decide to retry or return a conflict. Never assume stale results are always safe to apply.

### Exercise 2 — Read and Run LockBoundaryDemo

Run the program and explain why `quick` always prints before `slow`. Would progress still be guaranteed if `allowFinish.await()` were moved inside `synchronized (guard)` while still calling `quick.get()` before opening the latch?

**Hint:** While `slow` holds the monitor waiting on the latch, `quick` cannot acquire `guard` to finish; meanwhile `main` waits for `quick` before opening the latch. That is a circular wait. Only analyze the broken variant; do not run it without a timeout.

### Exercise 3 — Distinguish Two Kinds of Deadlock

Compare A holding monitor M and waiting on B which needs M, against A running in a single-worker pool, submitting B to that same pool, and waiting on B. Why does the second kind deadlock without any monitor?

**Hint:** Identify the resource B must wait on: the monitor in the first case, an idle worker in the second.

### Exercise 4 — Prove Newer Data Is Not Overwritten

Run `VersionGuardDemo`. If `publishIfUnchanged` were replaced by `value = result` without checking the version, how would the output differ? When can results be merged instead of rejected?

**Hint:** Final state could be overwritten by stale results. Independent additive deltas can be merged, whereas replacing a configuration derived from an older version usually requires conflict checking.

### Exercise 5 — Audit a Real Bean

For an existing bean using `synchronized` or `ReentrantLock`, list the operations inside the lock and classify them into: reading/writing shared mutable state, I/O or waiting, stateless computation, calling external code. Keep only what is needed to preserve invariants; verify with concurrent tests and examine thread dumps if contention appears.

## 15. Key Takeaways

- **Never hold a monitor or ReentrantLock while waiting on I/O, Futures, or dependent tasks**, unless there is a specific synchronization reason proven free of circular waits and unacceptable contention.
- **Short snapshot read → release lock → slow operation → short lock to validate and update** is the foundational pattern. Under concurrent changes, use version checks, merging, or appropriate retries.
- **`synchronized` protects data inside one process; it does not control networks, DB transactions, or external systems.** Never substitute it for idempotency or cross-service transactions.
- **`Future.get()` and `Thread.sleep()` do not release held locks.** `Object.wait()` and `Condition.await()` have specific lock-release mechanisms when used properly, and do not make arbitrary waiting safe.
- **Singleton beans and `@Async` do not create thread-safety automatically.** Minimize shared mutable state, use appropriate synchronization primitives, bound resources, and manage task lifecycles explicitly.
