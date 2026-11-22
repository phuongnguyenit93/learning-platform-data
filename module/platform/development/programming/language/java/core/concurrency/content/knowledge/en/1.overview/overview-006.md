# Shared Mutable State, Coordination, and Thread Confinement in Java

When multiple threads process work concurrently, the hard part is usually not **creating threads**, but answering **who is allowed to read, modify, and publish data, and what rules threads follow when waiting for one another**. The three core concepts of this article are:

- **Shared mutable state:** state that can change and can be accessed by multiple threads, such as a shared counter, balance, cache, or task list.
- **Coordination:** mechanisms for coordinating progress and exchanging signals between threads or tasks, such as waiting for results, signaling completion, passing work through a queue, or limiting the number of tasks.
- **Thread confinement:** a design in which mutable state is owned and manipulated by only one thread at a time, thereby avoiding the need to synchronize on that state.

These three concepts are related but do not replace one another: a `CountDownLatch` can make workers wait at the right time, but **does not automatically make `counter++` atomic**; `synchronized` protects shared state, but does not by itself solve how to stop a pipeline; and a variable declared inside a method **is not truly confined** if its reference is passed to another thread.

> Scope: **general Java** concurrency mechanisms (Java Memory Model, `java.lang`, `java.util.concurrent`). Spring Framework-specific concurrency mechanisms are not covered.

## 1. Identifying shared mutable state

Data becomes **shared** when the same object or memory location can be accessed from multiple threads. It is **mutable** when its contents can be changed after creation. If both conditions hold at the same time, the design must define how access is controlled.

For example:

```java
final class Metrics {
    int processed; // Mutable, can be shared when Metrics is used across multiple threads.
}
```

The `processed` variable is not automatically safe just because it lives inside a Java object. If the same `Metrics` instance is accessed by multiple workers, each worker can read and write this field.

It is important to distinguish:

| Case | Shared mutable state? | Right way to think about it |
| --- | --- | --- |
| Each task creates its own `StringBuilder` and does not share it | No | Each task owns its own data |
| Multiple threads read a safely published `String` | Shared, but immutable | No lock is needed to protect changes to `String` because it does not change |
| Multiple threads increment `int count` on one instance | Yes | Must ensure atomicity and visibility |
| Multiple threads write to one `ArrayList` | Yes | `ArrayList` does not guarantee thread safety on its own |
| One thread updates a `HashMap`, another thread reads the same map | Yes | Requires publication, visibility, and data structure protection |
| Multiple threads receive the same `AtomicInteger` reference and call `incrementAndGet()` | Yes | Increments on the atomic variable are linearized; multi-step logic still requires analysis |

**Declaration location does not determine ownership.** A `static` field often easily becomes shared, but an instance field is also shared if the instance passes across multiple threads. A local reference such as `List<T> local` can point to a shared list; conversely, a field belonging to an object used by only a single thread can be completely confined.

### Three error categories to separate

1. **Atomicity:** does a logical operation execute as an indivisible step that cannot be interleaved?
2. **Visibility:** when thread A updates state, is thread B guaranteed to see the update under the required rules?
3. **Ordering:** do read/write operations have ordering guarantees provided by the Java Memory Model?

A mechanism may solve part of the problem without solving all of it. For example, `volatile int count` provides visibility and ordering for volatile accesses, but `count++` still consists of multiple logical operations and is therefore not atomic.

## 2. Data race and lost update: why is `count++` dangerous?

Suppose two threads both execute `count++`. The operation can be understood at the logical level as follows:

```text
count = 10

Thread A                         Thread B
read count -> 10
                                 read count -> 10
compute 10 + 1
                                 compute 10 + 1
write count = 11
                                 write count = 11

Result: 11, even though there were two increments; expected result: 12.
```

This is an example of a **lost update**: the read, compute, and write steps are interleaved. The execution schedule above is only one possible schedule, not a schedule Java always chooses.

