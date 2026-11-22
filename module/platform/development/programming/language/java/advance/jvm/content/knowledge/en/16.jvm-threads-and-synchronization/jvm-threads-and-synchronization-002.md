# Virtual Thread Stacks and the Limits of the One-Native-Stack-Per-Thread Diagram

## 1. The old model holds for platform threads, not for all Java threads

A common JVM diagram is:

~~~text
Java Thread A ── OS thread A ── native stack A
Java Thread B ── OS thread B ── native stack B
Java Thread C ── OS thread C ── native stack C
~~~

That is an approximate model for **platform threads** on HotSpot: each platform thread is bound to an OS thread for its lifetime, using the OS thread's native stack/context. Since **Java 21**, there are also **virtual threads**: they are still `java.lang.Thread` with identity, locals, a call stack, and exception handling, but **do not hold a dedicated OS thread/native stack for their entire lifetime**.

~~~text
             VIRTUAL THREADS (logical concurrent tasks)
               VT-1       VT-2       VT-3 ... VT-10000
                 |          |          |
                 +----------+----------+-------+
                            |
                       JVM scheduler
                            |
           mount running VT onto a carrier
                            |
                  +---------+---------+
                  |                   |
              carrier-1            carrier-2
                  |                   |
             OS thread 1          OS thread 2
                  |                   |
           native stack 1      native stack 2

Parked/unmounted VT: retains logical execution state/call stack,
possibly in stack chunk objects on the Java heap.
Does not need 10000 separate OS/native stacks for 10000 VTs.
~~~

**The conclusion must distinguish two propositions:**

- A virtual thread **has a logical Java stack** containing frames, variables, method calls, and exception handling state.
- A virtual thread **does not own a fixed dedicated native stack**; it uses a carrier platform thread while running and can **unmount** when waiting on a JDK-supported blocking operation.

Do not infer that "VTs always run in the heap without using any OS thread". When executing CPU instructions, a VT is still **mounted on a platform/OS carrier thread**.

## 2. Java 17, 19, 20, 21, and 24 milestones

| JDK | Virtual threads status | Consequence |
| --- | --- | --- |
| **17** | No standard virtual threads API | Cannot compile `Thread.ofVirtual()` with `--release 17` |
| **19** | JEP 425: first preview | Must use preview features of that exact runtime |
| **20** | JEP 436: second preview | Still preview |
| **21** | **JEP 444** officially introduces virtual threads into Java | `Thread.ofVirtual()`, `isVirtual()`, `newVirtualThreadPerTaskExecutor()` |
| **24** | **JEP 491** improves monitor/synchronized pinning | Conclusions about JDK 21 pinning no longer apply verbatim |

**The runnable examples in this lesson require Java 21+**, even though the module name is Java Advance - jvm. If production deployment still uses JDK 17, this module serves to understand the change in JVM design; to use the stable virtual threads API, JDK 21 or later is required.

Commands:

~~~bash
javac --release 21 VirtualThreadParkingDemo.java
java VirtualThreadParkingDemo
~~~

`--release 21` is the **API/language target at compile time**. Running that bytecode on JDK 24 still uses the scheduler, HotSpot, and GC of **JDK 24**, rather than automatically emulating every detail of JDK 21.

## 3. Three meanings of "stack" to separate

### 3.1. Logical Java call stack

An execution flow `handleRequest() → authenticate() → fetch() → read()` has Java frames in JVM semantics. Frames hold method state, locals/operand stack at the bytecode level, and return/exception information.

~~~text
VT logical call stack:

handleRequest()
    └── authenticate()
        └── fetch()
            └── readFromSocket()  ← paused waiting for I/O
~~~

When the I/O operation completes, the program must **continue the exact call chain and locals**, without forcing the author to rewrite it as a callback state machine.

### 3.2. Native stack of the platform/carrier thread

A platform thread is bound to an OS thread; the OS thread uses a native stack and context managed by the OS/JVM. With the "platform thread per request" style, a blocking request holds its OS thread throughout the wait. A native stack can have different reserved/committed/resident sizes, so `-Xss1m` does not mean every stack already uses exactly 1 MiB of physical RAM.

A **carrier** is a platform thread used by the scheduler to execute a virtual thread. The carrier's native stack is a resource belonging to the carrier, **not a resource hard-bound to one VT for its entire lifetime**.

