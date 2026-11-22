# Write Queue Bounding and Read-Side Throttling for Slow Receivers with Java NIO Selector

In a TCP server using `Selector`, the ability to read data quickly does not mean the ability to send data to the peer is equally fast. When a peer receives slowly, `SocketChannel.write(ByteBuffer)` in non-blocking mode may write only part of the data or return `0`. If the application keeps reading, processing, and appending data to an **unbounded** outbound write list, each slow connection can hold more and more bytes in heap/direct memory and eventually exhaust the entire server's memory.

This lesson explains how to build **backpressure** in an NIO event loop: set a **hard cap** on the outbound queue, track unwritten bytes, enable `OP_WRITE` only when data is pending, temporarily remove `OP_READ` when the queue is high, and re-enable it when the queue drains. The ultimate goal is to preserve **correct data, correct ordering, bounded memory usage, and avoid busy-waiting CPU loops**, rather than simply calling `write()` as many times as possible.

The examples use **Java 17+**, non-blocking `SocketChannel`, `SelectionKey`, and `Selector`. Two complete programs later in this lesson demonstrate (1) watermarks with a simulated buffer and (2) a real TCP echo connection over loopback throttled by an event loop.

## 1. Data Flow and Why Backpressure Is Necessary

An echo server or a TCP proxy can be visualized as follows:

~~~text
TCP peer/sender
       │
       ▼
kernel receive buffer ── OP_READ ──► read(ByteBuffer)
                                        │
                                        ▼
                            process / build response
                                        │
                                        ▼
                             outbound queue [ByteBuffer...]
                                        │
                          OP_WRITE, partial write()
                                        ▼
                               kernel send buffer
                                        │
                                        ▼
                               slow-receiving TCP peer
~~~

If the data generation rate exceeds the rate at which `write` actually moves data into the kernel send buffer, the backlog grows. Let:

- `λ` (bytes/s): the rate at which the application produces outbound data.
- `μ` (bytes/s): the rate at which `SocketChannel.write` consumes data from the application queue.
- `Q` (bytes): the number of outbound bytes not yet consumed by `write`.

During a period where `λ > μ`, the queue grows approximately as `(λ−μ) × time` until throttling or a limit kicks in. For a hypothetical example with `λ = 5 MiB/s` and `μ = 1 MiB/s`, the backlog can grow at roughly `4 MiB/s`. After one minute, a single slow client alone can accumulate around 240 MiB of pending data at the application layer if unbounded. This is only an illustrative load calculation, not an exact prediction of TCP/OS behavior.

**Critical point:** `SocketChannel.write(...)` returns the number of bytes transferred **from the ByteBuffer to the channel/OS**, not the number of bytes the remote application has read. TCP, the kernel send buffer, the receiver window, and the network continue processing afterward. Therefore, `Q=0` does not mean the peer has received everything; it only means **the application's write queue** has currently been drained.

Three buffer layers must be distinguished:

| Layer | Who manages it? | What can throttle it? |
| --- | --- | --- |
| Read data buffer and parser state | Application | Frame size limits, input buffer limits, in-flight request limits |
| Outbound queue of unwritten `ByteBuffer`s | Application | Byte cap, high/low watermarks, full-queue policy, `OP_READ` |
| TCP send/receive buffers | Kernel/OS | TCP flow control, socket options such as `SO_SNDBUF` (hint), OS configuration |

`SO_SNDBUF` is not a substitute for bounding the outbound queue in heap. Nor can you "hard-lock memory" solely by disabling `OP_READ` if many tasks/responses have already been created beforehand.

## 2. API Foundations: Non-Blocking Write, Ready Set, and Interest Set

### 2.1. `SocketChannel.write(ByteBuffer)` Can Perform Partial Writes

Suppose a buffer has 1,000 remaining bytes:

~~~java
int written = channel.write(buffer);
~~~

You may receive `written=1000`, a smaller number, or `0`. `ByteBuffer.position()` advances by the exact number of bytes written, and `remaining()` reflects the unsent portion. **Do not `clear()` or `flip()` this buffer again** after a partial write; doing so corrupts the content and can cause duplicate sends or lost bytes.

Mechanism example:

~~~text
ByteBuffer: [ A B C D E F G H ]  position=0, limit=8
write() => 3
ByteBuffer: [ A B C | D E F G H ]  position=3, limit=8
write() => 0
ByteBuffer: [ A B C | D E F G H ]  position=3, limit=8
After OP_WRITE, write() => 5
ByteBuffer: [ A B C D E F G H | ] position=8, limit=8
~~~

Only when `remaining()==0` may the head buffer be removed from the queue. In NIO, **partial writes are normal behavior**, not an error. Repeatedly calling `write` in a loop when it returns `0` is busy-spinning; you must stop and let the `Selector` notify you of writability on a later turn.

### 2.2. `SelectionKey.OP_WRITE` Is Only a Readiness Interest Registration

Once a non-blocking channel is registered with a `Selector`:

~~~java
SelectionKey key =
        channel.register(selector, SelectionKey.OP_READ);
~~~

A `SelectionKey` has:

- **Interest set**: the operation bits the application wants `Selector` to monitor, read via `interestOps()`.
- **Ready set**: the operations the OS/selector marked as ready in the current `select` cycle, read via `readyOps()` or `isReadable()/isWritable()`.
- **Attachment**: an attached connection state object, such as an outbound queue.

Two common operations on Java 17 (available since Java 11):

~~~java
key.interestOpsOr(SelectionKey.OP_WRITE);    // add OP_WRITE
key.interestOpsAnd(~SelectionKey.OP_WRITE);  // remove OP_WRITE

key.interestOpsAnd(~SelectionKey.OP_READ);   // pause reading
key.interestOpsOr(SelectionKey.OP_READ);     // resume reading
~~~

These are **illustrative snippets inside a method** with a valid `SelectionKey key`. `interestOpsOr/And` perform the corresponding bit updates; if you use `key.interestOps(newOps)`, you must preserve the other required bits (`OP_CONNECT`, `OP_READ`, `OP_WRITE`) rather than overwriting them indiscriminately. Do not add `OP_ACCEPT` to a `SocketChannel`; that bit is for `ServerSocketChannel`.

