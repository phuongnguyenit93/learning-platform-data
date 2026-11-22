# Impact of Blocking I/O and Condition Waiting on Thread Lifecycle in Java

## Lesson Objectives

A `Thread` in Java is not necessarily computing whenever it is alive. It may be **waiting for data from I/O**, **waiting for a condition to be satisfied**, **waiting to acquire a monitor lock**, or **sleeping for a period of time**. These types of waiting produce different representations in `Thread.State`, affecting response time, resource utilization, and the ability to serve new tasks.

After this lesson, you will be able to:
- Distinguish **I/O blocking** from **condition waiting** and from **monitor contention**.
- Correctly read the six Java states `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, and `TERMINATED`; explain why a thread **waiting for I/O can still appear as `RUNNABLE`**.
- Understand why `Object.wait()`/`notifyAll()`, `Condition.await()`/`signalAll()`, and `BlockingQueue.take()` allow a thread to wait for work without spinning and consuming CPU.
- Recognize the impact of long waits on thread pools, queue length, throughput, and tail latency.
- Run Java 17+ examples to observe a thread waiting on a condition and a thread waiting for data on a stream; know the limitations of state snapshots via `getState()`.
- Choose appropriate timeouts, interruption, concurrency limits, and diagnostic tools for each type of waiting.

**Scope:** general Java/JVM thread and concurrency mechanisms. Spring-specific asynchronous mechanisms, annotations, or configurations belong to another chapter.

## 1. A live thread does not mean it is always executing on the CPU

Suppose a worker is processing a data read request:

~~~text
NEW
 |
 | start()
 v
RUNNABLE ----> calls read() with no data yet ----> waiting for I/O
   ^                                                 |
   |                        data arrives / I/O done  |
   +-------------------------------------------------+
   |
   +---- waits on predicate via wait() ---> WAITING or TIMED_WAITING
   |                                           |
   |          signal/notify/timeout            |
   +-------------------------------------------+
   |
   +---- tries to acquire held monitor -----> BLOCKED
   |                                           |
   |            monitor acquired               |
   +-------------------------------------------+
   |
   +---- run() finishes --------------------> TERMINATED
~~~

The diagram above describes **why a thread pauses its work and how it resumes**, without claiming that I/O waiting is a separate enum state. Java does not have `Thread.State.IO_BLOCKED`. Even while waiting on an operating system I/O operation, Java may still report the thread as `RUNNABLE`. There is no separate `RUNNING` enum state: `RUNNABLE` includes a thread that is eligible to run, currently running, or potentially waiting on an external resource outside the JVM depending on the situation.

**Two layers must be distinguished:**
1. **The JVM state** reported by `Thread.getState()` or a thread dump: a coarse snapshot for monitoring.
2. **The actual cause of waiting**: a socket read system call, `Object.wait()`, a `Lock`, waiting for data from a queue, waiting to be scheduled on CPU, etc. Identifying this cause usually requires combining stack traces, lock information, metrics, and logs.

A thread can change state many times within a single millisecond. `getState()` is only a snapshot at the moment of reading; use it to understand behavior, **not** to drive thread coordination logic.

## 2. The six Thread.State values to know

| `Thread.State` | Meaning in Java | Related examples |
| --- | --- | --- |
| `NEW` | `Thread` object created, `start()` not yet called | `new Thread(task)` |
| `RUNNABLE` | Thread is eligible to run or executing from the JVM's perspective; may be waiting for OS resources | CPU work, some forms of blocking socket/file I/O |
| `BLOCKED` | **Waiting for a monitor lock** to enter/re-enter `synchronized` | Thread A holds the monitor, B tries to enter `synchronized(monitor)` |
| `WAITING` | Waiting for another action with no time limit | `Object.wait()`, `Thread.join()`, `LockSupport.park()` |
| `TIMED_WAITING` | Waiting for at most a specified period of time | `Thread.sleep(500)`, `Object.wait(500)`, `Thread.join(500)`, `LockSupport.parkNanos(...)` |
| `TERMINATED` | `run()` has finished normally or due to an uncaught exception | After the worker terminates |

Important notes:

- The name **`BLOCKED` in the Java enum has a narrow meaning**: waiting for a `synchronized` *monitor*. "Blocking I/O" in programming terminology **does not automatically correspond to `Thread.State.BLOCKED`**.
- Waiting on `ReentrantLock.lock()` or `Condition.await()` may be implemented using parking and observed as `WAITING`/`TIMED_WAITING`; do not automatically categorize them as `BLOCKED` just because they are "waiting for a lock".
- Java states are JVM states, not a direct mirror of operating system runnable/sleeping states.
- A thread changes state due to execution conditions, not its name or ID. `notifyAll()` is only a signal; it does not mean the thread will run immediately.

## 3. Blocking I/O: waiting for data or a device

### 3.1. Where does blocking occur?

A **blocking** I/O call only returns after the operation has a result, reaches EOF, encounters an error, is closed/cancelled per the API contract, or hits a timeout if the API supports one. For example:

~~~java
int firstByte = inputStream.read();
~~~

If `InputStream` has no bytes available yet, `read()` may wait. Inside the read method, the calling thread cannot continue executing the code after `read()`. In other cases, the call may return immediately if data is already available, EOF has been reached, or the stream is already in an error state; **calling a blocking API does not mean it actually waits every time**.

Practical examples:
- Reading a TCP socket with traditional streams when data has not arrived yet.
- Waiting to receive results from a device or file system; the degree of blocking depends on the API, buffers, and operating system.
- Waiting on `accept()` of a traditional server socket when there are no new connections yet.
- Reading from a pipe that has no bytes from the writer side yet.

**Do not confuse elapsed time with CPU time.** A `read()` call lasting 700 ms may consume very little CPU for most of that time because the thread is waiting for data. However, it still occupies **an open unit of work**, potentially holding onto a socket, memory, stack, a slot in a thread pool, or quota of another resource.

### 3.2. Impact on lifecycle and performance

With a pool of **4 platform worker threads**, if all four are waiting on I/O for several seconds, a fifth task may wait in the queue even if the machine's CPU is idle. Common observation:

~~~text
All 4 workers are waiting on remote I/O
             |
             +--> CPU may still be low
             |
             +--> worker pool is completely busy
                        |
                        +--> new tasks queue up
                        +--> queue wait increases
                        +--> end-to-end latency increases
~~~

Increasing the number of workers **can** help run more I/O-waiting work concurrently, but only up to real limits: connection count, memory, file descriptors, downstream service throughput, and admitted load. If each request waits 2 seconds on a downstream service, spawning more threads does not make the downstream finish faster; it also risks increasing the backlog and overloading the dependency.

In practice, you should measure:
- Queue wait time and time from when a worker starts until completion.
- Number of tasks/workers waiting on I/O, active connections, and pending connections.
- Timeouts, retries, error counts, admitted requests, and successfully processed requests.
- p95/p99 latency; low CPU is **not** sufficient to conclude the system has spare capacity.

### 3.3. Why can getState() still be RUNNABLE?

For some classic blocking I/O operations, the JVM observes the thread in `RUNNABLE` because it is inside a native/OS call; the operating system itself may actually be waiting on network or disk. Other APIs/implementations may use internal monitors or synchronization primitives, causing you to see `WAITING` or `TIMED_WAITING`.

Therefore:

~~~java
Thread.State snapshot = readerThread.getState();
System.out.println(snapshot);
~~~

This line gives a **Java state snapshot**, which is not enough evidence to claim the reader is computing, has received data, or is blocked on a socket. To know more accurately, you need stack traces, I/O information, metrics, and before–after call measurements.

**Do not infer backward:** seeing `RUNNABLE` does not prove the CPU is busy; seeing `WAITING` does not prove the source of waiting is `Object.wait()` in your own code.

## 4. Condition waiting: waiting for a predicate to become true

Unlike waiting on I/O from an external data source, **condition waiting** occurs when a thread needs a coordinated state between threads, for example:

- Buffer is still empty → consumer waits for producer to add an element.
- Work is not yet marked complete → another thread waits for the completion signal.
- Not enough resources/permits → task waits for permission to proceed.
- A `ready` flag updated by another thread has not yet become `true`.

The key is the **condition predicate**, such as `ready == true` or `!queue.isEmpty()`. A `notify`/`signal` only indicates "the condition may have changed"; the awakened thread must still check the predicate. Never use a bare signal as the source of truth.

### 4.1. Busy-wait vs. blocking wait

A performance anti-pattern using a hot loop:

~~~java
while (!ready) {
    // Continuously checks the condition; can consume high CPU.
}
~~~

Such a loop also carries a **visibility** risk if `ready` is updated by another thread without a happens-before relationship (for instance via `volatile`, a lock, or an atomic). Adding `volatile` makes the value visible, but **does not** stop the hot loop from burning CPU. `Thread.yield()` is not a reliable coordination solution either.

The structured approach is to let the thread **sleep while waiting for a signal** using `wait()`, `Condition.await()`, or higher-level primitives such as `BlockingQueue.take()` or `CountDownLatch.await()`. These avoid burning CPU when there is no work and establish clear synchronization rules.

### 4.2. Object.wait() releases the object's own monitor

Standard pattern:

~~~java
final Object monitor = new Object();
boolean ready = false; // In real code: variable lives in a shared object guarded by monitor.

// Waiting thread (illustrative, not a standalone program):
synchronized (monitor) {
    while (!ready) {
        monitor.wait(); // Releases monitor; enters wait set.
    }
    // Upon returning here, the thread has reacquired monitor and ready == true.
}
~~~

For another thread to update `ready`, it must also enter `synchronized (monitor)` and call `monitor.notifyAll()` **inside that monitor**. `wait()`:
1. Requires the current thread to hold that exact monitor; otherwise it throws `IllegalMonitorStateException`.
2. Temporarily releases the monitor **of the object on which `wait()` is called** while waiting; it does not automatically release any other monitors the thread holds.
3. May return due to `notify`/`notifyAll`, interruption, or a **spurious wakeup**; `wait()` has no timeout by default.
4. Before returning normally or throwing `InterruptedException`, the thread must reacquire that monitor.

**Always check the condition with `while`, never `if`**: after waking up, the condition may still be false due to a spurious wakeup or another thread having consumed the resource first.

Calling `notifyAll()` **does not transfer monitor ownership immediately**. The signaling thread keeps the monitor until it exits the synchronized block. Awakened threads must compete to reacquire the monitor, and may briefly appear in `BLOCKED`.

### 4.3. Waiting with a timeout

APIs like `wait(long timeoutMillis)` or `Condition.await(long, TimeUnit)` allow setting a bound. For `Object.wait(0)`, the value 0 means **wait indefinitely**, not return immediately.

A timeout only means "the wait duration expired according to the API contract"; it does **not** mean the predicate has become true. Conceptual example:

~~~java
long deadline = System.nanoTime() + java.util.concurrent.TimeUnit.SECONDS.toNanos(2);
synchronized (monitor) {
    while (!ready) {
        long remainingNanos = deadline - System.nanoTime();
        if (remainingNanos <= 0) {
            throw new java.util.concurrent.TimeoutException("ready timeout");
        }
        java.util.concurrent.TimeUnit.NANOSECONDS.timedWait(monitor, remainingNanos);
    }
}
~~~

This is an **illustrative snippet**, assuming `monitor` and `ready` exist in a valid scope; when used in a method, `InterruptedException` and `TimeoutException` must be declared or handled. `timedWait` here is a convenience method on `TimeUnit` that still relies on monitor wait. Use `System.nanoTime()` for elapsed intervals, not wall-clock time, to compute internal deadlines. In production code, handling deadlines with large additions should consider overflow, and concurrency primitives with built-in timeouts may be preferred.

## 5. Distinguishing wait(), sleep(), join(), BLOCKED, and Condition.await()

| Situation | Resource/signal being waited on | Typical Java state | Releases monitor/lock? |
| --- | --- | --- | --- |
| `Thread.sleep(500)` | Clock elapsing | `TIMED_WAITING` | **Does not release** held monitors |
| `Object.wait()` | Notify/interrupt/spurious wakeup | `WAITING` | Releases the monitor of the object `wait()` is called on and reacquires it before returning |
| `Object.wait(500)` | Signal or timeout | `TIMED_WAITING` | Releases the corresponding monitor |
| Trying to enter `synchronized` held by another thread | Monitor lock | `BLOCKED` | Has not acquired that monitor yet |
| `Thread.join()` | Target thread termination | `WAITING` | No "release all locks" rule |
| `Thread.join(500)` | Target thread termination or timeout | `TIMED_WAITING` | No "release all locks" rule |
| `Condition.await()` with `ReentrantLock` | `signal`/`signalAll`/interrupt/spurious wakeup | Usually `WAITING` | Releases **the lock associated with the Condition**, reacquires it before returning |
| `BlockingQueue.take()` on an empty queue | New element available | Usually `WAITING` | Primitive manages internal locks/conditions |
| Blocking I/O reading a socket | Data/EOF/error/timeout | Depends on API and JVM; may be `RUNNABLE` | **Does not release** monitors or `Lock`s held outside the I/O call |

Two common mistakes:

**Mistake A — holding a monitor while sleeping**

~~~java
synchronized (monitor) {
    Thread.sleep(1000);
}
~~~

During that second, the thread still holds the monitor. Other threads needing to enter `synchronized(monitor)` must wait in `BLOCKED`. `sleep()` only pauses execution; it is not a predicate-waiting mechanism and does not release the monitor.

**Mistake B — holding a lock during a very slow I/O call**

~~~java
synchronized (monitor) {
    byte[] data = inputStream.readNBytes(1024);
    // If the data source is slow, other threads may get stuck
    // waiting on the same monitor, even though the CPU is not busy.
}
~~~

The snippet above only illustrates the impact of holding a lock; to use it, `inputStream` must be declared and `IOException` handled. Limit critical sections to updating shared state, and avoid putting I/O operations with unpredictable duration inside a locked region unless truly necessary.

## 6. Java 17+ Example: thread waiting on a condition and then being awakened

This program demonstrates four milestones: the thread has started, enters `wait()` when `ready=false`, is awakened via `notifyAll()` by another thread, and terminates. The `ready` variable is only read/written while holding the same monitor to ensure correctness and visibility.

Create file **`ConditionLifecycleDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public class ConditionLifecycleDemo {
    private static final Object MONITOR = new Object();
    private static boolean ready;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch entered = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            synchronized (MONITOR) {
                entered.countDown();

                while (!ready) {
                    try {
                        MONITOR.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        System.out.println("worker-interrupted");
                        return;
                    }
                }
            }
            System.out.println("worker-finished");
        }, "condition-worker");

        System.out.println("before-start=" + worker.getState());
        worker.start();
        entered.await(); // Ensures worker has entered synchronized at least once.

        // Snapshot: may be RUNNABLE or WAITING depending on timing.
        System.out.println("during-wait=" + worker.getState());

        synchronized (MONITOR) {
            ready = true;
            MONITOR.notifyAll();
        }

        worker.join(); // Wait for worker to finish.
        System.out.println("after-join=" + worker.getState());
    }
}
~~~

