# Throughput, Latency, and Memory Footprint

When evaluating a Java application, measuring the execution time of a single operation is not enough. A service might process many requests per second while responding slowly to some users; an application might have low latency under light load yet saturate quickly under high concurrency; or it might achieve strong throughput while consuming too much memory to run reliably inside a container.

Three groups of metrics must be examined together:

- **Throughput:** the amount of work completed per unit of time, typically requests/second or operations/second.
- **Latency:** the time from when an operation is submitted until a result is produced, typically measured in milliseconds and analyzed by percentiles.
- **Memory footprint:** the amount of memory an application uses, including heap, off-heap regions, and process native memory.

In Java 17, you can observe these metrics with Java Flight Recorder (JFR), `jcmd`, unified GC logging, Java Management APIs, and benchmarking tools like JMH. Always measure on a representative workload, because the results of a small microbenchmark do not automatically predict whole-service performance.

## 1. Throughput

Throughput represents the volume of work completed over a period of time. Depending on the application, units may be:

- HTTP requests/second (RPS).
- Messages/second.
- Database transactions/second.
- Operations/second.
- Records/second in a data-processing pipeline.

If a system completes 12,000 requests in 60 seconds, the average throughput over that window is:

\[
\text{throughput} = \frac{12\,000}{60} = 200 \text{ requests/second}
\]

Distinguish **offered load** (the request rate sent by clients) from **achieved throughput** (the request rate the system actually completes). When overloaded, clients may send 500 requests/second while the server only completes 350 requests/second; the remainder may queue, be rejected, or time out.

### 1.1. Throughput is not the same as single-request speed

A fast individual request does not guarantee high system throughput. If every request requires an exclusive connection, a global lock, or sequential I/O, other requests must wait.

Conversely, a system can process many requests concurrently and achieve high throughput even if each request takes tens of milliseconds.

Example:

| System | Throughput | Average latency |
| --- | ---: | ---: |
| A | 100 requests/s | 5 ms |
| B | 1,000 requests/s | 40 ms |

B completes more requests per second, yet each request on B takes longer. You cannot conclude B is better than A without knowing business targets, latency percentiles, error rates, and resource consumption.

### 1.2. Throughput can saturate

As concurrency increases, throughput often rises initially because CPUs, workers, and connections are utilized more efficiently. Beyond a point, a resource becomes a bottleneck:

- CPU nears saturation.
- Thread pool runs out of workers.
- Connection pool runs out of connections.
- Locks or queues cause contention.
- GC consumes heavy CPU.
- A database or downstream service cannot keep up.

Past the saturation point, adding concurrency may only lengthen queues and increase latency while throughput plateaus or drops.

## 2. Latency

Latency is the time from when an operation starts until it completes from the measured viewpoint. For HTTP, it may be measured from when the client sends a request until the full response arrives; on the server side, it may be measured from when the request enters until the response is ready.

Clearly define the start and end points. Method latency inside the JVM is not the same as end-to-end request latency across networks, proxies, applications, databases, and downstream services.

### 2.1. Why not look only at the average?

Latency is rarely evenly distributed. Most requests may be fast while a small subset is very slow due to GC pauses, lock contention, I/O, queueing, or background activity.

Common percentiles:

| Metric | Meaning |
| --- | --- |
| p50 | 50% of requests complete in this time or faster; median |
| p90 | 90% of requests complete in this time or faster |
| p95 | 95% of requests complete in this time or faster |
| p99 | 99% of requests complete in this time or faster |
| p99.9 | 99.9% of requests complete in this time or faster |

Example:

| Metric | Latency |
| --- | ---: |
| p50 | 18 ms |
| p95 | 75 ms |
| p99 | 420 ms |
| p99.9 | 1,800 ms |

A 18 ms median looks healthy, yet the slowest 1% of requests take around 420 ms or more. For systems requiring snappy responses, tail latency can matter more than the mean.

Report histograms or percentiles together with sample counts. Do not average percentiles across multiple instances to infer system-wide percentiles; merge histograms or distribution data properly instead.

### 2.2. Service time and queueing time

A request can spend time in several places:

~~~text
Client sends
   |
   v
