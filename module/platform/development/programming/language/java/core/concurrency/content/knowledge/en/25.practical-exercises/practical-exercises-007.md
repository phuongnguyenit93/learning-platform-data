# Comparing Platform Threads and Virtual Threads for I/O Tasks

## 1. Practical Problem and Expected Outcomes

Suppose a Java program has to send hundreds of HTTP requests to another service. Most of the time for each request is spent waiting for the network response, while the CPU only processes a small amount of data. Should you create one platform thread per request, use a fixed thread pool, or use one virtual thread per request?

This practical exercise compares **platform threads** and **virtual threads** using the same I/O workload. You will run a simulated HTTP server locally on your machine, send synchronous HTTP requests using `HttpClient.send(...)`, verify correct results, measure the elapsed time of the entire batch, and observe the impact of concurrency limits.

**Environment requirement:** **JDK 21 or later**. Virtual threads were standardized in Java 21 (JEP 444). The APIs `Executors.newVirtualThreadPerTaskExecutor()`, `Thread.ofVirtual()`, and `Thread.isVirtual()` may not exist or may not be stable in JDK 17. Do not use `--enable-preview` for virtual threads on Java 21+.

**Objectives upon completion:**

1. Explain that a platform thread holds an OS thread for its lifetime, whereas a virtual thread can yield its carrier when encountering blocking I/O operations supported by the JVM.
2. Run **the same request logic** under three mechanisms: a bounded platform pool, one virtual thread per task, and virtual threads with a semaphore limiting the downstream service.
3. Distinguish between **batch throughput**, **single-request latency**, concurrency level, and resource usage.
4. Measure elapsed time while always verifying status codes, response bodies, and the number of succeeded/failed requests.
5. State why virtual threads do not make the CPU faster and do not eliminate connection pool limits, rate limits, file descriptor limits, or target system capacity.
6. Diagnose the effects of blocking I/O, pinning by JDK version, timeouts, interruption, backpressure, and shutdown.

This exercise uses only Java SE and the JDK's `jdk.httpserver` module, with no framework dependencies.

## 2. Core Concepts

### Platform Thread

`Thread.ofPlatform()` creates a Java thread bound to an OS thread. When Java code performs synchronous blocking I/O, that OS thread is typically held for the duration of the wait. Creating too many platform threads can increase stack, scheduling, memory, and OS thread count overhead.

`Executors.newFixedThreadPool(12)` creates a pool with at most 12 worker platform threads running concurrently; if 120 tasks are all waiting on I/O, the 13th task onward must wait in the executor queue until a worker becomes free.

### Virtual Thread

`Thread.ofVirtual()` creates a virtual thread managed by the JVM. When a virtual thread encounters a blocking I/O operation that supports unmounting, the JVM can temporarily unmount the virtual thread from its platform **carrier thread**, allowing the carrier to run other work while the I/O is waiting. Once the I/O result is ready, the virtual thread resumes on an appropriate carrier.

`Executors.newVirtualThreadPerTaskExecutor()` starts **a new virtual thread for each submitted task**; it is not a fixed pool of virtual threads. A large number of requests waiting on the network can coexist without needing a dedicated OS thread per request.

**No magic:** The CPU still executes code on platform carrier threads. If 1,000 tasks all need 100% CPU, virtual threads do not provide 1,000 CPU cores. If the target service only allows 20 concurrent connections, creating 10,000 virtual threads will not increase that service's capacity either.

| Perspective | Platform thread / fixed pool | Virtual thread / thread-per-task |
| --- | --- | --- |
| OS thread binding | A platform thread holds an OS thread for its lifetime. | A virtual thread is mounted onto a carrier by the JVM when running; it can unmount during supported waits. |
| Per-thread cost | Typically higher, hard to scale to very large counts. | Typically lower, suitable for many concurrently waiting tasks. |
| On blocking I/O | A worker in the pool is occupied until the call returns. | With blocking APIs that support unmounting, the carrier is used for other tasks. |
| On CPU-bound work | Limited by CPU cores, plus scheduler overhead. | Still limited by CPU cores; not inherently faster. |
| Coding style | Easy to write synchronously, but requires managing the number of platform threads. | Keeps synchronous style, one thread per task. |
| Downstream limits | Still requires controlling connections/rate/memory. | Still requires controlling connections/rate/memory; cheap threads do not mean free tasks. |
| Tooling | Thread dumps, JFR, profilers, metrics. | Includes thread dumps/JFR for virtual threads and related events. |

