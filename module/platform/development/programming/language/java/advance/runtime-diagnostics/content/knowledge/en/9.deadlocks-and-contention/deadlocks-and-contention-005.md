# 9.5 Distinguishing Monitor Contention from I/O Waits or Waiting on a Future Result

When a Java service becomes slow or appears “hung,” dozens of request threads can sit idle together in a thread dump. Yet **sitting idle is not a single root cause**: some threads are **waiting to acquire a Java object monitor**, some are **waiting on sockets/disk/databases**, and some are **waiting for a `Future` or `CompletableFuture` result**. These three wait types require different fixes. Resizing a thread pool to cure an overly long monitor hold may only increase the number of blocked threads; increasing timeouts to cure executor starvation sometimes makes the problem worse.

This lesson focuses on **reading evidence from a Java 17+ JVM**, specifically `Thread.State`, stack frames, monitor/lock owners, native I/O indicators, `Future.get()`/`CompletableFuture.join()`, and task dependency chains. The goal is to build a **classification procedure**, avoiding labeling every `WAITING` thread as “deadlock” or concluding “CPU is hot” merely from `RUNNABLE`.

**After this lesson, you should be able to:**

- Identify `BLOCKED (on object monitor)` related to `synchronized`, and find the object monitor and the thread holding it.
- Distinguish `Object.wait()`, `LockSupport.park()`, and `ReentrantLock` from classic Java monitor contention.
- Recognize I/O waits via stack frames in `Socket`, `InputStream.read`, `Selector.select`, `FileChannel`, or client libraries; understand that Java `RUNNABLE` does not mean a thread is burning CPU.
- Recognize async result waits via `FutureTask.get`, `CompletableFuture.join/get`, `ForkJoinPool.managedBlock`, and `LockSupport.park` frames.
- Identify **thread-pool starvation** and logical dependency cycles that JVM deadlock detectors may not report.
- Combine multiple thread dumps with lock ownership, pool metrics, downstream latency, JFR, and UTC timestamps from the **same JVM instance**.
- Propose appropriate remediation for each case without adding extra load or exposing sensitive data.

## 1. Same “Hang” Symptom, Three Root-Cause Categories

Initial triage flow:

```text
                  Request makes no progress
                           │
                   Capture thread dump
                           │
                 Where is the thread?
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
  Java monitor         I/O boundary       Future / async wait
  BLOCKED?             socket/file?        get() / join()?
       │                   │                   │
  Lock identity         Remote endpoint     Future completion
  Lock owner            Timeout/deadline    Executor / producer
  Holder stack          Pool connection     Dependency graph
       │                   │                   │
  Critical section      Downstream/I/O       Queue starvation,
  and hold duration     latency/limit        logical deadlock/timeout
       └───────────────────┼───────────────────┘
                           ▼
               Cross-check multiple snapshots,
                metrics, logs, JFR/traces
```

All three can happen simultaneously. For example, **thread A holds a monitor, then waits on `Future.get()`**, while the task completing the Future needs that exact monitor: in a dump A may appear `WAITING (parking)` at `FutureTask.get`, while B is `BLOCKED` waiting for the monitor. Looking at A or B’s state in isolation misses the dependency cycle.

An essential rule: **Java `Thread.State` is only the JVM’s state at the moment of sampling**, not a final diagnosis of the slow resource. Stack frames tell which execution path the thread is on; lock-owner info, metrics, and wait chains explain *why*.

## 2. The Six Java States and Diagnostic Questions

Java 17 has six `Thread.State` values:

| State | Meaning in the Java VM | Investigation Hint |
| --- | --- | --- |
| `NEW` | `Thread` object has not called `start()` yet | Not a live worker handling requests |
| `RUNNABLE` | Thread is running/eligible to execute per the VM | May be computing on CPU or waiting on OS I/O; must read stack |
| `BLOCKED` | Waiting to acquire/reacquire a Java object monitor to enter `synchronized` or reenter after `wait` | Look for `- waiting to lock` and lock owner |
| `WAITING` | Waiting without timeout for another thread’s action | `Object.wait()`, `LockSupport.park()`, `Thread.join()`; read callers |
| `TIMED_WAITING` | Waiting with a timeout / bounded duration | `sleep`, timed `wait/join`, `parkNanos`, various timed waits |
| `TERMINATED` | Thread has exited | Usually absent from a live JVM thread dump |

**Do not map one-to-one to Linux states `R/S/D`.** A Java `RUNNABLE` thread can be inside a native socket read while the OS thread is sleeping. Conversely, Java `WAITING` can be a completely normal idle pool. <u>State + top frames + caller frames + lock data + time together form evidence.</u>

### 2.1. Quick Identification Matrix

| Indicator in Dump | Initial Possibility | Missing Evidence Needed |
| --- | --- | --- |
| `BLOCKED (on object monitor)`, `- waiting to lock <id>` | Monitor contention | Which thread has `- locked <id>`, and for how long? |
| `WAITING (on object monitor)` at `Object.wait` | Waiting for notify/condition | Who notifies? Has predicate/condition changed? |
| `WAITING (parking)` at `AbstractQueuedSynchronizer` | Lock/condition/semaphore/future/pool queue | Is the actual caller `lock`, `await`, or `getTask`? |
| `RUNNABLE` with `SocketDispatcher.read0` / `SocketInputStream.socketRead0` | Network read wait or native work | Endpoint, deadline, byte count, OS socket state |
| `RUNNABLE` with `EPoll.wait` / `Selector.select` | Event loop waiting for I/O readiness | Event-loop progress, backlog, select timeout |
| `WAITING` at `FutureTask.awaitDone` / `CompletableFuture.waitingGet` | Waiting for async result | Which executor runs the producer/task, and is it running? |
| `TIMED_WAITING` at timed `Future.get` | Bounded wait up to timeout | Remaining timeout, overall request deadline, producer progress |
| Many request threads in `join`, pool active=max and queue growing | Executor starvation / async bottleneck | Dependency graph: is the completing task in the occupied pool itself? |

Specific frame names can change across JDKs, I/O libraries, and runtime implementations. Never write a parser asserting every JDK 17 must print exact names like `SocketDispatcher.read0` or `CompletableFuture.waitingGet`.

## 3. Monitor Contention: Traces of `synchronized`

### 3.1. What Is an Object Monitor?

Every Java object can serve as a monitor for `synchronized (obj)` or a `synchronized` method. At any instant, only one thread owns that monitor to execute the critical section; other threads wishing to enter must wait. In a Java thread dump, a **thread waiting to enter a monitor** typically has state:

```text
java.lang.Thread.State: BLOCKED (on object monitor)
    at com.example.InventoryCache.lookup(InventoryCache.java:91)
    - waiting to lock <0x0000000700a01000> (a java.lang.Object)
    at com.example.OrderService.reserve(OrderService.java:54)
```

This is a **synthetic HotSpot sample**. The `<0x...>` field is the object monitor identity in the matching dump, **not a thread ID**, and not a native `nid` address. File/line names and formatting vary by JDK version.

What can be concluded: at snapshot time, the thread had not acquired a monitor to proceed. What **cannot** yet be concluded: that the monitor will be held forever, that this is a deadlock, or whether it is merely microsecond-level transient contention. You must find the thread owning that monitor.