Compile and run:

~~~bash
javac ConditionLifecycleDemo.java
java ConditionLifecycleDemo
~~~

One **possible** observed output:

~~~text
before-start=NEW
during-wait=WAITING
worker-finished
after-join=TERMINATED
~~~

**`during-wait` is not guaranteed to always be `WAITING`**: right after `entered.countDown()`, the worker might not have called `wait()` yet. If main acquires `MONITOR` first, the worker may not have waited yet, and then later see `ready=true` and skip `wait()`. On other runs, the snapshot may be `RUNNABLE`, `BLOCKED`, or another state consistent with scheduling. What is reliable is `before-start=NEW`, eventually printing `worker-finished` (when not interrupted), and then `after-join=TERMINATED`.

Why doesn't this program suffer from a "lost notification"?
- `ready` is checked **under the same monitor** as the update/`notifyAll()` operation.
- If main sets `ready=true` before the worker manages to call `wait()`, the worker will see the predicate is true and **will not wait**. It does not depend on "remembering" a notify signal.
- If the worker has already called `wait()`, waiting releases the monitor so main can enter, update the predicate, and signal.
- `while` protects against spurious wakeups or predicate changes in more complex programs.

Note that `CountDownLatch` in this demo only coordinates the observation point `entered.await()`; it **does not guarantee** the worker has transitioned into `WAITING`. If you need to write tests around state, use active synchronization tools and timeouts; do not assert on a single `getState()` call as a deterministic check.

