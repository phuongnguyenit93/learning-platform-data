# Choosing Socket, Selector, Virtual Threads, or HttpClient by Workload Characteristics

When designing a networking system in Java, the question **“should we use `Socket`, `Selector`, virtual threads, or `HttpClient`?”** actually consists of **two different axes of choice**:

1. **Application protocol:** Are you communicating over a **custom TCP byte stream** or **HTTP request–response**? For HTTP, prefer an HTTP-aware API like `java.net.http.HttpClient`, rather than writing HTTP framing, TLS/proxy/redirect handling on top of `Socket` yourself.
2. **Concurrency model:** Are most tasks **I/O-bound**, do you need to serve **many long-lived connections**, or are they **CPU-bound**? You can use blocking I/O + platform threads, **nonblocking NIO `Selector`**, or **virtual threads** when running Java 21+.

These solutions are **not mutually exclusive**: a virtual thread can call `HttpClient.send()`; an HTTP client can be shared across many tasks; a server using `Selector` can offload CPU-heavy processing to a worker pool. A good decision is based on traffic profile, target latency, connection lifetime, resource quotas, failure observability, and the level of complexity the team can maintain — not just a “requests per second” benchmark number.

**Critical version note:** `java.net.Socket`, `java.nio.channels.Selector`, and `java.net.http.HttpClient` are all available on **Java 17**. **Virtual threads became a finalized feature in Java 21** (JEP 444); do **not** write `Executors.newVirtualThreadPerTaskExecutor()` in a project targeting Java 17. This article uses **three programs compiled with `--release 17`** and **one separate program compiled with `--release 21`** to illustrate how these choices can be combined.

This Knowledge article belongs to the **Reliability** section of **Java Advance - networking**. The focus is on **choosing the right abstraction for the workload while preserving guarantees around data, timeouts, backpressure, fairness, idempotency, and cleanup**.

## 1. Selection Map of the Four Tools

| Tool / Model | Directly Solves | Best Suited For | Must Handle Yourself | Minimum Java |
| --- | --- | --- | --- | --- |
| Blocking `Socket` / `ServerSocket` | TCP streams and accepting connections via blocking calls | Custom TCP protocols, moderate connection counts, easy-to-read sequential logic | Framing, read/write loops, deadlines, thread pool, auth/TLS, queues | Java 17 (available much earlier) |
| `SocketChannel` + `Selector` | Multiplexing **many nonblocking channels** via an event loop | Many idle/slow connections, high fan-in, need to control state/byte buffers | Selector keys, partial I/O, framing, OP_WRITE toggling, fairness, cross-thread coordination | Java 17 |
| **Virtual threads** | Cheaper to create tasks waiting on blocking I/O; one-thread-per-task model | Java 21+, many independent blocking operations, need readable linear code | Outbound/DB quotas, deadlines, structured lifecycle, thread-local/driver caveats | **Java 21** finalized |
| `HttpClient` | HTTP/1.1/HTTP/2 request/response, TLS/redirect/proxy via API | Calling REST APIs, microservices, HTTP endpoints, and HTTP streaming | Body lifecycle, application limits, HTTP status, retries/idempotency, deadlines | Java 11+, used in Java 17 |

**Do not compare “Socket vs HttpClient” as two ways of doing the exact same thing.** `Socket` is a TCP primitive; `HttpClient` is an **HTTP protocol client**. When a client needs to call `https://api.example/...`, `HttpClient` handles many things that raw TCP does not do for you. When you build a **custom binary TCP server**, `HttpClient` is not the right API for accepting sockets.

## 2. How to Read the Workload Before Choosing an Abstraction

Collect **measurable** data:

- **C** — maximum concurrent connections; how many are idle vs. how many are active?
- **R** — requests/messages per second; how much fan-out per request to downstream services?
- **S** — average message size, p95/p99, maximum payload, streaming rate.
- **W** — time each task spends **waiting on I/O** (DB, HTTP, file, socket), compared to **P** — actual CPU time.
- **L** — p95/p99 latency requirements, deadlines, burst backlog, number of slow consumers.
- **V** — acceptable deployment Java version (17 LTS or 21+).
- **M** — memory budget, file descriptors, OS thread limit, connection pools.
- **D** — data semantics: message framing, idempotency, durability, replay after disconnect.
- **Security** — TLS/mTLS, authn/authz, proxy, tenant isolation, input limits.

For example: **20,000 TCP connections where only 2% have incoming bytes** is a different problem from **200 concurrent requests all calling the DB and waiting 300 ms**, and different again from **100 tasks continuously compressing data and saturating the CPU**.

Do not choose a selector just because you have many connections if the team lacks the capacity to manage state and errors; do not choose virtual threads just because “it is new technology” if CPU is the bottleneck.

## 3. Two-Axis Decision Diagram

```text
What protocol is the application using?
  |
  +-- HTTP(S) request/response?
  |      |
  |      +-- NEED TO CALL a server -> java.net.http.HttpClient
  |      |       |
  |      |       +-- Few operations -> send() or sendAsync() fits
  |      |       +-- Many independent calls -> sendAsync + bounded in-flight
  |      |       +-- Java 21+ blocking style -> virtual thread calling send()
  |      |
  |      +-- NEED TO SERVE HTTP -> HttpServer/HTTP server framework
  |              (HttpClient is NOT an HTTP server)
  |
  +-- Custom binary/text TCP protocol?
         |
         +-- Few/moderate connections, simple -> Socket + bounded workers
         +-- Many idle/long-lived connections -> Selector + nonblocking
         +-- Java 21+, many I/O-waiting tasks -> virtual threads + Socket
         +-- Heavy CPU tasks -> CPU-sized pool, separated from I/O path
```

The branches also depend on **TLS, throughput, data framing, resource quotas, and reliability**. There is no JDK-guaranteed magic number like “above 1,000 connections you must use Selector”. Threshold numbers are only meaningful when measured on your actual workload/hardware/OS/JDK.

## 4. `Socket`: An Understandable Choice When the Custom TCP Protocol Is Compact

`Socket` is a **blocking** TCP byte stream. Operations such as `InputStream.read` and `OutputStream.write` can block waiting for data or waiting on the peer/network; Java does not create **message boundaries** out of TCP. One server `write` is not guaranteed to correspond to one client `read`.

```text
TCP sender:  [4-byte length][UTF-8 bytes] [4-byte length][UTF-8 bytes]
                          |
                TCP byte stream
                          |
TCP reader:  readInt -> readFully(length) -> decode frame
```

When using blocking sockets, one implementation approach is that each accepted socket is **assigned to a worker**, and handler code reads/writes sequentially. That is a natural model for a small protocol with relatively predictable latency, provided the number of workers/connections is bounded.

**Main risk:** if one socket holds a worker in `read` for a long time, other connections may have to wait; a platform thread has a stack and OS resources, and cannot scale indefinitely with idle connections. Avoid an unbounded thread pool or default factories with an **unbounded queue** if the server must withstand traffic bursts.

## 5. Four Common Pitfalls When Implementing Blocking TCP