### 3.2. Finding the Owner of the Same Lock

The same dump may contain another thread:

```text
"cache-refresh" #52 ...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.base/java.lang.Thread.sleep(Native Method)
    at com.example.InventoryCache.refresh(InventoryCache.java:120)
    - locked <0x0000000700a01000> (a java.lang.Object)
```

If identity `<0x0000000700a01000>` matches, thread `cache-refresh` holds the monitor that `OrderService.reserve` is waiting for. A very easy mistake: **`Thread.sleep` does not release held monitors**. Thus a sleeping thread can still block many request threads.

A sound investigation path:

1. Confirm the exact same object monitor identity **within the same dump**.
2. Inspect the owner’s stack to locate the `synchronized` critical section.
3. Read the source around the owner’s frames: is there a sleep, synchronous network call, database query, lock held across a loop, or lock held before `Future.get`?
4. Capture additional snapshots while symptoms persist, keeping collection impact bounded.
5. Cross-check blocked time/blocked count, request latency, and lock contention events.
6. Fix **lock hold duration or ownership structure**, not just increasing waiting thread counts.

Monitor identities can differ across process lifetimes or even across two dumps; never treat them as cluster-wide keys. Java lock-owner/monitor frames also depend on thread dump verbosity and JVM optimizations.

### 3.3. `BLOCKED` Is Not Every Kind of Lock Contention

`ReentrantLock.lock()` typically relies on `AbstractQueuedSynchronizer` and `LockSupport.park`. A thread waiting on a `ReentrantLock` may appear as **WAITING (parking)** rather than `BLOCKED`. `Condition.await`, `Semaphore.acquire`, `CountDownLatch.await`, and `FutureTask.get` can also show `WAITING` or `TIMED_WAITING`. Therefore:

- `BLOCKED` is a fairly specific sign of **Java monitor entry**.
- **Absence of `BLOCKED`** does not rule out `java.util.concurrent` contention.
- `WAITING (parking)` alone **does not** identify the wait type; read frames below `Unsafe.park`/`LockSupport.park`.
- A `WAITING` thread can still **hold another monitor or lock**, blocking other threads.

### 3.4. `Object.wait` Differs from Waiting to Enter a Monitor

`Object.wait()` can only be called while the thread owns that object’s monitor. Upon entering wait, the thread **releases the monitor on the waited object**, waiting for `notify`/`notifyAll`, interrupt, or wakeup conditions; afterward it must reacquire the monitor before returning to Java code inside the critical section. It **does not automatically release any other monitors** the thread holds.

A sample:

```text
"producer" ...
   java.lang.Thread.State: WAITING (on object monitor)
    at java.base/java.lang.Object.wait(Native Method)
    at com.example.Queue.take(Queue.java:67)
    - waiting on <0x0000000700a02000> (a java.lang.Object)
```

This is not evidence that the thread is **`BLOCKED` trying to enter** the monitor. It is waiting for a **condition/notify**. Once notified, if it cannot immediately reacquire the lock, the thread may transition to `BLOCKED`. Analysis must separate “waiting to be notified” from “waiting to enter the monitor.”

**Safe practice with wait/notify:** check predicates in a `while` loop, never `if`, because spurious wakeups can occur; avoid notifying the wrong object or missing condition updates in concurrency designs. When higher-level concurrency primitives fit, prefer `BlockingQueue`/`Condition`/`CompletableFuture` with clear semantics over building complex custom `wait/notify` protocols.

## 4. How Monitor Contention Can Turn into Starvation

A code path of the form:

```java
// Illustrative snippet inside a method, not a standalone program.
synchronized (cacheLock) {
    refreshFromRemoteService(); // I/O may take several seconds.
    updateSharedCache();
}
```

All request threads needing `cacheLock` must queue up while the owner **waits on I/O**. In the same dump:

- The owner may be `RUNNABLE` inside a native socket read.
- Many other request workers are `BLOCKED` waiting on one monitor ID.
- JVM CPU may be low while p99 remains high.
- The **immediate** cause for the waiters is monitor contention; the cause **prolonging monitor hold time** is slow I/O.

Do not classify the entire incident as “monitor” *or* “network” when **both form a causal chain**. Fixes typically involve moving I/O outside the critical section or using snapshots/immutable state, alongside timeouts, circuit breakers, and proper synchronization design.

## 5. I/O Wait: Why `RUNNABLE` Can Mislead

### 5.1. Blocking Socket Read

A common HotSpot/JDK 17 pattern when a request calls a dependency:

```text
"http-worker-17" #70 ...
   java.lang.Thread.State: RUNNABLE
    at java.base/sun.nio.ch.SocketDispatcher.read0(Native Method)
    at java.base/sun.nio.ch.SocketDispatcher.read(SocketDispatcher.java:...)
    at java.base/sun.nio.ch.NioSocketImpl.tryRead(NioSocketImpl.java:...)
    at java.base/java.net.Socket$SocketInputStream.read(Socket.java:...)
    at com.example.http.Client.fetch(Client.java:84)
    at com.example.web.OrderController.submit(OrderController.java:37)
```

This is a **stack-style example**: line numbers/frames vary by JDK, HTTP/TLS driver, library, and socket implementation. Another implementation might show `SocketInputStream.socketRead0` or different NIO/Netty frames.

**`RUNNABLE` does not confirm high CPU.** The Java VM may classify a thread inside a native I/O method as `RUNNABLE` while the OS puts it to sleep awaiting data. Inspect OS thread CPU time/TID, socket states, network timeouts, dependency latency, bytes received, and connection counts to know whether CPU is truly busy.

### 5.2. Selector/Event Loop Waiting for I/O

A reactor/Netty/Java NIO worker may show:

```text
java.lang.Thread.State: RUNNABLE
    at java.base/sun.nio.ch.EPoll.wait(Native Method)
    at java.base/sun.nio.ch.EPollSelectorImpl.doSelect(EPollSelectorImpl.java:...)
    at java.base/java.nio.channels.Selector.select(Selector.java:...)
```

This may be an **intentionally idle event loop**, not a “CPU-hogging infinite loop.” Check:

- Is epoll/select genuinely blocking awaiting events?
- Does the native TID’s CPU time climb sharply or barely move?
- Event-loop backlog, queue size, completed tasks, and dispatch duration?
- Is there busy-spinning (select returning immediately over and over), CPU-heavy callbacks, or an I/O handler blocking the event loop too long?
- Could client-observed latency come from downstream or queueing before the event loop?

An async framework can also offload I/O waits onto **tasks/callbacks or futures**: the event-loop thread waits for readiness while another request thread waits for the result. Never assign one fixed state to “I/O wait” across all libraries.

### 5.3. File/Disk I/O and Native Calls

Frames like `FileInputStream.readBytes`, `FileChannelImpl.read`, filesystem providers, database drivers, or JNI native methods can indicate a thread on an I/O path. A Linux thread may be in `D` uninterruptible sleep, yet Java state still will not display `IO_WAITING` — Java `Thread.State` **has no such enum**.

To investigate, cross-check:

- I/O latency/IOPS/disk queue info;
- connection pool wait vs. socket read vs. TLS handshake;
- SQL/query latency from database metrics, tracing, active/pending pool stats;
- OS thread state, `/proc`, or read-only tools when authorized;
- network latency/retransmissions, DNS, timeouts/deadlines;
- JVM heap/GC/safepoints if abnormal durations coincide with pauses.

**Do not conclude the backend is slow** merely from seeing a JDBC frame: it could be waiting on the connection pool, a transaction lock, a network read, driver synchronization, or application-level backpressure. Read full caller frames and dependency metrics.

### 5.4. I/O Timeouts Are Not Future Timeouts

`Socket.setSoTimeout(...)` bounds a blocking socket read per API semantics, not the total deadline of a business transaction. `HttpClient`, JDBC drivers, pool acquisition, and RPC frameworks have multiple distinct timeouts: connect, handshake, read, request/call, and queue/pool acquisition.

A request can have three stages:

```text
Wait for pool connection (500 ms)
→ connect (300 ms)
→ read response (3 s)
→ retry (2 times)
→ total latency exceeds SLA
```

A thread dump only sees **the current stage**. Diagnostics must account for total deadlines, retry budgets, and dependency chains, not just one call’s socket timeout configuration.

### 5.5. Evidence Distinguishing I/O Wait from CPU Hotspot

| Observation | Suggests I/O Wait | Suggests CPU-Heavy |
| --- | --- | --- |
| Java state | May be `RUNNABLE`/native or `WAITING` depending on framework | Typically `RUNNABLE` in application methods |
| Stack | `Socket.read`, `FileChannel.read`, `Selector.select`, driver calls | Java loops, transforms, serialization, crypto, matching |
| CPU time of same OS TID across 2 samples | Rises little when genuinely blocked | Rises fast proportional to interval |
| Dependency latency | May be elevated | May be normal |
| JFR | Significant `SocketRead`/`FileRead` durations or thread parks | Execution samples concentrated in code |
| First step | Verify endpoints, timeouts, queues, I/O latency | CPU profiling and optimizing hot paths |

Both CPU work and I/O can occur in a single request. One `Thread.State` reading is insufficient for quantification.

## 6. Future Wait: Waiting for Another Task’s Result

### 6.1. What Does `Future.get()` Wait For?

`Future<V>` represents the result of an asynchronous computation. With an un-timed `Future.get()`, the caller **waits if necessary for the task to complete**, then receives the result or corresponding exception/cancellation. `get(timeout, unit)` waits at most the specified time and may throw `TimeoutException`.

An API example (snippet inside a method):

```java
Future<String> result = executor.submit(() -> remoteLookup());

try {
    String value = result.get(2, TimeUnit.SECONDS);
    use(value);
} catch (TimeoutException ex) {
    // Handle deadline/timeout at the application layer.
}
```

`executor`, `remoteLookup`, and `use` are assumed to exist; this is **not a standalone compilable program**. `get` can also throw `InterruptedException` and `ExecutionException`; the example omits handling them to emphasize timeouts. In real code, handle all three properly, restore interrupt status when appropriate, and address cancellation per policy.

### 6.2. Common Stack When Waiting on `FutureTask.get`

A HotSpot sample:

```text
"request-worker-8" #87 ...
    java.lang.Thread.State: WAITING (parking)
     at java.base/jdk.internal.misc.Unsafe.park(Native Method)
     at java.base/java.util.concurrent.locks.LockSupport.park(LockSupport.java:...)
     at java.base/java.util.concurrent.FutureTask.awaitDone(FutureTask.java:...)
     at java.base/java.util.concurrent.FutureTask.get(FutureTask.java:...)
     at com.example.OrderService.create(OrderService.java:109)
```

Reading bottom-up for **why it is waiting**: business method `OrderService.create` called `FutureTask.get`, and internally `FutureTask` uses `awaitDone`/`park` to wait for task completion. The thread can be `WAITING` even though **there is no Java object monitor contention at all**.

In logs/metrics, check:

- Where was the Future created, and who submitted it?
- Which executor runs the producer?
- Is the task pending, running, completed, failed, or cancelled?
- Executor queue, active threads, completed task count, rejected tasks?
- Is the running task itself waiting on I/O, a monitor, or another Future?
- Is the caller holding a lock before calling `get`?

There is no default “producerThread” field stored inside a Future object. The consumer’s thread dump reveals the **wait point**, without guaranteeing identification of the producer thread unless correlated via traces/task IDs or scheduler metadata.

### 6.3. CompletableFuture `join`/`get`

`CompletableFuture<T>` implements `Future<T>` and `CompletionStage<T>`. Frames may include `CompletableFuture.waitingGet`, `CompletableFuture$Signaller.block`, `ForkJoinPool.managedBlock`, and `LockSupport.park`. Exact names and stack details vary by JVM, so look for **`join` or `get` call chains in caller frames**.

Notable differences:

| API | Timeout | Primary Exceptions | Wait Signature |
| --- | --- | --- | --- |
| `Future.get()` | No | `InterruptedException`, `ExecutionException`, `CancellationException` | Typically `WAITING` if not done |
| `Future.get(t, unit)` | Yes | Adds `TimeoutException` | May be `TIMED_WAITING` |
| `CompletableFuture.join()` | No | `CompletionException` (unchecked) on exceptional completion, `CancellationException` | Typically `WAITING`/parking if not done |
| `CompletableFuture.get()` | No | `InterruptedException`, `ExecutionException` | May be `WAITING` |
| `CompletableFuture.orTimeout(t,unit)` | Changes future state on expiry | Future completes exceptionally with `TimeoutException` | **Does not automatically guarantee** background work is canceled |
| `CompletableFuture.completeOnTimeout(value,t,unit)` | Supplies fallback value on timeout | Subject to completion/cancellation races | Does not prove underlying work stopped |

`Future.isDone() == true` means the computation **completed in Future terms**—which can be success, failure, or cancellation; it does **not** mean success. `join()` does not declare `InterruptedException`, so it does not handle interrupts identically to `get()`; check exact API and executor interrupt/cancellation policies.

### 6.4. `WAITING` Does Not Prove the Future Will Never Complete

A thread dump is a snapshot at one instant. The Future may complete immediately afterward, or the consumer may not yet have been resumed by the scheduler. Even after an HTTP-layer timeout, a submitted task can keep running unless cancellation is properly implemented.

If many request threads are waiting on `get`, before concluding “Futures aren’t running,” inspect pool size/queue, submission failures, callback executors, deadlock cycles, producer native I/O, and timing.

## 7. Thread-Pool Starvation: Hanging Without a Monitor Deadlock

### 7.1. A Worker Waiting on an Unstarted Task

Suppose an executor has **one worker**. Task A runs on the worker, submits task B to **the same executor**, and then calls `B.get()`. B sits in the queue, unable to run because the sole worker is occupied by A while A waits for B. This is **thread-pool starvation** or scheduling dependency cycle, needing no two monitors waiting on each other.

```text
SingleThreadExecutor (1 worker)
                │
                ▼
           task A running
                │
          submit task B
                │
                ▼
          futureB.get()
                │
              WAITING
                │
                ▼
     B queued, no free worker
                │
                └── B cannot complete yet
```

