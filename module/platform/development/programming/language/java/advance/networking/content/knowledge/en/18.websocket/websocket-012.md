# WebSocket Message Size Limits, Reconnection, and Session State Recovery

## 1. The problem: an alive connection does not guarantee a correct application session

WebSocket provides a bidirectional, long-lived communication channel between client and server after the HTTP handshake. However, **WebSocket does not inherently provide** application-specific message limits, automatic reconnection on disconnect, or automatic recovery of event/session history after reconnecting.

Three related yet **distinct** needs:

1. **Message size limit:** prevent a peer from sending oversized text/binary payloads, too many fragments, or compressed data that expands beyond memory/CPU budgets. Enforce limits in **actual bytes**, not Java character counts.
2. **Reconnect:** establish a **new WebSocket connection** when the old connection is lost, with a new handshake, re-authentication, and retry/backoff control. It is not reviving the old TCP connection.
3. **Session recovery:** synchronize what the client has already processed, which events were missed, whether access permissions are still valid, and which commands the server has accepted. Requires an **application-layer protocol** such as sequence IDs, replay cursors, snapshots, acknowledgments, and idempotency.

If a client only writes `onError -> connect()` without managing data/sequences, it can **miss notifications**, **apply an event twice**, or resend an operation with incorrect side effects. If it only uses `StringBuilder.append(fragment)` with no limit, a peer can keep the application busy and consume arbitrary RAM, even if each individual frame is small.

This lesson uses Java 17 `java.net.http.WebSocket` (client API) and a **minimal loopback WebSocket server for testing**, without external libraries. The runnable Java file in section 11 demonstrates a fragmented event, unexpected TCP drop, reconnect, sequence-based resume, deduplication, and UTF-8 limit enforcement.

## 2. WebSocket frames differ from application messages

WebSocket RFC 6455 allows a **message** to be split into multiple **frames**:

```text
A text message: "seq=1|Hello"

Frame 1: opcode=TEXT,          FIN=0, data="seq=1|He"
Frame 2: opcode=CONTINUATION,  FIN=1, data="llo"

Application receives a completed text message:
  "seq=1|Hello"
```

A frame is not automatically a message. With Java `WebSocket.Listener.onText(socket, data, last)`:

- `data` is **a part of the text message provided by the decoder** as a `CharSequence`.
- `last==true` means the current part finishes the text message.
- **Do not assume one callback == one message**; you must accumulate parts or use a streaming parser.
- **Do not assume callback boundaries match wire frame boundaries**; implementations may split/coalesce differently.
- When receiving binary, `WebSocket.Listener.onBinary(socket, ByteBuffer data, boolean last)` has the same "part of a binary message" semantics.
- Control frames such as Ping/Pong/Close have separate rules and cannot be interleaved like continuation frames. Control frame payloads in RFC 6455 are **at most 125 bytes** and cannot be fragmented.

**Typical risk:** the server sends a 100 MiB message as 100,000 1 KiB fragments. If the client only checks each `data.length() <= 1024`, it can still accumulate 100 MiB in a `StringBuilder`. You must limit the **total message across all fragments**, not just a single frame or callback size.

Comparison table:

| Concept | What to limit | Where to enforce |
| --- | --- | --- |
| Frame payload size | Bytes per WebSocket frame | Network/WebSocket codec |
| **Message size** | Total bytes of all fragments belonging to **one message** | Decoder + application listener |
| Encoded/compressed size | Bytes on the wire when a compression extension is active | Codec/proxy |
| Decoded/decompressed size | Data after decompression/UTF-8 decoding | Application; prevents decompression bombs |
| In-flight message count | Number of messages being processed concurrently | Queue/worker/backpressure |
| Outbound queued bytes | Total response/request bytes waiting to be sent | Client and server send queues |
| Session backlog | Number of events retained for replay while client is offline | Session/event store |

**Do not choose limits based solely on message count.** A single 200 MiB message can be dangerous even if each client only has one in-flight message. Conversely, 100,000 100-byte messages can also saturate CPU/queues.

## 3. Limit by bytes, not `String.length()`

In Java, `String.length()` counts **UTF-16 code units**, not UTF-8 bytes on the network:

```java
String message = "é".repeat(70);
int charactersAsUtf16Units = message.length();               // 70
int utf8Bytes = message.getBytes(StandardCharsets.UTF_8).length; // 140
```

With a budget of `MAX_TEXT_BYTES=128`, a message consisting of 70 `é` characters **exceeds the limit** even though `message.length()==70`. Similarly, a Unicode supplementary character such as an emoji takes two UTF-16 code units but typically four UTF-8 bytes. This is why you **must not use `String.length()` as a byte quota**.

In Java `onText`, data has already been converted from WebSocket bytes to `CharSequence`; a callback part may end between two UTF-16 surrogate code units. Do not force each fragment into UTF-8 bytes and sum them independently if the decoder/fragment splits a surrogate pair: you may miscount or produce replacement characters. An easy-to-understand approach for **small messages**:

1. Set an **early guard threshold** based on total accumulated UTF-16 code units. For valid UTF-8 text, each code unit contributes at least one byte on the wire; if the code unit count already exceeds `MAX_TEXT_BYTES`, the total UTF-8 byte count will definitely exceed it.
2. Accumulate until `last==true`, without letting `StringBuilder` grow past the early threshold.
3. **After completion** of the message, compute `completeText.getBytes(StandardCharsets.UTF_8).length` and compare against the real byte quota.
4. If using large messages, use a **stateful streaming UTF-8 size validator across fragments** or a bounded streaming decoder/parser instead of always building a huge string. Never call `getBytes(...)` on a message that is already too large.

Snippet inside a listener, **not a standalone class**:

```java
// fields per WebSocket connection:
private static final int MAX_TEXT_BYTES = 128;
private final StringBuilder partial = new StringBuilder();

// inside onText(WebSocket socket, CharSequence fragment, boolean last):
if (fragment.length() > MAX_TEXT_BYTES - partial.length()) {
    socket.sendClose(1008, "message too large");
    return CompletableFuture.completedFuture(null);
}
partial.append(fragment);
if (last) {
    String completed = partial.toString();
    partial.setLength(0);
    if (completed.getBytes(StandardCharsets.UTF_8).length
            > MAX_TEXT_BYTES) {
        socket.sendClose(1008, "message too large");
        return CompletableFuture.completedFuture(null);
    }
    // Parse/validate completed text message here.
}
socket.request(1);
return CompletableFuture.completedFuture(null);
```

