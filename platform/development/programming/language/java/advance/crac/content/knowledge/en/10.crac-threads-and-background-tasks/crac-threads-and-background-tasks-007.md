# Locks, Condition Waiting, and State Visibility Between Threads

A multithreaded Java application often shares data and resources: workers read configuration, schedulers update state, request threads write to a cache, while a background task monitors progress. If threads access the same data without proper coordination mechanisms, the program can suffer race conditions, stale reads, lost updates, or deadlocks.

In an application using CRaC, these issues also directly affect the moment of checkpointing. Before saving process state, the application must bring threads to a safe boundary: no half-finished data updates, no tasks still using resources about to be closed, and shared conditions consistently protected. After restore, threads must resume from a valid state and only restart once dependencies are ready.

To achieve that, you must understand three foundational concepts: **locks** protect shared data regions; **condition waiting** allows a thread to sleep until a desired state appears; **visibility** ensures changes made by one thread can be observed by other threads according to the Java Memory Model.

## 1. Why Do Multiple Threads Need Coordination?

Suppose two workers increment the same counter:

```java
counter++;
```

The statement above looks like a single operation, yet actually consists of reading the current value, computing the new value, and writing it back. If two threads both read the value `10`, both may compute `11` and write `11`. The final result is `11` instead of `12`. This is a lost update, a form of race condition.

Another issue is visibility. Thread A writes `running = false`, yet Thread B has no proper synchronization relationship. The JVM and CPU may allow Thread B to continue observing the old value for an indeterminate duration under the Java Memory Model. Therefore, the following loop is not a safe way to stop a thread:

```java
boolean running = true;

// Worker thread
while (running) {
    doWork();
}

// Management thread
running = false;
```

There is no happens-before relationship between the write and read of `running`, so the worker is not guaranteed to see the change. You must use `volatile`, a lock, or a suitable synchronization mechanism.

In real applications, concurrency bugs often arise when:

- Multiple threads update the same object or collection.
- One thread checks state while another thread modifies that state.
- A worker waits for data yet is not woken up at the right time.
- One thread closes a connection or executor while another thread is still using it.
- Multiple threads acquire locks in different orders and wait on each other.
- Checkpointing starts while business logic is midway through updating multiple related fields.

## 2. Visibility Under the Java Memory Model

The Java Memory Model (JMM) defines how threads observe each other's memory reads and writes. One thread does not necessarily observe all operations of another thread in exact source-code order without a synchronization relationship recognized by the JMM.

The key concept is **happens-before**. If action A happens-before action B, memory writes prior to A are guaranteed to be visible to B according to the JMM rules.

Some commonly used happens-before relationships:

| Relationship | Practical meaning |
|---|---|
| Unlocking a monitor happens-before a subsequent lock on the same monitor | Changes inside `synchronized` are seen by a thread acquiring the same lock afterward |
| Writing a `volatile` variable happens-before a subsequent read of that variable | A reading thread sees the value published via the volatile variable and operations preceding the write |
| Calling `Thread.start()` happens-before actions inside the newly started thread | The new thread sees state established before calling `start()` |
| All actions in a thread happen-before another thread successfully returns from `join()` | The thread calling `join()` sees results produced by the finished thread |
| Actions before placing an element into a concurrent collection/queue are published per the collection's contract | A thread taking the element can observe data prepared before insertion |
| `countDown()` happens-before actions following a successful `await()` on the same `CountDownLatch` | Waiting threads can observe results published before the count reaches 0 |

You do not need to memorize every rule at once. When sharing state, identify which synchronization mechanism establishes a happens-before relationship between writer and reader.

### 2.1. Visibility Differs from Atomicity

Visibility is the ability of one thread to see changes made by another thread. Atomicity is the property that a guarded operation cannot be observed in a partially executed state. The two concepts are related yet not identical.

For example:

```java
private volatile int count;

public void increment() {
    count++;
}
```

