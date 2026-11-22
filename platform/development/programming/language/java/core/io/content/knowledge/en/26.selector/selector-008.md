# Selector: I/O Readiness Does Not Guarantee Full Operation Completion

In Java NIO, `Selector` monitors multiple `SelectableChannel` instances to detect **readiness** — when a read, write, accept, or connect operation **is able to make progress** without blocking. However, **ready does not mean complete**: an `OP_READ` signal does not promise reading an entire message, `OP_WRITE` does not promise flushing an entire buffer, `OP_ACCEPT` does not promise accepting all waiting connections, and `OP_CONNECT` does not promise the connection has succeeded.

That is why a proper event loop must combine **ready ops + actual API return values + remaining buffer/protocol state**, and then return to the Selector when unfinished. This lesson focuses on distinguishing readiness from completion, handling partial I/O, zero progress, and the limits of each event in Java 17+.

## 1. How Does Readiness Differ from Completion?

Two concepts:

- **Readiness:** the OS/provider notifies that a class of operation on a channel is likely able to execute at the time of inspection; `Selector.select()` yields `SelectionKey` instances containing readiness bits.
- **Completion:** the **application-level** operation actually achieves its goal, such as receiving a full 100-byte frame, sending an entire 8 KiB response, completing a TCP connect, or draining all pending connections.

```text
                 Selector.select()
                        |
                        v
                  OP_READ ready
                        |
                        v
              socket.read(buffer)
                        |
             +----------+-----------+
             |          |           |
           n > 0       n == 0      n == -1
             |          |           |
        New bytes   No progress   EOF/half-close
             |        yet           |
             v                      v
       Full frame yet?       Handle close/end
          /       \
        Yes        No
        |          |
  Process frame  Save buffer/state
                 and wait for more reads
```

A single TCP message may be split across multiple `read` calls, or multiple messages may arrive in a single `read`. Never equate **I/O call boundaries**, **TCP packet boundaries**, and **application request boundaries**.

### Short Example

Suppose a protocol defines an **8-byte** frame, yet when `OP_READ` fires, the first read returns only 3 bytes. The buffer now has `position = 3`, missing 5 bytes: the request is **not yet complete**. If the handler tries to decode immediately, it may throw `BufferUnderflowException` or produce corrupt data. The handler must retain the 3 bytes, wait for the next read, and decode only once all 8 bytes arrive.

Conversely, a single `OP_READ` event can also yield **two complete frames** in one read; the parser must process both rather than assuming at most one arrived.

## 2. Interest Ops and Ready Ops Are Not I/O Results

A `SelectionKey` carries two bitmasks:

| API | Answers the Question | Does Not Guarantee |
| --- | --- | --- |
| `key.interestOps()` | Which operation types does the application **want to monitor**? | Does not assert the channel is ready. |
| `key.readyOps()` | Which operation types did the selector just detect as **able to make progress**? | Does not assert bytes or records are complete. |
| `key.isReadable()` | Is the `OP_READ` bit present in ready ops? | Does not guarantee `read` returns the required byte count. |
| `key.isWritable()` | Is the `OP_WRITE` bit present in ready ops? | Does not guarantee `write` empties the buffer. |
| `key.isAcceptable()` | Is there readiness for `accept`? | Does not guarantee draining every waiting client. |
| `key.isConnectable()` | Is there readiness to try completing connect? | Does not guarantee connect succeeded. |

Both `interestOps` and `readyOps` describe **operation types**, not transfer sizes. To know progress, use the count `n` returned by the channel and the state of `ByteBuffer`.

Before reading key state, check `key.isValid()`. A key might have been `cancel()`ed or its channel closed; many operations on an invalid key throw `CancelledKeyException`.

## 3. Effect of Read/Write on ByteBuffer

A `ByteBuffer` has three parameters and one derived value:

```text
0 <= position <= limit <= capacity
remaining = limit - position
```

- `position()` is the offset of the next element in the buffer.
- `limit()` is the **exclusive** upper bound of the permitted working region.
- `capacity()` is the total capacity of the buffer.
- `remaining()` is the number of elements remaining in the range from `position` up to `limit`.