Virtual threads primarily help **scale the number of concurrently waiting tasks** and increase throughput under suitable workloads. **An individual HTTP request does not automatically get lower latency** just by running on a virtual thread.

## 3. Designing a Fair Comparison Experiment

This exercise uses an internal HTTP server:

- Listens only on `127.0.0.1` on an OS-assigned ephemeral port (port `0`), with no Internet dependency.
- Each request to `/slow` is handled by a **separate** server executor using virtual threads, simulating waiting work with `Thread.sleep(100)` and then returning `HTTP 200` with body `ok`.
- The client sends `120` synchronous HTTP GET requests using **one shared HttpClient**, targeting the same endpoint, timeout, and body check.
- Runs three rounds **sequentially**, waiting for all Futures of the previous round to finish before starting the next.
- Computes the total result and elapsed time for the entire batch. Times may vary across runs, machines, OSes, and JDKs.

Three configurations:

1. **`platform-12`:** `Executors.newFixedThreadPool(12)`, 120 tasks submitted to the pool; at most 12 client tasks run concurrently.
2. **`virtual-unbounded`:** `Executors.newVirtualThreadPerTaskExecutor()`; on the client side, no limiting semaphore is imposed. With 120 tasks, many requests can wait simultaneously, though the actual limit still depends on HttpClient, sockets, the server, and the OS.
3. **`virtual-limited-24`:** still one virtual thread per task, but uses `Semaphore(24)` so that at most 24 client requests use the target's resources concurrently. Other tasks wait for a permit synchronously.

**Why does the server use its own executor?** If the server only had a single platform worker, all requests would be serialized on the server side, masking the effect of client scheduling. Conversely, if the server also uses many virtual threads, the experiment tests a system where **both client and server** support a high number of connections. Therefore, the results must be interpreted as end-to-end measurements of the local system, not an absolute thread benchmark.

**Note:** `Thread.sleep` on the server only simulates schedulable wait time; the client comparison uses **real HTTP I/O over loopback** via `HttpClient.send`. Comparing two sleeping threads and calling it a real network benchmark would lead to inaccurate conclusions about sockets, TCP, TLS, and the target host.

## 4. Runnable Example for JDK 21+

Save the following code as **`ThreadIoComparison.java`**. It compiles with JDK 21+ and runs standalone without external dependencies beyond the JDK.

