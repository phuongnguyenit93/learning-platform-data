# Limiting connections, requests, and active buffer memory

*Java Advance – networking · Category: Reliability · Java 17+*

## 1. Why do these three limits need to be designed together?

A networking application does not just need to **handle requests**; it must **continue operating when requests spike, the peer is slow, or data is untrusted**. The core resources typically consumed are:

1. **Open connections**: socket/TCP connections, file descriptors, TLS state, idle keep-alive connections, and native network buffers.
2. **In-flight or queued requests**: HTTP requests, tasks in thread pools, futures, queue entries, database queries, and downstream calls.
3. **Retained buffers**: `byte[]`, heap/direct `ByteBuffer`, buffered request/response bodies, socket send/receive buffers, buffer pools, and application caches.

**Limiting one resource type does not automatically limit the other two.** A single HTTP/2 TCP connection can carry many concurrent HTTP streams/requests; a single HTTP request downloading a large file can retain many MiB of buffers; and an HTTP/1.1 keep-alive connection can remain open for a long time **even when no request is being processed**.

~~~text
                          Networking service
                                  |
    +-----------------------------+-------------------------------+
    |                             |                               |
    v                             v                               v
Connection budget            Request budget                 Memory budget
open TCP/TLS sockets         in-flight operations           retained buffer bytes
idle connections             request queues                 heap + direct memory
file descriptors             worker threads                 body size and caches
    |                             |                               |
    v                             v                               v
max connections              max active + queue             max bytes + pool sizes
idle timeout                 overload admission              per-request byte quota
backlog (pending only)       deadline + cancel              release in finally
    |                             |                               |
    +-----------------------------+-------------------------------+
                                  |
                     Bounded and observable load
~~~

Three operational goals:

- **Stability:** load exceeding capacity is rejected/throttled in a controlled manner, instead of exhausting heap, running out of sockets, or creating unbounded queues.
- **Fairness:** one large client/tenant/request does not consume all resources of all other users.
- **Predictability:** there are explicit limits, timeouts, metrics, and concrete error responses; overload does not turn into “the server just hangs”.

This is knowledge about **resource budgets and backpressure**. There is no single Java configuration that replaces all limits, especially when combining TCP, HTTP/1.1, HTTP/2, `HttpServer`, `HttpClient`, NIO, and thread pools.

## 2. Distinguish quantities before setting limits

| Quantity | Unit | What does it measure? | Not equivalent to |
|---|---|---|---|
| Open TCP connections | Connections/sockets | Open TCP connections, including active and idle | Number of running requests |
| Accepted connections | Connections | Connections accepted by the application from the accept loop | Number of completed requests |
| Backlog | Pending connections | Connection requests waiting to be accepted in the kernel | Max active connections |
| Idle keep-alive connections | Connections | Connections with no in-flight request kept for reuse | Request queue |
| In-flight HTTP requests | Requests | Requests received/sent that have not yet completed per contract | TCP connection count |
| Queued requests/tasks | Items | Tasks accepted but not yet started by the executor | Active worker threads |
| Request rate | Requests/second | Arrival rate over a time interval | Concurrency |
| Heap buffer usage | Bytes | `byte[]`, heap `ByteBuffer`, and still-referenced objects | Direct memory |
| Direct buffer usage | Bytes | Buffers allocated via `ByteBuffer.allocateDirect` / native pooling | `Runtime.totalMemory()` |
| Cached response/data | Bytes / entries | Data retained for reuse (true cache) | Active I/O buffers |

**Three counterexamples:**

- There is only **1 HTTP/2 connection**, yet **100 requests** can be multiplexed on that connection. A socket limit of 1 does not cap requests at 1.
- There are only **5 requests**, each buffering a **50 MiB** response into a `byte[]` → the payload alone can hold **250 MiB**, not counting copies, JSON objects, TLS, and native buffers.
- There are **500 keep-alive connections** but **0 active requests**. Request-handling threads may be idle, yet file descriptors and connection buffers are still held.

Therefore, each resource needs **an independent measurement metric and admission policy**.

## 3. Budget model: active, waiting, and retained bytes

A simple model for a server:

~~~text
Incoming connections (kernel listen backlog)
            |
            v
Connection accepted + socket lifetime
            |
            v
HTTP request parsed
            |
            v
Admission? active requests < limit
            |
       +----+----+
       |         |
      yes        no
       |         |
       v         v
bounded worker   503 / 429 / close per policy
       |
       v
reserve request buffers / downstream slots
       |
       v
business processing + response streaming
       |
       v
close streams, release request slot, release memory reservation
~~~

When designing limits, ask about both **peak** and **resource holding duration**. For example, 100 in-flight requests with an average latency of 20 ms is a very different load from 100 requests each waiting 30 seconds for downstream.

### 3.1. Invariants to maintain

~~~text
0 <= openConnections <= configuredConnectionBudget
0 <= activeRequests   <= configuredRequestBudget
0 <= queuedTasks      <= configuredQueueCapacity
0 <= reservedBytes    <= configuredBufferBudget
~~~

These are **policy/application-layer goals**, not automatically satisfied just by setting `ServerSocket.bind(backlog)` or `ThreadPoolExecutor.maximumPoolSize`. A single request can consume multiple buffer types at once, and a socket can remain open after the request.

A sound control mechanism uses:

- **Counted permits** (e.g., `Semaphore`) for active requests or application-managed connections.
- **Bounded `BlockingQueue`** for waiting tasks.
- **Byte reservation** before allocating/retaining buffers.
- **Deadlines/idle timeouts** so requests cannot hold permits forever.
- **Release in `finally`** or a terminal callback (success, failure, cancel), including on exceptions.

## 4. Limiting connections: do not confuse with backlog

### 4.1. ServerSocket.bind(backlog) is only the queue of connections waiting to be accepted

~~~java
// Snippet: plain TCP socket server, not a complete server.
ServerSocket listener = new ServerSocket();
listener.bind(new InetSocketAddress("127.0.0.1", 8080), 64);
~~~

The **`backlog = 64`** parameter asks the operating system to reserve a queue for **connections waiting to be accepted**. The Java 17 Javadoc states this is a requested maximum and **exact behavior depends on the implementation/OS**; the OS may cap or ignore the value.

**Backlog is not:** a limit on accepted sockets, a limit on HTTP requests, thread count, file descriptors, or total RAM. A server can accept thousands of connections even with a backlog of 64 if it continuously drains the queue.

| Value | What it affects |
|---|---|
| `backlog` | Queue of incoming connections before the application accepts them |
| Active connection cap | Number of open/managed connections |
| Socket read timeout | Time spent reading without progress |
| Idle timeout | Time a connection is allowed to remain idle |
| Request concurrency cap | Number of executing HTTP requests |
| Worker queue capacity | Number of tasks waiting to be picked up by the executor |

### 4.2. Connection limit for a custom TCP server

