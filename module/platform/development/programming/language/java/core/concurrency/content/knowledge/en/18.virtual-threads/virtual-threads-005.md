# Thread-per-request for Blocking I/O with Virtual Threads (Java 21+)

## 1. Problem Statement and Goals

**Thread-per-request** is a processing model in which each independent request is assigned to its own execution thread. The thread receives the request, executes steps sequentially (reading input, calling a service or database, waiting for I/O, building a response), and then terminates. This model is easy to read and debug because the handler code retains a synchronous, linear style.

With traditional **platform threads** (Java threads typically bound to an OS thread while running), keeping thousands of threads alive just to wait on sockets, files, or responses from external systems consumes memory and scheduling overhead. One common workaround is bounding the thread pool, but when all workers are blocked on I/O, new requests must wait in a queue even when the CPU is idle.

Starting in **Java 21**, virtual threads (JEP 444) are a standard feature. A virtual thread is still a `Thread` object and provides the familiar synchronous programming style, but the Java runtime can **suspend it and yield the underlying platform thread** when it encounters many supported waiting operations. This makes it possible to use **one virtual thread per request** at very high concurrency without dedicating an OS thread to every waiting request.

After this lesson, you should be able to:
- Describe the request-processing flow and why blocking I/O saturates a platform-thread pool.
- Write Java 21+ code that handles each connection/request on a virtual thread.
- Distinguish between **concurrent requests**, **platform thread count**, **throughput**, and **latency**.
- Apply timeouts, backpressure, and real resource limits; recognize pinning scenarios and common implementation pitfalls.

## 2. How It Works

### 2.1. With Platform Threads

Consider a worker processing a request in sequence:

1. Receive the request.
2. Read data from a socket (may wait).
3. Call an external system using a synchronous API (may wait).
4. Compute the result and write the response.
5. Complete the request.

When an I/O operation waits, the platform thread is typically blocked as well. If a pool has 200 threads, 200 waiting requests can occupy the entire pool, forcing the 201st request into a queue. Increasing the pool size indefinitely is not a sustainable solution because every OS thread carries its own overhead.

### 2.2. With Virtual Threads

A virtual thread is **mounted** onto a platform thread called a **carrier** in order to execute. When it encounters a blocking operation supported by the JDK, the virtual thread can **unmount**, save the necessary state, and yield the carrier to another virtual thread. When I/O becomes ready, it is scheduled to resume, potentially on a different carrier.

```text
Request A → Virtual thread A ──[read socket, wait]──┐
                                                    │ unmount
                                                    ▼
                              Carrier thread → run request B/C/...
                                                    │
                          A's I/O completes ────────┘
                                                    ▼
                        Virtual thread A is remounted
                                                    ▼
                                      Write response A
```

This is still **blocking from the application code's perspective**: `readLine()` only returns when data arrives, on EOF, on error, or on timeout. What changes is how the JVM uses the carrier during the wait. Not every native operation, legacy library, or blocking call guarantees unmounting.

### 2.3. What Improves and What Does Not?

| Characteristic | Platform thread-per-request | Virtual thread-per-request |
|---|---|---|
| Programming unit | One request per thread | One request per virtual thread |
| When waiting on suitable I/O | Typically holds the OS thread | Can yield the carrier |
| Feasible number of concurrently waiting tasks | Strongly constrained by OS threads | Usually much higher if other resources allow |
| Synchronous business code | Yes | Yes |
| Speeding up CPU-bound tasks | Not automatically | Not automatically |
| Connections, heap, downstream, quotas | Still a limit | **Still a limit** |

Virtual threads primarily improve **the ability to serve many concurrently waiting I/O tasks (throughput/scalability)**. They **do not turn a 300 ms network call into 3 ms**, do not add extra CPU cores, and do not remove connection limits.

## 3. Java 21+ API for Creating One Thread per Task

The common approach is `Executors.newVirtualThreadPerTaskExecutor()`. Each `submit` or `execute` call creates a new virtual thread to run the task; this executor is **not a pool that reuses a fixed number of virtual threads**.

The first example uses `Thread.sleep` to simulate waiting time and illustrate the independent processing structure. This is **not a real network I/O example**; Section 4 uses real sockets.

