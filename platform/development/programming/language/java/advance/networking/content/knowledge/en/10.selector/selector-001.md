# How does Selector solve the problem of monitoring many connections?

When building a TCP server, the problem is not just accepting a connection. The server also has to wait for data from a large number of clients with open sockets, which may only send a few bytes per minute. If you use blocking I/O in a naive way, a thread calling `read()` on client A will have to wait for A to have data; during that time, the same thread cannot immediately handle clients B and C. The usual approach is to create one thread per connection, but if there are many idle connections, the system still has to manage a large number of threads.

Java NIO's **`java.nio.channels.Selector`** solves the **I/O readiness monitoring** part using **I/O multiplexing**: one or a few event-loop threads can register multiple channels in non-blocking mode, and then wait for the operating system to notify **which channels are ready for accept/connect/read/write**. Only channels with events worth handling are brought into the processing loop.

This article walks through the blocking problem, selector architecture, `SelectionKey` and interest/ready sets, up to a Java 17+ program with **three concurrently active TCP clients and one server event loop**. The goal is to understand the mechanism, its limitations, and how to use it properly in real networking applications.

## 1. Why does monitoring many connections with blocking I/O run into trouble?

Suppose a server needs to maintain TCP connections with 10,000 clients. Most of them are online but have not sent any data yet. With the **one-thread-per-connection** approach, each thread may sit waiting:

~~~java
// Blocking idea: this is only a snippet, not a complete server.
Socket client = serverSocket.accept();
InputStream in = client.getInputStream();
int value = in.read(); // Blocks until there is data, EOF, or an error.
~~~

If you use a single thread to process sequentially, when the first client has not sent anything yet, the other clients may be left waiting. If you create a dedicated thread for every client, you can increase concurrency, but each thread requires a stack, metadata, scheduler bookkeeping, and context-switching overhead. The maximum scale also depends on CPU/RAM/OS and Java's thread model.

Side by side:

~~~text
A. Blocking + one platform thread per client

Client A ──> Thread A ───── read() ─── [waiting]
Client B ──> Thread B ───── read() ─── [waiting]
Client C ──> Thread C ───── read() ─── [waiting]
...
Client N ──> Thread N ───── read() ─── [waiting]


B. Non-blocking + Selector

Client A ── SocketChannel A ─┐
Client B ── SocketChannel B ─┤
Client C ── SocketChannel C ─┼─> Selector ─> event loop
...                         │                 |
Client N ── SocketChannel N ─┘                 +─ handle ready channels
                                              +─ return to select()
~~~

Selector **does not** make a TCP connection disappear, does not automatically receive/write bytes, and does not "run each client in parallel" inside a single thread. It helps the thread **avoid sitting and waiting separately on each idle socket**. When readiness occurs, the application still has to call `accept()`, `read()`, and `write()` accordingly.

**Trade-off:** For a few connections, blocking code can be simple and good enough. With thousands of mostly idle connections, event-driven NIO can reduce thread demand and overhead. Newer Java versions also have virtual threads to write blocking code in a more readable model; technology choice should be based on workload and specific requirements, rather than assuming Selector is always faster.

## 2. Selector is an "I/O readiness" selector, not an I/O executor

A `Selector` monitors registered `SelectableChannel` instances:

1. Create a `Selector`, for example `Selector.open()`.
2. Create selectable channels such as `ServerSocketChannel` and `SocketChannel`; configure **non-blocking** mode via `configureBlocking(false)`.
3. Register the channel with the Selector via `register(selector, interestOps)`. The method returns a `SelectionKey`.
4. Call `selector.select()` or `selector.select(timeout)`. At this point, the thread can **sleep in a single shared wait operation**, instead of checking each socket in a busy loop.
5. When matching events occur, read `selector.selectedKeys()` and handle each key. **Remove the key from the selected set after taking it out for processing**.
6. Update `interestOps(...)` when the connection state changes (for example, when there is data waiting to be sent), then return to `select()`.

~~~text
register channels (non-blocking)
            |
            v
       [ Selector ]
            |
            v
      select() waits ───────────┐
            |                  |
   readiness observed           |
            |                  |
            v                  |
       selectedKeys             |
            |                  |
  ACCEPT / CONNECT / READ / WRITE
            |                  |
   perform I/O, update key      |
            |                  |
            └──────────────────┘