An accept loop can use a `Semaphore` to limit **the number of sockets handled concurrently**:

~~~java
// Conceptual snippet; serverSocket, workerPool, and processSocket are already configured.
// Not a standalone Java program.
Semaphore connectionSlots = new Semaphore(100);

for (;;) {
    Socket socket = serverSocket.accept();
    if (!connectionSlots.tryAcquire()) {
        socket.close();                 // Policy: reject new connection.
        continue;
    }
    try {
        workerPool.execute(() -> {
            try (Socket owned = socket) {
                processSocket(owned);  // Read/write with timeout + byte limit.
            } catch (IOException ex) {
                // Log redacted info and update error metrics.
            } finally {
                connectionSlots.release();
            }
        });
    } catch (RejectedExecutionException rejected) {
        socket.close();
        connectionSlots.release();      // Do not leak permit if task did not run.
    }
}
~~~

This is a **pattern for a blocking socket server**. If you hold sockets in a queue while acquiring the permit immediately upon accept, the permit includes connections waiting to be processed; if you want to distinguish active vs. accepted/queued limits precisely, you must separate the counters. With asynchronous NIO, you do not need one thread per connection, but you still need a connection budget and timeouts.

**Note:** closing a raw TCP socket does not return a structured HTTP 503. If the HTTP request has been parsed and the server is able to write a response, returning a short 503 response is usually better. A connection that was accepted without enough workers may have nowhere to handle HTTP immediately; additional admission at the ingress/reverse proxy or handler is needed.

### 4.3. OS file descriptors and source ports

Each socket typically consumes a file descriptor/handle. An application also opens files, pipes, database connections, TLS sessions, and DNS resources. Opening too many sockets risks:

- `Too many open files` / `SocketException`.
- Exhausting ephemeral source ports on the client side, especially when creating new connections continuously or accumulating many `TIME_WAIT` sockets.
- Kernel socket buffers and native TLS buffers ballooning in memory.
- Many idle connections holding resources despite zero active requests.
- Slow/half-open connections holding slots for minutes.

Therefore, max connections must be paired with **keep-alive/idle policies, socket timeouts, graceful close, and monitoring**. Raising the OS file descriptor limit only addresses one bottleneck; it does not replace application-level limits.

## 5. Configuring connection caps in JDK HttpServer

Java 17's `com.sun.net.httpserver.HttpServer` lets you specify the backlog on creation/bind and an executor for handling requests:

~~~java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 8080),
        64  // TCP pending accept backlog, NOT max open connections
);
server.setExecutor(workers);           // Must be set before server.start().
server.start();
~~~

This is a **snippet**: `workers` must be created; to bound threads/queues, see the executor section below.

According to *Oracle Java 17 Java Networking* for the default JDK implementation, there are **JDK-specific system properties**:

| Java system property (JDK 17 implementation) | Documented description | What it does NOT guarantee |
|---|---|---|
| `jdk.httpserver.maxConnections` | Maximum **open connections**, including active and idle; 0/negative means no limit applied | Not an in-flight request cap |
| `sun.net.httpserver.maxIdleConnections` | Cap on retained **idle connections** | Does not limit active connections |
| `sun.net.httpserver.idleInterval` | Time a connection is kept idle (seconds) | Not an overall request deadline |
| `sun.net.httpserver.maxReqHeaders` | Maximum number of request header fields | Does not limit response body |
| `sun.net.httpserver.maxReqHeaderSize` | Maximum size of request headers | Does not limit request count |
| `sun.net.httpserver.maxReqTime` | Time limit for the request-receiving phase per JDK implementation | Not an independent business processing deadline |
| `sun.net.httpserver.maxRspTime` | Time limit for the response phase per JDK implementation | Does not replace downstream timeouts |
| `sun.net.httpserver.drainAmount` | Maximum unread request bytes the server attempts to discard to allow connection reuse | Not the application's max request body |

According to the JDK 17 documentation, `jdk.httpserver.maxConnections` defaults to `-1` (no limit enforced by this property). The default values of the `sun.net.httpserver.*` properties are **version-specific implementation details**; do not design a service assuming all Java vendors/versions will behave identically.

Example configuration at JVM startup:

~~~bash
java -Djdk.httpserver.maxConnections=200 \
     -Dsun.net.httpserver.maxIdleConnections=50 \
     -Dsun.net.httpserver.idleInterval=30 \
     -jar your-server.jar
~~~

`your-server.jar` is an illustrative artifact, not included with this lesson. On Windows, you can pass the same `-D` arguments on **one line**. Verify against your actual JDK and load-test before applying in production: these properties are **not portable setters on the `HttpServer` class**, and behavior when reaching the cap depends on the implementation.

**Do not use `jdk.httpserver.maxConnections` as a substitute for a request concurrency cap.** HTTP keep-alive allows multiple sequential requests on the same socket, and a single request can retain large amounts of memory/worker resources.

## 6. Client-side: open connection limits are DIFFERENT from request limits

`java.net.http.HttpClient` (Java 11+, included in Java 17) shares a client across many requests and supports connection reuse. `HttpClient.Builder` exposes options such as `version`, `connectTimeout`, `executor`, `proxy`, and `followRedirects`, but **has no portable public `maxConnections` or `maxConcurrentRequests` setter in the Java 17 builder**.

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .connectTimeout(Duration.ofSeconds(3))
        .build();
~~~

**Key point:** `.executor(myPool)` configures the executor for asynchronous/dependent tasks. **Do not treat that pool's size as a guaranteed ceiling on TCP connections or requests currently in flight over the network.** To limit in-flight HTTP requests issued by your application, add an admission permit at the API-calling layer.

### 6.1. Commonly misunderstood JDK-specific HTTP client properties

Oracle Java 17 *Java Networking* lists:

| Property | Exact meaning per Java 17 docs | Pitfall |
|---|---|---|
| `jdk.httpclient.connectionPoolSize` | Cap on connections in the **HTTP/1.1 keep-alive cache**; 0 means unbounded **cache** | **Not** max active connections or a global in-flight request cap |
| `jdk.httpclient.keepalive.timeout` | Time limit for keeping idle HTTP/1.1 connections in the keep-alive cache | Not total duration of a request |
| `jdk.httpclient.maxstreams` | Maximum **HTTP/2 streams per connection** per implementation (JDK 17 docs note 100) | Not a global cap on requests across all connections |
| `jdk.httpclient.bufsize` | Size of certain internally allocated buffers (JDK 17 docs note default 16 KiB) | Not total memory budget across all responses |
| `jdk.httpclient.receiveBufferSize` | Socket receive buffer size per JDK/OS | Does not limit application body accumulation |

An easy mistake is:

~~~bash
java -Djdk.httpclient.connectionPoolSize=8 -jar your-client.jar
~~~