1. **Framing:** For protocols with messages, use a length prefix, delimiter, or stateful stream parser. Do not decode each TCP chunk as an independent JSON message.
2. **Timeouts:** Set `Socket.setSoTimeout(...)` for blocking reads; connection establishment has a separate timeout via `socket.connect(address, timeout)`. A read timeout does **not** automatically bound total business processing time.
3. **Bounds:** Limit frame bytes before allocation, number of connections, number of workers, executor queue size, total pending outbound bytes, and idle time.
4. **Cleanup:** Use try-with-resources; handle EOF (`read() == -1`), half-close, remote reset, and `IOException`. A TCP close does not mean the server has rolled back side effects of an already-received message.

Do not treat `DataInputStream.readFully` as proof that a connection will always read enough bytes: it waits for the exact number of bytes **or throws `EOFException`** if the peer closes early. This is the proper behavior to catch and surface as an **incomplete frame**.

## 6. Java 17+ Example A — TCP Socket with Four-Byte Framing and UTF-8

The standalone program **`BlockingSocketWorkloadDemo.java`** opens a `ServerSocket` on `127.0.0.1` with an ephemeral port. A worker accepts one connection and echoes **two messages**. Framing is a **4-byte signed integer** indicating the UTF-8 payload length, in big-endian order via `DataOutputStream.writeInt` and `DataInputStream.readInt`. The server only accepts `0 <= length <= 1024`; `readFully` ensures all frame bytes are read before decoding.

```java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BlockingSocketWorkloadDemo {
    private static void writeFrame(DataOutputStream out, String value)
            throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
        out.flush();
    }

    private static String readFrame(DataInputStream in) throws IOException {
        int length = in.readInt();
        if (length < 0 || length > 1024) {
            throw new IOException("Invalid frame length");
        }
        byte[] bytes = new byte[length];
        in.readFully(bytes);
        return new String(bytes, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        try (ServerSocket server = new ServerSocket(0, 10, local)) {
            server.setSoTimeout(5000);
            ExecutorService pool = Executors.newFixedThreadPool(2);
            AtomicInteger handled = new AtomicInteger();
            try {
                Future<?> accept = pool.submit(() -> {
                    try (Socket peer = server.accept()) {
                        peer.setSoTimeout(5000);
                        DataInputStream in = new DataInputStream(
                                peer.getInputStream());
                        DataOutputStream out = new DataOutputStream(
                                peer.getOutputStream());
                        for (int i = 0; i < 2; i++) {
                            String payload = readFrame(in);
                            writeFrame(out, payload);
                            handled.incrementAndGet();
                        }
                    } catch (IOException error) {
                        throw new UncheckedIOException(error);
                    }
                });

                try (Socket client =
                        new Socket(local, server.getLocalPort())) {
                    client.setSoTimeout(5000);
                    DataInputStream in = new DataInputStream(
                            client.getInputStream());
                    DataOutputStream out = new DataOutputStream(
                            client.getOutputStream());
                    writeFrame(out, "alpha");
                    System.out.println("First echo: " + readFrame(in));
                    writeFrame(out, "Xin chào");
                    System.out.println("Second echo: " + readFrame(in));
                }
                accept.get(6, TimeUnit.SECONDS);
                System.out.println("Frames handled: " + handled.get());
            } finally {
                pool.shutdownNow();
            }
        }
    }
}
```

Compile and run on JDK 17+:

```sh
javac --release 17 -encoding UTF-8 BlockingSocketWorkloadDemo.java
java BlockingSocketWorkloadDemo
```

Verified stdout:

```text
First echo: alpha
Second echo: Xin chào
Frames handled: 2
```

**What this example demonstrates:**

- The two `writeFrame` calls are **two application-defined messages**, not two TCP packets. `readFrame` uses the length prefix to determine message boundaries.
- `String.getBytes(UTF_8)` then `length` measures bytes; do not use `String.length()` to define length in the protocol.
- `DataInputStream.readFully` may complete across multiple network reads, or throw an exception if the body is short.
- `Socket.setSoTimeout(5000)` bounds the blocking time of each read call, not the total time of the entire operation under 5 seconds.
- `newFixedThreadPool(2)` only illustrates worker scheduling; **its default queue is unbounded**, so it is not production admission control.
- `ServerSocket` and `Socket` are closed; the worker pool is shut down in `finally`.
- The demo only handles **one accepted connection** and two messages; it does not prove a real server can hold hundreds of thousands of clients by spawning one thread per connection.

**When to choose:** if the server needs to communicate over a simple custom protocol with tens or hundreds of connections within verified quotas, blocking sockets can be easier to maintain than a stateful event loop. Actual thresholds must be load-tested.

## 7. `Selector`: Multiplexing Nonblocking I/O Without a Waiting Thread per Socket

Java NIO provides `ServerSocketChannel`, `SocketChannel`, `Selector`, and `SelectionKey`. When channels are switched to **nonblocking mode**, an event loop can register interest sets and handle readiness for many connections inside `selector.select()`.

| Operation bit | Meaning when interest is set |
| --- | --- |
| `OP_ACCEPT` | `ServerSocketChannel` has an accept-ready event |
| `OP_CONNECT` | `SocketChannel` can complete a nonblocking connection |
| `OP_READ` | Channel has data, EOF, or a condition needing read-side handling |
| `OP_WRITE` | Channel can write data into the transport output buffer (or a related error condition) |

**Readiness is not completion.** When `key.isReadable()`, `read(buffer)` may only read **a partial amount**; when `key.isWritable()`, `write(buffer)` may write **0 bytes or a partial amount**. `ByteBuffer.position()` must be preserved across subsequent iterations to avoid losing or duplicating bytes.

Selector excels when most connections are idle: the event loop does not need a blocked platform thread per socket. The cost is that you **own the state machines**, connection lifetimes, buffer queues, fairness, framing, error/cancel handling, cross-thread commands, and memory control.

## 8. Do Not Register `OP_WRITE` Permanently

For a TCP socket with space in the kernel send buffer, **write-ready is frequent**. If you keep `OP_WRITE` in the interest set all the time, `selector.select()` can wake up continuously **even when there is no data to send**, creating a high-CPU loop.

Rule:

```text
When accepted:
   register OP_READ (no OP_WRITE while outbound queue is empty)

When application enqueues outbound data:
   enable OP_WRITE; selector.wakeup() if from another thread

When isWritable:
   write pending ByteBuffers, preserving position if partial/zero
   if queue is now empty:
      clear OP_WRITE immediately
   if queue still has data:
      keep OP_WRITE for the next readiness event

On error/EOF:
   cancel SelectionKey, close channel, clean up per-connection state
```

Add `OP_WRITE` **only when there are bytes waiting**; do not write/spin until a huge buffer drains in a single callback. In real systems, enforce a **per-turn write budget** so one connection does not monopolize the event loop; when a peer reads slowly, bound **pending bytes per connection** and apply a backpressure/reject/close policy.

`OP_READ` does not always need to stay enabled either; if the application's inbound queue is congested, you can selectively remove read interest to avoid exhausting memory, but you must design resume logic and avoid deadlocks.