`volatile` gives reads/writes of `count` JMM visibility and ordering semantics, yet `count++` remains a read–modify–write operation. Two threads can both read the same value and overwrite each other's result. `volatile` does not turn incrementing into an atomic operation.

If you need an independent counter increment, use `AtomicInteger`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public final class RequestCounter {
    private final AtomicInteger count = new AtomicInteger();

    public int increment() {
        return count.incrementAndGet();
    }

    public int current() {
        return count.get();
    }
}
```

If multiple fields must change together as an invariant, such as `balance` and `reservedAmount`, an atomic for each field may not be enough. In that case, you need a lock spanning the entire operation or an atomic data structure designed for that invariant.

## 3. `synchronized` and Intrinsic Monitors

The `synchronized` keyword uses the monitor associated with an object. At any one time, only one thread can own that monitor. Other threads wanting to enter a `synchronized` region on the same monitor must wait.

Example guarding a counter:

```java
public final class SafeCounter {
    private int count;

    public synchronized void increment() {
        count++;
    }

    public synchronized int get() {
        return count;
    }
}
```

The two instance methods above lock on the same monitor `this`. Thus, `increment()` and `get()` do not execute concurrently on the same object. When a thread exits a synchronized region, unlocking the monitor happens-before the next lock on the same monitor. This both protects the atomicity of the code region and provides visibility for the guarded data.

A `synchronized` block can be used to choose the lock scope:

```java
public void update() {
    validateInput();

    synchronized (stateLock) {
        updateSharedState();
    }

    publishMetric();
}
```

Only the part updating shared data needs locking. Input validation or recording metrics can stay outside the locked region if they do not depend on the protected invariant.

### 3.1. Which Object Should You Lock On?

Do not use an object that is easily replaced or arbitrarily locked by external code. You can create a dedicated private object:

```java
private final Object stateLock = new Object();
```

Threads needing coordination must use that exact lock object. Two `synchronized` blocks on two different objects do not guard the same state.

Avoid locking on:

- String literals such as `"LOCK"`, because strings can be interned and unintentionally shared.
- Public objects such as `this` when callers might synchronize on the same instance.
- An object reference that can be reassigned, causing threads to lock on different monitors.
- Global `Class` objects when you do not need to lock across all instances of a class.

### 3.2. Monitors Are Reentrant

Java intrinsic monitors are reentrant: a thread already owning a monitor can enter another `synchronized` region on the same monitor without deadlocking itself. Entry count is tracked by thread ownership; the thread must exit the corresponding synchronized regions before the monitor is released for other threads.

Reentrancy does not mean every nested locking design is safe. If Thread A locks X then Y, while Thread B locks Y then X, the two threads can still deadlock.

## 4. `wait`, `notify`, and `notifyAll`

`Object.wait()`, `notify()`, and `notifyAll()` coordinate threads through an object's monitor.

- `wait()` tells the thread owning the monitor to release the monitor and wait.
- `notify()` wakes up a single thread waiting on that monitor.
- `notifyAll()` wakes up all threads waiting on that monitor; each thread must reacquire the monitor before proceeding.

These methods must be called while the thread owns the corresponding monitor, usually inside a `synchronized` block. Calling them outside the monitor throws `IllegalMonitorStateException`.

### 4.1. Always Check Conditions in a Loop

Do not write:

```java
synchronized (lock) {
    if (!ready) {
        lock.wait();
    }
    useResource();
}
```

A thread can wake up due to a spurious wakeup; `notify` also does not guarantee the business condition remains true when the thread reacquires the monitor. Another thread may have changed the state in the meantime. Therefore, you must recheck the condition in a `while` loop:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    useResource();
}
```

`wait()` releases the monitor while waiting and reacquires the monitor before the method returns. After reacquiring the monitor, the thread rechecks the predicate `ready` under the same lock.

### 4.2. Simple Producer–Consumer Example