**File `VirtualIoBatch.java`:**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualIoBatch {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<String>> results = new ArrayList<>();

            for (int id = 1; id <= 3; id++) {
                final int requestId = id;
                results.add(executor.submit(() -> {
                    Thread.sleep(100); // Simulate waiting time
                    return "request " + requestId
                            + ", virtual=" + Thread.currentThread().isVirtual();
                }));
            }

            // Retrieve in submission order for deterministic stdout.
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
        }
    }
}
```

Run with JDK 21 or later:

```bash
javac VirtualIoBatch.java
java VirtualIoBatch
```

Stdout:

```text
request 1, virtual=true
request 2, virtual=true
request 3, virtual=true
```

The three tasks can wait **concurrently**, yet the results are printed in order because the loop calls `Future.get()` in the stored submission order. `get()` waits for completion and may throw `ExecutionException` or `InterruptedException` (the example declares `throws Exception` only to stay concise). The `try`-with-resources block on `ExecutorService` closes the executor and waits for submitted tasks to finish; this requires tasks to be able to terminate.

You can also create virtual threads directly with `Thread.ofVirtual().start(runnable)` or create a `ThreadFactory` via `Thread.ofVirtual().factory()`. When handling many independent requests and collecting results, a per-task executor is usually easier to manage.

## 4. Practical Example: One Virtual Thread per TCP Connection

This example consists of a pure-Java server and client using blocking sockets. Each time `accept()` returns a connection, the server dispatches the connection handling to a **new virtual thread**. The `BufferedReader.readLine()` call in the handler genuinely waits on network data. In this example, **each connection sends one line and receives one line**; treat one connection as equivalent to one request to demonstrate the model.

### 4.1. Server

**File `VirtualEchoServer.java`:**

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class VirtualEchoServer {
    public static void main(String[] args) throws IOException {
        try (ServerSocket server = new ServerSocket()) {
            // Listen only on the local machine.
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 9090));

            try (ExecutorService requests =
                         Executors.newVirtualThreadPerTaskExecutor()) {
                System.out.println("Listening on loopback port 9090");

                while (true) {
                    Socket client = server.accept();
                    requests.execute(() -> handle(client));
                }
            }
        }
    }

    private static void handle(Socket client) {
        try (client) {
            client.setSoTimeout(5_000); // Limit how long a read waits.
            BufferedReader input = new BufferedReader(
                    new InputStreamReader(
                            client.getInputStream(), StandardCharsets.UTF_8));
            BufferedWriter output = new BufferedWriter(
                    new OutputStreamWriter(
                            client.getOutputStream(), StandardCharsets.UTF_8));

            String line = input.readLine(); // Blocking socket I/O
            if (line != null) {
                output.write("echo: " + line);
                output.newLine();
                output.flush();
            }
        } catch (IOException exception) {
            System.err.println("Request failed: " + exception.getMessage());
        }
    }
}
```

The server keeps one platform thread (the `main` thread) for `accept()`, then processes **each connection on its own virtual thread**. It does not tie up a platform thread waiting for data from each client. `setSoTimeout(5_000)` limits how long a single socket read operation waits before throwing `SocketTimeoutException`; it is not an overall deadline for the entire request.

The `while (true)` loop is a continuous serving loop, stopped manually with Ctrl+C. This is a minimal demo without graceful shutdown, authentication, connection limits, or protection against slow-sending clients.

### 4.2. Client

