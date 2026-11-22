# Avoiding Busy Waiting with Blocking Primitives in Java

## 1. Lesson Objectives

After this lesson, you will be able to:

- Explain **busy waiting**, **spinning**, **blocking wait**, and why continuous polling loops typically waste CPU, cause contention, and can suffer from visibility bugs.
- Choose the right Java tool for the condition being waited on: **CountDownLatch**, **BlockingQueue**, **Semaphore**, **Future.get()**, **Condition.await()**, and thread-termination waiting methods.
- Distinguish between **one-shot signaling**, **producer–consumer data handoff**, **resource limiting**, **waiting for a result**, and **waiting for a mutable predicate**.
- Write Java 17+ programs using blocking primitives while properly handling **interruption**, **timeout**, **cleanup**, and **happens-before**.
- Identify **blocking while holding a lock**, deadlocks, lost notifications, wrong queue or timeout choices, and replacing a busy loop with sleep without a synchronization protocol.
- Recognize the limits of blocking: it does not promise an exact wake-up time, does not automatically mean business-level success, and does not automatically handle results already committed outside the JVM.

This lesson belongs to the topic **Thread Coordination** in **general Java concurrency**. Spring-specific orchestration mechanisms belong to another chapter.

## 2. What Is Busy Waiting?

**Busy waiting** is a pattern where a thread repeatedly checks a condition while having virtually no useful work to do, typically via a loop:

~~~java
// Illustrative buggy code: ready is a plain field shared between threads.
while (!ready) {
    // Continuously checking, consuming CPU.
}
process();
~~~

The snippet above is not a standalone program: **ready** and **process()** are hypothetical components.

Notable problems:

1. **CPU waste**: the thread is repeatedly scheduled to run just to re-read the same condition.
2. **Cache/memory bus contention**: multiple threads continuously reading a shared flag can create unnecessary pressure.
3. **Lack of visibility guarantees** if `ready` is a plain field: without a happens-before relationship, the waiting thread may never see updates from another thread; the compiler/JIT is also allowed to optimize based on the JMM.
4. **Hard-to-control stopping time**: if the producer fails and never signals, the loop has no timeout or clear cancellation policy.
5. **Increased load when multiple threads wait**: short-interval polling can keep the system busy without making progress.

A **while (!ready) {}** loop should only exist in specialized spinning algorithms that are explicitly designed to address memory ordering, CPU cost, fairness, and fallback strategies. It is not the default for waiting on events in Java applications.

### Is Switching to `volatile` Enough?

~~~java
// Illustrative code: volatile handles visibility of the flag, not CPU waste.
private volatile boolean ready;

// Waiting thread:
while (!ready) {
    Thread.onSpinWait();
}
~~~

**Thread.onSpinWait()** is only a *hint* that the thread is in a spin loop; the JVM/CPU may use the hint to optimize execution. It **does not block**, **does not detect signals on its own**, and **does not guarantee wake-up timing or forward progress**. `volatile` makes updates visible, but the loop can still burn CPU.

## 3. How Does a Blocking Primitive Differ from a Busy Loop?

A **blocking primitive** lets a thread **wait on an API-managed condition/event**, instead of repeatedly reading shared state itself. The API contract defines when the wait is released, which memory relationships are established, and how timeouts/interrupts behave.

Example of waiting for a single signal:

~~~java
// Illustrative code inside a method declaring throws InterruptedException:
CountDownLatch done = new CountDownLatch(1);

// After completing the relevant step, the worker calls done.countDown().
// Waiting thread:
done.await();
~~~

Here **CountDownLatch** is a type in `java.util.concurrent` (requires import). This snippet has no `main()` and does not run on its own; a complete example is in Section 6.

How to understand the contract: when the count reaches 0, threads calling `await` are allowed to proceed. The runtime does not have to execute a hand-written Java loop `while (latch.getCount() > 0)` continuously. A primitive's internal implementation may have short optimization steps, but from a usage perspective this is a **blocking wait**, not application-level busy-waiting.

### Diagram

~~~text
Busy waiting:
  reader -> check -> check -> check -> check -> ... -> check -> continue
                  CPU may stay active almost continuously

Blocking:
  waiter -> await() -> [waiting for signal / condition / result]
  producer ----------------------> signal / put / complete
  waiter -> allowed to proceed -> execute next step
~~~