This command **does not guarantee that Java opens at most eight active TCP connections**. It specifies how many HTTP/1.1 connections are **kept in the keep-alive cache** when idle. Do not equate cached connection count with active socket count.

**Important for maintenance:** these are properties of the default JDK implementation, not a portable contract from `HttpClient.Builder`; verify the JDK/runtime version and observe metrics. Do not infer undocumented semantics from property names.

### 6.2. HTTP/1.1 and HTTP/2 have different request–connection relationships

~~~text
HTTP/1.1 (simplified):
  Connection A --> Request A in progress
  Connection B --> Request B in progress
  Connection C --> idle keep-alive

HTTP/2:
  Connection A --> Stream 1 / Request A
               --> Stream 3 / Request B
               --> Stream 5 / Request C
               --> ... multiplexed streams
~~~

HTTP/2 also has settings/flow control and server-advertised `SETTINGS_MAX_CONCURRENT_STREAMS`. Both HTTP/2 and the Java implementation have stream/flow-control ceilings, but **they do not replace application-level business request admission**. A single request can involve multiple redirects/retries, or hold an unconsumed streaming response body; you must define which phase the permit covers.

## 7. Limiting in-flight requests with Semaphore

`java.util.concurrent.Semaphore` manages a count of permits; `tryAcquire()` returns `false` immediately when slots are exhausted, without accumulating unbounded blocked threads. This is a common tool for **bulkheads / concurrency limits**.

~~~java
Semaphore requestSlots = new Semaphore(50, true);

if (!requestSlots.tryAcquire()) {
    // Server can return a short 503/Retry-After;
    // client can fail-fast or enqueue into a bounded queue.
    return;
}

try {
    processOneRequest();
} finally {
    requestSlots.release();
}
~~~

This is a **snippet**, not a standalone program. On the server, acquire only after routing the request to a handler and before expensive work; on the client, acquire **before issuing** `sendAsync` to avoid creating thousands of requests/futures when already overloaded.

### 7.1. What counts as an “in-flight request”?

You must clearly define when a permit is acquired and released:

- Server: from when the request is admitted until **business work and response body** complete or are aborted.
- Client using `BodyHandlers.ofString()/ofByteArray()`: when the response future completes **successfully**, the subscriber has already processed the full body per the handler; downstream business processing may still remain.
- Client using `BodyHandlers.ofInputStream()/ofLines()/ofPublisher()`: the `HttpResponse` future can complete **early right after headers**, **before EOF/onComplete**. **Do not release the permit just because the future returned `HttpResponse<InputStream>`** if the goal is to limit the request exchange until the body is fully consumed.
- For streaming, release the permit at **EOF/close/onComplete/onError/cancel** with clear ownership.
- Retries/redirects can generate additional HTTP exchanges; the policy must bound both total in-flight tasks and individual attempts if the goal is load control.

**Dangerous bug:** calling `release()` twice from two callbacks (e.g., a timeout and success race) causes the permit count to exceed the cap. Use an ownership token or atomic terminal state to guarantee single release. Conversely, forgetting to release on exception/cancel causes the service to gradually stop accepting requests even when load is gone.

### 7.2. Fairness and real-world load

`Semaphore(max, true)` supports fairness for waiting threads, but fairness has overhead and **`tryAcquire()` does not guarantee the exact same fairness as `acquire()`** per the API documentation. Consider starvation, priority, per-tenant fairness, and throughput.

During server overload, `tryAcquire` is useful when you want to **fail fast**. If you want to wait for a slot, use `tryAcquire(timeout, unit)` with a **very clear deadline**; do not use unbounded `acquire()` for thousands of server threads because it turns overload into thread starvation.

## 8. Limiting queues and worker threads

`Executor` schedules tasks. Maximum threads and **waiting** tasks must be configured **separately**. A common snippet:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(8);
~~~

This fixes worker threads at **8**, but `newFixedThreadPool`'s internal queue can **hold an unbounded number of waiting tasks** relative to application limits. Under load spikes, a long queue can retain request objects, `CompletableFuture`s, and body data in memory.

For a bounded queue, use `ThreadPoolExecutor` with `ArrayBlockingQueue`:

~~~java
ThreadPoolExecutor workers = new ThreadPoolExecutor(
        8, 8,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(32),
        new ThreadPoolExecutor.AbortPolicy());
~~~

Per the Javadoc, when both workers and queue are full, `AbortPolicy` throws `RejectedExecutionException` for new tasks.

| Component | Example | What does it limit? |
|---|---|---|
| `corePoolSize` | 8 | Core worker count |
| `maximumPoolSize` | 8 | Maximum worker count |
| `ArrayBlockingQueue<>(32)` | 32 | Tasks waiting in the queue |
| `AbortPolicy` | Reject | Behavior when executor has no remaining capacity |
| `Semaphore(16)` | 16 | Number of **admitted** requests per custom policy |
| `HttpServer.create(address, 64)` | 64 | Backlog of **pending TCP connections** |

**Do not add 8 + 32 and claim “the server is guaranteed to handle at most 40 HTTP requests”**: the executor may serve internal tasks, each task may span multiple steps, and the server may accept connections before a task is executed. These are distinct layers of the system and must be measured accurately.

### 8.1. RejectedExecutionException does not guarantee HTTP 503

If JDK `HttpServer` submits a task to a full executor, the executor can **reject at the dispatch layer**, before `HttpHandler.handle` ever runs. In that case, the handler has no chance to write status 503. Therefore:

- Use **handler-level admission** (`Semaphore.tryAcquire`) when you want to actively return `503`.
- Use a **bounded worker queue** to protect executor memory.
- You may need a **reverse proxy/ingress** or an HTTP server framework with overload handling if you want control even before the handler is invoked.
- Do not assume executor rejection is automatically translated into `503 Service Unavailable` with a `Retry-After` header.

### 8.2. Set the executor before starting the server

The Java 17 Javadoc for `HttpServer.setExecutor` requires configuring it before `server.start()`. If no executor is set, the default executor may use the thread created by `start()` to handle requests, which is unsuitable for reasoning about production concurrency/throughput.

~~~java
HttpServer server = HttpServer.create(address, 64);
server.createContext("/work", handler);
server.setExecutor(workers); // Before start
server.start();
~~~

Size the pool to the workload: CPU-bound differs from blocking I/O-bound. **Do not increase worker count indefinitely to “boost throughput”**: it increases thread stacks, context switching, queues, and downstream saturation; combine timeouts, admission, and resource budgets instead.

## 9. Structured overload responses: 503, 429, and Retry-After

Limiting resources is not just throwing exceptions or closing sockets; it is also deciding **what the client will see**.

