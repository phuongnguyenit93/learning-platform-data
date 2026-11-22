# Selector: OP_ACCEPT, OP_CONNECT, OP_READ, and OP_WRITE in Java NIO

## 1. What Do the Four Flags Represent?

In Java NIO, `java.nio.channels.Selector` allows a single thread to monitor the **I/O readiness** state of multiple `SelectableChannel` instances. Instead of repeatedly calling `read()` or `write()` on each connection and guessing which one can make progress, the program registers events of interest via `SelectionKey`.

The four constants defined in `java.nio.channels.SelectionKey`:

| Operation | Bit Value | Typical Channel | Meaning |
| --- | ---: | --- | --- |
| `OP_ACCEPT` | 16 | `ServerSocketChannel` | An incoming connection is ready for `accept()` |
| `OP_CONNECT` | 8 | `SocketChannel` | An asynchronous TCP connection is ready to be checked/completed via `finishConnect()` |
| `OP_READ` | 1 | `SocketChannel`, `DatagramChannel`, `Pipe.SourceChannel` | Reading can make progress or EOF/error has been detected |
| `OP_WRITE` | 4 | `SocketChannel`, `DatagramChannel`, `Pipe.SinkChannel` | Writing can make progress, typically because space exists in the output buffer |

The constants are **bit flags**, so they can be combined with the bitwise OR operator `|`:

~~~java
int interests = SelectionKey.OP_READ | SelectionKey.OP_WRITE;
~~~

The expression above requests monitoring **both reading and writing**; it performs no I/O itself. An `OP_ACCEPT` operation does not mean a client has already been returned; you still must call `ServerSocketChannel.accept()`. `OP_CONNECT` does not mean every connection step is finished; you still need `SocketChannel.finishConnect()` if the prior `connect()` was pending.

**Core rule:** Selector reports **readiness** (ability to make progress), not that the application has already read, written, accepted, or completed the connection for you.

## 2. Three Operation Sets: validOps, interestOps, and readyOps

A `SelectionKey` connects **one channel** to **one selector**. To understand why a flag is or is not reported, separate three concepts:

1. `channel.validOps()`: the set of flags **the channel supports by type**. For example, `ServerSocketChannel` supports `OP_ACCEPT`; `SocketChannel` supports `OP_CONNECT`, `OP_READ`, and `OP_WRITE`.
2. `key.interestOps()`: the set of flags **the application currently wants the selector to monitor**. Modifiable via `key.interestOps(mask)` while the key is valid.
3. `key.readyOps()`: the set of flags that the selector **determined are ready** on the selected key during a selection pass. Checkable via `isAcceptable()`, `isConnectable()`, `isReadable()`, and `isWritable()`.

~~~text
channel.validOps()
    │ operations supported by the channel type
    ▼
key.interestOps()
    │ application selects bits to monitor
    ▼
selector.select()
    │ detects actual readiness
    ▼
key.readyOps() / key.isReadable() / ...
    │
    ▼
Application calls accept / finishConnect / read / write itself
~~~

Having `OP_READ` in `interestOps` does not make `isReadable()` return `true` immediately. It only registers monitoring intent. Conversely, `readyOps` should not be inferred as an immutable I/O state: network state can change right after the selector marks it ready.

### validOps Must Match the Channel

| Channel Type | Type-level validOps |
| --- | --- |
| `ServerSocketChannel` | `OP_ACCEPT` |
| `SocketChannel` | `OP_CONNECT \| OP_READ \| OP_WRITE` |
| `DatagramChannel` | `OP_READ \| OP_WRITE` |
| `Pipe.SourceChannel` | `OP_READ` |
| `Pipe.SinkChannel` | `OP_WRITE` |

Do not register `OP_ACCEPT` on a `SocketChannel`, nor `OP_CONNECT` on a `ServerSocketChannel`. If `interestOps` contains a bit not in `validOps()`, `register(selector, ops)` or `interestOps(ops)` can throw `IllegalArgumentException`.

You can check:

~~~java
boolean canAccept =
        (serverChannel.validOps() & SelectionKey.OP_ACCEPT) != 0;
~~~

This is an illustrative code fragment assuming an open `serverChannel` variable and `SelectionKey` imported, not a standalone program.

