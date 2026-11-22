# Configuring Channels to Non-Blocking Mode and Registering SelectionKey in Java NIO

## 1. Objective and Big Picture

In Java NIO, **`Selector` monitors multiple `SelectableChannel` instances using one or a few threads**. For a channel to participate in this mechanism, you must **configure it to non-blocking mode first**, and then **register it with a `Selector` using `register(...)`**. The registration returns a **`SelectionKey`**: an object representing the relationship between **a channel**, **a selector**, **the events the application wants to monitor**, and **the events currently reported as ready by the operating system**.

Minimal example for a TCP server:

~~~java
// Snippet: selector and server have already been initialized.
server.bind(new InetSocketAddress("127.0.0.1", 8080));
server.configureBlocking(false);
SelectionKey key = server.register(selector, SelectionKey.OP_ACCEPT);
~~~

After `register`, the server **does not automatically accept connections or read payloads**. It merely tells the selector: "notify me when a new connection can be accepted". The event loop calls `selector.select()`, retrieves the selected keys from `selectedKeys()`, and then handles `isAcceptable()`, `isConnectable()`, `isReadable()`, or `isWritable()` accordingly.

**The most important rule:**

~~~text
open channel
  → bind/connect (if required by the API and context)
  → configureBlocking(false)
  → register(selector, interestOps [, attachment])
  → selector.select(...)
  → iterate over selectedKeys and remove each key
  → check readyOps, perform non-blocking I/O
  → update interestOps when I/O needs change
  → cancel/close when finished
~~~

For a non-blocking TCP client, `connect()` may still be in progress when registering `OP_CONNECT`; the connection does not have to complete before calling `register`. For a TCP server, you must **bind before `accept()` works**, and you should bind before waiting for `OP_ACCEPT`.

## 2. Three Objects: Channel, Selector, and SelectionKey

| Component | Role | Commonly Used APIs |
|---|---|---|
| `SelectableChannel` | I/O endpoint that can switch between blocking and non-blocking modes | `configureBlocking(false)`, `isBlocking()`, `register(...)`, `keyFor(...)`, `validOps()` |
| `Selector` | Coordinator that receives **readiness** notifications for registered channels | `Selector.open()`, `select()`, `select(timeout)`, `selectNow()`, `selectedKeys()`, `wakeup()` |
| `SelectionKey` | "Registration token" for **a channel + selector pair** | `interestOps()`, `readyOps()`, `isReadable()`, `attachment()`, `cancel()` |

A channel has only **one key per selector**, though it can be registered with multiple different selectors according to the API rules. `selector.keys()` and `selector.selectedKeys()` are not the same set: the former contains all current registrations; the latter contains the keys selected by the previous selection operation that have not yet been removed by the application from the selected-key set.

~~~text
ServerSocketChannel #A -- register(OP_ACCEPT) ---+
                                                  |
SocketChannel #B ------ register(OP_READ) --------+--> Selector #1
                                                  |      |
SocketChannel #C -- register(OP_READ|OP_WRITE) ---+      +--> select()
                                                         +--> selectedKeys()
                                                         +--> SelectionKey.readyOps
~~~

`Selector` is a multiplexer for **readiness events**; it does not turn a channel into a separate thread, nor does it automatically write business logic, send data, decode UTF-8, define request boundaries, or release sockets.

## 3. Mandatory Step: `configureBlocking(false)`

### 3.1. Blocking by default

`ServerSocketChannel.open()` and `SocketChannel.open()` create new channels in **blocking mode**. Verify:

~~~java
ServerSocketChannel server = ServerSocketChannel.open();
System.out.println(server.isBlocking()); // true when newly opened
server.configureBlocking(false);
System.out.println(server.isBlocking()); // false
~~~

This is an **illustrative snippet**; `server` must be closed after use. In blocking mode, calling `accept()` typically waits for an incoming connection; calling `read()` may wait for bytes. In non-blocking mode, an I/O operation returns immediately with whatever work can be done right now: `accept()` may return `null`, `SocketChannel.read()` may return `0`, and `write()` may write fewer bytes than expected.

### 3.2. The order must not be reversed

Registering a selectable channel that is **still in blocking mode** with a selector throws `IllegalBlockingModeException`.

~~~java
// WRONG: a newly opened server is blocking by default.
ServerSocketChannel server = ServerSocketChannel.open();
SelectionKey badKey = server.register(selector, SelectionKey.OP_ACCEPT);
// ↑ IllegalBlockingModeException
~~~

Correct:

~~~java
// Correct order; assuming selector is still open.
try (ServerSocketChannel server = ServerSocketChannel.open()) {
    server.bind(new InetSocketAddress("127.0.0.1", 0));
    server.configureBlocking(false);
    SelectionKey key = server.register(selector, SelectionKey.OP_ACCEPT);
}
~~~

You also **cannot arbitrarily switch back to `configureBlocking(true)`** while the channel is still registered with one or more selectors. Doing so throws `IllegalBlockingModeException`. `key.cancel()` only **marks the registration for cancellation**; actual deregistration is typically completed during a subsequent selection operation. `isRegistered()` may still be `true` immediately after `cancel()`. Do not write code assuming `cancel()` immediately allows switching back to blocking mode.

### 3.3. Mode of the listening channel differs from mode of the accepted channel

This is a common mistake when building a Java NIO TCP server:

- `ServerSocketChannel` has `configureBlocking(false)` called so the selector can monitor `OP_ACCEPT`.
- `ServerSocketChannel.accept()` returns a **new `SocketChannel`** for the client when a connection is ready.
- According to the Java 17 Javadoc, **a newly accepted `SocketChannel` defaults to blocking mode**, **regardless of whether the listener is blocking or non-blocking**.
- Therefore, you **must call `accepted.configureBlocking(false)` on every accepted channel** before calling `accepted.register(selector, SelectionKey.OP_READ)`.

~~~java
SocketChannel accepted = server.accept();
if (accepted != null) {
    accepted.configureBlocking(false); // Do not omit this line!
    accepted.register(selector, SelectionKey.OP_READ);
}
~~~

In non-blocking mode, `server.accept()` **may return `null`** if no connection is currently pending. A readiness event is only a hint at a point in time; do not treat `accept() != null` as an invariant immediately after `isAcceptable()`.

## 4. Registering a `SelectionKey` and Overloads

### 4.1. Basic syntax

~~~java
SelectionKey key = channel.register(selector, SelectionKey.OP_READ);
~~~

or with an attachment:

~~~java
ByteBuffer inbound = ByteBuffer.allocate(4096);
SelectionKey key = channel.register(
        selector, SelectionKey.OP_READ, inbound);
~~~

`register(selector, ops, attachment)` creates/locates the key representing the channel-selector pair, sets the initial **interest set**, and allows attaching **an application state object** (attachment). When handling multiple connections, the attachment is a convenient place to store the receive buffer, send buffer, parser, session ID, or protocol state **per connection**.

`register(selector, ops)` is equivalent to calling `register(selector, ops, null)`; when a key already exists, passing a `null` attachment argument **does not clear the previous attachment** per the `register` contract. To clear the current attachment, use `key.attach(null)` if needed.

### 4.2. Return value and an "already registered" key

When the same channel calls `register` again with the **same selector** and the existing key has not been cancelled, the API **returns the same key**, updating `interestOps` and the attachment if a non-`null` attachment is passed; it **does not create a second registration** for the same channel-selector pair.

~~~java
// Snippet on a non-blocking SocketChannel and an open Selector.
SelectionKey first = socket.register(selector, SelectionKey.OP_READ);
SelectionKey second = socket.register(
        selector, SelectionKey.OP_READ | SelectionKey.OP_WRITE);

System.out.println(first == second); // true (if the key is still valid)
~~~

Including `OP_WRITE` in the example above is **only to illustrate the bitmask**, not a recommendation to keep `OP_WRITE` continuously registered for every socket.

You can use `channel.keyFor(selector)` to look up an existing key (or `null` if it is no longer registered with this selector); `channel.isRegistered()` only answers whether it is registered with **any selector**. For a cancelled key, calling `register` again before cancellation completes can throw `CancelledKeyException`; manage the lifecycle explicitly rather than retrying blindly.

## 5. Interest Set and Ready Set: Two Different Concepts

A `SelectionKey` has two important **bitmasks**:

- **`interestOps()`:** the set of operations the application **wants the selector to monitor**; for example `OP_READ` or `OP_READ | OP_WRITE`.
- **`readyOps()`:** the set of operations that **a selection operation** determined can be performed; a key may be ready for only a subset of its interest set.

Example:

~~~text
interestOps = OP_READ | OP_WRITE
readyOps    = OP_WRITE

=> The application is interested in both reading and writing, but this time only writability was detected.
=> Do not assume OP_READ is ready just because it was included in interestOps.
~~~

The bits of `SelectionKey`:

| Bit | Hex Value | Typical Channel | Meaning of Readiness |
|---|---|---|---|
| `OP_ACCEPT` | `0x10` | `ServerSocketChannel` | A new connection is ready to be `accept`ed |
| `OP_CONNECT` | `0x08` | `SocketChannel` | A non-blocking connect is in a state that can be checked/completed |
| `OP_READ` | `0x01` | `SocketChannel`, `DatagramChannel`, `Pipe.SourceChannel` | Data is available to read, or an end-of-stream/error condition requires a read to handle |
| `OP_WRITE` | `0x04` | `SocketChannel`, `DatagramChannel`, `Pipe.SinkChannel` | At least partial writing is possible or the corresponding write state can proceed |

Readiness is a **hint**, not a guarantee of a minimum number of bytes or that the peer has processed anything. The operating system and timing of I/O execution can change the state after `select`. Therefore, handler code must tolerate `read(...) == 0`, `write(...) == 0`, or `accept() == null` on a non-blocking channel.

You can check:

~~~java
if (key.isValid() && key.isReadable()) {
    SocketChannel ch = (SocketChannel) key.channel();
    // Read only when the channel has the appropriate type and state.
}
~~~

The methods `isReadable()`, `isWritable()`, `isAcceptable()`, and `isConnectable()` check **bits in the ready set**, not `interestOps`. Do not call these methods unconditionally on a cancelled key; `CancelledKeyException` may be thrown. In a multi-threaded loop, validity can change after the check, so appropriate error/race handling is also needed.

## 6. `validOps()`: Register Only Event Types Supported by the Channel

Not all channels understand every flag.

| Channel Type | Valid Ops |
|---|---|
| `ServerSocketChannel` | `OP_ACCEPT` |
| `SocketChannel` | `OP_CONNECT | OP_READ | OP_WRITE` |
| `DatagramChannel` | `OP_READ | OP_WRITE` |
| `Pipe.SourceChannel` | `OP_READ` |
| `Pipe.SinkChannel` | `OP_WRITE` |

Check using `channel.validOps()` instead of assuming all channels always accept all four bits. For example, registering `OP_ACCEPT` for a `SocketChannel` or `OP_READ` for a `ServerSocketChannel` is invalid and throws `IllegalArgumentException`.

~~~java
// Snippet:
int requested = SelectionKey.OP_READ | SelectionKey.OP_WRITE;
if ((requested & ~socket.validOps()) != 0) {
    throw new IllegalArgumentException("Unsupported interest operation");
}
socket.register(selector, requested);
~~~

`ops=0` is also valid: the key remains registered without expressing any interest; use this when you need to temporarily pause I/O monitoring. However, while disabled, the selector will not notify readiness for the turned-off bits. You must manage when to re-enable them so application logic does not "hang".

## 7. Complete Java 17+ Example: Non-Blocking Server, Register, Select, and Read Data

The following example uses only **localhost/loopback** and an OS-assigned ephemeral port, so it requires no Internet access or external server. It intentionally uses a **client in blocking mode** to keep the demo focused on server-side selector registration. Only the **server listener and accepted socket** are monitored by the selector.

Demo flow:

1. `Selector.open()`; `ServerSocketChannel.open()`; bind loopback port `0`.
2. `server.configureBlocking(false)` and then register `OP_ACCEPT`.
3. Client connects and sends the ASCII line `PING\n`.
4. `selector.select(1000)` returns when readiness occurs; the loop retrieves and **removes** each selected key.
5. On `OP_ACCEPT`: `accept()`, **configure the accepted channel as non-blocking**, and register `OP_READ` with its own `ByteBuffer`.
6. On `OP_READ`: read into the buffer, check for the newline delimiter; if complete, print `PING` and close the accepted channel.
7. An overall 5-second deadline is used so the demo does not wait forever when run in constrained environments.

Create the file **`SelectorRegistrationDemo.java`**:

~~~java
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

