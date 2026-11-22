# Problems When Calling Callbacks or Blocking I/O Inside `synchronized`

In Java, `synchronized` protects a **critical section** using an intrinsic monitor lock. When one thread holds the monitor, another thread that needs the same monitor must wait. This is a useful way to protect the invariants of shared state. However, if code **calls an externally provided callback** or **performs an operation that may block** inside the critical section, the monitor hold time becomes unpredictable. The consequences can include increased latency, lock contention, deadlocks, resource starvation, and hard-to-trace lifecycle bugs.

An important design principle:

> **Keep `synchronized` regions short and protect only the state operations that truly need to be atomic. Do not call uncontrolled user code or wait on long-running I/O while holding a monitor, unless the contract and rationale have been clearly proven.**

This article belongs to the **Synchronization** section of **general Java concurrency**. The examples use Java SE 17+ (`Thread`, monitors, `java.util.concurrent`, callbacks, and common blocking operations), without using Spring Framework-specific synchronization mechanisms.

## 1. What Does `synchronized` Lock and for How Long?

Example:

```java
synchronized (monitor) {
    updateSharedState();
    slowOperation();
}
```

This is an illustrative snippet; `monitor` and the methods are undeclared. A thread entering the block must acquire the **monitor of that exact `monitor` object**. The monitor is held from entry until exiting the block, including when a `return` or exception causes control to leave the block. The JVM guarantees that the intrinsic lock is released when control flow leaves the `synchronized` region.

Three forms to distinguish:

| Syntax | Monitor held |
| --- | --- |
| `synchronized (lock) { ... }` | The `lock` object itself |
| `synchronized void method() { ... }` | `this` of the instance |
| `static synchronized void method() { ... }` | The corresponding `Class` object |

Different monitors **do not automatically exclude one another**. If two methods protect the same invariant but lock on two different objects, they do not have proper mutual exclusion.

Beyond mutual exclusion, `synchronized` also carries Java Memory Model semantics: **an unlock on a monitor happens-before every subsequent lock on that same monitor**. Writes before the unlock are properly published to the thread that next acquires the lock, provided all access paths follow the same locking protocol.

**`synchronized` does not know on its own which operations will be slow.** If code inside the locked region sleeps for 10 seconds, makes a 30-second network call, or waits for a callback that never returns, the lock continues to be held during that time. The lock wait time of other threads grows with how long the lock owner has not exited the locked region.

## 2. Why Are Callbacks a Particularly Dangerous Boundary?

A **callback** is code invoked through an object, interface, lambda, or listener whose logic may lie outside the control of the current class.

Anti-pattern example:

```java
final class UnsafeNotifier {
    private final java.util.List<java.util.function.Consumer<String>>
            listeners = new java.util.ArrayList<>();

    public synchronized void addListener(
            java.util.function.Consumer<String> listener) {
        listeners.add(listener);
    }

    public synchronized void publish(String event) {
        for (var listener : listeners) {
            listener.accept(event); // Calling uncontrolled code under the `this` monitor.
        }
    }
}
```

The class above is an illustrative example without a `main` method. It may synchronize access to `listeners`, yet **it holds the notifier's monitor while executing `listener.accept(event)`**. A client-registered listener can:

- Perform very slow synchronous logging or I/O.
- Wait on `Future.get()`, `Thread.join()`, `CountDownLatch.await()`, or another task.
- Call back into `publish` or `addListener` (reentrancy).
- Call another component that holds its own lock, creating a risk of **lock-order inversion**.
- Register or unregister a listener during iteration.
- Throw an unchecked exception and abort the dispatch pass partway through.
- Call a closed API or initiate a `shutdown` operation that introduces a wait cycle.

Therefore, the promise of a "thread-safe notifier" holds only if the class also handles **callback policy**, **lifecycle**, and the **synchronization protocol** across all branches. Locking to protect the `listeners` structure does not mean callbacks are safe.

## 3. Risk 1: Lock Contention and Lock Convoy

Consider the sequence:

```text
Thread A                       Thread B                  Thread C
--------                       --------                  --------
lock notifier
update list
call slow listener
    |
    |                         call addListener()
    |                         -> wait for monitor
    |                                                     call snapshot()
    |                                                     -> wait for monitor
    |
listener returns
unlock notifier
                              acquires monitor ...
```

While the slow listener runs, threads B and C cannot enter `synchronized` regions that use the same monitor. They may remain in the `BLOCKED` state waiting for the intrinsic monitor; if there are many callers, wait times pile up, creating a **lock convoy** or prolonged contention.

This does not mean the JVM is deadlocked. If the callback returns, the system can continue. However, **the latency of calls unrelated to the callback** is still stretched because they are forced to queue behind that callback.

For example, if `getStatus()` only reads an integer and is declared `synchronized` on the same object, it can still be blocked by a listener performing an HTTP request even though the read operation needs very little time.

**Severity depends on the contract:** in a simple internal utility where callbacks are extremely short and controlled, holding the lock might be acceptable; in a public API accepting arbitrary callbacks, this is a high-risk assumption and should be avoided.

