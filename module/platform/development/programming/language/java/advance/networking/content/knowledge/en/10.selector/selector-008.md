# Register OP_WRITE Only When Outbound Data Is Pending to Avoid a CPU-Burning Loop (Java NIO Selector)

**Core rule:** with a `SocketChannel` in **non-blocking** mode, only enable `SelectionKey.OP_WRITE` when the application actually has **unwritten bytes** on that connection; once the outbound queue is empty, **remove OP_WRITE from the interest set immediately**. If `OP_WRITE` is kept enabled permanently, `Selector.select()` can wake up continuously because a socket is almost always *writable* whenever the send buffer has space, even though the application **has no data to write**. The event loop then burns CPU processing useless events.

This is a classic performance bug in the **Selector** topic of **Java Advance - networking**. This lesson covers the nature of write-readiness, how to toggle interest bits properly using bitmasks without losing `OP_READ`, handling partial writes and queues, coordinating from other threads, backpressure, testing, and two standalone compilable/runnable Java 17+ programs.

## 1. Why is OP_WRITE different from “new data needs to be sent”?

`SelectionKey.OP_WRITE` indicates that the channel **is capable of writing more bytes to the OS send layer without blocking for long**. It is neither a “the application just produced a response” event nor a “the peer has received the data” signal.

When the TCP send buffer has available capacity, the channel can remain writable across many `select` rounds. For most healthy connections, this is a **very common** state, especially when nothing is being sent. Conversely, `OP_READ` is usually only notable when there are incoming bytes/EOF/I/O events to process. Therefore, writing an event loop that permanently registers `OP_READ | OP_WRITE` causes write events to fire even when the send queue is empty.

```text
No outbound data, but the key still has OP_WRITE registered:

selector.select()  -> writable -> pendingQueue.isEmpty() -> nothing sent
selector.select()  -> writable -> pendingQueue.isEmpty() -> nothing sent
selector.select()  -> writable -> pendingQueue.isEmpty() -> nothing sent
... loops at high speed despite zero application work ...

When OP_WRITE is disabled while idle:
selector.select()  -> wait for OP_READ / OP_ACCEPT / timer / wakeup
                                    |
                               New response
                                    v
                     enqueue(response) + enable OP_WRITE
                                    |
                         writable -> write in chunks
                                    |
                         no pending left -> disable OP_WRITE
                                    |
                              continue waiting
```

**Readiness ≠ message completion, and ≠ acknowledgement.** A writable channel may write `0` bytes due to a race/state change, may write only part of the buffer, or may throw an `IOException`. A successful write to TCP also does not confirm that the peer has decoded or processed the response.

## 2. Interest set, ready set, and selected-key set are three different things

A `SelectionKey` represents the registration between a selectable channel and a `Selector`. Three concepts are commonly confused:

| Component | API | Role |
| --- | --- | --- |
| **Interest set** | `key.interestOps()` | The I/O operations the application **wants to be notified about** in subsequent selection rounds |
| **Ready set** | `key.readyOps()`, `key.isWritable()`, `key.isReadable()` | Operations marked by the selector as ready to make progress from the selection result |
| **Selected-key set** | `selector.selectedKeys()` | The set of keys the application must iterate over and **remove from the set after handling** |

An event loop knows there are bytes to send **from the data in the outbound queue**, not from `key.isWritable()`. When the queue has data, it registers `OP_WRITE` interest and waits for readiness. When the queue is drained, it removes the interest. **Do not use `readyOps()` as storage for business state**: it is a readiness result, not “a response is waiting to be sent.”

Java NIO `Selector` primarily models **readiness**, not a completion API like “the OS will finish sending the message and invoke a callback.” When `select` returns a writable key, the code still has to call `channel.write(ByteBuffer)` and check `remaining()`.

Another essential point: when iterating over `selector.selectedKeys()`, use an iterator and `iterator.remove()`. If a key is left in the selected set, subsequent `select` calls may not add that key as you expect, making the observed behavior confusing. Removing a selected key does **not** cancel the registration and does not clear `OP_WRITE` interest: the two operations are completely separate.

## 3. Common mistake: always enabling OP_WRITE upon accept

This is an **incorrect illustrative snippet**, not a standalone runnable program:

```java
SocketChannel client = server.accept();
client.configureBlocking(false);

// WRONG: interested in writing even before there is any data to send.
client.register(selector,
        SelectionKey.OP_READ | SelectionKey.OP_WRITE);

// In the event loop:
if (key.isWritable()) {
    if (outboundQueue.isEmpty()) {
        // No data; the next select round will still typically wake up.
        return;
    }
    // ...
}
```

The mistake is not `if (outboundQueue.isEmpty())` — that defensive check is necessary. The mistake is that **`OP_WRITE` interest remains enabled** after determining there are no pending bytes. If the loop keeps calling `selector.select()` and continuously receiving writable events while idle, CPU usage can spike sharply, `select`/sec counts soar, and latency for other sockets increases because the event loop is busy handling idle keys.

Another version that is also wrong:

```java
// Wrong: no outbound data, yet OP_WRITE remains registered.
if (key.isWritable()) {
    ByteBuffer buffer = outboundQueue.peek();
    if (buffer != null) {
        channel.write(buffer);
    }
    // Fails to update interestOps when the queue is empty!
}
```

