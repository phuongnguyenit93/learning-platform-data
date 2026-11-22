# AsynchronousChannelGroup, Executors, and Group Lifecycle in Java NIO.2

## 1. Why Is AsynchronousChannelGroup Needed?

When using Java NIO.2, a call such as `AsynchronousSocketChannel.read(buffer, attachment, handler)` **initiates** an I/O operation, and the result is reported later in the `CompletionHandler`. The questions that arise are: **which thread will receive the event and run the callback, which resources do the channels share, who cleans up the thread pool, and when has the system actually stopped?**

`java.nio.channels.AsynchronousChannelGroup` answers those questions at the **asynchronous I/O channel group** level. A group owns/coordinates the implementation resources and an **associated thread pool** to process completion events, dispatch `CompletionHandler`s, and perform the work required for asynchronous I/O. Channels are bound to a group at the time they are opened; multiple channels can share a group instead of each connection creating its own pool.

**Four things to distinguish:**

1. **Channel** (`AsynchronousServerSocketChannel`, `AsynchronousSocketChannel`): the concrete endpoint and its connection/read/write state.
2. **Channel group** (`AsynchronousChannelGroup`): the group that manages shared completion mechanics and thread pool lifecycle.
3. **ExecutorService**: where internal tasks and completion handlers of the group execute; by default, it is not a “dedicated thread per socket”.
4. **Application/connection handler**: decides when to stop accepting connections, let requests finish, close channels, and request group shutdown.

A group’s `shutdown()` **does not mean** “close all channels right now”. It **marks the group to stop accepting new channels** and waits for channels/handlers to finish according to the contract. `shutdownNow()` is **stronger**: it actively closes remaining open channels in the group, but **does not forcibly stop a currently running completion handler**. `awaitTermination()` is the point where you wait for the group to finish terminating.

This lesson belongs to **Java Advance - networking → Asynchronous I/O**. The examples use Java 17+ and TCP loopback, requiring no framework, database, or Internet access; complete code is provided for both normal shutdown and forced shutdown.

## 2. Learning Objectives

After this lesson, you can:

- Describe what `AsynchronousChannelGroup` does, which channels belong to a group, and why completion handlers run on group threads.
- Create groups via `withFixedThreadPool`, `withCachedThreadPool`, and `withThreadPool`; distinguish fixed size from an executor that creates threads on demand.
- Open listeners/clients with the `open(group)` overload; understand that an accepted channel inherits the listener’s group, while parameterless `open()` uses the default group.
- Use `Future<T>` and `CompletionHandler<V,A>`; understand that `get()` still blocks the calling thread and callbacks should not perform heavy work.
- Distinguish `shutdown()`, `shutdownNow()`, `isShutdown()`, `isTerminated()`, and `awaitTermination(timeout, unit)`.
- Understand that the group **owns the lifecycle** of its associated executor, and never call `executor.shutdown()` externally while the group is still using the pool.
- Prevent races between pending accepts, in-flight I/O, callbacks, and shutdown without leaking channels or pools.
- Run two Java programs to observe exact group and executor states.
- Design timeouts, load limits, and production observability without treating “async” as unlimited or thread-free.

## 3. Architecture: Multiple Channels Sharing One Group

~~~text
                 Application / server lifecycle
                              |
                     creates / owns
                              v
           +---------------------------------------+
           |    AsynchronousChannelGroup           |
           |  - event completion coordination      |
           |  - associated ExecutorService         |
           |  - pooled completion-handler threads  |
           +-----------+-------------+-------------+
                       |             |
             open(group)             open(group)
                       |             |
               +-------v------+   +--v----------------+
               | Async server |   | Async client     |
               | listen/accept|   | connect/read/write|
               +-------+------+   +-------------------+
                       |
                accept succeeds
                       |
                +------v----------------+
                | accepted async socket |
                | bound to SAME group   |
                | read/write callbacks  |
                +-----------------------+

Completion events -> group pool threads -> user CompletionHandler
Application coordinates channel close -> group.shutdown -> awaitTermination
~~~

Looking at the resource level:

| Resource | Who creates it | What it is used for | Who closes/stops it |
| --- | --- | --- | --- |
| Custom `AsynchronousChannelGroup` | Application or lifecycle manager | Sharing executor and completion mechanics | Owner calls `shutdown()`/`shutdownNow()`, `awaitTermination()` |
| `AsynchronousServerSocketChannel` | `open(group)` | Binding/accepting TCP connections | Server owner closes when stopping client acceptance |
| Client `AsynchronousSocketChannel` | `open(group)` | Connecting and exchanging byte streams | Client/connection owner closes when finished |
| Accepted `AsynchronousSocketChannel` | Result from `listener.accept()` | Exchanging bytes with a client | Connection handler closes; shares group with listener |
| `ExecutorService` used by the group | Can be provided by the application when creating the group | I/O completion / running handlers | **Owned by the group**; shutting down the group leads to shutting down the executor |
| `CompletionHandler` | Provided by the application | Handling `completed`/`failed` | Not `Closeable`; must ensure code finishes quickly and correctly |
| `ByteBuffer` | Application | Carrying bytes of an in-flight operation | Avoid modifying/reading before the operation completes |

**Key point:** being in the same group does **not** mean all sockets share an input stream, UDP port, TCP connection, or business message queue. Each channel maintains its own connection state. The group shares **the completion coordination infrastructure and executor**.

### Do Not Confuse with Similarly Named Abstractions

- `Selector` is used with `SelectableChannel` for readiness-based **non-blocking I/O** and an application-driven event loop; it is **not** `AsynchronousChannelGroup`.
- `AsynchronousFileChannel` uses `open(path, options, executor, attrs...)`, accepting an **ExecutorService** directly; it **does not bind to `AsynchronousChannelGroup`** like network asynchronous socket channels.
- `CompletableFuture` has a default executor / ability to specify its own executor; if you call `thenApplyAsync` without supplying an executor, the task is not guaranteed to run in the channel group’s thread pool.
- A business thread pool for parsing/DB/CPU can be **separated** from the group executor to prevent I/O callbacks from being blocked.

## 4. Creating a Group: Three Factories and Pool Semantics

`AsynchronousChannelGroup` is not created via a public constructor. Three common ways:

### 4.1. `withFixedThreadPool(int nThreads, ThreadFactory factory)`

~~~java
ThreadFactory threads = task -> {
    Thread thread = new Thread(task, "aio-handler");
    return thread;
};
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(2, threads);
~~~