```java
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class ThreadIoComparison {
    private static final int REQUESTS = 120;
    private static final int PLATFORM_WORKERS = 12;
    private static final int VIRTUAL_LIMIT = 24;
    private static final int SERVER_DELAY_MS = 100;

    record Measurement(String label, int success, long elapsedMs) {}

    private static Measurement runBatch(
            String label,
            ExecutorService executor,
            HttpClient client,
            URI endpoint,
            int maxInFlight) throws Exception {

        Semaphore permits = new Semaphore(maxInFlight);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Boolean>> futures = new ArrayList<>();

        for (int i = 0; i < REQUESTS; i++) {
            futures.add(executor.submit(() -> {
                start.await();

                // Limit the number of I/O calls actually in flight.
                permits.acquire();
                try {
                    HttpRequest request = HttpRequest.newBuilder(endpoint)
                            .timeout(Duration.ofSeconds(15))
                            .GET()
                            .build();

                    HttpResponse<String> response = client.send(
                            request,
                            HttpResponse.BodyHandlers.ofString());

                    return response.statusCode() == 200
                            && "ok".equals(response.body());
                } finally {
                    permits.release();
                }
            }));
        }

        long begin = System.nanoTime();
        start.countDown();

        int success = 0;
        for (Future<Boolean> future : futures) {
            if (future.get(30, TimeUnit.SECONDS)) {
                success++;
            }
        }

        long elapsedMs =
                TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - begin);

        return new Measurement(label, success, elapsedMs);
    }

    private static void show(Measurement m) {
        System.out.println(
                m.label() + ": success=" + m.success() + "/" + REQUESTS);
    }

    public static void main(String[] args) throws Exception {
        // Port 0: the operating system selects an available loopback port.
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        try (ExecutorService serverExecutor =
                     Executors.newVirtualThreadPerTaskExecutor();
             HttpClient client = HttpClient.newBuilder()
                     .connectTimeout(Duration.ofSeconds(5))
                     .build()) {

            server.setExecutor(serverExecutor);
            server.createContext("/slow", exchange -> {
                try {
                    Thread.sleep(SERVER_DELAY_MS);

                    byte[] body = "ok".getBytes(StandardCharsets.UTF_8);
                    exchange.sendResponseHeaders(200, body.length);
                    exchange.getResponseBody().write(body);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    exchange.close();
                }
            });

            server.start();
            URI endpoint = URI.create(
                    "http://127.0.0.1:"
                            + server.getAddress().getPort() + "/slow");

            try {
                Measurement platform;
                try (ExecutorService workers =
                             Executors.newFixedThreadPool(PLATFORM_WORKERS)) {
                    platform = runBatch(
                            "platform-12", workers, client, endpoint,
                            PLATFORM_WORKERS);
                }

                Measurement virtual;
                try (ExecutorService workers =
                             Executors.newVirtualThreadPerTaskExecutor()) {
                    virtual = runBatch(
                            "virtual-unbounded", workers, client, endpoint,
                            REQUESTS);
                }

                Measurement limited;
                try (ExecutorService workers =
                             Executors.newVirtualThreadPerTaskExecutor()) {
                    limited = runBatch(
                            "virtual-limited-24", workers, client, endpoint,
                            VIRTUAL_LIMIT);
                }

                show(platform);
                show(virtual);
                show(limited);

                System.out.println("elapsedMs:");
                System.out.println("  platform-12="
                        + platform.elapsedMs());
                System.out.println("  virtual-unbounded="
                        + virtual.elapsedMs());
                System.out.println("  virtual-limited-24="
                        + limited.elapsedMs());

                if (platform.success() != REQUESTS
                        || virtual.success() != REQUESTS
                        || limited.success() != REQUESTS) {
                    throw new AssertionError(
                            "An HTTP request failed or returned invalid data");
                }
            } finally {
                server.stop(0);
            }
        }
    }
}
```

This example is for **JDK 21+**, not Java 17. Explicitly compile and run with the `jdk.httpserver` module:

```bash
javac --add-modules jdk.httpserver ThreadIoComparison.java
java --add-modules jdk.httpserver ThreadIoComparison
```

If the runtime environment blocks loopback sockets or limits file descriptors, the exercise may fail to start the server or experience failed requests; in that case, address the environment restriction rather than concluding that virtual threads are slow or broken.

### Output and How to Read It

**The three correctness lines** when all HTTP requests succeed will be:

```text
platform-12: success=120/120
virtual-unbounded: success=120/120
virtual-limited-24: success=120/120
```

Then the program prints:

```text
elapsedMs:
  platform-12=<measured elapsed time>
  virtual-unbounded=<measured elapsed time>
  virtual-limited-24=<measured elapsed time>
```

The strings in angle brackets are **illustrative placeholders** for where the measurements appear, not fixed stdout text. The actual values printed by the program are integer milliseconds and **cannot be predicted exactly**. Machine, JDK, HTTP client, open connection counts, CPU, scheduling, GC, and code warmup all affect the results.

With a workload waiting 100 ms/request and sufficient server capacity, `platform-12` typically has to process more sequential waves of requests than `virtual-unbounded`. However, you should not claim a specific speedup ratio, or that virtual threads are always fastest. This experiment is also subject to HTTP server and OS bottlenecks; it is simply a controlled measurement to **learn the mechanics and form hypotheses**.

### Line-by-Line Analysis

