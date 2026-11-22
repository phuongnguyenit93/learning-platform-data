# OutOfMemoryError and the Limits of In-Process Recovery in Java

## 1. Why Does This Topic Matter?

`OutOfMemoryError`, often abbreviated **OOME**, signals that the Java Virtual Machine cannot satisfy an allocation request for memory or a corresponding resource under given conditions. It does not only occur when `new byte[...]` fills up the Java heap: an application can also run into shortages of native memory, metaspace, direct buffers, thread creation limits, or array size limits.

The most common mistake is treating OOME like an ordinary business error: writing `catch (OutOfMemoryError e)`, calling `System.gc()`, clearing a few cache entries, and letting the entire service continue as before. **Catching an OOME does not prove that the JVM has enough resources, that data is still consistent, or that the next request is safe.** Some failure modes do not even give the JVM a chance to catch anything, such as when the process is terminated by the operating system or container OOM killer.

Lesson objectives:

- Correctly identify the inheritance hierarchy and **unchecked `Error`** contract.
- Distinguish heap exhaustion from metaspace, native thread, direct buffer, and other limits.
- Understand that the JVM may remain running after an OOME, yet application recovery is **not guaranteed**.
- Recognize the limits of `catch`, `finally`, `try-with-resources`, manual GC, and memory reserves.
- Explain OOME during **static initialization** and its impact on subsequent uses of the class.
- Design memory budgets for input/cache/concurrency, streaming, and backpressure to prevent errors.
- Diagnose issues via heap dumps, GC logs, JFR, process metrics, Native Memory Tracking, and OOM kill data.
- Establish fail-fast policies, failure detection, and out-of-process restarts with business-state verification.
- Write safe Java 17+ examples **without attempting to exhaust real memory**.

All runnable examples include filenames, `javac`/`java` commands, and `stdout`. Examples that throw `new OutOfMemoryError("simulated")` are **deliberately simulated errors**, used solely to study exception and class initialization semantics—**not tests of recovery capability in a genuinely out-of-RAM environment**.

## 2. Where Does `OutOfMemoryError` Sit in the `Throwable` Hierarchy?

```text
java.lang.Throwable
├── java.lang.Exception
│   ├── java.lang.RuntimeException [unchecked]
│   └── checked exceptions
└── java.lang.Error                  [unchecked]
    └── java.lang.VirtualMachineError
        ├── java.lang.OutOfMemoryError
        ├── java.lang.StackOverflowError
        └── java.lang.InternalError
```

`OutOfMemoryError` is a subclass of `VirtualMachineError` → `Error` → `Throwable`, and is **not** a subclass of `Exception`. Therefore:

- `catch (Exception e)` and `catch (RuntimeException e)` do not catch OOME.
- `catch (OutOfMemoryError e)`, `catch (Error e)`, `catch (VirtualMachineError e)`, and `catch (Throwable e)` can match OOME by type.
- The compiler **does not require** a method to declare `throws OutOfMemoryError`.
- "Unchecked" is purely a compile-time rule; it does **not** mean less severe or safe to ignore.

### Runnable program: checking type relationships

Create the file **`OomeHierarchyDemo.java`**:

```java
public class OomeHierarchyDemo {
    public static void main(String[] args) {
        Throwable sample = new OutOfMemoryError("simulated");

        System.out.println("type="
                + sample.getClass().getSimpleName());
        System.out.println("Throwable="
                + (sample instanceof Throwable));
        System.out.println("Error="
                + (sample instanceof Error));
        System.out.println("VirtualMachineError="
                + (sample instanceof VirtualMachineError));
        System.out.println("Exception="
                + (sample instanceof Exception));
    }
}
```

```bash
javac OomeHierarchyDemo.java
java OomeHierarchyDemo
```

`stdout`:

```text
type=OutOfMemoryError
Throwable=true
Error=true
VirtualMachineError=true
Exception=false
```

This program only creates a small `Throwable` object and **does not** attempt to exhaust memory. The `instanceof` checks use a variable of static type `Throwable` to accurately demonstrate the inheritance relationship.

## 3. Common Causes of OOME

The `OutOfMemoryError` message hints at which area to investigate, but it is not an immutable standard error code across all JVMs/JDKs. Do not build business logic by matching solely on `getMessage()` strings.