~~~

**Readiness is different from completion:** `isReadable()` notifies that the channel **can** be read without a long wait (or has reached EOF/error), not that it already contains the client's payload. The `SocketChannel.read(buffer)` call still has to be executed and **may return 0**, `-1`, or a positive number of bytes. Similarly, `isWritable()` does not promise that all data will be written in a single call.

NIO Selector is a **readiness-based** model, unlike a completion-based API that returns a callback/future after I/O has actually completed. Do not confuse `Selector` with `ExecutorService`: a selector monitors I/O, whereas an executor runs submitted tasks.

## 3. Classes to know

| Component | Role | Example |
| --- | --- | --- |
| `Selector` | Monitors a set of registered channels and waits for readiness | `Selector.open()`, `select()`, `selectedKeys()` |
| `ServerSocketChannel` | Server-side TCP channel, accepts new connections | `bind(...)`, `accept()`, `OP_ACCEPT` |
| `SocketChannel` | TCP channel for a single connection | `read(buffer)`, `write(buffer)`, `OP_READ` |
| `SelectionKey` | Token linking a channel with a selector and a set of operations of interest | `interestOps(...)`, `isReadable()`, `attach(...)` |
| `ByteBuffer` | Byte buffer with `position`, `limit`, `capacity` | `put`, `flip()`, `compact()`, `clear()` |
| `NetworkChannel` / `SelectableChannel` | Channel interfaces that can be configured and/or registered | `configureBlocking(false)`, `validOps()` |

**Not every channel can be registered with a Selector.** For example, `FileChannel` is not a `SelectableChannel`; regular file reading has its own I/O model. For UDP, `DatagramChannel` can use a Selector to receive/send datagrams, but the problem of monitoring **many TCP connections** mainly uses `ServerSocketChannel` and `SocketChannel`.

Each channel can only be registered with the operations allowed by `validOps()`; using an invalid operation can throw `IllegalArgumentException`. `ServerSocketChannel` only supports `OP_ACCEPT`, while `SocketChannel` supports `OP_CONNECT`, `OP_READ`, and `OP_WRITE`. Before registering, the channel must be in **non-blocking mode**, otherwise it may throw `IllegalBlockingModeException`.

## 4. OP_ACCEPT, OP_CONNECT, OP_READ, OP_WRITE

| Operation | Common channel | When to be interested? | Action after readiness |
| --- | --- | --- | --- |
| `SelectionKey.OP_ACCEPT` | `ServerSocketChannel` | Server is listening for new connections | Call `accept()`; configure the new socket as non-blocking and register it |
| `SelectionKey.OP_CONNECT` | `SocketChannel` | Client started a non-blocking connect that has not finished yet | Call `finishConnect()`; if successful, switch to the appropriate OP_READ/OP_WRITE |
| `SelectionKey.OP_READ` | `SocketChannel` | Want to know when reading can make progress or there is EOF/error | Call `read(buffer)`; handle the returned byte count |
| `SelectionKey.OP_WRITE` | `SocketChannel` | **There is data waiting to be written** after a partial write | Call `write(buffer)`; check `buffer.hasRemaining()` |

**The table above describes operations of interest, not a claim that the selector "already performed" those operations.** For example, a channel reported as `OP_ACCEPT` still needs `accept()`; because the channel is non-blocking, `accept()` can return `null` if there are no pending connections left.

### Why not always register OP_WRITE?

In TCP, a socket is usually **ready for writing** whenever the kernel send buffer has free space. If you always keep `OP_WRITE` in the interest set even when **there is no data to send**, `select()` can return continuously, causing the CPU to spin (busy loop).

Common approach:

~~~text
Newly connected:
    interestOps = OP_READ

Request read, response ByteBuffer ready to send:
    interestOps = OP_WRITE  (or OP_READ | OP_WRITE
                            if there is a queue and proper backpressure)

When the buffer is completely written:
    interestOps = OP_READ   (remove OP_WRITE)
~~~

In the demo below, to keep memory bounding simple, we **temporarily stop being interested in OP_READ** while there is unfinished echo data to send. Each connection only holds **one pending ByteBuffer**. This is a basic form of backpressure; production servers may need bounded queues, fairness, and protocol framing.

## 5. SelectionKey: interest set, ready set, selected set, attachment