1. **One internal server:** `HttpServer.create(..., 0)` acquires an OS-assigned port. Using `127.0.0.1` avoids external network dependencies; `server.stop(0)` shuts down the server in `finally`.
2. **Same request across all three modes:** every task creates a GET `/slow`, waits on `HttpClient.send`, and checks `statusCode()==200` and exact body `ok`.
3. **Same amount of work:** each round submits exactly `120` tasks; at the end there must be exactly `120` successes. Never use the number of submitted requests in place of actual successes.
4. **Platform pool with a queue:** only 12 workers execute tasks simultaneously; the rest sit in the executor queue. Each worker is typically occupied until the synchronous HTTP send call completes.
5. **Virtual thread per task:** the executor creates a new virtual thread for each task; when waiting on JVM-supported I/O, it can yield its carrier. This removes the need to hold an OS thread per request.
6. **Semaphore as a target resource limit:** virtual threads wait for a permit before issuing the HTTP request. Do not create a fixed pool of virtual threads to simulate an I/O limit; concurrency limit and thread type are two separate decisions.
7. **`CountDownLatch` for a common starting point:** tasks already started by the executor wait on `start.await()`; tasks still in the platform queue have not reached the latch yet. After submitting all tasks, `main` opens the latch and starts timing. This compares **a realistic model including queue wait time**, not an absolute simultaneous launch of 120 requests across all three configurations.
8. **`Future.get(timeout)`:** `main` waits for completion and propagates exceptions from tasks back to `main`. If a task throws an exception or times out, the batch fails rather than reporting a misleadingly fast time.
9. **Lifecycle cleanup:** `ExecutorService` since Java 21 is `AutoCloseable`; exiting `try` calls `close()` and waits for tasks to finish. `HttpClient` should also be closed when the program no longer needs it. The example also stops the HTTP server in `finally`.
10. **`System.nanoTime()`:** used to measure elapsed time; do not use `currentTimeMillis()` for latency because wall-clock time can shift. The total measurement is converted to milliseconds.

### Important Limitations of the Example

`Semaphore(REQUESTS)` in `virtual-unbounded` does not restrict concurrency for 120 tasks, yet it is still a semaphore; "unbounded" here means **not setting a limit smaller than the experiment's task count**, not that the system allows infinite requests.

`HttpRequest.timeout(15s)` is the limit for a single HTTP request; `Future.get(30s)` limits the wait time for each future from the moment `get` is called. Because `main` iterates over futures sequentially, the whole batch does not have a strict 30-second overall deadline; a shared deadline mechanism is needed in a real service.

The example does not apply rigorous warmup/benchmarking techniques and does not measure per-request percentiles. You should run multiple iterations and distinguish per-request latency from batch elapsed time.

## 5. Interpreting Results by Throughput and Latency

With the same `N = 120` requests, the observed batch throughput calculation is:

\[
\text{Throughput (request/s)} =
\frac{N \times 1000}{\text{elapsedMs}}
\]

Compute this only from the **number of successfully completed requests** if failures occur; avoid using `120` for a batch where 10 requests errored.

**Latency** of a single request is the time from right before the client attempts to send the request until the full response is received, or from when the task is submitted if you want to include queue wait time. These are two different definitions; state which one you use in your report.

**Batch elapsed** also includes scheduling time, connection establishment, server execution, and client result collection. If concurrent requests genuinely wait on I/O, batch elapsed time can drop sharply even though **each request still waits around 100 ms on the server**.

| Observation | Possible interpretation | Further checks needed |
| --- | --- | --- |
| Virtual finishes the batch faster than the small platform pool | Many waiting tasks do not need to hold many platform workers. | Actual concurrent requests, network/server capacity, and error count. |
| Virtual-limited is slower than virtual-unbounded | The semaphore throttles resources; requests must wait for permits. | Does it reduce server overload/errors/tail latency? |
| Virtual-unbounded is slow or errors out | Downstream/client/socket resources may be overloaded. | Ports, connection limits, rate limits, timeouts, CPU, server saturation. |
| All three cases are similar | Load is low or another bottleneck dominates; does not prove the models are equivalent everywhere. | Scale up in a controlled way; run more iterations, add warmup. |
| 100% CPU in both | The work may be CPU-bound or the system is overloaded by HTTP/JVM overhead. | Profile CPU, GC, and actual wait time. |
| Many virtual threads but few in-flight requests | The real limit lies in a semaphore, connections, or the server. | Pending/active metrics, sockets, server queue. |

Do not report "virtual threads are X times faster" based on a single run. Measure median/p95 across multiple rounds, alternate the order of configurations to reduce warmup/JIT/cache bias, monitor CPU, and alert on any HTTP failure.

## 6. Extension Exercise: Measuring In-Flight and p95 Latency