## 4. Risk 2: Callback Waiting on Another Thread That Needs the Same Monitor — Deadlock

An example that creates a self-inflicted wait cycle:

```text
Thread A (holds monitor M)
  -> calls callback under lock M
     -> callback submits task T and waits for T to complete

Thread B (executes task T)
  -> needs lock M to call a synchronized method
  -> becomes BLOCKED because A holds M

A waits for B; B waits for A to release M => deadlock.
```

The following Java snippet is solely for analyzing the **anti-pattern**—never run it as an automated test without a timeout:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ExecutionException;

final class DeadlockIllustration {
    private int value;

    synchronized int readValue() {
        return value;
    }

    synchronized void wrongWait(ExecutorService pool)
            throws InterruptedException, ExecutionException {
        // Caller holds the `this` monitor.
        pool.submit(this::readValue).get();
        // Worker needs that same monitor before the Future can complete.
    }
}
```

If the executor runs the task on **another thread**, and that task tries to acquire the monitor before completing, the thread calling `wrongWait` holds the monitor while waiting on the future: an unresolvable dependency cycle. If the executor has a policy of running tasks inline on the caller thread, the behavior may differ. The takeaway is **do not wait on work that might need a lock you are currently holding**.

### Wait—Intrinsic Locks Are Reentrant; Does a Callback Calling Back Always Deadlock?

**No.** Java intrinsic monitors are **reentrant**: the same thread already holding a monitor can re-enter a `synchronized` method on **that same monitor**. For example, a listener running directly on thread A and calling `notifier.addListener(...)` can reacquire the `notifier` monitor without deadlocking on that monitor.

However, reentrancy still causes problems:

- The callback can mutate state in the middle of an operation that appeared atomic to the calling layer.
- The listener can add/remove elements while iterating an `ArrayList` with an iterator, causing `ConcurrentModificationException` or breaking iteration assumptions.
- The callback can recursively call `publish` again, leading to nested dispatches, confusing event ordering, or `StackOverflowError`.
- The callback can acquire **another lock** and create a wait cycle with another thread, even though the initial monitor is reentrant.

Distinguish precisely: **re-entering the same monitor from the same thread does not deadlock by itself**; **waiting on another thread or inverting the order of multiple locks** can deadlock.

## 5. Risk 3: Lock-Order Inversion Between Two Components

A common deadlock that does not require `Future.get()`:

```text
Thread A: lock ServiceA -> callback calls ServiceB -> waits for ServiceB lock
Thread B: lock ServiceB -> callback calls ServiceA -> waits for ServiceA lock
```

At this point:

- A holds ServiceA's lock and waits for ServiceB's lock.
- B holds ServiceB's lock and waits for ServiceA's lock.

Neither thread can make progress, even if the callback was originally meant only to "notify of a change." When each class manages its own locks, the risk is even harder to spot: no single class can see the full **lock order** across other components.

The foundational solution is **do not call external callbacks while holding internal locks**. In places where multiple locks genuinely must be acquired, define a **consistent lock order** and avoid running uncontrolled code while holding them.

With `ReentrantLock`, `tryLock(timeout, unit)` can help some designs avoid indefinite waiting; it **does not eliminate deadlock by itself** if the lock-acquisition logic and cross-resource dependencies remain flawed.

## 6. Risk 4: Exceptions, Partial Work, and Invariants

When a callback throws an exception, the intrinsic monitor is released by the JVM as the method exits abnormally. However, **releasing the lock does not roll back any state changes**:

```java
synchronized (lock) {
    status = Status.UPDATING;
    listener.onUpdate(); // Throws RuntimeException.
    status = Status.READY; // Skipped.
}
```

This is an illustrative snippet with hypothetical `lock`, `status`, `Status`, and `listener`. If the callback throws an unchecked exception, the state may remain stuck in `UPDATING`. Subsequent callers can acquire the monitor yet encounter an invariant or lifecycle state not intended by the design.

You must decide the **order of state updates and callback invocation**:

1. Update valid state under the lock.
2. Create event data or an immutable snapshot.
3. Release the lock.
4. Invoke callbacks outside the lock.
5. Handle callback exceptions according to policy: propagate, log and continue, retry, or report per-listener results.

There is no single policy right for every API. However, for a public API, **callback exception behavior** must be documented: if listener A throws an error, is listener B still called? Does the state change before the callback remain intact? Is the event redelivered?

### State Atomicity Is Different from "All-or-Nothing Delivery"

Updating a list under a lock can be an atomic change to internal state. However, if an event is delivered to A, and then B throws an exception before C receives the event, delivery has **partially succeeded**. Do not promise "exactly once to all listeners" without an appropriate delivery and error-handling protocol.

If a transaction spanning external systems is needed, in-memory JVM locks also **do not create a transaction** encompassing HTTP requests or database writes.

## 7. Risk 5: Callbacks Can Corrupt Iterators

Example:

```java
synchronized (this) {
    for (var listener : listeners) {
        listener.onEvent(event);
    }
}
```

If a listener is called on the same thread and registers a new listener through a `synchronized` method on the same notifier, the reentrant monitor does not block the callback. While the `ArrayList` iterator is active, structurally modifying the list via `add` can result in `ConcurrentModificationException` when the iterator checks again.

**Lock reentrancy does not make an `ArrayList` iterator resilient to structural modification.** A common solution is to **snapshot the listener list under the lock** and iterate the snapshot outside the lock.

Snapshot semantics must be defined:

- A listener registered **after the snapshot is taken** will not be included in the current dispatch pass.
- A listener removed **after the snapshot is taken** may still receive the event in the ongoing dispatch pass.
- Two `publish` calls may execute concurrently, causing two callbacks on the **same listener object** to run simultaneously unless another serialization mechanism exists.
- Callback order within a pass can match the snapshot order; no global ordering across concurrent publish calls is promised.

## 8. Safe Pattern: Snapshot Under Lock, Callback Outside Lock

Save as `CallbackOutsideLockDemo.java`, run with JDK 17+:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Consumer;

public class CallbackOutsideLockDemo {
    static final class Notifier {
        private final List<Consumer<String>> listeners =
                new ArrayList<>();

        public synchronized void subscribe(Consumer<String> listener) {
            listeners.add(Objects.requireNonNull(listener));
        }

        public synchronized int listenerCount() {
            return listeners.size();
        }

        public void publish(String event) {
            List<Consumer<String>> snapshot;
            synchronized (this) {
                snapshot = List.copyOf(listeners);
            }

            // Notifier monitor is not held here.
            for (Consumer<String> listener : snapshot) {
                listener.accept(event);
            }
        }
    }

    public static void main(String[] args) {
        Notifier notifier = new Notifier();

        notifier.subscribe(event -> {
            System.out.println("Under notifier lock: "
                    + Thread.holdsLock(notifier));
            System.out.println("Listener count: "
                    + notifier.listenerCount());
        });

        notifier.subscribe(event ->
                System.out.println("Second listener: " + event));

        notifier.publish("READY");
    }
}
```

