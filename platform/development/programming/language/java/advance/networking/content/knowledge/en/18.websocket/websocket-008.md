# WebSocket: Ordered Send Chains and Pending Operation Limits in Java 17+

A WebSocket connection allows a Java application to send and receive multiple messages without reopening an HTTP request for each communication. However, **a `sendText(...)` call is not a completed synchronous write**, and **multiple producer threads calling `sendText(...)` concurrently do not automatically form a safe, bounded queue**. If the client sends faster than the network can transfer data, backlog can accumulate in the application; if a text/binary send is invoked while the previous text/binary operation has not finished, the JDK 17 `java.net.http.WebSocket` API may return a `CompletableFuture` that completes exceptionally with `IllegalStateException`.

This lesson focuses on two requirements of a reliable outbound WebSocket client:

1. **In order:** establish **business order**, starting the next text/binary send operation only after the previous one completes successfully; avoid accidental concurrent sends, out-of-order delivery, and interleaving message fragments.
2. **Bounded:** control the number of messages and bytes **waiting and in flight**, wait times, and the queue-full handling policy. Do not create an unbounded `CompletableFuture` chain or accumulate unbounded `ByteBuffer` instances.

Two standalone Java 17+ examples below verify these principles. The first example **does not use the network**, allowing send-completion timing to be controlled with a mock and the queue cap to be observed precisely. The second example creates a **minimal test WebSocket server on loopback**, uses Java `HttpClient` to perform an HTTP Upgrade, chains three `sendText` calls, and verifies that the server receives the messages in the exact order.

## 1. Three Layers to Distinguish: Logical Message, Send Operation, Transport

~~~text
Producer A / B / C (multiple threads)
             │
             ▼
      APPLICATION assigns order
      - message #1, #2, #3
      - admission / bounded queue
             │
             ▼
       serial send dispatcher
       - at most one text/binary send pending
       - calls sendText/sendBinary
       - awaits CompletableFuture completion
             │
             ▼
     java.net.http.WebSocket (client)
       - WebSocket framing / masking
       - state and pending-send policy
             │
             ▼
       TLS/TCP/OS/network
             │
             ▼
        Remote peer / application
~~~

A **WebSocket message** is a logical unit of type **text** or **binary**. A message may be transmitted across **one or more frames**. The Java API has a `last` parameter to distinguish the final fragment from an unfinished fragment. A **send operation** is a call to `sendText`, `sendBinary`, `sendPing`, `sendPong`, or `sendClose` and the returned `CompletableFuture`.

According to the [JDK 17 WebSocket Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html), an operation that has been initiated but whose `CompletableFuture` has not yet completed is considered **pending**. When the future completes normally, **the operation is considered sent successfully**; when it completes exceptionally, the operation fails.

**Do not infer that the remote application has processed a message solely from the send future succeeding.** TCP/WebSocket send-completion does not replace an **application-layer acknowledgment**. If you need to know that the server has updated an order, recorded an event, or committed a transaction, you must define a dedicated ACK message with a correlation ID or protocol response and appropriate timeout/idempotency handling.

| Event | What Is Proven | What Is Not Proven |
| --- | --- | --- |
| `sendText("A", true)` returns a future | The operation was initiated or rejected per contract | Does not mean the future has succeeded |
| `sendText` future completes normally | The JDK send operation completed successfully | Does not prove the peer processed the business logic |
| Server WebSocket listener receives message A | The message reached that WebSocket server endpoint | Does not prove the server-side transaction committed |
| Server sends application ACK for message ID A | Depends on the designed ACK semantics | Does not automatically guarantee exactly-once after retry |
| Client closes WebSocket output with a Close frame | Close-send was initiated/completed per the future | Does not guarantee the peer application processed all side effects |

## 2. Specific Send Constraints in Java 17

### 2.1. `sendText` and `sendBinary` Should Not Overlap

API:

~~~java
CompletableFuture<WebSocket> a =
        webSocket.sendText("first", true);

CompletableFuture<WebSocket> b =
        webSocket.sendText("second", true);
~~~

This is **risk-demonstration code**, not a pattern to use. If `a` is still pending when the second `sendText` is called, per the Javadoc `b` **may complete exceptionally with `IllegalStateException`** because a text or binary send operation is already pending. The exception is in the **returned future**, not necessarily thrown synchronously at the `sendText` line.

The same applies to `sendBinary(ByteBuffer, boolean)`: if a text/binary send operation is pending, the future may complete with `IllegalStateException`. An I/O error or a closed output side typically manifests as an `IOException` in the future.

**Application rule:** do not rely on loopback speed making the first future happen to complete immediately. If you want order A→B, only **initiate send B after send A's future has completed normally**.

### 2.2. Chaining with `thenCompose`

~~~java
CompletableFuture<WebSocket> chain =
        CompletableFuture.completedFuture(webSocket);

chain = chain
        .thenCompose(ws -> ws.sendText("first", true))
        .thenCompose(ws -> ws.sendText("second", true))
        .thenCompose(ws -> ws.sendText("third", true));
~~~

This is an **illustrative Java snippet inside a method**; it requires `webSocket` of type `WebSocket`, and imports `java.net.http.WebSocket` and `java.util.concurrent.CompletableFuture`.

- `thenCompose` does not start the second send until the first stage succeeds.
- The chain preserves the order of **operations enqueued within that chain**.
- If the first operation fails, subsequent `thenCompose` steps **are not invoked**; the final stage also completes exceptionally.
- `thenApply` is suitable for transforming a value after a send; `thenCompose` is used to **chain a new asynchronous future**, avoiding `CompletableFuture<CompletableFuture<...>>`.
- `thenRun` can be used for a synchronous step, but does not replace `thenCompose` when the callback returns a send future.
- Do not block the event loop/callback with `join()` or `get()` for each message; only wait on a test thread or a consumer permitted to block.

An ordered future chain is **not automatically bounded**. If one million `thenCompose` calls are added while the first send has not finished, the program can retain one million messages/payloads and future nodes on the heap. There must be **admission control** before adding a stage.

### 2.3. Ping/Pong Has Its Own Pending Policy

According to JDK 17:

- `sendText` / `sendBinary` treat a **pending text or binary send** as a conflict.
- `sendPing` / `sendPong` treat a **pending ping or pong send** as a conflict within the corresponding control group.
- Ping/Pong payload is at most **125 bytes**; `sendPing(ByteBuffer)` and `sendPong(ByteBuffer)` may complete exceptionally with `IllegalArgumentException` if the limit is exceeded.
- The WebSocket implementation automatically sends Pong in response to Ping per contract; applications usually **do not need to send Pong manually**.
- `sendClose` has its own semantics and also affects output state; **do not** place Close between data messages that still need to be sent.