The main exercise measures batch elapsed time. To verify where bottlenecks occur, add these variables:

- `AtomicInteger inFlight`: increment right before `client.send`, decrement in `finally`.
- `AtomicInteger peakInFlight`: on each increment, update the max using `peakInFlight.accumulateAndGet(now, Math::max)`.
- A start/completion timestamp for each request using `System.nanoTime()`; store latency after the request returns or throws.
- Count errors separately by HTTP status, timeout, connect error, and interruption. Never swallow exceptions and count the request as successful.

Example **illustrative snippet inside the task body** (assuming `inFlight` and `peakInFlight` fields are declared and measurement plumbing is set up):

```java
int current = inFlight.incrementAndGet();
peakInFlight.accumulateAndGet(current, Math::max);

long started = System.nanoTime();
try {
    HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());
    long latencyNs = System.nanoTime() - started;
    // Record latencyNs and the result into a thread-safe collector.
} finally {
    inFlight.decrementAndGet();
}
```

Place the counter **after acquiring the semaphore** to accurately measure in-flight HTTP calls, excluding tasks merely waiting for a permit. In real code, the response body must be consumed or closed properly; the snippet uses `BodyHandlers.ofString()`, which reads the entire body before the call completes.

To compute p95/p99 from multiple samples, store them in a thread-safe collection or an array written at a dedicated index per task and aggregate only after `Future.get` completes for all tasks; sort and define how percentiles are selected. Do not approximate p95 using `max` or an average.

**Advanced analysis:** if results show `success=120/120` yet `peakInFlight` is unusually low in `virtual-unbounded`, check whether the server, HttpClient, or environment limits connections. If `peakInFlight` is high but throughput does not increase, the server may be the bottleneck.

## 7. Do Virtual Threads Replace Backpressure?

**No.** Even if a virtual thread task is cheap, the program must still hold its request object, response buffer, stack, context, socket, or connection. Spawning millions of uncontrolled requests can overload both client and server.

Distinguish between:

- **Thread scheduling:** choosing the thread type and executor.
- **Concurrency limit:** the number of requests allowed to execute simultaneously (e.g., semaphore).
- **Arrival rate:** the rate at which new requests arrive; may require a rate limiter or bounded queue.
- **Connection pool:** the number of connections to a service/database.
- **Timeout and cancellation:** how to terminate unnecessary or slow tasks.
- **Backpressure:** how to signal the producer when the consumer/downstream lacks capacity.

For example, `Semaphore(24)` limits **the number of requests entering the guarded section**, but all tasks have still been submitted and may be waiting for a permit. It **does not bound the number of pending tasks** or created virtual threads. If the request source is unbounded, you need a bounded queue, admission control, rate limiting, or controlled rejection.

For `Semaphore`, fairness `new Semaphore(permits, true)` can prioritize earlier waiters when acquiring permits, but it can reduce throughput. There is no need to enable fairness to compare the fundamental behavior of platform vs. virtual threads in this exercise.

## 8. When Virtual Threads Help Less

### 8.1. CPU-Bound Work

If tasks mostly perform encryption, compression, heavy hashing, or matrix multiplication, virtual threads do not provide extra CPUs. Using a platform pool sized near the core count or an appropriate task model usually makes contention easier to control.

Try this exercise: replace the HTTP request with a long CPU calculation, measure CPU%, completion time, and speedup as thread count varies. Do not mix CPU measurements into the initial I/O comparison and attribute the results to virtual threads.

### 8.2. Uncooperative Blocking Libraries or Native Calls

Some native/foreign operations or library usages can hold a carrier thread for a long time, reducing virtual thread scalability. Measure with a profiler/JFR in the specific runtime rather than guessing from method names.

### 8.3. Pinning Depends on JDK Version

On **JDK 21–23**, blocking while a virtual thread is inside a `synchronized` block can **pin** the virtual thread to its carrier, preventing the carrier from yielding to other tasks during the wait. On **JDK 24+**, JEP 491 changed monitor synchronization so that virtual threads waiting inside `synchronized` blocks can yield their carrier, eliminating monitor-induced pinning under the old mechanism. Other pinning causes, such as native/foreign frames, still need to be monitored.

Example illustrating the issue for JDK 21–23:

```java
synchronized (sharedLock) {
    // Avoid holding a monitor during a slow I/O call;
    // on JDK 21–23, this can also pin the carrier thread.
    blockingHttpCall();
}
```

This is **not a standalone program**. Aside from pinning, holding a monitor while waiting on I/O also causes contention between threads and can create deadlocks, even on newer JDKs. Therefore, **do not** mechanically replace every `synchronized` with `ReentrantLock`; first identify the JDK version, correctness requirements, and which lock holds actually cause bottlenecks.

You can inspect JFR events and thread dumps appropriate for your JDK version. `jdk.VirtualThreadPinned` is a useful event when pinning conditions are recorded, though event thresholds/durations and stack contents depend on the JDK/configuration. On JDK 21–23, depending on the JVM, you can try `-Djdk.tracePinnedThreads=full` to locate call stacks causing pinning.

## 9. ThreadLocal, Interruption, and Resources

### ThreadLocal

Platform thread pools typically reuse the same workers across many tasks, so a `ThreadLocal` holding a per-thread cache/connection can be reused—and also risks leaking state to the next task if `remove()` is forgotten.

Virtual thread per task creates a new thread for each task; per-thread `ThreadLocal` can lead to high state/cache creation overhead if every task opens its own resource. Do not use `ThreadLocal` to implicitly own connections across hundreds of thousands of tasks without lifecycle control. For expensive resources, prefer explicit resource ownership and resource-level pools/limiters.

### Timeout and Interruption

`Future.cancel(true)` only requests interrupting the task. Code using `HttpClient.send` may respond with `InterruptedException`; in Java, interruption can also trigger request and connection cancellation protocols, though there is no guarantee that server-side side effects have stopped. If there is a real deadline, coordinate request timeouts, overall deadlines, and policies for handling late HTTP responses.

If catching `InterruptedException` without rethrowing:

```java
try {
    runBlockingOperation();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Stop the work or return a cancelled status to the caller.
}
```

This is only an illustrative skeleton inside a method where `runBlockingOperation()` is declared; it is not a standalone Java class. Never silently swallow an interrupt and keep making I/O calls indefinitely.

### Closing Executors and Services

`Executors.newVirtualThreadPerTaskExecutor()` creates a new executor with one virtual thread per task. When the processing phase finishes, close the owned executor; `close()` in Java 21 waits for tasks to complete. If a task can wait indefinitely, you need explicit timeouts/cancellation rather than expecting `close()` to enforce a deadline.

The example includes both `HttpServer` and `HttpClient`. The server uses a separate executor to avoid mixing with client resources; resources are closed where they are created. In real systems, avoid creating a new `HttpClient` per request because it increases connection overhead; reuse an appropriate client across requests.

## 10. How to Run and Evaluate the Exercise

Perform at least four measurement rounds for each configuration, recording the numbers, conditions, and **all errors**. A results table should follow this structure:

| Mode | JDK | N requests | Limit in-flight | Success | Median elapsed ms | CPU% | Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| platform-12 | Your JDK | 120 | 12 | Actual | Actual | Actual | Fixed OS thread pool |
| virtual-unbounded | Same JDK | 120 | 120 | Actual | Actual | Actual | Virtual task per thread |
| virtual-limited-24 | Same JDK | 120 | 24 | Actual | Actual | Actual | Downstream limit |

Do not put fabricated timing numbers in your report. The first run may incur JIT warmup, DNS/socket setup, caching, and lazy initialization. To draw performance conclusions, add warmup, alternate mode order across rounds, keep server capacity stable, run long enough, and include latency distributions.

**Completion criteria:**

1. Run on **JDK 21+** and record the exact `javac`/`java` commands.
2. All configurations return **120/120** valid requests under normal conditions; any failed cases must be analyzed, not ignored.
3. Explain why a platform pool of 12 must queue waiting tasks and why virtual-thread-per-task is not directly limited by 12 platform workers.
4. Explain why `virtual-limited-24` can produce a longer batch time than `virtual-unbounded` while protecting the dependent service.
5. State clearly which conclusions apply to I/O-bound work and which must not be extrapolated to CPU-bound work.
6. Distinguish batch elapsed time from per-request latency, and recognize that "cheap virtual threads" do not remove resource limits.

## 11. Advanced Exercises