Compile and run:

```bash
javac CallbackOutsideLockDemo.java
java CallbackOutsideLockDemo
```

Exact stdout:

```text
Under notifier lock: false
Listener count: 2
Second listener: READY
```

**Detailed explanation:**

- `subscribe` and `listenerCount` share `Notifier`'s monitor, so list access is protected.
- `publish` holds the monitor only while `List.copyOf(listeners)` creates a snapshot. After that block, callbacks run **without holding the notifier's monitor**.
- `Thread.holdsLock(notifier)` reports whether the **current thread** owns that object's monitor at the time of the check. The `false` line demonstrates the design accurately, though it does not measure other locks the callback might acquire on its own.
- Callbacks are invoked directly on the **caller thread** of `publish`. This code does not offload callbacks to the background or serialize them across two concurrent publish passes.
- `List.copyOf` snapshots the list of listener references; it does not make a mutable listener object thread-safe. If the same listener is invoked concurrently by two callers, the listener's own logic must ensure thread safety.

Here the callback receives an immutable `String`. If the event is a mutable object, you must also design **ownership/safe publication** so listeners do not read an object being modified by another thread.

### Alternative: `CopyOnWriteArrayList`

For a small listener set where **reads and event dispatches are very frequent while registrations/unregistrations are rare**, `CopyOnWriteArrayList<Listener>` can be appropriate:

- List write operations are internally synchronized by the structure.
- Iterators have snapshot semantics; you can iterate without holding a registry monitor.
- List modification cost is typically higher because the underlying array must be copied; it does not suit every workload.
- Callbacks can still be slow, throw exceptions, or run concurrently on the same listener, so it is not a "shield" for callback logic.

Switching from a locked `ArrayList` to `CopyOnWriteArrayList` solves only **list storage**, not the entire callback protocol.

## 9. Callbacks Outside the Lock Still Need a Defined Commit Point

Because callbacks run after releasing the lock, state may continue to be updated before or while the listener processes the event.

Example:

```text
Thread A                             Thread B
--------                             --------
lock
  state = VERSION_1
  snapshot event VERSION_1
unlock
                                     lock
                                       state = VERSION_2
                                     unlock
call listener with VERSION_1
```

When the callback receives event `VERSION_1`, the service's current state may already be `VERSION_2`. This is **not a bug** if the API defines an event as an immutable snapshot of an update that occurred, rather than a promise that the callback always sees the latest state.

If a callback **reads live state again**, it may observe a newer version than the event. Documentation should specify:

- Which snapshot, version, or ID data does the event carry?
- Can the callback query the latest state via another call, and must the two values match?
- Is **callback order** guaranteed to match the global commit order?
- Can two callers updating state concurrently dispatch callbacks in parallel?
- Which listeners can appear or be removed while a dispatch is in progress?

**Snapshotting outside the lock does not replace an ordering policy.** If sequential dispatch strictly matching commit order is required, use a queue managed under the same protection protocol on enqueue, with a worker consuming events in deterministic order. You must also account for backlog, full queues, worker death, and shutdown—not just locking.

## 10. Why Is Blocking I/O Inside `synchronized` Dangerous?

