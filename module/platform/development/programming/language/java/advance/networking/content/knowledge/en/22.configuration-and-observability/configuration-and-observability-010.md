# Evaluating Performance Using Throughput, Latency Percentiles, CPU, and Memory Footprint

## Lesson Objectives

A Java networking service may handle a few test HTTP requests very quickly, yet become slow, fail, or run out of memory as load increases. To evaluate it properly, you need to examine **throughput**, **latency percentiles**, **CPU utilization**, and **memory footprint** within the **same measurement window**, along with success rates and workload conditions. Do not judge quality by a single requests/second number alone.

After this lesson, you will be able to:

- Clearly define **offered load, completed throughput, successful throughput/goodput, bytes/second, errors, and timeouts**.
- Use `System.nanoTime()` to measure elapsed time and distinguish between client end-to-end time, server processing, queue wait, and full response body.
- Calculate **p50, p90, p95, p99, p99.9** from raw observations using **nearest-rank**, recognize sample-count bias, and understand the risk of looking only at the average.
- Avoid averaging p95/p99 across multiple servers; know how to use raw samples or merge histograms/sketches.
- Understand **coordinated omission**, closed-loop versus open-loop load generators, and Little's Law `L = λW`.
- Measure **process CPU time** using the JDK MXBean, convert it to core-equivalents, and normalize by processors/quota.
- Distinguish **heap used/committed/max**, off-heap/direct buffers, RSS/native memory, allocation rate, GC, and memory leaks.
- Design benchmarks with warmup, sufficient measurement duration, consistent environment parameters, multiple repeats, and without accidentally benchmarking the load generator.
- Run two Java 17+ programs: a fixed-input percentile calculation example, and an HTTP mini benchmark with a real server/client over loopback.
- Use **JFR**, `jcmd`, MXBeans, GC logs, and profilers to find root causes when p99, CPU, or RSS behaves abnormally.

**Scope:** Java 17+ and standard JDK libraries; examples run on `127.0.0.1` with no Internet required. A mini benchmark on the same JVM only illustrates **how to measure**, not production performance certification.

## 1. Metrics That Describe the Same System Together

| Group | Definition | Unit | Questions to Clarify |
|---|---|---|---|
| **Throughput** | Number of work units completed in a time interval | req/s, messages/s, operations/s | Does "completed" include 4xx/5xx/timeouts? |
| **Goodput** | Number of **useful, successful** units per system criteria | success req/s, valid bytes/s | Is HTTP 200 with an invalid body counted as success? |
| **Latency** | Time from a defined start point to a defined completion point | ms, µs | Measured at client or server, TTFB or full body? |
| **p50/p95/p99** | Latency percentile thresholds, showing tail slowness | ms, µs | How many samples, and which percentile algorithm is used? |
| **CPU** | CPU processing time consumed by the process/threads | core equivalents, % CPU quota | One core or the entire host? |
| **Memory** | Memory used or committed by the JVM/process | MiB/GiB, allocations/s | Heap, RSS, or direct buffers? |
| **GC** | Collection activity/pauses and object reclamation cost | count, ms, pause distribution | Does GC explain the tail latency? |

**Observation principle:** same time window, same traffic mix, same latency boundary, and same environment. If RPS is taken from the morning, p99 from the night, CPU before deployment, and memory after GC, those numbers **do not form a causal picture**.

For a Java server, record the **run ID, JDK/GC, process PID, heap limit, CPU quota, service version, concurrency, payload, and measurement interval** before publishing results.

## 2. Defining Throughput Without Misleading Readers

Basic formulas:

~~~text
completed_throughput_req_per_s =
    number of completed HTTP attempts / measurement duration in seconds

successful_throughput_req_per_s =
    number of HTTP attempts meeting success criteria / measurement duration

error_rate =
    number of failed requests / number of completed requests or attempts per contract

body_transfer_bytes_per_s =
    total body bytes sent/received / measurement duration
~~~

You must state the **denominator**. If a request times out and finishes its future exceptionally, in Example B it is counted as a **failed completed attempt**. In a production dashboard, additionally distinguish dropped/rejected requests that never entered the server.

For example, in a test with 1,000 completed attempts in 2 seconds:
- 900 succeed: **completed throughput 500 req/s**.
- **Successful throughput 450 req/s**.
- **Error rate 10%**.

Both throughput results are meaningful; however, looking only at 500 RPS hides quality issues. A service returning HTTP `503` very quickly can have high completed RPS yet **low goodput**. Even `200` is not necessarily a success if the business body/schema is invalid.

### Offered Load vs. Achieved Throughput

- **Offered load**: the rate at which the client *intends* to send requests, or the target concurrency.
- **Achieved/completed throughput**: requests that completed at the measurement boundary.
- **Successful throughput**: operations that completed **correctly** per second.
- **Queue/backlog**: requests waiting on a connection pool, thread pool, upstream database, or server.

Increasing offered load does not guarantee achieved throughput will keep increasing. At the **saturation point**, RPS may plateau/drop while p99, timeouts, and rejects rise. "Max RPS" in an overloaded region is not necessarily a safe operating level with headroom.

### Do Not Forget bytes/s

An endpoint returning 5,000 responses/s × 1,024-byte body = 5,120,000 body bytes/s, **not counting** HTTP headers, TLS records, TCP/IP framing, ACKs, and retries. If you switch to a 1 MiB payload, network/memory can become the bottleneck even at a much lower RPS. When measuring SocketChannel, DatagramChannel, WebSocket, and HTTP, record **both messages/s and bytes/s** along with the message size distribution.

## 3. Choosing the Right Latency Measurement Boundary

Client-side end-to-end latency can include:

~~~text
start
  ├─ wait in client queue/connection pool
  ├─ DNS/TCP/TLS handshake when needed
  ├─ send request bytes
  ├─ wait in server accept/queue
  ├─ server processing, DB/upstream calls
  ├─ response traverses network/proxy
  └─ read full body or receive result per contract
end → latency = end - start
~~~

These metrics are **not interchangeable**:
- **Server handler time**: only the processing segment inside the handler.
- **Queue wait**: waiting for a worker/connection.
- **TTFB**: time from start until the first response byte per the measurement definition.
- **Full-response latency**: until the body has been completely read/consumed.
- **End-to-end client latency**: depending on the client, may include DNS/connect/TLS, pool waits, and callbacks.

For long-lived HTTP streaming or WebSockets lasting many minutes, do not treat the entire connection lifetime as "request latency"; use **message/event latency** according to the protocol.

In Java:

~~~java
long start = System.nanoTime();
try {
    operation();
} finally {
    double milliseconds =
        (System.nanoTime() - start) / 1_000_000.0;
}
~~~

This is a **snippet**, where `operation()` is a hypothetical method. `System.nanoTime()` is suitable for **measuring durations**, not UTC timestamps. `System.currentTimeMillis()` is a wall clock that can be adjusted and is poorly suited for short intervals.

**HTTP body trap:** with `HttpResponse.BodyHandlers.ofInputStream()`, the future can complete before the application finishes reading the stream. If you want to measure full-body latency, place the end point **after the stream has been read/closed according to the protocol**, rather than immediately when the `HttpResponse<InputStream>` object is returned. Example B uses `ofByteArray()`, so the full response body has already been received upon callback completion.

## 4. Mean, Median, and Tail Percentiles

Suppose 99 requests take 10 ms and one request takes 2,000 ms:
- **Mean** = (99 × 10 + 2,000) / 100 = **29.9 ms**.
- **p50** = 10 ms.
- **p99 by nearest-rank** = 10 ms.
- **Max** = 2,000 ms.

Even p99 with N=100 may not reveal a single worst outlier; to see rare tails, use p99.9/max and **many samples**.

| Metric | Interpretation |
|---|---|
| p50 | Roughly half of observations are no greater than this threshold |
| p90 | Roughly 90% of observations are no greater than this threshold |
| p95 | Start of observing the slowest 5% group |
| p99 | Tail threshold of the slowest ~1% |
| p99.9 | Rare tail, requiring very many samples to estimate |
| mean | Arithmetic average, sensitive to outliers |
| max | Slowest **observed** sample, not the future worst case |

### Calculating with Nearest-Rank

Given N observations sorted in ascending order and percentile p in (0, 100]:

~~~text
rank = ceil((p / 100) * N)
percentile = sorted[rank - 1]
~~~

In Example A with 100 observations: 1, 2, ..., 98, 600, 2,000 microseconds:
- p50 = 50 µs, p90 = 90 µs, p95 = 95 µs.
- p99 = 600 µs.
- p99.9 = 2,000 µs.
- Mean = 74.51 µs.

**There is no single percentile definition across all libraries.** Some tools interpolate quantiles, while others choose nearest-rank or approximate histograms. When comparing services, specify the algorithm/buckets and sample counts.

If N=20, nearest-rank p99 has rank ceil(19.8)=20 → **max**. If N=240, p99 is the **238th** sorted sample, meaning very few tail samples. Do not report p99.9 from a few hundred requests as a reliable estimate.

## 5. Example A: Deterministic Stdout for Percentiles and Throughput

This program uses **fixed** input to verify the formulas. It does **not** benchmark CPU or HTTP; it is a unit test of percentile knowledge.