Each time a channel is registered with a Selector, a `SelectionKey` is created to track that relationship. The key has several concepts that are often confused:

**Interest set** is the set of operations the application **wants to be notified about**, set using:

~~~java
key.interestOps(SelectionKey.OP_READ);
key.interestOps(SelectionKey.OP_READ | SelectionKey.OP_WRITE);
~~~

**Ready set** is the set of operations the selector **detected as ready** in that selection round, readable via `readyOps()` or the helpers `isAcceptable()`, `isConnectable()`, `isReadable()`, and `isWritable()`. A key can have multiple ready flags if its interest set contains multiple operations.

**Selected-key set** is `selector.selectedKeys()`. This set holds the keys that were selected by the selector; it is **not** a list that automatically empties after each round. A proper loop should explicitly call `iterator.remove()`:

~~~java
Iterator<SelectionKey> it = selector.selectedKeys().iterator();
while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();                 // Very important.
    if (!key.isValid()) {
        continue;
    }
    // Handle readiness flags.
}
~~~

This is an event-loop snippet and requires importing `Iterator` and `SelectionKey`. If you forget `remove()`, the same key may remain in the selected set across rounds and cause duplicate processing or unpredictable behavior. Do not call `add(key)` directly on the selected set: this set is managed by the selector.

**Attachment** is data **specific to a single connection**, attached to the key:

~~~java
key.attach(connectionState);
Object state = key.attachment();
~~~

For example, `connectionState` can store a receive buffer, output queue, parser state, request ID, last activity time, and unsent byte count. Do not keep a single shared `ByteBuffer` for all clients and mutate it back and forth, because data from different connections could be mixed or overwritten.

**Lifecycle:** `key.cancel()` marks the registration for cancellation; you should usually close the channel when the connection finishes or errors. A key can become invalid when the channel is closed. Because readiness and state can change between `select()` and the handler, check `key.isValid()` before operating on it; you may need to handle `CancelledKeyException` in code that modifies keys from multiple places.

## 6. Java 17+ example: one Selector monitoring three TCP connections

To see the benefit without opening two terminals or picking a fixed port in advance, this example does everything in **one program**:

- A `ServerSocketChannel` binds to `127.0.0.1:0`. Port 0 means the operating system chooses an available port automatically.
- The server registers `OP_ACCEPT` with **one Selector** and runs the **event loop on the main thread**.
- Three clients are created concurrently by an `ExecutorService` solely to generate test load. They are **not** three server worker threads.
- Each client sends a short string and waits for the server to echo it back. The server accepts multiple connections, reads bytes incrementally, keeps a pending write buffer on the key, and switches between `OP_READ` / `OP_WRITE`.
- Once all three clients have received their echo, closed their connections, and the server sees EOF from all three, the event loop stops. The program prints results in `Future` order, because readiness order over the network has no guarantee.

Create **`SelectorManyClientsDemo.java`**:

~~~java
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SelectorManyClientsDemo {
    // Clients are only used to generate test load; the server side is an NIO event loop.
    private static String client(int port, int id) throws IOException {
        String text = "client-" + id;
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

        try (Socket socket = new Socket("127.0.0.1", port)) {
            socket.setSoTimeout(3000);
            socket.getOutputStream().write(bytes);

            // Client knows the echo byte count in advance, so it uses readNBytes.
            byte[] echo = socket.getInputStream().readNBytes(bytes.length);
            if (!Arrays.equals(bytes, echo)) {
                throw new IOException("Unexpected echo");
            }
            return new String(echo, StandardCharsets.UTF_8);
        }
    }

    private static void close(SelectionKey key) {
        key.cancel();
        try {
            key.channel().close();
        } catch (IOException ignored) {
            // Just cleaning up resources in the demo.
        }
    }

    private static int handle(
            SelectionKey key, Selector selector) throws IOException {

        if (key.isAcceptable()) {
            ServerSocketChannel server = (ServerSocketChannel) key.channel();
            SocketChannel accepted;

            // Non-blocking accept: null means no more pending connections.
            while ((accepted = server.accept()) != null) {
                accepted.configureBlocking(false);
                accepted.register(selector, SelectionKey.OP_READ);
            }
            return 0;
        }

        SocketChannel socket = (SocketChannel) key.channel();

        if (key.isReadable()) {
            ByteBuffer incoming = ByteBuffer.allocate(1024);
            int n = socket.read(incoming);

            if (n == -1) {
                close(key);         // Client closed input (EOF).
                return 1;
            }
            if (n > 0) {
                incoming.flip();    // Prepare to read bytes from the buffer.
                key.attach(incoming);
                key.interestOps(SelectionKey.OP_WRITE);
            }
        } else if (key.isWritable()) {
            ByteBuffer pending = (ByteBuffer) key.attachment();
            socket.write(pending);  // May write partially, or 0 bytes.

            if (!pending.hasRemaining()) {
                key.attach(null);
                key.interestOps(SelectionKey.OP_READ);
            }
        }

        return 0;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService clients = Executors.newFixedThreadPool(3);

        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open()) {

            server.configureBlocking(false);
            server.bind(new InetSocketAddress("127.0.0.1", 0));
            server.register(selector, SelectionKey.OP_ACCEPT);

            int port = ((InetSocketAddress)
                    server.getLocalAddress()).getPort();

            List<Future<String>> replies = new ArrayList<>();
            for (int id = 1; id <= 3; id++) {
                int clientId = id;
                replies.add(clients.submit(
                        () -> client(port, clientId)));
            }

            int closedClients = 0;
            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(10);

            while (closedClients < 3
                    && System.nanoTime() < deadline) {

                selector.select(100);
                Iterator<SelectionKey> it =
                        selector.selectedKeys().iterator();

                while (it.hasNext()) {
                    SelectionKey key = it.next();
                    it.remove();

                    if (!key.isValid()) {
                        continue;
                    }

                    if (key.isAcceptable()) {
                        closedClients += handle(key, selector);
                    } else {
                        try {
                            closedClients += handle(key, selector);
                        } catch (IOException e) {
                            close(key);
                            throw e;
                        }
                    }
                }
            }

            if (closedClients != 3) {
                throw new IOException("Timed out");
            }

            // Futures are iterated in submission order, even though I/O events interleave.
            for (Future<String> future : replies) {
                System.out.println("Echo: " + future.get());
            }
        } finally {
            clients.shutdownNow();
        }
    }
}
~~~

Run on JDK 17+:

~~~bash
javac -encoding UTF-8 SelectorManyClientsDemo.java
java SelectorManyClientsDemo
~~~

**Output on a machine with working TCP loopback:**

~~~text
Echo: client-1
Echo: client-2
Echo: client-3
~~~

This is a bounded-time program, **not a production service**. If the environment blocks TCP loopback connections, is overloaded, or times out, it may throw an exception instead of printing the three lines. The example uses `127.0.0.1` to avoid DNS resolution and uses port 0 to avoid hardcoded port conflicts.

### What actually happens when it runs?

1. `server.register(selector, OP_ACCEPT)` does not accept immediately; it only registers to ask "when is a client waiting to be accepted?".
2. Three clients are created concurrently; each client connects to the OS-assigned port and sends the bytes of `client-n`.
3. `selector.select(100)` waits up to 100ms for readiness. Only ready keys need to be processed; there is no dedicated server thread per connection.
4. When the key is **acceptable**, `server.accept()` returns a `SocketChannel`. The server configures the new channel in non-blocking mode and registers `OP_READ`. The `while (accept() != null)` loop drains all pending connections in that round.
5. When a client key is **readable**, `socket.read(incoming)` returns the number of newly available bytes; `-1` means EOF. If there are bytes, the code calls `flip()` and attaches the buffer as the attachment of **that exact key**.
6. The server switches interest to `OP_WRITE` to send the bytes back. While echoing, it does not continue reading from the same client, so there is no unbounded queue.
7. On the **writable** event, `socket.write(pending)` may only write partially. If the buffer still has remaining bytes, it keeps `OP_WRITE`; if finished, it sets `attach(null)` and switches back to `OP_READ`.
8. The client reads the number of bytes it sent, compares them for an exact match, and closes the socket; the server eventually reads EOF on all three connections and terminates.
9. The main thread iterates over the `Future` list in registration order to print deterministic output. **The actual accept/read/write order may differ.**

The key takeaway: **one server event loop served three TCP connections using readiness**, while the thread pool only represented three simulated clients. With a large N, the same mechanism can monitor many more sockets without allocating a dedicated platform thread per connection.