Network / Load balancer
   |
   v
Request queue
   |
   v
Application processing
   |
   +--> Database / remote service
   |
   v
Response serialization
   |
   v
Client receives full response
~~~

End-to-end latency combines waiting time and processing time across involved components. A Java method might execute in 2 ms while the request takes 200 ms waiting for a worker or database connection.

When optimizing, break down latency to identify whether time is spent in CPU, queues, locks, I/O, or external services. Optimizing a method that accounts for 1% of total time will not meaningfully improve end-to-end latency.

### 2.3. Tail latency and queueing effects

When load approaches maximum capacity, a small number of slow requests can trigger a cascading effect:

1. Slower requests hold workers or connections longer.
2. Incoming requests must wait in the queue.
3. Queueing time raises latency.
4. Workers remain occupied, preventing throughput from rising.
5. Timeouts and retries can generate extra load.

Unbounded retries can worsen the situation by injecting new requests into an already overloaded system. Use timeouts, concurrency limits, backpressure, and controlled retry policies.

## 3. Relationship between throughput, latency, and concurrency

A helpful law in stable systems is **Little's Law**:

\[
L = \lambda W
\]

Where:

- \(L\): average number of requests in the system (in-flight or waiting).
- \(\lambda\): average throughput, in requests/second.
- \(W\): average time a request spends in the system, in seconds.

For example, if a system completes an average of 200 requests/second and each request spends an average of 0.1 seconds in the system:

\[
L = 200 \times 0.1 = 20
\]

On average, roughly 20 requests are being processed or waiting at any given time.

Little's Law describes average relationships under steady-state conditions; it is not a formula to pick optimal concurrency or predict latency percentiles. If queues grow continuously, the system is not in steady state and averages must be interpreted cautiously.

### 3.1. Increasing concurrency does not always increase throughput

Adding threads or concurrent requests can hide I/O latency and utilize CPUs better. Beyond an appropriate level, however:

- Threads contend for CPU and context switching increases.
- The heap must retain more concurrent requests/objects.
- Longer queues raise latency.
- Connection pools or databases become bottlenecks.
- GC must manage more live objects and concurrent allocations.

Concurrency should be tuned to the real capacity of CPUs, memory, databases, and downstream services. No single thread count fits every application.

## 4. Memory footprint of a Java application

A Java application does not use only the heap. Process memory typically spans several regions:

~~~text
Java Process
|
+-- Java Heap
|   +-- Objects
|   +-- Arrays
|   +-- Collections
|
+-- Non-heap / JVM-managed
|   +-- Metaspace (class metadata)
|   +-- Code Cache (JIT compiled code)
|
+-- Native memory
|   +-- Thread stacks
|   +-- Direct buffers
|   +-- GC / JVM internal structures
|   +-- JNI / native libraries
|
+-- Memory-mapped files and OS-managed regions
~~~

Detailed categorization depends on the JVM implementation and operating system. Remember that **-Xmx only caps the Java heap**, not the total RAM a process can consume.

### 4.1. Heap

The heap is the memory area the JVM uses to allocate most objects and arrays. **-Xmx** sets the maximum heap limit; **-Xms** sets the initial/minimum heap size per JVM configuration.

Example:

~~~bash
java -Xms512m -Xmx2g -jar application.jar
~~~

Here the initial heap is 512 MiB and the maximum limit is 2 GiB. This is purely a syntax example, not a general recommendation for all containers or hosts.

The heap is managed by the garbage collector. **used** is the heap currently occupied at the time of observation; it may include objects that will be reclaimed in the next GC. **committed** is the heap capacity the JVM has committed for use; **max** is the reported upper limit, which may be undefined in some environments.

### 4.2. Live set and retained memory

After GC reclaims unreachable objects, the remaining live objects are roughly called the live set. This is a key metric when determining how much heap is actually needed.

If heap used rises before GC and drops significantly after GC, the application may simply be creating many short-lived objects. If post-GC heap climbs steadily over time under the same workload, objects may be retained longer than expected or a cache/queue may be unbounded.

Do not conclude there is a memory leak from a single heap increase. Observe trends across multiple cycles, comparable workloads, and heap dumps/JFR when investigation is needed.