Even when there are initially a few bytes to send, forgetting to clear `OP_WRITE` after the `ByteBuffer` has been completely written causes the CPU loop to persist **after all responses have finished sending**. This is often a bug that only appears after the first request, making it easy to overlook.

## 4. Rules for toggling interest with bitmask operations

Assume `SelectionKey key` is valid and registration updates are performed on the **owner event-loop thread**. The standard operations are:

```java
// Initially read-only, no outbound bytes yet.
key.interestOps(SelectionKey.OP_READ);

// When enqueuing new bytes (and the queue was previously empty):
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);

// When the entire queue has been written:
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);

// Check current interest, do not confuse with readyOps:
boolean wantsWrite =
        (key.interestOps() & SelectionKey.OP_WRITE) != 0;
```

This is an **illustrative snippet** without a full class or `key` variable, so it does not run standalone. Keep in mind:

- Use **`| OP_WRITE`** to turn on one bit while preserving other valid bits such as `OP_READ` and `OP_CONNECT`.
- Use **`& ~OP_WRITE`** to turn off only the write bit without clearing other interests.
- **Do not carelessly call `key.interestOps(SelectionKey.OP_WRITE)`** when you only want to *add* write: it replaces the entire interest set and can accidentally disable `OP_READ`.
- **Do not use `key.interestOps(0)` to stop writing** if you still want to keep reading; `0` means no readiness operations are of interest for that key.
- A key only accepts operations supported by its channel. For a connected `SocketChannel`, `OP_READ`/`OP_WRITE` are typically the two main interests; `ServerSocketChannel` uses `OP_ACCEPT`.
- `interestOps` can throw `CancelledKeyException` if the key has been cancelled. Lifecycle management, connection teardown, and worker completion must check key validity before re-enabling interest.

Changing the interest set affects **subsequent selection rounds**; it does not call `channel.write` or automatically “flush” a `ByteBuffer`. Real logic must handle both newly enqueued output **and** leftover unwritten bytes from previous attempts.

## 5. Outbound lifecycle: from idle to drain and back to idle

For **each connection**, you can model a `Deque<ByteBuffer>` queue of frames ready for transmission:

```text
IDLE
  outbound = []
  interest = OP_READ               (OP_WRITE OFF)
       |
       | app creates a completely framed response
       v
ENQUEUE
  outbound = [frame1, frame2, ...]
  interest |= OP_WRITE             (OP_WRITE ON)
       |
       | Selector reports writable
       v
WRITE
  write(head ByteBuffer)
  if head.hasRemaining(): keep position, wait for next event
  if head has no bytes left: remove head, try next frame
       |
       +---- outbound != [] -------> keep OP_WRITE ON
       |
       +---- outbound == [] -------> interest &= ~OP_WRITE
                                        |
                                        v
                                       IDLE
```

You can enable `OP_WRITE` on every enqueue, but to reduce unnecessary syscalls/interest updates, it is usually enabled only when the queue transitions from **empty → non-empty**. Regardless, if the queue still holds bytes after the last write, `OP_WRITE` **must remain enabled** so it has a chance to finish.

In multi-producer applications, updating the queue and interest set must have clear ownership/synchronization. A safe approach is to have **a single event-loop thread** perform all mutations to the socket's output queue, `key.interestOps`, and `channel.write`. Workers produce responses and send commands through a mailbox, and the event loop receives and enqueues the frames.

## 6. Why must ByteBuffer be preserved across write calls?

In non-blocking mode, `SocketChannel.write(ByteBuffer)` may:

- Write all remaining bytes, advancing `position` to `limit`.
- Write **partially**, advancing `position` accordingly.
- Return **0** because no more bytes can be written right now.
- Throw `IOException` on error or closed connection.

You cannot discard the unwritten portion of a buffer just because `write` returned normally:

```java
// Illustrative snippet; channel and queue already exist.
ByteBuffer current = outbound.peekFirst();

int n = channel.write(current);

if (current.hasRemaining()) {
    // Frame not finished; keep buffer with its position, keep OP_WRITE on.
    return;
}

outbound.removeFirst(); // Remove only when current has no bytes left.
if (outbound.isEmpty()) {
    key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
}
```

**Do not call `flip()` again** on a buffer after a partial `write`. `flip()` sets `limit` to the current `position` and will corrupt the unwritten boundary. `position` already tracks the next offset. Also do not wrap a fresh `ByteBuffer.wrap(allBytes)` from the start on every writable event — you would re-send bytes that were already transmitted.

If messages are length-prefixed, queue the **entire frame** (header + body) with clear ordering. Allowing multiple producers to write directly to the same `SocketChannel` will interleave parts of different frames. With a selector server, a single-writer-owner-per-connection model prevents that bug.

## 7. Write event handling pattern: bounded work per turn

**Illustrative pseudo-code**; the `Connection` class and `closeConnection` method belong to the application and are not standalone runnable code:

```java
void onWritable(SelectionKey key) throws IOException {
    SocketChannel channel = (SocketChannel) key.channel();
    Connection state = (Connection) key.attachment();

    int budget = 64 * 1024; // Example: max 64 KiB per turn.
    while (!state.outbound.isEmpty() && budget > 0) {
        ByteBuffer head = state.outbound.peekFirst();

        // Cap the number of bytes for this write call.
        int oldLimit = head.limit();
        head.limit(Math.min(oldLimit, head.position() + budget));
        int n;
        try {
            n = channel.write(head);
        } finally {
            head.limit(oldLimit);
        }
        budget -= n;

        if (head.hasRemaining()) {
            break; // Partial/zero write, or budget exhausted.
        }
        state.outbound.removeFirst();
    }

    if (state.outbound.isEmpty()) {
        key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
    }
}
```

The purpose of a **write budget** is to prevent one client with heavy output from monopolizing the event loop and increasing latency for other clients. The pattern above restores `limit` after writing because the `ByteBuffer` stays in the queue across turns. If `budget` runs out, `OP_WRITE` remains enabled because data is still pending; the event loop will resume on a subsequent turn.

**Design notes:** `SelectionKey` and `ByteBuffer` must be managed by the owner event loop; do not let workers concurrently mutate `position/limit`. When `write` returns `0`, exit the key's write loop and return to `select` rather than spinning hot on the same key. Some systems also add a max-frames-per-turn cap to ensure fairness.

If each client only handles a single small response, a complex budget is not strictly required; however, you must still uphold the core invariant: **no pending outbound ⇒ OP_WRITE OFF**.

## 8. Java 17+ Example 1: observing readiness when the queue is empty

The file **`SelectorWriteInterest.java`** runs on IPv4 loopback. `ServerSocketChannel` accepts one client; the accepted `SocketChannel` is switched to non-blocking mode and registered with a `Selector`. The program **deliberately** enables `OP_WRITE` with no payload for three selection rounds to show that writable readiness can appear. It then disables `OP_WRITE` while idle, enqueues the bytes for `PONG`, enables `OP_WRITE` to send it, and disables `OP_WRITE` again once the queue is empty.

```java
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
import java.util.ArrayDeque;
import java.util.Iterator;

public class SelectorWriteInterest {
    private static void readFully(SocketChannel channel, ByteBuffer dst)
            throws IOException {
        while (dst.hasRemaining()) {
            if (channel.read(dst) == -1) {
                throw new EOFException("Incomplete reply");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByAddress(new byte[] {127, 0, 0, 1});

        try (ServerSocketChannel listener = ServerSocketChannel.open();
             Selector selector = Selector.open()) {
            listener.bind(new InetSocketAddress(loopback, 0));
            int port = ((InetSocketAddress) listener.getLocalAddress())
                    .getPort();

            try (SocketChannel client = SocketChannel.open(
                         new InetSocketAddress(loopback, port));
                 SocketChannel peer = listener.accept()) {
                peer.configureBlocking(false);
                SelectionKey key = peer.register(
                        selector, SelectionKey.OP_WRITE);

                // Deliberately WRONG state: interested in OP_WRITE with
                // no application data queued.
                int idleWritable = 0;
                for (int i = 0; i < 3; i++) {
                    selector.select(1_000);
                    Iterator<SelectionKey> it =
                            selector.selectedKeys().iterator();
                    while (it.hasNext()) {
                        SelectionKey ready = it.next();
                        it.remove();
                        if (ready.isWritable()) {
                            idleWritable++;
                        }
                    }
                }

                System.out.println("Writable while idle observed: "
                        + (idleWritable > 0));

                // Correct idle state: retain OP_READ, disable OP_WRITE.
                key.interestOps(SelectionKey.OP_READ);
                System.out.println("OP_WRITE off while idle: "
                        + ((key.interestOps() & SelectionKey.OP_WRITE) == 0));

                ArrayDeque<ByteBuffer> outbound = new ArrayDeque<>();
                outbound.add(ByteBuffer.wrap(
                        "PONG".getBytes(StandardCharsets.UTF_8)));
                key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);

                for (int attempt = 0;
                     attempt < 20 && !outbound.isEmpty();
                     attempt++) {
                    selector.select(1_000);
                    Iterator<SelectionKey> it =
                            selector.selectedKeys().iterator();
                    while (it.hasNext()) {
                        SelectionKey ready = it.next();
                        it.remove();
                        if (!ready.isWritable()) {
                            continue;
                        }
                        while (!outbound.isEmpty()) {
                            ByteBuffer head = outbound.peek();
                            peer.write(head);
                            if (head.hasRemaining()) {
                                break;
                            }
                            outbound.remove();
                        }
                    }
                }
                if (!outbound.isEmpty()) {
                    throw new IOException("Write did not finish");
                }

                key.interestOps(
                        key.interestOps() & ~SelectionKey.OP_WRITE);
                ByteBuffer answer = ByteBuffer.allocate(4);
                readFully(client, answer);
                answer.flip();
                System.out.println("Queue empty: " + outbound.isEmpty());
                System.out.println("OP_WRITE after drain: "
                        + ((key.interestOps() & SelectionKey.OP_WRITE) != 0));
                System.out.println("Client got: "
                        + StandardCharsets.UTF_8.decode(answer));
            }
        }
    }
}
```

Compile and run on JDK 17+:

```sh
javac -encoding UTF-8 SelectorWriteInterest.java
java SelectorWriteInterest
```

Stdout when loopback is healthy and the socket has send buffer space:

```text
Writable while idle observed: true
OP_WRITE off while idle: true
Queue empty: true
OP_WRITE after drain: false
Client got: PONG
```

Explanation:

1. **`listener.accept()` in blocking mode** is only used to set up a loopback socket in the demo; `peer.configureBlocking(false)` is required before `register(selector, OP_WRITE)`.
2. The first three `select(1000)` calls demonstrate that writable readiness **can** be received repeatedly even without outbound data. This is a normal observation for a healthy loopback socket, not a guarantee that *every* network path is always writable.
3. Disable `OP_WRITE` when there is no data while keeping `OP_READ`. The queue then receives a `ByteBuffer.wrap("PONG")`, so the write bit is enabled.
4. In the write handling, `write` consumes bytes from `position` to `limit`; any remainder stays in the queue. Only after `queue.isEmpty()` is `interestOps & ~OP_WRITE` applied.
5. The client receives the exact four bytes `PONG` via blocking `readFully`. Finishing the write only means the data was accepted by the channel; the demo does not infer any business ACK.

This example is a **selector-state observation exercise**, not a production TCP server, and it intentionally includes a misconfigured phase to illustrate the bug. A proper event loop does not register `OP_WRITE` when the queue is empty in the first place.

## 9. Java 17+ Example 2: framed-response Selector server

The file **`SelectorFramedEcho.java`** is a simple loopback server that processes one request with a 4-byte length-prefix header and sends back `ACK:...`. Key takeaway: the accepted socket registers **`OP_READ` first**, the read handler assembles the full frame, puts the encoded response into the outbound queue **and enables `OP_WRITE`**; when writing finishes and the queue is empty, the handler **removes `OP_WRITE`**. There is no busy `while` loop waiting for `write` to return non-zero.

```java
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.Iterator;

public class SelectorFramedEcho {
    private static final int MAX_FRAME = 2048;

    private static final class Connection {
        final ByteBuffer header = ByteBuffer.allocate(4);
        ByteBuffer body;
        final ArrayDeque<ByteBuffer> outbound = new ArrayDeque<>();
        String request;
        boolean requestComplete;
    }

    private static void onRead(SelectionKey key) throws IOException {
        SocketChannel channel = (SocketChannel) key.channel();
        Connection state = (Connection) key.attachment();

        while (true) {
            ByteBuffer target =
                    state.body == null ? state.header : state.body;
            int bytes = channel.read(target);
            if (bytes == -1) {
                throw new EOFException("Peer closed during request");
            }
            if (bytes == 0) {
                return;
            }
            if (target.hasRemaining()) {
                continue;
            }

            if (state.body == null) {
                state.header.flip();
                int length = state.header.getInt();
                if (length <= 0 || length > MAX_FRAME) {
                    throw new IOException("Invalid frame length");
                }
                state.body = ByteBuffer.allocate(length);
            } else {
                state.body.flip();
                state.request = StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(state.body).toString();

                byte[] payload = ("ACK:" + state.request)
                        .getBytes(StandardCharsets.UTF_8);
                ByteBuffer reply = ByteBuffer.allocate(4 + payload.length);
                reply.putInt(payload.length);
                reply.put(payload);
                reply.flip();

                state.outbound.addLast(reply);
                state.requestComplete = true;
                // Pause reads for this one-request demo and enable writes.
                key.interestOps(
                        (key.interestOps() & ~SelectionKey.OP_READ)
                                | SelectionKey.OP_WRITE);
                return;
            }
        }
    }

    private static void onWrite(SelectionKey key) throws IOException {
        SocketChannel channel = (SocketChannel) key.channel();
        Connection state = (Connection) key.attachment();

        while (!state.outbound.isEmpty()) {
            ByteBuffer head = state.outbound.peekFirst();
            channel.write(head);
            if (head.hasRemaining()) {
                // Partial/zero write: keep OP_WRITE until next readiness.
                return;
            }
            state.outbound.removeFirst();
        }

        // No pending bytes. Keeping OP_WRITE would cause a hot loop.
        key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
    }

    private static void readFully(SocketChannel channel, ByteBuffer target)
            throws IOException {
        while (target.hasRemaining()) {
            if (channel.read(target) == -1) {
                throw new EOFException("Incomplete response");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByAddress(new byte[] {127, 0, 0, 1});
        String expected = "Xin chao \u20AC";

        try (Selector selector = Selector.open();
             ServerSocketChannel server = ServerSocketChannel.open()) {
            server.bind(new InetSocketAddress(loopback, 0));
            server.configureBlocking(false);
            server.register(selector, SelectionKey.OP_ACCEPT);
            int port = ((InetSocketAddress) server.getLocalAddress())
                    .getPort();

            try (SocketChannel client = SocketChannel.open(
                         new InetSocketAddress(loopback, port))) {
                byte[] data = expected.getBytes(StandardCharsets.UTF_8);
                ByteBuffer outgoing = ByteBuffer.allocate(4 + data.length);
                outgoing.putInt(data.length).put(data).flip();
                while (outgoing.hasRemaining()) {
                    client.write(outgoing); // Client is blocking.
                }

                SocketChannel accepted = null;
                SelectionKey peerKey = null;
                Connection state = null;

                try {
                    for (int i = 0;
                         i < 20 && (state == null
                                 || !state.requestComplete
                                 || !state.outbound.isEmpty());
                         i++) {
                        if (selector.select(2_000) == 0) {
                            throw new IOException("Selector timeout");
                        }

                        Iterator<SelectionKey> it =
                                selector.selectedKeys().iterator();
                        while (it.hasNext()) {
                            SelectionKey key = it.next();
                            it.remove();
                            if (key.isAcceptable()) {
                                accepted = server.accept();
                                if (accepted != null) {
                                    accepted.configureBlocking(false);
                                    state = new Connection();
                                    peerKey = accepted.register(
                                            selector, SelectionKey.OP_READ,
                                            state);
                                }
                            } else {
                                if (key.isReadable()) {
                                    onRead(key);
                                }
                                if (key.isValid() && key.isWritable()) {
                                    onWrite(key);
                                }
                            }
                        }
                    }

                    if (state == null || !state.requestComplete
                            || !state.outbound.isEmpty()) {
                        throw new IOException("Incomplete event loop");
                    }

                    ByteBuffer length = ByteBuffer.allocate(4);
                    readFully(client, length);
                    length.flip();
                    int n = length.getInt();
                    if (n < 0 || n > MAX_FRAME) {
                        throw new IOException("Invalid response length");
                    }

                    ByteBuffer body = ByteBuffer.allocate(n);
                    readFully(client, body);
                    body.flip();
                    String response = StandardCharsets.UTF_8
                            .newDecoder()
                            .onMalformedInput(CodingErrorAction.REPORT)
                            .decode(body).toString();

                    System.out.println("Request matches: "
                            + expected.equals(state.request));
                    System.out.println("Response matches: "
                            + ("ACK:" + expected).equals(response));
                    System.out.println("Queued frames: "
                            + state.outbound.size());
                    System.out.println("OP_WRITE after flush: "
                            + ((peerKey.interestOps()
                                    & SelectionKey.OP_WRITE) != 0));
                } finally {
                    if (accepted != null) {
                        accepted.close();
                    }
                }
            }
        }
    }
}
```

