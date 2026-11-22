# Selector and the Single-Thread Multi-Channel Model (Java NIO)

Normally, when a network application uses blocking read calls, each connection may require its own thread to wait for data. Java NIO provides **`Selector`** so that a single thread can monitor **multiple selectable channels** and handle only the I/O operations that the operating system/provider reports as **able to make progress** (*readiness*). This architecture is the foundation of many **event loops** and network servers that manage large numbers of connections.

The core point: **Selector does not read or write data itself, does not create a thread per channel, and does not guarantee that a single `read` or `write` transfers all data.** It works together with `SelectableChannel`, `SelectionKey`, `ByteBuffer`, and application logic to wait for and then process events.

## 1. What Problem Does Selector Solve?

Imagine a server with many TCP connections where most of the time each connection is simply waiting for the next request:

```text
Simple model: one thread per connection

Client A ── Socket A ── Thread A ── read() waiting
Client B ── Socket B ── Thread B ── read() waiting
Client C ── Socket C ── Thread C ── read() waiting
...                        ...

Event loop model using Selector

Client A ── SocketChannel A ─┐
Client B ── SocketChannel B ─┼── Selector.select() ── Event-loop thread
Client C ── SocketChannel C ─┘                       ├── A: OP_READ?
                                                    ├── B: OP_WRITE?
                                                    └── C: OP_CONNECT?
```

One thread waits for readiness across multiple channels, then processes each appropriate `SelectionKey`. This can reduce the overhead of managing many threads waiting on I/O, especially with a large number of mostly idle connections.

However, **an event-loop thread still executes code at only one point at a time**. If a handler runs heavy CPU work, makes a blocking database call, sleeps for a long time with `Thread.sleep`, or waits on a blocking Future, all connections managed by that thread can be slowed down. Therefore, an event loop usually performs I/O and brief logic, delegating blocking or CPU-intensive work to an appropriate worker pool.

## 2. Components and Ownership Relationships

| Component | Role |
| --- | --- |
| `Selector` | Registers multiple `SelectableChannel` instances, waits for readiness, and provides the set of ready keys. |
| `SelectableChannel` | A channel that can be set to non-blocking mode and registered with one or more selectors; for example `SocketChannel`, `ServerSocketChannel`, and `Pipe` channels. |
| `SelectionKey` | The registration relationship of **one channel on one selector**, holding interest ops, ready ops, and an attachment. |
| `SelectionKey.interestOps()` | The types of events the application wants the selector to monitor. |
| `SelectionKey.readyOps()` | The types of operations that the most recent selection indicates may make progress. |
| `SelectionKey.attachment()` | Arbitrary application state, such as a partially read buffer, write queue, or parser. |
| `ByteBuffer` | Data read/written through a channel, with `position`, `limit`, and `remaining()`. |

A channel can be registered with multiple selectors, but with **the same selector**, each channel has at most one valid registration/`SelectionKey`. Calling `register(selector, ops, attachment)` on an already registered channel can update the interest/attachment of the existing key without creating unbounded duplicate keys.

`Selector.open()` picks an available provider; you should not hard-code assumptions about native mechanisms like `epoll`, `kqueue`, or `poll` to infer every platform characteristic. The JVM and operating system select the appropriate implementation.

## 3. Interest Ops and Ready Ops: Two Different Sets

Key operations:

| Operation | Typical Channel | When to Care? |
| --- | --- | --- |
| `SelectionKey.OP_ACCEPT` | `ServerSocketChannel` | The server has a new connection waiting for `accept()`. |
| `SelectionKey.OP_CONNECT` | `SocketChannel` | A non-blocking connection can be completed; call `finishConnect()`. |
| `SelectionKey.OP_READ` | `SocketChannel`, `Pipe.SourceChannel` | Data may be readable, or EOF/state needs handling. |
| `SelectionKey.OP_WRITE` | `SocketChannel`, `Pipe.SinkChannel` | More data may be writable to the channel. |

Each channel type only supports a set of ops published via `validOps()`. Do not register `OP_ACCEPT` on a `SocketChannel` or `OP_READ` on a `ServerSocketChannel`: an unsupported combination can throw `IllegalArgumentException`.

Example:

```java
// Snippet: socket is a connected non-blocking SocketChannel.
SelectionKey key = socket.register(selector, SelectionKey.OP_READ);
int wanted = key.interestOps(); // The application is interested in OP_READ.
int ready = key.readyOps();     // Readiness detected in the recent selection.
```

These two bitmask flag sets are **not synonymous**. `interestOps` is the monitoring intent; `readyOps` is the selected readiness signal. Check safely with `key.isValid()` before methods that depend on key state. Convenience methods like `isReadable()`, `isWritable()`, `isAcceptable()`, and `isConnectable()` correspond to bits in ready ops.

**Readiness does not guarantee the operation will transfer data.** Between when `select()` returns and the I/O call, state can change; a `read`/`write` on a non-blocking channel can still return 0. Always handle the actual result.

## 4. Non-Blocking Mode Must Be Configured Before Registering

To register a channel with a selector, the channel must be in **non-blocking** mode:

```java
// Snippet: server is an open ServerSocketChannel.
server.configureBlocking(false);
server.register(selector, SelectionKey.OP_ACCEPT);
```

If the channel is still blocking, registration can throw `IllegalBlockingModeException`. For a connected `SocketChannel`:

```java
socket.configureBlocking(false);
socket.register(selector, SelectionKey.OP_READ, connectionState);
```

This is a snippet; `selector` and `connectionState` are declared by the program. Once a channel is registered with any selector, you cannot arbitrarily switch it back to blocking mode; attempting to configure blocking mode usually causes `IllegalBlockingModeException` while a valid registration exists.

**`FileChannel` is not a `SelectableChannel`** and does not use `register(selector, OP_READ)`. File reads via `FileChannel` can still block; when a network event loop needs file I/O, handle file I/O with a dedicated strategy such as a thread pool, an appropriate asynchronous API, or controlled data transfer.

## 5. Standard Event Loop Cycle

Typical processing flow:

```text
1. Selector.open()
2. Create + configureBlocking(false) on channels
3. register(selector, interestOps, attachment)
                    |
                    v
          selector.select()
                    |
       +------------+-------------+
       | selectedKeys()           |
       v                          |
4. Iterate each SelectionKey      |
5. iterator.remove()              |
6. Check key.isValid()            |
7. Handle ACCEPT/CONNECT/READ/WRITE
8. Update interestOps, buffers    |
9. Close/cancel when needed       |
       |                          |
       +--------------------------+
```

Typical Java skeleton:

```java
// Snippet: selector is open and channels are registered.
while (running) {
    selector.select(); // Wait for at least one event or wakeup/interrupt.
    Iterator<SelectionKey> it =
            selector.selectedKeys().iterator();

    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove(); // Remove from the selected-key set after retrieving.

        if (!key.isValid()) {
            continue;
        }
        if (key.isAcceptable()) {
            handleAccept(key);
        }
        if (key.isValid() && key.isConnectable()) {
            handleConnect(key);
        }
        if (key.isValid() && key.isReadable()) {
            handleRead(key);
        }
        if (key.isValid() && key.isWritable()) {
            handleWrite(key);
        }
    }
}
```

The snippet above is **Java-like pseudocode**, assuming `running` and the `handle...` methods exist in your program. Each handler can cancel the key, close the channel, or change interest ops, so you must check validity appropriately before subsequent use.

**Why is `iterator.remove()` mandatory in this pattern?** `selectedKeys()` is the set of selected keys and is not automatically cleared on each iteration. If you do not remove a processed key, it can keep appearing and cause repeated processing on an old event. Do not clear via `selector.selectedKeys().clear()` while iterating with the same iterator.

## 6. Standalone Java 17+ Example: One Selector Monitoring Two Pipes

To demonstrate the **one thread – many channels** mechanism without depending on a network or ports, this example uses **two `Pipe.SourceChannel` instances**. They are selectable channels that can accept `OP_READ`. Two `Pipe.SinkChannel` instances write messages, and the selector reads from the corresponding sources.

Each message ends with a newline character. The read buffer is intentionally small (3 bytes) to illustrate that **a message can be received in multiple chunks**, so incomplete state is held in `Session.pending`. Once a message is complete, the program cancels the key. Results are stored in a `TreeMap` to print in a stable order, because **the order of ready keys is not guaranteed**.