| Common symptom/message | Investigation direction | Mistake to avoid |
| --- | --- | --- |
| `Java heap space` | `-Xmx` limit, live objects, oversized data, allocation spikes | Concluding everything is a leak |
| `GC overhead limit exceeded` | Garbage collection spends excessive effort freeing very little according to JVM thresholds | Calling `System.gc()` endlessly |
| `Metaspace` | Class metadata, class loading, retained class loaders, `MaxMetaspaceSize` | Only increasing the Java heap |
| `Requested array size exceeds VM limit` | Array size is bounded by VM limits or cannot be represented | Believing adding more RAM allows creating it |
| `unable to create native thread` | Native threads, stacks, OS/process/container limits | Assuming the heap must be full |
| Direct-buffer memory allocation error | `ByteBuffer.allocateDirect`, native/direct buffer budget | Reading `Runtime.freeMemory()` and concluding there is enough RAM |

### 3.1. Java heap

Java objects managed by the GC normally reside on the heap. Heap exhaustion can result from:

- **Logical leaks**: caches without eviction, static collections, listeners, `ThreadLocal`, sessions, or queues still holding references.
- **Legitimate but oversized live-set**: business requirements hold more data than the configured heap allows.
- **Allocation spikes**: parsing large files, decoding images, creating many string/array copies, batch processing, and concurrent requests.
- **A single oversized allocation**: a buffer, array, or intermediate object that exceeds the limit.

The GC cannot reclaim still-reachable objects merely because the application feels they are "no longer needed." Conversely, many live objects that are genuinely needed by the business may not be a leak, and instead require changing the processing architecture or memory budget.

### 3.2. Metaspace

Metaspace relates to class metadata and typically uses native memory. Frameworks that dynamically generate proxies/classes, load plugins through multiple class loaders, or retain old class loaders can create pressure. Investigate class counts, class loader lifetimes, `-XX:MaxMetaspaceSize`, and native memory rather than only checking `-Xmx`.

### 3.3. Native memory, direct buffers, and threads

Direct buffers, thread stacks, JNI libraries, the native allocator, and several JVM subsystems use resources that are not fully measured by free heap metrics alone. Inside containers, **total RSS/process memory** alongside the cgroup limit matters just as much as `-Xmx`.

Raising the Java heap close to the RAM/container limit can **starve native memory**, making other failures worse. Unbounded thread pools or too many platform threads can fail when creating native threads even while heap space remains.

### 3.4. OS OOM kill is different from a Java OOME

If the OS/container decides to terminate the process for exceeding its memory budget, Java **does not necessarily receive an `OutOfMemoryError` object to catch**. There is no guarantee that `finally` blocks, shutdown hooks, or heap dumps will run before termination. Signals must be gathered from **the supervisor, cgroup/container events, and host logs**.

## 4. The JVM May Keep Running, but Application State Is Not Necessarily Safe

Java does not specify that every `OutOfMemoryError` immediately shuts down the JVM. One thread can throw OOME, unwind its stack, run a matching handler, and other threads can continue operating. Sometimes after a failed request, certain objects become unreachable and the GC can reclaim memory.

However, that does not allow concluding that:

- There is enough memory for the next request.
- Caches or queues have dropped to a safe threshold.
- Transactions were completely rolled back.
- External APIs did or did not execute.
- Invariants of objects shared across multiple threads remain consistent.
- A class that failed initialization can re-initialize normally.
- Logging, emitting metrics, or building an error response is guaranteed to succeed.

For example, a request might update in-heap state, send a request to an external system, and then hit an OOME when allocating a buffer to process the response. **Catching OOME does not undo side effects**, nor does it tell you whether the request is safe to retry.

Three layers of checks must be distinguished:

1. **JVM liveness**: is the process still running?
2. **Readiness**: does the instance have sufficient resources and healthy state to accept new workloads?
3. **Consistency**: do persistent data, transactions, and business state match?

A `return true` from a health endpoint after a `catch` is not reliable evidence for all three layers.

## 5. `catch (OutOfMemoryError)` Is Valid Syntax, but Not Default Recovery

You can write:

```java
try {
    operation();
} catch (OutOfMemoryError failure) {
    // Perform only an extremely minimal signal if truly needed.
    throw failure;
}
```

This is an **illustrative snippet**; `operation()` must be defined. In production code, you **should not** turn this handler into a heavy workflow: building a JSON response, formatting a full stack trace, sending HTTP requests, taking a large snapshot, allocating a new cache, spawning threads, or immediately retrying the same operation.

### Runnable program: catching and rethrowing a deliberately created error

Create the file **`ControlledOomePropagationDemo.java`**:

```java
public class ControlledOomePropagationDemo {
    static void run() {
        try {
            throw new OutOfMemoryError("simulated only");
        } catch (OutOfMemoryError failure) {
            System.out.println("boundary=observed");
            throw failure;
        } finally {
            System.out.println("finally=ran");
        }
    }

    public static void main(String[] args) {
        try {
            run();
        } catch (OutOfMemoryError failure) {
            System.out.println("caller=" + failure.getMessage());
        }
    }
}
```