public class SelectorRegistrationDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(loopback, 0));
            server.configureBlocking(false);
            SelectionKey listenKey =
                    server.register(selector, SelectionKey.OP_ACCEPT);
            System.out.println("listenInterest=" +
                    (listenKey.interestOps() == SelectionKey.OP_ACCEPT));

            try (SocketChannel client = SocketChannel.open(
                    new InetSocketAddress(loopback,
                            server.socket().getLocalPort()))) {
                ByteBuffer request = StandardCharsets.US_ASCII.encode("PING\n");
                while (request.hasRemaining()) {
                    client.write(request);
                }
                client.shutdownOutput();

                boolean done = false;
                long deadline = System.nanoTime() + 5_000_000_000L;
                while (!done && System.nanoTime() < deadline) {
                    if (selector.select(1000) == 0) {
                        continue;
                    }
                    Iterator<SelectionKey> keys = selector.selectedKeys().iterator();
                    while (keys.hasNext()) {
                        SelectionKey key = keys.next();
                        keys.remove();
                        if (!key.isValid()) {
                            continue;
                        }
                        if (key.isAcceptable()) {
                            ServerSocketChannel listener =
                                    (ServerSocketChannel) key.channel();
                            SocketChannel peer = listener.accept();
                            if (peer != null) {
                                peer.configureBlocking(false);
                                peer.register(selector, SelectionKey.OP_READ,
                                        ByteBuffer.allocate(64));
                                System.out.println("acceptedNonBlocking=" +
                                        !peer.isBlocking());
                            }
                        } else if (key.isReadable()) {
                            SocketChannel peer = (SocketChannel) key.channel();
                            ByteBuffer data = (ByteBuffer) key.attachment();
                            int n = peer.read(data);
                            if (n == -1) {
                                throw new IOException("EOF before newline");
                            }
                            for (int i = 0; i < data.position(); i++) {
                                if (data.get(i) == '\n') {
                                    data.flip();
                                    String text = StandardCharsets.US_ASCII
                                            .decode(data).toString();
                                    System.out.println("received=" +
                                            text.substring(0, text.indexOf('\n')));
                                    done = true;
                                    key.cancel();
                                    peer.close();
                                    break;
                                }
                            }
                            if (!done && !data.hasRemaining()) {
                                throw new IOException("Request exceeded buffer");
                            }
                        }
                    }
                }
                if (!done) {
                    throw new IOException("Selector deadline expired");
                }
            }
        }
    }
}
~~~

Run with **JDK 17 or later**:

~~~bash
javac --release 17 SelectorRegistrationDemo.java
java SelectorRegistrationDemo
~~~

**Stdout verified on OpenJDK 24 when compiled with `--release 17`:**

~~~text
listenInterest=true
acceptedNonBlocking=true
received=PING
~~~

Output explanation:

- `listenInterest=true`: the listener's key has an interest set of exactly `OP_ACCEPT`.
- `acceptedNonBlocking=true`: the **newly accepted** channel was switched to non-blocking mode **before registering `OP_READ`**. If `peer.configureBlocking(false)` were omitted, `peer.register(...)` would throw `IllegalBlockingModeException`.
- `received=PING`: the selector reported readiness, the accepted `SocketChannel` received the bytes, and the parser found the newline and extracted the complete line.

**Demo limitations:** this is not a production multi-client server. It serves a single short request, allocates only a 64-byte buffer, and exits after one message. It has no full protocol, writes no response, does not support multiple consecutive frames, does not replace a TLS/HTTP server, and does not guarantee graceful shutdown for a large number of connections. The client is intentionally kept blocking; if you need to connect a client using a selector, use `OP_CONNECT` and `finishConnect()` as shown in a later section.

## 8. Why Must You Call `keys.remove()` When Iterating Over `selectedKeys()`?

A `selector.select(...)` operation adds/updates keys that have readiness events in the **selected-key set**. This set **is not automatically cleared just because you read it**. If you forget to remove a key after processing it, an old key can remain in the set, causing your code to reprocess the event or report inaccurate statistics.

Common pattern:

~~~java
Iterator<SelectionKey> it = selector.selectedKeys().iterator();
while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();                   // Remove from the selected-key set
    if (!key.isValid()) continue;

    if (key.isAcceptable()) {
        // Accept a new connection.
    } else if (key.isConnectable()) {
        // Complete a non-blocking connect.
    } else {
        if (key.isReadable()) {
            // Receive data.
        }
        if (key.isWritable()) {
            // Send pending data.
        }
    }
}
~~~

This is an **event-handling skeleton**, not a standalone runnable program. `it.remove()` only removes the key from the **selected-key set**; it **does not deregister** the channel from the selector. To deregister, call `key.cancel()` and/or close the channel when appropriate.

In the skeleton above, `isReadable()` and `isWritable()` are checked **independently** because a selected key can be ready for both reading and writing in the same turn. Do not put them in an `else if` chain that would miss one side when the application needs to serve both. `OP_ACCEPT` and `OP_CONNECT` typically have separate handling based on channel type.

`selector.keys()` shows all currently managed registrations; **do not use `keys().clear()` to cancel everything**. The total key set does not support direct modification like the selected-key set; cancel keys using `cancel` and manage the channel lifecycle.

## 9. Managing Per-Connection State with Attachments

With multiple accepted sockets, each connection needs its own receive/write buffers. You can attach a session state object:

~~~java
// Snippet declaring application state.
final class ConnectionState {
    final ByteBuffer inbound = ByteBuffer.allocate(8192);
    ByteBuffer outbound;
    boolean peerFinishedSending;
}
~~~

On accept:

~~~java
SocketChannel peer = server.accept();
if (peer != null) {
    peer.configureBlocking(false);
    peer.register(selector, SelectionKey.OP_READ, new ConnectionState());
}
~~~

When the selected key is ready:

~~~java
// Snippet; key is a valid registration of a SocketChannel.
ConnectionState state = (ConnectionState) key.attachment();
SocketChannel peer = (SocketChannel) key.channel();
int n = peer.read(state.inbound);

if (n == -1) {
    state.peerFinishedSending = true;
    // Handle EOF/incomplete frame per protocol, then decide whether to close.
} else if (n > 0) {
    state.inbound.flip();
    // Process as many complete messages as can be parsed.
    // Retain unparsed bytes; do not drop a partial frame.
    state.inbound.compact();
}
~~~

**These are linked snippets**, not a self-contained runnable program. `ConnectionState` must be provided by the application; the parser and outbound queue must be implemented according to the protocol. `ByteBuffer` maintains per-connection state; avoid sharing a single `ByteBuffer` across all clients without ownership rules.

Do not retain references to sessions/buffers indefinitely after a key is cancelled: close the channel and remove related references, queues, timers, or map entries to avoid memory leaks.

## 10. `OP_CONNECT`: Registering a Non-Blocking Connecting Client

With a `SocketChannel` in non-blocking mode, `connect(remote)` may complete immediately (`true`) or be pending completion (`false`). If the connection is not finished yet, register `OP_CONNECT`:

~~~java
// Snippet: selector is already open; remote is a valid InetSocketAddress.
SocketChannel client = SocketChannel.open();
client.configureBlocking(false);
boolean alreadyConnected = client.connect(remote);

SelectionKey key = client.register(
        selector,
        alreadyConnected ? SelectionKey.OP_READ : SelectionKey.OP_CONNECT
);
~~~

If a subsequent selection sees `key.isConnectable()`:

~~~java
// Snippet for the same client in non-blocking mode.
if (key.isValid() && key.isConnectable()) {
    SocketChannel client = (SocketChannel) key.channel();
    if (client.finishConnect()) {
        key.interestOps(SelectionKey.OP_READ);
        // TCP connection is complete; begin application protocol.
    }
}
~~~

`finishConnect()` may throw `IOException` if the connection is refused, times out, or fails at the OS layer. Registering `OP_CONNECT` **does not automatically send an application request**, nor does it guarantee the connection will ultimately succeed. If `connect` already returned `true`, there is no need to wait for `OP_CONNECT`; switch to the appropriate interest immediately.

In a program with pending outbound data to send, you can switch to `OP_READ | OP_WRITE` **only when needed** (and turn off `OP_WRITE` once everything is sent). A complete HTTP client also needs message framing, timeouts, shutdown, and error policies beyond the TCP connection.

## 11. `OP_WRITE`: Avoiding Busy Loops and Data Loss on Partial Writes

Typical mistake:

~~~java
// Prone to causing a busy loop when the socket has available send-buffer capacity:
socket.register(selector, SelectionKey.OP_READ | SelectionKey.OP_WRITE);
~~~

On many operating systems, a TCP socket is **writable** most of the time. If you stay interested in `OP_WRITE` permanently, the selector may wake up continuously even when the application has no bytes to send: the loop wastes CPU ("spins") uselessly.

Practical rule:

1. By default, register only `OP_READ` after the connection is ready for receiving.
2. When the outbound queue has unsent bytes, enable `OP_WRITE`.
3. In `isWritable()`, call `SocketChannel.write(ByteBuffer)`; after the write, `ByteBuffer.position()` reflects the number of bytes transferred to the local channel.
4. If the buffer still `hasRemaining()`, keep that buffer for the next writable event. **Do not call `clear()` and overwrite the unsent portion**.
5. When there is no pending outbound data left, **turn off `OP_WRITE`** to avoid continuous wakeups.

~~~java
// Snippet: valid key, accepted SocketChannel, one outbound ByteBuffer.
if (key.isWritable()) {
    SocketChannel peer = (SocketChannel) key.channel();
    ByteBuffer data = (ByteBuffer) key.attachment(); // Example with outbound attached.
    peer.write(data);
    if (!data.hasRemaining()) {
        key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
    }
}
~~~

This is only **a piece of logic**, not a complete loop. A production app will have connection state storing **separate inbound and outbound**, handling multiple buffers, close, backpressure, cancellation, and race conditions.

