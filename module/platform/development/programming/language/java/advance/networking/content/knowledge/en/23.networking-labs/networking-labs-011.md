# Verifying WebSocket Message Fragmentation and Receive Throttling in a Java 17 Client

## 1. What does the experiment need to prove?

When a WebSocket server sends a **text message split into multiple frames**, a Java client can receive the data parts via `WebSocket.Listener.onText(...)`. However, **frame**, **message**, **callback**, and **TCP packet** are not the same concept. Besides reassembling the message correctly, the client must control receiving with `WebSocket.request(n)` so callbacks do not run ahead of processing capacity.

In this lab, we create a **verification-only** server running on `127.0.0.1` that sends a `Hello Java` message in **three frames**, then sends a second message `next` and Close code `1000`. The client uses the standard `java.net.http.WebSocket` from **JDK 17+**; the Listener intentionally **does not** call `request` in `onOpen`. After the server finishes sending, we verify:

1. Without granting receive demand: **0 `onText` calls**.
2. Granting `request(1)`: exactly **one receive callback** is allowed to fire.
3. Granting further demand: callback parts are reassembled into **`Hello Java`**, without being mixed with the new message **`next`**.
4. The client receives `onClose` code **1000** and the server observes the client's Close reply.
5. **Do not claim "three frames produce three callbacks"**: the JDK WebSocket API makes no 1:1 guarantee between frame and callback.

Test output of the complete program:

~~~text
without_request=0
after_request_one=1
fragmented_message=Hello Java
next_message=next
close=1000
~~~

This is an **API contract verification experiment**, not a throughput benchmark program. The raw socket server part is for loopback only to precisely control wire-level bytes and is not safe enough to expose to a public network.

## 2. Four data layers to distinguish

~~~text
Application wants to send a logical text MESSAGE:
                     "Hello Java"
                           |
                  WebSocket framing
                           |
            +--------------+-------------+
            |              |             |
     TEXT FIN=0       CONT FIN=0    CONT FIN=1
         "Hel"             "lo "        "Java"
            |              |             |
            +--------------+-------------+
                           |
                       TCP bytes
             (does not preserve write/read boundaries)
                           |
                    JDK WebSocket client
                           |
      onText(ws, part, last=false or true)
                           |
         assemble parts until last=true
                           |
                  One message "Hello Java"
~~~

**TCP:** is an ordered byte stream with no awareness of the WebSocket message concept. A single `Socket.read(buffer)` may read part of a frame, multiple frames, or just a few bytes. A single read cannot be treated as a single frame.

**WebSocket frame:** contains the FIN bit, opcode, payload length, masking metadata, and payload bytes. A message can be one frame or multiple frames. Frame boundaries are a detail of RFC 6455.

**WebSocket message:** a logical text/binary unit. `Hello Java` is one message even though the server intentionally used three frames. The subsequent message `next` must be kept separate.

**Listener callback:** each time the JDK invokes `onText` or `onBinary`, it may deliver **part or all of a logical message**. Callback boundaries are not guaranteed to match frame boundaries. Rely on `boolean last` to know when a message is complete.

### 2.1. First-byte codes of the experiment

| Frame | First byte | Opcode | FIN | Payload | Meaning |
| --- | --- | --- | --- | --- | --- |
| 1 | `0x01` | Text `0x1` | 0 | `Hel` | Start first message |
| 2 | `0x00` | Continuation `0x0` | 0 | `lo ` | Same message |
| 3 | `0x80` | Continuation `0x0` | 1 | `Java` | End first message |
| 4 | `0x81` | Text `0x1` | 1 | `next` | A new message |
| 5 | `0x88` | Close `0x8` | 1 | `0x03, 0xE8` | Normal closure, code 1000 |

The experiment writes small **ASCII** payloads so the bytes are easy to inspect. If multi-byte UTF-8 data spans across frame boundaries, a standard WebSocket implementation must handle the logical text properly. Do not decode each raw UTF-8 part separately with `new String(payloadPart, UTF_8)` and concatenate them: that can corrupt split characters.

### 2.2. RFC 6455 fragmentation rules

- A fragmented message starts with a Text or Binary frame that has `FIN=0`.
- Subsequent parts use **Continuation opcode 0x0**; the final frame has `FIN=1`.
- Do not interleave another data message between fragments of an open message, unless a negotiated extension specifies otherwise.
- **Control frames** such as Ping, Pong, and Close may be interleaved between fragments, but a control frame itself **cannot be fragmented**, and its payload must not exceed **125 bytes**.
- Client-to-server frames **must be masked**, server-to-client frames **must not be masked**. Masking is not encryption and does not replace `wss://`/TLS.
- A frame may arrive across multiple TCP reads. An RFC-compliant receiver needs a length/flags-based parser and resource limits.
- Extensions may change how framing is interpreted; avoid assuming no compression if an extension has been negotiated.

**Do not parse JSON on individual wire frames**: a JSON message must be completely assembled before parsing, unless the application designs a custom streaming format with an appropriate parser.

