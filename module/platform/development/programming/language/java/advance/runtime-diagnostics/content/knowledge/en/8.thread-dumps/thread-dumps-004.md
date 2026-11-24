# 8.4. Distinguishing RUNNABLE, BLOCKED, WAITING, and TIMED_WAITING

When investigating a slow, hung, or unresponsive Java service, you often inspect a thread dump and see the labels `RUNNABLE`, `BLOCKED`, `WAITING`, and `TIMED_WAITING`. **The same label can be a completely normal operating state or a symptom of an incident**, depending on what the thread is doing, whom or what resource it is waiting on, whether the state persists, and whether business work is making progress.

This lesson belongs to **8. Thread dumps**. The goal is to accurately interpret the four `java.lang.Thread.State` values, connect them with stack frames, monitors/locks, synchronization APIs, and evidence across one or more thread dumps, and investigate with evidence rather than guessing “WAITING means hung” or “RUNNABLE definitely burns CPU”.

## 1. The four states and the core diagnostic questions

In Java 17, `Thread.State` is a state **described by the JVM**, **not** a direct mapping to OS thread states. A thread has only **one** of the six enum values at a given moment: `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED`. The four states commonly analyzed in thread dumps are:

| Java state | Short meaning | Common APIs/situations | Questions to ask |
| --- | --- | --- | --- |
| **RUNNABLE** | Executable in the JVM; **may be waiting for OS resources** | Running Java code, loops, JNI/native I/O, socket reads in some stacks | Is it consuming actual CPU? Do frames change? Is there I/O or a native wait? |
| **BLOCKED** | Waiting to enter/reenter an **intrinsic monitor** | Waiting on `synchronized` block/method, waiting to reacquire monitor after `Object.wait` | Which monitor is held? Which owner thread holds it? Is there contention/lock ordering? |
| **WAITING** | Waiting indefinitely for another thread/event to perform an action | `Object.wait()`, `Thread.join()`, `LockSupport.park()`; `Condition.await()` typically uses park | What signal is it waiting for? Is there a corresponding producer/unpark/notify/complete? |
| **TIMED_WAITING** | Waiting with a specified time limit | `Thread.sleep(...)`, timed `Object.wait`/`join`, `LockSupport.parkNanos`/`parkUntil`, timed condition wait | What is it waiting for and how long is the timeout? Is this valid sleep/backoff/polling or abnormal repeated waiting? |

**Key rules to remember:**
- `BLOCKED` in `Thread.State` specifically means **waiting for a monitor lock**, not generically “blocked by network, DB, or any arbitrary mutex”.
- `WAITING`/`TIMED_WAITING` describes the **waiting mechanism**, not yet a conclusion that the thread has a problem.
- `RUNNABLE` does not mean the thread **is occupying a CPU core**. The Java docs allow RUNNABLE while a thread is waiting for an OS resource such as a processor.
- A thread in `BLOCKED`, `WAITING`, or `TIMED_WAITING` may still **be doing the right work** by design. Saying “hung” requires progress/duration/timeline evidence.

### The remaining two states

- `NEW`: `new Thread(...)` has been created, but **`start()` has not been called yet**.
- `TERMINATED`: the thread has finished `run()` and is no longer running.

Not every `Thread` in `NEW`/`TERMINATED` appears in a **thread dump of live threads**. These two states exist in the enum/API, while practical dumps usually focus on threads still alive at sampling time.

## 2. RUNNABLE: “runnable”, not necessarily “running on CPU”

### 2.1. Mechanism

In Java SE 17, a thread in `RUNNABLE` is executing in the JVM under the Java model, yet **may be waiting for a resource from the OS**. The OS decides whether the thread is truly **running**, **ready/on-run-queue**, or waiting on a native operation. Therefore, do not look at a single `RUNNABLE` snapshot and conclude the application is CPU-bound.

**Illustrative** stack example for a CPU task:

~~~text
"price-worker-1" #42 ... nid=0x2a10 runnable ...
   java.lang.Thread.State: RUNNABLE
        at com.example.PriceCalculator.recalculate(PriceCalculator.java:118)
        at com.example.PriceJob.run(PriceJob.java:53)
~~~

If across multiple dumps spaced seconds apart the thread remains in the same loop, CPU time surges, request p99 rises, and throughput drops, that is a **sign** to investigate a hot loop or inefficient algorithm. However, **a single dump showing the same frame** does not prove an infinite loop.

Example where RUNNABLE may not consume much CPU:

~~~text
"network-reader" #51 ... nid=0x2a19 runnable ...
   java.lang.Thread.State: RUNNABLE
        at sun.nio.ch.SocketDispatcher.read0(Native Method)
        at sun.nio.ch.SocketDispatcher.read(SocketDispatcher.java:...)
        at sun.nio.ch.NioSocketImpl.implRead(NioSocketImpl.java:...)