Run:

```sh
javac -encoding UTF-8 SelectorFramedEcho.java
java SelectorFramedEcho
```

Deterministic stdout on a successful run:

```text
Request matches: true
Response matches: true
Queued frames: 0
OP_WRITE after flush: false
```

Read these details carefully:

- `server.configureBlocking(false)` is required to register `OP_ACCEPT`. The socket returned by `server.accept()` **still starts in blocking mode**; the example calls `accepted.configureBlocking(false)` before registering `OP_READ`.
- `Connection` is a **per-key attachment**: it holds the header/body buffers, outbound queue, and request state. It does **not** use a server-wide queue that mixes bytes from different clients.
- `onRead` continues when a single read does not fill the header/body; when `read` returns `0`, it stops and waits for the next event without spinning. If EOF occurs mid-frame, it throws `EOFException`.
- Once the full payload is read, the application builds a response frame consisting of a 4-byte big-endian length and a UTF-8 body. **Nothing is sent before data exists**; interest becomes `OP_WRITE` only after enqueuing.
- `onWrite` handles **partial/zero writes**, preserving `ByteBuffer.position`. When no frames remain in `outbound`, it disables `OP_WRITE`.
- The demo only handles **one request**; after parsing the frame, it temporarily disables `OP_READ` to show the state transition clearly. A production server can re-enable `OP_READ` when ready for the next frame, depending on backpressure and quotas.

Do not turn a short example into a production system while omitting timeouts, authentication, maximum concurrent clients, queue capacity, and disconnect handling. The scenario is scoped to one client, one frame, and loopback for deterministic verification.

## 10. Notes on selectedKeys and changing interest during processing

A basic event loop:

```java
// Pseudo-code: handler methods and selector already exist.
while (running) {
    selector.select();

    Iterator<SelectionKey> iterator =
            selector.selectedKeys().iterator();
    while (iterator.hasNext()) {
        SelectionKey key = iterator.next();
        iterator.remove();

        if (!key.isValid()) {
            continue; // Already cancelled/closed.
        }
        try {
            if (key.isAcceptable()) onAccept(key);
            if (key.isValid() && key.isReadable()) onRead(key);
            if (key.isValid() && key.isWritable()) onWrite(key);
        } catch (IOException e) {
            closeConnection(key);
        }
    }
}
```

The pattern above is an **illustrative skeleton, not standalone runnable code**: `running`, `onAccept`, `onRead`, `onWrite`, and `closeConnection` are application components. Key points:

- **Remove the key from the selected-key set** via the iterator before/after handling. If forgotten, behavior across subsequent selection rounds becomes unpredictable; do not blindly call `selectedKeys().clear()` if you have not processed all keys.
- A key can report multiple readiness bits. Check `key.isValid()` after steps that might close/cancel the channel before proceeding to subsequent steps.
- Modifying `interestOps` inside a callback affects the next readiness selection. `isWritable()` reads the ready set already returned by the selector; it does **not** mean that merely enabling `interestOps` forces the currently executing handler to call `onWrite`.
- Avoid enabling `OP_WRITE` and then **repeatedly calling write in the same turn** once the kernel returns `0`. Return to the selector to receive fresh readiness.
- Do not process an unbounded amount of data for one client in a single ready callback; use a budget/quota when fairness is needed.