## 9. Java 17+ Example B — A Selector Echo with Proper `OP_WRITE` Toggling

The file **`SelectorWorkloadDemo.java`** uses one event-loop thread to manage a `ServerSocketChannel` and a nonblocking `SocketChannel`. The client sends a line `selector\n`. The server keeps a `ByteBuffer` bounded at 128 bytes, waits for a newline, then **switches interest from `OP_READ` to `OP_WRITE`**, echoes the data (which could be partial-written), **clears `OP_WRITE` after the buffer drains**, and closes the connection.

```java
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class SelectorWorkloadDemo {
    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        try (ServerSocketChannel server = ServerSocketChannel.open();
             Selector selector = Selector.open()) {
            server.bind(new InetSocketAddress(local, 0));
            server.configureBlocking(false);
            server.register(selector, SelectionKey.OP_ACCEPT);
            AtomicBoolean completed = new AtomicBoolean();
            AtomicBoolean writeInterestCleared = new AtomicBoolean();
            AtomicReference<Throwable> problem = new AtomicReference<>();

            Thread eventLoop = new Thread(() -> {
                try {
                    long deadline = System.nanoTime()
                            + 8_000_000_000L;
                    while (!completed.get()
                            && System.nanoTime() < deadline) {
                        selector.select(500);
                        Iterator<SelectionKey> it =
                                selector.selectedKeys().iterator();
                        while (it.hasNext()) {
                            SelectionKey key = it.next();
                            it.remove();
                            if (!key.isValid()) continue;

                            if (key.isAcceptable()) {
                                SocketChannel peer = server.accept();
                                if (peer != null) {
                                    peer.configureBlocking(false);
                                    peer.register(selector,
                                            SelectionKey.OP_READ,
                                            ByteBuffer.allocate(128));
                                }
                            } else if (key.isReadable()) {
                                SocketChannel peer =
                                        (SocketChannel) key.channel();
                                ByteBuffer buffer =
                                        (ByteBuffer) key.attachment();
                                int count = peer.read(buffer);
                                if (count == -1) {
                                    throw new IllegalStateException(
                                            "EOF before line");
                                }
                                boolean lineComplete = false;
                                for (int p = 0;
                                     p < buffer.position(); p++) {
                                    if (buffer.get(p) == '\n') {
                                        lineComplete = true;
                                        break;
                                    }
                                }
                                if (lineComplete) {
                                    buffer.flip();
                                    key.interestOps(SelectionKey.OP_WRITE);
                                } else if (!buffer.hasRemaining()) {
                                    throw new IllegalStateException(
                                            "Line too long");
                                }
                            } else if (key.isWritable()) {
                                SocketChannel peer =
                                        (SocketChannel) key.channel();
                                ByteBuffer pending =
                                        (ByteBuffer) key.attachment();
                                peer.write(pending);
                                if (!pending.hasRemaining()) {
                                    key.interestOps(0);
                                    writeInterestCleared.set(true);
                                    key.cancel();
                                    peer.close();
                                    completed.set(true);
                                }
                            }
                        }
                    }
                    if (!completed.get()) {
                        throw new IllegalStateException(
                                "Selector deadline exceeded");
                    }
                } catch (Throwable error) {
                    problem.set(error);
                }
            }, "selector-loop");
            eventLoop.start();

            try (Socket client =
                    new Socket(local, server.socket().getLocalPort())) {
                client.setSoTimeout(5000);
                OutputStream out = client.getOutputStream();
                out.write("selector\n".getBytes(StandardCharsets.UTF_8));
                out.flush();
                InputStream in = client.getInputStream();
                ByteArrayOutputStream reply = new ByteArrayOutputStream();
                int next;
                while ((next = in.read()) != -1) {
                    reply.write(next);
                    if (next == '\n') break;
                    if (reply.size() > 128) {
                        throw new IllegalStateException("Response too large");
                    }
                }
                System.out.println("Echo: " + reply.toString(
                        StandardCharsets.UTF_8).trim());
            } finally {
                eventLoop.join(9000);
                if (eventLoop.isAlive()) {
                    selector.wakeup();
                    throw new IllegalStateException("Event loop not stopped");
                }
            }

            if (problem.get() != null) {
                throw new IllegalStateException(problem.get());
            }
            System.out.println("OP_WRITE removed after send: "
                    + writeInterestCleared.get());
            System.out.println("Selector loop completed: "
                    + completed.get());
        }
    }
}
```

Run on JDK 17+:

```sh
javac --release 17 -encoding UTF-8 SelectorWorkloadDemo.java
java SelectorWorkloadDemo
```

Verified stdout:

```text
Echo: selector
OP_WRITE removed after send: true
Selector loop completed: true
```

Explanation:

1. `selector.select(500)` only operates on registered channels; `selectedKeys().iterator().remove()` avoids reprocessing a stale selected key.
2. The server registers `OP_ACCEPT`, and the accepted peer registers `OP_READ` with a `ByteBuffer` attachment; **it does not register `OP_WRITE` upon accept**.
3. `read(buffer)` may read a partial chunk; the code preserves `buffer.position()` until a newline is seen.
4. When a newline is seen, `buffer.flip()` and `interestOps(OP_WRITE)` are called. From that point, the buffer becomes the **outbound pending bytes** for **one demo message**.
5. `peer.write(pending)` may be partial/zero. While `pending.hasRemaining()` is still true, the code **does not rewind** and keeps `OP_WRITE` interest.
6. Once fully written, the code calls `interestOps(0)` and closes the peer; it prints `OP_WRITE removed after send: true`. The connection closes immediately because the demo only echoes **one** line. In a long-lived server, you would typically switch back to `OP_READ` instead of closing.
7. The event loop has a deadline and records errors into an `AtomicReference` for the main thread to inspect; the demo requires no Internet access.
8. The code is minimal in scope: **one connection, one line, maximum 128 bytes**, with no multi-client fairness, TLS, outbound queue, or production lifecycle.

**Do not copy this NIO snippet as a production server**: it accurately illustrates interest transitions, but it is not a complete implementation for long message framing, half-close, high load, quotas, and worker handoff.

## 10. Selector Does Not Mean “Every Task Will Run Faster”

An event loop can handle I/O for many sockets, but if you invoke a **CPU-heavy operation or blocking JDBC/HTTP call** directly inside `isReadable()`, **all connections** on that loop may have to wait. `Selector` does **not** make business code nonblocking.

Typical design:

```text
Selector event loop
   |
   +-- Readiness/read bytes/parse bounded frame
   +-- Enqueue bounded work item -> worker pool (CPU/DB)
   +-- Receive worker completion via mailbox
   +-- selector.wakeup()
   +-- Enable OP_WRITE only while outbound pending
   +-- Write with per-loop byte/time budget
```

If another worker needs to modify `SelectionKey.interestOps` or an attachment queue, there must be clear **ownership/happens-before** semantics. A safe choice is for the event loop thread to own channel/key/buffer state; workers **send commands** via a thread-safe mailbox, then call `selector.wakeup()` so the loop processes the command. Avoid having workers concurrently mutate the same `ByteBuffer` as the event loop.