| Situation | Typically appropriate response | Watch out for |
|---|---|---|
| Server/service temporarily unable to serve | `503 Service Unavailable` | Can include `Retry-After` |
| A user/API key exceeds its own rate quota | `429 Too Many Requests` | Can include `Retry-After` |
| Request body exceeds limit | `413 Content Too Large` | Do not read/buffer the entire body before rejecting |
| Invalid/oversized headers | `400` or protocol-layer rejection | May be blocked before the handler |
| Service cannot process because upstream is down | `502/503/504` depending on gateway semantics | Do not hide all errors inside 200 |
| Server hard cap at TCP accept/OS layer | Connection refused/reset/timeout | An HTTP status may **not be sent** |

Pattern for returning 503 in `HttpExchange`:

~~~java
byte[] response = "BUSY".getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set("Retry-After", "1");
exchange.getResponseHeaders()
        .set("Content-Type", "text/plain; charset=UTF-8");
exchange.sendResponseHeaders(503, response.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(response);
}
~~~

**`Retry-After: 1` is a hint to wait 1 second, not a guarantee that the server will have capacity after 1 second.** Clients need exponential backoff + jitter, a total deadline, and a retry budget; only retry when the request is idempotent or has a proper idempotency key/policy. If all clients retry at the exact same time, the system can suffer a **retry storm**.

**Intentional fail-fast is usually better** than holding requests until multi-minute timeouts while consuming extra buffers/threads. However, overly aggressive rejection can cause starvation: measure error rate, queue wait, and p95/p99 latency, and tune capacity to your SLO.

## 10. Limiting buffer memory: byte quotas, not just buffer counts

A buffer can be:

- `byte[]` residing in the **Java heap**.
- `ByteBuffer.allocate(n)` creating a heap buffer.
- `ByteBuffer.allocateDirect(n)` creating a direct buffer, typically with storage **outside the GC-managed heap**; direct memory still increases the process footprint.
- `ByteBuffer.wrap(existingArray)` merely wrapping an existing array; it can **share the same backing storage**.
- `ByteBuffer.slice()/duplicate()` creating views that share storage, so **you must not sum the full capacity of every view as independent data**.
- Kernel socket send/receive buffers, TLS implementation buffers, compressed/decompressed representations, cached bodies, and decoder/parser objects.

A quota counting only **the number of buffers** is insufficient: 100 buffers × 1 KiB and 100 buffers × 8 MiB consume vastly different memory. Measure **retained bytes by type**, alongside buffer count, allocation rate, and peak.

### 10.1. Buffer memory vs. cache memory

| Term | Purpose | Appropriate limit |
|---|---|---|
| Network read/write buffer | Temporarily hold bytes during transfer/parsing | Concurrent buffers × size; byte quota |
| Buffer pool | Reuse blocks to reduce allocation | Maximum retained bytes, idle count, eviction |
| HTTP response body collector | Assemble body for processing | Per-response max bytes + concurrent total |
| HTTP cache | Retain responses to serve again | Max entries/bytes + TTL/eviction |
| Kernel socket buffers | OS-maintained send/receive queues | OS/socket settings and connection count |
| Direct memory | Native/off-heap storage for direct buffers | JDK-specific limit + `BufferPoolMXBean` metrics |

This lesson focuses on **active buffers**, without turning an HTTP cache into a mandatory component. However, if your application has a real response cache, you must **separately set max cached bytes and an eviction policy**. A cache limited to 1,000 entries where each entry is 10 MiB can still hold nearly 10 GiB.

### 10.2. Heap and direct memory cannot all be reduced to -Xmx

`-Xmx` caps the heap, **not the process's total RSS**. Direct buffers, thread stacks, JVM metaspace, native libraries, socket buffers, and container overhead can all sit outside the heap limit.

`ByteBuffer.allocateDirect` can have higher allocation/deallocation cost than heap buffers; the Javadoc recommends preferring it for large/long-lived buffers and native I/O when there is **measurable benefit**, rather than replacing every `byte[]` with a direct buffer.

The JVM provides `-XX:MaxDirectMemorySize` in many HotSpot builds, but this is a JVM implementation option, **not a portable API capping total memory across all libraries, kernel sockets, and native allocations**. Check your JDK, container memory limits, and memory metrics instead of looking only at heap usage.

## 11. Reservation: reserve bytes before allocating

If multiple requests create large buffers simultaneously, checking the size **after allocation** is too late. A safer pattern:

~~~text
request needs 8 MiB
    |
    v
tryReserve(8 MiB)?
    |
    +-- false -> reject / wait with deadline / stream to disk
    |
    +-- true
           |
         allocate/borrow buffer
           |
         read/write/process
           |
         release buffer/reference
           |
         release(8 MiB) exactly once (finally)
~~~

A quota counter can use `AtomicLong.compareAndSet`:

~~~java
// Class snippet, full version is in the demo below.
boolean tryReserve(int bytes) {
    if (bytes < 0) throw new IllegalArgumentException();
    for (;;) {
        long current = used.get();
        if (bytes > limit - current) return false;
        if (used.compareAndSet(current, current + bytes)) return true;
    }
}
~~~

Checking `bytes > limit - current` prevents overflowing the limit under concurrent threads. **Reservation is the logical amount of memory promised/managed by the application**, not a measure of **heap reclaimed by GC**. Upon `release`, the object may not yet be garbage-collected; therefore, measure logical budget and actual process memory separately.

### 11.1. Why not count currentBuffers * standardBufferSize?

Sizes can vary; view buffers share underlying storage, and pooled buffers can be returned to a pool while still holding physical memory. If a pool retains 100 blocks × 64 KiB, even with **0 active borrowers**, it can still retain about **6.25 MiB** of block storage. Thus, two counters are needed:

- **Borrowed/reserved bytes:** blocks currently owned by in-flight operations.
- **Retained pool bytes:** blocks not currently borrowed but still held by the pool for reuse.

If you want a quota on **actual retained memory**, reserve when the pool **allocates a new block**, and do not release the actual-memory counter just because a block is returned to the pool; release the counter when the block is actually evicted/freed. If you only limit **concurrent usage**, releasing upon returning the block is right, but that is a different quota.

### 11.2. Avoiding double-release and leaks

A request can have multiple terminal events: success, timeout, cancel, connection reset, or handler exception. If both `finally` and a timeout callback call `release`, the counter can go negative or permits can exceed the max. If an exception occurs before `release`, the quota can be “lost” forever.

Use **clear ownership**, structured cleanup, and an exactly-once terminal state. For streams/publishers, keep the permit alive until **the body ends/closes**; do not release immediately when `HttpResponse<InputStream>` becomes available after headers.

## 12. Bound bodies and queues before buffers grow

### 12.1. Count actual bytes while reading request/response

`Content-Length` is metadata, not a guarantee of small data, and it can also be absent. For chunked bodies or compressed data, count **actual bytes flowing through the pipeline**.