When calling `socket.read(buffer)` in **buffer write mode**, if `n > 0`, the channel places `n` more bytes and advances `buffer.position()` by exactly `n`.

After reading, call `buffer.flip()` to switch to **consume mode**: `limit = old position` and `position = 0`. The decoder reads bytes or fields within `[position, limit)`. After decoding:

- Call `clear()` **only when all** retained content has been processed, to prepare for a fresh read batch.
- Call `compact()` when incomplete frame bytes still remain; this keeps `remaining()`, shifts them to the start, sets `position` to the retained byte count, and sets `limit` to `capacity`.
- Call `rewind()` when you want to re-read the same region, not to prepare for receiving new data.

When calling `socket.write(outBuffer)` in **buffer read mode**, if `n > 0`, the channel consumes `n` bytes and advances `outBuffer.position()` by `n`. If `outBuffer.hasRemaining()` is still true, the response is **not completely sent**.

**Do not manually add `n` to `position`**: channel methods update it already. And never use `capacity` as the valid byte count after `flip()`; the proper measure is `remaining()`.

## 4. OP_READ: Partial Reads Are Normal

With a `SocketChannel` configured via `configureBlocking(false)`, calling `read(ByteBuffer)` returns:

| Value | Meaning | Typical Handling |
| --- | --- | --- |
| `n > 0` | Actually read `n` bytes. | Advance parser; if frame is still incomplete, retain partial bytes and read more when appropriate. |
| `n == 0` | No bytes transferred in this call. | Do not conclude EOF; exit the read loop and wait for another readiness. |
| `n == -1` | Input reached EOF, e.g., peer closed its write half. | Handle protocol termination, incomplete frames, and half-close/connection-close policy. |

When ready, you can read in a loop until `read == 0` (currently available data drained) **or a per-event work budget is reached**. You should not let a single busy client continuously pumping data monopolize the event loop.

**Illustrative** pattern (the functions and state variables belong to the application, not built-in APIs):

```java
// socket: non-blocking SocketChannel; state.input is in write mode.
int n = socket.read(state.input);
if (n < 0) {
    handleInputEof(state); // Account for partial frame, half-close, pending output.
} else if (n > 0) {
    state.input.flip();
    decodeCompleteFrames(state.input, state); // Consume complete frames only.
    state.input.compact(); // Keep incomplete bytes so next read appends smoothly.
}
// n == 0: No new data to process; wait for the next OP_READ.
```

If the input buffer is full yet the parser still cannot make progress, enforce a capacity/frame-size limit or design payload streaming. **Never** wait forever on `OP_READ` with `buffer.remaining() == 0`; even with readiness, the buffer cannot accept any more bytes.

Readiness can also be reported when EOF is present; do not assume `key.isReadable()` guarantees at least one data byte is available.

## 5. OP_WRITE: Writable Does Not Mean All Data Was Sent

In TCP, a socket can be reported writable whenever the OS has room to accept **at least part** of the data into its send buffer. However:

- `socket.write(buffer)` can return `n < buffer.remaining()` from before the call.
- It can return `0`, even after the key previously reported ready (conditions changed or resources are temporarily unavailable).
- While data remains, the application must retain the buffer (with its updated `position`) and write further in this turn or on a later readiness event.
- Bytes accepted by the channel **do not equal** bytes processed by the receiver, and do not guarantee the message reached the peer application.

Proper sending pattern:

```java
// pending: flipped ByteBuffer containing data waiting to be sent.
while (pending.hasRemaining()) {
    int n = socket.write(pending);
    if (n == 0) {
        break; // Avoid busy-looping: wait for the next OP_WRITE.
    }
}
if (!pending.hasRemaining()) {
    // Current buffer finished; clear OP_WRITE if queue is empty.
}
```

This is a snippet requiring a non-blocking `SocketChannel socket`. In a real program, check deadlines, close the socket on `IOException`, process subsequent buffers in the queue, and apply backpressure.