`OP_WRITE` means the socket can accept **some** more bytes on the local side; it is **not** an ACK that the remote peer has received or processed the data. `write` can return **0** in non-blocking mode; in that case, do not run an infinite `while(hasRemaining)` loop on the selector thread. Keep the remainder and wait for the next readiness event.

## 12. `Selector.select`, Timeouts, and Wakeup

Commonly used APIs:

| API | Meaning |
|---|---|
| `select()` | Waits until readiness occurs, `wakeup`/interrupt happens, or another documented condition causes it to return |
| `select(long timeout)`, with `timeout > 0` | Waits at most the requested duration in **milliseconds** |
| `select(0)` | **Waits indefinitely without a timeout**, **not** an immediate poll |
| `selectNow()` | **Does not block**; checks current readiness |
| `wakeup()` | Requests an ongoing or next selection operation to return; commonly used to coordinate interest/configuration changes from another thread |

Do not write logic like `if (selector.select() == 0) throw ...` and conclude with certainty that "no channels are active anymore": selection can return due to wakeup, interrupt, or other conditions, and readiness can change over time.

Deadline example:

~~~java
long deadline = System.nanoTime() + 5_000_000_000L;
while (System.nanoTime() < deadline) {
    int count = selector.select(1000);
    if (count == 0) {
        continue; // No new selected keys yet; check deadline.
    }
    // Iterate over selectedKeys and process.
}
~~~

Use `System.nanoTime()` for **elapsed time within the same JVM**, not as a meaningful timestamp across machines or different JVM sessions. For a production deadline, compute the remaining timeout instead of always waiting a large interval that exceeds the budget; the demo example uses 1-second slices and checks the deadline before each slice, so it can overshoot by up to one selection interval.

When **another thread** changes `interestOps` or enqueues work, when that update is observed by an ongoing `select` call depends on the selector's synchronization rules; the common pattern is to place the task into a selector-thread queue and call `selector.wakeup()` so it drains the task and updates interests before the next loop iteration. Do not mutate buffers, keys, and queues from multiple threads without a clearly defined coordination mechanism.

## 13. Readiness Events Do Not Replace Protocol Framing

The selector observes the ability to perform **channel-level I/O**; it does not know what "finished reading the entire JSON", "received a complete HTTP request", or "got a full N-byte message" means.

For example, a client wants to send a 100-byte frame, but one `read` puts 37 bytes into the `ByteBuffer`: `OP_READ` fired and `read()` returned 37, yet **the message is incomplete**. When parsing:

~~~java
// Snippet: channel is a SocketChannel registered for OP_READ.
int bytes = channel.read(inbound);
if (bytes > 0) {
    inbound.flip();   // Prepare to read the bytes actually received.
    // Consume only complete frames; keep any incomplete tail.
    inbound.compact();
} else if (bytes == -1) {
    // EOF: peer closed its output; check for any incomplete frame.
} else {
    // bytes == 0 in non-blocking mode: no bytes transferred right now.
}
~~~

Do not equate `ByteBuffer.remaining() > 0` with "the socket has new data": it is the number of bytes remaining in the **current `ByteBuffer` window** being operated on. After `flip`, `remaining` is typically the unparsed bytes; before `flip`, `remaining` is typically the **space still available for writing**.

If a frame is larger than capacity, `compact` will not automatically expand memory. Design buffer sizes and payload limits to avoid stalling the parser when the buffer is full without a complete message.

## 14. Lifecycle Management and Safe Deregistration

A `SelectionKey` remains valid until `cancel()` is called, its channel is closed, or its selector is closed. However, cancelling a key **does not mean** closing the socket: resource management is the application's responsibility.

~~~java
// Snippet to clean up a connection; close may throw IOException.
key.cancel();
key.channel().close();
~~~

When **closing a channel**, its associated registration keys are implicitly cancelled. When **closing a selector**, its keys are invalidated and deregistered; the associated channels **are not necessarily closed by closing the selector**. Therefore, manage the `Selector`, listening channel, accepted channels, and client channels with clear resource ownership.

In a multi-client server, consolidate cleanup into an idempotent helper that can be called from read errors, write errors, EOF, timeouts, and shutdown:

~~~java
// Logic skeleton snippet; other state cleanup is implemented by the application.
static void closeConnection(SelectionKey key) {
    if (key == null) return;
    key.cancel();
    try {
        key.channel().close();
    } catch (java.io.IOException e) {
        // Log appropriately; do not infinitely retry the close operation.
    }
}
~~~