## 7. Explaining buffers, partial I/O, and message boundaries

**TCP is a byte stream, with no message boundaries** per `write()` call. A client sending `"client-1"` in one call does not guarantee that the server will receive all eight bytes in a single `read()` call. The example handles this by echoing **each received chunk** and letting the client assemble the known byte count using `readNBytes(bytes.length)`.

A non-blocking `SocketChannel.read(ByteBuffer)` returns:
- **`n > 0`:** `n` bytes were read. The data lies in the buffer from the position before the read up to the new position.
- **`n == 0`:** no bytes are available to read right now; do not spin in an infinite loop inside the handler.
- **`n == -1`:** the input side of the stream is at EOF (e.g., the peer closed or shut down output); handle lifecycle/half-close according to the protocol.

Similarly, `SocketChannel.write(buffer)` can write 0, part of, or all remaining bytes. Therefore, the following code is **logically wrong** if it assumes everything was sent:

~~~java
socket.write(buffer);           // May not have sent everything.
key.interestOps(SelectionKey.OP_READ); // Wrong if buffer.hasRemaining().
~~~

The correct way in the example:

~~~java
socket.write(buffer);
if (buffer.hasRemaining()) {
    key.interestOps(SelectionKey.OP_WRITE);
} else {
    key.interestOps(SelectionKey.OP_READ);
}
~~~

These are illustrative snippets, assuming `socket`, `key`, and `buffer` are already configured.

### ByteBuffer has position, limit, capacity

`ByteBuffer` is not just a byte array. It has three state fields:
- **capacity:** total capacity.
- **position:** the next position to operate on.
- **limit:** the bound of the readable/writable region.

Typical lifecycle:

~~~text
buffer = ByteBuffer.allocate(8)

When receiving from socket:
    [a b c . . . . .]
         ^ position = 3
    limit = 8

flip(): switch to read mode
    [a b c . . . . .]
     ^ position = 0
           ^ limit = 3

write(buffer): send until position == limit
    [a b c . . . . .]
           ^ position = 3
           ^ limit = 3

clear(): position = 0, limit = capacity
    (does not physically erase old bytes)
~~~

In a parser receiving messages with a length header or delimiter, you may need to keep trailing bytes that do not yet form a complete frame using `compact()`, then read more. Do not force every `read` to be an independent message. If decoding UTF-8 Unicode when bytes are incomplete, a code point can be split across reads; keep the decoder state or wait for a complete frame.

Common framing patterns:
- **Length-prefix:** read the full header (e.g., 4-byte length), validate the size, then read the full payload.
- **Delimiter:** read up to a separator character, such as newline, while bounding the length to prevent a client from sending endlessly without a delimiter.
- **Existing protocol:** HTTP/WebSocket/RPC each have their own grammar; do not use the "one read = one request" assumption.

## 8. Why must per-connection state be maintained?

In blocking code, much of the state lives on the client thread's stack. In an NIO event loop, client A's handler only runs briefly and then returns to the selector; the next iteration may handle client B and then come back to A. Therefore, state must be **persisted across readiness events**.

A production state might include:

~~~java
// Illustrative type, not a standalone program.
final class ConnectionState {
    final ByteBuffer input = ByteBuffer.allocate(8192);
    final java.util.ArrayDeque<ByteBuffer> outputQueue =
            new java.util.ArrayDeque<>();

    long lastActivityNanos;
    boolean outputShutdownRequested;
}
~~~

You can attach the state right when accepting:

~~~java
client.register(selector, SelectionKey.OP_READ, new ConnectionState());
~~~

This is a snippet; the constructor requires an already-opened `selector` and `client.configureBlocking(false)` beforehand. The handler retrieves it via `(ConnectionState) key.attachment()`.

In the demo, the attachment is simply a single pending `ByteBuffer`:
- `null`: interested in read, no echo data waiting to be sent.
- non-empty `ByteBuffer`: interested in write, needing to preserve `position` across write calls.
- When the buffer is completely sent: `attach(null)` to release the reference and switch back to read.