**Blocking does not mean "guaranteed 0 CPU while waiting" or "instantaneous wake-up."** Details depend on the JVM, OS, scheduler, and API. The key point is that the application does not maintain a continuous polling loop itself.

## 4. Choosing the Right Primitive for the Event Being Waited On

| Need | Suitable Java Primitive | Key Point |
| --- | --- | --- |
| Wait for N tasks to report completion | **CountDownLatch** | Counts down to 0; does not reset |
| Threads meet at a multi-phase barrier | **CyclicBarrier** or **Phaser** | Per-phase protocol, handles broken barrier |
| Producer sends elements to consumer | **BlockingQueue** | **put/take** both transfers data and coordinates |
| Limit concurrent operations | **Semaphore** | Manages permits; acquire/release per business rules |
| Wait for an asynchronous computation result | **Future.get()** | Yields value, error, or cancellation state |
| Wait for a specific thread to terminate | **Thread.join()** | Thread termination does not equal business success |
| Wait for a predicate under an explicit lock | **Condition.await()/signalAll()** | Always check predicate in a `while` loop |
| Wait for a predicate under an intrinsic monitor | **Object.wait()/notifyAll()** | Must own the right monitor, always use `while` |
| Wait on a low-level park/unpark permit | **LockSupport.park()/unpark()** | Low-level; must design predicate and exact unpark yourself |

Do not replace **BlockingQueue** with **CountDownLatch** just because both have a waiting method: a latch carries no elements. Do not replace **Semaphore** with a boolean if the problem actually requires at most K concurrent entrants.

## 5. Comparison Example: Polling, Sleep, and Blocking

### 5.1. Busy Loop

~~~java
// Anti-pattern: plain flag with no visibility protocol.
while (!finished) {
    // spin
}
~~~

No guarantee of seeing `finished = true`; consumes CPU.

### 5.2. Polling with Sleep

~~~java
// Illustrative: finished needs a visibility mechanism such as volatile or atomic.
while (!finished) {
    Thread.sleep(50);
}
~~~

This pattern **no longer burns CPU continuously** while sleeping, but it is still **periodic polling**:

- Introduces **extra latency** between when `finished` is set to `true` and the next check.
- Incurs repeated wake-up overhead just to check.
- **Thread.sleep() does not create a happens-before relationship** for `finished`; an appropriate `volatile`/atomic/lock is still required.
- Has no channel to report errors or detect that the producer died without updating the flag.
- Can throw `InterruptedException`, which must be handled properly.

If the event source API supports **signaling or blocking wait**, use it. Polling is acceptable when integrating with an API that does not support signaling, with a deliberately chosen poll interval and deadline.

### 5.3. Waiting for a Signal

~~~java
// Illustrative: done is a safely shared CountDownLatch.
done.await();
~~~

The thread sleeps while waiting for the event instead of polling in a loop. The completion protocol is managed by the primitive; you must ensure the producer **always calls `countDown()` at the right time**, including on error paths if the contract requires waiters not to hang.

## 6. Example 1: CountDownLatch Instead of a Spin Loop

A program waits for a worker to report that a result is ready. We explicitly use a latch as the publication milestone for the result and wait via `await()`.

File **LatchInsteadOfSpinDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class LatchInsteadOfSpinDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);
        AtomicInteger result = new AtomicInteger();

        Thread worker = new Thread(() -> {
            try {
                result.set(6 * 7);
            } finally {
                ready.countDown();
            }
        }, "worker");

        worker.start();
        ready.await();
        System.out.println("result = " + result.get());
        worker.join();
    }
}
~~~

~~~bash
javac -encoding UTF-8 LatchInsteadOfSpinDemo.java
java LatchInsteadOfSpinDemo
~~~

Stdout:

~~~text
result = 42
~~~

**Explanation:**

1. The worker computes the value and stores it in `AtomicInteger` before calling `countDown`.
2. `main`'s **CountDownLatch.await()** waits until the count reaches 0; there is no hand-written polling loop.
3. With `CountDownLatch`, actions in the producer before `countDown` **happen-before** actions in the consumer after `await` returns. `AtomicInteger` also provides its own atomic variable memory contract.
4. **join()** at the end reclaims/waits for the worker thread to finish; the latch itself is already enough to observe the result published **before `countDown`**, though it does not necessarily guarantee that all code after `countDown` has finished.
5. If the worker can fail, a real application needs to store **either the result or an exception** and define whether the latch signals "phase finished" or "succeeded." The latch reaching 0 **does not by itself mean business success**.