Crucially: `ThreadMXBean.findDeadlockedThreads()` may return `null` because there is no JVM-recognizable monitor/ownable-synchronizer cycle. **`null` does not rule out starvation or logical deadlocks** across Futures, message queues, callbacks, semaphores, and remote services.

### 7.2. Signs in Thread Dumps and Executor Metrics

- One or more pool workers at `FutureTask.get`, `CompletableFuture.join`, or `LockSupport.park`.
- `activeCount` near `maximumPoolSize`; queue size grows or `completedTaskCount` stops growing.
- Tasks are **submitted by the workers themselves** back into the same pool.
- No `BLOCKED` threads or Java monitor deadlock reports.
- Request timeouts climb while thread count does not necessarily rise.
- CPU may be low because workers are waiting, even while the queue is full.

A large queue alone does not prove starvation: it could be a traffic burst or slow downstream. You need dependency edges, worker utilization, and queue wait times.

### 7.3. Callback / CompletableFuture Chains Can Also Form Wait Cycles

An async flow can accidentally block:

```java
// Conceptual snippet, incomplete:
CompletableFuture<String> a = loadAsync();
CompletableFuture<String> b = a.thenApply(value -> transform(value));
String result = b.join();  // Blocks current thread while b has not completed.
```

`loadAsync` and `transform` are undefined here. This pattern is not automatically wrong: `join` on an orchestration thread can be acceptable. However, calling `join` **inside the thread pool used to run dependent stages** can starve a small pool or bounded queue.

A less blocking pattern:

```java
// Snippet in code that already has async operations:
CompletableFuture<Result> result =
        fetchAsync()
            .thenCompose(data -> enrichAsync(data))
            .thenApply(this::toResult);
```

`fetchAsync`, `enrichAsync`, `toResult`, and type `Result` are assumed to exist; this is not a standalone file. `thenCompose` expresses an async dependency without forcing a worker to wait on `get` inside a critical section; however, it **does not** by itself guarantee no blocking occurs inside callbacks or executor implementations.

### 7.4. Do Not Fix Starvation Simply by Increasing Pool Size

Increasing threads from 1 to 2 may let a simple A→B example pass, yet only postpone failure under higher traffic: N workers all submit N tasks and wait together. Structural fixes usually include:

- never blocking on `Future.get`/`join` inside the same bounded pool that runs the producer;
- designing async composition or properly isolating pools by blocking vs. CPU characteristics;
- avoiding circular dependencies across tasks/requests;
- setting queue bounds, rejection policies, deadlines, timeouts, and observable cancellation;
- validating backpressure, workload, and thread-pool sizing through measurement;
- minimizing time holding Java monitors when awaiting Futures/I/O.

## 8. Decision Table: Monitor, I/O, or Future?

| Indicator | Monitor Contention | I/O Wait | Future Wait |
| --- | --- | --- | --- |
| Typical Java state | `BLOCKED` | May be `RUNNABLE` in native read or `WAITING` per library | `WAITING`/`TIMED_WAITING` |
| Characteristic top frames | `- waiting to lock` entering `synchronized` | Socket/file/selector/driver/native read | `FutureTask.get`, `CompletableFuture.join/get` |
| Target to locate | Monitor ID + owning thread | Endpoint/file/connection/timeout | Future producer + executor/dependency |
| Helpful metrics | Blocked count/time, lock owner chains, JFR monitor enter | `SocketRead`/`FileRead` durations, pool waits, downstream latency | Active/queue/completed tasks, dependency traces |
| Waiter CPU | Usually low when `BLOCKED` | Usually low during blocking I/O, though state may be `RUNNABLE` | Usually low when parked |
| Caught by deadlock detector? | Can detect monitor cycles | Usually not | Usually not |
| Structural fixes | Shrink lock hold time, move I/O/await out of critical sections | Timeouts/deadlines, pools, downstream fixes, backpressure | Async composition, executor graph, timeouts, bounded queues |
| Interpretation risk | A `BLOCKED` thread may be transient | `RUNNABLE` does not equal CPU-bound | `WAITING` does not equal monitor deadlock |

**A single thread can participate in chained causes:** A holds a monitor while waiting on a Future; producer B waits on a database; requests C wait on A’s monitor. The root latency may be a slow database *amplified* by monitor design, rather than purely “database” or purely “lock.”

## 9. Taking Thread Dumps Safely on Java 17

### 9.1. `jcmd Thread.print -l`

On HotSpot JDK 17, illustrative commands (PID `12345` must be the verified target JVM with proper permissions):

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 help Thread.print
jcmd 12345 Thread.print -l
```

`-l` requests `java.util.concurrent` lock information when supported by the JVM. Per JDK documentation, `Thread.print` has **Medium** impact depending on thread count: capturing too many dumps on a heavily loaded JVM can affect latency.

Before capturing:

1. Lock down the service, node/container ID, PID **in the right namespace**, JVM start time, and build revision.
2. Record UTC timestamp and incident window.
3. Check existing metrics first; capture dumps purposefully.
4. Take 2–3 snapshots a few seconds apart while symptoms persist **and impact budget permits**.
5. Save files only in authorized locations with restricted read permissions and retention limits.
6. Do not dump tightly just to catch a 10 ms spike; JFR/sampling profilers are usually better suited.

Example saving a dump to a protected directory:

```bash
jcmd 12345 Thread.print -l > thread-20261029T081000Z.txt
```

This only redirects the tool’s stdout in the terminal running the command; it will not necessarily create a file inside a target container. The filename is illustrative, **not a real dump**. In containers, `jcmd -l` does not necessarily see JVMs in other namespaces.

### 9.2. Reading Multiple Snapshots to Separate Causes

An analytical pattern:

```text
t0: 27 request threads BLOCKED on monitor M
t0: owner "cache-refresh" in Socket.read

t0+5s: 43 request threads BLOCKED on M
t0+5s: owner still in Socket.read, no progress

t0+10s: 52 request threads BLOCKED on M
t0+10s: owner transitions to timeout/retry

Cross-check: client timeouts, backend latency, p99, monitor contention.
```

This is a **hypothetical scenario**. It suggests slow I/O prolonging monitor ownership, causing `BLOCKED` requests to pile up. Confirming requires matching the exact JVM/monitor, thread identities, event timestamps, and code holding the monitor on the I/O path.

For Future starvation:

```text
t0: 8 pool workers at FutureTask.get, queue size=300
t0+5s: 8 workers still at FutureTask.get, queue size=600
t0+10s: active=8, completedTaskCount barely increasing

Dependency analysis: are the tasks that will complete the awaited Future
sitting in the very queue that has no free worker?
```

`Thread.State.WAITING` alone does not answer the final question. You need submission/callback code, task IDs, or executor tracing.

### 9.3. Never Read One Stack Frame Out of Context

Each thread entry typically looks like:

```text
"request-worker-17" #77 ... tid=0x... nid=0x...
  java.lang.Thread.State: WAITING (parking)
      at jdk.internal.misc.Unsafe.park(Native Method)
      at java.util.concurrent.locks.LockSupport.park(...)
      at java.util.concurrent.FutureTask.awaitDone(...)
      at java.util.concurrent.FutureTask.get(...)
      at com.example.PaymentService.process(PaymentService.java:144)
