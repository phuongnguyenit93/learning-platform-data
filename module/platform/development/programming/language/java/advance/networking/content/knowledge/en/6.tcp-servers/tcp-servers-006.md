# Java TCP Servers: Thread per Connection, Thread Pool, and Virtual Threads

## 1. Objectives

A TCP server typically repeats two operations: **waiting for new connections** via `ServerSocket.accept()`, and then **exchanging data** with each accepted `Socket`. The problem arises when multiple clients connect concurrently: if the server processes them sequentially, one client waiting to read can force all other clients to wait.

Three common models for handling this are:

1. **Thread per connection with platform threads:** each connection has its own platform thread.
2. **Thread pool:** a fixed or bounded number of worker threads; connections are placed into a queue waiting for a worker.
3. **Virtual thread per connection:** from **Java 21 onwards**, a lightweight virtual thread can be allocated for each connection, allowing a great many pending blocking I/O tasks without requiring a dedicated OS thread for each task.

All three can use the same `ServerSocket`/`Socket` API and the same protocol handler function; they differ mainly in **how lifecycle, resources, and concurrency are managed**. This lesson focuses on TCP server design, without treating the choice of threading model as a substitute for framing, timeouts, or security.

After this lesson, you will know: why blocking `accept()`/`read()` affects concurrency; how to use `Thread`, `ExecutorService`, and `ThreadPoolExecutor`; how to understand virtual threads; how to build a runnable Java 17+ demo; how to choose models and limit load; and how to handle timeouts, shutdown, and faulty clients properly.

## 2. TCP Servers and the "Connection" Unit of Work

### 2.1. Processing Diagram

~~~text
                    ┌──────────────────────────┐
Client A ── TCP ────>│                          │──> handler(A)
Client B ── TCP ────>│  ServerSocket.accept()   │──> handler(B)
Client C ── TCP ────>│  accept loop              │──> handler(C)
                    └──────────────────────────┘
                                 │
                         dispatch handlers
                         to thread / pool
~~~

`ServerSocket` is a **listening socket** used to wait for connections. Each time `accept()` succeeds, the API returns a different `Socket` object, representing **an accepted TCP connection**. A successful `accept()` does not mean the server has received a complete application message; all data on the connection must be read from the stream according to the protocol's framing.

Some important distinctions:

- **Accept loop:** receives new connections and hands off the socket to the handler; should be kept lightweight enough not to block subsequent incoming connections.
- **Connection handler:** reads/writes on a client's socket, validates data, responds, and closes the socket when finished.
- **Blocking I/O:** `read()` may wait when no data is available yet; `write()` may wait when the send stream is congested; `accept()` waits for a new connection.
- **TCP connection ≠ Java thread:** a socket belongs to a network connection; a thread is a resource for executing Java code. You decide how to map a connection to a processing task.

The basic "one handler per connection" model is very convenient for protocols that require reading multiple requests over the same socket. However, connections can stay **idle** for minutes, so the resources consumed while waiting are what determine scalability.

### 2.2. Why Is a Sequential Loop Usually Not Enough?

~~~java
// Simple illustration, not a standalone runnable program.
try (ServerSocket server = new ServerSocket(9000)) {
    while (true) {
        Socket client = server.accept();
        handle(client); // Blocking directly on the connection-accepting thread!
    }
}
~~~

If `handle(client)` waits for the client to send enough bytes, the loop will not return to `accept()`. The TCP stack can still hold pending connections in the backlog (according to OS limits and behavior), but the application does not process other clients immediately. Increasing the backlog **does not create more workers**.

For the server to handle requests concurrently, the accept loop must hand the socket off to an appropriate execution model. Regardless of which model is chosen, **socket ownership** must be clear: once handed over to a handler, the handler is responsible for closing the socket, unless the task is rejected immediately upon dispatch.

## 3. Model A — One Platform Thread per Connection

### 3.1. Idea

A traditional platform thread (`java.lang.Thread`) is typically tied to an OS thread. Each time `accept()` returns a socket, the server creates and starts a thread to handle that socket:

~~~java
// Illustration: listener is already bound, handle(Socket) closes the socket.
while (running) {
    Socket peer = listener.accept();
    Thread worker = new Thread(
            () -> handle(peer), "tcp-client-handler");
    worker.start();
}
~~~

**You must call `start()`, not `run()`** if you actually want to run concurrently. Calling `worker.run()` directly just executes the handler on the accept thread, bringing back the sequential processing problem. Thread names should include connection-identifying information when needed for observability, but avoid putting passwords or private data into the name.

