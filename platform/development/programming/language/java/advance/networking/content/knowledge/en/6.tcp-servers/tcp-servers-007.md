# Bounding Active Connections and Separating CPU Work from I/O Waiting

## Lesson Objectives

A TCP server typically has to perform three inherently different tasks: **accepting connections**, **waiting to read/write network data**, and **processing data with the CPU**. If every connection spawns a new thread or CPU tasks share a pool with threads blocked on `read()`, resources can be exhausted even while the CPU is idle.

After this lesson, you will be able to:

- Distinguish **the backlog waiting for `accept()`** from **the number of connections already admitted by the application for service**.
- Limit the number of active connections using `Semaphore`, understanding who acquires/releases permits and why a permit must be released **exactly once**.
- Separate the **acceptor**, the **I/O worker** pool, and the **CPU worker** pool; bound threads, queues, and handle full pools.
- Use timeouts, request size limits, and backpressure policies to prevent slow clients or long CPU tasks from holding resources indefinitely.
- Run a Java 17+ example with a TCP server and client using two independent executors; understand the limitation of `Future.get()` on an I/O thread.
- Choose when blocking I/O is sufficient and when a nonblocking model with `Selector`/`SocketChannel` is needed.

## 1. Why Shouldn't Everything Run in One Shared Thread Pool?

Suppose a server uses four threads to serve four connections:

~~~text
I/O thread 1  → Socket A: waiting on read()
I/O thread 2  → Socket B: waiting on read()
I/O thread 3  → Socket C: waiting on read()
I/O thread 4  → Socket D: waiting on read()

CPU task already has all its data → still sitting in the queue
~~~

All four threads are **waiting on I/O**, so a new CPU task—even though its data is already available—still has no worker. This is a form of **thread starvation**. If you use `newCachedThreadPool()` to avoid waiting, the pool can spawn too many threads as the number of clients grows, putting pressure on memory, context switching, and the scheduler.

A clearer architecture:

~~~text
TCP clients
    │
    ▼
ServerSocket.accept()     ← acceptor thread, no long business logic
    │
    ▼
Semaphore admission       ← only serve if a slot is available
    │
    ├── full → close the new socket (per overload policy)
    │
    ▼
I/O executor              ← read header/payload, wait on network, write response
    │
    └── data ready → CPU executor ← compute without calling socket.read()
                            │
                            └── result → I/O handler → write and close socket
                                                    → release permit
~~~

Separating responsibilities helps control the two types of resources independently:
- **I/O-bound**: most time is spent waiting for bytes from the client; the main risks are too many sockets, waiting threads, and prolonged timeouts.
- **CPU-bound**: heavy parsing, encryption, compression, computation; the main risks are CPU saturation, contention, and long wait queues.

Moving CPU work to a separate pool **does not automatically make I/O nonblocking**. In the blocking example below, the I/O handler still waits for the CPU result using `Future.get()`. The immediate benefit is that CPU tasks do not run directly inside I/O workers and limits are explicit. For tens of thousands of long-lived connections, consider NIO or async I/O.

## 2. Three Connection Concepts Not to Confuse

| Term | Meaning | Who Controls It? |
|---|---|---|
| **Listen backlog** | Capacity/hint related to connections waiting to be `accept()`ed | OS and listening socket; the `backlog` parameter is a hint |
| **Accepted socket** | `ServerSocket.accept()` has returned a `Socket` object | Application acceptor |
| **Admitted active connection** | The application has allowed the socket to be served and is holding resources for it | `Semaphore` and lifecycle handler |

For example, `new ServerSocket(0, 32, InetAddress.getLoopbackAddress())` has `backlog=32`, which does **not** mean it allows up to 32 active connections being served. If the application limit is four permits, at most four sessions are processed concurrently; a fifth socket may still be returned by `accept()` but will be closed immediately if it cannot acquire a permit.

**Port 0** asks the operating system to choose a free ephemeral port. **Loopback** keeps the exercise on the local machine. This is not a public configuration for all interfaces.

No single number is enough to protect a server: you must control the number of connections, I/O threads, CPU tasks, queue sizes, request/response bytes, and session lifetime.

## 3. Limiting Active Connections with `Semaphore`

`Semaphore` manages a number of permits. With `new Semaphore(4)`, at most four `tryAcquire()` calls succeed before any permit is returned:

~~~java
Semaphore active = new Semaphore(4);
Socket socket = listener.accept();

