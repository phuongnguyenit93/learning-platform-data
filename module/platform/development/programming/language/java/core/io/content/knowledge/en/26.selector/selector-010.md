# Avoiding Busy Loops, Handler Stalls, and Unsafe Shared Buffers with Java NIO Selector

## 1. Goal: Wait Properly, Process Fast, and Keep Data Ownership Clear

`java.nio.channels.Selector` allows a single thread to monitor many non-blocking channels and act when they are ready to read, write, accept connections, or finish connecting. The effectiveness of this model depends on three key decisions:

1. **No pointless spinning (*busy loop*)**: do not repeatedly call `selectNow()` or `read()`/`write()` when no progress occurs; do not leave `OP_WRITE` enabled when no bytes remain to send.
2. **Do not let one connection stall the entire event loop**: a slow, CPU-heavy, or blocking callback/API call delays every other channel on the selector.
3. **Do not unsafely share mutable buffers**: `ByteBuffer` holds both data and `position`, `limit`, and `mark`; sharing the same buffer across connections or workers without clear ownership rules can corrupt data, lose bytes, or leak data from another connection.

A selector *does not* orchestrate business work, backpressure, buffer permissions, or memory visibility by itself. It only notifies you of channel operations that are **likely able** to make progress. Your program must properly combine the selector, connection state, and protocol for toggling `interestOps`.

## 2. Understanding Selector.select() and Readiness Properly

A typical selector loop:

~~~java
try (Selector selector = Selector.open()) {
    while (running) {
        selector.select(); // wait for readiness or wakeup
        Iterator<SelectionKey> iterator = selector.selectedKeys().iterator();
        while (iterator.hasNext()) {
            SelectionKey key = iterator.next();
            iterator.remove();
            if (!key.isValid()) continue;
            // Check key.isAcceptable()/isConnectable()/isReadable()/isWritable()
        }
    }
}
~~~

This is an **illustrative skeleton** meant to live inside a program with imports, a `running` variable, and actual channel handling. Do not use this skeleton as a complete server: it has not registered any channel yet, so it does no useful work.

- `selector.select()` blocks until a key is ready, `wakeup()` is called, the thread is interrupted, or another API condition occurs. It **can return 0**, so never assume every return from `select` has I/O to perform.
- `selector.select(timeout)` waits at most the specified positive duration; on timeout it can return 0. Per the API, **a timeout of 0 equals waiting indefinitely**, not immediate polling.
- `selector.selectNow()` checks immediately without blocking. Calling it continuously in `while(true)` creates CPU-burning polling when no data exists.
- `key.readyOps()`/`key.isReadable()` reflects readiness recorded by the selection pass, **not** proof that a single operation is guaranteed to transfer bytes. You must check actual `read`/`write` results.
- `key.interestOps(...)` is the set of events the application wants to monitor. Bits like `OP_READ`/`OP_WRITE` are not immediate read/write commands; they decide which events wake the event loop.
- `selector.selectedKeys()` is the set of selected keys. You must remove each key when handling it, usually via `iterator.remove()`. Leaving it in place lets the same key be processed over and over with no new events.
- A single key can be ready for multiple operation types. Check validity and channel state after each operation, because one handler can close or `cancel()` the key.

Clearly distinguish the **selected-key set** (already selected) from the **registered-key set** (registered). Removing from the selected-key set does not cancel registration; `key.cancel()` cancels the key, and the channel must be closed when no longer used.

## 3. Three Common Types of Busy Loops

### 3.1. Infinite Polling with selectNow()

**Wrong:**

~~~java
while (running) {
    selector.selectNow();
    processReadyKeys(selector);
}
~~~

This is Java pseudocode (`processReadyKeys` is an application-supplied method). When there is no readiness, the loop never sleeps and spins immediately, keeping a CPU core nearly 100% busy.

**Better:** use `select()` when there is no deadline, or `select(timeout)` with a genuinely needed timeout (for example, to process scheduled tasks). For internal work submitted by another thread, coordinate via a queue and call `selector.wakeup()` when adding new work. Do not sprinkle arbitrary `Thread.sleep(1)` calls to patch a broken polling design.

### 3.2. `read()==0` and `write()==0` Loops

In non-blocking mode:

~~~java
int count = channel.read(input);
if (count == 0) {
    // No bytes available right now; wait on selector.
}
if (count == -1) {
    // Peer ended its send direction: handle EOF state or close.
}
~~~

This is an illustrative snippet; `channel` and `input` must exist. `read()==0` is not EOF. If `input` has no remaining space (`!input.hasRemaining()`), you must process/compact the buffer instead of waiting to read more.

Similarly, non-blocking `write(output)` can consume **part or 0 bytes** when the socket cannot accept more data right now. If `output.hasRemaining()`, keep the buffer and register `OP_WRITE`; when write readiness arrives, try writing again. Do not busy-spin:

~~~java
while (output.hasRemaining()) {
    channel.write(output); // WRONG in non-blocking mode if write repeatedly returns 0.
}
~~~

In blocking mode, waiting to write more may fit a blocking call, but the code above is a common bug when `channel.configureBlocking(false)` is set with no readiness wait mechanism.

### 3.3. Keeping `OP_WRITE` Enabled Even With No Outbound Data

A socket is frequently able to accept more outbound bytes. If you register `OP_WRITE` unconditionally:

~~~java
key.interestOps(SelectionKey.OP_READ | SelectionKey.OP_WRITE);
~~~

and keep the `OP_WRITE` bit set even when the outbound queue is empty, `select()` can return repeatedly because the socket remains writable. This is a common reason an event loop consumes high CPU even under zero application load.

**Rule:** register `OP_WRITE` **only while data is waiting to be sent**. Once all output is written, remove `OP_WRITE`:

~~~java
// When outbound transitions from empty to having data:
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);

// Inside the writable handler, after draining all pending outbound data:
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
~~~

This is illustrative event-loop code, assuming `key` is valid. If a channel serves just one request and finishes, close/cancel the key once flushed rather than leaving unnecessary `OP_READ` active. When multiple outbound frames exist, remove `OP_WRITE` only once **the entire outbound queue** is empty, not just when one buffer finishes.

## 4. Runnable Java 17+ Example: One Event Loop, Dedicated Buffers, Conditional OP_WRITE

The following example runs a server on loopback with a non-blocking `ServerSocketChannel` and an independent client using a blocking `SocketChannel`. The client sends a single newline-terminated request; the server receives the request, switches to watching only `OP_WRITE` once a response is ready, and closes the socket after flushing. Each server-side socket gets its own `Connection` object holding dedicated `ByteBuffer`/state inside `SelectionKey.attachment()`.