```java
final class UnsafeCounter {
    private int count;

    void increment() {
        count++; // Read-modify-write, not atomic.
    }

    int get() {
        return count; // No visibility guarantee when read from another thread.
    }
}
```

Even if `int` is changed to `volatile int`, two threads can still read the same value before both writing; `volatile` does not turn a read-modify-write sequence into an atomic operation.

If multiple threads access the same variable, at least one access is a write, and the conflicting accesses lack the necessary **happens-before** relationship, the program has a **data race** under the Java Memory Model. The consequence is not only lost increments: the program can also read stale state or observe related fields in a way that violates the design invariant.

An **invariant** is a condition that must hold at valid observable points, such as `balance >= 0` or `available + reserved == capacity`. Protecting each field individually does not necessarily protect an invariant that spans multiple fields.

## 3. Java Memory Model: what does it mean to observe data safely?

The Java Memory Model (JMM) defines guarantees about ordering and visibility between actions across threads. The key concept is **happens-before** (HB): if action X happens-before action Y, the memory effects of X must be observable at Y under the rules of the memory model, provided they are not overwritten by other valid writes.

Important relationships:

| Relationship | Key guarantee |
| --- | --- |
| Program order within the same thread | An earlier action in program order happens-before a later action in that thread |
| `Thread.start()` | Actions before calling `start()` happen-before actions in the newly started thread |
| Successful `Thread.join()` | Actions of the waited-on thread happen-before the calling thread continues after `join()` |
| Monitor (`synchronized`) | An unlock on a monitor happens-before a subsequent lock on the **same** monitor |
| `volatile` access | A volatile write happens-before a subsequent volatile read in synchronization order on the same variable |
| `ExecutorService.submit` and `Future.get` | Actions before submitting a task happen-before actions in the task; actions in the task happen-before actions after retrieving the result via `Future.get()` |
| `BlockingQueue` | Actions before placing an element into the queue happen-before actions after another thread takes the corresponding element from the queue |
| `CountDownLatch` | Actions before `countDown()` happen-before actions after the corresponding `await()` returns normally |

For example: data initialized before `thread.start()` has visibility to the child thread. If the child thread computes a result and the main thread successfully calls `join()`, the main thread can read the published result through that HB relationship. This is one reason a thread's result can be read after `join` even if the value is not `volatile`, as long as there are no additional conflicting accesses from other threads.

**HB does not mean locking the entire application.** It is an ordering/visibility relationship. A program can establish HB relationships through locks, volatile, queues, thread lifecycle, or appropriate synchronization utilities.

### Safe publication

**Safe publication** means passing an object reference to another thread in a way that guarantees the receiving thread sees a valid initialized state. Common ways include publishing via a monitor, a volatile reference, a concurrent data structure, timely task submission to an executor, or the thread start relationship.

`final` fields have special initialization rules when the constructor does not let the `this` reference escape; however, **a final reference does not make the referenced object immutable**:

```java
final class Holder {
    final java.util.List<String> names = new java.util.ArrayList<>();
}
```

You cannot reassign the `names` reference, but you can still call `names.add(...)`. If the list is modified by multiple threads, having a `final` field does not make `ArrayList` thread-safe.

## 4. Priority strategy: reduce shared mutable state before using locks

A useful decision order:

1. **Do not share** if there is no need: use local variables, per-task objects, or have each worker keep its own state.
2. **Share immutable data** via safe publication when possible: for example, configuration modeled as a `record` containing immutable values.
3. **Exchange data via queues/messages** instead of having multiple workers modify the same collection.
4. **Use atomic operations** when the invariant fits within a single variable and the atomic API supports the exact operation.
5. **Use locks or higher-level synchronization constructs** when multiple steps or multiple fields must satisfy an invariant together.

There is no rigid order for every architecture. The decision depends on requirements for correctness, latency, throughput, workload, and maintainability.

### Immutable snapshot

One design approach is to build a result in one thread and then create an immutable value to pass to another thread:

```java
record Report(String name, long total) {}

static Report createReport(String name, long total) {
    return new Report(name, total);
}
```