```bash
javac ControlledOomePropagationDemo.java
java ControlledOomePropagationDemo
```

`stdout`:

```text
boundary=observed
finally=ran
caller=simulated only
```

This is the **normal execution path of a thrown `Throwable`**, not a JVM genuinely out of memory. The line `finally=ran` proves that `finally` ran in this example; it does **not** prove it always runs when the process is killed by the OS or when the JVM has no resources left.

### Why can the handler itself also fail?

Under out-of-memory conditions, the following operations may still require allocations:

- String concatenation, generating stack trace text, serializing JSON, or formatting a logging event.
- Enqueuing a message to an asynchronous logger.
- Initializing a class used for the first time inside the handler.
- Creating a new exception object to wrap the error.
- Opening sockets, creating threads, or performing complex I/O.
- Building an HTTP response and framework state.

A handler containing those steps is **not guaranteed to complete**. Catching and returning normally after an OOME can allow further requests into a JVM that is out of memory or in a half-broken state.

### Should you pre-allocate an "emergency" buffer?

Some applications pre-allocate a buffer early and drop its reference on error, hoping GC frees space to write a short signal. This technique is only **best-effort**: it may not help with native/metaspace/thread exhaustion; GC is not guaranteed to reclaim enough immediately; other threads keep allocating; and business state is not restored either. **Do not treat a reserve as a guarantee of in-process recovery**.

## 6. `finally` and `try-with-resources`: Semantic Guarantees, Not Magic

When a `Throwable` is thrown via normal Java mechanisms, `finally` executes according to control-flow rules. `try-with-resources` attempts to close resources that were successfully created, and if both the body and `close()` throw, the close failure can be recorded as a **suppressed exception** on the primary error.

However:

- If the process is killed by the OS, `Runtime.halt`, power loss, or a JVM crash, `finally` has no guarantee of running.
- `close()` may require memory, I/O, or throw another error.
- A `finally` block throwing another `Throwable` can mask the original error if manual cleanup is written poorly.
- `synchronized` monitors are released when exiting via a normal Java exception flow, which **does not** roll back state that was already modified.
- Even when transaction rollback is properly designed, you still need to check whether the transaction committed in external systems.

### Runnable program: closing a resource when throwing a simulated OOME

Create the file **`ControlledOomeCleanupDemo.java`**:

```java
public class ControlledOomeCleanupDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("close=called");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            throw new OutOfMemoryError("controlled failure");
        } catch (OutOfMemoryError failure) {
            System.out.println("caught=" + failure.getMessage());
        }
    }
}
```

```bash
javac ControlledOomeCleanupDemo.java
java ControlledOomeCleanupDemo
```

`stdout`:

```text
close=called
caught=controlled failure
```

This program demonstrates TWR **with an error created while the heap is still healthy**. It is not a stress test, nor does it prove that every resource can still close when native memory or the heap is genuinely exhausted.

**Proper design:** scope cleanup to resource ownership, and use transactions and data recovery mechanisms that work after a crash. Do not rely on a JVM OOME alone to preserve system integrity.

## 7. OOME in Static Initialization: Error State Can Persist

An `OutOfMemoryError` occurring during the initialization of a class's static fields/initializers can cause **class initialization to fail**. The JVM records that class as being in an initialization error state within its corresponding class loader.

When the `Throwable` escaping a class initializer is an **Error** (such as OOME), it may be propagated **as-is** on the first attempt. On subsequent accesses to the failed class, the JVM typically throws `NoClassDefFoundError` rather than re-running the entire static initializer.

### Runnable program: a class that failed initialization

Create the file **`OomeClassInitializationDemo.java`**:

```java
public class OomeClassInitializationDemo {
    static class Broken {
        static final int VALUE = initialize();

        static int initialize() {
            throw new OutOfMemoryError("simulated during init");
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(Broken.VALUE);
        } catch (OutOfMemoryError failure) {
            System.out.println("first="
                    + failure.getClass().getSimpleName());
        }

        try {
            System.out.println(Broken.VALUE);
        } catch (NoClassDefFoundError failure) {
            System.out.println("second="
                    + failure.getClass().getSimpleName());
        }
    }
}
```

```bash
javac OomeClassInitializationDemo.java
java OomeClassInitializationDemo
```

`stdout` in Java 17:

```text
first=OutOfMemoryError
second=NoClassDefFoundError
```

Analysis:

1. Accessing `Broken.VALUE` for the first time triggers initialization of `Broken`.
2. `initialize()` throws a simulated OOME. Because it is an `Error`, it can propagate as-is without being wrapped in `ExceptionInInitializerError`.
3. `Broken` enters an initialization-failed state in the class loader.
4. The next access is not a retry in the same class loader: the JVM reports `NoClassDefFoundError`.
5. No memory was intentionally exhausted in this test.

This case shows that **local recovery with a single catch is not enough**: lingering failure state can remain right inside runtime state. When a static initializer throws a `Throwable` that is **not an Error**, JLS rules may wrap it in `ExceptionInInitializerError`; do not conflate the two cases.

## 8. `System.gc()` Is Not an OOME Fix Button

`System.gc()` is a request/hint to the JVM to make a garbage collection effort; it does not guarantee exact timing, GC type, or the amount of memory freed, and some configurations may disable explicit GC.

Even when GC runs:

- Objects **still reachable** from static caches or queues will not disappear.
- Array requests exceeding VM limits remain invalid.
- Native thread resources do not automatically recover from a full GC.
- Metaspace leaks caused by retained class loader references can still persist.
- If the OS OOM killer has stopped the process, there is no Java code left to call GC.

Anti-pattern example:

```java
try {
    doWork();
} catch (OutOfMemoryError failure) {
    System.gc();
    doWork(); // Retry immediately in the same state.
}
```

This is a **policy-flawed snippet**; `doWork` must be defined. It can fail repeatedly and cause duplicate side effects. Do not use manual GC as a substitute for root-cause analysis, workload bounding, and data lifecycle management.

### `Runtime.freeMemory()` is not "total remaining RAM"

`Runtime.getRuntime().freeMemory()` describes the free space within the JVM's **current** heap, not total physical RAM, cgroup limits, direct memory, or the number of native thread bytes still available to allocate. `Runtime.maxMemory()` is primarily the heap limit; it does not replace measuring RSS and native memory either.

When diagnosing, examine **used, committed, and max heap**, non-heap, GC, direct/mapped buffers, thread counts, class loaders, queue sizes, process RSS, and container limits together.

## 9. Reject Oversized Allocation Requests Before Hitting JVM Limits

Inputs from the network, files, JSON, images, or configuration may contain untrusted size fields. Do not write:

```java
int count = Integer.parseInt(input);
byte[] buffer = new byte[count];
```

This is an **anti-pattern snippet**, because `input` is unbounded and could be negative or huge. Programs should enforce a **business max size**, perform math checks to prevent integer overflow, and maintain a combined budget across concurrent requests.

### Runnable program: rejecting before allocation

Create the file **`AllocationBudgetDemo.java`**:

```java
public class AllocationBudgetDemo {
    static byte[] allocateBounded(int count, int maxAllowed) {
        if (count < 0 || count > maxAllowed) {
            throw new IllegalArgumentException(
                    "allocation outside allowed budget");
        }
        return new byte[count];
    }

    public static void main(String[] args) {
        System.out.println("length="
                + allocateBounded(8, 16).length);

        try {
            allocateBounded(1000, 16);
        } catch (IllegalArgumentException failure) {
            System.out.println("rejected=" + failure.getMessage());
        }
    }
}
```

```bash
javac AllocationBudgetDemo.java
java AllocationBudgetDemo
```

`stdout`:

```text
length=8
rejected=allocation outside allowed budget
```

This turns invalid input into a **controlled** error without attempting to trigger OOME. Even so, an allocation within budget is **not an absolute guarantee** of success in every JVM: other threads and objects still compete for memory.

To avoid integer overflow when calculating budgets for `count * elementSize`, use `long` or checks such as `Math.multiplyExact` with explicit bounds before allocating.

## 10. Bounded Streaming Instead of Reading All Data

`Files.readAllBytes(...)`, `Files.readAllLines(...)`, or collecting all entries into an `ArrayList` can be suitable for small inputs. When sizes are uncertain, they easily create large memory peaks; moreover, decompression can cause **decompressed** data to expand many times over.

Approach:

- Read in reasonably sized buffers/chunks.
- Limit **total bytes**, record counts, per-token/line length, and structure depth.
- Release resources with `try-with-resources` according to ownership.
- Do not cache the entire request body in middleware and then copy it again in the parser.
- Under concurrency, enforce an **aggregate** budget, not only per-request limits.

### Runnable program: enforcing limits while streaming