```java
import java.util.ArrayDeque;
import java.util.Queue;

public final class OneSlotQueue<T> {
    private final Object lock = new Object();
    private final Queue<T> queue = new ArrayDeque<>();

    public void put(T item) throws InterruptedException {
        synchronized (lock) {
            while (!queue.isEmpty()) {
                lock.wait();
            }
            queue.add(item);
            lock.notifyAll();
        }
    }

    public T take() throws InterruptedException {
        synchronized (lock) {
            while (queue.isEmpty()) {
                lock.wait();
            }
            T item = queue.remove();
            lock.notifyAll();
            return item;
        }
    }
}
```

The producer only adds an item when the queue is empty; the consumer only takes an item when the queue has data. Both the predicate and queue mutations are protected by the same monitor. `notifyAll()` wakes waiting threads so they recheck the condition.

This example only illustrates the monitor mechanism. In real applications, `BlockingQueue` is usually a simpler and less error-prone choice because it encapsulates waiting, signaling, and synchronization:

```java
BlockingQueue<Job> queue = new LinkedBlockingQueue<>();

// Producer
queue.put(job);

// Consumer
Job next = queue.take();
```

### 4.3. Why Is `notifyAll()` Usually Preferred?

`notify()` only wakes one arbitrary thread waiting on the monitor. If multiple kinds of predicates are waiting on the same monitor, the woken thread might not be one whose condition just became true. It may go back to waiting while the appropriate thread stays asleep.

`notifyAll()` wakes all threads so each thread checks its own predicate. This approach is usually easier to get right, even though it can create extra contention to reacquire the monitor. If better performance is needed, separate conditions/monitors or use `Condition` to wake the appropriate group of threads.

## 5. `ReentrantLock` and `Condition`

`ReentrantLock` provides explicit locking capabilities with features such as try-lock, timed lock acquisition, interruptible waiting, and multiple conditions attached to the same lock.

Example:

```java
import java.util.concurrent.locks.ReentrantLock;

public final class LockedCounter {
    private final ReentrantLock lock = new ReentrantLock();
    private int count;

    public void increment() {
        lock.lock();
        try {
            count++;
        } finally {
            lock.unlock();
        }
    }

    public int get() {
        lock.lock();
        try {
            return count;
        } finally {
            lock.unlock();
        }
    }
}
```

Every successful `lock()` must have a matching `unlock()`. Place `unlock()` in `finally` so exceptions do not leak the lock. Never call `unlock()` from another thread because `ReentrantLock` only permits the owning thread to release the lock.

### 5.1. Condition Is a Predicate Bound to a Lock

`Condition` is similar to the `wait/notify` mechanism, yet bound to a specific `Lock`. A single lock can create multiple conditions, such as `notEmpty` and `notFull` for a queue.

Example waiting for a queue to have data:

```java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class ConditionQueue<T> {
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition notEmpty = lock.newCondition();
    private final Condition notFull = lock.newCondition();
    private final java.util.ArrayDeque<T> queue =
            new java.util.ArrayDeque<>();
    private final int capacity;

    public ConditionQueue(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }
        this.capacity = capacity;
    }

    public void put(T item) throws InterruptedException {
        lock.lockInterruptibly();
        try {
            while (queue.size() == capacity) {
                notFull.await();
            }
            queue.addLast(item);
            notEmpty.signal();
        } finally {
            lock.unlock();
        }
    }

    public T take() throws InterruptedException {
        lock.lockInterruptibly();
        try {
            while (queue.isEmpty()) {
                notEmpty.await();
            }
            T item = queue.removeFirst();
            notFull.signal();
            return item;
        } finally {
            lock.unlock();
        }
    }
}
```

`await()` releases the lock while waiting and reacquires the lock before resuming. The predicate must still be checked inside a `while` loop because spurious wakeups can occur or another thread can alter the queue before the woken thread reacquires the lock.

### 5.2. `lock()` and `lockInterruptibly()`

