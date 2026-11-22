# sendClose, Dual Input/Output Sides, and abort When Orderly Closure Is Not Possible

## Lesson Objectives

When working with `java.net.http.WebSocket` on Java 17+, closing a connection is **not** simply changing a single state from OPEN to CLOSED. A `WebSocket` object has **two independent sides**: **input** for receiving and **output** for sending. Calling `sendClose(...)` only initiates an **orderly closure of output** with a Close control frame; input may remain open to receive the reciprocal Close. If the peer does not respond, the transport fails, or the application cannot wait any longer, `abort()` closes **both input and output abruptly**.

After this lesson, you will be able to:

- Describe the **closing handshake** according to RFC 6455, distinguishing the Close frame, WebSocket state, and closing the underlying TCP/TLS connection.
- Explain `isInputClosed()` and `isOutputClosed()`; recognize that the state **input=false, output=true** is valid.
- Understand accurately the future returned by `sendClose(int, String)`: it completes when the **Close message has been sent**, not when the peer has responded or application data has been processed.
- Use `WebSocket.Listener.onClose`, `onError`, and `request(n)` to properly observe receiving and errors.
- Choose `sendClose` for graceful shutdown and `abort` when the deadline expires or orderly closure is not possible.
- Control valid Close codes, UTF-8 reason up to 123 bytes, pending sends, and avoid sending again after output has closed.
- Chain `sendText` before `sendClose` in the proper order; understand why Close does not replace application acknowledgment.
- Run a **standalone Java 17+ program on loopback** demonstrating the difference before/after the reciprocal Close and before/after abort.

**Scope:** the `java.net.http.WebSocket` client available since Java 11, using Java 17 APIs for testing. This is not `javax.websocket.Session` or `Socket.shutdownInput/shutdownOutput`, nor the `HttpClient.close/shutdown` lifecycle methods introduced in Java 21. The mock server in this lesson is only a minimal testing tool, **not a production WebSocket server**.

## 1. Why Does WebSocket Need a Separate Closing Protocol?

After the HTTP opening handshake (typically `101 Switching Protocols`), WebSocket transmits data in **frames** over a long-lived connection. Both endpoints can send data; there is no concept of each HTTP response automatically ending the session.

~~~text
Client                                        Server
   │── GET /chat + Upgrade: websocket ──────►│
   │◄──────── HTTP/1.1 101 Switching Protocols│
   │                                         │
   ╞══════ WebSocket established ═══════════╡
   │────── Text / Binary / Ping ────────────►│
   │◄────────────── Text / Binary / Pong ────┤
   │                                         │
   │────── Close (status 1000) ─────────────►│
   │◄──────────────────── Close (status 1000)│
   │       close underlying TCP/TLS         │
~~~

**Close** in WebSocket is a **control frame**, not an HTTP status code or a command that directly sends a TCP FIN. According to RFC 6455, one side can initiate with a Close frame; the other side responds with a Close if it has not already sent one. When both have **sent and received Close**, the WebSocket connection can end cleanly by closing the underlying transport.

Do not confuse three milestones:
1. **Local Close frame sent**: the sending side has signaled its intent to close.
2. **Reciprocal Close frame received**: the peer has emitted Close; the listener can report the event.
3. **Underlying TCP/TLS connection closed**: transport resources terminate; the RFC distinguishes closing *cleanly* after the handshake from abnormal closure due to network loss.

A peer can drop the network immediately after receiving a message, preventing the client from seeing a Close frame; that is an **abnormal closure**, not an orderly closing handshake.

## 2. Two Independent Sides: input and output

The Javadoc defines `WebSocket` as having an **input side** and an **output side**. Once a side is closed, it cannot be reopened.

| API | Question It Answers |
|---|---|
| `isInputClosed()` | Has the **receiving** side for WebSocket messages closed? |
| `isOutputClosed()` | Has the **sending** side for WebSocket messages closed? |
| `sendClose(code, reason)` | Initiates closing **output** with a WebSocket Close frame |
| `abort()` | Closes **both input and output** abruptly |

### Four State Combinations

| Input closed? | Output closed? | Common Interpretation |
|---|---|---|
| `false` | `false` | Both sides open; can send and receive according to WebSocket rules |
| `false` | `true` | Close sent; no more data can be sent; can still wait for Close from peer |
| `true` | `false` | Close received, input closed; output may be waiting for listener completion to respond |
| `true` | `true` | Both sides closed due to Close handshake, error, or abort |