**Why use close code 1008 instead of 1009 in the Java snippet above?** Under RFC 6455, **1009** means "message too big". However, **Java 17 `java.net.http.WebSocket.sendClose(...)` lists 1009 among the status codes that callers are not allowed to send** (alongside 1002/1003/1006/1007/1010/1012/1013/1015); the API may complete the `CompletableFuture` with `IllegalArgumentException`. In this Java 17 API, use **1008 (policy violation)** when closing due to an application size policy, or `abort()` when an orderly close is not possible. Another WebSocket server implementation may send **1009** per the RFC; a Java client can still *receive* that close code. Do not write `socket.sendClose(1009, ...)` assuming Java 17 handles the limit.

**Resource note:** `sendClose(...)` only initiates the output-side close handshake; it **does not guarantee input is closed immediately**. If the peer is slow or never completes the handshake, you need a deadline followed by `abort()`/cleanup to stop resource consumption. In production code, handle failed futures, stop processing subsequent messages, and do not trigger infinite reconnects when the client itself is rejecting an over-limit peer.

## 4. Limit binary messages accurately with `ByteBuffer.remaining()`

For binary messages, `WebSocket.Listener` provides a `ByteBuffer`, making byte counting more direct:

```java
// Illustrative snippet inside WebSocket.Listener.
private static final long MAX_BINARY_BYTES = 1024 * 1024;
private long accumulatedBytes = 0;
private final ByteArrayOutputStream binary =
        new ByteArrayOutputStream();

@Override
public CompletionStage<?> onBinary(WebSocket ws,
        ByteBuffer fragment, boolean last) {
    int n = fragment.remaining();
    if (n > MAX_BINARY_BYTES - accumulatedBytes) {
        ws.sendClose(1008, "binary message limit");
        return CompletableFuture.completedFuture(null);
    }

    // Load fragment data into an upper-bounded accumulator.
    byte[] bytes = new byte[n];
    fragment.get(bytes);
    binary.write(bytes, 0, n);
    accumulatedBytes += n;

    if (last) {
        byte[] complete = binary.toByteArray();
        // Parse/validate complete binary bytes. No untrusted deserialization.
        binary.reset();
        accumulatedBytes = 0;
    }
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
```

*This snippet has fields inside a listener and requires importing `java.io.ByteArrayOutputStream`, `ByteBuffer`, `WebSocket`, `CompletionStage`, and `CompletableFuture`; it is not a standalone program.*

Important:

- Use `fragment.remaining()`, **not** `capacity()` or `limit()` alone; only the `position...limit` range holds the fragment's bytes.
- Check `n > MAX - accumulated` before adding to avoid overflow and quota overrun.
- Do not retain references to the callback's `ByteBuffer` for workers to use indefinitely without knowing its lifecycle/ownership; copy the bytes or establish a clear ownership contract.
- If the protocol supports large file streams, do not call `toByteArray()` on the whole payload; **stream into a `.part` file** with a total-size limit and checksum, then commit when the message/end-of-file protocol completes.
- An application may choose **binary streaming chunks as independent messages**. In that case, you must protect both the per-message limit and the total size/offset of the **logical file**; do not mistake each WebSocket message for the entire file.
- The WebSocket-level decoder and server must guard against malformed frames, invalid UTF-8, invalid control frames, and fragmentation abuse; the client listener is not the only control layer.

## 5. Managing receive demand and preventing overload on Java WebSocket

Java 17 `WebSocket.Listener` uses a **demand** mechanism via `webSocket.request(n)`. In `onOpen`, you typically start with:

```java
@Override
public void onOpen(WebSocket socket) {
    socket.request(1);
}
```

After completing a callback when you still want to receive more:

```java
socket.request(1);
```

This does not "send an HTTP request"; it increments the number of receive callbacks the WebSocket client may deliver to the listener. This supports **callback-layer flow control**:

- Do not call `request(...)` unboundedly without a budget.
- For small messages processed quickly and synchronously, the listener can process one part and then call `request(1)`.
- If handing messages off to a worker/queue, only call `request(1)` when the queue has space or the required work has completed; set upper bounds on both messages and work queues.
- Avoid running blocking database work or heavy CPU processing inside WebSocket client callbacks; use a bounded executor, track ownership, and drive demand according to state.
- Demand is not a **hard cap on all network/JDK buffers**. Both client and server still need frame/message limits, byte quotas, and total connection limits.
- WebSocket send has an asynchronous API returning `CompletableFuture<WebSocket>`. **Future completion means bytes have been handed off per the API contract, not that the peer has committed the business operation**. A separate **application-layer ACK** is required.

**Faulty** example:

```java
// ANTI-PATTERN: a slow peer and fast producer can queue many sends.
for (String event : hugeEventStream) {
    socket.sendText(event, true); // No bound on outstanding queue whatsoever.
}
```

In practice, sending frames/messages concurrently without respecting prior state can throw exceptions or queue up depending on the API/implementation. The right approach is to **serialize outbound sends** via a bounded queue, enqueue only when budget allows, chain/handle completions properly, and handle failures. With `sendBinary(ByteBuffer,...)`, do not mutate the buffer while the send future is still using it.

**Multiple independent limits must be enforced:** max bytes/message, max fragment count, max messages/s, max concurrent sessions, max queued send bytes, max in-flight jobs, and operation timeouts. A single `MAX_MESSAGE_BYTES` does not solve the case of 1,000 small messages per second.

## 6. Connection lifecycle: reconnecting means a new connection

WebSocket has no `reconnect()` button in the Java 17 API. When a socket drops, the client **must perform a new handshake**:

```text
DISCONNECTED
     |
     v
CONNECTING (new HTTP Upgrade / TLS handshake)
     |
     v
AUTHENTICATING / NEGOTIATING APP VERSION
     |
     v
RESUMING (cursor, server validation, replay/snapshot)
     |
     v
LIVE (application events)
     |
     +---- network failure ----> RETRY_WAIT ----> CONNECTING
     |
     +---- auth revoked -------> STOP; ask for fresh credentials
     |
     +---- explicit logout ----> CLOSED; no reconnect
```

These states answer two questions:

1. **Is the connection ready?** The HTTP/WebSocket handshake succeeded and the connection is open.
2. **Can the application session operate normally?** Auth passed, replay/snapshot passed, and the client knows its state is up-to-date with no gaps.

The `onOpen` method is invoked when the WebSocket connection opens, but **does not prove the application session has recovered**. If the UI immediately displays "synced", it may miss data from while it was offline.

When a new connection opens:

- Re-authenticate using an allowed mechanism, including a fresh token if the old one expired.
- Send the application protocol version/negotiation.
- Send a well-scoped **resume cursor** (e.g., `lastAppliedSequence`), along with session/stream identity and protection token per design.
- Wait for the server to return `RESUME_OK` / replay or `SNAPSHOT_REQUIRED` before considering state synchronized.
- Only after synchronization should you perform operations that depend on fresh state.

