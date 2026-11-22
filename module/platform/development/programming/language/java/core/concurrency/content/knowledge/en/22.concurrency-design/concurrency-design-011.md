# Avoiding Holding Locks Across Uncontrolled Calls in Java

## 1. The Problem and the Principle

When multiple threads access mutable shared state, locks help protect **invariants**: for example, a list must be updated consistently, or an order can only transition between states according to allowed rules. However, **holding a lock while calling a function whose execution time, blocking behavior, or lock acquisition you do not control** can turn a very short state-protection section into a bottleneck or a deadlock.

**Principle:** A critical section should only perform short, predictable-duration operations necessary to read or update shared state. Take a snapshot or reserve a valid state under the lock, **release the lock**, and only then execute callbacks, I/O, or uncontrolled work. If you need to update the result, re-acquire the lock and verify that the preconditions still hold.

An "uncontrolled call" does not necessarily mean third-party code. A call to an overridable method, a user-registered listener, an executor, a logger, or an internal function that later adds I/O can all change behavior without the lock holder knowing.

## 2. Why Is Holding a Lock Across a Call Dangerous?

Suppose thread T1 holds lock L, then calls a service or callback. Meanwhile, thread T2 wants to acquire L to complete the work that T1's call is waiting for:

```text
T1: lock(L) → calls callback / waits for T2's result ──┐
                                                       │ waits for T2
T2: needs lock(L) to complete its work <───────────────┘
```

T1 does not release L because it is still waiting for the call; T2 cannot make progress because L is held: a wait cycle causing a **deadlock**. Even without a cycle, a slow call forces every other thread that needs L to queue up, increasing latency and reducing throughput.

| Situation inside a lock | Main risk |
| --- | --- |
| Calling a network API, querying a database, reading/writing a file | Practically unbounded duration; network timeouts/slowness; blocking other threads |
| Calling a plugin, listener, callback, or overridable method | Arbitrary code may acquire another lock, call back into the component, wait for a task, or throw an exception |
| `Future.get()`, `CompletableFuture.join()`, `Thread.join()`, waiting on a task | The awaited task may need the very lock currently held |
| `Executor.execute()`, `CompletableFuture.thenApply(...)` | Never assume a callback runs on another thread: a direct executor or an already-completed stage can run synchronously |
| Logging or calling a library with unknown implementation | May acquire another lock, flush/block on I/O, or trigger callbacks |
| `Thread.sleep(...)` or very long CPU processing | Still holds the lock; increases wait time even without I/O |

In Java, `synchronized` releases the monitor when exiting the block, even on an exception; `ReentrantLock` must be `unlock()`ed in `finally`. **Neither automatically releases the lock just because a method inside the block is blocking.** Specifically, `Object.wait()` releases the corresponding monitor while waiting, and `Condition.await()` releases the lock associated with the condition while waiting and re-acquires it before returning; these are intentional coordination mechanisms, not a way to make arbitrary calls safe. Nor do they release any other locks the thread is holding.

## 3. Anti-Pattern: Invoking Listeners Inside the Locked Region

The following snippet illustrates a common design flaw in a registry. Because the listener is externally provided, you cannot know whether it runs fast, calls back into the registry, acquires another lock, or waits for another thread.

```java
// Illustrative snippet: NOT a standalone Java program.
private final Object lock = new Object();
private final List<Consumer<String>> listeners = new ArrayList<>();

void publishBad(String message) {
    synchronized (lock) {
        for (Consumer<String> listener : listeners) {
            listener.accept(message); // Runs external code while holding the lock.
        }
    }
}
```

Specific problems:

- A slow callback forces `subscribe()` and other operations sharing the same lock to wait, even though the registry only needs to protect the listener list.
- A callback may call back into `subscribe()`. Java monitors are **reentrant**, so the same thread re-acquiring the same monitor will not necessarily deadlock; however, the callback can observe or mutate state at an unexpected moment. Modifying the list while iterating over it can throw `ConcurrentModificationException`.
- A callback may acquire lock B; another thread holding B and needing the registry lock creates an **A → B → A** cycle.
- An exception from one callback can prevent subsequent callbacks from being invoked; even though the monitor is released on block exit, event-delivery behavior must still be clearly defined.

Never assume a `private` method or "code we wrote ourselves" is always safe: a call that only computes today may add I/O or invoke a hook tomorrow.

## 4. Correct Pattern: Snapshot Under the Lock, Call Outside the Lock

The following standalone example runs on **Java 17+**. The registry maintains a mutable list of listeners; when publishing a message, it creates an immutable snapshot inside the locked region and invokes the listeners after releasing the lock.