## 3. Receive contract of `java.net.http.WebSocket`

JDK 17 provides a **WebSocket client API**, and does not provide a corresponding high-level `java.net.http.WebSocketServer`. A client is created with:

~~~java
WebSocket ws = HttpClient.newHttpClient()
        .newWebSocketBuilder()
        .buildAsync(URI.create("wss://example.test/events"), listener)
        .join();
~~~

This is an **illustrative fragment** with `listener` already initialized and `java.net.URI`, `java.net.http.*` imported, not a standalone program. In real applications, prefer asynchronous futures/callbacks over blocking a UI/event loop thread with `join()`.

`WebSocket.Listener` receives `onOpen`, `onText`, `onBinary`, `onPing`, `onPong`, `onClose`, and `onError`. Among them, **`onText` and `onBinary` both have a `last` parameter** — indicating whether the current callback ends the **logical message**.

### 3.1. Initial receive counter is 0

According to the Java 17 WebSocket API, each WebSocket has a **receive invocation counter**:

- When newly created: counter = **0**.
- `request(n)` with `n > 0`: increases the counter by up to n receive callbacks.
- Each time the JDK invokes a receive method: the counter decreases by 1.
- When the counter is 0: the JDK **does not** invoke any further throttled receive methods.
- `request(0)` or a negative number throws `IllegalArgumentException`.

The receive methods counted against demand are `onText`, `onBinary`, `onPing`, `onPong`, and **`onClose`**. `onOpen` and `onError` are **not** receive methods; `onError` may occur even when demand = 0.

~~~text
request(1) -> at most one receive callback, NOT one message.
request(2) -> at most two receive callbacks, which could be onPing + onText.
request(1) -> if onText(..., last=false), subsequent parts need more demand.
~~~

If the server sends a fragmented message and the client only grants 1 demand, the first callback may have `last=false`; the client has not yet received the complete message, **even though the server may have already sent all the bytes**.

### 3.2. Default `onOpen` automatically grants one demand

An easy way to break the experiment: the default `WebSocket.Listener.onOpen` **calls `ws.request(1)`**. If you do not override `onOpen`, the client already allows one receive callback as soon as it connects. Therefore, the program intentionally does:

~~~java
@Override
public void onOpen(WebSocket ws) {
    // Do not call request() so we can measure the initial demand = 0 state.
}
~~~

Normal applications should grant demand to start receiving; here we temporarily withhold it **solely for testing**.

### 3.3. Default `onText` also automatically grants one more demand

If you do not override `onText`, the default Listener implementation calls `ws.request(1)` and returns `null`. To prove that `request(1)` only permits **one** callback, you must override `onText` and **not request again** before `main` enables `autoDemand`.

### 3.4. `CompletionStage` does not grant additional receive credit

`onText(...)` returns a `CompletionStage<?>` or `null`. The Stage tells the WebSocket **when the callback data is no longer in use by the listener** and may be reclaimed; it **does not replace the receive counter**. According to the JDK docs, Stage completion and the number of receive callbacks are **two independent mechanisms**: returning an uncompleted future does not mean the JDK is guaranteed not to invoke the next callback while demand remains.

With `return null`, the callback signals that the data can be reclaimed immediately; therefore, you must **copy** the `CharSequence` or `ByteBuffer` data needed for longer use before returning. Do not store the `part` reference in a queue and process it after the Stage has completed.

### 3.5. Listener invocations are serialized per WebSocket

The JDK invokes Listener methods for **a single WebSocket** sequentially, non-reentrantly. A `StringBuilder` per connection can assemble parts in callback order, but:

- Do not share a static `StringBuilder` across **multiple WebSockets**.
- Do not read/write plain mutable variables from `main` while the Listener updates them on the callback thread without visibility; use `CompletableFuture`, `AtomicInteger`, or synchronization.
- Do not block a callback for several seconds to query a database; hand off the copied message to a bounded executor/queue and only grant more demand based on capacity.

## 4. Verification plan so results do not depend on sleep

The experiment has two components: **a server emitting controllable raw frames**, and **a JDK WebSocket client receiving callbacks**.

The server runs in its own thread, binds `127.0.0.1` with port 0 (OS assigns a free port), and accepts a minimal WebSocket handshake. After returning a valid `101 Switching Protocols`, the server writes each frame and calls `flush()`. Once both messages and Close are finished, the server calls `framesSent.complete(null)`.

After client `buildAsync()` completes, it waits on `framesSent` with a deadline to ensure the server has executed **the write/flush frames calls** before reading the counter. No need for `Thread.sleep(200)` and guessing.

When `ws.request(1)` is called, the Listener calls `firstCallback.complete(null)` on the first callback. Main waits on the future with a deadline, then prints the count. Then main enables `autoDemand` so `onText` grants further demand as it processes each part, and waits for `message1`, `message2`, `closeCode`, and `serverDone` with a timeout.