**Important note:** `OP_WRITE` is frequently ready whenever the socket can write. If `OP_WRITE` stays permanently enabled even with **no pending data**, the selector can wake repeatedly and spike CPU usage. Enable it only when the outbound queue is non-empty, and disable it once sent:

```java
// Snippet: key is still valid.
key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);

// After completing the entire outbound queue:
key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
```

Bitmask operations `|` and `& ~` preserve other interests such as `OP_READ`. Blindly calling `interestOps(OP_WRITE)` can accidentally turn off reading.

## 6. Java 17+ Example: Selector Ready Multiple Times, Data Transferred in Parts

This example actually uses **one `Selector`**, one `Pipe.SinkChannel`, and one `Pipe.SourceChannel`. Both channels are set to **non-blocking** and registered for `OP_WRITE` and `OP_READ` respectively. To demonstrate partial I/O **deterministically**, each write is intentionally capped at most 2 bytes by temporarily shrinking `ByteBuffer.limit()`; the read buffer likewise has capacity 2.

Temporarily lowering the limit is a **testing technique** to make the behavior obvious, not a promise that `SocketChannel` always writes 2 bytes. Real channels can transfer **even fewer**.

Save as **`ReadinessNotCompletionDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;

public class ReadinessNotCompletionDemo {
    public static void main(String[] args) throws IOException {
        Pipe pipe = Pipe.open();
        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {

            source.configureBlocking(false);
            sink.configureBlocking(false);
            source.register(selector, SelectionKey.OP_READ);
            SelectionKey outputKey =
                    sink.register(selector, SelectionKey.OP_WRITE);

            ByteBuffer pending = ByteBuffer.wrap(
                    "ABCDE".getBytes(StandardCharsets.US_ASCII));
            ByteArrayOutputStream received = new ByteArrayOutputStream();
            int writeCalls = 0;
            int readCalls = 0;

            while (pending.hasRemaining() || received.size() < 5) {
                if (selector.select(3_000) == 0) {
                    throw new IOException("Timeout khi chờ I/O");
                }
                Iterator<SelectionKey> it =
                        selector.selectedKeys().iterator();
                while (it.hasNext()) {
                    SelectionKey key = it.next();
                    it.remove();
                    if (!key.isValid()) {
                        continue;
                    }

                    if (key.isWritable()) {
                        int oldLimit = pending.limit();
                        pending.limit(Math.min(
                                oldLimit, pending.position() + 2));
                        try {
                            int n = sink.write(pending);
                            if (n > 0) {
                                writeCalls++;
                            }
                        } finally {
                            pending.limit(oldLimit);
                        }
                        if (!pending.hasRemaining()) {
                            outputKey.interestOps(0);
                        }
                    }

                    if (key.isReadable()) {
                        ByteBuffer chunk = ByteBuffer.allocate(2);
                        int n = source.read(chunk);
                        if (n == -1) {
                            throw new IOException("EOF sớm");
                        }
                        if (n > 0) {
                            readCalls++;
                            chunk.flip();
                            while (chunk.hasRemaining()) {
                                received.write(chunk.get());
                            }
                        }
                    }
                }
            }

            System.out.println("writeCalls>=3: " + (writeCalls >= 3));
            System.out.println("readCalls>=3: " + (readCalls >= 3));
            System.out.println("payload=" +
                    received.toString(StandardCharsets.US_ASCII));
            System.out.println("pending=" + pending.remaining());
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 ReadinessNotCompletionDemo.java
java ReadinessNotCompletionDemo
```

Verified output when compiled and executed:

```text
writeCalls>=3: true
readCalls>=3: true
payload=ABCDE
pending=0
```

Detailed explanation:

1. `Pipe.open()` creates the sink/source pair. Both source and sink are configured with `configureBlocking(false)` and registered with the same selector.
2. `ByteBuffer.wrap("ABCDE"...)` has 5 pending bytes. Each time the sink is ready, the program temporarily caps the write window to 2 bytes; thus **at least 3 successful writes are required**, even though the selector reported readiness beforehand.
3. `sink.write(pending)` advances position by the actual byte count. `finally` restores the old limit. Once the buffer is fully sent, `outputKey.interestOps(0)` disables `OP_WRITE` to prevent pointless spinning.
4. Source readiness leads to `source.read(chunk)` with a 2-byte buffer, so receiving all 5 bytes takes **at least 3 successful read passes**. Bytes accumulate into `ByteArrayOutputStream`.
5. `selectedKeys().iterator()` is iterated and each key is removed via `iterator.remove()`; key selection order is unspecified, yet the final result is identical.
6. The event loop finishes based on **two real completion conditions**: `pending` has no bytes left **and** received byte count reaches 5, not simply because one readiness event occurred.
7. A timeout is used in the example to fail cleanly if no readiness arrives rather than waiting forever. In real systems, timeouts should govern the overall operation, not merely each individual select call.

The lines `writeCalls>=3` and `readCalls>=3` express a **lower bound**, not a fixed native call count. That is why the output is deterministic across valid channel implementations in test environments; the actual iteration count could be higher.

## 7. OP_ACCEPT Does Not Guarantee Accepting Every Connection

With a non-blocking `ServerSocketChannel`, `OP_ACCEPT` signals a connection may be waiting. The handler must call `server.accept()` and check the actual return value:

```java
// Snippet: server is a non-blocking ServerSocketChannel
// registered for OP_ACCEPT, selector is open.
for (int i = 0; i < 64; i++) { // Cap to avoid starving other channels.
    SocketChannel client = server.accept();
    if (client == null) {
        break; // No connection ready to accept right now.
    }
    client.configureBlocking(false);
    client.register(selector, SelectionKey.OP_READ, new ClientState());
}
```

`ClientState` is an application-defined type; this snippet does not compile standalone. `accept()` can return `null` when no pending connection remains, even if readiness was previously reported.

**Do not** write `while (server.accept() == null) { }`: that is a busy spin. Do not assume one `OP_ACCEPT` corresponds to just one client; you can accept multiple available connections in one turn with a cap so the event loop continues serving other channels.

## 8. OP_CONNECT Does Not Mean TCP Is Connected Successfully

With a non-blocking `SocketChannel`:

```java
// Snippet: non-blocking client; remoteAddress and selector are available.
boolean connected = client.connect(remoteAddress);
if (connected) {
    client.register(selector, SelectionKey.OP_READ);
} else {
    client.register(selector, SelectionKey.OP_CONNECT);
}
```

When `key.isConnectable()`:

```java
// Snippet: valid key of a SocketChannel.
SocketChannel client = (SocketChannel) key.channel();
try {
    if (client.finishConnect()) {
        key.interestOps(SelectionKey.OP_READ);
    }
} catch (IOException failure) {
    key.cancel();
    client.close();
    // Report connection failure, apply controlled retry if needed.
}
```

`OP_CONNECT` means you can **attempt to finish** the connection state, not that the handshake succeeded. `finishConnect()` can return `false` if still unfinished or throw an exception when the connect fails. Until connected, **do not** start reading/writing the application protocol.

Distinguish an established TCP connection from **application-protocol completion** (TLS handshake, authentication, receiving a request...). Selector reports readiness at the channel layer; higher-level stages maintain their own state.

## 9. A Ready Event Is a Hint at Selection Time, Not a Long-Term Promise

Between `select()` and the actual operation, readiness can change. Common causes:

- Another thread or consumer already consumed data on the channel.
- The destination buffer is full or the input reader tries to read 0 bytes.
- The source buffer has run out of data to write, so being writable does not imply a response is still waiting to be sent.
- The peer closed the connection, the socket errored, or the channel was canceled/closed.
- Readiness on the same key was updated in another selection pass while the application still inspects stale bits due to mismanaging the selected-key set.

Therefore, handlers must inspect the returned count `n` instead of guessing from `isReadable()`/`isWritable()`. A ready signal also **does not guarantee any arbitrary I/O call on that channel can never block**: use proper non-blocking mode, the right operation type, and keep other blocking code out of handlers.