## 7. Java 17+ Example: a reader waiting for I/O data

To observe blocking I/O without needing an external server/network, use a `PipedInputStream` / `PipedOutputStream` pair. The reader calls `read()` when no bytes are available yet; the writer on the main thread sends the character `A` after a brief delay.

This is **an in-memory Java pipe**, suitable for experimentation, and does not exactly represent every type of socket or native file I/O. The observed `Thread.State` depends on how `PipedInputStream` implements waiting.

Create file **`BlockingIoLifecycleDemo.java`**:

~~~java
import java.io.IOException;
import java.io.PipedInputStream;
import java.io.PipedOutputStream;
import java.util.concurrent.CountDownLatch;

public class BlockingIoLifecycleDemo {
    public static void main(String[] args) throws Exception {
        try (PipedInputStream input = new PipedInputStream();
             PipedOutputStream output = new PipedOutputStream(input)) {

            CountDownLatch startingRead = new CountDownLatch(1);
            Thread reader = new Thread(() -> {
                try {
                    startingRead.countDown();
                    int value = input.read(); // May wait until a byte is available.
                    System.out.println("received=" + (char) value);
                } catch (IOException e) {
                    System.out.println("io-error=" + e.getClass().getSimpleName());
                }
            }, "pipe-reader");

            reader.start();
            startingRead.await();

            Thread.sleep(100); // Just creates a window to observe.
            System.out.println("while-reading=" + reader.getState());

            output.write('A');
            output.flush();

            reader.join();
            System.out.println("after-join=" + reader.getState());
        }
    }
}
~~~