When `handle(peer)` performs a blocking `read()`, **the corresponding OS thread must wait**, consuming stack, memory, and scheduler overhead even though the handler is not using CPU. This model is easy to write and debug, suitable for internal services with a small or moderate number of concurrent connections, but has limits when the number of idle clients grows sharply.

### 3.2. Strengths and Limitations

**Strengths:**

- Readable sequential code: a handler can read the header, read the payload, process, and write the response in order.
- Relative isolation: one handler waiting on I/O does not directly block other handlers (assuming no contention on shared locks/resources).
- No need to manage an executor task queue, if only creating standalone threads.

**Limitations:**

- Each connection typically uses one platform/OS thread, even when just waiting on a socket.
- No automatic limit on the number of threads. Creating unbounded threads per connection can exhaust native stack memory, descriptors, or overload the scheduler.
- No built-in mechanism to shed work when the system is overloaded; **admission control** such as a connection count limit or semaphore is needed.
- Creating a dedicated thread for each very short-lived connection incurs startup/teardown overhead; a pool can reuse platform threads.

With traditional `Thread`, **threads are not daemon by default**. Living non-daemon threads can keep the JVM from exiting after the accept loop stops. The service must have a mechanism to stop, close sockets, wait for workers to finish, or safely force-stop according to policy.

### 3.3. Common Mistake: Forgetting to Close the Socket After the Handler Returns

The handler should own and close the socket using `try-with-resources`:

~~~java
// Snippet illustrating a handler, not a standalone program.
static void handle(Socket peer) {
    try (peer) {
        peer.setSoTimeout(5_000);
        int firstByte = peer.getInputStream().read();
        if (firstByte == -1) return; // EOF
        peer.getOutputStream().write(firstByte);
        peer.getOutputStream().flush();
    } catch (IOException ex) {
        // Log the error with context; do not swallow it and leave the socket open forever.
    }
}
~~~

`try (peer)` is valid in Java 9+ if the variable is effectively final. Each accept returns a separate socket; avoid having two handlers read concurrently from the same socket because they can consume interleaved data and corrupt parser state. If multiple tasks can write to the same connection, **entire frames** must be serialized.

## 4. Model B — Thread Pool: ExecutorService and Queue

### 4.1. Idea

Instead of creating a new platform thread for every connection, the server submits the handler to an executor. For example:

~~~java
// Illustrative code; the pool is created at the server level and closed on shutdown.
ExecutorService pool = Executors.newFixedThreadPool(8);

while (running) {
    Socket peer = listener.accept();
    pool.execute(() -> handle(peer));
}
~~~

With 8 workers, at most 8 handlers are **actively executing** in the pool at the same time. Other handlers wait their turn. This bounds the number of platform threads in the executor, but **does not automatically limit the number of accepted TCP connections** or queued tasks.

An important detail: `Executors.newFixedThreadPool(n)` uses a queue that can grow very large (effectively an unbounded queue in terms of task count in the standard configuration). If tens of thousands of clients connect and handlers wait a long time, sockets and tasks can still pile up in the queue. Therefore, "using a thread pool" is **not enough** to be called backpressure.

### 4.2. Fixed Pool with a Bounded Queue

A more explicitly bounded configuration:

~~~java
// Illustration; requires importing java.util.concurrent.*
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        8, 8,                       // core and maximum platform workers
        0L, TimeUnit.MILLISECONDS,  // keepAlive does not matter with fixed core
        new ArrayBlockingQueue<>(32), // maximum 32 queued tasks
        new ThreadPoolExecutor.AbortPolicy());
~~~

With this configuration, we have at most 8 running workers and 32 tasks waiting in the executor's queue. When it cannot accept more, `execute(...)` throws `RejectedExecutionException`. The server must handle rejection:

~~~java
Socket peer = listener.accept();
try {
    pool.execute(() -> handle(peer));
} catch (RejectedExecutionException rejected) {
    try {
        peer.close(); // Mandatory to release the socket that was not handed off.
    } catch (IOException closeError) {
        rejected.addSuppressed(closeError);
    }
    // Record metric and decide whether to continue accepting or shed load.
}
~~~

This snippet illustrates **closing a rejected socket**. If handlers are queued, an accepted socket can wait a very long time **before** the handler calls `setSoTimeout`. A bounded queue helps limit queued resources but does not completely solve clients holding connections open for a long time; total connection limits, timeouts, max session duration, and deadlines are needed.

Common rejection policies:

| Policy | Behavior on overload | Risks / usage conditions |
| --- | --- | --- |
| `AbortPolicy` | Throws `RejectedExecutionException` | Can proactively close the socket and report overload; easy to observe |
| `CallerRunsPolicy` | The thread calling `execute` runs the handler itself when not shut down | If the caller is the accept thread, it can get stuck in I/O; creates backpressure but blocks accept |
| `DiscardPolicy` | Drops the task without throwing an exception | With sockets, easily **leaks connections** if not closed properly; not recommended |
| `DiscardOldestPolicy` | Drops the oldest task in the queue and retries | The old task may own a socket; easily leaks / hard to guarantee protocol safety without cleanup |

For a TCP server, the clearest solution is usually **bounded queue + explicit rejection handler + socket close**, combined with admission control before or after accept. Do not use `newCachedThreadPool()` as a load-limiting mechanism: this pool can create many platform threads as demand spikes.

### 4.3. What Workloads Suit a Pool?

A pool is especially useful when each handler is relatively short, or the number of truly active connections at the same time is much smaller than the total number of accessing clients. However, with protocols featuring **long-lived connections and blocking reads**, a worker can be held for the entire session. When all 8 workers are waiting on 8 idle clients, the 9th client gets queued **even though the CPU is nearly idle**.

Do not solve this situation simply by increasing the thread count to a huge number. You can choose non-blocking NIO + an event loop, or Java 21 virtual threads; either model still requires limiting sockets, buffers, memory, and fair CPU handling.

## 5. Model C — Virtual Thread per Connection (Java 21+)

### 5.1. What Is a Virtual Thread?

**Virtual threads** were standardized in Java 21. They are `Thread` objects scheduled by the JVM onto a set of platform threads (often called **carrier threads**). The goal is to allow **thread-per-task** style code, especially with blocking I/O, to scale to a large number of tasks without needing a dedicated OS thread for each waiting task.

When a virtual thread waits on compatible blocking I/O operations, the JVM can usually **unmount** the task from its carrier so the carrier can run another task. Thus:

- A virtual thread can be attached to **a long-lived connection** in code as simple as with platform threads.
- Creating and waiting on many virtual threads is usually lighter than creating a corresponding number of platform threads.
- **Virtual threads do not make the CPU faster.** CPU-bound tasks still contend for real CPU cores.
- This is still a *concurrency* model, not magic for network operations: socket descriptors, buffers, heap, databases, and downstream limits remain finite resources.

### 5.2. Java 21+ API

If using Java 21 or newer:

~~~java
// Java 21+ — illustrative snippet, assuming listener/handle/running already exist.
// This executor creates one virtual thread per task.
try (ExecutorService executor =
             Executors.newVirtualThreadPerTaskExecutor()) {
    while (running) {
        Socket peer = listener.accept();
        executor.execute(() -> handle(peer));
    }
}
~~~

`Executors.newVirtualThreadPerTaskExecutor()` is available from Java 21; this code **will not compile on Java 17**. Another direct way is `Thread.startVirtualThread(() -> handle(peer))`. Both follow the spirit of **one virtual thread per connection handler**, rather than reusing a small pool of virtual threads.

`ExecutorService.close()` in Java 21's try-with-resources waits for tasks to finish when closing. If the accept loop runs forever or handlers are waiting indefinitely on I/O, shutdown cannot complete just by closing the executor: you must **stop accepting**, **close the listening socket** and connected sockets, set timeouts/deadlines, and handle task cancellation. The snippet above illustrates the API, not a service with a full lifecycle.

### 5.3. Virtual Threads Should Not Be "Pooled" Like Platform Threads

The main benefit of virtual threads is **creating a lightweight thread per task**. Do not fix a pool of 8 virtual threads and force thousands of connections to wait in a queue just to "save virtual threads." That is optimizing the wrong resource.

If you need to limit the number of sessions, DB queries, or downstream requests, limit the **actual resource** using a `Semaphore`, connection limiter, rate limiter, bounded request queue, or appropriately sized DB connection pool. Virtual threads reduce the cost of *threads while waiting*, not database connection limits.

Example of limiting the number of handlers currently owning connections:

~~~java
// Java 21+ — admission control illustration, not a standalone main.
// listener, handle(Socket), running, and MAX_CONNECTIONS are managed by the server.
Semaphore slots = new Semaphore(MAX_CONNECTIONS);

try (ExecutorService vexec =
             Executors.newVirtualThreadPerTaskExecutor()) {
    while (running) {
        Socket peer = listener.accept();
        if (!slots.tryAcquire()) {
            peer.close(); // Exceeded allowed sessions: reject and close.
            continue;
        }
        try {
            vexec.execute(() -> {
                try {
                    handle(peer); // Handler must close peer.
                } finally {
                    slots.release();
                }
            });
        } catch (RejectedExecutionException ex) {
            slots.release();
            peer.close();
            throw ex;
        }
    }
}
~~~