## 10. Write Loops and Handling Zero Progress

On a non-blocking channel, `write` can return 0 when no bytes are transferred. Wrong pattern:

```java
while (out.hasRemaining()) {
    socket.write(out); // Can keep returning 0; CPU spins endlessly.
}
```

Right pattern for a single readiness pass:

```java
while (out.hasRemaining()) {
    int n = socket.write(out);
    if (n == 0) {
        break; // Wait for the next appropriate OP_WRITE.
    }
}
if (out.hasRemaining()) {
    key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
} else {
    key.interestOps(key.interestOps() & ~SelectionKey.OP_WRITE);
}
```

Both are snippets. With a multi-buffer queue, logic should only remove `OP_WRITE` when the **entire queue** is empty, not just the current buffer. To avoid starvation, event loops typically enforce a byte or time cap per readiness event.

If buffers are produced by another thread, use a thread-safe queue and call `selector.wakeup()` to notify the event-loop thread to update interest/state. Never mutate the same `ByteBuffer` from two threads without clear ownership.

## 11. When Is a Request Complete?

A solid application defines clear completion criteria:

| Task | What Does Readiness Mean? | Application Completion Condition |
| --- | --- | --- |
| Receive 4-byte fixed header | `OP_READ` may yield partial bytes. | Accumulated all 4 bytes and decoded valid header. |
| Receive length-prefixed frame | `OP_READ` may yield partial or multiple frames. | Full header, bounded payload bytes arrived, validated. |
| Send 10 KiB response | `OP_WRITE` may perform partial write. | All outbound buffers `!hasRemaining()` or queue empty. |
| Open TCP connection | `OP_CONNECT` lets you try `finishConnect()`. | `finishConnect() == true`; on exception, connection failed. |
| Accept client | `OP_ACCEPT` signals possible pending connection. | Accepted and initialized required resources for each client. |
| TLS handshake | Readiness for socket read/write steps. | TLS state machine indicates handshake complete, not just writable socket. |

With TCP, even after `socket.write` consumes all application data, that **only** means bytes were accepted by the channel for sending per contract; it does not guarantee the peer received, processed, or committed them. When business confirmation is needed, design application-level ACKs, timeouts, request IDs, and retry/deduplication handling.

**Never use `selectedKeys().isEmpty()` or `select() > 0` as transaction completion criteria.** Those are merely states of the selection mechanism.

## 12. Protocol Framing and Memory Under Partial Reads

A protocol typically needs message framing. Three common approaches:

1. **Fixed-size:** each record is N bytes; read until N bytes accumulate, then process.
2. **Length-prefix:** header specifies payload length; validate length, enforce quota, and accumulate all bytes before decoding.
3. **Delimiter:** read until a delimiter character, capping length to protect against peers that never send the delimiter.

Parser example for 4-byte `int` records:

```java
// Snippet: input has received bytes in write mode.
input.flip();
while (input.remaining() >= Integer.BYTES) {
    int value = input.getInt(); // Relative read: consumes 4 bytes.
    handleValue(value);
}
input.compact(); // Retain 0..3 bytes for the next read turn.
```

This avoids `BufferUnderflowException` when only part of an integer has arrived. EOF with 1–3 leftover bytes indicates a truncated record (unless the protocol specifies otherwise).

When a frame carries an external length prefix, validate the length **before allocating** or stream with bounded limits. Abnormally large inputs, decompression bombs, very slow clients, or unbounded output queues can all exhaust memory even though the event loop remains "non-blocking."

## 13. Fairness, Backpressure, and Never Blocking the Event Loop

One event-loop thread manages many channels. Continuously draining an inexhaustible source on **one** busy client can starve other clients. Budgets are commonly set on:

- Maximum total bytes processed per readiness event.
- Maximum frames/work units per pass.
- Handler deadline or time budget.
- Maximum capacity of input frame buffers / outbound queues.
- Idle timeout, frame completion timeout, and minimum transfer rate.