~~~

This is illustrative; frames vary by JDK/version/network stack. Native/OS I/O calls can wait for data while Java state is RUNNABLE. **Do not claim every socket read is RUNNABLE**; correlate `top -H`/`pidstat -t`/Java Flight Recorder (JFR) or thread CPU time when needed.

### 2.2. Distinguishing CPU-bound work from native waits

Suggested workflow:
1. Identify **thread name + Java thread ID + native ID (`nid`)** from the dump header, along with the JVM PID.
2. Capture **multiple snapshots** while the issue is occurring, spaced at useful intervals; save timestamps.
3. Look at frames at the **top of the stack**, business-logic calls, and changes between snapshots.
4. Measure **per-thread** CPU with an appropriate OS tool, mapping native TIDs to `nid` when supported by the runtime; on Linux `nid` is typically represented in hex.
5. If CPU time rises alongside a loop frame, prioritize investigating CPU-bound work. If CPU is low, check OS waits, I/O, locks/latches, native calls, polling, and infrastructure.

**Note:** “many RUNNABLE threads” is not sufficient to explain 100% CPU, because the JVM state name does not directly reflect CPU usage. Do not use the count of RUNNABLE threads as a substitute CPU metric.

## 3. BLOCKED: waiting to enter a `synchronized` monitor

### 3.1. What is a monitor in Java?

Every Java object can act as an **intrinsic monitor** used by `synchronized (lock)` or a synchronized instance method. At any one time only one thread may **hold that monitor**. Another thread attempting to enter the same monitor while someone holds it will be in Java state `BLOCKED` until it gains entry.

~~~java
final Object monitor = new Object();

// Thread A:
synchronized (monitor) {
    // Holding the monitor.
    work();
}

// Thread B:
synchronized (monitor) {
    // If A has not exited, B must wait for the monitor: BLOCKED.
    otherWork();
}
~~~

This is an **illustrative snippet**, assuming `work()`/`otherWork()` and two threads already exist; it is not a standalone Java file.

If B is blocked, a HotSpot dump may contain information such as:

~~~text
"order-worker-2" #67 ... waiting for monitor entry ...
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.OrderRepository.update(OrderRepository.java:84)
        - waiting to lock <0x00000000ABCDEF00> (a java.lang.Object)
        at com.example.OrderService.process(OrderService.java:41)
~~~

Addresses, classes, lines, and headers are **illustrative values**, not reproducible stdout. You must find the **thread holding the monitor**; the output may contain a corresponding frame:

~~~text
"order-worker-1" #66 ... 
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.lang.Thread.sleep(Native Method)
        at com.example.OrderRepository.update(OrderRepository.java:79)
        - locked <0x00000000ABCDEF00> (a java.lang.Object)
~~~

Even though the owner is `TIMED_WAITING` due to sleep, it **still holds the monitor**; B waits in `BLOCKED`. This shows you cannot diagnose solely from each thread's individual state while ignoring **lock owner relationships**.

### 3.2. BLOCKED differs from `ReentrantLock.lock()`

A thread waiting on **`java.util.concurrent.locks.ReentrantLock`** is typically implemented using **`LockSupport.park()`**, so in dumps it usually appears as `WAITING (parking)` or `TIMED_WAITING` with a timeout. It is **not necessarily** in `BLOCKED`, even though in everyday language it is “blocked by a lock”.

Look for:
- Frames `java.util.concurrent.locks.AbstractQueuedSynchronizer.acquire/park...` or `LockSupport.park`.
- Lines `parking to wait for <...>` or ownable synchronizer details, depending on the tool and the `-l` option.
- `ThreadInfo.getLockOwnerId()/getLockOwnerName()` or `ThreadMXBean.dumpAllThreads(true,true)` if the runtime supports lock info collection.

**Do not equate:** `BLOCKED` (JVM enum) ↔ blocked I/O ↔ waiting for a database connection ↔ waiting on `ReentrantLock`. Always read the **primitive type** and the **actual frames**.

### 3.3. What does prolonged BLOCKED mean?

- A few milliseconds of `BLOCKED` when multiple threads enter a short critical section is normal.
- Many threads `BLOCKED` on **the same object monitor** across multiple snapshots, with the owner holding the lock for a long time: may be a **contention bottleneck**.
- Two or more threads holding different monitors and waiting on each other without progress: may be a **deadlock**.
- An owner sleeping/doing I/O/calling DB **inside synchronized**, forcing other threads to wait a long time: usually an overly broad critical section design.