~~~java
// Snippet: read stream with a limit, do not buffer body unboundedly.
long maxBytes = 1_000_000;
long count = 0;
byte[] block = new byte[8192];
for (int n; (n = input.read(block)) != -1;) {
    if (n > maxBytes - count) {
        throw new IOException("Body exceeds configured limit");
    }
    count += n;
    // Pass exact n bytes to a backpressure-aware parser/sink.
}
~~~

When `Content-Encoding: gzip` is present, you must distinguish the **compressed bytes** quota from the **decompressed bytes** quota: a small compressed payload can expand enormously (a decompression bomb). Avoid unbounded `readAllBytes()` on externally controlled HTTP bodies.

### 12.2. Queue items also hold memory

A queue with just 1,000 entries can still hold multiple GiB if each entry carries a 5 MiB payload. Budget concurrently by:

- **Queue length**: number of tasks.
- **Queued payload bytes**: amount of data waiting.
- **Queue wait time**: drop requests whose deadline has expired before starting work.
- **Per-tenant share**: one tenant cannot occupy all slots.

Do not “clear an overloaded queue” by increasing queue length unboundedly. That only prolongs wait times and increases memory pressure.

## 13. Runnable Java 17+ example: request admission and buffer quota

This complete example demonstrates **two independent limits** and produces **deterministic** results without `Thread.sleep`:

- The `HttpServer` runs on `127.0.0.1` with a `ThreadPoolExecutor` of **4 workers and a 4-task queue**, backlog 8. These numbers are **small demo settings**, not production recommendations.
- In `HttpHandler`, `Semaphore(2)` accepts **at most 2 in-flight requests**. The first two requests are held using a `CountDownLatch` to ensure they remain active; the third request receives **`503 Service Unavailable` and `Retry-After: 1`**.
- Once the latch opens, the first two requests receive `200 OK`. `finally` returns permits and decrements the active counter.
- `BufferQuota` uses `AtomicLong` to enforce a **16-byte logical reservation**. After reserving 12 bytes, requesting 8 more is rejected. After releasing 12 bytes, reserving 8 is allowed. This is a *logical byte budget*, not a real RSS measurement.
- All network connections are loopback; no Internet access or libraries outside the JDK are required.