A **blocking I/O** operation can wait on data from a network, file, socket, pipe, stream, database driver, or other resource. Wait duration depends on factors external to the JVM and can be long or unbounded without proper timeouts/cancellation.

Anti-pattern example:

```java
synchronized (lock) {
    updateMetadata();
    outputStream.write(payload);
    outputStream.flush();
}
```

This is an illustrative snippet with hypothetical variables/methods. `write` or `flush` may wait on the receiver, buffers, or devices; meanwhile **the `lock` monitor remains held**. Threads wanting to access metadata via the same monitor must wait, even though reading metadata has nothing to do with the network.

Common harms:

1. **Unpredictable lock hold time** because it depends on I/O latency.
2. **Reduced throughput** as calls needing the same monitor queue behind I/O.
3. **Tail latency spikes** when a single I/O call is unusually slow.
4. **Lock inversion** if I/O indirectly triggers callbacks or another thread needs the original monitor.
5. **Hard shutdown/cancellation** when a lock-holding thread gets stuck in a call that does not respond to interruption.
6. **Inconsistent business state** if state is updated before I/O and I/O fails, while callers assume the two committed together.

Note: **not every I/O call blocks on every invocation**. The problem is that the API **can block** and the wait time is not bounded by the critical section. A quick benchmark does not prove safety under all loads.

## 11. Which Waiting Calls Release Locks and Which Do Not?

It is easy to confuse the English word "waiting" with "the JVM automatically releases the monitor."

| Call made while holding monitor `M` | Automatically releases monitor `M` while waiting? | Notes |
| --- | --- | --- |
| `Thread.sleep(...)` | **No** | Thread sleeps while still holding all owned monitors |
| `Thread.join()` | **Does not release monitor M** | May wait on target thread; if target needs M there is a deadlock risk |
| `Future.get()` | **No** | May wait on another task that needs the same monitor |
| `CountDownLatch.await()` | **No** | Waits on latch; latch `countDown` may depend on a thread needing M |
| `BlockingQueue.take()/put()` | **No** | Queue manages its own synchronization but does not release monitor M held by caller |
| Blocking socket/file I/O | **No** | I/O does not unlock monitors held by caller |
| `Object.wait()` called on **M** while holding monitor M | **Yes: releases monitor M while waiting** | Reacquires monitor M before `wait()` returns; use a `while` loop to check condition |
| `Condition.await()` under `ReentrantLock L` | Releases and reacquires **lock L** per Condition contract | Does not release **other** held monitors/locks |

An important nuance: if you call `otherObject.wait()`, the thread must own **otherObject**'s monitor; that call releases `otherObject`'s monitor, **which does not mean** it releases every held monitor, including the service's monitor M. Therefore, "using `wait` inside `synchronized` is fine" is only true when waiting on **the right monitor and the right predicate**, without holding other secondary locks that cause wait cycles.

Similarly, `Condition.await()` atomically releases and reacquires **the lock bound to that Condition**, not every lock on the call stack.

## 12. Races Between External I/O and State Updates After Unlocking

"Just move the network call outside the lock" is a starting point, but **not enough** when I/O reads from state and the I/O result determines the next update step.

Three-phase pattern:

```text
Phase 1 — under lock:
  read state and create immutable snapshot / operation ID / version
  or set an "in-progress" state per invariant

Phase 2 — outside lock:
  perform potentially slow I/O or callback
  check timeout, cancellation, errors

Phase 3 — under lock:
  verify version/ownership/invariant
  commit result if still valid
  if stale: reject, bounded retry, or resolve conflict
```

Two common design patterns:

- **Snapshot + validate:** if state can change while I/O is in flight, record a version/token and commit only if the version still matches.
- **Reservation/state machine:** if business logic must reserve usage rights during I/O, create a reservation or transitional state under the lock first, release the lock for I/O, then commit/abort via a synchronized operation. Ensure timeouts and rollback/resolution when I/O fails.

Do not hold a monitor just because "I want I/O and the state update to be one atomic operation." A JVM monitor lock **does not turn out-of-process I/O into a transaction**, and holding the lock longer only amplifies contention. If an external side effect has already occurred and the internal commit fails, you need idempotency/compensation or an appropriate transaction protocol; `synchronized` alone cannot provide this.

## 13. Java 17+ Example: Queue `put` Can Block Without Holding the State Monitor

`BlockingQueue.put` is an easily verifiable **blocking coordination** operation illustrating the same principle as blocking I/O: the producer waits until the queue has space. It is not socket I/O, but it demonstrates the exact same design flaw if code holds a monitor while waiting.