**Important rule:** enable `OP_WRITE` only when the outbound queue is **non-empty**, and disable it immediately when the queue becomes empty. A TCP socket is typically marked writable most of the time. If `OP_WRITE` remains registered when there is no data to send, `select` can return continuously and drive a CPU core near 100% while the application sends nothing.

`OP_READ` can become ready when there is incoming data, EOF, peer shutdown, or a pending error. `OP_WRITE` can also signal readiness due to close/error events. Readiness does not guarantee that a `read/write` call will transfer bytes; you must still handle `0`, `-1`, and `IOException`.

### 2.3. The `Selector` Loop Must Handle Keys with Discipline

A typical event loop:

~~~java
selector.select(timeoutMillis);

Iterator<SelectionKey> it =
        selector.selectedKeys().iterator();
while (it.hasNext()) {
    SelectionKey key = it.next();
    it.remove();  // remove from selected set after retrieving
    if (!key.isValid()) {
        continue;
    }

    if (key.isReadable()) {
        onRead(key);
    }
    if (key.isValid() && key.isWritable()) {
        onWrite(key);
    }
}
~~~

This is **pseudocode placed inside an event loop**; `onRead/onWrite` must be defined. After `onRead`, the key may have been canceled/closed due to EOF or an error; therefore, you must re-check `isValid()` before checking `isWritable()`. When `select` returns `0` due to timeout/wakeup, handle timers or other pending work; do not assume the socket has an error.

If `OP_CONNECT` was registered for a non-blocking connect, you must call `finishConnect()` successfully before transitioning to read/write logic. The standalone program example below uses `ServerSocketChannel.accept()`, so the accepted channel is already connected and does not need an `OP_CONNECT` branch.

## 3. Bounded Outbound Queue: Bound by **Bytes**, Not Just Element Count

A simple per-connection structure:

~~~java
final Deque<ByteBuffer> outbound = new ArrayDeque<>();
long pendingBytes = 0;
~~~

When adding a buffer whose `position/limit` are already set properly:

~~~java
int bytesToAdd = data.remaining();
if (bytesToAdd > MAX_PENDING - pendingBytes) {
    // Do not enqueue: apply full-queue policy.
} else {
    outbound.addLast(data);
    pendingBytes += bytesToAdd;
}
~~~

This snippet is **pseudocode**: `data` must have clear ownership, and `MAX_PENDING` is the connection's cap. Comparing `bytesToAdd > MAX_PENDING - pendingBytes` avoids potential `int/long` addition overflow if the input is untrusted.

When `n` bytes are written:

~~~java
int n = channel.write(outbound.peekFirst());
pendingBytes -= n;

if (!outbound.peekFirst().hasRemaining()) {
    outbound.removeFirst();
}
~~~

Only decrement `pendingBytes` by **the number of bytes actually accepted by `write`**, not by `ByteBuffer.capacity()`, initial data length, message count, or `limit()`. When the queue still has a partially written head buffer, its `remaining()` represents the exact number of bytes left to send.

### 3.1. Invariants to Test

For each connection managed by an event-loop thread:

1. `0 <= pendingBytes <= MAX_PENDING`.
2. `pendingBytes == sum(buffer.remaining())` across all buffers currently in the outbound queue.
3. The `ByteBuffer` at the head of the queue always holds **the unwritten portion of data**; never `clear`/`flip` it indiscriminately.
4. When the queue is non-empty, `OP_WRITE` may be needed (if the socket is connected and still open).
5. When the queue is empty, `OP_WRITE` must be removed.
6. When reading is paused due to backpressure, **`OP_WRITE` must still remain enabled** so the backlog can drain and deadlock is avoided.
7. When reading is re-enabled, do not forget other pause conditions (shutdown, parser not ready, global memory pressure, application-level admission).

Bounding by *buffer count* does not replace bounding by *bytes*: 10 buffers could hold 10 KiB or 10 GiB depending on how they were allocated. Conversely, if many empty or tiny buffers are allowed, object overhead is still significant; production systems should also bound **entry count, frame size, pending tasks, and total server memory**.

For shared memory, you also need:
- `MAX_PENDING_PER_CONNECTION` for each client.
- `MAX_PENDING_GLOBAL` or a per-tenant budget for the entire event loop.
- Protection against a single peer monopolizing all direct/heap memory or socket count.
- Accounting for buffer capacity *outside the queue*: parser buffers, executor backlogs, in-flight responses, and TLS buffers if applicable.

## 4. High Watermark, Low Watermark, and Hard Cap

An illustrative policy:

~~~text
             outbound pendingBytes
  0 ─────── LOW ───────── HIGH ───────── MAX
           4 KiB          8 KiB         12 KiB
              ▲             ▲              ▲
              │             │              └─ Hard limit: do not allocate/enqueue more
              │             └──────────────── Temporarily disable OP_READ
              └────────────────────────────── Re-enable OP_READ once drained enough
~~~

Guidelines:
- **HIGH**: when `pendingBytes >= HIGH`, stop pulling more data from the source that generates output.
- **LOW**: when currently paused and `pendingBytes <= LOW`, resume reading.
- **MAX**: if an enqueue operation would exceed the limit, **do not allow it to exceed**. Reject, apply backpressure to the producer, close the connection, or apply another protocol-defined policy.

The condition `0 <= LOW < HIGH <= MAX` applies, and each read/frame receive must account in advance for what it might add to the queue. If you read a chunk up to 16 KiB when the queue only has 4 KiB of space left, "disabling `OP_READ` after reading" is already too late. You can:
- Allocate the read `ByteBuffer` with capacity ≤ `MAX - pendingBytes`.
- Set `HIGH` sufficiently below `MAX` by at least the maximum chunk/frame size.
- For processing that can **amplify data** (e.g., decoding and encoding a response larger than the request), **reserve output capacity for the worst-case size** or use queue/admission control before reading/processing.

### 4.1. Why Two Thresholds Instead of One?

