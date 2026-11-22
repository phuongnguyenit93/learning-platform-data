# Choosing Blocking, Selector, or Asynchronous APIs for the Task

## 1. The Problem of Choosing an I/O Model

Java lets you implement the same read/write operation in several ways. For a TCP client sending `PING` and awaiting `PONG`, you can:

- Call `SocketChannel.read()`/`write()` in **blocking mode**: the thread may wait at the call.
- Use `SocketChannel.configureBlocking(false)` combined with a **`Selector`**: an event-loop thread waits for *readiness* signals, then actively invokes read/write.
- Use **`AsynchronousSocketChannel`**: initiate the operation and obtain results via `Future` or `CompletionHandler` (*completion*), without necessarily keeping the calling thread waiting.

The difference does not lie in "which API is more modern," but in **who holds I/O state while unfinished** and **which thread bears the waiting cost**.

~~~text
Blocking:
  thread -> connect -> write -> read[wait] -> process -> close

Selector / readiness:
  event loop -> select -> channel ready -> attempt read/write
             -> unprocessed bytes remain? keep state -> next select

Asynchronous / completion:
  caller -> issue read/write -> continue other work
                                      |
                     Future or CompletionHandler delivers result
~~~

**Choose based on actual workload**: open connection count, wait-to-CPU ratio, throughput, tail latency, acceptable complexity, timeout/cancellation requirements, and RAM/file descriptor limits. Blocking, selector, and async can each be the right choice in different circumstances.

## 2. Three Concepts to Distinguish

### 2.1. Blocking: The Call May Wait

~~~java
try (SocketChannel socket = SocketChannel.open(remote)) {
    ByteBuffer dst = ByteBuffer.allocate(1024);
    int n = socket.read(dst);
    // Calling thread may wait at read().
}
~~~

This is an **illustrative snippet**, requiring `SocketChannel`, `ByteBuffer`, and a valid `remote`; `IOException` must be declared or handled. `SocketChannel.open(remote)` uses a blocking TCP connection by default.

Blocking code has linear control flow, is easy to follow in a debugger, and manages resources cleanly with `try-with-resources`. When an application has many platform threads blocked for long periods on the network, stack memory, scheduler overhead, and resource limits can become significant.

Blocking **does not guarantee a single `read` fills the buffer**. A channel may receive fewer bytes than the application needs; `write` may also consume less than `remaining()`. Protocol-driven loops are required across every model.

### 2.2. Selector: Readiness, Not Completion

~~~java
socket.configureBlocking(false);
SelectionKey key = socket.register(selector, SelectionKey.OP_READ);
selector.select();
~~~

This is an **illustrative snippet**: `socket` must be initialized and `selector` already open. `SelectionKey.OP_READ` means the program is interested in when the socket **can attempt reading**.

When `key.isReadable()`, the application calls `socket.read(buffer)`. The call may return:

- `n > 0`: `n` bytes were received;
- `n == 0`: no bytes were transferred this time;
- `n == -1`: end of stream (EOF) on the read side.

Readiness does not mean the entire TCP message has arrived. Because one event loop can manage many sockets, it typically must retain input buffers, parser state, and output queues **per connection**.

### 2.3. AsynchronousChannel: Completion of an Operation

~~~java
try (AsynchronousSocketChannel socket =
        AsynchronousSocketChannel.open()) {
    Future<Void> future = socket.connect(remote);
    future.get(); // Caller still BLOCKS if waiting at get().
}
~~~

This is an **illustrative snippet**; requires `AsynchronousSocketChannel`, `Future`, a valid `remote`, and handling checked exceptions.

Async APIs have two styles:

- **`Future`**: initiates the operation and returns a Future to poll/wait for the result. Calling `get()` immediately after each call can turn the caller into a waiting thread just like sequential code.
- **`CompletionHandler`**: passes a callback to the API and receives `completed` or `failed` when the operation finishes. You must manage data lifetimes, error flows, and callback threads.