**Exercise A — Varying load.** Change `REQUESTS` to `24`, `120`, and `600` in turn; keep server sleep duration fixed. Observe at which load level differences emerge between the models. For high loads, increase the HTTP request timeout if justified, but avoid comparing a failing mode against a succeeding one without noting it clearly.

**Exercise B — Capacity-limited service.** Add a `Semaphore(20)` inside the HTTP handler to simulate a backend that handles at most 20 requests concurrently. Excess requests will queue. Compare the effects of `virtual-limited-24`, `virtual-unbounded`, and a limit of 20; observe throughput, errors, and tail latency. Do not confuse HTTP handler thread count with backend capacity.

**Exercise C — Fan-out I/O.** Each logical request needs to fetch data concurrently from three independent endpoints. Compare a fixed platform pool with virtual threads, waiting for all futures to succeed and aggregating results. If one branch times out, cancel the remaining branches when appropriate and ensure no executor/task runs indefinitely.

**Exercise D — CPU tasks.** Replace the HTTP call with an iterative computation algorithm with a verifiable result, measuring with a worker count near CPU cores and with a virtual executor. Explain why the results differ from I/O-bound work.

**Exercise E — Runtime observation.** Capture JFR or thread dumps while the program is running; analyze blocking platform workers and parked/unmounted virtual threads. If running on JDK 21–23, add a variant that intentionally holds a monitor while waiting to observe pinning. On JDK 24+, compare the difference under JEP 491.

## 12. Common Mistakes

1. **Using Java 17 and looking for virtual thread APIs:** JDK 21+ is required for stable `newVirtualThreadPerTaskExecutor`.
2. **Comparing different tasks:** having one mode make more HTTP requests, use different timeouts, or hit a different server makes measurements meaningless.
3. **Assuming virtual threads speed up individual HTTP requests:** the main benefit is scaling the concurrency of waiting tasks, not reducing network or server time for a single request.
4. **Using a fixed pool of virtual threads:** virtual threads should be bound to tasks; use semaphores/admission control to limit downstream load instead of pooling virtual workers like platform threads.
5. **Not closing resources:** leaving the server, executor, HTTP client, or tasks running after a test causes leaks or skews measurements.
6. **Counting only submitted tasks:** 120 submitted tasks does not mean 120 successful HTTP calls. Check status/body and all Futures.
7. **Ignoring errors/timeouts:** fast numbers caused by tasks failing early are not better throughput. Report errors and stop drawing conclusions when runs are not comparable.
8. **Skipping warmup or running only once:** JIT/connection setup/GC make single-run results unstable.
9. **Spawning virtual threads recklessly because they are "almost free":** sockets, buffers, downstream services, memory, and rate limits are still finite.
10. **Confusing pinning with locking in general:** monitor-related pinning changed in JDK 24; contention and lock ownership remain separate issues.
11. **Ignoring correctness when changing architecture:** virtual threads carry the same race/deadlock risks if shared state is accessed improperly.
12. **Abusing ThreadLocal caches:** each virtual task has its own thread, gaining little from thread-bound caches while increasing allocations.
13. **Using `Thread.sleep` as the sole conclusion about networking:** sleep is useful to illustrate waiting, but socket I/O and production-like infrastructure are needed for real evaluations.
14. **Lacking an ownership map:** closing a shared executor/client while other threads still use it causes errors; define who creates and who closes each resource.

## 13. Conclusion

**Platform threads** are suitable when concurrency is moderate or most work is CPU-bound; a fixed pool directly caps the number of OS threads/workers. **Virtual threads** allow writing synchronous blocking I/O code in a thread-per-task style without holding a dedicated OS thread per waiting request; they are useful when a system must serve many independent I/O-bound tasks simultaneously.

The exercise is only complete when you both measure timing and prove **correct HTTP results**, explain the waiting mechanism, and identify server/downstream limits. The final choice of model must be based on workload and measurements rather than thread counts alone.

### Official Java Documentation

- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [Oracle Java 21 — Executors API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Oracle Java 21 — HttpClient API](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java 21 — HttpServer API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [JEP 491 — Synchronize Virtual Threads without Pinning (JDK 24)](https://openjdk.org/jeps/491)
- [Oracle Java 24 — Significant Changes](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html)