`lock()` waits to acquire the lock and does not throw `InterruptedException` if the thread is interrupted while waiting. The interrupt flag may still be set. `lockInterruptibly()` allows canceling the wait via interruption and throws `InterruptedException`.

For background tasks that need a controlled stop before checkpointing, interruptible waiting is often useful. When catching `InterruptedException`, restore the interrupt flag if you do not propagate the exception:

```java
try {
    lock.lockInterruptibly();
    try {
        updateState();
    } finally {
        lock.unlock();
    }
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}
```

Do not swallow interrupts and continue an infinite loop. An interrupt is a coordination signal allowing a thread to terminate or transition state according to application policy.

## 6. `volatile`: Publishing Simple State

`volatile` is suitable for simple state read by multiple threads and written by one or more threads, when operations do not require a multi-step transaction.

Example worker stop flag:

```java
public final class Worker implements Runnable {
    private volatile boolean running = true;

    public void requestStop() {
        running = false;
    }

    @Override
    public void run() {
        while (running) {
            doOneUnitOfWork();
        }
    }

    private void doOneUnitOfWork() {
        // Process a single unit of work with well-defined boundaries.
    }
}
```

Writing `running = false` is published to threads reading the volatile variable. When the worker reads `false`, it exits the loop at the next check boundary. This does not automatically wait for the worker to finish; the management thread still needs to call `join()` or use a latch to wait.

`volatile` does not protect an invariant spanning multiple fields. For example, if `state` and `lastUpdatedAt` must change in sync, making each field volatile does not guarantee readers see a consistent pair of values. Use a lock or publish an immutable object via a volatile reference.

## 7. Atomic Classes and Concurrent Utilities

### 7.1. Atomic Classes

Classes in `java.util.concurrent.atomic` use atomic operations such as compare-and-set (CAS) to update a single value without explicit locks.

Example:

```java
AtomicInteger activeTasks = new AtomicInteger();

int current = activeTasks.incrementAndGet();
int remaining = activeTasks.decrementAndGet();
```

`AtomicInteger`, `AtomicLong`, `AtomicBoolean`, and `AtomicReference` suit single counters, flags, or references. If multiple interrelated values must be updated concurrently, consider a lock or an immutable state object replaced atomically.

### 7.2. CountDownLatch

`CountDownLatch` helps one thread wait for multiple pieces of work to complete:

```java
CountDownLatch completed = new CountDownLatch(3);

for (int i = 0; i < 3; i++) {
    executor.submit(() -> {
        try {
            performTask();
        } finally {
            completed.countDown();
        }
    });
}

if (!completed.await(30, TimeUnit.SECONDS)) {
    throw new IllegalStateException("Tasks did not finish in time");
}
```

`countDown()` must be called in `finally` so an error in a worker does not make the waiting thread hang forever. A latch only counts down and cannot reset for a subsequent cycle. If reuse across multiple phases is needed, consider `Phaser` or creating a new latch.

### 7.3. Semaphore

`Semaphore` limits the number of threads concurrently accessing a pool of resources. For example, limiting to at most five concurrent tasks calling an external service:

```java
Semaphore permits = new Semaphore(5);

permits.acquire();
try {
    callExternalService();
} finally {
    permits.release();
}
```

The permit must be returned in `finally`. If a thread is interrupted while waiting in `acquire()`, handle the interrupt according to the task's policy.

### 7.4. BlockingQueue and ExecutorService

`BlockingQueue` provides waiting mechanisms when a queue is empty or full. `ExecutorService` manages worker threads and task queues. These are usually the abstractions to prefer over hand-writing `wait/notify` mechanics.

Before checkpoint, determine which tasks have been accepted, which are running, and which remain in the queue. `shutdown()` prevents accepting new tasks while letting submitted tasks continue running; `shutdownNow()` requests stopping and returns waiting tasks, yet cannot force a running task to terminate safely. After restore, do not assume a shut-down executor can be restarted; typically create a new executor before submitting work.