## 3. Preconditions Before Registering with a Selector

A `SelectableChannel` must be placed in **non-blocking mode** before registering with a selector. Foundational procedure:

~~~java
Selector selector = Selector.open();
ServerSocketChannel server = ServerSocketChannel.open();
server.configureBlocking(false);
server.bind(new InetSocketAddress("127.0.0.1", 0));
SelectionKey serverKey =
        server.register(selector, SelectionKey.OP_ACCEPT);
~~~

This is an illustrative snippet inside a method handling `IOException` and closing resources with `try-with-resources`; required imports are in `java.nio.channels` and `java.net`. Port `0` asks the operating system to choose an available ephemeral port.

`register(selector, ops)` returns a `SelectionKey`; `key.channel()` is the registered channel and `key.selector()` is the corresponding selector. A channel has only **one key per selector**, though it can register with multiple selectors if API conditions are met. If already registered on that selector, re-registering updates the interest set and attachment of the existing key.

Distinguish between:

- **Blocking mode:** I/O calls may block waiting for data/completion. You cannot register a blocking channel with a selector; attempting to do so throws `IllegalBlockingModeException`.
- **Non-blocking mode:** `accept()` may return `null`, and `read()` or `write()` may return `0`; the program should react through readiness rather than busy-waiting indefinitely.
- **Selector:** does not perform I/O on behalf of the application, but provides the set of selected keys for the application to dispatch.

A program can still use non-blocking channels without a selector; a selector is valuable when managing multiple channels and avoiding polling each connection continuously.

## 4. OP_ACCEPT: Accepting New Connections

`OP_ACCEPT` applies to an open `ServerSocketChannel` bound to a listening address. When the key has `isAcceptable() == true`, call `accept()`:

~~~java
if (key.isAcceptable()) {
    ServerSocketChannel server =
            (ServerSocketChannel) key.channel();

    SocketChannel client = server.accept();
    if (client != null) {
        client.configureBlocking(false);
        client.register(selector, SelectionKey.OP_READ);
    }
}
~~~

This snippet sits **inside the selected-key processing loop**, assuming `selector` and `key` are valid.

Explanation:

1. `server` accepts connections; by itself it only supports `OP_ACCEPT`.
2. `accept()` returns a **new** `SocketChannel` for the newly accepted connection, distinct from the listening `ServerSocketChannel`.
3. With a non-blocking channel, even after a readiness notification, `accept()` can still return `null` if no connection is available to accept at the moment of the call.
4. The newly accepted `SocketChannel` must be configured non-blocking **before registering**.
5. If the server may receive many connections in succession, you can handle multiple `accept()` calls in one turn with a reasonable bound so as not to starve other keys.

After accepting, data for the new connection is read via `SocketChannel` and `OP_READ`; do not read directly from `ServerSocketChannel` using `OP_READ`.

## 5. OP_CONNECT: Completing a Non-Blocking TCP Connection

`OP_CONNECT` applies to a **`SocketChannel` performing an incomplete connection**. Client-side procedure:

~~~java
SocketChannel client = SocketChannel.open();
client.configureBlocking(false);

boolean connected = client.connect(remoteAddress);
if (connected) {
    client.register(selector, SelectionKey.OP_READ);
} else {
    client.register(selector, SelectionKey.OP_CONNECT);
}
~~~

This is an illustrative snippet; `remoteAddress` is the target address and `selector` is an open `Selector`.

Key point: `connect(...)` **can return `true` immediately** if the connection completes right away. In that case, **there is no need to wait for `OP_CONNECT`**, and you can register `OP_READ`/`OP_WRITE` directly as needed.

If `connect(...)` returns `false`, the connection is still pending. When the selector reports `isConnectable()`:

~~~java
if (key.isConnectable()) {
    SocketChannel client = (SocketChannel) key.channel();
    if (client.finishConnect()) {
        key.interestOps(SelectionKey.OP_READ);
    }
}
~~~

`finishConnect()` can complete the connection and return `true`, or return `false` if still pending in non-blocking mode. It can also throw `IOException` if the connection fails (e.g., target refused). Do not treat `OP_CONNECT` as a guarantee that the connection succeeded.