**TCP/WebSocket reconnection does not preserve server in-memory sessions.** The server may have restarted, deployed to another node, lost in-memory subscriptions, or pruned its replay log. A durable "reconnect" mechanism requires an **event store/shared session store** or reloadable snapshots.

## 7. When to reconnect, when to stop permanently?

Not every close should trigger a reconnect. Evaluate the categories:

| Scenario | Recommended decision |
| --- | --- |
| Wi-Fi drop/TCP reset/EOF without a Close frame | Retry with backoff and a limit |
| Server restart/node failover | Retry after backoff, then resume |
| Server returns close `1001 Going Away` | Depends on contract, usually reconnect with delay |
| Server reports overload/retry-after via app protocol | Respect server delay, backoff/jitter |
| Normal close `1000` when user explicitly logs out | **Do not** reconnect |
| Auth invalid/forbidden during handshake (401/403) | Stop and prompt for valid token/login; do not retry infinitely |
| Policy violation `1008` due to client sending invalid data | Do not repeatedly retry the same payload |
| Message too large `1009` received from server | Fix payload/limit; do not loop resending verbatim |
| Incompatible app protocol version | Stop, notify client to update or negotiate supported version |
| Intentional offline mode or application shutdown | Cancel timers/jobs; do not open new connections |
| A request/command was sent but not yet ACKed | State is **unknown**; do not blindly resend as unprocessed |

**Close code `1006` is an observed code for abnormal connection loss, not a valid code to send in a Close frame.** Likewise, transport errors may be reported via `onError` instead of `onClose`; use a shared handler path and avoid scheduling retries **twice**.

## 8. Backoff, jitter, retry budget, and generation ID

Retrying continuously without delay can hit an already overloaded server with thousands of simultaneous client reconnects (thundering herd). A production strategy:

```text
baseDelay = 250 ms
maxDelay  = 30 s
attempt:  0, 1, 2, ...
cap = min(maxDelay, baseDelay * 2^attempt)
delay = random(0, cap)      // full jitter, for example
```

Essentials to include:

- **Exponential backoff + jitter** to reduce synchronized reconnect waves.
- **Attempt/duration cap** or app-state-based retry policy; when budget is exhausted, surface an actionable error.
- **Reset backoff only when the connection is stable and resume succeeds** for long enough, not merely on `onOpen`.
- Respect server-provided retry intervals if defined by the protocol and authenticated.
- A scheduler and a **connection attempt generation ID** to ignore late callbacks from old sockets.
- Guard **retry scheduled once** per attempt using `AtomicBoolean`/state machine, since `onError`/`onClose`/connect-future failure can all report the same failure.
- When the user logs out, cancel pending retries, close the socket, and cancel work; never let a timer "resurrect" a logged-out session.

Illustrative code snippet from the runnable program:

```java
void retry() {
    if (owner.finished.isDone()
            || !retryQueued.compareAndSet(false, true)) return;
    owner.timers.schedule(owner::connect, 100,
            TimeUnit.MILLISECONDS);
}
```

**This is a fixed 100 ms timer for localhost testing, not a production configuration.** Real systems need exponential backoff/jitter, idle timeouts, auth state, throttling, and network-awareness.

If using a timer thread pool, do not spawn an unbounded new thread for every retry; use a `ScheduledExecutorService` with a clear lifecycle. On application shutdown, shut down the timer so it does not keep the JVM alive or leak callbacks.

## 9. Protocol design for message and state recovery

WebSocket has no universal replay protocol for all apps. A minimal schema typically needs:

```text
Client -> Server:
  HELLO {appProtocolVersion, sessionId, resumeToken, lastAppliedSeq}

Server -> Client:
  RESUME_OK {streamId, epoch, replayFromSeq}
  EVENT {streamId, epoch, seq, eventId, payload}
  ... EVENT ...

Client -> Server:
  ACK {streamId, epoch, lastDurablyAppliedSeq}

When history is no longer available:
  RESYNC_REQUIRED {reason, minAvailableSeq, snapshotVersion}

Client:
  fetch snapshot / request full state from a reliable channel
  apply snapshot atomically
  start replaying events after snapshotVersion
  transition state to SYNCED then LIVE
```

Fields to distinguish:

| Field | Purpose |
| --- | --- |
| `sessionId` | Identifies the application session allowed to resume; not inferred from TCP connection |
| `resumeToken` | Proves authorization to resume the session; must be protected, expired/rotated, and scoped |
| `streamId` | Sequence scope; prevents mixing two streams from two resources |
| `epoch/generation` | Distinguishes sequences after restart/reset/topology change |
| `seq` | Increasing sequence number per stream, used to detect duplicates/gaps |
| `eventId` | Event identifier for long-term idempotency/dedup |
| `lastDurablyAppliedSeq` | Cursor actually **committed** by the client (not merely seen) |
| `snapshotVersion` | Full-state baseline for replaying deltas |
| `ACK` | **Application-layer** acknowledgment, not the WebSocket transport send future |
| `retention window` | History window the server can replay |

**Normal flow:**

```text
Server stored events: #41, #42, #43, #44
Client lastAppliedSeq: 41
Connection lost while #42..#44 were produced
      |
      v
New WebSocket handshake + auth
      |
      v
Client HELLO(lastAppliedSeq=41)
      |
      v
Server replays #42, #43, #44 in order
      |
      v
Client validates, applies and durably commits each event
      |
      v
Client ACK 44
      |
      v
LIVE from #45 onward
```

**Lost ACK case:** the server may resend #44 even though the client already committed #44. Therefore, the client must detect `seq<=lastAppliedSeq` to **avoid applying the event twice**, then ACK the current cursor. Never mistake a completed `sendText("ACK 44")` future for the server having received and persisted that ACK.

**Gap case:** if the client is at seq41 and receives seq44 before 42/43, do not skip ahead to 44. You must buffer/reorder with a bound or request **resync/snapshot**, depending on the contract. If event #42 has expired from the replay log, the server must return `RESYNC_REQUIRED` instead of claiming "resume succeeded" and dropping data.

## 10. Exactly-once is an application-layer requirement, not a built-in WebSocket feature

In distributed systems, disconnects can occur **after the server processes a command but before the client sees the ACK**:

```text
Client: SEND transferFunds(requestId=X)
Server: commit transferFunds(X)
TCP breaks before ACK
Client cannot know whether X committed
```

Reconnecting and resending a **transfer command without an idempotency key** can cause double processing. You need:

1. The client generates a stable **request ID/idempotency key** for a logical operation.
2. The server stores state/response by key within the appropriate user/tenant scope and retention period, with transactions/commits ensuring it is not executed twice.
3. On reconnect, the client queries the result or resends with the **same ID**, rather than generating a new ID for the same action.
4. The client updates its cursor **only after application state is durably applied**, so event replay does not skip side effects.
5. If business logic requires strict ordering, process events sequentially or use sequence-based reordering; multiple parallel workers can finish out of order.

**At-least-once replay + idempotency/dedup** can achieve effectively once business semantics within a designed transaction boundary; WebSocket transport does not guarantee exactly-once delivery. Do not promise "each event is received exactly once" when networks drop and ACKs can be lost.

For UIs that do not require durability, keeping `lastAppliedSeq` in RAM and treating restart state loss as needing a fresh snapshot may suffice. For finance, orders, or critical workflows, cursor/dedup and business processing must live in a durable store/transaction.

## 11. Complete Java 17 example: fragmentation, disconnect, resume, deduplication

The example below uses **pure JDK**, including:

- Java `HttpClient.newWebSocketBuilder()` to create a WebSocket client (Java 17 API).
- A **minimal loopback test server** using `ServerSocket` solely to simulate an HTTP Upgrade WebSocket handshake and a few **small frames**. It does not fully support RFC 6455, does not check authentication or extensions, and does not use TLS; **it must not be used as a production WebSocket server**.
- First server connection: client sends `RESUME 0`; server sends event #1 in **two frames** (TEXT FIN=0 then CONTINUATION FIN=1), waits for `ACK 1`, then abruptly closes TCP **without sending a Close frame**.
- Client detects disconnect, schedules a 100 ms reconnect for testing, opens a new connection, and sends `RESUME 1`.
- Second server connection intentionally resends event #1 then event #2. Client ignores duplicate #1, processes #2, sends ACK 2, and then the server sends Close 1000.
- The listener enforces `MAX_TEXT_BYTES=128` for the entire text message, checking both total UTF-16 code units and UTF-8 bytes. **In Java 17, when closing due to policy violation, use 1008 instead of 1009** as explained in section 3.
- At the end, the program runs a `"é".repeat(70)` check to remind that 70 code units are still 140 UTF-8 bytes, exceeding the 128 limit.

**Filename: `WebSocketResumeDemo.java`**