If there is only a single threshold at 8 KiB, after writing just a few bytes, the server re-enables `OP_READ`, immediately reads a tiny bit more, and disables it again. This rapid toggling (*thrashing*) increases readiness churn and overhead.

With **hysteresis**:
- `pending = 8 KiB` → pause `OP_READ`.
- `pending = 7 KiB` → **stay paused**.
- `pending = 4 KiB` → resume `OP_READ`.
- After resuming, read up to HIGH before pausing again.

State diagram:

~~~text
  READING ─── pending >= HIGH ───► PAUSED_READ
     ▲                                │
     └────── pending <= LOW ──────────┘
              and reading is still allowed by policy
~~~

These are **application queue** thresholds, not kernel `SO_SNDBUF` thresholds. There is no single universally optimal LOW/HIGH pair; choose them based on connection count, traffic, frame size, memory limit, and latency budget. Setting HWM too high increases memory/latency; setting it too low can reduce throughput or cause excessive readiness transitions.

### 4.2. Handling a Full Queue

If a response cannot be enqueued in full, **never** append "just the first part" and silently drop the rest for a TCP protocol that requires integrity. Depending on the application contract:

| Policy | When appropriate | Risks to handle |
| --- | --- | --- |
| Pause producer / defer processing | Pipeline can pause and accepts backpressure | Needs a way to wake the producer when the queue drops to LOW; avoid deadlock |
| Return error and close socket cleanly | Protocol cannot tolerate missing data; peer is too slow | Track which data was already sent, handle idempotency and logging |
| Reject new requests | Server has admission control and an error response can be sent safely | Error responses are also outbound bytes and need their own allowance |
| Drop/coalesce new or old events | Only for **event streams that allow loss/coalescing** | Never use for general TCP byte streams or responses requiring integrity |
| Spill to disk | Batch/log systems with storage contracts and quotas | I/O, disk quota, ordering, crash recovery, and security |

True backpressure means **propagating the overload signal back to the producer**; merely capping the queue while continuing to read and generate unbounded responses into another executor only moves the memory leak to a different queue.

## 5. Basic Algorithm: `OP_READ` Produces Data, `OP_WRITE` Consumes Data

### 5.1. Handling a Readable Event

A callback should:
1. Check whether the session can accept more data.
2. Compute remaining capacity and bound the `ByteBuffer` for reading.
3. `read()` a bounded amount; handle `-1` as EOF and `0` by stopping.
4. Only after bytes are read, create an output buffer with proper ownership and enqueue it.
5. Enable `OP_WRITE` if the queue now has data.
6. Pause `OP_READ` when `pendingBytes >= HIGH`.

Pseudocode:

~~~java
void onReadable(SelectionKey key, State s) throws IOException {
    int available = MAX_PENDING - s.pendingBytes;
    if (available <= 0) {
        key.interestOpsAnd(~SelectionKey.OP_READ);
        return;
    }

    ByteBuffer input = ByteBuffer.allocate(
            Math.min(READ_CHUNK, available));
    int n = s.channel.read(input);

    if (n == -1) {
        s.inputEof = true;
        key.interestOpsAnd(~SelectionKey.OP_READ);
        // If the queue still has data, continue flushing before closing.
        return;
    }
    if (n == 0) return;

    input.flip();
    s.outbound.addLast(input);   // echo: input is output
    s.pendingBytes += n;
    key.interestOpsOr(SelectionKey.OP_WRITE);

    if (s.pendingBytes >= HIGH) {
        key.interestOpsAnd(~SelectionKey.OP_READ);
    }
}
~~~

The snippet above is **pseudocode depending on `State` and constants**; a standalone compilable example is in Section 8. For echo, output bytes equal input bytes. For HTTP, transcoding, encryption, or business logic, **output data is not necessarily the same size as input data**, so you cannot use an echo-style capacity formula without bounding response size.

### 5.2. Handling a Writable Event

When `key.isWritable()`:

~~~java
void onWritable(SelectionKey key, State s) throws IOException {
    int budget = WRITE_BUDGET_PER_EVENT;
    while (!s.outbound.isEmpty() && budget > 0) {
        ByteBuffer head = s.outbound.peekFirst();
        int n = s.channel.write(head);
        s.pendingBytes -= n;
        budget -= n;

        if (!head.hasRemaining()) {
            s.outbound.removeFirst();
        }
        if (n == 0) break;
    }

    if (s.outbound.isEmpty()) {
        key.interestOpsAnd(~SelectionKey.OP_WRITE);
    }

    if (!s.inputEof && s.pendingBytes <= LOW
            && s.readWasPaused) {
        key.interestOpsOr(SelectionKey.OP_READ);
        s.readWasPaused = false;
    }
}
~~~

This is **pseudocode** for the conceptual flow, not a standalone runnable class. There is a subtle detail when applying `WRITE_BUDGET_PER_EVENT`: `SocketChannel.write(head)` can transfer **more than the remaining budget** if `head.remaining()` is large, so production code must temporarily cap `ByteBuffer.limit` or write a partial slice matching the budget, as shown in `SelectorBackpressureLoopback` below. If you omit a strict fairness budget, you can write the full `head.remaining()`, but you should still bound the number of calls/bytes processed so one connection does not monopolize the event loop.

Never do `pendingBytes -= head.capacity()` after a partial write. Doing so makes the counter negative or triggers a premature resume. If `write` returns `0`, preserve `position`, **keep `OP_WRITE`**, and return to the selector.

### 5.3. Never Stop the Consumer When the Queue Is High

A dangerous logic bug:

~~~java
if (pendingBytes >= HIGH) {
    key.interestOps(0);  // WRONG: disables both READ and WRITE
}
~~~

In this case, the queue may never drain because `OP_WRITE` is no longer registered to drain it. The right approach is to **remove only `OP_READ`** when the producer needs to pause; `OP_WRITE` must remain monitored while pending data exists.

Conversely, when the queue is empty, remove `OP_WRITE`. Do not leave `OP_READ` disabled forever once the queue drops to LOW; otherwise, the connection may stall even though the peer is still sending data.

## 6. First Java 17+ Program: Simulating Watermarks and Partial Consumption