This is a **code snippet inside a method with `throws IOException`**; import `java.nio.channels.AsynchronousChannelGroup` and `java.util.concurrent.ThreadFactory`. `nThreads` must be greater than 0. Naming threads helps diagnostics; in production code, give unique indexed names and also consider an uncaught-exception handler, thread priority, and daemon policy.

- The group uses a **fixed pool** with the configured number of pooled threads; it is not one thread per client.
- Two threads for a demo can handle several network operations, which does **not** mean the group can only open two sockets.
- Group threads can execute callbacks and I/O support work, so a callback waiting indefinitely on a database can stall completions.
- Sizing should be measured based on completion rate, handler duration, load, provider/OS, and CPU; do not apply the formula “number of connections = number of threads”.

### 4.2. `withCachedThreadPool(ExecutorService executor, int initialSize)`

~~~java
ExecutorService pool = Executors.newCachedThreadPool();
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withCachedThreadPool(pool, 0);
~~~

The snippet requires imports `java.util.concurrent.*`, `java.nio.channels.*`, and `IOException` handling. With this approach:

- The executor **should** be capable of creating additional threads as needed (e.g., a cached thread pool) to handle completion tasks.
- `initialSize` is an initial **hint** to the implementation; it does **not** mean a maximum of 0 threads, is not a hard limit configuration, and is not the socket count.
- Non-negative or negative values carry implementation-specific default meanings per the API. For clarity, use `0` for groups taking an executor.
- The supplied executor is **dedicated to the group**. When the group terminates, the executor will be shut down. **Do not reuse that executor for independent business tasks.**

Flexible thread growth can help prevent callback starvation in some situations, but consumes more threads/memory. Do not treat a cached executor as an infinitely safe resource; you still need to limit clients and tasks.

### 4.3. `withThreadPool(ExecutorService executor)`

~~~java
ExecutorService pool = Executors.newCachedThreadPool();
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withThreadPool(pool);
~~~

This differs from `withCachedThreadPool(executor, initialSize)` in the declaration contract, and the `initialSize` passed to the provider is set to 0 in this factory. For `withThreadPool`, the JDK notes that the executor must **support direct handoff or an unbounded queue** and **must not run tasks directly on the thread calling `execute`**; the provider may impose additional requirements.

**Avoid `CallerRunsPolicy`** on a group’s executor: a pool that runs a callback directly on the thread enqueuing I/O can break thread assumptions and cause deadlocks. An executor with a poorly designed blocking/bounded queue or that shuts itself down will cause hard-to-diagnose issues.

### Factory Selection Table

| Factory | Input | Focus | Risks / Things to Note |
| --- | --- | --- | --- |
| `withFixedThreadPool(n,factory)` | Thread count and ThreadFactory | Fixed pool, easy to observe | Blocking callbacks stall other work |
| `withCachedThreadPool(executor,initialSize)` | Executor that grows threads on demand + hint | Scales according to implementation needs | Thread growth; executor must be dedicated to the group |
| `withThreadPool(executor)` | Qualified ExecutorService | Pre-existing executor managed with desired policy | Must satisfy executor contract; avoid CallerRuns / unsuitable queues |
| Async channel `open()` without passing a group | No group passed | Uses the JVM’s **default group** | Ownership and tuning differ from a custom group |

There is no single factory that is “best for every system”. When you want an independent lifecycle, thread naming, and workload isolation, a custom group is usually useful. Short demos can use the default group if separate shutdown control is not needed.

## 5. Default Group vs. Application-Owned Group

~~~java
AsynchronousSocketChannel a = AsynchronousSocketChannel.open();
AsynchronousSocketChannel b = AsynchronousSocketChannel.open(group);
AsynchronousServerSocketChannel server =
        AsynchronousServerSocketChannel.open(group);
~~~

This is a **code snippet**, where `group` must already be created; `IOException` must be handled and channels must be closed. Semantics:

- `open()` or `open(null)` places the channel in the **system-wide default group**.
- `open(group)` places the channel in the **specific group** passed in; that is the choice for managing a dedicated thread pool and lifecycle.
- `AsynchronousServerSocketChannel.accept()` returns an `AsynchronousSocketChannel` **belonging to the same group as the listener**.
- You cannot “move a live channel’s group” with a setter; the group is chosen when the channel is created.
- If the group has already shut down, creating a new channel bound to that group throws `ShutdownChannelGroupException`.
- A group uses the corresponding `AsynchronousChannelProvider` to create channels; the group and channel must be provider-compatible. The Java API does not allow attaching a group from another provider via casting tricks.

The default group is maintained by the JVM, has an executor that creates threads on demand, and is configured via system properties:

- `java.nio.channels.DefaultThreadPool.threadFactory`: class name of a `ThreadFactory` for the JVM to instantiate via the system class loader.
- `java.nio.channels.DefaultThreadPool.initialSize`: configures the initial size hint for the default group.

If no factory is configured, the JDK documentation describes the default group’s pooled threads as **daemon threads**. However, do not assume daemon threads guarantee that all I/O resources are cleanly closed at JVM exit; proper cleanup is still required. Runtime-managed default group initialization does not replace the lifecycle control of a custom group in a service.

**Do not arbitrarily set system properties just to fix a slow handler.** First separate blocking/CPU-heavy work from callbacks, limit resources, and measure actual load.

## 6. CompletionHandler and Future: Who Executes, Who Waits?

An asynchronous operation typically has two styles.

### 6.1. Future-based

~~~java
Future<AsynchronousSocketChannel> pending = listener.accept();
AsynchronousSocketChannel accepted = pending.get(5, TimeUnit.SECONDS);
~~~

This is a code snippet inside a method with `throws Exception`. `accept()` **initiates** waiting for a connection asynchronously; however, `Future.get(...)` **blocks the calling thread** until a result, timeout, or error occurs. If you call `get()` inside a callback occupying a group thread, you can create a deadlock when the pool is small and the operation needs those very group threads to complete.

Using `Future` is suitable for demos and simple multi-step orchestration; in multi-client servers, completion handlers or non-blocking pipelines are usually more appropriate.

### 6.2. Callback-based

~~~java
ByteBuffer buffer = ByteBuffer.allocate(1024);
client.read(buffer, null, new CompletionHandler<Integer, Void>() {
    @Override
    public void completed(Integer count, Void attachment) {
        // Distinguish count=-1 (EOF), count=0, count>0.
        // Only read the buffer after the operation has completed.
    }

    @Override
    public void failed(Throwable error, Void attachment) {
        // Handle error, log, and close the channel properly.
    }
});
~~~