**Create file `ResourceBudgetDemo.java`:**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class ResourceBudgetDemo {
    static final Semaphore REQUEST_SLOTS = new Semaphore(2, true);
    static final CountDownLatch STARTED = new CountDownLatch(2);
    static final CountDownLatch RELEASE = new CountDownLatch(1);
    static final CountDownLatch FINISHED = new CountDownLatch(2);
    static final AtomicInteger ACTIVE = new AtomicInteger();
    static final AtomicInteger MAX_ACTIVE = new AtomicInteger();

    static void reply(HttpExchange exchange, int status, String text)
            throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=UTF-8");
        if (status == 503) {
            exchange.getResponseHeaders().set("Retry-After", "1");
        }
        exchange.sendResponseHeaders(status, payload.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(payload);
        }
    }

    static void handle(HttpExchange exchange) throws IOException {
        try {
            if (!REQUEST_SLOTS.tryAcquire()) {
                reply(exchange, 503, "BUSY");
                return;
            }
            int now = ACTIVE.incrementAndGet();
            MAX_ACTIVE.accumulateAndGet(now, Math::max);
            STARTED.countDown();
            try {
                if (!RELEASE.await(5, TimeUnit.SECONDS)) {
                    reply(exchange, 503, "DEADLINE");
                    return;
                }
                reply(exchange, 200, "OK");
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            } finally {
                ACTIVE.decrementAndGet();
                REQUEST_SLOTS.release();
                FINISHED.countDown();
            }
        } finally {
            exchange.close();
        }
    }

    static class BufferQuota {
        final long limit;
        final AtomicLong used = new AtomicLong();

        BufferQuota(long limit) {
            if (limit < 0) throw new IllegalArgumentException();
            this.limit = limit;
        }
        boolean tryReserve(int bytes) {
            if (bytes < 0) throw new IllegalArgumentException();
            for (;;) {
                long current = used.get();
                if (bytes > limit - current) return false;
                if (used.compareAndSet(current, current + bytes)) return true;
            }
        }
        void release(int bytes) {
            long now = used.addAndGet(-bytes);
            if (now < 0) throw new IllegalStateException("Double release");
        }
    }

    static void await(CountDownLatch latch) throws Exception {
        if (!latch.await(5, TimeUnit.SECONDS)) throw new IOException("Deadline exceeded");
    }

    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor workers = new ThreadPoolExecutor(
                4, 4, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(4),
                new ThreadPoolExecutor.AbortPolicy());
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 8);
        server.createContext("/work", ResourceBudgetDemo::handle);
        server.setExecutor(workers);
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/work");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3)).build();
            HttpRequest req = HttpRequest.newBuilder(uri).GET()
                    .timeout(Duration.ofSeconds(5)).build();

            CompletableFuture<HttpResponse<String>> first = client.sendAsync(
                    req, HttpResponse.BodyHandlers.ofString());
            CompletableFuture<HttpResponse<String>> second = client.sendAsync(
                    req, HttpResponse.BodyHandlers.ofString());

            await(STARTED);
            HttpResponse<String> overloaded = client.send(
                    req, HttpResponse.BodyHandlers.ofString());
            System.out.println("overloadStatus=" + overloaded.statusCode());
            System.out.println("retryAfter=" +
                    overloaded.headers().firstValue("Retry-After").orElse("missing"));

            RELEASE.countDown();
            System.out.println("acceptedStatuses=" +
                    first.get(5, TimeUnit.SECONDS).statusCode() + "," +
                    second.get(5, TimeUnit.SECONDS).statusCode());
            await(FINISHED);
            System.out.println("maxInFlight=" + MAX_ACTIVE.get());
            System.out.println("requestSlotsRestored=" +
                    REQUEST_SLOTS.availablePermits());

            BufferQuota memory = new BufferQuota(16);
            boolean firstReserve = memory.tryReserve(12);
            System.out.println("reserve12=" + firstReserve);
            if (firstReserve) {
                byte[] bytes = new byte[12];
                try {
                    System.out.println("reserve8WhileUsed=" +
                            memory.tryReserve(8));
                    bytes[0] = 7;
                } finally {
                    memory.release(bytes.length);
                }
            }
            boolean secondReserve = memory.tryReserve(8);
            System.out.println("reserve8AfterRelease=" + secondReserve);
            if (secondReserve) {
                byte[] bytes = new byte[8];
                try {
                    bytes[0] = 9;
                } finally {
                    memory.release(bytes.length);
                }
            }
            System.out.println("reservedBytesEnd=" + memory.used.get());
        } finally {
            RELEASE.countDown();
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
~~~

Compile and run with **JDK 17+**; `jdk.httpserver` is an official JDK module:

~~~bash
javac --release 17 --add-modules jdk.httpserver ResourceBudgetDemo.java
java --add-modules jdk.httpserver ResourceBudgetDemo
~~~

**Verified stdout when compiled with `--release 17` and run on OpenJDK 24:**

~~~text
overloadStatus=503
retryAfter=1
acceptedStatuses=200,200
maxInFlight=2
requestSlotsRestored=2
reserve12=true
reserve8WhileUsed=false
reserve8AfterRelease=true
reservedBytesEnd=0
~~~

### 13.1. Line-by-line output explanation

| Output | What is verified |
|---|---|
| `overloadStatus=503` | Two requests held slots; the third could not acquire one and was rejected in a controlled way |
| `retryAfter=1` | The overload response includes a header guiding the client to delay retrying |
| `acceptedStatuses=200,200` | The two admitted requests completed successfully after opening the `CountDownLatch` |
| `maxInFlight=2` | The handler recorded at most two active admitted requests |
| `requestSlotsRestored=2` | Both permits were properly released after the handlers finished |
| `reserve12=true` | A 12-byte reservation fits within the 16-byte quota |
| `reserve8WhileUsed=false` | 12 + 8 exceeds the 16-byte quota, so the new request is rejected |
| `reserve8AfterRelease=true` | After releasing 12 bytes, enough budget is available to reserve 8 |
| `reservedBytesEnd=0` | Logical reservations return to 0 when both allocations finish |

### 13.2. Why use CountDownLatch instead of Thread.sleep?

If you just send three requests quickly and measure concurrency, results can vary by scheduler and machine speed: the first request might finish before the third arrives. `CountDownLatch STARTED` guarantees **two handlers have acquired permits and are waiting**; `RELEASE` prevents them from finishing while the third request is evaluated. Thus `503` and max active 2 do not rely on timing guesswork.

The 5-second timeout is only a **test deadline to avoid hanging** in abnormal runtime environments. On very slow hosts the deadline may need adjustment; do not treat this 5-second timeout as a fixed production SLA.

### 13.3. Intentional limitations of the demo

- **Does not prove max TCP connections.** The demo limits **in-flight requests**, not open sockets. Backlog 8 is not an active connection cap.
- `ThreadPoolExecutor` has a bounded queue, but if a task is rejected **before the handler**, the JDK server does not guarantee an HTTP 503; the demo's 503 comes from the **handler-level Semaphore**.
- The demo uses **HTTP/1.1 loopback**, without testing HTTP/2 multiplexing, TLS, Internet sockets, or a load balancer.
- `BufferQuota(16)` simulates logical reservation; it does not measure heap/GC/RSS and does not account for backing storage of objects outside the demo.
- The `200`/`503` output is the status from the local handler. When the server loses the ability to accept due to OS/socket overload, the client may encounter a connection error before receiving a status.
- `workers.shutdownNow()` is only for test cleanup; production needs graceful shutdown/draining of in-flight work rather than abruptly stopping valid requests.

## 14. Client-side Semaphore: avoid creating thousands of futures

On the HTTP client side, place request admission **before `sendAsync`**. For example:

~~~java
// Conceptual snippet; client, request, and requestSlots are already created.
if (!requestSlots.tryAcquire()) {
    // Fail-fast or enqueue into a bounded queue.
    return;
}

try {
    CompletableFuture<HttpResponse<byte[]>> future = client.sendAsync(
            request, HttpResponse.BodyHandlers.ofByteArray());
    future.whenComplete((response, error) -> {
        requestSlots.release();
        // Record metrics; distinguish HTTP 4xx/5xx from transport exceptions.
    });
} catch (RuntimeException setupFailure) {
    requestSlots.release(); // sendAsync did not return a future: must roll back.
    throw setupFailure;
}
~~~

This is **only a snippet**. In a real implementation, ensure ownership and exactly-once release once the callback is registered (avoiding double-release if an exception occurs after setting up the callback), handle cancellation/timeouts, and include downstream business work if the permit is defined to cover until business completion.

In particular, if you use `BodyHandlers.ofInputStream()`, the future can complete **right after headers**. In that scenario, a `whenComplete` callback releases the slot **too early** while the body is not yet fully read. You must tie the permit to the stream's lifecycle, such as an `InputStream` wrapper that releases the permit exactly once on close/EOF, or hold the permit in the worker processing the stream from start to finish.

## 15. Setting memory limits based on a reasonable worst-case

### 15.1. Estimating from size and concurrency

Suppose a service has:

- 100 potentially active requests.
- Each request holds at most 256 KiB of **dedicated application buffer**.
- No additional copies in this back-of-the-envelope calculation.

Peak dedicated buffer budget:

~~~text
100 requests x 256 KiB = 25,600 KiB ≈ 25 MiB
~~~

This is **only an estimate of the counted buffer portion**, not the service's total memory. You must add TLS buffers, kernel socket buffers, request bodies, response bodies, decoder/JSON trees, queue elements, thread stacks, idle buffers, caches, and JVM overhead. If the application parses JSON into an object graph, memory can be many times larger than the raw body.

### 15.2. Multi-layered budget

An illustrative configuration:

| Budget | Example | Why not too large? |
|---|---|---|
| Open connections | 200 | Bounds sockets/file descriptors and idle memory |
| Active requests | 64 | Prevents CPU/downstream overload |
| Waiting requests | 128 | Caps queue memory and queue latency |
| Body per request | 1 MiB | Prevents a single request from causing OOM |
| Total active buffer reservations | 32 MiB | Prevents multiple large bodies from piling up |
| Retained idle buffer pool | 8 MiB | Prevents the pool from holding native memory forever |
| Request deadline | 5 seconds | Frees slots when upstream stalls |
| Idle connection timeout | Per traffic profile | Reclaims unused sockets |

These numbers are **not default recommendations**; you must measure workload, payload distributions, concurrent users, OS limits, and SLOs. A service streaming 1 GiB files may need a large per-body bytes *transferred* limit but a small per-request *in-memory buffer*. Distinguish total body data quotas from quotas on bytes retained in RAM.

## 16. Monitoring: observe all three resource types

### 16.1. Measuring connections

- Open connections **active + idle**.
- Connections accepting/waiting in backlog if supported by the OS.
- TCP connection failures, resets, timeouts, TLS handshake failures.
- File descriptors/handles in use relative to OS limit.
- Connections by origin/host/tenant, HTTP protocol version, keep-alive reuse rate.
- Socket states like `ESTABLISHED`/`TIME_WAIT` when investigating ephemeral port exhaustion.

### 16.2. Measuring requests

- In-flight requests and peak, histogram of permit hold duration.
- Queue length, queue wait duration, rejected tasks.
- 2xx/4xx/5xx separately, especially `429`/`503`.
- RPS, success/error rate, p50/p95/p99 latency, and open downstream calls.
- Timeouts, cancels, retries, retry amplification; distinguish HTTP error statuses from network exceptions.
- Per-tenant/per-route in-flight quota to prevent one group from exhausting all slots.

### 16.3. Measuring memory/buffers

- Java heap used, committed, GC pauses, allocation rate.
- Native/direct buffer count, capacity, and memory used.
- Buffer pool retained bytes vs. borrowed/in-use bytes.
- In-memory request/response body bytes and queue payload bytes.
- Container RSS/working set, OOM-kill metrics; distinguish heap/direct/OS memory.
- Leaked buffers or `ByteBuffer` views still retaining large backing storage.

Java 17 provides `BufferPoolMXBean`:

~~~java
// Snippet; requires importing ManagementFactory and BufferPoolMXBean.
for (BufferPoolMXBean p : ManagementFactory.getPlatformMXBeans(
        BufferPoolMXBean.class)) {
    System.out.println(p.getName() + " count=" + p.getCount()
            + " capacity=" + p.getTotalCapacity()
            + " used=" + p.getMemoryUsed());
}
~~~

Per the Javadoc, these are **estimates** for buffer pools such as `direct` or `mapped`; `getMemoryUsed()` can be `-1` if no estimate is available. **Do not sum these numbers and treat them as all network memory bytes**, because the kernel, JVM internals, and application arrays work differently. Use these metrics together with heap/native metrics and application-owned quotas.

## 17. Protecting the system against slow clients and slow upstreams

A client can open a connection and send bytes extremely slowly (**slow request/Slowloris**), or read the response slowly. An upstream can hang, preventing the request slot from being returned.

Coordinated defenses needed:

- **Connect timeout**: limits the connection establishment phase.
- **Header/body read timeout**: limits periods with no progress.
- **Overall deadline**: limits total duration of a logical operation.
- **Maximum request body size**: limits actual bytes read, including chunked.
- **Minimum throughput/idle policy** where appropriate; prevent one byte every few seconds from holding a connection indefinitely.
- **Cancellation**: close the stream/socket or cancel the subscription per the API.
- **Semaphore slots + queue budget**: prevent slow operations from making all requests wait unboundedly.
- **Per-downstream circuit breaker/bulkhead**: one slow dependency API does not monopolize the entire application.

**Do not confuse read timeout with overall deadline**: a server can trickle small amounts of data before each read timeout, stretching the entire download indefinitely. A separate total deadline is needed when policy requires it.

### 17.1. Acquisition order to avoid deadlock and over-reservation

If each operation needs a connection permit, a request permit, and a byte quota, define **a consistent acquisition order** and roll back when a later layer fails:

~~~text
admit request slot
    |
check/obtain connection capacity
    |
reserve buffer bytes
    |
perform I/O
    |
release memory -> connection lifecycle -> request slot
~~~

This example is purely illustrative: a connection pool can reuse sockets so a connection slot does not necessarily belong to a single request, and releasing a connection must follow the real socket lifecycle. **Do not force every service into this rigid order**; the goal is to avoid holding resource A indefinitely while waiting for B, avoid deadlocks, and guarantee rollback on every failure path.

## 18. Load testing to verify real limits

Just reading configuration is not enough. Test at least these scenarios:

| Test | Expectation |
|---|---|
| Requests below admission cap | Succeeds normally, no rejections |
| Requests at exact cap | Active counter does not exceed limit |
| Requests above cap | Controlled rejection/queuing, no OOM |
| Queue full | New tasks do not create an unbounded queue; overload feedback is observable |
| Slow requests/body | Slots are released on timeout/cancel/EOF per contract |
| Long idle keep-alive | Idle sockets are reclaimed per policy |
| HTTP/2 multiple streams on one connection | Request count is bounded independently of socket count |
| Body larger than per-request quota | Blocked before retaining too much memory |
| Many concurrent buffers | Total reservation does not exceed budget |
| Buffer view/pool retention | Does not undercount actual retained memory or misrelease logical quota |
| Client disconnects mid-response | Server does not leak permits/buffers |
| Failure right after allocating or enqueuing | Proper rollback, no double release |
| 503 burst + client retries | No retry storm, system recovers with backoff |
| Multiple tenants/host routes | No single tenant monopolizes all slots |

Measure **throughput, p99 latency, rejection rate, queue latency, connection count, heap/direct memory, and GC** in the same test run. If increasing the queue sharply raises p99 without increasing throughput, that is a sign **the queue is merely buffering overload**, not solving the bottleneck.

### 18.1. Do not use one benchmark as a fixed config for every workload

Data to gather before setting limits:

1. Average/p95/p99 request duration under real load.
2. Distribution of request/response body sizes.
3. Ratio of streaming vs. buffering.
4. Keep-alive ratio, HTTP/1.1 vs. HTTP/2, number of origins.
5. CPU core quota, memory limit, file descriptors, and ephemeral port limits.
6. Downstream concurrency / database pool / remote service quotas.
7. Latency SLO and target overload error rate.

Start with **conservative budgets, bounded queues, and full metrics**, then increase based on throughput and headroom. Do not look only at low CPU and raise request concurrency: the service might be waiting on the database/network or already out of direct memory.

## 19. Common mistakes

| Misconception / mistake | Consequence | Fix |
|---|---|---|
| Backlog 100 means max 100 active sockets | Server can still open many sockets after accept | Separate pending accept queue and active cap |
| Connection cap = request cap | HTTP/2 multiplexes many streams | Count in-flight requests separately |
| `HttpClient.Builder.executor` is max HTTP connections | Network I/O is not bound 1-to-1 to workers | Use application admission and observability |
| `jdk.httpclient.connectionPoolSize=8` means max 8 active sockets | Property bounds the **HTTP/1.1 idle keep-alive cache** | Do not treat it as a total live socket limit |
| Increasing backlog increases request throughput | Backlog only stores pending connections | Fix worker/downstream bottlenecks |
| `Executors.newFixedThreadPool(8)` is completely bounded | Waiting queue may be unbounded | Use bounded queue + rejection |
| Limiting only queue count, not payload bytes | Queue retains multiple GiB | Byte quota for queued bodies |
| Unbounded `Semaphore.acquire()` in handlers | Waiting threads pile up | Fail fast or timed acquire |
| Forgetting to release on exception | Permit leak, service stops accepting requests | `finally`/terminal callback exactly once |
| Releasing twice in a cancel/success race | Active requests exceed ceiling | Ownership/atomic terminal state |
| Returning HTTP 200 during overload | Clients and monitoring think it succeeded | `429`/`503` per semantics |
| Assuming all executor rejections become 503 | Handler may not have been invoked yet | Admission at HTTP handler or ingress |
| Setting only `-Xmx` gives a total memory cap | Direct/native/kernel memory lives outside heap | Measure RSS/direct/heap separately |
| `ByteBuffer.slice()` creates an independent block | Shares backing memory, causing retention/double-counting | Track the owner of the original allocation |
| Returning to buffer pool means memory is freed | Pool still retains memory for reuse | Separate borrowed vs. retained counters |
| Using `readAllBytes()` for untrusted bodies | OOM/GC pressure | Per-body max + streaming |
| Relying on `Content-Length` as the sole quota | Can be missing/spoofed/chunked/compressed | Count actual bytes read; decompress with limits |
| Releasing client permit when `HttpResponse<InputStream>` arrives | Body is not yet consumed | Hold until EOF/close/onComplete |
| Retrying every 503 immediately | Retry storm | Deadline, exponential backoff + jitter |
| Closing socket and expecting client to always get 503 | TCP reject may produce no HTTP response | Understand pre- vs. post-HTTP-parse rejection layers |
| Relying on `maxstreams` to limit global requests | That is a per-connection HTTP/2 policy | Separate global concurrency admission |

## 20. Production checklist

**Connections:** Are active, idle, and pending backlog distinguished? Open sockets ≤ budget? Are idle timeouts and graceful cleanup in place? Is file descriptor headroom sufficient? Are HTTP/2 streams measured separately? Is the client-side keep-alive cache configured per its actual semantics rather than treated as a connection concurrency cap?

**Requests:** Is there an independent active concurrency cap? Bounded queue? Is there 503/429 logic and a retry/backoff policy? Per-tenant fairness? Deadlines/cancellation? Are permits released exactly once after body processing completes, including on errors? Does worker pool configuration reflect CPU/downstream and avoid unbounded queues?

**Buffers:** Are there per-request body quotas, global memory reservations, and pool retention budgets? Are heap/direct/kernel and logical in-use vs. physically retained distinguished? Are post-decompression sizes, `ByteBuffer` views, and unbounded `readAllBytes` controlled? Are heap, direct `BufferPoolMXBean`, and process RSS metrics collected?

**Verification:** Have you load-tested overload, slow clients, HTTP/2 multiplexing, chunked bodies, retry storms, cancel/timeout, double-release, and queue full? When disconnecting mid-body, do server/client release sockets/permits/buffers? Are metrics labeled appropriately by route/tenant/origin without leaking PII?

## 21. Self-check questions

**1. Does `ServerSocket.bind(address, 64)` limit active connections to 64?** No. 64 is the requested pending connection backlog and also depends on the OS.

**2. Can one HTTP/2 connection carry multiple requests?** Yes, multiple HTTP streams multiplex over the same TCP/TLS connection.

**3. What does JDK 17's `jdk.httpserver.maxConnections` limit?** The number of open connections including active and idle; not a request concurrency cap.

**4. How many active TCP connections does `jdk.httpclient.connectionPoolSize` limit?** It does not define a cap on active connections; it is the limit for the HTTP/1.1 **keep-alive cache** in the JDK implementation.

**5. Does `HttpClient.Builder.executor(pool)` automatically cap max in-flight HTTP requests?** No. That is the executor for asynchronous/dependent tasks per the API.

**6. Does `Executors.newFixedThreadPool(8)` have a bounded waiting queue?** You should not assume the queue is bounded. Use `ThreadPoolExecutor` and `ArrayBlockingQueue` when a finite cap is needed.

**7. What should a server do when it runs out of request permits?** Return 503 with policy/`Retry-After` if the handler can respond; or throttle/reject early at the network layer without waiting indefinitely.

**8. How does 429 differ from 503?** 429 is typically a client quota/rate limit; 503 means the service is temporarily unavailable.

**9. Why must `Semaphore` be released in `finally`?** So that exceptions/timeouts do not permanently leak permits.

**10. Why must you not release twice from timeout and success callbacks?** It can push permits above the ceiling; an exactly-once terminal ownership state is required.

**11. Is `ByteBuffer.allocateDirect` guaranteed to be inside `-Xmx`?** No. Direct memory is typically outside the heap and must be monitored separately.

**12. Can two `ByteBuffer.slice()` instances share storage?** Yes. Do not count them as two independent allocations when calculating physical memory.

**13. Does memory reservation `release` mean GC has reclaimed the bytes?** No. That is a logical budget; GC and pool retention have different lifecycles.

**14. Why is `Content-Length` not enough to prevent oversized bodies?** It can be absent or wrong, and compression changes the processed size; actual bytes must be counted.

**15. When a client uses `ofInputStream()` and the response future completes, should the request permit be released immediately?** Not if the permit protects full body consumption. Wait for EOF/close/error.

**16. Why does the demo guarantee receiving 503 for the third request?** Two `CountDownLatch`es hold two requests that have acquired permits, so the third request cannot obtain a slot.

**17. Does the demo set a max TCP connections cap?** No. It sets max request processing and a logical buffer quota, with a separate backlog.

**18. Why can a large queue worsen latency?** Requests wait longer, retain payloads/objects, and may expire their deadlines before being processed.

**19. Does `BufferPoolMXBean.getMemoryUsed()` measure total RSS?** No. It is only a memory estimate for a single buffer pool and may return `-1`.

**20. What risk does a service with few active requests but many idle sockets still face?** File descriptors and kernel/native memory remain held, exhausting connection capacity.

## 22. Official references

- [Java SE 17 – ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): `bind(backlog)` is the requested pending connection queue, not an active cap.
- [Java SE 17 – HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): `create/bind` backlog, `setExecutor` before `start`, server lifecycle.
- [Java SE 17 – HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): request/response body, headers, and close.
- [Java SE 17 – Java Networking](https://docs.oracle.com/en/java/javase/17/core/java-networking.html): table of **JDK-specific HTTP client/server system properties**, including `jdk.httpserver.maxConnections`, `jdk.httpclient.connectionPoolSize`, `jdk.httpclient.maxstreams`, and memory/buffer-related knobs.
- [Java SE 17 – HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): public builder options, `executor`, `connectTimeout`, protocol version.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client reuse, `sendAsync`, response `BodyHandler`s.
- [Java SE 17 – Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html): concurrency permits, `tryAcquire`, and `release`.
- [Java SE 17 – ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): bounded thread pools, queues, and rejection.
- [Java SE 17 – ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): fixed-capacity queue.
- [Java SE 17 – ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): heap/direct buffers, `slice/duplicate`, backing storage, and native I/O.
- [Java SE 17 – BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): measuring estimates of direct/mapped buffers.
- [Java SE 17 – ManagementFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html): obtaining platform MXBeans.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): `429`, `503`, `Retry-After`, and retry semantics.
- [RFC 9113 – HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): streams, multiplexing, and concurrency settings.

**Conclusion:** Reliability is not achieved with a single “max connections” number. **Backlog** is only the queue waiting for TCP accept; **connection cap** protects sockets/file descriptors; **request cap + bounded queue** protect workers/downstream; **byte reservations + pool budgets** protect heap/direct memory. With Java 17, distinguish JDK-specific cache properties from public APIs, limit requests with explicit admission, hold permits until body processing completes, return controlled overload responses, and measure real resources during load testing.