Once connected, **replace `OP_CONNECT` with the flags for the next protocol state**. Usually that is `OP_READ` when expecting incoming data, or `OP_WRITE` when there is a payload to send. Leaving `OP_CONNECT` in the interest set after connecting can lead to improper event handling.

## 6. OP_READ: Read Readiness Does Not Mean a Full Message Is Available

`OP_READ` typically appears when a socket has data, the peer closes one direction of the connection, or an I/O condition requires application handling.

~~~java
if (key.isReadable()) {
    SocketChannel channel = (SocketChannel) key.channel();
    ByteBuffer dst = ByteBuffer.allocate(4096);
    int n = channel.read(dst);

    if (n > 0) {
        dst.flip();
        // Consume exactly the n bytes just received.
    } else if (n == -1) {
        // Peer sent EOF on this read direction.
        key.cancel();
        channel.close();
    } else {
        // n == 0: no progress yet; retry on an appropriate turn.
    }
}
~~~

This is illustrative code; real applications generally need a mechanism to retain buffers across reads.

Distinguish:

- `n > 0`: exactly `n` new bytes were placed into the buffer; buffer `position` increased, so call `flip()` before consuming.
- `n == 0`: the call transferred no bytes; do not assume the connection is closed.
- `n == -1`: EOF on the read channel. Decide whether to close the whole connection or support half-close according to protocol.
- **A single `read` does not guarantee a complete HTTP request, JSON message, or application record.** TCP is a byte stream and preserves no message boundaries.

For protocols with headers and payloads, you commonly store a `ByteBuffer` in the `SelectionKey` attachment or a connection state object. Parse complete records, then call `compact()` to preserve remaining incomplete bytes and continue receiving on the next turn. Avoid allocating a new buffer and discarding unparsed data on every `OP_READ`.

Readiness only signals an opportunity to make progress; because data might be consumed elsewhere or state might change, the `read` call still needs to handle its actual return value.

## 7. OP_WRITE: Only Monitor When You Actually Have Data to Send

`OP_WRITE` signals that the channel is **capable of writing**. On ordinary TCP sockets, this condition is frequently true because the OS send buffer has space. If you keep `OP_WRITE` registered even when nothing needs to be sent, the selector can continuously report writable, wasting CPU cycles in the loop.

**Standard policy:**

1. Monitor `OP_READ` by default for an established connection.
2. When there is data to send, place it into a queue/buffer and add `OP_WRITE` to `interestOps`.
3. When the selector reports writable, call `write` and inspect the actual number of bytes written.
4. If unsent payload remains, keep `OP_WRITE` to continue on the next turn.
5. Once the queue is empty, **remove the `OP_WRITE` bit** from the interest set.

Illustrative code snippet:

~~~java
if (key.isWritable()) {
    SocketChannel channel = (SocketChannel) key.channel();
    ByteBuffer pending = (ByteBuffer) key.attachment();

    if (pending != null) {
        channel.write(pending);
        if (!pending.hasRemaining()) {
            key.attach(null);
            key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
        }
    }
}
~~~

This snippet assumes the attachment holds only a single outbound buffer; in real programs, the attachment is usually an object holding an inbound buffer, outbound queue, and protocol state.

`write(ByteBuffer)` **does not guarantee consuming the entire payload** in one call. If it returns `0` or `pending.hasRemaining()` is still true, do not discard the buffer. Only clear `OP_WRITE` when the data has been fully written to the channel (or the protocol explicitly aborts sending).

To add the write bit while keeping the read bit:

~~~java
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
~~~

To remove the write bit:

~~~java
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
~~~

The `|` operator adds a bit, and `& ~` selectively clears a bit. Do not call `key.interestOps(OP_WRITE)` if you still need to monitor `OP_READ`: that setter replaces the entire interest set.

## 8. The selectedKeys Processing Cycle

A minimal Selector loop takes the form:

~~~java
while (running) {
    selector.select();

    Iterator<SelectionKey> it = selector.selectedKeys().iterator();
    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove();

        if (!key.isValid()) {
            continue;
        }

        if (key.isAcceptable()) {
            // accept() and register the accepted socket.
        }
        if (key.isConnectable()) {
            // finishConnect(), change interest set when connected.
        }
        if (key.isReadable()) {
            // read(), handle n > 0, n == 0, n == -1.
        }
        if (key.isWritable()) {
            // write(), continue partial data, clear OP_WRITE when drained.
        }
    }
}
~~~