Save with the exact filename **`SelectorMultiplexDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;
import java.util.Map;
import java.util.TreeMap;

public class SelectorMultiplexDemo {
    private static final class Session {
        final String name;
        final ByteArrayOutputStream pending = new ByteArrayOutputStream();
        Session(String name) { this.name = name; }
    }

    private static void send(Pipe.SinkChannel sink, String text)
            throws IOException {
        ByteBuffer data = ByteBuffer.wrap(
                (text + "\n").getBytes(StandardCharsets.US_ASCII));
        while (data.hasRemaining()) {
            sink.write(data);
        }
    }

    public static void main(String[] args) throws IOException {
        Pipe a = Pipe.open();
        Pipe b = Pipe.open();
        try (Selector selector = Selector.open();
             Pipe.SourceChannel readA = a.source();
             Pipe.SinkChannel writeA = a.sink();
             Pipe.SourceChannel readB = b.source();
             Pipe.SinkChannel writeB = b.sink()) {

            readA.configureBlocking(false);
            readB.configureBlocking(false);
            readA.register(selector, SelectionKey.OP_READ, new Session("A"));
            readB.register(selector, SelectionKey.OP_READ, new Session("B"));

            send(writeA, "alpha");
            send(writeB, "beta");

            Map<String, String> received = new TreeMap<>();
            while (received.size() < 2) {
                if (selector.select(2_000) == 0) {
                    throw new IOException("Timeout chờ dữ liệu");
                }
                Iterator<SelectionKey> iterator =
                        selector.selectedKeys().iterator();
                while (iterator.hasNext()) {
                    SelectionKey key = iterator.next();
                    iterator.remove();
                    if (!key.isValid() || !key.isReadable()) {
                        continue;
                    }
                    Session session = (Session) key.attachment();
                    Pipe.SourceChannel channel =
                            (Pipe.SourceChannel) key.channel();
                    ByteBuffer chunk = ByteBuffer.allocate(3);
                    while (key.isValid()) {
                        int n = channel.read(chunk);
                        if (n == -1) {
                            throw new IOException("EOF trước dấu kết thúc");
                        }
                        if (n == 0) {
                            break;
                        }
                        chunk.flip();
                        while (chunk.hasRemaining()) {
                            byte ch = chunk.get();
                            if (ch == '\n') {
                                received.put(session.name,
                                        session.pending.toString(
                                                StandardCharsets.US_ASCII));
                                key.cancel();
                                break;
                            }
                            session.pending.write(ch);
                        }
                        chunk.clear();
                    }
                }
            }
            System.out.println("channels=" + received.size());
            received.forEach((name, message) ->
                    System.out.println(name + "=" + message));
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 SelectorMultiplexDemo.java
java SelectorMultiplexDemo
```

Stdout verified when actually compiled and run on Java 17+:

```text
channels=2
A=alpha
B=beta
```

Points to observe:

1. `Pipe.open()` creates **two** source/sink pairs. The program runs only one `main` thread handling selection, without creating a thread per channel.
2. Both sources are configured with `configureBlocking(false)` and then `register(selector, OP_READ, Session)`. Each key attaches a name and a container for incomplete data.
3. `send` writes ASCII strings with a newline to both sinks. `write` is called in a loop until the buffer has no remaining bytes; the sinks in the demo remain in blocking mode and only write a small amount **before** the event loop, making it suitable for a self-contained example.
4. `selector.select(2_000)` waits up to about two seconds for ready keys; the demo throws an error if no progress occurs, helping avoid waiting forever when the environment does not supply data as expected.
5. Each `SourceChannel.read` reads at most three bytes at a time. If it returns 0, the non-blocking source currently has no more bytes; the inner loop exits to return to the selector. When `\n` is encountered, the complete message is stored in the map and the key is canceled.
6. Output is sorted A then B using `TreeMap`. Do not assume `selectedKeys()` always iterates keys in registration order.
7. `try-with-resources` closes the selector and all four channels on completion. The demo does not use the network, open ports, or use multiple threads.

**Intentional limitations of the demo:** it only receives a single short ASCII line per pipe and does not allow large messages or multiple lines in the same chunk. In a real server, the handler must handle multiple frames in a single read pass, bound buffer sizes, guard against malicious data, and preserve state across select iterations.

## 7. Applying the Model to TCP ServerSocketChannel

A TCP server typically starts with:

```java
// Snippet: requires imports Selector, SelectionKey,
// ServerSocketChannel, SocketChannel, InetSocketAddress.
Selector selector = Selector.open();
ServerSocketChannel server = ServerSocketChannel.open();
server.configureBlocking(false);
server.bind(new InetSocketAddress("127.0.0.1", 8080));
server.register(selector, SelectionKey.OP_ACCEPT);
```

When receiving `OP_ACCEPT`:

```java
// Snippet: key retrieved from the selectedKeys() loop.
ServerSocketChannel server =
        (ServerSocketChannel) key.channel();
SocketChannel client = server.accept();
if (client != null) {
    client.configureBlocking(false);
    client.register(selector, SelectionKey.OP_READ,
            new ConnectionState());
}
```

`ConnectionState` is a class **the application must define**, for example containing `ByteBuffer input`, an output queue, and parser state. These two snippets are **illustrative**, and do not include server/socket closing lifecycle, error handling, or full imports.

With a non-blocking server, `accept()` can return `null` even if readiness previously reported accept; conditions can change. Do not use a busy-wait loop `while (accept() == null) { }`. When an event allows, you can loop `accept()` until it returns null to process multiple pending connections, but you must set a reasonable work budget so as not to starve other channels.

A newly accepted socket needs `configureBlocking(false)` **before** registering `OP_READ`; if forgotten, `register` can fail. The event-loop thread can maintain per-connection state via attachments without needing a Java thread per connection.

## 8. OP_CONNECT: Incomplete Non-Blocking Connection

For a client actively initiating a connection:

```java
// Snippet: selector is already open.
SocketChannel client = SocketChannel.open();
client.configureBlocking(false);
boolean connected = client.connect(remoteAddress);
if (connected) {
    client.register(selector, SelectionKey.OP_READ, state);
} else {
    client.register(selector, SelectionKey.OP_CONNECT, state);
}
```

`remoteAddress` and `state` must be declared in the application context. When the key reports `isConnectable()`:

```java
SocketChannel client = (SocketChannel) key.channel();
if (client.finishConnect()) {
    key.interestOps(SelectionKey.OP_READ);
}
```

Before `finishConnect()` succeeds, do not treat the socket as ready to handle the application protocol. The connection can fail with `IOException`. On failure, cancel the registration, close the channel, and report the error or apply a retry policy; do not continue enabling `OP_READ` on a broken socket.

Note: `OP_CONNECT` is an event to **check and complete the connection**, not proof that the connection has succeeded.

## 9. OP_READ: How Many Bytes Are Enough?

An `OP_READ` means reading may make progress. With a non-blocking `SocketChannel`:

- `read(buffer) > 0`: transferred that many bytes into the buffer and advanced `position`.
- `read(buffer) == 0`: no bytes transferred; exit the current read attempt loop and wait for new readiness.
- `read(buffer) == -1`: peer closed its write side / EOF; depending on the protocol, you may allow half-close or close the connection after processing remaining data.

State pattern when the parser can hold an incomplete frame:

```java
// Snippet: non-blocking socket; state.input is a ByteBuffer
// in write mode, with enough capacity to process at least the header.
int n = socket.read(state.input);
if (n == -1) {
    closeConnection(key);
} else if (n > 0) {
    state.input.flip();
    decodeAvailableFrames(state.input, state);
    state.input.compact();
}
```

The functions `closeConnection`/`decodeAvailableFrames` and the `state` type are **design scaffolding**, not built-in JDK APIs. `decodeAvailableFrames` must only consume bytes that actually form a complete frame or retain the required state. `compact()` preserves bytes not yet consumed by the parser, moving them to the beginning of the buffer so the next `read` continues seamlessly.

**Do not equate a single TCP `read` with a single request.** TCP is a byte stream: one `read` may receive half a header, one full request, or multiple concatenated requests. Choose framing accordingly: length-prefix, delimiter, fixed-size, or an appropriate protocol decoder. For untrusted data, enforce limits on length, frame count, rate, memory, and time.

If the parser cannot make progress and the input buffer is full, have a plan to grow capacity within bounds, stream the payload, or reject the request; calling `read` into a buffer with no `remaining()` simply causes a no-progress condition.

## 10. OP_WRITE: Register Only When There Is Data to Send