if (!active.tryAcquire()) {
    socket.close();       // Does not own a permit.
} else {
    // Hand the socket off to a handler.
    // After the socket truly finishes: active.release().
}
~~~

This is an **illustrative snippet**, placed in a class that imports `java.util.concurrent.Semaphore` and `java.net.Socket`/`ServerSocket`, not a standalone program.

Important rules:

1. `tryAcquire()` returns `false`: do **not** call `release()`. Returning a permit that was never acquired will cause the limit to be exceeded.
2. `tryAcquire()` succeeds: hold the permit from the moment the application admits the connection for service until the socket finishes. Do not release it just because the CPU task has been submitted.
3. Whether the handler finishes successfully, times out, hits EOF, encounters a client reset, or fails processing: **it must always release the permit**. Put `release()` in a `finally` block.
4. If a permit was acquired but **the I/O executor rejects the task**, the acceptor must close the socket and release the permit immediately.
5. Each permit has **one owner responsible for releasing it**. Never let both the acceptor and the handler release the permit for an accepted task.

Ownership flow:

~~~text
accept → tryAcquire()
             │
      ┌──────┴────────┐
      │ false         │ true
      ▼               ▼
   close            io.execute(task)
   no release         │
                     ┌─┴──────────────────┐
                     │ accepted           │ rejected
                     ▼                    ▼
               handler finally:     acceptor close
                 release()          + release()
~~~

`Semaphore.acquire()` can block the acceptor until a permit becomes available; that changes the overload strategy and the ability to `accept()` new sockets. With a **fail-fast when busy** policy, `tryAcquire()` after `accept()` is easier to model. An application that wants to wait for a bounded time can use `tryAcquire(timeout, unit)`, but must design clear wait limits.

## 4. Bounding Executors and Queues

A semaphore only limits active connections being served. It does **not** automatically bound the CPU queue, threads, or in-flight requests. This lesson chooses an experimental budget:

| Component | Illustrative Value | Purpose |
|---|---|---|
| `MAX_ACTIVE` | 4 | At most four connections served concurrently |
| I/O executor | 4 workers, `SynchronousQueue` | Avoid queuing sockets for a long time waiting for an I/O worker |
| CPU executor | 2 workers, `ArrayBlockingQueue<>(1)` | At most two CPU tasks running and one waiting |
| `MAX_BODY` | 1024 bytes | Reject headers declaring an oversized payload |
| Socket read timeout | 5 seconds | Do not wait indefinitely on a single read operation |
| CPU future timeout | 2 seconds | Limit how long the I/O handler waits for the CPU result |

These are parameters **for learning**, not general production sizing. Choose production values by measuring throughput, tail latency, CPU, file descriptors, memory, and connection lifetime.

You should understand the commonly used factories:

- `Executors.newCachedThreadPool()` does not set a fixed thread limit suitable for TCP overload.
- `Executors.newFixedThreadPool(n)` only bounds the number of workers, while its default task queue has unbounded capacity. If tasks are submitted faster than they are processed, queue length can grow, causing latency and memory consumption.
- `ThreadPoolExecutor` combines pool size, a bounded queue, and a `RejectedExecutionHandler` to make the resource budget explicit.
- With `ThreadPoolExecutor.AbortPolicy`, tasks are rejected with `RejectedExecutionException` when the executor can no longer accept them.

**Do not casually use `CallerRunsPolicy` for the CPU pool:** a rejected task will run immediately on the thread calling `submit`, which may be the I/O handler. Heavy CPU work then falls back to blocking the I/O thread. If `CallerRunsPolicy` is applied to the I/O executor from the acceptor, the acceptor can run the handler directly and get stuck on the socket.

## 5. Java 17+ Server with Bounded Connections and Two Separate Pools

The example protocol uses **one request per TCP connection**. Requests and responses have the format:

~~~text
[4-byte length, big-endian][length bytes of UTF-8 payload]
~~~

The sender uses `DataOutputStream.writeInt(length)`, and the receiver uses `DataInputStream.readInt()`. `length` is the **number of UTF-8 bytes**, not `String.length()`. After reading the full request, the server submits an uppercase text conversion to the CPU executor, sends the response, and closes the connection.

Save the file **`BoundedTcpServer.java`**:

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.concurrent.*;

public class BoundedTcpServer {
    private static final int MAX_ACTIVE = 4;
    private static final int MAX_BODY = 1024;