The two getters **do not tell you who closed first** or the Close code. The value is a snapshot at the time of the call; receiving/sending threads can cause it to change right after checking. The Javadoc guarantees that once a getter returns `true`, subsequent calls also return `true`.

**Proper understanding:** these are the two sides of the **WebSocket API**, not a direct guarantee about TCP half-close or the timing of TCP FIN. The implementation manages the underlying TCP/TLS; the application uses the WebSocket protocol API.

## 3. `sendClose` Closes Output Orderly, Not Input

Common invocation:

~~~java
CompletableFuture<WebSocket> closeSent =
    socket.sendClose(WebSocket.NORMAL_CLOSURE, "");
~~~

`WebSocket.NORMAL_CLOSURE` = **1000**. The returned future completes **when the Close message has been sent**; if sending fails, the future completes exceptionally. This **does not mean** the peer has received the Close or has completed application work.

~~~text
Client connected
 input=false, output=false
             │
    sendClose(1000,"bye")
             ▼
    local Close sent
 input=false, output=true   ← completely normal
             │
    peer sends reciprocal Close
             ▼
     listener.onClose
 input=true, output=true
~~~

The Java 17 Javadoc explicitly states: `sendClose` **does not close input**. It only initiates the closure of output. Input remains open until a Close is received, abort is called, or an error occurs. Therefore, the code below **must not** assert that input is closed:

~~~java
socket.sendClose(WebSocket.NORMAL_CLOSURE, "bye").join();
System.out.println(socket.isOutputClosed()); // true when send succeeds
System.out.println(socket.isInputClosed());  // may be false
~~~

This snippet requires a connected `socket` variable. `join()` can block the thread **until the send completes**, not waiting for the remote Close. If you need to wait for the remote Close, create a future completed by the listener when `onClose` or `onError` occurs and set a separate deadline.

### Do Not Continue Sending Data After Close

Once output is closed, new `sendText`, `sendBinary`, `sendPing`, or `sendPong` operations may fail with `IOException`. A closed WebSocket cannot be "reopened"; create a new connection if you want to continue communicating.

If you need to send a final message before Close, **do not** start both operations independently and hope for the right order:

~~~java
// Should not be used to guarantee the final message completes before Close:
socket.sendText("last data", true);
socket.sendClose(WebSocket.NORMAL_CLOSURE, "");
~~~

Use a dependent future:

~~~java
CompletableFuture<WebSocket> closedOutput =
    socket.sendText("last data", true)
        .thenCompose(ws -> ws.sendClose(
            WebSocket.NORMAL_CLOSURE, ""));
~~~

`thenCompose` guarantees **sending Close is only initiated when the previous data-sending future completes normally**. It **does not** guarantee the server has processed the data at the business layer. If you need a server ACK/commit, design a message ID/ACK and wait for that confirmation **before** the closing handshake.

## 4. Close Status Code, Reason, and Parameter Errors

A Close frame can carry a **status code** along with a **UTF-8 reason**:

| Status | Common Meaning |
|---|---|
| `1000` | Normal closure |
| `1001` | Going away, e.g., endpoint is about to shut down |
| `1008` | Policy violation |
| `1011` | Server encountered an internal error and cannot continue processing |
| `1005` | Sentinel code when Close is received without a code; must not be sent on the wire |
| `1006` | Abnormal closure, no valid Close frame received; **must not be sent on the wire** |
| `1015` | Sentinel code related to TLS failure; must not be sent on the wire |
| `3000–3999` | Status codes registered by libraries/frameworks/applications via registry |
| `4000–4999` | Private range by application agreement |

**According to the Java SE 17 `WebSocket.sendClose` Javadoc:** the code passed to the method must be in the range **1000–4999**; codes `1002`, `1003`, `1006`, `1007`, `1009`, `1010`, `1012`, `1013`, and `1015` are marked illegal by the JDK; the behavior of other codes may depend on the implementation. That list **does not replace** protocol/IANA rules: you should not send reserved sentinel codes such as 1005. For normal closure, choose `WebSocket.NORMAL_CLOSURE`.

### Reason Maximum 123 UTF-8 Bytes

A control frame has a maximum payload of **125 bytes**. When a code is present, the **first 2 bytes** are reserved for the status, leaving **123 bytes** to describe the reason. Java's `String.length()` measures UTF-16 code units, **not** UTF-8 byte count:

~~~java
String reason = "Session ended";
int bytes = reason.getBytes(StandardCharsets.UTF_8).length;
if (bytes > 123) {
    throw new IllegalArgumentException("Close reason too long");
}
socket.sendClose(WebSocket.NORMAL_CLOSURE, reason);
~~~

