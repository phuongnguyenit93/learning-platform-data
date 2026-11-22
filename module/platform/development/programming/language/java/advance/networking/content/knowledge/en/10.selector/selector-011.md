# Coordinating an Event Loop with a Worker Pool Without Blocking the Selector Thread

## 1. Goal: Selector Thread for I/O, Workers for Business Processing

When building a TCP server with Java NIO, a single **event loop** thread can monitor multiple `SocketChannel` instances using a `Selector`. A common architectural mistake is receiving an `OP_READ` event and then **running long-running business logic directly on the selector thread**: blocking database queries, synchronous HTTP API calls, CPU-heavy work, waiting on `Future.get()`, or waiting for a lock. During that time, the event loop cannot process other connections, even though their sockets are already ready.

The solution is **separation of responsibilities**:

- **Event loop (I/O thread):** `select()`, accepting connections, reading currently available bytes, writing bytes that can be sent immediately, updating `SelectionKey` state, managing connections, and framing messages.
- **Worker pool (thread pool):** handling business logic that is expensive enough not to run on the event loop, such as complex data transformations, computation, or synchronous I/O work that lacks a suitable asynchronous API.
- **Completion queue + `selector.wakeup()`:** workers hand results back to the event loop; the **event loop** uses those results to update response buffers, `interestOps`, and pause/resume reading.

Important point: **not blocking the selector thread** does not mean every task on the workers executes instantaneously. Tasks can wait in a queue, time out, fail, or be canceled. Therefore, the design also needs **bounds on in-flight tasks**, overload handling, per-connection state tracking, and a shutdown policy.

```text
                          TCP clients
                    A       B       C
                    |       |       |
                    v       v       v
              +--------------------------+
              | Event loop / Selector    |
              | OP_ACCEPT, OP_READ       |
              | decode/validate frame    |
              | enqueue work             |
              +------------+-------------+
                           |
                           v  bounded work queue (production)
              +--------------------------+
              | Worker pool              |
              | W1         W2      W3    |
              | business processing      |
              +------------+-------------+
                           |
                  completion/result
                           v
              +--------------------------+
              | Thread-safe completions  |
              +------------+-------------+
                           |
                    selector.wakeup()
                           |
                           v
              +--------------------------+
              | Event loop               |
              | apply result to Conn     |
              | interestOps(OP_WRITE)    |
              | partial channel.write()  |
              +--------------------------+
                           |
                       TCP response
```

The core focus of this exercise is **Selector**, so the examples below use **Java 17+ NIO SocketChannel**. The runnable program handles one request per connection to stay easy to follow, and then we analyze how to scale to multiple requests and production systems.

## 2. Why Calling a Worker Can Still Block the Event Loop

The following snippets are **not standalone programs**; they illustrate common mistakes in the `OP_READ` handling branch:

```java
// WRONG: doing long-running work directly on the I/O thread.
String result = databaseCallBlocking(request);
sendResponse(channel, result);

// STILL WRONG: offloading work but immediately waiting synchronously on the I/O thread.
Future<String> future = workerPool.submit(
        () -> databaseCallBlocking(request));
String result2 = future.get(); // blocks the event loop until the worker finishes
```

In both cases, if the task takes 500 ms, the selector fails to service many other keys during those 500 ms. Adding more workers does not save the second case because **the event loop thread is still blocked at `get()`**.

The correct flow is:

```text
Event loop:
  READ a complete frame
  -> submit request to the pool (without waiting for the result)
  -> pause reading on that connection (if sequential processing is required)
  -> continue selecting other connections

Worker:
  process request
  -> place result into ConcurrentLinkedQueue
  -> call selector.wakeup()
  -> finish, do not call channel.write in the demo

Event loop upon waking up:
  -> drain results from the queue
  -> verify the connection/key is still valid
  -> set the response ByteBuffer
  -> register OP_WRITE
  -> attempt write; if partial write, keep OP_WRITE for the next round
```

Another subtle mistake is writing a callback that runs on a worker thread while that callback still **owns I/O logic, mutates the attachment, and updates `SelectionKey.interestOps()`** without synchronization. Instead of sharing complex mutable state, the example uses a simple approach: **only the event loop mutates connection state**, and workers only return immutable results.