In this example, no unchecked exception occurs in the arithmetic, so the output is deterministic.

### A Latch Can Have Multiple Waiters

With **new CountDownLatch(N)**, N calls to `countDown` decrement the counter to 0. N can be the number of workers or phases to satisfy. **Calling `countDown` when the count is already 0 does not make it negative**. Once a latch reaches 0, subsequent `await` calls pass through immediately—it **does not reset**; multi-phase lifecycles require a different primitive.

## 7. Timeout: Do Not Wait Forever When a Condition Has a Deadline

Most synchronization APIs provide timed wait overloads:

- **CountDownLatch.await(long, TimeUnit)**: returns a `boolean`—`true` if the count reached 0 before the timeout elapsed, `false` on timeout.
- **Future.get(long, TimeUnit)**: returns the result or throws `TimeoutException`; the computation is **not automatically cancelled** just because the caller timed out.
- **BlockingQueue.poll(long, TimeUnit)**: returns the element, or `null` if the timeout expired with no element available.
- **Semaphore.tryAcquire(long, TimeUnit)**: returns `true` if a permit was acquired, `false` on timeout.
- **Condition.await(long, TimeUnit)**: returns a value reflecting remaining wait time; the predicate must still be rechecked.
- **Thread.join(long)**: returns when the target thread terminates or the timeout expires; after `join(timeout)`, you must not assume the thread is dead.

### Example 2: Timed `await` with Predictable Outcome

File **LatchTimeoutDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class LatchTimeoutDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch neverSignaled = new CountDownLatch(1);

        boolean completed =
                neverSignaled.await(5, TimeUnit.MILLISECONDS);

        System.out.println("completed = " + completed);
        System.out.println("remaining = " + neverSignaled.getCount());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LatchTimeoutDemo.java
java LatchTimeoutDemo
~~~

Stdout:

~~~text
completed = false
remaining = 1
~~~

No thread called `countDown()`, so the timed `await` returns `false` and the count remains 1. A timeout gives the caller a **controlled exit path**, but the latch is still incomplete. For real tasks, you must decide whether to alert, retry, keep waiting, request cancellation, or release resources according to your policy.

**Do not treat very short timeouts as latency guarantees**: the JVM, scheduler, and timers have granularity/jitter; a timeout is not a promise of millisecond-exact execution.

## 8. BlockingQueue: Wait for Elements Instead of Waiting on a Ready Flag

Producer–consumer problems naturally require **transferring data**, not just signaling. **BlockingQueue<E>** provides:

- **put(e)**: may block when the queue is full (for bounded queues).
- **take()**: blocks when the queue is empty, returning an element when available.
- **offer(e)**: tries to insert immediately, returning `false` if unable to.
- **offer(e, timeout, unit)**: waits up to a bounded time to insert.
- **poll()**: retrieves immediately or returns `null` if empty.
- **poll(timeout, unit)**: waits up to a bounded time to retrieve.

**ArrayBlockingQueue** has a fixed capacity; **LinkedBlockingQueue** can be configured with a capacity, though its no-arg constructor uses a very large bound (`Integer.MAX_VALUE`). If you want real **backpressure**, specify an appropriate capacity.

**BlockingQueue does not allow `null` elements**, because `null` is used as a sentinel meaning "no element received." If you need an end-of-stream signal, use a special message or another explicit protocol.

### Example 3: Wait with `take()`, Do Not Spin on `isEmpty()`