Create the file **`StreamingInputBudgetDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class StreamingInputBudgetDemo {
    static long consume(InputStream input, long maxBytes)
            throws IOException {
        if (maxBytes < 0) {
            throw new IllegalArgumentException("negative limit");
        }

        long total = 0;
        byte[] chunk = new byte[3];
        int count;

        while ((count = input.read(chunk)) != -1) {
            if (count > maxBytes - total) {
                throw new IOException(
                        "input exceeds " + maxBytes + " bytes");
            }
            total += count;
        }
        return total;
    }

    public static void main(String[] args) throws IOException {
        byte[] data = "abcde".getBytes(StandardCharsets.UTF_8);

        try (InputStream input = new ByteArrayInputStream(data)) {
            System.out.println("accepted=" + consume(input, 5));
        }

        try (InputStream input = new ByteArrayInputStream(data)) {
            consume(input, 4);
        } catch (IOException failure) {
            System.out.println("rejected=" + failure.getMessage());
        }
    }
}
```

```bash
javac StreamingInputBudgetDemo.java
java StreamingInputBudgetDemo
```

`stdout`:

```text
accepted=5
rejected=input exceeds 4 bytes
```

This example uses only a 3-byte buffer and stops the data when it exceeds the budget instead of creating an unbounded array. That is only a **total-byte check**; a production parser must also bound token lengths and nesting. `BufferedReader.readLine()` can still create a massive `String` if a single line is extraordinarily long, even though the file is read line by line.

Do not trust client-supplied `Content-Length` alone; you must actually **enforce the number of bytes received**, while distinguishing compressed size from decompressed size.

## 11. Bounded Caches: GC Does Not Automatically Remove Referenced Objects

A cache such as:

```java
static final java.util.Map<String, byte[]> CACHE =
        new java.util.HashMap<>();

static void put(String key, byte[] value) {
    CACHE.put(key, value);
}
```

is a **risk-identifying snippet**. If new keys keep growing, the static map still references the payloads; the GC will not automatically reclaim them based on business intent.

Choose measures such as eviction, TTL, bounding **entry count**, or even better, bounding **byte weight** when objects vary widely in size. Monitor cache hit ratio, total size, eviction count, and lifecycle. `WeakHashMap` is also **not a default bounded cache**: it evicts based on weak references to keys and has significant caveats if values reference keys back.

### Runnable program: a three-entry cache

Create the file **`BoundedCacheDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class BoundedCacheDemo {
    static class LimitedMap extends LinkedHashMap<Integer, String> {
        private final int capacity;

        LimitedMap(int capacity) {
            this.capacity = capacity;
        }

        @Override
        protected boolean removeEldestEntry(
                Map.Entry<Integer, String> eldest) {
            return size() > capacity;
        }
    }

    public static void main(String[] args) {
        LimitedMap cache = new LimitedMap(3);

        for (int i = 1; i <= 5; i++) {
            cache.put(i, "value-" + i);
        }

        System.out.println("size=" + cache.size());
        System.out.println("keys=" + cache.keySet());
    }
}
```

```bash
javac BoundedCacheDemo.java
java BoundedCacheDemo
```

`stdout`:

```text
size=3
keys=[3, 4, 5]
```

Because `LinkedHashMap` preserves insertion order by default, the oldest entries are evicted when exceeding size 3. This is a simple learning technique with **no synchronization** and **no total payload byte limit**. In multi-threaded applications, use an appropriate thread-safe cache structure and a system-wide budget.

## 12. Bound Both the Thread Pool **and** the Task Queue

Limiting the number of workers is not enough if the task queue is unbounded. A huge queue can retain closures and payloads for millions of requests.

For example:

- `Executors.newFixedThreadPool(n)` has a fixed worker count but an **unbounded default queue**.
- `Executors.newCachedThreadPool()` can create additional threads under load and needs practical bounding policies.
- `CompletableFuture` or framework queues can retain waiting state for a long time.
- Unbounded retries can generate additional tasks and data when the system is already overloaded.

Use bounded queues, admission control, semaphores, backpressure, or controlled rejection; decide based on latency requirements and idempotency.

### Runnable program: bounded executor

Create the file **`BoundedExecutorDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedExecutorDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.CallerRunsPolicy());

        AtomicInteger done = new AtomicInteger();

        for (int i = 0; i < 6; i++) {
            pool.execute(done::incrementAndGet);
        }

        pool.shutdown();
        boolean terminated =
                pool.awaitTermination(5, TimeUnit.SECONDS);

        System.out.println("terminated=" + terminated);
        System.out.println("completed=" + done.get());
    }
}
```

```bash
javac BoundedExecutorDemo.java
java BoundedExecutorDemo
```

`stdout` in a normal scheduling environment:

```text
terminated=true
completed=6
```