Here `String`, `long`, and `record` contain no internal mutable structures. However, a record **is not automatically deep-immutable**: if a record contains a `List<String>`, you should create a snapshot such as `List.copyOf(input)` and ensure the elements inside the list themselves meet the immutability requirement.

When an entire configuration needs to be replaced, it is often easier to reason about replacing an **immutable snapshot** through a safely published reference rather than sequentially mutating multiple fields of a shared object.

## 5. Protecting shared state with `synchronized`

`synchronized` uses an object's **intrinsic monitor lock**. At any given time, at most one thread can hold the same monitor; other threads needing that lock must wait. Unlocking and then locking the same monitor also establishes a happens-before relationship.

Standalone example, runnable with Java 17+:

Save as `SynchronizedCounterDemo.java`:

```java
public class SynchronizedCounterDemo {
    static final class Counter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int get() {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();

        Runnable work = () -> {
            for (int i = 0; i < 100_000; i++) {
                counter.increment();
            }
        };

        Thread first = new Thread(work);
        Thread second = new Thread(work);

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println(counter.get());
    }
}
```

Compile and run:

```bash
javac SynchronizedCounterDemo.java
java SynchronizedCounterDemo
```

Exact stdout:

```text
200000
```

Two threads increment **one** counter; `increment()` cannot interleave at `value++` because both must hold `counter`'s monitor. `get()` also uses that monitor to read state consistent with the protected operations. The two `join()` calls ensure the main thread waits for both workers to finish before printing.

**A lock must protect the entire invariant**, not just a single write operation. For example, deducting a balance requires checking the condition and updating **within the same critical section**:

```java
final class Wallet {
    private int balance;

    Wallet(int initialBalance) {
        if (initialBalance < 0) {
            throw new IllegalArgumentException("Negative initial balance");
        }
        balance = initialBalance;
    }

    synchronized boolean withdraw(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
        if (balance < amount) {
            return false;
        }
        balance -= amount;
        return true;
    }

    synchronized int balance() {
        return balance;
    }
}
```

If `if (balance >= amount)` and `balance -= amount` are split into two separate lock acquisitions, another thread can change `balance` between the two steps, breaking the invariant. Locking must be consistent: there must be no other access path that modifies `balance` while bypassing the same protection rule.

**Note:** an instance `synchronized` method locks `this`; a `static synchronized` method locks the `Class` object. These two monitors are different. Locking the wrong object does not provide the intended mutual exclusion.

## 6. `volatile`, atomic variables, locks: choosing the right tool

| Tool | Suitable properties | Does not solve on its own |
| --- | --- | --- |
| `volatile boolean stopped` | A flag written by one/more threads and observed by others, with visibility/ordering | Atomicity of multi-step read-modify-write; consistency across multiple fields |
| `AtomicInteger.incrementAndGet()` | Incrementing an integer variable atomically | Transactions updating multiple objects/fields |
| `AtomicReference.compareAndSet(...)` | Conditionally swapping a reference based on an observed value | Correctness of the underlying mutable object if it is still mutated directly |
| `synchronized` | Protecting critical sections and multi-operation invariants under the same monitor | Automatically eliminating deadlocks or long-running blocking work |
| `ReentrantLock` | Explicit lock with `tryLock`, interruptible lock option, and `Condition` | Automatically releasing the lock if `unlock()` is forgotten; `finally` is required |
| `ConcurrentHashMap` | Concurrent map access, many per-key/API-specific atomic operations | Atomicity of a sequence of multi-key operations, or safety of mutable values |

### Stop flag case

```java
final class StopSignal {
    private volatile boolean stopped;

    void requestStop() {
        stopped = true;
    }

    boolean shouldStop() {
        return stopped;
    }
}
```

Workers can read `shouldStop()` in a loop; however, if a worker is blocked indefinitely in `BlockingQueue.take()` or I/O, **the flag alone cannot wake the thread**. Interruption, a timeout, or an appropriate close protocol is also needed. A loop that only checks the flag continuously can also waste CPU.

### Single-variable counter case