File **BlockingQueueDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class BlockingQueueDemo {
    private static final int END = -1;

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Integer> queue =
                new ArrayBlockingQueue<>(2);

        Thread producer = new Thread(() -> {
            try {
                queue.put(1);
                queue.put(2);
                queue.put(3);
                queue.put(END);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        producer.start();

        int sum = 0;
        int count = 0;

        while (true) {
            int value = queue.take();
            if (value == END) {
                break;
            }
            sum += value;
            count++;
        }

        producer.join();
        System.out.println("processed = " + count);
        System.out.println("sum = " + sum);
    }
}
~~~

~~~bash
javac -encoding UTF-8 BlockingQueueDemo.java
java BlockingQueueDemo
~~~

Stdout:

~~~text
processed = 3
sum = 6
~~~

**Walkthrough:**

1. The producer puts three numbers into the FIFO queue, then puts **END** to signal no more data.
2. The consumer is `main`. **take()** waits when the queue is empty and resumes when the producer puts an element; it does not spin on **isEmpty()**.
3. Capacity 2 bounds the number of unconsumed items; **put()** can block, creating backpressure instead of an unbounded queue.
4. After `END`, `main` joins the producer and prints the totals, so stdout is deterministic.
5. This example uses one producer, one consumer, and a sentinel that **does not collide with valid data values**. With multiple producers/consumers, the shutdown protocol must be designed explicitly (e.g., an appropriate number of sentinels or closing the queue under a protocol), rather than arbitrarily putting one `END` and assuming all consumers will stop.

**Memory visibility:** Actions in a thread prior to **placing an object into a BlockingQueue** happen-before actions in another thread **subsequent to retrieving that object**. However, that **does not automatically make a mutable object immutable**: if the producer keeps mutating an object after `put`, races can occur when the consumer reads the same object.

### Anti-pattern: `isEmpty()` + `poll()` / `sleep()`

~~~java
// Illustrative design bug; queue is an already-created shared queue.
while (queue.isEmpty()) {
    Thread.sleep(10);
}
var item = queue.poll();
~~~

The queue can change right after `isEmpty()`; `item` may be `null` if another consumer took the element first. To wait for an element, use **take()**. If you cannot block indefinitely, use **poll(timeout, unit)** and check for `null`.

## 9. Semaphore: Waiting for Resource Access Permits

**Semaphore** manages a set of **permits**. Only threads that acquire the required permits may enter the concurrency-limited section.

- **acquire()**: waits until a permit is available; can throw `InterruptedException`.
- **tryAcquire()**: tries immediately, returning a `boolean`.
- **tryAcquire(timeout, unit)**: waits up to a bounded time.
- **release()**: returns a permit per the application protocol.

**Semaphore does not have thread ownership like `ReentrantLock`**: the API allows a different thread to release a permit, and extra releases can increase the permit count beyond the intended limit. Therefore, the application itself must ensure **every successful `acquire` has a matching `release`**, unless intentionally implementing a permit-handoff protocol.

### Example 4: Limiting Concurrency to at Most Two Tasks

File **SemaphoreLimitDemo.java**:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class SemaphoreLimitDemo {
    public static void main(String[] args) throws InterruptedException {
        Semaphore slots = new Semaphore(2);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximum = new AtomicInteger();
        AtomicInteger completed = new AtomicInteger();

        Runnable work = () -> {
            boolean acquired = false;
            try {
                slots.acquire();
                acquired = true;

                int now = active.incrementAndGet();
                maximum.accumulateAndGet(now, Math::max);

                try {
                    int value = 6 * 7; // Example of doing useful work.
                    if (value == 42) {
                        completed.incrementAndGet();
                    }
                } finally {
                    active.decrementAndGet();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                if (acquired) {
                    slots.release();
                }
            }
        };

        Thread[] threads = new Thread[4];
        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(work, "worker-" + i);
            threads[i].start();
        }

        for (Thread worker : threads) {
            worker.join();
        }

        System.out.println("completed = " + completed.get());
        System.out.println("capacity respected = " + (maximum.get() <= 2));
        System.out.println("permits = " + slots.availablePermits());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SemaphoreLimitDemo.java
java SemaphoreLimitDemo
~~~

Stdout:

~~~text
completed = 4
capacity respected = true
permits = 2
~~~

**Why is this correct?**

- Each thread must acquire a permit before incrementing `active`.
- At most two threads can hold permits concurrently; **maximum <= 2** is an invariant, without assuming `maximum` must equal 2 on every schedule.
- **active** is decremented in `finally` after the work; **slots.release()** runs only if the thread successfully acquired a permit.
- After joining all four threads, all permits have been returned and 4 tasks were processed.

**Watch out:** If you catch `InterruptedException` without having acquired a permit and still call `release()`, the semaphore can end up with **3 permits** instead of 2 and break the concurrency limit. Proper cleanup is a mandatory part of the protocol.

**Fairness:** `new Semaphore(permits, true)` applies a fairness policy for acquisitions per the API contract, but it does not guarantee strictly fair CPU scheduling for every thread; **immediate `tryAcquire()`** calls can barge ahead according to their own rules.

## 10. `Future.get()`: Wait for Results Instead of Polling `isDone`

When an application submits a computation to an **ExecutorService**, **Future<T>** represents its completion and result.

Anti-pattern:

~~~java
// Illustrative: future is a Future<Integer>.
while (!future.isDone()) {
    // Busy waiting or calling sleep periodically.
}
int answer = future.get();
~~~

Instead:

~~~java
// Illustrative inside a method handling checked exceptions.
int answer = future.get(); // Blocks until completion, failure, or cancellation.
~~~

**Future.get()** can:

- Return value `T` when the computation completes normally.
- Throw **ExecutionException** when the task throws an exception.
- Throw **CancellationException** when the `Future` was cancelled.
- Throw **InterruptedException** if the waiting thread is interrupted.
- With the timed overload, throw **TimeoutException** if the caller waits past the deadline; **the task may still continue running**.

**`isDone() == true` does not mean success**; it is also `true` on failure or cancellation. If you need business-level status, you must interpret the result/exception according to your application protocol.

### Example 5: Waiting for a `Future` to Return a Result

File **FutureBlockingDemo.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class FutureBlockingDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> future = pool.submit(() -> 21 * 2);
            int result = future.get();

            System.out.println("result = " + result);
            System.out.println("done = " + future.isDone());
            System.out.println("cancelled = " + future.isCancelled());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 FutureBlockingDemo.java
java FutureBlockingDemo
~~~

Stdout:

~~~text
result = 42
done = true
cancelled = false
~~~

The caller **does not poll** and instead waits for the result via `get()`. The `ExecutorService` must be shut down so worker threads are not kept alive unintentionally. **Future.get()** returns a result or reports an error; this is a computation-level contract, not an external business transaction boundary.

**Do not hold a monitor/`ReentrantLock` that the worker needs and then call `get()`**: the caller holds the lock and waits for the worker, while the worker waits for the caller's lock → potential deadlock.

## 11. `Condition`: Blocking When Waiting on a Predicate That Can Change Repeatedly

With **ReentrantLock**, the **Condition** API is suitable when a thread must wait on **a condition over shared state** and another thread updates that condition. Choose `Condition` when you need multi-step state logic that a queue or latch cannot express directly.

Rules:

1. Create a condition via **lock.newCondition()**.
2. The caller must hold **the associated lock** when calling `await()`, `signal()`, or `signalAll()`.
3. Protect the predicate under the same lock; typically use **while (!predicate) condition.await()**.
4. **await() releases the associated lock while waiting**, then reacquires it before returning.
5. **Spurious wakeups** can occur; never use a single `if` assuming the condition is already true.
6. Signaling does not mean the waiting thread runs immediately: it still must reacquire the lock.

### Example 6: `await` While Condition Is False, `signalAll` When Ready

File **ConditionBlockingDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class ConditionBlockingDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        Condition readyCondition = lock.newCondition();
        boolean[] ready = {false};
        int[] result = {0};
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            lock.lock();
            try {
                started.countDown();
                while (!ready[0]) {
                    try {
                        readyCondition.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                result[0] = 42;
            } finally {
                lock.unlock();
            }
        }, "condition-worker");

        worker.start();
        started.await();

        lock.lock();
        try {
            ready[0] = true;
            readyCondition.signalAll();
        } finally {
            lock.unlock();
        }

        worker.join();

        lock.lock();
        try {
            System.out.println("ready = " + ready[0]);
            System.out.println("result = " + result[0]);
        } finally {
            lock.unlock();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConditionBlockingDemo.java
java ConditionBlockingDemo
~~~

Stdout:

~~~text
ready = true
result = 42
~~~

**Explanation:**

- The worker waits on the **predicate `ready[0]`**, instead of polling when not ready.
- **await()** releases the associated lock, allowing `main` to update `ready` and call `signalAll`.
- `main` cannot "miss" the condition just because `signal` happened before `await`: it must hold the same lock to modify `ready`, and the worker always checks the predicate in a `while` loop.
- After the signal, the worker reacquires the lock, checks `ready`, writes `result`, and releases the lock.
- `worker.join()` waits for the worker to finish; `main` also reads under the same lock, so the final output is deterministic.

**Do not use a `Condition` as a message queue without storing a predicate.** Calling `signal` when no waiter is present does not store a "future signal"; the predicate is the source of truth. If you need per-message delivery, `BlockingQueue` is usually a better fit.

## 12. `Object.wait()/notifyAll()`: Blocking with Intrinsic Monitors

Alongside `Condition`, Java provides **Object.wait()**, **notify()**, and **notifyAll()**:

~~~java
// Illustrative with lock as an Object monitor and ready as a shared field.
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    consume();
}
~~~

Thread updating the condition:

~~~java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
~~~

These two snippets are not a standalone program: `lock`, `ready`, `consume()`, and `InterruptedException` handling must be declared.

**Differences from `sleep()`:**

- **Object.wait()** on the exact object whose monitor the thread holds **releases that object's monitor while waiting**, then reacquires it before continuing.
- **Thread.sleep()** does not release any held monitors.
- **notify/notifyAll does not release the monitor immediately**; waiters must wait for the notifier to exit the `synchronized` block and reacquire the monitor themselves.
- Waits can experience spurious wakeups; **while** must recheck the condition.
- Calling `wait`/`notify` without holding the right monitor throws **IllegalMonitorStateException**.

If a thread holds multiple monitors, `wait()` only releases the monitor **on which `wait()` was called**, not any other monitors. Thus, deadlock is still possible if waiting while holding another lock needed by the producer.

## 13. Interrupts: Waiting Can Be Cancelled by Contract

Common blocking calls such as **CountDownLatch.await()**, **BlockingQueue.take()/put()**, **Semaphore.acquire()**, **Condition.await()**, **Thread.join()**, and **Future.get()** support **InterruptedException**.

When a waiting thread is interrupted, the call may throw `InterruptedException`; typically the interrupt flag is cleared when the exception is thrown. Code must follow a cooperative policy:

- If **it cannot handle cancellation at the current layer**, typically **restore the flag** via `Thread.currentThread().interrupt()` and exit/return up the call stack per contract.
- If the method signature allows, **propagate `InterruptedException`** to the caller.
- Do not swallow the interrupt and **keep waiting indefinitely** when cancellation requests must be respected.
- For permits/locks, in `finally` **only release/unlock what was actually acquired**.

### Example 7: Interruption Releases a Thread Blocked in `await()`

File **InterruptibleAwaitDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptibleAwaitDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch neverReleased = new CountDownLatch(1);
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();
        AtomicBoolean restored = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            started.countDown();
            try {
                neverReleased.await();
            } catch (InterruptedException ex) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
                restored.set(Thread.currentThread().isInterrupted());
            }
        }, "await-worker");

        worker.start();
        started.await();
        worker.interrupt();
        worker.join();

        System.out.println("interrupted = " + interrupted.get());
        System.out.println("flag restored = " + restored.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterruptibleAwaitDemo.java
java InterruptibleAwaitDemo
~~~

Stdout:

~~~text
interrupted = true
flag restored = true
~~~

Whether the interrupt arrives before or after the worker actually enters `await()`, if the interrupt flag is set when `await` begins or while waiting, `await()` handles it by throwing `InterruptedException`. The worker restores the flag and exits; `main` joins it and prints the state recorded by the `AtomicBoolean`s.

**An interrupt is not a forced thread termination command.** If a worker ignores interrupts or is in a non-interruptible operation, it may continue running. Execution code must be designed cooperatively, and you should not assume external side effects roll back automatically.

## 14. Deadlines and Timeouts: Waiting Properly Across Multiple Steps

When performing multiple waiting steps within **one overall deadline**, do not give the full timeout to each step:

~~~text
Overall task deadline: 1000 ms
Step A waits 1000 ms
Step B also waits 1000 ms
=> Total time can exceed the original budget.
~~~

Instead, compute the **remaining time** from a monotonic clock (**System.nanoTime()**) for each wait step. Avoid computing relative deadlines with **System.currentTimeMillis()**, because wall-clock time can be adjusted.

Illustrative pseudocode (not a standalone program):

~~~text
budget = 1 second
deadline = monotonicNow + budget

remaining = deadline - monotonicNow
if remaining <= 0 -> timeout
await(stepA, remaining)

remaining = deadline - monotonicNow
if remaining <= 0 -> timeout
await(stepB, remaining)
~~~

Note that deadline addition with very large budgets can overflow if not handled carefully; JDK timeout APIs have their own semantics. For real-time requirements, define SLAs, use deadlines/timeouts deliberately, and measure actual latency—do not treat `await(timeout)` as a precision scheduler.

If **Future.get(timeout)** throws `TimeoutException`, it means **the caller waited too long**, not that the worker has stopped. If policy requires cancellation, the caller can invoke **future.cancel(true)** and the worker must support interruption; side effects already completed before that are not automatically undone.

## 15. Avoiding Deadlocks When Using Blocking Primitives

Blocking primitives reduce busy waiting, but **they do not automatically guarantee deadlock freedom**.

### Holding a Lock While Waiting on a Worker That Needs That Lock

~~~text
Main holds lock L
  -> main calls Future.get() or Thread.join() waiting on worker

Worker tries synchronized(L) or lock.lock()
  -> worker waits for main to release L

=> Wait cycle: main waits for worker, worker waits for main's L.
~~~

The fix is to define **wait ordering and lock scope**. If the work being waited on does not require holding the lock, you can release the lock before waiting; upon reacquiring the lock, you must **recheck the condition**, because state may have changed. Do not drop a lock casually if doing so breaks invariants.

### Pool Worker Waiting on a Task in the Same Pool

A pool has only one worker executing task A. If A submits task B to **the same single-thread executor** and calls **Future.get()** waiting for B, B cannot run because the sole worker is occupied by A. That is a **thread-starvation deadlock** even without two `ReentrantLock`s.

Alternative design: do not block waiting on work that requires the same single resource; use composition/chaining or provision independent workers as needed. **Adding a timeout only provides an escape hatch**, not proof that the architecture is sound.

### Full Queue and Wait Cycles

A producer holds a resource and calls **put()** on a full queue; the consumer tries to acquire that resource before calling **take()**. The producer waits for queue space, the consumer waits for the resource → potential deadlock. Therefore, analyze not only lock ordering, but the entire **resource dependency graph**, including permits, queue capacity, and task results.

## 16. Spinning Is Not Always Pointless

In very short, measured cases—such as lock-free or low-latency algorithms—**bounded spinning** can avoid park/unpark overhead compared to blocking. However, you must:

- Use appropriate memory ordering mechanisms (**volatile**, atomics, `VarHandle` with the right access mode).
- Bound the number of iterations or time, with a fallback to blocking if waiting persists.
- Measure CPU usage, tail latency, fairness, and impact on other threads.
- Be careful on single-core or low-core-count machines: a spinner can starve the CPU that the producer needs to finish.
- Do not treat **Thread.onSpinWait()** as a JMM guarantee for visibility, ordering, or wake-up.

For most data, signal, completion, or permit waiting protocols in typical applications, **a semantically appropriate blocking primitive is easier to maintain than a custom spin loop**.

## 17. Guide to Choosing a Primitive by Semantics

| If you are asking... | Consider | Do not do |
| --- | --- | --- |
| "When have the workers finished a step?" | `CountDownLatch` or `Future` | Poll a plain flag indefinitely |
| "Is there an element to process yet?" | `BlockingQueue.take()`/`poll(timeout)` | `isEmpty` then `sleep` |
| "Is there a resource slot available?" | `Semaphore.acquire()`/`tryAcquire(timeout)` | Plain counter and spin |
| "What value or error did the computation return?" | `Future.get()` / composition | `while (!isDone())` then `get` |
| "Is the condition under the lock satisfied?" | `Condition.await()` in a `while` loop | `await` without lock or using `if` |
| "Has a specific thread terminated?" | `Thread.join()` | `while (thread.isAlive())` without sleep/cancel |
| "I just need a low-level signal?" | High-level primitives; `LockSupport` only when truly needed | `park` without a state predicate |
| "I need to optimize ultra-short waits?" | Measured bounded spin + fallback | Unbounded spin hoping on the scheduler |

**Selection rule:** identify **what you want to receive** (signal, element, permit, result, predicate), **when it is valid**, **who provides it**, and **error/timeout/interrupt paths**. Then choose the primitive whose contract matches most closely.

## 18. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Spin on a plain field | Data race/visibility bug and CPU waste | Use a blocking primitive or a proven `volatile`/atomic protocol |
| Spin with `volatile` thinking it is optimal | Still burns CPU | Use `await`/`take`/`get` when appropriate |
| `sleep` thinking it establishes happens-before | May not see valid data | Use a primitive with explicit memory consistency |
| Use `CountDownLatch` to pass objects like a queue | Latch only carries a count event | Use `BlockingQueue` or `Future` |
| Omit `countDown` on error paths | Waiters can hang | Complete the completion contract and use `finally` |
| Call `await(timeout)` and treat `false` as success | Condition is not met | Handle the timeout branch separately |
| Assume `Future.isDone` means success | `Done` includes exception/cancellation | Check `Future.get` and business policy |
| Call timed `Future.get` and assume task stopped | Task may still be running | Cancel cooperatively per policy |
| `BlockingQueue` without an explicit capacity | Can grow memory unboundedly | Choose a bounded queue and backpressure |
| `put` into a queue while holding a lock the consumer needs | Deadlock or contention | Analyze dependencies, change coordination structure |
| Inflate `Semaphore` permits via extra `release` | Breaks concurrency limit | Release strictly after a successful `acquire` |
| Call `Condition.signal` outside the lock | `IllegalMonitorStateException` | Hold the associated lock |
| Use `if` around `Condition.await` | Spurious wakeups, changed predicate | Recheck in a `while` loop |
| Swallow `InterruptedException` | Cancellation path has no effect | Propagate or restore flag and stop per policy |
| Wait on a `Future` inside a single-worker task on the same pool | Thread-starvation deadlock | Do not block waiting on a task sharing the same worker |
| Believe `WAITING` thread means "holds no locks" | May still hold other locks | Audit all held locks |
| Believe blocking is always instant or fair | Scheduler/timer/contention vary | Measure actual latency, deadlines, and fairness |

## 19. Self-Check Exercises

**1. Why can `while (!flag) {}` fail even when the worker is guaranteed to set `flag = true`?**  
Because a plain `flag` can suffer from a data race / lack of happens-before; the reader is not guaranteed to see the update. Even if `flag` is `volatile`, the spin loop can still waste CPU.

**2. When you only need to know that N workers have finished a phase, what should you use?**  
`CountDownLatch(N)`, where each worker calls `countDown` per contract and the caller calls `await`. If you need per-worker errors/results, add an appropriate result-collection mechanism or use `Future`.

**3. When you need to receive individual items from a producer, is `CountDownLatch` enough?**  
No. A latch carries no data; `BlockingQueue` provides `put`/`take` and memory consistency for handed-off elements.

**4. How does `Semaphore` differ from `ReentrantLock` regarding lock ownership?**  
`ReentrantLock` requires the owning thread to unlock the lock it holds. `Semaphore` manages permits and does not require the releasing thread to be the acquiring thread; the application must preserve the permit count itself.

**5. Can you place `signalAll()` outside the lock to avoid contention?**  
Not for a `Condition` created by `ReentrantLock`: `signalAll` requires the thread to hold the associated lock. Update the predicate and signal under the same lock.

**6. Does `Future.get(timeout)` throwing `TimeoutException` mean the job was cancelled?**  
No. It only means the caller timed out waiting; the task may still be running.

**7. If a worker is interrupted during `CountDownLatch.await()`, how should it be handled?**  
Per contract: you can propagate `InterruptedException`; if caught without handling at the current layer, restore the interrupt flag and exit cooperatively, while cleaning up any acquired resources.

**8. Why is `Thread.sleep(50)` in a polling loop not the best coordination solution?**  
It introduces periodic wake-up latency/overhead and does not by itself provide memory visibility. Blocking primitives let you wait directly on the event.

**9. Does a `Condition.await()` release all locks held by the thread?**  
No, it only releases the lock associated with that `Condition` while awaiting. If the thread holds other locks, deadlock can still occur.

**10. Does a `BlockingQueue` with capacity 2 guarantee the producer holds at most two objects in the entire program?**  
No. Capacity only limits the number of elements **currently inside the queue**. Producers/consumers can hold other references outside the queue, and related side effects/memory are not automatically bounded by queue capacity.

## 20. Conclusion

**Avoiding busy waiting** is not simply adding `sleep` to a `while` loop; it is **shifting from repeatedly polling state to waiting on the right event using a protocol with synchronization guarantees**.

- Use **CountDownLatch** to wait for a one-time completion milestone.
- Use **BlockingQueue** to wait for and hand off elements.
- Use **Semaphore** to wait for bounded resource access permits.
- Use **Future.get()** to wait for computation results, including errors and cancellation.
- Use **Condition.await()** or **Object.wait()** with a predicate in a `while` loop when the condition is guarded by a lock/monitor.

With every primitive, you must clarify **timeout, interruption, resource cleanup, memory visibility, business state, and the dependency graph**. Blocking eliminates wasteful polling loops, but only a sound protocol ensures the program both makes progress and preserves its invariants.