Because text/binary and ping/pong have different pending condition groups, do not assume the API automatically creates a **global FIFO order for all send types**. If the application requires strict ordering for a group of data/control commands, place them in a **dispatcher with an explicit policy**, though do not promise that wire-level control frame interleaving will always match the application queue order.

## 3. Where Does Order Come From When There Are Multiple Producer Threads?

For example, chat, telemetry, or game state:

~~~text
Producer A: enqueue seq=101 (JOIN)
Producer B: enqueue seq=102 (MOVE)
Producer C: enqueue seq=103 (LEAVE)
               │
               ▼
        One outbound owner
        queue [101, 102, 103]
               │
               ▼
         serial send chain
~~~

If all three threads independently call `webSocket.sendText` directly, each thread can win the race differently. **Thread scheduling does not guarantee business order**, even if the user clicked "JOIN" before "MOVE" in the UI. If order truly matters, the application must:

1. **Establish order at a single linearization point** (single actor/event loop, or lock on admission) and assign a sequence ID if needed.
2. Have only **one owner** decide enqueueing and invoke send; producer threads do not send directly.
3. Use a FIFO queue or a `tail` future chain to preserve order from **admission** time.
4. Pause/limit producers when the queue is full instead of creating unbounded future nodes.
5. Have provisions for error handling, timeouts, and shutdown so waiting messages are not left stranded forever.

**Admission order under `synchronized` = the order in which threads acquire the lock**, not necessarily the chronological order in which events occurred in the real world. For multiple producers requiring a global business order, assign sequences at the upstream/transaction log, or use a single-owner event stream/actor with a clear source-order contract. Do not use `System.currentTimeMillis()` as a guaranteed total order because events can share timestamps and clocks can shift.

### 3.1. A Bounded Queue Must Limit Both Active and Waiting

A common design:

~~~text
MAX_MESSAGES = 3
MAX_BYTES    = 6

T0: request A (1 byte) -> accepted -> send A in flight
T1: request BB (2 bytes) -> accepted, waits
T2: request CCC (3 bytes) -> accepted, waits
    reserved = 1 + 2 + 3 = 6 bytes
    pendingMessages = 3

T3: request D (1 byte) -> REJECTED:
    pendingMessages has reached MAX_MESSAGES=3

T4: send A completes -> release A, start BB
T5: send BB completes -> release BB, start CCC
T6: send CCC completes -> release CCC
    reserved=0, pendingMessages=0
~~~

You must count the **in-flight message** in the quota, not just the waiting queue. If there is 1 active + 100 waiting and the cap only checks the 100 waiting, the actual resource state exceeds the intended cap.

When sending text, the byte cap should be based on the **UTF-8 encoded payload** size, not `String.length()`: `"é"` has one UTF-16 code unit but two UTF-8 bytes; an emoji typically has two UTF-16 code units and four UTF-8 bytes. You must also account for the overhead of `String`/future/queue nodes, binary buffers, WebSocket framing, and the client implementation when establishing a realistic memory budget. **A payload-based `MAX_BYTES` is a useful boundary, not a guarantee that total heap/direct memory equals `MAX_BYTES`.**

### 3.2. High-Water/Low-Water + Hard Cap

You can combine:

- `LOW_WATER`: when pending bytes drop to or below this level, resume paused data sources.
- `HIGH_WATER`: when pending bytes rise to this level, pause producers or stop polling upstream.
- `MAX_PENDING_BYTES`: hard cap that must not be exceeded, regardless of the high watermark.
- `MAX_PENDING_MESSAGES`: protects against object overhead when there are many small messages.

~~~text
0 ─── LOW (256 KiB) ─── HIGH (768 KiB) ─── MAX (1 MiB)
        ▲                    ▲                ▲
   resume producer       pause producer   reject/defer
    (if room exists)                     before enqueue
~~~

**Do not** wait until after enqueueing to check MAX. For a 2 MiB message and a 1 MiB cap, reject that single message immediately; do not fragment it into two million entries or truncate the tail unless the business protocol allows it.

## 4. Policy When Queue Is Full: Fail-Fast, Defer, Coalesce, or Disconnect?

There is no single policy for all types of WebSocket traffic.

| Policy | Suitable For | Caveat |
| --- | --- | --- |
| **Reject new message** | RPC/control commands requiring strictness; caller has a retry policy | Caller must receive a clear error, not silent drops |
| **Pause producer** | Streams from file/DB/upstream that support backpressure | Avoid accumulating bytes in another queue; must resume at LOW |
| **Drop/coalesce snapshots** | UI presence, high-rate state updates where loss is acceptable | Must define replaceable messages; **does not apply to all business logic** |
| **Disconnect slow peer** | Sustained quota violation, client not consuming | Close/abort may lose unacknowledged messages |
| **Spool to disk** | Queues with durability semantics and strict quotas | Disk I/O, checksums, ordering, crash recovery, PII |
| **Fail entire session** | A send failure leaves session state untrustworthy | Fail pending futures, cleanup, reconnect, and reconcile |

If a message represents a payment, order placement, permission change, or a command with side effects, **do not drop or reorder arbitrarily**. If it is merely the latest temperature snapshot, an older snapshot can be replaced before sending if the protocol allows. Every choice should be reflected in **delivery semantics**: at-most-once, at-least-once, dedupe, ACK, replay, or idempotency.

**Do not use unbounded retries** for `sendText` when a future fails. The peer may have received part or all of it before disconnecting; repeating a command without an idempotency token can cause duplicate side effects.

## 5. Java 17+ Example 1: Bounded Send Queue and Ordered Future Chain

This example intentionally **does not open the network**. A `ManualTransport` acts as a transport whose `CompletableFuture` completes when the test explicitly calls `finishOne()`. This clearly shows that **while operation A is pending, B and C have not started**, even though all three were accepted into the queue. Both the message count and total reserved bytes are bounded.

Create file **`WebSocketBoundedQueueDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

public final class WebSocketBoundedQueueDemo {
    interface AsyncTextTransport {
        CompletableFuture<Void> send(String message);
    }

    static final class BoundedOrderedSender {
        private final AsyncTextTransport transport;
        private final int maxMessages;
        private final int maxBytes;
        private int pendingMessages;
        private int pendingBytes;
        private boolean accepting = true;
        private CompletableFuture<Void> tail =
                CompletableFuture.completedFuture(null);

        BoundedOrderedSender(AsyncTextTransport transport,
                             int maxMessages, int maxBytes) {
            if (maxMessages < 1 || maxBytes < 1) {
                throw new IllegalArgumentException(
                        "positive limits required");
            }
            this.transport = Objects.requireNonNull(transport);
            this.maxMessages = maxMessages;
            this.maxBytes = maxBytes;
        }

        synchronized CompletableFuture<Void> offer(String message) {
            Objects.requireNonNull(message);
            int bytes =
                    message.getBytes(StandardCharsets.UTF_8).length;

            if (!accepting) {
                return CompletableFuture.failedFuture(
                        new IllegalStateException("sender stopped"));
            }
            if (pendingMessages >= maxMessages
                    || bytes > maxBytes - pendingBytes) {
                return CompletableFuture.failedFuture(
                        new RejectedExecutionException("send queue full"));
            }

            pendingMessages++;
            pendingBytes += bytes;

            CompletableFuture<Void> internal =
                    tail.thenCompose(ignored ->
                            transport.send(message));
            tail = internal;

            CompletableFuture<Void> forCaller =
                    new CompletableFuture<>();
            internal.whenComplete((ok, failure) -> {
                synchronized (BoundedOrderedSender.this) {
                    pendingMessages--;
                    pendingBytes -= bytes;
                    if (failure != null) accepting = false;
                }
                if (failure == null) {
                    forCaller.complete(null);
                } else {
                    forCaller.completeExceptionally(failure);
                }
            });
            return forCaller;
        }

        synchronized int pendingMessages() {
            return pendingMessages;
        }

        synchronized int pendingBytes() {
            return pendingBytes;
        }
    }

    static final class ManualTransport
            implements AsyncTextTransport {
        final List<String> started = new ArrayList<>();
        final Deque<CompletableFuture<Void>> acknowledgments =
                new ArrayDeque<>();

        @Override
        public CompletableFuture<Void> send(String message) {
            started.add(message);
            CompletableFuture<Void> ack = new CompletableFuture<>();
            acknowledgments.addLast(ack);
            return ack;
        }

        void finishOne() {
            acknowledgments.removeFirst().complete(null);
        }
    }

    public static void main(String[] args) {
        ManualTransport transport = new ManualTransport();
        BoundedOrderedSender queue =
                new BoundedOrderedSender(transport, 3, 6);

        CompletableFuture<Void> first = queue.offer("A");
        CompletableFuture<Void> second = queue.offer("BB");
        CompletableFuture<Void> third = queue.offer("CCC");
        CompletableFuture<Void> rejected = queue.offer("D");

        System.out.println("started: " + transport.started);
        System.out.println("pending: " + queue.pendingMessages()
                + " messages, " + queue.pendingBytes() + " bytes");
        System.out.println("fourth rejected: "
                + rejected.isCompletedExceptionally());

        transport.finishOne();
        System.out.println("after first ack: " + transport.started);

        transport.finishOne();
        System.out.println("after second ack: " + transport.started);

        transport.finishOne();
        System.out.println("all accepted completed: "
                + (first.isDone() && second.isDone()
                        && third.isDone()));
        System.out.println("pending after drain: "
                + queue.pendingMessages() + "/"
                + queue.pendingBytes());
    }
}
~~~

Run with JDK 17+:

~~~bash
javac --release 17 WebSocketBoundedQueueDemo.java
java WebSocketBoundedQueueDemo
~~~

Stdout **exact, deterministic, verified with local JDK**:

~~~text
started: [A]
pending: 3 messages, 6 bytes
fourth rejected: true
after first ack: [A, BB]
after second ack: [A, BB, CCC]
all accepted completed: true
pending after drain: 0/0
~~~

In `ManualTransport`, the word "ack" in the name and stdout is a **mock signal explicitly triggered by the test calling `complete(null)`**, **not an application ACK from a real WebSocket peer**. This only verifies send initiation order and queue accounting; it does not verify network transport or server delivery.

### 5.1. Why Does This Pattern Preserve Order?

- `offer` is synchronized with `synchronized`, so at most one thread performs admission and appends a stage at a time.
- `tail.thenCompose(...)` ensures the next transport call starts only when the previous operation **succeeds**.
- The three messages are accepted in **the order in which `offer` calls acquire the lock**.
- `pendingMessages` and `pendingBytes` are incremented **before** creating the send stage and decremented only when the internal future completes.
- A message exceeding the quota receives `CompletableFuture.failedFuture(RejectedExecutionException)` **immediately at admission**; it is not enqueued and silently dropped.
- `forCaller` is decoupled from the internal future chain: if the caller cancels its own observed future, it **does not directly cancel the internal ordering chain**.
- If a send fails, the `tail` chain becomes exceptional; subsequent accepted sends are not initiated and also complete exceptionally; `accepting=false` stops accepting new messages.

**Demo limitations:** `thenCompose` may run its callback immediately on the thread completing the future; `transport.send(...)` should be a **fast, asynchronous, non-blocking** call. In production, move ownership and dispatch to a dedicated event loop/actor if there are many producers/callbacks; a state machine for shutdown/timeouts and metrics is needed. The demo does not support reordering, ping/pong prioritization, or snapshot coalescing. UTF-8 counting uses a temporary `getBytes(...)` allocation; if payloads are very large, input size must be bounded **before** creating copies.

### 5.2. Applying a Real Transport for `WebSocket`

`BoundedOrderedSender` uses the small `AsyncTextTransport` interface so it can be tested without a network. After creating a real `WebSocket ws`, the corresponding adapter is:

~~~java
// Illustrative snippet inside a method with WebSocket ws.
WebSocketBoundedQueueDemo.BoundedOrderedSender out =
        new WebSocketBoundedQueueDemo.BoundedOrderedSender(
                text -> ws.sendText(text, true)
                          .thenApply(ignored -> (Void) null),
                64, 256 * 1024);

CompletableFuture<Void> accepted = out.offer("hello");
accepted.whenComplete((ignored, failure) -> {
    if (failure != null) {
        // report/reconcile; do not assume the peer did not receive the message
    }
});
~~~

This snippet **is not a standalone program**; it requires the demo class and an already established `ws`. Each `text` is a **complete logical message**, hence `sendText(text, true)` is used. If you want to send a logical message across multiple fragments, you need a dispatcher with its own notion of a "message transaction" (Section 7), without allowing fragments of two different messages to interleave.

**Improvements needed for production:** Policy when the queue is full (defer/reject/close), global cap across sockets, timeouts, trapping `IOException`, close handshake, and recovery after reconnect. 64 messages/256 KiB in the adapter are **illustrative values**, not universal optimal thresholds.

## 6. A Successful Send Chain Does Not Equal a Business ACK

There are two axes that many applications confuse:

~~~text
Transport/send operation:
  sendText() ── future complete ──> JDK send step succeeded

Application workflow:
  publish(commandId=42) ──> server receive ──> server process
                                    │                │
                                    └─ ACK/RESULT ◄──┘
~~~

When designing ACKs:
- Each message has a `messageId` that remains stable across retries.
- The client keeps a `messageId → pending result` mapping in **a bounded table** with timeouts.
- The server defines whether ACK means **received**, **durably written**, or **fully processed**. Different levels must not all be lumped together as "delivered".
- Have server-side idempotency/deduplication for commands with side effects.
- If an ACK does not arrive, do not assume the message was never processed; retry only according to an appropriate protocol.

If the WebSocket is closed immediately after the send future completes, the remote application may not have processed it yet or the ACK may not have arrived yet. `sendClose` after the data-send chain is the **correct order of local operations**, but does not substitute for application delivery confirmation.

## 7. Fragmentation: `last=false` Does Not Complete the Message

JDK 17 `WebSocket.sendText(CharSequence data, boolean last)` and `sendBinary(ByteBuffer data, boolean last)` support sending **one logical message** in multiple parts:

~~~java
webSocket.sendText("Hello, ", false)
         .thenCompose(ws -> ws.sendText("world!", true))
         .thenCompose(ws -> ws.sendText("next message", true));
~~~

This snippet is **illustrative**; with `last=false`, the first text part **does not end the message**. The second part with `last=true` closes the logical message "Hello, world!". The third part starts a new message. Chaining both avoids pending send conflicts and reduces the risk of interleaving fragments.

**Do not do this:**

~~~java
webSocket.sendText("part A", false)
         .thenCompose(ws -> ws.sendBinary(
                 ByteBuffer.wrap(new byte[]{1}), true)); // WRONG
~~~

If the previous text message has not finished, calling `sendBinary` is not a valid transition to a new binary logical message; the JDK 17 future may complete with `IllegalStateException` because **previous textual data does not complete the message**. Conversely, do not switch to text in the middle of unfinished binary fragments.

A subtle note: even if futures complete sequentially, if you send `sendText("part A", false)` and then interject a `sendText("unrelated", true)` from another producer, `"unrelated"` may be interpreted as a **continuation** of the same logical text message, not an independent message. A lock/actor is needed to ensure **all fragments of a message are sent as a single logical transaction**, before moving to the next message.

### 7.1. `ByteBuffer` Ownership

The `sendBinary(ByteBuffer, last)` Javadoc states you must not **access the data buffer** until the operation's future completes. After normal completion, the buffer has no `remaining()`. Therefore:

~~~java
ByteBuffer data = ByteBuffer.wrap(
        new byte[]{10, 20, 30});
CompletableFuture<WebSocket> f =
        webSocket.sendBinary(data, true);

// Do not modify data.position()/limit(), do not overwrite byte[]
// or reuse the buffer before f completes.
~~~

This is **illustrative**. A common mistake is passing the **same `ByteBuffer` or underlying `byte[]`** into multiple asynchronous sends and immediately calling `clear()`/`flip()`. The result can be duplicated/lost/corrupted data or a buffer ownership violation. In a queue, use independent buffers or copy data when ownership cannot be transferred; set a memory cap on those copies themselves.

With `sendText(CharSequence, last)`, **do not modify the `CharSequence`** before the send future completes. Immutable `String` is appropriate; mutable `StringBuilder`/`StringBuffer` can lead to a data race when modified mid-send. Use `toString()` to create an immutable snapshot before admission if the producer retains the mutable source.

### 7.2. UTF-8 and UTF-16 Errors

WebSocket text is **UTF-8** on the wire. A JDK 17 implementation note states that a malformed UTF-16 sequence in `sendText` may cause the future to fail with `IOException`. Do not rely on `String.length()` to allocate memory by byte count; validate or encode properly when a byte quota is needed. For binary, count `ByteBuffer.remaining()` before admission, not `capacity()`.

Fragmented text can also split at boundaries that do not align with code points/chunks; avoid assuming a single fragment is a complete text message on the receiver side. `WebSocket.Listener.onText(WebSocket, CharSequence, boolean last)` may be called multiple times for a single message; `last` determines when the logical message completes.

## 8. Java 17+ Example 2: Real WebSocket on Loopback, Verifying Message Order

This example verifies the `HttpClient.newWebSocketBuilder()` and `sendText` APIs in practice **without needing an external Internet server**. The program creates a **tiny mock WebSocket server** using `ServerSocket`:

1. Accepts an HTTP Upgrade request (RFC 6455) on loopback.
2. Computes `Sec-WebSocket-Accept` from `Sec-WebSocket-Key` and returns `HTTP/1.1 101 Switching Protocols`.
3. Reads exactly three **masked client text frames**, unmasks them, and records the payloads.
4. Receives a Close frame and replies with a Close frame.
5. The client sends three messages using a **`thenCompose` chain**, waits for completion, and then sends Close.

**The mock server is only a test harness**: it intentionally supports only frames with `FIN=1`, payload ≤125 bytes, and text opcode; it does not support fragmentation, extended payload lengths, extensions, TLS, ping/pong scheduling, quotas, or multi-client concurrency. **Do not deploy it as a production server**.

Create file **`WebSocketOrderLoopbackDemo.java`**:

~~~java
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;

public final class WebSocketOrderLoopbackDemo {
    private static String readHandshake(InputStream in)
            throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        int prev3 = -1, prev2 = -1, prev1 = -1, ch;

        while ((ch = in.read()) != -1) {
            buf.write(ch);
            if (buf.size() > 16384) {
                throw new IOException("Handshake too large");
            }
            if (prev3 == '\r' && prev2 == '\n'
                    && prev1 == '\r' && ch == '\n') {
                return buf.toString(
                        StandardCharsets.ISO_8859_1);
            }
            prev3 = prev2;
            prev2 = prev1;
            prev1 = ch;
        }
        throw new EOFException("Incomplete HTTP upgrade");
    }

    private static String acceptKey(String header)
            throws Exception {
        String key = null;
        for (String line : header.split("\r\n")) {
            if (line.regionMatches(true, 0,
                    "Sec-WebSocket-Key:", 0,
                    "Sec-WebSocket-Key:".length())) {
                key = line.substring(
                        "Sec-WebSocket-Key:".length()).trim();
                break;
            }
        }
        if (key == null) {
            throw new IOException("Missing WebSocket key");
        }
        byte[] digest = MessageDigest.getInstance("SHA-1")
                .digest((key
                        + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                        .getBytes(StandardCharsets.US_ASCII));
        return Base64.getEncoder().encodeToString(digest);
    }

    private record Frame(int opcode, byte[] data) { }

    private static int requiredByte(InputStream in)
            throws IOException {
        int b = in.read();
        if (b == -1) throw new EOFException("Truncated frame");
        return b;
    }

    private static Frame readFrame(InputStream in)
            throws IOException {
        int first = requiredByte(in);
        int second = requiredByte(in);
        if ((first & 0x80) == 0
                || (second & 0x80) == 0) {
            throw new IOException(
                    "Expected final masked client frame");
        }
        int length = second & 0x7F;
        if (length >= 126) {
            throw new IOException(
                    "Demo supports payload <= 125 bytes");
        }

        byte[] mask = in.readNBytes(4);
        byte[] body = in.readNBytes(length);
        if (mask.length != 4 || body.length != length) {
            throw new EOFException("Truncated frame payload");
        }
        for (int i = 0; i < body.length; i++) {
            body[i] ^= mask[i % 4];
        }
        return new Frame(first & 0x0F, body);
    }

    public static void main(String[] args)
            throws Exception {
        InetAddress loopback =
                InetAddress.getLoopbackAddress();
        try (ServerSocket listener =
                new ServerSocket(0, 1, loopback)) {
            listener.setSoTimeout(5000);

            FutureTask<List<String>> server = new FutureTask<>(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(5000);
                    InputStream in = peer.getInputStream();
                    OutputStream out = peer.getOutputStream();

                    String key = acceptKey(readHandshake(in));
                    String response =
                            "HTTP/1.1 101 Switching Protocols\r\n"
                            + "Upgrade: websocket\r\n"
                            + "Connection: Upgrade\r\n"
                            + "Sec-WebSocket-Accept: "
                            + key + "\r\n\r\n";
                    out.write(response.getBytes(
                            StandardCharsets.ISO_8859_1));
                    out.flush();

                    List<String> values = new ArrayList<>();
                    for (int i = 0; i < 3; i++) {
                        Frame frame = readFrame(in);
                        if (frame.opcode() != 1) {
                            throw new IOException(
                                    "Expected text frame");
                        }
                        values.add(new String(
                                frame.data(),
                                StandardCharsets.UTF_8));
                    }

                    Frame close = readFrame(in);
                    if (close.opcode() != 8) {
                        throw new IOException(
                                "Expected close frame");
                    }
                    out.write(new byte[]{
                            (byte) 0x88, 2, 3, (byte) 0xE8
                    });
                    out.flush();
                    return values;
                }
            });

            Thread serverThread = new Thread(
                    server, "websocket-test-server");
            serverThread.setDaemon(true);
            serverThread.start();

            URI uri = new URI(
                    "ws", null, loopback.getHostAddress(),
                    listener.getLocalPort(), "/test", null, null);

            WebSocket socket = HttpClient.newHttpClient()
                    .newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(5))
                    .buildAsync(uri, new WebSocket.Listener() {
                        @Override
                        public void onOpen(WebSocket ws) {
                            ws.request(1);
                        }
                    }).get(5, TimeUnit.SECONDS);

            CompletableFuture<WebSocket> chain =
                    CompletableFuture.completedFuture(socket);
            chain = chain
                    .thenCompose(ws -> ws.sendText("one", true))
                    .thenCompose(ws -> ws.sendText("two", true))
                    .thenCompose(ws -> ws.sendText("three", true));
            chain.get(5, TimeUnit.SECONDS);

            socket.sendClose(
                    WebSocket.NORMAL_CLOSURE, "")
                    .get(5, TimeUnit.SECONDS);

            List<String> received = server.get(
                    5, TimeUnit.SECONDS);
            System.out.println("server messages: " + received);
            System.out.println("in order: " +
                    received.equals(List.of(
                            "one", "two", "three")));
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac --release 17 WebSocketOrderLoopbackDemo.java
java WebSocketOrderLoopbackDemo
~~~

Stdout **verified on a machine with loopback available**:

~~~text
server messages: [one, two, three]
in order: true
~~~

**What is proven and what is not proven:**

- Proven: the JDK WebSocket client upgraded and sent text frames over TCP; the mock server unmasked the frames and collected three logical messages in order.
- Proven ordering: the client only invoked send 2 after send 1's future completed, and send 3 after send 2.
- Not proven: that any production server would accept the handshake like the mock, that the network has exactly-once delivery, that messages were processed by business logic, or that the queue is bounded in this example. Example 1 addresses the queue cap separately.
- The test server only supports small payloads because it reads minimal frames directly; **do not** expose this parser to the Internet.
- The client sends the Close frame **after** the data-send chain. The mock replies with Close to finish the protocol handshake; production needs an idle timeout/abort fallback if the peer does not respond with Close.
- The `get(5, TimeUnit.SECONDS)` calls on futures only appear in the **test program** to avoid hanging, and are not a recommendation to block on callbacks/event loops.

Depending on the sandbox, binding to loopback may be blocked. The mock does not implement TLS because it uses `ws://loopback`; production uses `wss://` when confidentiality and TLS server identity verification are required.