    static void closeQuietly(Socket socket) {
        try {
            socket.close();
        } catch (IOException ignored) {
        }
    }

    static void handle(Socket socket, ExecutorService cpu) {
        try (socket) {
            socket.setSoTimeout(5_000);

            DataInputStream in = new DataInputStream(
                new BufferedInputStream(socket.getInputStream()));
            int length = in.readInt();
            if (length < 0 || length > MAX_BODY) {
                throw new IOException("Invalid payload length");
            }

            byte[] request = in.readNBytes(length);
            if (request.length != length) {
                throw new EOFException("Truncated request");
            }

            Future<byte[]> job;
            try {
                job = cpu.submit(() -> {
                    String text = new String(
                        request, StandardCharsets.UTF_8);
                    return text.toUpperCase(Locale.ROOT)
                        .getBytes(StandardCharsets.UTF_8);
                });
            } catch (RejectedExecutionException e) {
                throw new IOException("CPU executor overloaded", e);
            }

            byte[] response;
            try {
                response = job.get(2, TimeUnit.SECONDS);
            } catch (TimeoutException e) {
                job.cancel(true);
                throw new IOException("CPU work timed out", e);
            } catch (InterruptedException e) {
                job.cancel(true);
                Thread.currentThread().interrupt();
                throw new IOException("I/O handler interrupted", e);
            } catch (ExecutionException e) {
                throw new IOException("CPU work failed", e.getCause());
            }

            if (response.length > MAX_BODY) {
                throw new IOException("Response too large");
            }

            DataOutputStream out = new DataOutputStream(
                new BufferedOutputStream(socket.getOutputStream()));
            out.writeInt(response.length);
            out.write(response);
            out.flush();
        } catch (IOException e) {
            System.err.println(
                "Client request failed: " + e.getMessage());
        }
    }

    public static void main(String[] args) throws Exception {
        Semaphore active = new Semaphore(MAX_ACTIVE);

        ThreadPoolExecutor io = new ThreadPoolExecutor(
            MAX_ACTIVE, MAX_ACTIVE, 0, TimeUnit.SECONDS,
            new SynchronousQueue<>(),
            new ThreadPoolExecutor.AbortPolicy());

        ThreadPoolExecutor cpu = new ThreadPoolExecutor(
            2, 2, 0, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(1),
            new ThreadPoolExecutor.AbortPolicy());

        try (ServerSocket listener = new ServerSocket(
                0, 32, InetAddress.getLoopbackAddress())) {
            System.out.println("Port: " + listener.getLocalPort());

            while (!Thread.currentThread().isInterrupted()) {
                Socket socket = listener.accept();

                if (!active.tryAcquire()) {
                    closeQuietly(socket);
                    continue;
                }

                try {
                    io.execute(() -> {
                        try {
                            handle(socket, cpu);
                        } finally {
                            active.release();
                        }
                    });
                } catch (RejectedExecutionException e) {
                    closeQuietly(socket);
                    active.release();
                }
            }
        } finally {
            io.shutdownNow();
            cpu.shutdownNow();
        }
    }
}
~~~

### Responsibility and Error Handling Explained

**Acceptor:** `accept()` obtains the socket, and `tryAcquire()` checks admission. It does not read the request or run CPU processing. If the server already has four permits in use, the next socket is closed; no HTTP status is emitted because the demo uses a custom TCP protocol.

**I/O pool:** four threads, with `SynchronousQueue` holding no application task backlog. Only accepted handlers run `handle`; if `io.execute` rejects the task, the acceptor closes the socket and releases the permit. If the handler is accepted, the handler's `finally` block releases the permit, even on error.

**I/O handler:** `try (socket)` ensures the socket is closed; `setSoTimeout(5_000)` bounds blocking read operations. `readInt` reads the four-byte header; `readNBytes(length)` can return a shorter array at EOF, so comparing lengths is mandatory. Negative lengths or lengths over 1024 are rejected before allocating a large payload.

**CPU pool:** two workers perform `toUpperCase(Locale.ROOT)`. This is just a small computation to illustrate the path; real CPU work could be heavy parsing, data normalization, or algorithms. CPU workers do not call `read()` or `write()` on the socket.

**Future result:** the I/O handler waits with `job.get(2, TimeUnit.SECONDS)`; if CPU work is too slow, it cancels with `cancel(true)` and closes the socket. `cancel(true)` only issues an interruption request and **does not guarantee** stopping a task if it does not check/respect interruption. If `submit` throws `RejectedExecutionException`, the handler reports the error per policy and closes the socket.

