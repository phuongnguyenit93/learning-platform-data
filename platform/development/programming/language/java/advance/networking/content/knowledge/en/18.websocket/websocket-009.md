# Ownership and Access Rules for CharSequence and ByteBuffer Before WebSocket Send Completion in Java 17

In the **WebSocket** module of Java Advance — networking, sending a message via **java.net.http.WebSocket** is not a synchronous operation that completes immediately at the method call site. Both common methods **sendText(CharSequence data, boolean last)** and **sendBinary(ByteBuffer data, boolean last)** initiate an **asynchronous** send operation and return a **CompletableFuture<WebSocket>**. The Java WebSocket implementation may still be accessing the data you provided **after sendText/sendBinary has returned**.

Therefore, the critical question is not just "how to send a string or bytes", but **who owns read/write access to the payload during the period before the send completes**. If a thread mutates a **StringBuilder** while the WebSocket is still sending, the transmitted content can be corrupted or suffer a data race. If the application calls **flip/clear/put/get/reads position** on a **ByteBuffer** currently in use by sendBinary, it violates the Java 17 contract; the sent data, position, and errors may not behave as you expect.

According to the **Java SE 17 Javadoc**:

- **sendText(data, last)**: **The CharSequence must not be modified** until the **CompletableFuture** returned by the method **has completed**.
- **sendBinary(data, last)**: bytes are taken from the region **position to limit**. **The ByteBuffer must not be accessed** before that CompletableFuture completes; when the future **completes normally**, the buffer **has no remaining bytes**.
- **sendPing(ByteBuffer)** and **sendPong(ByteBuffer)** also have the rule of not accessing the buffer until the future completes; the maximum control payload is 125 bytes.
- **A future completing normally** means the WebSocket send operation succeeded according to the API, **not proof** that the receiving application has read, parsed, or processed the message.

This lesson explains the exact Java 17 contract, how to distinguish an **immutable String** from a **mutable StringBuilder/CharBuffer**, **data independence** versus **ByteBuffer views sharing storage**, the **snapshot/ownership transfer** principle, how to chain sends and control backpressure, failure/cancellation, along with **two runnable programs** tested on the JDK with the **--release 17** compilation option. One program actually sends data over a localhost WebSocket; the other proves why **slice/duplicate/asReadOnlyBuffer are not deep copies**.

## 1. The Nature of a WebSocket Send

A Java 17 WebSocket client is created like this:

~~~java
WebSocket webSocket = HttpClient.newHttpClient()
        .newWebSocketBuilder()
        .buildAsync(uri, listener)
        .join();
~~~

This is an **illustrative snippet**, assuming uri is a valid **ws:// or wss://** URI and listener is a configured **WebSocket.Listener**. **buildAsync** is the connection opening and handshake process; **sendText/sendBinary** are only performed after the WebSocket is ready.

When the application calls:

~~~java
CompletableFuture<WebSocket> sent = webSocket.sendText("HELLO", true);
~~~

the method **returns a CompletableFuture immediately**, while the send completion occurs when the future completes. A successful call **does not mean** you can immediately reuse all the data passed in.

~~~text
APPLICATION THREAD                   WEBSOCKET SEND OPERATION
      |
      | create payload
      | sendText(data, true) --------> initiate asynchronous send
      |    |
      | receive CompletableFuture      |
      |    |                           | may read data later
      |    |                           | handle framing / send
      |    |                           |
      |    +---- future not done ----->| still pending
      |    |                           |
      |    | do not modify the data    |
      |    | being sent                |
      |    |                           |
      |    +---- future completed <----+
      |          |
      |          +-- success: send operation succeeded
      |          +-- failure: check exception/cancellation
      |
      +-- can release/reuse
          data according to each API's rules
~~~

**A created future is not an automatic lock.** Java does not automatically lock the application's StringBuilder or byte array; the caller is responsible for ensuring consistent access rights. There is no general requirement that the WebSocket provider must **deep-copy** the payload at the moment you call send.

### Things to Distinguish

| Event | What is known | What cannot be inferred |
|---|---|---|
| **sendText/sendBinary returns CompletableFuture** | The operation has been initiated or has already returned a failed future | Data has been fully read, fully sent, or reached the server |
| **future.isDone() == false** | The operation has not completed according to the future | Must not modify the CharSequence or access the ByteBuffer being sent |
| **future completes normally** | The send operation succeeded according to the WebSocket API | The receiving application has processed and committed it |
| **future completes exceptionally** | The send operation failed | The ByteBuffer still has its original position or the message never reached the peer |
| **sendClose completes** | Sent Close according to the contract | All application-level business acknowledgments have been received |

A successful message can still be lost at the business layer if the peer crashes after receiving the bytes; if the protocol needs processing guarantees, add **application ACK**, request ID, timeout, and idempotency. **WebSocket send completion is not an application delivery receipt**.

## 2. Specific Rules for sendText(CharSequence, boolean)

Java 17 signature:

~~~java
CompletableFuture<WebSocket> sendText(CharSequence data, boolean last);
~~~

The **data** parameter is a **CharSequence**, an **interface**, so at runtime it can receive:

- **String**: immutable; a String literal or a constructed String is the simplest choice to keep content unchanged.
- **StringBuilder**: mutable; **do not call append/insert/delete/setCharAt/replace/setLength** on the object being sent until the future completes.
- **StringBuffer**: mutable and some operations are synchronized, but that **does not grant permission to mutate while a send is pending**.
- **CharBuffer**: can be a view over a char[] or a shared memory region; do not modify the content or the backing storage of the CharBuffer being sent.
- **Custom CharSequences**: may read data that changes over time; if immutability cannot be guaranteed, create an independent snapshot.

**The contract of sendText is "do not modify the CharSequence until the future completes"**, not "just do not modify it on the line calling sendText". A call may return before the client has actually finished reading all characters.

### Dangerous pattern: modifying StringBuilder too early

~~~java
StringBuilder builder = new StringBuilder("ORDER-001");
CompletableFuture<WebSocket> pending =
        webSocket.sendText(builder, true);

builder.replace(0, builder.length(), "ORDER-999");
// WRONG: builder is the CharSequence currently being sent.
~~~

This is an **anti-pattern**, not a standalone program, and **must not be used to test your luck in production**. Sometimes running on localhost still shows ORDER-001 because the provider read it very quickly; under network congestion or different thread scheduling, the outcome can differ. **Do not rely on accidental success to prove safety**.

### Correct approach A: use an immutable String

~~~java
StringBuilder draft = new StringBuilder("ORDER-001");
String stablePayload = draft.toString();

CompletableFuture<WebSocket> pending =
        webSocket.sendText(stablePayload, true);

// Safe for stablePayload:
// draft is now a different object, not the CharSequence that was passed.
draft.replace(0, draft.length(), "ORDER-999");

pending.join();
~~~

Here **sendText receives stablePayload (String)**, not draft. String is immutable; draft can be modified without changing the content of stablePayload. When using **StringBuilder.toString()**, creating the String snapshot must finish **before modifying draft**, and synchronization is still required if multiple threads are concurrently modifying draft during the snapshot.

### Correct approach B: retain builder ownership until completion