```java
import java.util.concurrent.atomic.AtomicInteger;

final class AtomicCounter {
    private final AtomicInteger count = new AtomicInteger();

    int incrementAndGet() {
        return count.incrementAndGet();
    }

    int get() {
        return count.get();
    }
}
```

`AtomicInteger` is suitable if the logic is incrementing/decrementing a single value. If success depends on **two related values**, merely calling two separate atomic operations does not make the whole sequence a single transaction.

### When using `ReentrantLock`

```java
import java.util.concurrent.locks.ReentrantLock;

final class GuardedValue {
    private final ReentrantLock lock = new ReentrantLock();
    private int value;

    void increment() {
        lock.lock();
        try {
            value++;
        } finally {
            lock.unlock();
        }
    }

    int get() {
        lock.lock();
        try {
            return value;
        } finally {
            lock.unlock();
        }
    }
}
```

Every access path to `value` must follow the same lock. Use `finally` to release the lock even if an exception occurs. Avoid holding a lock across I/O operations or uncontrolled callbacks whenever possible, as that increases wait times and deadlock risk.

## 7. Coordination: protecting data and coordinating progress are two separate problems

**Mutual exclusion** answers: *who is allowed to enter the critical section?*

**Coordination** answers: *which task needs to wait for which event, who signals completion, through which channel do work and results flow, and when to stop?*

For example: multiple workers updating a value with `AtomicInteger` solves atomic increments, but the aggregator thread still needs to know **when all workers have finished** to produce the final report. Conversely, the aggregator thread can use `CountDownLatch.await()` to wait for enough workers, but that does not make `int count++` increments across workers safe.

### Main coordination tools

| Java tool | Purpose | Key properties to remember |
| --- | --- | --- |
| `Thread.join()` | Wait for a thread to terminate | Caller may block; do not use sleep to guess completion time |
| `Future.get()` | Wait for and retrieve a task's result | May block and throw `InterruptedException`/`ExecutionException`; `get(timeout, unit)` bounds wait time |
| `CountDownLatch` | Wait for a fixed number of completion signals | One-shot; each `countDown()` decrements the count; cannot be reset |
| `CyclicBarrier` | Let a group of workers meet at a point before continuing | Reusable across rounds; broken barriers must be handled |
| `Phaser` | Phase-based synchronization with dynamic participant registration/deregistration | Suitable for multi-stage rounds with a flexible number of participants |
| `Semaphore` | Limit the number of permits for a resource/task | `acquire()` may block; must `release()` properly |
| `BlockingQueue` | Pass work between producers and consumers | `put()` may wait when full, `take()` may wait when empty |
| `Condition` on `Lock` | Wait for and signal a predicate under a lock | Always check the condition in a `while` loop; do not rely on a single `signal()` |
| `wait()/notifyAll()` | Monitor-level condition mechanism | Must hold the monitor, check predicate in a `while` loop, avoid if higher-level tools fit better |

`Thread.sleep(...)` only pauses the thread; it **does not guarantee** that other workers have finished, that data has been safely published, or that a condition is true. Use `join`, futures, latches, or queues when concrete completion relationships are needed.

## 8. Producer–consumer example: coordination via `BlockingQueue`

A bounded queue both transfers data and creates **backpressure**: the producer must wait if the consumer cannot keep up. This avoids having multiple workers directly modify the same result list.

The following standalone example uses **one** producer, **one** consumer, and `0` as the termination signal (valid inputs are positive integers only). Save as `BlockingQueueDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BlockingQueueDemo {
    public static void main(String[] args) throws Exception {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);
        ExecutorService executor = Executors.newFixedThreadPool(2);

        try {
            Future<?> producer = executor.submit(() -> {
                for (int i = 1; i <= 5; i++) {
                    queue.put(i);
                }
                queue.put(0); // Sentinel: end of data stream.
                return null;
            });

            Future<Integer> consumer = executor.submit(() -> {
                int sum = 0;
                while (true) {
                    int item = queue.take();
                    if (item == 0) {
                        return sum;
                    }
                    sum += item;
                }
            });

            producer.get();
            System.out.println("Tong = " + consumer.get());
        } finally {
            executor.shutdown();
        }
    }
}
```

