# Ping/Pong, Silent Connection Detection, and the Limits of Heartbeats in WebSocket (Java 17+)

## 1. The Real-World Problem: The Socket Is Still "Open" but the Other Side Has Disappeared

WebSocket applications often keep connections open for a long time to receive notifications, chat messages, telemetry, or real-time updates. However, the fact that a `WebSocket` object still exists in Java, a "connected" flag has not changed, and **no exception has been seen yet** does not mean the client can actually communicate with the server right then.

Real-world scenarios:

- A laptop loses Wi-Fi, switches networks, or goes to sleep and wakes up; the IP address or route to the server changes.
- A NAT, proxy, firewall, or load balancer deletes the connection state after a period with no traffic, **without sending a WebSocket Close frame**.
- The TCP connection on one side has not yet received `FIN`/`RST` because the link dropped silently (*half-open connection*).
- The application's event loop/callback is blocked, experiencing a garbage collection pause, or CPU-bound, so it cannot process messages in time.
- The server process hangs or crashes mid-flight; TCP and WebSocket do not necessarily report an error immediately.
- The server still replies with Pong at the WebSocket layer, but the business worker, database, or queue is no longer ready.

A **heartbeat** is a periodic check to look for signs that a connection is still responsive. In standard RFC 6455 WebSocket, the common approach is to send a **Ping control frame** and wait for a **Pong control frame** carrying the corresponding payload. If no Pong is seen within an appropriate time window, the client marks the connection as **suspected unresponsive (suspect/unresponsive)**, and may close and reconnect.

**Core message:** *A Pong indicates that one side of the WebSocket stack was still able to receive and respond to a Ping recently; it does not prove that the business service is healthy. Conversely, a Pong timeout only provides evidence according to a timeout policy, not absolute proof that the peer is dead.*

This lesson belongs to **Java Advance - networking → WebSocket**, focusing on **"Ping/Pong, Silent Connection Detection, and the Limits of Heartbeats"**. The examples use Java 17's `java.net.http.WebSocket` API, RFC 6455, and two self-contained runnable programs (one testing over a real loopback WebSocket, and one testing a heartbeat policy with a simulated clock).

## 2. Learning Objectives

After this lesson, you will be able to:

1. Describe **WebSocket Ping (opcode 0x9)**, **Pong (opcode 0xA)**, the maximum payload of **125 bytes**, the prohibition on fragmenting control frames, and response conditions under RFC 6455.
2. Distinguish **paired** Ping→Pong, **unsolicited Pong**, application-level heartbeats, TCP keepalive, and proxy/load balancer idle timeouts.
3. Understand why `WebSocket.sendPing(ByteBuffer)` returns a `CompletableFuture<WebSocket>` for the **send operation**, not a promise that a Pong has been received.
4. Implement `WebSocket.Listener.onPong(...)`, manage `webSocket.request(n)`, and correlate the **token/nonce** in the payload.
5. Understand that the Java 17 WebSocket client **automatically sends a Pong when receiving a Ping**; normally you do not need to call `sendPong(...)` yourself in `onPing`.
6. Design a state machine `IDLE → PING_SENT → PONG_RECEIVED` or `SUSPECT`, using monotonic time `System.nanoTime()`, with at most one unacknowledged Ping at a time.
7. Distinguish **send timeout**, **Pong timeout**, **idle threshold**, **TCP connection failure**, and **application readiness**.
8. Avoid falsely marking a connection as dead during jitter, network congestion, JVM pauses, scheduling delays, or when a listener is not granted demand.
9. Integrate deadlines, cancellation, `sendClose`/`abort`, retry backoff, jitter, observability, and resource cleanup.
10. Explain the browser limitation: browser JavaScript `WebSocket` **does not** allow applications to directly send/receive Ping/Pong control frames; a message-level heartbeat must be used if business code confirmation is needed.
11. Run and accurately read the stdout of two Java 17+ examples: **real frame handshake/ping/pong** and **policy deadline**.
12. Write tests verifying a matching-payload Pong, a mismatched Pong, an overdue Pong, an unsolicited Pong, server auto-Pong, and a half-open network.

## 3. Ping/Pong Flow Model and Silent Connection Cases

~~~text
CLIENT WEB SOCKET                                  SERVER WEB SOCKET
      |                                                   |
      |  PING payload=seq-71 (control opcode 0x9)          |
      |-------------------------------------------------->|
      |                                                   |
      |  PONG payload=seq-71 (control opcode 0xA)          |
      |<--------------------------------------------------|
      |       correlation matched: seq-71                 |
      |       record RTT, mark probe successful           |
      |                                                   |
      | ... wait according to heartbeat interval ...      |
      |                                                   |
      |  PING payload=seq-72                              |
      |-------------------------------------------------->X  network path lost
      |                                                   X
      |  No PONG seq-72 received before deadline          X
      |       ↓                                           |
      |  SUSPECT → cleanup/reconnect per policy           |
      |                                                   |
~~~

There are **three distinct layers of information**:

| Layer | Signal | What Can Be Concluded | What Cannot Be Concluded |
| --- | --- | --- | --- |
| TCP/transport | ACK, keepalive probe, FIN/RST, socket error | The link at a point in time shows some signs of life/death | That the business API is healthy |
| WebSocket protocol | Ping answered with Pong | The WebSocket peer/stack and a two-way path were responsive at probe time | That the DB, queue, or business consumer is not stuck |
| Application | `{"type":"health","seq":...}` → `{"type":"health-ack",...}` | The logic for receiving and handling that message type ran | That all business functions are ready |

Pongs are sent **automatically** by many WebSocket stacks, including the Java JDK client; therefore, an app's order-processing logic getting stuck **does not necessarily** stop WebSocket from replying with Pong. Conversely, a slow application ack can still be caused by a busy handler or client background throttling, rather than a broken TCP connection.

## 4. What Does RFC 6455 Specify for WebSocket Ping and Pong?

### 4.1. Control Frames, Opcodes, and Payload Limits

In RFC 6455, the WebSocket control frames are:

| Control frame | Opcode | Purpose |
| --- | --- | --- |
| Close | `0x8` | Initiate/acknowledge connection closing |
| Ping | `0x9` | Check responsiveness/keepalive |
| Pong | `0xA` | Reply to Ping or send proactively |

Constraints:

- **Maximum payload of 125 bytes** for every control frame. Java's `sendPing(ByteBuffer)` rejects longer payloads with `IllegalArgumentException` via the future result per the API contract.
- **Control frames must not be fragmented**: the FIN bit must be set (the frame is final); do not split a control frame into multiple continuation frames.
- Control frames **may be interleaved between fragments of a data message** to avoid waiting for a very large file transfer to finish before sending a Ping.
- Client-to-server frames must be **masked** per RFC 6455; server-to-client frames do not use masking per protocol rules. This is important when writing your own TCP test fixture.
- Ping/Pong payloads are **bytes**, not a business JSON message, and have no mandatory format semantics.
- Both WebSocket client and server **may send Ping** once the connection is established and not yet closed.
- Upon receiving a Ping before receiving Close, a peer **must send a Pong** and should do so as soon as possible; **the reply Pong must contain the same payload as the Ping being answered**.
- If multiple Pings are pending, the RFC allows a peer to reply with a Pong only for the **most recent** Ping under certain conditions. Therefore, a heartbeat application should limit itself to one pending probe rather than firing a burst.
- An endpoint may send a **Pong without a preceding Ping** (*unsolicited Pong*). This does not mean the other side should send another Pong in response to that Pong.

~~~text
Frame from Java client to server:
FIN=1 | opcode=0x9 (Ping) | MASK=1 | length <=125 | masking key | payload bytes

Reply frame from server:
FIN=1 | opcode=0xA (Pong) | MASK=0 | length <=125 | same payload bytes
~~~