## 11. When a worker thread produces a response: use a mailbox and selector.wakeup()

This is a very common scenario: a thread pool computes a response after a request is received, while the selector thread is blocked in `select()` waiting for I/O. **Workers must not concurrently mutate `ByteBuffer.position`, the queue, or the accepted key's state**. Design clear ownership:

```text
Worker thread:
  compute response -> immutable byte[]/frame
          |
          v
Thread-safe mailbox (ConcurrentLinkedQueue<Runnable>)
          |
          | selector.wakeup()
          v
Selector owner thread:
  drain mailbox:
    if key valid:
      outbound.add(frame)
      interestOps |= OP_WRITE
  selector.select()
          |
          v
  writable event -> write queue -> drain -> interestOps &= ~OP_WRITE
```

An **illustrative snippet** of handoff (not a standalone runnable program):

```java
// mailbox: ConcurrentLinkedQueue<Runnable>
// selector, key, connection: objects owned by the event-loop thread.
// payload is copied/frozen before placing it into the mailbox.
byte[] ownedCopy = java.util.Arrays.copyOf(
        responseBytes, responseBytes.length);

mailbox.add(() -> {
    if (!key.isValid()) return; // Connection may have closed.
    connection.outbound.addLast(ByteBuffer.wrap(ownedCopy));
    key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
});
selector.wakeup();
```

**`wakeup()` is not a command to send bytes**. It causes an in-progress `select()` (or the next selection call, per the API contract) to return so the owner thread can drain the mailbox and update interest. Enqueuing the task and then calling `selector.wakeup()` prevents a response from sitting in the queue while the selector sleeps indefinitely simply because no new I/O readiness has occurred.

The loop design must **drain the mailbox at a deterministic point**, such as before each `select` or immediately after `select` returns. If a task arrives right as the loop enters `select`, `wakeup` prevents lost progress. Do not treat the selector as thread-safe for arbitrary mutations just because the mailbox is thread-safe: a single owner should decide socket state, and exchanged data must be safely published.

Do not let a callback from another thread call `socketChannel.write` concurrently with the owner writer. A connection needs a single writer responsible for **per-frame** ordering.

## 12. No unbounded queues: per-connection backpressure

Disabling `OP_WRITE` when idle solves the **busy-loop**, but it does not solve workers producing responses **faster than the client can receive them**. If the outbound queue grows without bound:

- Each queued response/frame retains a byte array/`ByteBuffer` on the heap.
- A slow-reading client causes `write` to return `0`; `OP_WRITE` stays enabled (correctly), yet the queue can still grow.
- When many clients are slow simultaneously, total memory usage and GC pressure can rise until the service degrades.

Set a **pending byte limit** rather than only limiting the frame count. A 100-frame queue could hold 100 bytes or 100 MiB if frame sizes are unconstrained.

```text
Example policy:
- perConnectionPendingBytes <= 1 MiB
- globalPendingBytes <= budgeted limit
- frameBytes <= protocol limit
- highWatermark: pause OP_READ / throttle response producers
- lowWatermark: re-enable OP_READ when outbound drops
- overdue/too slow: close peer or report error per application contract
```

These thresholds are **example policies**, not standard constants. You must account for traffic, SLA, connection count, memory, TLS/compression buffer sizes, and peer capacity. Suppressing `OP_READ` can throttle request generation, but it does not automatically throttle independent producers such as notifications or server pushes; those must also be subject to quotas.

**Do not disable `OP_WRITE` while the queue still has bytes** just to save CPU: disabling it at the wrong time can leave pending data **never transmitted** if nothing else re-enables it. When a backlog exists and the kernel cannot accept more writes yet, keep `OP_WRITE` enabled and let the selector wait for readiness.

## 13. Concurrent read/write on one key: preserve the right event mask

A TCP application that both reads requests and sends pushes can keep `OP_READ` enabled and only add `OP_WRITE` when data is pending:

```text
Idle:                       OP_READ
Outbound pending:           OP_READ | OP_WRITE
Kernel write temporarily 0: OP_READ | OP_WRITE  (still pending)
Outbound drained:           OP_READ
Reader under backpressure:  OP_WRITE            (if still pending)
Neither read nor write:     0                   (only if actively managed)
```

If you call `key.interestOps(OP_WRITE)` when enqueuing and forget to OR with the current mask, the system can **accidentally disable `OP_READ`** and stop processing new requests. Conversely, if you always write `interestOps(OP_READ | OP_WRITE)` after every event, you re-enable `OP_WRITE` even when the queue is empty, causing a busy-loop.

A state machine should determine **each bit by its condition**: `OP_READ` by read/inbound backpressure policy; `OP_WRITE` by pending bytes; `OP_CONNECT` only while connecting; `OP_ACCEPT` for listeners. Do not overload an unrelated readiness bit with the meaning “busy processing a request.”

Some designs choose to **stop reading** when the output queue reaches a high watermark. Once it drops below the low watermark, `OP_READ` must be re-enabled with the proper bitmask after checking that the key is still valid. That approach is completely different from leaving `OP_WRITE` permanently enabled.

## 14. The send path: frame length, encoding, ownership, and no interleaving

Before enqueuing, construct a **consistent representation** of the response:

```java
// Snippet: build a frame with a 4-byte big-endian header.
byte[] payload = message.getBytes(StandardCharsets.UTF_8);
ByteBuffer frame = ByteBuffer.allocate(4 + payload.length);
frame.putInt(payload.length); // 4-byte prefix, big-endian by default.
frame.put(payload);
frame.flip();                 // Ready to be consumed by write().
outbound.addLast(frame);     // From here, the event loop owns the frame.
```

If the message contains multi-byte UTF-8 characters, `payload.length` is the **correct** byte count to send. Do not use `String.length()` as the length when the protocol defines a byte length. Validate `payload.length`, frame count, and total pending bytes before allocating/enqueuing.

After `flip`, **do not call `flip` a second time** after a partial `write`; the `ByteBuffer` already maintains the exact `position`. Do not share a single mutable `ByteBuffer` across two connections if both update `position`, even if they wrap the same immutable backing `byte[]`.

With multiple producers, order responses explicitly (by request ID, synchronized enqueue order, or priority), and ensure a **single writer** emits complete frames in the chosen order. TCP preserves byte order on a connection, but it has no awareness of application headers, payloads, or message boundaries.

## 15. Handling close, cancel, and errors to prevent phantom OP_WRITE

When a connection is closed or cancelled:

1. Cancel the `SelectionKey` and close the `SocketChannel` following the defined cleanup path. A cancelled key will no longer receive valid readiness as before.
2. Release outbound buffers and decrement the pending-bytes counter accurately; do not retain references to the queue in stale tasks/attachments.
3. Worker completions arriving **after** the socket has closed must observe `key.isValid() == false` or a mismatched connection generation/token and **must not enqueue** into stale state.
4. When `write` throws `IOException`, do not retry in an infinite loop on the same buffer. Decide whether to close the connection, report a business error, or apply an application-level retry per the protocol.
5. When `write` returns `0` and the queue still has bytes, that is **not an error**; wait for appropriate readiness. If the key never becomes writable again due to a stalled peer, enforce deadlines, rate limits, and a peer-close policy.
6. If **graceful shutdown** is needed, do not immediately close a socket with pending responses without a defined flush/deadline policy. At the same time, do not wait indefinitely for a peer that is not reading.

Sometimes `OP_WRITE` is continuously ready yet the code still fails to shrink the queue because each cycle enqueues more than it writes. In that case the problem is **backpressure/throughput**, not just a busy-loop: inspect queued bytes, producer/consumer rates, channel write return values, and outbound depth to diagnose the cause.

## 16. Testing for CPU bugs and correctness of disabling OP_WRITE

Do not only assert that “one response was returned correctly.” Cover at least these cases:

| Test case | Expectation |
| --- | --- |
| Socket with no outbound bytes | Interest does **not** include `OP_WRITE`; `select` does not wake up pointlessly for writes |
| Enqueue first frame | `OP_WRITE` is enabled; selector can make progress to send |
| Partial write / 0-byte write | `ByteBuffer` preserves unwritten bytes; `OP_WRITE` stays enabled because data is still pending |
| Entire queue written | `OP_WRITE` is removed immediately; `OP_READ` remains intact if still reading |
| Multiple sequential responses | Toggled on/off cleanly across multiple cycles; no bytes re-sent |
| Producer from another worker while selector waits | Mailbox + `wakeup` wakes the event loop, response is sent |
| Slow-reading client | Queue is bounded; overload/backpressure and deadlines trigger |
| Key cancelled while worker computes response | Nothing sent to closed connection; no unhandled `CancelledKeyException` |
| Two clients, one with a large backlog | Write budget prevents starving the other client |

**Useful metrics**: `select` calls per second, selected-key count, ratio of writable events where `queue.isEmpty()`, event-loop thread CPU usage, queue length/bytes, throughput in bytes written, count of `write` returning `0`, and p95/p99 latency. If idle produces hundreds of thousands of `select` calls/sec and most are `OP_WRITE` with no data, that is a clear sign of misconfigured interest.

Performance checks must be evaluated against connection count, buffer sizes, load, TLS, CPU profiler data, and network environment. There is no fixed CPU percentage from which every issue can be attributed to `OP_WRITE`.

## 17. Common mistakes and fixes