Run:

~~~bash
javac BlockingIoLifecycleDemo.java
java BlockingIoLifecycleDemo
~~~

On a normal run, example output:

~~~text
while-reading=TIMED_WAITING
received=A
after-join=TERMINATED
~~~

Only the two lines **`received=A`** and **`after-join=TERMINATED`** are expected to be stable when I/O succeeds and the thread finishes. **`while-reading` is a snapshot with no fixed value**: it may be `TIMED_WAITING`, `WAITING`, `RUNNABLE`, or another valid state depending on timing and implementation. If the stream fails, the `io-error=...` branch will appear instead of successful data.

Important observation: the condition for the reader to make progress is **a byte arriving from the writer**, not main waking up the reader's monitor with `notifyAll()`. Nor should you call `reader.interrupt()` and assume every `InputStream.read()` will exit immediately: interruption support varies by API and I/O path.

In the example, main calls `reader.join()` to wait for the result; `join()` is **a different kind of wait** by the main thread, and does not make the reader automatically transition to `RUNNABLE`.

## 8. Condition.await() and primitives instead of manual wait/notify

`Object.wait()/notifyAll()` helps explain the monitor mechanism, but in application code, higher-level concurrency primitives are usually simpler and less error-prone.

### 8.1. ReentrantLock + Condition