This is a **code snippet**, with `client` already connected and importing `java.nio.ByteBuffer` and `CompletionHandler`. When the operation completes, the callback is typically dispatched via a thread from the group’s pool.

**JDK guarantee:** the completion handler of an operation on a channel belonging to a group is invoked by **one of the pooled threads in the group**. If the operation completes immediately and the code is called from a group thread, the implementation **may** run the callback directly on that thread (inline), except for certain operations with specific constraints such as `accept`. Therefore:

- **Do not rely on specific thread names or ordering** for correctness; rely only on the pooled-thread contract.
- **Do not block for long in a callback** waiting on `Future.get()` for other work in the same group, making long DB calls, or waiting on a lock held by a thread that needs completions.
- A callback can be triggered very quickly, even inline where permitted. Be careful with recursive `read`/`write` re-arming, stack limits, and progress handling.
- A buffer passed to an asynchronous operation is **not safe for concurrent modification/reading from another thread** before the operation completes; use per-request ownership.
- `completed`/`failed` of `CompletionHandler` is not a place to mutate shared state directly without synchronization. Use thread-safe data structures or message passing.

### 6.3. How Many Operations Can Be Active at Once?

| Channel | Core Limit | Exception if Violated |
| --- | --- | --- |
| `AsynchronousServerSocketChannel` | At most **one outstanding accept** per channel | `AcceptPendingException` |
| `AsynchronousSocketChannel` | At most **one outstanding read** | `ReadPendingException` |
| `AsynchronousSocketChannel` | At most **one outstanding write** | `WritePendingException` |
| `AsynchronousSocketChannel` | Can have one read **and** one write concurrently | Does not mean multiple concurrent reads |
| `ByteBuffer` used for I/O | One owner until callback/`Future` completes | Data race if reused prematurely |

The limits are **per channel**, not one read for the entire group. A group can manage many channels in parallel. If using a custom pipeline, manage per-connection state and backpressure before initiating a new operation.

### 6.4. I/O Errors Do Not Mean Callbacks Always Run on the Main Thread

Errors when initiating an operation (e.g., `AcceptPendingException` or `ShutdownChannelGroupException` in certain states) may be thrown **immediately at the call site**, not in the callback. Errors occurring during the asynchronous operation are typically delivered via `failed(Throwable, attachment)` or `Future.get()` with a cause. Therefore, both error paths must be handled.

Do not hold a lock on the main thread and wait for a callback that needs that lock: the application can deadlock even though I/O is handled asynchronously by the OS.

## 7. Lifecycle: States You Must Distinguish

~~~text
CREATED / RUNNING
   |
   | group.shutdown()
   v
SHUTDOWN (orderly)
   - rejects new channels bound to the group
   - does not automatically close open channels
   - running handlers are not interrupted
   |
   | all group channels closed
   | + running completion handlers finish
   | + group resources are released
   v
TERMINATED
   - isShutdown() == true
   - isTerminated() == true
   - associated executor has terminated

Or from running / shutdown state:
   |
   | group.shutdownNow()
   v
FORCE SHUTDOWN REQUESTED
   - group closes all remaining open group channels
   - does not forcibly interrupt running handlers
   |
   | running handlers finish + release resources
   v
TERMINATED
~~~

### 7.1. `shutdown()`: Orderly Stop

`group.shutdown()` marks the group as shutting down. After that:

- `AsynchronousSocketChannel.open(group)` or `AsynchronousServerSocketChannel.open(group)` will throw `ShutdownChannelGroupException`.
- **Existing channels are not automatically closed** just because `shutdown()` was called. The application remains responsible for closing the listener and connected channels per contract.
- The group only terminates when **all asynchronous channels of the group are closed**, **currently executing completion handlers complete**, and **group resources are released**.
- The group does not attempt to stop/interrupt threads currently executing callbacks.
- `isShutdown()` can be true while `isTerminated()` remains false for a long time, even indefinitely if the application fails to close open channels.

**Common pitfall:** calling `shutdown()` while leaving `AsynchronousServerSocketChannel` open with an unfinished `accept`; the group may never terminate. Proper shutdown must coordinate the listener and accepted channels rather than just setting the group flag.

### 7.2. `shutdownNow()`: Closing Group Channels

`group.shutdownNow()` initiates shutdown and **calls `close()` on open channels belonging to the group**. This typically helps release pending asynchronous operations on those channels, but:

- The method may throw `IOException`.
- It does **not** forcibly stop or interrupt a completion handler that has already entered user code and is blocking indefinitely.
- It does not automatically close database connections/files/queues **that do not belong to the group**.
- You must still wait for the group to terminate; `isTerminated()` must not be assumed to turn true immediately upon return.
- If a callback is in the middle of writing a response, a forced close can corrupt the transaction; use it when the drain deadline has expired or immediate cancellation is required.

### 7.3. `awaitTermination(long timeout, TimeUnit unit)`

~~~java
group.shutdown();
boolean terminated = group.awaitTermination(5, TimeUnit.SECONDS);
if (!terminated) {
    group.shutdownNow();
    terminated = group.awaitTermination(5, TimeUnit.SECONDS);
}
~~~

This is a code snippet inside a method with `throws IOException, InterruptedException` or handling both exceptions accordingly. Before `shutdown()`, the application must **stop accepting new clients and close/let group channels close** so that waiting can succeed. If the timeout expires and `terminated` is still false, you must report/investigate stuck handlers; never log “cleanly stopped” misleadingly.

`awaitTermination` contract: returns true if the group has terminated; false if the timeout elapsed. If the waiting thread is interrupted, the method throws `InterruptedException`. Applications catching the exception usually need to restore the interrupt flag (`Thread.currentThread().interrupt()`), coordinate cleanup, and report status appropriately.

### 7.4. `isShutdown()` and `isTerminated()`

| Observation Point | `isShutdown()` | `isTerminated()` |
| --- | --- | --- |
| Group newly created and running | false | false |
| `shutdown()` just called, at least one channel still open | true | false |
| Channels closed, handlers finished, resources released | true | true |
| `shutdownNow()` just returned, but a long-running handler is still active | true | May be false |
| After `awaitTermination(...) == true` | true | true |

**Do not** write a health check using the formula “`isShutdown()` = true => all connections are closed and threads are released”. Only `isTerminated()` confirms the terminated state.

## 8. Runnable Example 1: Group, Completion Handler, and Normal Shutdown

The Java 17+ code below:

1. Creates a **custom group** with 2 threads named with the prefix `aio-group-`.
2. Opens a **listener and client** with `open(group)`; the accepted socket from the listener also belongs to the group.
3. Uses `Future` to accept the connection and `CompletionHandler` to receive a four-byte `PING` message.
4. Verifies that the handler runs on a thread belonging to the group via the name set by the ThreadFactory.
5. Calls `group.shutdown()` while channels are still open: the group is shut down but **not yet terminated**.
6. Attempts to open a new channel on the group and receives `ShutdownChannelGroupException`.
7. Exits scopes to close the accepted socket, client, and listener; waits for `awaitTermination` to confirm termination.

Create the file **`AsyncGroupLifecycleDemo.java`**:

~~~java
import java.io.EOFException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousChannelGroup;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.nio.channels.AsynchronousSocketChannel;
import java.nio.channels.CompletionHandler;
import java.nio.channels.ShutdownChannelGroupException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

public class AsyncGroupLifecycleDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger counter = new AtomicInteger();
        ThreadFactory threads = task -> new Thread(
                task, "aio-group-" + counter.incrementAndGet());
        AsynchronousChannelGroup group =
                AsynchronousChannelGroup.withFixedThreadPool(2, threads);
        try {
            try (AsynchronousServerSocketChannel listener =
                         AsynchronousServerSocketChannel.open(group).bind(
                                 new InetSocketAddress(
                                         InetAddress.getLoopbackAddress(), 0));
                 AsynchronousSocketChannel client =
                         AsynchronousSocketChannel.open(group)) {
                Future<AsynchronousSocketChannel> pending = listener.accept();
                client.connect(listener.getLocalAddress())
                        .get(5, TimeUnit.SECONDS);

                try (AsynchronousSocketChannel accepted =
                             pending.get(5, TimeUnit.SECONDS)) {
                    ByteBuffer input = ByteBuffer.allocate(4);
                    CompletableFuture<String> message = new CompletableFuture<>();
                    CompletableFuture<Boolean> correctThread = new CompletableFuture<>();
                    accepted.read(input, null, new CompletionHandler<Integer, Void>() {
                        @Override public void completed(Integer n, Void unused) {
                            try {
                                if (n < 0) throw new EOFException("Missing request");
                                if (input.hasRemaining()) {
                                    accepted.read(input, null, this);
                                } else {
                                    input.flip();
                                    correctThread.complete(Thread.currentThread()
                                            .getName().startsWith("aio-group-"));
                                    message.complete(StandardCharsets.US_ASCII
                                            .decode(input).toString());
                                }
                            } catch (Throwable e) {
                                correctThread.completeExceptionally(e);
                                message.completeExceptionally(e);
                            }
                        }

                        @Override public void failed(Throwable error, Void unused) {
                            correctThread.completeExceptionally(error);
                            message.completeExceptionally(error);
                        }
                    });

                    ByteBuffer payload = StandardCharsets.US_ASCII.encode("PING");
                    while (payload.hasRemaining()) {
                        client.write(payload).get(5, TimeUnit.SECONDS);
                    }
                    System.out.println("Server received: " +
                            message.get(5, TimeUnit.SECONDS));
                    System.out.println("Handler used group thread: " +
                            correctThread.get(5, TimeUnit.SECONDS));

                    group.shutdown();
                    System.out.println("Group shutdown: " + group.isShutdown());
                    System.out.println("Terminated with channels open: " +
                            group.isTerminated());
                    try (AsynchronousSocketChannel ignored =
                                 AsynchronousSocketChannel.open(group)) {
                        System.out.println("New channel rejected: false");
                    } catch (ShutdownChannelGroupException expected) {
                        System.out.println("New channel rejected: true");
                    }
                }
            }
            System.out.println("Terminated after channel close: " +
                    group.awaitTermination(5, TimeUnit.SECONDS));
        } finally {
            if (!group.isTerminated()) {
                group.shutdownNow();
                group.awaitTermination(5, TimeUnit.SECONDS);
            }
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 AsyncGroupLifecycleDemo.java
java AsyncGroupLifecycleDemo
~~~

**Verified stdout with OpenJDK 24 on TCP loopback:**

~~~text
Server received: PING
Handler used group thread: true
Group shutdown: true
Terminated with channels open: false
New channel rejected: true
Terminated after channel close: true
~~~

**Step-by-step explanation:**

- `InetAddress.getLoopbackAddress()` keeps connections local; binding port 0 lets the OS pick an available port. No external server is needed.
- `listener.accept()` returns `Future<AsynchronousSocketChannel>`. `Future.get` on main waits for the accepted channel; the operation was already initiated asynchronously.
- `accepted.read(input, null, handler)` uses a callback. The callback may be invoked after each partial read; if the buffer is not full yet, it re-arms the read. For a 4-byte example, this handling is straightforward.
- `client.write(payload).get` in a loop handles potential partial writes; this is a demo—production code should use an async state machine if you do not want main to block.
- `correctThread` checks the name prefix created by `ThreadFactory`. This is **example instrumentation**; do not use thread names for authorization or correctness in real applications.
- `shutdown` marks the group without closing channels. Because the listener and client are still open, `isTerminated()` is false.
- `AsynchronousSocketChannel.open(group)` is rejected because the group is already shut down.
- Only after the `try-with-resources` scopes close all listener/client/accepted channels can the group terminate and `awaitTermination` return true.

**Do not apply a four-byte length as a production protocol**: TCP is a byte stream; real applications need framing, payload limits, timeouts/cancellation, and proper handling of EOF/partial reads. A `ByteBuffer` must belong to one operation at a time. The demo code intentionally uses `CompletableFuture` so main can wait for the callback; handlers do not block on `get()` for other work.

## 9. Runnable Example 2: shutdownNow Closes Channels and Stops the Pool

The next program creates an `ExecutorService` with `Executors.newCachedThreadPool()`, hands it to `AsynchronousChannelGroup.withThreadPool(pool)`, and opens a listener in the group. After `group.shutdownNow()`, the listener must be closed, and when the group terminates, the executor is also shut down.

Create the file **`AsyncGroupForceCloseDemo.java`**:

~~~java
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.channels.AsynchronousChannelGroup;
import java.nio.channels.AsynchronousServerSocketChannel;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

public class AsyncGroupForceCloseDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newCachedThreadPool();
        AsynchronousChannelGroup group =
                AsynchronousChannelGroup.withThreadPool(pool);
        try {
            AsynchronousServerSocketChannel listener =
                    AsynchronousServerSocketChannel.open(group);
            try {
                listener.bind(new InetSocketAddress(
                        InetAddress.getLoopbackAddress(), 0));
                System.out.println("Listener open before: " + listener.isOpen());
                group.shutdownNow();
                System.out.println("Listener open after: " + listener.isOpen());
                System.out.println("Group terminated: " +
                        group.awaitTermination(5, TimeUnit.SECONDS));
                System.out.println("Executor shutdown: " + pool.isShutdown());
            } finally {
                listener.close();
            }
        } finally {
            if (!group.isTerminated()) {
                group.shutdownNow();
                group.awaitTermination(5, TimeUnit.SECONDS);
            }
        }
    }
}
~~~