Ask “which thread holds the lock, what is it doing inside the lock, for how long, and is it making progress?” before changing code.

## 4. WAITING: indefinite waiting, does not mean “waiting forever”

`WAITING` is the state where a thread waits for an action without a specified timeout in the wait call.

### 4.1. Familiar causes

- `Object.wait()`: the thread must hold the monitor when calling, then **releases that monitor** and waits for `notify`/`notifyAll` or interruption/spurious wakeup; to resume from `wait`, the thread must **reacquire the monitor**, possibly transitioning to `BLOCKED` if the monitor is still held.
- `Thread.join()` without timeout: waits for another thread to complete.
- `LockSupport.park()`: waits for a permit/unpark/interrupt, or may return spuriously.
- `Condition.await()` typically uses the park mechanism; a thread may show `WAITING` while waiting on a condition.
- Worker threads in an `ExecutorService` may be `WAITING` when the queue has no tasks; this is usually a healthy **idle pool**.
- `CompletableFuture.join()` or synchronization utilities may use parking/waiting; check the stack and timeout semantics of the specific API.

Illustrative example:

~~~text
"worker-pool-3" #88 ...
   java.lang.Thread.State: WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        at java.util.concurrent.locks.LockSupport.park(LockSupport.java:...)
        at java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionNode.block(...)
        at java.util.concurrent.ThreadPoolExecutor.getTask(ThreadPoolExecutor.java:...)
~~~

**Do not hardcode internal frames**: AQS/ThreadPoolExecutor internals change across JDKs and collectors; the output above is merely suggestive. A worker `WAITING` in `getTask` can be completely normal when there is no work.

### 4.2. `Object.wait` differs from `Thread.sleep`

Two frequently confused APIs:
- `Object.wait()` **releases the monitor of the object on which wait is called**, waits for notification, and then must re-acquire it before continuing. You may see `WAITING (on object monitor)` or a transition to `BLOCKED` upon reentry.
- `Thread.sleep(milliseconds)` **does not release any held monitors** and places the thread into `TIMED_WAITING` when sleeping for a positive duration.

Illustrative snippet:

~~~java
synchronized (monitor) {
    monitor.wait();   // Releases this monitor while waiting.
}

synchronized (monitor) {
    Thread.sleep(1000); // Still holds the monitor while sleeping.
}
~~~

The calls above assume `monitor` is already declared and the enclosing method declares `throws InterruptedException` or catches it. **Do not run the first `wait()` sample alone** if no thread can notify/unpark it: it can wait indefinitely. When using wait for a real condition, wrap it in `while (!condition) monitor.wait()` to handle **spurious wakeups** and re-check state.

### 4.3. When is WAITING suspicious?

- A pool has many `WAITING` threads while the queue is empty and request latency is normal: usually not a problem.
- A request waits on `CompletableFuture.join()` or `CountDownLatch.await()`, while the producer is not running/never signals: may be a **liveness issue**.
- A thread waits on a condition while code fails to call `signal`/`notify` on the right branch: suspect a **lost notification/protocol bug**, requiring understanding of the synchronization logic.
- A thread waits on `Future.get()` while the executor has only a single worker and the awaited task is queued in that same executor: may be a **thread pool starvation deadlock**, even though the thread state is WAITING and tools will not necessarily report a Java monitor deadlock.

A prolonged WAITING state alone does not prove deadlock: you must identify **which event will wake it up**, which actor must produce that event, and whether it is able to do so.

## 5. TIMED_WAITING: has a timeout, does not mean expired

`TIMED_WAITING` is waiting up to a specified time limit:

| API | Example | Meaning |
| --- | --- | --- |
| `Thread.sleep` | `Thread.sleep(500)` | Sleeps for a requested duration of 500 ms |
| `Object.wait(timeout)` | `lock.wait(500)` inside `synchronized` | Releases monitor, waits for notification up to the interval, then re-acquires |
| `Thread.join(timeout)` | `other.join(1000)` | Waits for the other thread to finish, with a bound |
| `LockSupport.parkNanos` | `LockSupport.parkNanos(1_000_000)` | Parks for up to roughly 1 ms |
| `LockSupport.parkUntil` | Park until deadline | Waits until the specified timestamp |
| `Condition.await(time, unit)` | Timed condition wait | Waits for signal or deadline per API |

Illustrative dump signs:

~~~text
"retry-scheduler" #91 ...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
        at java.lang.Thread.sleep(Native Method)
        at com.example.RetryLoop.backoff(RetryLoop.java:57)
~~~

Or:

~~~text
"polling-worker" #92 ...
   java.lang.Thread.State: TIMED_WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        at java.util.concurrent.locks.LockSupport.parkNanos(LockSupport.java:...)
        at java.util.concurrent.DelayQueue.take(DelayQueue.java:...)