**File `EchoClient.java`:**

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class EchoClient {
    public static void main(String[] args) throws Exception {
        Socket socket = new Socket();
        socket.connect(new InetSocketAddress(
                InetAddress.getLoopbackAddress(), 9090), 3_000);
        socket.setSoTimeout(5_000);

        try (socket) {
            BufferedReader input = new BufferedReader(
                    new InputStreamReader(
                            socket.getInputStream(), StandardCharsets.UTF_8));
            BufferedWriter output = new BufferedWriter(
                    new OutputStreamWriter(
                            socket.getOutputStream(), StandardCharsets.UTF_8));

            output.write("xin chao");
            output.newLine();
            output.flush();
            System.out.println(input.readLine());
        }
    }
}
```

In the directory containing both files, compile:

```bash
javac VirtualEchoServer.java EchoClient.java
```

Terminal 1:

```bash
java VirtualEchoServer
```

Initial server stdout:

```text
Listening on loopback port 9090
```

Terminal 2:

```bash
java EchoClient
```

Client stdout:

```text
echo: xin chao
```

Open multiple clients concurrently: each connection has its own handler, so a client still waiting to finish sending its line will not block other handlers. Completion order across clients is **not guaranteed**. Port 9090 must be free, and the server must be started before the client.

### 4.3. Tracing a Request Through Its States

1. `ServerSocket.accept()` returns a new `Socket`.
2. `requests.execute(...)` starts a virtual thread for the handler.
3. The handler creates the reader/writer and calls `readLine()`, which may wait until enough data arrives.
4. While this socket operation can unmount, the carrier is free to run another virtual thread.
5. When data arrives, the handler resumes right after `readLine()`, writes the response, and calls `flush()`.
6. `try (client)` closes the socket even if an I/O error occurs; the virtual thread terminates.

The model keeps handler code linear like normal single-request processing, while increasing the number of I/O-waiting requests that can be served on the same set of carriers.

## 5. Applying This in Application Code

A synchronous handler can be structured like this (this is **pseudocode**, not a standalone Java program):

```java
Response handle(Request request) {
    Input input = validate(request);       // CPU, short
    Data data = blockingFetch(input);      // I/O waiting
    Result result = transform(data);       // CPU
    blockingWrite(result);                 // I/O waiting
    return Response.ok(result);
}
```

When each request has a virtual thread, you do not need to manually split every waiting point into callbacks, but you still must respect each API's contract, check timeouts, and handle errors. `blockingFetch` and `blockingWrite` here are illustrative undefined functions; the application must supply real implementations.

An important design decision: **the unit of concurrency should reflect a business task** (a request, an independent job) rather than spawning virtual threads arbitrarily for every tiny operation. If a request needs to query two independent data sources in parallel, you can use two tasks/futures and combine their results; remember to cancel the remaining work if one source fails or times out.

## 6. Resource Limits: Many Virtual Threads Do Not Mean Unlimited Requests

`newVirtualThreadPerTaskExecutor()` does not bound the number of submitted tasks. Virtual threads are cheaper than platform threads, but **each request still holds objects, buffers, sockets, memory, and may occupy downstream connections**. A server that opens 100,000 more database connections simply because it has 100,000 virtual threads can bring down downstream systems.

Use **backpressure/admission control** before starting expensive work or accessing finite resources:

- **Semaphore** limits how many tasks can concurrently use a resource; permits are released in `finally`.
- **Connection pool** regulates the actual number of connections to downstream services (the limit must be based on downstream capacity, not virtual thread count).
- **Timeout/deadline** for connecting, reading, API calls, and the entire operation; fail fast or reject early under overload.
- **Bounded queue / rejection** at the request ingress boundary when needed to protect the system; avoid unbounded queuing that drives up latency and heap usage.

The following example is a **snippet placed inside a handler**, limiting concurrent access to `slowDependency` to at most 20 calls, assuming `Semaphore permits` is shared and `slowDependency.call()` is an I/O call with a timeout:

```java
if (!permits.tryAcquire()) {
    throw new IllegalStateException("Dependency is busy");
}
try {
    return slowDependency.call();
} finally {
    permits.release();
}
```

Do not place `new Semaphore(20)` inside **each** handler; doing so gives every request its own set of permits and provides no global limit. In a real API, design permit wait behavior, interrupt handling, overload error codes, and resource cleanup appropriately.

**Two distinct limits:** virtual threads allow many concurrent requests *waiting*, whereas a semaphore/pool determines how many requests may *use a scarce resource*. Do not turn virtual threads into a fixed-size pool just to protect downstream systems.

## 7. Pinning, Blocking, and Differences Across JDK Versions

A virtual thread can yield its carrier only if the runtime can unmount it at that waiting point. **Pinning** occurs when a virtual thread cannot release its carrier during certain waits, reducing the number of available carriers.

- On **JDK 21–23**, long or frequent blocking inside `synchronized` can pin the carrier. Avoid holding a monitor across long I/O calls; if locking around such an operation is required, consider `ReentrantLock` or narrowing the critical section.
- Starting in **JDK 24**, JEP 491 changes monitor handling so virtual threads can synchronize without being pinned by `synchronized` in the old way. Do not apply JDK 21 warnings verbatim to newer JDKs.
- Blocking inside certain **native/foreign-function** calls can still pin the carrier; behavior depends on the JDK version and library. Having virtual threads does not turn every blocking library into nonblocking at the runtime level.
- `Thread.sleep` is an example of a wait supported by the virtual-thread runtime; for specific I/O libraries, measure rather than assuming they always yield the carrier.

On JDK 21, you can inspect `jdk.VirtualThreadPinned` via JDK Flight Recorder (JFR) when diagnosing pinning. You can use `-Djdk.tracePinnedThreads=full` to print stack traces in JDK 21; check the tools, options, and their semantics against the exact JDK version you run.

Important: pinning **does not inherently cause incorrect results**. It primarily impacts scalability when it happens frequently and each pinned wait lasts significantly long.

## 8. Timeouts, Interruption, and Errors

- **Blocking without timeouts:** can leave a virtual thread, socket, and associated objects alive indefinitely; too many hung tasks will still exhaust heap or off-JVM resources.
- **`Future.cancel(true)`:** requests interrupting the task; there is no guarantee every library or I/O call will cancel promptly. Design explicit task termination and resource closing.
- **`InterruptedException`:** if caught for cleanup without rethrowing, usually call `Thread.currentThread().interrupt()` to preserve the interrupt status; do not silently swallow interrupts.
- **Task failures:** when using `submit`, task exceptions surface through `Future.get()` wrapped in `ExecutionException`. When using `execute`, handle and log exceptions at the handler boundary.
- **`ExecutorService.close()`:** waits for tasks to complete; if a task is stuck indefinitely, shutdown can hang as well. Implement deadlines, socket closing, or task cancellation for production servers.
- **ThreadLocal:** virtual threads still support `ThreadLocal`, but do not use it as a large per-thread cache; a high virtual thread count multiplies heap usage. Request-scoped data should have a clear lifecycle.

In the TCP demo, `setSoTimeout` bounds each individual read operation; it does **not** automatically bound the entire connection lifetime or write duration. Production systems also need limits on message size, total deadline, idle time, memory buffers, and connection count.

## 9. Common Anti-patterns

| Mistake | Why it causes problems | How to handle it |
|---|---|---|
| Fixed pool of 50 virtual threads out of fear of creating too many | Uses thread limits to mask other resource limits; requests queue up again | One virtual thread per request; bound downstream access with pools/permits |
| Adding virtual threads to speed up CPU-heavy workloads | CPU cores remain finite | Profile CPU, optimize algorithms, or bound CPU jobs appropriately |
| Dropping all timeouts because virtual threads are cheap | Tasks still hold memory/sockets/connections | Use timeouts, deadlines, and cleanup |
| Opening thousands of connections to a resource that handles only 100 | Overloads downstream even when the JVM still has capacity | Admission control, bounded pools, and backpressure |
| Assuming every blocking call releases the carrier | Pinning/native blocking depends on JDK and libraries | Verify at runtime with profiling/JFR and load tests |
| Using `ThreadLocal` to cache large objects per request | No thread reuse like a pool; wastes heap | Pass context explicitly; keep per-request data compact |
| Not collecting `Future` results or ignoring task errors | Errors are lost or hard to detect | Await/aggregate results and log errors with context |

## 10. Measuring Effectiveness Properly

Run load tests with the **same business logic and the same resource limits** when comparing a platform-thread pool against virtual-thread-per-task. Gradually increase concurrent requests and measure:

1. **Throughput**: requests/second actually completed.
2. **Latency p50/p95/p99**: including queuing, I/O wait, and processing time.
3. **CPU, heap/GC, connection counts, file descriptors**, and downstream utilization.
4. **Timeouts, errors, rejected requests**, and waiting task counts; observe pinning if on a relevant JDK.

For example, a request spending roughly 10 ms on CPU and 300 ms waiting on I/O can benefit noticeably as concurrency increases. If each request simply does 300 ms of CPU work, virtual threads will not make the CPU faster. Actual gains must be **measured under realistic conditions**, not extrapolated from a 300/10 ratio as a performance guarantee.

## 11. Adoption Checklist

- [ ] Identified independent requests/jobs and blocking I/O points.
- [ ] Running JDK 21+ and chose `newVirtualThreadPerTaskExecutor()` or `Thread.ofVirtual()` as appropriate.
- [ ] Each task has a well-defined lifecycle, output, and error handling.
- [ ] Timeouts/deadlines are configured and sockets, streams, and connections are released on all paths.
- [ ] Finite resources (downstream services, databases, connection pools, memory) are bounded.
- [ ] Checked pinning behavior for the **exact JDK version** in use, rather than assuming from another version's docs.
- [ ] Load tested and verified throughput, latency, resource usage, and overload failure behavior.

## 12. Self-Check

1. If 2,000 requests simultaneously wait on I/O for 500 ms, why can a 200-worker platform thread pool build up a queue even though CPU is idle?
2. When a handler calls `readLine()` on a virtual thread, is the **source code** still blocking? Is the carrier always held?
3. Why is there no need to create a pool of 100 virtual threads to cap database connections at 100? Which mechanism enforces that limit properly?
4. Two variants of a workload: 300 ms waiting on an API vs. 300 ms of computation. Which variant is more likely to benefit from moving to virtual threads, and why?
5. Why should `synchronized` pinning warnings from JDK 21 be re-evaluated when an application upgrades to JDK 24+?

**Suggested answers:** (1) a worker waiting on I/O still occupies a pool slot; (2) the handler is still written in blocking style, while the carrier can be released if the wait point is supported and not pinned; (3) use a semaphore or connection pool for bounded resources; (4) the I/O-waiting workload; (5) JEP 491 changes monitor behavior.

## Reference Documentation

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444) (standard feature in Java 21).
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) (model, scheduling, client/server examples, pinning on JDK 21).
- [Java 21 API — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html) (`newVirtualThreadPerTaskExecutor()`).
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) (changes starting in JDK 24).

> **Key takeaway:** Virtual threads let you write **clear, synchronous code** and serve many **I/O-waiting** requests with lower thread overhead. They do not replace timeouts, resource limits, backpressure, or load testing.