For a TCP connection, the socket is usually writable most of the time whenever the OS send buffer has space. If a program keeps `OP_WRITE` in interest ops **constantly even when no data is waiting**, the selector can repeatedly wake up the event loop, causing a **busy loop** and wasting CPU.

Common strategy:

1. Monitor `OP_READ` by default.
2. When there is a message to send, encode it into a `ByteBuffer` and enqueue it into the connection's outbound queue.
3. Try `socket.write(buffer)`. If unsent bytes remain, keep the buffer with its advanced `position` and enable `OP_WRITE`.
4. When receiving `OP_WRITE`, write pending buffers until data is exhausted, a budget limit is reached, or `write` returns 0.
5. When the outbound queue is empty, **remove `OP_WRITE` from interest ops** to avoid unnecessary wakeups.

Bitmask toggle pattern:

```java
// Enable write interest while preserving other flags:
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);

// Once everything has been sent:
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
```

This is a snippet; the key must still be valid. **Do not** blindly call `interestOps(SelectionKey.OP_WRITE)` if you still need to read, because that replaces the **entire** bitmask and can accidentally turn off `OP_READ`.

Write handling pattern (with an application-managed `ByteBuffer` queue):

```java
// Snippet: pending is the ByteBuffer at the head of the queue,
// non-blocking socket, valid key.
while (pending.hasRemaining()) {
    int written = socket.write(pending);
    if (written == 0) {
        break; // Preserve position/limit to retry when OP_WRITE is ready.
    }
}
```

`write` can transfer fewer than `remaining()`. Do not `clear()` or recreate a partially written buffer; that will lose data or send duplicates. A production outbound queue needs to coordinate multiple buffers, bound queued size (backpressure), and close slow connections according to policy.

## 11. selectedKeys, keys, and Cancellation

Distinguish the sets:

| API | Meaning |
| --- | --- |
| `selector.keys()` | Keys currently registered with the selector (excluding keys already removed as part of the cancellation process). |
| `selector.selectedKeys()` | The set of keys with selected readiness, for the application to iterate and **remove processed keys**. |
| `key.cancel()` | Marks registration for cancellation; the key becomes invalid, and deregistration is processed during subsequent selection operations. |
| `key.isValid()` | Checks whether the registration is still valid at the time of the call. |
| `key.channel()` / `key.selector()` | Retrieves the associated channel/selector. |
| `key.attach(obj)` / `key.attachment()` | Stores/retrieves connection state, reducing the need for global maps. |

Practical point: **`key.cancel()` does not equate to closing the channel**. If the connection is broken or the application is finished with it, close the `SocketChannel`/`Pipe.SourceChannel` when you own it; closing a channel invalidates its associated registrations, though it does not necessarily close the selector itself.

Do not loop over all of `selector.keys()` to look for ready ops after `select()`; use `selectedKeys()`. Do not arbitrarily mutate key sets disallowed by the API; the standard pattern is `iterator.remove()` on the selected set.

A key can be simultaneously ready for multiple valid ops, so handlers must consider ordering, check `isValid()` after any step that might cancel the key, and bound work per iteration so other connections are served fairly.

## 12. select(), select(timeout), selectNow(), and wakeup()

| Method | Primary Meaning |
| --- | --- |
| `select()` | Waits until selection can complete; can be woken up by `wakeup()`/interrupt/close. |
| `select(long timeout)` | Waits up to the specified time in milliseconds if timeout is positive; `timeout == 0` means wait indefinitely per API. |
| `selectNow()` | Performs **non-blocking** selection. |
| `wakeup()` | Requests waking up a currently blocked or upcoming `select` operation; takes effect for a selection cycle. |
| `close()` | Closes the selector; associated registrations are canceled, without automatically closing all channels. |

`select()` returns the number of keys whose readiness information was updated in that selection, **not** the number of requests processed or total bytes readable. Returning 0 is not necessarily an error: it can happen due to timeout, wakeup, or other selection contexts. A real event loop must handle a 0 return appropriately, avoiding spinning continuously when no progress is made.

When another thread updates application state that the event loop needs to process promptly, a common pattern is:

```java
// Snippet: executed by producer thread.
pendingTasks.add(task); // Thread-safe queue provided by the application.
selector.wakeup();
```