~~~

Frames are **illustrative** and may differ by runtime.

**Correct understanding:** the timeout is only a **requested limit** under the API contract and JVM/OS scheduling; it does not guarantee the thread will get CPU immediately when the deadline expires. The call may return early due to interruption, notify/unpark (for supporting APIs), or spurious wakeup. For `sleep`, early return via interruption is reported through `InterruptedException`; do not arbitrarily assume all APIs behave identically.

### Normal and abnormal `TIMED_WAITING`

- A scheduler sleeping between scan cycles, retries with backoff, or sockets/clients waiting with timeouts: can be normal.
- Thousands of threads calling `sleep` inside a `synchronized` block: suspect lock contention impacting other threads.
- Many request threads in timed `Future.get`/`Condition.await` with high p99: may indicate slow downstream dependencies or a saturated thread pool.
- A thread repeating short sleep cycles and retrying indefinitely: may be a **retry storm**; inspect event logs/metrics.
- **Do not** rely on TIMED_WAITING to conclude “about to recover on its own”, especially if the timeout is configured too long or the loop waits again after timing out.

## 6. Reading labels in a thread dump in proper context

### 6.1. Capturing snapshots with the right tool

For a running JVM on the right host/namespace with attach permissions:

~~~bash
jcmd -l
jcmd 12345 help Thread.print
jcmd 12345 Thread.print -l
~~~

`12345` is an **illustrative** PID; verify the PID of the real JVM. `-l` on `Thread.print` requests additional info about `java.util.concurrent` locks, which can help find owners/waiters. `jcmd -l` is the **list JVMs** switch, not the same as `Thread.print -l`.

Some environments use:

~~~bash
jstack 12345
~~~

Depending on JDK/OS/version, output and support levels vary; if the JVM cannot be attached to, check process owner, container PID namespace, whether the JVM exited, or whether attach is disabled. Capturing a thread dump has a cost proportional to thread count; do not run it repeatedly in production without assessing impact.

**Do not use `jcmd 0 Thread.print`** to investigate one specific PID: target `0` can send the command to **multiple visible JVMs**, creating unnecessary load.

### 6.2. Reading headers and state lines

**Illustrative** HotSpot example:

~~~text
"request-worker-7" #53 daemon prio=5 os_prio=0 cpu=4.21ms elapsed=22.14s
   tid=0x00007f1234010000 nid=0x2a91 waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.OrderService.update(OrderService.java:88)
        - waiting to lock <0x00000000deadbeef> (a java.lang.Object)
        at com.example.OrderController.handle(OrderController.java:42)
~~~

Values, classes/lines, field ordering, and even whether fields appear at all **depend on JDK build, tool, and OS**.

| Information | Meaning | Mistake to avoid |
| --- | --- | --- |
| `"request-worker-7"` | Thread name, useful for identifying executor type | Names can duplicate, change, and be reused by pools; not a request ID |
| `#53` | In many HotSpot dumps, the printed number/Java thread ID | Do not equate with OS TID; verify format |
| `tid=0x...` | In some HotSpot headers, the VM thread structure address/identifier | Do not convert this hex to treat it as Linux TID or `Thread.getId()` |
| `nid=0x2a91` | Native thread ID in HotSpot header | Typically hex; when matching OS, use the right PID namespace |
| `java.lang.Thread.State` | Java enum state at snapshot time | Not instantaneous OS/CPU condition |
| Frame `at Class.method(File.java:line)` | Call site (top is usually closest to active execution/wait) | Do not conclude root cause from a single frame |
| `- waiting to lock` | Monitor being awaited | Find the owner thread and matching object monitor ID |
| `- locked` | Monitor held at the corresponding frame | Do not assume holding a monitor is automatically a bug |
| `- parking to wait for` | Synchronizer or blocker object associated with park | Requires API semantics; may simply be an idle queue |

Headers from other tools/versions may use phrasing like “runnable”, “waiting on condition”, or “waiting for monitor entry” in **the header**, whereas the `java.lang.Thread.State: ...` line is the enum to read first. Do not take the word “waiting” in the header as proof a thread is `WAITING` if the actual state line is `TIMED_WAITING` or `BLOCKED`.

### 6.3. How to trace a thread across multiple dumps

When comparing two dumps:
1. Match **JVM PID + process start time**, avoiding mixing a new process after restart.
2. Use thread name and **Java thread ID/native ID** (when provided by the tool) to track the right thread; do not rely on name alone since pools reuse names.
3. Compare states, top frames, monitor IDs, owners, and call chains across multiple timestamps.
4. Compare application timestamps, requestId/traceId, queue size, duration, CPU/GC/I/O metrics, and throughput.
5. Ask “is there forward progress?”, rather than only “is it still in the same state?”.