The following program **does not open any sockets**. It simulates an outbound queue with `Deque<ByteBuffer>`, checks admission before enqueueing, and consumes a fixed number of bytes per turn. The strength of this example is that stdout is **completely deterministic**, helping verify watermark logic without depending on OS/network speeds.

Create **`QueueWatermarksDemo.java`**:

~~~java
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class QueueWatermarksDemo {
    private static final int HIGH = 8;
    private static final int LOW = 3;
    private static final int MAX = 12;
    private final Deque<ByteBuffer> queue = new ArrayDeque<>();
    private int pending;
    private boolean readPaused;

    public boolean enqueue(String text) {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX - pending) return false;
        queue.addLast(ByteBuffer.wrap(bytes));
        pending += bytes.length;
        if (pending >= HIGH) readPaused = true;
        return true;
    }

    public void drain(int budget) {
        while (budget > 0 && !queue.isEmpty()) {
            ByteBuffer head = queue.peekFirst();
            int moved = Math.min(budget, head.remaining());
            head.position(head.position() + moved);
            pending -= moved;
            budget -= moved;
            if (!head.hasRemaining()) queue.removeFirst();
        }
        if (pending <= LOW) readPaused = false;
    }

    private void print(String label) {
        System.out.println(label + ": pending=" + pending +
                ", readPaused=" + readPaused);
    }

    public static void main(String[] args) {
        QueueWatermarksDemo q = new QueueWatermarksDemo();
        System.out.println("A accepted: " + q.enqueue("ABCDE"));
        q.print("after A");
        System.out.println("B accepted: " + q.enqueue("1234"));
        q.print("after B");
        System.out.println("C accepted: " + q.enqueue("xxxxx"));
        q.drain(3);
        q.print("after drain 3");
        q.drain(3);
        q.print("after drain 6");
        q.drain(3);
        q.print("after drain 9");
    }
}
~~~

Run:

~~~bash
javac --release 17 QueueWatermarksDemo.java
java QueueWatermarksDemo
~~~

Exact stdout:

~~~text
A accepted: true
after A: pending=5, readPaused=false
B accepted: true
after B: pending=9, readPaused=true
C accepted: false
after drain 3: pending=6, readPaused=true
after drain 6: pending=3, readPaused=false
after drain 9: pending=0, readPaused=false
~~~

How to read it:
- Message A is 5 bytes, below HIGH=8, so reading stays enabled.
- B is 4 bytes; `pending=9 >= HIGH`, so the application decides to pause reading.
- C is 5 bytes; enqueueing it would make 14 > MAX=12, so it is **rejected in full**, preventing the queue from exceeding the cap.
- After draining 3 bytes, pending is 6, still paused because it has not dropped to LOW=3.
- After draining 3 more bytes, pending reaches 3 and transitions back to unpaused.
- A total of 9 bytes have been consumed; the queue is empty, pending=0.

This `drain` method **only simulates `ByteBuffer` progress** and does not call `SocketChannel.write`. In a real server, pending must decrease by **the return value of `write`**, and pausing must update the `SelectionKey`. Do not use a simulated `drain` method to "send" real TCP data.

## 7. Complete Event Loop: Invariants to Preserve in Non-Blocking Mode

Before looking at a runnable network example, understand the state design:

~~~text
ConnectionState
  channel            non-blocking SocketChannel
  outbound           Deque<ByteBuffer>
  pendingBytes       sum of remaining() in outbound
  inputEof           has read() == -1 been seen?
  pauseCount         number of times OP_READ was removed
  resumeCount        number of times OP_READ was re-enabled
  peakBytes          observed peak pendingBytes
~~~

Required operations:

- **Accept:** `ServerSocketChannel.accept` can return `null` on a non-blocking listener; configure the accepted channel as non-blocking and register `OP_READ` with its own attachment.
- **Read:** process only a bounded number of bytes per event; if `read==-1`, stop reading further, but keep outbound data until it finishes flushing.
- **Write:** preserve `ByteBuffer.position` after a partial write, do not remove a buffer while it still has `remaining`; do not remove `OP_WRITE` while the queue is non-empty.
- **Pause:** when the backlog is high, remove only `OP_READ`, keeping `OP_WRITE`.
- **Resume:** only when the backlog ≤ LOW and the connection is still allowed to read; never re-enable `OP_READ` after EOF.
- **Close:** if the peer has half-closed input and outbound has finished flushing, close the channel. If the connection still needs to send a response after the client has shut down output, allow it to finish sending before closing.
- **Cleanup:** `SelectionKey.cancel()`, close the channel, and handle invalidated selected keys in the event loop.

**TCP is a byte stream and does not preserve message boundaries.** The next example only echoes bytes, so it needs no parser. For frame-based protocols such as length-prefixed frames, you must retain the parser buffer across multiple `read` calls and **validate frame size before allocating output**. Disabling `OP_READ` must not discard a partially read frame mid-stream.

## 8. Second Java 17+ Program: Selector TCP Echo with a Real Bounded Queue

This example runs **both server and client over loopback in the same JVM**, requiring no external tools. The client sends 4,096 `'x'` bytes, shuts down its output side, and then reads the echo. The server uses `ServerSocketChannel` + `Selector` + non-blocking `SocketChannel` with a per-connection outbound queue.

To **observe pause/resume in a short test without relying on the kernel happening to back up**, the program **deliberately caps the bytes processed per writable event at 128 bytes**. This is a **throttle simulating a slow application-layer consumer**, not proof that the OS send buffer is full. On a real system, `write` can return `0` or perform partial writes due to TCP backpressure; the queue and `interestOps` management logic remains the same.

Create **`SelectorBackpressureLoopback.java`**:

~~~java
import java.io.*;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.util.*;
import java.util.concurrent.*;

public class SelectorBackpressureLoopback {
    private static final int READ_CHUNK = 512;
    private static final int HIGH = 1024;
    private static final int LOW = 512;
    private static final int MAX_PENDING = 2048;
    private static final int WRITE_BUDGET = 128;

    private static final class Session {
        final SocketChannel channel;
        final Deque<ByteBuffer> outbound = new ArrayDeque<>();
        int pendingBytes;
        int peakBytes;
        int paused;
        int resumed;
        boolean eof;
        Session(SocketChannel channel) { this.channel = channel; }
    }