Save as `QueueOutsideLockDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public class QueueOutsideLockDemo {
    static final class State {
        private int value = 10;

        public synchronized void increment() {
            value++;
        }

        public synchronized int get() {
            return value;
        }

        public void send(
                BlockingQueue<Integer> queue,
                CountDownLatch snapshotTaken)
                throws InterruptedException {
            int snapshot;
            synchronized (this) {
                snapshot = value;
            }

            // Monitor released before queue.put, which may block.
            snapshotTaken.countDown();
            queue.put(snapshot);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        State state = new State();
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(1);
        CountDownLatch snapshotTaken = new CountDownLatch(1);

        queue.put(-1); // Fill queue before the worker sends.

        Thread sender = new Thread(() -> {
            try {
                state.send(queue, snapshotTaken);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        sender.start();
        snapshotTaken.await();

        // State remains accessible even though sender may be waiting on the queue.
        state.increment();
        System.out.println("State now: " + state.get());

        System.out.println("Removed: " + queue.take());
        sender.join();
        System.out.println("Sent: " + queue.take());
    }
}
```

Compile/run:

```bash
javac QueueOutsideLockDemo.java
java QueueOutsideLockDemo
```

Exact stdout on a normal run:

```text
State now: 11
Removed: -1
Sent: 10
```

**Observations:**

- The worker snapshots `value == 10` under the monitor and releases the monitor before `snapshotTaken.countDown()`.
- `main` updates only after receiving the signal that the snapshot was taken; thus the new state value is 11, while the sent message remains the snapshot 10.
- The queue is initially full. `queue.put(snapshot)` **may have to wait** until `main` removes `-1`. There is no requirement that the worker has already called `put` by the time `main` prints the first line; the output remains deterministic thanks to the latch and snapshot.
- If `send` held the monitor throughout `queue.put`, `main` could block in `increment()` while `main` itself is the only thread that will later take an item from the queue: a progress-blocking wait cycle would emerge.
- `CountDownLatch.await` in `main` is proper coordination; the worker releases the monitor before signaling. `Thread.sleep` cannot substitute for proving the snapshot was created.

The same principle applies when sending data over a socket or writing to a file: **snapshot a valid payload under the lock, send outside the lock**, then handle the result in a separate commit phase if business logic requires it.

## 14. Snapshots Can Go Stale: Check Version Before Committing

An external response may return after another thread has already modified state. Writing the response blindly into state without checking can overwrite newer data with stale information.

The following Java 17+ example focuses on **validate/commit logic** without making network calls. External processing is simulated with a fixed value so stdout does not depend on the network.

Save as `VersionedCommitDemo.java`:

```java
public class VersionedCommitDemo {
    private record Snapshot(long value, long version) {}

    private static final class State {
        private long value = 10;
        private long version;

        synchronized Snapshot snapshot() {
            return new Snapshot(value, version);
        }

        synchronized void incrementLocally() {
            value++;
            version++;
        }

        synchronized boolean commitIfUnchanged(
                Snapshot expected, long externalResult) {
            if (version != expected.version()) {
                return false;
            }
            value = externalResult;
            version++;
            return true;
        }

        synchronized long get() {
            return value;
        }
    }

    public static void main(String[] args) {
        State state = new State();

        Snapshot beforeExternalWork = state.snapshot();

        // Another update occurs while the out-of-lock processing phase runs.
        state.incrementLocally();

        // Attempt to commit a result computed from the stale snapshot.
        boolean accepted = state.commitIfUnchanged(
                beforeExternalWork, 99);

        System.out.println("Accepted stale result: " + accepted);
        System.out.println("Current value: " + state.get());
    }
}
```

```bash
javac VersionedCommitDemo.java
java VersionedCommitDemo
```

Exact stdout:

```text
Accepted stale result: false
Current value: 11
```

This is **optimistic concurrency control** at the in-process state level: commit only if the version has not changed. The `commitIfUnchanged` method holds the monitor across both the check and update steps so there is no gap between them.

Limitations:

- The version must increment on **every change related to the invariant**; if a mutation is missed, the version check can be wrong.
- In a long-running system, consider version overflow and identity/generation management; do not use a small, easily reused version if that creates an ABA problem.
- If the external request already produced an irreversible side effect, skipping the internal commit does not roll back the external side effect outside the JVM.
- If retries are needed, define timeouts, cancellation, retry limits, idempotency, and event ordering.
- The demo runs sequentially to explain semantics; in real applications, the phases between snapshot and commit may run on different threads. Invariants remain protected as long as every mutation goes through the proper monitor.

## 15. A Callback Waits, Yet the Registry Still Handles Other Requests

Snapshotting and invoking callbacks outside the lock is beneficial even when a callback does not perform I/O but waits on a signal.

Java 17+ example where a callback intentionally waits on a latch while the main thread can still read the registry:

Save as `CallbackProgressDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class CallbackProgressDemo {
    static final class Hub {
        private final List<Runnable> callbacks = new ArrayList<>();

        synchronized void register(Runnable callback) {
            callbacks.add(callback);
        }

        synchronized int count() {
            return callbacks.size();
        }

        void fire() {
            List<Runnable> snapshot;
            synchronized (this) {
                snapshot = List.copyOf(callbacks);
            }
            for (Runnable callback : snapshot) {
                callback.run(); // Does not hold Hub's monitor.
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Hub hub = new Hub();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        hub.register(() -> {
            System.out.println("Callback entered");
            entered.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            System.out.println("Callback released");
        });

        Thread caller = new Thread(hub::fire);
        caller.start();
        entered.await();

        try {
            System.out.println(
                    "Registry size while callback waits: " + hub.count());
        } finally {
            release.countDown();
            caller.join();
        }
    }
}
```