## 3. APIs and Mechanisms You Must Understand

| API / Concept | Practical Role |
| --- | --- |
| `Selector.open()` | Creates an object that monitors registered channels |
| `ServerSocketChannel.configureBlocking(false)` | Puts the listener into non-blocking mode so it can be used with a selector |
| `SocketChannel.configureBlocking(false)` | Puts an accepted child connection into non-blocking mode before registration |
| `channel.register(selector, OP_READ, attachment)` | Registers the interest set and attaches connection state |
| `selector.select()` | Waits for readiness events or a wakeup/interrupt/close signal |
| `selector.selectedKeys()` | Set of keys reported ready; each key must be processed and removed from the set after handling |
| `SelectionKey.isAcceptable()/isReadable()/isWritable()` | Queries the readiness operations of a selected key |
| `key.interestOps(...)` | Adjusts the types of events to receive on the next select; driven by a state machine |
| `selector.wakeup()` | Wakes up a blocking select or causes the next select to return early |
| `ExecutorService.execute(...)` | Submits work to the pool; **does not wait for a result** |
| `ConcurrentLinkedQueue<Runnable>` | Example thread-safe queue for workers to hand completion steps back to the event loop |

**Readiness does not guarantee that I/O will complete in one call**: `OP_READ` does not promise a full request in a single `read()`; `OP_WRITE` does not mean a single `write()` sends the entire buffer. A socket in non-blocking mode can return `0` from `read()`/`write()`. You must track `ByteBuffer.position()`, `limit()`, `remaining()`, and framing state.

**`Selector.wakeup()` does not carry a business result.** It only affects the selector's waiting behavior. The result is placed in the **queue** first; the event loop drains the queue and applies it to the connection. You must preserve the ordering: **enqueue the completion first, then call wakeup**.

## 4. Per-Connection State and Ownership

Do not use shared global variables for every client's payload. Each `SelectionKey` should have an **attachment** holding its own state, for example:

```java
static final class Connection {
    final ByteArrayOutputStream request = new ByteArrayOutputStream();
    ByteBuffer response;
}
```

This is the simple structure used by the runnable program below: `request` accumulates ASCII bytes until a newline; `response` holds the unsent `OK:...` bytes. In a real-world server, the attachment typically holds more state:

| Category | Example Data to Retain |
| --- | --- |
| Framing | `ByteBuffer header`, expected body length, undecoded receive buffer, parser state |
| In-flight | Request ID, number of running jobs, deadline, cancellation state |
| Outbound | Response queue, `ByteBuffer` with remaining bytes (`remaining()`), pending byte count |
| Lifecycle | `OPEN`, `PROCESSING`, `WRITE_PENDING`, `CLOSING` |
| Resource safety | Frame size limit, request count limit, pending outbound byte limit, version/generation token |

**Ownership rule:** a worker must not directly read or mutate a `ByteBuffer` or attachment that the event loop is still modifying, unless there is an explicit synchronization contract. An easy-to-verify approach is to pass an **immutable request** to the worker (such as a `String` or a completed `byte[]` copy), and have the event loop receive an **immutable response**. The worker only needs to capture `SelectionKey` to build the completion closure; it **does not query or mutate the key on the worker**.

If a worker holds onto a byte array while the selector calls `clear()` and reads new packets into that same array, the business logic can end up using overwritten data. Avoiding copies requires explicit buffer ownership and lifetime management; for a foundational lesson, snapshotting decoded request data into an immutable object is safer.

## 5. Main Flow of the Demo Program

Minimal protocol:

- The client connects to the server over TCP via loopback.
- **One connection handles exactly one request**: the client sends a single **printable ASCII** line `hello\n`. Payload length is capped at 64 bytes, with no newlines inside the payload.
- The selector accepts the connection and reads data in non-blocking mode. When it sees `\n`, it marks the request complete, **disables `OP_READ` for this connection via `interestOps(0)`**, and submits the request to the pool.
- The worker processes the request: `hello` → `HELLO`, building the reply `OK:HELLO\n`. The worker puts a callback into the completion queue and calls `selector.wakeup()`. It **does not call `channel.write()`**.
- The event loop receives the completion; if the key is still valid, it sets the response `ByteBuffer` and switches the interest set to `OP_WRITE`.
- `OP_WRITE` writes partially according to `remaining()`. Once all bytes are sent, the server closes the connection (matching the one-request contract). The client receives one response line.
- The main thread sets the stop flag, wakes up the event loop, waits for the event loop thread to finish, and then shuts down the pool.