```

`Unsafe.park` at the top **does not** mean “the JVM hung inside Unsafe.” What helps is the caller chain from `PaymentService.process` to `FutureTask.get`, as that explains why the thread entered park. Locate the task producer and completion path next. Likewise, `Socket.read` must be traced back to the service/client call in caller frames.

## 10. `ThreadMXBean` API: Lock Owner, Thread Info, CPU/Blocked Time

Java 17 provides `ManagementFactory.getThreadMXBean()` to inspect managed Java threads. This standard API returns Java thread ID/state/stack/locks, **not an “I/O_WAITING” enum or a portable native thread ID**.

### 10.1. Fetching Info for One Thread

```java
java.lang.management.ThreadMXBean mx =
        java.lang.management.ManagementFactory.getThreadMXBean();

long javaId = Thread.currentThread().getId();
java.lang.management.ThreadInfo info =
        mx.getThreadInfo(javaId, 20);

if (info != null) {
    System.out.println(info.getThreadName());
    System.out.println(info.getThreadState());
    System.out.println(info.getLockOwnerName());
}
```

This is a snippet inside a method. `ThreadInfo.getLockOwnerName()` can be `null` if no owner is known; never use `null` to conclude “no dependency.” `getThreadInfo(id, maxDepth)` fetches up to the requested number of stack frames. If the thread terminates between calls, `getThreadInfo` can return `null`.

### 10.2. Checking Monitor and Ownable Synchronizer Support

```java
boolean monitors = mx.isObjectMonitorUsageSupported();
boolean synchronizers = mx.isSynchronizerUsageSupported();

java.lang.management.ThreadInfo[] snapshot =
        mx.dumpAllThreads(monitors, synchronizers);