### 4.3. Metaspace

Metaspace stores class metadata and is managed in native memory. Loading many classes, generating dynamic classes, or retaining class loaders can cause this region to grow.

Applications with plugins, proxy-generating frameworks, or hot reload should watch class loader lifecycles. If a class loader cannot be collected because references remain, metadata for classes belonging to that loader may remain retained.

Metaspace is outside the heap, so increasing **-Xmx** does not directly solve uncontrolled metaspace growth.

### 4.4. Code Cache

The JIT compiler compiles bytecode into machine code and stores it in the Code Cache. This is a JVM-managed memory area distinct from the Java heap.

The Code Cache can vary with the number of compiled methods and optimization activity. Do not add it to heap used or assume **-Xmx** controls it.

### 4.5. Direct buffers and native memory

**ByteBuffer.allocateDirect(...)** allocates off-heap memory to support certain I/O or binary data operations:

~~~java
ByteBuffer buffer = ByteBuffer.allocateDirect(1024 * 1024);
~~~

Direct buffer capacity is not counted like an ordinary byte array on the heap. Still, it consumes process memory and has its own limits and management costs.

In addition, JNI, native libraries, thread stacks, GC internal structures, and memory mappings can make process memory exceed committed heap.

### 4.6. Thread stacks

Each platform thread has its own stack. Many concurrent threads can increase native memory substantially even when the heap does not grow proportionally.

Stack size can be configured with **-Xss**, though lowering it too far can cause **StackOverflowError** in code with deep call chains. Raising thread counts also raises total stack demand and scheduling overhead.

## 5. Distinguishing heap, process RSS, and container limits

Three numbers are frequently confused:

| Metric | What does it measure? | What cannot be inferred directly |
| --- | --- | --- |
| Heap used | Objects/arrays occupying the heap at measurement time | Total process RAM |
| Heap committed | Heap the JVM has committed for use | All native memory |
| Process RSS | Process memory pages currently resident in RAM per the OS | Heap alone or live object volume |
| Container memory usage | Memory usage recorded by cgroups/container runtime | Heap used alone |

A process with **-Xmx=2g** can still consume more than 2 GiB of RAM because of metaspace, code cache, stacks, direct buffers, and native allocations. In containers, leave headroom for these regions and for any auxiliary processes.

Java 17 HotSpot supports container limit awareness on supported platforms. **-XX:MaxRAMPercentage** can control the fraction of RAM used to calculate maximum heap, yet that fraction remains a heap budget, not a cap on total process memory.

Example:

~~~bash
java -XX:MaxRAMPercentage=60 -jar application.jar
~~~

60% merely illustrates syntax. Choose the percentage based on container memory limit, native memory, thread count, direct buffers, workload, and operational headroom. If **-Xmx** is set explicitly, it governs max heap instead of the default percentage calculation.

## 6. Allocation rate and garbage collection

**Allocation rate** is how quickly the application creates new objects, often measured in bytes/second. It differs from the live set:

- High allocation rate can come from many short-lived objects.
- High live set means many objects remain reachable after GC.
- An application can have a high allocation rate yet a small live set.
- An application with a low allocation rate can still hold a large cache in the heap.

Example:

~~~java
public static long countWords(String[] words) {
    long total = 0;

    for (String word : words) {
        String normalized = word.trim().toLowerCase();
        total += normalized.length();
    }

    return total;
}
~~~

Depending on data and JIT optimizations, these operations may allocate temporary objects. If the method is called very frequently, allocation rate can climb. Still, do not look at source code alone and assume objects are definitely allocated; the JIT may optimize some cases via escape analysis or scalar replacement.

### 6.1. How GC affects throughput and latency

GC requires CPU and can introduce stop-the-world pauses. The impact depends on collector, heap, allocation pattern, object lifetimes, and configuration:

- CPU spent on GC can reduce CPU available for business logic.
- Pauses can raise latency, especially in the tail.
- An undersized heap can cause frequent GC.
- Larger heaps can reduce GC pressure in some workloads while increasing footprint and not guaranteeing shorter pauses.
- Long-lived objects increase old-region/live-set management work.