### 3.3. Continuation and stack chunks on the heap

HotSpot implements virtual-thread continuations and stores suspended stack state via **GC-managed stack chunk objects on the Java heap**, according to JEP 444. The stack can grow/shrink according to execution depth. A VT with a shallow call stack merely waiting on the network does not need the same footprint as a VT with many deep frames.

Do not describe it as **every frame always residing 100% on the heap even while the VT is running**: execution still runs on the carrier OS stack and the VM may move/preserve frames on mount/unmount. The exact memory representation is a HotSpot/JDK implementation detail.

Important: The JVM Specification describes abstract JVM stacks; not every JVM vendor is required to organize virtual-thread stack chunks identically to HotSpot.

## 4. Mount, park, unmount, and resume

~~~text
Time →
Carrier OS thread:
  | VT-A runs | VT-B runs ........ | VT-C runs | VT-A resumes |

VT-A:
  processing → blocking socket read → PARK/UNMOUNT → I/O ready → RESUME
                                     |
                              continuation state
                              heap stack chunks
~~~

A conceptual cycle:

1. `Thread.ofVirtual().start(task)` creates a VT and schedules the task.
2. The scheduler **mounts** the VT on an available carrier.
3. The VT runs Java code on the carrier's OS thread.
4. The VT encounters a blocking operation supported by the JDK for unmounting (for example, certain socket I/O, `BlockingQueue.take()`, or `CountDownLatch.await()` under appropriate conditions).
5. The JVM preserves execution state/stack so it can resume, **unmounts** the VT, and returns the carrier to the scheduler.
6. When the operation can continue, the VT is woken up/scheduled and may **mount onto a different carrier**.
7. Code continues along the old logical Java stack, preserving `try/catch/finally` and locals per contract.

**There is no guarantee a VT always uses a specific carrier**, nor is there a portable `getMyCarrierThread()` API. `Thread.currentThread()` inside VT code returns **the VT itself**, not the carrier.

### Unmount points do not mean every method call

A virtual thread does not automatically unmount when calling a short method, reading a field, or performing CPU computation. It still uses the carrier while working; if CPU-bound code does not block, the virtual thread still occupies the execution capacity of an OS thread as usual.

Some native/JNI sections or blocking paths that do not support unmounting may **pin the carrier**. Therefore, the statement "every blocking call releases the carrier" is false.

## 5. Comparing platform stack and virtual stack

| Question | Platform thread | Virtual thread |
| --- | --- | --- |
| Is a Java `Thread` object? | Yes | Yes |
| Has logical Java frames/stack trace? | Yes | Yes |
| Has a dedicated OS thread for its entire lifetime? | Yes, per platform thread mechanism | **No** |
| Has a dedicated native OS stack for its entire lifetime? | Usually yes | **No** |
| Needs a carrier OS thread when running CPU? | Is itself an OS thread | Yes, uses a carrier |
| When waiting on supported I/O, can release OS thread? | Usually not in synchronous platform-thread I/O | **Can unmount** |
| Can resume on a different carrier? | Not applicable | **Yes** |
| Execution state when unmounted can reside in heap chunks? | Not in the same model | **Yes** |
| Count can far exceed OS threads? | Limited by OS thread resources | **Yes**, depending on heap and other resources |
| Do CPU-bound methods automatically run faster? | No guarantee | No guarantee |

**"Virtual threads have no stack"** is a false statement. If they had no logical stack, synchronous Java code with nested calls, recursion, exceptions, and debugger stack traces would not have their familiar semantics.

## 6. Why do stack chunks on the heap make virtual threads cheaper?

Platform-thread-per-request can require an OS thread, native stack, OS context, and scheduler resources for each waiting request. With VTs, carriers are reused when tasks are blocked/unmounted; many logical call stacks are kept on the heap on demand.

Architectural example:

~~~text
10000 synchronous requests waiting on network:

Platform-thread-per-request:
  nearly 10000 platform/OS threads if not limited by a pool
  many native stacks and OS scheduling state

Virtual-thread-per-request:
  10000 Java VT objects and waiting continuations can exist
  several carriers are reused by the scheduler when VTs unmount
  stack chunks/locals are managed by GC on the heap
~~~

