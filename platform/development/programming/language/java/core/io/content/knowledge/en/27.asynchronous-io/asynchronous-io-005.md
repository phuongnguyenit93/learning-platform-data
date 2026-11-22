# AsynchronousChannelGroup and Execution Thread Pools in Java NIO.2

**`AsynchronousChannelGroup`** is the mechanism for grouping **asynchronous socket channels** in Java NIO.2 to share I/O processing resources and an **execution thread pool**. The group manages the work required to detect, complete, and deliver the results of asynchronous operations to `CompletionHandler`. As a result, a program can initiate an I/O operation and continue doing other work instead of having to keep a thread waiting for every connection.

However, the following three concepts are **not synonymous**:

- *Asynchronous I/O*: an operation is initiated and its result arrives later via `Future` or `CompletionHandler`.
- *Thread pool*: where tasks servicing I/O processing and callbacks execute; **there is not necessarily a dedicated thread per connection**.
- *Non-blocking Selector*: a different `Selector`/`SocketChannel` model, where the application actively reads/writes channels based on readiness events.

Understanding `AsynchronousChannelGroup` properly helps manage server resources, avoid stalling the thread pool when callbacks run heavy work, avoid shutting down the group while requests remain active, and avoid confusing it with `AsynchronousFileChannel`'s `ExecutorService`.

## 1. Primary Role of AsynchronousChannelGroup

`AsynchronousChannelGroup` belongs to the `java.nio.channels` package (Java 7 and later). It is an abstract class representing **a group of asynchronous channels sharing a processing mechanism**. A group has an associated thread pool to:

1. Service the events/tasks required for asynchronous I/O on channels bound to the group.
2. Dispatch completion or failure results to `CompletionHandler`.
3. Manage the lifecycle of I/O resources, channels, and the group's thread pool.

**A group is not a connection, does not transfer bytes, does not define a protocol on its own, and is not a single dedicated thread.** Each `AsynchronousSocketChannel`/`AsynchronousServerSocketChannel` still represents a specific endpoint with its own state; the group is the infrastructure serving multiple endpoints.

### Visualizing the Relationship

```text
                          AsynchronousChannelGroup
                        +--------------------------+
                        | Thread pool / I/O tasks  |
                        | completion dispatch      |
                        +-------------+------------+
                                      |
            +-------------------------+-------------------------+
            |                         |                         |
   AsynchronousServerSocketChannel   AsynchronousSocketChannel  AsynchronousSocketChannel
          accept(...)                 read/write/connect       read/write/connect
            |                         |                         |
            +------------+------------+------------+------------+
                         |
                 Future / CompletionHandler
                         |
              Results, errors, business processing
```

The diagram depicts **logical relationships**, not a promise that the OS always uses one fixed thread to handle a given operation. Implementations may use native asynchronous I/O or simulate it with background tasks; Java defines an API contract for completion, without promising a uniform kernel I/O mechanism across every OS.

## 2. Which Channels Actually Bind to a Group?

| Channel Type | Can Bind to `AsynchronousChannelGroup`? | How It Associates |
| --- | --- | --- |
| `AsynchronousSocketChannel` | **Yes** | `AsynchronousSocketChannel.open(group)` or `open()` uses the default group. |
| `AsynchronousServerSocketChannel` | **Yes** | `AsynchronousServerSocketChannel.open(group)` or `open()` uses the default group. |
| Socket accepted from an async server | **Yes, via the server's group** | `server.accept(...)` returns a connected channel using the server's group infrastructure. |
| `AsynchronousFileChannel` | **Does not directly take AsynchronousChannelGroup as a parameter** | `open(Path, Set<OpenOption>, ExecutorService, ...)` specifies an executor; or the overload uses the default thread pool. |
| Synchronous `SocketChannel` / `ServerSocketChannel` | **No** | Uses blocking I/O or `Selector`; not an asynchronous channel group. |
| `FileChannel` | **No** | Ordinary synchronous file channel operations, with no group association. |

This is an important distinction when seeing the shared `Asynchronous*` prefix. `AsynchronousFileChannel` is an asynchronous API but **does not have** an `open(group)` overload; it associates with an `ExecutorService` and has no `group()` method. Java may use the same default thread-pool configuration internally, yet does not make file channels direct members of a user-created `AsynchronousChannelGroup`.

Example binding two socket channels to a group:

```java
AsynchronousChannelGroup group =
    AsynchronousChannelGroup.withFixedThreadPool(4,
        runnable -> new Thread(runnable, "nio-aio"));

AsynchronousServerSocketChannel server =
    AsynchronousServerSocketChannel.open(group);
AsynchronousSocketChannel client =
    AsynchronousSocketChannel.open(group);
```

This is an **illustrative snippet**, without `bind`/`connect` or resource cleanup; real applications must close both channels and then shut down the group. You cannot call `SocketChannel.open(group)` because that is a different channel type.

## 3. How Are Groups Created?

Three main factory methods:

| Method | Meaning | Notes |
| --- | --- | --- |
| `withFixedThreadPool(int nThreads, ThreadFactory factory)` | Creates a group with up to `nThreads` worker threads for the group's tasks. | `nThreads` must be positive. The thread factory determines name/daemon/priority; do not set it too low if callbacks do heavy work. |
| `withCachedThreadPool(ExecutorService executor, int initialSize)` | Uses an executor that can create additional threads as needed; `initialSize` is a **hint** to the implementation. | The executor should create threads as needed and may reuse threads. The hint value is not a guarantee of active thread count. |
| `withThreadPool(ExecutorService executor)` | Uses an application-supplied executor for work servicing the group. | The executor should support **direct handoff or an unbounded queue**; the thread calling `execute` should not run tasks directly. Implementations may impose additional constraints. |

All three factories may throw `IOException` if the provider fails to create the group. `withFixedThreadPool` also throws `IllegalArgumentException` if the thread count is invalid.

### Using a Fixed Group

```java
// Illustrative snippet: appropriate imports, called inside a method that throws IOException.
ThreadFactory factory = task -> {
    Thread thread = new Thread(task, "async-io-worker");
    thread.setDaemon(false);
    return thread;
};
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(4, factory);
```

`ThreadFactory` lets you assign names useful when inspecting thread dumps. Using daemon or non-daemon threads must be paired with an explicit shutdown policy; **do not rely on the JVM exiting on its own to release resources**. The number 4 is illustrative, not a universal production formula; measure load and observe how long callbacks take.

**Note on executor ownership:** With `withThreadPool` or `withCachedThreadPool`, the executor **is dedicated** to the group. The Javadoc states that calling `executor.shutdown()` elsewhere while the group is still active results in **undefined** behavior; when the group terminates, it performs an orderly shutdown of the executor. Do not share the same executor with HTTP handlers, business schedulers, or multiple groups without examining the contract. If you supply a custom executor, let the group manage its lifecycle.

## 4. Default Group and JVM Configuration

When no group is passed:

```java
AsynchronousSocketChannel client = AsynchronousSocketChannel.open();
AsynchronousServerSocketChannel server = AsynchronousServerSocketChannel.open();
```

These channels attach to the JVM-wide **default asynchronous channel group**. Java creates the default group automatically; as of Java SE 21, its thread pool creates threads as needed. Without configuring a thread factory for the default group, the default group's pooled threads are **daemon threads**.

Two system properties defined by Java for the default group:

- `java.nio.channels.DefaultThreadPool.threadFactory`: fully qualified class name of a concrete `ThreadFactory` that can be loaded and instantiated.
- `java.nio.channels.DefaultThreadPool.initialSize`: integer value used as the `initialSize` parameter, as in `withCachedThreadPool`; not a fixed thread count.

These properties are JVM configurations, not settings for user-created groups. When developing applications or libraries that share the default group, it is harder to isolate callback impact from other components; when resource isolation is needed for a subsystem, a dedicated group may be appropriate.

Using the default group keeps code concise, yet **does not mean** the entire system lifecycle is managed for you: the program must still close socket channels and track pending tasks. If the only threads keeping the JVM alive are daemon threads, the JVM can exit once no non-daemon threads remain; do not rely on pending callbacks as a mechanism to keep the process alive.

## 5. Which Thread Runs CompletionHandler?

For channels attached to an `AsynchronousChannelGroup`, the Javadoc guarantees **the completion handler is invoked by one of the group's pooled threads**. This gives predictable execution identity at the group level, not a promise that callbacks always run on "thread A" or in request submission order.

For an operation that completes immediately, if the thread that initiated the operation **is already one of the group's pooled threads**, the implementation may invoke the handler **directly on that initiating thread** rather than going through a queue. There may be a limit on nested callback depth to avoid stack overflow.

Example:

```java
socket.read(buffer, requestId,
    new CompletionHandler<Integer, String>() {
        @Override
        public void completed(Integer n, String id) {
            // Callback processing the result; may run on a thread from the group.
        }

        @Override
        public void failed(Throwable error, String id) {
            // Callback invoked when the operation completes with an error.
        }
    });
```

This is an **API illustration**, assuming `socket` is connected, `buffer` is valid, and `requestId` is declared. `Integer n` is the number of bytes read (`-1` can indicate EOF), not an application message count. `attachment` carries caller-supplied context; it is not generated by the JDK.

### Callback Execution Thread vs. Business Logic Thread

Treat callbacks as running on pooled resources that **must be returned quickly**:

- **Suitable:** checking results, updating buffer state, completing a `CompletableFuture`, enqueuing work onto another queue, scheduling the next read when needed.
- **Unsuitable when time-consuming:** running blocking DB queries, making blocking HTTP calls, parsing huge payloads, sleeping, waiting for users, or calling `Future.get()` on work that also needs the same pool.
- **Risk:** a pool with only 2 threads where both callbacks block waiting on another task from the group → processing of other I/O/callbacks can be severely delayed or deadlock due to starvation.

A sound architecture separates **I/O completion dispatch** from the **business executor**:

```text
AsynchronousChannelGroup threads
     |
     | read/write completes
     v
CompletionHandler (very brief)
     |
     | inspect + enqueue
     v
Business Executor / bounded queue
     |
     | validate, parse, DB query, business rules
     v
Result returned → initiate async write
```

Still, the business executor also needs bounded queues and backpressure. Do not offload heavy work from the group by creating unbounded tasks that exhaust heap memory. For network protocols, preserve message/response ordering according to application rules rather than assuming a thread pool executes in submission order.

## 6. Future and CompletionHandler: Two Ways to Receive Results

Both operate on asynchronous socket I/O, yet the way results are retrieved affects scalability:

| Usage | Model | Points to Note |
| --- | --- | --- |
| `Future<V>` | Call `connect` / `accept` / `read` / `write` to obtain a Future; caller can do other work and later call `get` to retrieve the result. | `Future.get()` **blocks the calling thread** if not finished. Do not use inside a callback of the same pool if it depends on another task from that pool. |
| `CompletionHandler<V,A>` | Pass handler/attachment; JDK calls `completed` or `failed` when the operation finishes. | Does not block waiting for results inside callbacks; requires managing state, errors, buffers, concurrency, and lifecycle. |

`Future` **does not mean end-to-end non-blocking** if you call `get()` immediately. It is still an asynchronously initiated API, yet the thread calling `get` waits. In short demos, `get(timeout, unit)` conveniently verifies results; in servers with many connections, completion callbacks or event-driven abstractions are usually more suitable.

An operation can complete with failure. With `Future`, I/O exceptions are typically wrapped in `ExecutionException` on `get`. With callbacks, `failed(Throwable, attachment)` is the error-handling branch. **Do not swallow either** and assume data transferred completely.

## 7. Runnable Java 17+ Example: Group, Future, and Callback

This example opens a TCP loopback server and client **both attached to a single group with 2 threads**. The client writes `PING` using asynchronous write/Future; the server reads until all 4 bytes arrive via `CompletionHandler`. The program waits for completion with a timeout so the demo cannot hang indefinitely.