The event loop needs metrics for selected keys, bytes read/written, pending queues, long callbacks, wakeups, time spent in processing, CPU idle/spin, and slow peer counts. A selector can handle very many connections, but **it does not eliminate file descriptor limits or kernel buffers**.

## 11. Virtual Threads: Finalized in Java 21, Not Available in Java 17

**JEP 444** standardized **virtual threads in Java 21**. `Thread.ofVirtual()` and `Executors.newVirtualThreadPerTaskExecutor()` let you express blocking tasks using **one virtual thread per task**, instead of requiring a dedicated platform thread while waiting on I/O.

For supported blocking operations, the JDK can **unmount** a virtual thread from its carrier platform thread while it waits on I/O, allowing the carrier to serve another virtual thread. This is a scaling benefit for **I/O-bound concurrency**, **not** a way to make each request or CPU operation run faster.

Key facts:

- **Java 17:** no finalized virtual threads APIs. `Thread.ofVirtual()` does not compile with `javac --release 17`.
- **Java 19/20:** virtual threads were in preview; preview features should not be treated as stable APIs for Java 17.
- **Java 21+:** virtual threads are finalized; you can use `Executors.newVirtualThreadPerTaskExecutor()` and `Thread.currentThread().isVirtual()`.
- **Do not pool virtual threads** just to save thread count. They are designed for one task per virtual thread; bound other resources using `Semaphore`, connection pools, queue quotas, or API rate limits.
- **Do not use virtual threads to “add CPU cores”**. CPU-intensive tasks need a bounded CPU pool or better algorithms.
- Test blocking operations, native calls, monitoring, and pinning-related behavior on the **exact target JDK version**; Java 21 has caveats around `synchronized`/native blocks, and behavior can change in newer JDKs. Do not extrapolate all versions from a single JEP.