Run commands:

~~~bash
javac -encoding UTF-8 AsyncGroupForceCloseDemo.java
java AsyncGroupForceCloseDemo
~~~

**Verified stdout:**

~~~text
Listener open before: true
Listener open after: false
Group terminated: true
Executor shutdown: true
~~~

The line `Listener open after: false` is the consequence of `shutdownNow()` calling close on group channels. The line `Executor shutdown: true` demonstrates that **the group owns the executor’s lifecycle**. You should not call `pool.shutdown()` first and expect the group to continue executing callbacks normally.

This example **has no long-running callbacks**: the group can terminate quickly. In production, if a handler is waiting on a DB, a lock, or heavy CPU work, `shutdownNow()` can close channels while `awaitTermination` still times out until the handler finishes.

## 10. Who Owns the Executor, and Why Not Shut It Down Directly?

With `withThreadPool(pool)` or `withCachedThreadPool(pool, initialSize)`, even though the caller creates the `ExecutorService`, **the group is granted lifecycle ownership** of that pool. The JDK documentation emphasizes:

- The executor should be **dedicated to the group**.
- Group termination results in an orderly shutdown of the executor.
- Shutting down the executor by other means while the group is using it leads to **unspecified behavior**.

Wrong ownership:

~~~java
ExecutorService executor = Executors.newCachedThreadPool();
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withThreadPool(executor);

executor.shutdown(); // WRONG: the group is still active, callbacks may fail.
~~~

This is a **code snippet**. Do not mix resource lists like `try (executor; group)`: in Java 17, `ExecutorService` is not yet `AutoCloseable` per the Java 17 API, and `AsynchronousChannelGroup` is not `AutoCloseable` either. Therefore, lifecycle management requires **explicit** `shutdown/awaitTermination` calls in `finally` / a shutdown hook or manager.

Proper design:

~~~java
AsynchronousChannelGroup group =
        AsynchronousChannelGroup.withFixedThreadPool(4, factory);
try {
    runServer(group);
} finally {
    group.shutdown();     // Group channels have been closed in runServer.
    if (!group.awaitTermination(5, TimeUnit.SECONDS)) {
        group.shutdownNow();
        if (!group.awaitTermination(5, TimeUnit.SECONDS)) {
            reportStuckHandlers();
        }
    }
}
~~~

This is a **sketch snippet**, not standalone: `factory`, `runServer`, and `reportStuckHandlers` are provided by the application; `shutdownNow()` can throw `IOException` and `awaitTermination()` can throw `InterruptedException`, so the method must handle or declare them. `runServer` needs a stop path so cleanup can begin; do not put an infinite accept loop that prevents the caller from reaching `finally`.

**If you have another application executor for business processing**, that is a **different** pool with a different owner. Shut down in the proper order: stop accepting requests, drain business operations, close channels, shut down the group, await the group, and then shut down separate application pools once they are no longer in use. Do not share the group’s executor for job scheduling or long CPU tasks just for convenience.

## 11. Designing Controlled Asynchronous Server Shutdown

A real server has an `AsynchronousServerSocketChannel` listener, many accepted `AsynchronousSocketChannel` instances, and potentially many running `CompletionHandler`s. Proper shutdown requires a state machine.

~~~text
RUNNING:
  listener accept loop is active
  accepted channels are reading/writing
  completion handlers may initiate new operations

STOPPING_ACCEPT:
  set stopping=true (thread-safe / volatile / atomic)
  stop re-arming accept
  listener.close()
  accept failure callback sees stopping -> do not retry
  do not create new client channels on the group

DRAINING:
  wait for accepted sessions to finish within deadline
  each handler closes its accepted channel
  do not open more channels or initiate new business operations

GROUP_SHUTDOWN:
  after stopping new group channels from being opened, call group.shutdown()
  wait for awaitTermination; open channels will prevent termination

FORCED_CLOSE (when deadline expires):
  group.shutdownNow() -> closes remaining open group channels
  complete or handle running handlers
  wait for awaitTermination further with deadline

TERMINATED:
  resource cleanup done; associated executor has terminated
  log status and metrics
~~~

**You can start `group.shutdown()` before all channels are closed**, because shutdown only forbids opening **new channels** and does not automatically close existing ones. However, you must coordinate the accept loop: per the `AsynchronousServerSocketChannel` contract, if the group is shutting down when a connection is accepted, the operation may fail with cause `ShutdownChannelGroupException` and the accepted socket is closed. Therefore, the application’s order should minimize races: set the stop flag and close the listener / stop re-arming accept first, then shut down the group once new accepts have stopped.

### 11.1. Rules for the Accept Completion Handler

Logic sketch (not standalone code):

~~~java
listener.accept(null, new CompletionHandler<AsynchronousSocketChannel, Void>() {
    @Override
    public void completed(AsynchronousSocketChannel client, Void ignored) {
        if (stopping.get()) {
            closeQuietly(client);
            return;
        }
        // Re-arm exactly one next accept if the listener is still open.
        listener.accept(null, this);
        // Transfer ownership of the client to the handler; the handler must close it.
        handOff(client);
    }

    @Override
    public void failed(Throwable error, Void ignored) {
        if (stopping.get()) {
            // Expected shutdown, do not retry infinitely.
            return;
        }
        reportAcceptFailure(error);
        // Apply backoff/retry policy based on the error and state.
    }
});
~~~

This illustrative snippet requires `listener`, an `AtomicBoolean` `stopping`, and helpers `closeQuietly`, `handOff`, and `reportAcceptFailure`; it must also handle `ClosedChannelException`/`ShutdownChannelGroupException` thrown synchronously when re-arming, as well as failed ownership transfer. Production code needs concurrency bounds and task-handoff guarantees. Do not copy the snippet above as a complete server.

Rules:

- A listener allows only **one outstanding accept**. Calling it concurrently throws `AcceptPendingException`.
- Re-arming accept after the previous operation completes allows accepting the next connection; code often re-arms early in the callback to avoid delaying new clients, but must not create a race with stop.
- If a client is accepted after stop has begun, **close the newly accepted client** immediately without dispatching further tasks.
- A `failed` callback caused by the server intentionally closing during stop **should not retry infinitely** or flood error logs.
- Track active accepted channels so they can be drained or force-closed when needed.

### 11.2. Managing Accepted Channels and Subtasks

If a group has many handlers, use a thread-safe registry for accepted channels, such as `ConcurrentHashMap.newKeySet()`. On accept:

1. Accept the client and register it in the registry before processing.
2. If the system has already stopped, do not dispatch new work; close immediately.
3. When the handler finishes or errors out, `close()` the channel and remove it from the registry.
4. When the drain period expires, close remaining channels in the registry; `shutdownNow()` is also available to force-close the entire group.
5. Limit connection counts, per-client pending reads/writes, buffers, and downstream tasks.

**Race to avoid:** if stop occurs between checking `stopping` and registering/handing off to a handler, a new client can slip in after stop. State/registry must use atomic coordination or a rule that accepts late arrivals and closes them immediately. A boolean flag alone without a retry/close policy is insufficient.

## 12. Timeouts, Cancellation, and Errors on Async Channels

### 12.1. Timeouts Are Not Handled Just by Shutting Down the Group

The `AsynchronousSocketChannel.read/write` overloads allow specifying a timeout. For `read`:

~~~java
client.read(buffer, 3, TimeUnit.SECONDS, null,
        new CompletionHandler<Integer, Void>() {
    @Override public void completed(Integer n, Void ignored) {
        // Handle n >= 0 or -1 EOF.
    }
    @Override public void failed(Throwable error, Void ignored) {
        // May be InterruptedByTimeoutException or an I/O error.
    }
});
~~~

This is a **code snippet**; `client`/`buffer` already exist. According to JDK documentation, an I/O timeout can leave the channel or `ByteBuffer` state unreliable depending on the implementation if it cannot be confirmed whether bytes were transferred. Therefore, **do not retry on the same `ByteBuffer`/channel by default right after a timeout**. Usually you should close the connection and establish a new session per the protocol when frame state is uncertain.

`Future.get(timeout, unit)` differs from an I/O timeout: it limits **how long the calling thread waits on the Future**, and does not guarantee that the kernel operation has been canceled when the caller times out. If you want to stop the operation, have a strategy to cancel/close the channel and handle completion results that are no longer needed.

### 12.2. Exceptions to Classify

| Situation | Typical Exception / Result | Meaning |
| --- | --- | --- |
| Opening a channel bound to a shut-down group | `ShutdownChannelGroupException` | New channels cannot be attached to the group |
| Initiating accept while another accept is pending | `AcceptPendingException` | Must coordinate a single outstanding accept |
| Initiating read while another read is pending | `ReadPendingException` | Per-connection state machine is wrong |
| Initiating write while another write is pending | `WritePendingException` | Coalesce/queue writes properly |
| Connection gone / close in progress | `AsynchronousCloseException`, `ClosedChannelException`, or corresponding I/O error | Must treat lifecycle/close races as normal during stop |
| Read/Write exceeded deadline | `InterruptedByTimeoutException` | Buffer/connection state may be uncertain |
| Async Future I/O failed | `ExecutionException` in `Future.get()` | Use `getCause()` to inspect the root error |
| Future wait timed out | `TimeoutException` | Caller stopped waiting; operation is not guaranteed canceled |
| Main thread interrupted while awaiting | `InterruptedException` | Restore interrupt flag and coordinate cleanup |
| `shutdownNow()` cleanup failed | `IOException` | Report stop failure; resources may not be released |

Do not “swallow” exceptions in `CompletionHandler.failed`: failing to close or signal the error can leave a channel holding resources so `awaitTermination()` never succeeds. Close the channel from the proper owner, complete the business `CompletableFuture`/promise exceptionally, and avoid logging secret payloads.

### 12.3. Cancellation and Completion Can Race

An operation can complete right before the caller cancels/closes, or fail as the group is shut down. Therefore:

- Design each request to **complete only once** (atomic state or `CompletableFuture.complete/completeExceptionally`).
- Avoid further operations on a `ByteBuffer` while an operation is still pending.
- On business timeout, you can close the channel to abort I/O, then handle late callbacks and release buffers safely.
- Only confirm channel/group closure after the lifecycle has truly finished; do not let a late-arriving callback update canceled state in a way that revives the request.

## 13. Performance: Async Does Not Mean Unlimited Threads/Connections

A group with 2 or 4 threads can still coordinate a very large number of channels because the I/O itself is performed asynchronously. However, **callback handlers** execute Java code on pooled threads and can easily become a bottleneck.

Scenario:

~~~text
Group fixed pool: 2 threads
  Thread A: handler finishes reading -> blocking DB call 10 s
  Thread B: handler finishes reading -> CPU computation 10 s

Other completions may have to wait.
TCP senders/receivers still have bytes in OS buffers, but application latency increases.
~~~

Countermeasures:

- Keep completion handlers **short and non-blocking**; offload CPU/DB work to a separate **application executor** so group threads can return to dispatching I/O.
- Cap active connections and pending tasks; do not create unbounded `CompletableFuture` instances or per-request buffers.
- Per socket, allow only one pending read and one pending write; use per-connection queues and backpressure.
- Choose a fixed or cached pool based on measured load, not simply on total socket count.
- Avoid `CallerRunsPolicy`, manually shutting down a group-owned pool, or letting callbacks throw unhandled exceptions without closing channels.
- Track metrics: active channels, pending accepts, pending reads/writes, completion latency, group thread count, executor queue, time-to-drain, timed-out operations, and forced closes.
- When deadline control is needed, account for callbacks, network I/O, the application pool, and downstream resources; `awaitTermination()` alone does not enforce timeouts on business operations.

A callback that blocks waiting on other work in the **same fixed-size group** risks deadlock; do not fix this by endlessly increasing thread counts—fix the dependency graph so callbacks do not wait synchronously.

## 14. Default Group and Operational Issues

If you write:

~~~java
try (AsynchronousSocketChannel client = AsynchronousSocketChannel.open()) {
    client.connect(address).get(5, TimeUnit.SECONDS);
}
~~~

This is a **code snippet**; `address` must already be defined, and the method `throws Exception`. It uses the **JVM’s default group**. When a system has multiple modules/libraries sharing the default group:

- You cannot rely on a custom group to isolate one module’s callbacks if that module does not use `open(customGroup)`.
- The default group’s thread pool can be affected by other libraries and JVM system properties.
- Do not try to shut down an executor not attached to the group or swap the thread factory at runtime assuming everything will change immediately.
- If you want independent tests/metrics/lifecycle, create an explicit group and pass it to **all** channels in that subsystem.

**Note on thread naming:** the demo handlers use `aio-group-` only for observation. In real environments, additional threads may be created by the provider for internal tasks in an implementation-specific way; there is no guarantee of “exactly one Java thread per socket” or “one event = one new thread”.

### 14.1. Do Not Confuse AsynchronousFileChannel with Network Groups

`AsynchronousFileChannel.open(path, Set<OpenOption>, ExecutorService, FileAttribute...)` accepts a pool directly. It is **not** an `open(AsynchronousChannelGroup)` overload, so it does not automatically belong to the network groups discussed in this lesson.

If using file channels and socket channels in the same application, separate the ownership of the file executor and the group executor, especially during server shutdown. Do not call `group.shutdownNow()` expecting it to close every `AsynchronousFileChannel` in the JVM.

### 14.2. Do Not Assume All Platforms Have Identical Thread Counts or Timing

NIO.2 depends on `AsynchronousChannelProvider` and the operating system. Callback timing, helper thread counts, and I/O completion details can differ across Windows/Linux/macOS. The API guarantees certain contracts—such as callbacks running on group pooled threads and shutdown states—but does not guarantee global event ordering, specific response times, or a fixed number of native workers in the provider.

Therefore, tests should verify **synchronization/contract conditions**, rather than sleeping 100 ms and assuming resources are closed.

## 15. Test Matrix for Group and Lifecycle

| Test | Setup | Expected |
| --- | --- | --- |
| Create custom group | `withFixedThreadPool(2, factory)` | Group created successfully; not yet shut down |
| Channel bound to group | `AsynchronousSocketChannel.open(group)` | Channel belongs to chosen group |
| Accepted channel | `listener.open(group)` then `accept()` | Accepted channel bound to listener’s group |
| Callback thread | Create thread factory with fixed prefix | Callback runs on pooled thread per contract |
| Graceful shutdown | Call `group.shutdown()` while channels remain open | `isShutdown()=true`, `isTerminated()=false` |
| Open new after shutdown | `AsynchronousSocketChannel.open(group)` | `ShutdownChannelGroupException` |
| Await while channels open | `awaitTermination(shortTimeout)` | May return false |
| Close all channels | Close listener/client/accepted and finish handlers | `awaitTermination(...)` becomes true |
| Force shutdown | `group.shutdownNow()` while listener is open | Listener is closed |
| Executor ownership | `withThreadPool(pool)` then group terminates | `pool.isShutdown()=true` |
| Slow handler | Controlled blocking callback | `shutdownNow` does not forcibly interrupt callback |
| Double pending accept | Issue 2 accepts on same listener | `AcceptPendingException` |
| Double pending read | Issue 2 reads on same connected channel | `ReadPendingException` |
| Double pending write | Issue 2 writes on same connected channel | `WritePendingException` |
| Fault during callback | Handler throws IOException or runtime error | Caught/propagated/closed properly without leaks |
| Shutdown race | Stop flag and accept callback run concurrently | No new clients opened/dispatched after stop policy; late accepted closed |
| File channel separate from group | Create separate `AsynchronousFileChannel` | Not shut down by network group |

For concurrency tests, do not assert exact thread names or callback ordering across two connections. Use `CountDownLatch`/`CompletableFuture` to synchronize and test with deadlines. A test that only passes on a laptop does not guarantee there are no races under load.

## 16. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `group.shutdown()` and assuming channels close | Group never terminates because channels remain open | Close / let channels close according to ownership |
| Not calling `awaitTermination()` | Unknown whether resources/pool are released | Wait with deadline, check boolean |
| Calling `shutdownNow()` and assuming blocked callbacks stopped | Running Java callbacks are not interrupted by this contract | Design cancellation and cooperative deadlines |
| Shutting down the group’s executor directly | Provider may exhibit unspecified behavior | Let the group own the executor lifecycle |
| Sharing the group executor for long CPU tasks | Completion events stall, latency spikes | Separate app executor, short callbacks |
| Choosing `CallerRunsPolicy` for the group executor | May run handlers on caller thread, violating API assumptions | Use an executor matching the contract |
| Creating a group/pool per client | Excessive threads/resources, hard to shut down | One shared group per subsystem |
| Mixing `open()` and `open(group)` unintentionally | Channel lands in default group; custom shutdown does not affect it | Pass group consistently throughout the subsystem |
| Accepting connections without closing them | Group waits on channels forever, leak | Try-with-resources/cleanup in handlers |
| Calling `accept()` while an accept is pending | `AcceptPendingException` | Re-arm exactly once after completion |
| Calling `read()`/`write()` concurrently in the same direction | `ReadPendingException` / `WritePendingException` | Per-channel queue/state machine |
| Accessing ByteBuffer before I/O finishes | Data race/corruption | Only use buffer after completion |
| Calling `Future.get()` inside a group callback | Starvation/deadlock when pool is small | Chain callbacks, do not block group threads |
| Thinking `Future.get(timeout)` cancels I/O on timeout | Operation may still be pending | Close/cancel channel per policy |
| Thinking a timed-out read leaves the buffer untouched | JDK allows buffer state to be undefined | Do not blindly reuse buffer after timeout |
| `completed()` throws without notifying the caller | Request hangs, channel leaks | Catch, completeExceptionally, close properly |
| Logging shutdown errors as abnormal failures | Log noise, infinite retries | Distinguish planned stop from failure |
| Checking only `isShutdown()` to confirm stop succeeded | Group may not be terminated yet | Use `isTerminated()`/`awaitTermination` |
| Increasing thread pool without capping connections | Queues, file descriptors, and buffers still grow | Backpressure and resource budgets |

## 17. Exercises with Solutions

### Exercise 1 — Shutdown Does Not Stop

A server calls `group.shutdown()`, `group.isShutdown()` returns true, but `awaitTermination(5, SECONDS)` returns false. Is this necessarily a JDK bug?

**Answer:** No. There may still be an open listener, client/accepted channels, or running completion handlers. `shutdown` does not close channels. You must identify the owners, close/let the channels finish, wait for handlers, and release resources; only then will the group terminate.