Run with Java 17+:

```bash
javac BlockingQueueDemo.java
java BlockingQueueDemo
```

Exact stdout:

```text
Tong = 15
```

What is guaranteed?

- The producer can `put` concurrently while the consumer calls `take`; the queue handles internal synchronization, so no manual locking around a list is needed.
- `ArrayBlockingQueue<>(2)` holds at most two pending elements at a time; `put` can block when full, and `take` can block when empty. This is **blocking coordination**, not non-blocking I/O.
- The consumer is the sole owner of `sum`. Two threads never modify that variable concurrently, so `AtomicInteger` is not needed for `sum`.
- The sentinel `0` is valid only because real data does not contain `0` and there is exactly one consumer. If there are multiple consumers, the termination protocol must ensure each consumer exits properly.
- The `Future.get()` calls wait for completion and publish the result to the caller. `shutdown()` releases the executor lifecycle after the submitted tasks.

**Production considerations:** you need handling paths for when the producer fails before sending the sentinel, when the consumer fails, when a task is cancelled, and when the caller cannot wait indefinitely. Depending on requirements, you can use timeouts, cancellation, close signals, shared error states, or higher-level coordination mechanisms. The example above illustrates only the success path.

## 9. Coordination example when workers must all finish: `CountDownLatch`

`CountDownLatch` is useful when a coordinating thread needs to wait for a group of independent tasks to report completion. It is **not** a mutex.

Save as `LatchDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class LatchDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch finished = new CountDownLatch(3);
        AtomicInteger total = new AtomicInteger();

        for (int i = 1; i <= 3; i++) {
            final int contribution = i * 10;
            Thread worker = new Thread(() -> {
                try {
                    total.addAndGet(contribution);
                } finally {
                    finished.countDown();
                }
            });
            worker.start();
        }

        finished.await();
        System.out.println("Tong = " + total.get());
    }
}
```

```bash
javac LatchDemo.java
java LatchDemo
```

Exact stdout:

```text
Tong = 60
```

Here `AtomicInteger` ensures safe addition when workers update `total`; `CountDownLatch` ensures the `main` thread prints only after all three workers have finished and called `countDown()`. The two tools address **two different concerns**. Placing `countDown()` in `finally` prevents a worker that fails mid-processing from forgetting to decrement the latch. However, real applications still need to collect and report worker errors, because a latch reaching 0 does not prove all workers succeeded.

If a group of tasks has multiple rounds and must wait for each other at the end of **each round**, consider `CyclicBarrier` or `Phaser` instead of reusing a latch that has reached 0. A `CountDownLatch` cannot be reset.

## 10. Thread confinement: who owns the state?

**Thread confinement** means a mutable object is accessed exclusively by one thread during an ownership phase, without allowing other threads to concurrently modify or read that state without coordination. Because there is no conflicting access, locking around each operation can be avoided.

Common patterns:

1. **Stack/task confinement:** Each call creates its own state and does not let references escape; this is the simplest option.
2. **Actor/event-loop ownership:** One worker owns a map/cache/accumulator and receives commands via a queue; other threads send messages instead of touching the state.
3. **`ThreadLocal<T>`:** Each thread has a value bound to that thread; useful for certain contexts or buffers, but its lifecycle must be managed especially carefully when threads are reused.

### Simplest approach: task-local state

```java
static String formatForOneTask(String id) {
    StringBuilder buffer = new StringBuilder(); // Each call has its own builder.
    buffer.append("job-").append(id);
    return buffer.toString(); // Return an immutable String.
}
```

Two threads can run this method concurrently without sharing `buffer`. Neither `synchronized` nor `ThreadLocal` is needed. This is why **reducing sharing** is often simpler than adding synchronization tools.

However, if `buffer` is placed into a shared collection or its reference is passed to another thread before completion, the state may no longer be confined. The rule is **never let a mutable reference escape ownership**.