With `java.util.concurrent.locks.ReentrantLock`, a condition bound to the lock is created via `newCondition()`:

~~~java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

// Illustrative snippet inside a class with shared state:
private final ReentrantLock lock = new ReentrantLock();
private final Condition canProceed = lock.newCondition();
private boolean ready = false;

public void awaitReady() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        while (!ready) {
            canProceed.await(); // Releases lock; waits; reacquires lock before returning.
        }
    } finally {
        lock.unlock();
    }
}

public void markReady() {
    lock.lock();
    try {
        ready = true;
        canProceed.signalAll();
    } finally {
        lock.unlock();
    }
}
~~~

This is a **class-member snippet**, not a standalone program. When placed in a valid class, the methods illustrate how `await` and `signalAll` differ from `wait` and `notifyAll`:
- `Condition.await()` must be called while the thread holds **the corresponding lock**. It releases the lock while waiting and reacquires it before returning.
- `signalAll()` does not carry a predicate; the awakened thread still rechecks `ready` in `while`.
- Always `unlock()` in `finally`; when an interruption occurs during `await()`, lock reacquisition is handled according to the `Condition` contract before unwinding.
- `lockInterruptibly()` can be interrupted while waiting to acquire the lock. `lock()` has different semantics, so choose based on task cancellation requirements.

### 8.2. BlockingQueue.take() expresses the "element available" condition

If the real requirement is **a consumer waiting for a producer to submit work**, `BlockingQueue` eliminates manual `wait/notify`:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

public class QueueWaitDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new LinkedBlockingQueue<>();

        Thread consumer = new Thread(() -> {
            try {
                String value = queue.take(); // Waits until an element is available.
                System.out.println("consumed=" + value);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("consumer-interrupted");
            }
        }, "consumer");

        consumer.start();
        queue.put("work");
        consumer.join();
    }
}
~~~