"Async" does not mean threadless: the implementation may use a thread pool, completion ports, or other platform mechanisms. Nor does it mean zero-copy, built-in transactions, or automatic resolution of partial I/O.

## 3. Comprehensive Comparison Table

| Criterion | Blocking I/O | Non-blocking Selector | Asynchronous API |
| --- | --- | --- | --- |
| Semantics | Caller may wait until the operation progresses/completes per contract. | Selector notifies channel ready; caller attempts read/write itself. | Future/callback reports that a specific operation completed/failed. |
| Source code | Linear, minimal state machine. | Event loop and per-connection state. | Continuations, callbacks/Future, and in-flight state. |
| Concurrency | Typically uses many platform threads or a pool. | One event loop can monitor many selectable channels. | Provider/pool handles multiple operations; thread count depends on implementation. |
| File handling capability | `Files`/`FileChannel` are very convenient. | `FileChannel` cannot register with Selector like a socket. | `AsynchronousFileChannel` supports positional file I/O. |
| Partial read/write | Yes. | Yes. | Yes, even when a Future/completion returns a result. |
| Timeout | Configured and deadlined per API/protocol. | Must track deadlines in the event loop; `select(timeout)` only bounds waiting for readiness. | `Future.get(timeout)`/handler and cancel/close policies. |
| Backpressure | Bound workers/queues, wait on write. | Manage `OP_READ`/`OP_WRITE` and per-connection queues. | Limit in-flight operations and buffer lifetimes. |
| Implementation cost | Usually lowest. | Must manage state, fairness, readiness, and cleanup yourself. | Must manage callbacks, ownership, cancellation, and completion order. |
| Best suited for | Simple I/O, low/moderate connections, batch tools. | Many concurrent sockets, mostly idle, event-driven services. | Completion-based pipelines, file offsets, and callbacks/Future. |

Do not interpret this table as benchmark results. Measured performance also depends on OS, provider configuration, payload, server behavior, GC, TLS, connection count, and application processing time.

## 4. When Is Blocking a Reasonable Choice?

Blocking fits well when:

1. Communicating over only a few connections, or pending connections fit comfortably within the current thread pool.
2. Request/response logic benefits from linear, readable code and straightforward exception handling.
3. CLI tools, batch jobs, small services, or local file reading/writing with moderate volume.
4. Dependent libraries are mostly blocking and massive concurrent connection counts are not required.
5. The current approach already meets throughput/latency goals with no profiling evidence that thread waiting is the bottleneck.

### 4.1. Full Send and Receive with Blocking SocketChannel

~~~java
static void writeFully(SocketChannel channel, ByteBuffer source)
        throws IOException {
    while (source.hasRemaining()) {
        int n = channel.write(source);
        if (n == 0) {
            throw new IOException("Blocking write không tiến triển");
        }
    }
}

static void readFully(SocketChannel channel, ByteBuffer target)
        throws IOException {
    while (target.hasRemaining()) {
        int n = channel.read(target);
        if (n == -1) {
            throw new EOFException("EOF trước khi đủ dữ liệu");
        }
        if (n == 0) {
            throw new IOException("Blocking read không tiến triển");
        }
    }
}
~~~

The two methods above are **snippets to place inside a class**, importing `IOException`, `EOFException`, `ByteBuffer`, and `SocketChannel`. They are intentionally written for *blocking channels* with buffer space available and forward progress expected. Do not reuse them unchanged for non-blocking sockets: a return value of `0` there can be completely normal.

`readFully` should only be used if the protocol strictly requires **an exact number of bytes**. Reading a file until EOF or reading newline-delimited text follows a different procedure.

### 4.2. Do Virtual Threads Change the Decision?

Starting with **Java 21**, virtual threads are an important option for large numbers of *blocking-style* tasks. In Java 17, virtual threads are not yet a standard feature, so the code examples in this lesson use only Java 17 APIs.