If the outbound queue grows too large, apply **backpressure**: pause reading/accepting new messages for that connection, reject/throttle the producer, or close the client per policy. Never keep allocating unbounded buffers simply because the Selector keeps reporting ready reads.

Heavy CPU work, synchronous JDBC, blocking file I/O, and slow processing belong in a worker pool or appropriate asynchronous mechanism. The single-thread-for-many-channels model only shines when handlers are fast and never stalled by unrelated work.

## 14. `selectedKeys`: Removing Properly to Avoid Duplicate Processing

Event-loop pattern:

```java
// Snippet: selector and running are declared externally.
while (running) {
    selector.select();
    Iterator<SelectionKey> it =
            selector.selectedKeys().iterator();

    while (it.hasNext()) {
        SelectionKey key = it.next();
        it.remove();

        if (!key.isValid()) {
            continue;
        }
        if (key.isAcceptable()) {
            onAccept(key);
        }
        if (key.isValid() && key.isConnectable()) {
            onConnect(key);
        }
        if (key.isValid() && key.isReadable()) {
            onRead(key);
        }
        if (key.isValid() && key.isWritable()) {
            onWrite(key);
        }
    }
}
```

The handlers are application-defined methods, not a standalone program. `iterator.remove()` must execute after taking the key out of the selected-key set: the set does not auto-clear keys merely because a handler ran. Otherwise, old keys continue appearing, causing duplicate handling and making one readiness look like many distinct events.

A key can be reported ready for multiple ops at once. An earlier handler might close the channel or cancel the key, so re-check `isValid()` between steps that can change lifecycle state.

`selector.select()` can also return 0 due to wakeup, interrupt, close, or other API-permitted reasons. Never turn `select() == 0` into "peer disconnected" or an infinite spin loop; process pending tasks, shutdown, and timeouts according to application state.

## 15. Readiness APIs Are Not Completion APIs

Java provides several groups of abstractions:

| Group | Model | What the Application Must Do |
| --- | --- | --- |
| `Selector` + non-blocking `SocketChannel` | **Readiness**: picks channels capable of operating. | Call `read/write`, check `n`, keep state, loop as needed. |
| Blocking `InputStream`/`Socket` | Call may wait for data. | Still must loop to get N bytes; read does not promise filling the buffer. |
| `AsynchronousSocketChannel` | Submits async I/O request, receives completion via `Future`/`CompletionHandler`. | Handle actual completed byte count and continue to complete a frame. |
| `FileChannel` | File channel supporting positional I/O and buffers. | Cannot register as a `SelectableChannel` with a selector; still check partial transfers. |

Even with an async API's *completion callback*, a single completion may represent **only part** of a larger message. I/O call completion and application request completion do not necessarily coincide.

Do not switch to `AsynchronousSocketChannel` merely wanting "every event to always send the entire buffer"; applications still need framing, backpressure, timeouts, termination handling, and progress state.

## 16. Common Misconceptions

| Claim or Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| "`OP_READ` ⇒ full 1 request read." | TCP is a byte stream; data can fragment or coalesce. | Frame-based parser accumulating bytes via `remaining()`. |
| "`OP_WRITE` ⇒ entire response sent." | Socket may accept partial bytes or 0. | Loop on `hasRemaining()`, retain pending buffers. |
| "`OP_CONNECT` ⇒ TCP connected." | Needs `finishConnect()`; can fail. | Check return/exception before running protocol logic. |
| "`OP_ACCEPT` ⇒ always accepts a client." | Non-blocking `accept()` can return null. | Check for null, return to selector; allow accepting multiple clients. |
| "`write() > 0` ⇒ peer acknowledged data." | Channel only reports bytes consumed from send buffer. | Define application-level ACK if business guarantee is needed. |
| "If ready, read/write cannot return 0." | Readiness can change; not a byte-count guarantee. | Handle n==0 and wait for subsequent readiness. |
| "Keep calling write when it returns 0." | Busy-spin spikes CPU. | Break, keep state, wait for `OP_WRITE`. |
| "`clear()` after every read." | Loses incomplete frame bytes. | Use `compact()` to retain partial data. |
| "Use `capacity` to know remaining bytes." | After flip, `limit` is the valid boundary. | Use `remaining()` and `hasRemaining()`. |
| "Always enable `OP_WRITE` for all clients." | Sockets are usually writable even with no data. | Turn off when output queue is empty. |
| "An event loop can run large blocking tasks without affecting other clients." | Blocking the thread stalls all channels on that selector. | Budget work and offload blocking tasks to workers. |
| "`FileChannel` can register with `Selector`." | `FileChannel` does not implement `SelectableChannel`. | Use appropriate APIs for file I/O. |