**Memory must be bounded.** If a user sends data faster than the network can write it back, adding all data to an unbounded output queue can cause out-of-memory errors. A common approach is high/low-water marks to temporarily remove `OP_READ` when pending bytes exceed a threshold, then re-enable it once drained. In the demo, each connection holds only one pending 1024-byte buffer, which keeps the code easy to follow and naturally creates backpressure, though throughput may be lower because reading pauses while replying.

## 9. OP_CONNECT: monitoring non-blocking outbound connections

The server in the example only uses `OP_ACCEPT`, `OP_READ`, and `OP_WRITE`. For applications that **actively initiate connections** using a non-blocking `SocketChannel`, `OP_CONNECT` is also needed.

Idea (snippet, not a complete program):

~~~java
SocketChannel client = SocketChannel.open();
client.configureBlocking(false);

boolean connected =
        client.connect(new InetSocketAddress("127.0.0.1", 9090));

if (connected) {
    client.register(selector, SelectionKey.OP_READ);
} else {
    client.register(selector, SelectionKey.OP_CONNECT);
}

// In the event loop, after receiving a connectable key:
if (key.isConnectable()) {
    SocketChannel channel = (SocketChannel) key.channel();
    if (channel.finishConnect()) {
        key.interestOps(SelectionKey.OP_READ);
    }
}
~~~

The `selector` and `key` variables in the snippet must belong to the event loop managing the corresponding channel. `connect(...)` may return `true` if the connection completes immediately, or `false` if it is pending. When `OP_CONNECT` becomes ready, **you still must call `finishConnect()`**; do not switch to reading/writing as if the connection were already complete without verifying.

If the connection fails, `finishConnect()` or a related operation may throw `IOException`; handle it and close the key/channel. Depending on the implementation, there may be a pending connection error. A `ServerSocketChannel` does not have `OP_CONNECT`; it is used for accepting.

## 10. Select methods, wakeup, and avoiding CPU spin loops

| API | How it waits | When appropriate |
| --- | --- | --- |
| `selector.select()` | Waits until readiness, wakeup, or interrupt according to API semantics | Standard event loop waiting for I/O |
| `selector.select(timeoutMillis)` | Waits at most a positive number of milliseconds before returning | When there are timers / deadlines / housekeeping |
| `selector.selectNow()` | Returns immediately, even if no channels are ready | Active polling inside a designed scheduling loop |
| `selector.wakeup()` | Causes a currently blocked or upcoming select operation to return | Another thread needs the event loop to update registrations/tasks |

**Note:** In `select(long timeout)`, **timeout = 0 has unbounded wait semantics like `select()`**, not "wait 0ms and return". To avoid blocking, use `selectNow()`. `select(100)` in the demo is a 100ms timeout, allowing the program to check the deadline on each iteration; long-running server code typically uses `select()` with an accurate wakeup/timer mechanism.

A production event-loop pattern (pseudo code):

~~~text
while running:
    applyPendingRegistrationsAndTasks()
    selector.select(nextTimerDeadline)
    for each key in selectedKeys:
        remove key from selected set
        if valid:
            handleReadyOperations(key)
    runExpiredTimersAndHousekeeping()
~~~

**Cross-thread issue:** If a secondary thread creates a channel or changes `interestOps` while the event loop is in `select()`, proper ownership conventions and synchronization are required. A common safe pattern is for the secondary thread to push the request onto a queue, call `selector.wakeup()`, and then let the event-loop thread drain the queue and execute `register()/interestOps()`. Do not arbitrarily let multiple threads modify structures and attachments without synchronization.

**Busy spin:** If `selectNow()` is called in an infinite loop when there is no data, or if `OP_WRITE` is always enabled even when the output queue is empty, CPU usage can spike. Prefer blocking to wait for readiness when idle, and only enable `OP_WRITE` when there are actually bytes waiting to be sent.

## 11. How many threads does a Selector have, and does it really process in parallel?

A Selector can be used by a single event-loop thread, or combined across multiple selectors and event-loop threads. **Multiplexing does not mean parallel execution**. Within a single loop:
- Only **one callback/handler** runs at a time on the event-loop thread.
- Multiple different sockets are served **interleaved** as they become ready.
- CPU-heavy work, blocking database queries, blocking file I/O, synchronous DNS lookups, or `Thread.sleep(...)` inside a handler will block **the entire event loop**.

A design serving many clients typically separates:

~~~text
                          acceptor selector (design-dependent)
                                   |
                        1..N selector event loops
                                   |
                    fast read/parse, non-blocking write
                                   |
                   bounded queue / worker executor
                                   |
                      business logic or storage
                                   |
                    result queue back to event loop
                                   |
                           wakeup(), OP_WRITE
~~~

Not every application needs this complex diagram. With very fast handlers, a single event loop may suffice; with slow CPU/DB processing, you can offload the slow part to an executor, **along with queue bounds and backpressure**. Many modern event-driven frameworks are built on a similar model, though their thread models and how they distribute channels across selectors vary.

Operational costs do not disappear: you still need file descriptors/socket resources, buffers, per-client state, timers, cleanup, security, and connection limits. "10,000 connections" also **does not automatically** mean "10,000 requests/second".

## 12. Readiness does not guarantee immediate operation success

Selector typically uses the operating system's polling/event notification infrastructure (depending on platform/provider) to detect readiness. Readiness is only a **current hint**, which can change before the application acts on it.

Cases that must be handled:
1. `OP_READ` is reported, yet `read` returns **0 bytes** in non-blocking mode.
2. `OP_READ` is reported because the peer closed output, so `read` returns **-1 EOF**; this is not a data packet.
3. `OP_WRITE` is reported, yet `write` only accepts part of the data or **0 bytes** if the send buffer has no space at the moment of the call.
4. `OP_ACCEPT` is reported, yet a subsequent `accept()` call may return `null` because there are no pending connections left.
5. A `SelectionKey` may be cancelled between selection and handling; check validity and distinguish channel close from key cancellation.
6. `select()` may return **0**, for example due to wakeup, interrupt, or timeout; do not treat that as a client error.

That is why event-driven code needs to branch completely on return values and preserve state. If a write operation is partial, the unwritten portion stays in the `ByteBuffer`; if a protocol frame has not been read completely, the parser must keep the bytes/state for the next round.

## 13. Connection lifecycle and resource cleanup

With TCP and Selector, initialization and closing are the application's responsibility:

- When a client is accepted, configure non-blocking mode before registering, and optionally attach connection state, timeout policy, and request limits.
- When encountering EOF `read() == -1`, decide whether to close the channel immediately or handle **half-close** according to the protocol if there is still pending output; the demo closes immediately because the client has already received the echo.
- When an individual client encounters an `IOException`, usually only cancel the key/close that client's channel and keep serving other clients; do not let one broken client crash the entire server.
- When shutting down the server, stop accepting, cancel registrations, close all client channels and the server channel; then close the selector. **Closing the Selector does not automatically replace closing all registered channels**.
- Key cancellation may be processed during the selector's next select round; code must avoid using keys that are no longer valid.
- Set idle timeouts/heartbeats, connection limits, and pending-byte limits if the server holds many idle connections.

The demo intentionally runs with a deadline and stops after reading EOF from three clients. It is not a forever-running production server and does not include full shutdown/task-cancellation logic for unexpected errors. Production designs should clean up accepted channels even when the event loop exits due to an exception.

## 14. Is Selector suitable for every problem?

| Scenario | Should you consider Selector? | Reason |
| --- | --- | --- |
| Many TCP sockets staying connected while mostly idle | Yes | One event loop can wait for readiness across many channels |
| Chat server, gateway, proxy needing non-blocking read/write | Yes | Fits event-driven design with per-connection state |
| Simple client with a few connections, clear readable blocking I/O | Probably not needed | Blocking API is easier to program, low overhead at small scale |
| Per-request work is CPU-heavy or makes blocking DB calls | Use Selector for I/O only | Must offload slow work or choose a different architecture |
| Need to handle file channels with Selector | Not directly | `FileChannel` is not a `SelectableChannel` |
| Using Java 21+ with virtual threads | Compare and weigh | Virtual threads make thread-per-request easier to write but do not replace all backpressure policies |
| Want automatic protocol framing, retransmission, or authentication | Not enough | Selector is only a readiness mechanism, not a protocol framework |

NIO libraries such as Netty, Grizzly, or server frameworks typically encapsulate many details about buffers, framing, lifecycle, timeouts, and backpressure. You need to understand Selector to analyze behavior and debug; you do not necessarily have to hand-write an event loop for a production product.