Virtual threads do not remove the need to bound sockets, downstream database connections, memory buffers, or deadlines. If a project is permitted to upgrade to Java 21+, include virtual threads in your comparison alongside selectors and async.

## 5. When Should You Choose Selector?

Choose `Selector` when:

- There are thousands of concurrently open TCP connections, most of them idle waiting for data.
- You want **one or a few I/O event-loop threads** managing many sockets.
- Each event handling turn is brief, and you can design parsers as state machines.
- You want control over readiness, outbound queues, fairness, and per-connection backpressure.
- The system already follows a non-blocking architecture or uses a selector-based framework.

Event-loop skeleton pattern:

~~~java
while (running) {
    selector.select();
    Iterator<SelectionKey> iterator =
            selector.selectedKeys().iterator();

    while (iterator.hasNext()) {
        SelectionKey key = iterator.next();
        iterator.remove(); // Mandatory to avoid retaining stale selected keys.

        if (!key.isValid()) {
            continue;
        }
        if (key.isAcceptable()) {
            // ServerSocketChannel.accept(): may return null.
        } else if (key.isConnectable()) {
            // SocketChannel.finishConnect(): finishes pending connect.
        } else if (key.isReadable()) {
            // SocketChannel.read(): >0, 0, or -1.
        } else if (key.isWritable()) {
            // SocketChannel.write(): may write partially or 0.
        }
    }
}
~~~

This is **event-loop pseudocode**, omitting declarations for `running`, `selector`, per-connection state, try/catch, and cleanup.

Key principles:

- Only channels in **non-blocking mode** can register with a Selector. A `SocketChannel` returned by `ServerSocketChannel.accept()` starts in blocking mode; call `configureBlocking(false)` before registering.
- A selector only signals *ready*. `read/write` may still transfer partial data. Each `ByteBuffer`'s position/limit state must be preserved across turns.
- `SelectionKey.attachment()` can hold the input parser, output queue, and connection metadata.
- `OP_WRITE` should not stay enabled continuously when no bytes are waiting to send; doing so can wake up the event loop incessantly.
- Never run CPU-heavy processing, blocking database queries, or sleeps on the event loop; one slow callback stalls every socket sharing that thread.
- `selector.close()` is not equivalent to closing all peer sockets; the application must close the channels it owns.

In particular, **`FileChannel` is not a `SelectableChannel`**. Do not try to use a Selector to "make FileChannel asynchronous"; use the appropriate file API instead.

## 6. When Should You Choose AsynchronousChannel?

Key Java NIO.2 classes:

| API | Function |
| --- | --- |
| `AsynchronousSocketChannel` | Asynchronous TCP connect/read/write. |
| `AsynchronousServerSocketChannel` | Asynchronous TCP bind and accept. |
| `AsynchronousFileChannel` | Read/write file regions at explicit offsets via Future/callback. |
| `CompletionHandler<V, A>` | `completed(result, attachment)` or `failed(error, attachment)` callback. |
| `AsynchronousChannelGroup` | Group of channels and associated execution resources. |

This is a useful option when the application is already built around a **completion pipeline**, wants callers to issue operations and do other work, or wants file I/O with callbacks/Futures at explicit offsets.

### 6.1. Future Does Not Make Waiting Code Disappear

~~~java
try (AsynchronousSocketChannel client =
        AsynchronousSocketChannel.open()) {

    client.connect(remote).get(5, TimeUnit.SECONDS);

    ByteBuffer data = ByteBuffer.allocate(256);
    Future<Integer> operation = client.read(data);
    int n = operation.get(5, TimeUnit.SECONDS);
}
~~~

Illustrative snippet requiring a valid `remote` and imports for `AsynchronousSocketChannel`, `ByteBuffer`, `Future`, and `TimeUnit`. **`get(...)` still blocks the caller while waiting**; the underlying `read` method is issued asynchronously.