The snippet requires importing `java.nio.charset.StandardCharsets` and an open `socket` variable. An invalid reason/code can cause the future from `sendClose` to complete exceptionally with `IllegalArgumentException`; a `null` reason can cause `NullPointerException`. An I/O error or already-closed output leads to exceptional completion with `IOException`.

The Javadoc also specifies: except for invalid arguments (e.g., `IllegalArgumentException`/`NullPointerException` per contract), calling `sendClose` transitions output to a closed state. Do not retry sending Close indefinitely when a send fails with an I/O error.

**Security:** the reason is data that can be logged or appear on the peer; do not put access tokens, session cookies, secret file paths, or stack traces into the reason.

## 5. `Listener.onClose` and Receive Demand

`WebSocket.Listener` is where events from the **input** side are received:

- `onOpen` is called once when the WebSocket connects; typically grants receive demand with `socket.request(1)`.
- `onText`, `onBinary`, `onPing`, `onPong`, and `onClose` are receive methods governed by the WebSocket's demand counter.
- `onClose(socket, code, reason)` is called when a **Close frame is received**. **As soon as onClose begins, input is already closed**. This is the listener's final callback for that WebSocket.
- `onError(socket, error)` reports an error; when it is called, **both input and output are already closed**. This is also a final callback, but it is **not** the same as receiving a valid Close.
- Java WebSocket has a mechanism to **automatically handle the reciprocal Close**; the listener is not required to manually call `sendClose` when the peer sends Close.

Listener pattern for tracking the outcome:

~~~java
static final class CloseListener implements WebSocket.Listener {
    final CompletableFuture<Integer> peerClose = new CompletableFuture<>();

    @Override
    public void onOpen(WebSocket socket) {
        socket.request(1);
    }