This is an **illustrative skeleton**, without declarations for `running`, `selector`, exception handling, or channel closing. Production systems require proper stop conditions and resource management.

Key points:

- `selector.select()` can block until a key is ready, `wakeup()` is called, the thread is interrupted, or another API condition occurs. `select(timeout)` limits wait duration; you must handle returning 0.
- `selectedKeys()` is the selected-key set and **is not automatically cleared** merely by iterating over it. Call `it.remove()` after retrieving the key.
- `key.isValid()` checks whether the key is still valid. Once canceled via `cancel()` or channel close, the key is no longer usable for readiness checks.
- `isReadable()` and `isWritable()` can both be true on **the same `SocketChannel` key**, so code can handle multiple conditions in one turn; if one branch closes/cancels the channel, subsequent branches must avoid using an invalid key.
- In production code, dispatch by **channel type/connection state** and check validity after any action that could close the channel.
- `interestOps` is what is monitored, whereas `readyOps` is the selection result; updating the interest set does not turn an old ready bit into an I/O event that just occurred.

Some systems use one Selector thread while worker threads produce outbound data. When another thread modifies state, `selector.wakeup()` may be needed so the thread waiting in `select()` sees the change promptly. Even so, `wakeup()` does not replace queue synchronization or shared-state safety across threads.

## 9. Standalone Java 17+ Example: TCP Loopback Using All Four Flags

The example below creates a server and client in the same process over loopback and an OS-assigned ephemeral port. The program uses Selector for:

- `OP_ACCEPT`: server accepts the new socket;
- `OP_CONNECT`: client monitors connection completion **if connect is still pending**;
- `OP_WRITE`: client sends the ASCII string `PING`, then removes write interest;
- `OP_READ`: server-side socket reads all four bytes.

The example prints only the final result so stdout does not depend on key ordering returned by the selector. `OP_CONNECT` might not fire on a given run if `connect()` finishes immediately; the code handles both possibilities cleanly.

Save as `SelectorOperationsDemo.java`:

~~~java
import java.io.EOFException;
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
import java.util.concurrent.TimeUnit;