No single collector or heap size is optimal for every application. Measure with a representative workload and concrete latency/throughput goals.

### 6.2. Do not use System.gc() as a memory management strategy

Calling **System.gc()** only makes a hint/request to the JVM; it is not a command guaranteeing unused objects are immediately freed. Calling it frequently can disrupt the application and skew measurements.

Focus on reference lifetimes, cache/queue bounds, allocation patterns, and GC configuration. Use explicit GC mechanisms only for concrete operational reasons after measuring the impact.

## 7. Measuring heap and non-heap with Java Management APIs

Java provides **MemoryMXBean** to read heap and non-heap usage. It is a standard API in package **java.lang.management**.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

public class MemoryUsageDemo {
    public static void main(String[] args) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();

        print("heap", memory.getHeapMemoryUsage());
        print("non-heap", memory.getNonHeapMemoryUsage());
    }

    private static void print(String name, MemoryUsage usage) {
        System.out.printf(
                "%s: used=%d MiB, committed=%d MiB, max=%d MiB%n",
                name,
                toMiB(usage.getUsed()),
                toMiB(usage.getCommitted()),
                toMiB(usage.getMax())
        );
    }

    private static long toMiB(long bytes) {
        return bytes < 0 ? bytes : bytes / (1024 * 1024);
    }
}
~~~

**MemoryUsage.getMax()** can be negative if undefined. The example above preserves negative values rather than displaying them as actual capacities.

**getNonHeapMemoryUsage()** reports non-heap metrics as defined by the JVM; it does not include all types of native allocations such as direct buffers or all memory allocated by native libraries. Do not use this API alone to infer total process memory.

### 7.1. Tracking GC counts and times

You can read collector statistics via **GarbageCollectorMXBean**:

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

for (GarbageCollectorMXBean gc :
        ManagementFactory.getGarbageCollectorMXBeans()) {

    System.out.printf(
            "%s: collections=%d, collectionTime=%d ms%n",
            gc.getName(),
            gc.getCollectionCount(),
            gc.getCollectionTime()
    );
}
~~~

Some values may be **-1** if the implementation does not provide the data. **collectionTime** is an accumulated MXBean metric whose precision depends on the JVM; do not treat it as an exact measurement of individual pauses. Use JFR and GC logs when detailed analysis is needed.

## 8. Observing GC with unified logging in Java 17

Java 17 uses unified JVM logging. Enable GC logging at startup with:

~~~bash
java -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar application.jar
~~~

Logs help observe:

- GC start and end times.
- Heap before/after GC.
- Recorded pause durations.
- Collector phases and activity.
- Safepoints related to pausing application threads.

Configure logging to suit the deployment environment: write to files with appropriate rotation/retention to avoid unbounded growth or filling small filesystems.

### 8.1. Reading logs alongside latency

If p99 spikes align with long GC pauses, GC may be a contributor. Still, temporal correlation alone is insufficient for proof. Cross-check with CPU, thread scheduling, locks, I/O, and queues.

If GC logs show frequent young collections with short pauses, the bottleneck may lie elsewhere. If old-generation occupancy climbs steadily, investigate live set and retention. If GC CPU is high, examine allocation rate and object lifetimes.

## 9. Using Java Flight Recorder to find root causes

Java Flight Recorder (JFR) is built into the JDK and can record many runtime events with typically low overhead when appropriately configured. It supports analyzing CPU, allocations, GC, lock contention, threads, I/O, and other JVM events.

Start a 60-second recording:

~~~bash
jcmd <pid> JFR.start name=performance settings=profile duration=60s filename=performance.jfr
~~~

**<pid>** is the Java application's process ID. After the recording completes, view a summary:

~~~bash
jfr summary performance.jfr
~~~

You can open the **.jfr** file with Java Mission Control to inspect:

- Which methods consume CPU.
- Which classes/methods perform heavy allocations.
- GC events and pauses.
- Blocked threads or lock waits.
- Slow socket/file I/O.
- Thread states and JVM activity.

### 9.1. JFR and heap dumps answer different questions

JFR is useful for observing behavior over a time window: where allocations happen, what threads wait on, and how GC operates.