    @Override
    public CompletionStage<?> onClose(
            WebSocket socket, int statusCode, String reason) {
        peerClose.complete(statusCode);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public void onError(WebSocket socket, Throwable error) {
        peerClose.completeExceptionally(error);
    }
}
~~~

This is a **code snippet of a class**, requiring imports `java.net.http.WebSocket` and `java.util.concurrent.*`. The complete runnable program in section 10 uses a similar listener.

### Why Is `request(1)` Important?

Initial receive demand is **0**, and `request(n)` allows `n` additional receive callback invocations. It **does not send an HTTP request** and does not mean each invocation corresponds to one complete WebSocket message. If the listener consumes multiple text fragments without calling `request(1)` again, demand may be exhausted before Close, preventing `onClose` from being called even though the peer has sent Close.

In an example with only a Close frame, `request(1)` in `onOpen` is sufficient for the Close callback. For a chat application receiving multiple text messages, each `onText` must manage the content and grant subsequent demand according to policy.

### Peer Sends Close First

If the peer sends Close while local output is still open, Java WebSocket **automatically manages the reciprocal Close**. According to the Javadoc, the stage returned by `onClose` can control when the implementation closes output if output is not yet closed. Returning `null` (default) signals it can close immediately; returning a stage that never completes can **delay the automatic Close response**, causing a liveness bug. Only customize `sendClose` inside `onClose` if you genuinely need to choose a reciprocal close code/reason per protocol and understand the callback contract; do not unconditionally send two Close frames.

## 6. `abort()`: Abruptly Stopping Both Sides

`socket.abort()` is a `void` method. According to the Java 17 Javadoc, after it **returns**:
- `socket.isInputClosed() == true`.
- `socket.isOutputClosed() == true`.
- Pending send operations will fail with `IOException`.
- Calling `abort()` again has no additional effect.

~~~java
socket.abort();
assert socket.isInputClosed();
assert socket.isOutputClosed();
~~~

The snippet assumes `socket` has already been created. `abort` does not send an orderly WebSocket Close frame like `sendClose`, does not wait for the peer, and does not guarantee the peer has processed pending data. Therefore, it is a **force stop**, not a "cleaner but faster close".

### When to Use It?

| Situation | Reasonable Choice |
|---|---|
| Normal session completion and peer responds | `sendClose(1000, reason)` and wait for reciprocal Close |
| `sendClose` finished but peer does not return Close before deadline | `abort()` and record timeout |
| I/O error or protocol state cannot safely continue | `abort()` or let the implementation stop on error, do not send further |
| Application must stop immediately | `abort()` while accepting abnormal connection closure |
| Close sent, but want to wait for peer a little longer | Do not abort immediately; observe input/onClose with a deadline |
| Business logic requires knowing whether the last message committed | Need **application ACK**, Close does not replace it |

**Do not infer that abort performs a rollback:** the server may have already received/written the transaction before the local client force-closed. Upon reconnecting, you need message IDs, an idempotency policy, server state synchronization, and bounded retries.

## 7. Two Futures Must Be Tracked Separately

A proper graceful close usually has at least **two independent events**:

1. **Close has been sent:** the future returned by `sendClose` completes.
2. **Peer Close has arrived:** the listener's `onClose` completes an application-managed future.

~~~text
Application stops new sends
             │
     Wait for pending sends
             │
             ▼
  sendClose(1000, reason)
             │
             ├── send failed ───────► abort / report
             ▼
    Close-send future done
             │
             ├── peer onClose ──────► graceful path
             │
             ├── listener onError ──► error path
             │
             └── deadline expired ─► abort / timeout path
~~~

If you only call `sendClose(...).join()`, you are only waiting for **part 1**. If you only call `peerClose.join()` without a timeout, a hung peer can hold the thread forever.

### `CompletableFuture.orTimeout` Does Not Auto-Abort

~~~java
CompletableFuture<WebSocket> sending =
    socket.sendClose(WebSocket.NORMAL_CLOSURE, "");

sending.orTimeout(2, TimeUnit.SECONDS)
    .whenComplete((ws, failure) -> {
        if (failure != null) {
            socket.abort();
        }
    });
~~~

This snippet requires importing `java.util.concurrent.*`. `orTimeout` makes **the future itself** complete exceptionally if not finished within the limit; it **does not** automatically cancel the network operation or send a reciprocal Close. In the example, the application explicitly calls `abort()` when the deadline is exceeded. A second deadline is also needed to wait for the **peer Close** after the local Close has been sent.

### Scheduler for Graceful Deadline

A complementary pattern:

~~~java
ScheduledFuture<?> deadline = scheduler.schedule(
    () -> {
        if (!socket.isInputClosed()) {
            socket.abort();
        }
    },
    3, TimeUnit.SECONDS);

peerClose.whenComplete((code, error) -> {
    deadline.cancel(false);
    if (error != null) {
        socket.abort();
    }
});
~~~

The snippet assumes `scheduler` is a running `ScheduledExecutorService` and `peerClose` is a `CompletableFuture<Integer>` from the listener. Only start the timer **after the local Close has been sent**; otherwise, the grace period measurement may not behave as intended. Manage the scheduler in the application lifecycle; do not create a new thread for each WebSocket and forget to shut it down.

**Clean closure is not a hard timing guarantee:** the deadline is an application policy; if the peer does not cooperate, `abort` frees local sides but does not guarantee the server completed business processing. When shutting down a service with many sockets, you need a coordinator and limits on connections/scheduled tasks.

## 8. Send Ordering and Races Across Multiple Threads

In the Java 17 WebSocket client, `sendText`/`sendBinary` have a pending-operations contract. An incomplete pending text/binary send or an unfinished fragment sequence can cause another operation to fail with `IllegalStateException`. `sendClose` also closes output. Therefore, three threads sending a message, a ping, and a close should not be treated as completely independent actions.

**Recommended pattern:** have a coordinator own the OPEN → CLOSING → CLOSED lifecycle, stop accepting new outbound messages when closing starts, chain futures for the final message, and then send Close. Update an application state atomically/with a lock if multiple threads try to close simultaneously; only one thread initiates the closing handshake.

Example:

~~~java
CompletableFuture<WebSocket> finalSend =
    socket.sendText("BYE", true);

CompletableFuture<WebSocket> closeSend =
    finalSend.thenCompose(ws ->
        ws.sendClose(WebSocket.NORMAL_CLOSURE, "done"));
~~~

Do not add new `sendText` calls once the application state transitions to CLOSING. `isOutputClosed()==false` is not an atomic permission token: right after checking, another thread could close output. Always handle exceptional completion on send futures.

**What should not be promised:** completion of `sendText`'s future does not prove the peer processed the message in a business sense. If "server saved it" is required, there must be a separate ACK or response message before closing.

## 9. Runnable Example: Server Responds to Close vs. Unresponsive Server

To test **half-closed** state deterministically rather than relying on `Thread.sleep`, the program uses a **CountDownLatch** allowing the mock server to delay returning Close until after the client checks the state.

- **Cooperative server:** receives Close from the client, waits on the latch; client prints `input=false output=true`, server sends Close 1000, listener receives it, and client prints `true/true`.
- **Unresponsive server:** receives Close but does not return Close; client sees `false/true`, calls `abort()`, and then sees `true/true`.

Both client and server bind/connect on loopback `127.0.0.1`. `TestServer` **only** accepts one short masked Close frame and sends one minimal Close frame. It is not a complete HTTP/WebSocket stack and must not be reused in a real service.

### 9.1. File `WebSocketCloseDemo.java`

~~~java
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Base64;
import java.util.concurrent.*;

public class WebSocketCloseDemo {
    static final class CloseListener implements WebSocket.Listener {
        final CompletableFuture<Integer> peerClose = new CompletableFuture<>();