Create file **`SelectorSafeDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SelectorSafeDemo {
    static final class Connection {
        final ByteBuffer input = ByteBuffer.allocate(128);
        final ByteArrayOutputStream request = new ByteArrayOutputStream();
        ByteBuffer output;
    }

    public static void main(String[] args) throws Exception {
        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            server.configureBlocking(false);
            server.register(selector, SelectionKey.OP_ACCEPT);

            ExecutorService clients = Executors.newSingleThreadExecutor();
            try {
                Future<String> result = clients.submit(() -> {
                    try (SocketChannel channel = SocketChannel.open()) {
                        channel.connect(server.getLocalAddress());
                        ByteBuffer request = ByteBuffer.wrap(
                                "ping\n".getBytes(StandardCharsets.UTF_8));
                        while (request.hasRemaining()) channel.write(request);
                        channel.shutdownOutput();
                        ByteBuffer response = ByteBuffer.allocate(32);
                        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                        while (true) {
                            int n = channel.read(response);
                            if (n == -1) break;
                            response.flip();
                            while (response.hasRemaining()) bytes.write(response.get());
                            response.clear();
                        }
                        return bytes.toString(StandardCharsets.UTF_8).trim();
                    }
                });

                int completed = 0;
                while (completed < 1) {
                    if (selector.select(2000) == 0) {
                        throw new IOException("Timed out waiting for ready channels");
                    }
                    Iterator<SelectionKey> selected = selector.selectedKeys().iterator();
                    while (selected.hasNext()) {
                        SelectionKey key = selected.next();
                        selected.remove();
                        if (!key.isValid()) continue;
                        if (key.isAcceptable()) {
                            SocketChannel peer = server.accept();
                            if (peer != null) {
                                peer.configureBlocking(false);
                                peer.register(selector, SelectionKey.OP_READ, new Connection());
                            }
                        } else {
                            SocketChannel peer = (SocketChannel) key.channel();
                            Connection state = (Connection) key.attachment();
                            if (key.isReadable()) {
                                int n = peer.read(state.input);
                                if (n < 0) {
                                    throw new IOException("Request truncated before newline");
                                }
                                if (n > 0) {
                                    state.input.flip();
                                    while (state.input.hasRemaining()) {
                                        byte value = state.input.get();
                                        if (value == '\n') {
                                            System.out.println("Server received: " +
                                                    state.request.toString(StandardCharsets.UTF_8));
                                            state.output = ByteBuffer.wrap(
                                                    "PONG\n".getBytes(StandardCharsets.UTF_8));
                                            key.interestOps(SelectionKey.OP_WRITE);
                                            break;
                                        }
                                        state.request.write(value);
                                        if (state.request.size() > 64) {
                                            throw new IOException("Request too long");
                                        }
                                    }
                                    state.input.compact();
                                }
                            }
                            if (key.isValid() && key.isWritable()) {
                                peer.write(state.output);
                                if (!state.output.hasRemaining()) {
                                    key.cancel();
                                    peer.close();
                                    completed++;
                                }
                            }
                        }
                    }
                }
                System.out.println("Client received: " + result.get());
                System.out.println("Completed: " + completed);
            } finally {
                clients.shutdownNow();
            }
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac SelectorSafeDemo.java
java SelectorSafeDemo
~~~

Output **verified by compiling and running**:

~~~text
Server received: ping
Client received: PONG
Completed: 1
~~~

### Why Does the Example Avoid the Three Target Pitfalls?

1. **No busy loop:** the server uses `selector.select(2000)` and processes only ready keys; it does not call `selectNow()` endlessly. The 2-second limit here is a *demo timeout*, not a fixed production recommendation.
2. **No pointless `OP_WRITE`:** newly connected clients start with `OP_READ` interest only. Upon seeing newline and creating the response, the server switches interest to `OP_WRITE`. Once the response bytes are fully written, the server closes the channel. For long-lived connections, instead of closing, clear the `OP_WRITE` bit and keep appropriate interests.
3. **No sharing buffers across connections:** each `accept()` creates a dedicated `Connection`. `state.input` and `state.output` are used exclusively within the single event loop via `key.attachment()`.
4. **Handles partial writes:** `peer.write(state.output)` writes only the bytes it can accept right away. If bytes remain, the buffer keeps its `position` and `OP_WRITE` stays active so the next writable event finishes sending. Never call `clear()` before sending completes.
5. **Minimal framing handling:** requests end with a newline, bounded to 64 bytes. The server does not assume one `read` always equals one message. If EOF arrives before newline, it reports a truncated request.
6. **Handled selected keys are removed from the selected set** via `selected.remove()`. This differs from `key.cancel()`: canceling registration occurs only once the response is complete and the server intentionally closes the connection.

**Intentional limitations of the demo:** handles exactly **one short ASCII request and one response** on one connection, then stops. Once it sees newline, the demo does not retain extra bytes to parse a subsequent request; it is not a multi-message parser. The client runs separately using blocking I/O for simplicity of observation; only the server uses Selector. Production code must ensure closing all accepted channels even on errors/timeouts, cap connection counts, protect queues, parse multiple frames if required, and manage cancellation, deadlines, and full server shutdown. When extending to a persistent protocol, use an outbound queue structure instead of a single `state.output`.

## 5. Why Does One Slow Handler Stall All Connections?

An event loop uses **one thread** to process many keys. While handling key A, that thread has not yet returned to check key B. If the handler for A performs a blocking action, every other connection on that selector must wait, even if their sockets are ready.

Example of dangerous behavior inside a handler:

~~~java
if (key.isReadable()) {
    int n = socket.read(buffer);
    // After reading, perform 10 seconds of heavy CPU work,
    // synchronous JDBC calls, or blocking HTTP requests right here.
}
~~~

This is illustrative code. Common stall culprits include synchronous DB queries, blocking HTTP clients, `Thread.sleep()`, holding mutex locks for long periods, parsing massive JSON payloads, heavy encryption, logging to slow blocking I/O, or calling an async API and immediately invoking `future.get()` on the event loop.

Observable consequences:

- Latency spikes across many connections simultaneously, even when each client sends very little data.
- Read buffers are not drained promptly, putting pressure on kernel receive buffers; senders slow down via TCP flow control.
- Pending output is not flushed, causing response queues to grow and holding connections and resources longer.
- Application-layer timers and timeouts can fire late if they run on the same stalled thread.
- Registering more channels on the same selector does not give the event loop extra CPU cores.

**Design direction:** the event loop should only perform non-blocking I/O, lightweight frame parsing, small state updates, and task scheduling. Heavy CPU or blocking tasks are offloaded to a bounded worker pool. Workers return results via a thread-safe queue; the event loop drains results, creates outbound buffers, enables `OP_WRITE`, and continues. Never let workers directly mutate buffers currently used by the event loop.

## 6. Offloading Heavy Tasks While Preserving Ownership and Ordering

A safe architecture can look like:

~~~text
SocketChannel (non-blocking)
      │ OP_READ
      ▼
Selector thread ── decode frame / check limits
      │
      ├─ copy immutable input / hand off ownership
      ▼
Bounded worker queue → Worker handles blocking/CPU-heavy work
      │
      └─ immutable result / outbound bytes
                   ▼
          Thread-safe completion queue
                   │ selector.wakeup()
                   ▼
Selector thread → queue bytes → enable OP_WRITE → write partial → drain
~~~

Key principles:

- **Only one owner manipulates a read/write buffer's cursors at a time.** The event loop can pass a byte snapshot to a worker; once ownership is genuinely transferred, it must not `compact/clear/put` on that same buffer until the worker returns it.
- **Do not pass a mutable `ByteBuffer` reference to a worker and immediately reuse it for further reads.** The worker could observe `position/limit` changing mid-processing; decoding can corrupt or throw `BufferUnderflowException`.
- **Bounded queues** cap pending tasks. If workers cannot keep up, throttle or temporarily disable `OP_READ` on affected connections or reject overload per policy. Never use unbounded queues, as memory can grow until OOM.
- **Worker results must carry connection generation/id** and be discarded if the socket/key has closed or the request timed out. Avoid sending late responses on a newly recycled channel ID.
- **Preserve response ordering** if required by the protocol: multiple workers can finish out of request order. Use sequence numbers, per-connection queues, or limit to one in-flight task per connection.
- **Selector wakeup protocol:** another thread can append results to the completion queue and call `selector.wakeup()`. When `select()` returns, the event loop drains the queue and updates interest ops. Never assume an off-thread writer calling `key.interestOps(...)` guarantees the event loop wakes immediately.
- **Never call `Future.get()` inside the event loop** to wait for a worker: that turns offloading back into blocking, defeating the selector.

Illustrative example of passing notifications between worker and event loop, **not a standalone program**:

~~~java
// On worker:
completedResults.add(new Result(connectionId, requestId, outputBytes));
selector.wakeup();

// On event loop, after select() returns:
Result done;
while ((done = completedResults.poll()) != null) {
    // Verify key is still valid and request still expects a result.
    // Create a dedicated ByteBuffer from outputBytes or transfer ownership explicitly.
    // Enqueue into the connection's own outbound queue.
    // Enable OP_WRITE if the queue just transitioned from empty to non-empty.
}
~~~

`completedResults` must be a thread-safe queue, and `Result` is an application-defined type. Calling `selector.wakeup()` **does not transfer data on behalf of the queue** and does not make an arbitrarily shared `ByteBuffer` thread-safe.

## 7. Never Share ByteBuffer Unsafely

A `ByteBuffer` has two kinds of state to protect:

1. **Cursor metadata**: `position`, `limit`, `mark`. Calls like `get()`, `put()`, `flip()`, `clear()`, and `compact()` mutate them.
2. **Backing bytes**: the byte array or direct/mapped memory region. Two distinct buffer objects can still share the same underlying storage.

A common bug:

~~~java
ByteBuffer sharedInput = ByteBuffer.allocate(8192);

// Inside every OP_READ handler across multiple sockets:
int n = channel.read(sharedInput);
sharedInput.flip();
consume(sharedInput);
sharedInput.clear();
~~~

This is illustrative code: `consume` is supplied by the application. When multiple connections share `sharedInput` and data arrives interleaved, it is easy to read client A's bytes as client B's bytes. Even though handlers execute sequentially on one event loop, if a parser needs to retain an incomplete frame across reads, calling `clear()` on a global buffer between connections **destroys partial state**. Buffer sharing becomes even more dangerous when offloading to workers.

### 7.1. One Connection, One Inbound State and Outbound Queue

In larger programs, store per-connection state in `SelectionKey.attachment()`:

~~~java
final class ConnectionState {
    final ByteBuffer input = ByteBuffer.allocate(8192);
    final Deque<ByteBuffer> outbound = new ArrayDeque<>();
    boolean inputEof;
    long queuedBytes;
}
~~~

This is an **illustrative class**; imports for `ByteBuffer`, `Deque`, and `ArrayDeque` are needed. It fits an exclusively owned event loop; **`ArrayDeque` is not a thread-safe queue**. When a worker produces a response, post the result through the completion queue; the event loop updates `outbound` and `queuedBytes`.

Each connection maintains its own parser state: incomplete frame bytes, expected frame length, closing state, watermarks, and deadlines. Never keep one shared `ByteBuffer` for all connections hoping `Selector` automatically separates data by key.

### 7.2. `duplicate()`, `slice()`, and `asReadOnlyBuffer()` Do Not Copy Bytes

- `duplicate()` creates a view with independent cursors yet **shares content**.
- `slice()` creates a view over a remaining or sub-region yet **shares backing storage**.
- `asReadOnlyBuffer()` forbids writing through that view, yet the original alias can still write to the memory region.
- `ByteBuffer.wrap(byteArray)` shares the array with the caller; a caller holding the array can mutate contents outside the buffer.
- `ByteBuffer.allocateDirect(...)` only specifies allocation type; it does not guarantee thread safety.

**An easily misunderstood example:**

~~~java
ByteBuffer original = ByteBuffer.wrap(new byte[] {1, 2, 3});
ByteBuffer readOnly = original.asReadOnlyBuffer();
original.put(0, (byte) 9);
System.out.println(readOnly.get(0)); // 9
~~~

This snippet can run inside a method without concurrency to prove that a read-only view **does not own an immutable copy**. If another thread writes concurrently to backing bytes while a reader reads, synchronization or ownership is required; only if both data and cursors are completely immutable after safe publication can multiple readers use separate views.

### 7.3. `flip()`/`compact()` on Incomplete Frames

When reading part of a frame, do not call `clear()` and drop unconsumed bytes:

~~~java
int n = channel.read(input);
if (n > 0) {
    input.flip();
    decodeCompleteFrames(input);
    input.compact(); // keep incomplete frame bytes, shift to start of write region
}
~~~

This is an illustrative snippet; `decodeCompleteFrames` must advance `position` only past **complete frames**, leaving incomplete bytes in `remaining()`. `compact()` copies remaining bytes to the beginning and positions the cursor so the next read appends right after them. If the parser consumed all data, `clear()` is valid; if the buffer fills up because a frame exceeds capacity, enforce a size limit, grow boundedly, or use a streaming parser.

In non-blocking writes, **do not** `clear()`/`compact()` output before `write` drains all data; whatever remains in the buffer is precisely what the channel has not yet consumed.

## 8. Backpressure: When the Producer Outpaces the Socket

Suppose workers produce responses at 20 MB/s while a client receives at only 1 MB/s. If the server keeps pushing new responses into the queue unboundedly, pending bytes grow until memory runs out. Selector only reports transient writability; it does not cap pending bytes in your program.

Rules to establish:

| Signal | Action |
| --- | --- |
| Outbound queue just gained bytes | Enable `OP_WRITE` for the connection |
| `write(...) > 0` with bytes remaining | Keep buffer at updated position and continue on next writable event |
| `write(...) == 0` | Stop write turn; wait for `OP_WRITE`, do not busy-spin |
| Outbound queue empty | Remove `OP_WRITE`; keep only needed interests |
| Queued bytes exceed **high watermark** | Pause accepting more work, throttle producer, or signal overload |
| Queued bytes drop below **low watermark** | Restore `OP_READ`/work acceptance per policy |
| Client makes no progress past deadline | Cancel work, release queue/buffers, and close connection cleanly |

Two watermarks prevent rapid flapping when the queue hovers around a single threshold. When `OP_READ` is turned off, incoming data may buffer in the kernel receive buffer and the peer is slowed by TCP flow control; this does not mean the application rejected all new network data yet. Also enforce limits on connection count, frame size, and timeouts.

A handler writing multiple buffers should bound its **write budget** per loop pass, such as a maximum byte count or buffer count, to avoid starving the event loop when a client transfers data continuously. Once the budget is spent while the queue still holds data, leave `OP_WRITE` enabled for the next turn. This promotes fairness.

## 9. Fairness and Avoiding "One Key Monopolizing the Loop"

Even when every channel is non-blocking, the event loop can stall if one key's handler:

- Reads endlessly until `read() == 0` on a connection that continuously has data.
- Decodes hundreds of thousands of frames in a single selection pass.
- Writes an entire massive outbound queue in a single key invocation.
- Runs CPU-heavy logic or blocking I/O after every read.
- Holds a contended monitor lock for a long time, forcing the event loop to wait on another thread.

One strategy is setting a **per-key budget**: at most N read calls, M decoded frames, or X bytes written per pass. When the budget runs out, preserve state to resume on the next pass without losing already-read bytes. Budgets should be tuned alongside real load, fairness, deadlines, and backpressure.

You cannot simply cut off the loop and forget data already sitting in the inbound buffer: complete frames already in memory will **not** generate further socket readiness if the kernel receives no new bytes. If you stop early while internal frames remain buffered, schedule a follow-up pass via the event loop's task queue, or process to a safe point before returning from the callback.

## 10. EOF Errors, Key Cancellation, and Connection Lifecycle

Inside an `OP_READ` handler:

~~~java
int n = channel.read(input);
if (n == -1) {
    // Peer ended its send direction.
    // Finish last frame or report truncated frame; decide whether to send a response.
}
~~~

`-1` means **receive-side EOF**, distinct from `0` when no bytes are ready yet. Do not leave `OP_READ` enabled forever and keep reading `-1` without changing state; depending on the platform, that can trigger a readiness spin. If responses still need flushing after peer half-close, remove `OP_READ` and keep `OP_WRITE` until drained. Once no more data needs exchanging, close the channel and cancel the key.

Also handle:

- `IOException` when the peer resets or a network error occurs.
- `ClosedChannelException` if the channel closed during registration or an operation.
- `CancelledKeyException` if `isReadable`/`interestOps` is called on a canceled key.
- `ClosedSelectorException` when the selector is closed while the loop still uses it.
- Non-blocking connecting socket: `OP_CONNECT` and `finishConnect()` must be handled properly before reading/writing.
- Listener accept: `ServerSocketChannel.accept()` in non-blocking mode can return `null` even on an `OP_ACCEPT` event; never dereference null.
- EOF/truncated frames: the parser must enforce protocol framing; TCP does not preserve boundaries across `write`/`read` calls.

On every error, cleanup must remove the connection from registries, cancel the key, close the channel, and release buffers/references/pending tasks. If work was offloaded to a worker, discard late completions once the connection is no longer valid.

Do not call `selector.keys().clear()` or rely on `iterator.remove()` alone assuming the socket closed. Canceling keys and closing channels are separate operations; resource cleanup needs a clear owner.

## 11. Diagnosing High CPU and Troubleshooting

If the Java process uses high CPU while network traffic is low, check first:

1. Is the event loop calling `selectNow()` continuously or using a tiny unnecessary `select(positiveTimeout)`?
2. Is `OP_WRITE` staying enabled while the outbound queue is empty?
3. Did the handler forget `selectedIterator.remove()`, causing keys to be reprocessed repeatedly?
4. After EOF, is `OP_READ` still enabled and repeatedly reading `-1`?
5. Are `read/write` calls returning 0 inside a `while` retry loop?
6. Is an exception being caught and ignored, repeating the same failure without closing the key/channel?
7. Is `selector.wakeup()` being called excessively by workers without producing new results?
8. Is a huge parser/outbound backlog starving the event loop from reaching remaining connections?

If latency is high while CPU is not necessarily elevated, inspect blocking calls in handlers, overloaded worker pools, lock contention, outbound queue buildup, connection counts, and time spent per selection pass.

Useful metrics: registered channel count, selected keys per operation, count of `select()` returning 0, per-callback duration, pending bytes per connection, outbound high-watermark events, worker queue depth, I/O idle/stall duration, and connections closed due to timeouts.

These metrics are observational suggestions; they are not built into the `Selector` API itself. The application must record its own metrics or use appropriate JVM profilers/statistics.

## 12. Consolidated Design Rules

| Need | Right Approach | Mistake to Avoid |
| --- | --- | --- |
| Waiting for I/O on many sockets | `Selector.select()` with non-blocking channels | Infinite `selectNow()` polling |
| No outbound bytes | Keep only `OP_READ` (or other needed interest) | Leaving `OP_WRITE` always on |
| Unfinished outbound bytes | Keep per-connection buffer, leave `OP_WRITE` enabled | Busy-spinning when write returns 0; clearing output too early |
| Receiving partial frames | Per-connection input/decoder state, timely `compact()` | One global buffer for all connections |
| CPU/blocking DB tasks | Offload to a bounded worker pool | `Future.get()` inside the event loop |
| Receiving worker results | Thread-safe queue + `selector.wakeup()` + event-loop owner updates interest | Worker mutating shared ByteBuffer/SelectionKey state without protocol |
| Production rate > send rate | Backpressure, watermarks, deadlines | Unbounded outbound queues |
| Connection constantly sending data | Read/write/parse budget per pass | Letting one key monopolize the event loop |
| EOF or errors | Update state, cancel interest, close cleanly | Repeatedly reading -1 or skipping cleanup |

An easily verifiable responsibility layout: **the event loop owns the selector, selection keys, and I/O state buffers; workers process safely transferred data snapshots; results return through a thread-safe queue; the event loop updates interest ops and executes I/O itself**. Alternative designs are possible, provided you can prove equivalent ownership, visibility, and resource bounds.

## 13. Self-Check Questions

1. `selectNow()` returns 0 repeatedly, and `while(true)` immediately calls it again. What happens? **A busy loop**, burning high CPU without processing data.
2. Is `select(0)` equivalent to `selectNow()`? **No**; a timeout of 0 on `select(long)` means wait indefinitely, whereas `selectNow()` is non-blocking.
3. Why can `OP_WRITE` cause high CPU when the output queue is empty? Because sockets are frequently writable, so the selector continuously selects the key while the handler has no bytes to send.
4. Does `SocketChannel.write(buffer)` returning 0 mean the channel closed? **No**; in non-blocking mode it usually means temporarily unable to write right now. Keep the buffer and wait for readiness.
5. Two connections share one `ByteBuffer` with only one event-loop thread; is it safe? **No**: incomplete frames and `position/limit` of one connection can be overwritten or lost by operations on the other connection.
6. Do `duplicate()` or `asReadOnlyBuffer()` create an independent data region? **No**; they still share backing bytes with their aliases.
7. Why is offloading blocking JDBC to a worker and immediately calling `future.get()` in the event loop still slow? Because the event-loop thread is still blocked waiting for the result.
8. When a worker creates a response, should it directly `put()` into an outbound buffer that the event loop is `write()`ing? **No**, unless the design has a proven-safe ownership/synchronization protocol.
9. One buffer finished sending, yet the outbound queue holds another buffer; should you clear `OP_WRITE`? **Not yet**; remove it only when no pending bytes remain.
10. After `read() == -1`, is it okay to keep `OP_READ` enabled and read repeatedly? **No**; that is receive-side EOF, requiring state/interest updates or closing once protocol completes.
11. Why must worker and output queues be bounded? Because a producer faster than its consumer causes uncontrolled memory growth if left unbounded.
12. Can you cap the read budget and simply ignore frames already sitting in the input buffer? **No**; preserve parser state and schedule continued processing so no frames are missed.

## References

- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): `select()`, `selectNow()`, timeouts, selected keys, `wakeup()`, and synchronization rules.
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): interest/ready operations, attachments, cancellation.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking read/write, connect, EOF.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): cursors, `flip`, `compact`, views sharing backing storage.
- [Java SE 17 — ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): non-blocking accept, channel configuration.