## 17. Practice Exercises

**Exercise 1 — Accumulate a 10-byte frame.** Using `ByteBuffer.allocate(16)`, simulate four read passes: 3, 1, 4, and 2 bytes. After each pass, print `position/limit/remaining`; decode the frame only once all 10 bytes arrive. Explain why you cannot rely on the first `OP_READ`.

**Exercise 2 — Simulate partial writes.** Create an outbound buffer with 11 bytes. Cap each write to at most 3 bytes (using the demo's limit-shrinking technique). Count the passes required and verify the final content. Eleven bytes require **at least 4 write passes**; if the channel writes even less than the cap, the actual count may be higher.

**Exercise 3 — Replace Pipe with TCP.** Use non-blocking `ServerSocketChannel` and `SocketChannel` over local loopback. Implement `OP_ACCEPT`, `OP_READ`, `OP_WRITE`, and per-connection state. Have the client intentionally send one frame in two separate writes; the server must reply only after collecting all bytes.

**Exercise 4 — Avoid keeping OP_WRITE enabled unnecessarily.** Create a queue of two buffers. Enable `OP_WRITE` when the queue becomes non-empty, preserve the buffer if write returns 0, and remove `OP_WRITE` only after both buffers are exhausted. Check CPU usage while the server is idle.

**Exercise 5 — EOF mid-frame.** With a 4-byte header + payload protocol, have the sender close after 2 header bytes. Detect the truncation error without confusing EOF with `read == 0`. Add length bounds and timeouts to guard against incomplete client sends.

**Exercise 6 — Fairness across clients.** Create two channels: A continuously sends data while B occasionally sends short frames. Compare B's latency when A's handler drains bytes unboundedly vs. when it processes at most N bytes or M frames per selection pass.

**Exercise 7 — Completion vs. business ACK.** Draw a sequence diagram covering client `write` completion, server receiving bytes, server committing to a database, and server sending an ACK. Indicate where retries are safe and why an idempotency key is needed to prevent duplicate processing after a lost ACK.

### Self-Check Questions

1. Why can `isReadable() == true` still coincide with `read() == 0` or `read() == -1`?
2. Why does `isWritable()` not tell you how many bytes were sent or whether the peer received them?
3. A frame is 100 bytes but a read returns 60; what must you do with the missing 40 bytes?
4. Why should you call `compact()` instead of `clear()` when the parser has unprocessed bytes?
5. When should you set/clear the `OP_WRITE` bit in `interestOps`?
6. What condition actually proves `finishConnect()` is complete?
7. Does having one event loop with many channels automatically solve CPU-heavy handlers?
8. Does an async API's completion callback equate to a completed business request?

## 18. References

- [Java SE 21 — Selector](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html): readiness selection mechanics, key sets, and wakeup.
- [Java SE 21 — SelectionKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SelectionKey.html): ready/interest ops and registration state.
- [Java SE 21 — SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking connect/read/write, EOF, and byte transfer results.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): position, limit, remaining, flip, compact.
- [Java SE 21 — AsynchronousSocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousSocketChannel.html): completion handler/Future and asynchronous I/O.

**Remember:** `Selector` signals **an opportunity to perform I/O**, not confirmation that the operation completed. Success must be determined from **actual return values, remaining byte counts, protocol state, and business outcomes**. Preserve state across selection passes, avoid busy spinning, bound resources, and declare a request complete only when every condition is genuinely satisfied.