~~~java
StringBuilder builder = new StringBuilder("ORDER-001");
CompletableFuture<WebSocket> pending =
        webSocket.sendText(builder, true);

pending.whenComplete((socket, error) -> {
    // Only here can builder be considered no longer held by the send.
    if (error != null) {
        reportFailure(error);
    }
    builder.setLength(0);
});
~~~

The snippet above **is for illustration only**, with reportFailure defined by the application; it is not a standalone runnable file. In practice, ensure no other thread modifies builder before whenComplete is triggered and do not clear/recycle the object if another callback still uses it. If the future fails, you must handle the possibility that the message was not sent or was partially sent; if you want to retry, rebuild the payload from an **immutable data source**, not inferred from external state.

**Do not use a shared StringBuilder variable** for all requests on the same connection. A shared builder appended/cleared by an event loop can accidentally alter the content of a still-pending send. Use a **per-message immutable snapshot** or a **per-message ownership token**.

## 3. CharBuffer, char[], and Read-Only Views Do Not Guarantee Content Immutability

**CharSequence** is not synonymous with String. For example:

~~~java
char[] raw = {'O', 'K'};
CharBuffer view = CharBuffer.wrap(raw).asReadOnlyBuffer();

raw[0] = 'N';
// view is read-only for a writer using view,
// but still sees the value 'N' because the backing array was modified.
~~~

**CharBuffer.asReadOnlyBuffer()** protects against calling **put(...) directly on the view**, not against an external alias modifying the backing array. **A read-only view is not an immutable snapshot**.

Rules:

1. If you receive a CharSequence input and **do not know whether the source is mutable**, create a **String snapshot** before sending, with size limits and valid encoding.
2. If the CharSequence wraps a char[] or a shared memory region, **do not let another thread modify the backing array** while the send is pending.
3. If using CharBuffer.asReadOnlyBuffer(), you must still respect ownership of the backing storage, because the source buffer or external array can modify the data.
4. If the data is updated continuously and you need to send a consistent "snapshot", take the snapshot inside a critical section or use an appropriate immutable structure.
5. **StringBuilder is not thread-safe**; do not read a snapshot concurrently with an unsynchronized writer and expect the snapshot to be self-consistent.

### UTF-16 and text fragmentation

Java **CharSequence** contains **UTF-16 code units**; WebSocket text on the wire uses valid UTF-8. The Java 17 Javadoc states that if the input is a **malformed UTF-16 sequence**, the sendText operation **fails with an IOException in the future**. For example, assembling fragments or slicing content must avoid creating broken surrogate pairs.

**Do not slice text by an arbitrary number of Java chars** and assume Unicode boundaries are always valid: an emoji can consist of two UTF-16 code units, and visible grapheme clusters can consist of multiple code points. Choose fragment boundaries according to the WebSocket/UTF-16 contract and test with Vietnamese, emojis, combining marks, and international data.

## 4. Crucial Rules for sendBinary(ByteBuffer, boolean)

Signature:

~~~java
CompletableFuture<WebSocket> sendBinary(ByteBuffer data, boolean last);
~~~

The Java 17 Javadoc clearly states:

1. Bytes sent come from the **current region of data: [position, limit)**.
2. **The data ByteBuffer must not be accessed** until **the CompletableFuture returned by sendBinary has completed**. This is a stronger rule than merely "do not modify the bytes".
3. When the future **completes normally**, **data.remaining() == 0**.
4. If the future **fails**, do not assume the buffer still has its original position, how many bytes were consumed, or that it can be reused directly for a retry; handle the error and build a new payload if the business logic requires it.

**Why does "must not be accessed" matter?** A ByteBuffer contains **content + position + limit + mark**. The implementation may transfer bytes by updating the position during the send. If the caller concurrently calls **get/put/flip/clear/compact/rewind/position/limit/remaining**, you can cause a race on the buffer's state or alter the data region to be sent.

### The position/limit rule

~~~text
ByteBuffer capacity = 8
          position=2            limit=6
               |                   |
index:  0  1  [2  3  4  5]  6  7
sendBinary will send the bytes at [position, limit)
= indexes 2, 3, 4, 5

after successful completion:
    remaining() == 0
    position == limit
~~~

This is a logical model, not a promise that bytes outside the sent range will be erased or that the buffer will be automatically cleared. **sendBinary is not a "send entire capacity" operation**; the sent region depends on position/limit at the time of the call and the immobility contract throughout the pending operation.

### Dangerous pattern: calling flip/clear too early

~~~java
ByteBuffer buffer = ByteBuffer.wrap(new byte[] {1, 2, 3, 4});
CompletableFuture<WebSocket> pending =
        webSocket.sendBinary(buffer, true);

buffer.clear(); // WRONG: still pending, must not access buffer.
buffer.put((byte) 99); // WRONG: overwriting content before completion.
~~~

It is also wrong to even call **buffer.remaining()** for logging while pending, because Java 17 states **the buffer must not be accessed**. To track progress, save **the expected size into a separate numeric variable before sending**, or use metrics at the operation/future level after completion.

### Correct approach A: wait for send success before reusing

~~~java
ByteBuffer buffer = ByteBuffer.wrap(new byte[] {1, 2, 3, 4});
CompletableFuture<WebSocket> pending =
        webSocket.sendBinary(buffer, true);

pending.join();
int remaining = buffer.remaining(); // 0 after normal completion.
buffer.clear();                     // Now it is safe to reuse.
~~~

This is an illustrative snippet; you need to handle CompletionException on error and ensure no other alias modifies the storage while pending. **Do not assume buffer.clear() erases the bytes in the backing storage**: clear only resets position/limit; the old data may still remain in the array/direct memory until overwritten or freed.

### Correct approach B: copy bytes into a buffer owned by the send

~~~java
byte[] mutableSource = {1, 2, 3, 4};
byte[] ownedBytes = mutableSource.clone();
ByteBuffer ownedBuffer = ByteBuffer.wrap(ownedBytes);

CompletableFuture<WebSocket> pending =
        webSocket.sendBinary(ownedBuffer, true);

// Valid: modifying the original array, because WebSocket is using the cloned array.
mutableSource[0] = 99;

// DO NOT read or modify ownedBuffer or ownedBytes before completion.
pending.join();
assert ownedBuffer.remaining() == 0;
~~~

In this pattern **mutableSource** and **ownedBytes** are **two independent arrays**. You just need to ensure the application does not touch ownedBytes during the pending operation. **ByteBuffer.wrap(ownedBytes)** itself **does not copy ownedBytes again**; it is a view over the cloned array. This pattern creates an independent snapshot from the original array.

### Correct approach C: copy the remaining part from a source buffer

~~~java
ByteBuffer source = obtainSourceBuffer();
ByteBuffer snapshot = ByteBuffer.allocate(source.remaining());
snapshot.put(source.duplicate());
snapshot.flip();

CompletableFuture<WebSocket> pending =
        webSocket.sendBinary(snapshot, true);

// Caller may modify source, but must not modify snapshot while pending.
pending.join();
~~~