Save file **`QueueWaitDemo.java`**, run:

~~~bash
javac QueueWaitDemo.java
java QueueWaitDemo
~~~

When there is no interruption:

~~~text
consumed=work
~~~

If main calls `put` before the consumer calls `take`, the consumer takes the element immediately and **does not need to enter `WAITING`**. If the consumer calls `take` before an element is available, it waits using the queue's internal mechanism. In both cases the program remains correct: **the data in the queue is the required state**, independent of any missed signal.

With `LinkedBlockingQueue<>()` without a capacity argument, the default capacity is large (up to `Integer.MAX_VALUE`); in systems under real load, consider a bounded queue, timeouts, and an appropriate rejection policy rather than accumulating an unbounded backlog by design.

### 8.3. CountDownLatch and join serve different purposes

- `CountDownLatch.await()`: waits for a counter to reach 0; used for a one-shot signal—once it reaches 0, it does not reset.
- `Thread.join()`: waits for **the target thread to terminate**; it is not waiting for network data and does not mean a "logical task" has finished if work continues on another worker.
- `Future.get()`: waits for a task's result or receives an exception; has a timed variant.
- `Semaphore.acquire()`: waits for a permit; suitable for limiting the number of tasks concurrently using a scarce resource.

Using the right primitive makes intent clearer and reduces the risk of deadlock, missed signals, and race conditions.

## 9. Interrupts, timeouts, resource closing, and cancellation

A thread can wait indefinitely if the data source, condition, or completion signal never arrives. Therefore, concurrency design must answer: **when should waiting stop, and who is responsible for releasing resources?**

### 9.1. Interruption is a cooperative request, not a forced stop

`Thread.interrupt()` sets the interrupt status and has specific behavior for certain waiting operations.

For example, with `Object.wait()`, `Thread.sleep()`, `Thread.join()`, and many `java.util.concurrent` primitives, an interrupt may throw `InterruptedException`, and the interrupt flag is cleared when the exception is thrown. Pattern when code cannot propagate the exception:

~~~java
try {
    queue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt(); // Restore flag for outer callers.
    return;
}
~~~

This is an **illustrative snippet** inside a method that has `queue` in scope. If your API can declare `throws InterruptedException`, it is usually better to let the exception propagate rather than swallowing it. Do not continue an infinite wait loop after catching and ignoring an interrupt if the task needs to be cancellable.

**For I/O: rules vary by API.** For instance, a blocking operation on an `InterruptibleChannel` may close the channel and throw `ClosedByInterruptException`; `Selector` has its own interrupt handling. There is no general guarantee that `interrupt()` will unblock every `InputStream.read()` or every native call in Java 17. Use the appropriate API's timeout, cancellation, and/or resource closing according to its documented contract. Be careful to ensure threads still have an exit path during application shutdown.

### 9.2. Timeouts must have clear boundaries and consequences

For example, when waiting on a queue, replace `take()` with `poll(2, TimeUnit.SECONDS)`: if it expires, a `null` result means **no element was retrieved before the deadline**, not that the queue is broken. With traditional sockets, a read timeout can be configured via the corresponding API (`Socket#setSoTimeout`); a read timeout differs from a connect timeout and does not replace an end-to-end request deadline.

A complete policy should distinguish:
- **Timeout**: maximum wait time for an operation.
- **Cancellation**: user/system request not to continue the work.
- **Backpressure/admission control**: reducing admitted load when resources/queues are full.
- **Resource cleanup**: closing streams/sockets, returning connections, releasing locks in `finally` or try-with-resources.

Simply increasing timeouts without addressing the source of waiting can increase the number of held tasks and make subsequent requests slower.

## 10. Thread pools and virtual threads

### 10.1. Platform threads are a finite resource

A platform thread typically corresponds to an operating system thread. In a **thread-per-request** model, if each request mostly blocks on I/O, the number of threads needed to hold many concurrent requests can be large even while the CPU is idle. This causes:
- Stack, scheduling, and thread management overhead.
- Queuing for free workers in a bounded `ExecutorService`.
- Increased connections, open files, and pressure on downstream services.

I/O-bound tasks can benefit from higher concurrency than CPU-bound tasks, but a reasonable limit depends on **actual resources and SLOs**. Measure latency, successful throughput, queued requests, errors, and pool utilization rather than choosing thread count from core count alone.

