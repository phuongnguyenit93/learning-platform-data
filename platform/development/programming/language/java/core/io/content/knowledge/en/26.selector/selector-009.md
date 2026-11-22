# Register OP_WRITE Only While Outbound Data Remains in Java NIO Selector

## 1. Why Does OP_WRITE Often Cause a CPU-Burning Loop?

In Java NIO, `SelectionKey.OP_WRITE` asks the `Selector` to monitor whether a `SocketChannel` is able to accept more bytes from the application. For a connected TCP socket, the OS send buffer usually has free space, so the channel can be reported **writable** almost continuously.

If every socket registers `OP_WRITE` upon connecting and keeps that flag set even when there is no data to send, a Selector thread can spin very fast:

~~~text
Outbound queue empty
        |
interestOps = OP_READ | OP_WRITE
        |
select() returns because socket is writable
        |
isWritable() is true yet zero bytes need sending
        |
return to select() → writable again → empty handling → loop forever
~~~ 

This is **write-readiness spin**: the event loop wakes up repeatedly with no useful work, driving up CPU usage, wasting energy, and reducing capacity for connections that genuinely have work.

**Rule:** add `OP_WRITE` to `interestOps` only while the connection has bytes waiting to be sent; remove it as soon as the outbound queue is empty. `OP_READ` is normally kept separately if the connection still needs to receive data.

## 2. Interest, Readiness, and Actual Write Are Three Different Things

| Component | Question Answered |
| --- | --- |
| `key.interestOps()` | Which operations does the application **want to monitor**? |
| `key.readyOps()` or `key.isWritable()` | Did the selector **detect** that the socket can attempt writing on this selection pass? |
| `channel.write(buffer)` | How many bytes did this call **actually transfer** from the buffer? |

A key having `OP_WRITE` in its interest set does not mean bytes were sent. `key.isWritable()` does not guarantee a single `write` drains the entire buffer. With a non-blocking channel, `write` can return 0 or fewer bytes than `buffer.remaining()` prior to the call.

Writability only concerns write capacity on the sending side. It **does not prove** the peer received, processed, or durably stored the data; knowing that requires an application-layer response or ACK protocol.

~~~text
Bytes queued to send → Add OP_WRITE → Selector reports writable
                                              |
                                              v
                                        write(buffer)
                                              |
                              +---------------+---------------+
                              |                               |
                         Data remains?                   All data sent?
                              |                               |
                          Keep OP_WRITE                 Remove OP_WRITE
                          Keep position                 Keep OP_READ
                          Wait next turn                Avoid CPU spin
~~~

## 3. Toggling the OP_WRITE Bit Correctly

Once TCP is connected, with no outbound data:

~~~java
key.interestOps(SelectionKey.OP_READ);
~~~

When new data appears, add `OP_WRITE` **without losing** existing flags:

~~~java
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
~~~

When the queue empties, remove only the `OP_WRITE` bit:

~~~java
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
~~~

These are illustrative snippets inside an event loop, assuming a valid `key` and appropriate `java.nio.channels.*` imports; they are not a standalone program.

| Prior Interest Set | Action | Resulting Interest Set |
| --- | --- | --- |
| `OP_READ` | Add `OP_WRITE` | `OP_READ | OP_WRITE` |
| `OP_READ | OP_WRITE` | Add `OP_WRITE` again | Unchanged |
| `OP_READ | OP_WRITE` | Remove `OP_WRITE` | `OP_READ` |
| `OP_READ` | Remove `OP_WRITE` | Unchanged |

**Mistake:** writing `key.interestOps(SelectionKey.OP_WRITE)` when you still want to read. That call **replaces the entire mask**, wiping out `OP_READ`. To only add a flag, use bitwise OR; to only remove a flag, use bitwise AND with the inverted bit.

Java 17 also offers `SelectionKey.interestOpsOr(mask)` and `interestOpsAnd(mask)` for atomic bit updates. However, atomicity of the mask does not by itself protect the data queue: multithreaded applications still need ownership rules, synchronization, or task handoff.

## 4. ByteBuffer Must Preserve Unwritten Bytes