### When `ThreadLocal` is actually needed

`ThreadLocal` stores a separate value per thread, often useful when a legacy API requires thread-scoped context without a convenient way to pass explicit parameters. It does not make the object inside `ThreadLocal` thread-safe if a reference to that object is handed off to another thread.

Standalone example illustrating cleanup with a thread pool that reuses workers. Save as `ThreadLocalDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadLocalDemo {
    private static final ThreadLocal<StringBuilder> BUFFER =
            ThreadLocal.withInitial(StringBuilder::new);

    private static String process(String id) {
        StringBuilder buffer = BUFFER.get();
        try {
            buffer.append("job-").append(id);
            return buffer.toString();
        } finally {
            BUFFER.remove(); // Remove state attached to the worker after the task.
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<String> first =
                    executor.submit(() -> process("A"));
            Future<String> second =
                    executor.submit(() -> process("B"));

            System.out.println(first.get());
            System.out.println(second.get());
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac ThreadLocalDemo.java
java ThreadLocalDemo
```

Exact stdout:

```text
job-A
job-B
```

Both tasks run on the same worker because `newSingleThreadExecutor()` reuses the thread; `remove()` ensures the second task receives a fresh `StringBuilder` instead of retaining the previous task's contents. For state used only within a single call like in this example, **a local variable is still the preferred choice**; `ThreadLocal` is used here to accurately illustrate the mechanism and its lifecycle risks.

**Important limitations of `ThreadLocal`:**

- It binds state to a **thread**, not to a **request** or `CompletableFuture`. An async chain running across multiple threads does not automatically carry `ThreadLocal` values between stages.
- Threads in a pool can outlive tasks; if `remove()` is forgotten, another task on the same worker can encounter stale data, and referenced objects can be retained in memory longer than intended.
- `ThreadLocal` is not a security mechanism or a way to synchronize state across threads. It prevents sharing through the *ThreadLocal access path*, not when a programmer intentionally shares the mutable object itself.
- In Java 21+, virtual threads are still threads and can use `ThreadLocal`, but attaching heavy data to a very large number of virtual threads can consume significant memory. This belongs to core Java; no framework-specific mechanism is needed.

## 11. Handover ownership: transfer ownership instead of sharing freely

An effective design is to split work into stages where each stage has **one owner of mutable state**:

```text
Data source
    |
    v
[Producer - owns input state]
    |
    | sends item/snapshot via BlockingQueue
    v
[Consumer - owns accumulated state]
    |
    | publishes immutable result via Future
    v
[Caller - reads result]
```

Benefits:

- The producer does not need a lock around the consumer's accumulator.
- The queue defines the handoff point and provides visibility rules.
- The consumer updates its state in the order messages are received.
- The caller retrieves the completed result via a future; it never needs to read an object that is being mutated mid-flight.

Note: **putting a mutable reference into a queue does not magically transfer ownership**. The producer must stop modifying the object after handoff, or send a copy/immutable snapshot. If the producer continues modifying that same object while the consumer reads it, shared mutable state still exists despite the queue in between.

Error and cancellation boundaries must also be defined: who closes the producer, who sends the termination signal, who decides what happens when the consumer fails, and who is responsible for releasing resources.

## 12. Using concurrent collections within their guarantee boundaries

Collections in `java.util.concurrent` reduce the need to write manual locks around shared data structures:

- `ConcurrentHashMap`: concurrent reads/updates on a map. Methods such as `putIfAbsent`, `compute`, and `merge` provide atomic operations according to the API contract. Do **not** assume two separate calls `get` followed by `put` form an atomic operation.
- `ConcurrentLinkedQueue`: non-blocking concurrent queue with no default capacity bound; callers need their own protocol to know when data is available and when to stop.
- `ArrayBlockingQueue`/`LinkedBlockingQueue`: provide blocking `put/take` and producer–consumer communication. With `LinkedBlockingQueue`, consider configuring an appropriate capacity to avoid unbounded queue growth.
- `CopyOnWriteArrayList`: suitable for read-heavy, write-rare workloads because mutating operations typically copy the underlying structure; not optimal for continuously updated data.
- `LongAdder`: useful for statistics counters updated by many threads; `sum()` while threads are still updating **is not necessarily an atomic snapshot**. If you need an exact observation point synchronized with other updates, a more suitable design is required.