## 15. Common mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Registering while channel is still blocking | May throw `IllegalBlockingModeException` | Call `configureBlocking(false)` first |
| Registering wrong operation for channel type | `IllegalArgumentException` / incorrect behavior | Check `validOps()` |
| Not calling `iterator.remove()` on selected key | Already-processed key may stay in selected set | Remove immediately inside the loop |
| Using `if(isReadable())` and always decoding a complete message | TCP may deliver partial data or coalesce multiple messages | Design framing and parser state |
| Assuming a single `write` sends everything | Remaining data in buffer gets left behind | Check `hasRemaining()`, keep `OP_WRITE` when needed |
| Always registering `OP_WRITE` when queue is empty | Busy spin and high CPU usage | Only enable `OP_WRITE` when there are pending bytes |
| No per-client state | Data from different connections gets mixed/overwritten | Attach or map state per key |
| Unbounded output queue | OOM when a client reads slowly | Backpressure/high-water marks, bound memory |
| Handler runs slow SQL/blocking I/O | Blocks the entire event loop | Offload blocking/CPU tasks to a worker pool |
| Treating `read() == 0` as EOF | Mistakenly closes the client | EOF is only when it returns `-1` |
| Not handling `read() == -1` | Dead socket remains in the selector | Cancel key/close or handle half-close |
| Forgetting `finishConnect()` after `OP_CONNECT` | Socket is read/written before connect finishes | Complete connection first, then update interest set |
| Calling `select(0)` to avoid blocking | May actually wait indefinitely | Use `selectNow()` |
| Changing `interestOps` from another thread without wakeup/sync | Event loop may not see the change in time or hit a race | Queue task for the loop + `selector.wakeup()` |
| Only closing Selector when server stops | Registered channels may remain open | Close channels and selector according to lifecycle |

## 16. Self-check questions

**1.** A thread calls `selector.select()` to wait on 5,000 `SocketChannel`s. Does this mean 5,000 clients are processed in parallel?  
**Answer:** No. It monitors readiness across multiple channels; the event-loop thread processes ready channels one by one, possibly interleaving connections.

**2.** What is the difference between a `SelectionKey`'s **interest set** and **ready set**?  
**Answer:** Interest is the operations the application wants to monitor, whereas ready is the operations the selector detected as ready in the current selection round.

**3.** Why must a selected key be removed with `iterator.remove()`?  
**Answer:** The selected set does not automatically clear all processed keys after a loop iteration; removing them avoids unintended reprocessing.

**4.** Why should `OP_WRITE` not stay enabled for the entire lifetime of a socket?  
**Answer:** A socket is usually writable whenever the kernel buffer has space, which can cause the selector to repeatedly wake up the event loop even when the application has no data to send.

**5.** How do `read(buffer) == 0` and `== -1` differ?  
**Answer:** 0 means no bytes could be read at that moment; -1 means EOF on the input stream.

**6.** If a client sends 100 bytes in a single `write()` call, is the server guaranteed to receive all 100 bytes in a single `read()` call?  
**Answer:** No. TCP is a byte stream; you must accumulate according to framing or a known length.

**7.** Why does the demo use `key.attach(ByteBuffer)`?  
**Answer:** To keep the unsent portion of the reply data for **each connection**, without losing `ByteBuffer.position` between writable notifications.

**8.** Is registering `OP_CONNECT` on a `ServerSocketChannel` valid?  
**Answer:** No. `ServerSocketChannel` only supports `OP_ACCEPT`. Non-blocking outbound `SocketChannel` uses `OP_CONNECT`.

**9.** How do you prevent a slow-reading client from causing the server to use too much RAM?  
**Answer:** Bound pending output/buffers and temporarily reduce or disable read interest when exceeding a threshold; re-enable it once drained.

**10.** Why should the selector thread not make blocking database queries?  
**Answer:** Because while waiting on the DB, the entire event loop cannot process other sockets, increasing latency even when readiness is already there.

## Official Java API and NIO references

- [Java SE 17 — `java.nio.channels` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/package-summary.html): multiplexed, non-blocking I/O model.
- [Java SE 17 — Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): `select`, selected-key set, and `wakeup`.
- [Java SE 17 — SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): interest set/ready set, OP_*, and attachment.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html), [ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): read/write/accept and non-blocking behavior.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): position, limit, flip, compact, and buffer lifecycle.