## 9. Close/Abort: Stop Accepting New Messages Before Closing Output

A WebSocket has independent **input side** and **output side**. `sendClose(int,String)` initiates an **orderly close** on the output side; it does not necessarily close the input side immediately. `abort()` closes both sides abruptly. Per the JDK 17 WebSocket Javadoc, a successful `sendClose` call means the Close message has been sent in the local send operation, **not replacing an application ACK**.

**Ordered graceful close:**

~~~java
// Illustrative snippet: "tail" is the future at the end of the data queue.
CompletableFuture<Void> closing =
        tail.thenCompose(ignored ->
                webSocket.sendClose(
                        WebSocket.NORMAL_CLOSURE, "")
                        .thenApply(ws -> (Void) null));
~~~

You must stop admission **before** scheduling close; otherwise another producer could add data **after** the close stage and fail/be lost. If a preceding send fails, `thenCompose` skips close; you may need to call `abort()` and run cleanup per your failure policy. If close is sent but the peer does not reply with Close within the deadline, enforce a timeout and then `abort` to avoid holding the connection indefinitely.

Conditions to standardize:

1. State `OPEN`: still accepting new messages.
2. State `DRAINING`: reject/defer new messages, continue sending the already-accepted backlog.
3. State `CLOSING`: Close has been initiated, send no more application data.
4. State `CLOSED/FAILED`: release pending queue, subscriptions, and timers; callers receive a clear error.
5. `abort()`: use on severe error, deadline expiration, protocol violation, or when graceful close does not complete per policy.