**File: `ListenerRegistryDemo.java`**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Consumer;

public final class ListenerRegistryDemo {
    private final Object lock = new Object();
    private final List<Consumer<String>> listeners = new ArrayList<>();

    public void subscribe(Consumer<String> listener) {
        Objects.requireNonNull(listener, "listener");
        synchronized (lock) {
            listeners.add(listener);
        }
    }

    public void publish(String message) {
        final List<Consumer<String>> snapshot;
        synchronized (lock) {
            snapshot = List.copyOf(listeners);
        }

        // Do not hold the lock when executing externally provided callbacks.
        for (Consumer<String> listener : snapshot) {
            listener.accept(message);
        }
    }

    public int subscriberCount() {
        synchronized (lock) {
            return listeners.size();
        }
    }

    public static void main(String[] args) {
        ListenerRegistryDemo registry = new ListenerRegistryDemo();
        registry.subscribe(msg -> System.out.println("listener: " + msg));
        registry.publish("hello");
        System.out.println("subscribers: " + registry.subscriberCount());
    }
}
```

Compile and run in the directory containing the file:

```bash
javac ListenerRegistryDemo.java
java ListenerRegistryDemo
```

Deterministic stdout of the program:

```text
listener: hello
subscribers: 1
```

**Correctness explanation:**

1. Every update to `listeners` goes through the same monitor; `List.copyOf` is created while the monitor protects the list, so iteration never traverses a list being modified by another thread.
2. The snapshot is an independent list that cannot be modified through its own list API. `listener.accept` executes after exiting `synchronized`; even if a callback is slow, other threads can still acquire the registry's monitor.
3. Releasing and acquiring the monitor establishes a *happens-before* relationship between properly synchronized operations. The example does not need `volatile` just to protect this list.
4. A listener registered **after the snapshot is taken** will not receive the current publish. If an unsubscribe operation exists, a listener unsubscribed after the snapshot may still receive this delivery. This is the *snapshot semantics* contract, not a synchronization bug.
5. The example intentionally lets a listener's exception propagate out, so subsequent listeners might not be called. Real-world applications must choose an explicit policy: stop, catch errors per listener, retry, or record failures. Never silently swallow errors.

A snapshot only copies the **list of references**; it does not make each listener thread-safe and does not guarantee listeners always run fast. It only narrows the scope of the registry's lock.

## 5. When Side Effects Must Precede State Updates: Multi-Phase Protocol

Simply moving the call outside the lock is not enough if the state can change during the call. For example, checking that an order is `NEW`, releasing the lock, calling a payment gateway, and then setting `PAID` can cause **two threads to pay simultaneously** because both read `NEW`.

Design a protocol with an **intermediate/claim state** instead of holding the lock across the payment gateway:

```text
Phase 1, under the lock:
    check state is NEW
    transition NEW → PROCESSING; attach a unique operationId
    release the lock

Phase 2, outside the lock:
    call the payment gateway with operationId as the idempotency key

Phase 3, under the lock:
    verify operationId and state PROCESSING still match
    write PAID or a failed/unknown-outcome state
    release the lock
```

This is an **algorithmic sketch**, not standalone Java code. Essential points when implementing:

- The `NEW → PROCESSING` transition must be atomic under the same synchronization mechanism followed by other processing flows. Only the thread that successfully claims the order may issue the payment request.
- After I/O, re-check `operationId`, version, or current state before committing; never use a stale read to overwrite a newer valid change.
- A timeout from an external system **does not prove the side effect failed**: the request may have succeeded while the response was lost. You need an externally supported idempotency key, status lookup, reconciliation, and a safe retry policy.
- If the process stops between phases, you need a way to detect and recover stuck `PROCESSING` records (a lease, controlled timeout, or appropriate recovery workflow); never blindly retry a non-idempotent side effect.
- If strict ordering is required, use a queue/actor/serial executor or an explicit ordering and state protocol. **Releasing the lock changes when operations can interleave**, so define the ordering contract explicitly instead of implicitly relying on lock hold duration.

Depending on system scope, you can use snapshot + version, optimistic validation, a state machine, or offload work to a dedicated worker. The goal is to keep invariant protection **short and clear**, while keeping slow work outside the lock.

## 6. Cases That Look Safe at First Glance

### Hidden callbacks inside libraries

An API that looks like "registration" or "computation" can still invoke the caller's code immediately. For instance, `CompletableFuture.thenApply` can run the action on the registering thread if the future is already completed; and `Executor.execute` can run the `Runnable` directly on the caller thread with a direct executor or a rejection policy like `CallerRunsPolicy`. Therefore, calling them under a lock still requires considering the synchronous execution path.

Prepare data under the lock, release the lock, and then register/execute the action. If the action requires ordering or consistent data, design state/queues to guarantee it rather than expecting callbacks to always be asynchronous.

### `tryLock`, timeouts, and interrupts

`ReentrantLock.tryLock(timeout, unit)` bounds **the time spent waiting to acquire the lock**, not how long the thread holds the lock after acquiring it. A network call timeout can limit blocking time, but it does not eliminate lock dependency cycles or every slow path. Likewise, `interrupt()` does not force arbitrary external code to stop and does not automatically release locks; cancellability depends on the API and handler logic.

The proper pattern for releasing `ReentrantLock` still requires `finally`:

```java
// Illustrative snippet, assuming lock is a ReentrantLock.
lock.lock();
try {
    // Only short, bounded reads/updates of shared state.
} finally {
    lock.unlock();
}