Upon waking up, the event loop drains work from the queue and updates registrations/interest ops. **Do not** let producer threads directly modify non-thread-safe state of handlers. If you are concerned about concurrent selector configuration, consult the JDK synchronization rules; do not rely on "usually works" instead of the contract.

Waking a selector **does not send network data** and does not guarantee a socket is writable; it is purely a coordination signal, after which the event loop must still check channel state and queues.

## 13. Things Never to Do in an Event Loop

- **Do not make blocking I/O calls** inside a handler of an event loop managing multiple connections: e.g., synchronous JDBC, direct large file reads, or blocking network calls.
- **Do not busy-spin when `read/write == 0`.** On a non-blocking channel, return to `select` and wait for appropriate readiness.
- **Do not keep `OP_WRITE` permanently enabled when the outbound queue is empty.** Write readiness can be reported repeatedly, spiking CPU usage.
- **Do not assume `readyOps` guarantees a specific number of bytes will transfer.** `read/write` can still transfer fewer bytes, or even 0.
- **Do not share a single `ByteBuffer`/parser state across all connections** if data can interleave; each connection needs its own state or controlled ownership.
- **Do not process one connection indefinitely during a single readiness event.** Limit bytes, frames, or time per key to ensure fairness.
- **Do not allow unbounded outbound queues.** Slow connections can cause the application to run out of memory.
- **Do not ignore invalid keys or closed channels** during resource cleanup; `CancelledKeyException`/`ClosedChannelException` can occur if state changes.
- **Do not use Selector as a substitute for an application protocol**: framing, encoding, validation, authorization, timeouts, and recovery still belong in the application layer.

## 14. Single-Thread Architecture Model and How to Scale

For a large number of connections, one thread monitoring readiness across many channels is effective when each handler performs lightweight work. As load grows, you can use **multiple event-loop threads**, each owning its own selector and a distinct subset of connections, combined with a worker pool for CPU/blocking tasks. Assigning which selector owns a channel is an architectural decision; avoid concurrently processing the same connection from multiple event loops without an explicit ownership strategy.

Layered example:

```text
                      Acceptor / ServerSocketChannel
                                  |
                        Accept TCP connection
                                  |
                        Distribute connection
                          /                 \
                 Event loop A            Event loop B
                   Selector A              Selector B
                   N sockets               M sockets
                      |                       |
               Decode + queue          Decode + queue
                          \                 /
                           Worker pool
                        (CPU/blocking jobs)
                                  |
                         Results via task queue
                         + selector.wakeup()
```

This is an illustrative model, not a requirement that every system must use multiple selectors. For services with moderate traffic, a single simple, clear, and measurable event loop may suffice; adding more threads/selectors requires managing thread ownership, queues, state synchronization, and more complex shutdown.

### Complexity and Limits

Selector reduces the need to hold one blocking thread per connection, but **does not make sockets/file descriptors free**. OS resources, per-connection memory, buffer counts, quotas, handler latency, TLS, timeouts, and backpressure still limit capacity. Actual performance must be measured under representative traffic patterns.

Not every channel supports a selector, and not every kind of I/O is a readiness API. For instance, ordinary streams or file channels may require different handling strategies. Choosing an event loop depends on workload patterns and state management requirements.

## 15. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| `IllegalBlockingModeException` | Calling `register` while the channel is blocking, or switching to blocking while still registered. | Call `configureBlocking(false)` before `register`; manage lifecycle clearly. |
| `IllegalArgumentException` on `register` | Interest ops are not in the channel's `validOps()`. | Choose the right OP_ACCEPT/CONNECT/READ/WRITE for the channel type. |
| 100% CPU with low traffic | Keeping `OP_WRITE` enabled or spinning when `read/write == 0`. | Remove OP_WRITE when the queue is empty; wait for readiness/wakeup. |
| A request is processed repeatedly | Not removing the key from `selectedKeys()`. | Call iterator.remove() immediately during iteration. |
| `CancelledKeyException` | Checking readiness/interest after the key was canceled or channel closed. | Check `isValid()` and stop handling when closed. |
| One connection slows down the entire server | Blocking handler, heavy CPU work, or unbounded processing loop. | Budget per event and offload blocking/CPU work to workers. |
| `write` reports success but client receives partial data | Not looping on `ByteBuffer.hasRemaining()`, losing state on partial write. | Retain the pending buffer and enable OP_WRITE until fully sent. |
| Server waits forever even though client sent partial data | Parser requires a full frame without preserving state or compacting properly. | Implement framing, persist input across turns, and bound sizes. |
| Client cannot connect | Forgot to register `OP_ACCEPT` or call `finishConnect()` on a non-blocking client. | Distinguish server/client lifecycles and handle OP_CONNECT. |
| No new keys after `wakeup()` | Wakeup only wakes `select`; it does not create I/O readiness. | Drain the task queue and then inspect keys as usual. |
| Closed socket but selector still holds invalid key | Cancellation is processed during the selection lifecycle; selected set not cleared. | Cancel the key, close the channel, remove handled keys, and close the selector on shutdown. |