## 8. Deadlock, Livelock, and Starvation

### 8.1. Deadlock

Deadlock occurs when threads wait on each other's resources and no thread can proceed.

Example:

```java
Object lockA = new Object();
Object lockB = new Object();

// Thread 1
synchronized (lockA) {
    synchronized (lockB) {
        updateAAndB();
    }
}

// Thread 2
synchronized (lockB) {
    synchronized (lockA) {
        updateBAndA();
    }
}
```

If Thread 1 holds `lockA` and waits for `lockB`, while Thread 2 holds `lockB` and waits for `lockA`, both are stuck.

A common way to prevent this is establishing a global lock order: every thread must acquire `lockA` before `lockB`. Additionally:

- Keep locked sections short.
- Avoid calling untrusted/uncontrolled external code while holding a lock.
- Avoid waiting on I/O, network, or user callbacks inside locked sections.
- Use `tryLock(timeout)` when wait times need to be bounded and have a timeout handling plan.
- Collect thread dumps when stuck threads are detected.

### 8.2. Livelock and Starvation

Livelock occurs when threads remain active and repeatedly react to each other without making progress on work. Starvation occurs when a thread is repeatedly denied the resources or CPU time needed to make progress.

Lock fairness can reduce certain starvation cases yet can decrease throughput. Do not enable fairness by default without a measured need. Observe actual latency and wait times.

## 9. Locks and Condition Waiting in the CRaC Cycle

Checkpointing saves the state of a running process. The fact that threads have locks, conditions, or are waiting does not replace application-level coordination requirements. A snapshot can restore thread memory and execution state according to platform capabilities, yet that does not guarantee an interrupted business operation will make sense when resumed.

For example, a worker may hold a lock and have updated one field without yet updating the second field. If a checkpoint is taken at an inappropriate boundary, the restored process could continue from an intermediate state undesired by business logic. Similarly, a thread waiting for a signal from an external system might continue waiting after restore even though that signal already occurred, was lost, or will never be sent again.

Before checkpoint, you should:

1. Stop accepting new work from HTTP, message brokers, schedulers, or queues.
2. Ask workers to finish their current unit of work or reach a safe point.
3. Wait for workers using `join()`, `CountDownLatch`, `Phaser`, or timed conditions.
4. Ensure invariants of shared data have been completely updated.
5. Close resources once no threads are using them anymore.
6. Abort the checkpoint if the timeout expires before workers finish draining.

After restore, you should:

1. Restore external dependencies such as database pools, HTTP clients, and message connections.
2. Verify required shared state.
3. Recreate executors or workers if required by the library's lifecycle.
4. Open work admission gates and mark readiness after dependencies are ready.

Do not use `Thread.sleep()` to wait until workers are "probably done". Sleeping establishes no synchronization relationship and does not prove tasks finished. Use a coordination primitive with conditions and timeouts.

### 9.1. Example Gate to Stop Accepting Tasks and Drain Workers

The following example uses `ReentrantLock` and `Condition` to guard task admission state together with the count of running tasks:

```java
import java.time.Duration;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class TaskGate {
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition drained = lock.newCondition();

    private boolean accepting = true;
    private int activeTasks;

    public boolean tryBeginTask() {
        lock.lock();
        try {
            if (!accepting) {
                return false;
            }
            activeTasks++;
            return true;
        } finally {
            lock.unlock();
        }
    }

    public void endTask() {
        lock.lock();
        try {
            if (activeTasks <= 0) {
                throw new IllegalStateException("No active task to finish");
            }
            activeTasks--;
            if (activeTasks == 0) {
                drained.signalAll();
            }
        } finally {
            lock.unlock();
        }
    }

    public boolean pauseAndDrain(Duration timeout)
            throws InterruptedException {
        long remaining = timeout.toNanos();
        lock.lockInterruptibly();
        try {
            accepting = false;
            while (activeTasks != 0) {
                if (remaining <= 0) {
                    accepting = true;
                    drained.signalAll();
                    return false;
                }
                try {
                    remaining = drained.awaitNanos(remaining);
                } catch (InterruptedException interrupted) {
                    accepting = true;
                    drained.signalAll();
                    throw interrupted;
                }
            }
            return true;
        } finally {
            lock.unlock();
        }
    }

    public void resume() {
        lock.lock();
        try {
            accepting = true;
            drained.signalAll();
        } finally {
            lock.unlock();
        }
    }

    public int activeTasks() {
        lock.lock();
        try {
            return activeTasks;
        } finally {
            lock.unlock();
        }
    }
}
```