For example, `ConcurrentHashMap<String, Integer>` only protects map operations per its contract. If the value is a mutable `ArrayList` and multiple threads freely call `map.get(key).add(...)`, the list can still race. Container thread safety does not automatically extend to mutable contents stored inside it.

## 13. Avoiding deadlock, starvation, and incorrect condition waiting

### Deadlock from acquiring multiple locks in inconsistent order

Suppose thread A holds lock X and waits for lock Y, while thread B holds Y and waits for X:

```text
Thread A: lock X -> wait for Y
Thread B: lock Y -> wait for X
                   |
                 deadlock
```

Ways to reduce the risk include enforcing a **consistent lock ordering** when multiple locks must be acquired, minimizing lock hold time, avoiding uncontrolled logic while holding a lock, and using `tryLock` with a timeout when system requirements allow. Lock ordering must be followed across all relevant code paths, not just a single method.

**Starvation** occurs when a task does not receive reasonable progress even though other tasks keep running; it is not the same as deadlock. Fair locks/queues can help fairness in some cases, but they do not replace load-limiting design and scheduler management.

### Waiting on conditions with monitors

When you must use `Object.wait/notifyAll`, the rule is to guard the predicate and wait **in a `while` loop under the same monitor**:

```java
final class Gate {
    private boolean open;

    synchronized void awaitOpen() throws InterruptedException {
        while (!open) {
            wait();
        }
    }

    synchronized void open() {
        open = true;
        notifyAll();
    }
}
```

A thread calling `wait()` must hold the monitor; `wait` releases the monitor while waiting and reacquires it before returning. Use `while` because the thread may wake up when the condition is still false (including spurious wakeups and another thread changing the condition). `notifyAll` wakes eligible waiters so they can recheck the predicate; it does not immediately grant execution.

For typical producer–consumer or coordination tasks, `BlockingQueue` and higher-level utilities usually lead to less error-prone code.

## 14. Cancellation, interruption, and lifecycle management

A sound concurrency design does not just return results when everything goes well; it must define **who has the right to stop**, **how blocked threads are woken up**, and **whether errors propagate back to the caller**.

- `Thread.interrupt()` sends an interruption request; it does not forcibly terminate a thread. Operations such as `sleep`, `wait`, `join`, and `BlockingQueue.put/take` can respond with `InterruptedException`.
- If you catch `InterruptedException` and cannot handle it completely, you should usually end the task and/or restore the interrupt flag with `Thread.currentThread().interrupt()`. Do not swallow the exception and continue waiting indefinitely.
- `Future.cancel(true)` can request interruption of a running task, but ultimate success depends on whether the task supports interruption and whether the blocking point responds to it.
- `ExecutorService.shutdown()` stops accepting new tasks and lets submitted tasks finish; `shutdownNow()` attempts to stop active tasks and returns waiting tasks, though it also does not guarantee immediate termination.
- When using an explicit `Lock`, place `unlock()` in `finally`. When using queues, semaphores, or latches, plan cleanup and termination signals on error paths as well.
- With `Semaphore`, only `release()` permits that the task actually `acquire()`d successfully. Excess releases can increase the permit count beyond the logical limit.
- When reporting results, use clear convergence points (`Future.get`, `join`, latch, or signal) and distinguish **completion** from **success**. A task ending with an exception has still completed.

If a request is cancelled while a worker still holds a mutable context, ensure the context is closed or cleaned up according to its ownership lifecycle; if threads are reused, check any remaining `ThreadLocal` values.

## 15. Choosing a design through three concrete problems

### A. Counting completed requests

**Problem:** multiple workers increment a counter, with no invariant spanning multiple variables.