        @Override
        public void onOpen(WebSocket socket) {
            socket.request(1);
        }

        @Override
        public CompletionStage<?> onClose(WebSocket socket,
                int statusCode, String reason) {
            peerClose.complete(statusCode);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket socket, Throwable error) {
            peerClose.completeExceptionally(error);
        }
    }

    static final class TestServer implements AutoCloseable {
        final ServerSocket listener;
        final ExecutorService worker = Executors.newSingleThreadExecutor();
        final CountDownLatch mayFinish = new CountDownLatch(1);
        final CompletableFuture<Void> closeReceived = new CompletableFuture<>();
        final boolean replyToClose;
        final Future<?> task;

        TestServer(boolean replyToClose) throws IOException {
            this.replyToClose = replyToClose;
            listener = new ServerSocket(0, 1,
                InetAddress.getByName("127.0.0.1"));
            task = worker.submit(this::run);
        }

        URI uri() {
            return URI.create("ws://127.0.0.1:"
                + listener.getLocalPort() + "/close");
        }

        void release() {
            mayFinish.countDown();
        }

        void run() {
            try (Socket peer = listener.accept()) {
                peer.setSoTimeout(5_000);
                InputStream in = peer.getInputStream();
                OutputStream out = peer.getOutputStream();

                ByteArrayOutputStream headerBytes = new ByteArrayOutputStream();
                int b;
                while ((b = in.read()) != -1) {
                    headerBytes.write(b);
                    int n = headerBytes.size();
                    byte[] data = headerBytes.toByteArray();
                    if (n >= 4 && data[n-4] == '\r'
                            && data[n-3] == '\n'
                            && data[n-2] == '\r'
                            && data[n-1] == '\n') {
                        break;
                    }
                    if (n > 16_384) throw new IOException("Oversized handshake");
                }

                String headers = headerBytes.toString(StandardCharsets.US_ASCII);
                String key = null;
                for (String line : headers.split("\r\n")) {
                    if (line.regionMatches(true, 0,
                            "Sec-WebSocket-Key:", 0, 18)) {
                        key = line.substring(18).trim();
                    }
                }
                if (key == null) throw new IOException("No WebSocket key");

                byte[] digest = MessageDigest.getInstance("SHA-1").digest(
                    (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                    .getBytes(StandardCharsets.US_ASCII));
                String accept = Base64.getEncoder().encodeToString(digest);
                out.write(("HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\n"
                    + "Connection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n")
                    .getBytes(StandardCharsets.US_ASCII));
                out.flush();

                int first = in.read();
                int second = in.read();
                if (first < 0 || second < 0
                        || (first & 0x0f) != 8
                        || (second & 0x80) == 0
                        || (second & 0x7f) > 125) {
                    throw new IOException("Expected masked Close frame");
                }
                byte[] mask = in.readNBytes(4);
                int len = second & 0x7f;
                byte[] payload = in.readNBytes(len);
                if (mask.length != 4 || payload.length != len) {
                    throw new EOFException("Truncated Close frame");
                }
                for (int i = 0; i < payload.length; i++) {
                    payload[i] ^= mask[i % 4];
                }
                if (payload.length < 2
                        || (payload[0] & 0xff) != 3
                        || (payload[1] & 0xff) != 232) {
                    throw new IOException("Expected close code 1000");
                }
                closeReceived.complete(null);

                if (!mayFinish.await(5, TimeUnit.SECONDS)) {
                    throw new IOException("Test not released");
                }
                if (replyToClose) {
                    out.write(new byte[] {
                        (byte) 0x88, 0x02, 0x03, (byte) 0xe8
                    });
                    out.flush();
                }
            } catch (Exception error) {
                closeReceived.completeExceptionally(error);
                throw new CompletionException(error);
            }
        }

        @Override
        public void close() throws Exception {
            release();
            try {
                task.get(5, TimeUnit.SECONDS);
            } finally {
                listener.close();
                worker.shutdownNow();
            }
        }
    }