Save as `AsyncGroupDemo.java`:

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public class AsyncGroupDemo {
    public static void main(String[] args) throws Exception {
        AsynchronousChannelGroup group =
                AsynchronousChannelGroup.withFixedThreadPool(2,
                    task -> new Thread(task, "aio-worker"));
        try {
            InetAddress loopback = InetAddress.getLoopbackAddress();
            try (AsynchronousServerSocketChannel server =
                         AsynchronousServerSocketChannel.open(group)
                             .bind(new InetSocketAddress(loopback, 0));
                 AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open(group)) {
                Future<AsynchronousSocketChannel> accepted = server.accept();
                client.connect(server.getLocalAddress()).get(5, TimeUnit.SECONDS);
                try (AsynchronousSocketChannel peer =
                             accepted.get(5, TimeUnit.SECONDS)) {
                    ByteBuffer outbound = ByteBuffer.wrap(
                            "PING".getBytes(StandardCharsets.US_ASCII));
                    int totalSent = 0;
                    while (outbound.hasRemaining()) {
                        int n = client.write(outbound).get(5, TimeUnit.SECONDS);
                        if (n <= 0) throw new IOException("Write made no progress");
                        totalSent += n;
                    }
                    ByteBuffer inbound = ByteBuffer.allocate(4);
                    CompletableFuture<Integer> done = new CompletableFuture<>();
                    CompletionHandler<Integer, Void> handler = new CompletionHandler<>() {
                        @Override public void completed(Integer n, Void attachment) {
                            if (n < 0) {
                                done.completeExceptionally(
                                        new EOFException("Truncated message"));
                            } else if (inbound.hasRemaining()) {
                                peer.read(inbound, null, this);
                            } else {
                                done.complete(inbound.position());
                            }
                        }
                        @Override public void failed(Throwable error, Void attachment) {
                            done.completeExceptionally(error);
                        }
                    };
                    peer.read(inbound, null, handler);
                    int totalRead = done.get(5, TimeUnit.SECONDS);
                    inbound.flip();
                    System.out.println("sent=" + totalSent);
                    System.out.println("received=" + totalRead);
                    System.out.println("body=" +
                            StandardCharsets.US_ASCII.decode(inbound));
                }
            }
        } finally {
            group.shutdown();
            if (!group.awaitTermination(5, TimeUnit.SECONDS)) {
                group.shutdownNow();
                group.awaitTermination(5, TimeUnit.SECONDS);
            }
        }
    }
}
```

Compile and run commands:

```bash
javac --release 17 AsyncGroupDemo.java
java AsyncGroupDemo
```

Verified output in an environment permitting TCP loopback:

```text
sent=4
received=4
body=PING
```

**Full explanation:**

1. `withFixedThreadPool(2, ...)` creates a group binding the I/O completion infrastructure to two pooled threads; `ThreadFactory` names them. **Thread names are not printed** because callback execution thread order is not a guaranteed contract.
2. `AsynchronousServerSocketChannel.open(group)` and `AsynchronousSocketChannel.open(group)` use the same group. `bind(..., 0)` asks the OS to choose a free port.
3. `server.accept()` returns `Future<AsynchronousSocketChannel>`. Client `connect(...).get(5, ...)` waits for connection establishment, then the accept Future returns the server-side channel. `get` blocks **the main thread**; it does not turn channel I/O into a blocking API.
4. The client writes the `PING` buffer. The `write` loop handles potentially writing **fewer bytes** per call; only after the Future completes is the buffer accessed/written further.
5. Server `read` registers a callback. Upon completing one read, the handler checks EOF and **initiates the next read** if the buffer does not yet have 4 bytes. Because TCP is a stream, never assume one read equals one message.
6. `CompletableFuture done` here serves only as a bridge for **the main thread** to await the entire demo block; the completion handler itself never calls `get`. After `done.get` returns, the buffer has finished being populated; `flip` prepares it for decoding.
7. `try-with-resources` closes the server/client/accepted channels. Finally `group.shutdown()` and `awaitTermination` wait for the group to finish, falling back to `shutdownNow` if the sample deadline expires.

The code simplifies network content to 4 ASCII bytes and a single connection. Real services require framing, size limits, write queues, backpressure, request-wide timeouts, callback error handling, and coordinated shutdown. If the environment restricts socket creation, the program may throw an exception; that is not proof the group API fails to work.

### Limitations of the Example to Understand

- An `AsynchronousSocketChannel` allows multiple threads to use it, yet **at most one pending read and one pending write** on the same channel. Initiating a second read before the old one completes throws `ReadPendingException`; likewise `WritePendingException` for writes. The code schedules the next read inside the callback to avoid overlap.
- `read` can return `-1` if the peer closes its write side; the handler treats that as truncated data if fewer than 4 bytes arrived. Production code needs parser rules for valid EOF.
- `CompletableFuture` serves as the coordination layer in the example, not a replacement for the group; both executor/thread layers still have distinct responsibilities.
- `awaitTermination(5,...)` is a demo duration. Real systems need grace periods, cancellation policies, and tracking of in-flight requests.

## 8. Constraints on Pending Operations and Buffers

Async does not permit arbitrary multi-threaded buffer access.

### One Pending Read and One Pending Write per Async Socket

`AsynchronousSocketChannel` can concurrently have **one read and one write** pending. However, two concurrent pending reads or two concurrent pending writes on the same socket will be rejected via the corresponding exception. This requires per-connection state:

```text
READ_IDLE --start read--> READ_PENDING --completed/failed--> READ_IDLE
WRITE_IDLE --start write--> WRITE_PENDING --completed/failed--> WRITE_IDLE
```

If multiple messages must be sent, place them in an outbound queue and initiate the next write only after the previous operation completes; partially sent data must resume from the current `ByteBuffer.position`. When queues grow large, apply backpressure or queue limits instead of spawning unbounded Futures hoping the group preserves order automatically.

### Buffers Should Not Be Mutated While Operations Are Pending

**Incorrect** example:

```java
ByteBuffer buffer = ByteBuffer.wrap(payload);
socket.write(buffer); // async write is not guaranteed to be finished yet
buffer.clear();        // WRONG: mutates buffer state while I/O is still pending
```

This is only an illustrative snippet; `payload` and `socket` are assumed to exist. By contract, after initiating an asynchronous operation, do not access or mutate the associated buffer until the operation completes. If a socket API times out and the implementation does not guarantee how many bytes were processed, the buffer state after timeout may be **undefined**; apply a cancellation/closing policy and do not arbitrarily retry on that buffer.

For protocols with large frames, preserve strict buffer ownership across callbacks; never pass the same buffer to two pending operations. **A group thread pool does not automatically make ByteBuffer thread-safe.**

## 9. AsynchronousFileChannel Uses ExecutorService, Not Group Directly

`AsynchronousFileChannel` also supports `Future` and `CompletionHandler`, but has no **current file position**; every `read/write` takes an explicit offset. It allows **multiple outstanding read/write operations** on the same file channel, though operation and callback order **is not guaranteed** to match initiation order. Buffers used for pending I/O must not be carelessly shared.

Characteristic factory:

```java
AsynchronousFileChannel.open(
    path,
    Set.of(StandardOpenOption.READ, StandardOpenOption.WRITE),
    executor);