A heap dump is a point-in-time snapshot of the object graph, useful for finding retained objects and paths to GC roots. Capturing a heap dump can take significant time and disk space and may impact the application; follow proper operational procedures.

Not every memory issue requires a heap dump. Start with metrics, GC logs, and JFR; capture a heap dump only when you need to inspect specific retained objects.

## 10. Native Memory Tracking and off-heap memory

When process RSS is much higher than committed heap, inspect native memory. HotSpot offers **Native Memory Tracking (NMT)** to summarize several internal JVM allocation categories.

NMT must be enabled at JVM startup:

~~~bash
java -XX:NativeMemoryTracking=summary -jar application.jar
~~~

Or select greater detail:

~~~bash
java -XX:NativeMemoryTracking=detail -jar application.jar
~~~

Then use `jcmd`:

~~~bash
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
~~~

The **baseline** command records a reference point for comparison; **summary.diff** shows changes since that baseline. NMT adds overhead and does not track every allocation by every native library or all aspects of how the OS counts RSS. Use the output as a diagnostic input, not as the sole comprehensive measurement.

### 10.1. Investigating direct buffers

**BufferPoolMXBean** provides metrics on buffer pools, including the direct buffer pool on supported JVMs:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {

    System.out.printf(
            "%s: count=%d, used=%d MiB, capacity=%d MiB%n",
            pool.getName(),
            pool.getCount(),
            pool.getMemoryUsed() / (1024 * 1024),
            pool.getTotalCapacity() / (1024 * 1024)
    );
}
~~~

These metrics help when an application uses NIO or libraries backed by direct buffers. They do not represent all native memory.

## 11. Microbenchmarking with JMH

When comparing two implementations of a small operation, use **JMH (Java Microbenchmark Harness)** instead of hand-rolled loops with **System.currentTimeMillis()**.

The JVM applies JIT compilation, warmup, dead-code elimination, escape analysis, and workload-dependent optimizations. Ad-hoc benchmarks can accidentally measure startup cost, optimize away results, or create conditions far removed from production.

Example JMH benchmark:

~~~java
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
public class StringBenchmark {
    private String input;

    @Setup(Level.Trial)
    public void setup() {
        input = "  Java 17 performance  ";
    }

    @Benchmark
    public int normalizedLength() {
        return input.strip().toLowerCase().length();
    }
}
~~~

JMH is a separate benchmarking library, not bundled in the JDK. When running benchmarks:

- Provide enough warmup for the JVM to reach steady state.
- Use multiple forks to reduce JVM state carryover from earlier runs.
- Choose sufficient measurement iterations and duration.
- Return results or use **Blackhole** to avoid dead-code elimination.
- Keep inputs and environments equivalent when comparing.
- Check allocation rate if reducing GC pressure is a goal.

A typical run command after packaging benchmarks:

~~~bash
java -jar target/benchmarks.jar -f 3 -wi 5 -i 10
~~~

JMH fits isolated operation measurement. It does not replace end-to-end load testing when evaluating throughput and tail latency of services involving networks, databases, queues, and many threads.

## 12. Load testing to evaluate the whole system

To measure a service, generate a workload close to how users or other systems actually interact with it:

- Request mix across endpoints.
- Payload sizes and data distribution.
- Concurrent client counts.
- Request arrival rate (offered load).
- Error and timeout rates.
- Run duration long enough to observe GC, caches, and background activity.

Step up load incrementally to find the throughput saturation point and see where latency begins climbing. Do not measure only at low load and conclude the application scales.

### 12.1. Closed-loop and open-loop load

In a closed-loop test, each client typically waits for its previous request to finish before sending the next. When the server slows down, client send rate drops automatically; this can mask poor latency under heavy load.

In an open-loop test, request arrival rate is driven more independently of response time. This helps test the system under a defined offered load, though you must handle queue bounds and backpressure policies when the system falls behind.

Some load-testing tools offer coordinated-omission correction to reduce skew when requests are delayed by waiting for prior responses. When evaluating tail latency, understand your tool's load-generation model.

### 12.2. Observation matrix

At each load level, record at least:

| Category | Metrics |
| --- | --- |
| Workload | Offered RPS, achieved throughput, concurrent requests |
| Latency | p50, p95, p99, p99.9 given enough samples |
| Reliability | Error rate, timeouts, retries, rejected requests |
| CPU | Process CPU, per-thread CPU if needed, GC CPU |
| Heap | Used/committed/max, post-GC occupancy |
| GC | Frequency, pause duration, allocation rate |
| Native memory | RSS, direct buffers, metaspace, NMT if enabled |
| Runtime | Thread count, queue length, connection pool usage |

Measure across the same time window so changes can be correlated. A p99 spike occurring alongside rising queue length, thread count, and GC activity can point to interacting causes.

## 13. Optimizing throughput, latency, and memory in order

Do not optimize all three goals via scattershot tweaks without knowing the bottleneck. A practical workflow:

1. **Define goals:** e.g., p99 under 200 ms at 500 RPS, error rate below threshold, and memory within container limit.
2. **Establish a baseline:** measure workload, JVM config, CPU, heap, native memory, and latency distribution.
3. **Locate the bottleneck:** use JFR, GC logs, thread/queue metrics, and profiling to pinpoint where cost lies.
4. **Change one group of factors:** such as reducing allocations, tuning pools, improving queries, or reducing lock contention.
5. **Re-measure with the same workload:** compare throughput, p95/p99, error rate, and memory.
6. **Run a soak test:** run long enough to observe memory retention, cache growth, and long-term GC behavior.
7. **Keep headroom:** ensure stability under load growth or traffic bursts.

### 13.1. Reducing allocations when allocation rate is a bottleneck

If JFR shows high allocations and heavy GC CPU usage, consider:

- Avoiding unnecessary temporary objects in hot loops.
- Using buffers with clear lifecycles when processing large data.
- Avoiding repeated array/string copies when safe direct processing is available.
- Bounding caches and queues.
- Choosing data structures suited to the workload.
- Avoiding premature manual optimizations before a profiler proves real allocation cost.

Do not carelessly reuse mutable objects if doing so compromises thread safety or corrupts data. Reducing allocations only helps when semantics remain intact and improvements are measured.

### 13.2. Reducing retained heap

If the live set climbs over time, inspect structures retaining references:

- Static collections or singleton caches.
- Maps without eviction.
- Unbounded queues.
- Unremoved listeners/callbacks.
- ThreadLocals holding objects longer than a request's lifetime.
- Retained class loaders or plugins.
- Unintentionally retained tasks/`CompletableFuture`s.

Set size bounds and eviction policies on caches/queues. If an object remains reachable, GC cannot reclaim it merely because the application has stopped using it logically.

### 13.3. Adjusting heap and collectors

Raising **-Xmx** can help if the heap is genuinely too small for the live set and allocation pattern. However, raising the heap does not fix memory leaks, does not cap native memory, and can push total footprint past container limits.

Changing collectors or GC settings may improve one metric while worsening another. Evaluate throughput, pause distribution, CPU, and memory together. Confirm the active collector via GC logs or runtime tools rather than assuming from defaults.

## 14. Example container memory budget calculation

Suppose a container has a 4 GiB limit. Do not set max heap to the full 4 GiB because the process also needs native memory and safety headroom.

An illustrative budget might allocate:

| Component | Illustrative budget |
| --- | ---: |
| Java heap max | 2.5 GiB |
| Metaspace and Code Cache | 250 MiB |
| Thread stacks | 300 MiB |
| Direct buffers / native libraries / JVM native | 450 MiB |
| Headroom for fluctuations and OS | 500 MiB |
| **Total** | **4 GiB** |

This is not a fixed allocation formula. Actual figures must be measured on your application's workload and runtime. If direct buffers grow, thread counts are high, or native libraries consume significant memory, adjust the heap budget or cap those regions.

Crucially, total process/container memory must be observed alongside heap metrics. An application with low heap used can still hit container OOM due to native memory or RSS growth.