public class SelectorOperationsDemo {
    public static void main(String[] args) throws IOException {
        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open();
             SocketChannel client = SocketChannel.open()) {

            server.configureBlocking(false);
            server.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            server.register(selector, SelectionKey.OP_ACCEPT);

            client.configureBlocking(false);
            boolean connectedNow = client.connect(server.getLocalAddress());
            client.register(selector, connectedNow
                    ? SelectionKey.OP_WRITE
                    : SelectionKey.OP_CONNECT);

            ByteBuffer outbound = ByteBuffer.wrap(
                    "PING".getBytes(StandardCharsets.US_ASCII));
            ByteBuffer inbound = ByteBuffer.allocate(4);
            SocketChannel accepted = null;
            boolean acceptedConnection = false;

            try {
                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(10);

                while (inbound.hasRemaining()
                        && System.nanoTime() < deadline) {

                    selector.select(250);
                    Iterator<SelectionKey> it =
                            selector.selectedKeys().iterator();

                    while (it.hasNext()) {
                        SelectionKey key = it.next();
                        it.remove();

                        if (!key.isValid()) {
                            continue;
                        }

                        if (key.isAcceptable()) {
                            ServerSocketChannel listener =
                                    (ServerSocketChannel) key.channel();
                            SocketChannel peer = listener.accept();

                            if (peer != null) {
                                peer.configureBlocking(false);
                                peer.register(selector, SelectionKey.OP_READ);
                                accepted = peer;
                                acceptedConnection = true;
                                key.interestOps(0);
                            }
                        } else if (key.isConnectable()) {
                            SocketChannel connecting =
                                    (SocketChannel) key.channel();
                            if (connecting.finishConnect()) {
                                key.interestOps(SelectionKey.OP_WRITE);
                            }
                        } else if (key.isWritable()) {
                            SocketChannel sender =
                                    (SocketChannel) key.channel();
                            sender.write(outbound);

                            if (!outbound.hasRemaining()) {
                                key.interestOps(0);
                            }
                        } else if (key.isReadable()) {
                            SocketChannel receiver =
                                    (SocketChannel) key.channel();
                            int n = receiver.read(inbound);

                            if (n == -1) {
                                throw new EOFException(
                                        "Connection ended before PING");
                            }
                        }
                    }
                }

                if (inbound.hasRemaining()) {
                    throw new IOException("Timed out waiting for PING");
                }

                inbound.flip();
                System.out.println("accepted=" + acceptedConnection);
                System.out.println("connected=" + client.isConnected());
                System.out.println("message="
                        + StandardCharsets.US_ASCII.decode(inbound));
            } finally {
                if (accepted != null) {
                    accepted.close();
                }
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac SelectorOperationsDemo.java
java SelectorOperationsDemo
~~~

Expected stdout when the environment allows TCP loopback and connect/read/write complete normally:

~~~text
accepted=true
connected=true
message=PING
~~~

Stage-by-stage walkthrough:

1. `server` opens in non-blocking mode, binds to loopback, and registers `OP_ACCEPT`.
2. `client.connect(...)` may return `true` or `false`. If `true`, the client connected immediately and registers `OP_WRITE` right away; if `false`, the client registers `OP_CONNECT`, and `finishConnect()` later transitions to `OP_WRITE`.
3. Selector reports `OP_ACCEPT` when the server has a connection ready. `accept()` returns the `peer` socket (which could be `null` at a given instant); the code registers it for `OP_READ`.
4. When the client is writable, `OP_WRITE` causes the code to progressively send the `PING` buffer. If unsent bytes remain, `OP_WRITE` stays enabled; when fully sent, `interestOps(0)` prevents continuous writable loops.
5. `OP_READ` on the server-side socket reads into `inbound`. If only part arrived, the buffer still has `remaining()` and the loop continues waiting.
6. Once all four bytes arrive, the loop finishes and prints `PING`. The two booleans describe the final connection state regardless of whether `OP_CONNECT` fired.
7. `selectedKeys` has each key removed via `Iterator.remove()`; the sockets, server, and Selector are closed on completion.

**Example scope:** requires an environment permitting loopback sockets. The 10-second timeout ensures clear failure if blocked or too slow; in that case, the program throws `IOException` instead of printing all three lines. This is a learning sample and does not implement production features like multi-message queues, general backpressure, per-connection timeout management, or resource limits.

## 10. How Should `interestOps` Transition During Use?

A typical TCP connection lifecycle looks like:

~~~text
Server side: ServerSocketChannel
    OP_ACCEPT
       |
       | accept() succeeds
       v
Accepted SocketChannel
    OP_READ  <-------------+
       |                   |
       | data to send      |
       v                   |
  OP_READ | OP_WRITE       |
       |                   |
       | all sent          |
       +-------------------+

Client side: SocketChannel
    connect(...)
       |
       +-- returns true ----------> OP_READ / OP_WRITE
       |
       +-- returns false -> OP_CONNECT
                           |
                           | finishConnect() succeeds
                           v
                      OP_READ / OP_WRITE
~~~

The diagram shows the **interest set** state managed by the program. This is not an automatic state machine inside `Selector`; application logic is responsible for state transitions.

Decision table:

| Scenario | Appropriate Interest Set |
| --- | --- |
| Server waiting for new connections | `OP_ACCEPT` |
| Non-blocking client with pending connect | `OP_CONNECT` |
| Connected, awaiting incoming request/response | `OP_READ` |
| Connected, outbound data queued | `OP_READ \| OP_WRITE` (or OP_WRITE when intentionally pausing reads) |
| Payload fully sent | Remove `OP_WRITE`; typically keep `OP_READ` |
| Connection closing or no longer monitored | `cancel()` key then close channel if lifecycle ended |

Never permanently register `OP_READ | OP_WRITE` on all sockets when there is zero outbound data. Because writability is usually ready, the program can spin handling spurious write events, significantly increasing CPU usage.

## 11. Common Pitfalls

### Confusing an Operation Flag with a Completed Action

`isAcceptable()` does not create a client by itself; `isConnectable()` does not finish a connection by itself; `isReadable()` does not pour bytes into a buffer; `isWritable()` does not transmit a payload. **You must call the corresponding I/O API** and check its result.

### Registering an Invalid Operation

`ServerSocketChannel` does not support `OP_READ` or `OP_CONNECT`. `SocketChannel` does not support `OP_ACCEPT`. Use `validOps()` to tell them apart and avoid `IllegalArgumentException`.

### Forgetting `configureBlocking(false)`

Registering a blocking channel with a Selector throws `IllegalBlockingModeException`. Configure non-blocking mode before calling `register`.

### Skipping the Immediate-Connect Branch

`SocketChannel.connect(address)` can return `true`. If your program always waits for `OP_CONNECT` afterward, it may fail to progress properly. When it returns true, transition immediately to the interest set needed for an established connection.

### Not Calling `finishConnect`

For a pending non-blocking connect, you must call `finishConnect()` to complete it or receive failure notification. Skipping this step and reading/writing right away can cause `NotYetConnectedException`.

### Keeping `OP_WRITE` Registered Continuously

This is a classic performance bug. Because sockets are normally writable, the selector can repeatedly wake the thread. Add `OP_WRITE` only when there is data to send, and remove it immediately once all data is sent.

### Failing to Handle Partial I/O

An `OP_READ` event might read only a few bytes of a message; an `OP_WRITE` might send only part of a buffer. Because TCP has no built-in message boundaries, you must retain state across turns and implement framing.

### Not Removing Keys from `selectedKeys`

If you iterate `selector.selectedKeys()` without `iterator.remove()`, the key stays in the selected set and can cause unwanted duplicate processing. Managing the selected set is the event loop's responsibility.

### Ignoring Invalid Keys and State Changes Inside the Loop

After one branch closes a channel or calls `cancel()`, subsequent readiness checks can throw `CancelledKeyException`. Check `isValid()` and avoid reusing canceled keys.

### Touching the Same Selector from Multiple Threads Without Coordination

If another thread enqueues data or updates the interest set, design thread safety for queues/state and consider `selector.wakeup()` so the select loop notices new work promptly. `wakeup()` does not synchronize variables automatically and does not generate network messages.

## 12. Self-Check Questions

1. Which flag must `ServerSocketChannel` monitor to accept connections? **`OP_ACCEPT`**. New connections are retrieved via **`accept()`**.
2. Client calls `connect(...)` and gets `false`. Which event should it watch? **`OP_CONNECT`**, then call `finishConnect()`.
3. Client calls `connect(...)` and gets `true`. Must it wait for `OP_CONNECT`? **No**; the connection completed immediately, so monitor read/write as needed.
4. After `OP_READ`, does `read(buffer)` returning `0` mean EOF? **No**. EOF is **`-1`**; 0 means no bytes were read in that call.
5. Why shouldn't `OP_WRITE` remain registered all the time? Because sockets are very often writable, easily causing a CPU-burning loop when there is no payload.
6. Does `key.interestOps(OP_WRITE)` preserve an already-registered `OP_READ`? **No**; the setter replaces the entire mask. Use `key.interestOps(key.interestOps() | OP_WRITE)` to add while keeping existing bits.
7. How do `validOps` and `readyOps` differ? **`validOps`** are operations the channel type can support; **`readyOps`** are operations reported ready by the selector in a selection pass.
8. Why is `it.remove()` needed when iterating `selectedKeys()`? Because the selected-key set is not cleared automatically after the application handles it.
9. Does `OP_CONNECT` apply to a server-side socket just obtained from `accept()`? Usually **not needed**; a socket returned by `accept()` is already connected and is typically registered for `OP_READ`.
10. In an event loop, you receive `OP_WRITE` and `channel.write(buffer)` writes only partially. How do you handle it? **Keep the buffer with remaining bytes, keep `OP_WRITE`, and retry when readiness fires again**.

**Remember:** `OP_ACCEPT` signals a chance to accept a connection, `OP_CONNECT` signals a chance to finish a pending connection, `OP_READ` signals a chance to read or detect EOF, and `OP_WRITE` signals a chance to write. They are **bits of interest/ready state**, not I/O actions themselves. An effective NIO pattern registers valid `validOps`, acts on `readyOps` based on actual channel call outcomes, preserves incomplete data, and **keeps `OP_WRITE` enabled only while outbound data is pending**.