    static WebSocket connect(TestServer server, CloseListener listener)
            throws Exception {
        return HttpClient.newHttpClient().newWebSocketBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .buildAsync(server.uri(), listener)
            .get(3, TimeUnit.SECONDS);
    }

    static void cooperative() throws Exception {
        try (TestServer server = new TestServer(true)) {
            CloseListener listener = new CloseListener();
            WebSocket socket = connect(server, listener);
            socket.sendClose(WebSocket.NORMAL_CLOSURE, "bye")
                .get(3, TimeUnit.SECONDS);
            server.closeReceived.get(3, TimeUnit.SECONDS);

            System.out.println("graceful sent: input="
                + socket.isInputClosed()
                + " output=" + socket.isOutputClosed());

            server.release();
            int code = listener.peerClose.get(3, TimeUnit.SECONDS);
            System.out.println("graceful peer: code=" + code
                + " input=" + socket.isInputClosed()
                + " output=" + socket.isOutputClosed());
        }
    }

    static void unresponsive() throws Exception {
        try (TestServer server = new TestServer(false)) {
            CloseListener listener = new CloseListener();
            WebSocket socket = connect(server, listener);
            socket.sendClose(WebSocket.NORMAL_CLOSURE, "bye")
                .get(3, TimeUnit.SECONDS);
            server.closeReceived.get(3, TimeUnit.SECONDS);

            System.out.println("stalled before abort: input="
                + socket.isInputClosed()
                + " output=" + socket.isOutputClosed());
            socket.abort();
            System.out.println("stalled after abort: input="
                + socket.isInputClosed()
                + " output=" + socket.isOutputClosed());
            server.release();
        }
    }