Do not publish full dumps publicly: stack frames, classes/paths, log metadata, and some parameters can expose internal details.

## 7. The four states from a diagnostic view: quick matrix

| Observation | May be normal when | Needs deeper investigation when | Additional evidence |
| --- | --- | --- | --- |
| Many `RUNNABLE` | Processing load or native I/O | High CPU/thread CPU, stuck in same loop, requests not progressing | OS per-thread CPU, JFR, multiple thread dumps |
| Many `BLOCKED` | Short-lived monitor contention | Same lock across multiple dumps, owner holds lock long, p99 rises | Monitor ID, owner stack, `-l`, contention |
| Many `WAITING` | Idle executor, empty queue, background service awaiting events | Requests waiting on unsignaled future/latch, thread starvation | Pending tasks, queue, producer/consumer, traces |
| Many `TIMED_WAITING` | Sleep/backoff/scheduled polling, controlled timeouts | Retry storm, cascading waits, sleeping while holding lock, overly long deadline | Timeout config, event timeline, lock ownership |

**There is no fixed “severity level” by enum.** One RUNNABLE thread in an infinite CPU loop is far worse than hundreds of idle WAITING threads. A 2 ms BLOCKED wait is more normal than an indefinite WAITING on a future with no remaining producer.

## 8. Standalone Java 17+: creating four states under control

The following program creates Java platform threads using **four independent mechanisms**:

- `demo-runnable`: runs a short loop with `Thread.onSpinWait()` until main signals stop.
- `demo-blocked`: waits on a monitor held by `demo-lock-owner`.
- `demo-waiting`: calls `LockSupport.park()` without timeout until main calls `unpark`.
- `demo-timed`: calls `Thread.sleep(60_000L)`, which main interrupts on shutdown.

The main thread uses `awaitState` to verify **the actual state** before printing, avoiding a common race where calling `getState()` right after `Thread.start()` happens before the thread enters the target code section. If an overloaded environment prevents reaching the state within 10 seconds, the demo throws a clear error instead of printing false output; `finally` still releases all worker threads.

Create file **ThreadStatesDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.LockSupport;

public final class ThreadStatesDemo {
    private static Thread.State awaitState(
            Thread thread, Thread.State expected)
            throws InterruptedException {

        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(10);

        while (System.nanoTime() < deadline) {
            if (thread.getState() == expected) {
                return expected;
            }
            Thread.sleep(5L);
        }

        throw new IllegalStateException(
                "State not reached: " + thread.getName()
                + " actual=" + thread.getState());
    }