```bash
javac CallbackProgressDemo.java
java CallbackProgressDemo
```

Exact stdout on a normal run:

```text
Callback entered
Registry size while callback waits: 1
Callback released
```

**Why does the example not get stuck?**

- `fire` holds `Hub`'s monitor **only to copy the callback list**.
- The callback can wait on `release` without holding `Hub`'s monitor. `main` can still call `hub.count()` and then open the latch.
- If `fire` were written as `synchronized void fire()` calling callbacks directly inside the method, `main` would wait for the lock in `count()`, while the callback waited for `main` to call `release.countDown()`: the program would risk getting stuck.
- `Thread.join()` is called after `release.countDown()` to wait for the callback thread to finish, rather than polling `Thread.getState()`.

In production, avoid unbounded waits when dealing with untrusted data or callbacks: add timeouts, cancellation policies, and error monitoring. Here the latch is used to deterministically simulate a waiting callback.

## 16. When Offloading Callbacks Asynchronously, Is Using an Executor Enough?

Not quite. A common architecture looks like:

```text
State-writing thread
   |
   v
[lock, update state, create immutable event, unlock]
   |
   v
[executor/queue]
   |
   v
[callback on another worker]
```

The idea of not forcing the state-mutating thread to run heavy callbacks is good. However, you must understand:

1. **Submission can be rejected** if the executor is shut down or the queue is full; `RejectedExecutionException` or the rejection policy must be handled.
2. Some policies such as **CallerRunsPolicy** can run the task directly on the calling thread; some executors execute directly on the caller. Therefore, **do not call `executor.execute(callback)` inside a lock and assume the callback will always run outside the lock**. Release the lock **before submitting**.
3. An executor may use multiple workers, so callbacks for the same listener **can run concurrently** or events can complete out of order.
4. Futures and exceptions must be collected/routed. If a callback throws an error on a worker, the publisher may not receive the error directly as with a synchronous callback.
5. Unbounded queues can accumulate backlog; bounded queues require backpressure or controlled drop/retry policies.
6. On shutdown, you must decide whether already-accepted events are drained, drain timeouts, cancellation behavior, and resource cleanup.

If the API promises **event ordering by commit**, you must define how enqueuing corresponds to commit order and worker dispatch. Two threads can commit sequentially under a lock and then submit outside the lock in reversed order; a FIFO queue will still dispatch in enqueue order, not necessarily commit order. You can use sequence numbers and an appropriate dispatcher or a clearly designed reservation/queue protocol.

**Async callbacks do not remove the thread-safety requirements of the listener.** They only shift the execution boundary. A listener can still share mutable state or call back into the API being used.

## 17. Must You Hold the Lock Across I/O to Guarantee Write Ordering?

Sometimes the goal of the code is "do not send message B before message A." Holding a monitor across the entire network send may **incidentally** force serialization, at the cost of making every caller wait on the network. Separate the two concerns:

- **Protect state and assign order:** a short critical section to generate a sequence number, take a snapshot, or enqueue an event in order.
- **Perform I/O:** a single worker owning the output channel or a queue with defined ordering; the worker processes outside the state monitor.

For sockets or streams written by multiple threads, understand **message framing atomicity**. A single `OutputStream.write(byte[])` does not create a multi-message transaction contract for an arbitrary protocol; data may need to be framed and sent by a single owner or a dedicated writer lock.

A separate **writer** lock may also be necessary if the output protocol requires serialization. However, **do not use the same monitor managing all state** across a long network call unless the tradeoff is proven necessary and has explicit timeouts.

**There is no guarantee that a file write or socket write can be canceled immediately via `Thread.interrupt()`.** Interruptibility depends on the API, channel type, and operating system. For blocking network I/O, set timeouts, design close/cancel per the API, and handle partial writes/retries according to the protocol.

## 18. Keeping Data Consistent While Invoking Callbacks Outside the Lock

When snapshotting state for callbacks, prefer **immutable events**:

```java
record AccountEvent(long accountId, long version, long balance) {}
```

If a thread mutates state after the event is created, the callback still reads the captured payload. This record is immutable because it contains only primitive types. For a record containing a `List<Item>` where `Item` is mutable, you must copy the collection and handle mutable elements separately.

The "snapshot under lock" solution is only valid if the values being read are protected by **the same locking protocol**. If another writer can modify a field without holding this lock, the snapshot can still be inconsistent.

### One Event and Callback Can Run Concurrently With Another Event

Once the publisher releases the lock, another thread can commit a new change while the older event has not yet been dispatched. If listeners expect strict commit order, you must add an ordering policy. If only **at-least-once notification** or **eventual update** is needed, define duplicate/retry/out-of-order handling and idempotent solutions.

The public contract should answer:

- "At what point in time does the event capture its snapshot?"
- "Is the callback invoked synchronously or asynchronously, and on which thread?"
- "Can it be called repeatedly, concurrently, or out of order?"
- "Does `unsubscribe` prevent callbacks that were already snapshotted?"
- "What happens to queued-but-unsent events on close?"
- "If a callback fails, is the committed state rolled back?"