### 10.2. Virtual threads (Java 21+) change the cost of waiting

Virtual threads are a lighter-weight thread mechanism for workloads with many independent I/O-waiting tasks. For JVM-supported blocking operations, a virtual thread can **yield its carrier platform thread** while waiting, allowing the carrier to serve another virtual thread. This makes models with many waiting tasks more convenient.

However, keep in mind:
- Virtual threads **do not increase the number of CPU cores** and do not make remote services respond faster.
- They still consume memory, file descriptors, connections, and downstream resource capacity.
- Do not infer the exact state of the carrier from a virtual thread's `Thread.currentThread().getState()`.
- Some blocking or native/foreign operations, synchronization mechanisms, and pinning behavior depend on the specific JDK version; consult documentation and observe the exact JDK when analyzing such issues.
- `Thread.State` and `wait/interrupt` APIs must still be understood according to the Java contract; virtual threads do not make untimed waiting unconditionally safe.

The runnable examples in this lesson use Java 17 and platform threads to isolate the causes of waiting. The virtual threads section only provides Java 21+ context and does not require new APIs to run the demos.

## 11. What information helps diagnose a "stuck thread"?

### 11.1. Reading stack traces and Java state together

Use `Thread.getState()` to inspect the current state, combined with `Thread.getStackTrace()` or a thread dump (e.g., `jcmd <pid> Thread.print` on supported JDKs). For CPU, locks, and thread activity in a Java process, you can use Java Flight Recorder (JFR), Java Mission Control (JMC), or `ThreadMXBean` where the relevant metrics are supported.

| Symptom | What may be happening | What to verify next |
| --- | --- | --- |
| Thread dump shows `BLOCKED`, stack at `synchronized` | Monitor contention | Who holds the monitor, for how long, and is there a lock-order cycle |
| `WAITING` at `Object.wait()` or `Condition.await()` | Waiting for a predicate/signal | Where the predicate is updated, who signals, and whether timeout/cancellation paths exist |
| `TIMED_WAITING` at `Thread.sleep` | Timed sleep | Whether a lock is held, and whether sleep is mistakenly replacing waiting logic |
| `RUNNABLE` with stack in `SocketInputStream.read` or native read | Possibly waiting on I/O | Remote latency, socket timeout, connection count, logs before/after read |
| Many pool workers active, low CPU, growing queue | Many workers may be waiting on I/O or locks | Measure wait duration, queue size, pool metrics, and downstream |
| `TERMINATED` but business task has no final result yet | Processing path may have handed off to another thread or failed | Correlation ID, task Future/status, data flow |

**Do not conclude deadlock just because a thread stays in `WAITING` for a long time.** A consumer with no work may wait completely legitimately. Deadlock requires evidence of a cycle of lock/resource dependencies preventing all parties from making progress; `ThreadMXBean.findDeadlockedThreads()` can help detect some cases, but does not replace analyzing I/O waits or external dependencies.

### 11.2. Measuring time at the right boundaries

Measure separate intervals with `System.nanoTime()`:

~~~text
submit/enqueue ---- queue wait ---- start worker
                                         |
                                         +-- waiting for lock
                                         +-- blocking I/O
                                         +-- condition wait
                                         +-- CPU work
                                         |
                                       complete
~~~

**Task latency = queue wait + elapsed time in worker**, whereas **CPU time** only counts CPU time actually used. If a worker waits 1 second on I/O and then does 5 ms of CPU work, ~1 second of elapsed time does not mean the CPU ran for 1 second.

Use histograms/p95/p99 and counter metrics (timeouts/rejections/connections/CPU). A thread state snapshot tells you **what state it was in at sampling time**; timing measurements tell you **how long it waited**.

## 12. Common mistakes and how to fix them