This is an illustrative snippet, with obtainSourceBuffer() defined by the application. **source.duplicate() is used before sending** to read the remaining region without changing source.position; **snapshot.allocate + put** creates an **independent** byte storage region. **source** must be stable **during the copy**: if another thread is writing to source, the copy can also be inconsistent. For a thread-safe snapshot, synchronize the producer/consumer or use immutable data/queue ownership.

**You do not need to clone every buffer in every system.** If the producer is willing to transfer **exclusive ownership** of the buffer to the WebSocket until completion, you can avoid copying to reduce CPU and allocations. The choice is **copy vs exclusive ownership**, not defaulting to "just call duplicate()".

## 5. ByteBuffer.wrap, duplicate, slice, asReadOnlyBuffer: Aliasing Is Not Deep Copy

This is one of the most common misconceptions:

| Operation | Independent byte storage? | Independent position/limit? | If backing storage is modified? |
|---|---|---|---|
| **ByteBuffer.wrap(byte[])** | No: uses the same array | Buffer keeps its own state | Buffer sees the array changes |
| **original.duplicate()** | No: shares content | Yes | Both views see the data change |
| **original.slice()** | No: uses a subsequence of the same content | Yes | Both views see the data change |
| **original.asReadOnlyBuffer()** | No: shares content | Yes | Read-only view still sees data changes from aliases |
| **ByteBuffer.allocate(n) + put(source.duplicate())** | Yes, new byte storage | Yes | Snapshot does not change if source changes |
| **Arrays.copyOf(byteArray, length)** | Yes, new array | Not applicable | New array is unaffected by the original array |
| **byteArray.clone()** | Yes, new array | Not applicable | New array is independent of the original array |

**A Read-only ByteBuffer does not have immutable underlying bytes.** It prevents **writing through that view itself**, but does not stop the holder of the original buffer or backing byte[] from modifying the data. Therefore, using **asReadOnlyBuffer()** for sendBinary does not automatically solve races, and you must still obey the Javadoc "buffer must not be accessed until after future completed".

**duplicate()/slice()** are useful for changing **position/limit independently** within one thread or a phase with clear ownership, but the byte content **is still shared**. If you send view A and modify original B before completion, you can still alter the payload. **Do not use duplicate as if it had copied the bytes.**

### With direct ByteBuffers

**ByteBuffer.allocateDirect(...)** allocates direct/off-heap memory; **asReadOnlyBuffer/duplicate/slice** of a direct buffer continue to share that direct memory region. Even though there is no accessible backing byte[], ownership and the no-access rule during send **still apply**. Do not free/mutate direct memory via native/JNI/foreign memory mechanisms while the provider is still sending.

## 6. Runnable Java 17: Proving Aliasing and Snapshot with ByteBuffer and CharBuffer

The first program does not need a server/network. It creates an array-backed ByteBuffer, views sharing storage, an independent deep copy, and a CharBuffer read-only view. After modifying the original array, we observe **the views change while the snapshot does not**.

Create the file **BufferAliasingDemo.java**:

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;