Save the file as **`PercentileMathDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Locale;

public class PercentileMathDemo {
    static long nearestRank(long[] observations, double percentile) {
        if (observations.length == 0
                || percentile <= 0.0 || percentile > 100.0) {
            throw new IllegalArgumentException("Invalid sample or percentile");
        }
        long[] sorted = observations.clone();
        Arrays.sort(sorted);
        int index = (int) Math.ceil(
            percentile / 100.0 * sorted.length) - 1;
        return sorted[index];
    }

    public static void main(String[] args) {
        long[] latencyUs = new long[100];
        for (int i = 0; i < 98; i++) {
            latencyUs[i] = i + 1;
        }
        latencyUs[98] = 600;
        latencyUs[99] = 2_000;
        long total = 0;
        for (long v : latencyUs) total += v;

        System.out.println("samples: " + latencyUs.length);
        System.out.printf(Locale.ROOT, "mean_us: %.2f%n",
            (double) total / latencyUs.length);
        for (double p : new double[] {50, 90, 95, 99, 99.9}) {
            System.out.printf(Locale.ROOT, "p%s_us: %d%n",
                (p == Math.rint(p)
                    ? Integer.toString((int) p) : "99.9"),
                nearestRank(latencyUs, p));
        }
        long completed = 900;
        long elapsedNanos = 1_500_000_000L;
        System.out.printf(Locale.ROOT, "throughput_req_per_s: %.2f%n",
            completed * 1e9 / elapsedNanos);
        System.out.printf(Locale.ROOT, "little_law_inflight: %.2f%n",
            600.0 * 0.025);
    }
}
~~~

Compile/run on JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 PercentileMathDemo.java
java PercentileMathDemo
~~~

**Actual tested stdout:**

~~~text
samples: 100
mean_us: 74.51
p50_us: 50
p90_us: 90
p95_us: 95
p99_us: 600
p99.9_us: 2000
throughput_req_per_s: 600.00
little_law_inflight: 15.00
~~~

`900 requests / 1.5 seconds` and `L=600 × 0.025 = 15` are just **hypothetical illustrative data**, not a measurement of machine capacity. The code uses `Locale.ROOT` to print decimal points consistently and clones the array before sorting so it does not mutate the input.

### Why Not Use Average Instead of p99?

The data has two outliers: 600 and 2,000 µs. A mean of 74.51 µs can give the impression that a typical request takes ~75 µs even though the median is only 50 µs and one request took 2,000 µs. Therefore, p50, p95, p99, max, and timeout rate should be viewed together.

## 6. Little's Law: Relating Throughput, Latency, and Concurrency

In a **stable** system, Little's Law states:

~~~text
L = λ × W
L: average number of work items in the system
λ: average throughput (requests/second)
W: average time in system (seconds)
~~~

For example, 600 requests/s and **mean** end-to-end time of 25 ms:

~~~text
L = 600 × 0.025 = 15 in-flight requests
~~~

**Do not substitute p99 for W.** Little's Law requires the **mean** and the same system boundary. When queues are growing unboundedly, offered load differs from completion throughput, requests are dropped, or retries complicate things, the formula must be applied with the right set of work items and assumptions.

Increasing concurrency can improve throughput while many requests are waiting on I/O. However, if the worker pool/CPU/DB is already saturated, increasing concurrency mainly increases queue wait, memory, and p99 instead of productivity.

## 7. Why Not Average p95/p99 Across Multiple Servers?

Percentiles are **not linear**. For example:
- Server A receives 100 requests, all taking 10 ms → p95(A)=10 ms.
- Server B receives 1 request taking 1,000 ms → p95(B)=1,000 ms.
- Average of the two servers' p95 = (10+1,000)/2 = 505 ms.
- But across the 101 combined samples, p95 rank = ceil(0.95×101)=96; the 96th sample is 10 ms → **global p95 = 10 ms**.

Not only simple averaging, **weighted average p95** also does not yield the global percentile.

The right approaches:
1. Merge **raw observations** when data volume is small and storage permits.
2. For high traffic, merge **histogram bucket counts** that share the same bucket boundaries, then compute quantiles from the combined histogram.
3. Or use mergeable sketches with clear error bounds (HDR Histogram, t-digest, etc.) matching your stack.
4. Do not merge metrics with different boundaries: server processing latency is not client full-response latency.

Also report the **sample count per replica**, status/error distribution, and window time; a pod receiving 100 req must not carry the same weight as a pod receiving 10 million req just because each pod has one p99 number.

## 8. Coordinated Omission: A Very Common Benchmark Pitfall

Closed-loop tests typically generate a request/batch, **wait for it to finish**, and only then generate the next request/batch. When the server stalls for 2 seconds, the client waits too; no new requests arrive during that time. If actual production traffic **keeps arriving steadily**, closed-loop results can make tail latency look better than reality: this is **coordinated omission**.

~~~text
Closed-loop:
send batch ───────── wait responses ───────── send next batch
server stalled → generator also stops creating new requests

Open-loop / scheduled arrivals:
0ms send ─ 10ms send ─ 20ms send ─ 30ms send ...
server stalled → queue, timeouts, rejects are clearly recorded
~~~

True open-loop does not mean firing requests without limit: you need a **rate cap, in-flight cap, queue cap, stop criteria, and testing authorization** to avoid a DoS. If the generator drops requests due to overload, you must count dropped events and define their latency according to the reporting contract.

Example B below intentionally uses **12 concurrent requests per batch and waits on `allOf`**, so it is a **closed-loop mini benchmark** with limitations. Do not use it to prove production p99 or open-load behavior.

### Timeouts Must Not Disappear From Statistics

If a request hits a 5s timeout:
- Record the **error/timeout count**.
- You may record the attempt's termination-time latency, but that is not a successful response time.
- Report a **success-only latency histogram**, **all-attempt duration**, and error rate separately, or a combined SLO such as "completed successfully within deadline."
- Do not discard all failed requests and publish a flattering percentile.

Because a timeout can be a **censored observation** of the true response time, do not assume the server finished right when the client timed out.

## 9. Process CPU Time, Cores, and Quota

A request taking 100 ms wall time might only actually use 8 ms of CPU because it spent 92 ms waiting on the network. Conversely, a multithreaded process can use multiple cores in one second: total process CPU time is **greater than** wall time.

Java 17 provides `com.sun.management.OperatingSystemMXBean.getProcessCpuTime()` (nanoseconds; if unsupported, report unavailable). Measure two snapshots:

~~~text
cpuCoresAvg =
    (processCpuTimeAfter - processCpuTimeBefore)
    / (wallTimeAfter - wallTimeBefore)

processCpuPctOfVisible =
    100 * cpuCoresAvg / Runtime.getRuntime().availableProcessors()
~~~

For example, 3 seconds of process CPU time in 1 second of wall time → an average of **3 core-equivalents**. If the JVM sees 8 cores, that is about **37.5% of 8 visible cores**, but you need to know the actual cgroup/quota before comparing containers.

**Common pitfalls:**
- "100% CPU" in tool A may mean **one logical core**; tool B may normalize 100% = **the entire process quota**.
- `availableProcessors()` depends on the JDK/container/affinity, not necessarily the total physical host CPUs.
- A CPU sampling window that is too short is noisy due to counter resolution, JIT, GC, and background processes.
- If client and server share the same JVM (as in the demo), **process CPU includes both the load generator and the server**, so server capacity cannot be isolated.
- Low CPU does not prove ample headroom: the bottleneck could be an I/O pool, lock contention, network throttling, or an upstream service.

### CPU Profiling When the Bottleneck Is Unclear

`ThreadMXBean` (if supported) can measure per-thread CPU time. JFR CPU samples and profilers help identify whether CPU is spent on serialization, TLS, JSON, GC, contention, selector callbacks, the DB driver, or application code. Do not add threads before knowing whether existing threads are **RUNNABLE using CPU** or **WAITING on I/O**.

## 10. Memory Footprint: Heap, Committed, RSS, and Native Memory

A JVM process uses multiple memory regions:

~~~text
RSS / resident process memory (OS)
├─ Java heap (objects and arrays)
│  ├─ used       : bytes in use at snapshot
│  ├─ committed  : committed by JVM
│  └─ max        : heap ceiling per JVM configuration
├─ Metaspace / class metadata
├─ JIT code cache
├─ Thread stacks / native threads
├─ Direct and mapped ByteBuffers
├─ Native runtime / TLS / JNI / libc allocations
└─ Other OS/JVM overhead
~~~

### Reading the Metrics Correctly

| Metric | What It Observes | What Not to Infer |
|---|---|---|
| `MemoryMXBean.getHeapMemoryUsage().getUsed()` | Heap used at snapshot | Not peak, not total RSS |
| `MemoryUsage.getCommitted()` | Committed heap memory | Not total system RAM |
| `MemoryUsage.getMax()` or `Runtime.maxMemory()` | Heap ceiling | Not necessarily equal to container RAM |
| `MemoryMXBean.getNonHeapMemoryUsage()` | Part of off-heap memory | Does not cover all native allocations |
| `BufferPoolMXBean.getMemoryUsed()` | JVM-tracked direct/mapped buffer pool memory | May return -1 when unsupported |
| RSS / cgroup memory | Resident or charged memory of process/container | Not identical to heap used |
| Allocation rate | Object bytes allocated per unit time | Heap used may stay flat when GC reclaims frequently |
| GC pauses | GC pause/processing intervals per collector | Not automatically equal to total latency |

**A single snapshot showing higher heap used does not prove a leak.** Caches, JIT/class loading, response byte arrays, retained futures, or GC not having run yet can all raise heap in a mini test. Finding a leak requires analyzing **live object retention** across multiple load/GC cycles, allocation profiles, and heap dumps when permitted.

Conversely, a service using `SocketChannel` and `ByteBuffer.allocateDirect` can have **low heap yet high RSS** due to direct buffers. Do not look only at `-Xmx` when sizing container memory limits; account for native allocations, threads, metaspace, and GC/JIT overhead.

### Direct ByteBuffers

Example snippet to observe buffer pools:

~~~java
for (BufferPoolMXBean pool : ManagementFactory.getPlatformMXBeans(
        BufferPoolMXBean.class)) {
    System.out.println(pool.getName() + ": "
        + pool.getMemoryUsed());
}
~~~

You must import `java.lang.management.BufferPoolMXBean` and `java.lang.management.ManagementFactory`. `getMemoryUsed()` may return -1; do not interpret it as a negative byte count. Observe direct/mapped pools and OS RSS **together** when suspecting native memory pressure.

### Memory Units

- 1 MiB = **1,048,576 bytes**.
- 1 decimal MB = **1,000,000 bytes**.
- Do not compare `heap_used_mib` against a memory dashboard labeled MB without converting.
- `Runtime.maxMemory()` returns bytes; a system does not always need to use the full max heap.

## 11. GC and p99: Look at Both CPU and Allocations

Garbage collection affects performance in multiple ways:
- High allocation rates cause the collector to run more frequently.
- Collectors have concurrent phases that can consume CPU alongside the application.
- Stop-the-world pauses can spike p99 for some requests.
- Too small a heap can create GC pressure; too large a heap increases footprint and carries other trade-offs depending on the collector.

JDK `GarbageCollectorMXBean.getCollectionCount()` and `getCollectionTime()` are counters that may return -1 when unsupported. **Collection time does not always equal total downtime** for concurrent GCs; to inspect pause distribution, use JFR/GC unified logs.

If the demo prints `gc_collections_delta: 0`, that **only means the counter did not increment during the measurement window**; it does not prove the program did not allocate, that the heap needs no GC, or that there is no native memory overhead.

Use timestamps in the same window to compare p99 spikes against GC pause events and lock/queue/network events; temporal coincidence alone is not conclusive proof of causation.

## 12. Designing Meaningful Networking Benchmarks

### Keep Workload and Environment Consistent

Record at minimum:
- JDK vendor/version, GC, `-Xms/-Xmx`, OS/kernel/CPU quota, RAM/cgroup.
- HTTP/1.1 vs. HTTP/2, HTTPS/TLS, keep-alive, proxy, DNS/region.
- Request mix, method/path, body size, response size, validation semantics.
- Number of clients/connections, concurrency, offered rate, queue/rate limits.
- Warmup, measurement duration, repeats, status/timeout criteria.
- Latency measurement boundary, percentile algorithm/histogram bucket policy.
- Differences between server version/config A and B.

If one run measures plain HTTP on localhost and another measures HTTPS through a proxy, you cannot simply attribute the RPS difference to a Java algorithm.

### Warmup and Steady State

Java involves class loading, JIT compilation, connection setup, and caches. To measure **steady-state**, run a warmup, then separate measurement windows. If you want to measure **cold start**, that is a different workload: measure the first request(s) **separately** rather than deleting the warmup and claiming there is no cold-start problem.

Production-like tests should run long enough to observe cache eviction, multiple GC cycles, tail latency, throttling, connection resets, and queue buildup. Run multiple repeats to see variance, rather than picking only the fastest run.

### The Load Generator Has Limits Too

If the client generator hits 100% CPU or creates connections too slowly, the server may show low CPU and low RPS even though **the server still has spare capacity**. Run client and server in **separate processes/machines** to avoid interference, and measure offered requests as well as generator drops/retries. A single JVM running both server and client like the demo is only for learning how to produce metrics.

### Safety Boundaries

Load tests should only run against systems **you are authorized to test**; cap concurrency, ramp-up, timeouts, network traffic, and duration. Have a stop plan if errors or resources exceed thresholds to avoid accidental DoS or runaway cloud costs.

## 13. Example B: Loopback HTTP + Throughput, p50/p95/p99, CPU, Heap, and GC

The following lab uses **JDK 17** with no external dependencies:
- `HttpServer` on `127.0.0.1:0`, route `GET /payload` returning **1,024 bytes**.
- Server executor with 4 workers, `HttpClient` preferring HTTP/1.1, reusing a single instance.
- 30 warmup requests **excluded from metrics**.
- 240 measured requests, split into **20 batches × 12** concurrent requests.
- Each future records latency via `System.nanoTime()`; classified as successful on HTTP `200` and exact 1,024-byte body.
- Total measured wall duration is used to compute completed RPS.
- Process CPU time computes average core-equivalents and normalized process CPU percentage.
- Heap used before/after/max and GC collection counts are recorded using MXBeans.

**Important limitations:** this is a **closed-loop 12-in-flight mini benchmark** with client and server running **in the same process**; process CPU includes both; heap before/after is not peak; p99 from 240 samples has high uncertainty. The measurements only illustrate instrumentation, not SLO certification.

### 13.1. Complete Source `LoopbackHttpBenchmarkDemo.java`

~~~java
import com.sun.management.OperatingSystemMXBean;
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class LoopbackHttpBenchmarkDemo {
    static final int REQUESTS = 240;
    static final int BATCH_SIZE = 12;
    static final int BODY_BYTES = 1_024;

    static long processCpuNanos() {
        var bean = ManagementFactory.getOperatingSystemMXBean();
        if (bean instanceof OperatingSystemMXBean mx) {
            return mx.getProcessCpuTime();
        }
        return -1;
    }

    static long heapUsedBytes() {
        return ManagementFactory.getMemoryMXBean()
            .getHeapMemoryUsage().getUsed();
    }

    static long gcCollections() {
        long count = 0;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long value = bean.getCollectionCount();
            if (value < 0) return -1;
            count += value;
        }
        return count;
    }

    static double percentileMs(long[] latencyNanos, double percentile) {
        long[] sorted = latencyNanos.clone();
        Arrays.sort(sorted);
        int position = (int) Math.ceil(
            percentile / 100.0 * sorted.length) - 1;
        return sorted[position] / 1_000_000.0;
    }

    public static void main(String[] args) throws Exception {
        byte[] payload = new byte[BODY_BYTES];
        Arrays.fill(payload, (byte) 'A');
        ExecutorService serverThreads = Executors.newFixedThreadPool(4);
        HttpServer server = HttpServer.create(
            new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        server.setExecutor(serverThreads);
        server.createContext("/payload", exchange -> {
            try {
                if (!"GET".equals(exchange.getRequestMethod())) {
                    exchange.sendResponseHeaders(405, -1);
                    return;
                }
                exchange.getResponseHeaders().set(
                    "Content-Type", "application/octet-stream");
                exchange.sendResponseHeaders(200, payload.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(payload);
                }
            } finally {
                exchange.close();
            }
        });
        server.start();

        try {
            URI endpoint = URI.create("http://127.0.0.1:"
                + server.getAddress().getPort() + "/payload");
            HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(2))
                .build();
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(Duration.ofSeconds(5)).GET().build();

            // Warm up code paths and reusable HTTP connections; exclude samples.
            for (int i = 0; i < 30; i++) {
                HttpResponse<byte[]> response = client.send(
                    request, HttpResponse.BodyHandlers.ofByteArray());
                if (response.statusCode() != 200
                        || response.body().length != BODY_BYTES) {
                    throw new IllegalStateException("Warmup failed");
                }
            }

            long[] latencies = new long[REQUESTS];
            AtomicInteger successes = new AtomicInteger();
            AtomicInteger failures = new AtomicInteger();
            long heapBefore = heapUsedBytes();
            long gcBefore = gcCollections();
            long cpuBefore = processCpuNanos();
            long wallBefore = System.nanoTime();

            for (int offset = 0; offset < REQUESTS;
                    offset += BATCH_SIZE) {
                List<CompletableFuture<Void>> batch = new ArrayList<>();
                for (int i = offset; i < Math.min(
                        offset + BATCH_SIZE, REQUESTS); i++) {
                    final int index = i;
                    long started = System.nanoTime();
                    CompletableFuture<Void> done = client.sendAsync(
                        request, HttpResponse.BodyHandlers.ofByteArray())
                        .handle((response, error) -> {
                            latencies[index] =
                                System.nanoTime() - started;
                            if (error == null
                                    && response.statusCode() == 200
                                    && response.body().length == BODY_BYTES) {
                                successes.incrementAndGet();
                            } else {
                                failures.incrementAndGet();
                            }
                            return (Void) null;
                        });
                    batch.add(done);
                }
                CompletableFuture.allOf(
                    batch.toArray(new CompletableFuture<?>[0])).join();
            }

            long wallAfter = System.nanoTime();
            long cpuAfter = processCpuNanos();
            long gcAfter = gcCollections();
            long heapAfter = heapUsedBytes();
            int completed = successes.get() + failures.get();
            double seconds = (wallAfter - wallBefore) / 1e9;
            double throughput = completed / seconds;

            System.out.println("requests_completed: " + completed);
            System.out.println("successes: " + successes.get());
            System.out.println("failures: " + failures.get());
            System.out.printf(Locale.ROOT,
                "throughput_req_per_s: %.2f%n", throughput);
            System.out.printf(Locale.ROOT,
                "latency_ms p50=%.3f p95=%.3f p99=%.3f%n",
                percentileMs(latencies, 50),
                percentileMs(latencies, 95),
                percentileMs(latencies, 99));
            if (cpuBefore >= 0 && cpuAfter >= cpuBefore) {
                double cpuCores =
                    (cpuAfter - cpuBefore) / (double) (wallAfter - wallBefore);
                int visibleCpus = Runtime.getRuntime().availableProcessors();
                System.out.printf(Locale.ROOT,
                    "process_cpu_cores_avg: %.3f%n", cpuCores);
                System.out.printf(Locale.ROOT,
                    "process_cpu_pct_visible: %.2f%%%n",
                    100.0 * cpuCores / visibleCpus);
            } else {
                System.out.println("process_cpu: unavailable");
            }
            System.out.printf(Locale.ROOT,
                "heap_used_mib before=%.2f after=%.2f%n",
                heapBefore / 1_048_576.0, heapAfter / 1_048_576.0);
            System.out.printf(Locale.ROOT,
                "heap_max_mib: %.2f%n",
                Runtime.getRuntime().maxMemory() / 1_048_576.0);
            if (gcBefore >= 0 && gcAfter >= gcBefore) {
                System.out.println("gc_collections_delta: "
                    + (gcAfter - gcBefore));
            } else {
                System.out.println("gc_collections_delta: unavailable");
            }
        } finally {
            server.stop(0);
            serverThreads.shutdownNow();
        }
    }
}
~~~

### 13.2. Compile and Run

Requires a full JDK 17+ with `jdk.httpserver`, `jdk.management`, `java.management`, `java.net.http`. For classpath applications, modules are usually resolved automatically. For projects with `module-info.java`, declare the appropriate `requires` directives.

~~~bash
javac --release 17 -encoding UTF-8 LoopbackHttpBenchmarkDemo.java
java LoopbackHttpBenchmarkDemo
~~~

**Actual stdout from a test run on one JDK environment (performance values vary across runs):**

~~~text
requests_completed: 240
successes: 240
failures: 0
throughput_req_per_s: 5340.35
latency_ms p50=1.177 p95=2.536 p99=3.398
process_cpu_cores_avg: 6.258
process_cpu_pct_visible: 22.35%
heap_used_mib before=33.11 after=65.11
heap_max_mib: 30208.00
gc_collections_delta: 0
~~~

**Do not expect 5340.35 RPS throughput or 65.11 MiB heap on your machine.** A short mini test with both client and server in the same JVM can have very noisy sampled process CPU, many background threads, and JIT/GC activity; `heap_max_mib` depends on `-Xmx`/container; p99 varies with scheduler and hardware.

If the provider does not support process CPU time, the program prints `process_cpu: unavailable` instead of reporting a fake 0% CPU number. If requests fail due to runtime/network issues, `successes` may be less than 240. That is test behavior that must be reported, not hidden data.

### 13.3. Understanding the Measurements Precisely

- `REQUESTS=240` and `BATCH_SIZE=12` → 20 batches; waiting for `allOf` before the next batch makes it a **closed loop**.
- `System.nanoTime()` measures elapsed time from right before `sendAsync` to `handle`; this covers the client/server/network portions of the HTTP exchange under `BodyHandlers.ofByteArray()`.
- `AtomicInteger` avoids races when callbacks complete on different threads.
- `latencies` holds one element **per attempt** and includes the time until error recording if a request fails exceptionally. Real dashboards should separate successful latency from timeout/error metrics.
- `completed/s` measures the **wall window** including launching batches and waiting for all callbacks, rather than summing individual latencies to compute total duration.
- CPU core-equivalents are for the **JVM process including both client and server**; you cannot claim that as server-only CPU.
- Heap used before/after snapshots are **two points in time**, not peak or proof of a leak.
- A GC collection delta of 0 only shows the counter did not increment during the short window.
- `Runtime.maxMemory()` is the heap maximum, not OS RSS.
- `server.stop(0)` and `serverThreads.shutdownNow()` release the server/executor after the test; the code does not create a separate HTTP client per request.

### What More Does a Real-Environment Test Need?

Run server and client in **two separate processes/machines**; realistic workload, realistic response body size distribution, properly configured HTTP/TLS/connection reuse, fixed offered rate if needed, large sample counts, long enough duration, repeats, and OS/container metrics. If you want to benchmark **a small piece of Java processing** rather than end-to-end HTTP, consider **JMH** with warmup/iterations/forks instead of writing a microbenchmark with a manual `for` loop.

## 14. Finding Bottlenecks From the Four Metric Groups

These are **investigative hypotheses**, not definitive diagnoses:

| Simultaneous Observation | Where to Check |
|---|---|
| RPS rising, p99 stable, moderate CPU, low errors | May still have headroom; ramp up carefully |
| RPS plateauing, high process CPU, p99 rising | CPU saturation, JIT/GC, serialization, lock contention |
| Low CPU but high p99, long queue/pool waits | DB/upstream I/O, connection pool, semaphore, network |
| p50 stable, p99 only spikes occasionally | GC pauses, kernel scheduling, retransmissions, queue bursts |
| p50/p95/p99 all rising together | Baseline bottleneck, reduced server capacity, slow upstream |
| Heap used rises with load, drops after GC | Allocation pressure; check allocation rate |
| Heap live set grows across multiple GC cycles | Possible retained references/leak |
| Low heap but rising RSS/native | Direct buffers, metaspace, stacks, native allocations |
| High generator CPU, low server CPU | Generator cannot produce enough offered load |
| High RPS but rising 5xx/timeouts | Failed throughput, not increased useful capacity |
| Concurrency increases, RPS flat, p99 rises | Past saturation point, queue buildup |
| Low server processing p99, high client e2e p99 | Queue before handler, network/proxy/TLS/pool wait |

**Do not optimize by "adding threads" before identifying the bottleneck.** An NIO server can serve many connections with few selectors, but if CPU-heavy callbacks block the event loop, p99 will still suffer. Similarly, adding more worker threads when the DB connection pool only has a few slots usually just moves the queue elsewhere.

## 15. Observing with JFR, jcmd, JMX, and GC Logs

### JFR

Java Flight Recorder captures CPU samples, allocation/GC, thread scheduling, and many JVM events suited for investigating p99 spikes/CPU pressure. For a JVM you own, check its PID:

~~~bash
jcmd
~~~

Example of starting a time-bounded profile:

~~~bash
jcmd 12345 JFR.start name=netperf settings=profile duration=60s filename=netperf.jfr
~~~

**12345 is a placeholder PID**; pick a real PID you have permission to inspect. `settings=profile` has overhead that can affect benchmarks. JFR files contain metadata/stack traces that may be sensitive; protect them per policy.

### Heap and Thread Diagnostics

~~~bash
jcmd 12345 GC.heap_info
jcmd 12345 Thread.print
~~~

Thread dumps help reveal WAITING/BLOCKED/RUNNABLE states, though not every RUNNABLE thread is **actively using CPU**. Heap info is a snapshot; combine repeated windows/profiling before concluding a leak.

### Native Memory Tracking

On HotSpot, NMT must be enabled at startup:

~~~bash
java -XX:NativeMemoryTracking=summary -jar service.jar
jcmd 12345 VM.native_memory summary
~~~

`service.jar` is an **illustrative application name**, not a dependency of the demo; replace the PID. NMT has overhead and does not cover all native allocations made by external libraries. It is **not an exact total RSS**, so cross-check with OS/cgroup metrics.

### GC Logs

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar service.jar
~~~

This is an illustrative HotSpot configuration; configure log retention/rotation as needed. Compare GC pause timestamps with latency tail spikes in the same window, without claiming causation solely because an event coincided.

### MXBeans

- `MemoryMXBean`: heap/non-heap.
- `GarbageCollectorMXBean`: collections and collection time.
- `ThreadMXBean`: thread count, thread CPU times when supported.
- JDK's extended `OperatingSystemMXBean`: process CPU time.
- `BufferPoolMXBean`: direct/mapped buffers.

When using a metrics backend such as Micrometer/Prometheus/OpenTelemetry, prefer exporting aggregatable histograms. Do not use **raw URLs containing tokens/user IDs**, session cookies, or request IDs as high-cardinality metric labels; use route templates and redaction.

## 16. Setting SLOs Instead of Just Publishing High RPS

An example SLO design:

> "At least 99% of valid requests to GET /items within the evaluation window must complete successfully within 200 ms per client-side e2e timing; timeouts and HTTP 5xx count toward the failure budget."

This is an **example SLO**, not a real SLA of any system. To operationalize it:
1. Lock down the boundary and which events count as valid requests.
2. Define how 2xx/4xx/5xx statuses, timeouts, cancels, dropped load, and redirects are classified.
3. Choose the time window and how histograms are merged across instances.
4. Publish throughput + error rate + latency distribution + CPU/memory.
5. Ensure headroom for spikes, failover, and background work.

**Note:** "99% of requests succeed" and "99% of requests complete **successfully under 200 ms**" are two different conditions. A request succeeding after 10 seconds satisfies the first condition but fails the second.

## 17. Common Mistakes to Avoid

| Mistake | Problem | Fix |
|---|---|---|
| Looking only at average latency | p99 tail can be huge | Report p50/p95/p99/max |
| Reporting p99 from 20 requests as a production metric | Insufficient sample count | Sufficiently large window/sample count |
| Averaging per-pod p99s | Not the global quantile | Merge histograms/raw samples |
| Measuring short operations with `System.currentTimeMillis` | Wall clock drift/resolution | Use `System.nanoTime` |
| Not checking HTTP status/body | Fast HTTP errors inflate RPS | Separate completed and success RPS |
| Omitting timeouts/dropped load | Artificially rosy SLO | Report error/timeout/drop counts |
| Not separating successful-only and all-attempt latencies | Mixes failure latency with success | Report clear metric boundaries |
| Timing right when `ofInputStream` returns | Misses full-body latency | Measure until body is fully read |
| Skipping warmup when comparing steady-state | JIT/cache/cold connections add noise | Run warmup; test cold-start separately |
| Picking only the fastest run | Selection bias | Repeat runs, report variability |
| Client/server in same JVM, attributing CPU to server | CPU includes both generator and server | Separate processes/hosts |
| Running 50 ms and concluding CPU quota | Noisy sample | Longer window and OS cross-check |
| Heap used increased = leak | Could just be allocations/cache/GC timing | Analyze live set/retention |
| Heap max = RSS | Ignores direct/native/stacks | Check OS RSS/NMT/BufferPoolMXBean |
| Unchanged GC count = no allocations | Counter does not reflect everything | Check JFR allocations/heap |
| Closed-loop without noting coordinated omission | Tail latency may look overly optimistic | Use open-loop if it fits the workload |
| Increasing concurrency unboundedly | Queue/memory overload, potential DoS | Rate cap, ramp-up, stop limits |
| Changing payload/TLS/HTTP version between A/B | Comparing different workloads | Lock config and document changes |
| Reporting CPU % without core count/quota | Hard to compare environments | Report avg cores + visible/quota |
| Enabling a heavy profiler in one run vs. none in another | Instrumentation bias | Account for profile overhead |
| Looking only at CPU without queue/pool waits | Misdiagnosing the bottleneck | Track queues, in-flight, upstream |
| Putting URLs/tokens into metric labels | Data leakage and high cardinality | Use route templates, redact |
| Running unauthorized load tests on production | Downtime risk and cost | Use approved lab/staging |

## 18. Practice Exercises

1. A service completes 2,400 requests in 4 seconds, of which 2,280 succeed. Calculate completed RPS, successful RPS, and error rate.
2. Why can a service returning `503` very quickly still report high completed RPS?
3. Distinguish offered load, completed throughput, success throughput, and bytes/s.
4. How does `System.nanoTime()` differ from `System.currentTimeMillis()`?
5. Why is `sendAsync` completing with `ofInputStream()` not necessarily full-body latency?
6. Given an array of 100 samples 1..98, 600, 2,000 µs, what are p50/p95/p99/max?
7. With 20 samples, which element is the nearest-rank p99?
8. Why must you not take the average of two p95 values from two servers?
9. Explain coordinated omission and why a closed-loop generator can miss tail latency when the server stalls.
10. A timed-out request is excluded from the success histogram. What additional metrics should be reported?
11. Does Little's Law use mean time or p99? What are its required conditions?
12. A process uses 3 seconds of CPU in 1 second of wall time; how many CPU core-equivalents is that?
13. Why can a process's CPU time be greater than elapsed wall time?
14. Why can't the process CPU of a shared client+server JVM represent the server alone?
15. Is `Runtime.maxMemory()` the heap max or total RSS?
16. Name at least three off-heap memory regions and how to observe direct buffers.
17. Is an increase in heap used between two snapshots proof of a leak?
18. Does a GC collection delta of 0 prove there were no allocations?
19. Why is `-Xmx` not enough to predict container RAM usage?
20. In Demo B, why must `AtomicInteger` be used?
21. Why does throughput use the total wall time of the batch loop instead of summing individual request latencies?
22. Can p99 of 240 requests represent production traffic? Why or why not?
23. When observing flat RPS, low CPU, and growing queues, what should you investigate?
24. Name three factors that can raise p99 while p50 stays stable.
25. To compare versions A and B, which JDK/protocol/payload/load parameters would you lock?
26. When should you measure cold-start latency separately instead of skipping warmup?
27. Can using JFR/jcmd skew performance?
28. A service achieves 99% success, but 10% of successful responses take longer than 200ms; does it meet the SLO "99% successful within 200ms"?

**Suggested answers:** (1) 600, 570 req/s, 5%; (2) fast errors are not useful work; (3) intended send rate / completed / successful / bandwidth; (4) monotonic elapsed vs. wall time; (5) stream not yet fully read; (6) 50/95/600/2000 µs; (7) 20th; (8) quantiles are not linear; (9) client stops sending when server stalls; (10) timeout/error rate and all-attempt duration; (11) mean and steady state; (12) 3 cores; (13) multi-core execution; (14) CPU mixes both sides; (15) heap max; (16) metaspace/stacks/direct buffers and BufferPoolMXBean; (17) not yet; (18) no; (19) native/off-heap memory; (20) concurrent callbacks; (21) batch requests overlap; (22) too few samples, closed-loop generator, localhost; (23) upstream I/O/pools/locks; (24) GC pauses/queue bursts/retransmissions; (25) same env/workload; (26) when cold start is an SLO; (27) yes, overhead; (28) no.

## 19. Pre-Publication Benchmark Checklist

1. Clearly define endpoint/response correctness and use the same workload.
2. Record JDK, GC, heap, CPU quota, host/container, network, and deployment version.
3. Include request counts: attempts/completions/success/errors/timeouts/rejected.
4. Separate completed throughput and successful throughput.
5. Set the latency boundary and use `System.nanoTime` for durations.
6. Report percentile method, sample count, and p50/p95/p99/max.
7. Do not average p99 across replicas; merge histograms/distributions.
8. Avoid coordinated omission or clearly state the closed-loop model.
9. Include warmup for steady state; measure cold-start separately if needed.
10. Use sufficient duration, repeats, and consistent offered rate/concurrency.
11. Measure process CPU time in the same window as latency/throughput; report cores/quota.
12. Report heap used/committed/max along with native/RSS/GC as needed.
13. Separate the server from the load generator when drawing capacity conclusions.
14. Use JFR/JMX/GC logs to investigate, controlling for diagnostic overhead.
15. Define pass/fail SLO criteria, not just a single flattering RPS number.
16. Test only authorized systems; protect logs/telemetry from secrets.

## 20. Summary

- **Throughput** is completed work/second; **goodput** is successful/useful work. Always report status/error/timeout context.
- **Latency is a distribution**, not just a mean; p50/p95/p99 require clear sample counts and percentile methods. Do not average percentiles across machines.
- **Coordinated omission** can make closed-loop benchmarks evaluate tail latency too optimistically compared to workloads with independent arrival rates.
- **CPU** should be measured via process CPU time and wall time in the same window, converted to core-equivalents; identify quotas and separate generator CPU from server CPU.
- **Memory** includes heap used/committed/max as well as native/direct/stack regions; RSS does not equal heap, and rising memory in a single snapshot does not prove a leak.
- **GC/JFR/queues/network** help explain p99 spikes; a single metric is never enough to pinpoint the cause.
- **A good benchmark** has a workload contract, warmup, sufficient duration, repeats, proper response validation, and an SLO.
- **Two real Java 17 demos were run:** percentile/throughput with fixed data; HTTP loopback with 240 requests, p50/p95/p99 latency, process CPU, heap, and GC counts.

### References

- [Oracle Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [Oracle Java SE 17 — ManagementFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html)
- [Oracle Java SE 17 — MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [Oracle Java SE 17 — MemoryUsage](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html)
- [Oracle Java SE 17 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html)
- [Oracle Java SE 17 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html)
- [Oracle Java SE 17 — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [Oracle Java SE 17 — Extended OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html)
- [Oracle Java SE 17 — jcmd and JFR](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Oracle Java SE 17 — JFR command-line](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html)
- [OpenJDK JMH](https://github.com/openjdk/jmh)