    public static void main(String[] args) throws Exception {
        Object monitor = new Object();
        AtomicBoolean keepRunning = new AtomicBoolean(true);
        AtomicBoolean keepWaiting = new AtomicBoolean(true);
        CountDownLatch ownerLocked = new CountDownLatch(1);
        CountDownLatch releaseOwner = new CountDownLatch(1);

        Thread runnable = new Thread(() -> {
            while (keepRunning.get()) {
                Thread.onSpinWait();
            }
        }, "demo-runnable");

        Thread owner = new Thread(() -> {
            synchronized (monitor) {
                ownerLocked.countDown();
                try {
                    releaseOwner.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-lock-owner");

        Thread blocked = new Thread(() -> {
            synchronized (monitor) {
                // Enters only after demo-lock-owner releases monitor.
            }
        }, "demo-blocked");

        Thread waiting = new Thread(() -> {
            while (keepWaiting.get()) {
                LockSupport.park();
            }
        }, "demo-waiting");

        Thread timed = new Thread(() -> {
            try {
                Thread.sleep(60_000L);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "demo-timed");

        runnable.start();
        owner.start();

        try {
            ownerLocked.await(); // Owner now holds monitor.
            blocked.start();
            waiting.start();
            timed.start();

            System.out.println("runnable="
                    + awaitState(runnable, Thread.State.RUNNABLE));
            System.out.println("blocked="
                    + awaitState(blocked, Thread.State.BLOCKED));
            System.out.println("waiting="
                    + awaitState(waiting, Thread.State.WAITING));
            System.out.println("timedWaiting="
                    + awaitState(timed, Thread.State.TIMED_WAITING));
        } finally {
            keepRunning.set(false);
            keepWaiting.set(false);
            releaseOwner.countDown();
            LockSupport.unpark(waiting);
            timed.interrupt();

            runnable.join(2_000L);
            blocked.join(2_000L);
            waiting.join(2_000L);
            timed.join(2_000L);
            owner.join(2_000L);
        }
    }
}
~~~

Compile and run using **JDK 17 or newer**:

~~~bash
javac ThreadStatesDemo.java
java ThreadStatesDemo
~~~

**Exact stdout under normal scheduling conditions:**

~~~text
runnable=RUNNABLE
blocked=BLOCKED
waiting=WAITING
timedWaiting=TIMED_WAITING
~~~

**Why each line is right:**
1. `demo-runnable` is looping and has not received stop; the JVM reports RUNNABLE. This is a spin loop for **illustration** that can consume CPU; do not use it in business code.
2. `demo-lock-owner` has entered `synchronized` and holds the monitor. `demo-blocked` waits for the same monitor, so it is BLOCKED.
3. `demo-waiting` is parked without timeout, so it is WAITING (even if park returns spuriously, the loop puts the thread back into park).
4. `demo-timed` is sleeping for a positive duration, so it is TIMED_WAITING; main interrupts it so we do not wait 60 seconds.
5. `finally` stops the loop, releases the monitor, unparks the worker, and interrupts the sleeper so the program exits.

**Limitations and QA:**
- `Thread.getState()` is only a **snapshot** and can change immediately after returning. Polling for a state makes the demo more reliable, but does not “freeze” all threads.
- Under severe CPU starvation or thread-creation restrictions, states may miss the deadline; in that case the program throws `IllegalStateException` and output will differ. The four lines above are the expected output in a normal Java 17 environment.
- The demo holds a monitor while the owner calls `await()`, which is **intentionally creating contention for learning**, not an optimal code pattern.
- The spin loop intentionally creates brief CPU load. Do not run infinite stress tests or run it in production to “catch” RUNNABLE.
- Java 17 uses platform threads; if you run a newer JVM with virtual threads, consult the corresponding formats and APIs instead of imposing all HotSpot JDK 17 header details onto newer versions.

### 8.1. Viewing a thread dump while the demo is running

The demo above usually finishes quickly, leaving **too little time** to run `jcmd` in another terminal. There are two ways:
- **Without modifying the program:** run the demo multiple times to observe via `getState()`; check the four verification output lines.
- **Test-environment adjustment:** add `Thread.sleep(10_000L);` **in main after the four print lines and before `finally`** to keep the workers in their established states for 10 seconds, then in another terminal run `jcmd -l` and `jcmd <PID> Thread.print -l`. While main sleeps, main is `TIMED_WAITING`, though worker states can still change between snapshots; verify specifically.

If you want a command without the literal `<PID>`, substitute the actual real PID:
~~~bash
jcmd 12345 Thread.print -l
~~~

Do not let the demo thread hold the monitor indefinitely; `finally` releases it on all valid execution paths.

### 8.2. Connecting to Java management APIs

In Java code, you can read `Thread.State` via `thread.getState()` or observe externally via `ThreadMXBean`:

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
ThreadInfo[] infos = bean.dumpAllThreads(true, true);

for (ThreadInfo info : infos) {
    System.out.printf(
            "%s javaId=%d state=%s lockOwner=%s%n",
            info.getThreadName(),
            info.getThreadId(),
            info.getThreadState(),
            info.getLockOwnerName()
    );
}
~~~

This is an **illustrative snippet** requiring imports for `java.lang.management.ManagementFactory`, `ThreadMXBean`, and `ThreadInfo`; it is not a standalone program. `dumpAllThreads(true,true)` has runtime-dependent cost and lock-collection support; do not call it at very high frequency when a service is under stress.

`ThreadInfo` can provide `getLockName()`, `getLockOwnerId()`, `getLockOwnerName()`, `getStackTrace()`, `getLockedMonitors()`, and `getLockedSynchronizers()` depending on captured info. If owner is `null` or `-1`, it does not mean the whole system has no dependency; it merely says the bean/dump currently has no identified owner.

## 9. Patterns that easily lead to wrong conclusions

### 9.1. “Many WAITING threads = application deadlocked”

A `ThreadPoolExecutor` can have dozens of workers in `WAITING` awaiting `BlockingQueue.take()`. If requests are still being processed and the queue is not backing up, this is an **idle** state. Conversely, even a single request thread WAITING on `Future.get()` with no worker left to produce the result can stall a transaction.

**Check:** thread names, call stacks, queue length, active threads, pending tasks, business logs, and progress by correlation ID.

### 9.2. “BLOCKED means JVM deadlock”

`BLOCKED` merely means waiting on a monitor; brief monitor contention is normal. Deadlock requires a **wait cycle**: A holds monitor X waiting on Y; B holds Y waiting on X, with neither making progress. An owner holding a lock for a long time due to I/O also causes many BLOCKED threads without necessarily forming a cycle/deadlock.

**Check:** owner stack, monitor identity, lock order, multiple dumps, `ThreadMXBean.findDeadlockedThreads()`, or appropriate deadlock detection tools. Do not confuse contention with deadlock.

### 9.3. “RUNNABLE = burning 100% CPU”

A RUNNABLE thread may be in a native socket read/OS wait. Concluding a CPU hotspot requires **per-thread CPU measurement** plus stack sampling. Reading the state line alone is not enough.

### 9.4. “TIMED_WAITING means about to exit”

A thread might call `sleep(60_000)` and immediately sleep again after timing out. It could be holding a monitor or waiting on a dependency with a very long deadline. There is not enough evidence to call it healthy solely from a timed state.

### 9.5. “Threads with the same name belong to the same request”

Thread pools reuse names like `http-nio-8080-exec-7` for **many sequential requests**; a single request can also traverse multiple workers and services. When correlating timelines, use **correlation/trace IDs**, timestamps, and PID/start time; thread name is only execution metadata.

### 9.6. “Seeing a lock name in the dump means we know the root cause”

`- waiting to lock <0x...>` identifies the monitor/object being awaited in the snapshot, but the **root cause** might be the owner doing I/O, a large critical section, thread starvation, or lock ordering. You must find the owner and code path, not just the hex address.

### 9.7. “One snapshot is enough to confirm a hang”

A thread dump is a **point-in-time snapshot**. A 50 ms WAITING can be normal; a RUNNABLE thread at the same frame across 10 dumps plus high CPU suggests a loop. Compare **time, progress, and resources**, rather than reading a single picture like a video.

## 10. Distinguishing lock contention, starvation, deadlock, and I/O wait

| Situation | Visible signs | Next investigation step |
| --- | --- | --- |
| **Intrinsic monitor contention** | Many BLOCKED on same `waiting to lock`; owner holds monitor | Find owner, shrink critical section, avoid I/O while holding monitor |
| **Java monitor deadlock** | Owner/waiter cycle across multiple monitors; no progress | Use deadlock detection and lock graph; fix lock ordering |
| **Ownable synchronizer contention** | WAITING parking in AQS/ReentrantLock | Use `Thread.print -l`, owner info, timing |
| **Thread pool starvation** | Requests WAITING in Future/join; no worker free to run queued task | Check pool active/queue, task dependencies, avoid nested blocking |
| **Native I/O wait** | RUNNABLE or other state depending on stack/JVM; native socket/file frames | OS/JFR I/O events, timeouts, downstream latency |
| **Backoff/polling** | TIMED_WAITING in sleep/parkNanos | Check retries, cadence, rate, and total duration |
| **CPU hot loop** | Continuous RUNNABLE + rising OS thread CPU | Profiler/JFR, CPU time, stack changes |
| **Healthy idle pool** | WAITING in queue take/getTask with empty queue | Confirm throughput/metrics and job queue |

These situations can **coexist**: pool starvation can leave requests WAITING while the underlying worker is BLOCKED on a monitor held by another RUNNABLE thread. Analyzing the **dependency chain** helps locate the primary bottleneck.

## 11. Step-by-step production diagnostic workflow

**Step 1 — Define target and symptom.** Record service, environment, version, host/container, JVM PID, start time, symptom (high CPU, latency, no progress, timeouts), and throughput/queue/GC metrics. Do not run multiple diagnostic commands against the wrong PID.

**Step 2 — Capture a few timestamped thread dumps.** Take enough to compare changes, but not so rapidly as to add overhead or flood files. `Thread.print` has Medium Impact depending on thread count. If the JVM cannot be attached to, use supported management mechanisms and document limitations.

**Step 3 — Group by stack pattern and state.** Do not merely count `RUNNABLE/BLOCKED/WAITING`; group by top frames and business operation. Separate idle framework workers from request-processing threads.

**Step 4 — Map waiting/owner relationships.** For BLOCKED, read `waiting to lock`; locate `locked` on another thread or `lockOwnerName/Id`. For WAITING, check `Object.wait`, `Condition.await`, `LockSupport.park`, `Future.get`, `join`, or queues. For TIMED_WAITING, check timeout/backoff. For RUNNABLE, check CPU/I/O.

**Step 5 — Correlate forward progress.** Is a lock owner completing work? Is the queue draining? Are traces advancing? Which thread CPU time is increasing? Are memory/GC causing long pauses? If multiple snapshots show the same pattern, JFR/profiler and service metrics may be needed.

**Step 6 — Prioritize causes by evidence.** For example, “12 request threads BLOCKED on monitor X, owner holding X during a prolonged DB call” is a far stronger hypothesis than “many BLOCKED so JVM is broken”. If the owner waits only 1 ms, inspect other causes.

**Step 7 — Test fixes in a verified environment.** Narrow synchronized sections, extract blocking calls, fix lock ordering, tune pools/queues, add deadlines/backpressure, avoid nested waits. Re-measure p95/p99, throughput, CPU, blocked thread count, and business outcomes.

**Step 8 — Preserve evidence safely.** Save snapshots with timestamps, PID/start time, JDK version, capture command, selected stacks, and metrics; redact sensitive info. Do not post raw dumps to public channels.

## 12. State reading and interpretation exercises

### Exercise A — Two threads on the same monitor

~~~text
A: TIMED_WAITING at Thread.sleep
   - locked <0xABCD>
B: BLOCKED
   - waiting to lock <0xABCD>
~~~

**Explanation:** A holds the monitor while sleeping, and B waits. Investigate why A sleeps inside a critical section and how long it lasts. B being `BLOCKED` does not by itself prove deadlock because A can wake up and release the monitor.

### Exercise B — Pool workers waiting for tasks

~~~text
worker-1 WAITING at LinkedBlockingQueue.take
worker-2 WAITING at LinkedBlockingQueue.take
queue_size=0
processed_requests increasing
~~~

**Explanation:** likely a normal idle pool. Do not start optimizing synchronization without observing an actual problem.

### Exercise C — Multiple request threads waiting on Future

~~~text
request-1 WAITING at CompletableFuture.join
request-2 WAITING at CompletableFuture.join
async-worker-1 WAITING at CompletableFuture.join
task_queue_size=128
active_workers=1
~~~

**Explanation:** suspect starvation or a chain of interdependent tasks. Determine whether the task `async-worker-1` is waiting on sits inside that very queue; the metrics above are not yet sufficient to assert a deadlock.

### Exercise D — RUNNABLE in native read

~~~text
network-worker RUNNABLE at SocketDispatcher.read0(Native Method)
cpu_delta_ms approximately 0 over sample interval
downstream p99 high
~~~

**Explanation:** CPU is not increasing, so native I/O may be waiting for data; prioritize analyzing network/downstream timeouts rather than a “CPU loop”. Native states depend on implementation, so combine with OS/JFR.

### Exercise E — Timed waiting scheduler

~~~text
retry-timer TIMED_WAITING at Thread.sleep
retry_count increasing quickly
error_rate high
~~~

**Explanation:** a single TIMED_WAITING is not an error, but overall this may be a retry storm; check backoff configuration, jitter, max attempts, and circuit breakers.

## 13. End-of-lesson checklist

When looking at a thread dump, ask in order:

1. **Is this the right JVM?** PID, process start, Java vendor/version, container namespace, and timestamp.
2. **Which names and IDs?** Thread name, Java thread ID, native `nid` if present; do not confuse with `tid=0x...` or request ID.
3. **What is the true state?** Read the `java.lang.Thread.State` line, not just the word “waiting” in the header.
4. **Is RUNNABLE using CPU?** Compare per-thread CPU, sampling, and native/Java frames.
5. **Which intrinsic monitor is BLOCKED waiting on?** `waiting to lock`, who is the owner, and what is the owner doing?
6. **What condition is WAITING waiting on?** Future, queue, park, join, or Object.wait? Is there a thread/event to wake it?
7. **Does TIMED_WAITING have a reasonable timeout/backoff?** Is it holding a monitor? Is there a retry loop or an excessively long deadline?
8. **Is there progress across snapshots?** Compare states/frames/lock ownership with logs and metrics.
9. **Could it be contention, starvation, deadlock, I/O wait, CPU loop, or valid idle?** Do not diagnose by enum alone.
10. **Are remediation actions backed by evidence?** Avoid changing thread pools/GC/timeouts blindly without verification.

**Short takeaway:** **RUNNABLE** means executable in the JVM (not necessarily burning CPU); **BLOCKED** means waiting for a `synchronized` monitor; **WAITING** means waiting without a timeout; **TIMED_WAITING** means waiting with a time limit. To conclude whether a thread is hung or the system is bottlenecked, you must inspect **stack frames, lock owners, wake-up signals, timelines, and resource metrics**, ideally across multiple dumps.

### References

- Oracle Java SE 17, `Thread.State`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html
- Oracle Java SE 17, `ThreadInfo`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html
- Oracle Java SE 17, `ThreadMXBean`: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Oracle JDK 17, `jcmd` and `Thread.print`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle JDK 17, *Troubleshoot Process Hangs and Loops*: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-process-hangs-and-loops.html

Dump samples marked “illustrative” are not stdout from a specific PID. Always prioritize real dumps from the target JVM under investigation, along with timestamps, Java version, and operational evidence.