```text
Client                           Selector thread               Worker thread
  |                                    |                              |
  |-- "hello\n" --------------------->| OP_READ                      |
  |                                    | read+framing                 |
  |                                    | key.interestOps(0)           |
  |                                    | workers.execute(request) --->|
  |                                    |                              | process
  |                                    | continue selecting other keys |
  |                                    |                              | completions.add(result)
  |                                    |<------------ wakeup() -------|
  |                                    | apply result, OP_WRITE       |
  |<-- "OK:HELLO\n" -------------------| partial write if needed      |
  |                                    | close when all bytes written |
```

**Why not wait on `Future.get()` in the selector?** If the selector waits for the worker, all other connections suffer the same wait time. Completing via a callback/queue lets the selector immediately continue servicing other keys as soon as the job is submitted.

## 6. Standalone, Runnable Java 17+ Example

**Filename:** `SelectorWorkerDemo.java`.

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
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
import java.util.Locale;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public final class SelectorWorkerDemo {
    private static final int MAX_REQUEST = 64;

    static final class Connection {
        final ByteArrayOutputStream request = new ByteArrayOutputStream();
        ByteBuffer response;
    }

    static void close(SelectionKey key) {
        key.cancel();
        try {
            key.channel().close();
        } catch (IOException ignored) {
            // Already closing.
        }
    }

    static void accept(ServerSocketChannel listener, Selector selector)
            throws IOException {
        SocketChannel client = listener.accept();
        if (client == null) {
            return;
        }
        client.configureBlocking(false);
        client.register(selector, SelectionKey.OP_READ, new Connection());
    }

    static void read(SelectionKey key, ExecutorService workers,
            ConcurrentLinkedQueue<Runnable> completions, Selector selector)
            throws IOException {
        SocketChannel channel = (SocketChannel) key.channel();
        Connection state = (Connection) key.attachment();
        ByteBuffer buffer = ByteBuffer.allocate(256);
        int n = channel.read(buffer);
        if (n < 0) {
            close(key);
            return;
        }
        if (n == 0) {
            return;
        }
        buffer.flip();
        while (buffer.hasRemaining()) {
            int b = Byte.toUnsignedInt(buffer.get());
            if (b == '\n') {
                final String request = state.request.toString(
                        StandardCharsets.US_ASCII);
                key.interestOps(0); // Stop read notifications while processing.
                workers.execute(() -> {
                    // Slow/CPU-heavy business work would run here instead.
                    byte[] reply = ("OK:" + request.toUpperCase(Locale.ROOT)
                            + "\n").getBytes(StandardCharsets.US_ASCII);
                    completions.add(() -> {
                        if (key.isValid()) {
                            Connection current = (Connection) key.attachment();
                            current.response = ByteBuffer.wrap(reply);
                            key.interestOps(SelectionKey.OP_WRITE);
                        }
                    });
                    selector.wakeup();
                });
                return; // Protocol allows one request per connection.
            }
            if (b < 32 || b > 126 || state.request.size() >= MAX_REQUEST) {
                close(key);
                return;
            }
            state.request.write(b);
        }
    }

    static void write(SelectionKey key) throws IOException {
        SocketChannel channel = (SocketChannel) key.channel();
        Connection state = (Connection) key.attachment();
        channel.write(state.response);
        if (!state.response.hasRemaining()) {
            close(key); // One response per connection.
        }
    }

    static void loop(Selector selector, ServerSocketChannel listener,
            ExecutorService workers,
            ConcurrentLinkedQueue<Runnable> completions,
            AtomicBoolean running) throws IOException {
        while (running.get()) {
            Runnable completed;
            while ((completed = completions.poll()) != null) {
                completed.run(); // Run selector-key updates only in this thread.
            }
            selector.select();
            while ((completed = completions.poll()) != null) {
                completed.run();
            }
            Iterator<SelectionKey> it = selector.selectedKeys().iterator();
            while (it.hasNext()) {
                SelectionKey key = it.next();
                it.remove();
                if (!key.isValid()) {
                    continue;
                }
                try {
                    if (key.isAcceptable()) {
                        accept(listener, selector);
                    } else {
                        if (key.isReadable()) {
                            read(key, workers, completions, selector);
                        }
                        if (key.isValid() && key.isWritable()) {
                            write(key);
                        }
                    }
                } catch (IOException | RuntimeException ex) {
                    close(key);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getLoopbackAddress();
        try (Selector selector = Selector.open();
             ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.configureBlocking(false);
            listener.bind(new InetSocketAddress(local, 0));
            listener.register(selector, SelectionKey.OP_ACCEPT);

            ExecutorService workers = Executors.newFixedThreadPool(2);
            ConcurrentLinkedQueue<Runnable> completions =
                    new ConcurrentLinkedQueue<>();
            AtomicBoolean running = new AtomicBoolean(true);
            AtomicReference<Throwable> error = new AtomicReference<>();
            Thread eventLoop = new Thread(() -> {
                try {
                    loop(selector, listener, workers, completions, running);
                } catch (Throwable ex) {
                    error.set(ex);
                }
            }, "selector-loop");
            eventLoop.start();
            try (Socket client = new Socket(local,
                    ((InetSocketAddress) listener.getLocalAddress()).getPort())) {
                client.setSoTimeout(5000);
                BufferedWriter out = new BufferedWriter(
                        new OutputStreamWriter(client.getOutputStream(),
                                StandardCharsets.US_ASCII));
                BufferedReader in = new BufferedReader(
                        new InputStreamReader(client.getInputStream(),
                                StandardCharsets.US_ASCII));
                out.write("hello\n");
                out.flush();
                System.out.println("client sent: hello");
                String response = in.readLine();
                if (!"OK:HELLO".equals(response)) {
                    throw new IOException("Unexpected response: " + response);
                }
                System.out.println("client received: " + response);
            } finally {
                running.set(false);
                selector.wakeup();
                eventLoop.join(5000);
                workers.shutdownNow();
                if (eventLoop.isAlive()) {
                    throw new IllegalStateException("Loop did not stop");
                }
            }
            if (error.get() != null) {
                throw new IllegalStateException("Selector loop failed", error.get());
            }
            System.out.println("selector loop stopped");
        }
    }
}
```

Compile and run:

```bash
javac --release 17 SelectorWorkerDemo.java
java SelectorWorkerDemo
```

Stdout on a successful run:

```text
client sent: hello
client received: OK:HELLO
selector loop stopped
```

**Reading the example accurately:** the client receiving `OK:HELLO` proves the response frame was transmitted over TCP to the client, not just that the pool finished running. The test code does not print thread names, so parallel execution timing is not directly visible in stdout; the non-blocking `workers.execute(...)` structure and completion handling on the event loop are the **code-level** evidence of decoupling. You can observe this further with a debugger, thread dump, or by extending the test to two clients.

**Intentional limitations of the demo:** one ASCII line per connection; bytes after the newline in the same read are not treated as a second request; the server closes after sending the response. Therefore, the example **does not implement HTTP, keep-alive, pipelining, Unicode support, or multiple consecutive frames**, and it has no global server-side deadline mechanism. `ByteBuffer.allocate(256)` is allocated per read-ready event for simplicity; production systems usually retain/reuse a per-connection receive buffer, while still managing ownership carefully.

`Executors.newFixedThreadPool(2)` in the example has an **unbounded task queue in its default configuration**; it is only suitable for illustration and **should not be copied as-is into a system facing untrusted load**. Section 9 replaces it with a bounded queue.

## 7. Why `interestOps(0)` Only Applies to the Connection Currently Being Processed

Suppose two clients A and B are connected simultaneously:

```text
A: READ request A -> submit worker A -> keyA.interestOps(0)
B: keyB still has OP_READ -> selector still accepts input from B
A: worker A finishes -> completion A -> keyA.interestOps(OP_WRITE)
B: is not blocked by connection A
```

Only **keyA** pauses read notifications; other keys continue to be served normally. This works well when **each connection may have at most one in-flight request**, such as a sequential protocol. If more bytes remain in the OS receive buffer, they may continue accumulating: disabling `OP_READ` does not discard data, but it limits processing at the application layer. With one request per connection like in the demo, the server closes the socket after sending the response.

**Do not overuse `interestOps(0)` when a protocol requires full-duplex** (such as server push) or multiple in-flight requests on the same connection: in those cases, read/write control must follow pipelining, quota, and ordering rules rather than unconditionally disabling reads. You can keep `OP_READ | OP_WRITE` when both reading is possible and outbound bytes are pending, provided reading does not exceed the connection's processing budget.

**Important pitfall:** `key.interestOps(SelectionKey.OP_WRITE)` in the callback **replaces the entire interest set**. In a multi-request protocol, this can accidentally drop `OP_READ`. When you need both reading and writing, use the appropriate bitwise OR according to your state machine and toggle each bit deliberately. In the demo, replacing the set is **correct** because each connection has only one request, and it is waiting to write the response and then close.

## 8. Workers Report Completion via Queue + `selector.wakeup()`

The key structure in the demo:

```java
// Worker thread: only build the result, do not mutate connection/key.
byte[] reply = ("OK:" + request.toUpperCase(Locale.ROOT) + "\n")
        .getBytes(StandardCharsets.US_ASCII);
completions.add(() -> {
    // This closure runs ONLY on the event loop thread.
    if (key.isValid()) {
        Connection state = (Connection) key.attachment();
        state.response = ByteBuffer.wrap(reply);
        key.interestOps(SelectionKey.OP_WRITE);
    }
});
selector.wakeup();
```

*This is a code fragment from the handler and worker in the runnable program; the variables `request`, `completions`, `key`, and `selector` must be in scope.*

Why both steps are needed:

1. **The queue** is the channel for passing data/commands from workers to the event loop. `ConcurrentLinkedQueue` allows multiple workers to enqueue completions safely.
2. **Wakeup** ensures an event loop blocked in `selector.select()` does not have to wait for another network readiness event before checking the completion queue.

If a worker **only calls wakeup without enqueuing**, the event loop has no idea what response to write. If a worker **only enqueues without calling wakeup**, the event loop can remain stuck in `select()` when no new network events arrive, delaying the response indefinitely. The sample loop drains the queue **both before and after** `select()` to handle callbacks that arrive right around the wakeup window.

`Selector.wakeup()` is designed to be called from another thread; it does not mean a worker is allowed to call `selectedKeys().clear()` or arbitrarily mutate attachments. When a client closes a connection while a worker is processing, the completion may arrive late. The demo checks `key.isValid()` and discards the result if the key was canceled; a production version also needs **generation/request ID** protection so a stale request's response is never attached to new state.

## 9. Bounded Worker Pool and Backpressure

An event loop that reads very fast while workers process slowly can **push the number of queued jobs up without bound**. For example, if 10,000 clients send requests at once, even with only two workers processing, `Executors.newFixedThreadPool(2)` can accumulate many jobs in its queue. Each job holds references to the request, response, and key; memory usage, latency, and shutdown time can grow continuously.

In a real system, consider a **bounded `ThreadPoolExecutor`**:

```java
// Configuration snippet for a production prototype (requires importing the classes).
ThreadPoolExecutor workers = new ThreadPoolExecutor(
        2, 2,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(128),
        new ThreadPoolExecutor.AbortPolicy());
```

*This snippet is self-contained in terms of configuration intent, but must be placed in a class that imports `java.util.concurrent.ThreadPoolExecutor`, `ArrayBlockingQueue`, and `TimeUnit`; shutdown lifecycle must also be managed.* When both workers are busy and the queue is full, `execute(...)` can throw `RejectedExecutionException`. The event loop **must not casually run the business logic inline to "rescue" a rejection**; doing so would block the selector during the very overload situation you are trying to survive.

Several ways to handle a full queue:

- Send a `BUSY`/`429`/`503` response according to the **application protocol** if the connection and protocol allow it, then close or wait for the next turn.
- Pause `OP_READ` on some connections within a budget, but there must be a mechanism to **re-enable reading** when pressure drops. If disabled without a resume path, the connection stalls.
- Limit the number of connections, in-flight jobs per connection, total pending response bytes, and timeouts; reject new requests when budgets are exceeded.
- Only use `CallerRunsPolicy` when you intentionally accept the caller running the job. **It is unsuitable by default** if the caller is the selector thread: it will execute the business task synchronously and break the non-blocking event loop requirement.

Each workload type requires sizing the pool appropriately: CPU-bound work is typically limited by core count; blocking I/O may need more workers, though asynchronous client/database APIs should be used where appropriate. Do not pick a thread count simply by making it huge: context switching, connection pool/DB limits, and contention can become bottlenecks.

**Backpressure is controlling the rate of work generation so it does not exceed the rate of consumption.** A bounded queue combined with rejection/read-pausing mechanisms can keep memory stable; merely increasing the worker count or `SO_RCVBUF` does not solve sustained overload.

## 10. Handling Partial Reads and Partial Writes on the Event Loop

A `SocketChannel` in non-blocking mode may only read or write partially:

```text
OP_READ:
  read() > 0 : append bytes to the per-connection decoder
  read() == 0: no new bytes; wait for another readiness event
  read() == -1: EOF; handle any incomplete request and close

OP_WRITE:
  write(buffer) > 0: buffer.position advances
  write(buffer) == 0: socket cannot accept more bytes yet; wait for OP_WRITE
  buffer.hasRemaining() == false: response has been completely written to the channel
```

In the demo, `write(...)` is called only once per ready event. If `response.hasRemaining()` is still `true`, `interestOps(OP_WRITE)` remains set, so the loop receives the next writable event and sends the rest. **Do not `rewind()` or `clear()` the response buffer between partial writes**, as that will send duplicate data or lose bytes.

For input parsing, the demo accumulates bytes until `\n`, enforces a 64-byte limit, and rejects non-printable ASCII bytes. For production binary framing, use a state machine:

```text
READ_FIXED_HEADER
    -> enough header length, validate 0 <= L <= MAX
READ_BODY
    -> accumulate L bytes, possibly across multiple read events
SUBMIT_WORK
    -> pause/limit OP_READ
WAIT_WORKER
    -> completion queue + wakeup
WRITE_RESPONSE
    -> preserve buffer position across multiple OP_WRITE events
READY_FOR_NEXT_FRAME or CLOSE
```

**TCP does not preserve write boundaries:** multiple client `write()` calls can be coalesced into a single `read()`; a single frame can arrive across multiple `read()` calls. Never assume one readiness event equals one message. If a client sends two frames on the same socket and the protocol allows it, the parser must retain any leftover bytes after the first frame to process the second frame. The demo intentionally does **not** implement this case.

## 11. Ensuring Response Ordering and Avoiding Race Conditions

When a connection allows multiple concurrent requests, completions may return **out of submission order**. For example:

```text
Request #10 -> worker A takes 400 ms
Request #11 -> worker B takes  30 ms
Completion #11 may arrive before #10
```

There are three design choices depending on the protocol:

1. **Sequential per connection:** only one in-flight request; disable `OP_READ` until the response finishes. Easy to preserve ordering, but causes head-of-line blocking **within that connection**.
2. **Allow out-of-order responses:** each request/response carries a `requestId`, and the client matches responses by ID. Requires synchronized frame sending and result routing.
3. **Process in parallel but reply in order:** buffer results by sequence ID and only write responses once all preceding results are ready. Can consume memory and cause head-of-line blocking on the response path.

Do not let multiple workers call `channel.write()` directly on the same socket without a writer queue or serialization. Two tasks could interleave header/body bytes and corrupt framing. Owning write state on the event loop keeps a single serialized stream per connection.

Every job needs a **cancellation and expiration** policy: if the client disconnects, a worker may still be performing useless work. The callback must check whether the key is still valid; if the operation has side effects, client-side cancellation does not mean the backend has not committed. Important transactions require an idempotency key, a deadline, and proper processing-state tracking.

## 12. Exception Handling, Connection Closure, and Shutdown

In the example, an `IOException` or `RuntimeException` while handling a ready key cancels the key and closes the channel. This is a clean illustration: a failing connection does not crash the entire event loop. **Production** requires additional deliberate handling:

- **Worker exceptions:** wrap processing in `try/catch`, turning it into a success/failure result or an error response. If a worker throws an exception before enqueuing a completion, the key can remain stuck at `interestOps(0)` forever, hanging the client. There must always be a completion, error-reporting, or close path.
- **Queue rejection:** catch `RejectedExecutionException` at submission time. Return a valid error/rejection or close the connection; do not run long tasks on the selector thread.
- **Channel closed while job is running:** late completions must be discarded without re-registering `OP_WRITE` on a canceled key; release buffers and references when no longer needed.
- **Worker taking too long:** enforce per-request timeouts/deadlines and cancel when appropriate. `Future.cancel(true)` only requests thread interruption; business code and libraries must respect interruption. Do not treat cancellation as proof that side effects did not happen.
- **Selector crash:** an uncaught exception outside the per-key handler can stop the event loop completely. Log the error, alert monitoring, clean up all connections, and apply a restart policy.
- **Graceful shutdown:** stop accepting new connections, stop submitting new jobs, wait for or cancel jobs up to a deadline, flush or cancel pending responses, wake up the selector, close channels/selector, and then shut down the pool. Avoid having worker callbacks mutate keys after the selector is closed.
- **Do not block shutdown indefinitely:** `join()`/`awaitTermination()` on the **main/manager thread** can be valid, but never place that wait inside the event loop that is supposed to process I/O.

The demo code uses `AtomicBoolean running` to request shutdown, `selector.wakeup()` to exit `select()`, and `eventLoop.join(5000)` on the **main thread**. `workers.shutdownNow()` stops the pool quickly for demo purposes; production systems should design graceful shutdown appropriate for jobs with business impact.

Another risk: a callback itself can throw an exception. Because closures run on the event loop, an uncaught exception can break the main loop. Keep what callbacks do minimal and add dedicated error handling when building large systems.

## 13. Fairness, Latency, and Observability

When thousands of channels are ready, the event loop must distribute its time fairly:

- Do not let a single connection monopolize CPU with an unbounded processing loop. Set a **maximum byte/frame budget per iteration** and continue in the next iteration.
- Do not perform heavy decoding, gzipping, or JSON parsing directly on the event loop; keep only the parsing needed to determine frame boundaries and basic validity, and offload heavy work to workers.
- Bound response sizes and pending outbound bytes; if a client reads slowly, the write queue can balloon. Enable `OP_WRITE` only when there is actually data to send.
- Prevent one client's errors from affecting other connections. Do not write high-volume synchronous logs on the selector thread if the logging backend can block.
- For synchronous I/O tasks in workers, remember that even though the event loop remains non-blocking, the **worker pool** can still saturate; measure queue length and wait time, not just the selector loop.

Useful metrics:

| Metric | Description |
| --- | --- |
| `selector loop iteration latency` | Time per select cycle and ready-key processing |
| `ready keys processed / iteration` | Number of connections/events serviced |
| `worker queue depth` | Number of queued tasks, indicating backlog |
| `worker queue wait time` | Time from submission until execution begins |
| `worker execution latency` | Actual processing duration |
| `in-flight requests` | Unfinished requests per connection and server-wide |
| `pending write bytes` | Total response bytes waiting for `OP_WRITE` |
| `timeouts/rejections/failed completions` | Signs of overload or response-path failures |

Log `connectionId`, `requestId`, read/worker/write states, and timestamps; **do not log sensitive payloads**. If selector loop latency spikes when the pool is full, check whether `CallerRunsPolicy`, `Future.get()`, synchronized locks, or heavy parsing accidentally crept onto the event loop.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling blocking JDBC/HTTP directly in `isReadable()` | Selector misses servicing other connections | Offload to workers or use async APIs |
| Submitting work and immediately calling `Future.get()` | Event loop still blocks | Use a completion queue/callback; never wait on the I/O thread |
| Worker mutates attachment/`interestOps` without ownership | Races and hard-to-verify state | Worker sends completion; event loop applies it |
| Enqueuing completion but forgetting `selector.wakeup()` | `select()` may wait indefinitely when no I/O events occur | Enqueue first, then call wakeup |
| Calling wakeup without a queue/result | Selector does not know what response to write | Pass commands/results via a thread-safe queue |
| Keeping `OP_WRITE` enabled with no output | Selector reports writable continuously, causing CPU spin | Enable only when a response is pending |
| Calling `write()` once and ignoring `remaining()` | Unsent portion of the response is lost | Keep the `ByteBuffer` and continue writing on `OP_WRITE` |
| Treating `read() == 0` as connection close | Accidentally closes a non-blocking channel | Distinguish `0`, `-1`, and exceptions |
| Disabling `OP_READ` with no path to re-enable | Connection becomes "frozen" | State machine with resume or write/close |
| Leaving the worker queue unbounded under high load | Memory and latency grow without bound | Bounded pool, rejection/backpressure |
| Using `CallerRunsPolicy` by default on the selector | Business tasks run on the selector during overload | Never run long tasks on the caller |
| Worker exception fails to produce a completion | Key waits forever | Error completion + deadline/cleanup |
| Sending multiple frames concurrently from multiple writers on one channel | Bytes from different frames interleave | Single writer/response queue per connection |
| Not validating frame size | Excessive allocations, DoS | Enforce size and time limits |
| Worker response arrives after channel closes | Stale result or invalid key access | Check key validity and request generation |
| One client creates too many in-flight requests | Worker pool and outbound queue saturate | Per-client quotas and flow control |

## 15. Comprehension Exercises

**Exercise 1.** In the `OP_READ` callback, the server submits a 2-second job and calls `future.get()`. If 2,000 other connections are ready, how are they affected? How should the architecture be changed?

**Exercise 2.** A worker creates a response and puts it into `ConcurrentLinkedQueue` but forgets `selector.wakeup()`. If no new network events arrive, what can happen to the client?

**Exercise 3.** A response is 10,000 bytes long; the first `SocketChannel.write(buffer)` writes only 3,000 bytes. What should the event loop do with `buffer.position()` and `OP_WRITE`?

**Exercise 4.** Why can `interestOps(SelectionKey.OP_WRITE)` be fine when each connection has only one request, yet dangerous when the protocol allows continuing to read other requests?

**Exercise 5.** A worker pool has two threads and a queue capacity of 100; all are busy. If the system uses `CallerRunsPolicy` and `workers.execute()` is called directly from the selector thread, what happens when the queue is full?

**Exercise 6.** A client disconnects before a job finishes; the worker returns a response. Why must you not unconditionally call `key.interestOps(OP_WRITE)`? Besides `key.isValid()`, what additional information does a multi-request system need to track?

**Exercise 7.** When a server supports two concurrent requests A/B on the same socket and worker B finishes before A, how does the client know which response corresponds to which request? If the protocol requires in-order responses, what must the server manage?

**Suggested Answers:**

1. The event loop is blocked for 2 seconds, delaying all other ready connections. Submit without waiting; have the worker post a completion and wake up the selector.
2. The event loop may stay stuck in `select()`; `OP_WRITE` is not enabled promptly for the response. Call wakeup after enqueuing.
3. Preserve `position` already advanced by 3,000 bytes, keep `OP_WRITE` interest, and continue writing `remaining() == 7,000` bytes when writable; do not rewind.
4. Assigning directly replaces the entire interest set, dropping `OP_READ` if further reads are needed. Manage the bitmask according to the state machine.
5. The policy runs the job on the **caller**—the selector thread—forcing the event loop to execute the business task synchronously and causing head-of-line blocking.
6. The connection/key may already be closed; stale callbacks must be discarded. Multi-request connections also need request ID/generation tracking, cancellation, and lifecycle management.
7. Attach `requestId` to each response; if in-order delivery is required, maintain a reorder buffer by sequence number and emit responses only when all preceding requests have completed.

## Official References

- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): `select()`, `wakeup()`, and `selectedKeys()`.
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): `interestOps`, ready operations, validity, and attachment.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): `configureBlocking(false)`, partial read/write.
- [Java SE 17 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): non-blocking accept.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit/execute, lifecycle.
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): bounded queue, rejection policies, and pool sizing.
- [Java SE 17 — ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): thread-safe queue for completions.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `flip`, `remaining`, and partial I/O.