This section is **illustrative code in a server context**, requiring `java.util.concurrent.*` imports, `IOException` handling, and appropriate shutdown logic; it is not a standalone Java file. `Semaphore` enforces the limit on total active sessions. `tryAcquire()` here proactively **rejects connections** when permits run out instead of piling up sockets indefinitely. If the handler throws an unchecked exception, `finally` still releases the permit. All error paths before handing off the socket must also ensure the socket is closed or the permit is released properly.

### 5.4. Limitations to Keep in Mind

- A virtual thread blocking on a compatible I/O API can release its carrier; however, **native calls, certain lock/monitor regions, and incompatible APIs** can cause it to be *pinned* depending on the JDK version. Avoid holding locks across blocking I/O and use JFR/thread dump diagnostic tools to inspect real-world behavior.
- `ThreadLocal` still works with virtual threads; however, if there are very many sessions, storing large buffers or objects in `ThreadLocal` per virtual thread can consume significant memory. Design state explicitly with bounded lifecycles.
- Virtual threads run blocking code in a sequential style; they do not automatically limit message length, timeouts, socket creation rate, or contending CPU tasks.
- Virtual threads are suited for **I/O-bound workloads**, not necessarily optimal for long CPU-bound computations. For CPU-bound work, limit parallelism appropriately.
- Java 17 LTS **does not have** the stable virtual thread API; separate Java 21+ code from Java 17 classes when compiling.

## 6. Comparing the Three Models by Actual Resources

| Criterion | Platform thread / connection | Fixed thread pool | Virtual thread / connection |
| --- | --- | --- | --- |
| Java support | Java 17+ and earlier | Java 17+ and earlier | **Java 21+** |
| Connection mapping | 1 platform thread/connection | Each handler holds 1 worker while running; other connections wait in queue | 1 virtual thread/connection, JVM shares carriers |
| Blocking socket read | Occupies 1 OS thread while waiting | Occupies 1 pool worker while waiting | Usually unmounts and frees carrier if I/O is compatible |
| Natural limit | Platform threads/native resources | Workers are bounded; default queue may be unbounded | Virtual threads are lightweight but do not limit sockets/heap |
| Overload management | Must add connection cap | Bounded queue, rejection, close socket | Semaphore/rate limit/connection cap, downstream limits |
| Handler code | Sequential, easy to understand | Sequential, easy to understand | Sequential, easy to understand |
| Suitable scenarios | Few connections or short connections | Controllable number of concurrent blocking tasks | Very many waiting I/O-bound connections, using Java 21+ |
| When not to prefer | Tens of thousands of idle sessions | Small pool occupied by long-lived sessions | Purely CPU-bound problems, heavy native blocking/pinning |

The comparison table describes **architectural tendencies**, not guaranteed throughput numbers. Actual performance depends on the OS, JVM, session length, payload, GC, database, TLS, kernel backlog, file descriptors, idle client ratio, and load-limiting policies.

## 7. Complete Java 17+ Example: Platform Thread per Connection and Bounded Pool

The following example uses a TCP server on **loopback** (no Internet needed) and three clients sending integers with `DataOutputStream.writeInt()`. The server accepts each socket via `accept()`; the `platform` mode creates a new thread, while the `pool` mode uses 2 workers with a bounded queue. Each handler reads a number, simulates a 100 ms wait, responds with that number multiplied by 10, and closes the socket. Three clients run concurrently and main waits for results in client ID order for deterministic stdout.

This is an example teaching **execution models**, not a production server. It uses a minimal one-request-per-connection protocol, avoiding complex parsers to focus on threading. In a real system, validation, policy-based overload handling, and graceful shutdown are needed.

Create the file **TcpConcurrencyDemo.java** with the following content:

~~~java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class TcpConcurrencyDemo {
    static final int CLIENTS = 3;

    static void handle(Socket socket) {
        try (socket;
             DataInputStream in =
                     new DataInputStream(socket.getInputStream());
             DataOutputStream out =
                     new DataOutputStream(socket.getOutputStream())) {

            socket.setSoTimeout(3_000);
            int id = in.readInt();
            if (id < 1 || id > CLIENTS) {
                throw new IOException("Invalid id");
            }

            // Simulate a waiting I/O task (not CPU-bound).
            try {
                Thread.sleep(100);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }

            out.writeInt(id * 10);
            out.flush();
        } catch (IOException ex) {
            System.err.println("Client handling failed: " + ex);
        }
    }

    static int call(int port, int id) throws IOException {
        try (Socket client = new Socket()) {
            client.connect(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), port), 2_000);
            client.setSoTimeout(3_000);

            DataOutputStream out =
                    new DataOutputStream(client.getOutputStream());
            DataInputStream in =
                    new DataInputStream(client.getInputStream());

            out.writeInt(id);
            out.flush();
            return in.readInt();
        }
    }

    static void runMode(String mode) throws Exception {
        ThreadPoolExecutor pool = mode.equals("pool")
                ? new ThreadPoolExecutor(
                        2, 2,
                        0L, TimeUnit.MILLISECONDS,
                        new ArrayBlockingQueue<>(3),
                        new ThreadPoolExecutor.AbortPolicy())
                : null;

        List<Thread> dedicated = new ArrayList<>();
        ExecutorService acceptor = Executors.newSingleThreadExecutor();
        ExecutorService clients = Executors.newFixedThreadPool(CLIENTS);

        try (ServerSocket server = new ServerSocket(
                0, 10, InetAddress.getLoopbackAddress())) {

            server.setSoTimeout(3_000);

            Future<?> accepting = acceptor.submit(() -> {
                try {
                    for (int i = 0; i < CLIENTS; i++) {
                        Socket peer = server.accept();

                        if (pool == null) {
                            // Mode A: one platform thread per connection.
                            Thread thread = new Thread(
                                    () -> handle(peer),
                                    "client-handler-" + i);
                            dedicated.add(thread);
                            thread.start();
                        } else {
                            // Mode B: 2 platform workers, queue max 3.
                            try {
                                pool.execute(() -> handle(peer));
                            } catch (RejectedExecutionException ex) {
                                peer.close(); // Do not leak the socket.
                                throw ex;
                            }
                        }
                    }
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            });

            List<Future<Integer>> replies = new ArrayList<>();
            for (int id = 1; id <= CLIENTS; id++) {
                final int requestId = id;
                replies.add(clients.submit(
                        () -> call(server.getLocalPort(), requestId)));
            }

            int[] values = new int[CLIENTS];
            for (int i = 0; i < CLIENTS; i++) {
                values[i] = replies.get(i).get(5, TimeUnit.SECONDS);
            }

            // Propagate errors from the acceptor thread to main (if any).
            accepting.get(5, TimeUnit.SECONDS);
            System.out.println(mode + " -> " + Arrays.toString(values));

        } finally {
            if (pool != null) {
                pool.shutdown();
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            }
            for (Thread thread : dedicated) {
                thread.join(5_000);
            }
            clients.shutdownNow();
            acceptor.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        runMode("platform");
        runMode("pool");
    }
}
~~~

Compile and run with **JDK 17 or newer**:

~~~bash
javac -encoding UTF-8 TcpConcurrencyDemo.java
java TcpConcurrencyDemo
~~~

Stdout on a successful run:

~~~text
platform -> [10, 20, 30]
pool -> [10, 20, 30]
~~~

### 7.1. Why Are the Results of Both Modes Identical?

**The concurrency models differ, while the protocol and computation are the same.** The server receives IDs 1/2/3, multiplies by 10, and returns 10/20/30. Main retrieves `Future` results in **request submission order**, so the printed order does not depend on which client finishes first. Try changing the calculation or logging the thread name in the handler to observe the thread count more clearly, but do not rely on log ordering across workers to determine program correctness.

`Thread.sleep(100)` only simulates a wait interval for illustration: it does not perform real I/O and does not prove the throughput of either model. With **3 clients**, both approaches handle them; this is not a benchmark. For real evaluation, you need to measure under sufficient load with p95/p99 latency, throughput, heap/native memory, socket count, CPU, GC, queue depth, rejected requests, and downstream CPU.

### 7.2. Why Doesn't the Pooled Server Create More Threads Under High Load?

In `pool` mode, `ThreadPoolExecutor(2,2, ..., queue(3))` uses at most 2 platform workers. The third client may have to wait in the queue until a worker becomes free. The queue holds **socket-processing tasks**, and does not make the sockets asynchronous. If clients keep connections open without sending data, workers will stay blocked at `readInt()` until data arrives, EOF, or timeout.

`platform` mode has no worker queue but creates 1 OS thread for each accepted socket. When there are many idle connections, resource consumption can be higher. This is the main trade-off that virtual threads aim to improve.

### 7.3. Areas to Improve Before Production

The demo accepts exactly three connections to have a deterministic stopping point, does not run an infinite loop, has no TLS, and only replies with a single `int`. In a real service:

- Replace the fixed `CLIENTS` count with an accept loop that has a proactive stop mechanism.
- Under overload, limit **active connections** and queued tasks; close sockets immediately upon rejection.
- Add overall request deadlines, message size limits, and idle timeouts.
- Track open sockets to close them on shutdown; do not just call `ExecutorService.shutdownNow()` and expect all blocking reads to terminate immediately.
- Offload CPU-heavy work from I/O threads if tasks are long; consider a pipeline with an appropriate concurrency level.
- Include health checks, metrics, safe logging, client limits, and tests for network errors and connection resets.

## 8. Backpressure and Overload: A Bigger Problem Than Thread Selection

When a server can no longer keep up with incoming data, there must be **backpressure**—that is, controlling the amount of new work. Without it, all three models can be exhausted.

Example of finite resources:

~~~text
Server:
  max open sockets       = 1,000
  max active DB queries  = 32
  max pending tasks      = 100
  max request payload    = 64 KiB

50,000 clients connect simultaneously:
  No thread model automatically turns 1,000 sockets into 50,000 sockets.
  Must accept / reject / queue / timeout / limit explicitly.
~~~

The numbers above are only **an illustration of how to set resource budgets**, not universal recommended parameters. You must choose them based on machine resources, the application, and SLAs.

### 8.1. Four Levels of Limits

1. **Socket/file descriptors:** the OS has limits on file descriptors, kernel memory, and socket buffers; lightweight Java threads do not reduce the number of TCP connection descriptors.
2. **Active connection/session count:** use a counter or `Semaphore` to ensure not too many sessions are accepted for processing.
3. **Executor/queue capacity:** with platform threads, bound workers and use a bounded queue; with virtual threads, limit tasks/downstream resources as needed rather than using a "small pool of virtual threads."
4. **Downstream/CPU/heap:** DB pool, HTTP upstream, business logic, parsing large payloads, object lifetimes, and GC; enforce limits at each layer.

Using a large queue does not equate to higher throughput. It may only increase wait times, causing clients to time out before a worker processes them. A good system usually **reports overload early and transparently** rather than keeping thousands of connections open to wait indefinitely.

### 8.2. Accept Backlog Is Not a Worker Queue

The backlog parameter when binding `ServerSocket` relates to **the queue of connections waiting to be accepted at the OS level**, with actual semantics/caps depending on the OS. It is not the `ThreadPoolExecutor` queue. A full backlog can cause connects to be slow/fail; a full pool queue is a state where **the app has already accepted** but cannot process fast enough. The two bottlenecks need different metrics.

### 8.3. Per-Connection State and Independence

Each handler should keep parser state scoped to the connection: bytes received so far, frame length, client permissions, processing deadline. Do not let multiple handlers share the same `DataInputStream` or `BufferedReader` for a single socket without explicit protocol multiplexing. Sharing caches, session maps, or metrics across threads requires safe mechanisms like `ConcurrentHashMap`, atomics, or locks; however, avoid holding locks while performing blocking I/O.

With virtual threads, storing connection-bound state in local variables/session objects is usually easier to manage than using large `ThreadLocal`s. Because `ThreadLocal` does not have a small thread pool to reuse from, state across millions of virtual threads can increase memory usage significantly.

## 9. Timeouts and Shutdown Across the Three Models

### 9.1. Read Timeouts Apply to the Socket, Not the Executor

`socket.setSoTimeout(5_000)` limits **a single blocking read wait**. If the client sends no bytes, the handler can catch `SocketTimeoutException` and decide to close the session. However:

- This is not a limit on total connection lifetime; a client trickling bytes slowly can prolong the session.
- `SO_TIMEOUT` does not automatically limit `write()` or connect time.
- For `ServerSocket`, `listener.setSoTimeout(...)` only applies to the wait time of `accept()`.
- Pools/virtual threads do not alter the semantics of TCP timeouts.

You should have an **idle timeout**, **frame deadline**, **request deadline**, and protocol-appropriate retry counts. Overall deadlines should be measured with `System.nanoTime()`. If connections are held long, detecting idle clients or canceling sessions in time helps free workers/sockets, rather than just "adding more threads."

### 9.2. Server Shutdown Must Be Ordered

A typical graceful shutdown strategy is:

1. Mark `running = false` so no new work is accepted.
2. Close `ServerSocket` to wake up the blocking `accept()` (usually throws `SocketException`); treat this as the expected exit path when shutting down.
3. Stop accepting new tasks, e.g., `executor.shutdown()`; wait for handlers to complete within an allowed timeout.
4. If the timeout expires, cancel tasks, close remaining open client sockets to unblock blocking I/O, and wait for cleanup.
5. Ensure every connection permit/counter is released exactly once in `finally`. Flush metrics and shutdown logs without losing information needed for reconciliation.

`shutdownNow()` only sends interrupt/cancel signals as supported by the API; it **does not** reliably replace closing all sockets currently blocked on read in every situation. `ExecutorService.close()` also requires designing termination conditions for handlers, otherwise it may wait a long time. In the platform-thread-per-connection model without an executor, you need a mechanism to track and join/cancel handler threads.

### 9.3. Errors Must Not Accidentally Kill the Accept Loop

Normally, a handler catches and handles `IOException` for its own client, closes the socket, and exits. Do not let a single client sending a malformed request cause **the entire server** to stop accepting. Conversely, severe errors on the listening socket or shutdown must be reported/exit the loop in a controlled manner; do not use `while(true) { catch(Exception e) {} }` to loop forever, causing CPU spin when the socket is already closed.

If a handler runs via `ExecutorService.submit()`, exceptions may be captured inside the `Future` rather than printed automatically; you must observe `Future.get()` or monitor the task. With `execute()`, unchecked exceptions go through the thread's uncaught exception handling. Choose logging/metrics mechanisms intentionally so errors are not lost.

## 10. When to Choose Which Model?

### Case 1: Internal admin server, a few dozen clients

Platform thread per connection is simple and easy to debug, provided there is a connection cap and timeout. Not every application needs virtual threads or non-blocking NIO.

### Case 2: Many short requests, concurrent running handlers need to be bounded

A bounded `ThreadPoolExecutor` with workers sized for CPU/downstream is usually reasonable. Pay attention to queue wait, task rejection, and having the server close sockets when out of capacity. If tasks hold sockets throughout long sessions, a small pool can cause bottlenecks even when CPU is idle.

### Case 3: Very many concurrent connections, mostly waiting on socket I/O

On Java 21+, virtual thread per connection keeps sequential blocking code easy to read while reducing platform thread overhead. However, you still must limit **sockets and downstream resources**, configure timeouts, watch for pinning, and test under realistic load.

### Case 4: Need event-driven handling of massive connections, fine-grained buffer/throughput control

Non-blocking `SocketChannel` + `Selector` or an event-loop framework may be appropriate. That model decouples connection state from threads, requiring stateful parsers and more careful handling of partial reads/writes. Virtual threads do not negate the benefits of NIO for specific workloads and systems.

### Case 5: Heavy CPU-bound computation

Adding platform threads does not create more CPU; the same goes for virtual threads. Use concurrency limits matching core counts and downstream resources; consider offloading heavy computation to a separate executor so socket-serving handlers do not monopolize resources indefinitely.

## 11. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `worker.run()` instead of `start()` | Runs on the accept thread, losing concurrency | Call `start()` or `executor.execute(...)` |
| Calling `handle()` directly inside the `accept()` loop | One blocking client prevents the server from handling others | Dispatch the handler to an appropriate thread/task |
| Creating unbounded platform threads | Exhausts OS threads/native memory | Limit connections; use an appropriate pool or virtual threads |
| Assuming `newFixedThreadPool` automatically caps all queues | Tasks/sockets can accumulate indefinitely | Use a bounded `ThreadPoolExecutor` and a rejection policy |
| Using `DiscardPolicy` with socket tasks | Sockets are abandoned, leaking descriptors | Signal rejection and close the socket immediately |
| A small pool holding thousands of long-lived TCP sessions | Workers are blocked on reads, large queue buildup | Limit sessions, adjust architecture, use virtual threads or NIO |
| Pooling virtual threads just thinking they are "expensive" | Creates an unnecessary bottleneck | Virtual thread per task; limit actual resources |
| Thinking virtual threads make CPU-bound tasks faster | CPU remains bottlenecked, throughput does not increase | Limit computation, optimize algorithms/CPU |
| Forgetting `setSoTimeout` and overall deadline | Idle/slow-trickle clients hold handlers too long | Read timeout + session/frame deadline |
| Not closing the socket when a task is rejected | Connection stays open with no owning handler | Close inside the `RejectedExecutionException` catch block |
| Closing the executor but forgetting to close the listening socket | `accept()` stays blocked, server does not exit | Stop accepting, close listener, drain handlers |
| Relying on `shutdownNow()` as a guaranteed way to cancel reads | Blocking I/O may remain stuck depending on API/state | Close active client sockets |
| Catching exceptions and ignoring them | Client/server errors go unobserved | Log/record metrics with context, clean up resources |
| Multiple handlers reading the same socket | Data gets interleaved, parser breaks | One read owner per connection or proper multiplexing |
| Holding shared locks during blocking I/O | Stalls all other handlers; may pin carrier | Shorten lock scope, avoid I/O inside synchronized blocks |
| Using thread count as the sole load metric | Ignores sockets/queues/DB/heap | Monitor multiple resource layers and p95/p99 |

## 12. Self-Check Exercises

### Exercise A — Thread per Connection and 1,000 Idle Clients

A server creates 1 platform thread per client, and each client calls `read()` and waits a long time for data. How many threads are involved in 1,000 handlers?

**Answer:** roughly 1,000 platform threads may be needed to serve 1,000 connection handlers, not counting accept/main/runtime threads. Many of those threads are blocked on read, consuming native thread resources even when the CPU is barely busy. Connection limits, timeouts, and another model should be considered.

### Exercise B — 8-Worker Pool, 100 Connections Holding Slots

Suppose `Executors.newFixedThreadPool(8)` is used, and all 8 connection handlers are waiting for data. Where are the remaining 92 handlers?

**Answer:** they are waiting in the executor's queue (if submitted successfully), potentially holding open sockets without being served yet. Do not assume a fixed thread pool automatically limits connections; bounded queues/admission control are the application's responsibility.

### Exercise C — Executor Rejects a New Socket

A pool has 8 workers and a queue of 16 tasks, all full. `execute(() -> handle(peer))` throws `RejectedExecutionException`. What must be done?

**Answer:** **close `peer`** because ownership was not transferred to a handler; record overload metrics and decide on retry/backoff/exit according to policy. Do not just catch the exception and ignore it.

### Exercise D — Virtual Threads and 100,000 Clients

A Java 21 server uses `newVirtualThreadPerTaskExecutor()`. Does this allow "100,000 clients unconditionally"?

**Answer:** no. Virtual threads reduce scheduling/stack overhead for I/O-bound tasks, but file descriptors, socket buffers, heap, TCP backlog, TLS, service limits, and databases remain finite. Stress testing, session limits, and downstream limits are still required.

### Exercise E — Debugging a Hung Shutdown

The server calls `executor.close()`, but a handler is still waiting indefinitely on `read()`. Why is shutdown slow?

**Answer:** closing the executor waits for tasks to complete; if a connection has no deadline or has not been closed, the handler may never exit. You must track open sockets, close them on shutdown, stop accepting, and wait with a reasonable deadline.

### Exercise F — Choosing a Model for 5,000 TCP Chat Sessions

Most sessions are idle, each occasionally sending small messages, and the application is deployed on Java 21. Which model is worth trying first?

**Answer:** virtual-thread-per-connection is worth trying first because each handler can use sequential blocking I/O and spends most of its time waiting. However, the final choice needs benchmarking and still requires capping sockets, buffer sizes, max session duration, parse limits, and backpressure. An NIO event loop could also be suitable.

## 13. Multi-Connection TCP Server Implementation Checklist

- [ ] Does the accept loop only accept connections and dispatch, without accidentally blocking long in a handler?
- [ ] Have you explicitly chosen **platform per connection**, **bounded pool**, or **virtual per connection (Java 21+)**?
- [ ] Does each socket have a single owner responsible for reading, processing, and closing?
- [ ] Have concurrency limits been defined: socket count, executor workers, queue depth, downstream sessions, CPU, and heap?
- [ ] When rejected or task dispatch fails, is the socket closed and the permit released?
- [ ] Do socket reads have timeouts; do frames/requests/sessions have appropriate deadlines and size limits?
- [ ] Have you tested with idle clients, slow clients, disconnects, partial frames, and a full queue?
- [ ] Are you avoiding unbounded platform threads or unbounded pool queues as a load-handling strategy?
- [ ] With Java 21 virtual threads, have you checked compatible blocking APIs, thread-local footprint, and monitor/lock regions?
- [ ] Do the accept loop, worker handlers, thread pool, and sockets all have shutdown paths and error observability?
- [ ] Have you benchmarked by concurrent connections, throughput, p95/p99, heap/native memory, queue depth, rejects, and downstream load?

**Conclusion:** A TCP connection does not automatically equate to an OS thread. **Thread per connection** is easy to understand but hard to scale to many idle clients; a **thread pool** bounds platform workers but must manage queues, waiting sockets, and overload; **virtual thread per connection** (Java 21+) brings a sequential code model with lighter thread cost when waiting on I/O. Whichever approach you choose, the deciding factors for server reliability remain **socket ownership, timeouts, framing, backpressure, and controlled shutdown**.