## 15. Common mistakes

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| Throughput rises but p99 worsens | Queueing, excessive concurrency, or stretched tail requests | Check latency histogram, queue length, and saturation point |
| Average latency looks good but users see slow requests | Tail latency hidden by the mean | Track p95/p99/p99.9 and sample counts |
| Adding threads does not increase throughput | CPU, locks, DB, or connection pool saturated | Find the bottleneck before raising concurrency |
| -Xmx 2 GiB yet process uses over 2 GiB | Heap excludes all native/non-heap memory | Measure RSS, NMT, direct buffers, stacks, and metaspace |
| Heap used rises before GC | Temporary objects are being allocated | Inspect allocation rate and GC logs |
| Post-GC heap rises continuously | Retained objects/caches/queues or leaks | Use JFR, heap dumps, and GC root analysis |
| GC pauses are short yet latency remains high | Bottleneck may be queues, I/O, locks, or external services | Decompose latency and inspect with JFR |
| Microbenchmark is fast yet production is slow | Differing workloads, warmup, concurrency, or I/O | Use JMH for methods and load tests for systems |
| Hand-written benchmarks give unstable results | JIT, dead-code elimination, timers, and warmup | Use JMH with proper forks/warmup/measurement |
| Container gets OOM killed even when heap is not full | Native memory or total footprint exceeds limit | Reserve headroom, measure RSS/NMT, and bound allocations |
| Shrinking heap raises latency | More frequent GC or live set near the cap | Measure GC/occupancy and size for the workload |
| Raising heap does not stop a memory leak | Objects remain reachable | Trace retention paths; fix ownership/caches/queues |

## 16. Practice exercises

### Exercise 1 — Compute throughput and latency

A test completes 30,000 requests in 120 seconds. Compute average throughput. Then explain why throughput alone is not enough to conclude the system performs well.

### Exercise 2 — Read percentiles

A report shows p50 = 20 ms, p95 = 80 ms, p99 = 600 ms. Explain what happens to the slowest requests and why the average does not adequately describe user experience.

### Exercise 3 — Apply Little's Law

A service completes 400 requests/second with an average time in system of 50 ms. Calculate the average number of requests in-flight or waiting. State the steady-state assumption.

### Exercise 4 — Observe heap and non-heap

Run **MemoryUsageDemo** on JDK 17. Record used, committed, and max. Allocate more objects in a controlled lifecycle and observe how the numbers change.

### Exercise 5 — Monitor GC

Launch an application with unified GC logging. Create a workload allocating short-lived objects and observe GC frequency, pre/post-GC heap, and pauses.

### Exercise 6 — Record JFR

Use `jcmd` to capture a recording while the application is under load. Inspect allocation, CPU, lock, and GC events. Identify one hotspot and explain it with metrics.

### Exercise 7 — Distinguish heap from process memory

Compare committed heap with process RSS. Explain why the two numbers differ. If direct buffers are used, check **BufferPoolMXBean**.

### Exercise 8 — Design a load test

Ramp offered load in steps. Record achieved throughput, p95/p99, error rate, CPU, GC, and memory. Identify the saturation point and state the bottleneck with evidence.

## 17. Principles to remember

- **Throughput** measures work completed; **latency** measures operation duration; **memory footprint** measures memory resources used by the process.
- Track both achieved throughput and offered load; throughput does not rise indefinitely as concurrency increases.
- Use p50/p95/p99 to expose tail latency; averages can mask very slow requests.
- Little's Law relates average requests in the system, throughput, and average residence time in steady state.
- **-Xmx** caps the Java heap, not total RSS or container memory.
- Distinguish allocation rate, live set, committed heap, metaspace, code cache, direct buffers, thread stacks, and native memory.
- Use JFR, unified GC logging, `jcmd`, Management APIs, and NMT to find root causes; understand each tool's scope and overhead.
- Use JMH for microbenchmarks and representative load tests for end-to-end throughput/latency.
- Change one factor at a time, re-measure on the same workload, and verify both performance and memory.
- Maintain headroom for native memory and load variance; never optimize one metric by destabilizing another.

In Java 17, performance must be evaluated across the full request lifecycle and the entire process memory footprint. When throughput, latency distribution, allocation/retained heap, and native footprint are measured together, teams can pinpoint actual bottlenecks, choose the right optimizations, and keep applications stable under real-world load.