This is only a **scalability model**, not a memory formula or a promise that the number of carriers always equals `Runtime.availableProcessors()` or that a VT only costs 1 KiB. The JVM also creates GC/JIT/service threads, and the scheduler/native code may use additional platform threads.

### VTs still consume heap and keep objects alive

A parked call stack can reference a large object in a local variable:

~~~java
static void handle() throws InterruptedException {
    byte[] payload = new byte[2_000_000];
    Thread.sleep(100);
    consume(payload);
}
~~~

This is an **illustrative snippet** with `consume` defined by the application. Because `payload` needs to be used **after sleeping**, the 2 MB object must remain alive across the wait, even though the carrier may have been released. With 10,000 VTs each holding a 2 MB array, payloads alone reach **about 20 GB**, excluding overhead and stacks.

Creating many VTs is only cheap when each task actually has a moderate footprint. You should monitor **heap live set, request buffering, ThreadLocal state, number of waiting tasks, and scheduler queues** rather than just counting native OS threads.

### Virtual stack chunks and GC roots

According to JEP 444, virtual-thread stacks on the heap **are not treated like native platform stacks as GC roots**. Objects referenced by frames of a reachable continuation are still reachable through the **heap object graph**. Do not infer "the VT unmounted, so local objects are automatically GC'd".

### StackOverflowError can still occur

VTs have growable/shrinkable stacks, not **infinite stacks**. Deep recursion can still throw `StackOverflowError`.

JEP 444 also describes a **JDK 21/G1 limitation**: the implementation at that time did not support humongous stack chunk objects; if a chunk grew to around half a G1 region (which can be as small as 512 KiB), `StackOverflowError` could occur. This is a **version/collector-specific detail** and must not be turned into an invariant law for all JDKs/JVMs.

`-Xss` is related to stack size/limits in HotSpot, but **does not mean** `-Xss1m` allocates a separate 1 MiB native stack for every VT like an OS platform thread. You must distinguish a configuration limit from actual representation/allocation.

## 7. Complete Java 21 example: 1,200 virtual threads waiting on a latch together