**Avoid confusion:** `PING` written inside a normal text message does not have the same opcode as a WebSocket **Ping control frame**. A server receiving the WebSocket text `"PING"` may simply treat it as chat text and is not required by the RFC to automatically reply with a Pong.

### 4.2. Successful Send Does Not Mean the Peer Replied

Suppose:

~~~java
webSocket.sendPing(ByteBuffer.wrap(new byte[]{1, 2, 3}))
         .get(5, TimeUnit.SECONDS);
~~~

This is a **code snippet** where `webSocket` is a connected WebSocket, importing `ByteBuffer` and `TimeUnit`. When the future succeeds, the JDK is reporting that the **send operation has completed**. It **does not mean** the server received it, processed the Ping, or sent a Pong. Over TCP, bytes being enqueued/handed off to the transport also does not prove the business layer handled them.

To confirm a Pong, you need **`Listener.onPong(...)`**, matching the Pong's payload against the pending Ping, and an independent deadline.

### 4.3. A Pong Must Not Trigger Another Reply

An incorrect diagram that easily creates a ping-pong storm:

~~~text
Client Ping → Server Pong → Client Pong → Server Pong → ...  (WRONG)
~~~

Correct response:

~~~text
Client Ping(payload=x) → Server Pong(payload=x) → END probe.
~~~

An unsolicited Pong is valid, but **must not require a Pong in response to a Pong**. If an application chooses to send an unsolicited Pong as a one-way signal, the receiver can observe traffic/estimate liveness, but that does not replace the sender's paired Ping→Pong measurement.

## 5. Java 17 API: sendPing, onPing, onPong, request(n)

Java 17 provides a WebSocket client in the `java.net.http` module (available since Java 11):

~~~java
HttpClient client = HttpClient.newHttpClient();
WebSocket webSocket = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .buildAsync(URI.create("wss://example.com/events"), listener)
        .get(10, TimeUnit.SECONDS);
~~~

This is a **code snippet**: `listener` must be defined beforehand, the illustrative URI is untested, and the method declares `throws Exception` or handles timeouts/exceptions. The builder's `connectTimeout` applies to **establishing the WebSocket**, and does not automatically configure a **periodic heartbeat after connecting**.

### 5.1. Key API Table

| API | Purpose | Pitfall to Avoid |
| --- | --- | --- |
| `WebSocket.sendPing(ByteBuffer)` | Send a Ping frame, returning a future for the send operation | A completed future is **not** a Pong ack |
| `WebSocket.sendPong(ByteBuffer)` | Send a Pong frame proactively | The JDK already auto-replies to Ping; do not send redundantly |
| `WebSocket.Listener.onPing(WebSocket, ByteBuffer)` | Callback for receiving Ping | The Java implementation automatically sends a reciprocal Pong |
| `WebSocket.Listener.onPong(WebSocket, ByteBuffer)` | Callback for receiving Pong | Must copy/read the payload while owning the buffer |
| `WebSocket.Listener.onOpen(WebSocket)` | Callback after handshake | Call `webSocket.request(n)` to grant receive callback demand |
| `WebSocket.request(long n)` | Increase the demand count for receive callbacks | Without requesting more, the app may **never receive onPong** even when the network is fine |
| `WebSocket.Listener.onClose(...)` | Observe a WebSocket Close frame | Stop heartbeat, close input/output per lifecycle |
| `WebSocket.Listener.onError(...)` | Notified of a receive/callback error | Stop probes, clean up resources; do not wait forever for Pong |
| `WebSocket.sendClose(1000, reason)` | Initiate an orderly close handshake | Future indicates send completion, not that the peer/business has gracefully stopped |
| `WebSocket.abort()` | Close input/output immediately, terminating the connection abruptly | Use only on timeout/when forcing is needed, not as a normal graceful close |
| `WebSocket.isInputClosed()/isOutputClosed()` | Observe input/output directions | Both directions can close independently; current flags do not replace active probes |

**Buffer rule:** bytes in the `ByteBuffer` passed to `sendPing` must lie between `position` and `limit` and must not be accessed/modified before the send `CompletableFuture` completes. When handling `onPong`, copy the bytes before completing the callback's `CompletionStage`; the JDK may reclaim the buffer afterward.

### 5.2. The JDK Automatically Replies to Ping

Per Java 17 `WebSocket`, the implementation automatically replies to a Ping with a Pong and handles the Close protocol reply. Therefore, a normal `Listener` **does not need to write `sendPong(...)` inside `onPing(...)`**.