### Exercise 2 — Choosing a Factory

An application wants a group with 4 threads to process completions, with custom thread names for latency measurement. Which factory should be used? Does the number 4 mean only 4 sockets can be opened?

**Answer:** Use `AsynchronousChannelGroup.withFixedThreadPool(4, threadFactory)`. Four is the configured number of pooled threads, not a socket count limit; hundreds of sockets can attach to the same group, though resource limits and backpressure are still needed.

### Exercise 3 — Executor Shut Down Unexpectedly

A library shares `ExecutorService pool` with business application code and creates `group = withThreadPool(pool)`. When the application calls `pool.shutdown()` midway, what goes wrong?

**Answer:** The group expects **exclusive ownership** of the executor. Shutting it down directly via another path while the group still uses it leads to behavior unspecified by the JDK; completion tasks may be disrupted. Use a dedicated executor and call `group.shutdown()/awaitTermination()` through a lifecycle manager.

### Exercise 4 — Creating a New Channel After Shutdown

After `group.shutdown()`, what happens when `AsynchronousSocketChannel.open(group)` is called?

**Answer:** It throws `ShutdownChannelGroupException`. That does not prove old channels are closed; it only proves the group is no longer accepting new channels.

### Exercise 5 — Blocking Callbacks

A fixed-pool group has only two threads. Two `CompletionHandler.completed` callbacks simultaneously call `Future.get()` waiting on another operation that also needs group callbacks to complete. What is the risk?

**Answer:** Starvation/deadlock. The handlers occupy all pooled threads while other completions need processing. Do not block group callbacks; use callback chaining / non-blocking logic or offload CPU/DB work to a separate business executor.

### Exercise 6 — Comparing shutdownNow

An application calls `group.shutdownNow()`. Is `isTerminated()` guaranteed to be immediately true and running callbacks interrupted?

**Answer:** No. `shutdownNow` closes remaining open group channels, but does not attempt to stop/interrupt currently executing handlers. Wait on `awaitTermination` and ensure callbacks cooperate to finish.

### Exercise 7 — Confusing the Default Group

A server uses `AsynchronousServerSocketChannel.open(group)`, while a client uses `AsynchronousSocketChannel.open()`. When `group.shutdownNow()` is called, is the client automatically closed because it is in the same JVM process?

**Answer:** No. The client belongs to the **default group**, not the server’s custom group. Group shutdown only closes channels belonging to that group. The client may be affected normally by the server closing its connection, but not because the group directly owns it.

### Exercise 8 — One Pending Read

Before a client `read` callback has been invoked, another handler calls `read` on the same `AsynchronousSocketChannel`. Which exception is thrown and why?

**Answer:** `ReadPendingException`: only one outstanding read is allowed per channel. Use a state machine to wait for the previous callback before re-arming a read.

### Exercise 9 — File Channel

Does `AsynchronousFileChannel.open(path, options, executor)` automatically belong to the network’s custom `AsynchronousChannelGroup`?

**Answer:** No. File channels accept an executor directly and do not bind to a network group via `open(group)`. Manage the file channel’s executor/lifecycle under its own owner.

### Exercise 10 — Verifying Lifecycle

Why is a test with `Thread.sleep(200)` followed by checking `group.isTerminated()` weaker than a test using `awaitTermination(timeout)`?

**Answer:** Sleep makes assumptions about CPU/OS timing and is prone to flakiness. `awaitTermination` waits for the actual state condition with a deadline and returns a verifiable boolean. The test must close channels/handlers per contract before waiting.

## 18. Code Review Checklist for Asynchronous I/O Groups

- [ ] Clearly identified which subsystem owns the custom `AsynchronousChannelGroup`.
- [ ] Selected `withFixedThreadPool`/`withCachedThreadPool`/`withThreadPool` with a sound rationale and suitable executor.
- [ ] Associated executor is **dedicated to the group** and is never shut down before the group.
- [ ] Listener, client, and accepted async channels are all attached to the **intended group**.
- [ ] Accepted channels are owned by handlers and closed on both happy and error paths.
- [ ] Callbacks do not block for long and do not wait on other Futures in the same pool via `get()`.
- [ ] `ByteBuffer` is not read/written while an asynchronous operation is still pending.
- [ ] Each channel has at most one pending accept, one pending read, and one pending write per the API.
- [ ] Framing, payload limits, deadlines, and EOF/timeout handling are in place.
- [ ] Thread-safe stop flag/registry is used to minimize races between accept and shutdown.
- [ ] Accept re-arming is stopped and the listener is closed before terminating the group.
- [ ] `shutdown()` only marks stopping; **closing channels** is what allows termination.
- [ ] `awaitTermination()` has a deadline; `false` is checked and `shutdownNow` is handled with proper ownership.
- [ ] `InterruptedException`/`IOException` during shutdown are handled without logging false success.
- [ ] Metrics separate group shutdown, group terminated, active channels, and blocked handlers.
- [ ] Default group, FileChannel executors, and application executors have separate lifecycles.
- [ ] Tests cover normal shutdown, forced close, callback errors, and races.

## 19. Authoritative References

- [Java SE 17 — AsynchronousChannelGroup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousChannelGroup.html): factory methods, threading, default group, shutdown, awaitTermination, and executor ownership.
- [Java SE 17 — AsynchronousServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousServerSocketChannel.html): `open(group)`, `accept`, accepted channel sharing group, `AcceptPendingException`.
- [Java SE 17 — AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): `read/write`, `CompletionHandler`, `Future`, buffer state on timeout, `ReadPendingException`, and `WritePendingException`.
- [Java SE 17 — CompletionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/CompletionHandler.html): `completed` and `failed`.
- [Java SE 17 — AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): differs from network channel groups; manages the executor passed when opening the file.
- [Java SE 17 — ShutdownChannelGroupException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ShutdownChannelGroupException.html): response when a group no longer accepts new channels.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): executor lifecycle; distinct from group shutdown.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, and buffer safety.
- [Java SE 17 — java.nio.channels package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/package-summary.html): place of asynchronous I/O in NIO.2.

**Key takeaway:** `AsynchronousChannelGroup` is a **shared completion + executor mechanism** for async socket channels, **not** a list of sockets that automatically closes when `shutdown()` is called. Separate channel ownership from group ownership, keep callbacks short, let the group manage its associated executor, stop accepting and close channels before awaiting `awaitTermination()`, and only use `shutdownNow()` to force-close once you have accounted for the impact on in-flight transactions.