public class BufferAliasingDemo {
    public static void main(String[] args) {
        byte[] array = {10, 20, 30, 40};
        ByteBuffer original = ByteBuffer.wrap(array);
        original.position(1);
        original.limit(3);

        ByteBuffer slice = original.slice();
        ByteBuffer readOnly = original.asReadOnlyBuffer();
        ByteBuffer copy = ByteBuffer.allocate(original.remaining());
        copy.put(original.duplicate());
        copy.flip();

        array[1] = 99;

        System.out.println("Slice first byte: " + slice.get(0));
        System.out.println("Read-only view first byte: " + readOnly.get(1));
        System.out.println("Independent copy first byte: " + copy.get(0));
        System.out.println("Original position: " + original.position());

        char[] letters = {'O', 'K'};
        CharBuffer charView = CharBuffer.wrap(letters).asReadOnlyBuffer();
        String snapshot = charView.toString();
        letters[0] = 'N';
        System.out.println("Read-only CharBuffer now: " + charView);
        System.out.println("String snapshot: " + snapshot);
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac --release 17 BufferAliasingDemo.java
java BufferAliasingDemo
~~~

Exact output:

~~~text
Slice first byte: 99
Read-only view first byte: 99
Independent copy first byte: 20
Original position: 1
Read-only CharBuffer now: NK
String snapshot: OK
~~~

**Compiled with javac --release 17 and ran successfully**, output matches the six lines above.

### Analysis

- original sets **position=1, limit=3**, so **original.remaining()=2** and slice contains the logical index range corresponding to the two bytes 20, 30.
- **slice.get(0)** returns 99 after **array[1]=99**, proving the view shares backing storage.
- **readOnly.get(1)** also returns 99; read-only only forbids put through the view, without making the backing memory immutable.
- **copy.put(original.duplicate())** creates a new buffer with bytes 20/30 and keeps original.position() at 1. When the original array changes, copy still starts with 20.
- **CharBuffer.wrap(letters).asReadOnlyBuffer()** still observes changes in letters[0], so it prints NK.
- **String snapshot = charView.toString()** stores the content OK independently of the letters array; modifying letters afterward does not change the snapshot content.

**Limitation of the example:** all mutations happen sequentially and **before a send**; it does not demonstrate "modifying while a WebSocket send is pending" because that is forbidden by the Javadoc and can produce undefined results. The goal is to prove storage aliasing so you avoid passing mutable aliases into an in-flight send.

## 7. Real WebSocket on Loopback: Sending an Immutable String and an Owned ByteBuffer

Java SE 17 has a **WebSocket client API** in **java.net.http**, but does not provide a **symmetric public WebSocket server API** in the same package. To make the exercise self-contained without external server dependencies, the program below creates a **loopback ServerSocket** simulating **a very small subset of the RFC 6455 WebSocket protocol**:

1. Receives the HTTP Upgrade request, extracts Sec-WebSocket-Key, and computes Sec-WebSocket-Accept per RFC 6455.
2. Returns the **101 Switching Protocols** handshake.
3. Receives small **masked** frames from the Java client: one text frame, one binary frame, and one close frame.
4. Unmasks and records the payload; returns close frame 1000 and exits.

**This is a minimal mock server dedicated to testing**, not a production WebSocket server: it only supports short frames <=125 bytes with FIN=true, and does not handle large fragmented frames, extensions, most control opcodes, Origin/authentication checks, TLS, rate limiting, or multiple clients. For a real server, use a battle-tested WebSocket framework.

The client uses **HttpClient.newWebSocketBuilder().buildAsync(...)**, sends a **String snapshot** of a StringBuilder, and a **ByteBuffer wrapping a cloned array**. After initiating the send:

- It is safe to modify **StringBuilder draft**, because WebSocket is using a separate **String stableText**.
- It is safe to modify **the original array**, because WebSocket is using an **owned ByteBuffer** wrapping **original.clone()**.
- **Do not** read/modify the **owned ByteBuffer** until binarySend completes.
- When binarySend completes normally, **owned.remaining() == 0**.

File **WebSocketPayloadOwnershipDemo.java**:

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
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class WebSocketPayloadOwnershipDemo {
    private record Received(String text, String binaryHex) {}

    private static String httpLine(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        while (out.size() <= 4096) {
            int b = in.read();
            if (b == -1) throw new EOFException("EOF in handshake");
            if (b == '\n') {
                byte[] bytes = out.toByteArray();
                int len = bytes.length;
                if (len > 0 && bytes[len - 1] == '\r') len--;
                return new String(bytes, 0, len, StandardCharsets.US_ASCII);
            }
            out.write(b);
        }
        throw new IOException("Oversized handshake line");
    }

    private static String acceptKey(String key) throws Exception {
        String merged = key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
        byte[] sha1 = MessageDigest.getInstance("SHA-1")
                .digest(merged.getBytes(StandardCharsets.US_ASCII));
        return Base64.getEncoder().encodeToString(sha1);
    }

    private static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder();
        for (byte b : bytes) {
            out.append(String.format("%02x", b & 0xff));
        }
        return out.toString();
    }

    private static Received serve(ServerSocket listener) throws Exception {
        try (Socket peer = listener.accept()) {
            peer.setSoTimeout(5000);
            InputStream in = peer.getInputStream();
            OutputStream out = peer.getOutputStream();
            String requestLine = httpLine(in);
            if (!requestLine.startsWith("GET /demo ")) {
                throw new IOException("Unexpected handshake path");
            }

            String key = null;
            for (String line; !(line = httpLine(in)).isEmpty();) {
                if (line.regionMatches(true, 0, "Sec-WebSocket-Key:", 0, 18)) {
                    key = line.substring(18).trim();
                }
            }
            if (key == null) throw new IOException("No websocket key");

            String response = "HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + acceptKey(key) + "\r\n\r\n";
            out.write(response.getBytes(StandardCharsets.US_ASCII));
            out.flush();

            String text = null, binary = null;
            boolean closed = false;
            while (!closed) {
                int first = in.read(), second = in.read();
                if (first < 0 || second < 0) {
                    throw new EOFException("EOF before websocket close");
                }
                boolean fin = (first & 0x80) != 0;
                int opcode = first & 0x0f;
                int length = second & 0x7f;
                if (!fin || length >= 126 || (second & 0x80) == 0) {
                    throw new IOException("Demo expects short masked frames");
                }
                byte[] mask = in.readNBytes(4);
                byte[] data = in.readNBytes(length);
                if (mask.length != 4 || data.length != length) {
                    throw new EOFException("Truncated frame");
                }
                for (int i = 0; i < data.length; i++) {
                    data[i] ^= mask[i % 4];
                }
                switch (opcode) {
                    case 1 -> text = new String(data, StandardCharsets.UTF_8);
                    case 2 -> binary = hex(data);
                    case 8 -> {
                        out.write(new byte[] {
                                (byte) 0x88, 2, 0x03, (byte) 0xE8});
                        out.flush();
                        closed = true;
                    }
                    default -> throw new IOException("Unexpected opcode: " + opcode);
                }
            }
            if (text == null || binary == null) {
                throw new IOException("Expected text and binary frames");
            }
            return new Received(text, binary);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket(
                0, 8, InetAddress.getByName("127.0.0.1"))) {
            Future<Received> serverResult =
                    worker.submit(() -> serve(listener));

            URI uri = URI.create(
                    "ws://127.0.0.1:" + listener.getLocalPort() + "/demo");
            WebSocket webSocket = HttpClient.newHttpClient()
                    .newWebSocketBuilder()
                    .connectTimeout(java.time.Duration.ofSeconds(5))
                    .buildAsync(uri, new WebSocket.Listener() {})
                    .get(5, TimeUnit.SECONDS);

            StringBuilder draft = new StringBuilder("HELLO");
            String stableText = draft.toString();
            CompletableFuture<WebSocket> textSend =
                    webSocket.sendText(stableText, true);
            draft.replace(0, draft.length(), "CHANGED");
            textSend.get(5, TimeUnit.SECONDS);

            byte[] original = {1, 2, 3, 4};
            ByteBuffer owned = ByteBuffer.wrap(original.clone());
            CompletableFuture<WebSocket> binarySend =
                    webSocket.sendBinary(owned, true);
            original[0] = 99;
            binarySend.get(5, TimeUnit.SECONDS);
            int remainingAfterSend = owned.remaining();

            webSocket.sendClose(WebSocket.NORMAL_CLOSURE, "done")
                    .get(5, TimeUnit.SECONDS);

            Received result = serverResult.get(5, TimeUnit.SECONDS);
            System.out.println("Server text: " + result.text());
            System.out.println("Server binary: " + result.binaryHex());
            System.out.println("Builder after change: " + draft);
            System.out.println("Original byte[0]: " + original[0]);
            System.out.println("Buffer remaining after send: "
                    + remainingAfterSend);
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac --release 17 WebSocketPayloadOwnershipDemo.java
java WebSocketPayloadOwnershipDemo
~~~

Stdout on success:

~~~text
Server text: HELLO
Server binary: 01020304
Builder after change: CHANGED
Original byte[0]: 99
Buffer remaining after send: 0
~~~

**Compiled with javac --release 17 and ran successfully**, output matches the five lines above in the loopback test environment.

### What does each output line prove?

- **Server text: HELLO** proves WebSocket received the **String snapshot**, not the **StringBuilder draft** being modified. They are two different objects.
- **Server binary: 01020304** proves WebSocket received the independent **cloned array**, not the original array whose first byte the caller changed to 99.
- **Builder after change: CHANGED** does not mean any mutable CharSequence is allowed to be modified before completion; the builder in the demo **is not the object passed to sendText**.
- **Original byte[0]: 99** shows that original can be modified when the send uses a clone, with no alias to the owned bytes.
- **Buffer remaining after send: 0** matches the **sendBinary** contract when the future succeeds. Reading remaining only happens **after binarySend.get(...) completes**.

### What the program does not claim

- **Does not claim** a real WebSocket server can be implemented with a few dozen lines of parser. The server in the demo lacks many RFC 6455 checks and only serves the payload ownership lesson.
- **Does not measure** server business processing or data persistence; it only decodes frames and prints the received text/bytes.
- **Does not test modifying a StringBuilder/ByteBuffer while pending**, because that operation violates the Java 17 API contract. We test **valid snapshot/clone** instead of relying on a race.
- **Does not promise** every network will run with the exact same timing. The code uses loopback, socket timeout, and Future.get timeout; if a firewall blocks loopback or the system is very slow, the program may report an error.
- **Does not test large fragments, ping/pong, or TLS wss**, so production needs a WebSocket framework with an RFC-compliant server, max frame/message length, auth/TLS, and backpressure.

## 8. Multi-Fragment Messages: last=false, last=true, and Ordering

The **last** parameter in **sendText/sendBinary** marks **whether this send completes the message**.

~~~java
webSocket.sendText("Part one ", false)
        .thenCompose(ws -> ws.sendText("part two", true))
        .join();
~~~

This is an illustrative snippet assuming the WebSocket is already connected. Both sendText calls belong to **one text message**. When sendText("Part one ", false) completes, the message is **incomplete**; the next sendText(..., true) closes the message.

You must distinguish:

- **A completed send operation** and **a complete WebSocket message** are two different concepts.
- **last=false** allows creating multi-fragment messages; **last=true** signals the final fragment of the message.
- Java 17 WebSocket can fail the sendText or sendBinary future with **IllegalStateException** when another **text/binary send operation is pending**.
- When a **binary message is in progress** (previous binary fragment had last=false), you must not switch to a **text message** until the binary message finishes; conversely, an in-progress text message must not switch to binary.
- Only send the next fragment after the previous fragment completes, for example using **thenCompose**, to avoid concurrency ordering errors.
- Text fragments must contain valid UTF-16 data per the contract; do not split a surrogate pair into a malformed CharSequence and expect the protocol to fix it.

### Anti-pattern: sending concurrently on the same WebSocket

~~~java
CompletableFuture<WebSocket> first =
        webSocket.sendText("first", true);
CompletableFuture<WebSocket> second =
        webSocket.sendBinary(ByteBuffer.wrap(new byte[] {1}), true);
~~~

This is an **error-prone pattern**: **second** may encounter **IllegalStateException** if the first text/binary send is still pending. Even if both futures complete on a fast machine, you cannot rely on scheduling for correct ordering. If you want to send multiple messages, **serialize sends** via a chain/queue.

### Sequential pattern using futures

~~~java
CompletableFuture<WebSocket> done = webSocket
        .sendText("first", true)
        .thenCompose(ws ->
                ws.sendBinary(ByteBuffer.wrap(new byte[] {1}), true));

done.join();
~~~

Here the sendBinary call is only created when sendText completes successfully. **The ByteBuffer is created fresh inside the lambda**, not accessed by any external thread, so it fits the ownership model. If first fails, thenCompose is skipped and the overall future reports an error; do not attempt to send the next message on a connection in an unknown state.

## 9. Designing Ownership Transfer or Snapshots in an Outbound Queue

In a real WebSocket application, messages may be created by hundreds of request producers and placed into a queue. **Producers should not retain the ability to modify already-enqueued data if the WebSocket will send it later**.

A clear model:

~~~text
Producer builds mutable payload
      |
      v
OPTION A: snapshot into String/byte[]
    or
OPTION B: exclusive transfer of object/buffer, producer no longer touches it
      |
      v
Bounded outgoing queue
      |
      v
Single sender owner dequeues
      |
      v
sendText/sendBinary -> CompletableFuture
      |
      +-- future success --> mark sent, release/recycle buffer
      |
      +-- future failed  --> mark failed, cleanup/close/retry policy
      |
      v
Dequeue next message
~~~

### Do not let the queue hold mutable producer references

If the queue holds a **StringBuilder** and the producer continuously clears/reuses it after enqueueing, the message may have already changed even **before sendText starts**. The ownership principle should apply **from the moment of enqueueing**, not only from the moment of calling send.

If the queue holds **ByteBuffer.duplicate()**, the producer modifying the array/original buffer still changes the data in the view. **duplicate does not solve data sharing**.

### Java queue pattern (illustrative, not a standalone file)

~~~java
final class SequentialSender {
    private final WebSocket socket;
    private CompletableFuture<WebSocket> tail;

    SequentialSender(WebSocket socket) {
        this.socket = socket;
        this.tail = CompletableFuture.completedFuture(socket);
    }

    synchronized CompletableFuture<WebSocket> sendTextSnapshot(
            CharSequence source) {
        String owned = source.toString(); // Copy on enqueue.
        tail = tail.thenCompose(ws -> ws.sendText(owned, true));
        return tail;
    }

    synchronized CompletableFuture<WebSocket> sendBinarySnapshot(
            ByteBuffer source) {
        ByteBuffer owned = ByteBuffer.allocate(source.remaining());
        owned.put(source.duplicate()); // Copy before enqueue.
        owned.flip();
        tail = tail.thenCompose(ws -> ws.sendBinary(owned, true));
        return tail;
    }
}
~~~

The snippet above **only illustrates the serialization pattern**, assuming WebSocket, CompletableFuture, and ByteBuffer are imported; in production you need **constructor validation, a bounded queue, close/error handling, per-message identity, and deadlines**. Note that **source** must be stable during the snapshot: synchronized on the method is not enough if the producer thread does not use the same lock when modifying source.

Because **tail** will complete exceptionally when a send fails, **subsequent thenCompose stages will not automatically keep sending**. That is a suitable fail-stop choice when the connection errors; the application must **fail the remaining queued messages, clean up data, and decide on reconnect/retry**. If you want a recovery mechanism, build an explicit state machine rather than simply swallowing errors with exceptionally and continuing as if everything is still fine.

### Backpressure: do not create unbounded futures and buffer copies

A sequential sender can still OOM if 100,000 producers continuously send 1 MiB payloads into the queue. You need:

- **maxMessages**, **maxQueuedBytes**, and **maxInFlightBytes**.
- Reject/await/backpressure mechanisms when the queue is full.
- Deadline/TTL for messages waiting too long.
- Cancellation policy for messages not yet dequeued and messages that have started sending.
- Observability: queue depth, active send duration, success/failure, bytes sent, retries.
- Retry only with a **stable payload snapshot** and with an **idempotency key** if the application protocol needs to avoid duplicate side effects.

**A WebSocket typically has one pending text/binary send** under the Java 17 contract. For good throughput, optimize scheduling/payload size and backpressure; **do not** call sendText/sendBinary concurrently hoping the provider will serialize them for you.

## 10. Completion, Cancellation, Timeout, and Failure

**CompletableFuture<WebSocket>** can complete in these ways:

| State | Safe behavior |
|---|---|
| **Success** | Send operation succeeded per API; safe to reuse/free payload; binary buffer remaining == 0 |
| **Exceptional completion** | Extract root cause, notify application, clean up; do not assert binary position is still original |
| **Caller calls future.cancel(...)** | Do not assume bytes were definitely not transmitted; preserve ownership until lifecycle is confirmed per implementation/policy |
| **Timeout on future.get(timeout)** | Only bounds the thread's wait time, does not prove the send has stopped |
| **WebSocket.abort()** | Abruptly closes WebSocket input/output; affects pending sends, futures must be handled |
| **WebSocket.sendClose(...)** | Initiates orderly output closure; does not substitute for a business ACK |

### Failure does not automatically restore the payload

If **sendBinary** fails, avoid writing:

~~~java
ByteBuffer buffer = originalBuffer;
webSocket.sendBinary(buffer, true).join();
// On error: call webSocket.sendBinary(buffer, true) again with the old buffer.
~~~

This is an **anti-pattern**, especially when the code does not keep the source bytes elsewhere. The buffer may have been partially consumed or the connection closed. For retries, create a new connection when needed, **build a new ByteBuffer from an immutable snapshot**, and check whether business logic permits resending. A send timeout does not prove the peer did not receive the message.

### Caller-side timeout is not guaranteed send cancellation

~~~java
CompletableFuture<WebSocket> pending =
        webSocket.sendBinary(ownedBuffer, true);

try {
    pending.get(2, TimeUnit.SECONDS);
} catch (TimeoutException waitExpired) {
    // DO NOT call ownedBuffer.clear() here:
    // timeout only means the caller stopped waiting; the send may still be pending.
    webSocket.abort();
    // Apply cleanup policy once future/lifecycle is confirmed.
}
~~~

This is an **illustrative snippet** with imports and ownedBuffer already initialized. In a real application, organize the async lifecycle, retain the future, and handle exceptional completion/cancellation; do not treat a **TimeoutException from get** as a signal of permission to reuse the buffer. **abort()** is an abrupt close, not a promise that the receiver has not processed the bytes.

### Can you read the ByteBuffer when the future completes with an error?

The Javadoc stipulates "buffer must not be accessed until after [the returned future has completed]". After completion, in terms of timing the pending phase may be over, but **there is no guarantee that the byte position reflects the number of bytes successfully sent if the future failed**. For systems requiring correctness, **discard that buffer and rebuild from the canonical source**. Only when the future completes **normally** is remaining == 0 a clear guarantee.

### Error handling pattern with whenComplete

~~~java
CompletableFuture<WebSocket> pending =
        webSocket.sendText(immutableText, true);

pending.whenComplete((socket, error) -> {
    if (error == null) {
        notifySendSucceeded();
    } else {
        notifySendFailed(error);
    }
});
~~~

This is an illustrative snippet with immutableText and user-defined callbacks. Callbacks should not block the networking thread with heavy DB/CPU work. If metrics or long processing are needed, offload to a bounded executor. **A callback reporting send success is not an ACK from the receiving application**.

## 11. sendPing/sendPong Also Have ByteBuffer Ownership

Two WebSocket control APIs:

~~~java
CompletableFuture<WebSocket> ping = webSocket.sendPing(pingData);
CompletableFuture<WebSocket> pong = webSocket.sendPong(pongData);
~~~

**pingData/pongData are ByteBuffers and must not be accessed until the corresponding future completes.** The protocol payload limit is **125 bytes**; if exceeded, sendPing/sendPong may return a failed future or throw **IllegalArgumentException** per the API contract. **Ping/Pong also have their own pending-state policy**; do not make unbounded control send calls while a ping/pong send is pending.

The Java 17 Javadoc states that the WebSocket implementation automatically replies with **Pong** when receiving a Ping, so most applications do not need to manually send Pong in onPing. If the program uses Ping to check liveness, do not treat **sendPing future completed** as proof that the peer replied with Pong; you need a mechanism to observe **onPong** and a deadline.

Also do not pass a ByteBuffer currently used in **sendBinary** to **sendPing** before the binary future completes; even though the two methods have different names, **ownership of the same data** is not automatically separated.

## 12. Receiving Data in Listener Has the Reverse Ownership Contract

The topic focuses on **before send completion**, but when programming WebSockets you need to distinguish **buffers owned by the sender** from **buffers provided by the provider to the receiver**.

When calling **sendBinary(data, last)**, **the application provides the buffer to the provider** and **must not access it until the send future completes**.

When WebSocket.Listener invokes **onBinary(WebSocket, ByteBuffer data, boolean last)**, the ownership direction reverses: **the provider gives the buffer to the listener**. According to the Java 17 Javadoc, **the CompletionStage returned by the listener** signals when the WebSocket can **reclaim the buffer**. **The listener must not access the ByteBuffer after that stage completes**. If processing is needed after the callback returns/completes, **copy the data immediately while you still have access** or keep the stage uncompleted until processing finishes.

Similarly for **onText(WebSocket, CharSequence data, boolean last)**, the CharSequence may be reclaimed when the corresponding CompletionStage completes. Do not store a reference to the provider-supplied CharSequence and read it from another task after returning a completed stage, unless you have snapshotted it into a String.

~~~text
OUTGOING:
  App owns payload  --- sendBinary(buffer) ---> WebSocket provider
       |                                        |
       +--- do not access buffer until           |
            send future completes <--------------+

INCOMING:
  WebSocket provider --- onBinary(buffer) ----> App listener
       |                                         |
       +<--- listener CompletionStage completes -+
                provider may reclaim buffer

If you need to keep data longer: SNAPSHOT into an independent object.
~~~

**An important detail:** request(n) on WebSocket **controls the number of receive callback invocations** per the contract; it **does not** transfer access rights of outbound sendBinary buffers or automatically limit how many bytes you are enqueueing to send. **Request(1) on receive does not mean one byte**, similar to Flow-style demand counters.

### onText/onBinary and last

With Listener, **boolean last** indicates whether the callback is receiving the final fragment of the message. If you need to parse a complete message, you must accumulate/stream according to application framing and **respect size limits**; do not assume one callback corresponds to one entire message. Retaining data across callbacks must obey the CompletionStage lifecycle; snapshotting for long async processing is the cleanest approach.

## 13. How Thread-Safe Are CharSequence and ByteBuffer?

### String and StringBuilder

- **String is immutable** and its content can be safely shared between threads after proper initialization; sendText does not need to be given a mutable StringBuilder.
- **StringBuilder is mutable and not synchronized**; it requires single ownership or locking for both the snapshot producer and the writer.
- **StringBuffer has synchronized methods** but does not allow mutation while a send operation is pending; synchronizing individual methods does not change the WebSocket contract.
- **Custom CharSequence** may read data lazily from an external buffer or a memory-mapped file; do not assume it is immutable just because the interface only has length/charAt/subSequence.

### ByteBuffer

- **Buffer is not thread-safe** according to the Java NIO Buffer Javadoc.
- **position/limit/mark are mutable state**; even a relative get() changes position.
- **absolute get(index)** does not modify position but is still a buffer access: **do not call while sendBinary is pending**.
- **slice/duplicate/readOnly** have their own position, but **share bytes**; concurrent mutation of the backing storage is still dangerous.
- For **array-backed** buffers, if you hold the raw byte[], treat it as an alias: do not modify the array while the provider is sending the buffer wrapping that array.
- For **direct** buffers, do not modify the memory via foreign/native aliases while a send is pending.
- If a ByteBuffer is placed in a pool, **do not return it to the pool before completion**: another thread could borrow it and overwrite its content.

### Memory visibility and completion

**CompletableFuture completion** is a good coordination point to transfer ownership back to the application. To guarantee no race, only start reusing **after observing the future has completed**, for example via **get/join/thenRun/whenComplete** and with ownership discipline.

Do not poll **buffer.position()** to check send progress. That is a forbidden access while pending and is not a reliable progress API. Measure progress using **future state, precomputed expected bytes, and send latency/queue metrics**, not by "peeking" at the buffer position being updated by the implementation.

## 14. Optimizing Copy vs Zero-Copy: Conditional Choices

**Snapshot/copy** reduces aliasing bugs but uses more RAM/CPU. **Zero-copy/ownership transfer** can be efficient when exclusive ownership can be clearly enforced.

| Strategy | Data before send | What the producer may do | Main cost |
|---|---|---|---|
| **String snapshot** | StringBuilder.toString() | Modify builder after snapshot | Allocating a new String |
| **ByteBuffer.allocate + copy** | New buffer containing the bytes to send | Modify source after copy finishes | Copying bytes and extra memory |
| **byte[].clone() + ByteBuffer.wrap** | Independent cloned array | Modify original array after clone | Copying the entire array |
| **Transfer exclusive ByteBuffer** | Same buffer object handed to sender | **Do not read/modify** buffer until completion | Harder ownership management, less copying |
| **duplicate()/slice()** | View sharing content | Do not modify backing storage while view send is pending | No byte copy, **no data isolation** |
| **asReadOnlyBuffer()** | Read-only view sharing storage | Do not modify original storage while view send is pending | No byte copy, only forbids writing via view |

**Measure before deciding:** for small payloads, String/byte[] copying can be much cheaper than the cost of debugging races. For large payloads/high throughput, pool management and exclusive ownership can avoid copying, but require strict binding to message lifecycle and backpressure. Never optimize by violating the contract.

### Ownership timeline table

| Milestone | Passed mutable CharSequence | Passed ByteBuffer |
|---|---|---|
| Before calling send | Caller may modify per its contract | Caller may configure position/limit and data |
| Right after calling send, future not done | **Do not modify data** | **Do not access buffer** |
| Future done normally | May be reused, if no other party holds it | May be read/reused; remaining()==0 |
| Future done with error | May process data after lifecycle ends, but do not assume message did not reach peer | Do not trust byte state; rebuild from snapshot on retry |
| Only timeout on future.get(timeout) | **Must not consider send completed** | **Must not consider send completed** |
| Connection abort/close | Clean up per futures and contract | Clean up/recycle once certain no operation is still using it |

## 15. Security and Data Size Limits

Ownership bugs are not just logic bugs. In a system exchanging **tokens, financial orders, PII, or binary protocols**, accidentally mutating an in-flight payload can send the wrong user ID, wrong request ID, or another message's data.

Protective principles:

- **Do not log payload secrets** when debugging races; log message type, ID, controlled hashes, byte count, and future state.
- **Do not share a ByteBuffer pool slot** across two sending sessions; pools must have leases/release-on-completion.
- **Limit message size and queued bytes**; a malicious producer could create many large messages and hold heap/direct memory for too long.
- **WebSocket wss:// with TLS** when traversing untrusted networks; ws:// is only for loopback/lab or environments with separate protection.
- **Validate input** before snapshotting/sending; an oversized StringBuilder can still cause OOM when toString creates a new String.
- **Do not overwrite credentials between messages** using a shared char[]/ByteBuffer while the previous send has not completed.
- **Server-side authorization** and application ACKs are still necessary; WebSocket transport does not grant permissions or guarantee commit.

### Relationship with backpressure

A slow server/peer causes send futures to complete slowly, making **in-flight buffers** live longer. If you keep enqueueing snapshots unboundedly, heap/direct memory grows. Design resource quotas, backlog alerts, and appropriate drop/reject/cancel policies; do not increase concurrent sends on the same connection beyond the contract to "run faster".

## 16. Common Programming Mistakes

### Mistake A — Modifying StringBuilder right after sendText

**Wrong:** passing builder into sendText and immediately calling append/clear/replace. **Right:** pass a String snapshot or wait for the future to finish before modifying builder.

### Mistake B — Assuming sendText copied everything upon returning

**Wrong:** relying on "the test machine runs fast so the message is right". **Right:** follow the Javadoc, do not infer when the implementation reads the data.

### Mistake C — Calling buffer.remaining() to log right after sendBinary

**Wrong:** that is still accessing the ByteBuffer while the future is pending. **Right:** save expectedLength before sending; only read remaining after success.

### Mistake D — Calling rewind/flip/clear before completion

**Wrong:** changing the position/limit that WebSocket is currently using. **Right:** one operation holds exclusive access to the buffer until the future is done.

### Mistake E — Using duplicate/slice as a "copy"

**Wrong:** both buffers share content. **Right:** clone the array or allocate+copy if independent data is needed.

### Mistake F — Treating asReadOnlyBuffer as making all aliases immutable

**Wrong:** the read-only view sees the backing array modified from another source. **Right:** manage backing storage or deep copy.

### Mistake G — Reusing the buffer after future.get(timeout) throws TimeoutException

**Wrong:** get timeout only means the caller's wait expired; the send may still be pending. **Right:** protect ownership until the lifecycle is resolved and clean up/cancel per policy.

### Mistake H — Sending multiple text/binary operations concurrently

**Wrong:** calling sendText and sendBinary at the same time hoping the JDK queues them automatically. **Right:** chain with thenCompose or a bounded send queue; handle IllegalStateException.

### Mistake I — Leaving last=false and switching message type

**Wrong:** text in progress then calling sendBinary; may throw IllegalStateException. **Right:** finish the message of the same type with last=true before switching types.

### Mistake J — Thinking future success means the server processed it

**Wrong:** no business ACK. **Right:** add app-level response/ACK/request ID when the protocol needs exactly-once/effectively-once semantics.

### Mistake K — Returning/recycling a pooled ByteBuffer before future done

**Wrong:** another consumer could overwrite the bytes. **Right:** retain the lease with the future, release after completion, and do not reuse when state is unclear.

### Mistake L — Keeping a CharSequence from Listener after receive stage completion

**Wrong:** the provider may reclaim the data. **Right:** create a String snapshot/byte[] copy while you still have access.

## 17. Ownership and Failure Test Matrix

| Test | Setup | Expectation |
|---|---|---|
| Immutable text | Send String "HELLO" | Server receives HELLO |
| Mutable builder snapshot | Snapshot builder then modify builder | Server still receives the old snapshot |
| Owned binary buffer | Clone array then send | Server sees bytes of the clone |
| Binary completion | sendBinary future succeeds | ByteBuffer.remaining()==0 after future done |
| ByteBuffer.slice alias | Modify original backing array | slice sees changed bytes |
| ByteBuffer.read-only alias | Modify backing array | read-only view still sees changed bytes |
| Deep copy | allocate+put from source | snapshot does not change with source |
| CharBuffer read-only alias | Modify source char[] | view sees new data |
| String snapshot | String created before modifying char[] | String does not change |
| Fragmented text | sendText(...,false) then chained sendText(...,true) | One complete message, in correct order |
| Concurrent text+binary sends | Send while another send is pending | May complete exceptionally with IllegalStateException |
| I/O failure | Close peer while send is running | Future failed; clean up, do not blindly retry old buffer |
| Wait timeout | get(timeout) expires | Do not reuse payload if send is still pending |
| Pool reuse | Per-send lease | No buffer slot is lent out before completion |
| High concurrency | N producers sending messages | Bounded queue/bytes, no OOM |
| Malformed UTF-16 | Unpaired surrogate in lab test | sendText may fail with IOException via future |
| Backpressure | Slow reading peer | Futures take longer, queue stays bounded |

**Do not intentionally mutate a pending object to "test races"**: that behavior already violates the contract. A runtime happening to send the right payload does not prove the code is correct. Instead of creating timing-dependent tests, write tests for snapshots, aliasing, sequencing, queues, and lifecycle.

### Monitoring and Operations

Recommended metrics:

- **websocket_send_pending_count** and duration of uncompleted send futures.
- **websocket_outbound_queued_bytes/messages**, in-flight bytes, number of held buffer leases.
- **websocket_send_success/failure** broken down by message type/cause.
- **websocket_close_code**, abnormal close, timeouts, aborts.
- **application_ack_latency** if the protocol has application-layer ACKs.
- **snapshot_copy_bytes**, direct/heap memory pressure, GC pause, pool exhaustion.

Limit metric cardinality, and do not put message content, tokens, or user credentials into metric labels. A failed operation may be due to IOException, connection closed, or invalid send state; log the cause rather than lumping everything under "timeout".

## 18. Practice Exercises

### Exercise 1 — Prove String snapshot

Run **WebSocketPayloadOwnershipDemo.java**. Change HELLO to a Unicode text with Vietnamese characters; create a String snapshot before sending, and modify draft right after initiating the send. Expect the server to receive **the snapshot content**, not the modified builder. Do not pass the mutable builder directly into send and mutate it to test your luck.

### Exercise 2 — ByteBuffer region bounds

Create an 8-byte byte[], set position=2 and limit=6, create an **independent buffer from remaining()**, then call sendBinary. Verify the server receives the exact byte indexes 2..5 and owned.remaining() equals 0 after successful completion. Do not read the buffer while pending.

### Exercise 3 — Views vs copy

In **BufferAliasingDemo.java**, try using **duplicate()** instead of allocate+copy, then modify the backing array. Explain why the output no longer demonstrates an independent snapshot. Restore the code to the deep copy version.

### Exercise 4 — CharBuffer readonly

Create CharBuffer.wrap(char[]) then asReadOnlyBuffer; modify the source array and compare with a String snapshot. Write a unit test for the differing results, and explain why readonly is not enough for safe sendText if the backing array is mutable.

### Exercise 5 — Message fragmentation

Use a lab WebSocket server that supports standard fragmentation (not the tiny server in the demo which only supports FIN=true). Send sendText("A",false) then thenCompose sendText("B",true). Test that the listener receives the exact message AB; do not switch to binary before text last=true.

### Exercise 6 — Multi-producer queue

Write a SequentialSender class owning a WebSocket, receiving Strings/snapshots from multiple producers through a queue with max 100 messages and max 1 MiB queued data. Chain futures, handle failures fail-stop, and release buffers after completion.

### Exercise 7 — Send deadline

Set a deadline for a pending send on a slow peer. When get(timeout) expires, **do not** call clear/reuse on the buffer. Design abort/cleanup and handle application outcome unknown; distinguish it from future exceptional completion.

### Exercise 8 — Binary pool lease

Create a pool of up to 10 ByteBuffers. Each send acquires a lease, transfers exclusive ownership to the sender, and releases only when the future is done. Measure active leases; test that the same object cannot be owned by two sends concurrently.

### Exercise 9 — Listener ownership

Create a WebSocket Listener.onBinary, copy the payload into a byte[], and return a completed stage. Ensure the task processing the byte[] afterward **does not touch the ByteBuffer passed by the provider**. Compare with onText creating a String snapshot before the callback completes.

### Exercise 10 — Business ACK

Build a message protocol with a requestId where the server sends an ACK after processing. Distinguish **send future success** from **received business ACK**. When the connection closes before ACK, classify the outcome as unknown and retry according to an idempotency policy, avoiding duplicate side effects.

## 19. Self-Check Questions

**1. After sendText returns a CompletableFuture, can you modify the StringBuilder that was passed in?** No, not until the future completes.

**2. Why is String preferred when sending text?** String is immutable, so the caller cannot change its content mid-send.

**3. Can you modify a StringBuilder after creating a String snapshot and passing the snapshot?** Yes, because WebSocket is not using that builder; the snapshot must be consistent at creation time.

**4. Which bytes does sendBinary use?** The [position, limit) region of the ByteBuffer.

**5. Can you call buffer.remaining() while the binary future is not done?** No. The Javadoc states the ByteBuffer must not be accessed until the future completes.

**6. When sendBinary completes normally, what is remaining()?** 0.

**7. When a sendBinary future fails, can you assert the position is still the original one?** No. Do not build retries from assumed buffer state.

**8. Is duplicate() a deep copy?** No. It shares content but has its own position/limit state.

**9. Does slice() share content?** Yes; it is a view of a region of the original buffer's data.

**10. Does asReadOnlyBuffer() guarantee the backing array cannot change?** No. Other aliases can still modify the backing bytes.

**11. Does CharBuffer.asReadOnlyBuffer() make the source char[] immutable?** No.

**12. Does ByteBuffer.wrap(array) copy the array?** No, the buffer shares the original array.

**13. Does byteArray.clone() create separate backing storage?** Yes, for a byte array.

**14. Does TimeoutException from future.get(timeout) mean the send has definitely stopped?** No; it only indicates the waiting thread's timeout expired.

**15. Can you call sendText and sendBinary concurrently on one WebSocket?** Do not rely on that; a pending text/binary send can cause IllegalStateException, so serialize them.

**16. Does last=false mean the WebSocket message is complete?** No; there are more fragments to follow.

**17. Does sendText success mean the server business logic has committed?** No. A business ACK is needed if you want processing confirmation.

**18. Can you access the ByteBuffer being sent by sendPing(ByteBuffer)?** No; you must also wait for the future. Control payload is at most 125 bytes.

**19. Does Listener onBinary use the same ownership rule as sendBinary?** The directions are opposite: an outgoing caller must not access the buffer before send future done; an incoming listener must not access the provider buffer **after the receive stage has completed**.

**20. What rule is needed when using a ByteBuffer pool?** Do not recycle a lease currently held by a future; release after completion/clear lifecycle.

**21. Why shouldn't you use a test that mutates pending data to conclude safety?** Because that violates the contract and results can vary with scheduling/network/provider.

**22. What is the simplest way to avoid mutable CharSequence races?** Snapshot into an immutable String before sending, while synchronizing source data if there are multiple writers.

## Official Documentation Sources

- **Java SE 17 — WebSocket (sendText, sendBinary, sendPing, sendPong, sendClose):** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html
- **Java SE 17 — WebSocket.Listener (ownership of received CharSequence/ByteBuffer):** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html
- **Java SE 17 — WebSocket.Builder (buildAsync):** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html
- **Java SE 17 — ByteBuffer (wrap/duplicate/slice/asReadOnlyBuffer):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- **Java SE 17 — Buffer (position, limit, thread safety):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html
- **Java SE 17 — CharBuffer:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/CharBuffer.html
- **Java SE 17 — CompletableFuture:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **RFC 6455 — The WebSocket Protocol:** https://www.rfc-editor.org/rfc/rfc6455

**Key Takeaway:** For **WebSocket.sendText(CharSequence, last)**, do not modify the **passed CharSequence** until the returned CompletableFuture completes. For **sendBinary(ByteBuffer, last)**, **do not access the passed ByteBuffer** until the future completes; after successful completion, remaining()==0. **slice/duplicate/asReadOnlyBuffer still share backing data**, so they are not deep copies. Use **immutable String snapshots**, **byte[] clone/allocate+copy**, or **exclusive buffer ownership**; serialize send operations with futures, manage backpressure and timeouts/failures, and do not confuse send completion with an application ACK.