The queue holds at most 2 tasks; there is one worker; when saturated, `CallerRunsPolicy` can make the submitting thread run the task to create backpressure. After submitting all six tasks, the program shuts down and waits for them to finish, so the counter is 6 given sufficient wait time.

**Limitations:** `CallerRunsPolicy` is not a solution for every application; it can increase caller latency or cause side effects on the request thread. Once the executor is shut down, this handler can drop tasks according to its contract. Even a bounded queue does not bound all memory used outside of it. In real overload environments, include timeouts, rejection, and observability.

## 13. When Is Local Recovery Possible?

There is no general Java rule that **every OOME must kill the JVM**, yet there is also no guarantee that serving can safely continue. Local recovery is only worth considering if the application has **concrete evidence**:

- The error is isolated to a **partition/task** with clear ownership and state.
- Resources can be safely reclaimed.
- Data invariants and transactions have been restored or can be verified.
- The failure does not leak into other threads, shared caches, singletons, or class initialization.
- Memory pressure has dropped according to reliable metrics.
- Any retry is idempotent, bounded, and uses backoff.
- Operators accept the residual risk and can terminate the instance remotely.

For most backend services, these conditions are **hard to prove when the JVM is genuinely out of resources**. A more reliable policy is to treat the instance as **no longer ready to serve**, emit a best-effort signal, and use an **out-of-process supervisor** to replace it.

### Restarting does not fix the root cause

Restarting clears the failed process's state and gives it a chance to serve again, but if a heap leak, class-loader leak, unbounded queue, or unbounded input remains, the new instance can OOME again. You must fix the **design, configuration, and workload root causes** and verify under load testing.

## 14. Process Boundary: Detection, Fail-Fast, and Restart

A practical model:

```text
Application with memory budget and health checks
                   |
                   v
             OOME or OOM kill
                   |
                   v
        Instance is no longer trustworthy
                   |
                   +--> Best-effort error signal (if still executing)
                   +--> Stop/exit per JVM and service policy
                   |
                   v
  Service manager / container orchestrator (outside the JVM)
                   |
                   +--> Detects dead process, failed health check, lost heartbeat
                   +--> Applies restart policy / backoff
                   v
             Starts new instance
                   |
                   +--> Checks readiness
                   +--> Reconciles data and unfinished tasks
                   v
             Accepts workload again
```

If the process is killed directly, Java code may **not be able to write any logs**. That is why out-of-process tooling is essential.

When deciding to stop the process:

- `System.exit(...)` requests JVM shutdown and may run shutdown hooks. Hooks can require memory, I/O, or locks; **they are not guaranteed to run cleanly during a real OOME**.
- `Runtime.halt(...)` terminates more abruptly, skipping shutdown hooks and potentially losing unflushed data. Do not use it casually as a memory fix.
- HotSpot JVM flags can assist with process exit/crash on OOME, configured according to operational policy and JVM support.

**Do not scatter `System.exit` calls into business methods** just because an OOME was caught. That is an operational-layer decision to protect the overall system.

### Ensuring data integrity across restarts

Services requiring consistency typically use transactions, idempotency keys, durable queues, the outbox/inbox pattern, checkpoints, and reconciliation. If a process dies mid-write, a restart **does not automatically undo** all side effects; the system must know which steps committed and which need safe replay or compensation.

## 15. Diagnostic JVM Options (HotSpot Java 17)

The following options are **configuration examples**, not commands to trigger errors:

```bash
java -Xms128m -Xmx512m -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=./diagnostics -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
```

`app.jar` is provided by the application; the dump path must exist and be writable. The 128/512 MiB memory settings are only examples, **not recommended levels** for every workload.

| Option | Meaning |
| --- | --- |
| `-Xms128m` | Sets the initial heap size on HotSpot |
| `-Xmx512m` | Maximum Java heap limit, excluding total native RSS |
| `-XX:+HeapDumpOnOutOfMemoryError` | Requests generating a heap dump on eligible JVM OOMEs, on a best-effort basis |
| `-XX:HeapDumpPath=...` | Specifies where to save the dump |
| `-Xlog:gc*...` | Writes GC information using the JVM's unified logging |

Heap dumps can be **very large** and contain secrets, tokens, PII, request payloads, and transaction details. Protect read permissions, disk space, and retention. Dump creation is never guaranteed: lack of disk space, an external OOM kill, native failures, or other severe conditions can prevent collection.

### Fail-fast flags

Some HotSpot JVMs support:

```text
-XX:+ExitOnOutOfMemoryError
-XX:+CrashOnOutOfMemoryError
```