When the Future completes, `n` is **the actual bytes received**, not `data.capacity()` by default. `n == -1` signals EOF; `n == 0` does not mean a message is complete.

### 6.2. CompletionHandler Truly Organizes Flow Around Callbacks

~~~java
ByteBuffer input = ByteBuffer.allocate(1024);

channel.read(input, input,
        new CompletionHandler<Integer, ByteBuffer>() {
    @Override
    public void completed(Integer n, ByteBuffer buffer) {
        if (n == -1) {
            closeConnection();
            return;
        }
        if (n > 0) {
            buffer.flip();
            processAvailableBytes(buffer);
            buffer.compact();
        }
        // If continuation is needed, issue the next read.
    }

    @Override
    public void failed(Throwable error, ByteBuffer buffer) {
        reportFailure(error);
        closeConnection();
    }
});
~~~

This is **integration pseudocode**, not standalone Java; `channel`, `closeConnection`, `processAvailableBytes`, and `reportFailure` must be defined by the application.

Input/output state and buffers must remain alive at least until completion finishes. Do not allow another thread to modify the position/limit of a buffer currently used by an operation. Handlers are usually invoked via the provider/channel group's execution mechanism; avoid long CPU work or blocking inside handlers.

### 6.3. Asynchronous File I/O

~~~java
try (AsynchronousFileChannel file =
        AsynchronousFileChannel.open(path, StandardOpenOption.READ)) {

    ByteBuffer target = ByteBuffer.allocate(4096);
    Future<Integer> op = file.read(target, 0L);
    int n = op.get();
}
~~~

This is an illustrative snippet requiring a valid `path` and corresponding imports. `AsynchronousFileChannel.read(dst, position)` takes an **explicit file position** for each operation. This differs from using a shared file position on `FileChannel`; operations may complete out of initiation order. Do not treat an earlier callback arrival as proof that a lower byte offset finished writing first.

Implementations of asynchronous file I/O may use a thread pool; do not assume it is kernel-native async or faster than every blocking `FileChannel`.

## 7. Workload-Based Decision Tree

~~~text
Start
   |
   +-- Is I/O primarily file reading/writing?
   |     |
   |     +-- Sequential and simple -> Files / blocking FileChannel
   |     |
   |     +-- Multiple independent offsets / need completion?
   |             -> AsynchronousFileChannel
   |
   +-- Is I/O many TCP sockets?
         |
         +-- Low/moderate count, linear logic, easy maintenance?
         |       -> Blocking SocketChannel
         |
         +-- Many idle sockets, need a readiness event loop?
         |       -> Non-blocking SocketChannel + Selector
         |
         +-- System structured around callbacks/completion?
                 -> AsynchronousSocketChannel
~~~

A design can **combine** approaches: a selector managing the network, a worker pool handling CPU tasks, `AsynchronousFileChannel` for offset-based file work, and blocking APIs for small operations outside the event loop. You do not need to force every call in an application into a single API style.

Scenario table:

| Scenario | Starting Choice | Reason |
| --- | --- | --- |
| CLI program generating reports from small files | Blocking `Files` or `FileChannel` | Async state overhead outweighs benefits. |
| A client calling a few TCP services | Blocking `SocketChannel` | Clear request-response flow, easy to debug. |
| Gateway with very many idle connections | Selector or proven event-driven framework | Many sockets monitored by few I/O threads. |
| Callback-first network application | `AsynchronousSocketChannel` | Completion-driven flow, caller need not wait. |
| Processing multiple file regions at distinct offsets | `AsynchronousFileChannel` or worker pool | Can overlap tasks, though ordering must be handled. |
| Server performing heavy CPU compression/encryption | Separate worker executor | Selector does not parallelize CPU work on its own. |
| Linear blocking-style I/O with high concurrency on Java 21+ | Virtual threads are a candidate | Still requires capping sockets and downstream resources. |
| File needing consistent snapshots while another writer updates it | Versioning, transactions, snapshots | Changing I/O APIs does not create consistency automatically. |