Create the file **`VirtualThreadParkingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class VirtualThreadParkingDemo {
    public static void main(String[] args) throws Exception {
        final int tasks = 1200;
        CountDownLatch allWaiting = new CountDownLatch(tasks);
        CountDownLatch release = new CountDownLatch(1);
        List<Future<Boolean>> futures = new ArrayList<>();

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < tasks; i++) {
                futures.add(executor.submit(() -> {
                    boolean virtual = Thread.currentThread().isVirtual();
                    allWaiting.countDown();
                    release.await();
                    return virtual;
                }));
            }
            allWaiting.await();
            System.out.println("tasksReady=" + tasks);
            release.countDown();

            int completed = 0;
            boolean allVirtual = true;
            for (Future<Boolean> future : futures) {
                allVirtual &= future.get();
                completed++;
            }
            System.out.println("completed=" + completed);
            System.out.println("allVirtual=" + allVirtual);
        }
    }
}
~~~

Compile/run:

~~~bash
javac --release 21 VirtualThreadParkingDemo.java
java VirtualThreadParkingDemo
~~~

**Expected stdout per the Java 21 API (compile with `javac --release 21` and run on JDK 21+ to verify):**

~~~text
tasksReady=1200
completed=1200
allVirtual=true
~~~

Meaning:

- `newVirtualThreadPerTaskExecutor()` creates **one virtual thread per task**, rather than creating a pool of 1,200 OS threads.
- Each task signals it has reached the latch via `allWaiting.countDown()` and then waits on `release.await()`.
- Waiting via a `CountDownLatch` mechanism supported by the JDK for VTs allows the VT to **unmount**, yielding the carrier to other tasks.
- Main only prints `tasksReady=1200` after all tasks have reached that point.
- After `release.countDown()`, `Future.get()` waits for each task to complete and receives the result of `Thread.currentThread().isVirtual()`.
- `try-with-resources` ensures the executor is closed with the proper lifecycle.

**Do not infer from stdout how many exact carriers/OS threads the JVM used**: the example does not measure carrier count. OS/JVM schedulers can have different parallelism, compensation, and service threads. To report performance numbers, you must measure with OS/JFR tools on a specific workload.

If you only have JDK 17, the source will **not compile with `javac --release 17`** because the virtual threads API does not exist in Java SE 17.

## 8. Complete Java 21 example: VTs still have a logical call stack

Create the file **`VirtualStackTraceDemo.java`**:

~~~java
import java.util.Arrays;

public final class VirtualStackTraceDemo {
    static long descend(int remaining) {
        if (remaining == 0) {
            return Arrays.stream(Thread.currentThread().getStackTrace())
                    .filter(frame ->
                            frame.getMethodName().equals("descend"))
                    .count();
        }
        return descend(remaining - 1);
    }

    public static void main(String[] args) throws Exception {
        Thread worker = Thread.ofVirtual()
                .name("logical-task")
                .start(() -> {
                    System.out.println("virtual=" +
                            Thread.currentThread().isVirtual());
                    System.out.println("logicalFrames=" + descend(5));
                });

        worker.join();
        System.out.println("terminated=" + !worker.isAlive());
    }
}
~~~

Compile/run:

~~~bash
javac --release 21 VirtualStackTraceDemo.java
java VirtualStackTraceDemo
~~~

**Observed stdout on OpenJDK 24:**

~~~text
virtual=true
logicalFrames=6
terminated=true
~~~

Calling `descend(5)` nests six times, creating a logical call-chain at values 5, 4, 3, 2, 1, 0. `Thread.currentThread().getStackTrace()` runs **inside the VT itself** and on the tested JVM counted 6 frames named `descend`.

`getStackTrace()` has implementation limitations regarding stack walking/virtual machine frames; do not assume every JDK is required to display the exact same frame count in all cases. The output **states a single observed run**; the goal of the lesson is to prove the concept that VTs still have a logical call stack, not something "stackless".

`worker.join()` waits for the VT to finish; `terminated=true` does not mean its carrier platform thread was shut down.

## 9. What is pinning? Why distinguish JDK 21 from JDK 24?

**Pinning** occurs when a VT **cannot unmount** from its carrier during a section with a blocking operation. The carrier OS thread can be blocked along with the VT, so other VTs cannot utilize that carrier. Pinning **does not necessarily break correctness**, but frequent and long pinning can cause the application to lose scalability.

### JDK 21–23: synchronized + blocking can pin

In JDK 21, a virtual thread performing a blocking operation **inside a `synchronized` method or block** can keep the carrier pinned. Illustrative example:

~~~java
synchronized (lock) {
    readFromRemoteService();  // may block for a long time
}
~~~

This snippet is **not standalone runnable**, because `lock` and `readFromRemoteService()` must be defined by the application.

You should not conclude "all synchronized is bad": very short synchronized regions updating in-memory state are usually not a bottleneck. The risk is **frequent and long-lived** blocking I/O inside a monitor. In JDK 21, for those places, a design using `ReentrantLock` can avoid monitor-related pinning:

~~~java
lock.lock();
try {
    readFromRemoteService();
} finally {
    lock.unlock();
}
~~~

Here `lock` is a `ReentrantLock` created by the application. **Do not mechanically replace all synchronized blocks**: you must consider monitor semantics, `wait/notify`, reentrancy, ordering, and exception paths.

### JDK 24+: JEP 491 improves monitor behavior

**JEP 491 — Synchronize Virtual Threads without Pinning** was implemented in JDK 24: virtual threads can unmount when blocking under the improved Java monitor/synchronization cases. Therefore, the statement "JDK 24 always pins all blocking I/O inside synchronized" is **no longer true**.

However, **native frames/JNI/foreign calls and certain platform-specific operations** can still hold the carrier in other situations. Do not promise that JDK 24 "eliminates all pinning".

| Case | JDK 21–23 | JDK 24+ |
| --- | --- | --- |
| Blocking under Java `synchronized` | Risk of monitor pinning | JEP 491 resolves the corresponding monitor cases |
| JNI/native/foreign operation | May hold carrier | Still has cases that hold carrier |
| Unmount-supporting JDK blocking API, not pinned | Usually releases carrier | Usually releases carrier |
| Non-blocking CPU-bound code | Continues using carrier | Continues using carrier |

When analyzing production, record **JDK vendor/build, JVM implementation, OS, native libraries, and JFR settings**. Do not copy the pinning table from JDK 21 documentation as a permanent law.

## 10. Virtual threads do not replace CPU cores or resource limits

Virtual threads are designed to increase **concurrency of tasks that frequently wait on I/O**, not to make a CPU-bound computation automatically run faster.

A system with 8 CPU cores cannot simultaneously execute one million Java CPU-bound tasks at the exact same instant just by creating one million virtual threads. They still have to share carriers, the scheduler, and those 8 cores.

For example, a request does 2 ms of CPU work and then waits 100 ms on the database: platform-thread-per-request can hold an OS thread while waiting; a VT can yield the carrier on unmount-supporting I/O, allowing the OS thread to serve another task. However, that request **still needs the database time**; throughput can increase when the previous bottleneck was OS threads, while single-request latency does not necessarily decrease.

**Downstream is still a bottleneck**: 10 DB connections do not become 10,000 connections. If 10,000 VTs call the database at once, the connection pool, rate limiting, file descriptors, socket buffers, and heap retention still limit serving capacity.

### Bounded concurrency instead of pooling VTs

JEP 444 recommends **virtual thread per task**, not pooling virtual threads because they are lightweight task units, not expensive OS workers to reuse.

~~~java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    // Each submit creates a new VT for the task.
    var future = executor.submit(() -> performOperation());
    var result = future.get();
    process(result);
}
~~~

This snippet is an **illustrative fragment**; real `performOperation()`/`process()` are needed. For bounded downstreams, use a `Semaphore`, connection pool, or backpressure:

~~~java
semaphore.acquire();
try {
    return callDatabase();
} finally {
    semaphore.release();
}
~~~

`semaphore` and `callDatabase()` here belong to the application and the code must handle interruption properly. A VT waiting on a semaphore can release its carrier, but downstream concurrency limits must still be enforced.

## 11. ThreadLocal, object retention, and memory budget

Virtual threads support `ThreadLocal` like platform threads, but a "per-thread cache" becomes a problem when **each task has its own thread**.

~~~java
private static final ThreadLocal<byte[]> SCRATCH =
        ThreadLocal.withInitial(() -> new byte[1_000_000]);
~~~

This is an **illustrative field**, not a runnable program. A platform thread pool of 32 workers might create about 32 buffers if each worker accesses it once. With 20,000 VTs using this ThreadLocal simultaneously, there can be 20,000 buffers amounting to **about 20 GB of bytes**, excluding objects/stack chunks.

Instead of caching large resources per thread, consider **immutable shared objects, bounded pools, request-scoped data, and explicit cleanup**. Thread-local state in the carrier is **not** implicitly treated as the VT's ThreadLocal. `Thread.currentThread()` in a VT returns the VT, and thread-local namespaces do not mix with the carrier.

Budgeting considerations:

~~~text
Java heap:
    request payloads, business objects
  + virtual Thread objects
  + stack chunks / continuation state
  + ThreadLocals and Futures/scheduler metadata

Native/process memory:
    carrier OS thread stacks
  + GC/JIT/VM service threads and internal structures
  + JNI/native allocations
  + mapped/direct buffers and OS resources
~~~

Do not add reserved/committed/RSS numbers indiscriminately; they have different meanings. **Do not take `N_virtual × -Xss` as a mandatory formula for native stack usage.**

## 12. Observing virtual threads: why are `ps` and ThreadMXBean not enough?

The OS knows about **native threads** (carriers, GC/JIT workers, native library threads...), not all virtual threads as separate OS threads. Therefore:

~~~text
OS native thread count  != logical virtual-thread count
ThreadMXBean count       != number of existing virtual threads
~~~

JEP 444 notes that in JDK 21 `ThreadMXBean` focuses on managing platform threads and does not list all virtual threads like a traditional thread manager. Many `ThreadGroup` APIs also have limitations because virtual threads are not considered active group members in the old sense.

### `jcmd` virtual-thread-aware dumps

On JDK 21+, you can use `Thread.dump_to_file`:

~~~text
jcmd PID Thread.dump_to_file -format=text threads.txt
jcmd PID Thread.dump_to_file -format=json threads.json
~~~

`PID` is a placeholder to **replace with the actual process ID**, not a shell command with a default PID variable. Appropriate JDK tools/attach permissions are required. This dump can represent logical virtual threads/stack traces much better than many legacy dump formats.

With very many VTs, the dump can be **very large** and impact CPU/memory/disk. Stack traces can also expose sensitive class names/methods/metadata; control access permissions.

### JFR virtual-thread events

JDK 21 events that can be used:

- `jdk.VirtualThreadStart`/`jdk.VirtualThreadEnd`: track lifecycle; usually **not enabled by default** due to event volume.
- `jdk.VirtualThreadPinned`: observe blocking while pinned, depending on thresholds/settings (JDK 21 documentation describes a default threshold of around 20 ms).
- `jdk.VirtualThreadSubmitFailed`: failure when scheduling/starting/unparking a VT.

Reading from an existing recording:

~~~bash
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed recording.jfr
~~~

The file `recording.jfr` must be created beforehand. Event availability, settings, and thresholds depend on the JDK version; if an event does not appear, do not state with absolute certainty that there is "no pinning".

On JDK 21, the property:

~~~bash
java -Djdk.tracePinnedThreads=full MyMain
~~~

can help detect some pinning call stacks (`MyMain` must be a real main class). With JDK 24+, JEP 491 changed monitor behavior; do not rely on the absence of a trace as proof of a perfect scheduler.

## 13. A design table for a 10,000 I/O requests scenario

Suppose there are 10,000 requests waiting on the network while each request needs only a little CPU.

| Criterion | Platform-thread-per-request | Virtual-thread-per-request |
| --- | --- | --- |
| Thread per logical request | Platform thread | Virtual thread |
| Native OS stack per request | Usually must be held | Not independently required per VT |
| Blocking I/O | OS thread is occupied in traditional style | Can unmount VT and reuse carrier |
| Sequential code with `try/finally` | Natural | Also natural |
| Memory for request context | Heap objects and platform stack | Heap objects and VT stack chunks |
| Downstream connection limit | Still must be managed | **Still must be managed** |
| CPU-bound throughput | CPU-limited | **Still CPU-limited** |
| JVM pinning pitfalls | Not under virtual scheduler | Must consider JDK/native/synchronized version |
| Profiling | Native+Java thread tools | Virtual-thread-aware dumps/JFR required |

**You cannot choose VTs solely from fewer native stacks**. You must measure end-to-end throughput, p99/p99.9, RSS/heap live set, CPU/carriers, executor task backlog, connection pools, and timeout/OOM errors under real workload.

### When are VTs most useful?

- Many concurrent tasks mainly **waiting on I/O** with APIs that support suspension.
- The application needs readable synchronous code, one task per thread, and needs to scale beyond traditional OS thread limits.
- Resource limits (DB, sockets, heap) have clear backpressure.

### When can VTs not save you?

- CPU-bound hot loops have already saturated cores.
- The database is already at full load and the connection pool has long waits.
- Each VT holds a large payload for too long, causing high heap/GC pressure.
- Native code pins carriers for long periods where blocking occurs frequently.
- The system already uses an optimized async framework with very few OS threads and has no thread scarcity issue.

## 14. Typical misconceptions

1. **"Every `Thread` instance has its own native stack."** False for VTs.
2. **"Virtual threads have no call stack."** False; they still have logical Java frames and stack traces.
3. **"VTs do not need an OS thread to run CPU."** False; they need a carrier.
4. **"A VT's carrier is fixed."** False; it can change upon resume.
5. **"Thread.currentThread() returns the carrier."** False; it returns the virtual thread.
6. **"A parked VT always holds an OS thread."** Not when the operation supports unmounting and is not pinned.
7. **"Every blocking call unmounts."** False; native/platform-specific/pinning cases exist.
8. **"A virtual-thread stack is a native OS stack of size `-Xss`."** False.
9. **"VT stack chunks do not reside on the heap."** False with HotSpot/JEP 444.
10. **"Heap does not grow when creating thousands of parked VTs."** False; chunks, locals, payloads, and metadata have a footprint.
11. **"VTs never throw StackOverflowError."** False.
12. **"VTs run CPU-bound code faster than platform threads."** Not the goal.
13. **"Java 17 supports stable `Thread.ofVirtual()`."** False; Java 21.
14. **"JDK 24 still always pins inside synchronized."** Generally false due to JEP 491.
15. **"JDK 24 has no pinning at all anymore."** False; native cases still exist.
16. **"You need to pool VTs like OS threads."** Does not fit the virtual-thread-per-task model.
17. **"The carrier's ThreadLocal is the VT's ThreadLocal."** False.
18. **"Increasing the number of VTs increases the number of DB connections."** False.
19. **"ThreadMXBean counts all virtual threads in JDK 21."** False.
20. **"A low OS thread count proves low heap memory."** False.
21. **"A VT can run CPU concurrently on two carriers."** False; a VT has only one execution flow at a time.
22. **"Stack chunks are GC-managed, so all local objects when a VT parks are GC'd."** False.
23. **"Seeing `logicalFrames=6` means the VT unmounted six times."** False; those are logical call frames, not scheduler transitions.
24. **"The Java API promises a fixed number of carrier threads."** False.

## 15. Self-check exercises

1. A JVM has 10,000 VTs and 32 carriers; does it need 10,000 native stack reservations per VT? **No**.
2. Where does a CPU-running VT actually execute? **On a carrier platform/OS thread**.
3. Does an unmounted VT lose its locals/Java frames? **No**, the runtime preserves continuation state to resume.
4. Do heap stack chunks mean a VT cannot stack overflow? **No**.
5. In which Java release was the stable virtual threads feature released? **Java 21, JEP 444**.
6. Does `--release 21` on JDK 24 turn the runtime into JDK 21? **No**.
7. Does `newVirtualThreadPerTaskExecutor()` create 1 OS thread per submit? **No**.
8. What does `Thread.currentThread().isVirtual()` return inside a VT? **True**.
9. If socket I/O supports unmounting, can the carrier serve another VT while waiting? **Yes**.
10. Is every JNI operation guaranteed to unmount? **No**.
11. Can blocking inside synchronized in JDK 21 pin the carrier? **Yes**.
12. Which JEP improves that in JDK 24? **JEP 491**.
13. Has JEP 491 eliminated all native-related pinning? **No**.
14. Does running 1,200 tasks in the example prove there are exactly 2 carriers? **No**, carrier count is not measured.
15. Why not use `ThreadMXBean.getThreadCount()` as the total VT count in JDK 21? **MXBean primarily manages platform threads**.
16. Which command is used to inspect VT stacks with JDK tools? **`jcmd PID Thread.dump_to_file -format=json ...`**.
17. What order of memory pressure do 10,000 VTs each holding `byte[2_000_000]` across sleep create? **About 20 GB of payload bytes before overhead**.
18. When the DB only has 20 connections, does creating 10,000 VTs automatically increase DB throughput infinitely? **No**.
19. Are VTs mainly beneficial for CPU-bound or I/O-blocking concurrency? **I/O-blocking concurrency**.
20. Which statement is more accurate: "VTs have no stack" or "VTs have a logical Java stack but no fixed dedicated native OS stack"? **The second statement**.

## 16. Official references

- **OpenJDK JEP 444 — Virtual Threads** (final in JDK 21, stack chunks, GC interactions): https://openjdk.org/jeps/444
- **Oracle Java SE 21 — Virtual Threads**, carrier scheduling, debugging, pinning, and design guidance: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- **Java SE 21 `Thread` API**, `Thread.ofVirtual()` and `isVirtual()`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html
- **Java SE 21 `Executors` API**, virtual-thread-per-task executor: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html
- **OpenJDK JEP 425/436**, preview JDK 19/20: https://openjdk.org/jeps/425 and https://openjdk.org/jeps/436
- **OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning (JDK 24):** https://openjdk.org/jeps/491
- **Oracle Java SE 24 migration changes** noting JEP 491: https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html
- **Oracle JDK 21 `jcmd`**, Thread.dump_to_file: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- **JVMS 21 §2.5 Runtime Data Areas**, abstract JVM stacks: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5

**Conclusion:** A virtual thread is a **real Java thread at the semantic level**: it has locals, a call stack, stack traces, and exception handling. However, since JDK 21, it **does not need a dedicated OS thread/native stack for its entire lifetime**; the JVM mounts the VT onto a **carrier** while running, can store continuation/stack chunks on the **Java heap**, and returns the carrier to the scheduler when the VT waits on an unmount-supporting operation. The diagram "each Java thread = one native stack" should only be used for platform threads. Concurrency scalability does not remove limits on CPU, heap, native pinning, or downstream connections, and one must read the differences between **JDK 21 and JDK 24+** accurately.