**Close can race with producers** if each thread calls the WebSocket API independently. This is why a single owner/dispatcher is needed, not just an unsynchronized `boolean closed` variable.

### 9.1. `WebSocket.Listener.onClose` and `onError`

- `onClose(ws,status,reason)` reports that the **input** side received Close. It does not mean all application messages have been processed by the server.
- `onError(ws,error)` reports a receive/session error; the application should shut down/reconcile state. The Javadoc does not guarantee every send failure always triggers a corresponding `onError`; **observe both send futures and the listener**.
- When receiving Close, the listener should handle it per protocol, potentially replying with Close if not yet sent; do not assume this invocation coincides with send-future completion.
- In `onOpen`, the application must call `ws.request(n)` if it wants to receive callbacks, because the initial receive counter is **0**.

Do not mistake `request(n)` for a way to drain the send queue: it only permits the WebSocket listener to be invoked for **n more receive callbacks**, not necessarily n complete messages, and certainly not outbound `sendText` credit.

## 10. Receive Backpressure Is Different from Send Backpressure

~~~text
OUTBOUND (this topic)
app producers -> queue -> sendText/sendBinary futures -> network

INBOUND
network -> WebSocket.Listener callbacks -> app consumer
               ^
               |
       ws.request(n) controls number of receive callbacks