```java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Base64;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

public final class WebSocketResumeDemo {
    static final int MAX_TEXT_BYTES = 128;

    static final class Client {
        final HttpClient http = HttpClient.newHttpClient();
        final ScheduledExecutorService timers =
                Executors.newSingleThreadScheduledExecutor();
        final URI uri;
        final AtomicLong lastApplied = new AtomicLong(0);
        final AtomicInteger attempts = new AtomicInteger(0);
        final CompletableFuture<Void> finished = new CompletableFuture<>();

        Client(URI uri) {
            this.uri = uri;
        }

        void connect() {
            if (finished.isDone()) return;
            int attempt = attempts.incrementAndGet();
            if (attempt > 4) {
                finished.completeExceptionally(
                        new IOException("Reconnect budget exhausted"));
                return;
            }
            WsListener listener = new WsListener(this);
            http.newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .buildAsync(uri, listener)
                    .whenComplete((ws, error) -> {
                        if (error != null) listener.retry();
                    });
        }

        void stop() {
            timers.shutdownNow();
        }
    }

    static final class WsListener implements WebSocket.Listener {
        final Client owner;
        final StringBuilder pending = new StringBuilder();
        final AtomicBoolean retryQueued = new AtomicBoolean(false);

        WsListener(Client owner) {
            this.owner = owner;
        }

        @Override
        public void onOpen(WebSocket socket) {
            socket.request(1);
            String resume = "RESUME " + owner.lastApplied.get();
            System.out.println("client " + resume);
            socket.sendText(resume, true).whenComplete((ok, ex) -> {
                if (ex != null) retry();
            });
        }

        @Override
        public CompletionStage<?> onText(WebSocket socket,
                CharSequence fragment, boolean last) {
            if (fragment.length() > MAX_TEXT_BYTES - pending.length()) {
                // JDK 17 WebSocket.sendClose does not allow status 1009.
                socket.sendClose(1008, "message too large");
                owner.finished.completeExceptionally(
                        new IOException("Text exceeds safe character cap"));
                return CompletableFuture.completedFuture(null);
            }
            pending.append(fragment);
            if (last) {
                String message = pending.toString();
                pending.setLength(0);
                if (message.getBytes(StandardCharsets.UTF_8).length
                        > MAX_TEXT_BYTES) {
                    socket.sendClose(1008, "message too large");
                    owner.finished.completeExceptionally(
                            new IOException("Text exceeds UTF-8 byte cap"));
                    return CompletableFuture.completedFuture(null);
                }
                try {
                    int separator = message.indexOf('|');
                    if (!message.startsWith("seq=") || separator <= 4) {
                        throw new IOException("Bad application message");
                    }
                    long seq = Long.parseLong(
                            message.substring(4, separator));
                    String text = message.substring(separator + 1);
                    long lastApplied = owner.lastApplied.get();
                    if (seq <= lastApplied) {
                        System.out.println("duplicate seq=" + seq
                                + " ignored");
                    } else if (seq == lastApplied + 1) {
                        // Demo commits in memory. Production commits durably
                        // before advancing the cursor and sending ACK.
                        owner.lastApplied.set(seq);
                        System.out.println("applied seq=" + seq
                                + " text=" + text);
                    } else {
                        throw new IOException("Gap: snapshot required");
                    }
                    long acknowledged = owner.lastApplied.get();
                    socket.sendText("ACK " + acknowledged, true)
                            .whenComplete((ok, ex) -> {
                                if (ex != null) retry();
                            });
                } catch (Exception error) {
                    owner.finished.completeExceptionally(error);
                    socket.sendClose(1008, "invalid event");
                    return CompletableFuture.completedFuture(null);
                }
            }
            socket.request(1);
            return CompletableFuture.completedFuture(null);
        }

        void retry() {
            if (owner.finished.isDone()
                    || !retryQueued.compareAndSet(false, true)) return;
            System.out.println("connection lost: reconnecting");
            owner.timers.schedule(owner::connect, 100,
                    TimeUnit.MILLISECONDS);
        }

        @Override
        public CompletionStage<?> onClose(WebSocket socket,
                int code, String reason) {
            if (code == 1000 && owner.lastApplied.get() == 2) {
                System.out.println("normal close after seq=2");
                owner.finished.complete(null);
            } else {
                retry();
            }
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket socket, Throwable error) {
            retry();
        }
    }

    static int read(InputStream in) throws IOException {
        int value = in.read();
        if (value < 0) throw new EOFException("Unexpected EOF");
        return value;
    }

    static String readHeaders(InputStream in) throws IOException {
        ByteArrayOutputStream result = new ByteArrayOutputStream();
        int a = -1, b = -1, c = -1, d;
        while (result.size() < 8192) {
            d = read(in);
            result.write(d);
            if (a == '\r' && b == '\n'
                    && c == '\r' && d == '\n') {
                return result.toString(StandardCharsets.US_ASCII);
            }
            a = b; b = c; c = d;
        }
        throw new IOException("Too many header bytes");
    }

    static void handshake(InputStream in, OutputStream out)
            throws Exception {
        String request = readHeaders(in);
        String key = null;
        for (String line : request.split("\r\n")) {
            if (line.regionMatches(true, 0,
                    "Sec-WebSocket-Key:", 0, 18)) {
                key = line.substring(18).trim();
            }
        }
        if (key == null) throw new IOException("No WebSocket key");
        byte[] raw = MessageDigest.getInstance("SHA-1").digest(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                        .getBytes(StandardCharsets.US_ASCII));
        String accept = Base64.getEncoder().encodeToString(raw);
        out.write(("HTTP/1.1 101 Switching Protocols\r\n"
                + "Upgrade: websocket\r\n"
                + "Connection: Upgrade\r\n"
                + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n")
                .getBytes(StandardCharsets.US_ASCII));
        out.flush();
    }

    static void writeFrame(OutputStream out, int opcode,
            boolean fin, byte[] payload) throws IOException {
        if (payload.length >= 126)
            throw new IllegalArgumentException("Demo frame too large");
        out.write((fin ? 0x80 : 0) | opcode);
        out.write(payload.length); // Server frames are never masked.
        out.write(payload);
        out.flush();
    }

    static void writeText(OutputStream out, String text)
            throws IOException {
        writeFrame(out, 1, true, text.getBytes(StandardCharsets.UTF_8));
    }

    static String readClientText(InputStream in) throws IOException {
        int first = read(in);
        int second = read(in);
        int opcode = first & 0x0f;
        int n = second & 0x7f;
        boolean masked = (second & 0x80) != 0;
        if (opcode != 1 || !masked || n >= 126) {
            throw new IOException("Unexpected demo client frame");
        }
        byte[] mask = in.readNBytes(4);
        byte[] payload = in.readNBytes(n);
        if (mask.length != 4 || payload.length != n)
            throw new EOFException();
        for (int i = 0; i < n; i++)
            payload[i] = (byte) (payload[i] ^ mask[i % 4]);
        return new String(payload, StandardCharsets.UTF_8);
    }

    static void runServer(ServerSocket server) throws Exception {
        for (int session = 1; session <= 2; session++) {
            try (Socket peer = server.accept()) {
                peer.setSoTimeout(5000);
                InputStream in = peer.getInputStream();
                OutputStream out = peer.getOutputStream();
                handshake(in, out);
                String resume = readClientText(in);
                if (!resume.equals("RESUME " + (session - 1)))
                    throw new IOException("Bad cursor: " + resume);
                if (session == 1) {
                    writeFrame(out, 1, false, "seq=1|He".getBytes(
                            StandardCharsets.UTF_8));
                    writeFrame(out, 0, true, "llo".getBytes(
                            StandardCharsets.UTF_8));
                    if (!"ACK 1".equals(readClientText(in)))
                        throw new IOException("Missing ACK 1");
                    // Drop underlying TCP without a WebSocket CLOSE frame.
                } else {
                    writeText(out, "seq=1|Hello"); // At-least-once duplicate.
                    writeText(out, "seq=2|World");
                    String ack;
                    do {
                        ack = readClientText(in);
                    } while ("ACK 1".equals(ack));
                    if (!"ACK 2".equals(ack))
                        throw new IOException("Missing ACK 2");
                    writeFrame(out, 8, true, new byte[]{3, (byte) 232});
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket server = new ServerSocket()) {
            server.bind(new InetSocketAddress(
                    InetAddress.getByName("127.0.0.1"), 0));
            server.setSoTimeout(5000);
            AtomicReference<Throwable> serverError = new AtomicReference<>();
            Thread serverThread = new Thread(() -> {
                try {
                    runServer(server);
                } catch (Throwable error) {
                    serverError.set(error);
                }
            }, "loopback-ws-server");
            serverThread.start();

            URI uri = URI.create("ws://127.0.0.1:"
                    + server.getLocalPort() + "/events");
            Client client = new Client(uri);
            try {
                client.connect();
                client.finished.get(10, TimeUnit.SECONDS);
            } finally {
                client.stop();
            }
            serverThread.join(5000);
            if (serverThread.isAlive())
                throw new IllegalStateException("Server thread stuck");
            if (serverError.get() != null)
                throw new IllegalStateException(
                        "Server failed", serverError.get());
            int utf8Size = "é".repeat(70).getBytes(
                    StandardCharsets.UTF_8).length;
            System.out.println("UTF-8 size test: " + utf8Size
                    + " bytes > limit " + MAX_TEXT_BYTES
                    + ": " + (utf8Size > MAX_TEXT_BYTES));
        }
    }
}
```

**Run with JDK 17:**

```bash
javac --release 17 WebSocketResumeDemo.java
java WebSocketResumeDemo
```

**Actual stdout (from a tested run on Java 17):**

```text
client RESUME 0
applied seq=1 text=Hello
connection lost: reconnecting
client RESUME 1
duplicate seq=1 ignored
applied seq=2 text=World
normal close after seq=2
UTF-8 size test: 140 bytes > limit 128: true
```

### 11.1. Output explanation and testing limitations

- `client RESUME 0`: no events applied yet, so the client requests to resume from cursor 0.
- `applied seq=1 text=Hello`: the server sends **two frames**, and the client accumulates callbacks until `last==true` and processes one complete message.
- `connection lost: reconnecting`: the server closes TCP abruptly **without** sending a WebSocket Close frame. The client goes through `onError` and schedules a retry.
- `client RESUME 1`: a brand-new WebSocket connection, sending the processed cursor.
- `duplicate seq=1 ignored`: the server simulates at-least-once delivery; the client does not reapply the duplicate event.
- `applied seq=2 text=World`: the missing event is processed continuously in sequence order.
- `normal close after seq=2`: the server sends close 1000 to end the test; the client treats it as successful completion of the task and does not retry.
- `UTF-8 size test: 140 bytes > limit 128: true`: 70 `é` characters occupy 140 UTF-8 bytes. This line tests the **byte limit rule**, not an oversized WebSocket message sent by the server in the test.