Sources: [JEP 444](https://openjdk.org/jeps/444), [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html).

## 12. How Do Virtual Threads Differ from a Platform Thread Pool?

Platform threads model:

```text
1000 connections/tasks waiting on I/O
    |
    +-- 1000 platform threads: high OS thread/stack cost
    or
    +-- 50 fixed workers: at most 50 tasks running/waiting,
                          the rest sit in the executor queue
```

Virtual threads model:

```text
1000 independent tasks
    |
    +-- virtual thread per task (Java 21+)
             |
             +-- waiting on supported I/O -> carrier can do other work
             |
             +-- CPU work -> still uses real CPU
             |
             +-- downstream DB pool of 20 -> at most 20 DB connections
```

**Nothing is free:** a million virtual threads still have **heap objects/stacks**, application state, sockets, queued requests, and downstream limits. If each task holds a `byte[10_000_000]`, lightweight threads **will not save you from OOM**. If 100,000 virtual threads simultaneously send requests to a database that only accepts 100 connections, throughput will be capped by the DB and can trigger a timeout storm.

`Semaphore`, body-byte quotas, max pending operations, rate limiters, and deadlines must reflect **real resources**. This also holds true if code calls `HttpClient.send` inside virtual threads.

## 13. Java 21+ Example C — Virtual Threads Using Blocking HTTP with Outbound Concurrency Limits

The program **`VirtualThreadHttpWorkloadDemo.java`** **requires Java 21 or later** and does not run on Java 17. It creates 9 virtual thread tasks. Each task calls **blocking `HttpClient.send`** to a loopback HTTP server, while **`Semaphore(3)` allows at most 3 active HTTP calls concurrently**. The server intentionally waits for the first three requests to arrive together using a `CountDownLatch` before returning responses, deterministically verifying this concurrency limit.

```java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetAddress;
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
import java.util.concurrent.atomic.AtomicInteger;

public class VirtualThreadHttpWorkloadDemo {
    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService httpWorkers = Executors.newFixedThreadPool(4);
        AtomicInteger served = new AtomicInteger();
        CountDownLatch firstThree = new CountDownLatch(3);
        CountDownLatch release = new CountDownLatch(1);
        byte[] ok = "OK".getBytes(StandardCharsets.UTF_8);
        server.createContext("/work", exchange -> {
            try {
                int count = served.incrementAndGet();
                if (count <= 3) {
                    firstThree.countDown();
                    try {
                        release.await(5, TimeUnit.SECONDS);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    }
                }
                exchange.sendResponseHeaders(200, ok.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(ok);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(httpWorkers);
        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(URI.create(
                    "http://127.0.0.1:"
                            + server.getAddress().getPort() + "/work"))
                    .timeout(Duration.ofSeconds(10)).GET().build();
            Semaphore maxInFlight = new Semaphore(3);
            AtomicInteger active = new AtomicInteger();
            AtomicInteger peak = new AtomicInteger();
            List<Future<Boolean>> futures = new ArrayList<>();
            try (ExecutorService virtual =
                         Executors.newVirtualThreadPerTaskExecutor()) {
                for (int i = 0; i < 9; i++) {
                    futures.add(virtual.submit(() -> {
                        boolean isVirtual =
                                Thread.currentThread().isVirtual();
                        maxInFlight.acquire();
                        int now = active.incrementAndGet();
                        peak.accumulateAndGet(now, Math::max);
                        try {
                            HttpResponse<String> result = client.send(
                                    request,
                                    HttpResponse.BodyHandlers.ofString());
                            return isVirtual && result.statusCode() == 200
                                    && "OK".equals(result.body());
                        } finally {
                            active.decrementAndGet();
                            maxInFlight.release();
                        }
                    }));
                }
                if (!firstThree.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Server did not receive three requests");
                }
                release.countDown();
                boolean good = true;
                for (Future<Boolean> future : futures) {
                    good &= future.get(10, TimeUnit.SECONDS);
                }
                System.out.println("Virtual tasks completed: "
                        + futures.size());
                System.out.println("All virtual and HTTP 200: " + good);
                System.out.println("Peak in-flight HTTP: " + peak.get());
                System.out.println("Server handled: " + served.get());
            } finally {
                release.countDown();
            }
        } finally {
            release.countDown();
            server.stop(0);
            httpWorkers.shutdownNow();
        }
    }
}
```

Compile and run with JDK 21+:

```sh
javac --release 21 --add-modules jdk.httpserver -encoding UTF-8 VirtualThreadHttpWorkloadDemo.java
java --add-modules jdk.httpserver VirtualThreadHttpWorkloadDemo
```

Verified stdout:

```text
Virtual tasks completed: 9
All virtual and HTTP 200: true
Peak in-flight HTTP: 3
Server handled: 9
```

**Practical takeaways:**

- `Executors.newVirtualThreadPerTaskExecutor()` creates **a virtual thread per task**; `isVirtual()` confirms each task's thread context.
- `client.send` is still blocking at the **source-code level**, but the runtime can execute many I/O-bound tasks concurrently thanks to virtual threads.
- `Semaphore(3)` sets an **outbound call quota**, not a “virtual thread pool”. `peak==3` proves both the limit and concurrent activity in the demo.
- `HttpClient` is a **shared** instance for making HTTP calls, rather than creating a new HTTP client per task.
- The server uses `HttpServer`, which is a test-fixture HTTP server; **client virtual threads do not mean the server automatically runs on virtual threads**. Both sides configure concurrency independently.
- `close()` on the executor in try-with-resources waits for the virtual thread tasks to finish per the Java 21 contract.
- The demo only performs 9 GETs with an `OK` payload; it does **not** prove a configuration can handle millions of users or provides exactly-once semantics.

If your project targets Java 17, **do not copy this example** into a `--release 17` module. You can use `sendAsync` on Java 17 as in the next example, or upgrade the runtime to 21+ according to your compatibility/QA plan.

## 14. `HttpClient`: When the Protocol Is HTTP, Use an HTTP Abstraction

`java.net.http.HttpClient` in Java 17 manages many parts of HTTP request–response:

- `HttpRequest` with URI, HTTP method, headers, body publisher, and timeout.
- `HttpResponse<T>` with status/headers/body via `BodyHandler`.
- Synchronous `send(...)`, and `sendAsync(...)` returning `CompletableFuture<HttpResponse<T>>`.
- `HTTP_1_1` and `HTTP_2` are supported HTTP versions subject to configuration/peer negotiation.
- TLS `https://`, proxies, redirects, and authentication via the API; the application must still configure the right policies.
- A client instance can **be shared to reuse connection resources** instead of creating a new one per request; specific connection reuse is not an invariant across every server/request.
- Streaming requests/responses via `BodyPublisher` and `BodyHandlers.ofInputStream/ofLines/ofPublisher` when payloads are large or need incremental processing.

**`HttpClient` is a client**, not an API to `accept()` incoming connections. If you want to **serve HTTP** on Java 17, there is `jdk.httpserver.HttpServer` for minimal embedded needs, or a framework/server with the required security, routing, HTTP protocol handling, and production features.

Do not hand-roll HTTP GET over `Socket` by concatenating header strings; TLS, redirects, proxies, chunked responses, status codes, header validation, keep-alive, and HTTP/2 are all protocol details that are hard to get right yourself.

## 15. `send` or `sendAsync` When Calling Multiple HTTP Services?

| Approach | Code Style | Best For | Caveats |
| --- | --- | --- | --- |
| `HttpClient.send` on platform thread (Java 17) | Sequential blocking | Few calls, simple service logic, sufficient worker budget | Blocking threads are held while waiting on the network |
| `HttpClient.sendAsync` (Java 17+) | Future-based async | Fanning out many HTTP requests, pipelines, limiting concurrent work | Callback chaining, cancellation propagation, exception handling, and backpressure |
| `HttpClient.send` in virtual thread (Java 21+) | Sequential blocking style, lightweight thread on I/O | Many independent requests, linear code, bounded downstream | Does not turn HTTP 500 into success; does not eliminate timeouts/quotas |
| HTTP over raw `Socket` | Implementing framing/TLS/HTTP protocol yourself | Only when writing a library/server/proxy with a very specific reason | High correctness/security cost, usually not recommended |

On Java 17, `sendAsync` allows many requests to be in-flight simultaneously without blocking a dedicated caller platform thread per request. However, **thousands of `sendAsync` futures** does not mean downstream can withstand thousands of concurrent HTTP requests. You still need in-flight limits, connection/body budgets, and retry rate limits.

`HttpClient.Version.HTTP_2` is a client **preference**, not a guarantee that every endpoint will use HTTP/2; check `response.version()` or negotiation behavior if the protocol version matters.

## 16. Java 17+ Example D — Shared `HttpClient` + Batched `sendAsync`

The standalone program **`HttpClientWorkloadDemo.java`** creates a `jdk.httpserver` loopback HTTP server returning `item-N` based on the URI path. A shared `HttpClient` sends **6 GET requests**, split into **two batches, with at most 3 requests submitted concurrently in a batch**. The code waits for all futures in each batch before sending the next batch.

```java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class HttpClientWorkloadDemo {
    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(4);
        AtomicInteger requests = new AtomicInteger();
        server.createContext("/item/", exchange -> {
            try {
                requests.incrementAndGet();
                String id = exchange.getRequestURI().getPath()
                        .substring("/item/".length());
                byte[] bytes = ("item-" + id).getBytes(
                        StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=UTF-8");
                exchange.sendResponseHeaders(200, bytes.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(bytes);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(workers);
        server.start();

        try {
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            List<HttpResponse<String>> replies = new ArrayList<>();
            final int batchSize = 3;
            for (int start = 0; start < 6; start += batchSize) {
                List<CompletableFuture<HttpResponse<String>>> batch =
                        new ArrayList<>();
                for (int i = start; i < start + batchSize; i++) {
                    HttpRequest req = HttpRequest.newBuilder(
                            URI.create(base + "/item/" + i))
                            .timeout(Duration.ofSeconds(5))
                            .GET().build();
                    batch.add(client.sendAsync(req,
                            HttpResponse.BodyHandlers.ofString()));
                }
                for (CompletableFuture<HttpResponse<String>> f : batch) {
                    replies.add(f.join());
                }
            }
            boolean statuses = true;
            boolean orderedBodies = true;
            for (int i = 0; i < replies.size(); i++) {
                statuses &= replies.get(i).statusCode() == 200;
                orderedBodies &= ("item-" + i)
                        .equals(replies.get(i).body());
            }
            System.out.println("HTTP replies: " + replies.size());
            System.out.println("Batch cap: " + batchSize);
            System.out.println("All status 200: " + statuses);
            System.out.println("Bodies follow request order: "
                    + orderedBodies);
            System.out.println("Server handled: " + requests.get());
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
```

Run on Java 17+:

```sh
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 HttpClientWorkloadDemo.java
java --add-modules jdk.httpserver HttpClientWorkloadDemo
```

Verified stdout:

```text
HTTP replies: 6
Batch cap: 3
All status 200: true
Bodies follow request order: true
Server handled: 6
```

Explanation:

1. `HttpClient.newBuilder()` reuses **the same client instance** across all requests; bodies are handled by `BodyHandlers.ofString()` because payloads are small.
2. `sendAsync` returns a future; the code stores them in **submission order**. Even if request 2's response arrives before request 1's, collecting the futures in order still produces the list in the defined business order.
3. Each `HttpRequest` sets `timeout(Duration.ofSeconds(5))` and the client has a separate `connectTimeout`.
4. `batchSize=3` is a **simple bounded fan-out** mechanism, not a sophisticated limiter for continuous workloads. In production, you can use a semaphore, bounded scheduler, or rate limiter to maintain throughput when one request is slow without stalling the entire batch.
5. `All status 200` is **explicitly checked**; `sendAsync` completes normally for a 500 response if a valid HTTP response is received, so never ignore the status code.
6. `Bodies follow request order` checks test correctness, **not** that network completions occurred in order.
7. The server is a lightweight `HttpServer` for loopback self-testing. It **does not demonstrate HTTPS, HTTP/2, retries, or production security**.

If payloads are large or unbounded, **do not use `ofString()` to buffer the entire response in memory**; choose an appropriate streaming body handler, and consume/close it properly to release resources.

## 17. Trade-Off Matrix: Complexity, Memory, Latency, and Workload

| Factor | Blocking Socket + Platform Threads | Selector / NIO | Virtual Threads + Blocking API | HttpClient (`sendAsync` or `send`) |
| --- | --- | --- | --- | --- |
| Protocol | Custom TCP bytes | Custom TCP bytes | TCP/HTTP/... via blocking API | HTTP |
| I/O code complexity | Usually low | Higher, event state machine | Usually low (linear code) | Low for HTTP; async composition requires understanding futures |
| Very many idle connections | Thread budget can become a bottleneck | Usually a strength | Java 21+, can be a good fit if OS sockets/heap suffice | HTTP keep-alive/HTTP2 depends on peer; not applicable to arbitrary TCP servers |
| Mostly I/O-bound tasks | Holds platform workers | Event loop multiplexes readiness | Carrier can be reused | Supported via futures or virtual-thread callers |
| CPU-heavy tasks | Bounded CPU workers | **Must offload off the event loop** | Does not create new CPU cores | Body parsing also needs CPU quota |
| Framing/messages | Self-designed | Self-designed + partial buffer state | Self-designed if using raw Socket | HTTP framing implemented by client |
| TLS | `SSLSocket`/JSSE or TLS layer | `SSLEngine`/framework, more complex | Depends on blocking API used | `https://` supports JSSE via client API |
| Stop/timeout point | Socket/blocking lifecycle | Cancel key/close channel | Interrupt/cancel task + close resources | Future cancel/request timeout/body cleanup |
| Resource limits | Threads, sockets, queues | Keys, buffers, loop CPU, queues | Heap, sockets, downstream quotas, permits | In-flight, connections, response buffers, retries |
| Java 17 | Yes | Yes | **Not finalized** | Yes |

This is an **evaluation matrix**, not a benchmark ranking table. Advantages depend on OS, connection patterns, JDK, message size, TLS, and actual workload.

## 18. When to Choose Each Approach — Four Concrete Scenarios

### Scenario A: An internal TCP service, 40 clients, small messages

If each connection sends a few short messages/s and workers, memory, and file descriptors stay within quotas: **`Socket` + bounded executor** can be the lowest-complexity-risk choice. Set deadlines, frame bounds, TLS, and connection caps, and test slow clients. There is no need to hand-write a selector event loop just to save a few dozen platform threads if there is no performance problem.

### Scenario B: Tens of thousands of TCP connections, mostly idle

`Selector` can reduce platform-thread-per-connection costs and give control over `OP_READ`/`OP_WRITE`. However, each connection still holds an FD, kernel buffers, ByteBuffers, and application state. You need event-loop sharding, per-connection quotas, fairness, worker offload, backpressure, half-close/reconnect state, and load testing. If running Java 21+ and the team prefers blocking style, **virtual threads should also be benchmarked as a candidate**, rather than assuming selector always wins.

### Scenario C: A microservice calling 5 downstream HTTP APIs per operation

Choose `HttpClient` because **the protocol is HTTP**. On Java 17 use `sendAsync` + bounded fan-out/`CompletableFuture` composition; on Java 21+ you can use virtual threads calling `send` for cleaner readability. Use an overall per-request deadline, body limits, idempotent retries, tracing, and a circuit breaker. Do not open a raw `Socket` just to send GET/POST.

### Scenario D: 500 tasks all compressing video on the CPU

There is no reason to expect virtual threads or a selector to make the CPU run 10x faster. Choose a **bounded CPU worker pool** sized to cores/pipeline specs and measurements; avoid blocking the selector loop. If a task also waits on disk/network, separate I/O and CPU stages and apply queue capacity limits; when CPU compression is the bottleneck, focus on algorithms, the I/O pipeline, or hardware.

## 19. Reliability Does Not Come Automatically from Concurrency Primitives

**TCP** provides an ordered byte stream and transport checksums, but it **does not** know whether “the order committed” or “the message was processed once”. **`Selector`** only reports readiness. **Virtual threads** only change how blocking tasks are scheduled. **`HttpClient`** implements the HTTP protocol but does not guarantee business idempotency on its own.

For example:

```text
Client -> sends POST to create order
Server -> reads bytes -> DB COMMIT
Network fails / client times out before receiving response
Client -> UNKNOWN outcome
Client retries POST without key -> may create a second order
```

To achieve business-level reliability:

- **Operation ID / idempotency key** generated before the first request and resent with the same key.
- **Server-side deduplication** that is durable/atomic with the transaction or state machine.
- **Properly scoped ACK**: distinguish between bytes accepted by the kernel, HTTP 202 response, server processed, DB committed, and user-visible result.
- **Status/reconciliation API** when a response is lost but the server may have processed it.
- **Retry semantics** tailored to GET/PUT/POST and the actual API contract, with bounded attempts and backoff + jitter.
- **Timeouts/deadlines** at the connection, network I/O, business request, and end-to-end operation layers.

Do not treat `socket.close()`, `SelectionKey.cancel()`, `future.cancel(true)`, or `Thread.interrupt()` as proof that a remote side effect has been rolled back.

## 20. Backpressure Is the Deciding Factor for Survival Under Overload

Regardless of which tool you choose, if producers outpace consumers, **outbound/inbound queues** can grow unboundedly. You must separate and bound the limits:

| Resource | Quotas to Consider |
| --- | --- |
| TCP accepted connections | Max open sockets/FDs, idle limit, pending accept backlog |
| Blocking worker tasks | Active workers + **bounded queue**, rejection policy |
| Selector buffers | Max pending outbound bytes/connection, per-event write budget |
| Virtual thread work | Max in-flight business operations, downstream semaphore, heap budget |
| HttpClient fan-out | Max in-flight requests, per-host quotas, timeouts, retry budget |
| Request body | Max bytes, max decoded size, parser depth/line length |
| Slow consumers | Pause producer, enforce per-tenant limits, drop/close per protocol |
| Downstream DB | Pool size, query timeout, queue limits, circuit breaker |

**Pool size is not the same as queue size.** `Executors.newFixedThreadPool(n)` has an **unbounded queue** by contract. Production systems need a `ThreadPoolExecutor` with a bounded queue or an appropriate admission pattern, paired with an explicit `RejectedExecutionHandler`.

**Virtual threads do not need pooling**, but that does **not** mean you can spawn an unlimited number of concurrent requests. Semaphores/connection pools must still keep work at safe levels.

**Selector has no memory magic**: thousands of keys each holding a 10 MiB queue still consumes gigabytes. Pick a max queued bytes limit and measure saturation.

## 21. Capacity Planning: Quotas Instead of a Single “Max Connections” Number

An initial estimation approach (for budgeting, **not** a substitute for benchmarking):

```text
Memory used by connection state approx:
  concurrent connections
  × (user-space buffers + per-connection objects)
  + JVM/GC/stack/heap overhead
  + kernel socket buffers (not entirely inside JVM heap)

HTTP in-flight concurrency approx:
  request arrival rate × average response time
(this is the Little's Law intuition for a relatively stable system)

CPU capacity:
  number of CPU-bound tasks actually running in parallel
  bounded by cores and scheduling overhead

Downstream maximum:
  min(local in-flight quotas, remote capacity, connection-pool limits)
```

**Hypothetical** example: 500 RPS with an average round-trip time of 200 ms gives an average in-flight concurrency of approximately `500 × 0.2 = 100` operations in steady state. However, p99 latency and bursts can push peaks significantly higher; you must plan for distributions and overload scenarios, not just averages.

If one socket holds 64 KiB of user-space buffers, 20,000 sockets correspond to roughly **1.22 GiB** of user-space buffers before overhead (20,000 × 65,536 bytes ≈ 1.22 GiB). **Virtual threads do not eliminate those buffers**, and neither does a selector. Bounded buffers/pooling are only safe when ownership and memory caps are explicit.

The numbers above are hypothetical calculations to illustrate capacity planning, **not Java default configurations**.

## 22. Timeouts and Cancellation by Model

| Model | Common Mechanisms | Limitations / Warnings |
| --- | --- | --- |
| Blocking `Socket` | `connect(timeout)`, `setSoTimeout`, close socket, interrupt task | `setSoTimeout` bounds a single blocking read, not the entire business SLA |
| `Selector` | `select(timeout)`, deadline state, cancel key, close channel, `wakeup()` | `select(timeout)` is a readiness wait timeout, not a per-request deadline; must track manually |
| Virtual threads | `interrupt()`/`Future.cancel`, deadlines, close owned resources | Cooperative cancellation, does not abort remote side effects; stable API only in Java 21+ |
| `HttpClient` | `connectTimeout`, `HttpRequest.timeout`, `sendAsync` cancellation, close body | 5xx status/timeout does not mean the server did not commit; streaming body has its own lifecycle |

An **end-to-end deadline** should cover queue wait, DNS/connect/TLS, upload, server processing, response consumption, and retry attempts. A socket that still “reads one byte every 10 seconds” can evade a short read timeout while stalling the whole operation — you need a total deadline/idle-rate policy.

When a receiver uses `BodyHandlers.ofInputStream()`, `HttpResponse` can arrive after headers **before the body finishes**; you must consume or close the body stream. With `ofPublisher()`, you must subscribe/request until a terminal event or cancel properly.

## 23. TLS and Security: Do Not Pick a Primitive and Ignore the Protocol

- `Socket`/`SocketChannel` only provide TCP; HTTPS/TLS requires JSSE `SSLSocket`, `SSLContext`, or `SSLEngine` (a complex NIO TLS state machine). Never transmit tokens or user data in plaintext over untrusted networks.
- `HttpClient` handles HTTPS over JSSE per configuration; that does **not** automatically give you business authorization or token refresh.
- Virtual threads do not encrypt traffic on their own. They can run blocking TLS/HTTP APIs according to those APIs' semantics.
- `Selector` does not come with an HTTP parser, WebSocket frames, HTTP/2 streams, or application-layer message integrity.
- Every server needs max body/header limits, per-resource authn/authz, rate limits, URL/path validation, log redaction, and slowloris protection.
- In multi-tenant systems, avoid sharing mutable credential state and session data across the wrong scope. A resource-sharing `HttpClient` must **not** become a place where bearer tokens/cookies of incompatible security principals mix.

Do not “fix” TLS handshake failures with a `trustAll` manager or by disabling hostname verification. If using a reverse proxy to terminate TLS, enforce a trusted forwarded-headers policy and protect traffic between the gateway and backend.

## 24. HTTP Status, Retries, and Idempotency in Practice

`sendAsync` completes normally when a valid HTTP response is received, including status **404/429/500**, unless a specific protocol/handler/transport error occurs. Always check `statusCode()`.

- **GET/HEAD** are typically safe and idempotent per HTTP semantics and can be retried with bounds if the actual API conforms.
- **PUT/DELETE** have idempotent HTTP semantics, yet still require conditional versions/ETags and awareness that status codes across attempts may differ.
- **POST** creating a payment/order is not idempotent by default. If the response is lost after commit, a blind retry can create duplicate effects.
- **Timeout/interrupt/cancel** does not mean “the server did not process it”; the state may be **UNKNOWN_OUTCOME**.
- **`Retry-After`**, exponential backoff, jitter, and a retry budget help prevent retry storms when downstream is overloaded.

For custom TCP protocols, you must **define** equivalent semantics yourself: request IDs, ACK levels, duplicate detection, status queries, and replay from a durable log if the business requires it. TCP byte delivery does not provide these contracts.

## 25. Observing Performance Properly Instead of Looking Only at Total CPU

A useful set of metrics:

| Group | What to Measure | Helps Decide |
| --- | --- | --- |
| Traffic | Open connections, active/idle, RPS, bytes in/out, avg/p95/p99 body | Idle fan-in vs. request-heavy |
| Platform workers | Thread count, active workers, queue length, rejections, blocked time | Is the socket thread model saturating? |
| Selector | select wakeups, selected-key count, OP_WRITE-ready when idle, loop lag, per-key queue bytes | Is the event loop spinning or starving? |
| Virtual threads | Virtual task concurrency, blocked vs. CPU, pinned operations per JDK, heap usage | Are we leveraging blocking I/O scalability or hitting downstream bottlenecks? |
| HttpClient | In-flight requests, response versions, status mix, connect/TLS errors, body lifetimes | Are HTTP concurrency/reuse/cancellation policies right? |
| Downstream | DB pool waits, RPC latency, 429/503, queue depth, retries | Is the bottleneck at the remote server? |
| Reliability | Timeout/cancelled vs. committed, duplicate IDs, partial frames, reconciliation | Are client errors causing bad business state? |

Measure **p95/p99 latency and throughput alongside error rate**, not just CPU%. Multiple bottlenecks can coexist: low CPU with long queues due to a lock/DB pool, high selector loop CPU due to misregistered `OP_WRITE`, or increased virtual threads hitting remote API 429 limits.

Every benchmark needs the same payloads, same hardware/JDK/GC, warmup, concurrent connections, keep-alive/TLS settings, network faults, and request mix to be fair.

## 26. Common Technology-Selection Mistakes

1. **“HttpClient is an HTTP server.”** False: `HttpClient` calls HTTP endpoints; an HTTP server needs `HttpServer` or a framework.
2. **“With 10,000 sockets, Java forces you to use Selector.”** No: Java 21 virtual threads are a benchmarkable candidate; constraints decide.
3. **“Virtual threads are in Java 17 LTS.”** False: finalized in Java 21, does not compile with `--release 17`.
4. **“Virtual threads automatically add CPU cores.”** False: they mainly help I/O-bound concurrency, not heavy CPU computation.
5. **“You must pool virtual threads to limit concurrency.”** Don't: use semaphores/quotas on real resources.
6. **“Selector handles many keys so no memory cap is needed.”** Each connection still has buffers, queues, and FD/kernel overhead.
7. **“OP_WRITE should always stay enabled to be ready to send.”** Easily causes a CPU busy loop when outbound is empty.
8. **“One TCP `read()` returns one business message.”** TCP is a byte stream; framing is required.
9. **“Socket `write()` succeeding means the server committed.”** It is not a business ACK.
10. **“Selector `read`/`write` always completes all bytes.”** Nonblocking I/O can be partial or zero.
11. **“Put blocking DB queries into the selector event loop for convenience.”** Can lag every connection; offload with bounds.
12. **“A new HttpClient per request is always faster.”** Usually loses resource reuse and increases overhead.
13. **“HttpClient `sendAsync` means sending 100,000 requests is safe.”** You need max in-flight, response caps, and rate limits.
14. **“HTTP 500 automatically throws `IOException`.”** Not by default: HTTP response status must be checked by the application.
15. **“With virtual threads we can open unlimited DB connections.”** No: DB pool/remote capacity still bounds it.
16. **“A thread pool of 8 workers has a max queue of 8.”** No: `newFixedThreadPool` uses an unbounded queue.
17. **“`setSoTimeout` is the total deadline for the request.”** It only controls a blocking read, not the whole operation.
18. **“Socket/selector cancel rolls back the remote job.”** There is no such guarantee.
19. **“HttpClient supports HTTP/2 so every server will run HTTP/2.”** It must be negotiated; version is a preference.
20. **“Using Java 21+ eliminates backpressure.”** No: quotas, bounded queues, and deadlines are still needed.
21. **“One-thread-per-connection is always worse than NIO.”** No absolute rule; it depends on workload and JVM version.
22. **“Closing the HTTP response stream does not matter.”** Streaming bodies must be consumed/closed to avoid holding resources.
23. **“Replacing existing code with NIO guarantees better reliability.”** State-machine complexity can introduce harder-to-spot bugs.
24. **“Using nonblocking means nothing blocks anywhere else.”** Parsers, file I/O, DB calls, and locks can still block.
25. **“Measuring peak RPS alone is enough.”** Reliability, p99, error rate, security, memory, and maintainability matter just as much.

## 27. Self-Check Knowledge Questions

**Q1.** A Java 17 app needs to call 40 REST endpoints in parallel; should it use raw `Socket` or virtual threads? **Neither.** Use `HttpClient.sendAsync` with bounded in-flight concurrency; finalized virtual threads are not available on Java 17.

**Q2.** Java 21+, 5,000 tasks mostly waiting on HTTP/DB, and you want sequential-style readable code: which option is worth trying? **Virtual threads**, using appropriate blocking APIs and semaphore/DB quotas.

**Q3.** A server has 50,000 idle TCP connections. What does `Selector` solve? **Multiplexing readiness of many nonblocking channels**, reducing the need for platform-thread-per-connection; it does not eliminate socket/heap budgets.

**Q4.** Should `SelectionKey.OP_WRITE` always stay in the interest set? **No** if outbound is empty; it can stay ready and cause a CPU spin.

**Q5.** A TCP `read` returns 6 bytes from a 20-byte frame. Is that a corrupted packet? **No.** TCP is a stream; the parser must read the full frame based on length or delimiter.

**Q6.** Is `newVirtualThreadPerTaskExecutor()` a thread pool with 1,000 carrier threads? **No**; it creates a virtual thread per task; carriers and scheduling are managed by the runtime.

**Q7.** If `sendAsync` returns a 500 response, must the future complete exceptionally? **No**; an HTTP error status can still be a normal response completion, so you must check `statusCode()`.

**Q8.** Does “a virtual thread can call `HttpClient.send()`” prove the two choices are mutually exclusive? **No**; they belong to two different abstraction levels.

**Q9.** Why shouldn't a selector event loop parse a 1 GiB ZIP file inside a callback? **CPU/blocking work will stall all other sockets**; use bounded worker offloading.

**Q10.** Does `Socket.close()` after a POST prove the server did not commit? **No**; you need operation IDs and status reconciliation.

**Q11.** If throughput is limited because the DB pool only has 20 connections, will increasing virtual threads from 200 to 20,000 make the database faster? **No**; you must address the actual bottleneck/quota.

**Q12.** A load test has 100,000 idle connections, each using just 64 KiB of user buffers. Roughly how much memory do the buffers alone take? **About 6.1 GiB**, not counting connection state, OS/kernel, and other layers (100,000 × 65,536 bytes ≈ 6.1 GiB).

## 28. Pre-Production Solution Selection Checklist

- [ ] Identify the **protocol** first: raw TCP / HTTP(S) / streaming? Incoming server or outgoing client?
- [ ] Measure the workload: concurrent open vs. active sockets, I/O wait vs. CPU, RPS/messages, payload distribution, and peak bursts.
- [ ] Lock down the JDK runtime: **Java 17** or **Java 21+**. Do not use stable virtual-thread APIs in a Java 17 build.
- [ ] For custom TCP, clearly define **framing, byte order, charset, max frame, EOF, heartbeat, and reconnect**.
- [ ] If using `Socket`, ensure **bounded workers/connections**, connect/read deadlines, cleanup, and saturation metrics.
- [ ] If using `Selector`, ensure **per-channel state**, partial reads/writes, `OP_WRITE` toggling, wakeup/mailbox, and bounded queues.
- [ ] If using virtual threads, **do not pool them**; limit operations via semaphores/downstream quotas, and test pinning/drivers on the target JDK.
- [ ] If using HTTP, prefer **`HttpClient`**, share the client appropriately, and pick `send/sendAsync` per concurrency model.
- [ ] Set timeouts/deadlines for the **whole operation**, not just socket read/connect; verify cancellation propagation.
- [ ] Bound **bytes in memory**, HTTP body size, in-flight requests, retry budgets, and queue depth.
- [ ] Implement **TLS/mTLS, authn/authz**, secrets isolation, input validation, and trusted-proxy policies.
- [ ] Separate **transport acknowledgement** from **business acknowledgement**; use operation IDs/idempotency for side effects.
- [ ] Run realistic load tests: p50/p95/p99, throughput, error rate, peak memory, GC, FDs, worker/selector lag.
- [ ] Test faults: slow readers, half-close, timeouts, unreachable peers, HTTP 429/500, disconnect after commit.
- [ ] Document the **decision rationale**: why one model won, unresolved risks, owners, and migration path.

**Conclusion:** Choose `Socket` when handling a **simple custom TCP protocol with connection counts within quotas**, choose `Selector` when you need **nonblocking multiplexing for many idle/slow sockets and accept complex state management**, choose **virtual threads on Java 21+** to keep **readable blocking code for many I/O-bound tasks**, and choose **`HttpClient` when the protocol is HTTP**. They can be combined, but **no tool replaces designing framing, backpressure, deadlines, security, and idempotency**. Reliability comes from **application contracts + resource limits + measured testing**, not from an API name.

### Official References

- [Java SE 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [Java SE 17 — ServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html)
- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html)
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [JEP 444 — Virtual Threads finalized in JDK 21](https://openjdk.org/jeps/444)
- [Oracle Java 21 — Virtual Threads and best practices](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Java SE 21 — Executors.newVirtualThreadPerTaskExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [RFC 9110 — HTTP semantics and idempotence](https://www.rfc-editor.org/rfc/rfc9110.html).