Calling `channel.write(source)` consumes bytes from `source.position()` up to `source.limit()`, advancing position by the number of bytes actually transferred.

Suppose a buffer holds 10 bytes. One `write` transfers 4 bytes:

~~~text
Before: position=0, limit=10, remaining=10
write() returns 4
After:  position=4, limit=10, remaining=6
~~~

The last six bytes **have not yet been transferred out of the ByteBuffer**. The application must keep that buffer and continue writing on the next readiness event. Never call `clear()`, `rewind()`, or `flip()` arbitrarily between two send attempts, as doing so can resend duplicates or lose bytes.

Example of a connection with an outbound queue:

~~~text
head                                                       tail
  |                                                          |
[Buffer A: 6 bytes left] → [Buffer B: 12 bytes left] → [Buffer C]
                             Outbound is still non-empty
                             so OP_WRITE is needed
~~~

Use a queue holding `ByteBuffer` objects already in **read** mode ready for sending. `ByteBuffer.wrap(byte[])` and `StandardCharsets.UTF_8.encode(text)` return buffers already positioned for sending; when using `ByteBuffer.allocate(...)` followed by `put(...)`, call `flip()` after putting.

Basic snippet for a writable event:

~~~java
while (!outbound.isEmpty()) {
    ByteBuffer head = outbound.peek();
    int n = channel.write(head);

    if (head.hasRemaining()) {
        // Partial write or n == 0; keep head to continue sending.
        break;
    }

    outbound.remove();
}

if (outbound.isEmpty()) {
    key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
}
~~~

This is an illustrative snippet inside a method handling a `SocketChannel` with a `Queue<ByteBuffer> outbound` and `SelectionKey key`; it is not a standalone runnable program.

Checking `head.hasRemaining()` is the crucial step. Once the head buffer is exhausted, remove it from the queue and try sending the next buffer. When the socket cannot make progress yet, never spin calling `write` endlessly: return from the method, keep `OP_WRITE`, and wait for the next readiness pass.

## 5. What States Does a Connection Have?

~~~text
                    Connected
                        |
                        v
                   Queue empty
                  interest=OP_READ
                        |
                  enqueue(payload)
                        |
                        v
                 Queue has bytes
            interest=OP_READ | OP_WRITE
                        |
                 Selector writable
                        |
                   write(head)
                        |
             +----------+----------+
             |                     |
      Head has bytes         Head fully sent
             |                     |
       Wait next turn       Remove head from queue
             |                     |
       Keep OP_WRITE         Another head left?
                                   |
                              +----+----+
                              |         |
                             Yes        No
                              |         |
                        Keep OP_WRITE   Remove OP_WRITE
                                        Keep OP_READ
~~~

This is an **application-managed state machine**, not an automatic Selector mechanism. It must handle both partial writes and `write` returning 0.

Do not create a new `SelectionKey` every time a payload arrives. A channel registered on a selector normally keeps its corresponding key and simply updates the interest set. If the key is canceled/closed, end the connection lifecycle or re-register according to API rules.

## 6. Standalone Java 17+ Example: Toggling OP_WRITE While Sending PING and PONG

This program uses loopback TCP, one `Selector`, and one thread. The client sends `PING`, and the server replies `PONG`. `OP_WRITE` is enabled only when outbound data exists, and turned off once sending completes.

The server uses `OP_ACCEPT`. The client uses `OP_CONNECT` if `connect()` is not yet finished; if the connection finishes immediately, it transitions straight to `OP_WRITE`. Output lines are printed only as each milestone completes, so they do not depend on selected-key ordering.

Save as `WriteInterestDemo.java`:

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