```

The snippet above is illustrative; `path` and `executor` already exist. `executor` is an `ExecutorService` servicing operations/dispatch for this file channel. **Do not pass `AsynchronousChannelGroup` to the overload** because Java defines no such signature. The `AsynchronousFileChannel.open(path, options...)` overload uses the environment's default thread pool.

### Java 17+ Example: Async File with Dedicated Executor

Save as `AsyncFilePoolDemo.java`:

```java
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;

public class AsyncFilePoolDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("async-file-", ".dat");
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            try (AsynchronousFileChannel channel = AsynchronousFileChannel.open(
                    file, Set.of(StandardOpenOption.READ, StandardOpenOption.WRITE),
                    executor)) {
                ByteBuffer payload = ByteBuffer.wrap(
                        "DATA".getBytes(StandardCharsets.US_ASCII));
                int written = channel.write(payload, 0).get(5, TimeUnit.SECONDS);
                ByteBuffer target = ByteBuffer.allocate(4);
                int read = channel.read(target, 0).get(5, TimeUnit.SECONDS);
                target.flip();
                System.out.println("file-written=" + written);
                System.out.println("file-read=" + read);
                System.out.println("file-data=" +
                        StandardCharsets.US_ASCII.decode(target));
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac --release 17 AsyncFilePoolDemo.java
java AsyncFilePoolDemo
```

Verified output on local filesystem:

```text
file-written=4
file-read=4
file-data=DATA
```

Here `ExecutorService` is used directly rather than **creating an `AsynchronousChannelGroup`**. Both Futures are `get`-awaited to confirm completion before reusing buffers or reading results. Small 4-byte file contents make output stable in testing, yet **the API still permits short reads/writes**; when implementing for large files, loop by actual bytes processed and maintain exact offsets.

Unlike how a group **owns the executor** passed to `withThreadPool`, the executor in the file example is created by the application and actively shut down by the application **after the channel is closed**. Do not mix lifecycles across APIs. On large files, coordinating multiple operations at the same offset can corrupt logical records without an overlap-avoidance protocol, even though each individual call is valid.

## 10. AsynchronousChannelGroup Lifecycle: shutdown, shutdownNow, termination

`AsynchronousChannelGroup` **does not implement AutoCloseable**; do not use `try (AsynchronousChannelGroup group = ...)` as with socket channels. Manage the group via five states/methods:

| API | Main Meaning | Do Not Infer |
| --- | --- | --- |
| `isShutdown()` | Whether the group has been marked for shutdown. | Does not mean all channels have closed. |
| `shutdown()` | Initiates **orderly shutdown**: prevents creating new channels bound to the group. | **Does not** automatically close open channels or cancel running callbacks. |
| `shutdownNow()` | Initiates shutdown and closes all open channels in the group. | Does not attempt to interrupt executing callbacks; tasks may fail due to closed channels. |
| `awaitTermination(timeout, unit)` | Waits for the group to finish or for the timeout to expire. | Not a method that initiates shutdown; the wait may expire before the group terminates. |
| `isTerminated()` | Confirms the group has terminated. | Not a signal that "every request committed" if the application does not track state itself. |

According to the Javadoc, once `shutdown` has been called:

- Attempting to create another channel bound to the group throws `ShutdownChannelGroupException`.
- **The group terminates only when** all asynchronous channels in the group are closed, all currently executing completion handlers have finished, and group resources are released.
- `shutdown` **does not** attempt to stop or interrupt threads executing callbacks.
- `shutdownNow` closes open channels, but **likewise does not** interrupt currently executing callbacks; hence do not treat it as a guaranteed hard kill/timeout.

### Safe Shutdown Sequence

```text
Mark server as no longer accepting new requests
       |
Stop registering new operations / close server accept endpoint
       |
Wait for or cancel in-flight requests per policy
       |
Close client sockets / server socket belonging to the group
       |
group.shutdown()
       |
group.awaitTermination(gracefulTimeout, unit)
       |
If not stopped yet: group.shutdownNow(); monitor results/timeout
       |
Report completion only when business state and resources have been handled
```

`shutdownNow` may throw `IOException` if closing a channel fails. `awaitTermination` may throw `InterruptedException`; follow proper interruption policy rather than ignoring it and claiming termination. Callbacks invoked while channels are closing may receive failures; ensure completion signaling and cleanup occur in error branches too.

**Common shutdown deadlock:** a callback waits on a `CountDownLatch` that will only be released by another task also needing a group thread, or a coordinating thread closes the group and waits for a callback that is never permitted to run. Avoid blocking waits on group threads and build cancellation/outstanding-work tracking into the design.

### Group Ownership

Multiple modules in a system can share one group to reduce overhead, yet if module A calls `shutdownNow` while module B still holds sockets in that group, module B is affected too. Only the **group owner** should be allowed to shut it down; libraries receiving a group from a caller should only close the channels they own, unless the API contract specifies otherwise.

If you want fault/latency isolation between subsystems, use separate groups per I/O class or keep callbacks lightweight. However, creating a new group for **every connection** adds threads/resources and defeats resource sharing—usually inappropriate.

## 11. Sizing the Pool Appropriately

**No Java API formula guarantees the optimal thread count.** When choosing fixed vs. cached, analyze:

- Concurrent connections and pending operations; they **do not** equal the number of threads needed.
- How the JDK/provider processes I/O events and dispatches callbacks, and callback completions per second.
- How long callbacks run and whether any blocking occurs.
- Whether a separate business thread pool exists and whether queues are bounded with backpressure.
- Network throughput, latency requirements, CPU cores, GC, socket memory, and other resource pressures.
- OS, JDK version/provider, file descriptor limits, and behavior under load.

### Fixed Thread Pool

Pros: easy to cap workers servicing the group, easy to measure saturation, clear thread factory setup. Cons: if callbacks are slow or blocking, the entire group can run out of workers. Increasing `nThreads` does not fix logic deadlocks or missing backpressure; raising it indefinitely also adds overhead.

### Cached Thread Pool

Pros: can spawn extra threads when needed, suiting certain workload/provider profiles. Cons: requires application-level load limits because unbounded thread/queue growth can consume substantial memory and cause latency jitter. `initialSize` is a hint, **not** a guarantee of creating that exact initial thread count.

### Custom ExecutorService

Pros: control over ThreadFactory, instrumentation, and configuration policies. Cons: must obey `withThreadPool` constraints. The Javadoc requires supporting **direct handoff or an unbounded queue**, and the thread calling `execute` must not run the task directly. Therefore **do not** blindly pass an executor with a bounded queue + `CallerRunsPolicy` to `withThreadPool`; under overload, `CallerRunsPolicy` can pull the dispatching/initiating thread into executing work in violation of the contract. Use a separate bounded business queue for backpressure without breaking the group's dispatch assumptions.

**Useful metrics to observe:** open socket count, active/pending callbacks, callback duration, outbound queue lengths, timeout/exception counts, graceful shutdown duration, thread dumps, and CPU utilization. Measure throughput and tail latency on the exact deployment JDK/OS.

## 12. Distinguishing AsynchronousChannelGroup from Selector / CompletableFuture / Virtual Threads

| Tool | Responsibility | Key Difference |
| --- | --- | --- |
| `AsynchronousChannelGroup` | Resource sharing, I/O completion processing, completion dispatch for async socket channels. | Not an API that reads/writes directly; a group does not represent a connection. |
| `AsynchronousSocketChannel` | Initiates async connect/read/write, receives `Future` or `CompletionHandler`. | Sockets can belong to a user-created group or the default group. |
| `SocketChannel` + `Selector` | Readiness-based non-blocking I/O actively coordinated by an event loop. | Read/write operations are still **actively called by the application** after readiness. |
| `ExecutorService` | General task execution; can act as a group's resource pool or serve async file I/O. | An executor alone does not create asynchronous I/O semantics for network sockets. |
| `CompletableFuture` | Composes asynchronous task results. | Does not create a group itself; can receive results from callbacks. |
| Virtual threads (Java 21+) | Allows writing blocking-style control flow with lower thread cost in many I/O workloads. | A different programming model; not synonymous with AsynchronousChannelGroup. |

**Do not pick a group simply because you want "many connections."** Weigh three common architectures:

1. Blocking network I/O with existing infrastructure, or virtual threads when using a supporting JDK and suitable problem.
2. Non-blocking `SocketChannel` + `Selector` when direct control over an event loop and readiness is desired.
3. `AsynchronousSocketChannel` + `AsynchronousChannelGroup` when you want to initiate I/O and receive completion via callbacks/Future.

Every choice must still solve TCP framing, short reads/writes, timeouts, TLS, authentication, error handling, and backpressure at the appropriate layer. A group does not eliminate those responsibilities.

## 13. Common Pitfalls and How to Fix Them

| Pitfall | Consequence | Correct Design |
| --- | --- | --- |
| Creating an `AsynchronousChannelGroup` per connection. | Extra threads and resource overhead; hard to shut down. | One shared group per subsystem with clear ownership. |
| Calling `Thread.sleep` or slow DB queries in callbacks. | Completion pool stalls/starves, latency spikes. | Keep callbacks brief; offload heavy work to another executor with a bounded queue. |
| Calling `Future.get()` inside a callback to wait on a task that also needs the group. | Possible deadlock or pool starvation. | Compose asynchronously, chain callbacks, or move waiting elsewhere. |
| Running two concurrent reads on the same socket. | `ReadPendingException`. | Track per-connection state: at most one pending read. |
| Running two concurrent writes on the same socket. | `WritePendingException`. | Write queue; issue next write after previous completes. |
| Mutating `ByteBuffer` while operation is unfinished. | Data/position races, unreliable results. | Buffer ownership rules; access only after completion. |
| Assuming `read` receives a full TCP frame. | Broken parser when data arrives in chunks. | Accumulate bytes and apply protocol framing. |
| Calling `group.shutdown()` while leaving sockets open. | `awaitTermination` may wait forever or time out. | Close all channels in the group and wait for callbacks to finish. |
| Calling `shutdownNow` and assuming callbacks are definitely interrupted. | Callbacks keep running, potentially accessing business resources. | Design cancellation/cooperative stop, close channels, and await. |
| Calling `executor.shutdown()` manually on an executor currently used by a group. | Undefined behavior per Javadoc. | Let the group own and shut down its executor. |
| Calling `AsynchronousFileChannel.open(path, group)`. | No such overload; compilation error. | Use `open(path, options, ExecutorService)` for async files. |
| Observing one callback on a certain thread and assuming all callbacks stay on that thread. | Scheduling-dependent, concurrency bugs. | Rely only on the group's pooled-thread guarantee, never specific thread IDs. |
| Treating buffer as immediately safe to reuse after `get(timeout)` expires. | Operation may still be running; buffer in use. | Verify completion/cancel semantics, close channel when needed, handle per-API timeouts. |

### Notable Exceptions to Recognize

- `ShutdownChannelGroupException`: attempting to create a new channel bound to an already-shutdown group.
- `ReadPendingException` / `WritePendingException`: previous same-direction operation has not completed on an asynchronous socket.
- `AcceptPendingException`: attempting to initiate a new accept while the previous accept is still pending on the same server channel.
- `ExecutionException`: `Future.get` wrapper around a failed I/O cause.
- `TimeoutException`: thread waiting on a Future did not receive a result within the requested duration; **does not mean underlying I/O was canceled**.
- `AsynchronousCloseException` / `ClosedChannelException`: channel was closed or is no longer valid for the operation.
- `InterruptedByTimeoutException`: timeout exceeded in timed async socket read/write overloads; Javadoc warns buffer/connection state may be undefined in some cases.

Do not turn every exception into "retry immediately." When a network disruption occurs, it is uncertain how many bytes the peer application already processed. Protocols with business side effects require framing and dedicated idempotency/acknowledgment.

## 14. Implementation Checklist and Self-Check

### Checklist

1. **Clarify channel type:** async socket or async file? Only socket channels bind directly to `AsynchronousChannelGroup`.
2. **Choose group:** default group for simplicity; explicit group when bounding/isolation and lifecycle control are needed.
3. **Choose factory:** fixed, cached, or custom executor based on workload and Javadoc constraints.
4. **Pool ownership:** for user-created groups, the group shuts down its pooled executor; do not shut it down from other modules.
5. **Keep callbacks short:** avoid waiting on locks/DB/blocking network inside pooled threads whenever possible.
6. **Buffer ownership:** do not reuse/modify buffers while I/O is pending; manage per-connection state.
7. **Limit pending operations:** each async socket gets at most one read and one write concurrently; manage write queues.
8. **Protocol:** TCP streams lack message boundaries; handle partial reads/writes, EOF, and frame sizes.
9. **Timeout/cancel:** enforce deadlines at the request level; `Future.get` timeouts do not cancel I/O automatically.
10. **Ordered shutdown:** stop accepting work, complete/cancel, close channels, `group.shutdown`, `awaitTermination`, appropriate fallback.
11. **Load test:** monitor callback latency, pending tasks, memory, active sockets, error rates, and tail latency.
12. **Platform test:** verify behavior on the actual deployment OS/JDK/network provider rather than guessing implementation from the NIO name.

### Self-Check Questions

**1. Is `AsynchronousChannelGroup` used to transfer bytes between two sockets?**

No. The group shares completion-processing infrastructure; `AsynchronousSocketChannel` itself performs `read/write`.

**2. Can a callback of a group-bound channel run randomly on a thread outside the group?**

By contract, callbacks are invoked by one of the group's pooled threads. If an operation completes immediately and the caller is already on a pooled thread, it may be invoked directly on that initiating pooled thread.

**3. Does `group.shutdown()` close all sockets?**

Not yet. Orderly shutdown marks the group as shutdown and prevents new channels from being created; the group terminates only after its channels are closed, executing callbacks finish, and resources are released.

**4. Can you call `group.shutdownNow()` to guarantee every callback is immediately interrupted?**

No. It closes open channels, yet does not attempt to interrupt threads currently running completion handlers.

**5. If `Future.get(5, SECONDS)` throws `TimeoutException`, has the I/O operation automatically canceled itself?**

You cannot infer that. `Future.get`'s timeout is only a timeout on waiting for the result. You must use explicit cancel/close/timeout mechanisms aligned with the channel's semantics.

**6. Why shouldn't you call a long `Future.get()` directly inside a `CompletionHandler` of a fixed pool?**

Because the callback occupies a pooled thread. If all pooled threads wait on other tasks/callbacks that also need the same pool, the application can suffer starvation or deadlock.

**7. Can `AsynchronousFileChannel` be created with `AsynchronousChannelGroup.withFixedThreadPool` and then `open(path, group)`?**

No. The async file API accepts an `ExecutorService` in its dedicated overload, not a group.

**8. Why must the example loop reads and writes despite using the asynchronous API?**

Because one operation only promises to return actual bytes read/written, not an entire TCP message. "Asynchronous" describes how completion is received, **not** turning a stream into a message-based protocol.

## Official Reading Sources

- Oracle Java SE 21 — [`AsynchronousChannelGroup`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): groups, thread pools, default group, callback dispatch, shutdown, and termination.
- Oracle Java SE 21 — [`AsynchronousSocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): Future/CompletionHandler, limit of one pending read and one pending write, timeouts.
- Oracle Java SE 21 — [`AsynchronousServerSocketChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): accepting connections, pending accept, and groups.
- Oracle Java SE 21 — [`AsynchronousFileChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): async file I/O with ExecutorService and explicit offsets.
- Oracle Java SE 21 — [`CompletionHandler`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/CompletionHandler.html): completion callbacks, attachments, and error branch.

**In summary:** `AsynchronousChannelGroup` is a **resource-sharing and thread-pool layer** for asynchronous socket channels, not a protocol handler or an event loop that automatically handles business logic. Design success depends on clear ownership, brief callbacks, buffer/pending-operation management, measured thread sizing, and proper lifecycle shutdown for both channels and the group.