Workers must call `tryBeginTask()` before starting a unit of work and always call `endTask()` in `finally`:

```java
if (taskGate.tryBeginTask()) {
    try {
        processOneJob();
    } finally {
        taskGate.endTask();
    }
}
```

Before checkpoint, the coordinator stops producers or consumers so no new tasks keep entering, then calls `pauseAndDrain()` with a timeout. If it returns `false`, the checkpoint lacks a safe boundary and the application must abort the request. If it returns `true`, no accepted tasks remain running through this gate.

The gate only tracks tasks registered through it. It does not automatically stop schedulers, message consumers, or queue producers; those sources must be coordinated separately. In real applications, ensure every entry path to workers goes through the gate; otherwise `activeTasks` will not fully reflect activity.

## 10. State Visibility After Restore

On restore, process memory state is restored according to CRaC and platform mechanisms. However, restore should not be viewed as a synchronization signal between threads or across multiple instances.

JMM rules remain the foundation for thread coordination when execution resumes:

- Data protected by the same monitor must continue to be read/written through that monitor.
- State published via `volatile` needs to be read through the same volatile field.
- Atomic state needs to be updated through atomic operations.
- Queues, latches, and concurrent collections need to be used according to their synchronization contracts.
- New threads need to receive initialization data before `Thread.start()` or via a safe publication mechanism.

If the application has external state that changed while the image was stored, the copy in the heap may be stale. For example, a `databasePrimary = true` flag read before checkpoint does not prove that node is still primary after restore. Query or re-validate external state.

Similarly, a `volatile boolean connected` in the heap may still be `true` after restore even though the socket was lost. Visibility only guarantees threads see the value under the JMM; it does not confirm external resources are alive. After restore, update connection state based on actual check results.

## 11. Common Concurrency Mistakes

**Using `volatile` for incrementing a counter.** Visibility does not make `count++` atomic. Use `AtomicInteger` or a lock.

**Reading the predicate outside a lock before calling `wait()`.** State can change between checking and starting to wait, leading to missed notifications. Check and wait under the same monitor.

**Using `if` instead of `while` around `wait()`/`await()`.** Spurious wakeups may occur or the predicate may have changed. Always recheck the condition in a loop.

**Calling `notify()` without understanding which thread groups are waiting.** It can wake the wrong thread. Use separate conditions or `notifyAll()` when all waiters must be woken.

**Forgetting `unlock()` in `finally`.** An exception can leave other threads waiting forever. Always put `unlock()` in `finally`.

**Swallowing `InterruptedException`.** The thread no longer responds to stop signals. Propagate the exception or restore the interrupt flag.

**Holding a lock while invoking slow I/O or callbacks.** Other threads cannot make progress and cascading deadlocks easily occur. Shrink critical sections.

**Acquiring multiple locks in different orders.** This can cause deadlocks. Enforce a single global order.

**Checkpointing while a worker is midway through a business update.** Memory state may be saved at a business-inconsistent point. Drain tasks to a safe boundary.

**Using sleep instead of coordination.** Sleeping only delays a thread, does not prove conditions are met, and establishes no happens-before. Use conditions, latches, joins, or queues.

**Treating a `connected` flag after restore as proof the socket is alive.** State in the heap may be stale. Verify external dependencies before publishing readiness.