**Writing the response:** the uppercase result is converted back to UTF-8 bytes, `response.length` is measured, the header and payload are written via `DataOutputStream`, and `flush()` is called. A Unicode string after uppercasing can change its byte count; do not reuse the request's length.

**Demo boundaries:** the program runs until stopped, uses blocking streams, and only handles **one request per connection**. In a real system, you must add graceful shutdown (stop accepting, track/close active sockets, wait for/cancel tasks with a deadline). `shutdownNow()` does not guarantee automatically closing sockets that are inside blocked handlers.

## 6. Client for Local Testing

Save as **`TcpProbe.java`**:

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;

public class TcpProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: java TcpProbe <port>");
        }

        int port = Integer.parseInt(args[0]);
        try (Socket socket = new Socket(
                InetAddress.getLoopbackAddress(), port)) {
            socket.setSoTimeout(5_000);

            byte[] data = "hello".getBytes(StandardCharsets.UTF_8);
            DataOutputStream out = new DataOutputStream(
                socket.getOutputStream());
            out.writeInt(data.length);
            out.write(data);
            out.flush();

            DataInputStream in = new DataInputStream(
                socket.getInputStream());
            int length = in.readInt();
            if (length < 0 || length > 1024) {
                throw new IOException("Invalid response size");
            }
            byte[] reply = in.readNBytes(length);
            if (reply.length != length) {
                throw new EOFException("Incomplete response");
            }
            System.out.println(
                new String(reply, StandardCharsets.UTF_8));
        }
    }
}
~~~

Terminal A:

~~~bash
javac -encoding UTF-8 BoundedTcpServer.java TcpProbe.java
java BoundedTcpServer
~~~

The server prints, **for example**, `Port: 53123`; the actual port changes because port `0` is used. In terminal B, use the exact port number the server just printed:

~~~bash
java TcpProbe 53123
~~~

When the server is running and accepting connections, the **client stdout** is:

~~~text
HELLO
~~~

This is the verified result with a loopback socket: the request `hello` goes over TCP, a CPU worker converts it to `HELLO`, and the I/O handler sends it back. If the server has stopped or all slots are full, it may produce EOF/IOException and will **not** print this line.

### Testing the Connection Limit

Open **4 TCP clients** that keep their sockets open without sending all four header bytes. The I/O handlers will wait on read, holding their permits. When a fifth client connects:

- `accept()` may return the fifth socket, but `active.tryAcquire()` returns `false`.
- The server closes that socket and does **not** call `release()` for it.
- When one of the four handlers hits EOF/timeout or completes, `finally` releases one permit.
- A subsequent client can then be served again.

The timing of accept, EOF, and timeout depends on scheduling; do not write tests that assert a specific log order or absolute time interval. In unit/load tests, use `CountDownLatch`/`CyclicBarrier` to hold workers in a known state to test pool saturation instead of relying on flaky `Thread.sleep`.

## 7. CPU and I/O Are Separate, Yet a Waiting Point Remains

In the demo, CPU tasks run in a separate pool, but the line:

~~~java
byte[] response = job.get(2, TimeUnit.SECONDS);
~~~

still **blocks the I/O handler** until the CPU task completes or times out. I/O threads can be held by slow clients or those waiting for CPU, so at most four requests are still being handled concurrently. This is an **intentional simplification** to illustrate how to separate CPU execution and resource management.

When the number of connections is large, long-lived, or there are many requests on the same socket, consider:
- **Java NIO**: use `SocketChannel.configureBlocking(false)`, `Selector`, and one or a few I/O event-loop threads monitoring channels ready for read/write. Submit CPU tasks to a bounded CPU pool, push results to an outbound queue; the event loop is signaled via `selector.wakeup()` and writes when the channel is writable. Do not run heavy CPU work directly on the event loop.
- **`AsynchronousSocketChannel`**: coordinates callbacks/futures for I/O; you still have to manage buffers, response ordering, in-flight request counts, and queue memory.
- **Virtual threads**: a stable option starting in **Java 21**, not a standard Java 17 feature. They make blocking code easier to scale, but you still need to bound connections, CPU, and downstream resources.

For persistent-connection protocols, do not release the connection permit after each CPU task if the socket remains open. If multiple CPU tasks run in parallel, responses can finish out of request order: you need a protocol convention, a single writer, or an outbound queue to ensure writes do not interleave bytes or reorder responses unintentionally.