~~~java
@Override
public CompletionStage<?> onPing(
        WebSocket ws, ByteBuffer payload) {
    // The Java WebSocket implementation automatically sends a protocol-compliant Pong.
    // If overriding the callback, you still must grant demand to receive the next event.
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
~~~

This is a **method snippet**, to be placed inside a class implementing `WebSocket.Listener` with imports for `WebSocket`, `ByteBuffer`, `CompletionStage`, and `CompletableFuture`. If no logic is needed upon seeing a Ping, you can **omit overriding `onPing`**; the default listener implementation also calls `request(1)`.

**Subtle point:** "Automatic Pong" does not prove that the server's or client's business handler is healthy. As long as the WebSocket stack can still respond to protocol-level Pings, it can return a Pong even if the task processing business messages is hung.

### 5.3. Demand/Backpressure in Listener

A newly constructed `WebSocket` has an initial demand count of **0**. The JDK only invokes receive callbacks when the application has called `request(n)`; each receive callback consumes one unit of demand. Therefore:

~~~java
@Override
public void onOpen(WebSocket ws) {
    ws.request(1);
}

@Override
public CompletionStage<?> onPong(
        WebSocket ws, ByteBuffer payload) {
    byte[] bytes = new byte[payload.remaining()];
    payload.get(bytes);
    // Process bytes here; do not retain ByteBuffer outside the callback.
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
~~~

This is a **code snippet** belonging to a `Listener`; corresponding imports are needed. If you override `onOpen` and forget `request(1)`, you may never see `onPong` and trigger a **false** timeout. If you override `onPong` without granting demand for the next event, subsequent Pongs may also not be dispatched.

Java 17's default methods `onText/onBinary/onPing/onPong` call `request(1)` if you do not override them. If you override any callback, manage demand intentionally; do not call `request(Long.MAX_VALUE)` as a shortcut to bypass backpressure in a system that might receive large or unbounded messages.

**Do not assume callbacks always run on one fixed thread:** the JDK guarantees serialization of listener callbacks for a single WebSocket, but your scheduler/timer runs on another thread. Shared state such as `pendingPing`, `lastPongNanos`, or `status` must be thread-safe (atomic, lock, or event-loop synchronized).

### 5.4. sendPing Errors and Concurrency Limits

Per Java 17 `WebSocket.sendPing`:

- The payload from `ByteBuffer` must not exceed **125 bytes**.
- A pending Ping/Pong send can cause a subsequent send to fail with `IllegalStateException` in the future.
- `IOException` can occur if an I/O error happens or output is already closed.
- `sendPing` does not provide a **Pong timeout** itself; the Java application must define the deadline/scheduler.
- `sendPong` is rarely needed to reply to a Ping because the implementation does it automatically.

**Do not send a new Ping before handling the previous Ping** just to "be sure." If the peer sends a Pong only for the latest Ping, the old Ping record may never match; you create a false alarm and add traffic when the network is already congested.

## 6. When Is a Connection Considered "Silent"?

A connection can be "silent" in different senses:

| State | What Is Observed | How Does Heartbeat Help? |
| --- | --- | --- |
| No new chat/events | No application messages | Ping/Pong confirms the WebSocket stack is still responsive |
| Proxy silently drops idle connection | No Close/FIN/RST on client | Ping/Pong can detect path loss after timeout |
| NAT mapping expired | Outgoing packets no longer return as before | Probes can expose that the network path is lost |
| JVM pause or listener lacking demand | Pong may arrive but is not processed by callback yet | Risk of **false positive** |
| Server only answers control frames | Ping still gets Pong, business API is hung | **Does not detect business readiness** |
| Server heavily overloaded | Slow Pong, callback starved of CPU | Timeout can mark suspect, without knowing the root cause |
| Device switches from Wi-Fi to 4G | Old TCP connection may be unusable | Probes help reveal the need to reconnect |
| Browser tab suspended | JS timers are heavily throttled or paused | App heartbeat is less accurate in background |
| Slow network or transient packet loss | Pong arrives after deadline | Timeout is a policy, not absolute proof the peer is dead |
| One-way path works, return path lost | Ping leaves client, Pong never returns | Two-way probe detects loss of responsiveness |
| Very short proxy/LB idle timeout | WS may be closed before next probe | Heartbeat must be configured to match infrastructure |

**Detecting a "silent" connection is always a trade-off** between detection time, probe overhead, false positive risk, and infrastructure timeouts.

## 7. Choosing Intervals and Deadlines Properly

Key concepts:

- **Heartbeat interval** `I`: target spacing between probe starts (when no probe is currently pending).
- **Pong timeout** `T`: maximum allowed time from when a probe is eligible/sent until the matching Pong is received.
- **Miss threshold** `M`: number of consecutive failures before force-closing (if the policy chooses this).
- **Idle threshold**: whether to ping only after a period with no network/app traffic, or ping regularly regardless of traffic.
- **Jitter**: a small phase offset in the send schedule so many clients do not flood the server simultaneously.
- **RTT estimate**: `PongReceivedAt - PingSentAt`, approximating round-trip including event processing and scheduling, not just network RTT.

Illustrative example *not a universal recommendation*: `I=20 seconds`, `T=8 seconds`, potentially requiring multiple consecutive misses. On mobile networks or backgrounded devices, `T=8 seconds` may be too low; on low-latency servers, thresholds may differ. Choose numbers using real measurements: p95/p99 Pong RTT, GC pauses, network jitter, proxy/LB idle settings, and detection-time requirements.

### 7.1. Use a Monotonic Clock

**Do not** compute deadlines using `System.currentTimeMillis()` and assume the OS clock never jumps. NTP adjustments or user clock changes can skew the elapsed difference.

In production:

~~~java
long startedAt = System.nanoTime();
long timeoutNanos = TimeUnit.SECONDS.toNanos(8);

if (System.nanoTime() - startedAt >= timeoutNanos) {
    // Expired per policy, mark SUSPECT.
}
~~~

This is a **code snippet**; `TimeUnit` is from `java.util.concurrent`. Use the difference between two `nanoTime()` timestamps (monotonic clock) and avoid comparing against epoch time. Do not treat `System.nanoTime()` as UTC time or use it to log wall-clock timestamps like `Instant.now()`.

### 7.2. One Outstanding Ping at a Time

~~~text
IDLE
  |
  | interval elapsed
  v
PING_PENDING(seq=47, sentAt)
  |        |
  |        +-- onPong(seq=46)  → IGNORE (stale/unsolicited)
  |        |
  |        +-- onPong(seq=47)  → ACKED → IDLE
  |        |
  |        +-- timeout         → SUSPECT → policy reconnect/abort
  |
  +-- Forbidden to create seq=48 while seq=47 is still pending
~~~

This prevents two bugs:

1. An old/unsolicited Pong making you mistakenly think the new Ping was acknowledged.
2. Overlapping Pings making correlation difficult and risking the peer **replying only to the latest Ping** per RFC.

The payload can just be `seq` or a short nonce; **do not** put JWTs, secret tokens, or sensitive data into a Ping payload. It is a control frame, not a private secure business metadata channel. Best practice is to keep the payload to a few bytes and match exact bytes, not just "any Pong arrived."

### 7.3. Send Failure Is Different From Missing Pong

The heartbeat scheduler should distinguish:

~~~text
sendPing()              → API initiates send
future SEND_SUCCESS     → frame sent per JDK contract
onPong(matching payload)→ peer responded to probe
Pong deadline expired   → matching Pong not observed on time
sendPing SEND_FAILURE   → local send error / output closed / I/O
~~~

If the send fails immediately, do not start counting a "missing Pong response" as if the Ping had left the client. If the send queue backs up before the frame is actually sent, the policy should distinguish **send deadline/backpressure** from Pong deadline; measure RTT from an appropriate point (when send completes or a clearly defined and recorded timestamp) to avoid blaming all delay on the server.

## 8. Runnable Example 1 — Real WebSocket: Ping, Auto-Pong, and Overdue Probe

### 8.1. What Does This Test Verify?

The program builds a **minimal WebSocket test server over TCP loopback** with an RFC 6455 handshake so we need no framework, Internet, or external server. The client is Java 17's **real `java.net.http.WebSocket`**.

Test flow:

1. A local `ServerSocket` accepts the HTTP Upgrade request, reads `Sec-WebSocket-Key`, computes `Sec-WebSocket-Accept` per RFC 6455, and replies with `101 Switching Protocols`.
2. The Java WebSocket client sends **Ping `seq-1`**; the server unmasks the frame and replies with **Pong `seq-1`**.
3. Listener `onPong` matches the payload and completes the `CompletableFuture` for the first probe.
4. The server sends **Ping `srv-1`** to the client. The JDK automatically sends a reciprocal Pong; the test server records it, **without** the client manually calling `sendPong`.
5. The client sends **Ping `seq-2`**; the server deliberately **does not respond** to simulate a silent/unresponsive WebSocket peer.
6. The client waits up to 600 ms for **Pong seq-2**; on expiration, it prints `true` and calls `abort()` to end the demo.
7. The server returns the Ping count and whether it received the auto-Pong from the client.

**Note:** real-world proxy/firewall/TCP behavior is more complex than a test that intentionally withholds a Pong. This demo proves **matching + deadline**, not that a single timeout is enough to conclude a connection is definitely dead.

### 8.2. File `WebSocketPingPongHeartbeatDemo.java`

~~~java
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class WebSocketPingPongHeartbeatDemo {
    record Frame(int opcode, byte[] body) {}

    static String readHttpHeaders(InputStream stream) throws IOException {
        ByteArrayOutputStream result = new ByteArrayOutputStream();
        int state = 0;
        while (result.size() < 8192) {
            int b = stream.read();
            if (b < 0) throw new EOFException("Handshake incomplete");
            result.write(b);
            state = switch(state) {
                case 0 -> b == '\r' ? 1 : 0;
                case 1 -> b == '\n' ? 2 : b == '\r' ? 1 : 0;
                case 2 -> b == '\r' ? 3 : 0;
                default -> b == '\n' ? 4 : b == '\r' ? 1 : 0;
            };
            if (state == 4) return result.toString(StandardCharsets.US_ASCII);
        }
        throw new IOException("Handshake header too long");
    }

    static Frame readFrame(InputStream in) throws IOException {
        int first = in.read();
        if (first < 0) return null;
        int second = in.read();
        if (second < 0) throw new EOFException("No frame length");
        boolean masked = (second & 0x80) != 0;
        int length = second & 0x7f;
        if ((first & 0x80) == 0 || length > 125 || !masked) {
            throw new IOException("Demo expects short, masked FIN client frame");
        }
        byte[] mask = in.readNBytes(4);
        byte[] data = in.readNBytes(length);
        if (mask.length != 4 || data.length != length) throw new EOFException();
        for (int i=0;i<data.length;i++) data[i] ^= mask[i%4];
        return new Frame(first & 0x0f, data);
    }

    static void sendControl(OutputStream out, int opcode, String text)
            throws IOException {
        byte[] data = text.getBytes(StandardCharsets.US_ASCII);
        if (data.length > 125) throw new IllegalArgumentException();
        out.write(0x80 | opcode);
        out.write(data.length);
        out.write(data);
        out.flush();
    }

    static String serve(ServerSocket server) throws Exception {
        try (Socket peer = server.accept()) {
            peer.setSoTimeout(5000);
            InputStream in=peer.getInputStream();
            OutputStream out=peer.getOutputStream();
            String headers = readHttpHeaders(in);
            String key=null;
            for (String line:headers.split("\r\n")) {
                if (line.regionMatches(true,0,"Sec-WebSocket-Key:",0,18)) {
                    key=line.substring(18).trim();
                }
            }
            if (key == null) throw new IOException("No websocket key");
            byte[] digest=MessageDigest.getInstance("SHA-1").digest(
                (key+"258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                   .getBytes(StandardCharsets.US_ASCII));
            String accept=Base64.getEncoder().encodeToString(digest);
            out.write(("HTTP/1.1 101 Switching Protocols\r\n"+
                       "Upgrade: websocket\r\n"+
                       "Connection: Upgrade\r\n"+
                       "Sec-WebSocket-Accept: "+accept+"\r\n\r\n")
                    .getBytes(StandardCharsets.US_ASCII));
            out.flush();
            int count=0;
            boolean clientEchoedPing=false;
            while(true) {
                Frame frame;
                try {frame=readFrame(in);}catch(SocketException e){break;}
                if(frame==null) break;
                String payload=new String(frame.body(),StandardCharsets.US_ASCII);
                if(frame.opcode()==9) {
                    count++;
                    if(count==1) {
                        sendControl(out,10,payload);
                        sendControl(out,9,"srv-1");
                    }
                    // Deliberately ignore the second Ping.
                } else if(frame.opcode()==10) {
                    if(payload.equals("srv-1")) clientEchoedPing=true;
                } else if(frame.opcode()==8) {
                    break;
                }
            }
            return "clientPingCount="+count+
                   " autoPongReceived="+clientEchoedPing;
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker=Executors.newSingleThreadExecutor();
        try(ServerSocket server=new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {
            server.setSoTimeout(5000);
            Future<String> serverResult=worker.submit(() -> serve(server));

            CompletableFuture<String> pong1=new CompletableFuture<>();
            CompletableFuture<String> pong2=new CompletableFuture<>();
            WebSocket.Listener listener = new WebSocket.Listener() {
                @Override public void onOpen(WebSocket ws) {
                    ws.request(1);
                }
                @Override public CompletionStage<?> onPong(
                        WebSocket ws, ByteBuffer payload) {
                    byte[] data=new byte[payload.remaining()];
                    payload.get(data);
                    String token=new String(data,StandardCharsets.US_ASCII);
                    if(token.equals("seq-1"))pong1.complete(token);
                    if(token.equals("seq-2"))pong2.complete(token);
                    ws.request(1);
                    return CompletableFuture.completedFuture(null);
                }
                @Override public void onError(WebSocket ws, Throwable error) {
                    pong1.completeExceptionally(error);
                    pong2.completeExceptionally(error);
                }
            };
            WebSocket ws=HttpClient.newHttpClient().newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .buildAsync(URI.create("ws://127.0.0.1:"+
                            server.getLocalPort()+"/health"),listener)
                    .get(5,TimeUnit.SECONDS);
            try {
                ws.sendPing(ByteBuffer.wrap(
                        "seq-1".getBytes(StandardCharsets.US_ASCII)))
                    .get(5,TimeUnit.SECONDS);
                System.out.println("Matched first pong: "+
                        pong1.get(5,TimeUnit.SECONDS));

                ws.sendPing(ByteBuffer.wrap(
                        "seq-2".getBytes(StandardCharsets.US_ASCII)))
                    .get(5,TimeUnit.SECONDS);
                boolean expired;
                try {
                    pong2.get(600,TimeUnit.MILLISECONDS);
                    expired=false;
                } catch(TimeoutException expected) {
                    expired=true;
                }
                System.out.println("Second pong deadline exceeded: "+expired);
                if(expired)ws.abort();
            } finally {
                ws.abort();
            }
            System.out.println("Server: "+serverResult.get(5,TimeUnit.SECONDS));
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

Compile targeting Java 17, run on JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 WebSocketPingPongHeartbeatDemo.java
java WebSocketPingPongHeartbeatDemo
~~~

**Verified stdout on OpenJDK 24 with `javac --release 17`:**

~~~text
Matched first pong: seq-1
Second pong deadline exceeded: true
Server: clientPingCount=2 autoPongReceived=true
~~~

### 8.3. Breaking Down the Results

- `Matched first pong: seq-1` proves `onPong` **received the exact payload of the pending probe**, not just any Pong.
- `Second pong deadline exceeded: true` proves **no matching Pong seq-2 was observed within the 600 ms** of the test. It is **not absolute proof** that the peer is dead; in the demo, the server is alive but deliberately withholds the reply.
- `clientPingCount=2` proves the server received both **two Ping control frames** from the Java client.
- `autoPongReceived=true` proves the server sent Ping `srv-1` and received the JDK client's reciprocal Pong, even though the listener **did not override `onPing` or call `sendPong`**.
- Client frames use masking, server frames do not; the `Sec-WebSocket-Accept` handshake is a protocol requirement, **not cryptographic authentication of the server**.
- The code uses `sendPing().get` **for send completion**, and `pong1.get/pong2.get` **for matching Pong**. These two futures have different meanings.
- `ws.abort()` is **required cleanup** allowing the test to finish immediately even though the server is intentionally silent; production may use a close handshake before force abort depending on policy.

### 8.4. Limitations of the Test Fixture

The hand-written WebSocket server above is **not** a production WebSocket server:

- It accepts only **one** TCP client, parses only short masked FIN control frames, and does not handle long data frames, fragmentation, compression, multiple sessions, authorization, full validation, TLS, quotas, or proper closing in all cases.
- Only for `ws://127.0.0.1`; do not expose a public proxy or Internet listener, and do not use this fixture in a real system.
- Uses `SHA-1` to compute `Sec-WebSocket-Accept` **per the RFC handshake**, not to hash passwords or authenticate the server; WSS security requires separate TLS/hostname validation.
- The 600 ms timeout is to make the test run fast on loopback; **do not** use it as a default for the Internet or mobile networks.
- In production, response times can spike abnormally under high load, stop-the-world GC, scheduler starvation, or device background sleep.

If you need a full WebSocket server, use a maintained library/server with security, rate-limiting, authentication, timeout, and capacity policies.

## 9. Runnable Example 2 — Heartbeat State Machine With Simulated Timestamps

The first example shows **wire behavior**; this example focuses on **policy**. We simulate milliseconds using an injected `nowMillis` variable without sleeping or depending on wall-clock time. This creates deterministic unit tests for decisions:

- t=0: allowed to send `seq-1`.
- Receiving mismatched Pong `seq-old`: **not** treated as success.
- Receiving Pong `seq-1` at t=35: success, measured RTT is 35 ms.
- t=70: 100 ms interval has not elapsed, so **IDLE**.
- t=120: send `seq-2`.
- t=140: still waiting.
- t=171: exceeded 50 ms Pong timeout from t=120, so **SUSPECT**.

### 9.1. File `HeartbeatDecisionDemo.java`

~~~java
public class HeartbeatDecisionDemo {
    enum Action { SEND_PING, IDLE, WAIT_FOR_PONG, SUSPECT }

    static final class Policy {
        private final long intervalMillis;
        private final long pongTimeoutMillis;
        private long lastSentMillis;
        private long sentAtMillis;
        private int nextSequence;
        private String pending;
        private long lastRttMillis = -1;

        Policy(long intervalMillis, long pongTimeoutMillis) {
            if (intervalMillis <= 0 || pongTimeoutMillis <= 0)
                throw new IllegalArgumentException();
            this.intervalMillis = intervalMillis;
            this.pongTimeoutMillis = pongTimeoutMillis;
            this.lastSentMillis = -intervalMillis;
        }

        Action check(long nowMillis) {
            if (pending != null) {
                return nowMillis - sentAtMillis >= pongTimeoutMillis
                        ? Action.SUSPECT : Action.WAIT_FOR_PONG;
            }
            if (nowMillis - lastSentMillis < intervalMillis)
                return Action.IDLE;
            pending = "seq-" + ++nextSequence;
            sentAtMillis = nowMillis;
            lastSentMillis = nowMillis;
            return Action.SEND_PING;
        }

        String pendingToken() {
            return pending;
        }

        boolean onPong(String token, long nowMillis) {
            if (pending == null || !pending.equals(token))
                return false;
            lastRttMillis = Math.max(0, nowMillis - sentAtMillis);
            pending = null;
            return true;
        }

        long lastRttMillis() {
            return lastRttMillis;
        }
    }

    public static void main(String[] args) {
        Policy heartbeat = new Policy(100, 50);
        System.out.println("t=0: " + heartbeat.check(0) +
                " " + heartbeat.pendingToken());
        System.out.println("Wrong pong accepted: " +
                heartbeat.onPong("seq-old", 15));
        System.out.println("Matching pong accepted: " +
                heartbeat.onPong("seq-1", 35));
        System.out.println("Measured RTT millis: " +
                heartbeat.lastRttMillis());
        System.out.println("t=70: " + heartbeat.check(70));
        System.out.println("t=120: " + heartbeat.check(120) +
                " " + heartbeat.pendingToken());
        System.out.println("t=140: " + heartbeat.check(140));
        System.out.println("t=171: " + heartbeat.check(171));
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 HeartbeatDecisionDemo.java
java HeartbeatDecisionDemo
~~~

**Verified stdout:**

~~~text
t=0: SEND_PING seq-1
Wrong pong accepted: false
Matching pong accepted: true
Measured RTT millis: 35
t=70: IDLE
t=120: SEND_PING seq-2
t=140: WAIT_FOR_PONG
t=171: SUSPECT
~~~

### 9.2. Why Is a State Machine Useful?

**Independence from scheduler timing** makes it possible to test cases that sleep-based tests often miss. With a state machine, you can prove:

- **At most one pending token** because `check` does not create a new token if `pending != null`.
- **Mandatory matching**: a Pong for `seq-old` does not complete `seq-1`.
- **RTT** is updated only on a valid Pong.
- **Timeout** is computed from the recorded timestamp, not from total elapsed time since the client created the WebSocket.
- **SUSPECT is a policy decision**, and must not be turned into `DEAD_CONFIRMED` without stronger terminal evidence.

**Policy demo limitations:** `nowMillis` is a simulated clock, and the `Policy` object is not thread-safe. When integrating with a real Java WebSocket, use `System.nanoTime()`, protect state via locks/atomics or an event loop, handle send future failures, close/abort, reconnect, reset state when creating a new socket, and never match old tokens against a new session.

In particular, `check(now) == SEND_PING` in the demo **is only a request to send**; in production you must record the success/failure state of `sendPing`. If the network is congested and the send future does not complete, a send timeout is needed rather than mistakenly assuming the peer received the Ping.

## 10. From Examples to Production Heartbeat Scheduler Design

A production design should have a **lifecycle owner** per WebSocket connection, rather than an arbitrary scheduler holding a reference to a socket that has already been replaced after a reconnect.

### 10.1. State Machine Model

~~~text
CREATED
  | WebSocket handshake complete
  v
ACTIVE
  | interval / idle timer
  v
PING_SENDING
  | future send failed ----> FAILED → cleanup/reconnect
  | future send success
  v
WAITING_PONG(token, deadline)
  |             |
  | onPong match| deadline exceeded / receive error
  v             v
ACTIVE       SUSPECT
                |
                +--> record metric, cancel old socket
                +--> close handshake/abort per policy
                +--> schedule reconnect with backoff+jitter
                v
             RECONNECTING
                |
                v
           new WebSocket session (new token epoch)
~~~

**Do not share pending tokens across two WebSocket sessions.** If a reconnect just happened and an old callback arrives late, it must not mark the new session healthy. Attach a **generation/session ID** to the heartbeat policy to check which socket a callback belongs to.

### 10.2. Scheduler: Fixed Delay and Non-Overlapping Probes

Java provides `ScheduledExecutorService`:

~~~java
ScheduledExecutorService timer =
        Executors.newSingleThreadScheduledExecutor();

ScheduledFuture<?> task = timer.scheduleWithFixedDelay(
        () -> {
            // 1. If session is not ACTIVE, skip.
            // 2. If Ping is pending, check deadline/mark suspect.
            // 3. If interval has not elapsed, do not send.
            // 4. If eligible to send, generate nonce and dispatch sendPing.
            // 5. Handle send future failure/success separately.
        },
        0, 1, TimeUnit.SECONDS);
~~~

This is an **architectural snippet**, not a standalone application. Import `java.util.concurrent.*`; the heartbeat logic is supplied by the application. Ticking every second **does not** mean sending a Ping every second: only send when state and interval permit. You must call `task.cancel(...)` when the socket closes and shut down the timer when there is no longer an owner, avoiding executor leaks. With thousands of clients, do not create a separate thread pool per connection; use a bounded shared scheduler and per-session state.

**`scheduleAtFixedRate` pitfall:** if one tick is delayed for a long time, subsequent ticks can run back-to-back (even if not concurrently on a single-thread scheduler), creating bursts or false timeouts. `scheduleWithFixedDelay` combined with state/deadlines is usually easier to control, though the application must still check monotonic timestamps rather than trusting ticks to fire on time.

### 10.3. Event Listener: Update State, Do Not Block Callbacks

~~~java
@Override
public CompletionStage<?> onPong(WebSocket ws, ByteBuffer data) {
    byte[] bytes = new byte[data.remaining()];
    data.get(bytes);
    // Call heartbeatPolicy with nonce, session/generation, and now=System.nanoTime().
    // If matching pending Ping, record RTT, clear pending.
    // Do not call DB or CompletableFuture.get() waiting on network here.
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
~~~

This is a **code snippet** inside a `Listener`. Use a minimal, bounded payload parser; avoid allocating large byte arrays (the protocol already caps control frames at <=125). Do not log raw secret tokens. If the scheduler thread and listener thread both update state, synchronize properly.

### 10.4. Normal Close and Force Abort

When the application shuts down proactively:

~~~java
socket.sendClose(WebSocket.NORMAL_CLOSURE, "shutdown")
      .orTimeout(3, TimeUnit.SECONDS)
      .whenComplete((ignored, error) -> {
          if (error != null) socket.abort();
      });
~~~

This is a **code snippet** (`socket` is a `WebSocket`), using `CompletableFuture.orTimeout` and `TimeUnit`; cleaning up input/awaiting peer closure may be needed depending on API/lifecycle. `sendClose` only initiates closing the send direction; for a full graceful shutdown, you must handle `onClose` and close all resources.

On **Pong timeout** when the connection is considered unusable per policy, `socket.abort()` closes input/output immediately. `abort` **does not** perform a WebSocket close handshake, so use it intentionally. Do not accidentally trigger dozens of concurrent `abort()` and reconnect calls from multiple callbacks: you need atomic terminal transitions and a single owner.

## 11. What Is a Heartbeat Not? Limits You Cannot Ignore

### 11.1. Pong Does Not Prove the Application/Business Layer Is Healthy

If a WebSocket server still automatically handles protocol Pings, but business threads are hung due to deadlock, cache/database failure, or queue backlog, the client can still receive Pongs regularly.

~~~text
Network alive     : true
WebSocket Pong    : true
Message consumer  : stuck
Database ready    : false
User operation    : failing

=> Protocol heartbeat PASSES but business readiness FAILS
~~~

If you need to confirm that the **business consumer can actually process messages**, design an **application-level request/ack** with a correlation ID, timeout, and domain-specific signal (for example "worker accepted job"), yet **do not** treat a simple ack as a guarantee that a transaction has committed.

### 11.2. Missing Pong Does Not Prove the Peer Is Dead

A Pong can be delayed because of:

- Increased RTT, congestion, packet loss, or TCP retransmission.
- JVM stop-the-world GC pause or CPU starvation.
- A blocked WebSocket receive listener or forgetting to call `request(1)`, preventing `onPong` from being dispatched in time.
- OS process suspension or a laptop/browser tab being backgrounded.
- Server overload, prioritizing other work, or control frames queued behind blocked I/O.
- Delayed clock/timer scheduler; deadline measured from the wrong timestamp.
- Proxy/LB flow control and buffering, or abnormal tunneling.
- The peer receiving multiple Pings and returning only one Pong for the most recently processed Ping (permitted by the RFC under certain conditions).

Therefore, a timeout should be recorded as **SUSPECT/UNRESPONSIVE**. The application action may still be to close and reconnect (to meet SLAs), but logs should state **"no matching Pong before deadline"** rather than **"proved server is dead"**.

### 11.3. Keepalive Does Not Guarantee the Tunnel Will Not Be Closed

Ping/Pong traffic can help prevent some NAT/proxy/LB idle timeouts, however:

- Not every proxy counts control frames as activity in the way you expect.
- There may be an **absolute connection lifetime** regardless of traffic.
- The server may intentionally enforce a max session duration, auth refresh, or rolling restart.
- Network migration can render an old TCP connection unrecoverable even if Pings succeeded earlier.
- An **application-layer** idle timeout may track business messages and **ignore protocol-level Pings**.

You must check the connection idle/absolute timeout policy of **each hop**, not just set the smallest possible interval.

### 11.4. TCP Keepalive vs. WebSocket Ping

| Characteristic | TCP keepalive | WebSocket Ping/Pong | Application heartbeat |
| --- | --- | --- | --- |
| Layer | OS/transport | WebSocket protocol | Business protocol/application |
| Configured by | OS/socket options/platform | WebSocket endpoint/application/library | The application itself |
| Response | TCP ACK/keepalive handling | Pong control frame | App-defined ack |
| Verifies WebSocket stack? | Not necessarily | Yes, within protocol limits | Can reach business consumer |
| Correlation ID payload | Usually not in app | Yes, up to 125 bytes | App-defined |
| Detects hung app worker? | Not guaranteed | Not guaranteed | Possible if ack is handled in the right place |
| Directly controlled by Browser JS? | No | **No** via standard browser WebSocket API | Yes, via text/binary messages |
| Effect on proxy idle | Hop-dependent | Possible, proxy-dependent | Possible, proxy-dependent |
| Timeout policy | OS-specific, often not SLA-optimal | App-defined | App-defined |

Do not blindly replace WebSocket Ping with `Socket.setKeepAlive(true)`: Java's `java.net.http.WebSocket` does not expose a direct socket API to enable TCP keepalive across all runtimes, and OS defaults can be very long. When an accurate application-level heartbeat is needed, use WebSocket Ping/Pong or a custom protocol suited to the environment.

## 12. Special Case: Browser WebSocket Has No sendPing()

Java applications have the `WebSocket.sendPing(...)` API, but the standard browser WebSocket JavaScript API only allows sending text/binary via `socket.send(...)` and listening to `onmessage`, `onopen`, `onclose`, `onerror`, and `readyState`. It **does not expose control-frame Ping/Pong** to JavaScript.

Therefore:

- The server can send native Ping control frames; the browser network stack usually replies with Pong automatically.
- Browser JavaScript code **cannot directly invoke native Ping or receive native Pong callbacks** to measure RTT.
- If you want a client-side heartbeat from the browser, define an **application-level message** such as text JSON:

~~~json
{"type":"heartbeat","seq":"42","sentAt":123456789}
~~~

Server replies:

~~~json
{"type":"heartbeat-ack","seq":"42"}
~~~

This is **illustrative JSON**, not a native control frame. The server must **explicitly implement the handler and ack** per the application protocol; no RFC forces a WebSocket server to automatically reply with `heartbeat-ack` to that JSON. The `sentAt` field here is demo data only, not clock synchronization. In browsers, when a tab is suspended/throttled, app timers can be heavily delayed; do not conclude the server is dead from a single delayed tick and reconnect aggressively.

Depending on the architecture, you can use **server-initiated Ping** to keep the WebSocket network path alive and **client-initiated application-level heartbeat** to measure business processing. When both are active, account for their traffic and deadlines separately to avoid probe storms.

## 13. Designing Retry and Reconnect After Heartbeat Timeout

A good heartbeat paired with a bad reconnect strategy can make a service less stable:

~~~text
100,000 clients connected
    |
   brief proxy network outage
    |
100,000 clients all time out at 5 seconds
    |
100,000 clients reconnect at the exact same time
    |
server CPU/TLS handshake spike -> prolonged outage
~~~

**Mitigations:**

1. On heartbeat timeout, transition the session to **SUSPECT** via atomic state; only one flow is allowed to close/reconnect.
2. Cancel pending operations and timers of the old socket, and separate generation IDs so old callbacks cannot mark a new socket "healthy."
3. Use **exponential backoff with jitter** when reconnecting, e.g., a bounded increasing base delay; never sleep inside a network callback.
4. Cap maximum concurrent reconnects and TLS handshakes.
5. Re-authenticate the session/token if needed; do not skip authorization just because the reconnect is for the same user.
6. Provide **resumption/replay** for application messages requiring delivery semantics. WebSocket transport does not guarantee an event was processed by a business subscriber if the socket drops.
7. Do not automatically resend payment/order commands when you do not know if the server already committed; use request IDs, idempotency keys, and state checks.
8. Track heartbeat misses, RTT distribution, reconnect attempts, close codes, timeout phases, and network/device class.
9. Distinguish normal client closure on user logout from unexpected timeouts.
10. Never reuse an old `WebSocket` that has been `abort`ed; create a new WebSocket session and new state.

**Delivery note:** Ping/Pong is a connection check, **not** a business message ACK. Receiving a Pong after sending a chat event does not confirm that the user saw the event, that the server persisted the data, or that a consumer processed the transaction.

## 14. Detecting False Positives and Avoiding Misleading Monitoring

### 14.1. Events to Log/Metric

| Metric/event | What It Measures | Purpose |
| --- | --- | --- |
| `ws_heartbeat_ping_sent_total` | Number of successful Ping sends | Understand probe traffic, client count |
| `ws_heartbeat_send_fail_total` | Failed Ping send futures | Distinguish local/output errors |
| `ws_heartbeat_pong_matched_total` | Pongs whose payload matches pending | Liveness observed |
| `ws_heartbeat_pong_unmatched_total` | Late/unsolicited/mismatched Pongs | Debug correlation, duplicates |
| `ws_heartbeat_timeout_total` | Deadlines missing a matching Pong | Suspect rate, needs analysis |
| `ws_heartbeat_rtt_ms` | Duration from send timestamp to matching Pong | Baseline p95/p99 and variance |
| `ws_connection_reconnect_total` | Number of reconnect attempts | Detect reconnect storms |
| `ws_connection_close_code` | Close code per RFC | Separate normal closes from failures |
| `ws_listener_processing_lag_ms` | How much callbacks are delayed when measurable | Identify starvation/GC |
| `ws_business_ack_timeout_total` | Overdue application acks | Independent of protocol Ping |

**Do not attach raw authentication tokens, sensitive user IDs, or Pong payloads containing secrets to metric labels** due to high cardinality and security. You can aggregate by app instance, region, route, connection type, and version.

### 14.2. Layered Diagnosis

~~~text
No application messages seen
    |
    +-- Matching Pong received?
    |      |
    |      +-- Yes → WebSocket stack still responsive,
    |      |          check business queue/consumer/authorization
    |      |
    |      +-- No  → check network path, listener demand,
    |                 scheduler timing, timeout, GC, proxy/LB
    |
    +-- TCP FIN/RST / onClose / onError?
    |      |
    |      +-- Yes → inspect close reason/codes and reconnect policy
    |      |
    |      +-- No  → half-open/network blackhole may be occurring
    |
    +-- Did app-level ack arrive?
           |
           +-- No, but Pong did → suspect abnormal app consumer
           +-- Yes → part of the business path processed the message
~~~

**Do not use a single `isInputClosed() == false` check as a complete health check.** It is local state, not an active network probe.

## 15. Testing Heartbeats: Not Just the Happy Path

| Test | Setup | Expected |
| --- | --- | --- |
| Normal Ping→Pong | Server sends Pong echoing payload | Matching probe succeeds |
| Wrong-payload Pong | Server sends Pong `old` instead of `seq-current` | Ignored; pending remains |
| Unsolicited Pong | Server sends Pong with no outstanding Ping | Not treated as ack for future probes |
| Deliberately silent server | No Pong sent after Ping | Timeout → SUSPECT |
| Delayed Pong after deadline | Pong arrives late | Policy marks overdue; avoid reviving closed session |
| Reply only to latest Ping | Multiple outstanding probes | Exposes risk; design enforces one pending |
| Client auto-Pong | Server sends native Ping | Java 17 client auto-sends echoing Pong |
| Listener stops requesting demand | Override `onPong` without `request(1)` | Subsequent callback blocked; measures false timeout |
| Client sendPing while pending | Send back-to-back without awaiting future | May fail with `IllegalStateException` |
| 126-byte payload | `sendPing(ByteBuffer)` > 125 | Send operation rejected |
| Text frame `"PING"` | Server receives text, no Ping opcode | No automatic Pong control frame |
| Hung server app worker | Protocol server still auto-Pongs | Protocol heartbeat PASSES but business FAILS |
| GC pause/timer delay | Controlled scheduler stall in test | Timeout can false-positive |
| Proxy idle timeout | Test in staging environment with LB | Choose interval per actual idle policy |
| Absolute session timeout | LB closes after max lifetime despite traffic | Heartbeat does not prevent closure |
| Network blackhole | Drop return path in staging | Missing Pong, no immediate Close |
| Browser background | Throttle/suspend tab in test | App timer unreliable as an exact clock |
| Reconnect race | Old Pong callback arrives after new session | Does not validate new session |
| Mass reconnect | Many clients lose network simultaneously | Jitter/backoff avoids thundering herd |
| Graceful shutdown | Send close code 1000 and handle onClose | Stops timers/closes resources |
| Force abort | No Pong within deadline and policy aborts | Old socket is no longer used |

### 15.1. Tests Should Use Explicit Synchronization

Do not write unit tests that just do `Thread.sleep(100)` and hope a callback has been invoked. Use `CompletableFuture` or `CountDownLatch` with timeouts for integration tests; use a **simulated clock** for state machine deadlines.

Example 1 uses `CompletableFuture<String> pong1/pong2` to wait for the exact payload and timeout. Example 2 uses `nowMillis` for deterministic results independent of the OS scheduler. The two test styles complement each other: **wire correctness** and **policy correctness**.

### 15.2. Notes on Testing Over the Internet

Do not send Pings too frequently to servers you do not own. Use a local or staging server and tune frequency to service agreements. Tests for intentionally bad frames, oversized payloads, or deliberately disrupted links should only be run in authorized environments to avoid DoS or log spam.

## 16. Common Programming Mistakes

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Assuming `sendPing().get()` is a Pong ack | Future only represents send operation | Use `onPong`, nonce matching, and deadline |
| Sending a new Ping every tick while old Ping is pending | Hard to correlate, peer may reply only to latest | At most one outstanding probe |
| Treating every Pong as a reply to the current Ping | Unsolicited/stale Pongs exist | Compare payload token/session |
| Using payload >125 bytes | Violates RFC control frame limit | Keep payload short, do not fragment |
| Using text `"PING"` expecting native Pong | Text frame is not a control Ping | Use `sendPing` or separate app ack protocol |
| Calling `sendPong` manually in JDK's `onPing` | JDK already auto-sends reciprocal Pong | Usually just observe and request demand |
| Overriding `onOpen` without `request(1)` | Callbacks will not be received | Grant demand explicitly |
| Overriding `onPong` without `request(1)` | Subsequent Pongs may not arrive | Re-grant demand at the right time |
| Retaining callback's `ByteBuffer` after completion | Buffer may be reclaimed by JDK | Copy contents immediately |
| Mutating send `ByteBuffer` before future completes | Race/corrupted payload | Wait for send future before reusing |
| Treating Pong as business readiness | Pong is auto-replied by stack | App-level ack/health with business validation |
| Treating timeout as proof server is dead | Network/scheduler can be slow | Mark SUSPECT, configure appropriate policy |
| Using `currentTimeMillis` as deadline clock | System clock can jump | Use `nanoTime` / monotonic |
| Using a very low timeout on mobile | False positives from suspend/radio/GC | Measure RTT distribution and jitter |
| Sending heartbeat via browser JS Ping API | Browser does not expose native Ping/Pong | Use text/binary app heartbeat |
| Relying solely on TCP keepalive | Different OS timing/layer | Use WS/app heartbeat when needed |
| Using `sendClose` in every network blackhole and waiting forever | Graceful close can also hang | Bounded close, force abort per policy |
| Not stopping scheduler after socket close | Memory/thread/task leak | Cancel timer, release executor owner |
| Reconnecting immediately without jitter | Thundering herd | Exponential backoff+jitter |
| Not resetting token after reconnect | Old callback marks new session healthy | Session/generation ID |
| Retrying business writes after heartbeat timeout | Can duplicate transactions | Idempotency key/operation tracking |
| Logging Ping payloads containing secrets | Data leak in logs | Non-secret short nonce, redaction |
| Treating absence of `onError` as healthy | Half-open does not error immediately | Active probe + timeout |
| Assuming Ping always prevents LB idle timeout | LB may have absolute timeout/custom policy | Check infrastructure at every hop |

## 17. Exercises and Solutions

### Exercise 1 — Ping's CompletableFuture

A client calls `webSocket.sendPing(buffer).get()` and it succeeds. Does that guarantee the remote sent a Pong and the application processed the most recent request?

**Answer:** No. The future confirms the **send operation**, not receiving a Pong. You need `onPong` receiving a matching payload. And even a matching Pong does not confirm the business application processed other requests.

### Exercise 2 — Protocol Frame or Text?

An application sends the WebSocket text message `"PING"` and receives no Pong control frame. Is the server violating RFC 6455?

**Answer:** No. `"PING"` is a **text data frame**, not a WebSocket Ping control frame. The RFC only requires a Pong reply to a **Ping frame opcode 0x9** when conditions are met, not handling the word "PING" inside a message.

### Exercise 3 — Oversized Ping

A programmer creates `ByteBuffer.allocate(200)`, position=0, limit=200 and passes it to `sendPing`. What is wrong?

**Answer:** 200 bytes exceeds the **125-byte** limit for control frames; the Java API rejects it per contract. Use a short payload, and do not attempt to fragment a control frame.

### Exercise 4 — Late Old Pong

The current pending token is `seq-8`, and the listener receives Pong `seq-7`. Should it mark the session healthy and clear pending?

**Answer:** No. An old/unsolicited Pong does not prove `seq-8` was received by the peer. Keep pending, wait for the matching Pong until the deadline, or mark suspect.

### Exercise 5 — Missing onPong Callback

Server logs show a Pong was sent, but the client's `onPong` is not called after one successful call. Besides the network, what should you check?

**Answer:** Did `Listener.onOpen` and `Listener.onPong` call `webSocket.request(1)` to grant further demand? Receive callbacks are gated by flow control; do not immediately conclude the Pong never reached the machine.

### Exercise 6 — Server Still Replies Pong but Users Receive No Messages

The WebSocket protocol heartbeat always PASSES, yet the event consumer is not processing notifications. Why?

**Answer:** The WebSocket stack can **automatically send Pongs** independently of business handlers. You need app-level ack/readiness and queue/worker metrics, not Pong as proof of "business healthy."

### Exercise 7 — Timeout and State

The client receives no matching Pong within 8 seconds; does that prove the server process died?

**Answer:** No. That is a **policy timeout**, which could be caused by network jitter, GC pause, listener demand, overload, or a dead peer. Mark SUSPECT; the app may proactively reconnect to meet SLAs, but logs must be accurate.

### Exercise 8 — Unsolicited Pong

The server sends an unsolicited Pong. Must the client send a Pong in reply?

**Answer:** No. A Pong does not require a reply; do not create a Pong→Pong loop. If you want the client to reply at the business protocol level, design it separately rather than relying on RFC control Pongs.

### Exercise 9 — Browser WebSocket

Can browser JavaScript call `socket.sendPing(...)` and read `onpong` directly?

**Answer:** Not in the standard browser WebSocket API. Browsers handle protocol Ping/Pong in the network stack. For client-side app liveness, send an **application message** with a sequence and wait for a server-defined ack.

### Exercise 10 — RTT and Clock

Why use `System.nanoTime()` instead of `System.currentTimeMillis()` to measure Pong RTT?

**Answer:** `nanoTime` is suitable for measuring **monotonic duration**; `currentTimeMillis` represents wall-clock time which can jump due to NTP/clock adjustments. Do not use `nanoTime` to display UTC timestamps.

### Exercise 11 — Choosing Heartbeat Interval

A reverse proxy closes connections after 60 seconds idle, and the client sends a Ping every 5 minutes. Will this prevent idle timeouts?

**Answer:** Usually no. The Ping arrives too late. You must understand the proxy/server idle policy and set an appropriate interval, though it still does not guarantee preventing **absolute max lifetime** or policies that ignore control frames.

### Exercise 12 — Reconnect Storm

10,000 clients all time out at once and retry immediately after 0 ms. What is the risk and how do you fix it?

**Answer:** A TLS/connect storm overloading the server. Use exponential backoff, jitter, cap concurrent attempts, and enforce a single lifecycle owner per session.

### Exercise 13 — TCP Keepalive

Does `Socket.setKeepAlive(true)` prove the WebSocket application responder is healthy?

**Answer:** No. TCP keepalive only checks partial transport reachability per OS policy. If you need WebSocket protocol responsiveness, use Ping/Pong. If you need business readiness, use app-level ack/health.

### Exercise 14 — Case From the Demo

In the first example, the server replies with Pong `seq-1` but deliberately ignores Ping `seq-2`. Why does stdout still show `clientPingCount=2` while timeout is `true`?

**Answer:** Because the server **received** both Pings but **only replied to the first Ping**. This proves you must not treat "Ping sent/reached remote" as "Pong received"; timeout is a separate measurement.

### Exercise 15 — State Machine

A session received `seq-1` at t=35 ms, sent `seq-2` at t=120, and has not received a Pong by t=171 with a 50 ms timeout. What should the state be?

**Answer:** **SUSPECT** because 51 ms since t=120 exceeds the 50 ms limit. Do not call it `DEAD_CONFIRMED`; application policy decides whether to close/reconnect.

## 18. Production Code Review Checklist

- [ ] I distinguish protocol Ping/Pong, TCP keepalive, and application heartbeats.
- [ ] I use WebSocket `sendPing(ByteBuffer)`, not confusing text `"PING"` with a control frame.
- [ ] Ping payload is <=125 bytes, unfragmented, and contains no credentials/secrets.
- [ ] I know the Java 17 client automatically sends a reciprocal Pong for incoming Pings.
- [ ] I do not manually send unnecessary duplicate Pongs in `onPing`.
- [ ] I know the send future is only send completion, **not** a Pong ack.
- [ ] I implement `onPong` and match nonce/seq against the pending probe for the right session.
- [ ] I handle unsolicited/stale Pongs without completing the wrong probe.
- [ ] I call `request(1)` in `onOpen` and overridden receive handlers when needed.
- [ ] I do not retain the callback's `ByteBuffer` after the callback `CompletionStage` completes.
- [ ] I allow only one outstanding heartbeat Ping at a time.
- [ ] I separate send timeout, Pong timeout, callback lag, and connection error.
- [ ] I use the monotonic clock `System.nanoTime()` for intervals/deadlines.
- [ ] I choose heartbeat interval/timeout based on RTT, network/device, proxy/LB policy, and SLA.
- [ ] I do not treat a single missed Pong as absolute proof the peer is dead.
- [ ] I do not treat a matching Pong as proof the business API is healthy.
- [ ] I use a separate application ack if I need to verify consumer/database/transaction health.
- [ ] I understand browser JS does not control native WebSocket control Ping/Pong.
- [ ] I cancel scheduled tasks, stop timers, and clean up on `onClose`/`onError`.
- [ ] I use a bounded graceful close or `abort` depending on the situation; avoid hanging forever.
- [ ] I cap reconnect attempts and use exponential backoff+jitter.
- [ ] I prevent old-session callbacks from updating the new session's heartbeat using generation/session IDs.
- [ ] I do not automatically retry business writes after disconnect without idempotency safeguards.
- [ ] Metrics do not log secrets or raw Ping payloads.
- [ ] I have simulated-clock unit tests and loopback Ping/Pong integration tests.
- [ ] I test delayed/unmatched/unsolicited Pongs, receive demand, proxy idle, and reconnect races.

## 19. Standards and Java API References

- [RFC 6455 `5.5 — Control Frames](https://www.rfc-editor.org/rfc/rfc6455#section-5.5): opcodes 8/9/A, max 125-byte payload, no control frame fragmentation, directional masking.
- [RFC 6455 `5.5.2 — Ping](https://www.rfc-editor.org/rfc/rfc6455#section-5.5.2): when Ping may be sent and the requirement to send Pong in response.
- [RFC 6455 `5.5.3 — Pong](https://www.rfc-editor.org/rfc/rfc6455#section-5.5.3): payload echo, unsolicited Pong, and limits on replying to multiple Pings.
- [RFC 6455 `5.3 — Client-to-Server Masking](https://www.rfc-editor.org/rfc/rfc6455#section-5.3): client frames must be masked, XOR rule.
- [RFC 6455 `7 — Closing Handshake](https://www.rfc-editor.org/rfc/rfc6455#section-7): Close frame and connection closure.
- [Java SE 17 — WebSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html): `sendPing`/`sendPong`/`sendClose`/`abort`/`request`, pending sends, automatic Ping/Close handling.
- [Java SE 17 — WebSocket.Listener](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): `onOpen`, `onPing`, `onPong`, `onError`, `request(n)`, and buffer lifetime.
- [Java SE 17 — WebSocket.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html): `buildAsync` and `connectTimeout` for handshake.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): creating a WebSocket client via `newWebSocketBuilder`.
- [Java SE 17 — ScheduledExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html): periodically triggering state-based checks.
- [Java SE 17 — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): clock for measuring elapsed time.
- [MDN — WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket): browser JavaScript API does not expose native Ping/Pong to application code.

**Summary:** WebSocket **Ping/Pong** helps check **peer protocol responsiveness and the two-way path**. In Java 17, call `sendPing(ByteBuffer)`, receive and match Pongs via `Listener.onPong`, maintain `request(n)`, use a single pending token and monotonic deadlines; **do not confuse the send future with a Pong ack**. However, **a successful Pong does not prove the business service is healthy**, and **an overdue Pong does not absolutely prove the peer is dead**. Use heartbeats as **a signal for connection management decisions**, combined with application-level health, load limits, proxy/LB policies, reconnect backoff, and cleanup rules.