1. **Seeing `RUNNABLE` and claiming the thread is burning CPU.** The thread may be in native/blocking I/O or waiting to be scheduled. Combine stack traces, CPU time, and I/O metrics.
2. **Calling every kind of waiting `BLOCKED`.** In `Thread.State`, `BLOCKED` means waiting for a monitor; `WAITING` and `TIMED_WAITING` have different meanings.
3. **Using `Thread.sleep()` to "wait until data arrives".** Sleep is not tied to a predicate or signal, causing unnecessary delay or continuous polling. Prefer condition-based concurrency primitives.
4. **Calling `wait()` outside `synchronized`.** This throws `IllegalMonitorStateException`. You must hold the right monitor.
5. **Using `if` instead of `while` around `wait/await`.** Fails to guard against spurious wakeups or condition races after waking up.
6. **Just calling `notify()` to fix any liveness bug.** A signal does not replace a predicate; it can also wake the wrong waiter if multiple conditions share a monitor. Use a proper predicate and `notifyAll()`/`signalAll()` where appropriate, or a higher-level abstraction.
7. **Thinking `notifyAll()` makes a thread run immediately.** Waiters still need to reacquire the monitor/lock; wakeup order does not guarantee execution order.
8. **Holding a lock during slow I/O.** A thread waiting on the network can still hold a monitor, forcing other threads into `BLOCKED`.
9. **Swallowing `InterruptedException` and continuing the loop.** This can stall cancellation/shutdown. Propagate the exception or restore the interrupt status and exit cleanly.
10. **Increasing worker count indefinitely to solve slow I/O.** This can shift the bottleneck to connections, databases, memory, file descriptors, or downstream services; measure and bound concurrent work.
11. **Not setting timeouts for external dependency waits.** A failing request can hold resources indefinitely. Configure timeouts and cleanup per the API.
12. **Checking `getState() == WAITING` to decide whether to call notify.** Snapshots are racy and cannot replace a predicate under the same synchronization mechanism.
13. **Assuming virtual threads remove all limits.** They reduce thread overhead in many waiting scenarios, but do not eliminate resource limits or the need for timeouts and cancellation.

## 13. Self-check questions

1. A thread is waiting for bytes on a socket and `getState() == RUNNABLE`. Does that prove it is running on the CPU? **No.** The Java state may not reflect OS-level I/O waiting details.
2. A thread tries to enter `synchronized(lock)` while another thread holds the monitor. What can its Java state be? **`BLOCKED`.**
3. Why does `Object.wait()` allow a producer to enter the same monitor while `Thread.sleep()` inside `synchronized` does not? **`wait()` releases the associated monitor; `sleep()` does not release the monitor.**
4. Why must you write `while (!ready) monitor.wait()` instead of `if`? **The predicate may still be false due to a spurious wakeup or another thread changing the state before the waiter reacquires the monitor.**
5. Does `notifyAll()` guarantee that a waiter starts running immediately? **No.** Waiters still have to compete to reacquire the monitor.
6. A pool of four workers are all waiting 2 seconds on the database, process CPU is only 10%, and the queue is growing. Why? **Worker slots are occupied by waiting tasks; low CPU does not mean workers are free.**
7. Does `interrupt()` guarantee interrupting every I/O call in Java 17? **No.** The contract depends on the stream/channel type; use appropriate timeouts, cancellation, or closing.
8. When observing `WAITING` inside `BlockingQueue.take()`, is that a sign of deadlock? **Not necessarily.** An empty queue with a consumer waiting for data is normal.
9. What problem do virtual threads help with, and what do they not help with? **They reduce the cost of keeping many concurrent tasks waiting on supported blocking operations; they do not increase CPU or speed up the data source.**

## Conclusion

**Blocking I/O** makes a task's execution wait for external data or resources; **condition waiting** makes a thread wait for a predicate changed by coordinating threads. Both can prevent tasks from completing even when the CPU is idle. However, **`Thread.State.BLOCKED` only refers to waiting for a monitor lock**, whereas I/O can be observed as `RUNNABLE` and condition waiting typically appears as `WAITING` or `TIMED_WAITING`.

When designing Java concurrency, express conditions with predicates and appropriate primitives, avoid holding locks during I/O waits, include timeouts/cancellation/cleanup, and measure both queue wait and actual wait duration. **Do not use `getState()` snapshots as a synchronization mechanism or as the sole conclusion about performance.**

### Java API References

- [Java SE 17 — Thread.State](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): definition of the six states and limitations when inferring OS state.
- [Java SE 17 — Object.wait/notify](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): monitor release, reacquisition, interruption, and spurious wakeup.
- [Java SE 17 — Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `sleep()`, `join()`, `interrupt()`.
- [Java SE 17 — Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): `await`, `signal`, and lock rules.
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): `take`, `poll`, `put`.
- [Java SE 17 — PipedInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PipedInputStream.html): reading a pipe when no bytes are available yet.