| Point in time | What to assert | What not to infer |
| --- | --- | --- |
| Server has flushed, client has not requested | `textInvocations=0` | The OS has not received any bytes |
| Main just called request 1 and waited for callback | `textInvocations=1` | The client has received a complete message |
| Further receive demand granted | `Hello Java` is one message | The JDK must call `onText` exactly 3 times |
| Second message completed | `next` is separate | The second TCP packet is independent |
| Close received code 1000 | Close handshake succeeded | A DB transaction/app command has committed |

`framesSent.complete` is a signal that **server-side Java code has flushed**, not a business ACK from the client. Separating this milestone is especially useful when investigating "the server says it sent, but the listener has no callback yet".

## 5. Standalone runnable Java 17+ program: `FragmentDemandExperiment.java`

**Security note:** the code below contains a **minimal raw TCP WebSocket server solely for learning RFC framing**. It does not fully validate Upgrade headers/version/extensions/origin/auth, has no TLS/WSS, has no production limits, does not handle general inbound fragmentation, and does not serve multiple clients. **Do not deploy this raw server to the Internet.** In real systems, use Jakarta WebSocket, Spring WebSocket, Jetty, Netty, or a compatible runtime.

**The client part** in the program is the JDK 17 `java.net.http.WebSocket` API. No external library dependencies, no dependency on the Internet or public echo sites.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
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
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class FragmentDemandExperiment {
    record Frame(int opcode, byte[] bytes) {}

    static String readHeaders(InputStream in) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        int last4 = 0;

        for (int b; (b = in.read()) != -1;) {
            bytes.write(b);
            last4 = (last4 << 8) | b;
            if (bytes.size() > 8192) {
                throw new IOException("Header too large");
            }
            if (last4 == 0x0d0a0d0a) {
                return bytes.toString(
                        StandardCharsets.ISO_8859_1);
            }
        }
        throw new EOFException("Missing handshake");
    }

    static String header(String all, String name)
            throws IOException {
        for (String line : all.split("\r\n")) {
            int sep = line.indexOf(':');
            if (sep > 0 &&
                    line.substring(0, sep).trim()
                            .equalsIgnoreCase(name)) {
                return line.substring(sep + 1).trim();
            }
        }
        throw new IOException("Missing header: " + name);
    }

    static void sendServerFrame(
            OutputStream out, int byte1, byte[] payload)
            throws IOException {
        if (payload.length > 125) {
            throw new IOException(
                    "Experiment only supports short frames");
        }
        out.write(byte1);
        out.write(payload.length);
        out.write(payload);
        out.flush();
    }

    static Frame readClientFrame(InputStream in)
            throws IOException {
        int first = in.read();
        int second = in.read();
        if (first < 0 || second < 0) {
            throw new EOFException("Missing frame");
        }
        if ((second & 0x80) == 0) {
            throw new IOException("Client frame unmasked");
        }

        int n = second & 0x7f;
        if (n >= 126) {
            throw new IOException("Oversized frame");
        }
        byte[] mask = in.readNBytes(4);
        byte[] data = in.readNBytes(n);
        if (mask.length != 4 || data.length != n) {
            throw new EOFException("Truncated frame");
        }
        for (int i = 0; i < n; i++) {
            data[i] ^= mask[i & 3];
        }
        return new Frame(first & 15, data);
    }

    static void serve(
            ServerSocket listener,
            CompletableFuture<Void> framesSent,
            CompletableFuture<Void> finished) {

        try (Socket socket = listener.accept()) {
            socket.setSoTimeout(5000);
            InputStream in = socket.getInputStream();
            OutputStream out = socket.getOutputStream();

            String request = readHeaders(in);
            if (!request.startsWith("GET /lab HTTP/1.1\r\n")) {
                throw new IOException("Unexpected path");
            }

            String key = header(request, "Sec-WebSocket-Key");
            String input = key
                    + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
            String accept = Base64.getEncoder().encodeToString(
                    MessageDigest.getInstance("SHA-1")
                            .digest(input.getBytes(
                                    StandardCharsets.US_ASCII)));

            String response =
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\n"
                    + "Connection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + accept
                    + "\r\n\r\n";
            out.write(response.getBytes(
                    StandardCharsets.US_ASCII));
            out.flush();

            // First message split into 3 frames.
            sendServerFrame(out, 0x01, "Hel".getBytes(
                    StandardCharsets.US_ASCII));  // TEXT FIN=0
            sendServerFrame(out, 0x00, "lo ".getBytes(
                    StandardCharsets.US_ASCII));  // CONT FIN=0
            sendServerFrame(out, 0x80, "Java".getBytes(
                    StandardCharsets.US_ASCII));  // CONT FIN=1

            // Second message is a complete text frame.
            sendServerFrame(out, 0x81, "next".getBytes(
                    StandardCharsets.US_ASCII));  // TEXT FIN=1

            // WebSocket Close frame, status=1000.
            sendServerFrame(out, 0x88,
                    new byte[]{3, (byte) 232});

            framesSent.complete(null);

            // JDK client automatically sends a masked Close reply when handling onClose.
            Frame reply = readClientFrame(in);
            if (reply.opcode() != 8) {
                throw new IOException(
                        "Expected client's Close");
            }
            finished.complete(null);
        } catch (Throwable t) {
            framesSent.completeExceptionally(t);
            finished.completeExceptionally(t);
        }
    }

    static class ListenerImpl implements WebSocket.Listener {
        final AtomicInteger textInvocations =
                new AtomicInteger();
        final AtomicBoolean autoDemand =
                new AtomicBoolean(false);

        final CompletableFuture<Void> firstCallback =
                new CompletableFuture<>();
        final CompletableFuture<String> message1 =
                new CompletableFuture<>();
        final CompletableFuture<String> message2 =
                new CompletableFuture<>();
        final CompletableFuture<Integer> closeCode =
                new CompletableFuture<>();

        final StringBuilder text = new StringBuilder();
        int messagesDone;

        @Override
        public void onOpen(WebSocket ws) {
            // No request: default onOpen would automatically call request(1).
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket ws, CharSequence part, boolean last) {
            int current = textInvocations.incrementAndGet();

            text.append(part); // Copy before callback completes.
            if (last) {
                String message = text.toString();
                text.setLength(0); // Reset between two messages.

                if (messagesDone++ == 0) {
                    message1.complete(message);
                } else {
                    message2.complete(message);
                }
            }

            if (current == 1) {
                firstCallback.complete(null);
            }
            if (autoDemand.get()) {
                ws.request(1);
            }
            return null;
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket ws, int code, String reason) {
            closeCode.complete(code);
            return null;
        }

        @Override
        public void onError(WebSocket ws, Throwable error) {
            firstCallback.completeExceptionally(error);
            message1.completeExceptionally(error);
            message2.completeExceptionally(error);
            closeCode.completeExceptionally(error);
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 1,
                InetAddress.getByName("127.0.0.1"))) {

            CompletableFuture<Void> framesSent =
                    new CompletableFuture<>();
            CompletableFuture<Void> serverDone =
                    new CompletableFuture<>();

            Thread server = new Thread(
                    () -> serve(listener, framesSent, serverDone),
                    "one-shot-websocket");
            server.setDaemon(true);
            server.start();

            ListenerImpl callbacks = new ListenerImpl();
            String target = "ws://127.0.0.1:"
                    + listener.getLocalPort() + "/lab";

            WebSocket ws = HttpClient.newHttpClient()
                    .newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .buildAsync(URI.create(target), callbacks)
                    .get(5, TimeUnit.SECONDS);

            // Server has sent/flushed, but Listener has no demand yet.
            framesSent.get(5, TimeUnit.SECONDS);
            System.out.println("without_request="
                    + callbacks.textInvocations.get());

            ws.request(1);
            callbacks.firstCallback.get(5, TimeUnit.SECONDS);
            System.out.println("after_request_one="
                    + callbacks.textInvocations.get());

            // After measurement, allow Listener to continue receiving.
            callbacks.autoDemand.set(true);
            ws.request(1);

            System.out.println("fragmented_message="
                    + callbacks.message1.get(
                            5, TimeUnit.SECONDS));
            System.out.println("next_message="
                    + callbacks.message2.get(
                            5, TimeUnit.SECONDS));
            System.out.println("close="
                    + callbacks.closeCode.get(
                            5, TimeUnit.SECONDS));

            serverDone.get(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Save the file matching the class name, compile, and run with JDK 17+:

~~~bash
javac -encoding UTF-8 FragmentDemandExperiment.java
java FragmentDemandExperiment
~~~

**Stdout directly verified with Java 17 JShell:**

~~~text
without_request=0
after_request_one=1
fragmented_message=Hello Java
next_message=next
close=1000
~~~

### 5.1. Meaning of each line

**`without_request=0`:** the server has completed sending/flushing all frames and Close; the client's Listener has not granted receive demand yet. No `onText` callback is fired. **It cannot be inferred** that the network has not received the bytes; the data may already be in TCP buffers/JDK internal buffers.

**`after_request_one=1`:** main called `ws.request(1)` once, the Listener recorded the first callback and did not request more while `autoDemand=false`. This measures **one receive invocation**, not "one text message" or "one frame".

**`fragmented_message=Hello Java`:** callback parts are assembled until `last=true`. Because the server sent `Hel` + `lo ` + `Java` as **one logical text message**, the client must reconstruct the exact content.

**`next_message=next`:** after the first message completes, the Listener resets `StringBuilder`. The subsequent text message is not accidentally appended to the previous one.

**`close=1000`:** the Listener receives Close code 1000 when receive demand continues. The server also checks for a masked Close reply from the client, then completes `serverDone`.

### 5.2. Determinism and limitations

The code does not rely on `Thread.sleep` to guess when the server finishes sending. `framesSent` completes when the server has flushed; `firstCallback` is the milestone for the first callback; all futures use `get(..., TimeUnit.SECONDS)` to fail fast. That does not turn the network/OS into a real-time system, but it eliminates sleep-dependent assertions and naive scheduler timing.

The demo **does not print the callback count for message1** because that count is not fixed to the number of frames by the RFC/JDK API. If you want to measure it for learning, add logging in `onText` for `last` and `part.length()` — treat the output as **non-fixed diagnostics**, and never write a test asserting `onText` count = 3.

### 5.3. Why does the server only use loopback?

The raw `ServerSocket` server is not a standard WebSocket server framework. It only reads minimal HTTP Upgrade headers, computes `Sec-WebSocket-Accept` with SHA-1 per the RFC 6455 formula, emits small unmasked frames (correct for server → client), and reads one masked Close frame (correct for client → server). It **does not** handle full HTTP headers/Origin/session/TLS, extended length/inbound fragmentation, UTF-8 validation, Ping/Pong, compression, max message size, multiple clients, or abuse protection. Do not use the demo as an Internet endpoint.

## 6. Variant experiment: observing `last`

Replace the counter increment line in `onText`:

~~~java
int current = textInvocations.incrementAndGet();
System.err.println(
        "callback=" + current +
        " chars=" + part.length() +
        " last=" + last);
~~~

This is an **illustrative patch**; do not add a second increment. The output may show `last=false` on some parts and `last=true` at the message boundary. However, there is no guarantee that callback counts/char lengths correspond one-to-one with each frame sent by the server, even with identical wire input.

When verifying message correctness, always ask:

- Is there a final callback for every logical message (`last=true`)?
- Is the buffer reset after a complete message?
- Are messages from two sessions mixed?
- Are text messages split across multiple callbacks handled?
- Are there a max message length and timeout if the peer never finishes fragments?

A parser should not call `JSON.parse` or decode business payloads inside `onText(last=false)` if the input does not yet form a complete JSON document. A custom-designed streaming parser can be used, but JSON/message boundaries must be clearly distinguished.

## 7. Binary messages: using `onBinary` and proper ByteBuffer ownership

The same concept applies to binary. If the server sends:

~~~text
BINARY FIN=0 bytes [01 02]
CONT   FIN=1 bytes [03 04]
=> one logical binary message [01 02 03 04]
~~~

The JDK client calls `onBinary(WebSocket, ByteBuffer data, boolean last)` to deliver parts. The data lies from `data.position()` to `data.limit()`, not always the entire backing array. Do not blindly use `data.array()` because a direct/read-only ByteBuffer may not have an accessible backing array.

An illustrative handler (not standalone):

~~~java
final ByteArrayOutputStream assembled = new ByteArrayOutputStream();

@Override
public CompletionStage<?> onBinary(
        WebSocket ws, ByteBuffer part, boolean last) {

    byte[] copy = new byte[part.remaining()];
    part.get(copy); // Copy before callback completes.
    assembled.writeBytes(copy);

    if (assembled.size() > MAX_BINARY_BYTES) {
        ws.abort(); // Illustrates policy when exceeding limit.
        return null;
    }
    if (last) {
        byte[] whole = assembled.toByteArray();
        assembled.reset();
        handleCompleteBinary(whole);
    }

    ws.request(1);
    return null;
}
~~~

The snippet above requires `MAX_BINARY_BYTES`, `handleCompleteBinary`, and appropriate imports defined by the application. `abort` is an abrupt client close, not a business response. In production, choose an appropriate Close/error policy, copy safely, and bound queued bytes.

### 7.1. UTF-8 Unicode split across frames

A text frame may end in the middle of a multi-byte UTF-8 sequence. If you write a raw server parser and decode each frame into a separate `String`, it is very easy to produce `` characters and assemble incorrectly. `java.net.http.WebSocket` decodes valid text and delivers a `CharSequence` with valid UTF-16 per the API. The experiment currently tests ASCII for readable stdout; extend testing with a message containing `Tiếng Việt 😊` whose raw bytes are split at arbitrary positions, and compare the complete logical message. Never assume each Unicode code point will fit neatly inside a single `onText` callback.

## 8. Control frames: Ping/Pong also consume receive demand

A fragmented message may have a **Ping** in the middle:

~~~text
TEXT FIN=0 "Hel"
PING FIN=1 "x"
CONT FIN=0 "lo "
CONT FIN=1 "Java"
~~~

`onPing` is also among the receive methods that count against demand. If you grant `request(2)`, you may receive one `onText` and one `onPing`, **not necessarily** two `onText` calls. The main demo server intentionally does not send Ping to keep the single-demand measurement simple.

Example adding `onPing` to the listener (fragment):

~~~java
@Override
public CompletionStage<?> onPing(WebSocket ws, ByteBuffer data) {
    // Java WebSocket implementation automatically replies with Pong per the API contract.
    ws.request(1);
    return null;
}
~~~

According to the Java 17 Listener API, the WebSocket implementation automatically sends a Pong in response to a Ping per the rules; you usually do not need to call `sendPong` manually to reply to a Ping. You must copy the ByteBuffer if using it after the Stage completes.

**`onClose` also consumes demand**. When pausing receives, if the peer sends Close, the `onClose` callback may not be invoked until demand is granted. Conversely, `onError` may be invoked without demand, because it is an error/lifecycle callback rather than a receive callback.

### 8.1. When `request(1)` "does not see" `onText`

Do not conclude the server did not send without observing:

- Has `onOpen` run yet?
- Did the Listener grant receive demand or accidentally use the default `onOpen`?
- Did Ping/Pong/Close consume demand before text?
- Did `onError` occur? Was the connection closed/aborted?
- Has the server sent/flushed data? Did a proxy forward Upgrade/frames properly?
- Is a text message half-delivered with `last=false` while the client has not requested further?

Measure multiple signals before adjusting timeouts or writing a `request(Long.MAX_VALUE)` loop.

## 9. Receive demand differs from end-to-end backpressure

**`request(n)` throttles the number of listener receive callback invocations**, not directly "the server is only allowed to send n frames". The server may have already sent thousands of bytes, the JDK may buffer them, the TCP window may change; the consumer may also be slow on a downstream worker queue.

~~~text
Producer server
      |
   TCP / kernel buffers
      |
   JDK WebSocket internal state
      |
   request(n) -> callbacks (onText/onBinary/...)
      |
   assembler with message length limit
      |
   bounded processing queue
      |
   DB, UI, parser, or business worker
~~~

If the callback pushes unbounded messages into an `ArrayList`, having called `request(1)` earlier will not help when the callback **always** calls a new `request(1)` without waiting for the consumer to process.

A good receive policy:

1. **Only receive when downstream has capacity** (queue is not full, workers have slots).
2. **Copy the message part** into a buffer with clear ownership before returning/completing the Stage.
3. Have **max assembled bytes/characters** and a deadline if a message is fragmented indefinitely.
4. When a message completes, dispatch it to a **bounded queue** per schema; only grant further demand when enough capacity is available.
5. If the queue is full, **pause granting `request`**, coalesce non-essential updates, or close the connection per policy. Do not wait indefinitely and do not silently drop critical data.
6. If the sender needs to slow down according to **business semantics**, design an application-level credit/ACK window; the WebSocket RFC does not define this automatically.

Example application protocol with credit:

~~~json
{"type":"subscribe","channel":"prices","credit":10}
{"type":"ack","lastSeenSequence":101,"moreCredit":5}
~~~

This is an **illustrative application-defined schema**, not a mandatory WebSocket format. The server must honor credit, and the client must have recovery/resubscribe logic if the connection drops.

### 9.1. Stage, request, and producer credit are three different things

| Mechanism | Meaning | Does not guarantee |
| --- | --- | --- |
| `CompletionStage` from `onText` | Callback data is done being used and can be reclaimed | Additional receive invocations |
| `ws.request(n)` | Permits n receive method invocations | Peer/server stops sending immediately |
| Application `credit/ack` | Rules designed by both sides to throttle business flow | Automatic TCP packet reliability/exactly-once transactions |
| TCP receive window | Transport-layer flow control | Parser/DB worker has enough capacity |

Do not return a never-completing `CompletableFuture` and assume you have end-to-end backpressure. If demand remains, callbacks may continue per the JDK contract; at the same time, you may cause the implementation to retain buffers unnecessarily.

### 9.2. Timeouts and cleanup

If demand is missing, `message1.get()` can wait forever even after the server has finished sending. Use `get(5, TimeUnit.SECONDS)` in tests, monitor `onError`, complete futures exceptionally, and have a cleanup/`abort` path when forced to cancel.

For production, define an idle timeout, a deadline for incomplete fragmented messages, and a max processing lag. Do not keep a WebSocket listener open indefinitely in a "paused" state without a resume or close mechanism.

## 10. Send fragmentation in Java is a different story

To **have the client send** a text message in two parts:

~~~java
ws.sendText("Hel", false)
  .thenCompose(ready -> ready.sendText("lo Java", true));
~~~

This is a fragment where `ws` is already a connected WebSocket. The `last=false` parameter marks a partial message, and `last=true` ends the message. Call `thenCompose` to serialize sends; do not overlap two text send operations and hope for natural ordering.

The `CompletableFuture` from `sendText` completes for the client API's **send operation**; it does not mean the peer has saved to a database or the server application has issued a business ACK. For side effects, design separate requestId/ACK/idempotency.

When receiving, the JDK already handles WebSocket frame parsing; you **do not need to read raw opcodes yourself** inside `onText`. Just assemble callback data until `last=true` and parse the business message.

## 11. Common errors and how to diagnose them

| Symptom | Possible cause | Remedy |
| --- | --- | --- |
| Only receives the first callback | `onText` does not request more, counter hits 0 | Call `request(1)` based on capacity |
| Receives no callback even though server sent | Overrode `onOpen` without requesting | Check demand and intentional pause |
| Test "3 frames must be 3 callbacks" fails | Confusing frame/callback boundaries | Assert logical message and `last` flag |
| JSON parser fails on `last=false` | Parsing incomplete data | Assemble parts, bound size, parse when `last=true` |
| Message2 contains data from message1 | Forgot to reset assembler | `setLength(0)`/reset after `last` |
| Unicode arrives corrupted | Decoding UTF-8 per raw frame | Decode complete message, use WebSocket API |
| `ByteBuffer.array()` throws exception | Buffer has no accessible backing array | Copy using `remaining` and `get` |
| Application stops receiving Close | No receive demand left | Add liveness/deadline/grant demand/abort |
| `onError` occurs when counter is 0 | `onError` is not controlled by demand | Distinguish lifecycle from receive callbacks |
| `request(1)` receives Ping instead of text | Control callbacks also decrement counter | Have an `onPing` policy and request again |
| Handler queue grows unboundedly | Requesting immediately despite downstream overload | Bounded queue + credit/admission |
| OOM when receiving oversized message | Unbounded `StringBuilder`/`ByteArrayOutputStream` | Max message bytes and timeout |
| Async task reads `CharSequence` after callback | Data already reclaimed | Copy before Stage completes |
| `sleep(100)` test occasionally fails | Time-based synchronization | Futures/latches + timeout |
| Client loses response despite successful send future | No application ACK | RequestId/ACK/transaction status |
| Using demo server publicly | Lacks RFC/TLS/auth/limits | Use a standard server framework |

## 12. Extending the test suite by invariant

**Case A — Unfragmented single text message.** Server sends TEXT FIN=1 "hi"; client must complete one message "hi". Do not assert a single TCP read.

**Case B — Three-fragment text.** Server sends TEXT FIN=0 "Hel", CONT FIN=0 "lo ", CONT FIN=1 "Java"; client must assemble "Hello Java", and not dispatch before `last=true`.

**Case C — Two consecutive messages.** After message1, server sends TEXT FIN=1 "next"; client must produce a separate message2, not "Hello Javanext".

**Case D — Zero demand.** Override `onOpen` and `onText`; server has flushed, client has not requested; the callback counter must not increase. When `onError` occurs, a different rule applies.

**Case E — One receive credit.** Call `request(1)` and wait for the first callback; no second receive callback occurs if the listener does not request again.

**Case F — Resume.** After the first callback and pause, resume requesting; the entire message and subsequent events are still processed per contract.

**Case G — Ping between fragments.** Send a Ping between Text/Continuation; account for `onPing` also consuming demand and verify the frame does not corrupt the message.

**Case H — Fragmented binary.** Server sends binary FIN=0 + continuation FIN=1; client assembles bytes using `position/limit`, not treating them as UTF-8.

**Case I — Split UTF-8.** Send a multi-byte Unicode character across two frames and verify the logical text is intact. For the current demo server, raw payload assembly and RFC validation would need to be added.

**Case J — Size exceeds limit.** Peer sends a very large fragmented message or never sets `last=true`. Client must not accumulate unboundedly and must abort/close per policy.

**Case K — Cancel while receive is paused.** Have a deadline to exit; `abort` cleanup when graceful close is impossible, completing futures exceptionally rather than waiting forever.

**Case L — Two concurrent WebSockets.** Each session needs its own message assembler without mixing parts; use atomic/concurrency-aware metrics.

**Case M — Protocol-invalid frames.** Continuation without an initial Text/Binary, unmasked client frame, fragmented control frame: test protocol errors through a proper compliant test harness, not the demo server for all RFC edge cases.

**Case N — Slow business-side behavior.** When the queue is full, the consumer must reduce receive demand, bound memory, and have a policy for prolonged slowness.

**Case O — Close code and business success.** Receiving Close 1000 does not prove a prior command committed. Test business ACK separately.

**Case P — Testing across JDK versions.** Keep assertions on messages, `last`, and demand; do not hard-code callback count per frame across all builds.

## 13. Exercises with solutions

### Exercise 1 — Is one callback for three frames wrong?

The server sends a text message fragmented into three frames. The client only receives `onText(data="Hello Java", last=true)` once.

**Answer:** this cannot be called wrong. The API does not guarantee the callback count equals the frame count; the logical message and `last` are what the application relies on.

### Exercise 2 — Client receives automatically even without calling `request` in code

You do not override `onOpen` on the Listener. When the server sends, the client calls `onText` once.

**Answer:** the default `onOpen` called `webSocket.request(1)`. To test zero demand, you must override it.

### Exercise 3 — Only receives `onText("Hel", false)`

After the first callback, the complete-message future never completes even though the server already sent the continuation frames.

**Answer:** the receiver may have run out of demand. Call `request(1)` again and observe the callbacks/`last`; do not jump to concluding the server did not send.

### Exercise 4 — Requested two callbacks but received Ping then one text part

Is that a violation because the full message was not received?

**Answer:** no. Ping consumes receive demand just like `onText`, and a single `onText` part may not yet be a complete message; you must request more per policy.

### Exercise 5 — Returning a slow future to stop receiving

You call `request(100)` and return an uncompleted `CompletableFuture` for every `onText`. Is the JDK guaranteed not to call `onText` again?

**Answer:** no. `CompletionStage` controls data lifetime, not the receive callback counter. You must limit demand and the queue.

### Exercise 6 — Parsing JSON on every part

The server sends `{"type":"ping"}` in multiple frames, and the client parses when `last=false`.

**Answer:** wrong message boundary. Assemble parts and parse when complete, with size/time limits.

### Exercise 7 — Keeping a `CharSequence` in a queue

The callback returns `null` but stores the `data` reference for a worker to use later.

**Answer:** unsafe under the ownership contract. Copy into an immutable `String`/bytes before returning a completed Stage.

### Exercise 8 — Can Close wait for demand?

The server has sent Close, and the client pauses receiving and waits for `onClose` forever.

**Answer:** `onClose` is a throttled receive callback, so it may not be invoked when demand is 0. You need a resume/timeout/abort policy.

### Exercise 9 — Does 0 mean stop requesting?

The client calls `ws.request(0)` to pause.

**Answer:** wrong: `request(n)` requires positive n, and 0 throws `IllegalArgumentException`. To pause, **simply do not grant more demand** after previously granted credits are consumed.

### Exercise 10 — Two threads sharing a StringBuilder

Two WebSocket sessions are attached to the same listener instance that has a shared buffer.

**Answer:** messages can mix and race; the JDK serializes callbacks **within a single WebSocket**, and does not promise serialization across two WebSockets. Use per-session state or a concurrency-safe map.

### Exercise 11 — Client stops requesting so server definitely stops sending

The server still writes bytes after the client has no demand.

**Answer:** this can be normal. `request` controls callbacks, not application credit sent to the server. TCP flow control only takes effect after buffers/receive window fill up; an end-to-end protocol is needed if you want the server to stop based on capacity.

### Exercise 12 — Binary misread

`onBinary` receives a direct `ByteBuffer`, and the code calls `array()` then parses as text.

**Answer:** `array()` may not be supported; binary has no UTF-8 guarantee. Copy `remaining` bytes and process according to the binary message schema.

## 14. Lab completion checklist

- [ ] Read and distinguished TCP byte stream, WebSocket frame, logical message, and Listener callback?
- [ ] Understood the meaning of FIN/opcode for Text and Continuation frames?
- [ ] Known that Ping/Pong/Close can be interleaved between data fragments?
- [ ] Known that masking differs between client → server and server → client?
- [ ] Overrode `onOpen` when needing to verify **zero demand**?
- [ ] Overrode `onText` when needing to control **whether to request further**?
- [ ] Proved `request(1)` permits one receive invocation, not one message?
- [ ] Assembled text parts until `last=true` instead of parsing per callback?
- [ ] Reset the buffer after a complete message?
- [ ] Verified message1 `Hello Java` and message2 `next` do not mix?
- [ ] Observed Close code 1000 and understood it differs from a business ACK?
- [ ] Distinguished `onError` (does not require demand) and `onClose` (requires demand)?
- [ ] Used `CompletableFuture` with a deadline instead of sleep for timing?
- [ ] Understood that the returned `CompletionStage` does not replace `request(n)`?
- [ ] Handled data ownership of `CharSequence`/`ByteBuffer` when returning the Stage?
- [ ] Set message size/time limits and a bounded consumer queue in production design?
- [ ] Understood that receive demand does not directly stop the remote server from sending bytes?
- [ ] Understood that default `onOpen` and default `onText` automatically request one callback?
- [ ] Noted that the test does not promise callback count = wire frame count?
- [ ] Understood that the raw demo server must only run on loopback, not in production?

**Conclusion:** The experiment proves that a WebSocket text message can be split into multiple **wire frames**, yet applications should process at the **`last=true` message boundary**. On JDK 17, `request(n)` grants a number of **receive callback invocations**; the counter starts at 0, while the default `onOpen` automatically calls `request(1)` unless overridden. The results `without_request=0`, `after_request_one=1`, `fragmented_message=Hello Java`, and `next_message=next` show both controlled callback delivery and accurate message reassembly. For real products, combine demand, bounded buffers, timeouts, and an application protocol; do not infer one callback equals one frame or use `request` as a substitute for full backpressure.

## 15. References

- **RFC 6455 — The WebSocket Protocol, Section 5.4:** https://www.rfc-editor.org/rfc/rfc6455
- **Oracle Java 17 — WebSocket, request(long n):** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html
- **Oracle Java 17 — WebSocket.Listener:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html
- **Oracle Java 17 — WebSocket.Builder:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html
- **Oracle Java 17 — HttpClient:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **Oracle Java 17 — CompletableFuture:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html

The RFC document defines wire framing, while the Oracle API defines receive demand/callbacks/ownership. The test intentionally verifies what is **guaranteed by the API**, without imposing the callback count of one JDK implementation onto all other versions.