## 8. Backpressure: Reacting When Each Budget Is Full

| Overload Point | Symptom | How to Handle |
|---|---|---|
| Out of connection permits | `tryAcquire() == false` | Close the new socket or send a busy response per the designed protocol |
| I/O pool full | `io.execute` throws `RejectedExecutionException` | Close the socket and release the acquired permit |
| CPU pool + queue full | `cpu.submit` throws `RejectedExecutionException` | Reject processing and release resources; do not run CPU directly on the acceptor |
| Slow-sending client | `SocketTimeoutException` or overall deadline | Stop waiting and release resources |
| Oversized/invalid header | `length < 0` or `length > MAX_BODY` | Reject before allocating payload |
| Slow-receiving client | `write` can block | Bound outbound buffer, send deadline, or close connection |
| Shutdown | Executor does not accept new tasks | Stop accepting, drain/cancel with deadline, close active sockets |

**The CPU queue in the example has capacity 1:** if both CPU workers are busy and one task is already waiting, a new CPU task can be rejected under `AbortPolicy`. This makes overload **visible**, rather than silently queuing thousands of tasks. With a very fast `toUpperCase` task, it is hard to reproduce a rejection in a normal run; controlled tests should hold workers busy with a latch to verify.

**Do not retry immediately in a stampede:** if clients continuously open new connections after being rejected, synchronized retries can worsen overload. Applications can use backoff + jitter and protocol-level busy signals when appropriate.

**Do not limit only request length:** connection count, in-flight requests, CPU queue, and outbound queue can all cause memory pressure. With nonblocking I/O, when the CPU queue is full you can temporarily pause registering for read interest, or apply quotas/close the socket depending on the service contract.

## 9. Timeouts and Lifecycles to Keep Separate

- **`socket.setSoTimeout(5_000)`**: limits the duration of a single blocking read on `Socket.getInputStream()`. It does **not** set a 5-second deadline for the entire connection/request.
- A client can send a few bytes right before each timeout repeats, stretching the overall request for a very long time. If you need protection against slow senders, use an **overall deadline**, minimum throughput rate, or byte/chunk quota.
- **`Future.get(2, SECONDS)`**: waits for the CPU result for at most 2 seconds from when waiting begins, including time the task spends in the queue. Canceling with `cancel(true)` does not guarantee an uncooperative task stops immediately.
- **`ServerSocket.accept()`**: is a connection-waiting operation; a listener timeout (if configured) is a separate policy from `SO_TIMEOUT` on an accepted socket.
- **`Socket.close()`**: releases the socket when the handler finishes; only release the permit after the lifecycle is handled per contract. For persistent connections, the permit lasts until the connection ends.
- **Graceful shutdown**: stop the acceptor, stop accepting new tasks, track active sockets, close sockets if past a deadline, and only then clean up the pools. `shutdownNow()` is not enough to guarantee all blocked `read()` calls are unblocked across all environments.

## 10. Sizing Thread Pools with Metrics

There is no fixed formula for every TCP server:

**CPU workers** should start around the actual CPUs allocated to the JVM (`Runtime.getRuntime().availableProcessors()` is a hint), then benchmark throughput, p95/p99 latency, context switches, and contention. Adding too many CPU workers usually only increases scheduling pressure.

**I/O workers** can outnumber CPU cores if most time is spent waiting on the network, but each platform thread and socket still consumes memory/OS resources. With Java 17 platform threads, thousands of long-waiting connections can make the thread-per-connection model expensive; when high concurrency is needed, consider NIO.

**Connection permits** should be based on average lifetime, available sockets/FDs, heap/buffers, and downstream budgets. An idle connection still holds a permit, so read idle timeouts, heartbeats, and max-lifetime policies are valuable.

**Queue capacity** that is too large can hide overload and increase tail latency. A queue that is too short can reject short bursts. Measure in practice and choose appropriate queue lengths, wait times, and rejection policies instead of defaulting to unbounded.

Useful metrics:
- `active_connections` / remaining permits; total `accept`/reject/close counts.
- `io_pool_active_threads`, `cpu_pool_active_threads`, `cpu_queue_size`, CPU rejection count.
- `requests_in_flight`, read timeouts, CPU timeouts, request/response bytes.
- CPU processing time, time in CPU queue, response latency p50/p95/p99.