Do not simply write "listener is thread-safe" and ignore these points.

## 19. When Holding a Lock Across Slow Code Is Unavoidable

Some systems require strong serialization or involve legacy resources without an owner/queue design. When you cannot separate them immediately, make the tradeoffs explicit and mitigate risk:

1. Identify which monitor is held and who else needs it.
2. Set **timeouts** or deadlines on calls that support them. Never assume an I/O call always returns.
3. Do not call arbitrary client callbacks without a contract regarding non-blocking behavior, reentrancy, and locking order.
4. Avoid holding multiple locks simultaneously; if necessary, use a consistent lock acquisition order.
5. Place rollback, reset, or valid error-state transitions in `try/finally` when needed, keeping in mind that external side effects may not be rollbackable.
6. Monitor **lock contention**, wait times, queue depth, callback duration, deadlocks, and timeouts.
7. Evaluate migrating to snapshot + outside-lock, a state machine, producer–consumer, or an actor-like owner when feasible.

With `ReentrantLock`, the author must release via `unlock()` in `finally`; a `synchronized` block is automatically released by the JVM on exit. **Do not** confuse `finally` with the ability to cancel a blocking call: if a thread hangs indefinitely in an I/O call, control flow never reaches `finally`.

One property of `ReentrantLock.lockInterruptibly()` is that it waits **to acquire the lock** interruptibly; it does not automatically cancel network calls already in progress inside the critical section.

## 20. Is a Callback Under a Lock Ever Right?

Not every callback is strictly forbidden. Very short internal hooks controlled by the implementation itself—that do not block, do not re-enter, and do not acquire other locks—can be called inside a critical section when the contract is clear.

Examples:

- An internally controlled pure function that calls no arbitrary code, used to quickly compute a value from locked state.
- An invariant-updating operation on a helper object whose thread-safe protocol is well defined.
- An audited internal callback with no wait or reverse lock-acquisition paths.

However, for callbacks accepted through a **public API** such as `Consumer<T>` or `Runnable`, the implementation does not control behavior. A contract stating "this callback must be fast and non-blocking" can be a constraint, yet it is hard to ensure every caller obeys it. Designs that do not run callbacks under a monitor remain easier to maintain and more robust.

Furthermore, even a non-blocking pure callback can throw an unchecked exception. If the overall operation expects invariants to be in a transitional state, restore invariants before returning control externally.

## 21. Code Review Checklist: Are There Call-Outs While Holding a Monitor?

When reviewing a class that uses `synchronized`, look for the following calls:

| Signal in critical section | Questions to check |
| --- | --- |
| `listener.accept(...)`, `callback.run()` | Can the callback block, re-enter, throw errors, or acquire another lock? |
| `InputStream.read`, `OutputStream.write/flush` | Is there a timeout, is I/O cost bounded, and how is partial I/O handled? |
| `Future.get`, `join`, `await` | Could the awaited task need the same monitor to complete? |
| `BlockingQueue.put/take` | Could the queue be full/empty and require the monitor-holding thread to make progress? |
| `Thread.sleep` | Is a monitor accidentally held while sleeping? Sleep does not release locks |
| `executor.execute(...)` | Can the executor inline the task, reject it, or block in a custom implementation? |
| `log(...), serialize(...), toString()` | Are there user-defined callbacks/collaborators or hidden I/O? |
| `otherService.method(...)` | Are there locks on the other side, reverse callbacks, or lock-order inversion? |

**Indirect risks are also worth checking.** A method named `format` or `toString` may invoke a user-supplied formatter; a logger may have a slow appender; a serializer may have a custom adapter; a collection operation may use a caller-defined comparator. Do not look only for method names containing "I/O" or "callback."

### Detection Tools

- Thread dumps and `ThreadMXBean` can help inspect monitor owners, threads waiting on monitors, and some deadlock cases.
- Java Flight Recorder (JFR) or an appropriate profiler can measure monitor contention, blocking, and callback durations.
- Tests using `CountDownLatch` to deterministically orchestrate waiting help expose dependency cycles; do not rely solely on `Thread.sleep` and guess ordering.
- Stress tests are useful, but they do not replace analyzing ownership, lock ordering, and happens-before relationships.

A `Thread.State.BLOCKED` indicates a thread is waiting on an intrinsic monitor, **not proof of deadlock by itself**. You must analyze lock owners and dependency cycles or progress over time.

## 22. Common Misconceptions and Accurate Explanations

**"Synchronized makes callbacks automatically thread-safe."** No. It only serializes threads competing for the same monitor; callbacks can access other state or be invoked concurrently by other publishers.

**"A callback calling back into a synchronized method on the same object always deadlocks."** No. Intrinsic monitors are reentrant for the same thread. However, callbacks can cause recursion, iterator invalidation, or deadlock when waiting on another thread.

**"Moving `listener.accept` outside the lock preserves all semantics."** No. Snapshot and ordering semantics change; listeners can receive older events while newer state has already committed. Document this clearly.