Do not rely on `key.isValid()` turning false as a sign that **all resources have been closed**: a key can become invalid due to cancellation alone while the channel remains open. `isRegistered()` may also temporarily remain true until the selector processes cancelled keys.

### Multi-client flow

In a real event loop, when `OP_ACCEPT` fires there may be **multiple connections** waiting. With a non-blocking listener, the common pattern is:

~~~java
// Snippet inside the isAcceptable handler:
for (;;) {
    SocketChannel peer = server.accept();
    if (peer == null) break;
    peer.configureBlocking(false);
    peer.register(selector, SelectionKey.OP_READ, new ConnectionState());
}
~~~

This snippet requires the `ConnectionState` class from Section 9. Do not use a `while(true)` loop on `accept()` for a **blocking listener**, because once pending connections are exhausted it will block the entire event loop.

Limit the number of connections, total pending bytes, timeouts, and time spent per key; a connection sending data continuously must not monopolize the selector thread and starve other connections.

## 15. Exceptions, Configuration Errors, and Common Causes

| Symptom | Common Cause | Fix |
|---|---|---|
| `IllegalBlockingModeException` right at `register` | Channel is still blocking | Call `configureBlocking(false)` before `register` |
| `IllegalBlockingModeException` on `configureBlocking(true)` | Channel is still registered | Cancel and ensure deregistration completes before switching back to blocking |
| `IllegalArgumentException` when registering flags | `ops` contains bits not in `channel.validOps()` | Use `OP_ACCEPT` for listener; `OP_READ/WRITE/CONNECT` for socket |
| `CancelledKeyException` when accessing key | Key was cancelled/closed, or is in deregistration phase | Check lifecycle, handle races, stop using the key |
| `ClosedChannelException` on register | Channel is already closed | Only register open channels |
| `ClosedSelectorException` on register or select | Selector is already closed | Manage shutdown ordering clearly |
| `IllegalSelectorException` | Channel and selector have incompatible `SelectorProvider` | Use an appropriate provider; avoid mixing incompatible providers |
| `NotYetBoundException` from `accept` | `ServerSocketChannel` is not bound yet | Bind local endpoint first |
| `accept() == null` | Non-blocking listener, no connection ready right now | Return to event loop; do not treat as an error |
| `SocketChannel.read() == 0` | Temporarily no bytes available or buffer has no remaining space | Inspect `ByteBuffer` state and wait for next readiness |
| `SocketChannel.read() == -1` | Read-side EOF reached | Handle any incomplete frame, clean up appropriately |
| `write()` sends fewer than length | Partial write, bounded send buffer | Keep remaining outbound data, register `OP_WRITE` when needed |
| Selector loop uses high CPU | `OP_WRITE` always enabled, selected keys not removed, or loop polls continuously | Turn off `OP_WRITE` when nothing is pending, remove keys, avoid busy polling |
| Called `cancel()` but `isRegistered()` is still true | Deregistration is deferred | Wait for selector to process cancellation; do not assume immediate completion |
| Server accepts connections but `peer.register` fails | Accepted channel still defaults to blocking | Call `peer.configureBlocking(false)` on every accepted channel |
| Interest changed but select thread does not wake up | Modified from another thread without synchronizing with selector loop | Use a task queue and `selector.wakeup()` appropriately |

Do not handle every exception with an unconditional `continue`: a persistently failing key can make the event loop spin and leak resources. Classify **per-connection** errors, **listener** errors, **selector** errors, and **shutdown** policies.

## 16. Things You Can Inspect via Logs and Testing

Diagnostic details worth logging **without sensitive data**:

- Channel type, `isOpen()`, `isBlocking()`, `isRegistered()`.
- Whether the selector is open or closed; `key.isValid()`; `interestOps()` and `readyOps()` bitmasks.
- How many keys each `select` round selected; whether selected keys are accidentally not being removed.
- How many bytes `SocketChannel.read` and `write` returned; buffer `position/limit/remaining` before and after.
- Number of live accepted connections, pending outbound bytes, total buffer memory.
- Frequency of `OP_WRITE`, EOFs, business timeouts, cancels/closes, and connections rejected due to quotas.

Example of printing ops:

~~~java
// Snippet; run only while the key is valid:
System.out.println("interest=" + key.interestOps());
System.out.println("ready=" + key.readyOps());
System.out.println("readable=" + key.isReadable());
~~~

Bitmasks are typically printed as integers: `OP_READ=1`, `OP_WRITE=4`, `OP_CONNECT=8`, `OP_ACCEPT=16`. For readable logs, inspect each bit individually instead of treating the integer as a "single event code": a set can contain **multiple bits** at the same time.