~~~

JDK 17 `WebSocket.request(long n)` increments an internal counter for **the number of listener receive method invocations** such as `onText/onBinary/onPing/onPong/onClose`. One logical text message can arrive across **multiple `onText` callbacks** with `last=false`, so `request(1)` **does not** mean requesting one complete logical message.

Listener example:

~~~java
WebSocket.Listener listener = new WebSocket.Listener() {
    @Override
    public void onOpen(WebSocket ws) {
        ws.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket ws, CharSequence chars, boolean last) {
        // Consumer processes each part per ownership/size limits.
        handleFragment(chars, last);
        ws.request(1);
        return CompletableFuture.completedFuture(null);
    }
};
~~~

This is **illustrative code**; `handleFragment` is application-defined and must execute quickly and correctly. If processing is asynchronous and backpressure is needed, request the next callback only when downstream has capacity; do not default to `request(Long.MAX_VALUE)` if the app cannot tolerate the memory usage. Do not treat the receive counter as a hard cap for outbound.

**Important point:** not calling `request` pauses receive callbacks, but peer/OS/network buffers may still hold in-flight data. It does not replace a global inbound memory cap or protocol-level flow control/timeouts.

## 11. Avoiding Deadlocks When Sending from a Listener Callback

An anti-pattern:

~~~java
@Override
public CompletionStage<?> onText(
        WebSocket ws, CharSequence data, boolean last) {
    ws.sendText("reply", true).join(); // MAY BLOCK callback thread
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
~~~

Blocking inside a listener callback can:
- delay subsequent callbacks;
- cause starvation on the client's executor;
- create a dependency cycle with code waiting for a receive callback;
- prevent timely handling of timeouts/Close/Ping.

A safer approach: **enqueue the response into the bounded outbound dispatcher**, return a `CompletionStage` representing the receive work if needed, and manage `request(n)` based on downstream capacity. If the listener calls `sendText` directly from multiple callbacks/threads, it can race with other producers sending; use **one owner** for the entire output side.

### 11.1. Callback Order ≠ Business Order from Multiple Sources

The Javadoc guarantees listener receive methods are called in a thread-safe lifecycle manner; that does not turn all application tasks spawned from callbacks into a strict send order when they continue on multiple executors. For example, receiving A then B in order, but processing A in a slower task than B: if both call `sendText` on completion, B may be sent before A. To preserve A→B, assign a sequence/message ID and **reorder at outbound admission** or process sequentially per business contract.

## 12. Rules for Handling Send Failures and Cancelled Futures

A send failure can occur at several points:
- Future fails with `IllegalStateException` due to a pending text/binary send or an unfinished previous message type.
- Future fails with `IOException` due to closed output, disconnect, or I/O error.
- Future fails due to malformed UTF-16 text (implementation note).
- Quota failure: the application itself returns `RejectedExecutionException` at admission.
- Application timeout: operation pending too long; no ACK/progress per SLA.

**Distinguish quota errors from network errors:**

| Situation | What the Caller Should See | How to Handle |
| --- | --- | --- |
| Queue full, WebSocket send not initiated | Application rejection with a clear code | Defer/retry when capacity opens, or fail per policy |
| Text/binary send conflict from concurrent calls | `IllegalStateException` in send future | Fix serializer/chain; do not retry blindly |
| Message rejected because output side is closed | `IOException` in send future or closed state | Stop enqueueing; reconcile/reconnect |
| Send operation fails after initiation | Exceptional completion (usually I/O) | Stop queue, fail pending, verify business status before retry |
| Caller no longer needs the returned future's result | May cancel the observed future | **Do not** infer the send operation was cancelled/reversed |
| Slow peer keeps future pending for a long time | Queue cap protects bytes, but latency rises | Timeout, abort/close, telemetry, and upstream backpressure |

**Do not handle errors with `tail.exceptionally(e -> null)` and automatically continue all messages** without knowing whether the WebSocket is still usable. Swallowing errors can allow subsequent messages to be sent after one failed, breaking business consistency. If retry is needed, ensure safe replay, message ID/idempotency, and a healthy connection state.

### 12.1. Cancellation and Lifetime of the Underlying Send

The `BoundedOrderedSender` pattern intentionally returns a **separate `forCaller` future**. Cancelling that future only changes **result observation** at the caller; it **does not promise to cancel an already-initiated send operation** or immediately free the queue slot. The underlying operation retains quota until the internal future completes. This protects ordering if a caller cancels a downstream task.

Production needs dedicated APIs to:
- Cancel **messages that have not started sending** (if the protocol permits).
- Avoid blindly removing a message that has already started sending from the queue.
- Close/abort the session when an overall deadline expires.
- Properly release/reject pending messages after failure/close.
- Avoid leaking timers, future callbacks, or `ByteBuffer`s after reconnect.

Cancelling a `CompletableFuture` is not a transaction rollback model and cannot reverse a message that may already have gone over the network.

## 13. Managing Queues and Concurrency Across Multiple WebSocket Connections

A server/client with N sessions cannot rely solely on a per-socket cap and let N grow unboundedly. For example, 100,000 sockets × 1 MiB pending cap gives **100 GiB** of potential payload before even counting overhead. Therefore you need:

- **Per-connection cap:** bytes, messages, age of the oldest item.
- **Global cap:** total pending across all WebSockets, per process/tenant.
- **Producer quotas:** outstanding commands, publish rate, subscriber count.
- **Bounded executor/task queue:** if user code has deferred work; do not bound only the WebSocket queue while leaving an upstream executor queue unbounded.
- **Metrics:** offered, accepted, rejected, in-flight bytes, queue bytes, send latency, errors, close reasons, and queue age.
- **Fair scheduling:** prevent one large connection/message from monopolizing CPU or memory.
- **Load shedding:** fail/reject slow clients, coalesce permitted event types, and gracefully close/abort when deadlines are exceeded.

If a user interface sends 60 cursor positions/second, many updates can be coalesced with latest-only semantics. But for audit logs, ordered chat sequences, or financial commands, you must store/send everything per the delivery contract rather than shedding rate by dropping.

### 13.1. Byte Limits Must Reflect Ownership

For immutable text, `message.getBytes(UTF_8).length` is the estimated encoded payload size; WebSocket framing adds overhead, and JShell/JDK may create additional internal copies. For binary, track `ByteBuffer.remaining()` and do not modify the buffer before the send future completes. If the buffer is only a view into a large array, a queue cap counting `remaining()` may be smaller than the **backing array memory** still being retained. Global memory budgets must account for object retention/pooled direct buffers.

For messages rejected by the queue, the caller must **release or avoid holding references** to the payload if no retry is planned. If retry logic puts payloads into an unbounded `ScheduledExecutorService`, you have merely moved the memory leak from the WebSocket queue to the scheduler queue.

### 13.2. Measure Queue Age, Not Just Queue Size

A queue with only 2 messages where each message waits 15 minutes is a troubled connection. Track:
- `pending_message_count`.
- `pending_payload_bytes`.
- `oldest_pending_age_ms`.
- `send_completion_latency_ms` (from operation start to send future completion).
- `queue_wait_latency_ms` (from admission to send start).
- `send_failures_total` separated by quota vs. transport.
- `close_drain_duration_ms` and deadline exceeded count.
- `application_ack_latency_ms` **if** the protocol has application ACKs.

Do not conflate `send_completion_latency` with end-to-end business processing latency.

## 14. When to Use a Queue Actor Instead of a Future Chain?

A **future chain + admission lock** as in Example 1 is great for learning and small queues. When production involves:
- multiple message types (text/binary/ping/pong/close),
- splitting large fragments,
- priority rules and per-user quotas,
- cancellation of unsent items,
- reconnect/replay,
- multiple producer threads,
- high-water/low-water notifications,
- timeouts and fair scheduling,

a **single-thread actor/event-loop owner** model is usually clearer:

~~~text
many producers
     │
     ▼
bounded mailbox of commands
     │
     ▼
one owner event loop
     │
     ├── dequeue one logical message
     ├── send sequential frames / fragments
     ├── await CompletableFuture completion
     ├── account/release quota
     ├── process error / deadline / close
     └── wake next command only when allowed
~~~

Do not use `Executors.newSingleThreadExecutor()` with an unbounded task queue and assume "just one thread means bounded memory." A single-threaded executor with an unbounded job queue still causes overload. You need a bounded mailbox with an admission cap, and at most one active send job. Do not call `join()` on the owner thread if future completion requires the owner to run a callback; that will deadlock.

### 14.1. Put Close Under the Same Owner

An outbound actor can accept commands:
- `SendText(message)`,
- `SendBinary(bytes)`,
- `SendPing(payload)`,
- `DrainAndClose(reason)`,
- `Abort(cause)`.

Handling `DrainAndClose` must:
1. Transition state to `DRAINING`, stop accepting new data messages.
2. Wait for already-accepted data messages to complete their send futures.
3. Send the Close frame with the appropriate status/reason.
4. Wait for peer Close or deadline; call `abort()` if the deadline is exceeded.
5. Complete/fail pending public futures, release memory and timers.

Do not push Close into a shared queue **while still allowing producers to enqueue afterward**. A multi-priority context must also ensure control messages are not starved while not reordering critical data messages.

## 15. How to Test Send Ordering and Hard Caps

### 15.1. Deterministic Unit Tests with Manual Send Futures

Example 1 is a convenient unit test because:
- Sending `A` starts immediately; `BB` and `CCC` have not been called on the transport.
- The fourth operation is rejected when the cap is reached.
- Only when the test completes future `A` does `BB` start.
- Only when `BB` completes does `CCC` start.
- After three completions, reserved=0 and there are no pending messages.

Tests can be extended to:
- Simulate a failure while `BB` is sending; `CCC` must fail/be skipped without calling the transport.
- Send a single message exceeding the byte cap, ensuring rejection **before** initiating send.
- Have multiple producers call `offer` concurrently, verifying IDs are accepted in lock admission order.
- On each completion, assert `pendingBytes>=0` and `pendingMessages>=0`.
- Test `forCaller.cancel(true)`: the internal operation still holds resources until it actually completes.
- Test shutdown while pending messages remain: accept no more, drain or abort per policy.
- Test producer slow/resume when the queue hits HIGH and drops to LOW.

### 15.2. Integration Tests with a Real Server

Example 2 verifies ordering over network loopback, but production should test:
- TLS `wss://`, certificate/hostname/trust policy.
- A real server supporting large/fragmented messages, Ping/Pong/Close.
- Intentionally slow-reading peer: do queues and timeouts stay bounded?
- Concurrent producers: is order preserved **by business sequence** or only admission order?
- Disconnect after a message is sent but before application ACK.
- Reconnect and idempotent replay without duplicate side effects.
- Behavior when `sendClose` is called while a data backlog remains.
- Metrics/in-flight counts do not leak across exceptions/cancellations.
- Bounded global memory across many connections and message sizes.

Do not claim WebSocket provides exactly-once just because TCP has an ordered byte stream. TCP order is a transport property while a connection is alive; application reconnect/retry requires its own state.

## 16. Common Mistakes and Consequences

| Mistake | Why It Is Dangerous | Right Approach |
| --- | --- | --- |
| Multiple threads calling `sendText` concurrently | `IllegalStateException` from pending text/binary; business order not guaranteed | One sender owner, serialize with `thenCompose` or a queue actor |
| Using `thenApply` to return the next send's future | Creates a nested future; easily marks completion too early | Use `thenCompose` |
| Calling `join()` on a listener thread | Blocks/stalls/deadlocks callbacks | Async chain, bounded dispatcher |
| Building a chain of millions of futures without admission | Retains payloads/future nodes unboundedly | Hard caps before enqueue |
| Capping only message count | A single message can be many MB | Cap bytes + entries + max message size |
| Capping only the waiting queue, ignoring active send | Actual usage exceeds quota | Count **in-flight + waiting** |
| Using `String.length()` as bytes | UTF-16 code units do not equal UTF-8 bytes | Count UTF-8 payload bytes, add overhead budget |
| Mutating `StringBuilder` before future completes | Violates mutable `CharSequence` ownership | Snapshot `String` |
| `ByteBuffer.clear()` while future is still pending | Lost/corrupted payload, position/limit race | Do not access buffer until future completes |
| Interleaving logical messages between `last=false` fragments | Can mix message semantics | Send fragments atomically per logical message |
| Calling `sendBinary` while a text message is unfinished | API may fail with `IllegalStateException` | Finish the current message type first |
| Using `sendPing` payload >125 bytes | Javadoc specifies `IllegalArgumentException` | Limit control payload |
| Treating `request(1)` as outbound credit | It is receive callback demand | Set a separate outbound queue cap |
| Treating send future success as server ACK | Does not prove business effect | Message IDs + explicit ACK protocol |
| Send fails but chain automatically continues | May lose order/consistency | Stop/fail pending, reconcile state |
| Retrying all messages after reconnect | Duplicate side effects | Idempotency, dedupe, sequence/ACK |
| Calling `sendClose` while producers keep enqueueing | Data may be sent after close or fail | `DRAINING` state, stop admission, drain then close |
| Waiting indefinitely for peer Close | Connection/resources get stuck | Close deadline then `abort` |
| Putting an unbounded executor queue in front of a bounded WS queue | Only moves the overload point | Upstream backpressure + bound all queues |

## 17. Self-Check Exercises

**Q1.** A and B both call `sendText` while future A is still pending. What can happen?  
**Answer:** Future B may complete exceptionally with `IllegalStateException`. Wait for A to complete normally before initiating B.

**Q2.** Why is `thenCompose` more suitable than `thenApply` for send futures?  
**Answer:** `thenCompose` flattens the future returned by the send call, ensuring the next stage starts after the previous operation finishes.

**Q3.** Three producers call `offer` under `synchronized`; does admission order necessarily reflect the order in which business events occurred?  
**Answer:** No. It is only the lock-acquisition order; a sequence ID/single source is needed to represent business order.

**Q4.** Does `pendingMessages==0` mean the server has processed all messages?  
**Answer:** No. It only means the tracked local send operations have completed; a separate application ACK is needed.

**Q5.** `MAX_MESSAGES=3`, with 1 send active and 2 waiting. Should another message be accepted even if `Deque waiting.size()==2`?  
**Answer:** No, if the cap counts **both active + waiting**, the total is already 3.

**Q6.** Is `String.length()` sufficient to cap UTF-8 payload bytes?  
**Answer:** No. Unicode byte length differs from UTF-16; count encoded bytes/actual buffer bytes.

**Q7.** `sendText("abc",false)` followed by `sendText("def",true)` creates how many logical messages?  
**Answer:** One text message `"abcdef"` made of fragments, not two messages.

**Q8.** Is it allowed to modify a `ByteBuffer` while the `sendBinary` future is still pending?  
**Answer:** No; the Javadoc requires not accessing the buffer until the future completes.

**Q9.** Is a 126-byte Ping payload valid?  
**Answer:** No. Ping/Pong payload is at most 125 bytes per RFC/Javadoc.

**Q10.** Does `WebSocket.request(1)` request one more outbound send slot?  
**Answer:** No. It permits one more receive callback invocation.

**Q11.** When the queue is full, should an already-accepted but unsent chat message be dropped?  
**Answer:** Not by default. Apply protocol/delivery policy; usually reject/defer new messages or fail the session rather than dropping unexpectedly.

**Q12.** Send future A fails; does the chain `A.thenCompose(sendB)` invoke `sendB`?  
**Answer:** No. Stage B is skipped; the chain completes exceptionally unless there is an intentional recovery handler.

**Q13.** Does a caller cancelling the observed future from the queue mean the network send was cancelled?  
**Answer:** Not necessarily. If the queue separates the internal future and caller future, the operation continues to preserve order and accounting.

**Q14.** Is it valid to send Close and still enqueue a new message afterward?  
**Answer:** No. When starting an orderly close, stop admission, drain already-accepted items before Close, and send no more application data after Close.

**Q15.** Seeing the mock server receive A→B→C guarantees "exactly once" message delivery across reconnects?  
**Answer:** No. The loopback test proves ordering on a single connection; reconnect/retry requires idempotency and ACK/correlation.

## 18. Production Implementation Checklist

1. Create **one owner for the WebSocket output side**; producers call the queue, never `sendText` directly from multiple threads.
2. If **business order** is required, assign sequence IDs upstream and define proper admission/reordering.
3. Serialize text/binary sends with `thenCompose`/actor, starting a new operation only after the previous send future succeeds.
4. Use queue admission **bounded by messages, payload bytes (active+waiting), age, and global budget**.
5. When quota is full, reject/defer/coalesce/close per message semantics; never arbitrarily drop critical messages.
6. Do not block the listener/event loop with `get()`/`join()`; use bounded workers and async callbacks.
7. For text, snapshot mutable `CharSequence`; for binary, keep `ByteBuffer` immutable/exclusive until future completion.
8. For fragments, send all parts of **one logical message** in order through `last=true` before another message.
9. Handle future and listener errors; do not swallow `IllegalStateException`/`IOException` and continue the pipeline as if nothing happened.
10. Distinguish Ping/Pong pending policy and payload ≤125 bytes; do not treat `request(n)` as outbound credit.
11. Close with proper lifecycle: stop admission → drain → `sendClose` → wait for peer Close with deadline → `abort` when needed.
12. Do not infer remote application ACK from send future completion; design message IDs, ACKs, and idempotency as needed.
13. Test slow receivers, reconnects, partial/fragments, multi-producer races, quota overflow, and failures before ACK.
14. Monitor pending bytes/messages, oldest age, send latency, quota rejections, send failures, and close timeouts.
15. Use `wss://` and TLS hostname verification for external/sensitive networks; the WebSocket API does not add authorization/business validation on its own.

## Official Documentation

- [Java SE 17 — WebSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html): `sendText`, `sendBinary`, `sendPing`, `sendPong`, `sendClose`, pending send operations, future-completion, and `request(n)`.
- [Java SE 17 — WebSocket.Listener](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): `onOpen`, `onText`, `onBinary`, `onClose`, `onError`, and receive callback lifecycle.
- [Java SE 17 — WebSocket.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html): `buildAsync`, handshake, connect timeout, and subprotocols.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `thenCompose`, `whenComplete`, `failedFuture`, `handle`, and completion semantics.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `remaining`, and buffer ownership.
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455): handshake, frame masking, fragmentation, control frames, and close handshake.

**Core principle:** Preserve **order with a single outbound owner and a send-future chain**, bound **both in-flight and waiting data** with hard caps, and distinguish **local send success** from **remote application ACK**. Do not rely on scheduling or loopback luck in place of proper ordering or backpressure.