These are **implementation-specific JVM flags**, not Java source syntax or guarantees across all JVM vendors. Choose based on evidence retention, core dump, restart, and supervisor requirements. Test on your specific JDK/JVM before using in production.

### What should you collect?

- Heap usage: **used, committed, max**, allocation rate, and GC data.
- Metaspace/class loaders, loaded class count.
- Direct/mapped buffer pools, native memory, and thread count.
- Process RSS, cgroup/container memory, host OOM events.
- Queue lengths, active requests, cache entries, payload sizes.
- Timing of memory growth relative to deploys, workloads, and new releases.
- Heap dumps and GC logs from a **controlled environment**, avoiding heavy tracing that adds extra pressure.

NMT (`Native Memory Tracking`) in HotSpot is useful for inspecting certain JVM native allocation categories, but it requires configuration and has overhead; it is not guaranteed to capture all memory from every native/JNI library.

## 16. Investigating Heap Dumps: Retaining References and Retained Size

Once you confirm the issue is in the Java heap and have a valid heap dump:

1. Open the dump with Eclipse Memory Analyzer, VisualVM, or a compatible JVM tool.
2. Inspect the histogram: which classes have many instances or many shallow bytes.
3. Inspect the **dominator tree** and retained size.
4. Follow **paths to GC roots** to see which objects keep data alive.
5. Focus on caches, static maps, `ThreadLocal`, listeners, request/session objects, queues, and buffer arrays.
6. Distinguish a **memory leak** from a large dataset that is still needed or a legitimate allocation spike.
7. Compare snapshots over time if you have a safe way to collect them.
8. Fix data lifecycles/limits; run load tests to prove memory stabilizes.
9. Clean up and protect dumps since they may contain sensitive data.

**Shallow size** is the direct memory of a single object. **Retained size** is the amount of heap indirectly freed if that object no longer retains the associated graph. A `HashMap` with a tiny shallow size can still retain millions of payloads behind it.

If the OOME involves threads, native memory, or metaspace, analyzing a heap dump alone **may not reveal the full cause**; check metrics for the corresponding memory region.

## 17. OOME vs. `StackOverflowError` and Common Business Errors

| Type | Branch | Typical meaning |
| --- | --- | --- |
| `OutOfMemoryError` | `VirtualMachineError` | Cannot satisfy a memory/resource allocation |
| `StackOverflowError` | `VirtualMachineError` | A thread's stack exceeded its limit, often due to recursion |
| `InternalError` | `VirtualMachineError` | Internal runtime failure |
| `ArithmeticException` | `RuntimeException` | For example, integer division by 0 |
| `IOException` | Checked `Exception` | Input/output error that must be handled/declared |

Do not conflate `StackOverflowError` with OOME. Increasing `-Xmx` does not directly fix infinite recursion. An `IOException` or `ArithmeticException` can follow business error-handling flows; OOME should not be routed into the same handler and return a normal response.

## 18. Common Pitfalls to Avoid

**"Every OOME means the Java heap is full."** False. You must consider metaspace, native buffers, thread resources, VM limits, and the OS/container.

**"If OOME is caught, the service has recovered."** False. The JVM staying alive does not prove the application and data are consistent.

**"`catch (Exception)` catches every `Throwable`."** False. It does not catch `Error`.

**"`catch (Throwable)` and returning a success response is fine."** Dangerous: it can hide critical errors and propagate untrustworthy state.

**"`System.gc()` is guaranteed to free enough memory."** False. It does not reclaim reachable objects, and explicit GC carries no such guarantee.

**"`finally` is guaranteed to run even if the process is killed."** False.

**"TWR always finishes closing every resource even when the JVM is out of memory."** There is no absolute guarantee during a catastrophic failure.

**"If a simulated OOME and catch run, recovery in a real OOME will run too."** False. Throwing a small `Error` object does not exhaust memory.

**"Having a heap dump means it captures all native memory."** False. A heap dump primarily reflects Java heap state.

**"No heap dump means there was no OOME."** False. The process may have been killed directly or unable to write a dump.

**"`-Xmx` is the total RAM limit of the process."** False. Native memory, metaspace, and thread stacks also consume memory outside the heap.

**"Increasing `-Xmx` always fixes OOME."** False. Sometimes it makes container native RAM starvation worse.

**"GC will automatically clear a static cache even if the application still holds references."** False.

**"A fixed thread pool has a bounded queue by default."** False for common configurations from `Executors.newFixedThreadPool`.

**"Line-by-line streaming can never have large inputs."** False. A single line or token can be abnormally long.

**"Checking `Content-Length` alone blocks all large payloads."** False. Inputs can misreport it, and decompressed data can be much larger.