## 17. Structuring the Event Loop Properly

A selector **does not make I/O automatically parallel**. A selector thread should typically:

1. Process pending tasks from the queue (e.g., interest changes requested by workers).
2. Call `select` with an appropriate timeout/deadline.
3. Iterate over and remove selected keys.
4. For `OP_ACCEPT`, accept a bounded number of connections according to a fairness policy.
5. For `OP_CONNECT`, call `finishConnect()` and update interest.
6. For `OP_READ`, read up to a reasonable limit; accumulate/parse messages.
7. For `OP_WRITE`, flush bounded outbound data, disable writable interest if empty.
8. Close/cancel errored or EOF keys, release session state.
9. Repeat, combining timeouts and shutdown signals.

If business logic takes a long time (database, image processing, calling other services), do not run long tasks directly on the selector thread: offload them to an appropriate worker and post results back via **task queue + wakeup**; manage data races, response ordering, and backpressure.

A well-behaved NIO app recognizes that **readiness ≠ I/O completion**, **register ≠ automatic task execution**, **interest set ≠ ready set**, **cancel ≠ close**, and **non-blocking ≠ never needing deadline waits**.

## 18. Self-Check Questions

**1. Is `SocketChannel.open()` blocking or non-blocking by default?** **Blocking** by default; `configureBlocking(false)` is required before registering with a selector.

**2. A non-blocking `ServerSocketChannel` calls `accept()` and returns a `SocketChannel`. Is the accepted channel automatically non-blocking?** No. Per Java 17, it **starts in blocking mode**; it must be configured separately.

**3. Does `register(selector, OP_READ)` mean Java will read immediately?** No. It only adds **interest**; the event loop must `select` and then call `read`.

**4. What problem can keeping `OP_WRITE` permanently in interest cause?** It causes a **busy loop** because many sockets are writable most of the time, even when there is no data to send.

**5. Does `key.isReadable()` check the interest set or the ready set?** The **ready set**, which is the readiness result observed by the selector.

**6. Is `selector.selectedKeys()` cleared automatically when the loop finishes?** No. The application must remove processed keys; removing is not cancelling.

**7. Does `key.cancel()` immediately make `channel.isRegistered() == false` and close the socket?** Not necessarily. Deregistration may be deferred; `cancel` does not automatically close the channel.

**8. Is `selector.select(0)` equivalent to `selectNow()`?** No. `select(0)` is defined to **wait with no timeout**, whereas `selectNow()` is non-blocking.

**9. Does registering the same channel twice with the same selector create two SelectionKeys?** No. As long as the key is still valid, the API returns **the same key** and may update its interest/attachment.

**10. Is registering `OP_ACCEPT | OP_READ` for a `ServerSocketChannel` valid?** No, because a listener only supports `OP_ACCEPT`.

**11. Does `SocketChannel.read(ByteBuffer) == 0` prove that TCP has closed?** No. Read-side EOF is **`-1`**; 0 can mean no data is ready yet or the buffer has no remaining space.

**12. How do you accept a new connection and register it for reading?** `SocketChannel peer = server.accept();`, check non-`null`, call `peer.configureBlocking(false)`, then `peer.register(selector, OP_READ, state)`.

**13. Does `isWritable()` mean the client has received the sent bytes?** No. It only indicates local writability on the channel.

**14. What must another thread do when adding outbound data while the selector is waiting?** Synchronize via a task/queue and use `selector.wakeup()` by design to update interests and process outbound data at the right time.

## Official Documentation

- [Java SE 17 – SelectableChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html): `configureBlocking`, `register`, `validOps`, `keyFor`, blocking rules.
- [Java SE 17 – SelectionKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): `interestOps`, `readyOps`, `OP_ACCEPT/CONNECT/READ/WRITE`, attachment, and cancel.
- [Java SE 17 – Selector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): `select`, `selectedKeys`, cancelled-key set, and `wakeup`.
- [Java SE 17 – ServerSocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): `bind`, `accept`, non-blocking accept, and default mode of accepted channels.
- [Java SE 17 – SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): `connect`/`finishConnect`, partial read/write, EOF.
- [Java SE 17 – ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `flip`, `compact`, `hasRemaining`, and managing partial bytes.

**Key takeaway:** To use a Selector, call **`channel.configureBlocking(false)` before `channel.register(selector, ops [, attachment])`**. `SelectionKey` distinguishes **interest** (what to monitor) from **ready** (what is currently detected as ready). The loop must manually iterate/remove selected keys, handle non-blocking read/write/accept/connect, toggle interest at the right time, preserve unread/unwritten data, and clean up resources.