**Intentional scope:** the `ServerSocket` server only supports two handshakes, small frames, simple masked client text, and a few specific opcodes. It is **not a fully compliant WebSocket server**: it does not handle full client fragmentation, extended payload lengths, TLS, Ping/Pong, origin validation, authentication, compression, HTTP header security, or scale. For production, use a tested WebSocket framework/server and configure max frame/message limits at both codec and business layers. The demo client uses an **in-memory** cursor, a 100 ms timer, and no token; this is **not durable session recovery** or a production retry policy.

**About the 1008 limit:** the test only emits valid small messages and checks the byte count of the `é` string afterward; it **does not trigger the `WebSocket.sendClose(1008,...)` branch with an oversized message**. That branch relies on the Java 17 API contract and must be tested separately in production integration tests. Do not claim that stdout line proves wire-level 1008 close frame behavior.

## 12. Production protocol additions: HELLO, ACK, snapshot, and cutover

The demo uses a simple text payload:

```text
Client: RESUME 1
Server: seq=1|Hello
Server: seq=2|World
Client: ACK 1
Client: ACK 2
```

A real-world system should have a clearer schema:

```json
{"type":"HELLO","protocol":2,"streamId":"orders-42","epoch":"e17",
 "lastAppliedSeq":1042,"resumeToken":"<opaque-secret-not-logged>"}

{"type":"RESUME_OK","streamId":"orders-42","epoch":"e17",
 "replayFromSeq":1043}

{"type":"EVENT","streamId":"orders-42","epoch":"e17","seq":1043,
 "eventId":"evt-...","payload":{"orderId":"42","status":"SHIPPED"}}

{"type":"ACK","streamId":"orders-42","epoch":"e17","seq":1043}
```

*This JSON is a custom protocol payload example, not a mandatory WebSocket format.* Token/ID values are illustrative; never use real secrets.

**Snapshot + delta requires a consistent cutover**. For example, given a snapshot at sequence #500, the server must ensure:

1. The snapshot reflects state at a consistent point #500.
2. Replay of events #501 onward is retained from an existing log.
3. There is no "gap" between taking the snapshot and starting the live subscription.
4. The client must not apply event #501 before snapshot #500 has been committed.
5. When replay finishes and the live stream continues, new events must be appended after the cursor with ordering and retention safeguards.

If the event log only retains back to #600 while the client is at #200, the server must signal that a snapshot is required instead of silently sending #601 and marking the session synced. If permissions change, the server must re-verify stream read authorization before replaying, rather than treating the resume token as an indefinite pass.

## 13. Multi-node connections: where does state live after reconnect?

Suppose a client connects through a load balancer:

```text
Client
   |
   v
Load Balancer
   |------ Node A: old connection, client received up to #17
   |
   +------ Node B: new connection after reconnect
                    |
                    +--> Shared event log / database
                    +--> Shared session or resume metadata
                    +--> Snapshot store
```

If Node B only keeps events in RAM starting from when it booted, it cannot replay events #18 and #19 from Node A. You need one of these strategies:

- **Shared durable event log** per stream/user (with offset/sequence), readable and replayable by any node.
- **Snapshot + replay** with explicit log retention and versioning.
- **Session affinity** can reduce node switches, but **does not guarantee recovery** on node failure, redeployment, or autoscaling.
- **Pub/sub with replay** or a database change log with managed ordering and retention; do not confuse ephemeral pub/sub with a durable event store.

Protect replay with per-stream/per-tenant authorization: if the server only looks at `lastSeq=7` and lets any client read stream history, that is a data exposure vulnerability. Tokens and auth must verify specific access rights, with expiration/revocation.

## 14. Disconnect while sending commands: outbox and UNKNOWN state

It is not only server→client events that need recovery. Client→server commands also have an uncertain region:

```text
Client: sendText("CREATE_ORDER idempotencyKey=X")
Network: bytes reach server
Server: commit order X
Network: disconnect before response ACK
Client: sendText future may complete or fail, but result unknown
```

Appropriate design:

1. Write the command to the client's **durable outbox** when required by business logic.
2. Attach a unique `commandId`/`idempotencyKey` for the logical action.
3. On reconnect, query the command's status or resend with the **same key**, without creating a new command.
4. The server stores the idempotency result long enough to prevent duplicate retries; the transaction must be atomic with the business side effect.
5. After receiving a reliable **application ACK**, the client updates the outbox state.
6. Do not treat `sendText`'s `CompletableFuture<WebSocket>` as a business ACK.

If the app only sends "typing..." signals or droppable telemetry, you do not necessarily need a durable outbox; you can simply resend the latest state. Choose based on the **semantics of each message type** rather than forcing a heavy protocol on everything.

## 15. Authentication, wss://, and session information

When using WebSocket in production:

- Prefer **`wss://`** for TLS encryption and server certificate/hostname verification; `ws://127.0.0.1` in the demo is for loopback only.
- Both the HTTP handshake and application protocol must validate authentication. Resume tokens must have sufficient randomness, scope, expiration, rotation, and revocation; never trust a client-sent sequence number alone.
- Avoid putting secret bearer/resume tokens in URL query strings, as URLs are easily logged in proxies/servers/access logs. Use a token transport mechanism appropriate to your server/client and security policy; Java `WebSocket.Builder` has an API to configure HTTP request headers, though header restrictions and redirects must be handled.
- Browser WebSockets typically carry cookies per browser policy; servers must check **Origin** and protect against cross-site WebSocket hijacking when using cookie auth. A Java client is not a browser, so CORS/SameSite are not a firewall replacing backend authorization.
- Validate and limit messages **before** parsing JSON/XML or deserializing, because peer-supplied content-type/payloads are untrusted.
- If WebSocket sits behind a proxy/load balancer, check idle timeouts, WebSocket upgrade forwarding, maximum frame/message sizes, session affinity, and TLS termination modes.
- When a session is logged out or a token is revoked, close the corresponding connections and **do not auto-retry** with the revoked token. Clear outbox/replay cursors according to data policy.
- Minimize information returned in close reasons; do not expose tokens, stack traces, or sensitive payloads in protocols/logs.

**Size limits are not complete security.** A valid 5 KB message can still be deeply nested JSON, a malicious payload, an unauthorized command, or SQL injection. You must validate schemas, authorization, and rate limits.

## 16. Heartbeat, half-open connections, and deadlines

A TCP/WebSocket connection can appear "open" in the JVM even though the peer or proxy has lost the path (half-open). Heartbeats/deadlines are needed to detect this:

- WebSocket has **Ping/Pong control frames**; Java `WebSocket.sendPing(ByteBuffer)` sends a Ping, and `WebSocket.Listener.onPong(...)` receives a Pong. In the JDK WebSocket implementation, receiving a Ping may automatically send a corresponding Pong per the API, but heartbeat/timeout policy is still decided by the application.
- Ping/Pong payloads are at most **125 bytes** per the WebSocket protocol.
- Applications can use **application heartbeat messages** when measuring backend/business session health, distinct from whether the TCP/WebSocket transport is alive.
- Track the timestamp of the latest Pong or application reply and enforce a deadline, instead of waiting for a very long TCP timeout.
- Do not use heartbeats as a substitute for replay/resume. An alive connection does not prove no events were dropped due to bugs or queue overflows.

In Java, note that `sendPing` returns a future for **sending the ping**, not a future proving a **Pong was received**. If you need to check liveness, include a nonce/sequence in the Ping payload and match the corresponding Pong in the listener. Manage ping rates to avoid self-inflicted floods and handle proxy/server idle timeouts appropriately.

## 17. Limits with compression, binary/files, and complex payloads

Applications may enable WebSocket compression extensions such as permessage-deflate. When compression is active:

```text
Uncompressed logical event  = 15 MiB
Compressed WebSocket bytes  = 100 KiB
Frame size limit            = 2 MiB
Application message limit   = 1 MiB
```

Even though the wire payload is below the frame cap, **the 15 MiB decoded message still exceeds the 1 MiB application cap**. You must limit **decompressed data**, CPU, and expansion ratios. Do not rely only on the HTTP handshake `Content-Length`; once WebSocket is upgraded, WebSocket messages are no longer framed by HTTP `Content-Length`.

For file transfer over WebSocket:

- Split into **application chunks** with offset, file ID, total expected size, and digest (if trusted).
- Limit each chunk/message and the total file; stream output to a temporary file rather than buffering everything in RAM.
- Distinguish transport continuation frames from **application chunks**: continuation frames belong to the same WebSocket message, whereas application chunks may be multiple WebSocket messages.
- Verify offsets, sequences, checksums, permissions, quotas, deadlines, and forbid path traversal when saving files.
- On reconnect, resume only from the committed offset; if the server resends an old chunk, deduplicate/verify it. Never blindly append new data to a file of a different version.
- Reset parsers/partial messages when a connection dies: an incomplete WebSocket message **cannot** be continued by a continuation frame on a new connection.

In particular, **a disconnect in the middle of a fragmented message** means that message is incomplete; discard the old connection's partial builder. The server must replay **from an application event/message boundary with a stable ID**, not try to stitch new raw frames onto old fragments.

## 18. Observability: measuring failures and data loss

Key operational metrics:

| Metric | Why it is needed |
| --- | --- |
| `websocket_active_connections` | Detect high connection counts / connection leaks |
| `ws_handshake_failures_by_reason` | Auth/TLS/upgrade/proxy problems |
| `reconnect_attempts` / `reconnect_delay_ms` | Reconnection storms, exponential backoff |
| `last_applied_seq` / `last_acked_seq` | Track session progress |
| `replay_events_total` / `duplicates_ignored_total` | Quality of at-least-once recovery |
| `gap_detected_total` / `resync_required_total` | Detect log loss or inconsistency |
| `message_bytes_in/out`, `oversize_rejections_total` | Tune size caps and prevent abuse |
| `fragment_count_per_message` | Detect fragmentation abuse |
| `pending_outbound_bytes` / `worker_queue_depth` | Backpressure, RAM pressure |
| `ping_rtt_ms` / `last_pong_age_ms` | Detect half-open connections and network latency |
| `application_ack_latency_ms` | From event/command to durable processing |
| `session_recovery_duration_ms` | Time from handshake to SYNCED |

Log structured fields with `connectionGeneration`, `streamId`, `epoch`, event IDs, and close/error classifications; **never log `resumeToken`, `Cookie`/`Authorization` headers, or personal payloads**. Measure reconnect success rate separately from **session resume** success rate. If reconnects keep succeeding but sessions never synchronize, a "connection up" dashboard is overly optimistic.

Test **clock drift** between nodes if the protocol uses `expiresAt`; sequences/cursors should not rely on the client clock as the sole source of ordering.

## 19. Mandatory release test matrix

| Test | Input/scenario | Expected outcome |
| --- | --- | --- |
| Short message | 10 ASCII bytes | Accepted, parsed correctly |
| Multi-byte UTF-8 text | 70 × `é` = 140 UTF-8 bytes, limit 128 | Rejected per byte quota |
| Fragmented text | One message across 2+ frames/callbacks | Parsed only when `last=true`; correct content |
| Fragmentation flood | Thousands of tiny fragments in one message | Rejected/timed out when budget exceeded |
| Binary limit | Total `remaining()` exceeds MAX | No further accumulation, closed/aborted per policy |
| Invalid UTF-8 | Malformed WebSocket text | WebSocket implementation rejects per protocol |
| Compression bomb | Tiny compressed input, huge decoded payload | Rejected by decoded-size quota |
| Server TCP reset | Disconnect without Close frame | Retry with backoff, reconnect once per failure |
| Authentication error | Handshake 401/403, expired credential | Stop or refresh per policy; no infinite loop |
| Logout | User explicitly closes | No automatic reconnect |
| Duplicate event | Replay #5 when #5 already committed | Not applied twice, ACK cursor |
| Missing event | Receive #8 while expecting #6 | Detect gap, snapshot/replay, do not "skip" |
| Replay retention expired | Server only has #100+, client at #20 | `RESYNC_REQUIRED`, fresh snapshot |
| ACK lost | Server resends already committed event | Dedup, idempotent state |
| Crash during processing | Event read but not yet committed | Cursor not advanced, replay reprocesses safely |
| Side-effect command | Request ID X committed, ACK lost | Replay result/idempotency, no duplicate side effect X |
| Session switching | New connection routed to another node | Shared event log/state, proper scope |
| Proxy idle timeout | Long period with no traffic | Ping/Pong/deadline, reconnect |
| Slow reader | Client does not request callbacks fast enough | Bounded queue and server backpressure |
| Slow writer | Large send futures/backlog | Bounded outbound queue, failure policy |
| Rapid retry | Thousands of clients reconnecting simultaneously | Jitter/backoff, rate limit |
| Stale callback | Old WebSocket completes after new generation | Generation guard, does not overwrite new cursor |
| Resume token stolen | Token used by another user | Auth/scope reject, revoke token |

Testing should combine **unit parser tests**, **integration tests against a compliant WebSocket server**, network fault injection (disconnect/reset/delay/duplicate/reorder), and load tests measuring RAM/CPU/queues. Do not test only the happy path.

## 20. Common mistakes