**"`Thread.sleep` temporarily releases the lock."** False. Sleep does not release any held intrinsic monitors.

**"`Future.get` or `BlockingQueue.take` releases all locks while waiting."** False. They do not release external monitors held by the caller.

**"`Object.wait` releases all owned locks."** False. `wait` releases the monitor of **the object it is called on**, not arbitrarily all other monitors.

**"Releasing the lock before I/O means the operation is atomic."** False. State can change while I/O runs. If committing against a snapshot is required, check a version/reservation and handle stale results.

**"Using an executor means the callback definitely runs on another thread."** False. Direct executors and rejection policies can run tasks on the caller thread. Release the monitor even before submitting.

**"Having `finally` ensures the lock is released immediately when a thread blocks."** False. `finally` runs only when control exits `try`; an infinitely blocking call prevents code from reaching cleanup.

**"One monitor can protect an entire network transaction."** An intrinsic monitor cannot guarantee transactions outside the JVM. Use appropriate transaction/idempotency/compensation protocols.

**"No exception means no problem."** No. Contention and deadlocks can hang an application without throwing exceptions; slow callbacks can simply inflate tail latency.

## 23. Self-Check Questions

**Question 1:** A `synchronized void publish(...)` iterates over an `ArrayList` of listeners and invokes callbacks. A listener calls synchronized `addListener` on the same instance. What is true?

**Answer:** The monitor is reentrant, so the same-thread call does not deadlock on that lock. However, adding to the `ArrayList` while the iterator is traversing can break the iterator, and callbacks are still running under the monitor. Use a snapshot and out-of-lock callbacks or another protocol.

**Question 2:** Thread A holds a monitor when calling `Future.get()`. The future's task wants to call a synchronized method on the same object. What is the risk?

**Answer:** If the task runs on another thread, A waits for the task; the task waits for A to release the monitor: **deadlock**. Move waiting on the future outside the critical section.

**Question 3:** Is `Object.wait()` equivalent to `Thread.sleep()` with respect to monitors?

**Answer:** No. `wait` called properly on a held monitor temporarily releases that monitor and reacquires it before returning; `sleep` does not release any monitor.

**Question 4:** Does snapshotting listeners and invoking callbacks outside the lock guarantee the callback always sees the latest current state?

**Answer:** No. The callback receives a snapshot from a point in time, while another thread may update state afterward. If ordering is required, add a dispatch/version protocol.

**Question 5:** Why is queue `put` in the example safer when not holding the state monitor?

**Answer:** The queue may be full, causing `put` to wait; releasing the monitor before `put` allows other threads to update state or consume from the queue so the system can make progress.

**Question 6:** If I/O sends successfully but `commitIfUnchanged` returns `false`, does the intrinsic monitor roll back the external side effect?

**Answer:** No. You must design idempotency, compensation, or a synchronization protocol with the external resource.

**Question 7:** Is invoking callbacks via `executor.execute` while `synchronized` guaranteed to be safe?

**Answer:** Not yet. An executor or rejection handler can run the task inline on the caller. Also, tasks can be rejected. Release the monitor before submitting and define error, backlog, and ordering policies.

**Question 8:** When can calling a callback under a lock be acceptable?

**Answer:** When the callback code is controlled, very short, non-blocking, non-reentrant, acquires no reverse locks, and invariants and exceptions are proven safe. For uncontrolled callbacks from a public API, avoid it.

## 24. Implementation Checklist

1. **Identify invariants** that need synchronization: which fields must be read/written as a unit, and which monitor protects them?
2. **Map call-out boundaries:** all callbacks, I/O, queue/future/await calls, and logging/serialization that could block or invoke uncontrolled code.
3. **Shorten critical sections:** copy immutable events/snapshots or make valid state transitions, then release the monitor.
4. **Run slow work outside monitors:** callbacks, I/O, future waits, task submission; design timeouts/cancellation where APIs support them.
5. **Re-validate state if needed:** version, token, reservation, or state machine when committing results after an out-of-lock phase.
6. **Preserve ordering if contracted:** a queue/dispatcher with a provably correct commit–enqueue protocol.
7. **Handle exceptions explicitly:** callback failures, I/O failures, partial side effects, rejected tasks, shutdown errors, and permit/lock releases.
8. **Publish the concurrency contract:** callback thread model, concurrent delivery, removal semantics, snapshot visibility, failure policy, blocking, reentrancy, and ordering.
9. **Test adverse cases:** waiting callbacks, reentrant callbacks, two monitors in opposite order, full queues, timeouts, I/O errors, and closing with pending tasks.
10. **Measure contention and progress:** monitor wait time, callback duration, queue depth, tail latency; do not trade correctness just to reduce measured numbers.

In Java concurrency, the key question is not merely **"is it synchronized?"** but **"who am I handing execution control to while holding this monitor, what am I waiting on, and how can state change before I resume?"** Protecting state with short critical sections, handling callbacks/I/O outside, and re-validating invariants on commit significantly reduces deadlocks, bottlenecks, and hard-to-reproduce bugs.