## 12. Guide to Choosing Synchronization Primitives

| Need | Typically suitable mechanism |
|---|---|
| Protecting multiple fields that must remain consistent together | `synchronized` or `ReentrantLock` |
| Publishing a simple status flag | `volatile` |
| Atomically incrementing/changing a single value | `AtomicInteger`, `AtomicLong`, `AtomicReference` |
| Waiting for a condition tied to a lock | `Condition` or `Object.wait()` |
| Waiting for a group of tasks to complete once | `CountDownLatch` |
| Reusable multi-phase synchronization | `Phaser` or `CyclicBarrier` depending on pattern |
| Limiting the number of concurrent tasks | `Semaphore` |
| Passing work between producers and consumers | `BlockingQueue` |
| Managing workers and task lifecycles | `ExecutorService` |
| Waiting for a thread to terminate | `Thread.join()` |

Choose the highest-level abstraction that meets the requirement. `BlockingQueue` is usually easier to use and less error-prone than hand-writing a queue with `wait/notify`; `ExecutorService` is usually better than manually creating and managing many threads.

## 13. Process for Applying to a CRaC Application

You can implement it following these steps:

1. **Inventory shared data.** Identify objects, fields, collections, and resources accessed by multiple threads.
2. **Identify invariants.** Specify which fields must change together and which conditions workers must wait on.
3. **Select synchronization mechanisms.** Use monitors/locks for invariants, volatile for single flags, atomics for single operations, and concurrent utilities for task coordination.
4. **Bound critical sections.** Do not hold locks while calling network, database, or potentially blocking callbacks.
5. **Design worker shutdown.** Stop new work sources, drain running tasks, and wait using timed primitives.
6. **Integrate `beforeCheckpoint`.** Close dependencies only after workers have stopped and shared state reaches a safe boundary.
7. **Integrate `afterRestore`.** Restore dependencies, verify external state, and only then resume workers.
8. **Test failures and timeouts.** Test slow workers, interrupted workers, unavailable dependencies, and failed callbacks.
9. **Monitor thread dumps and metrics.** Record drain time, active task count, lock contention, and time from restore to readiness.

## 14. Self-Check of Understanding

1. **Why is `count++` unsafe when shared by multiple threads?** Because it is a read–modify–write sequence; threads can overwrite each other's results.
2. **What does `volatile` guarantee and what does it not guarantee?** It provides visibility and ordering under the JMM for accessing the volatile variable, yet does not automatically make a compound operation like `count++` atomic.
3. **Why must `wait()` be inside a `while` loop?** Because spurious wakeups can occur or the predicate may have changed before the thread reacquires the monitor.
4. **Does `wait()` release the monitor?** Yes. It releases the monitor while waiting and reacquires the monitor before returning.
5. **Why does `unlock()` need to be in `finally`?** To ensure the lock is released even if code inside the critical section throws an exception.
6. **How do you prevent deadlock when two locks are needed?** Define and follow the same lock acquisition order across all threads.
7. **Why not use `Thread.sleep()` to wait for workers to finish before checkpoint?** Sleeping does not prove conditions have been met, establishes no synchronization relationship, and can wake up too early or too late.
8. **After restore, does a `connected` flag in the heap prove the database is still connected?** No. You must recheck external resources and update state based on the actual result.

## Conclusion

Locks, condition waiting, and visibility are the foundation for multiple threads to share state safely. `synchronized` and `ReentrantLock` guard invariants; `wait/notify` and `Condition` coordinate threads by predicates; `volatile` publishes simple state; atomic classes and concurrent utilities support common operations without manual low-level lock management.

In the CRaC cycle, use these primitives to bring workers to a safe boundary before checkpoint and restart them after dependencies are restored. Stop accepting new work, drain tasks with timed mechanisms, avoid holding locks during I/O, and re-validate external state after restore. As a result, the snapshot reflects consistent application state and threads can continue coordinating cleanly when the process is restored.