    public static void main(String[] args) throws Exception {
        cooperative();
        unresponsive();
    }
}
~~~

### 9.2. Compilation and Output

Using JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 WebSocketCloseDemo.java
java WebSocketCloseDemo
~~~

Verified stdout (compiled with `--release 17`, run on Java and loopback):

~~~text
graceful sent: input=false output=true
graceful peer: code=1000 input=true output=true
stalled before abort: input=false output=true
stalled after abort: input=true output=true
~~~

### 9.3. Line-by-Line Explanation

1. `graceful sent`: the client has sent Close while the server is waiting on the latch, so output is closed while input remains open.
2. `graceful peer`: the server emits a Close frame with code 1000, the client's `onClose` receives it; input closes and output was already closed.
3. `stalled before abort`: the server side does not send a reciprocal Close even though it received the client's Close, showing that `sendClose` does not automatically close input.
4. `stalled after abort`: calling `abort()` guarantees closing both sides when the method returns.

**Synchronization point:** `CountDownLatch` ensures the measured state does not depend on network latency. The test server serves only one connection at a time and does not handle text/binary frames or all RFC corner cases; production must use a complete WebSocket server implementation.

**Why does the code use masking?** RFC 6455 requires client-to-server frames to be masked. The test fixture unmasks the 4-byte masking key to read the Close status 1000 in the payload. The fixture's server-to-client Close frame is unmasked. This accurately illustrates the basic wire-format rule without claiming to be a production parser.

**Why does `onOpen` call `request(1)`?** Because receiving Close is a receive callback and requires demand. Without demand, the listener may never report the reciprocal Close, leading to a false timeout.

## 10. Peer Closes First, Simultaneous Close, and Different Close Codes

### Peer Closes First

When the server sends Close first:
- Client input closes when `onClose` is called.
- Java WebSocket can automatically respond with Close to the peer over output if output is still open.
- Per the `Listener.onClose` contract, the returned completion stage can decide when output is allowed to close.
- It is not required to write `onClose(...){ socket.sendClose(...); }` just to "reply"; accidentally sending two Close frames is unnecessary.

If a handler wants a custom Close reason/code on the peer-initiated path, read the Javadoc contract carefully; in simple cases, return `null` or a completed stage and let the implementation respond.

### Both Sides Send Close Simultaneously

~~~text
Client                                        Server
send Close(1000) ────────────────►           send Close(1001)
                 ◄───────────────────────────
recv Close(1001)                               recv Close(1000)
~~~

According to RFC 6455, the code each endpoint records is the code in the **first Close frame it receives**. Therefore, the local code and remote code can differ in a simultaneous close scenario **without** a protocol error. Log `localCloseCode` and `remoteCloseCode` separately instead of forcing them to match.

### Transport Drops Before Close

When a TCP socket is reset, a firewall/proxy cuts the path, or the TLS transport breaks, the listener may report an error instead of Close. `1006` is an **abnormal closure symbol**, not a Close frame with code 1006 sent by the peer. Do not treat every connection drop as a WebSocket authentication error; distinguish timeouts, TCP/TLS failures, proxy idle limits, and application errors.

## 11. Cleanup and Reconnect Do Not Equal Business Completion

A WebSocket session often serves long-running transactions:
- The client sends message A and the server may have received it without writing it to the database yet.
- The client calls `sendClose` and waits for the reciprocal Close.
- The server responds with Close, but no RFC mechanism guarantees A was committed to the database.
- If the connection is aborted while a business request is pending, the client may not know whether the server executed A.

Therefore, when at-least-once/at-most-once semantics are needed:
- Attach a **message ID**, sequence/offset, and timestamp where appropriate.
- Build an **application ACK** after the server processes/records per contract.
- Mark requests complete only based on the ACK, not on the Close frame.
- Use idempotency/deduplication for retries after disconnect.
- When reconnecting, synchronize state against server-truth instead of resending everything unconditionally.

### `ws://` and `wss://`

- `ws://` has no TLS; examples only bind loopback and send no secrets.
- `wss://` protects the channel with TLS. Still validate certificates/hostnames properly; do not use trust-all to work around errors.
- A reverse proxy may terminate TLS; the backend needs separate protection according to your threat model.
- Do not put Bearer tokens, session cookies, or sensitive data in close reasons/logs; also protect opening handshake headers.
- Proxies/load balancers may have idle timeouts. Ping/Pong helps check liveness per policy, but **does not replace the closing handshake**.

### Reconnecting After `abort`

Do not reuse a closed `WebSocket`. Create a new connection via `HttpClient.newWebSocketBuilder()`; apply **retry/backoff with jitter**, cap retries, verify authentication is still valid, and recover state based on ACKs. Do not auto-reconnect indefinitely when rejected by policy, as this can create heavy load.

## 12. Shutdown Checklist for a Real-World WebSocket Client

1. **Transition application state to CLOSING** to prevent new outbound sends from being created.
2. **Track pending send futures** and decide how long to wait before closing; do not call `sendText` after output closes.
3. **Keep sufficient receive demand** to process the Close frame; do not accidentally block the listener.
4. **Send `sendClose(NORMAL_CLOSURE, reason)`** with a valid code/reason, without putting secrets in the reason.
5. **Set a deadline on the Close send future**; a send failure is not a "clean close".
6. **Wait for listener `onClose` or `onError`** with a separate deadline; distinguish peer Close from transport error.
7. **If the deadline expires, call `abort()`** and record an abnormal/forced shutdown; do not claim the peer processed the final message.
8. **Release application resources** such as scheduled tasks, custom executors, message queues, and subscription state by their proper owner.
9. **Record telemetry**: local/remote close code, Close send duration, peer Close wait duration, timeout/abort/error, and pending message count.
10. **If reconnecting**, only reconnect when policy permits; prevent lost/duplicate business operations with application ACKs and idempotency.

## 13. Common Mistakes and Fixes

| Misconception | Correct Understanding |
|---|---|
| “Once `sendClose(...).join()` finishes, the entire WebSocket is closed.” | The future only confirms Close **was sent**; input may still be open |
| “`sendClose` closes both input and output.” | `sendClose` closes **output** and waits for peer Close for input |
| “`isInputClosed` and `isOutputClosed` are always the same.” | The two states are **independent** |
| “`onClose` always needs to call `sendClose` itself to reply.” | The JDK manages the reciprocal Close automatically; read the callback contract |
| “`onClose` can continue receiving text afterward.” | It is the socket's final callback |
| “Without receive demand, `onClose` will still definitely be called.” | `request(n)` is required to grant receive callbacks |
| “`abort` is like sending Close 1000 but faster.” | Abort closes **abruptly**, without an orderly handshake |
| “`abort` emits Close code 1006 on the wire.” | 1006 is an abnormal sentinel, must not be sent |
| “Reason is at most 123 Java characters.” | The limit is **123 UTF-8 bytes** |
| “`orTimeout` automatically terminates the socket.” | It only alters future completion; call abort if you want to force close |
| “Closing the WebSocket means the server committed the last message.” | An application-level ACK/transaction confirmation is required |
| “Checking `isOutputClosed()==false` and then sending is thread-safe.” | There is a race; use a coordinator and handle future exceptions |
| “`sendText` and `sendClose` started independently always run in order.” | Chain futures to guarantee send before Close |
| “`onError` is guaranteed to be called after every abort.” | The Javadoc does not promise a separate callback for every abort |
| “A valid Close always equals immediate TCP closure.” | The WebSocket API and underlying transport have different lifecycles |
| “A closed WebSocket can be reused.” | A new connection must be created |
| “The simple `TestServer` in this lesson is production-ready.” | It only supports the test's handshake and short Close frame |
| “Network loss always comes with a peer-sent Close code.” | It can be an abnormal TCP/TLS loss with no Close frame |

## 14. Self-Check Exercises

1. What roles do the input/output sides of `java.net.http.WebSocket` play? When do they have different values?
2. After `socket.sendClose(1000,"").join()`, what has been confirmed and what has not?
3. What does `Listener.onClose` indicate about input state **as soon as the callback begins**?
4. Does Java WebSocket automatically reply to an incoming Close? When do you need a custom Close in the listener?
5. Why is `request(1)` in `onOpen` important? Does it send a message over the network?
6. A server does not return Close after 5 seconds. To avoid waiting forever, what should the client's policy be?
7. After `abort()` returns, what values must `isInputClosed/isOutputClosed` return?
8. Does `abort` guarantee sending Close status 1006 or waiting for a peer reply?
9. Why must `1005`, `1006`, and `1015` not be emitted as Close statuses on the wire?
10. Is a close reason of 110 Vietnamese characters always valid under the 123-byte limit? How do you check?
11. Distinguish the timeouts of the `sendClose` future and waiting for the `onClose` future.
12. Why does `CompletableFuture.orTimeout` not guarantee the network operation has stopped?
13. Write a snippet chaining `sendText("done",true)` followed by `sendClose(...)` in order.
14. Client sends Close 1000, server sends Close 1001 at the same time. Why can the logs differ?
15. In the demo, why does `graceful sent` display `input=false output=true`?
16. In the demo, why does calling `abort` on an unresponsive connection yield `true/true`?
17. When the server has received a message before Close, does the Close reply prove the database wrote the message?
18. If you need to prevent duplicate business sends on reconnect, what identifiers/ACKs should the application have?
19. What does `wss://` solve, and what still needs to be handled at the application/proxy level?
20. Is `java.net.http.WebSocket` the same API as `javax.websocket.Session`?

**Core answers:** (1) input receives/output sends independently; (2) Close was sent, reciprocal Close not necessarily received; (3) input is already closed; (4) JDK handles it automatically, custom only when a special contract is needed; (5) receive demand, does not send over the network; (6) graceful wait with a deadline then abort; (7) true/true; (8) no; (9) reserved/sentinel; (10) no, count UTF-8 bytes; (11) two different events; (12) only changes future state; (13) `thenCompose`; (14) each side sees the first Close frame it receives; (15) server has not returned Close yet; (16) abort abruptly closes both sides; (17) no; (18) IDs, ACK, dedup/idempotency; (19) TLS protects the channel, does not replace app ACK/authorization; (20) two different APIs.

## 15. Summary

- **Two independent sides:** `WebSocket.isInputClosed` and `isOutputClosed` do not have to change together; once closed, a side cannot be reopened.
- **`sendClose` closes output orderly:** the future completes when Close is sent, **not** when the peer confirms; input may remain open.
- **`onClose` is the Close-received event:** input is already closed when the callback begins; the implementation automatically manages the reciprocal Close, and receive demand is required.
- **`abort` stops abruptly:** when it returns, both sides are closed and pending sends fail; use when waiting for graceful closure is not possible/appropriate.
- **Close code/reason:** use status 1000 for normal closure; do not send 1006; reason is limited to 123 UTF-8 bytes.
- **Manage with deadlines:** stop outbound sends, wait for pending sends, send Close, wait for peer Close with a timeout, fall back to abort, and clean up.
- **Close is not a business ACK:** reconnect/retry requires message IDs, server confirmation, and idempotency.
- **Tested Java 17 example** on TCP loopback with states before/after reciprocal Close and before/after abort.

### References

- [Oracle Java SE 17 — WebSocket: sendClose, isInputClosed, isOutputClosed, and abort](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html)
- [Oracle Java SE 17 — WebSocket.Listener: onClose, onError, request(n)](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html)
- [Oracle Java SE 17 — WebSocket.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html)
- [Oracle Java SE 17 — HttpClient.newWebSocketBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html)
- [IANA — WebSocket Close Code Number Registry](https://www.iana.org/assignments/websocket/websocket.xhtml)