1. **Registering every socket with `OP_READ | OP_WRITE` immediately on accept.** When nothing is pending, `OP_WRITE` is usually ready. Start with `OP_READ` and only OR `OP_WRITE` when needed.
2. **Checking `queue.isEmpty()` without removing `OP_WRITE`.** The event loop keeps receiving ready events. Clear the write bit once the queue is drained.
3. **`interestOps(OP_WRITE)` instead of `interestOps(interestOps() | OP_WRITE)`.** Accidentally drops `OP_READ`. Fix with a bitmask.
4. **Disabling `OP_WRITE` after every write event, even on partial writes.** Remaining bytes can stall indefinitely. Only disable when the queue is empty.
5. **Tight-looping `while (write(buffer) == 0)`.** Spins CPU when the kernel buffer is full. Return to `select` and keep the buffer.
6. **Creating a new `ByteBuffer` from scratch on each write attempt.** Re-sends prefix/body bytes. Preserve the original `position` of the partially written buffer.
7. **Forgetting `iterator.remove()` on the selected-key set.** Makes selected readiness and loop behavior unpredictable. Process and remove every key.
8. **Writing two frames concurrently to the same channel from multiple threads.** Header/body bytes can interleave. Use one writer per connection.
9. **Worker only enqueues without calling `wakeup()`.** The selector may stay asleep even though a response is ready; hand off via mailbox and `wakeup`.
10. **Worker mutates queue/key concurrently while owner selector processes it.** Causes races on state/`ByteBuffer`/interest. Enforce single-owner semantics.
11. **Keeping `OP_WRITE` enabled when the queue is empty “just in case we send later.”** Writable readiness is not a notification for new data. New data must trigger interest/`wakeup` itself.
12. **Allowing the output queue to grow unbounded for slow clients.** Causes OOM or heavy GC; enforce byte limits, high/low watermarks, and an overload policy.
13. **Closing the connection immediately after enqueuing without flushing.** Responses may not be sent per contract. Define explicit shutdown/drain behavior.
14. **Confusing writable with peer-received or committed.** TCP writable only means the local send side can accept more bytes; use application-level ACKs when business logic requires it.
15. **Calling `selector.selectNow()` in a tight loop to “avoid blocking.”** When no events exist, that also creates a busy loop. Use blocking `select` + `wakeup`/timers appropriately.
16. **Re-enabling `OP_WRITE` on every selection round even when the queue is empty.** Reintroduces the bug right after fixing it. Treat queue state as the source of truth for interest.

## 18. Quick reasoning scenarios

**Q:** A server has 10,000 idle connections, each registered with `OP_READ | OP_WRITE`. Why is CPU high even with no requests?

**A:** Many sockets have empty send buffers and are therefore writable. `Selector.select` can continuously report `OP_WRITE`, and the event loop processes thousands of keys that have no outbound bytes. Register only `OP_READ` when idle; enable `OP_WRITE` only when enqueuing new data.

**Q:** After `channel.write(head)` returns `0`, should `OP_WRITE` be disabled?

**A:** **No** if `head.hasRemaining()`. The queue still has pending data, so keep `OP_WRITE` enabled and return to the selector. It can be disabled if all pending data has been cleared/cancelled under an explicit error policy.

**Q:** Just finished sending one buffer, and two more remain in the queue. Can `OP_WRITE` be disabled to reduce CPU?

**A:** No, because outbound data is still pending. Keep writing within the budget or keep `OP_WRITE` enabled to receive the next writable readiness.

**Q:** The event loop is in `selector.select()` waiting for `OP_READ`, and a worker just produced a response; why hasn't the response been sent?

**A:** If the worker only added to an external queue without notifying the event loop, the selector may keep waiting. Use a thread-safe mailbox, have the owner enable `OP_WRITE`, and call `selector.wakeup()` to make progress.

**Q:** Does removing `OP_WRITE` lose `OP_READ`?

**A:** Not if you use `key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE)`. That clears only the write bit.

**Q:** If `selectedKeys` still contains an old writable key, is disabling interest enough to remove it from the selected set?

**A:** No. The interest set and the selected-key set are separate. The handler must still remove the key from the selected-key set after processing.

## 19. Implementation checklist and conclusion

When reviewing a TCP selector server, check in order:

1. **Is the accepted `SocketChannel` configured with `configureBlocking(false)`?** Blocking channels cannot be registered with a selector.
2. **Right after accept with no outbound data, is interest `OP_READ` only?** Avoid enabling `OP_WRITE` by default.
3. **Who owns the outbound queue?** One event-loop/connection owner; do not mutate `ByteBuffer` from multiple threads.
4. **When adding the first response, are `OP_WRITE` and `wakeup` triggered properly?** Worker threads go through a mailbox.
5. **When a write is incomplete, are the `ByteBuffer` and `OP_WRITE` preserved?** Partial/zero writes must neither spin nor drop bytes.
6. **When the queue empties, is `OP_WRITE` cleared immediately with `& ~OP_WRITE`?** Preserve other valid interests.
7. **Are selected keys removed after processing?** Do not confuse the readiness set with the interest set.
8. **Are pending bytes bounded with backpressure for slow clients?** Do not let queues grow without limit.
9. **Is starvation of other connections prevented via a write budget?** A peer with a large backlog must not monopolize the event loop.
10. **Are close, cancel, timeout, and late worker completions handled?** Do not set interest on invalid keys.
11. **Are idle CPU, slow readers, partial writes, and enqueue→drain cycles tested?** Those are the most effective scenarios for catching `OP_WRITE` bugs.

**Conclusion:** `OP_WRITE` is a **signal that the socket can accept writes**, not a **signal that the application has something to send**. The application manages pending data itself: **enable `OP_WRITE` when the queue becomes non-empty, keep it enabled while bytes remain, and disable it immediately after draining**. This small rule often determines whether an idle selector event loop truly sleeps or spins hot at high CPU.

### Standard API references

- [Java SE 17 — `SelectionKey`, `OP_WRITE`, `interestOps()`, and `readyOps()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html)
- [Java SE 17 — `Selector`, `select()`, `selectedKeys()`, and `wakeup()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html)
- [Java SE 17 — `SocketChannel` and `write(ByteBuffer)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [Java SE 17 — `ByteBuffer` and `position/limit` positions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java SE 17 — `ServerSocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html).