## 8. Runnable Java 17+ Example: Same PING/PONG Using All Three Models

The example runs **one blocking loopback TCP server** serving three connections, each time receiving `PING` and sending `PONG`. All three clients run sequentially so stdout has a deterministic order:

- Client 1: blocking `SocketChannel`.
- Client 2: non-blocking `SocketChannel` + `Selector`, transitioning `OP_CONNECT → OP_WRITE → OP_READ`.
- Client 3: `AsynchronousSocketChannel` with Future and `get(timeout)`. Because `get` is called, the main thread still awaits completion.

The code does not assume a single `read/write` transfers all four bytes and includes timeouts to avoid infinite waits in the selector/Future clients.

Save as `IoModelChoiceDemo.java`:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.net.SocketTimeoutException;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class IoModelChoiceDemo {

    private static final byte[] REQUEST =
            "PING".getBytes(StandardCharsets.US_ASCII);

    static void sendBlocking(SocketChannel channel, ByteBuffer src)
            throws IOException {
        while (src.hasRemaining()) {
            if (channel.write(src) == 0) {
                throw new IOException("Blocking write không tiến triển");
            }
        }
    }

    static void receiveBlocking(SocketChannel channel, ByteBuffer dst)
            throws IOException {
        while (dst.hasRemaining()) {
            int n = channel.read(dst);
            if (n == -1) {
                throw new EOFException("EOF trước khi đủ dữ liệu");
            }
            if (n == 0) {
                throw new IOException("Blocking read không tiến triển");
            }
        }
    }

    static String decode(ByteBuffer data) {
        data.flip();
        return StandardCharsets.US_ASCII.decode(data).toString();
    }

    static String blockingClient(SocketAddress address)
            throws IOException {
        try (SocketChannel client = SocketChannel.open(address)) {
            sendBlocking(client, ByteBuffer.wrap(REQUEST));
            ByteBuffer reply = ByteBuffer.allocate(4);
            receiveBlocking(client, reply);
            return decode(reply);
        }
    }

    static String selectorClient(SocketAddress address)
            throws IOException {
        try (Selector selector = Selector.open();
             SocketChannel client = SocketChannel.open()) {

            client.configureBlocking(false);
            boolean connectedNow = client.connect(address);
            client.register(selector, connectedNow
                    ? SelectionKey.OP_WRITE
                    : SelectionKey.OP_CONNECT);

            ByteBuffer outgoing = ByteBuffer.wrap(REQUEST);
            ByteBuffer incoming = ByteBuffer.allocate(4);
            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(5);

            while (incoming.hasRemaining()) {
                long remainingNanos = deadline - System.nanoTime();
                if (remainingNanos <= 0) {
                    throw new SocketTimeoutException("Selector deadline");
                }
                long timeoutMs = Math.max(1,
                        TimeUnit.NANOSECONDS.toMillis(remainingNanos));

                if (selector.select(timeoutMs) == 0) {
                    continue;
                }
                Iterator<SelectionKey> it =
                        selector.selectedKeys().iterator();

                while (it.hasNext()) {
                    SelectionKey key = it.next();
                    it.remove();
                    if (!key.isValid()) {
                        continue;
                    }

                    if (key.isConnectable()) {
                        if (client.finishConnect()) {
                            key.interestOps(SelectionKey.OP_WRITE);
                        }
                    } else if (key.isWritable()) {
                        client.write(outgoing);
                        if (!outgoing.hasRemaining()) {
                            key.interestOps(SelectionKey.OP_READ);
                        }
                    } else if (key.isReadable()) {
                        int n = client.read(incoming);
                        if (n == -1) {
                            throw new EOFException("Selector EOF sớm");
                        }
                    }
                }
            }
            return decode(incoming);
        }
    }

    static String asyncClient(SocketAddress address)
            throws Exception {
        try (AsynchronousSocketChannel client =
                AsynchronousSocketChannel.open()) {

            client.connect(address).get(5, TimeUnit.SECONDS);

            ByteBuffer outgoing = ByteBuffer.wrap(REQUEST);
            while (outgoing.hasRemaining()) {
                int n = client.write(outgoing).get(5, TimeUnit.SECONDS);
                if (n == 0) {
                    throw new IOException("Async write không tiến triển");
                }
            }

            ByteBuffer incoming = ByteBuffer.allocate(4);
            while (incoming.hasRemaining()) {
                int n = client.read(incoming).get(5, TimeUnit.SECONDS);
                if (n == -1) {
                    throw new EOFException("Async EOF sớm");
                }
                if (n == 0) {
                    throw new IOException("Async read không tiến triển");
                }
            }
            return decode(incoming);
        }
    }

    static void serveThree(ServerSocketChannel server)
            throws IOException {
        for (int i = 0; i < 3; i++) {
            try (SocketChannel peer = server.accept()) {
                ByteBuffer request = ByteBuffer.allocate(4);
                receiveBlocking(peer, request);

                if (!"PING".equals(decode(request))) {
                    throw new IOException("Request không hợp lệ");
                }

                ByteBuffer answer = ByteBuffer.wrap(
                        "PONG".getBytes(StandardCharsets.US_ASCII));
                sendBlocking(peer, answer);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));

            SocketAddress address = server.getLocalAddress();
            ExecutorService executor =
                    Executors.newSingleThreadExecutor();

            try {
                Future<?> serving = executor.submit(() -> {
                    try {
                        serveThree(server);
                    } catch (IOException e) {
                        throw new RuntimeException(e);
                    }
                });

                String blocking = blockingClient(address);
                String selector = selectorClient(address);
                String async = asyncClient(address);

                serving.get(5, TimeUnit.SECONDS);

                System.out.println("blocking=" + blocking);
                System.out.println("selector=" + selector);
                System.out.println("async=" + async);
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Compile and run commands on JDK 17 or later:

~~~bash
javac IoModelChoiceDemo.java
java IoModelChoiceDemo
~~~

**Expected stdout** when the environment allows opening TCP sockets on loopback:

~~~text
blocking=PONG
selector=PONG
async=PONG
~~~

Explanation:

1. The server binds loopback on port 0 (OS-chosen), and a single executor thread accepts the three clients in turn.
2. `blockingClient` performs `sendBlocking`/`receiveBlocking` in the same flow, still looping until all 4 bytes arrive.
3. `selectorClient` manages connection state manually. If `connect` has not finished, it waits for `OP_CONNECT` and calls `finishConnect`; next it sends PING on `OP_WRITE` and reads PONG on `OP_READ`. Unprocessed bytes remain in the `ByteBuffer`.
4. `asyncClient` issues `connect`, `write`, and `read`, receiving completion counts via Future. In this example the caller invokes `get` with a timeout, so it still waits to keep the illustrative flow simple.
5. Each client finishes in sequence before printing results. The server always replies PONG upon receiving PING, so the three lines are deterministic.

**This example is not a benchmark.** It simply places three API styles side by side over the same protocol. The server serves only three tiny requests and does not represent thousands of connections under load. Performance evaluation requires realistic workloads measuring throughput, P95/P99, CPU, RAM, and timeout errors.

## 9. Partial I/O and Buffer State: Shared Risks

All three models must manage `ByteBuffer.position()`, `limit()`, and `remaining()` accurately:

~~~text
Buffer holds 8 bytes A B C D E F G H, position=0 limit=8
write #1 returns 3 -> position=3, remaining=5
write #2 returns 2 -> position=5, remaining=3
write #3 returns 3 -> position=8, remaining=0
Only now are all outbound bytes truly sent.
~~~

- **Blocking:** loop writing until finished, or handle errors/timeouts.
- **Selector:** if a non-blocking write returns `0`, retain the buffer and wait for `OP_WRITE`; on a partial write, do not `flip()` or `clear()` mistakenly.
- **Async:** after completion, inspect the actual `n` bytes transferred; issue the next operation if data remains. Never mutate a buffer while the previous operation is using it.

On reads, when reading a length-prefixed protocol, the 4-byte header can arrive across multiple reads. A parser state machine or accumulation until complete is required. TCP is a byte stream and **does not preserve boundaries between the sender's write calls**.

## 10. Timeouts, Cancellation, and Backpressure

### 10.1. Timeouts Must Not Be Guessed

Define limits for **connect**, **reading a frame**, **writing a response**, **idle time**, and **total request duration**. For example, `selector.select(5_000)` only bounds a single readiness wait; it does not create an overall request timeout. Track cumulative deadlines with something like `System.nanoTime()`.

`Future.get(timeout)` only bounds **the caller's wait duration**; when it throws `TimeoutException`, do not assume the operation was canceled. Close the socket or perform controlled cancellation, preventing late callbacks from processing data for an abandoned request.

### 10.2. Cancellation and Cleanup

When a client gives up, an issued I/O operation may still be unfinished. Define states such as OPEN, CLOSING, and CLOSED; close resources and discard pending buffers per policy; failure callbacks/futures must be handled **idempotently**, never closing or completing a request multiple times.

A `CompletionHandler` may execute on a thread managed by the implementation. If a callback invokes a long blocking method, other completions may be delayed. Offload heavy tasks to an appropriate worker pool or pipeline.

### 10.3. Backpressure

Suppose the application generates responses many times faster than the client reads them: the outbound queue grows and can exhaust RAM.

- Blocking: cap workers, queued requests, and send duration; never allow unbounded queue growth.
- Selector: enable `OP_WRITE` only when bytes are waiting; optionally pause `OP_READ` or close sockets when queues exceed thresholds.
- Async: cap in-flight operations and memory held by callbacks/Futures; while one write is unfinished, do not arbitrarily stack unbounded queued writes.

No API provides business-level backpressure automatically unless the application defines explicit limits.

## 11. When Should You Combine Multiple Models?

A system can use a Selector for networking while keeping a worker pool for blocking or CPU-heavy tasks:

~~~text
Selector thread                        Worker pool
      |                                     |
      +-- read/parse request                |
      +-- submit job ---------------------->|
      |   serve other sockets               +-- execute business logic
      |<------------ result via queue ------+
      +-- selector.wakeup()
      +-- push response to output queue
      +-- enable OP_WRITE
~~~

Here the queue must be thread-safe. Ideally only the event-loop thread owns and updates per-connection buffers/attachments; workers return immutable results or messages for the loop to process. `selector.wakeup()` wakes up select, **not meaning the socket naturally became ready**.

If the task involves `AsynchronousFileChannel`, you can receive a Future/callback and pass the result to the event loop. Still, combining models must never bypass ownership, cancellation, or write ordering.

## 12. Common Mistakes When Choosing an API

| Mistake | Consequence / Fix |
| --- | --- |
| Assuming asynchronous is always faster than blocking | Measure the workload: scheduling, callbacks, pools, and buffers all have costs. |
| Using Selector for a regular FileChannel | `FileChannel` is not selectable; use `FileChannel` or `AsynchronousFileChannel`. |
| Using Future, calling `get` immediately, and claiming the caller is non-blocking | `get` can block; non-blocking callers need proper completion/callbacks. |
| Putting all sockets on one event loop and doing CPU-heavy work in callbacks | One slow callback stalls other sockets; offload heavy work to a pool. |
| Using one ByteBuffer for multiple concurrent async operations | Risk of position/limit races; enforce clear ownership and release timing. |
| Ignoring read/write byte counts thinking blocking guarantees everything | Partial I/O still occurs; check `remaining()` and EOF. |
| Calling `clear()` after an incomplete non-blocking write | Loses unsent bytes; keep buffer and wait for OP_WRITE. |
| Keeping OP_WRITE in interestOps when the output queue is empty | Loop may wake continuously; enable only when data exists. |
| Thinking `Future.get(timeout)` definitely canceled the I/O | Timeout only reports the caller waited too long; cancel/close explicitly. |
| Failing to limit connections, queues, or memory | Any model can exhaust resources. |
| Assuming Java 17 has standard virtual threads | Official feature begins in Java 21. |
| Using the same choice for sockets, files, DB, and CPU | Different resource types have different APIs and costs; combining them is valid. |

## 13. Task-Based Selection Checklist

Answer these questions before implementing:

1. **Resource type?** TCP, UDP, file, database, pipe, or CPU? Selectors apply only to selectable channels.
2. **How many concurrent connections?** Do not measure only requests per second while ignoring idle sockets.
3. **How much time is spent waiting on I/O versus CPU processing?** Event loops excel particularly with brief callbacks.
4. **Which Java version?** On Java 17 use the three standard models; on Java 21+ also consider virtual threads.
5. **Latency and throughput requirements?** Measure P95/P99, not just averages.
6. **Are completion callbacks truly needed?** If not, blocking may be sufficient and simpler.
7. **Is there a state machine for framing and partial reads/writes?** Every API must preserve protocol correctness.
8. **Are timeouts, cancellation, and closing defined?** Never let requests or in-flight operations linger indefinitely.
9. **Who owns buffers and connections?** Avoid races when callbacks/workers update concurrently.
10. **Are output queues and in-flight operations bounded?** This is the foundation of backpressure.
11. **Have you load-tested slow clients, EOF, disconnects, and network failures?** Ideal loads often hide bugs.
12. **Do you truly need an architectural change?** If a simple approach meets SLOs, a complex model's benefit should be proven with data.

## 14. Self-Check Questions

1. **A CLI reads a small file and writes a result—does it need a Selector?** Usually no. Blocking `Files` or `FileChannel` is simpler.
2. **A gateway has very many TCP sockets waiting for data—which models merit consideration?** Selector or async sockets, with benchmarking and resource limits.
3. **What does `Selector.isReadable` report?** Readiness to attempt reading; it does not promise a complete message.
4. **With an asynchronous Future, can calling `get()` block the caller?** Yes.
5. **Can `AsynchronousFileChannel` register OP_READ with a Selector?** No; it is a completion API for files.
6. **Does a read completion receiving 2 of 4 header bytes complete the protocol?** No, you must keep reading or handle EOF/errors.
7. **Is a non-blocking write returning 0 definitely an error?** No; it may temporarily not be writable.
8. **When should `OP_WRITE` be enabled?** When data is waiting to send and writability must be awaited; disable when finished.
9. **Does a single-threaded loop parallelize CPU tasks automatically?** No.
10. **Does a `Future.get` timeout automatically cancel a socket operation?** Not guaranteed; cancel/close policies are needed.
11. **Why isn't `AsynchronousFileChannel` necessarily faster than blocking `FileChannel`?** The provider may use a thread pool; workload and overhead decide.
12. **If a system needs data consistency, does switching to async solve transactions?** No; consistency/transactions belong to the protocol or storage layer.

## 15. Java 17 Reference Documentation

- [SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): blocking/non-blocking, connect/read/write.
- [Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html) and [SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): readiness/interest operations.
- [AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): Future and completion handlers for TCP.
- [AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): file I/O with explicit offsets.
- [CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): operation success or failure results.

**Key takeaway:** **Blocking** optimizes simplicity of sequential flow; **Selector** optimizes coordinating many selectable channels by readiness with an event loop; **AsynchronousChannel** delivers completion via Future/callbacks. Choose based on workload, JDK version, state-management capability, and SLOs; all three must solve partial I/O, timeouts, cancellation, buffer lifetimes, and backpressure.