| Mistake | Consequence | Solution |
| --- | --- | --- |
| Limiting only frames, not messages | Fragmentation can add up to huge payloads | Accumulate across the entire message |
| Using `String.length()` as byte count | UTF-8 text exceeds quota | Count UTF-8 bytes accurately, keep bounded buffer |
| Concatenating text then calling `getBytes()` without prior limit | Out-of-memory before detecting oversize | Early char cap + final byte cap |
| Treating each `onText` callback as a full message | Lost/mis-parsed fragmented messages | Accumulate until `last==true` |
| Keeping partial messages across reconnects | Merges data from two different connections | Discard partials on socket loss, replay message |
| Calling Java 17 `sendClose(1009)` | API marks 1009 as illegal | Use 1008 policy close/abort, distinguish RFC 1009 |
| Relying solely on `request(1)` to cap all buffers | Ignores queue/network/codec limits | Bounded processing + server max size |
| Reconnecting immediately in a tight loop | Reconnect storm | Backoff, jitter, retry budget |
| Both `onError` and `onClose` scheduling connect | Multiple live sockets unintentionally | Scheduled-once/generation guard |
| Treating `onOpen` as data-synchronized state | Events missed during offline gap | Separate HELLO/RESUME/SNAPSHOT and SYNCED |
| Saving cursor upon receiving bytes, before commit | Crash loses actual event | Advance cursor after durable apply |
| Resending non-idempotent command with a new ID | Side effect executed twice | Stable idempotency key + server result store |
| No replay retention or snapshot | Unable to recover after long offline period | `RESYNC_REQUIRED` + valid snapshot |
| Treating send future as business ACK | Cannot determine commit status | Application-level ACK |
| Retrying failed auth infinitely | Overload and stuck broken session | Refresh/token policy, stop on terminal error |
| Putting sensitive tokens in URL query | Leaked in logs/proxies/browser history | Trusted header/auth channel, do not log secrets |
| Using `ws://` for real sessions outside loopback | Data/session can be eavesdropped | `wss://`, TLS validation |
| Not limiting decompressed content | Decompression bomb | Limit decoded bytes/time |
| Using a single sequence across arbitrary stream resets | Wrong dedup when epoch changes | `streamId` + `epoch` + `seq` |
| Building a raw WebSocket server for production | RFC/security/extended-frame bugs | Server framework with max limits and auth |

## 21. Self-check exercises

**Exercise 1.** A 2 MiB WebSocket text message is sent as 2,048 1 KiB fragments. Is checking only each `onText(...).data.length() <= 1024` sufficient? Over what scope must the limit be accumulated?

**Exercise 2.** `String message = "é".repeat(70)` with a 128-byte limit. What is `message.length()`? How many UTF-8 bytes is it? Should it be rejected?

**Exercise 3.** A server sends a text message via a TEXT frame with FIN=0 and a CONTINUATION frame with FIN=1. When should the client listener parse it, and what does `last` in `onText` indicate?

**Exercise 4.** A Java 17 client wants to close upon receiving an oversized message and calls `sendClose(1009, "...")`. Why is this wrong even though RFC 6455 defines 1009? What close policy should be used with this API?

**Exercise 5.** A client applies event #41 and loses network; the server produces #42 and #43. Right after reconnect `onOpen`, can it display "fully synced"? What must the client exchange?

**Exercise 6.** After reconnecting, the server sends #41 again and then #42. What must the client do with #41? What if it receives #44 when it has only applied #41?

**Exercise 7.** A client sends a money transfer command X; the server commits it but the ACK is lost. Should the client resend the same operation with a new request ID? How do you prevent duplicate side effects?

**Exercise 8.** Why is keeping `lastAppliedSeq` only in RAM insufficient for applications that must not lose transactions on a JVM crash? When should the cursor be updated?

**Exercise 9.** When a connection moves from Node A to Node B, what shared resources does the server need in order to replay stream events?

**Exercise 10.** `WebSocket.sendText(...).join()` returns successfully. Can you infer that the server has persisted the application transaction? What kind of ACK is needed?

**Exercise 11.** The server uses compression, and 100 KiB of compressed bytes expand to 15 MiB of text. Is a 2 MiB wire frame limit enough to protect a client enforcing a 1 MiB logical payload limit?

**Exercise 12.** A WebSocket connection is closed by user logout, while the scheduler still has a pending reconnect timer. How must the lifecycle be handled?

### Suggested answers

1. No. Limit the **total bytes of the entire message**, accumulated across all fragments, along with byte/time budgets.
2. 70 UTF-16 units, 140 UTF-8 bytes; it must be rejected when max is 128.
3. Parse when the message is complete, `last==true`; callbacks are not guaranteed to align with frame boundaries.
4. JDK 17 `WebSocket.sendClose` does not allow callers to send 1009; use code **1008** for policy violation or `abort` as needed, with a close deadline.
5. Not yet. Send HELLO/RESUME(`lastAppliedSeq=41`), server replays #42.., confirm synced before updating the UI.
6. Duplicate #41 must be ignored/deduplicated and the cursor ACKed; #44 creates a gap, requiring replay of #42/#43 or a snapshot, without advancing blindly.
7. Do not generate a new ID. Use a stable `idempotencyKey`, and have the server store/look up results by key and transaction.
8. Because a crash loses the cursor or leaves business commits inconsistent. Persist the cursor/dedup together with the business commit before sending ACK.
9. Shared durable event log/DB, snapshots, replay retention, session/auth state; load-balancer affinity alone is not enough.
10. No; the send future proves sending per the WebSocket API, not a server business commit. An application ACK is needed.
11. No. You must limit **decoded bytes** and compression ratio/CPU, not just compressed frame size.
12. Mark as terminal/closed, cancel timers/jobs, prevent old callbacks from reconnecting; distinguish user logout from transient failures.

## 22. Official references

- [Java SE 17 — WebSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html): `request(n)`, `sendText`, `sendBinary`, `sendPing`, `sendClose`/`abort`; especially the list of close codes forbidden in the Java API.
- [Java SE 17 — WebSocket.Listener](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): `onOpen`, `onText`, `onBinary`, `last`, `onClose`, `onError`, and demand handling.
- [Java SE 17 — WebSocket.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html): `buildAsync`, `connectTimeout`, subprotocols, and handshake headers.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): creating a WebSocket builder and handling the HTTP client.
- [Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8 byte counting.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `remaining()` and buffer ownership.
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html): framing, fragmentation, masking, control frames, status codes 1000/1006/1008/1009.
- [RFC 7692 — Compression Extensions for WebSocket](https://www.rfc-editor.org/rfc/rfc7692.html): permessage-deflate and decoded message limits.