If CPU is at 100%, the CPU queue is full, and active connections still have room, raising the connection cap will likely only worsen latency. If CPU is idle but all I/O threads are blocked on slow clients, address timeouts, the concurrency model, or reading mechanisms before increasing the CPU pool.

## 11. Common Mistakes

| Mistake | Consequence and Fix |
|---|---|
| Assuming `ServerSocket` backlog is the limit on active clients being served | Backlog is for the OS accept queue, separate from the active semaphore |
| Calling `release()` even when `tryAcquire()` failed | Extra permits are created; the limit is no longer enforced |
| Calling `release()` only on the success path | Timeouts/exceptions leak permits; use `finally` and clear ownership |
| Releasing the connection permit as soon as the CPU task is `submit`ted | The socket is still open, so actual connections exceed the budget |
| Using `Executors.newFixedThreadPool` assuming the task queue is bounded | Fixed thread pools use an unbounded queue by default |
| Using `CallerRunsPolicy` on the CPU pool | CPU tasks can run on I/O threads, causing starvation |
| Letting CPU workers call `socket.read()` directly | CPU workers become network-waiting threads, breaking separation |
| Thinking `future.get()` means I/O is nonblocking | The I/O handler still blocks waiting for the CPU result; nonblocking needs a different I/O model |
| Encoding frame length with `String.length()` | UTF-8 Unicode byte count differs from UTF-16 code unit count |
| Using only `SO_TIMEOUT` and thinking there is an overall deadline | Trickled reads can prolong a request |
| Multiple CPU tasks writing to the same socket without coordination | Bytes/responses can interleave or reorder; use a single writer or queue |
| Assuming `shutdownNow()` will close every socket | Not guaranteed; you must manage sockets and shutdown lifecycle |

## 12. Self-Check Exercises

1. A listener has `backlog=128` and `Semaphore(10)`. At most how many connections can the application actively serve at the same time according to the semaphore? Does the backlog change that number to 128?
2. `MAX_ACTIVE=4`, four clients already hold permits, and a fifth client has just been `accept()`ed. What must happen if `tryAcquire()` returns false? Should `release()` be called?
3. A socket acquired a permit, but `io.execute` rejects the task. What two critical actions must occur?
4. With 2 CPU workers and a queue of 1, when both workers are running and the queue is full, how does `AbortPolicy` handle a new `submit`?
5. Why can `CallerRunsPolicy` defeat the goal of "separating CPU from I/O waiting"?
6. The I/O handler calls `Future.get()`. Is the CPU work running on the I/O thread? Is the I/O thread still blocked?
7. A client sends one byte every 4 seconds while `SO_TIMEOUT=5_000`. Can you conclude the server will close the connection after exactly 5 seconds from the start of the request?
8. If the protocol uses multiple requests on the same TCP connection, when should the connection permit be released? What must be done if CPU responses finish out of order?

**Key Answers:** (1) 10 sessions admitted for service; the backlog does not change that cap; (2) close the new socket, do not release; (3) close the socket and release the permit exactly once; (4) throw `RejectedExecutionException`; (5) the CPU task runs directly on the submitting thread; (6) CPU work runs on a separate pool, but the I/O thread still waits; (7) no, an overall deadline is needed; (8) hold the permit until the socket finishes and manage response ordering / an outbound queue.

## 13. Key Takeaways

- **Cap connections** with explicit admission/permits, distinct from backlog; always close the socket and release exactly one permit on the appropriate branches.
- **Separate the CPU pool from the I/O pool**, bound both workers and queues, and define rejection, timeout, and backpressure strategies.
- **Do not equate CPU offloading with nonblocking I/O**: the example still uses `Future.get()` on the I/O handler; high loads with many waiting sockets require considering NIO.
- **Measure to choose budgets**: active connections, CPU queue, rejection counts, and latency help locate the real bottleneck.
- **Protect the entire lifecycle**: timeouts, input size, responses, socket closing, permit release, and shutdown; limits on paper are useless if an error branch leaks resources.

### Reference Documentation

- [Oracle Java SE 17 — ServerSocket, backlog, and accept](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html)
- [Oracle Java SE 17 — Socket.setSoTimeout](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [Oracle Java SE 17 — Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Oracle Java SE 17 — ThreadPoolExecutor, bounded queues, RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Oracle Java SE 17 — Future.get, cancellation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Oracle Java SE 17 — NIO Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