```

This uses `mx` declared above, and is not a standalone program. `dumpAllThreads` has overhead, especially with many threads. `getLockedMonitors()` and `getLockedSynchronizers()` help reveal ownership when supported by the VM and dump flags, yet do not automatically turn every `Future`/I/O dependency into a graph.

If you only need a subset of threads, use `getThreadInfo(ids, depth)` and metrics before dumping the entire JVM. Avoid logging full stack traces at `INFO` level in production.

### 10.3. `getBlockedTime` and `getWaitedTime`

`ThreadInfo.getBlockedCount()` and `getBlockedTime()` relate to monitor wait events; `getWaitedCount()` and `getWaitedTime()` relate to wait mechanisms as defined by the API. **Do not** interpret these fields as separately measured “network wait time” or “Future wait time.”

Thread contention monitoring must be supported and enabled to obtain reliable elapsed blocked/waited times:

```java
if (mx.isThreadContentionMonitoringSupported()
        && mx.isThreadContentionMonitoringEnabled()) {
    // Blocked/waited time can be read from ThreadInfo;
    // you must still understand the limits and scope of the counters.
}
```

Enabling via `setThreadContentionMonitoringEnabled(true)` is a **managed JVM state change** that can increase overhead. Do so only per policy after weighing impact; never enable it blindly in production just because you saw `-1`.

### 10.4. Deadlock Detection Has Finite Scope

- `findMonitorDeadlockedThreads()`: detects wait cycles on **Java object monitors**.
- `findDeadlockedThreads()`: can include ownable synchronizers if supported by the VM.
- `null` means no deadlock was found under **the lock model recognized by the API at check time**.

**It does not detect Future starvation, socket/DB waits, distributed locks, or logical dependency cycles through callbacks.** A pool whose workers all wait on `Future.get()` while producer tasks sit in its queue can hang indefinitely while the deadlock API returns `null`.

Never “fix a deadlock” by force-stopping threads. `Thread.stop` is unsafe and long deprecated; arbitrarily breaking monitors or killing tasks can corrupt state. Fix the dependency graph and perform safe rollback.

## 11. Standalone Java 17+ Program: Monitor BLOCKED and Future WAITING

This program **intentionally creates both wait types**, uses latches to synchronize observation timing, and then releases all threads. No network connection or external service is required. The goal is to demonstrate that `synchronized` makes a contender **`BLOCKED`**, whereas waiting on an uncompleted `CompletableFuture.join()` typically puts a consumer in **`WAITING (parking)`** on HotSpot/JDK 17.

Save the file **`MonitorFutureStatesDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class MonitorFutureStatesDemo {
    private static void awaitState(Thread thread, Thread.State expected)
            throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        while (thread.getState() != expected) {
            if (System.nanoTime() >= deadline) {
                throw new IllegalStateException(
                    thread.getName() + " did not enter " + expected
                    + "; actual=" + thread.getState());
            }
            Thread.sleep(5);
        }
    }

    public static void main(String[] args) throws Exception {
        Object monitor = new Object();
        CountDownLatch ownerEntered = new CountDownLatch(1);
        CountDownLatch releaseOwner = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            synchronized (monitor) {
                ownerEntered.countDown();
                try {
                    releaseOwner.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "monitor-holder");

        Thread contender = new Thread(() -> {
            synchronized (monitor) {
                // Only runs after owner releases the monitor.
            }
        }, "monitor-contender");

        owner.start();
        if (!ownerEntered.await(3, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Owner did not start");
        }
        contender.start();

        try {
            awaitState(contender, Thread.State.BLOCKED);
            ThreadMXBean mx = ManagementFactory.getThreadMXBean();
            ThreadInfo info = mx.getThreadInfo(contender.getId(), 10);

            System.out.println("monitor.state=" + info.getThreadState());
            System.out.println("monitor.owner="
                    + info.getLockOwnerName());
        } finally {
            releaseOwner.countDown();
            owner.join(3000);
            contender.join(3000);
        }

        CompletableFuture<String> result = new CompletableFuture<>();
        CountDownLatch consumerReady = new CountDownLatch(1);
        AtomicReference<String> observed = new AtomicReference<>();

        Thread consumer = new Thread(() -> {
            consumerReady.countDown();
            observed.set(result.join());
        }, "future-consumer");

        consumer.start();
        if (!consumerReady.await(3, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Consumer did not start");
        }

        try {
            awaitState(consumer, Thread.State.WAITING);
            System.out.println("future.state=" + consumer.getState());
            System.out.println("future.done.before=" + result.isDone());
        } finally {
            result.complete("ok");
            consumer.join(3000);
        }
        System.out.println("future.value=" + observed.get());
    }
}
```

Compile and run with JDK 17+:

```bash
javac MonitorFutureStatesDemo.java
java MonitorFutureStatesDemo
```

**Expected stdout on successful execution on HotSpot/OpenJDK 17** (without timeouts or debugger interference):

```text
monitor.state=BLOCKED
monitor.owner=monitor-holder
future.state=WAITING
future.done.before=false
future.value=ok
```

**Detailed explanation:**

1. `owner` acquires the monitor first and waits on `releaseOwner` while **still holding the monitor**. `contender` becomes `BLOCKED` at `synchronized`.
2. `ThreadMXBean.getThreadInfo` observes `BLOCKED` and owner named `monitor-holder` in environments supporting monitor ownership.
3. On `releaseOwner.countDown()`, `owner` releases the monitor and `contender` finishes; the example leaves no threads hung forever.
4. `consumer` calls `CompletableFuture.join()` on an uncompleted future; HotSpot 17 typically places it in `WAITING (parking)`, **not `BLOCKED` waiting on a Java monitor**.
5. `result.complete("ok")` releases `consumer`; the observed value is `ok`.
6. State polling loops are for demo synchronization only; they can time out on very slow VM/platform scheduling or different implementations. Never turn `getState()` polling into a production framework.
7. On other JVMs, `getLockOwnerName()` or the specific state of `join` may differ; hence output is stated **conditionally** on supporting environments rather than promised invariant across every VM.

This is a **complete runnable program**. It mutates state only on local threads it creates and does not attach to any external JVM. Never run demo code against a shared monitor of a production application.

## 12. Standalone Java 17+ Program: Future Starvation with Safe Timeout

This example deliberately creates a wait cycle inside `newSingleThreadExecutor`, yet **uses a timeout** so the program exits cleanly rather than hanging forever. Key point: there is only one worker; task A submits task B to **the same pool**, then A waits for B. B cannot run until A exits.

Save the file **`SingleWorkerFutureStarvationDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class SingleWorkerFutureStarvationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService one = Executors.newSingleThreadExecutor();
        try {
            Future<String> outer = one.submit(() -> {
                Future<String> inner = one.submit(() -> "inner-completed");
                try {
                    inner.get(200, TimeUnit.MILLISECONDS);
                    return "unexpected";
                } catch (TimeoutException expected) {
                    return "timeout-waiting-for-queued-inner";
                }
            });

            String result = outer.get(5, TimeUnit.SECONDS);
            System.out.println("outer=" + result);
        } finally {
            one.shutdown();
            if (!one.awaitTermination(5, TimeUnit.SECONDS)) {
                one.shutdownNow();
            }
        }
    }
}
```

Compile/run:

```bash
javac SingleWorkerFutureStarvationDemo.java
java SingleWorkerFutureStarvationDemo
```

**Exact stdout when running successfully without external interruption:**

```text
outer=timeout-waiting-for-queued-inner
```

Why is this not a “Java monitor deadlock”?

- `outer` is running on the sole worker; `inner` **was submitted and sits in the executor queue**.
- `outer` calls `inner.get(200, ...)` and waits 200 ms. It may appear in `TIMED_WAITING`/parking at snapshot time.
- There is no schedule order allowing `inner` to start **before `outer` releases the worker**. Thus timeout is an inevitable consequence of the single-worker design, not a bug in `Future.get`.
- After timeout, `outer` returns, freeing the worker to run `inner`; `shutdown`/`awaitTermination` completes.
- Replacing `get(200,...)` with an untimed `get()` would hang the example forever. **Never do that in environments requiring safety.**
- `findDeadlockedThreads` may not detect the problem, because the cause lies in **executor scheduling/dependency**, not a Java monitor cycle.

**Solution:** do not block a worker waiting on a task enqueued into the same bounded pool; pass results via async composition or use a properly structured dependent executor architecture. Adding a worker may unblock a small case, yet does not guarantee handling workloads where N tasks simultaneously wait on N other tasks.

## 13. Standalone Java 17+ Program: I/O Read on Loopback

This example starts a server socket on the practice machine’s **loopback** interface, lets a reader thread wait for a byte, and then has a client send data. It illustrates that a thread can be blocked in `InputStream.read` while its captured Java state depends on OS/implementation, with **no standard `I/O_WAITING` state**.

Save the file **`LoopbackIoWaitDemo.java`**:

```java
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class LoopbackIoWaitDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        AtomicInteger received = new AtomicInteger(-1);
        AtomicReference<IOException> error = new AtomicReference<>();
        CountDownLatch accepted = new CountDownLatch(1);

        try (ServerSocket listener = new ServerSocket(0, 1, loopback)) {
            Thread reader = new Thread(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(3000);
                    accepted.countDown();
                    received.set(peer.getInputStream().read());
                } catch (IOException ex) {
                    error.set(ex);
                }
            }, "socket-reader");

            reader.start();

            try (Socket client = new Socket(loopback,
                    listener.getLocalPort())) {
                if (!accepted.await(2, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("No connection accepted");
                }

                // Read state while peer has not sent a byte yet.
                Thread.sleep(50);
                System.out.println("io.reader.state.sample="
                        + reader.getState());

                client.getOutputStream().write(65); // ASCII 'A'
            }

            reader.join(4000);
            if (reader.isAlive()) {
                throw new IllegalStateException("Reader still running");
            }
            if (error.get() != null) {
                throw new IllegalStateException("Reader error", error.get());
            }
            System.out.println("io.received.byte=" + received.get());
        }
    }
}
```

Compile/run on JDK 17+ on a machine allowing loopback binding:

```bash
javac LoopbackIoWaitDemo.java
java LoopbackIoWaitDemo
```

**Illustrative output** on a HotSpot/Linux setup with blocking socket read:

```text
io.reader.state.sample=RUNNABLE
io.received.byte=65
```

`io.reader.state.sample=...` is a **live value** that can differ due to scheduler/JDK/socket implementations; `RUNNABLE` is not guaranteed in every environment. `io.received.byte=65` is determined by the byte the client sends **if it runs successfully**. The example calls no external services and sets a read timeout to avoid hanging indefinitely.

Key point: even when `reader` reports `RUNNABLE`, we **know** it is on the I/O path waiting for a byte because `reader` cannot receive `65` before the client sends it. To cross-check the JVM stack, fetch `ThreadMXBean.getThreadInfo(reader.getId(),20)` right before sending, keeping in mind that snapshot is not atomic with `getState()`.

## 14. JFR and Additional Cause-Specific Evidence

### 14.1. JFR Events for Monitors, Parking, and I/O

JDK Flight Recorder (JFR) provides events useful for investigations when recording settings are appropriate, for example:

- `jdk.JavaMonitorEnter`: thread waiting to enter a Java monitor; durations/thresholds help spot significant contention.
- `jdk.JavaMonitorWait`: thread waiting in `Object.wait` — **distinct from** monitor-enter contention.
- `jdk.ThreadPark`: thread parked; may involve a Future, AQS lock, idle executor, or other mechanisms.
- `jdk.SocketRead` / `jdk.SocketWrite`: socket I/O activity per configuration/thresholds.
- `jdk.FileRead` / `jdk.FileWrite`: file I/O when events are enabled with appropriate thresholds.
- Execution samples, CPU load, and GC/safepoints when appropriately configured.

**Never assume every event is always enabled or every wait is recorded.** JFR has thresholds, event settings, sampling, and data limits; short waits below threshold may not appear. Never label a `ThreadPark` event a “Future wait” without stack/caller context.

### 14.2. Checking Existing Recordings

Example on HotSpot JDK 17 with `jcmd` and an illustrative PID:

```bash
jcmd 12345 JFR.check
jcmd 12345 help JFR.dump
```

If a recording is running and capture is authorized, `JFR.dump` can save a snapshot per procedure. **Do not turn on recordings or lower event thresholds in production** without evaluating overhead, disk impact, and sensitive data. When catching micro-spikes, sampling/JFR is usually more effective than taking back-to-back thread dumps.

### 14.3. OS/Network and Executor Telemetry

For I/O:

- latency to endpoints, error/timeout rates, connection pool pending/active;
- socket states, retransmissions, DNS timings, disk latency, and queue depth;
- request trace/span IDs to locate related callbacks/producers;
- thread CPU time to distinguish native blocking from busy loops.

For Futures:

- executor core/max threads, `activeCount`, queue size, `completedTaskCount`, `rejectedCount` if supported;
- time tasks spend queued vs. executing, task/parent IDs;
- dependency graphs and cancellation/timeout propagation;
- completion metrics of data sources.

For monitors:

- lock owner/waiter counts, blocked time/count, JFR monitor enter events;
- critical section durations and whether code awaits network/Future under the monitor;
- multiple snapshots to see whether the holder changes or stays at the same call path.

## 15. Five Dump-Reading Scenarios and Action Choices

### Case A — 80 Request Threads `BLOCKED` on the Same Monitor

**Hypothetical data:** many `http-worker` threads show `- waiting to lock <0xABC>`; owner `cache-refresh` has `- locked <0xABC>` with its stack in `Socket.read`.

**Interpretation:** waiters face monitor contention; the owner holds the monitor during I/O. If downstream slows down, contention amplifies. Check matching monitor identity in the same dump, timeouts, JFR lock events, and source code to prove the relationship.

**Action:** shrink the critical section, move remote requests out of the monitor when design allows, use immutable/cached snapshots, and set proper timeouts and backpressure. Do not just enlarge the HTTP worker pool.

### Case B — 150 Threads in `Socket.read`, Low CPU

**Hypothetical data:** many threads are `RUNNABLE` in native socket reads, pool pending rises, dependency p99 climbs.

**Interpretation:** I/O waits can occupy worker threads even with low CPU. Inspect connection pools, server response times, socket read timeouts, DNS/TLS/retries. Use spans and JFR `SocketRead` events to verify. Simply reducing threads will not fix a slow dependency.

**Action:** overall deadlines, sensible per-hop timeouts, circuit breakers, concurrency/retry-budget limits, and scaling downstream resources if metrics prove the bottleneck there.

### Case C — Futures Waiting on Results from the Same Bounded Executor

**Hypothetical data:** 8/8 workers are in `FutureTask.get`, queue size rises, completed task count barely moves. Source code shows the 8 workers submitted child tasks back to the same pool and waited.

**Interpretation:** dependency starvation. No monitor deadlock is needed; `findDeadlockedThreads()` may return `null`.

**Action:** async composition, separating responsibilities/executors by task type, and eliminating blocking waits inside pools executing producers. Add timeouts/backpressure to avoid infinite hangs; do not arbitrarily bump pool size.

### Case D — CompletableFuture join Where the Real Producer Waits on DB

**Hypothetical data:** request threads are `WAITING` at `CompletableFuture.join`; producer tasks show JDBC/network stacks; database pool active=max and pending grows.

**Interpretation:** Future waiting is the **symptom at the caller**, while the delay keeping completion pending lies in the DB/pool or I/O path. Trace the producer/callback, then apply deadlines/cancellation, connection pool limits, and SQL diagnostics.

**Action:** improve the dependency/pool or tune queries, avoid infinite retries, and propagate deadlines. Never blame “CompletableFuture is broken” simply because `join` appears in the stack.

### Case E — Two Threads Waiting on Each Other Indirectly

**Hypothetical data:** A holds monitor M and waits on `futureB`; B needs to acquire M in order to complete `futureB`. A shows `WAITING` at `FutureTask.get`; B shows `BLOCKED` at `waiting to lock M`.

**Interpretation:** a **hybrid dependency cycle** (monitor + Future) that a monitor-only deadlock detector may miss. Locate owner A, waiter B, `futureB`’s producer, and the completion code path.

**Action:** remove blocking future waits from monitor-holding regions, separate state updates, define lock ordering and async boundaries; test to eliminate race/cancellation side effects.

## 16. How to Write a Verifiable Incident Conclusion

Avoid overconfident claims like “JVM hung because of WAITING” or “80 BLOCKED definitely means deadlock.” A better template:

```text
Observation:
  2026-10-29T08:10:00Z, JVM PID=12345, start=...
  37 request threads BLOCKED on monitor M
  owner thread="cache-refresh", frame Socket.read
  downstream p99 rose from 120ms to 4s