// Perform I/O or callbacks here, outside the locked region.
```

Never replace this with an early `unlock()` mid-method and then continue relying on old invariant assumptions without re-checking them.

### Nested locks and reentrancy

Holding lock A while calling a method that may acquire lock B creates a lock-ordering edge **A → B**. If other code acquires B then A, a deadlock can occur even when each lock works properly on its own. With `synchronized` and `ReentrantLock`, re-entering the same lock on the same thread is supported; however, reentrancy can let a callback observe incomplete state or modify a collection currently being iterated. Thus, "reentrant lock" does not mean "safe to invoke callbacks under the lock".

### A lock only protects local state, not the entire external action

If you need a guaranteed snapshot, use an immutable copy or a DTO containing the needed values. If multiple fields must be consistent together, capture them within the same critical section. If you want to commit after a call, use a version/claim and re-verify. A single `volatile` does not replace a transaction/lock for multi-field invariants; `AtomicInteger` also does not automatically make multi-object updates atomic.

### Computation functions on concurrent collections

APIs such as `ConcurrentHashMap.computeIfAbsent` or `compute` execute update logic atomically according to the collection's contract. The mapping/remapping function should not perform long I/O, wait on futures, recursively update the same map, or call uncontrolled code; using a concurrent collection does not eliminate contention or blocking risks inside the update computation.

## 7. Inspection and Diagnostics in Real Systems

When reviewing concurrency code, start from every `synchronized` block, `Lock.lock()`/`unlock()`, read/write lock, and callback running inside an atomic update. For each call inside, ask:

1. Can the call block on I/O, waiting for a future, waiting for a thread, sleeping, a full queue, or a resource outside the JVM?
2. Can the call run unknown code (listener, override, plugin, executor, callback, logger) or acquire a second lock?
3. Can the called code call back in and mutate the state currently being iterated or updated?
4. Can we snapshot/claim under the lock and move the call outside? If moved outside, how are invariants, ordering, and stale results handled?
5. Is there an explicit policy for exceptions, timeouts, retries, and side effects with uncertain outcomes?

Symptoms to watch for include rising lock wait times, high request tail latency, dropping throughput, many threads in `BLOCKED` or `WAITING` state, and resource wait cycles. Thread dumps (`jcmd <pid> Thread.print`) and Java Flight Recorder can help locate contention; however, `WAITING` or waiting on I/O does not by itself prove a deadlock. You must trace **which thread holds which lock and what it is waiting on**; some deadlocks involving I/O or callbacks may not be detected by traditional monitor deadlock detectors.

When measuring timing, distinguish **lock acquisition wait time** from **lock hold time**. Logging/metrics must keep overhead low, and the metric-recording path itself must not become a long blocking call directly under a lock.

## 8. Rules of Thumb

- **Keep locks for shared state:** validate invariants, snapshot, claim, short updates, publish internal state.
- **Release locks before uncontrolled calls:** network/file I/O, callbacks, hooks, listeners, task scheduling that may run inline, waiting for results, and operations with unknown latency.
- **Re-enter locks conditionally:** verify version/state/operationId before applying results; define contention and ordering handling.
- **Design for failures and side effects:** exceptions/timeouts/retries/idempotency/reconciliation; do not use local locks to pretend an external API is an atomic transaction.
- **Verify through observation:** measure lock hold time, lock wait time, traces/thread dumps, and test with slow callbacks, reentrant callbacks, and two competing threads.

**Self-check question:** A method holds `synchronized(lock)` and calls `future.join()`. The future only completes after a task that needs to enter `synchronized(lock)`. What happens? **Answer:** The thread holding the lock waits for the future; the task needing the lock cannot complete, creating a wait cycle. Decide what state needs to be read/updated under the lock, release the lock before waiting, and re-check the state after the future completes.