While debugging, emit structured logs per connection: ID, interest ops, ready ops, bytes read/written, `buffer.position/limit`, pending byte count, close reason, and handler execution time. Be careful not to log payloads containing sensitive information or let logging block inside the event loop.

## 16. Practice Exercises

**Exercise 1 — Add a third channel.** Extend the demo program with `Pipe c`, register an additional non-blocking `SourceChannel`, and send `gamma\n`. Adjust the completion condition to wait for 3 messages. Use `TreeMap` to keep results ordered without relying on readiness order.

**Exercise 2 — Split messages into multiple chunks.** Change `ByteBuffer.allocate(3)` to `allocate(1)` and then `allocate(5)`. Prove that the output stays identical thanks to `Session.pending` and newline handling. Explain why calling `read` once and immediately turning its contents into a request is wrong.

**Exercise 3 — OP_WRITE and backpressure.** Design an outbound queue of three `ByteBuffer` objects per connection. Write pseudocode that enables `OP_WRITE` if pending data remains; disables it when the queue empties; and preserves buffer `position` when `write == 0`. Add a quota on queued bytes to prevent unbounded memory growth.

**Exercise 4 — TCP echo server.** Use a non-blocking `ServerSocketChannel` to accept clients on `OP_ACCEPT`, create a `ConnectionState` with input/output buffers, read on `OP_READ`, and echo data on `OP_WRITE`. Bound the queue capacity; close the socket when `read == -1` and no output remains to flush. Test two clients sending half a message at a time.

**Exercise 5 — Another thread updating the event loop.** Create a thread-safe task queue. A producer adds a task and calls `selector.wakeup()`. The event loop picks up the task, updates interest ops, and executes it on the selector-owning thread. Explain why a mutable `ByteBuffer` should not be passed across threads without managing ownership.

**Exercise 6 — Graceful shutdown.** Build a mechanism to stop accepting new connections, continue draining outbound queues with a deadline, then cancel keys, close channels, and close the selector. Log timeouts, exceptions, and already-closed channels to avoid resource leaks.

### Self-Check

1. Does `Selector.select()` return bytes read or the count/readiness update of channels?
2. Why does `SocketChannel` need `configureBlocking(false)` before registration?
3. How does `interestOps` differ from `readyOps`, and why should `OP_WRITE` not stay enabled all the time?
4. When `socket.read(buffer) == 0`, can we conclude EOF or must we wait for the next readiness?
5. Does `key.cancel()` automatically close the socket?
6. Why is `iterator.remove()` important when iterating `selectedKeys()`?
7. One event-loop thread can handle many sockets, so why must blocking/heavy-CPU operations still be moved elsewhere?
8. Why must a parser handle partial reads, partial writes, and multiple frames in a single read pass?

## 17. Official References

- [Java SE 21 — Selector](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html): key sets, selection, wakeup, and lifecycle.
- [Java SE 21 — SelectionKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectionKey.html): interest/ready ops, attachments, key cancellation, and bitmasks.
- [Java SE 21 — SelectableChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectableChannel.html): non-blocking mode, valid ops, and registration.
- [Java SE 21 — SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking connect, read/write, and EOF.

**Remember:** `Selector` is a tool to **multiplex readiness of multiple selectable channels on a single event-loop thread**. Register non-blocking channels with the right interest ops, iterate and remove selected keys, maintain per-connection state, handle `read/write` potentially transferring only part of the data, enable `OP_WRITE` only when data is actually queued, and never let blocking work stall the event loop.