Re-observation:
  t+5s, 45 request threads BLOCKED on the same M
  owner still waiting on network read, pool queue growing

Hypothesis:
  Prolonged remote I/O while the holder retains the monitor,
  causing cascading contention.

Needs verification:
  source synchronized block, timeout settings,
  specific trace of the downstream call and JFR monitor enter.

Proposed remediation:
  remove I/O from the critical section when safe,
  add deadlines/backpressure and measure after the change.
```

This is a **simulated case**, not a real system report. Only write “confirmed root cause” once **evidence connects owner/waiter/dependency and timing**.

### 16.1. Collecting Without Destroying Evidence

- Do not restart the JVM before capturing minimum authorized snapshots if restarting wipes current state, unless emergency service restoration takes priority.
- Do not generate hundreds of thread dumps since measurement itself can add latency.
- Do not invoke `System.gc()` or a full heap dump just to confirm a Future wait.
- Never cancel all Futures or call `shutdownNow()` on a production executor without understanding idempotency/transactions/interruptibility.
- Keep all dumps/metrics in consistent UTC timezone, JVM identity, `t0/t1` timestamps, container scope, and tool sources.
- Thread names, file paths, DB URLs, custom MDCs, task labels, and stack traces may contain sensitive info: redact before sharing and enforce retention/access controls.

## 17. Common Mistakes When Classifying Hangs and Contention

1. **Equating `WAITING` with deadlock.** Idle thread pools are legitimately `WAITING`.
2. **Equating `BLOCKED` with every lock type.** `ReentrantLock` contention can appear as `WAITING`/parking.
3. **Assuming `RUNNABLE` always burns CPU.** Native I/O waits can report `RUNNABLE`.
4. **Reading only the top frame `Unsafe.park`.** Callers like `Future.get`/`Condition.await`/`ThreadPoolExecutor.getTask` explain the semantics.
5. **Reading a single dump and declaring root cause.** Time-series snapshots, metrics, and code context are required.
6. **Failing to find the lock owner.** A `BLOCKED` waiter does not tell who holds the monitor or why.
7. **Reading `Object.wait` as holding the awaited monitor.** The thread released that object’s monitor, though it may still hold other locks.
8. **Assuming `Thread.sleep` releases monitors.** It does not release monitors.
9. **Assuming every `LockSupport.park` is a Future.** It could be an idle pool, AQS lock, semaphore, or condition.
10. **Seeing `Socket.read` and blaming the database.** You need endpoint, driver/pool, timeout, SQL, and tracing.
11. **Seeing `CompletableFuture.join` and blaming `Future` implementation.** The producer/executor is usually where investigation belongs.
12. **Trusting `findDeadlockedThreads() == null` means no deadlock anywhere.** It does not detect logical wait cycles across Futures/I/O.
13. **Increasing pool size without fixing nested blocking.** That only delays when starvation strikes.
14. **Failing to separate queue wait from execution time.** Requests may be waiting on unstarted producers.
15. **Setting timeouts at only one layer without an overall deadline.** Retries and multiple hops push latency past SLA.
16. **Assuming `cancel(true)` definitely stops I/O tasks.** Cancellation is best-effort; work may not support interruption.
17. **Assuming `orTimeout` cancels remote work.** It may only complete the future exceptionally.
18. **Reading `ThreadInfo.getBlockedTime()=-1` as “unblocked.”** Contention monitoring may simply be off.
19. **Enabling high-detail contention monitoring/JFR without weighing overhead.** Measurement tools carry cost too.
20. **Ignoring JVM/PID/container namespaces.** You may analyze a dump from a different process lifetime.
21. **Overlooking I/O inside a monitor.** Incidents can have layered, dependent causes.
22. **Looking only at aggregate process CPU.** Low CPU does not rule out network waits, lock contention, or starvation.
23. **Ignoring high-CPU callback threads in favor of waiting request threads.** The producer may be stuck in a loop.
24. **Confusing Java ID / HotSpot `tid` / `nid`.** Never pass native TID as Java thread ID to `ThreadMXBean`.
25. **Failing to protect diagnostic data.** Full stacks/task names can expose internal endpoints and data.

## 18. Practice Checklist

- [ ] Verified exact JVM process, PID namespace, start time, and UTC timestamp?
- [ ] Is the symptom request timeouts, high CPU, growing queues, or an unresponsive service?
- [ ] Is the actual Java state `BLOCKED`, `WAITING`, `TIMED_WAITING`, or `RUNNABLE`?
- [ ] Read enough caller stack frames instead of only the top native/park frame?
- [ ] If `BLOCKED`: found matching monitor ID and holding thread in the same dump?
- [ ] If `Object.wait`: distinguished waiting for notification from waiting to reacquire the lock?
- [ ] If `ReentrantLock`/AQS: inspected the `park` caller and ownable synchronizers?
- [ ] If I/O: identified socket/file/driver/pool, endpoint, timeout, and dependency metrics?
- [ ] If `Future`: identified producer, executor, queue, completion, and dependency graph?
- [ ] Checked for nested `Future.get`/`join` inside the same bounded executor?
- [ ] Checked whether any thread holds a lock while calling remote I/O or `Future.get`?
- [ ] Distinguished `Future.isDone()` from business success?
- [ ] Audited timeouts, cancellation, interrupt handling, and overall deadlines?
- [ ] Known the deadlock detector’s scope; checked whether `null` actually rules out the hang?
- [ ] Collected CPU-time/JFR/OS I/O/GC data to rule out alternative hypotheses?
- [ ] Captured 2–3 snapshots when the incident persists and impact permits?
- [ ] Bounded dump counts and redacted sensitive data?
- [ ] Separated observations, hypotheses, and confirming evidence in the report?

## 19. Self-Check Exercises

**Exercise 1 — Monitor or Future?** Thread A is `BLOCKED` with `waiting to lock <0xAAA>`; thread B is `WAITING (parking)` with stack `FutureTask.get`. Can we say both are waiting on monitors? **No.** A waits on a Java monitor; B waits on a Future result. Check whether B holds `<0xAAA>` or the Future’s producer needs that monitor to uncover a hybrid dependency cycle.

**Exercise 2 — I/O and CPU.** A `RUNNABLE` thread has stack `SocketDispatcher.read0`; OS native TID CPU time barely rises. Is it burning CPU? **No evidence of that**; it may be native blocking I/O. Latency/endpoint/socket counters and multiple samples are needed.

**Exercise 3 — Future starvation.** A 1-worker pool has task A submit B to the same pool and call `B.get()` without timeout. B cannot run because A holds the worker. Is this a monitor deadlock that `findMonitorDeadlockedThreads` will definitely catch? **No.** This is dependency starvation, usually with no Java monitor cycle.

**Exercise 4 — `Object.wait`.** Thread C calls `wait()` on monitor M; does it release monitor M? **Yes**, while waiting, though it may still hold other monitors. Upon waking it must reacquire M before continuing inside `synchronized`.

**Exercise 5 — Is one snapshot enough?** 50 request threads are at `CompletableFuture.join`; can we conclude the `Future` implementation has a bug? **No.** Inspect producer tasks, executor queues, downstream I/O, and cancellation/timeouts; repeat snapshots if permitted.

**Exercise 6 — Timed waits.** A request times out in `Future.get(2,SECONDS)`, yet downstream keeps processing for 10 seconds. Is that a contradiction? **No**: caller timeout does not always cancel remote computation; cancellation/deadline propagation per the actual API is needed.

**Exercise 7 — Causal path.** A monitor owner waits on JDBC while 100 request threads are `BLOCKED` on that monitor. What is a better fix than “grow the request pool”? **Shrink monitor hold scope**, avoid synchronous I/O in the critical section when safe, check the database connection pool/timeouts, and verify with before–after metrics.

## References

- Oracle Java SE 17, [`Thread.State` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): semantics of `BLOCKED`, `WAITING`, `TIMED_WAITING`, `RUNNABLE`; Java states vs. OS states.
- Oracle Java SE 17, [`ThreadInfo` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html): lock owners, monitors, blocked/waited times, and stacks.
- Oracle Java SE 17, [`ThreadMXBean` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): dumps, lock usage, contention monitoring, and deadlock detection.
- Oracle Java SE 17, [`Future` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, timeouts, cancellation, and completion state.
- Oracle Java SE 17, [`FutureTask` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html): `FutureTask` execution and completion.
- Oracle Java SE 17, [`CompletableFuture` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `join`/`get`, async stages, completion/cancellation, and timeouts.
- Oracle Java SE 17, [`Object.wait` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): releasing the waited monitor and wakeup conditions.
- Oracle Java SE 17, [`LockSupport` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/LockSupport.html): parking and blocker context.
- Oracle Java SE 17, [`jcmd` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print -l`, syntax, and impact level.
- Oracle Java SE 17, [Java Flight Recorder Runtime Guide](https://docs.oracle.com/en/java/javase/17/jfapi/index.html): runtime events and JFR recordings when properly enabled.
- Oracle Java SE 17, [Prepare Java for Troubleshooting](https://docs.oracle.com/en/java/javase/17/troubleshoot/prepare-java-troubleshooting.html): collecting multiple thread dumps when a JVM is unresponsive and preserving evidence.

**Conclusion:** before fixing a “hang,” ask **is the thread waiting to acquire a monitor, waiting for I/O to finish, or waiting on a Future?**. `BLOCKED` with `waiting to lock` points to a monitor, `RUNNABLE` in native reads can be an I/O wait, and `WAITING` in `FutureTask.get`/`CompletableFuture.join` points to an async dependency. Trace the **lock owner or task producer**, verify whether it can continue executing, and cross-check multiple snapshots, queue/downstream metrics, and JFR to apply the fix at the right layer.