Typically suitable design: `AtomicInteger`, or `LongAdder` for high-contention statistics where `sum()` semantics are acceptable. Do not put a coarse lock around the entire request processing just to increment a counter. If you need a consistent statistical snapshot at a specific point, clearly define the completion point and how it is read.

### B. A wallet that must guarantee a non-negative balance

**Problem:** need to check `balance >= amount` before deducting.

Suitable design: keep the check and update in **one critical section** (`synchronized` or a lock), or use a carefully designed CAS loop for single-variable state. `volatile int balance` is not enough, because checking and deducting is a compound operation. If transferring money between two wallets, you need an atomic design across two objects and a lock ordering that avoids deadlock; locking each wallet independently and updating them one after another does not guarantee the overall transaction.

### C. Multiple sources sending events, one worker updating aggregated state

**Problem:** only one aggregation logic needs to update state; the various producers do not need to modify that state directly.

Suitable design: use a bounded `BlockingQueue`; producers send events/immutable messages, and the consumer owns its own map and mutable state. Ensure the consumer shuts down properly and reports errors. The main advantage is changing **data ownership**, eliminating the need to lock around every map modification.

## 16. Common misconceptions

1. **"`volatile` solves race conditions."** Only true for specific protocols based on visibility/ordering; `volatile count++` can still suffer lost updates.
2. **"Having a `CountDownLatch` makes shared worker data thread-safe."** A latch coordinates waiting and establishes HB relationships; it does not provide mutual exclusion for concurrent updates during execution.
3. **"Using `AtomicInteger` means the whole object is atomic."** Only the operations defined on the atomic variable have that guarantee.
4. **"A `final` field makes a collection immutable."** It fixes the reference; it does not prevent modifying elements in the collection.
5. **"Local variables are always safe."** A local variable only holds a reference; the referenced object can still be shared.
6. **"A concurrent map makes its values safe too."** The thread safety of the values must be analyzed separately.
7. **"A queue guarantees there are no data races."** If a producer keeps modifying an object after putting it into the queue, a data race can still occur.
8. **"`ThreadLocal` is per-request data."** It is **per-thread** data; thread reuse and async hops can break that assumption.
9. **"`Thread.sleep()` is a mechanism for waiting for workers to finish."** Sleep time is just a delay; it does not prove an event has happened.
10. **"`notify()` wakes one waiter so you can skip checking the condition."** A waiter must still check the predicate in a `while` loop after waking up and reacquiring the monitor.
11. **"Using multiple locks is always faster than one lock."** Splitting locks can increase concurrency, but it also increases the risk of invariant violations and deadlocks.
12. **"`shutdown()` stops tasks immediately."** It does not forcibly terminate running tasks; proper cancellation design is still required.

## 17. Checklist when designing shared state and coordination

Before implementing, answer these questions in order:

1. **Which state is mutable?** Who creates it, who owns it, and who still holds references to it?
2. **Does it need to be shared?** Can an immutable snapshot, local state, or a single exclusive consumer be used instead?
3. **If sharing is required, what invariants must hold?** Is a single atomic variable enough, or do multiple fields need a critical section?
4. **By what mechanism do other threads see changes?** Is there a clear happens-before relationship via lock, volatile, queue, start/join, or future?
5. **What condition are workers waiting on?** Use an appropriate queue, latch, future, semaphore, barrier, or condition; avoid guessing with sleep.
6. **How does the system stop and report errors?** Who sends the termination signal, who handles interruption, and who cancels and closes resources?
7. **Have thread pool boundaries been checked?** Is `ThreadLocal` cleaned up, and could data from a previous task leak into the next task?
8. **Have latency and contention been measured?** Avoid overly broad locks and unbounded queues, but never trade correctness for speculative performance.

With Java concurrency, the best starting point is **defining state ownership**, and then choosing mechanisms for **protecting invariants** and **coordinating progress** separately. From there, decide whether `synchronized`, atomic variables, concurrent collections, queues, or `ThreadLocal` are needed.