public class WriteInterestDemo {
    public static void main(String[] args) throws IOException {
        try (Selector selector = Selector.open();
             ServerSocketChannel listener = ServerSocketChannel.open();
             SocketChannel client = SocketChannel.open()) {

            listener.configureBlocking(false);
            listener.bind(new InetSocketAddress(
                    InetAddress.getLoopbackAddress(), 0));
            listener.register(selector, SelectionKey.OP_ACCEPT);

            client.configureBlocking(false);
            boolean connected = client.connect(listener.getLocalAddress());
            client.register(selector, connected
                    ? SelectionKey.OP_WRITE
                    : SelectionKey.OP_CONNECT);

            ByteBuffer request = ByteBuffer.wrap(
                    "PING".getBytes(StandardCharsets.US_ASCII));
            ByteBuffer serverInput = ByteBuffer.allocate(4);
            ByteBuffer response = ByteBuffer.wrap(
                    "PONG".getBytes(StandardCharsets.US_ASCII));
            ByteBuffer clientInput = ByteBuffer.allocate(4);

            SocketChannel peer = null;
            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(10);

            try {
                while (clientInput.hasRemaining()
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
                            SocketChannel accepted = listener.accept();
                            if (accepted != null) {
                                accepted.configureBlocking(false);
                                accepted.register(
                                        selector, SelectionKey.OP_READ);
                                peer = accepted;
                                key.interestOps(0);
                            }
                        } else if (key.isConnectable()) {
                            if (client.finishConnect()) {
                                key.interestOps(SelectionKey.OP_WRITE);
                            }
                        } else if (key.isWritable()) {
                            if (key.channel() == client) {
                                client.write(request);
                                if (!request.hasRemaining()) {
                                    key.interestOps(SelectionKey.OP_READ);
                                    System.out.println(
                                            "client OP_WRITE removed=true");
                                }
                            } else {
                                SocketChannel serverSide =
                                        (SocketChannel) key.channel();
                                serverSide.write(response);
                                if (!response.hasRemaining()) {
                                    key.interestOps(0);
                                    System.out.println(
                                            "server OP_WRITE removed=true");
                                }
                            }
                        } else if (key.isReadable()) {
                            SocketChannel reading =
                                    (SocketChannel) key.channel();

                            if (reading == client) {
                                int n = client.read(clientInput);
                                if (n < 0) {
                                    throw new EOFException(
                                            "Server closed before PONG");
                                }
                            } else {
                                int n = reading.read(serverInput);
                                if (n < 0) {
                                    throw new EOFException(
                                            "Client closed before PING");
                                }
                                if (!serverInput.hasRemaining()) {
                                    serverInput.flip();
                                    String message =
                                            StandardCharsets.US_ASCII
                                                    .decode(serverInput)
                                                    .toString();
                                    System.out.println(
                                            "server received=" + message);
                                    key.interestOps(SelectionKey.OP_WRITE);
                                }
                            }
                        }
                    }
                }

                if (clientInput.hasRemaining()) {
                    throw new IOException("Timed out waiting for PONG");
                }

                clientInput.flip();
                System.out.println("client received="
                        + StandardCharsets.US_ASCII.decode(clientInput));
            } finally {
                if (peer != null) {
                    peer.close();
                }
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac WriteInterestDemo.java
java WriteInterestDemo
~~~

Expected stdout when the environment allows loopback connections and completes I/O:

~~~text
client OP_WRITE removed=true
server received=PING
server OP_WRITE removed=true
client received=PONG
~~~

Analysis:

1. The client registers `OP_CONNECT` while connection is pending; if it finishes immediately, it registers `OP_WRITE` because `PING` is already queued.
2. The client writes the `PING` buffer. If fewer than 4 bytes are written, the buffer still has `remaining()` and `OP_WRITE` remains enabled. Once fully sent, it switches to `OP_READ`.
3. The server-side socket monitors `OP_READ`, accumulating all 4 bytes. Once `PING` arrives, it updates its interest set to `OP_WRITE` since it is ready to send `PONG`.
4. The server writes all of `PONG` and clears `OP_WRITE` by setting interest to 0, as this example handles a single request/response.
5. The client reads all 4 bytes of `PONG`, exits the loop, and prints the result.
6. Selected keys are removed from the set via `Iterator.remove()`; channels and the selector are closed at the end.

**Conditions:** the environment must permit opening TCP loopback sockets and complete within the 10-second deadline. This example demonstrates only one fixed message each way and does not handle multi-message queues, TLS, framing protocols, or thousands of connections. If networking is disallowed in the environment, an exception will be thrown instead of printing the stdout above.

## 7. In a Real Server: Outbound Queue and Connection State

For multiple messages, attach dedicated state to each `SelectionKey` using `key.attach(state)`. A common structure:

~~~java
final class ConnectionState {
    final java.util.ArrayDeque<ByteBuffer> outbound =
            new java.util.ArrayDeque<>();
    final ByteBuffer inbound = ByteBuffer.allocate(8192);
    long queuedBytes;
}
~~~

This is an illustrative class within a larger project; `java.nio.ByteBuffer` must be imported.

On the **Selector thread** when a new message is ready:

~~~java
void enqueue(SelectionKey key, ByteBuffer data) {
    ConnectionState state = (ConnectionState) key.attachment();
    if (!data.hasRemaining()) {
        return;
    }

    state.queuedBytes += data.remaining();
    state.outbound.addLast(data);
    key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
}
~~~

On the **Selector thread** when the key becomes writable:

~~~java
void onWritable(SelectionKey key) throws IOException {
    SocketChannel ch = (SocketChannel) key.channel();
    ConnectionState state = (ConnectionState) key.attachment();

    while (!state.outbound.isEmpty()) {
        ByteBuffer head = state.outbound.peekFirst();
        int n = ch.write(head);
        state.queuedBytes -= n;

        if (head.hasRemaining()) {
            break;
        }
        state.outbound.removeFirst();
    }

    if (state.outbound.isEmpty()) {
        key.interestOps(
                key.interestOps() & ~SelectionKey.OP_WRITE);
    }
}
~~~

These are **illustrative method fragments**, without `main` or full lifecycle guards. They assume the key is valid and state is mutated exclusively by the Selector thread.

**ByteBuffer ownership:** after enqueuing, the producer must not mutate the payload's backing array or position until the consumer finishes processing or copying it. Otherwise, races and corrupted transmissions can occur.

Once the queue is empty, there is no reason to watch for writable events. When new data arrives again, re-enable the bit. `OP_READ` stays enabled if the application still wants to accept incoming requests.

## 8. Backpressure and Bounding Queued Data

Turning off `OP_WRITE` prevents CPU spinning **when there is nothing to send**, but does not solve **a producer generating data faster than the socket can consume it**. If the application produces 10 MiB/s while the link consumes only 1 MiB/s, the queue grows by roughly 9 MiB every second; this is an illustrative example, not a measurement for all systems.

To avoid exhausting memory, you should:

- Cap queued bytes and message counts per connection and globally.
- Use a **high-water mark** to pause or throttle data generation when backlog grows too high.
- Use a **low-water mark** to resume accepting/pushing data once backlog drops.
- When appropriate, temporarily remove `OP_READ` so you do not accept more requests that generate even more responses, provided the protocol permits it.
- Cap bytes written per event-loop iteration so one connection with a large outbound backlog does not starve other connections.
- Enforce timeout policies, reject requests, or close overly slow connections if the queue cannot recover.

Even draining a queue completely through `write` does not mean the remote application has processed the data. Separate ACKs/responses are needed if the protocol requires confirmation.

## 9. When Another Thread Generates Outbound Data

In real applications, a worker thread may finish building a response while the selector thread is sleeping in `select()`. Never let a worker arbitrarily mutate a connection's `ArrayDeque`, because `ArrayDeque` is not thread-safe.

An easy-to-manage model:

1. Worker builds the payload and adds an **enqueue task** to a thread-safe command queue.
2. Worker calls `selector.wakeup()` so the thread in `select()` handles the task promptly.
3. The Selector thread drains tasks, appends the payload to the connection's outbound queue, and adds `OP_WRITE` when needed.
4. Once all data is written, the Selector thread itself removes `OP_WRITE`.

~~~text
Worker thread                       Selector thread
     |                                      |
     | build response                       | select()
     |                                      |
     +-- commandQueue.add(task) ----------->|
     +-- selector.wakeup() ---------------->| wakes up
                                            |
                                            +-- process task
                                            +-- outbound.add(payload)
                                            +-- add OP_WRITE
                                            +-- wait writable and write
~~~

`wakeup()` **does not** send bytes itself, does not change `interestOps`, and does not make any queue thread-safe. When a task arrives late after a key was canceled or a connection closed, have a policy to drop the task or handle the error safely.

`SelectionKey.interestOpsOr(...)` and `interestOpsAnd(...)` can assist with atomic bit updates, yet do not replace queue data synchronization. Having a single thread own the interest set and queue prevents subtle errors when multiple sources produce responses.

## 10. Common Pitfalls

### Keeping OP_WRITE Even Without a Payload

~~~java
socket.register(selector,
        SelectionKey.OP_READ | SelectionKey.OP_WRITE);
~~~

This snippet assumes an open `socket` and `selector`. When there is no outbound data, the socket is still usually writable, causing the selector to wake continuously. **Fix:** register only `OP_READ` by default, and turn on `OP_WRITE` only when the queue has bytes.

### Removing OP_WRITE Too Early

`channel.write(payload)` might transfer 4 out of 10 bytes. If you immediately clear `OP_WRITE`, the remaining 6 bytes may sit unsent forever. **Fix:** remove it only after every outbound buffer has no `remaining()`.

### Writing Partially Then Resetting the Buffer

Calling `clear()` or `rewind()` on a partially sent buffer moves position back to the start, potentially sending duplicate bytes. The buffer must retain its exact state from the previous writable turn.

### Busy-Looping When write Returns 0

~~~java
while (buffer.hasRemaining()) {
    channel.write(buffer);
}
~~~

On a non-blocking channel, the loop above can spin the CPU while making zero progress. **Fix:** if bytes remain unsent and cannot be written right now, return to the Selector and wait for readiness.

### Replacing the Entire Interest Mask and Losing OP_READ

`key.interestOps(SelectionKey.OP_WRITE)` wipes out existing bits instead of merely adding `OP_WRITE`. Use bitwise OR to add a bit, or replace the entire mask only if you genuinely intend to change the whole state.

### Unbounded Outbound Queues

Managing `OP_WRITE` properly can still exhaust RAM if a remote peer is very slow. Apply watermarks, queue caps, and backpressure.

### Mutating Queues from Multiple Threads Without Synchronization

`ArrayDeque` is not thread-safe. Let the Selector thread own the queue, while worker threads submit via a thread-safe command queue and `wakeup()`.

### Confusing Writable with Delivery ACK

When `write` returns the number of bytes transferred, there is no guarantee the peer processed the message. If end-to-end confirmation is needed, build an ACK protocol.

## 11. Practice Check

1. Channel is connected, outbound queue is empty. Which bits should be monitored? **Usually only `OP_READ`**, without keeping `OP_WRITE`.
2. A 200-byte buffer is added to the queue. What must be done? **Enable `OP_WRITE`**.
3. `write` transfers 70/200 bytes. Next step? **Keep the 130 bytes and `OP_WRITE`**, retrying when reported ready.
4. Queue has two buffers; the first buffer is exhausted while the second still has bytes. Can `OP_WRITE` be removed yet? **Not yet**.
5. Queue is completely empty. What must be done? **Remove `OP_WRITE`**, typically keeping `OP_READ`.
6. Does `key.interestOps(OP_WRITE)` keep the `OP_READ` bit? **No**; the setter replaces the entire mask.
7. Why not call `write` in an infinite loop when it returns `0`? **Because the non-blocking channel made no progress yet and must wait for readiness**.
8. Why must `ByteBuffer.position()` be preserved between writes? **To continue from the first unsent byte without repeating old data**.
9. A worker produces a response while the selector is waiting. How do they coordinate? **Submit a task to a thread-safe queue, call `wakeup()`, and let the selector thread enable `OP_WRITE`**.
10. Is toggling `OP_WRITE` enough to prevent running out of RAM? **No**; outbound queues must also be bounded with backpressure.

**Remember:** `OP_WRITE` represents write capability, not a signal that "data needs to be sent." Enable the bit only while the outbound queue contains bytes; keep it enabled when `write` transfers only partially; and once all buffers are consumed, remove `OP_WRITE` to avoid CPU spin. Combine this with `ByteBuffer` ownership, cross-thread synchronization, and backpressure for an event loop that is both accurate and efficient.