**"If static class initialization fails, accessing it again will automatically retry."** False. The class may remain in an erroneous state.

**"An emergency buffer guarantees logging and saving the JVM."** False. It is best-effort and does not address many other OOME sources.

**"Restarting is how you fix a memory leak."** False. Restarting recovers an instance; the root cause still must be fixed.

**"Heap dumps can be shared publicly for debugging."** Dangerous. Dumps can contain sensitive data.

## 19. Self-Check Exercises

1. **Is OOME checked or unchecked?** Unchecked, because it is under `Error`.
2. **Does `catch (Exception)` catch OOME?** No.
3. **Can the JVM stay alive after throwing OOME?** Possibly, but safe serving is not guaranteed.
4. **Does an OS OOM kill let Java catch OOME first?** Not necessarily; the process can die directly.
5. **Does increasing `-Xmx` reliably fix direct/native OOME?** No.
6. **Does `System.gc()` reclaim objects still referenced by a static map?** No.
7. **Does a fixed thread pool usually have a bounded default queue?** No.
8. **Does a 3-entry cache guarantee low memory usage?** No, each entry's payload could be huge.
9. **How do you prevent an allocation from an arbitrary request asking for a 2 GB array?** Size validation, pre-allocation budgets, and streaming where appropriate.
10. **Does `try-with-resources` running on a simulated OOME guarantee it runs during an OS kill?** No.
11. **What can an OOME during static initialization cause on the next class access?** `NoClassDefFoundError`.
12. **Why can an OOME in one request affect other requests?** Heap/native resources and shared state are process-wide resources.
13. **What is the risk of catching OOME and retrying immediately?** Repeating memory pressure and duplicating side effects of unknown status.
14. **Why shouldn't you log a full JSON stack trace inside an OOME catch block?** Logging can require allocations/resources that are no longer available.
15. **Does `Runtime.freeMemory()` represent all free physical RAM?** No.
16. **What should you investigate when an OOME reports Metaspace?** Class loaders, class counts, metaspace limits, and native usage.
17. **Can heap dump creation be guaranteed when a process is terminated by the OOM killer?** No.
18. **How is retained size useful for leak investigation?** It shows which objects keep other objects reachable.
19. **If the error is caused by an array exceeding the VM limit, is more GC guaranteed to help?** No.
20. **Why is an out-of-JVM supervisor needed?** To detect and replace the process when in-process code can no longer run reliably.
21. **Does a restart automatically roll back external transactions?** No; you need transactions, idempotency, and reconciliation.
22. **Are `OutOfMemoryError` and `StackOverflowError` the same class?** No, they are two subtypes of `VirtualMachineError`.
23. **Should you prioritize bounding input/cache/queues or waiting to catch OOME?** Prioritize prevention first.
24. **What does `new OutOfMemoryError("simulated")` prove?** Only exception flow in a normal JVM, not real recovery.

## 20. Official Java 17 Documentation

- [Java SE 17 — OutOfMemoryError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/OutOfMemoryError.html): meaning when the virtual machine cannot allocate required memory.
- [Java SE 17 — VirtualMachineError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/VirtualMachineError.html): virtual machine error hierarchy.
- [Java SE 17 — Error](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Error.html): serious problems that a reasonable application should not try to catch.
- [Java SE 17 — Runtime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `gc`, `maxMemory`, `freeMemory`.
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): queues, worker limits, rejection.
- [Java SE 17 — LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html): `removeEldestEntry`.
- [Java SE 17 — MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap and non-heap telemetry.
- [Java SE 17 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): direct/mapped buffer pool information.
- [Java Language Specification 17 — `11 Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html): checked/unchecked and `Throwable` propagation.
- [Java Language Specification 17 — `12.4.2 Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): erroneous class state after initialization failure.
- [Java Language Specification 17 — `14.20.3 try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): cleanup and suppressed exceptions.
- [Java SE 17 — java launcher options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xmx`, heap dumps, logging, and HotSpot flags.
- [Java SE 17 — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): JVM diagnostics.

**Takeaway:** `OutOfMemoryError` is an **unchecked `VirtualMachineError`**, not merely "heap full." The fact that the JVM stays running or a handler catches it **does not guarantee** that memory, class initialization state, resources, and business data have recovered. Sound design focuses on **budgets, streaming, cache eviction, bounded concurrency, monitoring, diagnosing the right memory region, fail-fast behavior, and out-of-process instance replacement**. Examples that throw a simulated OOME are only lessons on Java semantics, not proof that a memory-exhausted JVM can continue serving safely.