    private static void onRead(SelectionKey key) throws IOException {
        Session s = (Session) key.attachment();
        int free = MAX_PENDING - s.pendingBytes;
        if (free <= 0) {
            key.interestOpsAnd(~SelectionKey.OP_READ);
            return;
        }
        ByteBuffer buffer =
                ByteBuffer.allocate(Math.min(READ_CHUNK, free));
        int read = s.channel.read(buffer);
        if (read == -1) {
            s.eof = true;
            key.interestOpsAnd(~SelectionKey.OP_READ);
            if (s.outbound.isEmpty()) {
                key.cancel();
                s.channel.close();
            }
            return;
        }
        if (read == 0) return;
        buffer.flip();
        s.outbound.addLast(buffer);
        s.pendingBytes += read;
        s.peakBytes = Math.max(s.peakBytes, s.pendingBytes);
        key.interestOpsOr(SelectionKey.OP_WRITE);
        if (s.pendingBytes >= HIGH) {
            key.interestOpsAnd(~SelectionKey.OP_READ);
            s.paused++;
        }
    }

    private static void onWrite(SelectionKey key) throws IOException {
        Session s = (Session) key.attachment();
        int budget = WRITE_BUDGET;
        while (budget > 0 && !s.outbound.isEmpty()) {
            ByteBuffer head = s.outbound.peekFirst();
            int originalLimit = head.limit();
            head.limit(head.position()
                    + Math.min(head.remaining(), budget));
            int written;
            try {
                written = s.channel.write(head);
            } finally {
                head.limit(originalLimit);
            }
            s.pendingBytes -= written;
            budget -= written;
            if (!head.hasRemaining()) s.outbound.removeFirst();
            if (written == 0) break;
        }
        if (s.outbound.isEmpty()) {
            key.interestOpsAnd(~SelectionKey.OP_WRITE);
        }
        if (!s.eof && s.pendingBytes <= LOW
                && (key.interestOps() & SelectionKey.OP_READ) == 0) {
            key.interestOpsOr(SelectionKey.OP_READ);
            s.resumed++;
        }
        if (s.eof && s.outbound.isEmpty()) {
            key.cancel();
            s.channel.close();
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        byte[] payload = new byte[4096];
        Arrays.fill(payload, (byte) 'x');
        try (Selector selector = Selector.open();
             ServerSocketChannel listener = ServerSocketChannel.open()) {
            listener.bind(new InetSocketAddress(loopback, 0));
            listener.configureBlocking(false);
            listener.register(selector, SelectionKey.OP_ACCEPT);
            int port =
                    ((InetSocketAddress) listener.getLocalAddress())
                            .getPort();

            FutureTask<byte[]> clientJob = new FutureTask<>(() -> {
                try (Socket client = new Socket(loopback, port)) {
                    client.setSoTimeout(5000);
                    client.getOutputStream().write(payload);
                    client.shutdownOutput();
                    return client.getInputStream()
                            .readNBytes(payload.length);
                }
            });
            new Thread(clientJob, "loopback-client").start();

            Session session = null;
            long deadline = System.nanoTime()
                    + TimeUnit.SECONDS.toNanos(10);
            while (System.nanoTime() < deadline
                    && (session == null || session.channel.isOpen())) {
                selector.select(100);
                Iterator<SelectionKey> it =
                        selector.selectedKeys().iterator();
                while (it.hasNext()) {
                    SelectionKey key = it.next();
                    it.remove();
                    if (!key.isValid()) continue;
                    if (key.isAcceptable()) {
                        SocketChannel accepted = listener.accept();
                        if (accepted != null) {
                            accepted.configureBlocking(false);
                            session = new Session(accepted);
                            accepted.register(
                                    selector, SelectionKey.OP_READ, session);
                        }
                    } else {
                        if (key.isReadable()) onRead(key);
                        if (key.isValid() && key.isWritable()) onWrite(key);
                    }
                }
            }
            if (session == null || session.channel.isOpen()) {
                throw new IOException("Server did not finish");
            }
            byte[] echoed = clientJob.get(5, TimeUnit.SECONDS);
            System.out.println("echo matches: " +
                    Arrays.equals(payload, echoed));
            System.out.println("queue within cap: " +
                    (session.peakBytes <= MAX_PENDING));
            System.out.println("read paused: " + (session.paused > 0));
            System.out.println("read resumed: " + (session.resumed > 0));
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 SelectorBackpressureLoopback.java
java SelectorBackpressureLoopback
~~~

**When the OS allows creating and exchanging TCP traffic over loopback within the test timeout**, the verified stdout is:

~~~text
echo matches: true
queue within cap: true
read paused: true
read resumed: true
~~~

Detailed explanation:

1. `MAX_PENDING=2048` and `READ_CHUNK=512`. Before each read, the code computes `free = MAX_PENDING-pendingBytes`, so a single read cannot push the queue past the hard cap.
2. Each incoming read allocates its own `ByteBuffer`, calls `flip()`, and appends it to the queue. The `ByteBuffer` is "owned" by the outbound queue until written completely; unconsumed data is never overwritten.
3. `onRead` enables `OP_WRITE` because there is new output. When pending reaches `HIGH=1024`, it **removes `OP_READ`**.
4. `onWrite` processes at most 128 bytes per writable event. To enforce the budget accurately, it sets a **temporary `limit`** on the `ByteBuffer` and restores `limit` in `finally`, without losing `position` after a partial write.
5. `pendingBytes` is decremented by the exact `written` count, not `head.capacity()`. Only buffers with `remaining()==0` are dequeued.
6. When the queue becomes empty, `OP_WRITE` is removed to avoid CPU spin. When pending drops to `LOW=512` and EOF has not been reached, `OP_READ` is re-enabled.
7. The client calls `shutdownOutput()` to signal it has finished sending the request while still reading the echo. The server observes `read==-1` and **does not close before flushing outbound**; it closes the channel only after flushing.
8. The test compares **all 4,096 bytes**: a byte count alone is not enough to detect out-of-order data, so `Arrays.equals` guarantees both content and order are intact.
9. `peakBytes<=MAX_PENDING` verifies the per-connection bound during the run; `paused/resumed>0` proves the demo actually exercised both backpressure branches.

This is a **single-connection bounded demo**. For a production server, you must add: management of multiple accepted channels, catching and closing individual connections on `IOException`, server-wide global limits, parser/frame policies, executor handoff, metrics, timeout/idle deadlines, and handling shutdowns that may occur while blocked in `select`. Do not drop a loopback self-test straight into production assuming you have a complete multi-client server.

## 9. Two Different Roles of `OP_READ` in an Echo Server vs. a TCP Proxy

### 9.1. Single-Channel Echo Server

In an echo server, the same `SocketChannel` receives data and writes the echo back to **the same peer**. When the outbound queue reaches HIGH, disable `OP_READ` on **that channel's key**. Thus, the application stops consuming new data from the peer while `OP_WRITE` continues draining the backlog.

~~~text
client ──► server SocketChannel (READ) ──► echo queue ──► same channel (WRITE) ──► client
                        ▲                     │
                        └── pause/resume ◄────┘
~~~

### 9.2. Two-Channel Proxy

A proxy has an **upstream socket A** and a **downstream socket B**, typically with separate queues for each direction. If **B cannot be written to**, B's outbound queue grows; what needs to be paused is **A's `OP_READ`**, because reading from A is what produces bytes for B.

~~~text
A (source) ── OP_READ ──► queue pending-for-B ── OP_WRITE ──► B (slow receiver)
     ▲                                │
     └────── pause A when HIGH ───────┘
     └────── resume A when LOW ◄──────┘
~~~

Do not just disable `OP_READ` on B while letting A keep feeding `queue B`. That applies backpressure in the wrong direction, and the backlog keeps growing. In a bidirectional proxy, each direction has an independent relationship:

| Growing queue | Producer to pause | Consumer that must stay active |
| --- | --- | --- |
| A → B outbound queue for B | `OP_READ` of A | `OP_WRITE` of B |
| B → A outbound queue for A | `OP_READ` of B | `OP_WRITE` of A |

Be careful with dependencies and **half-close** between the two sockets: when A reaches EOF on its read side, the proxy must still flush A→B data; afterward, it can call `shutdownOutput` on B according to the protocol to propagate EOF without closing the still-active reverse direction B→A. Do not close both sockets immediately when one side reads `-1` if responses in the reverse direction are still needed.

### 9.3. Non-Proxy Applications

In an HTTP/RPC server, the producer may be a worker task completing a response rather than `OP_READ` directly. When a client receives slowly, backpressure must be applied to the **response producer** (future, stream, callback, upstream request), not just by disabling read. If a multiplexed protocol allows multiple independent requests on the same connection, pause logic must consider all related resources and per-stream control; you may need the protocol's own flow-control mechanism instead of locking the entire socket.

## 10. Event-Loop Fairness: Do Not Let One Client Starve Everyone Else

Bounding memory is one part; preventing starvation also requires **bounding work per selected key**:

- `MAX_READ_BYTES_PER_EVENT`: read at most N bytes or M chunks per turn. If more data remains, return to the selector to serve other connections.
- `MAX_WRITE_BYTES_PER_EVENT`: write at most K bytes per turn. The demo uses 128 bytes for testing, while production tunes this for real throughput/latency.
- `MAX_FRAMES_PER_EVENT` or a time budget for the parser, avoiding processing millions of tiny frames from one connection.
- Never perform database calls, blocking file I/O, or heavy CPU work directly on the selector thread.
- Avoid busy-spinning `while (channel.write(buffer)==0)` or `while (channel.read(buf)==0)`.
- Monitor selector event-loop lag, ready key counts, processing time per key, and clients paused for too long.

Without a per-event write limit, a connection with a constant backlog can monopolize the event loop, delaying other connections even when their queues are small. If the budget is too low, throughput drops noticeably and `select` calls increase. This is an empirical trade-off and should be measured under real workloads.

## 11. Communicating with Worker Threads: Ownership and `selector.wakeup()`

The loopback example modifies the queue and `interestOps` on **a single selector thread**, so there is no race between producer and consumer. In real systems, responses may be generated on worker threads. Never let multiple threads mutate `ArrayDeque<ByteBuffer>`, `pendingBytes`, and `SelectionKey.interestOps(...)` without a synchronized protocol.

A solid management pattern:

~~~text
worker thread
    │
    ├── build response or signal "response ready"
    ├── submit task to event-loop's concurrent controlQueue
    └── selector.wakeup()
                        │
                        ▼
                selector event-loop thread
                        │
                        ├── poll control tasks
                        ├── check admission and memory cap
                        ├── enqueue ByteBuffer with clear ownership
                        ├── enable OP_WRITE if needed
                        └── adjust OP_READ per watermarks
~~~

`selector.wakeup()` wakes up a blocked `select` operation (or causes the next `select` call to return immediately per its contract). It **does not automatically add a `ByteBuffer` to the outbound queue**, nor does it automatically enable `OP_WRITE`. A concrete pattern in a worker:

~~~java
controlQueue.add(() -> enqueueResponseOnEventLoop(key, response));
selector.wakeup();
~~~

This snippet is **pseudocode**, where `controlQueue` is a thread-safe queue and `enqueueResponseOnEventLoop` executes only on the event-loop thread. Ownership of `response` must be transferred before the worker moves on to other work—for example, by copying `byte[]` or using an immutable buffer. The event loop must drain control tasks whenever woken up, not only when there are selected keys.

Modifying `interestOps` while another thread is in `select` takes effect on the next selection per the Javadoc; therefore, avoid "enabling `OP_WRITE` without a wakeup" while the event loop is sleeping on a long timeout. If multiple threads update bits, use `interestOpsOr/And` for atomic bit updates, **but you still must synchronize queue state and key lifecycle**.

## 12. Choosing a Policy When a Slow Peer Does Not Recover

Backpressure keeps server resources bounded, but **it cannot guarantee that an extremely slow reader will finish a request on time**. Production systems need additional deadlines and handling policies:

1. **Bounded write queue**: reject enqueues if per-client/global hard caps are exceeded.
2. **Write-progress deadline**: if no additional bytes are written for too long while the queue still has data, close the connection per contract.
3. **Maximum paused duration**: if `OP_READ` stays paused for too long, log a warning or disconnect after a grace period.
4. **Response timeout/stream deadline**: prevent a single request from holding resources indefinitely.
5. **Per-client fairness/quotas**: protect other users from a slow peer.
6. **Clean disconnect**: cancel the key, close the channel, release queues/buffers, and cancel pending producer tasks. Never enqueue into a closed session.

No single timeout value fits every service. Choose values based on SLA, response size, WAN/LAN environment, minimum acceptable throughput, and protocol resume capabilities. Closing a socket after sending part of a response can leave the client with a **partial payload**; the protocol needs framing/checksums or error semantics to detect this.

### 12.1. Never Arbitrarily Drop TCP Bytes

TCP guarantees an ordered byte stream while the connection is open, so the application must **never** silently drop bytes from the outbound queue to save memory. If the server truncates a payload mid-stream, the remote application sees a corrupted protocol or incomplete data. Dropping is only appropriate when the application protocol is **explicitly designed** with the semantics that "this message may be dropped," such as latest-state snapshots that supersede older snapshots.

If a complete response cannot be enqueued and the producer cannot be paused, you may need to fail the request/connection. Choose an explicit rule instead of letting `OutOfMemoryError` decide.

### 12.2. Caution with TLS and HTTP

With `SSLEngine`, the queue may hold **encrypted application records** alongside separate plain/network buffers. `wrap/unwrap` can produce more output than input and require handshake progress even when application payloads are paused. Do not directly apply echo's "reading N bytes produces N outbound bytes" formula to TLS. Account for total memory and handshake state; avoid deadlocks caused by blocking reads too early while `SSLEngine` still needs to receive TLS records.

HTTP/2 or other multiplexed protocols have stream/connection-level flow control. You may need to coordinate those flow-control windows rather than only toggling `OP_READ`/`OP_WRITE` on the TCP channel. The ultimate goal remains coupling the **producer → queue → consumer** rates within resource bounds.

## 13. Observing and Testing Backpressure

### 13.1. Metrics to Measure

| Metric | Meaning |
| --- | --- |
| `outbound_pending_bytes` per-connection | Bytes remaining in the queue to write |
| `outbound_pending_bytes_global` | Total queued bytes across the server/tenant |
| `queue_peak_bytes` | Peak backlog, compared against caps and memory budgets |
| `read_paused_connections` | Number of connections with `OP_READ` removed by backpressure |
| `read_pause_duration_ms` | Duration reading has been paused, helping detect slow peers |
| `nonblocking_write_zero_count` | Number of times `write` returned `0` while the queue had data |
| `write_progress_bytes/s` | Rate at which the OS/channel accepts data from the app |
| `selector_loop_delay_ms` | Event-loop lag, helping detect CPU-bound handlers |
| `queue_overflow_rejections` | Number of responses/requests rejected due to the hard cap |
| `connection_closes_slow_peer` | Number of connections closed due to overly slow peers |

Do not measure queue length only by element count. Do not treat `write_progress_bytes/s` as the rate at which the remote side has processed business logic. Record useful dimensions (protocol, endpoint, state) without creating unbounded metric cardinality using every peer's IP/port.

### 13.2. Mandatory Test Cases

| Scenario | Expectation |
| --- | --- |
| Fast-reading peer, empty queue | `OP_WRITE` is not registered when there is no data |
| `write` accepts only part of buffer | Head buffer retains remaining bytes; data order is intact |
| `write` returns `0` | No busy-spin; keep `OP_WRITE` and data |
| Pending reaches HIGH | Only the corresponding producer's `OP_READ` is removed |
| Pending decreases but still > LOW | Reading is not re-enabled yet |
| Pending <= LOW | Re-enable `OP_READ` if session allows and not EOF |
| Pending would exceed MAX | Reject/defer **before** allocation/enqueue; never exceed cap |
| Peer sends EOF while outbound remains | Flush already-created data before closing/half-closing per protocol |
| Channel/key closed/canceled | Stop enqueueing/updating `interestOps`; clean up queues and tasks |
| One very slow client, many fast clients | Slow client causes neither unbounded memory growth nor starvation |
| Multiple producer threads | Data is not overwritten; queue ownership and wakeups are correct |
| Parser receives oversized frame | Do not allocate unbounded frames even if `OP_READ` throttling is active |

### 13.3. Building a Slow-Receiver Test Without Relying on Luck

A real network test can:
- Make the client **read intentionally slowly** (sleep between reads) with a sufficiently large payload.
- Set a small `SO_RCVBUF` on the receiver side to help reproduce backpressure, though this is only a hint and results vary by OS.
- Send many large responses and monitor `pendingBytes`, pause time, and write-zero count.
- Set a deadline so the test cannot hang forever; use loopback for functional tests and a controlled network environment for benchmarks.
- Verify invariants on total byte count and content hash, not just "the server stayed alive."
- Run on all JDKs/OSes supported in production; kernel buffering and scheduling make the exact timing of partial writes/`0` returns non-deterministic.

The `SelectorBackpressureLoopback` example intentionally uses a 128-byte write budget **per event**, allowing pause/resume branches to be tested deterministically **without waiting for the OS to back up**. That tests the throttling logic; real integration tests still need a slow-reading peer and real socket buffers.

## 14. Common Mistakes

**Mistake 1: enabling `OP_WRITE` from the start for every connection.** Since sockets are frequently writable, the event loop can spin CPU continuously. Enable it only when data is pending; disable it when the queue is empty.

**Mistake 2: calling `while(buffer.hasRemaining()) channel.write(buffer)` without checking `0`.** If the OS accepts no more bytes, the loop becomes a busy-spin. Stop when `write==0` and wait for writability readiness.

**Mistake 3: removing a buffer from the queue after a single `write`.** Non-blocking writes can be partial; keep the buffer until `remaining()==0`.

**Mistake 4: clearing all interest bits when the queue is full.** Disabling `OP_WRITE` as well prevents the queue from draining and can deadlock the connection.

**Mistake 5: bounding only by message count.** A single message can be huge. You must bound byte queues, frame lengths, and pending tasks.

**Mistake 6: treating the high watermark as the hard cap without accounting for chunk size.** If pending is near the cap and you read a large chunk before checking, you have already exceeded the cap. Compute free bytes **before reading/enqueueing**.

**Mistake 7: re-enabling `OP_READ` as soon as pending drops by one byte.** Causes rapid toggling; use a LOW watermark below HIGH.

**Mistake 8: disabling reads on the wrong socket in a TCP proxy.** When B is slow, you must pause source A that feeds B's outbound queue, not just pause B.

**Mistake 9: confusing `SO_SNDBUF` with the application memory budget.** The OS buffer is a separate layer; `SocketChannel.write` may accept bytes into the kernel while the remote side has not processed them.

**Mistake 10: a worker thread mutating the queue and `interestOps` directly while the selector thread is running.** Can cause races, lost wakeups, or double enqueues. Use a single event-loop owner and a thread-safe command queue.

**Mistake 11: closing immediately on `read==-1` even when responses remain in the queue.** Loses already-generated data; drain first if the protocol requires it.

**Mistake 12: failing to remove processed keys from `selectedKeys()` or failing to check `isValid()`.** Can cause repeated processing or invalid state after close, breaking the event loop.

## 15. Self-Check Exercises

**Question 1.** A non-blocking `SocketChannel` has 1,000 bytes in a `ByteBuffer`; `write` returns 300. Can it be dequeued immediately?  
**Answer:** No. There are 700 bytes `remaining()`; keep the buffer and continue when writable.

**Question 2.** Why does keeping `OP_WRITE` enabled continuously when the queue is empty cause high CPU?  
**Answer:** The socket may constantly report writable, causing `select` to return repeatedly even when there is no data to send.

**Question 3.** The queue currently holds 900 bytes; HIGH=1,024, MAX=1,280. Can you read another 512-byte chunk and check afterward?  
**Answer:** No. The chunk exceeds the 380 bytes of remaining space before MAX. You must cap the read to ≤380 bytes or defer it.

**Question 4.** HIGH=8 KiB, LOW=4 KiB, pending drops from 10 to 7 KiB. Should `OP_READ` be resumed yet?  
**Answer:** Not yet, because it is paused and pending is still > LOW.

**Question 5.** B receives slowly in an A→B proxy. Which `OP_READ` needs to be paused?  
**Answer:** `OP_READ` on A, the source of data entering B's outbound write queue; keep `OP_WRITE` enabled on B.

**Question 6.** `channel.write(buffer)` returns `0`. Does that mean the remote side closed or errored?  
**Answer:** Not necessarily. The OS may simply not accept more bytes right now; keep the data and wait for writability. Close/error states must be checked through the appropriate APIs and exceptions.

**Question 7.** Does `pendingBytes==0` prove the remote side received the entire response?  
**Answer:** No. It only proves the application queue is empty because the bytes have been transferred to the channel/OS.

**Question 8.** A client sends EOF while the server still has queued data. Should the server close immediately?  
**Answer:** Not by default. For protocols that must finish sending responses, stop reading, keep writing, flush outbound data, and only then close/half-close as designed.

**Question 9.** Is a 1 MiB per-client queue limit enough to protect a server with 100,000 clients?  
**Answer:** No. The potential total is ~100 GiB before even counting object overhead or input/task buffers; you need a global budget and connection admission control.

**Question 10.** A worker task just built a response while the selector is blocked in `select`. Is calling `selector.wakeup()` enough to enqueue it?  
**Answer:** No. You must pass the response/command through a thread-safe queue, wake up the selector, and have the event-loop owner actually enqueue it and enable `OP_WRITE`.

## 16. Production Checklist

1. Identify the **producer** of each outbound queue and its corresponding consumer; in a proxy, do not pause the wrong side.
2. Set per-connection **MAX_PENDING**, a global budget, and input/frame/task limits.
3. Track `pendingBytes = Σ outbound.remaining()`; update using actual bytes accepted by `write`.
4. Use `LOW < HIGH <= MAX`; pause the source at HIGH and resume only at LOW.
5. Ensure read-chunk/frame sizes cannot push the queue past MAX **before enqueueing**.
6. Enable `OP_WRITE` only when the queue has data; remove it immediately when empty.
7. Handle `write==0`, partial writes, `read==0`, `read==-1`, and `IOException`; never busy-spin.
8. Preserve `ByteBuffer` `position`/`limit`, ownership across worker threads, and byte-stream ordering.
9. Enforce per-event byte/time budgets so one connection cannot monopolize the event loop.
10. Design clear overload policies, slow-peer timeouts, EOF/half-close handling, and cleanup.
11. Measure peak queue size, pause duration, blocked writes, global memory, and loop lag.
12. Test with slow-reading peers, multiple clients, key errors/cancellations, and target JVMs/OSes.

## Official Documentation

- [Java SE 17 — `SocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): `read`/`write` in non-blocking mode, partial/zero-byte I/O, EOF, connection, and half-close.
- [Java SE 17 — `SelectionKey`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectionKey.html): `OP_READ`, `OP_WRITE`, interest/ready sets, `interestOpsAnd` and `interestOpsOr`, key validity.
- [Java SE 17 — `Selector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): `select`, `selectedKeys`, cancellation, `wakeup`, and concurrency rules.
- [Java SE 17 — `ServerSocketChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ServerSocketChannel.html): non-blocking `accept` and registration.
- [Java SE 17 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `remaining`, `flip`, and data ownership.
- [Java SE 17 — `StandardSocketOptions`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/StandardSocketOptions.html): `SO_SNDBUF` and OS socket buffer limits.

**Core principle:** **bound queues by byte count, never drop pending data; register `OP_WRITE` only when needed; pause the right source with `OP_READ` at HIGH and resume at LOW; for overly slow peers, enforce clear overload policies and deadlines.**
